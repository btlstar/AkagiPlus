"""Read-only Amatsuki native game-message capture."""
import argparse
import json
from pathlib import Path
import queue
import signal
import sys
import time
import frida


def output(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, required=True)
    args=parser.parse_args()
    if not args.game.is_file() or args.game.name.lower()!='mahjongp.exe':
        raise ValueError('请选择天月安装目录中的 mahjongP.exe。')
    events=queue.Queue(maxsize=2048)
    running=True
    def stop(*unused):
        nonlocal running
        running=False
    signal.signal(signal.SIGINT,stop)
    signal.signal(signal.SIGTERM,stop)
    def receive(message, binary):
        value=message.get('payload') if message.get('type')=='send' else {'kind':'error','message':message.get('description','天月读取脚本异常')}
        try:events.put_nowait(value)
        except queue.Full:stop()
    root=Path(__file__).resolve().parent
    source='\n'.join((root/name).read_text('utf8') for name in ['il2cpp.js','capture.js'])
    announced=False
    attempts=0
    while running:
        processes=[p for p in frida.get_local_device().enumerate_processes() if p.name.lower()=='mahjongp.exe']
        if not processes:
            if not announced:output({'kind':'status','message':'等待启动天月并登录。'});announced=True
            time.sleep(1);continue
        if len(processes)!=1:raise ValueError('请只保留一个天月客户端。')
        try:session=frida.attach(processes[0].pid)
        except frida.ProcessNotFoundError:continue
        try:
            script=session.create_script(source);script.on('message',receive);script.load()
            ready=script.exports_sync.start()
        except (frida.InvalidOperationError,frida.ProcessNotFoundError,frida.RPCException) as error:
            try:session.detach()
            except frida.InvalidOperationError:pass
            attempts+=1
            if attempts>=30:raise ValueError('天月客户端未初始化或版本未适配，请重新登录后重启捕获。') from error
            if not announced:output({'kind':'status','message':'等待天月客户端初始化。'});announced=True
            time.sleep(1);continue
        session.on('detached',lambda *unused:stop())
        try:
            output(ready)
            from protocol import Bridge
            bridge=Bridge()
            while running:
                try:value=events.get(timeout=0.2)
                except queue.Empty:continue
                if value.get('kind')=='packet':
                    for event in bridge.accept(value):output(event)
                else:output(value)
        finally:
            try:script.exports_sync.stop()
            except Exception:pass
            try:session.detach()
            except frida.InvalidOperationError:pass
        break


if __name__=='__main__':
    try:main()
    except Exception as error:
        output({'kind':'error','message':str(error)})
        sys.exit(1)
