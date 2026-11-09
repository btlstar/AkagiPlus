-- AkagiPlus independent local cosmetics. No changes to purchases or account entitlements.
-- Runs after the client's own HTTP decoding, and changes only local cosmetic views.
if _G.AkagiPlusLocalCosmetics then return _G.AkagiPlusLocalCosmetics end
local A = {version = 6, states = {}, headModes = {}}
local cosmeticTypes = {[13]=true,[14]=true,[15]=true,[16]=true,[17]=true,[18]=true,[19]=true,[20]=true,[22]=true,[24]=true,[25]=true,[26]=true,[27]=true,[28]=true,[30]=true,[36]=true,[37]=true,[38]=true,[39]=true,[40]=true,[42]=true}
local wireTypes = {[13]='riichi_stick_id',[14]='card_back_id',[15]='tablecloth_id',[16]='special_effect_id',[17]='riichi_effect_id',[19]='match_music_id',[20]='riichi_music_id',[24]='ming_effect_id',[26]='card_face_id',[30]='profile_frame_id',[36]='table_frame_id',[37]='head_id',[39]='hand_id'}
local function copy(v)
    if type(v) ~= 'table' then return v end
    local out = {}; for k,x in pairs(v) do out[k] = copy(x) end; return out
end
local function uid()
    local ok,v = pcall(function() return GameModules.ModelMgr:GetModel(EModelType.Player):GetUserID() end)
    if ok and v and tonumber(v) and tonumber(v) > 0 then return tostring(v) end
end
local function codec() return Json or json end
local function state()
    local id = uid(); if not id then return nil end
    if not A.states[id] then
        local s = {}; local raw = csharp.PlayerPrefs.GetString('AkagiPlus.LocalCosmetics.v1.'..id, '')
        if raw ~= '' then local ok,v=pcall(codec().decode,raw); if ok and type(v)=='table' and v.version==1 then s=v end end
        s.version=1;s.home=nil -- Older builds cached an entire response that was never read.
        for _,name in ipairs({'skins','equips','pages','stars','suits','suitOrder','deletedSuits','game'}) do
            if type(s[name])~='table' then s[name]={} end
        end
        A.states[id]=s
    end
    return A.states[id]
end
local function save(s)
    local id=uid(); assert(id,'No active local account')
    csharp.PlayerPrefs.SetString('AkagiPlus.LocalCosmetics.v1.'..id,codec().encode(s)); csharp.PlayerPrefs.Save()
end
local function config(name) return (Configuration and Configuration[name]) or {} end
-- Unlock only local voice previews; keep genuine progression and seasonal gates.
local previewCatalog
local function unlockVoicePreviews()
    local kinds=EnumDefine and EnumDefine.RoleSoundUnlockType
    if not kinds then return end
    local sounds=config('role_sound_config')
    if sounds==previewCatalog then return end
    for _,v in pairs(sounds) do
        if type(v)=='table' and v.unlock==kinds.Awake then v.unlock=kinds.Default end
    end
    previewCatalog=sounds
end
local function setMatch(s,r)
    s.match=copy(r);s.game.roles={copy(r)};s.game.isRoleRandom=false
end
local function validRole(id) return type(id)=='number' and config('role_config')[id] ~= nil end
local function validSkin(role,skin)
    if not validRole(role) then return false end
    if skin==0 then return true end
    local c=config('role_skin_config')[skin]; return c and c.role_id==role
end
local function overlayRole(v,r,style)
    if not r then return end
    if style=='wire' then v.role_id=r.roleID;v.skin_id=r.skinID;v.model=r.model or 0
    elseif style=='friend' then v.roleId=r.roleID;v.skinId=r.skinID;v.model=r.model or 0
    else v.roleID=r.roleID;v.skinID=r.skinID;v.model=r.model or 0 end
end
local function ownList(list,field)
    if type(list)~='table' then return end
    for _,v in ipairs(list) do if type(v)=='table' then v.isOwn=true; if field then v[field]=true end end end
