"""U1 Step 1 (Goal U): `zenc build foo.zen -o foo` / `zenc run foo.zen` produce + run a native binary.

The shipping `zenc` gains a real build path: it emits the program's C (HEAD swapped for #include "zenrt.h"),
links bootstrap/zenrt.c via cc, and runs it. A Zen `main = () i32 { … }` is the entry (emits C `int32_t
main()`). zenrt.{c,h} are found relative to the binary (<dir(argv0)>/bootstrap), so this uses the repo's
make-built ROOT/zenc (which sits beside ROOT/bootstrap). U1 Step 3 wired the Zen module loader
(std.resolve.resolve_program) into the binary, so `zenc build/run/check` now RESOLVE `{ … } = std.X`
imports from <root>/zen/std/X.zen — see test_zenc_run_resolves_std_import below.
"""
import subprocess
import tempfile
from pathlib import Path

import _oracle

ROOT = _oracle.ROOT


def _zenc():
    """The repo's make-built zenc (beside ROOT/bootstrap, so it can find zenrt.{c,h})."""
    subprocess.run(["make", "-f", "bootstrap/Makefile", "zenc"], cwd=str(ROOT),
                   check=True, capture_output=True)
    return str(ROOT / "zenc")


def test_zenc_build_emits_runnable_binary():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text("main = () i32 { 6 * 2 }\n")
    out = d / "p"
    r = subprocess.run([zenc, "build", str(d / "p.zen"), "-o", str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert out.exists(), "zenc build produced no binary"
    assert subprocess.run([str(out)]).returncode == 12


def test_zenc_run_struct_program():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text("P*: { x: i32, y: i32 }\nmain = () i32 { p := P(x: 3, y: 4)  p.x * p.y }\n")
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 12, r.stderr


def test_zenc_build_bad_file():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    out = d / "x"
    r = subprocess.run([zenc, "build", "/no/such/file.zen", "-o", str(out)], capture_output=True, text=True)
    assert r.returncode == 1, r.returncode  # clean failure (exit 1), not a signal death
    assert "cannot open" in r.stderr, r.stderr
    assert not out.exists()


def test_zenc_check_reports_error_count_and_first_kind():
    """U1.2: the binary now type-checks — the killer case (undefined name was emit-exit-0)."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    src = d / "p.zen"
    src.write_text("main = () i32 { undefined_fn(1, 2) }\n")
    r = subprocess.run([zenc, "check", str(src)], capture_output=True, text=True)
    assert r.returncode == 1
    # U1.4 Phase 2: human message + the error's 1-based line:col (undefined_fn starts at col 17)
    assert r.stderr == f"zenc: {src}:1:17: error: undefined name\n"


def test_zenc_check_position_survives_import_flattening():
    """U1.4 Phase 2: the checker's byte offset is into the import-FLATTENED source; the reported
    line:col must still land in the USER's file (mapped back by the error line's text)."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    src = d / "p.zen"
    src.write_text('{ println } = std.fmt\nmain = () i32 {\n    println("hi")\n    oops()\n}\n')
    r = subprocess.run([zenc, "check", str(src)], capture_output=True, text=True)
    assert r.returncode == 1
    assert r.stderr == f"zenc: {src}:4:5: error: undefined name\n"


# ── pos-preserving rebuilds (check.zen recall/revar/var_call): the resolver/inliner REBUILDS every
# Call/Var it walks, copying the ORIGINAL node's pos structurally. These lock the chosen semantics:
# an error inside a generic template body / a lambda spliced at a HOF call site reports the byte
# offset of the offending name ITSELF (template-internal positions survive subst_expr + xform_call
# + inline_lambda) — NOT a callsite fallback, and NOT pos 0 ("unknown"), which a single rebuild
# site using the pos-0 ctor once caused for EVERY call the inliner walked. ─────────────────────────
def test_zenc_check_position_survives_generic_instantiation():
    """Undefined name INSIDE a generic fn body, instantiated at a call site (the subst/xform
    inline paths): `oops` sits at 1:21 in the template body and is reported there."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    src = d / "p.zen"
    src.write_text("wrap = (x: T) i32 { oops(x) }\nmain = () i32 { wrap(41) }\n")
    r = subprocess.run([zenc, "check", str(src)], capture_output=True, text=True)
    assert r.returncode == 1
    assert f"{src}:1:21: error: undefined name" in r.stderr, r.stderr


def test_zenc_check_position_survives_lambda_body_inlining():
    """Undefined name inside a LAMBDA spliced by HOF inlining (inline_lambda/xform_body):
    `bad` sits at 3:17 inside the lambda literal and is reported there."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    src = d / "p.zen"
    src.write_text(
        "apply = (f: (i32) i32, x: i32) i32 { f(x) }\n"
        "main = () i32 {\n"
        "    apply((n) { bad(n) }, 41)\n"
        "}\n")
    r = subprocess.run([zenc, "check", str(src)], capture_output=True, text=True)
    assert r.returncode == 1
    assert f"{src}:3:17: error: undefined name" in r.stderr, r.stderr


def test_zenc_check_position_after_lambda_hof_inlining():
    """Undefined name AFTER a lambda-HOF call in the same body (the inliner rebuilt the whole
    body around it): `nope` sits at 4:5 and is reported there."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    src = d / "p.zen"
    src.write_text(
        "apply = (f: (i32) i32, x: i32) i32 { f(x) }\n"
        "main = () i32 {\n"
        "    r := apply((n) { n + 1 }, 41)\n"
        "    nope(r)\n"
        "}\n")
    r = subprocess.run([zenc, "check", str(src)], capture_output=True, text=True)
    assert r.returncode == 1
    assert r.stderr == f"zenc: {src}:4:5: error: undefined name\n"


def test_zenc_check_rejects_source_if():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text("main = () i32 { if (1 < 2) { return 9 } 7 }\n")
    r = subprocess.run([zenc, "check", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode != 0 and "undefined name" in r.stderr, r.stderr


def test_zenc_check_ok_program():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text("main = () i32 { 6 * 2 }\n")
    assert subprocess.run([zenc, "check", str(d / "p.zen")]).returncode == 0


def test_zenc_build_rejects_illtyped_no_binary():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text("main = () i32 { 1 < 2 }\n")  # bool not<: i32 -> return-fit
    out = d / "p"
    r = subprocess.run([zenc, "build", str(d / "p.zen"), "-o", str(out)], capture_output=True, text=True)
    assert r.returncode != 0 and not out.exists(), "ill-typed program should not produce a binary"


def test_zenc_run_prints_floats():
    """f64 end-to-end: float literals, arithmetic, and std.fmt's println_float (the %g-flavoured
    Zen-side formatter) — exact stdout pinned, so the formatting can't silently drift."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ println_float } = std.fmt\n\n"
        "main = () i32 {\n"
        "  println_float(1.5)\n"
        "  println_float(0.25)\n"
        "  println_float(-3.0)\n"
        "  println_float(0.001)\n"
        "  println_float(1.5 + 0.25 * 2.0)\n"   # precedence: 1.5 + 0.5 = 2
        "  0\n"
        "}\n")
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "1.5\n0.25\n-3\n0.001\n2\n", repr(r.stdout)


