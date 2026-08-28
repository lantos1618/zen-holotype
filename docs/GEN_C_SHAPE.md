# Compiler structure migration

This is the execution map for reducing compiler plumbing without changing the
language or generated C. Line count is a result, not the design constraint.

## Baseline

Measured 2026-08-28:

| area | files | lines | alias/import lines | same-folder aliases | functions with 8+ parameters |
|---|---:|---:|---:|---:|---:|
| `gen_c` | 52 | 28,800 | 1,044 | 495 | 125 |
| `sema` | 42 | 20,659 | 545 | 345 | 8 |
| `lsp` | 18 | 5,862 | 206 | 70 | 4 |
| `fmt` | 5 | 2,067 | 46 | 8 | 1 |

`gen_c` also has 46 mutual sibling-import pairs. Its worst 8+ parameter
concentrations are `call` (23), `loop` (12), `build` (11), `ptr` (10) and
`inline` (10).

## Per-file problem register

The folder total hides small, dense relay files. This register ranks concrete
cleanup work; update a row when its phase conversion lands.

| file | evidence | primary problem | state |
|---|---|---|---|
| `loop` | 747 LOC, 205 signature slots, 12 high-arity functions, 4 mutual peers | loop/shape state relayed across helpers | next clean lane |
| `inline` | 743 LOC, 217 slots, 10 high-arity, 3 mutual peers | call, closure and destination state travel separately | pending |
| `build` | 686 LOC, 201 slots, 11 high-arity | cohesive construction state has no phase owner | pending |
| `ptr` | 564 LOC, 218 slots, 10 high-arity; seven identical 10-slot relays | numbered verb dispatch chain | completed: 409 LOC, 120 slots, 1 high-arity |
| `call` | 1,412 LOC, 407 slots, 6 high-arity, 4 mutual peers | mixed resolution/emission hub | active WIP; reconcile first |
| `member` | 1,012 LOC, 241 slots, 6 mutual peers | lookup, selection and emission share one hub | active WIP |
| `expr` | 1,191 LOC, 15 mutual peers, 351 comment-only lines | dependency hub plus history-heavy commentary | active WIP |
| `bound` | 777 LOC, 247 slots, 6 high-arity, 3 mutual peers | bound-call relay and cycles | pending |
| `assoc` | 396 LOC, 128 slots, 6 high-arity; 18/20 functions carry output | dense associated-call relay | active WIP |
| `range` | 662 LOC, 159 slots, 6 high-arity, 2 mutual peers | range/walk state split across helpers | coordinate with loop/fold |
| `cap` | 459 LOC, 124 slots, 5 high-arity | dispatcher relay and temporary strings | active WIP |
| `floor` | 275 LOC, 73 slots; core helpers take 10/12 parameters | format-floor call site has no owner | pending |
| `fold` | 268 LOC, 65 slots, 3 high-arity, 2 mutual peers | fold site repeated across recursion | coordinate with loop/range |
| `sink` | 1,046 LOC, 310 slots, 6 high-arity | formatting walk and error routing relayed separately | completed: 874 LOC, 279 slots, 2 exported high-arity APIs |
| `fs` | 667 LOC, 176 slots, 6 high-arity | read/result operation tuples repeated | completed: 559 LOC, 155 slots, 1 exported high-arity API |
| `flow` | 910 LOC, 289 slots | pattern type/place repeated through two walks | completed: 764 LOC, 264 slots |
| `infer` | 411 LOC, 122 slots, 2 high-arity | return and unification tuples repeated | completed: 304 LOC, 88 slots, no high-arity |

Safe order is `loop` then `build`, coordinated `fold/range`, `inline`, `floor`
and `bound`. Files marked active WIP land only after their semantic changes are
committed, so a structural cherry-pick cannot overwrite them.

## Desired shape

```text
AST + Checker memos
        |
        v
  CallSite / InlineSite / FsReadPlan       immutable phase inputs
        |
        v
  CBackend receiver methods               sequencing and owned state
        |
        v
  focused emitters                         C text only
        |
        v
  lazy native floors                       requested only when reachable
```

Rules:

- A record bundles values created together and never mutated independently.
- Derived data travels with its source; do not pass both separately.
- The principal type is the receiver: `be.write(...)`, `c.type_of(...)`.
- A classifier returns one enum and is matched once; it is not a call chain.
- Traits describe substitutability. They are not a way to split one concrete
  type across files.
- Keep a file boundary only when it names a distinct decision or data owner.

## What stays split

- `gen_c_member` / `gen_c_impl`: member lookup versus impl selection.
- `gen_c_expr` / `gen_c_call`: expression dispatch versus call lowering.
- `gen_c_shape`: shared by loop, range and array lowering.
- `lsp_serve` / `lsp_reply`: session lifecycle versus JSON-RPC shapes.
- `sema_type` / `sema_try`: general typing versus failure propagation.
- `sema_member` / `sema_static`: value access versus `Type.NAME`.

Combining these would conceal dependencies rather than remove them.

## Phase 1 — remove false boundaries

1. Make the 500/800 line counts review notes, never a reason to split one
   subject. Replace the hard failure with direct structural measurements.
2. Delete forwarding-only modules such as `lsp_decl.zen`.
3. Consolidate the repeated LSP root/overlay/build/query setup.
4. Move generic result and block-emission helpers out of capability floors,
   breaking `cap` cycles with FS, env, stdin and threads.

Exit criteria:

- no forwarding-only module remains in LSP;
- at least five `gen_c` mutual imports are gone;
- targeted LSP and capability tests are unchanged.

## Phase 2 — stop forwarding call state

Introduce records one pipeline at a time:

```zen
CallSite = {
    id: ExprId,
    call: Call,
    ctx: Ctx,
    want: TyId,
}

InlineSite = {
    call: CallSite,
    inst: Inst,
    ret: TyId,
}
```

`FsReadPlan` similarly owns the types, generated names and result destination
currently threaded through `read_body` and `run_and_read`.

Landing order:

1. `gen_c_call`
2. `gen_c_inline`
3. `gen_c_bound`
4. `gen_c_fs`
5. remaining files with 8+ parameters

Each commit changes one pipeline and must reduce its high-arity count.

## Phase 3 — receivers and owned impls

- Convert `foo(be, ...)` to `be.foo(...)` and `foo(c, ...)` to `c.foo(...)`.
- Move behavior already colocated with `Own` and `Pats` into their structs.
- Delete imports made unnecessary by receiver resolution.
- Do not add an out-of-line extension form. Zen already has `impl`, and an
  impl stays in the module that owns its target.
- Use `impl` only for a real reusable bound. If a lowering phase needs that
  shape, give the phase its own type in the same module:

```zen
CallLower.impl(LowerPhase, { lower = (...) { ... } })
```

Do not create one trait per file merely to distribute `CBackend`: that repeats
every signature. A universal `CBackend` fact lives with `CBackend`; an
operation owned by one lowering module remains a UFCS receiver call; a true
phase contract uses a phase type plus `impl`.

## Phase 4 — comments and public surface

- Keep invariants, ownership, ordering and non-obvious failure reasons.
- Delete chronology, issue narratives, repeated examples and comments that
  restate the next statement.
- Export a helper only when a different subject consumes it.
- Recount folder-root re-exports after every consolidation.

## Targets

| measure | baseline | first target |
|---|---:|---:|
| `gen_c` same-folder aliases | 495 | below 300 |
| `gen_c` mutual sibling imports | 46 | below 20 |
| `gen_c` functions with 8+ parameters | 125 | below 50 |
| principal-receiver free calls | 1,153 | 0 |
| compiler/LSP handwritten lines | 57,388 | reduce 10–20% |

## Verification

For every structural commit:

1. focused tests for the touched pipeline;
2. `make lint`, formatter check and structural metrics;
3. build the self-hosted compiler;
4. fixpoint for cross-module signature changes;
5. compare old and new compilers on one frozen source tree when the change
   claims to be behavior-preserving.

Do not compare compilers on different source trees: source positions make
that differential meaningless. Do not regenerate the seed per lane; do it
once after the integrated series is green.
