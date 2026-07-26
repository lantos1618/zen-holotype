# Zen Language Spec

This is the current-state spec for the self-hosted `zenc` compiler in this
repository. It describes behavior implemented by the code and covered by tests,
not every long-term idea. [STATUS.md](STATUS.md) is the feature and roadmap ledger.

The strongest executable references are the Zen-native harness (no Python):

- [tests/harness.zen](../tests/harness.zen) — entry that sums category fail counts.
- [tests/harness_build.zen](../tests/harness_build.zen) — CLI, examples, fixtures, diagnostics.
- [tests/harness_verdict.zen](../tests/harness_verdict.zen) — accept/reject + `error[kind]` pins.
- [tests/harness_value.zen](../tests/harness_value.zen) — stdout value cases.
- [tests/harness_modules.zen](../tests/harness_modules.zen) — imports / resolver / std coverage.
- [tests/harness_boundaries.zen](../tests/harness_boundaries.zen) — raw primitive boundaries.
- [tests/harness_fuzz.zen](../tests/harness_fuzz.zen) — malformed-input crash resistance.

## Source Files

A Zen source file is UTF-8 text containing top-level declarations and import
heads. `//` starts a line comment. The lexer also handles nested block comments
and treats unterminated comments/strings as parse errors instead of silently
truncating valid source.

Checked user commands are:

```sh
zenc check   <file.zen|project-dir>
zenc build   <file.zen|project-dir> [-o out]        # C backend (default)
zenc build   <file.zen> --target js [-o out.js]     # JS backend (compiler.backend.js.js)
zenc run     <file.zen|project-dir>
zenc emit    <file.zen>                              # checked C
zenc emit-js <file.zen>                              # checked JS floor + module
```

`zenc emit <file.zen>` resolves imports and namespace binds before writing C, so
its output matches the source shape that `build` and `run` compile. Plain
`zenc file.zen` remains a lower-level flat-module C emitter. It does not load
`std` imports or validate a user program the way the file-based commands do.

## Declarations

Top-level declarations are one of:

```zen
name* = (a: i32, b: i32) i32 { a + b }    // public function
helper = () i32 { 1 }                      // private function
foreign = (n: i64) RawPtr<u8>              // bodyless C extern
counter := 0                               // mutable module global
Point*: { x: i32, y: i32 }                 // struct
Shape*: Circle(i32) | Square(i32) | Dot    // enum
Box*<T>: { value: T }                      // generic struct
Opt*<T>: Some(T) | None                    // generic enum
```

`*` is a glued visibility marker on the declaration name. The checked module loader rejects
destructured imports and qualified value/type uses of unstarred declarations as
`error[private-name]`. The lower-level flat-module emitter has no module boundary to enforce.

Function bodies return their trailing expression. `return expr` is supported as
an early return statement, but early returns inside value-position block/match
arms are rejected because they would be dropped by expression emission.