# ── U1.3: the binary RESOLVES `{ … } = std.X` imports from disk (std.resolve folded in) ──────────────
_IMPORT_PROG = (
    "{ eq } = std.str\n"
    "main = () i32 { eq(%s).match ({ true => 1, false => 0 }) }\n"
)


def test_zenc_run_resolves_std_import():
    """THE U1.3 PAYOFF: a program that imports std.str builds + runs — the import is resolved from
    <root>/zen/std/str.zen (today the binary used to silently strip imports → stdlib unreachable)."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    # eq of equal strings → true → 1 (so a non-resolving build, which would fail to link `eq`, can't pass).
    (d / "p.zen").write_text(_IMPORT_PROG % '"ab", "ab"')
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 1, r.stderr  # eq("ab","ab") == true → 1
    # the false branch resolves identically → 0.
    (d / "q.zen").write_text(_IMPORT_PROG % '"ab", "xy"')
    r = subprocess.run([zenc, "run", str(d / "q.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr  # eq("ab","xy") == false → 0


def test_zenc_build_resolves_std_import():
    """`zenc build` (not just run) of a std-importing program yields a runnable native binary."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(_IMPORT_PROG % '"ab", "ab"')
    out = d / "p"
    r = subprocess.run([zenc, "build", str(d / "p.zen"), "-o", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert out.exists(), "zenc build of a std-importing program produced no binary"
    assert subprocess.run([str(out)]).returncode == 1


def test_zenc_check_resolves_std_import():
    """`zenc check` resolves the import too — a well-typed std-importing program checks ok."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(_IMPORT_PROG % '"ab", "ab"')
    assert subprocess.run([zenc, "check", str(d / "p.zen")]).returncode == 0


# ── U3: std.fmt — a program can PRINT (output + int→string), via std.string ──────────────────────────
# This also locks in the #98 fix: std.fmt pulls std.string, so a built program emits its own `String`,
# which must NOT clash with zenrt.h's (the build path defines ZEN_NO_STRING to suppress the latter).
def test_zenc_run_prints_text_and_ints():
    """`println`/`println_int` from std.fmt actually write to stdout — text, then a formatted int."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ println, println_int } = std.fmt\n"
        "main = () i32 { println(\"answer:\")  println_int(42)  0 }\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "answer:\n42\n", repr(r.stdout)


def test_zenc_run_int_to_str_negatives_and_zero():
    """int→string handles 0, negatives (leading '-'), and multi-digit — the itoa edge cases."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ println_int } = std.fmt\n"
        "main = () i32 { println_int(0)  println_int(-7)  println_int(1000000)  0 }\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "0\n-7\n1000000\n", repr(r.stdout)


# ── U3: std.vec — a growable Vec<T> with an EXPLICIT allocator (acquire/resize/release), no hidden malloc ─
# (mutators are v-prefixed — vpush/vlen/vgrow — so they don't clash with std.string's push/len/grow in a
#  flat namespace; get/vec_of/free_vec don't clash and keep plain names.)
def test_zenc_run_vec_explicit_allocator():
    """Vec<T> threads a Ptr<A:Allocator> per op: vec_of/vpush/get/free_vec, Malloc-backed. Proves generic
    + trait dispatch (a.acquire/resize/release monomorphize to impl_Allocator_Malloc_*) end to end."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ vec_of, vpush, get, free_vec } = std.vec\n"
        "main = () i32 {\n"
        "  m := Malloc(_: 0)\n"
        "  v := addr(m).vec_of([10, 20])\n"
        "  v2 := addr(m).vpush(v, 30)\n"         # len==cap → grows via a.resize
        "  total := v2.get(0) + v2.get(2)\n"
        "  addr(m).free_vec(v2)\n"
        "  total\n"
        "}\n"
    )
    assert subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True).returncode == 40


