#!/usr/bin/env python3
"""Generate a body-free inventory of declarations in src/**/*.zen.

This deliberately uses Zen's tree-sitter grammar instead of guessing from
lines.  In Zen the right-hand side of ``Name = ...`` distinguishes imports,
aliases, constants, structs, enums, and functions, so a regular-expression
extractor cannot classify declarations correctly.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path
import sys
import warnings

from tree_sitter import Language, Node, Parser


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "src"
DEFAULT_GRAMMAR = ROOT / "grammar" / "zen.so"
DEFAULT_OUTPUT = ROOT / "docs" / "ZEN_SIGNATURES.md"

CATEGORY_ORDER = (
    "Types",
    "Enums",
    "Aliases",
    "Implementations",
    "Functions",
    "Constants",
    "Imports and re-exports",
)


def parser_for(grammar: Path) -> Parser:
    if not grammar.is_file():
        raise SystemExit(f"missing {grammar}; run `make grammar`")
    warnings.filterwarnings("ignore", category=FutureWarning)
    language = Language(str(grammar), "zen")
    parser = Parser()
    parser.set_language(language)
    return parser


def walk(node: Node):
    yield node
    for child in node.children:
        yield from walk(child)


def merged_edits(edits: list[tuple[int, int, bytes]]) -> list[tuple[int, int, bytes]]:
    """Return non-overlapping edits, preferring an enclosing body deletion."""
    ordered = sorted(edits, key=lambda edit: (edit[0], -edit[1]))
    out: list[tuple[int, int, bytes]] = []
    for start, end, replacement in ordered:
        if out and start < out[-1][1]:
            # Comments and nested functions inside an omitted body need no
            # separate edit.  Other overlaps indicate an extractor bug.
            if end <= out[-1][1]:
                continue
            raise RuntimeError(f"overlapping edits at bytes {start}:{end}")
        out.append((start, end, replacement))
    return out


def signature_text(node: Node, source: bytes) -> str:
    """Render a declaration, omitting comments and every function body."""
    edits: list[tuple[int, int, bytes]] = []
    for item in walk(node):
        if item.type in ("line_comment", "block_comment"):
            edits.append((item.start_byte, item.end_byte, b""))
        if item.type == "function":
            body = item.child_by_field_name("body")
            if body is not None:
                # An omitted return type on a function with a body means ().
                # Write it explicitly because the body-free result is now a
                # function signature, where the grammar requires a return.
                replacement = (
                    b" ()" if item.child_by_field_name("return_type") is None else b""
                )
                edits.append((body.start_byte, body.end_byte, replacement))

    begin = node.start_byte
    cursor = begin
    chunks: list[bytes] = []
    for start, end, replacement in merged_edits(edits):
        chunks.append(source[cursor:start])
        chunks.append(replacement)
        cursor = end
    chunks.append(source[cursor : node.end_byte])
    text = b"".join(chunks).decode("utf-8")

    # Comment/body removal may leave whitespace-only lines.  Preserve the
    # original multiline signature layout while removing that noise.
    lines = [line.rstrip() for line in text.splitlines()]
    compact = [line for line in lines if line.strip()]
    return "\n".join(compact).strip()


def category_of(declaration: Node) -> str:
    if declaration.type == "impl_declaration":
        return "Implementations"
    value = declaration.child_by_field_name("value")
    if value is None:
        raise RuntimeError(
            f"declaration at {declaration.start_point} has no value field"
        )
    # A plain identifier is an alias only for a single declared name.  Zen's
    # multi-name form is necessarily an import, including imports from a
    # one-component module path (`A, make = package`).
    if len(declaration.children_by_field_name("name")) > 1:
        return "Imports and re-exports"
    return {
        "struct_body": "Types",
        "enum_body": "Enums",
        "generic_type": "Aliases",
        "identifier": "Aliases",
        "function": "Functions",
        "function_signature": "Functions",
        "member_expression": "Imports and re-exports",
    }.get(value.type, "Constants")


def declarations_of(root: Node) -> list[Node]:
    return [
        child
        for child in root.named_children
        if child.type in ("declaration", "impl_declaration")
    ]


def generate(source_root: Path, grammar: Path) -> tuple[str, Counter[str]]:
    parser = parser_for(grammar)
    files = sorted(source_root.rglob("*.zen"))
    if not files:
        raise SystemExit(f"no .zen files below {source_root}")

    parsed: list[tuple[Path, bytes, list[Node]]] = []
    totals: Counter[str] = Counter()
    for path in files:
        source = path.read_bytes()
        tree = parser.parse(source)
        root = tree.root_node
        if root.has_error:
            raise SystemExit(f"tree-sitter reported a parse error in {path}")
        declarations = declarations_of(root)
        parsed.append((path, source, declarations))
        totals["Files"] += 1
        totals["Declarations"] += len(declarations)
        for declaration in declarations:
            totals[category_of(declaration)] += 1

    rows = [
        ("Zen files", totals["Files"]),
        ("Top-level declarations", totals["Declarations"]),
    ] + [(category, totals[category]) for category in CATEGORY_ORDER]

    out = [
        "# Zen source signature inventory",
        "",
        "Generated from every `src/**/*.zen` file by",
        "`python3 scripts/zen_signature_inventory.py`. The extractor uses the",
        "repository's tree-sitter grammar, preserves multiline source spelling,",
        "and omits implementation bodies. An omitted function return is rendered",
        "as `()` so the body-free declaration remains an explicit signature.",
        "",
        "This is an inventory, not an architectural recommendation. Imports and",
        "constants are included so aliases and public surfaces are not mistaken for",
        "free functions during a later ownership review.",
        "The corresponding decisions are in",
        "[`SOURCE_OWNERSHIP_AUDIT.md`](SOURCE_OWNERSHIP_AUDIT.md).",
        "",
        "## Coverage",
        "",
        "| Item | Count |",
        "| --- | ---: |",
    ]
    out.extend(f"| {label} | {count} |" for label, count in rows)
    out.extend(["", "## Files", ""])

    for path, source, declarations in parsed:
        relative = path.relative_to(ROOT).as_posix()
        grouped: dict[str, list[str]] = defaultdict(list)
        for declaration in declarations:
            grouped[category_of(declaration)].append(
                signature_text(declaration, source)
            )

        out.extend([f"### `{relative}`", ""])
        if not declarations:
            out.extend(["_No top-level declarations._", ""])
            continue
        counts = ", ".join(
            f"{category.lower()}: {len(grouped[category])}"
            for category in CATEGORY_ORDER
            if grouped[category]
        )
        out.extend([f"{len(declarations)} declarations ({counts}).", ""])
        for category in CATEGORY_ORDER:
            entries = grouped[category]
            if not entries:
                continue
            out.extend([f"#### {category}", "", "```zen"])
            out.append("\n\n".join(entries))
            out.extend(["```", ""])

    return "\n".join(out).rstrip() + "\n", totals


def main() -> int:
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    args.add_argument("--grammar", type=Path, default=DEFAULT_GRAMMAR)
    args.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args.add_argument(
        "--check",
        action="store_true",
        help="fail when the output differs instead of writing it",
    )
    options = args.parse_args()
    document, totals = generate(options.source.resolve(), options.grammar.resolve())
    output = options.output.resolve()
    if options.check:
        if not output.is_file() or output.read_text() != document:
            print(f"stale signature inventory: {output}", file=sys.stderr)
            return 1
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(document)
    print(
        f"{totals['Files']} files, {totals['Declarations']} declarations -> {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
