"""Consent-first Mercado cycle proposals. Standard library; NEVER executes trades.

Negotiation evidence is a lead, not proof of current ownership or willingness.
Only selected, explicitly shared intents enter the analysis. Full routes stay with
the operator; participants receive their own view and validate with local GETs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets

FEE_BPS = 200
BLOCKED = "blocked_atomic_settlement_unavailable"
PARTIAL = "independent_safe_legs_partial_completion_possible"
INTENT_FIELDS = {"team", "asset", "give", "want", "ask", "bid", "observed_tick",
                 "expires_tick", "evidence", "shared_with_consent"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"AskQuestions: invalid {name}")
    return value


def fee(price):
    return (integer(price, "price", 1) * FEE_BPS + 9999) // 10000


def validate_intent(row, tick):
    if not isinstance(row, dict) or set(row) != INTENT_FIELDS:
        raise ValueError("AskQuestions: selected intent schema is ambiguous; no private inventory or keys accepted")
    if row["shared_with_consent"] is not True:
        raise ValueError("explicit sharing consent required")
    if not isinstance(row["team"], str) or not re.fullmatch(r"t[0-9]{1,3}", row["team"]) or row["team"] == "t16":
        raise ValueError("invalid participant; Team 16 cannot trade on its own venue")
    for field in ("give", "want"):
        if not isinstance(row[field], str) or not re.fullmatch(r"[A-Z0-9]+-[0-9]+", row[field]):
            raise ValueError("unsupported card reference")
    if row["give"] == row["want"]:
        raise ValueError("same-card cycle is unsupported")
    for field in ("asset", "ask", "bid", "observed_tick", "expires_tick"):
        integer(row[field], field, 1 if field in ("ask", "bid") else 0)
    if not row["observed_tick"] <= tick < row["expires_tick"] or tick - row["observed_tick"] > 8:
        raise ValueError("stale intent: refresh locally; negotiations are not standing authority")
    evidence = row["evidence"]
    if (not isinstance(evidence, dict) or set(evidence) != {"kind", "id"}
            or evidence["kind"] not in {"failed_negotiation", "stalled_negotiation", "unfilled_offer", "standing_offer"}
            or not isinstance(evidence["id"], str) or not 1 <= len(evidence["id"]) <= 160):
        raise ValueError("structured negotiation evidence required; duel scenarios are not transferable inventory")
    return dict(row)


def discover(intents, tick, max_teams=3, partial=False, venue="v16"):
    """Bounded simple cycles; prefer fewer participants. No inference from free text.

    A bid is the buyer's maximum TOTAL cost including the fee. An ask is the
    seller's minimum net receipt. Inputs are consented claims, not ZK evidence.
    """
    integer(tick, "tick")
    if type(max_teams) is not int or not 3 <= max_teams <= 6:
        raise ValueError("bounded analysis supports three to six participants")
    if not isinstance(intents, list) or len(intents) > 24:
        raise ValueError("bounded analysis supports at most 24 selected intents")
    rows = [validate_intent(row, tick) for row in intents]
    if len({row["team"] for row in rows}) != len(rows):
        raise ValueError("one selected intent per team; competing assets need AskQuestions")
    if len({row["asset"] for row in rows}) != len(rows):
        raise ValueError("conflicting asset ownership claims: AskQuestions")
    result, visits = [], 0
    cycles = []
    # DFS over compatible card edges, not factorial permutations. Canonical
    # smallest-team start suppresses rotations; cap work and route count.
    def extend(path):
        nonlocal visits
        if visits >= 5000 or len(cycles) >= 100:
            return
        visits += 1
        first, last = path[0], path[-1]
        if len(path) >= 3 and last["want"] == first["give"]:
            cycles.append(path)
        if len(path) == max_teams:
            return
        for row in rows:
            if (row["team"] > first["team"] and row not in path
                    and last["want"] == row["give"]):
                extend(path + [row])
    for row in sorted(rows, key=lambda r: r["team"]):
        extend([row])
    for cycle in sorted(cycles, key=lambda c: (len(c), tuple(r["team"] for r in c))):
        legs = []
        for i, buyer in enumerate(cycle):
            seller = cycle[(i + 1) % len(cycle)]
            price = seller["ask"]
            if price + fee(price) > buyer["bid"]:
                break
            legs.append({"seller": seller["team"], "buyer": buyer["team"],
                         "asset": seller["asset"], "card": seller["give"],
                         "cash": price, "buyer_fee": fee(price)})
        else:
            route = {"version": 1, "venue": venue, "fee_bps": FEE_BPS,
                     "fee_basis": "each_cash_leg_buyer_once_rounded_up",
                     "created_tick": tick, "expires_tick": min(row["expires_tick"] for row in cycle),
                     "nonce": secrets.token_hex(16), "legs": legs,
                     "evidence": [row["evidence"] for row in cycle]}
            route["route_id"] = digest(route)
            route["execution_status"] = PARTIAL if partial else BLOCKED
            route["proof"] = "commitment_only_not_zk_or_server_attestation"
            result.append(route)
    return result


def validate_route(route, tick):
    if not isinstance(route, dict):
        raise ValueError("invalid route")
    core = {key: value for key, value in route.items() if key not in {"route_id", "execution_status", "proof"}}
    if digest(core) != route.get("route_id"):
        raise ValueError("route changed: all interest receipts invalidated")
    if (route.get("version") != 1 or not isinstance(route.get("venue"), str) or route.get("fee_bps") != FEE_BPS
            or route.get("fee_basis") != "each_cash_leg_buyer_once_rounded_up"
            or route.get("execution_status") not in (BLOCKED, PARTIAL)):
        raise ValueError("unsupported route policy: AskQuestions")
    if not route["created_tick"] <= tick < route["expires_tick"] or tick - route["created_tick"] > 8:
        raise ValueError("expired route; obtain fresh evidence and consent")
    legs = route.get("legs", [])
    sellers = [leg["seller"] for leg in legs]
    if not 3 <= len(legs) <= 6 or len(set(sellers)) != len(legs) or set(sellers) != {leg["buyer"] for leg in legs}:
        raise ValueError("not a simple multilateral route")
    if len({leg["asset"] for leg in legs}) != len(legs):
        raise ValueError("duplicate asset")
    for leg in legs:
        if leg["seller"] == leg["buyer"] or "t16" in (leg["seller"], leg["buyer"]) or leg["buyer_fee"] != fee(leg["cash"]):
            raise ValueError("invalid leg")
    # Reject disjoint cycles even if all cash and asset counts balance.
    next_team = {leg["seller"]: leg["buyer"] for leg in legs}
    seen, current = set(), sellers[0]
    while current not in seen:
        seen.add(current)
        current = next_team[current]
    if len(seen) != len(legs):
        raise ValueError("disconnected route")


def private_view(route, team, tick):
    validate_route(route, tick)
    outgoing = [leg for leg in route["legs"] if leg["seller"] == team]
    incoming = [leg for leg in route["legs"] if leg["buyer"] == team]
    if len(outgoing) != 1 or len(incoming) != 1:
        raise ValueError("not a route participant")
    sell, buy = outgoing[0], incoming[0]
    view = {"version": 1, "team": team, "route_id": route["route_id"], "venue": route["venue"],
            "fee_bps": FEE_BPS, "fee_basis": route["fee_basis"],
            "created_tick": route["created_tick"], "expires_tick": route["expires_tick"],
            "give": {"asset": sell["asset"], "card": sell["card"]},
            "receive": {"card": buy["card"], "asset": buy["asset"]}, "cash_received": sell["cash"],
            "cash_paid": buy["cash"], "buyer_fee": buy["buyer_fee"],
            "execution_status": route["execution_status"], "proof": route["proof"]}
    view["view_id"] = digest(view)
    return view


def assess(view, team, tick, outgoing_value, incoming_value, cash, reserve,
           held_asset, spare, protected=False, page_break=False, commitments=0):
    """Local-only conservative assessment. Same-set page interactions fail closed.

    No future receipts fund a purchase. Each cash leg must independently respect
    strict private-value bounds, preserving the existing Sunday invariants.
    """
    from math import isfinite
    if digest({k: v for k, v in view.items() if k != "view_id"}) != view.get("view_id"):
        raise ValueError("modified participant view")
    integer(tick, "tick")
    integer(view["cash_received"], "cash received", 1)
    integer(view["cash_paid"], "cash paid", 1)
    reasons = []
    if view["team"] != team or not view["created_tick"] <= tick < view["expires_tick"] or tick - view["created_tick"] > 8:
        reasons.append("wrong participant or stale proposal")
    if (not isinstance(view["venue"], str) or view["fee_bps"] != FEE_BPS
            or view["fee_basis"] != "each_cash_leg_buyer_once_rounded_up"
            or view["buyer_fee"] != fee(view["cash_paid"]) or view["execution_status"] not in (BLOCKED, PARTIAL)):
        reasons.append("unsupported fees, venue or execution policy")
    if any(type(value) not in (int, float) or not isfinite(value) or value < 0
           for value in (outgoing_value, incoming_value, cash, reserve, commitments)):
        raise ValueError("AskQuestions: missing/conflicting values or cash")
    if not held_asset or not spare or protected or page_break:
        reasons.append("asset missing, protected, not spare or page-breaking")
    if view["give"]["card"].split("-")[0] == view["receive"]["card"].split("-")[0]:
        reasons.append("same-set sequential page value uncertain")
    cost = view["cash_paid"] + view["buyer_fee"]
    if view["cash_received"] <= outgoing_value or cost >= incoming_value:
        reasons.append("strict private-value bound violated")
    if cash - commitments - cost < reserve:
        reasons.append("current cash insufficient after commitments and reserve")
    surplus = view["cash_received"] - outgoing_value + incoming_value - cost
    return {"route_id": view["route_id"], "view_id": view["view_id"], "assessed_tick": tick,
            "eligible_for_interest": not reasons, "estimated_private_surplus": surplus,
            "cash_after_purchase_before_sale": cash - commitments - cost,
            "outgoing_private_value": outgoing_value, "incoming_private_value": incoming_value,
            "page_impact": "no completed page broken" if not page_break and spare else "uncertain",
            "reasons": reasons, "execution_status": view["execution_status"],
            "human_question": "AskQuestions: confirm interest in this exact proposal; this is not authorization to trade"}


def interest_receipt(view, assessment, human_yes, tick):
    if (human_yes is not True or assessment.get("eligible_for_interest") is not True
            or not view["created_tick"] <= tick < view["expires_tick"]
            or assessment.get("assessed_tick") != tick
            or assessment.get("route_id") != view["route_id"] or assessment.get("view_id") != view["view_id"]):
        raise ValueError("fresh safe assessment and explicit human yes required")
    return {"team": view["team"], "route_id": view["route_id"], "view_id": view["view_id"],
            "expires_tick": view["expires_tick"], "decision": "interested_only",
            "authentication": "unsigned_requires_verified_team_channel",
            "execution_authorized": False}


def execute(*args, **kwargs):
    raise RuntimeError("AskQuestions: Bazaar atomic multilateral settlement is unverified. No trades executed; no override available.")


def review_local(api, view, reserve=100, protect=()):
    """GET-only review on the participant's machine. Private numbers never uploaded."""
    try:
        from .mercado16 import private_value, fee_on, checked_fees, buy_candidates, Settings
    except ImportError:  # standalone downloaded script, beside mercado16.py
        from mercado16 import private_value, fee_on, checked_fees, buy_candidates, Settings
    clock = api.call("GET", "/api/clock")
    if clock.get("doors") != "open" or clock.get("paused"):
        raise ValueError("AskQuestions: clock closed/paused; defer local validation")
    me = api.call("GET", "/api/me")
    assets = [a for a in me.get("assets", []) if a.get("kind") == "card"]
    held = next((a for a in assets if a.get("id") == view["give"]["asset"]), None)
    if held is None or held.get("ref") != view["give"]["card"]:
        raise ValueError("AskQuestions: selected asset missing or changed")
    catalog = api.call("GET", "/api/catalog")
    if view["receive"]["card"] not in buy_candidates(me, catalog, Settings(protect=set(protect))):
        raise ValueError("AskQuestions: incoming card is not an unprotected missing page card")
    offers = api.call("GET", "/api/me/offers").get("offers", [])
    venues = api.call("GET", "/api/venues").get("venues", [])
    venue_map = {v.get("venue") or v.get("id"): v for v in venues}
    active = [o for o in offers if o.get("status") in (None, "open", "queued")]
    if any(o.get("maker") is None for o in active):
        raise ValueError("AskQuestions: unknown offer owner")
    commitments = 0
    for offer in active:
        if offer["maker"] != me["id"]:
            continue
        give = offer.get("give") or {}
        locked = [a.get("id") if isinstance(a, dict) else a for a in give.get("assets", [])]
        if held["id"] in locked:
            raise ValueError("AskQuestions: selected asset already committed on another offer")
        if give.get("cash"):
            venue = venue_map.get(offer.get("venue"))
            if venue is None:
                raise ValueError("AskQuestions: another cash commitment has unknown fees")
            amount = integer(give["cash"], "cash commitment")
            bps, per = checked_fees(venue.get("fee_bps"), venue.get("fee_per_card"))
            commitments += amount + fee_on(amount, bps, per)
    incoming = private_value(api.call("GET", "/api/me/value", query={"card": view["receive"]["card"]}).get("your_value"))
    outgoing = private_value(held.get("your_value"))
    # A second read detects changes during this multi-request review. It is not a
    # lock or a transaction; every eventual execution must revalidate atomically.
    final_clock = api.call("GET", "/api/clock")
    final_me = api.call("GET", "/api/me")
    clock_fields = ("tick", "doors", "paused", "round", "today")
    if any(final_clock.get(k) != clock.get(k) for k in clock_fields) or digest(final_me) != digest(me):
        raise ValueError("AskQuestions: live state changed during validation; refresh before consent")
    result = assess(view, me["id"], clock["tick"], outgoing, incoming,
                    me.get("cash"), reserve, True,
                    sum(a.get("ref") == held["ref"] for a in assets) == 2,
                    held["ref"] in protect, commitments=commitments)
    venue = venue_map.get(view["venue"])
    result["venue_ready"] = bool(venue and venue.get("status") == "open"
                                  and (venue.get("rules") or {}).get("mechanism") == "auto"
                                  and venue.get("fee_bps") == FEE_BPS and venue.get("fee_per_card") == 0
                                  and venue.get("owner") != me["id"])
    result["warning"] = ("Partial completion accepted only through the coordinated agent: each leg must independently pass fresh safety checks."
                         if view["execution_status"] == PARTIAL else
                         "Interest only. Venue 2% configuration and atomic server support remain prerequisites; nothing executes.")
    return result, clock["tick"]


