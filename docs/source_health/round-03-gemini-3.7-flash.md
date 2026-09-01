# Gemini 3.7 Flash review — round-03

Model: `gemini-3.7-flash`

# Source Architecture Review — Round-03

### 1. Ranked Implementation Lanes

```
+---------------------------------------------------------------------------------------------------+
| 1. gen_c_loop / gen_c_range: Introduce LoopSite/LoopWalk phase record for iteration lowering       |
| 2. gen_c_json: Encapsulate JSON lowering context across recursive value and record serializers    |
| 3. gen_c_assoc: Model AssocCall site for module-scoped and type-associated calls                  |
| 4. gen_c_try: Introduce TryPropagation phase record for error unwinding and set retagging         |
| 5. gen_c_call: Complete CallSite adoption across vararg packing and spread relays                  |
| 6. lsp_diag / lsp_query: Encapsulate WorkspaceTurn in LSP diagnostic publication and queries       |
+---------------------------------------------------------------------------------------------------+
```

#### Lane 1: Introduce `LoopSite` / `LoopWalk` Phase Record for Iteration Lowering
* **Files**: `src/gen/gen_c/gen_c_loop.zen`, `src/gen/gen_c/gen_c_range.zen`
* **Signatures / Types**:
  * `lower_loop*`, `lower_with_body`, `lower_shaped`, `lower_walk*`, `lower_led`, `lower_forever`, `lower_range`, `lower_range_impl`, `lower_settled`, `lower_bounded`, `lower_impl_walk`, `lower_supplied_walk` (8–10 parameters in `gen_c_loop.zen`).
  * `run_body*`, `bind_threaded`, `bind_named`, `bind_pair`, `bind_single`, `run_range_body` (7–9 parameters in `gen_c_loop.zen`).
  * `take_pass*`, `run_at`, `inline_at` (7–8 parameters in `gen_c_range.zen`).
* **Proposed Owner**: Introduce a `LoopSite` record in `gen_c_loop.zen` owning call facts `(id: ExprId, sh: Shape, lam: Lambda, ctx: Ctx, want: TyId, fold: Fold)`. When lowering ranges, let `RangeWalk` expand to own `(counter: str, base: str, limit: str, elem_ty: TyId)`.
* **Smallest Safe Boundary**: Keep `lower_loop*` as the public entry point. Keep range protocol detection and impl bounds calculation in `gen_c_range.zen`; do not merge the files. Keep `LoopFrame` label management intact.

#### Lane 2: Encapsulate JSON Lowering Context in `gen_c_json`
* **Files**: `src/gen/gen_c/gen_c_json.zen`
* **Signatures / Types**:
  * `json_receiver`, `json_result`, `json_value`, `json_primitive`, `json_named`, `json_record`, `json_fields`, `json_raw`, `json_write`, `json_unsupported` (6–8 parameters in `gen_c_json.zen`).
* **Proposed Owner**: Introduce `JsonLower` record owning `(id: ExprId, buffer: str, ret: TyId, result: str, done: usize, ctx: Ctx)`. Make `json_value`, `json_record`, `json_fields`, and `json_write` methods on `JsonLower`.
* **Smallest Safe Boundary**: Scope entirely within `gen_c_json.zen`. Keep `is_json_door*` and `lower_json_door*` entry signatures stable. Preserve dynamic struct field traversal and escape formatting.

#### Lane 3: Model `AssocCall` Lowering Site in `gen_c_assoc`
* **Files**: `src/gen/gen_c/gen_c_assoc.zen`
* **Signatures / Types**:
  * `write_module_call`, `assoc_at_site`, `assoc_member`, `write_assoc_call`, `emit_assoc_call`, `write_assoc_arg` (7–9 parameters in `gen_c_assoc.zen`).
* **Proposed Owner**: Introduce `AssocSite` record owning `(id: ExprId, c: Call, a: Access, ty: TyId, ctx: Ctx)`. Once resolved to a candidate, attach `(s: Site, f: Function, sig: Vec<TyId>, inst: Inst)`.
* **Smallest Safe Boundary**: Private emission inside `gen_c_assoc.zen`. Keep `lower_assoc_call*` signature unchanged.

