"""Prove a waitlist row is the Bazaar team it names, without ever taking that team's key.

The team sends one exact line to Team 16 with its own agent. We only trust a message
we read back from that team. The Mercado Dieciséis token is shown once and stored as a hash.
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timezone

from bazaar.marketplace.network.readiness import public_view
from bazaar.marketplace.network.store import OUR_TEAM, VERIFIED, Store

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6


def new_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


def phrase(code: str) -> str:
    return f"MD16 VERIFY {code}"


def nonce_for(code: str) -> str:
    return f"MD16-{code}"


def code_from_nonce(nonce: str) -> str:
    return nonce.split("-", 1)[-1] if nonce else ""


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def begin(store: Store, participant_id: str) -> dict | None:
    """Return the challenge, or None when the participant does not exist.

    `issued` is False once a token has already been claimed.
    """
    row = store.by_id(participant_id)
    if row is None:
        return None
    if row.get("token_hash"):
        return {"issued": False, "participant_id": row["id"], "status": row["status"]}
    code = code_from_nonce(row.get("verification_nonce") or "") or new_code()
    if not row.get("verification_nonce"):
        store.set_nonce(row["id"], nonce_for(code))
    return {
        "issued": True,
        "participant_id": row["id"],
        "status": "verification_required",
        "verification_nonce": nonce_for(code),
        "message": phrase(code),
        "send_to": OUR_TEAM,
    }


def observe(store: Store, messages: list[dict]) -> list[str]:
    """Mark teams verified when a message is from that team and matches its own code.

    Returns the team ids newly verified. A message from anyone else is ignored,
    including one that copies another team's code.
    """
    verified = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for message in messages:
        if not isinstance(message, dict):
            continue
        sender = str(message.get("sender") or "").strip().lower()
        text = str(message.get("text") or "").strip()
        party = str(message.get("with") or "").strip().lower()
        if not sender or sender in {OUR_TEAM, "you"}:
            continue
        if party and party not in {OUR_TEAM, sender}:
            continue
        row = store.by_team(sender)
        if row is None or row.get("verified_at") or not row.get("verification_nonce"):
            continue
        if text != phrase(code_from_nonce(row["verification_nonce"])):
            continue
        if store.mark_verified(row["id"], now):
            verified.append(sender)
    return verified


def claim(store: Store, participant_id: str, nonce: str) -> dict:
    row = store.by_id(participant_id)
    if row is None:
        return {"error": "unknown participant", "status": 404}
    if row.get("token_hash"):
        return {"error": "already verified", "status": 409}
    if not row.get("verified_at"):
        return {"error": "message not seen yet", "status": 409}
    if not hmac.compare_digest(row.get("verification_nonce") or "", nonce or ""):
        return {"error": "verification nonce does not match", "status": 400}
    token = "md16_" + secrets.token_urlsafe(32)
    store.save_token(row["id"], token_hash(token))
    return {"status": 200, "token": token, "participant_id": row["id"], "team_status": VERIFIED}


def identify(store: Store, token: str) -> dict | None:
    if not token:
        return None
    row = store.by_token_hash(token_hash(token))
    if row is None:
        return None
    return public_view(row)


def messages_from_client(client) -> list[dict]:
    """Read open threads with GET only. The caller must not use this to post."""
    listed = client.my_threads(status="open").get("threads") or []
    messages = []
    for summary in listed:
        if not isinstance(summary, dict):
            continue
        thread_id = summary.get("id") or summary.get("thread")
        detail = client.thread(thread_id) if thread_id is not None else summary
        thread = detail.get("thread", detail) if isinstance(detail, dict) else {}
        if not isinstance(thread, dict):
            continue
        other = str(thread.get("with") or summary.get("with") or "").lower()
        for message in thread.get("messages") or []:
            if not isinstance(message, dict):
                continue
            messages.append({
                "sender": message.get("sender"),
                "text": message.get("text"),
                "with": other,
            })
    return messages
