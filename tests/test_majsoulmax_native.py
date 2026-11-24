"""Offline regression of the shipped Rust worker over AP's real JSONL pipe."""
import base64,json,os,struct,subprocess,sys,tempfile,time,unittest,threading,queue
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"plugins/majsoulmax"))
from majsoulmax.proto.protocol import build_protocol
from majsoulmax.proto import basic_pb2
pool,classes,methods=build_protocol((ROOT/"plugins/majsoulmax-rs/liqi_config/liqi.desc").read_bytes())
pb=SimpleNamespace(**classes)
NATIVE=ROOT/"plugins/majsoulmax-rs/majsoulmax-worker.exe"

def frame(kind,method,payload,ident=1):
    wrapper=basic_pb2.BaseMessage(method_name="" if kind==3 else method,data=payload.SerializeToString())
    return bytes([kind])+(b"" if kind==1 else struct.pack("<H",ident))+wrapper.SerializeToString()
def body(raw,cls):
    return cls.FromString(basic_pb2.BaseMessage.FromString(raw[1:] if raw[0]==1 else raw[3:]).data)

class NativeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home=Path(self.tmp.name)
        choices=self.home/"rust/settings.mod.json"
        choices.parent.mkdir()
        choices.write_text(json.dumps({"mainChar":20000128,"charSkin":{"20000128":40012803},"starCharacter":[20000128],"showServer":False,"antiNicknameCensorship":False}),encoding="utf8")
        self.next_id=1
        self.start()
        self.addCleanup(self.stop)

    def read_response(self):
        result=queue.Queue()
        def read():
            try:result.put(self.proc.stdout.readline())
            except Exception as error:result.put(error)
        threading.Thread(target=read,daemon=True).start()
        try:value=result.get(timeout=8)
        except queue.Empty:
            self.proc.kill()
            self.fail("JSONL response timed out")
        if isinstance(value,Exception):raise value
        return json.loads(value)

    def start(self):
        env=dict(os.environ,AKAGIPLUS_MAJSOULMAX_DATA_DIR=str(self.home))
        self.proc=subprocess.Popen([sys.executable,"-u",str(ROOT/"plugins/majsoulmax/worker.py")],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
        started=time.perf_counter()
        ready=self.read_response()
        self.assertTrue(ready["ready"],ready)
        self.assertIn("0.16.293",ready["snapshot"])
        self.start_ms=(time.perf_counter()-started)*1000

    def stop(self):
        if self.proc.poll() is None:
            self.proc.stdin.close()
            try:self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:self.proc.kill();self.proc.wait(timeout=5);self.fail("worker did not close on EOF")
        self.assertEqual(self.proc.returncode,0,self.proc.stderr.read().decode("utf8","replace"))
        self.proc.stdout.close();self.proc.stderr.close()

    def command(self,request):
        self.proc.stdin.write(json.dumps(request).encode()+b"\n");self.proc.stdin.flush()
        result=self.read_response()
        self.assertNotIn("error",result,result)
        return result

    def send(self,raw,up=False,flow="lobby"):
        result=self.command({"op":"frame","flow":flow,"from_client":up,"data":base64.b64encode(raw).decode()})
        result["bytes"]=base64.b64decode(result["data"])
        return result

    def exchange(self,method,response,flow="lobby"):
        ident=self.next_id;self.next_id+=1
        request=classes[methods[method]["req"].rsplit(".",1)[-1]]()
        self.send(frame(2,method,request,ident),True,flow)
        return self.send(frame(3,"",response,ident),False,flow)

    def login(self):
        reply=pb.ResLogin(account_id=123456)
        reply.account.account_id=123456
        reply.account.avatar_id=400101
        return self.exchange(".lq.Lobby.login",reply)

    def test_imported_choices_latest_collab_and_hidden_hands(self):
        self.login()
        response=pb.ResCharacterInfo()
        field=response.DESCRIPTOR.fields_by_name["hidden_hands_view"]
        if field.message_type:
            value=getattr(response,"hidden_hands_view")
            if field.label==field.LABEL_REPEATED:value=value.add()
            # A known empty nested message still tests field presence.
            value.SetInParent()
        elif field.label==field.LABEL_REPEATED:getattr(response,"hidden_hands_view").append(1)
        else:setattr(response,"hidden_hands_view",True if field.type==8 else 1)
        before=getattr(response,"hidden_hands_view")
        result=body(self.exchange(".lq.Lobby.fetchCharacterInfo",response)["bytes"],pb.ResCharacterInfo)
        self.assertEqual(result.main_character_id,20000128)
        self.assertEqual(next(c.skin for c in result.characters if c.charid==20000128),40012803)
        self.assertEqual(len(result.characters),129)
        self.assertEqual(len(result.skins),528)
        self.assertIn(20000131,[c.charid for c in result.characters])
        self.assertEqual(getattr(result,"hidden_hands_view"),before)

    def test_activity_workshop_field_preserved(self):
        notice=pb.NotifyAccountUpdate()
        update=notice.update
        # Verify the current workshop descriptor survives the actual modifying path.
        self.assertIn("work_shop_data",pb.AccountActivityUpdate.DESCRIPTOR.fields_by_name)
        field=pb.AccountUpdate.DESCRIPTOR.fields_by_name.get("activity")
        self.assertIsNotNone(field)
        activity=getattr(update,"activity")
        workshop=getattr(activity,"work_shop_data")
        if hasattr(workshop,"SetInParent"):workshop.SetInParent()
        elif hasattr(workshop,"add"):workshop.add().SetInParent()
        raw=frame(1,".lq.NotifyAccountUpdate",notice)
        result=body(self.send(raw)["bytes"],pb.NotifyAccountUpdate)
        self.assertEqual(result,notice)

    def test_skin_and_main_selection_persist_before_ack_and_restart(self):
        self.login()
        self.send(frame(2,".lq.Lobby.loginBeat",pb.ReqLoginBeat(contract="fixture"),8),True)
        result=self.send(frame(2,".lq.Lobby.changeCharacterSkin",
            pb.ReqChangeCharacterSkin(character_id=20000128,skin=40012802),9),True)
        self.assertEqual(basic_pb2.BaseMessage.FromString(result["bytes"][3:]).method_name,".lq.Lobby.loginBeat")
        self.assertEqual(len(result["inject_client"]),1)
        self.send(frame(3,"",pb.ResCommon(),9))
        self.send(frame(2,".lq.Lobby.changeMainCharacter",pb.ReqChangeMainCharacter(character_id=20000129),10),True)
        saved=json.loads((self.home/"rust/settings.mod.json").read_text("utf8"))
        self.assertEqual(saved["mainChar"],20000129)
        self.assertEqual(saved["charSkin"]["20000128"],40012802)
        self.stop();self.start();self.login()
        result=body(self.exchange(".lq.Lobby.fetchCharacterInfo",pb.ResCharacterInfo())["bytes"],pb.ResCharacterInfo)
        self.assertEqual(result.main_character_id,20000129)
        self.assertEqual(next(c.skin for c in result.characters if c.charid==20000128),40012802)

    def test_unknown_frames_gameplay_and_flow_isolation(self):
        for raw in [b"",b"hello",frame(3,"",pb.ResCommon(),42),
                    frame(1,".lq.ActionPrototype",pb.ActionPrototype(step=1,name="ActionDealTile",data=b"fixture"))]:
            result=self.send(raw,flow="game")
            self.assertEqual(result["bytes"],raw)
            self.assertFalse(result["drop"])
            self.assertEqual(result["inject_client"],[])
        self.send(frame(2,".lq.Lobby.fetchCharacterInfo",pb.ReqCommon(),5),True,"a")
        self.send(frame(2,".lq.Lobby.fetchServerTime",pb.ReqCommon(),5),True,"b")
        raw=frame(3,"",pb.ResServerTime(server_time=123),5)
        self.assertEqual(self.send(raw,flow="b")["bytes"],raw)
        chars=body(self.send(frame(3,"",pb.ResCharacterInfo(),5),flow="a")["bytes"],pb.ResCharacterInfo)
        self.assertEqual(len(chars.characters),129)
        self.assertTrue(self.command({"op":"close","flow":"a"})["closed"])

    def test_room_voice_identity_preserves_peer(self):
        self.login()
        res=pb.ResJoinRoom()
        res.room.room_id=321
        for account in [123456,456789]:
            player=res.room.persons.add(account_id=account,avatar_id=400101,nickname="fixture")
            player.character.charid=200001
            player.character.skin=400101
        peer=res.room.persons[1].SerializeToString()
        result=body(self.exchange(".lq.Lobby.joinRoom",res)["bytes"],pb.ResJoinRoom)
        self.assertEqual(result.room.persons[0].character.charid,20000128)
        self.assertEqual(result.room.persons[0].character.skin,40012803)
        self.assertEqual(result.room.persons[0].avatar_id,40012803)
        self.assertEqual(result.room.persons[1].SerializeToString(),peer)

if __name__=="__main__":unittest.main()
