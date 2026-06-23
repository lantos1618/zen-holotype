# Zen Language Spec

This is the current-state spec for the self-hosted `zenc` compiler in this
repository. It describes behavior implemented by the code and covered by tests,
not every long-term idea in [VISION.md](VISION.md).

The strongest executable references are:

- [tests/test_build.py](tests/test_build.py) for CLI, examples, std integration,
  diagnostics, formatter, doc output, actors, and runtime behavior.
- [tests/test_traits.py](tests/test_traits.py) for trait/impl conformance.
- [tests/test_oracle.py](tests/test_oracle.py) and
  [tests/_oracle_corpus.py](tests/_oracle_corpus.py) for accepted/rejected
  language behavior through the binary oracle.
- [tests/test_resolver_oracle.py](tests/test_resolver_oracle.py) and
  [tests/test_user_imports.py](tests/test_user_imports.py) for import resolution.
- [tests/test_genjs.py](tests/test_genjs.py) for the JavaScript backend subset.
- [tests/test_primitive_boundaries.py](tests/test_primitive_boundaries.py) for
  raw primitive boundaries.

## Source Files

A Zen source file is UTF-8 text containing top-level declarations and import
heads. `//` starts a line comment. The lexer also handles nested block comments
and treats unterminated comments/strings as parse errors instead of silently
truncating valid source.

Checked user commands are:

```sh
zenc check <file.zen|project-dir>
zenc build <file.zen|project-dir> [-o out]
zenc run   <file.zen|project-dir>
zenc emit  <file.zen>
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
Box<T>*: { value: T }                      // generic struct
Opt<T>*: Some(T) | None                    // generic enum
```

`*` is a glued visibility marker on the declaration name. It is used by docs and
module export intent. Full privacy enforcement is still pending.

Function bodies return their trailing expression. `return expr` is supported as
an early return statement, but early returns inside value-position block/match
arms are rejected because they would be dropped by expression emission.

Bodyless functions are foreign declarations. The backend emits C prototypes and
the system linker supplies the body.

## Types

Implemented scalar and structural types:

```zen
i32 i64 u8 f64 bool void str
Ptr<T> MutPtr<T> RawPtr<T>
[T]
(A, B) C
Name
Name<T, U>
```

`str` is a C string pointer. `[T]` is a fat slice with a pointer and length.
Function types are parameter types for inline templates and closure arguments.

Current pointer status: the parser accepts `Ptr<T>`, `MutPtr<T>`, and
`RawPtr<T>`, but the checker/backend currently collapse them to one pointer
shape and enforce invariant pointee equality. Direction and nullability are a
language goal, not a fully enforced current guarantee.

