import unittest
from pathlib import Path

import audit_code


class AuditCodeTest(unittest.TestCase):
    def test_extracts_two_go_blocks(self):
        implementation, tests = audit_code.code_blocks(
            "```go\npackage ratelimit\n```\n```go\npackage ratelimit\n```"
        )
        self.assertEqual("package ratelimit\n", implementation)
        self.assertEqual("package ratelimit\n", tests)

    def test_rejects_missing_test_block(self):
        with self.assertRaisesRegex(ValueError, "expected two"):
            audit_code.code_blocks("```go\npackage ratelimit\n```")

    def test_docker_is_locked_down(self):
        command = audit_code.docker_command(
            Path("/tmp/result"), "golang:1.25", "rigmark-test"
        )
        self.assertIn("none", command)
        self.assertIn("--read-only", command)
        self.assertIn("no-new-privileges", command)
        self.assertIn("ALL", command)
        self.assertIn("/tmp/result:/src:ro", command)
        self.assertIn("rigmark-test", command)
        self.assertIn("-json", command)


if __name__ == "__main__":
    unittest.main()
