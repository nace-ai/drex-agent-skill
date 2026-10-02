---
name: drex
license: MIT
description: >
  Write software that calls Drex, Nace's decision model. Drex is not a chat
  model and not a coding-agent LLM. It scores a state against typed choice,
  noul, and score questions and returns probabilities your code can branch on.
  Use when adding routing, classification, scoring, extraction checks,
  guardrails, or any structured decision; when replacing a prompt that asks
  an LLM to return JSON; or when choosing the hosted Drex API versus a
  self-hosted POST /v1/systemone server. Read the live docs before writing
  a request. This skill does not call Drex and does not expose MCP tools.
---

# Build with Drex

Drex returns a typed judgment and a probability. It does not write code, stream text, call tools, or choose the next agent step. Keep the coding agent's own model for writing and editing. Do not set Drex as that model, and do not import a backbone-only GGUF into stock Ollama chat and call the result Drex. Stock Ollama scores letter tokens. Drex scores a pointer head over the options you defined.

Code owns the workflow. Drex supplies the judgment where ordinary code needs semantic understanding.

## Read the live docs

The live docs are the source of truth for fields, limits, models, and errors. This skill gives direction. It does not freeze the API.

Fetch the Markdown form of a page when you can. Hosted pages are served as Markdown at `https://drex.nace.ai/llms.mdx/docs/<slug>/content.md`. The HTML page is `https://drex.nace.ai/docs/<slug>`.

