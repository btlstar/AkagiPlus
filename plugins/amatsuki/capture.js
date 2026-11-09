"use strict";
const listeners=[];
let muted=0,seat=-1;
const types=new Set(['JoinDeskResponse','ReconnectResponse','ReconnectInfoResponse','JpGameStart','RoundStart','SyncDoraArea','TehaiAction','RiverAction','AllRonAction','RyuukyokuAction','DrawActionResponse','ReachSet','GameEnd','KickOutResponse']);
function ownUid(){const user=IL.staticRead('Gvar','userInfo');return user&&!user.isNull()?IL.read(user,'uid'):null;}
function packet(result){
  const klass=IL.api.objectClass(result),type=IL.typeName(IL.api.classType(klass));
  if(!type.startsWith('JpGameResponse.'))return;
  const name=IL.api.name(klass).readUtf8String();if(!types.has(name))return;
  const uid=ownUid();if(!uid)return;
  muted++;let data;try{
    if(name==='RoundStart'){
      data={bakaze:IL.read(result,'bakaze'),oya:IL.read(result,'oya'),honba:IL.read(result,'honba'),playerPoints:IL.ints(IL.read(result,'playerPoints'),true)};
      data.playerTiles=IL.list(IL.read(result,'playerTiles')).map((item,index)=>{
        const hand=IL.list(IL.read(IL.read(item,'tehai'),'hand'));
        return {tehai:{hand:hand.map(card=>index===seat?IL.json(card):{name:'?'})}};
      });
    }else if(name==='JoinDeskResponse'||name==='ReconnectResponse'){
      data={};for(const field of ['status','errorCode','gameType','gameMode','roomType','endBakaze','startingPoint','singleKyoku'])data[field]=IL.read(result,field);
    }else if(name==='ReconnectInfoResponse')data={reconnect:true};
    else if(name==='JpGameStart'){
      data={playerList:IL.list(IL.read(result,'playerList')).map(p=>({uid:IL.read(p,'uid'),name:IL.read(p,'name'),posId:IL.read(p,'posId'),isEmpty:IL.read(p,'isEmpty')}))};
      seat=data.playerList.findIndex(p=>p.uid===uid);
    }else data=IL.json(result);
  }finally{muted--;}
  send({kind:'packet',type:name,uid,data});
}
rpc.exports={start(){return IL.attached(()=>{
  const method=IL.method('Newtonsoft.Json.Serialization.JsonSerializerInternalReader','Deserialize',3);
  listeners.push(Interceptor.attach(method.address,{onLeave(result){if(muted||result.isNull())return;try{packet(result);}catch(error){send({kind:'error',message:'天月消息读取失败：'+String(error)});}}}));
  const lobby=IL.methods(IL.klass('LobbyMgr')).find(m=>m.name==='Start'&&m.params.length===0);
  if(lobby)listeners.push(Interceptor.attach(lobby.address,{onEnter(){seat=-1;send({kind:'packet',type:'LobbyReturned',data:{}});}}));
  return {kind:'status',message:'已连接天月，请从新对局开局开始同步。'};
});},stop(){listeners.splice(0).forEach(x=>x.detach());}};
