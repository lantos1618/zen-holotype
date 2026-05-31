"""Zen-source-driven type-checker tests.

Each tests/cases/*.zen is a fixture run through the REAL pipeline
(parse -> trie -> resolve -> check). Functions carry an inline verdict:

    foo = (...) i32 { ... }      //~ PASS
    bad = (...) i32 { ... }      //~ FAIL <substring of the expected message>
    multi = () i32 { ... }       //~ multi PASS      (explicit name; use on any line)

This is the project's own type system checking itself — the front end and the
checker, not hand-built AST. The unit tests (test_fits/test_infer) still cover
the lattice internals directly; these cover end-to-end behaviour in Zen.
"""
import functools
import pathlib
import re

import pytest

from holotype.parser import parse
from holotype.main import build_space, build_scopes, resolve, check

CASES_DIR = pathlib.Path(__file__).parent / "cases"
_ANNOT = re.compile(r"//~\s*(.+?)\s*$")


def annotations(src):
    """name -> (expected_pass: bool, reason_substring: str)."""
    out = {}
    for line in src.splitlines():
        m = _ANNOT.search(line)
        if not m:
            continue
        head, *rest = m.group(1).split(None, 1)
        rest = rest[0] if rest else ""
        if head in ("PASS", "FAIL"):
            verdict, reason = head, rest                 # implicit: name from this decl line
            name = line.split("//~")[0].split("=")[0].strip().split()[-1]
        else:
            name = head                                  # explicit: //~ name PASS/FAIL
            verdict, _, reason = rest.partition(" ")
        out[name] = (verdict == "PASS", reason.strip())
    return out


@functools.lru_cache(maxsize=None)
def _check_fixture(path):
    src = path.read_text()
    files = {"t": parse(src, "t")}
    space = build_space(files)
    build_scopes(files)
    resolve(files, space)
    results, _ = check(files, space)
    verdicts = {qual.split(".", 1)[1]: (ok, why) for qual, ok, why in results}
    return verdicts, annotations(src)


def _params():
    out = []
    for path in sorted(CASES_DIR.glob("*.zen")):
        for name, (ok, reason) in annotations(path.read_text()).items():
            out.append(pytest.param(path, name, ok, reason,
                                    id=f"{path.stem}::{name}"))
    return out


def test_fixtures_exist():
    assert _params(), "no annotated cases found under tests/cases/"


@pytest.mark.parametrize("path,fn,expect_pass,reason", _params())
def test_case(path, fn, expect_pass, reason):
    verdicts, _ = _check_fixture(path)
    assert fn in verdicts, f"'{fn}' not type-checked (typo in annotation?)"
    got_pass, why = verdicts[fn]
    assert got_pass == expect_pass, \
        f"{fn}: expected {'PASS' if expect_pass else 'FAIL'}, got {why!r}"
    if not expect_pass and reason:
        assert reason in why, f"{fn}: expected reason ~{reason!r}, got {why!r}"
