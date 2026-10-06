"""Three local agents against a synthetic Bazaar API. No network/live evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from bazaar.marketplace.network.auth import token_hash
from bazaar.marketplace.network.cycles import Cycles
from bazaar.marketplace.network.service import Waitlist
from bazaar.marketplace.network.store import Store
from bazaar.marketplace.network.skill import mercado16 as m, triangles as t
from bazaar.marketplace.network.skill.cycle_agent import Agent, leads, policy_checked, Coordinator

POLICY = dict(reserve=100, max_trade=200, max_hour=500, min_surplus=1,
              max_participants=3, allow_partial=True, autonomous=True,
              share_selected_intents=True, protect=[], sell=[], buy=[])


class World:
    def __init__(self):
        self.tick, self.offers, self.events, self.calls, self.next_id, self.error = 10, {}, [], [], 1000, None
        self.venue_fee, self.doors, self.paused, self.duels = 200, "open", False, []
        self.refs = {"t01": "LAT-01", "t02": "CHA-01", "t03": "SAL-01"}
        self.want = {"t01": "CHA-01", "t02": "SAL-01", "t03": "LAT-01"}
        self.teams = {}
        for index, (team, ref) in enumerate(self.refs.items(), 1):
            self.teams[team] = {"id": team, "cash": 500, "assets": [
                {"id": index * 100 + k, "ref": ref, "kind": "card", "your_value": 90} for k in (1, 2)]}
        self.incoming_value = 130
    def clock(self):
        return {"tick": self.tick, "doors": self.doors, "paused": self.paused, "next_tick_in": 15,
                "limits": {"max_open_offers_per_team": 30}}
    def intents(self):
        return [dict(team=team, asset=data["assets"][0]["id"], give=self.refs[team], want=self.want[team],
                     ask=100, bid=120, observed_tick=self.tick, expires_tick=self.tick + 8,
                     shared_with_consent=True, evidence={"kind": "stalled_negotiation", "id": "synthetic"})
                for team, data in self.teams.items()]
    def advance(self):
        self.tick += 1
        for offer in self.offers.values():
            if offer["status"] != "queued":
                continue
            seller, buyer = self.teams[offer["maker"]], self.teams[offer["to"]]
            asset = next(a for a in seller["assets"] if a["id"] == offer["give"]["assets"][0])
            seller["assets"].remove(asset)
            buyer["assets"].append(asset)
            price = offer["want"]["cash"]
            seller["cash"] += price
            buyer["cash"] -= price + t.fee(price)
            offer["status"] = "settled"
            self.events.append({"type": "settlement", "tick": self.tick, "payload": {
                "venue": "v16", "price": price, "fee": t.fee(price),
                "items": [{"id": asset["id"], "frm": seller["id"], "to": buyer["id"]}]}})


class Api:
    def __init__(self, world, team):
        self.world, self.team, self.threads = world, team, []
    def call(self, method, path, body=None, query=None):
        w, me = self.world, self.world.teams[self.team]
        w.calls.append((self.team, method, path, copy.deepcopy(body)))
        if method != "GET" and w.error:
            error, w.error = w.error, None
            raise error
        if path == "/api/clock":
            return w.clock()
        if path == "/api/duels":
            return {"duels": w.duels}
        if path == "/api/duels/live":
            return {"duels": []}
        if path == "/api/venues/v16/offers":
            return {"offers": []}
        if path == "/api/me":
            return copy.deepcopy(me)
        if path == "/api/venues":
            return {"venues": [{"id": "v16", "owner": "t16", "status": "open", "fee_bps": w.venue_fee,
                                "fee_per_card": 0, "rules": {"mechanism": "auto"}}]}
        if path == "/api/me/offers":
            return {"offers": [copy.deepcopy(o) for o in w.offers.values()
                               if self.team in (o["maker"], o["to"]) and o["status"] in ("open", "queued")]}
        if path == "/api/catalog":
            return {"sets": [{"cards": [{"id": ref, "page": True} for ref in w.refs.values()]}]}
        if path == "/api/me/value":
            return {"your_value": w.incoming_value}
        if path == "/api/me/threads":
            return {"threads": [{"id": i + 1, "with": th["with"]} for i, th in enumerate(self.threads)]}
        if path.startswith("/api/threads/"):
            return copy.deepcopy(self.threads[int(path.split("/")[-1]) - 1])
        if path.startswith("/api/cards/"):
            asset = int(path.split("/")[-1])
            return copy.deepcopy(next(a for data in w.teams.values() for a in data["assets"] if a["id"] == asset))
        if path == "/api/feed":
            return {"events": copy.deepcopy(w.events)}
        if method == "POST" and path == "/api/offers":
            w.next_id += 1
            offer = {**body, "id": w.next_id, "maker": self.team, "status": "open", "expires_tick": w.tick + 40}
            w.offers[w.next_id] = offer
            return {"offer": copy.deepcopy(offer)}
        if method == "POST" and path.endswith("/accept"):
            offer = w.offers[int(path.split("/")[-2])]
            if offer["to"] != self.team or offer["status"] != "open":
                raise AssertionError("wrong/duplicate acceptance")
            offer["status"] = "queued"
            return {"accepted": True}
        if method == "DELETE":
            offer = w.offers[int(path.split("/")[-1])]
            if offer["maker"] != self.team:
                raise AssertionError("cancelled another team")
            offer["status"] = "cancelled"
            return {}
        raise AssertionError((method, path))


class LocalCoordinator:
    def __init__(self, service, team):
        self.service, self.team = service, team
    def call(self, method, path, body=None):
        code, result = self.service.handle(method, path, body, {"Authorization": "Bearer md16_" + self.team})
        if code != 200:
            raise ValueError(str(result))
        return result


class CycleFlow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root, self.world = Path(self.tmp.name), World()
        self.store = Store(self.root / "private.sqlite")
        self.cycles = Cycles(self.store, self.world.clock)
        self.service = Waitlist(self.store, self.cycles)
        for team in self.world.teams:
            row = self.store.join(team)
            self.store.mark_verified(row["id"], "now")
            self.store.save_token(row["id"], token_hash("md16_" + team))
        self.agents = {team: Agent(Api(self.world, team), LocalCoordinator(self.service, team), POLICY,
                                  self.root / team / "state.json", live=True) for team in self.world.teams}
    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()
    def propose(self):
        for intent in self.world.intents():
            self.cycles.submit(intent["team"], intent)
        return self.cycles.mine("t01")["proposals"][0]
    def approve_all(self):
        self.propose()
        for agent in self.agents.values():
            agent.cycle()
    def test_end_to_end_three_local_agents_and_actual_fees(self):
        self.approve_all()
        self.assertEqual(self.cycles.mine("t01")["proposals"][0]["coordination"]["state"], "running")
        for _ in range(2):
            for agent in self.agents.values():
                agent.cycle()
        self.assertEqual(len(self.world.offers), 3)
        self.assertEqual(sum(o["status"] == "queued" for o in self.world.offers.values()), 3)
        self.world.advance()
        for agent in self.agents.values():
            agent.cycle()
        self.assertEqual(sum(d["cash"] for d in self.world.teams.values()), 1500 - 6)
        self.assertEqual(self.cycles.mine("t01")["proposals"][0]["coordination"]["state"], "participant_confirmed_complete")
        self.assertEqual(len([c for c in self.world.calls if c[1:3] == ("POST", "/api/offers")]), 3)
    def test_no_actions_until_all_buy_in(self):
        self.propose()
        self.agents["t01"].cycle()
        self.assertNotIn("actions", self.cycles.mine("t01")["proposals"][0])
        self.assertFalse(any(c[1] != "GET" for c in self.world.calls))
    def test_manual_default_requires_exact_view_approval(self):
        proposal = self.propose()
        agent = self.agents["t01"]
        agent.policy["autonomous"] = False
        agent.cycle()
        self.assertEqual(self.cycles.mine("t01")["proposals"][0]["coordination"]["approved_count"], 0)
        agent.approve = proposal["view_id"]
        agent.cycle()
        self.assertEqual(self.cycles.mine("t01")["proposals"][0]["coordination"]["approved_count"], 1)
    def test_live_limits_and_partial_risk_mandatory(self):
        for field in ("reserve", "max_trade", "max_hour", "allow_partial"):
            policy = dict(POLICY)
            del policy[field]
            with self.assertRaises(ValueError):
                policy_checked(policy, True)
    def test_no_private_route_or_values_in_other_views(self):
        proposal = self.propose()
        data = json.dumps(proposal)
        self.assertNotIn("t02", data)
        self.assertNotIn("t03", data)
        self.assertNotIn("legs", proposal)
        self.assertNotIn("your_value", data)
    def test_authentication_and_identity_spoofing(self):
        self.assertEqual(self.service.handle("GET", "/v1/cycles/me")[0], 401)
        intent = self.world.intents()[1]
        self.assertEqual(self.service.handle("POST", "/v1/cycles/intents", intent,
                         {"Authorization": "Bearer md16_t01"})[0], 409)
    def test_expired_or_wrong_version_consent_refused(self):
        proposal = self.propose()
        body = {"view_id": "wrong", "approved": True, "allow_partial": True}
        with self.assertRaises(ValueError):
            self.cycles.update("t01", proposal["route_id"], body)
        self.world.tick = 18
        body["view_id"] = proposal["view_id"]
        with self.assertRaises(ValueError):
            self.cycles.update("t01", proposal["route_id"], body)
    def test_changed_private_value_stops_and_survives_restart(self):
        self.approve_all()
        self.world.teams["t01"]["assets"][0]["your_value"] = 101
        with self.assertRaises(ValueError):
            self.agents["t01"].cycle()
        agent = Agent(Api(self.world, "t01"), LocalCoordinator(self.service, "t01"), POLICY,
                      self.root / "t01" / "state.json", True)
        with self.assertRaises(ValueError):
            agent.cycle()
        self.assertFalse(self.world.offers)
    def test_wrong_fee_closed_clock_duels_no_writes(self):
        self.propose()
        for field, value in (("venue_fee", 0), ("doors", "closed"), ("paused", True), ("duels", [{"status": "open"}])):
            original = getattr(self.world, field)
            setattr(self.world, field, value)
            self.agents["t01"].cycle()
            setattr(self.world, field, original)
        self.assertFalse(any(c[1] != "GET" for c in self.world.calls))
    def test_429_recovery_and_no_duplicate_post(self):
        self.approve_all()
        self.world.error = m.ApiError("wait_for_tick", status=429, extra={"next_tick": 11})
        self.agents["t01"].cycle()
        self.assertFalse(self.world.offers)
        self.world.tick = 11
        self.agents["t01"].cycle()
        self.agents["t01"].cycle()
        self.assertEqual(len(self.world.offers), 1)
    def test_uncertain_write_never_retried(self):
        self.approve_all()
        self.world.error = m.ApiError("network", "timeout")
        with self.assertRaises(ValueError):
            self.agents["t01"].cycle()
        with self.assertRaises(ValueError):
            self.agents["t01"].cycle()
        self.assertFalse(self.world.offers)
    def test_cancel_only_own_offer_using_actual_expiry(self):
        self.approve_all()
        self.agents["t01"].cycle()
        offer = next(iter(self.world.offers.values()))
        self.assertEqual(offer["expires_tick"], 50)
        self.world.tick = 18
        self.agents["t01"].cleanup(18)
        self.assertEqual(offer["status"], "cancelled")
    def test_stalled_and_failed_negotiation_detection(self):
        api, state = self.agents["t01"].api, {}
        api.threads = [{"with": "t02", "status": "open", "messages": [], "standing_offers": [
            {"maker": "t01", "give": {"assets": [101]}, "want": {"cards": ["CHA-01"]}}]}]
        self.assertEqual(leads(api, POLICY, state, 10), [])
        result = leads(api, POLICY, state, 12)
        self.assertEqual(result[0][:2], (101, "CHA-01"))
        self.assertEqual(result[0][2]["kind"], "stalled_negotiation")
        api.threads[0]["status"] = "walked"
        self.assertEqual(leads(api, POLICY, {}, 12)[0][2]["kind"], "failed_negotiation")
    def test_dry_run_never_posts_or_uploads(self):
        self.propose()
        self.agents["t01"].live = False
        self.agents["t01"].cycle()
        self.assertEqual(self.cycles.mine("t01")["proposals"][0]["coordination"]["approved_count"], 0)
        self.assertFalse(any(c[1] != "GET" for c in self.world.calls))
    def test_token_transport_rejects_bazaar_keys_and_insecure_hosts(self):
        with self.assertRaises(ValueError):
            Coordinator("https://example.com", "tk_secret")
        with self.assertRaises(ValueError):
            Coordinator("http://example.com", "md16_test")

    def test_partial_completion_preserves_safe_first_leg(self):
        self.approve_all()
        for agent in self.agents.values():
            agent.cycle()
        self.world.advance()  # only t03's purchase has queued so far
        proposal = self.cycles.mine("t01")["proposals"][0]
        self.cycles.update("t01", proposal["route_id"], {"view_id": proposal["view_id"], "approved": False, "allow_partial": True})
        count = len([c for c in self.world.calls if c[2].endswith("/accept")])
        for agent in self.agents.values():
            agent.cycle()
        self.assertEqual(len([c for c in self.world.calls if c[2].endswith("/accept")]), count)
        self.assertEqual(self.world.teams["t03"]["cash"], 398)
        self.assertTrue(any(a["ref"] == "LAT-01" for a in self.world.teams["t03"]["assets"]))

    def test_reserve_changed_after_approval_prevents_purchase(self):
        self.approve_all()
        self.agents["t01"].cycle()
        self.agents["t02"].cycle()
        self.world.teams["t03"]["cash"] = 201
        with self.assertRaises(ValueError):
            self.agents["t03"].cycle()
        self.assertFalse(any(c[2].endswith("/accept") for c in self.world.calls))

    def test_human_gate_preserves_original_facts(self):
        agent = self.agents["t01"]
        with self.assertRaises(ValueError):
            agent.stop("original conflict")
        original = agent.marker.read_text()
        with self.assertRaises(ValueError):
            agent.stop("restart should not erase facts")
        self.assertEqual(agent.marker.read_text(), original)

    def test_five_party_cycles_are_supported(self):
        rows = []
        for i in range(5):
            rows.append(dict(team=f"t{i+1:02}", asset=100+i, give=f"S{i}-01", want=f"S{(i+1)%5}-01",
                             ask=100, bid=120, observed_tick=10, expires_tick=18, shared_with_consent=True,
                             evidence={"kind": "stalled_negotiation", "id": "synthetic"}))
        routes = t.discover(rows, 10, max_teams=6, partial=True)
        self.assertEqual(len(routes), 1)
        self.assertEqual(len(routes[0]["legs"]), 5)
        t.validate_route(routes[0], 10)

    def test_human_reconciliation_requires_real_own_offer(self):
        self.approve_all()
        self.world.error = m.ApiError("network", "timeout")
        agent = self.agents["t01"]
        with self.assertRaises(ValueError):
            agent.cycle()
        key = next(key for key, value in agent.state["writes"].items() if value["status"] == "uncertain")
        with self.assertRaises(ValueError):
            agent.reconcile(key, 999)
        action = agent.state["writes"][key]["action"]
        response = agent.api.call("POST", "/api/offers", {"venue": "v16", "to": action["buyer"],
                                  "give": {"assets": [action["asset"]]}, "want": {"cash": action["cash"]}})
        before = len([c for c in self.world.calls if c[1] != "GET"])
        agent.reconcile(key, response["offer"]["id"])
        self.assertEqual(agent.state["writes"][key]["status"], "done")
        self.assertEqual(before, len([c for c in self.world.calls if c[1] != "GET"]))
        self.assertTrue(agent.marker.exists())  # evidence alone never clears the human gate

    def test_actual_fee_conflict_stops_instead_of_claiming_success(self):
        self.approve_all()
        for _ in range(2):
            for agent in self.agents.values():
                agent.cycle()
        self.world.advance()
        for event in self.world.events:
            event["payload"]["fee"] = 999
        with self.assertRaisesRegex(ValueError, "actual settlement price/fee"):
            self.agents["t01"].cycle()
        self.assertTrue(self.agents["t01"].marker.exists())

    def test_competing_economic_routes_require_human_even_in_auto(self):
        rows = self.world.intents()
        alternative = dict(rows[1], team="t04", asset=401, ask=110)
        with self.store._lock:
            for row in rows + [alternative]:
                self.store._db.execute("INSERT INTO cycle_intents VALUES (?, ?)", (row["team"], json.dumps(row)))
            self.store._db.commit()
        self.cycles.submit("t01", rows[0])
        proposal = self.cycles.mine("t01")["proposals"][0]
        self.assertEqual(proposal["coordination"]["competing_terms"], [{"cash_paid": 110, "buyer_fee": 3, "participants": 3}])
        self.agents["t01"].cycle()
        self.assertEqual(self.cycles.mine("t01")["proposals"][0]["coordination"]["approved_count"], 0)
        self.agents["t01"].approve = proposal["view_id"]
        self.agents["t01"].cycle()
        self.assertEqual(self.cycles.mine("t01")["proposals"][0]["coordination"]["approved_count"], 1)


if __name__ == "__main__":
    unittest.main()
