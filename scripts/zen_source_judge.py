#!/usr/bin/env python3
"""Run the independent Gemini 3.7 Flash source-health review for one round."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
HEALTH = ROOT / "docs" / "SOURCE_HEALTH.md"
INVENTORY = ROOT / "docs" / "ZEN_SIGNATURES.md"
STYLE = ROOT / "docs" / "STYLE.md"
AUDIT = ROOT / "docs" / "SOURCE_OWNERSHIP_AUDIT.md"
PROMPT = ROOT / "docs" / "SOURCE_HEALTH_JUDGE.md"
SNAPSHOTS = ROOT / "docs" / "source_health"
PACKS = ROOT / "build" / "source_health"
MODEL = "gemini-3.7-flash"


def validate(review: str) -> None:
    missing = [
        number
        for number in range(1, 6)
        if re.search(rf"(?m)^#{{1,4}}\s+{number}\.\s+", review) is None
    ]
    if missing:
        joined = ", ".join(map(str, missing))
        raise SystemExit(f"Gemini review is incomplete; missing sections: {joined}")
    if len(review.split()) > 1800:
        raise SystemExit("Gemini review exceeds the 1,800-word contract")


def previous_review(label: str) -> Path | None:
    reviews = sorted(SNAPSHOTS.glob(f"*-{MODEL}.md"))
    current = SNAPSHOTS / f"{label}-{MODEL}.md"
    earlier = [path for path in reviews if path != current]
    return earlier[-1] if earlier else None


def main() -> int:
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--label", required=True)
    args.add_argument("--gemini", default="gemini")
    options = args.parse_args()

    contexts = [HEALTH, STYLE, AUDIT]
    body_pack = PACKS / f"{options.label}-context.md"
    if body_pack.is_file():
        contexts.append(body_pack)
    else:
        contexts.append(INVENTORY)
    previous = previous_review(options.label)
    if previous is not None:
        contexts.append(previous)
    missing = [path for path in [PROMPT, *contexts] if not path.is_file()]
    if missing:
        raise SystemExit("missing review input: " + ", ".join(map(str, missing)))

    command = [
        options.gemini,
        "-m",
        MODEL,
        "-s",
        "You are an independent source-architecture judge. Follow the supplied "
        "review schema exactly, ground every finding in the supplied code, and "
        "stay under 1800 words.",
        "-t",
        "0.2",
        "--max",
        "8000",
        "-f",
        str(PROMPT),
    ]
    for context in contexts:
        command.extend(["-c", str(context)])
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or f"Gemini exited {result.returncode}")
    review = result.stdout.strip()
    if not review:
        raise SystemExit("Gemini returned an empty review")
    validate(review)

    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    output = SNAPSHOTS / f"{options.label}-{MODEL}.md"
    output.write_text(
        f"# Gemini 3.7 Flash review — {options.label}\n\n"
        f"Model: `{MODEL}`\n\n{review}\n"
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
