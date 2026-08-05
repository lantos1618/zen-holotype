# Exact spans for `positions.zen`

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
  does not. `Ok(0);` is `25:5..25:11`; `Ok(0)` is `25:5..25:10`.
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

| # | node | kind | span | source |
|---|---|---|---|---|
| 1 | module (whole file) | Module | `1:1..26:2` | `// positions.zen -- t ... , d);\n    Ok(0);\n}` |
| 2 | leading trivia of `Point` | Trivia | `1:1..3:66` | `// positions.zen -- t ...  line 4 is 4:1..4:6.` |
| 3 | `Point` declaration | Struct | `4:1..7:2` | `Point = {\n    x: i32,\n    y: i32,\n}` |
| 4 | `Point` name | Ident | `4:1..4:6` | `Point` |
| 5 | `Point` body | Block | `4:9..7:2` | `{\n    x: i32,\n    y: i32,\n}` |
| 6 | field `x: i32` | Field | `5:5..5:11` | `x: i32` |
| 7 | field name `x` | Ident | `5:5..5:6` | `x` |
| 8 | field type `i32` | Type | `5:8..5:11` | `i32` |
| 9 | field `y: i32` | Field | `6:5..6:11` | `y: i32` |
| 10 | field type `i32` (second) | Type | `6:8..6:11` | `i32` |
| 11 | `Sign` declaration | Enum | `9:1..12:8` | `Sign =\n    Neg,\n    Zero,\n    Pos` |
| 12 | `Sign` name | Ident | `9:1..9:5` | `Sign` |
| 13 | variant `Neg` | Variant | `10:5..10:8` | `Neg` |
| 14 | variant `Zero` | Variant | `11:5..11:9` | `Zero` |
| 15 | variant `Pos` (last, no comma) | Variant | `12:5..12:8` | `Pos` |
| 16 | `sign_of` declaration | Function | `14:1..19:2` | `sign_of = (n: i32) Si ... Sign.Pos,\n    })\n}` |
| 17 | `sign_of` name | Ident | `14:1..14:8` | `sign_of` |
| 18 | parameter list | Params | `14:11..14:19` | `(n: i32)` |
| 19 | parameter `n: i32` | Param | `14:12..14:18` | `n: i32` |
| 20 | parameter name `n` | Ident | `14:12..14:13` | `n` |
| 21 | parameter type `i32` | Type | `14:15..14:18` | `i32` |
| 22 | return type `Sign` | Type | `14:20..14:24` | `Sign` |
| 23 | `sign_of` body | Block | `14:25..19:2` | `{\n    (n == 0).match ... Sign.Pos,\n    })\n}` |
| 24 | `(n == 0).match({..})` | Call | `15:5..18:7` | `(n == 0).match({\n    ... => Sign.Pos,\n    })` |
| 25 | receiver `(n == 0)` | Paren | `15:5..15:13` | `(n == 0)` |
| 26 | `n == 0` | Binary | `15:6..15:12` | `n == 0` |
| 27 | operator `==` | Op | `15:8..15:10` | `==` |
| 28 | literal `0` | Int | `15:11..15:12` | `0` |
| 29 | method name `match` | Ident | `15:14..15:19` | `match` |
| 30 | arm list `{..}` | Arms | `15:20..18:6` | `{\n        true => Si ...  => Sign.Pos,\n    }` |
| 31 | arm `true => Sign.Zero` | Arm | `16:9..16:26` | `true => Sign.Zero` |
| 32 | pattern `true` | Pattern | `16:9..16:13` | `true` |
| 33 | arrow `=>` | Op | `16:14..16:16` | `=>` |
| 34 | arm body `Sign.Zero` | Path | `16:17..16:26` | `Sign.Zero` |
| 35 | arm `false => Sign.Pos` | Arm | `17:9..17:26` | `false => Sign.Pos` |
| 36 | arrow `=>` (second arm) | Op | `17:15..17:17` | `=>` |
| 37 | `main` declaration | Function | `21:1..26:2` | `main = (env: Env) Res ... , d);\n    Ok(0);\n}` |
| 38 | parameter `env: Env` | Param | `21:9..21:17` | `env: Env` |
| 39 | return type `Res<i32, ArgError>` | Type | `21:19..21:37` | `Res<i32, ArgError>` |
| 40 | type argument `i32` | Type | `21:23..21:26` | `i32` |
| 41 | type argument `ArgError` | Type | `21:28..21:36` | `ArgError` |
| 42 | statement `p = Point(..);` | Bind | `22:5..22:27` | `p = Point(x: 3, y: 4);` |
| 43 | call `Point(x: 3, y: 4)` | Call | `22:9..22:26` | `Point(x: 3, y: 4)` |
| 44 | callee `Point` | Ident | `22:9..22:14` | `Point` |
| 45 | named argument `x: 3` | Arg | `22:15..22:19` | `x: 3` |
| 46 | argument value `3` | Int | `22:18..22:19` | `3` |
| 47 | `p.x * p.x + p.y * p.y` | Binary | `23:9..23:30` | `p.x * p.x + p.y * p.y` |
| 48 | its left operand `p.x * p.x` | Binary | `23:9..23:18` | `p.x * p.x` |
| 49 | operator `+` | Op | `23:19..23:20` | `+` |
| 50 | field access `p.x` | Field access | `23:9..23:12` | `p.x` |
| 51 | field name `y` (last) | Ident | `23:29..23:30` | `y` |
| 52 | call `println("{}", d)` | Call | `24:5..24:21` | `println("{}", d)` |
| 53 | string literal `"{}"` | Str | `24:13..24:17` | `"{}"` |
| 54 | `Ok(0)` | Call | `25:5..25:10` | `Ok(0)` |
| 55 | statement `Ok(0);` | Bind | `25:5..25:11` | `Ok(0);` |

## How this file is checked

There is no compiler yet, so the spans above were computed from the bytes of
`positions.zen` and every one was verified by extracting `start..end` from the
source and comparing it to the node it names. Once a parser exists, the harness
must do the same in reverse: parse `positions.zen`, walk to each node, and
compare its recorded span to the table. A row that cannot be located by name is
a table that has drifted, and drift here is exactly the failure `TESTING.md`
describes -- a correct diagnostic pointing at the wrong token.

`positions.zen` is also an ordinary corpus program: it prints `25`.
