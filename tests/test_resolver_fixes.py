"""The resolver triple-fix, acceptance-tested through the BINARY (the empirical census's 8 bullets).

Three localized zen/std/internal/resolve.zen bugs broke whole regions of the stdlib import surface:
  1. GENERIC HEADS INVISIBLE TO DEDUP — after_name_is_decl bailed at '<', so `new<T> = …` was never
     recorded/deduped: any two modules sharing a generic-decl dep died on "duplicate top-level
     definition" (fmt+rc, vec+rc, fmt+arc, fmt+drop; std.io.c / std.concurrent.cown alone).
  2. NS-BIND DEAD — `c = std.io.c` loaded the bound module's closure into the dedup region that is
     always kept (the main-file region started at 0, ns bodies sit before the main body), so the
     closure never deduped → duplicate-toplevel.
  3. LINE-BASED SCAN vs MULTI-LINE CONSTRUCTS — std.internal.ast's 5-line `{ … } = compiler.genc` import
     wasn't recognized (lines leaked into the flat source), and a multi-line `Type.impl(Trait, {…})`
     body with column-0 method lines (std.concurrent.runtime's `checkpoint = …`) had its SECOND `checkpoint` line
     silently deduped away as a "duplicate decl" → "impl does not satisfy the trait".
Residue of the same census: std.io.c/std.internal.ast redefined `dup`/`eq`, names std.text.str (in their own flat
closure via compiler.genc) already owns — per-name first-wins dedup kept the str ones and broke
every call site; the builders now carry std.internal.ast's x-suffix dodge (`dupx`/`eqx`, like `callx`).
"""
import subprocess
import tempfile
from pathlib import Path

import pytest

import _oracle

ROOT = _oracle.ROOT


def _zenc():
    """The repo's make-built zenc (beside ROOT/bootstrap, so it can find zen/std + zenrt.{c,h})."""
    subprocess.run(["make", "-f", "bootstrap/Makefile", "zenc"], cwd=str(ROOT),
                   check=True, capture_output=True)
    return str(ROOT / "zenc")


def _check(src):
    """`zenc check` on a temp program; returns the CompletedProcess."""
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(src)
    return subprocess.run([_zenc(), "check", str(d / "p.zen")], capture_output=True, text=True)


# ── bug 1: co-imports whose closures share generic decls (`new<T>`, `release<T>*`, `dup<T>`) ─────────
@pytest.mark.parametrize("imports", [
    pytest.param("{ println } = std.text.fmt\n{ Rc } = std.mem.rc\n", id="fmt+rc"),
    pytest.param("vec = std.collections.vec\n{ Rc } = std.mem.rc\n", id="vec+rc"),
    pytest.param("{ println } = std.text.fmt\n{ Arc } = std.mem.arc\n", id="fmt+arc"),
    pytest.param("{ println } = std.text.fmt\n{ Own } = std.mem.own\n", id="fmt+drop"),
])
def test_generic_decl_co_imports_check_ok(imports):
    r = _check(imports + "main = () i32 { 0 }\n")
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("imports", [
    pytest.param("{ libc } = std.io.c\n", id="std.io.c"),
    pytest.param("cown = std.concurrent.cown\n", id="std.concurrent.cown"),
])
def test_generic_heavy_module_alone_checks_ok(imports):
    r = _check(imports + "main = () i32 { 0 }\n")
    assert r.returncode == 0, r.stderr


# ── bug 2: namespace bind `c = std.io.c` + qualified access compiles AND runs ───────────────────────────
def test_ns_bind_qualified_call_runs():
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "c = std.io.c\n"
        "main = () i32 {\n"
        "    p := c.malloc(8)\n"
        "    store_i64(p, 37)\n"
        "    (load_i64(p) == 37).match ({ true => 37, false => 0 })\n"
        "}\n")
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 37, r.stderr


# ── bug 3: multi-line imports (std.internal.ast) and multi-line impl bodies (std.concurrent.runtime) ─────────────────────
def test_std_runtime_imports_clean():
    """The two Runtime impls both hold a column-0 `checkpoint = …` METHOD line; the line-based dedup
        used to treat the second as a duplicate top-level decl and silently drop it — the flattened
        AsyncArena impl then lacked `checkpoint` ("impl does not satisfy the trait")."""
    r = _check("rt = std.concurrent.runtime\nmain = () i32 { 0 }\n")
    assert r.returncode == 0, r.stderr


def test_std_ast_imports_clean():
    """std.internal.ast's import of compiler.genc spans 5 lines; the line-local import scan missed it, leaked
    the continuation lines into the flat source, and lost the imported types (unknown type 'Expr')."""
    r = _check("{ var } = std.internal.ast\nmain = () i32 { 0 }\n")
    assert r.returncode == 0, r.stderr


