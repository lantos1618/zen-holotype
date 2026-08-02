# Zen Syntax Reference

This is a syntax-first guide to the Zen language implemented in this
repository. It collects the everyday grammar in one file. For exact semantics,
diagnostics, memory rules, and current limitations, see [SPEC.md](SPEC.md).

## Complete example

```zen
{ println } = std.io.print

Shape*: Circle(i32) | Rect(RectDims) | Unit
RectDims*: {
    width: i32,
    height: i32,
}

area = (shape: Shape) i32 {
    shape.match ({
        .Circle(radius) => 3 * radius * radius,
        .Rect(dims)     => dims.width * dims.height,
        .Unit           => 0,
    })
}

main = () i32 {
    println(area(.Circle(4)))
    println(area(.Rect(RectDims(width: 6, height: 7))))
    0
}
```

## Files, comments, and visibility

Zen files use the `.zen` extension. Statements do not require semicolons.

```zen
// line comment

/* block comment
   /* nested block comment */
*/
```

A `*` glued to a top-level declaration name exports it. An unstarred name is
private to its module.

```zen
public_fn* = () i32 { 1 }
private_fn = () i32 { 2 }
PublicType*: { value: i32 }
```

## Imports and modules

Destructure exported names from a dotted module path:

```zen
{ println, formatln } = std.io.print
{ helper } = util
```

Bind a namespace to use qualified names:

```zen
vec = std.collections.vec
left = sibling.left

numbers: vec.Vec<i32> = vec.empty(allocator)
answer = left.compute()
```

There is no `import` keyword.

## Declarations

### Functions

```zen
add* = (a: i32, b: i32) i32 {
    a + b
}

log = (message: StringView) void {
    println(message)
}
```

The general form is:

```text
name[*][<type-parameters>] = (name: Type, ...) ReturnType { body }
```

The trailing expression is the return value. Use `return expression` for an
early return. A bodyless function is a foreign declaration:

```zen
sqrt* = (value: f64) f64
```

Foreign providers and FFI grants are configured by the project build, never by
comments in a Zen source file. In `build.zen`, native configuration is expressed with functions on the
target:

```zen
build = (b: MutPtr<Build>) void {
    app = b
        .exe("app")
        .root("src")
        .main("main.zen")
        .cimport("vendor.math")
        .link("m")
    b.install(app)
}
```

A variadic parameter is spelled `name: ...Type` and must be last.

### Globals and local bindings

Module globals support these forms:

```zen
limit = 100          // constant, inferred
mask: i64 = 255      // constant, annotated
counter ::= 0        // mutable, inferred
```

Locals have four forms:

```zen
x = 1             // constant, inferred
y: i64 = 2        // constant, annotated
count ::= 0       // mutable, inferred
total :: i64 = 0  // mutable, annotated
```

Every binding requires an initializer. The `::` mark makes a binding mutable.
A bare `name = value` declares a constant only when the name is not already in
scope; otherwise it assigns the existing binding.

```zen
count = count + 1
point.x = 10
values[0] = 20
return count
```

Field and indexed assignment are statements. Zen has no compound assignments
such as `+=`.

### Structs

```zen
Point*: {
    x: i32,
    y: i32,
}

Config*: {
    retries: i32 = 3,
    verbose: bool = false,
}
```

Construct structs with named fields:

```zen
p = Point(x: 10, y: 20)
cfg = Config(verbose: true)
origin = Point()
```

An omitted field uses its declared default or is zero-filled. Defaults are
re-evaluated for each construction and must be constant expressions.

### Enums

```zen
Status*: Ready | Busy(i32) | Failed(StringView)
Message*: Ask(i64, i64, StringView) | Stop
```

Variants may have zero, one, or multiple positional payloads. Use a leading dot
when the expected enum type is known, or qualify the constructor:

```zen
state: Status = .Ready
other = Status.Busy(3)
message: Message = .Ask(1, 2, "why")
```

A leading bar is allowed for multiline enum layout:

```zen
Status*:
    | Ready
    | Busy(i32)
    | Failed(StringView)
```

## Types and generics

Primitive and built-in non-owning string types:

```zen
i32 i64 u8 f64 bool void
StringLiteral StringCstr StringView
```

Pointer and slice types:

```zen
Ptr<T>          // non-null, read-only
MutPtr<T>       // non-null, writable
RawPtr<T>       // nullable raw pointer
Slice<T>        // read-only pointer-and-length view
MutSlice<T>     // writable pointer-and-length view
```

Other type forms:

```zen
Point                       // named
io.Writer                   // qualified
Result<i32, IoError>        // generic
(left: i32, right: i32) i32  // function type with required parameter labels
```

Zen has no anonymous struct types or struct literals. Declare a named struct, then construct that name.

Put type parameters after a declaration name. A parameter may have one trait
bound with `T: Trait`.

```zen
Pair*<A, B>: { first: A, second: B }

wrap<T> = (value: T) Pair<T, T> {
    Pair<T, T>(first: value, second: value)
}

draw<T: Display> = (value: T) StringView {
    value.addr().display()
}
```

## Traits, implementations, and methods

Zen has no `trait`, `impl`, or `for` keywords. A record containing only
function-typed fields describes a trait:

```zen
Display*: {
    display: (self: Ptr<Self>) StringView,
}
```

Implement it with `Type.impl(Trait, { ... })`:

```zen
Label*: { text: StringView }

Label.impl(Display, {
    display = (label: Ptr<Label>) StringView { label.text }
})
```

Trait requirements may provide default bodies. Data structs may also contain
inherent methods:

```zen
Box*<T>: {
    value: T,
    get = (box: Box<T>) T { box.value },
}
```

Receiver syntax uses uniform function call syntax (UFCS): `x.f(a)` has the
call shape `f(x, a)`, with receiver-specific inherent or trait dispatch when
available.

## Literals

```zen
42                  // decimal integer
1_000_000           // digit separators
0xff                // hexadecimal
0b1010              // binary
0o755               // octal
3.1415              // f64
true
false
'A'                 // u8 character
"hello\n"           // escaped string
[1, 2, 3]           // mutable slice literal
Point(x: 1, y: 2)     // named struct value
```

Escaped strings and characters support escapes such as `\n`, `\t`, `\"`,
`\\`, and `\xNN`.

Triple-quoted strings are raw and may span lines:

```zen
json = """{"name":"zen","ok":true}"""

text = """
line one
line two: \n stays as two characters
"""
```

Raw strings do not process escapes. A newline immediately after the opening
delimiter is omitted; other newlines and indentation are content.

## Expressions, calls, and lambdas

```zen
f(a, b)                       // function call
make_adder(10)(5)             // call a returned closure
value.method(a)               // receiver call
value.field                   // field access
values[index]                 // indexing
generic<i32>(value)           // explicit call type argument
Box<i32>(value: 3)            // generic struct construction
Opt<i32>.Some(3)              // explicit generic enum construction
```

Blocks contain statements and may yield their trailing expression:

```zen
result = {
    doubled = value * 2
    doubled + 1
}
```

A lambda is a parameter list followed by an optional return type and a body:

```zen
double = (x: i32) i32 { x * 2 }
visit((x) { println(x) })
apply(() i32 { 42 })
```

Lambda annotations may be omitted when a surrounding function type supplies
them.

## Operators

From highest to lowest precedence:

| Level | Operators |
|---|---|
| 1 | `* / %` |
| 2 | `+ -` |
| 3 | `<< >>` |
| 4 | `&` |
| 5 | `^` |
| 6 | `\|` |
| 7 | `== != < <= > >=` |
| 8 | `&&` |
| 9 | `\|\|` |

Prefix operators are numeric negation `-value` and boolean negation `!value`.
Binary operators at the same level associate left to right.

## Conditional control flow

Zen has no `if` and no ternary operator. Use `.then` or `.match`.

A two-arm `.then` is a lazy conditional expression:

```zen
label = ready.then({ "ready" }, { "waiting" })
```

A one-arm `.then` is effect-only:

```zen
verbose.then({ println("details") })
```

The explicit boolean match is:

```zen
label = ready.match ({
    true  => "ready",
    false => "waiting",
})
```

## Pattern matching

Match an enum and bind payloads:

```zen
value.match ({
    .Some(item) => item,
    .None       => 0,
})

message.match ({
    .Ask(id, count, text) => handle(id, count, text),
    .Stop                 => 0,
})
```

Enum matches must cover every variant unless they contain `_`. Boolean,
integer, character, and string literals can also be labels. A literal match
needs a wildcard because its domain is not finite.

```zen
command.match ({
    "start" => 1,
    "stop"  => 2,
    _       => 0,
})
```

An arm body may be an expression, a block, or a bare early return.

## Iteration

Zen has one public iteration model: `loop` and the combinators built on it.
There is no `for` or ordinary public `while`:

```zen
values.loop((handle, index, value) {
    println(value)
    (value == 0).then({ handle.break })
})
```

Loop control goes through the loop handle instead of bare `break` or
`continue`.

`@while` is reserved solely for implementing the `loop` substrate. It is not a
second iteration form: applications, examples, compiler code, and all other
standard-library code must use `.loop` or a loop combinator. The reserved
implementation primitive is:

```zen
@while (condition) {
    work()
}
```

Remaining uses outside that loop implementation are migration debt, not public
Zen syntax or precedent for new code.

## Results and error propagation

Recoverable errors are enum values, normally `Result<T, E>`. The library
method `.or_return()` unwraps `Ok` or returns `Err` from the current
function:

```zen
load = () Result<i32, IoError> {
    value = read_value().or_return()
    .Ok(value + 1)
}
```

This is a method-based expression pattern, not punctuation syntax.

## Raw intrinsics

An `@` call selects a compiler/runtime substrate operation:

```zen
p = @addr(value)
copy = @load(p)
```

An arbitrary `@name(...)` is not automatically defined. Application code
should normally use ordinary functions and standard-library APIs.

## Deliberately absent syntax

Zen does not provide:

- `if`, `else`, or `condition ? yes : no`;
- `for` or ordinary public `while`;
- bare `break` and `continue` in public loops;
- `async`, `await`, or `yield`;
- `class`, `trait`, `impl`, or `import` keywords;
- uninitialized locals;
- exceptions or `try`/`catch`;
- compound assignment operators.

Use `.then`/`.match`, loop helpers, record-shaped traits, `.impl(...)`,
module bindings, and `Result<T, E>` instead.

## Formatting and checking

```sh
./zen fmt source.zen
./zen check source.zen
./zen run source.zen
```

`zen fmt` is the canonical layout guide.