def prepare_intent(api, asset, want, evidence, sharing_yes, reserve=100, protect=()):
    """Generate selected price limits locally, without any market listing or upload."""
    if sharing_yes is not True:
        raise ValueError("AskQuestions: explicit consent to share this selected intent required")
    try:
        from .mercado16 import private_value, bid_price
    except ImportError:
        from mercado16 import private_value, bid_price
    from math import floor
    clock = api.call("GET", "/api/clock")
    me = api.call("GET", "/api/me")
    held = next((a for a in me.get("assets", []) if a.get("id") == asset and a.get("kind") == "card"), None)
    if held is None:
        raise ValueError("AskQuestions: selected real asset missing")
    incoming = private_value(api.call("GET", "/api/me/value", query={"card": want}).get("your_value"))
    ask = floor(private_value(held.get("your_value"))) + 1
    base_bid = bid_price(incoming, 0, FEE_BPS, 0)
    if base_bid < 1:
        raise ValueError("no safe incoming cash price")
    row = {"team": me["id"], "asset": asset, "give": held["ref"], "want": want,
           "ask": ask, "bid": base_bid + fee(base_bid), "observed_tick": clock["tick"],
           "expires_tick": clock["tick"] + 8, "evidence": evidence, "shared_with_consent": True}
    validate_intent(row, clock["tick"])
    # Review the exact bounds with the same local safety path used by proposals.
    view = {"version": 1, "team": row["team"], "route_id": "intent_preview",
            "venue": "v16", "fee_bps": FEE_BPS, "fee_basis": "each_cash_leg_buyer_once_rounded_up",
            "created_tick": clock["tick"], "expires_tick": row["expires_tick"],
            "give": {"asset": asset, "card": held["ref"]}, "receive": {"card": want},
            "cash_received": ask, "cash_paid": base_bid, "buyer_fee": fee(base_bid),
            "execution_status": BLOCKED, "proof": "commitment_only_not_zk_or_server_attestation"}
    view["view_id"] = digest(view)
    report, tick = review_local(api, view, reserve, protect)
    if tick != clock["tick"] or not report["eligible_for_interest"]:
        raise ValueError("AskQuestions: selected intent cannot be proven safe: " + "; ".join(report["reasons"]))
    return row


