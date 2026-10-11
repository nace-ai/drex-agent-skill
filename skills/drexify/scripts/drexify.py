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
SCHEMA = 2
DIRECT = {"drex", "model-call", "rerank", "fuzzy"}
STRONG = DIRECT | {"model-import", "wrapper-call"}
FUNCTION_STRONG = DIRECT | {"wrapper-call"}
FUNCTION_WEAK = {"label-set", "llm-mention", "regex", "text-rule", "local-call"}
MODEL_REACH = {"model-call", "wrapper-call", "model-reach"}
MAX_BYTES = 1_000_000
MAX_LINES_PER_FILE = 8
FUNCTIONS_PER_HELPER = 350
MAX_GROUPS = 6
HEADING = re.compile(r"^\s*(?:#{1,6}\s+(?P<md>.+)|\*\*(?P<bold>[^*]+)\*\*:?\s*)$")
DECISION_WORDS = (r"classif|categori|route|router|intent|rerank|relevan|judge|grade|verif|match|select|detect|triage|"
                  r"adjudicat|decide|label")
DECISION_NAME = re.compile(DECISION_WORDS, re.I)
NOT_FUNCTIONS = {"if", "for", "foreach", "while", "switch", "catch", "return", "function", "with", "elif", "else", "do",
                 "try", "new", "using", "lock", "synchronized", "when", "match", "sizeof", "typeof", "await", "throw"}
MODIFIERS = (r"(?:(?:export|default|public|private|protected|internal|static|final|abstract|override|readonly|async|"
             r"suspend|open|virtual|sealed|inline|unsafe|extern|pub(?:\([^)]*\))?)\s+)*")
TYPE_TOKEN = r"(?!(?:new|return|await|throw|else|case|class|interface|enum|struct)\b)[\w<>\[\],.?]+\s+"
FUNC_START = re.compile(
    r"^\s*" + MODIFIERS + r"(?:"
    r"def\s+(?:self\.)?(?P<py>\w+)"
    r"|function\s*\*?\s*(?P<js>\w+)"
    r"|func\s+(?:\([^)]*\)\s*)?(?P<go>\w+)"
    r"|fn\s+(?P<rs>\w+)"
    r"|fun\s+(?:<[^>]*>\s*)?(?:[\w.]+\.)?(?P<kt>\w+)"
    r"|(?:const|let|var)\s+(?P<arrow>\w+)\s*(?::[^=]+)?=\s*(?:async\s+)?"
    r"(?:function\b|(?:<[^>]*>)?\s*\((?:[^()]|\([^()]*\))*\)[^=]*=>|(?:<[^>]*>)?\s*\(\s*$|\w+\s*=>)"
    r"|(?:(?:get|set)\s+)?(?:" + TYPE_TOKEN + r")?(?P<method>[A-Za-z_]\w*)\s*(?:<[^>]*>)?\s*"
    r"\((?:[^()]|\([^()]*\))*\)\s*(?::\s*[^{=;]+)?(?:throws\s+[\w., ]+)?\s*\{\s*$"
    r"|(?:(?:public|private|protected|static|async|override|internal)\s+)+(?:" + TYPE_TOKEN + r")?"
    r"(?P<open>[A-Za-z_]\w*)\s*(?:<[^>]*>)?\s*\(\s*$"
    r")")
CALL_NAME = re.compile(r"\b([A-Za-z_]\w*)\s*\(")
LONG_CALL = re.compile(r"\b([A-Za-z]\w{7,})\s*\(")
DEF_NAME = re.compile(r"\b(?:def|function|func|fn|fun)\s+(\w+)")
STRING_OR_COMMENT = re.compile(r"\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|`[^`]*`|//.*$|(?:^|\s)#.*$")

