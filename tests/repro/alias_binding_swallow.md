# Fix: single-`=` top-level binding silently swallowed the next decl (+ its `*` export)

Task #27 (M4 actor work) reported: a bare module-alias import `x = std.mod` mishandled —
breaks resolution of `x.thing` and corrupts the NEXT declaration's `*` export visibility.

## Finding

The exact form `x = std.mod` (ident/path RHS) is classified correctly and WORKS on
origin/main (check/run/fmt/cross-module visibility all pass). It was fixed earlier by
#394/#395 (UFCS through module aliases + enforce `*` visibility).

The REAL, still-live bug with the reported symptoms: a top-level single-`=` binding whose
RHS is NOT an ident-led module path (`k = 5`, `x = 3 + 4`) is classified by neither
`decl_is_module_alias` (needs an ident RHS) nor `decl_is_global` (needs `:=`), so it fell
through parse.zen `fill_decl` to the catch-all `fill_func`, which mis-parsed `= <expr>` and
SILENTLY consumed the following declaration — dropping its name and its `*` export marker.
`zenc check` then reported "ok" on a corrupted program (silent miscompile).

## The flip

    k = 5
    main* = () i32 { 0 }

- BEFORE: `zenc fmt` -> `k = () i32 { 0 }` (main swallowed); `zenc check` -> **"ok"** (silent).
- AFTER:  `zenc check` -> clean `error[bad-binding]` caretting the RHS, hint "use `:=` for a
  value global"; `main` is no longer swallowed.

## Fix

parse.zen: a new `decl_is_bad_binding` predicate (single `=`, RHS not `(` = not a function,
and — since the alias path is peeled first — not an ident = not a module alias) routes such a
decl to `fill_bad_binding`, which flags a `bad-binding` parse error and parses the RHS purely
to resume at the NEXT declaration (no swallow). The sentinel machinery (parse_type.zen
`perr_set_bad_at` + a `__bad_binding` sentinel name) surfaces it as the new `KBADBIND`
diagnostic (check_validate.zen). The working ident-RHS alias path is untouched.

## Regression coverage

tests/harness_verdict.zen `verdict-kind` suite: `k = 5` and `x = 3 + 4` reject with
`error[bad-binding]`; `m = std.math` alias, `k := 5` global, and `f = () i32 {…}` function
all still accept.
