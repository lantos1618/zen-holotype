# tests/corpus/constants -- LANE.md

Module-level constants, their types, and constants used in expressions.
Oracle: `./runzen.sh <dir>`; every `.expected` below was byte-verified
against it, then re-run through `tests/run.py` (7 passed, 0 failed).

## One line per test: what one-line compiler change breaks it

- constant_folds_in_its_own_module -- keying gen_c's const lookup by NAME
  alone (`defs_of(ctx.module, name)` -> a world-global map) makes get_total
  answer 103 instead of 23; so does resolving an imported function's body
  against the CALLER's module ctx instead of `plain_ctx(d.id.module)`.
- constant_in_expression_positions -- dropping any arm of `lower_const_value`
  except the plain-print path (e.g. inlining only into `println` holes, or
  reading a dead slot when the const is a call ARGUMENT) flips div/sum while
  every direct print stays true.
- construction_valued_constant_arrives_whole -- narrowing `is_pure_call`'s
  "callee NAMES A TYPE" licence to literals-only rejects this program with
  "a constant whose value is not a literal"; field-swapping the compound
  literal prints `home 14 3`.
- local_shadows_constant_and_leaves_it -- consulting module defs BEFORE the
  frame in the bare-name path (or letting an arm-local binding outlive its
  frame, cf. the match-binder bug) prints 1111/1111/7 instead of
  7/80/1111.
- negative_valued_constants_keep_their_sign -- emitting Unary(Neg) as the
  bare token `-9223372036854775807` without folding Binary(Sub)
  (-9223372036854775808 as one C constant has no signed type) fails at cc,
  not quietly; printing through a signed formatter with a sign bit kept
  shows `-0` for TINY.
- str_constant_is_the_same_bytes_at_every_use -- emitting the str constant
  once as a C object plus per-use reads (or interning the literal but not
  writing its bytes) makes use #2 print empty/stale bytes and len read
  short of 7.
- wide_constants_keep_their_width -- sizing the inlined value from the USE
  site's type instead of the declared one ("the constant's DECLARED type
  wins", gen_c_const.zen) truncates BIG/SEED to int-width zeros-and-noise;
  SEED / 2 then answers wrong while both small lines still print.

## COMPILER BUG FOUND (not encoded as expected output)

**A constant whose VALUE names another constant is refused by codegen.**

    A: i64 = 5
    B: i64 = A + 3        // sema accepts
    println("{}", B)      // codegen refuses

    main.zen:5:21: codegen does not lower this yet:
    `a constant whose value names a function or reads a frame`

Suspected cause, grounded in source I read: `is_pure_value`
(`src/gen/gen_c/gen_c_const.zen:169`) matches Literal/Unit/Unary/Binary/
Call/Access and falls to `_ => false`. There is NO `Name` arm, so inside
a Binary-valued constant the operand `Name(A)` answers false via
`is_pure_pair`. The gate's own comment justifies refusing names because
"a name is a local whose frame the use site is not in" -- true for
locals, but the question is asked under `dctx`, the DECLARING module's
context (`lower_const_value`, :154), where a bare module-constant name
resolves to another `ConstDef` that is exactly as inlinable as the outer
one. Sema already has the lookup this needs: `sema_trap.const_def`
(`sema_trap.zen`) resolves a bare name to a ConstDef, frame-first, and
the array-count rule folds through it (`PAIR: usize = 1 + 1` works
because its operands are Literals; `SIZE * 2` is refused there too --
but by design, named, and only in the COUNT position).

Minimal repros tried (all refused at codegen, all sema-clean):
- single module: `A = 5; B = A + 3` (B unused AND used)
- own-module use via function: `TAX = RATE + 3; get_tax* = () i64 { TAX }`
- cross-module import of B (refusal fires even in helper's own file)
- chain: `BASE = 6; SQUARED = BASE * BASE; DOUBLE = SQUARED + SQUARED`

Controls that PASS, isolating cause to Name-in-value:
- `NEG = -42`, `FLOOR = 0 - 9223372036854775807` (Unary/Binary over
  Literals only) inline correctly
- imported literal-valued constants work (`RATE = helper.helper`)
- imported function combining two constants in ITS OWN module works

Impact: DESIGN.md says a constant "folds wherever it is read" and the
count-folder comment explicitly contemplates `SIZE: usize = 8 * 8`;
any program building constants from named pieces -- scale factors,
derived limits, the classic `DAY = HOURS * 24` -- is unwritable. The
diagnostic also names the wrong reason (ISSUES.md already records the
gate/message drift at gen_c_const.zen:158/:170).

The planned `constant_chain_folds_hop_by_hop` test was built on this
shape, verified blocked, and thrown away rather than encoding the
refusal.

## Language facts learned while probing (for the next lane)

- Import bindings rename nothing: `X = mod.mod` requires X to BE an
  export of mod.mod; multi-name form is `A, B = mod.mod`; dotted use of
  an import binding (`H.RATE`) is not a thing.
- Two same-named imports compile; first binding wins (resolution-order
  territory, not probed further).
- `str.len` is a FIELD; usize has no `.to_i64()`; bool has no `.to_i64()`
  (use `.match({true => 1, false => 0})`).
- A function-typed local inside a body does not parse
  (`twice = (x: i64) i64 {..};` inside main: "expected expression");
  declare helpers at module level.
- Folder rename trap while probing: `other/other.zen` was renamed dir-wise
  to `misc/other.zen` and silently became "nothing is at that path" --
  the FILE name must match the folder for `<folder>/<folder>.zen`.

TESTS: 7
