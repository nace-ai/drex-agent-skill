"""Offline tests for skills/drexify/scripts/drexify.py. No git, network, or model calls required."""
import importlib.util
import io
import json
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
        self.assertTrue(any("run with --fix" in p for p in drexify.check(path, self.repo)["problems"]))
        self.assertEqual(path.read_text(), body)
        result = drexify.check(path, self.repo, fix=True)
        self.assertEqual(result["problems"], [])
        self.assertIn("`services/billing/app/match.py:3`", path.read_text())

    def test_check_never_guesses_between_files_with_the_same_name(self):
        body = ("Identified 1 sites of drexification (0 already on Drex, 0 partial, 0 implemented now, 1 candidates)\n"
                "- Doc classify (`classify.py:4`): candidate.\n")
        path = self.report(body)
        result = drexify.check(path, self.repo, fix=True)
        self.assertTrue(any("ambiguous, matches 2 files" in p for p in result["problems"]))
        self.assertEqual(path.read_text(), body)

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

    def test_model_json_schema_is_not_a_model_call(self):
        kinds = {k for _, ks in drexify.line_hits("schema = Model.model_json_schema()\n") for k in ks}
        self.assertNotIn("model-call", kinds)

    def test_function_finder_handles_common_languages(self):
        samples = {
            "  async classifyDoc(text: string): Promise<Label> {": "classifyDoc",
            "  async classifyDoc(": "classifyDoc",
            "export const route = async (q: string) => {": "route",
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

    def test_suggested_groups_scale_with_candidate_functions(self):
        self.assertEqual([drexify.suggested_groups(n) for n in (0, 200, 351, 1245, 9999)], [1, 1, 2, 4, 6])

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
            "- Route (`services/search/app/route.py:1`): candidate.\n\n## Not counted\n\n"
            "- Old router (`services/billing/app/match.py:3`): no callers.\n\n## Coverage\n\nRead in depth: services.\n")
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


if __name__ == "__main__":
    unittest.main()
