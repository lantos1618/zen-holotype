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
// GENERATED CLEAN. `tree-sitter generate` was run against this file (in a
// scratch copy, so grammar/src/ is still unwritten): no unresolved conflicts,
// and no unnecessary ones — every entry in `conflicts` below was named by the
// generator, and every entry it called unnecessary is gone. The parser was
// then built and driven over tests/, tests/parse/errors/ and every Zen block
// in DESIGN.md. the deleted bootstrapper reader keeps every node name it depends on in ONE
// table at the top of the file, so a rename is a one-file, one-table edit.
//
// ---------------------------------------------------------------------------
// THE FOUR DECISIONS (settled after the first draft; the historical bootstrapper contract
// carries the same list, and it is binding)
// ---------------------------------------------------------------------------
//
// R1. SUM TYPES USE `|`, NOT `,`.
//
//       Shape = Circle(Circle) | Rect(Rect) | Unit   // nominal, with payloads
//       Error = AllocError | IoError | ArgError      // a union of existing types
//       AllocError* = | OutOfMemory                  // one variant: the bar LEADS
//       Alias = Shape                                // no bar at all: an alias
//
//     A declaration whose right-hand side contains a top-level `|` is an enum;
//     one that does not is an alias (or an import, or a constant — see R1a).
//     `|` is not an expression operator in Zen, so the fork between "call" and
//     "first variant" always closes at the first bar, and the leading bar
//     closes it before it opens. This one decision retires FOUR ambiguities
//     from tests/parse/constructs.md at once: A-ALIAS, A-UNIONDECL, A-ENUMEND,
//     and the enum half of A-CONSTRUCT. Enums are now declarable ANYWHERE —
//     the module-level-only restriction (old D10) existed purely as a tiebreak
//     and is deleted.
//
//     R1a. What is left of `Name = <thing>` is decided by the SHAPE of
//     <thing>, in the deleted bootstrapper reader, not by more grammar:
//       `{ .. }`            struct
//       variants with `|`   enum
//       `(..) T { .. }`     function, with a body
//       `(..) T`            function, signature only
//       `a.b.c`             import (dotted path)
//       `Name` / `Name<T>`  alias
//       anything else       a constant (module level) / a binding (in a body)
//
// R2. A STATEMENT ENDS WITH `;`. A DECLARATION DOES NOT.
//
//     Struct, enum, alias, function-with-body and signature declarations take
//     no `;`, at module level and inside a body alike. Every statement inside
//     a body takes one. There is NO newline sensitivity and NO semicolon
//     insertion, so the hazard the old D4 recorded — a line beginning `(` or
//     `[` silently becoming a call or an index of the line above — cannot
//     occur. Retires A-SEMI and A-LEADDOT (a leading-dot continuation is now
//     just whitespace; nothing about it is load-bearing).
//
//     A block is `statement* expression?`: the optional final expression, the
//     one WITHOUT a `;`, is the block's value. DESIGN.md:405 also lets a
//     `;`-terminated tail (`Ok(0);`) be the value; that is a typing rule, not
//     a syntax one, so this grammar records only what is written and sema
//     decides. A-TAIL is therefore narrowed, not closed.
//
// R3. `ref` / `val` / `iso` HAVE NO SYNTAX. Capabilities are inferred and the
//     only thing ever written is `consume` (DESIGN.md:308). Nothing to add;
//     recorded so the next reader does not add it.
//
// R4. A STRUCT BODY MAY BIND CONSTANTS, read as `Type.NAME`:
//
//       i32* = { MAX: i32 = 2147483647, MIN: i32 = -2147483648, BITS: usize = 32 }
//
//     A member with `:` (immutable) AND a value is a CONSTANT — one value per
//     type. A member with `::` (mutable) and a value is a FIELD WITH A DEFAULT
//     — storage per value, optional at construction (`verbose :: bool = false`).
//     That is the only syntactic difference between them, and it leaves an
//     immutable field with a default unspellable; reported, not invented.
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
//     different overflow rule, not a different binding strength. (A-PREC)
//
// D2. `consume e` binds LOOSER than every other prefix operator and looser
//     than binary operators (`prec.right(PREC.consume)`), so `consume f` and
//     `consume buf` (the only two forms in DESIGN.md) parse, and
//     `consume a.b` consumes the field rather than the base.
//
// D3. `|` in a TYPE is left-associative and appears only at the top of a type
//     (`Res<Cfg, IoError | ParseError>`). `A | B | C` is a flat left-nested
//     union_type. In DECLARATION position `|` is the enum separator (R1) and
//     never reaches this rule.
//
// D4. Superseded by R2.
//
// D5. A trailing comma is allowed in argument lists, array literals, record
//     bodies, match arms, parameter lists and struct bodies (all appear in
//     DESIGN.md). An enum variant list has no trailing separator to allow:
//     `|` separates and never terminates. (A-ENUMEND, closed by R1.)
//
// D6. Struct bodies separate members with an OPTIONAL comma: `Rect` uses
//     commas between fields, `String` and `Alloc` use none between methods,
//     `Tester` mixes both. So: `member (',')? member ...`. (A-SEP, A-IMPLSEP)
//
// D7. `*` (the export marker) is the plain `*` token, not `token.immediate`.
//     `a*b` therefore stays multiplication; `x* = e` stays an export. They are
//     never in the same context: an export marker only ever follows the name
//     of a declaration or a member, and no expression may begin a module item
//     except an impl call. Zen has no pointer sigil (raw pointers are
//     `Ptr<T>`), so `*` has exactly two jobs. (A-STAR)
//
// D8. Numeric literals: decimal integers and `d.d` floats ONLY. DESIGN.md
//     shows no hex, no binary, no exponent, no digit separators, no type
//     suffixes. Implementing more would be inventing.
//
// D9. Block comments do not nest. TESTING.md explicitly says "decide, then
//     test"; DESIGN.md does not decide, so this is the minimum.
//
// D10. Withdrawn. Enum and alias declarations were module-level only as a
//      tiebreak for A-ALIAS; R1 removes the reason, so they are declarable
//      anywhere a declaration is.
//
// D11. `Name = { .. }` is ALWAYS a struct declaration, never a binding to a
//      block value, and NO expression may begin with `{`. Records and match
//      arm lists are therefore only legal as call arguments, which is the only
//      place DESIGN.md puts them, and the four meanings of `{` (A-BRACE)
//      become three positions plus one `:`/`=>` test inside an argument.
//
// D12. A function with a body and a function signature are two rules,
//      `function` and `function_signature`, because R2 makes the body the
//      thing that decides whether a `;` may follow. They still collapse to ONE
//      ast node with an optional body (the historical bootstrapper contract `Function.form`),
//      which is DESIGN.md's method table — `= sig` vs `= sig {..}` differ only
//      by the body. Per R3 there is no capability syntax on either.
//
// D13. Parameter types are OPTIONAL in the grammar, because a closure infers
//      them from the call (DESIGN.md:254) and `(h, field)` must parse. A
//      DECLARATION and a function TYPE must still write every type
//      (DESIGN.md:223, 329); that is checked in the deleted bootstrapper reader, which is
//      where the position is known, and it is a diagnostic rather than a parse
//      error. Fixtures for that rule therefore belong in tests/must-fail/,
//      where the compiler's diagnostic is asserted, and NOT in
//      tests/parse/errors/, which contain programs the grammar must reject.
//      They lived in the wrong place until
//      2026-08-10; `bare_self_param` and `match_arm_paren_form` moved to
//      tests/must-fail/ and `fn_type_unnamed_params` was dropped as a
//      duplicate of the must-fail/parse test that already gated it. (A-CLO)
//
// D14. A return type is optional on a function with a body (`started ::=
//      (self :: @Self, ctx: Context) { .. }`, DESIGN.md:1165) and omitted
//      means `()`. DESIGN.md writes the same method both ways; A-RET stays
//      open, this grammar accepts both.
//
// D15. An enum variant carries AT MOST ONE payload type, per
//      the historical bootstrapper contract `Variant(name, payload)`. DESIGN.md never writes
//      two.
//
// D15a. A signature ALWAYS writes its return type; only a function WITH a
//      body may omit it (D14). Beyond following every `= sig` in DESIGN.md,
//      this is what keeps a bare `()` the unit type: with an optional return
//      type, `Res<(), IoError>` reads as a function type of no parameters.
//
// D15b. A payload pattern may NEST — `Left(Full(n))`, which TESTING.md
//      requires exhaustiveness over and tests/corpus/sema/match_nested.zen
//      writes. `Left(Blank)` and `Ok(n)` are the same three tokens, so
//      "binds the payload" versus "names a variant" is sema's question, not
//      the grammar's; cst.py hands both over as a plain name.
//
// D16. `A.impl(B, { .. })` is its own rule at module level rather than a call,
//      because module level has no expression statements at all under R2 — so
//      giving it a rule costs no ambiguity and gains a node name the LSP and
//      the formatter can match on. cst.py still checks the method is `impl`;
//      `impl` is NOT a reserved word (A-KEYWORDS).
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

