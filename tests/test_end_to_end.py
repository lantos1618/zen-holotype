"""T9-T11 + F1: the whole pipeline on the real `examples/` tree.

T9  expected PASS/FAIL set from the checker
T10 codegen is const-correct and excludes ill-typed fns
T11 `holotype build` actually compiles, links, and runs -> "vecdemo -> 12"
F1  un-lowerable declarations fail loudly instead of vanishing
"""
import subprocess
import sys

import pytest

import re
from dataclasses import dataclass

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


def test_type_errors_carry_a_source_location(checked):
    _, _, results, _ = checked
    why = {qual: reason for qual, ok, reason in results if not ok}
    # main.bad / main.dirbad fail in main.zen — message is prefixed main:line:col
    assert re.match(r"main:\d+:\d+: ", why["main.bad"]), why["main.bad"]
    assert re.match(r"main:\d+:\d+: ", why["main.dirbad"]), why["main.dirbad"]


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


# ── Phase A: generics monomorphize to concrete C that compiles and runs ─────
def test_generic_fn_monomorphizes(tmp_path):
    (tmp_path / "main.zen").write_text(
        "pub Vec: { len: i32, cap: i32 }\n"
        "pub id<T> = (x: Ptr<T>) Ptr<T> { x }\n"
        "pub area = (v: Ptr<Vec>) i32 { id(v).len * id(v).cap }\n"
        "pub main = () i32 { area(addr(Vec { len: 5, cap: 4 })) }\n")
    files = load(tmp_path)
    space = build_space(files)
    build_scopes(files)
    resolve(files, space)
    _, passing = check(files, space)
    c = emit_c(files, passing, space)
    # one specialized instance named for its type-arg; the template itself is gone
    assert "main_Vec const * main_id_main_Vec(main_Vec const * x)" in c
    assert "main_id_main_Vec(v)" in c
    assert "_T(" not in c                     # no un-monomorphized template emitted
    cfile = tmp_path / "o.c"
    cfile.write_text(c)
    r = subprocess.run(["cc", "-Wall", "-Wextra", "-c", str(cfile),
                        "-o", str(tmp_path / "o.o")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ── Phase B: match compiles to a tag-switch and runs ────────────────────────
def test_match_lowers_and_runs(tmp_path):
    (tmp_path / "main.zen").write_text(
        "pub Status: Idle, Busy(i32)\n"
        "pub code = (s: Status) i32 { match s { .Idle => 0, .Busy(n) => n } }\n"
        "pub main = () i32 { code(.Busy(7)) }\n")
    files = load(tmp_path)
    space = build_space(files)
    build_scopes(files)
    resolve(files, space)
    _, passing = check(files, space)
    c = emit_c(files, passing, space)
    assert ".tag == main_Status_Idle" in c             # tag test (subject bound to a temp)
    assert "int32_t n = " in c and ".u.Busy" in c      # payload binding
    harness = ("\n#include <stdio.h>\nint main(void){ "
               "printf(\"%d\\n\", main_main()); return 0; }\n")
    cfile = tmp_path / "o.c"
    cfile.write_text(c + harness)
    bexe = tmp_path / "o"
    r = subprocess.run(["cc", "-Wall", "-Wextra", str(cfile), "-o", str(bexe)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    run = subprocess.run([str(bexe)], capture_output=True, text=True)
    assert run.stdout.strip() == "7"


# ── A used but ill-typed trait impl is refused loudly (not silently emitted) ─
def test_used_illtyped_impl_refused(tmp_path):
    (tmp_path / "main.zen").write_text(
        "pub Box<T>: { val: T }\n"
        "trait Score { score: (Ptr<Self>) i32 }\n"
        "impl Score for Box { score = (b: Ptr<Box>) i32 { b.val } }\n"   # b.val : T ⊀ i32
        "pub total<T: Score> = (x: Ptr<T>) i32 { score(x) }\n"
        "pub main = () i32 { total(addr(Box { val: 9 })) }\n")
    files = load(tmp_path)
    space = build_space(files)
    build_scopes(files)
    resolve(files, space)
    _, passing = check(files, space)
    with pytest.raises(NotImplementedError) as ei:
        emit_c(files, passing, space)
    assert "did not type-check" in str(ei.value) and "score" in str(ei.value)


def test_unused_illtyped_impl_still_builds(tmp_path):
    # the same bad impl, but never used — the rest of the program still compiles
    (tmp_path / "main.zen").write_text(
        "pub Box<T>: { val: T }\n"
        "trait Score { score: (Ptr<Self>) i32 }\n"
        "impl Score for Box { score = (b: Ptr<Box>) i32 { b.val } }\n"
        "pub main = () i32 { 42 }\n")
    files = load(tmp_path)
    space = build_space(files)
    build_scopes(files)
    resolve(files, space)
    _, passing = check(files, space)
    assert "main_main(void) { return 42; }" in emit_c(files, passing, space)


# ── Traits: a bounded generic dispatches to the impl, compiles, and runs ────
def test_trait_dispatch_runs(tmp_path):
    (tmp_path / "main.zen").write_text(
        "pub Vec: { len: i32, cap: i32 }\n"
        "trait Area { area: (Ptr<Self>) i32 }\n"
        "impl Area for Vec { area = (v: Ptr<Vec>) i32 { v.len * v.cap } }\n"
        "pub total<T: Area> = (x: Ptr<T>) i32 { area(x) }\n"
        "pub main = () i32 { total(addr(Vec { len: 5, cap: 4 })) }\n")
    files = load(tmp_path)
    space = build_space(files)
    build_scopes(files)
    resolve(files, space)
    _, passing = check(files, space)
    c = emit_c(files, passing, space)
    # the bounded generic and the impl both monomorphize, and total calls the impl
    assert "main_total_main_Vec" in c
    assert "impl_main_Area_main_Vec_area" in c
    assert "return impl_main_Area_main_Vec_area(x)" in c
    harness = ("\n#include <stdio.h>\nint main(void){ "
               "printf(\"%d\\n\", main_main()); return 0; }\n")
    cfile = tmp_path / "o.c"
    cfile.write_text(c + harness)
    bexe = tmp_path / "o"
    r = subprocess.run(["cc", "-Wall", "-Wextra", str(cfile), "-o", str(bexe)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert subprocess.run([str(bexe)], capture_output=True, text=True).stdout.strip() == "20"


# ── Turing-complete: integer branching + recursion compiles and computes ────
def test_recursion_computes(tmp_path):
    (tmp_path / "main.zen").write_text(
        "pub fact = (n: i32) i32 { match n { 0 => 1, _ => n * fact(n - 1) } }\n"
        "pub fib = (n: i32) i32 { match n { 0 => 0, 1 => 1, _ => fib(n-1) + fib(n-2) } }\n"
        "pub main = () i32 { fact(5) + fib(10) }\n")   # 120 + 55 = 175
    files = load(tmp_path)
    space = build_space(files)
    build_scopes(files)
    resolve(files, space)
    _, passing = check(files, space)
    c = emit_c(files, passing, space)
    assert "== 0 ?" in c                                # literal-pattern branch
    assert "main_fact((n - 1))" in c                    # the recursive call
    assert c.count("main_fact((n - 1))") == 1           # subject/arms evaluated once
    harness = ("\n#include <stdio.h>\nint main(void){ "
               "printf(\"%d\\n\", main_main()); return 0; }\n")
    cfile = tmp_path / "o.c"
    cfile.write_text(c + harness)
    bexe = tmp_path / "o"
    r = subprocess.run(["cc", "-Wall", "-Wextra", str(cfile), "-o", str(bexe)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert subprocess.run([str(bexe)], capture_output=True, text=True).stdout.strip() == "175"


# ── Generic data types: a generic struct monomorphizes and runs ─────────────
def test_generic_struct_monomorphizes(tmp_path):
    (tmp_path / "main.zen").write_text(
        "pub Box<T>: { val: T }\n"
        "pub unwrap<T> = (b: Ptr<Box<T>>) T { b.val }\n"
        "pub main = () i32 { unwrap(addr(Box { val: 42 })) }\n")
    files = load(tmp_path)
    space = build_space(files)
    build_scopes(files)
    resolve(files, space)
    _, passing = check(files, space)
    c = emit_c(files, passing, space)
    assert "typedef struct { int32_t val; } main_Box_i32;" in c   # the instance struct
    assert "_T " not in c                                          # template not emitted raw
    harness = ("\n#include <stdio.h>\nint main(void){ "
               "printf(\"%d\\n\", main_main()); return 0; }\n")
    cfile = tmp_path / "o.c"
    cfile.write_text(c + harness)
    bexe = tmp_path / "o"
    r = subprocess.run(["cc", "-Wall", "-Wextra", str(cfile), "-o", str(bexe)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert subprocess.run([str(bexe)], capture_output=True, text=True).stdout.strip() == "42"


# ── A match subject with side effects is evaluated exactly once ─────────────
def test_match_subject_evaluated_once(tmp_path):
    (tmp_path / "main.zen").write_text(
        "pub Vec: { len: i32, cap: i32 }\n"
        "pub kind = (v: Ptr<Vec>) i32 { v.len }\n"
        "pub pick = (v: Ptr<Vec>) i32 { match (kind(v)) { 0 => 10, 1 => 20, _ => 30 } }\n")
    files = load(tmp_path)
    space = build_space(files)
    build_scopes(files)
    resolve(files, space)
    _, passing = check(files, space)
    pick = [ln for ln in emit_c(files, passing, space).splitlines()
            if "main_pick" in ln and "return" in ln][0]
    assert pick.count("main_kind") == 1, pick      # not re-evaluated per arm


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
