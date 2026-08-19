# `gen/` shape — the parameter-threading campaign

A ledger, not an essay. Every row is one file, one agent, one commit.

---

## The measurement that started it

`src/gen` is 18,625 code lines — the largest subsystem in the tree, and
larger than TinyCC's entire C compiler while emitting *C text* rather than
machine code. Three hypotheses were tested, two were wrong:

| hypothesis | measured | verdict |
|---|---|---|
| comments are exploding | 5,541 comment lines, header essays 7.3% of code | **no** |
| it is hard-coded emitted C | only **6%** of lines contain a string literal at all | **no** |
| parameters are threaded by hand | **3,649 lines — 20% of all code — are one parameter on its own line** | **yes** |

Twelve names are **64%** of those parameter lines (2,325 lines, one in every
eight in `gen/`): `be`(556) `out`(384) `ctx`(374) `id`(211) `c`(189)
`want`(118) `rty`(99) `a`(87) `f`(87) `s`(82) `name`(70) `d`(68).

The same measure elsewhere: `sema/` 11.0%, `fmt/` 10.5%, `lsp/` 7.1%,
`std/` 6.5%. **`gen/` is triple the stdlib.** This is not the language.

**And the parameters are not independent values.** `rty` is derived from
`a.base`; `s = site_of(be, rty)`; `f`/`m` come from `s` + `a.name`. The list
GROWS as you descend a chain, because each link computes one more derived
value and hands the whole accumulated pile to the next. `lower_dot_call`
starts at 7 parameters and `lower_method` ends at 9.

**109 functions have a signature longer than their body** — 850 lines of
signature carrying 399 lines of body.

---

## The two moves

Rust, OCaml and Pony all answer this the same two ways, and neither is "a
struct with nine fields".

### Move 2 — classify, then dispatch  ← **DO THIS FIRST**

A chain of predicates is one classifier returning a sum type, matched once.
`gen_c_member.zen` has a six-link chain — `lower_method` →
`lower_written_method` → `lower_declared_method` → `lower_bound_or_method` →
`lower_floor_or_fat`/`lower_fat_or_method` → `lower_ordinary_method` —
**66 lines of signature carrying 43 lines of body**, every link forwarding
the identical nine values. It becomes one `MethodKind` enum whose variants
carry the derived values, computed once, and one `.match`.

**It goes first because every link is PRIVATE.** 52 of the 59 functions in
`gen_c_member.zen` are unexported. No signature crosses a file boundary, so
this parallelises one-agent-per-file with no merge coupling.

**It is a correctness change, not only a size one.** The precedence order of
the kinds — ptr before capability before door before floor before fat before
ordinary — exists today ONLY as the order of the call chain, explained in
scattered header comments. As one enum it is a readable list, and a new kind
cannot silently land in the wrong slot.

### Move 1 — receiver, not parameter  ← **AFTER Move 2, SERIALISED**

`be`/`ctx`/`out` become one `Lower` receiver: 1,251 parameter lines gone.
`CBackend` already holds `buf :: Emit` ("where a body is lowered") and
`check :: Checker` as fields, and already has `self :: @Self` methods — the
receiver exists, the lowering layer just does not use it. 622 call sites
forward literally `out`, unchanged, so this is safe; leaf emitters that write
into a temp (`ctype(be, v, cty)`, `write_vec_literal`) keep an explicit sink.

**This one changes exported signatures, so it is cross-file and must be one
agent at a time through the fixpoint.** `make build` is blind to
resolution-shaped changes; only fixpoint and the corpus see them.

---

## The gates every row must pass

Non-negotiable, in this order. A row is not done until all four are green.

1. `make test` — **529 passed, 0 failed, 4 deferred**. Any other number is a red.
2. `make fixpoint` — `stage2.c == stage3.c`.
3. **`cmp` THE EMITTED C, with `file:line:col` triples erased.** This is the
   gate that makes the campaign safe: a pure reshaping must move no C.
   ```sh
   ./zen build src --emit-c -o /tmp/after.c
   sed -E 's/"[^"]*\.zen", [0-9]+, [0-9]+/"F", 0, 0/g' /tmp/before.c > /tmp/b.n
   sed -E 's/"[^"]*\.zen", [0-9]+, [0-9]+/"F", 0, 0/g' /tmp/after.c  > /tmp/a.n
   cmp /tmp/b.n /tmp/a.n        # MUST be identical
   ```
   Line numbers must not move at all. If they do, the change was not pure.
