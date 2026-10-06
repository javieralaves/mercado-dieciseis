"""Minimum waitlist state. Joining is not the same thing as being ready."""
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from secrets import token_hex

from bazaar.store.paths import DATA

PRIVATE_DIR = DATA / "private_network"
DEFAULT_DB = PRIVATE_DIR / "network.sqlite"

THRESHOLD = 5
OUR_TEAM = "t16"
JOINED = "joined"
READY = "ready"
VERIFIED = "verified"
NOT_INTERESTED = "not_interested"
SIGNAL_FIELDS = ("connect_agent", "execute_when_live", "not_interested")


def _lock_down(path: Path, directory_created: bool) -> None:
    if directory_created:
        path.parent.chmod(0o700)
    for candidate in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm")):
        if candidate.is_file():
            candidate.chmod(0o600)


class Store:
    def __init__(self, path: Path | str = DEFAULT_DB):
        self.path = Path(path)
        directory_created = not self.path.parent.exists()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
            os.close(fd)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS participants (
                id TEXT PRIMARY KEY,
                team_id TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                joined_at TEXT NOT NULL
            )
            """
        )
        self._migrate()
        self._db.commit()
        _lock_down(self.path, directory_created)

    def _migrate(self) -> None:
        existing = {row["name"] for row in self._db.execute("PRAGMA table_info(participants)")}
        for name, decl in (
            ("verification_nonce", "TEXT"),
            ("verified_at", "TEXT"),
            ("token_hash", "TEXT"),
            ("connect_agent", "INTEGER NOT NULL DEFAULT 0"),
            ("execute_when_live", "INTEGER NOT NULL DEFAULT 0"),
            ("not_interested", "INTEGER NOT NULL DEFAULT 0"),
        ):
            if name not in existing:
                self._db.execute(f"ALTER TABLE participants ADD COLUMN {name} {decl}")

    def close(self) -> None:
        self._db.close()

    def join(self, team_id: str) -> dict:
        with self._lock:
            existing = self._one(team_id)
            if existing:
                return existing
            row = {
                "id": "p_" + token_hex(8),
                "team_id": team_id,
                "status": JOINED,
                "joined_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            try:
                self._db.execute(
                    "INSERT INTO participants (id, team_id, status, joined_at) VALUES (?, ?, ?, ?)",
                    (row["id"], row["team_id"], row["status"], row["joined_at"]),
                )
                self._db.commit()
            except sqlite3.IntegrityError:
                self._db.rollback()
                return self._one(team_id)
            _lock_down(self.path, directory_created=False)
            return row

    def set_signals(self, participant_id: str, updates: dict) -> dict | None:
        unknown = set(updates) - set(SIGNAL_FIELDS)
        if unknown:
            raise ValueError("unknown signal")
        with self._lock:
            row = self._db.execute(
                "SELECT id FROM participants WHERE id = ?", (participant_id,)
            ).fetchone()
            if row is None:
                return None
            assignments = ", ".join(f"{name} = ?" for name in updates)
            values = [1 if updates[name] else 0 for name in updates]
            self._db.execute(
                f"UPDATE participants SET {assignments} WHERE id = ?",
                (*values, participant_id),
            )
            self._apply_status(participant_id)
            self._db.commit()
            found = self._db.execute("SELECT * FROM participants WHERE id = ?", (participant_id,)).fetchone()
            return dict(found)

    def participants(self) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM participants ORDER BY team_id").fetchall()
            return [dict(row) for row in rows]

    def public_status(self) -> dict:
        with self._lock:
            ready = self._db.execute(
                "SELECT COUNT(*) AS n FROM participants WHERE status = ?", (READY,)
            ).fetchone()["n"]
        return {"state": "waitlist", "ready": ready, "threshold": THRESHOLD}

    def registration_count(self) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) AS n FROM participants").fetchone()["n"]

    def by_team(self, team_id: str) -> dict | None:
        with self._lock:
            return self._one(team_id)

    def by_id(self, participant_id: str) -> dict | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM participants WHERE id = ?", (participant_id,)).fetchone()
            return dict(row) if row else None

    def set_nonce(self, participant_id: str, nonce: str) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE participants SET verification_nonce = ? WHERE id = ?",
                (nonce, participant_id),
            )
            self._db.commit()

    def mark_verified(self, participant_id: str, when: str) -> bool:
        with self._lock:
            cursor = self._db.execute(
                "UPDATE participants SET verified_at = ? WHERE id = ? AND verified_at IS NULL",
                (when, participant_id),
            )
            if cursor.rowcount:
                self._apply_status(participant_id)
            self._db.commit()
            return cursor.rowcount == 1

    def _apply_status(self, participant_id: str) -> None:
        row = self._db.execute("SELECT * FROM participants WHERE id = ?", (participant_id,)).fetchone()
        if row is None:
            return
        if row["not_interested"]:
            status = NOT_INTERESTED
        elif not row["verified_at"]:
            status = JOINED
        elif row["connect_agent"] and row["execute_when_live"]:
            status = READY
        else:
            status = VERIFIED
        self._db.execute("UPDATE participants SET status = ? WHERE id = ?", (status, participant_id))

    def save_token(self, participant_id: str, digest: str) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE participants SET token_hash = ?, verification_nonce = NULL WHERE id = ? AND token_hash IS NULL",
                (digest, participant_id),
            )
            self._db.commit()

    def by_token_hash(self, digest: str) -> dict | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM participants WHERE token_hash = ?", (digest,)
            ).fetchone()
            return dict(row) if row else None

    def _one(self, team_id: str) -> dict | None:
        row = self._db.execute("SELECT * FROM participants WHERE team_id = ?", (team_id,)).fetchone()
        return dict(row) if row else None
