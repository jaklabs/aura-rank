#!/usr/bin/env python3
"""
aura scan — local, offline developer signal extraction.

    THIS FILE HAS NO NETWORK ACCESS.

It imports no HTTP client and opens no socket. That is not a promise in a privacy
policy, it is a property of the file you are reading, and you can verify it in one
command before you ever run it:

    grep -rnE 'requests|urllib|http|socket|aiohttp|httpx|ssl' aurarank/

It DOES use `subprocess`, below, for exactly one thing: running `git` to read your
local commit history. Every call is checked by tests/test_no_network.py, which
fails the build if a subprocess call ever invokes anything other than git.

Your source code never leaves this machine. The output is integers and ratios --
never source text, never file contents, never absolute paths, never identifiers.
Print it and read it before you share it:

    aura scan ./my-repo --print

Usage:
    python3 -m aurarank.scan <path-to-git-repo> [--json out.json] [--print]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from . import langs

SPEC_VERSION = "0.10.0"


def stable_hash(text: str) -> str:
    """Deterministic across processes and machines.

    Python's built-in hash() is salted per interpreter run, so identifiers hashed
    with it changed on every invocation -- which made them useless for comparing
    two scans and silently wrong in any payload that claimed to identify a repo.
    """
    return hashlib.blake2s(text.encode("utf-8", "replace"),
                           digest_size=8).hexdigest()

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

def _git(repo: Path, *args: str, timeout: int = 60) -> str | None:
    """Returns None when git fails or times out -- NOT an empty string.

    This distinction is load-bearing. The previous version swallowed a timeout
    and returned "", which the callers read as "no history", which silently
    produced revisit_ratio 0.0 for any repository whose log was too big to walk
    in time. A large, well-maintained repo was being scored as abandoned.
    A failed measurement must never be indistinguishable from a bad result.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
        return out.stdout if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def git_signals(repo: Path) -> dict:
    """Cadence and maintenance, derived purely from commit metadata."""
    log = _git(repo, "log", "--all", "--pretty=format:%at|%aE|%cI")
    if not log or not log.strip():
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
        authors[stable_hash(parts[1].strip().lower())] += 1
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


# Recent history only. Two reasons, and the second matters more than the first:
# walking fifteen years of file lists took ~55s on a big repo, AND over that long
# a window every surviving file eventually gets touched twice, so the ratio drifts
# toward 1.0 and stops discriminating. A recent window is both faster and sharper.
REVISIT_WINDOW = "3.years"


def _revisit_ratio(repo: Path) -> float | None:
    raw = _git(repo, "log", "--all", f"--since={REVISIT_WINDOW}",
               "--name-only", "--pretty=format:@%at", timeout=45)
    if raw is None:
        return None                      # unmeasured -- never scored as zero
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
        return None
    multi = sum(1 for m in touched.values() if len(m) > 1)
    return round(multi / len(touched), 3)


# Coding agents write code under a person's direction. Their commits belong to
# whoever directed them, so they are attributed to the repository's dominant human.
AGENT_IDENTITIES = ("noreply@anthropic.com", "claude", "copilot", "cursor",
                    "aider", "devin", "codex", "openai.com", "windsurf")

# Automation that nobody directs. A dependency bump is not anyone's craft, so
# these are dropped from the numerator AND the denominator -- counting them would
# dilute every human in the repository.
BOT_IDENTITIES = ("dependabot", "renovate", "greenkeeper", "github-actions",
                  "semantic-release", "allcontributors", "snyk-bot", "imgbot",
                  "pre-commit-ci", "netlify", "vercel[bot]")

# GitHub's own committer identity on web-UI and bot commits. Not a person -- but
# note `12345+user@users.noreply.github.com` IS a person using a privacy address,
# and is deliberately not matched here.
MACHINE_IDENTITIES = ("noreply@github.com",)

# A local-part that is literally "agent", "bot" or "ci" is a service account
# whatever domain it sits on.
MACHINE_LOCALPARTS = {"agent", "bot", "ci", "build", "builder", "automation"}

_COAUTHOR = re.compile(r"<([^>]+)>")


