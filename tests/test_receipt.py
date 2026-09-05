import copy
import json
import unittest
from pathlib import Path

import receipt


class ReceiptTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = json.loads(Path(
            "results/reference/glm53-libert-nvfp4-tp2-low.json"
        ).read_text())

    def errors_after(self, mutate):
        value = copy.deepcopy(self.result)
        mutate(value)
        return receipt.validate_result(value)

    def test_reference_receipt_is_internally_consistent(self):
        self.assertEqual([], receipt.validate_result(self.result))

    def test_all_published_receipts_are_internally_consistent(self):
        for path in Path("results/reference").glob("*.json"):
            with self.subTest(path=path):
                value = json.loads(path.read_text())
                self.assertEqual([], receipt.validate_result(value))

    def test_missing_raw_run_is_rejected(self):
        errors = self.errors_after(lambda value: value["decode"]["prose"]["runs"].pop())
        self.assertTrue(any("decode.prose.runs has" in error for error in errors))

    def test_forged_summary_is_rejected(self):
        def mutate(value):
            value["decode"]["prose"]["decode_tokens_per_second"]["median"] *= 2
        errors = self.errors_after(mutate)
        self.assertTrue(any("does not match raw runs" in error for error in errors))

    def test_forged_row_rate_is_rejected_even_with_matching_summary(self):
        def mutate(value):
            rows = value["decode"]["prose"]["runs"]
            for row in rows:
                row["decode_tokens_per_second"] = 999_999
            summary = value["decode"]["prose"]["decode_tokens_per_second"]
            for field in ("median", "minimum", "maximum", "p90"):
                summary[field] = 999_999
        errors = self.errors_after(mutate)
        self.assertTrue(any("does not match tokens/time" in error for error in errors))

    def test_incomplete_error_receipt_is_rejected(self):
        errors = self.errors_after(lambda value: value.__setitem__("error", "boom"))
        self.assertIn("receipt records an incomplete run error", errors)

    def test_protocol_11_requires_new_timing_evidence(self):
        def mutate(value):
            value["protocol"]["version"] = "1.1.0"
            value["protocol"]["repository_source_sha256"] = "a" * 64
        errors = self.errors_after(mutate)
        self.assertTrue(any("measured_sse_events is required" in error for error in errors))
        self.assertTrue(any("requested_prompt_tokens is required" in error for error in errors))

    def test_forged_gate_is_rejected(self):
        def mutate(value):
            value["decode"]["code"]["completion_gate"]["passed"] = 0
        errors = self.errors_after(mutate)
        self.assertTrue(any("completion_gate" in error for error in errors))

    def test_wrong_prefill_depth_is_rejected(self):
        def mutate(value):
            value["prefill"]["8192"]["cold"]["runs"][0]["prompt_tokens"] = 1_234
        errors = self.errors_after(mutate)
        self.assertTrue(any("prompt_tokens does not match depth" in error for error in errors))

    def test_zero_prefill_ttft_cannot_hide_a_forged_rate(self):
        def mutate(value):
            owner = value["prefill"]["65536"]["cold"]
            for row in owner["runs"]:
                row["ttft_seconds"] = 0
                row["effective_prefill_tokens_per_second"] = 999_999
            for field in (
                "ttft_seconds",
                "effective_prefill_tokens_per_second",
            ):
                owner[field] = receipt.summary([
                    row[field] for row in owner["runs"]
                ])
        errors = self.errors_after(mutate)
        self.assertTrue(any("ttft_seconds must be positive" in error for error in errors))

    def test_wrong_concurrency_width_is_rejected(self):
        def mutate(value):
            value["concurrency"]["4"]["rounds"][0]["streams"].pop()
        errors = self.errors_after(mutate)
        self.assertTrue(any("streams has the wrong length" in error for error in errors))

    def test_zero_concurrency_wall_cannot_hide_a_forged_rate(self):
        def mutate(value):
            owner = value["concurrency"]["4"]
            for row in owner["rounds"]:
                row["wall_seconds"] = 0
                row["aggregate_end_to_end_tokens_per_second"] = 999_999
            owner["aggregate_end_to_end_tokens_per_second"] = receipt.summary([
                row["aggregate_end_to_end_tokens_per_second"]
                for row in owner["rounds"]
            ])
        errors = self.errors_after(mutate)
        self.assertTrue(any("wall_seconds must be positive" in error for error in errors))

    def test_concurrency_round_cannot_be_shorter_than_a_stream(self):
        def mutate(value):
            owner = value["concurrency"]["4"]
            for row in owner["rounds"]:
                row["wall_seconds"] = 0.001
                row["aggregate_end_to_end_tokens_per_second"] = round(
                    row["completion_tokens"] / row["wall_seconds"], 3
                )
            owner["aggregate_end_to_end_tokens_per_second"] = receipt.summary([
                row["aggregate_end_to_end_tokens_per_second"]
                for row in owner["rounds"]
            ])
        errors = self.errors_after(mutate)
        self.assertTrue(any("shorter than a member stream" in error for error in errors))

    def test_malformed_usage_is_rejected(self):
        def mutate(value):
            value["decode"]["code"]["runs"][0]["prompt_tokens"] = True
        errors = self.errors_after(mutate)
        self.assertTrue(any("prompt_tokens" in error for error in errors))

    def test_string_timing_is_rejected(self):
        def mutate(value):
            value["decode"]["code"]["runs"][0]["ttft_seconds"] = "0.5"
        errors = self.errors_after(mutate)
        self.assertTrue(any("ttft_seconds" in error for error in errors))

    def test_altered_output_is_rejected(self):
        def mutate(value):
            value["decode"]["code"]["runs"][0]["output"] += "tampered"
        errors = self.errors_after(mutate)
        self.assertTrue(any("output_" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
