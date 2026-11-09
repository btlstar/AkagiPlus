import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'plugins/amatsuki'))
from protocol import Bridge,tile


def card(name,id=0):return {'name':name,'id':id}

def feed(b,kind,data):return b.accept({'type':kind,'data':data,'uid':'9000000000000000001'})

def ready(n=4):
    b=Bridge();feed(b,'JoinDeskResponse',{'status':0,'gameType':0,'gameMode':0})
    players=[{'uid':str(9000000000000000000+i),'name':str(i),'posId':0}for i in range(n)]
    feed(b,'JpGameStart',{'playerList':players})
    hands=[{'tehai':{'hand':[card('0U',-1)]*13}}for _ in range(n)]
    hands[1]['tehai']['hand']=[card('1M',i)for i in range(13)]
    data={'bakaze':0,'oya':0,'honba':0,'playerPoints':[25000]*n,'playerTiles':hands}
    feed(b,'RoundStart',data)
    return b,data


def begin(b):return feed(b,'SyncDoraArea',{'dora':[card('3M',10)],'reachCount':0})


class ProtocolTests(unittest.TestCase):
    def test_tile_names_and_reds(self):
        for name,result in [('0M','5mr'),('0P','5pr'),('0S','5sr'),('5M','5m'),('1Z','E'),('7Z','C'),('0U','?')]:self.assertEqual(tile(card(name)),result)
        with self.assertRaises(ValueError):tile(card('8Z'))

    def test_seat_uses_roster_order_and_opponent_tiles_remain_hidden(self):
        b,_=ready();out=begin(b);self.assertEqual(b.seat,1)
        event=out[0]['event'];self.assertEqual(event['type'],'start_kyoku');self.assertEqual(event['dora_marker'],'3m')
        self.assertEqual(event['tehais'][0],['?']*13);self.assertEqual(event['tehais'][1],['1m']*13)

    def test_sanma_uses_three_seats(self):
        b,_=ready(3);self.assertEqual(begin(b)[0]['event']['num_players'],3)
        self.assertEqual(len(b.players),3)

    def test_missing_own_hand_stops_analysis(self):
        b,data=ready();data['playerTiles'][1]['tehai']['hand']=[card('0U',-1)]*13
        out=begin(b);self.assertEqual(out[0]['event']['type'],'end_game');self.assertTrue(out[0]['terminated']);self.assertFalse(b.started)

    def test_actions_wait_for_opening_dora(self):
        b,_=ready();self.assertEqual(feed(b,'DrawActionResponse',{'position':0,'hai':card('0U',-1)}),[])
        out=begin(b);self.assertEqual([x['event']['type']for x in out],['start_kyoku','tsumo'])

    def test_riichi_discard_and_acceptance_order(self):
        b,_=ready();begin(b)
        out=feed(b,'TehaiAction',{'position':1,'action':201,'haiList':[card('0M',16)],'isKiri':False})
        self.assertEqual([x['event']['type']for x in out],['reach','dahai']);self.assertEqual(out[-1]['event']['pai'],'5mr')
        self.assertEqual(feed(b,'ReachSet',{'position':1})[0]['event']['type'],'reach_accepted')
        self.assertEqual(feed(b,'ReachSet',{'position':1}),[])

    def test_pon_removes_the_called_physical_tile(self):
        b,_=ready();begin(b)
        feed(b,'TehaiAction',{'position':0,'action':200,'haiList':[card('5P',53)],'isKiri':True})
        out=feed(b,'RiverAction',{'position':1,'action':302,'menzu':{'menzuList':[card('0P',52),card('5P',53),card('5P',54)]}})
        self.assertEqual(out[0]['event'],{'type':'pon','actor':1,'target':0,'pai':'5p','consumed':['5pr','5p']})
        added=feed(b,'TehaiAction',{'position':1,'action':203,'haiList':[card('5P',55)]})
        self.assertEqual(added[0]['event']['pai'],'5p');self.assertIn('5pr',added[0]['event']['consumed'])
        ron=feed(b,'AllRonAction',{'isTsumo':False,'agariInfo':[{'position':2}], 'increaseAndDecrease':[0,-1000,1000,0]})
        self.assertEqual(ron[0]['event']['target'],1)

    def test_win_and_game_end(self):
        b,_=ready();begin(b)
        out=feed(b,'AllRonAction',{'isTsumo':True,'increaseAndDecrease':[-1000,3000,-1000,-1000],'agariInfo':[{'position':1,'uraDora':[card('1Z',108)]}]})
        self.assertEqual([x['event']['type']for x in out],['hora','end_kyoku']);self.assertEqual(out[0]['event']['target'],1)
        self.assertEqual(out[0]['event']['ura_markers'],['E'])
        out=feed(b,'GameEnd',{'points':[24000,28000,24000,24000],'reason':0});self.assertFalse(out[0]['terminated']);self.assertFalse(b.started)

    def test_lobby_and_reconnect_terminate_current_view(self):
        for kind in ('LobbyReturned','ReconnectInfoResponse'):
            b,_=ready();begin(b);out=feed(b,kind,{})
            self.assertTrue(out[0]['terminated']);self.assertFalse(b.started)

    def test_non_riichi_rules_are_ignored(self):
        b=Bridge();feed(b,'JoinDeskResponse',{'status':0,'gameType':1,'gameMode':0})
        self.assertEqual(feed(b,'JpGameStart',{'playerList':[]}),[])


if __name__=='__main__':unittest.main()
