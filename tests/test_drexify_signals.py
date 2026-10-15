"""Offline tests for the drexify scan's fast signal search and wrapper learning."""
import importlib.util
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "drexify" / "scripts" / "drexify.py"
_spec = importlib.util.spec_from_file_location("drexify_signals_under_test", SCRIPT)
drexify = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(drexify)

TRICKY = [
    "", "\n", "x = 1\n",
    "client.chat.completions.create(model='m')\n",
    "CLIENT.CHAT.COMPLETIONS.CREATE(MODEL='M')\n",
    "reſponses.create(x)\n",  # long s folds to s under ignore-case
    "\u212aeyword = 1\nreturn any(w in t for w in WORDS)\n",  # Kelvin sign folds to k
    "R\u0130SK = classify\nmy_llm.invoke(x)\n",  # dotted capital I folds to i
    "def classify_ticket(t):\n    return 'a' if 'refund' in t.lower() else 'b'\n",
    "import { generateText } from 'ai'\nawait generateText({ model })\n",
    "fetch(`${BASE}/chat/completions`, {})\n",
    "const URL = 'https://api.openai.com/v1'\n",
    "if strings.EqualFold(a, b) {}\n",
    "$x = stripos($text, 'refund');\n",
]


def corpus():
    sources = [SCRIPT, ROOT / "tests" / "test_drexify_script.py", ROOT / "skills" / "drexify" / "SKILL.md",
               ROOT / "skills" / "drex-for-harness" / "SKILL.md", ROOT / "scripts" / "drex.py"]
    return list(TRICKY) + [path.read_text(encoding="utf-8") for path in sources]


class EverySignal:
    def search(self, text, folded):
        return True


class FastSearchTests(unittest.TestCase):
    def test_every_non_ascii_letter_that_folds_to_ascii_is_in_the_fold_table(self):
        ascii_letter = re.compile("[a-z]", re.I)
        folding = {chr(c) for c in range(128, 0x110000) if ascii_letter.fullmatch(chr(c))}
        table = {chr(k) for k in drexify.ASCII_FOLDS}
        self.assertLessEqual(folding, table)

    def test_every_signal_part_has_a_literal_prefilter(self):
        self.assertEqual([p.regex.pattern for p in drexify.ANY_SIGNAL_PARTS if not p.needles], [])

    def test_prefiltered_search_agrees_with_the_plain_regex(self):
        parts = list(drexify.ANY_SIGNAL_PARTS) + [p for _, _, ps in drexify.SIGNALS_IN_TEXT for p in ps]
        for text in corpus():
            folded = drexify.folded_text(text)
            for part in parts:
                self.assertEqual(bool(part.search(text, folded)), bool(part.regex.search(text)),
                                 (part.regex.pattern[:80], text[:80]))

    def test_any_signal_agrees_with_one_alternation(self):
        combined = re.compile("|".join(f"(?:{p.pattern})" for _, p in drexify.SIGNALS), re.I | re.M)
        for text in corpus():
            self.assertEqual(drexify.any_signal(text), bool(combined.search(text)), text[:80])

    def test_line_hits_match_the_per_line_search_without_the_file_filter(self):
        unfiltered = tuple((kind, pattern, [EverySignal()]) for kind, pattern, _ in drexify.SIGNALS_IN_TEXT)
        for text in corpus():
            got = drexify.line_hits(text)
            with mock.patch.object(drexify, "SIGNALS_IN_TEXT", unfiltered):
                self.assertEqual(got, drexify.line_hits(text), text[:80])

    def test_literal_options_cover_alternations_and_skip_assertions(self):
        parse = drexify.RE_PARSER.parse
        self.assertEqual(drexify.literal_options(parse(r"\bfoo\.bar\(", 0)), {"foo.bar("})
        self.assertEqual(drexify.literal_options(parse(r"\b(?:alpha|beta)_x", 0)), {"alpha", "beta"})
        self.assertIsNone(drexify.literal_options(parse(r"\b(?:ab|cdef)\s", 0)))
        self.assertEqual(drexify.literal_options(parse(r"(?<!\w)Messages\.create", re.I)), {"messages.create"})


class WrapperTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="drexify wrappers ")
        self.repo = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, files):
        for rel, text in files.items():
            path = self.repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)

    def candidates(self):
        result = drexify.scan(self.repo)
        return {(f["path"], fn["name"]): fn["kinds"] for a in result["areas"].values() for f in a["files"]
                for fn in f["functions"]}, result["wrappers"]

    def test_short_python_wrapper_is_matched_through_its_module(self):
        self.write({
            "app/llm.py": "from openai import OpenAI\n\ndef ask(system, user):\n"
                          "    return OpenAI().chat.completions.create(model='m', messages=[])\n",
            "app/urgency.py": "from app import llm\n\ndef rate_urgency(text):\n    return int(llm.ask('Rate it', text))\n",
            "app/other.py": "def ask(question):\n    return input(question)\n\ndef greet():\n    return ask('name?')\n",
        })
        found, wrappers = self.candidates()
        self.assertIn("llm.ask", wrappers)
        self.assertIn("wrapper-call", found[("app/urgency.py", "rate_urgency")])
        self.assertNotIn(("app/other.py", "greet"), found)

    def test_raw_http_client_is_a_model_client_and_named_imports_are_followed(self):
        self.write({
            "src/openai.js": "const BASE = 'https://api.openai.com/v1';\n"
                             "export async function chat(system, user) {\n"
                             "  return post('/chat/completions', { system, user });\n}\n"
                             "export async function moderate(text) {\n  return post('/moderations', { input: text });\n}\n",
            "src/topics.js": "import { chat } from './openai.js';\n"
                             "export async function pickCategory(title) {\n  return chat('Pick one', title);\n}\n",
            "src/mod.js": "import { moderate as screen } from './openai';\n"
                          "export async function checkPost(text) {\n  return screen(text);\n}\n",
            "src/ns.js": "import * as ai from './openai.js';\n"
                         "export async function tagPost(text) {\n  return ai.chat('Tag', text);\n}\n",
            "src/cjs.js": "const { chat } = require('./openai');\n"
                          "async function triage(text) {\n  return chat('Triage', text);\n}\nmodule.exports = { triage };\n",
            "src/unrelated.js": "import { chat } from './chatroom.js';\n"
                                "export function sendMessage(text) {\n  return chat(text);\n}\n",
        })
        found, wrappers = self.candidates()
        self.assertIn("openai.chat", wrappers)
        for key in [("src/topics.js", "pickCategory"), ("src/mod.js", "checkPost"), ("src/ns.js", "tagPost"),
                    ("src/cjs.js", "triage")]:
            self.assertIn("wrapper-call", found.get(key, []), key)
        self.assertNotIn(("src/unrelated.js", "sendMessage"), found)

    def test_lowercased_variable_keyword_guard_is_a_word_guard(self):
        self.write({"app/spam.py": "PHRASES = ('buy now', 'free money')\n\ndef is_spam(text):\n"
                                   "    lowered = text.lower()\n    return any(p in lowered for p in PHRASES)\n",
                    "app/far.py": "def is_far(text):\n    lowered = text.lower()\n" + "    x = 1\n" * 8 +
                                  "    return any(p in lowered for p in WORDS)\n"})
        found, _ = self.candidates()
        self.assertIn("word-guard", found[("app/spam.py", "is_spam")])
        self.assertNotIn("word-guard", found.get(("app/far.py", "is_far"), []))


if __name__ == "__main__":
    unittest.main()
