# Verification re-census after full fix wave (v3)

USABLE: 5.5/10 — A coherent, genuinely expressive language with a real (40+ module) stdlib and near-rustc diagnostics, but the documented ergonomic paths break under you: chained collection wrappers panic/hang, rand is unusable via its own UFCS style, and short type names (T/A) silently poison stdlib generics. It runs real programs, but fights you often enough that a newcomer hits a wall in the first hour.

TRUSTWORTHY: 5/10 — The build/self-hosting story is exemplary (byte-exact fixpoint, tiny trusted C floor, gating CI), but the two things that matter most for trusting the OUTPUT are broken: the crown-jewel static ownership/escape checker is UNSOUND (silent, ASAN-confirmed use-after-free launders past `check: ok`), and the default C backend miscompiles a mainstream feature (generic multi-field enum variants). A trustworthy build system wrapped around a compiler you cannot yet trust to reject unsafe code or compile valid code.

## The scorecard

| dimension | score | verdict |
|---|---|---|
| error messages / diagnostics | 7/10 | rustc-adjacent surface (code+caret+expected/actual+hint+batch), but a variant typo yields no diagnostic then an ICE |
| stdlib breadth + ergonomics | 5/10 | genuinely broad and mostly works, but chained Set/Map wrappers crash, rand ICEs via UFCS, heavy allocator boilerplate |
| language expressiveness + friction | 6/10 | strong core (match-only, Result/or_return, generics, actors, real closures) undermined by no tuples, namespace landmines, flaky UFCS |
| memory + type soundness | 3.5/10 | runtime guards solid; static ownership/escape checker UNSOUND — one indirection launders UAF and dangling-stack-ptr past check |
| codegen correctness | 4/10 | generic multi-field enum variants fully miscompile on C backend (checker ok → invalid C); JS backend runs it correctly |
| reliability under hostile input | 7.5/10 | every malformed/deep input ends in a clean panic or parse error, never a raw segv; one quadratic compile-time blowup |
| self-hosted + trustworthy build | 9/10 | byte-exact fixpoint (verified 2 ways), generated seed, 228-line C floor, 900+ case oracle, CI gates on all of it |

(These are the 7 probes supplied; grouped as USABLE = diagnostics/stdlib/expressiveness and TRUSTWORTHY = soundness/codegen/reliability/build.)

## What BROKE (ranked by severity)

1. SILENT MEMORY CORRUPTION — static safety checker is unsound (soundness probe). Releasing an `Own<T>` through a borrow param (`MutPtr<Own<Resource>>`) then using it passes `zenc check: ok`, runs, and prints garbage; ASAN on the driver's real emitted C confirms `heap-use-after-free`. Separately, a stack pointer laundered through an identity fn into a returned struct field passes `check: ok` and ASAN confirms `stack-use-after-scope`. Root cause: consume tracking only fires when a param's type is `Own` (check_validate.zen:1524/:1375); a `MutPtr<Own<T>>` is classified as a non-consuming borrow, and escape analysis is intra-procedural and field-blind. This is the class the memory notes claim "verified/sound" — verification only exercised direct forms, not one-hop laundering. This is the #1 trust-killer.

2. MISCOMPILE of a mainstream feature (codegen probe). Generic enum with a multi-field payload variant (`Tree*<T>: Leaf(T) | Node(T,T)`) passes `check: ok` then emits invalid C (`unknown type name '__anon__0__1'`) → "this is a compiler bug." The tuple payload type is emitted un-monomorphized in the union member while its forward-decl and constructor use the mono suffix (genc.zen:913). The JS backend compiles and runs the identical program correctly — two backends disagree on a valid program. Confirmed across 1- and 2-tparam shapes; single-field generic and non-generic multi-field both work, so the break is precisely generic × multi-field payload.

3. Collections ergonomic API broken (stdlib probe). `AHMap.put(...).put(...)` chained → `slice index out of bounds` abort; `ASet.add(...).add(...)` chained → infinite hang (timeout). Sequential calls work and chained `AVec.push` works, so 2/3 of the allocator-free "A" wrappers — the whole point of hiding the boilerplate — miscompile chained struct-returning methods (hmap.zen:470, set.zen).

4. std.rand unusable via its documented style (stdlib probe). `r.next()`/`r.range()` on a local `Rng` passes the checker then ICEs at cc (`expected 'Rng *' but argument is of type 'Rng'`) — no UFCS auto-ref for MutPtr receivers, and the checker doesn't gate it. Only fully-explicit `rand.next(r.addr())` works (rand.zen:24,33).

5. Checker-gate holes surface as raw "compiler bug" ICEs (diagnostics + stdlib probes). A qualified nonexistent variant (`Color.Purple`), an undefined module member inside an inline UFCS chain (`os.env(...)`), and MutPtr arg mismatches all pass `check` and then ICE at cc. A typo becoming an internal compiler error is the worst-possible diagnostic.

