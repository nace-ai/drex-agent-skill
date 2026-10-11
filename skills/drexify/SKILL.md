---
name: drexify
license: MIT
description: >
  Scan a codebase for semantic decision sites that Drex can handle, report them
  as a whole-repository summary with verified file pointers, and migrate them in
  small, reviewable steps. Use when the user asks to drexify, scan, or audit a
  repository or large module for Drex opportunities, wants a list of decision
  sites, or wants to move several existing classifiers, routers, rerankers, or
  verifiers to Drex. Works in plan mode, read-only sessions, and incremental
  implementation.
---

# Drexify a repository

Map every place a codebase makes a semantic judgment, report the whole picture first, then move sites to Drex one at a time. The scan is useful on its own. Implementation is paced to the repository's conventions and deployment constraints.

## Use with drex-for-harness

This skill decides where Drex fits. The `drex-for-harness` skill covers how to call it: question design, the request contract, credentials, the bundled helper, and verification. Load it before designing questions or writing a call. If it is not installed, read the live Drex docs at `https://drex.nace.ai/docs` before writing any integration, and do not guess fields, model ids, or limits.

Whether Drex is the user's default decision provider is decided by the provider preference rules in `drex-for-harness`. When Drex is the default, new decision code must not silently fall back to another provider at runtime. Keeping the existing provider path behind an explicit configuration switch is allowed.

## The bundled script

`scripts/drexify.py` sits next to this file. Resolve it relative to the real location of this SKILL.md, not the current directory. It needs Python 3.9+, uses only the standard library, reads files, and never calls a model or the network.

- `python3 "<skill-dir>/scripts/drexify.py" scan --repo <root> --groups <N>` searches the whole repository once for decision signals in a few seconds. It prints a short map of areas and N balanced groups of areas.
- Add `--group <K>` to print the file list for group K only, or `--area <name>` for one area.
- `python3 "<skill-dir>/scripts/drexify.py" check <report> --repo <root> --fix` checks a written report: the headline counts, the statuses, duplicates, and every `path:line` pointer. `--fix` rewrites shortened paths that match exactly one file.

If the script is missing or cannot run, do the same steps by hand.

## Scan the repository

1. **Map.** Run `scan` once. Its signals are model calls and model library imports, existing Drex calls, rerankers, fuzzy matching, and decision-named functions that use label sets, regexes, or model wrappers. Treat the list as a starting point, not the full inventory.
2. **Split when it pays.** With three or more areas and helpers available, give each helper one group: tell it to run `scan --groups <N> --group <K>` with the same N, and to search or read only inside its group's folders. With one or two areas, scan alone, because one agent is cheaper.
3. **Read narrowly.** Open only the lines around each hit, enough to see the decision function, its inputs, and its outputs. Also look nearby for keyword lists or hand-tuned rules that guess what text means, which the scan can miss.
4. **Record each site** as one line in the format below. Helpers return these lines only, not prose.
5. **Merge and check.** Combine the lines, remove duplicates, write the report to a file, and run `check --fix`. Fix every remaining problem and rerun until it prints `ok`. If the session cannot write files, run `check` without `--fix` and apply its fixes in the report yourself.

Run helpers on a cheaper, faster model when the agent offers a choice. Keep the strongest model for merging, judging fit, and writing the plan.

## What counts as one site

Counting must be mechanical, so two scans of the same code give the same number.

- **One site is one decision function:** the function or method whose return value is the judgment, meaning a label, a yes or no, a pick from a set, or an ordered level.
- Its callers, prompt, schema, parser, and settings are extra pointers on the same line, not new sites.
- The same judgment in two different functions is two sites, because each one migrates separately.
- One model call that returns several judgments at once is one site. Name the judgments in its note.
- In scope: production code and evaluation code. Out of scope: tests, fixtures, notebooks, generated code, and vendored code.
- Out of scope: text generation, chat, summarization, embeddings, and fixed logic such as thresholds on measured numbers, schema checks, and exact lookups.
- Functions with no callers are not counted. Mention them in a separate note.

## Pick the status

Use the first status that is true. Use only these four.

1. **implemented now:** this session changed the site to Drex and verified it.
2. **already on Drex:** Drex runs on the default path with default settings.
3. **partial:** Drex code exists for this site, but it is off by default, behind a flag or setting, or one of several paths.
4. **candidate:** no Drex code exists for this site.

Pick the shape from the branch the code takes: `noul` for yes or no, `choice` for one of a fixed set, `score` for an ordered level. A reranker or relevance score maps to `score` with concrete relevance levels, or to `choice` when only the top candidate is used.

## Report the summary

Write the headline with all four counts in this order, then one line per site grouped by product area:

```text
Your repo has been scanned. Identified 23 sites of drexification (5 already on Drex, 3 partial, 2 implemented now, 13 candidates). Below is the list of processes:

- Document splitting (`src/ingest/split.py:42`): already on Drex, choice over document types.
- Document classification (`src/ingest/classify.py:88`): implemented now, choice over 11 section types, behind `USE_DREX_CLASSIFY`.
- Search passage filter (`src/search/filter.py:64`): partial, noul per passage, Drex only when `DREX_URL` is set.
- Template selection for the task (`src/tasks/templates.py:51`): candidate, choice over template ids, also `src/tasks/api.py:30`.
- Audit policy identification (`src/policy/match.py:120`): candidate, noul per policy.
```

- Each site line is `- <process> (`<path:line>`): <status>, <shape>, <short note>.` The pointer is the decision function.
- Write every pointer as a full path from the repository root, even when it repeats a heading. Do not shorten with `...`, brace groups, or bare filenames.
- Counts must match the list, including zeros.
- After the list, state which parts of the repository were read in depth and which were only sampled.
- Put anything outside the four statuses, such as dead code or sites that should stay fixed logic, in a separate note outside the counts.
- Mark a site implemented only when it was changed and verified in this session. Never report planned work as done.
- If the user or repository requires another report format, put the summary inside that format instead of replacing it.
- For a large list, write it to a file the user can review and keep the chat reply to the headline and top candidates.

## Pace the work

- The scan and summary are a complete deliverable. They do not require implementing every site in one pass.
- In plan mode or a read-only session, scan and summarize only, then present the implementation plan in the harness's own plan format.
- When implementing, change one site or one group of closely related sites at a time, and follow the repository's branch, review, size, and test conventions. Start with high-fit, low-risk sites unless the user sets the order.
- Respect deployment constraints and note them per site. Workflow engines with deterministic replay (for example Temporal) need Drex calls inside activities, not workflow code. Self-hosted, air-gapped, or customer-hosted deployments may need the self-hosted backend or the existing provider path kept available. Gate new paths with the repository's existing configuration or flag mechanism when one exists.
- On a re-scan, update the existing list and keep pointers stable rather than starting over.

## Implement one site

1. Design the questions with `drex-for-harness`. Keep the current mechanism's labels or outputs so callers do not change.
2. Put the new path behind the repository's configuration mechanism unless the user asks for a direct switch.
3. Compare Drex against the current mechanism on representative examples before recommending a default. Report accuracy, latency, and cost only from runs that actually happened.
4. Update the site's status in the summary, rerun `check`, and report what was changed and tested.

Do not change production routing, credentials, or unrelated code without authorization.
