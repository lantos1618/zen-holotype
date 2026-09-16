# Zen ergonomics: values, ownership, and composition

Status: the implementation batches below are in place; the remaining outline
is grounded in the current compiler and an independent allocator/ownership review.
Proposed APIs below are not promises that the current language implements them.
The target is predictable daily programming with explicit allocation and tested
contracts. Numerical reviews identify remaining work; passing tests alone does
not establish an ergonomics score.

## Numeric conversion ownership

Numeric conversions now use a validated standard-library contract, described
in [numeric conversions](NUMERIC_CONVERSIONS.md). The six local bodyless
conversion declarations in scalar lowering, text parsing, and map indexing are
removed. Parsing composes with checked results, and map indexing reduces the
hash into the index domain before converting it. Failed scalar conversion
retains the positioned backend diagnostic.

Sema records the permitted standard declarations by identity; C lowering
consumes that record. A primitive conversion name cannot grant a source-local
bodyless function cast behavior. Existing generic widening bounds remain
supported and tested. Other intrinsic families and general first-class
callback support remain separate work.

This improves one concrete trust boundary. It does not establish complete
lifetime safety, whole-language backend parity, or an ergonomics score.

`usize.min(other)` is an ordinary function in `std.core.num`; backend emission
uses it instead of a private `smaller` definition. This requires no new
compiler-recognized numeric operation.

### Generic requirements

Multiple requirements currently use conjunction: `f<T: Eq + Hash, R> = ...`.
A proposed bracket spelling, `T: [Eq, Hash]`, is not implemented. Keep one
canonical spelling if this changes, with matching parser, formatter, diagnostics
and editor support. Requirements must identify operations the checker can
prove; names such as `Numeric` or `Copy` are not existing blanket guarantees.
Generalizing `min` requires an ordering contract, including its relationship
to equality and behavior for floating-point NaN. Arithmetic and display are
separate requirements and should not be added to a function that only orders.

## Source-review implementation round

- `Tester.expect_eq` is an ordinary generic `Eq` operation with executable
  equal/unequal integer, string and custom-equality cases. Native test discovery
  and benchmark execution remain separate work.
- Generic method substitutions settle literal families to concrete defaults,
  and literal receiver lookup considers contextual generic arguments before
  defaulting. Free and method results use the same numeric conversion surface.
- `Vec.add_all(source: Ptr<T>, count: usize)` reserves, copies initialized
  elements, then publishes length. It replaces `grow_by` in String and HTTP/2
  buffer writes. The caller owns the raw source bounds and lifetime; valid
  self/interior appends survive moving reallocation. Exported `Vec.len` remains
  externally readable, with mutation restricted to the declaring module.
- `values.sort(alloc).try()` offers stable O(n log n) sorting with explicit
  O(n) scratch. Allocation failure leaves the input unchanged. The existing
  allocation-free `sort()` remains insertion sort. Formatter candidate and
  edit ordering use the scalable overload and indexed interval queries.
- Structural AST walking takes an explicit scratch allocator:
  `tree.walk(alloc, root, visitor)`. Its iterative event stack preserves
  structural order and stops on visitor or allocation failure without growing
  the host stack with the expression depth.
- Named-binding ownership provenance follows assignments and joins across
  branches/callbacks. The standard `bool.then` is recognized by resolved
  declaration identity for once-or-never callback handling. General field and
  interprocedural allocator-region relations and repeated-loop fixed points
  remain incomplete; these fixes do not establish whole-language memory safety.

## Further ownership and compiler improvements

- Ownership follows direct field overrides, aggregate/indexed values, match
  results, and block-local result aliases. Repeated callback provenance is
  iterated to a fixed point before ordinary diagnostics run once. Exact safe
  field overwrites and caller-owned storage remain supported. Stores through
  borrowed parameters refuse local-arena origins; definite owner identities
  preserve explicit transfers without treating an unrelated transfer as safe. Deep/indexed
  writes are conservative; arbitrary interprocedural region/effect guarantees
  and complete actor sendability remain open work.
- Successful written-type observations use initialized indexed storage separate
  from context-sensitive type memoization. Repeated marks allocate nothing;
  failed growth preserves recorded observations and remains fallible.
- C lowering consumes an exact recorded call declaration without rediscovering
  candidates or falling back to an unrelated singleton. Calls lacking a record
  still use a compatibility lookup: field defaults and context-dependent generic
  trait bodies need complete per-instantiation semantic records before it can
  be removed. This is not a completed shared checked-call architecture.
