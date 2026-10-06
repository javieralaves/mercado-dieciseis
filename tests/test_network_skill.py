"""The local skill never posts an offer that could lose a team value, and a dry run sends nothing."""
import io
import math
import unittest
from contextlib import redirect_stdout

from bazaar.marketplace.network.skill import mercado16 as m
from bazaar.marketplace.network.skill.mercado16 import Settings, ask_price, bid_price, fee_on, plan

CATALOG = {"sets": [{"id": "LAT", "cards": [
    {"id": "LAT-01", "name": "Caña", "book": 10, "page": True, "hidden": False},
    {"id": "LAT-02", "name": "Rastro", "book": 10, "page": True, "hidden": False},
    {"id": "LAT-03", "name": "Corrala", "book": 30, "page": True, "hidden": False},
    {"id": "LAT-12", "name": "Epic", "book": 200, "page": False, "hidden": False},
    {"id": "LAT-13", "name": "Hidden", "book": 0, "page": False, "hidden": True},
]}]}


def card(asset_id, ref, value):
    return {"id": asset_id, "kind": "card", "ref": ref, "name": ref, "your_value": value}


def team(team_id, cash, assets):
    return {"id": team_id, "cash": cash, "assets": assets}


FEES = [(0, 0), (100, 0), (200, 0), (500, 1)]


class Pricing(unittest.TestCase):
    def test_an_ask_always_nets_the_value_plus_margin_after_the_fee(self):
        for bps, per in FEES:
            for value in (0.4, 1.1, 2.8, 9.0, 83.9, 250.0):
                price = ask_price(value, 0.10, bps, per)
                self.assertGreaterEqual(price - fee_on(price, bps, per), value * 1.10)
                self.assertGreater(price, value)

    def test_a_bid_never_costs_more_than_the_value_minus_margin_with_the_fee(self):
        for bps, per in FEES:
            for value in (0.5, 1.5, 9.0, 83.9, 250.0):
                price = bid_price(value, 0.10, bps, per)
                if price:
                    self.assertLessEqual(price + fee_on(price, bps, per), value * 0.90)
                    self.assertLessEqual(price + fee_on(price, bps, per), value - 1)

    def test_no_bid_when_the_value_is_too_small(self):
        self.assertEqual(bid_price(1.5, 0.10, 0, 0), 0)


    def test_zero_margin_keeps_strict_fee_adjusted_bounds(self):
        for bps, per in FEES:
            for value in (0, 2.8, 9, 100, 180):
                ask = ask_price(value, 0, bps, per)
                self.assertGreater(ask - fee_on(ask, bps, per), value)
                bid = bid_price(value, 0, bps, per)
                if bid:
                    self.assertLess(bid + fee_on(bid, bps, per), value)

    def test_large_bid_is_not_arbitrarily_capped(self):
        me = team("t07", 500, [])
        offers, _ = plan(me, CATALOG, {"LAT-03": 180}, [], 0, 0, Settings())
        self.assertEqual(offers[0].price, 179)
        offers, _ = plan(me, CATALOG, {"LAT-03": 180}, [], 0, 0, Settings(max_price=80))
        self.assertEqual(offers[0].price, 80)

    def test_reserve_accounts_for_fees(self):
        offers, _ = plan(team("t07", 200, []), CATALOG, {"LAT-03": 110}, [], 500, 1, Settings())
        self.assertLessEqual(sum(o.price + fee_on(o.price, 500, 1) for o in offers), 100)

    def test_unvalued_and_unfamiliar_fees_fail_closed(self):
        with self.assertRaises(m.ApiError) as e:
            plan(team("t07", 500, []), CATALOG, {"LAT-03": None}, [], 0, 0, Settings())
        self.assertEqual(e.exception.code, "human_required")
        with self.assertRaises(m.ApiError):
            ask_price(100, 0, 10000, 0)


