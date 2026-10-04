"""Opt-in real CLI smoke test, with temporary HOME and CLAUDE_CONFIG_DIR.

Run: DREX_TEST_CLAUDE=1 python3 -m unittest discover -s tests -v
Requires Claude Code 2.1.285+ and sh. Never invokes an LLM or the Drex API.
Does not install into the user's normal Claude configuration.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get("DREX_TEST_CLAUDE") == "1", "opt-in Claude CLI smoke test")
class ClaudeInstallTests(unittest.TestCase):
    def test_install_flags_reach_session_hook(self):
        executable = shutil.which("claude")
        self.assertIsNotNone(executable, "Claude CLI is required")
        for value in ("false", "true"):
            with self.subTest(make_default=value), tempfile.TemporaryDirectory(prefix="drex-install-test-") as temp:
                base = Path(temp)
                home = base / "home"
                config = base / "config"
                project = base / "project"
                market = base / "marketplace"
                for path in (home, config, project):
                    path.mkdir()
                shutil.copytree(ROOT, market, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
                env = {
                    "PATH": os.environ.get("PATH", ""),
                    "HOME": str(home),
                    "CLAUDE_CONFIG_DIR": str(config),
                    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                    "DISABLE_AUTOUPDATER": "1",
                }

                def cli(*args):
                    result = subprocess.run([executable, *args], cwd=project,
                                            env=env, text=True, capture_output=True, timeout=90)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    return result

                cli("plugin", "marketplace", "add", str(market))
                cli("plugin", "install", "drex@nace-ai", "--config", f"make_default={value}")
                installed = json.loads(cli("plugin", "list", "--json").stdout)
                self.assertTrue(any(item["id"] == "drex@nace-ai" and item["enabled"] for item in installed))

                # --init-only executes SessionStart hooks without a model request.
                # Debug output remains only inside the temporary, credential-free HOME.
                debug = base / "startup.log"
                cli("--init-only", "--debug-file", str(debug))
                log = debug.read_text()
                self.assertIn(f"Drex plugin configuration: make_default={value}", log)
                self.assertNotIn("Drex plugin configuration is invalid", log)
                self.assertNotIn("unsupported event", log)


if __name__ == "__main__":
    unittest.main()
