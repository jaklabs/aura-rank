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
    # (display name, known email or None to infer from their own history, repo slugs)
    ("Simon Willison", "swillison@gmail.com",
     ["simonw__datasette", "simonw__sqlite-utils", "simonw__llm", "simonw__shot-scraper"]),
    ("David Lord", "davidism@gmail.com",
     ["pallets__flask", "pallets__jinja", "pallets__click", "pallets__itsdangerous"]),
    ("Tom Christie", "tom@tomchristie.com", ["encode__httpx", "encode__starlette"]),
    ("Sindre Sorhus", "sindresorhus@gmail.com",
     ["sindresorhus__got", "sindresorhus__execa", "sindresorhus__ora", "sindresorhus__p-limit"]),
    ("Andrej Karpathy", None,
     ["karpathy__nanoGPT", "karpathy__micrograd", "karpathy__minGPT", "karpathy__nn-zero-to-hero"]),
    ("Rich Harris", None, ["sveltejs__svelte", "sveltejs__kit"]),
    ("Mitchell Hashimoto", None, ["mitchellh__libxev"]),
    ("Fabrice Bellard", None, ["bellard__quickjs"]),
    ("Armin Ronacher", None, ["mitsuhiko__minijinja", "mitsuhiko__insta"]),
    ("Sebastian Ramirez", None,
     ["tiangolo__typer", "tiangolo__sqlmodel", "tiangolo__asyncer", "tiangolo__fastapi"]),
    ("Will McGugan", None, ["Textualize__rich", "Textualize__textual"]),
    ("Anthony Sottile", None, ["asottile__pyupgrade", "asottile__add-trailing-comma"]),
    ("Hynek Schlawack", None, ["hynek__structlog", "python-attrs__attrs"]),
    ("Ned Batchelder", None, ["nedbat__coveragepy"]),
("Jason Miller", None, ["developit__mitt"]),
    ("Colin McDonnell", None, ["colinhacks__zod"]),
    ("Luke Edwards", None, ["lukeed__clsx", "lukeed__polka", "lukeed__uvu"]),
    ("Matteo Collina", None, ["pinojs__pino"]),
    # Express, not commander.js -- he is the dominant author of one and not the other.
    ("TJ Holowaychuk", None, ["expressjs__express"]),
    ("Feross Aboukhadijeh", None, ["feross__standard"]),
    ("Salvatore Sanfilippo", None, ["antirez__kilo", "antirez__linenoise"]),
    ("Kent C. Dodds", None, ["kentcdodds__match-sorter"]),
    ("Guillermo Rauch", None, ["socketio__socket.io"]),
    ("Rich Hickey", None, ["clojure__clojure"]),
]


def dominant_author(paths):
    """The (name, email) with the most commits across these repositories."""
    from aurarank.scan import _git
    counts = {}
    for p in paths:
        for line in (_git(p, "log", "--all", "--pretty=format:%aN|%aE") or "").splitlines():
            if "|" not in line:
                continue
            n, e = line.rsplit("|", 1)
            e = e.strip().lower()
            if not e or "noreply" in e or "[bot]" in e:
                continue
            key = (n.strip(), e)
            counts[key] = counts.get(key, 0) + 1
    return max(counts, key=counts.get) if counts else (None, None)


def verify(person: str, author_name: str) -> bool:
    """Does the repository's dominant author plausibly BE the named person?

    This exists because the first run of this harness was wrong in a way that
    would have been genuinely damaging. Inferring "whoever committed most" and
    then printing a famous name beside it attributed John Gee's work on
    commander.js to TJ Holowaychuk, and two commits by a contributor to John
    Carmack. On a tool whose entire pitch is verifiability, publishing that
    would have been indefensible.

    So the rule is now: the inferred author must match the declared person, or
    the entry is dropped and the mismatch is printed. No silent guessing.
    """
    if not author_name:
        return False
    a = _fold(author_name)
    parts = [w for w in _fold(person).split() if len(w) > 2]
    if any(w in a for w in parts):
        return True
    if a.replace(" ", "") in _fold(person).replace(" ", ""):
        return True
    # People commit under a handle as often as a legal name.
    return a.replace(" ", "") in HANDLES.get(person, ())


def _fold(text: str) -> str:
    """Strip accents and punctuation so 'Sebastian' matches 'Sebastián'."""
    import unicodedata
    n = unicodedata.normalize("NFKD", text)
    n = "".join(c for c in n if not unicodedata.combining(c))
    return n.lower().replace("-", " ").replace(".", "")


# Verified handle aliases. Each one checked by hand against the person's own
# public profile -- this map is the only place a name is accepted without the
# commit author matching it literally.
HANDLES = {
    "Salvatore Sanfilippo": ("antirez",),
    "Andrej Karpathy": ("karpathy",),
    "Fabrice Bellard": ("bellard",),
}


def main():
    out = []
    for name, email, slugs in PEOPLE:
        paths = [CORPUS / s for s in slugs if (CORPUS / s).exists()]
        if not paths:
            print(f"  skip {name}: no repos cloned")
            continue
        if email:
            addr, author = email, name
        else:
            author, addr = dominant_author(paths)
            if not verify(name, author):
                print(f"  DROP {name}: dominant author is {author!r}, not them")
                continue
        if not addr:
            print(f"  skip {name}: no identity found")
            continue
        p = build(paths, {addr}, min_share=0.10)
        if "error" in p:
            print(f"  skip {name}: {p['error']}")
            continue
        # All four dimensions or nothing. Architecture needs a parsed AST, and the
        # analyzers cover Python, JS and TS only -- a C or Java portfolio scores on
        # three dimensions and is not comparable with one scored on four.
        if "architecture" not in p["dimensions"]:
            print(f"  DROP {name}: architecture unmeasured (no analyzer for its language)")
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
              f"n={p['repos_scanned']}  rigour {d.get('rigour', 0):>4}  "
              f"arch {d.get('architecture', 0):>4}  jdg {d.get('judgment', 0):>4}  "
              f"trn {d.get('transmission', 0):>4}")

    dest = pathlib.Path(__file__).parent / "reference_people.json"
    dest.write_text(json.dumps(sorted(out, key=lambda r: -r["score"]), indent=2))
    print(f"\nwrote {dest}")


if __name__ == "__main__":
    main()
