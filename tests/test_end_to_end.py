"""T9-T10 + F1: the whole pipeline on the real `examples/` tree — checker verdicts and
codegen that compiles + runs. (The `zen build` / CLI driver tests live in test_cli.py.)

T9  expected PASS/FAIL set from the checker
T10 codegen is const-correct and excludes ill-typed fns
F1  un-lowerable declarations fail loudly instead of vanishing
"""
import re
import subprocess
from dataclasses import dataclass

import pytest

from zen.main import (load, build_namespace, build_scopes, resolve, check, emit_c)
from conftest import EXAMPLES


@pytest.fixture
def checked():
    files = load(EXAMPLES, skip={"test.zen"})    # library modules only (as the exe build does)
    namespace = build_namespace(files)
    build_scopes(files)
    resolve(files, namespace)
    results, passing = check(files, namespace)
    return files, namespace, results, passing


# ── T9: the checker verdict on the example tree ─────────────────────────────
def test_expected_pass_fail_set(checked):
    _, _, results, passing = checked
    # the bundled stdlib (std.*) is checked too — incl. std trait impls, whose verdict
    # keys read "Trait for Type::m"; this test is about the example, which has neither
    verdict = {qual: ok for qual, ok, _ in results
               if not qual.startswith("std.") and " for " not in qual}
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
    files, namespace, _, passing = checked
    c = emit_c(files, passing, namespace)
    # Ptr<Vec> -> const *, MutPtr<Vec> -> plain *
    assert "ops_len(core_vec_Vec const * v)" in c
    assert "ops_bump(core_vec_Vec * v)" in c
    assert "struct core_vec_Vec { int32_t len; int32_t cap; };" in c


def test_codegen_excludes_failing_functions(checked):
    files, namespace, _, passing = checked
    c = emit_c(files, passing, namespace)
    assert "main_area" in c and "main_main" in c
    assert "main_bad" not in c and "main_dirbad" not in c


# ── F1: integrity — un-lowerable decls raise instead of silently dropping ───
@dataclass
class _UnknownDecl:           # a decl kind codegen has never heard of
    name: str


def test_unlowerable_decl_raises(checked):
    files, namespace, _, passing = checked
    # codegen lowers struct/enum/fn; anything else must refuse loudly, not vanish
    # (skip the bundled prelude — it's comptime-only and never lowered)
    some_file = next(f for ns, f in files.items() if not ns.startswith("prelude"))
    some_file.decls.append(_UnknownDecl("mystery"))
    with pytest.raises(NotImplementedError) as ei:
        emit_c(files, passing, namespace)
    assert "_UnknownDecl" in str(ei.value) and "mystery" in str(ei.value)


def test_empty_body_fn_is_checked_and_emitted(compile_main):
    # an EMPTY body `[]` is NOT a foreign binding (`body is None`): it must type-check,
    # enter `passing`, and be emitted — with no bogus `return 0;` in a void function (which
    # -Werror rejects). `not d.body` used to drop it -> undefined symbol -> link error.
    assert compile_main("noop = () void { }\nmain* = () i32 { noop()\n 7 }") == 7


# ── F3: user enums lower to a tagged union that cc accepts ──────────────────
def test_enum_lowers_to_tagged_union(tmp_path):
    (tmp_path / "main.zen").write_text(
        "Status*: Idle | Busy(i32)\n"
        "idle* = () Status { .Idle() }\n"
        "busy* = (n: i32) Status { .Busy(n) }\n")
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files)
    resolve(files, namespace)
    _, passing = check(files, namespace)
    c = emit_c(files, passing, namespace)
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
        "Vec*: { len: i32, cap: i32 }\n"
        "id*<T> = (x: Ptr<T>) Ptr<T> { x }\n"
        "area* = (v: Ptr<Vec>) i32 { id(v).len * id(v).cap }\n"
        "main* = () i32 { area(addr(Vec { len: 5, cap: 4 })) }\n")
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files)
    resolve(files, namespace)
    _, passing = check(files, namespace)
    c = emit_c(files, passing, namespace)
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
        "Status*: Idle | Busy(i32)\n"
        "code* = (s: Status) i32 { s.match ({ .Idle => 0, .Busy(n) => n }) }\n"
        "main* = () i32 { code(.Busy(7)) }\n")
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files)
    resolve(files, namespace)
    _, passing = check(files, namespace)
    c = emit_c(files, passing, namespace)
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


