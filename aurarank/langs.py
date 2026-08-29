"""
Per-language source analyzers. Pure text in, counters out.

    NO NETWORK. NO DEPENDENCIES. NO CODE EXECUTION.

Nothing here imports a network library, and nothing here evaluates or executes the
source it reads -- it is only ever parsed or scanned as text:

    grep -rnE 'requests|urllib|http|socket|aiohttp|httpx|ssl' aurarank/

The package DOES use `subprocess`, in scan.py, exclusively to invoke `git` and
read local history. That is the honest version of the claim, and a grep cannot
tell "runs git" from "runs anything", so it is enforced by a test instead:
tests/test_no_network.py asserts every subprocess call has the literal "git" as
its executable, and CI runs it on every push.

Python uses the standard-library `ast` module. JavaScript and TypeScript have no
parser in the standard library and adding one would mean a dependency, so they get
a hand-written lexical scanner instead. It is a heuristic, it is documented as one,
and its limits are listed in `JS_LIMITATIONS` below.

Every analyzer returns the same accumulator shape so a polyglot repository can be
measured by merging them rather than by picking a winner.
"""

from __future__ import annotations

import ast
import bisect
import re

# Honest scope statement. Surfaced in the payload so nobody has to read the source
# to discover what the JS scanner cannot see.
JS_LIMITATIONS = [
    "lexical scanner, not a parser -- no scope or type resolution",
    "arrow functions with expression bodies (x => x*2) are not counted as functions",
    "nesting counts control-flow blocks only, not object or class literals",
    "decorators and overload signatures may be counted as separate declarations",
    "template-literal interpolations are opaque -- code inside ${...} is not scanned",
    "minified, bundled and generated files are skipped, not analyzed",
]

# Authored code only. A minified bundle is not a person's work, and scoring it
# would measure their build tool.
MAX_SOURCE_BYTES = 150_000
MAX_LINE_FOR_AUTHORED = 500


def looks_generated(src: str) -> bool:
    if len(src) > MAX_SOURCE_BYTES:
        return True
    head = src[:4000]
    if "@generated" in head or "DO NOT EDIT" in head.upper():
        return True
    # Minified files are a handful of enormous lines.
    return max((len(ln) for ln in src.split("\n", 400)[:400]), default=0) > MAX_LINE_FOR_AUTHORED


def blank() -> dict:
    """The shared accumulator. Every analyzer fills this shape."""
    return {
        "parsed": 0,
        "fns": 0,
        "lengths": [],       # function line-lengths
        "depths": [],        # control-flow nesting depth per function
        "typed": 0,          # functions carrying type annotations
        "typable": 0,        # functions where typing is POSSIBLE (py, ts -- not plain js)
        "documented": 0,     # functions with a docstring / JSDoc block
        "handlers": 0,       # except / catch blocks
        "imprecise": 0,      # bare except, broad except, empty catch, log-and-swallow
        "any_hits": 0,       # TS `: any` -- the typed-language escape hatch
    }


def merge(*accs: dict) -> dict:
    """Combine analyzers so a polyglot repo is measured across all of its code."""
    out = blank()
    for a in accs:
        for k, v in a.items():
            if isinstance(v, list):
                out[k].extend(v)
            else:
                out[k] += v
    return out


# ---------------------------------------------------------------------------
# Python -- real AST, via the standard library
# ---------------------------------------------------------------------------

def _py_depth(node, d: int = 0) -> int:
    nesting = (ast.If, ast.For, ast.While, ast.With, ast.Try,
               ast.AsyncFor, ast.AsyncWith)
    best = d
    for child in ast.iter_child_nodes(node):
        best = max(best, _py_depth(child, d + isinstance(child, nesting)))
    return best


def analyze_python(src: str) -> dict:
    a = blank()
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError):
        return a
    a["parsed"] = 1
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a["fns"] += 1
            a["typable"] += 1
            if node.end_lineno and node.lineno:
                a["lengths"].append(node.end_lineno - node.lineno + 1)
            a["depths"].append(_py_depth(node))
            args = list(node.args.args) + list(node.args.kwonlyargs)
            if node.returns is not None or (args and all(x.annotation for x in args)):
                a["typed"] += 1
            if ast.get_docstring(node):
                a["documented"] += 1
        elif isinstance(node, ast.ExceptHandler):
            a["handlers"] += 1
            if node.type is None:
                a["imprecise"] += 1
            elif isinstance(node.type, ast.Name) and node.type.id in (
                    "Exception", "BaseException"):
                a["imprecise"] += 1
    return a


