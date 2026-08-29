#!/usr/bin/env python3
"""
aura portfolio — aggregate many repositories into one developer rank.

    NO NETWORK. Same guarantee as `aura scan`, which this wraps.

A repository is not a person. This turns a pile of directories into a single
profile, which needs three decisions the per-repo scanner never had to make:

  WHOSE WORK IS IT?     Weight each repo by your share of its commits. A repo you
                        sent three patches to is not your work; a vendored clone
                        is not your work at all.

  WHICH REPOS COUNT?    Not the mean -- that punishes exploration, and every
                        scratch directory would drag you down, which is exactly
                        backwards. Not the max either -- one good repo among
                        thirty abandoned ones is not an elite engineer.
                        Instead: your CORE BODY OF WORK, the best repos that
                        together carry most of your actual output.

  WHAT'S ONLY VISIBLE HERE?   Sustained output across projects, how concentrated
                        your effort is, and how far your best work sits from your
                        typical work. None of that exists inside one repo.

Usage:
    python3 -m aura.portfolio ~/code/*/ [--me you@example.com] [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from datetime import datetime, timezone
from math import log1p
from pathlib import Path

from .scan import TIERS, _git, attribution, scan, stable_hash, tier_of

# Fraction of total evidence-weight that defines the "core body of work".
# 0.60 keeps the projects carrying most of your output and drops the long tail of
# scratch repos, without letting a single large repo decide the whole rank.
CORE_COVERAGE = 0.60


def evidence_mass(res: dict) -> float:
    """How much a repository can legitimately say about its author.

    Logarithmic in both size and duration: a 500-file project genuinely carries
    more evidence than a 5-file one, but not a hundred times more, and a linear
    weight would let one big repository decide the entire rank.
    """
    files = res["tree"]["source_files"]
    months = res["git"].get("active_months", 0) if res["git"].get("is_git_repo") else 0
    return log1p(files) * log1p(months)


def active_months(repo: Path) -> set[str]:
    log = _git(repo, "log", "--all", "--pretty=format:%at")
    if not log:
        return set()
    out = set()
    for line in log.splitlines():
        try:
            out.add(datetime.fromtimestamp(
                int(line.strip()), timezone.utc).strftime("%Y-%m"))
        except (ValueError, OSError):
            continue
    return out


def detect_identity(repos: list[Path]) -> set[str]:
    """Read git's own configured identity. Falls back to whatever authored the
    most commits across the given repos, so it works on a machine that was never
    configured."""
    emails: set[str] = set()
    for r in repos[:5]:
        cfg = _git(r, "config", "user.email")
        if cfg and cfg.strip():
            emails.add(cfg.strip().lower())
    if emails:
        return emails
    counts: dict[str, int] = {}
    for r in repos:
        log = _git(r, "log", "--all", "--pretty=format:%aE") or ""
        for line in log.splitlines():
            e = line.strip().lower()
            if e:
                counts[e] = counts.get(e, 0) + 1
    return {max(counts, key=counts.get)} if counts else set()


def build(paths: list[Path], emails: set[str], min_share: float = 0.25) -> dict:
    repos = []
    months_union: set[str] = set()
    skipped: list[tuple[str, str]] = []
    unclaimed: Counter[str] = Counter()

    for p in paths:
        if not (p / ".git").exists():
            skipped.append((p.name, "not a git repository"))
            continue
        try:
            res = scan(str(p))
        except Exception as e:
            skipped.append((p.name, f"scan failed: {type(e).__name__}"))
            continue
        if res["tree"]["source_files"] < 3:
            skipped.append((p.name, "too little source"))
            continue

        attr = attribution(p, emails) if emails else None
        share = 1.0 if attr is None or attr["share"] is None else attr["share"]
        if attr:
            for e, n in attr["unclaimed"].items():
                unclaimed[e] += n
        if share < min_share:
            skipped.append((p.name, f"only {share:.0%} yours"))
            continue

        mass = evidence_mass(res)
        repos.append({
            "name": p.name,
            "name_hash": stable_hash(p.name),
            "score": res["measured_score"],
            "grade": res["grade"],
            "dimensions": res["dimensions"],
            "share": share,
            "mass": round(mass, 2),
            "weight": round(mass * share, 2),
            "languages": list(res["tree"]["languages"]),
            "active_months": res["git"].get("active_months", 0),
            "tenure_days": res["git"].get("tenure_days", 0),
            "agent_directed": attr["agent_directed"] if attr else 0,
            "bots_excluded": attr["bots_excluded"] if attr else 0,
        })
        months_union |= active_months(p)

    if not repos:
        return {"error": "no repositories qualified", "skipped": skipped}

    out = aggregate(repos, months_union)
    out["skipped"] = skipped
    # Never silently merge two addresses into one person -- surface them and let
    # the user claim them. Guessing that jak@ and jak.dev@ are the same human is
    # exactly the kind of inference a ranking tool should not make on its own.
    out["unclaimed_identities"] = dict(unclaimed.most_common(6))
    out["agent_directed_total"] = sum(r["agent_directed"] for r in repos)
    return out


def aggregate(repos: list[dict], months_union: set[str]) -> dict:
    """Pure aggregation. Takes already-scored repos, returns the profile.

    Separated from build() so the part with actual judgement in it -- which repos
    count and how they're weighted -- can be tested without touching a disk.
    """
    from .scan import SPEC_VERSION

    repos = list(repos)
    repos.sort(key=lambda r: -r["score"])
    total_w = sum(r["weight"] for r in repos) or 1.0

    # The core body of work: best repos covering CORE_COVERAGE of total weight.
    core, acc = [], 0.0
    for r in repos:
        core.append(r)
        acc += r["weight"]
        if acc >= total_w * CORE_COVERAGE:
            break
    core_w = sum(r["weight"] for r in core) or 1.0

    wmean = lambda key: round(
        sum(r[key] * r["weight"] for r in core) / core_w, 1)

    dims: dict[str, float] = {}
    for name in ("ship", "architecture", "judgment", "transmission"):
        present = [r for r in core if name in r["dimensions"]]
        if present:
            w = sum(r["weight"] for r in present) or 1.0
            dims[name] = round(
                sum(r["dimensions"][name] * r["weight"] for r in present) / w, 1)

    score = int(round(wmean("score")))
    grade, means = tier_of(score)

    all_scores = [r["score"] for r in repos]
    # Herfindahl index over effort. 1.0 = everything in one project;
    # near 1/n = spread evenly across many.
    focus = sum((r["weight"] / total_w) ** 2 for r in repos)
    langs = sorted({l for r in repos for l in r["languages"]})

    span = 0
    if months_union:
        lo, hi = min(months_union), max(months_union)
        span = ((int(hi[:4]) - int(lo[:4])) * 12 + int(hi[5:]) - int(lo[5:])) + 1

    return {
        "spec_version": SPEC_VERSION,
        "tier": "self-assessed",
        "score": score,
        "grade": grade,
        "grade_means": means,
        "dimensions": dims,
        "repos_scanned": len(repos),
        "repos_in_core": len(core),
        "core_coverage": CORE_COVERAGE,
        "portfolio_signals": {
            "active_months": len(months_union),
            "span_months": span,
            "consistency": round(len(months_union) / span, 3) if span else 0.0,
            "focus": round(focus, 3),
            "languages": langs,
            "best": max(all_scores),
            "median": int(statistics.median(all_scores)),
            "spread": max(all_scores) - int(statistics.median(all_scores)),
        },
        "repos": repos,
        "note": ("Aggregates only the repositories you pointed at. It cannot see "
                 "work you did not scan, and it does not verify authorship beyond "
                 "git metadata -- that is what the attested tier is for."),
    }


def render(p: dict) -> str:
    if "error" in p:
        return f"no repositories qualified.\n" + "\n".join(
            f"  skipped {n}: {why}" for n, why in p["skipped"])
    w = 66
    bar = lambda v: "#" * int(round(v * 2)) + "." * (20 - int(round(v * 2)))
    s = p["portfolio_signals"]
    L = ["+" + "-" * w + "+",
         f"|  AURA PORTFOLIO  ·  {p['repos_scanned']} repos  ·  spec v{p['spec_version']}".ljust(w) + " |",
         "+" + "-" * w + "+",
         f"|  {p['grade'].upper()}   {p['score']}/100".ljust(w) + " |",
         f"|  {p['grade_means'][:w-4]}".ljust(w) + " |",
         f"|  from your core {p['repos_in_core']} repos "
         f"({int(p['core_coverage']*100)}% of your output)".ljust(w) + " |",
         "+" + "-" * w + "+"]
    for k, v in p["dimensions"].items():
        L.append(f"|  {k:<14} {bar(v)} {v:>4}".ljust(w) + " |")
    L += ["+" + "-" * w + "+",
          f"|  active {s['active_months']}/{s['span_months']} months "
          f"(consistency {s['consistency']})".ljust(w) + " |",
          f"|  focus {s['focus']}  ·  best {s['best']}  median {s['median']}  "
          f"spread {s['spread']}".ljust(w) + " |",
          f"|  {', '.join(s['languages'])[:w-4]}".ljust(w) + " |",
          "+" + "-" * w + "+", "", "  core body of work"]
    core_names = {r["name"] for r in p["repos"][:p["repos_in_core"]]}
    for r in p["repos"]:
        mark = "*" if r["name"] in core_names else " "
        L.append(f"  {mark} {r['score']:>3}  {r['name'][:30]:<30} "
                 f"{r['grade']:<10} {r['share']:>4.0%} yours")
    if p.get("agent_directed_total"):
        L.append(f"\n  {p['agent_directed_total']} agent-authored commits counted as "
                 f"yours (directed work)")
    if p.get("unclaimed_identities"):
        L.append("\n  unclaimed identities in your repos"
                 " — add with --me if these are you")
        for e, n in p["unclaimed_identities"].items():
            L.append(f"    {n:>5} commits  {e}")
    if p["skipped"]:
        L.append("\n  skipped")
        for n, why in p["skipped"][:8]:
            L.append(f"    {n[:34]:<34} {why}")
    L.append("\n  Nothing left this machine.")
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser(prog="aura portfolio", description=__doc__)
    ap.add_argument("paths", nargs="+", help="repository directories")
    ap.add_argument("--me", action="append", default=[],
                    help="your git email (repeatable). Auto-detected if omitted.")
    ap.add_argument("--min-share", type=float, default=0.25,
                    help="drop repos where less than this fraction is yours")
    ap.add_argument("--json", metavar="FILE")
    a = ap.parse_args()

    paths = [Path(x).expanduser().resolve() for x in a.paths]
    paths = [x for x in paths if x.is_dir()]
    emails = {e.lower() for e in a.me} or detect_identity(paths)
    if not a.me and emails:
        print(f"identity: auto-detected from git config "
              f"({len(emails)} address{'es' if len(emails) > 1 else ''})\n")

    p = build(paths, emails, a.min_share)
    print(render(p))
    if a.json:
        Path(a.json).write_text(json.dumps(p, indent=2))
        print(f"\nwrote {a.json}")


if __name__ == "__main__":
    main()