SIGNALS = (
    ("drex", re.compile(r"\b(systemone|drex)\b", re.I)),
    ("model-call", re.compile(
        r"chat\.completions\.create|messages\.create|responses\.create|generate_content|"
        r"with_structured_output|response_format|\bjson_schema\b|\bacompletion\(|litellm\.|\.chat\.complete", re.I)),
    ("decision-name", re.compile(r"\b(?:def|function|func|fn|fun|class)\s+\w*(?:" + DECISION_WORDS + r")\w*", re.I)),
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
WRAPPER_STOP = {"generate", "complete", "completion", "run_sync", "execute", "process", "create", "invoke", "predict",
                "request", "response", "get_client", "get_model", "from_config", "validate"}


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


def git_state(repo):
    """(HEAD commit, has uncommitted changes), or (None, None) outside git."""
    try:
        head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, timeout=30,
                              check=True).stdout.decode().strip()
        dirty = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"],
                               capture_output=True, timeout=60, check=True).stdout.strip() != b""
        return head, dirty
    except (OSError, subprocess.SubprocessError):
        return None, None


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
    """[(start, end, qualified name, called names)] for every Python function, or None when the file does not parse."""
    containers = (ast.stmt, ast.excepthandler) + ((ast.match_case,) if hasattr(ast, "match_case") else ())
    try:
        tree = ast.parse(text)
        spans = []

        def visit(node, prefix):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    spans.append((child.lineno, getattr(child, "end_lineno", None) or child.lineno,
                                  prefix + child.name, called_names(child)))
                    visit(child, f"{prefix}{child.name}.")
                elif isinstance(child, ast.ClassDef):
                    visit(child, f"{prefix}{child.name}.")
                elif isinstance(child, containers):
                    visit(child, prefix)
        visit(tree, "")
        return spans
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None


def generic_starts(lines):
    starts = []
    for number, line in enumerate(lines, 1):
        match = FUNC_START.match(line)
        if match:
            name = next(v for v in match.groupdict().values() if v)
            if name not in NOT_FUNCTIONS:
                starts.append((number, name))
    return starts


def generic_spans(lines):
    """Function spans for brace languages by brace depth. Without braces, a span runs to the next start."""
    starts = generic_starts(lines)
    spans = []
    for index, (line, name) in enumerate(starts):
        limit = starts[index + 1][0] - 1 if index + 1 < len(starts) else len(lines)
        depth, opened, end = 0, False, None
        for i in range(line - 1, len(lines)):
            code = STRING_OR_COMMENT.sub("", lines[i])
            depth += code.count("{") - code.count("}")
            opened = opened or "{" in code
            if opened and depth <= 0:
                end = i + 1
                break
            if not opened and i - line > 8:
                break
        end = end or limit
        body = "\n".join(lines[line - 1:end])
        spans.append((line, end, name, set(CALL_NAME.findall(body)) - NOT_FUNCTIONS))
    return spans


def file_spans(rel, text):
    """(spans, parsed) where parsed is False when a Python file fell back to the generic finder."""
    if rel.endswith(".py"):
        spans = python_spans(text)
        if spans is not None:
            return spans, True
        return generic_spans(text.splitlines()), False
    return generic_spans(text.splitlines()), True


def owner_of(spans, number):
    inside = [s for s in spans if s[0] <= number <= s[1]]
    return max(inside, key=lambda s: s[0]) if inside else None


def short(qualified):
    return qualified.split(".")[-1]


def propagate(grouped, calls, seeds, tag):
    """A function that calls a same-file function carrying a seed kind inherits `tag`, until nothing changes."""
    marks = seeds | {tag}
    changed = True
    while changed:
        reach = {short(key[1]) for key, kinds in grouped.items() if kinds & marks}
        changed = False
        for key, names in calls.items():
            kinds = grouped.get(key, set())
            if not kinds & marks and names & (reach - {short(key[1])}):
                grouped[key] = kinds | {tag}
                changed = True


def by_function(spans, found):
    """{(line, qualified name): kinds} for hit lines inside a function, plus same-file call propagation.

    `local-call` follows any strong signal, for decision-named functions built on a same-file helper.
    `model-reach` follows model calls only, for learning the repository's model wrappers."""
    grouped = {}
    for number, kinds in found:
        owner = owner_of(spans, number)
        if owner:
            grouped.setdefault((owner[0], owner[2]), set()).update(kinds)
    calls = {(s[0], s[2]): s[3] for s in spans}
    propagate(grouped, calls, FUNCTION_STRONG, "local-call")
    propagate(grouped, calls, {"model-call", "wrapper-call"}, "model-reach")
    return grouped


