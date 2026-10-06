"""Discovery sees only accessible evidence and cannot turn triangulation into linked writes."""
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from bazaar.marketplace.network.skill import mercado16 as m
from tests.test_network_skill import CATALOG, V16, card, team
from tests.test_mercado_watch import WatchApi


def ask(oid, ref, price, venue='rastro', maker='t09', expiry=30):
    return {'id': oid, 'maker': maker, 'venue': venue, 'status': 'open', 'expires_tick': expiry,
            'give': {'assets': [card(oid+100, ref, 999)]}, 'want': {'cash': price}}


def bid(oid, ref, price, venue='rastro', maker='t08', expiry=30):
    return {'id': oid, 'maker': maker, 'venue': venue, 'status': 'open', 'expires_tick': expiry,
            'give': {'cash': price}, 'want': {'types': ['card:'+ref]}}


def swap(oid, give, want, maker):
    return {'id': oid, 'maker': maker, 'venue': 'rastro', 'status': 'open', 'expires_tick': 30,
            'give': {'assets': [card(oid+100, give, 999)]}, 'want': {'cards': [want]}}


def evidence(offers, tick=10, fees=(0, 0)):
    return {'rows': [{'offer': o, 'venue': o['venue'], 'tick': tick, 'fees': fees} for o in offers],
            'coverage': 'test coverage', 'duels': [], 'recent': [], 'notes': []}


class DiscoveryApi(WatchApi):
    def __init__(self, me):
        super().__init__(me)
        self.boards, self.reads, self.duel_rows = {}, [], []
        self.extra_venues = []
        self.values = {}

    def call(self, method, path, body=None, query=None):
        self.reads.append((method, path, query))
        if method == 'GET' and path == '/api/me/value':
            return {'your_value': self.values.get(query['card'],60)}
        if method == 'GET' and path == '/api/venues':
            return {'venues': [self.venue, {**V16, 'venue': 'rastro', 'owner': None}, *self.extra_venues]}
        if method == 'GET' and path.startswith('/api/venues/'):
            return {'offers': self.boards.get(path.split('/')[3], [])}
        if method == 'GET' and path == '/api/duels':
            return {'duels': self.duel_rows}
        return super().call(method, path, body, query)


