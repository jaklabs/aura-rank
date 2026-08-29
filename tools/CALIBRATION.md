# Calibration — how the bands were set, and what's still wrong with them

Spec `v0.3.0`. Run `python3 tools/calibrate.py --clone` to reproduce everything here.

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
| `ship` degenerate | p25 = median = p75 = **6.5**, an identical score for half the corpus | every component saturated: tests, CI, tenure all maxed, IaC and migrations absent for libraries |
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
3. **Python only.** The AST analyzer parses Python. Other-language repos have Architecture
   marked unmeasured, which is honest but leaves them scored on three dimensions instead of
   four.
4. **`has_ci` is 97% true in the corpus.** It no longer discriminates *within* open source.
   It is kept because it discriminates sharply against typical private work, which is the
   population that will actually run this.
5. **Repos are not developers.** A score describes one repository. A developer is not their
   worst repo, and this tool does not yet aggregate across several.

## What would make this real

- A representative sample — a few thousand repos across the popularity distribution,
  including abandoned, small and application-shaped ones, not just libraries.
- JS/TS and Go analyzers, so the corpus stops being Python-shaped.
- Multi-repo aggregation, so the unit of measurement is a person rather than a directory.

Until then: **the per-dimension breakdown is the useful output, and the single number is
provisional.** Said here rather than discovered by a user.
