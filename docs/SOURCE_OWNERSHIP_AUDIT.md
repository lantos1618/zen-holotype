# Source ownership audit

This audit asks one question of every Zen source declaration:

> Is this behavior owned by the value, phase, or domain where it is written?

The exhaustive evidence is [ZEN_SIGNATURES.md](ZEN_SIGNATURES.md). It contains
the body-free declaration surface of all 227 files below `src`: 7,202
top-level declarations, including private declarations, imports, constants,
types, functions, and `impl`s. It is generated with Zen's tree-sitter grammar
by `scripts/zen_signature_inventory.py`; it is not a regular-expression scan.

This document is the judgement applied to that inventory. It is deliberately
not a proposal to merge files until their count looks smaller. Repeated state,
wrong dependency direction, copied policy, false error types, and comments
that describe the act of construction are the problems. File count and line
count are only symptoms.

## Coverage and method

| Area | Files read | Principal question |
| --- | ---: | --- |
| `fmt` | 5 | Is formatting state owned by the renderer, and are comments durable? |
| `gen` | 60 | Which lowering phases are hidden in repeated parameter bundles? |
| `lsp` | 18 | Which work is protocol handling, compiler query, presentation, or JSON? |
| `sema` | 42 | Which walks share a real lifecycle, and which remain distinct analyses? |
| `std` | 91 | Which local workaround is actually missing standard/compiler behavior? |
| `zen` | 11 | Does project building own flags, toolchain policy, and runtime needs? |
| **Total** | **227** | **Every `src/**/*.zen` file** |

The review had four passes:

1. Parse every source file and extract declarations without bodies.
2. Review `std` and `lsp` independently from the compiler, generator, semantic
   checker, formatter, and project driver.
3. Give the complete inventory plus `STYLE.md` and `GEN_C_SHAPE.md` to Gemini
   for a second similarity and consolidation pass.
4. Challenge each large recommendation against bodies, ownership, allocation,
   lifetime, dependency direction, and preserved behavior.

The fourth pass matters. A similar signature is evidence of a possible
concept, not proof that its parameters should become a record or that its
files should merge.

## Decisions

### 1. JSON needs one syntax engine, not one ownership model

There are currently two implementations of JSON grammar:

- `json_read.zen` recursively parses into `Jsons`;
- `json_stream.zen` independently tracks containers, commas, colons, quoted
  tokens, atoms, and byte offsets;
- the stream implementation imports `decode_text_token`, `number_token`, and
  `MAX_NESTING` from the recursive reader to keep only part of the grammar in
  sync.

This is a real false boundary. A syntax fix can land in one parser and not the
other.

The correct target is one incremental syntax machine with more than one
consumer:

```text
bytes -> JSON syntax machine -> zero-copy tree consumer
                            \-> owned event consumer
                            \-> callback/sink adapter
```

The consumers deliberately have different ownership:

- whole-document `read` should continue borrowing unescaped strings and
  number lexemes from its stable input where possible;
- public streaming events must own token bytes that outlive a feed buffer;
- an actor or HTTP client should be able to route each completed event without
  retaining all earlier events.

Therefore `events :: Vec<JsonEvent>` does **not** become a field of `Decoder`.
Caller-owned output, a callback, or a small event-sink contract preserves
draining and backpressure. Likewise, `read` must not be naively rebuilt on the
current `JsonEvent`, whose `Key`, `Text`, and `Number` variants own `String`s;
that would replace the existing zero-copy path with allocation per token.

The implementation lane is:

1. Extract escape, Unicode, number, whitespace, nesting, delimiter, and offset
   rules into one private syntax state machine.
2. Give that machine a consumer boundary that can spell borrowed tokens for a
   stable document and owned tokens for arbitrary feed buffers.
3. Implement the tree and event APIs as consumers of the same transitions.
4. Delete `decode_text_token` and `number_token`; they exist only as a bridge
   between the two current grammar owners.
5. Generalise JSON writing from `String` to an output sink. Keep `to_json` as
   the allocating convenience API.
6. Replace `json_meta.zen`'s fourteen primitive `write_*` ABI doors with one
   typed encoding contract once code generation can resolve the contract
   without magic symbol strings.

