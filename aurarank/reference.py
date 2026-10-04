"""Measured reference portfolios, for the "you are here" position.

    NO NETWORK. These are static measurements, shipped with the package.

Every number here was produced by this same tool over that person's public
repositories, using the email that dominates their own commit history. Nobody's
score is an opinion, and anyone can reproduce the set:

    python3 tools/measure_people.py

That reproducibility is the only thing that makes it defensible to put a
stranger's name on a chart beside yours.

READ THIS BEFORE QUOTING A PERCENTILE
-------------------------------------
This is a small, deliberately chosen reference set -- not a census. A position
against it means "where you sit among these measured portfolios", and nothing
whatsoever about all developers alive. The tool will not print a global
percentile, because it has no population to compute one from and inventing one
would be the exact dishonesty the project exists to avoid.

Caveats that belong with the numbers:
  * Some portfolios are a single repository. Thin, and marked by `repos`.
  * Every entry is IDENTITY-VERIFIED: the dominant commit author in the repos
    must match the named person, or the entry is dropped. An earlier run of the
    harness inferred "whoever committed most" and would have credited John Gee's
    work on commander.js to TJ Holowaychuk, and two commits by a contributor to
    John Carmack. Nothing here is attributed on a guess.
  * Only portfolios where all four dimensions could be measured are included.
    C and Java repositories score on three and are not comparable, so Rich
    Hickey and Salvatore Sanfilippo are absent rather than misrepresented.
  * A low score is not a low opinion. Teaching artifacts like nanoGPT are
    deliberately unmaintained minimal code -- scoring them low on maintenance
    discipline is the tool working, not a judgement of the author.
"""

from __future__ import annotations

from typing import NamedTuple


class Ref(NamedTuple):
    name: str
    score: int
    rigour: float
    architecture: float
    judgment: float
    transmission: float
    repos: int

    @property
    def craft(self) -> float:
        """Architecture and judgment: what the code is like."""
        return round((self.architecture + self.judgment) / 2, 2)

MEASURED_AT = "2026-08-29"
SPEC = "0.8.0"

REFERENCE: list[Ref] = [
    Ref('Hynek Schlawack', 86, 10.0, 5.8, 9.2, 9.2, 2),
    Ref('David Lord', 85, 9.9, 7.3, 7.9, 8.8, 4),
    Ref('Matteo Collina', 83, 10.0, 8.2, 8.0, 7.1, 1),
    Ref('Feross Aboukhadijeh', 83, 10.0, 8.5, 7.8, 7.0, 1),
    Ref('Sebastian Ramirez', 82, 9.9, 8.0, 7.7, 7.1, 4),
    Ref('Will McGugan', 82, 8.8, 7.0, 8.0, 9.2, 2),
    Ref('Tom Christie', 80, 9.6, 7.1, 7.4, 7.8, 2),
    Ref('Sindre Sorhus', 80, 10.0, 7.4, 8.3, 6.3, 4),
    Ref('Simon Willison', 79, 9.8, 5.0, 8.7, 8.1, 4),
    Ref('Ned Batchelder', 79, 10.0, 4.5, 7.7, 9.3, 1),
    Ref('Rich Harris', 78, 10.0, 6.0, 6.3, 8.8, 2),
    Ref('TJ Holowaychuk', 78, 10.0, 7.9, 8.5, 4.9, 1),
    Ref('Guillermo Rauch', 75, 8.4, 8.2, 6.2, 7.2, 1),
    Ref('Armin Ronacher', 74, 8.3, 6.6, 7.1, 7.7, 2),
    Ref('Kent C. Dodds', 73, 8.1, 7.7, 6.4, 7.0, 1),
    Ref('Colin McDonnell', 72, 9.1, 7.4, 7.3, 4.9, 1),
    Ref('Luke Edwards', 70, 8.4, 8.2, 5.0, 6.6, 3),
    Ref('Mitchell Hashimoto', 68, 4.7, 7.7, 10.0, 4.9, 1),
    Ref('Anthony Sottile', 67, 9.9, 6.1, 7.2, 3.7, 2),
    Ref('Fabrice Bellard', 59, 4.9, 7.1, 7.8, 3.8, 1),
    Ref('Andrej Karpathy', 44, 1.5, 4.8, 4.6, 6.9, 3),
]

