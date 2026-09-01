# Gemini 3.7 Flash review — round-02

Model: `gemini-3.7-flash`

### 1. Ranked Implementation Lanes

```
+---------------------------------------------------------------------------------------------------+
| 1. gen_c_loop / gen_c_range: Unify LoopWalk iteration phase state without merging files           |
| 2. gen_c_call: Extend CallSite through vararg packing and direct callee lowering                  |
| 3. gen_c_bound: Introduce BoundDispatch phase record for fat-pointer erased-method calls          |
| 4. gen_c_assoc: Model AssocCall site for module-scoped and type-associated calls                  |
| 5. json: Extract shared JSON syntax machine while preserving tree borrowing vs. streaming events  |
| 6. lsp: Decouple LSP query from CLI project driver and adopt typed diagnostic serializers         |
+---------------------------------------------------------------------------------------------------+
```

#### Lane 1: Unify `LoopWalk` Iteration Phase State Across `gen_c_loop` and `gen_c_range`
* **Files**: `src/gen/gen_c/gen_c_loop.zen`, `src/gen/gen_c/gen_c_range.zen`, `src/gen/gen_c/gen_c_fold.zen`
* **Signatures / Types**:
  * `lower_range`, `lower_range_impl`, `lower_settled`, `lower_bounded`, `lower_impl_walk`, `lower_forever` (8–10 parameters in `gen_c_loop.zen`)
  * `lower_supplied*`, `lower_impl_range`, `lower_impl_walk`, `take_pass*`, `run_at`, `inline_at` (7–10 parameters in `gen_c_range.zen`)
  * `run_body*` (9 parameters in `gen_c_loop.zen`)
* **Proposed Owner**: Introduce a `LoopWalk` record in `gen_c_loop.zen` (or `gen_c_shape.zen`) owning `id: ExprId`, `sh: Shape`, `target: ExprId`, `rty: TyId`, `lam: Lambda`, `ctx: Ctx`, `want: TyId`, and `fold: Fold`.
* **Smallest Safe Boundary**: Keep `lower_loop*` entry point and `lower_fold` accumulation logic untouched. Do not physically merge `gen_c_loop.zen` and `gen_c_range.zen`; pass `LoopWalk` to `gen_c_range` for impl-bound step extraction while keeping range storage predicates and pass generation cohesive.

#### Lane 2: Extend `CallSite` Through Vararg Packing and Direct Callee Lowering
* **Files**: `src/gen/gen_c/gen_c_call.zen`
* **Signatures / Types**:
  * `write_call_args*`, `write_written_args`, `write_to_pack`, `write_pack`, `is_forwarded_pack`, `pack_typed_arg`, `write_forwarded`, `write_spread`, `write_run`, `write_pack_elems` (7–8 parameters)
  * `CallSite` methods: `foreign_at`, `signature`, `settled`, `reachable`, `emit`
* **Proposed Owner**: Extend `CallSite` in `gen_c_call.zen` to own `f: Function`, `sig: Vec<TyId>`, `first: usize`, and `slot: usize` once resolved, converting `write_to_pack`, `write_spread`, and `write_run` into receiver methods on `CallSite`.
* **Smallest Safe Boundary**: Keep public `lower_call*`, `lower_plain_call*`, and `write_call_args*` signatures stable so callers in `gen_c_member.zen` and `gen_c_expr.zen` remain unaffected.

#### Lane 3: Introduce `BoundDispatch` Phase Record for Fat-Pointer Calls
* **Files**: `src/gen/gen_c/gen_c_bound.zen`
* **Signatures / Types**:
  * `lower_fat_call*`, `lower_answered_call`, `settle_call`, `read_slot`, `emit_fat_call`, `fat_args`, `fat_arg` (8–10 parameters)
* **Proposed Owner**: Introduce `BoundDispatch` (owning `c: Call`, `a: Access`, `rty: TyId`, `s: Site`, `slot: Slot`, `declared: Vec<TyId>`, `ret: TyId`, `targs: Inst`, `ctx: Ctx`).
* **Smallest Safe Boundary**: Encapsulate fat method dynamic dispatch and thunk size generation entirely within `gen_c_bound.zen`. Preserve `fat_ret_type*` and `slot_call*` public entry points.

