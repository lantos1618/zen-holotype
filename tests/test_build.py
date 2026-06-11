"""U1 Step 1 (Goal U): `zenc build foo.zen -o foo` / `zenc run foo.zen` produce + run a native binary.

The shipping `zenc` gains a real build path: it emits the program's C (HEAD swapped for #include "zenrt.h"),
links bootstrap/zenrt.c via cc, and runs it. A Zen `main = () i32 { … }` is the entry (emits C `int32_t
main()`). zenrt.{c,h} are found relative to the binary (<dir(argv0)>/bootstrap), so this uses the repo's
make-built ROOT/zenc (which sits beside ROOT/bootstrap). U1 Step 3 wired the Zen module loader
(std.internal.resolve.resolve_program) into the binary, so `zenc build/run/check` now RESOLVE `{ … } = std.X`
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
    src.write_text('{ println } = std.text.fmt\nmain = () i32 {\n    println("hi")\n    oops()\n}\n')
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
    """f64 end-to-end: float literals, arithmetic, and std.text.fmt's println_float (the %g-flavoured
    Zen-side formatter) — exact stdout pinned, so the formatting can't silently drift."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ println_float } = std.text.fmt\n\n"
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


# ── U1.3: the binary RESOLVES `{ … } = std.X` imports from disk (std.internal.resolve folded in) ──────────────
_IMPORT_PROG = (
    "{ eq } = std.text.str\n"
    "main = () i32 { eq(%s).match ({ true => 1, false => 0 }) }\n"
)


def test_zenc_run_resolves_std_import():
    """THE U1.3 PAYOFF: a program that imports std.text.str builds + runs — the import is resolved from
    <root>/zen/std/text/str.zen (today the binary used to silently strip imports → stdlib unreachable)."""
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


# ── U3: std.text.fmt — a program can PRINT (output + int→string), via std.text.string ──────────────────────────
# This also locks in the #98 fix: std.text.fmt pulls std.text.string, so a built program emits its own `String`,
# which must NOT clash with zenrt.h's (the build path defines ZEN_NO_STRING to suppress the latter).
def test_zenc_run_prints_text_and_ints():
    """Generic `println` from std.text.fmt writes text and primitive values."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ println } = std.text.fmt\n"
        "main = () i32 { b: bool := true  println(\"answer:\")  println(42)  println(b)  0 }\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "answer:\n42\ntrue\n", repr(r.stdout)


def test_zenc_run_prints_str_and_string():
    """std.text.fmt prints borrowed str and owned String without forcing String.finish()."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ println, println_str, print_string, println_string } = std.text.fmt\n"
        "{ new, append } = std.text.string\n"
        "main = () i32 {\n"
        "  println(\"borrowed\")\n"
        "  println_str(\"alias\")\n"
        "  s := new().append(\"owned\")\n"
        "  print_string(s)\n"
        "  println(\"!\")\n"
        "  println_string(s)\n"
        "  0\n"
        "}\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "borrowed\nalias\nowned!\nowned\n", repr(r.stdout)


def test_zenc_run_int_to_str_negatives_and_zero():
    """int→string handles 0, negatives (leading '-'), and multi-digit — the itoa edge cases."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ println_int } = std.text.fmt\n"
        "main = () i32 { println_int(0)  println_int(-7)  println_int(1000000)  0 }\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "0\n-7\n1000000\n", repr(r.stdout)


def test_zenc_run_core_slice_explicit_allocator():
    """std.core.slice exposes allocator-backed helpers; callers can place copied slices in an arena."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ nbuf_in, dupx_in, node_in, concat_in } = std.core.slice\n"
        "{ arena_new, arena_free } = std.mem.arena\n"
        "main = () i32 {\n"
        "  a := arena_new(1024)\n"
        "  xs := a.addr().dupx_in([1, 2, 3])\n"
        "  ys := a.addr().concat_in(xs, [4, 5])\n"
        "  p := a.addr().node_in(9)\n"
        "  zs := a.addr().nbuf_in(2, xs)\n"
        "  zs[0] = load(p)\n"
        "  zs[1] = ys[4]\n"
        "  out := zs[0] + zs[1]\n"
        "  a.addr().arena_free()\n"
        "  out\n"
        "}\n"
    )
    assert subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True).returncode == 14


