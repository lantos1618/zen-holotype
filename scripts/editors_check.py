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

Nor is the grammar the whole bracket story, which is why this script
grew a second half. A scope only ever tells VS Code where a bracket is
NOT; `language-configuration.json` is what says a bracket exists at all,
and its `autoClosingPairs` are the one part of that file which is token
aware — and opt-in. `StandardAutoClosingPairConditional` starts every
pair with `_inString = true` and only `notIn` turns it off, so a pair
written without one auto-inserts its partner inside a string literal,
with the grammar loaded and working. Three of Zen's five pairs were
written that way, in the same array as two that were not.

And the third silent failure is that none of it ships. `vsce` builds the
.vsix against `.vscodeignore`; a pattern that swallows `syntaxes/` costs
nothing at package time and produces exactly the untokenized editor this
file's first paragraph is about. So the contributed paths are checked
against the ignore patterns too.

STILL NOT A TOKENIZATION CHECK, WHICH IS THE HALF THIS CANNOT DO. Running
the grammar means an Oniguruma engine — `vscode-textmate` over node —
and `editors/vscode/node_modules/` is untracked with no install step in
`make test`, so such a gate would either make a Python-only checkout
fail or skip itself when the dependency is absent, and a gate that
skips is a gate that is green for the wrong reason. What holds the line
instead is `tests/corpus/lex/string_containing_bracket_markers`, which
pins the compiler's OWN answer for the same bytes: a bracket inside a
literal is not a bracket. That is the answer the grammar has to agree
with, and the file to check by hand when it is suspected of drifting.
"""

from __future__ import annotations

import json
import re
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

# WHAT MAKES A SCOPE EXCLUDE A BRACKET, and it is not the scope being listed
# above. VS Code reduces every TextMate scope to a `StandardTokenType` with
# this regex (vscode-textmate, `BasicScopeAttributesProvider`), and a bracket
# counts wherever the answer is `Other` -- in the bracket-pair AST
# (`bracketPairsTree/tokenizer.ts`) and in the older matcher
# (`bracketPairsImpl.ts`, `ignoreBracketsInToken`) alike. So a scope named
# `literal.quoted.zen` is a perfectly valid TextMate scope that reads as
# ordinary text, and renaming one of the four above to it would put every
# bracket inside a Zen string back into matching -- silently, and with the
# list above still satisfied if the two were edited together.
STANDARD_TOKEN_TYPE = re.compile(r"\b(comment|string|regex)\b")

# The contexts an auto-closing pair must decline to fire in. These are the
# two `notIn` values that mean anything to VS Code for this language --
# `regex` is the third, and Zen has no regex literals for it to name.
NOT_IN = {"string", "comment"}


def pairs_of(entries) -> set[tuple[str, str]]:
    """`[open, close]` and `{open, close}` are the same pair, two spellings.

    `brackets` and `surroundingPairs` take the array form, `autoClosingPairs`
    the object form, and VS Code accepts either everywhere -- so the three
    lists can only be compared after both are read.
    """
    out: set[tuple[str, str]] = set()
    for entry in entries:
        if isinstance(entry, dict):
            out.add((entry.get("open"), entry.get("close")))
        elif isinstance(entry, list) and len(entry) == 2:
            out.add((entry[0], entry[1]))
    return out


def glob_re(pattern: str) -> re.Pattern[str]:
    """`.vscodeignore`'s globs, narrowed to the ones minimatch and vsce agree on."""
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append(r"(?:[^/]*/)*")
            i += 3
        elif pattern.startswith("**", i):
            out.append(r".*")
            i += 2
        elif pattern[i] == "*":
            out.append(r"[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append(r"[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def ignored(patterns: list[str], rel: str) -> bool:
    """Last pattern to match wins, and a leading `!` re-includes -- vsce's rule."""
    verdict = False
    for pattern in patterns:
        negated = pattern.startswith("!")
        if glob_re(pattern.lstrip("!")).match(rel):
            verdict = not negated
    return verdict


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
            elif not STANDARD_TOKEN_TYPE.search(want):
                bad.append(f"{want} reads as ordinary text to VS Code — a "
                           f"scope excludes brackets only when its name "
                           f"carries `comment`, `string` or `regex` as a word")

    # The language configuration is what declares brackets in the first place.
    cfg_rel = next((e.get("configuration") for e in
                    contributes.get("languages", []) if e.get("configuration")),
                   None)
    closing = brackets = surrounding = set()
    if cfg_rel:
        cfg = VSCODE / cfg_rel.lstrip("./")
        if not cfg.is_file():
            bad.append(f"language configuration {cfg_rel} does not exist")
        else:
            conf = json.loads(cfg.read_text())
            brackets = pairs_of(conf.get("brackets", []))
            surrounding = pairs_of(conf.get("surroundingPairs", []))
            closing = pairs_of(conf.get("autoClosingPairs", []))
            if not brackets:
                bad.append(f"{cfg_rel} declares no brackets")

            # Auto-closing is the one bracket subsystem that is token aware by
            # OPT-IN. Everything else -- the bracket-pair AST, the guides, the
            # older matcher -- reads `StandardTokenType` and needs no help; a
            # pair with no `notIn` types a `)` into the middle of a string.
            for pair in conf.get("autoClosingPairs", []):
                if not isinstance(pair, dict):
                    bad.append(f"{cfg_rel}: autoClosingPairs {pair!r} is the "
                               f"array form, which cannot carry a `notIn`")
                    continue
                missing = NOT_IN - set(pair.get("notIn") or ())
                if missing:
                    bad.append(f"{cfg_rel}: the {pair.get('open')!r} pair is "
                               f"not held out of {', '.join(sorted(missing))} "
                               f"— it auto-closes inside one")

            # And the three lists must be the same three pairs plus the
            # quotes. A bracket in `brackets` but not in `autoClosingPairs`
            # has no `notIn` to be missing, so the check above would pass it.
            for pair in sorted(brackets - closing):
                bad.append(f"{cfg_rel}: {pair[0]!r} is a bracket but not an "
                           f"auto-closing pair, so nothing guards it")
            if closing != surrounding:
                bad.append(f"{cfg_rel}: autoClosingPairs and surroundingPairs "
                           f"disagree on "
                           f"{sorted(p[0] for p in closing ^ surrounding)}")

    # None of the above ships unless `.vscodeignore` lets it. A grammar left
    # out of the .vsix is the original bug, packaged.
    ignore = VSCODE / ".vscodeignore"
    patterns = [ln.strip() for ln in ignore.read_text().splitlines()
                if ln.strip() and not ln.startswith("#")] if ignore.is_file() else []
    shipped = [e.get("path") for e in grammars] + [cfg_rel, pkg.get("main")]
    for rel in filter(None, shipped):
        rel = rel.lstrip("./")
        if ignored(patterns, rel):
            bad.append(f".vscodeignore excludes {rel}, which package.json "
                       f"contributes — it would be absent from the .vsix")

    for line in bad:
        print(f"editors: {line}", file=sys.stderr)
    if bad:
        print(f"\neditors: {len(bad)} broken contribution(s).", file=sys.stderr)
        return 1

    n = sum(len(scopes_in(json.loads((VSCODE / e['path'].lstrip('./')).read_text())))
            for e in grammars)
    print(f"editors: {len(grammars)} grammar(s), {n} scope(s), "
          f"{len(REQUIRED_SCOPES)}/{len(REQUIRED_SCOPES)} bracket-excluding "
          f"scopes present; {len(closing)} auto-closing pair(s), all held out "
          f"of strings and comments; {len(list(filter(None, shipped)))} "
          f"contributed path(s) survive .vscodeignore")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
