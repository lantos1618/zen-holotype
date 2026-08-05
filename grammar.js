/// <reference types="tree-sitter-cli/dsl" />
// @ts-check

// ---------------------------------------------------------------------------
// tree-sitter grammar for Zen.
//
// Written from docs/DESIGN.md (the law) + docs/PLAN.md 0.1, BEFORE any other
// code, per PLAN.md. Every construct here traces to a code block in DESIGN.md;
// nothing is invented. Where DESIGN.md is silent the grammar takes the
// minimum reading that parses and the choice is recorded below AND in the
// report that ships with this file. A parser that quietly picks a reading is
// how a language ends up with no specification (STYLE.md).
//
// NOT YET RUN THROUGH `tree-sitter generate` (instructed not to). The
// `conflicts` list below is derived by reading the item sets, not by running
// the generator; expect one iteration of "add/remove a conflict the generator
// names" before it builds.
//
// ---------------------------------------------------------------------------
// DECISIONS DESIGN.md DOES NOT STATE (all reported; each is a doc bug)
// ---------------------------------------------------------------------------
//
// D1. Operator precedence and associativity are nowhere in DESIGN.md. Taken as
//     C-like, all binary operators left-associative:
//       || < && < (== !=) < (< > <= >=) < (+ - +% -%) < (* / % *%) < unary
//     `+%` sits at exactly the precedence of `+`, `*%` of `*` — DESIGN.md
//     calls them "the wrapping forms", so they are the same operation with a
//     different overflow rule, not a different binding strength.
//
// D2. `consume e` binds LOOSER than every other prefix operator and looser
//     than binary operators (`prec.right(PREC.consume)`), so `consume f` and
//     `consume buf` (the only two forms in DESIGN.md) parse, and
//     `consume a.b` consumes the field rather than the base. DESIGN.md shows
//     `consume` only on a bare name.
//
// D3. `|` in a type is left-associative and binds tighter than nothing else —
//     it only ever appears at the top of a type. `A | B | C` is a flat
//     left-nested union_type.
//
// D4. Statement terminators. `;` is OPTIONAL everywhere (DESIGN.md writes
//     `Ok(());` but not `})` after a match, and never after a declaration).
//     Consequence, reported: with no terminator a newline does not end a
//     statement, so `f(x)` followed by a line starting with `(` or `[`
//     parses as a call/index of the previous line. DESIGN.md would need to
//     either require `;` or make the lexer newline-sensitive.
//
// D5. A trailing comma is allowed in argument lists, array literals, record
//     bodies, match arms, parameter lists and struct bodies (all appear in
//     DESIGN.md) but NOT in an enum variant list — an enum has no brackets,
//     so a trailing comma would leave no way to know the variant list ended.
//
// D6. Struct bodies separate members with an OPTIONAL comma: `Rect` uses
//     commas between fields, `String` and `Alloc` use none between methods,
//     `Tester` mixes both. So: `member (',')? member ...`.
//
// D7. `*` (the export marker) is the plain `*` token, not `token.immediate`.
//     `a*b` therefore stays multiplication; `x* = e` stays an export. The two
//     are distinguished by the token AFTER the star, which costs one GLR
//     fork. Zen has no pointer sigil (raw pointers are `Ptr<T>`), so `*` has
//     exactly two jobs: export marker and multiply.
//
// D8. Numeric literals: decimal integers and `d.d` floats ONLY. DESIGN.md
//     shows no hex, no binary, no exponent, no digit separators, no type
//     suffixes. Implementing more would be inventing.
//
// D9. Block comments do not nest. TESTING.md explicitly says "decide, then
//     test"; DESIGN.md does not decide, so this is the minimum.
//
// D10. `enum_declaration` and `alias_declaration` are MODULE-LEVEL only. This
//      is what keeps `Circle1 = AddFoo(Circle)` (inside `main`) a binding to a
//      comptime call rather than a one-variant enum. See A1 in the report.
//
// D11. `Name = { .. }` is ALWAYS a struct declaration, never a binding to a
//      block value. DESIGN.md shows blocks as values (`@scope`) only in
//      statement position, so no expression in this grammar may start with
//      `{`. Records and match blocks are therefore only legal as call
//      arguments, which is the only place DESIGN.md puts them.
//
// D12. One `function` node covers lambdas AND function types: a function type
//      is a function with no `body` field. That is exactly DESIGN.md's method
//      table — `= sig` vs `= sig {..}` differ only by the body — so making
//      them two nodes would put the same fact in two places. `iso` / `val` /
//      `ref` have NO written syntax anywhere in DESIGN.md and are therefore
//      NOT in this grammar.
// ---------------------------------------------------------------------------

