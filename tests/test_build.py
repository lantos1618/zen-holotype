"""U1 Step 1 (Goal U): `zenc build foo.zen -o foo` / `zenc run foo.zen` produce + run a native binary.

The shipping `zenc` gains a real build path: it emits the program's C (HEAD swapped for #include "zenrt.h"),
links bootstrap/zenrt.c via cc, and runs it. A Zen `main = () i32 { … }` is the entry (emits C `int32_t
main()`). zenrt.{c,h} are found relative to the binary (<dir(argv0)>/bootstrap), so this uses the repo's
make-built ROOT/zenc (which sits beside ROOT/bootstrap). U1 Step 3 wired the Zen module loader
(std.internal.resolve.resolve_program) into the binary, so `zenc build/run/check` now RESOLVE `{ … } = std.X`
imports from <root>/zen/std/X.zen — see test_zenc_run_resolves_std_import below.
"""
import subprocess
import tempfile
import pytest
from pathlib import Path
import shutil

import _oracle

ROOT = _oracle.ROOT
ZEN_FIXTURES = ROOT / "tests" / "fixtures" / "zen"
PROJECT_FIXTURES = ROOT / "tests" / "fixtures" / "project"


def _zenc():
    """The repo's make-built zenc (beside ROOT/bootstrap, so it can find zenrt.{c,h})."""
    subprocess.run(["make", "-f", "bootstrap/Makefile", "zenc"], cwd=str(ROOT),
                   check=True, capture_output=True)
    return str(ROOT / "zenc")


def _run_fixture(zenc, name):
    return subprocess.run([zenc, "run", str(ZEN_FIXTURES / name)], capture_output=True, text=True)


def _caret(col, width=1):
    return "  " + (" " * (col - 1)) + "^" + ("~" * (width - 1)) + "\n"


def test_zenc_build_emits_runnable_binary():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text("main = () i32 { 6 * 2 }\n")
    out = d / "p"
    r = subprocess.run([zenc, "build", str(d / "p.zen"), "-o", str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert out.exists(), "zenc build produced no binary"
    assert subprocess.run([str(out)]).returncode == 12


def test_zenc_run_struct_program():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text("P*: { x: i32, y: i32 }\nmain = () i32 { p := P(x: 3, y: 4)  p.x * p.y }\n")
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 12, r.stderr


def test_zenc_build_bad_file():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    out = d / "x"
    r = subprocess.run([zenc, "build", "/no/such/file.zen", "-o", str(out)], capture_output=True, text=True)
    assert r.returncode == 1, r.returncode  # clean failure (exit 1), not a signal death
    assert "cannot open" in r.stderr, r.stderr
    assert not out.exists()


def test_zenc_check_reports_error_count_and_first_kind():
    """U1.2: the binary now type-checks — the killer case (undefined name was emit-exit-0)."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    src = d / "p.zen"
    src.write_text("main = () i32 { undefined_fn(1, 2) }\n")
    r = subprocess.run([zenc, "check", str(src)], capture_output=True, text=True)
    assert r.returncode == 1
    # U1.4 Phase 2: human message + the error's 1-based line:col (undefined_fn starts at col 17)
    assert r.stderr == (
        f"zenc: {src}:1:17: error[undefined-name]: undefined name\n"
        "  main = () i32 { undefined_fn(1, 2) }\n"
        + _caret(17, len("undefined_fn"))
        + "hint: declare the name, import it, or qualify the intended module binding\n"
    )


def test_zenc_check_diagnostics_have_kind_span_message_and_hint():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())

    cases = [
        (
            "arity.zen",
            "add = (a: i32, b: i32) i32 { a + b }\nmain = () i32 { add(1) }\n",
            ":2:17: error[arity]: wrong number of arguments\n",
            "hint: check the callee signature and pass exactly the declared parameters\n",
            "main = () i32 { add(1) }",
            17,
        ),
        (
            "arg.zen",
            "takes_u8 = (b: u8) i32 { 0 }\nbig = () i64 { 9999999999 }\nmain = () i32 { takes_u8(big()) }\n",
            ":3:26: error[arg-type]: argument type does not fit the parameter\n",
            "hint: check the argument type or add an explicit conversion at the call site\n",
            "main = () i32 { takes_u8(big()) }",
            26,
            3,
        ),
        (
            "trait.zen",
            "Show*: { render: (Ptr<Self>) i32 }\nPoint*: { x: i32 }\nPoint.impl(Show, { })\n",
            ":3:1: error[conformance]: impl does not satisfy the trait\n",
            "hint: define every required trait method with the exact receiver, parameter, and return types\n",
            "Point.impl(Show, { })",
            1,
            5,
        ),
        (
            "assign.zen",
            "main = () i32 {\n    x := 5\n    y := (1 < 2)\n    x = y\n    x\n}\n",
            ":4:5: error[assign-fit]: assigned value does not fit the variable's type\n",
            "hint: make the assigned value fit the target's type\n",
            "    x = y",
            5,
            1,
        ),
        (
            "idxset.zen",
            "main = () i32 {\n    s := [1, 2, 3]\n    b := (1 < 2)\n    s[0] = b\n    s[0]\n}\n",
            ":4:5: error[assign-fit]: assigned value does not fit the variable's type\n",
            "hint: make the assigned value fit the target's type\n",
            "    s[0] = b",
            5,
            1,
        ),
        (
            "return.zen",
            "main = () i32 { 1 < 2 }\n",
            ":1:19: error[return-fit]: returned value does not fit the declared return type\n",
            "hint: make the returned value fit the function's declared return type\n",
            "main = () i32 { 1 < 2 }",
            19,
            1,
        ),
    ]
    for case in cases:
        name, text, diagnostic, hint, source_line, col = case[:6]
        width = case[6] if len(case) > 6 else len(source_line[col - 1:].split("(", 1)[0].split(".", 1)[0])
        src = d / name
        src.write_text(text)
        r = subprocess.run([zenc, "check", str(src)], capture_output=True, text=True)
        assert r.returncode == 1
        assert diagnostic in r.stderr, r.stderr
        assert f"  {source_line}\n" in r.stderr, r.stderr
        assert _caret(col, width) in r.stderr, r.stderr
        assert hint in r.stderr, r.stderr


def test_diagnostic_value_exposes_nested_span_shape():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    src = d / "diag_shape.zen"
    src.write_text(
        "{ diagnostic_from_source } = compiler.check_validate\n"
        "{ to_exit } = std.core.bool\n"
        "{ eq } = std.text.str\n"
        "main = () i32 {\n"
        "    diag := diagnostic_from_source(\"main = () i32 { missing_name() }\\n\", 515, 1)\n"
        "    ok := eq(diag.kind, \"undefined-name\")\n"
        "        && (diag.span.start == 16)\n"
        "        && (diag.span.width == 12)\n"
        "        && (diag.count == 1)\n"
        "        && eq(diag.message, \"undefined name\")\n"
        "        && eq(diag.hint, \"declare the name, import it, or qualify the intended module binding\")\n"
        "    ok.to_exit()\n"
        "}\n"
    )
    r = subprocess.run([zenc, "run", str(src)], capture_output=True, text=True)
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)


def test_zenc_check_position_survives_import_flattening():
    """U1.4 Phase 2: the checker's byte offset is into the import-FLATTENED source; the reported
    line:col must still land in the USER's file (mapped back by the error line's text)."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    src = d / "p.zen"
    src.write_text('{ println } = std.text.fmt\nmain = () i32 {\n    println("hi")\n    oops()\n}\n')
    r = subprocess.run([zenc, "check", str(src)], capture_output=True, text=True)
    assert r.returncode == 1
    assert r.stderr == (
        f"zenc: {src}:4:5: error[undefined-name]: undefined name\n"
        "      oops()\n"
        + _caret(5, len("oops"))
        + "hint: declare the name, import it, or qualify the intended module binding\n"
    )


def test_zenc_check_reports_imported_sibling_source_location():
    """Errors inside an imported sibling should render against that sibling's original file/source,
    not the root module that triggered flattening."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    bad = d / "bad.zen"
    main = d / "main.zen"
    bad.write_text("bad* = () i32 { missing() }\n")
    main.write_text("{ bad } = bad\nmain = () i32 { bad() }\n")
    r = subprocess.run([zenc, "check", str(main)], capture_output=True, text=True)
    assert r.returncode == 1
    assert r.stderr == (
        f"zenc: {bad}:1:17: error[undefined-name]: undefined name\n"
        "  bad* = () i32 { missing() }\n"
        + _caret(17, len("missing"))
        + "hint: declare the name, import it, or qualify the intended module binding\n"
    )


def test_zenc_check_reports_namespace_imported_sibling_source_location():
    """Namespace-bound imports rewrite exported names in the flat source. Diagnostics still need
    to land on the original sibling source line."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    bad = d / "bad.zen"
    main = d / "main.zen"
    bad.write_text("bad* = () i32 { missing() }\n")
    main.write_text("bad = bad\nmain = () i32 { bad.bad() }\n")
    r = subprocess.run([zenc, "check", str(main)], capture_output=True, text=True)
    assert r.returncode == 1
    assert r.stderr == (
        f"zenc: {bad}:1:17: error[undefined-name]: undefined name\n"
        "  bad* = () i32 { missing() }\n"
        + _caret(17, len("missing"))
        + "hint: declare the name, import it, or qualify the intended module binding\n"
    )


# ── pos-preserving rebuilds (check.zen recall/revar/var_call): the resolver/inliner REBUILDS every
# Call/Var it walks, copying the ORIGINAL node's pos structurally. These lock the chosen semantics:
# an error inside a generic template body / a lambda spliced at a HOF call site reports the byte
# offset of the offending name ITSELF (template-internal positions survive subst_expr + xform_call
# + inline_lambda) — NOT a callsite fallback, and NOT pos 0 ("unknown"), which a single rebuild
# site using the pos-0 ctor once caused for EVERY call the inliner walked. ─────────────────────────
def test_zenc_check_position_survives_generic_instantiation():
    """Undefined name INSIDE a generic fn body, instantiated at a call site (the subst/xform
    inline paths): `oops` sits at 1:21 in the template body and is reported there."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    src = d / "p.zen"
    src.write_text("wrap = (x: T) i32 { oops(x) }\nmain = () i32 { wrap(41) }\n")
    r = subprocess.run([zenc, "check", str(src)], capture_output=True, text=True)
    assert r.returncode == 1
    assert f"{src}:1:21: error[undefined-name]: undefined name" in r.stderr, r.stderr
    assert "  wrap = (x: T) i32 { oops(x) }\n" in r.stderr, r.stderr
    assert _caret(21, len("oops")) in r.stderr, r.stderr


def test_zenc_check_position_survives_lambda_body_inlining():
    """Undefined name inside a LAMBDA spliced by HOF inlining (inline_lambda/xform_body):
    `bad` sits at 3:17 inside the lambda literal and is reported there."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    src = d / "p.zen"
    src.write_text(
        "apply = (f: (i32) i32, x: i32) i32 { f(x) }\n"
        "main = () i32 {\n"
        "    apply((n) { bad(n) }, 41)\n"
        "}\n")
    r = subprocess.run([zenc, "check", str(src)], capture_output=True, text=True)
    assert r.returncode == 1
    assert f"{src}:3:17: error[undefined-name]: undefined name" in r.stderr, r.stderr
    assert "      apply((n) { bad(n) }, 41)\n" in r.stderr, r.stderr
    assert _caret(17, len("bad")) in r.stderr, r.stderr


def test_zenc_check_position_after_lambda_hof_inlining():
    """Undefined name AFTER a lambda-HOF call in the same body (the inliner rebuilt the whole
    body around it): `nope` sits at 4:5 and is reported there."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    src = d / "p.zen"
    src.write_text(
        "apply = (f: (i32) i32, x: i32) i32 { f(x) }\n"
        "main = () i32 {\n"
        "    r := apply((n) { n + 1 }, 41)\n"
        "    nope(r)\n"
        "}\n")
    r = subprocess.run([zenc, "check", str(src)], capture_output=True, text=True)
    assert r.returncode == 1
    assert r.stderr == (
        f"zenc: {src}:4:5: error[undefined-name]: undefined name\n"
        "      nope(r)\n"
        + _caret(5, len("nope"))
        + "hint: declare the name, import it, or qualify the intended module binding\n"
    )


def test_zenc_check_rejects_source_if():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text("main = () i32 { if (1 < 2) { return 9 } 7 }\n")
    r = subprocess.run([zenc, "check", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode != 0 and "undefined name" in r.stderr, r.stderr


def test_zenc_check_ok_program():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text("main = () i32 { 6 * 2 }\n")
    assert subprocess.run([zenc, "check", str(d / "p.zen")]).returncode == 0


def test_zenc_build_rejects_illtyped_no_binary():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text("main = () i32 { 1 < 2 }\n")  # bool not<: i32 -> return-fit
    out = d / "p"
    r = subprocess.run([zenc, "build", str(d / "p.zen"), "-o", str(out)], capture_output=True, text=True)
    assert r.returncode != 0 and not out.exists(), "ill-typed program should not produce a binary"


def test_zenc_run_prints_floats():
    """f64 end-to-end: float literals, arithmetic, and std.text.fmt's generic println.
    Exact stdout is pinned so formatting cannot silently drift."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ println } = std.text.fmt\n\n"
        "main = () i32 {\n"
        "  println(1.5)\n"
        "  println(0.25)\n"
        "  println(-3.0)\n"
        "  println(0.001)\n"
        "  println(1.5 + 0.25 * 2.0)\n"   # precedence: 1.5 + 0.5 = 2
        "  0\n"
        "}\n")
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "1.5\n0.25\n-3\n0.001\n2\n", repr(r.stdout)


# ── U1.3: the binary RESOLVES `{ … } = std.X` imports from disk (std.internal.resolve folded in) ──────────────
_IMPORT_PROG = (
    "{ eq } = std.text.str\n"
    "main = () i32 { eq(%s).match ({ true => 1, false => 0 }) }\n"
)


