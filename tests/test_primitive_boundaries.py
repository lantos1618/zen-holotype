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
    # Temporary low-level string scanner. Once std gets a loop primitive that can
    # express condition-driven scans, this should move off @while too.
    Path("zen/std/text/str.zen"),
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