const PREC = {
  consume: 1,
  union: 2,
  or: 3,
  and: 4,
  equality: 5,
  comparison: 6,
  additive: 7,
  multiplicative: 8,
  unary: 9,
  call: 10,
  member: 11,
};

/** @param {RuleOrLiteral} rule */
const comma_sep1 = (rule) => seq(rule, repeat(seq(',', rule)));

/** @param {RuleOrLiteral} rule */
const comma_sep = (rule) => optional(comma_sep1(rule));

module.exports = grammar({
  name: 'zen',

  word: ($) => $.identifier,

  extras: ($) => [/\s/, $.line_comment, $.block_comment],

  conflicts: ($) => [
    // `Name = Foo` / `Name = Foo(T)` — one-variant enum vs a binding to a
    // name or a call. THE known ambiguity (A1). Resolved by prec.dynamic on
    // enum_declaration, which is why the grammar can only carry this at
    // module level (D10).
    [$.binding, $.enum_declaration],
    // the payload of that fork: `str` in `Failed(str)` is a type on one side
    // of the fork and an expression on the other.
    [$._type, $._expression],
    // `self.len` — a binding target, or an expression statement? decided at
    // the `=` that may or may not follow.
    [$.binding, $.expression_statement],
    // `Foo*` — export marker, or `Foo * ...`? decided at the token after `*`.
    [$.declaration_name, $.binary_expression],
    // `(x)` / `(x, y)` — parameter list of a lambda, or a parenthesized
    // expression? decided at the `{` or return type that may follow.
    [$.parameters, $.parenthesized_expression],
    // `()` — the unit value/type, or an empty parameter list?
    [$.unit, $.parameters],
    // `[a, b]` — a two-element array literal, or a `[type, count]` array
    // type? decided at the `(` that may follow (A4).
    [$.array_literal, $.array_type],
    // `{ .. }` as a call argument — record, or match arms? decided at the
    // `:` / `=>` after the first entry.
    [$.record, $.match_block],
    // `f<T>(x)` — a generic call, or `f < T > (x)`? resolved by prec.dynamic
    // on call_expression (A5).
    [$.call_expression, $.binary_expression],
  ],

  rules: {
    source_file: ($) => repeat($._module_item),

    // enum and alias declarations are module-level only — D10 / A1.
    _module_item: ($) =>
      choice($.enum_declaration, $.alias_declaration, $._statement),

    _statement: ($) =>
      choice(
        $.struct_declaration,
        $.binding,
        $.expression_statement,
        $.block,
      ),

    // ------------------------------------------------------------------
    // names
    //
    // `*` means "this name crosses a module boundary" — law 6 — and it is
    // the same marker on a type, a field, a method and an import. One rule,
    // used in every declaring position.
    // ------------------------------------------------------------------

    declaration_name: ($) =>
      seq(
        field('name', $.identifier),
        optional(field('exported', $.export_marker)),
        optional(field('type_parameters', $.type_parameters)),
      ),

    export_marker: (_) => '*',

    // ------------------------------------------------------------------
    // declarations
    // ------------------------------------------------------------------

    // `x = e`, `x ::= e`, `x: T = e`, `x: T ::= e`
    // `self.len = self.len + 1` — a member expression is a target too.
    // `Res*, Ok*, None* = std.core.result` — re-export is an import whose
    // bindings are starred, so the target is a LIST and the value is an
    // ordinary path expression. No `export`, no `from`.
    binding: ($) =>
      seq(
        field('target', comma_sep1($._binding_target)),
        optional(seq(':', field('type', $._type))),
        field('operator', choice('=', '::=')),
        field('value', $._expression),
        optional(';'),
      ),

    _binding_target: ($) =>
      choice($.declaration_name, $.member_expression, $.index_expression),

    // `Name* = { field: T, field :: T, field: T = default, method* = sig {..} }`
    struct_declaration: ($) =>
      seq(
        field('name', $.declaration_name),
        '=',
        field('body', $.struct_body),
        optional(';'),
      ),

    // members are separated by an OPTIONAL comma — D6.
    struct_body: ($) =>
      seq('{', repeat(seq($.field_declaration, optional(','))), '}'),

    // one rule for fields and methods, because DESIGN.md has one rule:
    // "a struct whose fields happen to be functions, used as a bound, is what
    // other languages call a trait — nothing marks it special".
    //
    //   width: f64                       storage, set at construction
    //   data :: Vec<u8>                  storage, mutable
    //   verbose :: bool = false          storage with a default
    //   name* = sig                      required: impl must provide it
    //   name* = sig {..}                 sealed
    //   name* ::= sig {..}               default: impl may rebind
    //   name* ::= sig                    optional hook
    field_declaration: ($) =>
      seq(
        field('name', $.declaration_name),
        choice(
          seq(
            field('mutability', choice(':', '::')),
            field('type', $._type),
            optional(seq('=', field('default', $._expression))),
          ),
          seq(
            field('operator', choice('=', '::=')),
            field('value', $._expression),
          ),
        ),
      ),

    // `Name* = A(T), B(T), C` — NO braces. The asymmetry against structs is
    // deliberate in DESIGN.md and it is what makes A1 unresolvable here.
    // No trailing comma (D5): there is no closing bracket, so a trailing
    // comma would leave the end of the variant list undecidable.
    enum_declaration: ($) =>
      prec.dynamic(
        2,
        seq(
          field('name', $.declaration_name),
          '=',
          field('variants', comma_sep1($.enum_variant)),
          optional(';'),
        ),
      ),

    // payloads are TYPES: `Circle(Circle)`, `Failed(str)`, `Missing(str)`.
    // "a default payload and a discriminant are different things and are
    // written apart" — so a payload list never contains `name: value`, which
    // is what keeps `Package(url: "..", ..)` a call and not a variant.
    enum_variant: ($) =>
      seq(
        field('name', $.identifier),
        optional(field('payload', $.variant_payload)),
      ),

    variant_payload: ($) => seq('(', comma_sep1($._type), ')'),

    // `Error = AllocError | IoError | ArgError`
    // Requires at least one `|`, which is the ONLY thing that distinguishes
    // it from an enum declaration. A single-name right-hand side is not an
    // alias here — see A1.
    alias_declaration: ($) =>
      seq(
        field('name', $.declaration_name),
        '=',
        field('type', $.union_type),
        optional(';'),
      ),

    expression_statement: ($) => seq($._expression, optional(';')),

    // "A block is a value too." `@scope` stands for the enclosing block.
    // Blocks nest, and a block in statement position is a scope, never a
    // record — D11.
    block: ($) => seq('{', repeat($._statement), '}'),

    // ------------------------------------------------------------------
    // functions — D12
    //
    //   (a: T, b: T) R { .. }          lambda
    //   (a: i32, b: i32) i32           function TYPE (no body)
    //   <T: Bound>(x: T) R { .. }      generic, params on the lambda
    //   (h, field) { .. }              closure: parameter types optional
    //   () ()                          no params, returns unit
    //
    // "Function types must name their parameters" — so a parameter always
    // has a name, and only its TYPE is optional (closures infer it).
    // prec.right resolves the shift/reduce on `{`: a brace after a return
    // type is this function's body, never a following block statement.
    // ------------------------------------------------------------------

    function: ($) =>
      prec.right(
        seq(
          optional(field('type_parameters', $.type_parameters)),
          field('parameters', $.parameters),
          choice(
            seq(
              field('return_type', $._type),
              optional(field('body', $.block)),
            ),
            field('body', $.block),
          ),
        ),
      ),

    parameters: ($) =>
      seq('(', comma_sep($.parameter), optional(','), ')'),

    // `self :: @Self` is not a receiver rule — it is the ordinary binding
    // marker on the ordinary first parameter. `args: ...` is the variadic.
    parameter: ($) =>
      seq(
        field('name', $.identifier),
        optional(
          seq(
            field('mutability', choice(':', '::')),
            field('type', $._type),
          ),
        ),
      ),

    type_parameters: ($) => seq('<', comma_sep1($.type_parameter), '>'),

    // `<T>`, `<T: Rect>`, `<K: Eq + Hash, V>`, `<A: Actor>`
    type_parameter: ($) =>
      seq(
        field('name', $.identifier),
        optional(seq(':', field('bound', $.type_bound))),
      ),

    type_bound: ($) => seq($._type, repeat(seq('+', $._type))),

    // ------------------------------------------------------------------
    // types
    // ------------------------------------------------------------------

    _type: ($) =>
      choice(
        $.identifier,
        $.qualified_type,
        $.generic_type,
        $.array_type,
        $.function,
        $.unit,
        $.self_type,
        $.union_type,
        $.inferred_type,
        $.variadic_type,
      ),

    // no example in DESIGN.md qualifies a type across a module (imports bind
    // locally, so `Res` is already local). Supported anyway because module
    // paths are values: `pkg.json`.
    qualified_type: ($) =>
      prec.left(PREC.member, seq($._type, '.', $.identifier)),

    // `Vec<T>`, `Map<K, V>`, `Res<(), AllocError>`, `Vec<Entry<K, V>>`.
    // Zen has no `>>` operator, so nested generics close without a lexer
    // hack — that is a real property of the language, not luck.
    generic_type: ($) =>
      seq(field('name', $.identifier), field('arguments', $.type_arguments)),

    type_arguments: ($) => seq('<', comma_sep1($._type), '>'),

    // `[u8, 64]` — "fixed-size arrays are [type, count]: comptime length".
    // The count is an expression: it is comptime, not necessarily a literal.
    array_type: ($) =>
      seq(
        '[',
        field('element', $._type),
        ',',
        field('length', $._expression),
        ']',
      ),

    // `A | B` — "an anonymous enum of two variants — a structural enum, not
    // a new kind of type". D3: left-associative.
    union_type: ($) =>
      prec.left(PREC.union, seq($._type, repeat1(seq('|', $._type)))),

    // `Res<Cfg, _>` — inferred inside a module, written at the boundary.
    inferred_type: (_) => '_',

    // `args: ...`
    variadic_type: (_) => '...',

    // ------------------------------------------------------------------
    // expressions
    //
    // NOTHING here starts with `{` — D11. Records and match blocks exist
    // only as call arguments.
    // ------------------------------------------------------------------

    _expression: ($) =>
      choice(
        $.identifier,
        $.number_literal,
        $.string_literal,
        $.char_literal,
        $.boolean_literal,
        $.unit,
        $.self_type,
        $.scope_expression,
        $.meta_expression,
        $.parenthesized_expression,
        $.array_literal,
        $.fixed_array_expression,
        $.function,
        $.call_expression,
        $.member_expression,
        $.index_expression,
        $.unary_expression,
        $.binary_expression,
        $.consume_expression,
      ),

    parenthesized_expression: ($) => seq('(', $._expression, ')'),

    // `()` — the unit value and the unit type are one token pair.
    unit: (_) => seq('(', ')'),

    // ------------------------------------------------------------------
    // the `@` namespace. EXACTLY three entries: @Self, @meta, @scope.
    // "Adding a fourth is a design change, not an implementation detail"
    // (STYLE.md). They are tokens, not identifiers, so no user binding can
    // ever collide with one.
    // ------------------------------------------------------------------

    // the type being declared, inside a struct or impl body
    self_type: (_) => '@Self',

    // the enclosing block, as a value
    scope_expression: (_) => '@scope',

    // the ast node for a value or a type. `@meta(n)` takes a value;
    // `@meta(self: @Self)` takes a name and a type, which is the only place
    // in the language where an argument carries a type annotation.
    meta_expression: ($) =>
      seq('@meta', '(', field('argument', $._meta_argument), ')'),

    _meta_argument: ($) => choice($.typed_meta_argument, $._expression),

    typed_meta_argument: ($) =>
      seq(field('name', $.identifier), ':', field('type', $._type)),

    // `[0, 1, 2]`, `["/opt/homebrew/lib"]`, `[json, libsodium, extern_add]`
    array_literal: ($) => seq('[', comma_sep($._expression), optional(','), ']'),

    // `[i32, 4](2, 3, 5, 7)` — a fixed-array TYPE applied to its elements.
    // This is its own node rather than call(array_literal, ..) because an
    // array literal is never a callee; that keeps the reading unambiguous
    // once the `(` is seen. See A4.
    fixed_array_expression: ($) =>
      prec.dynamic(
        1,
        seq(field('type', $.array_type), field('arguments', $.arguments)),
      ),

    // `f(a, b)`, `alloc.Vec<i32>()`, `env.args<Opts>().try()`,
    // `Circle.impl(Rect, {..})`, `x.match({..})`.
    //
    // `A.impl(B, {..})` needs no rule of its own: it is a call in statement
    // position whose second argument is a record. "One rule, no second
    // mechanism."
    //
    // The callee is restricted (no array literals, no bare functions), which
    // is what makes `[i32, 4](..)` decidable.
    call_expression: ($) =>
      prec.dynamic(
        1,
        prec(
          PREC.call,
          seq(
            field('function', $._callee),
            optional(field('type_arguments', $.type_arguments)),
            field('arguments', $.arguments),
          ),
        ),
      ),

    _callee: ($) =>
      choice(
        $.identifier,
        $.member_expression,
        $.call_expression,
        $.index_expression,
        $.parenthesized_expression,
        $.self_type,
        $.scope_expression,
        $.meta_expression,
      ),

    arguments: ($) =>
      seq(
        '(',
        comma_sep(choice($.named_argument, $.record, $.match_block, $._expression)),
        optional(','),
        ')',
      ),

    // `Budget(name: "vec_add", ns_op: 40)`, `Entry(hash: h, key: key)`,
    // `Circle1(radius: 1.0, foo: 1)` — construction is `name: value`, the
    // same form an impl uses to supply a field.
    named_argument: ($) =>
      seq(field('name', $.identifier), ':', field('value', $._expression)),

    // the `{..}` of `A.impl(B, {..})` and of `b.exe("x", {..})`.
    // "an f64 field takes an f64, a function-typed field takes a function" —
    // so an entry is either `name: expr` (a supplied value) or
    // `name = fn` / `name ::= fn` (a supplied method, sealed or rebindable).
    record: ($) => seq('{', repeat(seq($.record_field, optional(','))), '}'),

    record_field: ($) =>
      seq(
        field('name', $.declaration_name),
        choice(
          seq(':', field('value', $._expression)),
          seq(
            field('operator', choice('=', '::=')),
            field('value', $._expression),
          ),
        ),
      ),

    // ------------------------------------------------------------------
    // match
    //
    // `.match` is a method, so there is no match rule — only the argument
    // it takes. "Arms are `pattern => expr`, comma-separated, no leading
    // `|`". Match is always exhaustive; `_` is a pattern, not a keyword
    // form, so exhaustiveness is sema's job and not the grammar's.
    // ------------------------------------------------------------------

    match_block: ($) =>
      seq('{', comma_sep1($.match_arm), optional(','), '}'),

    match_arm: ($) =>
      seq(
        field('pattern', $._pattern),
        '=>',
        field('value', choice($.block, $._expression)),
      ),

    _pattern: ($) =>
      choice(
        $.wildcard_pattern,
        $.destructure_pattern,
        $.path_pattern,
        $.number_literal,
        $.string_literal,
        $.char_literal,
        $.boolean_literal,
      ),

    // "cover every case or write `_`"
    wildcard_pattern: (_) => '_',

    // `Ok(n) => n`, `Circle(circle) => ..`, `Enum(e) => ..` — the payload
    // binds in the pattern, and the arm sees the typed node.
    destructure_pattern: ($) =>
      seq(
        field('name', $.path_pattern),
        '(',
        comma_sep1($._pattern),
        optional(','),
        ')',
      ),

    // `None`, `Macos`, `Shape.Unit`
    path_pattern: ($) => seq($.identifier, repeat(seq('.', $.identifier))),

    // ------------------------------------------------------------------
    // operators
    // ------------------------------------------------------------------

    member_expression: ($) =>
      prec.left(
        PREC.member,
        seq(field('object', $._expression), '.', field('property', $.identifier)),
      ),

    // `buf[i]` — bounds-checked and traps. A fixed array has no `Res`
    // escape hatch; that is the failure model, not the grammar.
    index_expression: ($) =>
      prec.left(
        PREC.call,
        seq(field('array', $._expression), '[', field('index', $._expression), ']'),
      ),

    // `&c.width`, `!self.eq(other)`, `-1`
    unary_expression: ($) =>
      prec.right(
        PREC.unary,
        seq(field('operator', choice('!', '-', '&')), field('operand', $._expression)),
      ),

    // "`consume` moves." Stated at the use site: `g = consume f`.
    consume_expression: ($) =>
      prec.right(
        PREC.consume,
        seq('consume', field('value', $._expression)),
      ),

    // D1. `+ - *` trap on overflow; `+% -% *%` wrap, at the same
    // precedence, because they are the same operation with a different
    // overflow rule. `/ %` trap on a zero divisor.
    binary_expression: ($) => {
      const table = [
        [PREC.or, '||'],
        [PREC.and, '&&'],
        [PREC.equality, '=='],
        [PREC.equality, '!='],
        [PREC.comparison, '<'],
        [PREC.comparison, '>'],
        [PREC.comparison, '<='],
        [PREC.comparison, '>='],
        [PREC.additive, '+'],
        [PREC.additive, '-'],
        [PREC.additive, '+%'],
        [PREC.additive, '-%'],
        [PREC.multiplicative, '*'],
        [PREC.multiplicative, '/'],
        [PREC.multiplicative, '%'],
        [PREC.multiplicative, '*%'],
      ];

      return choice(
        ...table.map(([precedence, operator]) =>
          prec.left(
            /** @type {number} */ (precedence),
            seq(
              field('left', $._expression),
              field('operator', /** @type {string} */ (operator)),
              field('right', $._expression),
            ),
          ),
        ),
      );
    },

    // ------------------------------------------------------------------
    // lexical
    // ------------------------------------------------------------------

    identifier: (_) => /[A-Za-z_][A-Za-z0-9_]*/,

    // D8: decimal only. No hex, no exponent, no separators, no suffixes —
    // DESIGN.md shows none of them.
    number_literal: (_) => token(seq(/[0-9]+/, optional(seq('.', /[0-9]+/)))),

    boolean_literal: (_) => choice('true', 'false'),

    // `"{}"` placeholders are format-string content, not syntax: the format
    // machinery routes `{}` through toString at the call, so the lexer sees
    // an ordinary string.
    string_literal: ($) =>
      seq('"', repeat(choice($.escape_sequence, token.immediate(/[^"\\]+/))), '"'),

    // "zen has `'a'` char literals; write `b == ':'` not `b == 58`"
    char_literal: ($) =>
      seq("'", choice($.escape_sequence, token.immediate(/[^'\\]/)), "'"),

    // the escape set is not enumerated in DESIGN.md; `\'` and `\\` are named
    // in TESTING.md. Anything after a backslash lexes, and sema decides.
    escape_sequence: (_) => token.immediate(seq('\\', /./)),

    line_comment: (_) => token(seq('//', /[^\n]*/)),

    // D9: not nested.
    block_comment: (_) => token(seq('/*', /[^*]*\*+([^/*][^*]*\*+)*/, '/')),
  },
});
