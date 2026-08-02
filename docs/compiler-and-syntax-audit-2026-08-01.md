# Zen compiler and syntax audit — 2026-08-01

> **Snapshot note.** The detailed findings preserve the broken baseline that was audited. The
> remediation table below records the current result after repair. The workspace is still heavily
> modified, but the source, generated bootstrap seed, and executable now reach a byte-identical
> fixpoint and the complete repository harness passes.

**Scope.** The language surface in `docs/SYNTAX.md` and `docs/SPEC.md`; parsing, checking,
lowering, formatting, C emission, JS emission, bootstrap/self-hosting, and the regression corpus.

**Method.** Findings came from reading the specification and implementation, running small Zen
programs, exercising saved reproducers, comparing `check` with `run`, and comparing the C and JS
backends. Marks used throughout:

- **[V] Verified** — directly reproduced in the current workspace.
- **[E] Evidence-backed** — a minimal reproducer or explicit implementation note exists in-tree.
- **[D] Design judgment** — the behavior may be intentional, but it creates a concrete usability,
  maintenance, or language-coherence cost.

Priority means:

- **P0** — crash, silent miscompile, unsound accepted program, or broken release gate.
- **P1** — semantic instability, formatter damage, major syntax ambiguity, or missing regression gate.
- **P2** — usability/design debt that should be resolved before calling the language stable.

---

## Remediation update

Repair work completed on 2026-08-01. Verification ended with `make harness` reporting
`zen harness: ALL PASS`, including value/verdict tests, module loading, C/JS regressions, build and
diagnostic cases, formatter semantic round trips, boundaries, fuzzing, LSP, the standard-library
surface, leak checks, and bootstrap fixpoint.

| ID | Current status | Repair or remaining boundary |
|---|---|---|
| C01 | **Fixed** | Rebuilt the seed through the self-hosted path and proved a byte-identical fixpoint. |
| C02 | **Fixed** | Parser depth is bounded; the exact 640-term call-argument ladder rejects cleanly and is regression-tested. |
| C03 | **Fixed** | Literal and discarded-enum match subjects are bound once on C and JS, in value and statement positions. |
| C04 | **Partial** | Direct and local-alias allocation provenance is enforced. Fields, returns, and generic/interprocedural provenance require the nullability design decision below. |
| C05 | **Fixed** | Only `() i32` and `(Sys) i32` entry points are accepted; byte-zero diagnostics span `main` correctly. |
| C06 | **Fixed** | Typed pointee information survives `offset`; `load` checking and C emission now agree. |
| C07 | **Partial** | Audited `sizeof`, scalar-address, bounds, panic, and integer-width divergences are fixed and gated. Unsupported aggregate linear-memory slices now fail loudly, but rejection still occurs at JS runtime rather than before artifact emission. |
| C08 | **Fixed** | Each module is parse-preflighted within its own byte region; unterminated input cannot bleed into an import. |
| C09 | **Fixed** | Character width and `\xNN` escapes are validated with positioned `invalid-literal` diagnostics. |
| C10 | **Fixed** | Flat statement/declaration sequences no longer consume nesting depth; 400 flat declarations are accepted. |
| C11 | **Fixed** | Bodyless generic parameters are preserved, multi-payload enum meaning round-trips, and the whole accepted corpus is idempotent and emit-equivalent. |
| C12 | **Fixed for audited reproducers** | The crash, main ABI, typed-load, null-alias, lexer-boundary, literal, statement-cap, match, and JS cases are now ordinary harness regressions. |
| C13 | **Partial** | Implementation, seed, tests, and this audit agree again. Broader syntax/status prose still depends on the language-compatibility decision below. |
| S07 | **Fixed** | Any literal or boolean arm after `_` is rejected as unreachable. |
| S01-S06, S08-S12 | **Decision required** | These are language-design choices, not safe mechanical fixes. They were intentionally not changed underneath existing programs. |

Additional failures found during repair were also closed: EOF diagnostics now anchor before trailing
layout, formatter shell tests quote backticks safely, current formatting call chains no longer
heap-promote borrowed temporary slices (the 12-example leak sweep is clean), `std.argparse` uses the
current carried-string surface, and the repaired UFCS-on-match case is accepted by the matrix.

The two decisions that block further automatic work are:

1. **Nullability:** conservatively reject every unchecked allocation that escapes through a field,
   return, or unknown/generic call, or add nullable pointer/provenance information to the type system.
2. **Syntax compatibility:** migrate compatibly with deprecations, or make an immediate syntax break
   for explicit declarations, control flow, traits, imports/exports, foreign linkage, and field defaults.

## 1. Verdict

Zen has a promising small core: expressions, trailing values, records, enums, generics, UFCS, and
value matching fit together well. The problem is not that the language is unconventional. The
problem is that it makes important semantic categories **implicit**.

Today the meaning of source can depend on:

- whether a name already exists somewhere in scope;
- whether whitespace contains a newline;
- whether a function declaration happens to have a body;
- whether a record-shaped declaration is constructed or implemented later;
- whether a method-looking name is recognized specially by the compiler;
- which backend is selected;
- whether the formatter has rewritten the program.

This produces one root diagnosis:

> **Zen is optimizing for fewer keywords at the cost of context-sensitive meaning. It is concise
> locally, but expensive globally.**

At the audited baseline the compiler was not trustworthy enough to freeze this syntax. The concrete
failures named above have now been repaired or bounded as recorded in the remediation table. Syntax
stabilization still waits on the explicit language-design choices; the remaining C04 and C07
boundaries must not be mistaken for fully closed type-system/backend support.

---

## 2. Executive finding table

| ID | Priority | Area | Finding | Evidence |
|---|---:|---|---|---|
| C01 | P0 | Bootstrap | Current source does not reproduce a working self-hosted compiler | [V] |
| C02 | P0 | Parser | Operator ladder inside a call argument can exhaust the C stack | [V][E] |
| C03 | P0 | Lowering | Literal-match subjects can be evaluated more than once | [V][E] |
| C04 | P0 | Safety | Allocation-null checking is defeated by one alias | [V][E] |
| C05 | P0 | Entry point | `main` return type is not enforced; runtime observes garbage | [V][E] |
| C06 | P0 | Checker/emitter | `check` accepts an untyped load that emitted C cannot compile | [V][E] |
| C07 | P0 | JS backend | Supported-looking programs silently behave differently from C | [E] |
| C08 | P1 | Lexer/modules | Unterminated input can bleed into an imported module | [V][E] |
| C09 | P1 | Literals | Empty, multibyte, and malformed escaped characters are accepted or fabricated | [E] |
| C10 | P1 | Parser | A flat block of about 400 statements is rejected as if deeply nested | [V][E] |
| C11 | P1 | Formatter | Formatting can remove generic or enum syntax and change meaning | [E] |
| C12 | P1 | Tests | Saved crash and miscompile reproducers are deliberately outside normal gates | [V][E] |
| C13 | P1 | Project state | `STATUS`, `SPEC`, syntax docs, seed, and implementation contradict one another | [V] |
| S01 | P1 | Bindings | `=` means declaration or assignment according to surrounding scope | [V][D] |
| S02 | P1 | Bindings | Mutability syntax also acts as the only reliable shadowing syntax | [V][D] |
| S03 | P1 | Control flow | Compiler constructs masquerade as ordinary method calls | [V][D] |
| S04 | P1 | Type system | Traits are inferred from record shape and later usage | [E][D] |
| S05 | P1 | Grammar | Statement/call meaning depends on whitespace and line placement | [V][E][D] |
| S06 | P1 | Initialization | Missing required-looking fields silently become zero | [V][E][D] |
| S07 | P1 | Matching | Arms after `_` are accepted even though unreachable | [V] |
| S08 | P2 | Modules | Imports and exports resemble assignment and operators | [D] |
| S09 | P2 | FFI | Absence of a function body silently grants foreign/linkage meaning | [V][D] |
| S10 | P2 | Strings | Construction and interpolation depend on compiler magic and source names | [E][D] |
| S11 | P2 | Enums | `|` is both the enum separator and bitwise OR | [V][D] |
| S12 | P2 | Intrinsics | `@` exposes compiler substrate as ordinary language surface | [D] |

---

## 3. Compiler findings

### C01 — the self-hosting claim is not true for this snapshot **[V] — P0**

The self-build/fixpoint path currently fails with at least 129 errors around calls such as
`a.String(...)`. The checked-in C seed and the current Zen source no longer agree about the string
surface.

