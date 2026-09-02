# `@meta` and comptime

`@meta` reads and eventually builds the compiler's existing `std.ast` values.
It does not introduce a parallel reflection tree or macro language.

## Current surface

The lexer, parser, AST, formatter, and semantic-token layer all understand the
typed and value forms. Sema currently supports:

```zen
@meta(name: T).name
@meta(name: T).fields().len
@meta(name: T).fields().loop((h, field) {
    out.fmt(" {}: {},", field.name, value.at(field));
})

value.variant_name()
```

Type-name reads preserve the written nominal name, including aliases. A field
walk checks its body once per declared field. `field.name` is compile-time text;
`value.at(field)` is a residual expression whose concrete member changes per
pass. `variant_name()` is available on nominal enum values and returns the
active variant's name exactly as declared as borrowed `str`; payload and generic
enum variants use the same declaration name. Lowercase protocol spelling can
therefore live directly in the enum declaration without a conversion table or
case-folding allocation.

Unsupported `@meta` forms meet one `MetaNotImplemented` diagnostic at the
`@meta` token. Current refusals include standalone `@meta` value reflection,
nested field walks, field binders used as ordinary values, walks over unresolved
type parameters, and projections onto a receiver without the selected field.

## Implementation ownership

`src/sema/sema_meta.zen` owns recognition, type-name/field-count folds,
per-field checking, diagnostics, and fold memos. Written type keys preserve
distinct aliases; instantiation-sensitive memo identity remains a milestone.

`src/gen/gen_c/gen_c_meta.zen` deterministically unrolls a checked field walk
and rewrites each projection using sema's facts. The backend does not invent a
second checker or reflection representation. Formatter input remains the
parser's original AST.

`src/sema/sema_variant_name.zen` recognizes and records the enum-only
`variant_name()` intrinsic. `src/gen/gen_c/gen_c_variant_name.zen` evaluates its
receiver once and selects static string literals using the enum's private dense
tag. It adds no runtime name table and performs no allocation.

## Seed order

An `@meta` form used inside `src/` must already be expandable by the compiler
built from `seed/zen.c`. Land the implementation, regenerate the seed, then
land the compiler use. Reversing that order makes a clean build unable to
compile its own source.

## Remaining milestones

- A step-budgeted evaluator for ordinary comptime expressions. Declining to
  evaluate is not a valid answer, so exhaustion must be a named diagnostic.
- Field-walk control flow beyond the current unit-valued form, including
  `h.break(value)` where a real consumer requires it.
- Nested execution, with a budget and memo identity that remain sound across
  generic instantiations.
- BUILD: functions returning new AST values, memoized by function and
  arguments, followed by type-checking of the generated residue.

No milestone may add file I/O at comptime, a second evaluator in a backend, or
a new `@` namespace entry.

## Verification

- Unsupported forms and budgets belong in `tests/must-fail/` with exact
  diagnostic counts.
- A generated consumer and its hand-written Zen twin share one expected
  result.
- Field-walk fixtures use distinct, non-default values and are
  mutation-checked; silently skipping one field would otherwise look valid.

The live examples and refusals are under `tests/corpus/meta/` and
`tests/must-fail/sema/meta_*`.