def _classify(email: str) -> str:
    e = email.lower()
    if any(b in e for b in BOT_IDENTITIES) or e in MACHINE_IDENTITIES:
        return "bot"
    if any(a in e for a in AGENT_IDENTITIES):
        return "agent"
    if e.split("@", 1)[0] in MACHINE_LOCALPARTS:
        return "agent"
    return "human"


def attribute_commit(ids: set[str], wanted: set[str], dominant: bool) -> str:
    """Who owns one commit. Pure, so the rule can be tested directly.

    `mine`  -- your identity is on it (author, committer or co-author), OR a coding
               agent authored it and you are the dominant human in the repository.
               Agent commits are directed work; the person who directed them owns
               the result.
    `bot`   -- pure automation. Excluded from the total rather than counted against
               anyone: a dependency bump is nobody's craft.
    `other` -- somebody else's work.
    """
    if ids & wanted:
        return "mine"
    kinds = {_classify(e) for e in ids}
    if kinds == {"bot"}:
        return "bot"
    if "agent" in kinds and "human" not in kinds:
        return "mine" if dominant else "agent_other"
    return "other"


def commit_identities(repo: Path) -> list[dict] | None:
    """One record per commit: author, committer and any Co-Authored-By trailers.

    All three matter. A commit you authored and an agent committed is yours; so is
    one an agent authored and you committed; so is one where you are named in a
    co-author trailer. Attribution should follow anyone whose name is on the work.
    """
    fmt = "%aE%x00%cE%x00%(trailers:key=Co-authored-by,valueonly,separator=%x1f)%x01"
    raw = _git(repo, "log", "--all", f"--pretty=format:{fmt}")
    if raw is None:                       # old git, no trailer support
        raw = _git(repo, "log", "--all", "--pretty=format:%aE%x00%cE%x00%x01")
    if not raw:
        return None
    out = []
    for rec in raw.split("\x01"):
        rec = rec.strip("\n")
        if not rec.strip():
            continue
        parts = rec.split("\x00")
        if len(parts) < 2:
            continue
        ids = {parts[0].strip().lower(), parts[1].strip().lower()}
        if len(parts) > 2 and parts[2].strip():
            for chunk in parts[2].split("\x1f"):
                m = _COAUTHOR.search(chunk)
                if m:
                    ids.add(m.group(1).strip().lower())
        out.append({e for e in ids if e})
    return out


def attribution(repo: Path, emails: set[str]) -> dict | None:
    """How much of this repository is the caller's work.

    A commit is theirs when any identity on it is theirs, or when a coding agent
    authored it and they are the dominant human in the repo -- an agent commit is
    directed work, and the person who directed it owns it.

    Pure automation (dependency bots, release bots) is excluded from the total
    rather than counted against anyone.
    """
    commits = commit_identities(repo)
    if commits is None:
        return None

    wanted = {e.strip().lower() for e in emails}
    human_counts: Counter[str] = Counter()
    for ids in commits:
        for e in ids:
            if _classify(e) == "human":
                human_counts[e] += 1
    dominant = (not human_counts) or (
        sum(human_counts[e] for e in wanted if e in human_counts)
        >= max(human_counts.values(), default=0))

    mine = agent = bot = total = 0
    unclaimed: Counter[str] = Counter()
    for ids in commits:
        verdict = attribute_commit(ids, wanted, dominant)
        if verdict == "bot":
            bot += 1
            continue                       # excluded from the denominator entirely
        total += 1
        if verdict == "mine":
            mine += 1
            if not (ids & wanted):
                agent += 1                 # directed, not typed by hand
        elif verdict == "agent_other":
            agent += 0
        else:
            for e in ids:
                if _classify(e) == "human":
                    unclaimed[e] += 1

    return {
        "share": round(mine / total, 3) if total else None,
        "commits": total,
        "mine": mine,
        "agent_directed": agent if dominant else 0,
        "bots_excluded": bot,
        "unclaimed": dict(unclaimed.most_common(5)),
    }


def author_share(repo: Path, emails: set[str]) -> float | None:
    a = attribution(repo, emails)
    return a["share"] if a else None


# --------------------------------------------------------------------------
# tree — structure, not content
# --------------------------------------------------------------------------

