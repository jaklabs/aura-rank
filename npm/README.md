# aurarank

`npx` wrapper for [**aura-rank**](https://github.com/jaklabs/aura-rank) — a developer rank
that never sees your code.

```bash
pip install aura-rank      # the analyzer itself (Python, zero dependencies)
npx aurarank scan ~/code/your-project
npx aurarank portfolio ~/code/*/
```

The analyzer is Python. This package exists so JavaScript and TypeScript developers can
reach it without a clone — it shells out to the real scanner and adds nothing of its own.

**Your source never leaves your machine.** The scanner imports no HTTP client and opens no
socket, and a test in CI fails the build if that ever changes. Full detail and the
verification command: <https://rank.jaklabs.io>

MIT.
