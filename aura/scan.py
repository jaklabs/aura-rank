#!/usr/bin/env python3
"""
aura scan — local, offline developer signal extraction.

    THIS FILE HAS NO NETWORK ACCESS.

It imports no HTTP client and opens no socket. That is not a promise in a privacy
policy, it is a property of the file you are reading, and you can verify it in one
command before you ever run it:

    grep -nE 'requests|urllib|http|socket|aiohttp|curl' aura/scan.py

Your source code never leaves this machine. The output is integers and ratios --
never source text, never file contents, never absolute paths, never identifiers.
Print it and read it before you share it:

    aura scan ./my-repo --print

Usage:
    python3 -m aura.scan <path-to-git-repo> [--json out.json] [--print]
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

SPEC_VERSION = "0.3.0"

# Directories that are never signal, only noise.
SKIP_DIRS = {
    ".git", "node_modules", "venv", ".venv", "env", "__pycache__", "dist",
    "build", ".next", ".nuxt", "target", "vendor", ".terraform", "site-packages",
    ".mypy_cache", ".pytest_cache", ".tox", "coverage", ".idea", ".vscode",
}

SOURCE_EXT = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript", ".ts": "typescript",
    ".tsx": "typescript", ".go": "go", ".rs": "rust", ".rb": "ruby", ".java": "java",
    ".kt": "kotlin", ".swift": "swift", ".c": "c", ".h": "c", ".cpp": "cpp",
    ".cs": "csharp", ".php": "php", ".sh": "shell", ".sql": "sql",
}

TEST_HINT = re.compile(r"(^|[/_.-])(tests?|spec|__tests__)([/_.-]|$)", re.I)

CI_MARKERS = [".github/workflows", ".gitlab-ci.yml", ".circleci", "Jenkinsfile",
              ".travis.yml", "azure-pipelines.yml", ".buildkite"]
IAC_MARKERS = ["terraform", "Dockerfile", "docker-compose.yml", "serverless.yml",
               "template.yaml", "Chart.yaml", "k8s", "kubernetes", "ansible",
               "cloudformation", "pulumi", "cdk.json"]
MIGRATION_MARKERS = ["migrations", "migrate", "alembic", "flyway", "liquibase",
                     "schema.sql", "prisma"]
DOC_MARKERS = ["readme", "docs", "documentation", "architecture", "adr", "contributing"]
DEP_FILES = ["requirements.txt", "pyproject.toml", "package.json", "go.mod",
             "Cargo.toml", "Gemfile", "pom.xml", "build.gradle"]


# --------------------------------------------------------------------------
# git — metadata only. Dates and counts. Never message bodies, never diffs.
# --------------------------------------------------------------------------

def _git(repo: Path, *args: str) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=60, check=False,
        )
        return out.stdout if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def git_signals(repo: Path) -> dict:
    """Cadence and maintenance, derived purely from commit metadata."""
    log = _git(repo, "log", "--all", "--pretty=format:%at|%aE|%cI")
    if not log.strip():
        return {"is_git_repo": False}

    times: list[int] = []
    authors: Counter[str] = Counter()
    months: set[str] = set()

    for line in log.splitlines():
        parts = line.split("|")
        if len(parts) < 2:
            continue
        try:
            ts = int(parts[0])
        except ValueError:
            continue
        times.append(ts)
        # The address is hashed immediately; the raw value is never stored or emitted.
        authors[str(hash(parts[1].strip().lower()) % (10**9))] += 1
        months.add(datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m"))

    if not times:
        return {"is_git_repo": False}

    first, last = min(times), max(times)
    tenure_days = max(1, int((last - first) / 86400))
    span_months = max(1, round(tenure_days / 30.44))
    total = sum(authors.values())

    # Bus factor: how many authors it takes to account for half the commits.
    bus, acc = 0, 0
    for _, n in authors.most_common():
        acc += n
        bus += 1
        if acc >= total / 2:
            break

    # Revisit ratio: files touched in more than one distinct month.
    # This is the load-bearing signal -- it separates maintained work from
    # dump-and-run work, and it cannot be faked without actually doing it.
    revisit = _revisit_ratio(repo)

    tags = len([t for t in _git(repo, "tag").splitlines() if t.strip()])

    return {
        "is_git_repo": True,
        "tags": tags,
        "tenure_days": tenure_days,
        "active_months": len(months),
        "span_months": span_months,
        "cadence": round(min(1.0, len(months) / span_months), 3),
        "commits": total,
        "contributors": len(authors),
        "bus_factor": bus,
        "revisit_ratio": revisit,
    }


def _revisit_ratio(repo: Path) -> float:
    raw = _git(repo, "log", "--all", "--name-only", "--pretty=format:@%at")
    if not raw.strip():
        return 0.0
    touched: dict[str, set[str]] = defaultdict(set)
    month = ""
    for line in raw.splitlines():
        line = line.rstrip()
        if line.startswith("@"):
            try:
                month = datetime.fromtimestamp(
                    int(line[1:]), timezone.utc).strftime("%Y-%m")
            except ValueError:
                month = ""
        elif line and month:
            if not any(p in SKIP_DIRS for p in line.split("/")):
                touched[line].add(month)
    if not touched:
        return 0.0
    multi = sum(1 for m in touched.values() if len(m) > 1)
    return round(multi / len(touched), 3)


# --------------------------------------------------------------------------
# tree — structure, not content
# --------------------------------------------------------------------------

def walk_sources(repo: Path):
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and d != ".git"]
        for f in files:
            yield Path(root) / f


def tree_signals(repo: Path) -> tuple[dict, list[Path]]:
    langs: Counter[str] = Counter()
    src: list[Path] = []
    n_test = n_src = 0
    rel_all: list[str] = []

    for p in walk_sources(repo):
        try:
            rel = str(p.relative_to(repo))
        except ValueError:
            continue
        rel_all.append(rel.lower())
        lang = SOURCE_EXT.get(p.suffix.lower())
        if not lang:
            continue
        langs[lang] += 1
        if TEST_HINT.search(rel):
            n_test += 1
        else:
            n_src += 1
            src.append(p)

    blob = "\n".join(rel_all)
    has = lambda markers: any(m.lower() in blob for m in markers)
    n_doc = sum(1 for r in rel_all if r.endswith((".md", ".rst", ".adoc")))
    # Library-shaped and service-shaped repos prove "ship" differently. A library
    # with no Terraform is not deficient, it is a library -- so each shape gets a
    # route to full marks instead of being scored against the other's checklist.
    packaged = any(m in blob for m in
                   ("setup.py", "pyproject.toml", "setup.cfg", "package.json"))

    deps = 0
    for dep_file in DEP_FILES:
        fp = repo / dep_file
        if fp.exists():
            try:
                text = fp.read_text(errors="ignore")
                if dep_file == "package.json":
                    data = json.loads(text)
                    deps += len(data.get("dependencies", {})) + \
                            len(data.get("devDependencies", {}))
                else:
                    deps += sum(
                        1 for ln in text.splitlines()
                        if ln.strip() and not ln.strip().startswith("#")
                    )
            except (OSError, ValueError):
                pass

    return {
        "languages": dict(langs.most_common(6)),
        "substrate_breadth": len(langs),
        "source_files": n_src,
        "test_files": n_test,
        "test_ratio": round(n_test / n_src, 3) if n_src else 0.0,
        "has_ci": has(CI_MARKERS),
        "has_iac": has(IAC_MARKERS),
        "has_migrations": has(MIGRATION_MARKERS),
        "has_docs": has(DOC_MARKERS),
        "doc_files": n_doc,
        "doc_ratio": round(n_doc / n_src, 3) if n_src else 0.0,
        "packaged": packaged,
        "production_shape": has(IAC_MARKERS) or has(MIGRATION_MARKERS),
        "dependencies": deps,
    }, src


# --------------------------------------------------------------------------
# AST — parsed locally, only distributions emitted
# --------------------------------------------------------------------------

def _depth(node, d=0) -> int:
    nesting = (ast.If, ast.For, ast.While, ast.With, ast.Try,
               ast.AsyncFor, ast.AsyncWith)
    best = d
    for child in ast.iter_child_nodes(node):
        best = max(best, _depth(child, d + isinstance(child, nesting)))
    return best


def python_signals(files: list[Path], cap: int = 400) -> dict:
    lengths: list[int] = []
    depths: list[int] = []
    bare_except = broad_except = handled = 0
    fns = typed = documented = 0
    parsed = 0

    for p in [f for f in files if f.suffix == ".py"][:cap]:
        try:
            tree = ast.parse(p.read_text(errors="ignore"))
        except (OSError, SyntaxError, ValueError):
            continue
        parsed += 1
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fns += 1
                if node.end_lineno and node.lineno:
                    lengths.append(node.end_lineno - node.lineno + 1)
                depths.append(_depth(node))
                args = node.args
                every = list(args.args) + list(args.kwonlyargs)
                if (node.returns is not None
                        or (every and all(a.annotation for a in every))):
                    typed += 1
                if ast.get_docstring(node):
                    documented += 1
            elif isinstance(node, ast.ExceptHandler):
                handled += 1
                if node.type is None:
                    bare_except += 1
                elif isinstance(node.type, ast.Name) and node.type.id in (
                        "Exception", "BaseException"):
                    broad_except += 1

    if not parsed:
        return {"parsed_files": 0}

    pct = lambda xs, q: int(statistics.quantiles(xs, n=10)[q]) if len(xs) > 9 \
        else (max(xs) if xs else 0)

    return {
        "parsed_files": parsed,
        "functions": fns,
        "fn_len_p50": int(statistics.median(lengths)) if lengths else 0,
        "fn_len_p90": pct(lengths, 8),
        "nesting_p90": pct(depths, 8),
        "type_coverage": round(typed / fns, 3) if fns else 0.0,
        "docstring_coverage": round(documented / fns, 3) if fns else 0.0,
        "except_handlers": handled,
        "bare_except": bare_except,
        "broad_except": broad_except,
        "except_precision": round(
            1 - (bare_except + broad_except) / handled, 3) if handled else None,
    }


# --------------------------------------------------------------------------
# scoring — every weight lives here, in the open, and is versioned
# --------------------------------------------------------------------------

def _band(value, lo, hi) -> float:
    """Linear 0..1 between lo and hi, clamped."""
    if hi == lo:
        return 0.0
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


def _weighted(parts: list[tuple[float, float | None]]) -> float:
    """Weighted mean over the components we actually have.

    Components whose input is unavailable are DROPPED and the remaining weights
    renormalised -- never defaulted to zero or to a plausible-looking constant.
    A missing measurement and a bad measurement are different things, and a
    scorer that conflates them is inventing numbers.
    """
    live = [(w, v) for w, v in parts if v is not None]
    if not live:
        return 0.0
    total_w = sum(w for w, _ in live)
    return sum(w * v for w, v in live) / total_w


def score(g: dict, t: dict, p: dict) -> dict:
    """Four of the eight dimensions are measurable from a repository.

    The other four -- Embed, Fundamentals, Reach, Renown -- are NOT inferable
    from code, and this tool deliberately refuses to guess at them. A system that
    claimed to measure whether you can sit with a customer, by reading your AST,
    would be obvious nonsense to exactly the people whose respect it needs.

    Architecture additionally requires a parsed AST. With no Python to parse it
    is reported as unmeasured rather than scored from defaults, and the overall
    score is averaged over the dimensions that were genuinely measured.
    """
    has_ast = p.get("parsed_files", 0) >= 3

    # Bands widened after the first calibration run: the originals saturated,
    # so half the corpus landed on an identical score. Ranges below are set from
    # the observed distribution over 36 public repos (see tools/calibration.json).
    ship = 10 * _weighted([
        (0.28, _band(t["test_ratio"], 0, 1.0)),
        (0.22, 1.0 if t["has_ci"] else 0.0),
        (0.20, _band(g.get("tags", 0), 0, 12)),
        (0.15, _band(g.get("tenure_days", 0), 60, 1825)),
        # Each shape gets its own route to full marks.
        (0.15, 1.0 if (t["production_shape"] or t["packaged"]) else 0.0),
    ])

    arch = 10 * _weighted([
        (0.35, (1 - _band(p["fn_len_p90"], 20, 90)) if has_ast else None),
        (0.25, (1 - _band(p["nesting_p90"], 1, 5)) if has_ast else None),
        (0.15, _band(t["substrate_breadth"], 1, 5)),
        (0.25, _band(p["type_coverage"], 0, 0.9) if has_ast else None),
    ]) if has_ast else None

    judgment = 10 * _weighted([
        (0.45, _band(g.get("revisit_ratio", 0), 0.05, 0.75)),
        (0.30, p.get("except_precision") if has_ast else None),
        (0.25, _band(g.get("cadence", 0), 0.15, 0.95)),
    ])

    transmission = 10 * _weighted([
        (0.30, _band(t["doc_ratio"], 0, 0.35)),
        (0.30, _band(p["docstring_coverage"], 0, 0.8) if has_ast else None),
        (0.25, _band(g.get("contributors", 1), 1, 25)),
        (0.15, 1.0 if t["has_docs"] else 0.0),
    ])

    dims: dict[str, float] = {"ship": round(ship, 1)}
    if arch is not None:
        dims["architecture"] = round(arch, 1)
    dims["judgment"] = round(judgment, 1)
    dims["transmission"] = round(transmission, 1)

    measured = round(sum(dims.values()) / (len(dims) * 10) * 100)
    return {
        "dimensions": dims,
        "measured_score": measured,
        "unmeasured": [] if arch is not None else ["architecture"],
    }


# Bands are anchored on MEANING, then validated against two populations --
# not fitted to percentiles of one. The calibration corpus is 36 elite public
# Python libraries (median 78); real solo/private repositories score far lower
# (median 26 over a 9-repo sample). Fitting bands to the corpus alone would put
# almost every genuine user in the bottom band, which is both useless and wrong.
# See tools/CALIBRATION.md for the method, the samples and the known bias.
TIERS = [
    (0,  14,  "Dormant",   "little engineering signal yet -- a scratch or scratch-shaped repo"),
    (15, 29,  "Kindled",   "working code, shipped, but no test or CI discipline behind it"),
    (30, 44,  "Drawn",     "discipline appearing -- some tests, some structure, held together"),
    (45, 59,  "Formed",    "real practice: tested, documented, maintained over time"),
    (60, 72,  "Marked",    "professional open-source standard -- others could rely on this"),
    (73, 81,  "Sealed",    "a strong, well-maintained library others do rely on"),
    (82, 88,  "Sovereign", "flagship quality -- among the best-run projects in its language"),
    (89, 100, "Apex",      "best-in-class. Reference-grade engineering"),
]


def tier_of(s: int) -> tuple[str, str]:
    for lo, hi, name, blurb in TIERS:
        if lo <= s <= hi:
            return name, blurb
    return TIERS[0][2], TIERS[0][3]


# --------------------------------------------------------------------------

def scan(path: str) -> dict:
    repo = Path(path).expanduser().resolve()
    if not repo.is_dir():
        raise SystemExit(f"not a directory: {repo}")

    g = git_signals(repo)
    t, src = tree_signals(repo)
    p = python_signals(src)
    s = score(g, t, p)

    return {
        "spec_version": SPEC_VERSION,
        "tier": "self-assessed",          # never anything else from this command
        "scanned_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo_name_hash": str(hash(repo.name) % (10**9)),   # not the name itself
        "git": g,
        "tree": t,
        "python": p,
        **s,
        "grade": tier_of(s["measured_score"])[0],
        "grade_means": tier_of(s["measured_score"])[1],
        "note": ("measured_score covers 4 of 8 dimensions. Embed, Fundamentals, "
                 "Reach and Renown are not inferable from a repository."),
    }


def render(r: dict) -> str:
    w = 62
    bar = lambda v: "#" * int(round(v * 2)) + "." * (20 - int(round(v * 2)))
    out = [
        "+" + "-" * w + "+",
        f"|  AURA  ·  local scan  ·  spec v{r['spec_version']}".ljust(w) + " |",
        "+" + "-" * w + "+",
        f"|  {r['grade'].upper()}   {r['measured_score']}/100".ljust(w) + " |",
        f"|  {r['grade_means'][:w-4]}".ljust(w) + " |",
        f"|  {r['tier']} · {len(r['dimensions'])} of 8 dimensions measured".ljust(w) + " |",
        "+" + "-" * w + "+",
    ]
    for k, v in r["dimensions"].items():
        out.append(f"|  {k:<14} {bar(v)} {v:>4}".ljust(w) + " |")
    out += [
        "+" + "-" * w + "+",
        f"|  tenure {r['git'].get('tenure_days', 0)}d · "
        f"cadence {r['git'].get('cadence', 0)} · "
        f"revisit {r['git'].get('revisit_ratio', 0)}".ljust(w) + " |",
        f"|  tests {r['tree']['test_ratio']} · "
        f"types {r['python'].get('type_coverage', 0)} · "
        f"bare-except {r['python'].get('bare_except', 0)}".ljust(w) + " |",
        "+" + "-" * w + "+",
        "   Nothing left this machine. Run with --print to read the payload.",
    ]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(prog="aura scan", description=__doc__)
    ap.add_argument("path", help="path to a git repository")
    ap.add_argument("--json", metavar="FILE", help="write the payload to a file")
    ap.add_argument("--print", action="store_true", dest="show",
                    help="print the exact JSON payload so you can audit it")
    a = ap.parse_args()

    r = scan(a.path)
    print(render(r))
    if a.show:
        print("\n" + json.dumps(r, indent=2))
    if a.json:
        Path(a.json).write_text(json.dumps(r, indent=2))
        print(f"\nwrote {a.json}")


if __name__ == "__main__":
    main()
