# Gemini 3.7 Flash review — round-01

Model: `gemini-3.7-flash`

### 1. Evaluation: Genuine Disagreements vs. Vocabulary Disputes

#### Vocabulary Disputes
* **"Parameter Bags" vs. "Phase Records"**: The tension over whether bundling function arguments into structs creates an anti-pattern or clarifies architecture is primarily a vocabulary dispute. Both positions agree on the underlying principle: creating ad-hoc structs that merely group transient arguments while still requiring `CBackend` and `out :: String` to be threaded into every method is detrimental ("parameter bags"). Conversely, when an intermediate lowering or semantic analysis step establishes an immutable set of domain facts born simultaneously with a shared lifetime (such as `ActorSpawn` $\rightarrow$ `ActorSpawnLayout` $\rightarrow$ `ActorLifecycle` in `gen_c_actor.zen`), encapsulating them into a named phase record establishes clean domain boundaries.
* **"File Consolidation" vs. "Physical Modularity"**: Debating whether tightly coupled siblings (e.g., `gen_c_loop`, `gen_c_range`, `gen_c_array`, `gen_c_fold`) should merge into a single file or stay split across four files is largely a dispute over layout vocabulary. Both sides agree that circular sibling imports and repeated 8+ parameter relay chains across files are symptoms of unmodeled iteration state. The true goal is establishing a single owner for loop walk coordination while keeping specialized domain decisions (such as range protocol dispatch and fold accumulation) independently testable.

#### Genuine Architectural Disagreements
* **LSP Dependency on the Compiler Query Layer vs. CLI Project Driver**:
  * *Driver-coupled approach*: Reuses `zen_build` and `zen_path` inside `lsp_query.zen` to avoid duplicating workspace/root resolution logic.
  * *Query-centric approach*: Insists that the LSP interact exclusively with a protocol-neutral compiler query interface, placing `zen` CLI driver concerns strictly downstream of `sema` and `ast`.
  * *Verdict*: The query-centric approach is correct. Coupling interactive editor protocols directly to command-line build abstractions (`zen_build.Build`) leaks CLI assumptions (e.g., emission flags, batch file writes) into real-time server queries.
* **Stream-level `Alloc` Ownership across Network Transports**:
  * *Uniform allocation signature*: Passing `Alloc` across all `Stream.read` variants to accommodate TLS buffering.
  * *Zero-allocation TCP transport*: Keeping `TcpStream.read` allocation-free while isolating TLS scratchpad allocation to `TlsStream`.
  * *Verdict*: Network transports must reflect true capability requirements. Forcing allocation parameters onto raw TCP read paths degrades performance and obscures ownership.

---

### 2. What Each Side Gets Right and Wrong

* **Source Ownership Audit (`SOURCE_OWNERSHIP_AUDIT.md`)**:
  * *Right*: Correctly identified that the 12–16 parameter relay chains in `gen_c_actor` were unmodeled lifecycle phases. Correctly insisted that unifying JSON syntax must not force heap allocation on zero-copy document parsing.
  * *Wrong*: Recommended deferring the cleanup of `zen_build_plan.Executor` solely on the grounds of future compile-time evaluator convergence, preserving redundant build-step evaluation logic in the interim.
* **Source Health Metrics & Structural Review (`SOURCE_HEALTH.md` & Prior Review)**:
  * *Right*: Accurately targeted `gen_c_call`, `gen_c_loop`, `gen_c_inline`, and `gen_c_bound` as top maintenance bottlenecks driven by extreme relay depth and high mutual coupling.
  * *Wrong*: Over-emphasized signature name collisions in `gen_c_widen.zen` (`member_reaches_set`) without accounting for Zen's native support for arity- and type-based function overloading.

---

### 3. Ranked Implementation Lanes

