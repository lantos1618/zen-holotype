# Code generation

C is the default, full-language backend and the compiler's bootstrap path.
JavaScript and GNU x86-64 assembly support scalar executables. Their support
boundary is deliberately checked: unsupported reachable code produces a source
diagnostic before the output callback runs. Selecting another backend never
falls back to C.

## Running the same source

After `make build`, enter the example project:

```sh
cd example/backends
../../zen run c
../../zen run js
../../zen run asm
```

Each prints `fib(10) = 55`. JavaScript runs on Node.js. Assembly projects require
Linux, x86-64, the GNU ABI, and a C toolchain for assembly and linking. The
assembly renderer writes `.s` directly; it does not ask a C compiler to generate
assembly from C.

`Codegen.C`, `Codegen.Js`, and `Codegen.Asm` select the recipe in `build.zen`.
JavaScript defaults to `build/{os}-{arch}/{name}.js`; an explicit output path is
used exactly. C and assembly produce native executables. Arguments after the
project target are passed to the selected runtime, although the scalar subset
does not yet expose `Env.args` to the program.

From the repository root, select a backend explicitly for raw source emission:

```sh
./zen build example/backends --entry main.zen --std src --backend js -o build/fib.js
./zen build example/backends --entry main.zen --std src --backend asm -o build/fib.s
```

`--backend` selects source output; omitting `-o` writes it to stdout. Existing
`--emit-c` invocations remain compatible. Split-module output and symbol maps
currently belong to C. Raw assembly output has a fixed Linux x86-64 GNU target; it is not a
host-independent assembly format.

## Implemented scalar surface

Both new backends share these language rules:

- `i32`, `bool`, and unit parameters, local values, and function results.
- A zero-argument `main` returning `i32` or unit; an unused standard `Env`
  parameter is also accepted. An integer result becomes the process exit code.
- Monomorphic functions, recursion, positional calls, local assignments, and
  nested boolean matches with explicit `true` and `false` arms.
- Checked arithmetic, comparisons, unary negation and boolean negation, and
  short-circuit `&&` and `||`. Source evaluation order is preserved. Dynamic
  integer arithmetic requires operands with a settled `i32` type. Unsettled
  literal arithmetic is accepted only when sema can fold it to a fitting
  constant; this avoids silently changing the current C path's wider literal
  arithmetic. The underlying defaulting discrepancy remains compiler work.
- `print` and `println` of scalar values and literal byte strings, positional
  and local named format holes, doubled braces, and Zen string escapes.
- Operator-position arithmetic diagnostics and exit status 134, matching Zen's
  failure model. Output preceding a trap is flushed before exit.

Actors, allocator capabilities, dynamic strings, collections, structural
results, closures, generic instantiation, foreign calls, named/default call
arguments, wrapping arithmetic, and other numeric widths are not lowered by
these backends yet. Unused generic functions need not be lowered, but the
frontend still checks the entire imported source graph. JavaScript project
recipes refuse native link dependencies.

## Phase boundaries

The new paths are:

```text
AST + checked semantic facts
  → gen_lower
  → gen_ir.Program
  → gen_verify
  → gen_js or gen_asm
  → synchronous artifact publication
```

The scalar IR contains typed slots, function signatures, explicit basic blocks
and terminators, and operator source spans. It uses mutable slots rather than
SSA. The verifier checks references, types, calls, constant representations,
branch targets, return types, and definite assignment across reachable control
flow. Structural validation also covers unreachable blocks. Validation failure
is a compiler diagnostic, not a partially emitted program.

Renderers consume verified IR without consulting the AST or semantic checker.
Direct renderer callers must satisfy that precondition. All vectors, source
spans, and text borrow caller-chosen compilation storage. Returning a Program
or String does not extend its allocator's lifetime.

`gen.gen_c_ir.emit_c(a, program)` is an experimental C renderer for this same
scalar IR. It returns `Res<String, AllocError>` after the caller verifies the
program. Its C11 output uses direct labels and branches, explicit arithmetic
checks, and length-aware byte output. It is an importable API, not a CLI backend
selection; `Codegen.C` continues to use the full-language C backend. Its private
scalar calling convention does not specify the foreign or aggregate ABI.

Generation publishes each borrowed artifact synchronously. The callback must
consume or copy its bytes before returning. Allocation failures stay typed;
backend diagnostics suppress publication and the driver reports publication
failures. The C split layout lowers once, emits its shared header, and renders
used modules in stable order with a fresh scratch arena for each. A requested
symbol map follows only when all source publications succeeded.

## Assembly target contract

`gen_asm.Target` declares `emit(self, program) -> Res<String, AllocError>`.
It consumes verified scalar IR, allocates output and scratch storage through
the caller-chosen allocator carried by its receiver, and returns assembly text
without publishing or running it. The renderer preserves effect order, control flow, checked arithmetic,
source-position traps, and exact byte output. Verification remains the caller's
precondition; the normal Generation path verifies before invoking a renderer.