This is more than a stale generated file. Self-hosting is the trust anchor for a bootstrapped
compiler: the committed seed must be able to build the current source, and that result must be able
to reproduce itself. Until that gate is green, results from the old `./zen` executable can describe
the old language while the source describes a new one.

**Required fix:** establish one canonical generation sequence, rebuild the seed, and require a
byte-identical second generation in the default integration gate. Do not mark bootstrap “shipped”
while this fails.

### C02 — operator ladder in a call argument crashes the compiler **[V][E] — P0**

A long addition chain inside a call argument exhausts the compiler's C stack:

```zen
f = (x: i32) i32 { x }
test* = () i32 { f(1 + 1 + 1 + /* ... about 640 terms ... */ + 1) }
```

The saved reproducer reports a clean parse error at roughly 620 terms and a deterministic
segmentation fault at roughly 640 terms on the default 8 MiB stack. Raising the stack limit removes
the crash, confirming unbounded parser recursion.

Evidence:

- [`parse_call_arg_operator_ladder_segv.zen.txt`](../tests/fixtures/zen/fuzz-repro/parse_call_arg_operator_ladder_segv.zen.txt)
- [`parse_call_arg_operator_ladder_segv.NOTES.txt`](../tests/fixtures/zen/fuzz-repro/parse_call_arg_operator_ladder_segv.NOTES.txt)

The existing deep-input gate tests bare operator ladders and nested calls separately, but not their
crashing combination.

**Required fix:** make expression parsing iterative or charge every recursive descent against one
real depth budget. Add this exact shape to the always-run crash-resistance suite.

### C03 — match subjects are not guaranteed to run exactly once **[V][E] — P0**

Some literal matches lower the subject into each comparison instead of first storing it in a hidden
temporary. A subject with a side effect can therefore run once per attempted arm. Discarded enum
matches have the same class of risk.

That violates the normal meaning of:

```zen
next().match({
    1 => first(),
    2 => second(),
    _ => other(),
})
```

The program appears to classify one value, but can call `next()` more than once. The open problem is
also recorded in `docs/STATUS.md` under evaluate-once lowering.

**Required fix:** every match form must bind its subject once, before arm selection, in both value
and statement position and on both backends.

### C04 — null-allocation enforcement stops at an alias **[V][E] — P0**

The checker rejects a directly consumed nullable allocation:

```zen
p = malloc(64)
p.slice(1)
```

But introducing a local alias allows the same unsafe use. Struct fields and wrapper functions also
launder the fact that the value came from a fallible allocation. Under forced allocation failure,
the accepted program reaches a null-pointer panic.

Evidence:

- [`alloc_null_check_control_direct.zen.txt`](../tests/fixtures/zen/fuzz-repro/alloc_null_check_control_direct.zen.txt)
- [`alloc_null_check_bypassed_by_alias.zen.txt`](../tests/fixtures/zen/fuzz-repro/alloc_null_check_bypassed_by_alias.zen.txt)
- [`alloc_null_check_bypassed_by_alias.NOTES.txt`](../tests/fixtures/zen/fuzz-repro/alloc_null_check_bypassed_by_alias.NOTES.txt)

**Required fix:** nullability must be a stable property of the value/type and survive assignment,
fields, returns, and generic substitution. A syntax-pattern check at the original call is not a
safety rule.

### C05 — `main` has an unchecked ABI contract **[V][E] — P0**

The compiler accepts entry points returning `void`, `bool`, `f64`, and `StringView`, while the C
runtime calls `zen_main` as an integer-returning function. The process exit status then comes from
the wrong return register or the low byte of unrelated data.

Observed examples include:

| Declared result | Observed status |
|---|---:|
| `void` | 3 |
| `bool` | 1 |
| `f64` | 3 |
| `StringView` | 199 |
| `i32` | correct |

Evidence:

- [`main_void_exit_status_garbage.zen.txt`](../tests/fixtures/zen/fuzz-repro/main_void_exit_status_garbage.zen.txt)
- [`main_return_type_exit_status.NOTES.txt`](../tests/fixtures/zen/fuzz-repro/main_return_type_exit_status.NOTES.txt)

**Required fix:** validate the exact supported entry-point signatures before emission. The backend
must never silently bridge an incompatible user signature to the runtime ABI.

