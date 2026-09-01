# Gemini 3.7 Flash review — round-03

Model: `gemini-3.7-flash`

### 1. Ranked Implementation Lanes

```
+---------------------------------------------------------------------------------------------------+
| 1. gen_c_loop / gen_c_range: Model LoopWalk phase record without merging loop control and ranges   |
| 2. gen_c_call: Extend CallSite through vararg packing and direct callee lowering                  |
| 3. gen_c_assoc: Model AssocSite for module-scoped and type-associated calls                       |
| 4. gen_c_member / gen_c_cap: Structure DotSite and CapabilityCall phase dispatch                  |
| 5. lsp_diag / lsp_query: Decouple workspace query from CLI driver and use typed serializers       |
| 6. json: Extract shared JSON syntax machine while preserving tree borrowing vs. streaming events  |
+---------------------------------------------------------------------------------------------------+
```

#### Lane 1: Model `LoopWalk` Phase Record Across `gen_c_loop.zen` and `gen_c_range.zen`
* **Files**: `src/gen/gen_c/gen_c_loop.zen`, `src/gen/gen_c/gen_c_range.zen`, `src/gen/gen_c/gen_c_fold.zen`
* **Signatures / Types**:
  * `lower_range`, `lower_range_impl`, `lower_settled`, `lower_bounded`, `lower_impl_walk`, `lower_forever` (8–10 parameters in `gen_c_loop.zen`)
  * `lower_supplied_walk`, `run_range_body`, `run_body*` (8–9 parameters in `gen_c_loop.zen`)
  * Impl bound and pass helpers in `gen_c_range.zen` (`supplied_bound`, `take_pass`)
* **Proposed Owner**: Introduce an immutable `LoopWalk` record in `gen_c_loop.zen` (or `gen_c_shape.zen`) owning `id: ExprId`, `sh: Shape`, `target: ExprId`, `rty: TyId`, `lam: Lambda`, `ctx: Ctx`, `want: TyId`, and `fold: Fold`.
* **Smallest Safe Boundary**: Keep `lower_loop*` entry point, `LoopFrame` stack management, and `Fold` accumulator logic intact. Do not merge `gen_c_loop.zen` and `gen_c_range.zen`; pass `LoopWalk` across the sibling boundary to resolve supplied bounds while leaving range storage predicates in `gen_c_range.zen`.

#### Lane 2: Extend `CallSite` Through Vararg Packing and Direct Callee Lowering
* **Files**: `src/gen/gen_c/gen_c_call.zen`
* **Signatures / Types**:
  * `write_call_args*`, `write_written_args`, `write_to_pack`, `write_pack`, `is_forwarded_pack`, `pack_typed_arg`, `write_forwarded`, `write_spread`, `write_run`, `write_pack_elems` (7–8 parameters)
  * `CallSite` methods: `foreign_at`, `signature`, `settled`, `reachable`, `emit`
* **Proposed Owner**: Extend `CallSite` in `gen_c_call.zen` to own `f: Function`, `sig: Vec<TyId>`, `first: usize`, and `slot: usize` once the callee is resolved. Make `write_to_pack`, `write_spread`, and `write_run` receiver methods on `CallSite`.
* **Smallest Safe Boundary**: Keep public `lower_call*`, `lower_plain_call*`, and `write_call_args*` entry signatures stable so callers in `gen_c_member.zen` and `gen_c_expr.zen` remain unchanged.

#### Lane 3: Model `AssocSite` Lowering Site in `gen_c_assoc.zen`
* **Files**: `src/gen/gen_c/gen_c_assoc.zen`
* **Signatures / Types**:
  * `assoc_at_site`, `assoc_member`, `write_assoc_call`, `emit_assoc_call`, `write_assoc_arg` (7–9 parameters)
  * `write_module_call`, `module_fn_decl` (7–8 parameters)
* **Proposed Owner**: Introduce `AssocSite` owning `id: ExprId`, `c: Call`, `a: Access`, `ty: TyId`, `s: Site`, `ctx: Ctx`, and once resolved, `f: Function`, `sig: Vec<TyId>`, `inst: Inst`.
* **Smallest Safe Boundary**: Encapsulate associated call resolution and emission within `gen_c_assoc.zen`. Keep `lower_assoc_call*` signature unchanged.