# ---------------------------------------------------------------------------
# JavaScript / TypeScript -- hand-written lexical scanner
# ---------------------------------------------------------------------------

# A `/` begins a regex literal (rather than division) only where an operand
# cannot legally have just ended. This is the standard heuristic.
_REGEX_OK_BEFORE = set("(,=:[!&|?{};+-*%~^<>")
_REGEX_OK_WORDS = {"return", "typeof", "instanceof", "in", "of", "new",
                   "delete", "void", "case", "do", "else", "yield", "await"}


# One alternation, applied by the regex engine in C, instead of a per-character
# state machine in Python. The state-machine version was correct but scanned a
# large repository in minutes rather than seconds, which for a tool people run
# casually is the same as being broken.
#
# Order matters: comments, then quoted strings, then template literals, then
# regex literals (whose leading character disambiguates them from division).
_NONCODE = re.compile(
    r"""
      //[^\n]*                                     # line comment
    | /\*[\s\S]*?\*/                              # block comment
    | '(?:\\.|[^'\\\n])*'                          # single-quoted string
    | "(?:\\.|[^"\\\n])*"                          # double-quoted string
    | `(?:\\.|[^`\\])*`                            # template literal (whole)
    | (?<=[(,=:\[!&|?{;+\-*%~^<>])\s*
      /(?:\\.|\[(?:\\.|[^\]\\\n])*\]|[^/\\\n])+/[gimsuyd]*   # regex literal
    """,
    re.X,
)

_KEEP_NEWLINES = re.compile(r"[^\n]")


def _blank_noncode(src: str) -> str:
    """Replace comments, strings, template literals and regex literals with spaces.

    Length and newlines are preserved so line numbers stay correct. Without this,
    a brace inside a string or a comment corrupts every depth measurement.

    Template literals are blanked WHOLE, interpolations included. Treating `${...}`
    as opaque loses function declarations written inside an interpolation -- rare,
    and worth it to avoid a recursive brace-tracking pass over every file.
    """
    return _NONCODE.sub(lambda m: _KEEP_NEWLINES.sub(" ", m.group(0)), src)


# Bounded quantifiers throughout, and no pattern may match across a newline.
# The previous method pattern used `(?:public|private|...|\s)*`, where the `\s`
# branch could match newlines -- catastrophic backtracking that made some files
# take minutes.
_FN_PATTERNS = [
    re.compile(r"\b(?:async[ \t]+)?function[ \t]*\*?[ \t]*[\w$]*[ \t]*\("),
    re.compile(r"[=:,(\[][ \t]*(?:async[ \t]+)?\([^()\n]{0,300}\)[ \t]*"
               r"(?::[^=;{\n]{0,120})?=>[ \t]*\{"),
    re.compile(r"[=:,(\[][ \t]*(?:async[ \t]+)?[\w$]+[ \t]*=>[ \t]*\{"),
    re.compile(r"^[ \t]*(?:(?:public|private|protected|static|async|readonly)[ \t]+)*"
               r"\*?[ \t]*([\w$]+)[ \t]*(?:<[^>\n]{0,80}>)?[ \t]*"
               r"\([^;{}\n]{0,400}\)[ \t]*(?::[^{;\n]{0,120})?[ \t]*\{", re.M),
]
_NOT_FN = {"if", "for", "while", "switch", "catch", "return", "typeof", "function",
           "do", "else", "with", "new", "delete", "await", "yield", "in", "of",
           "constructor", "get", "set", "import", "export", "class", "try", "finally"}

_CONTROL = re.compile(r"\b(?:if|for|while|switch|try|catch|finally|else|do)\b")
# Only the characters and keywords that can change brace state. Letting the regex
# engine find them in C, and looping in Python over just those hits, is far faster
# than stepping through every character of the file.
# `(?<![.\w$])` keeps promise handlers (`p.catch(...)`) from reading as blocks.
_BRACE_TOKENS = re.compile(
    r"(?<![.\w$])\b(?:if|for|while|switch|try|catch|finally|else|do)\b|[{};]")
_NEWLINE = re.compile(r"\n")
_ANY = re.compile(r":\s*any\b")
_CATCH = re.compile(r"\bcatch\b[ \t]*(?:\([^)\n]{0,120}\))?[ \t]*\{")
_JSDOC_BEFORE = re.compile(
    r"/\*\*[\s\S]*?\*/\s*"
    r"(?:(?:export|default|async|public|private|protected|static|readonly|abstract"
    r"|const|let|var)\s+)*$")
