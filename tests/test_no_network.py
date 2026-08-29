"""The trust guarantee, enforced by CI rather than asserted in a docstring.

Aura's entire value proposition is that the scanner cannot exfiltrate your code.
A README promising that is worth nothing -- promises don't fail a build. These
tests parse every module in the package and fail if the property is ever broken,
so a pull request that adds `import requests` cannot merge.

The invariant, stated exactly:

  1. No module in `aurarank/` imports a network-capable library.
  2. `subprocess` IS used -- solely to invoke `git`, which reads local history.
     Every subprocess call must have the literal "git" as its executable.
  3. Nothing calls eval() or exec().

Point 2 is why this file exists at all. The honest claim is not "no subprocess";
it is "subprocess, and only ever to run git." A grep cannot tell those apart.
`tools/` is deliberately NOT covered: the calibration harness clones public
repositories and is expected to use the network. That separation is the design.
"""

import ast
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

PKG = pathlib.Path(__file__).resolve().parents[1] / "aurarank"

NETWORK_MODULES = {
    "socket", "ssl", "http", "httplib", "urllib", "urllib2", "urllib3",
    "requests", "aiohttp", "httpx", "ftplib", "smtplib", "poplib", "imaplib",
    "telnetlib", "xmlrpc", "websockets", "websocket", "paramiko", "boto3",
    "botocore", "grpc", "pycurl",
}


def modules():
    for path in sorted(PKG.glob("*.py")):
        yield path, ast.parse(path.read_text())


def _root(name: str) -> str:
    return (name or "").split(".", 1)[0]


def test_no_network_imports_anywhere_in_the_package():
    bad = []
    for path, tree in modules():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if _root(a.name) in NETWORK_MODULES:
                        bad.append(f"{path.name}:{node.lineno} import {a.name}")
            elif isinstance(node, ast.ImportFrom):
                if _root(node.module or "") in NETWORK_MODULES:
                    bad.append(f"{path.name}:{node.lineno} from {node.module}")
    assert not bad, "network imports found in aurarank/: " + "; ".join(bad)


def test_subprocess_is_only_ever_used_to_run_git():
    """The honest version of the guarantee.

    subprocess is legitimate here -- reading git history is the whole job. What
    would break the promise is subprocess invoking something ELSE, so that is
    what gets checked: every call's argv[0] must be the literal "git".
    """
    offenders = []
    for path, tree in modules():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            is_sub = (isinstance(fn, ast.Attribute)
                      and isinstance(fn.value, ast.Name)
                      and fn.value.id == "subprocess")
            if not is_sub:
                continue
            if not node.args:
                offenders.append(f"{path.name}:{node.lineno} subprocess with no argv")
                continue
            argv = node.args[0]
            first = argv.elts[0] if isinstance(argv, (ast.List, ast.Tuple)) and argv.elts else argv
            if not (isinstance(first, ast.Constant) and first.value == "git"):
                offenders.append(
                    f"{path.name}:{node.lineno} subprocess argv[0] is not the literal 'git'")
    assert not offenders, "; ".join(offenders)


def test_shell_true_is_never_used():
    """shell=True would let a crafted path become a command."""
    bad = []
    for path, tree in modules():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg == "shell" and getattr(kw.value, "value", False) is True:
                        bad.append(f"{path.name}:{node.lineno}")
    assert not bad, "shell=True found: " + "; ".join(bad)


def test_no_eval_or_exec():
    bad = []
    for path, tree in modules():
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id in {"eval", "exec", "compile"}):
                bad.append(f"{path.name}:{node.lineno} {node.func.id}()")
    assert not bad, "dynamic execution found: " + "; ".join(bad)


def test_the_documented_verification_command_is_honest():
    """The README tells people to run a grep. It must not produce a surprise.

    An earlier docstring told readers to grep for `subprocess` and claimed only
    comments would match -- while scan.py genuinely uses it. Anyone who ran the
    documented command saw real hits and would reasonably conclude the project
    was lying about the one thing it asks to be trusted on. The docs now say
    subprocess is used for git; this test keeps the two in step.
    """
    readme = (PKG.parent / "README.md").read_text()
    assert "subprocess" in readme, (
        "README must disclose that subprocess is used, and why -- otherwise the "
        "verification command it recommends contradicts the source")


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS  {name}")
            except AssertionError as e:
                failures += 1
                print(f"  FAIL  {name}: {e}")
    print(f"\n{'all passed' if not failures else str(failures) + ' FAILED'}")
    sys.exit(1 if failures else 0)
