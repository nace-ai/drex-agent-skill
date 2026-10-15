"""Offline tests for evals/drexify/recall.py. No network. The repo under test is local."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECALL = ROOT / "evals" / "drexify" / "recall.py"

SOURCE = (
    "def label_contract(text):\n"
    "    return client.chat.completions.create(model='m')\n"
    "\n"
    "def load_rows(text):\n"
    "    return text\n"
)


class RecallEvalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="recall eval ")
        self.root = Path(self.tmp.name)
        self.repo = self.root / "src"
        self.repo.mkdir()
        (self.repo / "decide.py").write_text(SOURCE)
        self.git(self.repo, "init")
        self.git(self.repo, "config", "uploadpack.allowReachableSHA1InWant", "true")
        self.git(self.repo, "add", "decide.py")
        env = os.environ.copy()
        env.update({
            "GIT_AUTHOR_NAME": "recall test",
            "GIT_AUTHOR_EMAIL": "recall@example.com",
            "GIT_COMMITTER_NAME": "recall test",
            "GIT_COMMITTER_EMAIL": "recall@example.com",
        })
        self.git(self.repo, "commit", "-m", "init", env=env)
        head = self.git(self.repo, "rev-parse", "HEAD").stdout.strip()
        self.known = self.root / "known.json"
        self.known.write_text(json.dumps({
            "repos": [{
                "name": "toy",
                "url": str(self.repo),
                "commit": head,
                "sites": [
                    {"path": "decide.py", "line": 1, "function": "label_contract"},
                    {"path": "decide.py", "line": 4, "function": "load_rows"},
                ],
            }]
        }))
        self.cache = self.root / "cache"

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, repo, *args, env=None):
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, env=env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def run_recall(self, *extra):
        return subprocess.run(
            [sys.executable, str(RECALL), "--known", str(self.known), "--cache", str(self.cache), *extra],
            capture_output=True, text=True,
        )

    def test_baseline_reports_lost_sites_and_candidate_changes(self):
        before = self.run_recall("--json")
        self.assertEqual(before.returncode, 0, before.stderr)
        baseline = self.root / "before.json"
        baseline.write_text(before.stdout)
        same = self.run_recall("--baseline", str(baseline))
        self.assertEqual(same.returncode, 0, same.stderr)
        self.assertIn("recall 1 -> 1 of 2", same.stdout)
        self.assertNotIn("lost", same.stdout)

        report = json.loads(before.stdout)
        report["repos"][0]["missing"] = []
        report["repos"][0]["candidate_functions"] += 3
        report["total"]["found"] = 2
        baseline.write_text(json.dumps(report))
        worse = self.run_recall("--baseline", str(baseline))
        self.assertEqual(worse.returncode, 1, worse.stderr)
        self.assertIn("lost toy decide.py:4 load_rows", worse.stdout)
        self.assertIn("recall 2 -> 1 of 2", worse.stdout)
        self.assertIn("(-3)", worse.stdout)

        baseline.write_text("not json")
        self.assertIn("is not a recall --json report", self.run_recall("--baseline", str(baseline)).stderr)

    def test_found_and_missing_counts_and_strict_exit(self):
        result = self.run_recall("--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        repo = json.loads(result.stdout)["repos"][0]
        self.assertEqual(repo["found"], 1)
        self.assertEqual(repo["known"], 2)
        self.assertEqual(repo["missing"], [
            {"path": "decide.py", "line": 4, "function": "load_rows", "file_flagged": True},
        ])
        self.assertEqual(repo["found_in_files"], 2)
        self.assertEqual(repo["candidate_functions"], 1)

        strict = self.run_recall("--strict")
        self.assertEqual(strict.returncode, 1, strict.stderr)
        self.assertIn("1 of 2", strict.stdout)
        self.assertIn("decide.py:4 load_rows (file flagged)", strict.stdout)
        self.assertIn("2 of 2", strict.stdout)


if __name__ == "__main__":
    unittest.main()
