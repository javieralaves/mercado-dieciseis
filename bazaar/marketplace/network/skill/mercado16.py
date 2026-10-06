"""Mercado Dieciséis local skill: post single-card offers on Mercado Dieciséis from your own machine.

    export BAZAAR_URL=https://bazaar.causaprima.ai
    export BAZAAR_KEY=tk-xxxx-xxxx           # your own team key; it never leaves this machine
    python3 mercado16.py                      # dry run: prints the offers it would post, and why
    python3 mercado16.py --post               # posts them on the venue
    python3 mercado16.py --cancel             # withdraws all your offers on the venue

Standard library only. It talks to the Bazaar API and nothing else. Your values, cards, cash and
key stay here; the only thing others see is the offers you post (the card and your price).

How it prices: the venue runs on `mechanism: auto`. Every tick the Bazaar engine crosses, card by
card, the lowest ask with the highest bid at the midpoint. So you can quote close to your own limit
and still keep half of the gap:

  sell  a spare copy at or above its `your_value` plus your margin, after the venue fee;
  buy   a card you are missing at or below `GET /api/me/value` minus your margin, after the fee.

Both bounds assume you pay the whole fee, so no cross can leave you worse off at your own values.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass, field, replace
from pathlib import Path
import uuid

VERSION = "1"
DEFAULT_VENUE = "v16"
DEFAULT_URL = "https://bazaar.causaprima.ai"
ON_OFFER = "skipped, a copy is already on offer (any venue)"
BIDDING = "skipped, you already bid on it here"
HUMAN_SPARES = "AskQuestions: multiple saleable copies; sequential marginal loss needs human review, no ask posted"
NO_CASH = "skipped, no cash left after your {reserve} P reserve"


class ApiError(Exception):
    def __init__(self, code: str, message: str = "", status: int = 0, extra: dict | None = None):
        super().__init__(f"{code}: {message}" if message else code)
        self.code, self.message, self.status, self.extra = code, message, status, extra or {}


class Api:
    """The few Bazaar routes the skill needs, paced under 5 requests per second."""

    def __init__(self, url: str, key: str, timeout: float = 15.0):
        self.url, self.key, self.timeout = url.rstrip("/"), key, timeout
        self._last = 0.0
        self.defer_writes = False

    def call(self, method: str, path: str, body: dict | None = None, query: dict | None = None):
        url = self.url + path + ("?" + urllib.parse.urlencode(query) if query else "")
        data = None if body is None else json.dumps(body).encode()
        headers = {"X-Team-Key": self.key, "Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        for attempt in range(4):
            time.sleep(max(0.0, 0.25 - (time.monotonic() - self._last)))
            self._last = time.monotonic()
            try:
                req = urllib.request.Request(url, data=data, method=method, headers=headers)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read()
                return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as e:
                try:
                    payload = json.loads(e.read() or b"{}")
                except ValueError:
                    payload = {}
                payload = payload if isinstance(payload, dict) else {}
                err = ApiError(str(payload.get("error") or f"http_{e.code}"), str(payload.get("message") or ""),
                               e.code, payload)
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                if method != "GET":
                    raise ApiError("network", f"{method} {path}: {e}") from None
                err = ApiError("network", str(e))
                time.sleep(0.5 * (attempt + 1))
                continue
            if method != "GET" and self.defer_writes and (err.status == 429 or err.code in ("rate_limited", "wait_for_tick")):
                raise err  # watch must refresh values before retrying on another tick
            if err.code == "rate_limited":
                time.sleep(0.5 * (attempt + 1))
                continue
            if err.code == "wait_for_tick" or (err.status == 429 and "next_tick" in err.extra):
                self.wait_tick()
                continue
            raise err
        raise err

    def wait_tick(self) -> None:
        try:
            wait = float(self.call("GET", "/api/clock").get("next_tick_in", 1.0))
        except ApiError:
            wait = 1.0
        time.sleep(min(65.0, max(0.05, wait)) + 0.3)


@dataclass
class Settings:
    venue: str = DEFAULT_VENUE
    margin: float = 0.0
    reserve: int = 100
    max_price: int | None = None
    max_asks: int = 10
    max_bids: int = 6
    keep: int = 1
    protect: set = field(default_factory=set)
    sell: set = field(default_factory=set)
    buy: set = field(default_factory=set)
    only_buy: bool = False
    only_sell: bool = False
    expires: int = 120
    discover: bool = False


@dataclass
class Offer:
    side: str
    card: str
    name: str
    price: int
    limit: float
    why: str
    asset: int | None = None

    def payload(self, venue: str, expires: int) -> dict:
        if self.side == "sell":
            give, want = {"assets": [self.asset]}, {"cash": self.price}
        else:
            give, want = {"cash": self.price}, {"cards": [self.card]}
        return {"venue": venue, "give": give, "want": want, "expires_in_ticks": int(expires)}


def private_value(value, context="card") -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
        raise ApiError("human_required", f"AskQuestions: {context} has missing, negative or nonfinite private value; nothing posted")
    return float(value)


def checked_fees(fee_bps, fee_per_card):
    if (not isinstance(fee_bps, int) or isinstance(fee_bps, bool) or not 0 <= fee_bps < 10000
            or not isinstance(fee_per_card, int) or isinstance(fee_per_card, bool) or fee_per_card < 0):
        raise ApiError("human_required", "AskQuestions: unfamiliar venue fees; cannot prove private-value safety")
    return fee_bps, fee_per_card


def fee_on(price: int, fee_bps: int, fee_per_card: int) -> int:
    checked_fees(fee_bps, fee_per_card)
    return math.ceil(price * fee_bps / 10000) + fee_per_card


def ask_price(value: float, margin: float, fee_bps: int, fee_per_card: int) -> int:
    """Lowest whole price whose proceeds after the whole fee keep `margin` above your value."""
    value = private_value(value)
    floor = max(value * (1 + margin), value + 1)
    price = max(1, math.ceil(value) + 1, math.ceil(floor))
    while price - fee_on(price, fee_bps, fee_per_card) < floor:
        price += 1
    return price


def bid_price(value: float, margin: float, fee_bps: int, fee_per_card: int) -> int:
    """Highest whole price whose cost with the whole fee stays `margin` below your value; 0 when none."""
    value = private_value(value)
    ceiling = min(value * (1 - margin), value - 1)
    price = math.floor(ceiling)
    while price >= 1 and price + fee_on(price, fee_bps, fee_per_card) > ceiling:
        price -= 1
    return max(price, 0)


def _card_index(catalog: dict) -> dict:
    return {c["id"]: c for s in catalog.get("sets", []) for c in s.get("cards", [])}


def _open_mine(offers: list, me_id: str) -> list:
    return [o for o in offers if o.get("maker") == me_id and o.get("status") in (None, "open", "queued")]


def _offered_assets(mine: list) -> set:
    return {a["id"] if isinstance(a, dict) else a for o in mine for a in (o.get("give") or {}).get("assets") or []}


def _bid_cards(mine: list, venue: str) -> set:
    out = set()
    for o in mine:
        if o.get("venue") != venue or (o.get("give") or {}).get("assets"):
            continue
        want = o.get("want") or {}
        for t in list(want.get("types") or []) + [f"card:{c}" for c in want.get("cards") or []]:
            if str(t).startswith("card:"):
                out.add(str(t)[5:])
    return out


def read_discovery(api, venues, clock, state):
    """GET-only local evidence. No private data is uploaded or forwarded to participants."""
    tick = clock["tick"]
    cache = state.setdefault("discovery_boards", {})
    notes, recent, duels = [], [], []
    active = {v.get("venue") or v.get("id"): v for v in venues if v.get("status") == "open"}
    # Bound reads on the participant key. Rastro/Mercado each cycle; rotate other markets.
    fixed = [v for v in ("rastro", DEFAULT_VENUE) if v in active]
    rest = sorted(set(active) - set(fixed))
    cursor = state.get("discovery_cursor", 0)
    selected = fixed + ([rest[(cursor + i) % len(rest)] for i in range(min(2, len(rest)))] if rest else [])
    state["discovery_cursor"] = cursor + 2
    for venue in selected:
        try:
            rows = api.call("GET", f"/api/venues/{venue}/offers").get("offers")
            if not isinstance(rows, list):
                raise ApiError("evidence_unreadable", "board offers are not a list")
            cache[venue] = (tick, rows)
        except ApiError as e:
            cache.pop(venue, None)
            if e.status == 429 or e.code in ("rate_limited", "wait_for_tick"):
                raise
            notes.append(f"{venue} board unavailable ({e.code}); no demand inferred")
    try:
        events = api.call("GET", "/api/feed", query={"limit": 250}).get("events", [])
        for e in events:
            if e.get("scope") != "public" or not isinstance(e.get("tick"), int) or not 0 <= tick - e["tick"] <= 8:
                continue
            if e.get("type") in ("settlement", "duel.closed", "duels.scheduled", "duels.finished"):
                payload = e.get("payload") or {}
                recent.append({"type": e["type"], "tick": e["tick"],
                               "venue": payload.get("venue"), "price": payload.get("price"),
                               "item": payload.get("item"), "status": payload.get("status")})
    except ApiError as e:
        if e.status == 429 or e.code in ("rate_limited", "wait_for_tick"):
            raise
        notes.append(f"public feed unavailable ({e.code})")
    try:
        for d in api.call("GET", "/api/duels").get("duels", []):
            if d.get("status") == "live":
                rival = d.get("rival_offer") or {}
                duels.append({"duel": d.get("duel"), "item": d.get("item"), "role": d.get("role"),
                              "rival_price": rival.get("price"), "rival_days": rival.get("days"),
                              "deadline_tick": d.get("deadline_tick")})
    except ApiError as e:
        if e.status == 429 or e.code in ("rate_limited", "wait_for_tick"):
            raise
        notes.append(f"own duel read unavailable ({e.code}); other teams' private duels are inaccessible")
    rows, venue_fees = [], {}
    for venue, info in active.items():
        try:
            venue_fees[venue] = checked_fees(info.get("fee_bps"), info.get("fee_per_card"))
        except ApiError:
            notes.append(f"{venue}: unknown fees; excluded from triangulation")
    for venue, (at, offers) in list(cache.items()):
        if venue not in active or not 0 <= tick - at <= 8:
            cache.pop(venue, None)
            continue
        if venue not in venue_fees:
            continue
        fees = venue_fees[venue]
        for o in offers:
            if isinstance(o, dict):
                rows.append({"offer": o, "venue": venue, "tick": at, "fees": fees, "owner": active[venue].get("owner")})
    return {"rows": rows, "venue_fees": venue_fees, "recent": recent[-8:], "duels": duels, "notes": notes,
            "coverage": f"{len(selected)} boards read this cycle; other boards rotate; evidence expires after 8 ticks"}


def discovery_signals(evidence, me, tick, mine=()):
    """Only unambiguous, untargeted or locally targeted single-card cash quotes."""
    signals, swaps = [], []
    owned_ids = {o.get("id") for o in _open_mine(mine, me["id"])}
    for row in (evidence or {}).get("rows", []):
        o = row["offer"]
        expiry = o.get("expires_tick")
        if (o.get("id") in owned_ids or row.get("owner") == me["id"] or o.get("maker") == me["id"] or not o.get("maker") or o.get("status") != "open"
                or o.get("to") not in (None, me["id"]) or not isinstance(expiry, int)
                or expiry <= tick or not 0 <= tick - row["tick"] <= 8):
            continue
        give, want = o.get("give") or {}, o.get("want") or {}
        if not isinstance(give, dict) or not isinstance(want, dict):
            continue
        if any(not isinstance(part.get(k) or [], list) for part in (give, want) for k in ("assets", "cards", "types")):
            continue
        assets = give.get("assets") or []
        refs = list(want.get("cards") or []) + [t[5:] for t in want.get("types") or [] if isinstance(t, str) and t.startswith("card:")]
        outgoing = assets[0].get("ref") if len(assets) == 1 and isinstance(assets[0], dict) and assets[0].get("kind") == "card" else None
        base = {"venue": row["venue"], "offer": o.get("id"), "maker": o["maker"],
                "observed_tick": row["tick"], "expires_tick": expiry, "fees": row["fees"]}
        if (outgoing and len(refs) == 1 and not give.get("cash") and not want.get("cash")
                and not give.get("types") and not give.get("cards") and not want.get("assets")
                and all(isinstance(t, str) and t.startswith("card:") for t in want.get("types") or [])):
            swaps.append(dict(base, give=outgoing, want=refs[0]))
            continue
        try:
            side, target, price = quote_shape(o)
        except (ApiError, TypeError, ValueError, AttributeError):
            continue  # bundles/unknown asset refs never become execution evidence
        ref = outgoing if side == "sell" else target
        if isinstance(ref, str) and price > 0:
            signals.append(dict(base, side=side, ref=ref, price=price))
    return signals, swaps


def interest(offer, signals, fees):
    matches = [q for q in signals if q["ref"] == offer.card and q["side"] != offer.side
               and ((offer.side == "sell" and q["price"] >= offer.price)
                    or (offer.side == "buy" and q["price"] <= offer.price))]
    def gain(q):
        midpoint = (offer.price + q["price"]) / 2
        fee = fee_on(math.ceil(midpoint), *fees)
        return midpoint - fee - offer.limit if offer.side == "sell" else offer.limit - midpoint - fee
    return max(((max(0, gain(q)), q) for q in matches), key=lambda v: v[0], default=(0, None))


def discovery_cash(me, mine, fees, evidence, venue):
    """Adjust the existing planner for fees on cash already committed on other venues."""
    fee_map = {r["venue"]: r["fees"] for r in evidence["rows"]}
    fee_map.update(evidence.get("venue_fees", {}))
    fee_map[venue] = fees
    extra = 0
    for o in _open_mine(mine, me["id"]):
        cash = private_value((o.get("give") or {}).get("cash") or 0, "cash commitment")
        if cash:
            if o.get("venue") not in fee_map:
                raise ApiError("human_required", "AskQuestions: fees on another cash commitment are unknown; no discovery posts")
            extra += max(0, fee_on(math.ceil(cash), *fee_map[o["venue"]]) - fee_on(math.ceil(cash), *fees))
    return dict(me, cash=max(0, me["cash"] - extra))


def show_discovery(evidence, me, catalog, values, mine, fees, s, tick, post=False):
    """Local awareness only; linked legs are never executed or advertised by this function."""
    signals, swaps = discovery_signals(evidence, me, tick, mine)
    # Show all eligible quotes before listing-count truncation; cash reserve still applies.
    all_s = replace(s, max_asks=len(me.get("assets", [])), max_bids=len(values))
    quote_me = discovery_cash(me, mine, fees, evidence, s.venue)
    offers, _ = plan(quote_me, catalog, values, mine, *fees, all_s, signals)
    deals = sorted([(gain, o, q) for o in offers for gain, q in [interest(o, signals, fees)] if q],
                   key=lambda d: -d[0])
    print("\nLOCAL DEAL DISCOVERY · no counterparty commitments; no private information uploaded")
    print(evidence["coverage"])
    for gain, o, q in deals[:8]:
        print(f"  {o.side.upper()} {o.card} on {s.venue} at {o.price} P; current private value {o.limit:g}; "
              f"conditional midpoint surplus +{gain:.2f} P if outside quote migrates unchanged")
        print(f"    evidence {q['venue']} offer {q['offer']} ({q['maker']}), {q['side']} {q['price']:g} P, "
              f"age {tick-q['observed_tick']} ticks, expires {q['expires_tick']}; local agents automatically quote on {s.venue} when independently safe")
    if post and not s.only_sell and s.max_bids > 0:
        commitments = sum(((o.get("give") or {}).get("cash") or 0) +
                          (fee_on(math.ceil((o.get("give") or {}).get("cash")), *fees) if (o.get("give") or {}).get("cash") else 0)
                          for o in _open_mine(mine, me["id"]))
        budget = quote_me["cash"] - s.reserve - commitments
        bidding = _bid_cards(mine, s.venue)
        rivals = []
        for ref, value in values.items():
            if ref in s.protect or ref in bidding:
                continue
            price = bid_price(value, s.margin, *fees)
            if s.max_price is not None:
                price = min(price, s.max_price)
            if price < 1:
                continue
            o = Offer("buy", ref, ref, price, value, "")
            gain, evidence_row = interest(o, signals, fees)
            cost = price + fee_on(price, *fees)
            if gain >= 20 and evidence_row and cost <= budget:
                rivals.append((gain, cost, o))
        rivals.sort(key=lambda x: -x[0])
        if len(rivals) > 1 and (sum(x[1] for x in rivals[:2]) > budget or s.max_bids < 2):
            facts = "; ".join(f"{o.card}: quote {o.price} P, private value {o.limit:g}, conditional surplus +{g:.2f} P" for g, c, o in rivals[:2])
            raise ApiError("human_required", f"AskQuestions: competing valuable bids. {facts}. Cash {me['cash']} P, reserve {s.reserve} P, standing commitments (plus extra external fees) {commitments + me['cash'] - quote_me['cash']} P, budget {budget} P. Page targets compete; acquisition cost not applicable. Worst downside: crowding out the alternative or committing cash before its seller migrates. Recommendation: post neither until human chooses one/both with revised limits/neither.")
    if not deals:
        print("  No corroborated local cash deal in the readable evidence.")
    # Cash-mediated local paths use only already-safe quotes and current cash, never hoped-for proceeds.
    executable, _ = plan(quote_me, catalog, values, mine, *fees, s, signals)
    selling = [(o, interest(o, signals, fees)) for o in executable if o.side == "sell"]
    buying = [(o, interest(o, signals, fees)) for o in executable if o.side == "buy"]
    for sell, (sale_gain, buyer) in selling[:3]:
        for buy, (buy_gain, seller) in buying[:3]:
            if not buyer or not seller or sell.card == buy.card:
                continue
            print(f"  AUTOMATIC SAFE LEGS: sell {sell.card} at minimum {sell.price} P; buy {buy.card} at maximum {buy.price} P on {s.venue}. "
                  f"Current private values: {sell.limit:g} / {buy.limit:g}; reserve {s.reserve} P. "
                  "Purchase is funded by current cash, not future sale proceeds. Each leg remains safe if the other never fills. "
                  "Existing watch execution posts these cash quotes automatically after --auto approval; no linked swap is submitted.")
    # Cross-venue resale is non-atomic and outgoing marginal value after acquisition is unknown.
    paths = []
    eligible = set(buy_candidates(me, catalog, s)) if not s.only_sell else set()
    for ask in signals:
        if ask["side"] != "sell" or ask["ref"] not in eligible:
            continue
        for bid in signals:
            if bid["side"] != "buy" or bid["ref"] != ask["ref"] or bid["maker"] == ask["maker"]:
                continue
            cost = ask["price"] + fee_on(math.ceil(ask["price"]), *ask["fees"])
            proceeds = bid["price"] - fee_on(math.ceil(bid["price"]), *bid["fees"])
            if proceeds > cost:
                paths.append((proceeds-cost, cost, ask, bid))
    for spread, cost, ask, bid in sorted(paths, key=lambda p: -p[0])[:3]:
        print(f"  AskQuestions: RESALE {ask['ref']} {ask['venue']}#{ask['offer']} → {bid['venue']}#{bid['offer']}; "
              f"conditional spread +{spread:g} P; cash at risk {cost:g} P; current incoming private value {values.get(ask['ref'], 'unknown')}; "
              "outgoing value/page effect after purchase unverified. Recommendation: do not execute linked legs; resale may disappear.")
    # Small 2/3-leg barter paths starting from a locally spare card; no matching service.
    counts = Counter(a.get("ref") for a in me.get("assets", []) if a.get("kind") == "card")
    starts = {r for r, n in counts.items() if n > s.keep and r not in s.protect} if not s.only_buy else set()
    cycles, seen, visits = [], set(), [0]
    def extend(start, current, path):
        if len(path) == 3:
            return
        for q in swaps[:100]:
            visits[0] += 1
            if visits[0] > 2000 or len(cycles) >= 3:
                return
            if q["want"] != current or q["offer"] in {p["offer"] for p in path}:
                continue
            chain = path + [q]
            if q["give"] == start and len(chain) > 1:
                key = tuple(p["offer"] for p in chain)
                if key not in seen and len({p["maker"] for p in chain}) == len(chain):
                    seen.add(key); cycles.append(chain)
            elif q["give"] not in s.protect:
                extend(start, q["give"], chain)
    for start in sorted(starts):
        extend(start, start, [])
    for chain in cycles[:3]:
        print("  AskQuestions: BARTER CYCLE " + " → ".join(f"{q['want']}→{q['give']} ({q['venue']}#{q['offer']})" for q in chain)
              + "; conditional cash upside unproven; fees/intermediate values/page effects unknown. Worst downside: first card leaves and later legs vanish. Recommendation: do nothing without human review.")
    for d in evidence["duels"]:
        print(f"  OWN DUEL {d['duel']}: {d['item']}, {d['role']}, rival price {d['rival_price']}, days {d['rival_days']}, deadline {d['deadline_tick']}; context only, not transferable-card demand")
    for e in evidence["recent"]:
        print(f"  public {e['type']} tick {e['tick']}: venue {e['venue']}, price {e['price']}, item {e['item']}; history, not a standing offer")
    for note in evidence["notes"]:
        print("  NOTE: " + note)
    print("  No messages/invitations sent. Linked paths are advisory; refresh values after every fill.")
    return signals


def plan(me: dict, catalog: dict, values: dict, my_offers: list, fee_bps: int, fee_per_card: int,
         s: Settings, signals=None) -> tuple[list[Offer], list[str]]:
    """The offers to post, and (reason, card) for everything skipped. Pure: no network."""
    notes: list[tuple[str, str]] = []
    cards = _card_index(catalog)
    mine = _open_mine(my_offers, me["id"])
    busy = _offered_assets(mine)
    held = [a for a in me.get("assets", []) if a.get("kind") == "card"]
    counts = Counter(a["ref"] for a in held)
    out: list[Offer] = []

    if not s.only_buy:
        for ref in sorted(counts):
            if ref in s.protect:
                continue
            copies = sorted((a for a in held if a["ref"] == ref), key=lambda a: a["id"])
            on_offer = [a for a in copies if a["id"] in busy]
            if on_offer:
                notes.append((ON_OFFER, ref))
            room = len(copies) if ref in s.sell else max(len(copies) - s.keep, 0)
            if room > 1:
                notes.append((HUMAN_SPARES, ref))
                continue
            free = [a for a in copies if a["id"] not in busy]
            for a in free[len(free) - max(room - len(on_offer), 0):] if room > len(on_offer) else []:
                value = private_value(a.get("your_value"), f"held {ref} asset {a['id']}")
                price = ask_price(value, s.margin, fee_bps, fee_per_card)
                why = "you asked to sell it" if ref in s.sell else "spare copy"
                out.append(Offer("sell", ref, a.get("name") or ref, price, value,
                                 f"{why}; worth {value:g} to you, you net at least "
                                 f"{price - fee_on(price, fee_bps, fee_per_card)} after the fee", a["id"]))
        out = sorted(out, key=lambda o: (-interest(o, signals or [], (fee_bps, fee_per_card))[0], -o.price))[: s.max_asks]

    if not s.only_sell:
        budget = private_value(me.get("cash"), "cash") - s.reserve - sum(
            private_value((o.get("give") or {}).get("cash") or 0, "standing cash commitment") +
            (fee_on(int((o.get("give") or {}).get("cash") or 0), fee_bps, fee_per_card)
             if (o.get("give") or {}).get("cash") else 0) for o in mine)
        bidding = _bid_cards(mine, s.venue)
        wanted = []
        for ref, value in values.items():
            if ref in s.protect:
                continue
            value = private_value(value, ref)
            if ref in bidding:
                notes.append((BIDDING, ref))
                continue
            price = bid_price(float(value), s.margin, fee_bps, fee_per_card)
            if price < 1:
                continue
            if s.max_price is not None and price > s.max_price:
                price = s.max_price
            wanted.append((float(value) - price, ref, price, float(value)))
        bids = 0
        def priority(w):
            gain, ref, price, value = w
            quote = Offer("buy", ref, ref, price, value, "")
            return interest(quote, signals or [], (fee_bps, fee_per_card))[0], gain, ref
        for gain, ref, price, value in sorted(wanted, key=priority, reverse=True):
            if bids >= s.max_bids:
                break
            cost = price + fee_on(price, fee_bps, fee_per_card)
            if cost > budget:
                notes.append((NO_CASH, ref))
                continue
            budget -= cost
            bids += 1
            card = cards.get(ref, {})
            out.append(Offer("buy", ref, card.get("name") or ref, price, value,
                             f"missing; one more is worth {value:g} to you, you pay at most "
                             f"{price + fee_on(price, fee_bps, fee_per_card)} with the fee"))
    return out, notes


def buy_candidates(me: dict, catalog: dict, s: Settings) -> list[str]:
    counts = Counter(a["ref"] for a in me.get("assets", []) if a.get("kind") == "card")
    refs = [c["id"] for c in _card_index(catalog).values()
            if c.get("page") and counts[c["id"]] == 0 and c["id"] not in s.protect]
    return sorted((set(refs) | set(s.buy)) - s.protect)


def venue_info(api: Api, venue: str) -> dict | None:
    data = api.call("GET", "/api/venues")
    rows = data.get("venues", data) if isinstance(data, dict) else data
    return next((v for v in rows or [] if v.get("venue") == venue or v.get("id") == venue), None)


def free_slots(api: Api, me_id: str) -> tuple[int, int]:
    limits = api.call("GET", "/api/clock").get("limits") or {}
    open_now = len(_open_mine(api.call("GET", "/api/me/offers").get("offers", []), me_id))
    return int(limits.get("offers_per_team_per_tick", 12)), int(limits.get("max_open_offers_per_team", 30)) - open_now


def show(offers: list[Offer], notes: list[str], venue: dict, s: Settings) -> None:
    fee = f"{venue.get('fee_bps', 0) / 100:g}%" + (f" + {venue['fee_per_card']} P/card" if venue.get("fee_per_card") else "")
    print(f"Mercado Dieciséis · venue {s.venue} ({venue.get('name')}) · {venue.get('rules', {}).get('mechanism')} · fee {fee}")
    cap = "private-value bound / cash reserve" if s.max_price is None else f"{s.max_price} P"
    print(f"margin {s.margin:.0%} · cash reserve {s.reserve} P · max price {cap}\n")
    if not offers:
        print("Nothing to post right now.")
    for o in offers:
        print(f"  {o.side.upper():4} {o.card:7} {o.price:>4} P  {o.name[:28]:28}  {o.why}")
    for reason in (ON_OFFER, BIDDING, NO_CASH, HUMAN_SPARES):
        refs = sorted({ref for r, ref in notes if r == reason})
        if refs:
            print(f"\n  {reason.format(reserve=s.reserve)}: {', '.join(refs)}")


def run(api: Api, s: Settings, post: bool) -> int:
    venue = venue_info(api, s.venue)
    if venue is None:
        print(f"Venue {s.venue} not found. Check https://bazaar.causaprima.ai or pass --venue.")
        return 2
    me = api.call("GET", "/api/me")
    if venue.get("owner") == me["id"]:
        print(f"{s.venue} is your own venue; Bazaar does not let a team trade on its own venue.")
        return 2
    if venue.get("status") != "open":
        print(f"{s.venue} is {venue.get('status')}; nothing posted.")
        return 2
    if (venue.get("rules") or {}).get("mechanism") != "auto":
        print(f"AskQuestions: {s.venue} is not an auto venue; unfamiliar venue state, nothing posted.")
        return 2
    fee_bps, fee_card = checked_fees(venue.get("fee_bps", 0), venue.get("fee_per_card", 0))
    evidence = None
    if s.discover:
        clock = api.call("GET", "/api/clock")
        evidence = read_discovery(api, api.call("GET", "/api/venues").get("venues", []), clock, {})
        me = api.call("GET", "/api/me")  # refresh local position after public reads
    catalog = api.call("GET", "/api/catalog")
    values = {}
    if not s.only_sell:
        for ref in buy_candidates(me, catalog, s):
            values[ref] = private_value(api.call("GET", "/api/me/value", query={"card": ref}).get("your_value"), ref)
    mine = api.call("GET", "/api/me/offers").get("offers", [])
    signals = None
    if evidence is not None:
        signals = show_discovery(evidence, me, catalog, values, mine, (fee_bps, fee_card), s, api.call("GET", "/api/clock")["tick"], post)
    quote_me = discovery_cash(me, mine, (fee_bps, fee_card), evidence, s.venue) if evidence is not None else me
    offers, notes = plan(quote_me, catalog, values, mine, fee_bps, fee_card, s, signals)
    show(offers, notes, venue, s)
    if not post:
        print("\nDry run: nothing was sent. Run again with --post to post these offers.")
        return 0
    posted = 0
    per_tick, room = free_slots(api, me["id"])
    queue = list(offers)
    while queue and room > 0:
        batch, queue = queue[: min(per_tick, room)], queue[min(per_tick, room):]
        for o in batch:
            try:
                res = api.call("POST", "/api/offers", o.payload(s.venue, s.expires))
                posted += 1
                room -= 1
                print(f"posted {o.side} {o.card} at {o.price} P (offer {res.get('id') or (res.get('offer') or {}).get('id')})")
            except ApiError as e:
                print(f"refused {o.side} {o.card} at {o.price} P: {e.code} {e.message}")
        if queue and room > 0:
            api.wait_tick()
    if queue:
        print(f"{len(queue)} not posted: you are at Bazaar's limit of open offers.")
    print(f"\nPosted {posted}. The engine crosses them every tick; cancel any time with --cancel.")
    return 0


WATCH_MARKER = Path(__file__).with_name("HUMAN_REQUIRED_mercado16.json")


def quote_shape(o):
    """Only classify the simple quotes this local skill can prove safe."""
    give, want = o.get("give") or {}, o.get("want") or {}
    assets = give.get("assets") or []
    refs = list(want.get("cards") or []) + [t[5:] for t in want.get("types") or [] if isinstance(t, str) and t.startswith("card:")]
    if (len(assets) == 1 and not give.get("cash") and not give.get("types") and not give.get("cards")
            and not want.get("assets") and not want.get("types") and not want.get("cards")):
        asset = assets[0].get("id") if isinstance(assets[0], dict) else assets[0]
        return "sell", asset, private_value(want.get("cash"), "ask price")
    if (not assets and not give.get("types") and not give.get("cards") and len(refs) == 1
            and not want.get("assets") and not want.get("cash")
            and all(isinstance(t, str) and t.startswith("card:") for t in want.get("types") or [])):
        return "buy", refs[0], private_value(give.get("cash"), "bid price")
    raise ApiError("human_required", f"AskQuestions: ambiguous offer {o.get('id')}; no reconciliation writes")


def watch_cycle(api, s, post, state):
    clock = api.call("GET", "/api/clock")
    tick = clock.get("tick")
    if not isinstance(tick, int):
        raise ApiError("human_required", "AskQuestions: unreadable clock tick")
    if clock.get("paused") or clock.get("doors") == "closed":
        return clock
    if clock.get("doors") != "open":
        raise ApiError("human_required", "AskQuestions: unfamiliar door state; no writes")
    if state.get("wait_until", tick) > tick:
        return clock
    venues = api.call("GET", "/api/venues").get("venues", [])
    venue = next((v for v in venues if v.get("venue") == s.venue or v.get("id") == s.venue), None)
    if not venue or venue.get("status") != "open":
        print("Venue closed or missing; no writes.")
        return clock
    if (venue.get("rules") or {}).get("mechanism") != "auto":
        raise ApiError("human_required", "AskQuestions: venue is no longer auto")
    fees = checked_fees(venue.get("fee_bps", 0), venue.get("fee_per_card", 0))
    if state.get("fees", fees) != fees:
        raise ApiError("human_required", f"AskQuestions: venue fees changed from {state['fees']} to {fees}")
    evidence = read_discovery(api, venues, clock, state) if s.discover else None
    if s.discover:
        clock = api.call("GET", "/api/clock")
        tick = clock["tick"]
        if clock.get("paused") or clock.get("doors") != "open":
            return clock
    me = api.call("GET", "/api/me")
    if venue.get("owner") == me["id"]:
        raise ApiError("human_required", "AskQuestions: cannot trade on your own venue")
    all_offers = api.call("GET", "/api/me/offers").get("offers", [])
    if any(o.get("maker") is None and o.get("status") in (None, "open", "queued") for o in all_offers):
        raise ApiError("human_required", "AskQuestions: offer ownership is unreadable")
    mine = _open_mine(all_offers, me["id"])
    fee_map = {v.get("venue") or v.get("id"): checked_fees(v.get("fee_bps", 0), v.get("fee_per_card", 0)) for v in venues}
    if any((o.get("give") or {}).get("cash") and o.get("venue") not in fee_map for o in mine):
        raise ApiError("human_required", "AskQuestions: fees on another cash commitment are unknown")
    own = {o["id"]: o for o in mine if o.get("venue") == s.venue}
    if set(state.get("cancelled", ())) & set(own):
        print("Waiting for server to confirm our cancellation; no new writes.")
        return clock
    for o in own.values():
        if not isinstance(o.get("expires_tick"), int) or o["expires_tick"] <= tick:
            raise ApiError("human_required", f"AskQuestions: open offer {o['id']} has missing/contradictory actual expiry")
    held = {a["id"]: a for a in me.get("assets", []) if a.get("kind") == "card"}
    previous = state.get("owned", {})
    gone = [o for oid, o in previous.items() if oid not in own]
    old_ids = set(state.get("held", held))
    changed = old_ids ^ set(held)
    if gone or changed:
        events = api.call("GET", "/api/feed", query={"limit": 1000}).get("events", [])
        settlements = [e.get("payload") or {} for e in events
                       if e.get("type") == "settlement" and e.get("tick", -1) > state.get("tick", -1)]
        explained = {i.get("id") for p in settlements for i in p.get("items", [])
                     if (i.get("frm") or i.get("from")) == me["id"] or i.get("to") == me["id"]}
        if changed - explained:
            raise ApiError("human_required", f"AskQuestions: inventory changed without visible settlement: {sorted(changed - explained)}")
        for o in gone:
            if o.get("id") in state.get("cancelled", ()) or o["expires_tick"] <= tick:
                continue
            side, target, price = quote_shape(o)
            visible = any(p.get("venue") == s.venue and any(
                (side == "sell" and i.get("id") == target and (i.get("frm") or i.get("from")) == me["id"]
                 and target not in held)
                or (side == "buy" and i.get("ref") == target and i.get("to") == me["id"] and i.get("id") in changed)
                for i in p.get("items", [])) for p in settlements)
            if not visible:
                raise ApiError("human_required", f"AskQuestions: offer {o['id']} vanished before actual expiry without visible settlement")
    catalog = api.call("GET", "/api/catalog")
    candidates = buy_candidates(me, catalog, s)
    shapes = {oid: quote_shape(o) for oid, o in own.items()}
    refs = set(candidates) | {target for side, target, _ in shapes.values() if side == "buy"}
    values = {ref: private_value(api.call("GET", "/api/me/value", query={"card": ref}).get("your_value"), ref)
              for ref in refs} if not s.only_sell else {}
    signals = None
    counts = Counter(a["ref"] for a in held.values())
    cancels = set()
    for oid, (side, target, price) in shapes.items():
        if side == "sell":
            a = held.get(target)
            if a is None:
                cancels.add(oid)
                continue
            ref = a["ref"]
            room = counts[ref] if ref in s.sell else max(0, counts[ref] - s.keep)
            if room > 1:
                raise ApiError("human_required", f"AskQuestions: {ref} has multiple saleable copies; sequential value needs review")
            value = private_value(a.get("your_value"), ref)
            if s.only_buy or ref in s.protect or room < 1 or price - fee_on(price, *fees) <= value:
                cancels.add(oid)
        elif (s.only_sell or target not in candidates or target in s.protect
              or price + fee_on(price, *fees) >= values[target]
              or (s.max_price is not None and price > s.max_price)):
            cancels.add(oid)
    # Do not guess which of several valid cash commitments the human prefers to cancel.
    bids = [oid for oid, shape in shapes.items() if shape[0] == "buy" and oid not in cancels]
    commitments = sum(private_value((o.get("give") or {}).get("cash") or 0, "cash commitment")
                      + (fee_on((o.get("give") or {}).get("cash"), *fee_map[o.get("venue")]) if (o.get("give") or {}).get("cash") else 0)
                      for o in mine if o.get("id") not in cancels)
    if commitments + s.reserve > private_value(me.get("cash"), "cash"):
        if len(bids) > 1:
            raise ApiError("human_required", f"AskQuestions: competing bids {bids} breach reserve; cash {me['cash']}, reserve {s.reserve}, commitments {commitments}")
        cancels.update(bids)
    if len({target for oid, (side, target, _) in shapes.items() if oid not in cancels}) < len(own) - len(cancels):
        raise ApiError("human_required", "AskQuestions: duplicate quotes need review")
    for oid in sorted(cancels):
        print(f"cancel unsafe own offer {oid}" + ("" if post else " [DRY RUN]"))
        if post:
            api.call("DELETE", f"/api/offers/{oid}")
            state.setdefault("cancelled", set()).add(oid)
    if post and cancels:
        # Cancellation may be queued: confirm it is gone before freeing its cash/asset locally.
        fresh = api.call("GET", "/api/me/offers").get("offers", [])
        if any(o.get("id") in cancels and o.get("status") in (None, "open", "queued") for o in fresh):
            return clock
        mine = _open_mine(fresh, me["id"])
        own = {o["id"]: o for o in mine if o.get("venue") == s.venue}
    elif not post:
        mine = [o for o in mine if o.get("id") not in cancels]
        own = {oid: o for oid, o in own.items() if oid not in cancels}
    remaining = replace(s, max_asks=max(0, s.max_asks - sum(quote_shape(o)[0] == "sell" for o in own.values())),
                        max_bids=max(0, s.max_bids - sum(quote_shape(o)[0] == "buy" for o in own.values())))
    adjusted_me = dict(me, cash=me["cash"] - sum(max(0, fee_on((o.get("give") or {}).get("cash"), *fee_map[o.get("venue")]) - fee_on((o.get("give") or {}).get("cash"), *fees)) for o in mine if (o.get("give") or {}).get("cash")))
    if evidence is not None:
        state.update(cash=me.get("cash"), values=values)
        signals = show_discovery(evidence, me, catalog, values, mine, fees, remaining, tick, post)
    offers, notes = plan(adjusted_me, catalog, {r: values[r] for r in candidates} if not s.only_sell else {}, mine, *fees, remaining, signals)
    show(offers, notes, venue, s)
    if state.get("posts_tick") != tick:
        state["posted_ids"] = set()
        state["posts_tick"] = tick
    limits = clock.get("limits") or {}
    if not all(isinstance(limits.get(k), int) and limits[k] >= 0 for k in ("offers_per_team_per_tick", "max_open_offers_per_team")):
        raise ApiError("human_required", "AskQuestions: missing or unfamiliar server offer limits")
    used = state["posted_ids"] | {o["id"] for o in mine if o.get("created_tick") == tick}
    room = min(max(0, limits["offers_per_team_per_tick"] - len(used)), max(0, limits["max_open_offers_per_team"] - len(mine)))
    if post:
        for o in offers[:room]:
            res = api.call("POST", "/api/offers", o.payload(s.venue, s.expires))
            row = res.get("offer") if isinstance(res.get("offer"), dict) else res
            if not isinstance(row.get("id"), int) or not isinstance(row.get("expires_tick"), int) or row["expires_tick"] <= tick or row.get("maker", me["id"]) != me["id"] or row.get("venue", s.venue) != s.venue:
                raise ApiError("human_required", "AskQuestions: post may have landed, but actual id/expiry is unreadable; do not repeat")
            merged = {**o.payload(s.venue, s.expires), **row, "maker": me["id"]}
            if quote_shape(merged) != (o.side, o.asset if o.side == "sell" else o.card, o.price):
                raise ApiError("human_required", "AskQuestions: posted terms differ from the safe quote; do not repeat")
            own[row["id"]] = merged
            state["posted_ids"].add(row["id"])
            print(f"posted {o.side} {o.card}, offer {row['id']}, actual expires_tick {row['expires_tick']}")
    state.update(owned=own, held=list(held), cash=me.get("cash"), values=values, fees=fees, tick=tick)
    return clock


def watch(api, s, post, every=0, marker=None):
    marker = Path(marker) if marker is not None else WATCH_MARKER
    if post and marker.exists():
        print(f"AskQuestions: unresolved stop at {marker}; no writes. Resolve only after an explicit human answer.")
        return 2
    api.defer_writes = True
    state = {}
    while True:
        try:
            clock = watch_cycle(api, s, post, state)
        except ApiError as e:
            if e.status == 429 or e.code in ("rate_limited", "wait_for_tick"):
                clock = api.call("GET", "/api/clock")
                state["wait_until"] = e.extra.get("next_tick", clock["tick"] + 1)
                print("429: defer writes and replan after the permitted tick.")
            else:
                facts = {"id": uuid.uuid4().hex, "decision": "Resume Mercado maintenance?", "recommended_action": "Do nothing; use AskQuestions",
                         "expected_upside": "Safe executable liquidity after uncertainty is resolved",
                         "worst_credible_downside": "Duplicate spending or an unsafe sale if history/value is misread",
                         "private_values": state.get("values"), "cash": state.get("cash"), "assets": state.get("held"),
                         "page_impact": "Unknown until reviewed", "evidence": e.message, "why_human": e.code}
                if post:
                    try:
                        with marker.open("x") as f:
                            json.dump(facts, f, indent=2)
                    except FileExistsError:
                        pass
                print(f"AskQuestions: {e.message}; stopped" + (f", facts at {marker}" if post else " [DRY RUN]"))
                return 2
        delay = 15 if clock.get("paused") or clock.get("doors") != "open" else (every or clock.get("next_tick_in") or clock.get("tick_seconds") or 15)
        time.sleep(max(1, min(60, float(delay))) + 0.3)


def cancel_all(api: Api, venue: str) -> int:
    me = api.call("GET", "/api/me")
    mine = [o for o in _open_mine(api.call("GET", "/api/me/offers").get("offers", []), me["id"]) if o.get("venue") == venue]
    for o in mine:
        try:
            api.call("DELETE", f"/api/offers/{int(o['id'])}")
            print(f"cancelled offer {o['id']}")
        except ApiError as e:
            print(f"could not cancel {o['id']}: {e.code}")
    print(f"Cancelled {len(mine)} offer(s) on {venue}.")
    return 0


def _refs(text: str) -> set:
    return {r.strip().upper() for r in (text or "").split(",") if r.strip()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Post single-card offers on Mercado Dieciséis from your own machine.")
    ap.add_argument("--auto", action="store_true", help="explicit live approval: discover and maintain independently safe Mercado quotes automatically")
    ap.add_argument("--post", action="store_true", help="post the offers for real (default: dry run)")
    ap.add_argument("--discover", action="store_true", help="local awareness from public markets/feed and own duels; linked trades remain advisory")
    ap.add_argument("--watch", action="store_true", help="maintain quotes each tick; read-only unless --post")
    ap.add_argument("--resolve-human-required", metavar="DECISION_ID", help="operator only, after explicit AskQuestions response")
    ap.add_argument("--human-answer", choices=("yes", "no"))
    ap.add_argument("--human-note", default="")
    ap.add_argument("--cancel", action="store_true", help="withdraw all your open offers on the venue")
    ap.add_argument("--venue", default=DEFAULT_VENUE, help=f"venue id (default {DEFAULT_VENUE})")
    ap.add_argument("--margin", type=float, default=0.0, help="extra margin beyond strict private-value safety (default 0)")
    ap.add_argument("--reserve", type=int, default=100, help="cash your bids never touch (default 100)")
    ap.add_argument("--max-price", type=int, default=None, help="optional hard bid cap in P (default: private-value bound and reserve)")
    ap.add_argument("--max-asks", type=int, default=10)
    ap.add_argument("--max-bids", type=int, default=6)
    ap.add_argument("--keep", type=int, default=1, help="copies of each card you never sell (default 1)")
    ap.add_argument("--protect", default="", help="cards never to sell or buy, e.g. LAT-02,SAL-11")
    ap.add_argument("--sell", default="", help="also sell these cards even if it is your last copy")
    ap.add_argument("--buy", default="", help="also consider bidding on these cards")
    ap.add_argument("--only-buy", action="store_true")
    ap.add_argument("--only-sell", action="store_true")
    ap.add_argument("--expires", type=int, default=120, help="ticks before an offer expires (default 120)")
    ap.add_argument("--every", type=int, default=0, help="with --post, run again every N seconds")
    args = ap.parse_args(argv)
    if args.auto:
        if args.cancel or args.resolve_human_required:
            ap.error("--auto cannot be combined with cancellation or human-stop resolution")
        args.post = args.watch = args.discover = True

    if args.resolve_human_required:
        if args.post or args.watch or args.cancel or not args.human_answer or not args.human_note.strip():
            ap.error("resolution requires a separate command with --human-answer and --human-note")
        record = json.loads(WATCH_MARKER.read_text())
        if record.get("id") != args.resolve_human_required:
            ap.error("decision ID changed; read the marker and ask the human again")
        with WATCH_MARKER.with_name("HUMAN_REQUIRED_mercado16_resolutions.jsonl").open("a") as f:
            f.write(json.dumps({"id": record["id"], "answer": args.human_answer, "note": args.human_note}) + "\n")
        if args.human_answer == "yes":
            WATCH_MARKER.unlink()
        print("Human response recorded; " + ("stop cleared" if args.human_answer == "yes" else "stop retained"))
        return 0
    if args.watch and args.cancel:
        ap.error("--watch cannot be combined with --cancel; watch is read-only without --post")
    if (args.post or args.cancel) and WATCH_MARKER.exists():
        print(f"AskQuestions: unresolved stop at {WATCH_MARKER}; no writes")
        return 2
    key = os.environ.get("BAZAAR_KEY", "").strip()
    if not key:
        print("Set BAZAAR_KEY to your team key (it stays on this machine).")
        return 2
    if not 0 <= args.margin < 1:
        ap.error("--margin must be between 0 and 1")
    for name in ("reserve", "max_asks", "max_bids", "every"):
        if getattr(args, name) < 0:
            ap.error(f"--{name.replace('_', '-')} must be nonnegative")
    if args.max_price is not None and args.max_price < 1:
        ap.error("--max-price must be positive")
    api = Api(os.environ.get("BAZAAR_URL", DEFAULT_URL), key)
    if args.cancel:
        return cancel_all(api, args.venue)
    s = Settings(venue=args.venue, margin=args.margin, reserve=args.reserve, max_price=args.max_price,
                 max_asks=args.max_asks, max_bids=args.max_bids, keep=max(args.keep, 1),
                 protect=_refs(args.protect), sell=_refs(args.sell), buy=_refs(args.buy),
                 only_buy=args.only_buy, only_sell=args.only_sell, expires=args.expires, discover=args.discover)
    try:
        if args.watch or (args.post and args.every > 0):
            return watch(api, s, args.post, args.every)
        return run(api, s, args.post)
    except ApiError as e:
        if args.post and e.code == "human_required":
            try:
                with WATCH_MARKER.open("x") as f:
                    json.dump({"id": uuid.uuid4().hex, "decision": "Resume Mercado posting?", "evidence": e.message,
                               "recommendation": "Use AskQuestions; do nothing pending explicit human response"}, f, indent=2)
            except FileExistsError:
                pass
        if e.code in ("bad_key", "http_401"):
            print("Bazaar refused the key (401). Check BAZAAR_KEY.")
        else:
            print(f"Bazaar refused: {e.code} {e.message}")
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
