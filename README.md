# Drex for coding agents

Get a Drex API key, export it once, then install the plugin or skill for your agent. Drex handles System One decisions without changing your coding model.

## Export the API key

1. **Get your API key.** Sign in at [drex.nace.ai](https://drex.nace.ai/login), open **API Keys**, create a key, and copy it.

2. **Set the key in your terminal.** Replace the placeholder with your key:

   ```bash
   export DREX_API_KEY='paste-your-key-here'
   ```

Run your agent from that terminal so it inherits the key. You need GitHub access to the Drex repository. For the sections using a local skill file, clone the source once, then use your agent's installation command:

```bash
git clone --depth 1 https://github.com/nace-ai/drex-agent-skill.git "$HOME/drex-agent-skill"
```

If you already cloned it elsewhere, substitute that path in the commands below. A copied skill provides instructions, not the repository-level helper script or a default-provider setting; use the linked agent documentation for project-scoped installation.

## Claude Code

Use the [native plugin installer](https://code.claude.com/docs/en/plugins/install) to make Drex the default System One model:

```bash
claude plugin marketplace add nace-ai/drex-agent-skill
claude plugin install drex@nace-ai --config make_default=true
```

## OpenCode

[OpenCode discovers skills](https://opencode.ai/docs/skills/) under `~/.config/opencode/skills/`:

```bash
mkdir -p ~/.config/opencode/skills/drex
cp "$HOME/drex-agent-skill/skills/drex/SKILL.md" ~/.config/opencode/skills/drex/SKILL.md
```

To prefer Drex for System One decisions, add this line to your global [`~/.config/opencode/AGENTS.md`](https://opencode.ai/docs/rules/):

> For System One decisions, use Drex by default and load the drex skill. Do not silently switch to another decision provider if Drex is unavailable.

## Hermes Agent

Use [Hermes' native installer](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills):

```bash
hermes skills install nace-ai/drex-agent-skill/skills/drex
hermes skills list
```

For hosted calls, Hermes' isolated terminal tools need [credential passthrough](https://hermes-agent.nousresearch.com/docs/user-guide/security#environment-variable-passthrough) in `~/.hermes/config.yaml`:

```yaml
terminal:
  env_passthrough:
    - DREX_API_KEY
```

## Codex

[Codex discovers personal skills](https://developers.openai.com/codex/skills) under `~/.agents/skills/`:

```bash
mkdir -p ~/.agents/skills/drex
cp "$HOME/drex-agent-skill/skills/drex/SKILL.md" ~/.agents/skills/drex/SKILL.md
```

## Cursor

[Cursor discovers personal skills](https://cursor.com/docs/skills) under `~/.cursor/skills/`:

```bash
mkdir -p ~/.cursor/skills/drex
cp "$HOME/drex-agent-skill/skills/drex/SKILL.md" ~/.cursor/skills/drex/SKILL.md
```

For Cursor Cloud Agents, put the skill in the repository's `.cursor/skills/drex/` instead; local personal skills are not synced to remote agents.

## Gemini CLI

Use [Gemini CLI's native Git installer](https://geminicli.com/docs/cli/skills/) with the skill's path inside the repository:

```bash
gemini skills install https://github.com/nace-ai/drex-agent-skill.git --path skills/drex
gemini skills list --all
```

## GitHub Copilot

[Copilot discovers personal skills](https://docs.github.com/en/copilot/concepts/agents/about-agent-skills) under `~/.copilot/skills/`:

```bash
mkdir -p ~/.copilot/skills/drex
cp "$HOME/drex-agent-skill/skills/drex/SKILL.md" ~/.copilot/skills/drex/SKILL.md
```

For Copilot coding or review agents on GitHub, put the skill in the repository's `.github/skills/drex/` instead; a local personal skill is not available to a cloud agent.

## Windsurf

[Windsurf discovers global skills](https://docs.devin.ai/desktop/cascade/skills) under `~/.codeium/windsurf/skills/`:

```bash
mkdir -p ~/.codeium/windsurf/skills/drex
cp "$HOME/drex-agent-skill/skills/drex/SKILL.md" ~/.codeium/windsurf/skills/drex/SKILL.md
```

## Cline

[Cline discovers global skills](https://docs.cline.bot/customization/skills) under `~/.cline/skills/`:

```bash
mkdir -p ~/.cline/skills/drex
cp "$HOME/drex-agent-skill/skills/drex/SKILL.md" ~/.cline/skills/drex/SKILL.md
```

## OpenClaw

[OpenClaw's native installer](https://docs.openclaw.ai/cli/skills) accepts a local skill directory containing `SKILL.md`; the Drex skill is inside the repository rather than at its root:

```bash
openclaw skills install "$HOME/drex-agent-skill/skills/drex" --global
```

## Pi

[Pi discovers personal skills](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/skills.md) under `~/.pi/agent/skills/`:

```bash
mkdir -p ~/.pi/agent/skills/drex
cp "$HOME/drex-agent-skill/skills/drex/SKILL.md" ~/.pi/agent/skills/drex/SKILL.md
```

## DeepSeek Harness

[DeepSeek Harness discovers personal skills](https://deepseek-harness.github.io/deepseek-harness/en/reference/subsystems/skills) under `${DSH_HOME:-$HOME/.dsh}/skills/` and project skills under `.dsh/skills/`:

```bash
mkdir -p "${DSH_HOME:-$HOME/.dsh}/skills/drex"
cp "$HOME/drex-agent-skill/skills/drex/SKILL.md" "${DSH_HOME:-$HOME/.dsh}/skills/drex/SKILL.md"
```

After installation, restart your agent so it loads Drex and inherits the exported key.
