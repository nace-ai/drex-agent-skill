#!/usr/bin/env python3
"""Drexify helper. Python 3.9+, standard library only. Reads files, never calls a model or the network.

scan:  one cheap signal search over the whole repository, grouped by area.
check: lint a drexify report. Counts must match the headline, statuses must be valid,
       and every `path:line` pointer must resolve. --fix rewrites shortened paths.
"""
import argparse
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
POINTER = re.compile(r"`(?P<path>[^`\s]+?\.[A-Za-z0-9]+):(?P<line>\d+)(?P<tail>(?:[-,:]\d+)*)`")

CODE_EXT = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".go", ".java", ".kt", ".rb", ".rs", ".cs", ".php", ".scala", ".swift"}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "env", "__pycache__", "dist", "build", "vendor", "third_party",
             "target", ".next", ".nuxt", "coverage", "site-packages", ".mypy_cache", ".pytest_cache", ".tox", ".cache"}
TEST_DIRS = {"tests", "test", "__tests__", "spec", "specs", "fixtures", "__mocks__"}
STRONG = {"drex", "model-call", "model-import", "rerank", "fuzzy"}
MAX_BYTES = 1_000_000
MAX_LINES_PER_FILE = 8

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
)


def list_files(repo):
    try:
        out = subprocess.run(["git", "-C", str(repo), "ls-files", "-co", "--exclude-standard", "-z"],
                             capture_output=True, text=True, timeout=60, check=True).stdout
        files = [f for f in out.split("\0") if f]
        if files:
            return files
    except (OSError, subprocess.SubprocessError):
        pass
    files = []
    for root, dirs, names in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        rel = Path(root).relative_to(repo)
        files.extend(str(rel / n) if str(rel) != "." else n for n in names)
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
        if len(parts) > 2 and len(children.get(parts[0], ())) >= 2:
            areas[p] = f"{parts[0]}/{parts[1]}"
        else:
            areas[p] = parts[0] if len(parts) > 1 else "."
    return areas


def scan(repo, include_tests=False, groups=0):
    repo = Path(repo)
    listed = list_files(repo)
    hits = {}
    scanned = 0
    for rel in listed:
        if not scannable(rel, include_tests):
            continue
        path = repo / rel
        try:
            if path.stat().st_size > MAX_BYTES:
                continue
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        scanned += 1
        found = []
        for number, line in enumerate(text.splitlines(), 1):
            kinds = [kind for kind, pattern in SIGNALS if pattern.search(line)]
            if kinds:
                found.append((number, kinds))
        kinds = {k for _, ks in found for k in ks}
        if kinds & STRONG or ("decision-name" in kinds and kinds & {"label-set", "llm-mention", "regex"}):
            hits[rel] = found
    areas = assign_areas(list(hits))
    by_area = {}
    for rel, found in sorted(hits.items()):
        entry = by_area.setdefault(areas[rel], {"files": [], "hits": 0})
        kinds = sorted({k for _, ks in found for k in ks})
        entry["files"].append({"path": rel, "kinds": kinds, "lines": [n for n, _ in found[:MAX_LINES_PER_FILE]],
                               "hits": len(found)})
        entry["hits"] += len(found)
    result = {"listed": len(listed), "scanned": scanned, "files_with_hits": len(hits), "areas": by_area}
    if groups > 0:
        bins = [{"areas": [], "hits": 0} for _ in range(groups)]
        for name, entry in sorted(by_area.items(), key=lambda kv: -kv[1]["hits"]):
            target = min(bins, key=lambda b: b["hits"])
            target["areas"].append(name)
            target["hits"] += entry["hits"]
        result["groups"] = [b for b in bins if b["areas"]]
    return result