class SimulatedAutoBook(unittest.TestCase):
    """Two teams run the skill; the venue crosses lowest ask with highest bid at the midpoint."""

    def cross(self, asks, bids):
        trades = []
        for ref in {o.card for o in asks} & {o.card for o in bids}:
            ask = min((o for o in asks if o.card == ref), key=lambda o: o.price)
            bid = max((o for o in bids if o.card == ref), key=lambda o: o.price)
            if bid.price >= ask.price:
                trades.append((ask, bid, (ask.price + bid.price) / 2))
        return trades

    def test_every_cross_leaves_both_teams_better_off_at_their_own_values(self):
        seller = team("t03", 300, [card(1, "LAT-01", 83.9), card(2, "LAT-02", 2.8), card(3, "LAT-02", 2.8)])
        buyer = team("t07", 300, [card(9, "LAT-01", 5.0)])
        buyer_values = {"LAT-02": 60.0, "LAT-03": 40.0}
        for bps, per in FEES:
            s = Settings(venue="v16")
            asks, _ = plan(seller, CATALOG, {}, [], bps, per, Settings(venue="v16", only_sell=True))
            bids, _ = plan(buyer, CATALOG, buyer_values, [], bps, per, s)
            trades = self.cross(asks, [b for b in bids if b.side == "buy"])
            self.assertEqual(len(trades), 1)
            for ask, bid, mid in trades:
                for price in (math.floor(mid), math.ceil(mid)):
                    fee = fee_on(price, bps, per)
                    self.assertGreater(price - fee, ask.limit, "seller net above its value")
                    self.assertLess(price + fee, bid.limit, "buyer cost below its value")

    def test_the_skill_never_sells_the_last_copy_unless_told(self):
        me = team("t03", 300, [card(1, "LAT-01", 83.9), card(2, "LAT-02", 2.8), card(3, "LAT-02", 2.8)])
        asks, _ = plan(me, CATALOG, {}, [], 0, 0, Settings(only_sell=True))
        self.assertEqual([(o.card, o.asset) for o in asks], [("LAT-02", 3)])
        asks, _ = plan(me, CATALOG, {}, [], 0, 0, Settings(only_sell=True, sell={"LAT-01"}))
        self.assertIn(("LAT-01", 1), [(o.card, o.asset) for o in asks])
        self.assertGreater(next(o.price for o in asks if o.card == "LAT-01"), 83.9)
        asks, _ = plan(me, CATALOG, {}, [], 0, 0, Settings(only_sell=True, protect={"LAT-02"}))
        self.assertEqual(asks, [])


class Limits(unittest.TestCase):
    def test_bids_fit_the_cash_reserve_including_bids_already_open(self):
        me = team("t07", 200, [])
        values = {"LAT-01": 90.0, "LAT-02": 90.0, "LAT-03": 90.0}
        open_bid = {"maker": "t07", "status": "open", "venue": "rastro", "give": {"cash": 50, "assets": []},
                    "want": {"types": ["card:LAT-13"]}}
        bids, notes = plan(me, CATALOG, values, [open_bid], 0, 0, Settings(reserve=100, max_price=80))
        self.assertEqual(sum(o.price for o in bids), 0)
        self.assertIn(m.NO_CASH, {reason for reason, _ in notes})
        bids, _ = plan(me, CATALOG, values, [], 0, 0, Settings(reserve=100, max_price=80))
        self.assertLessEqual(sum(o.price for o in bids), 100)
        self.assertTrue(all(o.price <= 80 for o in bids))

    def test_running_twice_does_not_double_post(self):
        me = team("t03", 300, [card(2, "LAT-02", 2.8), card(3, "LAT-02", 2.8)])
        mine = [
            {"maker": "t03", "status": "open", "venue": "v16", "give": {"assets": [{"id": 3}]}, "want": {"cash": 4}},
            {"maker": "t03", "status": "open", "venue": "v16", "give": {"cash": 30, "assets": []},
             "want": {"types": ["card:LAT-03"]}},
            {"maker": "t09", "status": "open", "venue": "v16", "give": {"cash": 30, "assets": []},
             "want": {"types": ["card:LAT-01"]}},
        ]
        offers, notes = plan(me, CATALOG, {"LAT-01": 50.0, "LAT-03": 50.0}, mine, 0, 0, Settings())
        self.assertEqual([(o.side, o.card) for o in offers], [("buy", "LAT-01")])
        self.assertEqual(sorted(notes), [(m.ON_OFFER, "LAT-02"), (m.BIDDING, "LAT-03")])

    def test_multiple_spares_are_left_for_human_review(self):
        me = team("t03", 300, [card(i, "LAT-02", 10) for i in (1, 2, 3)])
        offers, notes = plan(me, CATALOG, {}, [], 0, 0, Settings(only_sell=True))
        self.assertEqual(offers, [])
        self.assertIn((m.HUMAN_SPARES, "LAT-02"), notes)

    def test_only_missing_page_cards_are_bid_on_by_default(self):
        me = team("t03", 300, [card(1, "LAT-01", 83.9)])
        self.assertEqual(m.buy_candidates(me, CATALOG, Settings()), ["LAT-02", "LAT-03"])
        self.assertEqual(m.buy_candidates(me, CATALOG, Settings(buy={"LAT-12"})), ["LAT-02", "LAT-03", "LAT-12"])


