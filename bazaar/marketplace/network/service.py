"""Public waitlist page, the local-mode contract, and the endpoints a team needs to join."""
import html
import json
import re
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from bazaar.marketplace.network.auth import begin, claim, identify
from bazaar.marketplace.network.readiness import public_view
from bazaar.marketplace.network.store import OUR_TEAM, SIGNAL_FIELDS, THRESHOLD, Store
from bazaar.marketplace.network.terms import VENUE, pricing_line
from bazaar.store.paths import ROOT

TEAM_ID = re.compile(r"t\d{2}")
MAX_BODY = 4096
SECRET_FIELDS = {
    "bazaar_key", "api_key", "key", "token", "github", "password", "secret",
    "broker_key", "starter_broker_key", "email",
}

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mercado Dieciséis</title>
<style>
  body {{ margin: 0; font: 18px/1.45 ui-sans-serif, system-ui, sans-serif; background: #f6f3ec; color: #1c1915; }}
  main {{ max-width: 36rem; margin: 4rem auto; padding: 0 1.25rem; }}
  h1 {{ font-size: 1.75rem; line-height: 1.2; margin: 0 0 0.75rem; }}
  p {{ margin: 0 0 0.75rem; }}
  .count {{ font-variant-numeric: tabular-nums; font-size: 1.35rem; margin: 1.5rem 0 0.25rem; }}
  form {{ display: flex; gap: 0.5rem; margin-top: 1.5rem; }}
  input {{ flex: 1; font: inherit; padding: 0.55rem 0.7rem; border: 1px solid #c8c0b4; border-radius: 6px; background: #fff; }}
  button {{ font: inherit; padding: 0.55rem 0.9rem; border: 0; border-radius: 6px; background: #1c1915; color: #f6f3ec; cursor: pointer; }}
  #result {{ min-height: 1.5rem; margin-top: 1rem; }}
</style>
</head>
<body>
<main>
  <h1>A Bazaar market that never sees your values</h1>
  <p>Your agent runs where it already runs, in your own Cursor or Claude.<br>It posts offers on Mercado Dieciséis and the Bazaar engine matches them.<br>Your values, cards, cash and key never reach us.</p>
  <p>{pricing} <a href="/contract">How it works</a></p>
  <p class="count">{ready} / {threshold} teams ready</p>
  <p>Mercado Dieciséis is live on venue {venue}. Any team can post there now; this waitlist is optional.</p>
  <p>Joining this waitlist does not count as ready. We never ask for your Bazaar key.</p>
  <form id="join">
    <input name="team_id" autocomplete="off" placeholder="t07" aria-label="Bazaar team id" required>
    <button type="submit">Connect my team</button>
  </form>
  <p id="result"></p>
</main>
<script>
  const result = document.getElementById("result");
  document.getElementById("join").addEventListener("submit", async (event) => {{
    event.preventDefault();
    result.textContent = "";
    const team_id = new FormData(event.target).get("team_id").trim();
    const response = await fetch("/v1/waitlist", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{ team_id }}),
    }});
    const body = await response.json();
    if (!response.ok) {{
      result.textContent = body.error || "Could not join.";
      return;
    }}
    result.textContent = "You are on the waitlist. Your id is " + body.participant_id + ". This does not make your team ready.";
  }});
</script>
</body>
</html>
"""


CONTRACT = ROOT / "docs" / "mercado-dieciseis-contract.md"

CONTRACT_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mercado Dieciséis · how it works</title>
<style>
  body {{ margin: 0; background: #f6f3ec; color: #1c1915; }}
  main {{ max-width: 46rem; margin: 3rem auto; padding: 0 1.25rem; }}
  pre {{ white-space: pre-wrap; font: 15px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace; }}
</style>
</head>
<body>
<main>
<p><a href="/">Back to Mercado Dieciséis</a></p>
<pre>{text}</pre>
</main>
</body>
</html>
"""


def page(status: dict, now: datetime | None = None) -> str:
    when = now or datetime.now(timezone.utc)
    return PAGE.format(
        ready=status["ready"], threshold=status["threshold"], pricing=html.escape(pricing_line(when)), venue=VENUE,
    )


def contract_page() -> str:
    return CONTRACT_PAGE.format(text=html.escape(CONTRACT.read_text(encoding="utf-8")))


class Waitlist:
    def __init__(self, store: Store, cycles=None):
        self.store = store
        self.cycles = cycles

    def handle(self, method: str, path: str, body: dict | None = None, headers=None) -> tuple[int, dict | str]:
        if path.startswith("/v1/cycles/"):
            who = self._me(headers)
            if who[0] != 200:
                return who
            if who[1]["status"] == "not_interested":
                return 403, {"error": "participant opted out"}
            if self.cycles is None:
                return 503, {"error": "coordination not enabled"}
            try:
                team = who[1]["team_id"]
                if method == "GET" and path == "/v1/cycles/me":
                    return 200, self.cycles.mine(team)
                if method == "POST" and path == "/v1/cycles/intents":
                    return 200, self.cycles.submit(team, body)
                match = re.fullmatch(r"/v1/cycles/([a-f0-9]{64})/(decision|result)", path)
                if method == "POST" and match:
                    return 200, self.cycles.update(team, match[1], body or {}, result=match[2] == "result")
            except (ValueError, TypeError, KeyError):
                return 409, {"error": "AskQuestions: stale, conflicting or unsupported coordination state; no action authorized"}
            return 404, {"error": "not found"}
        if method == "GET" and path == "/":
            return 200, page(self.store.public_status())
        if method == "GET" and path == "/contract":
            return 200, contract_page()
        if method == "GET" and path == "/v1/status":
            return 200, self.store.public_status()
        if method == "GET" and path == "/v1/me":
            return self._me(headers)
        if method == "POST" and path == "/v1/waitlist":
            return self._join(body or {})
        if method == "POST" and path == "/v1/verify":
            return self._verify(body or {})
        if method == "POST" and path == "/v1/verify/claim":
            return self._claim(body or {})
        if method == "POST" and path == "/v1/me/signals":
            return self._signals(body or {}, headers)
        return 404, {"error": "not found"}

    def _join(self, body: dict) -> tuple[int, dict]:
        if not isinstance(body, dict):
            return 400, {"error": "send a JSON object with team_id"}
        extra = SECRET_FIELDS.intersection(body)
        if extra or set(body) - {"team_id"}:
            return 400, {"error": "send only team_id"}
        team_id = body.get("team_id")
        if not isinstance(team_id, str):
            return 400, {"error": "team_id must look like t07"}
        team_id = team_id.strip().lower()
        if not TEAM_ID.fullmatch(team_id):
            return 400, {"error": "team_id must look like t07"}
        if team_id == OUR_TEAM:
            return 400, {"error": "Team 16 does not join its own network"}
        row = self.store.join(team_id)
        status = self.store.public_status()
        return 200, {
            "participant_id": row["id"],
            "status": row["status"],
            "threshold": THRESHOLD,
            "ready_teams": status["ready"],
        }

    def _only(self, body: dict, allowed: set[str]) -> dict | None:
        if not isinstance(body, dict):
            return {"error": "send a JSON object"}
        if SECRET_FIELDS.intersection(body) or set(body) - allowed:
            return {"error": "send only " + ", ".join(sorted(allowed))}
        return None

    def _verify(self, body: dict) -> tuple[int, dict]:
        refused = self._only(body, {"participant_id"})
        if refused:
            return 400, refused
        challenge = begin(self.store, str(body.get("participant_id") or ""))
        if challenge is None:
            return 404, {"error": "unknown participant"}
        if not challenge["issued"]:
            return 409, {"error": "already verified"}
        return 200, {
            "participant_id": challenge["participant_id"],
            "status": challenge["status"],
            "verification_nonce": challenge["verification_nonce"],
            "message": challenge["message"],
            "send_to": challenge["send_to"],
        }

    def _claim(self, body: dict) -> tuple[int, dict]:
        refused = self._only(body, {"participant_id", "verification_nonce"})
        if refused:
            return 400, refused
        if self.cycles is not None:
            from bazaar.marketplace.network.auth import observe, messages_from_client
            from common import client
            try:
                observe(self.store, messages_from_client(client()))
            except Exception:
                return 503, {"error": "verification evidence unavailable; retry later, no token issued"}
        result = claim(self.store, str(body.get("participant_id") or ""), str(body.get("verification_nonce") or ""))
        code = result["status"]
        if code != 200:
            return code, {"error": result["error"]}
        return 200, {
            "participant_id": result["participant_id"],
            "status": result["team_status"],
            "token": result["token"],
        }

    def _me(self, headers) -> tuple[int, dict]:
        header = ""
        if headers is not None:
            header = headers.get("Authorization") or ""
        token = header[7:].strip() if header.startswith("Bearer ") else ""
        who = identify(self.store, token)
        if who is None:
            return 401, {"error": "unknown token"}
        return 200, who

    def _signals(self, body: dict, headers) -> tuple[int, dict]:
        who = self._me(headers)
        if who[0] != 200:
            return who
        refused = self._only(body, set(SIGNAL_FIELDS))
        if refused or not body:
            return 400, refused or {"error": "send at least one signal"}
        if any(not isinstance(body[name], bool) for name in body):
            return 400, {"error": "signals must be true or false"}
        row = self.store.set_signals(who[1]["participant_id"], body)
        return 200, public_view(row)


def make_handler(waitlist: Waitlist):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: dict | str) -> None:
            if isinstance(body, str):
                raw, ctype = body.encode(), "text/html; charset=utf-8"
            else:
                raw, ctype = json.dumps(body).encode(), "application/json; charset=utf-8"
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:
            code, body = waitlist.handle("GET", self.path.split("?", 1)[0], headers=self.headers)
            self._send(code, body)

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", 0) or 0)
            if length > MAX_BODY:
                return self._send(413, {"error": "send only team_id"})
            raw = self.rfile.read(length) if length else b"{}"
            try:
                parsed = json.loads(raw or b"{}")
            except ValueError:
                return self._send(400, {"error": "send a JSON object with team_id"})
            code, body = waitlist.handle("POST", self.path.split("?", 1)[0], parsed, headers=self.headers)
            self._send(code, body)

        def log_message(self, fmt, *args) -> None:
            return

    return Handler


def serve(waitlist: Waitlist, port: int) -> None:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(waitlist))
    print(f"Mercado Dieciséis waitlist at http://127.0.0.1:{port}")
    print("This service does not open or change a venue. Verify the approved live venue before enabling participant writes. Ctrl-C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        httpd.server_close()
