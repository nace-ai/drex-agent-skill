# Drex for coding agents

Teach your agent to use [Drex](https://drex.nace.ai/docs) for System One decisions: routing, classification, scoring, evidence checks, and other typed judgments inside a workflow. Your agent keeps its existing model for reasoning and coding.

**One plugin, one skill, two install choices.**

## Install in Claude Code

Use Claude Code **2.1.285 or later** and a POSIX `sh` on PATH (standard on macOS/Linux; available through Git Bash on Windows). Repository access is required.

Add the marketplace once:

```bash
claude plugin marketplace add nace-ai/drex-agent-skill
```

Then choose one:

### Add Drex

```bash
claude plugin install drex@nace-ai --config make_default=false
```

The agent learns how to use Drex and where it helps in workflows. Existing decision-provider preferences stay unchanged. `false` is also the default for a fresh installation when the flag is omitted.

### Make Drex the default System One model

```bash
claude plugin install drex@nace-ai --config make_default=true
```

The agent gets the same Drex guidance, plus the preference to use Drex over all other decision-model skills for System One judgments. If Drex is unavailable, it reports the problem instead of silently switching engines.

**No setup prompt or slash command follows installation.** The selected behavior is supplied automatically when Claude loads the plugin, normally in your next session. The agent loads the full skill itself when relevant. No need to ask it to activate Drex.

The default install scope is your user account. `--scope project` or `--scope local` can limit where the plugin is enabled, but the saved `make_default` option is a user-level plugin configuration, not an independent per-project preference. It applies wherever that plugin is enabled, subject to managed settings.

## Start using it

Just describe the task:

> Find the steps in this workflow that need semantic judgment rather than brittle rules. Propose typed questions and show how the answers drive the next step.

> Add a request router with an uncertain-case escalation path. Keep the questions and thresholds easy to review.

Both modes teach question design, workflow composition, HTTP integration, hosted versus self-hosted deployment, and verification. Default mode changes provider selection; it does not require an extra skill or a separate setup action.

## Credentials and first use

**Skill installation and API authentication are separate.** No activation command is needed, but hosted calls need your own API key. Installing the plugin does not create an account, provision a key, or start a model server. You can use its design guidance without any credentials.

### Hosted Drex: create a key

1. Sign in at [drex.nace.ai](https://drex.nace.ai/login), open **API Keys**, and create a key.
2. Copy it from the one-time display. Do not paste it into agent chat, a source file, or a command-line argument.
3. Choose one of the credential methods below. See [authentication](https://drex.nace.ai/llms.mdx/docs/guides/authentication/content.md) for rotation and revocation.

### Option A: hidden prompt, without a manual export

The optional helper needs **Python 3.9+**, with no additional packages. From a checkout of this repository:

```bash
python3 scripts/drex.py run -- claude
```

Run this **yourself in a terminal**, not through the agent. It prompts for the key with typing hidden, then launches Claude with `DREX_API_KEY` in its environment. If that variable is already set, there is no prompt. The key is not written to disk or placed in the command line, shell history, skill text, or hook context by the helper.

This launches a new agent process; it does not inject a key into an already-running session. It does not install the plugin either—use the install instructions above first. Each fresh launch prompts again unless your environment supplies the key. There is no keychain or persistent credential store in this helper.

If you need a checkout for these terminal commands:

```bash
git clone https://github.com/nace-ai/drex-agent-skill.git
python3 drex-agent-skill/scripts/drex.py run -- claude
```

Repository access is required. A copied helper also works on its own. The installed plugin bundles the same file under its root at `scripts/drex.py`; the skill explains how agents find it. Do not assume the plugin installation exposes a global `drex` command or sets a shell variable pointing to the plugin.

### Option B: your existing secret manager or environment

Supply **`DREX_API_KEY`** to the process making calls, using your secret manager, IDE environment configuration, or deployment secrets. For agent-time calls, start the agent with that environment. For application code, supply the key to the application's backend runtime instead. These environments are separate.

Do not put the actual key into an `export` command recorded in shell history. A secret-manager launcher or Option A avoids that. No key value belongs in the plugin's `make_default` configuration.

**Security boundary:** the launched command and its children inherit the key. Use only trusted commands. Environment injection keeps secrets out of ordinary prompts, but is not a vault or protection against an agent with unrestricted process/shell access. Do not run environment-dumping commands, enable HTTP debug logging, or expose the key in browser code.

### Check access or make a request

From the checkout, check a supplied key (or enter it at a hidden terminal prompt):

```bash
python3 scripts/drex.py check
```

This calls **GET `/v1/models`**, without an inference charge. It confirms authentication, not available credit or model quality. A key entered for this check is not saved for later commands. Agents and automation use `check --no-input`, which fails on a missing key instead of ever prompting.

For a real decision, create a JSON file with one state and a questions map:

```json
{
  "model": "drex-v1.0",
  "state": "I was charged twice. Please refund one charge.",
  "questions": {
    "wants_refund": {
      "type": "noul",
      "instructions": "Is the customer asking for a refund?"
    }
  }
}
```

With `DREX_API_KEY` supplied to the calling process:

```bash
python3 scripts/drex.py judge --input request.json
# Or: python3 scripts/drex.py judge < request.json
```

Alternatively, launch this one command with a hidden key prompt:

```bash
python3 scripts/drex.py run -- python3 scripts/drex.py judge --input request.json
```

`judge` itself never prompts, so agents can use it non-interactively. It sends the state and questions to hosted Drex; **successful inference calls are billable**. Use synthetic data first, then only data authorized for hosted processing. The helper writes the JSON response to stdout, fixed diagnostic messages to stderr, and returns nonzero on failure. It validates basic request/answer shapes but does not establish semantic correctness or implement your routing policy. The served model is retained in the result; aliases and retired IDs can resolve to a different model, so check it when exact model identity matters.

The helper is intentionally small: fixed `https://drex.nace.ai` origin, redirects refused, no environment proxies, no automatic retries, no provider fallback, and no request/credential logging. It does not implement every SDK feature or every server validation rule. Transient errors return to the caller; use bounded retry/manual-review policy, not guessed answers. Do not blindly repeat invalid requests.

### Self-hosted Drex

Give the agent your server endpoint and authentication requirements. Follow the [self-host README](https://github.com/nace-ai/drex-dlm) for deployment and limits. The helper above is **hosted-only**; it deliberately cannot forward a hosted API key to a custom URL. Use a separate client for self-hosted inference, with that deployment's credentials if required. The documented loopback server needs no hosted Drex key.

The agent asks for missing connection details when a task needs a call—not for permission to activate the skill.

## How the install flag works

`make_default` is a declared boolean plugin option. Claude saves it at installation. Small local hooks add the selected mode to context at session start, before prompts, and when subagents start. This makes the preference available before Claude chooses which decision-model skill to use, rather than hiding it inside a skill that has not loaded yet.

The hooks only emit fixed context. They do not inspect prompts, read files or credentials, contact a service, change permissions, or modify other skills. Nothing is written into your project's `AGENTS.md` or `CLAUDE.md`. Disabling the plugin removes its hooks from future sessions; use a fresh session to discard previously injected context.

“Default” is an agent instruction about provider selection, **not a hard routing lock**. Other skills remain installed. Explicit user choices, higher-priority instructions, safety rules, and data-handling restrictions still apply. There is no MCP server or chat-model replacement. A task needs an authorized HTTP-capable tool or application client to call Drex; mandatory decision gates belong in application or harness code.

If hooks are disabled by policy or `sh` is unavailable, automatic preference injection cannot run. The plugin does not claim otherwise.

## Other agents

Copy `skills/drex/` into your agent's supported skills directory for Drex capability. Claude's `--config` flag and plugin hooks do not transfer to other agents; a plain skill copy does not establish a default-provider override. No second skill is needed.

## Development

```bash
python3 -m unittest discover -s tests -v
claude plugin validate .claude-plugin/plugin.json --strict
claude plugin validate .claude-plugin/marketplace.json --strict
claude plugin validate skills --strict
```

The offline tests check both flag values, all context events, malformed configuration, packaging, and the absence of a manual activation step. Helper tests use only synthetic credentials and mocked HTTP responses to cover credential injection, validation, redaction, and failures. They never call the live API. See `tests/test_claude_install.py` for an opt-in isolated install smoke test using the real Claude CLI, without an LLM or Drex API call.

Validated on Claude Code 2.1.285: both install flags reach the actual SessionStart hook with the expected behavior, using temporary Claude configurations. This verifies installation and context delivery, not model compliance or end-to-end API connectivity.

Claude references: [install options](https://code.claude.com/docs/en/plugins/cli-reference#plugin-install), [plugin configuration](https://code.claude.com/docs/en/plugins/manifest-reference#user-configuration), [context hooks](https://code.claude.com/docs/en/hooks#add-context-for-claude).

## License

[MIT](LICENSE).
