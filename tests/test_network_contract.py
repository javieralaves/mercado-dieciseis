"""The page, the contract and the public site tell a team the local-mode deal, the venue and the fee."""
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from bazaar.marketplace.network.service import Waitlist, page
from bazaar.marketplace.network.site import SKILL_DIR, build
from bazaar.marketplace.network.store import Store
from bazaar.marketplace.network.terms import CUTOFF, MADRID, VENUE, fee_bps_at, pricing_line


class FeeSchedule(unittest.TestCase):
    def test_a_paid_venue_would_charge_one_percent_before_the_cutoff_and_two_from_it(self):
        self.assertEqual(fee_bps_at(datetime(2026, 10, 4, 9, 59, tzinfo=MADRID)), 100)
        self.assertEqual(fee_bps_at(CUTOFF), 200)
        self.assertEqual(fee_bps_at(datetime(2026, 10, 4, 8, 0, tzinfo=timezone.utc)), 200)
        self.assertEqual(fee_bps_at(datetime(2026, 10, 4, 7, 59, tzinfo=timezone.utc)), 100)
        with self.assertRaises(ValueError):
            fee_bps_at(datetime(2026, 10, 4, 9, 0))

    def test_the_page_shows_the_live_venue_at_zero_percent(self):
        html = page({"ready": 0, "threshold": 5}, datetime(2026, 10, 3, 22, 0, tzinfo=MADRID))
        self.assertIn("0% fee, no per-card fee, on venue v16.", html)
        self.assertNotIn("1% founding", html)
        self.assertIn('href="/contract"', html)
        self.assertEqual(pricing_line(CUTOFF), pricing_line())


class Contract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "network.sqlite")
        self.api = Waitlist(self.store)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_contract_explains_local_mode_the_venue_and_the_skill(self):
        code, body = self.api.handle("GET", "/contract")
        self.assertEqual(code, 200)
        for line in (
            "local mode only",
            "your Bazaar key.",
            "Venue: `v16`",
            "mechanism: auto",
            "midpoint",
            "0% fee",
            "No per-card fee.",
            "never be your counterparty",
            "pseudonym",
            "python3 mercado16.py --post",
        ):
            self.assertIn(line, body)
        self.assertIn("&quot;venue&quot;: &quot;v16&quot;", body)
        self.assertNotIn("1% founding", body)
        self.assertNotIn("/v1/", body)
        self.assertNotIn("share_intent", body)


class PublicSite(unittest.TestCase):
    def test_the_site_serves_the_page_the_contract_and_the_exact_skill_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "site"
            files = {p.relative_to(out).as_posix() for p in build(out, "https://mercado16.example.app/")}
            self.assertEqual(files, {"index.html", "contract.html", "contract.md", "vercel.json",
                                     "skill/SKILL.md", "skill/mercado16.py", "skill/triangles.py", "skill/cycle_agent.py"})
            for name in ("SKILL.md", "mercado16.py", "triangles.py", "cycle_agent.py"):
                self.assertEqual((out / "skill" / name).read_bytes(), (SKILL_DIR / name).read_bytes())
            index = (out / "index.html").read_text(encoding="utf-8")
            self.assertIn(f"venue <code>{VENUE}</code>", index)
            self.assertIn("curl -fsSLO https://mercado16.example.app/skill/SKILL.md -O https://mercado16.example.app/skill/mercado16.py", index)
            self.assertIn(".cursor/skills/mercado16", index)
            self.assertIn(".claude/skills/mercado16", index)
            for absent in ("<form", "fetch(", "/v1/", "tk-", "X-Team-Key"):
                self.assertNotIn(absent, index)
            build(out, "https://mercado16.example.app")
            self.assertEqual(len(list(out.rglob("*.html"))), 2)


if __name__ == "__main__":
    unittest.main()
