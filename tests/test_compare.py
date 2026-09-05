import hashlib
import json
import unittest
from pathlib import Path

import compare


class CompareTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = Path("results/reference/glm53-libert-nvfp4-tp2-low.json")
        cls.result = json.loads(cls.path.read_text())

    def test_matched_card_is_fixed_width(self):
        fingerprint = hashlib.sha256(self.path.read_bytes()).hexdigest()
        card = compare.render_card(
            self.result, self.result, fingerprint, fingerprint
        )
        self.assertTrue(all(
            len(line) == compare.CARD_WIDTH for line in card.splitlines()
        ))
        self.assertIn("MATCHED REQUEST A/B", card)
        self.assertIn("PROSE DECODE", card)
        self.assertIn("PROSE LAST OUTPUT", card)
        self.assertIn("1.00×", card)
        self.assertIn("left 15/15", card)
        self.assertIn("CODE LAST OUTPUT, SEC", card)
        self.assertIn("BENCH  left git:", card)
        self.assertIn("clean", card)

    def test_depth_label_does_not_round_down(self):
        self.assertEqual("1,536 TOKENS", compare.depth_label(1_536))

    def test_seed_mismatch_is_rejected(self):
        other = json.loads(json.dumps(self.result))
        other["settings"]["seed"] += 1
        self.assertIn("settings.seed", compare.comparable(self.result, other))

    def test_benchmark_revision_mismatch_is_rejected(self):
        other = json.loads(json.dumps(self.result))
        other["protocol"]["repository_revision"] = "f" * 40
        self.assertIn(
            "protocol.repository_revision",
            compare.comparable(self.result, other),
        )

    def test_source_fingerprint_mismatch_is_rejected_when_present(self):
        left = json.loads(json.dumps(self.result))
        right = json.loads(json.dumps(self.result))
        left["protocol"]["repository_source_sha256"] = "a" * 64
        right["protocol"]["repository_source_sha256"] = "b" * 64
        self.assertIn(
            "protocol.repository_source_sha256",
            compare.comparable(left, right),
        )

    def test_foreign_result_shape_reports_mismatches(self):
        mismatches = compare.comparable({}, {})
        self.assertIn("protocol.version", mismatches)

    def test_identical_clean_receipts_are_comparable(self):
        result = json.loads(json.dumps(self.result))
        self.assertEqual([], compare.comparable(result, result))

    def test_dirty_receipts_require_matching_worktree_hash(self):
        left = json.loads(json.dumps(self.result))
        right = json.loads(json.dumps(self.result))
        left["protocol"]["repository_dirty"] = True
        right["protocol"]["repository_dirty"] = True
        left["protocol"]["repository_worktree_sha256"] = "a" * 64
        self.assertIn(
            "protocol.repository_worktree_sha256",
            compare.comparable(left, right),
        )

    def test_card_rejects_forged_summary(self):
        result = json.loads(json.dumps(self.result))
        result["decode"]["prose"]["decode_tokens_per_second"]["median"] *= 2
        with self.assertRaisesRegex(ValueError, "invalid receipt"):
            compare.render_card(result, result, "0" * 64, "0" * 64)


if __name__ == "__main__":
    unittest.main()
