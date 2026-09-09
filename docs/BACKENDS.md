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

Generation publishes each borrowed artifact synchronously. The callback must
consume or copy its bytes before returning. Allocation failures stay typed;
backend diagnostics suppress publication and the driver reports publication
failures. The C split layout lowers once, emits its shared header, and renders
used modules in stable order with a fresh scratch arena for each. A requested
symbol map follows only when all source publications succeeded.

Registration is static: a generator has a Codegen case, Generation dispatch,
and an explicit project recipe. Importing a generator module exposes its API;
it does not register a plugin. No dynamic plugin loader is implemented.

The C backend still has its existing AST-based lowering, specialization,
closure handling, cleanup, and runtime machinery. Its `lower_program` operation
stages C emission; it does not produce this shared IR. The scalar backends do
not establish full-language parity or a completed architecture migration.

## Further work and acceptance criteria

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
