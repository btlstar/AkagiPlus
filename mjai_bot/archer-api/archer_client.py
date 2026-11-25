"""Archer API transport with direct HTTP keep-alive; no automatic paid retries."""
from __future__ import annotations
import http.client
import json
import math
import socket
import select
import threading
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_URL="https://la.moxcomic.com"
MAX_BODY=32768
MAX_RESPONSE=262144
DECISION_BUDGET=4.4

class ArcherError(Exception):
    def __init__(self,code,message,*,status=0,retry_after=0):
        super().__init__(message)
        self.code=str(code)
        self.status=status
        self.retry_after=min(120.0,max(0.0,float(retry_after)))

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        return None

def compact(value):
    return json.dumps(value,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode("utf-8")

class ArcherClient:
    def __init__(self,settings):
        self.base=str(settings.get("api_url",DEFAULT_URL)).strip().rstrip("/")
        parsed=urllib.parse.urlsplit(self.base)
        loopback=parsed.hostname in ("127.0.0.1","localhost","::1")
        if (parsed.scheme!="https" and not(parsed.scheme=="http" and loopback)) or not parsed.hostname:
            raise ArcherError("configuration","接口地址应为 HTTPS 根地址。")
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("","/"):
            raise ArcherError("configuration","接口地址只填写服务器根地址，不含 /v1/decide。")
        self.parsed=parsed
        self.key=str(settings.get("api_key","")).strip()
        if not self.key or any(c.isspace() for c in self.key):
            raise ArcherError("configuration","请在 Archer API 机器人配置中填写专用 API 密钥。")
        self.timeout=min(4.0,max(0.5,float(settings.get("timeout_ms",4000))/1000.0))
        self.proxy=str(settings.get("proxy_url","")).strip()
        if self.proxy:
            proxy=urllib.parse.urlsplit(self.proxy)
            if proxy.scheme not in ("http","https") or not proxy.hostname:
                raise ArcherError("configuration","此插件的代理仅支持 HTTP/HTTPS；SOCKS 请使用本机混合端口。")
            handler=urllib.request.ProxyHandler({"http":self.proxy,"https":self.proxy})
        else:
            handler=urllib.request.ProxyHandler({})
        self.opener=urllib.request.build_opener(handler,NoRedirect())
        self.connection=None
        self.last_timing={}
        self._warm_lock=threading.Lock()
        self._warm_connection=None
        self._warm_generation=0
        self._warming=False
        self._last_used=0.0

    def new_connection(self,timeout):
        cls=http.client.HTTPSConnection if self.parsed.scheme=="https" else http.client.HTTPConnection
        return cls(self.parsed.hostname,self.parsed.port,timeout=timeout)

    def prepare_async(self):
        # Prepare TLS only: no credentials, HTTP requests or paid inference.
        if self.proxy or self.parsed.scheme!="https":
            return
        with self._warm_lock:
            if self._warming or self._warm_connection is not None:
                return
            self._warming=True
            generation=self._warm_generation
        def prepare():
            connection=self.new_connection(min(2.0,self.timeout))
            try:
                connection.connect()
                with self._warm_lock:
                    if generation==self._warm_generation:
                        self._warm_connection=(connection,time.monotonic())
                        connection=None
            except (OSError,http.client.HTTPException):
                pass
            finally:
                if connection is not None:
                    connection.close()
                with self._warm_lock:
                    self._warming=False
        threading.Thread(target=prepare,daemon=True,name="archer-tls-prepare").start()

    def take_prepared_connection(self):
        with self._warm_lock:
            warmed=self._warm_connection
            self._warm_connection=None
        if warmed is None:
            return False
        connection,created=warmed
        if time.monotonic()-created>15.0:
            connection.close()
            return False
        self.connection=connection
        return True

    def close(self):
        with self._warm_lock:
            self._warm_generation+=1
            if self._warm_connection is not None:
                self._warm_connection[0].close()
                self._warm_connection=None
        if self.connection is not None:
            self.connection.close()
            self.connection=None

    def request(self,path,payload=None):
        body=None if payload is None else compact(payload)
        if body is not None and len(body)>MAX_BODY:
            raise ArcherError("too_large","本小局事件超过 Archer 32 KB 限制，已停止本次请求。")
        headers={"Authorization":"Bearer "+self.key,"Accept":"application/json","Content-Type":"application/json",
                 "User-Agent":"AkagiPlus-Archer/0.4.5"}
        timeout=self.timeout if payload is not None else 10.0
        started=time.perf_counter()
        reused=self.connection is not None
        prepared=False
        connect_attempts=0
        phase="connect"
        failure=None
        connect_ms=None
        deadline=started+(DECISION_BUDGET if payload is not None else 10.0)
        status=None
        response_headers={}
        try:
            if self.proxy:
                req=urllib.request.Request(self.base+path,data=body,method="GET" if body is None else "POST",headers=headers)
                try:
                    with self.opener.open(req,timeout=timeout) as response:
                        status=response.status
                        data=response.read(MAX_RESPONSE+1)
                except urllib.error.HTTPError as exc:
                    status,response_headers,data=exc.code,exc.headers,exc.read(MAX_RESPONSE+1)
            else:
                if self.connection is not None and self.connection.sock is not None:
                    # Discard expired/closed idle sockets before any request bytes.
                    expired=time.monotonic()-self._last_used>15.0
                    readable=bool(select.select([self.connection.sock],[],[],0)[0])
                    if expired or readable:
                        self.close()
                        reused=False
                if self.connection is None:
                    prepared=self.take_prepared_connection()
                if self.connection is None:
                    for attempt in range(2):
                        connect_attempts+=1
                        remaining=deadline-time.perf_counter()
                        if remaining<=0:
                            raise TimeoutError()
                        connection=self.new_connection(max(0.05,min(2.0,remaining-0.5)))
                        try:
                            connection.connect()
                            self.connection=connection
                            break
                        except (OSError,http.client.HTTPException):
                            connection.close()
                            if attempt or deadline-time.perf_counter()<0.7:
                                raise
                    connect_ms=round((time.perf_counter()-started)*1000,2)
                self.set_remaining_timeout(self.connection,timeout,deadline)
                phase="send"
                self.connection.request("GET" if body is None else "POST",path,body=body,headers=headers)
                phase="response"
                self.set_remaining_timeout(self.connection,timeout,deadline)
                response=self.connection.getresponse()
                status,response_headers=response.status,response.headers
                # Recalculate the remaining total budget after headers and each
                # body chunk. A slow body cannot get a fresh full wait window.
                chunks=[];size=0
                while size<=MAX_RESPONSE:
                    self.set_remaining_timeout(self.connection,timeout,deadline,response)
                    chunk=response.read1(MAX_RESPONSE+1-size)
                    if not chunk:
                        if response.length not in (None,0):
                            raise http.client.IncompleteRead(b"".join(chunks),response.length)
                        break
                    chunks.append(chunk);size+=len(chunk)
                data=b"".join(chunks)
                if response.will_close or len(data)>MAX_RESPONSE:
                    self.close()
        except (urllib.error.URLError,http.client.HTTPException,TimeoutError,socket.timeout,OSError) as exc:
            failure=type(exc).__name__
            self.close()
            if phase=="response" and isinstance(exc,(TimeoutError,socket.timeout)):
                reason="等待 Archer 响应超时"
            elif phase=="connect":
                reason="无法连接 Archer 服务"
            else:
                reason="Archer 连接中断"
            raise ArcherError("network",reason+"；为避免重复扣费，不自动重发本次请求。") from None
        finally:
            self.last_timing={"total_ms":round((time.perf_counter()-started)*1000,2),
                              "connection_reused":reused and not bool(self.proxy),"connect_ms":connect_ms,
                              "connection_prepared":prepared,"connect_attempts":connect_attempts,
                              "failure_phase":phase if failure else None,"failure_type":failure,
                              "configured_timeout_ms":round(self.timeout*1000),"http_status":status}
            self._last_used=time.monotonic()
        if len(data)>MAX_RESPONSE:
            self.close()
            raise ArcherError("invalid_response","Archer 返回内容过大。")
        if status>=300:
            self.raise_http_error(status,response_headers,data)
        try:
            obj=json.loads(data)
        except (ValueError,UnicodeError):
            raise ArcherError("invalid_response","Archer 返回的内容不是有效 JSON。") from None
        if not isinstance(obj,dict):
            raise ArcherError("invalid_response","Archer 返回结构不正确。")
        if "error" in obj:
            raise ArcherError("invalid_response","Archer 返回了错误，本次没有建议。")
        return obj

    @staticmethod
    def set_remaining_timeout(connection,timeout,deadline,response=None):
        remaining=deadline-time.perf_counter()
        if remaining<=0:
            raise TimeoutError()
        value=min(timeout,remaining)
        connection.timeout=value
        sock=connection.sock
        if sock is None and response is not None:
            # HTTPConnection releases its reference after Connection: close;
            # the response's buffered reader still owns the live socket.
            sock=getattr(getattr(response.fp,"raw",None),"_sock",None)
        if sock is not None:
            sock.settimeout(value)

    @staticmethod
    def raise_http_error(status,headers,data):
        try:
            obj=json.loads(data)
        except (ValueError,UnicodeError):
            obj={}
        detail=obj.get("error",{}) if isinstance(obj,dict) else {}
        code=detail.get("code","http_"+str(status)) if isinstance(detail,dict) else "http_"+str(status)
        messages={
            "invalid_key":"Archer 密钥无效，请检查专用 API 密钥。",
            "insufficient_balance":"Archer Token 余额不足；充值后再开始新对局。",
            "account_disabled":"此账号暂时无法使用开放接口。",
            "unknown_model":"模型名称不正确或尚未开放，请先查询模型。",
            "bad_request":"Archer 拒绝了事件格式，请保留本机日志排查。",
            "engine_rejected":"Archer 无法处理当前事件序列，本次没有建议。",
            "loading":"模型正在加载，本次没有建议；下一次决策再尝试。",
            "busy":"Archer 服务繁忙，本次没有建议。",
            "rate_limited":"请求过于频繁，本次没有建议。",
            "cold_start_limited":"模型加载次数受限，请稍后再试。",
            "engine_timeout":"Archer 引擎超时，本次没有建议。",
        }
        try:
            delay=float(headers.get("Retry-After","0"))
            if not math.isfinite(delay):delay=0
        except (TypeError,ValueError):delay=0
        raise ArcherError(code,messages.get(code,"Archer 接口返回 HTTP "+str(status)),status=status,retry_after=delay)

    def models(self,players=4):
        items=self.request("/v1/models").get("models")
        if not isinstance(items,list):
            raise ArcherError("invalid_response","模型列表格式不正确。")
        return [m for m in items if isinstance(m,dict) and m.get("players") in (3,4)
                and (players is None or m["players"]==players) and isinstance(m.get("name"),str)]

    def balance(self):
        value=self.request("/v1/balance").get("balance")
        if type(value) is not int or value<0:
            raise ArcherError("invalid_response","余额格式不正确。")
        return value

    def decide(self,model,seat,events):
        if not model:
            raise ArcherError("configuration","请先查询并选择对应人数的模型。")
        if not events or events[0].get("type")!="start_kyoku" or len(events)>400:
            raise ArcherError("invalid_events","缺少完整小局历史，或事件超过 400 条。")
        return self.request("/v1/decide",{"model":model,"seat":seat,"events":events})
