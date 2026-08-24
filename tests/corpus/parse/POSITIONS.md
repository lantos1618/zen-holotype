# Exact spans for `positions.zen`

**These conventions are executed by
`tests/corpus/parse_zen/positions_are_exact/`.** That test embeds a source
string of its own -- a struct with two fields, a one-line enum, and a function
whose body is a call around a binary expression -- parses it, and asserts
thirty-two spans against the values counted by hand off those bytes. It is the
gate for the rules stated below: 1-based lines, 1-based *byte* columns,
half-open `start..end`, a span covering a node's children and its own
delimiters but not the separator after it or the trivia before it. Three of its
rows (`module`, `struct.body`, `fn.block`) start on one line and end on
another, and most of the rest end more than one column past their start, so a
tree carrying only a start point cannot pass it. `parser_spans.zen` in this
folder asserts the same conventions on a smaller file and from the struct/bind
side; this table remains the specification both were written from, and the rows
below still name `positions.zen`, which nothing checks.

`TESTING.md` calls position accuracy "the one everyone skips and the one that
decays fastest". This is that test, written out: every row is a node in
`positions.zen` and the exact span the parser must report for it.

**Conventions, because `DESIGN.md` states only that a node carries
`file:line:col` and never says what the position *is*:**

- Lines are 1-based. Columns are 1-based and counted in **bytes** (this file is
  ASCII, so bytes, characters and UTF-16 units agree here -- an LSP will have
  to convert, and that conversion is its own test).
- A span is `start..end`, **half-open**: `end` is one past the last character.
  So `Point` on line 4 occupies columns 1-5 and its span is `4:1..4:6`.
- A node's span **includes its children and its own delimiters** and excludes
  the separator that follows it: the field `x: i32` on line 5 is `5:5..5:11`
  and the comma at `5:11` belongs to the field list, not to the field.
- A *statement* span **includes its terminating `;`**; the expression inside it
  does not. `Ok(0);` is `22:5..22:11`; `Ok(0)` is `22:5..22:10`.
- Trivia is a span like any other, attached to the node that owns it. The three
  comment lines at the top of the file are the leading trivia of the `Point`
  declaration -- **not** of the module. See the gaps at the bottom.

**Four gaps `DESIGN.md` leaves open**, each of which changes a row here:

1. It says every node carries `file:line:col` -- a **point**, not a span. Every
   `end` column below assumes nodes carry an end position too. Without one,
   `fmt` cannot reprint and the LSP cannot select a node.
2. It never says whether a column counts bytes, codepoints, or UTF-16 units.
3. It never says whether a declaration's span includes its leading trivia. This
   table says **no**: the trivia is a separate span hanging off the node, which
   is what lets `fmt` move a declaration without moving its comment by accident.
4. It never says whether a statement's span includes the `;`. This table says
   **yes** -- otherwise deleting a statement leaves the semicolon behind.

## The drift, and which side won

This table was written against a `positions.zen` whose `Sign` declaration was
four lines of comma-separated variants:

```groovy
Sign =
    Neg,
    Zero,
    Pos
```

The file no longer says that. It says `Sign = Neg | Zero | Pos`, on one line,
and **the file is right**. `DESIGN.md` is the law and it is unambiguous --
"Sum types are written with `|`, always" -- and `grammar.js` R1 retired the
comma form explicitly, because it is what makes an alias and a one-variant enum
different declarations rather than the same three tokens. The comma spelling
survived only in `PLAN.md` 0.1's early sketch of the grammar.

So the source was treated as authoritative and **this table was recomputed
against it**, byte by byte. Five rows became four (an enum on one line has no
separate line per variant, and it gains a row for the absent leading bar), and
every row below the enum moved up by three lines. The columns were re-derived
from the file rather than shifted, so a stale column cannot have survived the
edit.

One row is new rather than moved: the **statement** containing the `.match`.
The old table asserted the match expression and never the statement around it,
so the `;` convention was stated in the prose and tested only at `Ok(0);`.

`tests/corpus/parse/parser_spans.zen` is this table made executable against the
parser, on a smaller file. Both exist on purpose: that one is a gate, this one
is the specification it was written from.

