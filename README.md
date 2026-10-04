# Make Drex the default System One model

Get a Drex API key, export it once, then install the plugin or skill for the harness you use. Drex handles System One decisions without changing your coding model.

The export is the shared step. Each heading after it is one supported harness, including Claude Code.

## Export the API key

1. **Get your API key.** Sign in at [drex.nace.ai](https://drex.nace.ai/login), open **API Keys**, create a key, and copy it.

2. **Set the key in your terminal.** Replace the placeholder with your key:

   ```bash
   export DREX_API_KEY='paste-your-key-here'
   ```

Your key stays in that terminal session; set it again in a new terminal. Keep the key out of chats and committed files. Start the harness from that terminal so the process inherits the key.

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

No manual Git checkout is needed. Restart OpenCode; it discovers the installed skill through its [native skill tool](https://opencode.ai/docs/skills/). To make Drex your default System One provider in OpenCode, add this line to your global [`~/.config/opencode/AGENTS.md`](https://opencode.ai/docs/rules/):

> For System One decisions, use Drex by default and load the drex skill. Do not silently switch to another decision provider if Drex is unavailable.

The Claude Code `make_default=true` flag does not configure OpenCode.

## Hermes Agent

Use [Hermes' native installer](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills) to install directly from the GitHub skill path (repository access required):

```bash
hermes skills install nace-ai/drex-agent-skill/skills/drex
```

Start a new Hermes session and check with `hermes skills list`. Hermes isolates terminal tool environments; for hosted calls, [allow the key through](https://hermes-agent.nousresearch.com/docs/user-guide/security#environment-variable-passthrough) in `~/.hermes/config.yaml`:

```yaml
terminal:
  env_passthrough:
    - DREX_API_KEY
```

Launch Hermes from the terminal where you exported the key. Do not paste it into chat. Installing the skill does not automatically change Hermes' default decision-provider preference. The Skills CLI alternative uses agent id `hermes-agent`.

## Codex

```bash
npx skills add nace-ai/drex-agent-skill -g -a codex -s drex
```

Agent id: `codex`. Restart Codex after installation.

## Cursor

```bash
npx skills add nace-ai/drex-agent-skill -g -a cursor -s drex
```

Agent id: `cursor`. Restart Cursor after installation.

## Gemini CLI

```bash
npx skills add nace-ai/drex-agent-skill -g -a gemini-cli -s drex
```

Agent id: `gemini-cli`. Restart Gemini CLI after installation.

## GitHub Copilot

```bash
npx skills add nace-ai/drex-agent-skill -g -a github-copilot -s drex
```

Agent id: `github-copilot`. Restart GitHub Copilot after installation.

## Windsurf

```bash
npx skills add nace-ai/drex-agent-skill -g -a windsurf -s drex
```

Agent id: `windsurf`. Restart Windsurf after installation.

## Cline

```bash
npx skills add nace-ai/drex-agent-skill -g -a cline -s drex
```

Agent id: `cline`. Restart Cline after installation.

## Roo Code

```bash
npx skills add nace-ai/drex-agent-skill -g -a roo -s drex
```

Agent id: `roo`. Restart Roo Code after installation.

## OpenClaw

```bash
npx skills add nace-ai/drex-agent-skill -g -a openclaw -s drex
```

Agent id: `openclaw`. Restart OpenClaw after installation.

A skill install provides Drex capability, not a universal `make_default` flag; set a preference in that harness's native persistent instructions if you want one. Hosted calls use the shared export above. Hermes' isolated tools still need the passthrough in the Hermes Agent section.
