"""S1 CROSS-MODULE TYPE-CHECK oracle — the #1 coverage hole from deleting the Python frontend.

Deleting zen/*.py lost the proof that the STDLIB type-checks as an inter-module WHOLE. The flat
CHECK binary (tests/test_oracle.py) treats every `{…} = std.x` import as a known-but-unchecked
name (the DImport fallback), so it never verifies an imported call's arity or arg types — it gates
parse+resolve+local-typing only. This module restores the lost dimension (the old test_acid CHECK
pass over multi-module code + test_modules check_linked + test_imports) entirely with the BINARY.

HOW (route (a) — wire check_validate.check_linked, no new compiler code): for each std module we
gather the EXPORTED signatures of every std.x it imports (parse those modules; module_header reduces
each `name* = (params) ret { … }` to a bodyless DForeign), layer that header on, and run
check_module. An imported call now resolves to its REAL signature in `the_func`, so check_call ->
call_errs verifies arity AND arg types exactly like a local call. The import discovery is the same
`{ ` + `= std.` classification std.internal.resolve makes. Driven by tests/_oracle.check_linked_count, which
builds a CHECK_LINKED binary from the committed `zenc` binary + cc — NO Python compiler in the loop.

POSITIVE: every real std/*.zen, checked WITH its imports, must report 0 errors (the stdlib IS a
well-typed whole — the recovered coverage). NEGATIVE: an import called with the WRONG arity / arg
type IS rejected, and the SAME bad call with the header ABSENT is accepted — proving the header is
load-bearing and the net is not hollow.
"""
from pathlib import Path

import pytest

import _oracle

ROOT = Path(__file__).resolve().parent.parent
STD = ROOT / "zen" / "std"

# Every real std module. Each is type-checked against the REAL signatures of the modules it imports.
ALL_MODULES = sorted(p.relative_to(STD).as_posix() for p in STD.rglob("*.zen"))


@pytest.mark.parametrize("module", ALL_MODULES)
def test_module_typechecks_against_its_imports(module):
    # The whole point: an imported call is now arity/arg-type-checked against the importee's real
    # signature (layered via check_linked's module_header), not waved through as "imported". 0 errors
    # == this module composes with its imports as a well-typed inter-module unit.
    path = "zen/std/" + module
    # A call to a cross-module GENERIC (e.g. std.concurrent.cown calling std.mem.own's `own<T>` and receiver methods) is now
    # handled: check_validate.call_errs skips the strict arg-TYPE check for an imported generic (its
    # param types still carry the unbound tparam `T`, uninferable at the call site), mirroring how a
    # LOCAL generic call is monomorphized away before this pass. Arity is still enforced.
    n = _oracle.check_linked_count(path)
    assert n == 0, f"{module}: {n} cross-module type error(s) against imports {_oracle.imports_of(path)}"


def test_bootstrap_sources_typecheck_as_a_whole():
    # The bootstrap manifest-listed sources must type-check cross-module — this is the
    # acid-CHECK dimension over the real multi-module compiler that deleting Python removed.
    for rel in _oracle._CHECK_SOURCES:
        n = _oracle.check_linked_count(rel)
        assert n == 0, f"bootstrap source {rel}: {n} cross-module error(s)"


# ── the NET IS NOT HOLLOW: a wrong cross-module call must be REJECTED ────────────────────────────
# The header exports `f(a: i32, b: i32) i32`; the target imports it from std.x and calls it wrong.
_LIB = "f* = (a: i32, b: i32) i32 { a + b }\n"


def test_wrong_arg_type_against_import_is_rejected():
    # f expects (i32, i32); a str arg can't fit an i32 param -> rejected. (A str is non-numeric, so
    # the numeric-literal escape hatch does not apply.)
    bad = '{ f } = std.x\nbad* = () i32 { f("hi", "there") }\n'
    assert _oracle.check_linked_count_src(bad, _LIB) > 0


def test_correct_call_against_import_is_accepted():
    good = "{ f } = std.x\ngood* = () i32 { f(1, 2) }\n"
    assert _oracle.check_linked_count_src(good, _LIB) == 0


def test_header_is_load_bearing():
    # The CONTROL that makes the net real: the SAME wrong-arity call, but with NO lib header, is
    # accepted (the old flat-module behaviour — every imported name known-but-unchecked). So the
    # rejections above come from the layered signature, not from some unrelated local check.
    bad = "{ f } = std.x\nbad* = () i32 { f(1, 2, 3) }\n"
    assert _oracle.check_linked_count_src(bad, "") == 0
    assert _oracle.check_linked_count_src(bad, _LIB) > 0


def _emit_project(main_src, helper_src):
    # Drive the committed EMIT binary's `emit <file>` subcommand (full import resolution) on a 2-file
    # project; return the emitted C. NO Python compiler in the loop.
    import subprocess, tempfile
    d = Path(tempfile.mkdtemp())
    (d / "helper.zen").write_text(helper_src)
    (d / "main.zen").write_text(main_src)
    return subprocess.run([str(_oracle._build_emit()), "emit", str(d / "main.zen")],
                          capture_output=True, text=True, timeout=30).stdout


_HELPER = "addh* = (a: i32, b: i32) i32 { a + b }\n"


def test_import_no_space_after_brace_resolves():
    # IMPORT-SPACE regression: `{addh}` (no space after `{`) must resolve the sibling import exactly
    # like `{ addh }` — std.internal.resolve.opens_import / driver.bs_is_import used to require a
    # space, so the binding was silently dropped (the importee was never pulled in -> link error).
    for opener in ("{addh}", "{ addh }", "{addh }", "{ addh}"):
        c = _emit_project(opener + " = helper\ntest* = () i32 { addh(3, 4) }\n", _HELPER)
        assert "return addh(3, 4)" in c and "int32_t addh(" in c, (opener, c)


def test_modules_oracle_has_no_python_frontend_dependency():
    # Same guarantee test_oracle makes: this whole net runs on the BINARY (cc + the committed zenc),
    # never on a Python reference frontend. There is no zen.* import anywhere in the loop.
    import sys
    assert "zen.main" not in sys.modules
    assert not any(m == "zen" or m.startswith("zen.") for m in sys.modules)
