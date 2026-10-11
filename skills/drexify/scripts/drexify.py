#!/usr/bin/env python3
"""Drexify helper. Python 3.9+, standard library only. Reads files, never calls a model or the network.

scan:  one cheap signal search over the whole repository, grouped by area, listing the
       candidate decision functions in each file. --save writes the map once and
       --from reads it back, so parallel helpers never repeat the search.
check: lint a drexify report. Counts must match the headline, statuses must be valid,
       and every `path:line` pointer must resolve. --fix rewrites shortened paths.
"""
import argparse
import ast
import json
import os
from pathlib import Path
import re
import subprocess
import sys

STATUSES = ("already on Drex", "partial", "implemented now", "candidate")
HEADLINE = re.compile(
    r"Identified (\d+) sites? of drexification \((\d+) already on Drex, (\d+) partial, "
    r"(\d+) implemented now, (\d+) candidates?\)"
)
SITE = re.compile(r"^\s*[-*]\s+(?P<name>.+?)\s+\(`(?P<ptr>[^`]+)`\):\s*(?P<rest>.*)$")
CODE_EXT = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".go", ".java", ".kt", ".rb", ".rs", ".cs", ".php", ".scala", ".swift"}
POINTER_EXT = CODE_EXT | {".md", ".mdx", ".yaml", ".yml", ".json", ".toml", ".sql", ".sh", ".html", ".css", ".ini", ".cfg", ".txt",
                          ".c", ".h", ".cc", ".cpp", ".hpp", ".m", ".vue", ".svelte", ".ipynb"}
POINTER = re.compile(r"`(?P<path>[^`\s:]+?(?P<ext>\.[A-Za-z][A-Za-z0-9]*)):(?P<line>\d+)(?P<tail>(?:[-,:]\d+)*)`")
SITE_POINTER = re.compile(r"^[^`\s:]+\.[A-Za-z][A-Za-z0-9]*:\d+(?:[-,:]\d+)*$")
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "env", "__pycache__", "dist", "build", "vendor", "third_party",
             "target", ".next", ".nuxt", "coverage", "site-packages", ".mypy_cache", ".pytest_cache", ".tox", ".cache"}
TEST_DIRS = {"tests", "test", "__tests__", "spec", "specs", "fixtures", "__mocks__"}
STRONG = {"drex", "model-call", "model-import", "rerank", "fuzzy", "wrapper-call"}
FUNCTION_STRONG = {"drex", "model-call", "rerank", "fuzzy"}
FUNCTION_STRONG = FUNCTION_STRONG | {"wrapper-call"}
FUNCTION_WEAK = {"label-set", "llm-mention", "regex", "model-call", "text-rule", "local-call"}
PROPAGATES = FUNCTION_STRONG | {"local-call"}
MAX_BYTES = 1_000_000
MAX_LINES_PER_FILE = 8
NOT_COUNTED = "not counted"
HEADING = re.compile(r"^\s*(?:#{1,6}\s+(?P<md>.+)|\*\*(?P<bold>[^*]+)\*\*:?\s*)$")
NOT_FUNCTIONS = {"if", "for", "while", "switch", "catch", "return", "function", "with", "elif", "else", "do", "try", "new"}
FUNC_START = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:"
    r"def\s+(?P<py>\w+)|function\s*\*?\s*(?P<js>\w+)|func\s+(?:\([^)]*\)\s*)?(?P<go>\w+)|fn\s+(?P<rs>\w+)|"
    r"(?:const|let|var)\s+(?P<arrow>\w+)\s*(?::[^=]+)?=\s*(?:async\s+)?(?:function\b|\([^)]*\)[^=]*=>|\w+\s*=>)|"
    r"(?:(?:public|private|protected|static|override|readonly|async)\s+)*(?P<method>[A-Za-z_]\w*)\s*\([^)]*\)\s*"
    r"(?::\s*[^{=]+)?\{\s*$)")