#### Lane 4: Model `AssocCall` Lowering Site in `gen_c_assoc`
* **Files**: `src/gen/gen_c/gen_c_assoc.zen`
* **Signatures / Types**:
  * `write_module_call`, `assoc_at_site`, `assoc_member`, `write_assoc_call`, `emit_assoc_call`, `write_assoc_arg` (7–9 parameters)
* **Proposed Owner**: Introduce `AssocSite` owning `(id: ExprId, c: Call, a: Access, ty: TyId, s: Site, f: Function, sig: Vec<TyId>, inst: Inst, ctx: Ctx)`.
* **Smallest Safe Boundary**: Refactor private associated function emission in `gen_c_assoc.zen`. Keep `lower_assoc_call*` signature unchanged.

#### Lane 5: Extract Shared JSON Incremental Syntax Machine
* **Files**: `src/std/json/json_read.zen`, `src/std/json/json_stream.zen`
* **Signatures / Types**:
  * `decode_text_token*`, `number_token*`, `Reader*`, `Decoder*`
* **Proposed Owner**: Private syntax machine in `src/std/json/json_syntax.zen`.
* **Smallest Safe Boundary**: Extract escape, unicode, number, and container transition rules into `json_syntax.zen`. Keep `json_read.zen` borrowing `str` and lexemes directly from source; keep `json_stream.zen` owning streamed tokens. Delete the bridge helpers `decode_text_token` and `number_token`.

#### Lane 6: Decouple LSP Query from CLI Project Driver and Modernize Diagnostics
* **Files**: `src/lsp/lsp_query.zen`, `src/lsp/lsp_diag.zen`, `src/zen/zen_path.zen`
* **Signatures / Types**:
  * `Diagnostics.settled*`, `Diagnostics.build_owed`, `Diagnostics.told`, `Diagnostics.say_all`, `Diagnostics.say_one` (8–9 parameters)
  * `write_plain_spot`, `write_noted_spot`
* **Proposed Owner**: Decouple `lsp_query` from `zen.zen_build.Build`; move workspace resolution into query helpers below LSP. Convert `Diagnostics` reporting to use typed JSON serialization when omit/null policies allow.
* **Smallest Safe Boundary**: Preserve external LSP JSON-RPC framing and wire positions; change only internal compiler query invocation and diagnostic formatting.

---

### 2. Likely Bugs Identified

| Issue | File & Location | Evidence | Confidence |
| :--- | :--- | :--- | :--- |
| **Silent Swallowing of Missing Bound Impls** | `src/gen/gen_c/gen_c_bound.zen:280-310` (`bound_answered`, `table_answered`) | When checking `table_answered`, if an implementation table lookup fails or a bound cannot be resolved, `one_impl` returns `false` without reporting an error. If a user defines an impl with mismatched type parameters, it silently falls through to an "unsupported: bodiless member of a bound used as a value" error rather than a clear diagnostic identifying missing/malformed implementation bodies. | **Medium** |
| **Unsound Local Binding Release in Nested Expressions** | `src/gen/gen_c/gen_c_expr.zen:626-640` (`lower_consume`, `release_moved`) | `release_moved` unwraps `Name` and `Paren`, clearing `live` on the local binding. If `consume x` is used inside a sub-expression that subsequently fails code generation or is evaluated conditionally (e.g. inside short-circuiting or loop guards), the local is marked released in the frame unconditionally before verifying the statement actually commits. | **High** |
| **Hard-coded Error Constant in LSP Diagnostics** | `src/lsp/lsp_diag.zen:298-330` (`write_plain_spot`, `write_noted_spot`) | `severity` is hard-coded to `ERROR = 1` across all diagnostics emitted to the client, ignoring warning and info diagnostic levels produced by parser and semantic checker passes. | **High** |

---

### 3. Proposals from Prior Audit: Disposition

