#!/usr/bin/env python3
"""The VS Code extension's contributions still resolve.

Every failure this catches is a SILENT one. VS Code does not report a
`grammars` entry whose `path` is missing, nor one whose `scopeName`
disagrees with the grammar file's own — it simply contributes nothing,
and the language falls back to no tokenization at all. That fallback is
what put `(` inside a string into bracket matching:

    out.add_bytes("(zg_fs_kind(").try();

read as three real open brackets, because with no grammar every byte is
plain text. Colour survived (the server sends semanticTokens), so the
break was invisible to anyone reading the file rather than editing it.

Not a colour check. The grammar names comments, strings and character
literals and nothing else, on purpose — `editors/README.md` says why.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VSCODE = ROOT / "editors" / "vscode"

# The scopes bracket matching must be excluded from. A grammar that stops
# naming one of these is the bug this script exists for.
REQUIRED_SCOPES = (
    "comment.line.double-slash.zen",
    "comment.block.zen",
    "string.quoted.double.zen",
    "string.quoted.single.zen",
)


def scopes_in(node) -> set[str]:
    """Every `name` a grammar's rules carry, however deeply nested."""
    out: set[str] = set()
    if isinstance(node, dict):
        name = node.get("name")
        if isinstance(name, str):
            out.add(name)
        for value in node.values():
            out |= scopes_in(value)
    elif isinstance(node, list):
        for value in node:
            out |= scopes_in(value)
    return out


def main() -> int:
    bad: list[str] = []

    pkg_path = VSCODE / "package.json"
    if not pkg_path.is_file():
        print(f"editors: {pkg_path} is missing", file=sys.stderr)
        return 2
    pkg = json.loads(pkg_path.read_text())

    contributes = pkg.get("contributes", {})
    languages = {entry.get("id") for entry in contributes.get("languages", [])}
    grammars = contributes.get("grammars", [])

    if not grammars:
        bad.append(
            "contributes.grammars is empty — with no grammar VS Code has no "
            "tokenization for .zen, and every `(` inside a string matches as "
            "a real bracket"
        )

    for entry in grammars:
        lang, scope, rel = (entry.get("language"), entry.get("scopeName"),
                            entry.get("path"))
        if lang not in languages:
            bad.append(f"grammar names language {lang!r}, which "
                       f"contributes.languages does not declare")
        if not rel:
            bad.append(f"grammar for {lang!r} has no path")
            continue
        path = (VSCODE / rel.lstrip("./")).resolve()
        if not path.is_file():
            bad.append(f"grammar path {rel} does not exist "
                       f"(VS Code ignores this silently)")
            continue
        grammar = json.loads(path.read_text())
        if grammar.get("scopeName") != scope:
            bad.append(f"{rel} declares scopeName "
                       f"{grammar.get('scopeName')!r}, package.json says "
                       f"{scope!r} — they must match or nothing is applied")
        found = scopes_in(grammar)
        for want in REQUIRED_SCOPES:
            if want not in found:
                bad.append(f"{rel} names no {want} rule — brackets inside "
                           f"that construct would match as real brackets")

    # The language configuration is what declares brackets in the first place.
    cfg_rel = next((e.get("configuration") for e in
                    contributes.get("languages", []) if e.get("configuration")),
                   None)
    if cfg_rel:
        cfg = VSCODE / cfg_rel.lstrip("./")
        if not cfg.is_file():
            bad.append(f"language configuration {cfg_rel} does not exist")
        else:
            brackets = json.loads(cfg.read_text()).get("brackets", [])
            if not brackets:
                bad.append(f"{cfg_rel} declares no brackets")

    for line in bad:
        print(f"editors: {line}", file=sys.stderr)
    if bad:
        print(f"\neditors: {len(bad)} broken contribution(s).", file=sys.stderr)
        return 1

    n = sum(len(scopes_in(json.loads((VSCODE / e['path'].lstrip('./')).read_text())))
            for e in grammars)
    print(f"editors: {len(grammars)} grammar(s), {n} scope(s), "
          f"{len(REQUIRED_SCOPES)}/{len(REQUIRED_SCOPES)} bracket-excluding "
          f"scopes present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
