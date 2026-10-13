"""Offline, standard-library tests for scripts/drex.py.

Only synthetic credentials are used. Network and agent subprocesses are blocked
by default; the only real subprocesses execute Python's local CLI help. Each
case gets an empty temporary HOME/cwd and an isolated environment. Regression
cases cover previously discovered malformed-response bugs.
Run: python3 -B -m unittest discover -s tests -p test_helper.py -v
"""
import contextlib
import copy
import getpass
import http.client
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import urllib.error
import urllib.request
import warnings


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "drex.py"
SYNTHETIC_KEY = "nace_sk_" + "A" * 43
PRIVATE_INPUT = "SYNTHETIC_PRIVATE_INPUT_DO_NOT_LOG"
PRIVATE_SERVER = "SYNTHETIC_PRIVATE_SERVER_DO_NOT_LOG"
REAL_SUBPROCESS_RUN = subprocess.run

# Import without creating scripts/__pycache__ (this task owns only this file).
_spec = importlib.util.spec_from_file_location("drex_helper_under_test", SCRIPT)
drex = importlib.util.module_from_spec(_spec)
with mock.patch.object(sys, "dont_write_bytecode", True):
    _spec.loader.exec_module(drex)


def valid_body():
    return {
        "state": {"text": PRIVATE_INPUT},
        "model": "drex-test-v1.0",
        "questions": {
            "route": {
                "type": "choice",
                "criteria": {"accept": "Acceptable", "review": None},
            },
            "quality": {"type": "score", "criteria": ["low", "medium", "high"]},
            "safe": {"type": "noul", "instructions": "Is this safe?"},
        },
    }


def valid_response():
    return {
        "model": "drex-served-v2",
        "answers": {
            "route": {
                "type": "choice", "choice": "accept", "confidence": 0.75,
                "probabilities": {"accept": 0.75, "review": 0.25},
            },
            "quality": {
                "type": "score", "score": 1.5, "confidence": 0.5,
                "probabilities": {"0": 0.0, "1": 0.5, "2": 0.5},
                "legend": ["low", "medium", "high"],
            },
            "safe": {"type": "noul", "noul": 0.8},
        },
        "usage": {"input_tokens": 10, "output_tokens": 5},
        "evaluation_time_ms": 12.5,
        "request_id": "req_" + "0" * 32,
    }


class OfflineTestCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="drex helper offline ")
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        original_cwd = Path.cwd()
        os.chdir(self.folder)
        self.addCleanup(os.chdir, original_cwd)
        self.patchers = []
        self.start_patch(mock.patch.dict(os.environ, {
            "HOME": str(self.folder), "USERPROFILE": str(self.folder),
            "XDG_CONFIG_HOME": str(self.folder / "config"),
            "PYTHONDONTWRITEBYTECODE": "1",
        }, clear=True))
        self.network = self.start_patch(mock.patch.object(
            drex.urllib.request, "build_opener",
            side_effect=AssertionError("Unexpected HTTP attempt in offline test"),
        ))
        self.start_patch(mock.patch.object(
            socket, "socket", side_effect=AssertionError("Real sockets forbidden"),
        ))
        self.child = self.start_patch(mock.patch.object(
            drex.subprocess, "run",
            side_effect=AssertionError("Real agent subprocess forbidden"),
        ))
        self.prompt = self.start_patch(mock.patch.object(
            drex.getpass, "getpass",
            side_effect=AssertionError("Unexpected terminal prompt"),
        ))
        self.stdin = mock.Mock()
        self.stdin.isatty.return_value = False
        self.stdin.buffer = io.BytesIO()
        self.stdin.read.side_effect = AssertionError("Echoed stdin read forbidden")
        self.start_patch(mock.patch.object(drex.sys, "stdin", self.stdin))

    def start_patch(self, patcher):
        value = patcher.start()
        self.addCleanup(patcher.stop)
        return value

    def invoke(self, argv, body=None, raw=None):
        if body is not None:
            raw = json.dumps(body).encode("utf-8")
        if raw is not None:
            self.stdin.buffer = io.BytesIO(raw)
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = drex.main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def allow_response(self, result=None, raw=None, error=None):
        self.network.side_effect = None
        opener = self.network.return_value
        opener.open.side_effect = error
        response = opener.open.return_value.__enter__.return_value
        response.read.return_value = (
            raw if raw is not None else json.dumps(result).encode("utf-8")
        )
        return opener, response

    def assert_private(self, text, *more):
        for private in (SYNTHETIC_KEY, PRIVATE_INPUT, PRIVATE_SERVER) + more:
            if private:
                self.assertNotIn(private, text)
        self.assertNotIn("Traceback", text)

    def assert_failure(self, result, *more):
        code, stdout, stderr = result
        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertTrue(stderr.startswith("Drex helper: "), stderr)
        self.assert_private(stderr, *more)
        return stderr


