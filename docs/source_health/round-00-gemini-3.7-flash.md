# Gemini 3.7 Flash review — round-00

Model: `gemini-3.7-flash`

### Evaluation: Genuine Disagreements vs. Vocabulary Disputes

#### 1. Vocabulary Disputes (Surface Contradictions without Underlying Conflict)
* **"Parameter Bags" vs. "Phase Records"**: The dispute over whether creating structs like `CallSite`, `ActorSpawn`, or `InlineSite` constitutes an anti-pattern ("parameter bag") or proper domain modeling is largely lexical. Both perspectives agree that grouping variables is harmful if those fields have disjoint lifetimes, variable mutation scopes, or if `CBackend` and `out :: String` must still be threaded into every method. Conversely, both agree that when an analysis step fixes immutable facts born simultaneously (e.g., AST node, target type, typing context), capturing them in a named type clarifies domain boundaries.
* **"File Consolidation" vs. "Cohesion"**: Debates over whether files like `gen_c_loop`, `gen_c_range`, `gen_c_array`, and `gen_c_fold` should merge versus remain split are largely semantic. The genuine architectural goal is eliminating mutual sibling coupling and shared parameter relays. Whether physical boundaries sit across three files or one is secondary to ensuring that dependencies flow unidirectionally without circular imports.

#### 2. Genuine Architectural Disagreements
* **Compiler Query Layer (LSP) vs. Build Driver Coupling**:
  * *Build-centric approach*: Uses `Build` and `zen_path` directly in `lsp_query.zen` to avoid duplicating file/root resolution.
  * *Query-centric approach*: Demands `lsp` depend exclusively on a compiler query layer (`check_workspace`), keeping CLI/driver concerns strictly above both.
  * *Assessment*: The query-centric approach is correct. Driving the compiler from LSP via the CLI driver leaks disk assumptions and command-line execution modes into an interactive protocol server.
* **Dual JSON Parsers vs. Unified Syntax Machine**:
  * *Dual-engine approach*: Keeps `json_read.zen` (DOM tree) and `json_stream.zen` (event stream) separate, bridging them via borrowed helpers (`decode_text_token`, `number_token`).
  * *Unified-engine approach*: Replaces both with a single incremental parser core with pluggable consumers (zero-copy tree builder vs. streaming event emitter).
  * *Assessment*: The unified syntax machine is architecturally necessary to prevent grammar drift (e.g., surrogate pair handling, number validation differences).

---

### What Each Side Gets Right and Wrong

* **Ownership Audit (`SOURCE_OWNERSHIP_AUDIT.md`)**:
  * *Right*: Correctly identifies that high-arity functions in `gen_c` are symptoms of unnamed intermediate lowering phases rather than missing generic helpers. Correctly rejects making `JsonEvent` the universal intermediate representation (which would force heap allocation onto zero-copy tree parsing).
  * *Wrong*: Suggests immediate wholesale migration of project evaluation to compile-time evaluation before compile-time effect boundaries and deterministic budgets are implemented in `sema`.
* **Health Metrics & Structural Review (`SOURCE_HEALTH.md` & `STYLE.md`)**:
  * *Right*: Accurately pinpoints `gen_c_call`, `gen_c_loop`, `gen_c_expr`, and `gen_c_inline` as the primary maintenance bottlenecks due to high mutual coupling and parameter relay depth (up to 16 parameters).
  * *Wrong*: Raw parameter counts can incentivize mechanical grouping into dummy context structs without actually addressing root receiver ownership or reducing the threading of `CBackend`/`Emit`.

---

### Ranked Implementation Lanes

