"""std.check — the Zen-written type-resolution/checking module.

Goal C Phase 1: the type lattice `fits(given, want)` over genc's monomorphic Ty
(numeric widening u8<=i32<=i64, else structural equality). Exercised by a Zen program
that builds Ty values, runs fits on them, and returns the count of correct verdicts.
"""
import subprocess
from zen.main import (load, build_namespace, build_scopes, resolve, fold_comptime,
                      run_emits, check, emit_c)


FITS_DRIVER = """
{ ti32, ti64, tu8, tbool, tstr, tnamed } = std.genc
{ fits } = std.check
beq = (got: bool, want: bool) i32 {
    got.match ({ true => want.match ({ true => 1, false => 0 }), false => want.match ({ true => 0, false => 1 }) })
}
main* = () i32 {
    c := 0
    c = c + beq(fits(tu8(), ti32()), true)        // u8 widens to i32
    c = c + beq(fits(tu8(), ti64()), true)        // u8 widens to i64
    c = c + beq(fits(ti32(), ti64()), true)       // i32 widens to i64
    c = c + beq(fits(ti32(), ti32()), true)       // identical
    c = c + beq(fits(ti32(), tu8()), false)       // no narrowing
    c = c + beq(fits(ti64(), ti32()), false)      // no narrowing
    c = c + beq(fits(tbool(), ti32()), false)     // bool is not numeric
    c = c + beq(fits(ti32(), tbool()), false)
    c = c + beq(fits(tstr(), tstr()), true)       // str == str
    c = c + beq(fits(tnamed("Pt"), tnamed("Pt")), true)    // same struct name
    c = c + beq(fits(tnamed("Pt"), tnamed("Q")), false)    // different struct name
    c = c + beq(fits(tnamed("Pt"), ti32()), false)         // struct vs scalar
    c
}
"""


def test_fits_lattice(tmp_path):
    (tmp_path / "main.zen").write_text(FITS_DRIVER)
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files); resolve(files, namespace)
    fold_comptime(files, namespace); run_emits(files, namespace)
    _, passing = check(files, namespace)
    assert "main.main" in passing
    c = emit_c(files, passing, namespace, roots={"main.main"})
    (tmp_path / "o.c").write_text(c + "\nint main(void){ return main_main(); }\n")
    assert subprocess.run(["cc", "-std=gnu11", str(tmp_path / "o.c"), "-o", str(tmp_path / "o")],
                          capture_output=True, text=True).returncode == 0
    assert subprocess.run([str(tmp_path / "o")]).returncode == 12   # all 12 verdicts correct


# check_module: a validating pass (Goal C Phase 1) — counts CALL ARITY errors.
ARITY_DRIVER = """
{ Malloc } = std.alloc
{ parse_module } = std.parse
{ check_module } = std.check
main* = () i32 { m := Malloc { _: 0 }\n addr(m).check_module(addr(m).parse_module("%s")) }
"""


def _arity_errors(tmp_path, src):
    (tmp_path / "main.zen").write_text(ARITY_DRIVER % src.replace("\n", "\\n"))
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files); resolve(files, namespace)
    fold_comptime(files, namespace); run_emits(files, namespace)
    _, passing = check(files, namespace)
    assert "main.main" in passing
    c = emit_c(files, passing, namespace, roots={"main.main"})
    (tmp_path / "o.c").write_text(c + "\nint main(void){ return main_main(); }\n")
    assert subprocess.run(["cc", "-std=gnu11", str(tmp_path / "o.c"), "-o", str(tmp_path / "o")],
                          capture_output=True, text=True).returncode == 0
    return subprocess.run([str(tmp_path / "o")]).returncode


def test_check_arity_accepts_correct_calls(tmp_path):
    assert _arity_errors(tmp_path, "add* = (a: i32, b: i32) i32 { a + b }\nuse* = () i32 { add(1, 2) }") == 0


