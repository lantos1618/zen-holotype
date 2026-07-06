# Repro: leading-`|` inline enum silently swallows the next decl (+ its `*` export)

Task #34 — a silent-miscompile SIBLING of #411 (`decl_is_bad_binding`), but through the
SEPARATE `fill_enum` / `fill_variant` machinery in parse.zen, which #411's guard does not cover.

## The swallow

    Status*: | Ok | Err
    main* = () i32 { 0 }

- BEFORE (origin/main): `zenc check` -> **"ok"** (silent miscompile); `zenc fmt --stdout` ->

        Status*: |
        Ok = () i32 { 0 }

  `main` is GONE — no `zen_main` in the emitted C. Only `Status` (a bogus 1-variant enum whose
  single variant is literally named `|`) survives; everything after is mis-parsed and swallowed.

The same defect fires for the newline-then-leading-bar form:

    Color*:
     | Red
     | Green
     | Blue
    main* = () i32 { 0 }

-> `Color*: |` + `Red = () i32 { 0 }` (main swallowed).

## What is NOT affected (control cases, all correct on origin/main)

- `Status*: Ok | Err` + `main*` — main SURVIVES, fmt round-trips. (No leading bar.)
- Multi-line CONTINUATION enums parse + fold correctly and MUST keep working:

        Color*: Red
         | Green
         | Blue

  -> `Color*: Red | Green | Blue` (the legitimate case — do not break).
- `Status*: Ok | Err |` (TRAILING bar) already errors cleanly (`error[parse]`), no swallow.

## Root cause (parse.zen)

`fill_variants` / `fill_variant` (parse.zen ~282-313) read a variant NAME from whatever token
sits at the current position via `a.lexeme(src, nt.tok)` WITHOUT checking it is an identifier.
The variant list is terminated only by "the token after a parsed variant is not `|`" — which is
the CORRECT decl boundary (a new top-level decl never begins with `|`). The bug is purely that a
leading / stray `|` (the first token in the variant list) is itself consumed as a bogus variant
NAME. `Status*: | Ok | Err` reads variant `"|"`, then sees `Ok` (not another `|`) and STOPS,
leaving `Ok | Err\nmain* = …` to be mis-parsed as a following function that eats `main`.

## Boundary rule (continuation vs. new decl)

Not ambiguous: the variant list continues iff the token following a variant is `|`; it ends
otherwise. A new top-level decl never starts with `|`, so the terminator already stops at the
right place. The ONLY missing invariant is: a variant NAME must be an identifier.
