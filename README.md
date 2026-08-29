# AURA

**A developer rank you can actually verify — that never sees your code.**

Working name. Spec `v0.7.0`. Early, opinionated, and open on purpose.

```
+--------------------------------------------------------------+
|  AURA  ·  local scan  ·  spec v0.5.0                         |
+--------------------------------------------------------------+
|  SOVEREIGN   87/100                                               |
|  best-in-class. Reference-grade engineering                  |
|  self-assessed · 4 of 8 dimensions measured                  |
+--------------------------------------------------------------+
|  ship           #################### 10.0                    |
|  architecture   ###############.....  7.6                    |
|  judgment       ###################.  9.4                    |
|  transmission   ##################..  9.1                    |
+--------------------------------------------------------------+
   Nothing left this machine.
```
<sub>`pallets/flask`, scanned locally in 0.4s. Nothing about it left the machine.</sub>

---

## The problem

There is no way for a developer without a famous employer to show what they can do.

GitHub stars measure marketing. Years of experience measure patience. LeetCode measures
LeetCode. Meanwhile the people who are actually good — the ones running production systems
alone, for real businesses, without a logo behind them — have no legible signal at all.

And the obvious fix is unacceptable: **nobody is uploading their private codebase to a
website to get a score.** Not their client's code, not their startup's code, not their own.
Any ranking system that requires it is dead on arrival, and should be.

## The design that makes it possible

Split the scan from the claim.

```
  LOCAL — never leaves your machine        PUBLIC — opt-in, independently checkable
  +-------------------------------+        +----------------------------------+
  |  aura scan ./repo             |        |  aura attest                     |
  |    git metadata (dates only)  |        |    published packages            |
  |    file tree structure        |        |    public repos + dependents     |
  |    AST metrics (counts only)  |        |    merged contributions          |
  |                               |        |                                  |
  |  emits: integers and ratios   |        |  emits: a signed, checkable claim|
  |  NO NETWORK CODE AT ALL       |        |  separate binary. separate opt-in|
  +-------------------------------+        +----------------------------------+
                  \                                     /
                   \                                   /
                    v                                 v
                  +---------------------------------------+
                  |  rank engine — open, versioned spec    |
                  +---------------------------------------+
```

`aura scan` **contains no network code.** That is not a privacy policy, it is a property of
the source, and you verify it yourself before you ever run the thing:

```bash
grep -rnE 'requests|urllib|http|socket|aiohttp|httpx|ssl' aura/
```

The only matches are the docstrings telling you to run it.

**One honest caveat, because a half-true guarantee is worse than none:** the scanner
does use `subprocess` — to run `git`, which is how it reads your commit history. A grep
can't distinguish "runs git" from "runs anything," so that's enforced by a test instead.
[`tests/test_no_network.py`](tests/test_no_network.py) parses every module and fails if a
subprocess call ever invokes something other than `git`, if any network library is
imported, or if `shell=True`, `eval` or `exec` appear. CI runs it on every push.

Everything it emits is integers and ratios. No source text, no file contents, no absolute
paths, no email addresses (author identities are hashed on read and never stored). Read the
exact payload before you share it with anyone:

```bash
python3 -m aura.scan ./your-repo --print
```

## Three tiers of claim

The reason most scoring systems become worthless is that they let unverifiable
self-reports sit in the same table as verified facts. This one keeps them apart, visibly.

| Tier | What it means | Fakeable? |
|---|---|---|
| **Self-assessed** | You ran the scan. The JSON is yours, on your disk. | Trivially — it's your file, and we say so |
| **Attested** | Public artifacts checked against public APIs | Hard. Anyone can re-run the check |
| **Witnessed** | An already-ranked developer vouches for a claim | Costs the voucher their own standing |

Self-assessed is the fun one and it's the default. It is **never** presented as
verified, because the moment a ranking system blurs that line it stops being worth anything.

## What it measures, and what it refuses to

Eight dimensions. **Four are measurable from a repository. Four are not**, and this tool
will not pretend otherwise.

| Dimension | Source | Why |
|---|---|---|
| **Ship** | measured | tests, CI, release tags, tenure, project shape |
| **Architecture** | measured | function length + nesting distributions, substrate breadth, typing (`: any` doesn't count) |
| **Judgment** | measured | revisit ratio, exception precision, cadence |
| **Transmission** | measured | doc ratio, docstring coverage, contributors |
| **Embed** | claim + witness | whether you can sit with a customer is not in your AST |
| **Fundamentals** | optional challenge | a timed exercise, not a repo property |
| **Reach** | attested | dependents, installs — public by nature |
| **Renown** | attested | public record — public by nature |

A system that claimed to measure whether you can map a messy business by reading your
source would be obvious nonsense to exactly the people whose respect it needs.

### The load-bearing signal

`revisit_ratio` — the share of files touched in more than one distinct calendar month.

It separates maintained work from dump-and-run work, it is invisible to anyone optimising
for stars or commit counts, and **it cannot be faked without actually doing the thing.**
Most vanity metrics reward volume. This one rewards coming back.

## Anti-gaming

If it works at all, people will game it. Design consequences:

- **Nothing scores on volume.** Not commits, not lines, not repo count. All trivially inflated.
- **Ratios and sustained time only.** You cannot retroactively manufacture three years of
  monthly maintenance without leaving an obvious signature.
- **The spec is open**, so gaming is visible and gets patched like a CVE.
- **Nothing unverifiable is ever scored at the attested tier.**

## Quick start

```bash
git clone <repo> && cd aura-rank
python3 -m aura.scan ~/code/your-project          # stdlib only. no install, no deps.
python3 -m aura.scan ~/code/your-project --print  # audit the exact payload
python3 -m aura.scan ~/code/your-project --json me.json
```

Requires Python 3.9+ and `git`. Nothing else. There are no dependencies, deliberately —
a tool that asks you to trust it should not ask you to install forty packages first.

## Status

- [x] Local scanner — git, tree, and Python AST signals
- [x] Open scoring spec, versioned
- [x] Terminal rank card
- [x] Calibration against a public corpus — bands anchored + validated
- [x] Multi-repo aggregation — `aura portfolio`
- [x] JS/TS analyzer — hand-written scanner, zero dependencies
- [ ] Go and Rust analyzers
- [ ] `aura attest` (public signals, separate binary)
- [ ] Witness protocol

### Calibrated — with stated bias

Bands are set against a corpus of 52 public Python/JS/TS repositories plus real private
work, and **validated rather than percentile-fitted** — fitting to the public corpus alone
would put every genuine user in the bottom band. Reproduce it:

```bash
python3 tools/calibrate.py --clone
```

Anchors: `scrapy` **88** · `flask` **87** · `fastapi` **86** · `requests` **84** · `express`
**78** · `axios` **76** · `zod` **72**. A typical solo project lands 15–45.

**The corpus is small (n=52), elite, and covers three languages.** It anchors the top of the scale
credibly and says little about the middle. The per-dimension breakdown is the useful output;
the single number is provisional. Full method, the three bugs calibration exposed, and every
known bias: **[tools/CALIBRATION.md](tools/CALIBRATION.md)**.

## Licence

**MIT.** Fork it, audit it, embed it, sell something built on it. Auditability is the
entire value proposition here — a restrictive licence would defeat the point of the tool.

_(Apache-2.0 was the alternative and adds an explicit patent grant; MIT was chosen for
being shorter and more permissive. Say so if you want it swapped.)_

---

Built by [JAK Labs](https://jaklabs.io) · [rank.jaklabs.io](https://rank.jaklabs.io)
