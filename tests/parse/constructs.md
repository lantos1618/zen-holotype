# Syntactic constructs of Zen, as they appear in `docs/DESIGN.md`

Every distinct syntactic construct that appears anywhere in `DESIGN.md`, transcribed
verbatim. This file is a **transcription**, not an interpretation: where the document
is unclear, the snippet is copied as-is and flagged. Where two parts of the document
disagree, **both readings are recorded** and neither is reconciled here.

Deliberately written blind to `grammar.js`. No tree-sitter node names appear below —
"what it should parse as" is prose only, so that a disagreement between this file and
the grammar localises an ambiguity in `DESIGN.md` rather than a naming mismatch.

Locations are `DESIGN.md:<line>` against the 1283-line revision read on 2026-08-05.

Legend:
- **FLAG** — the document does not settle this; a grammar must choose, and the choice
  belongs in `DESIGN.md` (per `PLAN.md:131`).
- **CONTRADICTION** — two places in `DESIGN.md` say different things.

Counts: **156 entries** catalogued (C001-C156, of which three record constructs that
are conspicuously *absent* from `DESIGN.md`), **30 inline FLAGs**, **8 inline
CONTRADICTIONs**, and **29 named ambiguities** collected at the end.

The must-fail companion suite is `errors/` — 26 programs, one construct each. Note
that `PLAN.md:86` names this directory `errors/` while `PLAN.md:148` calls it
`parse-errors/`; `errors/` is used here, per the tree.

---

## 1. Lexical

### C001 — line comment
```groovy
// this project's own build file
```
`DESIGN.md:10`, and everywhere. Trivia: a `//` comment running to end of line.
`DESIGN.md:50` requires it be **attached to a node, not discarded**.

