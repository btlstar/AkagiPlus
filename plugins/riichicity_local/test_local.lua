local uidValue=111
local prefs,encoded={},{}
local token=0
Json={encode=function(v)token=token+1;local k='fixture-'..token;encoded[k]=v;return k end,decode=function(k)assert(encoded[k],'invalid fixture json');return encoded[k]end}
csharp={PlayerPrefs={GetString=function(k,d)return prefs[k] or d end,SetString=function(k,v)prefs[k]=v end,Save=function()end}}
EModelType={Player='player'}
local nativeModel={GetUserID=function()return uidValue end}
GameModules={ModelMgr={GetModel=function()return nativeModel end}}
Configuration={role_config={[10001]={id=10001,source=1},[10069]={id=10069,source=2},[20004]={id=20004,source=0}},role_skin_config={[1000101]={role_id=10001},[1006902]={role_id=10069}},item_config={[10002]={id=10002,type=10},[14001]={id=14001,type=14},[14002]={id=14002,type=14},[30001]={id=30001,type=30}}}
local A=assert(loadfile(PAYLOAD))()
local r={code=0,data={roleList={{roleID=10001,isOwn=false,FeelValue=19}},useRoleID=10001}}
A.read('users/getRoleInfo',{},r)
assert(r.data.roleList[1].isOwn and #r.data.roleList==2,'all known playable roles')
assert(r.data.roleList[1].FeelValue==19,'preserve original progression')
local skins={code=0,data={{skinID=1006902,isOwn=false}}}
A.read('users/getSkinInfo',{roleID=10069},skins);assert(skins.data[1].isOwn and skins.data[1].ownemoticon)
local bag={code=0,data={{itemID=10002,itemType=10,num=7}}}
A.read('backpack/userItemList',{},bag);assert(bag.data[1].num==7 and #bag.data==4,'only cosmetic inventory extended')
local calls=0;local http={MjGamePost=function(url,data,cb,params)calls=calls+1;if cb then cb({code=0,data={}},params)end end}
A.install(http)
local success
http.MjGamePost('users/updateRoleInfo',{roleID=10069,skinID=1006902,model=0},function(ret)success=ret.code==0 end,{})
assert(success and calls==0,'local selection never sent to server')
local player={user={user_id=111,role_id=10001,skin_id=1000101},hand_cards={1,2,3},hand_chips=25000}
local other={user={user_id=222,role_id=10001,skin_id=1000101},hand_cards={4,5,6}}
A.onMessage({cmd='cmd_enter_room',data={players={player,other}}})
assert(player.user.role_id==10069 and player.user.skin_id==1006902 and other.user.role_id==10001)
assert(player.hand_cards[1]==1 and player.hand_chips==25000,'gameplay fields unchanged')
A.states={};local restored={code=0,data={roleList={{roleID=10069,isOwn=false}}}}
A.read('users/getRoleInfo',{},restored);assert(restored.data.useRoleID==10069,'cross-restart selection')
uidValue=333;local separate={code=0,data={roleList={{roleID=10001,isOwn=false}},useRoleID=10001}}
A.read('users/getRoleInfo',{},separate);assert(separate.data.useRoleID==10001,'account separation');uidValue=111
local failed
http.MjGamePost('users/updateRoleInfo',{roleID=10001,skinID=1006902},function(ret)failed=ret.code~=0 end,{})
assert(failed and calls==0,'invalid local choice rejected without server fallback')
http.MjGamePost('store/buyProduct',{productId=123},function()end,{});assert(calls==1,'unrelated purchase handling unchanged')
A.write('backpack/equipItem',{itemID=14002})
local equip={code=0,data={{ItemID=14001,ItemType=14}}};A.read('backpack/userEquip',{},equip);assert(equip.data[1].ItemID==14002)
local room={cmd='cmd_enter_room',data={players={player,other}}};A.onMessage(room);assert(player.user.card_back_id==14002)
local home={code=0,data={homePage={id='original',roleID=10001,skinID=1000101,items={}},gamePage={roles={{roleID=10001,skinID=1000101}}}}}
A.read('users/userHomePage',{},home);assert(home.data.gamePage.roles[1].roleID==10069)
A.write('users/editHomePage',{homePage={id='original',roleID=10069,skinID=1006902,items={}}})
local home2={code=0,data={homePage={id='original',roleID=10001,skinID=1000101,items={}},gamePage={roles={}}}}
A.read('users/userHomePage',{},home2);assert(home2.data.homePage.roleID==10069,'local hall selection restored')
uidValue=444;prefs['AkagiPlus.LocalCosmetics.v1.444']='corrupt';A.states={};assert(A.read('users/getRoleInfo',{},separate),'corrupt local storage tolerated')

-- V2 regressions from real native-client reports.
uidValue=111
Configuration.title_config={[10101]={id=10101},[10201]={id=10201}}
local permanent={code=0,data={{itemID=14001,itemType=14,num=0,expiredAt=1,limitedEndTime=1,isExpired=true},{itemID=10002,itemType=10,num=7,limitedEndTime=1}}}
A.read('backpack/userItemList',{},permanent)
assert(permanent.data[1].limitedEndTime==0 and permanent.data[1].expiredAt==0 and permanent.data[1].isExpired==false)
assert(permanent.data[2].num==7 and permanent.data[2].limitedEndTime==1,'currency is not locally unlocked')
for _,v in ipairs(permanent.data) do if v.itemType==14 or v.itemType==30 then assert(v.limitedEndTime==0 and v.isExpired==false) end end
A.write('users/addRoleStar',{roleID=10069,isSet=true})
A.states={};local stars={code=0,data={roleList={{roleID=10001,isStar=false,priority=0}}}}
A.read('users/getRoleInfo',{},stars)
local found=false;for _,v in ipairs(stars.data.roleList) do if v.roleID==10069 then found=v.isStar end end;assert(found,'new role star survives list reload')
A.write('users/addRoleStar',{roleID=10069,isSet=false});A.states={};A.read('users/getRoleInfo',{},stars)
for _,v in ipairs(stars.data.roleList) do if v.roleID==10069 then assert(v.isStar==false,'unstar survives reload') end end
local heads={code=0,data={{headID=0,headState=2,roleID=10001},{headID=37001,headState=3,expiredAt=1,roleID=0}}}
A.read('users/getHeadList',{},heads);assert(heads.data[2].headState==1 and heads.data[2].expiredAt==0,'native head ownership fields')
A.write('users/updateHead',{headID=37001});A.states={};A.read('users/getHeadList',{},heads);assert(heads.data[2].headState==2)
local titles={code=0,data={{titleID=10101,titleState=2},{titleID=10201,titleState=3,expiredAt=1}}}
A.read('users/getTitleList',{},titles);assert(titles.data[2].titleState==1 and titles.data[2].expiredAt==0,'native title ownership fields')
A.write('users/updateTitle',{titleID=10201,isSync=true});A.states={};A.read('users/getTitleList',{},titles);assert(titles.data[2].titleState==2)
local suite={code=0,data={list={{id='official',name='fixture',items={}}},total=1}}
A.read('backpack/userEquipSuitV2',{tab=0},suite)
local items={{Category=1,ItemType=10069,ItemID=1006902,Model=0,IsRand=false},{Category=0,ItemType=14,ItemID=14002,IsRand=false},{Category=4,ItemID=10201,ItemType=0},{Category=0,ItemType=30,ItemID=30001,IsRand=false}}
local saved
http.MjGamePost('backpack/editEquipSuitV1',{id='official',name='changed',items=items},function(ret)saved=ret end,{isOnlyChangeName=false})
assert(saved.code==0 and saved.data.items[2].ItemID==14002 and calls==1,'save-only suit is local with native response schema')
local used
http.MjGamePost('backpack/useEquipSuitV1',{id='official',name='changed',items=items},function(ret)used=ret end,{})
assert(used.code==0 and used.data.useable.official and calls==1,'save-and-use is local; no server expiry rejection')
A.states={};local suitsReload={code=0,data={list={{id='official',name='old',items={}}},total=1}}
A.read('backpack/userEquipSuitV2',{tab=0},suitsReload);assert(suitsReload.data.list[1].name=='changed' and suitsReload.data.list[1].items[2].ItemID==14002,'suit survives restart')
for _,url in ipairs({'lobbys/createFriendMatch','lobbys/enterFriendMatch','lobbys/getFriendMatchInfo'}) do
 local ret={code=0,data={players={{userID=111,roleId=10001,skinId=1000101,score=6},{userID=222,roleId=10001,skinId=1000101,score=7}},rule={playerCount=3}}};A.read(url,{},ret)
 assert(ret.data.players[1].roleId==10069 and ret.data.players[1].titleID==10201 and ret.data.players[1].score==6)
 assert(ret.data.players[2].roleId==10001 and ret.data.rule.playerCount==3,'friend room self only')
end
local lobby={code=0,data={nickname='fixture',stagePt=3}};A.read('users/homeUserData',{},lobby)
assert(lobby.data.headID==37001 and lobby.data.titleID==10201 and lobby.data.stagePt==3)
local page={code=0,data={homePage={id='original',roleID=10001,skinID=1000101,items={}},gamePage={roles={},titleIDs={10101},profileFrames={0}}}}
A.read('users/userHomePage',{},page);assert(page.data.gamePage.roles[1].roleID==10069 and page.data.gamePage.titleIDs[1]==10201)
A.write('backpack/removeEquipSuit',{id='official'});A.read('backpack/userEquipSuitV2',{tab=0},suitsReload);assert(#suitsReload.data.list==0,'deleted suit not resurrected by server list')
local newSuit=A.write('backpack/addEquipSuitV1',{name='new',tab=0});assert(newSuit.data.id)
local allSkins={code=0,list={}};A.read('backpack/suitSkins',{},allSkins);assert(#allSkins.list==2,'scheme role picker uses full client skin catalog')
local failedScheme
http.MjGamePost('backpack/useEquipSuitV1',{id='x',items={{Category=0,ItemType=10,ItemID=10002}}},function(ret)failedScheme=ret.code~=0 end,{})
assert(failedScheme and calls==1,'non-cosmetic suit refused locally')
uidValue=333;local otherAccount={code=0,data={{titleID=10201,titleState=3}}};A.read('users/getTitleList',{},otherAccount);assert(otherAccount.data[1].titleState==1,'catalog displayed locally')
local otherBase={code=0,data={titleID=10101,roleID=10001}};A.read('users/userBaseData',{userID=333},otherBase);assert(otherBase.data.titleID==10101,'selected title account isolated')
uidValue=111
-- Called by the runner using the actual generated ingress function, not a duplicate of it.
function AP_TEST_PACKET(category)
 local own={user={user_id=111,role_id=10001,skin_id=1000101},hand_cards={1,2},hand_chips=35000}
 local other={user={user_id=222,role_id=10001,skin_id=1000101},hand_cards={3,4},hand_chips=25000}
 local body={cmd='cmd_enter_room',data={players={own,other}}}
 local handle=function(packet)
  assert(packet.data.players[1].user.role_id==10069 and packet.data.players[1].user.skin_id==1006902,'all command categories apply before dispatch')
  assert(packet.data.players[1].user.card_back_id==14002 and packet.data.players[1].user.title_id==10201)
  assert(packet.data.players[2].user.role_id==10001 and packet.data.players[1].hand_chips==35000 and packet.data.players[1].hand_cards[2]==2)
 end
 CMD={[category]=handle};CMDDef={CMDRspHeartbeat=-1};Time={realtimeSinceStartup=0}
 log=function()end;logError=function(e)error(e)end;logWarn=function()end
 local disposed=false
 APIngress({cmd=category,bodyStr=Json.encode(body),version=1,Dispose=function()disposed=true end})
 assert(disposed,'packet disposed normally')
end

local previewModule = 'UIView/Role/RoleNewSoundView'
UISubViewDef = {RoleSound = {viewPath='UIView/Role', viewName='RoleNewSoundView'}}
local noOp = function() end
local voiceClass = AP_VOICE_CLASS
voiceClass.SetParentView = noOp
voiceClass.SetParent = noOp
voiceClass.SetViewName = noOp
voiceClass.SetIsFullScreen = noOp
voiceClass.Init = noOp
package.loaded[previewModule] = voiceClass
local profile = AP_VOICE_BASE
profile.ChildView, profile.ChildViewList = {}, {}
csharp.DateTime = {Now={Year=2026}}
DateUtil = {IsInDay=function() return false end, IsInLunarDay=function() return false end}
local owned = {}
local model = {GetRoleVoicesList=function() return owned end}
local original = voiceClass.new()
original.playerModel = model
assert(UIViewBase.CreateChildView == nil and voiceClass.IsUnlock == nil,'native class methods cannot be read on the class')
assert(not original:IsUnlock({id='6002',unlock=3}),'native off-holiday baseline')
A.onMessage({cmd='unrelated',data={}})
local voicePreview = profile:CreateChildView({}, UISubViewDef.RoleSound)
voicePreview.playerModel = model
EnumDefine={RoleSoundUnlockType={Default=0,Awake=1,Ancient=2}}
Configuration.role_sound_config={
 {id='lv2',unlock=1,extra={lv=2}}, {id='lv5',unlock=1,extra={lv=5}},
 {id='awaken',unlock=1,extra={awake=true}}, {id='seasonal',unlock=3}, {id='normal',unlock=0},
}
local voiceRole={roleID=10001,isOwn=true,cultivateStatus=1,FeelValue=19,oathValue=0}
A.read('users/getRoleInfo',{}, {code=0,data={roleList={voiceRole}}})
assert(Configuration.role_sound_config[1].unlock==0 and Configuration.role_sound_config[2].unlock==0 and Configuration.role_sound_config[3].unlock==0,'bond and awakened voice previews')
assert(Configuration.role_sound_config[4].unlock==3,'holiday catalog entries are unchanged')
for id=6002,6008 do
 assert(voicePreview:IsUnlock({id=tostring(id),unlock=3}),'holiday clip can be previewed')
end
assert(not voicePreview:IsUnlock({id='6009',unlock=3}),'other restricted clips follow native logic')
owned[1] = 6009
assert(voicePreview:IsUnlock({id='6009',unlock=3}),'native ownership is still honored')
assert(not voicePreview:IsUnlock({id='6002',unlock=4}),'an unrelated restriction is preserved')
local isUnlock = voicePreview.IsUnlock
profile:CreateChildView({}, UISubViewDef.RoleSound)
assert(voicePreview.IsUnlock == isUnlock,'preview is wrapped once')
assert(voiceRole.cultivateStatus==1 and voiceRole.FeelValue==19 and voiceRole.oathValue==0,'real progression preserved')

-- Native follow-role portraits encode role/skin/model inside the head ID.
Configuration.role_config[10022]={id=10022,source=1}
A.write('users/editHomePage',{homePage={id='original',roleID=10069,skinID=1006902,model=1,items={}}})
A.write('users/updateHead',{headID=100220000}) -- migrate the user's existing encoded choice
A.states={}
local defaultHeads={code=0,data={{headID=100220000,headState=2,type=1,roleID=10022,skinID=0,model=0},{headID=37001,headState=1,type=2,roleID=0}}}
A.read('users/getHeadList',{},defaultHeads)
local followID=100690201
assert(defaultHeads.data[1].headID==followID and defaultHeads.data[1].roleID==10069 and defaultHeads.data[1].skinID==1006902 and defaultHeads.data[1].model==1,'encoded follow avatar rebuilt from hall role')
assert(defaultHeads.data[2].roleID==0 and defaultHeads.data[2].headID==37001,'fixed sprites preserved')
assert(defaultHeads.data[1].headState==2,'migrated encoded selection stays selected')
local avatarHome={code=0,data={roleID=10001,skinID=1000101,headID=100220000}}
A.read('users/homeUserData',{},avatarHome);assert(avatarHome.data.headID==followID and avatarHome.data.roleID==10069)
local events=0;Event={Brocast=function()events=events+1 end};NetEvt={homeUserData='home',userBaseData='base'}
nativeModel.home_user_data={headID=100220000};nativeModel.my_user_base_data={headID=100220000,userID=111}
nativeModel.user_base_datas={[1]={[4]=nativeModel.my_user_base_data}};nativeModel.custom_head_list_data=defaultHeads.data
A.write('users/editHomePage',{homePage={id='original',roleID=10001,skinID=1000101,model=0,items={}}})
assert(nativeModel.userHeadId==100010100 and nativeModel.home_user_data.headID==100010100 and nativeModel.my_user_base_data.headID==100010100,'local player cache refreshes immediately')
assert(events>0,'native refresh events dispatched')
A.write('users/updateHead',{headID=37001});A.read('users/getHeadList',{},defaultHeads)
assert(defaultHeads.data[2].headState==2 and nativeModel.userHeadId==37001,'fixed sprite remains independently selected')
A.write('users/editHomePage',{homePage={id='original',roleID=10069,skinID=1006902,model=1,items={}}})
assert(nativeModel.userHeadId==37001,'changing role does not replace fixed sprite')
local defaultScheme=A.write('backpack/useEquipSuitV1',{id='dynamic-head-scheme',name='default',items={{Category=5,ItemType=37,ItemID=followID}}})
assert(defaultScheme.code==0,'scheme accepts native encoded role avatar')
local headRoom={cmd='cmd_enter_room',data={players={{user={user_id=111,role_id=10001,skin_id=1000101,head_id=100220000}}}}}
A.onMessage(headRoom);assert(headRoom.data.players[1].user.head_id==followID,'encoded follow head applied to own table profile')
A.write('users/updateHead',{headID=0});assert(nativeModel.userHeadId==followID,'legacy zero follows hall as well')

AP_TEST_FOLLOW_HEAD=headRoom.data.players[1].user.head_id

-- Reproduce a real stale match/default-skin record with an updated hall plan.
uidValue=555
Configuration.role_skin_config[1002206]={role_id=10022}
Configuration.role_skin_config[1002201]={role_id=10022}
local stale={version=1,skins={['10022']={roleID=10022,skinID=1002206,model=0}},equips={},pages={main={id='main',roleID=10022,skinID=1002206,model=0}},activePage='main',syncInGame=true,match={roleID=10001,skinID=0,model=0},game={roles={{roleID=10001,skinID=0,model=0}}}}
prefs['AkagiPlus.LocalCosmetics.v1.555']=Json.encode(stale);A.states={}
local function ownSkin()
 local packet={cmd='cmd_enter_room',data={players={{user={user_id=555,role_id=10001,skin_id=0,model=0},hand_chips=35000},{user={user_id=222,role_id=10001,skin_id=0}}}}}
 A.onMessage(packet)
 assert(packet.data.players[2].user.role_id==10001 and packet.data.players[1].hand_chips==35000)
 return packet.data.players[1].user
end
local initial=ownSkin();assert(initial.role_id==10022 and initial.skin_id==1002206,'legacy synced record uses selected hall skin on entry')
A.write('users/roleWearSkin',{roleID=10022,skinID=1002201,model=0})
assert(ownSkin().skin_id==1002201,'active role skin is applied to match')
A.write('users/roleWearSkin',{roleID=10022,skinID=1002206,model=1})
A.states={};local worn=ownSkin();assert(worn.skin_id==1002206 and worn.model==1,'special skin persists after restart')
local detail={code=0,data={roleID=10001,skinID=0}};A.read('users/userBaseData',{userID=555},detail)
assert(detail.data.roleID==worn.role_id and detail.data.skinID==worn.skin_id,'profile and entry agree')
A.write('users/roleWearSkin',{roleID=10069,skinID=1006902,model=0});assert(ownSkin().role_id==10022,'browsing another role does not switch active role')
A.write('users/changeRoleModel',{roleID=10022,model=0});assert(ownSkin().skin_id==1002206,'model-only change preserves selected skin')
A.write('users/editUserHomePage',{syncInGame=false})
A.write('users/updateRoleInfo',{roleID=10069,skinID=1006902,model=0})
A.write('users/roleWearSkin',{roleID=10022,skinID=1002201,model=0})
assert(ownSkin().role_id==10069 and ownSkin().skin_id==1006902,'independent match role remains independent')
A.write('users/editUserHomePage',{syncInGame=true});assert(ownSkin().role_id==10022 and ownSkin().skin_id==1002201,'enabling sync uses current hall skin')
A.write('users/roleWearSkin',{roleID=10022,skinID=0,model=0});assert(ownSkin().skin_id==0,'explicit default skin remains selectable')
uidValue=111


-- The decoded settlement command must not mutate the genuine progression packet.
function AP_TEST_SETTLEMENT()
 local moduleName='UIView/FavorabilitySettlement/FavorabilitySettlementView'
 UIViewDef={FavorabilitySettlement={viewPath='UIView/FavorabilitySettlement',viewName='FavorabilitySettlementView'}}
 local create=AP_NATIVE_SETTLEMENT.new
 local refresh=create().RefershView
 assert(AP_NATIVE_SETTLEMENT.RefershView==nil and type(refresh)=='function','native method lives on instances')
 local shown,view
 UIHelper={ShowView=function(def)
  shown=def
  view=require(moduleName).new()
 end}
 package.loaded[moduleName]=AP_NATIVE_SETTLEMENT
 A.onMessage({cmd='unrelated',data={}})
 assert(AP_NATIVE_SETTLEMENT.new==create,'unrelated packet does not load the settlement view')
 UIHelper.ShowView(UIViewDef.FavorabilitySettlement)
 assert(shown==UIViewDef.FavorabilitySettlement,'original UI opening is preserved')
 assert(view.RefershView~=refresh,'constructed view receives the portrait hook')
 local wrappedCreate=AP_NATIVE_SETTLEMENT.new
 local packet={cmd='cmd_feel_value_settle',data={roleId=10012,skinId=0,model=0,nowValue=2240,nowCultivateStatus=1}}
 CMD={[3]=function(received)
  assert(received.data.roleId==10012 and received.data.skinId==0 and received.data.model==0 and received.data.nowValue==2240)
 end}
 APIngress({cmd=3,bodyStr=Json.encode(packet),version=1,Dispose=function()end})
 assert(AP_NATIVE_SETTLEMENT.new==wrappedCreate,'constructor wrapped once')
 EnumDefine.CultivateStatus={FinishedAwaken=3}
 EnumDefine.ShowRolePanel={UpStage=1}
 local portrait={}
 local loaded
 local function load(role,skin,model,loader,img,panel)
  assert(img==portrait and panel==1)
  loaded={role,skin,model}
 end
 UIHelper.LoadRoleImg=load
 UIHelper.ShowView(UIViewDef.FavorabilitySettlement)
 assert(shown==UIViewDef.FavorabilitySettlement,'original UI opening is preserved')
 view.favorabilityData=packet.data
 view.uiElemsBinder={roleImg=portrait}
 view.ShowButtomBtns=function()end
 view.ShowBooldRole=function(self)
   assert(self.favorabilityData==packet.data and self.favorabilityData.roleId==10012 and self.favorabilityData.skinId==0 and self.favorabilityData.nowValue==2240)
 end
 uidValue=555
 A.write('users/roleWearSkin',{roleID=10022,skinID=1002206,model=1})
 view:RefershView()
 assert(loaded[1]==10022 and loaded[2]==1002206 and loaded[3]==1,'native portrait follows the local match role')
 assert(UIHelper.LoadRoleImg==load,'portrait override restored')
 local audio,subtitle
 local played,shownText
 EnumDefine.SoundName={FeelBubble='bubble'}
 SoundType={UI=1,Voice=2}
 SoundManager={Play=function()end,PlayWithRole=function(...) audio={...} end}
 CommonHelper={GetSoundContentName=function(...) subtitle={...}; return 'fixture_line' end}
 i18NStr=setmetatable({fixture_line='fixture subtitle'},{__index=function() return '%s' end})
 setmetatable(view.uiElemsBinder,{__index=function(self,key)
  local control={SetActive=function()end}
  self[key]=control
  return control
 end})
 view.autoMsgBox={SetContent=function(_,text) shownText=text end,SetActive=function(_,on) played=on end}
 packet.data.changeExpValue,packet.data.changeValue=0,20
 view:SetViewGoShow(1)
 assert(audio[1]==10022 and audio[2]==1002206 and audio[3]==1,'settlement audio follows the selected portrait')
 assert(audio[4]==8011 or audio[4]==8012,'original settlement dialogue selected')
 for i=1,4 do assert(subtitle[i]==audio[i],'subtitle resolves the exact line used for audio') end
 assert(played and shownText=='fixture subtitle' and view.uiElemsBinder.favorateText.text=='20','subtitle and progress rendered')
 assert(view.favorabilityData==packet.data and packet.data.roleId==10012 and packet.data.nowValue==2240,'original settlement data retained')
 SoundManager.PlayWithRole=function() error('synthetic playback failure') end
 assert(not pcall(view.SetViewGoShow,view,1) and view.favorabilityData==packet.data,'failure restores original settlement data')
 SoundManager.PlayWithRole=function(...) audio={...} end

 uidValue=333
 view:RefershView()
 assert(loaded[1]==10012 and loaded[2]==0 and loaded[3]==0,'without a local selection use the native portrait')
 view:SetViewGoShow(1)
 assert(audio[1]==10012 and subtitle[1]==10012,'without a local selection use the native audio and subtitle')
 uidValue=555
 UIHelper.LoadRoleImg=function() error('synthetic renderer failure') end
 local failing=UIHelper.LoadRoleImg
 assert(not pcall(view.RefershView,view) and UIHelper.LoadRoleImg==failing,'failure restores the native loader')
 uidValue=111
end

-- If the account omits its unearned task outfit, expose the shipped skin locally.
Configuration.role_config[10035]={id=10035}
Configuration.role_skin_config[1003502]={role_id=10035,source=8}
local special = {code=0,data={{skinID=0,isOwn=true}}}
A.read('users/getSkinInfo',{roleID=10035},special)
A.read('users/getSkinInfo',{roleID=10035},special)
assert(#special.data==2 and special.data[2].skinID==1003502 and special.data[2].isOwn)
local unrelated = {code=0,data={{skinID=0,isOwn=true}}}
A.read('users/getSkinInfo',{roleID=10022},unrelated)
assert(#unrelated.data==1,'the special skin does not appear on a different role')
assert(A.write('users/roleWearSkin',{roleID=10035,skinID=1003502}).code==0)