def walk_sources(repo: Path):
    """Walk the repo's own files.

    Nested git repositories -- vendored checkouts, submodules, a corpus directory --
    are somebody else's code and are skipped. Without this a repo that happens to
    contain a clone scores on the clone's tests and typing, not its own.
    """
    for root, dirs, files in os.walk(repo):
        dirs[:] = [
            d for d in dirs
            if d not in SKIP_DIRS
            and d != ".git"
            and not (Path(root) / d / ".git").exists()
        ]
        for f in files:
            yield Path(root) / f


def tree_signals(repo: Path) -> tuple[dict, list[Path], list[Path]]:
    langs: Counter[str] = Counter()
    src: list[Path] = []
    tests: list[Path] = []
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
            tests.append(p)
        else:
            n_src += 1
            src.append(p)

    blob = "\n".join(rel_all)
    has = lambda markers: any(m.lower() in blob for m in markers)
    n_doc = sum(1 for r in rel_all if r.endswith((".md", ".rst", ".adoc")))

    # Does the README teach, or merely exist? A title and a badge is not
    # transmission. Usage examples, real headings and enough prose to orient a
    # stranger are -- and unlike contributor count, a solo developer controls
    # every one of them.
    readme_depth = 0.0
    for cand in ("README.md", "readme.md", "README.rst", "Readme.md"):
        f = repo / cand
        if not f.exists():
            continue
        try:
            text = f.read_text(errors="ignore")
        except OSError:
            break
        words = len(text.split())
        fences = text.count("```")
        heads = sum(1 for ln in text.splitlines() if ln.lstrip().startswith("#"))
        readme_depth = round(min(1.0,
            0.40 * min(1.0, words / 400)
            + 0.35 * min(1.0, fences / 6)
            + 0.25 * min(1.0, heads / 8)), 3)
        break
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
        "readme_depth": readme_depth,
        "packaged": packaged,
        "production_shape": has(IAC_MARKERS) or has(MIGRATION_MARKERS),
        "dependencies": deps,
    }, src, tests


# --------------------------------------------------------------------------
# AST — parsed locally, only distributions emitted
# --------------------------------------------------------------------------

def test_signals(tests: list[Path], source_modules: int, cap: int = 200) -> dict | None:
    """Judge the test suite itself, not how many files it spans.

    A file-count ratio cannot tell nineteen regression tests from eighty-three
    empty ones -- and it rewards the second. This reads the tests: do they
    assert, do they exercise failure paths, how much of the package do they
    touch. All proxies, because the tool never runs anything and therefore
    cannot measure coverage. Stated as proxies in the payload.
    """
    acc = {"test_fns": 0, "assertions": 0, "edge_fns": 0, "modules": set()}
    for f in tests[:cap]:
        try:
            text = f.read_text(errors="ignore")
        except OSError:
            continue
        if langs.looks_generated(text):
            continue
        ext = f.suffix.lower()
        if ext == ".py":
            a = langs.analyze_tests_python(text)
        elif ext in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"):
            a = langs.analyze_tests_js(text)
        else:
            continue
        for k in ("test_fns", "assertions", "edge_fns"):
            acc[k] += a[k]
        acc["modules"] |= a["modules"]
    return langs.test_quality(acc, source_modules)


def code_signals(files: list[Path], cap: int = 600) -> dict:
    """Analyze every language we can, then MERGE -- a polyglot repo is measured
    across all of its code rather than by whichever language happens to win a
    file count. Languages with no analyzer are simply absent from the merge."""
    accs = []
    skipped = 0
    langs_seen: set[str] = set()
    for f in files[:cap]:
        ext = f.suffix.lower()
        try:
            src = f.read_text(errors="ignore")
        except OSError:
            continue
        if langs.looks_generated(src):
            skipped += 1
            continue
        if ext == ".py":
            accs.append(langs.analyze_python(src)); langs_seen.add("python")
        elif ext in (".js", ".jsx", ".mjs", ".cjs"):
            accs.append(langs.analyze_js(src, typed_lang=False)); langs_seen.add("javascript")
        elif ext in (".ts", ".tsx", ".mts", ".cts"):
            accs.append(langs.analyze_js(src, typed_lang=True)); langs_seen.add("typescript")

    if not accs:
        return {"parsed_files": 0, "analyzed_languages": []}

    out = langs.summarize(langs.merge(*accs))
    out["analyzed_languages"] = sorted(langs_seen)
    out["skipped_generated"] = skipped
    if langs_seen & {"javascript", "typescript"}:
        out["js_scanner_limits"] = langs.JS_LIMITATIONS
    return out


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


