"""Local Mercado cycle agent. Default read-only; live requires explicit limits.

Only selected card intentions/price bounds and execution receipts go to the
coordinator. Bazaar keys and private values never go there. Partial fills allowed
only after opt-in; every leg revalues independently before writing.
"""
from __future__ import annotations
import argparse
from collections import Counter
import fcntl
import json
import os
import re
from pathlib import Path
import time
import urllib.parse
import urllib.request
import urllib.error

try:
    from . import mercado16 as m
    from . import triangles as t
except ImportError:
    import mercado16 as m
    import triangles as t

POLICY_FIELDS = {"reserve", "max_trade", "max_hour", "min_surplus", "max_participants",
                 "protect", "sell", "buy", "share_selected_intents", "allow_partial", "autonomous"}


def policy_checked(policy, live=False):
    if not isinstance(policy, dict) or set(policy) - POLICY_FIELDS:
        raise ValueError("policy has unsupported fields; no keys or secrets belong in it")
    for field in ("reserve", "max_trade", "max_hour", "min_surplus"):
        if field in policy:
            t.integer(policy[field], field)
    if live and any(field not in policy for field in ("reserve", "max_trade", "max_hour", "min_surplus")):
        raise ValueError("live requires explicit reserve, max_trade, max_hour and min_surplus")
    for field in ("protect", "sell", "buy"):
        if field in policy and (not isinstance(policy[field], list) or any(not isinstance(x, str) for x in policy[field])):
            raise ValueError("card selections must be lists")
    for field in ("share_selected_intents", "allow_partial", "autonomous"):
        if field in policy and type(policy[field]) is not bool:
            raise ValueError("approval policy flags must be boolean")
    size = policy.get("max_participants", 3)
    if type(size) is not int or not 3 <= size <= 6:
        raise ValueError("max_participants must be 3..6")
    if live and policy.get("allow_partial") is not True:
        raise ValueError("live requires explicit acceptance of partial completion")
    return dict(policy)


def save_state(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as out:
        json.dump(data, out, indent=2)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())
    os.replace(tmp, path)


class Coordinator:
    def __init__(self, url, token=""):
        parsed = urllib.parse.urlsplit(url)
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("coordinator URL must not contain credentials or parameters")
        if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1")):
            raise ValueError("coordinator needs HTTPS, or loopback for local tests")
        if token and not token.startswith("md16_"):
            raise ValueError("verified Mercado token required; never use a Bazaar key here")
        self.url, self.token = url.rstrip("/"), token

    def call(self, method, path, body=None):
        if not (path.startswith("/v1/cycles/") or path in ("/v1/me", "/v1/waitlist", "/v1/verify", "/v1/verify/claim")):
            raise ValueError("unsupported coordinator path")
        # No redirects: a redirect must not forward the bearer token elsewhere.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        req = urllib.request.Request(self.url + path, method=method,
            data=None if body is None else json.dumps(body).encode(),
            headers=headers)
        try:
            with urllib.request.build_opener(NoRedirect).open(req, timeout=15) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            raise ValueError(f"coordinator HTTP {error.code}; refresh/review before action") from None


def clean_view(proposal):
    return {k: v for k, v in proposal.items() if k not in ("coordination", "actions")}


