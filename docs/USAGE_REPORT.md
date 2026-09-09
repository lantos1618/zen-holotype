# Checked source usage and review

The usage tool is a Zen program. It loads the requested entry and imports with
`Build.whole`, visits the checked AST and writes `zen-usage-v1` JSON. An optional
Markdown pack includes bounded source excerpts and call evidence from the same
loader-captured bytes. Nothing is uploaded or changed by the tool.

Build the tool against the compiler source and standard library:

```
./zen build src --entry ../scripts/zen_usage.zen --std src --emit-c -o build/source_health/zen-usage.c
cc -O1 build/source_health/zen-usage.c -o build/source_health/zen-usage -pthread -lm
```

Invoke the resulting executable as:

```
zen-usage SOURCE_ROOT ENTRY STD_ROOT main OUTPUT.json [--review REVIEW.md]
zen-usage SOURCE_ROOT ENTRY STD_ROOT loaded_exports OUTPUT.json [--review REVIEW.md]
```

Keep outputs under ignored `build/source_health/`. Use absolute roots when
passing results between tools. Relative roots are relative to the command's
working directory. A source span's file is compilation-root-relative, except
`std/...` paths use the selected standard-library root. Spans are half-open;
lines and byte columns start at one.

Loading, parsing or checking errors refuse analysis. `main` requires exactly
one top-level main in the entry module. `loaded_exports` roots every exported
declaration in the loaded modules; it does not discover arbitrary external
consumers or load the entire repository. Root policy is recorded in the output.

## Reading the facts

Declaration IDs contain module and declaration indexes from this parse.
Names, declaration kinds and source spans accompany IDs so overloads and
same-named declarations remain distinct. IDs are not stable across edits.

A direct call points to the declaration selected by the checker. Constructor
calls are separate facts. Compiler-marked reflection calls are intrinsic facts.
Calls without a recorded declaration are unresolved facts; that includes
currently incomplete method, callback and actor dispatch information. Function
values without a recorded invocation also create uncertainty.

The shared AST traversal preserves structural ownership. Calls in lambdas,
member bodies, nested declarations, signature/default expressions and generic
bodies remain visible. They are attached to their containing top-level
owner, marked nested, and excluded from ordinary direct-call propagation.
Targets named by those deferred facts receive conservative retention status.

The report's graph uses a worklist over selected direct calls from its roots.
It does not count runtime executions or assume both sides of every branch run.
Statuses mean:

- `root`: selected by the recorded root policy.
- `known_reachable`: connected to a root by the report's direct-call edges.
- `conservative`: the current facts do not support ordinary reachability
  classification, including deferred targets, generic bodies, non-root exports and non-functions.
- `review_candidate`: no root path was established by those known edges.

A review candidate is **not proven unused**. Every report records
`complete: false` and `deletion_safe: false`. Missing call identities, implicit
cleanup, type/field usage, reflection, exported APIs, generated actor adapters
and indirect function values prevent automatic source removal. Never relabel
absence from this graph as “no callers.”

The JSON is explicitly unstamped: its source roots and spans do not identify an
immutable file revision. The optional Markdown is rendered from source text
captured while loading that same checked program, avoiding a second disk read.
Consumers persisting the JSON independently must record source hashes or a
snapshot revision and verify freshness before joining it to later bytes.

## Development loop

Review candidates with their known callers, callees, uncertainty and source
bodies. Assign bounded edits to an agent, then recheck the changed program and
run meaningful behavior tests. Compare subsequent reports only with recorded
source identity and root policy. Source deletion or executable tree shaking
requires stronger evidence than this first report supplies.

C emission is separate evidence. The current C backend roots concrete
non-callback functions in the entry module, not only main. Its symbol map omits
inlined functions and generated adapters. Neither presence nor absence there
replaces the checked usage facts.

The corpus fixture `sema/usage_report` covers overload identity, deferred
callback/member targets, unresolved dispatch, generic conservatism, explicit
export roots, escaped deterministic JSON and invalid-input refusal. The shared
AST walk fixture guards embedded type expressions and balanced ownership.