def test_zenc_run_vec_growth_resizes():
    """Repeated push past capacity forces several a.resize grows; live elements survive each grow."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    pushes = "".join(f"  v{i} := addr(m).vpush(v{i-1}, {i+1})\n" for i in range(1, 6))
    gets = " + ".join(f"v5.get({i})" for i in range(6))
    (d / "p.zen").write_text(
        "{ vec_of, vpush, get } = std.vec\n"
        "main = () i32 {\n"
        "  m := Malloc(_: 0)\n"
        "  v0 := addr(m).vec_of([1])\n"
        f"{pushes}"
        f"  {gets}\n"
        "}\n"
    )
    # 1+2+3+4+5+6 = 21
    assert subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True).returncode == 21


def test_zenc_run_vec_and_print_together():
    """THE payoff: a single program imports a COLLECTION (std.vec) AND formatted output (std.fmt) and
    runs — the v-prefixed Vec verbs no longer clash with std.string's push/len in one flat namespace."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ vec_of, vpush, get } = std.vec\n"
        "{ println_int } = std.fmt\n"
        "main = () i32 {\n"
        "  m := Malloc(_: 0)\n"
        "  v := addr(m).vec_of([10, 20])\n"
        "  v2 := addr(m).vpush(v, 30)\n"
        "  println_int(v2.get(0))\n"              # 10
        "  println_int(v2.get(2))\n"              # 30
        "  0\n"
        "}\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "10\n30\n", repr(r.stdout)


