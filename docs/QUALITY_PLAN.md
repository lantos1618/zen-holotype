# Quality plan

The target is a repository where one green command means the compiler is
releasable. Architecture work comes first because naming the compiler's phases
exposes the semantic, performance, and ownership mistakes hidden by long relay
chains.

This plan uses builder-language vocabulary so order and gates are explicit.
The `Step`, `run`, `group`, and `default` APIs below are **proposed**, not current
`std.build` behavior. Today the public `Builder` declares `test`, `bench`, and
`budget`, while the checked-AST project planner implements only `target`,
`c_import`, `lib`, `extern`, and `exe`. The first builder card closes that gap;
until then, `make verify` is the executable compatibility door.

## Agent builder

This is the orchestration pattern for the work. `AgentPlanBuilder` is planning
notation, not a repository API. It makes file ownership, dependencies, proof,
and merge order visible before an agent edits anything.

```zen
plan = AgentPlanBuilder("zen-9.5")
    .policy("comments", EndUserAndAiContract)
    .policy("seed", RegenerateOnlyAtMerge)
    .policy("files", ExclusiveLaneOwnership)

    .lane("named-call", {
        agent: Agent("call-lowering"),
        owns: ["src/gen/gen_c/gen_c_call.zen", "tests/corpus/codegen/named_call_*"],
        build: Card("NamedCallSite"),
        prove: [Focused("call dispatch"), Make("test"), Make("determinism")],
    })
    .lane("actor-send", {
        agent: Agent("actor-lowering"),
        owns: ["src/gen/gen_c/gen_c_actor.zen", "tests/corpus/actor/*"],
        build: Card("ActorSend", "ActorSendEmission"),
        prove: [Focused("actor send"), Make("test"), Make("determinism")],
    })
    .lane("signature-use", {
        agent: Agent("sema-calls"),
        owns: [
            "src/sema/sema_call.zen",
            "src/sema/sema_cand.zen",
            "src/sema/sema_supply.zen",
            "tests/must-fail/sema/call_*",
        ],
        build: Card("SignatureUse", "Exact | Recovery"),
        prove: [Focused("call rejection"), Differential(), Make("test")],
    })

    .barrier("compiler-phases", {
        needs: ["named-call", "actor-send", "signature-use"],
        owner: Agent("integrator"),
        prove: [Make("test"), Make("fmt"), Make("determinism"), Fixpoint()],
    })

    .fan("quality-system", {
        after: "compiler-phases",
        lanes: ["verify-and-ci", "generated-c", "native-test-and-bench"],
    })
    .barrier("release", {
        needs: ["quality-system"],
        owner: Agent("integrator"),
        prove: [Make("verify"), CleanWorktree(), ReproducibleRelease()],
    })
    .build();
```

The execution rules are:

1. Scouts may inspect the whole tree but do not edit.
2. Implementers receive disjoint source and test ownership. Shared surfaces
   such as module roots, `Makefile`, `build.zen`, and documentation belong to
   one explicitly named lane, with the integrator as the default owner.
3. Each lane proves focused behavior before requesting a merge.
4. The integrator reviews the diff, resolves cross-lane contracts, and runs the
   barrier gates. Agents never regenerate or stage `seed/zen.c` independently.
5. A red barrier sends the failure back to the lane that owns the contract; it
   is not patched in a different lane merely because that agent is available.

### Agent waves

| Wave | Parallel agents | Integrator result |
| --- | --- | --- |
| 1 | call-lowering scout, actor/member scout, sema/style scout | build cards and non-overlapping ownership |
| 2 | `NamedCallSite`, `ActorSend`, `SignatureUse` implementers | compiler-phase barrier and one seed regeneration |
| 3 | verify/CI, generated-C/UBSan, native-test/benchmark implementers | authoritative `verify` graph |
| 4 | differential closure, performance budgets, release-state cleanup | 9.5 release barrier |

An agent lane is complete only when its proof is green and its comments read as
language contracts for an end user or their AI, not as a transcript of the
agent's work.

## The graph

```zen
Builder, BuildError, Dep, Step = std.build

quality = (b :: Builder, zen: Step) Res<Step, BuildError> {
    architecture = b.run("phase-ownership", {
        tool: zen,
        args: ["gate", "source-health"],
        needs: [zen],
    }).try();

    soundness = b.run("sema-implies-valid-c", {
        tool: zen,
        args: ["gate", "differential"],
        needs: [architecture],
    }).try();

    generated_c = b.run("generated-c", {
        tool: zen,
        args: ["gate", "warnings", "--cc", "gcc", "--cc", "clang"],
        needs: [soundness],
    }).try();

    tests = b.test("language-tests", {
        tests: b.module(Path("tests")).functions(b.alloc).try(),
        deps: [],
        needs: [soundness],
    }).try();

    benches = b.bench("compiler-budgets", {
        benches: b.module(Path("tests/bench")).functions(b.alloc).try(),
        budgets: compiler_budgets(),
        needs: [architecture, tests],
    }).try();

    release = b.run("release-state", {
        tool: zen,
        args: ["gate", "release-state"],
        needs: [generated_c, tests, benches],
    }).try();

    verify = b.group("verify", {
        needs: [
            architecture,
            soundness,
            generated_c,
            tests,
            benches,
            release,
        ],
    }).try();
    b.default(verify);
    Ok(verify)
}
```

