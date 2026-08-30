# Contributing

Pull requests welcome. The scoring spec especially — if you can show a band is wrong or
a signal is gameable, that is the most valuable thing you can send.

## Run the tests

```bash
python3 tests/test_no_network.py    # the trust guarantee. run this one first
python3 tests/test_langs.py
python3 tests/test_portfolio.py
```

No dependencies, no fixtures to install, under a second. CI runs all three on Python
3.9 through 3.13.

## The one rule that cannot bend

**`aurarank/` never touches the network.** No HTTP client, no socket, and `subprocess`
only ever invokes `git`. This is enforced by `tests/test_no_network.py`, which parses
every module and fails the build on a network import, a subprocess call whose `argv[0]`
is not the literal `"git"`, `shell=True`, or `eval`/`exec`.

Anything that needs the network lives in `tools/`, which nobody has to run. That
separation is the entire reason this tool can be trusted with private code, so a PR that
blurs it will be declined regardless of how useful the feature is.

## Four questions, from bugs this project actually shipped

These are not style preferences. Each one is a class of bug that reached `main` here, and
they are listed with the damage they did.

### 1. "Can two real things share this value?"

Ask before keying, matching or joining on anything. Addresses, names, emails and
filenames are **attributes, not identities**.

The identity harness once inferred "whoever committed most in this repo" and then printed
a famous name beside it. It would have published **John Gee's work on commander.js under
TJ Holowaychuk's name**, and two commits by a contributor under John Carmack's. It is now
required to verify the match and drop the entry otherwise.

### 2. "What does this return when it fails?"

Return `None` and let the caller drop the signal. **Never a plausible-looking default.**

This project has produced that bug **seven times**: a git timeout returning `""` scored an
actively maintained library as abandoned; absent AST data defaulted an Architecture score;
plain `.js` was scored 0% typed when it *cannot* carry annotations; a date filter silently
excluded every abandoned repository from the calibration sample.

A missing measurement and a bad measurement are different facts and must not produce the
same number. `_weighted()` exists for exactly this — it drops absent components and
renormalises rather than zeroing them.

### 3. "Was this knowable at the time?"

Every derived value carries its source and its as-of moment. A signal computed from data
that did not exist at decision time is look-ahead bias, and it looks like alpha right up
until it costs money.

### 4. Keep the seam

Functions take their data as arguments; callers fetch it. `score()` takes dicts.
`aggregate()` takes already-scored repos. `test_quality()` takes counters.

That is the only reason this codebase can be tested offline in under a second — and a
function that fetches its own data cannot be tested at all.

## Tests come from incidents, not coverage targets

Every test here exists because something broke. `test_hollow_test_files_cannot_game_the_score`
exists because the scorer once rewarded filler. `test_working_alone_does_not_cost_transmission`
exists because a solo developer was being penalised 25% of a dimension for having no
colleagues.

If you fix a bug, add the test that would have caught it. If you cannot write that test,
say so in the PR — sometimes the answer is a documented limitation rather than code, and
`test_an_invoice_that_never_cites_the_work_order_is_invisible_to_the_guard` is what that
looks like.

## Changing the scoring spec

Bump `SPEC_VERSION`, say what moved and why, and re-run `tools/recalibrate.py`. Scores
from different spec versions are not comparable and the payload records which produced it.

If a change makes the tool look *better* at the user's expense, that is a bug. Two recent
changes lowered scores on purpose: correct attribution counted work previously dropped,
and README substance replaced a component solo developers could not move. **A metric that
only ever goes up is not measuring anything.**