- Syntax-level may-call facts are memoized per immutable expression identity.
  Iterative traversal avoids repeated subtree scans; allocation refusal remains
  conservative to preserve operand evaluation order.
- Editor cache rebuilds invalidate published values before fallible work and
  preserve borrowed input paths before releasing their previous arena. Failed
  rebuilding leaves empty accessors; retry remains supported. Written-type hover
  and definition can use validated observations after an Unknown memo.
- `zen check` validates source without emission or requiring `main`. The CLI
  parser takes the caller's allocator, so parsed configuration need not borrow
  local parsing storage after the parser returns.
- Backend key ordering uses the shared allocator-explicit stable sort over
  borrowed keys and original indices, eliminating a private merge algorithm
  and fabricated zero/empty fallbacks from guaranteed ordering positions.
- Aggregate differential checks include reproducible generated integer
  expressions against an independent evaluator, including lazy match and
  receiver effects, across C optimization levels and formatter roundtrips.

## First implementation batch

- `str.split_once` accepts a byte or string separator and returns borrowed
  `before` and `after` views. An absent separator returns None; an empty string
  separator yields empty-before/full-after. No allocator is needed.
- `Split.loop` now uses ordinary library methods to advance a fresh cursor for
  the supported callback arities. The callback shape selects value-only,
  handle/value, or handle/index/value traversal through the same loop name.
  Calling a traversal after manual next() still walks the full input, preserving
  previous indexed traversal behavior without changing the cursor.
- Direct dot traversal is sequential. Free `loop(split, ...)` and generic
  indexed operations retain their existing paths; the general iterator
  protocol remains future work. This batch adds no compiler Split special case.
- Semantic union canonicalization returns its vector. C backend helpers return
  qualified names, method signatures, and parameter types. Shared append paths
  stay in place, with the same allocation sequence as before.
- LSP frame parsing returns the first matching header from its scan instead of
  coordinating found/value/bad flags. Missing and malformed header faults and
  first-header-wins behavior are preserved.
- Server.workspace is a required field. Its factory explicitly supplies the
  initial empty view because initialization has not supplied a root yet; this
  removes the field default, not the existing empty-means-no-root convention.
- The runnable task example in `tests/corpus/actor/task_summary/` uses the new
  APIs and an explicit request-local arena. Its summary is consumed before that arena
  drops, so temporary vectors do not accumulate in the actor's persistent arena.

The focused split fixture covers skip/break/index behavior, callback error
propagation, receiver evaluation once, empty pieces, repeated traversal, and
16,385 pieces. Generated C inspection and temporary instrumentation confirm
cursor advancement rather than rescanning. The parser fixture checks separator
boundaries and verifies that both returned pointers borrow the original buffer.

First-batch validation: the stable-source full corpus passed 1,179 active cases, with
one existing deferred case. An earlier run also passed those cases but was
invalidated by the harness because a source file was formatted during it; it
was repeated after edits finished. Native C objects were cached, while Zen
emission, linking, execution, and assertions still ran. The full compiler
fixpoint and matching seed, six determinism axes, 14 differential cases,
formatting, source gates, UBSan with its positive control, 54 incremental-build
checks, and 14 runner checks passed. Seed warning baselines fell to GCC 1,855
and Clang 1,885; emitted-fixture baselines remain 1 and 8.

The independent post-change review found no blocking issue in this batch and
rated the task-level Zen example about 7.5/10. It highlighted two limits: generic
indexed traversal is still separate, and creating a local arena can itself
trap on allocation failure under the current runtime policy. The example's
SummaryError.OutOfMemory covers vector growth, not every allocation in request
processing. Neither lifetime safety nor recoverable OOM should be inferred
merely from the presence of an Alloc argument.

## Composition implementation batch

The current source adds the following operations and compiler support.
`make verify J=8 TEST_J=8` passed in 154.16 seconds: 1,197 active corpus cases
passed, with one existing deferred case. Formatting and source gates, six
determinism axes, the complete 182-unit C/header fixpoint and matching seed,
14 differential cases, UBSan with its positive control, 54 incremental-build
checks, and 15 runner checks passed. Signature and source-health inventories
are current. Earlier validation results below describe their own source batches.

