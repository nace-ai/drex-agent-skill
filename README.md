# Make Drex the default System One model

Get a Drex API key, install the Claude Code plugin, and use Drex for System One decisions without changing your coding model.

## Quickstart

1. **Get your API key.** Sign in at [drex.nace.ai](https://drex.nace.ai/login), open **API Keys**, create a key, and copy it.

2. **Set the key in your terminal.** Replace the placeholder with your key:

   ```bash
   export DREX_API_KEY='paste-your-key-here'
   ```

3. **Install the plugin with Drex as the default.** Run these in the same terminal:

   ```bash
   claude plugin marketplace add nace-ai/drex-agent-skill
   claude plugin install drex@nace-ai --config make_default=true
   ```

Start a new Claude Code session from that terminal so it inherits the key and loads the plugin. Your key stays in that terminal session; set it again in a new terminal. Keep the key out of chats and committed files.

## OpenCode

After steps 1–2 above, install the Drex skill with the [Skills CLI](https://github.com/vercel-labs/skills) (requires Node.js and access to this repository):

```bash
npx skills add nace-ai/drex-agent-skill -g -a opencode -s drex
```

No manual Git checkout is needed. Restart OpenCode; it discovers the installed skill through its [native skill tool](https://opencode.ai/docs/skills/). To make Drex your default System One provider in OpenCode, add this line to your global [`~/.config/opencode/AGENTS.md`](https://opencode.ai/docs/rules/):

> For System One decisions, use Drex by default and load the drex skill. Do not silently switch to another decision provider if Drex is unavailable.

The Claude Code `make_default=true` flag does not configure OpenCode.

## Other coding agents

For Codex, Cursor, or Gemini CLI, use the same installer and select your agent:

```bash
npx skills add nace-ai/drex-agent-skill -g -a codex -s drex
# Replace codex with cursor or gemini-cli for those agents.
```

Restart your agent after installation. The skill is available for System One work, but installation alone does not change that agent's default provider; set a preference in its native persistent instructions if you want one. Supply `DREX_API_KEY` to the agent process as in step 2 for hosted calls.