Integer literals are context-sensitive. They fit numeric slots when in range and
default to `i32` unless the value requires `i64`. `u8 <= i32 <= i64` widening is
accepted. Explicit casts exist as intrinsics such as `to_i32`, `to_i64`,
`to_u8`, and `to_f64`.

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
```

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

Source-level branching is `.match`. `if`, `for`, and ordinary `while` are not
source syntax. The C backend may lower checked matches to C `switch`, `if`, or
ternary expressions as target details.

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
unknown variants are type errors.

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
impls that omit them.

Data structs can also own inherent methods inside their record body:

```zen
Box<T>*: {
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
Box<T>*: { value: T }
wrap<T> = (x: T) Box<T> { Box<T>(value: x) }
```

Generic functions with function-typed parameters are inline templates. Closure
arguments such as `(a, x) { a + x }` are inlined at the call site; no runtime
function pointer is emitted for that template path.

Generic inference is still growing. The current tree proves `ReplyRef<T>.send`
works generically in actor flows, but broader inference coverage remains a
roadmap item.

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

`std.internal.resolve` also exposes structured import-edge values for resolver
work:

```zen
ImportEdge*: { module: str, alias: str, namespace: bool, start: i32, next: i32 }
ProvidedSymbol*: { name: str, start: i32, next: i32, decl_start: i32, decl_next: i32, imported: bool, foreign: bool }
ModuleGraph*: { imports: [ImportEdge], symbols: [ProvidedSymbol] }
ModuleEntry*: { id: str, path: str, source: str, graph: ModuleGraph }
ModuleTable*: { modules: [ModuleEntry] }
ResolvedProgram*: { table: ModuleTable, flat: str, body_start: i64, body_end: i64 }
ParsedModule*: { id: str, path: str, source: str, body: str, graph: ModuleGraph, decls: [Decl] }
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
```

`check`/`build`/`run <project-dir>` resolve `<root>/<main>`, use `out` for
build output when `-o` is omitted, and pass `ccflags` through to `cc`.

## Memory And Ownership

The language currently exposes explicit memory primitives and library-level
ownership types:

- raw intrinsics: `@addr`, `@load`, `@store`, `offset`, `slice`, `cstr`,
  `sizeof`, `load_i64`, `store_i64`, `atomic_add_i64`, `null_ptr`;
- `std.mem.alloc`: `Allocator`, `Heap`, `Malloc`, namespace-bound
  `default`, `try_acquire`, `try_resize`;
- `std.mem.arena`: `Arena`, namespace-bound `new_in` and `try_new_in`;
- `std.core.slice`: allocator-first `buf`, `dup`, `node`, `concat`, their `_in`
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
`a.try_cell(16)`, `cell.reply(a)`, and `cell.try_reply(a)`.

Current safety status: these APIs exist and are tested, and the checker rejects
same-body local use after `Own<T>.release_in(...)`, `Rc<T>.drop_in(...)`, or
`Arc<T>.drop_in(...)`. The full model is documented in
[MEMORY_MODEL.md](MEMORY_MODEL.md). Branch-sensitive ownership flow, pointer
direction/nullability, and lifetime checking remain roadmap items.

## Errors And Results

The stdlib fast/fallible API policy is documented in
[ERROR_POLICY.md](ERROR_POLICY.md).

Zen has no exceptions and no unwinding. Fallible library APIs return values:

```zen
Result<T, E>: Ok(T) | Err(E)
Opt<T>: Some(T) | None
IoError*: NotFound | Denied | Eof | Errno(i32)
```

Callers branch with `.match`. `std.core.result` also provides sentinel-lifting
helpers such as `ok_if` and `ok_ptr`, and `panic` as an explicit abort for
invariants.

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

- `std.concurrent.coroutine`: coroutine substrate over context switching,
  with `try_spawn` / `try_spawn_in` for fallible stack/context allocation;
- `std.concurrent.runtime`: sync/async runtime and colorless `checkpoint`,
  with namespace-bound `runtime.sync` / `runtime.async` constructors;
- `std.concurrent.sched`: small scheduler, with `try_run` / `try_run_in`
  for fallible scheduler flag allocation;
- `std.concurrent.actor`: typed actor queue, `Receiver<M>`, `ActorRef<M>`,
  `ReplyRef<T>`, `ActorEngine<M>`, `ActorCell<M>`, and
  `ActorHandle<M, ActorT>`;
- `std.concurrent.cown`: owned FFI-handle examples, with namespace-bound
  `cown.buf` / `cown.try_buf` / `cown.file` / `cown.file_in` spellings.

Public code should call runtime/actor APIs rather than raw coroutine checkpoint
primitives. Actor draining checkpoints internally, while allocator parameters
only own actor queues and reply storage. Actor messages are typed enums and
receivers implement `Receiver<M>` through
`Type.impl(Receiver<M>, { receive = ... })`.

`ActorEngine<M>` owns the internal queue state. `ActorCell<M>` is the
lower-level queue wrapper: it exposes `tell(message)` for fire-and-forget sends,
drives a receiver through `await_reply`, wraps request/reply flows through
`request`, and frees the engine storage through `free`. Actor cells infer
their message type from typed destinations such as
`cell: actor.ActorCell<Msg> := actor.cell(heap.addr(), 16)`, where `actor`
is a namespace bind for `std.concurrent.actor` and `heap` may come from
namespace-bound `alloc.default()`.
`ActorHandle<M, ActorT>` is the higher-level stateful actor wrapper. A program
can create one with `actor.spawn(heap.addr(), 16, ActorState(...))`, or use
`actor.try_spawn(...)` when allocation failure should stay in the value flow.
It sends typed messages with `handle.tell(message)`, drains its owned state with
`handle.run()`, wraps request/reply flows through `handle.request(...)`, and
releases storage with `handle.free(heap.addr())`. Actor state persists across
multiple drains.
`request` creates the `ReplyRef<T>`, calls a request callback that returns the
typed message, for example `(reply) { .GetStats(reply) }`, enqueues it, drains
the receiver, awaits the reply, and releases the reply storage. The lower-level
`ask` method remains available for callbacks that need side effects before
draining. Fallible variants `actor.try_spawn`, `cell.try_reply`, and
`try_cell` return `Result` values and clean up partial allocation before
returning `.Err`.

## Backends

The C backend is the shipping/bootstrap backend. It lowers the checked AST to C
and invokes `cc` for `build`/`run`.

`compiler.genjs` is experimental; its scope is documented in
[JS_BACKEND.md](JS_BACKEND.md). It emits JavaScript for the computational
subset: arithmetic, calls, conditionals, structs as JS objects, enums as tagged
objects, slices, index, loops, recursion, block expressions, lambdas after
template lowering, and imperative statements. Raw pointer/memory primitives are
emitted as explicit `unsupported-in-js` markers rather than faked.

## Tooling

`zenc fmt [--check] <file.zen>` exists and is conservative: it preserves line
comments, block comments, strings, and char literals while normalizing brace
indentation/trailing whitespace, and is tested for idempotence. It is not yet a
full AST pretty-printer.

`zenc doc <std.mod|file.zen>` lists public declaration heads and adjacent `//`
docs. It is a first-pass docs command, not a rich documentation generator.

## Test Map

| Spec area | Primary tests |
|---|---|
| CLI build/run/check/project manifest | [tests/test_build.py](tests/test_build.py) |
| Examples | [tests/test_build.py::test_all_examples_run](tests/test_build.py) |
| Lexer/parser/bootstrap/fixpoint | [tests/test_bootstrap.py](tests/test_bootstrap.py), [tests/test_acid.py](tests/test_acid.py) |
| Accepted/rejected core language behavior | [tests/test_oracle.py](tests/test_oracle.py) |
| Crash-resistance fuzzing (malformed input) | [tests/oracle_fuzz.zen](tests/oracle_fuzz.zen) |
| Traits and impl conformance | [tests/test_traits.py](tests/test_traits.py) |
| Imports and resolver behavior | [tests/test_user_imports.py](tests/test_user_imports.py), [tests/test_resolver_oracle.py](tests/test_resolver_oracle.py) |
| Std module import coverage | [tests/test_modules_oracle.py](tests/test_modules_oracle.py) |
| JS backend subset | [tests/test_genjs.py](tests/test_genjs.py) |
| Raw primitive boundaries | [tests/test_primitive_boundaries.py](tests/test_primitive_boundaries.py) |
| Formatter and docs commands | [tests/test_build.py](tests/test_build.py) |
