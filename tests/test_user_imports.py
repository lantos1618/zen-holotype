"""USER MULTI-FILE IMPORTS (Goal R, #1 outsider blocker): `{ helper } = b` loads b.zen from the
importing program's OWN directory — a SIBLING file — through the same std.resolve loader that handles
`{ … } = std.X` (transitive closure, per-module dedup/cycle break, per-name dedup).

Before this, a sibling import TYPECHECKED (the checker trusts DImport names) and then died in raw
linker spew (`undefined reference to 'helper'`). The point of the feature is the error quality as much
as the loading: unknown module / unknown imported name / cross-sibling duplicate / sibling-from-stdin
all print one `zenc: <file>: error: …` line (the loader writes stderr and exits 1 itself — the C
driver adds nothing).
"""
import subprocess
import tempfile
from pathlib import Path

import _oracle

ROOT = _oracle.ROOT


def _zenc():
    """The repo's make-built zenc (beside ROOT/bootstrap, so it can find zen/std + zenrt.{c,h})."""
    subprocess.run(["make", "-f", "bootstrap/Makefile", "zenc"], cwd=str(ROOT),
                   check=True, capture_output=True)
    return str(ROOT / "zenc")


def _program(files):
    """Write {name: source} into a fresh dir; returns the dir."""
    d = Path(tempfile.mkdtemp())
    for name, src in files.items():
        (d / name).write_text(src)
    return d


# ── the feature: a bare module name imports a sibling file ───────────────────────────────────────
def test_sibling_import_builds_and_runs():
    d = _program({
        "b.zen": "helper* = (x: i32) i32 { x * 2 }\n",
        "p.zen": "{ helper } = b\nmain = () i32 { helper(21) }\n",
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 42, r.stderr


def test_sibling_helper_importing_std_is_transitive():
    """b.zen's own `{ println } = std.fmt` edge is loaded into the same closure."""
    d = _program({
        "h.zen": '{ println } = std.fmt\nshout* = (s: str) i64 { println(s) }\n',
        "p.zen": '{ shout } = h\nmain = () i32 { shout("from helper") 0 }\n',
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "from helper\n"


def test_two_sibling_modules():
    d = _program({
        "m1.zen": "one* = () i32 { 1 }\n",
        "m2.zen": "two* = () i32 { 2 }\n",
        "p.zen": "{ one } = m1\n{ two } = m2\nmain = () i32 { one() + two() }\n",
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 3, r.stderr


def test_sibling_import_cycle_terminates_and_runs():
    """a imports b imports a: the per-module seen-set breaks the cycle — each body emitted once."""
    d = _program({
        "aa.zen": "{ g } = bb\nf* = (n: i32) i32 { (n <= 0).match ({ true => 0, false => g(n - 1) + 1 }) }\n",
        "bb.zen": "{ f } = aa\ng* = (n: i32) i32 { (n <= 0).match ({ true => 0, false => f(n - 1) + 1 }) }\n",
        "p.zen": "{ f } = aa\nmain = () i32 { f(7) }\n",
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 7, r.stderr


# ── error quality (the point): loader errors, not linker spew ────────────────────────────────────
def test_unknown_module_is_a_loader_error_not_linker_spew():
    d = _program({"p.zen": "{ f } = nosuch\nmain = () i32 { f() }\n"})
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 1
    assert r.stderr == f"zenc: {d}/p.zen: error: unknown module 'nosuch' (no nosuch.zen next to {d}/p.zen)\n"
    assert "undefined reference" not in r.stderr


def test_unknown_name_in_sibling_module_names_both():
    d = _program({
        "b.zen": "helper* = (x: i32) i32 { x }\n",
        "p.zen": "{ nope } = b\nmain = () i32 { 0 }\n",
    })
    r = subprocess.run([_zenc(), "check", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 1
    assert r.stderr == f"zenc: {d}/p.zen: error: unknown name 'nope' in module 'b' (no such top-level definition)\n"


def test_unknown_name_validation_covers_std_imports_too():
    d = _program({"p.zen": "{ nosuchname } = std.fmt\nmain = () i32 { 0 }\n"})
    r = subprocess.run([_zenc(), "check", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 1
    assert "unknown name 'nosuchname' in module 'std.fmt'" in r.stderr


def test_unknown_std_module_is_clean_too():
    d = _program({"p.zen": "{ x } = std.nosuchmod\nmain = () i32 { 0 }\n"})
    r = subprocess.run([_zenc(), "check", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 1
    assert "unknown module 'std.nosuchmod'" in r.stderr


def test_name_collision_between_sibling_modules_is_rejected():
    """std-vs-std keeps the silent first-wins dedup; two USER files defining the same name reject."""
    d = _program({
        "c1.zen": "dupf* = () i32 { 1 }\n",
        "c2.zen": "dupf* = () i32 { 2 }\n",
        "p.zen": "{ dupf } = c1\n{ dupf } = c2\nmain = () i32 { dupf() }\n",
    })
    r = subprocess.run([_zenc(), "check", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 1
    assert "duplicate top-level definition 'dupf'" in r.stderr
    assert "'c2'" in r.stderr                      # the redefining module is named


def test_main_redefining_an_imported_sibling_name_is_rejected():
    """the existing dedup rule: a name BOTH imported and defined by the main file reaches the
    validator as a duplicate (silent shadowing was a miscompile trap)."""
    d = _program({
        "b.zen": "helper* = (x: i32) i32 { x }\n",
        "p.zen": "{ helper } = b\nhelper = (x: i32) i32 { x + 1 }\nmain = () i32 { helper(1) }\n",
    })
    r = subprocess.run([_zenc(), "check", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 1
    assert "duplicate top-level definition" in r.stderr


# ── stdin mode: no program directory ─────────────────────────────────────────────────────────────
def test_stdin_sibling_import_errors_cleanly():
    """`cat prog.zen | zenc` has no directory to resolve a sibling from — clean error, not garbage C."""
    src = "{ helper } = b\nmain = () i32 { helper(21) }\n"
    r = subprocess.run([_zenc()], input=src, capture_output=True, text=True)
    assert r.returncode == 1
    assert "sibling import 'b'" in r.stderr
    assert "stdin" in r.stderr
    assert r.stdout == ""                          # no half-emitted C


def test_stdin_without_sibling_imports_stays_the_classic_filter():
    """the oracle's source→C filter mode is untouched for import-free source."""
    r = subprocess.run([_zenc()], input="main = () i32 { 6 * 7 }\n", capture_output=True, text=True)
    assert r.returncode == 0
    assert "int32_t main(" in r.stdout
