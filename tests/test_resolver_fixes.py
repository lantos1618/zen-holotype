"""The resolver triple-fix, acceptance-tested through the BINARY (the empirical census's 8 bullets).

Three localized zen/std/resolve.zen bugs broke whole regions of the stdlib import surface:
  1. GENERIC HEADS INVISIBLE TO DEDUP — after_name_is_decl bailed at '<', so `new<T> = …` was never
     recorded/deduped: any two modules sharing a generic-decl dep died on "duplicate top-level
     definition" (fmt+rc, vec+rc, fmt+arc, fmt+drop; std.c / std.cown alone).
  2. NS-BIND DEAD — `c = std.c` loaded the bound module's closure into the dedup region that is
     always kept (the main-file region started at 0, ns bodies sit before the main body), so the
     closure never deduped → duplicate-toplevel.
  3. LINE-BASED SCAN vs MULTI-LINE CONSTRUCTS — std.ast's 5-line `{ … } = compiler.genc` import
     wasn't recognized (lines leaked into the flat source), and a multi-line `Type.impl(Trait, {…})`
     body with column-0 method lines (std.runtime's `suspend = …`) had its SECOND `suspend` line
     silently deduped away as a "duplicate decl" → "impl does not satisfy the trait".
Residue of the same census: std.c/std.ast redefined `dup`/`eq`, names std.str (in their own flat
closure via compiler.genc) already owns — per-name first-wins dedup kept the str ones and broke
every call site; the builders now carry std.ast's x-suffix dodge (`dupx`/`eqx`, like `callx`).
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
    pytest.param("{ println } = std.fmt\n{ rc_val } = std.rc\n", id="fmt+rc"),
    pytest.param("{ vec_of } = std.vec\n{ rc_val } = std.rc\n", id="vec+rc"),
    pytest.param("{ println } = std.fmt\n{ arc_val } = std.arc\n", id="fmt+arc"),
    pytest.param("{ println } = std.fmt\n{ own_get } = std.drop\n", id="fmt+drop"),
])
def test_generic_decl_co_imports_check_ok(imports):
    r = _check(imports + "main = () i32 { 0 }\n")
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("imports", [
    pytest.param("{ libc } = std.c\n", id="std.c"),
    pytest.param("{ buf_alloc } = std.cown\n", id="std.cown"),
])
def test_generic_heavy_module_alone_checks_ok(imports):
    r = _check(imports + "main = () i32 { 0 }\n")
    assert r.returncode == 0, r.stderr


# ── bug 2: namespace bind `c = std.c` + qualified access compiles AND runs ───────────────────────────
def test_ns_bind_qualified_call_runs():
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "c = std.c\n"
        "main = () i32 {\n"
        "    p := c.malloc(8)\n"
        "    store_i64(p, 37)\n"
        "    (load_i64(p) == 37).match ({ true => 37, false => 0 })\n"
        "}\n")
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 37, r.stderr


# ── bug 3: multi-line imports (std.ast) and multi-line impl bodies (std.runtime) ─────────────────────
def test_std_runtime_imports_clean():
    """The two Runtime impls both hold a column-0 `suspend = …` METHOD line; the line-based dedup
    used to treat the second as a duplicate top-level decl and silently drop it — the flattened
    AsyncRuntime impl then lacked `suspend` ("impl does not satisfy the trait")."""
    r = _check("{ sync_runtime } = std.runtime\nmain = () i32 { 0 }\n")
    assert r.returncode == 0, r.stderr


def test_std_ast_imports_clean():
    """std.ast's import of compiler.genc spans 5 lines; the line-local import scan missed it, leaked
    the continuation lines into the flat source, and lost the imported types (unknown type 'Expr')."""
    r = _check("{ var } = std.ast\nmain = () i32 { 0 }\n")
    assert r.returncode == 0, r.stderr


def test_user_shadow_of_imported_std_name_is_an_error():
    """A program decl that collides with a name in its imported std closure used to be a SILENT
    shadow (the std decl was deduped away — so the std module's own internal calls rebound to the
    user's decl, a miscompile trap). The decl-span dedup keeps both and the validator rejects."""
    r = _check("{ println } = std.fmt\n"
               "eq = (a: i32, b: i32) bool { a == b }\n"   # std.str (in fmt's closure) owns `eq`
               "main = () i32 { 0 }\n")
    assert r.returncode != 0
    assert "duplicate top-level definition" in r.stderr


def test_import_vs_import_collision_still_first_wins():
    """Two IMPORTED modules sharing a name (std.string `free(String)` vs std.mem `free(RawPtr)`)
    still dedup silently — dependency-first, the defining module wins; no false dup error."""
    r = _check("{ String, with_cap, finish } = std.string\nmain = () i32 { 0 }\n")
    assert r.returncode == 0, r.stderr


def test_std_ast_builders_usable():
    """Beyond importing: the renamed builders (dupx/eqx — the std.str collision dodge) actually run."""
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ var, dot, eqx } = std.ast\n"
        "main = () i32 {\n"
        '    e := var("x").dot("a").eqx(var("y").dot("a"))\n'
        "    0\n"
        "}\n")
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
