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
        self.assertIn("MATCHED A/B", card)
        self.assertIn("PROSE DECODE", card)
        self.assertIn("1.00×", card)
        self.assertIn("left 15/15", card)
        self.assertIn("BENCH  left git:", card)
        self.assertIn("clean", card)


if __name__ == "__main__":
    unittest.main()
