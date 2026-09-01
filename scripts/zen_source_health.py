#!/usr/bin/env python3
"""Measure structural review signals in Zen source and keep comparable snapshots.

The measurements are intentionally mechanical. They rank files for human or
external-model review; they do not declare that a long signature, import, or
comment is wrong.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys

from zen_signature_inventory import (
    DEFAULT_GRAMMAR,
    DEFAULT_SOURCE,
    ROOT,
    category_of,
    declarations_of,
    parser_for,
    walk,
)


DEFAULT_SNAPSHOTS = ROOT / "docs" / "source_health"
DEFAULT_REPORT = ROOT / "docs" / "SOURCE_HEALTH.md"
HISTORY_MARKERS = re.compile(
    r"\b(PLAN\.md|issue|measured|previous(?:ly)?|temporary|eventual|"
    r"benchmark|reported|stage [0-9]|used to)\b",
    re.IGNORECASE,
)


def text_of(node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8")


def module_of(path: Path, source_root: Path) -> str:
    relative = path.relative_to(source_root)
    parts = list(relative.with_suffix("").parts)
    if len(parts) > 1 and parts[-1] == parts[-2]:
        parts.pop()
    return ".".join(parts)


def function_shape(node, source: bytes) -> tuple[tuple[str, ...], str]:
    parameters = node.child_by_field_name("parameters")
    types: list[str] = []
    if parameters is not None:
        for parameter in parameters.named_children:
            ty = parameter.child_by_field_name("type")
            spelling = "?" if ty is None else " ".join(text_of(ty, source).split())
            types.append(spelling)
    result = node.child_by_field_name("return_type")
    returned = "()" if result is None else " ".join(text_of(result, source).split())
    return tuple(types), returned


def comment_measure(root, source: bytes) -> tuple[int, int, int]:
    lines: set[int] = set()
    blocks = 0
    history = 0
    for node in walk(root):
        if node.type not in ("line_comment", "block_comment"):
            continue
        blocks += 1
        lines.update(range(node.start_point[0] + 1, node.end_point[0] + 2))
        if HISTORY_MARKERS.search(text_of(node, source)):
            history += 1
    return len(lines), blocks, history


def control_measure(root, source: bytes) -> tuple[int, int, int, int]:
    match_blocks = 0
    single_arm_matches = 0
    unit_branch_matches = 0
    then_calls = 0
    for node in walk(root):
        if node.type == "match_block":
            match_blocks += 1
            arms = [child for child in node.named_children if child.type == "match_arm"]
            single_arm_matches += len(arms) == 1
            values = [arm.child_by_field_name("value") for arm in arms]
            unit_branch_matches += len(arms) == 2 and sum(
                value is not None and text_of(value, source).strip() == "()"
                for value in values
            ) == 1
        if node.type != "call_expression":
            continue
        function = node.child_by_field_name("function")
        if function is not None and text_of(function, source).rstrip().endswith(".then"):
            then_calls += 1
    return match_blocks, single_arm_matches, unit_branch_matches, then_calls


def measure(source_root: Path, grammar: Path, label: str, revision: str) -> dict:
    parser = parser_for(grammar)
    paths = sorted(source_root.rglob("*.zen"))
    modules = {module_of(path, source_root): path for path in paths}
    files: dict[str, dict] = {}
    dependencies: dict[str, set[str]] = {}

    for path in paths:
        source = path.read_bytes()
        root = parser.parse(source).root_node
        if root.has_error:
            raise SystemExit(f"tree-sitter reported a parse error in {path}")
        relative = (Path("src") / path.relative_to(source_root)).as_posix()
        declarations = declarations_of(root)
        functions = [node for node in walk(root) if node.type == "function"]
        arities = [len(function_shape(node, source)[0]) for node in functions]
        shapes = Counter(
            function_shape(node, source)
            for node in functions
            if len(function_shape(node, source)[0]) >= 4
        )
        repeated_shapes = sum(count - 1 for count in shapes.values() if count > 1)
        comment_lines, comment_blocks, history_blocks = comment_measure(root, source)
        match_blocks, single_arm_matches, unit_branch_matches, then_calls = (
            control_measure(root, source)
        )

        imports = []
        same_folder_aliases = 0
        for declaration in declarations:
            if category_of(declaration) != "Imports and re-exports":
                continue
            value = declaration.child_by_field_name("value")
            if value is None:
                continue
            target = "".join(text_of(value, source).split())
            target_path = modules.get(target)
            if target_path is None:
                continue
            imports.append(
                (Path("src") / target_path.relative_to(source_root)).as_posix()
            )
            if target_path.parent == path.parent:
                same_folder_aliases += len(declaration.children_by_field_name("name"))
        dependencies[relative] = set(imports)

        lines = source.count(b"\n") + (0 if source.endswith(b"\n") else 1)
        high_arity = sum(arity >= 8 for arity in arities)
        relay_excess = sum(max(0, arity - 5) for arity in arities)
        files[relative] = {
            "lines": lines,
            "declarations": len(declarations),
            "functions": len(functions),
            "parameter_slots": sum(arities),
            "max_arity": max(arities, default=0),
            "high_arity_functions": high_arity,
            "relay_excess": relay_excess,
            "repeated_signature_shapes": repeated_shapes,
            "comment_lines": comment_lines,
            "comment_blocks": comment_blocks,
            "history_marker_blocks": history_blocks,
            "match_blocks": match_blocks,
            "single_arm_matches": single_arm_matches,
            "unit_branch_matches": unit_branch_matches,
            "then_calls": then_calls,
            "same_folder_aliases": same_folder_aliases,
            "sibling_modules": len(
                {item for item in imports if Path(item).parent == Path(relative).parent}
            ),
            "mutual_siblings": 0,
        }

    for path, peers in dependencies.items():
        parent = Path(path).parent
        files[path]["mutual_siblings"] = sum(
            Path(peer).parent == parent and path in dependencies.get(peer, set())
            for peer in peers
        )

    for item in files.values():
        # This is a review-priority score, not a quality score. Its fixed
        # weights keep rankings comparable between rounds.
        item["review_priority"] = (
            item["high_arity_functions"] * 10
            + item["relay_excess"] * 2
            + item["repeated_signature_shapes"] * 5
            + item["mutual_siblings"] * 6
            + item["sibling_modules"] * 2
            + item["history_marker_blocks"] * 2
            + item["single_arm_matches"] * 2
            + item["unit_branch_matches"]
            + max(0, item["lines"] - 800) // 100
        )

    totals = {
        "files": len(files),
        "lines": sum(item["lines"] for item in files.values()),
        "declarations": sum(item["declarations"] for item in files.values()),
        "functions": sum(item["functions"] for item in files.values()),
        "parameter_slots": sum(item["parameter_slots"] for item in files.values()),
        "high_arity_functions": sum(
            item["high_arity_functions"] for item in files.values()
        ),
        "relay_excess": sum(item["relay_excess"] for item in files.values()),
        "repeated_signature_shapes": sum(
            item["repeated_signature_shapes"] for item in files.values()
        ),
        "comment_lines": sum(item["comment_lines"] for item in files.values()),
        "history_marker_blocks": sum(
            item["history_marker_blocks"] for item in files.values()
        ),
        "match_blocks": sum(item["match_blocks"] for item in files.values()),
        "single_arm_matches": sum(
            item["single_arm_matches"] for item in files.values()
        ),
        "unit_branch_matches": sum(
            item["unit_branch_matches"] for item in files.values()
        ),
        "then_calls": sum(item["then_calls"] for item in files.values()),
        "same_folder_aliases": sum(
            item["same_folder_aliases"] for item in files.values()
        ),
        "mutual_sibling_edges": sum(
            item["mutual_siblings"] for item in files.values()
        ),
    }
    ranked = sorted(
        files,
        key=lambda path: (
            -files[path]["review_priority"],
            -files[path]["high_arity_functions"],
            path,
        ),
    )
    return {
        "schema": 3,
        "label": label,
        "revision": revision,
        "totals": totals,
        "ranking": ranked,
        "files": files,
    }


def delta(now: int, before: int) -> str:
    change = now - before
    return "—" if change == 0 else f"{change:+d}"


def report_of(snapshots: list[dict]) -> str:
    latest = snapshots[-1]
    metrics = (
        ("Files", "files"),
        ("Lines", "lines"),
        ("Functions", "functions"),
        ("Parameter slots", "parameter_slots"),
        ("Functions with 8+ parameters", "high_arity_functions"),
        ("Relay excess above five parameters", "relay_excess"),
        ("Repeated 4+-parameter signature shapes", "repeated_signature_shapes"),
        ("Same-folder imported aliases", "same_folder_aliases"),
        ("Mutual sibling import edges", "mutual_sibling_edges"),
        ("Comment lines", "comment_lines"),
        ("History-marker comment blocks", "history_marker_blocks"),
        ("Single-arm match blocks", "single_arm_matches"),
        ("Boolean/unit match candidates", "unit_branch_matches"),
    )
    out = [
        "# Zen source health",
        "",
        "Generated by `python3 scripts/zen_source_health.py`. These are stable",
        "review signals, not pass/fail targets. A lower number is useful only when",
        "ownership, behavior, and dependency direction also improve.",
        "",
        "## History",
        "",
        "| Round | Revision | " + " | ".join(label for label, _ in metrics) + " |",
        "| --- | --- | " + " | ".join("---:" for _ in metrics) + " |",
    ]
    for snapshot in snapshots:
        values = [str(snapshot["totals"][key]) for _, key in metrics]
        out.append(
            f"| {snapshot['label']} | `{snapshot['revision']}` | "
            + " | ".join(values)
            + " |"
        )

    if len(snapshots) > 1:
        before = snapshots[-2]["totals"]
        now = latest["totals"]
        out.extend(
            [
                "",
                "## Latest delta",
                "",
                "| Metric | Change |",
                "| --- | ---: |",
            ]
        )
        out.extend(
            f"| {label} | {delta(now[key], before[key])} |" for label, key in metrics
        )

    out.extend(
        [
            "",
            f"## Current review ranking — {latest['label']}",
            "",
            "The priority score weights high arity, parameter relay, repeated",
            "signature shapes, sibling coupling, history-marked comments, and only",
            "then line count. It selects the next files to inspect; it does not",
            "authorize a mechanical rewrite.",
            "",
            "| Rank | File | Score | 8+ args | Slots | Repeated shapes | Sibling imports | Mutual | Then candidates | Comment lines | History markers |",
            "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for rank, path in enumerate(latest["ranking"][:40], 1):
        item = latest["files"][path]
        out.append(
            f"| {rank} | `{path}` | {item['review_priority']} | "
            f"{item['high_arity_functions']} | {item['parameter_slots']} | "
            f"{item['repeated_signature_shapes']} | {item['sibling_modules']} | "
            f"{item['mutual_siblings']} | "
            f"{item['single_arm_matches'] + item['unit_branch_matches']} | "
            f"{item['comment_lines']} | "
            f"{item['history_marker_blocks']} |"
        )
    out.extend(
        [
            "",
            "## External review",
            "",
            "Each implementation round stores a separate Gemini Flash review next",
            "to its JSON snapshot. The model receives the current signatures, this",
            "metric report, the previous external ranking, and the style constraints.",
            "It is asked to rank bounded implementation lanes and to reject metric",
            "gaming, parameter bags, dependency reversals, and behavior regressions.",
            "",
        ]
    )
    return "\n".join(out)


def load_snapshots(directory: Path) -> list[dict]:
    snapshots = [
        json.loads(path.read_text()) for path in sorted(directory.glob("*.json"))
    ]
    return [snapshot for snapshot in snapshots if snapshot.get("schema") == 3]


def main() -> int:
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    args.add_argument("--grammar", type=Path, default=DEFAULT_GRAMMAR)
    args.add_argument("--snapshots", type=Path, default=DEFAULT_SNAPSHOTS)
    args.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args.add_argument("--label", required=True)
    args.add_argument("--revision", required=True)
    args.add_argument("--check", action="store_true")
    options = args.parse_args()

    snapshot = measure(
        options.source.resolve(),
        options.grammar.resolve(),
        options.label,
        options.revision,
    )
    snapshots_dir = options.snapshots.resolve()
    snapshot_path = snapshots_dir / f"{options.label}.json"
    encoded = json.dumps(snapshot, indent=2, sort_keys=True) + "\n"

    existing = load_snapshots(snapshots_dir) if snapshots_dir.is_dir() else []
    others = [item for item in existing if item["label"] != options.label]
    document = report_of(others + [snapshot])
    report_path = options.report.resolve()

    if options.check:
        stale = (
            not snapshot_path.is_file()
            or snapshot_path.read_text() != encoded
            or not report_path.is_file()
            or report_path.read_text() != document
        )
        if stale:
            print("stale Zen source health snapshot or report", file=sys.stderr)
            return 1
    else:
        snapshots_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(encoded)
        report_path.write_text(document)
    print(f"{snapshot['totals']['files']} files -> {snapshot_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