def test_check_arity_flags_wrong_count(tmp_path):
    # one too few, then one too many -> two errors.
    assert _arity_errors(tmp_path, "add* = (a: i32, b: i32) i32 { a + b }\nf* = () i32 { add(1) }") == 1
    assert _arity_errors(tmp_path, "add* = (a: i32, b: i32) i32 { a + b }\nf* = () i32 { add(1) }\ng* = () i32 { add(1, 2, 3) }") == 2
    # an undefined name (a typo or a missing binding) IS flagged — matching the Python frontend,
    # which rejects `putchar` here as an unbound function. (A foreign decl or import makes it known;
    # see tests/test_undefined.py and tests/test_foreign.py.)
    assert _arity_errors(tmp_path, "f* = (x: i32) i32 { putchar(x) }") == 1


def test_check_arg_type_widening_ok(tmp_path):
    # u8 -> i64 is a valid widening; passing a u8 where i64 is wanted is NOT an error
    assert _arity_errors(tmp_path, "f* = (n: i64) i32 { 0 }\ng* = (b: u8) i32 { f(b) }") == 0


def test_check_arg_type_narrowing_flagged(tmp_path):
    # i64 -> u8 narrows; flagged. And an int passed where a struct is wanted is flagged.
    assert _arity_errors(tmp_path, "f* = (n: u8) i32 { 0 }\ng* = (m: i64) i32 { f(m) }") == 1
    assert _arity_errors(tmp_path, "Pt*: { x: i32 }\nf* = (p: Pt) i32 { 0 }\nuse* = () i32 { f(42) }") == 1


def test_check_arg_type_uninferable_arg_is_skipped(tmp_path):
    # `true` parses as a Var whose type the checker can't infer (void) -> SKIPPED, no false
    # positive. (Soundness: a valid program is never rejected.)
    assert _arity_errors(tmp_path, "f* = (b: bool) i32 { 0 }\nuse* = () i32 { f(true) }") == 0


# ── Phase 3: the PARITY GATE — the Zen checker (check_module) and the Python checker must
# agree on accept/reject for the same programs. The Zen checker covers a SOUND subset (arity
# + clear arg-type mismatches), so the suite stays within what both decide the same way.
import pytest


def _python_accepts(tmp_path, src):
    """Run the Python pipeline through check on `src`; True iff every user fn type-checks."""
    (tmp_path / "main.zen").write_text(src)
    files = load(tmp_path)
    ns = build_namespace(files)
    build_scopes(files); resolve(files, ns)
    fold_comptime(files, ns); run_emits(files, ns)
    errs, _ = check(files, ns)
    return all(ok for name, ok, _ in errs if name.startswith("main."))


@pytest.mark.parametrize("src,valid", [
    # valid monomorphic programs — both accept
    ("add* = (a: i32, b: i32) i32 { a + b }\nuse* = () i32 { add(1, 2) }", True),
    ("wide* = (n: i64) i32 { 0 }\ng* = (b: u8) i32 { wide(b) }", True),            # u8 -> i64 widens
    ("Pt*: { x: i32, y: i32 }\nfx* = (p: Pt) i32 { p.x }", True),
    # rejected — both reject
    ("add* = (a: i32, b: i32) i32 { a + b }\nf* = () i32 { add(1) }", False),       # too few args
    ("add* = (a: i32, b: i32) i32 { a + b }\nf* = () i32 { add(1, 2, 3) }", False), # too many args
    ("narrow* = (n: u8) i32 { 0 }\ng* = (m: i64) i32 { narrow(m) }", False),        # i64 -> u8 narrows
])
def test_checker_parity_with_python(tmp_path, src, valid):
    # sanity: the Python checker agrees with our label, then the Zen checker agrees with Python
    assert _python_accepts(tmp_path, src) == valid
    zen_errors = _arity_errors(tmp_path, src)
    assert (zen_errors == 0) == valid, f"Zen checker disagreed with Python on: {src!r}"
