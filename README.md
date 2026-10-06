# Mercado Dieciséis

**Team 16 · Claude Hackathon Madrid · The Bazaar · 2–4 October 2026**
Recognised by the organisers as *the most sophisticated technical implementation* of the competition.

Landing page: <https://mercado-dieciseis.vercel.app>

The Bazaar was a live market game: AI agents traded collectible cards with other teams'
agents and with simulated dealers, each team holding private valuations. Over the weekend our
system grew from a handful of negotiation scripts into an agentic orchestration layer. This
repository open-sources one piece of it: **Mercado**, a coordination engine that finds trades
no pair of teams can close on its own.

## What Mercado does

Bilateral bidding misses value that only exists in a cycle. A wants B's card, B wants C's,
C wants A's, and no two of them have a mutually profitable swap. Mercado finds those cycles
across three or more teams, preferring fewer participants. It then asks every team to approve
its own legs and executes them as ordinary bilateral trades.

- **Every leg pays on its own.** A sale must receive strictly more than the seller's private
  marginal value. A purchase must cost strictly less than the buyer's value, including the 2%
  buyer fee, and must fit within the cash left after the team's reserve.
- **Values stay local.** Each team runs its own agent. The coordinator receives only the
  intents a team chooses to share (asset, card, price limits), its consent, and its receipts.
  It never receives keys, cash balances, full inventories or private valuations.
- **Commitments, not zero-knowledge.** Shared intents are bound with salted SHA-256
  commitments, so an approval cannot be altered after the fact. Zero-knowledge proofs are on
  the roadmap, not in this code.
- **Partial execution is explicit.** A cycle can settle partially. Every team approves that
  risk up front, and each leg re-reads state before it runs.
- **Human gates are durable.** Anything uncertain writes a persistent block that requires a
  person to resolve it. Restarting the agent does not clear it.

Read the full contract in [`docs/mercado-dieciseis-contract.md`](docs/mercado-dieciseis-contract.md)
and the cycle design in [`docs/MERCADO_TRIANGLES.md`](docs/MERCADO_TRIANGLES.md).

## Layout

| Path | Contents |
| --- | --- |
| `bazaar/marketplace/network/` | Coordinator: cycle search, terms, auth, readiness, store, HTTP service |
| `bazaar/marketplace/network/skill/` | The participant skill each team runs locally (`SKILL.md`, `cycle_agent.py`) |
| `mercado_demo.py`, `demo/mercado/` | Offline deterministic replay on a synthetic market, and its explanatory pages |
| `network.py` | Waitlist and coordinator CLI |
| `tests/` | Unit and contract tests |
| `site/` | The Next.js landing page |

## Run it

Python 3.10 or newer. There are no third-party Python dependencies.

```bash
python3 -m unittest discover -s tests       # 102 tests
python3 mercado_demo.py > /tmp/results.json # synthetic replay: no network, no credentials
python3 -m http.server 8080 --directory demo/mercado
```

Every number the demo produces comes from a synthetic simulation. None of them are trades
from the event.

Talking to a live Bazaar requires the organisers' `bazaar_sdk.py`, which is not
redistributed here. Copy it into the repository root and put `BAZAAR_KEY` in a local `.env`.

### Landing page

```bash
cd site
npm install
npm run dev
```

The page uses Next.js 16 and Tailwind CSS v4, and is bilingual (`/en`, `/es`).

## What is not here

Our trading strategy, rival-team intelligence, live event data and private negotiation
records stay in a private repository.

## Team

- [Javier Alaves](https://www.linkedin.com/in/javieralaves/)
- [Javier García Pavón](https://www.linkedin.com/in/javier-garc%C3%ADa-pav%C3%B3n-99a970435/)
- [Ricardo López Alcántara](https://www.linkedin.com/in/ricardol%C3%B3pezalc%C3%A1ntara/)

Thanks to [Anthropic](https://www.anthropic.com), Causa Prima and Nova for organising the
Claude Hackathon Madrid.

## License

[MIT](LICENSE)
