"""Tests for the aggregation maths.

Deciding which repositories count, and how much, is the only place this project
makes a real judgement call. These pin that behaviour down.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from aura.portfolio import aggregate, CORE_COVERAGE


def repo(name, score, weight=10.0, dims=None):
    return {"name": name, "name_hash": name, "score": score, "grade": "x",
            "dimensions": dims or {"ship": score / 10, "architecture": score / 10,
                                   "judgment": score / 10, "transmission": score / 10},
            "share": 1.0, "mass": weight, "weight": weight,
            "languages": ["python"], "active_months": 6, "tenure_days": 200}


MONTHS = {"2026-0%d" % i for i in range(1, 7)}


def test_core_covers_the_configured_share_of_weight():
    rs = [repo(f"r{i}", 50) for i in range(10)]
    out = aggregate(rs, MONTHS)
    covered = sum(r["weight"] for r in out["repos"][:out["repos_in_core"]])
    assert covered >= sum(r["weight"] for r in rs) * CORE_COVERAGE


def test_scratch_repos_do_not_drag_down_strong_work():
    # Five strong repos plus fifteen abandoned ones. A mean would say ~35 and
    # punish the developer for experimenting; the core statistic must not.
    rs = [repo(f"good{i}", 80) for i in range(5)] + \
         [repo(f"scratch{i}", 15, weight=2.0) for i in range(15)]
    out = aggregate(rs, MONTHS)
    mean = sum(r["score"] for r in rs) / len(rs)
    assert out["score"] > mean + 15
    assert out["score"] >= 75


def test_one_good_repo_among_many_bad_does_not_max_the_score():
    # The opposite failure: `max` would call this an elite engineer.
    rs = [repo("good", 90)] + [repo(f"bad{i}", 20) for i in range(9)]
    out = aggregate(rs, MONTHS)
    assert out["score"] < 90
    assert out["repos_in_core"] > 1


def test_bigger_longer_repos_carry_more_weight():
    rs = [repo("big", 70, weight=40.0), repo("tiny", 20, weight=1.0)]
    out = aggregate(rs, MONTHS)
    assert out["score"] > 65          # the substantial project dominates


def test_dimension_missing_from_some_repos_is_not_counted_as_zero():
    # A repo with no parseable code has no architecture score. Averaging it in
    # as zero would be the same fallback bug this project keeps finding.
    rs = [repo("a", 60, dims={"ship": 6.0, "judgment": 6.0, "transmission": 6.0}),
          repo("b", 60, dims={"ship": 6.0, "architecture": 8.0,
                              "judgment": 6.0, "transmission": 6.0})]
    out = aggregate(rs, MONTHS)
    assert out["dimensions"]["architecture"] == 8.0


def test_focus_detects_scatter_versus_concentration():
    spread = aggregate([repo(f"r{i}", 50) for i in range(20)], MONTHS)
    single = aggregate([repo("one", 50, weight=100.0),
                        repo("two", 50, weight=1.0)], MONTHS)
    assert spread["portfolio_signals"]["focus"] < 0.1
    assert single["portfolio_signals"]["focus"] > 0.9


def test_spread_reports_best_minus_median():
    rs = [repo("a", 80), repo("b", 40), repo("c", 40)]
    s = aggregate(rs, MONTHS)["portfolio_signals"]
    assert s["best"] == 80 and s["median"] == 40 and s["spread"] == 40


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  PASS  {name}")
            except AssertionError as e:
                fails += 1; print(f"  FAIL  {name}: {e}")
    print(f"\n{'all passed' if not fails else str(fails) + ' FAILED'}")
    sys.exit(1 if fails else 0)