Ordinary loop completion labels are now emitted only when referenced, including
references through captured outer handles. Seed warning counts fell from GCC
1,122 / Clang 1,152 to 937 / 967 without suppression; emitted-fixture counts
remain 1 / 8. The first aggregate attempt found one old generated-C expectation
that counted unused labels. After correcting that expectation and its comment,
the full gate passed on unchanged compiler source. The warm build check in that
run took 0.06 seconds; this is an observed local result, not a timing budget.

- `bool.ensure()` returns optional unit, while `ensure(reason)` retains the
  caller's error type. A guard can propagate absence without inventing an error.
- `str.lines()` borrows LF/CRLF-delimited lines, retains interior empty lines,
  omits a final extra line, and preserves lone CR bytes. Its value,
  handle/value, and handle/index/value loops restart a fresh cursor and do not
  allocate. The task actor now uses these lines directly and still consumes its
  summary within request-local storage.
- `map` supports value, handle/value, and handle/index/value callbacks and
  returns `Res<Vec<U>, AllocError>`. `filter` takes a value predicate and returns
  `Res<Vec<T>, AllocError>`. Both take an explicit allocator; callers of the
  previous optional-result API must migrate `None` handling to `Err`. Empty maps
  and filters with no accepted elements return empty vectors without requiring
  a backing allocation.
- Inlined helper failures return to that helper's result. Callback `.try()`
  keeps the lexical caller's return destination, including through nested
  helpers. Cleanup follows the emitted blocks crossed by that exit. Lifted
  thread and defer bodies isolate their return targets; direct `.try()` in a
  unit-returning deferred body is rejected before invalid C is emitted.
- Nongeneric callback parameter and return annotations constrain generic
  inference before ordinary actual arguments. Explicit type arguments remain
  authoritative, and incompatible concrete arguments still fail. Generic
  range wrappers forward their declared bound arguments symbolically rather
  than guessing an element type. Overload exclusion uses only conservative
  proofs and preserves declaration diagnostics.
- Folds accept value/accumulator, handle/value/accumulator, and full indexed
  callbacks. Stored ranges, arrays, Vec, and supplied Range implementations use
  the accumulator type independently of the element type. `at(None)` is natural
  exhaustion and returns `Ok(acc)`; `h.break()` still returns `None`, and
  `h.break(value)` overrides the accumulator. `Range.at` has its own inline
  return target for optional propagation.
- Inline unions of uniquely named members support exhaustive constructor
  matching with their existing tags and payloads. Nested payload patterns
  preserve their conditions, and a bare member case does not shadow its type.
  An omitted member is still diagnosed.
- C member lowering puts completed signature construction on `Site`, borrowing
  the mutable backend and reusing its receiver/module facts. Other lowerers keep
  the existing append APIs for shared signature storage.
- The corpus runner explicitly selects its staged standard library, so an
  isolated compiler executable cannot silently replace the tested source with
  the library beside that executable.

`Split` and `Lines` now provide sequential folds through all three `loop`
callback shapes. Each traversal starts a fresh cursor and preserves the
receiver's cursor, early break, and lexical error propagation. Inline generic
methods retain their own type arguments; callback annotations constrain member
calls in the same order as free calls, without overriding explicit arguments
or incompatible concrete values.

Sequential iteration is still incomplete as a shared protocol. `Lines` cannot
feed generic Range-based `find`/`map`/`filter` consumers. `Split`'s generic/free
indexed Range paths can still rescan and be quadratic; the sequential guarantee
belongs to its direct methods. Generic callback inference
also remains distinct from complete first-class callback support. Enum-name
parsing, enum JSON policy, complete lifetime checking, and recoverable allocation
of a new arena remain separate work. These changes do not establish a 9/10
writing experience across the repository.

## Consolidation and backend boundary batch

This source batch consolidates repeated operations and closes two concrete
feature/cache interactions:

- Callback annotations now constrain bounded overload selection through the
  same inference used for selected calls. Explicit type arguments and concrete
  argument contradictions remain checked. The three new fixtures failed under
  the prior compiler; they and ten related cases pass under a private candidate.
- Loop-result inference indexes relevant immutable AST syntax once. Repeated
  queries retain per-context checking and expression order; no whole-AST scan
  is needed for every possible break site. A frozen-input comparison measured
  11.8% less C-emission time with byte-identical output.
- HTTP/2 HPACK decoding owns a bounded borrowed block, cursor, and caller
  allocator. Integer/string/field decoding are methods; raw strings and static
  names borrow existing bytes. Truncated blocks and overflowing ranges return
  errors, and header filtering treats mixed-case names consistently.