# ── match's optional paren form: `subj.match ({ … })` — the arms wrapped in parens ──
# The parens are pure punctuation (stripped in the grammar), so the paren form lowers and
# runs identically to the brace form. Covers both the bool subject and the enum subject.
def test_match_paren_form_lowers_and_runs(tmp_path):
    (tmp_path / "main.zen").write_text(
        "Status*: Idle | Busy(i32)\n"
        "code* = (s: Status) i32 { s.match({ .Idle => 0, .Busy(n) => n }) }\n"
        "sign* = (n: i32) i32 { (n < 0).match({ true => 0, false => 1 }) }\n"
        "main* = () i32 { code(.Busy(7)) + sign(5) }\n")
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files)
    resolve(files, namespace)
    _, passing = check(files, namespace)
    c = emit_c(files, passing, namespace)
    assert ".tag == main_Status_Idle" in c             # variant match still lowers
    assert "int32_t n = " in c and ".u.Busy" in c      # payload binding intact
    assert "? (0) : (1)" in c                           # bool match -> ternary
    harness = ("\n#include <stdio.h>\nint main(void){ "
               "printf(\"%d\\n\", main_main()); return 0; }\n")
    cfile = tmp_path / "o.c"
    cfile.write_text(c + harness)
    bexe = tmp_path / "o"
    r = subprocess.run(["cc", "-Wall", "-Wextra", str(cfile), "-o", str(bexe)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    run = subprocess.run([str(bexe)], capture_output=True, text=True)
    assert run.stdout.strip() == "8"                   # code(.Busy(7))=7 + sign(5)=1


# ── A used but ill-typed trait impl is refused loudly (not silently emitted) ─
def test_used_illtyped_impl_refused(tmp_path):
    (tmp_path / "main.zen").write_text(
        "Box*<T>: { val: T }\n"
        "Score: { score: (Ptr<Self>) i32 }\n"
        "Box.impl(Score, { score = (b: Ptr<Box>) i32 { b.val } })\n"   # b.val : T ⊀ i32
        "total*<T: Score> = (x: Ptr<T>) i32 { score(x) }\n"
        "main* = () i32 { total(addr(Box { val: 9 })) }\n")
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files)
    resolve(files, namespace)
    _, passing = check(files, namespace)
    with pytest.raises(NotImplementedError) as ei:
        emit_c(files, passing, namespace)
    assert "did not type-check" in str(ei.value) and "score" in str(ei.value)


def test_unused_illtyped_impl_still_builds(tmp_path):
    # the same bad impl, but never used — the rest of the program still compiles
    (tmp_path / "main.zen").write_text(
        "Box*<T>: { val: T }\n"
        "Score: { score: (Ptr<Self>) i32 }\n"
        "Box.impl(Score, { score = (b: Ptr<Box>) i32 { b.val } })\n"
        "main* = () i32 { 42 }\n")
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files)
    resolve(files, namespace)
    _, passing = check(files, namespace)
    assert "main_main(void) { return 42; }" in emit_c(files, passing, namespace)


# ── Traits: a bounded generic dispatches to the impl, compiles, and runs ────
def test_trait_dispatch_runs(tmp_path):
    (tmp_path / "main.zen").write_text(
        "Vec*: { len: i32, cap: i32 }\n"
        "Area: { area: (Ptr<Self>) i32 }\n"
        "Vec.impl(Area, { area = (v: Ptr<Vec>) i32 { v.len * v.cap } })\n"
        "total*<T: Area> = (x: Ptr<T>) i32 { area(x) }\n"
        "main* = () i32 { total(addr(Vec { len: 5, cap: 4 })) }\n")
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files)
    resolve(files, namespace)
    _, passing = check(files, namespace)
    c = emit_c(files, passing, namespace)
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
        "fact* = (n: i32) i32 { n.match ({ 0 => 1, _ => n * fact(n - 1) }) }\n"
        "fib* = (n: i32) i32 { n.match ({ 0 => 0, 1 => 1, _ => fib(n-1) + fib(n-2) }) }\n"
        "main* = () i32 { fact(5) + fib(10) }\n")   # 120 + 55 = 175
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files)
    resolve(files, namespace)
    _, passing = check(files, namespace)
    c = emit_c(files, passing, namespace)
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
        "Box*<T>: { val: T }\n"
        "unwrap*<T> = (b: Ptr<Box<T>>) T { b.val }\n"
        "main* = () i32 { unwrap(addr(Box { val: 42 })) }\n")
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files)
    resolve(files, namespace)
    _, passing = check(files, namespace)
    c = emit_c(files, passing, namespace)
    assert "struct main_Box_i32 { int32_t val; };" in c   # the instance struct
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


