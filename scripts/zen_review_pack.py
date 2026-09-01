#!/usr/bin/env python3
"""Build a bounded source-body pack for one external review round."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS = ROOT / "docs" / "source_health"


def source_path(relative: str) -> Path:
    return ROOT / relative


def line_count(path: Path) -> int:
    data = path.read_bytes()
    return data.count(b"\n") + (0 if data.endswith(b"\n") else 1)


def area_of(relative: str) -> str:
    parts = Path(relative).parts
    return parts[1] if len(parts) > 2 else "src"


def sample_key(label: str, relative: str) -> str:
    return hashlib.sha256(f"{label}:{relative}".encode()).hexdigest()


def choose(snapshot: dict, label: str, max_lines: int, ranked_files: int) -> list:
    selected: list[tuple[str, str, int]] = []
    used: set[str] = set()
    total = 0

    for relative in snapshot["ranking"]:
        if len(selected) >= ranked_files:
            break
        lines = line_count(source_path(relative))
        if total + lines > max_lines:
            continue
        selected.append((relative, "ranked", lines))
        used.add(relative)
        total += lines

    areas = sorted({area_of(path) for path in snapshot["files"]})
    for area in areas:
        candidates = [
            path
            for path in snapshot["files"]
            if area_of(path) == area and path not in used
        ]
        candidates.sort(key=lambda path: sample_key(label, path))
        for relative in candidates:
            lines = line_count(source_path(relative))
            if total + lines > max_lines:
                continue
            selected.append((relative, f"spot-check:{area}", lines))
            used.add(relative)
            total += lines
            break
    return selected


def render(label: str, revision: str, selected: list[tuple[str, str, int]]) -> str:
    out = [
        f"# Source body review pack — {label}",
        "",
        f"Revision: `{revision}`.",
        "",
        "This bounded pack contains the highest mechanical review priorities",
        "plus one deterministic spot-check from each top-level source area.",
        "Inspect bodies and comments rather than inferring implementation from",
        "signatures. Selection is evidence for review, not authorization to edit.",
        "",
        "| File | Selection | Lines |",
        "| --- | --- | ---: |",
    ]
    out.extend(f"| `{path}` | {reason} | {lines} |" for path, reason, lines in selected)
    for relative, reason, lines in selected:
        out.extend(
            [
                "",
                f"## `{relative}`",
                "",
                f"Selection: {reason}; {lines} lines.",
                "",
                "```zen",
                source_path(relative).read_text().rstrip(),
                "```",
            ]
        )
    return "\n".join(out) + "\n"


def main() -> int:
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--label", required=True)
    args.add_argument("--max-lines", type=int, default=15000)
    args.add_argument("--ranked-files", type=int, default=10)
    args.add_argument("--check", action="store_true")
    options = args.parse_args()

    snapshot_path = SNAPSHOTS / f"{options.label}.json"
    if not snapshot_path.is_file():
        raise SystemExit(f"missing {snapshot_path}")
    snapshot = json.loads(snapshot_path.read_text())
    selected = choose(
        snapshot,
        options.label,
        options.max_lines,
        options.ranked_files,
    )
    document = render(options.label, snapshot["revision"], selected)
    output = SNAPSHOTS / f"{options.label}-context.md"
    if options.check:
        if not output.is_file() or output.read_text() != document:
            raise SystemExit(f"stale source review pack: {output}")
    else:
        output.write_text(document)
    print(
        f"{len(selected)} files, {sum(lines for _, _, lines in selected)} lines"
        f" -> {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
