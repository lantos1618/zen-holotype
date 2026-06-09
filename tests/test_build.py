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
    r = subprocess.run([zenc, "build", "/no/such/file.zen", "-o", "/tmp/x"], capture_output=True, text=True)
    assert r.returncode != 0  # clean failure, not a crash


def test_zenc_check_rejects_undefined_name():
    """U1.2: the binary now type-checks — the killer case (undefined name was emit-exit-0)."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text("main = () i32 { undefined_fn(1, 2) }\n")
    r = subprocess.run([zenc, "check", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode != 0 and "undefined-name" in r.stderr, r.stderr


def test_zenc_check_reports_error_count_and_first_kind():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    src = d / "p.zen"
    src.write_text("main = () i32 { undefined_fn(1, 2) }\n")
    r = subprocess.run([zenc, "check", str(src)], capture_output=True, text=True)
    assert r.returncode == 1
    assert r.stderr == f"zenc: {src}: 1 error (first: undefined-name)\n"


def test_zenc_check_rejects_source_if():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text("main = () i32 { if (1 < 2) { return 9 } 7 }\n")
    r = subprocess.run([zenc, "check", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode != 0 and "undefined-name" in r.stderr, r.stderr


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
    assert r.returncode != 0 and "undefined-name" in r.stderr, r.stderr


def test_zenc_check_rejects_undefined_name_in_arg_position():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text("id = (n: i32) i32 { n }\nmain = () i32 { id(undefined_thing) }\n")
    r = subprocess.run([zenc, "check", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode != 0 and "undefined-name" in r.stderr, r.stderr


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