`gen_asm_x86.X86_64LinuxGnu(alloc: a)` implements that contract. Its allocator
is required at construction. This concrete target owns instruction selection,
registers, stack layout, System V calls, ELF/GNU syntax,
and Linux runtime linkage. `Codegen.Asm` explicitly selects this target; neither
host detection nor another architecture is implied by the generic contract.
The direct assembly corpus invokes the target through a generic `Target` bound
and checks real executable behavior, including stack arguments and ABI alignment.
The x86 renderer reuses a slot value already held in `%eax` within a basic
block. Stack slots remain authoritative; writes update or invalidate that fact,
and block entries and libc calls discard it. This removes redundant reloads
without changing arithmetic checks, evaluation order, or the calling convention.

Future implementations such as `gen_asm_aarch64` should satisfy the same
whole-program contract. Add a target only with its OS, object format, ABI,
runtime dependencies, and execution tests specified. Keep machine-specific
operations inside that implementation; extend shared IR for language semantics,
not to encode x86 register names or force other targets through x86 operations.
Target selection belongs at the generation/build boundary. The contract does
not import its implementations.

The next target implementations are separate platform contracts, not alternate
spellings of `Asm`:

| Target | Object/link format | Calling convention | Status |
| --- | --- | --- | --- |
| Linux x86-64 GNU | ELF | System V AMD64 | Implemented scalar subset |
| Linux ARM64 | ELF | AAPCS64 | Proposed |
| Windows x86-64 | COFF/PE | Microsoft x64 | Proposed |

Keep libc/foreign calls distinct from direct kernel syscalls. A foreign call
uses the selected platform's function ABI and symbol linkage; a direct syscall
needs its own target-specific operation and error contract. Neither follows
automatically from support for arithmetic instructions. Windows support must
define its runtime imports rather than reuse Linux syscall numbers or symbols.

Before exposing another target in build recipes, run the shared scalar suite
and executable tests for argument passing, stack alignment, returns, byte
output, and traps on that target. Extend language coverage through shared
lowering and verified IR, using the experimental C renderer as a differential
oracle; do not duplicate generic specialization, ownership, or cleanup rules
inside each assembly renderer.

Registration is static: a generator has a Codegen case, Generation dispatch,
and an explicit project recipe. Importing a generator module exposes its API;
it does not register a plugin. No dynamic plugin loader is implemented.

The C backend still has its existing AST-based lowering, specialization,
closure handling, cleanup, and runtime machinery. Its `lower_program` operation
stages C emission; it does not produce this shared IR. The scalar backends do
not establish full-language parity or a completed architecture migration.

## Further work and acceptance criteria

Networking requires extending shared lowering before adding assembly-specific
socket operations. `std.net.socket` declares POSIX foreign functions; the
scalar lowerer currently rejects external calls, and its IR cannot represent
pointers, memory accesses, or structured results. The first executable milestone
is a scalar foreign `socket`/`close` call with the platform ABI verified. Follow
with pointer-width values and memory operations, then record/result layouts and
cleanup sufficient for a loopback TCP send/receive through the existing library.
Keep symbol linkage and target ABI rules in the target; keep language types,
effects, and cleanup in shared lowering. Existing libc printing tests do not
establish support for arbitrary foreign calls or direct Linux syscalls.

The experimental scalar C renderer exercises the current contract without
requiring whole-language IR support or changing the bootstrap path. Its corpus
compares evaluation order, output, and arithmetic traps with existing C, JS,
and assembly, and compiles IR C with warnings as errors and UBSan. This is a
correctness baseline for extending the IR, not a performance result.

A shared whole-language backend boundary requires migration of concrete
semantic responsibilities, not another dispatch case:

1. Carry settled call targets, type substitutions, captures, and cleanup exits
   into a shared representation. Renderers must not repeat name resolution or
   type inference.
2. Define allocation, ownership transfer, actor mailboxes, and foreign ABI
   operations with explicit runtime contracts. Prove behavior against the
   existing C path one feature family at a time.
3. Migrate C to that representation while retaining the current bootstrap
   path until fixpoint and corpus parity hold. Remove each duplicated lowering
   only after its replacement covers the existing behavior.
4. Measure frontend, lowering, validation, rendering, and native-tool time
   separately before adding optimization passes. This change does not claim a
   compilation-speed improvement.
5. Add an LLVM renderer when that shared contract can serve it. Textual `.ll`
   is a viable first interface. Typed blocks and explicit runtime operations
   transfer; LLVM still needs the correct target layout, ABI, debug locations,
   and explicit checks for Zen's trapping arithmetic.

`gen_llvm` is not implemented. A future LLVM path may initially lower mutable
slots to stack allocations and let promotion passes construct SSA. LLVM is an
optional native backend, not a requirement for bootstrapping or running the C
path.

The executable corpus covers cross-backend evaluation and output, renderer
runtime behavior, malformed IR, and project build/run recipes. `make verify`
remains the aggregate gate. Passing it is evidence for the implemented surface,
not a numerical ergonomics rating.

## Migration order and measurement