def leads(api, policy, state, tick):
    """Observe own real team threads and own unfilled quotes. Never parse chat prices.

    Failed/stalled structured swaps identify both refs. Cash negotiations provide
    a desired card; an outgoing card is chosen only if exactly one allowed spare
    exists. Ambiguous choices are human decisions, never arbitrary tie-breaks.
    """
    me = api.call("GET", "/api/me")
    assets = {a["id"]: a for a in me.get("assets", []) if a.get("kind") == "card"}
    counts = Counter(a["ref"] for a in assets.values())
    catalog = api.call("GET", "/api/catalog")
    targets = set(m.buy_candidates(me, catalog, m.Settings(protect=set(policy.get("protect", [])))))
    spares = [a for a in assets.values() if counts[a["ref"]] == 2
              and a["ref"] not in policy.get("protect", [])
              and (not policy.get("sell") or a["ref"] in policy["sell"])]
    # A ref with exactly two copies yields two interchangeable IDs; pick the
    # concrete lowest ID only when no economic choice is involved.
    for ref in {a["ref"] for a in spares}:
        if len({m.private_value(a.get("your_value")) for a in spares if a["ref"] == ref}) != 1:
            raise ValueError("AskQuestions: supposedly interchangeable copies have conflicting private values")
    spares = list({a["ref"]: min((b for b in spares if b["ref"] == a["ref"]), key=lambda b: b["id"])
                   for a in spares}.values())
    cache = state.setdefault("observations", {})
    found = []
    def consider(source, offers, failed=False, activity=None):
        fingerprint = t.digest({"offers": offers, "activity": activity})
        old = cache.get(source)
        unchanged = old is not None and old["fingerprint"] == fingerprint
        since = old["since"] if unchanged else tick
        cache[source] = {"fingerprint": fingerprint, "since": since, "seen": tick}
        if not failed and tick - since < 2:
            return
        for offer in offers:
            if not isinstance(offer, dict):
                continue
            give, want = offer.get("give") or {}, offer.get("want") or {}
            if set(want) != {"cards"} or not isinstance(want["cards"], list) or len(want["cards"]) != 1:
                continue
            card = want["cards"][0]
            if not isinstance(card, str) or card not in targets or (policy.get("buy") and card not in policy["buy"]):
                continue
            outgoing = give.get("assets", [])
            outgoing = [a.get("id") if isinstance(a, dict) else a for a in outgoing]
            choices = [a for a in spares if a["id"] in outgoing] if outgoing else spares
            if len(choices) == 1:
                found.append((choices[0]["id"], card, {"kind": "failed_negotiation" if failed else "stalled_negotiation", "id": source}))
            elif len(choices) > 1:
                raise ValueError("AskQuestions: several spare cards compete for the same negotiation; narrow sell limits")
    summaries = api.call("GET", "/api/me/threads").get("threads", [])
    for summary in summaries[:6]:
        if not re.fullmatch(r"t\d{2}", str(summary.get("with", ""))):
            continue  # dealers and synthetic duels are not real-team inventory
        thread = api.call("GET", f"/api/threads/{int(summary['id'])}")
        thread = thread.get("thread", thread)
        if thread.get("status") == "deal":
            continue
        offers = [o for o in thread.get("standing_offers", []) if o.get("maker") == me["id"]]
        # Withdrawn structured messages still explain failed intent. Free text,
        # rival prices and synthetic duel items never create card commitments.
        for message in thread.get("messages", []):
            if message.get("sender") in (me["id"], "you") and isinstance(message.get("offer"), dict):
                offers.append(message["offer"])
        consider("thread:" + str(summary["id"]), offers, thread.get("status") == "walked",
                 t.digest(thread.get("messages", [])))
    mine = api.call("GET", "/api/me/offers").get("offers", [])
    for offer in mine:
        if offer.get("maker") == me["id"] and offer.get("status") in (None, "open"):
            consider("offer:" + str(offer["id"]), [offer])
    state["observations"] = {k: v for k, v in cache.items() if tick - v["seen"] <= 8}
    found = list({(asset, card): (asset, card, evidence) for asset, card, evidence in found}.values())
    if len(found) > 1:
        raise ValueError("AskQuestions: multiple actionable negotiations compete; select buy/sell limits")
    return found


