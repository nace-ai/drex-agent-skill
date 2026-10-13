#!/usr/bin/env python3
"""Small hosted Drex helper. Python 3.9+, standard library only; no secret storage."""
import argparse
import getpass
import http.client
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.request

BASE_URL = "https://drex.nace.ai"
REQUEST_LIMIT = 1048576
MODEL_OVERHEAD_LIMIT = 1024
RESPONSE_LIMIT = 8 * 1048576


class HelperError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def api_key(interactive=False):
    key = os.environ.get("DREX_API_KEY")
    if key is None:
        if not interactive or not sys.stdin.isatty():
            raise HelperError("DREX_API_KEY is missing. Supply it through your environment/secret manager, or run the helper's 'run' command yourself in a terminal. Never paste it into agent chat.")
        # Never fall back to an echoed stdin read when a terminal is unavailable.
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            try:
                key = getpass.getpass("Drex API key (hidden, not saved): ")
            except (getpass.GetPassWarning, EOFError):
                raise HelperError("A hidden terminal prompt is unavailable. Use a secret manager to supply DREX_API_KEY.") from None
    if not re.fullmatch(r"nace_sk_[A-Za-z0-9_-]{43}", key):
        raise HelperError("DREX_API_KEY has an invalid format; replace it with a key from Drex API Keys.")
    return key


def encode_request(body):
    if not isinstance(body, dict) or "state" not in body:
        raise HelperError("Request must be an object containing state and questions.")
    questions = body.get("questions")
    if not isinstance(questions, dict) or not 1 <= len(questions) <= 512:
        raise HelperError("questions must be a map containing 1 to 512 questions.")
    model = body.get("model")
    if not isinstance(model, str) or not re.fullmatch(r"drex-[A-Za-z0-9.-]+", model):
        raise HelperError("Set an explicit Drex model from the current model catalog.")
    if set(body) - {"state", "questions", "model"}:
        raise HelperError("Unknown request field; use one state and questions map, not a requests wrapper.")
    for name, question in questions.items():
        if not isinstance(name, str) or not name.strip() or not isinstance(question, dict):
            raise HelperError("Each question needs a non-empty ID and an object definition.")
        instructions = question.get("instructions", "")
        if not isinstance(instructions, str):
            raise HelperError("Question instructions must be strings when present.")
        kind, criteria = question.get("type"), question.get("criteria")
        if kind == "choice":
            if not isinstance(criteria, dict) or not criteria or any(not isinstance(v, (str, type(None))) for v in criteria.values()):
                raise HelperError("choice criteria must be a non-empty map of strings or null.")
        elif kind == "score":
            if not isinstance(criteria, list) or not criteria or any(not isinstance(v, str) for v in criteria):
                raise HelperError("score criteria must be a non-empty array of strings.")
        elif kind == "noul":
            if criteria is not None and not isinstance(criteria, dict):
                raise HelperError("noul criteria may contain true/false descriptions as strings or null.")
            described = criteria or {}
            for label in ("true", "false"):
                if label in described and not isinstance(described[label], (str, type(None))):
                    raise HelperError("noul criteria may contain true/false descriptions as strings or null.")
            if not instructions.strip() and not any(
                    isinstance(described.get(label), str) and described[label].strip()
                    for label in ("true", "false")):
                raise HelperError("noul needs a non-empty instruction or criterion.")
        else:
            raise HelperError("Question type must be choice, noul, or score.")
    try:
        encoded = json.dumps(body, allow_nan=False).encode("utf-8")
        counted = json.dumps(
            {"state": body["state"], "questions": body["questions"]}, allow_nan=False,
        ).encode("utf-8")
    except (ValueError, TypeError):
        raise HelperError("Request must contain valid, finite JSON values.") from None
    if len(counted) > REQUEST_LIMIT:
        raise HelperError("Request exceeds the hosted 1 MiB JSON limit.")
    return encoded


def request(key, path, data=None):
    # Fixed origin, no redirects, no environment proxies; never forward keys to a caller-selected URL.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    req = urllib.request.Request(BASE_URL + path, data=data, headers={
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    try:
        with opener.open(req, timeout=65) as response:
            raw = response.read(RESPONSE_LIMIT + 1)
    except urllib.error.HTTPError as error:
        messages = {
            400: "Drex rejected the request as malformed. Do not retry unchanged.",
            401: "Authentication failed; check or replace your Drex key.",
            402: "Drex account has insufficient credit.",
            403: "Drex refused access to this resource. Do not retry unchanged.",
            404: "Drex could not find that resource. Do not retry unchanged.",
            408: "The request timed out before Drex finished it. Retry later with a bounded policy.",
            413: "Drex rejected the request as too large. Do not retry unchanged.",
            422: "Drex rejected the request; check fields, model, and context limits. Do not retry unchanged.",
            429: "Drex rate limit reached; retry later according to the service retry policy.",
            500: "Drex encountered a service error; retry only with a bounded policy.",
            503: "Drex is temporarily unavailable. Retry later with a bounded policy.",
            504: "Drex gateway timed out. Retry later with a bounded policy.",
            529: "Drex is unavailable; retry later or queue for review.",
        }
        raise HelperError(messages.get(error.code, "Drex returned an unexpected HTTP status (redirects are not followed).")) from None
    except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException):
        raise HelperError("Could not reach Drex securely. No alternative provider was called.") from None
    if len(raw) > RESPONSE_LIMIT:
        raise HelperError("Drex response exceeded the helper's size limit.")
    try:
        return json.loads(raw)
    except (ValueError, UnicodeError):
        raise HelperError("Drex returned invalid JSON.") from None


