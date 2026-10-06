"""Persistent coordination, using existing verified-team auth and private SQLite.

This service never holds participant Bazaar keys, values or execution authority.
It dispatches only individually safe bilateral legs after all teams opt in.
"""
import json
from bazaar.marketplace.network.skill.triangles import discover, private_view, validate_intent


class Cycles:
    def __init__(self, store, clock, venue="v16", max_teams=6):
        self.store, self.clock, self.venue, self.max_teams = store, clock, venue, max_teams
        with store._lock:
            store._db.execute("CREATE TABLE IF NOT EXISTS cycle_intents (team TEXT PRIMARY KEY, doc TEXT NOT NULL)")
            store._db.execute("CREATE TABLE IF NOT EXISTS cycles (id TEXT PRIMARY KEY, doc TEXT NOT NULL)")
            store._db.commit()

    def _routes(self):
        return [json.loads(row[0]) for row in self.store._db.execute("SELECT doc FROM cycles ORDER BY rowid")]

    def _save(self, route):
        self.store._db.execute("INSERT OR REPLACE INTO cycles VALUES (?, ?)", (route["route"]["route_id"], json.dumps(route)))

    def _current(self):
        clock = self.clock()
        if type(clock.get("tick")) is not int:
            raise ValueError("AskQuestions: authoritative clock unreadable")
        return clock

    def submit(self, team, intent):
        clock = self._current()
        tick = clock["tick"]
        validate_intent(intent, tick)
        if intent["team"] != team:
            raise ValueError("intent team differs from authenticated participant")
        with self.store._lock, self.store._db:
            routes = self._routes()
            busy = {leg["seller"] for r in routes if r["state"] in ("offered", "running")
                    and r["route"]["expires_tick"] > tick for leg in r["route"]["legs"]}
            if team in busy:
                raise ValueError("team already has a proposal; resolve it before sharing another")
            self.store._db.execute("INSERT OR REPLACE INTO cycle_intents VALUES (?, ?)", (team, json.dumps(intent)))
            rows = []
            for (doc,) in self.store._db.execute("SELECT doc FROM cycle_intents ORDER BY team"):
                row = json.loads(doc)
                if row["team"] in busy:
                    continue
                try:
                    validate_intent(row, tick)
                except ValueError:
                    continue
                rows.append(row)
            if clock.get("doors") == "open" and not clock.get("paused"):
                candidates = discover(rows[:24], tick, self.max_teams, partial=True, venue=self.venue)
                for route in candidates:
                    teams = {leg["seller"] for leg in route["legs"]}
                    if teams & busy:
                        continue
                    alternatives = {}
                    for team_id in teams:
                        variants = set()
                        own = private_view(route, team_id, tick)
                        own_terms = (own["cash_paid"], own["buyer_fee"], len(route["legs"]))
                        for other in candidates:
                            if any(l["seller"] == team_id for l in other["legs"]):
                                view = private_view(other, team_id, tick)
                                terms = (view["cash_paid"], view["buyer_fee"], len(other["legs"]))
                                if terms != own_terms:
                                    variants.add(terms)
                        alternatives[team_id] = [dict(cash_paid=p, buyer_fee=f, participants=n) for p, f, n in sorted(variants)]
                    self._save({"route": route, "state": "offered", "decisions": {}, "results": {}, "alternatives": alternatives})
                    busy |= teams
            self.store._db.commit()
        return {"received": True}

    def mine(self, team):
        clock = self._current()
        tick = clock["tick"]
        views = []
        with self.store._lock:
            for record in self._routes():
                route = record["route"]
                if not any(leg["seller"] == team for leg in route["legs"]):
                    continue
                if route["expires_tick"] <= tick:
                    continue
                view = private_view(route, team, tick)
                view["coordination"] = {"state": record["state"], "participant_count": len(route["legs"]),
                                        "approved_count": sum(record["decisions"].values()),
                                        "competing_terms": record.get("alternatives", {}).get(team, [])}
                if record["state"] == "running" and clock.get("doors") == "open" and not clock.get("paused"):
                    sell = next(l for l in route["legs"] if l["seller"] == team)
                    buy = next(l for l in route["legs"] if l["buyer"] == team)
                    view["actions"] = []
                    if not record["results"].get(team, {}).get("offer_id"):
                        view["actions"].append({"kind": "post_sale", **sell})
                    seller_result = record["results"].get(buy["seller"], {})
                    if seller_result.get("offer_id") and not record["results"].get(team, {}).get("accepted"):
                        view["actions"].append({"kind": "accept_purchase", "offer_id": seller_result["offer_id"], **buy})
                views.append(view)
        return {"proposals": views}

    def update(self, team, route_id, body, result=False):
        clock = self._current()
        tick = clock["tick"]
        with self.store._lock, self.store._db:
            record = next((r for r in self._routes() if r["route"]["route_id"] == route_id), None)
            if record is None or not any(l["seller"] == team for l in record["route"]["legs"]):
                raise ValueError("unknown proposal")  # do not reveal membership or foreign routes
            route = record["route"]
            view = private_view(route, team, tick)
            if body.get("view_id") != view["view_id"]:
                raise ValueError("proposal version changed; fresh consent required")
            if clock.get("doors") != "open" or clock.get("paused"):
                raise ValueError("clock closed/paused")
            if not result:
                if set(body) != {"view_id", "approved", "allow_partial"} or type(body["approved"]) is not bool:
                    raise ValueError("send only view_id, approved and allow_partial")
                if body["approved"] and body["allow_partial"] is not True:
                    raise ValueError("partial-completion risk must be explicitly accepted")
                if record["state"] not in ("offered", "running"):
                    raise ValueError("proposal no longer actionable")
                record["decisions"][team] = body["approved"]
                if not body["approved"]:
                    record["state"] = "declined" if record["state"] == "offered" else "partial_stopped"
                elif len(record["decisions"]) == len(route["legs"]) and all(record["decisions"].values()):
                    record["state"] = "running"
            else:
                if record["state"] != "running" or set(body) - {"view_id", "offer_id", "expires_tick", "accepted", "settled"}:
                    raise ValueError("unexpected execution result")
                saved = record["results"].setdefault(team, {})
                if "offer_id" in body:
                    if (type(body["offer_id"]) is not int or body["offer_id"] <= 0
                            or type(body.get("expires_tick")) is not int or body["expires_tick"] <= tick):
                        raise ValueError("unreadable actual offer ID/expiry")
                    if saved.get("offer_id") not in (None, body["offer_id"]):
                        raise ValueError("duplicate posting refused")
                    if any(v.get("offer_id") == body["offer_id"] for k, v in record["results"].items() if k != team):
                        raise ValueError("offer ID already belongs to another leg")
                    saved.update(offer_id=body["offer_id"], expires_tick=body["expires_tick"])
                for key in ("accepted", "settled"):
                    if key in body:
                        if body[key] is not True:
                            raise ValueError("execution results must be true")
                        saved[key] = True
                if all(record["results"].get(l["seller"], {}).get("settled") for l in route["legs"]):
                    record["state"] = "participant_confirmed_complete"
            self._save(record)
            self.store._db.commit()
            return {"state": record["state"]}
