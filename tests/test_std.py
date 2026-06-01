"""The bundled standard library — `std.*`, ordinary runtime Zen, importable from
any program. Unlike the comptime-only prelude, std is checked and lowered like
user code; but its helpers are templates, so importing std costs nothing unless a
program uses them (they inline at the call site, never emitted standalone)."""
import subprocess

from zen.main import (load, build_space, build_scopes, resolve, fold_comptime,
                      run_emits, check, emit_c)


def build(tmp_path, src):
    (tmp_path / "main.zen").write_text(src)
    files = load(tmp_path)
    space = build_space(files)
    build_scopes(files); resolve(files, space)
    fold_comptime(files, space); run_emits(files, space)
    _, passing = check(files, space)
    return files, space, passing


def run(tmp_path, c, entry="main"):
    cfile = tmp_path / "o.c"
    cfile.write_text(c + f"\nint main(void){{ return main_{entry}(); }}\n")
    r = subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-std=gnu11",
                        str(cfile), "-o", str(tmp_path / "o")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return subprocess.run([str(tmp_path / "o")]).returncode


def test_std_iter_is_loaded_and_importable(tmp_path):
    files, space, passing = build(tmp_path, """
{ fold } = std.iter
main* = () i32 { fold([1, 2, 3], 0, (a, x) { a + x }) }
""")
    assert "std.iter" in files                       # bundled, always loaded
    assert space.walk("std.iter.fold").value.tparams == ("T",)
    assert "main.main" in passing


def test_fold_and_each_run(tmp_path):
    files, space, passing = build(tmp_path, """
{ fold, each } = std.iter
main* = () i32 {
    s := fold([10, 20, 30], 0, (a, x) { a + x })   // 60
    r := 0
    each([1, 2, 3], (x) { r = r + x })             // 6
    s + r
}
""")
    assert run(tmp_path, emit_c(files, passing, space)) == 66


def test_fold_is_generic_over_element_type(tmp_path):
    # the same template folds an i64 slice — T solved from the arguments
    files, space, passing = build(tmp_path, """
{ fold } = std.iter
main* = () i64 { fold([100, 200, 300], 0, (a, x) { a + x }) }
""")
    c = emit_c(files, passing, space)
    assert run(tmp_path, c, entry="main") == (600 & 0xFF)   # exit code is 8-bit


def test_unused_std_emits_nothing(tmp_path):
    # importing nothing from std → std contributes no C at all (zero-cost ambient)
    files, space, passing = build(tmp_path, "main* = () i32 { 0 }")
    c = emit_c(files, passing, space)
    assert "std_iter" not in c and "fold" not in c


# ── std.mem — the library's allocator over libc ────────────────────────────
def test_mem_round_trips_the_heap(tmp_path):
    files, space, passing = build(tmp_path, """
{ alloc, release } = std.mem
main* = () i32 {
    p := alloc(8)
    store(p, 42)
    x := load(p)
    release(p)
    x
}
""")
    assert "main.main" in passing
    assert run(tmp_path, emit_c(files, passing, space)) == 42


def test_mem_zeroed_and_copy(tmp_path):
    files, space, passing = build(tmp_path, """
{ zeroed, copy, release } = std.mem
main* = () i32 {
    src := zeroed(4)
    store(src, 7)
    dst := zeroed(4)
    copy(dst, src, 4)
    r := load(dst)
    release(src)  release(dst)
    r
}
""")
    assert run(tmp_path, emit_c(files, passing, space)) == 7


# ── std.iter map_into / filter_into — caller-owned output, no allocation ────
def test_map_into(tmp_path):
    files, space, passing = build(tmp_path, """
{ map_into } = std.iter
main* = () i32 {
    xs  := [1, 2, 3, 4]
    out := [0, 0, 0, 0]
    map_into(xs, out, (x) { x * 10 })
    out[0] + out[1] + out[2] + out[3]
}
""")
    assert run(tmp_path, emit_c(files, passing, space)) == 100   # (1+2+3+4)*10


def test_filter_into_packs_and_counts(tmp_path):
    files, space, passing = build(tmp_path, """
{ filter_into } = std.iter
main* = () i32 {
    xs   := [1, 2, 3, 4, 5]
    kept := [0, 0, 0, 0, 0]
    n := filter_into(xs, kept, (x) { x > 2 })       // packs [3, 4, 5], returns n = 3
    (n == 3).match { true => kept[0] + kept[1] + kept[2], false => 0 }   // 12 iff count right
}
""")
    assert run(tmp_path, emit_c(files, passing, space)) == 12   # 3 + 4 + 5, and n == 3


# ── std.str — read-only string ops over libc (first-class string literals) ──
def test_str_len_and_eq(tmp_path):
    files, space, passing = build(tmp_path, """
{ len, eq, ne, is_empty } = std.str
main* = () i32 {
    a := (len("hello") == 5).match  { true => 1,  false => 0 }
    b := (eq("abc", "abc")).match   { true => 2,  false => 0 }
    c := (eq("abc", "xyz")).match   { true => 4,  false => 0 }   // c stays 0
    d := (ne("abc", "xyz")).match   { true => 8,  false => 0 }
    e := (is_empty("")).match       { true => 16, false => 0 }
    a + b + c + d + e
}
""")
    assert "main.main" in passing
    assert run(tmp_path, emit_c(files, passing, space)) == 27   # 1 + 2 + 0 + 8 + 16