def test_zenc_run_resolves_std_import():
    """THE U1.3 PAYOFF: a program that imports std.text.str builds + runs — the import is resolved from
    <root>/zen/std/text/str.zen (today the binary used to silently strip imports → stdlib unreachable)."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    # eq of equal strings → true → 1 (so a non-resolving build, which would fail to link `eq`, can't pass).
    (d / "p.zen").write_text(_IMPORT_PROG % '"ab", "ab"')
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 1, r.stderr  # eq("ab","ab") == true → 1
    # the false branch resolves identically → 0.
    (d / "q.zen").write_text(_IMPORT_PROG % '"ab", "xy"')
    r = subprocess.run([zenc, "run", str(d / "q.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr  # eq("ab","xy") == false → 0


def test_zenc_build_resolves_std_import():
    """`zenc build` (not just run) of a std-importing program produces a runnable native binary."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(_IMPORT_PROG % '"ab", "ab"')
    out = d / "p"
    r = subprocess.run([zenc, "build", str(d / "p.zen"), "-o", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert out.exists(), "zenc build of a std-importing program produced no binary"
    assert subprocess.run([str(out)]).returncode == 1


def test_zenc_check_resolves_std_import():
    """`zenc check` resolves the import too — a well-typed std-importing program checks ok."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(_IMPORT_PROG % '"ab", "ab"')
    assert subprocess.run([zenc, "check", str(d / "p.zen")]).returncode == 0


def test_or_return_propagates_err():
    """.or_return() (M4): keyword-free error propagation. `x := g().or_return()` yields the Ok payload
    or early-returns the Err from the enclosing fn. Exit 61 = f(1)->Ok(6), f(0)->Err propagated."""
    zenc = _zenc()
    r = _run_fixture(zenc, "or_return.zen")
    assert r.returncode == 61, r.stderr


def test_scope_cancellation_signal_consumed():
    """Cancellation is a behavior, not just a type: a Scope's checkpoint budget runs out, checkpoint
    CONSTRUCTS .Stop(.Deadline), and the body MATCHES it and bails — exit 3 = ran 3 Go's then Stop."""
    zenc = _zenc()
    r = _run_fixture(zenc, "scope_cancellation.zen")
    assert r.returncode == 3, r.stderr


def test_scope_colorless_sync_async():
    """M3 capstone: ONE colorless body (`run`) runs under both a sync scope (with_sync) and an
    async scope (spawned coroutine), producing the same 105 either way — checkpoint is a no-op
    under SyncArena and a coroutine yield under AsyncArena. Exit 3 = sync(1) + async(2)."""
    zenc = _zenc()
    r = _run_fixture(zenc, "scope_colorless_sync_async.zen")
    assert r.returncode == 3, r.stderr


def test_scope_generic_field_dispatch():
    """A1: trait dispatch through a nested-generic struct FIELD receiver across an inlined generic fn.
    `Scope<A>(alloc: a.addr())` monomorphizes to Scope<SyncArena>, and the field receiver `s.alloc`
    (an Arrow after pointer-receiver resolution) is re-inferred so `acquire`/`checkpoint` route to the
    SyncArena impls rather than emitting bare unlinkable names. Exit 105."""
    zenc = _zenc()
    r = _run_fixture(zenc, "scope_generic_field_dispatch.zen")
    assert r.returncode == 105, r.stderr


def test_zenc_project_manifest_build_run_check():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    src = d / "src"
    src.mkdir()
    native = d / "native.c"
    native.write_text('#include <stdint.h>\nint32_t manifest_bonus(void){ return 2; }\n')
    (d / "zen.toml").write_text(
        'package = "manifest-demo"\n'
        'root = "src"\n'
        'main = "main.zen"\n'
        'out = "manifest-bin"\n'
        f'ccflags = "{native}"\n'
    )
    (src / "util.zen").write_text("add* = (a: i32, b: i32) i32 { a + b }\n")
    (src / "main.zen").write_text(
        "{ println } = std.text.fmt\n"
        "{ add } = util\n"
        "manifest_bonus = () i32\n"
        'main = () i32 { println("project")  add(40, manifest_bonus()) }\n'
    )

    checked = subprocess.run([zenc, "check", str(d)], capture_output=True, text=True)
    assert checked.returncode == 0, checked.stderr
    assert f"{src / 'main.zen'}: ok" in checked.stderr

    run = subprocess.run([zenc, "run", str(d)], capture_output=True, text=True)
    assert run.returncode == 42, run.stderr
    assert run.stdout == "project\n"

    built = subprocess.run([zenc, "build", str(d)], capture_output=True, text=True)
    assert built.returncode == 0, built.stderr
    out = d / "manifest-bin"
    assert out.exists()
    exe = subprocess.run([str(out)], capture_output=True, text=True)
    assert exe.returncode == 42, exe.stderr
    assert exe.stdout == "project\n"


def test_zenc_project_manifest_fixture_build_run_check():
    zenc = _zenc()
    project = Path(tempfile.mkdtemp()) / "manifest_demo"
    shutil.copytree(PROJECT_FIXTURES / "manifest_demo", project)

    checked = subprocess.run([zenc, "check", str(project)], capture_output=True, text=True)
    assert checked.returncode == 0, checked.stderr
    assert f"{project / 'src' / 'main.zen'}: ok" in checked.stderr

    run = subprocess.run([zenc, "run", str(project)], capture_output=True, text=True)
    assert run.returncode == 42, run.stderr
    assert run.stdout == "fixture project\n"

    built = subprocess.run([zenc, "build", str(project)], capture_output=True, text=True)
    assert built.returncode == 0, built.stderr
    out = project / "fixture-bin"
    assert out.exists()
    exe = subprocess.run([str(out)], capture_output=True, text=True)
    assert exe.returncode == 42, exe.stderr
    assert exe.stdout == "fixture project\n"


def test_zenc_build_zen_program_drives_the_build():
    """M6 (real build): a project with a `build.zen` is built by RUNNING that Zen program. `zenc build`
    appends a main that calls its `build(b)` and reads back the Target (root/main/out/link) it returns
    — the build is code, not a TOML file. The fixture's build.zen sets out="fixture-bin"; main.zen also
    imports a project sibling (util.zen), proving sibling resolution survives the build path."""
    zenc = _zenc()
    project = Path(tempfile.mkdtemp()) / "build_zen_demo"
    shutil.copytree(PROJECT_FIXTURES / "build_zen_demo", project)

    built = subprocess.run([zenc, "build", str(project)], capture_output=True, text=True)
    assert built.returncode == 0, built.stderr
    out = project / "fixture-bin"
    assert out.exists(), built.stderr
    exe = subprocess.run([str(out)], capture_output=True, text=True)
    assert exe.returncode == 42, exe.stderr           # score(40) = 42
    assert exe.stdout == "built from build.zen\n"      # the program's output, NOT the build spec

    run = subprocess.run([zenc, "run", str(project)], capture_output=True, text=True)
    assert run.returncode == 42, run.stderr
    assert run.stdout == "built from build.zen\n"


def test_zenc_project_manifest_link_directive_links_c_library():
    """M6 (build graph): a `link = "m"` manifest directive adds `-l<lib>` to the cc link line, so a
    program that calls a libm symbol links + runs. We use Bessel `j0` (gcc has no const-folding path
    once its argument is an opaque cross-TU value), fed by a native `zen_seed()` returning 1.5;
    j0(1.5)*100 truncates to 51. Without the directive the libm symbol is unresolved and the build
    fails with no binary — proving the `link` field is load-bearing, not cosmetic."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    src = d / "src"
    src.mkdir()
    native = d / "native.c"
    native.write_text('#include <stdint.h>\ndouble zen_seed(void){ return 1.5; }\n')
    (src / "main.zen").write_text(
        "{ println } = std.text.fmt\n"
        "j0 = (x: f64) f64\n"
        "zen_seed = () f64\n"
        "main = () i32 {\n"
        '    println("link libm")\n'
        "    to_i32(j0(zen_seed()) * 100.0)\n"
        "}\n"
    )

    def write_manifest(out_name, with_link):
        link_line = 'link = "m"\n' if with_link else ""
        (d / "zen.toml").write_text(
            'package = "linklib-demo"\n'
            'root = "src"\n'
            'main = "main.zen"\n'
            f'out = "{out_name}"\n'
            + link_line
            + f'ccflags = "{native}"\n'
        )

    # with `link = "m"`: the libm symbol resolves -> builds, runs, exits 51.
    write_manifest("linklib-bin", with_link=True)
    built = subprocess.run([zenc, "build", str(d)], capture_output=True, text=True)
    assert built.returncode == 0, built.stderr
    out = d / "linklib-bin"
    assert out.exists()
    exe = subprocess.run([str(out)], capture_output=True, text=True)
    assert exe.returncode == 51, exe.stderr
    assert exe.stdout == "link libm\n"

    run = subprocess.run([zenc, "run", str(d)], capture_output=True, text=True)
    assert run.returncode == 51, run.stderr
    assert run.stdout == "link libm\n"

    # drop the directive: j0 is now unresolved at link time -> clean build failure, no binary.
    write_manifest("linklib-bin-nolink", with_link=False)
    nolink = subprocess.run([zenc, "build", str(d)], capture_output=True, text=True)
    assert nolink.returncode != 0, "the `link` directive should be load-bearing"
    assert not (d / "linklib-bin-nolink").exists()


def test_type_import_keeps_actor_methods_available():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "alloc = std.mem.alloc\n"
        "{ Context, Receiver, ReplyRef, ActorCell } = std.concurrent.actor\n"
        "Msg*: Ping(ReplyRef<i32>)\n"
        "Room*: { n: i32 }\n"
        "Room.impl(Receiver<Msg>, {\n"
        "    receive = (room: MutPtr<Room>, ctx: Context<Msg>) void {\n"
        "        ctx.msg.match({ .Ping(reply_to) => reply_to.send(7) })\n"
        "    }\n"
        "})\n"
        "main = () i32 {\n"
        "    heap := alloc.default()\n"
        "    cell: ActorCell<Msg> := heap.addr().cell(4)\n"
        "    reply_to: ReplyRef<i32> := cell.reply(heap.addr())\n"
        "    ref: ActorRef<Msg> := cell.ref()\n"
        "    ref.send(.Ping(reply_to))\n"
        "    room := Room(n: 0)\n"
        "    cell.drain(room.addr())\n"
        "    out := reply_to.await(heap.addr())\n"
        "    cell.free(heap.addr())\n"
        "    out\n"
        "}\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 7, r.stderr


def test_generic_replyref_send_in_trait_match_arm():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ default } = std.mem.alloc\n"
        "{ to_exit } = std.core.bool\n"
        "{ eq } = std.text.str\n"
        "{ Context, Receiver, ReplyRef, ActorCell } = std.concurrent.actor\n"
        "Msg*: Ping(ReplyRef<str>)\n"
        "Room*: { n: i32 }\n"
        "Room.impl(Receiver<Msg>, {\n"
        "    receive = (room: MutPtr<Room>, ctx: Context<Msg>) void {\n"
        "        ctx.msg.match({ .Ping(reply_to) => reply_to.send(\"done\") })\n"
        "    }\n"
        "})\n"
        "main = () i32 {\n"
        "    alloc := default()\n"
        "    cell: ActorCell<Msg> := alloc.addr().cell(4)\n"
        "    room := Room(n: 0)\n"
        "    out: str := cell.request(alloc.addr(), room.addr(), (reply_to) { .Ping(reply_to) })\n"
        "    cell.free(alloc.addr())\n"
        "    eq(out, \"done\").to_exit()\n"
        "}\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_generic_receiver_method_infers_match_payload_binding_type():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ eq } = std.text.str\n"
        "{ to_exit } = std.core.bool\n"
        "Box<T>: {\n"
        "    value: T,\n"
        "    get = (box: Box<T>) T { box.value }\n"
        "}\n"
        "Msg*: Hold(Box<str>) | Empty\n"
        "main = () i32 {\n"
        "    msg := Msg.Hold(Box<str>(value: \"generic\"))\n"
        "    got := msg.match({\n"
        "        .Hold(box) => box.get(),\n"
        "        .Empty => \"empty\"\n"
        "    })\n"
        "    eq(got, \"generic\").to_exit()\n"
        "}\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_generic_receiver_method_infers_non_first_match_payload_binding_type():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ eq } = std.text.str\n"
        "{ to_exit } = std.core.bool\n"
        "Box<T>: {\n"
        "    value: T,\n"
        "    get = (box: Box<T>) T { box.value }\n"
        "}\n"
        "Msg*: Empty | Hold(Box<str>)\n"
        "main = () i32 {\n"
        "    msg := Msg.Hold(Box<str>(value: \"generic\"))\n"
        "    got := msg.match({\n"
        "        .Empty => \"empty\",\n"
        "        .Hold(box) => box.get()\n"
        "    })\n"
        "    eq(got, \"generic\").to_exit()\n"
        "}\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_zenc_check_rejects_mixed_enum_match_result_types():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    src = d / "p.zen"
    src.write_text(
        "Msg*: A | B\n"
        "main = () i32 {\n"
        "    msg := Msg.A()\n"
        "    msg.match({ .A => 1, .B => \"bad\" })\n"
        "}\n"
    )
    r = subprocess.run([zenc, "check", str(src)], capture_output=True, text=True)
    assert r.returncode == 1
    assert "error[return-fit]" in r.stderr, r.stderr


def test_zenc_check_rejects_bool_enum_match_result_mismatch():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    src = d / "p.zen"
    src.write_text(
        "Msg*: A | B\n"
        "main = () i32 {\n"
        "    msg := Msg.A()\n"
        "    bad := msg.match({ .A => 1, .B => (1 < 2) })\n"
        "    0\n"
        "}\n"
    )
    r = subprocess.run([zenc, "check", str(src)], capture_output=True, text=True)
    assert r.returncode == 1
    assert "error[return-fit]" in r.stderr, r.stderr


def test_zenc_run_enum_match_numeric_arms_widen_result_type():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ to_exit } = std.core.bool\n"
        "Msg*: Small | Big\n"
        "big = () i64 { 4294967298 }\n"
        "main = () i32 {\n"
        "    msg := Msg.Big()\n"
        "    got := msg.match({ .Small => 1, .Big => big() })\n"
        "    (got == big()).to_exit()\n"
        "}\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ── U3: std.text.fmt — a program can PRINT (output + int→string), via std.text.string ──────────────────────────
# This also locks in the #98 fix: std.text.fmt pulls std.text.string, so a built program emits its own `String`,
# which must NOT clash with zenrt.h's (the build path defines ZEN_NO_STRING to suppress the latter).
def test_zenc_run_prints_text_and_ints():
    """Generic `println` from std.text.fmt writes text and primitive values."""
    zenc = _zenc()
    r = _run_fixture(zenc, "print_text_and_ints.zen")
    assert r.returncode == 0, r.stderr
    assert r.stdout == "answer:\n42\ntrue\n", repr(r.stdout)


def test_zenc_run_prints_bool_literals():
    """Bool literals infer as bool, so generic Display dispatch resolves before C emission."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ println } = std.text.fmt\n"
        "{ to_exit } = std.core.bool\n"
        "main = () i32 {\n"
        "    println(true)\n"
        "    println(false)\n"
        "    true.to_exit()\n"
        "}\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "true\nfalse\n", repr(r.stdout)


def test_zenc_run_prints_str_and_string():
    """std.text.fmt prints borrowed str and owned String without forcing String.finish()."""
    zenc = _zenc()
    r = _run_fixture(zenc, "print_str_and_string.zen")
    assert r.returncode == 0, r.stderr
    assert r.stdout == "borrowed\nalias\nowned!\nowned\n", repr(r.stdout)


def test_zenc_run_fmt_numeric_write_uses_explicit_allocator():
    """Numeric fmt helpers can use a caller allocator for the temporary String."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ Allocator, Heap, default } = std.mem.alloc\n"
        "{ write_int_in, write_float_in } = std.text.fmt\n"
        "Counting: { heap: Heap, acquired: i32, released: i32 }\n"
        "Counting.impl(Allocator, {\n"
        "    acquire = (a: MutPtr<Counting>, n: i64) RawPtr<u8> {\n"
        "        a.acquired = a.acquired + 1\n"
        "        a.heap.addr().acquire(n)\n"
        "    }\n"
        "    resize = (a: MutPtr<Counting>, p: RawPtr<u8>, n: i64) RawPtr<u8> {\n"
        "        a.heap.addr().resize(p, n)\n"
        "    }\n"
        "    release = (a: MutPtr<Counting>, p: RawPtr<u8>) void {\n"
        "        a.released = a.released + 1\n"
        "        a.heap.addr().release(p)\n"
        "    }\n"
        "})\n"
        "main = () i32 {\n"
        "    c := Counting(heap: default(), acquired: 0, released: 0)\n"
        "    a := c.addr()\n"
        "    write_int_in(a, -7)\n"
        "    write_float_in(a, 1.25)\n"
        "    ((c.acquired == 2) && (c.released == 2)).match({ true => 0, false => 1 })\n"
        "}\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "-71.25"


def test_zenc_run_fmt_numeric_try_write_result_paths():
    """Numeric fmt helpers expose Result paths for temporary String allocation failure."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ Allocator, Heap, default } = std.mem.alloc\n"
        "{ Result, IoError } = std.core.result\n"
        "{ try_write_int_in, try_write_float_in } = std.text.fmt\n"
        "{ to_exit } = std.core.bool\n"
        "Limit: { heap: Heap, remaining: i32, released: i32 }\n"
        "Limit.impl(Allocator, {\n"
        "    acquire = (a: MutPtr<Limit>, n: i64) RawPtr<u8> {\n"
        "        (a.remaining <= 0).match({\n"
        "            true => null_ptr(),\n"
        "            false => {\n"
        "                a.remaining = a.remaining - 1\n"
        "                a.heap.addr().acquire(n)\n"
        "            }\n"
        "        })\n"
        "    }\n"
        "    resize = (a: MutPtr<Limit>, p: RawPtr<u8>, n: i64) RawPtr<u8> {\n"
        "        a.heap.addr().resize(p, n)\n"
        "    }\n"
        "    release = (a: MutPtr<Limit>, p: RawPtr<u8>) void {\n"
        "        a.released = a.released + 1\n"
        "        a.heap.addr().release(p)\n"
        "    }\n"
        "})\n"
        "main = () i32 {\n"
        "    ok_alloc := Limit(heap: default(), remaining: 1, released: 0)\n"
        "    wrote := ok_alloc.addr().try_write_int_in(42).match({\n"
        "        .Ok(n) => (n == 2) && (ok_alloc.released == 1),\n"
        "        .Err(e) => false\n"
        "    })\n"
        "    fail_alloc := Limit(heap: default(), remaining: 0, released: 0)\n"
        "    failed := fail_alloc.addr().try_write_float_in(1.25).match({\n"
        "        .Ok(n) => false,\n"
        "        .Err(e) => e.match({ .NotFound => true, _ => false })\n"
        "    })\n"
        "    (wrote && failed && (fail_alloc.released == 0)).to_exit()\n"
        "}\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "42"


def test_zenc_check_rejects_default_num_allocating_helpers():
    """Numeric owned-String helpers are allocator-first; std.text.num does not hide default heap allocation."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    cases = {
        "integer.zen": "num = std.text.num\nmain = () i32 { s := num.integer(42)  0 }\n",
        "try_integer.zen": "num = std.text.num\nmain = () i32 { r := num.try_integer(42)  0 }\n",
        "float.zen": "num = std.text.num\nmain = () i32 { s := num.float(1.5)  0 }\n",
        "try_float.zen": "num = std.text.num\nmain = () i32 { r := num.try_float(1.5)  0 }\n",
    }
    for name, source in cases.items():
        src = d / name
        src.write_text(source)
        r = subprocess.run([zenc, "check", str(src)], capture_output=True, text=True)
        assert r.returncode != 0, f"{name} unexpectedly checked ok"


def test_zenc_run_integer_print_negatives_and_zero():
    """int→string handles 0, negatives (leading '-'), and multi-digit — the itoa edge cases."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ println } = std.text.fmt\n"
        "main = () i32 { println(0)  println(-7)  println(1000000)  0 }\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "0\n-7\n1000000\n", repr(r.stdout)


def test_zenc_run_core_slice_explicit_allocator():
    """std.core.slice exposes allocator-backed helpers; callers can place copied slices in an arena."""
    zenc = _zenc()
    assert _run_fixture(zenc, "core_slice_explicit_allocator.zen").returncode == 14


def test_zenc_run_core_slice_try_result_paths():
    """Fallible slice helpers return Result values when caller-owned allocation fails."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ Allocator, default, malloc, free } = std.mem.alloc\n"
        "{ Result, IoError } = std.core.result\n"
        "{ to_exit } = std.core.bool\n"
        "{ try_dup_in, try_concat_in, try_node_in } = std.core.slice\n"
        "LimitAlloc: { left: i32 }\n"
        "LimitAlloc.impl(Allocator, {\n"
        "    acquire = (a: MutPtr<LimitAlloc>, n: i64) RawPtr<u8> {\n"
        "        (a.left > 0).match ({\n"
        "            true => {\n"
        "                a.left = a.left - 1\n"
        "                malloc(n)\n"
        "            },\n"
        "            false => null_ptr()\n"
        "        })\n"
        "    }\n"
        "    resize = (a: MutPtr<LimitAlloc>, p: RawPtr<u8>, n: i64) RawPtr<u8> { null_ptr() }\n"
        "    release = (a: MutPtr<LimitAlloc>, p: RawPtr<u8>) void { free(p) }\n"
        "})\n"
        "success = () bool {\n"
        "    heap := default()\n"
        "    a := heap.addr()\n"
        "    r0: Result<[i32], IoError> := a.try_dup_in([1, 2])\n"
        "    r0.match({\n"
        "        .Ok(xs) => {\n"
        "            r1: Result<[i32], IoError> := a.try_concat_in(xs, [3, 4])\n"
        "            r1.match({\n"
        "                .Ok(ys) => {\n"
        "                    rp: Result<Ptr<i32>, IoError> := a.try_node_in(5)\n"
        "                    rp.match({\n"
        "                        .Ok(p) => (ys[0] == 1) && (ys[3] == 4) && (load(p) == 5),\n"
        "                        .Err(e) => false\n"
        "                    })\n"
        "                },\n"
        "                .Err(e) => false\n"
        "            })\n"
        "        },\n"
        "        .Err(e) => false\n"
        "    })\n"
        "}\n"
        "failure = () bool {\n"
        "    lim := LimitAlloc(left: 0)\n"
        "    r: Result<[i32], IoError> := lim.addr().try_dup_in([1])\n"
        "    r.match({\n"
        "        .Err(e) => e.match({ .NotFound => true, _ => false }),\n"
        "        .Ok(xs) => false\n"
        "    })\n"
        "}\n"
        "main = () i32 {\n"
        "    (success() && failure()).to_exit()\n"
        "}\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_zenc_run_iter_try_result_paths():
    """Allocating iter helpers have Result paths for caller-owned allocation failure."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ Allocator, default, malloc, free } = std.mem.alloc\n"
        "{ Result, IoError } = std.core.result\n"
        "{ to_exit } = std.core.bool\n"
        "{ try_map_in, try_filter_in } = std.collections.iter\n"
        "LimitAlloc: { left: i32 }\n"
        "LimitAlloc.impl(Allocator, {\n"
        "    acquire = (a: MutPtr<LimitAlloc>, n: i64) RawPtr<u8> {\n"
        "        (a.left > 0).match ({\n"
        "            true => {\n"
        "                a.left = a.left - 1\n"
        "                malloc(n)\n"
        "            },\n"
        "            false => null_ptr()\n"
        "        })\n"
        "    }\n"
        "    resize = (a: MutPtr<LimitAlloc>, p: RawPtr<u8>, n: i64) RawPtr<u8> { null_ptr() }\n"
        "    release = (a: MutPtr<LimitAlloc>, p: RawPtr<u8>) void { free(p) }\n"
        "})\n"
        "success = () bool {\n"
        "    heap := default()\n"
        "    a := heap.addr()\n"
        "    r0: Result<[i32], IoError> := a.try_map_in([1, 2, 3], (x) { x + 1 })\n"
        "    r0.match({\n"
        "        .Ok(mapped) => {\n"
        "            r1: Result<[i32], IoError> := a.try_filter_in(mapped, (x) { x > 2 })\n"
        "            r1.match({\n"
        "                .Ok(filtered) => (filtered.len == 2) && (filtered[0] == 3) && (filtered[1] == 4),\n"
        "                .Err(e) => false\n"
        "            })\n"
        "        },\n"
        "        .Err(e) => false\n"
        "    })\n"
        "}\n"
        "failure = () bool {\n"
        "    lim := LimitAlloc(left: 0)\n"
        "    r: Result<[i32], IoError> := lim.addr().try_map_in([1], (x) { x })\n"
        "    r.match({\n"
        "        .Err(e) => e.match({ .NotFound => true, _ => false }),\n"
        "        .Ok(xs) => false\n"
        "    })\n"
        "}\n"
        "main = () i32 {\n"
        "    (success() && failure()).to_exit()\n"
        "}\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ── U3: std.collections.vec — a growable Vec<T> with an EXPLICIT allocator (acquire/resize/release), no hidden malloc ─
# Mutating Vec operations are receiver-scoped methods, with the allocator passed explicitly.
def test_zenc_run_vec_explicit_allocator():
    """Vec<T> threads a Ptr<A:Allocator> per op: vec.of plus receiver methods, allocator-backed."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ default } = std.mem.alloc\n"
        "vec = std.collections.vec\n"
        "main = () i32 {\n"
        "  alloc := default()\n"
        "  a := alloc.addr()\n"
        "  v := vec.of(a, [10, 20])\n"
        "  v2 := v.push(a, 30)\n"         # len==cap -> grows via a.resize
        "  total := v2.get(0) + v2.get(2)\n"
        "  v2.free(a)\n"
        "  total\n"
        "}\n"
    )
    assert subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True).returncode == 40


def test_zenc_run_vec_growth_resizes():
    """Repeated push past capacity forces several a.resize grows; live elements survive each grow."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    pushes = "".join(f"  v{i} := v{i-1}.push(a, {i+1})\n" for i in range(1, 6))
    gets = " + ".join(f"v5.get({i})" for i in range(6))
    (d / "p.zen").write_text(
        "{ default } = std.mem.alloc\n"
        "vec = std.collections.vec\n"
        "main = () i32 {\n"
        "  alloc := default()\n"
        "  a := alloc.addr()\n"
        "  v0 := vec.of(a, [1])\n"
        f"{pushes}"
        f"  {gets}\n"
        "}\n"
    )
    # 1+2+3+4+5+6 = 21
    assert subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True).returncode == 21


def test_zenc_run_vec_try_result_paths():
    """Fallible Vec allocation returns Result values; failed growth leaves the old Vec valid."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ Allocator, default, malloc, free } = std.mem.alloc\n"
        "{ Result, IoError } = std.core.result\n"
        "vec = std.collections.vec\n"
        "LimitAlloc: { left: i32 }\n"
        "LimitAlloc.impl(Allocator, {\n"
        "    acquire = (a: MutPtr<LimitAlloc>, n: i64) RawPtr<u8> {\n"
        "        (a.left > 0).match ({\n"
        "            true => {\n"
        "                a.left = a.left - 1\n"
        "                malloc(n)\n"
        "            },\n"
        "            false => null_ptr()\n"
        "        })\n"
        "    }\n"
        "    resize = (a: MutPtr<LimitAlloc>, p: RawPtr<u8>, n: i64) RawPtr<u8> { null_ptr() }\n"
        "    release = (a: MutPtr<LimitAlloc>, p: RawPtr<u8>) void { free(p) }\n"
        "})\n"
        "success = () i32 {\n"
        "    m := default()\n"
        "    a := m.addr()\n"
        "    r0: Result<vec.Vec<i32>, IoError> := vec.try_of(a, [1])\n"
        "    r0.match ({\n"
        "        .Ok(v0) => {\n"
        "            r1: Result<vec.Vec<i32>, IoError> := v0.try_push(a, 2)\n"
        "            r1.match ({\n"
        "                .Ok(v) => {\n"
        "                    n := v.get(0) + v.get(1)\n"
        "                    v.free(a)\n"
        "                    n\n"
        "                },\n"
        "                .Err(e) => 90\n"
        "            })\n"
        "        },\n"
        "        .Err(e) => 91\n"
        "    })\n"
        "}\n"
        "failure = () i32 {\n"
        "    lim := LimitAlloc(left: 1)\n"
        "    a := lim.addr()\n"
        "    r0: Result<vec.Vec<i32>, IoError> := vec.try_of(a, [4])\n"
        "    r0.match ({\n"
        "        .Ok(v) => {\n"
        "            r1: Result<vec.Vec<i32>, IoError> := v.try_push(a, 5)\n"
        "            r1.match ({\n"
        "                .Ok(v2) => {\n"
        "                    v2.free(a)\n"
        "                    80\n"
        "                },\n"
        "                .Err(e) => {\n"
        "                    n := v.get(0)\n"
        "                    v.free(a)\n"
        "                    n\n"
        "                }\n"
        "            })\n"
        "        },\n"
        "        .Err(e) => 81\n"
        "    })\n"
        "}\n"
        "main = () i32 {\n"
        "    n := success() + failure()\n"
        "    (n == 7).match ({ true => 0, false => n })\n"
        "}\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_zenc_run_vec_and_print_together():
    """THE payoff: a single program imports a COLLECTION (std.collections.vec) AND formatted output (std.text.fmt) and
    runs — Vec accessors are receiver methods instead of imported free functions."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ default } = std.mem.alloc\n"
        "vec = std.collections.vec\n"
        "{ println } = std.text.fmt\n"
        "main = () i32 {\n"
        "  alloc := default()\n"
        "  a := alloc.addr()\n"
        "  v := vec.of(a, [10, 20])\n"
        "  v2 := v.push(a, 30)\n"
        "  println(v2.get(0))\n"              # 10
        "  println(v2.get(2))\n"              # 30
        "  0\n"
        "}\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "10\n30\n", repr(r.stdout)


def test_vec_and_string_push_coexist_by_receiver_type():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ default } = std.mem.alloc\n"
        "vec = std.collections.vec\n"
        "{ String, init } = std.text.string\n"
        "main = () i32 {\n"
        "  alloc := default()\n"
        "  a := alloc.addr()\n"
        "  v := vec.of(a, [10, 20])\n"
        "  v2 := v.push(a, 30)\n"
        "  s := a.init(4)\n"
        "  s2 := s.push_in(a, '!')\n"
        "  out := v2.get(2) + to_i32(s2.len)\n"
        "  v2.free(a)\n"
        "  s2.free_in(a)\n"
        "  out\n"
        "}\n"
    )
    assert subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True).returncode == 31


