-- ZhangxinPlus: local cosmetic plugin, reviewed resource baseline 92217.
-- Cosmetic selections stay on this computer, separately for each game UID.
if _G.ZhangxinPlus then return _G.ZhangxinPlus end
local A = {version='0.1.5', states={}, reads=0, writes=0, instance=tostring(os.time())..'-'..tostring(os.clock())}
local function copy(v)
    if type(v)~='table' then return v end
    local t={};for k,x in pairs(v) do t[k]=copy(x) end;return t
end
local function config(name) return (Configuration and Configuration[name]) or {} end
local function player() return GameModules.ModelMgr:GetModel(EModelType.Player) end
local function uid()
    local ok,id=pcall(function() return player():GetUserID() end)
    if ok and tonumber(id) and tonumber(id)>0 then return tostring(id) end
end
local function state()
    local id=uid();if not id then return end
    if not A.states[id] then
        local s={schema=1,equips={},skins={},stars={}}
        local raw=csharp.PlayerPrefs.GetString('AkagiPlus.Zhangxin.Cosmetics.1.'..id,'')
        if raw~='' then
            local ok,v=pcall(Json.decode,raw)
            if ok and type(v)=='table' and v.schema==1 and type(v.equips)=='table' and type(v.skins)=='table' and type(v.stars)=='table' then s=v end
        end
        if type(s.clearedEquips)~='table' then s.clearedEquips={} end
        s.suits=s.suits or {};s.deletedSuits=s.deletedSuits or {}
        if s.role and s.role.roleID==10020 then s.role=nil end
        A.states[id]=s
    end
    return A.states[id],id
end
local function persist(s,id)
    csharp.PlayerPrefs.SetString('AkagiPlus.Zhangxin.Cosmetics.1.'..id,Json.encode(s))
    csharp.PlayerPrefs.Save();A.states[id]=s
end
-- Restrict local ownership changes to cosmetics; keep currencies and progression intact.
local cosmeticTypes={[13]=true,[14]=true,[15]=true,[16]=true,[17]=true,[18]=true,[19]=true,[20]=true,[22]=true,[24]=true,[25]=true,[26]=true,[30]=true,[36]=true,[37]=true}
local musicTypes={[18]=true,[19]=true,[20]=true,[22]=true}
local wireTypes={[13]='riichi_stick_id',[14]='card_back_id',[15]='tablecloth_id',[16]='special_effect_id',[17]='riichi_effect_id',[19]='game_music_id',[20]='riichi_music_id',[26]='card_face_id',[30]='profile_frame_id',[36]='table_frame_id'}
local function equipType(ty) return cosmeticTypes[ty]==true end
local aliases={
    ['users/getRole']='users/getRoleInfo',['users/getSkin']='users/getSkinInfo',
    ['users/updateRole']='users/updateRoleInfo',['users/wearSkin']='users/roleWearSkin',
    ['users/setRoleStar']='users/addRoleStar',['backpack/itemList']='backpack/userItemList',
    ['backpack/equip']='backpack/equipItem',['backpack/equipList']='backpack/userEquip',
    ['users/titleList']='users/getTitleList',
    ['backpack/equipSuitList']='backpack/userEquipSuit',
    ['backpack/deleteEquipSuit']='backpack/removeEquipSuit',
}
local function route(url) return aliases[url] or url end
local function report(lastRoute)
    pcall(function()
        local value={plugin='ZhangxinPlus',version=A.version,resource_version='92217',loaded=true,reads=A.reads,writes=A.writes,last_route=lastRoute,ai_frames=A.aiSeq or 0,ai_error=A.aiError,last_error=A.lastError,scheme_id_type=A.schemeIdType}
        System.IO.File.WriteAllText(csharp.Util.DataPath..'/zhangxinplus-status.json',Json.encode(value))
    end)
end
local function validRole(id)
    local c=config('role_config')[id]
    return type(id)=='number' and id>=10000 and id<20000 and id~=10020 and c and c.source and c.source>0
end
local function validSkin(role,skin)
    local c=config('role_skin_config')[skin]
    return validRole(role) and (skin==0 or (c and c.role_id==role))
