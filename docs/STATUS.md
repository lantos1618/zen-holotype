# Zen status and roadmap

Last full code/document audit: 2026-07-12 (base `5f33f01`); refreshed 2026-07-18 after the no-`if`
law (match guards removed), readonly-pointer write soundness, and `zenc init` landed (#493/#494).

This is the one implementation ledger. It replaces scattered goals, feature inventories, design
plans, judge reports, research notes, fix queues, and resolved repro essays. Status is derived from
source plus executable tests; old prose is not evidence.

Labels:

- **Shipped**: public path works and has executable proof.
- **Partial**: useful implementation exists with an important boundary.
- **Legacy**: live and possibly depended on, but not the preferred direction.
- **Planned**: decision/direction only; do not write examples as if it exists.

## Goals and distance

| Goal | Current result | Distance |
|---|---|---|
| Self-hosted, deterministic, small bootstrap | Zen compiler reproduces committed C byte-for-byte; C and JS runtime floors are the only hand-written target substrate. | **Shipped** |
| One understandable language structure | Records, enums, signatures, traits-as-records, UFCS, and value matches form a promising core; match guards are gone (`if` is rejected at the lexer, `error[no-if]`). Enum/bitwise `\|`, internal `@while`, evaluate-more-than-once lowering, and backend name special cases still weaken it. | **Partial — coherent direction, unsafe lowering edges** |
| Correct programs accepted; bad programs rejected before C/JS | Broad type, generic, trait, pointer, ownership, escape, diagnostic, and fuzz coverage exists. The exhaustive audit also found silent miscompiles, type/symbol identity collisions, malformed literals that are accepted, and backend-specific reinterpretation. | **Partial — broad, not yet trustworthy** |
| Errors are values, panic is explicit | `Result`, `Opt`, `.or_return`, fallible allocation/IO, and runtime checks work. Some best-effort/sentinel APIs and actor-panic cleanup gaps remain. | **Partial — good core, uneven std surface** |
| Explicit capability and memory model | `Sys`, `Writer`, `Fs`, explicit allocators, pointer kinds, owner wrappers, and actor send checks exist. Ambient `std.rt` and scope/runtime experiments still coexist. | **Partial — competing surfaces** |
| Real modules and packages | Transitive imports, privacy, namespace binds, projects, `build.zen`, local siblings, and dotted nested user modules (`{ x } = app.utils`) work; per-module signatures (`ModuleSig`) drive privacy/dup checks, diagnostics map by identity, and a differential gate (`make difftest`) pins dispatch behavior. Registered package roots, dependency metadata, library artifacts, and signature-first linking do not exist. | **Partial — modules real, packages not yet** |
| Usable standalone toolchain | `init`, `check`, `run`, `build`, C/JS emit, AST formatting, basic docs, manifests, examples, and diagnostics ship in one binary. Installation/distribution and archive/package output are missing. | **Partial — usable for the repo, rough as a product** |
| Portable multi-backend compiler | C is the bootstrap target. JS shares the frontend, but audited DOM wrapping, browser startup, width scoping, field-name, dispatch, and buffer paths are not equivalent to C. | **Partial — JS is experimental** |
| Safe, comprehensible concurrency | Real OS-thread pool, typed actors, send checks, stress tests, and panic/stack-overflow isolation work. Actor APIs are split, `Sys.Spawner` is a stub, scheduler is a global queue, cleanup/supervision are incomplete. | **Partial — engine works, model is unsettled** |
| Sub-second feedback | Warm `check`/`run` of an unchanged closure is 0.01–0.11s via the content-hash cache; cold `check` of the full compiler closure is ~5.7s (was 27s) and self-host regeneration ~7s (was 22–29s); the generated seed shrank 7.5→2.3 MB via shared generic instantiation. | **Met on the warm path; cold full-closure ~5.7s** |

## Feature, location, and report coverage

“Coverage” below is evidence quality, not a fabricated line-coverage percentage. The repository does
not instrument lines or branches. Every reported feature area is mapped to implementation and tests:
17/17 areas have evidence, currently assessed as 9 strong, 7 moderate, and 1 thin.

| Feature area | Status | Primary implementation | Primary executable proof | Coverage |
|---|---|---|---|---|
| Bootstrap/fixpoint | Shipped | `bootstrap/Makefile`, `driver.zen`, `bootstrap/sources.txt` | `harness.zen` fixpoint suite | Strong |
| CLI, init, manifests, `build.zen` | Shipped/partial; `Target.target(platform)` cross-compiles for real (Linux aarch64/x86_64/riscv64 via `<triple>-gcc`/`ZENC_TARGET_CC`/`zig cc`, target in the cache key, loud error when no toolchain; cross-OS errors as unsupported v1) | `driver.zen`, `std.build` | `harness_build.zen`, project fixtures | Strong |
| Lexer, literals, declarations, core types | Partial at malformed char/hex validation | `compiler.lex`, `parse*` | value + verdict + fuzz suites | Strong |
| Records, enums, exhaustive match, loops | Partial: some literal-match subjects can repeat; loop-control and statement-match lowering fixed 2026-07-18 | `parse*`, `check`, emitters | value/verdict/formatter fixtures | Strong |
| Functions, generics, traits, closures | Partial at escaping local captures | `check.zen`, `mono.zen` | value, verdict, module closure cases | Strong |
| Modules, privacy, namespace binds | Shipped/partial: dotted ids, ModuleSig, identity diagnostics; flat concat remains the compat layer | `std.internal.resolve` | `harness_modules.zen`, `make difftest` | Strong |
| C backend and runtime | Shipped | `genc_emit.zen`, `zenrt.c` | build/value/examples/fixpoint | Strong |
| JavaScript backend | Experimental target subset | `genjs.zen`, `zenrt.js` | build JS + limited differential suite | Moderate |
| Diagnostics and source mapping | Shipped, multi-channel | `check_validate.zen`, `diagnostic.zen`, `driver.zen` | verdict-kind + diagnostic cases | Strong |
| AST formatter | Partial: known semantic round-trip failures | `pretty.zen`, driver fmt path | fmt fixtures, whole-tree check, idempotence | Moderate |
| `zenc doc` | Minimal by design | driver doc path | a few build-harness cases | Thin |
| `Result`/`Opt`, IO, panic policy | Shipped/uneven | `std.core.result`, `std.io`, `std.sys` | result, IO, runtime panic cases | Moderate |
| Pointer direction/nullability | Shipped with raw floor | `genc` type tags, `check`, `check_validate` | adversarial verdict/diagnostic pairs | Strong |
| Ownership, escape, scratch, sendability | Partial bounded analyses | `check_validate.zen` | large verdict safety matrix | Moderate |
| Text and collections | Broad, APIs still shifting | `std.text`, `std.collections` | value/build/module/std fixtures | Moderate |
| `Sys`, ambient rt, scopes | Multiple live surfaces | `std.sys`, `std.rt`, `std.scope`, concurrent runtime | build and rt/scope fixtures | Moderate |
| Actors, pool, panic isolation | Working split APIs | `std.concurrent.actor`, `pool_actor`, `pool`, `zenrt.c` | parallel/stress/panic/stack-overflow fixtures | Moderate |

Current test inventory is 201 `.zen` fixture files plus large inline case arrays across 8,790 lines
of harness source. This audit removed a committed generated ELF and flagged misleadingly-named `bool_guard_wild`
fixtures (they test return-in-arm, not wildcards) plus stale hard-coded verdict case counts.

The census was exhaustive rather than sample-based: all 303 current `.zen` files were read, including
all 213 test sources, all 77 compiler/stdlib sources, the root driver, and all 12 examples. All 52
Markdown files present before consolidation and every other text source, workflow, manifest, editor,
runtime, and script file were also read. Generated `bootstrap/zenc.gen.c` and the `zenc` executable
were inspected mechanically; the generated C was regenerated and byte-compared rather than treated
as independent handwritten logic.

## Test audit

The full pre-cleanup harness passed in 167.70 seconds with 1.47 GB peak RSS; the fast semantic lane
passed in 6.05 seconds. Slow project/module/runtime/campaign work consumed 96.4% of wall time. These
numbers describe the audit host, not a portable performance guarantee.

After the immediate cleanup and targeted `if` diagnostic, the final fast lane passed in 6.83 seconds
and the full harness plus byte fixpoint still passed. With the new eight-job default the full run took
190.02 seconds and still reported 1.47 GB peak RSS: limiting fan-out is a useful system-load bound,
but the heavyweight deep-resolver compile remains a separate memory target.

| Finding | Value judgment | Status / next action |
|---|---|---|
| Bootstrap byte fixpoint | Essential: proves the checked-in seed is exactly self-reproducible. | Keep in the merge gate. |
| Semantic accept/reject pairs | Essential for pointer direction, ownership/escape, sendability, exhaustiveness, traits, and inference. | Keep the boundaries; simplify their representation. |
| Runtime value/output cases | Essential where acceptance alone can hide a silent miscompile. | Keep one discriminating oracle per lowering/backend behavior. |
| Project, init, module privacy/path, and native-link cases | Essential product behavior. | Keep; these become the acceptance suite for package work. |
| Actor panic/race/stress cases | Valuable but expensive and partly probabilistic. | Keep deterministic cases in full; move repeated stress campaigns to a stress tier. |
| 165 negative cases with an empty diagnostic kind | Weak: any unrelated rejection can pass them. | Pin each to a reason while deduplicating; never replace them with broad “must fail” checks. |
| 81 duplicate inline source groups causing 82 redundant verdict compilations | Redundant work and misleading test volume. | Collapse each source to one named case with all required assertions. |
| Anonymous `.`/`F` reporting | Poor failure localization. | Add stable case names and print the name/source on failure. |
| Source-grep architecture scans | Useful as a temporary fence, brittle as correctness proof. Four unreadable-file paths formerly passed. | Now fail closed; replace private-name substring checks with behavior or typed API-surface checks where possible. |
| Unbounded `nproc` subprocess fan-out | Wasteful: the audit reached 1.47 GB RSS. | Default is now capped at 8; `ZEN_TEST_JOBS=N` is the explicit override. |
| Raw failure count as process exit | Incorrect at exactly 256/512/... failures because POSIX truncates status. | Fixed: the harness now exits 0/1 while retaining individual failure marks. |
| Dead serial runner copies | Maintenance-only duplication. | Removed; argparse now reuses the parallel module-value runner. |
| 220 random token/noise inputs on every full run | Campaign value, low merge-loop value after known crash seeds are retained. | Move random campaigns to an explicit campaign/nightly tier. |
| “Anonymous struct” fixtures rewritten to generated named structs | Bullshit coverage: they no longer exercise anonymous source syntax. | Replace with raw-source compile plus formatter round-trip cases. |
| OOM tests with unreachable branches or “any Err” oracles | Can pass without testing the claimed cleanup/error path. | Use allocation-stage sweeps, exact variants, and acquired/released balance. |
| Concurrency assertions based only on worker count/timing | Scheduler-sensitive and sometimes unable to prove the claimed queue/CondVar path. | Add barriers/instrumentation; keep probabilistic variants out of the merge lane. |
| `tests/atomic_test.zen` | Unwired and always returns success after printing. | Convert to assertions and wire it, or delete it. |

## Important current limits and defects

| Area | Code truth | Consequence / workaround |
|---|---|---|
| std path resolution | `zen` resolves `src/std` relative to the project root (the binary's directory, or `$ZEN_ROOT`), not the invocation cwd. | Run the repo-built `./zen` in place; a relocated binary needs `$ZEN_ROOT` pointing at the checkout. |
| Parallelism fixtures | 5 pool fixtures assert *observed* concurrency and flake under machine load. | Their run stage is skipped in `make difftest`; check/emit still compared. |
| Ordinary `if` | Any `if` token is rejected at the lexer with `error[no-if]` and a teaching hint; match guards were removed entirely (2026-07-18). | Use `.match` (or `.then` for one-way effects); nest a boolean `.match` in an arm body where a guard was wanted. |
| Enum separator | `\|` separates variants and is also bitwise OR. | Comma-separated variants are the chosen cleanup direction but require a bootstrap migration. |
| Local packages | Dotted user modules resolve from the entry program's directory as one logical namespace (`app.utils` → `app/utils.zen`); registered roots/dependency metadata still absent. | Structure projects freely under the entry dir; package roots are the next module-system stage. |
| External signatures | Bodyless functions type-check calls and link only when used; no later Zen definition/completeness pairing. std's foreign prototypes are verified against the real system headers by `make ffi-verify` (CI-gated). | Use them for FFI today, not as a finished module-signature system. |
| Closures | Arbitrary-local escaping captures/capturing fields reject. | Pass directly, lift a named function, or return a parameter-capturing closure. |
| UFCS type args | `value.id<i32>()` does not parse. | Write `id<i32>(value)`. |
| Multi-return | Tuple syntax was reverted. | Return a named record. |
| Ownership | Alias/call analysis is bounded and not a borrow proof. | Keep ownership flows simple; use explicit clone/release and narrow pointer scopes. |
| Scratch/shared memory | Checker is a source-shape heuristic; there are no typed regions or `.share/.give` verbs. | Construct in the actor, move explicit ownership from long-lived storage, or use immutable `Arc`. |
| Runtime API | `Sys` is preferred, but `std.rt`, `std.scope`, checkpoint/coroutine paths remain live. | Do not claim the explicit transition is complete. |
| Actor API | Cooperative and pooled typed actor APIs differ; `Sys.Spawner.spawn` returns `.Err(.Errno(38))` (ENOSYS), not implemented. | Choose the concrete surface explicitly; pooled actors need a concrete trampoline. |
| Actor scheduler | One global mutex-protected run queue, no per-worker deques/work stealing. | Correct multicore execution, not final scalability architecture. |
| Actor panic cleanup | Panic and stack overflow isolate the actor, but non-local recovery can leak behavior allocations and queued typed boxes. | Isolation is process-availability protection, not deterministic unwinding. |
| `fs.read_dir` | Counts, rewinds, then fills a fixed allocation without guarding directory growth; recursive fill scales with entry count. | A changing/huge directory can write out of bounds or overflow the stack; fix before calling robust. |
| File contents | `contents*` sizes via `lseek`. | Contract is regular seekable files; pipes/procfs-style streams need grow-as-you-read IO. |
| Build temporaries | compile/run leave some PID temp outputs; `build.zen` uses a fixed project-local entry; raw `system()` status handling is simplistic. | Concurrent same-project builds and abnormal shell failures need hardening. |
| Library output | `kind = library` is check-only. | No archive/object/package artifact yet. |
| JavaScript | Shared frontend but incomplete native/runtime equivalence. | Use C for full language/runtime behavior. |

## Confirmed defects from the exhaustive census

These are code-path findings, not guesses inherited from old prose. Priority reflects user impact:
P0 can corrupt memory or silently change program meaning; P1 breaks an advertised operation or
accepts/returns a materially wrong result; P2 is a bounded contract, robustness, or resource issue.
Each row names a discriminating regression gate. Fixes should be smaller than this table: land one
coherent row or tightly related group at a time.

| Priority | Confirmed failure | Primary code truth | Required regression gate |
|---|---|---|---|
| P0 | Exact-cap stdin writes one byte out of bounds and larger input silently truncates. | `driver.zen`: `read_stdin` / `read_fd_all` | Feed exactly 8 MiB and more under ASan; grow or reject explicitly, with no OOB. |
| P0 | Allocation products can overflow to a non-positive size; `try_acquire` then returns `Ok(null)` for a positive logical slice. Negative `save` lengths reach `write` as `SIZE_MAX`. | `std.mem.alloc`, `std.core.slice`, collection/backbone allocators; `std.io.file::save` | Checked add/multiply helpers; boundary tests reject overflow/negative counts before allocation or syscall. |
| P0 | `fs.read_dir` counts, rewinds, and fills a fixed allocation; directory growth writes past it, and fill still recurses once per entry. | `std.fs::count_entries`, `fill_entries`, `fill_all`, `read_dir` | Mutating-directory and very-large-directory tests; bounded grow/retry and iterative cleanup on every error. |
| P0 | JS build converts a non-NUL-terminated generated `String` to `cstr`, so append scans beyond the buffer. | `driver.zen::build_js`, `finish_cstr` | Under perturbed allocation, `emit-js` and `build --target js` are byte-identical and pass `node --check`. |
| P0 | Growing `String.append_in(s, s.view()/subview)` can relocate `s` before copying from the old, now-dangling view. | `std.text.string::append_in`, `reserve_in` | Self-append and overlapping-subview tests that force realloc, under ASan and a moving allocator. |
| P0 | Generic tracing is erased to `Rc<Node>` regardless of `T`, and collection frees tracked blocks through the collector caller's allocator rather than the allocator that created each block. | `std.mem.trace::tracked_in`, `blk_trace`, `blk_drop`, `free_white_in` | Two payload types and two counting allocators; dispatch the right trace/drop and free through original provenance. |
| P0 | JS `realloc` copies the requested new size without knowing the old size, reading into adjacent allocations on growth. | `bootstrap/zenrt.js::__zr.realloc` | Grow a block adjacent to a sentinel allocation; copy exactly `min(old,new)` bytes. |
| P0 | Compound assignments can evaluate the base/index twice. | `compiler.parse_stmt::parse_comp_idxset_stmt`, `parse_comp_set_stmt`, and block twins | `a[next()] += 1` calls `next` exactly once. |
| P0 | Literal matches and discarded enum matches can evaluate their subject once per comparison/access rather than once per match. | `compiler.parse_expr::parse_lit_arm_lit` / `cons_lit_arm`; `compiler.check::lower_match_arms` | Side-effectful literal and enum subjects run once in value and statement position on C and JS. |
| P0 | Generic substitution duplicates nested side effects when a parameter is reused and drops them when unused. | `compiler.check::subst_var`, `arg_needs_bind` | `twice(side()+1)` and `drop(side()+1)` each call `side` once. |
| P0 | Anonymous structural identity hashes field names but not field types; different layouts can become the same generated type. | `compiler.genc::mangle_anon_in`; `compiler.parse_type::register_anon` | Use `{q:i32}` and `{q:i64}` together, plus distinct enum payload records; layouts and values remain distinct. |
| P0 | Generic/function type mangling uses unescaped underscore concatenation, so distinct type argument trees can share a symbol and monomorphization entry. | `compiler.genc::mangle_ty`, `mangle_write_args`, `mangle_semantic_ty`; `compiler.mono::has_mangled` | Colliding names such as `Pair<A_B,C>` / `Pair<A,B_C>` emit distinct symbols and layouts. |
| P0 | Generated C temporaries use fixed user-visible names such as `_zdl` and `_subj`. | `compiler.genc_emit` binary, match, sequence, and null lowerings | User locals with every reserved-looking name behave identically; generated names come from a hygienic ID. |
| P0 | Parameter-capturing closure substitution ignores lambda-local shadowing. | `compiler.check::clos_sub_var`, `clos_sub_stmt`, `lift_arms_cap`, `clos_bad_arms` | Local-shadow closures preserve lexical binding. |
| P0 | JS backend rewrites every field named `u`, dispatches intrinsic/DOM behavior by bare function name, and returns raw DOM objects/strings where Zen expects `Opt`/`string_view` representations. | `compiler.genjs::js_member`, `js_dom_dispatch`; `compiler.genc_emit::call_kind`; DOM lowering | Ordinary `S(u:7).u`, function values named `load`, user `log`, DOM Some/None, and DOM text round-trip match C/source semantics. |
| P1 | Formatter can remove generic parameters from bodyless signatures, change nonprintable `u8` chars into `i32` literals, and lose multi-payload enum syntax. | `compiler.pretty::ff_foreign`, `ff_char`, `ff_mkenum`, `ff_arm_pat` | Format, reparse, and compare typed meaning for all three forms; require idempotence. |
| P1 | Duplicate boolean labels are accepted and reinterpreted; empty/multibyte chars and invalid hex escapes fabricate values; nested-bracket assignment places are misparsed. | `compiler.parse_expr::bool_close`, char/unescape paths; `compiler.lex::char_end`; `compiler.parse_stmt::skip_brackets` | Reject duplicate/non-exhaustive bool arms and malformed escapes; accept `a[b[0]] = 3`. |
| P1 | Generic nesting beyond 24 is silently dropped; large enum default literals get contradictory `i32`/`i64` inference; JS fixed-width binding facts leak out of inner scopes. | `compiler.mono::add_inst`, `check::rc_add` / `light_ty`; `compiler.genjs::vw_note` / `vw_lookup` | Deep finite generic gets output or a deliberate diagnostic; large enum and shadowed-width cases match C/JS. |
| P1 | Resolver deletes every second `(receiver, trait)` implementation before SEMA, truncates module IDs/aliases into fixed buffers, and reads/scans dependencies twice while leaking the count graph. | `std.internal.resolve::dedup_impls`, import buffers, `module_count_one`, `fill_module_one` | Conflicting impls reject; long legal IDs resolve or diagnose; one graph/read pass under a counting allocator and `strace`. |
| P1 | Cooperative actor request ignores mailbox-full send, then awaits an uninitialized reply. | `std.concurrent.actor::request`, `ask` | Fill a capacity-one mailbox; request returns back-pressure, never `Ok(uninitialized)`. |
| P1 | Actor panic/stack-overflow recovery can leak queued typed boxes and behavior allocations; `siglongjmp` can also skip a held `Mutex.with` unlock and deadlock the runtime. | `std.concurrent.pool_actor`, `std.sync::Mutex.with`; actor recovery in `bootstrap/zenrt.c` | Counting allocator cleanup plus a second actor acquiring a mutex after the first panics inside it. |
| P1 | Thread/atomic constructors do not handle allocator, `pthread_create`, or join failure safely. | `std.thread`; `std.atomic` constructors | Inject each failure and require a `Result` without null stores or fabricated handles. |
| P1 | Network errors report syscall return `-1` rather than `errno`, writes map unrelated failures to EOF, HTTP receive errors become successful EOF, and truncated chunks are accepted. | `std.net`; `std.http::read_loop`, chunk parser | Closed-port `ECONNREFUSED`, injected `EPIPE`, reset mid-response, and truncated chunk fixtures return exact errors. |
| P1 | JSON accepts leading-zero/trailing-dot numbers and raw control characters; uppercase regex shorthands lose negation inside classes. | `std.json` number/string parsers; `std.regex` class shorthand expansion | Reject `01`, `1.`, and raw-newline strings; `[\\D]` matches non-digits only. |
| P1 | `parse_f64` accumulates an unchecked exponent and computes it with linear recursion; argparse can fail to enforce a required positional that follows an optional one. | `std.text.num::parse_f64`, `pf_pow10`; `std.os` argparse validation | Huge exponent returns a bounded result/error without deep recursion; mixed optional/required positional matrix is exact. |
| P1 | Path normalization advertises `Result` while using infallible scratch allocations; absolute reset in `join` abandons the previous builder. Process output draining is recursive and several error paths leak. | `std.path::normalize_in`, `join_fold`; `std.process::read_more`, `run_ok` | Failpoint allocation sweeps balance allocations; large process output cannot overflow the stack. |
| P1 | `BTree`, `HMap`, `Map`, and `Set` use linear recursion on valid large inputs. | `std.collections.btree`, `hmap`, `map`, `set` traversal/rehash paths | Large adversarial operations remain bounded-stack while preserving ordering/hash behavior. |
| P1 | A missing JS runtime floor still returns success with broken output, while the shipped DOM example's runtime unconditionally calls Node `require("fs")` in a browser. | `driver.zen::js_floor`, `emit_js`, `build_js`; `bootstrap/zenrt.js` | Missing-floor command exits nonzero and creates nothing; DOM example starts in a browser-like VM without Node globals. |
| P1 | Top-level decl parsing used one recursive call per decl, so a module near the 16,384-`decl_buf` cap died with a stack-overflow panic instead of a diagnostic. | `compiler.parse::fill_decls` and its one-decl helpers | Done: `fill_decls` is an explicit loop and the one-decl helpers return a `DCont` continuation; a module past the decl capacity now rejects with a positioned `error[capacity]` (harness `capacity` suite), and registry overflows share the path. |
| P2 | CSV parser abandons field/builder scratch on empty input, trailing newline, and parse errors. | `std.csv` parse buffers | Counting-allocator fail/error-path sweep returns to baseline. |
| P2 | Source byte offset zero doubles as “no location”; first-byte diagnostics can lose line 1, column 1. | `compiler.lex::lerr_set_at`, `compiler.parse_type::perr_set_at`, `compiler.diagnostic::diag_user_span` | Malformed byte zero has stable first-error selection and an exact line-1/column-1 span. |
| P2 | `DateTime` claims the whole `i64` Unix range but negative-floor adjustment overflows at `INT64_MIN`; generic `println` reports only the newline write count rather than the complete operation. | `std.datetime::from_unix`; `std.text.fmt::println` | Round-trip `INT64_MIN` or narrow the contract; define and test `println`'s return contract. |
| P2 | Foreign prototypes model heap pointers as `uint8_t*` and sizes as `int64_t`, so emitted `malloc`/`memcpy`/`free`/`realloc` declarations mismatch the C builtins (ABI-compatible on LP64, UB by the standard; `-Wbuiltin-declaration-mismatch` is suppressed in `bootstrap/Makefile` pending a real fix). | Zen foreign decls (`std.mem.raw`, `std.c.libc`) and the emitter prelude (`compiler.genc_emit`) | A `size_t`/`void*` mapping (or canonical-prototype remapping for known libc symbols) lets the build drop the suppression; `cc -Wall` on the seed stays clean without it. |

## What to build or review next

| Priority | Work | Why now | Done when |
|---|---|---|---|
| P0-A | Size-safe buffers, allocation arithmetic, and allocator provenance | These are the shortest paths from valid input to OOB access, dangling reads, or freeing through the wrong allocator. They undermine every higher-level test. | Fix exact-cap stdin, build-JS termination, `read_dir`, checked sizes/negative IO, String overlap, trace provenance/type erasure, and JS realloc; add sanitizer/failpoint gates. |
| P0-B | Evaluate-once and hygienic lowering | Ordinary expressions can still run twice, vanish, or collide with compiler temporary names in some lowerings (multi-use call args and loop control were fixed 2026-07; guards no longer exist). This is silent miscompilation in the language core. | Compound assignment, every match form, generic substitution, and closure lowering preserve source evaluation exactly once; all compiler names are hygienic. |
| P0-C | Formatter and JS parity-or-reject gate | `fmt` can change types/syntax, and JS currently reinterprets names, fields, DOM values, scopes, and browser startup. A partial backend must still be honest. | Typed format round trips; C/JS differential gates for every shared claim; unsupported JS surfaces reject cleanly before producing an artifact. |
| P1 | Canonical project modules and registered source roots | This remains the next product feature. It matches the desired `src/package/file.zen` model and creates the stable identity boundary SEMA needs. | Build retains roots; nested logical paths resolve deterministically; ambiguity/traversal reject; module graph is keyed by identity rather than flattened text. |
| P1 | Signature/definition pairing | Once module identity is stable, existing bodyless syntax can become a real signature boundary without adding `extern`, path strings, effects, or Rust moves. | Exact structural pairing; referenced missing definitions diagnose; unused signatures are harmless; native obligations remain linker-authoritative. |
| P1 | Simplify SEMA without changing judgments | Repeated AST walks, flat-source rewriting, and channel ordering are the largest correctness/maintenance multiplier. | One module/signature world, one typed-body pass, diagnostics from that pass, lowering afterwards, one monomorphization path; partial move heuristics are not ported. |
| P1 | Simplify and shard tests | Breadth is valuable, but weak negative oracles, repeated compiles, random campaigns, and opaque case names obscure signal and cost minutes. | Declarative named cases compile once per source/backend, assert all applicable outcomes, pin rejection reasons, and separate deterministic merge/stress/campaign lanes. |
| P1 | Converge actors/runtime after cleanup correctness | Split APIs and three runtime concepts obscure the product model, while panic/request cleanup is not yet reliable. | Failure-safe request/cleanup first; then one typed spawn/send/reply surface, real `Sys.Spawner`, and an explicit `std.rt`/scope retirement decision. |
| P2 | Syntax cleanup: enum commas, bitwise-only `\|` | This is coherent but less urgent than correctness and module identity. | Transitional bootstrap accepts old seed/new source, formatter emits commas, then enum `\|` is removed. |
| P2 | Tooling robustness and speed | Temp/process leaks and 1.47 GB self-host RSS are real; ordinary edit/run already meets the sub-second goal. | Race-free cleaned temporaries, decoded process errors, resolver single-pass graph, then profile-driven cold/self-host memory and time reductions without skipping fixpoint proof. |
| P2 | Library/package artifacts and installation | Needed for use beyond a checkout, after the package identity contract exists. | `zenc build` emits a library artifact, dependency metadata matters, and a relocated install locates std/runtime assets. |

## Next product build, after the correctness gate: package and signature spine

Keep the existing import shape. Do not add `@imports`, a path-string import, or `self` in the first
slice:

```zen
pkg = some_package
{ read_config } = some_package.config
```

For a source root registered by `build.zen` or `zen.toml`, resolve logical identities as follows:

| Logical module | Canonical file |
|---|---|
| `some_package` | `<source-root>/some_package/some_package.zen` |
| `some_package.config` | `<source-root>/some_package/config.zen` |
| `std.text.fmt` | Existing toolchain-root mapping, unchanged |
| legacy bare sibling `util` | `<entry-directory>/util.zen`, temporarily retained only when no registered package conflicts |

Reject absolute paths, `.`/`..` traversal, duplicate canonical identities, and an ambiguous package
plus legacy sibling. A module is identified by its logical path, never by a flattened short name.

Land this as two reviewable changes, in order.

**PR 1 — canonical project modules.** In `driver.zen`, retain `source_root` in `Spec`; today both
`zen.toml` and `build.zen` reduce the project to an entry path and the resolver receives only that
file's directory. In `std.internal.resolve`, replace the bare-sibling special case with one
`ModuleId -> canonical path` function, allow dotted user IDs, and key the graph by logical identity.
Do not crawl the filesystem or silently prefer one ambiguous path. Direct-file mode keeps its legacy
sibling behavior. Add end-to-end coverage in `harness_modules.zen`, `harness_build.zen`, and nested
project fixtures.

PR 1 is complete only when executable tests prove:

- package-root and nested-module alias imports work;
- transitive dotted imports work under both `zen.toml` and `build.zen` roots;
- destructured public imports work and private names reject at the importing line;
- two packages may export the same short name without collision;
- traversal, ambiguous legacy/package paths, missing modules, and duplicate identities reject with a
  stable diagnostic kind;
- direct-file legacy siblings and existing `std`/`compiler` imports remain green.

**PR 2 — signature/definition pairing.** Keep the existing syntax; the compiler already parses a
bodyless function, so adding `extern`, `@imports`, or an effect syntax would create migration without
solving identity:

```zen
read_config* = (fs: Fs, path: string_view) Result<String, IoError>
read_config = (fs: Fs, path: string_view) Result<String, IoError> {
    // implementation
}
```

Treat the bodyless declaration as a neutral signature rather than inherently foreign. Separate
signature and definition indexes, require exact structural agreement, and preserve both through
resolution/emission. A referenced signature must have one Zen provider or remain an obligation for
registered native/link input; an unreferenced signature is harmless. In the first implementation,
“used” should mean syntactically referenced anywhere in emitted code. True `main`-rooted reachability
needs call-graph dead-code elimination and is later work. Native link inputs remain linker-authoritative
until build metadata can name provided symbols.

`String` is legal in a signature: it is a concrete owned library value, not proof that the language
needs a move system or an effect annotation. Full exported record definitions already provide layout
signatures; opaque/incomplete by-value records are a separate feature and should be deferred.

PR 2 touches the declaration variant/model in `genc.zen`/`parse.zen`, separate signature and body
lookup in `check.zen`, pairing diagnostics in `check_validate.zen`, prototype/body emission in
`genc_emit.zen`, source-preserving formatting in `pretty.zen`, and signature-aware symbol retention in
`std.internal.resolve`. It is complete when tests prove:

- an unreferenced bodyless signature builds;
- a matching signature plus body runs, including across modules;
- arity, parameter, return, or generic-bound mismatches reject even when uncalled;
- a referenced unsatisfied signature reports `missing-definition` at a call or function-value use;
- existing native fixtures remain linker-authoritative;
- C/JS shared-front-end cases, formatter round trips, the full harness, regeneration, and byte
  fixpoint remain green.

## Semantic simplification plan

The goal is not a giant rewrite and not Rust move semantics. Signatures and type structure should do
the stable work; flow analysis should cover only facts that genuinely depend on program order.

| Current responsibility | Current shape | Target owner | Retire after parity |
|---|---|---|---|
| Module identity/imports | `std.internal.resolve` builds a graph, then flattens and rewrites names as text. | `World` of `ModuleId`, public `ModuleSig`, and canonical paths. | Alias text rewriting, flat concatenation, shadow/dedup compatibility passes. |
| Types and calls | `check.zen` overlaps `infer_expr`, `light_ty`, `infer_targs`, `fits`, and repeated resolve/inline rounds. | One typed-body pass, one `resolve_call`, one `coerce`, stable `SymbolId`/`TypeId`. | Mangled-name semantic lookup and pseudo-local context keys. |
| Diagnostics | `check_validate.zen` repeats count, kind, batch, enrichment, and specialized safety walkers; the driver manually orders about 15 channels. | One diagnostic sink emitted during signature/body checking with module-aware spans. | Packed kind/count values, enrichment re-walks, flat-source inverse mapping. |
| Rewriting/lowering | Source AST is rewritten before all source judgments are complete. | A separate lowering pass after successful SEMA. | Diagnostic archaeology over inlined/mangled source. |
| Generics | Function specialization in `check.zen`, aggregate specialization in `mono.zen`, and backend repetition. | One deterministic monomorphization pass shared by C and JS. | Textual generic inlining and backend-owned instantiation. |
| Ownership/send safety | About 1,900 lines of bounded move/alias/escape/scratch/send heuristics. | Explicit language decision for `Own`; structural `sendable(Ty)` and straightforward pointer rules. | Partial Rust-like dead-variable state and function-name/source-shape guesses. |

1. **Make diagnostics the result, not a parallel shadow.** Introduce one sink/list used by the core
   semantic walk. Derive error counts and first-error behavior from that list. Preserve current kind,
   span, message, and cascade suppression tests.
2. **Unify declaration/type lookup.** Keep one `DeclIndex`/module-signature world and one canonical
   `Ty` compatibility relation. Stop rebuilding the same receiver, bound, and argument facts in raw
   and resolved walkers except where syntax genuinely disappears during lowering.
3. **Validate before destructive lowering.** Retain a typed source AST (or annotations on it) through
   diagnostics. Perform inlining, `.or_return`, match, closure, and backend lowering after source
   judgments are recorded.
4. **Do not port the partial move checker.** Ordinary bindings, assignments, calls, and sends should
   not silently make a source variable dead. Decide `Own<T>` explicitly before removal: retire it,
   make it a clearly manual/unsafe handle, or adopt deliberate reference-counted value semantics.
   Keep structural `sendable(Ty)`, pointer direction/nullability, infinite-type, and must-use rules;
   delete scratch/name-shape promises unless real region/effect types replace them.
5. **Move from flat source to linked module signatures.** Check each module against imported public
   headers, require definitions only for reachable used symbols, and preserve path identity. Remove
   compatibility flattening only after the same module suite and generated output pass.
6. **Delete in slices.** Each replacement must flip a discriminating test pair, run both backends
   where relevant, pass the full harness, regenerate the seed, and prove the byte fixpoint before the
   old path is removed.

Success is structural, not a line-count contest: the driver no longer manually chains specialized
diagnostic channels; one semantic fact is computed in one place; source diagnostics do not depend on
post-lowering archaeology; and safety promises match the actual analysis.

## Test simplification direction

Keep the tests that protect a user-visible contract or a previously demonstrated crash/miscompile:

- one accepting and one rejecting case for each semantic boundary;
- runtime value/output checks for lowering and stdlib behavior;
- diagnostic kind/span/message checks where teaching quality is the feature;
- module privacy/path/collision cases;
- C/JS differential cases for shared claims;
- fuzz no-crash/no-hang budgets;
- actor race/stress/panic isolation;
- architectural raw-boundary checks;
- formatter idempotence and bootstrap fixpoint.

Simplify or remove:

- the same source repeated in verdict, kind, build, module, and diagnostic arrays when one compiled
  fixture can feed several assertions;
- comments or test labels that manually claim case counts;
- source-text substring checks for implementation details when a behavioral test is possible;
- many separate shell invocations that recompile identical flattened programs;
- resolved-bug prose files once the executable regression exists;
- broad happy-path duplicates that add no new type, lowering, backend, allocator, or failure boundary.

The target shape is a declarative case record with fields such as source/files, phase, backend,
expected verdict/kind/value/output, and optional diagnostic fragments. One runner should compile once
per unique case/backend and evaluate all applicable assertions. Slow OS/concurrency/fuzz/fixpoint
suites should remain explicit shards; the deterministic semantic core should stay a fast inner loop.

## Stable design decisions

- No ordinary `if` statement; `.match` is branching.
- No attempt to copy Rust's universal move/borrow semantics.
- Errors are values; `panic` is explicit.
- Signatures, path identity, and type structure are the desired module/effect boundary.
- `|` should remain bitwise OR; enum commas are the migration direction, not current syntax.
- Capabilities should be explicit at boundaries and attenuated to the narrowest required value.
- C remains an intentional bootstrap/backend target, not a fallback implementation language.
- Historical audits belong in Git history; maintained docs describe only current truth and ordered
  next work.
