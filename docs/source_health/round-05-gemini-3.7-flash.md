# Gemini 3.7 Flash review — round-05

Model: `gemini-3.7-flash`

### 1. Ranked Implementation Lanes

```
+----------------------------------------------------------------------------------------------------+
| 1. gen_c_call: Unify CallSite and ResInit to eliminate 8+-parameter entry relays                  |
| 2. gen_c_member: Extend MethodCallSite upward through method_kind and intrinsic dispatch           |
| 3. gen_c_actor: Introduce ActorSend phase record in write_actor_send and write_send_value          |
| 4. gen_c_expr: Separate pure call-reordering predicates from expression evaluation doors          |
| 5. sema_member: Encapsulate MemberLookup for multi-candidate resolution and accessibility checks   |
| 6. gen_c_json: Fix compound literal string initialization in JsonLower.raw                         |
+----------------------------------------------------------------------------------------------------+
```

#### Lane 1: Unify `CallSite` and `ResInit` in `gen_c_call`
* **Files**: `src/gen/gen_c/gen_c_call.zen`
* **Signatures / Types**:
  * `write_res_payload*` (8 params: `be`, `id`, `want`, `variant`, `value`, `payload`, `ctx`, `out`)
  * `write_extern*` (9 params: `be`, `id`, `c`, `d`, `f`, `sig`, `recv`, `ctx`, `out`)
  * `lower_plain_call*` (8 params: `be`, `id`, `c`, `name`, `recv`, `ctx`, `want`, `out`)
  * `lower_sugar_or_plain`, `lower_named_call`, `lower_res_arg` (6–7 params)
* **Proposed Owner**: Extend the existing `CallSite` to own `(id: ExprId, c: Call, recv: Res<ExprId>, ctx: Ctx)`. Replace loose forwarding in `lower_plain_call` and `write_extern` by calling methods directly on `CallSite`. Introduce `ResInit(id: ExprId, want: TyId, variant: str, value: ExprId, payload: TyId, ctx: Ctx)` for tagged `Res` payload emission.
* **Smallest Safe Boundary**: Keep `CallSite.resolve` and `CallArgs.write` public boundaries intact; preserve tagged compound literal output (`({}){ .zg_tag = ... }`).

#### Lane 2: Extend `MethodCallSite` Upward in `gen_c_member`
* **Files**: `src/gen/gen_c/gen_c_member.zen`
* **Signatures / Types**:
  * `lower_method` (7 params), `declared_member` (7 params), `supplied_member` (7 params), `supplied_or_refused` (7 params), `with_site` (6 params), `supplied_or_ufcs` (6 params)
  * `method_kind` (5 params), `method_inst` (5 params), `write_variant_call` (5 params)
* **Proposed Owner**: Form `MethodCallSite` immediately after `pick_member` resolves candidate `Function`, owning `(dot: Dot, site: Site, function: Function, ctx: Ctx, want: TyId)`. Make `method_kind`, intrinsic lowerer branching, and generic instantiation methods on `MethodCallSite`.
* **Smallest Safe Boundary**: Keep `lower_dot_call*`, `site_of*`, `member_symbol*`, and `method_sig*` entry signatures stable.

#### Lane 3: Encapsulate `ActorSend` in `gen_c_actor`
* **Files**: `src/gen/gen_c/gen_c_actor.zen`
* **Signatures / Types**:
  * `write_actor_send` (9 params: `be`, `id`, `c`, `a`, `rty`, `actor_ty`, `hit`, `ctx`, `out`)
  * `write_send_value` (11 params: `be`, `c`, `a`, `rty`, `ret`, `payload`, `turn`, `f`, `sig`, `ctx`, `out`)
  * `write_behavior_turn` (6 params: `be`, `n`, `payload`, `actor_ty`, `hit`, `sig`)
* **Proposed Owner**: Introduce `ActorSend(id: ExprId, call: Call, access: Access, receiver_ty: TyId, actor_ty: TyId, hit: BehaviorHit, ctx: Ctx)` parallel to `ActorSpawn`. Move turn callback generation, message descriptor layout, and return value mapping onto `ActorSend`.
* **Smallest Safe Boundary**: Keep `lower_actor_send*`, `lower_actor_spawn*`, and runtime header layout functions unchanged.

#### Lane 4: Separate Pure Ordering Predicates from Expression Doors in `gen_c_expr`
* **Files**: `src/gen/gen_c/gen_c_expr.zen`
* **Signatures / Types**:
  * `holds*`, `reorderable*`, `may_reorder*`, `recv_slots`, `recv_calls`, `position_calls`, `any_arg_calls`, `last_call_arg`, `has_call*`, `has_call_walk`, `holdable*` (tree analysis)
  * `ty_of*`, `ty_source`, `expr*`, `value_expr*`, `spill_temp`, `value_held*` (lowering doors)
