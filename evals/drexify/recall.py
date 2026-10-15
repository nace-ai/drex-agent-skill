#!/usr/bin/env python3
"""Recall of the drexify scan against known decision sites. Python 3.9+, standard library only.

Checks out each pinned repo under the cache, or reuses a checkout already at that
commit, then runs drexify.py scan (never with --include-tests). A known site counts
when its path and function name are on the candidate list. The flagged-files column counts
known sites whose file the scan flagged, which agents open even without a candidate. Repos with no sites report
candidate counts only. --extra scans a local repo and reports its candidate count.

    python3 evals/drexify/recall.py
    python3 evals/drexify/recall.py --cache /tmp/drexify-oss
    python3 evals/drexify/recall.py --repo crewAI --strict
    python3 evals/drexify/recall.py --extra /path/to/repo --json
    python3 evals/drexify/recall.py --baseline before.json

--baseline compares with an earlier --json report made with the same answer key. It lists
known sites that report found and this scan misses, and exits 1 when there are any.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DREXIFY = ROOT / "skills" / "drexify" / "scripts" / "drexify.py"
DEFAULT_KNOWN = Path(__file__).resolve().parent / "known_sites.json"
DEFAULT_CACHE = Path.home() / ".cache" / "drexify-evals"


def git_out(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def git_head(repo):
    """Full HEAD commit, or None when `repo` is not a checkout with a commit."""
    if not Path(repo).is_dir():
        return None
    result = git_out(repo, "rev-parse", "HEAD")
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def run(cmd, cwd):
    result = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise SystemExit(f"command failed ({' '.join(cmd)}): {detail}")
    return result


def ensure_checkout(cache, spec):
    """Reuse `<cache>/<name>` when its HEAD is the pinned commit. Otherwise fetch that commit."""
    dest = Path(cache) / spec["name"]
    want = spec["commit"]
    if git_head(dest) == want:
        return dest
    dest.mkdir(parents=True, exist_ok=True)
    if not (dest / ".git").exists():
        if any(dest.iterdir()):
            raise SystemExit(f"{dest} exists and is not a git checkout at {want}")
        run(["git", "init"], dest)
        run(["git", "remote", "add", "origin", spec["url"]], dest)
    else:
        remotes = git_out(dest, "remote").stdout.split()
        if "origin" in remotes:
            run(["git", "remote", "set-url", "origin", spec["url"]], dest)
        else:
            run(["git", "remote", "add", "origin", spec["url"]], dest)
    run(["git", "fetch", "--depth", "1", "origin", want], dest)
    run(["git", "checkout", "--detach", "FETCH_HEAD"], dest)
    got = git_head(dest)
    if got != want:
        raise SystemExit(f"{dest} is at {got}, not {want}")
    return dest


def scan_repo(repo):
    """Run this checkout's drexify scan. Returns (map, seconds)."""
    handle, name = tempfile.mkstemp(prefix="drexify-recall-", suffix=".json")
    os.close(handle)
    path = Path(name)
    try:
        started = time.perf_counter()
        result = subprocess.run(
            [sys.executable, str(DREXIFY), "scan", "--repo", str(repo), "--save", str(path)],
            capture_output=True, text=True,
        )
        seconds = round(time.perf_counter() - started, 2)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise SystemExit(f"scan failed for {repo}: {detail}")
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="" if result.stderr.endswith("\n") else "\n")
        try:
            return json.loads(path.read_text(encoding="utf-8")), seconds
        except ValueError:
            raise SystemExit(f"scan wrote an unreadable map for {repo}")
    finally:
        path.unlink(missing_ok=True)


def candidate_keys(scan_map):
    keys = set()
    for area in scan_map.get("areas", {}).values():
        for item in area.get("files", []):
            for fn in item.get("functions", []):
                keys.add((item["path"], fn["name"]))
    return keys


def flagged_paths(scan_map):
    return {item["path"] for area in scan_map.get("areas", {}).values() for item in area.get("files", [])}


def score_repo(spec, scan_map, seconds):
    keys = candidate_keys(scan_map)
    flagged = flagged_paths(scan_map)
    missing = []
    found = 0
    in_files = 0
    for site in spec.get("sites") or []:
        in_files += site["path"] in flagged
        if (site["path"], site["function"]) in keys:
            found += 1
        else:
            missing.append({"path": site["path"], "line": site["line"], "function": site["function"],
                            "file_flagged": site["path"] in flagged})
    known = len(spec.get("sites") or [])
    return {
        "name": spec["name"],
        "commit": spec["commit"],
        "known": known,
        "found": found if known else None,
        "found_in_files": in_files if known else None,
        "missing": missing,
        "candidate_functions": scan_map["candidate_functions"],
        "scanned": scan_map["scanned"],
        "seconds": seconds,
    }


def score_extra(path, scan_map, seconds):
    return {
        "path": str(path),
        "candidate_functions": scan_map["candidate_functions"],
        "scanned": scan_map["scanned"],
        "seconds": seconds,
    }


def totals(repos):
    known = sum(repo["known"] for repo in repos)
    found = sum(repo["found"] or 0 for repo in repos)
    in_files = sum(repo["found_in_files"] or 0 for repo in repos)
    return {
        "known": known,
        "found": found if known else None,
        "found_in_files": in_files if known else None,
        "candidate_functions": sum(repo["candidate_functions"] for repo in repos),
        "scanned": sum(repo["scanned"] for repo in repos),
        "seconds": round(sum(repo["seconds"] for repo in repos), 2),
    }


