#!/usr/bin/env python3
"""
Re-fit the tier bands using the anonymous corpus as the population.

    Reads local files only. No network.

WHY THE METHOD CHANGES HERE
---------------------------
The bands were first anchored on meaning and validated against 52 hand-picked
libraries. That corpus was honest about being elite (median 78) and the README
said so, but it could only ever anchor the TOP of the scale -- it says nothing
about the middle, because flagship open source is not what most software is.

`tools/discover.py` fixed that by sampling public repositories at random across
the whole popularity range. That sample is the first thing this project has had
that resembles a population, so it is what the middle of the scale should be
fitted to.

The combination rule, stated plainly:

  * The ANONYMOUS corpus sets the middle. It is a random sample, so its
    percentiles mean something about ordinary software.
  * The ELITE corpus anchors the ceiling. Sovereign and Apex should describe
    work like flask and pino, and those only appear in the hand-picked set.
  * Band NAMES keep their meanings. A band is a description of a state of a
    repository, not a percentile label -- if "Formed" stops meaning "tested,
    documented, maintained", the scale has become a curve and lost its point.

Run:  python3 tools/recalibrate.py            # report only
      python3 tools/recalibrate.py --apply    # rewrite TIERS in aurarank/scan.py
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from aurarank.scan import TIERS  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
ANON = ROOT / "tools" / "corpus_scores.jsonl"
ELITE = ROOT / "tools" / "calibration.json"


def pct(xs, p):
    if not xs:
        return 0.0
    s = sorted(xs)
    k = (len(s) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def load():
    anon = []
    if ANON.exists():
        for line in ANON.read_text().splitlines():
            if line.strip():
                try:
                    anon.append(json.loads(line)["score"])
                except (ValueError, KeyError):
                    pass
    elite = []
    if ELITE.exists():
        try:
            elite = [r["score"] for r in json.loads(ELITE.read_text())["rows"]]
        except (ValueError, KeyError):
            pass
    return anon, elite


def propose(anon, elite):
    """Anonymous percentiles below the median, elite above it.

    The crossover sits at the anonymous p90: past that point a repository is no
    longer ordinary, and the only sample with anything useful to say about it is
    the hand-picked one.
    """
    return [
        (0, round(pct(anon, .05)), "Dormant"),
        (0, round(pct(anon, .20)), "Kindled"),
        (0, round(pct(anon, .40)), "Drawn"),
        (0, round(pct(anon, .62)), "Formed"),
        (0, round(pct(anon, .85)), "Marked"),
        (0, round(pct(elite or anon, .45)), "Sealed"),
        (0, round(pct(elite or anon, .88)), "Sovereign"),
        (0, 100, "Apex"),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    anon, elite = load()
    if len(anon) < 20:
        raise SystemExit(f"only {len(anon)} anonymous repos — too few to refit")

    print(f"{'='*74}\nPOPULATIONS\n{'='*74}")
    print(f"  anonymous (random public repos)  n={len(anon):<4} "
          f"p25 {pct(anon,.25):.0f}  median {statistics.median(anon):.0f}  p75 {pct(anon,.75):.0f}  max {max(anon)}")
    print(f"  elite (hand-picked libraries)    n={len(elite):<4} "
          f"p25 {pct(elite,.25):.0f}  median {statistics.median(elite):.0f}  p75 {pct(elite,.75):.0f}  max {max(elite)}")
    print(f"\n  the gap between those medians is why the middle of the scale was wrong")

    prop = propose(anon, elite)
    bounds, prev = [], 0
    for _, hi, name in prop:
        hi = max(int(hi), prev + 1)
        bounds.append((prev, hi, name))
        prev = hi + 1
    bounds[-1] = (bounds[-1][0], 100, bounds[-1][2])

    print(f"\n{'='*74}\nBANDS\n{'='*74}")
    print(f"  {'band':<12}{'current':>12}{'proposed':>14}   {'anon %':>8}{'elite %':>9}")
    old = {t[2]: (t[0], t[1]) for t in TIERS}
    for lo, hi, name in bounds:
        o = old.get(name)
        na = 100 * sum(1 for s in anon if lo <= s <= hi) / len(anon)
        ne = 100 * sum(1 for s in elite if lo <= s <= hi) / len(elite) if elite else 0
        print(f"  {name:<12}{f'{o[0]}-{o[1]}' if o else '—':>12}{f'{lo}-{hi}':>14}"
              f"   {na:>7.0f}%{ne:>8.0f}%")

    jak = 39
    def grade(score, table):
        for lo, hi, name in table:
            if lo <= score <= hi:
                return name
        return "?"
    before = grade(jak, [(t[0], t[1], t[2]) for t in TIERS])
    after = grade(jak, bounds)
    below = 100 * sum(1 for s in anon if s < jak) / len(anon)
    print(f"\n{'='*74}\nEFFECT ON A SCORE OF {jak}\n{'='*74}")
    print(f"  grade before : {before}")
    print(f"  grade after  : {after}")
    print(f"  and against the random sample: {jak} beats {below:.0f}% of ordinary public repos")
    print(f"  (the score itself does not move — recalibration changes what it MEANS)")

    if a.apply:
        blurbs = {t[2]: t[3] for t in TIERS}
        rows = "\n".join(
            f'    ({lo}, {hi}, "{name}", "{blurbs[name]}"),'
            for lo, hi, name in bounds)
        p = ROOT / "aurarank" / "scan.py"
        s = p.read_text()
        s = re.sub(r"TIERS = \[.*?\n\]", f"TIERS = [\n{rows}\n]", s, flags=re.S)
        p.write_text(s)
        print(f"\napplied to {p}")
    else:
        print("\nreport only — pass --apply to rewrite TIERS")


if __name__ == "__main__":
    main()
