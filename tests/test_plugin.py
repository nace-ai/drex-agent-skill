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

    def test_one_automatic_skill_and_no_legacy_onboarding(self):
        skills = list((ROOT / "skills").glob("*/SKILL.md"))
        self.assertEqual(skills, [ROOT / "skills/drex/SKILL.md"])
        skill = skills[0].read_text()
        self.assertIn("${user_config.make_default}", skill)
        self.assertNotIn("disable-model-invocation: true", skill)
        self.assertIn("## Find the useful workflow", skill)
        self.assertIn("## Design the questions", skill)
        self.assertIn("## Call Drex", skill)
        readme = (ROOT / "README.md").read_text()
        self.assertTrue(readme.startswith("# Drex for coding agents\n"))
        self.assertIn("drex.nace.ai/login", readme)
        self.assertIn("export DREX_API_KEY='paste-your-key-here'", readme)
        self.assertIn("claude plugin marketplace add nace-ai/drex-agent-skill", readme)
        self.assertIn("claude plugin install drex@nace-ai --config make_default=true", readme)
        clone = 'git clone --depth 1 https://github.com/nace-ai/drex-agent-skill.git "$HOME/drex-agent-skill"'
        local_agents = ("OpenCode", "Cursor", "GitHub Copilot", "Windsurf", "Cline", "OpenClaw", "DeepSeek Harness", "Other harness")
        native_agents = ("Claude Code", "Hermes Agent", "Codex", "Gemini CLI", "Pi")
        for agent in (*local_agents, *native_agents):
            section = readme.split(f"### {agent}\n", 1)[1].split("\n### ", 1)[0]
            if agent in local_agents:
                self.assertIn(clone, section, agent)
            else:
                self.assertNotIn(clone, section, agent)
            self.assertRegex(section, r"Restart .+ after installation to load Drex", agent)
        self.assertIn('ln -s "$HOME/drex-agent-skill/skills/drex" ~/.config/opencode/skills/drex', readme)
        self.assertIn("~/.config/opencode/AGENTS.md", readme)
        self.assertIn("hermes skills install nace-ai/drex-agent-skill/skills/drex", readme)
        self.assertIn("env_passthrough:\n    - DREX_API_KEY", readme)
        self.assertIn("$skill-installer Install https://github.com/nace-ai/drex-agent-skill/tree/main/skills/drex", readme)
        self.assertIn(".agents/skills/drex/", readme)
        self.assertIn('ln -s "$HOME/drex-agent-skill/skills/drex" ~/.cursor/skills/drex', readme)
        self.assertIn("gemini skills install https://github.com/nace-ai/drex-agent-skill.git --path skills/drex", readme)
        self.assertIn('copilot skill add "$HOME/drex-agent-skill/skills/drex"', readme)
        self.assertIn('ln -s "$HOME/drex-agent-skill/skills/drex" ~/.codeium/windsurf/skills/drex', readme)
        self.assertIn('ln -s "$HOME/drex-agent-skill/skills/drex" ~/.cline/skills/drex', readme)
        self.assertIn('openclaw skills install "$HOME/drex-agent-skill/skills/drex" --global', readme)
        self.assertIn("pi install git:github.com/nace-ai/drex-agent-skill", readme)
        self.assertIn("no third-party skill installer", readme)
        self.assertIn('ln -s "$HOME/drex-agent-skill/skills/drex" "${DSH_HOME:-$HOME/.dsh}/skills/drex"', readme)
        self.assertNotIn('cp "$HOME/drex-agent-skill', readme)
        self.assertNotIn("## Roo Code", readme)
        self.assertNotIn("npx skills add", readme)
        self.assertIn("## Install Drex for your agent\n", readme)
        self.assertIn("### Other harness\n", readme)
        self.assertNotIn("## Restart your agent\n", readme)
        self.assertLess(readme.index("### DeepSeek Harness\n"), readme.index("### Other harness\n"))
        self.assertIn("## Self-hosted Drex\n", readme)
        self.assertIn("https://github.com/nace-ai/drex-dlm#quick-start", readme)
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
