#!/usr/bin/env python3
"""
aura calibrate — fit the tier bands against a corpus of public repositories.

    THIS TOOL USES THE NETWORK. `aura/scan.py` DOES NOT.

That separation is deliberate and load-bearing: the scanner people run on their
own machines must be provably offline, so everything that touches the network
lives here instead, in a tool nobody has to run.

    python3 tools/calibrate.py --clone     # fetch the corpus (slow, once)
    python3 tools/calibrate.py             # score it and fit the bands
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aura.scan import scan  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CORPUS_DIR = ROOT / ".corpus"
CORPUS_LIST = ROOT / "tools" / "corpus.txt"
OUT = ROOT / "tools" / "calibration.json"


def entries() -> list[tuple[str, str]]:
    out = []
    for line in CORPUS_LIST.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            out.append((parts[0], parts[1]))
    return out


def clone_all() -> None:
    """Partial clone: full commit history (needed for cadence and revisit),
    blobs fetched lazily so we don't pull years of file contents."""
    CORPUS_DIR.mkdir(exist_ok=True)
    items = entries()
    for i, (tier, slug) in enumerate(items, 1):
        dest = CORPUS_DIR / slug.replace("/", "__")
        if dest.exists():
            print(f"[{i}/{len(items)}] have {slug}")
            continue
        print(f"[{i}/{len(items)}] clone {slug} ...", flush=True)
        r = subprocess.run(
            ["git", "clone", "--filter=blob:none", "--quiet",
             f"https://github.com/{slug}.git", str(dest)],
            capture_output=True, text=True, timeout=600,
        )
        if r.returncode != 0:
            print(f"    FAILED: {r.stderr.strip()[:120]}")


def score_all() -> list[dict]:
    rows = []
    for tier, slug in entries():
        d = CORPUS_DIR / slug.replace("/", "__")
        if not d.exists():
            continue
        try:
            r = scan(str(d))
        except Exception as e:  # a corpus repo should never break the fit
            print(f"  skip {slug}: {e}")
            continue
        if not r["git"].get("is_git_repo"):
            continue
        # Needs enough analyzable source to say anything. Since v0.4.0 that
        # includes JS/TS, so the corpus is no longer Python-shaped.
        if r["code"].get("parsed_files", 0) < 5:
            print(f"  skip {slug}: too little analyzable source")
            continue
        rows.append({
            "slug": slug, "corpus_tier": tier,
            "score": r["measured_score"], **r["dimensions"],
            "langs": ",".join(r["code"].get("analyzed_languages", [])),
            "test_ratio": r["tree"]["test_ratio"],
            "has_ci": r["tree"]["has_ci"],
            "has_iac": r["tree"]["has_iac"],
            "revisit": r["git"]["revisit_ratio"],
            "cadence": r["git"]["cadence"],
            "tenure_days": r["git"]["tenure_days"],
            "type_cov": r["code"].get("type_coverage"),
            "fn_p90": r["code"].get("fn_len_p90", 0),
            "nest_p90": r["code"].get("nesting_p90", 0),
            "exc_prec": r["code"].get("except_precision"),
        })
    return rows


def pct(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    k = (len(s) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def report(rows: list[dict]) -> dict:
    scores = [r["score"] for r in rows]
    print(f"\n{'='*72}\nCORPUS: {len(rows)} repos\n{'='*72}")
    print(f"score      min {min(scores)}  p25 {pct(scores,.25):.0f}  "
          f"median {statistics.median(scores):.0f}  p75 {pct(scores,.75):.0f}  "
          f"max {max(scores)}")

    print(f"\n{'dimension':<16}{'min':>6}{'p25':>7}{'med':>7}{'p75':>7}{'max':>7}")
    for d in ("ship", "architecture", "judgment", "transmission"):
        v = [r[d] for r in rows]
        print(f"{d:<16}{min(v):>6.1f}{pct(v,.25):>7.1f}"
              f"{statistics.median(v):>7.1f}{pct(v,.75):>7.1f}{max(v):>7.1f}")

    print(f"\n{'input':<16}{'min':>6}{'p25':>7}{'med':>7}{'p75':>7}{'max':>7}")
    for k in ("test_ratio", "revisit", "cadence", "type_cov", "fn_p90", "nest_p90"):
        v = [r[k] for r in rows if r[k] is not None]
        print(f"{k:<16}{min(v):>6.2f}{pct(v,.25):>7.2f}"
              f"{statistics.median(v):>7.2f}{pct(v,.75):>7.2f}{max(v):>7.2f}")
    ci = sum(1 for r in rows if r["has_ci"])
    print(f"\nhas_ci true: {ci}/{len(rows)} ({100*ci/len(rows):.0f}%)")

    print(f"\nby language:")
    from collections import Counter
    for lg, cnt in Counter(r["langs"] for r in rows).most_common():
        v = [r["score"] for r in rows if r["langs"] == lg]
        print(f"  {lg or '?':<22} n={cnt:<3} median {statistics.median(v):>5.1f}")

    print(f"\nby corpus tier:")
    for t in ("flagship", "mid", "small"):
        v = [r["score"] for r in rows if r["corpus_tier"] == t]
        if v:
            print(f"  {t:<10} n={len(v):<3} median {statistics.median(v):>5.1f}  "
                  f"range {min(v)}–{max(v)}")

    # NOT percentile-fitted. Fitting bands to this corpus would be a mistake:
    # it is 36 elite public libraries, and their median is ~78 while real
    # solo/private work sits near 26. Percentile-fitting one population puts
    # every genuine user in the bottom band. So the bands are anchored on
    # meaning in aura/scan.py, and this function VALIDATES them instead.
    from aura.scan import TIERS
    print(f"\n{'='*72}\nBAND OCCUPANCY (anchored bands, validated here)\n{'='*72}")
    for lo, hi, name, blurb in TIERS:
        n = sum(1 for s_ in scores if lo <= s_ <= hi)
        bar = "#" * n
        print(f"  {name:<11}{lo:>4}-{hi:<4} {bar:<26} n={n}")

    print(f"\n  corpus median {statistics.median(scores):.0f} -> "
          f"{[t[2] for t in TIERS if t[0] <= statistics.median(scores) <= t[1]][0]}")
    print("  (elite public libraries SHOULD sit high. If they didn't, the")
    print("   bands would be wrong -- that is what makes this a check.)")

    bands = [[lo, hi, name] for lo, hi, name, _ in TIERS]

    return {"n": len(rows), "bands": bands, "rows": rows,
            "percentiles": {str(p): round(pct(scores, p / 100), 1)
                            for p in (5, 10, 25, 50, 75, 90, 95, 99)}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clone", action="store_true")
    a = ap.parse_args()
    if a.clone:
        clone_all()
    rows = score_all()
    if not rows:
        raise SystemExit("no repos scored — run with --clone first")
    OUT.write_text(json.dumps(report(rows), indent=2))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