def test_string_builder_chain_inlines_linearly_not_exponentially():
    """Regression (BUG #2): a deep chain of generic String-builder helpers used to blow up the
    template inliner EXPONENTIALLY (`reserve_in` read its `s` arg 4×, so each nested
    `.push_in(…)` level spliced the whole receiver subtree in 4× — k links ≈ 4^k inlined size).
    `reserve_in` now binds `s` to a local first, so the receiver is emitted once per level and an
    8-deep generic builder chain compiles in well under a second. Guard with a tight timeout."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    chain = "".join(".push_byte(a, 'x')" for _ in range(8))
    (d / "p.zen").write_text(
        "{ to_exit } = std.core.bool\n"
        "{ String, new_in } = std.text.string\n"
        "alloc = std.mem.alloc\n"
        "push_byte<A> = (s: String, a: MutPtr<A>, v: u8) String { s.push_in(a, v).push_in(a, v) }\n"
        f"build<A> = (a: MutPtr<A>) str {{ a.new_in(){chain}.finish_in(a) }}\n"
        "main = () i32 { heap := alloc.default()  s := build(heap.addr())  (s.len() == 16).to_exit() }\n"
    )
    # 30s is ~100× the linear time and far below the (timed-out) exponential blowup.
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr


def test_zenc_run_string_explicit_allocator_and_result():
    """String has the same allocator story as Vec: explicit MutPtr<A> variants, plus Result-returning
    allocation checks for code that wants errors as values instead of raw NULL."""
    zenc = _zenc()
    assert _run_fixture(zenc, "string_explicit_allocator_result.zen").returncode == 8


def test_zenc_check_rejects_default_string_constructors_and_mutators():
    """String construction and mutation are allocator-explicit."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    cases = {
        "new.zen": "{ new } = std.text.string\nmain = () i32 { s := new()  0 }\n",
        "init_without_allocator.zen": "string = std.text.string\nmain = () i32 { s := string.init(16)  0 }\n",
        "try_init_without_allocator.zen": "string = std.text.string\nmain = () i32 { r := string.try_init(16)  0 }\n",
        "append.zen": (
            "{ default } = std.mem.alloc\n"
            "{ new_in } = std.text.string\n"
            "main = () i32 { a := default()  s := a.addr().new_in()  s.append(\"x\")  0 }\n"
        ),
        "push.zen": (
            "{ default } = std.mem.alloc\n"
            "{ new_in } = std.text.string\n"
            "main = () i32 { a := default()  s := a.addr().new_in()  s.push('x')  0 }\n"
        ),
        "finish.zen": (
            "{ default } = std.mem.alloc\n"
            "{ new_in } = std.text.string\n"
            "main = () i32 { a := default()  s := a.addr().new_in()  done := s.finish()  0 }\n"
        ),
        "free.zen": (
            "{ default } = std.mem.alloc\n"
            "{ new_in } = std.text.string\n"
            "main = () i32 { a := default()  s := a.addr().new_in()  s.free()  0 }\n"
        ),
    }
    for name, source in cases.items():
        src = d / name
        src.write_text(source)
        r = subprocess.run([zenc, "check", str(src)], capture_output=True, text=True)
        assert r.returncode != 0, f"{name} unexpectedly checked ok"


def test_zenc_check_rejects_default_core_slice_storage_helpers():
    """std.core.slice storage helpers are allocator-first; short names still take the allocator."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    cases = {
        "buf.zen": "slice = std.core.slice\nmain = () i32 { xs := slice.buf(2, [0])  0 }\n",
        "try_buf.zen": "slice = std.core.slice\nmain = () i32 { r := slice.try_buf(2, [0])  0 }\n",
        "dup.zen": "slice = std.core.slice\nmain = () i32 { xs := slice.dup([1, 2])  0 }\n",
        "try_dup.zen": "slice = std.core.slice\nmain = () i32 { r := slice.try_dup([1, 2])  0 }\n",
        "node.zen": "slice = std.core.slice\nmain = () i32 { p := slice.node(1)  0 }\n",
        "try_node.zen": "slice = std.core.slice\nmain = () i32 { r := slice.try_node(1)  0 }\n",
        "concat.zen": "slice = std.core.slice\nmain = () i32 { xs := slice.concat([1], [2])  0 }\n",
        "try_concat.zen": "slice = std.core.slice\nmain = () i32 { r := slice.try_concat([1], [2])  0 }\n",
    }
    for name, source in cases.items():
        src = d / name
        src.write_text(source)
        r = subprocess.run([zenc, "check", str(src)], capture_output=True, text=True)
        assert r.returncode != 0, f"{name} unexpectedly checked ok"


# ── CAPSTONE: a real program (examples/stats.zen) composing Vec + generics + enums + match + fmt ──────
def test_zenc_run_capstone_stats_example():
    """The Goal-U proof: examples/stats.zen — list statistics (sum/max/even-count) over a vec.Vec<i32> with an
    explicit allocator, enum-dispatched via .match, printed via std.text.fmt — builds and runs end to end."""
    zenc = _zenc()
    r = subprocess.run([zenc, "run", str(ROOT / "examples" / "stats.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "sum:\n39\nmax:\n9\nevens:\n3\n", repr(r.stdout)


def test_zenc_run_actor_demo_example():
    """examples/actor_demo.zen is the actor ergonomics proof: typed messages, a chat-room handle, and reply refs."""
    zenc = _zenc()
    demo = ROOT / "examples" / "actor_demo.zen"
    r = subprocess.run([zenc, "run", str(demo)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "", repr(r.stdout)


def test_zenc_run_actor_try_constructors_result_paths():
    """Actor cell/reply allocation has Result paths and cleans up partial allocations."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ Allocator, malloc, free } = std.mem.alloc\n"
        "{ Result, IoError } = std.core.result\n"
        "{ to_exit } = std.core.bool\n"
        "{ ActorCell, ReplyRef, try_cell } = std.concurrent.actor\n"
        "Msg*: Ping\n"
        "Counting: { acquired: i32, released: i32, fail_after: i32 }\n"
        "should_fail = (a: MutPtr<Counting>) bool { (a.fail_after >= 0) && (a.acquired >= a.fail_after) }\n"
        "Counting.impl(Allocator, {\n"
        "    acquire = (a: MutPtr<Counting>, n: i64) RawPtr<u8> {\n"
        "        a.should_fail().match ({\n"
        "            true => null_ptr(),\n"
        "            false => {\n"
        "                a.acquired = a.acquired + 1\n"
        "                malloc(n)\n"
        "            }\n"
        "        })\n"
        "    }\n"
        "    resize = (a: MutPtr<Counting>, p: RawPtr<u8>, n: i64) RawPtr<u8> { null_ptr() }\n"
        "    release = (a: MutPtr<Counting>, p: RawPtr<u8>) void {\n"
        "        a.released = a.released + 1\n"
        "        free(p)\n"
        "    }\n"
        "})\n"
        "success = () bool {\n"
        "    c := Counting(acquired: 0, released: 0, fail_after: -1)\n"
        "    a := c.addr()\n"
        "    cell_r: Result<ActorCell<Msg>, IoError> := a.try_cell(4)\n"
        "    ok_cell := cell_r.match({\n"
        "        .Ok(cell) => { cell.free(a)  true },\n"
        "        .Err(e) => false\n"
        "    })\n"
        "    cell2: ActorCell<Msg> := a.cell(4)\n"
        "    reply_r: Result<ReplyRef<i32>, IoError> := cell2.try_reply(a)\n"
        "    ok_reply := reply_r.match({\n"
        "        .Ok(reply) => {\n"
        "            reply.send(9)\n"
        "            v := reply.await(a)\n"
        "            v == 9\n"
        "        },\n"
        "        .Err(e) => false\n"
        "    })\n"
        "    cell2.free(a)\n"
        "    ok_cell && ok_reply && (c.acquired == 6) && (c.released == 6)\n"
        "}\n"
        "fail_cell = () bool {\n"
        "    c := Counting(acquired: 0, released: 0, fail_after: 1)\n"
        "    r: Result<ActorCell<Msg>, IoError> := c.addr().try_cell(4)\n"
        "    r.match({\n"
        "        .Err(e) => e.match({ .NotFound => (c.acquired == 1) && (c.released == 1), _ => false }),\n"
        "        .Ok(cell) => false\n"
        "    })\n"
        "}\n"
        "fail_reply = () bool {\n"
        "    c := Counting(acquired: 0, released: 0, fail_after: 3)\n"
        "    a := c.addr()\n"
        "    cell: ActorCell<Msg> := a.cell(4)\n"
        "    r: Result<ReplyRef<i32>, IoError> := cell.try_reply(a)\n"
        "    cell.free(a)\n"
        "    r.match({\n"
        "        .Err(e) => e.match({ .NotFound => (c.acquired == 3) && (c.released == 3), _ => false }),\n"
        "        .Ok(reply) => false\n"
        "    })\n"
        "}\n"
        "main = () i32 {\n"
        "    (success() && fail_cell() && fail_reply()).to_exit()\n"
        "}\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_zenc_run_actor_try_spawn_result_paths():
    """Stateful actor handle allocation has a Result path and releases partial allocations."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ Allocator, malloc, free } = std.mem.alloc\n"
        "{ Result, IoError } = std.core.result\n"
        "{ to_exit } = std.core.bool\n"
        "actor = std.concurrent.actor\n"
        "Msg*: Ping\n"
        "Room*: { n: i32 }\n"
        "Counting: { acquired: i32, released: i32, fail_after: i32 }\n"
        "should_fail = (a: MutPtr<Counting>) bool { (a.fail_after >= 0) && (a.acquired >= a.fail_after) }\n"
        "Counting.impl(Allocator, {\n"
        "    acquire = (a: MutPtr<Counting>, n: i64) RawPtr<u8> {\n"
        "        a.should_fail().match ({\n"
        "            true => null_ptr(),\n"
        "            false => {\n"
        "                a.acquired = a.acquired + 1\n"
        "                malloc(n)\n"
        "            }\n"
        "        })\n"
        "    }\n"
        "    resize = (a: MutPtr<Counting>, p: RawPtr<u8>, n: i64) RawPtr<u8> { null_ptr() }\n"
        "    release = (a: MutPtr<Counting>, p: RawPtr<u8>) void {\n"
        "        a.released = a.released + 1\n"
        "        free(p)\n"
        "    }\n"
        "})\n"
        "success = () bool {\n"
        "    c := Counting(acquired: 0, released: 0, fail_after: -1)\n"
        "    a := c.addr()\n"
        "    r: Result<actor.ActorHandle<Msg, Room>, IoError> := actor.try_spawn(a, 4, Room(n: 7))\n"
        "    r.match({\n"
        "        .Ok(h) => { h.free(a)  (c.acquired == 3) && (c.released == 3) },\n"
        "        .Err(e) => false\n"
        "    })\n"
        "}\n"
        "fail_state = () bool {\n"
        "    c := Counting(acquired: 0, released: 0, fail_after: 0)\n"
        "    r: Result<actor.ActorHandle<Msg, Room>, IoError> := actor.try_spawn(c.addr(), 4, Room(n: 7))\n"
        "    r.match({\n"
        "        .Err(e) => e.match({ .NotFound => (c.acquired == 0) && (c.released == 0), _ => false }),\n"
        "        .Ok(h) => false\n"
        "    })\n"
        "}\n"
        "fail_queue = () bool {\n"
        "    c := Counting(acquired: 0, released: 0, fail_after: 2)\n"
        "    r: Result<actor.ActorHandle<Msg, Room>, IoError> := actor.try_spawn(c.addr(), 4, Room(n: 7))\n"
        "    r.match({\n"
        "        .Err(e) => e.match({ .NotFound => (c.acquired == 2) && (c.released == 2), _ => false }),\n"
        "        .Ok(h) => false\n"
        "    })\n"
        "}\n"
        "main = () i32 {\n"
        "    (success() && fail_state() && fail_queue()).to_exit()\n"
        "}\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ── U2/fuzz #2b/P3: undefined name in VALUE/ARG position is rejected (was check=ok → leaked cc errors) ──
def test_zenc_check_rejects_undefined_name_in_value_position():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text("main = () i32 { undefined_thing }\n")
    r = subprocess.run([zenc, "check", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode != 0 and "undefined name" in r.stderr, r.stderr


def test_zenc_check_rejects_undefined_name_in_arg_position():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text("id = (n: i32) i32 { n }\nmain = () i32 { id(undefined_thing) }\n")
    r = subprocess.run([zenc, "check", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode != 0 and "undefined name" in r.stderr, r.stderr


def test_p3_does_not_false_reject_true_false_or_sizeof_or_bound_locals():
    """Guard the P3 false-positives: `true`/`false` as values, `sizeof(T)` (T is a type, not a value), and
    a local bound to a void/generic value all stay ACCEPTED (the membership-based var_err)."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "Box<T>: { v: T }\n"
        "mk<T> = (x: T) i64 { b := Box<T>(v: x)  sizeof(T) }\n"   # sizeof(T) + a generic-struct-bound local
        "pick = (c: bool) bool { c.match ({ true => false, false => true }) }\n"  # true/false as VALUES
        "main = () i32 { 0 }\n"
    )
    assert subprocess.run([zenc, "check", str(d / "p.zen")]).returncode == 0


