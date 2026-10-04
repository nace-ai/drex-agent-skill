# Drex for coding agents

Get a Drex API key, export it once, then install the plugin or skill for the harness you use. Drex handles System One decisions without changing your coding model.

The export is the shared step. Each heading after it is one supported harness, including Claude Code.

## Export the API key

1. **Get your API key.** Sign in at [drex.nace.ai](https://drex.nace.ai/login), open **API Keys**, create a key, and copy it.

2. **Set the key in your terminal.** Replace the placeholder with your key:

   ```bash
   export DREX_API_KEY='paste-your-key-here'
   ```

## Claude Code

Install the plugin with Drex as the default. Run these in the same terminal where you exported the key:

```bash
claude plugin marketplace add nace-ai/drex-agent-skill
claude plugin install drex@nace-ai --config make_default=true
```

Start a new Claude Code session from that terminal so it inherits the key and loads the plugin.

## OpenCode

Install the Drex skill with the [Skills CLI](https://github.com/vercel-labs/skills) (requires Node.js and access to this repository):

```bash
npx skills add nace-ai/drex-agent-skill -g -a opencode -s drex
```

Restart OpenCode; it discovers the installed skill through its [native skill tool](https://opencode.ai/docs/skills/). To make Drex your default System One provider in OpenCode, add this line to your global [`~/.config/opencode/AGENTS.md`](https://opencode.ai/docs/rules/):

> For System One decisions, use Drex by default and load the drex skill. Do not silently switch to another decision provider if Drex is unavailable.

## Hermes Agent

Use [Hermes' native installer](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills):

```bash
hermes skills install nace-ai/drex-agent-skill/skills/drex
```

Start a new Hermes session and check with `hermes skills list`. Hermes isolates terminal tool environments; for hosted calls, [allow the key through](https://hermes-agent.nousresearch.com/docs/user-guide/security#environment-variable-passthrough) in `~/.hermes/config.yaml`:

```yaml
terminal:
  env_passthrough:
    - DREX_API_KEY
```

## Codex

```bash
npx skills add nace-ai/drex-agent-skill -g -a codex -s drex
```

## Cursor

```bash
npx skills add nace-ai/drex-agent-skill -g -a cursor -s drex
```

## Gemini CLI

```bash
npx skills add nace-ai/drex-agent-skill -g -a gemini-cli -s drex
```

## GitHub Copilot

```bash
npx skills add nace-ai/drex-agent-skill -g -a github-copilot -s drex
```

## Windsurf

```bash
npx skills add nace-ai/drex-agent-skill -g -a windsurf -s drex
```

## Cline

```bash
npx skills add nace-ai/drex-agent-skill -g -a cline -s drex
```

## Roo Code

```bash
npx skills add nace-ai/drex-agent-skill -g -a roo -s drex
```

## OpenClaw

```bash
npx skills add nace-ai/drex-agent-skill -g -a openclaw -s drex
```

