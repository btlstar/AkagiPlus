"""Local configuration and diagnostics for the Archer plugin."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import threading
import tomllib

from archer_client import ArcherClient, ArcherError, NoRedirect

ROOT = Path(__file__).resolve().parent
SAMPLE_EVENTS = [
    {"type": "start_kyoku", "bakaze": "E", "dora_marker": "2s", "kyoku": 1,
     "honba": 0, "kyotaku": 0, "oya": 0, "scores": [25000] * 4,
     "tehais": [["1m", "2m", "3m", "5m", "5mr", "7p", "8p", "9p", "2s", "3s", "E", "E", "P"]]
               + [["?"] * 13 for _ in range(3)]},
    {"type": "tsumo", "actor": 0, "pai": "4s"},
]


def read_settings():
    with (ROOT / "manifest.toml").open("rb") as stream:
        defaults = {key: spec["default"] for key, spec in tomllib.load(stream)["settings"].items()}
    if (ROOT / "settings.toml").exists():
        with (ROOT / "settings.toml").open("rb") as stream:
            defaults.update(tomllib.load(stream))
    return defaults


def save_settings(settings):
    # Only declared fields; serialize strings with JSON quoting (valid TOML basic strings).
    with (ROOT / "manifest.toml").open("rb") as stream:
        names = tomllib.load(stream)["settings"]
    lines = []
    for name in names:
        value = settings.get(name, names[name]["default"])
        if isinstance(value, bool):
            encoded = "true" if value else "false"
        elif isinstance(value, (int, float)):
            encoded = str(value)
        else:
            encoded = json.dumps(str(value), ensure_ascii=False)
        lines.append(name + " = " + encoded)
    target = ROOT / "settings.toml"
    temporary = ROOT / ".settings.tmp"
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(temporary, target)


def check(settings):
    client = ArcherClient(settings)
    models = client.models(None)
    balance = client.balance()
    names = [model["name"] for model in models if model["players"] == 4]
    names_3p = [model["name"] for model in models if model["players"] == 3]
    configured = str(settings.get("model", "")).strip()
    return {"ok": True, "balance": balance, "models": [m for m in models if m["players"] == 4],
            "models_3p": [m for m in models if m["players"] == 3],
            "selected_3p_valid": settings.get("model_3p", "") in names_3p,
            "selected_model_valid": bool(configured) and configured in names,
            "decision_tested": False}


def readiness(settings, modes=(3, 4)):
    """Free account/model checks; never calls /v1/decide or writes settings."""
    import time
    started = time.perf_counter()
    result = {"state": "error", "message": "", "models": [], "elapsed_ms": 0}
    client = None
    try:
        for players in sorted(set(modes), reverse=True):
            name = str(settings.get("model_3p" if players == 3 else "model", "")).strip()
            if not name:
                result["message"] = ("三麻" if players == 3 else "四麻") + "模型尚未配置"
                return result
            result["models"].append({"players": players, "name": name[:80], "available": False})
        client = ArcherClient(settings)
        models = client.models(None)
        balance = client.balance()
        for item in result["models"]:
            item["available"] = any(m["players"] == item["players"] and m["name"] == item["name"] for m in models)
        unavailable = [item for item in result["models"] if not item["available"]]
        if unavailable:
            result["message"] = "所选模型不可用，请重新选择"
        elif balance == 0:
            result["message"] = "账户余额不足"
        else:
            result.update(state="ready", message="连接正常")
    except ArcherError as exc:
        messages = {"configuration": "请先配置 Archer API 密钥和连接地址",
                    "invalid_key": "API 密钥无效，请重新配置",
                    "account_disabled": "Archer 账号暂时不可用",
                    "network": "无法连接 Archer，请检查网络",
                    "rate_limited": "检查过于频繁，请稍后重试"}
        result["message"] = messages.get(exc.code, "Archer 接口暂时不可用，请稍后重试")
    except Exception:
        result["message"] = "连接检查失败，请检查本机配置"
    finally:
        if client is not None:
            client.close()
        result["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
    return result


def sample_events(players=4):
    from copy import deepcopy
    events = deepcopy(SAMPLE_EVENTS)
    if players == 3:
        events[0]["scores"] = [35000] * 3
        events[0]["tehais"] = events[0]["tehais"][:3]
        events[0]["tehais"][0] = ["1p","2p","3p","5p","5pr","7p","8p","9p","2s","3s","E","E","P"]
    return events


def smoke(settings, players=4):
    client = ArcherClient(settings)
    model = str(settings.get("model_3p" if players == 3 else "model", "")).strip()
    available = [item["name"] for item in client.models(players)]
    if not model or model not in available:
        raise ArcherError("configuration", "请先查询并选择对应人数的有效模型，再保存。")
    if client.balance() <= 0:
        raise ArcherError("insufficient_balance", "Token 余额为 0，未发起付费决策。")
    events = sample_events(players)
    response = client.decide(model, 0, events)
    # Exercise the exact adapter and HUD conversion with the real response.
    from bot import ArcherBot
    class CapturedResponse:
        def decide(self, model, seat, events):
            return response
    adapter = ArcherBot(settings, client=CapturedResponse(), notifier=lambda *args: None)
    result = adapter.react([{"type": "start_game", "id": 0, "num_players": players}] + events)
    meta = result.get("meta", {})
    if result.get("type") == "none" or not meta.get("archer", {}).get("last_usage"):
        raise ArcherError("invalid_response", "接口已返回，但未通过动作与用量验证；请检查本机显示和余额。")
    return {"ok": True, "decision_tested": True, "action": {k: v for k, v in result.items() if k != "meta"},
            "usage": meta["archer"]["last_usage"], "show": meta["show"]}


def write_check(result):
    folder = ROOT / ".akagi"
    folder.mkdir(exist_ok=True)
    (folder / "connection_check.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def page_identity():
    import hashlib
    return hashlib.sha256(str(ROOT.resolve()).casefold().encode("utf-8")).hexdigest()[:20]


def page_is_ready(url):
    import urllib.request
    import urllib.parse
    try:
        parsed = urllib.parse.urlsplit(url)
        if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or not parsed.path.startswith("/") or not parsed.path.endswith("/")):
            return False
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(url + "health", timeout=0.5) as response:
            data = json.loads(response.read(4096))
        return data == {"service": "archer-api-config", "instance": page_identity()}
    except (OSError, ValueError):
        return False


def existing_page():
    try:
        url = (ROOT / ".akagi/config_url.txt").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return url if page_is_ready(url) else None


def open_page(url):
    # A BROWSER override can invoke a blocking third-party app launcher.
    # Use the Windows URL association directly for this local settings page.
    if os.name == "nt":
        os.startfile(url)
    else:
        import webbrowser
        webbrowser.open(url)


def run_gui():
    import http.server
    import secrets
    import socket
    import threading
    previous = existing_page()
    if previous:
        open_page(previous)
        return

    page = """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Archer API · 三麻 / 四麻配置</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#111419;color:#ebedf2;font:15px system-ui,"Microsoft YaHei",sans-serif}
