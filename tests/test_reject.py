"""Phase 6 — reject-parity: the self-hosted checker (check_module) catches errors, not just
accepts valid code. Toward "same accept/reject as the Python frontend".

Each program is run through parse_module -> resolve_module -> check_module; the error count is
the process exit code. Valid programs give 0; the listed bugs give >= 1.

Scope today: call ARITY, arg-TYPE fit (categorical), and RETURN-type category mismatches
(str/bool/struct returned where another category is declared). Numeric->numeric narrowing on
returns is intentionally skipped — int literals are polymorphic and the checker can't track
literal-ness through a Cond, so flagging it would false-reject valid code like `(…) u8 { 10 }`.
"""
import subprocess

import pytest

from zen.main import (load, build_namespace, build_scopes, resolve,
                      fold_comptime, run_emits, check, emit_c)

_DRIVER = """
{ Malloc } = std.alloc
{ parse_module } = std.parse
{ resolve_module, check_module } = std.check
main* = () i32 {
    m := Malloc { _: 0 }
    addr(m).check_module(addr(m).resolve_module(addr(m).parse_module("%s")))
}
"""


def _zlit(s):
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _errors(tmp_path, src):
    (tmp_path / "main.zen").write_text(_DRIVER % _zlit(src))
    files = load(tmp_path); ns = build_namespace(files)
    build_scopes(files); resolve(files, ns)
    fold_comptime(files, ns); run_emits(files, ns)
    _, passing = check(files, ns)
    c = emit_c(files, passing, ns, roots={"main.main"})
    (tmp_path / "o.c").write_text(c + "\nint main(void){ return main_main(); }\n")
    assert subprocess.run(["cc", "-std=gnu11", str(tmp_path / "o.c"), "-o", str(tmp_path / "o")],
                          capture_output=True, text=True).returncode == 0
    return subprocess.run([str(tmp_path / "o")]).returncode


@pytest.mark.parametrize("src", [
    "f* = (n: i32) i32 { n + 1 }",
    "f* = (a: i32, b: i32) bool { a < b }",
    "g* = (n: i32) u8 { 10 }",                       # int literal -> u8 is fine (polymorphic)
    "id* = (s: str) str { s }",
    "Pt*: { x: i32 }\nf* = (p: Pt) i32 { p.x }",
])
def test_checker_accepts_valid(tmp_path, src):
    assert _errors(tmp_path, src) == 0


@pytest.mark.parametrize("src", [
    'f* = (n: i32) i32 { "hi" }',                    # str returned where i32 declared
    "f* = (n: i32) i32 { n < 5 }",                   # bool returned where i32 declared
    "f* = (n: i32) str { n }",                       # i32 returned where str declared
    "f* = (a: i32) i32 { a }\ng* = () i32 { f(1, 2) }",   # arity: f takes 1, called with 2
])
def test_checker_rejects_invalid(tmp_path, src):
    assert _errors(tmp_path, src) >= 1
