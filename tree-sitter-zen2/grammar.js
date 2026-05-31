// Zen v2 — the "one structure" grammar.
// Everything is a decl:  name [*] [: Type] [ (= | :=) value ]
// A `{ }` is ONE thing (a brace of items); record-vs-block is a semantic call, not syntax.
// Products are { decls }, sums are  a | b,  control flow is postfix (.match).
const sep1   = (r, s) => seq(r, repeat(seq(s, r)));
const comma1 = (r)    => sep1(r, ',');

module.exports = grammar({
  name: 'zen2',
  extras: $ => [/\s/, $.comment],
  word: $ => $.ident,

  rules: {
    source_file: $ => repeat($.decl),
    comment: $ => token(seq('//', /[^\n]*/)),

    // THE declaration. A decl must carry a `:` or a bind — a bare name is an expression.
    decl: $ => seq(
      field('name', $.name_path),                      // `main`, or a path: `Circle.Area`
      optional(field('pub', token.immediate('*'))),    // `name*` (glued) = pub; `a * b` = multiply
      optional(field('tparams', $.tparams)),
      choice(
        seq(':', field('type', $._type),
            optional(seq(field('bind', choice(':=', '=')), field('value', $._value)))),
        seq(field('bind', choice(':=', '=')), field('value', $._value)),
      ),
    ),

    tparams: $ => seq(token.immediate('<'), comma1($.tparam), '>'),   // `Box<T>` glued vs `a < b`
    tparam: $ => seq(field('name', $.ident), optional(seq(':', field('bound', $.ident)))),

    name_path: $ => sep1($.ident, token.immediate('.')),   // glued dotted name

    // a record holds DECLS (where `*` means pub); a block holds STATEMENTS (where
    // `*` means multiply). Splitting them keeps `*` unambiguous inside each brace.
    record: $ => seq('{', repeat(seq($.decl, optional(','))), '}'),   // commas optional
    block:  $ => seq('{', repeat($._stmt), '}'),
    _stmt: $ => choice($.let_, $._expr),
    let_: $ => prec(2, seq(field('name', $.ident),
                           optional(seq(':', field('type', $._type))),
                           field('bind', choice(':=', '=')), field('value', $._expr))),

    // ── types ───────────────────────────────────────────────────────────────
    _type: $ => choice($.record, $.fn_t, $.ptr_t, $.named_t),
    fn_t: $ => seq('(', optional(comma1($._type)), ')', $._type),   // (T, U) R — a signature
    ptr_t: $ => seq(field('dir', choice('Ptr', 'MutPtr', 'RawPtr')), '<', $._type, '>'),
    named_t: $ => seq(field('name', $.type_path), optional(seq('<', comma1($._type), '>'))),
    type_path: $ => sep1($.ident, '.'),

    // ── values ──────────────────────────────────────────────────────────────
    _value: $ => choice($.fn, $.sum, $.record, $._expr),
    fn: $ => prec(3, seq('(', optional(comma1($.param)), ')',
                         optional(field('ret', $._type)), field('body', $.block))),
    param: $ => seq(field('name', $.ident), ':', field('type', $._type)),
    sum: $ => prec.left(2, seq($.variant, repeat1(seq('|', $.variant)))),  // ≥2 → unambiguous
    variant: $ => seq(field('name', $.ident), optional(seq(':', field('payload', $._type)))),

    // ── expressions (dotted access is postfix `.`, never a multi-segment atom) ─
    _expr: $ => choice($.binary, $._post),
    _post: $ => choice($._atom, $.call, $.field, $.match),
    _atom: $ => choice($.paren, $.record_lit, $.integer, $.string, $.boolean, $.ident),

    call:  $ => prec.left(6, seq(field('fn', $._post), $.args)),
    field: $ => prec.left(6, seq(field('obj', $._post), '.', field('name', $.ident))),
    args:  $ => seq('(', optional(comma1($._expr)), ')'),

    match: $ => prec.left(6, seq(field('subj', $._post), '.', 'match',
                                 '{', comma1($.arm), optional(','), '}')),
    arm: $ => seq(field('pat', $.pattern), '=>', field('body', $._expr)),
    pattern: $ => choice($.ctor_pat, $.integer, $.boolean, '_'),
    ctor_pat: $ => seq(field('name', $.ident),
                       optional(seq('(', field('bind', $.ident), ')'))),

    record_lit: $ => prec(7, seq(field('type', $.ident),
                          '{', optional(seq(comma1($.field_init), optional(','))), '}')),
    field_init: $ => seq(field('name', $.ident), ':', field('value', $._expr)),

    binary: $ => choice(
      prec.left(1, seq($._expr, '||', $._expr)),
      prec.left(2, seq($._expr, '&&', $._expr)),
      prec.left(3, seq($._expr, choice('==', '<', '>', '<=', '>='), $._expr)),
      prec.left(4, seq($._expr, choice('+', '-'), $._expr)),
      prec.left(5, seq($._expr, '*', $._expr)),
    ),

    paren: $ => seq('(', $._expr, ')'),
    integer: $ => /\d+/,
    boolean: $ => choice('true', 'false'),
    string: $ => token(seq('"', /[^"]*/, '"')),
    ident: $ => /@?[A-Za-z_]\w*/,
  }
});