main{max-width:850px;margin:36px auto;padding:28px;background:#1b2028;border:1px solid #333d4b;border-radius:18px}
h1{font-size:30px;margin:0 0 8px}p{color:#adb7c6;line-height:1.7}label{display:block;margin-top:18px;font-weight:600}
input,select{width:100%;padding:12px;margin-top:8px;background:#11161d;border:1px solid #435063;border-radius:8px;color:#e9edf4;font-size:15px}
input:focus{outline:2px solid #80b6ff}button{border:0;border-radius:8px;padding:12px 17px;cursor:pointer;font:inherit;background:#85baff;color:#102137;margin:18px 10px 0 0}
button.secondary{background:#333f51;color:#ecf2fc}button:disabled{opacity:.5;cursor:wait}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.note{font-size:13px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#10151c;padding:18px;border-radius:10px;min-height:150px;font:14px/1.7 system-ui}
@media(max-width:700px){main{margin:10px;padding:20px}.grid{grid-template-columns:1fr}}
</style><main>
<h1>Archer API</h1><p>三麻、四麻自动切换 · 独立引擎配置</p>
<p class="note">填写 Archer 专用 API 密钥。配置保存在本机，不会提交给 MJOT。修改后从下一个新对局生效。</p>
<label>接口根地址<input id="api_url" autocomplete="off"></label>
<label>Archer API 密钥<input id="api_key" type="password" autocomplete="off"></label>
<label>四麻模型<input id="model" list="models" placeholder="先查询模型，再选择完整模型名"><datalist id="models"></datalist></label>
<label>三麻模型<input id="model_3p" list="models_3p" placeholder="三麻对局将自动使用此模型"><datalist id="models_3p"></datalist></label>
<label>评分显示<select id="score_mode"><option value="weights">候选权重（合计 100%）</option><option value="relative">首选与落后差值</option><option value="raw">原始 q</option></select></label>
<div class="grid"><label>请求超时（毫秒）<input id="timeout_ms" type="number" min="500" max="4000"></label>
<label>候选数量<input id="top_n" type="number" min="1" max="10"></label></div>
<label>HTTP/HTTPS 代理（留空直连）<input id="proxy_url" autocomplete="off" placeholder="http://127.0.0.1:7890"></label>
<div><button onclick="act('check')">查询模型与余额</button><button onclick="act('save')">保存配置</button>
<button class="secondary" onclick="act('smoke')">测试四麻（扣 Token）</button>
<button class="secondary" onclick="act('smoke3')">测试三麻（扣 Token）</button>
<button class="secondary" onclick="closeConfig()">关闭配置服务</button></div>
<p class="note">查询模型与余额不消耗 Token。测试一次决策会按官方规则扣费。请先关闭自动操作，再启用对应人数的插件开关查看建议。</p>
<pre id="result">正在读取本机配置……</pre></main>
<script>
const fields=['api_url','api_key','model','model_3p','score_mode','timeout_ms','proxy_url','top_n'];
const output=document.getElementById('result');
function values(){let v={};fields.forEach(k=>v[k]=document.getElementById(k).value.trim());v.timeout_ms=Number(v.timeout_ms);v.top_n=Number(v.top_n);return v}
async function act(action){
 document.querySelectorAll('button').forEach(b=>b.disabled=true);
 output.textContent=(action==='smoke'||action==='smoke3')?'正在进行一次付费决策测试……':'正在处理……';
 try{
  const r=await fetch(action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(values())});
  const data=await r.json();if(!data.ok)throw Error(data.message||'请求失败');
  if(action==='check'){
   const names3=data.models_3p.map(m=>m.name);document.getElementById('models_3p').replaceChildren(...names3.map(n=>{let o=document.createElement('option');o.value=n;return o}));
   if(!names3.includes(document.getElementById('model_3p').value)&&names3.length)document.getElementById('model_3p').value=names3[0];
   const names=data.models.map(m=>m.name);document.getElementById('models').replaceChildren(...names.map(n=>{let o=document.createElement('option');o.value=n;return o}));
   if(!names.includes(document.getElementById('model').value)&&names.length)document.getElementById('model').value=names[0];
   output.textContent='连接成功，密钥可用。\\n余额：'+data.balance.toLocaleString()+' Token\\n\\n四麻模型：\\n'+names.join('\\n')+'\\n\\n三麻模型：\\n'+names3.join('\\n')+'\\n\\n请分别选择模型并保存。'+(data.balance===0?'余额为零，尚不能验证真实决策。':'可以进行一次决策测试。');
  }else if(action==='save'){output.textContent='配置已保存。\\n\\n回到 AkagiPlus 的“机器人”页点击刷新，找到“Archer API · 三麻 / 四麻”，同时启用四麻和三麻。\\n请保持自动操作关闭，并从新对局开始。\\n顶部 MJOT 设置无需填写 Archer 密钥。'}
  else{output.textContent='真实决策测试通过。\\n\\n'+JSON.stringify(data,null,2)}
 }catch(e){output.textContent=e.message}
 finally{document.querySelectorAll('button').forEach(b=>b.disabled=false)}
}
async function closeConfig(){await fetch('close',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});output.textContent='配置服务已关闭，可以关闭此标签页。';document.querySelectorAll('button').forEach(b=>b.disabled=true)}
fetch('settings').then(r=>r.json()).then(v=>{fields.forEach(k=>document.getElementById(k).value=v[k]??'');output.textContent='先查询模型与余额，再选择模型并保存。\\n此页面仅由本机临时配置服务提供。'}).catch(()=>output.textContent='无法读取本机配置。');
</script></html>"""
    token = secrets.token_urlsafe(24)
    prefix = "/" + token + "/"

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, value, status=200, content_type="application/json; charset=utf-8"):
            data = value.encode("utf-8") if isinstance(value, str) else json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def allowed(self):
            expected = "127.0.0.1:" + str(self.server.server_port)
            origin = self.headers.get("Origin")
            return self.headers.get("Host") == expected and (not origin or origin == "http://" + expected)

        def do_GET(self):
            if not self.allowed():
                self.respond({"ok": False}, 403)
            elif self.path == prefix:
                self.respond(page, content_type="text/html; charset=utf-8")
            elif self.path == prefix + "health":
                self.respond({"service": "archer-api-config", "instance": page_identity()})
            elif self.path == prefix + "settings":
                self.respond(read_settings())
            else:
                self.respond({"ok": False}, 404)

        def do_POST(self):
            if not self.allowed() or not self.path.startswith(prefix):
                self.respond({"ok": False}, 403)
                return
            action = self.path[len(prefix):]
            if action not in ("save", "check", "smoke", "smoke3", "close"):
                self.respond({"ok": False}, 404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 16384:
                    raise ArcherError("configuration", "配置内容大小不正确。")
                values = json.loads(self.rfile.read(length))
                if action == "close":
                    self.respond({"ok": True})
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                    return
                if not isinstance(values, dict):
                    raise ArcherError("configuration", "配置格式不正确。")
                for name, low, high in (("timeout_ms", 500, 4000), ("top_n", 1, 10)):
                    if type(values.get(name)) is not int or not low <= values[name] <= high:
                        raise ArcherError("configuration", "超时范围 500～4000 毫秒；候选数量范围 1～10。")
                ArcherClient(values)
                if action == "save":
                    if not str(values.get("model", "")).strip():
                        raise ArcherError("configuration", "请先查询并选择四麻模型。")
                    save_settings(values)
                    result = {"ok": True, "saved": True}
                elif action == "check":
                    result = check(values)
                    write_check(result)
                else:
                    result = smoke(values, 3 if action == "smoke3" else 4)
                    write_check(result)
                self.respond(result)
            except ArcherError as exc:
                self.respond({"ok": False, "message": str(exc), "code": exc.code})
            except Exception:
                self.respond({"ok": False, "message": "本机检查失败，请检查配置、网络或文件写入权限。"})

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    # Start handling requests BEFORE opening a browser or invoking any shell.
    # This also keeps the service responsive if a browser launch takes time.
    url = "http://127.0.0.1:" + str(server.server_port) + prefix
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    timer = threading.Timer(1800, server.shutdown)
    timer.daemon = True
    timer.start()
    record = ROOT / ".akagi/config_url.txt"
    try:
        if not page_is_ready(url):
            raise RuntimeError("Local configuration service did not become ready")
        record.parent.mkdir(exist_ok=True)
        record.write_text(url, encoding="utf-8")
        open_page(url)
        worker.join()
    finally:
        timer.cancel()
        server.shutdown()
        server.server_close()
        # Never leave a dead URL to be reopened by another launch.
        try:
            if record.read_text(encoding="utf-8").strip() == url:
                record.unlink()
        except OSError:
            pass


def main():
    parser = argparse.ArgumentParser(description="Archer local configuration")
    parser.add_argument("--players", type=int, choices=(3,4), default=4)
    parser.add_argument("--readiness", action="store_true", help="Free pre-game readiness status")
    parser.add_argument("--modes", nargs="+", type=int, choices=(3, 4), default=[3, 4])
    parser.add_argument("--check", action="store_true", help="Read-only model and balance check")
    parser.add_argument("--smoke", action="store_true", help="One paid decision after checking balance")
    args = parser.parse_args()
    if args.readiness:
        try:
            result = readiness(read_settings(), args.modes)
        except Exception:
            result = {"state": "error", "message": "无法读取 Archer 配置", "models": [], "elapsed_ms": 0}
        print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
        return
    if not args.check and not args.smoke:
        try:
            run_gui()
        except Exception as exc:
            message = "Archer 配置服务启动失败（" + type(exc).__name__ + "）。请检查插件文件和文件夹写入权限，然后重新运行 configure.cmd。"
            folder = ROOT / ".akagi"
            try:
                folder.mkdir(exist_ok=True)
                (folder / "config_start_error.txt").write_text(message, encoding="utf-8")
            except OSError:
                pass
            if os.name == "nt":
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, message, "Archer 配置", 0x10)
            raise SystemExit(1)
        return
    try:
        result = smoke(read_settings(), args.players) if args.smoke else check(read_settings())
        write_check(result)
        print(json.dumps(result, ensure_ascii=True, indent=2))
    except ArcherError as exc:
        result = {"ok": False, "code": exc.code, "message": str(exc), "decision_tested": False}
        write_check(result)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