- LSP copies use the existing str.dup operation, replacing 19 calls through a
  duplicate reply-module helper without changing their allocator choices.
- Code generator selection is separate from output delivery and platform
  targets. The working C adapter owns lowering/rendering and publishes borrowed
  artifacts synchronously. The later scalar backend batch is described in
  [Code generation](BACKENDS.md); neither boundary implies whole-language
  shared lowering or general cross-compilation support.
- Incremental build validation records include-search candidates as well as
  resolved dependencies. Header shadowing invalidates object reuse. Every native
  compilation uses ccache preprocessor mode to avoid stale direct-mode history;
  opaque includes decline reuse conservatively.

Aggregate validation: `make verify J=8 TEST_J=8` passed in 176.30 seconds on
September 9, 2026, with the source tree unchanged during the run. The corpus
passed 1,203 cases, with zero failures and one existing deferred ownership case.
Formatting, source gates, six determinism axes, the 182-unit C fixpoint plus
header and seed match, 14 differential cases, warning ratchets, and UBSan with
its positive control passed. Build validation passed 54 checks and 16 header
search scenarios with both native compilation and ccache; all 15 runner checks
passed. Seed warnings fell to GCC 936 and Clang 966 without suppression.
These checks do not establish the numerical ergonomics target or complete
borrowed-view lifetime enforcement.

## Module and shared-operation consolidation

Standalone networking modules belong directly under `std.net`: socket, TLS,
and SSE retain their public import paths without single-file directories.
SSE remains an independent incremental protocol decoder; it does not belong
inside the HTTP/1.1 client or general text utilities. Protocol identifiers use
represented enums while combinable flags retain their bitset semantics.

`std.text` owns borrowed text scans, numeric conversion, and format-hole grammar.
`std.parse` owns Zen syntax, and `fmt` owns source layout and trivia preservation.
Share their general text operations downward without moving compiler policy
into the standard text library. Source-literal escape stepping and diagnostic
positions remain compiler concerns. LSP UTF-16 conversion remains distinct from
AST byte columns, even when a located line is reused.

CLI parameter-name and alias collision rules belong to `Parameter`; commands
search their later declarations and consume the returned collision. Refactoring
validation must preserve diagnostic precedence as well as accepted inputs.

Two larger follow-ups require explicit contracts before implementation:

- Unused-code hints need a semantic use index, initially for private top-level
  functions. Generated C is not a complete usage index: inlining, generics,
  reflection, trait methods, and actor/drop hooks can consume declarations
  without emitting an independent function. Executable reachability should
  eventually root at `main`, while raw module emission retains its module roots.
  An advisory hint must not be represented as a rejecting semantic error.
- Most process orchestration can move from `proc.c` into Zen, but the current
  C importer does not expose the required records, globals, macros, and typed
  pointers, and project builds do not yet attach translated planned imports.
  Preserve the native boundary until spawn-action layout, `errno`, `environ`,
  polling, wait-status normalization, and interrupted-call behavior have a
  supported representation. A header list alone cannot replace that behavior.

The AST contract remains maintained documentation: stable node identities,
trivia ownership, and source coordinates are shared consumer invariants rather
than generated source-health evidence.

Validation on September 9, 2026: `make verify J=8 TEST_J=8` passed in 245.19
seconds with the source tree unchanged. The corpus passed 1,204 cases with zero
failures and one existing ownership case deferred. All required gates passed,
including the 182-unit compiler/header fixpoint and seed freshness, six
determinism axes, 14 differential cases, warning ratchets, UBSan with a positive
control, build-cache checks, and test-runner checks. Seed warnings decreased to
GCC 933 and Clang 963 without suppression. Boundary controls reproduced the
previous unsupported-radix acceptance and LSP length overflows; formatter and
CLI declaration comparisons preserved diagnostics and first-error precedence.

## The ownership contract to build around

A function can already accept an Alloc and return a String allocated through
it. The allocator's owner controls the bytes' lifetime; the function's frame
only contains the returned descriptor. Passing the result through another
helper does not copy its text or change its allocation region.

```zen
to_json = std.json

Status = Todo | Done
Record = { status: str }

encode = (a: Alloc, value: Status) Res<String, AllocError> {
    record = Record(status: value.variant_name());
    record.to_json(a)
}

main = (env: Env) Res<i32, AllocError> {
    arena ::= env.mem.alloc();
    text = encode(arena, Status.Done).try();
    env.out.println("{}", text.view());
    Ok(0)
}
```

