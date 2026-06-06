// tree-sitter grammar for the Zen subset that zen type-checks.
// Mirrors lantos1618/zenlang surface syntax: `Name: {..}` structs, `name = (..) Ret {..}`
// functions, `Ptr/MutPtr/RawPtr<T>` pointers, `{ a } = mod` imports.

const sep1   = (r, s) => seq(r, repeat(seq(s, r)));
const comma1 = (r)    => sep1(r, ',');

module.exports = grammar({
  name: 'zen',

  extras: $ => [/\s/, $.comment],     // whitespace (incl. newlines) is insignificant here
  word: $ => $.identifier,

  // loop(EXPR, (h,i){…}) vs loop((h){…}): after `loop(`, a `(` could begin the
  // count expression or the param group — GLR forks and the valid parse wins.
  conflicts: $ => [[$.loop_, $._primary, $.closure], [$._primary, $.closure],
                   // a bodyless fn (foreign binding) vs one whose `{…}` body follows the
                   // return type: after `name = (p) Ret`, a `{` lookahead forks — GLR wins.
                   [$.function],
                   // prefix `!` vs a postfix `.match`/`.name` on the same operand
                   // (`!x.match {…}`): GLR forks; a `.match {` is unambiguously a match.
                   [$.unary_op, $.match, $.field_access]],

  rules: {
    source_file: $ => repeat($._item),
    _item: $ => choice($.import, $.struct, $.enum, $.function, $.impl, $.emit),

    // @emit(gen(reflect(Point)))   — run a comptime (Ast)->Ast generator and splice
    // the declaration it returns into this module, then check + lower it. The `@`
    // marks it a compiler primitive (like @while), not a bare prefix keyword.
    emit: $ => seq('@emit', '(', field('value', $._expression), ')'),

    comment: $ => token(seq('//', /[^\n]*/)),

    // { a, b } = core.vec
    import: $ => seq('{', comma1($.identifier), '}', '=', $.module_path),
    module_path: $ => sep1($.identifier, '.'),

    // a declaration's own type parameters, each optionally bounded by a trait:
    //   Box<T>,  map<T, U>,  total<T: Area>
    type_params: $ => seq('<', comma1($.tparam), '>'),
    tparam: $ => seq(field('name', $.identifier),
                     optional(seq(':', field('bound', $.identifier)))),

    // A trait has NO keyword — it is a record whose every member is a function type:
    //   Area*: { area: (Ptr<Self>) i32 }
    // It shares the `struct` rule (a field type may be a fn_type); the parser tells a
    // trait from a struct by that all-function-typed shape.

    // Vec.impl(Area, { area = (v: Ptr<Vec>) i32 { ... } })   — no `impl`/`for` keywords leading
    // the line; the implementing type owns it via a postfix `.impl(Trait, { methods })`. The methods
    // block is an ARGUMENT (inside the parens), consistent with `recv.match({ … })` / `.loop((…){…})`.
    impl: $ => seq(field('type', $.identifier), '.', 'impl',
                   '(', field('trait', $.identifier), ',',
                   '{', repeat($.function), '}', ')'),

    // Vec*: { len: i32, cap: i32 }   /   Box*<T>: { val: T }   (the glued `*` = public)
    struct: $ => seq(field('name', $.identifier), optional(field('vis', token.immediate('*'))),
                     optional(field('tparams', $.type_params)), ':',
                     '{', comma1($.field), optional(','), '}'),
    field: $ => seq(field('name', $.identifier), ':', field('type', $._type)),

    // Opt*<T>: None | Some(T)   (the glued `*` = public; variants are `|`-separated —
    // a sum type is a *choice*, so `|` ("or"), vs the `{a, b}` *record* with commas)
    enum: $ => seq(field('name', $.identifier), optional(field('vis', token.immediate('*'))),
                   optional(field('tparams', $.type_params)), ':',
                   sep1($.variant, '|')),
    variant: $ => seq(field('name', $.identifier),
                      optional(seq('(', field('payload', $._type), ')'))),

    // area* = (v: Ptr<Vec>) i32 { … }   — the glued `*` = public; the return type may be
    // omitted and inferred:  area* = (v: Ptr<Vec>) { len(v) * cap(v) }
    // A function with NO body block is a foreign binding (the C symbol is the bare name),
    // e.g.  malloc* = (n: i64) RawPtr<u8>  — replaces the old `extern` keyword.
    function: $ => seq(field('name', $.identifier), optional(field('vis', token.immediate('*'))),
                       optional(field('tparams', $.type_params)), '=',
                       '(', optional(comma1($.param)), ')',
                       optional(field('ret', $._type)), optional(field('body', $.block))),
    param: $ => seq(field('name', $.identifier), ':', field('type', $._type)),

    _type: $ => choice($.primitive, $.pointer, $.slice_type, $.fn_type, $.named_type),
    // (A, T) A — a closure/function type. Only meaningful as a parameter: the fn
    // taking it is an inline template (monomorphized + inlined, no fn pointers).
    fn_type: $ => seq('(', optional(comma1($._type)), ')', field('ret', $._type)),
    primitive: $ => choice('i32', 'i64', 'u8', 'bool', 'void', 'str'),
    pointer: $ => seq(field('dir', choice('Ptr', 'MutPtr', 'RawPtr')),
                      '<', field('pointee', $._type), '>'),
    slice_type: $ => seq('[', field('elem', $._type), ']'),   // [T] — a (ptr, len) view
    // a nominal type: `Vec`, `Box<T>`, or a fully-qualified `core.vec.Vec`
    // (a dotted path, so a type can be named without importing it first).
    named_type: $ => seq(field('name', $.identifier),
                         repeat(seq('.', field('seg', $.identifier))),
                         optional(seq('<', comma1($._type), '>'))),

    block: $ => seq('{', repeat($._statement), '}'),
    _statement: $ => choice($.let_binding, $.assign, $.while_prim, $.loop_, $.loop_method, $._expression),
    // x := expr  — a local binding (type inferred from the value)
    let_binding: $ => seq(field('name', $.identifier), ':=', field('value', $._expression)),
    // lvalue = expr  — reassign a local, or set a struct field (s.f = v)
    assign: $ => prec(1, seq(field('target', choice($.identifier, $.field_access, $.index)),
                             '=', field('value', $._expression))),
    // @while(cond) { … } — the structured loop PRIMITIVE (plumbing; prefer `loop`).
    // It carries a backend-visible structure (lowers to a C `for`), so the C
    // compiler can still auto-vectorize it — never unravelled to gotos.
    while_prim: $ => seq('@while', '(', field('cond', $._expression), ')', field('body', $.block)),

    // the one iteration construct (no `while`/`for`):
    //   loop((h) { … })          iterless — the handle drives it (h.break/h.continue)
    //   loop(n, (h, i) { … })    count    — i runs 0..n-1
    // the closure is sugar (inlined), so the body reads/mutates enclosing locals;
    // it all folds to a C `for`.
    loop_: $ => seq('loop', '(',
                    optional(seq(field('count', $._expression), ',')),
                    '(', field('params', seq($.identifier, repeat(seq(',', $.identifier)))), ')',
                    field('body', $.block), ')'),
    // postfix: xs.loop((h, i, x) { … }) — same as loop(xs, (h, i, x) { … }).
    loop_method: $ => prec(8, seq(field('recv', $._unary), token.immediate('.'), 'loop', '(',
                    '(', field('params', seq($.identifier, repeat(seq(',', $.identifier)))), ')',
                    field('body', $.block), ')')),
    // a leading-dot constructor `.Ok(x)` — an expression, so it works as a call
    // argument and match arm body too, not just a bare statement.
    enum_ctor: $ => seq('.', field('name', $.identifier), $.arguments),

    // a postfix chain: primary, then any number of (args) calls and .name accesses.
    // A "method call" is simply a call whose `fn` is a field_access — no special rule.
    _expression: $ => choice($.binary, $._unary),
    _unary: $ => choice($._primary, $.call, $.field_access, $.index, $.unary_op, $.match),
    unary_op: $ => prec(7, seq(field('op', '!'), $._unary)),   // logical not
    // xs[i] — the `[` must be glued (token.immediate), so a statement-leading
    // `[a,b,c]` slice literal is never absorbed as an index of the previous line.
    index: $ => prec.left(4, seq(field('seq', $._unary), token.immediate('['), field('idx', $._expression), ']')),
    _primary: $ => choice($.parenthesized, $.closure, $.enum_ctor, $.struct_literal, $.slice_literal, $.integer, $.char, $.boolean, $.string, $.identifier),
    slice_literal: $ => seq('[', optional(seq(comma1($._expression), optional(','))), ']'),  // [a, b, c]
    // (a, x) { a + x } — a closure value; the trailing block is what tells it apart
    // from a parenthesized expression (GLR forks, the one with a `{` body wins).
    closure: $ => seq('(', optional(field('params', seq($.identifier, repeat(seq(',', $.identifier))))), ')',
                      field('body', $.block)),

    // subject.match ({ .Variant(x) => expr, .Other => expr, _ => expr })
    // Postfix, like .loop / .impl — subject-first, no `match` prefix keyword. The
    // subject is any postfix expression (`result.match ({…})`, `xs.head().match ({…})`);
    // wrap a binary subject in parens: `(n < 0).match ({…})`. `match` stays a reserved
    // word, so `.match (` is unambiguous against a `.name` field access.
    // The arm-record MUST be wrapped in parens — `subject.match ({…})` — so match
    // reads as "a function taking a `{}`". The parens are pure punctuation (no field).
    // The bare brace form `subject.match {…}` is a hard error.
    match: $ => prec.left(8, seq(field('subject', $._unary), token.immediate('.'), 'match',
                    '(',
                    '{', comma1($.match_arm), optional(','), '}',
                    ')')),
    match_arm: $ => seq(field('pat', $.pattern), '=>', field('body', $._expression)),
    pattern: $ => choice($.ctor_pattern, $.literal_pattern, $.wildcard),
    ctor_pattern: $ => seq('.', field('name', $.identifier),
                           optional(seq('(', field('binding', $.identifier), ')'))),
    literal_pattern: $ => choice($.integer, $.boolean),   // n.match { 0 => …, _ => … }
    wildcard: $ => '_',

    // The callee is a name `f(…)` or a method receiver chain `a.b.f(…)` — NOT an
    // arbitrary expression. ast.py's Call.callee is a `str`, and the parser only reads
    // an identifier or field_access here; allowing any `_unary` let `f()()` / `xs[0]()`
    // parse into a garbage callee. (field_access's own `obj` is still any _unary, so
    // `addr(x).f()` and `a.b.c(…)` chains keep working.)
    call:         $ => prec.left(4, seq(field('fn', choice($.identifier, $.field_access)), $.arguments)),
    // the postfix `.` is glued (token.immediate) — like the call `(` and index `[` —
    // so a statement-leading `.Ok(…)` on the next line is a fresh enum_ctor, not a
    // method call absorbed onto the previous statement.
    field_access: $ => prec.left(4, seq(field('obj', $._unary), token.immediate('.'), field('name', $.identifier))),

    binary: $ => choice(
      prec.left(1, seq($._expression, '||', $._expression)),                       // bool -> bool
      prec.left(2, seq($._expression, '&&', $._expression)),
      prec.left(3, seq($._expression, choice('==', '<', '>', '<=', '>='), $._expression)),  // -> bool
      prec.left(4, seq($._expression, choice('+', '-'), $._expression)),           // numeric
      prec.left(5, seq($._expression, choice('*', '/', '%'), $._expression)),       // mul/div/rem
    ),

    struct_literal: $ => prec(5, seq(field('type', $.identifier),
                          '{', optional(seq(comma1($.field_init), optional(','))), '}')),
    field_init: $ => seq(field('name', $.identifier), ':', field('value', $._expression)),
    parenthesized: $ => seq('(', $._expression, ')'),
    // the call `(` must be glued (token.immediate) — so a statement that begins with
    // `(` (e.g. `(n < 0).match {…}`) is never absorbed as arguments of the line above.
    arguments: $ => seq(token.immediate('('), optional(comma1($._expression)), ')'),

    integer: $ => /\d+/,
    char: $ => token(seq("'", choice(/[^'\\]/, /\\./), "'")),   // 'a' '0' ':' '\n' — its byte value
    boolean: $ => choice('true', 'false'),
    string: $ => token(seq('"', repeat(choice(/[^"\\]/, /\\./)), '"')),  // escapes: \" \\ \n \t …
    identifier: $ => /@?[A-Za-z_]\w*/,
  }
});
