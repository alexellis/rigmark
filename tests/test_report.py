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
        self.assertIn("OUTPUT  //  15/15 COMPLETE", card)
        self.assertIn("PROSE", card)
        self.assertIn("tok/s", card)
        self.assertIn("SHORT CODE LOAD  //  END-TO-END", card)
        self.assertIn(fingerprint[:16], card)

    def test_failed_gate_marks_card_incomplete(self):
        result = json.loads(json.dumps(self.result))
        result["decode"]["prose"]["completion_gate"]["passed"] = 4
        card = report.render(result, "0" * 64)
        self.assertIn("OUTPUT  //  14/15 COMPLETE — DO NOT HEADLINE", card)
        self.assertIn("FAIL 4/5", card)

    def test_save_report_writes_card_beside_receipt(self):
        with TemporaryDirectory() as directory:
            result_path = Path(directory) / "run.json"
            result_path.write_text(json.dumps(self.result))
            card_path = report.save_report(self.result, result_path)
            self.assertEqual(Path(directory) / "run.card.txt", card_path)
            self.assertIn("R I G M A R K", card_path.read_text())


if __name__ == "__main__":
    unittest.main()