# ── CAPSTONE: a real program (examples/stats.zen) composing Vec + generics + enums + match + fmt ──────
def test_zenc_run_capstone_stats_example():
    """The Goal-U proof: examples/stats.zen — list statistics (sum/max/even-count) over a Vec<i32> with an
    explicit allocator, enum-dispatched via .match, printed via std.fmt — builds and runs end to end."""
    zenc = _zenc()
    r = subprocess.run([zenc, "run", str(ROOT / "examples" / "stats.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "sum:\n39\nmax:\n9\nevens:\n3\n", repr(r.stdout)


# ── U2/fuzz #2b/P3: undefined name in VALUE/ARG position is rejected (was check=ok → leaked cc errors) ──
def test_zenc_check_rejects_undefined_name_in_value_position():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text("main = () i32 { undefined_thing }\n")
    r = subprocess.run([zenc, "check", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode != 0 and "undefined name" in r.stderr, r.stderr


def test_zenc_check_rejects_undefined_name_in_arg_position():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text("id = (n: i32) i32 { n }\nmain = () i32 { id(undefined_thing) }\n")
    r = subprocess.run([zenc, "check", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode != 0 and "undefined name" in r.stderr, r.stderr


def test_p3_does_not_false_reject_true_false_or_sizeof_or_bound_locals():
    """Guard the P3 false-positives: `true`/`false` as values, `sizeof(T)` (T is a type, not a value), and
    a local bound to a void/generic value all stay ACCEPTED (the membership-based var_err)."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "Box<T>: { v: T }\n"
        "mk<T> = (x: T) i64 { b := Box<T>(v: x)  sizeof(T) }\n"   # sizeof(T) + a generic-struct-bound local
        "pick = (c: bool) bool { c.match ({ true => false, false => true }) }\n"  # true/false as VALUES
        "main = () i32 { 0 }\n"
    )
    assert subprocess.run([zenc, "check", str(d / "p.zen")]).returncode == 0


def test_zenc_check_keeps_match_payload_bindings_in_scope():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "R*: Ok(i32) | Err\n"
        "main = () i32 { r := .Ok(7)  r.match({ .Ok(v) => v, .Err => 0 }) }\n"
    )
    r = subprocess.run([zenc, "check", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_zenc_check_threads_block_let_bindings():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "main = () i32 { true.match({ true => { x := 4  x }, false => 0 }) }\n"
    )
    r = subprocess.run([zenc, "check", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ── review fix #1: HOFs — calling a fn-typed PARAM works (named fn AND lambda args) ──────────────────
def test_zenc_run_hof_named_fn_and_lambda():
    """`apply = (f: (i32) i32, x: i32) i32 { f(x) }` — the call f(x) was false-rejected as undefined-name
    (validator missed the FnT-param case), and a NAMED fn arg mono-inlined to a bare var (bad C)."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "apply = (f: (i32) i32, x: i32) i32 { f(x) }\n"
        "twice = (n: i32) i32 { n * 2 }\n"
        "main = () i32 { apply(twice, 11) + apply((n){ n + 9 }, 11) }\n"   # 22 + 20 = 42
    )
    assert subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True).returncode == 42


# ── review fix #3: mid-file garbage is a SYNTAX ERROR, not silently-dropped decls ────────────────────
def test_zenc_check_rejects_midfile_garbage():
    """A truncated/garbage region used to make `check` say ok while silently DROPPING every decl after it
    (then run said "no main"). Now: kind 14 syntax-error sentinel per unparseable token, later decls kept."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text("good = () i32 { 1 }\n@@@ !!!\nmain = () i32 { good() + 6 }\n")
    r = subprocess.run([zenc, "check", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode != 0 and "syntax error" in r.stderr, r.stderr


# ── review fix #4 / fuzz #8: leading-paren statement glue ────────────────────────────────────────────
def test_zenc_no_leading_paren_statement_glue():
    """`b := id` then a new line `(4)` used to glue into `b := id(4)` (a silent miscompile when the RHS
    names a fn). A `(` that opens a NEW LINE is its own statement, mirroring the `[` same-line rule."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ println_int } = std.fmt\n"
        "id = (n: i64) i64 { n }\n"
        "main = () i32 {\n  b := id\n  (4)\n  println_int(7)\n  0\n}\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout == "7\n", (r.returncode, r.stdout, r.stderr)


# ── census #5: bitwise operators & | ^ << >> (were SILENT wrong-answers via statement-glue) ──────────
def test_zenc_bitwise_operators():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text("main = () i32 { (12 & 10) + (12 | 3) * 10 + (12 ^ 10) * 100 + (1 << 4) - (64 >> 2) }\n")
    # 8 + 150 + 600 + 16 - 16 = 758 % 256 = 246
    assert subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True).returncode == 246
    # bitwise binds TIGHTER than comparison: 6 & 3 == 2 → (6&3)==2 → true
    (d / "q.zen").write_text("main = () i32 { (6 & 3 == 2).match ({ true => 1, false => 0 }) }\n")
    assert subprocess.run([zenc, "run", str(d / "q.zen")], capture_output=True).returncode == 1


# ── census #6: explicit int casts to_i32/to_i64/to_u8 (no narrowing path existed at all) ─────────────
def test_zenc_int_cast_intrinsics():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text('{ len } = std.str\nmain = () i32 { n := len("hello")  to_i32(n) }\n')
    assert subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True).returncode == 5
    (d / "q.zen").write_text("main = () i32 { big := 4294967298  to_i32(big) }\n")   # 2^32+2 truncates to 2
    assert subprocess.run([zenc, "run", str(d / "q.zen")], capture_output=True).returncode == 2


# ── census #8: C-keyword identifiers are mangled (fn `double` emitted verbatim → cc explosion) ───────
def test_zenc_c_keyword_identifiers():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "double = (n: i32) i32 { n * 2 }\n"
        "P*: { int: i32 }\n"
        "main = () i32 { short := P(int: double(20))  short.int + 2 }\n"
    )
    assert subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True).returncode == 42


# ── census #11: the 1024-decl cap silently truncated big programs ────────────────────────────────────
def test_zenc_2000_decl_program():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    fns = "\n".join(f"f{i} = () i32 {{ {i % 100} }}" for i in range(2000))
    (d / "p.zen").write_text(fns + "\nmain = () i32 { f1999() }\n")
    assert subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True).returncode == 99


