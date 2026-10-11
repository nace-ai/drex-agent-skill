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

This skill decides where Drex fits. The `drex-for-harness` skill covers how to call it: question design, the request contract, credentials, the bundled helper, and verification. Load it before designing questions or writing a call. If it is not installed, read the live Drex docs at `https://drex.nace.ai/docs/drex` before writing any integration, and do not guess fields, model ids, or limits.

Whether Drex is the user's default decision provider is decided by the provider preference rules in `drex-for-harness`. When Drex is the default, new decision code must not silently fall back to another provider at runtime. Keeping the existing provider path behind an explicit configuration switch is allowed.

## The bundled script

`scripts/drexify.py` sits next to this file. Resolve it relative to the real location of this SKILL.md, not the current directory. It needs Python 3.9+, uses only the standard library, reads files, and never calls a model or the network.

- `python3 "<skill-dir>/scripts/drexify.py" scan --repo <root> --save <map.json>` searches the whole repository once for decision signals, in under a minute on a large repository. It prints a short map of areas and balanced groups, one per suggested helper, and writes the full map to `<map.json>`. An area too big for one helper is split by folder. Add `--groups <N>` to choose the number yourself.
- `scan --from <map.json> --group <K>` prints group K from the saved map instantly, without searching again. The first line gives the group's totals: files, candidate functions, and files without one. Each file is followed by its candidate functions as `path:line  name  [signals]`. `--area <name>` prints one area. An area ending in `/*` means only the files directly inside that folder. It warns when the repository changed since the map was saved.
- Candidate functions are functions that call a model, Drex, a reranker, or fuzzy matching, functions that call the repository's own model wrappers, and decision-named functions that use labels, regexes, keyword rules, model wording, or a same-file helper with one of those signals. Wrappers are learned from files that import a model library. The list is a checklist, not the answer. Some candidates are not decisions, and some decisions are not listed.
- `python3 "<skill-dir>/scripts/drexify.py" check <report> --repo <root> --fix` checks a written report: the headline counts, the statuses, duplicates, and every `path:line` pointer. `--fix` rewrites a shortened path only when it matches exactly one file, and moves each site pointer to the first line of the function it sits in. Use `-` as the report to read it from standard input without writing anything.

If the script is missing or cannot run, do the same steps by hand.

## Scan the repository

1. **Map.** Run `scan --save` once, with the map file outside the repository (for example in the system temp folder). If the session cannot write that file, helpers use `scan --repo <root> --groups <N> --group <K>` instead, which repeats the search.
2. **Split when it pays.** If the scan prints one group, or helpers are not available, scan alone, because one agent is cheaper. Otherwise give each helper one group. Pass it the exact command `python3 "<skill-dir>/scripts/drexify.py" scan --from <map.json> --group <K>` with absolute paths. Tell it to record only sites whose decision function is inside its group. It may search the rest of the repository for callers of a function, but not for new sites.
3. **Check every candidate function.** Open the lines of each one, enough to see what it returns. Decide whether it is a site using the rules below. This fixed checklist is what keeps two scans of the same code close.
4. **Then look past the list.** For every flagged file without a candidate, open the hit lines the scan prints for it. Around those lines and around the candidates, look for decisions the scan cannot see: keyword lists or hand-tuned rules that guess what text means, and decisions made through an agent or request object built in one place and run in another.
5. **Return a fixed format.** Each helper returns three parts and nothing else: the site lines in the format below, a `## Not counted` section with any dead code or fixed logic worth noting, and one coverage line that sorts every candidate, such as `Checked 212 of 212 candidate functions: 48 sites, 61 callers or wrappers, 99 not decisions, 4 dead. Opened 95 of 95 files without one: 6 more sites. 54 site lines in total.` The total must equal the number of site lines returned.
6. **Wait for every helper.** Do not write the report until every helper has returned its result. If the agent only delivers helper results after the turn ends, end the turn with a short status and write the report when the results arrive. If a helper fails, rerun its group or scan that group yourself. A report built from some groups is not a scan of the repository.
7. **Merge and check.** Combine the lines, remove duplicates, write the report to a file, and run `check --fix`. Fix every remaining problem and rerun until it prints `ok`. Run it on the exact file you deliver, after your last edit. A passing draft does not count. If the session cannot write a file, pipe the report to `check -` and apply the reported fixes yourself.

Start every helper on a cheaper, faster model, and name that model explicitly when starting it, because some agents give helpers the lead's model by default. Keep the strongest model for merging, judging fit, and writing the plan.

## What counts as one site

Counting must be mechanical, so two scans of the same code give the same number.

