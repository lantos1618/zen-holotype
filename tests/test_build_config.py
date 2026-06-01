"""build.zen reads cc flags and link libraries off the Executable, and threads
them into the cc invocation (goals #16, #17)."""
import subprocess

from zen.main import (parse, interpret_build, load, load_uses, build_space,
                      build_scopes, resolve, fold_comptime, run_emits, check, emit_c)


def test_cflags_and_links_are_read_from_build():
    bf = parse("""
{ Builder, Executable } = @builtin.build
build = (b: Builder) i32 {
    b.add(Executable { name: "demo", main: "main.zen", cflags: ["-O2", "-g"], links: ["m"] })
    0
}
""", "build")
    cfg = interpret_build(bf)
    assert cfg["cflags"] == ["-O2", "-g"]
    assert cfg["links"] == ["m"]


def test_defaults_are_empty_when_absent():
    bf = parse("""
{ Builder, Executable } = @builtin.build
build = (b: Builder) i32 { b.add(Executable { name: "demo", main: "main.zen" })  0 }
""", "build")
    cfg = interpret_build(bf)
    assert cfg["cflags"] == [] and cfg["links"] == []


def test_cflags_reach_the_compiler(tmp_path):
    # a program built with the configured cflags (-O2) still compiles and runs
    (tmp_path / "main.zen").write_text("main* = () i32 { 7 }")
    files = load(tmp_path)
    space = build_space(files)
    build_scopes(files); resolve(files, space)
    fold_comptime(files, space); run_emits(files, space)
    _, passing = check(files, space)
    c = emit_c(files, passing, space)
    cpath = tmp_path / "o.c"
    cpath.write_text(c + "\nint main(void){ return main_main(); }\n")
    cc_extra = ["-O2", "-g", "-lm"]              # what cmd_build would pass
    r = subprocess.run(["cc", "-Wall", "-Wextra", *cc_extra, str(cpath), "-o", str(tmp_path / "o")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert subprocess.run([str(tmp_path / "o")]).returncode == 7


# ── target scaffold (goal #18): native now, structured for wasm ─────────────
def test_target_defaults_to_native_and_is_read():
    bf = lambda t: parse(
        "{ Builder, Executable } = @builtin.build\n"
        f"build = (b: Builder) i32 {{ b.add(Executable {{ name: \"d\", main: \"m.zen\"{t} }})  0 }}",
        "build")
    assert interpret_build(bf("")).get("target") == "native"            # default
    assert interpret_build(bf(', target: "wasm"')).get("target") == "wasm"  # read through


def test_unknown_target_is_rejected(tmp_path):
    import pytest
    from zen.main import cmd_build
    (tmp_path / "build.zen").write_text(
        "{ Builder, Executable } = @builtin.build\n"
        'build = (b: Builder) i32 { b.add(Executable { name: "d", main: "main.zen", target: "wasm" })  0 }')
    (tmp_path / "main.zen").write_text("main* = () i32 { 0 }")
    with pytest.raises(SystemExit, match="not supported yet"):
        cmd_build(str(tmp_path))