class Discovery(unittest.TestCase):
    def show(self, ev, me, values, settings=None, post=False):
        out = io.StringIO()
        with redirect_stdout(out):
            signals = m.show_discovery(ev, me, CATALOG, values, [], (0, 0), settings or m.Settings(), 10, post)
        return out.getvalue(), signals

    def test_direct_evidence_prioritizes_safe_quotes_inside_reserve(self):
        ev = evidence([ask(1, 'LAT-01', 20)])
        me = team('t03', 200, [])
        signals, _ = m.discovery_signals(ev, me, 10)
        quotes, _ = m.plan(me, CATALOG, {'LAT-01': 90, 'LAT-03': 90}, [], 0, 0,
                           m.Settings(max_bids=1), signals)
        self.assertEqual(quotes[0].card, 'LAT-01')
        self.assertEqual(quotes[0].price, 89)
        self.assertLess(quotes[0].price, quotes[0].limit)
        self.assertLessEqual(quotes[0].price, me['cash']-100)
        text, _ = self.show(ev, me, {'LAT-01': 90})
        self.assertIn('conditional midpoint', text)
        self.assertIn('rastro offer 1', text)
        self.assertIn('local agents automatically quote on v16', text)

    def test_seller_keeps_private_bound_and_last_copy_and_protection(self):
        me = team('t03', 300, [card(2,'LAT-02',10),card(3,'LAT-02',10),card(4,'LAT-01',5)])
        ev = evidence([bid(1,'LAT-02',30),bid(2,'LAT-01',100)])
        signals, _ = m.discovery_signals(ev, me, 10)
        quotes, _ = m.plan(me, CATALOG, {}, [], 500, 1, m.Settings(only_sell=True), signals)
        self.assertEqual([q.card for q in quotes], ['LAT-02'])
        self.assertGreater(quotes[0].price-m.fee_on(quotes[0].price,500,1),10)
        quotes, _ = m.plan(me, CATALOG, {}, [], 0, 0, m.Settings(protect={'LAT-02'}), signals)
        self.assertEqual(quotes, [])

    def test_expired_targeted_bundled_unknown_and_self_quotes_are_not_signals(self):
        good=ask(1,'LAT-01',20)
        malformed={**good,'id':2,'give':'unreadable'}
        targeted={**good,'id':3,'to':'t07'}
        bundled={**good,'id':4,'give':{'assets':[card(100,'LAT-01',2),card(101,'LAT-02',2)]}}
        expired=ask(5,'LAT-01',20,expiry=10)
        selfquote=ask(6,'LAT-01',20,maker='t03')
        signals, _ = m.discovery_signals(evidence([good,malformed,targeted,bundled,expired,selfquote]),team('t03',200,[]),10)
        self.assertEqual([q['offer'] for q in signals],[1])
        self.assertEqual(m.discovery_signals(evidence([good],tick=1),team('t03',200,[]),10)[0],[])
        private_own={**good,'maker':'opaque-maker'}
        mine=[{**good,'maker':'t03'}]
        self.assertEqual(m.discovery_signals(evidence([private_own]),team('t03',200,[]),10,mine)[0],[])

    def test_resale_is_advisory_and_fee_adjusted_and_never_adds_speculative_bid(self):
        me=team('t03',300,[])
        text,_=self.show(evidence([ask(1,'LAT-01',40),bid(2,'LAT-01',70)]),me,{'LAT-01':50})
        self.assertIn('RESALE',text)
        self.assertIn('cash at risk 40',text)
        self.assertIn('outgoing value/page effect after purchase unverified',text)
        text,_=self.show(evidence([ask(1,'LAT-01',40),bid(2,'LAT-01',41)],fees=(500,1)),me,{'LAT-01':50})
        self.assertNotIn('RESALE',text)
        quotes,_=m.plan(me,CATALOG,{'LAT-01':30},[],0,0,m.Settings(),m.discovery_signals(evidence([ask(1,'LAT-01',40),bid(2,'LAT-01',70)]),me,10)[0])
        self.assertLess(quotes[0].price,30)  # no buying above private value for a hoped-for resale

    def test_three_leg_cycle_from_local_spare_requires_human(self):
        me=team('t03',300,[card(1,'LAT-01',2),card(2,'LAT-01',2)])
        ev=evidence([swap(1,'LAT-02','LAT-01','t07'),swap(2,'LAT-03','LAT-02','t08'),swap(3,'LAT-01','LAT-03','t09')])
        text,signals=self.show(ev,me,{})
        self.assertIn('BARTER CYCLE',text)
        self.assertIn('Worst downside',text)
        self.assertEqual(signals,[])
        text,_=self.show(ev,me,{},m.Settings(protect={'LAT-01'}))
        self.assertNotIn('BARTER CYCLE',text)

    def test_competing_valuable_bids_stop_before_writes_and_survive_restart(self):
        api=DiscoveryApi(team('t03',300,[]))
        api.values={'LAT-01':180,'LAT-02':180,'LAT-03':180}
        api.boards={'rastro':[ask(1,'LAT-01',40),ask(2,'LAT-02',40)]}
        with tempfile.TemporaryDirectory() as tmp, patch.object(m.time, 'sleep', side_effect=AssertionError('unexpected maintenance retry')), redirect_stdout(io.StringIO()):
            marker=Path(tmp)/'stop.json'
            self.assertEqual(m.watch(api,m.Settings(discover=True),True,marker=marker),2)
            self.assertTrue(marker.exists())
            self.assertEqual(m.watch(api,m.Settings(discover=True),True,marker=marker),2)
            self.assertIn('competing valuable bids',marker.read_text())
        self.assertEqual((api.posts,api.deletes),([],[]))

    def test_reads_rotate_markets_and_duels_are_context_not_transferable_demand(self):
        api=DiscoveryApi(team('t03',300,[]))
        api.extra_venues=[{**V16,'venue':'v'+str(i),'owner':'t99'} for i in range(4)]
        api.duel_rows=[{'duel':7,'status':'live','item':'LAT-01','role':'buyer','your_limit':999,
                        'rival_offer':{'price':2,'days':1},'deadline_tick':20}]
        api.events=[{'scope':'public','type':'duel.closed','tick':9,'payload':{'item':'LAT-01','price':1}},
                    {'scope':'team:t09','type':'settlement','tick':9,'payload':{'price':1000}}]
        state={}
        venues=api.call('GET','/api/venues')['venues']
        ev=m.read_discovery(api,venues,{'tick':10},state)
        m.read_discovery(api,venues,{'tick':11},state)
        boards={path for method,path,q in api.reads if '/offers' in path}
        self.assertEqual(len(boards),6)
        self.assertTrue(all(method=='GET' for method,path,q in api.reads))
        self.assertEqual(len(ev['recent']),1)
        text,signals=self.show(ev,api.me,{'LAT-01':90})
        self.assertIn('OWN DUEL 7',text)
        self.assertIn('not transferable-card demand',text)
        self.assertEqual(signals,[])
        self.assertNotIn('999',text)  # don't broadcast own duel limits

    def test_discovery_watch_is_read_only_without_post_and_does_not_duplicate(self):
        api=DiscoveryApi(team('t03',300,[]))
        api.boards={'rastro':[ask(1,'LAT-01',20)]}
        s=m.Settings(discover=True,max_bids=1)
        with redirect_stdout(io.StringIO()):
            m.watch_cycle(api,s,False,{})
        self.assertEqual(api.posts,[])
        state={}
        with redirect_stdout(io.StringIO()):
            m.watch_cycle(api,s,True,state)
            api.tick+=1
            m.watch_cycle(api,s,True,state)
        self.assertEqual(len(api.posts),1)
        self.assertEqual(api.posts[0]['venue'],'v16')
        self.assertEqual(set(api.posts[0]),{'venue','give','want','expires_in_ticks'})

    def test_future_sale_proceeds_never_fund_a_bid(self):
        me=team('t03',50,[card(1,'LAT-02',10),card(2,'LAT-02',10)])
        signals,_=m.discovery_signals(evidence([bid(1,'LAT-02',200),ask(2,'LAT-01',10)]),me,10)
        quotes,_=m.plan(me,CATALOG,{'LAT-01':100},[],0,0,m.Settings(),signals)
        self.assertEqual([q.side for q in quotes],['sell'])

    def test_two_leg_cycle_is_advisory_and_search_is_bounded(self):
        me=team('t03',300,[card(1,'LAT-01',2),card(2,'LAT-01',2)])
        text,_=self.show(evidence([swap(1,'LAT-02','LAT-01','t07'),swap(2,'LAT-01','LAT-02','t08')]),me,{})
        self.assertIn('BARTER CYCLE',text)
        self.assertIn('do nothing without human review',text)
        flood=[swap(i,'LAT-02' if i%2 else 'LAT-01','LAT-01' if i%2 else 'LAT-02','t'+str(i)) for i in range(1,500)]
        text,_=self.show(evidence(flood),me,{})
        self.assertLessEqual(text.count('BARTER CYCLE'),3)

    def test_discovery_closed_doors_and_429_do_not_write(self):
        api=DiscoveryApi(team('t03',300,[]))
        api.doors='closed'
        with redirect_stdout(io.StringIO()):
            m.watch_cycle(api,m.Settings(discover=True),True,{})
        self.assertFalse(any('/api/venues/' in path for method,path,q in api.reads))
        api.doors='open'
        original=api.call
        throttled=[False]
        def read(method,path,body=None,query=None):
            if not throttled[0] and path.startswith('/api/venues/'):
                throttled[0]=True
                raise m.ApiError('rate_limited',status=429,extra={'next_tick':11})
            return original(method,path,body,query)
        api.call=read
        sleeps=[]
        def advance(delay):
            sleeps.append(delay)
            if len(sleeps)==1:
                self.assertEqual(api.posts,[])
                api.tick=11
            else:
                raise KeyboardInterrupt
        with tempfile.TemporaryDirectory() as tmp, patch.object(m.time,'sleep',side_effect=advance), redirect_stdout(io.StringIO()):
            with self.assertRaises(KeyboardInterrupt):
                m.watch(api,m.Settings(discover=True,max_bids=1),True,marker=Path(tmp)/'stop.json')
        self.assertEqual(len(api.posts),1)
        self.assertEqual(api.offers[0]['created_tick'],11)

    def test_external_fees_remain_in_reserve_and_unknown_fees_fail_closed(self):
        me=team('t03',200,[])
        mine=[{'id':99,'maker':'t03','venue':'other','status':'open',
               'give':{'cash':90},'want':{'cards':['LAT-03']}}]
        ev=evidence([ask(1,'LAT-01',5)])
        ev['venue_fees']={'other':(500,1)}
        adjusted=m.discovery_cash(me,mine,(0,0),ev,'v16')
        quotes,_=m.plan(adjusted,CATALOG,{'LAT-01':10},mine,0,0,m.Settings())
        self.assertEqual(quotes,[])  # only 4 P remain after 96 P commitment and reserve
        with self.assertRaises(m.ApiError) as caught:
            m.discovery_cash(me,mine,(0,0),evidence([]),'v16')
        self.assertEqual(caught.exception.code,'human_required')

    def test_disabled_bids_do_not_create_unnecessary_human_stop(self):
        text,_=self.show(evidence([ask(1,'LAT-01',40),ask(2,'LAT-02',40)]),
                         team('t03',300,[]),{'LAT-01':180,'LAT-02':180},m.Settings(max_bids=0),True)
        self.assertIn('LOCAL DEAL DISCOVERY',text)

    def test_auto_launch_selects_local_discovery_and_safe_watch_without_new_service(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(m,'WATCH_MARKER',Path(tmp)/'stop.json'), patch.dict(m.os.environ,{'BAZAAR_KEY':'test-local-key'}), patch.object(m,'watch',return_value=0) as watch:
            self.assertEqual(m.main(['--auto']),0)
            args=watch.call_args.args
            self.assertTrue(args[1].discover)
            self.assertTrue(args[2])

    def test_automatic_cash_legs_are_independently_safe_not_dependent_on_resale(self):
        me=team('t03',300,[card(1,'LAT-02',10),card(2,'LAT-02',10)])
        ev=evidence([bid(1,'LAT-02',30),ask(2,'LAT-01',20)])
        text,_=self.show(ev,me,{'LAT-01':90})
        self.assertIn('AUTOMATIC SAFE LEGS',text)
        self.assertIn('not future sale proceeds',text)
        self.assertIn('Each leg remains safe if the other never fills',text)
        poor=team('t03',50,me['assets'])
        text,_=self.show(ev,poor,{'LAT-01':90})
        self.assertNotIn('AUTOMATIC SAFE LEGS',text)
