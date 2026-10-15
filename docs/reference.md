# Reference

The skills run these scripts for the agent. This page is for people who want to run them by hand, review what they do, or work on this repository.

## The helper

`scripts/drex.py` needs Python 3.9 or newer and nothing else. It only talks to `https://drex.nace.ai`, ignores proxy settings, refuses redirects, and never prints, saves, or forwards the key. It reads the key from `DREX_API_KEY`.

| Command | What it does | Cost |
| --- | --- | --- |
| `python3 scripts/drex.py check --no-input` | Confirms the key works | Free |
| `python3 scripts/drex.py models --no-input` | Lists the current model ids | Free |
| `python3 scripts/drex.py judge --input request.json` | Sends one request and prints the response JSON. Reads standard input when `--input` is left out | Billed per input token |
| `python3 scripts/drex.py run -- claude` | Asks for the key at a hidden prompt and starts the command with it set. Saves nothing | Free |

A request names a model, a `state`, and its questions:

```json
{
  "model": "drex-v2.0",
  "state": "I was charged twice for my March invoice. Please refund one charge.",
  "questions": {
    "wants_refund": {"type": "noul", "instructions": "Is the customer asking for a refund?"}
  }
}
```

`judge` checks the request before sending it: a `drex-` model id is required, 1 to 512 questions, valid question shapes, and at most 4 MiB for `state` and `questions` together. It checks that every answer came back in the requested shape, and it warns on standard error when a different model answered than the one requested. It does not retry. It exits `0` on success, `1` on any error with a one-line reason on standard error, and `130` when cancelled. Error messages never repeat the key, the request, or the server's reply.

## The scan

```bash
python3 skills/drexify/scripts/drexify.py scan --repo /path/to/repo --save /tmp/drex-map.json
python3 skills/drexify/scripts/drexify.py scan --from /tmp/drex-map.json --group 1
python3 skills/drexify/scripts/drexify.py check report.md --repo /path/to/repo --fix
```

`scan` lists candidate functions: model calls, calls to the repository's own model wrappers, rerankers, fuzzy matching, and decision-named functions built on labels, keyword rules, or regexes. Wrappers are learned from files that import a model library or name an inference path such as `/chat/completions`. A short wrapper name such as `ask` counts only when it is called through its module, as in `llm.ask(`, or imported from it. The scan skips tests, fixtures, examples, vendored code, and database migrations. `--save` writes the map, and `--from` reads it back for one group or area without searching again. `check` verifies a written report: the headline counts, every `path:line` pointer, and the coverage line.

The candidate list is a checklist, not the answer. The agent opens every candidate and the code around it and decides what counts, using the rules in the `drexify` skill. The scan reads files locally, skips files over 1 MB, and never calls a model or the network.

Measured on this release, on an Apple silicon laptop:

| Measure | Result |
| --- | --- |
| Known decision sites on the candidate list, 21 pinned open-source repositories | 130 of 153 |
| Known sites in a flagged file | 146 of 153 |
| Scan time, LangChain (1,782 files scanned) | about 8 seconds |
| Scan time, Dify (6,329 files scanned) | about 15 seconds |

## Develop

```bash
python3 -m unittest discover -s tests -v
DREX_TEST_CLAUDE=1 python3 -m unittest tests.test_claude_install -v
claude plugin validate .
python3 evals/drexify/recall.py --cache /tmp/drexify-oss
```

- The unit tests are offline. They never call Drex, a model, or the network, and CI runs them on Python 3.9 to 3.14.
- `DREX_TEST_CLAUDE=1` installs the plugin into a temporary Claude Code profile and checks that the `make_default` choice reaches the session hook. It needs the `claude` CLI and never calls a model.
- `recall.py` checks out the pinned repositories in `evals/drexify/known_sites.json`, about 3.5 GB of shallow clones, runs the scan on each, and reports how many known sites are on the candidate list. Add `--strict` to fail when any known site is missing. Save a report with `--json` and pass it to a later run as `--baseline` to list the sites the new scan lost and the change in candidate counts. It exits 1 when a site was lost.
- The `Scan recall` workflow runs that comparison against the base branch on every pull request that changes the scanner or the answer key.

Layout:

| Path | What it is |
| --- | --- |
| `skills/drex-for-harness/SKILL.md` | How to design, call, and verify Drex decisions |
| `skills/drexify/SKILL.md` | How to scan, count, report, and migrate decision sites |
| `skills/drexify/scripts/drexify.py` | The scanner and report checker |
| `scripts/drex.py` | The hosted Drex helper |
| `scripts/session-context.sh`, `hooks/hooks.json` | The Claude Code hook that reports the `make_default` choice to the agent |
| `.claude-plugin/` | The Claude Code plugin and marketplace manifests |
| `evals/drexify/` | The recall eval and its answer key |
| `tests/` | Unit tests and the opt-in Claude install test |
