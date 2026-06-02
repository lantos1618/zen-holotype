"""Shared fixtures/helpers for the zen test suite.

`make_space()` builds a tiny resolved type space by hand (no parsing) so the
unit tests for fits()/infer() exercise the checker in isolation. `compile_main`
is the common compile-and-run harness shared by the codegen/stdlib/self-hosting tests.
"""
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from zen.ast import (Dir, Prim, PrimT, NameT, PtrT, Field_, Struct,
                          Param, Fn)
from zen.types import Namespace
from zen.main import (load, build_namespace, build_scopes, resolve, fold_comptime,
                      run_emits, check, emit_c)


@pytest.fixture
def compile_main(tmp_path):
    """The common harness: write a zen program (defining `main* () i32`), run it through
    the whole pipeline, compile the emitted C, and run it. Returns the exit code — or
    (stdout, exit_code) with capture=True. `strict` uses -Wall -Wextra -Werror; `roots`
    is the DCE entry set (None = emit everything)."""
    def run(src, *, capture=False, roots=("main.main",), strict=True):
        (tmp_path / "main.zen").write_text(src)
        files = load(tmp_path)
        namespace = build_namespace(files)
        build_scopes(files); resolve(files, namespace)
        fold_comptime(files, namespace); run_emits(files, namespace)
        _, passing = check(files, namespace)
        assert "main.main" in passing, "main.main did not type-check"
        c = emit_c(files, passing, namespace, roots=set(roots) if roots else None)
        (tmp_path / "o.c").write_text(c + "\nint main(void){ return main_main(); }\n")
        cflags = ["-Wall", "-Wextra", "-Werror"] if strict else []
        r = subprocess.run(["cc", *cflags, "-std=gnu11", str(tmp_path / "o.c"), "-o", str(tmp_path / "o")],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        done = subprocess.run([str(tmp_path / "o")], capture_output=True, text=True)
        return (done.stdout, done.returncode) if capture else done.returncode
    return run

I32 = PrimT(Prim.I32)
VEC = NameT("core.vec.Vec", ())


def ptr(pointee, d=Dir.READ):
    return PtrT(d, pointee)


def option(inner):
    return NameT("Option", (inner,))


@pytest.fixture
def namespace():
    """A resolved namespace: struct core.vec.Vec + fns ops.len (Ptr) / ops.bump (MutPtr)."""
    sp = Namespace()
    sp.insert("core.vec.Vec", Struct("Vec",
              [Field_("len", I32), Field_("cap", I32)], pub=True))
    sp.insert("ops.len", Fn("len", [Param("v", ptr(VEC, Dir.READ))], I32))
    sp.insert("ops.bump", Fn("bump", [Param("v", ptr(VEC, Dir.MUT))], I32))
    return sp


@pytest.fixture
def scope():
    """Local-name -> fully-qualified-path map matching the `namespace` fixture."""
    return {"Vec": "core.vec.Vec", "len": "ops.len", "bump": "ops.bump"}


EXAMPLES = pathlib.Path(__file__).parent.parent / "examples"
