# Gemini 3.7 Flash review — round-04

Model: `gemini-3.7-flash`

# Source Architecture Review — Round-04

### 1. Ranked Implementation Lanes

```
+----------------------------------------------------------------------------------------------------+
| 1. gen_c_json: Encapsulate JsonLower phase record and resolve literal escaping in json_raw         |
| 2. gen_c_try: Introduce TryPropagation phase record for error unwinding, retagging, and mapping   |
| 3. sema_match: Encapsulate CoverageMatrix / MatchCoverage walk in Maranget usefulness engine       |
| 4. lsp_diag / lsp_def: Introduce WorkspaceTurn in diagnostic publishing and index called_decl      |
| 5. gen_c_call: Consolidate CallSite across write_res_payload and plain UFCS relays                 |
| 6. gen_c_member: Model MethodCallSite for receiver-taking method resolution and argument emission  |
+----------------------------------------------------------------------------------------------------+
```

#### Lane 1: Encapsulate `JsonLower` Phase Record and Fix Escaping in `gen_c_json`
* **Files**: `src/gen/gen_c/gen_c_json.zen`
* **Signatures / Types**:
  * `json_receiver`, `json_result`, `json_value`, `json_primitive`, `json_named`, `json_record`, `json_fields`, `json_raw`, `json_write`, `json_unsupported` (6–8 parameters each).
* **Proposed Owner**: Introduce a private `JsonLower` record owning `(id: ExprId, buffer: str, ret: TyId, result: str, done: usize, ctx: Ctx)`. Make `json_value`, `json_primitive`, `json_named`, `json_record`, `json_fields`, and `json_write` methods on `JsonLower`.
* **Smallest Safe Boundary**: Keep `is_json_door*` and `lower_json_door*` entry signatures stable. Ensure zero-copy string references and allocator-passed dynamic objects are preserved in generated C.

#### Lane 2: Introduce `TryPropagation` Phase Record in `gen_c_try`
* **Files**: `src/gen/gen_c/gen_c_try.zen`
* **Signatures / Types**:
  * `lower_try_res`, `write_guard`, `map_and_propagate`, `map_error`, `lower_try_mapper`, `propagate_into`, `propagate_failure`, `propagate_error`, `propagate_wider`, `widen_or_report`, `widen_into_enum`, `widen_into_set`, `retag_or_report`, `write_propagation`, `write_built`, `write_tag_map`, `write_tag_case`, `write_err_init` (6–8 parameters each).
* **Proposed Owner**: Introduce `TryPropagation` owning `(node: Expr, source: TyRes, target: TyRes, tmp: str, ctx: Ctx)`. Make error mapping, member retagging, and propagation return emission methods on `TryPropagation`.
* **Smallest Safe Boundary**: Keep `lower_try*` and public helpers (`wrap_error*`, `carrier*`) unchanged. Preserve the early scope unwinding order (`unwind_to(0, "")`) before returning errors.

#### Lane 3: Encapsulate `CoverageMatrix` / `MatchCoverage` in `sema_match`
* **Files**: `src/sema/sema_match.zen`
* **Signatures / Types**:
  * `norm_arms`, `plain_ctor`, `norm_set_ctor`, `norm_qualified`, `norm_member_dot`, `norm_binder`, `check_coverage`, `run_coverage`, `arm_reachable`, `check_exhaustive`, `useful*`, `useful_head`, `useful_ctor`, `useful_lit`, `useful_wild`, `useful_split`, `useful_one_case`, `useful_default`, `specialise`, `spec_row`, `spec_wild`, `spec_ctor`, `spec_keep`, `specialise_lit`, `lit_row`, `emit_row` (5–6 parameters relayed recursively).
* **Proposed Owner**: Introduce a `CoverageWalk` record owning `(checker: Checker, pats: Pats, sty: TyId)` to encapsulate matrix specialization and usefulness recursion over Maranget pattern matrices.
* **Smallest Safe Boundary**: Keep `match_type*`, `norm_pattern*`, `Pats*`, `PatMatrix*`, and `bind_pattern*` signatures unchanged. Retain diagnostic reporting order and uncovered case synthesis.

#### Lane 4: Encapsulate `WorkspaceTurn` in `lsp_diag` and Optimize `lsp_def`
* **Files**: `src/lsp/lsp_diag.zen`, `src/lsp/lsp_def.zen`
* **Signatures / Types**:
  * `Diagnostics.shared*`, `Diagnostics.settled*`, `Diagnostics.clear_closed`, `Diagnostics.build_owed`, `Diagnostics.told`, `Diagnostics.say_all`, `Diagnostics.say_one`, `Diagnostics.take_back` (6–8 parameters in `lsp_diag.zen`).
  * `called_decl`, `callee_of` in `lsp_def.zen`.
