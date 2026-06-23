import re
from pathlib import Path

import _oracle


ROOT = _oracle.ROOT

RAW_CHECKPOINT_ALLOWED = {
    Path("zen/std/concurrent/coroutine.zen"),
    Path("zen/std/concurrent/runtime.zen"),
}

ATWHILE_ALLOWED = {
    Path("zen/compiler/parse.zen"),
    Path("zen/compiler/parse_expr.zen"),
    Path("zen/compiler/parse_stmt.zen"),
    # genfmt EMITS the `@while` token as formatter output text (pretty-printing a While stmt back to
    # source) — codegen text, not a control-flow use; same category as genc_emit's allow-listed malloc.
    Path("zen/compiler/genfmt.zen"),
}

RAW_ALLOC_ALLOWED = {
    Path("zen/std/mem/alloc.zen"),
    Path("zen/std/mem/raw.zen"),
    # std.thread is the OS-thread FFI floor (wraps pthread). Its two raw 8-byte cells are the
    # pthread_t and void*-retval OUT-PARAMS that pthread_create/join write into — raw C threading
    # scratch, same FFI-floor category as raw.zen. FOLLOW-UP (parallelism cleanup): move these into
    # the JoinHandle by-value (needs address-of-field — blocked on the .addr()-of-field limit) or
    # thread an allocator through spawn/join, to drop even the floor malloc.
    Path("zen/std/thread.zen"),
    # std.concurrent.pool is the work-stealing scheduler. The CROSS-THREAD-SHARED actor state is now
    # ARC-BACKED (goal item E, DONE): pool_spawn allocates the PoolActor block via std.mem.arc's
    # new_in, sharing CLONEs the Arc (atomic +1), and the LAST handle drop frees it — so a sender on
    # one worker can never use-after-free an actor whose owner finished on another (Arc's atomic
    # refcount is now load-bearing under contention; proven by pool_arc_contention.zen, 50x ASan-clean).
    # The malloc calls that REMAIN here are NOT the shared actor state: they are (a) the pool's own
    # SINGLE-OWNER infrastructure (the Pool block, the global run-queue ring, the per-worker stats, the
    # pthread handle/arg cells) — freed by the one owner in pool_close after the workers join, the same
    # floor justification as std.thread; and (b) the per-actor mailbox ring, which the Arc'd actor OWNS
    # and frees in its last-drop destructor (so it too has no free-while-a-sender-holds-a-ref hazard).
    Path("zen/std/concurrent/pool.zen"),
    Path("zen/compiler/genc.zen"),
    # genc_emit emits malloc/memcpy as the LOWERING of a heap-promoted slice literal (codegen text,
    # not a call) — same codegen category as genc.zen, which is already allow-listed.
    Path("zen/compiler/genc_emit.zen"),
}

EXAMPLE_PRIMITIVES = {
    "raw addr": re.compile(r"(?<!\.)\baddr\s*\("),
    "raw checkpoint": re.compile(r"\bcheckpoint_current\s*\("),
    "@while": re.compile(r"@while\b"),
    "raw break": re.compile(r"\bbreak\b"),
    "raw continue": re.compile(r"\bcontinue\b"),
    "malloc": re.compile(r"\bmalloc\s*\("),
    "load": re.compile(r"\bload\s*\("),
    "store": re.compile(r"\bstore\s*\("),
    "load_i64": re.compile(r"\bload_i64\s*\("),
    "store_i64": re.compile(r"\bstore_i64\s*\("),
    "atomic_add_i64": re.compile(r"\batomic_add_i64\s*\("),
    "offset": re.compile(r"(?:\boffset|\.\s*offset)\s*\("),
    "null_ptr": re.compile(r"\bnull_ptr\s*\("),
    "slice": re.compile(r"\bslice\s*\("),
    "cstr": re.compile(r"\bcstr\s*\("),
    "sizeof": re.compile(r"\bsizeof\s*\("),
}


def _zen_files_under(*roots: str):
    files = []
    for root in roots:
        files.extend((ROOT / root).rglob("*.zen"))
    return sorted(files)


def _code(path: Path) -> str:
    return "\n".join(line.split("//", 1)[0] for line in path.read_text().splitlines())


def _rel(path: Path) -> Path:
    return path.relative_to(ROOT)


def test_examples_stay_above_raw_primitives():
    hits = []
    for path in _zen_files_under("examples"):
        src = _code(path)
        for name, pattern in EXAMPLE_PRIMITIVES.items():
            if pattern.search(src):
                hits.append(f"{_rel(path)} uses {name}")

    assert not hits, "examples should use stdlib/runtime APIs, not raw primitives:\n" + "\n".join(hits)


