"""Mercado Dieciséis waitlist.

    python3 network.py --status          # ready count and threshold; no team is named
    python3 network.py --serve           # page and API on this machine only
    python3 network.py --serve --port 8776

Joining records a team id and a stable participant id. It does not make the team ready,
and it does not open a venue.

    python3 network.py --validation        # which teams count, and why
    python3 network.py --check-verifications

Reads open team threads with GET and marks a team verified when its own message
matches the nonce it was given. It never posts, and it never prints a token.

    python3 network.py --export waitlist-site --base-url https://mercado16.vercel.app

Writes the static waitlist site (page, contract, skill files) into `waitlist-site/`;
deploy that folder. Do not export into `site/`, which holds the landing page.
"""
import argparse

from bazaar.marketplace.network.auth import messages_from_client, observe
from bazaar.marketplace.network.readiness import validation_text
from bazaar.marketplace.network.service import Waitlist, serve
from bazaar.marketplace.network.store import DEFAULT_DB, Store
from bazaar.marketplace.network.terms import VENUE


def status_text(store: Store) -> str:
    public = store.public_status()
    return (
        f"WAITLIST\n"
        f"{public['ready']} / {public['threshold']} ready\n"
        f"{store.registration_count()} joined\n"
        f"venue {VENUE} live"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Mercado Dieciséis private network")
    ap.add_argument("--serve", action="store_true", help="serve the waitlist page and API on 127.0.0.1")
    ap.add_argument("--status", action="store_true", help="print the public ready count")
    ap.add_argument("--validation", action="store_true", help="operator view of who counts as ready")
    ap.add_argument("--check-verifications", action="store_true", help="GET open threads and apply verification messages")
    ap.add_argument("--export", metavar="DIR", help="write the static public site into DIR")
    ap.add_argument("--base-url", default="", help="public address of the site, used in the install commands")
    ap.add_argument("--port", type=int, default=8776)
    ap.add_argument("--cycles", action="store_true", help="enable verified-team private route coordination with --serve")
    ap.add_argument("--cycle-venue", default="v16", help="approved venue for coordinated trades; agents require actual 2% fee")
    ap.add_argument("--db", default=str(DEFAULT_DB), help="private sqlite file; kept out of git")
    args = ap.parse_args()
    if args.cycles and not args.serve:
        ap.error("--cycles requires --serve")
    if sum((args.serve, args.status, args.validation, args.check_verifications, bool(args.export))) != 1:
        ap.error("choose one of --serve, --status, --validation, --check-verifications or --export")
    if args.export:
        if not args.base_url.startswith("https://"):
            ap.error("--export needs --base-url https://...")
        from bazaar.marketplace.network.site import build
        for path in build(args.export, args.base_url):
            print(path)
        return
    store = Store(args.db)
    try:
        if args.status:
            print(status_text(store))
            return
        if args.validation:
            print(validation_text(store))
            return
        if args.check_verifications:
            from common import client
            found = observe(store, messages_from_client(client()))
            print(f"verified {len(found)}")
            return
        cycles = None
        if args.cycles:
            from bazaar.marketplace.network.cycles import Cycles
            from common import client
            cycles = Cycles(store, lambda: client().clock(), venue=args.cycle_venue)
        serve(Waitlist(store, cycles=cycles), args.port)
    finally:
        store.close()


if __name__ == "__main__":
    main()
