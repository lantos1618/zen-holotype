# JavaScript Backend

`compiler.genjs` is experimental. It is not the bootstrap backend and it is not
yet a full language target. The shipping compiler path remains `compiler.genc`
to C plus `cc`.

The JS backend exists to prove that the compiler's shared AST is not C-shaped.
It walks the same `compiler.genc` `Expr` / `Stmt` / `Decl` values as the C
backend and emits JavaScript for the value-oriented computational subset.

## Supported Subset

The tested subset includes:

- functions, calls, recursion, local lets, assignment, returns;
- integer and float literals, arithmetic, comparisons, integer casts;
- structs as structural JS objects;
- enums as tagged JS objects;
- `.match` over enum tags;
- slices backed by JS arrays, indexing, and `loop`;
- block expressions and lowered lambdas/templates.

Programs in this subset are emitted by the Zen-written backend and run under
Node in `tests/test_genjs.py`.

## Explicitly Unsupported

Raw pointer and C-memory operations do not have a truthful JavaScript equivalent.
The backend emits `unsupported-in-js` comments for those operations instead of
pretending they work:

- raw `@...` primitive calls;
- `load`, `store`, `offset`, `addr`, `cstr`;
- `load_i64`, `store_i64`, `atomic_add_i64`;
- `null_ptr`.

Plain user functions named like C functions are not treated as magic. For
example, a user-defined `malloc` emits and calls a normal JS function.

## Decision

For now JS is a documented experimental backend for the computational subset.
It should stay tested and honest about unsupported memory constructs. Making it
first-class would require a CLI surface, module/linking story, runtime model,
and either a JS memory representation or a stronger rule that pointer programs
are outside the JS target.