# ── U3: std.collections.vec — a growable Vec<T> with an EXPLICIT allocator (acquire/resize/release), no hidden malloc ─
# (mutators are v-prefixed — vpush/vlen/vgrow — so they don't clash with std.text.string's push/len/grow in a
#  flat namespace; get/vec_of/free_vec don't clash and keep plain names.)
def test_zenc_run_vec_explicit_allocator():
    """Vec<T> threads a Ptr<A:Allocator> per op: vec_of/vpush/get/free_vec, Malloc-backed. Proves generic
    + trait dispatch (a.acquire/resize/release monomorphize to impl_Allocator_Malloc_*) end to end."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ vec_of, vpush, get, free_vec } = std.collections.vec\n"
        "main = () i32 {\n"
        "  m := Malloc(_: 0)\n"
        "  v := m.addr().vec_of([10, 20])\n"
        "  v2 := m.addr().vpush(v, 30)\n"         # len==cap → grows via a.resize
        "  total := v2.get(0) + v2.get(2)\n"
        "  m.addr().free_vec(v2)\n"
        "  total\n"
        "}\n"
    )
    assert subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True).returncode == 40


def test_zenc_run_vec_growth_resizes():
    """Repeated push past capacity forces several a.resize grows; live elements survive each grow."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    pushes = "".join(f"  v{i} := m.addr().vpush(v{i-1}, {i+1})\n" for i in range(1, 6))
    gets = " + ".join(f"v5.get({i})" for i in range(6))
    (d / "p.zen").write_text(
        "{ vec_of, vpush, get } = std.collections.vec\n"
        "main = () i32 {\n"
        "  m := Malloc(_: 0)\n"
        "  v0 := m.addr().vec_of([1])\n"
        f"{pushes}"
        f"  {gets}\n"
        "}\n"
    )
    # 1+2+3+4+5+6 = 21
    assert subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True).returncode == 21


def test_zenc_run_vec_and_print_together():
    """THE payoff: a single program imports a COLLECTION (std.collections.vec) AND formatted output (std.text.fmt) and
    runs — the v-prefixed Vec verbs no longer clash with std.text.string's push/len in one flat namespace."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ vec_of, vpush, get } = std.collections.vec\n"
        "{ println_int } = std.text.fmt\n"
        "main = () i32 {\n"
        "  m := Malloc(_: 0)\n"
        "  v := m.addr().vec_of([10, 20])\n"
        "  v2 := m.addr().vpush(v, 30)\n"
        "  println_int(v2.get(0))\n"              # 10
        "  println_int(v2.get(2))\n"              # 30
        "  0\n"
        "}\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "10\n30\n", repr(r.stdout)


def test_zenc_run_string_explicit_allocator_and_result():
    """String has the same allocator story as Vec: explicit MutPtr<A> variants, plus Result-returning
    allocation checks for code that wants errors as values instead of raw NULL."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ default_allocator } = std.mem.alloc\n"
        "{ new_in, append_in, free_in, try_with_cap, try_append } = std.text.string\n"
        "main = () i32 {\n"
        "  m := default_allocator()\n"
        "  s := m.addr().new_in()\n"
        "  s = m.addr().append_in(s, \"abc\")\n"
        "  n := s.len\n"
        "  m.addr().free_in(s)\n"
        "  m.addr().try_with_cap(2).match({\n"
        "    .Ok(t0) => m.addr().try_append(t0, \"hello\").match({\n"
        "      .Ok(t)  => { tn := t.len  m.addr().free_in(t)  to_i32(n + tn) },\n"
        "      .Err(e) => 90\n"
        "    }),\n"
        "    .Err(e) => 91\n"
        "  })\n"
        "}\n"
    )
    assert subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True).returncode == 8


# ── CAPSTONE: a real program (examples/stats.zen) composing Vec + generics + enums + match + fmt ──────
def test_zenc_run_capstone_stats_example():
    """The Goal-U proof: examples/stats.zen — list statistics (sum/max/even-count) over a Vec<i32> with an
    explicit allocator, enum-dispatched via .match, printed via std.text.fmt — builds and runs end to end."""
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


