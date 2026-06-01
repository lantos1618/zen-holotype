"""Incremental builds: compile_if_changed skips cc when the C it would emit is
byte-identical to last time and the binary still exists (goal #20). Sound because
codegen is deterministic — identical C means an identical binary, nothing to redo.
A header comment records the cc command, so a flag change busts the cache too."""
from zen.main import compile_if_changed


def test_first_build_compiles_then_caches(tmp_path):
    cpath, bpath = tmp_path / "o.c", tmp_path / "o"
    c = "int main(void){ return 3; }"
    assert compile_if_changed(cpath, bpath, c) is True       # first time → compiles
    assert bpath.exists()
    assert compile_if_changed(cpath, bpath, c) is False      # unchanged → cached, no cc
    import subprocess
    assert subprocess.run([str(bpath)]).returncode == 3


def test_changed_source_recompiles(tmp_path):
    cpath, bpath = tmp_path / "o.c", tmp_path / "o"
    compile_if_changed(cpath, bpath, "int main(void){ return 1; }")
    assert compile_if_changed(cpath, bpath, "int main(void){ return 2; }") is True
    import subprocess
    assert subprocess.run([str(bpath)]).returncode == 2


def test_changed_cc_flags_bust_the_cache(tmp_path):
    cpath, bpath = tmp_path / "o.c", tmp_path / "o"
    c = "int main(void){ return 0; }"
    compile_if_changed(cpath, bpath, c, [])
    # same C, different flags → must recompile (the stamped cc command differs)
    assert compile_if_changed(cpath, bpath, c, ["-O2"]) is True


def test_missing_binary_recompiles_even_if_c_matches(tmp_path):
    cpath, bpath = tmp_path / "o.c", tmp_path / "o"
    c = "int main(void){ return 0; }"
    compile_if_changed(cpath, bpath, c)
    bpath.unlink()                                           # binary gone, .c still there
    assert compile_if_changed(cpath, bpath, c) is True