`Dep` remains an import/link dependency. `Step` is an execution dependency.
Conflating them would make a quality gate look like a library and leak build
order into program linkage.

## Build cards

Each card ends at a command that can go red. A card is not complete when its
code lands; it is complete when its gate has been mutation-tested.

### A. Phase ownership

Build small immutable phase values where facts are discovered together and
share a lifetime. Do not store `CBackend`, `Checker`, or output buffers merely
to shorten signatures.

Order:

1. `NamedCallSite`: own bare-name closure, `Res`, print-sugar, and direct-call
   dispatch in `gen_c_call`.
2. `ActorSend` then `ActorSendEmission`: own settled actor-send facts without
   widening the `gen_c_member`/`gen_c_actor` cycle.
3. `SignatureUse`: distinguish an exact semantic call from a signature used
   only to recover nested diagnostics. A recovery signature may never become a
   successfully typed call.
4. Continue with `InlineSite`, member lookup, and expression-order queries only
   where a repeated bundle crosses at least three functions.

Gate: targeted corpus tests, `make test`, `make determinism`, and a ratcheting
source-health snapshot. No new function may exceed eight domain parameters
without an adjacent invariant explaining why they do not form one value.

### B. Semantic soundness

Enforce one backend contract:

> Every program accepted by sema lowers to supported, valid C; otherwise Zen
> emits a positioned diagnostic.

Close bound-member type/arity checks, indirect/local function arity, equality
operand agreement, ordinary union widening, and every differential-hunt class.
Reduce each failure to a corpus or must-fail test before fixing it. A recovery
path must check nested expressions but return poison after one primary
diagnostic; it must not commit resolution memos as if selection succeeded.

Gate: a maintained differential suite classifies each input as `ZEN_REJECTED`,
`CC_REJECTED`, `CC_WARNING`, `RAN_OK`, or `NONZERO_EXIT`. The accepted-to-C-
rejected count is zero.

### C. Generated C

Define supported compiler/flag sets and ratchet warnings to zero under GCC and
Clang. Cover evaluation order, signedness, overflow assumptions, aliasing,
unused control-flow artifacts, and deterministic symbol emission. Add UBSan to
the existing ASan/LSan door.

Gate: generated programs and the seed compile under the supported warning set;
ASan and UBSan are clean; the complete stage-2/stage-3 fixpoint is byte-identical.

### D. Language-native tests

Finish `Tester.expect_eq`, `Module.functions`, test discovery, per-test
allocation, failure reporting, and `zen test`. Every advertised `*_test.zen`
must be collected and type-checked. Preserve the Python corpus runner as an
outer compatibility oracle until the native runner proves the same collection.

Gate: collection manifests agree, deliberately uncollected and failing tests
make the gate red, and parse/format/parse plus formatter-idempotence properties
hold.

### E. Performance budgets

Finish `Bencher.iter`, `BenchStats`, `Builder.bench`, and budget execution.
Benchmark owned hot paths rather than only container micro-operations:
self-compile, name/member lookup, symbol ordering, incomplete-buffer parser
recovery, generic instantiation, and LSP edit-to-diagnostic latency.

Allocation limits are exact. Timing uses a recorded environment, warmups, a
rolling median, and an explicit tolerance. A benchmark belongs to the subsystem
whose regression it detects.

Gate: `compiler-budgets` fails on a deliberate quadratic regression and stays
stable across repeated unchanged runs.

### F. Builder and authoritative verification

Add `Step` to `std.build`; make `exe`, `test`, and `bench` return it; teach
`BuildPlan` to retain tests, benches, run steps, groups, defaults, and budgets.
Planning records a graph and never executes project code. Port Make targets one
at a time, retaining one `make verify` adapter.

`verify` owns the list: build, corpus/must-fail, format, determinism, full
fixpoint, generated-C warnings, sanitizers, benchmarks, editor checks, and
release-state checks. CI and releases call only this aggregate.

Gate: a clean checkout runs `make verify`; removing any child step makes a
builder-graph test fail.

### G. Project and release state

Every active correctness issue names an executable reproducer and expected
classification. Passing reproducers leave the active queue in the same change
that fixes them. Generated inventories are refreshed by one command. Add the
license, contribution and security policies, versioning, changelog, and
reproducible release checksums.

Gate: the issue/reproducer ledger has no stale entries, generated documents are
fresh, required release files exist, and a release rebuild matches its recorded
artifacts.

## Milestones

| Milestone | Required cards | Exit |
| --- | --- | --- |
| 8.5 | A first three phases, F compatibility gate | `make verify` exists and the current tree is green |
| 9.0 | B, C, D | no known sema-to-C hole; native tests collect every advertised test |
| 9.3 | E and builder execution graph | real compiler/LSP budgets fail on deliberate regressions |
| 9.5 | G plus cross-compiler/release matrix | one clean-checkout command proves a releasable tree |