6. Flat-namespace landmines (expressiveness probe). A user type named `T` or `A` poisons stdlib generics with an error pointing INTO stdlib (fmt.zen:107, alloc.zen:36) and zero attribution to the user's decl. UFCS `xs.find(p)` on `[i32]` silently resolves to `str.find` and errors on arg type. Both bite the most natural code.

7. No tuples / multi-return (expressiveness probe). Tuple return syntax not only fails to parse but cascades the parse error INTO stdlib (libc.zen:20). Every multi-value return needs a hand-written struct.

8. Quadratic compile time (reliability probe). 1k/2k/4k/8k trivial fns → 0.76/1.5/4.2/11.3s (~n^1.4); 50k fns never finished in >4 min CPU (99.9% CPU, flat 1.37GB RSS = compute-bound, not a leak). Effectively a hang on large/generated modules; likely O(n²) flat-namespace resolution.

Minor: positionless/misleading message for wrong match-arm arity (e14); operand-type check missing in call-arg position; exhaustiveness lists one missing variant at a time; JSON is f64-only (lossy integers); UFCS-through-module-alias unsupported; camel/snake naming inconsistency; parse-error carets land on the following token; deep array-literal parse path escapes the depth guard (caught by SIGSEGV handler).

## The gap to genuinely usable (~8/10)

Ranked shortest-path:
1. Per-module namespacing / scoped resolution. Kills the T/A stdlib-poisoning, the UFCS wrong-fn resolution, and almost certainly the quadratic compile-time (the O(n²) flat-namespace scan). Single biggest usability + scalability lever; already partially tracked (#13/#39, blocker #1 in the feature table).
2. Fix the chained struct-returning method miscompile so AHMap.put/ASet.add work chained — the allocator-free collection API is the intended ergonomic path and is 2/3 broken.
3. UFCS auto-ref for MutPtr/Ptr receivers (unblocks std.rand and any method whose receiver is a mut-pointer), plus gate the mismatch in the checker instead of ICE-ing at cc.
4. Tuples / multi-return (even just anonymous tuple types + destructuring bind). Removes per-return struct boilerplate; the acid programs and stdlib idioms both want it.
5. Reduce allocator threading — an ambient/default allocator within a scope (aligns with the active rt scoped-runtime direction) so string/collection/encoding calls don't each take an explicit allocator arg.
6. Ergonomic polish: `=` vs `:=` should give a "did you mean :=" hint not undefined-name; boolean-match/cond sugar for >2-way conditionals; UFCS-through-module-alias; consistent snake_case; fix deeply-qualified-call arity miscount.

## The gap to trustworthy (~8/10)

Ranked by trust impact:
1. Make the ownership checker sound for indirection. Track consumes through `MutPtr<Own<T>>`/`Ptr<Own<T>>` borrow params (per-fn "frees through pointer" summary) or forbid releasing through a borrow. This is a silent-corruption hole, not a diagnostic-quality nit — highest priority for the word "trustworthy."
2. Make escape analysis inter-procedural and field-aware: follow pointers returned through calls (including identity/wrapper fns) and pointers stored into returned struct fields/slice elements.
3. Fix the generic multi-field-enum monomorphization bug (genc.zen anon-mangle must run during enum-variant payload type substitution) — a valid program must not silently emit invalid C.
4. Close the checker-gate holes so no valid-looking AST reaches codegen and dies as "compiler bug": nonexistent qualified variants, undefined module members in UFCS chains, MutPtr arg mismatches. Every one of these should be a positioned `error[...]` at check time.
5. Backend parity: C and JS must agree on validity — a program that runs on JS must at least compile on C, or both reject. Add differential C-vs-JS oracle coverage (JS is currently under-tested).
6. Audit the rest of the type-soundness surface not yet probed: unsafe casts, generic variance, RawPtr reinterpret/transmute — given the ownership pattern, more holes are likely.
7. Route all recursive-descent parse paths through the explicit depth guard (array-literal path currently only survives via the SIGSEGV handler), and fix runaway-lexer diagnostic misattribution to stdlib files.

## Honest bottom line

Zen today is a genuinely self-hosting compiler with an exemplary, adversarially-verified build (byte-exact fixpoint, tiny trusted C floor, gating CI) that exposes a coherent, more-capable-than-reputed language — but it is not yet a language you can trust to write real programs in: its flagship static safety checker is unsound (silent, ASAN-confirmed use-after-free), its C backend miscompiles generic multi-field enums, and multiple typos/errors slip past `check` into raw compiler-bug ICEs. It is usable and trustworthy for its authors dogfooding the compiler and for small, well-trodden programs; for an outside developer writing production code it is roughly halfway there. Shortest path to real: per-module namespacing (fixes the biggest usability landmine and the quadratic blowup at once) and making the ownership/escape checker sound through one indirection (fixes the biggest trust-killer) — those two moves alone would push both scores toward 7.