* **Proposed Owner**: Group argument-order and call-containment checks into a non-allocating query suite over `(tree: Ast, call: Call)`. Leave `door_of` and `spill_temp` to own statement destination delivery.
* **Smallest Safe Boundary**: Retain `ty_of*`, `want_of*`, and `expr*` entry points and the exact door precedence (`Set -> Hoist -> Widen -> Fat -> Plain`).

#### Lane 5: Encapsulate `MemberLookup` in `sema_member`
* **Files**: `src/sema/sema_member.zen`
* **Signatures / Types**:
  * `known_access`, `pick`, `first_type`, `select`, `ambiguous`, `struct_members`, `add_own` (5–8 params relayed across member filtering and access checks)
* **Proposed Owner**: Introduce a private `MemberLookup(id: ExprId, node: Expr, access: Access, ty: TyId, ctx: Ctx)` to own candidate collection, visibility filtration (`first_hidden`), and ambiguity diagnostics.
* **Smallest Safe Boundary**: Keep `access_type*`, `base_of*`, `members_of*`, `computed_member*`, and `writable_member*` query surfaces intact.

#### Lane 6: Fix Compound Literal Initialization in `gen_c_json`
* **Files**: `src/gen/gen_c/gen_c_json.zen`
* **Signatures / Types**:
  * `JsonLower.raw = (self: @Self, be :: CBackend, raw: str)`
* **Proposed Owner**: Fix `JsonLower.raw` to construct the `zg_str` compound literal without doubled braces in raw string allocation.
* **Smallest Safe Boundary**: Preserve zero-allocation runtime JSON writing and byte-length tracking for unescaped field names.

---

### 2. Likely Bugs Identified

| Issue | File & Location | Evidence | Confidence |
| :--- | :--- | :--- | :--- |
| **Invalid C syntax from doubled braces in `JsonLower.raw` string constructor** | `src/gen/gen_c/gen_c_json.zen:266-274` | `JsonLower.raw` initializes `literal` using `be.alloc.String("(zg_str){{ (unsigned char *)\"")`. The constructor `String(str)` stores bytes literally without format-string unescaping. It then calls `literal.fmt("\", {}u }}", raw.len)`. In the output, the opening prefix retains `(zg_str){{ (unsigned char *)"` (two opening braces) while the suffix formats to `", ...u }"` (one closing brace). This emits unbalanced braces into generated C, causing compilation errors in `cc`. | **High** |
| **Dead `be :: CBackend` parameter in `write_position*`** | `src/gen/gen_c/gen_c_op.zen:717-723` | `write_position*` declares `be :: CBackend`, but never references `be`. It only formats `file`, `span.start.line`, and `span.start.col` into `out`. Relaying `be` across `gen_c_op`, `gen_c_cap`, and `gen_c_stmt` forces caller modules to hold backend state unnecessarily. | **High** |
| **`write_extern*` bypasses `CallSite` abstraction despite constructing it** | `src/gen/gen_c/gen_c_call.zen:498-510` | `write_extern*` accepts 9 parameters (`be`, `id`, `c`, `d`, `f`, `sig`, `recv`, `ctx`, `out`), constructs `s = CallSite(id: id, c: c, recv: recv, ctx: ctx)`, and immediately invokes `s.foreign_at(be, d, f, sig, out)`. Downstream callers in `gen_c_decl` relay all 9 fields instead of accepting or reusing a `CallSite`. | **Medium** |

---

### 3. Proposals from Prior Audit: Disposition

* **Introduce `JsonLower` in `gen_c_json.zen`**: **COMPLETED & CONFIRMED**. `JsonLower` successfully encapsulated recursive JSON emission, dropping parameter relay chains across primitive, named, and struct member formatting.
* **Introduce `TryPropagation` in `gen_c_try.zen`**: **COMPLETED & CONFIRMED**. `TryPropagation` consolidated error mapping, carrier construction, and set retagging.
* **Introduce `MatchCoverage` in `sema_match.zen`**: **COMPLETED & CONFIRMED**. Encapsulated Maranget usefulness state and eliminated 5-slot recursion parameter passing.
* **Introduce `WorkspaceTurn` in `lsp_diag.zen`**: **COMPLETED & CONFIRMED**. Replaced 6–8 parameter relays in diagnostic workspace turns.
* **Merge `gen_c_expr.zen` and `gen_c_op.zen`**: **REJECT**. Expression dispatch (1,142 lines) and type-directed operator/helper lowering (723 lines) have distinct invariants; merging them would form an unwieldy 1,865-line file with conflicting responsibilities.
* **Combine `sema_member.zen` into `sema_type.zen`**: **REJECT**. `sema_member` (986 lines) encapsulates member visibility, impl priority, and actor behavior resolution. Merging it into `sema_type` violates single-subject cohesion.
* **Generalize JSON writing to `Sink` before syntax engine consolidation**: **DEFER**. Syntax engine consolidation (borrowed tree vs. owned stream parser) must precede typed sink encoding to ensure consistent tokenization invariants.

