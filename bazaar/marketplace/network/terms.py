"""Mercado Dieciséis venue and fee, in one place for the page, the contract and the skill.

Mercado Dieciséis runs on Team 16's free starter stall, `v16`: `auto` mechanism, no fee, no bond.
The 1% founding -> 2% schedule below applies only if we later open a paid venue (BAZ-47).
"""
from datetime import datetime
from zoneinfo import ZoneInfo

VENUE = "v16"
VENUE_NAME = "Puesto de Team 16"
LIVE_FEE_BPS = 0

MADRID = ZoneInfo("Europe/Madrid")
CUTOFF = datetime(2026, 10, 4, 10, 0, tzinfo=MADRID)
FOUNDING_BPS = 100
STANDARD_BPS = 200
FEE_PER_CARD = 0


def fee_bps_at(when: datetime) -> int:
    """The fee a paid Mercado Dieciséis venue would charge at `when`."""
    if when.tzinfo is None:
        raise ValueError("pass an aware datetime")
    return FOUNDING_BPS if when < CUTOFF else STANDARD_BPS


def pricing_line(when: datetime | None = None) -> str:
    return f"0% fee, no per-card fee, on venue {VENUE}."
