"""Source-level module resolution — the project's central claim, that one trie is
the namespace, the import resolver, AND the conflict checker. test_trie.py covers
the Namespace data structure in isolation; these drive it from real `.zen` sources
across multiple modules."""
import pytest

from zen.parser import parse
from zen.main import build_space, build_scopes, resolve, check
from zen.types import Conflict, Unresolved


def files_from(srcs):
    """{namespace: source} -> the parsed File map the pipeline consumes."""
    return {ns: parse(s, ns) for ns, s in srcs.items()}


def test_diamond_import_resolves_to_one_node():
    # two modules each import Vec from core.vec — both must land on the SAME node,
    # never a duplicate (a path is an identity).
    files = files_from({
        "core.vec": "Vec*: { len: i32, cap: i32 }",
        "a": "{ Vec } = core.vec\nfa* = (v: Ptr<Vec>) i32 { v.len }",
        "b": "{ Vec } = core.vec\nfb* = (v: Ptr<Vec>) i32 { v.cap }",
    })
    space = build_space(files)
    build_scopes(files)
    resolve(files, space)
    assert files["a"].scope["Vec"] == "core.vec.Vec"
    assert files["b"].scope["Vec"] == "core.vec.Vec"          # same qualified path
    assert space.walk("core.vec.Vec").value is space.walk("core.vec.Vec").value
    results = check(files, space)[0]
    assert {q: ok for q, ok, _ in results} == {"a.fa": True, "b.fb": True}


def test_two_decls_at_the_same_path_conflict():
    # the only possible name conflict: two declarations claiming one path
    with pytest.raises(Conflict, match="m.Vec"):
        build_space(files_from({"m": "Vec*: { x: i32 }\nVec*: { y: i32 }"}))


def test_same_name_different_modules_is_fine():
    # same simple name under different paths are different nodes — no conflict
    files = files_from({
        "core.vec": "Vec*: { len: i32, cap: i32 }",
        "other": "Vec*: { x: i32 }",
    })
    space = build_space(files)                                # no Conflict raised
    assert space.walk("core.vec.Vec").value is not space.walk("other.Vec").value


def test_importing_a_missing_name_is_unresolved():
    # importing a name the module doesn't export fails when it's resolved
    files = files_from({
        "core.vec": "Vec*: { x: i32 }",
        "m": "{ Nope } = core.vec\nf* = (x: Ptr<Nope>) i32 { 0 }",
    })
    space = build_space(files)
    build_scopes(files)
    with pytest.raises(Unresolved, match="core.vec.Nope"):
        resolve(files, space)
