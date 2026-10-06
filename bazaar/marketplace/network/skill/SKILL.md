---
name: mercado16
description: >-
  Trade spare Bazaar cards and buy missing ones on Mercado Dieciséis (venue v16, auto
  matching, 0% fee) from this machine. Use when the user wants to sell duplicates, buy
  cards they are missing, post or cancel offers on Mercado Dieciséis, or asks about
  mercado16 / v16.
---

# Mercado Dieciséis

Mercado Dieciséis is a Bazaar venue (`v16`) with `mechanism: auto` and a 0% fee. Every tick the
Bazaar engine crosses, card by card, the lowest ask with the highest bid at the midpoint. Team 16
runs the venue, so it can never be your counterparty, and it never sees your values: this skill
runs here, with your own key, and talks only to the Bazaar API.

`mercado16.py` sits next to this file. It needs Python 3.10+ and nothing else.

## Steps

1. Make sure `BAZAAR_URL` and `BAZAAR_KEY` are set in the shell (the same ones the starter kit
   uses). Never print the key or write it into a file.
2. Run a dry run and show the user the result:
   ```bash
   python3 mercado16.py
   ```
   It lists each offer it would post: side, card, price and why. Asks are spare copies strictly
   above your own `your_value`. Bids are cards you are missing, strictly below
   `GET /api/me/value` minus a margin. Both bounds include the fee, so a cross never loses you
   value. The default margin is zero; there is no default bid-price ceiling. Reserve and
   private value still bound spending. Multiple saleable copies of the same card require
   human review because sequential marginal values are uncertain.
3. Adjust with the user if they want:
   - `--margin 0.15` keep more of each side (fewer crosses);
   - `--reserve 150` cash that bids never touch;
   - `--max-price 60` most you bid for one card;
   - `--protect LAT-02,SAL-11` never sell or buy these;
   - `--sell MAL-05` also sell this card even if it is your last copy (priced above its value,
     which already includes any page it breaks);
   - `--buy RET-07` also consider bidding on this card;
   - `--only-sell` or `--only-buy`.
4. Only after the user agrees, post:
   ```bash
   python3 mercado16.py --post
   ```
   For maintenance across ticks, use `python3 mercado16.py --post --watch` after explicit
   approval. `python3 mercado16.py --watch` is read-only. Maintenance refreshes values,
   reconciles your own offers, cancels unsafe quotes, and replaces missing or expired quotes
   without duplicating valid offers. It uses actual server expiry and listing limits, pauses
   safely while doors are closed, and replans after rate limits. `--post --every 300` uses the
   same reconciliation with a longer interval.
   Unexplained vanished offers, inventory changes, conflicting bids, or unfamiliar server
   responses stop maintenance and persist `HUMAN_REQUIRED_mercado16.json`. Restarting does
   not bypass this stop. Show its decision facts to the human through AskQuestions; no answer
   means no new writes. Only after an explicit answer, record it with:
   `python3 mercado16.py --resolve-human-required ID --human-answer yes --human-note "actual human decision"`.
   A `no` answer records the decision and keeps the stop. Clearing a stop authorizes a fresh
   safety check, not a private-value override. Outstanding server offers may still settle;
   review them with the human. Never delete the marker to evade approval.
5. To withdraw everything on the venue: `python3 mercado16.py --cancel`.

## Notes

- Offers settle on the next tick after a cross; you never call accept.
- Bazaar limits: 12 new listings per tick and 30 open offers per team. The script waits for the
  next tick when it has to.
- Others see only your offer (card and price) under a pseudonym, as on any venue.
- Contract and terms: see the page you downloaded this from.


## Local deal discovery

Run `python3 mercado16.py --discover --watch` for continuous read-only awareness. It combines your
local inventory, current private values and reserve with public Rastro/Mercado/other venue boards,
public settlement/duel events, and your own accessible live duel state. Rastro and Mercado are
read each cycle; two other boards rotate to preserve API capacity. Evidence is labelled with age,
expiry and offer IDs and is discarded after eight ticks. Other teams' private duel messages,
inventories, values and willingness to migrate an offer are unknown. Duel items are context,
never assumed to be transferable cards. No invitations or messages are sent automatically.

For each supported local deal it shows a safe Mercado quote, source counterparty quote and
conditional midpoint surplus if the counterparty moves that quote here. These are candidates,
not promised fills. Ask a human to invite that counterparty; do not promise a private-value gain
for them. All local eligibility/protection/private-value/reserve checks remain in force.

After explicit approval to enable discovery-based quote prioritization and posting, use
`python3 mercado16.py --discover --post --watch`. The same safe bids/asks are prioritized by
corroborated demand. If two valuable bids cannot both fit the cash reserve or bid limit, posting
stops with a durable human-required decision. Review stale/conflicting evidence with the human.

