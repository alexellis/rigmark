import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import bench


class BenchTest(unittest.TestCase):
    def test_default_decode_cap_reaches_runner_and_receipt(self):
        argv = ["bench.py", "--base-url", "http://localhost:1", "--model", "test",
                "--label", "test", "--comparison-id", "test",
                "--metadata", "unused.json", "--output", "unused.json"]
        with patch("sys.argv", argv), \
             patch("bench.load_metadata", return_value={"context_limit": 131072}), \
             patch("bench.run_decode", return_value={}) as decode, \
             patch("bench.run_prefill", return_value={}), \
             patch("bench.run_concurrency", return_value={}), \
             patch("bench.write_result") as write, \
             patch("report.save_report", return_value=Path("unused.card.txt")), \
             patch("report.print_report"), patch("builtins.print"):
            bench.main()
        self.assertEqual(8192, decode.call_args.args[4])
        result = write.call_args.args[0]
        self.assertEqual(8192, result["settings"]["decode_tokens"])
        self.assertEqual(5, result["settings"]["runs"])
        self.assertEqual(256, result["settings"]["concurrency_tokens"])
        self.assertEqual("1.3.0", result["protocol"]["version"])

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

    def test_protocol_bump_preserves_workload_nonce(self):
        self.assertEqual("d41fd2e892d2aa50a177f821a15b6709",
                         bench.nonce("sweep-1", "decode", "code", 1))

    def test_stream_retains_and_validates_cached_token_usage(self):
        def response(cached):
            events = [
                {"choices": [{"delta": {"content": "a"}}]},
                {"choices": [{"delta": {"content": "b"}, "finish_reason": "stop"}],
                 "usage": {"prompt_tokens": 10, "completion_tokens": 2,
                           "prompt_tokens_details": {"cached_tokens": cached}}},
            ]
            return io.BytesIO(("".join("data: " + json.dumps(e) + "\n\n" for e in events)
                               + "data: [DONE]\n\n").encode())
        client = bench.Client("http://example.test", "", 1)
        for cached in (0, 7, None):
            with patch("bench.urllib.request.urlopen", return_value=response(cached)):
                self.assertEqual(cached, client.stream("/v1/completions", {})["cached_prompt_tokens"])
        for cached in (-1, 11, True, "0"):
            with patch("bench.urllib.request.urlopen", return_value=response(cached)):
                with self.assertRaisesRegex(RuntimeError, "invalid cached"):
                    client.stream("/v1/completions", {})

    def test_prefill_salts_change_across_pairs_and_repeated_sweeps(self):
        class CacheClient:
            def __init__(self):
                self.requests = []
                self.seen = set()

            def json(self, path, payload):
                return {"tokens": [1, 2]}

            def stream(self, path, payload):
                self.requests.append(payload)
                salt = payload["cache_salt"]
                cached = 16 if salt in self.seen else 0
                self.seen.add(salt)
                return {"prompt_tokens": len(payload["prompt"]), "ttft_seconds": 0.5,
                        "cached_prompt_tokens": cached}
        client = CacheClient()
        with patch("builtins.print"):
            for _ in range(2):
                bench.run_prefill(client, "model", {"prefill_unit": "unit"}, [32], 2, "same-id")
        salts = [r["cache_salt"] for r in client.requests]
        self.assertEqual(4, len(set(salts)))
        for i in range(0, 8, 2):
            self.assertEqual(salts[i], salts[i + 1])
        self.assertEqual(client.requests[0]["prompt"], client.requests[4]["prompt"])

    def test_prefill_refuses_known_cold_cache_hit(self):
        class CacheClient:
            def json(self, path, payload):
                return {"tokens": [1]}

            def stream(self, path, payload):
                return {"prompt_tokens": 32, "ttft_seconds": 0.5, "cached_prompt_tokens": 16}
        with patch("builtins.print"), self.assertRaisesRegex(RuntimeError, "reported 16 cached"):
            bench.run_prefill(CacheClient(), "model", {"prefill_unit": "unit"}, [32], 1, "id")

    def test_pooled_decode_supplements_median_with_matching_windows(self):
        class Client:
            def __init__(self):
                self.calls = 0

            def stream(self, path, payload):
                self.calls += 1
                tokens, seconds = (11, 1) if self.calls == 1 else (201, 10)
                return {"completion_tokens": tokens, "decode_seconds": seconds,
                        "decode_tokens_per_second": (tokens - 1) / seconds,
                        "ttft_seconds": 0.1, "time_to_last_output_seconds": seconds + 0.1,
                        "wall_seconds": seconds + 0.1, "finish_reason": "stop", "output": "answer"}
        with patch("builtins.print"):
            result = bench.run_decode(Client(), "model", {"system": "sys", "workloads": {"prose": "p"}},
                                      2, 4096, 1, {}, "id")["prose"]
        self.assertEqual(15, result["decode_tokens_per_second"]["median"])
        self.assertEqual(round(210 / 11, 3), result["pooled_decode_tokens_per_second"])

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

    def test_first_party_serving_records_are_valid(self):
        root = Path(__file__).resolve().parents[1]
        records = sorted((root / "examples" / "serving-records").glob("*.json"))
        expected = {
            "alexellis-ds4f-0731-nvfp4-2x-dgx-spark.json",
            "alexellis-glm53-flash-nvfp4-2x-dgx-spark.json",
            "alexellis-qwen38-27b-fp8-rtxpro6000.json",
        }
        self.assertTrue(expected.issubset({record.name for record in records}))
        for record in records:
            with self.subTest(record=record.name):
                metadata = bench.load_metadata(record)
                self.assertEqual(
                    "first-party serving input snapshot",
                    metadata["record_type"],
                )


if __name__ == "__main__":
    unittest.main()
