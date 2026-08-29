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