| # | node | kind | span | source |
|---|---|---|---|---|
| 1 | module (whole file) | Module | `1:1..24:1` | the whole file, trivia included |
| 2 | leading trivia of `Point` | Trivia | `1:1..3:66` | `// positions.zen -- t ...  line 4 is 4:1..4:6.` |
| 3 | `Point` declaration | Struct | `4:1..7:2` | `Point = {\n    x: i32,\n    y: i32,\n}` |
| 4 | `Point` name | Ident | `4:1..4:6` | `Point` |
| 5 | `Point` body | Body | `4:9..7:2` | `{\n    x: i32,\n    y: i32,\n}` |
| 6 | field `x: i32` | Field | `5:5..5:11` | `x: i32` |
| 7 | field name `x` | Ident | `5:5..5:6` | `x` |
| 8 | field type `i32` | Type | `5:8..5:11` | `i32` |
| 9 | field `y: i32` | Field | `6:5..6:11` | `y: i32` |
| 10 | field type `i32` (second) | Type | `6:8..6:11` | `i32` |
| 11 | `Sign` declaration | Enum | `9:1..9:24` | `Sign = Neg \| Zero \| Pos` |
| 12 | `Sign` name | Ident | `9:1..9:5` | `Sign` |
| 13 | `Sign` leading bar | Span? | **absent** | no bar leads, so this is an enum of three and not an alias |
| 14 | variant `Neg` | Variant | `9:8..9:11` | `Neg` |
| 15 | variant `Zero` | Variant | `9:14..9:18` | `Zero` |
| 16 | variant `Pos` (last) | Variant | `9:21..9:24` | `Pos` |
| 17 | `sign_of` declaration | Function | `11:1..16:2` | `sign_of = (n: i32) Si ... Sign.Pos,\n    });\n}` |
| 18 | `sign_of` name | Ident | `11:1..11:8` | `sign_of` |
| 19 | parameter list | Params | `11:11..11:19` | `(n: i32)` |
| 20 | parameter `n: i32` | Param | `11:12..11:18` | `n: i32` |
| 21 | parameter name `n` | Ident | `11:12..11:13` | `n` |
| 22 | parameter type `i32` | Type | `11:15..11:18` | `i32` |
| 23 | return type `Sign` | Type | `11:20..11:24` | `Sign` |
| 24 | `sign_of` body | Block | `11:25..16:2` | `{\n    (n == 0).match ... Sign.Pos,\n    });\n}` |
| 25 | `(n == 0).match({..})` | Match | `12:5..15:7` | `(n == 0).match({\n    ... => Sign.Pos,\n    })` |
| 26 | receiver `(n == 0)` | Paren | `12:5..12:13` | `(n == 0)` |
| 27 | `n == 0` | Binary | `12:6..12:12` | `n == 0` |
| 28 | operator `==` | Op | `12:8..12:10` | `==` |
| 29 | literal `0` | Int | `12:11..12:12` | `0` |
| 30 | method name `match` | Ident | `12:14..12:19` | `match` |
| 31 | arm list `{..}` | Arms | `12:20..15:6` | `{\n        true => Si ...  => Sign.Pos,\n    }` |
| 32 | arm `true => Sign.Zero` | Arm | `13:9..13:26` | `true => Sign.Zero` |
| 33 | pattern `true` | Pattern | `13:9..13:13` | `true` |
| 34 | arrow `=>` | Op | `13:14..13:16` | `=>` |
| 35 | arm body `Sign.Zero` | Access | `13:17..13:26` | `Sign.Zero` |
| 36 | arm `false => Sign.Pos` | Arm | `14:9..14:26` | `false => Sign.Pos` |
| 37 | arrow `=>` (second arm) | Op | `14:15..14:17` | `=>` |
| 38 | statement `(n == 0).match({..});` | Stmt | `12:5..15:8` | the whole statement, `;` included |
| 39 | `main` declaration | Function | `18:1..23:2` | `main = (env: Env) Res ... , d);\n    Ok(0);\n}` |
| 40 | parameter `env: Env` | Param | `18:9..18:17` | `env: Env` |
| 41 | return type `Res<i32, ArgError>` | Type | `18:19..18:37` | `Res<i32, ArgError>` |
| 42 | type argument `i32` | Type | `18:23..18:26` | `i32` |
| 43 | type argument `ArgError` | Type | `18:28..18:36` | `ArgError` |
| 44 | statement `p = Point(..);` | Stmt | `19:5..19:27` | `p = Point(x: 3, y: 4);` |
| 45 | call `Point(x: 3, y: 4)` | Call | `19:9..19:26` | `Point(x: 3, y: 4)` |
| 46 | callee `Point` | Name | `19:9..19:14` | `Point` |
| 47 | named argument `x: 3` | Arg | `19:15..19:19` | `x: 3` |
| 48 | argument value `3` | Int | `19:18..19:19` | `3` |
| 49 | `p.x * p.x + p.y * p.y` | Binary | `20:9..20:30` | `p.x * p.x + p.y * p.y` |
| 50 | its left operand `p.x * p.x` | Binary | `20:9..20:18` | `p.x * p.x` |
| 51 | operator `+` | Op | `20:19..20:20` | `+` |
| 52 | field access `p.x` | Access | `20:9..20:12` | `p.x` |
| 53 | field name `y` (last) | Ident | `20:29..20:30` | `y` |
| 54 | call `println("{}", d)` | Call | `21:5..21:21` | `println("{}", d)` |
| 55 | string literal `"{}"` | Str | `21:13..21:17` | `"{}"` |
| 56 | `Ok(0)` | Call | `22:5..22:10` | `Ok(0)` |
| 57 | statement `Ok(0);` | Stmt | `22:5..22:11` | `Ok(0);` |

## How this file is checked

The spans above were computed from the bytes of `positions.zen` and every one
was verified by extracting `start..end` from the source and comparing it to the
node it names. A harness must do the same in reverse: parse `positions.zen`,
walk to each node, and compare its recorded span to the table. A row that
cannot be located by name is a table that has drifted, and drift here is
exactly the failure `TESTING.md` describes -- a correct diagnostic pointing at
the wrong token.

That harness does not exist yet, and until it does this file is checked by
hand, which is why it drifted once already. What DOES run is
`parser_spans.zen`, which asserts the same conventions on a file small enough
to build a token stream for by hand. Point the harness at this table the day
`src/lex/` can turn `positions.zen` into tokens, and delete this paragraph.

`positions.zen` is also an ordinary corpus program: it prints `25`.
