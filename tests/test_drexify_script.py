"""Offline tests for skills/drexify/scripts/drexify.py. No git, network, or model calls required."""
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import time
from contextlib import redirect_stdout
from unittest import mock
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "drexify" / "scripts" / "drexify.py"
_spec = importlib.util.spec_from_file_location("drexify_under_test", SCRIPT)
drexify = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(drexify)

FILES = {
    "services/billing/app/match.py": "import openai\n\ndef match_contract(x):\n    return client.chat.completions.create(model='m')\n",
    "services/search/app/route.py": "def route_query(q):\n    return 'fact'\n",
    "services/search/app/drex_call.py": "URL = 'https://drex.nace.ai/v1/systemone'\n\ndef call_drex(x):\n    return post(URL, x)\n",
    "shared/core/a/classify.py": "from typing import Literal\nLabel = Literal['a', 'b']\n\ndef classify_doc(t):\n    pass\n",
    "shared/core/b/classify.py": "def classify_page(t):\n    pass\n",
    "services/billing/tests/test_match.py": "def match_contract_test():\n    client.chat.completions.create(model='m')\n",
    "node_modules/pkg/index.js": "function classifyThing() {}\n",
    "README.md": "classify everything\n",
}


class DrexifyScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="drexify test ")
        self.repo = Path(self.tmp.name) / "repo"
        for rel, text in FILES.items():
            path = self.repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)

    def tearDown(self):
        self.tmp.cleanup()

    def report(self, body):
        if not re.search(r"candidate\s+functions?", body, re.I):
            if body and not body.endswith("\n"):
                body += "\n"
            body += "Coverage: checked the candidate functions listed above.\n"
        path = Path(self.tmp.name) / "report.md"
        path.write_text(body)
        return path

    def test_scan_groups_by_area_and_skips_tests_and_vendored(self):
        result = drexify.scan(self.repo)
        self.assertEqual(set(result["areas"]), {"services/billing", "services/search", "shared"})
        paths = {f["path"] for a in result["areas"].values() for f in a["files"]}
        self.assertNotIn("services/billing/tests/test_match.py", paths)
        self.assertFalse(any(p.startswith("node_modules") for p in paths))
        match = next(f for f in result["areas"]["services/billing"]["files"] if f["path"].endswith("match.py"))
        self.assertEqual(match["kinds"], ["decision-name", "model-call", "model-import"])
        drex = next(f for f in result["areas"]["services/search"]["files"] if f["path"].endswith("drex_call.py"))
        self.assertEqual(drex["kinds"], ["drex"])
        self.assertIn("services/billing/tests/test_match.py",
                      {f["path"] for a in drexify.scan(self.repo, include_tests=True)["areas"].values() for f in a["files"]})

    def test_scan_balanced_groups_cover_every_area_once(self):
        groups = drexify.scan(self.repo, groups=2)["groups"]
        names = [a for g in groups for a in g["areas"]]
        self.assertEqual(sorted(names), sorted(set(names)))
        self.assertEqual(set(names), {"services/billing", "services/search", "shared"})

    def test_check_accepts_a_clean_report(self):
        path = self.report(
            "Your repo has been scanned. Identified 2 sites of drexification "
            "(1 already on Drex, 0 partial, 0 implemented now, 1 candidates). Below is the list of processes:\n\n"
            "- Search Drex call (`services/search/app/drex_call.py:3`): already on Drex.\n"
            "- Contract matching (`services/billing/app/match.py:3`): candidate, choice over contracts.\n")
        result = drexify.check(path, self.repo)
        self.assertEqual(result["problems"], [])
        self.assertEqual(result["statuses"]["candidate"], 1)

    def test_check_fixes_shortened_paths_only_with_fix(self):
        body = ("Identified 1 sites of drexification (0 already on Drex, 0 partial, 0 implemented now, 1 candidates)\n"
                "- Contract matching (`.../app/match.py:3`): candidate.\n")
        path = self.report(body)
        written = path.read_text()
        self.assertTrue(any("run with --fix" in p for p in drexify.check(path, self.repo)["problems"]))
        self.assertEqual(path.read_text(), written)
        result = drexify.check(path, self.repo, fix=True)
        self.assertEqual(result["problems"], [])
        self.assertIn("`services/billing/app/match.py:3`", path.read_text())

    def test_check_never_guesses_between_files_with_the_same_name(self):
        body = ("Identified 1 sites of drexification (0 already on Drex, 0 partial, 0 implemented now, 1 candidates)\n"
                "- Doc classify (`classify.py:4`): candidate.\n")
        path = self.report(body)
        written = path.read_text()
        result = drexify.check(path, self.repo, fix=True)
        self.assertTrue(any("ambiguous, matches 2 files" in p for p in result["problems"]))
        self.assertEqual(path.read_text(), written)

    def test_check_rejects_site_pointers_without_a_line(self):
        path = self.report("Identified 1 sites of drexification (0 already on Drex, 0 partial, 0 implemented now, 1 candidates)\n"
                           "- Route (`services/search/app/route.py`): candidate.\n")
        self.assertTrue(any("must be a full `path:line`" in p for p in drexify.check(path, self.repo)["problems"]))

    def test_check_ignores_hosts_versions_and_urls_in_notes(self):
        path = self.report("Identified 1 sites of drexification (0 already on Drex, 0 partial, 0 implemented now, 1 candidates)\n"
                           "- Route (`services/search/app/route.py:1`): candidate, server at `127.0.0.1:8000`, "
                           "`api.example.com:443`, `v1.2:3`.\n")
        self.assertEqual(drexify.check(path, self.repo)["problems"], [])

    def test_check_reads_stdin_without_writing(self):
        body = ("Identified 1 sites of drexification (0 already on Drex, 0 partial, 0 implemented now, 1 candidates)\n"
                "- Contract matching (`.../app/match.py:3`): candidate.\n")
        with mock.patch.object(drexify.sys, "stdin", io.StringIO(body)):
            result = drexify.check("-", self.repo, fix=True)
        self.assertEqual(result["pointers_fixed"], [])
        self.assertTrue(any("services/billing/app/match.py" in p for p in result["problems"]))

    def test_check_round_trips_utf8_reports(self):
        body = ("Identified 1 sites of drexification (0 already on Drex, 0 partial, 0 implemented now, 1 candidates)\n"
                "- Сопоставление контрактов ✓ (`.../app/match.py:3`): candidate, naïve café.\n")
        path = self.report(body)
        self.assertEqual(drexify.check(path, self.repo, fix=True)["problems"], [])
        self.assertIn("Сопоставление контрактов ✓ (`services/billing/app/match.py:3`)", path.read_text(encoding="utf-8"))

    def test_files_directly_in_a_split_folder_get_their_own_area(self):
        (self.repo / "services/top.py").write_text("client.chat.completions.create(model='m')\n")
        areas = drexify.scan(self.repo)["areas"]
        self.assertIn("services/*", areas)
        self.assertEqual([f["path"] for f in areas["services/*"]["files"]], ["services/top.py"])

    def test_scan_lists_candidate_functions_with_lines(self):
        files = {f["path"]: f for a in drexify.scan(self.repo)["areas"].values() for f in a["files"]}
        self.assertEqual([(fn["name"], fn["line"]) for fn in files["services/billing/app/match.py"]["functions"]],
                         [("match_contract", 3)])

    def test_scan_follows_in_house_model_wrappers(self):
        (self.repo / "shared/core/llm.py").write_text(
            "import openai\n\nclass TextGen:\n    def generate_raw(self, p):\n"
            "        return client.chat.completions.create(model='m')\n\n"
            "    def generate_dict(self, p):\n        return self.generate_raw(p)\n")
        (self.repo / "services/search/app/pick.py").write_text(
            "from core.llm import TextGen\n\ndef pick_template(q):\n    return TextGen().generate_dict(q)\n\n"
            "def unrelated(q):\n    return q\n")
        result = drexify.scan(self.repo)
        self.assertEqual(result["wrappers"], ["generate_dict", "generate_raw"])
        files = {f["path"]: f for a in result["areas"].values() for f in a["files"]}
        self.assertEqual([fn["name"] for fn in files["services/search/app/pick.py"]["functions"]], ["pick_template"])

    def test_scan_learns_a_two_layer_wrapper_chain_without_a_model_import(self):
        (self.repo / "shared/core/llm.py").write_text(
            "import openai\n\ndef post_to_model(prompt):\n"
            "    return client.chat.completions.create(model='m')\n")
        (self.repo / "services/search/app/client.py").write_text(
            "def forward_to_model(prompt):\n    return post_to_model(prompt)\n\n"
            "def ask_model_client(prompt):\n    return forward_to_model(prompt)\n\n"
            "def relay_model_call(prompt):\n    return ask_model_client(prompt)\n\n"
            "def should_ask_model(prompt):\n    return forward_to_model(prompt)\n\n"
            "def send_to_model(prompt):\n    return forward_to_model(prompt)\n\n"
            "def summarize_thread(prompt):\n    return forward_to_model(prompt)\n")
        (self.repo / "services/chat/app").mkdir(parents=True)
        (self.repo / "services/chat/app/send.py").write_text(
            "def send_to_model(prompt):\n    return forward_to_model(prompt)\n")
        (self.repo / "services/search/app/grade.py").write_text(
            "def grade_answer(text):\n    return ask_model_client(text)\n\n"
            "def is_relevant(text):\n    return forward_to_model(text)\n")
        result = drexify.scan(self.repo)
        self.assertIn("forward_to_model", result["wrappers"])
        self.assertIn("ask_model_client", result["wrappers"])
        for name in ("grade_answer", "is_relevant", "summarize_thread", "should_ask_model", "send_to_model",
                     "relay_model_call"):
            self.assertNotIn(name, result["wrappers"])
        files = {f["path"]: f for a in result["areas"].values() for f in a["files"]}
        self.assertEqual([fn["name"] for fn in files["services/search/app/grade.py"]["functions"]],
                         ["grade_answer", "is_relevant"])

    def test_eval_folders_are_scanned_when_plain_tests_are_not(self):
        eval_file = self.repo / "tests/evals/judge.py"
        eval_file.parent.mkdir(parents=True)
        eval_file.write_text(
            "def grade_reply(text):\n    return client.chat.completions.create(model='m')\n")
        skipped = ("tests/plain_check.py", "tests/evals/test_judge.py", "examples/chat/grade.py",
                   "samples/grade.py", "examples/evals/grade.py", "tests/evals/fixtures/fake.py",
                   "evals/tests/helpers.py", "testing/llmtest/check.go")
        for rel in skipped + ("evals/judge.py",):
            (self.repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / rel).write_text(
                "def grade_reply(text):\n    return client.chat.completions.create(model='m')\n")
        paths = {f["path"] for a in drexify.scan(self.repo)["areas"].values() for f in a["files"]}
        self.assertIn("tests/evals/judge.py", paths)
        self.assertIn("evals/judge.py", paths)
        for rel in skipped:
            self.assertNotIn(rel, paths)
        self.assertNotIn("services/billing/tests/test_match.py", paths)
        self.assertIn("services/billing/tests/test_match.py",
                      {f["path"] for a in drexify.scan(self.repo, include_tests=True)["areas"].values() for f in a["files"]})

    def test_scan_follows_same_file_helpers_for_decision_named_functions(self):
        (self.repo / "services/billing/app/gl.py").write_text(
            "from rapidfuzz import fuzz\n\ndef _score(a, b):\n    return fuzz.ratio(a, b)\n\n"
            "def match_accounts(rows):\n    return [_score(r, 'x') for r in rows]\n\ndef load(rows):\n    return rows\n")
        files = {f["path"]: f for a in drexify.scan(self.repo)["areas"].values() for f in a["files"]}
        self.assertEqual([fn["name"] for fn in files["services/billing/app/gl.py"]["functions"]],
                         ["_score", "match_accounts"])

    def test_wrappers_skip_decisions_private_helpers_fuzzy_chains_and_duplicates(self):
        (self.repo / "shared/core/llm.py").write_text(
            "import openai\nfrom rapidfuzz import fuzz\n\n"
            "def _post_json(p):\n    return client.chat.completions.create(model='m')\n\n"
            "def classify_intent(p):\n    return _post_json(p)\n\n"
            "def fuzzy_score(a):\n    return fuzz.ratio(a, 'x')\n\n"
            "def normalize_names(a):\n    return fuzzy_score(a)\n\n"
            "def schema_for(model):\n    return model.model_json_schema()\n\n"
            "def generate_text(p):\n    return _post_json(p)\n")
        (self.repo / "shared/core/other.py").write_text("def generate_text(p):\n    return p\n")
        self.assertEqual(drexify.scan(self.repo)["wrappers"], [])

    def test_decision_functions_inherit_top_level_rule_constants(self):
        (self.repo / "shared/core/cells.py").write_text(
            "import re\n\n_CURRENCY_RE = re.compile(\n    r'^[$]?[0-9,]+$'\n)\n\n"
            "def classify_cell(value):\n    return 'money' if _CURRENCY_RE.match(value) else 'text'\n\n"
            "def load(value):\n    return value\n")
        files = {f["path"]: f for a in drexify.scan(self.repo)["areas"].values() for f in a["files"]}
        self.assertEqual([fn["name"] for fn in files["shared/core/cells.py"]["functions"]], ["classify_cell"])

    def test_go_regexp_and_keyword_rules_are_signals(self):
        (self.repo / "services/search/app/detect.go").write_text(
            "package app\n\nvar repeatRe = regexp.MustCompile(`(.)\\1{19,}`)\n\n"
            "func detectRepetition(text string) bool {\n\treturn repeatRe.MatchString(text)\n}\n\n"
            "func matchLabel(label string) bool {\n\treturn strings.EqualFold(label, \"unknown\")\n}\n")
        files = {f["path"]: f for a in drexify.scan(self.repo)["areas"].values() for f in a["files"]}
        self.assertEqual([fn["name"] for fn in files["services/search/app/detect.go"]["functions"]],
                         ["detectRepetition", "matchLabel"])

    def test_go_generate_content_is_a_model_call(self):
        for line in ("resp, err := llm.GenerateContent(ctx, messages)",
                     "text, err := llms.GenerateFromSinglePrompt(ctx, llm, prompt)",
                     'url := fmt.Sprintf("%s/models/%s:generateContent", root, model)'):
            self.assertIn("model-call", drexify.line_hits(line)[0][1], line)
        for line in ("type GenerateContentResponse struct {}",
                     "func (m *Model) GenerateContent(ctx context.Context, mc []Message) error {"):
            self.assertNotIn("model-call", (drexify.line_hits(line) or [(0, [])])[0][1], line)

    def test_framework_llm_objects_are_model_calls(self):
        for line in ("response = self.llm.call(prompt)", "out = await llm_instance.ainvoke(messages)",
                     "r = self._llm.call([m])", "await this.llm.chat(messages)", "chat_model.invoke(x)"):
            self.assertIn("model-call", drexify.line_hits(line)[0][1], line)
        for line in ("self.llm = llm", "llm_config.get('model')", "callback.call(x)"):
            self.assertNotIn("model-call", (drexify.line_hits(line) or [(0, [])])[0][1], line)

    def test_model_json_schema_is_not_a_model_call(self):
        kinds = {k for _, ks in drexify.line_hits("schema = Model.model_json_schema()\n") for k in ks}
        self.assertNotIn("model-call", kinds)

    def test_function_finder_handles_common_languages(self):
        samples = {
            "  async classifyDoc(text: string): Promise<Label> {": "classifyDoc",
            "  async classifyDoc(": "classifyDoc",
            "export const route = async (q: string) => {": "route",
            'const fetchIt = (url = "http://example.test") => {': "fetchIt",
            "const pick = <T>(xs: T[]) => {": "pick",
            "export function triage(x) {": "triage",
            "func (s *Svc) Detect(ctx context.Context) error {": "Detect",
            "pub(crate) fn rerank(items: &[Item]) -> Vec<Item> {": "rerank",
            "suspend fun matchVendor(name: String): Vendor {": "matchVendor",
            "    public String classify(String text) {": "classify",
            "    public async Task<Label> ClassifyAsync(string text) {": "ClassifyAsync",
            "    public function selectTemplate($x) {": "selectTemplate",
            "  def self.grade(answer)": "grade",
        }
        for line, name in samples.items():
            with self.subTest(line=line):
                self.assertEqual(drexify.generic_starts([line]), [(1, name)])
        for line in ("    if (ready) {", "    foreach (var x in xs) {", "    } else if (x) {", "    return build(x);",
                     "    doThing(x)", "    lock (gate) {", "    new Foo() {"):
            with self.subTest(line=line):
                self.assertEqual(drexify.generic_starts([line]), [])

    def test_generic_spans_end_at_the_closing_brace(self):
        lines = ["function classifyDoc(t) {", "  return llm.chat.completions.create({x: '}'})", "}", "",
                 "const client = new OpenAI()"]
        spans = drexify.generic_spans(lines)
        self.assertEqual([(s[0], s[1], s[2]) for s in spans], [(1, 3, "classifyDoc")])
        self.assertIsNone(drexify.owner_of(spans, 5))

    def test_python_spans_cover_decorators_nesting_and_parse_failures(self):
        text = "@retry\ndef outer():\n    def inner():\n        return 1\n    return inner()\n"
        self.assertEqual([(s[0], s[1], s[2]) for s in drexify.python_spans(text)],
                         [(2, 5, "outer"), (3, 4, "outer.inner")])
        spans, parsed = drexify.file_spans("x.py", "def broken(:\n    pass\n")
        self.assertFalse(parsed)

    def test_heavy_areas_split_by_folder_until_they_fit(self):
        files = [{"path": f"services/main/src/main/{d}/m{i}.py", "hits": 1, "functions": [{}]}
                 for d in ("workflows", "app", "pipeline") for i in range(10)]
        files.append({"path": "services/main/src/main/top.py", "hits": 1, "functions": [{}]})
        areas = {"services/main": {"files": files, "hits": 31, "functions": 31},
                 "shared": {"files": files[:2], "hits": 2, "functions": 2}}
        split = drexify.split_heavy(areas, 3)
        self.assertEqual(sorted(split), ["services/main/src/main/*", "services/main/src/main/app",
                                         "services/main/src/main/pipeline", "services/main/src/main/workflows", "shared"])
        self.assertEqual(sum(len(e["files"]) for e in split.values()), 33)

    def test_group_printout_starts_with_totals(self):
        out = io.StringIO()
        result = drexify.scan(self.repo, groups=1)
        with redirect_stdout(out):
            drexify.print_scan(result, group=1)
        self.assertRegex(out.getvalue().splitlines()[0],
                         r"^# group 1: \d+ areas, \d+ files, \d+ candidate functions, \d+ files without one$")

    def test_suggested_groups_scale_with_candidate_functions(self):
        self.assertEqual([drexify.suggested_groups(n) for n in (0, 175, 176, 908, 9999)], [1, 1, 2, 6, 8])

    def test_check_points_sites_at_the_first_line_of_their_function(self):
        (self.repo / "services/search/app/pick.py").write_text(
            "import x\n\n@cache\ndef pick_template(q):\n    a = 1\n    return llm(q)\n")
        body = ("Identified 2 sites of drexification (0 already on Drex, 0 partial, 0 implemented now, 2 candidates)\n"
                "- Pick (`services/search/app/pick.py:6`): candidate.\n"
                "- Route (`services/search/app/route.py:2`): candidate.\n")
        path = self.report(body)
        self.assertTrue(any("starts at line 4" in p for p in drexify.check(path, self.repo)["problems"]))
        result = drexify.check(path, self.repo, fix=True)
        self.assertEqual(result["problems"], [])
        self.assertIn("`services/search/app/pick.py:4`", path.read_text())
        self.assertIn("`services/search/app/route.py:1`", path.read_text())
        path.write_text(body.replace("pick.py:6", "pick.py:3"))
        drexify.check(path, self.repo, fix=True)
        self.assertIn("`services/search/app/pick.py:4`", path.read_text())
        path.write_text(body.replace("pick.py:6", "pick.py:2"))
        drexify.check(path, self.repo, fix=True)
        self.assertIn("`services/search/app/pick.py:4`", path.read_text())
        path.write_text(body.replace("pick.py:6", "pick.py:1"))
        self.assertTrue(any("not inside a function" in p for p in drexify.check(path, self.repo, fix=True)["problems"]))

    def test_planning_area_headings_still_count(self):
        path = self.report("Identified 1 sites of drexification (0 already on Drex, 0 partial, 0 implemented now, 1 candidates)\n"
                           "## Audit planning\n- Route (`services/search/app/route.py:1`): candidate.\n")
        self.assertEqual(drexify.check(path, self.repo)["problems"], [])

    def test_plan_headings_skip_only_after_the_headline(self):
        site = "- Route (`services/search/app/route.py:1`): candidate.\n"
        path = self.report("# Drexify plan\nIdentified 1 sites of drexification (0 already on Drex, 0 partial, "
                           "0 implemented now, 1 candidates)\n## Pricing plan\n" + site)
        self.assertEqual(drexify.check(path, self.repo)["problems"], [])
        covered = ("Checked 1 of 1 candidate functions: 1 site, 0 callers, wrappers, or backends, "
                    "0 not decisions, 0 dead. 0 more sites. 1 site line in total.\n")
        path = self.report("Identified 1 sites of drexification (0 already on Drex, 0 partial, 0 implemented now, 1 candidates)\n" + site + covered + "## Plan\n```bash\n# run the scan\n```\n"
                           "- Step (`services/billing/app/match.py:3`): candidate first.\n")
        self.assertEqual(drexify.check(path, self.repo)["problems"], [])

    def test_check_reads_hard_wrapped_reports(self):
        path = self.report("Your repo has been scanned. Identified 1 site of drexification (0 already on\n"
                           "Drex, 0 partial, 0 implemented now, 1 candidate).\n\n"
                           "- Pick a template (`services/search/app/route.py:2`):\n"
                           "  candidate, `choice` over the template names.\n")
        result = drexify.check(path, self.repo, fix=True)
        self.assertEqual(result["problems"], [])
        self.assertIn("route.py:1`):\n  candidate", path.read_text())

    def test_typescript_generator_and_multiline_methods(self):
        text = ("class Azure {\n  async *chatStream(\n    body: Body,\n    signal: AbortSignal,\n  ): AsyncGenerator<Chunk> {\n"
                "    const r = await this.openai.chat.completions.create(body);\n  }\n\n"
                "  completion(\n    body: Body,\n  ) {\n    return 1;\n  }\n\n"
                "  run() {\n    doThing(\n      a,\n    );\n    if (\n      x\n    ) {\n      y();\n    }\n  }\n}\n")
        self.assertEqual([n for _, n in drexify.generic_starts(text.splitlines())], ["chatStream", "completion", "run"])

    def test_phrase_loop_is_a_text_rule(self):
        text = (
            "def _should_replan(self):\n"
            "    content = str(last.get('content', '')).lower()\n"
            "    indicators = ['need to reconsider', 'replan']\n"
            "    for indicator in indicators:\n"
            "        if indicator in content:\n"
            "            return True\n"
            "    return False\n\n"
            "def has_key(key):\n"
            "    return key in some_dict\n\n"
            "def walk(rows):\n"
            "    for key in rows:\n"
            "        if other in key:\n"
            "            return key\n\n"
            "def is_known(rows, seen):\n"
            "    for key in rows:\n"
            "        if key in seen:\n"
            "            return True\n"
            "    return False\n"
        )
        hits = {line.strip(): kinds for line, kinds in (
            (text.splitlines()[n - 1], ks) for n, ks in drexify.line_hits(text))}
        self.assertIn("text-rule", hits["if indicator in content:"])
        self.assertNotIn("text-rule", hits.get("return key in some_dict", []))
        self.assertNotIn("text-rule", hits.get("if other in key:", []))
        self.assertNotIn("text-rule", hits.get("if key in seen:", []))
        spans, _ = drexify.file_spans("f.py", text)
        got = [fn["name"] for fn in drexify.candidate_functions(spans, drexify.line_hits(text), text.splitlines())]
        self.assertEqual(got, ["_should_replan"])

    def test_inline_label_tuple_makes_a_can_predicate_a_candidate(self):
        text = (
            "def can_answer_from_history(self, context):\n"
            "    outcome = self._collapse_to_outcome(\n"
            "        feedback,\n"
            "        ('answer_from_history', 'route_to_flow'),\n"
            "        llm,\n"
            "    )\n"
            "    return outcome == 'answer_from_history'\n\n"
            "def can_store(self):\n"
            "    labels = ('answer_from_history', 'route_to_flow')\n"
            "    return labels\n\n"
            "def save_pair(self):\n"
            "    self.write(('answer_from_history', 'route_to_flow'))\n\n"
            "def upgrade():\n"
            "    op.execute(\"status IN ('pending', 'draft')\")\n\n"
            "def verify_token(token):\n"
            "    jwt.decode(token, options={'require': ['sub', 'email', 'iat']})\n"
        )
        spans, _ = drexify.file_spans("f.py", text)
        found = drexify.line_hits(text)
        got = {fn["name"]: fn["kinds"] for fn in drexify.candidate_functions(spans, found, text.splitlines())}
        self.assertEqual(list(got), ["can_answer_from_history"])
        self.assertIn("label-set", got["can_answer_from_history"])
        self.assertNotIn("label-set", {k for _, ks in found for k in ks})
        self.assertTrue(any("label-arg" in ks for _, ks in found))

    def test_task_output_promotes_the_same_file_caller(self):
        text = (
            "def _evaluation_task(agent, task):\n"
            "    return Task(\n"
            "        description=task.description,\n"
            "        agent=agent,\n"
            "        output_pydantic=TaskEvaluationPydanticOutput,\n"
            "    )\n\n"
            "def evaluate(self, task_output):\n"
            "    evaluation_task = self._evaluation_task(agent, task_output)\n"
            "    return evaluation_task.execute_sync()\n\n"
            "def kickoff(self, tasks):\n"
            "    return self.crew.kickoff(tasks)\n"
        )
        kinds = drexify.line_hits("output_pydantic=TaskEvaluationPydanticOutput")[0][1]
        self.assertIn("task-output", kinds)
        self.assertNotIn("model-call", kinds)
        self.assertFalse(drexify.line_hits("task.output_pydantic = None"))
        self.assertFalse(drexify.line_hits("output_json = answer.model_dump_json()"))
        self.assertFalse(drexify.line_hits("evaluation_task.execute_sync()"))
        agent = {k for _, ks in drexify.line_hits("return Agent(model, output_type=Label)") for k in ks}
        self.assertNotIn("task-output", agent)
        self.assertNotIn("model-call", agent)
        spans, _ = drexify.file_spans("f.py", text)
        got = [fn["name"] for fn in drexify.candidate_functions(spans, drexify.line_hits(text), text.splitlines())]
        self.assertEqual(got, ["_evaluation_task", "evaluate"])

    def test_predicates_with_keyword_rules_are_candidates(self):
        text = ("const PHRASES = ['sure', 'here is'];\n\nfunction isEnglishLine(line: string): boolean {\n"
                "  return PHRASES.some((p) => line.startsWith(p));\n}\n\nfunction isEmpty(x: string) {\n  return x === '';\n}\n")
        spans, _ = drexify.file_spans("f.ts", text)
        got = [f["name"] for f in drexify.candidate_functions(spans, drexify.line_hits(text), text.splitlines())]
        self.assertEqual(got, ["isEnglishLine"])

    def test_fenced_site_lines_are_not_counted(self):
        path = self.report("Identified 1 sites of drexification (0 already on Drex, 0 partial, 0 implemented now, 1 candidates)\n- Route (`services/search/app/route.py:1`): candidate.\n\n"
                           "```text\n- Copy (`services/search/app/route.py:1`): candidate.\n```\n")
        self.assertEqual(drexify.check(path, self.repo)["problems"], [])

    def test_constants_need_a_real_assignment_and_reach_one_line_functions(self):
        cases = {
            "kwarg.py": ("import re\nP = compile_all(\n    flags=re.compile('x'),\n)\n\n"
                         "def classify(flags):\n    return flags\n", []),
            "oneline.py": ("import re\nRX = re.compile('x')\n\ndef classify_kind(t): return RX.match(t)\n",
                           ["classify_kind"]),
            "Field.java": ("class A {\n  private static final Pattern RX = Pattern.compile(\"x\");\n"
                           "  String classifyKind(String t) {\n    return RX.matcher(t).find() ? \"a\" : \"b\";\n  }\n}\n",
                           ["classifyKind"]),
        }
        for name, (text, expected) in cases.items():
            spans, _ = drexify.file_spans(name, text)
            found = drexify.line_hits(text)
            got = [f["name"] for f in drexify.candidate_functions(spans, found, text.splitlines())]
            self.assertEqual(got, expected, name)

    def test_check_accepts_range_pointers(self):
        path = self.report("Identified 1 sites of drexification (0 already on Drex, 0 partial, 0 implemented now, 1 candidates)\n- Route (`services/search/app/route.py:1-2`): candidate.\n")
        self.assertEqual(drexify.check(path, self.repo, fix=True)["problems"], [])

    def test_check_keeps_pointers_where_function_ends_are_unknown(self):
        (self.repo / "services/search/app/rules.rb").write_text(
            "def first(x)\n  x\nend\n\nclass Router\n  def pick(q)\n    h = {a: 1}\n    q\n  end\nend\n")
        (self.repo / "services/search/app/tail.py").write_text(
            "def first(q):\n    return call(\n        q,\n    )\n\n\ndef second(q):\n    return q\n")
        for ptr, expected in (("rules.rb:5", "rules.rb:5"), ("tail.py:4", "tail.py:1")):
            path = self.report("Identified 1 sites of drexification (0 already on Drex, 0 partial, 0 implemented now, 1 candidates)\n- Pick (`services/search/app/" + ptr + "`): candidate.\n")
            drexify.check(path, self.repo, fix=True)
            self.assertIn(f"/{expected}`", path.read_text())

    def test_from_explains_a_missing_or_broken_map(self):
        broken = Path(self.tmp.name) / "broken.json"
        broken.write_text("{")
        for path in (broken, Path(self.tmp.name) / "missing.json"):
            with self.assertRaises(SystemExit) as caught:
                drexify.load_map(path, None, False)
            self.assertIn("scan --save", str(caught.exception))

    def test_official_sdk_counts_as_drex(self):
        self.assertIn("drex", drexify.line_hits("from nace_sdk import NaceClient")[0][1])

    def test_check_flags_two_sites_in_one_function_after_snapping(self):
        path = self.report("Identified 2 sites of drexification (0 already on Drex, 0 partial, 0 implemented now, 2 candidates)\n"
                           "- A (`services/billing/app/match.py:3`): candidate.\n"
                           "- B (`services/billing/app/match.py:4`): candidate.\n")
        self.assertTrue(any("already listed" in p for p in drexify.check(path, self.repo, fix=True)["problems"]))

    def test_from_rejects_stale_or_mismatched_maps_and_regroups(self):
        saved = Path(self.tmp.name) / "map.json"
        with redirect_stdout(io.StringIO()):
            drexify.main(["scan", "--repo", str(self.repo), "--groups", "1", "--save", str(saved)])
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(drexify.main(["scan", "--from", str(saved), "--groups", "3", "--group", "3"]), 0)
        self.assertIn("## ", out.getvalue())
        with self.assertRaises(SystemExit):
            drexify.main(["scan", "--from", str(saved), "--repo", self.tmp.name])
        with self.assertRaises(SystemExit):
            drexify.main(["scan", "--from", str(saved), "--include-tests"])
        stale = json.loads(saved.read_text())
        stale["schema"] = 1
        saved.write_text(json.dumps(stale))
        with self.assertRaises(SystemExit):
            drexify.main(["scan", "--from", str(saved)])

    def test_scan_save_and_from_skip_the_second_search(self):
        saved = Path(self.tmp.name) / "map.json"
        with redirect_stdout(io.StringIO()):
            drexify.main(["scan", "--repo", str(self.repo), "--groups", "2", "--save", str(saved)])
        out = io.StringIO()
        with mock.patch.object(drexify, "scan", side_effect=AssertionError("searched again")), redirect_stdout(out):
            self.assertEqual(drexify.main(["scan", "--from", str(saved), "--groups", "2", "--group", "1"]), 0)
        self.assertIn("candidate functions", out.getvalue())

    def test_check_skips_site_shaped_lines_under_not_counted(self):
        path = self.report(
            "Identified 1 sites of drexification (0 already on Drex, 0 partial, 0 implemented now, 1 candidates)\n"
            "- Route (`services/search/app/route.py:1`): candidate.\n"
            "Checked 1 of 1 candidate functions: 1 site, 0 callers, wrappers, or backends, "
            "0 not decisions, 0 dead. 0 more sites. 1 site line in total.\n\n## Not counted\n\n"
            "- Old router (`services/billing/app/match.py:3`): no callers.\n\n## Coverage\n\nRead in depth: services.\n"
            "\n## Implementation plan\n\n### Steps\n\n- Step one (`services/billing/app/match.py:3`): candidate first.\n"
            "**Order**\n- Step two (`services/billing/app/match.py:3`): candidate next.\n")
        self.assertEqual(drexify.check(path, self.repo)["problems"], [])
        mixed = path.read_text().replace("## Not counted", "## Billing (2 sites, 1 not counted)")
        self.assertTrue(any("status must start with" in p for p in drexify.check(self.report(mixed), self.repo)["problems"]))
        path.write_text(path.read_text().replace("match.py:3", "match.py:99"))
        self.assertTrue(any("past the end" in p for p in drexify.check(path, self.repo)["problems"]))

    def test_check_reports_bad_pointers_statuses_and_counts(self):
        path = self.report(
            "Identified 3 sites of drexification (1 already on Drex, 0 partial, 0 implemented now, 1 candidates)\n"
            "- Ambiguous (`classify.py:1`): candidate.\n"
            "- Missing (`services/none.py:1`): candidate.\n"
            "- Too far (`services/search/app/route.py:99`): candidate.\n"
            "- Made-up status (`services/search/app/route.py:1`): dormant.\n"
            "- Braces (`shared/core/{a,b}/classify.py:1`): candidate.\n"
            "- Ambiguous again (`classify.py:1`): candidate.\n")
        problems = "\n".join(drexify.check(path, self.repo)["problems"])
        for expected in ("ambiguous, matches 2 files", "no such file", "past the end", "status must start with",
                         "brace groups", "headline total 3 does not equal", "the list has 5", "already listed on line"):
            self.assertIn(expected, problems)

    def test_check_requires_headline(self):
        path = self.report("- Contract matching (`services/billing/app/match.py:3`): candidate.\n")
        self.assertTrue(any("headline not found" in p for p in drexify.check(path, self.repo)["problems"]))

    def test_skill_example_report_passes_the_checker_format(self):
        skill = (ROOT / "skills" / "drexify" / "SKILL.md").read_text()
        example = skill.split("```text\n", 1)[1].split("```", 1)[0]
        total, on, part, done, cand = map(int, drexify.HEADLINE.search(example).groups())
        tally = {s: 0 for s in drexify.STATUSES}
        for line in example.splitlines():
            site = drexify.SITE.match(line)
            if site:
                rest = site.group("rest").lower()
                tally[next(s for s in drexify.STATUSES if rest.startswith(s.lower()))] += 1
        self.assertEqual(sum(tally.values()), 5)
        self.assertEqual(on + part + done + cand, total)
        self.assertEqual(set(k for k, v in tally.items() if v), set(drexify.STATUSES))

    def test_judge_block_with_a_model_is_a_model_call(self):
        text = (
            "export function createBiasScorer({ model }) {\n"
            "  return createScorer({\n"
            "    judge: {\n"
            "      model,\n"
            "      instructions: 'grade bias',\n"
            "    },\n"
            "  });\n"
            "}\n\n"
            "export function setModel(model: string) {\n"
            "  return { model: model };\n"
            "}\n\n"
            "export function createPlainScorer() {\n"
            "  return createScorer({ judge: { instructions: 'no model here' } });\n"
            "}\n"
        )
        spans, _ = drexify.file_spans("bias.ts", text)
        found = drexify.line_hits(text)
        got = [fn["name"] for fn in drexify.candidate_functions(spans, found, text.splitlines())]
        self.assertEqual(got, ["createBiasScorer"])
        self.assertIn("model-call", next(ks for n, ks in found if "judge:" in text.splitlines()[n - 1]))
        self.assertFalse(any("model-call" in ks for n, ks in found if "instructions: 'no model here'" in text.splitlines()[n - 1]))

    def test_structured_output_beside_generate_is_a_model_call(self):
        text = (
            "async function moderateContent(prompt: string) {\n"
            "  const response = await this.moderationAgent.generate(prompt, {\n"
            "    structuredOutput: { schema },\n"
            "  });\n"
            "  return response.object;\n"
            "}\n\n"
            "async function createNetworkLoop() {\n"
            "  const options = {\n"
            "    structuredOutput: { schema },\n"
            "  };\n"
            "  return tryGenerateWithJsonFallback(routingAgent, prompt, options);\n"
            "}\n\n"
            "export async function runDefaultCompletionCheck(\n"
            "  streamContext?: {\n"
            "    writer?: { write: (chunk: string) => void };\n"
            "  },\n"
            "): Promise<void> {\n"
            "  return agent.stream(prompt, {\n"
            "    structuredOutput: { schema },\n"
            "  });\n"
            "}\n\n"
            "function describeSchema() {\n"
            "  return { structuredOutput: { schema } };\n"
            "}\n\n"
            "async function send(prompt: string) {\n"
            "  return agent.generate(prompt);\n"
            "}\n"
        )
        spans, _ = drexify.file_spans("moderation.ts", text)
        found = drexify.line_hits(text)
        got = [fn["name"] for fn in drexify.candidate_functions(spans, found, text.splitlines())]
        self.assertEqual(got, ["moderateContent", "createNetworkLoop", "runDefaultCompletionCheck"])
        self.assertFalse(any("model-call" in ks for _n, ks in drexify.line_hits("return agent.generate(prompt);\n")))

    def test_classifier_decide_and_sentiment_library_are_model_calls(self):
        text = (
            "async function processInput(text: string) {\n"
            "  return classifier.decide({ state: { request: text } });\n"
            "}\n\n"
            "function createToneScorer() {\n"
            "  const sentiment = new Sentiment();\n"
            "  return sentiment.analyze(text);\n"
            "}\n\n"
            "function note() {\n"
            "  return classifier.score(text);\n"
            "}\n\n"
            "function pickTopic(text: string) {\n"
            "  return this.topicClassifier.classify(text);\n"
            "}\n\n"
            "function label() {\n"
            "  const sentiment = 'positive';\n"
            "  return sentiment;\n"
            "}\n"
        )
        spans, _ = drexify.file_spans("processors.ts", text)
        got = [fn["name"] for fn in drexify.candidate_functions(spans, drexify.line_hits(text), text.splitlines())]
        self.assertEqual(got, ["processInput", "createToneScorer", "pickTopic"])
        self.assertFalse(drexify.line_hits("return classifier.score(text);\n"))
        self.assertFalse(drexify.line_hits("const sentiment = 'positive';\n"))

    def test_regex_some_test_makes_an_intent_predicate_a_candidate(self):
        text = (
            "export function isFutureIntentObservation(line: string): boolean {\n"
            "  return futureIntentPatterns.some(pattern => pattern.test(line));\n"
            "}\n\n"
            "export function isFutureIntentNote(line: string): boolean {\n"
            "  return futureIntentPatterns.some(pattern => pattern.exec(line));\n"
            "}\n\n"
            "export function collect(line: string) {\n"
            "  return patterns.some(pattern => pattern.test(line));\n"
            "}\n"
        )
        spans, _ = drexify.file_spans("date-utils.ts", text)
        found = drexify.line_hits(text)
        got = [fn["name"] for fn in drexify.candidate_functions(spans, found, text.splitlines())]
        self.assertEqual(got, ["isFutureIntentObservation"])
        self.assertIn("text-rule", next(ks for n, ks in found if ".test(" in text.splitlines()[n - 1]))
        self.assertFalse(any("text-rule" in ks and ".exec(" in text.splitlines()[n - 1] for n, ks in found))

    def test_chat_client_prompt_call_is_a_model_call(self):
        text = (
            "public EvaluationResponse evaluate(EvaluationRequest request) {\n"
            "  String evaluationResponse = this.chatClientBuilder.build()\n"
            "    .prompt()\n"
            "    .user(userMessage)\n"
            "    .call()\n"
            "    .content();\n"
            "  return evaluationResponse;\n"
            "}\n\n"
            "public String rewrite(String query) {\n"
            "  return this.chatClient.prompt().user(query).call().content();\n"
            "}\n\n"
            "public void prepare() {\n"
            "  this.chatClientBuilder.build().prompt();\n"
            "}\n"
        )
        spans, _ = drexify.file_spans("RelevancyEvaluator.java", text)
        found = drexify.line_hits(text)
        got = [fn["name"] for fn in drexify.candidate_functions(spans, found, text.splitlines())]
        self.assertEqual(got, ["evaluate"])
        self.assertTrue(drexify.keep_file(found))
        self.assertFalse(any("model-call" in ks for _n, ks in drexify.line_hits(
            "return this.chatClient.prompt().user(query).call().content();\n")))

    def test_java_any_match_contains_is_a_word_guard(self):
        text = (
            "private boolean containsSensitiveWord(ChatClientRequest request) {\n"
            "  return this.sensitiveWords.stream()\n"
            "    .anyMatch(w -> request.prompt()\n"
            "      .getContents()\n"
            "      .toLowerCase(Locale.ROOT)\n"
            "      .contains(w.toLowerCase(Locale.ROOT)));\n"
            "}\n\n"
            "private boolean blocked(String text) {\n"
            "  return BANNED.stream().anyMatch(w -> text.toLowerCase().contains(w));\n"
            "}\n\n"
            "private boolean containsToken(String text, List<String> tokens) {\n"
            "  return tokens.stream().anyMatch(w -> text.equals(w));\n"
            "}\n\n"
            "private boolean hasWord(String text, String word) {\n"
            "  return text.contains(word);\n"
            "}\n"
        )
        spans, _ = drexify.file_spans("SafeGuardAdvisor.java", text)
        found = drexify.line_hits(text)
        got = {fn["name"]: fn["kinds"] for fn in drexify.candidate_functions(spans, found, text.splitlines())}
        self.assertEqual(list(got), ["containsSensitiveWord", "blocked"])
        self.assertIn("text-rule", got["containsSensitiveWord"])
        self.assertTrue(drexify.keep_file(found))
        self.assertFalse(any("word-guard" in ks or "text-rule" in ks for n, ks in found
                             if "equals" in text.splitlines()[n - 1] or text.splitlines()[n - 1].strip() == "return text.contains(word);"))

    def test_evaluator_run_inherits_a_model_signal_from_its_class(self):
        text = (
            "class FaithfulnessEvaluator:\n"
            "    def __init__(self, chat_generator=None):\n"
            "        self.kwargs = {'response_format': {'type': 'json_object'}}\n"
            "\n"
            "    def run(self, **inputs):\n"
            "        return super().run(**inputs)\n"
            "\n"
            "class Bucket:\n"
            "    def __init__(self):\n"
            "        self.kwargs = {'response_format': {'type': 'json_object'}}\n"
            "\n"
            "    def run(self):\n"
            "        return super().run()\n"
            "\n"
            "class ScoreEvaluator:\n"
            "    def run(self):\n"
            "        return super().run()\n"
        )
        spans, _ = drexify.file_spans("faithfulness.py", text)
        got = [fn["name"] for fn in drexify.candidate_functions(spans, drexify.line_hits(text), text.splitlines())]
        self.assertIn("FaithfulnessEvaluator.run", got)
        self.assertNotIn("Bucket.run", got)
        self.assertNotIn("ScoreEvaluator.run", got)

    def test_cli_exit_codes_and_json(self):
        good = self.report("Identified 1 sites of drexification (0 already on Drex, 0 partial, 0 implemented now, 1 candidates)\n"
                           "- Route (`services/search/app/route.py:1`): candidate.\n")
        out = io.StringIO()
        with redirect_stdout(out):
            code = drexify.main(["check", str(good), "--repo", str(self.repo), "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["sites"], 1)
        good.write_text(good.read_text().replace("route.py:1", "route.py:50"))
        with redirect_stdout(io.StringIO()):
            self.assertEqual(drexify.main(["check", str(good), "--repo", str(self.repo)]), 1)
            self.assertEqual(drexify.main(["scan", "--repo", str(self.repo), "--groups", "2"]), 0)

    def test_migration_folders_are_skipped_even_with_include_tests(self):
        skipped = (
            "backend/alembic/versions/001_init.py",
            "app/migrations/0001_initial.py",
            "prisma/migrations/20200101000000_init/migration.ts",
            "supabase/migrations/001_init.ts",
            "db/migrations/001_init.js",
            "db/migrate/20240101000000_create_users.rb",
            "engines/blog/db/migrate/001_create.rb",
            "src/main/resources/flyway/V1__init.java",
        )
        kept = (
            "app/migration_utils.py",
            "services/data_migration_service/run.py",
            "lib/migrate/helper.rb",
        )
        body = "def upgrade():\n    return client.chat.completions.create(model='m')\n"
        for rel in skipped + kept:
            path = self.repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body)
        for include_tests in (False, True):
            paths = {f["path"] for a in drexify.scan(self.repo, include_tests=include_tests)["areas"].values()
                     for f in a["files"]}
            for rel in skipped:
                self.assertNotIn(rel, paths, include_tests)
            for rel in kept:
                self.assertIn(rel, paths, include_tests)

    def test_source_test_roots_are_not_reopened_by_an_evaluation_package(self):
        scanned = "src/main/java/com/acme/evaluation/Ranker.java"
        hidden = (
            "src/test/java/com/acme/evaluation/EvalRanker.java",
            "src/androidTest/java/com/acme/evaluation/Ranker.java",
            "src/integrationTest/kotlin/com/acme/evaluation/Ranker.kt",
            "src/testFixtures/java/com/acme/evaluation/Ranker.java",
        )
        text = "void evaluate() { client.chat.completions.create(model); }\n"
        for rel in (scanned,) + hidden:
            path = self.repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        paths = {f["path"] for a in drexify.scan(self.repo)["areas"].values() for f in a["files"]}
        self.assertIn(scanned, paths)
        for rel in hidden:
            self.assertNotIn(rel, paths)
        with_tests = {f["path"] for a in drexify.scan(self.repo, include_tests=True)["areas"].values() for f in a["files"]}
        self.assertIn(hidden[0], with_tests)

    def test_test_file_names_cover_vitest_e2e_bench_and_jvm(self):
        skipped = (
            "models.vitest.ts", "lineStream.vitest.tsx", "a.vitest.js", "a.vitest.mjs", "a.vitest.cjs",
            "flow.e2e.ts", "parse.bench.js", "foo_test.go", "test_foo.py", "foo_test.py", "foo.test.ts",
            "foo.spec.js", "FooTest.java", "FooTests.java", "FooIT.java", "FooTest.kt", "foo_spec.rb",
        )
        kept = ("latest.ts", "contest.py", "attestation.go", "Testimonial.java", "migration_utils.py")
        for name in skipped + kept:
            self.assertEqual(drexify.is_test_name(name), name in skipped, name)
        for name in skipped + kept:
            path = self.repo / "pkg" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("function classifyDoc() { return client.chat.completions.create(1) }\n")
        paths = {f["path"] for a in drexify.scan(self.repo)["areas"].values() for f in a["files"]}
        for name in skipped:
            self.assertNotIn(f"pkg/{name}", paths, name)
        for name in kept:
            self.assertIn(f"pkg/{name}", paths, name)

    def test_prompt_constants_are_not_candidate_functions(self):
        text = (
            "const RERANK_PROMPT = (\n"
            "  query: string,\n"
            "  document: string,\n"
            ") => `Is ${query} relevant to ${document}?\n"
            "def read_root():\n"
            "  return 1\n"
            "fn bubble_sort() {\n"
            "  return 1\n"
            "}`;\n\n"
            "const NOTES = (\n"
            "  \"rerank these documents\"\n"
            ");\n\n"
            "const pick = async (q: string) => {\n"
            "  return client.chat.completions.create({ model: \"m\" });\n"
            "};\n\n"
            "const send = async (\n"
            "  q: string,\n"
            ") => {\n"
            "  return client.chat.completions.create({ model: \"m\" });\n"
            "};\n\n"
            "export async function scoreChunk(query: string) {\n"
            "  return complete(RERANK_PROMPT(query, \"doc\"));\n"
            "}\n"
        )
        starts = [name for _, name in drexify.generic_starts(text.splitlines())]
        self.assertNotIn("read_root", starts)
        self.assertNotIn("bubble_sort", starts)
        self.assertNotIn("NOTES", starts)
        self.assertIn("pick", starts)
        self.assertIn("send", starts)
        spans, _ = drexify.file_spans("llm.ts", text)
        got = [fn["name"] for fn in drexify.candidate_functions(spans, drexify.line_hits(text), text.splitlines())]
        self.assertNotIn("RERANK_PROMPT", got)
        self.assertIn("pick", got)
        self.assertIn("send", got)
        self.assertIn("scoreChunk", got)
        nested = (
            "export function createToolCallAccuracyScorerLLM({ model }: Options) {\n"
            "  const text = tools.map(tool => `${tool.id}`).join('\\n');\n"
            "  return createScorer({\n"
            "    judge: {\n"
            "      model,\n"
            "    },\n"
            "  });\n"
            "}\n"
        )
        spans, _ = drexify.file_spans("scorer.ts", nested)
        got = [fn["name"] for fn in drexify.candidate_functions(spans, drexify.line_hits(nested), nested.splitlines())]
        self.assertEqual(got, ["createToolCallAccuracyScorerLLM"])
        self.assertEqual(spans[0][1], len(nested.splitlines()))

    def test_coverage_line_is_checked_after_the_site_list(self):
        site = "- Route (`services/search/app/route.py:1`): candidate.\n"
        head = "Identified 1 sites of drexification (0 already on Drex, 0 partial, 0 implemented now, 1 candidates)\n"
        bare = self.report(head + site)
        bare.write_text(head + site)
        self.assertTrue(any("no coverage line" in p for p in drexify.check(bare, self.repo)["problems"]))
        good = (
            "Checked 1 of 1 candidate functions: 1 site, 0 callers, wrappers, or backends, "
            "0 not decisions, 0 dead. Opened 0 of 0 files without one and looked around the candidates: "
            "0 more sites. 1 site line in total.\n"
        )
        self.assertEqual(drexify.check(self.report(head + site + good), self.repo)["problems"], [])
        singular = (
            "Checked 1 of 1 candidate function: 1 site, 0 callers, wrappers, or backends, "
            "0 not decisions, 0 dead. Opened 1 of 1 file without one and looked around the candidates: "
            "0 more sites. 1 site line in total.\n"
        )
        self.assertEqual(drexify.check(self.report(head + site + singular), self.repo)["problems"], [])
        wrapped = (
            "Checked 1,212 of 1,212 candidate functions: 48 sites, 61 callers, wrappers, or backends,\n"
            "1,099 not decisions, 4 dead. Opened 95 of 95 files without one and looked around the\n"
            "candidates: 6 more sites. 54 site lines in total.\n"
        )
        problems = drexify.check(self.report(head + site + wrapped), self.repo)["problems"]
        self.assertTrue(any("54" in p and "list has 1" in p for p in problems), problems)
        honest_wrapped = (
            "Checked 1,212 of 1,212 candidate functions: 1 site, 108 callers, wrappers, or backends,\n"
            "1,099 not decisions, 4 dead. Opened 95 of 95 files without one and looked around the\n"
            "candidates: 0 more sites. 1 site line in total.\n"
        )
        self.assertEqual(drexify.check(self.report(head + site + honest_wrapped), self.repo)["problems"], [])
        fenced = (
            "```\n"
            "Checked 9 of 9 candidate functions: 9 sites, 0 callers, wrappers, or backends, "
            "0 not decisions, 0 dead. 0 more sites. 9 site lines in total.\n"
            "```\n"
        )
        self.assertEqual(drexify.check(self.report(head + site + fenced + good), self.repo)["problems"], [])
        bad_sum = good.replace("0 not decisions", "1 not decisions")
        self.assertTrue(any("buckets sum" in p for p in drexify.check(self.report(head + site + bad_sum), self.repo)["problems"]))
        short = good.replace("Checked 1 of 1", "Checked 1 of 4")
        result = drexify.check(self.report(head + site + short), self.repo)
        self.assertEqual(result["problems"], [])
        self.assertTrue(any("checked 1 of 4" in w for w in result["warnings"]))
        bad_total = good.replace("1 site line in total", "3 site lines in total")
        self.assertTrue(any("site lines in total" in p for p in drexify.check(self.report(head + site + bad_total), self.repo)["problems"]))
        early = self.report(good + head + site)
        early.write_text(good + head + site)
        self.assertTrue(any("no coverage line" in p for p in drexify.check(early, self.repo)["problems"]))


    def test_scan_survives_empty_repos_odd_files_and_symlinks(self):
        empty = Path(self.tmp.name) / "empty café"
        empty.mkdir()
        result = drexify.scan(empty)
        self.assertEqual((result["listed"], result["scanned"], result["candidate_functions"], result["head"]), (0, 0, 0, None))
        odd = self.repo / "área" / "my file.py"
        odd.parent.mkdir()
        odd.write_bytes("def classify_doc(t):\n    return client.chat.completions.create(model='m')\n".encode())
        (self.repo / "broken.py").write_bytes(b"\xff\xfe def classify_doc(t):\n    pass\n")
        (self.repo / "binary.js").write_bytes(b"\x00\x01\x02function classify(x){return 1}\n")
        crlf = self.repo / "crlf.ts"
        crlf.write_bytes(b"export function classifyDoc(t: string) {\r\n  return llm.chat.completions.create(t);\r\n}\r\n")
        under = self.repo / "under.py"
        over = self.repo / "over.py"
        signal = b"def classify_doc(t):\n    return client.chat.completions.create(model='m')\n"
        under.write_bytes(signal + b"#" * (drexify.MAX_BYTES - len(signal)))
        over.write_bytes(signal + b"#" * (drexify.MAX_BYTES - len(signal) + 1))
        self.assertEqual(under.stat().st_size, drexify.MAX_BYTES)
        self.assertEqual(over.stat().st_size, drexify.MAX_BYTES + 1)
        outside = Path(self.tmp.name) / "outside.py"
        outside.write_text("def classify_outside(t):\n    return client.chat.completions.create(model='m')\n")
        (self.repo / "escape.py").symlink_to(outside)
        inside = self.repo / "inside_target.py"
        inside.write_text("def classify_inside(t):\n    return client.chat.completions.create(model='m')\n")
        (self.repo / "alias.py").symlink_to(inside)
        (self.repo / "loop_a.js").symlink_to(self.repo / "loop_b.js")
        (self.repo / "loop_b.js").symlink_to(self.repo / "loop_a.js")
        (self.repo / "loopdir").mkdir()
        (self.repo / "loopdir" / "again").symlink_to(self.repo / "loopdir")
        outside_dir = Path(self.tmp.name) / "outside_dir"
        outside_dir.mkdir()
        (outside_dir / "hidden.py").write_text("def classify_hidden(t):\n    return client.chat.completions.create(model='m')\n")
        (self.repo / "linked_out").symlink_to(outside_dir)
        started = time.perf_counter()
        result = drexify.scan(self.repo)
        self.assertLess(time.perf_counter() - started, 5)
        paths = {f["path"] for a in result["areas"].values() for f in a["files"]}
        self.assertIn("área/my file.py", paths)
        self.assertIn("crlf.ts", paths)
        self.assertIn("under.py", paths)
        self.assertIn("alias.py", paths)
        self.assertNotIn("over.py", paths)
        self.assertNotIn("escape.py", paths)
        self.assertNotIn("linked_out/hidden.py", paths)
        self.assertIsNone(result["head"])
        files = {f["path"]: f for a in result["areas"].values() for f in a["files"]}
        self.assertEqual(files["crlf.ts"]["functions"][0]["line"], 1)

    def test_minified_line_does_not_hang(self):
        blob = "function classify(x){" + ("a.b(c);" * 129000) + "return x}"
        self.assertGreater(len(blob), 900_000)
        path = self.repo / "pkg" / "bundle.js"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(blob)
        started = time.perf_counter()
        drexify.scan(self.repo)
        self.assertLess(time.perf_counter() - started, 5)

    def test_user_errors_do_not_print_a_traceback(self):
        missing = Path(self.tmp.name) / "missing.json"
        broken = Path(self.tmp.name) / "broken.json"
        broken.write_text("{")
        empty = Path(self.tmp.name) / "empty.md"
        empty.write_text("")
        missing_file = self.report(
            "Identified 1 sites of drexification (0 already on Drex, 0 partial, 0 implemented now, 1 candidates)\n"
            "- Missing (`services/nope.py:1`): candidate.\n")
        script = str(SCRIPT)
        cases = (
            ["scan", "--from", str(missing), "--repo", str(self.repo)],
            ["scan", "--from", str(broken), "--repo", str(self.repo)],
            ["check", str(empty), "--repo", str(self.repo)],
            ["check", str(Path(self.tmp.name) / "no-report.md"), "--repo", str(self.repo)],
            ["check", str(missing_file), "--repo", str(self.repo)],
        )
        for argv in cases:
            proc = subprocess.run([sys.executable, script, *argv], capture_output=True, text=True)
            self.assertNotEqual(proc.returncode, 0, argv)
            self.assertNotIn("Traceback", proc.stderr, argv)
            self.assertNotIn("Traceback", proc.stdout, argv)
        self.assertIn("no such file", "\n".join(drexify.check(missing_file, self.repo)["problems"]))
        self.assertTrue(any("headline not found" in p for p in drexify.check(empty, self.repo)["problems"]))

    def test_git_and_non_git_symlinks_stay_inside_the_repo(self):
        repo = Path(self.tmp.name) / "git repo"
        repo.mkdir()
        (repo / "keep.py").write_text("def classify_doc(t):\n    return client.chat.completions.create(model='m')\n")
        outside = Path(self.tmp.name) / "secret.py"
        outside.write_text("def classify_secret(t):\n    return client.chat.completions.create(model='m')\n")
        (repo / "secret.py").symlink_to(outside)
        env = dict(os.environ, GIT_AUTHOR_NAME="drexify", GIT_AUTHOR_EMAIL="drexify@example.com",
                   GIT_COMMITTER_NAME="drexify", GIT_COMMITTER_EMAIL="drexify@example.com")
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True, env=env)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True, env=env)
        paths = {f["path"] for a in drexify.scan(repo)["areas"].values() for f in a["files"]}
        self.assertIn("keep.py", paths)
        self.assertNotIn("secret.py", paths)
        self.assertIsNotNone(drexify.scan(repo)["head"])

    def test_stray_backtick_does_not_hide_later_functions(self):
        lines = [
            "const strip = (s) => s.replace(/`/g, '');",
            "",
            "export function classifyDoc(t) {",
            " return client.chat.completions.create(t);",
            "}",
        ]
        starts = drexify.generic_starts(lines)
        self.assertIn((1, "strip"), starts)
        self.assertIn((3, "classifyDoc"), starts)
        spans = {name: (start, end) for start, end, name, _calls in drexify.generic_spans(lines)}
        self.assertLess(spans["strip"][1], spans["classifyDoc"][0])
        self.assertEqual(spans["classifyDoc"], (3, 5))
        fence = [
            "const fence = /^```/;",
            "export function classifyDoc(t) {",
            " return client.chat.completions.create(t);",
            "}",
        ]
        self.assertIn("classifyDoc", [name for _, name in drexify.generic_starts(fence)])
        quoted = [
            "const tick = '`';",
            'const fenceText = "```";',
            "export function classifyDoc(t) {",
            " return client.chat.completions.create(t);",
            "}",
        ]
        self.assertIn("classifyDoc", [name for _, name in drexify.generic_starts(quoted)])
        combined = [
            "const strip = (s) => s.replace(/`/g, '');",
            "const RERANK_PROMPT = `score this",
            "function hidden() { return 1 }",
            "`;",
            "export function classifyDoc(t) {",
            " return client.chat.completions.create(t);",
            "}",
        ]
        combined_names = [name for _, name in drexify.generic_starts(combined)]
        self.assertIn("strip", combined_names)
        self.assertNotIn("hidden", combined_names)
        self.assertIn("classifyDoc", combined_names)
        unclosed = [
            "const bad = `nope",
            "export function classifyDoc(t) {",
            " return client.chat.completions.create(t);",
            "}",
        ]
        self.assertIn("classifyDoc", [name for _, name in drexify.generic_starts(unclosed)])

    def test_coverage_total_matches_the_listed_site_lines(self):
        def head(count):
            return (f"Identified {count} sites of drexification "
                    f"(0 already on Drex, 0 partial, 0 implemented now, {count} candidates)\n")

        def write_sites(count):
            body = []
            for index in range(count):
                rel = f"pkg/site{index}.py"
                path = self.repo / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("def classify_doc(t):\n    return 1\n")
                body.append(f"- Item {index} (`{rel}:1`): candidate.\n")
            return "".join(body)

        honest = (
            "Checked 60 of 60 candidate functions: 48 sites, 10 callers, wrappers, or backends, "
            "1 not decisions, 1 dead. After removing 2 duplicates, 6 more sites. "
            "52 site lines in total.\n"
        )
        result = drexify.check(self.report(head(52) + write_sites(52) + honest), self.repo)
        self.assertEqual(result["problems"], [], result["problems"])
        over = (
            "Checked 300 of 212 candidate functions: 1 site, 0 callers, wrappers, or backends, "
            "299 not decisions, 0 dead. 0 more sites. 1 site line in total.\n"
        )
        route = "- Route (`services/search/app/route.py:1`): candidate.\n"
        problems = drexify.check(self.report(head(1) + route + over), self.repo)["problems"]
        self.assertTrue(any("300" in problem and "212" in problem for problem in problems), problems)
        added = (
            "Checked 5 of 5 candidate functions: 1 site, 0 callers, wrappers, or backends, "
            "4 not decisions, 0 dead. 0 more sites. 5 site lines in total.\n"
        )
        problems = drexify.check(self.report(head(5) + write_sites(5) + added), self.repo)["problems"]
        self.assertTrue(any("less than 5" in problem for problem in problems), problems)
        plan = head(1) + route + "- Plan: revisit the candidate functions.\n"
        problems = drexify.check(self.report(plan), self.repo)["problems"]
        self.assertTrue(any("no coverage line" in problem for problem in problems), problems)


if __name__ == "__main__":
    unittest.main()