4. `make fmt` and `python3 scripts/style.py`.

**Do NOT gate on `make build`.** It is blind to every resolution-shaped
defect this tree has ever had; a 1,195-name cull passed `make build` and then
failed fixpoint with 5 diagnostics and the corpus with 16 more.

**Do not regenerate the seed.** The integrator does that once, at the end.

---

## Phase A — chain collapse, file by file

`before` is the file's total line count at campaign start. `chain fns` is the
count of private functions with ≥5 parameters and a body of ≤6 lines — the
shape being collapsed. `their lines` is what those functions occupy today.

| ☐ | file | before | code | param-lines | chain fns | their lines | after | commit |
|---|---|---:|---:|---:|---:|---:|---:|---|
| ☐ | `gen_c_member.zen` | 1111 | 787 | 87 | 7+ | ~77 | | |
| ☐ | `gen_c_op.zen` | 817 | 567 | 128 | 14 | 171 | | |
| ☐ | `gen_c_expr.zen` | 879 | 597 | 84 | 11 | 118 | | |
| ☐ | `gen_c_call.zen` | 1250 | 869 | 106 | 12+ | ~130 | | |
| ☐ | `gen_c_stmt.zen` | 519 | 378 | 66 | 10 | 112 | | |
| ☐ | `gen_c_flow.zen` | 619 | 475 | 85 | 9 | 100 | | |
| ☐ | `gen_c_try.zen` | 838 | 570 | 104 | 8 | 94 | | |
| ☐ | `gen_c_bound.zen` | 655 | 506 | 78 | 7 | 82 | | |
| ☐ | `gen_c_cap.zen` | 720 | 558 | 65 | 6 | 77 | | |
| ☐ | `gen_c_fat.zen` | 770 | 567 | 57 | 6 | 64 | | |
| ☐ | `gen_c_const.zen` | 261 | 184 | 41 | 5 | 61 | | |
| ☐ | `gen_c_ptr.zen` | 579 | 440 | 43 | 5 | 59 | | |
| ☐ | `gen_c_index.zen` | 248 | 199 | 39 | 4 | 52 | | |
| ☐ | `gen_c_impl.zen` | 395 | 237 | 31 | 4 | 43 | | |
| ☐ | `gen_c_alloc.zen` | 305 | 204 | 38 | 3 | 45 | | |
| ☐ | `gen_c_floor.zen` | 281 | 194 | 49 | 3 | 37 | | |
| ☐ | `gen_c_read.zen` | 627 | 452 | 48 | 3 | 35 | | |
| ☐ | `gen_c_display.zen` | 352 | 259 | 29 | 3 | 35 | | |
| ☐ | `gen_c_layout.zen` | 862 | 689 | 29 | 2 | 27 | | |
| ☐ | `gen_name.zen` | 507 | 301 | 33 | 2 | 22 | | |
| ☐ | `gen_c_mono.zen` | 425 | 247 | 14 | 2 | 20 | | |
| ☐ | `gen_c_fmt.zen` | 315 | 219 | 42 | 1 | 14 | | |
| ☐ | `gen_c_build.zen` | 683 | 504 | 22 | 1 | 14 | | |
| ☐ | `gen_c_sink.zen` | 938 | 659 | 21 | 1 | 13 | | |
| ☐ | `gen_c_range.zen` | 689 | 500 | 53 | 1 | 12 | | |
| ☐ | `gen_c_array.zen` | 325 | 217 | 50 | 1 | 12 | | |
| ☐ | `gen_c_settle.zen` | 622 | 463 | 17 | 1 | 9 | | |

**`gen_c_member.zen` and `gen_c_call.zen` carry `+` because the counter that
built this table miscounts them** — it balances braces and a `{` inside a
string literal (`be.fmt("if (..) {\n")`) throws it off. Their chains were
read by hand instead. Trust the file, not the number.

**Phase A total: ~113 functions, ~1,328 lines, over 27 files.**

---

## Phase B — the `Lower` receiver

Not started. Blocked on Phase A landing, because the two moves touch the same
signatures and doing them together makes every conflict a three-way one.

---

## Phase C — the rule that stops it coming back

A `style.py` rule: a signature with **≥6 parameters** is a violation,
ledgered by file with a count like `UFCS_OWED`, so it can shrink and cannot
grow. Without this the campaign is a one-off and the shape returns.
