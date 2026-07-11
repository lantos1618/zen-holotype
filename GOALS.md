# Zen Goals

North star: a **self-hosted** language with **explicit capabilities** (threaded allocators and a
`Sys` at the entry, not ambient globals), **actor-safe** concurrency (statically-checked sends +
per-actor panic isolation), and **two backends over one checked AST** — C (bootstrap) and JS
(browser/Node). The ambient-runtime experiment (`std.rt`) is *not* the direction; capabilities
are explicit, and the rt rework is "ambient-within-scope, explicit-at-boundary"
(`docs/runtime-design.md`).

Compact roadmap from the current codebase. Each goal names the gap and the check that proves it is done.

1. **Namespaces**
   - Status: namespace binds (`alloc = std.mem.alloc`, `vec = std.collections.vec`, `file = std.io.file`, ...) prefix a module's direct exports, so sibling and std modules can each export the same natural short names (`of`, `default`, `at`, `new_in`, `buf`, ...) and be used as `left.thing()` / `right.thing()` without collision. The std surface is namespace-first — `vec.of`, `maps.of`, `file.contents`, `text.at`, `num.integer(a, ...)`, `alloc.default`, `raw.of`, `arena.new_in`, `rt.sync`, `cown.buf` — with old prefixed/default-heap public spellings removed and allocator-first signatures wherever allocation happens. Imported modules can use their own namespace binds, and `zenc emit` runs the same import/namespace resolver as `build`/`run`. (Per-change history lives in CHANGELOG.md.)
   - Gap: destructuring imports still flatten/dedup by short name; namespace binds are source-text rewriting, not the final AST/symbol-table module system.
   - Done when: modules/types can export natural same short names without import collisions and resolver tests prove those names coexist.

2. **Generic Method Inference**
   - Status: `ReplyRef<T>.send` is generic; actor demo and a trait-impl match-arm regression prove it. Match-arm payload bindings now participate in return-type inference, so unannotated locals can infer generic receiver method returns such as `Box<str>.get()` from enum payloads in first and non-first arms. Enum match expression arms now reject the concrete C-unsafe string/non-string result mismatch before C emission.
   - Next: broaden inference coverage beyond actor replies and move match result typing toward a real common-type rule instead of first-arm result typing.

3. **Formatter**
   - Status: `zenc fmt [--check] <file>` exists; the first formatter preserves line comments, block comments, strings, char literals, and braces inside comments/literals, normalizes brace indentation/trailing whitespace, is idempotent, and has fixture tests.
   - Gap: formatter is still conservative line/brace formatting, not an AST-aware pretty-printer for the full language style.
   - Done when: `zenc fmt <file>` is idempotent, preserves comments, has fixture tests, supports check mode, and covers the full syntax/style policy.

4. **Diagnostics**
   - Status: CLI diagnostics render `error[kind]`, a human message, mapped source line/column, a source marker, and a hint for undefined names, arity errors, arg-type errors, return-fit errors, assign-fit errors, trait conformance errors, and ownership errors. The checker exposes the CLI-compatible `CheckDiagnostic { code, kind, source_offset, span_width, count, message, hint }` and first-class `Diagnostic { code, kind, span: SourceSpan, count, message, hint }` values via `diagnostic_from_source` and module diagnostic helpers, while preserving the older packed-kind oracle entrypoints; binary expressions carry source operator offsets so `main = () i32 { 1 < 2 }` reports `return-fit` at the `<` instead of falling back to a positionless diagnostic.
   - Gap: user-file line/column mapping is still assembled in the C CLI, and richer multi-diagnostic flows are not yet threaded through the validation pipeline.
   - Done when: undefined names, type errors, arity errors, and trait errors are represented as stable diagnostic values and render precise spans plus useful text.

5. **AST Import Resolution**
   - Status: `std.internal.resolve` exposes structured resolution data — `ImportEdge` values via `import_edges`, source-spanned `ProvidedSymbol` values via `provided_symbols`, a transitive `ModuleTable`, and `resolve_parsed_program` building a `ParsedProgram` whose `ParsedModule`s carry original source, graph, and parsed declarations. The checked loader consumes those edges and tables for dependency loading, import-head validation, and namespace-bound module loading, and `check_parsed_program` validates the root module against a graph-built import library (`root_link_decls`) without reparsing the flat program. Resolver diagnostics preserve original user source spans, and the internal scans use the public loop-handle style, with large-source regressions proving the call stack does not grow per token, line, symbol, or edge. (Per-change history lives in CHANGELOG.md.)
   - Gap: the C CLI still runs parse/check through `resolve_program(...).flat`; graph-linked checking currently covers the root module's direct import signatures, but full validation has not yet switched to a symbol-table/module-world resolver for every module body.
   - Done when: imports resolve through a module graph/symbol table, resolver tests pass, and positions still point to original files.

