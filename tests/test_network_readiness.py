"""Ready means verified plus three yeses. The public counter stays a number; the operator view explains it."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from bazaar.marketplace.network.auth import observe
from bazaar.marketplace.network.readiness import validation_text
from bazaar.marketplace.network.service import Waitlist
from bazaar.marketplace.network.store import Store

ROOT = Path(__file__).resolve().parents[1]
YES = {"connect_agent": True, "execute_when_live": True}


def workspace(directory: Path):
    store = Store(directory / "network.sqlite")
    return store, Waitlist(store)


class Readiness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store, self.api = workspace(Path(self.tmp.name))

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def join(self, team):
        code, body = self.api.handle("POST", "/v1/waitlist", {"team_id": team})
        self.assertEqual(code, 200)
        return body["participant_id"]

    def token_for(self, team):
        participant = self.join(team)
        _, challenge = self.api.handle("POST", "/v1/verify", {"participant_id": participant})
        observe(self.store, [{"sender": team, "with": "t16", "text": challenge["message"]}])
        _, claimed = self.api.handle("POST", "/v1/verify/claim", {
            "participant_id": participant, "verification_nonce": challenge["verification_nonce"],
        })
        return claimed["token"], participant

    def test_signals_without_verification_do_not_count(self):
        participant = self.join("t07")
        self.store.set_signals(participant, YES)
        self.assertEqual(self.store.by_team("t07")["status"], "joined")
        self.assertEqual(self.store.public_status()["ready"], 0)
        text = validation_text(self.store)
        self.assertIn("t07 joined", text)
        self.assertIn("does not count: not verified", text)
        self.assertIn("not enough ready teams to launch", text)
        self.store.mark_verified(participant, "2026-10-03T00:00:00Z")
        self.assertEqual(self.store.by_team("t07")["status"], "ready")
        self.assertEqual(self.store.public_status()["ready"], 1)
        _, public = self.api.handle("GET", "/v1/status")
        self.assertNotIn("t07", json.dumps(public))

    def test_verified_team_becomes_ready_only_when_both_answers_are_yes(self):
        token, _ = self.token_for("t07")
        other, _ = self.token_for("t03")
        headers = {"Authorization": f"Bearer {token}"}
        partial = self.api.handle("POST", "/v1/me/signals", {"connect_agent": True}, headers=headers)
        self.assertEqual(partial[0], 200)
        self.assertEqual(partial[1]["status"], "verified")
        self.assertEqual(self.store.public_status()["ready"], 0)
        text = validation_text(self.store)
        self.assertIn("t07 verified", text)
        self.assertIn("has not agreed to trade once the venue opens", text)
        self.assertEqual(
            self.api.handle("POST", "/v1/me/signals", {"share_intent": True}, headers=headers)[0], 400,
        )
        self.assertNotIn("t07 ready", text)

        done = self.api.handle("POST", "/v1/me/signals", {"execute_when_live": True}, headers=headers)
        self.assertEqual(done[1]["status"], "ready")
        self.assertEqual(self.store.public_status()["ready"], 1)
        self.assertIn("t07 ready", validation_text(self.store))
        self.assertIn("counts toward the threshold", validation_text(self.store))

        stolen = self.api.handle("POST", "/v1/me/signals", {"not_interested": True}, headers={
            "Authorization": f"Bearer {other}",
        })
        self.assertEqual(stolen[1]["team_id"], "t03")
        self.assertEqual(self.store.by_team("t07")["status"], "ready")
        self.assertEqual(self.store.by_team("t03")["status"], "not_interested")
        self.assertIn("does not count: not interested", validation_text(self.store))

        refused, body = self.api.handle("POST", "/v1/me/signals", {
            "connect_agent": True, "bazaar_key": "secret-value",
        }, headers=headers)
        self.assertEqual(refused, 400)
        self.assertNotIn("secret-value", json.dumps(body))
        _, public = self.api.handle("GET", "/")
        self.assertNotIn("t03", public)
        self.assertIn("1 / 5 teams ready", public)

    def test_five_ready_teams_is_enough_to_consider_launch_and_four_is_not(self):
        for team in ("t01", "t02", "t03", "t04", "t05"):
            participant = self.join(team)
            self.store.mark_verified(participant, "2026-10-03T00:00:00Z")
            self.store.set_signals(participant, YES)
        self.assertEqual(self.store.public_status()["ready"], 5)
        self.assertIn("enough ready teams to consider launching", validation_text(self.store))
        self.store.set_signals(self.store.by_team("t05")["id"], {"not_interested": True})
        self.assertEqual(self.store.public_status()["ready"], 4)
        text = validation_text(self.store)
        self.assertIn("not enough ready teams to launch", text)
        self.assertNotIn("md16_", text)
        completed = subprocess.run(
            [sys.executable, "network.py", "--validation", "--db", str(self.store.path)],
            cwd=ROOT, capture_output=True, text=True, check=True,
        )
        self.assertEqual(completed.stdout.strip(), text)
        self.assertIn("t01 ready", completed.stdout)
        self.assertIn("t05 not interested", completed.stdout)