def test_generic_struct_with_slice_field_infers_from_literal(tmp_path):
    # Vec<T> with a `[T]` field, built from a slice literal: T is solved from the
    # element values. Regression: an expected element type that's an unsolved type
    # param used to fail with "i32 ⊀ T" — a slice literal can't fit against a TVar,
    # so the TVar must be inferred-then-unified, not treated as a constraint.
    (tmp_path / "main.zen").write_text(
        "Vec*<T>: { data: [T], n: i32 }\n"
        "first*<T> = (v: Vec<T>) i32 { v.n }\n"
        "main* = () i32 { v := Vec { data: [5, 10, 15], n: 3 }\n v.data[0] + v.data[2] + first(v) }\n")
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files); resolve(files, namespace)
    _, passing = check(files, namespace)
    assert "main.main" in passing
    c = emit_c(files, passing, namespace)
    harness = '\n#include <stdio.h>\nint main(void){ printf("%d\\n", main_main()); return 0; }\n'
    (tmp_path / "o.c").write_text(c + harness)
    r = subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", str(tmp_path / "o.c"), "-o", str(tmp_path / "o")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert subprocess.run([str(tmp_path / "o")], capture_output=True, text=True).stdout.strip() == "23"


# ── type definitions are toposorted by by-value containment (any decl order) ──
def test_types_emitted_in_dependency_order(tmp_path):
    # `Outer` embeds `Inner` BY VALUE but is declared FIRST. The C definition of Inner
    # must still precede Outer's. Regression: emit used decl order -> incomplete type.
    (tmp_path / "main.zen").write_text(
        "Outer*: { inner: Inner, k: i32 }\n"
        "Inner*: { v: i32 }\n"
        "main* = () i32 { o := Outer { inner: Inner { v: 42 }, k: 1 }\n o.inner.v + o.k }\n")
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files); resolve(files, namespace)
    _, passing = check(files, namespace)
    assert "main.main" in passing
    c = emit_c(files, passing, namespace)
    assert c.index("struct main_Inner {") < c.index("struct main_Outer {")   # inner first
    (tmp_path / "o.c").write_text(c + "\nint main(void){ return main_main(); }\n")
    r = subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", str(tmp_path / "o.c"), "-o", str(tmp_path / "o")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert subprocess.run([str(tmp_path / "o")]).returncode == 43


# ── match auto-derefs a Ptr<Enum>, so recursive heap structures walk cleanly ──
def test_match_auto_derefs_pointer_to_enum(tmp_path):
    # A binary tree built on the heap (stack-addressed here): `sum` recurses through
    # Ptr<Tree>, and `t.match ({ … })` derefs the pointer like field access does, so
    # `n.l` / `n.r` (themselves Ptr<Tree>) recurse. Sum = 3 + (4 + 5) = 12.
    (tmp_path / "main.zen").write_text("""
NodeData*: { l: Ptr<Tree>, r: Ptr<Tree> }
Tree*: Leaf(i32) | Node(NodeData)
leaf = (v: i32) Tree { .Leaf(v) }
node = (l: Ptr<Tree>, r: Ptr<Tree>) Tree { .Node(NodeData { l: l, r: r }) }
sum* = (t: Ptr<Tree>) i32 { t.match ({ .Leaf(v) => v, .Node(n) => sum(n.l) + sum(n.r) }) }
main* = () i32 {
    a := leaf(3)\n    b := leaf(4)\n    c := leaf(5)
    bc := node(addr(b), addr(c))
    rt := node(addr(a), addr(bc))
    sum(addr(rt))
}
""")
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files); resolve(files, namespace)
    _, passing = check(files, namespace)
    assert "main.main" in passing
    c = emit_c(files, passing, namespace)
    assert "->tag" in c                                # the match reaches the tag through the pointer
    (tmp_path / "o.c").write_text(c + "\nint main(void){ return main_main(); }\n")
    r = subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", str(tmp_path / "o.c"), "-o", str(tmp_path / "o")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert subprocess.run([str(tmp_path / "o")]).returncode == 12


# ── A match subject with side effects is evaluated exactly once ─────────────
def test_match_subject_evaluated_once(tmp_path):
    (tmp_path / "main.zen").write_text(
        "Vec*: { len: i32, cap: i32 }\n"
        "kind* = (v: Ptr<Vec>) i32 { v.len }\n"
        "pick* = (v: Ptr<Vec>) i32 { (kind(v)).match ({ 0 => 10, 1 => 20, _ => 30 }) }\n")
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files)
    resolve(files, namespace)
    _, passing = check(files, namespace)
    pick = [ln for ln in emit_c(files, passing, namespace).splitlines()
            if "main_pick" in ln and "return" in ln][0]
    assert pick.count("main_kind") == 1, pick      # not re-evaluated per arm