### C06 — the checker and C emitter disagree about an untyped load **[V][E] — P0**

This program passes `zen check`:

```zen
x: i32 = 5
p = x.addr()
println(load(offset(p, 0)))
```

But `zen run` emits a call to `println_void` with an argument, and the C compiler rejects it. The
`offset` operation has erased the pointee type; resolution falls through to the zero-argument
printer without reporting a Zen error.

Evidence:

- [`check_accepts_untyped_load_then_c_fails.zen.txt`](../tests/fixtures/zen/fuzz-repro/check_accepts_untyped_load_then_c_fails.zen.txt)
- [`check_accepts_untyped_load_then_c_fails.NOTES.txt`](../tests/fixtures/zen/fuzz-repro/check_accepts_untyped_load_then_c_fails.NOTES.txt)

**Required fix:** `check` must prove every expression has a backend-emittable type. Either preserve
the pointer element type through `offset`, require an explicit typed cast, or reject the load.

### C07 — the JS backend silently changes program meaning **[E] — P0**

A differential run over 241 real programs found four cases where C and JS both exited successfully
but printed different results. The structural issue is worse than four individual bugs: the JS
backend does not reject unsupported memory operations, so unfinished stubs produce plausible but
wrong answers.

Confirmed classes include:

1. `sizeof(T)` is effectively always 8 in JS.
2. `addr()` of a scalar behaves like the scalar value, so stores update a copy rather than the
   original variable.
3. Raw `@addr`/`@load` inherits the same false aliasing model.
4. Byte-level string scanning over JS linear memory disagrees with C.
5. Slice indexing lacks C-equivalent bounds enforcement.
6. Panic/unwind paths refer to unavailable runtime behavior.

Evidence:

- [`js_backend_divergences.NOTES.txt`](../tests/fixtures/zen/fuzz-repro/js_backend_divergences.NOTES.txt)
- [`js_addr_is_identity_divergence.zen.txt`](../tests/fixtures/zen/fuzz-repro/js_addr_is_identity_divergence.zen.txt)
- [`js_sizeof_always_8.NOTES.txt`](../tests/fixtures/zen/fuzz-repro/js_sizeof_always_8.NOTES.txt)
- [`js_slice_index_no_bounds_check.NOTES.txt`](../tests/fixtures/zen/fuzz-repro/js_slice_index_no_bounds_check.NOTES.txt)
- [`js_panic_unwind_undefined.NOTES.txt`](../tests/fixtures/zen/fuzz-repro/js_panic_unwind_undefined.NOTES.txt)

**Required fix:** either implement a semantic memory model for JS or reject every unsupported
surface before producing output. “Experimental” may mean incomplete; it must not mean silently
incorrect.

### C08 — malformed source can bleed into an imported module **[V][E] — P1**

An unterminated string or brace in one source unit can cause scanning to continue into the
concatenated text of an imported module. The resulting error can point at the wrong module or allow
bytes from the next unit to terminate a construct begun in the first.

Evidence:

- [`lex_unterminated_string_bleeds_into_import.zen.txt`](../tests/fixtures/zen/fuzz-repro/lex_unterminated_string_bleeds_into_import.zen.txt)
- [`lex_unterminated_brace_bleeds_into_import.zen.txt`](../tests/fixtures/zen/fuzz-repro/lex_unterminated_brace_bleeds_into_import.zen.txt)
- [`lex_bleed.NOTES.txt`](../tests/fixtures/zen/fuzz-repro/lex_bleed.NOTES.txt)

**Required fix:** lex each module within a hard byte span. EOF for one module must be EOF for its
lexer, even if the resolver stores several modules in one backing buffer.

### C09 — malformed character syntax can fabricate values **[E] — P1**

The current parser has accepted or reinterpreted empty characters, multibyte characters where one
byte is expected, invalid hex escapes, and duplicate boolean labels. These should be positioned
source errors, not values manufactured by fallback parsing.

`docs/STATUS.md` records this class against `parse_atom`, `lex::char_end`, and
`parse_match::bool_close`.

**Required fix:** define the character domain precisely, validate the full token, and reject invalid
escapes before AST construction. Add negative fixtures for every malformed form.

### C10 — a flat statement list consumes the nesting budget **[V][E] — P1**

A block with 395 ordinary statements checks, while a block with 400 is rejected. The parser uses
the same cap intended to bound recursive nesting as a budget for a flat list.

