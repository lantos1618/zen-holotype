# Zen language contract

This document describes syntax and behavior accepted by the shipping checked CLI. It is not a list
of aspirations. Compiler source and executable tests remain the final authority; implementation
status and proposed changes belong in [STATUS.md](STATUS.md).

## Source and declarations

A source file is byte-oriented UTF-8 text containing top-level imports and declarations. Identifiers
are currently ASCII-style names; string data can contain UTF-8 bytes. Line comments use `//`; block
comments use `/* ... */` and may nest.

```zen
{ println } = std.text.fmt        // destructuring import
fmt = std.text.fmt                // namespace bind

LIMIT* := 100                     // public value global
Point*: { x: i32, y: i32 }        // public type
Colour*: Red | Green | Blue       // public enum

add* = (a: i32, b: i32) i32 {    // public function
    a + b
}

native_read* = (fd: i32, p: RawPtr<u8>, n: i64) i64
```

`*` makes the declaration importable from another module. Private declarations remain available
inside their file and produce `error[private-name]` if imported.

`:=` defines a value global or local. A top-level `=` is reserved for a function or a module bind;
using it for an ordinary value produces `error[bad-binding]`.

A bodyless function declaration is an external signature. It contributes a callable signature to
checking and expects a target/link definition only if the program uses it. It is not yet a Zen
forward declaration paired with a later same-named body: duplicate top-level definitions are an
error, and the compiler does not perform whole-project definition completeness checking.

## Types

Built-in scalar types are:

- signed integers: `i8`, `i16`, `i32`, `i64`;
- unsigned integers: `u8`, `u16`, `u32`, `u64`;
- floating point: `f32`, `f64`;
- `bool` and `void`.

Integer literals are range-checked in a typed slot. Decimal, hexadecimal (`0x`), binary (`0b`),
octal (`0o`), and `_` digit separators are supported. Float literals support decimal fractions and
scientific notation. There is no general implicit signed/unsigned mixing; unsafe comparisons such
as negative signed values against wide unsigned values are rejected.

Other type forms:

```zen
[T]                         // pointer + length slice
Ptr<T>                      // non-null read-only pointer
MutPtr<T>                   // non-null writable pointer
RawPtr<T>                   // nullable/raw FFI pointer
(i32, string_view) bool     // function type
Box<T>                      // generic instance
```

`MutPtr<T>` can be used where a read-only `Ptr<T>` is expected. A `Ptr<T>` cannot be used where
`MutPtr<T>` is expected. A nullable `RawPtr<T>` cannot satisfy a non-null slot; use
`assert_nonnull(raw)` to panic on null and obtain `MutPtr<T>`. `RawPtr<u8>` is the trusted raw byte
floor and has looser intrinsic rules. See [MEMORY_MODEL.md](MEMORY_MODEL.md).

### String provenance

Zen keeps three non-owning string provenances:

| Type | Meaning |
|---|---|
| `string_literal` | Immutable compiler/static literal storage. |
| `string_cstr` | NUL-terminated external or allocated storage. |
| `string_view` | Read-only string view used by ordinary APIs. |

The parser still accepts migration aliases `text`, `Cstr`, and `str` respectively. Formatting and
diagnostics use canonical names. `String` in `std.text.string` is a separate allocator-backed,
growable owned buffer. Slices and aggregates remain invariant; read-only trait lookup normalizes the
three non-owning provenances to the `string_view` receiver.

## Functions, values, and calls

```zen
mul = (a: i32, b: i32) i32 { a * b }
identity<T> = (x: T) T { x }
main = () i32 {
    n := mul(6, 7)
    n.to_i64()               // UFCS: to_i64(n)
    0
}
```

The last expression is the implicit return value. `return value` exits early. A return type may be
omitted where inference can determine it; public APIs should generally spell it out.

`receiver.method(args...)` is UFCS. The checker resolves inherent methods, trait methods, and
top-level functions by receiver type. A name bound in the local scope shadows a same-named top-level
function.

Function-typed parameters are supported. The current closure boundary is:

| Form | Status |
|---|---|
| Lambda passed directly to a generic/HOF call, including local captures | Supported by inlining. |
| Local binding of a callable lambda | Supported where it can be spliced/resolved. |
| Non-capturing lambda stored in a function-typed field or returned | Supported by top-level lift. |
| Returned lambda capturing enclosing function parameters | Supported as a by-value generated closure record. |
| Escaping lambda that captures an arbitrary local, including a capturing field value | Rejected with `error[lambda-value]`. |

Zen does not currently have tuple syntax. Use a named record when returning multiple values.

## Expressions and operators

Core expressions include literals, variables, calls, UFCS calls, struct/enum construction, field
access, indexing, slices, lambdas, blocks, and `.match`.

From low to high precedence, binary operators group as:

1. `||`
2. `&&`
3. comparisons: `== != < <= > >=`
4. `|`
5. `^`
6. `&`
7. `<< >>`
8. `+ -`
9. `* / %`

Bitwise operators therefore bind more tightly than comparisons. Parenthesize when mixing them.
`|` is both the current enum-variant separator in a type declaration and bitwise OR in a value
expression. Changing enums to comma separation is proposed but not shipped.

Assignments are statements:

```zen
x := 1
x: i64 := 1
x = x + 1
obj.field = value
items[index] = value
```

## Control flow

There is no ordinary `if`, `for`, or source-level `while` statement. An attempted `if (...)` is
rejected with a teaching diagnostic. Branch on the value:

```zen
abs = (n: i32) i32 {
    (n < 0).match ({
        true  => 0 - n,
        false => n,
    })
}
```

Enum and literal matches use the same form:

