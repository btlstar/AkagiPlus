import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugins/amatsuki'))
import host


class LifecycleTests(unittest.TestCase):
    def test_process_replacement_reconnects_and_resets_analysis(self):
        sessions = []
        stopped = False
        class Session:
            def __init__(self, pid):
                self.pid = pid
                self.receive = None
                self.exports_sync = self
                sessions.append(self)
            def on(self, name, callback):
                if name == 'detached': self.lost = callback
                else: self.receive = callback
            def create_script(self, source): return self
            def load(self): pass
            def start(self):
                self.receive({'type': 'send', 'payload': {'kind': 'packet', 'pid': self.pid}}, None)
                return {'kind': 'status', 'message': 'connected'}
            def stop(self): pass
            def detach(self): self.lost('application-requested')
        class Bridge:
            def accept(self, value):
                nonlocal stopped
                if value['pid'] == 10: sessions[-1].lost('process-terminated')
                else: stopped = True
                return [{'kind': 'event', 'pid': value['pid']}]
            def reset(self, message): return [{'kind': 'reset', 'message': message}]
        device = SimpleNamespace(attach=Session)
        def candidates(device, game):
            return [SimpleNamespace(pid=10 if not sessions else 20)]
        out = []
        with patch.object(host, 'candidates', candidates), patch.object(host, 'Bridge', Bridge), patch.object(host.time, 'sleep'):
            host.follow(device, Path('mahjongP.exe'), '', lambda: not stopped, emit=out.append)
        self.assertEqual([s.pid for s in sessions], [10, 20])
        self.assertEqual([v['pid'] for v in out if v['kind'] == 'event'], [10, 20])
        self.assertEqual(sum(v['kind'] == 'reset' for v in out), 1)
        self.assertIn('process-terminated', next(v['message'] for v in out if v['kind'] == 'reset'))

    def test_multiple_startup_processes_wait_instead_of_failing(self):
        running = True
        def pause(seconds):
            nonlocal running
            running = False
        out = []
        with patch.object(host, 'candidates', return_value=[1, 2]), patch.object(host.time, 'sleep', pause):
            host.follow(None, Path('mahjongP.exe'), '', lambda: running, emit=out.append)
        self.assertEqual(len(out), 1)
        self.assertIn('多个', out[0]['message'])

    def test_matches_configured_executable_not_just_name(self):
        game = Path('mahjongP.exe').resolve()
        device = SimpleNamespace(enumerate_processes=lambda **kw: [
            SimpleNamespace(pid=1, name='mahjongP.exe', parameters={'path': str(game)}),
            SimpleNamespace(pid=2, name='mahjongP.exe', parameters={'path': str(game.parent / 'other/mahjongP.exe')}),
        ])
        self.assertEqual([p.pid for p in host.candidates(device, game)], [1])


class CosmeticLifecycleTests(unittest.TestCase):
    def run_capture(self, factory):
        stopped = False
        class Session:
            def __init__(self): self.exports_sync = self
            def on(self, name, callback):
                if name == 'message': self.receive = callback
            def create_script(self, source): return self
            def load(self): pass
            def start(self):
                for n in range(3):
                    self.receive({'type': 'send', 'payload': {'kind': 'packet', 'n': n}}, None)
                return {'kind': 'status', 'message': 'connected'}
            def stop(self): pass
            def detach(self): pass
        class Bridge:
            def accept(self, value):
                nonlocal stopped
                if value['n'] == 2: stopped = True
                return [{'kind': 'event', 'n': value['n']}]
        session = Session()
        device = SimpleNamespace(attach=lambda pid: session)
        ticks = iter(range(0, 100, 2))
        out = []
        with patch.object(host, 'candidates', return_value=[SimpleNamespace(pid=10)]), patch.object(host, 'Bridge', Bridge), patch.object(host, 'create_cosmetics', factory), patch.object(host.time, 'monotonic', lambda: next(ticks)):
            host.follow(device, Path('mahjongP.exe'), '', lambda: not stopped, cosmetics=True, emit=out.append)
        self.assertEqual([v['n'] for v in out if v['kind'] == 'event'], [0, 1, 2])
        return out

    def test_login_wait_does_not_block_capture_and_loads_after_login(self):
        answers = iter([False, True])
        closed = []
        cosmetic = SimpleNamespace(poll=lambda: next(answers), close=lambda: closed.append(True))
        out = self.run_capture(lambda *args: cosmetic)
        self.assertTrue(any('等待登录' in v.get('message', '') for v in out))
        self.assertTrue(any('已启用' in v.get('message', '') for v in out))
        self.assertEqual(len(closed), 1)

    def test_cosmetic_constructor_failure_does_not_stop_ai(self):
        def broken(*args): raise ValueError('catalog unavailable')
        out = self.run_capture(broken)
        self.assertTrue(any('catalog unavailable' in v.get('message', '') and '捕获继续' in v['message'] for v in out))

    def test_cosmetic_configuration_failure_does_not_stop_ai(self):
        closed = []
        def broken(): raise RuntimeError('unsupported cosmetic API')
        cosmetic = SimpleNamespace(poll=broken, close=lambda: closed.append(True))
        out = self.run_capture(lambda *args: cosmetic)
        self.assertTrue(any('unsupported cosmetic API' in v.get('message', '') for v in out))
        self.assertEqual(len(closed), 1)


if __name__ == '__main__': unittest.main()
