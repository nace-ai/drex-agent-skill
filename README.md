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