end
local function overlay(v,r,wire)
    if not r then return end
    if wire==true then v.role_id=r.roleID;v.skin_id=r.skinID;v.model=r.model or 0
    elseif wire=='friend' then v.roleId=r.roleID;v.skinId=r.skinID;v.model=r.model or 0
    else v.roleID=r.roleID;v.skinID=r.skinID;v.model=r.model or 0 end
end
local function roles(list,s,requested)
    if type(list)~='table' then return end
    -- 10020 is an alternate-personality record; 1001901 is its selectable skin.
    for i=#list,1,-1 do if list[i].roleID==10020 then table.remove(list,i) end end
    local seen={}
    for _,v in ipairs(list) do
        seen[v.roleID]=true
        if validRole(v.roleID) then
            v.isOwn=true
            if s.stars[tostring(v.roleID)]~=nil then v.isStar=s.stars[tostring(v.roleID)];v.starTime=v.isStar and 1 or 0 end
            local r=s.skins[tostring(v.roleID)];if r then v.recentSkinId=r.skinID;v.model=r.model or 0 end
        end
    end
    for id in pairs(config('role_config')) do
        if validRole(id) and not seen[id] and (not requested or requested==0 or requested==id) then
            local r=s.skins[tostring(id)] or {}
            list[#list+1]={roleID=id,isOwn=true,isCanGet=true,FeelValue=0,cultivateStatus=0,recentSkinId=r.skinID or 0,model=r.model or 0,isStar=s.stars[tostring(id)] or false,starTime=s.stars[tostring(id)] and 1 or 0}
        end
    end
end
local function skins(list,role)
    if type(list)~='table' or not validRole(role) then return end
    local seen={}
    for _,v in ipairs(list) do seen[v.skinID]=true;if validSkin(role,v.skinID) then v.isOwn=true;v.ownemoticon=true end end
    for id,c in pairs(config('role_skin_config')) do
        if c.role_id==role and not seen[id] then list[#list+1]={roleID=role,skinID=id,isOwn=true,ownemoticon=true,model=0} end
    end
end
-- Unlock only the expression preview gate, not the account's cultivation.
function A.installEmoji()
    if not Configuration or type(Configuration.SortEmojiList)~='function' or A.emojiInstalled then return end
    local original=Configuration.SortEmojiList
    Configuration.SortEmojiList=function(data,skins,isAwake,...)
        return original(data,skins,true,...)
    end
    A.emojiInstalled=true
end
-- Optional local observation channel. The companion app explicitly enables it;
-- no auth/HTTP payloads, chat, login tokens or network destinations are copied.
local aiCommands={cmd_enter_room=true,cmd_game_start=true,cmd_send_current_action=true,
    cmd_in_card_brc=true,cmd_game_action_brc=true,cmd_gang_bao_brc=true,
    cmd_game_end=true,cmd_room_end=true}
function A.forwardAI(packet)
    if type(packet)~='table' or not aiCommands[packet.cmd] then return end
    local id=uid();if not id then return end
    local ok,err=pcall(function()
        local root=csharp.Util.DataPath
        local file=System.IO.File
        local controlPath=root..'/zhangxinplus-ai-control.json'
        if not file.Exists(controlPath) then return end
        local control=Json.decode(file.ReadAllText(controlPath))
        if not control or control.enabled~=true or type(control.session)~='string' then return end
        -- Short-lived lease: a crashed/closed app does not keep collecting games.
        if type(control.expires)~='number' or os.time()>control.expires then return end
        if A.aiSession~=control.session then A.aiSession=control.session;A.aiSeq=0 end
        if not A.aiBytes then
            local previous=root..'/zhangxinplus-ai.jsonl'
            A.aiBytes=file.Exists(previous) and #file.ReadAllText(previous) or 0
        end
        A.aiSeq=A.aiSeq+1
        local line=Json.encode({schema=1,session=A.aiSession,instance=A.instance,seq=A.aiSeq,uid=id,
            packet={cmd=packet.cmd,room_id=packet.room_id,data=packet.data}})..'\n'
        -- Bounded queue; rotation occurs at a room boundary, never during a hand.
        local output=root..'/zhangxinplus-ai.jsonl'
        if A.aiBytes and A.aiBytes>4194304 and packet.cmd=='cmd_enter_room' then file.WriteAllText(output,'');A.aiBytes=0 end
        file.AppendAllText(output,line);A.aiBytes=(A.aiBytes or 0)+#line
    end)
    if not ok then A.aiError=tostring(err) end
    if A.aiSeq then report('ai:'..packet.cmd) end
end
-- Ownership and equipped flags are separate in the native bag response.
local function equippedFlag(item,s)
    local c=config('item_config')[item.itemID];if not c then return end
    local key=tostring(c.type);local eq=s.equips[key]
    if s.clearedEquips[key] then item.isEquip=false
    elseif eq then
        item.isEquip=eq.ItemID==item.itemID
        if c.type==37 then
            item.isEquip=false
            for _,id in ipairs(eq.RandItemIDs or {}) do if id==item.itemID then item.isEquip=true;break end end
        end
    end
end
local function suitKey(id) return type(id)=='number' and string.format('%.0f',id) or tostring(id) end
local function validSuitId(id)
    return (type(id)=='number' and id>0 and id<math.huge and id==math.floor(id))
        or (type(id)=='string' and #id>0 and #id<=128)
end
local suitRoutes={['backpack/addEquipSuit']=true,['backpack/editEquipSuit']=true,
    ['backpack/useEquipSuit']=true,['backpack/removeEquipSuit']=true}
local function suitItems(items)
    assert(type(items)=='table','Invalid local scheme')
    local result=copy(items);local roles=0
    for _,v in ipairs(result) do
        local ty=v.ItemType;local item=v.ItemID or 0
        if v.Category==1 then
            roles=roles+1
            assert(validSkin(ty,item),'Invalid scheme role/skin')
            assert(v.Model==nil or v.Model==0 or v.Model==1,'Invalid scheme model')
        else
            assert(v.Category==0 and equipType(ty),'Unsupported scheme category')
            assert(item==0 or (config('item_config')[item] and config('item_config')[item].type==ty),'Invalid scheme item')
        end
        v.IsRand=v.IsRand==true;v.RandItemIDs=v.RandItemIDs or {}
        for _,id in ipairs(v.RandItemIDs) do
            assert((v.Category==1 and validSkin(ty,id)) or (v.Category==0 and config('item_config')[id] and config('item_config')[id].type==ty),'Invalid scheme random pool')
        end
    end
    assert(roles==1,'Scheme must include one role')
    return result
end
local function suitList(list,s)
    list=list or {};local seen={}
    for i=#list,1,-1 do
        local key=suitKey(list[i].id)
        if s.deletedSuits[key] then table.remove(list,i)
        else seen[key]=true;if s.suits[key] then list[i]=copy(s.suits[key]) end end
    end
    for key,v in pairs(s.suits) do if not seen[key] then list[#list+1]=copy(v) end end
    -- The view ignores Use clicks when the server marks locked gear unusable.
    -- Re-evaluate against reviewed local cosmetics, including server schemes.
    for _,record in ipairs(list) do
        local ok,items=pcall(suitItems,record.items)
        record.usable=ok
        if ok then record.items=items end
    end
    return list
end
function A.writeSuit(url,req,s,id)
    A.schemeIdType=type(req.id)
    if url~='backpack/addEquipSuit' then assert(validSuitId(req.id),'Missing scheme ID') end
    local key=suitKey(req.id);local result={code=0,message='ok',data={}}
    if url=='backpack/removeEquipSuit' then s.suits[key]=nil;s.deletedSuits[key]=true
    else
        local previous=s.suits[key]
        if not previous then
            pcall(function()
                local model=GameModules.ModelMgr:GetModel(EModelType.DecoratDesignModel)
                for _,v in ipairs(model:GetDecoratDesignDatas()) do if v.id==req.id then previous=v;break end end
            end)
        end
        local record=copy(previous or {id=req.id,name=req.name or '',items={},createTime=os.time()})
        if url=='backpack/addEquipSuit' then
            s.nextSuitId=math.max(900000000,s.nextSuitId or 900000000)+1
            record.id=s.nextSuitId;key=suitKey(record.id)
            local role=s.role
            if not role then
                role={roleID=player():GetCurRoleID(),skinID=player():GetUseSkinID() or 0,model=player():GetUseModel() or 0}
            end
            record.items={{Category=1,ItemType=role.roleID,ItemID=role.skinID,Model=role.model,IsRand=false,RandItemIDs={}}}
            local bag=GameModules.ModelMgr:GetModel(EModelType.Bagpack)
            for _,eq in ipairs(bag.user_equip_data or {}) do
                if equipType(eq.ItemType) then local v=copy(eq);v.Category=0;record.items[#record.items+1]=v end
            end
        elseif req.items~=nil then record.items=suitItems(req.items) end
        assert(validSuitId(record.id),'Missing scheme ID')
        record.name=req.name or record.name;record.usable=true
        s.suits[key]=record;s.deletedSuits[key]=nil
        if url=='backpack/useEquipSuit' then
            record.items=suitItems(record.items);s.activeSuit=key
            for _,v in ipairs(record.items) do
                if v.Category==1 then
                    local r={roleID=v.ItemType,skinID=v.ItemID or 0,model=v.Model or 0}
                    s.role=r;s.skins[tostring(r.roleID)]=copy(r)
                else
                    local k=tostring(v.ItemType)
                    if v.ItemID==0 then s.equips[k]=nil;s.clearedEquips[k]=true
                    else s.equips[k]=copy(v);s.clearedEquips[k]=nil end
                end
            end
            local usable={}
            pcall(function()
                local model=GameModules.ModelMgr:GetModel(EModelType.DecoratDesignModel)
                for _,v in ipairs(model:GetDecoratDesignDatas()) do usable[tostring(v.id)]=v.usable==true end
            end)
            for k,v in pairs(s.suits) do usable[k]=true;usable[tostring(v.id)]=true end
            result.data={useable=usable}
        else result.data=copy(record) end
    end
    persist(s,id);A.lastError=nil;A.writes=A.writes+1;report(url)
    return result
end
local function inventory(list,req,onlyType,s)
    if type(list)~='table' then return end
    local seen,ids={},nil
    if req.itemsID then ids={};for _,id in ipairs(req.itemsID) do ids[id]=true end end
    for _,v in ipairs(list) do
        seen[v.itemID]=true;local c=config('item_config')[v.itemID]
        if c and equipType(c.type) and (not onlyType or c.type==onlyType) then v.num=math.max(1,tonumber(v.num) or 0);v.expiredAt=0;v.isExpired=false end
    end
    for id,c in pairs(config('item_config')) do
        if equipType(c.type) and (not onlyType or c.type==onlyType) and not seen[id] and (not req.itemType or req.itemType==c.type) and (not ids or ids[id]) then
            list[#list+1]={itemID=id,itemType=c.type,num=1,expiredAt=0,isExpired=false,isNew=false,label=0}
        end
    end
    for _,v in ipairs(list) do equippedFlag(v,s) end
end
local function equips(list,s)
    if type(list)~='table' then return end
    for i=#list,1,-1 do if s.clearedEquips[tostring(list[i].ItemType)] then table.remove(list,i) end end
    for ty,v in pairs(s.equips) do
        local found=false
        for i,eq in ipairs(list) do if eq.ItemType==tonumber(ty) then list[i]=copy(v);found=true;break end end
        if not found then list[#list+1]=copy(v) end
    end
end
-- The bag renders inventory and equipment responses independently. Reapply the
-- local selection before either callback can render a stale server snapshot.
function A.syncCache()
    local s=state();if not s then return end
    pcall(function()
        local bag=GameModules.ModelMgr:GetModel(EModelType.Bagpack)
        bag.user_equip_data=bag.user_equip_data or {}
        equips(bag.user_equip_data,s)
        for _,v in pairs(bag.item_id_to_info or {}) do equippedFlag(v,s) end
        for _,v in ipairs(bag.show_items or {}) do equippedFlag(v,s) end
    end)
end
local function profile(v,s,style)
    overlay(v,s.role,style)
    local frame=s.equips['30']
    if style==true then
        if frame then v.profile_frame_id=frame.ItemID end
        if s.titleID~=nil then v.title_id=s.titleID end
    else
        if frame then v.profileFrameID=frame.ItemID end
        if s.titleID~=nil then v.titleID=s.titleID end
    end
end
local function selfFriend(v,s,owner)
    if type(v)=='table' and tostring(v.userID or owner)==uid() then profile(v,s,'friend') end
end
local function titles(list,s)
    if type(list)~='table' then return end
    local seen={}
    for _,v in ipairs(list) do
        seen[v.titleID]=true
        if s.titleID~=nil then v.titleState=v.titleID==s.titleID and 2 or 1
        elseif v.titleState~=2 then v.titleState=1 end
        v.expiredAt=0
    end
    for id,c in pairs(config('title_config')) do
        if type(id)=='number' and not seen[id] then list[#list+1]={titleID=id,titleState=id==s.titleID and 2 or 1,expiredAt=0,type=c.type,ownerDisplay=c.display==1} end
    end
end
function A.read(url,req,response)
    A.installEmoji()
    url=route(url)
    if type(response)~='table' or response.code~=0 then return response end
    local s=state();if not s then return response end
    local ret=copy(response);local d=ret.data;req=req or {}
    if url=='users/getRoleInfo' and type(d)=='table' then
        roles(d.roleList,s,req.roleID)
        if s.role then d.useRoleID=s.role.roleID;d.useSkinID=s.role.skinID;d.model=s.role.model;d.useModel=s.role.model end
    elseif url=='users/getRoleAndSkin' and type(d)=='table' then
        roles(d.roleList,s,req.roleID);skins(d.skinList,req.roleID)
        if d.roleInfo and validRole(d.roleInfo.roleID) then d.roleInfo.isOwn=true end
    elseif url=='users/getSkinInfo' then skins(d,req.roleID)
    elseif url=='users/homeUserData' and type(d)=='table' then profile(d,s)
    elseif url=='users/userBaseData' and tostring(req.userID)==uid() and type(d)=='table' then profile(d,s)
    elseif url=='backpack/userItemList' then inventory(d,req,nil,s)
    elseif url=='backpack/userEquip' then equips(d,s)
    elseif url=='backpack/userProfileFrame' then inventory(d,req,30,s)
    elseif url=='users/getTitleList' then titles(d,s)
    elseif url=='backpack/userEquipSuit' then ret.list=suitList(ret.list,s)
    elseif url=='lobbys/createFriendMatch' or url=='lobbys/enterFriendMatch' or url=='lobbys/getFriendMatchInfo' then
        if type(d)=='table' then for _,v in ipairs(d.players or {}) do selfFriend(v,s) end end
    end
    A.syncCache()
    A.reads=A.reads+1;report(url)
    return ret
end
local setters={['users/updateRoleInfo']=true,['users/roleWearSkin']=true,['users/addRoleStar']=true,['backpack/equipItem']=true,['backpack/unloadEquip']=true,['users/updateTitle']=true}
function A.write(url,req)
    url=route(url)
    if not setters[url] and not suitRoutes[url] then return end
    req=req or {}
    local c=config('item_config')[req.itemID]
    local ty=c and c.type or req.itemType
    if url=='backpack/equipItem' or url=='backpack/unloadEquip' then
        if not equipType(ty) then return end
    end
    local original,id=state();assert(original and id,'No active game account')
    local s=copy(original)
    if suitRoutes[url] then return A.writeSuit(url,req,s,id)
    elseif url=='users/updateTitle' then
        assert(req.titleID==0 or config('title_config')[req.titleID],'Unknown local title');s.titleID=req.titleID
    elseif url=='users/addRoleStar' then
        assert(validRole(req.roleID),'Unknown local role');s.stars[tostring(req.roleID)]=req.isSet==true
    elseif url=='users/updateRoleInfo' or url=='users/roleWearSkin' then
        local skin=req.skinID or 0
        assert(validSkin(req.roleID,skin),'Unknown local skin')
        assert(req.model==nil or req.model==0 or req.model==1,'Unknown model')
        local r={roleID=req.roleID,skinID=skin,model=req.model or 0};s.skins[tostring(req.roleID)]=r
        if url=='users/updateRoleInfo' or (s.role and s.role.roleID==req.roleID) then s.role=copy(r) end
    else
        local key=tostring(ty)
        if url=='backpack/unloadEquip' then
            s.equips[key]=nil;s.clearedEquips[key]=true
        else
            local old=s.equips[key]
            if not old then
                pcall(function() old=GameModules.ModelMgr:GetModel(EModelType.Bagpack):GetEquipInfo(ty) end)
            end
            local eq=copy(old or {ItemType=ty,IsRand=false})
            local ids=req.emojiIDs or req.modeItemIds
            if ids~=nil then
                assert(type(ids)=='table','Invalid local list')
                for _,id in ipairs(ids) do
                    local item=config('item_config')[id]
                    assert((ty==37 and id==0) or (item and item.type==ty),'Invalid local equip list')
                end
                eq.RandItemIDs=copy(ids)
            end
            if req.itemID~=nil then assert(c and c.type==ty,'Unknown local equip');eq.ItemID=req.itemID end
            if req.mode~=nil then assert(musicTypes[ty] and req.mode>=1 and req.mode<=3,'Invalid music mode');eq.Mode=req.mode end
            if not eq.ItemID then eq.ItemID=(eq.RandItemIDs or {})[1] end
            assert(eq.ItemID and config('item_config')[eq.ItemID],'Missing local equip')
            eq.RandItemIDs=eq.RandItemIDs or {eq.ItemID}
            if musicTypes[ty] then eq.Mode=eq.Mode or 1 end
            s.equips[key]=eq;s.clearedEquips[key]=nil
        end
    end
    persist(s,id);A.lastError=nil;A.writes=A.writes+1;report(url)
    return {code=0,message='ok',data={}}
end
function A.onMessage(packet)
    A.installEmoji()
    A.forwardAI(packet)
    if type(packet)~='table' or type(packet.data)~='table' then return end
    if packet.cmd~='cmd_enter_room' and packet.cmd~='cmd_friend_match_action' then return end
    local s=state();if not s then return end
    if packet.cmd=='cmd_enter_room' then
        for _,p in ipairs(packet.data.players or {}) do
            local u=p.user
            if u and tostring(u.user_id)==uid() then
                profile(u,s,true)
                for ty,eq in pairs(s.equips) do local field=wireTypes[tonumber(ty)];if field then u[field]=eq.ItemID end end
            end
        end
    else
        selfFriend(packet.data.player,s,packet.data.userID)
        for _,v in ipairs(packet.data.players or {}) do selfFriend(v,s) end
    end
end
function A.install(http)
    if http.__akagiplus_zhangxin then return end
    http.__akagiplus_zhangxin=true;local original=http.MjGamePost
    http.MjGamePost=function(url,data,callback,params,...)
        if setters[route(url)] or suitRoutes[route(url)] then
            local ok,ret=pcall(A.write,url,data)
            if not ok then
                A.lastError={route=route(url),reason=tostring(ret)}
                report(route(url));print('[ZhangxinPlus] local selection failed: '..route(url)..': '..tostring(ret))
                if suitRoutes[route(url)] then
                    -- Native scheme callbacks assume success and index useable.
                    -- Never call them with an error-shaped response.
                    pcall(function() CommonHelper.ShowTips('本地装扮方案应用失败，请查看日志。') end)
                    return
                end
                ret={code=1,message='AkagiPlus local cosmetic selection failed',data={}}
            end
            if ret then A.syncCache();if callback then callback(ret,params) end;A.syncCache();return end
        end
        if not callback then return original(url,data,callback,params,...) end
        return original(url,data,function(ret,...)
            local ok,value=pcall(A.read,url,data,ret)
            return callback(ok and value or ret,...)
        end,params,...)
    end
    A.installEmoji()
    report('loaded');print('[ZhangxinPlus] loaded '..A.version..' / resources 92217')
end
_G.ZhangxinPlus=A
return A