Physical files should still distinguish syntax state, tree storage, event
API, and encoding. The consolidation is one grammar, not one giant file.

### 2. LSP must depend on workspace queries, not the project driver

`lsp_query.zen` imports `Build` from `zen.zen_build` and root/path policy from
`zen.zen_path`. This makes an editor protocol layer depend on the command-line
driver. The direction should be:

```text
CLI -----\
          -> workspace/compiler query -> parser + sema
LSP -----/                         \
                                   -> overlay filesystem input
```

Move the overlay-aware operations behind a protocol-neutral workspace query:

```zen
check_standalone(alloc, name, text)
check_workspace(env, alloc, root, entry, documents)
check_project(env, alloc, workspace, path, text)
```

The LSP may own URI conversion, document versions, request routing, wire
positions, JSON-RPC errors, and response shapes. It should not own build-root
discovery or compiler construction.

Three repeated LSP bundles then have credible owners:

- a decoded request owns `tree`, `request`, and `id`, plus parameter access;
- a request turn owns the temporary allocator and response output;
- a checked document owns the checker plus the root/relative-path identity
  produced by one query.

These records should be introduced only where they shorten a complete route.
If every method still accepts `tree`, `id`, or output separately, the record is
only a parameter bag and has failed its purpose.

`lsp_hover.zen` also passes `(Checker, out :: String)` through a long semantic
rendering walk. The rendering is not an LSP wire concern. Give semantic
presentation an output sink and leave LSP responsible for selecting a value
and wrapping the result. This also gives diagnostics, hover, and future tools
one spelling of types and declarations.

Manual JSON punctuation remains in action, colour, completion, diagnostics,
formatting, reply, and symbols. The typed encoder must first support vectors,
dynamic-key objects, and explicit omit/null policy; then these modules should
emit typed response records directly. Do not preserve punctuation helpers as
an accidental LSP sub-language.

Finally, remove the user-visible response that says to read
`docs/design_lsp.md`. Repository planning notes are not a JSON-RPC diagnostic.

### 3. Actor and streaming boundaries must be explicit

The actor address type publicly declares `stop`, while generated behavior
dispatch makes a send appear as `receiver.receive(message)`. That overloads
the name of the actor's behavior with mailbox admission and hides the
asynchronous boundary from a user.

The language/runtime design should expose one address operation, conventionally
`send` or `tell`, constrained by the actor's `Receive<Message>` behavior. The
actor still implements `receive(context, message)`. Compiler lowering should
resolve that contract, not recognize more untyped name strings.

For HTTP/2 and streamed JSON, the useful actor boundaries are:

- input/frame actor: owns incomplete wire bytes;
- connection/session actor: owns protocol state;
- body receiver: owns application messages or byte chunks;
- writer actor: owns ordered output and backpressure;
- workspace actor in the LSP: owns expensive checking and generation IDs.

Messages crossing those boundaries must own their bytes. Borrowed `str`, an
arena-backed `Jsons`, or a temporary request allocator cannot escape to a
receiver. A build response must carry a document generation so stale results
can be dropped.

This does not mean every `Sink` is an actor. A sink is a synchronous output
capability; an actor is an asynchronous owner with a mailbox and lifecycle. A
sink can be implemented by an actor adapter when ordering/backpressure needs
that boundary.

### 4. `gen_c` should name phases while keeping distinct decisions split

The strongest repeated bundles are not generic helpers. They are unnamed
lowering phases. The most obvious example is actor creation:

```text
spawn_known       12 parameters
write_actor_spawn 13 parameters
write_spawn_value 16 parameters
```

The chain repeatedly carries the call/access, result and actor types, runtime
layout types, context, output, and generated callback names. Introduce an
immutable `ActorSpawn` site for facts discovered together, followed by a
smaller lifecycle/layout value once callbacks and runtime types are resolved.
Make emission operations methods of that phase or the backend. The conversion
is successful only if `CBackend` and the output do not continue to be repeated
through every method.

The same test applies to these high-value lanes:

| Area | Candidate concept | Evidence |
| --- | --- | --- |
| `gen_c_actor` | `ActorSpawn`, `ActorLifecycle` | 12–16-slot relay chain |
| `gen_c_inline` | `InlineSite`, `InlineBindings` | call, closure depths, context, destination relayed together |
| `gen_c_cap` | `CapabilityCall` | receiver/call/result/context/output repeated after one classification |
| `gen_c_assoc` | `AssocCall` | nearly every operation carries the same call and output state |
| `gen_c_bound` | `BoundCall` | bound lookup and emission facts travel together |
| `gen_c_call` | extend the existing `CallSite` | the type exists, but not all downstream relays use it |
| `gen_c_display` | `DisplayCall` | value/type/result/output repeat through recursive spelling |
| `gen_c_floor` | `FloorCall` | floor type, destination, and output travel as one site |
| `gen_c_index` | `IndexCall` | receiver/index/result/context form one lowering decision |
| `gen_c_threads` | spawn/join site values | thread runtime names and result state repeat together |

`gen_c_json` and `gen_c_try` also have high-arity signatures, but are not
automatic context-record conversions. Their values change across recursive
steps. First prototype one complete call chain and prove that the fields are
born together and share a lifetime.

Loop, range, array, and fold lowering share iteration shape and lifecycle.
They should share a phase state and stop forwarding it through sibling
imports. They should **not** become one file: range protocol selection, fold
accumulation, and loop control are separate decisions with separate tests.

Keep the explicit boundaries already recorded in `GEN_C_SHAPE.md`:

- member lookup versus impl selection;
- expression dispatch versus call lowering;
- general typing versus `try` propagation;
- value members versus static members;
- LSP session lifecycle versus JSON-RPC response shapes.

### 5. Build policy belongs to the project builder

`zen_project.zen` repeats `(env, alloc, job, planned)` and `link_exe` expands
to nine parameters. It also owns policy that is currently encoded as local
workarounds:

- `host_target` hard-codes one host tuple;
- compiler executable and linker flags are literal strings;
- `add_std_floors` scans generated C for spellings such as `zg_proc_` and
  `SSL_` to infer native dependencies.

Introduce a `ProjectBuild` phase that owns the environment, allocator, build
arguments, plan, and outputs for one invocation. Build flags should enter
through the `build.zen` project description / builder arguments used by
`zen build` and `zen run`, rather than being re-parsed by feature-specific
files.

Separate host/toolchain policy from the project plan:

```text
ProjectBuild -> Toolchain + Target + BuildArgs
generator    -> RuntimeNeeds (proc, tls, threads, ...)
linker       -> flags derived from RuntimeNeeds and Toolchain
```

That deletes the generated-C substring scan and gives non-GNU or non-Linux
targets one owner. `zen build`/`zen run` must locate and execute `build.zen`;
the CLI is only the entry to this API, not a second build configuration
language.

`zen_build_plan.zen`'s `Executor` is a partial evaluator for project files.
It is probably a future consumer of the compiler's compile-time evaluator,
but deleting it now would be unsafe: the shared evaluator must first support
the closed build effects, step budget, and diagnostics the project runner
requires. Treat this as a staged convergence, not a file merge.

### 6. Reusable text, hashing, and qualified-name behavior moves downward

Local formatters such as hexadecimal digit tables, fixed-width hex writers,
integer writers, byte append variants, and qualified-name slicing are symptoms
of missing owner methods.

The preferred shapes are:

```zen
out.add(byte)                 // one byte/value; no add_byte/add_bytes family
out.write_hex(value, width)
out.write_usize(value)
name.last_segment()
text.after_last('.')
```

One-value and many-value operations must remain semantically distinct:
`add(value)` and `add_all(values)`. Removing `add_byte` does not justify an
ambiguous `add_bytes` alias.

Qualified-name leaf extraction is currently repeated across semantic matching,
path construction, flow lowering, and build code. There are both structured
`QualifiedName` and dotted-`str` versions; at least one implementation appears
to select the first dot while another selects the last. Put structured segment
operations on `QualifiedName` in `std.ast`, and the generic delimiter operation
on `str` in `std.text`. Domain code should not implement either scan.

`sema_id` and `TyId` hashing manually apply mixing constants and ignore the
passed `Hasher`. Their `Hash` implementations should feed stable identity into
the hasher contract. A hash implementation belongs with the key type; the
mixing algorithm belongs with `Hasher`. Because maps and deterministic output
can change, land this with collision/distribution and fixpoint tests.