def test_std_actor_standalone_check_does_not_treat_assignments_as_imports():
    """Indented body assignments like `sent = true` are code, not namespace imports of sibling module `true`."""
    r = subprocess.run([_zenc(), "check", str(ROOT / "zen/std/concurrent/actor.zen")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_std_actor_can_export_spawn_despite_coroutine_spawn_dependency():
    """std.concurrent.actor owns actor.spawn/try_spawn even though the coroutine substrate owns the same names."""
    zenc = _zenc()
    r = subprocess.run([zenc, "check", str(ROOT / "zen/std/concurrent/actor.zen")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    doc = subprocess.run([zenc, "doc", "std.concurrent.actor"], capture_output=True, text=True)
    assert doc.returncode == 0, doc.stderr
    assert "spawn*<A, M, ActorT>" in doc.stdout
    assert "try_spawn*<A, M, ActorT>" in doc.stdout


def test_user_shadow_of_imported_std_name_is_an_error():
    """A program decl that collides with a name in its imported std closure used to be a SILENT
    shadow (the std decl was deduped away — so the std module's own internal calls rebound to the
    user's decl, a miscompile trap). The decl-span dedup keeps both and the validator rejects."""
    r = _check("{ println } = std.text.fmt\n"
               "eq = (a: i32, b: i32) bool { a == b }\n"   # std.text.str (in fmt's closure) owns `eq`
               "main = () i32 { 0 }\n")
    assert r.returncode != 0
    assert "duplicate top-level definition" in r.stderr


def test_import_vs_import_collision_still_first_wins():
    """Two IMPORTED modules sharing a name (std.text.string `free(String)` vs std.mem.raw `free(RawPtr)`)
    still dedup silently — dependency-first, the defining module wins; no false dup error."""
    r = _check("{ String, new_in } = std.text.string\nmain = () i32 { 0 }\n")
    assert r.returncode == 0, r.stderr


def test_std_ast_builders_usable():
    """Beyond importing: the renamed builders (dupx/eqx — the std.text.str collision dodge) actually run."""
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ default } = std.mem.alloc\n"
        "{ var, dot, eqx } = std.internal.ast\n"
        "main = () i32 {\n"
        "    heap := default()\n"
        "    a := heap.addr()\n"
        '    e := eqx(a, dot(a, var(a, "x"), "a"), dot(a, var(a, "y"), "a"))\n'
        "    0\n"
        "}\n")
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_std_ast_decl_buffer_uses_explicit_allocator():
    """std.internal.ast should not own declaration buffers through raw malloc."""
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ Allocator, malloc, free } = std.mem.alloc\n"
        "{ to_exit } = std.core.bool\n"
        "{ derive_accessors_in } = std.internal.ast\n"
        "{ Decl, sdef, field, ti32 } = compiler.genc\n"
        "Counting: { acquired: i32, released: i32 }\n"
        "Counting.impl(Allocator, {\n"
        "    acquire = (a: MutPtr<Counting>, n: i64) RawPtr<u8> {\n"
        "        a.acquired = a.acquired + 1\n"
        "        malloc(n)\n"
        "    }\n"
        "    resize = (a: MutPtr<Counting>, p: RawPtr<u8>, n: i64) RawPtr<u8> { null_ptr() }\n"
        "    release = (a: MutPtr<Counting>, p: RawPtr<u8>) void {\n"
        "        a.released = a.released + 1\n"
        "        free(p)\n"
        "    }\n"
        "})\n"
        "main = () i32 {\n"
        "    backing := Counting(acquired: 0, released: 0)\n"
        "    a := backing.addr()\n"
        "    sd := sdef(\"Point\", [field(\"x\", ti32()), field(\"y\", ti32())])\n"
        "    ds: [Decl] := a.derive_accessors_in(sd)\n"
        "    ok := (backing.acquired > 1) && (ds.len == 2)\n"
        "    a.release(ds.ptr)\n"
        "    (ok && (backing.released == 1)).to_exit()\n"
        "}\n")
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ── RESOLVE-2: undefined type names in annotations are rejected (was: leaked to C as `unknown type
#    name 'X'` at cc time). Driver-only check (runs on the flattened decls), so it's exercised here
#    through the binary, not via the oracle corpus. ──────────────────────────────────────────────────
def test_undefined_type_in_annotation_rejected():
    r = _check("f = (m: MutPtr<TotallyUndefinedType>, n: i64) i64 { n }\nmain = () i32 { 0 }\n")
    assert r.returncode != 0 and "unknown-type" in r.stderr, r.stderr


def test_undefined_return_type_rejected():
    r = _check("f = () Nonexistent { 0 }\nmain = () i32 { 0 }\n")
    assert r.returncode != 0 and "unknown-type" in r.stderr, r.stderr


def test_defined_and_imported_types_not_flagged():
    # a user type, a tparam, and an imported std type must all pass (no false positive)
    src = ("{ println } = std.text.fmt\n"
           "alloc = std.mem.alloc\n"
           "Pt*: { x: i32 }\n"
           "idp<T> = (p: MutPtr<T>) MutPtr<T> { p }\n"
           "useit = (m: MutPtr<alloc.Heap>, q: MutPtr<Pt>) i32 { q.x }\n"
           "main = () i32 { 0 }\n")
    r = _check(src)
    assert r.returncode == 0, r.stderr


# ── LAMBDA-2: a local-bound lambda used as a call arg is lowered (alias-spliced) and compiles; a
#    lambda the inliner can't splice — stored in a field or returned — is rejected cleanly with
#    error[lambda-value] instead of leaking `zen__unlowered_lambda` into the C. ────────────────────────
def test_lambda_bound_local_used_as_hof_arg_ok():
    r = _check("apply = (f: (i32) i32, x: i32) i32 { f(x) }\n"
               "main = () i32 {\n  k := 10\n  g := (n) { n + k }\n  apply(g, 41)\n}\n")
    assert r.returncode == 0, r.stderr


def test_lambda_stored_in_field_rejected():
    r = _check("S*: { f: (i32) i32 }\nmain = () i32 {\n  s := S(f: (n) { n + 1 })\n  0\n}\n")
    assert r.returncode != 0 and "lambda-value" in r.stderr, r.stderr


def test_lambda_returned_rejected():
    r = _check("mk = () (i32) i32 { (n) { n + 1 } }\nmain = () i32 { 0 }\n")
    assert r.returncode != 0 and "lambda-value" in r.stderr, r.stderr
