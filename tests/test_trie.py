"""T6-T7: the namespace trie — the one structure that is namespace, import
resolver, and conflict checker at once.
"""
import pytest

from holotype.types import Namespace, Conflict, Unresolved


def test_insert_then_walk_returns_value():
    sp = Namespace()
    sp.insert("core.vec.Vec", "DECL")
    assert sp.walk("core.vec.Vec").value == "DECL"


def test_walk_sets_canonical_path():
    sp = Namespace()
    sp.insert("a.b.c", 1)
    assert sp.walk("a.b.c").path == "a.b.c"
    assert sp.walk("a.b").path == "a.b"


def test_duplicate_path_is_the_only_conflict():
    sp = Namespace()
    sp.insert("ops.len", 1)
    with pytest.raises(Conflict):
        sp.insert("ops.len", 2)


def test_walk_missing_path_raises_unresolved():
    sp = Namespace()
    sp.insert("ops.len", 1)
    with pytest.raises(Unresolved):
        sp.walk("ops.missing")


def test_diamond_import_lands_on_one_node():
    # A and B both reference core.vec.Vec; both resolve to the SAME node object,
    # so there's nothing to dedup — identity is the path.
    sp = Namespace()
    sp.insert("core.vec.Vec", "the-holotype")
    from_a = sp.walk("core.vec.Vec")
    from_b = sp.walk("core.vec.Vec")
    assert from_a is from_b
    assert from_a.value == "the-holotype"


def test_shared_prefix_does_not_collide():
    sp = Namespace()
    sp.insert("ops.len", "len")
    sp.insert("ops.cap", "cap")
    assert sp.walk("ops.len").value == "len"
    assert sp.walk("ops.cap").value == "cap"
    # the shared parent 'ops' is one node with two kids, no value of its own
    assert sp.walk("ops").value is None
