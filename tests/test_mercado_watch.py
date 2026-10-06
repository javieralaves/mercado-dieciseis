import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from bazaar.marketplace.network.skill import mercado16 as m
from tests.test_network_skill import FakeApi, V16, card, team


class WatchApi(FakeApi):
    def __init__(self, me, venue=V16):
        super().__init__(me, dict(venue))
        self.tick, self.events, self.deletes = 10, [], []
        self.paused, self.doors, self.throttle = False, "open", False

    def call(self, method, path, body=None, query=None):
        if method == "GET" and path == "/api/clock":
            return {"tick": self.tick, "doors": self.doors, "paused": self.paused,
                    "next_tick_in": 0, "tick_seconds": 15, "limits": self.limits}
        if method == "GET" and path == "/api/venues":
            return {"venues": [self.venue, {**V16, "venue": "rastro", "owner": None}]}
        if method == "GET" and path == "/api/feed":
            return {"events": self.events}
        if method == "GET" and path == "/api/me/offers":
            self.offers = [o for o in self.offers if o.get("expires_tick", self.tick + 1) > self.tick]
            return {"offers": self.offers}
        if method == "POST" and path == "/api/offers":
            if self.throttle:
                self.throttle = False
                raise m.ApiError("wait_for_tick", status=429, extra={"next_tick": self.tick + 1})
            super().call(method, path, body, query)
            row = self.offers[-1]
            row.update(id=len(self.posts), created_tick=self.tick, expires_tick=self.tick + 3)
            return dict(row)
        if method == "DELETE":
            oid = int(path.rsplit("/", 1)[1])
            self.deletes.append(oid)
            self.offers = [o for o in self.offers if o["id"] != oid]
            return {"cancelled": oid}
        return super().call(method, path, body, query)


