# Style

How to write Zen and how to organise this tree. `DESIGN.md` specifies the
language; this guide describes code that is easy to locate, read, and change.

The formatter owns layout. The grammar owns syntax. This guide owns the
judgement the compiler cannot make: where behavior belongs, what deserves a
type or module, and which comments help the next reader.

## The ownership question

Before adding a function, ask:

> What value, state, or domain fact is this operation about?

Put the operation with that owner.

1. If it is intrinsic behavior of an existing type, make it a method in the
   type's module.
2. If several functions repeatedly carry the same state, name that state with
   a small record and make the functions methods on it.
3. If it is a reusable operation with no dominant receiver, keep it free in
   the lowest module that can own it without reversing dependencies.
4. If it only coordinates two existing owners, keep the orchestration at their
   boundary. Do not move either domain into the other.

The repeated-parameter smell is stronger than line count:

```zen
// no: one unnamed completion context repeated across the file
offer_global(checker, alloc, module, name, prefix, seen, out)
table_names(checker, alloc, module, table, prefix, seen, out)

// yes: the state has a name and its operations have an owner
offers.offer_global(module, name)
offers.table_names(module, table)
```

A record is not a bag for shortening signatures. Its fields must be created
together, share a lifetime, and describe one concept. Values that vary per
operation remain method parameters.

### Methods, context records, and free functions

Use a method when the operation is a fact about its receiver:

```zen
text.write_usize(n)
checker.type_of(expr)
backend.write_dest(dest, value)
```

Use a context record when a phase has several stable inputs or accumulators:

```zen
Offers = {
    completion : Completion,
    prefix     : str,
    seen       :: Map<str, bool>,
    out        :: Vec<Item>,

    offer = (self :: @Self, item: Item) Res<(), AllocError> { /* ... */ }
}
```

Keep a function free when it is a constructor, a symmetric operation, a pure
conversion between peer domains, or a helper with no natural state owner.
Do not invent a one-method record merely to avoid a free function.

Calling style follows ownership. If the first parameter is the natural
receiver, call the function on it. A source file full of `write(backend, ...)`
usually contains methods someone has not moved to their owner yet.

An `impl` stays with its target type. Traits sit below the types satisfying
them; putting an impl with the trait reverses that dependency.

## Where code lives

A module contains what is about its subject and nothing else.

Apply these tests in order:

### The stranger test

Write a one-line description without using the current module's name. If it
still describes the function completely, the function probably belongs
somewhere more general.

```text
"writes an integer in hexadecimal"       -> std.text
"finds the access expression at a cursor" -> lsp completion/navigation
```

### The second-caller test

When a private workaround gains a caller in another module, stop copying or
re-exporting it. Move the reusable part to its real owner and migrate both
callers.

The second caller is also a chance to reject false generality. If moving the
whole helper would pull parser, compiler, or protocol state into `std`, split
the general operation from the domain-specific policy.

### The direction test

Dependencies point from specialised code toward general code:

```text
driver -> compiler phase -> AST/text/collections -> memory/core
LSP    -> compiler queries and JSON transport
```

Lower layers do not import their consumers. If the proposed move creates an
upward import, either the owner is wrong or the function contains two jobs.

Every import is a claimed dependency. Import only names the file uses. A
folder root may re-export names intentionally; ordinary modules should not
carry forwarding imports for convenience.

## When to split a file

A file is too large when it has more than one subject. Line count only finds
candidates.

`make cap` prints review notes above 500 and 800 lines. Neither threshold
fails the build. A cohesive parser, state machine, or dispatch table may be
longer than 800 lines; splitting it into `part1` and `part2` would make it
harder to understand.

Split only when the proposed pieces pass all of these checks:

- each piece has a specific name and invariant;
- each has a reason to change independently;
- dependencies between them point in one direction;
- a consumer can reasonably need one without importing the other;
- the split removes state forwarding rather than adding it;
- neither result is named `helpers`, `utils`, `common`, `misc`, or `part2`.

Do not split merely because a gate reported a number. First name repeated
state and move methods to it; the real module boundaries are usually visible
after ownership is correct.

Folders own public surfaces. Sibling files that form one subject live under a
folder with a root module that deliberately re-exports its API. Prefixes exist
to prevent ambiguous filenames, not as a tax on every source file.

```text
src/std/parse/parse.zen         folder surface
src/std/parse/parse_expr.zen    expression parsing
src/std/parse/parse_decl.zen    declaration parsing
```

Forwarding-only modules and sibling modules that import each other are signs
that the boundary is false.

## Signatures

A signature should answer whether the operation allocates, mutates, fails, or
escapes.

```zen
add* = (self :: @Self, value: T) Res<(), AllocError>
len* = (self: @Self) usize
map* = <T, U>(items: Vec<T>, alloc: Alloc, body: (item: T) U)
       Res<Vec<U>, AllocError>
```

