# Adapted for AkagiPlus on 2026-11-05; GPL-3.0; see ../../PROVENANCE.md.
# Modified for MahjongCopilotPlus on 2026-11-03; see NOTICE.md.
from majsoulmax import wire as liqi
import random
from ruamel.yaml import YAML
import logging
logger = logging.getLogger("majsoulmax")
from struct import unpack
from majsoulmax.proto import liqi_pb2, basic_pb2
from majsoulmax.paths import CONFIG, DATA
from majsoulmax.validation import validate_max_data
from copy import deepcopy
from google.protobuf import json_format



class mod:
    def __init__(self,version):
        self.version = version
        self.safe = {'account_id': 0, 'characters': [], 'main_character_id': 0}
        self.contract = ''
        self.yaml = YAML()
        self.max_data = {}
        self.LoadSettings()
        logger.info('已载入mod')

    def LoadSettings(self):
        self.settings = self.yaml.load('''\
# 需要自定义的配置主要集中在这里，大多数无需修改，在游戏内设置即可更新
config:
  character: 200001  # 当前看板娘
  characters: {}  # 各角色使用的皮肤
  nickname: '' # 自定义你的名字
  star_chars: [] # 星标角色
  bianjietishi: false # 强制启用便捷提示，用于部分场没有宝牌指示、和牌指示等
  title: 0  # 当前使用的称号
  loading_image: [] # 加载CG
  emoji: false # 不建议开启，用于解锁角色全部emoji，如果你本身角色没有额外表情，在对局中却发送额外表情，这种行为相当于自爆卡车
  views: # 各装扮页的装扮
    0: []
    1: []
    2: []
    3: []
    4: []
    5: []
    6: []
    7: []
    8: []
    9: []
  views_index: 0 # 正在使用的装扮页
  show_server: false # 显示其他玩家所在服务器
  verified: 0 # 标识设置，0为无标识，1为主播标识，2为Pro标识，显示在名字后面
  anti_replace_nickname: true # 禁止将外服玩家设为默认名称，特殊时期必备
  random_character: # 对局随机角色皮肤
    enabled: false
    pool: []
  safe_mode: false  # 地铁模式，将除自己外所有人变成一姬初始形象，防止被误认为玩黄油。电脑形象请打开“游戏设置-偏好-电脑形象-一姬的初始形象”选项。
''')
        try:
            with open(CONFIG / 'settings.mod.yaml', 'r', encoding='utf-8') as f:
                temp = YAML()
                localyaml = temp.load(f)
                self.settings['config'].update(localyaml.get('config', {}))
        except FileNotFoundError:
            logger.info("Created private MajsoulMax settings")
        self.load_max_data()
        self.SaveSettings()

    def SaveSettings(self):
        import io, os, tempfile
        text = io.StringIO()
        self.yaml.dump(self.settings, text)
        blob = text.getvalue()
        path = CONFIG / 'settings.mod.yaml'
        if path.exists() and path.read_text(encoding='utf-8') == blob:
            return
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=CONFIG, delete=False) as f:
            temp = f.name
            f.write(blob)
        try:
            os.replace(temp, path)
        finally:
            if os.path.exists(temp): os.unlink(temp)

    def load_max_data(self):
        self.max_data = validate_max_data((DATA / 'max_data.yaml').read_bytes())
        config = self.settings['config']
        skins = set(self.max_data['skin'])
        for character in self.max_data['character']:
            default = int('40' + str(character)[4:] + '01')
            if config['characters'].get(character) not in skins and default in skins:
                config['characters'][character] = default
        if config['character'] not in self.max_data['character']:
            logger.warning('当前角色已不在资源表中，恢复默认角色')
            config['character'] = self.max_data['character'][0]

    def _rewrite_room_player(self, player):
        """Keep the local room appearance and voice identity in the same record.

        Ready notifications contain no character; the client reuses room player
        data. Never replace the entire Character message: retain future fields.
        """
        config = self.settings['config']
        account_id = self.safe.get('account_id', 0)
        own_player = bool(account_id) and player.account_id == account_id
        if own_player:
            character = config['character']
            player.avatar_id = player.character.skin = config['characters'][character]
            player.character.charid = character
            player.character.is_upgraded, player.character.level = True, 5
            player.character.exp = 0
            player.character.ClearField('rewarded_level')
            player.character.rewarded_level.extend([1, 2, 3, 4, 5])
            player.character.ClearField('extra_emoji')
            if config['emoji']:
                player.character.extra_emoji.extend(self.max_data['emoji'].get(character, []))
            if config['nickname']:
                player.nickname = config['nickname']
            player.title, player.verified = config['title'], config['verified']
            player.character.ClearField('views')
            for view in config['views'][config['views_index']]:
                json_format.ParseDict(view, player.character.views.add())
        elif config['safe_mode']:
            player.character.charid = 200001
            player.avatar_id = player.character.skin = 400101
        if config['show_server']:
            player.nickname = self.get_zone_id(player.account_id) + player.nickname


    def main(self, message, liqi_proto):
        modify = False
        drop = False
        fake = False
        msg = b''
        inject = False
        inject_msg = b''
        from_client = message.from_client
        buf = message.content
        if not buf or buf[0] not in (1, 2, 3):
            return modify, drop, msg, inject, inject_msg
        msg_type = liqi.MsgType(buf[0])
        msg_block = basic_pb2.BaseMessage()
        if msg_type == liqi.MsgType.NOTIFY:
            # Notify没有msg_id
            msg_block.ParseFromString(buf[1:])
            method_name = msg_block.method_name
            match method_name:
                case '.lq.NotifyAccountUpdate':
                    data = liqi_pb2.NotifyAccountUpdate()
                    data.ParseFromString(msg_block.data)
                    if data.update.HasField('character'):
                        drop = True
                case '.lq.NotifyRoomPlayerUpdate':
                    modify = True
                    data = liqi_pb2.NotifyRoomPlayerUpdate()
                    data.ParseFromString(msg_block.data)
                    for player in data.player_list:
                        self._rewrite_room_player(player)
                case '.lq.NotifyGameFinishRewardV2':
                    modify = True
                    data = liqi_pb2.NotifyGameFinishRewardV2()
                    data.ParseFromString(msg_block.data)
                    for c in self.safe['characters']:
                        if c.charid == self.safe['main_character_id']:
                            c.exp = data.main_character.exp
                            c.level = data.main_character.level
                            break
                    data.main_character.add = 0
                    data.main_character.exp = 0
                    data.main_character.level = 5
                case '.lq.NotifyCustomContestSystemMsg':
                    if self.settings['config']['show_server']:
                        modify = True
                        data = liqi_pb2.NotifyCustomContestSystemMsg()
                        data.ParseFromString(msg_block.data)
                        for p in data.game_start.players:
                            p.nickname =self.get_zone_id(p.account_id)+p.nickname
                case '.lq.NotifyAnnouncementUpdate':
                    modify = True
                    data = liqi_pb2.NotifyAnnouncementUpdate()
                    data.ParseFromString(msg_block.data)
                    
        else:
            msg_id = unpack('<H', buf[1:3])[0]
            msg_block.ParseFromString(buf[3:])
            if msg_type == liqi.MsgType.REQ:
                # Req类型必定是客户端发出的消息
                assert (from_client)
                assert (msg_id < 1 << 16)
                # assert (len(msg_block) == 2)
                assert (msg_id not in liqi_proto.res_type)
                method_name = msg_block.method_name
                # 根据method_name判断是否需要修改
                match method_name:
                    case '.lq.Lobby.changeMainCharacter':  # 修改看板娘
                        fake = True
                        data = liqi_pb2.ReqChangeMainCharacter()
                        data.ParseFromString(msg_block.data)
                        self.settings['config']['character'] = data.character_id
                        self.SaveSettings()
                    case '.lq.Lobby.changeCharacterSkin':  # 修改角色皮肤
                        fake = True
                        inject = True
                        data = liqi_pb2.ReqChangeCharacterSkin()
                        data.ParseFromString(msg_block.data)
                        # 保存角色和皮肤
                        self.settings['config']['characters'][data.character_id] = data.skin
                        self.SaveSettings()
                        update_data = liqi_pb2.NotifyAccountUpdate()
                        character = update_data.update.character.characters.add()
                        character.charid = data.character_id
                        character.skin = data.skin
                        character.exp = 0
                        character.is_upgraded = True
                        character.level = 5
                        character.rewarded_level.extend([1, 2, 3, 4, 5])
                        if self.settings['config']['emoji']:
                            character.extra_emoji.extend(
                                self.max_data['emoji'].get(character.charid, []))

                        basic = basic_pb2.BaseMessage()
                        basic.method_name = '.lq.NotifyAccountUpdate'
                        basic.data = update_data.SerializeToString()
                        inject_msg = b'\x01' + basic.SerializeToString()
                    case '.lq.Lobby.addFinishedEnding':  # 角色传记
                        drop = True
                    case '.lq.Lobby.updateCharacterSort':  # 角色星标
                        fake = True
                        data = liqi_pb2.ReqUpdateCharacterSort()
                        data.ParseFromString(msg_block.data)
                        # 保存星标角色
                        self.settings['config']['star_chars'] = list(data.sort)
                        self.SaveSettings()
                    case '.lq.Lobby.useTitle':  # 使用称号
                        fake = True
                        data = liqi_pb2.ReqUseTitle()
                        data.ParseFromString(msg_block.data)
                        self.settings['config']['title'] = data.title
                        self.SaveSettings()
                    case '.lq.Lobby.setLoadingImage':  # 加载CG
                        fake = True
                        data = liqi_pb2.ReqSetLoadingImage()
                        data.ParseFromString(msg_block.data)
                        # self.safe['loading_image'] = []
                        self.settings['config']['loading_image'] = list(
                            data.images)
                        self.SaveSettings()
                    case '.lq.Lobby.saveCommonViews':  # 保存装扮
                        fake = True
                        modify = True
                        data = liqi_pb2.ReqSaveCommonViews()
                        data.ParseFromString(msg_block.data)
                        for view in data.views:
                            if view.type == 0 and view.item_id_list != []:
                                view.ClearField('item_id_list')
                            elif view.type == 1 and view.item_id != 0:
                                view.ClearField('item_id')

                        views = json_format.MessageToDict(
                            data, including_default_value_fields=True, preserving_proto_field_name=True)
                        self.settings['config']['views'][views['save_index']
                                                         ] = views['views']
                        if views['is_use'] == 1:
                            self.settings['config']['views_index'] = views['save_index']
                        self.SaveSettings()
                    case '.lq.Lobby.useCommonView':  # 修改装扮页
                        data = liqi_pb2.ReqUseCommonView()
                        data.ParseFromString(msg_block.data)
                        self.settings['config']['views_index'] = data.index
                        self.SaveSettings()
                    case '.lq.Lobby.loginBeat':
                        data = liqi_pb2.ReqLoginBeat()
                        data.ParseFromString(msg_block.data)
                        self.contract = data.contract
                    case '.lq.Lobby.readAnnouncement':
                        data = liqi_pb2.ReqReadAnnouncement()
                        data.ParseFromString(msg_block.data)
                        if data.announcement_id == 666666:
                            fake = True
                    case '.lq.Lobby.receiveCharacterRewards':
                        fake = True
                    case '.lq.Lobby.setRandomCharacter':
                        fake = True
                        data = liqi_pb2.ReqRandomCharacter()
                        data.ParseFromString(msg_block.data)
                        self.settings['config']['random_character']['enabled'] = data.enabled
                        self.settings['config']['random_character']['pool'] = json_format.MessageToDict(data, including_default_value_fields=True, preserving_proto_field_name=True)['pool']
                        self.SaveSettings()


                if fake:
                    modify = True
                    data = liqi_pb2.ReqLoginBeat()
                    data.contract = self.contract
                    msg_block.method_name = '.lq.Lobby.loginBeat'
            elif msg_type == liqi.MsgType.RES:
                # Res类型必定是客户端收到的消息
                assert (not from_client)
                assert (len(msg_block.method_name) == 0)
                assert (msg_id in liqi_proto.res_type)
                method_name, liqi_pb2_res = liqi_proto.res_type[msg_id]
                response = liqi_pb2_res.FromString(msg_block.data)
                if 'error' in response.DESCRIPTOR.fields_by_name and response.error.code:
                    return modify, drop, msg, inject, inject_msg
                # 根据method_name判断是否需要修改
                match method_name:
                    case '.lq.Lobby.fetchCharacterInfo':  # 获取角色和皮肤信息
                        modify = True
                        data = liqi_pb2.ResCharacterInfo()
                        data.ParseFromString(msg_block.data)
                        self.safe['main_character_id'] = data.main_character_id
                        self.safe['characters'] = deepcopy(list(data.characters))
                        # self.safe['skins'] = data.skins
                        # self.safe['character_sort'] = data.character_sort
                        # START
                        data.ClearField('characters')
                        character_keys = self.settings['config']['characters'].keys(
                        )
                        for c in self.max_data['character']:
                            character = data.characters.add()
                            character.charid = c
                            character.exp = 0
                            character.is_upgraded = True
                            character.level = 5
                            character.rewarded_level.extend([1, 2, 3, 4, 5])
                            if c not in character_keys:
                                self.settings['config']['characters'][c] = int(
                                    '40'+str(c)[4:]+'01')
                            character.skin = self.settings['config']['characters'][c]
                            if self.settings['config']['emoji']:
                                character.extra_emoji.extend(
                                    self.max_data['emoji'].get(character.charid, []))
                        data.ClearField('skins')
                        data.skins.extend(self.max_data['skin'])
                        data.main_character_id = self.settings['config']['character']
                        data.ClearField('character_sort')
                        data.character_sort.extend(
                            self.settings['config']['star_chars'])
                        data.ClearField('hidden_characters')
                        data.ClearField('finished_endings')
                        data.ClearField('rewarded_endings')
                        data.finished_endings.extend(
                            self.max_data['endings'])
                        data.rewarded_endings.extend(
                            self.max_data['endings'])
                    case '.lq.Lobby.login' | '.lq.Lobby.oauth2Login':  # 登录时

                        modify = True
                        data = liqi_pb2.ResLogin()
                        data.ParseFromString(msg_block.data)
                        self.safe['account_id'] = data.account_id
                        self.safe['nickname'] = data.account.nickname
                        self.safe['skin'] = data.account.avatar_id
                        self.safe['title'] = data.account.title
                        self.safe['loading_image'] = list(data.account.loading_image)
                        # START
                        if self.settings['config']['character'] in self.settings['config']['characters'].keys():
                            data.account.avatar_id = self.settings['config'][
                                'characters'][self.settings['config']['character']]
                        else:
                            data.account.avatar_id = int(
                                '40'+str(self.settings['config']['character'])[4:]+'01')
                        for view in self.settings['config']['views'][self.settings['config']['views_index']]:
                            if view['slot'] == 5:
                                data.account.avatar_frame = view['item_id']
                        if self.settings['config']['nickname'] != '':
                            data.account.nickname = self.settings['config']['nickname']
                        data.account.title = self.settings['config']['title']
                        data.account.ClearField('loading_image')
                        data.account.loading_image.extend(
                            self.settings['config']['loading_image'])
                        data.account.verified = self.settings['config']['verified']
                    case '.lq.Lobby.createRoom' | '.lq.Lobby.joinRoom' | '.lq.Lobby.fetchRoom':
                        modify = True
                        data = liqi_pb2_res()
                        data.ParseFromString(msg_block.data)
                        for player in data.room.persons:
                            self._rewrite_room_player(player)
                    case '.lq.FastTest.authGame':  # 进入麻将桌
                        modify = True
                        data = liqi_pb2.ResAuthGame()
                        data.ParseFromString(msg_block.data)
                        if self.settings['config']['bianjietishi']:
                            data.game_config.mode.detail_rule.bianjietishi = True
                            if data.game_config.meta.mode_id == 15 :
                                data.game_config.meta.mode_id =11
                            elif data.game_config.meta.mode_id == 16:
                                data.game_config.meta.mode_id =12
                            elif data.game_config.meta.mode_id == 25:
                                data.game_config.meta.mode_id =23
                            elif data.game_config.meta.mode_id == 26:
                                data.game_config.meta.mode_id =24
                    
                        for p in data.players:
                            p.character.level = 5
                            p.character.is_upgraded = True
                            p.character.rewarded_level.extend([1, 2, 3, 4, 5])
                            p.character.exp = 0
                            if p.account_id == self.safe['account_id']:
                                if self.settings['config']['random_character']['enabled'] and self.settings['config']['random_character']['pool']!=[]: # 处理随机角色
                                    item = random.choice(self.settings['config']['random_character']['pool'])
                                    p.character.charid = item['character_id']
                                    p.avatar_id = p.character.skin = item['skin_id']
                                else:
                                    p.character.charid = self.settings['config']['character']
                                    p.avatar_id = p.character.skin = self.settings['config']['characters'][self.settings['config']['character']]
                                if self.settings['config']['emoji']:
                                    p.character.extra_emoji.extend(
                                        self.max_data['emoji'].get(p.character.charid, []))
                                if self.settings['config']['nickname'] != '':
                                    p.nickname = self.settings['config']['nickname']
                                p.title = self.settings['config']['title']
                                p.ClearField('views')
                                for view in self.settings['config']['views'][self.settings['config']['views_index']]:
                                    view_slot = p.views.add()
                                    #json_format.ParseDict(view, view_slot)
                                    view_slot.slot = view['slot']
                                    if view['type'] == 0: # 非随机装扮
                                        view_slot.item_id = view['item_id']
                                    else: # 随机装扮，要自己抽
                                        view_slot.item_id = random.choice(view['item_id_list'])
                                    if view['slot'] == 5:
                                        p.avatar_frame = view['item_id']
                                p.verified = self.settings['config']['verified']

                            if self.settings['config']['show_server']:
                                p.nickname =self.get_zone_id(p.account_id)+p.nickname
                            if self.settings['config']['safe_mode'] and p.account_id != self.safe['account_id']:
                                p.character.charid=200001
                                p.character.skin=400101
                                p.avatar_id= 400101
                        for p in data.robots:
                            p.character.level = 5
                            p.character.is_upgraded = True
                            p.character.rewarded_level.extend([1, 2, 3, 4, 5])
                            p.character.exp = 0
                            if self.settings['config']['safe_mode'] and p.account_id != self.safe['account_id']:
                                p.character.charid=200001
                                p.character.skin=400101
                                p.avatar_id= 400101
                    case '.lq.Lobby.fetchAccountInfo':  # 个人信息页和游戏结束
                        data = liqi_pb2.ResAccountInfo()
                        data.ParseFromString(msg_block.data)
                        if data.account.account_id == self.safe['account_id']:
                            modify = True
                            data.account.avatar_id = self.settings['config'][
                                'characters'][self.settings['config']['character']]
                            for view in self.settings['config']['views'][self.settings['config']['views_index']]:
                                if view['slot'] == 5:
                                    data.account.avatar_frame = view['item_id']
                            if self.settings['config']['nickname'] != '':
                                data.account.nickname = self.settings['config']['nickname']
                            data.account.title = self.settings['config']['title']
                            data.account.ClearField('loading_image')
                            data.account.loading_image.extend(
                                self.settings['config']['loading_image'])
                            data.account.verified = self.settings['config']['verified']
                        # if self.settings['config']['show_server']:
                        #     match self.get_zone_id(data.account.account_id):
                        #         case 0:
                        #             data.account.nickname = '[C' + b'\xef\xbb\xbf'.decode('utf-8') +'N]'+data.account.nickname
                        #         case 1:
                        #             data.account.nickname = '[JP]'+data.account.nickname
                        #         case 3:
                        #             data.account.nickname = '[EN]'+data.account.nickname
                        #         case _:
                        #             data.account.nickname = '[??]'+data.account.nickname
                    case '.lq.Lobby.fetchTitleList':  # 获取称号列表
                        modify = True
                        data = liqi_pb2.ResTitleList()
                        data.ParseFromString(msg_block.data)
                        # self.safe['title_list'] = data.title_list
                        data.ClearField('title_list')
                        data.title_list.extend(self.max_data['title'])
                    case '.lq.Lobby.fetchBagInfo':  # 获取背包
                        modify = True
                        data = liqi_pb2.ResBagInfo()
                        data.ParseFromString(msg_block.data)
                        self.safe['items'] = deepcopy(list(data.bag.items))
                        data.bag.ClearField('items')
                        # 添加原背包物品
                        for item in self.safe['items']:
                            if item.item_id not in self.max_data['item']:
                                myitem = data.bag.items.add()
                                myitem.item_id = item.item_id
                                myitem.stack = item.stack
                        # 添加其他物品
                        for id in self.max_data['item']:
                            item = data.bag.items.add()
                            item.item_id = id
                            item.stack = 1
                        # 添加加载插图
                        for id in self.max_data['loading_image']:
                            item = data.bag.items.add()
                            item.item_id = id
                            item.stack = 1
                    case '.lq.Lobby.fetchAllCommonViews':  # 获取装扮
                        modify = True
                        data = liqi_pb2.ResAllcommonViews()
                        data.use = self.settings['config']['views_index']
                        for i, view in self.settings['config']['views'].items():
                            views = data.views.add()
                            json_format.ParseDict(
                                {'index': i, 'values': view}, views)
                    case '.lq.Lobby.fetchAnnouncement':
                        modify = True
                        data = liqi_pb2.ResAnnouncement()
                        data.ParseFromString(msg_block.data)
                        MyAnnouncement = liqi_pb2.Announcement()
                        MyAnnouncement.title = '雀魂MAX载入成功'
                        MyAnnouncement.id = 666666
                        MyAnnouncement.header_image = 'internal://2.jpg'
                        MyAnnouncement.content = f'<color=#f9963b>作者：Avenshy        版本：{self.version}</color>\n\
<b>MahjongCopilotPlus 集成版；代码及第三方组件许可见项目仓库。</b>\n\
<b>请遵守游戏平台规则；使用修改工具可能导致账号处罚。</b>\n\n\
<color=#f9963b>开源地址：</color>\n\
<href=https://github.com/Avenshy/MajsoulMax>https://github.com/Avenshy/MajsoulMax</href>\n\n\
<color=#f9963b>请作者喝咖啡：</color>\n\
<href=https://afdian.net/a/Avenshy>爱发电，支持支付宝、微信</href>\n\
<href=https://patreon.com/Avenshy>Patreon，支持Paypal、信用卡</href>\n\
<color=#f9963b>再次重申：脚本完全免费使用，没有收费功能，请喝咖啡完全自愿，作者非常感谢您！</color>'
                        data.announcements.insert(0, MyAnnouncement)
                    case '.lq.Lobby.fetchInfo':  # 网页版特殊处理
                        modify = True
                        data = liqi_pb2.ResFetchInfo()
                        data.ParseFromString(msg_block.data)
                        
                        # 处理角色和皮肤
                        self.safe['main_character_id'] = data.character_info.main_character_id
                        self.safe['characters'] = deepcopy(list(data.character_info.characters))
                        data.character_info.ClearField('characters')
                        character_keys = self.settings['config']['characters'].keys(
                        )
                        for c in self.max_data['character']:
                            character = data.character_info.characters.add()
                            character.charid = c
                            character.exp = 0
                            character.is_upgraded = True
                            character.level = 5
                            character.rewarded_level.extend([1, 2, 3, 4, 5])
                            if c not in character_keys:
                                self.settings['config']['characters'][c] = int(
                                    '40'+str(c)[4:]+'01')
                            character.skin = self.settings['config']['characters'][c]
                            if self.settings['config']['emoji']:
                                character.extra_emoji.extend(
                                    self.max_data['emoji'].get(character.charid, []))
                        data.character_info.ClearField('skins')
                        data.character_info.skins.extend(
                            self.max_data['skin'])
                        data.character_info.main_character_id = self.settings['config']['character']
                        data.character_info.ClearField('character_sort')
                        data.character_info.character_sort.extend(
                            self.settings['config']['star_chars'])
                        data.character_info.ClearField('hidden_characters')
                        data.character_info.ClearField('finished_endings')
                        data.character_info.ClearField('rewarded_endings')
                        data.character_info.finished_endings.extend(
                            self.max_data['endings'])
                        data.character_info.rewarded_endings.extend(
                            self.max_data['endings'])

                        # 处理背包
                        self.safe['items'] = deepcopy(list(data.bag_info.bag.items))
                        data.bag_info.bag.ClearField('items')
                        # 添加原背包物品
                        for item in self.safe['items']:
                            if item.item_id not in self.max_data['item']:
                                myitem = data.bag_info.bag.items.add()
                                myitem.item_id = item.item_id
                                myitem.stack = item.stack
                        # 添加其他物品
                        for id in self.max_data['item']:
                            item = data.bag_info.bag.items.add()
                            item.item_id = id
                            item.stack = 1
                        # 添加加载插图
                        for id in self.max_data['loading_image']:
                            item = data.bag_info.bag.items.add()
                            item.item_id = id
                            item.stack = 1

                        # 处理装扮
                        data.ClearField('all_common_views')
                        data.all_common_views.use = self.settings['config']['views_index']
                        for i, view in self.settings['config']['views'].items():
                            views = data.all_common_views.views.add()
                            json_format.ParseDict(
                                {'index': i, 'values': view}, views)
                        # 处理称号
                        data.ClearField('title_list')
                        data.title_list.title_list.extend(self.max_data['title'])
                        # 处理随机角色皮肤
                        data.ClearField('random_character')
                        json_format.ParseDict(self.settings['config']['random_character'],data.random_character)


                    case '.lq.Lobby.fetchServerSettings':
                        data = liqi_pb2.ResServerSettings()
                        data.ParseFromString(msg_block.data)
                        if self.settings['config']['anti_replace_nickname']:
                            modify = True
                            data.settings.nickname_setting.enable = 0
                            data.settings.nickname_setting.ClearField(
                                'nicknames')
                    case '.lq.Lobby.fetchGameRecord':
                        modify = True
                        data = liqi_pb2.ResGameRecord()
                        data.ParseFromString(msg_block.data)
                        uuid = data.head.uuid
                        result = '发现读入牌谱！\n'
                        for account in data.head.accounts:
                            match account.seat:
                                case 0:
                                    result+='東: '
                                case 1:
                                    result+='南: '
                                case 2:
                                    result+='西: '
                                case 3:
                                    result+='北: '
                            account.character.level = 5
                            account.character.is_upgraded = True
                            account.character.rewarded_level.extend([1, 2, 3, 4, 5])
                            account.character.exp = 0
                            if account.account_id == self.safe['account_id']:
                                result+='（自己）'
                                if self.settings['config']['random_character']['enabled'] and self.settings['config']['random_character']['pool']!=[]: # 处理随机角色
                                    item = random.choice(self.settings['config']['random_character']['pool'])
                                    account.character.charid = item['character_id']
                                    account.avatar_id = account.character.skin = item['skin_id']
                                else:
                                    account.character.charid = self.settings['config']['character']
                                    account.avatar_id = account.character.skin = self.settings['config']['characters'][self.settings['config']['character']]

                                if self.settings['config']['emoji']:
                                    account.character.extra_emoji.extend(
                                        self.max_data['emoji'].get(account.character.charid, []))
                                if self.settings['config']['nickname'] != '':
                                    account.nickname = self.settings['config']['nickname']
                                account.title = self.settings['config']['title']
                                account.ClearField('views')
                                for view in self.settings['config']['views'][self.settings['config']['views_index']]:
                                    view_slot = account.views.add()
                                    #json_format.ParseDict(view, view_slot)
                                    view_slot.slot = view['slot']
                                    if view['type'] == 0: # 非随机装扮
                                        view_slot.item_id = view['item_id']
                                    else: # 随机装扮，要自己抽
                                        view_slot.item_id = random.choice(view['item_id_list'])
                                    if view['slot'] == 5:
                                        account.avatar_frame = view['item_id']
                                account.verified = self.settings['config']['verified']
                            elif self.settings['config']['safe_mode']:
                                account.character.charid=200001
                                account.character.skin=400101
                                account.avatar_id= 400101
                            if self.settings['config']['show_server']:
                                account.nickname =self.get_zone_id(account.account_id)+account.nickname

                            result += f'{self.get_zone_id(account.account_id)}{account.nickname}\n\
账号id: {account.account_id}   加好友id: {self.encode_account_id2(account.account_id)}\n\
主视角牌谱链接: {uuid}_a{self.encode_account_id(account.account_id)}\n\
主视角牌谱链接（匿名）: {self.encodePaipuUUID(uuid)}_a{self.encode_account_id(account.account_id)}_2\n\n'
                            
                        result+='注意：只有在同一服务器才能添加好友！'
                        logger.info(result)

                    case '.lq.Lobby.fetchRandomCharacter':
                        modify = True
                        data = liqi_pb2.ResRandomCharacter()
                        json_format.ParseDict(self.settings['config']['random_character'],data)


            else:
                logger.error(f'unknown msgtype: {msg_type}')
        if modify:
            msg_block.data = data.SerializeToString()
            if msg_type == liqi.MsgType.NOTIFY:
                msg = b'\x01' + msg_block.SerializeToString()
            else:
                msg = buf[:3] + msg_block.SerializeToString()
            self.SaveSettings()

        return modify, drop, msg, inject, inject_msg

    def get_zone_id(self, id:int):
        i = id >> 23
        if 0 <= i <= 6:
            return '[C' + b'\xef\xbb\xbf'.decode('utf-8') + 'N]'
        elif 7 <= i <= 12:
            return '[JP]'
        elif 13 <= i <= 15:
            return '[EN]'
        else:
            return '[??]'
    def encodePaipuUUID(self,uuid) :
        result = ''
        code0=ord('0')
        codeA=ord('a')
        for i,char in enumerate(uuid):
            code = ord(char)
            temp = -1
            if code >= code0 and code0+ 10 > code :
                temp = code - code0
            elif code >= codeA and codeA + 26 > code:
                temp= code - codeA + 10
            if -1 != temp:
                temp = (temp + 17 + i) % 36
                if 10 > temp:
                    result += chr(temp + code0)
                else:
                    result +=  chr(temp + codeA - 10)
                
            else:
                result += char
        return result
    def encode_account_id(self,id:int) :
            return int((7 * id + 1117113 ^ 86216345) + 1358437)
        
    def encode_account_id2(self,p:int):
        p = 6139246 ^ p
        H = 67108863
        S = p & ~H
        Z = p & H
        for i in range(5):
            Z = (511 & Z) << 17 | Z >> 9
        return int(Z + S + 1e7)
