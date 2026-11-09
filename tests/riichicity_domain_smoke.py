"""Optional anonymous CONNECT/TLS/WS probe; never authenticates or sends game messages."""
import argparse
import base64
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import time


def headers(stream):
    value=bytearray()
    while not value.endswith(b'\r\n\r\n'):
        data=stream.recv(1)
        if not data or len(value)>16384:raise ValueError('Invalid HTTP headers')
        value.extend(data)
    return bytes(value)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unlock',type=Path,required=True)
    args=parser.parse_args()
    child=None
    try:
        try:
            with socket.create_connection(('127.0.0.1',41110),timeout=0.5):pass
        except OSError:pass
        else:raise ValueError('Close the running capture/unlock first; this probe never adopts another process.')
        child=subprocess.Popen([str(args.unlock)],cwd=args.unlock.parent,stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        deadline=time.monotonic()+30
        while True:
            if child.poll() is not None:raise ValueError('External adapter exited before listening')
            try:
                with socket.create_connection(('127.0.0.1',41110),timeout=0.5):pass
                break
            except OSError:
                if time.monotonic()>deadline:raise ValueError('External adapter startup timed out')
                time.sleep(0.2)
        host='aga-alb.mahjong-jp.net'
        public_ca=Path.home()/'.mitmproxy/mitmproxy-ca-cert.pem'
        context=ssl.create_default_context(cafile=str(public_ca))
        with socket.create_connection(('127.0.0.1',41110),timeout=15) as connection:
            connection.sendall(f'CONNECT {host}:443 HTTP/1.1\r\nHost: {host}:443\r\n\r\n'.encode('ascii'))
            connect_status=headers(connection).split(b'\r\n',1)[0].split()[1].decode()
            if connect_status!='200':raise ValueError(f'CONNECT rejected: {connect_status}')
            with context.wrap_socket(connection,server_hostname=host) as secure:
                key=base64.b64encode(os.urandom(16)).decode('ascii')
                request=(f'GET /connector/ws HTTP/1.1\r\nHost: {host}\r\nConnection: Upgrade\r\n'
                    f'Upgrade: websocket\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: {key}\r\n\r\n')
                secure.sendall(request.encode('ascii'))
                response=headers(secure).split(b'\r\n',1)[0].decode('ascii',errors='replace')
                status=response.split()[1]
                if status!='101':raise ValueError(f'WebSocket handshake rejected: {status}')
        print(json.dumps({'original_domain':host,'strict_tls':True,'websocket_status':101,'authenticated':False,'game_messages_sent':0}))
    finally:
        if child and child.poll() is None:
            child.terminate()
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)
if __name__=='__main__':main()
