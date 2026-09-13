# Numeric conversions

Primitive conversions belong to `std.core.num`. A dot call uses the exported
operation associated with its receiver type; a bare call imports it explicitly.
Both spellings evaluate the operand once.

Lossless widening returns the destination value directly. Checked conversion
returns `Res<T>`: a fitting value becomes `Ok(value)`, and a value outside the
destination range becomes `None`. No conversion in this surface allocates,
truncates, wraps, saturates, or silently changes an error into absence.

```zen
to_i32 = std.core.num

parse_count = (text: str) Res<i32> {
    text.parse_i64().try().to_i32()
}
```

The source type selects the overload; the expected return type does not.
An `i16` receiver's `to_i32()` is lossless and returns `i32`. An `i64` receiver's
`to_i32()` is checked and returns `Res<i32>`. A caller can propagate `None` with
`.try()` or translate it explicitly with `.ok_or(error)`.

## Supported checked conversions

| Source | Destination |
| --- | --- |
| `usize`, `u32` | `u8` |
| `u64` | `u16`, `usize`, `i32` |
| `i64` | `i32` |
| `i32` | `c_int` |
| `c_int` | `i32` |

`usize` follows the target pointer width; current targets are 64-bit. The
`u64` conversion keeps an optional result even on a 64-bit target. C integer
bridges use the destination's limits from the selected native ABI.

The existing `ToI64`, `ToU64`, and other widening bounds remain useful for
functions accepting several losslessly convertible source types. Their
`widen_*` members are implemented by the same standard conversion declarations.
They do not promise checked narrowing or authorize new compiler operations.

## Compiler boundary

The bodyless declarations in [std.core.num](../src/std/core/num.zen) are
compiler-provided. [Semantic validation](../src/sema/sema_numeric.zen) checks
their defining module, visibility, arity,
mutability, generic parameters, source type, and result type against the finite
supported contract. It records validated operations by declaration identity
before checking function bodies. Re-exports and local import aliases retain
that identity.

[C numeric generation](../src/gen/gen_c/gen_c_num.zen) renders these recorded
operations. C call lowering
never interprets a `to_` prefix as permission to cast. Checked target ranges
form an enum, so adding a range requires handling it in the renderer.

A source module cannot introduce a bodyless primitive conversion of its own,
even if nobody calls it. Write a function body or import the standard operation.
A user function with a body remains an ordinary function, including one named
`to_i32`. A translated C declaration keeps its explicit foreign binding and is
not interpreted as a conversion.

This contract uses the existing standard-library declaration mechanism; there
is no new intrinsic annotation or syntax. Other compiler-provided operations
still need their own explicit contracts. Scalar JS/assembly currently refuse
numeric types and conversion calls outside their documented support; this
change does not extend their supported surface.

## Evidence

The conversion corpus checks signed and unsigned boundaries, evaluation once,
free and dot calls, parsing, and native C integer bridges. Semantic fixtures
reject local conversion declarations and malformed standard signatures, while
existing tests exercise ordinary same-named functions and generic widening
bounds. `make verify` remains the aggregate gate.