_RET_TYPE = re.compile(r"\)\s*:\s*[\w<>\[\]|{ ]+")
_PARAM_TYPE = re.compile(r"[\w$]\s*:\s*[\w<>\[\]|]")


def _scan_braces(code: str) -> tuple[dict, dict]:
    """Single O(n) pass over the blanked source.

    Returns `{open_index: close_index}` and `{open_index: max control-nesting
    depth inside that brace}`. Doing this once replaces a per-function rescan
    that was quadratic in file size.

    Only control-flow blocks add depth -- object and class literals do not, so a
    big config object doesn't read as deeply nested logic.
    """
    match: dict[int, int] = {}
    ctrl_max: dict[int, int] = {}
    stack: list[list] = []          # [open_idx, is_control, max_depth_inside]
    pending = False

    for m in _BRACE_TOKENS.finditer(code):
        tok = m.group(0)
        if tok == "{":
            stack.append([m.start(), pending, 0])
            pending = False
        elif tok == "}":
            if stack:
                open_idx, is_ctrl, inner = stack.pop()
                match[open_idx] = m.start()
                depth = inner + (1 if is_ctrl else 0)
                ctrl_max[open_idx] = depth
                if stack:
                    stack[-1][2] = max(stack[-1][2], depth)
        elif tok == ";":
            pending = False
        else:
            pending = True

    while stack:                     # unbalanced source; close at EOF
        open_idx, is_ctrl, inner = stack.pop()
        match[open_idx] = len(code)
        ctrl_max[open_idx] = inner + (1 if is_ctrl else 0)
    return match, ctrl_max


def analyze_js(src: str, typed_lang: bool) -> dict:
    """`typed_lang` is True for .ts/.tsx -- plain .js cannot carry annotations, so
    it is excluded from the type-coverage denominator rather than scored as zero."""
    a = blank()
    code = _blank_noncode(src)
    a["parsed"] = 1

    brace_match, ctrl_max = _scan_braces(code)
    nl = [m.start() for m in _NEWLINE.finditer(src)]
    line_of = lambda pos: bisect.bisect_right(nl, pos) + 1

    seen: set[int] = set()
    for pi, pat in enumerate(_FN_PATTERNS):
        for m in pat.finditer(code):
            if pi == 3 and m.group(1) in _NOT_FN:
                continue
            brace = code.find("{", max(m.end() - 1, m.start()))
            if brace == -1 or brace in seen or brace not in brace_match:
                continue
            seen.add(brace)

            end = brace_match[brace]
            head = code[m.start():brace]

            a["fns"] += 1
            a["lengths"].append(max(1, line_of(end) - line_of(m.start()) + 1))
            a["depths"].append(ctrl_max.get(brace, 0))

            if typed_lang:
                a["typable"] += 1
                params = head[head.find("("):]
                if (_RET_TYPE.search(head) or _PARAM_TYPE.search(params)) \
                        and not _ANY.search(head):
                    a["typed"] += 1

            before = src[max(0, m.start() - 400):m.start()]
            if _JSDOC_BEFORE.search(before):
                a["documented"] += 1

    a["any_hits"] = len(_ANY.findall(code)) if typed_lang else 0

    for m in _CATCH.finditer(code):
        brace = code.find("{", m.end() - 1)
        if brace == -1 or brace not in brace_match:
            continue
        a["handlers"] += 1
        end = brace_match[brace]
        # Empty catch is the bare-except of JavaScript. So is a catch whose whole
        # body is a console call -- the error is observed and then dropped.
        if not code[brace + 1:end].strip():
            a["imprecise"] += 1
        elif re.fullmatch(r"\s*console\.\w+\([^;]*\);?\s*", src[brace + 1:end] or ""):
            a["imprecise"] += 1
    return a


# ---------------------------------------------------------------------------
# Test quality
# ---------------------------------------------------------------------------

# Markers of a test that exercises a failure path rather than a happy one.
_EDGE = re.compile(
    r"\b(None|null|undefined|empty|blank|nan|void|voided|raises|assertRaises"
    r"|pytest\.raises|toThrow|Error|Exception|invalid|missing|absent|negative"
    r"|zero|boundary|duplicate|conflict|timeout|malformed|stale|never|not_|no_"
    r"|without|fails|failure|wrong|corrupt|unclear|ambiguous)\b", re.I)