#### Lane 4: Introduce `TryPropagation` Phase Record in `gen_c_try`
* **Files**: `src/gen/gen_c/gen_c_try.zen`
* **Signatures / Types**:
  * `lower_try_res`, `write_guard`, `map_and_propagate`, `map_error`, `lower_try_mapper`, `propagate`, `propagate_into`, `propagate_failure`, `propagate_error`, `propagate_wider`, `widen_or_report`, `widen_into_enum`, `widen_into_set`, `retag_or_report`, `write_propagation`, `write_built`, `write_tag_map`, `write_tag_case` (6–7 parameters in `gen_c_try.zen`).
* **Proposed Owner**: Introduce `TryPropagation` owning `(node: Expr, source: TyRes, target: TyRes, tmp: str, ctx: Ctx)`. Make error mapping and retagging methods on `TryPropagation`.
* **Smallest Safe Boundary**: Keep `lower_try*` and public helpers (`wrap_error*`, `carrier*`) unchanged. Preserve canonical error tag mapping and scope unwinding order (`unwind_to(0, "")`).

#### Lane 5: Complete `CallSite` Adoption Across Vararg Packing in `gen_c_call`
* **Files**: `src/gen/gen_c/gen_c_call.zen`
* **Signatures / Types**:
  * `write_call_args*`, `write_written_args`, `write_to_pack`, `write_pack`, `is_forwarded_pack`, `pack_typed_arg`, `write_forwarded`, `write_spread`, `write_run`, `write_pack_elems` (6–7 parameters in `gen_c_call.zen`).
* **Proposed Owner**: Extend `CallSite` methods to cover argument packing once `f: Function` and `sig: Vec<TyId>` are resolved.
* **Smallest Safe Boundary**: Keep `lower_call*`, `lower_plain_call*`, `write_call_args*`, and `write_extern*` signatures unchanged so external callers in `gen_c_member.zen`, `gen_c_expr.zen`, and `gen_c_assoc.zen` require no modifications.

#### Lane 6: Encapsulate Workspace Turns in LSP Diagnostics
* **Files**: `src/lsp/lsp_diag.zen`, `src/lsp/lsp_query.zen`
* **Signatures / Types**:
  * `Diagnostics.shared*`, `Diagnostics.settled*`, `Diagnostics.clear_closed`, `Diagnostics.build_owed`, `Diagnostics.told`, `Diagnostics.say_all`, `Diagnostics.say_one`, `Diagnostics.take_back` (6–8 parameters in `src/lsp/lsp_diag.zen`).
* **Proposed Owner**: Introduce `WorkspaceTurn` owning `(env: Env, workspace: str, uris: Vec<str>, docs: Map<str, str>, alloc: Alloc)` to represent a single document synchronization or publish cycle.
* **Smallest Safe Boundary**: Keep `Diagnostics` session state (`said`, `showing`, `built`) separate from ephemeral turn state. Do not alter JSON-RPC notification wire formatting.

---

### 2. Likely Bugs Identified