---

### 4. Metric Delta Assessment

* **Judgement**: **Genuine Improvement**.
* **Reasoning**:
  * **Functions with 8+ Parameters**: Reduced from 81 to 68 (-13, a 16.0% reduction in round-05).
  * **Parameter Relay Excess (>5 parameters)**: Dropped from 845 to 775 (-70).
  * **Total Parameter Slots**: Decreased from 17,767 to 17,635 (-132).
  * **Lines of Code**: Reduced by 224 lines (72,443 to 72,219) while adding 11 cohesive methods.
  * **Repeated 4+-parameter shapes**: Decreased from 364 to 357 (-7).
  * **Comment/History hygiene**: Comment lines decreased by 114 (-1 history marker) without stripping public contracts or non-obvious invariants.
  * **Structural Authenticity**: Reductions in `gen_c_json.zen` (`JsonLower`), `gen_c_try.zen` (`TryPropagation`), `sema_match.zen` (`MatchCoverage`), and `lsp_diag.zen` (`WorkspaceTurn`) reflect genuine phase boundaries with zero parameter-bag padding.

---

### 5. Suggested Non-Overlapping Wave Assignments

```
====================================================================================================
AGENT 1: Call Lowering & JSON String Escaping (Backend Generation)
  - Target: src/gen/gen_c/gen_c_call.zen, src/gen/gen_c/gen_c_json.zen, src/gen/gen_c/gen_c_op.zen
  - Task: 1. In gen_c_call.zen, unify write_res_payload and lower_plain_call into CallSite / ResInit,
             eliminating 4 functions with 8+ parameters.
          2. In gen_c_json.zen, fix JsonLower.raw to use proper C string literal initialization
             without doubled opening braces.
          3. In gen_c_op.zen, remove the unused `be` parameter from write_position* and update
             call sites in gen_c_op, gen_c_cap, and gen_c_stmt.
  - Inspection Chain: Trace CallSite.resolve -> lower_resolved -> lower_fn -> emit in gen_c_call.zen;
                      inspect JsonLower.raw in gen_c_json.zen.
  - Verification: make test && make cap. Ensure generated C compiles cleanly with -Wall -Werror.

AGENT 2: Method Dispatch & Actor Send Lowering (Backend Monomorphization & Concurrency)
  - Target: src/gen/gen_c/gen_c_member.zen, src/gen/gen_c/gen_c_actor.zen
  - Task: 1. In gen_c_member.zen, lift MethodCallSite creation to pick_member so lower_method,
             method_kind, and intrinsic branching operate on MethodCallSite.
          2. In gen_c_actor.zen, introduce ActorSend record to encapsulate write_actor_send and
             write_send_value, eliminating 3 functions with 8+ parameters.
  - Inspection Chain: Trace lower_receiver_site -> with_site -> declared_member -> lower_method in
                      gen_c_member.zen; trace lower_actor_send -> write_actor_send in gen_c_actor.zen.
  - Verification: make test && make lint. Ensure actor send/spawn and method dispatch tests pass.

AGENT 3: Member Visibility & Expression Ordering (Semantic Analysis & Code Gen)
  - Target: src/sema/sema_member.zen, src/gen/gen_c/gen_c_expr.zen
  - Task: 1. In sema_member.zen, encapsulate known_access, pick, first_type, and select into
             a private MemberLookup value to clean up 6-slot parameter relays.
          2. In gen_c_expr.zen, group pure call-reordering predicates (holds, reorderable,
             may_reorder, position_calls) into a dedicated AST inspection group.
  - Inspection Chain: Trace value_access -> known_access -> pick -> settled in sema_member.zen;
                      trace expr -> value_expr -> write_expr -> value_held in gen_c_expr.zen.
  - Verification: make test && make lsp-test. Verify semantic diagnostics and LSP queries pass.
====================================================================================================
```
