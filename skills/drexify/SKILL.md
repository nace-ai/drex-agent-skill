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

Plugin option `make_default`: `${user_config.make_default}`. Follow the provider preference rules in `drex-for-harness`. When Drex is the default, new decision code must not silently fall back to another provider at runtime. Keeping the existing provider path behind an explicit configuration switch is allowed.

## Scan the repository

Map every decision site in scope before changing code.

1. **Inventory.** Within the user's scope, find semantic decisions: model calls whose output is a label, boolean, pick-one-of-N, ranking, or level. Include heuristic or keyword classifiers that stand in for a judgment, rerankers and relevance filters, verification of extracted values, and existing Drex calls. Skip text generation, chat, summarization, embeddings, and deterministic logic.
2. **Record each site.** Plain-language process name, a verified `path:line` pointer, the current mechanism, the Drex shape (`choice`, `noul`, or `score`), fit, deployment constraints, and status: already on Drex, partial, candidate, or implemented in this session. One entry per decision, not per helper.
3. **Verify pointers.** Open each file and confirm the line sits inside the function or class that makes the decision. Drop or fix any pointer that does not resolve.

## Report the summary

Lead with a whole-repo summary, then list the processes grouped by product area or workflow:

```text
Your repo has been scanned. Identified 23 sites of drexification (5 already on Drex, 2 implemented now, 16 candidates). Below is the list of processes:

- Document splitting (`src/ingest/split.py:42`): already on Drex.
- Document classification (`src/ingest/classify.py:88`): implemented now, choice over 11 section types, behind `USE_DREX_CLASSIFY`.
- Template selection for the task (`src/tasks/templates.py:51`): candidate, choice over template ids.
- Audit policy identification (`src/policy/match.py:120`): candidate, noul per policy.
```

Counts must match the list. Mark a site implemented only when it was changed and verified in this session. Never report planned work as done. If the user or repository requires another report format, put the summary inside that format instead of replacing it. For a large list, write it to a file the user can review and keep the chat reply to the headline and top candidates.

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
4. Update the site's status in the summary and report what was changed and tested.

Do not change production routing, credentials, or unrelated code without authorization.
