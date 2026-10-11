# Drex for coding agents

Get a Drex API key, export it once, then install the plugin or skills for your agent. Drex handles System One decisions without changing your coding model.

## Skills

| Skill | Use it to |
| --- | --- |
| [`drex-for-harness`](skills/drex-for-harness/SKILL.md) | Design and call Drex decisions: routing, classification, ranking, extraction checks, guardrails, and verification. |
| [`drexify`](skills/drexify/SKILL.md) | Scan a repository for decision sites, report them as a whole-repo summary with file pointers, and move them to Drex one step at a time. |

Install both. `drexify` relies on `drex-for-harness` for question design and API calls. Your agent loads each one automatically when it is relevant.

## Export the API key

1. **Get your API key.** Sign in at [drex.nace.ai](https://drex.nace.ai/login), open **API Keys**, create a key, and copy it.

2. **Set the key in your terminal.** Replace the placeholder with your key:

   ```bash
   export DREX_API_KEY='paste-your-key-here'
   ```

Run your agent from that terminal so it inherits the key.

## Install Drex for your agent

### Claude Code

Use the [native plugin installer](https://code.claude.com/docs/en/plugins/install) to make Drex the default System One model:

```bash
claude plugin marketplace add nace-ai/drex-agent-skill
claude plugin install drex@nace-ai --config make_default=true
```

The plugin ships both skills. Restart Claude Code after installation to load Drex.

### OpenCode

[OpenCode discovers skills](https://opencode.ai/docs/skills/) under `~/.config/opencode/skills/`:

```bash
git clone --depth 1 https://github.com/nace-ai/drex-agent-skill.git "$HOME/drex-agent-skill"
mkdir -p ~/.config/opencode/skills
ln -s "$HOME/drex-agent-skill/skills/drex-for-harness" ~/.config/opencode/skills/drex-for-harness
ln -s "$HOME/drex-agent-skill/skills/drexify" ~/.config/opencode/skills/drexify
```

To prefer Drex for System One decisions, add this line to your global [`~/.config/opencode/AGENTS.md`](https://opencode.ai/docs/rules/):

> For System One decisions, use Drex by default and load the drex-for-harness skill. Do not silently switch to another decision provider if Drex is unavailable.

Restart OpenCode after installation to load Drex.

### Hermes Agent

Use [Hermes' native installer](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills):

```bash
hermes skills install nace-ai/drex-agent-skill/skills/drex-for-harness
hermes skills install nace-ai/drex-agent-skill/skills/drexify
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

Use Codex's [built-in `$skill-installer`](https://developers.openai.com/codex/skills) in a Codex session; ask it to install both Drex skills from their GitHub directories:

```text
$skill-installer Install https://github.com/nace-ai/drex-agent-skill/tree/main/skills/drex-for-harness and https://github.com/nace-ai/drex-agent-skill/tree/main/skills/drexify
```

Restart Codex after installation to load Drex.

### Cursor

[Cursor discovers personal skills](https://cursor.com/docs/skills) under `~/.cursor/skills/`:

```bash
git clone --depth 1 https://github.com/nace-ai/drex-agent-skill.git "$HOME/drex-agent-skill"
mkdir -p ~/.cursor/skills
ln -s "$HOME/drex-agent-skill/skills/drex-for-harness" ~/.cursor/skills/drex-for-harness
ln -s "$HOME/drex-agent-skill/skills/drexify" ~/.cursor/skills/drexify
```

For Cursor Cloud Agents, put both skills in the repository's `.cursor/skills/drex-for-harness/` and `.cursor/skills/drexify/`, or enable Cursor's Skills Sync for personal skills.

Restart Cursor after installation to load Drex. Configure `DREX_API_KEY` in the cloud agent's environment if using Cursor Cloud Agents.

### Gemini CLI

Use [Gemini CLI's native Git installer](https://geminicli.com/docs/cli/skills/) with the path to each skill inside the repository:

```bash
gemini skills install https://github.com/nace-ai/drex-agent-skill.git --path skills/drex-for-harness
gemini skills install https://github.com/nace-ai/drex-agent-skill.git --path skills/drexify
gemini skills list --all
```

Restart Gemini CLI after installation to load Drex.

### GitHub Copilot

For [GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills), clone the repository and register both skill directories with Copilot's built-in skill command:

```bash
git clone --depth 1 https://github.com/nace-ai/drex-agent-skill.git "$HOME/drex-agent-skill"
copilot skill add "$HOME/drex-agent-skill/skills/drex-for-harness"
copilot skill add "$HOME/drex-agent-skill/skills/drexify"
copilot skill list
```

For Copilot coding or review agents on GitHub, put both skills in the target repository's `.github/skills/drex-for-harness/` and `.github/skills/drexify/` instead. GitHub CLI also offers [`gh skill install`](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills) for discoverable repository skills.

Restart Copilot CLI after installation to load Drex. Configure `DREX_API_KEY` in the cloud agent's environment if using Copilot coding or review agents on GitHub.

### Windsurf

[Windsurf discovers global skills](https://docs.devin.ai/desktop/cascade/skills) under `~/.codeium/windsurf/skills/`:

```bash
git clone --depth 1 https://github.com/nace-ai/drex-agent-skill.git "$HOME/drex-agent-skill"
mkdir -p ~/.codeium/windsurf/skills
ln -s "$HOME/drex-agent-skill/skills/drex-for-harness" ~/.codeium/windsurf/skills/drex-for-harness
ln -s "$HOME/drex-agent-skill/skills/drexify" ~/.codeium/windsurf/skills/drexify
```

Restart Windsurf after installation to load Drex.

### Cline

[Cline discovers global skills](https://docs.cline.bot/customization/skills) under `~/.cline/skills/`:

```bash
git clone --depth 1 https://github.com/nace-ai/drex-agent-skill.git "$HOME/drex-agent-skill"
mkdir -p ~/.cline/skills
ln -s "$HOME/drex-agent-skill/skills/drex-for-harness" ~/.cline/skills/drex-for-harness
ln -s "$HOME/drex-agent-skill/skills/drexify" ~/.cline/skills/drexify
```

Restart Cline after installation to load Drex.

### OpenClaw

[OpenClaw's native installer](https://docs.openclaw.ai/cli/skills) accepts a local skill directory containing `SKILL.md`. Install each skill:

```bash
git clone --depth 1 https://github.com/nace-ai/drex-agent-skill.git "$HOME/drex-agent-skill"
openclaw skills install "$HOME/drex-agent-skill/skills/drex-for-harness" --global
openclaw skills install "$HOME/drex-agent-skill/skills/drexify" --global
```

Restart OpenClaw after installation to load Drex.

### Pi

Use Pi's [native Git package installer](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/packages.md):

```bash
pi install git:github.com/nace-ai/drex-agent-skill
pi list
```

Add `-l` to `pi install` for a project-local package. Pi fetches its own checkout and picks up both skills; a separate `git clone` is unnecessary.

Restart Pi after installation to load Drex.

### DeepSeek Harness

[DeepSeek Harness discovers personal skills](https://deepseek-harness.github.io/deepseek-harness/en/reference/subsystems/skills) under `${DSH_HOME:-$HOME/.dsh}/skills/` and project skills under `.dsh/skills/`:

```bash
git clone --depth 1 https://github.com/nace-ai/drex-agent-skill.git "$HOME/drex-agent-skill"
mkdir -p "${DSH_HOME:-$HOME/.dsh}/skills"
ln -s "$HOME/drex-agent-skill/skills/drex-for-harness" "${DSH_HOME:-$HOME/.dsh}/skills/drex-for-harness"
ln -s "$HOME/drex-agent-skill/skills/drexify" "${DSH_HOME:-$HOME/.dsh}/skills/drexify"
```

Restart DeepSeek Harness after installation to load Drex.

### Other harness

If your agent supports [Agent Skills](https://agentskills.io/specification) but is not listed above, use its built-in skill installer if it can install the GitHub `skills/drex-for-harness` and `skills/drexify` directories. Otherwise, clone the repository (if you have not already), then link both skill directories into the agent's documented personal or project skill-discovery directory:

```bash
git clone --depth 1 https://github.com/nace-ai/drex-agent-skill.git "$HOME/drex-agent-skill"
mkdir -p "/path/to/your-agent/skills"
ln -s "$HOME/drex-agent-skill/skills/drex-for-harness" "/path/to/your-agent/skills/drex-for-harness"
ln -s "$HOME/drex-agent-skill/skills/drexify" "/path/to/your-agent/skills/drexify"
```

Replace `/path/to/your-agent/skills` with the actual directory from your agent's documentation; keep the checkout in place. If the agent does not support skills, follow its instructions for loading custom agent instructions instead; skill-directory links alone will not activate Drex.

Restart your agent after installation to load Drex. For cloud agents, configure `DREX_API_KEY` in the agent's supported environment or secrets settings.

## Self-hosted Drex

To run the open-source [Drex](https://github.com/nace-ai/drex-decision-models) models yourself instead of using the hosted API, no `DREX_API_KEY` is needed:

1. **Start the server.** Follow the [Runners](https://github.com/nace-ai/drex-decision-models#runners) section of the Drex repository, using any of its runners. Check that it is up: `curl http://127.0.0.1:8000/health` (the default port is 8000; the other runners use 8097 and 11434).

2. **Install the skills** for your agent with the instructions above.

3. **Point your agent at your server.** Add this line to your agent's instructions (for example `AGENTS.md`), using your server's address:

   > For System One decisions, use my self-hosted Drex at http://127.0.0.1:8000. Do not fall back to hosted Drex.

Self-hosted requests use the same `POST /v1/systemone` format as the hosted API, with no `Authorization` header. The bundled helper only talks to hosted Drex, so your agent uses an ordinary HTTP client for your server. Keep the server on `127.0.0.1` unless you add authentication in front of it, and never send a hosted API key to it. See the repository for hardware requirements and license terms.

## Upgrade from the single drex skill

Version 0.5.0 renames the `drex` skill to `drex-for-harness` and adds `drexify`. A link or install that still points at `skills/drex` stops loading after you update.

- **Claude Code and Pi:** update the plugin or package as usual. Both skills come with it.
- **Linked installs** (OpenCode, Cursor, Windsurf, Cline, DeepSeek Harness, other harnesses): pull the checkout, remove the old link, and add both new links. For Cursor:

  ```bash
  git -C "$HOME/drex-agent-skill" pull
  rm ~/.cursor/skills/drex
  ln -s "$HOME/drex-agent-skill/skills/drex-for-harness" ~/.cursor/skills/drex-for-harness
  ln -s "$HOME/drex-agent-skill/skills/drexify" ~/.cursor/skills/drexify
  ```

- **Native installers** (Hermes, Codex, Gemini CLI, GitHub Copilot, OpenClaw): remove the old `drex` skill with the agent's own command, then install both skills as shown above.

Restart your agent after upgrading.
