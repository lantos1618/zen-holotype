# Repro: single-`=` top-level binding silently swallows the next decl (+ its `*` export)

Task #27 (M4 actor work) reported: a bare module-alias import `x = std.mod` mishandled —
breaks resolution of `x.thing` and corrupts the NEXT declaration's `*` export visibility.

## Finding

The exact form `x = std.mod` (ident/path RHS) is classified correctly and WORKS on
current origin/main (check/run/fmt/cross-module visibility all pass — see below). It was
almost certainly fixed by #394/#395 (UFCS through module aliases + enforce `*` visibility).

The REAL, still-live bug with the reported symptoms: a top-level single-`=` binding whose
RHS is NOT an ident-led module path (`k = 5`, `x = 3 + 4`, `CONST* = 5`) is classified by
neither `decl_is_module_alias` (needs an ident RHS) nor `decl_is_global` (needs `:=`), so it
falls through parse.zen `fill_decl` to the catch-all `fill_func`, which mis-parses `= <expr>`
and SILENTLY consumes the following declaration — dropping its name and its `*` export marker.
`zenc check` then reports "ok" on a corrupted program (silent miscompile).

## Broken (origin/main)

    $ printf 'k = 5\nmain* = () i32 { 0 }\n' | ...
    # zenc fmt --stdout  =>  `k = () i32 { 0 }`   (main swallowed; k stole main's body)
    # zenc check         =>  "ok"                 (SILENT: main is gone)

    $ printf 'x = 3 + 4\nwanted* = () i32 { 7 }\nmain* = () i32 { wanted() }\n' | ...
    # zenc fmt --stdout  =>  `x = () i32 { 7 }` then main  (wanted + its `*` swallowed)
    # zenc check         =>  error: undefined name `wanted`  (its decl was eaten)

## Works (control — the exact form the task named)

    $ printf 'm = std.math\nwanted* = (v: i64) i64 { m.abs(v) }\nmain* = () i32 { to_i32(wanted(0 - 5)) }\n' | ...
    # check ok; run => 5; cross-module `{ wanted } = a` imports fine; `{ priv } = a` correctly rejected.

## Fix direction

Single-`=` top-level bindings are ONLY valid as module aliases (ident/path RHS); value
globals must use `:=`. When a `name = <non-alias RHS>` decl is seen, emit a clean
`error[...]` at that line instead of silently falling to `fill_func`. No silent corruption.
