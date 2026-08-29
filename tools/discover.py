#!/usr/bin/env python3
"""
Anonymous calibration bot — grows the corpus without scoring a single person.

    USES THE NETWORK. `aurarank/` does not. That separation is the whole design.

WHY THIS IS ANONYMOUS, AND WHY THAT IS NOT SQUEAMISHNESS
--------------------------------------------------------
This bot scores REPOSITORIES. It never computes an author identity, never calls
`attribution()`, and never writes a name, email or hash of one. That is a hard
constraint enforced by a test, not a policy note.

The reason is concrete. A first pass at a named roster inferred identity as
"whoever committed most here" and would have published John Gee's work on
commander.js under TJ Holowaychuk's name, and two commits by a contributor under
John Carmack's. At 28 entries that was catchable by hand. A bot doing it across
thousands would misattribute people's work continuously and publicly -- which is
the one failure a tool selling verifiability cannot survive.

So: the statistical problem (too few repos, an empty Apex band, a corpus skewed
to elite libraries) gets solved at scale and anonymously. The human problem
(where does a named person sit) stays small, hand-verified, and eventually
opt-in. They are different problems and they get different machinery.

SAMPLING
--------
The existing corpus is 52 well-known libraries, which is why the bands are
uncertain in the middle -- flagship open source is not what most software looks
like. This samples across the WHOLE popularity distribution, deliberately
weighted toward the small and unloved end, because that is the population the
tool actually serves.

Repos are cloned, scored, and DELETED. Nothing accumulates on disk.

    python3 tools/discover.py --limit 60
    python3 tools/discover.py --limit 400 --out tools/corpus_scores.jsonl
"""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from aurarank.scan import scan, stable_hash  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "tools" / "corpus_scores.jsonl"

# Deliberately bottom-heavy. Flagship repositories are already over-represented
# in the hand-picked corpus; what the bands need is the ordinary middle.
STRATA = [
    ("stars:1..5", 5),
    ("stars:6..25", 5),
    ("stars:26..100", 4),
    ("stars:101..500", 3),
    ("stars:501..2000", 2),
    ("stars:2001..10000", 1),
    ("stars:>10000", 1),
]
LANGUAGES = ["python", "javascript", "typescript"]

# Activity windows. The first pass sampled only `pushed:>2024-01-01`, which
# quietly excluded every abandoned repository -- so the "ordinary" population it
# measured was really "ordinary AND still maintained", and its rigour was biased
# upward. Bands fitted to that would have been wrong in the same direction as the
# elite corpus, just less obviously. Abandoned code is most of what exists.
ACTIVITY = [
    ("pushed:>2025-01-01", 2),      # actively maintained
    ("pushed:2022-01-01..2024-06-30", 2),   # stale
    ("pushed:<2021-01-01", 2),      # abandoned
]


def gh_search(query: str, limit: int) -> list[str]:
    """Public repository search via the authenticated gh CLI."""
    cmd = ["gh", "api", "-X", "GET", "search/repositories",
           "-f", f"q={query}", "-f", "sort=updated", "-f", f"per_page={min(limit, 100)}",
           "--jq", ".items[] | .full_name"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    except (OSError, subprocess.SubprocessError):
        return []
    if r.returncode != 0:
        print(f"    search failed: {r.stderr.strip()[:100]}")
        return []
    return [l.strip() for l in r.stdout.splitlines() if l.strip()][:limit]


def already_seen() -> set[str]:
    if not OUT.exists():
        return set()
    seen = set()
    for line in OUT.read_text().splitlines():
        try:
            seen.add(json.loads(line)["repo_hash"])
        except (ValueError, KeyError):
            continue
    return seen


def measure(slug: str, workdir: pathlib.Path) -> dict | None:
    """Clone shallow-ish, score, and delete. Nothing is kept but numbers."""
    dest = workdir / slug.replace("/", "__")
    r = subprocess.run(
        ["git", "clone", "--filter=blob:none", "--quiet",
         f"https://github.com/{slug}.git", str(dest)],
        capture_output=True, text=True, timeout=240)
    if r.returncode != 0:
        return None
    try:
        res = scan(str(dest))
    except Exception:
        return None
    finally:
        shutil.rmtree(dest, ignore_errors=True)

    if res["tree"]["source_files"] < 3 or res["code"].get("parsed_files", 0) < 3:
        return None
    if "architecture" not in res["dimensions"]:
        return None

    # NOTE what is absent: no author, no email, no identity hash, no attribution
    # call anywhere in this function. The repo slug is hashed too -- the corpus
    # needs a de-duplication key, not a directory of who wrote what.
    g, t = res["git"], res["tree"]
    return {
        "repo_hash": stable_hash(slug),
        "score": res["measured_score"],
        "grade": res["grade"],
        **res["dimensions"],
        "languages": sorted(t["languages"]),
        "source_files": t["source_files"],
        "test_ratio": t["test_ratio"],
        "has_ci": t["has_ci"],
        "tenure_days": g.get("tenure_days", 0),
        "active_months": g.get("active_months", 0),
        "revisit_ratio": g.get("revisit_ratio"),
        "contributors": g.get("contributors", 0),
        "spec": res["spec_version"],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=60, help="repositories to score")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()

    out = pathlib.Path(a.out)
    seen = already_seen()
    print(f"corpus already holds {len(seen)} scored repositories\n")

    targets: list[str] = []
    slots = len(STRATA) * len(LANGUAGES) * len(ACTIVITY)
    per_round = max(1, a.limit // slots + 1)
    for lang in LANGUAGES:
        for stars, weight in STRATA:
            for window, wweight in ACTIVITY:
                q = f"language:{lang} {stars} {window}"
                targets += gh_search(q, max(1, per_round * weight * wweight // 2))
                time.sleep(1)      # courteous to the search API

    targets = [t for t in dict.fromkeys(targets) if stable_hash(t) not in seen][:a.limit]
    print(f"{len(targets)} new candidates\n")

    kept = 0
    with tempfile.TemporaryDirectory(prefix="aura-discover-") as tmp:
        work = pathlib.Path(tmp)
        with out.open("a") as fh:
            for i, slug in enumerate(targets, 1):
                row = measure(slug, work)
                if row is None:
                    print(f"  [{i}/{len(targets)}] skip")
                    continue
                fh.write(json.dumps(row) + "\n")
                fh.flush()
                kept += 1
                print(f"  [{i}/{len(targets)}] {row['score']:>3} {row['grade']:<10} "
                      f"{','.join(row['languages'][:2])}")

    print(f"\nscored {kept} repositories -> {out}")
    print("no author identity was computed or stored")


if __name__ == "__main__":
    main()
