"""Offline deterministic replay using unchanged Mercado agents and coordinator.

Run: python3 mercado_demo.py > results.json
No Bazaar credentials, HTTP requests or real trades. Synthetic fixture only.
"""
import contextlib
import copy
import io
import json
from pathlib import Path
import random
import tempfile
from unittest.mock import patch
from tests.test_cycle_agent import World, Api, LocalCoordinator, POLICY
from bazaar.marketplace.network.auth import token_hash
from bazaar.marketplace.network.cycles import Cycles
from bazaar.marketplace.network.service import Waitlist
from bazaar.marketplace.network.store import Store
from bazaar.marketplace.network.skill.cycle_agent import Agent

SCENARIOS = [
    ('three', 'Three-team route', 3, 'complete'),
    ('four', 'Four-team route', 4, 'complete'),
    ('reject', 'One team declines', 3, 'reject'),
    ('cash', 'Insufficient reserve', 3, 'cash'),
    ('value', 'Value changes after approval', 3, 'value'),
    ('partial', 'Only one trade settles', 3, 'partial'),
]

def run(key, title, count, mode):
    rng = random.Random(16)
    with tempfile.TemporaryDirectory() as tmp, patch('secrets.token_hex', side_effect=lambda n: rng.randbytes(n).hex()), patch('urllib.request.urlopen', side_effect=AssertionError('Network forbidden in offline simulation')):
        root = Path(tmp)
        world = World()
        refs = ['LAT-01', 'CHA-01', 'SAL-01', 'RET-01'][:count]
        world.refs = {f't{i+1:02}': ref for i, ref in enumerate(refs)}
        world.want = {team: refs[(i+1) % count] for i, team in enumerate(world.refs)}
        outgoing = [90, 80, 85, 75][:count]
        incoming = [140, 130, 125, 135][:count]
        world.teams = {team: dict(id=team, cash=250, assets=[dict(id=(i+1)*100+k, ref=ref, kind='card', your_value=outgoing[i]) for k in (1,2)]) for i,(team,ref) in enumerate(world.refs.items())}
        if mode == 'cash': world.teams['t02']['cash'] = 150
        class LocalApi(Api):
            def call(self, method, path, body=None, query=None):
                if path == '/api/me/value': return {'your_value': incoming[list(world.refs).index(self.team)]}
                return super().call(method, path, body, query)
        store = Store(root / 'private.sqlite')
        try:
            cycles = Cycles(store, world.clock, max_teams=count)
            service = Waitlist(store, cycles)
            agents = {}
            for team in world.teams:
                row = store.join(team); store.mark_verified(row['id'], 'synthetic'); store.save_token(row['id'], token_hash('md16_'+team))
                api = LocalApi(world, team)
                api.threads = [dict(**{'with':'t09'}, status='walked', standing_offers=[], messages=[dict(sender=team, offer={'give': {'assets':[world.teams[team]['assets'][0]['id']]}, 'want': {'cards':[world.want[team]]}})])]
                policy = {**copy.deepcopy(POLICY), 'max_participants':count}
                if mode == 'reject' and team == 't03': policy['autonomous'] = False
                agents[team] = Agent(api, LocalCoordinator(service, team), policy, root/team/'state.json', live=True)
            before = copy.deepcopy(world.teams)
            frames=[]; notices=[]; views={}
            def snapshot(label):
                settled=[o for o in world.offers.values() if o['status']=='settled']
                gains={t:0 for t in world.teams}
                for o in settled:
                    price=o['want']['cash']; seller=o['maker']; buyer=o['to']
                    gains[seller]+=price-outgoing[list(world.refs).index(seller)]
                    gains[buyer]+=incoming[list(world.refs).index(buyer)]-price-__import__('math').ceil(price*.02)
                rows=[]
                for i,(team,data) in enumerate(world.teams.items()):
                    rows.append(dict(team=team, cash=data['cash'], holdings=[a['ref'] for a in data['assets']], outgoing_value=next((a['your_value'] for a in data['assets'] if a['ref']==world.refs[team]), outgoing[i]), incoming_value=incoming[i], gain=gains[team], human_required=agents[team].marker.exists()))
                records=cycles._routes()
                frames.append(dict(label=label,tick=world.tick,teams=rows,offers=[dict(seller=o['maker'],buyer=o['to'],card=world.refs[o['maker']],price=o['want']['cash'],fee=__import__('math').ceil(o['want']['cash']*.02),status=o['status']) for o in world.offers.values()], state=records[0]['state'] if records else 'no_route', trades=len(settled), participant_gain=sum(gains.values()), fees=sum(__import__('math').ceil(o['want']['cash']*.02) for o in settled), notices=list(notices)))
            def cycle(team):
                try:
                    with contextlib.redirect_stdout(io.StringIO()): agents[team].cycle()
                except ValueError as exc: notices.append(f'{team}: {exc}')
            snapshot('Before coordination')
            for team in agents: cycle(team)
            for team in agents:
                proposals=cycles.mine(team)['proposals']
                if proposals: views[team]=proposals[0]
            snapshot('Local leads and private proposals')
            for team in agents: cycle(team)
            if mode=='reject' and views:
                view=cycles.mine('t03')['proposals'][0]
                cycles.update('t03',view['route_id'],dict(view_id=view['view_id'],approved=False,allow_partial=True))
                notices.append('t03 explicitly declined: no trade authorized.')
            snapshot('Buy-in and local safety checks')
            if mode=='value':
                world.teams['t01']['assets'][0]['your_value']=151
                notices.append('t01 outgoing marginal value changed from 90 to 151 P after approval.')
            for team in agents:
                if mode != 'partial' or team != 't03': cycle(team)
            snapshot('Directed offers / safety stops')
            if mode=='partial':
                cycle('t01')
                view=cycles.mine('t02')['proposals'][0]
                cycles.update('t02',view['route_id'],dict(view_id=view['view_id'],approved=False,allow_partial=True))
                notices.append('t02 withdrew after one acceptance. That queued trade can still settle; others stop.')
            else:
                for team in agents: cycle(team)
            snapshot('Acceptance decisions')
            world.advance()
            for team in agents: cycle(team)
            snapshot('Observed settlement and reconciliation')
            final=frames[-1]
            assert all(r['gain']>=0 for r in final['teams'])
            for offer in final['offers']:
                if offer['status'] == 'settled':
                    assert offer['price'] > outgoing[list(world.refs).index(offer['seller'])]
                    assert offer['price'] + offer['fee'] < incoming[list(world.refs).index(offer['buyer'])]
            assert sum(r['cash'] for r in final['teams'])+final['fees']==sum(r['cash'] for r in frames[0]['teams'])
            assert sum(len(r['holdings']) for r in final['teams'])==count*2
            if mode=='complete': assert final['trades']==count
            if mode in ('reject','cash'): assert final['trades']==0
            if mode=='partial': assert final['trades']==1
            if mode=='value': assert final['teams'][0]['human_required'] and not any(o['seller']=='t01' for o in final['offers'])
            # Route nonce/version commitments are deterministic in this offline harness.
            return dict(id=key,title=title,mode=mode,count=count,history=[dict(team=team,offered=world.refs[team],wanted=world.want[team],counterparty='t09',outcome='walked',reason='Counterparty has no requested card; negotiation ended without a trade.') for team in world.refs],views=views,frames=frames,baseline=dict(trades=0,gain=0,description='Replay of the supplied failed negotiations without introducing new counterparties. Not an optimal bilateral cash-market benchmark.'))
        finally: store.close()

def main():
    print(json.dumps(dict(version=1,seed=16,source_commit='9985b89c52167efc40fce962a0c577ac28b36e13',synthetic=True,scenarios=[run(*s) for s in SCENARIOS]),indent=2,sort_keys=True))

if __name__=='__main__': main()
