"""[]-overloading makes a user struct loopable (goal #5). A struct whose type has
an `at(Ptr<Self>, i64) T` method is indexable — `s[i]` dispatches to `at` — so the
element-form loop works on it exactly like a slice. The struct supplies its own
`len` (a field, here) and `at`; `s.loop(...)` then reads each element."""
import subprocess

from zen.main import (load, build_space, build_scopes, resolve, fold_comptime,
                      run_emits, check, emit_c)


def build(tmp_path, src):
    (tmp_path / "main.zen").write_text(src)
    files = load(tmp_path)
    space = build_space(files)
    build_scopes(files); resolve(files, space)
    fold_comptime(files, space); run_emits(files, space)
    results, passing = check(files, space)
    return results, passing, space, files


def run(tmp_path, files, passing, space):
    c = emit_c(files, passing, space)
    cfile = tmp_path / "o.c"
    cfile.write_text(c + "\nint main(void){ return main_main(); }\n")
    r = subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-std=gnu11",
                        str(cfile), "-o", str(tmp_path / "o")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return subprocess.run([str(tmp_path / "o")]).returncode


_BUF = """
Buf*: { data: [i32], len: i32 }
At*: { at: (Ptr<Self>, i64) i32 }
Buf.impl(At) { at = (b: Ptr<Buf>, i: i64) i32 { b.data[i] } }
"""


def test_struct_indexing_dispatches_to_at(tmp_path):
    results, passing, space, files = build(tmp_path, _BUF + """
main* = () i32 {
    buf := Buf { data: [10, 20, 30], len: 3 }
    addr(buf)[1]                       // b[1] -> At::at(b, 1) -> 20
}
""")
    assert "main.main" in passing
    assert run(tmp_path, files, passing, space) == 20


def test_loop_over_a_user_struct(tmp_path):
    results, passing, space, files = build(tmp_path, _BUF + """
sum* = (b: Ptr<Buf>) i32 {
    s := 0
    b.loop((h, i, x) { s = s + x })    // loop a STRUCT, not a slice
    s
}
main* = () i32 {
    buf := Buf { data: [10, 20, 30, 40], len: 4 }
    sum(addr(buf))
}
""")
    assert ("At for Buf::at", True, "ok") in results
    assert run(tmp_path, files, passing, space) == 100


def test_non_indexable_struct_is_rejected(tmp_path):
    # a struct without an `at` method still can't be indexed (no silent pass)
    results, _, _, _ = build(tmp_path, """
Plain*: { v: i32 }
bad* = (p: Ptr<Plain>) i32 { p[0] }
""")
    assert any(q == "main.bad" and not ok and "non-slice" in why for q, ok, why in results)
