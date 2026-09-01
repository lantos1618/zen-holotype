# Format strings

`DESIGN.md` defines the language. This note maps that design onto the current
implementation and names the one unresolved error-contract question.

## Language

| spelling | meaning |
|---|---|
| `{}` | consume the next positional argument |
| `{name}` | format the binding named at the call site; consumes no argument |
| `{{` / `}}` | one literal brace |
| `{` before any other byte, or a lone `}` | a literal byte |

There is no width, precision, positional index, or expression grammar inside a
hole. `{p.x}` and `{f()}` are errors; `{{p.x}` is the escaped literal form.
Named and positional holes may be mixed.

## Ownership

`src/std/text/text_fmt.zen` owns the reference scan. `fmt_next` returns literal
runs as slices and classifies positional holes, named holes, doubled braces,
and malformed named holes without allocating.

`src/gen/gen_c/gen_c_print.zen` owns call-site lowering because only the
compiler has the lexical scope needed to resolve `{name}`. A literal run becomes
a sink write and a hole becomes the selected value's writer. Formatting has no
runtime parser or format state.

Primitive writers target `Sink`, not `String`, so console formatting does not
need an allocator. `String` implements the same sink surface when the caller
wants an owned result. Raw byte APIs such as `String.add` never interpret
braces; changing `add("}}")` to `fmt("}}")` changes two bytes into one.

## Refusals

- A computed string is bytes, not a format program; only a leading string
  literal opens a format door.
- A missing or surplus positional argument is a compile error.
- An unresolved named hole is reported at the hole, not at the call.
- A type with no writer is rejected during lowering.

The reference parser and both sink doors are gated by
`tests/corpus/std/the_reference_format_parser_runs.zen`,
`both_format_doors_write_the_same_bytes.zen`, and the focused
`tests/must-fail/codegen/format_*` cases.

## Open error contract

An allocating format door returns `Res<String, AllocError>`, but a user
`Display` implementation writes through `Sink` and can return `WriteError`.
Today the lowering maps every failure on that door to `OutOfMemory`. That is
correct when the `String` cannot grow, but it mislabels an `IoError` invented by
user writer code.

The language still needs one decision: widen the allocating door to
`WriteError`, or treat a non-allocation failure from a writer targeting a
`String` as a program error. Do not spread the current conversion into new
formatting doors before that contract is settled.
