"""Phase 2 — surface operators: `!=` and prefix `-`, through the self-hosted toolchain.

Each program is compiled by the self-hosted toolchain (parse_module -> resolve_module ->
genModule); the emitted C is compiled with a `main` checking `test()` and run.
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
    (tmp_path / "g.c").write_text("#include <stdint.h>\n#include <stdbool.h>\n" + _HEAD + "\n" + body
                                  + "\nint main(void){ return test() == %d ? 0 : 1; }\n" % want)
    assert subprocess.run(["cc", "-std=gnu11", "-w", str(tmp_path / "g.c"), "-o", str(tmp_path / "g")],
                          capture_output=True, text=True).returncode == 0
    assert subprocess.run([str(tmp_path / "g")]).returncode == 0, f"{prog!r} should give {want}"


@pytest.mark.parametrize("prog,want", [
    # != comparison (yields bool, matched to an int here)
    ("test* = () i32 { (5 != 3).match({ true => 1, false => 0 }) }", 1),
    ("test* = () i32 { (5 != 5).match({ true => 1, false => 0 }) }", 0),
    ("test* = () i32 { (7 != 7).match({ true => 1, false => 0 }) + (1 != 2).match({ true => 10, false => 0 }) }", 10),
    # prefix negation, lowered as (0 - x)
    ("test* = () i32 { -5 + 8 }", 3),
    ("test* = () i32 { -3 * 4 }", -12),          # unary binds tighter than *
    ("test* = () i32 { x := 5\n 0 - -x }", 5),   # binary minus then unary minus
    # negation applied to a call result
    ("neg* = (n: i32) i32 { 0 - n }\ntest* = () i32 { -neg(7) }", 7),
])
def test_operator_runs(tmp_path, prog, want):
    _run(tmp_path, prog, want)


@pytest.mark.parametrize("prog,want", [
    # a multi-statement match arm `{ … }` (a genc Block / statement-expression)
    ("test* = () i32 { (3 < 5).match({ true => { x := 10\n y := 20\n x + y }, false => 0 }) }", 30),
    # one single-expr arm, one block arm
    ("classify* = (n: i32) i32 { (n < 0).match({ true => { 0 - n }, false => { d := n * 2\n d + 1 } }) }\n"
     "test* = () i32 { classify(5) }", 11),
    # a variant arm whose block uses the payload binding `r`
    ("Shape*: Circle(i32) | Square(i32)\n"
     "area* = (s: Shape) i32 { s.match({ .Circle(r) => { rr := r * r\n rr * 3 }, .Square(w) => w * w }) }\n"
     "test* = () i32 { area(.Circle(2)) }", 12),
])
def test_multi_statement_match_arm_runs(tmp_path, prog, want):
    _run(tmp_path, prog, want)