* **Introduce `InlineExpansion` and `InlineSite` Records**: **COMPLETED & CONFIRMED**. `gen_c_inline.zen` successfully encapsulated the 8–10 parameter inline expansion chain into `InlineExpansion` and `InlineSite` methods in round-02.
* **Merge `gen_c_loop`, `gen_c_range`, `gen_c_array`, and `gen_c_fold`**: **REJECT**. Inspection of `gen_c_range.zen` (622 lines) and `gen_c_loop.zen` (712 lines) proves that range protocol handling (impl-supplied bounds, synthesized `at` inlining) is distinct from loop frame control (`LoopFrame`, break/continue label management, counter step emission). Unifying them into one file would exceed 1,500 lines and obscure ownership. Share the `LoopWalk` record instead.
* **Replace JSON Streaming with Unified DOM Reader**: **REJECT**. `json_read.zen` relies on zero-copy borrowing from stable memory buffers, whereas `json_stream.zen` feeds from chunked I/O. They must share grammar transitions, not allocation strategies.
* **Replace `zen_build_plan.Executor` with General Comptime Evaluator**: **DEFERRED**. The comptime interpreter does not yet support sandboxed target capabilities or build graph step caching. Retain `zen_build_plan.zen` until evaluator capabilities are proven.

---

### 4. Metric Delta Assessment

* **Judgement**: **Genuine Improvement**.
* **Reasoning**:
  * **Functions with 8+ Parameters**: Dropped by 9 (from 111 to 102).
  * **Parameter Slots**: Dropped by 97 (from 18,022 to 17,925).
  * **Relay Excess (>5 parameters)**: Dropped by 43 (from 994 to 951).
  * **Total Lines**: Decreased by 87 (from 73,157 to 73,070) with 3 net new cohesive functions.
  * **Integrity**: Inspection of `gen_c_inline.zen` shows the metric reduction came from bona fide domain modeling (`InlineExpansion.run` and `InlineSite.bind`) rather than parameter bag hacks. The backend and output buffers are properly kept at method boundaries rather than bundled as struct fields.

---

### 5. Suggested Non-Overlapping Wave Assignments

```
====================================================================================================
AGENT 1: Loop & Range Lowering Phase Unification (Backend Iteration)
  - Target: src/gen/gen_c/gen_c_loop.zen, src/gen/gen_c/gen_c_range.zen, src/gen/gen_c/gen_c_fold.zen
  - Task: Implement LoopWalk phase record to eliminate 8-10 parameter relays across lower_range,
          lower_bounded, lower_supplied, and take_pass.
  - Inspection chain: Must read lower_range -> lower_range_impl -> lower_settled -> lower_bounded
                      in gen_c_loop.zen and lower_supplied -> lower_impl_walk in gen_c_range.zen.
  - Verification: make test && make cap. Verify no increase in mutual sibling imports.

AGENT 2: Call Site & Vararg Lowering Encapsulation (Backend Calls)
  - Target: src/gen/gen_c/gen_c_call.zen, src/gen/gen_c/gen_c_assoc.zen, src/gen/gen_c/gen_c_bound.zen
  - Task: Extend CallSite across write_to_pack/write_spread relays; implement AssocSite in
          gen_c_assoc.zen and BoundDispatch in gen_c_bound.zen.
  - Inspection chain: Read write_call_args -> write_to_pack -> write_spread -> write_run in
                      gen_c_call.zen and settle_call -> emit_fat_call in gen_c_bound.zen.
  - Verification: Diff emitted C code across compiler test suite.

AGENT 3: JSON Syntax Extraction & LSP Decoupling (Stdlib & Tooling)
  - Target: src/std/json/*, src/lsp/lsp_query.zen, src/lsp/lsp_diag.zen
  - Task: Extract shared json_syntax state machine and delete decode_text_token/number_token bridge.
          Sever zen_build import from lsp_query.zen and fix hard-coded severity in lsp_diag.zen.
  - Inspection chain: Read json_read.zen reader loop alongside json_stream.zen feed transitions.
  - Verification: JSON parser conformance suite and LSP integration tests.
====================================================================================================
```
