# Drex for coding agents

Get a Drex API key, export it once, then install the plugin or skill for your agent. Drex handles System One decisions without changing your coding model.

## Export the API key

1. **Get your API key.** Sign in at [drex.nace.ai](https://drex.nace.ai/login), open **API Keys**, create a key, and copy it.

2. **Set the key in your terminal.** Replace the placeholder with your key:

   ```bash
   export DREX_API_KEY='paste-your-key-here'
   ```

Run your agent from that terminal so it inherits the key. You need GitHub access to the Drex repository. The instructions below use each agent's own installer when it can install this skill directly; no third-party skill installer is needed. For methods that refer to a local skill directory, clone the source once:

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

Use [Hermes' native installer](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills). For this GitHub repository, [configure `GITHUB_TOKEN` for Hermes](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills) if it needs access to the private source; do not put the token in the skill file:

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

Use Codex's [built-in `$skill-installer`](https://developers.openai.com/codex/skills) in a Codex session; ask it to install the Drex skill from its GitHub directory (with access to the repository):

```text
$skill-installer Install https://github.com/nace-ai/drex-agent-skill/tree/main/skills/drex
```

For a project-local skill instead, copy `skills/drex/SKILL.md` from your authenticated clone to `.agents/skills/drex/SKILL.md` in that project. The installer only installs the skill directory, not the repository-level helper script.

## Cursor

[Cursor discovers personal skills](https://cursor.com/docs/skills) under `~/.cursor/skills/`:

```bash
mkdir -p ~/.cursor/skills/drex
cp "$HOME/drex-agent-skill/skills/drex/SKILL.md" ~/.cursor/skills/drex/SKILL.md
```

For Cursor Cloud Agents, put the skill in the repository's `.cursor/skills/drex/`, or enable Cursor's Skills Sync for personal skills; unsynced local skills are unavailable to cloud agents.

## Gemini CLI

Use [Gemini CLI's native skill installer](https://geminicli.com/docs/cli/skills/) with the directory in your authenticated clone:

```bash
gemini skills install "$HOME/drex-agent-skill/skills/drex"
gemini skills list --all
```

The installer also accepts a Git URL with `--path skills/drex` when Git authentication for this repository is available to Gemini CLI.

## GitHub Copilot

For [GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills), register the cloned skill directory with Copilot's built-in skill command:

```bash
copilot skill add "$HOME/drex-agent-skill/skills/drex"
copilot skill list
```

Keep that clone in place: registering a directory does not copy its files. For Copilot coding or review agents on GitHub, put the skill in the target repository's `.github/skills/drex/` instead; a local personal skill is not available to a cloud agent. GitHub CLI also offers [`gh skill install`](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills) for discoverable repository skills, but the command above does not depend on remote skill discovery for this nested private repository.

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

Use Pi's [native package installer](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/packages.md) on the authenticated clone. Pi discovers the repository's `skills/drex/SKILL.md` through its standard `skills/` package directory:

```bash
pi install "$HOME/drex-agent-skill"
pi list
```

Keep the clone for this local package; `pi install -l "$HOME/drex-agent-skill"` instead registers it for the current project. To load the skill for just one session without installing a package, use `pi --skill "$HOME/drex-agent-skill/skills/drex"`.

## DeepSeek Harness

[DeepSeek Harness discovers personal skills](https://deepseek-harness.github.io/deepseek-harness/en/reference/subsystems/skills) under `${DSH_HOME:-$HOME/.dsh}/skills/` and project skills under `.dsh/skills/`:

```bash
mkdir -p "${DSH_HOME:-$HOME/.dsh}/skills/drex"
cp "$HOME/drex-agent-skill/skills/drex/SKILL.md" "${DSH_HOME:-$HOME/.dsh}/skills/drex/SKILL.md"
```

After installation, restart your agent so it loads Drex and inherits the exported key.
