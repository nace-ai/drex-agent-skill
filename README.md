# Drex agent skill

Private skill for coding agents that write software against [Drex](https://drex.nace.ai/docs).

Drex is a decision model. It is not a drop-in chat model for Claude Code, Cursor, Codex, or Copilot, and this repo does not ship an MCP server. The skill teaches an agent when to call `POST /v1/systemone`, how to shape `choice`, `noul`, and `score` questions, and how to choose the hosted API or a self-hosted server.

This repository is private. Do not publish it, do not add it to skills.sh, and do not make the GitHub repo public unless that is asked for explicitly.

## Install

Use one method. Org access to this private repo is required.

### Claude Code

```bash
claude plugin marketplace add nace-ai/skills
claude plugin install drex@nace-ai
```

Invoke it with `/drex:drex`, or ask the agent to use the Drex skill.

Update with:

```bash
claude plugin marketplace update nace-ai
claude plugin update drex@nace-ai
```

Restart Claude Code, or run `/reload-plugins`.

### Other agents

Clone and copy the skill directory into that agent's skills folder:

```bash
git clone git@github.com:nace-ai/skills.git
```

Copy `skills/drex/` to `.claude/skills/drex/`, `.agents/skills/drex/`, `.codex/skills/drex/`, or the equivalent for the agent you are using. Include `SKILL.md` only; do not also install a second copy under another name.

### Paste into an agent

```text
Install the private Drex skill from git@github.com:nace-ai/skills.git. If you are in Claude Code, run `claude plugin marketplace add nace-ai/skills`, then `claude plugin install drex@nace-ai`. Otherwise clone that repo and copy skills/drex into this agent's skills directory. Use one method. Do not publish the repo. Then use the Drex skill when working on this project.
```

## Use

> Use the Drex skill. Look through this project for prompt-and-JSON steps that should be a typed decision, and propose the questions. Do not implement until I have edited them.

The agent writes your application code. It does not become a Drex-powered coding agent.

## License

[MIT](LICENSE).
