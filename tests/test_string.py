"""std.string — a growable, owned heap String assembled at RUNTIME (not a comptime
`str` literal). The keystone for runtime code generation: a program builds source as
a value while it runs. Functional API — each op returns the updated (ptr,len,cap)
header; the byte buffer is realloc'd underneath."""
import subprocess

from zen.main import (load, build_namespace, build_scopes, resolve, fold_comptime,
                      run_emits, check, emit_c)


def build_and_run(tmp_path, src):
    (tmp_path / "main.zen").write_text(src)
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files); resolve(files, namespace)
    fold_comptime(files, namespace); run_emits(files, namespace)
    _, passing = check(files, namespace)
    assert "main.main" in passing
    c = emit_c(files, passing, namespace)
    (tmp_path / "o.c").write_text(c + "\nint main(void){ return main_main(); }\n")
    r = subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-std=gnu11",
                        str(tmp_path / "o.c"), "-o", str(tmp_path / "o")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return subprocess.run([str(tmp_path / "o")], capture_output=True, text=True).stdout


_EMIT = """
{ String, new, with_cap, push, append, bytes, free } = std.string
putchar = (c: i32) i32

emit* = (s: String) void { bytes(s).loop((h, i, b) { putchar(b) }) }
"""


def test_string_built_at_runtime_with_growth(tmp_path):
    # cap starts at 4, so the appends MUST realloc the buffer to grow — proving the
    # String is assembled at runtime, not folded from literals.
    out = build_and_run(tmp_path, _EMIT + """
main* = () i32 {
    s := with_cap(4)
    s = append(s, "Hello, ")
    s = append(s, "runtime ")
    s = append(s, "codegen!")
    s = push(s, 10)
    emit(s)
    free(s)
    0
}
""")
    assert out == "Hello, runtime codegen!\n"


def test_string_push_bytes_and_length(tmp_path):
    # push single bytes; the running total length drives how many we emit.
    out = build_and_run(tmp_path, _EMIT + """
main* = () i32 {
    s := new()
    s = push(s, 65)        // 'A'
    s = push(s, 66)        // 'B'
    s = push(s, 67)        // 'C'
    emit(s)
    0
}
""")
    assert out == "ABC"
