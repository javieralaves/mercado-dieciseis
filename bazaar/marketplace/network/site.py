"""The public Mercado Dieciséis site: a static page, the contract and the skill files, built from the repo.

Nothing on it receives anything from teams: there is no form and no API.
"""
import html
import json
import shutil
from pathlib import Path

from bazaar.marketplace.network.service import CONTRACT, contract_page
from bazaar.marketplace.network.terms import VENUE, VENUE_NAME, pricing_line

SKILL_DIR = Path(__file__).resolve().parent / "skill"
SKILL_FILES = ("SKILL.md", "mercado16.py", "triangles.py", "cycle_agent.py")

INDEX = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mercado Dieciséis</title>
<style>
  body {{ margin: 0; font: 18px/1.5 ui-sans-serif, system-ui, sans-serif; background: #f6f3ec; color: #1c1915; }}
  main {{ max-width: 44rem; margin: 3.5rem auto; padding: 0 1.25rem; }}
  h1 {{ font-size: 1.8rem; line-height: 1.2; margin: 0 0 0.75rem; }}
  h2 {{ font-size: 1.15rem; margin: 2rem 0 0.5rem; }}
  p, li {{ margin: 0 0 0.6rem; }}
  .live {{ display: inline-block; padding: 0.15rem 0.55rem; border-radius: 999px; background: #1d6b3a; color: #fff; font-size: 0.85rem; }}
  pre {{ background: #1c1915; color: #f6f3ec; padding: 0.9rem 1rem; border-radius: 6px; overflow-x: auto;
         font: 14px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace; white-space: pre; }}
  code {{ font: 0.9em ui-monospace, SFMono-Regular, Menlo, monospace; }}
</style>
</head>
<body>
<main>
  <p><span class="live">Live</span> venue <code>{venue}</code> · {pricing}</p>
  <h1>Mercado Dieciséis: a Bazaar market that never sees your values</h1>
  <p>Your agent runs where it already runs, in your own Cursor or Claude. It posts offers on <code>{venue}</code> ({venue_name}) and the Bazaar <code>auto</code> engine crosses them every tick at the midpoint.
  Your values, cards, cash and key never leave your machine. Team 16 cannot trade on its own venue, so it is never your counterparty.</p>

  <h2>Sell your duplicates, buy what completes your pages</h2>
  <ul>
    <li>Sells only spare copies, never below what they are worth to you.</li>
    <li>Bids only on page cards you are missing, below what they are worth to you, inside a cash reserve.</li>
    <li>Dry run first: it shows every offer and why. Nothing is posted until you say <code>--post</code>.</li>
  </ul>

  <h2>Install (Cursor)</h2>
<pre>mkdir -p .cursor/skills/mercado16 &amp;&amp; cd .cursor/skills/mercado16 &amp;&amp; curl -fsSLO {base}/skill/SKILL.md -O {base}/skill/mercado16.py -O {base}/skill/triangles.py -O {base}/skill/cycle_agent.py
python3 mercado16.py          # dry run, needs BAZAAR_URL and BAZAAR_KEY like the kit</pre>
  <h2>Install (Claude Code)</h2>
<pre>mkdir -p .claude/skills/mercado16 &amp;&amp; cd .claude/skills/mercado16 &amp;&amp; curl -fsSLO {base}/skill/SKILL.md -O {base}/skill/mercado16.py -O {base}/skill/triangles.py -O {base}/skill/cycle_agent.py
python3 mercado16.py</pre>
  <p>Or tell your agent: <em>“Install the Mercado Dieciséis skill from {base} and show me a dry run.”</em></p>
  <p>Then <code>python3 mercado16.py --post</code> to post, <code>--cancel</code> to withdraw everything. Running it again never doubles an offer.</p>

  <h2>Discover likely deals locally</h2>
  <p>Read Rastro, Mercado and other public markets alongside your own inventory and private values:
  <code>python3 mercado16.py --discover --watch</code> is read-only. Offers show their source, age and
  conditional upside. Your own duel state is context; other teams' private negotiations remain private.</p>
  <p>After your approval, <code>python3 mercado16.py --auto</code> maintains safe quotes prioritized by observed
  demand. Competing valuable bids stop for human judgement. Resale and barter paths are advisory;
  teams do not enter listings manually. Bazaar requires technical offers, created automatically by each local agent. Linked trades and invitations still require human review.</p>

  <h2>Private coordinated cycles</h2>
  <p><a href="/skill/cycle_agent.py">cycle_agent.py</a> runs locally for each team. It observes your real
  failed/stalled negotiations and public markets, shares only selected intentions with your approval,
  and proposes cycles of three or more teams, preferring fewer. You see your own cards and net benefit.</p>
  <p>After every team accepts, local agents execute individually safe directed trades on the approved
  venue. Partial completion is possible; each purchase uses existing cash, never a hoped-for sale.
  Human approval is the default. Explicit configurable limits can authorize autonomous safe decisions.</p>
  <p>Coordinated execution requires an actual 2% fee per cash leg, once to the buyer, rounded up,
  and the running verified-team API. It does not change the live zero-fee venue automatically.
  Private values and keys stay local; selected card/price limits reach the coordinator only with consent.
  No ZK, multilateral atomicity or technical exclusivity is claimed.</p>
  <h2>Read before you run</h2>
  <p><a href="/contract">How it works</a> · <a href="/skill/mercado16.py">mercado16.py</a> (standard library only) · <a href="/skill/SKILL.md">SKILL.md</a></p>
</main>
</body>
</html>
"""

VERCEL = {
    "cleanUrls": True,
    "headers": [
        {"source": "/skill/(.*)", "headers": [{"key": "Content-Type", "value": "text/plain; charset=utf-8"}]},
    ],
}


def index_page(base: str) -> str:
    return INDEX.format(base=html.escape(base.rstrip("/")), venue=VENUE, venue_name=html.escape(VENUE_NAME),
                        pricing=html.escape(pricing_line()))


def build(out: Path, base: str) -> list[Path]:
    """Write the site into `out` (replacing it) and return the files written."""
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    (out / "skill").mkdir(parents=True)
    (out / "index.html").write_text(index_page(base), encoding="utf-8")
    (out / "contract.html").write_text(contract_page(), encoding="utf-8")
    (out / "contract.md").write_text(CONTRACT.read_text(encoding="utf-8"), encoding="utf-8")
    for name in SKILL_FILES:
        shutil.copyfile(SKILL_DIR / name, out / "skill" / name)
    (out / "vercel.json").write_text(json.dumps(VERCEL, indent=2) + "\n", encoding="utf-8")
    return sorted(p for p in out.rglob("*") if p.is_file())
