# Calibration — how the bands were set, and what's still wrong with them

Spec `v0.9.0`. Run `python3 tools/calibrate.py --clone` to reproduce everything here.

## Why the first attempt was thrown away

The obvious method is: score a corpus, set band boundaries at percentiles, done. **That
method is wrong here, and running it is what proved it.**

The corpus is 36 well-known public Python libraries. Their median score is **78**. A sample
of nine real solo/private repositories has a median of **26**. Those are two different
populations with almost no overlap, and percentile-fitting to the first one would put
essentially every genuine user of this tool in the bottom band — which is useless as
feedback and wrong as a description.

So the bands are **anchored on meaning** and then **validated against both populations**.
`tools/calibrate.py` no longer fits; it checks.

## Three bugs the first run exposed

Calibration earned its keep before it produced a single band.

| Bug | Symptom | Cause |
|---|---|---|
| `.github` excluded from the walk | `has_ci` false for **all 36** repos, Flask included | the skip rule was `d.startswith(".git")`, which also matches `.github` |
| `rigour` degenerate | p25 = median = p75 = **6.5**, an identical score for half the corpus | every component saturated: tests, CI, tenure all maxed, IaC and migrations absent for libraries |
| `transmission` degenerate | 10.0 for 34 of 36 repos | three boolean-ish inputs that all mature OSS passes |

A fourth was fixed pre-emptively during the run: a repo with no Python was having its
Architecture score computed from *default* AST values rather than being marked unmeasured.
Missing measurements are now dropped and the remaining weights renormalised.

## What changed in the model

- **Graded signals replaced boolean gates.** `doc_ratio` and `docstring_coverage` instead of
  `has_docs`; release-tag count instead of nothing; contributor band widened 1→25.
- **Ranges widened to the observed distribution.** `test_ratio` was banded 0→0.5 when the
  corpus median is 0.88 and the max is 4.95. Nearly everything saturated.
- **Project shape is respected.** A library with no Terraform is not deficient, it is a
  library. Service-shaped (IaC, migrations) and library-shaped (packaged and published)
  repos each get a route to full marks instead of being scored against the other's checklist.

Result: `transmission` went from a flat 10.0 to a real 2.9–9.4 spread, and separation between
flagship and small projects widened from 7.5 points to 12.

## The bands

| Band | Range | Means |
|---|---|---|
| Dormant | 0–14 | little engineering signal yet — a scratch or scratch-shaped repo |
| Kindled | 15–29 | working code, shipped, but no test or CI discipline behind it |
| Drawn | 30–44 | discipline appearing — some tests, some structure |
| Formed | 45–59 | real practice: tested, documented, maintained over time |
| Marked | 60–72 | professional open-source standard — others could rely on this |
| Sealed | 73–81 | a strong, well-maintained library others do rely on |
| Sovereign | 82–88 | flagship quality — among the best-run projects in its language |
| Apex | 89–100 | best-in-class. Reference-grade engineering |

### Validation

Corpus occupancy (n=36 elite public libraries):

```
  Kindled     15-29   #                          n=1
  Marked      60-72   #######                    n=7
  Sealed      73-81   #############              n=13
  Sovereign   82-88   ##############             n=14
  Apex        89-100  #                          n=1
```

35 of 36 land in Marked→Apex, which is the correct answer for that population — if elite
libraries *didn't* sit high the bands would be broken, and that is what makes this a check
rather than a tautology. The single Kindled outlier is `chrisdonahue/wavegan`, an abandoned
research repo: no tests, no CI, no maintenance since publication. Correctly placed.

Named anchors: `pallets/flask` **90** (Apex) · `simonw/datasette` **83** · `psf/requests`
**79** · `scrapy/scrapy` **74** · `simonw/shot-scraper` **71**.

## Known bias — read this before trusting a number

1. **The corpus is elite and small.** 36 repos, all published, maintained, Python-majority
   open source. That is a tiny and unrepresentative slice of software. It anchors the *top*
   of the scale credibly and says nothing reliable about the middle.
2. **The low anchor is worse.** Nine private repositories from a single developer. It is
   directionally right and statistically nothing.
3. **Three languages, and JS/TS is heuristic.** Python uses a real AST. JavaScript and
   TypeScript use a hand-written lexical scanner, because a real parser would mean a
   dependency and the zero-dependency property is what makes the tool auditable. Its
   limits ship in the payload as `js_scanner_limits`. Every other language has
   Architecture marked unmeasured.
4. **`has_ci` is 97% true in the corpus.** It no longer discriminates *within* open source.
   It is kept because it discriminates sharply against typical private work, which is the
   population that will actually run this.
5. **Repos are not developers.** A single score describes one repository; use
   `aura portfolio` for a person. Since v0.7.0 agent-authored commits count as the
   directing human's work, so AI-assisted development is no longer diluted.
6. **`hash()` was unstable until v0.6.0.** Identifier hashes in payloads from earlier
   versions changed on every run and cannot be compared. Fixed with blake2s.

## Round two — adding JavaScript/TypeScript (v0.4.0 → v0.5.0)

Extending the corpus to 54 repos exposed three more faults, two of them worse than
anything in round one.

| Bug | Symptom | Cause |
|---|---|---|
| **A git timeout was scored as a result** | `date-fns` reported `revisit_ratio` **0.0** across 3,124 commits — an actively maintained library reading as abandoned | `_git()` swallowed `TimeoutExpired` and returned `""`, which callers read as "no history". Its score was **56**; it is really **65** |
| Catastrophic regex backtracking | some files took minutes | the method pattern used `(?:public\|private\|…\|\s)*`, whose `\s` branch could match newlines |
| Quadratic brace matching | scan time scaled with the square of file size | `_match_brace` rescanned to end-of-file once per function |

