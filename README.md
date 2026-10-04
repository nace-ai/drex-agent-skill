# Drex for coding agents

Get a Drex API key, export it once, then install the plugin or skill for your agent. Drex handles System One decisions without changing your coding model.

## Export the API key

1. **Get your API key.** Sign in at [drex.nace.ai](https://drex.nace.ai/login), open **API Keys**, create a key, and copy it.

2. **Set the key in your terminal.** Replace the placeholder with your key:

   ```bash
   export DREX_API_KEY='paste-your-key-here'
   ```

Run your agent from that terminal so it inherits the key. You need GitHub access to the Drex repository. Use the agent's own installer where possible; no third-party skill installer is needed.

## Install Drex for your agent

Choose your agent below and follow its instructions. Sections that need a local checkout include the clone command; if you already have a checkout, skip that command and use your checkout path instead. Keep a checkout in place for any skill-directory links. For an agent not listed here, see [Other harness](#other-harness). A standalone skill does not set a default decision provider; use the linked agent documentation for project-scoped installation.

### Claude Code

Use the [native plugin installer](https://code.claude.com/docs/en/plugins/install) to make Drex the default System One model:

```bash
claude plugin marketplace add nace-ai/drex-agent-skill
claude plugin install drex@nace-ai --config make_default=true
```

Restart Claude Code after installation to load Drex.

### OpenCode

[OpenCode discovers skills](https://opencode.ai/docs/skills/) under `~/.config/opencode/skills/`. Clone the repository, then link the complete skill directory:

```bash
git clone --depth 1 https://github.com/nace-ai/drex-agent-skill.git "$HOME/drex-agent-skill"
mkdir -p ~/.config/opencode/skills
ln -s "$HOME/drex-agent-skill/skills/drex" ~/.config/opencode/skills/drex
```

To prefer Drex for System One decisions, add this line to your global [`~/.config/opencode/AGENTS.md`](https://opencode.ai/docs/rules/):

> For System One decisions, use Drex by default and load the drex skill. Do not silently switch to another decision provider if Drex is unavailable.

Restart OpenCode after installation to load Drex.

### Hermes Agent

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

Restart Hermes after installation to load Drex and apply credential passthrough.

### Codex

Use Codex's [built-in `$skill-installer`](https://developers.openai.com/codex/skills) in a Codex session; ask it to install the Drex skill from its GitHub directory (with access to the repository):

```text
$skill-installer Install https://github.com/nace-ai/drex-agent-skill/tree/main/skills/drex
```

For a project-local skill instead, link `skills/drex` from an authenticated checkout into that project's `.agents/skills/drex/`. The built-in installer installs only the skill directory, not the repository-level helper script.

Restart Codex after installation to load Drex.

### Cursor

[Cursor discovers personal skills](https://cursor.com/docs/skills) under `~/.cursor/skills/`. Clone the repository, then link the complete skill directory:

```bash
git clone --depth 1 https://github.com/nace-ai/drex-agent-skill.git "$HOME/drex-agent-skill"
mkdir -p ~/.cursor/skills
ln -s "$HOME/drex-agent-skill/skills/drex" ~/.cursor/skills/drex
```

For Cursor Cloud Agents, put the skill in the repository's `.cursor/skills/drex/`, or enable Cursor's Skills Sync for personal skills; unsynced local skills are unavailable to cloud agents.

Restart Cursor after installation to load Drex. Configure `DREX_API_KEY` in the cloud agent's environment if using Cursor Cloud Agents.

### Gemini CLI

Use [Gemini CLI's native Git installer](https://geminicli.com/docs/cli/skills/) with the path to the skill inside the repository (requires Git access):

```bash
gemini skills install https://github.com/nace-ai/drex-agent-skill.git --path skills/drex
gemini skills list --all
```

Restart Gemini CLI after installation to load Drex.

### GitHub Copilot

For [GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills), clone the repository and register its skill directory with Copilot's built-in skill command:

```bash
git clone --depth 1 https://github.com/nace-ai/drex-agent-skill.git "$HOME/drex-agent-skill"
copilot skill add "$HOME/drex-agent-skill/skills/drex"
copilot skill list
```

Keep that clone in place: registering a directory does not copy its files. For Copilot coding or review agents on GitHub, put the skill in the target repository's `.github/skills/drex/` instead; a local personal skill is not available to a cloud agent. GitHub CLI also offers [`gh skill install`](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills) for discoverable repository skills, but the command above does not depend on remote skill discovery for this nested private repository.

Restart Copilot CLI after installation to load Drex. Configure `DREX_API_KEY` in the cloud agent's environment if using Copilot coding or review agents on GitHub.

### Windsurf

[Windsurf discovers global skills](https://docs.devin.ai/desktop/cascade/skills) under `~/.codeium/windsurf/skills/`. Clone the repository, then link the complete skill directory:

```bash
git clone --depth 1 https://github.com/nace-ai/drex-agent-skill.git "$HOME/drex-agent-skill"
mkdir -p ~/.codeium/windsurf/skills
ln -s "$HOME/drex-agent-skill/skills/drex" ~/.codeium/windsurf/skills/drex
```

Restart Windsurf after installation to load Drex.

### Cline

[Cline discovers global skills](https://docs.cline.bot/customization/skills) under `~/.cline/skills/`. Clone the repository, then link the complete skill directory:

```bash
git clone --depth 1 https://github.com/nace-ai/drex-agent-skill.git "$HOME/drex-agent-skill"
mkdir -p ~/.cline/skills
ln -s "$HOME/drex-agent-skill/skills/drex" ~/.cline/skills/drex
```

Restart Cline after installation to load Drex.

### OpenClaw

[OpenClaw's native installer](https://docs.openclaw.ai/cli/skills) accepts a local skill directory containing `SKILL.md`. Clone the repository to provide that directory:

```bash
git clone --depth 1 https://github.com/nace-ai/drex-agent-skill.git "$HOME/drex-agent-skill"
openclaw skills install "$HOME/drex-agent-skill/skills/drex" --global
```

Restart OpenClaw after installation to load Drex.

### Pi

Use Pi's [native Git package installer](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/packages.md) (requires Git access). Pi discovers the repository's `skills/drex/SKILL.md` through its standard `skills/` package directory:

```bash
pi install git:github.com/nace-ai/drex-agent-skill
pi list
```

Add `-l` to `pi install` for a project-local package. Pi fetches its own checkout; a separate `git clone` is unnecessary.

Restart Pi after installation to load Drex.

### DeepSeek Harness

[DeepSeek Harness discovers personal skills](https://deepseek-harness.github.io/deepseek-harness/en/reference/subsystems/skills) under `${DSH_HOME:-$HOME/.dsh}/skills/` and project skills under `.dsh/skills/`. Clone the repository, then link the complete skill directory:

```bash
git clone --depth 1 https://github.com/nace-ai/drex-agent-skill.git "$HOME/drex-agent-skill"
mkdir -p "${DSH_HOME:-$HOME/.dsh}/skills"
ln -s "$HOME/drex-agent-skill/skills/drex" "${DSH_HOME:-$HOME/.dsh}/skills/drex"
```

Restart DeepSeek Harness after installation to load Drex.

### Other harness

If your agent supports [Agent Skills](https://agentskills.io/specification) but is not listed above, use its built-in skill installer if it can install the GitHub `skills/drex` directory. Otherwise, clone the repository (if you have not already), then link the whole skill directory into the agent's documented personal or project skill-discovery directory:

```bash
git clone --depth 1 https://github.com/nace-ai/drex-agent-skill.git "$HOME/drex-agent-skill"
mkdir -p "/path/to/your-agent/skills"
ln -s "$HOME/drex-agent-skill/skills/drex" "/path/to/your-agent/skills/drex"
```

Replace `/path/to/your-agent/skills` with the actual directory from your agent's documentation; keep the checkout in place. If the agent does not support skills, follow its instructions for loading custom agent instructions instead; a skill-directory link alone will not activate Drex.

Restart your agent after installation to load Drex. For cloud agents, configure `DREX_API_KEY` in the agent's supported environment or secrets settings.
