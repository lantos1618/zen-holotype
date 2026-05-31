"""T9-T11 + F1: the whole pipeline on the real `examples/` tree.

T9  expected PASS/FAIL set from the checker
T10 codegen is const-correct and excludes ill-typed fns
T11 `holotype build` actually compiles, links, and runs -> "vecdemo -> 12"
F1  un-lowerable declarations fail loudly instead of vanishing
"""
import subprocess
import sys

import pytest

from dataclasses import dataclass

from holotype.ast import Dir, Prim, PrimT, NameT, PtrT, Fn, Param, EnumDecl
from holotype.main import (load, build_space, build_scopes, resolve, check,
                           emit_c, run_test_root)
from conftest import EXAMPLES


@pytest.fixture
def checked():
    files = load(EXAMPLES, skip={"test.zen"})    # library modules only (as the exe build does)
    space = build_space(files)
    build_scopes(files)
    resolve(files, space)
    results, passing = check(files, space)
    return files, space, results, passing


# ── T9: the checker verdict on the example tree ─────────────────────────────
def test_expected_pass_fail_set(checked):
    _, _, results, passing = checked
    verdict = {qual: ok for qual, ok, _ in results}
    assert verdict == {
        "main.area": True,
        "main.main": True,
        "main.bad": False,      # nullable into nonnull
        "main.dirbad": False,   # read-only into mut-required
        "ops.len": True,
        "ops.cap": True,
        "ops.bump": True,
    }
    assert "main.bad" not in passing and "main.dirbad" not in passing


def test_failure_reasons_name_the_lattice_violation(checked):
    _, _, results, _ = checked
    why = {qual: reason for qual, ok, reason in results if not ok}
    assert "Option<Ptr<Vec>>" in why["main.bad"] and "⊀" in why["main.bad"]
    assert "MutPtr<Vec>" in why["main.dirbad"]


# ── T10: codegen golden properties ──────────────────────────────────────────
def test_codegen_is_const_correct(checked):
    files, space, _, passing = checked
    c = emit_c(files, passing, space)
    # Ptr<Vec> -> const *, MutPtr<Vec> -> plain *
    assert "ops_len(core_vec_Vec const * v)" in c
    assert "ops_bump(core_vec_Vec * v)" in c
    assert "typedef struct { int32_t len; int32_t cap; } core_vec_Vec;" in c


def test_codegen_excludes_failing_functions(checked):
    files, space, _, passing = checked
    c = emit_c(files, passing, space)
    assert "main_area" in c and "main_main" in c
    assert "main_bad" not in c and "main_dirbad" not in c


# ── F1: integrity — un-lowerable decls raise instead of silently dropping ───
@dataclass
class _UnknownDecl:           # a decl kind codegen has never heard of
    name: str


def test_unlowerable_decl_raises(checked):
    files, space, _, passing = checked
    # codegen lowers struct/enum/fn; anything else must refuse loudly, not vanish
    some_file = next(iter(files.values()))
    some_file.decls.append(_UnknownDecl("mystery"))
    with pytest.raises(NotImplementedError) as ei:
        emit_c(files, passing, space)
    assert "_UnknownDecl" in str(ei.value) and "mystery" in str(ei.value)


# ── F3: user enums lower to a tagged union that cc accepts ──────────────────
def test_enum_lowers_to_tagged_union(tmp_path):
    (tmp_path / "main.zen").write_text(
        "pub Status: Idle, Busy(i32)\n"
        "pub idle = () Status { .Idle() }\n"
        "pub busy = (n: i32) Status { .Busy(n) }\n")
    files = load(tmp_path)
    space = build_space(files)
    build_scopes(files)
    resolve(files, space)
    _, passing = check(files, space)
    c = emit_c(files, passing, space)
    assert "int32_t tag;" in c and "union { int32_t Busy; } u;" in c
    assert "enum { main_Status_Idle, main_Status_Busy };" in c
    assert ".tag = main_Status_Busy, .u.Busy = n" in c
    # the emitted C must actually compile
    cfile = tmp_path / "o.c"
    cfile.write_text(c)
    r = subprocess.run(["cc", "-Wall", "-Wextra", "-c", str(cfile),
                        "-o", str(tmp_path / "o.o")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ── T11: the build really runs ──────────────────────────────────────────────
def test_full_build_runs_and_prints_12():
    out = subprocess.run(
        [sys.executable, "-m", "holotype", "build", str(EXAMPLES)],
        capture_output=True, text=True, cwd=str(EXAMPLES.parent))
    assert out.returncode == 0, out.stderr
    assert "vecdemo -> 12" in out.stdout
    # the declared Test root is compiled and run, reporting per-test verdicts
    assert "tests: test.zen" in out.stdout
    assert "PASS ✓  test.test_len" in out.stdout


# ── F5: the test runner reports pass / fail / skip ──────────────────────────
def test_test_runner_reports_pass_fail_skip(tmp_path, capsys):
    (tmp_path / "lib.zen").write_text("pub three = () i32 { 3 }\n")
    (tmp_path / "t.zen").write_text(
        "{ three } = lib\n"
        "pub t_pass = () bool { three() == 3 }\n"   # true  -> PASS
        "pub t_fail = () bool { three() == 9 }\n"   # false -> FAIL
        "pub t_bad  = () bool { three() == true }\n")  # type error -> SKIP
    run_test_root(tmp_path, "t.zen")
    out = capsys.readouterr().out
    assert "PASS ✓  t.t_pass" in out
    assert "FAIL ✗  t.t_fail" in out
    assert "SKIP    t.t_bad" in out