```
+---------------------------------------------------------------------------------------------------+
| 1. gen_c_inline: Encapsulate inline expansion context and closure binding stack                  |
| 2. gen_c_loop / gen_c_range / gen_c_fold: Model shared LoopWalk state across iteration lowering    |
| 3. gen_c_call: Extend CallSite encapsulation across vararg and argument packing relays            |
| 4. gen_c_cap: Extract CapabilityCall lowering phase site                                          |
| 5. gen_c_bound: Structure BoundCall lowering context for fat-pointer dispatch                     |
| 6. json: Unify incremental syntax state machine across tree and streaming readers                 |
| 7. lsp_query & lsp_hover: Sever zen_build dependency and decouple presentation rendering         |
| 8. gen_c_assoc: Model AssocCall lowering site for module and associated type calls                |
| 9. tls & http_transport: Reconcile Alloc ownership between TcpStream and TlsStream                |
| 10. sema_id & sema_ty: Normalize Eq/Hash trait implementations into standard Hasher contracts    |
+---------------------------------------------------------------------------------------------------+
```

#### Lane 1: `gen_c_inline` Expansion State Encapsulation
* **Files**: `src/gen/gen_c/gen_c_inline.zen`
* **Signatures/Types**:
  * `run_called_body`, `run_settled`, `run_block` (10 parameters)
  * `bind_params`, `bind_param`, `bind_valued` (8 parameters)
* **Proposed Owner**: Introduce an internal `InlineExpansion` record owning `Function`, `argv: Vec<ExprId>`, `ptys: Vec<TyId>`, `ret: TyId`, `bctx: Ctx`, `inst: Inst`, and `ctx: Ctx`.
* **Smallest Safe Boundary**: Keep `inline_call*` and `inline_method*` public signatures stable; refactor only the internal parameter binding and block execution chain.

#### Lane 2: `gen_c_loop` / `gen_c_range` / `gen_c_fold` Walk State
* **Files**: `src/gen/gen_c/gen_c_loop.zen`, `src/gen/gen_c/gen_c_range.zen`, `src/gen/gen_c/gen_c_fold.zen`
* **Signatures/Types**:
  * `lower_impl_walk`, `lower_forever`, `lower_range`, `lower_range_impl`, `lower_settled`, `lower_bounded` (10 parameters)
  * `run_body*`, `take_pass*`, `run_at` (8–9 parameters)
* **Proposed Owner**: Model `LoopWalk` holding `(sh: Shape, one: ExprId, rty: TyId, lam: Lambda, ctx: Ctx, want: TyId, fold: Fold)`.
* **Smallest Safe Boundary**: Pass `LoopWalk` across existing module boundaries without physically merging files, preserving separate units for fold accumulation and range implementation lookup.

#### Lane 3: `gen_c_call` Argument Packing & CallSite Extension
* **Files**: `src/gen/gen_c/gen_c_call.zen`
* **Signatures/Types**:
  * `write_to_pack`, `write_pack`, `is_forwarded_pack`, `pack_typed_arg`, `write_forwarded`, `write_spread`, `write_run`, `write_pack_elems` (7 parameters)
  * `CallSite` methods
* **Proposed Owner**: Extend existing `CallSite` to own callee definition, instantiated signature, and argument slices.
* **Smallest Safe Boundary**: Migrate vararg pack-forwarding helpers into methods on `CallSite`.

#### Lane 4: `gen_c_cap` Capability Call Lowering Site
* **Files**: `src/gen/gen_c/gen_c_cap.zen`
* **Signatures/Types**:
  * `lower_capability*`, `lower_typed_capability`, `lower_capability_kind` (10–11 parameters)
* **Proposed Owner**: `CapabilityCall` (owning `kind: CapabilityKind`, `id: ExprId`, `c: Call`, `a: Access`, `rty: TyId`, `mi: usize`, `f: Function`, `ctx: Ctx`, `want: TyId`).
* **Smallest Safe Boundary**: Encapsulate capability dispatch internally within `gen_c_cap.zen`.

#### Lane 5: `gen_c_bound` Fat-Pointer Lowering Phase
* **Files**: `src/gen/gen_c/gen_c_bound.zen`
* **Signatures/Types**:
  * `lower_fat_call*`, `emit_fat_call`, `fat_args`, `fat_arg` (8–10 parameters)
* **Proposed Owner**: `BoundCall` (owning `Call`, `Access`, `rty: TyId`, `Slot`, `declared: Vec<TyId>`, `ret: TyId`, `targs: Inst`, `ctx: Ctx`).
* **Smallest Safe Boundary**: Refactor fat method resolution and thunk sizing within `gen_c_bound.zen`.