# ── outsider kit: every example must build and run (the quickstart points at these) ──────────────────
def test_all_examples_run():
    zenc = _zenc()
    names = sorted(p.stem for p in (ROOT / "examples").glob("*.zen"))
    assert {"hello", "fizzbuzz", "bank", "shapes", "stats"} <= set(names)
    for name in names:
        r = subprocess.run([zenc, "run", str(ROOT / "examples" / f"{name}.zen")], capture_output=True, text=True)
        assert r.returncode == 0, (name, r.returncode, r.stderr)


def test_zenc_help_version_and_zen_root():
    zenc = _zenc()
    h = subprocess.run([zenc, "--help"], capture_output=True, text=True)
    assert h.returncode == 0 and "usage:" in h.stdout
    v = subprocess.run([zenc, "--version"], capture_output=True, text=True)
    assert v.returncode == 0 and "zenc" in v.stdout
    # bare `zenc` is TTY-gated: on a TERMINAL it prints usage (exit 2); with PIPED stdin it stays the
    # classic source→C filter the oracle depends on. Under pytest stdin is a pipe, so exercise the filter.
    bare = subprocess.run([zenc], capture_output=True, text=True, input="test* = () i32 { 1 }\n")
    assert bare.returncode == 0 and "zslice" in bare.stdout
    # a relocated binary works when ZEN_ROOT points at the checkout
    d = Path(tempfile.mkdtemp())
    moved = d / "zenc-moved"
    moved.write_bytes(Path(zenc).read_bytes()); moved.chmod(0o755)
    (d / "p.zen").write_text("main = () i32 { 42 }\n")
    import os
    env = dict(os.environ, ZEN_ROOT=str(ROOT))
    assert subprocess.run([str(moved), "run", str(d / "p.zen")], capture_output=True, env=env).returncode == 42


