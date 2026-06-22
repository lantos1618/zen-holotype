"""USER MULTI-FILE IMPORTS (Goal R, #1 outsider blocker): `{ helper } = b` loads b.zen from the
importing program's OWN directory — a SIBLING file — through the same std.internal.resolve loader that handles
`{ … } = std.X` (transitive closure, per-module dedup/cycle break, per-name dedup).

Before this, a sibling import TYPECHECKED (the checker trusts DImport names) and then died in raw
linker spew (`undefined reference to 'helper'`). The point of the feature is the error quality as much
as the loading: unknown module / unknown imported name / cross-sibling duplicate / sibling-from-stdin
all print one `zenc: <file>: error: …` line (the loader writes stderr and exits 1 itself — the C
driver adds nothing).
"""
import subprocess
import tempfile
from pathlib import Path

import _oracle

ROOT = _oracle.ROOT


def _zenc():
    """The repo's make-built zenc (beside ROOT/bootstrap, so it can find zen/std + zenrt.{c,h})."""
    subprocess.run(["make", "-f", "bootstrap/Makefile", "zenc"], cwd=str(ROOT),
                   check=True, capture_output=True)
    return str(ROOT / "zenc")


def _program(files):
    """Write {name: source} into a fresh dir; returns the dir."""
    d = Path(tempfile.mkdtemp())
    for name, src in files.items():
        (d / name).write_text(src)
    return d