#### Lane 6: JSON Incremental Syntax Machine Unification
* **Files**: `src/std/json/json_read.zen`, `src/std/json/json_stream.zen`
* **Signatures/Types**:
  * `Reader*`, `Decoder*`, `decode_text_token*`, `number_token*`
* **Proposed Owner**: Private syntax machine in `src/std/json/json_syntax.zen`.
* **Smallest Safe Boundary**: Extract escape/Unicode/number transition logic into a shared machine; keep zero-copy borrowing in `read` and owned token allocations in `Decoder`. Delete the bridging helpers `decode_text_token` and `number_token`.

#### Lane 7: LSP Compiler Query & Semantic Presentation Decoupling
* **Files**: `src/lsp/lsp_query.zen`, `src/lsp/lsp_hover.zen`, `src/zen/zen_path.zen`
* **Signatures/Types**:
  * `check_workspace*`, `check_build*`, `hover_with*`, `write_decl_note`, `write_members`
* **Proposed Owner**: Compiler query functions in `zen_path` / `sema`; type-formatting sink in `sema_diag` / `sema_ty`.
* **Smallest Safe Boundary**: Remove `zen_build.Build` import from `lsp_query.zen`; redirect hover formatting to a semantic display sink.

#### Lane 8: `gen_c_assoc` Associated Call Lowering Site
* **Files**: `src/gen/gen_c/gen_c_assoc.zen`
* **Signatures/Types**:
  * `write_module_call`, `write_assoc_call`, `emit_assoc_call`, `write_assoc_arg` (8–10 parameters)
* **Proposed Owner**: `AssocCall` (owning `id: ExprId`, `c: Call`, `a: Access`, `ty: TyId`, `s: Site`, `f: Function`, `sig: Vec<TyId>`, `inst: Inst`, `ctx: Ctx`).
* **Smallest Safe Boundary**: Refactor private associated call emission in `gen_c_assoc.zen`.

#### Lane 9: TLS / TCP Transport Signature Alignment
* **Files**: `src/std/net/tcp.zen`, `src/std/net/tls/tls.zen`, `src/std/net/http/http_transport.zen`
* **Signatures/Types**:
  * `TlsStream.read* = (self: @Self, a: Alloc, buf :: Vec<u8>, n: usize) Res<usize, TlsError>`
  * `TcpStream.read* = (self: @Self, buf :: Vec<u8>, n: usize) Res<usize, TcpError>`
  * `Stream.read* = (self: Stream, a: Alloc, buf :: Vec<u8>, n: usize) Res<usize, HttpError>`
* **Proposed Owner**: `TlsStream` internal buffer management.
* **Smallest Safe Boundary**: Maintain allocator state in `TlsStream` struct instance; make `TlsStream.read` match the `(self: @Self, buf :: Vec<u8>, n: usize)` signature of `TcpStream.read` and `Socket.read`.

#### Lane 10: Hash Trait Normalization for Semantic Types
* **Files**: `src/sema/sema_id.zen`, `src/sema/sema_ty.zen`
* **Signatures/Types**:
  * `DeclId.impl(Hash)`, `MemberId.impl(Hash)`, `ImplId.impl(Hash)`, `TyId.impl(Hash)`, `MIX*`
* **Proposed Owner**: Hash implementations in `sema_id.zen` and `sema_ty.zen`.
* **Smallest Safe Boundary**: Pass discrete integer components (`module`, `decl`, `member`, `index`) directly into `hasher.write_u32` / `hasher.write_u64` rather than applying hardcoded multiplication constants (`MIX = 1099511628211`) inside the `impl`.

---

### 4. Likely Bugs Identified

| Issue | File & Location | Evidence | Confidence |
| :--- | :--- | :--- | :--- |
| **Asymmetric Transport Read Signatures Force Dead Allocation Parameters** | `src/std/net/tls/tls.zen` vs `src/std/net/tcp.zen` | `TlsStream.read*` requires `a: Alloc` on every read invocation, forcing `http_transport.Stream.read` to require `a: Alloc` even when dispatching to the non-allocating `TcpStream.read`. | **High** |
| **LSP Hover Bypasses Standard Output Sinks** | `src/lsp/lsp_hover.zen` | Long recursive rendering functions (`write_members`, `write_member_run`, `write_fn_member`) mutate `body :: String` directly rather than targeting `Sink`, duplicating semantic presentation logic found in `sema_diag.zen`. | **High** |
| **Manual Punctuation Bridge between JSON Parsers** | `src/std/json/json_read.zen`, `src/std/json/json_stream.zen` | `json_stream.zen` imports `decode_text_token` and `number_token` from `json_read.zen` to avoid duplicating lexical parsing, creating a fragile coupling where changes to number/escape limits in one parser break the other. | **High** |