# ── P3 / #100: the `_ => body` bool-guard parsed as if bare — swallowed the rest of the function ─────
def test_bool_guard_wild_with_body():
    """`(c).match({ true => { return X }, _ => {} })` — parse_bool_wild assumed a BARE `_` and resumed
    parsing inside the arm, silently dropping every statement after the match. All forms must work."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    for arm in ["_ => 0", "_ => {}", "_ => {},", "_"]:
        (d / "p.zen").write_text(
            "{ println_int } = std.fmt\n"
            "f = (n: i32) i32 {\n"
            f"  (n == 0).match ({{ true => {{ return 100 }}, {arm} }})\n"
            "  println_int(50)\n  n\n}\n"
            "main = () i32 { println_int(f(0))  println_int(f(7))  0 }\n"
        )
        r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
        assert r.returncode == 0 and r.stdout == "100\n50\n7\n", (arm, r.returncode, r.stdout, r.stderr)


# ── P3 / census #7: typed-local annotations are REAL (checked + drive inference + emit the C type) ───
def test_typed_local_annotations_honored():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    # (1) an i64 accumulator IS int64_t: 2^32 survives, (a+2^32)/2^30 = 4
    (d / "a.zen").write_text("main = () i32 { a: i64 := 0  a = a + 4294967296  to_i32(a / 1073741824) }\n")
    assert subprocess.run([zenc, "run", str(d / "a.zen")], capture_output=True).returncode == 4
    # (2) the fuzz-#7 escape hatch: an annotation gives a bare .None its enum
    (d / "b.zen").write_text(
        "Opt<T>: Some(T) | None\n"
        "u<T> = (o: Opt<T>) i32 { o.match ({ .Some(x) => x, .None => 7 }) }\n"
        "main = () i32 { o: Opt<i32> := .None  u(o) }\n"
    )
    assert subprocess.run([zenc, "run", str(d / "b.zen")], capture_output=True).returncode == 7
    # (3) a mismatching init is REJECTED
    (d / "c.zen").write_text('main = () i32 { x: i32 := "nope"  0 }\n')
    r = subprocess.run([zenc, "check", str(d / "c.zen")], capture_output=True, text=True)
    assert r.returncode != 0 and "does not fit" in r.stderr


# ── resolver triple-fix: generic-head dedup + multi-line imports + ns-region boundary ────────────────
def test_drop_and_fmt_coimport():
    """Generic decl heads (`new<T>* =`) were invisible to the per-name dedup (after_name_is_decl bailed
    at '<'), so std.drop + std.fmt co-import died on "duplicate top-level". Now dedup sees them."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text("{ println_int } = std.fmt\n{ Own } = std.drop\nmain = () i32 { println_int(7)  0 }\n")
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout == "7\n", (r.returncode, r.stdout, r.stderr)
# ── std.str search/slice/parse: find/contains/substr/parse_int/starts_with/char_at ───────────────────
def test_zenc_run_str_ops_edges():
    """The new std.str ops, hammered on edges: find at head/end/absent/empty-needle, substr CLAMPS
    out-of-range (start and n, both directions), char_at is 0 past either end, parse_int handles
    '-'/garbage-tail/all-garbage/empty (documented: no leading digits → 0) and i64-sized values."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        '{ find, contains, substr, parse_int, starts_with, char_at, eq, len } = std.str\n'
        '{ println_int } = std.fmt\n'
        'bi = (b: bool) i64 { b.match ({ true => 1, false => 0 }) }\n'
        'main = () i32 {\n'
        '  println_int(find("hello world", "world"))   // 6: needle flush at the end\n'
        '  println_int(find("hello world", "x"))       // -1: absent\n'
        '  println_int(find("hello world", ""))        // 0: empty needle (strstr convention)\n'
        '  println_int(find("aaab", "aab"))            // 1: overlapping-prefix scan\n'
        '  println_int(bi(contains("hello", "ell")) + bi(starts_with("hello", "he")))   // 2\n'
        '  println_int(bi(starts_with("he", "hello"))) // 0: prefix longer than s\n'
        '  println_int(bi(eq(substr("hello world", 6, 5), "world")))   // 1\n'
        '  println_int(bi(eq(substr("hi", 1, 99), "i")))   // 1: n clamped to the tail\n'
        '  println_int(len(substr("hi", 5, 2)))            // 0: start past the end -> ""\n'
        '  println_int(bi(eq(substr("hi", -3, 1), "h")))   // 1: negative start pinned to 0\n'
        '  println_int(to_i64(char_at("abc", 2)) - \'c\')  // 0: last byte\n'
        '  println_int(to_i64(char_at("abc", 3)) + to_i64(char_at("abc", -1)))   // 0: both ends\n'
        '  println_int(parse_int("-7"))            // -7\n'
        '  println_int(parse_int("12ab"))          // 12: stops at the first non-digit\n'
        '  println_int(parse_int("zen") + parse_int("") + parse_int("-"))   // 0: no digits -> 0\n'
        '  println_int(parse_int("123456789012"))  // i64-sized\n'
        '  0\n'
        '}\n'
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "6\n-1\n0\n1\n2\n0\n1\n1\n0\n1\n0\n0\n-7\n12\n0\n123456789012\n", repr(r.stdout)


def test_zenc_run_str_tokenizer():
    """THE acceptance program: tokenize a hardcoded sentence — find each space, substr the word out,
    parse_int the numeric tokens (incl. a negative) — composed UFCS-style with recursion."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        '{ find, substr, parse_int, len } = std.str\n'
        '{ println, println_int } = std.fmt\n'
        '// print the words of s[from..] (split on \' \'), each followed by its parse_int\n'
        'words = (s: str, from: i64) i64 {\n'
        '  rest := s.substr(from, s.len() - from)\n'
        '  sp := rest.find(" ")\n'
        '  (sp < 0).match ({\n'
        '    true  => { println(rest)  println_int(rest.parse_int())  0 },\n'
        '    false => {\n'
        '      w := rest.substr(0, sp)\n'
        '      println(w)\n'
        '      println_int(w.parse_int())\n'
        '      s.words(from + sp + 1)\n'
        '    },\n'
        '  })\n'
        '}\n'
        'main = () i32 { words("zen has 3 frontends and -1 regrets", 0)  0 }\n'
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout == ("zen\n0\nhas\n0\n3\n3\nfrontends\n0\nand\n0\n-1\n-1\nregrets\n0\n"), repr(r.stdout)