#### Lane 4: Structure `DotSite` and `CapabilityCall` Phase Dispatch
* **Files**: `src/gen/gen_c/gen_c_member.zen`, `src/gen/gen_c/gen_c_cap.zen`
* **Signatures / Types**:
  * `Dot` (in `gen_c_member.zen`), `lower_resolved_dot`, `lower_receiver_site`, `with_site`, `supplied_or_ufcs`, `declared_member`, `supplied_member`, `lower_method`, `write_method_call`, `emit_method_call` (7–8 parameters)
  * `CapabilityCall` (in `gen_c_cap.zen`)
* **Proposed Owner**: Elevate `Dot` to `DotSite`, making `with_site`, `pick_member`, and `lower_method` receiver methods on `DotSite`. Pass `CapabilityCall` directly to `gen_c_cap.zen`.
* **Smallest Safe Boundary**: Keep `lower_dot_call*`, `member_symbol*`, and `method_sig*` public interfaces stable. Do not merge `gen_c_member.zen` and `gen_c_cap.zen`.

#### Lane 5: Decouple LSP Query from CLI Driver and Modernize Diagnostics
* **Files**: `src/lsp/lsp_diag.zen`, `src/lsp/lsp_def.zen`, `src/lsp/lsp_query.zen`
* **Signatures / Types**:
  * `Diagnostics.settled*`, `Diagnostics.build_owed`, `Diagnostics.told`, `Diagnostics.say_all`, `Diagnostics.say_one` (8–9 parameters)
  * `write_plain_spot`, `write_noted_spot` in `lsp_diag.zen`
* **Proposed Owner**: Decouple `lsp_query` from `zen.zen_build`; move workspace lookup below LSP into compiler query helpers. Adopt typed JSON serialization for diagnostics once omit/null policies allow.
* **Smallest Safe Boundary**: Preserve external LSP JSON-RPC wire protocol and framing; modify only internal workspace query invocations and response builders.

#### Lane 6: Extract Shared JSON Incremental Syntax Machine
* **Files**: `src/std/json/json_read.zen`, `src/std/json/json_stream.zen`
* **Signatures / Types**:
  * `decode_text_token*`, `number_token*`, `Reader*`, `Decoder*`
* **Proposed Owner**: Private syntax machine in `src/std/json/json_syntax.zen`.
* **Smallest Safe Boundary**: Extract escape, unicode, number, and container transition rules into `json_syntax.zen`. Retain `json_read.zen` borrowing `str` and lexemes directly from source; retain `json_stream.zen` owning streamed tokens. Delete the bridge helpers `decode_text_token` and `number_token`.

---

### 2. Likely Bugs Identified

| Issue | File & Location | Evidence | Confidence |
| :--- | :--- | :--- | :--- |
| **Premature Local Release on Move in Uncommitted Expressions** | `src/gen/gen_c/gen_c_expr.zen:626-640` (`lower_consume`, `release_moved`) | `release_moved` unwraps `Name` and `Paren`, calling `be.release_binding(n.text)` to clear `live`. Because `release_moved` runs immediately before evaluating `x.operand`, if the enclosing expression fails or is inside a speculative/short-circuiting branch (such as a conditional operand), the variable is marked dead in the frame regardless of whether the move statement actually commits. | **High** |
| **Hard-coded Error Severity in LSP Diagnostics** | `src/lsp/lsp_diag.zen:298-330` (`write_plain_spot`, `write_noted_spot`, `ERROR`) | `severity` is hard-coded to `ERROR = 1` across all diagnostics emitted to the client. Warning or informational diagnostics produced by parser or semantic checker passes are reported as hard errors. | **High** |
| **Silent Swallowing of Missing Bound Impls** | `src/gen/gen_c/gen_c_bound.zen:280-310` (`bound_answered`, `table_answered`) | When checking `table_answered`, if an implementation table lookup fails or a bound cannot be resolved, `one_impl` returns `false` without reporting an error. If a user defines an impl with mismatched type parameters, it silently falls through to an "unsupported: bodiless member of a bound used as a value" error rather than a clear diagnostic identifying missing/malformed implementation bodies. | **Medium** |

---

### 3. Proposals from Prior Audit: Disposition

