"""Synthetic fixtures, not claims about actual participant negotiations."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from bazaar.marketplace.network.skill.triangles import (
    BLOCKED, assess, discover, execute, fee, interest_receipt, main,
    private_view, review_local, validate_route, write_private, prepare_intent,
)


def intents():
    return [dict(team=team, asset=i, give=give, want=want, ask=100, bid=120,
                 observed_tick=10, expires_tick=18, shared_with_consent=True,
                 evidence={"kind": "failed_negotiation", "id": f"synthetic-thread-{i}"})
            for i, (team, give, want) in enumerate([
                ("t01", "LAT-01", "CHA-01"), ("t02", "CHA-01", "SAL-01"),
                ("t03", "SAL-01", "LAT-01")], 101)]


class Triangles(unittest.TestCase):
    def setUp(self):
        self.route = discover(intents(), 10)[0]
        self.view = private_view(self.route, "t01", 10)

    def assessment(self, **updates):
        args = dict(view=self.view, team="t01", tick=10, outgoing_value=90,
                    incoming_value=130, cash=500, reserve=100, held_asset=True, spare=True)
        args.update(updates)
        return assess(**args)

    def test_three_party_cycle_and_fee_balance(self):
        self.assertEqual(len(discover(intents(), 10)), 1)
        self.assertEqual(sum(leg["buyer_fee"] for leg in self.route["legs"]), 6)
        self.assertEqual(fee(101), 3)
        self.assertEqual(self.route["execution_status"], BLOCKED)
        validate_route(self.route, 10)

    def test_no_two_party_routes(self):
        rows = intents()[:2]
        rows[1]["want"] = rows[0]["give"]
        self.assertEqual(discover(rows, 10), [])

    def test_fee_can_make_route_unaffordable(self):
        rows = intents()
        rows[0]["bid"] = 101
        self.assertEqual(discover(rows, 10), [])

    def test_private_recipient_view_hides_other_teams_and_route(self):
        text = json.dumps(self.view)
        self.assertNotIn("t02", text)
        self.assertNotIn("t03", text)
        self.assertNotIn("SAL-01", text)
        self.assertNotIn("evidence", self.view)
        with self.assertRaises(ValueError):
            private_view(self.route, "t04", 10)

    def test_input_cannot_include_private_values_or_keys(self):
        rows = intents()
        rows[0]["your_value"] = 90
        with self.assertRaises(ValueError):
            discover(rows, 10)

    def test_stale_or_unconsented_intent_refused(self):
        for field, value in (("shared_with_consent", False), ("expires_tick", 10), ("observed_tick", 11)):
            rows = intents()
            rows[0][field] = value
            with self.assertRaises(ValueError):
                discover(rows, 10)

    def test_duplicate_team_or_asset_refused(self):
        for field in ("team", "asset"):
            rows = intents()
            rows[1][field] = rows[0][field]
            with self.assertRaises(ValueError):
                discover(rows, 10)

    def test_duel_evidence_not_treated_as_asset_demand(self):
        rows = intents()
        rows[0]["evidence"]["kind"] = "duel"
        with self.assertRaises(ValueError):
            discover(rows, 10)

    def test_tampered_route_and_view_invalidate_consent(self):
        route = copy.deepcopy(self.route)
        route["legs"][0]["cash"] += 1
        with self.assertRaises(ValueError):
            validate_route(route, 10)
        self.view["cash_paid"] += 1
        with self.assertRaises(ValueError):
            self.assessment()

    def test_current_private_value_strict_bounds(self):
        self.assertTrue(self.assessment()["eligible_for_interest"])
        for update in (dict(outgoing_value=100), dict(incoming_value=102), dict(incoming_value=101)):
            self.assertFalse(self.assessment(**update)["eligible_for_interest"])

    def test_cash_does_not_include_future_sale_and_other_commitments(self):
        self.assertFalse(self.assessment(cash=201)["eligible_for_interest"])
        self.assertFalse(self.assessment(cash=500, commitments=299)["eligible_for_interest"])

    def test_protection_page_and_uncertainty_fail_closed(self):
        for update in (dict(spare=False), dict(protected=True), dict(page_break=True), dict(held_asset=False)):
            self.assertFalse(self.assessment(**update)["eligible_for_interest"])
        with self.assertRaises(ValueError):
            self.assessment(outgoing_value=float("nan"))

    def test_receipt_is_interest_only_and_no_values_shared(self):
        receipt = interest_receipt(self.view, self.assessment(), True, 10)
        self.assertFalse(receipt["execution_authorized"])
        self.assertNotIn("private", json.dumps(receipt))
        self.assertNotIn("surplus", receipt)
        for yes, tick in ((False, 10), (True, 18)):
            with self.assertRaises(ValueError):
                interest_receipt(self.view, self.assessment(), yes, tick)

    def test_no_execution_even_after_interest(self):
        receipt = interest_receipt(self.view, self.assessment(), True, 10)
        with self.assertRaisesRegex(RuntimeError, "No trades executed"):
            execute(self.route, [receipt] * 3, human_yes=True, atomic=True)

    def test_private_files_and_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "intents.json"
            source.write_text(json.dumps(intents()))
            out = Path(tmp) / "proposals"
            self.assertEqual(main([str(source), "--tick", "10", "--out", str(out)]), 0)
            files = list(out.rglob("*.json"))
            self.assertEqual(len(files), 4)
            self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in files))
            with self.assertRaises(FileExistsError):
                write_private(files[0], {})

    def test_live_review_get_only_and_state_conflict(self):
        view = self.view
        class Api:
            def __init__(self):
                self.calls = []
                self.cash = 500
            def call(self, method, path, query=None):
                self.calls.append((method, path))
                if path == "/api/clock":
                    return {"doors": "open", "tick": 10, "paused": False}
                if path == "/api/me":
                    return {"id": "t01", "cash": self.cash, "assets": [
                        {"id": asset, "ref": "LAT-01", "kind": "card", "your_value": 90}
                        for asset in (101, 999)]}
                if path == "/api/me/offers":
                    return {"offers": []}
                if path == "/api/catalog":
                    return {"sets": [{"cards": [{"id": "CHA-01", "page": True}]}]}
                if path == "/api/venues":
                    return {"venues": [{"id": "v16", "owner": "t16", "status": "open",
                                        "fee_bps": 0, "fee_per_card": 0, "rules": {"mechanism": "auto"}}]}
                if path == "/api/me/value":
                    return {"your_value": 130}
                raise AssertionError(path)
        api = Api()
        report, tick = review_local(api, view)
        self.assertTrue(report["eligible_for_interest"])
        self.assertFalse(report["venue_ready"])
        self.assertTrue(all(method == "GET" for method, _ in api.calls))
        selected = prepare_intent(api, 101, "CHA-01", {"kind": "failed_negotiation", "id": "synthetic"}, True)
        self.assertEqual(selected["ask"], 91)
        self.assertLess(selected["bid"], 130)
        self.assertEqual(set(selected), set(intents()[0]))
        with self.assertRaises(ValueError):
            prepare_intent(api, 101, "CHA-01", {"kind": "failed_negotiation", "id": "synthetic"}, False)
        original = api.call
        def changing(method, path, query=None):
            result = original(method, path, query)
            if path == "/api/me/value":
                api.cash = 499
            return result
        api.call = changing
        with self.assertRaisesRegex(ValueError, "state changed"):
            review_local(api, view)


if __name__ == "__main__":
    unittest.main()