class CredentialTests(OfflineTestCase):
    def test_synthetic_key_has_documented_format(self):
        self.assertRegex(SYNTHETIC_KEY, r"^nace_sk_[A-Za-z0-9_-]{43}$")
        self.assertEqual(len(SYNTHETIC_KEY), 51)

    def test_environment_key_never_prompts_or_changes_environment(self):
        os.environ["DREX_API_KEY"] = SYNTHETIC_KEY
        before = dict(os.environ)
        for interactive in (False, True):
            self.assertEqual(drex.api_key(interactive=interactive), SYNTHETIC_KEY)
        self.assertEqual(dict(os.environ), before)
        self.prompt.assert_not_called()
        self.network.assert_not_called()
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_all_documented_key_characters_are_accepted(self):
        os.environ["DREX_API_KEY"] = "nace_sk_" + "Az09_-" * 7 + "x"
        self.assertEqual(drex.api_key(), os.environ["DREX_API_KEY"])

    def test_missing_key_refused_without_prompt_unless_interactive_tty(self):
        for interactive, tty in ((False, False), (False, True), (True, False)):
            with self.subTest(interactive=interactive, tty=tty):
                self.stdin.isatty.return_value = tty
                with self.assertRaises(drex.HelperError) as caught:
                    drex.api_key(interactive=interactive)
                self.assertIn("missing", str(caught.exception))
                self.assert_private(str(caught.exception))
        self.prompt.assert_not_called()
        self.stdin.read.assert_not_called()
        self.network.assert_not_called()

    def test_malformed_environment_keys_are_rejected_without_echo_or_prompt(self):
        malformed = ["", "SYNTHETIC_INVALID_KEY", "nace_sk_" + "a" * 42,
                     "nace_sk_" + "a" * 44, "nace_sk_" + "!" * 43,
                     "nace_sk_" + "é" * 43, SYNTHETIC_KEY[:20] + "\n" + SYNTHETIC_KEY[20:],
                     SYNTHETIC_KEY[:20] + " " + SYNTHETIC_KEY[20:]]
        self.stdin.isatty.return_value = True
        for index, key in enumerate(malformed):
            with self.subTest(case=index):
                os.environ["DREX_API_KEY"] = key
                self.assert_failure(self.invoke(["check"]), key)
        self.prompt.assert_not_called()
        self.network.assert_not_called()

    def test_surrounding_whitespace_on_a_key_is_stripped(self):
        wrapped = " \t" + SYNTHETIC_KEY + "\r\n"
        os.environ["DREX_API_KEY"] = wrapped
        self.assertEqual(drex.api_key(), SYNTHETIC_KEY)
        self.allow_response({"models": []})
        code, stdout, stderr = self.invoke(["check"])
        self.assertEqual((code, stderr), (0, ""))
        self.assertNotIn(SYNTHETIC_KEY, stdout)
        req = self.network.return_value.open.call_args.args[0]
        self.assertEqual(req.get_header("Authorization"), "Bearer " + SYNTHETIC_KEY)
        self.assertNotIn("\n", req.get_header("Authorization"))
        del os.environ["DREX_API_KEY"]
        self.stdin.isatty.return_value = True
        self.prompt.side_effect = None
        self.prompt.return_value = "\n" + SYNTHETIC_KEY + "\n"
        self.assertEqual(drex.api_key(interactive=True), SYNTHETIC_KEY)
        self.prompt.assert_called_once()
        self.assertNotIn("DREX_API_KEY", os.environ)

    def test_hidden_prompt_is_ephemeral(self):
        self.stdin.isatty.return_value = True
        self.prompt.side_effect = None
        self.prompt.return_value = SYNTHETIC_KEY
        self.assertEqual(drex.api_key(interactive=True), SYNTHETIC_KEY)
        self.prompt.assert_called_once_with("Drex API key (hidden, not saved): ")
        self.assertNotIn("DREX_API_KEY", os.environ)
        self.stdin.read.assert_not_called()
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_prompted_malformed_key_does_not_leak(self):
        self.stdin.isatty.return_value = True
        self.prompt.side_effect = None
        self.prompt.return_value = PRIVATE_INPUT
        self.assert_failure(self.invoke(["run", "--", "synthetic-agent"]))
        self.child.assert_not_called()
        self.assertNotIn("DREX_API_KEY", os.environ)

    def test_getpass_warning_aborts_instead_of_echo_fallback(self):
        self.stdin.isatty.return_value = True
        reached_fallback = []

        def unsafe_prompt(_prompt):
            warnings.warn(PRIVATE_INPUT + SYNTHETIC_KEY, getpass.GetPassWarning)
            reached_fallback.append(True)
            return SYNTHETIC_KEY

        self.prompt.side_effect = unsafe_prompt
        with warnings.catch_warnings(record=True) as recorded:
            warnings.simplefilter("always")
            stderr = self.assert_failure(self.invoke(["run", "--", "synthetic-agent"]))
        self.assertIn("hidden terminal prompt is unavailable", stderr)
        self.assertEqual(recorded, [])
        self.assertEqual(reached_fallback, [])
        self.stdin.read.assert_not_called()
        self.child.assert_not_called()

    def test_prompt_eof_is_sanitized(self):
        self.stdin.isatty.return_value = True
        self.prompt.side_effect = EOFError(PRIVATE_INPUT + SYNTHETIC_KEY)
        self.assert_failure(self.invoke(["run", "synthetic-agent"]))
        self.child.assert_not_called()

    def test_prompt_keyboard_interrupt_is_sanitized(self):
        self.stdin.isatty.return_value = True
        self.prompt.side_effect = KeyboardInterrupt(PRIVATE_INPUT + SYNTHETIC_KEY)
        code, stdout, stderr = self.invoke(["run", "synthetic-agent"])
        self.assertEqual(code, 130)
        self.assertEqual(stdout, "")
        self.assertIn("cancelled", stderr)
        self.assert_private(stderr)
        self.child.assert_not_called()

    def test_judge_does_not_prompt_even_on_tty(self):
        self.stdin.isatty.return_value = True
        self.assert_failure(self.invoke(["judge"], body=valid_body()))
        self.prompt.assert_not_called()
        self.network.assert_not_called()