6. **Result/Error Policy**
   - Status: [ERROR_POLICY.md](ERROR_POLICY.md) documents the current fast/fallible naming rules and the `std.mem`, `std.core.slice`, `std.text`, `std.collections`, `std.concurrent.actor`, `std.concurrent.coroutine/sched`, `std.concurrent.cown`, and `std.io` surfaces. Tests cover allocator null lifting, arena backing allocation, namespaced ownership `try_new_in`, trace `try_tracked_in` plus `try_root_in`/`try_collect_in`, ownership/trace allocator paths, slice buffer/copy/node/concat result paths, text/string result paths, strict `try_parse_int` `Ok`/`NoDigits`/`Trailing`/`Overflow` result paths, Vec and Map fallible growth, iter map/filter result paths, actor cell/reply allocation cleanup, stateful actor `spawn` cleanup, coroutine spawn allocation cleanup, scheduler flag allocation failure, cown buffer/file wrapper allocation failure, and file I/O result paths.
   - Gap: the policy is still convention plus tests; effects/ownership are not checker-enforced.
   - Done when: `std.mem`, `std.text`, `std.collections`, and `std.io` document fallible vs fail-fast APIs and test both paths.

7. **Memory Safety Rules**
   - Status: [MEMORY_MODEL.md](MEMORY_MODEL.md) documents the current model; allocator-threaded tests cover arena backing storage, fallible ownership constructors, and internal AST declaration buffers; `zenc check` rejects same-body local use after `Own<T>.release_in(...)`, `Rc<T>.drop_in(...)`, or `Arc<T>.drop_in(...)` with precise ownership diagnostics.
   - Gap: no full branch-sensitive ownership, lifetime, pointer-direction, or nullability checker yet.
   - Done when: the model grows from the current local consume rule into the full pointer/ownership safety policy and tests cover representative invalid lifetime patterns.

8. **Package Manifest**
   - Status: `zenc check/build/run <project-dir>` reads `zen.toml` with `package`, `root`, `main`, optional `out`, and `ccflags` build options. A committed fixture project under `tests/fixtures/project/manifest_demo` proves `check`, `run`, and `build` against a real manifest tree.
   - Gap: no dependency graph, package registry, build profiles, or richer option model yet.
   - Done when: `zen.toml` declares package roots/options, fixture projects build from it, and package-level options/dependencies are tested.

9. **Tooling**
    - Status: `zenc fmt` exists; `zenc doc <std.mod|file.zen>` lists public declaration heads and adjacent `//` docs. Tests now assert docs for formatter, actor/concurrency, memory, collections, strict text parsing, file I/O `Result` APIs, and local source files.
    - Gap: no LSP, package tooling, or rich docs generator yet; formatter/doc output are still first-pass tools.
    - Done when: `zenc fmt` and `zenc doc` are covered by tests, and public std declarations can be listed with useful types/docs.

10. **Language Spec**
    - Status: `SPEC.md` covers current syntax, declarations, traits, generics, imports, memory, errors, concurrency, backends, tooling, and links each area to tests.
    - Gap: the spec is current-state documentation, not yet a rigorous versioned language standard with grammar and normative acceptance/rejection language.
    - Done when: spec covers syntax, declarations, traits, generics, imports, memory, errors, concurrency, and links to tests.