---

### 5. Prior Audit Proposals: Disposition

* **Consolidate `gen_c_actor` Spawn Phases**: **CONFIRMED & COMPLETED IN ROUND-01**. The introduction of `ActorSpawn`, `ActorSpawnLayout`, and `ActorLifecycle` dropped 8+ parameter functions by 6 and eliminated 54 relay slots.
* **Unify JSON Syntax Machine**: **CONFIRMED & RETAINED AT HIGH PRIORITY**. Proceed with a shared incremental syntax machine without altering zero-copy tree borrowing or streaming event ownership.
* **Merge Loop, Range, Array, and Fold into Monolithic File**: **REJECTED**. Physical merging would create a 2,000+ line monolith. Sharing the `LoopWalk` phase record across existing files resolves coupling cleanly.
* **Replace `zen_build_plan.Executor` with General Comptime Evaluator**: **DEFERRED**. The general evaluator lacks the deterministic budget tracking, effect sandboxing, and diagnostic isolation required by project building.
* **Eliminate `AllocError` from In-Place `sort`**: **CONFIRMED & COMPLETED**. `sort*` in `collections_sort.zen` now correctly returns `()`.

---

### 6. Metric Delta Assessment

* **Judgement**: **Genuine Improvement**.
* **Reasoning**:
  * **Parameter Slots**: Reduced by 81 (from 18,103 to 18,022).
  * **Functions with 8+ Parameters**: Decreased by 6 (from 117 to 111).
  * **Relay Excess (>5 Parameters)**: Decreased by 54 (from 1,048 to 994).
  * **Repeated 4+ Signature Shapes**: Reduced by 8 (from 376 to 368).
  * **Integrity**: The reduction was achieved via genuine phase modeling in `gen_c_actor` (`ActorSpawn`, `ActorSpawnLayout`, `ActorLifecycle`) rather than cosmetic parameter bags or file merging. No regressions were introduced into module dependencies or public contracts.

---

### 7. Suggested Non-Overlapping Wave Assignments

```
====================================================================================================
AGENT 1: Code Generation Phase Encapsulation (Backend Core)
  - Target: src/gen/gen_c/gen_c_inline.zen, src/gen/gen_c/gen_c_cap.zen, src/gen/gen_c/gen_c_bound.zen
  - Task: Implement InlineExpansion, CapabilityCall, and BoundCall phase records to collapse
          8+ parameter relays.
  - Verification: Diff check emitted C code across all compiler test cases.

AGENT 2: Loop & Iteration Lowering Unification (Backend Iteration)
  - Target: src/gen/gen_c/gen_c_loop.zen, src/gen/gen_c/gen_c_range.zen, src/gen/gen_c/gen_c_fold.zen
  - Task: Introduce shared LoopWalk phase record across loop, range, and fold lowering boundaries.
  - Verification: Run complete test suite and verify no increase in mutual sibling imports.

AGENT 3: Standard Library & Tooling Decoupling (Stdlib & Tooling)
  - Target: src/std/json/*, src/std/net/*, src/lsp/lsp_query.zen
  - Task: Extract shared json_syntax state machine; eliminate Alloc requirement from TlsStream.read;
          sever zen_build dependency from lsp_query.
  - Verification: JSON parser conformance tests, network I/O tests, LSP suite execution.
====================================================================================================
```

---

### 8. Synthesized Verdict

The round-01 refactoring demonstrates that disciplined phase encapsulation effectively eliminates signature sprawl without compromising domain boundaries. The successful transformation of `gen_c_actor` provides the architectural pattern for the remaining code-generation hotspots (`gen_c_inline`, `gen_c_loop`, `gen_c_cap`, and `gen_c_bound`).

Future waves must continue applying phase modeling to lowering pipelines, unify JSON grammar parsing across DOM and streaming decoders, and decouple editor query paths from CLI execution drivers, while rejecting mechanical file mergers that obscure cohesive domain logic.