SIGNALS = (
    ("drex", re.compile(r"\b(systemone|drex)\b", re.I)),
    ("model-call", re.compile(
        r"chat\.completions\.create|messages\.create|responses\.create|generate_content|"
        r"with_structured_output|response_format|json_schema|\bacompletion\(|litellm\.|\.chat\.complete", re.I)),
    ("decision-name", re.compile(
        r"\b(?:def|function|func|fn|class)\s+\w*(?:classif|categori|route|router|intent|rerank|relevan|judge|grade|"
        r"verif|match|select|detect|triage|adjudicat|decide|label)\w*", re.I)),
    ("model-import", re.compile(
        r"^\s*(?:from|import)\s+(?:openai|anthropic|google\.genai|google\.generativeai|vertexai|litellm|langchain\w*|"
        r"llama_index|pydantic_ai|instructor|dspy|fireworks|mistralai|cohere|groq|ollama|sentence_transformers)\b|"
        r"from\s+['\"](?:openai|@anthropic-ai/sdk|@google/genai|ai|langchain|@langchain/[\w-]+)['\"]")),
    ("llm-mention", re.compile(r"\bllm\w*|\w*_llm\b|\bLLM|judge\.complete|\bAgent\(|\bprompt\b", re.I)),
    ("label-set", re.compile(r"\bLiteral\[\s*['\"]")),
    ("fuzzy", re.compile(r"rapidfuzz|fuzzywuzzy|thefuzz|SequenceMatcher|jaro|levenshtein|\bfuzz\.|get_close_matches", re.I)),
    ("regex", re.compile(r"\bre\.(?:compile|search|match|fullmatch|findall)\(|new RegExp\(")),
    ("rerank", re.compile(r"cross.?encoder|rerank", re.I)),
    ("text-rule", re.compile(r"\.lower\(\)\s*(?:in\b|==|\.startswith|\.endswith)|\bin\s+[\w.]+\.lower\(\)|"
                             r"\bany\(\s*\w+\s+in\s+[\w.]+\s+for\b|\.toLowerCase\(\)\.(?:includes|startsWith)")),
)
WRAPPER_MIN_LEN = 8
WRAPPER_STOP = {"__init__", "__call__", "generate", "complete", "completion", "run_sync", "execute", "process", "create",
                "invoke", "predict", "request", "response", "get_client", "get_model", "from_config", "validate"}


ANY_SIGNAL = re.compile("|".join(f"(?:{pattern.pattern})" for _, pattern in SIGNALS), re.I | re.M)


def list_files(repo):
    try:
        out = subprocess.run(["git", "-C", str(repo), "ls-files", "-co", "--exclude-standard", "-z"],
                             capture_output=True, timeout=60, check=True).stdout.decode("utf-8", "replace")
        files = [f for f in out.split("\0") if f]
        if files:
            return files
    except (OSError, subprocess.SubprocessError):
        pass
    files = []
    for root, dirs, names in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        rel = Path(root).relative_to(repo)
        files.extend((rel / n).as_posix() if str(rel) != "." else n for n in names)
    return files


def is_test(parts, name):
    return (any(p in TEST_DIRS for p in parts[:-1]) or name.startswith("test_")
            or re.search(r"(_test\.\w+|\.(test|spec)\.\w+)$", name) is not None)


def scannable(rel, include_tests):
    parts = Path(rel).parts
    name = parts[-1]
    if Path(name).suffix not in CODE_EXT or name.endswith(".min.js"):
        return False
    if any(p in SKIP_DIRS or p.startswith(".") for p in parts[:-1]):
        return False
    return include_tests or not is_test(parts, name)


def assign_areas(paths):
    """Two path levels when a top folder holds several hit-bearing subfolders, else one."""
    children = {}
    for p in paths:
        parts = Path(p).parts
        if len(parts) > 2:
            children.setdefault(parts[0], set()).add(parts[1])
    areas = {}
    for p in paths:
        parts = Path(p).parts
        split = len(children.get(parts[0], ())) >= 2
        if len(parts) > 2 and split:
            areas[p] = f"{parts[0]}/{parts[1]}"
        elif len(parts) == 2 and split:
            areas[p] = f"{parts[0]}/*"
        else:
            areas[p] = parts[0] if len(parts) > 1 else "."
    return areas


def called_names(node):
    names = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            names.add(func.id if isinstance(func, ast.Name) else getattr(func, "attr", ""))
    return names - {""}