def score(g: dict, t: dict, p: dict, tq: dict | None = None) -> dict:
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
    # Named `rigour`, not `ship`. It measures the scaffolding AROUND shipping --
    # tests, CI, releases, tenure -- not whether you ship. Calling it "ship" made
    # the tool report 1.7 for people running four production systems, which reads
    # as a broken instrument rather than a real finding. A dimension whose name
    # misdescribes its contents is a defect on a tool asking to be trusted.
    # Tests count twice, for different things. BREADTH is how much of the
    # codebase has tests near it; DEPTH is whether those tests assert anything,
    # poke at failure paths and touch more than one module. Scoring breadth alone
    # rewarded eighty-three hollow files over nineteen that each prevent a real
    # money error -- and made the metric trivially gameable by adding empty files.
    # Depth is dropped, not zeroed, when a repo has no tests at all: absent is
    # already punished by breadth, and counting it twice would double-penalise.
    rigour = 10 * _weighted([
        (0.18, _band(t["test_ratio"], 0, 1.0)),
        (0.10, tq["quality"] if tq else None),
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
        (0.25, _band(p["type_coverage"], 0, 0.9)
               if (has_ast and p.get("type_coverage") is not None) else None),
    ]) if has_ast else None

    judgment = 10 * _weighted([
        (0.45, _band(g["revisit_ratio"], 0.05, 0.75)
               if g.get("revisit_ratio") is not None else None),
        (0.30, p.get("except_precision") if has_ast else None),
        (0.25, _band(g.get("cadence", 0), 0.15, 0.95)),
    ])

    # Contributor count was 25% of this dimension and a solo developer scores
    # zero on it by definition -- forfeiting a quarter of "can you make other
    # people good" for working alone. On a tool built for developers without a
    # company behind them that is precisely backwards, and it was measuring
    # REACH (did others join) rather than transmission (is the work legible).
    #
    # So it is DROPPED when a repo is solo, not scored zero. Nobody having
    # joined is a different fact from teaching badly. Where collaborators do
    # exist it still counts, because sustaining them is real transmission.
    solo = g.get("contributors", 1) <= 1
    transmission = 10 * _weighted([
        (0.28, _band(t["doc_ratio"], 0, 0.35)),
        (0.28, _band(p["docstring_coverage"], 0, 0.8) if has_ast else None),
        (0.24, t.get("readme_depth", 0.0)),
        (0.20, None if solo else _band(g["contributors"], 1, 25)),
    ])

    dims: dict[str, float] = {"rigour": round(rigour, 1)}
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
    (0, 23, "Dormant", "little engineering signal yet -- a scratch or scratch-shaped repo"),
    (24, 33, "Kindled", "working code, shipped, but no test or CI discipline behind it"),
    (34, 42, "Drawn", "discipline appearing -- some tests, some structure, held together"),
    (43, 53, "Formed", "real practice: tested, documented, maintained over time"),
    (54, 61, "Marked", "professional open-source standard -- others could rely on this"),
    (62, 77, "Sealed", "a strong, well-maintained library others do rely on"),
    (78, 84, "Sovereign", "flagship quality -- among the best-run projects in its language"),
    (85, 100, "Apex", "best-in-class. Reference-grade engineering"),
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
    t, src, test_files = tree_signals(repo)
    p = code_signals(src)
    tq = test_signals(test_files, t["source_files"])
    s = score(g, t, p, tq)

    return {
        "spec_version": SPEC_VERSION,
        "tier": "self-assessed",          # never anything else from this command
        "scanned_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo_name_hash": stable_hash(repo.name),   # not the name itself
        "git": g,
        "tree": t,
        "code": p,
        "tests": tq,
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
        f"revisit {r['git'].get('revisit_ratio')}".ljust(w) + " |",
        f"|  tests {r['tree']['test_ratio']} · "
        f"types {r['code'].get('type_coverage') or 0} · "
        f"loose-handlers {r['code'].get('imprecise_handlers', 0)}".ljust(w) + " |",
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
