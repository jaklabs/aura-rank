"""Regression tests for the language analyzers.

The JS/TS scanner is a hand-written heuristic, not a parser. That makes a test
suite the only thing standing between it and silent wrongness -- every case here
is one the scanner previously got wrong, or one it would be easy to break.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from aura import langs

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
