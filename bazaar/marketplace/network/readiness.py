"""Who counts toward the five-team threshold, and why the others do not.

Ready means a verified team has agreed to run its own agent on the venue and to trade there
once it opens. Its values stay on its machine. A signup alone does not count. Not interested never counts.
"""
from bazaar.marketplace.network.store import THRESHOLD, Store

SIGNAL_LABELS = (
    ("connect_agent", "has not agreed to run its agent on the venue"),
    ("execute_when_live", "has not agreed to trade once the venue opens"),
)


def gaps(row: dict) -> list[str]:
    if row.get("not_interested"):
        return ["not interested"]
    missing = []
    if not row.get("verified_at"):
        missing.append("not verified")
    for field, label in SIGNAL_LABELS:
        if not row.get(field):
            missing.append(label)
    return missing


def public_view(row: dict) -> dict:
    """What that participant may see about itself. No nonce, hash, or other team."""
    return {
        "participant_id": row["id"],
        "team_id": row["team_id"],
        "status": row["status"],
        "signals": {
            "connect_agent": bool(row.get("connect_agent")),
            "execute_when_live": bool(row.get("execute_when_live")),
            "not_interested": bool(row.get("not_interested")),
        },
    }


def validation_text(store: Store) -> str:
    public = store.public_status()
    ready, threshold = public["ready"], public["threshold"]
    demand = (
        "enough ready teams to consider launching"
        if ready >= threshold
        else "not enough ready teams to launch"
    )
    lines = ["VALIDATION", f"{ready} / {threshold} ready", demand, ""]
    for row in store.participants():
        missing = gaps(row)
        state = str(row["status"]).replace("_", " ")
        if not missing:
            lines.append(f"{row['team_id']} ready")
            lines.append("  counts toward the threshold")
        else:
            lines.append(f"{row['team_id']} {state}")
            lines.append("  does not count: " + "; ".join(missing))
    if not store.participants():
        lines.append("no teams yet")
    return "\n".join(lines)


def enough_to_launch(store: Store) -> bool:
    return store.public_status()["ready"] >= THRESHOLD
