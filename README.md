# Zen

A systems language: Pony's actors and capabilities, Zig's explicitness, and one rule for everything else.

```groovy
Shape = Circle(Circle) | Rect(Rect) | Unit

Shape.impl(Display, {
    toString ::= (self: @Self, out :: Sink) Res<(), WriteError> {
        self.match({
            Circle(c) => out.fmt("circle: {}", c.radius),
            Rect(r)   => out.fmt("rect: {} {}", r.width, r.height),
            Unit      => out.fmt("unit"),
        })
    }
})

main = (env: Env) Res<i32, Error> {
    alloc ::= env.mem.alloc();          // page authority comes from Env
    shapes ::= alloc.Vec<Shape>();      // allocation is in the signature
    shapes.add(Shape.Unit).try();       // failure is a value
    Ok(0);                              // the arena frees everything here
}
```

## What is unusual about it

- **Control flow is `.match`, a method.** No `if`, no ternary, no `?`. Match is always exhaustive, in every position, so a missing case is never ambiguous between deliberate and forgotten. `bool.then` covers the one-sided case out loud.
- **There are no traits, only structs.** A struct whose fields happen to be functions, used as a bound, is what other languages call a trait. `A.impl(B, {..})` supplies a value for every field `B` declares. One rule, no second mechanism.
- **The signature answers the question.** Does it allocate, does it mutate, can it fail, does it escape — read the first line. No `Alloc` parameter means no allocation, anywhere, including the standard library.
- **All authority flows from one `Env`.** No ambient io, net, threads, or page allocation.
- **`Res` is for failure a caller can act on; a trap is for a bug.** Overflow and out-of-bounds abort with a position rather than becoming values nobody checks.
- **Data races are compile errors**, not deep copies. Only deeply-immutable or uniquely-owned values cross an actor boundary, and the handoff is spelled `consume`.

## Streaming JSON

`std.json.Decoder` accepts any `Range<u8>`, so the same call handles borrowed
text, an HTTP/2 body chunk, or another byte container. Chunk boundaries do not
have to align with JSON tokens. Text, keys, and number events own their bytes;
call `finish` once when the document ends.

```groovy
JsonEvent, JsonFault = std.json

decode = (alloc: Alloc, first: str, second: str)
         Res<Vec<JsonEvent>, JsonFault> {
    decoder ::= alloc.Decoder().try();
    events  ::= alloc.Vec<JsonEvent>();
    decoder.feed(first, events).try();
    decoder.feed(second, events).try();
    decoder.finish(events).try();
    Ok(events)
}
```

A `Sink` is the synchronous output-side byte capability. Actors are the
asynchronous ownership boundary; an actor receiving `H2Chunk` can feed that
owned chunk directly to its decoder without copying it through a `String`.

## Building

```sh
make build      # needs only a C compiler: the seed is checked-in C
make test       # the corpus and must-fail suites
make fixpoint   # zen compiles itself to byte-identical C
```

`make help` lists the rest.

## The documents

Read them in this order. They are the specification, not commentary on it.

| | |
|---|---|
| [docs/DESIGN.md](docs/DESIGN.md) | what the language is, and the law forcing each decision |
| [docs/LANGUAGE_MAP.md](docs/LANGUAGE_MAP.md) | short map from syntax through sema, codegen, runtime, and tooling |
| [docs/PLAN.md](docs/PLAN.md) | stages 0–5, each ending at a gate that can go red |
| [docs/STYLE.md](docs/STYLE.md) | naming, code shape, and where a helper belongs |
| [docs/TESTING.md](docs/TESTING.md) | the bug classes each phase reliably has, written first |

`DESIGN.md` is binding. Where the others disagree with it, they are the bug — and where it is silent, its "Still open" section says so rather than leaving you to guess.
Feature notes, generated inventories, and review artifacts are indexed in
[docs/README.md](docs/README.md).

## Layout

```
grammar/     tree-sitter grammar. written before any other code.
seed/        the checked-in generated C. regenerate, THEN commit.
src/         the real compiler and the standard library, in Zen
example/     a project that uses the language
tests/       corpus, must-fail cases, and Zen gate programs
```

## Status

Stage 4. The standard library, the self-hosted compiler, the formatter, and the ownership checker exist, and `make fixpoint` proves the compiler compiles itself to byte-identical C. The stage in progress is the LSP — hover, lexical semantic tokens, and diagnostics answer; everything else is refused by name. 4 is the grade the tree is measured against, not a claim that stages 1–4 are finished; `STAGE` at the repo root says what is still open. `docs/PLAN.md` is the map, and every stage in it ends at a command that exits non-zero when the stage is wrong.
