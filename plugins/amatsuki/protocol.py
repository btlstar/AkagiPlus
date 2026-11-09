"""Translate visible ordinary-riichi Amatsuki messages to mjai."""
import re


def tile(value):
    name=value.get('name','') if isinstance(value,dict) else str(value)
    if name in ('0U','?'):return '?'
    match=re.fullmatch(r'([0-9])([MPSZ])',name.upper())
    if not match:raise ValueError('未识别的天月牌编码')
    number,suit=match.groups()
    if suit=='Z':
        if number not in '1234567':raise ValueError('无效字牌')
        return ['E','S','W','N','P','F','C'][int(number)-1]
    return '5'+suit.lower()+'r' if number=='0' else number+suit.lower()


def emit(kind,**fields):return {'kind':'event','event':{'type':kind,**fields}}


class Bridge:
    def __init__(self):
        self.rules=None
        self.players=[]
        self.seat=-1
        self.started=False
        self.round_active=False
        self.pending_round=None
        self.pending_actions=[]
        self.dora=[]
        self.kyotaku=0
        self.last_discard=None
        self.last_draw=None
        self.initial_draw=None
        self.reached=set()
        self.accepted=set()
        self.pons={}

    def reset(self,message):
        end=[{'kind':'event','event':{'type':'end_game'},'terminated':True}] if self.started else []
        self.__init__()
        return end+[{'kind':'status','message':message}]

    def actor(self,value):
        if not isinstance(value,int) or not 0<=value<len(self.players):raise ValueError('天月座次未通过校验')
        return value

    def accept(self,packet):
        try:return self._accept(packet)
        except (KeyError,ValueError,TypeError,IndexError) as error:
            return self.reset(str(error)+'，已暂停分析，请重新进入下一场对局。')

    def _accept(self,p):
        kind=p['type'];d=p['data']
        if kind in ('LobbyReturned','KickOutResponse','ReconnectResponse','ReconnectInfoResponse'):
            return self.reset('等待下一场天月对局开局。')
        if kind=='JoinDeskResponse':
            out=self.reset('等待天月普通立直麻将开局。')
            if d.get('status')==0 and d.get('gameType')==0 and d.get('gameMode') in (0,1):self.rules=d
            else:out[-1]['message']='当前天月玩法暂不支持 AI。'
            return out
        if kind=='JpGameStart':
            if not self.rules:return []
            players=d['playerList'];ids=[str(x['uid']) for x in players]
            if len(players) not in (3,4) or len(set(ids))!=len(ids) or str(p['uid']) not in ids:raise ValueError('天月玩家列表不完整')
            self.players=players;self.seat=ids.index(str(p['uid']));self.started=True
            names=[('电脑 '+str(i+1)) if str(x.get('name','')).startswith('TXT_') else str(x.get('name','玩家')) for i,x in enumerate(players)]
            return [emit('start_game',names=names,id=self.seat,num_players=len(players),aka_flag=True)]
        if not self.started:return []
        if kind=='GameEnd':
            result=emit('end_game');result['final_scores']=d.get('points');result['terminated']=d.get('reason',0)!=0
            self.__init__();return [result]
        if kind=='RoundStart':
            self.pending_round=d;self.pending_actions=[];self.dora=[];self.round_active=False
            self.reached=set();self.accepted=set();self.pons={};self.last_discard=None;self.last_draw=None;self.initial_draw=None
            return []
        if kind=='SyncDoraArea':
            markers=[tile(x) for x in d['dora']]
            if not markers or '?' in markers:raise ValueError('天月宝牌资料不完整')
            self.kyotaku=int(d.get('reachCount',self.kyotaku))
            if self.pending_round:
                self.dora=markers
                return self.begin_round()
            if self.round_active:
                if markers[:len(self.dora)]!=self.dora:raise ValueError('天月宝牌顺序发生变化')
                out=[emit('dora',dora_marker=x) for x in markers[len(self.dora):]];self.dora=markers;return out
            return []
        if self.pending_round:
            self.pending_actions.append(p)
            if len(self.pending_actions)>128:raise ValueError('天月开局消息未完整同步')
            return []
        if not self.round_active:return []
        if kind=='DrawActionResponse':
            actor=self.actor(d['position']);card=d['hai'];pai=tile(card) if actor==self.seat else '?'
            if actor==self.seat and pai=='?':raise ValueError('自身摸牌缺失')
            if actor==self.seat and self.initial_draw is not None:
                opening=self.initial_draw;self.initial_draw=None
                if card.get('id')==opening.get('id'):return []
            self.last_draw=(actor,card)
            return [emit('tsumo',actor=actor,pai=pai)]
        if kind=='TehaiAction':return self.tehai_action(d)
        if kind=='RiverAction':return self.river_action(d)
        if kind=='ReachSet':
            actor=self.actor(d['position'])
            if actor in self.accepted:return []
            if actor not in self.reached:raise ValueError('天月立直顺序未同步')
            self.accepted.add(actor);return [emit('reach_accepted',actor=actor)]
        if kind=='AllRonAction':
            out=[];winners=d['agariInfo']
            if not winners:raise ValueError('天月和牌资料缺失')
            for i,winner in enumerate(winners):
                actor=self.actor(winner['position'])
                if not d['isTsumo'] and not self.last_discard:raise ValueError('天月放铳座次缺失')
                target=actor if d['isTsumo'] else self.last_discard[0]
                deltas=winner.get('increaseAndDecrease')
                if not deltas or len(deltas)!=len(self.players):deltas=d.get('increaseAndDecrease') if i==0 else None
                out.append(emit('hora',actor=actor,target=target,deltas=deltas,ura_markers=[tile(x)for x in winner.get('uraDora')or []]))
            self.round_active=False;return out+[emit('end_kyoku')]
        if kind=='RyuukyokuAction':
            self.round_active=False;return [emit('ryukyoku',deltas=d.get('increaseAndDecrease')),emit('end_kyoku')]
        return []

    def begin_round(self):
        d=self.pending_round;n=len(self.players);oya=self.actor(d['oya']);wind=d['bakaze']
        if not isinstance(wind,int) or wind not in range(4):raise ValueError('天月场风未适配')
        if len(d['playerPoints'])!=n or len(d['playerTiles'])!=n:raise ValueError('天月开局人数不一致')
        own=d['playerTiles'][self.seat]['tehai']['hand']
        if len(own) not in (13,14) or any(tile(x)=='?'for x in own):raise ValueError('天月起手牌缺失')
        if len(own)==14 and self.seat!=oya:raise ValueError('天月庄家手牌不一致')
        hands=[['?']*13 for _ in range(n)];hands[self.seat]=[tile(x)for x in own[:13]]
        out=[emit('start_kyoku',bakaze=['E','S','W','N'][wind],dora_marker=self.dora[0],kyoku=oya+1,honba=d['honba'],kyotaku=self.kyotaku,oya=oya,scores=d['playerPoints'],tehais=hands,num_players=n)]
        out += [emit('dora',dora_marker=x)for x in self.dora[1:]]
        if len(own)==14:
            self.initial_draw=own[13];self.last_draw=(self.seat,own[13]);out.append(emit('tsumo',actor=self.seat,pai=tile(own[13])))
        self.pending_round=None;self.round_active=True
        pending=self.pending_actions;self.pending_actions=[]
        for packet in pending:out.extend(self._accept(packet))
        return out

    def tehai_action(self,d):
        actor=self.actor(d['position']);action=d['action'];cards=d.get('haiList')or [];out=[]
        if action in (200,201,207):
            if len(cards)!=1 or tile(cards[0])=='?':raise ValueError('天月弃牌资料不完整')
            if action in (201,207) and actor not in self.reached:
                self.reached.add(actor);out.append(emit('reach',actor=actor))
            self.last_discard=(actor,cards[0]);self.initial_draw=None
            return out+[emit('dahai',actor=actor,pai=tile(cards[0]),tsumogiri=bool(d.get('isKiri')))]
        if action==202:
            if len(cards)!=4 or any(tile(x)=='?'for x in cards):raise ValueError('天月暗杠资料未适配')
            return [emit('ankan',actor=actor,consumed=[tile(x)for x in cards])]
        if action==203:
            if not cards:raise ValueError('天月加杠资料不完整')
            key=tile(cards[0]).replace('r','');previous=self.pons.get((actor,key))
            if not previous:raise ValueError('天月加杠前的碰牌缺失')
            added=[x for x in cards if x.get('id')not in [c.get('id')for c in previous]]
            if len(added)!=1:raise ValueError('天月加杠牌未适配')
            self.last_discard=(actor,added[0])
            return [emit('kakan',actor=actor,pai=tile(added[0]),consumed=[tile(x)for x in previous])]
        if action==204:
            if len(self.players)!=3:raise ValueError('四人局出现拔北动作')
            return [emit('kita',actor=actor,pai='N')]
        if action in (205,206):return []
        raise ValueError('天月手牌动作未适配')

    def river_action(self,d):
        action=d['action']
        if action in (300,304):return []
        if action not in (301,302,303) or not self.last_discard:raise ValueError('天月鸣牌资料未同步')
        actor=self.actor(d['position']);target,called=self.last_discard;cards=list(d['menzu']['menzuList'])
        if actor==target or len(cards)!=(4 if action==303 else 3):raise ValueError('天月鸣牌数量不一致')
        index=next((i for i,c in enumerate(cards)if c.get('id')==called.get('id')),None)
        if index is None:raise ValueError('天月鸣牌中的弃牌缺失')
        cards.pop(index)
        if action==302:self.pons[(actor,tile(called).replace('r',''))]=[called,*cards]
        return [emit({301:'chi',302:'pon',303:'daiminkan'}[action],actor=actor,target=target,pai=tile(called),consumed=[tile(x)for x in cards])]