The first is the serious one, and it is the **third instance of the same class** this
project has produced: *a failure silently substituted with a plausible-looking value.*
Architecture defaulting from absent AST data, plain `.js` scored as 0% typed, and now a
timeout scored as zero maintenance. `_git()` returns `None` on failure now, and every
consumer drops the signal rather than zeroing it.

### Performance

A full scan of `prettier/prettier` went **>300s → 1.6s**, and five large repos
**80.1s → 3.2s**. The fixes: one regex pass instead of a per-character state machine,
a single O(n) brace scan replacing per-function rescans, token-driven iteration, and a
bounded `--since=3.years` window on the revisit walk.

That last one is not only a speed fix. Over fifteen years of history nearly every
surviving file gets touched in more than one month, so the unbounded ratio drifts toward
1.0 and stops discriminating. **The recent window is both faster and a sharper signal.**

### Does the JS analyzer agree with the Python one?

The question that decides whether cross-language scores are comparable at all:

| Language mix | n | median |
|---|---|---|
| python | 29 | 78.0 |
| javascript + typescript | 14 | 74.0 |
| javascript + python | 7 | 82.0 |
| javascript | 2 | 73.5 |

**Within four points.** A hand-written lexical scanner landing that close to a real AST
is the result that had to hold — if JS repos had come in twenty points low, the analyzer
would be measuring the parser rather than the code.

Occupancy over 52 scored repos (2 skipped as too small to say anything about):

```
  Kindled    15-29   #                          n=1
  Formed     45-59   #####                      n=5
  Marked     60-72   ###########                n=11
  Sealed     73-81   ######################     n=22
  Sovereign  82-88   #############              n=13
  Apex       89-100                             n=0
```

Anchors: `scrapy` **88** · `flask` **87** · `fastapi` **86** · `requests` **84** ·
`express` **78** · `axios` **76** · `zod` **72** · `react-window` **55**.

**Apex is empty**, which is the one band this corpus cannot validate. Either it is
correctly reserved for something rarer than n=52 can sample, or its floor is too high.
Unresolved, and stated rather than hidden.

## What would make this real

- A representative sample — a few thousand repos across the popularity distribution,
  including abandoned, small and application-shaped ones, not just libraries.
- Go and Rust analyzers, and a resolution for the empty Apex band.
- Multi-repo aggregation, so the unit of measurement is a person rather than a directory.

Until then: **the per-dimension breakdown is the useful output, and the single number is
provisional.** Said here rather than discovered by a user.

## Round three — fitting the middle to a real population (v0.9.0)

The bands were previously anchored on meaning and validated against 52 hand-picked
libraries. That could only ever anchor the ceiling; the middle of the scale was
reasoned, not fitted, because flagship open source is not what most software is.

`tools/discover.py` samples public repositories at random across the whole
popularity range, scores them and stores no identity. That gave the project its
first thing resembling a population, and `tools/recalibrate.py` fits the middle
to it while the elite corpus continues to anchor the top.

### The sampler was biased, and the first refit was wrong

The first pass queried `pushed:>2024-01-01`, which silently excluded every
abandoned repository. The "ordinary" population it measured was really *ordinary
and still maintained*, median **55**. Bands fitted to that were too harsh — wrong
in the same direction as the elite corpus, just less visibly.

Sampling the abandoned tail (`pushed:<2021-01-01`) returned scores of 18, 24, 27,
30, 32, 36, 37, 38, 38, 39, 43, 49, 50 and 60 — a median near **37**. Adding them
moved the population median from 55 to **48**, and the bands with it.

That is the sixth instance in this project of a filter or fallback quietly
changing what a measurement means. The others: a git timeout scored as zero
maintenance, absent AST data defaulting Architecture, plain `.js` scored 0% typed,
`.github` excluded from the walk, and a `head -1` pipeline killing a script
mid-run.

### Bands as of v0.9.0

| Band | Range | Anonymous % | Elite % |
|---|---|---:|---:|
| Dormant | 0–26 | 6% | 2% |
| Kindled | 27–36 | 17% | 0% |
| Drawn | 37–43 | 22% | 0% |
| Formed | 44–54 | 19% | 2% |
| Marked | 55–63 | 24% | 10% |
| Sealed | 64–77 | 11% | 35% |
| Sovereign | 78–84 | 2% | 42% |
| Apex | 85–100 | 0% | 10% |

### Deepened to n=82 — and the bands held

Doubling the sample (54 -> 82) moved the population median only 48 -> 49, and a
score of 39 stayed in the same band through the refit. **That stability is the
first evidence the scale is converging** rather than tracking whatever happened to
be sampled last. The bands shifted by 1-3 points at the edges and not at all in
their meaning.

| Band | Range | Anonymous % |
|---|---|---:|
| Dormant | 0–23 | 6% |
| Kindled | 24–33 | 16% |
| Drawn | 34–42 | 22% |
| Formed | 43–53 | 20% |
| Marked | 54–61 | 15% |
| Sealed | 62–77 | 18% |
| Sovereign | 78–84 | 2% |
| Apex | 85–100 | 0% |

**Still provisional, on two counts.** Apex remains occupied by nobody in either
corpus — either its floor is too high or it is correctly rarer than 134 repos can
sample. And the anonymous corpus is public code only; private and client work,
which is most software, is invisible to any sampler by construction.

One operational note: GitHub search allows roughly 30 queries a minute. The
sampler slept 1 second between them and got rate-limited; it now sleeps 2.5.