def test_zenc_emit_switches_enum_matches_but_keeps_bool_ternary():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "enum.zen").write_text(
        "R*: Ok(i32) | Err\n"
        "f* = (r: R) i32 { r.match({ .Ok(v) => v + 1, .Err => 0 }) }\n"
    )
    r = subprocess.run([zenc, "emit", str(d / "enum.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "switch (_subj.tag)" in r.stdout
    assert "case R_Ok:" in r.stdout

    (d / "bool.zen").write_text("f* = (b: bool) i32 { b.match({ true => 1, false => 0 }) }\n")
    r = subprocess.run([zenc, "emit", str(d / "bool.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "return (b ? 1 : 0);" in r.stdout
    assert "switch" not in r.stdout

    (d / "run.zen").write_text(
        "R*: Ok(i32) | Err\n"
        "f = (r: R) i32 { r.match({ .Ok(v) => { x := v + 1  x }, .Err => 0 }) }\n"
        "main = () i32 { (f(.Ok(6)) == 7).match({ true => 0, false => 1 }) }\n"
    )
    r = subprocess.run([zenc, "run", str(d / "run.zen")], capture_output=True, text=True)
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
        "{ println_int } = std.text.fmt\n"
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
    (d / "p.zen").write_text('{ len } = std.text.str\nmain = () i32 { n := len("hello")  to_i32(n) }\n')
    assert subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True).returncode == 5
    (d / "q.zen").write_text("main = () i32 { big := 4294967298  to_i32(big) }\n")   # 2^32+2 truncates to 2
    assert subprocess.run([zenc, "run", str(d / "q.zen")], capture_output=True).returncode == 2


def test_zenc_raw_intrinsics_have_at_spelling():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ println_int } = std.text.fmt\n"
        "main = () i32 { x := 41  p := @addr(x)  println_int(@load(p) + 1)  0 }\n")
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "42\n"
    (d / "bad.zen").write_text("main = () i32 { p := @malloc(8)  0 }\n")
    r = subprocess.run([zenc, "check", str(d / "bad.zen")], capture_output=True, text=True)
    assert r.returncode == 1
    assert "undefined name" in r.stderr


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
    assert {"hello", "shapes", "stats", "actor_demo"} <= set(names)
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
            "{ println_int } = std.text.fmt\n"
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
    at '<'), so std.mem.own + std.text.fmt co-import died on "duplicate top-level". Now dedup sees them."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text("{ println_int } = std.text.fmt\n{ Own } = std.mem.own\nmain = () i32 { println_int(7)  0 }\n")
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout == "7\n", (r.returncode, r.stdout, r.stderr)
# ── std.text.str search/slice/parse: find/contains/substr/parse_int/starts_with/char_at ───────────────────
def test_zenc_run_str_ops_edges():
    """The new std.text.str ops, hammered on edges: find at head/end/absent/empty-needle, substr CLAMPS
    out-of-range (start and n, both directions), char_at is 0 past either end, parse_int handles
    '-'/garbage-tail/all-garbage/empty (documented: no leading digits → 0) and i64-sized values."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        '{ find, contains, substr, parse_int, starts_with, char_at, eq, len } = std.text.str\n'
        '{ println_int } = std.text.fmt\n'
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
        '{ find, substr, parse_int, len } = std.text.str\n'
        '{ println, println_int } = std.text.fmt\n'
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



# ── std.collections.map: a str-keyed Map<T> with an EXPLICIT allocator (parallel str/T buffers, linear scan) ─────
def test_zenc_run_map_wordfreq():
    """THE std.collections.map acceptance: word-frequency counting via the mget+1-then-mput idiom — exercises
    put/get/overwrite-upsert/has/miss-default/len AND growth (cap 1 -> 3 -> 7 across 5 distinct keys).
    The counting idiom is also the regression guard for the by-name-arg use-after-free: the value arg
    `m.mget(w, 0) + 1` must be evaluated BEFORE mput's grow resizes the buffers (mappend force-binds)."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        '{ map_new, mput, mget, mhas, mlen, free_map } = std.collections.map\n'
        '{ println_int } = std.text.fmt\n'
        'bump = (a: MutPtr<Malloc>, m: Map<i32>, w: str) Map<i32> { a.mput(m, w, m.mget(w, 0) + 1) }\n'
        'main = () i32 {\n'
        '    m := Malloc(_: 0)\n'
        '    a := m.addr()\n'
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
        '{ map_new, mput, mget, mlen, free_map } = std.collections.map\n'
        '{ println, println_int } = std.text.fmt\n'
        'main = () i32 {\n'
        '    m := Malloc(_: 0)\n'
        '    a := m.addr()\n'
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


def test_zenc_run_map_try_result_paths():
    """Fallible map allocation returns Result errors; failed growth leaves the old map valid."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        '{ Allocator, default_allocator, malloc, free } = std.mem.alloc\n'
        '{ Result, IoError } = std.core.result\n'
        '{ try_map_new, try_mput, mget, free_map } = std.collections.map\n'
        'LimitAlloc: { left: i32 }\n'
        'LimitAlloc.impl(Allocator, {\n'
        '    acquire = (a: MutPtr<LimitAlloc>, n: i64) RawPtr<u8> {\n'
        '        (a.left > 0).match ({\n'
        '            true => {\n'
        '                a.left = a.left - 1\n'
        '                malloc(n)\n'
        '            },\n'
        '            false => null_ptr()\n'
        '        })\n'
        '    }\n'
        '    resize = (a: MutPtr<LimitAlloc>, p: RawPtr<u8>, n: i64) RawPtr<u8> { null_ptr() }\n'
        '    release = (a: MutPtr<LimitAlloc>, p: RawPtr<u8>) void { free(p) }\n'
        '})\n'
        'success = () i32 {\n'
        '    m := default_allocator()\n'
        '    a := m.addr()\n'
        '    r0: Result<Map<i32>, IoError> := a.try_map_new("x", 1)\n'
        '    r0.match ({\n'
        '        .Ok(w0) => {\n'
        '            r1: Result<Map<i32>, IoError> := a.try_mput(w0, "y", 2)\n'
        '            r1.match ({\n'
        '                .Ok(w) => {\n'
        '                    n := w.mget("x", 0) + w.mget("y", 0)\n'
        '                    a.free_map(w)\n'
        '                    n\n'
        '                },\n'
        '                .Err(e) => 90\n'
        '            })\n'
        '        },\n'
        '        .Err(e) => 91\n'
        '    })\n'
        '}\n'
        'failure = () i32 {\n'
        '    lim := LimitAlloc(left: 2)\n'
        '    a := lim.addr()\n'
        '    r0: Result<Map<i32>, IoError> := a.try_map_new("a", 4)\n'
        '    r0.match ({\n'
        '        .Ok(w) => {\n'
        '            r1: Result<Map<i32>, IoError> := a.try_mput(w, "b", 5)\n'
        '            r1.match ({\n'
        '                .Ok(w2) => {\n'
        '                    a.free_map(w2)\n'
        '                    80\n'
        '                },\n'
        '                .Err(e) => {\n'
        '                    n := w.mget("a", 0)\n'
        '                    a.free_map(w)\n'
        '                    n\n'
        '                }\n'
        '            })\n'
        '        },\n'
        '        .Err(e) => 81\n'
        '    })\n'
        '}\n'
        'main = () i32 {\n'
        '    n := success() + failure()\n'
        '    (n == 7).match ({ true => 0, false => n })\n'
        '}\n'
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ── colorless suspension: runtime.suspend no-ops outside a coroutine and yields inside one ──────────
def test_runtime_suspend_is_colorless():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "a.zen").write_text(
        "{ async_runtime } = std.concurrent.runtime\n{ println_int } = std.text.fmt\n"
        "main = () i32 { rt := async_runtime(1024)  rt.addr().suspend()  println_int(42)  rt.addr().suspend()  0 }\n")
    r = subprocess.run([zenc, "run", str(d / "a.zen")], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout == "42\n", (r.returncode, r.stdout, r.stderr)   # was SIGSEGV
    (d / "b.zen").write_text(
        "{ default_allocator } = std.mem.alloc\n{ spawn_in, resume, destroy_in } = std.concurrent.coroutine\n{ async_runtime } = std.concurrent.runtime\n{ println_int } = std.text.fmt\n"
        "work = () void { rt := async_runtime(1024)  println_int(1)  rt.addr().suspend()  println_int(3) }\n"
        "main = () i32 { alloc := default_allocator()  co := alloc.addr().spawn_in(work)  resume(co)  println_int(2)  resume(co)  alloc.addr().destroy_in(co)  0 }\n")
    r = subprocess.run([zenc, "run", str(d / "b.zen")], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout == "1\n2\n3\n", (r.returncode, r.stdout, r.stderr)
