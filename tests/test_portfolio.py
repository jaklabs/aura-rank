"""Tests for the aggregation maths.

Deciding which repositories count, and how much, is the only place this project
makes a real judgement call. These pin that behaviour down.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from aurarank.portfolio import aggregate, CORE_COVERAGE


def repo(name, score, weight=10.0, dims=None):
    return {"name": name, "name_hash": name, "score": score, "grade": "x",
            "dimensions": dims or {"rigour": score / 10, "architecture": score / 10,
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
    rs = [repo("a", 60, dims={"rigour": 6.0, "judgment": 6.0, "transmission": 6.0}),
          repo("b", 60, dims={"rigour": 6.0, "architecture": 8.0,
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


def test_all_weights_zero_falls_back_to_equal_weighting():
    # An identity that authored none of the repos gives every weight 0. The
    # weighted mean then divided by a substituted 1.0 and returned 0 -- a real
    # 50-point repo reported as DORMANT. Unweighted is defensible; zero is not.
    rs = [repo("a", 50, weight=0.0), repo("b", 50, weight=0.0)]
    assert aggregate(rs, MONTHS)["score"] == 50


# --- attribution rules -------------------------------------------------------
from aurarank.scan import attribute_commit, _classify

ME = {"me@example.com"}


def test_my_commit_is_mine():
    assert attribute_commit({"me@example.com"}, ME, True) == "mine"


def test_agent_authored_commit_is_mine_when_i_direct_the_repo():
    # The decision Jak made explicitly: agent commits under his direction are his.
    assert attribute_commit({"noreply@anthropic.com"}, ME, True) == "mine"


def test_agent_commit_is_not_mine_in_someone_elses_repo():
    assert attribute_commit({"noreply@anthropic.com"}, ME, False) != "mine"


def test_commit_i_committed_but_an_agent_authored_is_mine():
    assert attribute_commit(
        {"noreply@anthropic.com", "me@example.com"}, ME, False) == "mine"


def test_co_author_trailer_counts():
    assert attribute_commit(
        {"someone@else.com", "me@example.com"}, ME, False) == "mine"


def test_dependency_bots_are_excluded_not_blamed():
    # Excluded from the denominator entirely -- counting a dependabot commit
    # would dilute every human in the repo.
    assert attribute_commit(
        {"49699333+dependabot[bot]@users.noreply.github.com",
         "noreply@github.com"}, ME, True) == "bot"


def test_a_real_collaborator_is_not_mine():
    assert attribute_commit({"colleague@example.com"}, ME, True) == "other"


def test_github_privacy_addresses_are_humans_not_bots():
    # 12345+user@users.noreply.github.com is a person; noreply@github.com is not.
    assert _classify("12345+realperson@users.noreply.github.com") == "human"
    assert _classify("noreply@github.com") == "bot"


def test_service_localparts_are_machines_on_any_domain():
    assert _classify("agent@rork.com") == "agent"


# --- transmission scoring ---------------------------------------------------
from aurarank.scan import score  # noqa: E402


def _dims(contributors, readme=0.5, doc_ratio=0.2, docstrings=0.5):
    g = {"is_git_repo": True, "contributors": contributors, "tags": 3,
         "tenure_days": 400, "revisit_ratio": 0.4, "cadence": 0.8}
    t = {"test_ratio": 0.2, "has_ci": True, "has_docs": True, "doc_ratio": doc_ratio,
         "readme_depth": readme, "substrate_breadth": 2, "packaged": True,
         "production_shape": False, "source_files": 20}
    p = {"parsed_files": 10, "fn_len_p90": 30, "nesting_p90": 2,
         "type_coverage": 0.5, "docstring_coverage": docstrings,
         "except_precision": 0.8}
    return score(g, t, p)["dimensions"]


def test_working_alone_does_not_cost_transmission():
    """The flaw this replaced.

    Contributor count was 25% of transmission, and a solo developer scores zero
    on it by definition -- forfeiting a quarter of "can you make other people
    good" for having no colleagues. On a tool built for developers without a
    company behind them that is exactly backwards. Solo must not be punished.
    """
    solo = _dims(contributors=1)["transmission"]
    pair = _dims(contributors=2)["transmission"]
    assert solo >= pair - 0.5, (
        f"solo {solo} is penalised against a 2-contributor repo {pair}")


def test_many_contributors_still_earns_credit():
    """Dropping the signal when absent must not mean ignoring it when present --
    sustaining a group of contributors is real transmission."""
    assert _dims(contributors=20)["transmission"] > _dims(contributors=2)["transmission"]


def test_a_readme_that_teaches_beats_one_that_exists():
    """Something a solo developer can actually move, unlike contributor count."""
    assert _dims(1, readme=1.0)["transmission"] > _dims(1, readme=0.0)["transmission"] + 1.5


def test_docstrings_still_matter_most_alongside_docs():
    poor = _dims(1, doc_ratio=0.0, docstrings=0.0)["transmission"]
    rich = _dims(1, doc_ratio=0.35, docstrings=0.8)["transmission"]
    assert rich > poor + 4


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


