import unittest
from unittest.mock import patch

import release_check


class ReleaseCheckTest(unittest.TestCase):
    def test_newest_published_includes_prerelease(self):
        releases = [
            {"tag_name": "v0.0.3", "published_at": "2026-10-01T13:45:23Z",
             "draft": False, "prerelease": False, "html_url": "https://example.test/3"},
            {"tag_name": "v0.0.4", "published_at": "2026-10-06T09:05:19Z",
             "draft": False, "prerelease": True, "html_url": "https://example.test/4"},
        ]
        with patch("release_check.github_json", side_effect=[
            releases, {"status": "behind", "ahead_by": 0, "behind_by": 7},
        ]) as fetch:
            result = release_check.check_release("a" * 40, False)
        self.assertEqual("v0.0.4", result["tag"])
        self.assertEqual("behind", result["status"])
        self.assertTrue(result["prerelease"])
        self.assertIn("/compare/v0.0.4...", fetch.call_args.args[0])
        self.assertIn("Update before benchmarking", release_check.format_check(result))

    def test_network_failure_is_unverified(self):
        with patch("release_check.github_json", side_effect=OSError("offline")):
            result = release_check.check_release("a" * 40, False)
        self.assertEqual("unavailable", result["status"])
        self.assertNotIn("offline", str(result))


if __name__ == "__main__":
    unittest.main()
