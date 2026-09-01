# Zen language map

This is the short routing index for the language and its implementation. It
maps committed `main`; it does not promote worktree experiments into language
law. `DESIGN.md` remains binding.

## Authority

| Question | Authority |
|---|---|
| What does Zen mean? | `docs/DESIGN.md` |
| What is implemented, and in what stage? | `docs/PLAN.md` and `STAGE` |
| What shape should code take? | `docs/STYLE.md` |
| What proves a change? | `docs/TESTING.md` and `Makefile` |
| What does each AST node mean? | `src/AST_CONTRACT.md` |
| What syntax do editors parse? | `grammar/grammar.js` |

The tree-sitter grammar serves editors. The compiler has one independent
frontend in Zen: `src/std/lex` and `src/std/parse`.

## Compilation flow

```text
entry + root
    -> module walk (overlay, disk, imports, prelude)
    -> lexer -> parser -> one shared Ast
    -> World + memoized Checker queries
    -> ownership, layout, impl and termination walks
    -> reachable monomorphizations
    -> deterministic C99 -> C compiler
```

The formatter consumes lexer/parser spans and trivia. The LSP consumes the
same AST, build graph and checker; it does not maintain a second language
model.

| Layer | Public surface | Main implementation |
|---|---|---|
| Paths and modules | `src/zen/zen_path.zen` | `src/zen/zen_build.zen` |
| Tokens | `src/std/lex/lex.zen` | `src/std/lex/lex_*.zen` |
| Syntax | `src/std/parse/parse.zen` | `src/std/parse/parse_*.zen` |
| Tree | `src/std/ast/ast.zen` | `ast_node`, `ast_arena`, `ast_span`, `ast_id` |
| Meaning | `src/sema/sema.zen` | `src/sema/sema_*.zen` |
| C backend | `src/gen/gen_c/gen_c.zen` | `src/gen/gen_c/gen_c_*.zen` |
| Formatter | `src/fmt/fmt.zen` | `src/fmt/fmt_*.zen` |
| Language server | `src/lsp/lsp.zen` | `src/lsp/lsp_*.zen` |
| CLI | `src/zen/zen.zen` | `zen_cli`, `zen_run`, `zen_fmt`, `zen_write` |
| Standard library | `src/std/std.zen` | `src/std/*` |

Folder roots are public surfaces made from starred re-exports. A name absent
from the root is module-private.

## Surface language

- Bindings and fields use `:` for immutable/read-only and `::` for mutable.
- `*` exports a module declaration or struct member. Each re-export hop also
  needs `*`.
- A block may end in a value. Statements end in `;`; declarations do not.
- Sums use `|`. A one-variant enum needs a leading bar to differ from an alias.
- `.match` is exhaustive. `.then`, `.try()`, loops and formatting are ordinary
  library/member-shaped doors with compiler support only where required.
- There is no `if`, implicit cast, ambient allocator, ambient authority,
  operator-overload framework, `Clone`, or user-written `ref`/`val`/`iso`.
- The only `@` forms are `@Self`, `@scope` and `@meta`.
- Identifiers are ASCII. Numbers are decimal without suffixes. Escapes are a
  closed set, block comments do not nest, and malformed text is rejected
  rather than reinterpreted.

`Name = rhs` is classified from the right-hand shape: function, struct, enum,
alias, import, impl, or constant. `impl` is not a keyword.

## AST and source model

`Ast` is append-only and owns the whole compilation. Expressions, types,
patterns and blocks are referred to by typed arena IDs. Declarations, members,
statements, parameters, arguments, arms and variants are held by value in their
parent.

Every node carries a root-relative, half-open span with 1-based byte columns.
Trivia is retained. `ast_find.zen` finds arena nodes at a cursor;
`ast_named.zen` separately finds binding-site names held by value.

Parser faults are accumulated diagnostics. Recovery inserts poison and resumes
at a declaration boundary; only allocation failure travels as `Err`.

## Modules and names

A module is named by its root-relative path without `.zen`, with `/` changed to
`.`. Both of these spellings may reach one folder module:

```text
std/text.zen
std/text/text.zen
```

