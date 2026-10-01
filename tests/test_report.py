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
        self.assertIn("Last (s)", card)
        self.assertIn("Range tok/s", card)
        self.assertIn("31.6–47.7", card)
        self.assertIn("PROSE", card)
        self.assertIn("tok/s", card)
        self.assertIn("git:", card)
        self.assertIn("clean", card)
        self.assertIn("CAPPED CONCURRENT GENERATION", card)
        self.assertIn(fingerprint[:16], card)

    def test_card_preserves_headers_and_all_prefill_depths(self):
        card = report.render(self.result, "0" * 64)
        self.assertIn("BENCHMARKS LOCAL AI HOW CODING AGENTS ACTUALLY USE IT", card)
        for label in ("8K", "32K", "64K", "Replay TTFT (s)"):
            self.assertIn(label, card)
        self.assertLess(card.index("SINGLE STREAM"), card.index("Hardware:"))
        self.assertLess(card.index("Hardware:"), card.index("SUITE:"))

    def test_skipped_phases_and_custom_flags_stay_visible(self):
        result = json.loads(json.dumps(self.result))
        result["settings"]["prefill_depths"] = []
        result["settings"]["concurrency"] = []
        result["settings"]["seed"] = 42
        result.pop("prefill")
        result.pop("concurrency")
        card = report.render(result, "0" * 64)
        self.assertIn("15/15 BASIC OUTPUT GATES PASSED", card)
        for label in ("INCOMPLETE SUITE", "NOT MEASURED", "CUSTOM SETTINGS",
                      "--skip-prefill", "--skip-concurrency", "--seed=42"):
            self.assertIn(label, card)

    def test_hardware_and_request_body_wrap_without_losing_values(self):
        result = json.loads(json.dumps(self.result))
        hardware = "Four mixed Spark appliances " + "full details " * 20 + "END_HARDWARE"
        result["run"]["appliance"]["hardware"] = hardware
        result["settings"]["extra_body"]["vendor_option"] = "z" * 160 + "END_OPTION"
        card = report.render(result, "0" * 64)
        self.assertTrue(all(len(row) == report.WIDTH for row in card.splitlines()))
        self.assertIn("END_HARDWARE", card)
        self.assertIn("END_OPTION", card)
        self.assertIn("vendor_option", card)

    def test_cold_claim_requires_reported_zero_hits(self):
        result = json.loads(json.dumps(self.result))
        self.assertIn("Cold cache UNVERIFIED", report.render(result, "0" * 64))
        for value in result["prefill"].values():
            for row in value["cold"]["runs"]:
                row["cached_prompt_tokens"] = 0
        card = report.render(result, "0" * 64)
        self.assertIn("Cold tok/s", card)
        self.assertNotIn("UNVERIFIED", card)

    def test_depth_label_does_not_round_down(self):
        self.assertEqual("512 TOKENS", report.depth_label(512))
        self.assertEqual("64K", report.depth_label(65_536))

    def test_default_cap_label_respects_receipt_protocol(self):
        for version in ("1.0.0", "1.1.0", "1.2.0", "1.3.0"):
            for cap in (4096, 8192):
                with self.subTest(version=version, cap=cap):
                    settings = dict(report.SUITE_DEFAULTS, decode_tokens=cap)
                    card = "\n".join(report.settings_lines(settings, version))
                    expected = 8192 if version == "1.3.0" else 4096
                    if cap == expected:
                        self.assertIn("DEFAULT SETTINGS", card)
                        self.assertNotIn("Changed:", card)
                    else:
                        self.assertIn("CUSTOM SETTINGS", card)
                        self.assertIn(f"--decode-tokens={cap}", card)

    def test_reasoning_effort_supports_both_request_dialects(self):
        self.assertEqual(
            "low",
            report.reasoning_effort({"extra_body": {"reasoning_effort": "low"}}),
        )
        self.assertEqual(
            "high",
            report.reasoning_effort(
                {
                    "extra_body": {
                        "chat_template_kwargs": {"reasoning_effort": "high"}
                    }
                }
            ),
        )
        self.assertEqual("unspecified", report.reasoning_effort({}))

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