def test_generic_template_local_can_shadow_parameter():
    """Generic inlining must respect lexical locals. A template local named like a parameter used to be
    substituted back to the caller argument, so `x.v` became `7.v` after inlining."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "Box<T>: { v: T }\n"
        "unwrap<T> = (x: T) T {\n"
        "    x := Box<T>(v: x)\n"
        "    x.v\n"
        "}\n"
        "main = () i32 { unwrap(7) }\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 7, r.stderr


def test_generic_template_local_does_not_capture_caller_local():
    """Inlined template locals are alpha-renamed so a caller local with the same source name is not
    captured by generated C such as `int32_t value = value`."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "id<T> = (x: T) T {\n"
        "    value := x\n"
        "    value\n"
        "}\n"
        "main = () i32 {\n"
        "    value := 7\n"
        "    id(value)\n"
        "}\n"
    )
    c = subprocess.run([zenc, "emit", str(d / "p.zen")], capture_output=True, text=True)
    assert c.returncode == 0, c.stderr
    assert "int32_t value = value" not in c.stdout
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 7, r.stderr


def test_zenc_check_keeps_match_payload_bindings_in_scope():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "R*: Ok(i32) | Err\n"
        "main = () i32 { r := .Ok(7)  r.match({ .Ok(v) => v, .Err => 0 }) }\n"
    )
    r = subprocess.run([zenc, "check", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_zenc_emit_switches_enum_matches_but_keeps_bool_ternary():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "enum.zen").write_text(
        "R*: Ok(i32) | Err\n"
        "f* = (r: R) i32 { r.match({ .Ok(v) => v + 1, .Err => 0 }) }\n"
    )
    r = subprocess.run([zenc, "emit", str(d / "enum.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "switch (_subj.tag)" in r.stdout
    assert "case R_Ok:" in r.stdout

    (d / "bool.zen").write_text("f* = (b: bool) i32 { b.match({ true => 1, false => 0 }) }\n")
    r = subprocess.run([zenc, "emit", str(d / "bool.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "return (b ? 1 : 0);" in r.stdout
    assert "switch" not in r.stdout

    (d / "run.zen").write_text(
        "R*: Ok(i32) | Err\n"
        "f = (r: R) i32 { r.match({ .Ok(v) => { x := v + 1  x }, .Err => 0 }) }\n"
        "main = () i32 { (f(.Ok(6)) == 7).match({ true => 0, false => 1 }) }\n"
    )
    r = subprocess.run([zenc, "run", str(d / "run.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_zenc_check_threads_block_let_bindings():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "main = () i32 { true.match({ true => { x := 4  x }, false => 0 }) }\n"
    )
    r = subprocess.run([zenc, "check", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ── review fix #1: HOFs — calling a fn-typed PARAM works (named fn AND lambda args) ──────────────────
def test_zenc_run_hof_named_fn_and_lambda():
    """`apply = (f: (i32) i32, x: i32) i32 { f(x) }` — the call f(x) was false-rejected as undefined-name
    (validator missed the FnT-param case), and a NAMED fn arg mono-inlined to a bare var (bad C)."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "apply = (f: (i32) i32, x: i32) i32 { f(x) }\n"
        "twice = (n: i32) i32 { n * 2 }\n"
        "main = () i32 { apply(twice, 11) + apply((n){ n + 9 }, 11) }\n"   # 22 + 20 = 42
    )
    assert subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True).returncode == 42


def test_generic_hof_lambda_captures_caller_local():
    """A lambda passed into a generic template can read caller locals after the template is inlined."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "apply<T> = (f: (T) T, x: T) T { f(x) }\n"
        "main = () i32 {\n"
        "    base := 5\n"
        "    apply((n){ n + base }, 37)\n"
        "}\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 42, r.stderr


# ── review fix #3: mid-file garbage is a SYNTAX ERROR, not silently-dropped decls ────────────────────
def test_zenc_check_rejects_midfile_garbage():
    """A truncated/garbage region used to make `check` say ok while silently DROPPING every decl after it
    (then run said "no main"). Now: kind 14 syntax-error sentinel per unparseable token, later decls kept."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text("good = () i32 { 1 }\n@@@ !!!\nmain = () i32 { good() + 6 }\n")
    r = subprocess.run([zenc, "check", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode != 0 and "syntax error" in r.stderr, r.stderr


# ── review fix #4 / fuzz #8: leading-paren statement glue ────────────────────────────────────────────
def test_zenc_no_leading_paren_statement_glue():
    """`b := id` then a new line `(4)` used to glue into `b := id(4)` (a silent miscompile when the RHS
    names a fn). A `(` that opens a NEW LINE is its own statement, mirroring the `[` same-line rule."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ println } = std.text.fmt\n"
        "id = (n: i64) i64 { n }\n"
        "main = () i32 {\n  b := id\n  (4)\n  println(7)\n  0\n}\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout == "7\n", (r.returncode, r.stdout, r.stderr)


# ── census #5: bitwise operators & | ^ << >> (were SILENT wrong-answers via statement-glue) ──────────
def test_zenc_bitwise_operators():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text("main = () i32 { (12 & 10) + (12 | 3) * 10 + (12 ^ 10) * 100 + (1 << 4) - (64 >> 2) }\n")
    # 8 + 150 + 600 + 16 - 16 = 758 % 256 = 246
    assert subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True).returncode == 246
    # bitwise binds TIGHTER than comparison: 6 & 3 == 2 → (6&3)==2 → true
    (d / "q.zen").write_text("main = () i32 { (6 & 3 == 2).match ({ true => 1, false => 0 }) }\n")
    assert subprocess.run([zenc, "run", str(d / "q.zen")], capture_output=True).returncode == 1


# ── census #6: explicit int casts to_i32/to_i64/to_u8 (no narrowing path existed at all) ─────────────
def test_zenc_int_cast_intrinsics():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text('{ len } = std.text.str\nmain = () i32 { n := len("hello")  to_i32(n) }\n')
    assert subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True).returncode == 5
    (d / "q.zen").write_text("main = () i32 { big := 4294967298  to_i32(big) }\n")   # 2^32+2 truncates to 2
    assert subprocess.run([zenc, "run", str(d / "q.zen")], capture_output=True).returncode == 2


def test_integer_literal_fits_i64_parameter_without_cast():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "needs64 = (n: i64) i32 { (n == 16).match({ true => 0, false => 1 }) }\n"
        "main = () i32 { needs64(16) }\n"
    )
    assert subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True).returncode == 0


def test_struct_body_inherent_methods_dispatch_with_ufcs():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "Box*: {\n"
        "    n: i32\n"
        "    inc = (b: Box) i32 { b.n + 1 }\n"
        "    add = (b: Box, x: i32) i32 { b.n + x }\n"
        "}\n"
        "main = () i32 { b := Box(n: 2)  b.inc() + b.add(4) }\n"
    )
    assert subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True).returncode == 9


def test_generic_struct_body_inherent_methods_dispatch_with_ufcs():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "Box<T>: {\n"
        "    v: T\n"
        "    get = (b: Box<T>) T { b.v }\n"
        "}\n"
        "main = () i32 { b := Box<i32>(v: 7)  b.get() }\n"
    )
    assert subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True).returncode == 7


def test_inherent_methods_overload_by_receiver_type():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "Red*: {\n"
        "    _: i32\n"
        "    turnBlue = (r: Red) Blue { Blue(_: 0) }\n"
        "    score = (r: Red) i32 { 10 }\n"
        "}\n"
        "Blue*: {\n"
        "    _: i32\n"
        "    score = (b: Blue) i32 { 32 }\n"
        "}\n"
        "main = () i32 { r := Red(_: 0)  b := r.turnBlue()  r.score() + b.score() }\n"
    )
    assert subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True).returncode == 42


def test_zenc_raw_intrinsics_have_at_spelling():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ println } = std.text.fmt\n"
        "main = () i32 { x := 41  p := @addr(x)  println(@load(p) + 1)  0 }\n")
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "42\n"
    (d / "bad.zen").write_text("main = () i32 { p := @malloc(8)  0 }\n")
    r = subprocess.run([zenc, "check", str(d / "bad.zen")], capture_output=True, text=True)
    assert r.returncode == 1
    assert "undefined name" in r.stderr


# ── census #8: C-keyword identifiers are mangled (fn `double` emitted verbatim → cc explosion) ───────
def test_zenc_c_keyword_identifiers():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "double = (n: i32) i32 { n * 2 }\n"
        "P*: { int: i32 }\n"
        "main = () i32 { short := P(int: double(20))  short.int + 2 }\n"
    )
    assert subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True).returncode == 42


# ── census #11: the 1024-decl cap silently truncated big programs ────────────────────────────────────
def test_zenc_2000_decl_program():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    fns = "\n".join(f"f{i} = () i32 {{ {i % 100} }}" for i in range(2000))
    (d / "p.zen").write_text(fns + "\nmain = () i32 { f1999() }\n")
    assert subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True).returncode == 99


# ── outsider kit: every example must build and run (the quickstart points at these) ──────────────────
def test_all_examples_run():
    zenc = _zenc()
    names = sorted(p.stem for p in (ROOT / "examples").glob("*.zen"))
    assert {"hello", "shapes", "stats", "actor_demo"} <= set(names)
    for name in names:
        r = subprocess.run([zenc, "run", str(ROOT / "examples" / f"{name}.zen")], capture_output=True, text=True)
        assert r.returncode == 0, (name, r.returncode, r.stderr)


def test_zenc_help_version_and_zen_root():
    zenc = _zenc()
    h = subprocess.run([zenc, "--help"], capture_output=True, text=True)
    assert h.returncode == 0 and "usage:" in h.stdout
    assert "zenc doc" in h.stdout
    v = subprocess.run([zenc, "--version"], capture_output=True, text=True)
    assert v.returncode == 0 and "zenc" in v.stdout
    # bare `zenc` is TTY-gated: on a TERMINAL it prints usage (exit 2); with PIPED stdin it stays the
    # classic source→C filter the oracle depends on. Under pytest stdin is a pipe, so exercise the filter.
    bare = subprocess.run([zenc], capture_output=True, text=True, input="test* = () i32 { 1 }\n")
    assert bare.returncode == 0 and "zslice" in bare.stdout
    # a relocated binary works when ZEN_ROOT points at the checkout
    d = Path(tempfile.mkdtemp())
    moved = d / "zenc-moved"
    moved.write_bytes(Path(zenc).read_bytes()); moved.chmod(0o755)
    (d / "p.zen").write_text("main = () i32 { 42 }\n")
    import os
    env = dict(os.environ, ZEN_ROOT=str(ROOT))
    assert subprocess.run([str(moved), "run", str(d / "p.zen")], capture_output=True, env=env).returncode == 42