Private stable merge/permutation logic in `gen_emit` is a standard collections
candidate only after its ordering and allocation requirements are separated
from generator policy. `fmt_break.copy_of` is simply an owned-string
construction and should use the standard constructor rather than remain a
formatter helper.

### 7. Missing compiler/std primitives must replace fake local failures

Several workarounds pretend an invariant failure is allocation failure or
manufacture arithmetic underflow to trap:

- map access/settling maps impossible misses to `AllocError.OutOfMemory`;
- collection sorting returns `AllocError` although it does not allocate;
- AST arena stale access, `str.index`, and byte hex conversion manufacture
  unsigned underflow;
- `json_read.fine()` and `json_write.written()` exist to steer result-type
  inference;
- small `Vec.set` adapters in sema/generation translate an impossible bound
  failure into allocation failure.

Add a named `trap`/`unreachable` primitive with source-position behavior, then
make invariant-only operations return `()`. Separately fix contextual `Res`
inference so trivial `Ok(())` doors are not required. Error variants must name
recoverable failures, not act as an escape hatch for the compiler.

### 8. Sema contexts follow analysis lifetime, not file size

Good owners include:

- `CycleGraph` / `CycleSearch` for cycle construction and traversal;
- `Pats` / coverage state for one pattern-coverage walk;
- the existing ownership state for pin/drop operations that share its scope
  and mutation lifecycle;
- an `InstEdge` value where depth analysis repeatedly explodes one edge into
  adjacent parameters.

Do not move effect, operand, and spine analysis into `sema_type` merely because
they have a single caller. `sema_type` is already a broad consumer. A
single-consumer helper can still be a valid named decision, and merging it may
reverse dependencies or hide its invariant.

Likewise, do not add an inherent out-of-line extension mechanism merely to
make parser and lexer UFCS functions look like body-defined methods. Zen
already resolves principal-receiver calls such as `p.expr()` and `be.write()`.
The physical parse/lex files are valid splits by grammar subject. A true
`impl` remains with the type it implements; a lowering phase gets its own
phase type when it has a real lifecycle.

## Concrete cleanup register

### Safe mechanical or narrowly owned changes

- Remove unused parameters from `gen_c_expr.lower_literal`,
  `gen_c_main.write_void_exit`, context constructors that do not use the
  backend, and `gen_c_op.write_position`, after call-site confirmation.
- Confirm whether `gen_c_state.newline`, `sema_check.type_store`, and
  `zen_path.file_of` are uncalled; delete only after whole-tree and generated
  use checks.
- Remove the unused compatibility allocator from `TcpStream.read`; reconcile
  TLS read/allocation ownership rather than accepting two allocators.
- Replace LSP's planning-document MethodNotFound text.
- Hide low-level JSON, HPACK, CLI cursor, lexer cursor, and compiler-format ABI
  exports that have no consumer outside their subject.
- Replace pure copy helpers with standard constructors and owner methods.

### Changes that need a focused prototype

- A shared TCP/TLS byte stream. HTTP/1 and HTTP/2 duplicate the
  `Tcp(TcpStream) | Tls(TlsStream)` dispatch, but expose different protocol
  errors. Share only transport I/O; map `HttpError` and `H2Error` at their
  protocol boundaries.
- JSON's borrowed/owned consumer boundary. Allocation and feed-buffer lifetime
  tests must exist before replacing either parser.
- `CapabilityCall`, `TrySite`, and `JsonLower` records. Measure an entire route,
  not one signature.
- Project evaluation through the general compile-time evaluator.
- Actor `send` contract and compiler lowering. This changes public language
  ergonomics and must be specified with mailbox failure/lifecycle semantics.

### Changes explicitly rejected

- Do not give `Decoder` an ever-growing internal event vector.
- Do not rebuild whole-document JSON from today's allocated streaming events.
- Do not merge loop, range, array, and fold into a monolith.
- Do not combine every single-consumer sema module with `sema_type`.
- Do not add out-of-line inherent extension syntax to distribute one type
  across arbitrary implementation files.
- Do not erase HTTP/1 and HTTP/2 error identities behind a generic transport
  error at their public APIs.