- **One site is one decision function:** the function or method whose return value is the judgment, meaning a label, a yes or no, a pick from a set, or an ordered level.
- When a judgment passes through several functions, the site is the function that contains the model call, Drex call, or rule, even when a caller is the one on the candidate list. A shared client function that only sends requests for several different judgments is a wrapper. Each function that builds its own question for it is a site.
- Its callers, prompt, schema, parser, and settings are extra pointers on the same line, not new sites. Parsing the model's reply, for example a PASS or FAIL string, is part of the same site.
- The same judgment in two different functions is two sites only when each function makes its own model call, Drex call, or rule, because each one migrates separately. A function that gets the judgment by calling another site is a caller, not a site.
- One model call that returns several judgments at once is one site. Give the shape of the judgment the code acts on first, and name the others in the note.
- In scope: production code and evaluation code. Out of scope: tests, fixtures, notebooks, generated code, and vendored code.
- Out of scope: text generation, chat, summarization, embeddings, and fixed logic. Fixed logic includes thresholds on measured numbers (lengths, counts, scores), also when the score compares two texts, such as edit distance, token overlap, or recall. It also includes schema checks, exact lookups, and patterns that recognize a format, such as a number, date, currency, ID, or markup syntax. A keyword list or pattern matched against free text to guess its meaning, such as intent, topic, tone, or document type, is a site.
- Functions with no callers are not counted, and neither are functions reached only from them. Mention them in a separate note. Entry points count as called: HTTP handlers, queue or workflow activities, CLI commands, and scheduled jobs.

## Pick the status

Use the first status that is true. Use only these four. The headline lists them in a different, fixed order.

1. **implemented now:** this session changed the site to Drex and verified it.
2. **already on Drex:** Drex runs on the default path, all the way from the product's entry point. The default path is what runs with the code's own default values, ignoring environment variables, flags, settings files, and deployment configuration.
3. **partial:** Drex code exists for this site, but it is off by default, behind a flag or setting, one of several paths, or the default only inside a path that is itself not the default.
4. **candidate:** no Drex code exists for this site.

Drex code means any code that calls the Drex API, whatever the client is named. Look for the Drex host or its decision endpoints, not only the word Drex.

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

- Each site line is `- <process> (`<path:line>`): <status>, <shape>, <short note>.` The pointer is the first line of the decision function, its `def` or signature line. A class line is allowed when the class itself is the decision.
- Write every pointer as a full path from the repository root, even when it repeats a heading. Do not shorten with `...`, brace groups, or bare filenames.
- Counts must match the list, including zeros.
- After the list, add a coverage line: how many candidate functions were checked, and which parts of the repository were read in depth or only sampled.
- Put anything outside the four statuses, such as dead code or sites that should stay fixed logic, under a heading on its own line that starts with `Not counted`, for example `## Not counted`. `check` verifies pointers there but does not count them. The section ends at the next heading of the same or a higher level, so its subheadings stay uncounted. Put the implementation plan after the list under a heading that starts with `Plan` or `Implementation plan`, such as `## Plan`, which is not counted either. Headings above the headline and lines inside code blocks never change what is counted.
- Mark a site implemented only when it was changed and verified in this session. Never report planned work as done.
- If the user or repository requires another report format, put the summary inside that format instead of replacing it.
- For a large list, write it to a file the user can review and keep the chat reply to the headline and top candidates.

## Pace the work

- The scan and summary are a complete deliverable. They do not require implementing every site in one pass.
- In plan mode or a read-only session, scan and summarize only, then present the implementation plan in the harness's own plan format. The scan and the plan may name shapes without the live Drex docs. Read the docs before writing request bodies, choosing a model, or changing code.
- When implementing, change one site or one group of closely related sites at a time, and follow the repository's branch, review, size, and test conventions. Start with high-fit, low-risk sites unless the user sets the order.
- Respect deployment constraints and note them per site. Workflow engines with deterministic replay (for example Temporal) need Drex calls inside activities, not workflow code. Self-hosted, air-gapped, or customer-hosted deployments may need the self-hosted backend or the existing provider path kept available. Gate new paths with the repository's existing configuration or flag mechanism when one exists.
- On a re-scan, update the existing list and keep pointers stable rather than starting over.

## Implement one site

1. Design the questions with `drex-for-harness`. Keep the current mechanism's labels or outputs so callers do not change.
2. Put the new path behind the repository's configuration mechanism unless the user asks for a direct switch.
3. Compare Drex against the current mechanism on representative examples before recommending a default. Report accuracy, latency, and cost only from runs that actually happened.
4. Update the site's status in the summary, rerun `check`, and report what was changed and tested.

Do not change production routing, credentials, or unrelated code without authorization.
