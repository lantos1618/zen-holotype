"""The one iteration construct: `loop` (sugar) desugars onto the `@while`
primitive, which lowers to a structured C `for` — never gotos, so it stays
auto-vectorizable. `while` does not exist; `loop` and `@while` are the only forms."""
import subprocess
import pytest

from holotype.main import (load, build_space, build_scopes, resolve, check, emit_c)
from holotype.parser import parse


def build(tmp_path, src, entry="main"):
    (tmp_path / "m.zen").write_text(src)
    files = load(tmp_path)
    space = build_space(files)
    build_scopes(files)
    resolve(files, space)
    results, passing = check(files, space)
    c = emit_c(files, passing, space)
    return results, passing, c


def run(tmp_path, c, entry):
    cfile = tmp_path / "o.c"
    cfile.write_text(c + f"\nint main(void){{ return m_{entry}(); }}\n")
    # hardened: the emitted C must be warning-clean under -Wall -Wextra -Werror
    r = subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", str(cfile), "-o", str(tmp_path / "o")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return subprocess.run([str(tmp_path / "o")]).returncode


def test_count_loop_folds_to_a_for(tmp_path):
    results, passing, c = build(tmp_path, """
pub main = () i32 {
    s := 0
    loop(11, (h, i) { s = s + i })
    s
}
""")
    assert ("m.main", True, "ok") in results
    assert "for (; (i < 11); i = (i + 1)) {" in c          # a real, structured C for
    assert "while (" not in c                              # never a C `while`
    assert run(tmp_path, c, "main") == 55                  # 0+1+…+10


def test_iterless_loop_with_break(tmp_path):
    # loop((h){…}) is the while-replacement — handle-driven, breaks via h.break()
    results, passing, c = build(tmp_path, """
pub main = () i32 {
    r := 0
    loop((h) {
        r = r + 1
        match (r < 5) { true => h.continue(), false => h.break() }
    })
    r
}
""")
    assert ("m.main", True, "ok") in results
    assert "for (; true; ) {" in c                          # iterless -> for(;;)-style
    assert "break;" in c and "continue;" in c               # handle control as C statements
    assert run(tmp_path, c, "main") == 5


def test_at_while_primitive(tmp_path):
    results, passing, c = build(tmp_path, """
pub main = () i32 {
    n := 0
    @while(n < 5) { n = n + 1 }
    n
}
""")
    assert ("m.main", True, "ok") in results
    assert "for (; (n < 5); ) {" in c                       # @while -> a stepless for
    assert run(tmp_path, c, "main") == 5


def test_at_while_condition_must_be_bool(tmp_path):
    results, _, _ = build(tmp_path, "pub main = () i32 { @while(5) { }  0 }")
    assert any(q == "m.main" and not ok and "bool" in why for q, ok, why in results)


def test_while_keyword_is_gone(tmp_path):
    # `while` is no longer a construct — it parses as a bare call/identifier and fails
    with pytest.raises(SyntaxError):
        parse("pub main = () i32 { while (1) { }  0 }", "m")


def test_continue_runs_the_step(tmp_path):
    # the for-loop's step slot makes `continue` correct in a counted loop: every
    # iteration here continues, so if `continue` skipped the step (i++) the count
    # `i < 3` would never advance and the loop would hang. Terminating with n == 3
    # proves the step runs on continue.
    results, passing, c = build(tmp_path, """
pub main = () i32 {
    n := 0
    loop(3, (h, i) {
        n = n + 1
        match (i < 100) { true => h.continue(), false => h.break() }
    })
    n
}
""")
    assert run(tmp_path, c, "main") == 3