```
+---------------------------------------------------------------------------------------------------+
| 1. gen_c_actor: Consolidate ActorSpawn / ActorLifecycle lowering phases                           |
| 2. gen_c_widen: Resolve symbol collision and clean up widening dispatch                           |
| 3. json: Unify incremental syntax state machine across tree and streaming decoders                |
| 4. gen_c_inline: Encapsulate inline expansion context and closure binding stack                  |
| 5. lsp_query & zen_path: Sever LSP-to-CLI driver dependency via compiler query interface         |
| 6. gen_c_loop / gen_c_range / gen_c_fold: Rationalize loop walk state & break handling             |
| 7. collections: Eliminate fake AllocError returns from infallible operations                      |
| 8. std_net: Decouple TCP/TLS transport and remove redundant stream parameters                     |
| 9. sema_id & sema_ty: Normalize Eq/Hash trait implementations into standard Hasher contracts      |
| 10. gen_c_cap: Extract CapabilityCall lowering site                                               |
+---------------------------------------------------------------------------------------------------+
```

#### Lane 1: `gen_c_actor` Lowering Phase Encapsulation
* **Files**: `src/gen/gen_c/gen_c_actor.zen`
* **Signatures/Types**:
  * `write_spawn_value` (16 params)
  * `write_actor_spawn` (13 params)
  * `spawn_known` (12 params)
  * `spawn_types` (9 params)
* **Proposed Owner**: Introduce `ActorSpawnSite` (holding `ExprId`, `Call`, `Access`, `want: TyId`, `actor_ty: TyId`, `Ctx`) transitioning to `ActorRuntimeLayout` (holding resolved `ref_ty`, `context_ty`, `arena_ty`, `state_ty`, `alloc_ty`).
* **Smallest Safe Boundary**: Keep code emission logic inside `gen_c_actor.zen`; refactor only the internal private spawn-lowering chain without modifying external call sites from `gen_c_member`.

#### Lane 2: `gen_c_widen` Symbol Collision and Dispatch Cleanup
* **Files**: `src/gen/gen_c/gen_c_widen.zen`
* **Signatures/Types**:
  * `member_reaches_set = (be :: CBackend, got: TyId, want: TyId) bool` (line 17)
  * `member_reaches_set = (be :: CBackend, id: ExprId, ctx: Ctx, want: TyId, wide: TyId) Res<bool, AllocError>` (line 25)
* **Proposed Owner**: Disambiguate the type-level query (`type_reaches_set`) from the expression-level query (`expr_reaches_set`).
* **Smallest Safe Boundary**: Rename and restrict visibility within `gen_c_widen.zen`.

#### Lane 3: JSON Unified Incremental Parser Engine
* **Files**: `src/std/json/json_read.zen`, `src/std/json/json_stream.zen`
* **Signatures/Types**:
  * `Reader*`, `Decoder*`, `decode_text_token`, `number_token`
* **Proposed Owner**: `src/std/json/json_syntax.zen` (new internal state machine owning byte classification, string escaping, surrogate pair decoding, and number validation).
* **Smallest Safe Boundary**: Retain `Jsons.read` borrowing semantics and `JsonEvent` stream emission; replace only the internal parsing driver. Delete `decode_text_token` and `number_token`.

#### Lane 4: `gen_c_inline` Expansion State Encapsulation
* **Files**: `src/gen/gen_c/gen_c_inline.zen`
* **Signatures/Types**:
  * `run_called_body`, `run_settled`, `run_block` (10 params)
  * `bind_params`, `bind_param`, `bind_valued` (8 params)
* **Proposed Owner**: `InlineCallSite` (owning `Call`, `Function`, `argv: Vec<ExprId>`, `ptys: Vec<TyId>`, `ret: TyId`, `inst: Inst`, `ctx: Ctx`).
* **Smallest Safe Boundary**: Refactor parameter binding and block expansion internally within `gen_c_inline.zen`; keep `inline_call*` and `inline_method*` public signatures stable.

#### Lane 5: Decouple LSP from Project CLI Driver
* **Files**: `src/lsp/lsp_query.zen`, `src/zen/zen_path.zen`, `src/zen/zen_build.zen`
* **Signatures/Types**:
  * `check_workspace*`, `check_build*`, `Build`
* **Proposed Owner**: Move root and file discovery functions (`root_for`, `entry_of`, `relative_to`) into a protocol-neutral compiler query interface in `src/zen/zen_path.zen` or `src/sema/`.
* **Smallest Safe Boundary**: Remove `zen.zen_build` import from `lsp_query.zen`; make `lsp_query.zen` depend exclusively on `sema` and `ast`.