- Do not replace the project executor until the general evaluator satisfies
  its effect and diagnostic contract.

## Comment audit

Comments were judged as part of ownership because a transcript often hides a
missing name or boundary. Keep only facts needed to maintain the finished
program:

- public contract, units, ownership, lifetime, and error policy;
- protocol, language, or ABI invariant;
- ordering requirement;
- why a plausible simpler implementation is incorrect today.

Remove or relocate:

- the conversation that produced a file;
- dated measurements, issue/test filenames, stage numbers, and plan rules;
- all-caps persuasion and repeated examples;
- rejected implementations that no longer constrain the code;
- future feature ledgers;
- paragraphs that paraphrase the next branch.

High-density review targets are `gen_c_inline`, `gen_c_op`, `gen_c_member`,
`fmt_decl`, `fmt_out`, `sema_apply`, `sema_bound`, `sema_cycle`, `sema_def`,
`env`, `parser`, `ast_node`, `text_fmt`, `json_read`, `collections_map`, and the
lex/parse implementation files. This is not a command to delete every header.
For example, HTTP framing limits and arena lifetimes are durable contracts;
shorten them to the invariant rather than erasing them.

The completion header should say what candidate sources exist and what an
incomplete buffer returns. It should not narrate the implementation journey or
carry a feature backlog. If locals or UFCS candidates are missing, track and
implement that as a feature; do not preserve the omission as architecture.

## Every-area disposition

This table is the compact judgement ledger. The generated signature inventory
is the file-by-file ledger.

| Area | Keep split | Consolidate or relocate |
| --- | --- | --- |
| AST | identity, span, node, arena, and query concerns | named trap; qualified-name owner methods; derive/reuse Eq/Hash |
| Parse | declaration, expression, type, pattern, member, statement grammar | comment cleanup and receiver-call consistency; no new extension syntax |
| Lex | cursor, token, literal, punctuation concerns | narrow public surface; remove construction transcripts |
| Collections | modules by owned collection type | truthful invariant failures; non-allocating sort; reusable ordered operations |
| Text | storage, number conversion, formatting concerns | one add/add_all vocabulary; integer/hex/segment owner methods; Sink output |
| JSON | syntax, storage, event API, encoding as distinct subjects | one syntax engine and one typed Sink encoder |
| Network | protocol framing/types remain separate | possible low-level TCP/TLS transport only; actor-owned streaming |
| Actor | dependency-light identity/core and environment-bound context | explicit address send/tell API and owned-message rules |
| Memory | pointer, allocator, and arena boundaries | trap primitive instead of arithmetic failure tricks |
| LSP | framing, session, URI/position, feature selection | workspace query below LSP; semantic renderer; typed JSON; request contexts |
| Sema | distinct analyses with named invariants | contexts for shared walk lifetimes; owner methods; no `sema_type` dumping ground |
| C generation | expression/call, member/impl, type/try decisions | phase records for relay chains; common iteration state; smaller runtime floors |
| Project/CLI | CLI parsing versus project planning versus toolchain execution | `build.zen` arguments, `ProjectBuild`, `Toolchain`, structured `RuntimeNeeds` |
| Formatter | parser-independent rendering and break/output concerns | owner methods and removal of build-history commentary |

## Execution order

1. Land and gate this inventory so architectural review always has complete
   signatures.
2. Add truthful `trap`/inference primitives and remove small local workarounds.
3. Design and test the JSON syntax-consumer boundary, then migrate read and
   stream before changing the public encoder.
4. Move workspace checking below LSP and convert one request route to named
   request/turn values.
5. Make typed Sink JSON cover the LSP shapes and remove manual punctuation.
6. Convert `gen_c_actor`, then one of inline/capability, to a complete phase
   owner and measure parameter/import reduction.
7. Introduce project build/toolchain/runtime-need values and make `zen build`
   and `zen run` execute the `build.zen` entry.
8. Apply comment cleanup with each structural lane, after names and boundaries
   improve. A repository-wide deletion pass before that would discard useful
   invariants along with transcripts.

For each lane, require focused tests, `make lint`, the self-hosted compiler,
and a fixpoint when module/signature changes cross the compiler boundary.
Update `GEN_C_SHAPE.md` measurements only after the implementation lands.
