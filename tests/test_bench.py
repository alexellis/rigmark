import json
import unittest

import bench


class BenchTest(unittest.TestCase):
    def test_normalise_base_url(self):
        self.assertEqual("http://host:8000", bench.normalise_base_url("http://host:8000/v1/"))
        self.assertEqual("http://host:8000", bench.normalise_base_url("http://host:8000"))

    def test_percentile(self):
        self.assertEqual(5, bench.percentile([1, 2, 3, 4, 5], 0.9))

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

    def test_rejects_credentials_in_url(self):
        with self.assertRaises(ValueError):
            bench.validate_base_url("https://user:password@example.com")

    def test_extra_body_cannot_change_sampling(self):
        with self.assertRaises(ValueError):
            bench.build_chat_payload("model", "system", "prompt", 10, 1, {
                "temperature": 0.5,
            })

    def test_structured_output_validation(self):
        output = [
            {"index": index, "square": index * index}
            for index in range(1, 51)
        ]
        self.assertTrue(
            bench.validate_structured_output(json.dumps(output))["valid"]
        )
        self.assertFalse(bench.validate_structured_output("[1, 2]")["valid"])

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


if __name__ == "__main__":
    unittest.main()
