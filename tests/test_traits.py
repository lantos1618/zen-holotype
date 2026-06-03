"""Phase 4 — impl blocks (and pointer field auto-deref), through the self-hosted toolchain.

`Type.impl(Trait) { m = (s: Ptr<Type>, …) R { … } }` — the methods become ordinary top-level
functions named by the method, so a UFCS call `x.m(a)` (which the parser desugars to `m(x, a)`)
resolves to one. A method's `s.field` on a `Ptr<Type>` receiver auto-derefs to `s->field`.
"""
import subprocess

import pytest

from zen.main import (load, build_namespace, build_scopes, resolve,
                      fold_comptime, run_emits, check, emit_c)

_DRIVER = """
{ Malloc } = std.alloc
{ parse_module } = std.parse
{ resolve_module } = std.check
{ genModule } = std.genc
{ String, new, bytes } = std.string
putchar = (c: i32) i32
emit = (s: String) void { bytes(s).loop((h, i, b) { putchar(b) }) }
main* = () i32 {
    m := Malloc { _: 0 }
    emit(genModule(addr(m).resolve_module(addr(m).parse_module("%s"))))
    0
}
"""
_HEAD = "typedef struct { void* ptr; int64_t len; } zslice; "


def _zlit(s):
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _run(tmp_path, prog, want):
    (tmp_path / "main.zen").write_text(_DRIVER % _zlit(prog))
    files = load(tmp_path); ns = build_namespace(files)
    build_scopes(files); resolve(files, ns)
    fold_comptime(files, ns); run_emits(files, ns)
    _, passing = check(files, ns)
    c = emit_c(files, passing, ns, roots={"main.main"})
    (tmp_path / "o.c").write_text(c + "\nint main(void){ return main_main(); }\n")
    assert subprocess.run(["cc", "-std=gnu11", str(tmp_path / "o.c"), "-o", str(tmp_path / "o")],
                          capture_output=True, text=True).returncode == 0
    emitted = subprocess.run([str(tmp_path / "o")], capture_output=True, text=True).stdout
    body = emitted[len(_HEAD):] if emitted.startswith(_HEAD) else emitted
    (tmp_path / "g.c").write_text("#include <stdint.h>\n" + _HEAD + "\n" + body
                                  + "\nint main(void){ return test() == %d ? 0 : 1; }\n" % want)
    assert subprocess.run(["cc", "-std=gnu11", "-w", str(tmp_path / "g.c"), "-o", str(tmp_path / "g")],
                          capture_output=True, text=True).returncode == 0
    assert subprocess.run([str(tmp_path / "g")]).returncode == 0, f"{prog!r} should give {want}"


@pytest.mark.parametrize("prog,want", [
    # one impl method, called via UFCS; field access on the Ptr receiver auto-derefs
    ("Point*: { x: i32, y: i32 }\n"
     "Point.impl(Show) { sumk = (p: Ptr<Point>, k: i32) i32 { p.x + p.y + k } }\n"
     "test* = () i32 { p := Point { x: 3, y: 4 }\n p.addr().sumk(10) }", 17),
    # two methods in one impl block
    ("Counter*: { n: i32 }\n"
     "Counter.impl(Inc) { bump = (c: Ptr<Counter>) i32 { c.n + 1 }  get = (c: Ptr<Counter>) i32 { c.n } }\n"
     "test* = () i32 { c := Counter { n: 41 }\n c.addr().bump() }", 42),
    # an impl method that chains another UFCS call
    ("Box*: { v: i32 }\n"
     "Box.impl(B) { val = (b: Ptr<Box>) i32 { b.v }  twice = (b: Ptr<Box>) i32 { b.val() + b.val() } }\n"
     "test* = () i32 { b := Box { v: 21 }\n b.addr().twice() }", 42),
])
def test_impl_method_runs(tmp_path, prog, want):
    _run(tmp_path, prog, want)


@pytest.mark.parametrize("prog,want", [
    # a DECLARED trait (`Show*: { render: (Ptr<Self>) R }`) — parses but is skipped from codegen
    # (no runtime form); the impl provides the method, called via UFCS.
    ("Show*: { render: (Ptr<Self>) i32 }\n"
     "Point*: { x: i32, y: i32 }\n"
     "Point.impl(Show) { render = (p: Ptr<Point>) i32 { p.x * 10 + p.y } }\n"
     "test* = () i32 { p := Point { x: 4, y: 2 }\n p.addr().render() }", 42),
])
def test_declared_trait_with_impl_runs(tmp_path, prog, want):
    _run(tmp_path, prog, want)


# Trait conformance: an impl must DEFINE every method its trait declares. The check is tied to the
# impl's OWN methods (recorded in DImpl), not a global function search — so an unrelated same-named
# function elsewhere does NOT make a deficient impl conform.
def _check_errors(tmp_path, prog):
    drv = _DRIVER.replace("{ resolve_module } = std.check",
                          "{ resolve_module, check_module } = std.check").replace(
        "emit(genModule(addr(m).resolve_module(addr(m).parse_module(\"%s\"))))\n    0",
        "addr(m).check_module(addr(m).resolve_module(addr(m).parse_module(\"%s\")))")
    (tmp_path / "main.zen").write_text(drv % _zlit(prog))
    files = load(tmp_path); ns = build_namespace(files)
    build_scopes(files); resolve(files, ns)
    fold_comptime(files, ns); run_emits(files, ns)
    _, passing = check(files, ns)
    c = emit_c(files, passing, ns, roots={"main.main"})
    (tmp_path / "o.c").write_text(c + "\nint main(void){ return main_main(); }\n")
    assert subprocess.run(["cc", "-std=gnu11", str(tmp_path / "o.c"), "-o", str(tmp_path / "o")],
                          capture_output=True, text=True).returncode == 0
    return subprocess.run([str(tmp_path / "o")]).returncode


def test_conformance_accepts_complete_impl(tmp_path):
    assert _check_errors(tmp_path,
        "Show*: { render: (Ptr<Self>) i32, area: (Ptr<Self>) i32 }\nPoint*: { x: i32 }\n"
        "Point.impl(Show) { render = (p: Ptr<Point>) i32 { p.x }  area = (p: Ptr<Point>) i32 { p.x } }") == 0


def test_conformance_rejects_missing_method(tmp_path):
    assert _check_errors(tmp_path,
        "Show*: { render: (Ptr<Self>) i32, area: (Ptr<Self>) i32 }\nPoint*: { x: i32 }\n"
        "Point.impl(Show) { render = (p: Ptr<Point>) i32 { p.x } }") == 1


def test_conformance_unrelated_global_does_not_satisfy(tmp_path):
    # a top-level `area` exists, but Point's impl doesn't DEFINE area -> still non-conforming
    assert _check_errors(tmp_path,
        "Show*: { render: (Ptr<Self>) i32, area: (Ptr<Self>) i32 }\nPoint*: { x: i32 }\n"
        "area* = (n: i32) i32 { n }\n"
        "Point.impl(Show) { render = (p: Ptr<Point>) i32 { p.x } }") == 1
