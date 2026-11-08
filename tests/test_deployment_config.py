"""Static deployment configuration checks (stdlib only)."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DeploymentConfigTest(unittest.TestCase):
    def test_vercel_config_has_entrypoint_and_excludes_non_runtime_files(self):
        config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
        self.assertIn("app.py", config["functions"])
        excludes = config["functions"]["app.py"]["excludeFiles"]
        self.assertIn("tests/**", excludes)
        self.assertIn("migrations/**", excludes)
        self.assertIn("scripts/**", excludes)

    def test_vercel_edge_headers_cover_static_and_private_api(self):
        config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
        rules = {rule["source"]: {h["key"].lower(): h["value"] for h in rule["headers"]}
                 for rule in config["headers"]}
        static_headers = rules["/(.*)"]
        self.assertEqual(static_headers["x-content-type-options"], "nosniff")
        self.assertEqual(static_headers["x-frame-options"], "DENY")
        self.assertIn("frame-ancestors 'none'", static_headers["content-security-policy"])
        api_headers = rules["/api/(.*)"]
        self.assertEqual(api_headers["cache-control"], "private, no-store")
        self.assertEqual(api_headers["vary"], "Cookie")


if __name__ == "__main__":
    unittest.main()