def print_scan(result, area=None, group=0):
    """Summary by default. Files only for one --area or one --group, so each helper reads only its share."""
    if area or group:
        names = [area] if area else result["groups"][group - 1]["areas"]
        for name in names:
            entry = result["areas"].get(name)
            if entry is None:
                print(f"no hits in area {name}")
                continue
            print(f"## {name}: {len(entry['files'])} files, {entry['hits']} hits")
            for f in sorted(entry["files"], key=lambda f: -f["hits"]):
                print(f"{f['path']}  [{','.join(f['kinds'])}]  lines {','.join(map(str, f['lines']))}")
        return
    print(f"signal scan: {result['listed']} files listed, {result['scanned']} scanned, "
          f"{result['files_with_hits']} with strong hits, {len(result['areas'])} areas")
    for name, entry in sorted(result["areas"].items(), key=lambda kv: -kv[1]["hits"]):
        print(f"{name}: {len(entry['files'])} files, {entry['hits']} hits")
    for i, g in enumerate(result.get("groups", []), 1):
        print(f"group {i} ({g['hits']} hits): {' '.join(g['areas'])}")


def line_counts(repo, files, cache):
    def count(rel):
        if rel not in cache:
            try:
                cache[rel] = len((repo / rel).read_text(errors="ignore").splitlines())
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
    matches = [f for f in by_suffix.get(Path(tail).name, ()) if f == tail or f.endswith("/" + tail)]
    fitting = [f for f in matches if 1 <= line <= count(f)]
    if len(fitting) == 1:
        return fitting[0], None
    if not matches:
        return None, "no such file"
    if not fitting:
        return None, f"line {line} is past the end of every match"
    return None, f"ambiguous, matches {len(fitting)} files"


def check(report_path, repo, fix=False):
    repo = Path(repo)
    report_path = Path(report_path)
    text = report_path.read_text()
    files = set(list_files(repo))
    by_suffix = {}
    for f in files:
        by_suffix.setdefault(Path(f).name, []).append(f)
    count = line_counts(repo, files, {})
    problems, fixed = [], []

    def repl(match):
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
    if fix and new_text != text:
        report_path.write_text(new_text)
    if not fix and fixed:
        problems.extend(f"shortened path, run with --fix: {f}" for f in fixed)

    tally = {s: 0 for s in STATUSES}
    seen = {}
    sites = 0
    for number, line in enumerate(new_text.splitlines(), 1):
        site = SITE.match(line)
        if not site:
            continue
        rest = site.group("rest").strip().lower()
        status = next((s for s in STATUSES if rest.startswith(s.lower())), None)
        if status is None:
            problems.append(f"line {number}: status must start with one of: {', '.join(STATUSES)}")
            continue
        sites += 1
        tally[status] += 1
        ptr = site.group("ptr")
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
    return {"sites": sites, "statuses": tally, "pointers_fixed": fixed if fix else [], "problems": problems}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("scan", help="signal search over the repository, grouped by area")
    s.add_argument("--repo", default=".")
    s.add_argument("--include-tests", action="store_true")
    s.add_argument("--groups", type=int, default=0, help="split areas into N balanced groups for parallel helpers")
    s.add_argument("--group", type=int, default=0, help="with --groups, print the files of group K only")
    s.add_argument("--area", help="print the files of one area only")
    s.add_argument("--json", action="store_true")
    c = sub.add_parser("check", help="lint a drexify report")
    c.add_argument("report")
    c.add_argument("--repo", default=".")
    c.add_argument("--fix", action="store_true", help="rewrite shortened paths that resolve to one file")
    c.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "scan":
        result = scan(args.repo, args.include_tests, args.groups)
        if args.group and not 1 <= args.group <= len(result.get("groups", [])):
            parser.error("--group K needs --groups N with 1 <= K <= number of groups")
        print(json.dumps(result, indent=1)) if args.json else print_scan(result, args.area, args.group)
        return 0
    result = check(args.report, args.repo, args.fix)
    if args.json:
        print(json.dumps(result, indent=1))
    else:
        counts = ", ".join(f"{n} {s}" for s, n in result["statuses"].items())
        print(f"{result['sites']} sites ({counts})")
        for f in result["pointers_fixed"]:
            print(f"fixed: {f}")
        for p in result["problems"]:
            print(f"problem: {p}")
        print("ok" if not result["problems"] else f"{len(result['problems'])} problems")
    return 0 if not result["problems"] else 1


if __name__ == "__main__":
    sys.exit(main())
