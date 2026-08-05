# tests/corpus/codegen

The bug classes from `docs/TESTING.md` § Codegen, one program per class. Gate
arrives at stage 0.4 (`docs/PLAN.md`): each program is compiled, run, and its
stdout and exit code compared.

## Format

```
<name>.zen        the program
<name>.expected   exact stdout, byte for byte
<name>.exit       expected exit code; ABSENT means 0
```

A `.zen` file is a test **iff** a sibling `.expected` with the same basename
exists. That rule is what lets a multi-module test carry extra `.zen` files
that are not themselves entry points.

**Multi-module tests are a directory.** `mangle_module_collision/` holds
`mangle_module_collision.zen` (the entry, per `DESIGN.md`'s
`<folder>/<folder>.zen` rule) plus the modules it imports. **The test's own
directory is the source root**, so `alpha/alpha.zen` is imported as `alpha`.
That is a convention this corpus picks because `DESIGN.md` does not say what
the source root of a compilation is — see AMBIGUITIES below.

Every program here exits 0, so no `.exit` files. Non-zero exits are the traps
corpus (`tests/corpus/traps/`), which is a different area and a different
owner. **Nothing in this directory tests arithmetic traps.**

## How a codegen bug shows up here

Two different failure shapes, both red, and it is worth knowing which is which:

- **The C compiler rejects the output.** A local named `register`, a struct
  member named `errno`, an empty `struct {}`. The corpus runner must treat a
  failed C compile as a test failure with the C diagnostic attached, not as
  infrastructure noise.
- **The program runs and prints the wrong number.** Two Zen names mangled to
  one C name where C tolerated it, a `u64` literal truncated to `long`, a
  struct returned through the wrong ABI slot.

The keyword files sum distinct values precisely so the second shape is
detectable: if two names collapse, the sum moves.

## The files

| file | class |
|---|---|
| `c_keywords_c89.zen` | the 32 C89 keywords as ordinary Zen bindings |
| `c_keywords_c99_c11.zen` | the 12 C99/C11 additions |
| `c_keywords_c23.zen` | the C23 additions |
| `c_reserved_identifiers.zen` | `_Foo`/`__foo` reserved forms, vendor keywords, and the names `gen_c` itself emits |
| `c_libc_names.zen` | libc macros as struct fields, libc functions as bindings |
| `c_keywords_declaration_positions.zen` | keywords as type / field / method / param / type-param / module-level names |
| `mangle_generic_instantiation.zen` | a user name equal to a mangled instantiation name |
| `mangle_module_collision/` | two modules whose paths+names mangle to one C symbol |
| `forward_types.zen` | mutually recursive structs and enums; use-before-declare by value |
| `forward_functions.zen` | mutually recursive functions, methods, and a recursive generic |
| `struct_return_zero_field.zen` | a zero-field struct (illegal in ISO C) |
| `struct_return_large.zen` | 16/17/64-byte and mixed INTEGER+SSE returns |
| `struct_return_behavior.zen` | a struct crossing an actor message boundary (stage 5) |
| `literal_boundaries_signed.zen` | signed literals at the exact type boundary |
| `literal_boundaries_unsigned.zen` | `u64` literals that do not fit a C `long` |
| `nesting_expr.zen` | 256 nested parenthesised additions |
| `nesting_calls.zen` | 128 nested calls |
| `nesting_match.zen` | 32 nested `.match` expressions |
| `nesting_blocks.zen` | 160 nested blocks |

C11 §5.2.4.1 only requires a conforming C compiler to handle 63 levels of
nested parenthesised expressions and 127 levels of nested blocks. The four
nesting tests are all past those minimums on purpose: the correct fix is for
`gen_c` to flatten into temporaries, not to trust the C compiler's slack.

## The signed-overflow constraint

`DESIGN.md` § The failure model: signed overflow is UB in C, so a trap check
happens **before** the operation or through `__builtin_*_overflow`. Nothing in
this directory assumes post-hoc checking, and nothing here relies on a signed
overflow happening at all — every sum is small, every boundary value is
printed rather than incremented. `c_reserved_identifiers.zen` declares a Zen
binding literally named `__builtin_add_overflow`, because that is the name
`gen_c` will be emitting.

## AMBIGUITIES these tests are exposed to

Recorded here rather than guessed silently; the full list is in the agent
report that accompanied this directory.

1. **Name mangling is entirely unspecified.** `DESIGN.md` says two modules may
   define the same top-level name and never says what C symbol either becomes.
2. **The source root of a compilation.** Assumed to be the test's own
   directory for multi-module tests.
3. **`i32.MIN` / `u64.MAX`** are used by `TESTING.md` but never defined in
   `DESIGN.md`. These tests use them for the negative extremes rather than
   writing `-2147483648`, which `TESTING.md` flags as an open lexer question.
4. **The integer type family.** `DESIGN.md` names `u8`, `i32`, `u64`, `usize`,
   `f64`. `i8`/`i16`/`i64`/`u16`/`u32` are assumed to exist.
5. **`true` and `false`** are C23 keywords that must be mangled but cannot be
   written as Zen identifiers — they are Zen's bool literals. They are listed
   in `c_keywords_c23.zen`'s header comment and tested nowhere.
6. **`bool`** is tested as a shadowing binding; whether a local may shadow a
   prelude type is unspecified.