The resolver probes the flat path, then the folder-root path. An explicit
`--entry` is relative to the compilation root; otherwise it probes `main`, the
root basename, then `zen`. The LSP derives a compilation root by climbing
folder modules and respecting `build.zen` as root evidence.

`Build.walk` reads breadth-first from the entry, with open-document overlays
before disk. It queues each physical module once and appends every parsed
module to one AST.

`World.defs_of` searches the current module, explicit imports, then the
prelude. Locals shadow globals. Overloads are lists of definitions, not a
special namespace. Enum variants have a parallel lookup. UFCS and impl lookup
start from whole-program candidates, then filter by receiver identity.

## Types, bounds and impls

Types are canonical interned IDs: primitive, nominal named, function, union,
array, result, type variable, inference hole, or poison. Nominal identity
includes the declaration and concrete arguments. Unions and error sets are
flattened, sorted and deduplicated.

Zen has no trait declaration form. A nominal struct used as a bound is the
trait shape; `Target.impl(Bound, {...})` supplies it. The target's module owns
the impl; orphan impls are rejected. Impl-supplied fields are computed,
read-only and absent from layout. Own members win over impl members; an active
bound disambiguates
otherwise competing impl members.

Generic bodies are checked once. Calls infer an `Inst`, substitute canonical
types and record the selected declaration in the checker's memos. The C
backend emits one body per reachable concrete instantiation. A depth walk
rejects expanding instantiation chains.

## Ownership, failure and effects

- Parameters borrow. `consume` is the only move spelling.
- A moved place may be revived by assignment; a later read before revival is
  rejected. Partial moves cannot cross a `Drop` boundary.
- Drop runs exactly once, in reverse declaration order. Defers run first and
  in LIFO order. Early exits use the same cleanup path.
- `@scope` values cannot be stored, returned or captured by an escaping
  closure.
- `Res` carries recoverable failure. Traps carry program bugs such as overflow,
  division by zero and bounds failure. Errors do not convert implicitly.
- Allocation requires `Alloc`. IO, memory pages, files, time and threads flow
  from `Env` capabilities.

## C, runtime and FFI

`gen_c` consumes the same `Checker` that accepted the program. It must not
re-resolve names or re-infer types. Lowering discovers reachable functions,
members, concrete types and runtime helpers to a fixed point, then emits in a
stable order. Output may be one C file or a header plus one C unit per module.

Symbols are deterministic, length-prefixed encodings of declaration identity
and concrete type arguments. Runtime floors are requested lazily and split by
capability (`fs`, `stdin`, `clock`, `threads`, `scope`, printing and memory).

FFI is opt-in on committed main:

```text
zen build <root> --ffi --emit-c ...
```

An FFI call is a bodyless, non-generic free function whose written parameter
and result types are C-spellable. The backend emits and deduplicates a raw
same-name `extern` declaration; it does not link a library. Bodyless members
remain compiler capabilities or errors, not generic FFI.

`src/std/build/build.zen` defines the intended Zen build-file value API, but a
Zen build driver does not yet execute it.

## Tooling

The LSP currently supports full document sync, diagnostics, hover, definition,
document symbols, completion, whole-document formatting, quick-fix code
actions and full semantic tokens. A session keeps one arena-owned whole build
keyed by compilation root, entry and overlay bytes, and drops it when stale.

Definitions of globals, types, members and imported names work. Locals and
pattern binders still lack a surviving declaration span, so definition for
those names returns `null`.

The CLI exposes `build`, `fmt` and `lsp`. `zen test` is named but not yet a
driver; repository testing is still run by Make and the corpus runner.

## Gates and known boundaries

`make test` builds the self-hosted compiler, runs lint/tree-sitter parsing,
line-cap, duplicate-comment, reachable-fault and lexer-position gates, then
the corpus, must-fail and example suites. `make determinism` proves repeated
emission is stable. The stage-2/stage-3 fixpoint gate remains owed.

Known boundaries include deep actor sendability and scheduler policy, a general
comptime evaluator, nested `@meta` execution, generic methods, first-class
escaping closures, the `zen test` driver, and the full compiler fixpoint gate.