class FakeApi:
    def __init__(self, me, venue, offers=(), limits=None):
        self.me, self.venue, self.offers = me, venue, list(offers)
        self.limits = limits or {"offers_per_team_per_tick": 12, "max_open_offers_per_team": 30}
        self.posts, self.ticks = [], 0

    def call(self, method, path, body=None, query=None):
        if method == "GET" and path == "/api/venues":
            return {"venues": [self.venue]}
        if method == "GET" and path == "/api/me":
            return self.me
        if method == "GET" and path == "/api/catalog":
            return CATALOG
        if method == "GET" and path == "/api/me/value":
            return {"your_value": 60.0}
        if method == "GET" and path == "/api/me/offers":
            return {"offers": self.offers}
        if method == "GET" and path == "/api/clock":
            return {"limits": self.limits, "next_tick_in": 0}
        if method == "POST" and path == "/api/offers":
            self.posts.append(body)
            self.offers.append({"maker": self.me["id"], "status": "open", "venue": body["venue"], **body})
            return {"id": len(self.posts)}
        raise AssertionError(f"unexpected {method} {path}")

    def wait_tick(self):
        self.ticks += 1


V16 = {"venue": "v16", "name": "Puesto de Team 16", "owner": "t16", "status": "open", "fee_bps": 0,
       "fee_per_card": 0, "rules": {"mechanism": "auto"}}


class Run(unittest.TestCase):
    def quiet(self, fn, *args):
        with redirect_stdout(io.StringIO()) as out:
            code = fn(*args)
        return code, out.getvalue()

    def test_a_dry_run_sends_nothing(self):
        api = FakeApi(team("t03", 300, [card(2, "LAT-02", 2.8), card(3, "LAT-02", 2.8)]), V16)
        code, out = self.quiet(m.run, api, Settings(), False)
        self.assertEqual(code, 0)
        self.assertEqual(api.posts, [])
        self.assertIn("Dry run: nothing was sent", out)
        self.assertIn("SELL LAT-02", out)

    def test_post_sends_ordinary_offers_on_the_venue(self):
        api = FakeApi(team("t03", 300, [card(2, "LAT-02", 2.8), card(3, "LAT-02", 2.8)]), V16)
        self.quiet(m.run, api, Settings(), True)
        sells = [p for p in api.posts if "assets" in p["give"]]
        self.assertEqual(sells, [{"venue": "v16", "give": {"assets": [3]}, "want": {"cash": 4}, "expires_in_ticks": 120}])
        self.assertTrue(all(p["venue"] == "v16" for p in api.posts))
        self.assertTrue(all(set(p) == {"venue", "give", "want", "expires_in_ticks"} for p in api.posts))

    def test_post_waits_a_tick_past_the_per_tick_limit_and_stops_at_the_open_limit(self):
        api = FakeApi(team("t03", 1000, []), V16, limits={"offers_per_team_per_tick": 2, "max_open_offers_per_team": 3})
        self.quiet(m.run, api, Settings(reserve=0, max_bids=6), True)
        self.assertEqual(len(api.posts), 3)
        self.assertEqual(api.ticks, 1)

    def test_a_team_cannot_run_it_on_its_own_venue(self):
        api = FakeApi(team("t16", 300, [card(2, "LAT-02", 2.8), card(3, "LAT-02", 2.8)]), V16)
        code, out = self.quiet(m.run, api, Settings(), True)
        self.assertEqual(code, 2)
        self.assertEqual(api.posts, [])
        self.assertIn("own venue", out)

    def test_a_closed_venue_posts_nothing(self):
        api = FakeApi(team("t03", 300, [card(2, "LAT-02", 2.8), card(3, "LAT-02", 2.8)]), {**V16, "status": "closed"})
        code, _ = self.quiet(m.run, api, Settings(), True)
        self.assertEqual((code, api.posts), (2, []))


if __name__ == "__main__":
    unittest.main()