| Issue | File & Location | Evidence | Confidence |
| :--- | :--- | :--- | :--- |
| **Quadratic Expression Scan in LSP Definition Resolution** | `src/lsp/lsp_def.zen:288-301` (`called_decl`) | `called_decl` iterates linearly over all AST expression IDs via `Range(0, c.tree.expr_ids())` to find calls matching `id`. For large source files with thousands of expressions, resolving go-to-definition triggers full tree scans. Furthermore, if multiple call expressions share a callee ID, it takes the last match rather than matching the exact invocation at the cursor position. | **High** |
| **Incomplete Escaping in `json_raw`** | `src/gen/gen_c/gen_c_json.zen:351-364` (`json_raw`) | `json_raw` only escapes `"` and `\`. If `raw` contains control characters (such as `\n`, `\r`, or `\t`), it outputs literal raw bytes into the generated C string literal `(zg_str){ (unsigned char *)"..." }`, producing invalid C syntax with unescaped newlines in C string constants. | **High** |
| **Hard-coded ERROR Severity in LSP Diagnostic Serialization** | `src/lsp/lsp_diag.zen:288-316` (`write_plain_spot`, `write_noted_spot`) | `write_plain_spot` and `write_noted_spot` hard-code `severity: ERROR` (1) for all diagnostics published to the editor. Non-fatal warnings and informational notes emitted by compiler passes are forced to error status. | **Medium** |

---

### 3. Proposals from Prior Audit: Disposition

* **Introduce `BoundDispatch` and `BoundCall` in `gen_c_bound.zen`**: **COMPLETED & CONFIRMED**. `gen_c_bound.zen` now encapsulates fat pointer method resolution into `BoundDispatch.settle` and `BoundCall.emit`, reducing parameter lists cleanly.
* **Merge `gen_c_loop.zen`, `gen_c_range.zen`, and `gen_c_fold.zen`**: **REJECT**. Inspection of `gen_c_loop.zen` (795 lines) and `gen_c_range.zen` (496 lines) confirms their invariants are distinct: `gen_c_loop` manages C loop control frames, counter step labels, and body inlining; `gen_c_range` manages structural bounds extraction, prelude primitive range impls, and synthesized `at` pass execution. Merging them would create a 1,300+ line module with mixed concerns.
* **Replace `json_read.zen` and `json_stream.zen` with single AST parser**: **REJECT**. `json_read` requires zero-copy string slicing from stable buffers, while `json_stream` processes streamed chunks. They must share only token transition mechanics via `json_syntax.zen`, not memory ownership models.
* **Inline `gen_c_assoc.zen` into `gen_c_member.zen`**: **REJECT**. Associated functions (`Type.fn()`) do not accept a receiver and resolve via static module defs, whereas members (`val.fn()`) require receiver type matching and impl dispatch. Keeping them split maintains the clean separation specified in `GEN_C_SHAPE.md`.

---

### 4. Metric Delta Assessment

* **Judgement**: **Genuine Improvement**.
* **Reasoning**:
  * **Functions with 8+ Parameters**: Reduced from 102 to 96 (-6).
  * **Parameter Slots**: Reduced from 17,925 to 17,871 (-54).
  * **Relay Excess (>5 parameters)**: Reduced from 951 to 921 (-30).
  * **Lines of Code**: Net reduction of 408 lines (73,070 to 72,662).
  * **Comment Cleanup**: History markers dropped from 125 to 117 (-8); comment lines reduced by 298.
  * **Structural Quality**: Inspection of `gen_c_bound.zen` and `gen_c_inline.zen` confirms the reduction came from legitimate domain phase records (`BoundDispatch`, `BoundCall`, `InlineExpansion`, `InlineSite`), without artificial parameter bundling or moving backend/output buffers into long-lived structs.

---

### 5. Suggested Non-Overlapping Wave Assignments

```
====================================================================================================
AGENT 1: Loop and Iteration Lowering (Backend Control Flow)
  - Target: src/gen/gen_c/gen_c_loop.zen, src/gen/gen_c/gen_c_range.zen
  - Task: Implement LoopSite / RangeWalk phase records to eliminate the 14 functions with 8+
          parameters across lower_range, lower_settled, lower_bounded, run_body, and bind_threaded.
  - Inspection Chain: Trace lower_loop -> lower_with_body -> lower_shaped -> lower_walk ->
                      lower_range -> lower_bounded -> run_body in gen_c_loop.zen.
  - Verification: make test && make cap. Ensure generated C for counted loops and range iterations
                  remains bit-identical.

AGENT 2: Associated Calls and JSON Lowering (Backend Emission)
  - Target: src/gen/gen_c/gen_c_assoc.zen, src/gen/gen_c/gen_c_json.zen
  - Task: 1. Introduce AssocSite in gen_c_assoc.zen to shorten write_module_call and assoc_at_site.
          2. Introduce JsonLower in gen_c_json.zen to eliminate 6 functions with 8+ parameters
             across json_value, json_primitive, json_record, and json_fields. Fix json_raw escaping.
  - Inspection Chain: Trace lower_assoc_call -> assoc_at_site -> write_assoc_call in gen_c_assoc.zen;
                      trace lower_json_door -> json_receiver -> json_result -> json_value in gen_c_json.zen.
  - Verification: make test && make lint. Verify JSON serialization test cases pass.

AGENT 3: Try Propagation and LSP Diagnostic Contexts (Backend & Tooling)
  - Target: src/gen/gen_c/gen_c_try.zen, src/lsp/lsp_diag.zen, src/lsp/lsp_def.zen
  - Task: 1. Introduce TryPropagation in gen_c_try.zen to eliminate relays across error widening.
          2. Introduce WorkspaceTurn in lsp_diag.zen to eliminate 7-8 parameter method chains.
          3. Optimize called_decl in lsp_def.zen to avoid full-tree linear scans.
  - Inspection Chain: Trace lower_try -> lower_try_res -> write_guard -> propagate ->
                      propagate_into -> propagate_wider in gen_c_try.zen;
                      trace settled -> build_owed -> told -> say_all in lsp_diag.zen.
  - Verification: make test && make lsp-test. Verify LSP diagnostic and definition tests pass.
====================================================================================================
```