This uses existing enum-name reflection and record JSON encoding. Automatic
JSON representation for arbitrary enum values is a separate API decision.
The example produces `{"status":"Done"}`. Arena drop releases the bytes at
main's scope exit. No per-string defer is needed. A checked example under
`build/ownership-ergonomics/` also forwards the String through a second helper.

Existing precedents are `Display.toString(self, a)` in
`src/std/core/display.zen`, `join_path` in `src/std/core/path.zen`,
`TypeStore.name_of` in `src/sema/sema_ty.zen`, and `member_symbol` in
`src/gen/gen_c/gen_c_member.zen`.

The distinction between three values must be easy to discover:

| Value | Current responsibility |
| --- | --- |
| Arena | Owns pages; Drop releases them together. |
| Alloc | Copies an allocation interface handle; does not own its backing allocator. |
| String / str | String is a growable Vec descriptor; str borrows bytes. Neither extends the arena's lifetime. |

String and Vec currently have no Drop implementation. Arena.free is a no-op.
Dropping a String binding therefore does not individually reclaim its storage.
A borrowed view can also become invalid when its String grows.

A locally created arena must not back a result returned without its owner.
The current compiler rejects the straightforward case with an ArenaEscapes
diagnostic; the reachable local-arena JSON example was checked explicitly.
This is evidence for that case, not a proof of complete lifetime enforcement.
The present checker uses syntactic taint tracking and does not establish a
region relationship for every assignment, branch, alias, and nested scope.

## Returning an owner is different from cancelling defer

For actual Drop values, Zen already supports explicit consume and preserves
certain directly returned bindings during cleanup. This is distinct from
String's current arena-backed descriptor semantics and from universal
inference of last-use moves.

Explicit standard destructor calls now require a consumed concrete local owner.
The checker uses the selected member's supplying declaration, including
interface dispatch, rather than the method's spelling. Destroying a tracked
local arena invalidates its dependent views across the supported branch joins.
This closes explicit-destruction cases; it does not establish general borrow
regions, field destruction/reinitialization, or per-instantiation reflection
lifetime facts. Type-qualified methods lower with an explicit receiver using
the same method symbols as instance calls.

Arbitrary defer callbacks run unconditionally, before automatic drops. Returning
a value does not cancel its defer. Captures are copied at registration, so a
later mutation of a scalar transfer flag is not a general workaround.

The intended ergonomic rule should be:

- Caller-region allocation: pass the allocator inward, return values freely
  within that region, and let the region owner clean up.
- Independently owned resources: ownership-aware return/consume transfers the
  cleanup responsibility; the last owner drops the resource exactly once.
- Explicit deferred side effects: always run at the registered scope exit.

Do not implement "defer free unless returned" by inspecting arbitrary deferred
code. Do not extend an allocation's lifetime silently or copy it to another
region automatically. If a result must outlive its allocation region, allocate
in the destination region, explicitly copy into it, or transfer a supported
owner whose allocator handles remain valid after moving.

Adding Drop to String would be an ownership redesign, not a small cleanup.
For example, str.dup(a) currently returns the view of a local String and relies
on arena ownership. A per-buffer destruction policy would require an audit of
such APIs, constructors, copies, nested containers, borrowed views, and stable
allocator handles. Independently freed buffers also require an allocator whose
release policy actually supports that reclamation.

## Compiler API and file organization

Files are module/visibility boundaries, not runtime allocation scopes. Moving
a function between files does not change the lifetime of the allocator passed
to it. Cross-module imports and forwarding are organization costs, not reasons
that all results must use output parameters.

Use a value-returning operation when its result is a distinct object: a symbol
name, rendered diagnostic, JSON document, or resolved semantic model. Supply
an allocator directly or through the receiver when that receiver owns the
appropriate allocation region.

Keep an append operation when composing many fragments into one destination.
The public convenience operation can allocate one buffer, invoke the append
implementation, and return it. Display already provides both forms. Turning
every fragment append into a newly allocated String can add copying and retain
all intermediate buffers until arena drop.

Group methods and private helpers around an operation and its invariants:

- Checker owns semantic state and caches.
- Backend owns emission state and symbol publication.
- A formatter/emitter owns its destination and rendering options.
- A short-lived operation value may own immutable inputs or configuration.

