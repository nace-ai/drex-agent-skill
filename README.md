# Drex for coding agents

[Drex](https://drex.nace.ai/docs) answers System One decisions: a yes or no (`noul`), one pick from a fixed set (`choice`), or a level on an ordered scale (`score`), each with calibrated probabilities. This repository teaches your coding agent to use it. The agent keeps its own model for chat, reasoning, and code. Drex only answers the typed questions the agent or your application sends.

Get a Drex API key, export it once, then install the plugin or skills for your agent.

## Skills

| Skill | Use it to |
| --- | --- |
| [`drex-for-harness`](skills/drex-for-harness/SKILL.md) | Design and call Drex decisions: routing, classification, ranking, extraction checks, guardrails, and verification. |
| [`drexify`](skills/drexify/SKILL.md) | Scan a repository for decision sites, report them as a whole-repo summary with file pointers, and move them to Drex one step at a time. |

Install both. `drexify` relies on `drex-for-harness` for question design and API calls. Your agent loads each one automatically when it is relevant.

The skills come with two small scripts that the agent runs for you: a helper that checks your key and sends decision requests to hosted Drex, and a scanner that searches a repository for decision sites locally, without calling a model or the network. The Claude Code plugin bundles both skills and both scripts. Commands, limits, and development notes are in the [reference](docs/reference.md).

## Export the API key

1. **Get your API key.** Sign in at [drex.nace.ai](https://drex.nace.ai/login), open **API Keys**, create a key, and copy it.

2. **Set the key in your terminal.** Replace the placeholder with your key:

   ```bash
   export DREX_API_KEY='paste-your-key-here'
   ```

Run your agent from that terminal so it inherits the key. After installing, ask the agent to "check my Drex key". It verifies the key without spending credit and says what is wrong if it fails.

## Install Drex for your agent

These steps were tested end to end for Claude Code (the plugin) and Cursor (personal skills). The other sections follow each agent's documented skill installer and were not run as part of this repository's release checks.

### Claude Code

Use the [native plugin installer](https://code.claude.com/docs/en/plugins/install) to make Drex the default System One model. Run `/login` first if Claude Code says `Not logged in · Please run /login`.

```bash
claude plugin marketplace add nace-ai/drex-agent-skills
claude plugin install drex@nace-ai --config make_default=true
```

The plugin ships both skills. Restart Claude Code after installation to load Drex.

### OpenCode

[OpenCode discovers skills](https://opencode.ai/docs/skills/) under `~/.config/opencode/skills/`:

```bash
git clone --depth 1 https://github.com/nace-ai/drex-agent-skills.git "$HOME/drex-agent-skills"
mkdir -p ~/.config/opencode/skills
ln -s "$HOME/drex-agent-skills/skills/drex-for-harness" ~/.config/opencode/skills/drex-for-harness
ln -s "$HOME/drex-agent-skills/skills/drexify" ~/.config/opencode/skills/drexify
```

To prefer Drex for System One decisions, add this line to your global [`~/.config/opencode/AGENTS.md`](https://opencode.ai/docs/rules/):

> For System One decisions, use Drex by default and load the drex-for-harness skill. Do not silently switch to another decision provider if Drex is unavailable.

Restart OpenCode after installation to load Drex.

### Hermes Agent

Use [Hermes' native installer](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills):

```bash
hermes skills install nace-ai/drex-agent-skills/skills/drex-for-harness
hermes skills install nace-ai/drex-agent-skills/skills/drexify
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

Use Codex's [built-in `$skill-installer`](https://learn.chatgpt.com/docs/build-skills) in a Codex session. Ask it to install both Drex skills from their GitHub directories:

```text
$skill-installer Install https://github.com/nace-ai/drex-agent-skills/tree/main/skills/drex-for-harness and https://github.com/nace-ai/drex-agent-skills/tree/main/skills/drexify
```

Restart Codex after installation to load Drex.

### Cursor

[Cursor discovers personal skills](https://cursor.com/docs/skills) under `~/.cursor/skills/`:

```bash
git clone --depth 1 https://github.com/nace-ai/drex-agent-skills.git "$HOME/drex-agent-skills"
mkdir -p ~/.cursor/skills
ln -s "$HOME/drex-agent-skills/skills/drex-for-harness" ~/.cursor/skills/drex-for-harness
ln -s "$HOME/drex-agent-skills/skills/drexify" ~/.cursor/skills/drexify
```

For Cursor Cloud Agents, put both skills in the repository's `.cursor/skills/drex-for-harness/` and `.cursor/skills/drexify/`, or enable Cursor's Skills Sync for personal skills.

Cursor opened from the Dock does not see a key you exported in a separate terminal. Put the same `export DREX_API_KEY='paste-your-key-here'` line in `~/.zshrc` or `~/.bashrc`, then restart Cursor. Cursor's agent terminal reads that file. To keep the key out of a plain-text file on macOS, store it once with `security add-generic-password -a "$USER" -s drex -w` and put this line in the file instead:

```bash
export DREX_API_KEY="$(security find-generic-password -a "$USER" -s drex -w)"
```

Restart Cursor after installation to load Drex. Configure `DREX_API_KEY` in the cloud agent's environment if using Cursor Cloud Agents.

### Gemini CLI

Use [Gemini CLI's native Git installer](https://geminicli.com/docs/cli/skills/) with the path to each skill inside the repository:

```bash
gemini skills install https://github.com/nace-ai/drex-agent-skills.git --path skills/drex-for-harness
gemini skills install https://github.com/nace-ai/drex-agent-skills.git --path skills/drexify
gemini skills list --all
```

Restart Gemini CLI after installation to load Drex.

### GitHub Copilot

For [GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills), clone the repository and register both skill directories with Copilot's built-in skill command:

```bash
git clone --depth 1 https://github.com/nace-ai/drex-agent-skills.git "$HOME/drex-agent-skills"
copilot skill add "$HOME/drex-agent-skills/skills/drex-for-harness"
copilot skill add "$HOME/drex-agent-skills/skills/drexify"
copilot skill list
```

For Copilot coding or review agents on GitHub, put both skills in the target repository's `.github/skills/drex-for-harness/` and `.github/skills/drexify/` instead. GitHub CLI also offers [`gh skill install`](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills) for discoverable repository skills.

Restart Copilot CLI after installation to load Drex. Configure `DREX_API_KEY` in the cloud agent's environment if using Copilot coding or review agents on GitHub.

### Windsurf

[Windsurf discovers global skills](https://docs.devin.ai/desktop/cascade/skills) under `~/.codeium/windsurf/skills/`:

```bash
git clone --depth 1 https://github.com/nace-ai/drex-agent-skills.git "$HOME/drex-agent-skills"
mkdir -p ~/.codeium/windsurf/skills
ln -s "$HOME/drex-agent-skills/skills/drex-for-harness" ~/.codeium/windsurf/skills/drex-for-harness
ln -s "$HOME/drex-agent-skills/skills/drexify" ~/.codeium/windsurf/skills/drexify
```

Restart Windsurf after installation to load Drex.

### Cline

[Cline discovers global skills](https://docs.cline.bot/customization/skills) under `~/.cline/skills/`:

```bash
git clone --depth 1 https://github.com/nace-ai/drex-agent-skills.git "$HOME/drex-agent-skills"
mkdir -p ~/.cline/skills
ln -s "$HOME/drex-agent-skills/skills/drex-for-harness" ~/.cline/skills/drex-for-harness
ln -s "$HOME/drex-agent-skills/skills/drexify" ~/.cline/skills/drexify
```

Restart Cline after installation to load Drex.

### OpenClaw

[OpenClaw's native installer](https://docs.openclaw.ai/cli/skills) accepts a local skill directory containing `SKILL.md`. Install each skill:

```bash
git clone --depth 1 https://github.com/nace-ai/drex-agent-skills.git "$HOME/drex-agent-skills"
openclaw skills install "$HOME/drex-agent-skills/skills/drex-for-harness" --global
openclaw skills install "$HOME/drex-agent-skills/skills/drexify" --global
```

Restart OpenClaw after installation to load Drex.

### Pi

Use Pi's [native Git package installer](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/packages.md):

```bash
pi install git:github.com/nace-ai/drex-agent-skills
pi list
```

Add `-l` to `pi install` for a project-local package. Pi fetches its own checkout and picks up both skills, so a separate `git clone` is unnecessary.

Restart Pi after installation to load Drex.

### DeepSeek Harness

[DeepSeek Harness discovers personal skills](https://deepseek-harness.github.io/deepseek-harness/en/reference/subsystems/skills) under `${DSH_HOME:-$HOME/.dsh}/skills/` and project skills under `.dsh/skills/`:

```bash
git clone --depth 1 https://github.com/nace-ai/drex-agent-skills.git "$HOME/drex-agent-skills"
mkdir -p "${DSH_HOME:-$HOME/.dsh}/skills"
ln -s "$HOME/drex-agent-skills/skills/drex-for-harness" "${DSH_HOME:-$HOME/.dsh}/skills/drex-for-harness"
ln -s "$HOME/drex-agent-skills/skills/drexify" "${DSH_HOME:-$HOME/.dsh}/skills/drexify"
```

Restart DeepSeek Harness after installation to load Drex.

### Other harness

If your agent supports [Agent Skills](https://agentskills.io/specification) but is not listed above, use its built-in skill installer if it can install the GitHub `skills/drex-for-harness` and `skills/drexify` directories. Otherwise, clone the repository (if you have not already), then link both skill directories into the agent's documented personal or project skill-discovery directory:

```bash
git clone --depth 1 https://github.com/nace-ai/drex-agent-skills.git "$HOME/drex-agent-skills"
mkdir -p "/path/to/your-agent/skills"
ln -s "$HOME/drex-agent-skills/skills/drex-for-harness" "/path/to/your-agent/skills/drex-for-harness"
ln -s "$HOME/drex-agent-skills/skills/drexify" "/path/to/your-agent/skills/drexify"
```

Replace `/path/to/your-agent/skills` with the actual directory from your agent's documentation; keep the checkout in place. If the agent does not support skills, follow its instructions for loading custom agent instructions instead; skill-directory links alone will not activate Drex.

Restart your agent after installation to load Drex. For cloud agents, configure `DREX_API_KEY` in the agent's supported environment or secrets settings.

## Use it

Ask in plain words. The agent loads the right skill on its own.

| You ask | The agent |
| --- | --- |
| "Drexify this repo." | Scans the repository and writes a report: a headline with counts, one line per decision site with a `path:line` pointer and the question shape Drex would answer, and a coverage line. It changes nothing in the repository. |
| "Drexify this repo and move the ticket router to Drex." | Scans, then changes that one site behind a configuration switch. It compares Drex with the current mechanism on real examples when the current one can run, tests the failure paths, and reports what it changed and measured. |
| "Use Drex to check which of these 30 emails ask for a refund." | Writes the questions and calls hosted Drex through the helper. |
| "Add a Drex check before we auto-close a ticket." | Designs the question and writes the integration code with its tests. |

What the agent does and does not do:

- **The default stays yours.** A new Drex path starts switched off, and your existing mechanism stays the default, unless Drex is your default decision provider or you ask to switch.
- **No silent fallback in default mode.** When Drex is the default and a call fails, new code raises, returns an explicit failure, or uses a documented safe default, and it logs the failure. It does not quietly call another model provider. A switch back to your old mechanism is fine, because a person flips it.
- **Guardrails fail closed.** When Drex is down, moderation or a permission check blocks instead of letting everything through, and reports an outage, such as HTTP 503, rather than telling the user their content broke a rule. A filter that would turn away real users, such as a spam filter, lets input through with a log line instead.
- **The key goes only to Drex.** Generated clients send `DREX_API_KEY` only to `https://drex.nace.ai`, never to a self-hosted or other URL.
- **The answering model is checked.** Drex answers a mistyped or retired model id with another model instead of an error. Generated clients compare the response's `model` with the pinned id, and the helper warns when they differ.
- **Nothing ships without you.** The agent does not change production routing, credentials, or unrelated code without your authorization, and it reports only what it actually ran.

## Make Drex the default

In Claude Code, the plugin's `make_default` option decides it. The install command above sets it to `true`. With `false`, Drex adds capability and leaves your existing decision providers in charge. To change it, uninstall the plugin and install it again with the other value.

In other agents, installing the skills adds capability only. To make Drex the default, add a line like this to the agent's persistent instructions, such as `AGENTS.md`:

> For System One decisions, use Drex by default and load the drex-for-harness skill. Do not silently switch to another decision provider if Drex is unavailable.

## Data and security

- **The scan stays local.** It reads files and writes only the map and report paths you give it.
- **Drex sees only what is sent.** A decision request carries a `state` and its questions. The agent puts in it only what the task needs, and the skill tells it not to send private evaluation data as probes.
- **The key stays in the environment.** Never paste it into chat or source code. The Claude plugin's session hook only adds text to the agent's context. It reads no files or credentials and makes no network calls.
- **Self-hosted Drex needs no key**, and the hosted key is never sent to it.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `DREX_API_KEY is missing` | Export the key in the terminal that starts the agent. For Cursor opened from the Dock, put the export in `~/.zshrc` or `~/.bashrc` and restart Cursor. |
| `DREX_API_KEY has an invalid format` | Copy the whole key again. It starts with `nace_sk_`. |
| `Authentication failed` (401) | The key is wrong or revoked. Create a new one under **API Keys**. |
| `insufficient credit` (402) | Top up or add a card under **Billing**. The key check still works without credit. |
| `Drex rejected the request` (422) | The request is invalid or too long. Fix the request instead of retrying it. |
| Rate limit (429) or unavailable (529) | Wait and retry. Lower the number of requests you send at once. |
| `warning: drex-v2.0 answered, not the requested model` | The pinned model id is retired or mistyped. Ask the agent to list the current Drex models and pin one of them. |
| Claude Code says `Not logged in · Please run /login` | Run `/login` in Claude Code, then install again. |
| The agent does not use Drex | Restart the agent after installing, check that the skill folders are where the agent looks for skills, or ask it to use the drex-for-harness skill by name. |

## Update and uninstall

Claude Code:

```bash
claude plugin marketplace update nace-ai
claude plugin update drex@nace-ai
claude plugin uninstall drex@nace-ai
```

For agents installed from a clone, update with `git -C "$HOME/drex-agent-skills" pull`. To uninstall, delete the two `drex-for-harness` and `drexify` links from the agent's skill folder, then delete the clone. Restart the agent after either change.

## Self-hosted Drex

To run the open-source [Drex](https://github.com/nace-ai/drex-decision-models) models yourself instead of using the hosted API, no `DREX_API_KEY` is needed:

1. **Start the server.** Follow the [Runners](https://github.com/nace-ai/drex-decision-models#runners) section of the Drex repository, using any of its runners. Check that it is up: `curl http://127.0.0.1:8000/health`. The Drex repository's examples serve on port 8000, and its Ollama build on 11434.

2. **Install the skills** for your agent with the instructions above.

3. **Point your agent at your server.** Add this line to your agent's instructions (for example `AGENTS.md`), using your server's address:

   > For System One decisions, use my self-hosted Drex at http://127.0.0.1:8000. Do not fall back to hosted Drex.

Self-hosted requests use the same `POST /v1/systemone` format as the hosted API, with no `Authorization` header. The bundled helper only talks to hosted Drex, so your agent uses an ordinary HTTP client for your server. Keep the server on `127.0.0.1` unless you add authentication in front of it, and never send a hosted API key to it. See the repository for hardware requirements and license terms.

## Develop

The [reference](docs/reference.md) covers the offline tests, the opt-in Claude Code install test, plugin validation, the scan's recall eval, and the repository layout.

## License

[MIT](LICENSE)
