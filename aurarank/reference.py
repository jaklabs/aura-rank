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
  * Some portfolios are one repository (Bellard, Hashimoto, Harris). Thin.
  * A low score is not a low opinion. Teaching artifacts like nanoGPT are
    deliberately unmaintained minimal code -- scoring them low on maintenance
    discipline is the tool working, not a judgement of the author.
"""

from __future__ import annotations

from typing import NamedTuple


class Ref(NamedTuple):
    name: str
    score: int
    ship: float
    architecture: float
    judgment: float
    transmission: float
    repos: int

    @property
    def craft(self) -> float:
        """Architecture and judgment: what the code is like."""
        return round((self.architecture + self.judgment) / 2, 2)

    @property
    def rigour(self) -> float:
        """The scaffolding around shipping -- tests, CI, releases, tenure.
        Named `rigour` here rather than `ship`, because that is what it measures."""
        return self.ship


MEASURED_AT = "2026-08-29"
SPEC = "0.7.0"

REFERENCE: list[Ref] = [
    Ref('David Lord', 85, 9.9, 7.3, 7.9, 8.8, 4),
    Ref('Rich Harris', 84, 10.0, 6.0, 8.9, 8.8, 1),
    Ref('Sindre Sorhus', 80, 10.0, 7.4, 8.3, 6.3, 4),
    Ref('Tom Christie', 80, 9.6, 7.1, 7.4, 7.8, 2),
    Ref('Simon Willison', 79, 9.8, 5.0, 8.7, 8.1, 4),
    Ref('Mitchell Hashimoto', 68, 4.7, 7.7, 10.0, 4.9, 1),
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
