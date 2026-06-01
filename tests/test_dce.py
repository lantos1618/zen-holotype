"""Dead-code elimination (goal #21). emit_c(..., roots={entry}) emits only the
plain functions reachable from the entry — an executable drops what it never
calls. With roots=None (a library / check build) every passing fn is emitted, as
before. Generic instances and trait impls were already reachability-pruned; this
extends that to plain top-level functions."""
import subprocess

from zen.main import (load, build_space, build_scopes, resolve, fold_comptime,
                      run_emits, check, emit_c)


def built(tmp_path, src):
    (tmp_path / "main.zen").write_text(src)
    files = load(tmp_path)
    space = build_space(files)
    build_scopes(files); resolve(files, space)
    fold_comptime(files, space); run_emits(files, space)
    _, passing = check(files, space)
    return files, space, passing


_SRC = """
used* = (n: i32) i32 { n + 1 }
dead* = (n: i32) i32 { n * 99 }
main* = () i32 { used(5) }
"""


def test_library_build_emits_everything(tmp_path):
    files, space, passing = built(tmp_path, _SRC)
    c = emit_c(files, passing, space)                    # roots=None → library
    assert "main_used" in c and "main_dead" in c


def test_executable_build_drops_unreached(tmp_path):
    files, space, passing = built(tmp_path, _SRC)
    c = emit_c(files, passing, space, roots={"main.main"})
    assert "main_main" in c and "main_used" in c         # entry + what it calls
    assert "main_dead" not in c                          # never called → pruned


def test_pruned_executable_still_compiles_and_runs(tmp_path):
    files, space, passing = built(tmp_path, _SRC)
    c = emit_c(files, passing, space, roots={"main.main"})
    cpath = tmp_path / "o.c"
    cpath.write_text(c + "\nint main(void){ return main_main(); }\n")
    r = subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", str(cpath), "-o", str(tmp_path / "o")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr                   # no unused-function warning either
    assert subprocess.run([str(tmp_path / "o")]).returncode == 6


def test_transitive_reach_through_a_plain_call(tmp_path):
    # main → a → b: both live; c (only called by dead) is dropped
    files, space, passing = built(tmp_path, """
b* = (n: i32) i32 { n + 1 }
a* = (n: i32) i32 { b(n) }
c* = (n: i32) i32 { n + 1 }
dead* = (n: i32) i32 { c(n) }
main* = () i32 { a(5) }
""")
    c = emit_c(files, passing, space, roots={"main.main"})
    assert "main_a" in c and "main_b" in c
    assert "main_c" not in c and "main_dead" not in c