# ── the feature: a bare module name imports a sibling file ───────────────────────────────────────
def test_sibling_import_builds_and_runs():
    d = _program({
        "b.zen": "helper* = (x: i32) i32 { x * 2 }\n",
        "p.zen": "{ helper } = b\nmain = () i32 { helper(21) }\n",
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 42, r.stderr


def test_sibling_helper_importing_std_is_transitive():
    """b.zen's own `{ println } = std.text.fmt` edge is loaded into the same closure."""
    d = _program({
        "h.zen": '{ println } = std.text.fmt\nshout* = (s: str) i64 { println(s) }\n',
        "p.zen": '{ shout } = h\nmain = () i32 { shout("from helper") 0 }\n',
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "from helper\n"


def test_two_sibling_modules():
    d = _program({
        "m1.zen": "one* = () i32 { 1 }\n",
        "m2.zen": "two* = () i32 { 2 }\n",
        "p.zen": "{ one } = m1\n{ two } = m2\nmain = () i32 { one() + two() }\n",
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 3, r.stderr


def test_namespace_bound_siblings_can_export_same_function_name():
    d = _program({
        "left.zen": "thing* = () i32 { 10 }\n",
        "right.zen": "thing* = () i32 { 20 }\n",
        "p.zen": "left = left\nright = right\nmain = () i32 { left.thing() + right.thing() }\n",
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 30, r.stderr


def test_namespace_bound_module_can_use_its_own_namespace_bind():
    d = _program({
        "helper.zen": "value* = () i32 { 7 }\n",
        "left.zen": "helper = helper\ncalc* = () i32 { helper.value() + 1 }\n",
        "p.zen": "left = left\nmain = () i32 { left.calc() }\n",
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 8, r.stderr


def test_destructuring_imported_module_can_use_namespace_bind():
    d = _program({
        "helper.zen": "value* = () i32 { 40 }\n",
        "left.zen": "helper = helper\ncalc* = () i32 { helper.value() + 2 }\n",
        "p.zen": "{ calc } = left\nmain = () i32 { calc() }\n",
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 42, r.stderr


def test_resolver_exposes_structured_import_edges():
    d = _program({
        "p.zen": (
            "{ Malloc } = std.mem.alloc\n"
            "{ import_edges } = std.internal.resolve\n"
            "{ eq } = std.text.str\n"
            "{ to_exit } = std.core.bool\n"
            "arena = std.mem.arena\n"
            "main = () i32 {\n"
            "    heap := default()\n"
            "    a := arena.make_in(heap.addr(), 4096)\n"
            "    src := \"{ println } = std.text.fmt\\nactor = std.concurrent.actor\\nhelper = helper\\nmain = () i32 { 0 }\\n\"\n"
            "    edges := a.addr().import_edges(src)\n"
            "    ok := (edges.len == 3)\n"
            "        && (!edges[0].namespace) && eq(edges[0].module, \"std/text/fmt\") && eq(edges[0].alias, \"\") && (edges[0].start == 0) && (edges[0].next == 27)\n"
            "        && edges[1].namespace && eq(edges[1].module, \"std/concurrent/actor\") && eq(edges[1].alias, \"actor\") && (edges[1].start == 27) && (edges[1].next == 56)\n"
            "        && edges[2].namespace && eq(edges[2].module, \"u/helper\") && eq(edges[2].alias, \"helper\") && (edges[2].start == 56) && (edges[2].next == 72)\n"
            "    a.addr().free_in(heap.addr())\n"
            "    ok.to_exit()\n"
            "}\n"
        ),
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_resolver_import_edges_handles_many_edges_without_recursive_stack_growth():
    prefix = "first = first\n"
    middle = "right = right\n" * 700
    suffix = "{ last } = last\nmain = () i32 { 0 }\n"
    src = prefix + middle + suffix
    escaped = src.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n")
    d = _program({
        "p.zen": (
            "{ Malloc } = std.mem.alloc\n"
            "{ import_edges } = std.internal.resolve\n"
            "{ eq } = std.text.str\n"
            "{ to_exit } = std.core.bool\n"
            "main = () i32 {\n"
            "    a := default()\n"
            f"    src := \"{escaped}\"\n"
            "    edges := a.addr().import_edges(src)\n"
            "    last := edges.len - 1\n"
            "    ok := (edges.len == 702)\n"
            "        && edges[0].namespace && eq(edges[0].alias, \"first\") && eq(edges[0].module, \"u/first\")\n"
            "        && edges[last].namespace.match({ true => false, false => true }) && eq(edges[last].module, \"u/last\")\n"
            "    ok.to_exit()\n"
            "}\n"
        ),
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_resolver_try_import_edges_reports_allocator_failure():
    d = _program({
        "p.zen": (
            "{ Allocator, Heap, default } = std.mem.alloc\n"
            "{ Result, IoError } = std.core.result\n"
            "{ ImportEdge, try_import_edges } = std.internal.resolve\n"
            "{ eq } = std.text.str\n"
            "{ to_exit } = std.core.bool\n"
            "LimitAlloc: { heap: Heap, left: i32 }\n"
            "LimitAlloc.impl(Allocator, {\n"
            "    acquire = (a: MutPtr<LimitAlloc>, n: i64) RawPtr<u8> {\n"
            "        (a.left <= 0).match({\n"
            "            true => null_ptr(),\n"
            "            false => {\n"
            "                a.left = a.left - 1\n"
            "                a.heap.addr().acquire(n)\n"
            "            }\n"
            "        })\n"
            "    }\n"
            "    resize = (a: MutPtr<LimitAlloc>, p: RawPtr<u8>, n: i64) RawPtr<u8> { null_ptr() }\n"
            "    release = (a: MutPtr<LimitAlloc>, p: RawPtr<u8>) void { a.heap.addr().release(p) }\n"
            "})\n"
            "failed = (r: Result<[ImportEdge], IoError>) bool {\n"
            "    r.match({ .Err(e) => true, .Ok(xs) => false })\n"
            "}\n"
            "main = () i32 {\n"
            "    src := \"right = right\\n\"\n"
            "    none := LimitAlloc(heap: default(), left: 0)\n"
            "    only_slice := LimitAlloc(heap: default(), left: 1)\n"
            "    no_alias := LimitAlloc(heap: default(), left: 2)\n"
            "    enough := LimitAlloc(heap: default(), left: 3)\n"
            "    r0: Result<[ImportEdge], IoError> := none.addr().try_import_edges(src)\n"
            "    r1: Result<[ImportEdge], IoError> := only_slice.addr().try_import_edges(src)\n"
            "    r2: Result<[ImportEdge], IoError> := no_alias.addr().try_import_edges(src)\n"
            "    r3: Result<[ImportEdge], IoError> := enough.addr().try_import_edges(src)\n"
            "    ok3 := r3.match({\n"
            "        .Ok(edges) => (edges.len == 1) && edges[0].namespace && eq(edges[0].module, \"u/right\") && eq(edges[0].alias, \"right\"),\n"
            "        .Err(e) => false\n"
            "    })\n"
            "    (r0.failed() && r1.failed() && r2.failed() && ok3).to_exit()\n"
            "}\n"
        ),
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_many_import_and_namespace_edges_load_without_recursive_edge_walk():
    files = {}
    import_lines = []
    namespace_lines = []
    for i in range(40):
        files[f"imp{i}.zen"] = f"f{i}* = () i32 {{ {i} }}\n"
        files[f"ns{i}.zen"] = f"thing* = () i32 {{ {i} }}\n"
        import_lines.append(f"{{ f{i} }} = imp{i}\n")
        namespace_lines.append(f"ns{i} = ns{i}\n")

    files["p.zen"] = (
        "".join(import_lines)
        + "".join(namespace_lines)
        + "main = () i32 { f0() + f39() + ns0.thing() + ns39.thing() }\n"
    )
    d = _program(files)
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 78, r.stderr


def test_user_module_with_many_decls_loads_without_recursive_symbol_consumer():
    big = "".join(f"v{i}* = () i32 {{ {i % 10} }}\n" for i in range(240))
    d = _program({
        "big.zen": big,
        "p.zen": "{ v0, v239 } = big\nmain = () i32 { v0() + v239() }\n",
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 9, r.stderr


def test_import_head_validation_handles_many_names_without_recursive_walk():
    big = "".join(f"v{i}* = () i32 {{ {i % 10} }}\n" for i in range(120))
    names = ", ".join(f"v{i}" for i in range(120))
    d = _program({
        "big.zen": big,
        "p.zen": f"{{ {names} }} = big\nmain = () i32 {{ v0() + v119() }}\n",
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 9, r.stderr


def test_final_dedup_handles_many_symbols_without_recursive_walk():
    src = "".join(f"v{i}* = () i32 {{ {i % 10} }}\n" for i in range(260))
    src += "v0* = () i32 { 777 }\n"
    escaped = src.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n")
    d = _program({
        "p.zen": (
            "{ Malloc } = std.mem.alloc\n"
            "{ dedup_decls } = std.internal.resolve\n"
            "{ contains } = std.text.str\n"
            "{ to_exit } = std.core.bool\n"
            "main = () i32 {\n"
            "    a := Malloc(_: 0)\n"
            f"    src := \"{escaped}\"\n"
            "    out := a.addr().dedup_decls(src, 0, 0)\n"
            "    ok := out.contains(\"v259\") && (!out.contains(\"777\"))\n"
            "    ok.to_exit()\n"
            "}\n"
        ),
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_resolver_exposes_structured_provided_symbols():
    d = _program({
        "p.zen": (
            "{ Malloc, default } = std.mem.alloc\n"
            "{ provided_symbols_in } = std.internal.resolve\n"
            "{ eq } = std.text.str\n"
            "{ to_exit } = std.core.bool\n"
            "arena = std.mem.arena\n"
            "main = () i32 {\n"
            "    scratch := Malloc(_: 0)\n"
            "    heap := default()\n"
            "    a := arena.make_in(heap.addr(), 4096)\n"
            "    src := \"{ helper } = dep\\nforeign = (n: i64) i32\\nThing*: { a: i32 }\\nrun* = () i32 { 1 }\\n\"\n"
            "    symbols := scratch.addr().provided_symbols_in(a.addr(), src)\n"
            "    ok := (symbols.len == 4)\n"
            "        && symbols[0].imported && (!symbols[0].foreign) && eq(symbols[0].name, \"helper\") && (symbols[0].start == 2) && (symbols[0].next == 8) && (symbols[0].decl_start == 2) && (symbols[0].decl_next == 8)\n"
            "        && (!symbols[1].imported) && symbols[1].foreign && eq(symbols[1].name, \"foreign\") && (symbols[1].start == 17) && (symbols[1].next == 24) && (symbols[1].decl_start == 17) && (symbols[1].decl_next == 39)\n"
            "        && (!symbols[2].imported) && (!symbols[2].foreign) && eq(symbols[2].name, \"Thing\") && (symbols[2].start == 40) && (symbols[2].next == 45) && (symbols[2].decl_start == 40) && (symbols[2].decl_next == 58)\n"
            "        && (!symbols[3].imported) && (!symbols[3].foreign) && eq(symbols[3].name, \"run\") && (symbols[3].start == 59) && (symbols[3].next == 62) && (symbols[3].decl_start == 59) && (symbols[3].decl_next == 78)\n"
            "    a.addr().free_in(heap.addr())\n"
            "    ok.to_exit()\n"
            "}\n"
        ),
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_resolver_symbol_key_has_result_allocator_path():
    d = _program({
        "p.zen": (
            "{ Allocator, Heap, default } = std.mem.alloc\n"
            "{ to_exit } = std.core.bool\n"
            "{ ProvidedSymbol, try_symbol_key_in } = std.internal.resolve\n"
            "{ String } = std.text.string\n"
            "{ eq } = std.text.str\n"
            "Limit: { heap: Heap, remaining: i32 }\n"
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
            "        a.heap.addr().release(p)\n"
            "    }\n"
            "})\n"
            "main = () i32 {\n"
            "    sym := ProvidedSymbol(name: \"struct\", start: 0, next: 0, decl_start: 0, decl_next: 0, imported: false, foreign: false)\n"
            "    ok_alloc := Limit(heap: default(), remaining: 1)\n"
            "    good := sym.try_symbol_key_in(ok_alloc.addr()).match({\n"
            "        .Ok(key) => eq(key.finish_in(ok_alloc.addr()), \"struct_zk\"),\n"
            "        .Err(e) => false\n"
            "    })\n"
            "    fail_alloc := Limit(heap: default(), remaining: 0)\n"
            "    failed := sym.try_symbol_key_in(fail_alloc.addr()).match({\n"
            "        .Ok(key) => false,\n"
            "        .Err(e) => true\n"
            "    })\n"
            "    (good && failed).to_exit()\n"
            "}\n"
        ),
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_resolver_provided_symbols_handles_many_symbols_without_recursive_stack_growth():
    imports = ", ".join(f"imp{i}" for i in range(40))
    decls = "".join(f"sym{i}* = () i32 {{ {i % 10} }}\n" for i in range(220))
    src = f"{{ {imports} }} = dep\nforeign = (n: i64) i32\n" + decls
    escaped = src.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n")
    d = _program({
        "p.zen": (
            "{ Malloc, default } = std.mem.alloc\n"
            "{ provided_symbols_in, module_graph_in, decl_names_in, all_decl_names_in } = std.internal.resolve\n"
            "{ finish_in } = std.text.string\n"
            "{ eq } = std.text.str\n"
            "{ to_exit } = std.core.bool\n"
            "arena = std.mem.arena\n"
            "main = () i32 {\n"
            "    scratch := Malloc(_: 0)\n"
            "    heap := default()\n"
            "    a := arena.make_in(heap.addr(), 65536)\n"
            f"    src := \"{escaped}\"\n"
            "    symbols := scratch.addr().provided_symbols_in(a.addr(), src)\n"
            "    g := scratch.addr().module_graph_in(a.addr(), src)\n"
            "    names := g.decl_names_in(scratch.addr()).finish_in(scratch.addr())\n"
            "    all := g.all_decl_names_in(scratch.addr()).finish_in(scratch.addr())\n"
            "    last := symbols.len - 1\n"
            "    ok := (symbols.len == 261)\n"
            "        && symbols[0].imported && eq(symbols[0].name, \"imp0\")\n"
            "        && symbols[last].imported.match({ true => false, false => true }) && eq(symbols[last].name, \"sym219\")\n"
            "        && (g.symbol_count() == 261) && g.has(\"imp39\") && g.has(\"sym219\")\n"
            "        && names.contains(\"sym219\") && (!names.contains(\"foreign\")) && (!names.contains(\"imp39\"))\n"
            "        && all.contains(\"sym219\") && all.contains(\"foreign\") && (!all.contains(\"imp39\"))\n"
            "    a.addr().free_in(heap.addr())\n"
            "    ok.to_exit()\n"
            "}\n"
        ),
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_resolver_exposes_module_graph_imports_and_symbols():
    d = _program({
        "p.zen": (
            "{ Malloc, default } = std.mem.alloc\n"
            "{ module_graph_in } = std.internal.resolve\n"
            "{ eq } = std.text.str\n"
            "{ to_exit } = std.core.bool\n"
            "arena = std.mem.arena\n"
            "main = () i32 {\n"
            "    scratch := Malloc(_: 0)\n"
            "    heap := default()\n"
            "    a := arena.make_in(heap.addr(), 4096)\n"
            "    src := \"{ helper, if } = dep\\nbytes = std.text.bytes\\nforeign = (n: i64) i32\\nThing*: { a: i32 }\\nrun* = () i32 { 1 }\\n\"\n"
            "    g := scratch.addr().module_graph_in(a.addr(), src)\n"
            "    ok := (g.import_count() == 2) && (g.symbol_count() == 5)\n"
            "        && (!g.imports[0].namespace) && eq(g.imports[0].module, \"u/dep\") && eq(g.imports[0].alias, \"\")\n"
            "        && g.imports[1].namespace && eq(g.imports[1].module, \"std/text/bytes\") && eq(g.imports[1].alias, \"bytes\")\n"
            "        && g.has(\"helper\") && g.has(\"if_zk\") && g.has(\"foreign\") && g.has(\"Thing\") && g.has(\"run\")\n"
            "    a.addr().free_in(heap.addr())\n"
            "    ok.to_exit()\n"
            "}\n"
        ),
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_resolver_module_table_loads_transitive_namespace_modules():
    subject = (
        "left = left\n"
        "right = right\n"
        "{ plain } = plain\n"
        "main = () i32 { left.thing() + right.thing() + plain() }\n"
    )
    escaped = subject.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n")
    d = Path(tempfile.mkdtemp())
    (d / "helper.zen").write_text("value* = () i32 { 7 }\n")
    (d / "left.zen").write_text("helper = helper\nthing* = () i32 { helper.value() }\n")
    (d / "right.zen").write_text("thing* = () i32 { 20 }\n")
    (d / "plain.zen").write_text("plain* = () i32 { 5 }\n")
    (d / "driver.zen").write_text(
        "{ Malloc } = std.mem.alloc\n"
        "{ resolve_program_data } = std.internal.resolve\n"
        "{ to_exit } = std.core.bool\n"
        "main = () i32 {\n"
        "    a := Malloc(_: 0)\n"
        f"    subject := \"{escaped}\"\n"
        f"    resolved := a.addr().resolve_program_data(\"{ROOT}\", \"{d}\", \"{d / 'subject.zen'}\", subject)\n"
        "    table := resolved.table\n"
        "    left := table.module(\"u/left\")\n"
        "    helper := table.module(\"u/helper\")\n"
        "    ok := (table.count() == 5)\n"
        "        && table.has(\"u/left\") && table.has(\"u/right\") && table.has(\"u/plain\") && table.has(\"u/helper\")\n"
        "        && left.graph.has(\"thing\") && helper.graph.has(\"value\")\n"
        "        && resolved.flat.contains(\"left__thing\") && resolved.flat.contains(\"plain\")\n"
        "        && (!resolved.flat.contains(\"left = left\")) && (resolved.body_start <= resolved.body_end)\n"
        "    ok.to_exit()\n"
        "}\n"
    )
    r = subprocess.run([_zenc(), "run", str(d / "driver.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_resolver_parsed_program_keeps_per_module_ast_boundary():
    subject = (
        "left = left\n"
        "right = right\n"
        "{ plain } = plain\n"
        "main = () i32 { left.thing() + right.thing() + plain() }\n"
    )
    escaped = subject.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n")
    d = Path(tempfile.mkdtemp())
    (d / "helper.zen").write_text("value* = () i32 { 7 }\n")
    (d / "left.zen").write_text("helper = helper\nthing* = () i32 { helper.value() }\n")
    (d / "right.zen").write_text("thing* = () i32 { 20 }\n")
    (d / "plain.zen").write_text("plain* = () i32 { 5 }\n")
    (d / "driver.zen").write_text(
        "{ Malloc } = std.mem.alloc\n"
        "{ resolve_parsed_program } = std.internal.resolve\n"
        "{ to_exit } = std.core.bool\n"
        "main = () i32 {\n"
        "    a := Malloc(_: 0)\n"
        f"    subject := \"{escaped}\"\n"
        f"    program := a.addr().resolve_parsed_program(\"{ROOT}\", \"{d}\", \"{d / 'subject.zen'}\", subject)\n"
        "    root := program.module(\"\")\n"
        "    left := program.module(\"u/left\")\n"
        "    helper := program.module(\"u/helper\")\n"
        "    ok := (program.count() == 5)\n"
        "        && (program.flat_decls.len == 5)\n"
        "        && (root.decls.len == 1) && root.body.contains(\"left__thing\") && (!root.body.contains(\"left = left\"))\n"
        "        && (left.decls.len == 1) && left.body.contains(\"helper__value\") && (!left.body.contains(\"helper = helper\"))\n"
        "        && (helper.decls.len == 1) && helper.body.contains(\"value\")\n"
        "    ok.to_exit()\n"
        "}\n"
    )
    r = subprocess.run([_zenc(), "run", str(d / "driver.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_parsed_program_check_uses_graph_linked_import_signatures():
    good = (
        "left = left\n"
        "{ plain } = plain\n"
        "main = () i32 { left.thing(1, 2) + plain(3) }\n"
    )
    bad_ns = (
        "left = left\n"
        "{ plain } = plain\n"
        "main = () i32 { left.thing(1) + plain(3) }\n"
    )
    bad_plain = (
        "left = left\n"
        "{ plain } = plain\n"
        "main = () i32 { left.thing(1, 2) + plain() }\n"
    )
    good_escaped = good.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n")
    bad_ns_escaped = bad_ns.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n")
    bad_plain_escaped = bad_plain.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n")
    d = Path(tempfile.mkdtemp())
    (d / "left.zen").write_text("thing* = (a: i32, b: i32) i32 { a + b }\n")
    (d / "plain.zen").write_text("plain* = (a: i32) i32 { a }\n")
    (d / "driver.zen").write_text(
        "{ Malloc } = std.mem.alloc\n"
        "{ resolve_parsed_program, root_link_decls, check_parsed_program } = std.internal.resolve\n"
        "{ to_exit } = std.core.bool\n"
        "main = () i32 {\n"
        "    a := Malloc(_: 0)\n"
        f"    good := \"{good_escaped}\"\n"
        f"    bad_ns := \"{bad_ns_escaped}\"\n"
        f"    bad_plain := \"{bad_plain_escaped}\"\n"
        f"    gp := a.addr().resolve_parsed_program(\"{ROOT}\", \"{d}\", \"{d / 'good.zen'}\", good)\n"
        f"    nsp := a.addr().resolve_parsed_program(\"{ROOT}\", \"{d}\", \"{d / 'bad_ns.zen'}\", bad_ns)\n"
        f"    pp := a.addr().resolve_parsed_program(\"{ROOT}\", \"{d}\", \"{d / 'bad_plain.zen'}\", bad_plain)\n"
        "    lib := a.addr().root_link_decls(gp)\n"
        "    ok := (lib.len == 2)\n"
        "        && (a.addr().check_parsed_program(gp) == 0)\n"
        "        && (a.addr().check_parsed_program(nsp) > 0)\n"
        "        && (a.addr().check_parsed_program(pp) > 0)\n"
        "    ok.to_exit()\n"
        "}\n"
    )
    r = subprocess.run([_zenc(), "run", str(d / "driver.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_namespace_bound_unknown_member_keeps_user_source_span():
    d = _program({
        "left.zen": "thing* = () i32 { 10 }\n",
        "p.zen": "left = left\nmain = () i32 {\n    left.nope()\n}\n",
    })
    r = subprocess.run([_zenc(), "check", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 1
    assert f"zenc: {d}/p.zen:3:10: error[undefined-name]: undefined name" in r.stderr
    assert "      left.nope()\n" in r.stderr
    assert "           ^~~~\n" in r.stderr


def test_namespace_bound_rewritten_call_diagnostics_keep_user_source_span():
    d = _program({
        "left.zen": "thing* = (a: i32, b: i32) i32 { a + b }\n",
        "p.zen": "left = left\nmain = () i32 {\n    left.thing(1)\n}\n",
    })
    r = subprocess.run([_zenc(), "check", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 1
    assert f"zenc: {d}/p.zen:3:5: error[arity]: wrong number of arguments" in r.stderr
    assert "      left.thing(1)\n" in r.stderr
    assert "      ^~~~~~~~~~\n" in r.stderr

    d = _program({
        "left.zen": "thing* = (a: u8) i32 { 0 }\n",
        "p.zen": "left = left\nbig = () i64 { 9999999999 }\nmain = () i32 {\n    left.thing(big())\n}\n",
    })
    r = subprocess.run([_zenc(), "check", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 1
    assert f"zenc: {d}/p.zen:4:16: error[arg-type]: argument type does not fit the parameter" in r.stderr
    assert "      left.thing(big())\n" in r.stderr
    assert "                 ^~~\n" in r.stderr


def test_namespace_bound_std_modules_can_export_same_function_name():
    d = _program({
        "p.zen": (
            "slice = std.core.slice\n"
            "text = std.text.str\n"
            "alloc = std.mem.alloc\n"
            "main = () i32 {\n"
            "    heap := alloc.default()\n"
            "    nums := slice.dup(heap.addr(), [10, 20])\n"
            "    bytes := text.dup_bytes(heap.addr(), \"ab\")\n"
            "    ok := (nums[0] == 10) && (nums[1] == 20) && (bytes[0] == 'a') && (bytes[1] == 'b')\n"
            "    ok.match({ true => 0, false => 1 })\n"
            "}\n"
        ),
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_namespace_bound_std_slice_can_export_natural_buf_without_collision():
    d = _program({
        "right.zen": "buf* = (n: i32) i32 { n + 5 }\n",
        "p.zen": (
            "slice = std.core.slice\n"
            "alloc = std.mem.alloc\n"
            "right = right\n"
            "main = () i32 {\n"
            "    heap := alloc.default()\n"
            "    xs := slice.buf(heap.addr(), 2, [0])\n"
            "    xs[0] = 30\n"
            "    xs[1] = 7\n"
            "    xs[0] + xs[1] + right.buf(0)\n"
            "}\n"
        ),
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 42, r.stderr


def test_namespace_bound_std_bytes_can_export_natural_at_without_collision():
    d = _program({
        "right.zen": "at* = (n: i32) i32 { n + 5 }\n",
        "p.zen": (
            "bytes = std.text.bytes\n"
            "right = right\n"
            "main = () i32 {\n"
            "    (bytes.at(\"AZ\", 1) - 'Z') + right.at(37)\n"
            "}\n"
        ),
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 42, r.stderr


def test_namespace_bound_text_modules_can_export_same_at_name():
    d = _program({
        "right.zen": "at* = (n: i32) i32 { n + 5 }\n",
        "p.zen": (
            "text = std.text.str\n"
            "bytes = std.text.bytes\n"
            "right = right\n"
            "main = () i32 {\n"
            "    (text.at(\"abc\", 1) - 'b') + (bytes.at(\"AZ\", 1) - 'Z') + right.at(37)\n"
            "}\n"
        ),
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 42, r.stderr


def test_namespace_bound_std_ownership_modules_can_export_same_constructor_names():
    d = _program({
        "p.zen": (
            "arena = std.mem.arena\n"
            "rc = std.mem.rc\n"
            "arc = std.mem.arc\n"
            "own = std.mem.own\n"
            "{ default } = std.mem.alloc\n"
            "main = () i32 {\n"
            "    alloc := default()\n"
            "    ar := arena.make_in(alloc.addr(), 64)\n"
            "    r := rc.new_in(alloc.addr(), 11)\n"
            "    a := arc.new_in(alloc.addr(), 13)\n"
            "    o := own.new_in(alloc.addr(), own.Resource(id: 17, slot: 0))\n"
            "    ok := (ar.addr().used() == 0) && (r.get() == 11) && (a.get() == 13) && (o.get().id == 17)\n"
            "    ar.addr().free_in(alloc.addr())\n"
            "    r.drop_in(alloc.addr())\n"
            "    a.drop_in(alloc.addr())\n"
            "    o.release_in(alloc.addr())\n"
            "    ok.match({ true => 0, false => 1 })\n"
            "}\n"
        ),
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_namespace_bound_std_alloc_can_export_natural_default_without_collision():
    d = _program({
        "right.zen": "default* = (n: i32) i32 { n + 5 }\n",
        "p.zen": (
            "alloc = std.mem.alloc\n"
            "right = right\n"
            "main = () i32 {\n"
            "    h := alloc.default()\n"
            "    p := h.addr().acquire(8)\n"
            "    p.store_i64(30)\n"
            "    n := p.load_i64()\n"
            "    h.addr().release(p)\n"
            "    to_i32(n) + right.default(7)\n"
            "}\n"
        ),
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 42, r.stderr


def test_namespace_bound_std_num_can_export_natural_integer_float_without_collision():
    d = _program({
        "right.zen": "integer* = (n: i32) i32 { n + 1 }\nfloat* = (n: i32) i32 { n + 2 }\n",
        "p.zen": (
            "{ default } = std.mem.alloc\n"
            "{ finish_in } = std.text.string\n"
            "num = std.text.num\n"
            "right = right\n"
            "{ eq } = std.text.str\n"
            "{ to_exit } = std.core.bool\n"
            "main = () i32 {\n"
            "    heap := default()\n"
            "    hp := heap.addr()\n"
            "    i := num.integer(hp, -12).finish_in(hp)\n"
            "    f := num.float(hp, 1.5).finish_in(hp)\n"
            "    ok := eq(i, \"-12\") && eq(f, \"1.5\") && (right.integer(10) == 11) && (right.float(10) == 12)\n"
            "    ok.to_exit()\n"
            "}\n"
        ),
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_std_num_supports_allocator_and_result_formatting():
    d = _program({
        "p.zen": (
            "{ integer_in, float_in, try_integer_in, try_float_in } = std.text.num\n"
            "{ default } = std.mem.alloc\n"
            "{ eq } = std.text.str\n"
            "{ finish_in } = std.text.string\n"
            "{ to_exit } = std.core.bool\n"
            "main = () i32 {\n"
            "    a := default()\n"
            "    i := a.addr().integer_in(-12)\n"
            "    f := a.addr().float_in(1.5)\n"
            "    ok_fast := eq(a.addr().finish_in(i), \"-12\") && eq(a.addr().finish_in(f), \"1.5\")\n"
            "    ri := a.addr().try_integer_in(42)\n"
            "    rf := a.addr().try_float_in(42.25)\n"
            "    ok_try := ri.match({ .Ok(x) => eq(a.addr().finish_in(x), \"42\"), .Err(e) => false }) && rf.match({ .Ok(x) => eq(a.addr().finish_in(x), \"42.25\"), .Err(e) => false })\n"
            "    (ok_fast && ok_try).to_exit()\n"
            "}\n"
        ),
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_zenc_emit_resolves_namespace_bound_calls_before_cgen():
    d = _program({
        "right.zen": "default* = (n: i32) i32 { n + 5 }\n",
        "p.zen": (
            "alloc = std.mem.alloc\n"
            "right = right\n"
            "main = () i32 {\n"
            "    h := alloc.default()\n"
            "    to_i32(30) + right.default(7)\n"
            "}\n"
        ),
    })
    r = subprocess.run([_zenc(), "emit", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "alloc__default()" in r.stdout
    assert "right__default(7)" in r.stdout
    assert "default_zk(alloc)" not in r.stdout
    assert "default_zk(right" not in r.stdout


def test_namespace_bound_large_compiler_module_does_not_overflow_resolver():
    d = _program({
        "p.zen": "cv = compiler.check_validate\nmain = () i32 { 0 }\n",
    })
    zenc = _zenc()

    checked = subprocess.run([zenc, "check", str(d / "p.zen")], capture_output=True, text=True)
    assert checked.returncode == 0, checked.stderr

    emitted = subprocess.run([zenc, "emit", str(d / "p.zen")], capture_output=True, text=True)
    assert emitted.returncode == 0, emitted.stderr
    assert "cv__diagnostic_from_source" in emitted.stdout


def test_namespace_rewriter_preserves_literals_and_comments():
    d = _program({
        "right.zen": (
            "thing* = () i32 { 5 }\n"
            "text* = () str { \"thing\" } // thing in a comment should stay inert\n"
        ),
        "p.zen": (
            "right = right\n"
            "{ eq } = std.text.str\n"
            "{ to_exit } = std.core.bool\n"
            "main = () i32 {\n"
            "    literal := \"right.thing\"\n"
            "    // right.thing in a comment should not be rewritten\n"
            "    ok := eq(literal, \"right.thing\") && eq(right.text(), \"thing\")\n"
            "    ok.to_exit()\n"
            "}\n"
        ),
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

    emitted = subprocess.run([_zenc(), "emit", str(d / "p.zen")], capture_output=True, text=True)
    assert emitted.returncode == 0, emitted.stderr
    assert '"right.thing"' in emitted.stdout
    assert '"right__thing"' not in emitted.stdout


def test_namespace_rewriter_preserves_multiline_block_comments():
    d = _program({
        "p.zen": (
            "{ strip_ns_into, add_name } = std.internal.resolve\n"
            "{ Malloc } = std.mem.alloc\n"
            "{ String, init } = std.text.string\n"
            "{ eq } = std.text.str\n"
            "{ to_exit } = std.core.bool\n"
            "\n"
            "sname = (s: str) String { a := Malloc(_: 0)  a.addr().init(32).append_in(a.addr(), s) }\n"
            "\n"
            "main = () i32 {\n"
            "    a := Malloc(_: 0)\n"
            "    ap := a.addr()\n"
            "    quals := ap.init(32).add_name(ap, sname(\"right\"))\n"
            "    qnames := ap.init(64).add_name(ap, sname(\"right.thing\"))\n"
            "    empty := ap.init(1)\n"
            "    src := \"main = () i32 {\\n/*\\nright.thing\\n*/\\nright.thing()\\n}\\n\"\n"
            "    out := ap.init(256).strip_ns_into(ap, src, 0, quals, qnames, qnames, empty, true).finish_in(ap)\n"
            "    want := \"main = () i32 {\\n/*\\nright.thing\\n*/\\nright__thing()\\n}\"\n"
            "    eq(out, want).to_exit()\n"
            "}\n"
        ),
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_namespace_rewriter_handles_large_qualified_source_without_recursive_stack_growth():
    large_src = "main = () i32 {\n" + "\n".join("right.thing()" for _ in range(3500)) + "\n}\n"
    escaped = large_src.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n")
    d = _program({
        "p.zen": (
            "{ strip_ns_into, add_name } = std.internal.resolve\n"
            "{ Malloc } = std.mem.alloc\n"
            "{ String, init } = std.text.string\n"
            "{ contains } = std.text.str\n"
            "{ to_exit } = std.core.bool\n"
            "\n"
            "sname = (s: str) String { a := Malloc(_: 0)  a.addr().init(32).append_in(a.addr(), s) }\n"
            "\n"
            "main = () i32 {\n"
            "    a := Malloc(_: 0)\n"
            "    ap := a.addr()\n"
            "    quals := ap.init(32).add_name(ap, sname(\"right\"))\n"
            "    qnames := ap.init(64).add_name(ap, sname(\"right.thing\"))\n"
            "    empty := ap.init(1)\n"
            f"    src := \"{escaped}\"\n"
            "    out := ap.init(65536).strip_ns_into(ap, src, 0, quals, qnames, qnames, empty, true).finish_in(ap)\n"
            "    ok := out.contains(\"right__thing()\") && (!out.contains(\"right.thing()\"))\n"
            "    ok.to_exit()\n"
            "}\n"
        ),
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_resolver_append_span_handles_long_source_line_without_recursive_stack_growth():
    large_src = "main = () i32 { 0 } // " + ("x" * 30000) + "tail_marker\n"
    escaped = large_src.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n")
    d = _program({
        "p.zen": (
            "{ strip_ns_into } = std.internal.resolve\n"
            "{ Malloc } = std.mem.alloc\n"
            "{ String, init } = std.text.string\n"
            "{ contains, len } = std.text.str\n"
            "{ to_exit } = std.core.bool\n"
            "\n"
            "main = () i32 {\n"
            "    a := Malloc(_: 0)\n"
            "    ap := a.addr()\n"
            "    empty := ap.init(1)\n"
            f"    src := \"{escaped}\"\n"
            "    out := ap.init(65536).strip_ns_into(ap, src, 0, empty, empty, empty, empty, true).finish_in(ap)\n"
            "    ok := (out.len() > 30000) && out.contains(\"tail_marker\")\n"
            "    ok.to_exit()\n"
            "}\n"
        ),
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_namespace_rewriter_preserves_large_literals_and_comments_without_recursive_stack_growth():
    large_text = "right.thing " * 900
    src = (
        "main = () i32 {\n"
        f"    s := \"{large_text}\"\n"
        f"    // {large_text}\n"
        f"    /* {large_text} */\n"
        "    right.thing()\n"
        "}\n"
    )
    escaped = src.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n")
    d = _program({
        "p.zen": (
            "{ strip_ns_into, add_name } = std.internal.resolve\n"
            "{ Malloc } = std.mem.alloc\n"
            "{ String, init } = std.text.string\n"
            "{ contains } = std.text.str\n"
            "{ to_exit } = std.core.bool\n"
            "\n"
            "sname = (s: str) String { a := Malloc(_: 0)  a.addr().init(32).append_in(a.addr(), s) }\n"
            "\n"
            "main = () i32 {\n"
            "    a := Malloc(_: 0)\n"
            "    ap := a.addr()\n"
            "    quals := ap.init(32).add_name(ap, sname(\"right\"))\n"
            "    qnames := ap.init(64).add_name(ap, sname(\"right.thing\"))\n"
            "    empty := ap.init(1)\n"
            f"    src := \"{escaped}\"\n"
            "    out := ap.init(131072).strip_ns_into(ap, src, 0, quals, qnames, qnames, empty, true).finish_in(ap)\n"
            "    ok := out.contains(\"s := \\\"right.thing\")\n"
            "        && out.contains(\"// right.thing\")\n"
            "        && out.contains(\"/* right.thing\")\n"
            "        && out.contains(\"right__thing()\")\n"
            "    ok.to_exit()\n"
            "}\n"
        ),
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_strip_ns_lines_handles_many_import_and_namespace_lines_without_recursive_stack_growth():
    chunk = "{ thing } = right\nright = right\nkeep = () i32 { 0 }\n"
    large_src = (chunk * 700) + "tail = () i32 { 1 }\n"
    escaped = large_src.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n")
    d = _program({
        "p.zen": (
            "{ strip_ns_into } = std.internal.resolve\n"
            "{ Malloc } = std.mem.alloc\n"
            "{ String, init } = std.text.string\n"
            "{ contains } = std.text.str\n"
            "{ to_exit } = std.core.bool\n"
            "\n"
            "main = () i32 {\n"
            "    a := Malloc(_: 0)\n"
            "    ap := a.addr()\n"
            "    empty := ap.init(1)\n"
            f"    src := \"{escaped}\"\n"
            "    out := ap.init(131072).strip_ns_into(ap, src, 0, empty, empty, empty, empty, true).finish_in(ap)\n"
            "    ok := out.contains(\"tail = () i32 { 1 }\")\n"
            "        && (!out.contains(\"{ thing } = right\"))\n"
            "        && (!out.contains(\"right = right\"))\n"
            "    ok.to_exit()\n"
            "}\n"
        ),
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_namespace_bound_std_collections_can_export_natural_of_without_collision():
    d = _program({
        "right.zen": "of* = (n: i32) i32 { n + 5 }\n",
        "p.zen": (
            "vec = std.collections.vec\n"
            "maps = std.collections.map\n"
            "right = right\n"
            "{ default } = std.mem.alloc\n"
            "main = () i32 {\n"
            "    alloc := default()\n"
            "    a := alloc.addr()\n"
            "    v := vec.of(a, [10, 20])\n"
            "    m := maps.of(a, \"x\", 1)\n"
            "    ok := v.get(0) + v.get(1) + m.get(\"x\", 0) + right.of(6)\n"
            "    v.free(alloc.addr())\n"
            "    m.free(alloc.addr())\n"
            "    ok\n"
            "}\n"
        ),
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 42, r.stderr


def test_namespace_bound_generic_type_annotations_match_qualified_constructors():
    d = _program({
        "p.zen": (
            "vec = std.collections.vec\n"
            "alloc = std.mem.alloc\n"
            "sum = (v: vec.Vec<i32>) i32 { v.get(0) + v.get(1) }\n"
            "main = () i32 {\n"
            "    heap := alloc.default()\n"
            "    v := vec.of(heap.addr(), [19, 23])\n"
            "    v.sum()\n"
            "}\n"
        ),
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 42, r.stderr


def test_namespace_bound_std_runtime_can_export_natural_sync_async_without_collision():
    d = _program({
        "right.zen": "sync* = (n: i32) i32 { n + 1 }\nasync* = (n: i32) i32 { n + 2 }\n",
        "p.zen": (
            "alloc = std.mem.alloc\n"
            "rt = std.concurrent.runtime\n"
            "right = right\n"
            "main = () i32 {\n"
            "    heap := alloc.default()\n"
            "    hp := heap.addr()\n"
            "    s := rt.sync(hp, 128)\n"
            "    a := rt.async(hp, 128)\n"
            "    s.addr().checkpoint()\n"
            "    a.addr().checkpoint()\n"
            "    n := right.sync(10) + right.async(10)\n"
            "    s.addr().free(hp)\n"
            "    a.addr().free(hp)\n"
            "    n - 23\n"
            "}\n"
        ),
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_namespace_bound_std_actor_cell_request_survives_export_name_collision():
    d = _program({
        "right.zen": "cell* = (n: i32) i32 { n + 35 }\n",
        "p.zen": (
            "alloc = std.mem.alloc\n"
            "actor = std.concurrent.actor\n"
            "right = right\n"
            "{ to_exit } = std.core.bool\n"
            "Msg*: Ping(actor.ReplyRef<i32>)\n"
            "Room*: { n: i32 }\n"
            "Room.impl(actor.Receiver<Msg>, {\n"
            "    receive = (room: MutPtr<Room>, ctx: actor.Context<Msg>) void {\n"
            "        ctx.msg.match({ .Ping(reply_to) => reply_to.send(7) })\n"
            "    }\n"
            "})\n"
            "main = () i32 {\n"
            "    heap := alloc.default()\n"
            "    cell: actor.ActorCell<Msg> := actor.cell(heap.addr(), 4)\n"
            "    room := Room(n: 0)\n"
            "    out: i32 := cell.request(heap.addr(), room.addr(), (reply_to) { .Ping(reply_to) })\n"
            "    cell.free(heap.addr())\n"
            "    ((out + right.cell(35)) == 77).to_exit()\n"
            "}\n"
        ),
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_std_string_and_actor_imports_coexist_without_new_in_collision():
    """Regression (BUG #4): importing both std.text.string and std.concurrent.actor used to
    flatten two bare `new_in` decls (string's arity-1 builder vs arena's arity-2, pulled in via
    actor->runtime->arena), so `m.addr().new_in()` resolved to the wrong arity and cascaded into
    ~50 struct-field/arity errors. arena is now namespace-imported inside runtime.zen, so its
    `new_in` is qualified and no longer leaks a bare global. Both modules build + run together."""
    d = _program({
        "p.zen": (
            "{ to_exit } = std.core.bool\n"
            "{ String, new_in } = std.text.string\n"
            "alloc = std.mem.alloc\n"
            "actor = std.concurrent.actor\n"
            "Colour*: { r: u8, g: u8, b: u8 }\n"
            "hex_digit = (n: u8) u8 { (n < 10).match({ true => '0' + n, false => ('a' + n) - 10 }) }\n"
            "push_byte<A> = (s: String, a: MutPtr<A>, v: u8) String {\n"
            "    s2 := s.push_in(a, hex_digit(v / 16))\n"
            "    s2.push_in(a, hex_digit(v % 16))\n"
            "}\n"
            "PixelMsg*: Draw(Colour) | Clear\n"
            "Canvas*: { drawn: i32 }\n"
            "Canvas.impl(actor.Receiver<PixelMsg>, {\n"
            "    receive = (cv: MutPtr<Canvas>, ctx: actor.Context<PixelMsg>) void {\n"
            "        ctx.msg.match({ .Draw(c) => { cv.drawn = cv.drawn + 1 }, .Clear => { cv.drawn = 0 } })\n"
            "    }\n"
            "})\n"
            "main = () i32 {\n"
            "    heap := alloc.default()\n"
            "    a := heap.addr()\n"
            "    c := Colour(r: 255, g: 128, b: 0)\n"
            "    s := a.new_in().push_in(a, '#').push_byte(a, c.r).push_byte(a, c.g).push_byte(a, c.b)\n"
            "    hx := s.finish_in(a)\n"
            "    canvas: actor.ActorHandle<PixelMsg, Canvas> := actor.spawn(a, 8, Canvas(drawn: 0))\n"
            "    canvas.send(.Draw(c))\n"
            "    canvas.send(.Clear)\n"
            "    canvas.send(.Draw(c))\n"
            "    canvas.run()\n"
            "    canvas.free(a)\n"
            "    ok := (hx.at(0) == '#') && (hx.at(1) == 'f') && (hx.at(2) == 'f') && (hx.at(3) == '8')\n"
            "    ok.to_exit()\n"
            "}\n"
        ),
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_std_slice_and_text_imports_coexist_without_dup_in_collision():
    """Regression (COLLIDE-1): std.core.slice exported `dup_in<A,T>(a, [T])` (element copy) and
    std.text.str exported `dup_in<A>(a, str)` (byte copy). Flattened together (str loaded via
    std.text.fmt for println), str's bare `dup_in` shadowed slice's, so `slice.node_in`/`dup`
    mis-resolved to the str version -> arg-type error, or (via node_in) a C-miscompile that sized
    the allocation as `len` bytes instead of `len*sizeof(T)` -> heap corruption for T>u8. str's
    family is now `dup_bytes`/`dup_bytes_in`, so slice's `dup_in`/`node_in` resolve correctly even
    when str is loaded. Both build + run."""
    d = _program({
        "p.zen": (
            "{ println } = std.text.fmt\n"          # pulls in std.text.str
            "alloc = std.mem.alloc\n"
            "{ dup, node_in } = std.core.slice\n"
            "main = () i32 {\n"
            "    m := alloc.default()\n"
            "    xs: [i32] := m.addr().dup([10, 20, 30])\n"   # slice element-copy, not str byte-copy
            "    p := m.addr().node_in(777)\n"                # heap-alloc a node (the miscompile path)
            "    println(xs[2] + p.load())\n"                 # 30 + 777 = 807
            "    0\n"
            "}\n"
        ),
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "807", r.stdout


def test_namespace_bound_std_cown_can_export_natural_buf_file_without_collision():
    d = _program({
        "right.zen": "buf* = (n: i32) i32 { n + 5 }\nfile* = (n: i32) i32 { n + 7 }\n",
        "p.zen": (
            "cown = std.concurrent.cown\n"
            "right = right\n"
            "{ default } = std.mem.alloc\n"
            "main = () i32 {\n"
            "    alloc := default()\n"
            "    a := alloc.addr()\n"
            "    b := cown.buf(a, 8)\n"
            "    b.addr().set(0, 'Z')\n"
            "    missing := cown.file(a, \"/tmp/zen-cown-no-such-file\")\n"
            "    missing_is_err := missing.match({ .Err(e) => true, .Ok(f) => false })\n"
            "    ok := (b.addr().get(0) == 'Z') && missing_is_err && ((right.buf(3) + right.file(4)) == 19)\n"
            "    b.addr().free(a)\n"
            "    ok.match({ true => 0, false => 1 })\n"
            "}\n"
        ),
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_namespace_bound_siblings_can_export_same_type_name():
    d = _program({
        "left.zen": "Box*: { v: i32 }\nmake* = () Box { Box(v: 7) }\n",
        "right.zen": "Box*: { v: i32 }\nmake* = () Box { Box(v: 9) }\n",
        "p.zen": "left = left\nright = right\nmain = () i32 { left.make().v + right.make().v }\n",
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 16, r.stderr


def test_sibling_import_cycle_terminates_and_runs():
    """a imports b imports a: the per-module seen-set breaks the cycle — each body emitted once."""
    d = _program({
        "aa.zen": "{ g } = bb\nf* = (n: i32) i32 { (n <= 0).match ({ true => 0, false => g(n - 1) + 1 }) }\n",
        "bb.zen": "{ f } = aa\ng* = (n: i32) i32 { (n <= 0).match ({ true => 0, false => f(n - 1) + 1 }) }\n",
        "p.zen": "{ f } = aa\nmain = () i32 { f(7) }\n",
    })
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 7, r.stderr


# ── error quality (the point): loader errors, not linker spew ────────────────────────────────────
def test_unknown_module_is_a_loader_error_not_linker_spew():
    d = _program({"p.zen": "{ f } = nosuch\nmain = () i32 { f() }\n"})
    r = subprocess.run([_zenc(), "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 1
    assert r.stderr == f"zenc: {d}/p.zen: error: unknown module 'nosuch' (no nosuch.zen next to {d}/p.zen)\n"
    assert "undefined reference" not in r.stderr


def test_unknown_name_in_sibling_module_names_both():
    d = _program({
        "b.zen": "helper* = (x: i32) i32 { x }\n",
        "p.zen": "{ nope } = b\nmain = () i32 { 0 }\n",
    })
    r = subprocess.run([_zenc(), "check", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 1
    assert r.stderr == f"zenc: {d}/p.zen: error: unknown name 'nope' in module 'b' (no such top-level definition)\n"


def test_unknown_name_validation_covers_std_imports_too():
    d = _program({"p.zen": "{ nosuchname } = std.text.fmt\nmain = () i32 { 0 }\n"})
    r = subprocess.run([_zenc(), "check", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 1
    assert "unknown name 'nosuchname' in module 'std.text.fmt'" in r.stderr


def test_unknown_std_module_is_clean_too():
    d = _program({"p.zen": "{ x } = std.nosuchmod\nmain = () i32 { 0 }\n"})
    r = subprocess.run([_zenc(), "check", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 1
    assert "unknown module 'std.nosuchmod'" in r.stderr


def test_name_collision_between_sibling_modules_is_rejected():
    """std-vs-std keeps the silent first-wins dedup; two USER files defining the same name reject."""
    d = _program({
        "c1.zen": "dupf* = () i32 { 1 }\n",
        "c2.zen": "dupf* = () i32 { 2 }\n",
        "p.zen": "{ dupf } = c1\n{ dupf } = c2\nmain = () i32 { dupf() }\n",
    })
    r = subprocess.run([_zenc(), "check", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 1
    assert "duplicate top-level definition 'dupf'" in r.stderr
    assert "'c2'" in r.stderr                      # the redefining module is named


def test_dup_user_error_names_origin_and_suggests_qualified_import():
    """Stopgap UX (design option b): the collision diagnostic must NAME the origin module the name
    was first provided by AND suggest the qualified-import fix — not just say 'duplicate'."""
    d = _program({
        "c1.zen": "dupf* = () i32 { 1 }\n",
        "c2.zen": "dupf* = () i32 { 2 }\n",
        "p.zen": "{ dupf } = c1\n{ dupf } = c2\nmain = () i32 { dupf() }\n",
    })
    r = subprocess.run([_zenc(), "check", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 1
    assert "duplicate top-level definition 'dupf'" in r.stderr   # names the symbol
    assert "'c2'" in r.stderr                                    # names the redefining module
    assert "'c1'" in r.stderr                                    # names the ORIGIN module (new)
    assert "hint:" in r.stderr                                   # actionable hint (new)
    assert "m = c1" in r.stderr and "m.dupf" in r.stderr         # suggests qualified access (new)


def test_keyword_safe_name_collision_between_siblings_is_rejected():
    d = _program({
        "c1.zen": "default* = () i32 { 1 }\n",
        "c2.zen": "default_zk* = () i32 { 2 }\n",
        "p.zen": "{ default } = c1\n{ default_zk } = c2\nmain = () i32 { default() + default_zk() }\n",
    })
    r = subprocess.run([_zenc(), "check", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 1
    assert "duplicate top-level definition 'default_zk'" in r.stderr
    assert "'c2'" in r.stderr


def test_c_keyword_symbol_key_collision_between_siblings_is_rejected():
    d = _program({
        "c1.zen": "struct* = () i32 { 1 }\n",
        "c2.zen": "struct_zk* = () i32 { 2 }\n",
        "p.zen": "{ struct } = c1\n{ struct_zk } = c2\nmain = () i32 { struct() + struct_zk() }\n",
    })
    r = subprocess.run([_zenc(), "check", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 1
    assert "duplicate top-level definition 'struct_zk'" in r.stderr
    assert "'c2'" in r.stderr


def test_main_redefining_an_imported_sibling_name_is_rejected():
    """the existing dedup rule: a name BOTH imported and defined by the main file reaches the
    validator as a duplicate (silent shadowing was a miscompile trap)."""
    d = _program({
        "b.zen": "helper* = (x: i32) i32 { x }\n",
        "p.zen": "{ helper } = b\nhelper = (x: i32) i32 { x + 1 }\nmain = () i32 { helper(1) }\n",
    })
    r = subprocess.run([_zenc(), "check", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 1
    assert "duplicate top-level definition" in r.stderr


# ── stdin mode: no program directory ─────────────────────────────────────────────────────────────
def test_stdin_sibling_import_errors_cleanly():
    """`cat prog.zen | zenc` has no directory to resolve a sibling from — clean error, not garbage C."""
    src = "{ helper } = b\nmain = () i32 { helper(21) }\n"
    r = subprocess.run([_zenc()], input=src, capture_output=True, text=True)
    assert r.returncode == 1
    assert "sibling import 'b'" in r.stderr
    assert "stdin" in r.stderr
    assert r.stdout == ""                          # no half-emitted C


def test_stdin_without_sibling_imports_stays_the_classic_filter():
    """the oracle's source→C filter mode is untouched for import-free source."""
    r = subprocess.run([_zenc()], input="main = () i32 { 6 * 7 }\n", capture_output=True, text=True)
    assert r.returncode == 0
    assert "int32_t zen_main(" in r.stdout    # the Zen `main` is emitted as zen_main; zenrt.c owns the OS main