Bodyless functions are foreign declarations. The backend emits C prototypes and
the system linker supplies the body. FFI is a build-granted capability: a
module may contain foreign declarations only when the build grants that module
(see [Imports And Modules](#imports-and-modules)); an ungranted foreign
declaration in a dependency is `error[ffi-ungranted]`.

The program entry point is `main`, in one of two shapes:

```zen
main = () i32 { ... }            // niladic entry
main = (sys: Sys) i32 { ... }    // capability entry (std.sys)
```

For the capability entry, the compiler renames the user body to `zen_user_main`
and emits a niladic `zen_main` trampoline that calls it with `std.sys.root()`, so
the C boundary (`zenrt.c`) is byte-identical to the niladic case. `Sys`
(`std.sys`) bundles narrow capabilities — `heap()` (the process `Allocator`),
`stdout()`/`stderr()` (`Writer`s), `env()`, `clock()`, `fs()` — and the intended
style is attenuation: a function takes the narrowest capability it needs (a
`Writer`, an `Allocator`), never the whole `Sys`. `Writer.write` returns
`Result<i64, IoError>`; `write_or_panic` is the fatal script sink. Ambient `println` remains
best-effort during migration (`docs/sys-phase2-print-writer.md`).

## Types

Implemented scalar and structural types:

```zen
i32 i64 u8 f64 bool void
string_literal string_cstr string_view
Ptr<T> MutPtr<T> RawPtr<T>
[T]
(A, B) C
Name
Name<T, U>
```

The three canonical non-owning string types express provenance:
`string_literal` is static literal storage, `string_cstr` is a borrowed
NUL-terminated pointer, and `string_view` is the general readable borrow. They
currently lower to `const char*`; a true `(ptr, len)` view is a later phase
(tracked in [STATUS.md](STATUS.md)). The parser still accepts `text`, `Cstr`, and
`str` as migration aliases, while formatting and diagnostics use the canonical
names. The owned growable buffer remains `String`. `[T]` is a fat slice with a
pointer and length. Function types are parameter types for inline templates and
closure arguments.

Assembling text goes through `std.text.sb`'s sticky builder `Sb`: the allocator
is named once, each op (`.s` str, `.i` i64, `.ch` byte, `.rep` iterated repeat)
no-ops after a recorded failure, and `.done()` settles the chain as one
`Result<string_cstr, IoError>` — so allocation failure stays a value without an
`.expect` per append:

```zen
a.sb().s("os ").s(name).ch('(').s(abi).ch(')').done()    // .Ok("os zen(x86)")
```

Pointer kinds are enforced by the checker even though all three lower to `T*`
in C. `Ptr<T>` is non-null/read-only, `MutPtr<T>` is non-null/writable, and
`RawPtr<T>` is nullable. A writable pointer may flow to a read-only slot, but
not the reverse; nested pointer, slice, and generic arguments are invariant.
`null_ptr()` has type `RawPtr<u8>`, the deliberately permissive allocator/FFI
floor. Typed `RawPtr<T>` values require `assert_nonnull` before non-null use, and
that assertion preserves an existing direction (`Ptr` stays `Ptr`, `MutPtr`
stays `MutPtr`) while narrowing typed `RawPtr` to `MutPtr`. The byte floor is an
explicit unsafe boundary because allocation results and null share its type.

Integer literals are context-sensitive. They fit numeric slots when in range and
default to `i32` unless the value requires `i64`. `u8 <= i32 <= i64` widening is
accepted. Explicit casts exist as intrinsics such as `to_i32`, `to_i64`,
`to_u8`, and `to_f64`.

### String literals

A `"…"` literal resolves `\`-escapes (`\n`, `\t`, `\"`, `\\`, `\xNN`).

A `"""…"""` literal is **raw** and may span lines:

```zen
src := """{"name":"zen","ok":true,"nums":[1,2,3]}"""

blob := """
line one
line two with "quotes" and \n that stays two characters
"""
```

Inside a raw literal:

- **No escape processing.** A backslash is an ordinary byte, so `\n` is the two
  characters `\` and `n`. A `"` is just a quote. Only the closing `"""` ends it.
- **Newlines are literal.** The text spans lines as written.
- **A newline immediately after the opening `"""` is dropped**, so the block form
  above is `"line one\n…"` rather than starting with a stray newline.
- **Indentation is content.** Nothing is de-indented — what you see is what you
  get. Indent a block literal and those spaces are in the string.

The delimiter is three quotes rather than two because `""` already means the
empty string; a doubled delimiter would make every existing `""` ambiguous.
Maximal munch takes three quotes when present, so `""` is unaffected. A raw
literal therefore cannot contain `"""`; use an escaped `"…"` literal for that.

Both forms produce the same value type — rawness is a property of the source
text, not of the resulting string — so backends and comparisons see no
difference. `zen fmt` reproduces a raw literal byte for byte and never
re-escapes its contents.

## Expressions And Statements

Core expressions:

```zen
1
1.5
'a'
"text"
x
x + y
f(a, b)
x.f(a, b)
Point(x: 1, y: 2)
.Some(3)
xs[i]
[1, 2, 3]
value.match({ pattern => expr, _ => fallback })
cond.then({ a }, { b })
```

`cond.then({ a }, { b })` is the conditional expression — pure parse-level
sugar for the boolean two-arm match: it parses to exactly the node
`cond.match ({ true => a, false => b })` produces, so both arms are lazy (only
the taken arm evaluates) and exactly one block yields the value. The condition
must be `bool`. A single-expression arm block is that expression; a
multi-statement arm block yields its trailing expression, like any block-bodied
match arm. The one-armed `cond.then({ a })` stays the effect-only form (false
is a no-op, no value). `.then` takes one or two block arguments — a non-block
argument or a third argument is a positioned parse error. As a postfix method
the form chains and composes bare (`(n > 3).then({ 1 }, { 2 }) + 5`); nesting
is ordinary block nesting (`a.then({ b.then({ x }, { y }) }, { z })`), with no
dangling-else ambiguity. Zen deliberately has NO `c ? t : e` ternary — all
control flow is a visible postfix method on a value, never punctuation (see
the `?` guard below). The formatter canonicalizes accordingly — a short
exhaustive two-arm boolean match prints as `cond.then({ a }, { b })` when it
fits on one line, while long, nested, or block-bodied forms keep the multiline
`.match` spelling.

Statements:

```zen
x := value       // local let
x: T := value    // typed local let
x = value        // assignment
obj.field = v    // field assignment
xs[i] = v        // slice element assignment
expr             // expression statement, trailing expression returns
return expr      // early return
@while(cond) { } // compiler/substrate primitive, not public style
```

Source-level branching is `.match` (with two-arm `.then({ a }, { b })` as its
expression spelling). `if`, `for`, and ordinary `while` are not source syntax.
The C backend may lower checked matches to C `switch`, `if`, or ternary
expressions as target details.

An exact source token `if` is rejected as `error[no-if]`. The diagnostic shows
the equivalent forms: `cond.then({ yes }, { no })` in expression position, and
`cond.match ({ true => yes, false => no })` for statement-position control
flow.
Conditional logic inside an enum arm is another nested boolean `.match`; Zen has
no match-guard exception to the no-`if` rule.

Beside the no-`if` law sits the permanent `?` guard: a `?` symbol token
anywhere in source is rejected as `error[no-ternary]` — the C-style ternary
`c ? t : e` (briefly accepted, then removed) is hidden-punctuation control
flow and is not Zen. `?` appears in no other Zen syntax; `?` inside comments,
string literals, and char literals is of course fine. The diagnostic teaches
`cond.then({ yes }, { no })` / `.match`. Both guards carry the same law
status: they are language identity, not style.

`loop` is the public slice iteration form:

```zen
xs.loop((h, i, x) {
    (x == 0).match({
        true  => { h.break },
        false => {}
    })
})
```

Raw `break`, `continue`, and `yield` are not public control flow. Loop control
is routed through the loop handle.

UFCS is part of call syntax: `x.f(a)` parses as `f(x, a)`. The checker can route
that call to receiver-specific inherent or trait methods.

For read-only trait lookup, all three non-owning string provenances dispatch
through the canonical `string_view` receiver. Thus one `string_view.impl(Trait,
{ ... })` serves literals, C strings, and views; this lookup normalization does
not weaken their value conversions or aggregate invariance.

## Structs, Enums, Match

Structs are product types:

```zen
Point*: { x: i32, y: i32 }
p := Point(x: 3, y: 4)
p.x
```

Enums are tagged sums:

```zen
Shape*: Circle(i32) | Square(i32) | Dot
area = (s: Shape) i32 {
    s.match({
        .Circle(r) => r * r * 3,
        .Square(w) => w * w,
        .Dot => 0
    })
}
```

Enum matches must be exhaustive unless they include `_`. Duplicate arms and
unknown variants are type errors. The precise rules are in the
[Semantics Contract](#semantics-contract) below.

## Semantics Contract

Six implemented decisions the rest of this spec assumes. Each is current
behavior, anchored to the code that enforces it.

### Integer overflow wraps

Signed integer arithmetic wraps (two's complement): `2147483647 + 1` is
`-2147483648`. This is language semantics, not a C accident — every C compile
passes `-fwrapv`, both the user `build`/`run` command line (`cc_command` in
[driver.zen](../driver.zen)) and the bootstrap seed (`CFLAGS` in
[bootstrap/Makefile](../bootstrap/Makefile)). `u8` arithmetic wraps mod 256 as
unsigned arithmetic always does. There is no trapping or undefined-overflow
compiler mode, and none is planned as a mode: checked or saturating arithmetic,
when it arrives, will be library methods on the integer types, not flags. On the
JS backend, `i32`/`u8` results are re-wrapped to width (`| 0`, `& 255`,
`Math.imul` — see `compiler.backend.js.js`); full-width `i64` wrapping there is deferred
with the rest of JS i64 (see Backends).

### Implicit conversions

The entire implicit-conversion surface is one function: `fits` in
`compiler/check.zen`. A value of type `g` fills a slot of type `w` when:

- **Integer widening by rank**: `u8 <= i32 <= i64` (`ty_rank`). A narrower
  integer fits a wider slot; never the reverse — passing `i32` where `u8` is
  expected is `error[arg-type]`.
- **`f64` is outside the chain**: no implicit conversion between any integer
  and `f64` in either direction; conversions are the explicit `to_f64` /
  `to_i32` / `to_i64` / `to_u8` intrinsics.
- **`RawPtr<u8>` is the raw floor** (`raw_floor_fits`): the byte-buffer type of
  `null_ptr()` and allocation results fits *any* pointer slot. This is the one
  deliberately permissive edge, confined to the allocator/FFI boundary.
- **Pointer capability only weakens** (`mode_fits`): `MutPtr<T>` fits a
  `Ptr<T>` or `RawPtr<T>` slot, but a read-only `Ptr<T>` never fits either
  writable spelling.
- **Nullability never vanishes implicitly**: a typed `RawPtr<T>` (nullable)
  never fits a non-null `Ptr<T>`/`MutPtr<T>` slot; it must pass
  `assert_nonnull` first.
- **String provenance is directional**: `string_literal` fits `string_cstr`
  and `string_view`, and `string_cstr` fits `string_view`, never the reverse
  (`ty_eq`).

None of the above happens under a constructor. Pointees, slice elements,
function types, and generic type arguments compare with `invariant_ty_eq`:
`[i32]` does not fit `[i64]`, `MutPtr<u8>` does not fit a `MutPtr<i32>` or
nested `Ptr<u8>` position, and the string provenances are distinct types inside
aggregates. Widening and capability loss are outer-value coercions only.

### Evaluation order

The intended order is left to right, in source order: call arguments, binary
operands, struct literal fields, slice literal elements. This intent is not yet
a full guarantee. The C backend emits calls and literals as plain C argument
and initializer lists (`gen_call_default` in `compiler/backend/c/c_emit.zen`), so
where lowering introduces no sequencing temporaries, the C compiler's
unspecified order leaks through. Separately, the known-defects table in
[STATUS.md](STATUS.md) tracks open evaluate-exactly-once defects: compound
assignments can evaluate the base/index twice, literal and discarded enum match
subjects can re-evaluate per arm, and generic substitution can duplicate or
drop a side-effecting argument. Do not write code whose correctness depends on
evaluation order or count of side effects within one expression until those
rows close.

### Definite initialization

Every local binding form carries a value: `x := v` and `x: T := v`. A
value-less local declaration (`x: i32` alone) is not syntax — it is rejected at
parse. Uninitialized locals therefore do not exist by construction, and there
is no definite-assignment analysis because there is nothing for it to check.

### Shadowing

`x := v` always introduces a fresh binding, even when `x` is already bound.
Verified current behavior:

- A local may shadow a parameter, and the initializer still sees the old
  binding: in `f = (x: i32) i32 { x := x + 1; x }`, `f(41)` is `42`.
- Rebinding in the same block is accepted — there is no redeclaration error —
  and the later binding wins for subsequent statements. The new binding may
  even change type: `x := 1` followed by `x := "hello"` is accepted.
- Loop-lambda parameters (`xs.loop((h, i, x) { ... })`) and bindings inside
  match-arm blocks shadow outer names only within their block; the outer
  binding is unchanged afterwards.

Locals and parameters also shadow same-named top-level functions and
intrinsics; calls through such a name go to the local value
(`shadows_toplevel` in `compiler/check_validate.zen`).

### Match arm order and coverage

For an enum match, the checker enforces (`compiler/check_validate.zen`,
`kv_match_kind`):

- **Coverage**: without `_`, every declared variant needs an arm —
  `error[exhaustiveness]`, naming the first uncovered variant.
- **No duplicates**: a repeated variant arm is `error[dup-variant]`, with or
  without a `_` arm present.
- **No unknown variants**: an arm naming a variant the enum does not declare
  is `error[undefined-name]`.

Arms are tried in source order and the first match wins. `_` matches any
subject, so an arm written after `_` is unreachable; today such an arm is
accepted silently rather than rejected — order your `_` last.

## Traits, Impls, Methods

A trait is a record of method requirements. There are no `trait`, `impl`, or
`for` keywords:

```zen
Area*: { area: (Ptr<Self>) i32 }
Circle*: { r: i32 }

Circle.impl(Area, {
    area = (c: Ptr<Circle>) i32 { 3 * c.r * c.r }
})
```

An impl must define every required method with the exact receiver, parameter,
and return types after substituting `Self` with the implementing type. Trait
default bodies are allowed in method-record fields and are materialized for
impls that omit them. The sole receiver-normalization exception is the read-only
string family described above.

Data structs can also own inherent methods inside their record body:

```zen
Box*<T>: {
    value: T
    get = (b: Box<T>) T { b.value }
}
```

Inherent methods are dispatched by receiver type, so two types can both expose
`score` without colliding at the source call site.

## Generics

Generic structs and enums are monomorphized per concrete use. Generic functions
infer type arguments from call arguments and expected types where available.

```zen
Box*<T>: { value: T }
wrap<T> = (x: T) Box<T> { Box<T>(value: x) }
```

Generic functions with function-typed parameters are inline templates. Closure
arguments such as `(a, x) { a + x }` are inlined at the call site; no runtime
function pointer is emitted for that template path.

Generic inference is still growing. The current tree proves `ReplyRef<T>.send`
works generically in actor flows, but broader inference coverage remains a
roadmap item.

### Struct Equality

`==` / `!=` between two values of the same struct type compare structurally.
An `eq` method provided by an impl on the type wins; otherwise the compiler
derives a per-field `==` fold via reflection — string fields compare by
content, enum fields by tag, struct fields recurse, pointer fields by
identity. Operands are evaluated exactly once.

```zen
Point: { x: i64, y: i64 }
p == q                          // derived per-field fold

Tagged.impl(EqOps, {
    eq = (a: Tagged, b: Tagged) bool { a.id == b.id }
})
t1 == t2                        // the impl wins over the derived fold
```

A struct qualifies for the derived fold only when every field is transitively
`==`-comparable; a slice- or fn-typed field rejects the compare with
`error[operand-type]` (provide an `eq` impl instead). Mismatched struct types
reject the same way. Pointers to structs stay C pointer identity.

### Struct Reflection

Reflection rides generics: three intrinsics expand at inline time, once the
receiver's concrete struct type is known, into ordinary field expressions —
zero runtime cost, no comptime block, no stringly-typed API.

- `x.field_eq(y)` — per-field `==` fold over `x` and `y`'s fields; struct-typed
  fields recurse into their own fold. Strings compare by content.
- `x.each_field(f)` — unrolls to one inlined call of `f(name, value)` per field
  (`name` is the field's name as a string literal, `value` is statically typed).
- `x.zip_fields(y, f)` — the paired form: `f(name, x_value, y_value)` per field.

```zen
sum_fields<T> = (v: T) i64 {
    acc: i64 = 0
    v.each_field((name, fv) {
        acc = acc + fv
    })
    acc
}
```

Each unrolled copy of the lambda is checked against that field's own type, so
heterogeneous work dispatches per field (Zig `inline for` / Nim `fieldPairs`).
Generic-struct receivers (`Box<i64>`) reflect with the instance's type
arguments substituted, and a side-effecting receiver expression is evaluated
exactly once. Ill-formed shapes are rejected with positioned diagnostics: a
non-struct receiver, mismatched pair subjects, a non-lambda function argument,
or a wrong-shape lambda all report `error[arg-type]`/`error[arity]`.

A generic function whose body uses a reflection intrinsic is always inlined at
its call sites (like function-typed-parameter templates), so such a body must
not be self-recursive (`error[recursive-hof]`) and must not `return` from
inside a loop (`error[reflect-return]`). The intrinsic names are reserved: the
only definable shape is a generic delegating wrapper such as
`field_eq<T> = (x: T, y: T) bool { x.field_eq(y) }`.

An `each_field`/`zip_fields` lambda's value parameter is an assignable PLACE:
when the subject is a plain local variable, `fv = …` inside the lambda writes
that field of the subject directly (this is how `std.format.serde`'s
`from_json` fills a struct). Function parameters are still VALUES — a callee
that writes its parameter (directly or through a reflection expansion over it)
gets its own copy, so the caller's argument is never mutated. A subject that is
NOT a plain local (a member expression, a call result, or an enclosing
reflection lambda's value parameter) is evaluated once into a hidden temp;
assigning through such a bound subject's lambda is rejected with
`error[reflect-write]` — bind the subject to a local first, fill the local,
and assign it back whole (`leaf := fv` … `fv = leaf`).

## Imports And Modules

Imports destructure a module path:

```zen
{ println } = std.text.fmt
{ helper } = util
c = std.io.c
left = left
```

Checked CLI modes call the self-hosted loader before parsing. The loader:

- resolves `std.X`, `compiler.X`, and sibling user modules from disk;
- follows transitive imports;
- strips import heads;
- concatenates each module body once;
- deduplicates top-level names with deterministic first-definition behavior.

Namespace binds (`alias = std.X`, `alias = sibling`) are the checked-loader path
for same-short-name modules. The loader prefixes the bound module's direct
exports and rewrites qualified uses, so two sibling modules can both export
`thing` or `Box` and a program can call `left.thing()` and `right.thing()` in
the same file.

`compiler.resolve` also exposes structured import-edge values for resolver
work:

```zen
ImportEdge*: { module: string_view, alias: string_view, namespace: bool, start: i32, next: i32 }
ProvidedSymbol*: { name: string_view, start: i32, next: i32, decl_start: i32, decl_next: i32, imported: bool, foreign: bool }
ModuleGraph*: { imports: [ImportEdge], symbols: [ProvidedSymbol] }
ModuleEntry*: { id: string_view, path: string_view, source: string_view, graph: ModuleGraph }
ModuleTable*: { modules: [ModuleEntry] }
ResolvedProgram*: { table: ModuleTable, flat: string_view, body_start: i64, body_end: i64 }
ParsedModule*: { id: string_view, path: string_view, source: string_view, body: string_view, graph: ModuleGraph, decls: [Decl] }
ParsedProgram*: { resolved: ResolvedProgram, modules: [ParsedModule], flat_decls: [Decl] }
```

`import_edges(a, src)` scans destructuring imports and namespace binds into
source-order edges such as `std/text/fmt` or `u/helper`, preserving the source
byte span for each edge. It only needs the `Allocator` trait, so callers can
back the edge slice and each edge's normalized `module`/`alias` strings with
heap, arena, or a custom allocator. `try_import_edges(a, src)` returns
`Result<[ImportEdge], IoError>` and reports allocation failure for the edge
slice, module strings, or alias strings. The checked loader uses these edges to
load destructuring dependencies and namespace-bound modules.
`provided_symbols_in(scratch, alloc, src)` scans a module into source-order
provided names, including import re-export heads and declarations. Parser
boundary checks still need `scratch: Ptr<Malloc>`, but the returned symbol slice
and normalized `name` strings are backed by the caller allocator, so callers can
use a heap, arena, or custom allocator for the data they keep. The compatibility
`provided_symbols(scratch, src)` wrapper uses the scratch allocator for both.
`start`/`next` span the provided name; `decl_start`/`decl_next` span the whole
declaration for real declarations, while import-head symbols use the head name
span. `imported` marks import-head re-exports; `foreign` marks bodyless foreign
declarations. The checked loader uses those symbols to validate `{ name } =
module` heads, build namespace alias rewrite sets, and detect duplicate
top-level user-module definitions. The final flat per-name dedup pass also
consumes those declaration spans instead of re-scanning declarations.
`module_graph_in(scratch, alloc, src)` returns both slices in one value, with
imports and symbols backed by `alloc`. `module_graph(scratch, src)` is the
compatibility wrapper. Both expose
`import_count`, `symbol_count`, and `has(name)` helpers; it is the current
structured resolver boundary that later AST/module-table loading can replace
without changing callers.
`module_table(a, root, progdir, inpath, src)` builds the transitive module
table used by the checked loader, including namespace-bound modules and their
own dependencies. The checked loader now validates import heads and loads
namespace/import closures from this table instead of re-reading and re-scanning
module files during flattening.
`resolve_program_data(a, root, progdir, inpath, src)` returns that table together
with the compatibility flat source string and main-body span; `resolve_program`
is the older string-returning wrapper used by the current C CLI.
`resolve_parsed_program(a, root, progdir, inpath, src)` parses each table entry
into a `ParsedModule` with the loader directives stripped from `body`, while
also exposing `flat_decls` for the compatibility path. This is the current
compiler-facing bridge toward per-module AST checking. `root_link_decls(a,
program)` builds the root module's import library from direct graph edges:
namespace binds contribute alias-shaped declarations such as `left__thing`,
while destructuring imports contribute plain declarations such as `plain`.
`check_parsed_program(a, program)` checks the root parsed module against those
graph-built import signatures using the checker link path.

This is still a source-text flattening loader at the parse/check boundary, not
the final AST/symbol-table module system. Destructuring imports still share a
flat short-name space.

Project directories can contain `zen.toml`:

```toml
package = "hello"
root = "src"
main = "main.zen"
out = "hello"
ccflags = "native.c"
ffi = "util, vendor.hooks"
```

`check`/`build`/`run <project-dir>` resolve `<root>/<main>`, use `out` for
build output when `-o` is omitted, and pass `ccflags` through to `cc`.

`Target.target(platform)` in `build.zen` selects a CROSS target. A platform
equal to the build host (std.build's default) compiles natively — the host
`cc` command line is byte-identical to a target-less build. Anything else is
canonicalized to a `<arch>-<os>-<abi>` triple (`aarch64-linux-gnu`,
`riscv64-linux-musl`, …) and a cross C compiler is resolved in order:
`$ZENC_TARGET_CC` (the verbatim compiler command — the escape hatch), the
conventional cross gcc `<triple>-gcc` on PATH (its own sysroot supplies libc,
so `-lm`/`link =` just work), then `zig cc -target <triple>`. No toolchain
found is a LOUD error naming all three options — never a silent host-cc
fallback. The triple folds into the content cache key, so flipping
`.target(...)` is always a cache miss. v1 scope is Linux cross-ARCH only
(aarch64 | x86_64 | riscv64, gnu | musl): cross-OS/wasm targets error as
unsupported (`bootstrap/zenrt.c` is POSIX/glibc-shaped — sigaltstack, ucontext
SP reads, pthread). The generated C's platform prelude reads the C compiler's
own macros, so `std.platform.host()` inside a cross-built binary correctly
reports the TARGET platform.

FFI is a build-granted capability. A module may contain foreign (bodyless)
declarations only when the build grants it, closing the supply-chain hole where
a transitive dependency declares `system` and shells out without the build ever
saying so. The grant surfaces are:

- `zen.toml`: `ffi = "util, vendor.hooks"` — comma-separated dotted user
  module ids;
- `build.zen`: `b.exe(…).ffi("util, vendor.hooks")` — the `Target`'s grant
  field, threaded through the emitted plan;
- single-file programs: an entry-file-only pragma line `//! ffi: util,
  vendor.hooks` (the pragma is ignored in dependency files).

Implicitly granted, with no declaration needed: repo-tree modules (`std.*` /
`compiler.*` — the audited stdlib is the sanctioned FFI surface) and the entry
module itself (an extern in the program's own file is visible to its author;
the threat model is dependencies, not the program). A grant names the
DECLARING module: granting `mid` does not grant `mid`'s own dependency. An
ungranted foreign declaration rejects during resolution as
`error[ffi-ungranted]` at the declaration's line, naming the module and the
symbol; `ZEN_VIS_REPORT=1` downgrades it to a report-only sweep, exactly like
`error[private-name]`. The manifest/registry grant text folds into the content
cache key (the entry pragma lives in the keyed source already).

On top of the grant system, `build.zen` projects can declare a C library as a
VALUE (`std.build`): a typed module, its link flag, and its grant travel as one
edge:

```zen
// build.zen
sdl := c_library(b, CLib(
    lib: "m",                                  // -> "-lm" appended to the target's link flags
    name: "cmath",                             // the module id programs import
    decls: [
        c_fn("cbrt", "(x: f64) f64"),          // signature = literal Zen text after the name
        c_fn("hypot", "(x: f64, y: f64) f64"),
        c_opaque("FILE"),                      // opaque handle struct `{ handle: RawPtr<u8> }`
    ],
))
exe.use(sdl)                                    // registers: genmod + link + ffi grant
```

`c_library` renders a generated module (one bodyless `name* = sig` line per
`c_fn`; `c_opaque` renders the std.web.dom-style opaque-handle struct), and
`exe.use(lib)` — a plain statement — registers the whole edge on that target:
`-l<lib>` on its link line, the module id on its ffi-grant line (the generated
module IS a foreign surface, so `use()` is what grants it), and the generated
source in the plan's trailing genmod section. The plan transport is line-based,
so each use travels as one record: a header line `<target> <id> <lib> <K>`
followed by exactly K lines of generated source (line-count-prefixed framing —
the body is opaque to the transport). The driver writes each selected target's
genmods to `<projdir>/.zen/gen/<id>.zen` (gitignore `.zen/`) and registers the
explicit id → path map with the resolver BEFORE probe and resolve; the one
canonical `module_path` consults that map first for user ids, then falls back
to the ordinary `<progdir>/<segs>.zen` mapping. Programs import the library by
its plain module id (`cm = cmath`), the generated declarations pass the normal
`error[ffi-type]` gate (a bad `c_fn` signature reports at the generated file's
line), a genmod id never resolves without `use()`, and the generated bytes fold
into the content cache key through the ordinary module walk (editing a `c_fn`
is a cache miss). `c_library` requires `build.zen` mode — a `zen.toml` project
has no build program in which to `use()` a library value.

## Memory And Ownership

The language currently exposes explicit memory primitives and library-level
ownership types:

- raw intrinsics: `@addr`, `@load`, `@store`, `offset`, `slice`, `cstr`,
  `sizeof`, `load_i64`, `store_i64`, `atomic_add_i64`, `null_ptr`;
- `std.mem.alloc`: `Allocator`, `Heap`, `Malloc`, namespace-bound
  `default`, `try_acquire`, `try_resize`;
- `std.mem.arena`: `Arena`, namespace-bound `new_in` and `try_new_in`;
- `std.core.slice`: allocator-first `alloc_buf`, `dup`, `node`, `concat`, their `_in`
  aliases, and fallible `try_*` variants for allocator-backed slice storage;
- `std.mem.own`: `Own<T>` plus `Drop`, with `new_in` and `try_new_in`;
- `std.mem.rc`: `Rc<T>`, with `new_in` and `try_new_in`;
- `std.mem.arc`: atomic `Arc<T>`, with `new_in` and `try_new_in`;
- `std.mem.trace`: tracing/cycle-collection substrate.

Allocator-threaded std APIs make allocation visible in signatures. Examples:
`vec.of(a, [1, 2])`, `v.push(a, x)`, `vec.try_of(a, [1, 2])`, `v.try_push(a, x)`,
`maps.of(a, "k", 1)`, `m.try_put(a, "k", 2)`, `maps.try_of(a, "k", 1)`,
`a.try_map_in([1, 2], (x) { x + 1 })`, `arena.new_in(a, 1024)`,
`slice.dup(a, [1, 2])`, `a.try_dup_in([1, 2])`, `own.new_in(a, value)`, `rc.try_new_in(a, value)`,
`actor.cell(a, 16)`, and `cell.reply(a)` — the actor constructors return `Result`
directly; there is no separate `try_*` doubling.

Current safety status: these APIs exist and are tested, and the checker rejects
same-body local use after `Own<T>.release_in(...)`, `Rc<T>.drop_in(...)`, or
`Arc<T>.drop_in(...)`. The full model is documented in
[MEMORY_MODEL.md](MEMORY_MODEL.md). Pointer direction and typed-raw nullability are
checked; `RawPtr<u8>` remains the deliberately permissive allocator/FFI floor.
Branch-sensitive/interprocedural ownership flow and full lifetime checking remain
roadmap items.

## Errors And Results

The stdlib policy: fallible operations return `Result` (allocation, IO, parsing);
panic is explicit and greppable, never the default path.

Zen has no exceptions and no unwinding. Fallible library APIs return values:

```zen
Result<T, E>: Ok(T) | Err(E)
Opt<T>: Some(T) | None
IoError*: NotFound | Denied | Eof | Errno(i32)
```

Callers branch with `.match`, propagate with `.or_return()` (unwrap `.Ok`, or
early-return the `.Err` from the enclosing `Result`-returning function), and
give up on invariants with `.expect("...")` / `.expect_some("...")` (unwrap or
panic with the mandatory message). `std.core.result` also provides sentinel-lifting
helpers such as `ok_if` and `ok_ptr`, the combinators `or` / `or_else` /
`map_err`, and `panic` as an explicit abort for invariants (framed as
`zen: panic: <msg>` on stderr, matching the runtime's div-zero/OOB panics).

The stdlib still has fast paths, raw sentinel APIs, and `Result` APIs. The
current policy documents which paths are intended to be recoverable; moving that
from convention to checker-enforced effects and ownership rules remains a
roadmap item.

## Diagnostics

Checked CLI errors report:

- source path;
- mapped line and column when available;
- stable error kind, such as `error[undefined-name]`;
- human message;
- source-line range marker when the source maps cleanly;
- hint.

The checker exposes
`CheckDiagnostic { code, kind, source_offset, span_width, count, message, hint }` for
checked CLI modes and `Diagnostic { code, kind, span: SourceSpan, count, message, hint }`
as a first-class Zen value. The CLI maps source offsets back to the user's file and
renders the source range. Current spans cover the identifier at the reported offset when
one is available; richer multi-diagnostic flows remain roadmap work.

## Concurrency

Concurrency support is stdlib-level today:

- `std.concurrent.coroutine`: coroutine substrate over context switching;
  `spawn` / `spawn_in` return `Result<Coro, IoError>` and clean up partial
  stack/context allocation before returning `.Err`;
- `std.concurrent.runtime`: sync/async runtime and colorless `checkpoint`,
  with namespace-bound `runtime.sync` / `runtime.async` constructors;
- `std.concurrent.sched`: small scheduler, with `try_run` / `try_run_in`
  for fallible scheduler flag allocation;
- `std.concurrent.actor`: cooperative typed actors (inline drain on the caller
  thread) — `Receiver<M>`, `CellRef<M>`, `ReplyRef<T>`, `ActorEngine<M>`,
  `ActorCell<M>`, and `ActorHandle<M, ActorT>`. `run` / `request` / `ask` are
  same-thread; not scheduled on the pool.
- `std.concurrent.pool_actor`: parallel typed actors on `std.concurrent.pool`
  (`PooledHandle`, `spawn_actor`, typed `send`). `Context<M>` / `Receiver<M>` are
  imported from `std.concurrent.actor` — one canonical definition serves both
  actor surfaces. Requires a concrete trampoline
  stub per `(Msg, ActorT)` until the compiler can address generic instantiations.
- `std.concurrent.cown`: owned FFI-handle examples, with namespace-bound
  `cown.buf` / `cown.try_buf` / `cown.file` / `cown.file_in` spellings;
- `std.concurrent.pool`: a multi-threaded actor pool that runs actors across N OS
  cores on real pthreads + atomics (one global mutex-guarded run queue; work-stealing
  deques are roadmap); `std.thread` / `std.sync` are the OS-thread and locking floor
  beneath it.

Public code should call runtime/actor APIs rather than raw coroutine checkpoint
primitives. Actor draining checkpoints internally, while allocator parameters
only own actor queues and reply storage. Actor messages are typed enums and
receivers implement `Receiver<M>` through
`Type.impl(Receiver<M>, { receive = ... })`.

Two concurrency safety guarantees are enforced, not just documented:

- **Sendability (move-on-send).** The checker's SENDABILITY pass
  (`compiler.check_validate`) kills the sender's binding when an owned `Own<T>` is
  passed into a `send`, so the sender cannot keep using memory the receiving actor
  now owns (a later use is `error[ownership]`). A `Ptr<T>` is sendable only when
  `T` is deeply immutable; `Arc<T>` is the shared-sendable path. A companion
  scratch-escape pass keeps actor-local scratch from escaping across a send.
- **Panic isolation.** A `panic` inside one actor's behavior (div-zero, OOB, null
  deref, or stack overflow) unwinds into a per-worker catch in `zenrt.c` and kills
  that one actor; the worker and the rest of the pool continue.

Note: `std.concurrent.runtime`'s colorless `checkpoint` and the ambient runtime
(`std.rt`, `std.scope`) are an experiment, not the shipped model. The current
direction threads capabilities explicitly (allocators, and a `Sys` at the entry);
reworking the ambient runtime toward "ambient-within-scope, explicit-at-boundary"
is a roadmap item; the current runtime source of truth is
`docs/runtime-design.md`.

`ActorEngine<M>` owns the internal queue state. `ActorCell<M>` is the
lower-level queue wrapper: it exposes `tell(message)` for fire-and-forget sends,
drives a receiver through `await_reply`, wraps request/reply flows through
`request`, and frees the engine storage through `free`. Actor cells infer
their message type from typed destinations such as
`cell_r: Result<actor.ActorCell<Msg>, IoError> := actor.cell(heap.addr(), 16)`,
then unwrap with `cell_r.expect("cell allocation")` (or keep the failure in the
value flow with `.match` / `.or_return()`), where `actor` is a namespace bind
for `std.concurrent.actor` and `heap` may come from namespace-bound
`alloc.gpa()` (`alloc = std.mem.heap`).
`ActorHandle<M, ActorT>` is the higher-level stateful actor wrapper for the
**cooperative** path. A program creates one with
`actor.spawn_handle(heap.addr(), 16, ActorState(...))`, which returns
`Result<ActorHandle<M, ActorT>, IoError>`.
It sends typed messages with `handle.tell(message)`, drains its owned state with
`handle.run()` (inline on the caller), wraps request/reply flows through
`handle.request(...)`, and releases storage with `handle.free(heap.addr())`.
For parallel typed actors on the pool, use `std.concurrent.pool_actor` instead
(see `examples/pool_actor_demo.zen`).
`request` creates the `ReplyRef<T>`, calls a request callback that returns the
typed message, for example `(reply) { .GetStats(reply) }`, enqueues it, drains
the receiver, awaits the reply, and releases the reply storage. The lower-level
`ask` method remains available for callbacks that need side effects before
draining. The allocating entry points — `actor.spawn_handle`, `actor.cell`,
`actor.engine`, and `cell.reply` — all return `Result` and clean up partial
allocation before returning `.Err`; there are no separate `try_*` variants.

## Backends

The C backend (`compiler.backend.c` / `c_emit`) is the shipping/bootstrap backend. It lowers the
checked, monomorphized AST to C and invokes `cc` for `build`/`run`. C is the intentional
intermediate/bootstrap target.

A second backend, `compiler.backend.js.js`, walks the **same** post-monomorphization `[Decl]` AST and
emits JavaScript (Node/browser) over a small linear-memory floor (`bootstrap/zenrt.js`). It is
driven by `zenc emit-js <file>` and `zenc build --target js <file> [-o out]`, and covers the
computational subset — full i64 / 64-bit bitwise (needs BigInt) and scalar aliasing through
`MutPtr<i32>` (needs boxed refs) are deferred. New target = new walk over the checked AST; the
kernel does not re-check.

## Tooling

`zenc fmt [--check] <file.zen>` uses the comment-preserving AST pretty-printer in
`compiler.pretty`. It preserves faithful source forms such as UFCS calls, formats
matches/declarations structurally, round-trips comments and literals, and is tested
for idempotence on fixtures and a real-source corpus.

`zenc doc <std.mod|file.zen>` lists public declaration heads and adjacent `//`
docs. It is a first-pass docs command, not a rich documentation generator.

`zenc lsp` runs a diagnostics-only Language Server over stdio (JSON-RPC 2.0,
`Content-Length`-framed). It handles `initialize` (advertising `textDocumentSync: 1`
full-sync), `textDocument/didOpen`/`didChange`/`didClose`, `shutdown`, and `exit`;
unknown methods are no-ops. On open/change it runs the same check pipeline as
`zenc check` on the document's full text and pushes `textDocument/publishDiagnostics`
— each `CheckDiagnostic` mapped to an LSP `Diagnostic` with a 0-based range (Zen's
1-based line/col minus one), `severity: 1`, `code` = diagnostic kind, and
`source: "zen"`. Stage 0 is single-file: the document directory is derived from the
`file://` URI so sibling/std imports resolve; multi-file project awareness is later.

## Test Map

| Spec area | Primary tests |
|---|---|
| CLI build/run/check/project manifest | [tests/harness_build.zen](../tests/harness_build.zen) |
| Examples | [tests/harness_build.zen](../tests/harness_build.zen) |
| Lexer/parser/bootstrap/fixpoint | [tests/harness.zen](../tests/harness.zen) (`fixpoint` suite) |
| Accepted/rejected core language behavior | [tests/harness_verdict.zen](../tests/harness_verdict.zen), [tests/harness_value.zen](../tests/harness_value.zen) |
| Crash-resistance fuzzing (malformed input) | [tests/harness_fuzz.zen](../tests/harness_fuzz.zen) |
| Traits and impl conformance | [tests/harness_verdict.zen](../tests/harness_verdict.zen) |
| Imports and resolver behavior | [tests/harness_modules.zen](../tests/harness_modules.zen) |
| Std module import coverage | [tests/harness_modules.zen](../tests/harness_modules.zen) |
| Raw primitive boundaries | [tests/harness_boundaries.zen](../tests/harness_boundaries.zen) |
| Formatter and docs commands | [tests/harness_build.zen](../tests/harness_build.zen) |
