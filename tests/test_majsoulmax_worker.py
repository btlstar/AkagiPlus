"""Offline protocol regressions; no account, browser or network is used."""
import base64
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'plugins/majsoulmax'))
IMPORT_HOME = tempfile.TemporaryDirectory()
os.environ['AKAGIPLUS_MAJSOULMAX_DATA_DIR'] = IMPORT_HOME.name
from worker import Worker, verify_snapshot
from majsoulmax.proto import basic_pb2, liqi_pb2 as pb
from majsoulmax.plugin import mod


def frame(kind, method, payload, msg_id=1):
    envelope = basic_pb2.BaseMessage(method_name='' if kind == 3 else method,
                                   data=payload.SerializeToString())
    return bytes([kind]) + (b'' if kind == 1 else struct.pack('<H', msg_id)) + envelope.SerializeToString()


def body(content, cls):
    envelope = basic_pb2.BaseMessage.FromString(content[1:] if content[0] == 1 else content[3:])
    return cls.FromString(envelope.data)


class MajsoulMaxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = patch.object(mod, 'CONFIG', Path(self.tmp.name))
        patcher.start(); self.addCleanup(patcher.stop)
        self.worker = Worker()
        self.next_id = 1

    def send(self, content, up, flow='lobby'):
        result = self.worker.handle({'op': 'frame', 'flow': flow, 'from_client': up,
                                    'data': base64.b64encode(content).decode('ascii')})
        result['bytes'] = base64.b64decode(result['data'])
        return result

    def exchange(self, method, response, request=None, flow='lobby'):
        msg_id = self.next_id; self.next_id += 1
        if request is None:
            request = getattr(pb, pb.RPC_METHODS[method]['req'].rsplit('.', 1)[-1])()
        self.send(frame(2, method, request, msg_id), True, flow)
        return self.send(frame(3, method, response, msg_id), False, flow)

    def login(self):
        response = pb.ResLogin(account_id=123456)
        response.account.account_id = 123456
        response.account.nickname = 'fixture'
        response.account.avatar_id = 400101
        return self.exchange('.lq.Lobby.login', response)

    def select_character(self):
        self.worker.plugin.settings['config']['character'] = 200002
        self.worker.plugin.settings['config']['characters'][200002] = 400201

    def player(self, account=123456):
        player = pb.PlayerGameView(account_id=account, avatar_id=400101, nickname='fixture')
        player.character.charid = 200001
        player.character.skin = 400101
        player.character.exp = 123
        return player

    def test_snapshot_integrity(self):
        self.assertGreater(verify_snapshot()['counts']['skin'], 100)

    def test_fresh_choices_are_private(self):
        self.assertTrue((Path(self.tmp.name) / 'settings.mod.yaml').exists())
        self.assertFalse(self.worker.plugin.settings['config']['emoji'])
        self.assertFalse(self.worker.plugin.settings['config']['show_server'])

    def test_login_and_unlock(self):
        self.login()
        response = pb.ResFetchInfo()
        response.character_info.main_character_id = 200001
        response.character_info.characters.add(charid=200001, skin=400101, exp=77)
        result = body(self.exchange('.lq.Lobby.fetchInfo', response)['bytes'], pb.ResFetchInfo)
        self.assertEqual(list(result.character_info.skins), self.worker.plugin.max_data['skin'])
        self.assertEqual(len(result.character_info.characters), self.worker.manifest['counts']['character'])

    def test_skin_change_rewrites_heartbeat_and_notifies_same_client(self):
        self.login()
        self.send(frame(2, '.lq.Lobby.loginBeat', pb.ReqLoginBeat(contract='fixture'), 20), True)
        result = self.send(frame(2, '.lq.Lobby.changeCharacterSkin',
            pb.ReqChangeCharacterSkin(character_id=200002, skin=400201), 21), True)
        env = basic_pb2.BaseMessage.FromString(result['bytes'][3:])
        self.assertEqual(env.method_name, '.lq.Lobby.loginBeat')
        self.assertEqual(body(result['bytes'], pb.ReqLoginBeat).contract, 'fixture')
        self.assertEqual(len(result['inject_client']), 1)
        notice = body(base64.b64decode(result['inject_client'][0]), pb.NotifyAccountUpdate)
        self.assertEqual(notice.update.character.characters[0].skin, 400201)
        self.send(frame(3, '', pb.ResCommon(), 21), False)
        self.assertNotIn(21, self.worker.flows['lobby'].res_type)




    def test_starred_characters_survive_restart_and_both_fetch_paths(self):
        self.login()
        chosen = [200002, 200001]
        self.send(frame(2, '.lq.Lobby.updateCharacterSort', pb.ReqUpdateCharacterSort(sort=chosen), 76), True)
        self.worker = Worker()
        self.assertEqual(self.worker.plugin.settings['config']['star_chars'], chosen)
        info = body(self.exchange('.lq.Lobby.fetchCharacterInfo', pb.ResCharacterInfo())['bytes'], pb.ResCharacterInfo)
        self.assertEqual(list(info.character_sort), chosen)
        combined = body(self.exchange('.lq.Lobby.fetchInfo', pb.ResFetchInfo())['bytes'], pb.ResFetchInfo)
        self.assertEqual(list(combined.character_info.character_sort), chosen)

    def test_friend_room_character_and_voice_identity(self):
        self.login(); self.select_character()
        for method, cls in [('createRoom',pb.ResCreateRoom),('joinRoom',pb.ResJoinRoom),('fetchRoom',pb.ResSelfRoom)]:
            with self.subTest(method=method):
                res = cls(); res.room.room_id = 321
                res.room.persons.add().CopyFrom(self.player())
                res.room.persons.add().CopyFrom(self.player(456789))
                peer = res.room.persons[1].SerializeToString()
                result = body(self.exchange('.lq.Lobby.'+method,res)['bytes'], cls)
                self.assertEqual(result.room.persons[0].character.charid,200002)
                self.assertEqual(result.room.persons[0].character.skin,400201)
                self.assertEqual(result.room.persons[0].avatar_id,400201)
                self.assertEqual(result.room.persons[1].SerializeToString(),peer)

    def test_room_notifications_preserve_peers_and_unknown_fields(self):
        self.login(); self.select_character()
        res = pb.NotifyRoomPlayerUpdate(owner_id=123456,seq=7,robot_count=1)
        res.player_list.add().CopyFrom(self.player())
        res.player_list.add().CopyFrom(self.player(456789))
        # Future server field #1000, varint 7.
        res = pb.NotifyRoomPlayerUpdate.FromString(res.SerializeToString()+b'\xc0\x3e\x07')
        peer = res.player_list[1].SerializeToString()
        result = body(self.send(frame(1,'.lq.NotifyRoomPlayerUpdate',res),False)['bytes'],pb.NotifyRoomPlayerUpdate)
        self.assertEqual(result.player_list[0].character.charid,200002)
        self.assertEqual(result.player_list[1].SerializeToString(),peer)
        self.assertIn(b'\xc0\x3e\x07',result.SerializeToString())
        self.assertEqual(result.seq,7)

    def test_rpc_ids_are_isolated_between_flows(self):
        self.send(frame(2,'.lq.Lobby.fetchCharacterInfo',pb.ReqCommon(),5),True,'a')
        self.send(frame(2,'.lq.Lobby.fetchServerTime',pb.ReqCommon(),5),True,'b')
        self.assertNotEqual(self.worker.flows['a'].res_type[5][0],self.worker.flows['b'].res_type[5][0])
        raw = frame(3,'',pb.ResServerTime(server_time=123),5)
        self.assertEqual(self.send(raw,False,'b')['bytes'],raw)
        self.assertIn(5,self.worker.flows['a'].res_type)
        self.assertNotIn(5,self.worker.flows['b'].res_type)

    def test_close_releases_pending_requests(self):
        self.send(frame(2,'.lq.Lobby.fetchServerTime',pb.ReqCommon()),True)
        self.worker.handle({'op':'close','flow':'lobby'})
        self.assertNotIn('lobby', self.worker.flows)

    def test_unknown_response_and_non_liqi_pass_through(self):
        for raw in [b'',b'hello',frame(3,'',pb.ResCommon(),42)]:
            result=self.send(raw,False)
            self.assertEqual(result['bytes'],raw)
            self.assertFalse(result['drop']);self.assertEqual(result['inject_client'],[])

    def test_gameplay_notify_is_unchanged(self):
        raw=frame(1,'.lq.ActionPrototype',pb.ActionPrototype(step=1,name='ActionDealTile',data=b'fixture'))
        self.assertEqual(self.send(raw,False,'game')['bytes'],raw)

    def test_choices_survive_worker_restart(self):
        self.login(); self.select_character(); self.worker.plugin.SaveSettings()
        restarted=Worker()
        self.assertEqual(restarted.plugin.settings['config']['character'],200002)
        self.assertEqual(restarted.plugin.settings['config']['characters'][200002],400201)

    def test_jsonl_subprocess_protocol_and_clean_shutdown(self):
        env=dict(os.environ, AKAGIPLUS_MAJSOULMAX_DATA_DIR=self.tmp.name)
        proc=subprocess.Popen([sys.executable,'-u',str(ROOT/'plugins/majsoulmax/worker.py')],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
        try:
            ready=json.loads(proc.stdout.readline())
            self.assertEqual(ready['protocol'],1);self.assertTrue(ready['ready'])
            proc.stdin.write(b'{"op":"frame","flow":"a","from_client":true,"data":"aGVsbG8="}\n');proc.stdin.flush()
            response=json.loads(proc.stdout.readline())
            self.assertEqual(response['data'],'aGVsbG8=');self.assertFalse(response['drop'])
            proc.stdin.close();proc.wait(timeout=5)
            self.assertEqual(proc.returncode,0)
        finally:
            if proc.poll() is None: proc.kill();proc.wait(timeout=5)
            proc.stdout.close();proc.stderr.close()

if __name__ == '__main__':
    unittest.main()
