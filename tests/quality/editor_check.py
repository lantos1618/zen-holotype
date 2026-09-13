#!/usr/bin/env python3
"""Compile the editor and require executed lifecycle tests, including a nonempty suite."""

import argparse
from pathlib import Path
import re
import subprocess
import sys


def check(project: Path) -> int:
    required = project / "test/source-roots.test.cjs"
    if not required.is_file():
        print(f"editorcheck: missing required lifecycle suite: {required}", file=sys.stderr)
        return 1
    compiled = subprocess.run(["npm", "run", "compile"], cwd=project)
    if compiled.returncode:
        return compiled.returncode
    suites = sorted((project / "test").glob("*.test.cjs"))
    for suite in suites:
        result = subprocess.run(
            ["node", "--test", "--test-reporter=tap", str(suite)],
            cwd=project, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        print(result.stdout, end="", flush=True)
        if result.returncode:
            return result.returncode
        # Node reports an empty test file as one successful synthetic test named
        # after the file. That successful process is not an executed regression.
        passed = re.findall(r"^ok \d+ - (.+)$", result.stdout, re.MULTILINE)
        executed = [name for name in passed
                    if name not in {str(suite), suite.name, str(suite.relative_to(project))}
                    and not re.search(r" # (?:SKIP|TODO)\b", name)]
        if not executed:
            print(f"editorcheck: no executed tests in {suite}", file=sys.stderr)
            return 1
    print(f"editorcheck: {len(suites)} nonempty editor suite(s) passed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path,
                        default=Path(__file__).resolve().parents[2] / "editors/vscode")
    args = parser.parse_args()
    return check(args.project.resolve())


if __name__ == "__main__":
    sys.exit(main())