class RunTests(OfflineTestCase):
    def test_run_passes_key_only_in_child_environment_and_writes_nothing(self):
        os.environ["DREX_API_KEY"] = SYNTHETIC_KEY
        os.environ["SYNTHETIC_PRESERVED"] = "preserved"
        before = dict(os.environ)
        self.child.side_effect = None
        self.child.return_value.returncode = 23
        command = ["synthetic-agent", "argument with spaces", ";not-a-shell-command"]
        with mock.patch("builtins.open", side_effect=AssertionError("No file writes")), \
                mock.patch.object(Path, "open", side_effect=AssertionError("No file writes")):
            code, stdout, stderr = self.invoke(["run", "--"] + command)
        self.assertEqual((code, stdout, stderr), (23, "", ""))
        self.child.assert_called_once_with(command, env=before)
        child_env = self.child.call_args.kwargs["env"]
        self.assertIsNot(child_env, os.environ)
        self.assertEqual(child_env["DREX_API_KEY"], SYNTHETIC_KEY)
        self.assertNotIn(SYNTHETIC_KEY, repr(self.child.call_args.args))
        self.assertEqual(dict(os.environ), before)
        self.assertEqual(list(self.folder.iterdir()), [])
        self.network.assert_not_called()
        self.prompt.assert_not_called()

    def test_run_prompted_key_only_reaches_child_not_parent_or_disk(self):
        self.stdin.isatty.return_value = True
        self.prompt.side_effect = None
        self.prompt.return_value = SYNTHETIC_KEY
        self.child.side_effect = None
        self.child.return_value.returncode = 0
        self.assertEqual(self.invoke(["run", "synthetic-agent"]), (0, "", ""))
        self.assertEqual(self.child.call_args.args, (["synthetic-agent"],))
        self.assertEqual(self.child.call_args.kwargs["env"]["DREX_API_KEY"], SYNTHETIC_KEY)
        self.assertNotIn("DREX_API_KEY", os.environ)
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_missing_command_fails_before_credentials(self):
        for argv in (["run"], ["run", "--"]):
            with self.subTest(argv=argv):
                stderr = self.assert_failure(self.invoke(argv))
                self.assertIn("Specify a trusted command", stderr)
        self.prompt.assert_not_called()
        self.child.assert_not_called()
        self.network.assert_not_called()

    def test_missing_executable_error_does_not_echo_command_or_key(self):
        os.environ["DREX_API_KEY"] = SYNTHETIC_KEY
        self.child.side_effect = FileNotFoundError(PRIVATE_INPUT + SYNTHETIC_KEY)
        stderr = self.assert_failure(self.invoke(["run", "--", PRIVATE_INPUT]))
        self.assertIn("Could not launch", stderr)
        self.child.assert_called_once()
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_run_non_tty_missing_key_does_not_launch(self):
        self.assert_failure(self.invoke(["run", "synthetic-agent"]))
        self.prompt.assert_not_called()
        self.child.assert_not_called()


