#!/usr/bin/env python3
"""Measure named developers' public portfolios with the same tool.

    USES THE NETWORK (via tools/calibrate.py's clones). aurarank/ does not.

The reference points on the "you are here" chart have to be measured, not
asserted. Anyone can re-run this and get the same numbers -- which is the only
reason it is defensible to put a stranger's name on a chart next to yours.

Each person is scored over the public repositories they actually authored, using
the email that dominates their own commit history.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from aurarank.portfolio import build  # noqa: E402

CORPUS = pathlib.Path(__file__).resolve().parents[1] / ".corpus"

PEOPLE = [
    ("Simon Willison", "swillison@gmail.com",
     ["simonw__datasette", "simonw__sqlite-utils", "simonw__llm", "simonw__shot-scraper"]),
    ("Sindre Sorhus", "sindresorhus@gmail.com",
     ["sindresorhus__got", "sindresorhus__execa", "sindresorhus__ora", "sindresorhus__p-limit"]),
    ("Tom Christie", "tom@tomchristie.com",
     ["encode__httpx", "encode__starlette"]),
    ("David Lord", "davidism@gmail.com",
     ["pallets__flask", "pallets__jinja", "pallets__click", "pallets__itsdangerous"]),
    ("Andrej Karpathy", None,
     ["karpathy__nanoGPT", "karpathy__micrograd", "karpathy__minGPT", "karpathy__nn-zero-to-hero"]),
    ("Fabrice Bellard", None, ["bellard__quickjs"]),
    ("Mitchell Hashimoto", None, ["mitchellh__libxev"]),
    ("Rich Harris", None, ["sveltejs__svelte", "Rich-Harris__degit"]),
]


def dominant_email(paths):
    """Whoever authored the most commits across these repos. Used when a person's
    address isn't known in advance -- their own history is the source of truth."""
    from aurarank.scan import _git
    counts = {}
    for p in paths:
        for line in (_git(p, "log", "--all", "--pretty=format:%aE") or "").splitlines():
            e = line.strip().lower()
            if e and "noreply" not in e and "[bot]" not in e:
                counts[e] = counts.get(e, 0) + 1
    return max(counts, key=counts.get) if counts else None


def main():
    out = []
    for name, email, slugs in PEOPLE:
        paths = [CORPUS / s for s in slugs if (CORPUS / s).exists()]
        if not paths:
            print(f"  skip {name}: no repos cloned")
            continue
        addr = email or dominant_email(paths)
        if not addr:
            print(f"  skip {name}: no identity found")
            continue
        p = build(paths, {addr}, min_share=0.10)
        if "error" in p:
            print(f"  skip {name}: {p['error']}")
            continue
        s = p["portfolio_signals"]
        row = {
            "name": name, "score": p["score"], "grade": p["grade"],
            "dimensions": p["dimensions"], "repos": p["repos_scanned"],
            "focus": s["focus"], "consistency": s["consistency"],
            "best": s["best"], "median": s["median"],
        }
        out.append(row)
        d = p["dimensions"]
        print(f"  {p['score']:>3}  {p['grade']:<10} {name:<20} "
              f"n={p['repos_scanned']}  ship {d.get('ship', 0):>4}  "
              f"arch {d.get('architecture', 0):>4}  jdg {d.get('judgment', 0):>4}  "
              f"trn {d.get('transmission', 0):>4}")

    dest = pathlib.Path(__file__).parent / "reference_people.json"
    dest.write_text(json.dumps(sorted(out, key=lambda r: -r["score"]), indent=2))
    print(f"\nwrote {dest}")


if __name__ == "__main__":
    main()
