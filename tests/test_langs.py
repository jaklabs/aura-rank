"""Regression tests for the language analyzers.

The JS/TS scanner is a hand-written heuristic, not a parser. That makes a test
suite the only thing standing between it and silent wrongness -- every case here
is one the scanner previously got wrong, or one it would be easy to break.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from aurarank import langs

TS = '''
/** Adds numbers. */
export function add(a: number, b: number): number {
  if (a > 0) { for (const x of [1]) { while (true) { break; } } }
  return a + b;
}
const re = /\\}\\{/g;
const s = `tmpl ${ {a: 1}.a } end`;
function loose(x: any) { return x; }
async function risky() {
  try { await go(); } catch (e) {}
  try { await go(); } catch (e) { console.error(e); }
  try { await go(); } catch (e) { report(e); throw e; }
}
'''


def summary(src, typed=True):
    return langs.summarize(langs.analyze_js(src, typed_lang=typed))


def test_counts_block_bodied_functions():
    assert summary(TS)["functions"] == 3


def test_braces_in_regex_and_templates_do_not_corrupt_nesting():
    # if > for > while == 3. A `/\}\{/` regex and a `${ {a:1}.a }` interpolation
    # both contain braces that would break naive counting.
    assert summary(TS)["nesting_p90"] == 3


def test_any_does_not_count_as_typed():
    s = summary(TS)
    assert s["typable_functions"] == 3
    assert s["type_coverage"] == 0.333          # only `add`
    assert s["any_annotations"] == 1


def test_empty_and_log_only_catches_are_imprecise():
    s = summary(TS)
    assert s["except_handlers"] == 3
    assert s["imprecise_handlers"] == 2         # empty, and console-only
    assert s["except_precision"] == 0.333


def test_jsdoc_survives_export_modifier():
    assert summary(TS)["docstring_coverage"] > 0


def test_plain_js_is_not_penalised_for_being_untyped():
    # A .js file CANNOT carry annotations. Scoring it 0% typed would be measuring
    # the language, not the developer -- so it must be excluded, not zeroed.
    s = summary("function f(a) { return a; }", typed=False)
    assert s["typable_functions"] == 0
    assert s["type_coverage"] is None


def test_python_still_works():
    a = langs.analyze_python(
        "def f(x: int) -> int:\n    '''doc'''\n    try:\n        pass\n"
        "    except ValueError:\n        pass\n    return x\n")
    s = langs.summarize(a)
    assert s["functions"] == 1
    assert s["type_coverage"] == 1.0
    assert s["docstring_coverage"] == 1.0
    assert s["except_precision"] == 1.0


# --- test quality -----------------------------------------------------------

REAL = '''
def test_a_missing_issue_number_is_a_safe_no_op():
    """Never crash, and never claim clear as though it checked."""
    r = guard.check(None)
    assert r["alreadyBilled"] is False
    assert "no issue" in r["verdict"]

def test_a_voided_invoice_does_not_block_a_rebill():
    r = guard.check("103384", invoices=[{"TotalAmt": 0}])
    assert r["paid"] == []
'''

HOLLOW = "\n".join(f"def test_{i}(): pass" for i in range(40))


def test_hollow_test_files_cannot_game_the_score():
    """The whole reason this exists.

    A file-count ratio rewards forty empty test functions over two that each
    encode a real incident. Depth has to invert that, or the metric is an
    invitation to write filler.
    """
    real = langs.test_quality(langs.analyze_tests_python(REAL), source_modules=10)
    hollow = langs.test_quality(langs.analyze_tests_python(HOLLOW), source_modules=10)
    assert real["quality"] > hollow["quality"] * 4
    assert hollow["quality"] < 0.1


def test_assertions_and_edge_cases_are_both_counted():
    q = langs.test_quality(langs.analyze_tests_python(REAL), source_modules=10)
    assert q["test_functions"] == 2
    assert q["assertions_per_test"] >= 1.5
    assert q["edge_case_ratio"] > 0        # "missing", "None", "voided"


def test_no_tests_means_unmeasured_not_zero():
    """A repo with no tests has no test QUALITY to report. Returning 0.0 would be
    the fallback bug this project keeps producing -- absent is not bad."""
    assert langs.test_quality(langs.analyze_tests_python("x = 1"), source_modules=10) is None


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