class RequestValidationTests(OfflineTestCase):
    def assert_invalid_body(self, body):
        # A valid key ensures the test cannot pass solely due to missing auth.
        os.environ["DREX_API_KEY"] = SYNTHETIC_KEY
        self.assert_failure(self.invoke(["judge"], body=body))
        self.network.assert_not_called()
        self.prompt.assert_not_called()
        self.child.assert_not_called()

    def test_valid_three_question_request_round_trips(self):
        body = valid_body()
        before = copy.deepcopy(body)
        self.assertEqual(json.loads(drex.encode_request(body)), body)
        self.assertEqual(body, before)

    def test_noul_criteria_and_instructions_variants(self):
        for question in (
            {"type": "noul", "instructions": "Decide", "criteria": None},
            {"type": "noul", "instructions": "Decide", "criteria": {}},
            {"type": "noul", "criteria": {"true": "Safe", "false": None}},
            {"type": "noul", "criteria": {"false": "Unsafe"}},
        ):
            with self.subTest(question=question):
                body = valid_body()
                body["questions"] = {"safe": question}
                self.assertEqual(json.loads(drex.encode_request(body)), body)

    def test_top_level_schema_errors_never_use_network(self):
        cases = [None, [], "not an object", {}, {"state": PRIVATE_INPUT}]
        for field in ("state", "questions", "model"):
            body = valid_body()
            del body[field]
            cases.append(body)
        for field, value in (
            ("questions", {}), ("questions", []), ("questions", None),
            ("model", None), ("model", 1), ("model", ""), ("model", "drex-"),
            ("model", "other-model"), ("model", "drex-x/path"),
            ("model", "drex-x\n"), ("requests", []), ("url", "https://example.invalid"),
        ):
            body = valid_body()
            body[field] = value
            cases.append(body)
        for index, body in enumerate(cases):
            with self.subTest(case=index):
                self.assert_invalid_body(body)

    def test_question_schema_errors_never_use_network(self):
        invalid_questions = [
            None, [], "bad", {}, {"type": "unknown"},
            {"type": "choice", "criteria": {}},
            {"type": "choice", "criteria": []},
            {"type": "choice", "criteria": {"a": 1}},
            {"type": "choice", "criteria": {"a": True}},
            {"type": "choice", "criteria": {"a": []}},
            {"type": "score", "criteria": []},
            {"type": "score", "criteria": {}},
            {"type": "score", "criteria": [None]},
            {"type": "score", "criteria": [1]},
            {"type": "noul"},
            {"type": "noul", "instructions": "  "},
            {"type": "noul", "criteria": {"true": None, "false": " "}},
            {"type": "noul", "instructions": "Decide", "criteria": []},
            {"type": "noul", "criteria": {"yes": "Yes"}},
            {"type": "noul", "criteria": {"true": False}},
            {"type": "noul", "instructions": 1},
            {"type": "choice", "criteria": {"a": None}, "instructions": None},
        ]
        for index, question in enumerate(invalid_questions):
            with self.subTest(case=index):
                body = valid_body()
                body["questions"] = {"test": question}
                self.assert_invalid_body(body)
        for name in ("", " \t\n"):
            with self.subTest(empty_id=repr(name)):
                body = valid_body()
                body["questions"] = {name: {"type": "score", "criteria": ["low"]}}
                self.assert_invalid_body(body)

    def test_non_string_question_id_rejected_before_encoding(self):
        body = valid_body()
        body["questions"] = {7: {"type": "score", "criteria": ["low"]}}
        with self.assertRaises(drex.HelperError):
            drex.encode_request(body)
        self.network.assert_not_called()

    def test_question_count_limits(self):
        body = valid_body()
        question = {"type": "score", "criteria": ["low"]}
        for count in (1, 512):
            body["questions"] = {str(i): question for i in range(count)}
            self.assertEqual(len(json.loads(drex.encode_request(body))["questions"]), count)
        body["questions"]["512"] = question
        self.assert_invalid_body(body)

    def test_nonfinite_values_do_not_reach_network(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=repr(value)):
                body = valid_body()
                body["state"] = {"private": PRIVATE_INPUT, "invalid": value}
                self.assert_invalid_body(body)

    def test_nonserializable_and_circular_state_redacted(self):
        circular = []
        circular.append(circular)
        for value in (set([PRIVATE_INPUT]), object(), circular):
            body = valid_body()
            body["state"] = value
            with self.assertRaises(drex.HelperError) as caught:
                drex.encode_request(body)
            self.assert_private(str(caught.exception))
        self.network.assert_not_called()

    def counted_bytes(self, body):
        payload = {"state": body["state"], "questions": body["questions"]}
        return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

    def test_encoded_request_limit_counts_state_and_questions_only(self):
        body = valid_body()
        body["state"] = ""
        body["state"] = "x" * (drex.REQUEST_LIMIT - self.counted_bytes(body))
        encoded = drex.encode_request(body)
        self.assertEqual(self.counted_bytes(body), drex.REQUEST_LIMIT)
        self.assertGreater(len(encoded), drex.REQUEST_LIMIT)
        os.environ["DREX_API_KEY"] = SYNTHETIC_KEY
        self.allow_response(valid_response())
        code, stdout, stderr = self.invoke(["judge"], body=body)
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(json.loads(stdout)["request_id"], valid_response()["request_id"])
        body["state"] += "x"
        self.network.reset_mock()
        self.network.side_effect = AssertionError("Unexpected HTTP attempt in offline test")
        self.assert_failure(self.invoke(["judge"], body=body))
        self.network.assert_not_called()

    def test_limit_counts_compact_utf8_not_escaped_or_indented_input(self):
        # Drex measures compact UTF-8. The live API accepted a 1.27 MB escaped, 436 KB UTF-8 body.
        body = valid_body()
        body["state"] = "é😀" * (drex.REQUEST_LIMIT // 16)
        self.assertGreater(len(json.dumps(body).encode("utf-8")), drex.REQUEST_LIMIT)
        raw = json.dumps(body, indent=4).encode("utf-8")
        self.assertGreater(len(raw), drex.REQUEST_LIMIT)
        encoded = drex.encode_request(json.loads(raw))
        self.assertLess(len(encoded), drex.REQUEST_LIMIT)
        self.assertIn("é😀".encode("utf-8"), encoded)
        self.assertNotIn(b"\\u", encoded)
        self.assertNotIn(b": ", encoded)
        os.environ["DREX_API_KEY"] = SYNTHETIC_KEY
        self.allow_response(valid_response())
        code, _, stderr = self.invoke(["judge"], raw=raw)
        self.assertEqual((code, stderr), (0, ""))

    def test_invalid_json_and_invalid_utf8_stdin_do_not_leak_or_use_network(self):
        for raw in (b"", PRIVATE_INPUT.encode(), b'{"private":"' +
                    SYNTHETIC_KEY.encode(), b"\xff" + PRIVATE_INPUT.encode()):
            with self.subTest(length=len(raw)):
                self.assert_failure(self.invoke(["judge"], raw=raw))
        self.network.assert_not_called()
        self.prompt.assert_not_called()

    def test_missing_file_and_malformed_file_errors_hide_path_and_input(self):
        filename = self.folder / (PRIVATE_INPUT + ".json")
        stderr = self.assert_failure(self.invoke(["judge", "--input", str(filename)]))
        self.assertIn("not found", stderr)
        self.assertNotIn(PRIVATE_INPUT, stderr)
        filename.write_text(PRIVATE_INPUT + SYNTHETIC_KEY, encoding="utf-8")
        stderr = self.assert_failure(self.invoke(["judge", "--input", str(filename)]))
        self.assertNotIn("not found", stderr)
        self.network.assert_not_called()

    def test_load_body_accepts_file_with_spaces(self):
        filename = self.folder / "request with spaces.json"
        filename.write_text(json.dumps(valid_body()), encoding="utf-8")
        self.assertEqual(drex.load_body(str(filename)), valid_body())

    def test_raw_input_limit_for_file_and_stdin(self):
        read_limit = drex.INPUT_LIMIT
        exact = b"0" + b" " * (drex.INPUT_LIMIT - 1)
        self.stdin.buffer = io.BytesIO(exact)
        self.assertEqual(drex.load_body("-"), 0)
        filename = self.folder / "large.json"
        filename.write_bytes(exact)
        self.assertEqual(drex.load_body(str(filename)), 0)
        for source in ("-", str(filename)):
            with self.subTest(source="stdin" if source == "-" else "file"):
                oversized = exact + b" " * 50
                filename.write_bytes(oversized)
                self.stdin.buffer = io.BytesIO(oversized)
                with self.assertRaisesRegex(drex.HelperError, "4 MiB"):
                    drex.load_body(source)
                if source == "-":
                    self.assertEqual(self.stdin.buffer.tell(), read_limit + 1)
        self.network.assert_not_called()

    def test_documented_state_shapes_and_score_minimum(self):
        states = ("", "plain text", "状态 café 😀", {"ticket": "T-1", "note": "😀"},
                  ["Refund please", "Where is my order?"], None, 0, 1.5, True, False)
        for index, state in enumerate(states):
            with self.subTest(case=index):
                body = valid_body()
                body["state"] = state
                self.assertEqual(json.loads(drex.encode_request(body))["state"], state)
        body = valid_body()
        body["questions"] = {
            "only": {"type": "score", "criteria": ["only"]},
            "label": {"type": "choice", "criteria": {"other": None}},
            "safe": {"type": "noul", "criteria": {"true": "Yes", "note": "ignored by Drex"}},
        }
        self.assertEqual(json.loads(drex.encode_request(body))["questions"], body["questions"])
        body["questions"] = {"safe": {"type": "noul", "criteria": {"note": "not a real criterion"}}}
        self.assert_invalid_body(body)
        body = valid_body()
        body["questions"] = {"empty": {"type": "score", "criteria": []}}
        self.assert_invalid_body(body)

    def test_empty_stdin_is_rejected_without_traceback(self):
        stderr = self.assert_failure(self.invoke(["judge"], raw=b""))
        self.assertIn("valid JSON", stderr)
        self.network.assert_not_called()


class TransportAndCheckTests(OfflineTestCase):
    def test_check_uses_only_fixed_get_models_and_does_not_echo_catalog(self):
        os.environ["DREX_API_KEY"] = SYNTHETIC_KEY
        os.environ["HTTP_PROXY"] = "http://example.invalid:8080"
        os.environ["HTTPS_PROXY"] = "https://example.invalid/proxy"
        os.environ["ALL_PROXY"] = "socks5://example.invalid"
        os.environ["NO_PROXY"] = "*"
        opener, response = self.allow_response({"models": [PRIVATE_SERVER, SYNTHETIC_KEY]})
        code, stdout, stderr = self.invoke(["check"])
        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("No inference request made", stdout)
        self.assertIn("credit availability was not checked", stdout)
        self.assert_private(stdout)
        opener.open.assert_called_once()
        req = opener.open.call_args.args[0]
        self.assertEqual(req.full_url, "https://drex.nace.ai/v1/models")
        self.assertEqual(req.get_method(), "GET")
        self.assertIsNone(req.data)
        self.assertEqual(req.get_header("Authorization"), "Bearer " + SYNTHETIC_KEY)
        self.assertEqual(req.get_header("Accept"), "application/json")
        self.assertEqual(opener.open.call_args.kwargs, {"timeout": 65})
        response.read.assert_called_once_with(drex.RESPONSE_LIMIT + 1)
        proxy, redirect = self.network.call_args.args
        self.assertIsInstance(proxy, urllib.request.ProxyHandler)
        self.assertEqual(proxy.proxies, {})
        self.assertIsInstance(redirect, drex.NoRedirect)
        self.prompt.assert_not_called()
        self.child.assert_not_called()

    def test_check_no_input_never_prompts_even_with_terminal(self):
        self.stdin.isatty.return_value = True
        self.assert_failure(self.invoke(["check", "--no-input"]))
        self.prompt.assert_not_called()
        self.network.assert_not_called()

    def test_check_can_use_hidden_prompt_but_does_not_persist(self):
        self.stdin.isatty.return_value = True
        self.prompt.side_effect = None
        self.prompt.return_value = SYNTHETIC_KEY
        self.allow_response({"models": []})
        code, stdout, stderr = self.invoke(["check"])
        self.assertEqual((code, stderr), (0, ""))
        self.assert_private(stdout)
        self.assertNotIn("DREX_API_KEY", os.environ)
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_malformed_catalog_is_rejected_without_echo(self):
        os.environ["DREX_API_KEY"] = SYNTHETIC_KEY
        for catalog in (None, [], {}, {"models": PRIVATE_SERVER}, {"models": None}):
            with self.subTest(catalog_type=type(catalog).__name__):
                self.allow_response(catalog)
                self.assert_failure(self.invoke(["check"]))

    def test_redirect_handler_refuses_every_redirect_even_same_origin(self):
        handler = drex.NoRedirect()
        req = urllib.request.Request(drex.BASE_URL + "/v1/models")
        for status in (301, 302, 303, 307, 308):
            for target in ("https://example.invalid/steal", drex.BASE_URL + "/other",
                           "http://drex.nace.ai/plaintext"):
                with self.subTest(status=status, target=target):
                    self.assertIsNone(handler.redirect_request(req, None, status, "redirect", {}, target))
        self.network.assert_not_called()

    def test_http_errors_and_redirects_redact_url_reason_body_and_key(self):
        os.environ["DREX_API_KEY"] = SYNTHETIC_KEY
        expected = {400: "malformed", 401: "Authentication failed",
                    402: "insufficient credit", 403: "refused access",
                    404: "could not find", 408: "request timed out",
                    413: "too large", 422: "Do not retry unchanged",
                    429: "rate limit", 500: "bounded policy",
                    503: "temporarily unavailable", 504: "gateway timed out",
                    529: "unavailable"}
        for status in (301, 302, 303, 307, 308, 400, 401, 402, 403, 404, 408,
                       413, 422, 429, 500, 502, 503, 504, 529):
            with self.subTest(status=status):
                raw = io.BytesIO((PRIVATE_SERVER + PRIVATE_INPUT + SYNTHETIC_KEY).encode())
                error = urllib.error.HTTPError(
                    "https://example.invalid/" + SYNTHETIC_KEY, status,
                    PRIVATE_SERVER + SYNTHETIC_KEY, {"Location": PRIVATE_INPUT}, raw,
                )
                opener, _ = self.allow_response(error=error)
                opener.open.reset_mock()
                stderr = self.assert_failure(self.invoke(["check"]))
                self.assertIn(expected.get(status, "unexpected HTTP status"), stderr)
                opener.open.assert_called_once()  # No retry or alternative provider.
                self.assertEqual(raw.tell(), 0)  # Never read/print the error body.
                error.close()

    def test_connection_and_read_failures_are_sanitized(self):
        os.environ["DREX_API_KEY"] = SYNTHETIC_KEY
        for cls in (urllib.error.URLError, OSError, TimeoutError, ValueError):
            with self.subTest(exception=cls.__name__):
                error = cls(PRIVATE_SERVER + PRIVATE_INPUT + SYNTHETIC_KEY)
                opener, _ = self.allow_response(error=error)
                opener.open.reset_mock()
                stderr = self.assert_failure(self.invoke(["check"]))
                self.assertIn("No alternative provider was called", stderr)
                opener.open.assert_called_once()
        opener, response = self.allow_response({"models": []})
        response.read.side_effect = OSError(PRIVATE_SERVER + SYNTHETIC_KEY)
        self.assert_failure(self.invoke(["check"]))

    def test_http_protocol_errors_and_partial_response_body_are_redacted(self):
        os.environ["DREX_API_KEY"] = SYNTHETIC_KEY
        secret = PRIVATE_SERVER + PRIVATE_INPUT + SYNTHETIC_KEY
        for error in (http.client.HTTPException(secret),
                      http.client.BadStatusLine(secret),
                      http.client.IncompleteRead(secret.encode(), 100)):
            with self.subTest(exception=type(error).__name__):
                _, response = self.allow_response({"models": []})
                response.read.side_effect = error
                self.assert_failure(self.invoke(["check"]))

    def test_invalid_response_json_and_utf8_redacted(self):
        for raw in (b"", b"not-json" + PRIVATE_SERVER.encode(),
                    b'{"secret":"' + SYNTHETIC_KEY.encode(), b"\xff\xfe"):
            with self.subTest(length=len(raw)):
                self.allow_response(raw=raw)
                with self.assertRaises(drex.HelperError) as caught:
                    drex.request(SYNTHETIC_KEY, "/v1/models")
                self.assertIn("invalid JSON", str(caught.exception))
                self.assert_private(str(caught.exception))

    def test_response_limit_is_inclusive_and_read_is_bounded(self):
        # The production limit is also pinned; a small patched limit makes
        # boundary testing cheap while checking the exact same code path.
        self.assertEqual(drex.RESPONSE_LIMIT, 8 * 1048576)
        self.assertEqual(drex.REQUEST_LIMIT, 1048576)
        with mock.patch.object(drex, "RESPONSE_LIMIT", 32):
            _, response = self.allow_response(raw=b"0" + b" " * 31)
            self.assertEqual(drex.request(SYNTHETIC_KEY, "/v1/models"), 0)
            response.read.assert_called_with(33)
            self.allow_response(raw=b"0" + b" " * 32)
            with self.assertRaisesRegex(drex.HelperError, "size limit"):
                drex.request(SYNTHETIC_KEY, "/v1/models")


class JudgeAndResponseTests(OfflineTestCase):
    def test_valid_judge_posts_expected_schema_to_fixed_endpoint(self):
        os.environ["DREX_API_KEY"] = SYNTHETIC_KEY
        os.environ["DREX_BASE_URL"] = "https://example.invalid/ignored"
        os.environ["OPENAI_BASE_URL"] = "https://example.invalid/also-ignored"
        result = valid_response()
        opener, _ = self.allow_response(result)
        code, stdout, stderr = self.invoke(["judge"], body=valid_body())
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(json.loads(stdout), result)
        req = opener.open.call_args.args[0]
        self.assertEqual(req.full_url, "https://drex.nace.ai/v1/systemone")
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.get_header("Content-type"), "application/json")
        self.assertEqual(json.loads(req.data), valid_body())
        self.assertEqual(req.get_header("Authorization"), "Bearer " + SYNTHETIC_KEY)
        opener.open.assert_called_once()
        self.prompt.assert_not_called()
        self.child.assert_not_called()
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_unknown_response_fields_are_accepted(self):
        os.environ["DREX_API_KEY"] = SYNTHETIC_KEY
        result = valid_response()
        result["region"] = "synthetic-region"
        result["answers"]["quality"]["note"] = "synthetic-note"
        self.allow_response(result)
        code, stdout, stderr = self.invoke(["judge"], body=valid_body())
        self.assertEqual((code, stderr), (0, ""))
        parsed = json.loads(stdout)
        self.assertEqual(parsed["region"], "synthetic-region")
        self.assertEqual(parsed["answers"]["quality"]["note"], "synthetic-note")

    def test_score_legend_that_differs_from_criteria_is_rejected(self):
        os.environ["DREX_API_KEY"] = SYNTHETIC_KEY
        result = valid_response()
        result["answers"]["quality"]["legend"] = [PRIVATE_SERVER, "medium", "high"]
        self.allow_response(result)
        stderr = self.assert_failure(self.invoke(["judge"], body=valid_body()))
        self.assertIn("no decision should be consumed", stderr)

    def test_server_nan_is_rejected_without_traceback(self):
        os.environ["DREX_API_KEY"] = SYNTHETIC_KEY
        result = valid_response()
        result["answers"]["quality"]["score"] = float("nan")
        self.allow_response(result)
        stderr = self.assert_failure(self.invoke(["judge"], body=valid_body()))
        self.assertNotIn("nan", stderr.lower())

    def test_successful_response_exact_key_echo_is_redacted_everywhere(self):
        os.environ["DREX_API_KEY"] = SYNTHETIC_KEY
        result = valid_response()
        result["extra_text"] = "before-" + SYNTHETIC_KEY + "-after"
        result["extra"] = {SYNTHETIC_KEY: [SYNTHETIC_KEY, "nested " + SYNTHETIC_KEY]}
        self.allow_response(result)
        code, stdout, stderr = self.invoke(["judge"], body=valid_body())
        self.assertEqual((code, stderr), (0, ""))
        self.assertNotIn(SYNTHETIC_KEY, stdout)
        self.assertEqual(stdout.count("[REDACTED]"), 4)
        self.assertEqual(json.loads(stdout)["extra_text"], "before-[REDACTED]-after")

    def test_valid_response_model_alias_and_numeric_boundaries(self):
        body = valid_body()
        result = valid_response()
        self.assertNotEqual(result["model"], body["model"])
        self.assertIsNone(drex.validate_response(result, body))
        for value in (0, 1, 0.0, 1.0):
            result["answers"]["safe"]["noul"] = value
            result["answers"]["route"]["confidence"] = value
            self.assertIsNone(drex.validate_response(result, body))
        for score in (0, 2):
            result["answers"]["quality"]["score"] = score
            self.assertIsNone(drex.validate_response(result, body))

    def test_missing_response_fields_and_wrong_envelope_rejected(self):
        cases = [None, [], "invalid", {}, {"error": PRIVATE_SERVER + SYNTHETIC_KEY}]
        for field in ("model", "answers", "usage", "evaluation_time_ms", "request_id"):
            result = valid_response()
            del result[field]
            cases.append(result)
        for value in (None, [], "not-drex", 1):
            result = valid_response()
            result["model"] = value
            cases.append(result)
        for index, result in enumerate(cases):
            with self.subTest(case=index):
                with self.assertRaises(drex.HelperError) as caught:
                    drex.validate_response(result, valid_body())
                self.assert_private(str(caught.exception))

    def test_answer_ids_definitions_types_and_probability_keys_rejected(self):
        mutations = [
            lambda r: r.update(answers=[]),
            lambda r: r["answers"].pop("route"),
            lambda r: r["answers"].update(extra={}),
            lambda r: r["answers"].update(route=None),
            lambda r: r["answers"]["route"].update(type="score"),
            lambda r: r["answers"]["safe"].pop("noul"),
            lambda r: r["answers"]["route"].pop("probabilities"),
            lambda r: r["answers"]["route"].update(probabilities=[]),
            lambda r: r["answers"]["route"].update(probabilities={"accept": 1}),
            lambda r: r["answers"]["route"]["probabilities"].update(extra=0),
            lambda r: r["answers"]["route"].update(choice="unknown"),
            lambda r: r["answers"]["route"].update(choice=1),
            lambda r: r["answers"]["route"].pop("confidence"),
            lambda r: r["answers"]["quality"].update(probabilities={"low": 1}),
            lambda r: r["answers"]["quality"].update(legend={"0": "low"}),
            lambda r: r["answers"]["quality"].update(legend=["high", "medium", "low"]),
            lambda r: r["answers"]["quality"].pop("score"),
            lambda r: r["answers"]["quality"].pop("confidence"),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(case=index):
                result = valid_response()
                mutate(result)
                with self.assertRaises(drex.HelperError):
                    drex.validate_response(result, valid_body())

    def test_invalid_numeric_answers_rejected_without_bool_coercion(self):
        fields = [("safe", "noul"), ("route", "confidence"),
                  ("quality", "confidence"), ("quality", "score")]
        values = (None, "0.5", True, False, [], {}, -0.01, 3,
                  float("nan"), float("inf"), float("-inf"))
        for question, field in fields:
            for value in values:
                with self.subTest(question=question, field=field, value=repr(value)):
                    result = valid_response()
                    result["answers"][question][field] = value
                    with self.assertRaises(drex.HelperError):
                        drex.validate_response(result, valid_body())
        for question, criterion in (("route", "accept"), ("quality", "0")):
            for value in values + (1.01,):
                with self.subTest(question=question, probability=repr(value)):
                    result = valid_response()
                    result["answers"][question]["probabilities"][criterion] = value
                    with self.assertRaises(drex.HelperError):
                        drex.validate_response(result, valid_body())

    def test_malformed_judge_response_never_prints_server_content(self):
        os.environ["DREX_API_KEY"] = SYNTHETIC_KEY
        result = valid_response()
        result["answers"]["route"]["choice"] = PRIVATE_SERVER + SYNTHETIC_KEY
        result["extra"] = PRIVATE_INPUT
        self.allow_response(result)
        stderr = self.assert_failure(self.invoke(["judge"], body=valid_body()))
        self.assertIn("no decision should be consumed", stderr)

    def test_unserializable_response_and_generic_data_errors_are_sanitized(self):
        os.environ["DREX_API_KEY"] = SYNTHETIC_KEY
        result = valid_response()
        result["extra"] = float("nan")
        self.allow_response(result)
        self.assert_failure(self.invoke(["judge"], body=valid_body()))
        for cls in (ValueError, TypeError, RecursionError):
            with self.subTest(exception=cls.__name__):
                with mock.patch.object(drex, "load_body", side_effect=cls(
                        PRIVATE_SERVER + PRIVATE_INPUT + SYNTHETIC_KEY)):
                    self.assert_failure(self.invoke(["judge"]))

    def test_regression_oversized_response_integer_should_fail_cleanly(self):
        """An enormous JSON integer must not escape as an OverflowError."""
        os.environ["DREX_API_KEY"] = SYNTHETIC_KEY
        result = valid_response()
        result["answers"]["safe"]["noul"] = 10 ** 400
        self.allow_response(result)
        self.assert_failure(self.invoke(["judge"], body=valid_body()))

    def test_malformed_metadata_fields_rejected(self):
        cases = []
        for field, values in (
            ("request_id", (None, 1, "", "req_short", "req_" + "A" * 32,
                            "req_" + "0" * 31, "req_" + "0" * 33)),
            ("evaluation_time_ms", (None, True, "12", -1, float("nan"),
                                    float("inf"), 10 ** 400)),
            ("usage", (None, [], {}, {"input_tokens": 0})),
        ):
            for value in values:
                cases.append((field, value))
        for field in ("input_tokens", "output_tokens"):
            for value in (None, True, -1, 1.5, "1"):
                usage = {"input_tokens": 0, "output_tokens": 0}
                usage[field] = value
                cases.append(("usage", usage))
        for index, (field, value) in enumerate(cases):
            with self.subTest(case=index, field=field):
                result = valid_response()
                result[field] = value
                with self.assertRaises(drex.HelperError):
                    drex.validate_response(result, valid_body())

    def test_regression_null_metadata_should_not_be_accepted(self):
        """Required usage/timing/request ID must be more than presence checks."""
        result = valid_response()
        result.update(usage=None, evaluation_time_ms=None, request_id=None)
        with self.assertRaises(drex.HelperError):
            drex.validate_response(result, valid_body())

    def test_regression_bare_model_prefix_should_not_be_accepted(self):
        """Response and request both require an actual model ID, not 'drex-'."""
        result = valid_response()
        result["model"] = "drex-"
        with self.assertRaises(drex.HelperError):
            drex.validate_response(result, valid_body())


def sample_catalog():
    return {
        "models": [
            {
                "name": "drex-v1.0",
                "description": "Pinned model.\nStates up to 131,072 tokens.",
                "release_date": "2026-09-24",
                "alias_for": None,
                "tier": PRIVATE_SERVER,
            },
            {
                "name": "drex-latest",
                "description": "Points to drex-v2.0. " + SYNTHETIC_KEY,
                "release_date": "2026-10-06",
                "alias_for": "drex-v2.0",
            },
        ],
        "request_id": "req_" + "ab" * 16,
        "note": SYNTHETIC_KEY,
    }


class ModelsCommandTests(OfflineTestCase):
    def test_models_lists_catalog_without_inference_or_secrets(self):
        os.environ["DREX_API_KEY"] = SYNTHETIC_KEY + "\n"
        os.environ["HTTPS_PROXY"] = "https://example.invalid/proxy"
        opener, response = self.allow_response(sample_catalog())
        code, stdout, stderr = self.invoke(["models", "--no-input"])
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(stdout.splitlines(), [
            "drex-v1.0  2026-09-24  Pinned model. States up to 131,072 tokens.",
            "drex-latest -> drex-v2.0  2026-10-06  Points to drex-v2.0. [REDACTED]",
        ])
        self.assert_private(stdout)
        self.assertNotIn(PRIVATE_SERVER, stdout)
        req = opener.open.call_args.args[0]
        self.assertEqual(req.full_url, "https://drex.nace.ai/v1/models")
        self.assertEqual(req.get_method(), "GET")
        self.assertIsNone(req.data)
        self.assertEqual(req.get_header("Authorization"), "Bearer " + SYNTHETIC_KEY)
        proxy, redirect = self.network.call_args.args
        self.assertEqual(proxy.proxies, {})
        self.assertIsInstance(redirect, drex.NoRedirect)
        response.read.assert_called_once_with(drex.RESPONSE_LIMIT + 1)
        self.prompt.assert_not_called()
        self.child.assert_not_called()

    def test_models_accepts_extra_fields_and_an_empty_list(self):
        os.environ["DREX_API_KEY"] = SYNTHETIC_KEY
        payload = sample_catalog()
        del payload["request_id"]
        self.allow_response(payload)
        code, stdout, stderr = self.invoke(["models"])
        self.assertEqual(code, 0, stderr)
        self.assertEqual(len(stdout.splitlines()), 2)
        self.allow_response({"models": [], "unrelated": {"secret": SYNTHETIC_KEY}})
        code, stdout, stderr = self.invoke(["models", "--no-input"])
        self.assertEqual((code, stdout, stderr), (0, "", ""))

    def test_models_missing_list_and_bad_entries_are_not_echoed(self):
        os.environ["DREX_API_KEY"] = SYNTHETIC_KEY
        for catalog in (None, [], {}, {"request_id": SYNTHETIC_KEY}, "models"):
            with self.subTest(catalog_type=type(catalog).__name__):
                self.allow_response(catalog)
                stderr = self.assert_failure(self.invoke(["models", "--no-input"]))
                self.assertIn("missing the models list", stderr)
        bad = sample_catalog()
        bad["models"] = {"name": SYNTHETIC_KEY}
        self.allow_response(bad)
        stderr = self.assert_failure(self.invoke(["models", "--no-input"]))
        self.assertIn("unexpected model catalog", stderr)
        sparse = sample_catalog()
        sparse["models"] = [
            {"name": "drex-v1.0", "description": "Line one\nline two " + SYNTHETIC_KEY},
            {"name": "drex-v9", "alias_for": None, "release_date": None, "description": 5},
        ]
        self.allow_response(sparse)
        code, stdout, stderr = self.invoke(["models", "--no-input"])
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(stdout.splitlines(), ["drex-v1.0  Line one line two [REDACTED]", "drex-v9"])
        bad["models"] = [{
            "name": " ",
            "description": PRIVATE_INPUT,
            "release_date": "2026-09-24",
            "alias_for": "",
        }]
        self.allow_response(bad)
        self.assert_failure(self.invoke(["models", "--no-input"]))

    def test_models_no_input_never_prompts_and_prompt_is_not_saved(self):
        self.stdin.isatty.return_value = True
        self.assert_failure(self.invoke(["models", "--no-input"]))
        self.prompt.assert_not_called()
        self.network.assert_not_called()
        self.prompt.side_effect = None
        self.prompt.return_value = SYNTHETIC_KEY
        self.allow_response({"models": []})
        code, stdout, stderr = self.invoke(["models"])
        self.assertEqual((code, stdout, stderr), (0, "", ""))
        self.assertNotIn("DREX_API_KEY", os.environ)
        self.prompt.assert_called_once()


class CliHelpTests(OfflineTestCase):
    def test_real_subprocess_help_is_local_and_requires_no_credentials(self):
        # Do not use the patched subprocess entry point: these are the only real
        # child processes in this suite and can only run argparse --help.
        for args in (["--help"], ["run", "--help"], ["check", "--help"],
                     ["models", "--help"], ["judge", "--help"]):
            with self.subTest(args=args):
                result = REAL_SUBPROCESS_RUN(
                    [sys.executable, "-B", str(SCRIPT)] + args,
                    cwd=self.folder, env=dict(os.environ), input="",
                    text=True, capture_output=True, timeout=5,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, "")
                self.assertIn("usage:", result.stdout)
                self.assert_private(result.stdout)
        self.assertEqual(list(self.folder.iterdir()), [])
        self.network.assert_not_called()
        self.child.assert_not_called()


if __name__ == "__main__":
    unittest.main()