#### Lane 6: `gen_c_loop` / `gen_c_range` / `gen_c_fold` Walk State
* **Files**: `src/gen/gen_c/gen_c_loop.zen`, `src/gen/gen_c/gen_c_range.zen`, `src/gen/gen_c/gen_c_fold.zen`
* **Signatures/Types**:
  * `lower_impl_walk`, `lower_forever`, `lower_range`, `lower_settled`, `lower_bounded` (10 params)
  * `run_body*` (9 params)
  * `take_pass*`, `run_at` (8–9 params)
* **Proposed Owner**: Unify iteration parameters into `LoopWalk` (holding `Shape`, `one: ExprId`, `rty: TyId`, `Lambda`, `Ctx`, `want: TyId`, `Fold`).
* **Smallest Safe Boundary**: Retain separate files for range dispatch, fold accumulation, and loop control, but pass `LoopWalk` across the file boundaries.

#### Lane 7: Collections Infallible Return Normalization
* **Files**: `src/std/collections/collections_sort.zen`, `src/std/collections/collections_map.zen`, `src/std/collections/collections_vec.zen`
* **Signatures/Types**:
  * `sort*<T: Ordered> = (xs :: Vec<T>) Res<(), AllocError>` -> change return to `()`
  * `Map.get*` / `set*` error mappings
* **Proposed Owner**: `std.collections`
* **Smallest Safe Boundary**: Change `sort` signature to return `()` since in-place permutation does not allocate. Eliminate fake `AllocError` returns.

#### Lane 8: `std_net` Transport and Signature Cleanup
* **Files**: `src/std/net/tcp.zen`, `src/std/net/tls/tls.zen`, `src/std/net/http/http_transport.zen`
* **Signatures/Types**:
  * `TcpStream.read* = (self: @Self, a: Alloc, buf :: Vec<u8>, n: usize) Res<usize, TcpError>`
* **Proposed Owner**: `TcpStream`
* **Smallest Safe Boundary**: Remove unused `a: Alloc` parameter from `TcpStream.read*` to match `Socket.read*`.

#### Lane 9: Trait Contract Normalization in Semantic ID / Type Storage
* **Files**: `src/sema/sema_id.zen`, `src/sema/sema_ty.zen`
* **Signatures/Types**:
  * `DeclId.impl(Hash)`, `MemberId.impl(Hash)`, `ImplId.impl(Hash)`, `TyId.impl(Hash)`
* **Proposed Owner**: Type definitions in `sema_id.zen` and `sema_ty.zen`.
* **Smallest Safe Boundary**: Delegate state updates directly to `hasher.write_u64(...)` / `hasher.write_u32(...)` without ad-hoc magic multiplier arithmetic (`MIX = 1099511628211`) in the `impl`.

#### Lane 10: `gen_c_cap` Lowering Site Encapsulation
* **Files**: `src/gen/gen_c/gen_c_cap.zen`
* **Signatures/Types**:
  * `lower_capability*`, `lower_typed_capability`, `lower_capability_kind` (10–11 params)
* **Proposed Owner**: `CapCallSite` (owning `CapabilityKind`, `ExprId`, `Call`, `Access`, `rty: TyId`, `mi: usize`, `Function`, `Ctx`, `want: TyId`).
* **Smallest Safe Boundary**: Refactor capability dispatch internally within `gen_c_cap.zen`.

---

### Likely Bugs Identified

| Issue | File & Location | Evidence | Confidence |
| :--- | :--- | :--- | :--- |
| **Duplicate Function Declaration / Overload Collision** | `src/gen/gen_c/gen_c_widen.zen` | `member_reaches_set` is defined as both `(be, got, want) bool` and `(be, id, ctx, want, wide) Res<bool, AllocError>`. In a non-overloaded or C-lowered context, this causes symbol shadowing or codegen collisions. | **High** |
| **Redundant/Unused Allocator Parameter in I/O** | `src/std/net/tcp.zen` | `TcpStream.read*` requires `a: Alloc`, but delegates directly to `Socket.read*` which does not allocate. | **High** |
| **Misleading Allocation Error on In-Place Sort** | `src/std/collections/collections_sort.zen` | `sort*` returns `Res<(), AllocError>` but executes an in-place swap on `Vec<T>`, never allocating. | **High** |
| **Inconsistent Qualified Name Parsing** | `src/sema/sema_match.zen` vs `src/sema/sema_def.zen` | `last_segment` in `sema_match` takes `QualifiedName`, while `last_segment` in `sema_def` takes `str`. Inconsistent dot-scanning logic across modules risks misidentifying module roots. | **Medium** |

