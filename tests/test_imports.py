"""Source-level module resolution — the project's central claim, that one trie is
the namespace, the import resolver, AND the conflict checker. test_trie.py covers
the Namespace data structure in isolation; these drive it from real `.zen` sources
across multiple modules."""
import pytest

from zen.parser import parse
from zen.main import build_namespace, build_scopes, resolve, check
from zen.types import Conflict, Unresolved, Private


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
    namespace = build_namespace(files)
    build_scopes(files)
    resolve(files, namespace)
    assert files["a"].scope["Vec"] == "core.vec.Vec"
    assert files["b"].scope["Vec"] == "core.vec.Vec"          # same qualified path
    assert namespace.walk("core.vec.Vec").value is namespace.walk("core.vec.Vec").value
    results = check(files, namespace)[0]
    assert {q: ok for q, ok, _ in results} == {"a.fa": True, "b.fb": True}


def test_clashing_names_in_a_scope_are_a_conflict():
    # a local name must resolve to ONE path. Two imports of different things under the same
    # name — or an import colliding with a local decl — is ambiguous, so build_scopes rejects
    # it rather than silently taking the last binding.
    with pytest.raises(Conflict):
        build_scopes(files_from({"m": "{ X } = a\n{ X } = b\nf* = () i32 { 0 }"}))
    with pytest.raises(Conflict):
        build_scopes(files_from({"m": "{ len } = ops\nlen* = () i32 { 1 }"}))


def test_duplicate_import_of_the_same_path_is_fine():
    # re-importing the SAME name -> same path is a harmless duplicate, not a conflict
    files = files_from({"core.vec": "Vec*: { len: i32, cap: i32 }",
                        "m": "{ Vec } = core.vec\n{ Vec } = core.vec\nf* = (v: Ptr<Vec>) i32 { v.len }"})
    build_scopes(files)
    assert files["m"].scope["Vec"] == "core.vec.Vec"


def test_two_decls_at_the_same_path_conflict():
    # the only possible name conflict: two declarations claiming one path
    with pytest.raises(Conflict, match="m.Vec"):
        build_namespace(files_from({"m": "Vec*: { x: i32 }\nVec*: { y: i32 }"}))


def test_same_name_different_modules_is_fine():
    # same simple name under different paths are different nodes — no conflict
    files = files_from({
        "core.vec": "Vec*: { len: i32, cap: i32 }",
        "other": "Vec*: { x: i32 }",
    })
    namespace = build_namespace(files)                                # no Conflict raised
    assert namespace.walk("core.vec.Vec").value is not namespace.walk("other.Vec").value


def test_importing_a_private_name_is_rejected():
    # a bare (no `*`) name is private to its module — another module can't import it
    files = files_from({
        "core.vec": "secret = (n: i32) i32 { n + 1 }",      # no `*` → private
        "m": "{ secret } = core.vec\nf* = (x: i32) i32 { secret(x) }",
    })
    namespace = build_namespace(files)
    build_scopes(files)
    with pytest.raises(Private, match="private to core.vec"):
        resolve(files, namespace)


def test_importing_a_public_name_is_allowed():
    files = files_from({
        "core.vec": "shared* = (n: i32) i32 { n + 1 }",      # `*` → public
        "m": "{ shared } = core.vec\nf* = (x: i32) i32 { shared(x) }",
    })
    namespace = build_namespace(files)
    build_scopes(files)
    resolve(files, namespace)                                    # no Private raised
    assert {q: ok for q, ok, _ in check(files, namespace)[0] if q.startswith("m.")} == {"m.f": True}


def test_deeply_nested_modules_resolve():
    # a path is a path: a directory tree `a/b/c.zen` is the module `a.b.c`, and a
    # deep submodule's public names import + resolve like any other (goal #7).
    files = files_from({
        "a.b.c": "Thing*: { v: i32 }\nmk* = (n: i32) Thing { Thing { v: n } }",
        "main": "{ Thing, mk } = a.b.c\nuse* = (t: Ptr<Thing>) i32 { t.v }",
    })
    namespace = build_namespace(files)
    build_scopes(files)
    resolve(files, namespace)
    assert files["main"].scope["Thing"] == "a.b.c.Thing"      # the deep path resolves
    assert ("main.use", True, "ok") in check(files, namespace)[0]


def test_fully_qualified_type_needs_no_import():
    # a type can be named by its full path inline — no `{ Vec } = core.vec` needed
    files = files_from({
        "core.vec": "Vec*: { len: i32 }",
        "main": "use* = (v: Ptr<core.vec.Vec>) i32 { v.len }",
    })
    namespace = build_namespace(files)
    build_scopes(files)
    resolve(files, namespace)
    assert ("main.use", True, "ok") in check(files, namespace)[0]


def test_same_module_can_use_its_own_private_names():
    # privacy is about IMPORTS across modules; a file freely uses its own bare names
    files = files_from({"m": "helper = (n: i32) i32 { n + 1 }\nf* = (x: i32) i32 { helper(x) }"})
    namespace = build_namespace(files)
    build_scopes(files)
    resolve(files, namespace)
    assert ("m.f", True, "ok") in check(files, namespace)[0]


def test_importing_a_missing_name_is_unresolved():
    # importing a name the module doesn't export fails when it's resolved
    files = files_from({
        "core.vec": "Vec*: { x: i32 }",
        "m": "{ Nope } = core.vec\nf* = (x: Ptr<Nope>) i32 { 0 }",
    })
    namespace = build_namespace(files)
    build_scopes(files)
    with pytest.raises(Unresolved, match="core.vec.Nope"):
        resolve(files, namespace)