def position(score: int) -> dict:
    """Where a score sits in the reference set. Deliberately not a percentile
    of developers -- only a rank among these named, reproducible measurements."""
    above = [r for r in REFERENCE if r.score > score]
    below = [r for r in REFERENCE if r.score <= score]
    nearest = min(REFERENCE, key=lambda r: abs(r.score - score))
    return {
        "rank": len(above) + 1,
        "of": len(REFERENCE) + 1,
        "above": above[-1].name if above else None,
        "below": below[0].name if below else None,
        "nearest": nearest.name,
        "nearest_score": nearest.score,
        "reference_measured_at": MEASURED_AT,
    }

# The repositories each portfolio was BUILT FROM, so a reader can check the
# measurement rather than take it on faith. Lifted from tools/measure_people.py,
# which is the harness that produced REFERENCE above.
#
# ⚠️ THESE ARE THE REPOSITORIES CONSIDERED, NOT THE ONES SCORED, and for one
# person those differ: Andrej Karpathy lists four and `repos` says three, because
# a repository that cannot be measured on all four dimensions is dropped rather
# than misrepresented (see the caveats at the top of this file). So anything
# displaying this list must read `repos` for how many were actually scored and
# must not claim every slug here contributed a number. Presenting four as
# measured when three were is a small lie about a named stranger, which is
# exactly what the reproducibility note above exists to prevent.
CONSIDERED: dict[str, tuple[str, ...]] = {
    'Hynek Schlawack': ('hynek__structlog', 'python-attrs__attrs',),
    'David Lord': ('pallets__flask', 'pallets__jinja', 'pallets__click', 'pallets__itsdangerous',),
    'Matteo Collina': ('pinojs__pino',),
    'Feross Aboukhadijeh': ('feross__standard',),
    'Sebastian Ramirez': ('tiangolo__typer', 'tiangolo__sqlmodel', 'tiangolo__asyncer', 'tiangolo__fastapi',),
    'Will McGugan': ('Textualize__rich', 'Textualize__textual',),
    'Tom Christie': ('encode__httpx', 'encode__starlette',),
    'Sindre Sorhus': ('sindresorhus__got', 'sindresorhus__execa', 'sindresorhus__ora', 'sindresorhus__p-limit',),
    'Simon Willison': ('simonw__datasette', 'simonw__sqlite-utils', 'simonw__llm', 'simonw__shot-scraper',),
    'Ned Batchelder': ('nedbat__coveragepy',),
    'Rich Harris': ('sveltejs__svelte', 'sveltejs__kit',),
    'TJ Holowaychuk': ('expressjs__express',),
    'Guillermo Rauch': ('socketio__socket.io',),
    'Armin Ronacher': ('mitsuhiko__minijinja', 'mitsuhiko__insta',),
    'Kent C. Dodds': ('kentcdodds__match-sorter',),
    'Colin McDonnell': ('colinhacks__zod',),
    'Luke Edwards': ('lukeed__clsx', 'lukeed__polka', 'lukeed__uvu',),
    'Mitchell Hashimoto': ('mitchellh__libxev',),
    'Anthony Sottile': ('asottile__pyupgrade', 'asottile__add-trailing-comma',),
    'Fabrice Bellard': ('bellard__quickjs',),
    'Andrej Karpathy': ('karpathy__nanoGPT', 'karpathy__micrograd', 'karpathy__minGPT', 'karpathy__nn-zero-to-hero',),
}


def roster() -> list[dict]:
    """REFERENCE as plain JSON-able rows, newest calibration, best first.

    Exists so a consumer (the jaklabs-crm rank page) can show the set a position
    was computed against WITHOUT keeping its own copy. A second copy would drift,
    and a roster that disagrees with the rank beside it is worse than no roster:
    the page would say 21st of 22 next to a list the reader can count differently.
    """
    from .scan import tier_of
    rows = []
    for r in sorted(REFERENCE, key=lambda x: -x.score):
        grade, blurb = tier_of(r.score)
        rows.append({
            "name": r.name,
            "score": r.score,
            "grade": grade,
            "grade_means": blurb,
            "dimensions": {
                "rigour": r.rigour,
                "architecture": r.architecture,
                "judgment": r.judgment,
                "transmission": r.transmission,
            },
            "craft": r.craft,
            "repos_scored": r.repos,
            "considered": list(CONSIDERED.get(r.name, ())),
        })
    return rows