def recall_text(row, field="found"):
    if not row["known"]:
        return "n/a"
    return f"{row[field]} of {row['known']}"


def print_report(report):
    header = ("repo", "recall", "in flagged files", "candidates", "scanned", "seconds")
    body = [(
        repo["name"],
        recall_text(repo),
        recall_text(repo, "found_in_files"),
        str(repo["candidate_functions"]),
        str(repo["scanned"]),
        f"{repo['seconds']:.2f}",
    ) for repo in report["repos"]]
    total = report["total"]
    body.append((
        "total",
        recall_text(total),
        recall_text(total, "found_in_files"),
        str(total["candidate_functions"]),
        str(total["scanned"]),
        f"{total['seconds']:.2f}",
    ))
    rows = [header, *body]
    widths = [max(len(row[col]) for row in rows) for col in range(len(header))]

    def line(row):
        cells = [row[0].ljust(widths[0])]
        cells.extend(row[col].rjust(widths[col]) for col in range(1, len(header)))
        return "  ".join(cells)

    print(line(header))
    for repo, row in zip(report["repos"], body[:-1]):
        print(line(row))
        for site in repo["missing"]:
            where = "file flagged" if site["file_flagged"] else "file not flagged"
            print(f"  missing {site['path']}:{site['line']} {site['function']} ({where})")
    print(line(body[-1]))
    for extra in report["extras"]:
        print(
            f"extra {extra['path']}  candidates {extra['candidate_functions']}  "
            f"scanned {extra['scanned']}  seconds {extra['seconds']:.2f}"
        )


def compare(report, path):
    try:
        baseline = json.loads(Path(path).read_text(encoding="utf-8"))
        before = {repo["name"]: repo for repo in baseline["repos"]}
    except (OSError, ValueError, KeyError, TypeError):
        raise SystemExit(f"{path} is not a recall --json report")
    lost = []
    for repo in report["repos"]:
        old = before.get(repo["name"])
        if old is None:
            print(f"{repo['name']}: not in the baseline")
            continue
        missed_before = {(site["path"], site["function"]) for site in old["missing"]}
        for site in repo["missing"]:
            if (site["path"], site["function"]) not in missed_before:
                lost.append(f"{repo['name']} {site['path']}:{site['line']} {site['function']}")
        change = repo["candidate_functions"] - old["candidate_functions"]
        if change:
            print(f"{repo['name']}: candidates {old['candidate_functions']} -> {repo['candidate_functions']} ({change:+d})")
    old_total, new_total = baseline["total"], report["total"]
    print(f"recall {old_total['found']} -> {new_total['found']} of {new_total['known']}, "
          f"candidates {old_total['candidate_functions']} -> {new_total['candidate_functions']}")
    for site in lost:
        print(f"  lost {site}")
    return lost


def load_known(path, names):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as error:
        raise SystemExit(f"cannot read {path}: {error.strerror}")
    except ValueError:
        raise SystemExit(f"{path} is not valid JSON")
    repos = data.get("repos")
    if not isinstance(repos, list):
        raise SystemExit(f"{path} has no repos list")
    by_name = {}
    for spec in repos:
        for key in ("name", "url", "commit"):
            if not spec.get(key):
                raise SystemExit(f"a repo in {path} is missing {key}")
        by_name[spec["name"]] = spec
    if not names:
        return repos
    missing = [name for name in names if name not in by_name]
    if missing:
        raise SystemExit(f"unknown repo: {', '.join(missing)}")
    return [by_name[name] for name in names]


def measure(args):
    specs = load_known(args.known, args.repo)
    cache = Path(args.cache).expanduser()
    cache.mkdir(parents=True, exist_ok=True)
    repos = []
    for spec in specs:
        checkout = ensure_checkout(cache, spec)
        scan_map, seconds = scan_repo(checkout)
        repos.append(score_repo(spec, scan_map, seconds))
    extras = []
    for raw in args.extra:
        path = Path(raw).expanduser()
        if not path.is_dir():
            raise SystemExit(f"extra repo not found: {path}")
        scan_map, seconds = scan_repo(path)
        extras.append(score_extra(path, scan_map, seconds))
    return {"repos": repos, "total": totals(repos), "extras": extras}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--known", default=str(DEFAULT_KNOWN), help="answer key JSON (default: known_sites.json beside this script)")
    parser.add_argument("--cache", default=str(DEFAULT_CACHE), help="directory of pinned checkouts (default: ~/.cache/drexify-evals)")
    parser.add_argument("--repo", action="append", default=[], help="measure only this repo name (repeatable)")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    parser.add_argument("--strict", action="store_true", help="exit 1 when any known site is missing")
    parser.add_argument("--extra", action="append", default=[], help="local repo with no answer key (repeatable)")
    parser.add_argument("--baseline", help="earlier --json report; exit 1 when a site it found is now missing")
    args = parser.parse_args(argv)
    if args.json and args.baseline:
        parser.error("--baseline prints a comparison, not JSON")
    report = measure(args)
    if args.json:
        print(json.dumps(report, indent=1))
    else:
        print_report(report)
    lost = compare(report, args.baseline) if args.baseline else []
    missed = any(repo["missing"] for repo in report["repos"])
    return 1 if lost or (args.strict and missed) else 0


if __name__ == "__main__":
    sys.exit(main())