```zen
Opt<T>: Some(T) | None

unwrap_or = (o: Opt<i32>, fallback: i32) i32 {
    o.match ({
        .Some(v) => v,
        .None    => fallback,
    })
}
```

A value-producing match must be exhaustive. `_` is the catch-all. Duplicate variants, unknown
variants, incompatible arm values, and non-boolean guards are errors.

The current grammar permits an optional guard inside an arm:

```zen
n.match ({
    value if value > 10 => "large",
    _                    => "small",
})
```

This is the only public context in which the `if` token is currently accepted. Its inconsistency
with the no-`if` goal is tracked in [STATUS.md](STATUS.md); documentation must not pretend it is
already removed.

For a side effect that only runs on true, `std.core.bool.then` is a library helper:

```zen
{ then } = std.core.bool

ready.then(() {
    start()
})
```

It returns `void`; value decisions still use `.match`.

Public collection iteration uses `loop`:

```zen
items.loop((h, i, item) {
    (item == 0).match ({
        true  => h.break,
        false => consume(item),
    })
})
```

`@while` exists as a compiler/runtime substrate primitive and is restricted by boundary tests. It is
not the public iteration style.

## Records, enums, traits, and generics

Records are product types:

```zen
Point*: {
    x: i32,
    y: i32,
}

p := Point(x: 3, y: 4)
```

Enums are tagged sums. Variants can be empty, carry one value, or carry a named anonymous record
payload. Matches over enum values are exhaustiveness-checked.

A trait is a record of required method signatures; there are no `trait` or `impl` keywords:

```zen
Area*: {
    area: (Ptr<Self>) i32,
}
Circle*: {
    radius: i32,
}
Circle.impl(Area, {
    area = (c: Ptr<Circle>) i32 { 3 * c.radius * c.radius }
})
```

An implementation must provide every required method with a compatible signature after substituting
`Self`. Trait records may supply default method bodies. Generic bounds use `T: Trait`:

```zen
measure<T: Area> = (value: Ptr<T>) i32 { value.area() }
```

Generic records, enums, and functions are monomorphized for concrete uses. Explicit call-site type
arguments use `function<Type>(args)`. A type argument after UFCS, such as `value.id<i32>()`, is not
currently parsed; write `id<i32>(value)`.

## Modules and visibility

Destructuring imports bring selected public names into scope:

```zen
{ println, format } = std.text.fmt
{ helper } = util
```

Namespace binds qualify direct exports:

```zen
fmt = std.text.fmt
util = util

fmt.println(util.helper())
```

Resolution rules in checked CLI modes:

- `std.foo.bar` loads `zen/std/foo/bar.zen` relative to `ZEN_ROOT`/the compiler;
- `compiler.foo` loads `zen/compiler/foo.zen`;
- a bare local module such as `util` loads `util.zen` beside the entry source;
- local dotted paths are rejected with an explicit diagnostic;
- transitive imports, cycles, missing names, duplicate definitions, privacy, and namespace aliases
  are checked;
- the current CLI still emits through a deterministic flattened compatibility program, although the
  resolver also builds module tables and parsed-module structures internally.

There is no installed package registry, dependency solver, registered source-root table, or nested
local module path yet. A project manifest chooses the entry root; it does not make arbitrary
`src/some/package.zen` paths importable by package name.

Project directories use `zen.toml` or a higher-priority `build.zen`. The manifest contract is:

```toml
package = "name"              # metadata only today
kind = "executable"           # optional: executable or library
root = "src"                  # required
main = "main.zen"             # required
out = "program"               # optional
ccflags = "native.c"          # optional C linker/compiler input
link = "pthread"              # optional single -l library
```

`check` accepts a library entry without `main`. `build` and `run` reject `kind = "library"` because
the compiler does not yet emit a library archive.

## Results, optional values, and panic

Zen has no exceptions or language unwinding. Recoverable failure is a value:

```zen
Result<T, E>: Ok(T) | Err(E)
Opt<T>: Some(T) | None
```

`.match` handles either enum. On `Result`, `.or_return()` unwraps `.Ok` or returns the same `.Err`
from the enclosing compatible `Result` function. It is not an `Opt` operator. `.expect(message)` and
`.expect_some(message)` convert an impossible failure into explicit `panic`.

Fallible allocating and IO APIs should return `Result`. Fast/raw helpers may expose sentinel values
at a trusted boundary. `panic` is for violated invariants and process-fatal paths; pooled actor
workers install a catch boundary so a behavior panic or worker stack overflow kills that actor rather
than the whole pool. Main and cooperative inline actor drains do not have that isolation boundary.

Integer division by zero/overflow, modulo by zero, slice out-of-bounds, and failed
`assert_nonnull` panic through the runtime floor.

## Entry points, backends, and tools

Executable entry points are:

```zen
main = () i32 { 0 }
```

or, after importing `Sys`:

```zen
{ Sys } = std.sys
main = (sys: Sys) i32 {
    writer := sys.stderr()
    writer.write_or_panic("starting\n")
    0
}
```

The compiler supplies `std.sys.root()` only to the one-argument form. Libraries should accept the
narrow capability they require (`Writer`, `Fs`, `Allocator`) instead of `Sys`.

The C backend is the bootstrap and complete execution path. The JavaScript backend walks the same
checked/monomorphized AST and supports a substantial computational subset plus browser DOM bindings;
some 64-bit, pointer-aliasing, native IO, and concurrency behavior remains target-limited.

`zenc fmt` is a faithful AST pretty-printer with comment anchoring and idempotence tests. `zenc doc`
is intentionally small: it prints public declaration heads and adjacent `//` documentation, not a
full documentation model.