### C002 — block comment
```groovy
{ /* @meta field-wise */ }
```
`DESIGN.md:483`. A `/* ... */` comment used as the *entire* body of a function.
FLAG: nesting is not addressed anywhere (`TESTING.md:30` says "nested block comments
(decide, then test)" — the decision is not in `DESIGN.md`).

### C003 — comment as trailing annotation on a declaration member
```groovy
    os: Os,        // Macos, Linux, Windows
```
`DESIGN.md:662`. A comment after the separating comma, on the same line as a field.

### C004 — comment between enum variants
```groovy
ArgError* =
    Missing(str),   // required field absent; names the field
    Parse(str)      // value present but not the field's type
```
`DESIGN.md:455-457`. Comment interposed between variants of a brace-less enum; the
enum must still terminate correctly.

### C005 — decimal integer literal
```groovy
const_val_implicit = 1;
```
`DESIGN.md:1245`. Also `8` (`562`), `40` (`951`), `64` (`951`), `36` (`1223`),
`255` (`1251`), `2147483648`-class values are never written.

### C006 — float literal
```groovy
c.radius * c.radius * 3.14159
```
`DESIGN.md:1017`. Also `1.0` (`106`), `2.0` (`133`), `5.0` (`108`).

### C007 — string literal
```groovy
some_static_string = "hello";
```
`DESIGN.md:1267`. Type is `str`, "living in static memory" (`DESIGN.md:338`).

### C008 — string literal containing `{}` format placeholders
```groovy
sb.add("circle: {}", circle.radius),
```
`DESIGN.md:1037`. `{}` is **not** interpolation syntax — arguments are positional and
follow the literal. Also `"{} {"` (`365`), `"build/{}-{}/example_zen{}"` (`919`),
`"{}!"` (`1268`).

### C009 — string literal containing a colon and an ellipsis
```groovy
    hash: "sha256:9f2a...",
```
`DESIGN.md:880`. Purely lexical: `:` and `.` inside a literal must not be tokenised.

### C010 — boolean literals in pattern position
```groovy
            true => Ok(self.data.read(i)),
            false => None,
```
`DESIGN.md:555-556`. FLAG: `true`/`false` appear **only** as match patterns and as a
default value (`DESIGN.md:1136`); the document never states whether they are keywords,
literals, or the variants of a `bool` enum.

### C011 — unit literal / unit type `()`
```groovy
    Ok(());
```
`DESIGN.md:370`. `()` in expression position (as a call argument) and in type position
(`Res<(), IoError>`, `DESIGN.md:364`).

### C012 — char literals
**ABSENT.** No `'a'` char literal appears anywhere in `DESIGN.md`, although
`TESTING.md:31` demands lexer tests for `'a'`, `'\''`, `'\\'`. FLAG: the character
literal is a lexer feature with **no design authority**.

### C013 — reserved words
**ABSENT.** `DESIGN.md` never lists reserved words. The only word-shaped operators it
uses are `consume` (`DESIGN.md:250`) and possibly `true`/`false`. FLAG.

---

## 2. Bindings

### C014 — immutable binding, inferred type
```groovy
const_val_implicit = 1;
```
`DESIGN.md:1245`. `name = expr` — "set at construction and never reassigned"
(`DESIGN.md:87`).

### C015 — immutable binding, explicit type
```groovy
    const_val_explicit : i32 = 1;
```
`DESIGN.md:1246`. Note the **space before the colon** in the source; `DESIGN.md:87`
writes the same form as `name: T` without the space (a formatting question, not a
grammar one, but `zen fmt --check` gates it).

### C016 — mutable binding, inferred type
```groovy
    mutable_val_implicit ::= 1;
```
`DESIGN.md:1247`.

### C017 — mutable binding, explicit type
```groovy
    mutable_val_explicit : i32 ::= 1;
```
`DESIGN.md:1248`.

### C018 — binding whose value is a call
```groovy
    alloc ::= env.mem.alloc();
```
`DESIGN.md:1163`.

### C019 — binding whose value is a lambda (this is how functions are declared)
```groovy
    add_i32 = (a: i32, b: i32) i32 { a + b }
```
`DESIGN.md:1168`. "functions are just bindings of lambdas, so they're values"
(`DESIGN.md:1166`). No `fn` keyword exists.

### C020 — rebinding a mutable function binding
```groovy
    op ::= add_i32;
    op = (a: i32, b: i32) i32 { a * b }
```
`DESIGN.md:1173-1174`. FLAG/CONTRADICTION: the second line is **textually identical**
to a fresh immutable binding (C019). Only scope resolution distinguishes "assignment
to `op`" from "declare `op`". A grammar cannot tell them apart, and `DESIGN.md` never
says which production this is. Compare C023 (field assignment), which is unambiguous
only because the LHS is a field access.

### C021 — binding a comptime type-returning call to a Type-cased name
```groovy
    Circle1 = AddFoo(Circle) // memoized on the call: one type
```
`DESIGN.md:1156`. FLAG: syntactically identical to a one-variant enum declaration
(`Shape = Circle(Circle)`), which is the ambiguity `DESIGN.md:32` names as already
found and does not resolve. See C061.

### C022 — multiple statements on one line
```groovy
v = alloc.Vec<i32>();    v.add(1);   // ERROR: add needs a mutable receiver
```
`DESIGN.md:229`. Two `;`-terminated statements on a line.

### C023 — assignment to a field
```groovy
        self.len = self.len + 1;
```
`DESIGN.md:549`. Also `self.data = self.alloc.realloc(self.data, cap).try();`
(`DESIGN.md:565`), `self.capacity = cap;` (`566`), and the rejected
`c.width = 5.0;` (`108`).

---

## 3. Struct declarations

### C024 — exported struct with storage fields, trailing comma
```groovy
str* = {
    data: Ptr<u8>,
    len: usize,
}
```
`DESIGN.md:345-348`. Name + `*` export marker + `=` + brace-delimited, comma-separated
field list with a trailing comma.

### C025 — single-line struct
```groovy
Circle* = { radius: f64 }
```
`DESIGN.md:126`. No trailing comma.

### C026 — empty struct
```groovy
Foo = {}
```
`DESIGN.md:1098`. Also `Collector = {}` (`1121`). Unexported, empty body, no
terminating `;`.

### C027 — unexported struct
```groovy
Circle = {
    radius: f64,
}
```
`DESIGN.md:1008-1010`. No `*`: not visible outside the module.

### C028 — mutable field (`::`)
```groovy
String* = {
    data :: Vec<u8>,
```
`DESIGN.md:353-354`. `name :: T` — mutable field (`DESIGN.md:87`).

### C029 — field with a default value
```groovy
    verbose :: bool = false, // --verbose or VERBOSE, defaults false
```
`DESIGN.md:1136`. `= default` "makes a field optional at construction"
(`DESIGN.md:87`). FLAG: the *only* example of a defaulted field is a `::` (mutable)
field. `DESIGN.md:87` states the rule for fields generally, so `name: T = default`
should also be legal, but is never exemplified.

### C030 — field whose type is a `Res`, meaning "may be absent"
```groovy
    name: Res<str>,          // --name or NAME, optional, may be absent
```
`DESIGN.md:1135`.

### C031 — struct mixing storage fields and a method with a body
```groovy
Rect* = {
    width: f64,          // Rect's own fields: storage
    height: f64,

    area* ::= (self: @Self) f64 { self.width * self.height }
}
```
`DESIGN.md:119-124`. FLAG: `height: f64,` ends with a comma, then a **blank line**,
then `area* ::= ...` which is **not** followed by a comma. See A-SEP below — member
separation inside a struct body is not stated anywhere.

### C032 — struct whose members are method *signatures* with no body
```groovy
String* = {
    data :: Vec<u8>,

    add* = (self :: @Self, fmt: str, args: ...) Res<(), IoError>
    view* = (self: @Self) str
}
```
`DESIGN.md:353-358`. Two method signatures, **no comma between them**, no bodies.
Per `DESIGN.md:93`, `= sig` means "required: impl must provide it".

### C033 — generic struct declaration
```groovy
Vec*<T> = {
    data :: Ptr<T>,
    len :: usize,
    capacity :: usize,
    alloc: Alloc,       // : set once at construction
```
`DESIGN.md:536-540`. Generic parameters are attached **to the name**, after the `*`.

### C034 — unexported generic struct
```groovy
Entry<K, V> = {
    hash: u64,
    key: K,
    value: V,
}
```
`DESIGN.md:572-576`.

### C035 — generic struct with bounded parameters
```groovy
Map*<K: Eq + Hash, V> = {
    entries :: Vec<Entry<K, V>>,
```
`DESIGN.md:581-582`. A bound written `K: Eq + Hash` — `+` in bound position, and a
second unbounded parameter after it. Nested generic in a field type.

### C036 — generic struct with one parameter used as a phantom
```groovy
Ref*<A> = {
    id: u64,
}
```
`DESIGN.md:784-786`. `A` appears nowhere in the body.

### C037 — struct of plain scalar fields
```groovy
BenchStats* = {
    ns_op: u64,
    allocs_op: u64,
    bytes_op: u64,
}
```
`DESIGN.md:632-636`. Also `Budget*` (`694-699`), `Package*` (`649-653`).

### C038 — struct field of a function type with zero parameters
```groovy
    iter* = (self: @Self, f: () ()) BenchStats
```
`DESIGN.md:629`. Parameter `f` has the function type `() ()` — no parameters, unit
return. `DESIGN.md:329`: "`() ()` has nothing to name and stays as it is."

---

## 4. Method / function members inside a declaration body

The five forms are tabulated at `DESIGN.md:91-97`; each is exemplified below.

### C039 — `name*` export marker on a member
```groovy
    add* = (self :: @Self, value: T) Res<(), AllocError> {
```
`DESIGN.md:546`. "exported from the module (same `*` as types)" (`DESIGN.md:93`).

### C040 — required member: `= sig` with no body
```groovy
    raw* = (self: @Self, size: usize, align: usize) Res<Ptr<u8>, AllocError>
```
`DESIGN.md:509`. "required: impl must provide it" (`DESIGN.md:94`).

### C041 — sealed member: `= sig {..}`
```groovy
    ne* = (self: @Self, other: @Self) bool { !self.eq(other) }
```
`DESIGN.md:486`. "sealed: provided, cannot be overridden" (`DESIGN.md:95`).

### C042 — default member: `::= sig {..}`
```groovy
    eq* ::= (self: @Self, other: @Self) bool { /* @meta field-wise */ }
```
`DESIGN.md:483`. "default: provided, impl may rebind it" (`DESIGN.md:96`).

### C043 — optional hook: `::= sig` with no body
```groovy
    toString* ::= (self: @Self, sb :: String) Res<(), IoError>
```
`DESIGN.md:377`. "optional hook: impl may provide it" (`DESIGN.md:97`).
Also `started* ::= (self :: @Self, ctx: Context) ()` (`DESIGN.md:801`).

### C044 — unexported member (no `*`)
```groovy
Drop* = {
    drop = (self :: @Self) ()
}
```
`DESIGN.md:430-432`. `drop` has no `*` even though `Drop` does.

### C045 — unexported method with a body inside an exported struct
```groovy
    grow = (self :: @Self) Res<(), AllocError> {
```
`DESIGN.md:560`. Named at `TESTING.md:48` as one of the two `*`-gate test cases.

### C046 — two members of the same name, differing in signature (overload)
```groovy
    toString* ::= (self: @Self, sb :: String) Res<(), IoError>

    toString* = (self: @Self, a: Alloc) Res<String, IoError> {
```
`DESIGN.md:377,382`. Same struct, same name, one optional hook and one sealed
overload. Resolution is "on declared parameter types and arity" (`DESIGN.md:325`).

### C047 — member whose name collides with a type name
```groovy
    Vec* ::= <T>(self: @Self) Vec<T>
    Map* ::= <K, V>(self: @Self) Map<K, V>
    String* ::= (self: @Self, fmt: str, args: ...) Res<String, AllocError>
```
`DESIGN.md:515-517`. Fields of `Alloc` named `Vec`, `Map`, `String`; called as
`alloc.Vec<i32>()` (`DESIGN.md:1220`).

### C048 — variadic parameter
```groovy
    add* = (self :: @Self, fmt: str, args: ...) Res<(), IoError>
```
`DESIGN.md:356`. `args: ...` — FLAG: `...` in type position appears twice
(`356`, `517`) and is never defined. Is `...` a type, or is `args: ...` a distinct
parameter form?

### C049 — `self` receiver, immutable
```groovy
len* = (self: @Self) usize { self.len }                        // does not
```
`DESIGN.md:227`.

### C050 — `self` receiver, mutable
```groovy
add* = (self :: @Self, value: T) Res<(), AllocError> { ... }   // mutates
```
`DESIGN.md:226`. Note the body is the literal three-character elision `{ ... }`.
FLAG: `{ ... }` occurs as a body at `226`, `227`(no), `236`, `237`, `521` — is
`...` an expression, or is this prose elision inside a code block?

### C051 — non-`self` mutable parameter
```groovy
    toString* ::= (self: @Self, sb :: String) Res<(), IoError>
```
`DESIGN.md:377`. `sb :: String`. Also `hasher :: Hasher` (`491`),
`b :: Builder` (`883`), `sb :: String` as the *first* parameter (`1044`).

### C052 — method written out-of-body as a free function
```groovy
add*    = (v :: Vec<T>, value: T) Res<(), AllocError> { ... }   // identical
```
`DESIGN.md:237`. Note multiple spaces between `add*` and `=`. `DESIGN.md:233`:
"`@Self` is spelled `Vec<T>` when you write the same function outside the body".

### C053 — struct declared entirely on one line, containing a method
```groovy
Vec*<T> = { add* = (self :: @Self, value: T) Res<(), AllocError> { ... } }
```
`DESIGN.md:236`.

---

## 5. Function declarations at module level

### C054 — exported function with body
```groovy
area* = (c: Circle) f64 {
    c.radius * c.radius * 3.14159
}
```
`DESIGN.md:1016-1018`. A UFCS free function: first parameter's type is `Circle`, so it
"calls like a method" (`DESIGN.md:1012-1015`).

### C055 — generic function with a struct-shaped bound
```groovy
scale* = <T: Rect>(shape: T, k: f64) f64 { shape.area() * k }
```
`DESIGN.md:138`. Generic parameters **after the `=`**, before the parameter list.
Contrast C033/C057. See A-GEN below.

### C056 — generic function, parameters after `=`, no body
```groovy
then* = <T>(b: bool, f: () T) Res<T>
```
`DESIGN.md:423`. Module-level declaration with a signature and no body. FLAG: at
module level (as opposed to inside a struct) `DESIGN.md` never says what "no body"
means. The method table at `91-97` is written about members.

### C057 — generic function, parameters attached to the *name*, no body
```groovy
loop*<T> = (body: (h: LoopHandle) ()) Res<T>
```
`DESIGN.md:717`. CONTRADICTION with C055/C056: both `name*<T> = (...)` and
`name* = <T>(...)` occur for functions. See A-GEN.

### C058 — overload set: one name, seven declarations
```groovy
loop*<T> = (body: (h: LoopHandle) ()) Res<T>
loop*<T> = (body: (h: LoopHandle, index: usize) ()) Res<T>
loop*<T> = (cond: () bool, body: (h: LoopHandle) ()) Res<T>
loop*<T> = (cond: bool, body: (h: LoopHandle) ()) Res<T>
loop*<T> = (range: Range, body: (h: LoopHandle, index: usize, value: T) ()) Res<T>
loop*<T> = (range: Range, body: (h: LoopHandle, value: T) ()) Res<T>
loop*<T, A> = (range: Range, init: A, body: (h: LoopHandle, index: usize, value: T, acc: A) A) Res<A>
```
`DESIGN.md:717-731` (interleaved with comments). Seven top-level bindings of the same
name, distinguished by parameter types and arity, including differing counts of
generic parameters.

### C059 — generic function over two parameters
```groovy
map*<T, U> = (range: Range, alloc: Alloc, body: (h: LoopHandle, index: usize, value: T) U) Res<Vec<U>>
```
`DESIGN.md:735`.

### C060 — function taking a `Map` and a three-parameter closure
```groovy
loop*<K, V> = (map: Map<K, V>, body: (h: LoopHandle, key: K, value: V) ()) Res<()>
```
`DESIGN.md:743`. Return type `Res<()>` — `Res` of unit.

### C061 — module-level signature declaration with no body
```groovy
read_cfg  = (p: Path) Res<Cfg, _>                       // internal: inferred from the body
read_cfg* = (p: Path) Res<Cfg, IoError | ParseError>    // exported: written out
```
`DESIGN.md:184-185`. Two declarations of the same name differing only in `*`. FLAG:
these are presented as the *same* function shown twice (internal vs exported form),
not as an overload pair. Note the aligned `=`.

### C062 — `_` as an inferred type argument
```groovy
read_cfg  = (p: Path) Res<Cfg, _>
```
`DESIGN.md:184`. `_` also serves as the wildcard pattern (C094). Two roles, one token.

### C063 — `main`
```groovy
main = (env: Env) Res<i32, Error>
```
`DESIGN.md:188` (signature only) and `DESIGN.md:1143` (with a body). Not a method:
"it is not named `self`" (`DESIGN.md:1141`).

---

## 6. Enum declarations

### C064 — exported generic enum, brace-less, newline+comma separated
```groovy
Res*<T> =
    Ok(T),
    None
```
`DESIGN.md:392-394`. No braces — "this is the asymmetry to get right"
(`PLAN.md:139`). Last variant carries no trailing comma.

### C065 — two enum declarations of the same name at different arities
```groovy
Res*<T> =
    Ok(T),
    None

Res*<T, E> =
    Ok(T),
    Err(E)
```
`DESIGN.md:392-398`. FLAG: type-level overloading on generic arity. The only
occurrence, and `DESIGN.md` never discusses it. Note both declare a variant `Ok`.

### C066 — single-variant enum with no payload
```groovy
AllocError* =
    OutOfMemory
```
`DESIGN.md:500-501`. **This is the known ambiguity** (`DESIGN.md:32`,
`PLAN.md:126-131`): indistinguishable from an alias `AllocError* = OutOfMemory`.
UNRESOLVED in `DESIGN.md`.

### C067 — single-variant enum with a payload
```groovy
TestError* =
    Failed(str)
```
`DESIGN.md:606-607`. Ambiguous against "call `Failed(str)` bound to `TestError*`" —
compare C021 `Circle1 = AddFoo(Circle)`, which *is* a call binding.

### C068 — multi-variant enum, no payloads
```groovy
BuildError* =
    NotFound,
    FetchFailed,
    VersionConflict,
    HashMismatch
```
`DESIGN.md:641-645`. Also `ActorError*` (`777-779`), `ThreadError*` (`819-821`).

### C069 — enum with payloads on some variants only
```groovy
Shape =
    Circle(Circle),
    Rect(Rect),
    Unit
```
`DESIGN.md:1027-1030`. Three variants, two carrying payloads; the payload type of a
variant has the **same name as the variant**. Unexported.

### C070 — enum whose payloads are all `str`
```groovy
ArgError* =
    Missing(str),   // required field absent; names the field
    Parse(str)      // value present but not the field's type
```
`DESIGN.md:455-457`.

### C071 — enum declaration terminated by a blank line
The brace-less enum has **no terminator**. `DESIGN.md:645` (`HashMismatch`) is
followed by a blank line and a comment, then `Package* = {`. FLAG: the end of a
variant list is defined only by "the next line is not a continuation". Where a
comment separates variants (C070) the previous line ends in `,`; where the enum
ends, it does not. A grammar must decide whether the comma is the continuation
signal or the newline is the terminator.

---

## 7. Type expressions

### C072 — primitive and named types
```groovy
    ns_op: u64,
```
`DESIGN.md:695`. Occurring: `u8`, `u64`, `i32`, `f64`, `usize`, `bool`, `str`,
`String`, `Path`, `Duration`, `Range`, `LoopHandle`, `Hasher`, `Module`, `Dep`,
`Os`, `Arch`, `Exe`, `Lib`, `Console`, `Mem`, `Fs`, `Net`, `Threads`, `IoError`,
`ParseError`, `Cfg`, `User`, `Field`, `Enum`, `Struct`, `Function`, `Other`.
Several are never declared anywhere in `DESIGN.md`.

### C073 — generic type application
```groovy
    argv: Vec<str>,       // raw argv; argv.get(0) is the program path
```
`DESIGN.md:701`. The `vars: Map<str, str>` that stood beside it is gone —
`Env.var(name) Res<str>` replaced a field that could never be filled.

### C074 — nested generic application
```groovy
    entries :: Vec<Entry<K, V>>,
```
`DESIGN.md:582`. Two closing angle brackets adjacent — `>>` must not lex as a shift.

### C075 — unit type in a generic argument
```groovy
add* = (self :: @Self, value: T) Res<(), AllocError> { ... }
```
`DESIGN.md:226`.

### C076 — function type as a parameter type, named parameters
```groovy
    apply = (f: (a: i32, b: i32) i32, a: i32, b: i32) i32 { f(a, b) }
```
`DESIGN.md:1169`. "Function types must name their parameters" (`DESIGN.md:329`).

### C077 — function type with zero parameters and a value return
```groovy
then* = <T>(b: bool, f: () T) Res<T>
```
`DESIGN.md:423`. `() T`.

### C078 — function type with zero parameters and unit return
```groovy
    defer* = (self: @Self, f: () ()) ()
```
`DESIGN.md:443`. `() ()` as a parameter type and `()` as the return type in one
signature.

### C079 — function type returning a generic
```groovy
    spawn* = <T>(self: @Self, a: Alloc, body: () Res<T, ThreadError>) Res<Thread, ThreadError>
```
`DESIGN.md:834`.

### C080 — anonymous error union in type position
```groovy
read_cfg* = (p: Path) Res<Cfg, IoError | ParseError>    // exported: written out
```
`DESIGN.md:185`. "`A | B` is an anonymous enum of two variants — a structural enum"
(`DESIGN.md:181`).

### C081 — top-level union alias declaration
```groovy
Error = AllocError | IoError | ArgError
```
`DESIGN.md:187`; four-way at `DESIGN.md:1139`:
```groovy
Error = AllocError | IoError | ArgError | ThreadError
```
A declaration whose RHS is a `|`-joined union — as opposed to the `,`-joined nominal
enum of C064-C070. FLAG: `|` and `,` both build sum types at declaration level and
mean different things; nothing in `DESIGN.md` names this distinction as syntax.

### C082 — fixed-array type
```groovy
//   buf: [u8, 64]
```
`DESIGN.md:533`. **Appears only inside a comment.** `[type, count]` — "comptime
length, lives on the stack, no alloc" (`DESIGN.md:529-530`). FLAG: the type-position
form of a fixed array is never written in live code.

### C083 — pointer type
```groovy
    data: Ptr<u8>,
```
`DESIGN.md:346`. "(`*` is reserved for exports, so raw pointers are `Ptr<T>`)"
(`DESIGN.md:340`) — an explicit prohibition on `*T`.

### C084 — `@Self` in type position
```groovy
len* = (self: @Self) usize { self.len }
```
`DESIGN.md:227`. "the type being declared, supplied by the compiler inside a struct
or impl body" (`DESIGN.md:223`).

### C085 — generic parameter list with a bound naming a struct
```groovy
    spawn* = <A: Actor>(self: @Self, actor: A) Ref<A>
```
`DESIGN.md:475`.

### C086 — generic parameter list with a bound in a method with a body elsewhere
```groovy
    expect_eq* = <T: Eq>(self: @Self, a: T, b: T) Res<(), TestError>
```
`DESIGN.md:617`.

---

## 8. Match

### C087 — match as an expression, boolean patterns
```groovy
    label = (const_val_implicit == 0).match({
        true => "zero",
        false => "nonzero",
    })
```
`DESIGN.md:152`. `.match` is a method taking one brace-delimited argument;
arms are `pattern => expr`, comma-separated, **trailing comma present**, no leading
`|` (`DESIGN.md:152`). Note: **no `;` after the closing `)`**. The comma between
two arms is nevertheless OPTIONAL, as between struct members (D6): issue #770
was grammar/match_block demanding what the compiler's arm parser -- which eats
each arm's separator with `p.eat` -- never did, so a block-bodied arm followed
by another arm parses with or without it, and tests/corpus/parse/
block_bodied_arm_needs_no_comma pins the comma-less spelling for both parsers.

### C088 — match in statement/tail position as a function's value
```groovy
    get* = (self: @Self, i: usize) Res<T> {
        (i < self.len).match({
            true => Ok(self.data.read(i)),
            false => None,
        })
    }
```
`DESIGN.md:553-558`.

### C089 — match bound to a name, arms with arithmetic
```groovy
        cap = (self.capacity == 0).match({
            true => 8,
            false => self.capacity * 2,
        })
```
`DESIGN.md:561-564`. No `;` terminating the binding.

### C090 — match with payload-binding patterns
```groovy
    name = opts.name.match({
        Ok(n) => n,
        None  => "world",
    })
```
`DESIGN.md:1149-1152`. `Ok(n) =>` binds the payload in the pattern
(`DESIGN.md:152`). Note the alignment of `=>` (two spaces after `None`), which
`PLAN.md:278` makes a formatter rule.

### C091 — match on `self`, enum variant patterns with payload binding
```groovy
        self.match({
            Circle(circle) => sb.add("circle: {}", circle.radius),
            Rect(rect) => sb.add("rect: {} {}", rect.width, rect.height),
            Unit => sb.add("unit"),
        })
```
`DESIGN.md:1036-1040`. Patterns are **unqualified** variant names; a variant with no
payload is a bare name.

### C092 — match on a `Res` with both arms calling
```groovy
    t.join().match({
        Ok(v)  => println("thread says {}", v),
        Err(e) => println("thread failed: {}", e),
    })
```
`DESIGN.md:1209-1212`.

### C093 — match on an enum field of a value
```groovy
    lib_paths = b.os.match({
        Macos => ["/opt/homebrew/lib"],
        Linux => ["/usr/local/lib"],
        Windows => ["C:/sodium/lib"],
    })
```
`DESIGN.md:886-891`. Arm bodies are array literals.

### C094 — wildcard arm `_`
```groovy
    ext = b.os.match({
        Windows => ".exe",
        _ => "",
    })
```
`DESIGN.md:908-911`. "cover every case or write `_`" (`DESIGN.md:152`).

### C095 — match arm whose body is a block
```groovy
    @meta(n).type.match({
        Struct(s) => {
            s.fields.add(Field(name: "foo", value: 1));
        },
        _ => Err(Error("Invalid node type")),
    });
```
`DESIGN.md:1087-1092`. A `{ ... }` block as an arm body, followed by a comma; and
the whole match **terminated with `;`** — contrast C087/C088/C089 which are not.

### C096 — match whose arms dispatch to overloads
```groovy
    @meta(n).type.match({
        Enum(e) => DumpAst(sb, e),
        Struct(s) => DumpAst(sb, s),
        Function(f) => DumpAst(sb, f),
        Other(o) => DumpAst(sb, o),
    })
```
`DESIGN.md:1075-1080`.

### C097 — match on the result of a call chain
```groovy
    alloc.String("{}", sum).match({
        Ok(s)  => println(s),
        Err(e) => println("error: {}", e),
    })
```
`DESIGN.md:1239-1242`.

---

## 9. Closures and blocks

### C098 — closure with zero parameters
```groovy
    (const_val_implicit == 0).then(() { println("const_val_implicit is 0") });
```
`DESIGN.md:1264`. `() { ... }` — a lambda with an empty parameter list, no return
type, passed as an argument.

### C099 — closure with untyped parameters
```groovy
    n.fields.loop((h, field) {
        sb.add("{}: {}", field.name, field.value);
    })
```
`DESIGN.md:1046-1048`. CONTRADICTION with `DESIGN.md:223`: "that parameter is
written out like every other one — a name and a type, **never bare**". Closure
parameters here are bare names. See A-CLO.

### C100 — closure with mixed typed and untyped parameters
```groovy
    sum = [0, 1, 2].loop(0, (h, i, v, acc: i32) {
        acc + v
    })
```
`DESIGN.md:1233-1235`. `h`, `i`, `v` bare; `acc: i32` typed.

### C101 — closure with an explicit return type and no parameters
```groovy
    t = env.threads.spawn(alloc, () Res<i32, ThreadError> {
        Ok(21 * 2);   // imagine ffi or heavy batch work here
    }).try();
```
`DESIGN.md:1206-1208`. `() Res<i32, ThreadError> { .. }` as an argument, with a
method call `.try()` on the enclosing call's result.

### C102 — closure containing statements
```groovy
    bn.iter(() {
        v ::= bn.alloc.Vec<i32>();
        v.add(1);
    })
```
`DESIGN.md:985-988`.

### C103 — nested closures
```groovy
        self.entries.loop((hd, e) {
            ((e.hash == h) && e.key.eq(key)).then(() { hd.break(e.value) })
        })
```
`DESIGN.md:593-595`. A closure inside a closure; neither the inner nor the outer
call is `;`-terminated.

### C104 — bare block as a statement, nested
```groovy
{
    outer = @scope;
    {
        inner = @scope;                              // the inner block
        inner.defer(() { println("inner cleanup") });
    }                                                // inner's defers run, inner dies
    outer.defer(() { println("outer cleanup") });
}
```
`DESIGN.md:162-171`. A brace-delimited block in statement position, containing a
nested block. FLAG: this is a **fourth** meaning of `{` (see A-BRACE).

### C105 — block whose last expression is its value, no semicolon
```groovy
    area* ::= (self: @Self) f64 { self.width * self.height }
```
`DESIGN.md:123`. Also `{ a + b }` (`1168`), `{ acc + v }` (`1234`),
`{ x + base }` (`1179`), `{ !self.eq(other) }` (`486`), `{ shape.area() * k }` (`138`).

### C106 — block whose last expression **carries** a semicolon and is still the value
```groovy
    Ok(());
}
```
`DESIGN.md:370-371`, `959`, `973`, `1094`, `1270` (`Ok(0);`).
CONTRADICTION with C105: `DESIGN.md:405-406` states "`0;` closes a `Res<i32, E>`
function like `Ok(0);` does", so a trailing `;` does **not** discard the value; yet
C105 shows the same role played with no `;`. Both forms are the tail expression.

---

## 10. Expressions

### C107 — method call chain
```groovy
    self.entries.add(Entry(hash: h, key: key, value: value)).try();
```
`DESIGN.md:587`.

### C108 — `.try()` — non-local exit
```groovy
    names.add("ada").try();
```
`DESIGN.md:1221`. "the non-local-exit intrinsic, not a method on `Res`"
(`DESIGN.md:411-412`) — but written in method position everywhere.

### C109 — parenthesised expression as a method receiver
```groovy
        (self.len == self.capacity).then(() { self.grow().try() });
```
`DESIGN.md:547`. "a plain ufcs function: first param is bool, so it calls as a
method" (`DESIGN.md:422`).

### C110 — call with explicit generic arguments
```groovy
    opts = env.args<Opts>().try();
```
`DESIGN.md:1147`. FLAG: `x.f<T>()` — the classic `<` ambiguity against comparison.
`DESIGN.md` never addresses it. Also `alloc.Vec<i32>()` (`1220`),
`alloc.Map<str, i32>()` (`1223`), `b.alloc.Vec<Function>()` (`926`),
`t.alloc.Vec<i32>()` (`969`), `alloc.Vec<Display>()` (`144`).

### C111 — construction with named arguments
```groovy
c = Circle(radius: 1.0);
```
`DESIGN.md:106`. "the same `name: value` form used at construction"
(`DESIGN.md:129`). Also `Entry(hash: h, key: key, value: value)` (`587`),
`Field(name: "foo", value: 1)` (`1090`), `c1 = Circle1(radius: 1.0, foo: 1);`
(`1157`), `Budget(name: "vec_add", ns_op: 40, allocs_op: 1, bytes_op: 64)` (`951`).

### C112 — multi-line construction with a trailing comma
```groovy
json_pkg = Package(
    url: "https://github.com/zen-pkgs/json",
    version: "0.3.1",
    hash: "sha256:9f2a...",
)
```
`DESIGN.md:877-881`. No terminating `;`.

### C113 — construction with **positional** arguments
```groovy
    Range(0, 5).loop((h, v) {
```
`DESIGN.md:1186`. Also `Path("src")` (`929`), `Hasher()` (`585`), `Foo()` (`1185`),
`Collector()` (`1193`), `Error("Invalid node type")` (`1091`),
`Path("build/{}-{}/example_zen{}", b.os, b.arch, ext)` (`919`).
FLAG/CONTRADICTION with C111: `DESIGN.md:129` says construction takes `name: value`;
these take positional arguments, and `Path(...)` takes a format string plus
positional arguments.

### C114 — anonymous record literal as an argument
```groovy
    libsodium = b.lib("libsodium", {
        src: Path("src/extern.c"),
        libs: ["sodium"],
        paths: lib_paths,
    })
```
`DESIGN.md:895-899`. A `{ name: expr, .. }` literal with no type name in front,
passed as the second argument. Also `b.exe(...)` (`916-920`), `b.test(...)`
(`932-935`), `b.bench(...)` (`948-953`), `b.extern(...)` (`901-905`).
FLAG: `DESIGN.md` never names this construct; it is a **third** meaning of `{`.

### C115 — array literal
```groovy
        deps: [json, libsodium, extern_add],
```
`DESIGN.md:918`. Also `["sodium"]` (`897`), `["/opt/homebrew/lib"]` (`887`),
`[0, 1, 2]` (`1233`), `[Budget(...)]` (`950-952`).

### C116 — fixed-array construction: type applied to arguments
```groovy
    primes = [i32, 4](2, 3, 5, 7);
```
`DESIGN.md:1216`. Named at `TESTING.md:42` as a known ambiguity:
"`[i32, 4](2, 3)` as type-applied-to-arguments". Also written in a comment at
`DESIGN.md:534`.

### C117 — array literal with an inferred fixed type
```groovy
    sum = [0, 1, 2].loop(0, (h, i, v, acc: i32) {
```
`DESIGN.md:1233`. "`[0, 1, 2]` literals infer `[i32, 3]`" (`DESIGN.md:530`).
FLAG: `[0, 1, 2]` (a literal) and `[i32, 4]` (a type) are distinguished only by
whether the elements are types.

### C118 — index expression
```groovy
- `buf[i]` on a fixed array is **bounds-checked and traps**.
```
`DESIGN.md:210`. FLAG: **the only `[...]` index expression in the document**, and it
appears in prose, not in a code block. Every other element access is `.get(i)`.

### C119 — address-of
```groovy
p = &c.width;     // ERROR: computed field, no address exists
```
`DESIGN.md:107`. FLAG: **the only `&` in the document**. It appears in a line marked
ERROR — but the error is "computed field", not "`&` does not exist", so `&` is
apparently a real operator. Never otherwise used or specified.

### C120 — qualified enum variant in expression position
```groovy
    s = Shape.Unit;
```
`DESIGN.md:977`. Also `Error.NotFound` (`199`). Contrast C091: patterns are
unqualified, expressions are qualified.

### C121 — qualified associated call
```groovy
    b.budget(Duration.seconds(60));
```
`DESIGN.md:957`.

### C122 — qualified constant on a primitive type
```groovy
- `/ %` **trap** on a zero divisor, and on `i32.MIN / -1`
```
`DESIGN.md:209`. `i32.MIN` — a member access on a primitive type name, in prose only.

### C123 — `consume` as a prefix operator on a binding
```groovy
g = consume f;                  // move, stated at the use site. f is dead after
```
`DESIGN.md:254`.

### C124 — `consume` in argument position
```groovy
worker.process(consume buf);
```
`DESIGN.md:273`.

### C125 — arithmetic operators
```groovy
        self.len = self.len + 1;
```
`DESIGN.md:549`. Occurring: `+` (`549`), `-` (prose `208`), `*` (`123`, `1174`),
`/` and `%` (prose `209`).

### C126 — wrapping arithmetic operators
```groovy
    wrapped = const_val_implicit +% 255;
```
`DESIGN.md:1251`. `+% -% *%` (`DESIGN.md:208`); only `+%` is ever written in code.

### C127 — comparison operators
```groovy
        (i < self.len).match({
```
`DESIGN.md:554`. `<` (`554`), `==` (`547`, `561`, `928`, `1257`).
FLAG: `>`, `<=`, `>=`, `!=` never appear. `ne` exists as a method (`DESIGN.md:486`).

### C128 — logical and
```groovy
            ((e.hash == h) && e.key.eq(key)).then(() { hd.break(e.value) })
```
`DESIGN.md:594`. FLAG: `||` never appears anywhere.

### C129 — logical not
```groovy
    ne* = (self: @Self, other: @Self) bool { !self.eq(other) }
```
`DESIGN.md:486`.

### C130 — operator precedence
**ABSENT.** `DESIGN.md` states no precedence or associativity for any operator, yet
`TESTING.md:38` requires "one test per operator pair, including `+%` against `+`".
FLAG: precedence has no design authority.

### C131 — leading-dot method call continued on the next line
```groovy
        (f.params.len == 1 && f.params.get(0).try().type == Tester)
            .then(() { tests.add(f).try() })
```
`DESIGN.md:928-929`, repeated at `941-942`. FLAG: the only place a call chain is
broken across lines with a leading `.`.

### C132 — field named `type`
```groovy
        (f.params.len == 1 && f.params.get(0).try().type == Tester)
```
`DESIGN.md:928`. Also `@meta(n).type` (`1075`, `1087`). `type` is not reserved.

### C133 — bare `println` call (ambient-by-type sugar)
```groovy
    println("sent all five");   // may print BEFORE any receive
```
`DESIGN.md:1189`. "sugar for `<the Env in scope>.out.println(...)`, resolved BY TYPE"
(`DESIGN.md:451-452`). Syntactically an ordinary call.

### C134 — `.as(Trait)` fat-value construction
```groovy
printers.add(circle.as(Display)).try();   // 2 words copied in, no alloc
```
`DESIGN.md:145`. An ordinary method call taking a *type* as its argument.

### C135 — behaviour call on a `Ref` (a send)
```groovy
    foo.compute(41, bar);       // returns immediately
```
`DESIGN.md:1194`. "calling IS sending" (`DESIGN.md:758`). Syntactically an ordinary
method call. Also `foo.receive_msg("hello world!");` (`1187`), `foo.stop();` (`1197`),
`reply.result(n + 1);` (`1117`).

### C136 — loop-handle break
```groovy
            ((e.hash == h) && e.key.eq(key)).then(() { hd.break(e.value) })
```
`DESIGN.md:594`. `h.next()`, `h.break()`, `h.break(value)` (`DESIGN.md:747-749`, in
a comment). Ordinary method calls on the handle.

---

## 11. Impl declarations

### C137 — impl supplying computed field **values**
```groovy
Circle.impl(Rect, {
    width: self.radius * 2.0,
    height: self.radius * 2.0,
})
```
`DESIGN.md:132-135`. `Type.impl(Target, { .. })` — "a call in a statement position
that declares" (`PLAN.md:142`). Entries are `name: expr`, comma-separated, trailing
comma. `self` is in scope with no parameter declaring it. No terminating `;`.

### C138 — impl supplying a method with `::=`
```groovy
Shape.impl(Display, {
    toString ::= (self: @Self, sb :: String) Res<(), IoError> {
        self.match({
            Circle(circle) => sb.add("circle: {}", circle.radius),
            Rect(rect) => sb.add("rect: {} {}", rect.width, rect.height),
            Unit => sb.add("unit"),
        })
    }
})
```
`DESIGN.md:1032-1042`. The supplied name has **no `*`** even though `Display.toString`
does.

### C139 — impl supplying a method with `=`
```groovy
Alloc.impl(Drop, {
    drop = (self :: @Self) () { /* arena: release every page at once */ }
})
```
`DESIGN.md:520-522`. Return type `()` followed by a body.

### C140 — impl mixing `::=` hooks and `=` behaviours, no separators
```groovy
Foo.impl(Actor, {
    started ::= (self :: @Self, ctx: Context) { println("actor started") }
    stopped ::= (self :: @Self, ctx: Context) { println("actor stopped") }

    receive_msg = (self :: @Self, ctx: Context, data: str) {
        println("actor has received {}", data)
    }

    compute = (self :: @Self, ctx: Context, n: i32, reply: Ref<Collector>) {
        reply.result(n + 1);
    }
})
```
`DESIGN.md:1100-1119`. **No commas between members** — contrast C137, whose members
*are* comma-separated. CONTRADICTION: `started` here has **no return type**, while
`Actor.started*` at `DESIGN.md:801` is declared
`started* ::= (self :: @Self, ctx: Context) ()`. See A-RET.
Also: `receive_msg` and `compute` are supplied but are **not declared by `Actor`**.

### C141 — impl on an empty struct
```groovy
Collector.impl(Actor, {
    result = (self :: @Self, ctx: Context, v: i32) {
        println("got {}", v)
    }
})
```
`DESIGN.md:1123-1127`.

---

## 12. Modules and imports

### C142 — import binding a list of names from a module path
```groovy
Res, Ok, None = std.core.result     // imported, local to this module
```
`DESIGN.md:291`. Comma-separated names on the left, a dotted module path on the
right. FLAG: syntactically a multi-name binding; nothing else in the language binds
several names at once.

### C143 — re-export: an import whose bindings are starred
```groovy
Res*, Ok*, None* = std.core.result  // imported AND re-exported
len*, view* = std.text.string
```
`DESIGN.md:292-293`. "Re-export is an import whose bindings are starred. No `export`,
no `from`" (`DESIGN.md:287`) — an explicit prohibition.

### C144 — single-name import from a namespace
```groovy
json = pkg.json
sodium = pkg.libsodium
```
`DESIGN.md:1005-1006`. No `;`. `std` and `pkg` are namespaces (`DESIGN.md:996`).

---

## 13. `@` — the compiler namespace

`DESIGN.md:302`: "one flat namespace, deliberately small, and everything in it is
documented here". The complete set is `@Self`, `@meta`, `@scope`.

### C145 — `@Self`
See C084. Type position only.

### C146 — `@meta` applied to a value
```groovy
    @meta(n).type.match({
```
`DESIGN.md:1075`. Call-shaped, result is field-accessed.

### C147 — `@meta` applied to `self: @Self`
```groovy
        sb.add("{} {", @meta(self: @Self).name);
        @meta(self: @Self).fields.loop((h, field) {
```
`DESIGN.md:365-366`. FLAG: the argument is written `self: @Self` — a `name: Type`
pair inside an argument list. Three readings, none stated:
(a) a named/labelled argument whose value is the type `@Self`;
(b) a type-ascription expression `self` ascribed `@Self`;
(c) special `@meta` syntax meaning "the type of `self`".
Compare C111, where `name: value` in an argument list is construction.

### C148 — `@scope` bound to a name
```groovy
    outer = @scope;
```
`DESIGN.md:164`. A bare `@scope` in expression position.

### C149 — `@scope` as a receiver
```groovy
    @scope.defer(() { println("goodbye") });
```
`DESIGN.md:1228`.

### C150 — mutation of a `@meta` node
```groovy
        Struct(s) => {
            s.fields.add(Field(name: "foo", value: 1));
        },
```
`DESIGN.md:1088-1090`.

---

## 14. Whole-file shapes

### C151 — `build.zen`
```groovy
build = (b :: Builder) Res<(), BuildError> {
```
`DESIGN.md:883`. A module-level function whose sole parameter is a mutable `Builder`;
preceded by a module-level data binding (C112).

### C152 — a test function
```groovy
vec_grows* = (t: Tester) Res<(), TestError> {
    v ::= t.alloc.Vec<i32>();
    v.add(1).try();
    v.add(2).try();
    t.expect_eq(v.len, 2).try();
    Ok(());
}
```
`DESIGN.md:968-974`. "no annotations" (`DESIGN.md:965`) — a test is an ordinary
exported function whose single parameter is a `Tester`.

### C153 — a bench function
```groovy
vec_add* = (bn: Bencher) Res<(), TestError> {
    bn.iter(() {
        v ::= bn.alloc.Vec<i32>();
        v.add(1);
    })
    Ok(());
}
```
`DESIGN.md:984-990`. Note `bn.iter(...)` is **not** `;`-terminated while the
following `Ok(());` is.

### C154 — `DumpAst`, four monomorphic overloads plus a generic entry
```groovy
DumpAst = (sb :: String, n: Enum) Res<(), IoError> {
    sb.add("Enum {}", n.name);
    n.fields.loop((h, field) {
        sb.add("{}: {}", field.name, field.value);
    })
}
```
`DESIGN.md:1044-1049`, with three siblings (`1051`, `1058`, `1065`) and:
```groovy
DumpAst<T> = (sb :: String, n: T) Res<(), IoError> {
```
`DESIGN.md:1074`. Five top-level bindings of one name; the generic one carries `<T>`
on the **name** (C057's form) while none carries `*`.

### C155 — `AddFoo`, a comptime type-returning function
```groovy
AddFoo<T> = (n: T) Res<T, Error> {
    @meta(n).type.match({
        Struct(s) => {
            s.fields.add(Field(name: "foo", value: 1));
        },
        _ => Err(Error("Invalid node type")),
    });
    Ok(n);
}
```
`DESIGN.md:1086-1094`.

### C156 — non-Zen blocks in `DESIGN.md`
`DESIGN.md:9-20` (a directory listing inside a bare fence), `842-855` (a
`.gitignore`, fenced as `groovy`), `857-867` (C source, fenced as `c`). These are
**not Zen** and must not be fed to the parser. Noted because `PLAN.md:148` says the
corpus contains "every code block in `DESIGN.md`" — three of them are not Zen, and
one of those is mis-fenced.

---

# AMBIGUITIES

Places where `DESIGN.md` admits two readings, or where two parts of it disagree.
Each needs a sentence added to `DESIGN.md` (per `PLAN.md:131`: "Resolve each one *in
`DESIGN.md`*, not in the parser").

### A-ALIAS — `Alias = Shape` vs a one-variant enum  *(known, unresolved)*
`DESIGN.md:32` names it and does not settle it. `PLAN.md:126-131` repeats it.
Instances in live code: `AllocError* = OutOfMemory` (C066), `TestError* = Failed(str)`
(C067), `Circle1 = AddFoo(Circle)` (C021), `op = (a: i32, b: i32) i32 { a * b }`
(C020), `json = pkg.json` (C144). All five are `Name = <thing>` with different
meanings and no syntactic marker.

### A-GEN — generic parameters sit on **both** sides of the `=`
- name side: `Vec*<T> = {..}` (`536`), `Map*<K: Eq + Hash, V> = {..}` (`581`),
  `Res*<T> = ..` (`392`), `Entry<K, V> = {..}` (`572`), `Ref*<A> = {..}` (`784`),
  `loop*<T> = (..)` (`717`), `map*<T, U> = (..)` (`735`), `find*<T> = (..)` (`739`),
  `DumpAst<T> = (..)` (`1074`), `AddFoo<T> = (..)` (`1086`).
- value side: `then* = <T>(b: bool, ..)` (`423`),
  `scale* = <T: Rect>(shape: T, ..)` (`138`), `args* = <T>(self: @Self) ..` (`473`),
  `spawn* = <A: Actor>(..)` (`475`), `realloc* = <T>(..)` (`510`),
  `free* ::= <T>(..)` (`511`), `Vec* ::= <T>(..)` (`515`),
  `Map* ::= <K, V>(..)` (`516`), `expect_eq* = <T: Eq>(..)` (`617`),
  `join* = <T>(self: @Self) ..` (`827`), `spawn* = <T>(..)` (`834`).
Types only ever use the name side; functions use both, in the same document, with no
stated difference. Either both parse, or one set of examples is wrong.
**Weak pattern, not stated as a rule:** members inside a struct body use the value
side; module-level function declarations use the name side. `scale*` (`138`) and
`then*` (`423`) break that pattern — both are module-level and both use the value
side.

### A-SEP — member separation inside a struct body
Fields are comma-separated with an optional trailing comma (C024). Methods are
separated by **nothing** (`String*` `356-357`, `Alloc*` `509-517`, `Vec*` `546-568`,
`Display*` `364-386`, `Env*` `473-475`). A field is followed by a comma even when the
next member is a method (`Rect*` `120-123`, `String*` `354`, `Vec*` `540`, `Env*`
`466`, `Tester*` `611`, `Builder*` `667`, `Thread*` `824`). A method followed by a
field never occurs. Two readings:
(a) `,` is optional everywhere and merely conventional after fields;
(b) `,` is required between fields and forbidden/optional after a member with a body.
Neither is stated.

### A-BRACE — `{` has at least four meanings
1. declaration body: `Rect* = { .. }` (C024)
2. block / function body: `{ self.width * self.height }` (C105), bare block (C104)
3. anonymous record literal as an argument: `b.lib("libsodium", { src: .., libs: .. })`
   (C114) and the impl body `Circle.impl(Rect, { width: .., height: .. })` (C137)
4. match arm list: `.match({ true => 8, false => .. })` (C089)
`DESIGN.md` never distinguishes them. (3) and (4) are both "a braced thing passed as a
call argument" and differ only in whether entries use `:` or `=>`.

### A-SEMI — statement termination is inconsistent
`;` present: `c1 = Circle1(radius: 1.0, foo: 1);` (`1157`), `foo.compute(41, bar);`
(`1194`), `Ok(());` (`370`), the whole match at `1087-1092`.
`;` absent: `Circle1 = AddFoo(Circle)` (`1156`), `json = pkg.json` (`1005`),
`op = (a: i32, b: i32) i32 { a * b }` (`1174`), `label = (..).match({..})` (`1257`),
`cap = (..).match({..})` (`561`), `sum = [0,1,2].loop(..)` (`1233`),
`Range(0, 5).loop((h, v) { .. })` (`1186`), `b.module(Path("src")).functions.loop(..)`
(`930`), `bn.iter(() { .. })` (`985`), `json_pkg = Package(..)` (`877`),
`t.join().match({..})` (`1209`).
Readings: (a) `;` is optional; (b) `;` is required unless the statement ends in `}`;
(c) `;` is required except after a trailing call-with-block. (b) fails on
`Circle1 = AddFoo(Circle)` and `json = pkg.json`; (c) fails on `foo.compute(41, bar);`.
No rule fits.

### A-TAIL — does a trailing `;` discard the value?
`{ a + b }` (`1168`) and `{ Ok(()); }` (`370`) both denote the block's value, and
`DESIGN.md:405-406` explicitly says `0;` closes a `Res<i32, E>` function. So `;` does
**not** discard. Then `self.len = self.len + 1;` and `Ok(());` (`549-550`) are two
statements where only the second is the value, with identical punctuation.

### A-RET — is the return type optional on a function with a body?
- Omitted: `started ::= (self :: @Self, ctx: Context) { .. }` (`1103`),
  `stopped ::=` (`1104`), `receive_msg = (..) { .. }` (`1109`),
  `compute = (..) { .. }` (`1116`), every closure (`1233`, `985`, `1264`).
- Written: `started* ::= (self :: @Self, ctx: Context) ()` (`801`) — the **same
  method** as `1103`, with `()`; `drop = (self :: @Self) () { .. }` (`521`);
  every other named function.
CONTRADICTION between `DESIGN.md:801` and `DESIGN.md:1103`.

### A-CLO — "never bare" vs bare closure parameters
`DESIGN.md:223`: a parameter "is written out like every other one — a name and a
type, **never bare**". But `(h, field)` (`366`), `(h, f)` (`927`), `(hd, e)` (`593`),
`(h, v)` (`1186`), `(h, i, v, acc: i32)` (`1233`) are bare or partly bare.
Reading (a): "never bare" is about `self` only, and closure parameters infer.
Reading (b): the closure examples are inconsistent with the law.
Compounded by `DESIGN.md:325`: "a closure's type is its full signature", and
`DESIGN.md:329`: "Function types must name their parameters" — types name them,
lambdas apparently need not.

### A-ANGLE — `<` is both a comparison and a generic bracket
`(i < self.len)` (`554`) against `alloc.Vec<i32>()` (`1220`) and
`env.args<Opts>()` (`1147`). `DESIGN.md` never states how `a < b > (c)` is resolved.
Compounded by `Vec<Entry<K, V>>` (`582`), which requires `>>` to split.

### A-STAR — `*` is export, multiplication, and part of `*%`
`Rect* = {..}` (`119`) / `self.width * self.height` (`123`) / `*%` (`208`).
`add*    = (v :: Vec<T>, ..)` (`237`) puts whitespace between `*` and `=`. And
`DESIGN.md:340` says `*` is *reserved* for exports, so `*T` and `*p` are excluded —
but nothing states where the export `*` may appear (after the name only? after a
name inside a generic list?).

### A-CONSTRUCT — named vs positional construction
`DESIGN.md:129-130` presents `name: value` as *the* construction form (C111), and it
is how `Circle`, `Entry`, `Field`, `Package`, `Budget` are built. But `Path("src")`,
`Range(0, 5)`, `Error("Invalid node type")`, `Foo()`, `Collector()`, `Hasher()`,
`Duration.seconds(60)` are positional (C113), and
`Path("build/{}-{}/example_zen{}", b.os, b.arch, ext)` is a format string plus
arguments. Are these constructions, or calls to functions of the same name? Not stated.
Note `Circle(Circle)` in `Shape` (`1028`) is a *variant declaration*, a third reading
of `Name(args)`.

### A-ERRTYPE — `Error` is a union alias **and** a constructor
`Error = AllocError | IoError | ArgError` (`187`, and `1139` with four members) makes
`Error` an anonymous-union alias. But `Error.NotFound` (`199`) accesses a member of
it, and `Err(Error("Invalid node type"))` (`1091`) **calls** it with a string.
Neither `NotFound` nor a string-taking constructor is declared for any member of the
union. Three incompatible uses of one name.

### A-ELIDE — `{ ... }` as a body
`add* = (self :: @Self, value: T) Res<(), AllocError> { ... }` (`226`, `236`, `237`)
and `drop = (self :: @Self) () { /* arena: .. */ }` (`521`). Reading (a): `...` is
prose elision and these snippets are not parseable programs. Reading (b): `...` is
the same token as the variadic marker (C048) and is an expression. `DESIGN.md:319`
uses `..` (two dots) in prose (`A.impl(B, {..})`, `env.out.println(..)`) and `...`
(three) in code — possibly two different elisions, possibly a typo.

### A-ENUMEND — where a brace-less enum ends
See C071. A variant list is comma-separated across lines with no terminator, and the
next declaration begins on a fresh line. If a trailing comma were permitted on the
last variant (as it is for struct fields, C024), the enum would swallow whatever
follows. `DESIGN.md` never says whether a trailing comma is legal on an enum.

### A-UNIONDECL — `|` vs `,` at declaration level
`Error = A | B | C` (`187`) declares an anonymous union alias; `Shape = A(x), B(y), C`
(`1027`) declares a nominal enum. Both are sum types; the only difference is the
separator, and `DESIGN.md:181` describes `A | B` as "a structural enum, not a new kind
of type". Never presented as two declaration syntaxes, but that is what they are.

### A-INDEX — `buf[i]` exists only in prose
C118. Indexing appears once, at `DESIGN.md:210`, outside any code block. Every code
example uses `.get(i)`. Is `[]` an operator in the grammar?

### A-AMP — `&` exists only in an ERROR example
C119. `&c.width` at `DESIGN.md:107` is the sole `&`. The comment marks it an error for
an unrelated reason (computed field), implying `&` parses. Nothing else says so, and
`DESIGN.md:340` says raw pointers are `Ptr<T>`.

### A-META-ARG — `@meta(self: @Self)`  *(settled — M1, `docs/design_meta.md`)*
C147. A `name: Type` pair as a call argument, occurring twice (`365`, `366`) and
nowhere else in any argument list except construction (where the RHS is a *value*).

Settled as part of milestone M1 of `docs/design_meta.md`: `name: Type` inside
`@meta(...)` is a **labelled binding** — `@meta`-specific syntax, not a call
argument. In a call argument the RHS of `name: ...` is a value; here it is a TYPE.
The pair binds the name the reflection is about — the receiver that runtime
projections like `self.at(field)` read from — to the type whose declaration node
is returned. The parser already reflects this structurally: `Meta` carries its own
`name` and `type` fields rather than reusing an `Arg`
(`src/std/parse/parse_expr.zen:541-576`). That it occurs nowhere else in any
argument list is now the point, not a smell.

### A-VARIADIC — `args: ...`
C048. Two occurrences (`356`, `517`), never defined. Interacts with A-ELIDE.

### A-PREC — no precedence table
C130. `DESIGN.md` gives none; `TESTING.md:38` requires tests for it. The document
writes `((e.hash == h) && e.key.eq(key))` (`594`) with redundant inner parentheses,
which suggests `&&` binds looser than `==`, but that is an inference from formatting.

### A-OPS — the operator set is not enumerated
Present in code: `+ - * / % +% -% *% == < && ! &`. Absent entirely:
`> <= >= != || |` (as an operator; `|` appears only in type position), bitwise
operators, shifts, `+=`-style compound assignment, unary `-` (except in prose
`i32.MIN / -1`, `209`). No list is given anywhere.

### A-BOOLLIT — `true` / `false`
C010. They appear as match patterns (`555-556`, `562-563`, `1258-1259`) and as a
field default (`1136`). Are they literals, keywords, or the two variants of an enum
`bool`? If variants, `DESIGN.md:120`'s pattern rule (unqualified variant names) covers
them; if literals, patterns can be literals, which is stated nowhere.

### A-KEYWORDS — no reserved-word list
C013. Only `consume` is unambiguously a word-shaped operator. `type` is used as a
field name (`928`). `extern` is used as a method name (`901`). `impl`, `match`,
`loop`, `then`, `try`, `break`, `next`, `defer`, `drop`, `args` are all ordinary
identifiers in method position. A grammar must decide whether `consume` (and
`true`/`false`) are reserved, and `DESIGN.md` does not say.

### A-LEADDOT — leading-dot continuation
C131. `DESIGN.md:928-929` and `941-942` break a call chain across a line with a
leading `.`. Whether this is significant (a continuation rule) or merely formatting
depends on A-SEMI: if `;` is optional, a line beginning with `.` must be joined to
the previous line, which makes the lexer newline-sensitive.

### A-MODSIG — a module-level declaration with no body
C056, C061, C063: `then* = <T>(b: bool, f: () T) Res<T>` (`423`),
`read_cfg = (p: Path) Res<Cfg, _>` (`184`), `main = (env: Env) Res<i32, Error>`
(`188`), and the entire `loop.zen` block (`717-743`). The method table (`91-97`)
gives `= sig` the meaning "required: impl must provide it" — which is a *member*
notion. At module level there is no impl. Reading (a): these are declarations of
functions whose bodies are elsewhere/omitted for the document. Reading (b): the
`loop.zen` and `then` listings are documentation stubs, not real source.

### A-IMPLSEP — impl body member separation
C137 (`132-135`) separates entries with commas and ends with a trailing comma;
C140 (`1100-1119`) separates entries with nothing. C138 and C139 and C141 each have
a single entry, so they decide nothing. Same shape as A-SEP, one level in, and here
the two forms appear in the *same* construct.

### A-IMPLEXTRA — impl supplying undeclared names
C140: `Foo.impl(Actor, {..})` supplies `receive_msg` and `compute`, neither of which
`Actor` declares (`798-803`). `DESIGN.md:99` says an impl "supplies a value for every
field `B` declares" — it does not say whether it may supply *more*. `DESIGN.md:756`
("a behavior is any method in an Actor impl") implies yes. Sema, not syntax, but it
determines whether an impl body is a closed or open member list.

### A-FMT — `{}` placeholders are not syntax
C008. `"{} {"` (`365`) contains an unmatched brace inside a string. Purely lexical,
but worth stating: the format language is not parsed by the grammar.

### A-CORPUS — three blocks in `DESIGN.md` are not Zen
C156. `PLAN.md:148` gates on "a corpus containing every code block in `DESIGN.md`";
`DESIGN.md:842-855` is a `.gitignore` fenced as `groovy` and would fail any Zen
grammar. The gate as written is unsatisfiable unless those blocks are excluded.