* **Proposed Owner**: Introduce `WorkspaceTurn` in `lsp_diag.zen` owning `(env: Env, workspace: str, uris: Vec<str>, docs: Map<str, str>, alloc: Alloc)`. In `lsp_def.zen`, index caller lookups to avoid full-tree scans across all expressions.
* **Smallest Safe Boundary**: Keep `Diagnostics` session lifecycle intact (`built`, `said`, `showing`). Keep wire protocol JSON-RPC payloads bit-for-bit compatible.

#### Lane 5: Complete `CallSite` Adoption for `write_res_payload` and Plain Calls in `gen_c_call`
* **Files**: `src/gen/gen_c/gen_c_call.zen`
* **Signatures / Types**:
  * `write_res_payload*` (8 parameters), `lower_plain_call*` (8 parameters), `write_extern*` (9 parameters), `travelled_for`, `lower_named_call`, `lower_sugar_or_plain`, `lower_res_arg`.
* **Proposed Owner**: Move `write_res_payload` and `res_ctor` lowering to methods on or constructors of a unified `ResInit` / `CallSite` value.
* **Smallest Safe Boundary**: Retain `CallSite` and `CallArgs` public API. Preserve the exact compound literal formatting `({}){ .zg_tag = ... }`.

#### Lane 6: Model `MethodCallSite` in `gen_c_member`
* **Files**: `src/gen/gen_c/gen_c_member.zen`
* **Signatures / Types**:
  * `lower_method`, `lower_ordinary_method`, `write_method_call`, `method_inst`, `emit_method_call`, `keep_fits`, `keep_if_fits` (6–8 parameters in `gen_c_member.zen`).
* **Proposed Owner**: Extend `Dot` and `Site` into a settled `MethodCallSite` owning `(dot: Dot, site: Site, func: Function, ctx: Ctx, want: TyId)` once overload resolution selects a method candidate.
* **Smallest Safe Boundary**: Keep `lower_dot_call*`, `member_symbol*`, `method_sig*`, and `lower_eq_call*` entry points unchanged.

---

### 2. Likely Bugs Identified