def test_raw_checkpoint_stays_behind_coroutine_and_runtime():
    checkpoint_call = re.compile(r"\bcheckpoint_current\s*\(")
    checkpoint_import = re.compile(r"\{[^}\n]*\bcheckpoint_current\b[^}\n]*\}\s*=\s*std\.concurrent\.coroutine")
    hits = []

    for path in _zen_files_under("examples", "tools", "zen/std", "zen/compiler"):
        rel = _rel(path)
        src = _code(path)
        if rel not in RAW_CHECKPOINT_ALLOWED and (checkpoint_call.search(src) or checkpoint_import.search(src)):
            hits.append(str(rel))

    assert not hits, "call runtime.addr().checkpoint(); raw checkpoint_current is only for std.concurrent.coroutine/std.concurrent.runtime:\n" + "\n".join(hits)


def test_atwhile_stays_in_compiler_or_named_low_level_substrate():
    hits = []

    for path in _zen_files_under("examples", "tools", "zen/std", "zen/compiler"):
        rel = _rel(path)
        if rel not in ATWHILE_ALLOWED and re.search(r"@while\b", _code(path)):
            hits.append(str(rel))

    assert not hits, "@while is a substrate primitive; public code should use loop handles:\n" + "\n".join(hits)


def test_raw_allocation_calls_stay_behind_allocator_boundaries():
    raw_alloc = re.compile(r"(?<!\.)\b(?:malloc|calloc|realloc|free)\s*\(")
    hits = []

    for path in _zen_files_under("examples", "tools", "zen/std", "zen/compiler"):
        rel = _rel(path)
        if rel not in RAW_ALLOC_ALLOWED and raw_alloc.search(_code(path)):
            hits.append(str(rel))

    assert not hits, (
        "raw malloc/calloc/realloc/free must stay behind std.mem alloc/raw or the compiler bootstrap shim; "
        "thread an allocator and use acquire/resize/release instead:\n" + "\n".join(hits)
    )


def test_trace_gather_does_not_fall_back_to_default_list_growth():
    src = _code(ROOT / "zen" / "std" / "mem" / "trace.zen")
    gather = src.split("cc_gather = ", 1)[1].split("Node*: ", 1)[0]
    assert ".list_push(" not in gather, "trace gather must use collection-owned scratch capacity, not default list growth"
    assert ".list_push_static(" in gather


def test_io_contents_allocator_path_uses_try_acquire():
    src = _code(ROOT / "zen" / "std" / "io" / "file.zen")
    body = src.split("read_file_alloc", 1)[1].split("read_file_open", 1)[0]
    assert ".try_acquire(" in body, "std.io.file contents_in should keep allocation failure in Result flow"
    assert ".acquire(" not in body, "std.io.file contents_in should not hand-roll null checks around acquire"
    assert "default()" not in src, "std.io.file should not allocate through a hidden default heap"


def test_map_try_paths_use_result_allocator_helpers():
    src = _code(ROOT / "zen" / "std" / "collections" / "map.zen")
    grow = src.split("try_grow", 1)[1].split("append<A>", 1)[0]
    append = src.split("try_append", 1)[1].split("put<A>", 1)[0]
    of = src.split("try_of*", 1)[1]
    assert ".try_acquire(" in grow
    assert ".acquire(" not in grow
    assert ".try_grow(" in append
    assert ".acquire(" not in append
    assert ".try_acquire(" in of
    assert ".acquire(" not in of


def test_fmt_try_numeric_writes_use_fallible_num_helpers():
    src = _code(ROOT / "zen" / "std" / "text" / "fmt.zen")
    ti = src.split("try_write_int_in", 1)[1].split("try_write_float_in", 1)[0]
    tf = src.split("try_write_float_in", 1)[1].split("write_int = ", 1)[0]
    assert ".try_integer_in(" in ti
    assert ".integer_in(" not in ti
    assert ".try_float_in(" in tf
    assert ".float_in(" not in tf
    wi = src.split("write_int = ", 1)[1].split("write_fpad", 1)[0]
    wf = src.split("write_float = ", 1)[1].split("// Display", 1)[0]
    assert "default()" not in src, "std.text.fmt default printing must not hide heap allocation"
    assert ".integer_in(" not in wi and ".write_int_in(" not in wi
    assert ".float_in(" not in wf and ".write_float_in(" not in wf