Do not copy Checker or Backend into an operation struct merely to remove a
parameter. Mutable identity must remain intact. Consolidate files when callers
must traverse them together to understand one operation; preserve separate
modules when they represent independently understandable behavior. Avoid file
count targets and arbitrary maximum line counts.

## Implementation order and acceptance criteria

### 1. Establish the ownership and cost contract

Document allocator-in/value-out as the normal allocating-helper pattern.
Audit temporary versus persistent allocations in representative sema, codegen,
and actor paths. Extend lifetime checks with real escape regressions, including
assignment, nested blocks, branches, returned aggregates, and aliases. Identify
whether the current taint mechanism can express the necessary relationships
before extending it with additional syntax-specific exceptions.

Acceptance: caller-allocated returned values work; supported owner transfers
clean up exactly once; invalid local-region escapes are rejected with a useful
diagnostic. A long-running actor's temporary allocations are reclaimed after
each request rather than accumulating until shutdown. Persistent actor state
must not retain those temporary borrows.

### 2. Repair sequential iteration and add the missing string operations

Split.next already walks sequentially, but Split's Range.at rescans from the
beginning. Current generated C confirms the nested rescanning loop. Introduce
a coherent sequential iteration path, distinct from indexed access where
appropriate. Avoid a growing list of compiler special cases for particular
containers.

Borrowed split_once and lines are implemented with specified empty-input,
CRLF, and trailing-newline behavior, preserving split's delimiter semantics.
Direct loops support value-only traversal and explicit control. Indexed forms
still include a handle; the general sequential consumer protocol remains open.

Acceptance: iteration scales with input size, agrees with established behavior,
and does not allocate merely to supply a convenient loop. Validate byte visits
or scaling, not only a three-line output fixture.

### 3. Make fallible operations compose

Typed map/filter allocation failures and lexical callback propagation are
implemented, as are supplied-range folds and callback annotation inference.
Collecting takes an explicit allocator; direct traversal and folds do not
construct an intermediate Vec. The remaining composition work includes general
sequential consumers and accepting suitable named callbacks without adapter
lambdas whose only purpose is satisfying the library's shape.

Use existing .try(error) and .try(mapper) where appropriate. Optional absence
and typed failure remain distinguishable. Evaluate any shorthand for converting
absence using actual call sites; do not silently discard the failure reason.

Add enum-name parsing through supported reflection with an explicit policy for
wire spelling, case sensitivity, and unknown names. Do not accidentally couple
stable protocol strings to internal source renaming.

Acceptance: parse/map/fold stop at the first error, retain line context, expose
allocation failure, and do not keep a partial result alive longer than needed.

### 4. Apply the APIs to coherent compiler operations

Semantic union canonicalization and Site-owned C method signatures now return
completed values. Continue applying that boundary to coherent semantic and
emission operations while keeping shared-output composition inside the writer. Consolidate helpers that share one operation's invariants.
Measure retained allocation volume and compiler emission time before and after.

Acceptance: fewer forwarding parameters and cross-file jumps, unchanged output
and diagnostics, and no unexplained increase in copying, retained memory, or
compiler time. Batch related changes and run the relevant tests once per batch.

### 5. Refine actor request lifetimes and failure behavior

Keep method-call message sending and actor-owned persistent state. A handler
can already create an explicit local arena through ctx.env.mem.alloc() for
scratch results consumed within that turn. Make that pattern easy to express
and validate before introducing an ambient per-turn allocator.

Document copied payloads and mailbox allocation. Distinguish allocation refusal
from saturation when recovery requires different actions. Evaluate structured
actor cleanup without hiding admission closure, draining, or blocking joins.

Acceptance: repeated requests have bounded temporary memory, transferred data
outlives the sender where promised, and shutdown/error paths remain observable
and testable.

## Keeping the accepted style in place

`docs/STYLE.md` is the code-review contract; root `AGENTS.md` directs automated
contributors to it. The task actor under `tests/corpus/actor/task_summary/` is
a compilable reference in the normal verification corpus, including malformed
input checks. Update that reference when a shared API improves; do not hide a
missing feature behind a new per-example convention.

Traversal has one name:

```zen
values.loop((value) { /* every value */ });
values.loop((h, value) { /* break or skip when needed */ });
values.loop((h, index, value) { /* also use the zero-based index */ });
```

