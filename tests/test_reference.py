#!/usr/bin/env python3
"""Tests for the reference roster — the set a position is computed against.

Added 2026-10-04, when the jaklabs-crm rank page grew a section that lists the
whole set and lets a reader open any one of them. That turned REFERENCE from a
number used once into a thing with real strangers' names on screen, and these
pin the two ways that goes wrong.

Run: python3 tests/test_reference.py
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from aurarank.reference import CONSIDERED, REFERENCE, roster  # noqa: E402
from aurarank.scan import tier_of  # noqa: E402

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


rows = roster()

# --- the roster is the whole set, and ordered ------------------------------
check(len(rows) == len(REFERENCE),
      f"roster dropped someone: {len(rows)} rows for {len(REFERENCE)} entries")
check([r["score"] for r in rows] == sorted((r["score"] for r in rows), reverse=True),
      "roster is not ordered best-first, so a rendered list would number people wrongly")

# --- every name can be checked by a reader --------------------------------
# The docstring at the top of reference.py says reproducibility is the only thing
# that makes it defensible to put a stranger's name on a chart. A row with no
# repositories behind it cannot be checked by anyone.
for r in rows:
    check(r["considered"], f"{r['name']} has no repositories recorded — unverifiable")

missing = set(n.name for n in REFERENCE) - set(CONSIDERED)
check(not missing, f"CONSIDERED is missing entries: {sorted(missing)}")

# --- THE MISMATCH TRAP ----------------------------------------------------
# Andrej Karpathy lists four repositories and scored three. Any UI that prints
# len(considered) as "repositories measured" overstates by one for a named
# person. repos_scored is the count that is true; this test exists so the two
# fields stay distinguishable rather than being quietly conflated later.
by_name = {r["name"]: r for r in rows}
k = by_name.get("Andrej Karpathy")
check(k is not None, "Andrej Karpathy left the set; retarget this test")
if k:
    check(k["repos_scored"] == 3 and len(k["considered"]) == 4,
          "the known scored/considered mismatch changed shape — recheck the UI "
          "that renders both before updating this number")
check(any(r["repos_scored"] != len(r["considered"]) for r in rows),
      "no row now mismatches, so nothing proves the UI still separates "
      "'considered' from 'scored' — verify the page before deleting this")

# --- grades are derived, not carried -------------------------------------
# tools/reference_people.json still says Hynek Schlawack is 'Sovereign' at 86;
# the tier table has since moved Apex down to 85. Deriving the grade keeps the
# whole list on the SAME table as the viewer's own score, which is the only way
# a side-by-side comparison means anything.
for r in rows:
    check(r["grade"] == tier_of(r["score"])[0],
          f"{r['name']} carries a stored grade instead of a derived one")
    check(r["grade_means"], f"{r['name']} has a grade with no explanation")

# --- no network: deliberately NOT re-checked here --------------------------
# The first draft of this file grepped reference.py for "httpx" and "socket" and
# FAILED — on `encode__httpx` and `socketio__socket.io`, which are repository
# names. A substring scan for network libraries matches the data this module is
# made of. test_no_network.py already owns that guarantee and does it by walking
# the AST for real imports across every file in the package, so a second weaker
# copy here could only ever be wrong in one of two directions: a false alarm like
# the one it raised, or a silent pass on an import spelled differently. One
# guarantee, one check, in the file whose whole job it is.

if fails:
    print(f"FAILED ({len(fails)})")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print(f"ok — {len(rows)} reference portfolios, all verifiable")
