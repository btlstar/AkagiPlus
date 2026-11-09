local saved,decoded={},{}
local active=7
local function copy(v) if type(v)~='table' then return v end local t={};for k,x in pairs(v) do t[k]=copy(x) end;return t end
Json={encode=function(v) local k='state'..tostring(#decoded+1);decoded[#decoded+1]=copy(v);saved[k]=copy(v);return k end,decode=function(k)return copy(saved[k])end}
if NATIVE_JSON then Json=NATIVE_JSON end
csharp={PlayerPrefs={GetString=function(k,d)return saved[k] or d end,SetString=function(k,v)saved[k]=v end,Save=function()end}}
local bag={user_equip_data={}}
function bag:GetEquipInfo(ty) for _,v in ipairs(self.user_equip_data) do if v.ItemType==ty then return v end end end
local player={GetUserID=function()return active end}
GameModules={ModelMgr={GetModel=function(_,ty) if ty==2 then return bag else return player end end}}
EModelType={Player=1,Bagpack=2};EnumDefine={ItemType={CardBack=14,Tablecloth=15}}
Configuration={role_config={[10001]={source=1},[10002]={source=1},[99999]={source=2},[10020]={source=2}},role_skin_config={[1000201]={role_id=10002}},item_config={[14001]={type=14},[14002]={type=14},[15001]={type=15},[19001]={type=19},[19002]={type=19},[30001]={type=30},[37001]={type=37},[37002]={type=37},[1]={type=1}}}
Configuration.title_config={[11001]={type=1},[11002]={type=3}}
local awakeArg
Configuration.SortEmojiList=function(data,skins,awake) awakeArg=awake end
local A=dofile(PAYLOAD)
local sent=0;local http={MjGamePost=function(url,data,cb,params)sent=sent+1;if cb then cb({code=0,data={}},params)end end}
A.install(http)
local response
Configuration.SortEmojiList({}, {}, false)
assert(awakeArg==true,'local awakening expression gate is unlocked')
local files={};local appended
csharp.Util={DataPath='synthetic'}
System={IO={File={Exists=function(path)return files[path]~=nil end,ReadAllText=function(path)return files[path]end,
    WriteAllText=function(path,data)files[path]=data end,AppendAllText=function(path,data)appended=data end}}}
local control='synthetic/zhangxinplus-ai-control.json'
files[control]=Json.encode({enabled=true,session='test',expires=os.time()+15})
A.forwardAI({cmd='cmd_game_start',data={game_mode=0}})
assert(appended,'leased local AI channel forwards gameplay')
local envelope=Json.decode(string.sub(appended,1,-2));assert(envelope.uid=='7' and envelope.seq==1)
appended=nil
A.forwardAI({cmd='login',data={token='must-not-forward'}})
assert(appended==nil,'auth and non-game messages are not forwarded')
files[control]=Json.encode({enabled=true,session='test',expires=os.time()-1})
A.forwardAI({cmd='cmd_game_start',data={}})
assert(appended==nil,'expired companion lease stops collection')
files[control]=nil
http.MjGamePost('users/updateRole',{roleID=10002,skinID=1000201},function(r)response=r end)
assert(sent==0 and response.code==0,'local role selection must not reach the server')
http.MjGamePost('backpack/equip',{itemID=14002},function(r)response=r end)
assert(sent==0 and response.code==0)
local original={code=0,data={{itemID=1,itemType=1,num=23}}}
local r=A.read('backpack/itemList',{},original)
assert(#original.data==1 and original.data[1].num==23,'never alter original response or currency')
assert(#r.data==9,'only reviewed cosmetics added')
local filtered=A.read('backpack/itemList',{itemsID={14001}},original)
assert(#filtered.data==2,'respect requested item IDs')
A.states={}
local packet={cmd='cmd_enter_room',data={players={{user={user_id=7,role_id=10001,skin_id=0}},{user={user_id=8,role_id=10001,skin_id=0}}}}}
A.onMessage(packet)
assert(packet.data.players[1].user.skin_id==1000201 and packet.data.players[1].user.card_back_id==14002,'selected cosmetics survive fresh state and room entry')
assert(packet.data.players[2].user.role_id==10001,'other players unchanged')
-- Inventory may complete before equipList: UI must see the local cache immediately.
bag.user_equip_data={{ItemType=14,ItemID=14001}}
A.read('backpack/itemList',{},original)
assert(bag:GetEquipInfo(14).ItemID==14002,'inventory callback must not render stale equipment')
local eq=A.read('backpack/equipList',{}, {code=0,data={{ItemType=14,ItemID=14001}}})
assert(eq.data[1].ItemID==14002,'late server equipment response must keep local selection')
http.MjGamePost('backpack/unloadEquip',{itemType=14},function(r)response=r end)
A.states={}
eq=A.read('backpack/equipList',{}, {code=0,data={{ItemType=14,ItemID=14001}}})
assert(#eq.data==0,'explicit local unequip must survive server refresh and reload')
http.MjGamePost('backpack/equip',{itemID=14002},function(r)response=r end)
assert(bag:GetEquipInfo(14).ItemID==14002,'a new selection clears unequip tombstone')
http.MjGamePost('backpack/equip',{itemType=19,itemID=19001,mode=3,modeItemIds={19001,19002}},function(r)response=r end)
http.MjGamePost('backpack/equip',{itemType=19,mode=2},function(r)response=r end)
http.MjGamePost('backpack/equip',{itemID=37001,emojiIDs={37001,0,37002}},function(r)response=r end)
A.states={}
eq=A.read('backpack/equipList',{}, {code=0,data={}})
local loaded={};for _,v in ipairs(eq.data) do loaded[v.ItemType]=v end
assert(loaded[19].Mode==2 and loaded[19].RandItemIDs[2]==19002,'music mode/playlist survives reload')
assert(loaded[37].RandItemIDs[2]==0 and loaded[37].RandItemIDs[3]==37002,'emoji keeps empty slot positions')
http.MjGamePost('backpack/equip',{itemID=37001,emojiIDs={14001}},function(r)response=r end)
assert(response.code~=0 and sent==0,'mixed type lists fail locally')
http.MjGamePost('backpack/equip',{itemID=30001},function(r)response=r end)
http.MjGamePost('users/updateTitle',{titleID=11002},function(r)response=r end)
A.states={}
local profile=A.read('users/userBaseData',{userID=7},{code=0,data={roleID=10001,titleID=11001}})
assert(profile.data.roleID==10002 and profile.data.profileFrameID==30001 and profile.data.titleID==11002,'local title/frame on own profile')
local other=A.read('users/userBaseData',{userID=8},{code=0,data={roleID=10001,titleID=11001}})
assert(other.data.roleID==10001 and other.data.titleID==11001,'other profile stays untouched')
local frames=A.read('backpack/userProfileFrame',{}, {code=0,data={}})
assert(#frames.data==1 and frames.data[1].itemID==30001 and frames.data[1].label==0,'frame list adds only frames')
local ts=A.read('users/titleList',{}, {code=0,data={{titleID=11001,titleState=3,type=1}}})
assert(ts.data[1].titleState==1 and ts.data[2].titleState==2 and ts.data[2].type==3,'titles retain category and selected state')
local room=A.read('lobbys/enterFriendMatch',{}, {code=0,data={players={{userID=7,roleId=10001,skinId=0},{userID=8,roleId=10001}}}})
assert(room.data.players[1].roleId==10002 and room.data.players[1].skinId==1000201,'friend room uses selected character and skin')
assert(room.data.players[2].roleId==10001,'friend room leaves other players intact')
packet={cmd='cmd_friend_match_action',data={userID=7,player={roleId=10001,skinId=0}}}
A.onMessage(packet)
assert(packet.data.player.skinId==1000201,'friend room updates keep selected skin')
local sk=A.read('users/getSkin',{roleID=10002},{code=0,data={{skinID=1000201,isOwn=false,ownemoticon=false}}})
assert(sk.data[1].ownemoticon==true,'skin emoji ownership follows local skin availability')
active=8
local own=A.read('users/homeUserData',{}, {code=0,data={roleID=10001,skinID=0}})
assert(own.data.roleID==10001,'accounts remain isolated')
active=7
http.MjGamePost('users/updateRole',{roleID=10001,skinID=1000201},function(r)response=r end)
assert(response.code~=0 and sent==0,'invalid role/skin pairing rejected without network fallback')
http.MjGamePost('backpack/openGiftBag',{},function()end)
assert(sent==1,'noncosmetic operations pass through')
http.MjGamePost('users/giveCultivateGift',{},function()end)
assert(sent==2,'progression remains server controlled')
local list=A.read('users/getRole',{roleID=0},{code=0,data={roleList={{roleID=10001,FeelValue=24},{roleID=10020,isOwn=false}}}})
assert(#list.data.roleList==2 and list.data.roleList[1].FeelValue==24,'do not fake earned progression')
active=0
http.MjGamePost('users/updateRole',{roleID=10001,skinID=0},function(r)response=r end)
assert(response.code~=0 and sent==2,'no account must not send local-only request')

-- Native bag uses item.isEquip, not just its separate user_equip_data cache.
active=7
http.MjGamePost('backpack/equip',{itemID=14002},function(r)response=r end)
A.states={}
local bagRead=A.read('backpack/itemList',{}, {code=0,data={{itemID=14001,itemType=14,num=1,isEquip=true},{itemID=14002,itemType=14,num=0,isEquip=false}}})
assert(bagRead.data[1].isEquip==false and bagRead.data[2].isEquip==true,'bag must display the saved item, not stale server isEquip flags')
http.MjGamePost('backpack/addEquipSuit',{name='local scheme'},function(r)response=r end)
assert(response.code==0 and sent==2,'adding local scheme must not reach server')
local schemeID=response.data.id
local schemeItems={{Category=1,ItemType=10002,ItemID=1000201,Model=0,IsRand=false,RandItemIDs={}},{Category=0,ItemType=14,ItemID=14001,IsRand=false,RandItemIDs={}},{Category=0,ItemType=15,ItemID=15001,IsRand=false,RandItemIDs={}}}
http.MjGamePost('backpack/editEquipSuit',{id=schemeID+0.0,name='saved',items=schemeItems},function(r)response=r end)
assert(response.code==0 and response.data.items[2].ItemID==14001)
http.MjGamePost('backpack/useEquipSuit',{id=schemeID+0.0,name='saved',items=schemeItems},function(r)response=r end)
assert(response.code==0 and response.data.useable[tostring(schemeID)]==true)
A.states={}
local schemes=A.read('backpack/userEquipSuit',{}, {code=0,list={}})
assert(#schemes.list==1 and schemes.list[1].name=='saved','saved schemes survive a fresh server list and reload')
bagRead=A.read('backpack/itemList',{}, {code=0,data={{itemID=14002,itemType=14,num=1,isEquip=true}}})
local chosen;for _,v in ipairs(bagRead.data) do if v.itemID==14001 then chosen=v end end
assert(bagRead.data[1].isEquip==false and chosen.isEquip==true,'using a scheme applies its gear to bag re-entry')
http.MjGamePost('backpack/unloadEquip',{itemID=14001},function(r)response=r end)
bagRead=A.read('backpack/itemList',{}, {code=0,data={{itemID=14001,itemType=14,num=1,isEquip=true}}})
assert(bagRead.data[1].isEquip==false,'unequip clears server isEquip too')
http.MjGamePost('backpack/removeEquipSuit',{id=schemeID},function(r)response=r end)
A.states={}
schemes=A.read('backpack/userEquipSuit',{}, {code=0,list={{id=schemeID,name='stale',items={}}}})
assert(#schemes.list==0,'deleted schemes must not return with a server refresh')
assert(sent==2,'all scheme writes stay local')
local unavailable=A.read('backpack/equipSuitList',{}, {code=0,list={
    {id=610,usable=false,items={{Category=1,ItemType=10002,ItemID=1000201},{Category=0,ItemType=1,ItemID=1}}},
    {id=611,usable=false,items={{Category=1,ItemType=10002,ItemID=1000201},{Category=0,ItemType=14,ItemID=14001}}},
}})
assert(unavailable.list[1].usable==false,'noncosmetic schemes must stay unavailable')
assert(unavailable.list[2].usable==true and type(unavailable.list[2].items[1].RandItemIDs)=='table','locally valid server schemes must be selectable with native array fields')

if NATIVE_SCHEME_FACTORY then
    -- The real client module runs here against a synthetic local HTTP layer.
    class=function()return {} end
    NetEvt={};Event={Brocast=function()end};i18NStr={}
    CommonHelper={ShowTips=function()end,GameFlowLog=function()end}
    TableUtil={DeepCopy=copy};EnumDefine.Category={Item=0,Skin=1}
    GameModules.CheckHttpCode=function(r)return r.code==0 end
    EModelType.DecoratDesignModel=3
    local model=NATIVE_SCHEME_FACTORY();model:Init()
    local lookup=GameModules.ModelMgr.GetModel
    GameModules.ModelMgr.GetModel=function(self,ty)if ty==3 then return model end;return lookup(self,ty) end
    local playerModel=GameModules.ModelMgr:GetModel(EModelType.Player)
    playerModel.ChangeMyUserBaseDatas=function(self,data)self.nativeSchemeRole=copy(data)end
    bag.ChangeEquipBaseDatas=function(self,items)self.nativeSchemeItems=copy(items)end
    local serverItems=copy(schemeItems)
    for _,v in ipairs(serverItems) do v.RandItemIDs=nil end
    HttpUtil={MjGamePost=function(url,data,cb,params)
        assert(url=='backpack/equipSuitList','native scheme writes may not reach the server: '..url)
        cb({code=0,list={{id='server-501',name='server scheme',usable=false,items=copy(serverItems)}}},params)
    end}
    A.install(HttpUtil)
    model:userEquipSuit()
    assert(model:GetDecoratDesignData('server-501').usable==true,'server lock cannot disable local Use button')
    if NATIVE_SCHEME_VIEW_FACTORY then
        -- Run the actual list-building and Use-button handlers, not just HTTP.
        local view=NATIVE_SCHEME_VIEW_FACTORY()
        view.decoratDesignModel=model;view.uiElemsBinder={designText={}}
        view.designList={UpdateListData=function(self,data)self.data=data end}
        HttpUtil.MjGamePost('backpack/equip',{itemID=14002},function()end)
        view:OnRefershView()
        local writes=A.writes
        view:OnClickYesButton(nil,{data=view.designList.data[1]})
        assert(A.writes==writes+1,'native Use click must reach the local setter')
        assert(bag:GetEquipInfo(14).ItemID==14001 and playerModel.nativeSchemeRole.skinID==1000201,'native Use click changes equipment and character')
        A.states={};model:userEquipSuit()
        local after=A.read('backpack/equipList',{}, {code=0,data={{ItemType=14,ItemID=14002}}})
        assert(after.data[1].ItemID==14001,'native Use selection survives lobby refresh and reload')
    end
    local writesBeforeError=A.writes
    local callbackCalled=false
    HttpUtil.MjGamePost('backpack/useEquipSuit',{id='',items=schemeItems},function()callbackCalled=true end)
    assert(not callbackCalled and A.writes==writesBeforeError and A.lastError,'invalid scheme must fail visibly without a native success callback')
    model:useEquipSuit('server-501','server scheme',schemeItems)
    assert(A.lastError==nil,'a successful retry clears stale error state')
    model:editEquipSuit('server-501','renamed server scheme',schemeItems,false)
    assert(model:GetDecoratDesignData('server-501').name=='renamed server scheme','string scheme IDs work for rename/save too')
    model:addEquipSuit('created via native callback')
    local created=model:GetDecoratDesignDatas()[2]
    assert(created and created.id>900000000,'native add callback receives the scheme object')
    model:editEquipSuit(created.id,'native saved',schemeItems,false)
    assert(model:GetDecoratDesignData(created.id).name=='native saved')
    model:useEquipSuit(created.id,'native saved',schemeItems)
    assert(playerModel.nativeSchemeRole.skinID==1000201 and bag.nativeSchemeItems[2].ItemID==14001)
    A.states={};model:userEquipSuit()
    local reloaded=model:GetDecoratDesignData(created.id)
    assert(reloaded and reloaded.name=='native saved' and reloaded.items[2].ItemID==14001,'native refresh keeps locally saved scheme')
    model:removeEquipSuit(created.id)
    model:userEquipSuit()
    assert(model:GetDecoratDesignData(created.id)==nil,'native delete callback and refresh agree')
    model:removeEquipSuit('server-501');A.states={};model:userEquipSuit()
    assert(model:GetDecoratDesignData('server-501')==nil,'deleted string scheme must not return after refresh')
end