end
local function roleList(list,s)
    if type(list)~='table' then return end
    local seen={}; for _,v in ipairs(list) do v.isOwn=true;seen[v.roleID]=true; if s.stars[tostring(v.roleID)]~=nil then v.isStar=s.stars[tostring(v.roleID)];v.starTime=v.isStar and (s.starTime or 1) or 0 end; if s.skins[tostring(v.roleID)] then v.recentSkinId=s.skins[tostring(v.roleID)].skinID end end
    local template=list[1]
    if not template then return end
    for id,c in pairs(config('role_config')) do
        if type(id)=='number' and id>=10000 and id<20000 and c.source and c.source>0 and not seen[id] then
            local v=copy(template);v.roleID=id;v.isOwn=true;v.isCanGet=true;v.FeelValue=0;v.oathValue=0;v.cultivateStatus=0;v.recentSkinId=0;v.model=0;v.isStar=s.stars[tostring(id)] or false;v.starTime=v.isStar and (s.starTime or 1) or 0;v.priority=0;list[#list+1]=v
        end
    end
end
local function inventory(list,req,onlyFrames)
    if type(list)~='table' then return end
    local seen={}; for _,v in ipairs(list) do
        seen[v.itemID]=true
        local c=config('item_config')[v.itemID]
        if c and cosmeticTypes[c.type] then v.num=math.max(tonumber(v.num) or 0,1);v.isOwn=true;v.expiredAt=0;v.limitedEndTime=0;v.isExpired=false end
    end
    local requested
    if req.itemsID then requested={};for _,id in ipairs(req.itemsID) do requested[id]=true end end
    for id,c in pairs(config('item_config')) do
        local allowed=cosmeticTypes[c.type] and (not onlyFrames or c.type==30)
        if allowed and not seen[id] and (not req.itemType or req.itemType==c.type) and (not requested or requested[id]) then
            list[#list+1]={itemID=id,itemType=c.type,num=1,label=0,expiredAt=0,limitedEndTime=0,isExpired=false,isNew=false}
        end
    end
end
local function applyEquips(list,s)
    if type(list)~='table' then return end
    for ty,eq in pairs(s.equips) do
        local found=false
        for i,v in ipairs(list) do if v.ItemType==tonumber(ty) then list[i]=copy(eq);found=true;break end end
        if not found then list[#list+1]=copy(eq) end
    end
end
local function pagesList(s)
    local list={};for _,p in pairs(s.pages) do list[#list+1]=copy(p) end;table.sort(list,function(a,b)return tostring(a.id)<tostring(b.id)end);return list
end

local function hallRole(s)
    local p=s.pages[tostring(s.activePage)]
    return p and {roleID=p.roleID,skinID=p.skinID,model=p.model or 0} or s.match
end
local function rememberWear(s,r,selectForMatch)
    s.skins[tostring(r.roleID)]=copy(r)
    local p=s.pages[tostring(s.activePage)]
    local changesHall=p and p.roleID==r.roleID
    if changesHall then p.skinID=r.skinID;p.model=r.model or 0 end
    if selectForMatch or (s.match and s.match.roleID==r.roleID) or (changesHall and s.syncInGame==true) then setMatch(s,r) end
end
local function migrateSkinSync(s)
    if s.skinSyncVersion==1 then return end
    local p=s.pages[tostring(s.activePage)]
    local role=(s.syncInGame==true and p) or s.match
    if role and validSkin(role.roleID,role.skinID or 0) then
        local r={roleID=role.roleID,skinID=role.skinID or 0,model=role.model or 0}
        -- The active hall plan is authoritative when hall/game synchronization is on.
        -- With independent roles, retain the match role and its latest worn skin.
        if s.syncInGame~=true then
            local worn=s.skins[tostring(r.roleID)]
            if worn and validSkin(worn.roleID,worn.skinID) then r=copy(worn) end
        end
        setMatch(s,r)
    end
    s.skinSyncVersion=1
end
local function isRoleHead(id)
    return id==0 or (type(id)=='number' and id>=100000000 and id<200000000 and validRole(math.floor(id/10000)))
end
local function encodedHead(role)
    if not role or not validSkin(role.roleID,role.skinID or 0) then return nil end
    return role.roleID*10000+((role.skinID or 0)%100)*100+(role.model or 0)
end
local function followsHead(s,id)
    if s.followHallHead~=nil then return s.followHallHead end
    return isRoleHead(id)
end
local function currentHead(s,fallback)
    local id=s.headID
    if id==nil then id=fallback end
    return followsHead(s,id) and (encodedHead(hallRole(s)) or id) or id
end
local function selectHead(s,id)
    s.headID=id
    local mode=A.headModes[tostring(id)]
    if mode~=nil then s.followHallHead=mode else s.followHallHead=isRoleHead(id) end
end

-- These are the client's distinct cosmetic endpoints, not aliases of home-page saves.
local function profile(v,s,style,role)
    overlayRole(v,role or s.match,style)
    local head=currentHead(s,style=='wire' and v.head_id or v.headID)
    local title=(style and s.game.titleIDs and s.game.titleIDs[1]) or s.titleID
    local frame=(style and s.game.profileFrames and s.game.profileFrames[1]) or (s.equips['30'] or {}).ItemID
    if style=='wire' then
        if title~=nil then v.title_id=title end
        if frame~=nil then v.profile_frame_id=frame end
        for ty,eq in pairs(s.equips) do local field=wireTypes[tonumber(ty)];if field then v[field]=eq.ItemID end end
        if head~=nil then v.head_id=head end
    else
        if head~=nil then v.headID=head end
        if title~=nil then v.titleID=title end
        if frame~=nil then v.profileFrameID=frame end
    end
end
local function selfFriend(v,s)
    if type(v)=='table' and tostring(v.userID)==uid() then profile(v,s,'friend') end
end
local function listStates(list,field,selected,idField)
    for _,v in ipairs(list or {}) do
        v[field]=(selected~=nil and v[idField]==selected) and 2 or ((selected==nil and v[field]==2) and 2 or 1)
        v.expiredAt=0
    end
end
local function avatarList(list,s)
    local role=hallRole(s)
    local selected=s.headID
    if selected==nil then
        for _,v in ipairs(list or {}) do if v.headState==2 then selected=v.headID;break end end
    end
    for _,v in ipairs(list or {}) do
        local original=v.headID
        local dynamic=isRoleHead(original) and (v.type==nil or v.type==1)
        A.headModes[tostring(original)]=dynamic
        if dynamic then
            overlayRole(v,role)
            v.headID=encodedHead(role) or original
            A.headModes[tostring(v.headID)]=true
        end
    end
    listStates(list,'headState',currentHead(s,selected),'headID')
end
local function syncAvatar(s)
    local ok,player=pcall(function()return GameModules.ModelMgr:GetModel(EModelType.Player)end)
    if not ok or not player then return end
    local head=currentHead(s,player.userHeadId)
    if head==nil then return end
    local changed=player.userHeadId~=head
    player.userHeadId=head
    if player.home_user_data then player.home_user_data.headID=head end
    if player.my_user_base_data then player.my_user_base_data.headID=head end
    for _,group in pairs(player.user_base_datas or {}) do
        for _,v in pairs(group) do v.headID=head end
    end
    -- Cached avatar rows may already be on screen when the hall role changes.
    for _,v in ipairs(player.custom_head_list_data or {}) do
        if A.headModes[tostring(v.headID)]==true then
            overlayRole(v,hallRole(s));v.headID=encodedHead(hallRole(s)) or v.headID
            A.headModes[tostring(v.headID)]=true
        end
        v.headState=v.headID==head and 2 or 1
    end
    if changed and Event and Event.Brocast and NetEvt then
        if player.home_user_data and NetEvt.homeUserData then pcall(Event.Brocast,NetEvt.homeUserData,player.home_user_data,{}) end
        if player.my_user_base_data and NetEvt.userBaseData then pcall(Event.Brocast,NetEvt.userBaseData,player.my_user_base_data,{}) end
    end
end
local function applyGame(d,s)
    for k,v in pairs(s.game) do d[k]=copy(v) end
    if s.match then d.roles={copy(s.match)};d.isRoleRandom=false end
end
local function rememberSuit(s,p,tab)
    local id=tostring(p.id)
    if not s.suits[id] then s.suitOrder[#s.suitOrder+1]=p.id end
    p=copy(p);p.tab=p.tab or tab;s.suits[id]=p
end
local function suitList(s,tab)
    local list={}
    for _,id in ipairs(s.suitOrder) do
        local p=s.suits[tostring(id)]
        if p and not s.deletedSuits[tostring(id)] and (tab==nil or p.tab==nil or p.tab==tab) then
            local v=copy(p);v.usable=true;list[#list+1]=v
        end
    end
    return list
end
local function validateItems(items)
    assert(type(items)=='table','Missing local suit items')
    for _,v in ipairs(items) do
        if v.Category==1 then
            assert(validSkin(v.ItemType,v.ItemID),'Invalid suit role/skin')
            for _,r in ipairs(v.RandSkinItems or {}) do assert(validSkin(r.roleId,r.skinId),'Invalid role pool') end
        elseif v.Category==4 then
            assert(v.ItemID==0 or config('title_config')[v.ItemID],'Invalid suit title')
        elseif v.Category==5 then
            assert(isRoleHead(v.ItemID) or config('item_config')[v.ItemID],'Invalid suit head')
        else
            local c=config('item_config')[v.ItemID]
            assert(c and cosmeticTypes[c.type] and c.type==v.ItemType,'Invalid suit cosmetic')
            for _,id in ipairs(v.RandItemIDs or {}) do assert(config('item_config')[id] and config('item_config')[id].type==c.type,'Invalid suit pool') end
        end
    end
end
local function useSuit(s,items)
    validateItems(items)
    for _,v in ipairs(items) do
        if v.Category==1 then
            local r={roleID=v.ItemType,skinID=v.ItemID,model=v.Model or 0}
            setMatch(s,r);s.skins[tostring(r.roleID)]=copy(r)
            if v.headID~=nil then selectHead(s,v.headID) end
        elseif v.Category==4 then s.game.titleIDs={v.ItemID};s.game.isTitleRandom=false
        elseif v.Category==5 then selectHead(s,v.ItemID)
        else
            s.equips[tostring(v.ItemType)]={ItemType=v.ItemType,ItemID=v.ItemID,IsRand=v.IsRand or false,RandItemIDs=copy(v.RandItemIDs or {v.ItemID}),Model=v.Model or 0}
            if v.ItemType==30 then s.game.profileFrames={v.ItemID};s.game.isProfileFramesRandom=false end
        end
    end
end

function A.read(url,req,ret)
    if type(ret)~='table' or ret.code~=0 then return ret end
    local s=state();if not s then return ret end
    migrateSkinSync(s)
    local d=ret.data;req=req or {}
    if url=='users/getRoleInfo' or url=='users/getRoleAndSkin' or url=='users/getRoleVoices' then unlockVoicePreviews() end
    if url=='users/getRoleInfo' and type(d)=='table' then
        roleList(d.roleList,s)
        if s.match then d.useRoleID=s.match.roleID;d.useSkinID=s.match.skinID;d.model=s.match.model or 0 end
    elseif url=='users/getSkinInfo' then ownList(d,'ownemoticon')
    elseif url=='users/getRoleAndSkin' and type(d)=='table' then
        roleList(d.roleList,s);ownList(d.skinList,'ownemoticon');if d.roleInfo then d.roleInfo.isOwn=true end
    elseif url=='users/getAllSkinInfo' then ownList(d)
    elseif url=='users/userBaseData' and tostring(req.userID)==uid() and type(d)=='table' then profile(d,s)
    elseif url=='users/homeUserData' and type(d)=='table' then
        profile(d,s,nil,hallRole(s))
    elseif url=='users/getHeadList' then avatarList(d,s)
    elseif url=='lobbys/enterFriendMatch' or url=='lobbys/getFriendMatchInfo' or url=='lobbys/createFriendMatch' then
        if type(d)=='table' then for _,v in ipairs(d.players or {}) do selfFriend(v,s) end end
    elseif url=='backpack/userEquipSuitV2' and type(d)=='table' then
        for _,v in ipairs(d.list or {}) do if not s.suits[tostring(v.id)] and not s.deletedSuits[tostring(v.id)] then rememberSuit(s,v,req.tab) end end
        d.list=suitList(s,req.tab);d.total=#suitList(s);save(s)
    elseif url=='backpack/suitSkins' then
        local seen={};ret.list=ret.list or {}
        for _,v in ipairs(ret.list) do seen[tostring(v.roleId)..':'..tostring(v.skinId)..':'..tostring(v.model or 0)]=true;if s.stars[tostring(v.roleId)]~=nil then v.favor=s.stars[tostring(v.roleId)] end end
        for id,c in pairs(config('role_skin_config')) do
            local role=c.role_id;local rc=config('role_config')[role]
            if rc and role>=10000 and role<20000 and rc.source and rc.source>0 then
                local k=tostring(role)..':'..tostring(id)..':0'
                if not seen[k] then ret.list[#ret.list+1]={roleId=role,skinId=id,model=0,favor=s.stars[tostring(role)] or false} end
            end
        end
    elseif url=='backpack/userItemList' then inventory(d,req,false)
    elseif url=='backpack/userProfileFrame' then inventory(d,req,true)
    elseif url=='users/getTitleList' then
        listStates(d,'titleState',s.titleID,'titleID')
    elseif url=='backpack/userEquip' then applyEquips(d,s)
    elseif url=='users/homePageList' and type(d)=='table' then
        for _,p in ipairs(d.list or {}) do if not s.pages[tostring(p.id)] then s.pages[tostring(p.id)]=copy(p) end end
        d.list=pagesList(s);if s.activePage then d.useHomePageId=s.activePage end
        if s.syncInGame~=nil then d.syncInGame=s.syncInGame else s.syncInGame=d.syncInGame end
        if s.enterRand~=nil then d.enterRand=s.enterRand end
    elseif url=='users/userHomePage' and type(d)=='table' and type(d.homePage)=='table' then
        local original=d.homePage;local id=s.activePage or original.id
        if not s.pages[tostring(original.id)] then s.pages[tostring(original.id)]=copy(original) end
        d.homePage=copy(s.pages[tostring(id)] or original);s.activePage=d.homePage.id
        if type(d.gamePage)=='table' then applyGame(d.gamePage,s) end
        save(s)
    end
    syncAvatar(s)
    return ret
end
local setters={}
for _,url in ipairs({
    'users/updateRoleInfo','users/roleWearSkin','users/changeRoleModel','users/addRoleStar',
    'users/updateHead','users/updateTitle','users/editUserSyncSwitch',
    'users/editHomePage','users/addHomePage','users/removeHomePage','users/useHomePage','users/editUserHomePage',
    'backpack/equipItem','backpack/batchItemEquip','backpack/unloadEquip','backpack/updateGameSuit',
    'backpack/addEquipSuitV1','backpack/editEquipSuitV1','backpack/useEquipSuitV1','backpack/removeEquipSuit','backpack/equipSuitSort',
}) do setters[url]=true end
function A.write(url,req)
    if not setters[url] then return nil end
    local s=state();if not s then return nil end
    migrateSkinSync(s)
    req=req or {};local result={code=0,message='ok',data={}}
    if url=='users/addRoleStar' then
        assert(validRole(req.roleID),'Unknown local star role');s.stars[tostring(req.roleID)]=req.isSet==true;s.starTime=os.time()
    elseif url=='users/updateHead' then
        assert(type(req.headID)=='number','Missing local head');selectHead(s,req.headID);result.data=true;result.HeadID=currentHead(s)
    elseif url=='users/updateTitle' then
        assert(req.titleID==0 or config('title_config')[req.titleID],'Unknown local title');s.titleID=req.titleID
        if req.isSync then s.game.titleIDs={req.titleID};s.game.isTitleRandom=false end
    elseif url=='users/editUserSyncSwitch' then
        s.game.isSyncProfileFrame=req.syncProfileFrame;s.game.isSyncTitle=req.syncTitle
    elseif url=='backpack/updateGameSuit' then
        if req.category==4 then
            assert(req.titleId==0 or config('title_config')[req.titleId],'Unknown local title');s.game.titleIDs={req.titleId};s.game.isTitleRandom=false
            if req.isSync then s.titleID=req.titleId end
        else
            assert(config('item_config')[req.profileFrameId] and config('item_config')[req.profileFrameId].type==30,'Unknown frame')
            s.game.profileFrames={req.profileFrameId};s.game.isProfileFramesRandom=false
            if req.isSync then s.equips['30']={ItemType=30,ItemID=req.profileFrameId,RandItemIDs={req.profileFrameId}} end
        end
    elseif url=='backpack/addEquipSuitV1' then
        local id='ap-suit-'..tostring(os.time())..'-'..tostring(#s.suitOrder+1)
        local p={id=id,name=req.name,tab=req.tab,usable=true,items={},createTime=os.time()}
        rememberSuit(s,p,req.tab);result.data=copy(p)
    elseif url=='backpack/editEquipSuitV1' or url=='backpack/useEquipSuitV1' then
        validateItems(req.items)
        local p=copy(s.suits[tostring(req.id)] or {id=req.id});assert(p.id,'Missing local suit id')
        p.name=req.name;p.items=copy(req.items);p.usable=true;rememberSuit(s,p,p.tab);result.data=copy(p)
        if url=='backpack/useEquipSuitV1' then
            useSuit(s,req.items);local usable={};for id in pairs(s.suits) do usable[id]=true end;result.data={useable=usable}
        end
    elseif url=='backpack/removeEquipSuit' then s.suits[tostring(req.id)]=nil;s.deletedSuits[tostring(req.id)]=true
    elseif url=='backpack/equipSuitSort' then s.suitOrder=copy(req.suitIds or s.suitOrder)
    elseif url=='users/updateRoleInfo' or url=='users/roleWearSkin' or url=='users/changeRoleModel' then
        local role=req.roleID;local previous=s.skins[tostring(role)] or {}
        local skin=req.skinID or previous.skinID or 0
        assert(validSkin(role,skin),'Unknown local role or skin')
        local model=req.model;if model==nil then model=previous.model or 0 end
        rememberWear(s,{roleID=role,skinID=skin,model=model},url=='users/updateRoleInfo')
    elseif url=='backpack/equipItem' or url=='backpack/batchItemEquip' or url=='backpack/unloadEquip' then
        local id=req.itemID or (req.itemIDs or {})[1];local c=config('item_config')[id]
        if not c or not cosmeticTypes[c.type] then return nil end
        local ids=copy(req.itemIDs or {id})
        for _,x in ipairs(ids) do assert(config('item_config')[x] and config('item_config')[x].type==c.type,'Invalid local equip list') end
        if url=='backpack/unloadEquip' or req.isEquip==false then s.equips[tostring(c.type)]=nil
        else s.equips[tostring(c.type)]={ItemType=c.type,ItemID=id,RandItemIDs=ids,IsRand=false} end
        if c.type==30 and req.isSync then s.game.profileFrames={id};s.game.isProfileFramesRandom=false end
    elseif url=='users/editHomePage' or url=='users/addHomePage' then
        local p=copy(req.homePage);assert(type(p)=='table','Unsupported home-page schema')
        if url=='users/addHomePage' then p.id='ap-local-'..tostring(os.time())..'-'..tostring(#pagesList(s)+1);result.data=copy(p) end
        assert(p.id,'Missing local page id');s.pages[tostring(p.id)]=p
        if p.id==s.activePage and validSkin(p.roleID,p.skinID or 0) then s.skins[tostring(p.roleID)]={roleID=p.roleID,skinID=p.skinID or 0,model=p.model or 0} end
        if s.syncInGame==true and validSkin(p.roleID,p.skinID or 0) then setMatch(s,{roleID=p.roleID,skinID=p.skinID or 0,model=p.model or 0}) end
    elseif url=='users/removeHomePage' then s.pages[tostring(req.homePageId)]=nil
    elseif url=='users/useHomePage' then assert(s.pages[tostring(req.homePageId)],'Unknown local page');s.activePage=req.homePageId
        local p=s.pages[tostring(req.homePageId)];if validSkin(p.roleID,p.skinID or 0) then s.skins[tostring(p.roleID)]={roleID=p.roleID,skinID=p.skinID or 0,model=p.model or 0} end;if s.syncInGame==true and validSkin(p.roleID,p.skinID or 0) then setMatch(s,{roleID=p.roleID,skinID=p.skinID or 0,model=p.model or 0}) end
    elseif url=='users/editUserHomePage' then
        s.syncInGame=req.syncInGame;s.enterRand=req.enterRand
        local p=s.pages[tostring(s.activePage)]
        if s.syncInGame==true and p and validSkin(p.roleID,p.skinID or 0) then setMatch(s,{roleID=p.roleID,skinID=p.skinID or 0,model=p.model or 0}) end
    end
    save(s);syncAvatar(s);return result
end
function A.onMessage(packet)
    if type(packet)~='table' or type(packet.data)~='table' then return end
    if packet.cmd~='cmd_enter_room' and packet.cmd~='cmd_friend_match_action' then return end
    local s=state();if not s then return end
    migrateSkinSync(s)
    local d=packet.data
    if packet.cmd=='cmd_enter_room' then
        for _,p in ipairs(d.players or {}) do
            local u=p.user
            if u and tostring(u.user_id)==uid() then profile(u,s,'wire') end
        end
    else
        selfFriend(d.player,s)
        for _,v in ipairs(d.players or {}) do selfFriend(v,s) end
    end
end
function A.install(http)
    if http.__akagiplus_local then return end
    http.__akagiplus_local=true;local original=http.MjGamePost
    http.MjGamePost=function(url,data,callback,params,...)
        if setters[url] then
            local ok,response=pcall(A.write,url,data)
            if not ok then response={code=1,message='AkagiPlus local cosmetic selection failed',data={}} end
            if response then if callback then callback(response,params) end;return end
        end
        if not callback then return original(url,data,callback,params,...) end
        return original(url,data,function(ret,...)
            local ok,v=pcall(A.read,url,data,ret)
            if not ok then if logWarn then logWarn('[AkagiPlus LocalCosmetics] read schema not supported') end;v=ret end
            return callback(v,...)
        end,params,...)
    end
    if logWarn then logWarn('[AkagiPlus LocalCosmetics] installed v'..A.version) end
end
_G.AkagiPlusLocalCosmetics=A
return A