---

### Disposition of Prior Audit Proposals

* **Unify JSON Syntax Machine**: **CONFIRMED & UPGRADED TO HIGH PRIORITY**. Must be implemented without forcing allocation on the zero-copy DOM reader.
* **Encapsulate `gen_c_actor` Spawn Relays**: **CONFIRMED**. The 16-parameter relay chain in `write_spawn_value` is the cleanest candidate for phase encapsulation.
* **Immediate Replacement of `zen_build_plan.Executor` with Comptime Evaluator**: **DEFERRED**. The comptime interpreter does not yet support the isolation, error handling, and deterministic budgets required by the build plan executor.
* **Consolidate `gen_c_loop`, `gen_c_range`, `gen_c_array`, `gen_c_fold` into One File**: **REJECTED**. Physical merging would create an unmaintainable monolith exceeding 2,000 lines. The correct solution is sharing a `LoopWalk` context across existing modular boundaries.
* **Introduce General Extension Syntax for UFCS**: **REJECTED**. Zen's principal-receiver resolution already handles receiver method calls; adding language-level out-of-line inherent methods is unnecessary syntax churn.

---

### Metric Delta Assessment

* **Judgement**: **Inconclusive (Baseline Round-00 Established)**.
* **Reasoning**: Round-00 establishes the exhaustive declaration baseline (227 files, 7,202 declarations, 117 functions with 8+ parameters, 142 mutual sibling import edges). No code deletions or structural migrations have been measured yet. The priority ranking correctly identifies the hotspots (`gen_c_call`, `gen_c_loop`, `gen_c_expr`, `gen_c_inline`, `gen_c_actor`).

---

### Three Non-Overlapping Wave Assignments

```
====================================================================================================
AGENT 1: Code Generation Phase Encapsulation (Backend Lane)
  - Target: src/gen/gen_c/gen_c_actor.zen, src/gen/gen_c/gen_c_cap.zen, src/gen/gen_c/gen_c_widen.zen
  - Task: Implement ActorSpawnSite and CapCallSite; resolve member_reaches_set collision in gen_c_widen.
  - Verification: Diff check on emitted C output across compiler test suite.

AGENT 2: Standard Library I/O, JSON & Collections (Stdlib Lane)
  - Target: src/std/json/*, src/std/collections/*, src/std/net/tcp.zen
  - Task: Extract internal json_syntax parser state machine; make sort* infallible; clean TcpStream.read.
  - Verification: JSON conformance tests, zero-allocation assertion on sort, TCP socket tests.

AGENT 3: Compiler Architecture & LSP Decoupling (Frontend/Tooling Lane)
  - Target: src/lsp/lsp_query.zen, src/lsp/lsp_hover.zen, src/zen/zen_path.zen, src/zen/zen_build.zen
  - Task: Remove zen.zen_build dependency from lsp_query; route workspace checks via compiler queries.
  - Verification: LSP integration tests, verify no reverse imports via make lint / dependency check.
====================================================================================================
```

---

### Synthesized Verdict

The codebase exhibits strong architectural foundations—specifically clean module segregation by AST node type, disciplined error propagation via `Res`, and strict memory tracking via explicit allocators. However, the C generator and semantic analyzer suffer from parameter relay bloat where intermediate lowering phases are passed as loose arguments rather than structured phase values.

The immediate path forward requires targeted phase encapsulation in `gen_c_actor` and `gen_c_inline`, unifying the JSON grammar engine, and severing the dependency of the LSP on the CLI build driver, while avoiding superficial file merges that would degrade code modularity.