def write_private(path, value):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Never replace another proposal, and never expose a file before chmod.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("intents", type=Path, nargs="?", help="consented selected intents JSON; never a full inventory")
    parser.add_argument("--tick", type=int, help="current observed Bazaar tick")
    parser.add_argument("--out", type=Path, required=True, help="private runtime output directory")
    parser.add_argument("--max-teams", type=int, choices=(3, 4), default=3)
    parser.add_argument("--review", type=Path, help="review only your private proposal with live GETs")
    parser.add_argument("--prepare-intent", type=Path, help="structured negotiation evidence JSON, selected locally")
    parser.add_argument("--give-asset", type=int)
    parser.add_argument("--want-card")
    parser.add_argument("--share-approved", action="store_true", help="only after human approval to share selected card/price limits")
    parser.add_argument("--reserve", type=int, default=100)
    parser.add_argument("--protect", action="append", default=[])
    parser.add_argument("--human-yes", action="store_true", help="only after the human agrees to interest, never trade authorization")
    args = parser.parse_args(argv)
    if args.review or args.prepare_intent:
        if args.review and args.prepare_intent:
            parser.error("select one local operation")
        if args.intents is not None or args.tick is not None:
            parser.error("--review reads the current clock itself; do not supply intents or --tick")
        try:
            from .mercado16 import Api, DEFAULT_URL
        except ImportError:
            from mercado16 import Api, DEFAULT_URL
        key = os.environ.get("BAZAAR_KEY")
        if not key:
            parser.error("BAZAAR_KEY required locally; never include it in proposal files")
        api = Api(os.environ.get("BAZAAR_URL", DEFAULT_URL), key)
        if args.prepare_intent:
            if args.give_asset is None or not args.want_card or args.human_yes:
                parser.error("--prepare-intent requires --give-asset and --want-card, not --human-yes")
            row = prepare_intent(api, args.give_asset, args.want_card,
                                 json.loads(args.prepare_intent.read_text()), args.share_approved,
                                 integer(args.reserve, "reserve"), args.protect)
            write_private(args.out / "selected_intent.json", row)
            print("Selected intent prepared locally; nothing uploaded or posted. Share only through the approved private channel.")
            return 0
        view = json.loads(args.review.read_text())
        report, tick = review_local(api, view,
                                    integer(args.reserve, "reserve"), args.protect)
        write_private(args.out / "local_assessment.json", report)
        print(json.dumps(report, indent=2))  # participant-local only; do not send this to the coordinator
        if args.human_yes:
            write_private(args.out / "interest_receipt.json", interest_receipt(view, report, True, tick))
        return 0
    if args.intents is None or args.tick is None or args.human_yes:
        parser.error("analysis requires intents and --tick; --human-yes is only for local review")
    routes = discover(json.loads(args.intents.read_text()), args.tick, args.max_teams)
    for route in routes:
        directory = args.out / route["route_id"]
        write_private(directory / "operator_route.json", route)
        for leg in route["legs"]:
            write_private(directory / f"{leg['seller']}.json", private_view(route, leg["seller"], args.tick))
    print(f"{len(routes)} proposals prepared; fee 2% per cash leg to buyer; {BLOCKED}")
    print("Deliver only each recipient's own file over a verified private channel. No execution, invitations or API writes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