/** trailing comma allowed, empty allowed — D5 @param {RuleOrLiteral} rule */
const comma_list = (rule) => optional(seq(comma_sep1(rule), optional(',')));

module.exports = grammar({
  name: 'zen',

  word: ($) => $.identifier,

  extras: ($) => [/\s/, $.line_comment, $.block_comment],

  // Every entry below was named by `tree-sitter generate`, and every entry it
  // reported as unnecessary has been removed: this list is the real fork set,
  // not a guess.
  conflicts: ($) => [
    // `Foo(T)` — the first variant of an enum, or a call bound to a name?
    // Closes at the first `|` (R1), or never opens when the bar leads.
    [$.enum_variant, $._callee],
    // `Vec<i32>` — an alias target / a type, or `Vec < i32`? Decided at the
    // token after the `>`. (A-ANGLE)
    [$.generic_type, $._expression, $._callee],
    [$.generic_type, $._type],
    // the payload of the enum fork: `str` in `Failed(str)` is a type on one
    // side and an expression on the other.
    [$._type, $._expression],
    // D7: `x*` at the head of a statement — an export marker, or `x * y`?
    // And `x<T> =` — type parameters, or `x < T`? Decided one token later.
    [$.declaration_name, $._binding_target],
    [$.declaration_name, $._expression],
    [$.declaration_name, $._expression, $._callee],
    // `(x)` / `(x, y)` — a parameter list, or a parenthesized expression?
    // decided at the `{` or the return type that may follow.
    [$.parameter, $._expression],
    // `()` — the unit value/type, or an empty parameter list?
    [$.unit, $.parameters],
    // an expression that may or may not turn out to be a callee: decided at
    // the `(` — or at the `<` of a type argument list — that may follow.
    [$._expression, $._callee],
  ],

  rules: {
    source_file: ($) => repeat($._module_item),

    // Module level is DECLARATIONS ONLY, so nothing here ends in `;` — R2.
    // `A.impl(B, {..})` is the one call-shaped thing that declares (D16).
    _module_item: ($) => choice($.declaration, $.impl_declaration),

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
    //
    // ONE rule for every module-level declaration. What it declares is read
    // off the shape of the value (R1a) in the deleted bootstrapper reader, which is the
    // only place that knowledge lives:
    //
    //   Vec*<T> = { .. }                     struct
    //   Shape = Circle(Circle) | Unit        enum
    //   AllocError* = | OutOfMemory          enum, one variant
    //   Alias = Shape                        alias
    //   Res*, Ok*, None* = std.core.result   import, re-exported
    //   area* = (c: Circle) f64 { .. }       function, with a body
    //   then* = <T>(b: bool, f: () T) Res<T> function, signature only
    //   json_pkg = Package(url: "..", ..)    module constant
    //
    // The name list exists for imports: "Re-export is an import whose
    // bindings are starred. No `export`, no `from`" (DESIGN.md:328).
    // No `;` — a declaration does not take one (R2).
    // ------------------------------------------------------------------

    declaration: ($) =>
      seq(
        comma_sep1(field('name', $.declaration_name)),
        optional(seq(':', field('type', $._type))),
        field('operator', choice('=', '::=')),
        field('value', $._declaration_value),
      ),

    _declaration_value: ($) =>
      choice(
        $.struct_body,
        $.enum_body,
        $.function_signature,
        $.generic_type,
        $._expression,
      ),

    // `Circle.impl(Rect, { width: .., height: .. })` — D16. The shape is
    // fixed (a target, a trait, and a record) because that is the only shape
    // DESIGN.md writes; cst.py checks that the method really is `impl`.
    impl_declaration: ($) =>
      seq(
        field('target', $.identifier),
        '.',
        field('method', $.identifier),
        '(',
        field('trait', $._type),
        ',',
        field('body', $.record),
        optional(','),
        ')',
      ),

    // members are separated by an OPTIONAL comma — D6.
    struct_body: ($) =>
      seq('{', repeat(seq($.member_declaration, optional(','))), '}'),

    // one rule for fields, constants and methods, because DESIGN.md has one
    // rule: "a struct whose fields happen to be functions, used as a bound, is
    // what other languages call a trait — nothing marks it special".
    //
    //   width: f64                       storage, set at construction
    //   data :: Vec<u8>                  storage, mutable
    //   verbose :: bool = false          storage with a default        (R4)
    //   MAX: i32 = 2147483647            a CONSTANT, read as `i32.MAX` (R4)
    //   name* = sig                      required: impl must provide it
    //   name* = sig {..}                 sealed
    //   name* ::= sig {..}               default: impl may rebind
    //   name* ::= sig                    optional hook
    member_declaration: ($) =>
      seq(
        field('name', $.declaration_name),
        choice(
          seq(
            field('mutability', choice(':', '::')),
            field('type', $._type),
            optional(seq('=', field('value', $._expression))),
          ),
          seq(
            field('operator', choice('=', '::=')),
            field('value', choice($.function_signature, $.function)),
          ),
        ),
      ),

    // R1. `|` separates variants and NEVER terminates the list, so there is
    // no trailing-separator question and no "where does the list end". One
    // variant takes the LEADING bar; no bar at all is not an enum.
    enum_body: ($) =>
      choice(
        seq('|', $.enum_variant, repeat(seq('|', $.enum_variant))),
        seq($.enum_variant, repeat1(seq('|', $.enum_variant))),
      ),

    // payloads are TYPES: `Circle(Circle)`, `Failed(str)`, `Missing(str)`.
    // "a default payload and a discriminant are different things and are
    // written apart" — so a payload never contains `name: value`, which is
    // what keeps `Package(url: "..", ..)` a call and not a variant. D15: one
    // payload type, never a list.
    // prec.right: a `(` after a variant name is that variant's payload, never
    // the start of the next statement. This is the ONE residue of R2 — a
    // declaration takes no `;`, so a statement beginning `(` on the next line
    // still forks — and it is resolved greedily, in favour of the payload.
    enum_variant: ($) =>
      prec.right(
        seq(
          field('name', $.identifier),
          optional(field('payload', $.variant_payload)),
        ),
      ),

    variant_payload: ($) => seq('(', field('type', $._type), ')'),

    // ------------------------------------------------------------------
    // statements — R2. Every one of these ends with `;` EXCEPT a nested
    // declaration (which is a declaration, wherever it stands) and a bare
    // block (which ends with `}` and is not an expression, D11).
    // ------------------------------------------------------------------

    // "A block is a value too." The optional trailing expression — the one
    // with no `;` — is the block's value.
    block: ($) =>
      seq(
        '{',
        repeat($._statement),
        optional(field('value', $._expression)),
        '}',
      ),

    _statement: ($) =>
      choice(
        $.declaration_statement,
        $.let_statement,
        $.expression_statement,
        $.block,
      ),

    // a declaration inside a body: a struct, an enum, or a function with a
    // body — `add_i32 = (a: i32, b: i32) i32 { a + b }` (DESIGN.md:1230).
    // No `;`, exactly as at module level.
    declaration_statement: ($) =>
      seq(
        field('name', $.declaration_name),
        field('operator', choice('=', '::=')),
        field('value', choice($.struct_body, $.enum_body, $.function, $.function_signature)),
      ),

    // `x = e;`, `x ::= e;`, `x: T = e;`, `x: T ::= e;`
    // `self.len = self.len + 1;` — a member expression is a target too.
    let_statement: ($) =>
      seq(
        field('target', $._binding_target),
        optional(seq(':', field('type', $._type))),
        field('operator', choice('=', '::=')),
        field('value', $._expression),
        ';',
      ),

    _binding_target: ($) =>
      choice($.identifier, $.member_expression, $.index_expression),

    expression_statement: ($) => seq($._expression, ';'),

    // ------------------------------------------------------------------
    // functions — D12
    //
    //   (a: T, b: T) R { .. }          function with a body / lambda
    //   (a: i32, b: i32) i32           signature: a function TYPE, or a
    //                                  `= sig` declaration
    //   <T: Bound>(x: T) R { .. }      generic, parameters on the value side
    //   (h, field) { .. }              closure: parameter types inferred (D13)
    //   () ()                          no parameters, returns unit
    //
    // prec.dynamic prefers the form WITH a body when both fit, which is what
    // `x = (a: i32) i32 { .. }` means.
    // ------------------------------------------------------------------

    function: ($) =>
      prec.dynamic(
        1,
        prec.right(
          seq(
            optional(field('type_parameters', $.type_parameters)),
            field('parameters', $.parameters),
            optional(field('return_type', $._type)),
            field('body', $.block),
          ),
        ),
      ),

    // A signature ALWAYS writes its return type: `() ()` "has nothing to name
    // and stays as it is" (DESIGN.md:389), and every `= sig` in the document
    // writes one. Requiring it is also what keeps a bare `()` the unit type
    // rather than an empty parameter list — otherwise `Res<(), IoError>` reads
    // as a function type.
    function_signature: ($) =>
      prec.right(
        seq(
          optional(field('type_parameters', $.type_parameters)),
          field('parameters', $.parameters),
          field('return_type', $._type),
        ),
      ),

    parameters: ($) => seq('(', comma_list($.parameter), ')'),

    // `self :: @Self` is not a receiver rule — it is the ordinary binding
    // marker on the ordinary first parameter. `args: ...` is the variadic.
    // The type is optional for closures only; cst.py enforces the rest (D13).
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
        $.generic_type,
        $.array_type,
        $.function_signature,
        $.unit,
        $.self_type,
        $.union_type,
        $.inferred_type,
        $.variadic_type,
      ),

    // NOTE: there is no qualified type (`std.core.Res`) in this grammar,
    // because there is none in DESIGN.md — imports bind locally, so a type is
    // always reachable by a bare name. Adding one is a design change.

    // `Vec<T>`, `Map<K, V>`, `Res<(), AllocError>`, `Vec<Entry<K, V>>`.
    // Zen has no `>>` operator, so nested generics close without a lexer
    // hack — that is a real property of the language, not luck.
    generic_type: ($) =>
      seq(field('name', $.identifier), field('arguments', $.type_arguments)),

    type_arguments: ($) => seq('<', comma_sep1($._type), '>'),

    // `[u8, 64]` — "fixed-size arrays are [type, count]: comptime length".
    // The count is an expression: it is comptime, not necessarily a literal
    // (`[u8, i32.BITS]`, DESIGN.md:376).
    array_type: ($) =>
      seq(
        '[',
        field('element', $._type),
        ',',
        field('length', $._expression),
        ']',
      ),

    // `A | B` in TYPE position only — "an anonymous enum of two variants — a
    // structural enum, not a new kind of type". D3: left-associative. At
    // declaration level the same bar builds an enum_body (R1).
    union_type: ($) =>
      prec.left(
        PREC.union,
        seq(field('left', $._type), '|', field('right', $._type)),
      ),

    // `Res<Cfg, _>` — inferred inside a module, written at the boundary.
    inferred_type: (_) => '_',

    // `args: ...` (A-VARIADIC: never defined in DESIGN.md; taken as a type)
    variadic_type: (_) => '...',

    // ------------------------------------------------------------------
    // expressions
    //
    // NOTHING here starts with `{` — D11. Records and match arm lists exist
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
        $.try_expression,
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
    // in the language where an argument carries a type annotation. (A-META-ARG)
    meta_expression: ($) =>
      seq('@meta', '(', field('argument', $._meta_argument), ')'),

    _meta_argument: ($) => choice($.typed_meta_argument, $._expression),

    typed_meta_argument: ($) =>
      seq(field('name', $.identifier), ':', field('type', $._type)),

    // `[0, 1, 2]`, `["/opt/homebrew/lib"]`, `[json, libsodium, extern_add]`
    array_literal: ($) => seq('[', comma_list($._expression), ']'),

    // `[i32, 4](2, 3, 5, 7)` — a fixed-array TYPE applied to its elements.
    // Its own node rather than call(array_literal, ..) because an array
    // literal is never a callee; that keeps the reading unambiguous once the
    // `(` is seen.
    fixed_array_expression: ($) =>
      prec.dynamic(
        1,
        seq(field('type', $.array_type), field('arguments', $.arguments)),
      ),

    // The compiler AST gives this intrinsic its own node. It accepts no
    // mapping, one replacement value, or one mapper lambda.
    try_expression: ($) =>
      prec.dynamic(
        2,
        prec(
          PREC.call,
          seq(
            field('operand', $._expression),
            '.',
            field('operator', alias('try', $.identifier)),
            '(',
            optional(field('error', $._expression)),
            ')',
          ),
        ),
      ),

    // `f(a, b)`, `alloc.Vec<i32>()`, `env.args<Opts>().try()`,
    // `x.match({..})`, `b.exe("name", {..})`.
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
        comma_list(
          choice($.named_argument, $.record, $.match_block, $._expression),
        ),
        ')',
      ),

    // `Budget(name: "vec_add", ns_op: 40)`, `Entry(hash: h, key: key)`,
    // `Circle1(radius: 1.0, foo: 1)` — construction is `name: value`, the
    // same form an impl uses to supply a field. (A-CONSTRUCT: positional
    // arguments occur too, and both are accepted.)
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
            field('value', choice($.function_signature, $._expression)),
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

    // The comma BETWEEN arms is OPTIONAL, exactly as it is between struct
    // members (D6): the compiler's arm parser eats each arm's separator with
    // `p.eat` (src/std/parse/parse_match.zen) and `zen fmt`'s re-lex guard
    // forbids inserting one, so a block-bodied arm followed by another arm is
    // legal without the comma. Issue #770 was this rule demanding what the
    // compiler never did. A trailing comma is still allowed (D5).
    //
    // At least ONE arm stays required, as it was here before: an empty `{}` is
    // rejected by sema as non-exhaustive either way, and dropping the minimum
    // would make `{}` ambiguous against `record` inside `arguments`.
    match_block: ($) =>
      seq('{', repeat1(seq($.match_arm, optional(','))), '}'),

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

    // `Ok(n) => n`, `Circle(circle) => ..`, `Ok(_) => ..`, and nested:
    // `Left(Full(n))` (TESTING.md requires exhaustiveness over nested
    // patterns, and tests/corpus/sema/match_nested.zen writes them).
    //
    // `Left(Blank)` and `Ok(n)` are the same three tokens: whether the inner
    // name binds the payload or names a variant is a question about what is
    // in scope, so it is sema's, and cst.py hands both over as a plain name.
    destructure_pattern: ($) =>
      seq(field('name', $.path_pattern), '(', field('binder', $._pattern), ')'),

    // `None`, `Macos`, `Shape.Unit`
    path_pattern: ($) => seq($.identifier, repeat(seq('.', $.identifier))),

    // ------------------------------------------------------------------
    // operators
    // ------------------------------------------------------------------

    member_expression: ($) =>
      prec.left(
        PREC.member,
        seq(
          field('object', $._expression),
          '.',
          field('property', $.identifier),
        ),
      ),

    // `buf[i]` — bounds-checked and traps. A fixed array has no `Res`
    // escape hatch; that is the failure model, not the grammar. (A-INDEX)
    index_expression: ($) =>
      prec.left(
        PREC.call,
        seq(
          field('array', $._expression),
          '[',
          field('index', $._expression),
          ']',
        ),
      ),

    // `&c.width`, `!self.eq(other)`, `-1` (A-AMP: `&` appears once, in an
    // example marked ERROR for an unrelated reason, so it parses)
    unary_expression: ($) =>
      prec.right(
        PREC.unary,
        seq(
          field('operator', choice('!', '-', '&')),
          field('operand', $._expression),
        ),
      ),

    // "`consume` moves." Stated at the use site: `g = consume f`.
    consume_expression: ($) =>
      prec.right(PREC.consume, seq('consume', field('value', $._expression))),

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
    // an ordinary string. (A-FMT)
    // ONE token, not a seq. A `seq` lets `extras` -- whitespace and both
    // comment forms -- match BETWEEN its elements, so `"// x"` matched a
    // line_comment INSIDE the string and ran to the end of the next line,
    // corrupting every literal after it. A token has no seams for an extra
    // to enter.
    //
    // `\n` is excluded on both branches because DESIGN.md's lexical rules
    // say a string literal does not span lines, and a token is where that
    // is expressible: as a `seq` the newline was matched by `[^"\\]+` and
    // the rule could not state its own law.
    string_literal: (_) =>
      token(seq('"', repeat(choice(seq('\\', /[^\n]/), /[^"\\\n]/)), '"')),

    // "zen has `'a'` char literals; write `b == ':'` not `b == 58`"
    // one token, for the same reason as string_literal above. A char
    // literal holds exactly one byte (DESIGN.md), and does not span lines.
    char_literal: (_) =>
      token(seq("'", choice(seq('\\', /[^\n]/), /[^'\\\n]/), "'")),

    // the escape set is not enumerated in DESIGN.md; `\'` and `\\` are named
    // in TESTING.md. Anything after a backslash lexes, and sema decides.
    line_comment: (_) => token(seq('//', /[^\n]*/)),

    // D9: not nested.
    block_comment: (_) => token(seq('/*', /[^*]*\*+([^/*][^*]*\*+)*/, '/')),
  },
});