class Maintenance(unittest.TestCase):
    def cycle(self, api, s, state, post=True):
        with redirect_stdout(io.StringIO()):
            return m.watch_cycle(api, s, post, state)

    def test_no_duplicate_and_actual_expiry_replaces_missing_quotes(self):
        api = WatchApi(team("t03", 300, []))
        s, state = m.Settings(max_bids=1), {}
        self.cycle(api, s, state)
        self.assertEqual(len(api.posts), 1)
        self.assertEqual(state["owned"][1]["expires_tick"], 13)  # requested 120; server granted 3
        api.tick = 11
        self.cycle(api, s, state)
        self.assertEqual(len(api.posts), 1)
        api.tick = 13
        self.cycle(api, s, state)
        self.assertEqual(len(api.posts), 2)

    def test_filled_card_is_not_reposted_as_a_sale(self):
        api = WatchApi(team("t03", 300, [card(2, "LAT-02", 2.8), card(3, "LAT-02", 2.8)]))
        s, state = m.Settings(only_sell=True), {}
        self.cycle(api, s, state)
        api.tick = 11
        api.me["assets"] = [api.me["assets"][0]]
        api.offers = []
        api.events = [{"type": "settlement", "tick": 11, "payload": {"venue": "v16", "price": 4,
                      "items": [{"id": 3, "ref": "LAT-02", "frm": "t03", "to": "t07"}]}}]
        self.cycle(api, s, state)
        self.assertEqual(len(api.posts), 1)

    def test_changed_value_cancels_unsafe_quote_before_replacement(self):
        api = WatchApi(team("t03", 300, [card(2, "LAT-02", 2.8), card(3, "LAT-02", 2.8)]))
        s, state = m.Settings(only_sell=True), {}
        self.cycle(api, s, state)
        api.tick = 11
        for a in api.me["assets"]:
            a["your_value"] = 10
        self.cycle(api, s, state)
        self.assertEqual(api.deletes, [1])
        self.assertGreater(api.posts[-1]["want"]["cash"], 10)
        api.tick = 12
        self.cycle(api, s, state)
        self.assertEqual(api.deletes, [1])

    def test_reserve_after_another_bid_consumes_cash(self):
        api = WatchApi(team("t03", 300, []))
        s, state = m.Settings(max_bids=1), {}
        self.cycle(api, s, state)
        api.tick = 11
        api.offers.append({"id": 99, "maker": "t03", "status": "open", "venue": "rastro",
                           "give": {"cash": 200}, "want": {"cards": ["LAT-12"]}, "expires_tick": 30})
        self.cycle(api, s, state)
        self.assertEqual(api.deletes, [1])
        self.assertEqual(len(api.posts), 1)

    def test_closed_venue_and_dry_watch_never_write(self):
        for post in (False, True):
            api = WatchApi(team("t03", 300, []), {**V16, "status": "closed"})
            self.cycle(api, m.Settings(), {}, post)
            self.assertEqual((api.posts, api.deletes), ([], []))
        api = WatchApi(team("t03", 300, []))
        self.cycle(api, m.Settings(), {}, False)
        self.assertEqual((api.posts, api.deletes), ([], []))

    def test_paused_clock_sleeps_without_spinning(self):
        api = WatchApi(team("t03", 300, []))
        api.paused = True
        with patch.object(m.time, "sleep", side_effect=KeyboardInterrupt) as sleep, redirect_stdout(io.StringIO()):
            with self.assertRaises(KeyboardInterrupt):
                m.watch(api, m.Settings(), False)
        self.assertGreaterEqual(sleep.call_args.args[0], 15)
        self.assertEqual(api.posts, [])

    def test_429_defers_to_next_tick_and_replans(self):
        api = WatchApi(team("t03", 300, []))
        api.throttle = True
        calls = []
        def advance(delay):
            calls.append(delay)
            if len(calls) == 1:
                api.tick = 11
            else:
                raise KeyboardInterrupt
        with tempfile.TemporaryDirectory() as tmp, patch.object(m.time, "sleep", side_effect=advance), redirect_stdout(io.StringIO()):
            with self.assertRaises(KeyboardInterrupt):
                m.watch(api, m.Settings(max_bids=1), True, marker=Path(tmp) / "stop.json")
        self.assertEqual(len(api.posts), 1)
        self.assertEqual(api.offers[0]["created_tick"], 11)

    def test_unexplained_disappearance_is_sticky_and_cannot_repost(self):
        api = WatchApi(team("t03", 300, []))
        def vanish(delay):
            api.tick = 11
            api.offers = []
        with tempfile.TemporaryDirectory() as tmp, patch.object(m.time, "sleep", side_effect=vanish), redirect_stdout(io.StringIO()):
            marker = Path(tmp) / "stop.json"
            self.assertEqual(m.watch(api, m.Settings(max_bids=1), True, marker=marker), 2)
            self.assertTrue(marker.exists())
            self.assertEqual(m.watch(api, m.Settings(max_bids=1), True, marker=marker), 2)
        self.assertEqual(len(api.posts), 1)

    def test_inventory_without_visible_history_and_fee_changes_need_human(self):
        api = WatchApi(team("t03", 300, []))
        state = {}
        self.cycle(api, m.Settings(max_bids=1), state)
        api.tick = 11
        api.me["assets"].append(card(7, "LAT-02", 10))
        with self.assertRaises(m.ApiError) as e:
            self.cycle(api, m.Settings(max_bids=1), state)
        self.assertEqual(e.exception.code, "human_required")
        api.me["assets"] = []
        api.venue["fee_bps"] = 500
        with self.assertRaises(m.ApiError):
            self.cycle(api, m.Settings(max_bids=1), state)

    def test_per_tick_and_open_limits_are_respected(self):
        api = WatchApi(team("t03", 1000, []))
        api.limits = {"offers_per_team_per_tick": 1, "max_open_offers_per_team": 2}
        state = {}
        self.cycle(api, m.Settings(), state)
        self.cycle(api, m.Settings(), state)
        self.assertEqual(len(api.posts), 1)
        api.tick = 11
        self.cycle(api, m.Settings(), state)
        self.assertEqual(len(api.posts), 2)
        api.tick = 12
        self.cycle(api, m.Settings(), state)
        self.assertEqual(len(api.posts), 2)
