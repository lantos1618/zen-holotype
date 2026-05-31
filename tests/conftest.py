"""Shared fixtures/helpers for the holotype test suite.

`make_space()` builds a tiny resolved type space by hand (no parsing) so the
unit tests for fits()/infer() exercise the checker in isolation.
"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from holotype.ast import (Dir, Prim, PrimT, NameT, PtrT, Field_, Struct,
                          Param, Fn)
from holotype.types import Namespace

I32 = PrimT(Prim.I32)
VEC = NameT("core.vec.Vec", ())


def ptr(pointee, d=Dir.READ):
    return PtrT(d, pointee)


def option(inner):
    return NameT("Option", (inner,))


@pytest.fixture
def space():
    """A resolved space: struct core.vec.Vec + fns ops.len (Ptr) / ops.bump (MutPtr)."""
    sp = Namespace()
    sp.insert("core.vec.Vec", Struct("Vec",
              [Field_("len", I32), Field_("cap", I32)], pub=True))
    sp.insert("ops.len", Fn("len", [Param("v", ptr(VEC, Dir.READ))], I32))
    sp.insert("ops.bump", Fn("bump", [Param("v", ptr(VEC, Dir.MUT))], I32))
    return sp


@pytest.fixture
def scope():
    """Local-name -> fully-qualified-path map matching the `space` fixture."""
    return {"Vec": "core.vec.Vec", "len": "ops.len", "bump": "ops.bump"}


EXAMPLES = pathlib.Path(__file__).parent.parent / "examples"