* **Introduce `InlineExpansion` and `InlineSite` Records**: **COMPLETED & CONFIRMED**. `gen_c_inline.zen` in round-03 cleanly uses `InlineExpansion.run` and `InlineSite.bind`, eliminating the relay excess in inlining.
* **Merge `gen_c_loop`, `gen_c_range`, `gen_c_array`, and `gen_c_fold`**: **REJECT**. Inspection of `gen_c_range.zen` (622 lines) and `gen_c_loop.zen` (795 lines) confirms that range protocol handling (impl bounds, synthesized `at` inlining) and loop control flow (`LoopFrame`, break/continue labels, counter step emission) have distinct invariants and lifecycles. Share the `LoopWalk` record instead of merging files.
* **Combine DOM and Streaming JSON Parsers**: **REJECT**. `json_read.zen` relies on zero-copy borrowing from stable memory buffers, whereas `json_stream.zen` feeds from chunked I/O. They must share grammar transitions, not allocation strategies.
* **Replace `zen_build_plan.Executor` with General Comptime Evaluator**: **DEFERRED**. The compile-time evaluator does not yet support sandboxed target capabilities or build graph step caching. Retain `zen_build_plan.zen` until evaluator capabilities are proven.

---

### 4. Metric Delta Assessment

* **Judgement**: **Genuine Improvement**.
* **Reasoning**:
  * **Functions with 8+ Parameters**: Dropped by 6 (from 102 to 96).
  * **Parameter Slots**: Dropped by 54 (from 17,925 to 17,871).
  * **Relay Excess (>5 parameters)**: Dropped by 30 (from 951 to 921).
  * **Mutual Sibling Import Edges**: Reduced by 4 (from 142 to 138).
  * **Lines of Code**: Decreased by 408 lines (from 73,070 to 72,662) with 23 net new cohesive functions.
  * **Comment Cleanup**: History markers dropped by 8, and comment lines dropped by 298 without losing structural invariants.
  * **Integrity**: Improvements reflect actual phase modeling (such as `InlineExpansion` in `gen_c_inline.zen` and `CallSite` in `gen_c_call.zen`) without metric gaming or parameter bags.

---

### 5. Suggested Non-Overlapping Wave Assignments

```
====================================================================================================
AGENT 1: Loop & Range Lowering Phase Unification (Backend Iteration)
  - Target: src/gen/gen_c/gen_c_loop.zen, src/gen/gen_c/gen_c_range.zen, src/gen/gen_c/gen_c_fold.zen
  - Task: Implement LoopWalk phase record to eliminate 8-10 parameter relays across lower_range,
          lower_bounded, lower_supplied_walk, and take_pass.
  - Inspection chain: Read lower_range -> lower_range_impl -> lower_settled -> lower_bounded
                      in gen_c_loop.zen and lower_supplied_walk -> take_pass in gen_c_range.zen.
  - Verification: make test && make cap. Verify no increase in mutual sibling imports.

AGENT 2: Call Site, Associated Calls, and Member Lowering (Backend Calls)
  - Target: src/gen/gen_c/gen_c_call.zen, src/gen/gen_c/gen_c_assoc.zen, src/gen/gen_c/gen_c_member.zen
  - Task: Extend CallSite across write_to_pack/write_spread relays in gen_c_call.zen.
          Implement AssocSite in gen_c_assoc.zen and extend DotSite in gen_c_member.zen.
  - Inspection chain: Read write_call_args -> write_to_pack -> write_spread -> write_run in
                      gen_c_call.zen and assoc_at_site -> assoc_member in gen_c_assoc.zen.
  - Verification: Diff emitted C code across compiler test suite.

AGENT 3: JSON Syntax Extraction & LSP Decoupling (Stdlib & Tooling)
  - Target: src/std/json/*, src/lsp/lsp_query.zen, src/lsp/lsp_diag.zen
  - Task: Extract shared json_syntax state machine and delete decode_text_token/number_token bridge.
          Sever zen_build import from lsp_query.zen and fix hard-coded severity in lsp_diag.zen.
  - Inspection chain: Read json_read.zen reader loop alongside json_stream.zen feed transitions;
                      read Diagnostics.say_one -> write_notification in lsp_diag.zen.
  - Verification: JSON parser conformance suite and LSP integration tests.
====================================================================================================
```