| Task | Start here |
| --- | --- |
| First call | [Quick start](https://drex.nace.ai/llms.mdx/docs/quickstart/content.md) |
| Pick and shape a question | [Questions](https://drex.nace.ai/llms.mdx/docs/guides/questions/content.md) |
| What to put in `state` | [State](https://drex.nace.ai/llms.mdx/docs/guides/state/content.md) |
| Thresholds and confidence | [Reading answers](https://drex.nace.ai/llms.mdx/docs/guides/reading-answers/content.md) |
| Keys | [Authentication](https://drex.nace.ai/llms.mdx/docs/guides/authentication/content.md) |
| Coming from the TypeSafe SDK | [Migrate from TypeSafe](https://drex.nace.ai/llms.mdx/docs/guides/migrate-from-typesafe/content.md) |
| Model ids and prices | [Models](https://drex.nace.ai/llms.mdx/docs/reference/models/content.md) |
| Size and rate limits | [Limits](https://drex.nace.ai/llms.mdx/docs/reference/limits/content.md) |
| Every request and response field | [API reference](https://drex.nace.ai/llms.mdx/docs/api-reference/systemone/content.md) |
| Self-host the open weights | [nace-ai/drex-dlm](https://github.com/nace-ai/drex-dlm) and [the model card](https://huggingface.co/nace-ai/drex-dlm) |

If a page will not load, say so. Use the contract in this skill, and do not invent version-dependent limits, prices, or error strings.

## Two backends, one request

Write one request body. Only the base URL, auth, and context limit change.

```json
{
  "model": "drex-v1.0",
  "state": "I was charged twice for my March invoice. Please refund one of the charges.",
  "questions": {
    "wants_refund": {
      "type": "noul",
      "instructions": "Is the customer asking for a refund?"
    }
  }
}
```

`model` is optional on the hosted API. Omit it to take the account default, or send a pinned id (`drex-v1.0`, `drex-v1.5`) when the caller needs a fixed version. `drex-latest` can move. Read the models page before recommending it. Never send `jev-latest` or any other non-Drex name.

| | Hosted frontier | Self-host |
| --- | --- | --- |
| Call | `POST https://drex.nace.ai/v1/systemone` | `POST http://127.0.0.1:<port>/v1/systemone` |
| Auth | `Authorization: Bearer $DREX_API_KEY` | None on loopback |
| List models | `GET /v1/models` | The process you started. `--name` sets the response `model` on the Python server |
| Context | Read the live limits. `drex-v1.5` is the long model | Weights window is 32,768. Recommended serving default is 16,384. Full window is opt-in |

Do not tell a self-host user they have the hosted 131,072-token state limit. That limit belongs to the hosted frontier model, not to the open weights.

Python listens on port 8000, llama-server on 8097, and the Nace Ollama build on 11434. All three take the same JSON. A self-host server does not need a key. Do not add a bearer header unless the user has put one in front of it.

Keep `DREX_API_KEY` on a server or in a secret manager. Do not commit it, print it, or ship it in browser or mobile code. A key looks like `nace_sk_` plus a secret; never echo the value. The TypeSafe SDK can call Drex if `baseURL` is `https://drex.nace.ai` and the key is passed as `apiKey` or `TYPESAFE_API_KEY`. Set `defaultModel` to a `drex-*` id.

## Design the judgment

Start from the branch the application will take. Pick the type by what the code does next.

| The code needs | Type | You supply | You get back |
| --- | --- | --- | --- |
| Yes or no, then your own threshold | `noul` | `instructions`, optional `criteria.true` / `criteria.false` | `noul`, the probability of yes, from 0 to 1. No separate confidence |
| One label from a fixed set with no order | `choice` | `criteria` object. Keys are the labels. Values are short descriptions or `null` | `choice`, `probabilities`, `confidence` |
| A position on an ordered scale | `score` | `criteria` array, lowest first, at least two levels | `score`, `legend`, per-level `probabilities`, `confidence` |

Rules that Drex enforces:

- `instructions` must be a string when present. The TypeSafe helper `noul()` defaults it to `null`; Drex rejects that. Always pass a string.
- A `noul` needs a non-empty `instructions` or at least one non-empty criterion.
- `choice` criteria is an object with at least one label. An array is rejected.
- `score` criteria is an array of strings, lowest first. A one-level scale gives the model nothing to choose between.
- Question ids are the keys of `questions` and come back as the keys of `answers`. They are not sent to the model. Put the full meaning in `instructions` and `criteria`. Name ids for the field they fill (`wants_refund`), not `q1`.
- `state` is a string, object, or array. Send the shape you already have. Text only: do not put images, audio, video, or PDFs in `state` or `questions`.
- Ask every independent question about the same state in one `questions` map. That is one call. Do not loop one question per request.
- Do not wrap decisions in a `requests` list. That is not the hosted API. One POST body is one decision: one `state` and its `questions`.

`confidence` is not correctness, permission to act, or workflow success. Read the reading-answers page before treating it as a cutoff. A `noul` near 0.5 means yes and no are about equally likely, not medium intensity. Put questions and thresholds in one module so a person can review them. Agents write weak questions; expect the human to edit them before the code is accepted.

Hosted success bodies include `model`, `answers`, `usage.input_tokens`, `usage.output_tokens`, `evaluation_time_ms`, and `request_id`. A `score` legend comes back as an array of labels, not an object. A malformed body is HTTP 422 and is not retryable. Read the errors guide before writing retry logic. Do not copy a hosted error envelope onto a self-host server you have not read.

## Choose where it runs

Use the hosted API when the application is a product, needs the frontier model, or should not carry GPU weights. Pin a model id unless the user explicitly wants `drex-latest`.

Use self-host when the user wants the open weights on their own machine, no key, or an offline loop. Start from the drex-dlm README. The recommended default is `KEV_CONTEXT=16384` for Python and `SYSTEMONE_CONTEXT=16384` for llama-server and Ollama, with the server's `-c`, `-b`, and `-ub` matching that value. `32768` is the full window and is opt-in. A value above 32,768 falls back to 16,384. Oversized state raises; it is not silently truncated.

Hard-wire a call that must always run, such as a shell-command gate, in the application. This skill does not register tools, so the agent will not call Drex mid-task unless the user's code does.

## Verify

Run a representative request against the backend you told the user to use. Check the HTTP status, that every question id came back, and that the option names match the criteria you sent. Do not treat a cookbook threshold or a sample probability as a universal cutoff. Do not print the API key, and do not paste private evaluation cases into a request.