| Issue | File & Location | Evidence | Confidence |
| :--- | :--- | :--- | :--- |
| **Malformed String Literal & Byte Count Mismatch in `json_raw`** | `src/gen/gen_c/gen_c_json.zen:349-366` | `json_raw` only escapes `"` and `\` via `(b == '"' \|\| b == '\\').then(...)`. If `raw` contains newlines (`\n`), carriage returns (`\r`), or control bytes, raw unescaped bytes are written into the C literal `"(zg_str){ (unsigned char *)\"..."`. Unescaped newlines in C string constants cause compilation failure in `cc`. Furthermore, adding backslashes increases the C string length while `literal.fmt("\", {}u }}", raw.len)` hard-codes `raw.len`, producing a corrupted `zg_str` slice length. | **High** |
| **Underflow Risk in `Decoder.phase` on Empty Frame Stack** | `src/std/json/json_stream.zen:400-403` | `Decoder.phase` reads `self.frames.get(self.frames.len - 1)`. If `self.frames` is empty (e.g. at document root or after error recovery), `self.frames.len - 1` underflows in unsigned arithmetic to `usize.MAX`. While currently guarded at call sites in `ready`, `set_phase` and helper methods assume non-empty frames without asserting invariants. | **Medium** |
| **Unindexed Linear AST Walk in `called_decl`** | `src/lsp/lsp_def.zen:288-301` | `called_decl` iterates over `Range(0, c.tree.expr_ids())` to match `callee.index == id.index`. For large ASTs with tens of thousands of expressions, every hover and definition query triggers a full-file linear scan instead of reading from a call index or target map. | **Medium** |

---

### 3. Proposals from Prior Audit: Disposition

* **Introduce `LoopSite` and `RangeWalk` in `gen_c_loop.zen`**: **COMPLETED & CONFIRMED**. Round-04 successfully introduced `LoopSite` and `RangeWalk`, reducing parameter lists and eliminating 5 functions with 8+ parameters.
* **Merge `gen_c_loop.zen`, `gen_c_range.zen`, and `gen_c_fold.zen`**: **REJECT**. Inspection of `gen_c_loop.zen` (727 lines) confirms that iteration control flow and body inlining are distinct from range bounds arithmetic (`gen_c_range.zen`) and fold accumulation (`gen_c_fold.zen`). Merging them would create a 1,500+ line monolith violating single-subject ownership.
* **Combine `json_read.zen` and `json_stream.zen` into a single AST parser**: **REJECT**. `json_read` depends on zero-copy borrowed slices (`str`) from stable memory, whereas `json_stream` requires owned token buffers (`String`) across arbitrary feed boundaries. Unifying their AST parser would force streaming token allocation onto zero-copy tree parsing.
* **Consolidate `gen_c_assoc.zen` into `gen_c_member.zen`**: **REJECT**. Associated functions (`Type.fn()`) do not accept a receiver and resolve against static module definitions, whereas methods (`val.fn()`) require dynamic receiver type instantiation. Keeping them split maintains the clean separation specified in `GEN_C_SHAPE.md`.
* **Replace `called_decl` in `lsp_def.zen` with a reverse call map**: **ACCEPT & MODIFY**. Rather than rebuilding the whole semantic checker call map, maintain an expression-to-call lookup or index during checker queries to avoid full AST scans.

---

### 4. Metric Delta Assessment

* **Judgement**: **Genuine Improvement**.
* **Reasoning**:
  * **Functions with 8+ Parameters**: Dropped from 96 to 81 (-15), a 15.6% reduction in a single round.
  * **Parameter Slots**: Decreased from 17,871 to 17,767 (-104).
  * **Relay Excess (>5 parameters)**: Dropped from 921 to 845 (-76).
  * **Lines of Code**: Net reduction of 219 lines (72,662 to 72,443).
  * **History Markers & Comments**: History comment markers dropped from 117 to 115 (-2); comment lines decreased by 59 without losing semantic contracts.
  * **Structural Authenticity**: Inspection of `gen_c_loop.zen` (`LoopSite`, `RangeWalk`), `gen_c_call.zen` (`CallArgs`), and `gen_c_inline.zen` (`InlineExpansion`, `InlineSite`) verifies that reductions came from genuine domain phases, not decorative parameter bags or hidden global state.

---

### 5. Suggested Non-Overlapping Wave Assignments

```
====================================================================================================
AGENT 1: JSON Emission & Call Construction (Backend Generation)
  - Target: src/gen/gen_c/gen_c_json.zen, src/gen/gen_c/gen_c_call.zen
  - Task: 1. Introduce JsonLower record in gen_c_json.zen to eliminate 6 functions with 8+ parameters
             across json_value, json_primitive, json_record, and json_fields.
          2. Fix C string literal escaping and byte-length tracking in json_raw.
          3. Unify write_res_payload into a clean ResInit/CallSite method in gen_c_call.zen.
  - Inspection Chain: Trace lower_json_door -> json_receiver -> json_result -> json_value ->
                      json_fields in gen_c_json.zen; trace write_res_payload in gen_c_call.zen.
  - Verification: make test && make cap. Ensure JSON encoding and call generation tests pass.

AGENT 2: Try Propagation & Member Call Lowering (Backend Monomorphization & Lowering)
  - Target: src/gen/gen_c/gen_c_try.zen, src/gen/gen_c/gen_c_member.zen
  - Task: 1. Implement TryPropagation record in gen_c_try.zen to eliminate 3 functions with 8+ parameters
             and 15+ relay chains across error mapping, retagging, and early returns.
          2. Introduce MethodCallSite in gen_c_member.zen to encapsulate settled method facts
             (Dot, Site, Function, Inst, sig).
  - Inspection Chain: Trace lower_try -> lower_try_res -> write_guard -> propagate ->
                      propagate_into -> propagate_wider in gen_c_try.zen; trace lower_method ->
                      lower_ordinary_method -> write_method_call in gen_c_member.zen.
  - Verification: make test && make lint. Ensure error set widening and method dispatch tests pass.

AGENT 3: Pattern Match Coverage & LSP Diagnostics (Semantic Analysis & Tooling)
  - Target: src/sema/sema_match.zen, src/lsp/lsp_diag.zen, src/lsp/lsp_def.zen
  - Task: 1. Introduce CoverageWalk / MatchCoverage context in sema_match.zen to clean up Maranget
             matrix specialization recursion (useful, useful_ctor, specialise, spec_row).
          2. Introduce WorkspaceTurn in lsp_diag.zen to eliminate 4 functions with 8+ parameters.
          3. Optimize called_decl in lsp_def.zen to avoid full-tree linear scans.
  - Inspection Chain: Trace match_type -> check_coverage -> run_coverage -> arm_reachable ->
                      useful -> useful_ctor in sema_match.zen; trace settled -> clear_closed ->
                      build_owed -> told -> say_all in lsp_diag.zen.
  - Verification: make test && make lsp-test. Verify compiler match diagnostics and LSP tests pass.
====================================================================================================
```