def test_zenc_fmt_formats_checks_and_is_idempotent():
    zenc = _zenc()
    fixtures = sorted((ROOT / "tests" / "fixtures" / "fmt").glob("*_unformatted.zen"))
    assert fixtures
    for unformatted in fixtures:
        d = Path(tempfile.mkdtemp())
        src = d / "p.zen"
        shutil.copyfile(unformatted, src)
        expected = unformatted.with_name(unformatted.name.replace("_unformatted.zen", "_formatted.zen")).read_text()

        r = subprocess.run([zenc, "fmt", "--check", str(src)], capture_output=True, text=True)
        assert r.returncode == 1
        assert "needs formatting" in r.stderr

        r = subprocess.run([zenc, "fmt", str(src)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        assert src.read_text() == expected

        r = subprocess.run([zenc, "fmt", "--check", str(src)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr

        before = src.read_text()
        r = subprocess.run([zenc, "fmt", str(src)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        assert src.read_text() == before


def test_zenc_doc_lists_public_declarations_and_nearby_docs():
    zenc = _zenc()

    std = subprocess.run([zenc, "doc", "std.text.fmt"], capture_output=True, text=True)
    assert std.returncode == 0, std.stderr
    assert "# std.text.fmt" in std.stdout
    assert "Display*: {" in std.stdout
    assert "write_int_in*<A> = (a: MutPtr<A>, n: i64) i64" in std.stdout
    assert "write_float_in*<A> = (a: MutPtr<A>, x: f64) i64" in std.stdout
    assert "try_write_int_in*<A> = (a: MutPtr<A>, n: i64) Result<i64, IoError>" in std.stdout
    assert "try_write_float_in*<A> = (a: MutPtr<A>, x: f64) Result<i64, IoError>" in std.stdout
    assert "print*<T> = (x: T) i64 { x.fmt_print() }" in std.stdout
    assert "println*<T> = (x: T) i64 { x.fmt_println() }" in std.stdout
    assert "Display is the current type-directed print surface" in std.stdout
    assert "print_owned" not in std.stdout

    string = subprocess.run([zenc, "doc", "std.text.string"], capture_output=True, text=True)
    assert string.returncode == 0, string.stderr
    assert "init*<A>" in string.stdout
    assert "new_in*<A>" in string.stdout
    assert "try_init*<A>" in string.stdout
    assert "try_new_in*<A>" in string.stdout
    assert "try_new*<A>" not in string.stdout
    assert "new* = " not in string.stdout

    own = subprocess.run([zenc, "doc", "std.mem.own"], capture_output=True, text=True)
    assert own.returncode == 0, own.stderr
    assert "new_in*<A, T>" in own.stdout
    assert "try_new_in*<A, T>" in own.stdout
    assert "new*<T>" not in own.stdout
    assert "try_new*<T>" not in own.stdout
    assert "release = (o: Own<T>)" not in own.stdout

    rc = subprocess.run([zenc, "doc", "std.mem.rc"], capture_output=True, text=True)
    assert rc.returncode == 0, rc.stderr
    assert "new_in*<A, T>" in rc.stdout
    assert "try_new_in*<A, T>" in rc.stdout
    assert "new*<T>" not in rc.stdout
    assert "try_new*<T>" not in rc.stdout
    assert "drop = (r: Rc<T>)" not in rc.stdout

    arc = subprocess.run([zenc, "doc", "std.mem.arc"], capture_output=True, text=True)
    assert arc.returncode == 0, arc.stderr
    assert "new_in*<A, T>" in arc.stdout
    assert "try_new_in*<A, T>" in arc.stdout
    assert "new*<T>" not in arc.stdout
    assert "try_new*<T>" not in arc.stdout
    assert "drop = (r: Arc<T>)" not in arc.stdout

    actor = subprocess.run([zenc, "doc", "std.concurrent.actor"], capture_output=True, text=True)
    assert actor.returncode == 0, actor.stderr
    assert "ActorRef*<M>: {" in actor.stdout
    assert "ReplyRef*<T>: {" in actor.stdout
    assert "ActorEngine*<M>: {" in actor.stdout
    assert "ActorCell*<M>: {" in actor.stdout
    assert "cell*<A, M>" in actor.stdout
    assert "spawn*<A, M, ActorT>" in actor.stdout
    assert "try_spawn*<A, M, ActorT>" in actor.stdout
    assert "try_cell*<A, M>" in actor.stdout
    assert "reply*<" not in actor.stdout
    assert "try_reply*<" not in actor.stdout
    assert "Mailbox" not in actor.stdout
    assert "ActorSystem" not in actor.stdout
    assert "ActorState" not in actor.stdout

    core_slice = subprocess.run([zenc, "doc", "std.core.slice"], capture_output=True, text=True)
    assert core_slice.returncode == 0, core_slice.stderr
    assert "buf_in*<A, T>" in core_slice.stdout
    assert "try_buf_in*<A, T>" in core_slice.stdout
    assert "buf*<A, T>" in core_slice.stdout
    assert "try_buf*<A, T>" in core_slice.stdout
    assert "dup*<A, T>" in core_slice.stdout
    assert "node*<A, T>" in core_slice.stdout
    assert "concat*<A, T>" in core_slice.stdout
    assert "buf*<T>" not in core_slice.stdout
    assert "try_buf*<T>" not in core_slice.stdout
    assert "dup*<T>" not in core_slice.stdout
    assert "node*<T>" not in core_slice.stdout
    assert "concat*<T>" not in core_slice.stdout
    assert "nbuf" not in core_slice.stdout
    assert "try_nbuf" not in core_slice.stdout

    bytes_doc = subprocess.run([zenc, "doc", "std.text.bytes"], capture_output=True, text=True)
    assert bytes_doc.returncode == 0, bytes_doc.stderr
    assert "at* = (s: str, i: i32) u8" in bytes_doc.stdout
    assert "is_digit*" in bytes_doc.stdout
    assert "byte_at" not in bytes_doc.stdout

    cown = subprocess.run([zenc, "doc", "std.concurrent.cown"], capture_output=True, text=True)
    assert cown.returncode == 0, cown.stderr
    assert "buf*<A>" in cown.stdout
    assert "try_buf*<A>" in cown.stdout
    assert "file*<A> = (alloc: MutPtr<A>, path: str)" in cown.stdout
    assert "file_in*<A>" in cown.stdout
    assert "buf_alloc" not in cown.stdout
    assert "buf_free" not in cown.stdout
    assert "file_open" not in cown.stdout

    runtime = subprocess.run([zenc, "doc", "std.concurrent.runtime"], capture_output=True, text=True)
    assert runtime.returncode == 0, runtime.stderr
    assert "sync_in*<A> = (backing: MutPtr<A>, cap: i64) SyncArena" in runtime.stdout
    assert "async_in*<A> = (backing: MutPtr<A>, cap: i64) AsyncArena" in runtime.stdout
    assert "sync*<A> = (backing: MutPtr<A>, cap: i64) SyncArena" in runtime.stdout
    assert "async*<A> = (backing: MutPtr<A>, cap: i64) AsyncArena" in runtime.stdout
    assert "sync* = (cap: i64) SyncArena" not in runtime.stdout
    assert "async* = (cap: i64) AsyncArena" not in runtime.stdout
    assert "sync_arena" not in runtime.stdout
    assert "async_arena" not in runtime.stdout

    coroutine = subprocess.run([zenc, "doc", "std.concurrent.coroutine"], capture_output=True, text=True)
    assert coroutine.returncode == 0, coroutine.stderr
    assert "try_spawn_in*<A>" in coroutine.stdout
    assert "try_spawn*<A>" in coroutine.stdout

    sched = subprocess.run([zenc, "doc", "std.concurrent.sched"], capture_output=True, text=True)
    assert sched.returncode == 0, sched.stderr
    assert "run_in*<A>" in sched.stdout
    assert "try_run_in*<A>" in sched.stdout
    assert "try_run*<A>" in sched.stdout

    alloc = subprocess.run([zenc, "doc", "std.mem.alloc"], capture_output=True, text=True)
    assert alloc.returncode == 0, alloc.stderr
    assert "default* = () Heap" in alloc.stdout
    assert "system_allocator" not in alloc.stdout
    assert "default_allocator" not in alloc.stdout

    raw = subprocess.run([zenc, "doc", "std.mem.raw"], capture_output=True, text=True)
    assert raw.returncode == 0, raw.stderr
    assert "try_alloc* = (n: i64) Result<RawPtr<u8>, IoError>" in raw.stdout
    assert "try_zeroed* = (n: i64) Result<RawPtr<u8>, IoError>" in raw.stdout
    assert "of*<T>" in raw.stdout
    assert "try_of*<T>" in raw.stdout
    assert "buf_of" not in raw.stdout
    assert "new_i32" not in raw.stdout
    assert "new_u8" not in raw.stdout

    arena = subprocess.run([zenc, "doc", "std.mem.arena"], capture_output=True, text=True)
    assert arena.returncode == 0, arena.stderr
    assert "make_in*<A>" in arena.stdout
    assert "try_make_in*<A>" in arena.stdout
    assert "arena_new" not in arena.stdout
    assert "try_arena_new" not in arena.stdout

    vec = subprocess.run([zenc, "doc", "std.collections.vec"], capture_output=True, text=True)
    assert vec.returncode == 0, vec.stderr
    assert "of*<T, A>" in vec.stdout
    assert "try_of*<T, A>" in vec.stdout
    assert "vec_of" not in vec.stdout
    assert "try_vec_of" not in vec.stdout

    maps = subprocess.run([zenc, "doc", "std.collections.map"], capture_output=True, text=True)
    assert maps.returncode == 0, maps.stderr
    assert "of*<T, A>" in maps.stdout
    assert "try_of*<T, A>" in maps.stdout
    assert "map*<T" not in maps.stdout
    assert "try_map" not in maps.stdout

    iters = subprocess.run([zenc, "doc", "std.collections.iter"], capture_output=True, text=True)
    assert iters.returncode == 0, iters.stderr
    assert "map*<A> = (a: MutPtr<A>, xs: [i32], f: (i32) i32) [i32]" in iters.stdout
    assert "try_map*<A> = (a: MutPtr<A>, xs: [i32], f: (i32) i32) Result<[i32], IoError>" in iters.stdout
    assert "filter*<A> = (a: MutPtr<A>, xs: [i32], keep: (i32) bool) [i32]" in iters.stdout
    assert "try_filter*<A> = (a: MutPtr<A>, xs: [i32], keep: (i32) bool) Result<[i32], IoError>" in iters.stdout
    assert "map* = (xs: [i32]" not in iters.stdout
    assert "filter* = (xs: [i32]" not in iters.stdout

    trace = subprocess.run([zenc, "doc", "std.mem.trace"], capture_output=True, text=True)
    assert trace.returncode == 0, trace.stderr
    assert "Rc*<T>: {" in trace.stdout
    assert "tracked_in*<A, T>" in trace.stdout
    assert "tracked*<A, T> = (alloc: MutPtr<A>, x: T) Rc<T>" in trace.stdout
    assert "try_tracked*<A, T> = (alloc: MutPtr<A>, x: T) Result<Rc<T>, IoError>" in trace.stdout
    assert "root_in*<A, T>" in trace.stdout
    assert "root*<A, T> = (alloc: MutPtr<A>, r: Rc<T>) void" in trace.stdout
    assert "try_root_in*<A, T>" in trace.stdout
    assert "try_root*<A, T> = (alloc: MutPtr<A>, r: Rc<T>) Result<i32, IoError>" in trace.stdout
    assert "child*<T>" in trace.stdout
    assert "set_kid* = (parent: Rc<Node>, child: Rc<Node>) void" in trace.stdout
    assert "collect_in*<A>" in trace.stdout
    assert "collect*<A> = (alloc: MutPtr<A>) void" in trace.stdout
    assert "try_collect_in*<A>" in trace.stdout
    assert "try_collect*<A> = (alloc: MutPtr<A>) Result<i32, IoError>" in trace.stdout
    assert "tracked*<T> = (x: T)" not in trace.stdout
    assert "collect* = () void" not in trace.stdout
    assert "hcount*" not in trace.stdout
    assert "list_push*" not in trace.stdout
    assert "trace_child*" not in trace.stdout
    assert "node_set_kid*" not in trace.stdout
    assert "cc_mark*" not in trace.stdout
    assert "blk_drop*" not in trace.stdout

    text = subprocess.run([zenc, "doc", "std.text.str"], capture_output=True, text=True)
    assert text.returncode == 0, text.stderr
    assert "dup_bytes*<A> = (a: MutPtr<A>, s: str) [u8]" in text.stdout
    assert "try_dup_bytes*<A> = (a: MutPtr<A>, s: str) Result<[u8], IoError>" in text.stdout
    assert "substr*<A> = (a: MutPtr<A>, s: str, start: i64, n: i64) str" in text.stdout
    assert "try_substr*<A> = (a: MutPtr<A>, s: str, start: i64, n: i64) Result<str, IoError>" in text.stdout
    assert "at* = (s: str, i: i64) u8" in text.stdout
    assert "char_at" not in text.stdout
    assert "ParseError*: NoDigits | Trailing(u8) | Overflow" in text.stdout
    assert "try_parse_int* = (s: str) Result<i64, ParseError>" in text.stdout
    assert "what made try_parse_int refuse" in text.stdout

    num = subprocess.run([zenc, "doc", "std.text.num"], capture_output=True, text=True)
    assert num.returncode == 0, num.stderr
    assert "integer_in*<A> = (a: MutPtr<A>, n: i64) String" in num.stdout
    assert "integer*<A> = (a: MutPtr<A>, n: i64) String" in num.stdout
    assert "try_integer_in*<A> = (a: MutPtr<A>, n: i64) Result<String, IoError>" in num.stdout
    assert "try_integer*<A> = (a: MutPtr<A>, n: i64) Result<String, IoError>" in num.stdout
    assert "float_in*<A> = (a: MutPtr<A>, x: f64) String" in num.stdout
    assert "float*<A> = (a: MutPtr<A>, x: f64) String" in num.stdout
    assert "try_float_in*<A> = (a: MutPtr<A>, x: f64) Result<String, IoError>" in num.stdout
    assert "try_float*<A> = (a: MutPtr<A>, x: f64) Result<String, IoError>" in num.stdout
    assert "int_string" not in num.stdout
    assert "float_string" not in num.stdout
    assert "int_to_str" not in num.stdout
    assert "float_to_str" not in num.stdout

    io = subprocess.run([zenc, "doc", "std.io.file"], capture_output=True, text=True)
    assert io.returncode == 0, io.stderr
    assert "out* = (s: str) i64" in io.stdout
    assert "out_bytes* = (bytes: [u8]) i64" in io.stdout
    assert "contents_in*<A> = (a: MutPtr<A>, path: str) Result<str, IoError>" in io.stdout
    assert "contents*<A> = (a: MutPtr<A>, path: str) Result<str, IoError>" in io.stdout
    assert "contents* = (path: str) Result<str, IoError>" not in io.stdout
    assert "save* = (path: str, data: str, n: i64) Result<i64, IoError>" in io.stdout
    assert "shell* = (cmd: str) i32" in io.stdout
    assert "stdout*" not in io.stdout
    assert "stdout_bytes*" not in io.stdout
    assert "run*" not in io.stdout
    assert "read_file" not in io.stdout
    assert "write_file" not in io.stdout
    assert "Reads a whole file into an allocator-owned NUL-terminated buffer." in io.stdout

    d = Path(tempfile.mkdtemp())
    src = d / "doc.zen"
    src.write_text(
        "// Public counter type\n"
        "Counter*: { n: i32 }\n"
        "\n"
        "helper = () i32 { 1 }\n"
        "visible* = () i32 { 2 }\n"
    )
    local = subprocess.run([zenc, "doc", str(src)], capture_output=True, text=True)
    assert local.returncode == 0, local.stderr
    assert f"# {src}" in local.stdout
    assert "Public counter type" in local.stdout
    assert "Counter*: { n: i32 }" in local.stdout
    assert "visible* = () i32 { 2 }" in local.stdout
    assert "helper" not in local.stdout


def test_std_docs_do_not_export_legacy_flat_prefix_names():
    zenc = _zenc()
    legacy_by_module = {
        "std.text.fmt": [
            "print_int",
            "println_int",
            "print_owned",
        ],
        "std.collections.vec": [
            "vec_of",
            "try_vec_of",
            "vpush",
            "vgrow",
            "vfree",
            "vitems",
            "vlen",
        ],
        "std.collections.map": [
            "map_of",
            "try_map_of",
            "mput",
            "mget",
            "mhas",
            "mlen",
            "mfree",
        ],
        "std.mem.rc": [
            "rc_new",
            "rc_get",
            "rc_clone",
            "rc_drop",
            "rc_count",
        ],
        "std.mem.arc": [
            "arc_new",
            "arc_get",
            "arc_clone",
            "arc_drop",
            "arc_count",
        ],
        "std.mem.own": [
            "own_new",
            "own_clone",
            "own_ptr",
            "own_release",
        ],
        "std.mem.arena": [
            "arena_new",
            "try_arena_new",
        ],
        "std.mem.raw": [
            "buf_of",
            "new_i32",
            "new_u8",
        ],
        "std.mem.trace": [
            "trace_child",
            "node_set_kid",
            "hcount",
            "list_push",
            "cc_mark",
            "blk_drop",
        ],
        "std.core.slice": [
            "nbuf",
            "try_nbuf",
        ],
        "std.text.bytes": [
            "byte_at",
        ],
        "std.text.str": [
            "char_at",
            "str_parse_int",
        ],
        "std.text.num": [
            "int_string",
            "float_string",
            "int_to_str",
            "float_to_str",
        ],
        "std.io.file": [
            "read_file",
            "write_file",
            "run_cmd",
            "write_stdout",
            "write_stdout_bytes",
        ],
        "std.concurrent.runtime": [
            "sync_arena",
            "async_arena",
        ],
        "std.concurrent.cown": [
            "buf_alloc",
            "buf_free",
            "file_open",
            "file_wrap",
        ],
        "std.concurrent.actor": [
            "actor_ref",
            "actor_system",
            "run_actor",
            "make_reply",
        ],
    }

    for module, legacy_names in legacy_by_module.items():
        doc = subprocess.run([zenc, "doc", module], capture_output=True, text=True)
        assert doc.returncode == 0, (module, doc.stderr)
        for legacy in legacy_names:
            assert legacy not in doc.stdout, f"{module} still exports legacy flat name {legacy}"


def test_compiler_genc_docs_expose_allocator_threaded_helpers_only():
    zenc = _zenc()
    doc = subprocess.run([zenc, "doc", str(ROOT / "zen" / "compiler" / "genc.zen")],
                         capture_output=True, text=True)
    assert doc.returncode == 0, doc.stderr
    for helper in [
        "mangle_str_in*",
        "impl_cname_in*",
        "fnt_from_func_in*",
        "ty_cname_in*",
        "subst_ty_in*",
    ]:
        assert helper in doc.stdout
    for legacy in [
        "mangle_str*",
        "impl_cname*",
        "fnt_from_func*",
        "ty_cname*",
        "subst_ty*",
    ]:
        assert legacy not in doc.stdout


def test_zenc_run_raw_memory_typed_buffer_of():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "raw = std.mem.raw\n"
        "main = () i32 {\n"
        "    xs := raw.of(7, 3)\n"
        "    xs[1] = 35\n"
        "    n := xs[0] + xs[1]\n"
        "    raw.release(xs.ptr)\n"
        "    n\n"
        "}\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 42, r.stderr


def test_zenc_run_raw_memory_try_result_paths():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "raw = std.mem.raw\n"
        "{ Result, IoError } = std.core.result\n"
        "{ to_exit } = std.core.bool\n"
        "ptr_ok = () bool {\n"
        "    p0: Result<RawPtr<u8>, IoError> := raw.try_alloc(8)\n"
        "    p0.match({\n"
        "        .Ok(p) => {\n"
        "            raw.release(p)\n"
        "            p1: Result<RawPtr<u8>, IoError> := raw.try_zeroed(1)\n"
        "            p1.match({ .Ok(q) => { raw.release(q)  true }, .Err(e) => false })\n"
        "        },\n"
        "        .Err(e) => false\n"
        "    })\n"
        "}\n"
        "slice_ok = () bool {\n"
        "    r: Result<[i32], IoError> := raw.try_of(7, 3)\n"
        "    r.match({\n"
        "        .Ok(xs) => {\n"
        "            xs[1] = 35\n"
        "            ok := (xs[0] + xs[1]) == 42\n"
        "            raw.release(xs.ptr)\n"
        "            ok\n"
        "        },\n"
        "        .Err(e) => false\n"
        "    })\n"
        "}\n"
        "slice_err = () bool {\n"
        "    r: Result<[i32], IoError> := raw.try_of(7, 0)\n"
        "    r.match({\n"
        "        .Err(e) => e.match({ .NotFound => true, _ => false }),\n"
        "        .Ok(xs) => false\n"
        "    })\n"
        "}\n"
        "main = () i32 { (ptr_ok() && slice_ok() && slice_err()).to_exit() }\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ── P3 / #100: the `_ => body` bool-guard parsed as if bare — swallowed the rest of the function ─────
def test_bool_guard_wild_with_body():
    """`(c).match({ true => { return X }, _ => {} })` — parse_bool_wild assumed a BARE `_` and resumed
    parsing inside the arm, silently dropping every statement after the match. All forms must work."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    for arm in ["_ => 0", "_ => {}", "_ => {},", "_"]:
        (d / "p.zen").write_text(
            "{ println } = std.text.fmt\n"
            "f = (n: i32) i32 {\n"
            f"  (n == 0).match ({{ true => {{ return 100 }}, {arm} }})\n"
            "  println(50)\n  n\n}\n"
            "main = () i32 { println(f(0))  println(f(7))  0 }\n"
        )
        r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
        assert r.returncode == 0 and r.stdout == "100\n50\n7\n", (arm, r.returncode, r.stdout, r.stderr)


# ── P3 / census #7: typed-local annotations are REAL (checked + drive inference + emit the C type) ───
def test_typed_local_annotations_honored():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    # (1) an i64 accumulator IS int64_t: 2^32 survives, (a+2^32)/2^30 = 4
    (d / "a.zen").write_text("main = () i32 { a: i64 := 0  a = a + 4294967296  to_i32(a / 1073741824) }\n")
    assert subprocess.run([zenc, "run", str(d / "a.zen")], capture_output=True).returncode == 4
    # (2) the fuzz-#7 escape hatch: an annotation gives a bare .None its enum
    (d / "b.zen").write_text(
        "Opt<T>: Some(T) | None\n"
        "u<T> = (o: Opt<T>) i32 { o.match ({ .Some(x) => x, .None => 7 }) }\n"
        "main = () i32 { o: Opt<i32> := .None  u(o) }\n"
    )
    assert subprocess.run([zenc, "run", str(d / "b.zen")], capture_output=True).returncode == 7
    # (3) a mismatching init is REJECTED
    (d / "c.zen").write_text('main = () i32 { x: i32 := "nope"  0 }\n')
    r = subprocess.run([zenc, "check", str(d / "c.zen")], capture_output=True, text=True)
    assert r.returncode != 0 and "does not fit" in r.stderr


# ── resolver triple-fix: generic-head dedup + multi-line imports + ns-region boundary ────────────────
def test_drop_and_fmt_coimport():
    """Generic decl heads (`new<T>* =`) were invisible to the per-name dedup (after_name_is_decl bailed
    at '<'), so std.mem.own + std.text.fmt co-import died on "duplicate top-level". Now dedup sees them."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text("{ println } = std.text.fmt\n{ Own } = std.mem.own\nmain = () i32 { println(7)  0 }\n")
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout == "7\n", (r.returncode, r.stdout, r.stderr)


def test_own_rc_arc_constructors_use_explicit_allocator_names():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "own.zen").write_text(
        "{ default } = std.mem.alloc\n"
        "{ Resource, new_in } = std.mem.own\n"
        "main = () i32 {\n"
        "    alloc := default()\n"
        "    o := alloc.addr().new_in(Resource(id: 7, slot: 0))\n"
        "    n := o.get().id\n"
        "    o.release_in(alloc.addr())\n"
        "    n\n"
        "}\n"
    )
    assert subprocess.run([zenc, "run", str(d / "own.zen")], capture_output=True, text=True).returncode == 7

    (d / "rc.zen").write_text(
        "{ default } = std.mem.alloc\n"
        "{ new_in } = std.mem.rc\n"
        "{ to_exit } = std.core.bool\n"
        "main = () i32 {\n"
        "    alloc := default()\n"
        "    r := alloc.addr().new_in(41)\n"
        "    r2 := r.clone()\n"
        "    two := r.count() == 2\n"
        "    r.drop_in(alloc.addr())\n"
        "    one := r2.count() == 1\n"
        "    value := r2.get() == 41\n"
        "    r2.drop_in(alloc.addr())\n"
        "    (two && one && value).to_exit()\n"
        "}\n"
    )
    r = subprocess.run([zenc, "run", str(d / "rc.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

    (d / "arc.zen").write_text(
        "{ default } = std.mem.alloc\n"
        "{ new_in } = std.mem.arc\n"
        "{ to_exit } = std.core.bool\n"
        "main = () i32 {\n"
        "    alloc := default()\n"
        "    r := alloc.addr().new_in(41)\n"
        "    r2 := r.clone()\n"
        "    two := r.count() == 2\n"
        "    r.drop_in(alloc.addr())\n"
        "    one := r2.count() == 1\n"
        "    value := r2.get() == 41\n"
        "    r2.drop_in(alloc.addr())\n"
        "    (two && one && value).to_exit()\n"
        "}\n"
    )
    r = subprocess.run([zenc, "run", str(d / "arc.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_own_rc_arc_reject_default_allocator_wrappers():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    cases = {
        "own_new.zen": "{ Resource, new } = std.mem.own\nmain = () i32 { o := new(Resource(id: 1, slot: 0))  0 }\n",
        "own_try_new.zen": "{ Resource, try_new } = std.mem.own\nmain = () i32 { r := try_new(Resource(id: 1, slot: 0))  0 }\n",
        "own_release.zen": (
            "{ default } = std.mem.alloc\n"
            "{ Resource, new_in } = std.mem.own\n"
            "main = () i32 { a := default()  o := a.addr().new_in(Resource(id: 1, slot: 0))  o.release()  0 }\n"
        ),
        "rc_new.zen": "{ new } = std.mem.rc\nmain = () i32 { r := new(1)  0 }\n",
        "rc_try_new.zen": "{ try_new } = std.mem.rc\nmain = () i32 { r := try_new(1)  0 }\n",
        "rc_drop.zen": (
            "{ default } = std.mem.alloc\n"
            "{ new_in } = std.mem.rc\n"
            "main = () i32 { a := default()  r := a.addr().new_in(1)  r.drop()  0 }\n"
        ),
        "arc_new.zen": "{ new } = std.mem.arc\nmain = () i32 { r := new(1)  0 }\n",
        "arc_try_new.zen": "{ try_new } = std.mem.arc\nmain = () i32 { r := try_new(1)  0 }\n",
        "arc_drop.zen": (
            "{ default } = std.mem.alloc\n"
            "{ new_in } = std.mem.arc\n"
            "main = () i32 { a := default()  r := a.addr().new_in(1)  r.drop()  0 }\n"
        ),
    }
    for name, source in cases.items():
        src = d / name
        src.write_text(source)
        r = subprocess.run([zenc, "check", str(src)], capture_output=True, text=True)
        assert r.returncode != 0, f"{name} unexpectedly checked ok"


def test_own_rc_arc_try_constructors_return_result_paths():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ Allocator, malloc, free } = std.mem.alloc\n"
        "{ IoError } = std.core.result\n"
        "{ to_exit } = std.core.bool\n"
        "own = std.mem.own\n"
        "rc = std.mem.rc\n"
        "arc = std.mem.arc\n"
        "Counting: { left: i32, acquired: i32, released: i32 }\n"
        "Counting.impl(Allocator, {\n"
        "    acquire = (a: MutPtr<Counting>, n: i64) RawPtr<u8> {\n"
        "        a.acquired = a.acquired + 1\n"
        "        (a.left > 0).match({\n"
        "            true => {\n"
        "                a.left = a.left - 1\n"
        "                malloc(n)\n"
        "            },\n"
        "            false => null_ptr()\n"
        "        })\n"
        "    }\n"
        "    resize = (a: MutPtr<Counting>, p: RawPtr<u8>, n: i64) RawPtr<u8> { null_ptr() }\n"
        "    release = (a: MutPtr<Counting>, p: RawPtr<u8>) void {\n"
        "        a.released = a.released + 1\n"
        "        free(p)\n"
        "    }\n"
        "})\n"
        "not_found = (e: IoError) bool { e.match({ .NotFound => true, _ => false }) }\n"
        "own_success = () bool {\n"
        "    c := Counting(left: 1, acquired: 0, released: 0)\n"
        "    r := own.try_new_in(c.addr(), own.Resource(id: 7, slot: 0))\n"
        "    r.match({\n"
        "        .Ok(o) => {\n"
        "            ok := (o.get().id == 7) && (o.count() == 1) && (c.acquired == 1)\n"
        "            o.release_in(c.addr())\n"
        "            ok && (c.released == 1)\n"
        "        },\n"
        "        .Err(e) => false\n"
        "    })\n"
        "}\n"
        "rc_success = () bool {\n"
        "    c := Counting(left: 1, acquired: 0, released: 0)\n"
        "    r := rc.try_new_in(c.addr(), 41)\n"
        "    r.match({\n"
        "        .Ok(rc) => {\n"
        "            ok := (rc.get() == 41) && (rc.count() == 1) && (c.acquired == 1)\n"
        "            rc.drop_in(c.addr())\n"
        "            ok && (c.released == 1)\n"
        "        },\n"
        "        .Err(e) => false\n"
        "    })\n"
        "}\n"
        "arc_success = () bool {\n"
        "    c := Counting(left: 1, acquired: 0, released: 0)\n"
        "    r := arc.try_new_in(c.addr(), 41)\n"
        "    r.match({\n"
        "        .Ok(arc) => {\n"
        "            ok := (arc.get() == 41) && (arc.count() == 1) && (c.acquired == 1)\n"
        "            arc.drop_in(c.addr())\n"
        "            ok && (c.released == 1)\n"
        "        },\n"
        "        .Err(e) => false\n"
        "    })\n"
        "}\n"
        "own_failure = () bool {\n"
        "    c := Counting(left: 0, acquired: 0, released: 0)\n"
        "    r := own.try_new_in(c.addr(), own.Resource(id: 9, slot: 0))\n"
        "    r.match({\n"
        "        .Err(e) => e.not_found() && (c.acquired == 1) && (c.released == 0),\n"
        "        .Ok(o) => false\n"
        "    })\n"
        "}\n"
        "rc_failure = () bool {\n"
        "    c := Counting(left: 0, acquired: 0, released: 0)\n"
        "    r := rc.try_new_in(c.addr(), 9)\n"
        "    r.match({\n"
        "        .Err(e) => e.not_found() && (c.acquired == 1) && (c.released == 0),\n"
        "        .Ok(rc) => false\n"
        "    })\n"
        "}\n"
        "arc_failure = () bool {\n"
        "    c := Counting(left: 0, acquired: 0, released: 0)\n"
        "    r := arc.try_new_in(c.addr(), 9)\n"
        "    r.match({\n"
        "        .Err(e) => e.not_found() && (c.acquired == 1) && (c.released == 0),\n"
        "        .Ok(arc) => false\n"
        "    })\n"
        "}\n"
        "main = () i32 {\n"
        "    (own_success() && rc_success() && arc_success() && own_failure() && rc_failure() && arc_failure()).to_exit()\n"
        "}\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_zenc_check_rejects_owner_use_after_release_or_drop():
    """First checker-enforced memory rule: a local Own/Rc/Arc is consumed by release/drop in the
    same straight-line body, so using that same local afterwards is rejected before generic inlining
    lowers the call to raw pointer operations."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())

    own_src = d / "own_bad.zen"
    own_src.write_text(
        "{ default } = std.mem.alloc\n"
        "{ Resource, new_in } = std.mem.own\n"
        "main = () i32 {\n"
        "    alloc := default()\n"
        "    o := alloc.addr().new_in(Resource(id: 7, slot: 0))\n"
        "    o.release_in(alloc.addr())\n"
        "    o.get().id\n"
        "}\n"
    )
    r = subprocess.run([zenc, "check", str(own_src)], capture_output=True, text=True)
    assert r.returncode == 1
    assert f"zenc: {own_src}:7:5: error[ownership]: use of an owner after release/drop\n" in r.stderr
    assert "      o.get().id\n" in r.stderr
    assert _caret(5) in r.stderr
    assert "hint: after release/drop, bind a fresh owner instead of reusing the consumed local\n" in r.stderr

    rc_src = d / "rc_bad.zen"
    rc_src.write_text(
        "{ default } = std.mem.alloc\n"
        "{ new_in } = std.mem.rc\n"
        "main = () i32 {\n"
        "    alloc := default()\n"
        "    r := alloc.addr().new_in(41)\n"
        "    r.drop_in(alloc.addr())\n"
        "    r.get()\n"
        "}\n"
    )
    r = subprocess.run([zenc, "check", str(rc_src)], capture_output=True, text=True)
    assert r.returncode == 1
    assert f"zenc: {rc_src}:7:5: error[ownership]: use of an owner after release/drop\n" in r.stderr
    assert "      r.get()\n" in r.stderr
    assert _caret(5) in r.stderr

    arc_src = d / "arc_bad.zen"
    arc_src.write_text(
        "{ default } = std.mem.alloc\n"
        "{ new_in } = std.mem.arc\n"
        "main = () i32 {\n"
        "    alloc := default()\n"
        "    a := alloc.addr().new_in(41)\n"
        "    a.drop_in(alloc.addr())\n"
        "    a.get()\n"
        "}\n"
    )
    r = subprocess.run([zenc, "check", str(arc_src)], capture_output=True, text=True)
    assert r.returncode == 1
    assert f"zenc: {arc_src}:7:5: error[ownership]: use of an owner after release/drop\n" in r.stderr
    assert "      a.get()\n" in r.stderr
    assert _caret(5) in r.stderr


def test_zenc_check_rejects_scope_pointer_escape():
    """M5 lexical escape check: memory from `s.acquire(...)` lives in the scope's arena, which is freed
    on scope exit, so RETURNING it (directly, or via a local bound to it) compiles a use-after-free.
    The checker rejects it before generic inlining lowers the call to raw pointer ops. Scope's own
    `s.alloc.acquire(n)` accessor is NOT flagged (its receiver is the `.alloc` field, not the scope var),
    so std.scope itself and the colorless capstone body (which only loads a value out) still pass."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())

    # a local bound to s.acquire(...) is then returned -> escapes.
    via_let = d / "scope_escape_let.zen"
    via_let.write_text(
        "{ Scope, with_sync } = std.scope\n"
        "{ default } = std.mem.alloc\n"
        "leak = (s: MutPtr<Scope<A>>) RawPtr<u8> {\n"
        "    p := s.acquire(8)\n"
        "    p\n"
        "}\n"
        "main = () i32 { h := default()  h.addr().with_sync(4096, leak)  0 }\n"
    )
    r = subprocess.run([zenc, "check", str(via_let)], capture_output=True, text=True)
    assert r.returncode == 1, r.stderr
    assert f"zenc: {via_let}:5:5: error[scope-escape]: value from scope `s` escapes its scope" in r.stderr, r.stderr
    assert "      p\n" in r.stderr, r.stderr
    assert _caret(5) in r.stderr, r.stderr
    assert "hint: do not return a pointer from `s.acquire(...)`" in r.stderr, r.stderr

    # a direct trailing `s.acquire(...)` (the UFCS receiver IS the scope var) also escapes.
    direct = d / "scope_escape_direct.zen"
    direct.write_text(
        "{ Scope, with_sync } = std.scope\n"
        "{ default } = std.mem.alloc\n"
        "leak = (s: MutPtr<Scope<A>>) RawPtr<u8> { s.acquire(8) }\n"
        "main = () i32 { h := default()  h.addr().with_sync(4096, leak)  0 }\n"
    )
    r = subprocess.run([zenc, "check", str(direct)], capture_output=True, text=True)
    assert r.returncode == 1, r.stderr
    assert "error[scope-escape]: value from scope `s` escapes its scope" in r.stderr, r.stderr

    # GOOD: the colorless capstone binds `p := s.acquire(...)` but returns a loaded VALUE, not p — must pass.
    good = subprocess.run([zenc, "run", str(ZEN_FIXTURES / "scope_colorless_sync_async.zen")],
                          capture_output=True, text=True)
    assert good.returncode == 3, (good.returncode, good.stderr)


# ── std.text.str search/slice/parse: find/contains/substr/parse_int/starts_with/at ────────────────────────
def test_zenc_run_str_ops_edges():
    """The new std.text.str ops, hammered on edges: find at head/end/absent/empty-needle, substr CLAMPS
    out-of-range (start and n, both directions), at is 0 past either end, parse_int handles
    '-'/garbage-tail/all-garbage/empty (documented: no leading digits → 0) and i64-sized values."""
    zenc = _zenc()
    r = _run_fixture(zenc, "str_ops_edges.zen")
    assert r.returncode == 0, r.stderr
    assert r.stdout == "6\n-1\n0\n1\n2\n0\n1\n1\n0\n1\n0\n0\n-7\n12\n0\n123456789012\n", repr(r.stdout)


def test_zenc_run_str_allocator_result_variants():
    """std.text.str owns allocation through std.mem.alloc, with Result-returning variants for fallible paths."""
    zenc = _zenc()
    r = _run_fixture(zenc, "str_allocator_result.zen")
    assert r.returncode == 0, r.stderr
    assert r.stdout == "2\n3\n97\nell\nell\n0\n0\nor\nor\n", repr(r.stdout)


def test_zenc_check_rejects_default_str_allocating_helpers():
    """Borrowed text allocation is allocator-first; dup/substr no longer hide the default heap."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    cases = {
        "dup.zen": "text = std.text.str\nmain = () i32 { bs := text.dup_bytes(\"xy\")  0 }\n",
        "try_dup.zen": "text = std.text.str\nmain = () i32 { r := text.try_dup_bytes(\"xy\")  0 }\n",
        "substr.zen": "text = std.text.str\nmain = () i32 { s := text.substr(\"hello\", 1, 3)  0 }\n",
        "try_substr.zen": "text = std.text.str\nmain = () i32 { r := text.try_substr(\"hello\", 1, 3)  0 }\n",
    }
    for name, source in cases.items():
        src = d / name
        src.write_text(source)
        r = subprocess.run([zenc, "check", str(src)], capture_output=True, text=True)
        assert r.returncode != 0, f"{name} unexpectedly checked ok"


def test_zenc_run_str_try_parse_result_variants():
    """std.text.str.try_parse_int returns Result for ok/no-digits/trailing/overflow cases."""
    zenc = _zenc()
    r = _run_fixture(zenc, "str_try_parse_result.zen")
    assert r.returncode == 0, r.stderr
    assert r.stdout == "", repr(r.stdout)


def test_zenc_run_str_tokenizer():
    """THE acceptance program: tokenize a hardcoded sentence — find each space, substr the word out,
    parse_int the numeric tokens (incl. a negative) — composed UFCS-style with recursion."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        '{ default } = std.mem.alloc\n'
        '{ Arena, make_in } = std.mem.arena\n'
        '{ find, substr, parse_int, len } = std.text.str\n'
        '{ println } = std.text.fmt\n'
        '// print the words of s[from..] (split on \' \'), each followed by its parse_int\n'
        'tok_words = (a: MutPtr<Arena>, s: str, from: i64) i64 {\n'
        '  rest := a.substr(s, from, s.len() - from)\n'
        '  sp := rest.find(" ")\n'
        '  (sp < 0).match ({\n'
        '    true  => { println(rest)  println(rest.parse_int())  0 },\n'
        '    false => {\n'
        '      w := a.substr(rest, 0, sp)\n'
        '      println(w)\n'
        '      println(w.parse_int())\n'
        '      a.tok_words(s, from + sp + 1)\n'
        '    },\n'
        '  })\n'
        '}\n'
        'main = () i32 {\n'
        '  heap := default()\n'
        '  scratch: Arena := heap.addr().make_in(4096)\n'
        '  scratch.addr().tok_words("zen has 3 frontends and -1 regrets", 0)\n'
        '  scratch.addr().free_in(heap.addr())\n'
        '  0\n'
        '}\n'
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout == ("zen\n0\nhas\n0\n3\n3\nfrontends\n0\nand\n0\n-1\n-1\nregrets\n0\n"), repr(r.stdout)



# ── std.collections.map: a str-keyed Map<T> with an EXPLICIT allocator (parallel str/T buffers, linear scan) ─────
def test_zenc_run_map_wordfreq():
    """THE std.collections.map acceptance: word-frequency counting via the get+1-then-put idiom — exercises
    put/get/overwrite-upsert/has/miss-default/len AND growth (cap 1 -> 3 -> 7 across 5 distinct keys).
    The counting idiom is also the regression guard for the by-name-arg use-after-free: the value arg
    `m.get(w, 0) + 1` must be evaluated BEFORE put's grow resizes the buffers (append force-binds)."""
    zenc = _zenc()
    r = _run_fixture(zenc, "map_wordfreq.zen")
    assert r.returncode == 0, r.stderr
    assert r.stdout == "3\n2\n1\n-1\n1\n0\n5\n", repr(r.stdout)


def test_zenc_run_map_growth_and_second_value_type():
    """Entries survive repeated grows (9 keys force cap 1 -> 3 -> 7 -> 15, both buffers realloc'd), and
    a Map<str> coexists with a Map<i32> — two monomorphized C types from the one generic source."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    puts = "".join(f'    w = w.put(a, "k{i}", {i * 10})\n' for i in range(1, 9))
    (d / "p.zen").write_text(
        '{ default } = std.mem.alloc\n'
        'maps = std.collections.map\n'
        '{ println } = std.text.fmt\n'
        'main = () i32 {\n'
        '    alloc := default()\n'
        '    a := alloc.addr()\n'
        '    w := maps.of(a, "k0", 0)\n'
        f'{puts}'
        '    println(w.len())\n'                         # 9
        '    println(w.get("k0", -1))\n'                 # 0: the seed survived 3 grows
        '    println(w.get("k8", -1))\n'                 # 80
        '    caps := maps.of(a, "uk", "london")\n'              # a Map<str> beside the Map<i32>
        '    caps = caps.put(a, "fr", "paris")\n'
        '    caps = caps.put(a, "fr", "PARIS")\n'           # upsert overwrites in place
        '    println(caps.get("fr", "?"))\n'             # PARIS
        '    println(caps.get("de", "miss"))\n'          # miss
        '    println(caps.len())\n'                      # 2
        '    w.free(a)\n'
        '    caps.free(a)\n'
        '    0\n'
        '}\n'
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "9\n0\n80\nPARIS\nmiss\n2\n", repr(r.stdout)


def test_zenc_run_map_clone_value_semantics():
    """`clone` gives a Map an INDEPENDENT deep copy: mutating the original (in-place upsert AND a grow
    that reallocs its buffers) is invisible through the clone, and vice versa. This is the documented
    tool for the value semantics the by-value header doesn't provide on its own — a regression guard
    that clone copies storage rather than sharing it."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        '{ default } = std.mem.alloc\n'
        'maps = std.collections.map\n'
        '{ println } = std.text.fmt\n'
        'main = () i32 {\n'
        '    alloc := default()\n'
        '    a := alloc.addr()\n'
        '    e1 := maps.of(a, "x", 2)\n'
        '    e1 = e1.put(a, "y", 3)\n'
        '    snap := e1.clone(a)\n'             # independent copy of {x:2, y:3}
        '    e1 = e1.put(a, "x", 99)\n'         # upsert original in place
        '    e1 = e1.put(a, "z", 5)\n'          # grow original (reallocs its buffers)
        '    println(snap.get("x", -1))\n'      # 2: clone unaffected by upsert
        '    println(snap.get("y", -1))\n'      # 3
        '    println(snap.get("z", -1))\n'      # -1: grow added to original only
        '    println(snap.len())\n'             # 2
        '    println(e1.get("x", -1))\n'        # 99
        '    println(e1.get("z", -1))\n'        # 5
        '    snap.free(a)\n'
        '    e1.free(a)\n'
        '    0\n'
        '}\n'
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "2\n3\n-1\n2\n99\n5\n", repr(r.stdout)


def test_zenc_run_map_try_result_paths():
    """Fallible map allocation returns Result errors, releasing partial buffers on failure.

    The hashed Map<T> acquires THREE buffers (keys, vals, hash index); LimitAlloc(left: 2) lets the
    first two succeed and fails the third, so try_of returns .Err and frees the two it got (no leak)."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        '{ Allocator, default, malloc, free } = std.mem.alloc\n'
        '{ Result, IoError } = std.core.result\n'
        'maps = std.collections.map\n'
        'LimitAlloc: { left: i32 }\n'
        'LimitAlloc.impl(Allocator, {\n'
        '    acquire = (a: MutPtr<LimitAlloc>, n: i64) RawPtr<u8> {\n'
        '        (a.left > 0).match ({\n'
        '            true => {\n'
        '                a.left = a.left - 1\n'
        '                malloc(n)\n'
        '            },\n'
        '            false => null_ptr()\n'
        '        })\n'
        '    }\n'
        '    resize = (a: MutPtr<LimitAlloc>, p: RawPtr<u8>, n: i64) RawPtr<u8> { null_ptr() }\n'
        '    release = (a: MutPtr<LimitAlloc>, p: RawPtr<u8>) void { free(p) }\n'
        '})\n'
        'success = () i32 {\n'
        '    m := default()\n'
        '    a := m.addr()\n'
        '    r0: Result<maps.Map<i32>, IoError> := maps.try_of(a, "x", 1)\n'
        '    r0.match ({\n'
        '        .Ok(w0) => {\n'
        '            r1: Result<maps.Map<i32>, IoError> := w0.try_put(a, "y", 2)\n'
        '            r1.match ({\n'
        '                .Ok(w) => {\n'
        '                    n := w.get("x", 0) + w.get("y", 0)\n'
        '                    w.free(a)\n'
        '                    n\n'
        '                },\n'
        '                .Err(e) => 90\n'
        '            })\n'
        '        },\n'
        '        .Err(e) => 91\n'
        '    })\n'
        '}\n'
        'failure = () i32 {\n'
        '    lim := LimitAlloc(left: 2)\n'
        '    a := lim.addr()\n'
        '    r0: Result<maps.Map<i32>, IoError> := maps.try_of(a, "a", 4)\n'
        '    r0.match ({\n'
        '        .Ok(w) => {\n'
        '            r1: Result<maps.Map<i32>, IoError> := w.try_put(a, "b", 5)\n'
        '            r1.match ({\n'
        '                .Ok(w2) => {\n'
        '                    w2.free(a)\n'
        '                    80\n'
        '                },\n'
        '                .Err(e) => {\n'
        '                    n := w.get("a", 0)\n'
        '                    w.free(a)\n'
        '                    n\n'
        '                }\n'
        '            })\n'
        '        },\n'
        '        .Err(e) => 81\n'
        '    })\n'
        '}\n'
        'main = () i32 {\n'
        '    n := success() + failure()\n'
        '    (n == 84).match ({ true => 0, false => n })\n'   # success()=3 (1+2), failure()=81 (try_of .Err on 3rd buffer)
        '}\n'
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_zenc_run_allocator_try_acquire_result_path():
    """std.mem.try_acquire lifts allocator null sentinels into Result instead of leaking raw NULL handling."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        '{ Allocator, try_acquire } = std.mem.alloc\n'
        '{ Result, IoError } = std.core.result\n'
        '{ to_exit } = std.core.bool\n'
        'LimitAlloc: { _: i32 }\n'
        'LimitAlloc.impl(Allocator, {\n'
        '    acquire = (a: MutPtr<LimitAlloc>, n: i64) RawPtr<u8> { null_ptr() }\n'
        '    resize  = (a: MutPtr<LimitAlloc>, p: RawPtr<u8>, n: i64) RawPtr<u8> { null_ptr() }\n'
        '    release = (a: MutPtr<LimitAlloc>, p: RawPtr<u8>) void {}\n'
        '})\n'
        'main = () i32 {\n'
        '    lim := LimitAlloc(_: 0)\n'
        '    r: Result<RawPtr<u8>, IoError> := lim.addr().try_acquire(8)\n'
        '    ok := r.match({\n'
        '        .Err(e) => e.match({ .NotFound => true, _ => false }),\n'
        '        .Ok(p) => false\n'
        '    })\n'
        '    ok.to_exit()\n'
        '}\n'
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_zenc_run_cown_result_paths():
    """cown buffers and FFI-handle wrappers return Result when caller-owned allocation fails."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    existing = d / "input.txt"
    existing.write_text("x")
    (d / "p.zen").write_text(
        "{ Allocator, default, malloc, free } = std.mem.alloc\n"
        "{ Own } = std.mem.own\n"
        "{ Result, IoError } = std.core.result\n"
        "{ to_exit } = std.core.bool\n"
        "cown = std.concurrent.cown\n"
        "LimitAlloc: { _: i32 }\n"
        "LimitAlloc.impl(Allocator, {\n"
        "    acquire = (a: MutPtr<LimitAlloc>, n: i64) RawPtr<u8> { null_ptr() }\n"
        "    resize = (a: MutPtr<LimitAlloc>, p: RawPtr<u8>, n: i64) RawPtr<u8> { null_ptr() }\n"
        "    release = (a: MutPtr<LimitAlloc>, p: RawPtr<u8>) void {}\n"
        "})\n"
        "success_buf = () bool {\n"
        "    heap := default()\n"
        "    a := heap.addr()\n"
        "    r: Result<cown.Buf, IoError> := cown.try_buf(a, 4)\n"
        "    r.match({\n"
        "        .Ok(b) => {\n"
        "            b.addr().set(0, 'A')\n"
        "            ok := (b.len == 4) && (b.addr().get(0) == 'A')\n"
        "            b.addr().free(a)\n"
        "            ok\n"
        "        },\n"
        "        .Err(e) => false\n"
        "    })\n"
        "}\n"
        "fail_buf = () bool {\n"
        "    lim := LimitAlloc(_: 0)\n"
        "    r: Result<cown.Buf, IoError> := cown.try_buf(lim.addr(), 4)\n"
        "    r.match({\n"
        "        .Err(e) => e.match({ .NotFound => true, _ => false }),\n"
        "        .Ok(b) => false\n"
        "    })\n"
        "}\n"
        "fail_file_wrap = () bool {\n"
        "    lim := LimitAlloc(_: 0)\n"
        f"    r: Result<Own<cown.File>, IoError> := cown.file_in(lim.addr(), \"{existing}\")\n"
        "    r.match({\n"
        "        .Err(e) => e.match({ .NotFound => true, _ => false }),\n"
        "        .Ok(f) => false\n"
        "    })\n"
        "}\n"
        "main = () i32 {\n"
        "    (success_buf() && fail_buf() && fail_file_wrap()).to_exit()\n"
        "}\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_zenc_run_arena_uses_explicit_backing_allocator():
    """Arena's backing block can be acquired/released through a caller allocator, with a Result constructor."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ Allocator, malloc, free } = std.mem.alloc\n"
        "{ Result, IoError } = std.core.result\n"
        "{ to_exit } = std.core.bool\n"
        "arena = std.mem.arena\n"
        "Counting: { acquired: i32, released: i32 }\n"
        "Counting.impl(Allocator, {\n"
        "    acquire = (a: MutPtr<Counting>, n: i64) RawPtr<u8> {\n"
        "        a.acquired = a.acquired + 1\n"
        "        malloc(n)\n"
        "    }\n"
        "    resize = (a: MutPtr<Counting>, p: RawPtr<u8>, n: i64) RawPtr<u8> { null_ptr() }\n"
        "    release = (a: MutPtr<Counting>, p: RawPtr<u8>) void {\n"
        "        a.released = a.released + 1\n"
        "        free(p)\n"
        "    }\n"
        "})\n"
        "LimitAlloc: { _: i32 }\n"
        "LimitAlloc.impl(Allocator, {\n"
        "    acquire = (a: MutPtr<LimitAlloc>, n: i64) RawPtr<u8> { null_ptr() }\n"
        "    resize = (a: MutPtr<LimitAlloc>, p: RawPtr<u8>, n: i64) RawPtr<u8> { null_ptr() }\n"
        "    release = (a: MutPtr<LimitAlloc>, p: RawPtr<u8>) void {}\n"
        "})\n"
        "success = () bool {\n"
        "    backing := Counting(acquired: 0, released: 0)\n"
        "    a := backing.addr()\n"
        "    ar: arena.Arena := arena.make_in(a, 64)\n"
        "    p := ar.addr().acquire(8)\n"
        "    p.store_i64(33)\n"
        "    ok := (backing.acquired == 1) && (ar.addr().used() == 8) && (p.load_i64() == 33)\n"
        "    ar.addr().free_in(a)\n"
        "    ok && (backing.released == 1) && (ar.buf == null_ptr())\n"
        "}\n"
        "failure = () bool {\n"
        "    lim := LimitAlloc(_: 0)\n"
        "    r: Result<arena.Arena, IoError> := arena.try_make_in(lim.addr(), 64)\n"
        "    r.match({\n"
        "        .Err(e) => e.match({ .NotFound => true, _ => false }),\n"
        "        .Ok(a) => false\n"
        "    })\n"
        "}\n"
        "main = () i32 {\n"
        "    (success() && failure()).to_exit()\n"
        "}\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_zenc_run_io_file_result_paths():
    """std.io.file returns Result for missing reads, denied writes, allocation failure, and success."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    out = d / "out.txt"
    missing = d / "missing.txt"
    denied = d / "nope" / "out.txt"
    (d / "p.zen").write_text(
        '{ Allocator, default } = std.mem.alloc\n'
        '{ Result, IoError } = std.core.result\n'
        'file = std.io.file\n'
        '{ contents_in } = std.io.file\n'
        '{ eq } = std.text.str\n'
        '{ to_exit } = std.core.bool\n'
        'LimitAlloc: { _: i32 }\n'
        'LimitAlloc.impl(Allocator, {\n'
        '    acquire = (a: MutPtr<LimitAlloc>, n: i64) RawPtr<u8> { null_ptr() }\n'
        '    resize = (a: MutPtr<LimitAlloc>, p: RawPtr<u8>, n: i64) RawPtr<u8> { null_ptr() }\n'
        '    release = (a: MutPtr<LimitAlloc>, p: RawPtr<u8>) void {}\n'
        '})\n'
        'main = () i32 {\n'
        '    heap := default()\n'
        '    a := heap.addr()\n'
        f'    missing := a.contents_in("{missing}")\n'
        '    missing_ok := missing.match({\n'
        '        .Err(e) => e.match({ .NotFound => true, _ => false }),\n'
        '        .Ok(s) => false\n'
        '    })\n'
        f'    denied := file.save("{denied}", "zen", 3)\n'
        '    denied_ok := denied.match({\n'
        '        .Err(e) => e.match({ .Denied => true, _ => false }),\n'
        '        .Ok(n) => false\n'
        '    })\n'
        f'    wrote := file.save("{out}", "zen", 3)\n'
        '    wrote_ok := wrote.match({ .Ok(n) => n == 3, .Err(e) => false })\n'
        f'    read := a.contents_in("{out}")\n'
        '    read_ok := read.match({ .Ok(s) => s.eq("zen"), .Err(e) => false })\n'
        '    lim := LimitAlloc(_: 0)\n'
        f'    alloc_fail: Result<str, IoError> := file.contents_in(lim.addr(), "{out}")\n'
        '    alloc_ok := alloc_fail.match({\n'
        '        .Err(e) => e.match({ .Errno(code) => code == 12, _ => false }),\n'
        '        .Ok(s) => false\n'
        '    })\n'
        '    (missing_ok && denied_ok && wrote_ok && read_ok && alloc_ok).to_exit()\n'
        '}\n'
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_map_and_string_free_coexist_by_receiver_type():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ default } = std.mem.alloc\n"
        "maps = std.collections.map\n"
        "{ String, init } = std.text.string\n"
        "main = () i32 {\n"
        "    alloc := default()\n"
        "    a := alloc.addr()\n"
        "    w := maps.of(a, \"x\", 7)\n"
        "    s := a.init(4).push_in(a, '!')\n"
        "    n := w.get(\"x\", 0) + to_i32(s.len)\n"
        "    w.free(a)\n"
        "    s.free_in(a)\n"
        "    n\n"
        "}\n"
    )
    assert subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True).returncode == 8


def test_zenc_run_trace_uses_explicit_allocator_path():
    """std.mem.trace exposes allocator-threaded entrypoints for tracked blocks, root registration, and collection."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ Allocator, Heap, default } = std.mem.alloc\n"
        "{ to_exit } = std.core.bool\n"
        "trace = std.mem.trace\n"
        "Counting: { heap: Heap, acquired: i32, released: i32 }\n"
        "Counting.impl(Allocator, {\n"
        "    acquire = (a: MutPtr<Counting>, n: i64) RawPtr<u8> {\n"
        "        a.acquired = a.acquired + 1\n"
        "        a.heap.addr().acquire(n)\n"
        "    }\n"
        "    resize = (a: MutPtr<Counting>, p: RawPtr<u8>, n: i64) RawPtr<u8> {\n"
        "        a.heap.addr().resize(p, n)\n"
        "    }\n"
        "    release = (a: MutPtr<Counting>, p: RawPtr<u8>) void {\n"
        "        a.released = a.released + 1\n"
        "        a.heap.addr().release(p)\n"
        "    }\n"
        "})\n"
        "main = () i32 {\n"
        "    c := Counting(heap: default(), acquired: 0, released: 0)\n"
        "    a := c.addr()\n"
        "    left := trace.tracked_in(a, trace.Node(has: 0, kid: null_ptr()))\n"
        "    right := trace.tracked_in(a, trace.Node(has: 0, kid: null_ptr()))\n"
        "    trace.set_kid(left, right)\n"
        "    trace.set_kid(right, left)\n"
        "    trace.root_in(a, left)\n"
        "    trace.root_in(a, right)\n"
        "    allocated := c.acquired == 3\n"
        "    trace.collect_in(a)\n"
        "    reclaimed := (c.acquired == 4) && (c.released == 3)\n"
        "    (allocated && reclaimed).to_exit()\n"
        "}\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_zenc_run_trace_tracked_result_path():
    """std.mem.trace has a Result path for tracked block allocation failure."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ Allocator, Heap, default } = std.mem.alloc\n"
        "{ to_exit } = std.core.bool\n"
        "{ Node, try_tracked_in } = std.mem.trace\n"
        "LimitAlloc: { heap: Heap, remaining: i32, released: i32 }\n"
        "LimitAlloc.impl(Allocator, {\n"
        "    acquire = (a: MutPtr<LimitAlloc>, n: i64) RawPtr<u8> {\n"
        "        (a.remaining <= 0).match({\n"
        "            true => null_ptr(),\n"
        "            false => {\n"
        "                a.remaining = a.remaining - 1\n"
        "                a.heap.addr().acquire(n)\n"
        "            }\n"
        "        })\n"
        "    }\n"
        "    resize = (a: MutPtr<LimitAlloc>, p: RawPtr<u8>, n: i64) RawPtr<u8> {\n"
        "        a.heap.addr().resize(p, n)\n"
        "    }\n"
        "    release = (a: MutPtr<LimitAlloc>, p: RawPtr<u8>) void {\n"
        "        a.released = a.released + 1\n"
        "        a.heap.addr().release(p)\n"
        "    }\n"
        "})\n"
        "fails = () bool {\n"
        "    c := LimitAlloc(heap: default(), remaining: 0, released: 0)\n"
        "    r := c.addr().try_tracked_in(Node(has: 0, kid: null_ptr()))\n"
        "    r.match({ .Ok(v) => false, .Err(e) => true })\n"
        "}\n"
        "succeeds = () bool {\n"
        "    c := LimitAlloc(heap: default(), remaining: 1, released: 0)\n"
        "    r := c.addr().try_tracked_in(Node(has: 0, kid: null_ptr()))\n"
        "    r.match({\n"
        "        .Ok(v) => {\n"
        "            c.addr().release(v.base)\n"
        "            c.released == 1\n"
        "        },\n"
        "        .Err(e) => false\n"
        "    })\n"
        "}\n"
        "main = () i32 { (fails() && succeeds()).to_exit() }\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_zenc_run_trace_root_and_collect_result_paths():
    """Root registration and collection scratch allocation can fail through Result."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ Allocator, Heap, default } = std.mem.alloc\n"
        "{ to_exit } = std.core.bool\n"
        "trace = std.mem.trace\n"
        "LimitAlloc: { heap: Heap, remaining: i32, released: i32 }\n"
        "LimitAlloc.impl(Allocator, {\n"
        "    acquire = (a: MutPtr<LimitAlloc>, n: i64) RawPtr<u8> {\n"
        "        (a.remaining <= 0).match({\n"
        "            true => null_ptr(),\n"
        "            false => {\n"
        "                a.remaining = a.remaining - 1\n"
        "                a.heap.addr().acquire(n)\n"
        "            }\n"
        "        })\n"
        "    }\n"
        "    resize = (a: MutPtr<LimitAlloc>, p: RawPtr<u8>, n: i64) RawPtr<u8> {\n"
        "        (a.remaining <= 0).match({\n"
        "            true => null_ptr(),\n"
        "            false => {\n"
        "                a.remaining = a.remaining - 1\n"
        "                a.heap.addr().resize(p, n)\n"
        "            }\n"
        "        })\n"
        "    }\n"
        "    release = (a: MutPtr<LimitAlloc>, p: RawPtr<u8>) void {\n"
        "        a.released = a.released + 1\n"
        "        a.heap.addr().release(p)\n"
        "    }\n"
        "})\n"
        "root_fails = () bool {\n"
        "    heap := default()\n"
        "    node := trace.tracked_in(heap.addr(), trace.Node(has: 0, kid: null_ptr()))\n"
        "    lim := LimitAlloc(heap: default(), remaining: 0, released: 0)\n"
        "    r := trace.try_root_in(lim.addr(), node)\n"
        "    heap.addr().release(node.base)\n"
        "    r.match({ .Ok(v) => false, .Err(e) => true })\n"
        "}\n"
        "collect_succeeds = () bool {\n"
        "    c := LimitAlloc(heap: default(), remaining: 4, released: 0)\n"
        "    a := c.addr()\n"
        "    left := trace.tracked_in(a, trace.Node(has: 0, kid: null_ptr()))\n"
        "    right := trace.tracked_in(a, trace.Node(has: 0, kid: null_ptr()))\n"
        "    trace.set_kid(left, right)\n"
        "    trace.set_kid(right, left)\n"
        "    ok_roots := trace.try_root_in(a, left).match({ .Ok(v) => true, .Err(e) => false }) && trace.try_root_in(a, right).match({ .Ok(v) => true, .Err(e) => false })\n"
        "    ok_collect := trace.try_collect_in(a).match({ .Ok(v) => true, .Err(e) => false })\n"
        "    ok_roots && ok_collect && (c.released == 3)\n"
        "}\n"
        "collect_scratch_fails = () bool {\n"
        "    c := LimitAlloc(heap: default(), remaining: 2, released: 0)\n"
        "    a := c.addr()\n"
        "    left := trace.tracked_in(a, trace.Node(has: 0, kid: null_ptr()))\n"
        "    right := trace.tracked_in(a, trace.Node(has: 0, kid: null_ptr()))\n"
        "    trace.set_kid(left, right)\n"
        "    trace.set_kid(right, left)\n"
        "    trace.try_root_in(a, left)\n"
        "    trace.try_root_in(a, right)\n"
        "    failed := trace.try_collect_in(a).match({ .Ok(v) => false, .Err(e) => true })\n"
        "    trace.collect_in(c.heap.addr())\n"
        "    failed\n"
        "}\n"
        "main = () i32 { (root_fails() && collect_succeeds() && collect_scratch_fails()).to_exit() }\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_zenc_run_coroutine_try_spawn_result_path():
    """std.concurrent.coroutine has a Result path for stack/context/state allocation and cleans up partial state."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ Allocator, default, malloc, free } = std.mem.alloc\n"
        "{ Result, IoError } = std.core.result\n"
        "{ to_exit } = std.core.bool\n"
        "{ Coro, try_spawn, destroy } = std.concurrent.coroutine\n"
        "ran := 0\n"
        "work = () void { ran = ran + 1 }\n"
        "Counting: { left: i32, acquired: i32, released: i32 }\n"
        "Counting.impl(Allocator, {\n"
        "    acquire = (a: MutPtr<Counting>, n: i64) RawPtr<u8> {\n"
        "        (a.left <= 0).match({\n"
        "            true => null_ptr(),\n"
        "            false => {\n"
        "                a.left = a.left - 1\n"
        "                a.acquired = a.acquired + 1\n"
        "                malloc(n)\n"
        "            }\n"
        "        })\n"
        "    }\n"
        "    resize = (a: MutPtr<Counting>, p: RawPtr<u8>, n: i64) RawPtr<u8> { null_ptr() }\n"
        "    release = (a: MutPtr<Counting>, p: RawPtr<u8>) void {\n"
        "        a.released = a.released + 1\n"
        "        free(p)\n"
        "    }\n"
        "})\n"
        "success = () bool {\n"
        "    heap := default()\n"
        "    a := heap.addr()\n"
        "    r: Result<Coro, IoError> := a.try_spawn(work)\n"
        "    r.match({\n"
        "        .Ok(co) => {\n"
        "            co.resume()\n"
        "            a.destroy(co)\n"
        "            ran == 1\n"
        "        },\n"
        "        .Err(e) => false\n"
        "    })\n"
        "}\n"
        "fail_first = () bool {\n"
        "    c := Counting(left: 0, acquired: 0, released: 0)\n"
        "    r: Result<Coro, IoError> := c.addr().try_spawn(work)\n"
        "    r.match({\n"
        "        .Err(e) => e.match({ .NotFound => (c.acquired == 0) && (c.released == 0), _ => false }),\n"
        "        .Ok(co) => false\n"
        "    })\n"
        "}\n"
        "fail_state = () bool {\n"
        "    c := Counting(left: 3, acquired: 0, released: 0)\n"
        "    r: Result<Coro, IoError> := c.addr().try_spawn(work)\n"
        "    r.match({\n"
        "        .Err(e) => e.match({ .NotFound => (c.acquired == 3) && (c.released == 3), _ => false }),\n"
        "        .Ok(co) => false\n"
        "    })\n"
        "}\n"
        "main = () i32 { (success() && fail_first() && fail_state()).to_exit() }\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_zenc_run_scheduler_try_run_result_path():
    """std.concurrent.sched has a Result path for scheduler flag allocation."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ Allocator, default, malloc, free } = std.mem.alloc\n"
        "{ Result, IoError } = std.core.result\n"
        "{ to_exit } = std.core.bool\n"
        "{ Coro, spawn, destroy } = std.concurrent.coroutine\n"
        "{ try_run } = std.concurrent.sched\n"
        "ran := 0\n"
        "work = () void { ran = ran + 1 }\n"
        "Counting: { left: i32, acquired: i32, released: i32 }\n"
        "Counting.impl(Allocator, {\n"
        "    acquire = (a: MutPtr<Counting>, n: i64) RawPtr<u8> {\n"
        "        (a.left <= 0).match({\n"
        "            true => null_ptr(),\n"
        "            false => {\n"
        "                a.left = a.left - 1\n"
        "                a.acquired = a.acquired + 1\n"
        "                malloc(n)\n"
        "            }\n"
        "        })\n"
        "    }\n"
        "    resize = (a: MutPtr<Counting>, p: RawPtr<u8>, n: i64) RawPtr<u8> { null_ptr() }\n"
        "    release = (a: MutPtr<Counting>, p: RawPtr<u8>) void {\n"
        "        a.released = a.released + 1\n"
        "        free(p)\n"
        "    }\n"
        "})\n"
        "success = () bool {\n"
        "    heap := default()\n"
        "    h := heap.addr()\n"
        "    co := h.spawn(work)\n"
        "    c := Counting(left: 1, acquired: 0, released: 0)\n"
        "    r: Result<i32, IoError> := c.addr().try_run([co])\n"
        "    h.destroy(co)\n"
        "    r.match({\n"
        "        .Ok(n) => (ran == 1) && (c.acquired == 1) && (c.released == 1),\n"
        "        .Err(e) => false\n"
        "    })\n"
        "}\n"
        "fail_flags = () bool {\n"
        "    c := Counting(left: 0, acquired: 0, released: 0)\n"
        "    bogus := Coro(state: null_ptr())\n"
        "    r: Result<i32, IoError> := c.addr().try_run([bogus])\n"
        "    r.match({\n"
        "        .Err(e) => e.match({ .NotFound => (c.acquired == 0) && (c.released == 0), _ => false }),\n"
        "        .Ok(n) => false\n"
        "    })\n"
        "}\n"
        "main = () i32 { (success() && fail_flags()).to_exit() }\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ── colorless checkpoint: runtime.checkpoint no-ops outside a coroutine and pauses inside one ───────
def test_runtime_checkpoint_is_colorless():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "a.zen").write_text(
        "mem = std.mem.alloc\nrt = std.concurrent.runtime\n{ println } = std.text.fmt\n"
        "main = () i32 { heap := mem.default()  hp := heap.addr()  a := rt.async(hp, 1024)  a.addr().checkpoint()  println(42)  a.addr().checkpoint()  a.addr().free(hp)  0 }\n")
    r = subprocess.run([zenc, "run", str(d / "a.zen")], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout == "42\n", (r.returncode, r.stdout, r.stderr)   # was SIGSEGV
    (d / "b.zen").write_text(
        "mem = std.mem.alloc\nrt = std.concurrent.runtime\n{ Coro, spawn, destroy } = std.concurrent.coroutine\n{ run } = std.concurrent.sched\n{ println } = std.text.fmt\n"
        "work = () void { heap := mem.default()  hp := heap.addr()  a := rt.async(hp, 1024)  println(1)  a.addr().checkpoint()  println(3)  a.addr().free(hp) }\n"
        "main = () i32 { heap := mem.default()  hp := heap.addr()  arena := rt.sync(hp, 131072)  co := arena.addr().spawn(work)  co.resume()  println(2)  arena.addr().run([co])  arena.addr().destroy(co)  arena.addr().free(hp)  0 }\n")
    r = subprocess.run([zenc, "run", str(d / "b.zen")], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout == "1\n2\n3\n", (r.returncode, r.stdout, r.stderr)


def test_runtime_arena_constructors_accept_explicit_backing_allocator():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ Allocator, Heap, default } = std.mem.alloc\n"
        "{ to_exit } = std.core.bool\n"
        "rt = std.concurrent.runtime\n"
        "Counting: { heap: Heap, acquired: i32, released: i32 }\n"
        "Counting.impl(Allocator, {\n"
        "    acquire = (a: MutPtr<Counting>, n: i64) RawPtr<u8> {\n"
        "        a.acquired = a.acquired + 1\n"
        "        a.heap.addr().acquire(n)\n"
        "    }\n"
        "    resize = (a: MutPtr<Counting>, p: RawPtr<u8>, n: i64) RawPtr<u8> {\n"
        "        a.heap.addr().resize(p, n)\n"
        "    }\n"
        "    release = (a: MutPtr<Counting>, p: RawPtr<u8>) void {\n"
        "        a.released = a.released + 1\n"
        "        a.heap.addr().release(p)\n"
        "    }\n"
        "})\n"
        "main = () i32 {\n"
        "    backing := Counting(heap: default(), acquired: 0, released: 0)\n"
        "    a := backing.addr()\n"
        "    s := rt.sync_in(a, 1024)\n"
        "    y := rt.async_in(a, 1024)\n"
        "    s.addr().free_in(a)\n"
        "    y.addr().free_in(a)\n"
        "    ((backing.acquired == 2) && (backing.released == 2)).to_exit()\n"
        "}\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ── anonymous (structural) struct types + literals ──────────────────────────────────────────────
# `{ q: i32, r: i32 }` is a structural struct TYPE; `{ q: …, r: … }` its literal. Structural identity
# is by ORDERED field names: the same shape shares one synthesized C struct, so a function's declared
# `{q,r}` return unifies with a `{q,r}` literal and composes inside generics (`Result<{q,r}, E>`).
def test_zenc_run_anonymous_struct_in_result_generic():
    """The task program: divmod returns Result<{q,r}, IoError> and constructs the {q,r} literal in
    the .Ok payload; the caller matches and reads v.q / v.r. Prints 3 then 1."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ println } = std.text.fmt\n"
        "{ Result, IoError } = std.core.result\n"
        "divmod = (n: i32, d: i32) Result<{ q: i32, r: i32 }, IoError> {\n"
        "    (d == 0).match ({\n"
        "        true  => .Err(.NotFound),\n"
        "        false => .Ok({ q: n / d, r: n % d }),\n"
        "    })\n"
        "}\n"
        "main = () i32 {\n"
        "    divmod(7, 2).match ({\n"
        "        .Ok(v)  => { println(v.q)  println(v.r) },\n"
        "        .Err(e) => println(0 - 1),\n"
        "    })\n"
        "    0\n"
        "}\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "3\n1\n", repr(r.stdout)


def test_zenc_run_anonymous_struct_plain_and_nested():
    """An anon struct as a PLAIN return type (`() { q: i32 }`) and NESTED inside another anon struct,
    with field access through both levels. Identical shapes share one synthesized C struct."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(
        "{ println } = std.text.fmt\n"
        "mk = () { q: i32 } { { q: 42 } }\n"
        "nested = () { p: { x: i32, y: i32 }, z: i32 } {\n"
        "    { p: { x: 1, y: 2 }, z: 3 }\n"
        "}\n"
        "main = () i32 {\n"
        "    println(mk().q)\n"
        "    b := nested()\n"
        "    println(b.p.x)\n"
        "    println(b.p.y)\n"
        "    println(b.z)\n"
        "    0\n"
        "}\n"
    )
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "42\n1\n2\n3\n", repr(r.stdout)


def test_zenc_run_implicit_trait_bound_param():
    """A param whose declared type is a trait NAME is sugar for a bounded implicit generic:
    `(a: Allocator)` desugars to `<A: Allocator>(a: MutPtr<A>)`. Two params of the SAME trait
    get TWO DISTINCT tparams. The desugared form goes through the existing bounded-generic +
    monomorphization machinery, so it is byte-for-byte the explicit form."""
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    counting = (
        "{ Allocator, Heap, default } = std.mem.alloc\n"
        "Counting: { heap: Heap, acquired: i32 }\n"
        "Counting.impl(Allocator, {\n"
        "    acquire = (a: MutPtr<Counting>, n: i64) RawPtr<u8> {\n"
        "        a.acquired = a.acquired + 1\n"
        "        a.heap.addr().acquire(n)\n"
        "    }\n"
        "    resize = (a: MutPtr<Counting>, p: RawPtr<u8>, n: i64) RawPtr<u8> { a.heap.addr().resize(p, n) }\n"
        "    release = (a: MutPtr<Counting>, p: RawPtr<u8>) void { a.heap.addr().release(p) }\n"
        "})\n"
    )
    # implicit trait-bound param sugar, incl. TWO params of the same trait (distinct tparams)
    sugar = (
        counting +
        "grab = (a: Allocator, n: i64) RawPtr<u8> { a.acquire(n) }\n"
        "both = (dst: Allocator, src: Allocator, n: i64) i64 {\n"
        "    p := dst.acquire(n)\n"
        "    q := src.acquire(n)\n"
        "    n\n"
        "}\n"
        "main = () i32 {\n"
        "    c := Counting(heap: default(), acquired: 0)\n"
        "    a := c.addr()\n"
        "    p := a.grab(8)\n"
        "    r := a.both(a, 4)\n"
        "    ((c.acquired == 3) && (r == 4)).match({ true => 0, false => 1 })\n"
        "}\n"
    )
    (d / "sugar.zen").write_text(sugar)
    r = subprocess.run([zenc, "run", str(d / "sugar.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

    # the EXACT explicit equivalent must emit byte-identical C.
    explicit = sugar.replace(
        "grab = (a: Allocator, n: i64)",
        "grab = <A: Allocator>(a: MutPtr<A>, n: i64)",
    ).replace(
        "both = (dst: Allocator, src: Allocator, n: i64)",
        "both = <A: Allocator, B: Allocator>(dst: MutPtr<A>, src: MutPtr<B>, n: i64)",
    )
    (d / "explicit.zen").write_text(explicit)
    cs = subprocess.run([zenc, "emit", str(d / "sugar.zen")], capture_output=True, text=True)
    ce = subprocess.run([zenc, "emit", str(d / "explicit.zen")], capture_output=True, text=True)
    assert cs.returncode == 0, cs.stderr
    assert ce.returncode == 0, ce.stderr
    assert cs.stdout == ce.stdout, "implicit trait-bound param must desugar to the explicit form"