Evidence:

- [`parse_stmt_count_cap_overrejects.zen.txt`](../tests/fixtures/zen/fuzz-repro/parse_stmt_count_cap_overrejects.zen.txt)
- [`parse_stmt_count_cap_overrejects.NOTES.txt`](../tests/fixtures/zen/fuzz-repro/parse_stmt_count_cap_overrejects.NOTES.txt)

**Required fix:** parse statement sequences iteratively. Depth accounting should measure nesting,
not program length.

### C11 — formatting is not semantics-preserving **[E] — P1**

Known formatter failures include removing generic parameters from bodyless signatures and losing
multi-payload enum syntax. A formatter that changes the typed program is a compiler correctness bug,
not cosmetic debt.

The project has a strong semantic round-trip harness, but these forms remain listed as open in
`docs/STATUS.md`.

**Required fix:** formatting must satisfy all three properties:

1. formatted source reparses;
2. formatting is idempotent;
3. original and formatted source produce the same typed/lowered meaning.

### C12 — saved regressions are not regression tests **[V][E] — P1**

The reproducers under `tests/fixtures/zen/fuzz-repro` deliberately use the extension `*.zen.txt` so
normal formatter and fixture globs do not consume them. No regular harness references the named
crash, null-alias, bad-main, checker/emitter, lexer-bleed, or statement-cap reproducers.

The reason for excluding malformed input from ordinary success suites is valid. The missing piece is
a dedicated negative/crash suite that runs them with their expected verdicts.

**Required fix:** add a manifest-driven regression harness with expectations such as:

- rejects cleanly with a specific Zen diagnostic;
- does not crash or hang;
- `check` and emission agree;
- C and JS agree, or JS rejects before emission;
- forced OOM produces a checked error rather than a null dereference.

### C13 — the project has multiple conflicting sources of truth **[V] — P1**

Examples from this snapshot:

- `docs/STATUS.md` says self-hosting is shipped while the self-build gate fails.
- `docs/SYNTAX.md` says compound assignment does not exist, but `x += 2` compiles and runs.
- `docs/STATUS.md` still lists compound-assignment double evaluation as open, while the current
  implementation/probe evaluates the indexed place once.
- `docs/SPEC.md` says an annotated mutable global is not a top-level form, while the current checker
  accepts `counter :: i64 = 0`.
- the current Zen source and committed bootstrap seed disagree about `a.String`.

**Required fix:** choose one canonical language version per commit. Specification conformance,
bootstrap fixpoint, syntax examples, and status-ledger checks should be gates, not manual cleanup.

---

## 4. Syntax findings

### S01/S02 — declaration, assignment, mutability, and shadowing are entangled **[V][D] — P1**

Zen currently uses four closely related forms:

```zen
x = value        // constant declaration, but only if x is not already in scope
x: T = value     // annotated constant declaration
x ::= value      // mutable declaration
x :: T = value   // annotated mutable declaration
```

The first form is contextual. If `x` already exists, it is assignment instead of declaration:

```zen
x = 1
y = {
    x = 2        // attempts to assign the outer x; it does not shadow
    x
}
```

To shadow the global, the programmer must write:

```zen
x = 1
y = {
    x ::= 2      // mutable marker also forces a new local
    x
}
```

Parameters add another exception: they can be assigned without being declared mutable.

This creates several problems:

- a declaration can become an assignment when a distant import/global is added;
- immutable shadowing is impossible in an important case;
- `::` means both mutability and “this is definitely a declaration”;
- parameter mutability is invisible;
- refactoring a name can change binding behavior.

The contextual rule is documented directly in
[`src/compiler/astops.zen`](../src/compiler/astops.zen), including the admission that a constant
local cannot shadow a global.

**Recommended direction:** use explicit declaration forms and make assignment unambiguous:

```zen
let x = 1
let mask: i64 = 255
var count = 0
var total: i64 = 0
count = count + 1
```

The exact words are negotiable. The important invariant is: **a declaration is always visibly a
declaration, and `=` after declaration is always assignment.**

### S03 — control flow pretends to be library dispatch **[V][D] — P1**

Zen replaces familiar control-flow syntax with method-looking forms:

```zen
ready.then({ start() })
ready.then({ value_when_true }, { value_when_false })
value.match({ ... })
items.loop((item) { ... })
read_value().or_return()
```

These do not form one honest abstraction:

- `.then` changes role with argument count: one-way effect versus value selection;
- `.match` is syntax with exhaustiveness and pattern rules, not normal method dispatch;
- `.or_return` is detected by the literal function name in
  [`check_resolve.zen`](../src/compiler/check_resolve.zen) and lowered specially;
- `.loop` is compiler/runtime control machinery rather than an ordinary collection API;
- `@while` remains as a lower-level control primitive.

A reader cannot tell which calls can be defined, renamed, passed around, or overridden and which
ones are effectively reserved words.

**Recommended direction:** give language control flow visible language syntax:

```zen
if ready { start() }

result = if ready { a } else { b }

match value {
    .Some(v) => use(v)
    .None => fallback()
}

for item in items { use(item) }
```

If the project deliberately rejects these spellings, it should still use explicit reserved forms
rather than calls that only look user-definable.

### S04 — a trait and a callback record can be structurally identical **[E][D] — P1**

Traits are represented as records of function-typed fields. That makes these conceptual categories
indistinguishable from their declarations alone:

```zen
// Is this interface/trait behavior?
Renderable: {
    render: (Self, Writer) Result<i64, IoError>,
}

// Or ordinary data containing a callback?
Handler: {
    run: (Context) void,
}
```

The compiler source explicitly notes that a data struct holding a function value is
shape-indistinguishable from a trait and disambiguates it by usage: constructed means data;
implemented-but-never-constructed means trait. See
[`astops.zen`](../src/compiler/astops.zen).

This makes type category dependent on distant actions and prevents a record from safely serving
both roles.

**Recommended direction:** explicit categories:

```zen
trait Renderable {
    render: (Self, Writer) Result<i64, IoError>
}

impl Renderable for Label {
    render = (self: Label, out: Writer) Result<i64, IoError> { ... }
}
```

### S05 — whitespace can change the AST **[V][E][D] — P1**

Zen separates statements contextually with whitespace, so this is accepted:

```zen
main = () i32 { x = 1 y = 2 x + y - 3 }
```

At the same time, calls, constructions, enum payloads, indexing, and method continuations have
same-line or adjacency gates. Parser comments state that a newline before `(` can turn a payload or
call into a new statement. Relevant implementation points include:

- [`parse_primary.zen`](../src/compiler/parse_primary.zen)
- [`parse_postfix.zen`](../src/compiler/parse_postfix.zen)

Consequences:

- wrapping a long line can change meaning;
- adding or removing a space before `(` can change a call into another statement;
- formatter correctness becomes unusually difficult;
- error recovery cannot rely on clear statement boundaries;
- code review must inspect invisible layout details.

**Recommended direction:** newline and/or semicolon terminates a statement, while postfix operators
follow one uniform continuation rule. Formatting whitespace should not decide whether an operation
belongs to the preceding expression.

### S06 — omitted fields look required but silently zero-fill **[V][E][D] — P1**

Given:

```zen
Point: { x: i32, y: i32 }
p = Point()
```

both fields become zero even though neither declaration contains a default. Adding a field to an
existing record can therefore leave old construction sites compiling with a new implicit value.

The checker now rejects an omitted field when zero-filling it would create a null value for a
non-null pointer, including some transitive cases. That is a useful safety patch, but it also shows
the core problem: generic zero-fill is not the same as construction.

Implementation evidence is in
[`validate/args.zen`](../src/compiler/validate/args.zen), which recursively asks whether omitted
fields zero-fill into non-null pointer types.

**Recommended direction:**

- a field without `= default` is required;
- a field with a declared default may be omitted;
- low-level code that really wants bitwise zero uses an explicit `zeroed(Point)`-style operation.

### S07 — wildcard does not close a match **[V] — P1**

The compiler accepts an arm after the catch-all wildcard:

```zen
2.match({
    _ => 7,
    2 => 9,
})
```

The result is 7 and the second arm is unreachable. Accepting it hides mistakes caused by reordering
or inserting arms.

**Recommended direction:** reject every arm after an unconditional wildcard and reject duplicate
literal/boolean labels.

### S08 — imports and exports are visually disguised **[D] — P2**

Imports look like assignment/destructuring:

```zen
{ println } = std.io.print
vec = std.collections.vec
```

Exports use an attached `*`:

```zen
run* = () i32 { ... }
```

These forms are short, but they hide module structure among value bindings and operators. The export
marker is easy to miss in review and shares visual vocabulary with multiplication, pointer-like
notation, and compound operators.

**Recommended direction:** make dependency and visibility declarations searchable and explicit:

```zen
from std.io.print import println
import std.collections.vec as vec

pub run = () i32 { ... }
```

### S09 — missing body means foreign ABI **[V][D] — P2**

A declaration such as:

```zen
sqrt = (value: f64) f64
```

automatically becomes foreign because it has no body. This is subtle because the same source can
also look like an unfinished signature, an interface requirement, or a forward declaration. Merely
adding/removing a body changes linkage and build-capability requirements.

**Recommended direction:** a bodyless function should be a neutral signature, with foreign linkage
made explicit:

```zen
extern sqrt = (value: f64) f64
```

or through an explicit native import/build declaration. The project already discusses neutral
signature/definition pairing in `docs/STATUS.md`; that direction removes the ambiguity.

### S10 — `String` combines unrelated compiler-recognized operations **[E][D] — P2**

The same apparent constructor means several things according to its first argument:

```zen
empty = a.String()
reserved = a.String(400)
message = a.String("{msg}: {0}", value, msg)
```

Formatting arguments are compiler-rewritten, and named interpolation is derived from the source
name of a variable or member in [`check_resolve.zen`](../src/compiler/check_resolve.zen). Renaming a
local can therefore alter placeholder resolution. The compiler's own use of `a.String` is also part
of the present bootstrap mismatch.

**Recommended direction:** separate operations and make named arguments data rather than recovered
source spelling:

```zen
empty = String.new(a)
reserved = String.with_capacity(a, 400)
message = format(a, "{msg}: {value}", { msg: msg, value: value })
```

### S11 — `|` carries two unrelated grammatical roles **[V][D] — P2**

`|` separates enum variants and also means bitwise OR. A leading `|` is part of the enum declaration
style, while expressions use the same token at an operator precedence level.

This is parseable by context, but it increases grammar and formatter complexity for little gain.
Positional multi-payload variants add another evolution problem: adding/reordering payloads changes
call sites without field names to explain them.

**Recommended direction:** comma/block-separated variants, with named payloads for multi-field
variants. `docs/STATUS.md` already identifies comma-separated variants as the cleanup direction.

### S12 — `@` leaks the compiler substrate into normal code **[D] — P2**

`@` marks raw intrinsics, but `@while` has also been used as control-flow substrate. This combines
unsafe memory/runtime operations and language lowering machinery in one public-looking namespace.

**Recommended direction:** reserve `@` for a small, documented unsafe intrinsic boundary. Ordinary
control flow should not depend on user-visible internal lowering primitives.

---

## 5. Documentation contradictions

These are not merely editorial mistakes. When the language is punctuation-heavy and
context-sensitive, contradictory documentation makes it impossible to know which parse is
canonical.

| Topic | Documentation says | Current behavior/source says |
|---|---|---|
| Compound assignment | `docs/SYNTAX.md`: absent | `+=` parses, checks, and runs; parser has compound-assignment paths |
| Compound evaluate-once | `docs/STATUS.md`: open P0 | current probe calls a side-effecting index once |
| Annotated mutable global | `docs/SPEC.md`: not a top-level form | checker accepts `counter :: i64 = 0` |
| Self-hosting | `docs/STATUS.md`: shipped | current fixpoint/self-build fails on `a.String` |
| Match evaluation | expressions should behave as values | literal/discarded subjects may repeat |
| Formatter | presented as a toolchain feature | known forms can change typed meaning |
| JS support | emits shared-language programs | unsupported memory behavior may emit wrong answers instead of rejecting |

The source of truth must be selected, not inferred. A practical order is:

1. executable conformance tests;
2. a bootstrap fixpoint generated from the same source;
3. the language specification;
4. the syntax guide and examples;
5. status/roadmap text.

Every layer should be checked against the one above it.

---

## 6. What should remain

The audit does not imply replacing Zen with another language. Several existing choices are worth
preserving:

- expression-oriented blocks with trailing values;
- UFCS/postfix composition where it is genuine dispatch;
- compact record and enum construction;
- exhaustive value matching;
- allocator visibility in allocating APIs;
- explicit pointer and slice capability distinctions;
- generic functions and types without a separate template language;
- avoidance of implicit heap allocation.

The goal is to make semantic categories visible while retaining the compact expression model.

---

## 7. A coherent syntax direction

This is a direction, not a proposed final specification:

```zen
from std.io.print import println
import std.collections.vec as vec

pub struct Point {
    x: i32,
    y: i32,
}

pub enum Status {
    Ready,
    Busy { jobs: i32 },
    Failed { code: i32, message: StringView },
}

trait Display {
    display: (Self, Writer) Result<i64, IoError>
}

impl Display for Status {
    display = (self: Status, out: Writer) Result<i64, IoError> {
        match self {
            .Ready => out.write("ready"),
            .Busy { jobs } => format_to(out, "busy: {}", jobs),
            .Failed { code, message } => format_to(out, "{}: {}", code, message),
        }
    }
}

extern sqrt = (value: f64) f64

pub main = () i32 {
    let origin = Point(x: 0, y: 0)
    var attempts: i32 = 0
    attempts = attempts + 1

    if attempts > 0 {
        println("started")
    }

    0
}
```

The important properties are more fundamental than the exact spelling:

- declarations are visibly declarations;
- mutability is declared consistently, including parameters;
- assignment never doubles as declaration;
- imports, exports, traits, implementations, and foreign linkage are explicit;
- control flow looks like control flow;
- missing required fields are errors;
- whitespace formatting does not change the AST;
- compiler intrinsics are visibly separate from ordinary APIs.

---

## 8. Recommended repair order

### Phase 0 — restore a trustworthy baseline

1. Make the current compiler source build with the committed seed.
2. Produce a byte-identical second-generation compiler.
3. Pin the exact commands in one default integration gate.
4. Re-run every finding in this document on that fixed point.

### Phase 1 — close silent correctness failures

1. Reject invalid `main` signatures.
2. Stop the parser stack crash.
3. Guarantee evaluate-once for every match and compound place.
4. Preserve allocation nullability through aliases, fields, returns, and generics.
5. Make `check` imply successful backend lowering or a deliberate backend rejection.
6. Reject unsupported JS operations instead of emitting wrong behavior.

### Phase 2 — make regressions permanent

1. Convert `fuzz-repro` notes into a manifest-driven negative test suite.
2. Gate parser no-crash/no-hang behavior.
3. Gate formatter typed round trips and idempotence.
4. Gate C/JS equivalence for the shared subset.
5. Gate specification examples as executable tests.

### Phase 3 — settle syntax before expanding the language

1. Separate declaration from assignment.
2. Make mutability and shadowing orthogonal.
3. Make imports, visibility, traits, impls, and foreign linkage explicit.
4. Replace compiler-magical control-flow method names with reserved syntax.
5. Define stable statement/postfix whitespace rules.
6. Require explicit field defaults.
7. Remove enum/bitwise `|` overloading.
8. Separate string construction from formatting.

### Phase 4 — declare a language version

Only after the above:

- update `SPEC.md` and `SYNTAX.md` together;
- regenerate every example and formatter fixture;
- regenerate the bootstrap seed;
- run the full harness, negative corpus, differential backend tests, and fixpoint;
- mark the syntax version as the first stable compatibility target.

---

## 9. Acceptance criteria

Zen is ready for syntax stabilization when all of these are true:

- malformed source never crashes or reads into another module;
- `zen check` success guarantees that the selected backend can emit the program;
- every expression with side effects is evaluated exactly as many times as source semantics say;
- nullable/fallible values cannot lose that fact through an alias;
- entry-point signatures are checked before emission;
- formatting is a typed semantic fixed point;
- C and JS agree for every supported feature, and unsupported JS features reject explicitly;
- every saved repro is attached to an always-run expected-result test;
- the source compiler, generated seed, specification, syntax guide, and status ledger describe the
  same language;
- declaration, assignment, mutability, imports, traits, foreign linkage, and control flow are
  recognizable from the source itself rather than inferred from distant context.

The mechanical compiler gate is now green. Compiler correctness and syntax design should still be
treated as one task for the remaining decisions: several bugs existed precisely because the grammar
hides distinctions that later phases must reconstruct.