_JS_ASSERT = re.compile(r"\b(expect|assert|should|t\.(?:is|deepEqual|throws|truthy))\s*\(")


def analyze_tests_python(src: str) -> dict:
    """How substantive is a test file, judged without running it.

    The tool cannot execute anything, so it cannot measure coverage. What it CAN
    see is whether tests assert, whether they poke at failure paths, and how much
    of the package they touch. Those are proxies -- stated as proxies -- but they
    separate nineteen regression tests from eighty-three empty files, which a
    file-count ratio cannot do at all.
    """
    out = {"test_fns": 0, "assertions": 0, "edge_fns": 0, "modules": set()}
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError):
        return out
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = getattr(node, "module", None) or ""
            for alias in node.names:
                out["modules"].add((mod or alias.name).split(".")[0])
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                node.name.startswith("test"):
            out["test_fns"] += 1
            # The real source of the test, not its AST repr. A dump mangles the
            # words a human wrote, which are exactly the signal here -- a test
            # named `..._is_a_safe_no_op` says what it covers.
            lines = src.splitlines()[node.lineno - 1:(node.end_lineno or node.lineno)]
            body = node.name + "\n" + "\n".join(lines)
            n = sum(1 for x in ast.walk(node) if isinstance(x, ast.Assert))
            n += sum(1 for x in ast.walk(node)
                     if isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute)
                     and x.func.attr.startswith(("assert", "raises", "expect")))
            out["assertions"] += n
            if _EDGE.search(body):
                out["edge_fns"] += 1
    return out


def analyze_tests_js(src: str) -> dict:
    code = _blank_noncode(src)
    fns = len(re.findall(r"\b(?:it|test)\s*\(", code))
    asserts = len(_JS_ASSERT.findall(code))
    edges = len(_EDGE.findall(src))
    mods = set(re.findall(r"(?:from\s+|require\()\s*['\"]([^'\"]+)", code))
    return {"test_fns": fns, "assertions": asserts,
            "edge_fns": min(fns, edges), "modules": {m.split("/")[0] for m in mods}}


def test_quality(acc: dict, source_modules: int) -> dict | None:
    """0..1, or None when there are no tests to judge.

    Three things, none of them a count of files:
      assertion density -- a test that asserts nothing is theatre
      edge coverage     -- tests that exercise failure paths, not just happy ones
      module reach      -- how much of the package the suite actually touches
    """
    fns = acc.get("test_fns", 0)
    if not fns:
        return None
    per_test = acc["assertions"] / fns
    edge = acc["edge_fns"] / fns
    reach = (len(acc["modules"]) / source_modules) if source_modules else 0.0

    def band(v, lo, hi):
        return max(0.0, min(1.0, (v - lo) / (hi - lo))) if hi > lo else 0.0

    score = (0.45 * band(per_test, 0, 3.0)
             + 0.35 * band(edge, 0, 0.5)
             + 0.20 * band(reach, 0, 0.4))
    return {"test_functions": fns,
            "assertions_per_test": round(per_test, 2),
            "edge_case_ratio": round(edge, 2),
            "module_reach": round(reach, 3),
            "quality": round(score, 3)}


def summarize(a: dict) -> dict:
    """Accumulator -> the metrics the scorer consumes. Unmeasurable things are
    None, never zero -- a missing measurement and a bad one are different."""
    import statistics

    def q(xs, p):
        if not xs:
            return 0
        if len(xs) < 10:
            return max(xs)
        return int(statistics.quantiles(xs, n=10)[p])

    fns = a["fns"]
    return {
        "parsed_files": a["parsed"],
        "functions": fns,
        "fn_len_p50": int(statistics.median(a["lengths"])) if a["lengths"] else 0,
        "fn_len_p90": q(a["lengths"], 8),
        "nesting_p90": q(a["depths"], 8),
        "type_coverage": (round(a["typed"] / a["typable"], 3)
                          if a["typable"] else None),
        "typable_functions": a["typable"],
        "docstring_coverage": round(a["documented"] / fns, 3) if fns else 0.0,
        "except_handlers": a["handlers"],
        "except_precision": (round(1 - a["imprecise"] / a["handlers"], 3)
                             if a["handlers"] else None),
        "imprecise_handlers": a["imprecise"],
        "any_annotations": a["any_hits"],
    }
