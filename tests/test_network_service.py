"""The public waitlist records a team id and shows how many teams are ready. It does not open a venue."""
import json
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from bazaar.marketplace.network.service import SECRET_FIELDS, Waitlist, make_handler, page
from bazaar.marketplace.network.store import JOINED, THRESHOLD, Store
from network import status_text

ROOT = Path(__file__).resolve().parents[1]


def waitlist(directory: Path) -> tuple[Store, Waitlist]:
    store = Store(directory / "network.sqlite")
    return store, Waitlist(store)


class WaitlistJoin(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store, self.api = waitlist(Path(self.tmp.name))

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_join_returns_a_stable_id_and_does_not_count_as_ready(self):
        first, second = self.api.handle("POST", "/v1/waitlist", {"team_id": "t07"})
        again, same = self.api.handle("POST", "/v1/waitlist", {"team_id": "T07"})
        other, other_body = self.api.handle("POST", "/v1/waitlist", {"team_id": "t03"})
        self.assertEqual(first, 200)
        self.assertEqual(again, 200)
        self.assertEqual(second["participant_id"], same["participant_id"])
        self.assertNotEqual(second["participant_id"], other_body["participant_id"])
        self.assertEqual(second["status"], JOINED)
        self.assertEqual(second["ready_teams"], 0)
        self.assertEqual(second["threshold"], THRESHOLD)
        status_code, status = self.api.handle("GET", "/v1/status")
        self.assertEqual(status_code, 200)
        self.assertEqual(status, {"state": "waitlist", "ready": 0, "threshold": 5})
        self.assertNotIn("t07", json.dumps(status))
        self.assertNotIn("t03", json.dumps(other_body))
        self.assertEqual(other, 200)

    def test_joining_again_does_not_count_as_ready(self):
        self.api.handle("POST", "/v1/waitlist", {"team_id": "t07"})
        _, status = self.api.handle("GET", "/v1/status")
        self.assertEqual(status["ready"], 0)
        _, joined_again = self.api.handle("POST", "/v1/waitlist", {"team_id": "t07"})
        self.assertEqual(joined_again["status"], JOINED)
        self.assertEqual(joined_again["ready_teams"], 0)

    def test_page_shows_the_counter_and_that_the_waitlist_does_not_gate_trading(self):
        code, html = self.api.handle("GET", "/")
        self.assertEqual(code, 200)
        self.assertIn("0 / 5 teams ready", html)
        self.assertIn("Connect my team", html)
        self.assertIn("live on venue v16", html)
        self.assertIn("this waitlist is optional", html)
        self.assertNotIn("Bazaar key", html.replace("We never ask for your Bazaar key.", ""))
        self.store.join("t04")
        _, html = self.api.handle("GET", "/")
        self.assertNotIn("t04", html)
        self.assertEqual(page({"ready": 3, "threshold": 5}).count("3 / 5 teams ready"), 1)

    def test_credentials_and_our_own_team_are_refused(self):
        for field in SECRET_FIELDS:
            code, body = self.api.handle("POST", "/v1/waitlist", {"team_id": "t07", field: "secret-value"})
            self.assertEqual(code, 400, field)
            self.assertNotIn("secret-value", json.dumps(body))
        self.assertEqual(self.api.handle("POST", "/v1/waitlist", {"team_id": "t16"})[0], 400)
        self.assertEqual(self.api.handle("POST", "/v1/waitlist", {"team_id": "not-a-team"})[0], 400)
        self.assertEqual(self.api.handle("POST", "/v1/waitlist", {})[0], 400)
        self.assertEqual(self.store.registration_count(), 0)

    def test_there_is_no_list_of_participants(self):
        self.api.handle("POST", "/v1/waitlist", {"team_id": "t07"})
        for path in ("/participants", "/v1/participants", "/orderbook", "/intents", "/v1/waitlist"):
            code, body = self.api.handle("GET", path)
            self.assertEqual(code, 404, path)
            self.assertNotIn("t07", json.dumps(body))

    def test_private_file_is_not_world_readable(self):
        self.store.join("t07")
        mode = self.store.path.stat().st_mode
        self.assertEqual(mode & 0o077, 0)
        self.assertEqual(self.store.path.parent.stat().st_mode & 0o077, 0)

    def test_an_existing_parent_directory_keeps_its_mode(self):
        shared = Path(self.tmp.name) / "shared"
        shared.mkdir(mode=0o755)
        store = Store(shared / "network.sqlite")
        self.addCleanup(store.close)
        store.join("t08")
        self.assertEqual(shared.stat().st_mode & 0o777, 0o755)
        self.assertEqual(store.path.stat().st_mode & 0o077, 0)


class WaitlistCommands(unittest.TestCase):
    def test_status_command_names_no_team(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "network.sqlite"
            store = Store(db)
            store.join("t09")
            text = status_text(store)
            store.close()
            self.assertIn("WAITLIST", text)
            self.assertIn("0 / 5 ready", text)
            self.assertIn("1 joined", text)
            self.assertIn("venue v16 live", text)
            self.assertNotIn("t09", text)
            completed = subprocess.run(
                [sys.executable, "network.py", "--status", "--db", str(db)],
                cwd=ROOT, capture_output=True, text=True, check=True,
            )
            self.assertEqual(completed.stdout.strip(), text)
            self.assertNotIn("t09", completed.stdout)

    def test_gitignore_covers_the_private_directory(self):
        ignored = (ROOT / ".gitignore").read_text()
        self.assertIn("data/private_network/", ignored)


class WaitlistHttp(unittest.TestCase):
    def test_page_and_join_over_http(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store, api = waitlist(Path(tmp.name))
        self.addCleanup(store.close)
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(api))
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        base = f"http://127.0.0.1:{port}"
        with urllib.request.urlopen(base + "/") as response:
            html = response.read().decode()
        self.assertIn("Connect my team", html)
        self.assertIn("0 / 5 teams ready", html)
        request = urllib.request.Request(
            base + "/v1/waitlist",
            data=json.dumps({"team_id": "t12"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request) as response:
            body = json.loads(response.read().decode())
        self.assertTrue(body["participant_id"].startswith("p_"))
        self.assertEqual(body["ready_teams"], 0)
        with urllib.request.urlopen(base + "/v1/status") as response:
            self.assertEqual(json.loads(response.read().decode())["ready"], 0)


if __name__ == "__main__":
    unittest.main()
