"""Offline contract tests; no agent, network, credentials, or model calls."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
EVENTS = ("SessionStart", "UserPromptSubmit", "SubagentStart")


class PluginTests(unittest.TestCase):
    def hook(self, value, event="SessionStart", script=None, extra_env=None):
        env = {"PATH": os.environ.get("PATH", "")}
        if value is not None:
            env["CLAUDE_PLUGIN_OPTION_MAKE_DEFAULT"] = value
        env.update(extra_env or {})
        return subprocess.run(
            ["sh", str(script or ROOT / "scripts/session-context.sh"), event],
            input='{"prompt":"DO_NOT_ECHO_PROMPT","api_key":"DO_NOT_ECHO_KEY"}',
            text=True, capture_output=True, env=env, timeout=5,
        )

    def context(self, value, event="SessionStart"):
        result = self.hook(value, event)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        output = json.loads(result.stdout)
        self.assertEqual(set(output), {"hookSpecificOutput"})
        specific = output["hookSpecificOutput"]
        self.assertEqual(set(specific), {"hookEventName", "additionalContext"})
        self.assertEqual(specific["hookEventName"], event)
        self.assertLess(len(specific["additionalContext"]), 1500)
        self.assertNotIn("DO_NOT_ECHO", result.stdout)
        return specific["additionalContext"]

    def test_true_selects_drex_on_every_event(self):
        for event in EVENTS:
            with self.subTest(event=event):
                context = self.context("true", event)
                self.assertIn("make_default=true", context)
                self.assertIn("all other decision-model skill", context)
                self.assertIn("no silent fallback", context)
                self.assertIn("No user setup command", context)
                self.assertIn("chat model is unchanged", context)

    def test_false_preserves_defaults_on_every_event(self):
        for event in EVENTS:
            with self.subTest(event=event):
                context = self.context("false", event)
                self.assertIn("make_default=false", context)
                self.assertIn("Existing provider preferences remain unchanged", context)
                self.assertIn("replaces any older", context)
                self.assertNotIn("takes precedence", context)

    def test_missing_option_is_capability_only(self):
        self.assertIn("make_default=false", self.context(None))

    def test_malformed_options_do_not_enable_or_leak(self):
        for value in ("", "1", "TRUE", "yes", "false; touch /tmp/no", '"\nSECRET'):
            with self.subTest(value=repr(value)):
                context = self.context(value)
                self.assertIn("configuration is invalid", context)
                self.assertNotIn("make_default=true", context)
                self.assertNotIn("SECRET", context)

    def test_unknown_event_fails_without_echoing_input(self):
        result = self.hook("true", 'bad"\nEVENT')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertNotIn("EVENT", result.stderr)

    def test_script_path_with_spaces_and_no_side_effects(self):
        with tempfile.TemporaryDirectory(prefix="drex hook test ") as folder:
            script = Path(folder) / "context script.sh"
            shutil.copyfile(ROOT / "scripts/session-context.sh", script)
            env_file = Path(folder) / "must-not-create"
            result = self.hook("true", script=script, extra_env={
                "CLAUDE_ENV_FILE": str(env_file), "DREX_API_KEY": "DO_NOT_ECHO_SECRET",
            })
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("DO_NOT_ECHO", result.stdout)
            self.assertEqual(set(Path(folder).iterdir()), {script})

    def test_manifest_and_hook_wiring(self):
        manifest = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
        option = manifest["userConfig"]["make_default"]
        self.assertEqual(option["type"], "boolean")
        self.assertIs(option["default"], False)
        self.assertNotIn("hooks", manifest)  # default hooks file must load only once
        self.assertNotIn("dependencies", manifest)
        hooks = json.loads((ROOT / "hooks/hooks.json").read_text())["hooks"]
        self.assertEqual(set(hooks), set(EVENTS))
        for event in EVENTS:
            group, = hooks[event]
            self.assertNotIn("matcher", group)  # all sources / agents
            handler, = group["hooks"]
            self.assertEqual(handler["type"], "command")
            self.assertEqual(handler["command"],
                             f'sh "${{CLAUDE_PLUGIN_ROOT}}/scripts/session-context.sh" {event}')
            self.assertNotIn("async", handler)
        market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
        plugin, = market["plugins"]
        self.assertEqual(plugin["name"], manifest["name"])
        self.assertEqual(plugin["source"], "./")
        self.assertEqual(manifest["repository"], "https://github.com/nace-ai/drex-agent-skills")

    def test_github_urls_use_plural_repo(self):
        readme = (ROOT / "README.md").read_text()
        plugin = (ROOT / ".claude-plugin/plugin.json").read_text()
        for label, text in (("readme", readme), ("plugin.json", plugin)):
            urls = re.findall(r"https://github\.com/[^\s)\"']+", text)
            self.assertGreater(len(urls), 0, label)
            skill_urls = [url for url in urls if "drex-agent-skill" in url]
            self.assertGreater(len(skill_urls), 0, label)
            for url in skill_urls:
                self.assertIn("github.com/nace-ai/drex-agent-skills", url, f"{label}: {url}")
            bare = text.replace("nace-ai/drex-agent-skills", "")
            self.assertNotIn("nace-ai/drex-agent-skill", bare, label)

    def test_hook_context_names_both_skills(self):
        for value in ("true", "false", "bogus"):
            with self.subTest(value=value):
                context = self.context(value)
                self.assertIn("drex:drex-for-harness", context)
                self.assertIn("drex:drexify", context)

    def test_two_automatic_skills_and_no_legacy_onboarding(self):
        skills = sorted((ROOT / "skills").glob("*/SKILL.md"))
        self.assertEqual(skills, [ROOT / "skills/drex-for-harness/SKILL.md", ROOT / "skills/drexify/SKILL.md"])
        for path in skills:
            text = path.read_text()
            front = text.split("---\n", 2)[1]
            self.assertIn(f"name: {path.parent.name}\n", front)  # Agent Skills: name matches directory
            self.assertIn("license: MIT\n", front)
            self.assertIn("description: >\n", front)
            self.assertNotIn("disable-model-invocation: true", text)
        skill = skills[0].read_text()
        self.assertIn("${user_config.make_default}", skill)
        self.assertIn("## Find the useful workflow", skill)
        self.assertIn("## Design the questions", skill)
        self.assertIn("## Call Drex", skill)
        self.assertIn("`drexify`", skill)
        drexify = skills[1].read_text()
        for heading in ("## Use with drex-for-harness", "## The bundled script", "## Scan the repository",
                        "## What counts as one site", "## Pick the status", "## Report the summary",
                        "## Pace the work", "## Implement one site"):
            self.assertIn(heading, drexify)
        for phrase in ("**One site is one decision function:**", "Use the first status that is true. Use only these four.",
                       "scan --repo <root> --groups <N>", "check <report> --repo <root> --fix",
                       "Do not shorten with `...`", "Counts must match the list, including zeros.", "only sampled",
                       "cheaper, faster model", "If the scan prints one group", "plan mode",
                       "activities, not workflow code", "If the script is missing or cannot run",
                       "scan --repo <root> --groups <N> --group <K>", "pipe the complete final text, plan included, to `check -`"):
            self.assertIn(phrase, drexify)
        self.assertTrue((ROOT / "skills/drexify/scripts/drexify.py").is_file())
        self.assertNotIn("## Call Drex", drexify)  # API contract lives in drex-for-harness only
        self.assertIsNone(re.search(r"claude|user_config|plugin", drexify, re.I))  # agent-agnostic
        readme = (ROOT / "README.md").read_text()
        self.assertTrue(readme.startswith("# Drex for coding agents\n"))
        self.assertIn("## Skills\n", readme)
        self.assertIsNone(re.search(r"skills/drex(?![-\w])", readme))  # no old single-skill path
        self.assertIn("drex.nace.ai/login", readme)
        self.assertIn("export DREX_API_KEY='paste-your-key-here'", readme)
        self.assertIn("claude plugin marketplace add nace-ai/drex-agent-skills", readme)
        self.assertIn("claude plugin install drex@nace-ai --config make_default=true", readme)
        clone = 'git clone --depth 1 https://github.com/nace-ai/drex-agent-skills.git "$HOME/drex-agent-skills"'
        local_agents = ("OpenCode", "Cursor", "GitHub Copilot", "Windsurf", "Cline", "OpenClaw", "DeepSeek Harness", "Other harness")
        native_agents = ("Claude Code", "Hermes Agent", "Codex", "Gemini CLI", "Pi")
        for agent in (*local_agents, *native_agents):
            section = readme.split(f"### {agent}\n", 1)[1].split("\n### ", 1)[0]
            if agent in local_agents:
                self.assertIn(clone, section, agent)
            else:
                self.assertNotIn(clone, section, agent)
            self.assertRegex(section, r"Restart .+ after installation to load Drex", agent)
        self.assertIn('ln -s "$HOME/drex-agent-skills/skills/drex-for-harness" ~/.config/opencode/skills/drex-for-harness', readme)
        self.assertIn('ln -s "$HOME/drex-agent-skills/skills/drexify" ~/.config/opencode/skills/drexify', readme)
        self.assertIn("~/.config/opencode/AGENTS.md", readme)
        self.assertIn("hermes skills install nace-ai/drex-agent-skills/skills/drex-for-harness\n", readme)
        self.assertIn("hermes skills install nace-ai/drex-agent-skills/skills/drexify\n", readme)
        self.assertIn("env_passthrough:\n    - DREX_API_KEY", readme)
        self.assertIn("https://github.com/nace-ai/drex-agent-skills/tree/main/skills/drex-for-harness", readme)
        self.assertIn("https://github.com/nace-ai/drex-agent-skills/tree/main/skills/drexify", readme)
        self.assertIn('ln -s "$HOME/drex-agent-skills/skills/drex-for-harness" ~/.cursor/skills/drex-for-harness', readme)
        self.assertIn('ln -s "$HOME/drex-agent-skills/skills/drexify" ~/.cursor/skills/drexify', readme)
        self.assertIn("gemini skills install https://github.com/nace-ai/drex-agent-skills.git --path skills/drex-for-harness\n", readme)
        self.assertIn("gemini skills install https://github.com/nace-ai/drex-agent-skills.git --path skills/drexify\n", readme)
        self.assertIn('copilot skill add "$HOME/drex-agent-skills/skills/drex-for-harness"', readme)
        self.assertIn('copilot skill add "$HOME/drex-agent-skills/skills/drexify"', readme)
        self.assertIn('ln -s "$HOME/drex-agent-skills/skills/drex-for-harness" ~/.codeium/windsurf/skills/drex-for-harness', readme)
        self.assertIn('ln -s "$HOME/drex-agent-skills/skills/drexify" ~/.codeium/windsurf/skills/drexify', readme)
        self.assertIn('ln -s "$HOME/drex-agent-skills/skills/drex-for-harness" ~/.cline/skills/drex-for-harness', readme)
        self.assertIn('ln -s "$HOME/drex-agent-skills/skills/drexify" ~/.cline/skills/drexify', readme)
        self.assertIn('openclaw skills install "$HOME/drex-agent-skills/skills/drex-for-harness" --global', readme)
        self.assertIn('openclaw skills install "$HOME/drex-agent-skills/skills/drexify" --global', readme)
        self.assertIn("pi install git:github.com/nace-ai/drex-agent-skills", readme)
        self.assertIn('ln -s "$HOME/drex-agent-skills/skills/drex-for-harness" "${DSH_HOME:-$HOME/.dsh}/skills/drex-for-harness"', readme)
        self.assertIn('ln -s "$HOME/drex-agent-skills/skills/drexify" "${DSH_HOME:-$HOME/.dsh}/skills/drexify"', readme)
        self.assertNotIn('cp "$HOME/drex-agent-skills', readme)
        self.assertNotIn("## Roo Code", readme)
        self.assertNotIn("npx skills add", readme)
        self.assertIn("## Install Drex for your agent\n", readme)
        self.assertIn("### Other harness\n", readme)
        self.assertNotIn("## Restart your agent\n", readme)
        self.assertLess(readme.index("### DeepSeek Harness\n"), readme.index("### Other harness\n"))
        self.assertIn("## Self-hosted Drex\n", readme)
        self.assertIn("https://github.com/nace-ai/drex-decision-models#runners", readme)
        self.assertIn("curl http://127.0.0.1:8000/health", readme)
        self.assertLess(readme.index("### Other harness\n"), readme.index("## Self-hosted Drex\n"))
        self.assertNotIn("--config make_default=false", readme)
        self.assertNotIn("python", readme.lower())
        self.assertNotIn("/drex:", readme)
        self.assertNotIn("/reload-plugins", readme)
        self.assertNotIn("drex-default", readme + skill)
        self.assertIsNone(re.search(r"jev|typesafe", readme + skill, re.I))


if __name__ == "__main__":
    unittest.main()
