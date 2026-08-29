"""Console entry point: `aurarank <command>`.

A thin router over the two modules that do the work, so an installed copy reads
the same as the documented `python3 -m aurarank.scan`. Both forms stay supported
-- the module form is what the README teaches, because it works from a clone with
nothing installed.
"""

from __future__ import annotations

import sys

USAGE = """aurarank — a developer rank that never sees your code

  aurarank scan <path>            grade one repository
  aurarank portfolio <paths...>   aggregate many into one profile

Both accept --help. Equivalent module forms, which work from a clone with
nothing installed:

  python3 -m aurarank.scan <path>
  python3 -m aurarank.portfolio <paths...>

Your source never leaves this machine. Verify before you run it:
  grep -rnE 'requests|urllib|http|socket|aiohttp|httpx|ssl' aurarank/
"""


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(USAGE)
        raise SystemExit(0)

    command, rest = sys.argv[1], sys.argv[2:]

    if command == "scan":
        from . import scan as module
    elif command == "portfolio":
        from . import portfolio as module
    else:
        print(f"unknown command: {command}\n", file=sys.stderr)
        print(USAGE, file=sys.stderr)
        raise SystemExit(2)

    # argparse in each module reads sys.argv, so hand it a clean one.
    sys.argv = [f"aurarank {command}", *rest]
    module.main()


if __name__ == "__main__":
    main()