def decision_report(view, report):
    return {"Decision": f"Coordinate sale of {view['give']['card']} for {view['cash_received']} P and purchase of {view['receive']['card']} for {view['cash_paid']} P + {view['buyer_fee']} P fee?",
            "Recommended action": "Approve independently safe legs" if report["eligible_for_interest"] else "Do nothing",
            "Expected upside": report["estimated_private_surplus"],
            "Worst credible downside": "Only one leg may fill; cash/assets then differ from the complete route. Future sale proceeds are never required.",
            "Private values": {"outgoing": report["outgoing_private_value"], "incoming": report["incoming_private_value"]},
            "Cash after purchase before sale": report["cash_after_purchase_before_sale"],
            "Page impact": report["page_impact"], "Evidence": {"route_id": view["route_id"], "expires_tick": view["expires_tick"]},
            "Why human judgement": "Partial completion, selected intent sharing, or configured limits/uncertainty require explicit approval.",
            "Reasons": report["reasons"], "view_id": view["view_id"]}


class Agent:
    def __init__(self, api, coordinator, policy, path, live=False, approve=None):
        self.api, self.coordinator = api, coordinator
        self.policy, self.path, self.live, self.approve = policy_checked(policy, live), Path(path), live, approve
        self.marker = self.path.with_name("HUMAN_REQUIRED_cycles.json")
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {"writes": {}, "spend": []}
        self.api.defer_writes = True

    def persist(self):
        save_state(self.path, self.state)

    def stop(self, reason):
        facts = {"decision_id": t.digest({"reason": str(reason), "state": self.state}),
                 "reason": str(reason), "recommendation": "Do nothing until human reviews; outstanding offers may still fill"}
        if not self.marker.exists():
            t.write_private(self.marker, facts)
        raise ValueError("AskQuestions: " + str(reason))

    def require_clear(self):
        gates = (self.marker, m.WATCH_MARKER, self.path.parent / "HUMAN_REQUIRED.json",
                 Path(__file__).resolve().parents[4] / "data" / "HUMAN_REQUIRED.json")
        if any(path.exists() for path in gates):
            raise ValueError("AskQuestions: an unresolved durable human gate blocks startup; review and resolve explicitly")

    def cycle(self):
        self.require_clear()
        clock = self.api.call("GET", "/api/clock")
        if clock.get("doors") != "open" or clock.get("paused"):
            return clock
        tick = clock["tick"]
        # Duels have priority. No changed duel policy or extra duel process.
        duels = self.api.call("GET", "/api/duels").get("duels", [])
        if any(d.get("status") not in ("closed", "finished", "cancelled") for d in duels):
            print("Duel wave: coordinated writes stand down.")
            return clock
        venues = self.api.call("GET", "/api/venues").get("venues", [])
        evidence = m.read_discovery(self.api, venues, clock, self.state.setdefault("public_discovery", {}))
        print("Local market context: " + evidence["coverage"] + "; own negotiations supply consented intentions.")
        proposals = self.coordinator.call("GET", "/v1/cycles/me")["proposals"]
        if not proposals:
            self.cleanup(tick)
            candidates = leads(self.api, self.policy, self.state, tick)
            self.persist()
            if candidates:
                asset, card, evidence = candidates[0]
                if self.policy.get("share_selected_intents") is not True:
                    print("AskQuestions: a failed/stalled negotiation has a candidate; enable selected-intent sharing only with explicit consent.")
                    return clock
                intent = t.prepare_intent(self.api, asset, card, evidence, True,
                                          self.policy.get("reserve", 100), self.policy.get("protect", []))
                # Sharing is a distinct opt-in; dry mode never uploads even an intent.
                if self.live:
                    self.coordinator.call("POST", "/v1/cycles/intents", intent)
                else:
                    print("Dry run: a selected intent is safe; no upload or Bazaar write.")
            return clock
        if len(proposals) != 1:
            self.stop("competing proposals require human judgement")
        proposal = proposals[0]
        view = clean_view(proposal)
        if proposal["coordination"]["participant_count"] > self.policy.get("max_participants", 3):
            print("Proposal exceeds configured participant limit; no approval.")
            return clock
        state = proposal["coordination"]["state"]
        if state == "offered":
            report, current_tick = t.review_local(self.api, view, self.policy.get("reserve", 100), self.policy.get("protect", []))
            question = decision_report(view, report)
            competing = proposal["coordination"].get("competing_terms", [])
            question["Competing route terms"] = competing
            save_state(self.path.with_name("pending_decision.json"), question)
            print(json.dumps(question, indent=2))  # private local output only
            cost = view["cash_paid"] + view["buyer_fee"]
            allowed = (report["eligible_for_interest"] and report["venue_ready"]
                       and view["execution_status"] == t.PARTIAL and self.policy.get("allow_partial") is True
                       and cost <= self.policy.get("max_trade", 0)
                       and report["estimated_private_surplus"] >= self.policy.get("min_surplus", 1)
                       and self.hour_left() >= cost)
            if self.live and allowed and ((self.policy.get("autonomous") is True and not competing) or self.approve == view["view_id"]):
                self.coordinator.call("POST", f"/v1/cycles/{view['route_id']}/decision",
                                      {"view_id": view["view_id"], "approved": True, "allow_partial": True})
                self.state.setdefault("approved", {})[view["route_id"]] = view["view_id"]
                self.persist()
            return clock
        if state != "running":
            self.cleanup(tick, route_id=view["route_id"])
            return clock
        if self.state.get("approved", {}).get(view["route_id"]) != view["view_id"]:
            self.stop("server running proposal lacks durable local approval")
        for action in proposal.get("actions", []):
            if self.live:
                self.perform(view, action, tick)
        self.confirm_settlement(view, tick)
        return clock

    def hour_left(self):
        # Wall-clock rolling hour, durable across process restarts.
        self.state["spend"] = [x for x in self.state.get("spend", []) if time.time() - x[0] < 3600]
        return self.policy.get("max_hour", 0) - sum(x[1] for x in self.state["spend"])

    def snapshot(self, view):
        clock = self.api.call("GET", "/api/clock")
        if clock.get("doors") != "open" or clock.get("paused") or clock["tick"] >= view["expires_tick"]:
            raise ValueError("proposal/clock no longer actionable")
        venues = self.api.call("GET", "/api/venues").get("venues", [])
        venue = next((v for v in venues if (v.get("venue") or v.get("id")) == view["venue"]), None)
        me = self.api.call("GET", "/api/me")
        if (not venue or venue.get("status") != "open" or venue.get("owner") == me["id"]
                or (venue.get("rules") or {}).get("mechanism") not in ("auto", "board")
                or venue.get("fee_bps") != 200 or venue.get("fee_per_card") != 0):
            raise ValueError("AskQuestions: approved venue must actually be open, 2%, no per-card fee, and not our own")
        if me["id"] != view["team"]:
            raise ValueError("wrong local team")
        offers = self.api.call("GET", "/api/me/offers").get("offers", [])
        if any(o.get("maker") is None for o in offers):
            raise ValueError("unknown offer ownership")
        return clock, me, offers, venues

    def perform(self, view, action, tick):
        key = view["route_id"] + ":" + action["kind"]
        old = self.state["writes"].get(key)
        if old:
            if old["status"] == "uncertain":
                self.stop("unresolved previous write; do not repeat")
            if old["status"] == "done":
                self.report(view, old["result"])
                return
            if old.get("retry_tick", tick) > tick:
                return
        clock, me, offers, venues = self.snapshot(view)
        assets = [a for a in me.get("assets", []) if a.get("kind") == "card"]
        if action["kind"] == "post_sale":
            held = next((a for a in assets if a["id"] == view["give"]["asset"]), None)
            if (not held or held["ref"] != view["give"]["card"] or held["ref"] in self.policy.get("protect", [])
                    or sum(a["ref"] == held["ref"] for a in assets) != 2
                    or view["cash_received"] <= m.private_value(held.get("your_value"))
                    or view["cash_received"] - m.private_value(held.get("your_value")) < self.policy.get("min_surplus", 1)):
                self.stop("sale asset, protection, page or private value changed")
            if action != {"kind": "post_sale", "seller": me["id"], "buyer": action.get("buyer"),
                          "asset": held["id"], "card": held["ref"], "cash": view["cash_received"],
                          "buyer_fee": t.fee(view["cash_received"])}:
                self.stop("sale action contradicts approved view")
            for offer in offers:
                locked = [a.get("id") if isinstance(a, dict) else a for a in (offer.get("give") or {}).get("assets", [])]
                if offer.get("maker") == me["id"] and held["id"] in locked:
                    self.stop("selected asset already committed; do not duplicate or migrate")
            limits = clock.get("limits", {})
            if len([o for o in offers if o.get("maker") == me["id"]]) >= limits.get("max_open_offers_per_team", 30):
                return
            method, path = "POST", "/api/offers"
            body = {"venue": view["venue"], "to": action["buyer"], "give": {"assets": [held["id"]]},
                    "want": {"cash": view["cash_received"]}, "expires_in_ticks": min(8, view["expires_tick"] - clock["tick"])}
        elif action["kind"] == "accept_purchase":
            offer = next((o for o in offers if o.get("id") == action.get("offer_id")), None)
            expected_asset = view["receive"]["asset"]
            asset_detail = self.api.call("GET", f"/api/cards/{expected_asset}")
            asset_detail = asset_detail.get("asset", asset_detail.get("card", asset_detail))
            if asset_detail.get("ref") != view["receive"]["card"]:
                self.stop("server card instance contradicts proposed incoming ref")
            give = (offer or {}).get("give") or {}
            offered_assets = [a.get("id") if isinstance(a, dict) else a for a in give.get("assets", [])]
            if (not offer or offer.get("maker") != action.get("seller") or offer.get("to") != me["id"]
                    or offer.get("venue") != view["venue"] or set(give) != {"assets"}
                    or offered_assets != [expected_asset] or offer.get("want") != {"cash": view["cash_paid"]}
                    or offer.get("status") not in (None, "open")
                    or type(offer.get("expires_tick")) is not int or offer["expires_tick"] <= clock["tick"]):
                self.stop("directed offer vanished or differs from approved purchase")
            catalog = self.api.call("GET", "/api/catalog")
            if view["receive"]["card"] not in m.buy_candidates(me, catalog, m.Settings(protect=set(self.policy.get("protect", [])))):
                self.stop("incoming page/protection changed")
            value = m.private_value(self.api.call("GET", "/api/me/value", query={"card": view["receive"]["card"]}).get("your_value"))
            cost = view["cash_paid"] + view["buyer_fee"]
            if (cost >= value or cost > self.policy["max_trade"] or cost > self.hour_left()
                    or value - cost < self.policy.get("min_surplus", 1)):
                self.stop("purchase private value/spending limits changed")
            fee_map = {v.get("venue") or v.get("id"): v for v in venues}
            commitments = 0
            for o in offers:
                cash = (o.get("give") or {}).get("cash", 0)
                if o.get("maker") == me["id"] and cash:
                    v = fee_map.get(o.get("venue"))
                    if not v:
                        self.stop("unknown fees on existing cash commitment")
                    commitments += cash + m.fee_on(cash, v.get("fee_bps"), v.get("fee_per_card"))
            if m.private_value(me.get("cash")) - commitments - cost < self.policy["reserve"]:
                self.stop("purchase would violate reserve; future sale proceeds are not available")
            if self.state.get("accept_tick") == clock["tick"]:
                return
            method, path, body = "POST", f"/api/offers/{offer['id']}/accept", {}
        else:
            self.stop("unfamiliar action")
        final_clock = self.api.call("GET", "/api/clock")
        final_me = self.api.call("GET", "/api/me")
        if (any(final_clock.get(k) != clock.get(k) for k in ("tick", "doors", "paused", "round", "today"))
                or t.digest(final_me) != t.digest(me)):
            self.stop("clock/inventory/cash changed during leg validation; refresh with human review")
        # Durable before sending. A crash/network ambiguity never silently retries.
        self.state["writes"][key] = {"status": "uncertain", "action": action, "view": view}
        self.persist()
        try:
            self.require_clear()
            response = self.api.call(method, path, body)
        except m.ApiError as error:
            if error.status == 429 or error.code in ("rate_limited", "wait_for_tick"):
                retry_tick = error.extra.get("next_tick", clock["tick"] + 1)
                if type(retry_tick) is not int or retry_tick <= clock["tick"]:
                    self.stop("unfamiliar 429 next_tick; no automatic retry")
                self.state["writes"][key] = {"status": "deferred", "retry_tick": retry_tick}
                self.persist()
                return
            self.stop("write failed or outcome uncertain: " + error.code)
        if action["kind"] == "post_sale":
            offer = response.get("offer", response)
            if type(offer.get("id")) is not int or type(offer.get("expires_tick")) is not int or offer["expires_tick"] <= clock["tick"]:
                self.stop("server returned unfamiliar offer/actual expiry; do not repost")
            result = {"offer_id": offer["id"], "expires_tick": offer["expires_tick"]}
        else:
            if not isinstance(response, dict) or response.get("error"):
                self.stop("unfamiliar acceptance result")
            result = {"accepted": True}
            self.state["accept_tick"] = clock["tick"]
            self.state["spend"].append([time.time(), cost])
        self.state["writes"][key] = {"status": "done", "result": result, "action": action, "view": view}
        self.persist()
        self.report(view, result)

    def report(self, view, result):
        self.coordinator.call("POST", f"/v1/cycles/{view['route_id']}/result", {"view_id": view["view_id"], **result})

    def confirm_settlement(self, view, tick):
        key = view["route_id"] + ":accept_purchase"
        write = self.state["writes"].get(key)
        if not write or write["status"] != "done":
            return
        me = self.api.call("GET", "/api/me")
        if not any(a.get("id") == view["receive"]["asset"] and a.get("ref") == view["receive"]["card"] for a in me.get("assets", [])):
            return
        events = self.api.call("GET", "/api/feed", query={"limit": 1000}).get("events", [])
        settlements = [(e.get("payload") or {}) for e in events if e.get("type") == "settlement"
                       and (e.get("payload") or {}).get("venue") == view["venue"]
                       and any(i.get("id") == view["receive"]["asset"] and i.get("to") == me["id"]
                               for i in (e.get("payload") or {}).get("items", []))]
        if not settlements:
            self.stop("inventory acquired expected card without visible venue settlement")
        if any(p.get("price") != view["cash_paid"] or p.get("fee") != view["buyer_fee"] for p in settlements):
            self.stop("actual settlement price/fee contradicts approved private-surplus calculation")
        self.report(view, {"settled": True})

    def cleanup(self, tick, route_id=None):
        # Reconcile only offers created by this agent. Actual server expiry can
        # exceed requested route lifetime; cancel stale own offers, never others.
        for key, write in self.state["writes"].items():
            if write["status"] == "uncertain":
                self.stop("previous write uncertain after restart")
            if write["status"] != "done" or write.get("action", {}).get("kind") != "post_sale":
                continue
            view = write["view"]
            if view["expires_tick"] > tick and route_id != view["route_id"]:
                continue
            if write.get("reconciled"):
                continue
            me = self.api.call("GET", "/api/me")
            offers = self.api.call("GET", "/api/me/offers").get("offers", [])
            offer = next((o for o in offers if o.get("id") == write["result"]["offer_id"]), None)
            if offer:
                if offer.get("maker") != me["id"]:
                    self.stop("cannot classify own stale offer")
                if self.live:
                    self.require_clear()
                    self.api.call("DELETE", f"/api/offers/{offer['id']}")
                else:
                    return
            elif not any(a.get("id") == view["give"]["asset"] for a in me.get("assets", [])):
                events = self.api.call("GET", "/api/feed", query={"limit": 1000}).get("events", [])
                if not any(e.get("type") == "settlement" and any(i.get("id") == view["give"]["asset"]
                        and (i.get("frm") or i.get("from")) == me["id"] for i in (e.get("payload") or {}).get("items", [])) for e in events):
                    self.stop("sold card vanished without visible settlement")
            elif tick < write["result"]["expires_tick"]:
                self.stop("offer vanished early without settlement")
            write["reconciled"] = True
            self.persist()

    def reconcile(self, key, offer_id=None):
        """Human-only, GET evidence, never repeat an uncertain request."""
        write = self.state["writes"].get(key)
        if not write or write["status"] != "uncertain":
            raise ValueError("select the exact uncertain write from the marker/state")
        view, action = write["view"], write["action"]
        me = self.api.call("GET", "/api/me")
        if me["id"] != view["team"]:
            raise ValueError("wrong team")
        offers = self.api.call("GET", "/api/me/offers").get("offers", [])
        if action["kind"] == "post_sale":
            offer = next((o for o in offers if o.get("id") == offer_id), None)
            if (not offer or offer.get("maker") != me["id"] or offer.get("to") != action["buyer"]
                    or offer.get("venue") != view["venue"] or offer.get("give") != {"assets": [view["give"]["asset"]]}
                    or offer.get("want") != {"cash": view["cash_received"]}
                    or type(offer.get("expires_tick")) is not int):
                raise ValueError("actual posted offer cannot be proven from own API; keep the stop")
            result = {"offer_id": offer["id"], "expires_tick": offer["expires_tick"]}
        else:
            events = self.api.call("GET", "/api/feed", query={"limit": 1000}).get("events", [])
            if not any(a.get("id") == view["receive"]["asset"] and a.get("ref") == view["receive"]["card"] for a in me.get("assets", [])):
                raise ValueError("purchase has not visibly settled; keep the stop and wait for evidence")
            if not any(e.get("type") == "settlement" and (e.get("payload") or {}).get("venue") == view["venue"]
                       and (e.get("payload") or {}).get("price") == view["cash_paid"]
                       and (e.get("payload") or {}).get("fee") == view["buyer_fee"]
                       and any(i.get("id") == view["receive"]["asset"] and i.get("to") == me["id"]
                               for i in (e.get("payload") or {}).get("items", [])) for e in events):
                raise ValueError("settlement evidence unavailable; keep the stop")
            result = {"accepted": True}
            self.state["spend"].append([time.time(), view["cash_paid"] + view["buyer_fee"]])
        write.update(status="done", result=result, human_reconciled=True)
        self.persist()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coordinator", required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--state", type=Path, default=Path(__file__).with_name("cycle_state.json"))
    parser.add_argument("--token-file", type=Path, required=True, help="verified Mercado token file, never a Bazaar key")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--enroll", action="store_true", help="explicit consent to verify your team via one Bazaar message; stores token locally")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--approve", help="exact view_id approved by human; fresh safety checks still apply")
    parser.add_argument("--resolve", help="exact durable decision_id, only after explicit human response")
    parser.add_argument("--response", choices=("yes", "no"))
    parser.add_argument("--reconcile-write", help="exact uncertain ledger key, only with explicit human resolution")
    parser.add_argument("--offer-id", type=int, help="actual sale ID to verify with GET during reconciliation")
    args = parser.parse_args(argv)
    policy = policy_checked(json.loads(args.policy.read_text()), args.live)
    marker = args.state.with_name("HUMAN_REQUIRED_cycles.json")
    if args.resolve:
        record = json.loads(marker.read_text())
        if args.response != "yes" or record["decision_id"] != args.resolve:
            parser.error("matching decision ID and explicit human yes required; a no retains the stop")
        state = json.loads(args.state.read_text()) if args.state.exists() else {"writes": {}}
        uncertain = [key for key, value in state["writes"].items() if value["status"] == "uncertain"]
        if uncertain:
            if args.reconcile_write not in uncertain:
                parser.error("uncertain write remains: use --reconcile-write with its exact key; do not erase/retry it")
            key = os.environ.get("BAZAAR_KEY")
            if not key:
                parser.error("local BAZAAR_KEY required for read-only evidence reconciliation")
            agent = Agent(m.Api(os.environ.get("BAZAAR_URL", m.DEFAULT_URL), key), None, policy, args.state)
            agent.reconcile(args.reconcile_write, args.offer_id)
            if any(value["status"] == "uncertain" for value in agent.state["writes"].values()):
                parser.error("other uncertain writes remain; keep the stop")
        # A response records resolution but never erases ambiguous writes. Ops
        # must reconcile their actual outcome first; uncertainty will stop again.
        save_state(marker.with_suffix(".resolved.json"), {**record, "human_response": "yes"})
        marker.unlink()
        return 0
    if args.reconcile_write or args.offer_id is not None:
        parser.error("reconciliation needs --resolve and explicit --response yes")
    key = os.environ.get("BAZAAR_KEY")
    if not key:
        parser.error("BAZAAR_KEY required locally")
    if args.enroll:
        if args.token_file.exists():
            parser.error("token file already exists; do not re-enroll or overwrite it")
        api = m.Api(os.environ.get("BAZAAR_URL", m.DEFAULT_URL), key)
        coordinator = Coordinator(args.coordinator)
        me = api.call("GET", "/api/me")
        joined = coordinator.call("POST", "/v1/waitlist", {"team_id": me["id"]})
        challenge = coordinator.call("POST", "/v1/verify", {"participant_id": joined["participant_id"]})
        threads = api.call("GET", "/api/me/threads", query={"status": "open"}).get("threads", [])
        thread = next((x for x in threads if x.get("with") == "t16"), None)
        if thread is None:
            response = api.call("POST", "/api/threads", {"with": "t16", "venue": "rastro"})
            thread = response.get("thread", response)
        api.call("POST", f"/api/threads/{int(thread['id'])}/messages", {"text": challenge["message"]})
        claimed = coordinator.call("POST", "/v1/verify/claim",
                                   {"participant_id": joined["participant_id"], "verification_nonce": challenge["verification_nonce"]})
        args.token_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(args.token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as token_file:
            token_file.write(claimed["token"] + "\n")
        print("Team verified. Token saved locally, never printed. No offers or trades executed.")
        return 0
    args.state.parent.mkdir(parents=True, exist_ok=True)
    api = m.Api(os.environ.get("BAZAAR_URL", m.DEFAULT_URL), key)
    team = api.call("GET", "/api/me")["id"]
    if not re.fullmatch(r"t\d{2}", team):
        parser.error("unrecognized local team identity")
    leases = Path.home() / ".cache" / "mercado16" / "leases"
    leases.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(leases / (team + ".lock"), "a") as lease:
        try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error("another local cycle agent holds the lease; do not run duplicates")
        agent = Agent(api, Coordinator(args.coordinator, args.token_file.read_text().strip()), policy,
                      args.state, args.live, args.approve)
        while True:
            try:
                clock = agent.cycle()
            except m.ApiError as error:
                if error.status != 429 and error.code not in ("rate_limited", "wait_for_tick"):
                    agent.stop("API evidence unavailable: " + error.code)
                clock = {"next_tick_in": 15}
            except (ValueError, OSError, urllib.error.URLError) as error:
                agent.stop(str(error))
            if not args.watch:
                return 0
            time.sleep(min(60, max(1, float(clock.get("next_tick_in", 15))) + 0.3))


if __name__ == "__main__":
    raise SystemExit(main())
