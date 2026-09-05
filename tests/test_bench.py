import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import bench


class BenchTest(unittest.TestCase):
    def test_normalise_base_url(self):
        self.assertEqual("http://host:8000", bench.normalise_base_url("http://host:8000/v1/"))
        self.assertEqual("http://host:8000", bench.normalise_base_url("http://host:8000"))

    def test_percentile(self):
        self.assertEqual(5, bench.percentile([1, 2, 3, 4, 5], 0.9))

    def test_decode_rate_rejects_single_buffered_event(self):
        with self.assertRaisesRegex(RuntimeError, "one measurable SSE event"):
            bench.chunk_timed_decode_rate(100, 1.0, 1.0, 1)

    def test_decode_rate_uses_measurable_window(self):
        window, rate = bench.chunk_timed_decode_rate(101, 1.0, 3.0, 100)
        self.assertEqual(2.0, window)
        self.assertEqual(50.0, rate)

    def test_comma_ints(self):
        self.assertEqual([1, 2, 4], bench.comma_ints("1,2,4"))

    def test_safe_label(self):
        self.assertEqual("Qwen-27B-TP1", bench.safe_label("Qwen 27B / TP1"))

    def test_nonce_is_deterministic(self):
        self.assertEqual(
            bench.nonce("sweep-1", "decode", "code", 1),
            bench.nonce("sweep-1", "decode", "code", 1),
        )
        self.assertNotEqual(
            bench.nonce("sweep-1", "decode", "code", 1),
            bench.nonce("sweep-2", "decode", "code", 1),
        )

    def test_archival_identity_reads_exported_commit(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / ".git_archival.txt"
            path.write_text("node: " + "a" * 40 + "\nref-names: HEAD\n")
            identity = bench.archival_identity(path)
            self.assertEqual("a" * 40, identity["repository_revision"])
            self.assertIsNone(identity["repository_dirty"])
            self.assertEqual("git-archive", identity["repository_source"])
            self.assertRegex(identity["repository_source_sha256"], r"^[0-9a-f]{64}$")

    def test_archival_identity_rejects_unexpanded_placeholder(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / ".git_archival.txt"
            path.write_text("node: $Format:%H$\n")
            self.assertIsNone(bench.archival_identity(path))

    def test_rejects_credentials_in_url(self):
        with self.assertRaises(ValueError):
            bench.validate_base_url("https://user:password@example.com")

    def test_extra_body_cannot_change_sampling(self):
        with self.assertRaises(ValueError):
            bench.build_chat_payload("model", "system", "prompt", 10, 1, {
                "temperature": 0.5,
            })
        for field in ("n", "stop", "max_completion_tokens", "response_format"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                bench.build_chat_payload(
                    "model", "system", "prompt", 10, 1, {field: 2}
                )

    def test_structured_output_validation(self):
        output = [
            {"index": index, "square": index * index}
            for index in range(1, 51)
        ]
        self.assertTrue(
            bench.validate_structured_output(json.dumps(output))["valid"]
        )
        self.assertFalse(bench.validate_structured_output("[1, 2]")["valid"])
        output[0]["index"] = 1.0
        self.assertFalse(
            bench.validate_structured_output(json.dumps(output))["valid"]
        )

    def test_visible_output_validation(self):
        self.assertTrue(bench.validate_visible_output({
            "output": "A complete answer.",
            "finish_reason": "stop",
        })["valid"])
        self.assertFalse(bench.validate_visible_output({
            "output": "A truncated answer",
            "finish_reason": "length",
        })["valid"])
        self.assertFalse(bench.validate_visible_output({
            "output": "",
            "finish_reason": "length",
        })["valid"])
        self.assertFalse(bench.validate_visible_output({
            "output": "An answer with no normal end.",
            "finish_reason": None,
        })["valid"])
        self.assertFalse(bench.validate_visible_output({
            "output": "An answer blocked by policy.",
            "finish_reason": "content_filter",
        })["valid"])
        self.assertFalse(bench.validate_visible_output({
            "output": "An answer with a broken stream.",
            "finish_reason": "stop",
            "stream_done_marker": False,
        })["valid"])

    def test_structured_output_requires_normal_stream_end(self):
        output = json.dumps([
            {"index": index, "square": index * index}
            for index in range(1, 51)
        ])
        self.assertFalse(bench.validate_structured_row({
            "output": output,
            "finish_reason": "length",
        })["valid"])

    def test_prefill_depth_must_fit_declared_context(self):
        bench.validate_prefill_depths([512, 1_016], 1_024)
        with self.assertRaisesRegex(ValueError, "exceeds"):
            bench.validate_prefill_depths([1_017], 1_024)

    def test_prefill_depth_must_hold_unique_prefix(self):
        class TokenClient:
            def json(self, _path, payload):
                if str(payload["prompt"]).startswith("Unique"):
                    return {"tokens": [1, 2, 3, 4]}
                return {"tokens": [5]}

        with self.assertRaisesRegex(RuntimeError, "too small"):
            bench.exact_token_ids(TokenClient(), "model", 3, "unit", "nonce")

    def test_prefill_rejects_server_token_count_mismatch(self):
        class MismatchedClient:
            def stream(self, _path, _payload):
                return {
                    "prompt_tokens": 1_234,
                    "ttft_seconds": 0.05,
                }

        with self.assertRaisesRegex(
            RuntimeError,
            "requested 512, server reported 1234",
        ):
            bench.prefill_once(MismatchedClient(), "model", [1] * 512)

    def test_prefill_records_verified_requested_depth(self):
        class MatchingClient:
            def stream(self, _path, _payload):
                return {
                    "prompt_tokens": 512,
                    "ttft_seconds": 0.25,
                }

        row = bench.prefill_once(MatchingClient(), "model", [1] * 512)
        self.assertEqual(512, row["requested_prompt_tokens"])
        self.assertEqual(2_048, row["effective_prefill_tokens_per_second"])

    def test_metadata_rejects_placeholders(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "metadata.json"
            path.write_text('{"hardware": "CHANGE ME"}')
            with self.assertRaises(ValueError):
                bench.load_metadata(path)

    def test_metadata_rejects_zero_context(self):
        metadata = {
            "hardware": "GPU",
            "topology": "TP1",
            "model": "example/model",
            "model_revision": "abc123",
            "quantisation": "FP8",
            "kv_cache_dtype": "FP8",
            "serving_engine": "engine 1",
            "context_limit": 0,
            "competing_traffic": "none",
        }
        with TemporaryDirectory() as directory:
            path = Path(directory) / "metadata.json"
            path.write_text(json.dumps(metadata))
            with self.assertRaises(ValueError):
                bench.load_metadata(path)


if __name__ == "__main__":
    unittest.main()