11. **Actor Demo Polish**
   - Status: `ActorEngine<M>` hides the raw system state, `ActorCell<M>` remains the lower-level wrapper for `tell`, `request`, `ask`, `await_reply`, and `free`, and `ActorHandle<M, ActorT>` now owns allocator-backed actor state plus its queue with receiver-scoped `tell`, `run`, `request`, `ask`, and `free` methods. `actor_demo.zen` uses namespace-bound `alloc.default()` and `actor = std.concurrent.actor`, builds a generic `ChatRoomHandle<A>` with `actor.spawn(...)`, stores the allocator pointer once in that handle, sends typed chat operations through `room.join(...)` / `room.say(...)`, and asks for `ChatStats` with `room.stats()` through `ReplyRef<ChatStats>` rather than exposing reply construction or drain/await ordering. The demo asks once after Alice joins and again after Bob joins/posts, proving actor state persists across multiple drains and that generic replies can carry a structured value instead of an actor-specific integer wrapper. Actor draining checkpoints through `std.concurrent.runtime`, keeping the raw coroutine primitive inside the runtime/coroutine substrate, and `ActorHandle.request` / `ask` now release reply storage through `ReplyRef.await` instead of duplicating raw reply-buffer reads. Setup no longer needs a type-witness message, visible raw `ActorSystem`, imported `actor_*` helpers, standalone reply construction, named request shims, wrapper refs, direct `cell` constructor imports, or allocator threading through every room operation in `main`. Actor allocation is `Result`-shaped — `actor.cell`, `cell.reply`, and stateful `actor.spawn` return `Result` value paths for recoverable setup failure (no separate `try_*` doubling) — and namespace regression tests prove `actor.cell` / `ActorCell.request` can coexist with another module exporting `cell`, while `actor.spawn` can coexist with the coroutine substrate's own names.
   - Gap: broader actor spawning/scheduling ergonomics can still improve.
   - Done when: the demo remains runnable, hides queue plumbing, and no longer needs type-witness seed ceremony, manual reply allocation, or repeated allocator arguments in `main`.

12. **Capability entry (Sys) & explicit runtime**
   - Status: `main = (sys: Sys) i32` is accepted alongside `main = () i32`; the compiler emits a
     niladic `zen_main` trampoline that feeds the user body `std.sys.root()`, so the C boundary is
     byte-identical. `std.sys` bundles narrow capabilities (`Writer`, process `Allocator`, `Env`,
     `Clock`, `Fs`) built for attenuation. This is the explicit-capability alternative to the
     ambient runtime (`std.rt`), which is being reworked rather than adopted.
   - Gap: `Writer.write` still returns `i64` and swallows `write(2)` errors; the print/IO spine is
     not yet `Result`-shaped (Sys phase 2, design in `docs/runtime-design.md`). The
     ambient-rt rework (ambient-within-scope, two-memory scratch/shared split) is unresolved.
   - Done when: the print spine returns `Result` behind a `Writer` capability, and the runtime
     story is settled as explicit-at-boundary with the escape checker enforcing scope lifetimes.

13. **Second backend / browser (JS)**
   - Status: `compiler.genjs` walks the same post-mono AST and emits JavaScript over
     `bootstrap/zenrt.js`; driven by `zenc emit-js` and `zenc build --target js`. `std.web.dom`
     exposes the browser DOM as typed Zen. Proves one checked AST, many emitters.
   - Gap: the JS backend covers the computational subset — full i64 / 64-bit bitwise (BigInt) and
     scalar aliasing through `MutPtr<i32>` (boxed refs) are deferred; no LLVM backend yet.
   - Done when: the JS target runs the example corpus and the deferred i64/aliasing cases are
     closed or explicitly scoped out.

14. **Actor API convergence**
   - Status: typed actors ship as two surfaces. `std.concurrent.actor` is cooperative — `send`
     enqueues into the mailbox and `run`/`request`/`ask` drain it synchronously inline on the
     calling thread, with blocking request/ask replies. `std.concurrent.pool_actor` runs typed
     actors in parallel on `std.concurrent.pool` via a per-(M, ActorT) dispatch trampoline. The
     end state is ruled in `docs/runtime-design.md`: run-to-completion behaviors, no blocking
     request/ask, cancellation as a message, and spawning through a `Spawner` Sys capability
     (planned).
   - Gap: two APIs with different scheduling semantics (inline drain vs pool-parallel), and the
     coroutine/checkpoint substrate is still shipped even though the runtime-design ruling
     retires it.
   - Done when: one typed spawn surface schedules on the pool, blocking `request`/`ask` and the
     coroutine substrate are retired, and the demos run with unchanged semantics on the merged
     surface.

Priority: generic inference, namespaces, formatter, actor demo, AST imports, Result policy, diagnostics, memory rules, manifest, tooling, spec, capability entry / explicit runtime (Sys phase 2), JS/browser backend polish, actor API convergence.