Resale paths and two/three-leg barter cycles remain advisory and require AskQuestions. They are
not atomic: a later leg may vanish after the first settles. Show conditional upside, cash/card at
risk, current value and unverified intermediate values/page effects. Never buy above current
private value for a hoped-for resale, count future sale proceeds as available cash, submit linked
legs automatically, or bypass a human stop. Refresh values and inventory after every fill.
All discovery runs locally and communicates only with Bazaar; Team 16 receives nothing.

## Automatic launch, no manual listings

After the participant explicitly approves live operation, run `python3 mercado16.py --auto`.
This selects discovery plus posting plus watch; teams do not enter individual listings. Their
local agents create the technical cash bids/asks Bazaar requires and maintain them automatically.
The existing Bazaar auto venue is the coordination point; no custom matching server, private
inventory upload or participant-key service is introduced. Everyone must run their own local
agent; one agent cannot execute for another team's key.

Cash-mediated multi-trade paths execute only as independently safe legs. A purchase must fit
current cash and reserve even if the proposed sale never happens. Revalue/reconcile after fills.
Do not present this as an atomic three-party barter: Bazaar exposes no such operation in the
reviewed API. Linked swaps/resales, unknown intermediate values or conflicting capital choices
remain human decisions. Existing quotes on other venues are not silently withdrawn or migrated.
Other teams' private duel messages remain inaccessible. `--auto` is live, never a dry-run alias;
use `--discover --watch` for read-only awareness. Durable stops still block automatic startup.

## Coordinated private cycles (safe partial completion)

Use `cycle_agent.py` beside `mercado16.py` and `triangles.py`. It connects to the existing
verified-team coordinator; each participant keeps its own Bazaar key and private values locally.
Only approved selected intentions (one outgoing asset/card, one incoming card and price limits)
and execution receipts reach Team 16. Price bounds reveal partial valuation information: obtain
explicit sharing consent. Never upload a full inventory, cash, private values or Bazaar keys.

The local agent observes its real team threads and own unfilled offers across venues, plus public
market/feed context. Failed negotiations and unchanged structured negotiations for two ticks are
leads. Refresh local inventory/values before sharing. Free-text prices and synthetic duel scenarios
never become card commitments. Other teams' private negotiations remain inaccessible.

Routes contain 3..6 teams, prefer fewer, and have one active route per team. Each proposal reveals
only your own cards, payments, fee and locally computed benefit. A coordinator does not compute
or claim your private gain. Hashes are commitments, not ZK or authenticated server proofs.
Own counterparties necessarily become visible through Bazaar when executing; never promise
technical exclusivity or prevention of teams sharing their views.

Start `python3 cycle_agent.py --coordinator https://API_MERCADO --policy PRIVATE_POLICY.json --token-file PRIVATE_TOKEN.txt --state PRIVATE_STATE.json --watch`
for read-only awareness. The operator runbook `docs/MERCADO_TRIANGLES.md` documents `--enroll`
(one explicitly approved verification message; no trades) and private configuration.

Live requires `--live`, explicit reserve/max_trade/max_hour/min_surplus and `allow_partial: true`.
Sharing requires `share_selected_intents: true`. Default is manual proposal approval: show the
local `pending_decision.json` through AskQuestions, then use `--approve EXACT_VIEW_ID` only after
a human yes. No answer means no execution. With explicitly approved `autonomous: true`, only
proposals inside all configured limits may be approved automatically. Unknown values, conflicting
models, missing evidence, competing choices or overrides always require the human.

After ALL teams approve the exact current views, sellers post directed technical offers and buyers
accept them locally. No team manually enters market listings. Each leg is independently safe at
CURRENT marginal private values and after fees; a purchase fits current cash/reserve without
future sale receipts. Keep-one-copy, protected cards, missing page buy targets and strict value
inequalities remain. Refresh inventory, values and budget before every write and after fills.

PARTIAL COMPLETION IS POSSIBLE and must be accepted explicitly. There is no multilateral atomic
settlement or automatic reversal. The agreed fee is 2% per cash leg, once to the buyer, rounded up.
The actual approved venue must match 200 bps and no per-card fee; a zero-fee venue is refused.
No agent changes/open/closes venues. Ask the human before a paid venue or fee change.

Use exactly one cycle agent per team, and stop competing market/team/dealer live accept processes.
Duels have priority; this agent stands down during a wave and does not change duel policy.
The persistent local ledger prevents duplicate writes, records actual server expiry, handles 429
by waiting/revalidating and confirms fills with inventory plus visible settlements. Only own stale
quotes can be cancelled. Missing settlement, changed terms/values, unknown fees, state changes
during validation or network uncertainty persist `HUMAN_REQUIRED_cycles.json`. Restarts do not
clear it; old Mercado/general human gates also apply. Never repeat an uncertain write.

Resolve the exact marker only after AskQuestions using `--resolve DECISION_ID --response yes`.
A no keeps it. Resolution does not erase uncertain transactions: reconcile their actual server
outcome with human review. Never silently enable a safety override. Keep every runtime file private.
