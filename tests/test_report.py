import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import report


class ReportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = Path("results/reference/glm53-libert-nvfp4-tp2-low.json")
        cls.result = json.loads(cls.path.read_text())

    def test_verified_card_is_fixed_width_and_explicit(self):
        fingerprint = hashlib.sha256(self.path.read_bytes()).hexdigest()
        card = report.render(self.result, fingerprint)
        self.assertTrue(all(len(line) == report.WIDTH for line in card.splitlines()))
        self.assertIn("15/15 BASIC OUTPUT GATES PASSED", card)
        self.assertIn("s last", card)
        self.assertIn("PROSE", card)
        self.assertIn("tok/s", card)
        self.assertIn("git:", card)
        self.assertIn("clean", card)
        self.assertIn("CAPPED CONCURRENT GENERATION", card)
        self.assertIn(fingerprint[:16], card)

    def test_depth_label_does_not_round_down(self):
        self.assertEqual("512 TOKENS", report.depth_label(512))
        self.assertEqual("64K", report.depth_label(65_536))

    def test_failed_gate_marks_card_incomplete(self):
        result = json.loads(json.dumps(self.result))
        result["decode"]["prose"]["runs"][0]["finish_reason"] = "length"
        result["decode"]["prose"]["runs"][0]["completion_validation"] = {
            "valid": False,
            "error": "answer hit the token limit",
        }
        result["decode"]["prose"]["completion_gate"]["passed"] = 4
        card = report.render(result, "0" * 64)
        self.assertIn("14/15 BASIC OUTPUT GATES PASSED — DO NOT HEADLINE", card)
        self.assertIn("✗ 4/5", card)

    def test_dirty_card_includes_worktree_fingerprint(self):
        result = json.loads(json.dumps(self.result))
        result["protocol"]["repository_dirty"] = True
        result["protocol"]["repository_worktree_sha256"] = "a" * 64
        card = report.render(result, "0" * 64)
        self.assertIn("dirty", card)
        self.assertIn("worktree:aaaaaaaaaaaa", card)

    def test_save_report_writes_card_beside_receipt(self):
        with TemporaryDirectory() as directory:
            result_path = Path(directory) / "run.json"
            result_path.write_text(json.dumps(self.result))
            card_path = report.save_report(self.result, result_path)
            self.assertEqual(Path(directory) / "run.card.txt", card_path)
            self.assertIn("R I G M A R K", card_path.read_text())

    def test_published_cards_avoid_overclaiming_terms(self):
        forbidden = (
            "OUTPUTS COMPLETE",
            "STREAMS FINISHED",
            "cached replay",
            "├─ PROOF",
        )
        for path in Path("results/reference").glob("*.card.txt"):
            with self.subTest(path=path):
                card = path.read_text()
                for phrase in forbidden:
                    self.assertNotIn(phrase, card)


if __name__ == "__main__":
    unittest.main()
