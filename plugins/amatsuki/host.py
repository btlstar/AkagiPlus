"""Capture visible Amatsuki game messages and optionally load local cosmetics."""
import argparse
import json
import os
from pathlib import Path
import queue
import signal
import sys
import threading
import time
import frida
from protocol import Bridge


OUTPUT_LOCK = threading.Lock()


def output(value):
    with OUTPUT_LOCK:
        print(json.dumps(value, ensure_ascii=False), flush=True)


def candidates(device, game):
    expected = os.path.normcase(str(game.resolve()))
    return [p for p in device.enumerate_processes(scope='full')
            if p.name.lower() == 'mahjongp.exe'
            and os.path.normcase(p.parameters.get('path', '')) == expected]


def create_cosmetics(session, game, report):
    plugin_root = str(Path(__file__).resolve().parents[1])
    if plugin_root not in sys.path:
        sys.path.insert(0, plugin_root)
    from amatsukistyle.runtime import Cosmetics
    return Cosmetics(session, game.parent, report)


def follow(device, game, source, running, cosmetics=False, emit=output):
    announced = None
    attempts = 0
    def status(message):
        nonlocal announced
        if announced != message:
            emit({'kind': 'status', 'message': message})
            announced = message
    while running():
        processes = candidates(device, game)
        if len(processes) != 1:
            status('等待启动天月并登录。' if not processes else '检测到多个天月进程，等待客户端启动完成。')
            time.sleep(1)
            continue
        events = queue.Queue(maxsize=2048)
        detached = threading.Event()
        reason = []
        def receive(message, binary):
            value = message.get('payload') if message.get('type') == 'send' else {'kind': 'error', 'message': message.get('description', '天月读取脚本异常')}
            try:
                events.put_nowait(value)
            except queue.Full:
                reason.append('消息队列已满')
                detached.set()
        def lost(why, crash=None):
            reason.append(str(why))
            detached.set()
        session = script = cosmetic = None
        bridge = Bridge()
        initialized = False
        try:
            session = device.attach(processes[0].pid)
            session.on('detached', lost)
            script = session.create_script(source)
            script.on('message', receive)
            script.load()
            ready = script.exports_sync.start()
            initialized = True
            attempts = 0
            announced = None
            emit(ready)
            next_cosmetic_check = 0
            if cosmetics:
                try:
                    cosmetic = create_cosmetics(session, game, status)
                except Exception as error:
                    status('AmatsukiStyle 加载失败：' + str(error) + '；对局捕获继续运行。')
            while running() and not detached.is_set():
                if cosmetic and time.monotonic() >= next_cosmetic_check:
                    try:
                        if cosmetic.poll():
                            status('AmatsukiStyle 已启用，本地装扮选择会自动保存。')
                            next_cosmetic_check = float('inf')
                        else:
                            status('AmatsukiStyle 等待登录天月，登录完成后会自动加载。')
                            next_cosmetic_check = time.monotonic() + 1
                    except Exception as error:
                        cosmetic.close()
                        cosmetic = None
                        status('AmatsukiStyle 加载失败：' + str(error) + '；对局捕获继续运行。')
                try:
                    value = events.get(timeout=0.2)
                except queue.Empty:
                    continue
                if value.get('kind') == 'packet':
                    for event in bridge.accept(value):
                        emit(event)
                else:
                    emit(value)
        except (frida.InvalidOperationError, frida.ProcessNotFoundError, frida.RPCException) as error:
            if initialized and not detached.is_set():
                raise
            attempts += 1
            if attempts >= 30:
                raise ValueError('天月客户端未初始化或版本未适配，请重新登录后重启捕获。') from error
            status('等待天月客户端初始化。')
        finally:
            if cosmetic:
                cosmetic.close()
            if script:
                try:
                    script.exports_sync.stop()
                except Exception:
                    pass
            if session:
                try:
                    session.detach()
                except frida.InvalidOperationError:
                    pass
        if running():
            detail = reason[0] if reason else '初始化未完成'
            for event in bridge.reset('天月连接已断开（' + detail + '），正在自动重新连接；请从新对局开局同步。'):
                emit(event)
            time.sleep(1)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, required=True)
    parser.add_argument('--cosmetics', action='store_true')
    args = parser.parse_args()
    if not args.game.is_file() or args.game.name.lower() != 'mahjongp.exe':
        raise ValueError('请选择天月安装目录中的 mahjongP.exe。')
    stopped = threading.Event()
    def stop(*unused):
        stopped.set()
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    root = Path(__file__).resolve().parent
    source = '\n'.join((root / name).read_text('utf8') for name in ['il2cpp.js', 'capture.js'])
    follow(frida.get_local_device(), args.game, source, lambda: not stopped.is_set(), args.cosmetics)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        output({'kind': 'error', 'message': str(error)})
        sys.exit(1)