Call checking now publishes a `CheckedCall` containing the selected declaration
or member provider, substitutions, result type, and optional function signature
with its implicit receiver, plus the selected body when available. These facts are published together after argument
and callback checking succeeds. `Checking` and `Rejected` states expose no
selection, including when a contextual recheck replaces an earlier success.
Generic-instantiation edges are published at the same successful boundary.
Editor queries use these source-level facts rather than execution IR.

The scalar lowerer consumes the checked signature and result. C method
specialization uses complete checked substitutions without repeating argument
inference; missing or open substitutions still use the existing completion
path. Literal ranges are checked again when generic substitution supplies a
concrete numeric width, including literal receivers. An unresolved literal
family does not impose a concrete width.

Stored field defaults are checked in their declaring module and the struct's
symbolic type-parameter scope, including defaults on unused types. Their calls
publish checked declarations, substitutions, results, and signatures before C
lowering. Written field types constrain default values and literal ranges;
construction-site locals cannot supply missing names. C's default-value purity
check uses a recorded call selection when present, rather than resolving the
same name again. Default emission substitutes the constructed type's parameters
and restores the caller's instantiation on success or failure; nested generic
defaults do not inherit an unrelated caller's type-parameter scope or local
bindings. This does
not permit ordinary function calls in defaults.

This is not yet a complete call execution plan. Named/default argument
bindings, conversions, member implementation identity, captures, and cleanup
still need explicit shared representations. Checked generic facts can mention
enclosing type parameters; successful checking does not mean specialization is
finished. Calls in deferred contexts still require completion. A declaration
ID alone remains insufficient evidence that a call is valid.

Function and method worklists keep each target and its substitutions in one
queue record. Queue storage is reserved before publishing the seen symbol,
and lowering no longer substitutes an empty instantiation for a missing row.
Emitted functions keep their symbol, prototype, body, source origin, and module
in one record; foreign declarations and queued types likewise publish complete
records. Type storage is reserved before its lookup entry is published.
Allocation-refusal regressions check that failed publication leaves no visible
entry and that retry succeeds. Ordering extracts borrowed keys from records and
uses the existing stable sort without rebuilding parallel metadata vectors.

A checked free declaration selected for dot syntax takes precedence over
receiver-member lookup during C lowering. An incompatible same-named member
cannot replace that choice. Deferred calls and member specialization still
retain the compatibility paths described above.

Keep instance discovery separate from building an individual function. Extend
the IR one feature family at a time, with explicit places, aggregate values,
captures, cleanup, and runtime operations as each becomes necessary. Remove
the corresponding AST-based C lowering only after behavioral parity and
bootstrap fixpoint checks pass. Do not move the existing helper chains into a
larger shared lowerer unchanged.

Record frontend, specialization/lowering, IR verification, rendering, native
compilation, and linking separately. Benchmark cold native builds, unchanged
builds, and a single source edit; whole-suite duration is not compiler latency.
Use paired uninstrumented runs with identical source roots, reachable-program
policy, toolchains, and flags. Include output checks, allocation measurements,
and a failing regression control before imposing a budget. Different root
policies can change how much code is emitted and must not be reported as a
renderer speedup.

Preserve the existing dependency-aware native cache. Semantic caching and
parallel checking require explicit dependency and ownership contracts before
sharing results or mutable compiler state.

## Backend quality milestones

A high-quality backend needs evidence for its supported surface as well as a
maintainable implementation. These milestones guide subsequent review; they do
not assign a numerical rating or imply full-language support for scalar targets.

1. **Authoritative semantic input.** Complete per-instantiation call plans for
   named/default argument binding, conversions, member identity, captures, and
   cleanup. Remove C's compatibility lookup and inference only once accepted
   deferred calls have those facts. Check receiver evaluation once, argument
   order, diagnostics, and bootstrap parity.
2. **Shared lowering with explicit responsibilities.** Extend verified IR one
   feature family at a time, starting with places and aggregates, then calls,
   captures, cleanup, and runtime operations. Migrate the corresponding C path
   only after executable parity. Keep discovery, function-local lowering, and
   rendering state separate where their lifetimes differ.
3. **Executable target contracts.** Run shared semantic cases across all
   supporting renderers and target-specific cases for ABI boundaries, traps,
   byte output, and allocation refusal. Verify unsupported programs fail before
   publication. A second architecture must run on hardware or a specified
   emulator; assembling text alone does not establish calling-convention parity.
4. **Measured output quality.** Establish paired baselines for compile phases,
   retained allocation, generated size, and runtime. For x86, measure slot
   liveness/reuse and register allocation against the current stack-slot baseline.
   For JS, measure structured control-flow emission against block dispatch.
   Preserve arithmetic traps and ordered effects through every optimization.
5. **Independent maintainability review.** Trace representative changes through
   the C, JS, and assembly paths. Review whether semantic rules have one owner,
   target assumptions are explicit, and a new instruction or diagnostic has a
   clear home. Run `make verify`, including seed/fixpoint checks, for each
   integrated batch; reassess architecture separately from test results.
