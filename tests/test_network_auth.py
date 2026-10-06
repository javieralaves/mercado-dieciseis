"""A team is verified only by a message Bazaar shows as coming from that team. The token is stored as a hash."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from bazaar.marketplace.network.auth import begin, claim, messages_from_client, observe, phrase
from bazaar.marketplace.network.service import Waitlist
from bazaar.marketplace.network.store import Store


def open_store(directory: Path) -> tuple[Store, Waitlist]:
    store = Store(directory / "network.sqlite")
    return store, Waitlist(store)


class FakeThreads:
    def __init__(self, threads):
        self.threads = threads
        self.calls = []

    def my_threads(self, status=None):
        self.calls.append(("GET", "/api/me/threads", status))
        return {"threads": [{"id": t["id"], "with": t["with"]} for t in self.threads]}

    def thread(self, thread_id):
        self.calls.append(("GET", f"/api/threads/{thread_id}"))
        return next(t for t in self.threads if t["id"] == thread_id)

    def say(self, *args, **kwargs):
        raise AssertionError("verification must not post")

    def open_thread(self, *args, **kwargs):
        raise AssertionError("verification must not post")


class Verification(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store, self.api = open_store(Path(self.tmp.name))
        _, joined = self.api.handle("POST", "/v1/waitlist", {"team_id": "t07"})
        self.participant = joined["participant_id"]
        _, other = self.api.handle("POST", "/v1/waitlist", {"team_id": "t03"})
        self.other = other["participant_id"]

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def challenge(self, participant_id=None):
        code, body = self.api.handle("POST", "/v1/verify", {"participant_id": participant_id or self.participant})
        self.assertEqual(code, 200)
        return body

    def test_only_the_claimed_team_can_verify_and_the_token_is_stored_as_a_hash(self):
        challenge = self.challenge()
        self.assertEqual(challenge["send_to"], "t16")
        self.assertTrue(challenge["message"].startswith("MD16 VERIFY "))
        again = self.challenge()
        self.assertEqual(again["verification_nonce"], challenge["verification_nonce"])

        copied = observe(self.store, [{
            "sender": "t03", "with": "t16", "text": challenge["message"],
        }])
        self.assertEqual(copied, [])
        early = claim(self.store, self.participant, challenge["verification_nonce"])
        self.assertEqual(early["status"], 409)

        verified = observe(self.store, [
            {"sender": "t16", "with": "t07", "text": challenge["message"]},
            {"sender": "t07", "with": "t03", "text": challenge["message"]},
            {"sender": "t07", "with": "t16", "text": challenge["message"]},
        ])
        self.assertEqual(verified, ["t07"])
        self.assertEqual(self.store.public_status()["ready"], 0)

        wrong = self.api.handle("POST", "/v1/verify/claim", {
            "participant_id": self.participant, "verification_nonce": "MD16-NOPE",
        })
        self.assertEqual(wrong[0], 400)
        first = self.api.handle("POST", "/v1/verify/claim", {
            "participant_id": self.participant, "verification_nonce": challenge["verification_nonce"],
        })
        self.assertEqual(first[0], 200)
        token = first[1]["token"]
        self.assertTrue(token.startswith("md16_"))
        second = self.api.handle("POST", "/v1/verify/claim", {
            "participant_id": self.participant, "verification_nonce": challenge["verification_nonce"],
        })
        self.assertEqual(second[0], 409)
        self.assertNotIn("token", second[1])

        me = self.api.handle("GET", "/v1/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me[0], 200)
        self.assertEqual(me[1]["participant_id"], self.participant)
        self.assertEqual(me[1]["team_id"], "t07")
        self.assertEqual(me[1]["status"], "verified")
        self.assertEqual(set(me[1]), {"participant_id", "team_id", "status", "signals"})
        self.assertNotIn(self.other, json.dumps(me[1]))
        self.assertNotIn("token_hash", json.dumps(me[1]))
        self.assertEqual(self.api.handle("GET", "/v1/me", headers={"Authorization": "Bearer md16_nope"})[0], 401)
        self.assertEqual(self.api.handle("POST", "/v1/verify", {"participant_id": self.participant})[0], 409)

        saved = self.store.path.read_bytes()
        self.assertNotIn(token.encode(), saved)
        self.assertNotIn(b"bazaar_key", saved)

    def test_a_key_is_refused_and_a_duplicate_join_stays_one_row(self):
        code, body = self.api.handle("POST", "/v1/verify", {
            "participant_id": self.participant, "bazaar_key": "secret-value",
        })
        self.assertEqual(code, 400)
        self.assertNotIn("secret-value", json.dumps(body))
        _, again = self.api.handle("POST", "/v1/waitlist", {"team_id": "t07"})
        self.assertEqual(again["participant_id"], self.participant)
        self.assertEqual(self.store.registration_count(), 2)

    def test_reader_only_gets_threads_and_a_foreign_thread_does_not_count(self):
        challenge = self.challenge()
        code = challenge["message"].split()[-1]
        client = FakeThreads([{
            "id": 9,
            "with": "t07",
            "messages": [
                {"sender": "t07", "text": phrase(code)},
                {"sender": "you", "text": phrase(code)},
            ],
        }])
        messages = messages_from_client(client)
        self.assertEqual([call[0] for call in client.calls], ["GET", "GET"])
        self.assertEqual(observe(self.store, messages), ["t07"])
        self.assertEqual(self.store.by_team("t03")["status"], "joined")
        self.assertEqual(self.store.by_team("t07")["status"], "verified")

    def test_an_older_waitlist_database_can_verify(self):
        path = Path(self.tmp.name) / "old.sqlite"
        db = sqlite3.connect(path)
        db.execute(
            """CREATE TABLE participants (
                id TEXT PRIMARY KEY, team_id TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL, joined_at TEXT NOT NULL
            )"""
        )
        db.execute("INSERT INTO participants VALUES ('p_old', 't04', 'joined', '2026-01-01T00:00:00Z')")
        db.commit()
        db.close()
        store = Store(path)
        self.addCleanup(store.close)
        api = Waitlist(store)
        code, body = api.handle("POST", "/v1/verify", {"participant_id": "p_old"})
        self.assertEqual(code, 200)
        self.assertIn("MD16 VERIFY", body["message"])