def candidate_functions(spans, found):
    """Functions that look like a decision, in line order."""
    out = []
    for (line, name), kinds in sorted(by_function(spans, found).items()):
        if kinds & FUNCTION_STRONG or (DECISION_NAME.search(name) and kinds & FUNCTION_WEAK):
            out.append({"name": name, "line": line, "kinds": sorted(kinds - {"model-reach"})})
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


def wrapper_names(spans, found):
    """The repository's own model client layer: public, non-decision functions in files that import a model
    library and reach a model call directly or through same-file helpers."""
    if not any("model-import" in kinds for _, kinds in found):
        return set()
    names = set()
    for (_, qualified), kinds in by_function(spans, found).items():
        name = short(qualified)
        if (kinds & MODEL_REACH and len(name) >= WRAPPER_MIN_LEN and name not in WRAPPER_STOP
                and not name.startswith(("_", "test")) and not DECISION_NAME.search(name)):
            names.add(name)
    return names


def read_scannable(repo, rels):
    for rel in rels:
        path = repo / rel
        try:
            if path.stat().st_size > MAX_BYTES:
                continue
            yield rel, path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue


def suggested_groups(functions):
    return max(1, min(MAX_GROUPS, -(-functions // FUNCTIONS_PER_HELPER)))


def scan(repo, include_tests=False, groups=None):
    """Two passes. The first finds direct signals and learns the repository's model wrappers.
    The second marks callers of those wrappers, so decisions behind an in-house client are not missed."""
    repo = Path(repo)
    listed = list_files(repo)
    rels = [rel for rel in listed if scannable(rel, include_tests)]
    hits, texts, spans, wrappers, scanned, fallbacks = {}, {}, {}, set(), 0, 0

    def remember(rel, text, found):
        nonlocal fallbacks
        hits[rel], texts[rel] = found, text
        if rel not in spans:
            spans[rel], parsed = file_spans(rel, text)
            fallbacks += not parsed

    for rel, text in read_scannable(repo, rels):
        scanned += 1
        if not ANY_SIGNAL.search(text):
            continue
        found = line_hits(text)
        if keep_file(found):
            remember(rel, text, found)
            wrappers |= wrapper_names(spans[rel], found)
    if wrappers:
        callers, defined = [], {}
        for rel, text in read_scannable(repo, rels):
            for name in set(DEF_NAME.findall(text)) & wrappers:
                defined[name] = defined.get(name, 0) + 1
            if set(LONG_CALL.findall(text)) & wrappers:
                callers.append(rel)
        wrappers = {name for name in wrappers if defined.get(name, 0) <= 1}
        pattern = re.compile(r"\b(?:" + "|".join(sorted(map(re.escape, wrappers))) + r")\s*\(") if wrappers else None
        for rel, text in read_scannable(repo, callers if pattern else []):
            if pattern.search(text):
                found = line_hits(text, pattern)
                if keep_file(found):
                    remember(rel, text, found)
    areas = assign_areas(list(hits))
    by_area = {}
    functions_total = 0
    for rel, found in sorted(hits.items()):
        entry = by_area.setdefault(areas[rel], {"files": [], "hits": 0, "functions": 0})
        kinds = sorted({k for _, ks in found for k in ks})
        functions = candidate_functions(spans.pop(rel), found)
        texts.pop(rel)
        entry["files"].append({"path": rel, "kinds": kinds, "functions": functions,
                               "lines": [n for n, _ in found[:MAX_LINES_PER_FILE]], "hits": len(found)})
        entry["hits"] += len(found)
        entry["functions"] += len(functions)
        functions_total += len(functions)
    head, dirty = git_state(repo)
    count = groups or suggested_groups(functions_total)
    by_area = split_heavy(by_area, count)
    return {"schema": SCHEMA, "repo": str(repo.resolve()), "head": head, "dirty": dirty, "include_tests": include_tests,
            "python": ".".join(map(str, sys.version_info[:2])), "listed": len(listed), "scanned": scanned,
            "files_with_hits": len(hits), "candidate_functions": functions_total, "python_parse_fallbacks": fallbacks,
            "wrappers": sorted(wrappers), "suggested_groups": suggested_groups(functions_total), "areas": by_area,
            "groups": make_groups(by_area, count)}


def area_work(entry):
    return len(entry["files"]) + entry["functions"]


def split_heavy(by_area, groups, slack=1.2):
    """Split any area heavier than its share of the work by the next folder level, until it fits or cannot split."""
    out = dict(by_area)
    target = sum(area_work(e) for e in out.values()) / max(groups, 1) * slack
    queue = sorted(name for name, e in out.items() if area_work(e) > target)
    while queue:
        name = queue.pop()
        files = out[name]["files"]
        if len(files) < 2:
            continue
        depth = len(Path(os.path.commonpath([f["path"] for f in files])).parts)
        parts = {}
        for f in files:
            p = Path(f["path"]).parts
            key = "/".join(p[:depth + 1]) if len(p) > depth + 1 else "/".join(p[:depth]) + "/*"
            parts.setdefault(key, []).append(f)
        if len(parts) < 2:
            continue
        del out[name]
        for key, chunk in sorted(parts.items()):
            out[key] = {"files": chunk, "hits": sum(f["hits"] for f in chunk),
                        "functions": sum(len(f["functions"]) for f in chunk)}
            if area_work(out[key]) > target:
                queue.append(key)
    return out


def make_groups(by_area, groups):
    """Greedy balance by reading work: one unit per file plus one per candidate function."""
    bins = [{"areas": [], "work": 0} for _ in range(groups)]
    work = {name: area_work(e) for name, e in by_area.items()}
    for name in sorted(by_area, key=lambda n: (-work[n], n)):
        target = min(bins, key=lambda b: b["work"])
        target["areas"].append(name)
        target["work"] += work[name]
    return [b for b in bins if b["areas"]]


def load_map(path, repo, include_tests):
    result = json.loads(Path(path).read_text(encoding="utf-8"))
    if result.get("schema") != SCHEMA:
        raise SystemExit(f"{path} was written by another version of this script. Run scan --save again.")
    if include_tests and not result["include_tests"]:
        raise SystemExit(f"{path} was saved without --include-tests. Run scan --save again with it.")
    if repo is not None and Path(repo).resolve() != Path(result["repo"]):
        raise SystemExit(f"{path} is a map of {result['repo']}, not {Path(repo).resolve()}.")
    head, _ = git_state(result["repo"])
    if head and result["head"] and head != result["head"]:
        print(f"warning: {result['repo']} moved from {result['head'][:12]} to {head[:12]} since the map was saved. "
              f"Run scan --save again for exact results.", file=sys.stderr)
    return result


def print_scan(result, area=None, group=0):
    """Summary by default. Files only for one --area or one --group, so each helper reads only its share."""
    if area or group:
        names = [area] if area else result["groups"][group - 1]["areas"]
        entries = [result["areas"][n] for n in names if n in result["areas"]]
        files = [f for e in entries for f in e["files"]]
        label = f"group {group}" if group else f"area {area}"
        print(f"# {label}: {len(names)} areas, {len(files)} files, "
              f"{sum(len(f['functions']) for f in files)} candidate functions, "
              f"{sum(1 for f in files if not f['functions'])} files without one")
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
    if result["python_parse_fallbacks"]:
        print(f"{result['python_parse_fallbacks']} Python files did not parse on Python {result['python']} "
              f"and used the generic function finder")
    for name, entry in sorted(result["areas"].items(), key=lambda kv: (-kv[1]["functions"], kv[0])):
        print(f"{name}: {len(entry['files'])} files, {entry['functions']} candidate functions")
    print(f"{len(result['groups'])} groups (suggested {result['suggested_groups']}):")
    for i, g in enumerate(result["groups"], 1):
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


UNCOUNTED_SECTIONS = ("not counted", "plan")


def is_not_counted(heading):
    title = (heading.group("md") or heading.group("bold")).strip().rstrip(":").strip().lower()
    return title.startswith(UNCOUNTED_SECTIONS)


def site_start(repo, rel, line, cache):
    """(first line of the function holding `line`, problem). A blank, comment, or decorator line just above a
    function snaps to it.
    Python is exact. Other languages only snap when a function is found, because their finder can miss shapes."""
    if Path(rel).suffix not in CODE_EXT:
        return line, None
    if rel not in cache:
        try:
            text = (repo / rel).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            text = ""
        cache[rel] = (*file_spans(rel, text), text.splitlines())
    spans, parsed, lines = cache[rel]
    def preamble(i):
        text = lines[i].strip()
        return not text or text.startswith(("@", "#", "//", "/*", "*", ")"))

    if 1 <= line <= len(lines) and preamble(line - 1):
        below = [s[0] for s in spans if s[0] > line]
        if below and all(preamble(i) for i in range(line, min(below) - 1)):
            return min(below), None
    owner = owner_of(spans, line)
    if owner is None:
        if 1 <= line <= len(lines) and re.match(r"\s*class\s", lines[line - 1]):
            return line, None
        if rel.endswith(".py") and parsed:
            return line, "is not inside a function. Point at the decision function"
        return line, None
    return owner[0], None


def check(report_path, repo, fix=False):
    repo = Path(repo)
    from_stdin = str(report_path) == "-"
    text = sys.stdin.read() if from_stdin else Path(report_path).read_text(encoding="utf-8")
    writable = fix and not from_stdin
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

    lines = POINTER.sub(repl, text).split("\n")
    tally = {s: 0 for s in STATUSES}
    seen, spans_cache = {}, {}
    sites = 0
    counted = True
    for index, line in enumerate(lines):
        number = index + 1
        heading = HEADING.match(line)
        if heading:
            counted = not is_not_counted(heading)
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
        else:
            rel, at = ptr.split(":")[0], int(ptr.split(":")[1])
            if rel in files:
                start, problem = site_start(repo, rel, at, spans_cache)
                if problem:
                    problems.append(f"line {number}: `{ptr}` {problem}")
                elif start != at:
                    moved = f"{rel}:{start}"
                    if writable:
                        lines[index] = line.replace(f"(`{ptr}`)", f"(`{moved}`)", 1)
                        fixed.append(f"{ptr} -> {moved}")
                        ptr = moved
                    else:
                        problems.append(f"line {number}: `{ptr}` is inside a function that starts at line {start}, "
                                        f"run with --fix to point at it")
        if ptr in seen:
            problems.append(f"line {number}: `{ptr}` is already listed on line {seen[ptr]}")
        seen.setdefault(ptr, number)

    new_text = "\n".join(lines)
    if writable and new_text != text:
        Path(report_path).write_text(new_text, encoding="utf-8")
    if not writable and fixed:
        problems.extend(f"shortened path, run with --fix: {f}" for f in fixed)

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
    return {"sites": sites, "statuses": tally, "pointers_fixed": fixed if writable else [], "problems": problems}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("scan", help="signal search over the repository, grouped by area")
    s.add_argument("--repo")
    s.add_argument("--include-tests", action="store_true")
    s.add_argument("--groups", type=int, help="split areas into N balanced groups (default: suggested from the size)")
    s.add_argument("--group", type=int, default=0, help="print the files of group K only")
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
            result = load_map(args.source, args.repo, args.include_tests)
            if args.groups and args.groups != len(result["groups"]):
                result["areas"] = split_heavy(result["areas"], args.groups)
                result["groups"] = make_groups(result["areas"], args.groups)
        else:
            result = scan(args.repo or ".", args.include_tests, args.groups)
        if args.save:
            save = Path(args.save)
            partial = save.with_name(save.name + ".tmp")
            partial.write_text(json.dumps(result), encoding="utf-8")
            os.replace(partial, save)
        if args.group and not 1 <= args.group <= len(result["groups"]):
            parser.error(f"--group K needs 1 <= K <= {len(result['groups'])}, the number of groups in this map")
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