- No `Alloc` parameter means no allocation.
- `self :: @Self` means the method writes the receiver's own bytes.
- `self: @Self` may still act through capabilities or referenced state.
- Every parameter has a name and type, including parameters in function types.
- Use `Res` for a failure the caller can act on. Trap only for violated program
  invariants.
- If several adjacent parameters are always produced and consumed together,
  consider whether they are one domain value.

Avoid boolean parameters that switch between different operations. Prefer an
enum when the modes form one closed decision, or separate methods when callers
are asking different questions.

## Naming and code shape

- Types are nouns, functions are verbs, and predicates read as questions.
- Say what a value is: `view`, `add`, `grow`, `consume`; avoid `get_*` and
  `do_*`.
- Use `add` for one value and `add_all` for many. Use `push` or `insert` only
  when position is part of the contract.
- Avoid abbreviations that are not established words in this tree. `alloc`,
  `len`, `ptr`, and `env` are established; `blk`, `nd`, and `tp` are not.
- Prefix by role (`src_line`, `dst_line`), not by type or numbering.
- Rename before adding a comment that explains a name.

Method chains read left to right. Prefer `value.convert().write(out)` to nested
calls when the operations have natural receivers.

### Control flow

Use `.then` when a boolean has work on its true side and deliberately does
nothing on its false side:

```zen
(width > limit).then(() { line.break_at(at).try() });
```

Keep `.match` when both outcomes produce values or perform distinct work. Do
not add an empty arm merely to satisfy exhaustiveness, and do not turn a real
two-way decision into `.then(...).match(...)`.

Put refusal and failure at the edge of a function. Use `.try()` to propagate a
failure, `ensure` for a boolean precondition, and a breakable one-shot `loop`
when several guards choose an early value. Name the loop result when inference
needs its type. The successful path should not be buried under nested matches
whose other arms only stop the operation.

### Actors and streams

An actor owns asynchronous state behind a typed mailbox. Introduce one when a
component needs an independent lifetime, serialized turns, delivery refusal,
or backpressure. The message type is the public boundary; behavior belongs on
the actor and receives its turn through `Context`.

Do not use an actor as a wrapper around synchronous computation. `Sink` is a
synchronous byte destination, not an actor: use it when the producer and
consumer share one call. Use an actor receiver when chunks must cross an
asynchronous ownership boundary, as in a streamed HTTP response.

Use the strongest loop operation that states the question: `find`, `all`,
`filter`, or `map` instead of a `.loop` with a manual accumulator or break.

Three or more equality checks against literals are a membership question.
Use `is_in` where the type supports it. Ranges and distinct predicates remain
written as their actual questions.

Use character literals instead of numeric byte spellings. Shared protocol and
runtime constants belong with the protocol or runtime type, not at each call
site.

## Comments

Comments are for a reader maintaining the finished code.

Keep comments that explain:

- a public contract;
- a non-obvious invariant or ownership rule;
- a protocol or ABI requirement;
- why an apparently simpler change would be incorrect;
- a failure policy that callers must preserve.

Remove comments that record:

- the conversation that produced the code;
- estimates, chronology, issue archaeology, or previous implementations;
- rejected alternatives that no longer constrain the implementation;
- a paraphrase of the next statement;
- unfinished-feature ledgers better kept in the plan or issue tracker;
- rhetorical headings or emphasis used to persuade during construction.

Use a newcomer's test: after reading the comment, can someone understand or
safely change the current code? If it only explains why the author once felt
uncertain, remove it.

A paragraph often indicates a missing name or function boundary. Improve the
code first, then keep only the invariant the code cannot express.

## Tests and gates

- Name tests as behaviors, without a redundant `test_` prefix.
- Keep one behavior per test.
- Add a corpus program for every diagnostic and runtime trap.
- Before trusting a new gate, break its target deliberately and verify the gate
  fails.
- A check that scanned no files is a harness failure, not a clean result.
- For pipelines, preserve the producer's exit status. The repository Makefile
  uses `bash -o pipefail`; ad-hoc commands must do the same or record status
  before displaying truncated output.

The formatter is the authority on whitespace, wrapping, alignment, trailing
commas, and comment placement. Run it instead of maintaining a second layout
specification here.

## Review checklist

For every new or moved function, ask:

1. What is it about?
2. Is there already a type that owns that behavior?
3. Is a repeated parameter bundle hiding a phase or accumulator?
4. Does another module already implement the same workaround?
5. Is the dependency direction still downward?
6. Does an export serve another subject, or only convenience?
7. Is a one-sided boolean still written as a two-arm match?
8. Can failure or refusal leave before the successful path is nested?
9. Does an actor own a real mailbox and lifecycle, or only add indirection?
7. Would a proposed file split remove coupling or merely relocate it?
8. Does each comment help a new maintainer understand the current contract?

Do this while writing the function. A later cleanup has less context and more
callers to migrate.
