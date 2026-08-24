# `std/json` — the derive, sketched (stage 5)

Illustrative, not compilable: `@meta` is refused in sema (M0, `src/sema/sema_meta.zen`), and `offset_of`/`size_of` are comptime answers the stage-5 expander has to expose. The design argument: `gen_c` should emit a static field table per type plus ONE shared interpreter, not a monomorphized parser per type (the jsony shape). A JSON derive is a LIBRARY, written against `std.ast`'s own node types (DESIGN.md:457, "one AST, three consumers"), and the per-type output is DATA.

```zen
// std/json — the derive, sketched. The design argument: gen_c should emit a
// static field table per type plus ONE shared interpreter, not a
// monomorphized parser per type (the jsony shape). This file is the SOURCE
// side of that; the emitted-C side follows from Schema being plain data.
//
// It does not compile today, for two named reasons, and neither is an accident:
//
//   1. `@meta` is refused in sema (src/sema/sema_meta.zen, M0; design_meta.md).
//      Stage 5 owns the expander.
//   2. `Field.offset` is layout knowledge. Only the compiler knows where a
//      member lands, so the offset is a comptime answer `@meta` must be able
//      to give — everything else here is ordinary Zen.
//
// What this file asserts: a JSON derive is a LIBRARY, written against
// std.ast's own node types (DESIGN.md:457, "one AST, three consumers"), and
// the per-type output is DATA. The interpreter is written once, below.

Res*, Ok*, Err* = std.core.result
Vec* = std.collections.vec
Alloc*, AllocError* = std.mem
Ptr*, null_ptr* = std.mem

// --------------------------------------------------------------- the error

// An ordinary enum with payloads; the union in from_json's signature is the
// language's error-set merge, not a mechanism of this library's.
JsonError* = Expected(str)      // wanted one token, found something else
           | Unterminated(usize) // a string or structure that never closed
           | Trailing(usize)     // non-whitespace after the value

// ---------------------------------------------------------------- the data

Kind = Bool | U64 | I64 | F64 | Str | Struct | Vec_ | Opt_

Field* = {
    name*:   str,        // as written, or the remapped key
    offset*: usize,      // <- the comptime answer; see note 2 above
    type*:   Ptr<Schema>,
}

Schema* = {
    kind*:    Kind,
    size*:    usize,
    fields*:  Vec<Field>,          // Struct only; empty otherwise
    inner*:   Res<Ptr<Schema>>,    // Vec_/Opt_ only
    post*:    Res<Ptr<(Ptr<u8>) ()>>,  // a written post-hook, or None
}

// -------------------------------------------------------------- the cursor

Parser* = {
    s:  str,
    i :: usize,

    space* = (self :: @Self) () {
        loop((h) {
            (self.i >= self.s.len).then({ h.break(); });
            c = self.s[self.i];
            (c == ' ' or c == '\n' or c == '\t' or c == '\r')
                .match({
                    true  => { self.i = self.i + 1; },
                    false => { h.break(); },
                });
        });
    }

    expect* = (self :: @Self, c: u8) Res<(), JsonError> {
        self.space();
        (self.i < self.s.len and self.s[self.i] == c).match({
            true  => { self.i = self.i + 1; Ok(()) },
            false => Err(JsonError.Expected("delimiter")),
        })
    }

    at_end* = (self :: @Self) bool {
        self.space();
        self.i == self.s.len
    }

    // The one leaf that earns real code: a string, with escapes. Two paths,
    // jsony's own trick — no escape means no copy, the str borrows the
    // source slice.
    string* = (self :: @Self, alloc: Alloc) Res<str, JsonError | AllocError> {
        self.expect('"').try();
        start = self.i;
        simple ::= true;
        closed ::= false;
        loop((h) {
            (self.i >= self.s.len).then({ h.break(); });
            self.s[self.i].match({
                '"'  => { closed = true; h.break(); },
                '\\' => { simple = false; self.i = self.i + 2; },
                _    => { self.i = self.i + 1; },
            });
        });
        closed.match({
            false => Err(JsonError.Unterminated(start)),
            true  => {
                raw = self.s[start ..< self.i];
                self.i = self.i + 1;                    // the closing quote
                simple.match({
                    true  => Ok(raw),
                    false => self.unescape(raw, alloc), // the slow path, below
                })
            },
        })
    }

    unescape* = (self: @Self, raw: str, alloc: Alloc) Res<str, JsonError | AllocError> {
        out ::= Vec<u8>(alloc);
        j ::= 0;
        loop((h) {
            (j >= raw.len).then({ h.break(); });
            (raw[j] == '\\').match({
                false => { out.add(raw[j]).try(); j = j + 1; },
                true  => {
                    // \" \\ \/ \b \f \n \r \t and \uXXXX — the full table is
                    // jsony's; the shape is what matters here
                    j = j + 1;
                    out.add(unescape_one(raw, j)).try();
                    j = j + 1;
                },
            });
        });
        Ok(out.as_str())
    }

    // Skip a value without keeping it — the law for fields the type does
    // not declare. Recursive, and allocates nothing.
    skip* = (self :: @Self) Res<(), JsonError> {
        self.space();
        (self.i >= self.s.len).match({
            true  => Err(JsonError.Expected("value")),
            false => self.s[self.i].match({
                '"' => { self.string_skip().try(); Ok(()) },
                '{' => self.skip_block('{', '}'),
                '[' => self.skip_block('[', ']'),
                _   => {
                    loop((h) {
                        (self.i >= self.s.len).then({ h.break(); });
                        ",}] \n\t\r".contains(self.s[self.i])
                            .match({
                                true  => { h.break(); },
                                false => { self.i = self.i + 1; },
                            });
                    });
                    Ok(())
                },
            }),
        })
    }
}

// ------------------------------------------------------- once per program

// The interpreter is ordinary Zen and ordinary gen_c input — nothing in it
// is generic, so it lowers to exactly ONE value-walker in the C, no matter
// how many types the program deserializes. Each arm's value is the Res;
// `.try()` inside an arm exits the arm, and the match is the function's
// tail, so an error travels without a check written at every step.
parse_value = (p :: Parser, alloc: Alloc, sc: Ptr<Schema>, out: Ptr<u8>)
        Res<(), JsonError | AllocError> {
    s = sc.read(0);
    p.space();
    s.kind.match({
        Bool => {
            v = p.word_bool().try();
            out.to<bool>().write(0, v);
            Ok(())
        },
        U64 => {
            v = p.unsigned().try();
            out.to<u64>().write(0, v);
            Ok(())
        },
        I64  => p.signed_into(out),
        F64  => p.float_into(out),   // the scan is one leaf; specialization
                                     // lives here and nowhere else
        Str  => {
            v = p.string(alloc).try();
            out.to<str>().write(0, v);
            Ok(())
        },
        Struct => {
            p.expect('{').try();
            loop((h) {
                p.space();
                (p.i < p.s.len and p.s[p.i] == '}').then({
                    p.i = p.i + 1;
                    h.break();
                });
                key = p.string(alloc).try();
                p.expect(':').try();
                find_field(s, key).match({
                    // out.offset(f.offset) is byte arithmetic on a Ptr<u8> —
                    // the offset the compiler answered at comptime, used once
                    Ok(f)   => parse_value(p, alloc, f.type, out.offset(f.offset)).try(),
                    None    => p.skip().try(),   // extra fields are ignored
                });
                p.space();
                (p.i < p.s.len and p.s[p.i] == ',').match({
                    true  => { p.i = p.i + 1; },
                    false => { h.break(); },
                });
            });
            p.expect('}').try();
            s.post.match({
                Ok(post) => post(out),
                None     => {},
            });
            Ok(())
        },
        Vec_ => {
            // The arm touches Vec's layout — data/len/capacity — by name.
            // That is not magic: Vec is an ordinary struct, and its schema
            // is how the derive KNOWS those offsets. One walker, every Vec.
            p.expect('[').try();
            elem = s.inner.try();
            loop((h) {
                p.space();
                (p.i < p.s.len and p.s[p.i] == ']').then({
                    p.i = p.i + 1;
                    h.break();
                });
                slot = vec_grow(out, elem.size, alloc).try();
                parse_value(p, alloc, elem, slot).try();
                p.space();
                (p.i < p.s.len and p.s[p.i] == ',').match({
                    true  => { p.i = p.i + 1; },
                    false => { h.break(); },
                });
            });
            p.expect(']').try();
            Ok(())
        },
        Opt_ => {
            p.word_null().match({
                // None is the null Ptr; the C layout of Res<Ptr<_>> here is
                // one word, which is WHY the schema can write it blind
                true  => { out.to<usize>().write(0, 0); Ok(()) },
                false => {
                    cell = alloc.create_raw(s.inner.try().size).try();
                    parse_value(p, alloc, s.inner.try(), cell).try();
                    out.to<Ptr<u8>>().write(0, cell);
                    Ok(())
                },
            })
        },
    })
}

// ------------------------------------------------------------ the derive

// This is the whole trick: @meta hands back the compiler's own Struct value
// (the same node DumpAst walks and gen_c consumes), and the derive walks
// Struct.members — one ordered Member list, names as Idents — and builds a
// Schema constant. Per type, the emitted C is a field table, not a parser.
//
// NB: @meta is NOT a type and not an annotation. It is one of the three
// entries in the compiler's @ namespace (DESIGN.md:463): @meta(n) takes a
// VALUE and returns its node; @meta(name: T) is the typed form. So the
// type parameter in from_json is an ordinary <T>, and schema_of takes the
// Struct NODE — an ordinary std.ast value — not anything @-flavoured.
schema_of = (s: Struct, alloc: Alloc) Schema {
    fields ::= Vec<Field>(alloc);      // comptime vec, becomes a static C array
    for m in s.members {
        // Members that are not fields — methods, constants — are not data
        // and do not serialize. skipHook is the derive's filter, not an
        // overload set.
        m.kind.match({
            Field(f)  => {
                fields.push(Field(
                    name:   json_name(f.name.text),  // case mapping, comptime
                    offset: offset_of(f),     // layout's answer; comptime only
                    type:   schema_of(@meta(f.type), alloc),  // recursion over
                )).try();                     // types, and types are acyclic
            },
            Const(_)    => {},
            Function(_) => {},
        });
    }
    Schema(kind: Kind.Struct, size: size_of(s), fields: fields,
           inner: None, post: None)
}

// Generics compose by pointer: schema_of(Vec<Point>'s node) is one Schema
// whose inner points at Point's. Vec<A> and Vec<B> share the vec walker —
// no per-instantiation parser, which was the whole bloat argument.

// ------------------------------------------------------------- the surface

// A bare type parameter, the same spelling as Env.args (DESIGN.md:710):
// the caller writes from_json<Config>(alloc, s), and the typed form of
// @meta hands the body Config's Struct node.
from_json = <T>(alloc: Alloc, s: str) Res<T, JsonError | AllocError> {
    schema = comptime schema_of(@meta(t: T), alloc);  // folds to a static
                                                      // const in the C
    cell = alloc.create<T>().try();     // one zeroed T; AllocError rides the
                                        // union in the signature, no mapping
    p ::= Parser(s: s, i: 0);
    parse_value(p, alloc, schema_ptr(schema), cell.to<u8>()).try();
    p.at_end().match({
        true  => Ok(cell.read(0)),
        false => Err(JsonError.Trailing(p.i)),
    })
}

// -------------------------------------------------------- elided, on purpose

// Helpers named above but not shown, because each is a byte loop of the
// shape already written and none carries a design decision:
//
//   word_bool / word_null / unsigned / signed_into / float_into
//       the scalar leaves — jsony's char-by-char scans, written once each
//   unescape_one    the \" \\ \/ \b \f \n \r \t \uXXXX table row
//   skip_block      the bracket-matched half of skip, for '{' and '['
//   string_skip     string's fast path with the copy dropped
//   find_field      the linear name scan over s.fields
//   vec_grow        data/len/capacity, one element's worth, through alloc
//   json_name       the comptime case mapping (snake_case or identity)
//   offset_of / size_of / schema_ptr
//       the three comptime answers stage 5 must expose — offset_of and
//       size_of are layout's, schema_ptr is "address of a comptime const"
//
// If one of these turns out to hide a decision, it stops being elided.
```