def number(value, low, high):
    try:
        return type(value) in (int, float) and low <= value <= high and math.isfinite(value)
    except OverflowError:
        return False


def validate_response(result, body):
    invalid = HelperError("Drex returned an unexpected answer schema; no decision should be consumed.")
    if not isinstance(result, dict) or not {"model", "answers", "usage", "evaluation_time_ms", "request_id"} <= result.keys():
        raise invalid
    # Aliases/retired IDs may resolve to another model; return the served model to the caller.
    if not isinstance(result["model"], str) or not re.fullmatch(r"drex-[A-Za-z0-9.-]+", result["model"]):
        raise invalid
    if not isinstance(result["request_id"], str) or not re.fullmatch(r"req_[a-f0-9]{32}", result["request_id"]):
        raise invalid
    if not number(result["evaluation_time_ms"], 0, float("inf")):
        raise invalid
    usage = result["usage"]
    if not isinstance(usage, dict) or any(type(usage.get(k)) is not int or usage[k] < 0 for k in ("input_tokens", "output_tokens")):
        raise invalid
    answers = result["answers"]
    if not isinstance(answers, dict) or set(answers) != set(body["questions"]):
        raise invalid
    for name, question in body["questions"].items():
        answer = answers[name]
        kind = question["type"]
        if not isinstance(answer, dict) or answer.get("type") != kind:
            raise invalid
        if kind == "noul":
            if not number(answer.get("noul"), 0, 1):
                raise invalid
            continue
        criteria = question["criteria"]
        keys = set(criteria) if kind == "choice" else {str(i) for i in range(len(criteria))}
        probabilities = answer.get("probabilities")
        if not isinstance(probabilities, dict) or set(probabilities) != keys or any(not number(v, 0, 1) for v in probabilities.values()):
            raise invalid
        if not number(answer.get("confidence"), 0, 1):
            raise invalid
        if kind == "choice":
            if not isinstance(answer.get("choice"), str) or answer["choice"] not in keys:
                raise invalid
        elif answer.get("legend") != criteria or not number(answer.get("score"), 0, len(criteria) - 1):
            raise invalid


def load_body(filename):
    read_limit = REQUEST_LIMIT + MODEL_OVERHEAD_LIMIT
    try:
        if filename == "-":
            raw = sys.stdin.buffer.read(read_limit + 1)
        else:
            with Path(filename).open("rb") as file:
                raw = file.read(read_limit + 1)
        if len(raw) > read_limit:
            raise HelperError("Request file exceeds 1 MiB.")
        return json.loads(raw)
    except FileNotFoundError:
        raise HelperError("Request file was not found.") from None
    except HelperError:
        raise
    except (OSError, ValueError, UnicodeError):
        raise HelperError("Could not read a valid JSON request; input content is not logged.") from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    run = sub.add_parser("run", help="Prompt privately if needed, then launch an agent with DREX_API_KEY; saves nothing")
    run.add_argument("command", nargs=argparse.REMAINDER, help="-- claude (or another trusted command)")
    check = sub.add_parser("check", help="Validate credentials using GET /v1/models; no inference charge")
    check.add_argument("--no-input", action="store_true", help="Never prompt; use for agent tools and automation")
    judge = sub.add_parser("judge", help="Send one JSON request to hosted Drex; inference is billable")
    judge.add_argument("--input", default="-", help="JSON file, or - for stdin (default)")
    args = parser.parse_args(argv)
    try:
        if args.action == "run":
            command = args.command
            if command and command[0] == "--":
                command = command[1:]
            if not command:
                raise HelperError("Specify a trusted command, for example: run -- claude")
            key = api_key(interactive=True)
            env = dict(os.environ, DREX_API_KEY=key)
            try:
                return subprocess.run(command, env=env).returncode
            except OSError:
                raise HelperError("Could not launch the requested command.") from None
        if args.action == "check":
            key = api_key(interactive=not args.no_input)
            result = request(key, "/v1/models")
            if not isinstance(result, dict) or not isinstance(result.get("models"), list):
                raise HelperError("Drex returned an unexpected model catalog.")
            print("Drex authentication verified. No inference request made; credit availability was not checked.")
        else:
            body = load_body(args.input)
            data = encode_request(body)
            key = api_key()
            result = request(key, "/v1/systemone", data)
            validate_response(result, body)
            # Defend against an accidental exact-key echo even in a successful response.
            print(json.dumps(result, allow_nan=False).replace(key, "[REDACTED]"))
        return 0
    except HelperError as error:
        print("Drex helper: " + str(error), file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("Drex helper: cancelled.", file=sys.stderr)
        return 130
    except (ValueError, TypeError, RecursionError):
        print("Drex helper: invalid data; content is not logged.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