def python_spans(text):
    """(start, end, qualified name, called names) for every Python function, or None when the file does not parse."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    spans = []

    def visit(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                spans.append((child.lineno, getattr(child, "end_lineno", None) or child.lineno, prefix + child.name,
                              called_names(child)))
                visit(child, f"{prefix}{child.name}.")
            elif isinstance(child, ast.ClassDef):
                visit(child, f"{prefix}{child.name}.")
            else:
                visit(child, prefix)
    visit(tree, "")
    return spans


def generic_starts(lines):
    starts = []
    for number, line in enumerate(lines, 1):
        match = FUNC_START.match(line)
        if match:
            name = next(v for v in match.groupdict().values() if v)
            if name not in NOT_FUNCTIONS:
                starts.append((number, name))
    return starts


def by_function(rel, text, found):
    """{(line, qualified name): kinds} for hit lines inside a function.

    In Python, a function that calls a same-file function with a strong signal inherits it as
    `local-call`, repeated until nothing changes. That follows in-house helper chains such as
    generate_dict -> generate -> model call without reading other files."""
    spans = python_spans(text) if rel.endswith(".py") else None
    starts = generic_starts(text.splitlines()) if spans is None else []
    grouped = {}
    for number, kinds in found:
        if spans is not None:
            inside = [s for s in spans if s[0] <= number <= s[1]]
            innermost = max(inside, key=lambda s: s[0]) if inside else None
            owner = (innermost[0], innermost[2]) if innermost else None
        else:
            before = [s for s in starts if s[0] <= number]
            owner = before[-1] if before else None
        if owner:
            grouped.setdefault(owner, set()).update(kinds)
    if spans:
        calls = {(s[0], s[2]): s[3] for s in spans}
        changed = True
        while changed:
            strong = {key[1].split(".")[-1] for key, kinds in grouped.items() if kinds & PROPAGATES}
            changed = False
            for key, names in calls.items():
                kinds = grouped.get(key, set())
                if not kinds & PROPAGATES and names & strong - {key[1].split(".")[-1]}:
                    grouped[key] = kinds | {"local-call"}
                    changed = True
    return grouped


def candidate_functions(rel, text, found):
    """Functions that look like a decision, in line order."""
    out = []
    for (line, name), kinds in sorted(by_function(rel, text, found).items()):
        if kinds & FUNCTION_STRONG or ("decision-name" in kinds and kinds & FUNCTION_WEAK):
            out.append({"name": name, "line": line, "kinds": sorted(kinds)})
    return out


def line_hits(text, wrappers=None):
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        kinds = [kind for kind, pattern in SIGNALS if pattern.search(line)]
        if wrappers is not None and wrappers.search(line) and not FUNC_START.match(line):
            kinds.append("wrapper-call")
        if kinds:
            found.append((number, kinds))
    return found


def keep_file(found):
    kinds = {k for _, ks in found for k in ks}
    return bool(kinds & STRONG or ("decision-name" in kinds and kinds & {"label-set", "llm-mention", "regex"}))


def wrapper_names(rel, text, found):
    """The repository's own model client layer: in files that import a model library, functions that
    reach a model call directly or through same-file helpers."""
    if not any("model-import" in kinds for _, kinds in found):
        return set()
    names = set()
    for (_, qualified), kinds in by_function(rel, text, found).items():
        if kinds & {"model-call", "local-call"}:
            name = qualified.split(".")[-1]
            if len(name) >= WRAPPER_MIN_LEN and name not in WRAPPER_STOP and not name.startswith(("test", "__")):
                names.add(name)
    return names


def read_scannable(repo, listed, include_tests):
    for rel in listed:
        if not scannable(rel, include_tests):
            continue
        path = repo / rel
        try:
            if path.stat().st_size > MAX_BYTES:
                continue
            yield rel, path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue


def scan(repo, include_tests=False, groups=0):
    """Two passes. The first finds direct signals and learns the repository's model wrappers.
    The second marks callers of those wrappers, so decisions behind an in-house client are not missed."""
    repo = Path(repo)
    listed = list_files(repo)
    hits, texts, wrappers, scanned = {}, {}, set(), 0
    for rel, text in read_scannable(repo, listed, include_tests):
        scanned += 1
        if not ANY_SIGNAL.search(text):
            continue
        found = line_hits(text)
        if keep_file(found):
            hits[rel] = found
            texts[rel] = text
            wrappers |= wrapper_names(rel, text, found)
    if wrappers:
        pattern = re.compile(r"\b(?:" + "|".join(sorted(map(re.escape, wrappers))) + r")\s*\(")
        for rel, text in read_scannable(repo, listed, include_tests):
            if pattern.search(text):
                found = line_hits(text, pattern)
                if keep_file(found):
                    hits[rel] = found
                    texts[rel] = text
    areas = assign_areas(list(hits))
    by_area = {}
    functions_total = 0
    for rel, found in sorted(hits.items()):
        entry = by_area.setdefault(areas[rel], {"files": [], "hits": 0, "functions": 0})
        kinds = sorted({k for _, ks in found for k in ks})
        functions = candidate_functions(rel, texts.pop(rel), found)
        entry["files"].append({"path": rel, "kinds": kinds, "functions": functions,
                               "lines": [n for n, _ in found[:MAX_LINES_PER_FILE]], "hits": len(found)})
        entry["hits"] += len(found)
        entry["functions"] += len(functions)
        functions_total += len(functions)
    result = {"repo": str(repo.resolve()), "listed": len(listed), "scanned": scanned, "files_with_hits": len(hits),
              "candidate_functions": functions_total, "wrappers": sorted(wrappers), "areas": by_area}
    if groups > 0:
        result["groups"] = make_groups(by_area, groups)
    return result


def make_groups(by_area, groups):
    """Greedy balance by reading work: one unit per file plus one per candidate function."""
    bins = [{"areas": [], "work": 0} for _ in range(groups)]
    work = {name: len(e["files"]) + e["functions"] for name, e in by_area.items()}
    for name in sorted(by_area, key=lambda n: (-work[n], n)):
        target = min(bins, key=lambda b: b["work"])
        target["areas"].append(name)
        target["work"] += work[name]
    return [b for b in bins if b["areas"]]


def print_scan(result, area=None, group=0):
    """Summary by default. Files only for one --area or one --group, so each helper reads only its share."""
    if area or group:
        names = [area] if area else result["groups"][group - 1]["areas"]
        for name in names:
            entry = result["areas"].get(name)
            if entry is None:
                print(f"no hits in area {name}")
                continue
            print(f"## {name}: {len(entry['files'])} files, {entry['functions']} candidate functions")
            for f in sorted(entry["files"], key=lambda f: f["path"]):
                print(f"{f['path']}  [{','.join(f['kinds'])}]")
                for fn in f["functions"]:
                    print(f"  {f['path']}:{fn['line']}  {fn['name']}  [{','.join(fn['kinds'])}]")
                if not f["functions"]:
                    print(f"  no candidate function, hit lines {','.join(map(str, f['lines']))}")
        return
    print(f"signal scan: {result['listed']} files listed, {result['scanned']} scanned, "
          f"{result['files_with_hits']} with strong hits, {result['candidate_functions']} candidate functions, "
          f"{len(result['areas'])} areas")
    for name, entry in sorted(result["areas"].items(), key=lambda kv: (-kv[1]["functions"], kv[0])):
        print(f"{name}: {len(entry['files'])} files, {entry['functions']} candidate functions")
    for i, g in enumerate(result.get("groups", []), 1):
        print(f"group {i} (work {g['work']}): {' '.join(g['areas'])}")


def line_counts(repo, files, cache):
    def count(rel):
        if rel not in cache:
            try:
                cache[rel] = len((repo / rel).read_text(encoding="utf-8", errors="ignore").splitlines())
            except OSError:
                cache[rel] = 0
        return cache[rel]
    return count


def resolve(raw, line, files, by_suffix, count):
    """Return (full_path or None, problem or None)."""
    if raw in files:
        return (raw, None) if 1 <= line <= count(raw) else (None, f"line {line} is past the end of {raw}")
    if "{" in raw or "}" in raw:
        return None, "brace groups cannot be checked, write each path in full"
    tail = raw.split(".../")[-1].split("…/")[-1].lstrip("./")
    matches = sorted(f for f in by_suffix.get(Path(tail).name, ()) if f == tail or f.endswith("/" + tail))
    if not matches:
        return None, "no such file"
    if len(matches) > 1:
        return None, f"ambiguous, matches {len(matches)} files: {', '.join(matches[:3])}"
    if not 1 <= line <= count(matches[0]):
        return None, f"line {line} is past the end of {matches[0]}"
    return matches[0], None


def check(report_path, repo, fix=False):
    repo = Path(repo)
    from_stdin = str(report_path) == "-"
    text = sys.stdin.read() if from_stdin else Path(report_path).read_text(encoding="utf-8")
    files = set(list_files(repo))
    by_suffix = {}
    for f in files:
        by_suffix.setdefault(Path(f).name, []).append(f)
    count = line_counts(repo, files, {})
    problems, fixed = [], []

    def repl(match):
        if match.group("ext").lower() not in POINTER_EXT:
            return match.group(0)
        raw, line = match.group("path"), int(match.group("line"))
        full, problem = resolve(raw, line, files, by_suffix, count)
        if problem:
            problems.append(f"`{raw}:{line}`: {problem}")
            return match.group(0)
        if full != raw:
            fixed.append(f"{raw} -> {full}")
            return f"`{full}:{line}{match.group('tail')}`"
        return match.group(0)

    new_text = POINTER.sub(repl, text)
    if fix and not from_stdin and new_text != text:
        Path(report_path).write_text(new_text, encoding="utf-8")
    if (not fix or from_stdin) and fixed:
        problems.extend(f"shortened path, run with --fix: {f}" for f in fixed)

    tally = {s: 0 for s in STATUSES}
    seen = {}
    sites = 0
    counted = True
    for number, line in enumerate(new_text.splitlines(), 1):
        heading = HEADING.match(line)
        if heading:
            counted = NOT_COUNTED not in (heading.group("md") or heading.group("bold")).lower()
            continue
        site = SITE.match(line)
        if not site or not counted:
            continue
        rest = site.group("rest").strip().lower()
        status = next((s for s in STATUSES if rest.startswith(s.lower())), None)
        if status is None:
            problems.append(f"line {number}: status must start with one of: {', '.join(STATUSES)}")
            continue
        sites += 1
        tally[status] += 1
        ptr = site.group("ptr")
        if not SITE_POINTER.match(ptr):
            problems.append(f"line {number}: site pointer `{ptr}` must be a full `path:line`")
        if ptr in seen:
            problems.append(f"line {number}: `{ptr}` is already listed on line {seen[ptr]}")
        seen.setdefault(ptr, number)

    headline = HEADLINE.search(new_text)
    if not headline:
        problems.append("headline not found. Use: Identified N sites of drexification "
                        "(A already on Drex, B partial, C implemented now, D candidates)")
    else:
        total, on, part, done, cand = map(int, headline.groups())
        claimed = {"already on Drex": on, "partial": part, "implemented now": done, "candidate": cand}
        if on + part + done + cand != total:
            problems.append(f"headline total {total} does not equal the sum of its statuses")
        if sites != total:
            problems.append(f"headline says {total} sites, the list has {sites}")
        for status in STATUSES:
            if claimed[status] != tally[status]:
                problems.append(f"headline says {claimed[status]} {status}, the list has {tally[status]}")
    return {"sites": sites, "statuses": tally, "pointers_fixed": fixed if fix and not from_stdin else [], "problems": problems}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("scan", help="signal search over the repository, grouped by area")
    s.add_argument("--repo", default=".")
    s.add_argument("--include-tests", action="store_true")
    s.add_argument("--groups", type=int, default=0, help="split areas into N balanced groups for parallel helpers")
    s.add_argument("--group", type=int, default=0, help="with --groups, print the files of group K only")
    s.add_argument("--area", help="print the files of one area only")
    s.add_argument("--save", metavar="FILE", help="also write the full map as JSON, for helpers to read with --from")
    s.add_argument("--from", dest="source", metavar="FILE", help="read a map written by --save instead of searching again")
    s.add_argument("--json", action="store_true")
    c = sub.add_parser("check", help="lint a drexify report")
    c.add_argument("report", help="report file, or - to read it from stdin (no --fix)")
    c.add_argument("--repo", default=".")
    c.add_argument("--fix", action="store_true", help="rewrite shortened paths that resolve to one file")
    c.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "scan":
        if args.source:
            result = json.loads(Path(args.source).read_text(encoding="utf-8"))
            if args.groups and len(result.get("groups", [])) != args.groups:
                result["groups"] = make_groups(result["areas"], args.groups)
        else:
            result = scan(args.repo, args.include_tests, args.groups)
        if args.save:
            Path(args.save).write_text(json.dumps(result), encoding="utf-8")
        if args.group and not 1 <= args.group <= len(result.get("groups", [])):
            parser.error("--group K needs --groups N with 1 <= K <= number of groups")
        print(json.dumps(result, indent=1)) if args.json else print_scan(result, args.area, args.group)
        return 0
    result = check(args.report, args.repo, args.fix)
    if args.json:
        print(json.dumps(result, indent=1))
    else:
        counts = ", ".join(f"{n} {'candidates' if s == 'candidate' else s}" for s, n in result["statuses"].items())
        print(f"{result['sites']} sites ({counts})")
        for f in result["pointers_fixed"]:
            print(f"fixed: {f}")
        for p in result["problems"]:
            print(f"problem: {p}")
        print("ok" if not result["problems"] else f"{len(result['problems'])} problems")
    return 0 if not result["problems"] else 1


if __name__ == "__main__":
    sys.exit(main())