# ── A lone wildcard match still evaluates its subject without a -Werror warning ─
def test_wildcard_only_match_is_warning_clean(tmp_path):
    # `n.match ({ _ => 42 })` binds the subject to a temp that no arm reads. The temp
    # must still be emitted (the subject may have side effects) but guarded with
    # `(void)` so -Werror=unused-variable doesn't fire. Regression.
    (tmp_path / "main.zen").write_text(
        "f* = (n: i32) i32 { n.match ({ _ => 42 }) }\n"
        "main* = () i32 { f(7) }\n")
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files); resolve(files, namespace)
    _, passing = check(files, namespace)
    c = emit_c(files, passing, namespace)
    assert "(void)_subj" in c                          # the guard is present
    harness = '\n#include <stdio.h>\nint main(void){ printf("%d\\n", main_main()); return 0; }\n'
    (tmp_path / "o.c").write_text(c + harness)
    r = subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", str(tmp_path / "o.c"), "-o", str(tmp_path / "o")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr                 # would fail on -Werror=unused-variable before
    assert subprocess.run([str(tmp_path / "o")], capture_output=True, text=True).stdout.strip() == "42"


# ── Generic enums monomorphize and run ──────────────────────────────────────
def test_generic_enum_monomorphizes(tmp_path):
    (tmp_path / "main.zen").write_text(
        "Opt*<T>: None | Some(T)\n"
        "some_i* = (n: i32) Opt<i32> { .Some(n) }\n"
        "get* = (o: Opt<i32>) i32 { o.match ({ .None => 0, .Some(v) => v }) }\n"
        "main* = () i32 { get(some_i(42)) }\n")
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files)
    resolve(files, namespace)
    _, passing = check(files, namespace)
    c = emit_c(files, passing, namespace)
    assert "struct main_Opt_i32 { int32_t tag; union { int32_t Some; } u; };" in c   # instance struct
    assert "main_Opt_i32){ .tag = main_Opt_i32_Some" in c             # ctor uses the instance name
    harness = ("\n#include <stdio.h>\nint main(void){ "
               "printf(\"%d\\n\", main_main()); return 0; }\n")
    cfile = tmp_path / "o.c"
    cfile.write_text(c + harness)
    bexe = tmp_path / "o"
    r = subprocess.run(["cc", "-Wall", "-Wextra", str(cfile), "-o", str(bexe)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert subprocess.run([str(bexe)], capture_output=True, text=True).stdout.strip() == "42"


# ── M1: extern FFI binds libc; side-effecting statements are preserved ──────
def test_extern_ffi_runs(tmp_path):
    (tmp_path / "main.zen").write_text("""
putchar = (c: i32) i32
malloc  = (n: i64) RawPtr<u8>
free    = (p: RawPtr<u8>) void
main* = () i32 {
    putchar(90) putchar(101) putchar(110) putchar(10)   // Z e n \\n
    free(malloc(64))
    0
}
""")
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files)
    resolve(files, namespace)
    _, passing = check(files, namespace)
    c = emit_c(files, passing, namespace)
    # intermediate side effects are emitted (not collapsed to the last expr)
    assert c.count("putchar(") == 4
    assert "extern" not in c.split("int32_t main_main")[0] or "#include <stdlib.h>" in c
    cfile = tmp_path / "o.c"
    cfile.write_text(c + "\nint main(void){ return main_main(); }\n")
    bexe = tmp_path / "o"
    r = subprocess.run(["cc", "-Wall", "-Wextra", str(cfile), "-o", str(bexe)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr                  # warning-free (libc via headers)
    assert subprocess.run([str(bexe)], capture_output=True, text=True).stdout == "Zen\n"


# ── M2: alloc a buffer, store/load/offset through it, run ───────────────────
def test_raw_memory_runs(tmp_path):
    (tmp_path / "main.zen").write_text("""
putchar = (c: i32) i32
malloc  = (n: i64) RawPtr<u8>
free    = (p: RawPtr<u8>) void
main* = () i32 {
    buf := malloc(8)
    store(offset(buf, 0), 72)            // 'H'
    store(offset(buf, 1), 105)           // 'i'
    putchar(load(offset(buf, 0)))
    putchar(load(offset(buf, 1)))
    putchar(10)
    free(buf)
    0
}
""")
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files)
    resolve(files, namespace)
    _, passing = check(files, namespace)
    c = emit_c(files, passing, namespace)
    assert "((buf) + (0))" in c and "= 72)" in c        # store(offset(..)) erases to *(p+i)=v
    cfile = tmp_path / "o.c"
    cfile.write_text(c + "\nint main(void){ return main_main(); }\n")
    bexe = tmp_path / "o"
    r = subprocess.run(["cc", "-Wall", "-Wextra", str(cfile), "-o", str(bexe)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert subprocess.run([str(bexe)], capture_output=True, text=True).stdout == "Hi\n"


# ── M3: a String that TAKES AN ALLOCATOR, built on the memory primitives ────
def test_string_takes_an_allocator(tmp_path):
    (tmp_path / "main.zen").write_text("""
malloc  = (n: i64) RawPtr<u8>
free    = (p: RawPtr<u8>) void
putchar = (c: i32) i32

Allocator: { id: i32 }
String: { ptr: RawPtr<u8>, len: i64 }

alloc = (a: Ptr<Allocator>, n: i64) RawPtr<u8> { malloc(n) }   // a String takes an allocator

build_hi = (a: Ptr<Allocator>) String {
    p := alloc(a, 2)
    store(offset(p, 0), 72) store(offset(p, 1), 105)
    String { ptr: p, len: 2 }
}

// print by recursing over the bytes
step = (s: Ptr<String>, i: i64) i32 { putchar(load(offset(s.ptr, i))) print_from(s, i+1) }
print_from = (s: Ptr<String>, i: i64) i32 {
    (i < s.len).match ({ false => putchar(10), true => step(s, i) })
}

main* = () i32 {
    a := Allocator { id: 0 }
    s := build_hi(addr(a))
    print_from(addr(s), 0)
    free(s.ptr)
    0
}
""")
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files)
    resolve(files, namespace)
    _, passing = check(files, namespace)
    c = emit_c(files, passing, namespace)
    assert "struct main_String { uint8_t * ptr; int64_t len; };" in c   # heap string
    cfile = tmp_path / "o.c"
    cfile.write_text(c + "\nint main(void){ return main_main(); }\n")
    bexe = tmp_path / "o"
    r = subprocess.run(["cc", str(cfile), "-o", str(bexe)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert subprocess.run([str(bexe)], capture_output=True, text=True).stdout == "Hi\n"


# ── B1+B2: mutation + loops — a growable String that pushes and prints ──────
def test_growable_string_push_loop(tmp_path):
    (tmp_path / "main.zen").write_text("""
malloc  = (n: i64) RawPtr<u8>
free    = (p: RawPtr<u8>) void
putchar = (c: i32) i32

String: { ptr: RawPtr<u8>, len: i64, cap: i64 }
new_str = (cap: i64) String { String { ptr: malloc(cap), len: 0, cap: cap } }

push = (s: MutPtr<String>, b: u8) void {
    store(offset(s.ptr, s.len), b)
    s.len = s.len + 1                      // mutate the field through the pointer
}
print_str = (s: Ptr<String>) void {
    loop(s.len, (h, i) { putchar(load(offset(s.ptr, i))) })
    putchar(10)
}
main* = () i32 {
    s := new_str(16)
    push(addr(s), 72) push(addr(s), 105) push(addr(s), 33)   // H i !
    print_str(addr(s))
    free(s.ptr)
    0
}
""")
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files)
    resolve(files, namespace)
    _, passing = check(files, namespace)
    c = emit_c(files, passing, namespace)
    assert "->len = (" in c and "for (" in c                # field mutation + a loop (folds to for)
    cfile = tmp_path / "o.c"
    cfile.write_text(c + "\nint main(void){ return main_main(); }\n")
    bexe = tmp_path / "o"
    r = subprocess.run(["cc", str(cfile), "-o", str(bexe)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert subprocess.run([str(bexe)], capture_output=True, text=True).stdout == "Hi!\n"


def test_loop_sums(tmp_path):
    (tmp_path / "main.zen").write_text("""
main* = () i32 {
    sum := 0
    loop(11, (h, i) { sum = sum + i })
    sum
}
""")
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files)
    resolve(files, namespace)
    _, passing = check(files, namespace)
    c = emit_c(files, passing, namespace)
    cfile = tmp_path / "o.c"
    cfile.write_text(c + "\nint main(void){ return main_main(); }\n")
    subprocess.run(["cc", str(cfile), "-o", str(tmp_path / "o")], check=True)
    assert subprocess.run([str(tmp_path / "o")]).returncode == 55