Use the three-parameter form when an index is needed. Two untyped parameters
mean handle/value; callback variable names do not select overloads. The
value-only form is implemented through a normal library overload. A generic
bound must participate in deciding whether overloads can accept the same call;
a constrained range overload must not be rejected merely because an
unconstrained type variable could accept bool or a condition function.

The follow-up removes the each aliases and adds value-only loop coverage for
Range, arrays, Vec, and Split. Overload regressions exercise declaration order,
explicit type arguments, unsatisfied bounds, and diagnostics from invalid impl
declarations. The duplicate raw-argument bound check is removed; instantiated
substitutions remain the authoritative check. Backend roots inspect individual
overloads so generic definitions are emitted with a call instantiation.

This is a bounded constraint check. Optional and variadic inference stays
conservative, and it does not introduce general constraint-based selection
among generic candidates. The focused integration checks passed before the
source was frozen for aggregate verification.

The generated-C warning gate caught unnecessary index-origin state in value
traversals. LoopSite now creates that state only for indexed callbacks;
RangeWalk models its absence explicitly. Indexed nonzero ranges and folds
retain their origin. The measured seed warning counts fell to GCC 1,122 and
Clang 1,152, with no warning suppression.

Final follow-up validation: `make verify J=8 TEST_J=8` passed in 230.74 seconds
on this machine. The corpus passed 1,184 active cases with one existing deferred
case. Formatting, source gates, six determinism axes, the complete 182-unit C
fixpoint plus header and seed match, 14 differential cases, GCC/Clang warning
ratchets, UBSan with its positive control, 54 incremental-build checks, and 14
runner checks all passed. Signature and source-health inventories are current.
The full test target now uses the existing C cache and worker controls while
always running the full suite.

Formatting and semantic/runtime behavior can fail automated gates. Placement
of an operation, a meaningful default, or the reason for a file split still
needs review. Do not replace that judgment with line-count or style-score
thresholds. Full lifetime enforcement remains an explicit implementation gap.

## What would justify 9/10

Re-evaluate the task summarizer, a CLI, a binary decoder, an actor service, and
a formatter under equivalent requirements. Review writing and modification
effort, compiler diagnostics, explicit failure handling, allocation/lifetime
clarity, and predictable costs. Also track build and check turnaround.

The desired everyday experience is a caller choosing allocation scope once,
helpers returning meaningful values, normal loops requiring little ceremony,
and ownership errors explaining whose storage would expire. These properties
must hold through helpers and modules, not only in one attractive snippet.

The independent earlier review put the synchronous task at Zen 7/10, Go 8/10,
and Nim 8.5/10, with an approximate half-point uncertainty. Those are subjective
example-level assessments. Completing this plan is grounds for another review,
not an automatic entitlement to a 9/10 label.

## Scalar backend foundation

JavaScript and GNU x86-64 assembly now have concrete renderers behind the
backend selection boundary. Their shared lowerer preserves evaluated local
values in distinct slots and uses sema-selected declarations. Typed basic
blocks carry explicit terminators; verification checks types, references,
signatures, and definite assignment before artifact publication. Arithmetic
traps retain operator source locations. Hexadecimal byte encoding reuses the
standard String writer.

This is a bounded scalar implementation. C still owns the full-language
lowering and runtime path; actors, allocator capabilities, generics, and
closures have not migrated. [Code generation](BACKENDS.md) records the
implemented surface, runnable example, and acceptance criteria for extending
the shared boundary. No numerical ergonomics or compilation-speed target is
claimed by this change.

## Generated-program runtime checks

Call selection, member providers, substitutions, and checked signatures now
publish as one successful semantic result. Rejected contextual rechecks erase
the previous selection. C consumes complete checked method substitutions, and
the scalar lowerer consumes checked signatures and result types. Generic
literal arguments and receivers receive range checks after substitution;
`identity<u8>(300)` is rejected instead of compiling to a truncated value.
Argument binding plans, conversions, captures, cleanup, and full-language IR
migration remain open work in [Code generation](BACKENDS.md).

`make verify` includes `runtimecheck`: scalar loops, growing Vec/Map, String
construction, stable sorting, and a capturing generic callback are checked
against independent expected results and C references. Map allocation budgets
are deterministic gates; execution times remain reported measurements. Run
`tests/bench/runtime/run.py` for larger repeated samples. Reference container
representations and formatting algorithms differ, so their timing ratios do
not isolate backend overhead. Known-length Map slot initialization reserves
once before filling the table. Generated reports remain under
`build/source_health/`.