# ── std.map: a str-keyed Map<T> with an EXPLICIT allocator (parallel str/T buffers, linear scan) ─────
def test_zenc_run_map_wordfreq():
    """THE std.map acceptance: word-frequency counting via the mget+1-then-mput idiom — exercises
    put/get/overwrite-upsert/has/miss-default/len AND growth (cap 1 -> 3 -> 7 across 5 distinct keys).
    The counting idiom is also the regression guard for the by-name-arg use-after-free: the value arg
    `m.mget(w, 0) + 1` must be evaluated BEFORE mput's grow resizes the buffers (mappend force-binds)."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        '{ map_new, mput, mget, mhas, mlen, free_map } = std.map\n'
        '{ println_int } = std.fmt\n'
        'bump = (a: Ptr<Malloc>, m: Map<i32>, w: str) Map<i32> { a.mput(m, w, m.mget(w, 0) + 1) }\n'
        'main = () i32 {\n'
        '    m := Malloc(_: 0)\n'
        '    a := addr(m)\n'
        '    w := a.map_new("the", 1)\n'                     # "the cat sat on the mat the cat"
        '    w = a.bump(w, "cat")\n'
        '    w = a.bump(w, "sat")\n'
        '    w = a.bump(w, "on")\n'
        '    w = a.bump(w, "the")\n'
        '    w = a.bump(w, "mat")\n'
        '    w = a.bump(w, "the")\n'
        '    w = a.bump(w, "cat")\n'
        '    println_int(w.mget("the", 0))\n'                # 3
        '    println_int(w.mget("cat", 0))\n'                # 2
        '    println_int(w.mget("sat", 0))\n'                # 1
        '    println_int(w.mget("dog", -1))\n'               # -1: miss -> the default
        '    println_int(w.mhas("mat").match ({ true => 1, false => 0 }))\n'   # 1
        '    println_int(w.mhas("dog").match ({ true => 1, false => 0 }))\n'   # 0
        '    println_int(w.mlen())\n'                        # 5 distinct words
        '    a.free_map(w)\n'
        '    0\n'
        '}\n'
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "3\n2\n1\n-1\n1\n0\n5\n", repr(r.stdout)


def test_zenc_run_map_growth_and_second_value_type():
    """Entries survive repeated grows (9 keys force cap 1 -> 3 -> 7 -> 15, both buffers realloc'd), and
    a Map<str> coexists with a Map<i32> — two monomorphized C types from the one generic source."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    puts = "".join(f'    w = a.mput(w, "k{i}", {i * 10})\n' for i in range(1, 9))
    (d / "p.zen").write_text(
        '{ map_new, mput, mget, mlen, free_map } = std.map\n'
        '{ println, println_int } = std.fmt\n'
        'main = () i32 {\n'
        '    m := Malloc(_: 0)\n'
        '    a := addr(m)\n'
        '    w := a.map_new("k0", 0)\n'
        f'{puts}'
        '    println_int(w.mlen())\n'                        # 9
        '    println_int(w.mget("k0", -1))\n'                # 0: the seed survived 3 grows
        '    println_int(w.mget("k8", -1))\n'                # 80
        '    caps := a.map_new("uk", "london")\n'            # a Map<str> beside the Map<i32>
        '    caps = a.mput(caps, "fr", "paris")\n'
        '    caps = a.mput(caps, "fr", "PARIS")\n'           # upsert overwrites in place
        '    println(caps.mget("fr", "?"))\n'                # PARIS
        '    println(caps.mget("de", "miss"))\n'             # miss
        '    println_int(caps.mlen())\n'                     # 2
        '    a.free_map(w)\n'
        '    a.free_map(caps)\n'
        '    0\n'
        '}\n'
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "9\n0\n80\nPARIS\nmiss\n2\n", repr(r.stdout)


# ── ambient time (#107 v3 keystone): yield() NO-OPS outside a coroutine, still yields inside ────────
def test_yield_is_ambient():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "a.zen").write_text("{ yield } = std.coroutine\n{ println_int } = std.fmt\nmain = () i32 { yield()  println_int(42)  yield()  0 }\n")
    r = subprocess.run([zenc, "run", str(d / "a.zen")], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout == "42\n", (r.returncode, r.stdout, r.stderr)   # was SIGSEGV
    (d / "b.zen").write_text(
        "{ spawn, resume, yield } = std.coroutine\n{ println_int } = std.fmt\n"
        "work = () void { println_int(1)  yield()  println_int(3) }\n"
        "main = () i32 { co := spawn(work)  resume(co)  println_int(2)  resume(co)  0 }\n")
    r = subprocess.run([zenc, "run", str(d / "b.zen")], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout == "1\n2\n3\n", (r.returncode, r.stdout, r.stderr)
