# Round 05 disposition

Gemini 3.7 Flash judged the round a genuine structural improvement. The full
repository gate also passed: 1,073 tests passed, one stage-6 test was deferred,
and lint reported no errors.

## Completed lanes

- `JsonLower` owns type-directed JSON emission: score 142 → 51.
- `TryPropagation` owns try/error-carrier lowering: 182 → 68.
- `WorkspaceTurn` owns one LSP publication turn: `lsp_diag` 132 → 59.
- `MatchCoverage` owns match-coverage-local state: 149 → 139 and no 8+
  parameter functions remain in the file.
- `MethodCallSite` now owns settled ordinary method calls: `gen_c_member`
  255 → 229. It remains high because specialized dispatch is deliberately
  outside that owner.

The whole-tree round reduced high-arity functions 81 → 68, relay excess
845 → 775, parameter slots 17,767 → 17,635, and repeated signature shapes
364 → 357.

## Bug claims

### `JsonLower.raw` doubled braces — rejected

`Alloc.String("(zg_str){{ ...")` is the allocating format door, not a raw byte
constructor. `{{` emits one literal `{`; the later `fmt` call closes it. The
typed-record JSON corpus and the full suite compile the generated C, so the
claimed unbalanced compound literal is not present.

### `write_position` unused backend receiver — design debt, not a bug

The body uses only its file/span/output arguments. Removing `be` mechanically
would turn method-shaped calls back into a free UFCS relay. A future cleanup
should choose a real owner—most plausibly the output writer plus a source
position—rather than merely deleting the receiver.

### `write_extern` rebuilds `CallSite` — confirmed cleanup lane

The wrapper accepts fields that already form `CallSite`, constructs it, and
immediately delegates. This is useful evidence for extending the existing
owner upward, but it does not change behavior and is not a correctness bug.

## Next review order

The next independent pass should inspect, without mechanically merging files:

1. residual call lowering in `gen_c_call`;
2. actor-send state in `gen_c_actor`;
3. member lookup state in `sema_member`;
4. pure expression-order queries in `gen_c_expr`.

`gen_c_member` should be revisited only where the current `MethodCallSite`
already exists; lifting it across intrinsic/capability selection without a
settled candidate would erase a real boundary.
