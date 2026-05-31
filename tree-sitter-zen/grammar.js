// tree-sitter grammar for the Zen subset that holotype type-checks.
// Mirrors lantos1618/zenlang surface syntax: `Name: {..}` structs, `name = (..) Ret {..}`
// functions, `Ptr/MutPtr/RawPtr<T>` pointers, `{ a } = mod` imports.

const sep1   = (r, s) => seq(r, repeat(seq(s, r)));
const comma1 = (r)    => sep1(r, ',');

module.exports = grammar({
  name: 'zen',

  extras: $ => [/\s/, $.comment],     // whitespace (incl. newlines) is insignificant here
  word: $ => $.identifier,

  rules: {
    source_file: $ => repeat($._item),
    _item: $ => choice($.import, $.struct, $.enum, $.function, $.trait, $.impl, $.extern),

    // extern malloc = (n: i64) RawPtr<u8>   — bind a C symbol; no body
    extern: $ => seq('extern', field('name', $.identifier), '=',
                     '(', optional(comma1($.param)), ')', field('ret', $._type)),

    comment: $ => token(seq('//', /[^\n]*/)),

    // { a, b } = core.vec
    import: $ => seq('{', comma1($.identifier), '}', '=', $.module_path),
    module_path: $ => sep1($.identifier, '.'),

    // a declaration's own type parameters, each optionally bounded by a trait:
    //   Box<T>,  map<T, U>,  total<T: Area>
    type_params: $ => seq('<', comma1($.tparam), '>'),
    tparam: $ => seq(field('name', $.identifier),
                     optional(seq(':', field('bound', $.identifier)))),

    // trait Area { area: (Ptr<Self>) i32 }   — a named set of method signatures
    trait: $ => seq(optional('pub'), 'trait', field('name', $.identifier),
                    '{', comma1($.method_sig), optional(','), '}'),
    method_sig: $ => seq(field('name', $.identifier), ':',
                         '(', optional(comma1($._type)), ')', field('ret', $._type)),

    // impl Area for Vec { area = (v: Ptr<Vec>) i32 { ... } }
    impl: $ => seq('impl', field('trait', $.identifier), 'for', field('type', $.identifier),
                   '{', repeat($.function), '}'),

    // pub Vec: { len: i32, cap: i32 }   /   pub Box<T>: { val: T }
    struct: $ => seq(optional('pub'), field('name', $.identifier),
                     optional(field('tparams', $.type_params)), ':',
                     '{', comma1($.field), optional(','), '}'),
    field: $ => seq(field('name', $.identifier), ':', field('type', $._type)),

    // pub Opt<T>: None, Some(T)
    enum: $ => seq(optional('pub'), field('name', $.identifier),
                   optional(field('tparams', $.type_params)), ':',
                   comma1($.variant)),
    variant: $ => seq(field('name', $.identifier),
                      optional(seq('(', field('payload', $._type), ')'))),

    // pub area = (v: Ptr<Vec>) i32 { … }   — the return type may be omitted and inferred:
    // pub area = (v: Ptr<Vec>) { len(v) * cap(v) }
    function: $ => seq(optional('pub'), field('name', $.identifier),
                       optional(field('tparams', $.type_params)), '=',
                       '(', optional(comma1($.param)), ')',
                       optional(field('ret', $._type)), field('body', $.block)),
    param: $ => seq(field('name', $.identifier), ':', field('type', $._type)),

    _type: $ => choice($.primitive, $.pointer, $.named_type),
    primitive: $ => choice('i32', 'i64', 'u8', 'bool', 'void'),
    pointer: $ => seq(field('dir', choice('Ptr', 'MutPtr', 'RawPtr')),
                      '<', field('pointee', $._type), '>'),
    named_type: $ => seq(field('name', $.identifier),
                         optional(seq('<', comma1($._type), '>'))),

    block: $ => seq('{', repeat($._statement), '}'),
    _statement: $ => choice($.let_binding, $._expression),
    // x := expr  — a local binding (type inferred from the value)
    let_binding: $ => seq(field('name', $.identifier), ':=', field('value', $._expression)),
    // a leading-dot constructor `.Ok(x)` — an expression, so it works as a call
    // argument and match arm body too, not just a bare statement.
    enum_ctor: $ => seq('.', field('name', $.identifier), $.arguments),

    // a postfix chain: primary, then any number of (args) calls and .name accesses.
    // A "method call" is simply a call whose `fn` is a field_access — no special rule.
    _expression: $ => choice($.binary, $._unary),
    _unary: $ => choice($._primary, $.call, $.field_access, $.unary_op),
    unary_op: $ => prec(7, seq(field('op', '!'), $._unary)),   // logical not
    _primary: $ => choice($.parenthesized, $.match, $.enum_ctor, $.struct_literal, $.integer, $.boolean, $.string, $.identifier),

    // match subject { .Variant(x) => expr, .Other => expr, _ => expr }
    // The subject is a restricted expression so the `{` can't be mistaken for a
    // struct literal — wrap a struct-literal subject in parens if ever needed.
    // subject is an identifier or a parenthesized expression — keeps the `{`
    // unambiguous and sidesteps the struct-literal / left-recursion conflicts.
    match: $ => seq('match', field('subject', choice($.identifier, $.parenthesized)),
                    '{', comma1($.match_arm), optional(','), '}'),
    match_arm: $ => seq(field('pat', $.pattern), '=>', field('body', $._expression)),
    pattern: $ => choice($.ctor_pattern, $.literal_pattern, $.wildcard),
    ctor_pattern: $ => seq('.', field('name', $.identifier),
                           optional(seq('(', field('binding', $.identifier), ')'))),
    literal_pattern: $ => choice($.integer, $.boolean),   // match n { 0 => …, _ => … }
    wildcard: $ => '_',

    call:         $ => prec.left(4, seq(field('fn', $._unary), $.arguments)),
    field_access: $ => prec.left(4, seq(field('obj', $._unary), '.', field('name', $.identifier))),

    binary: $ => choice(
      prec.left(1, seq($._expression, '||', $._expression)),                       // bool -> bool
      prec.left(2, seq($._expression, '&&', $._expression)),
      prec.left(3, seq($._expression, choice('==', '<', '>', '<=', '>='), $._expression)),  // -> bool
      prec.left(4, seq($._expression, choice('+', '-'), $._expression)),           // numeric
      prec.left(5, seq($._expression, '*', $._expression)),
    ),

    struct_literal: $ => prec(5, seq(field('type', $.identifier),
                          '{', optional(seq(comma1($.field_init), optional(','))), '}')),
    field_init: $ => seq(field('name', $.identifier), ':', field('value', $._expression)),
    parenthesized: $ => seq('(', $._expression, ')'),
    arguments: $ => seq('(', optional(comma1($._expression)), ')'),

    integer: $ => /\d+/,
    boolean: $ => choice('true', 'false'),
    string: $ => token(seq('"', /[^"]*/, '"')),
    identifier: $ => /@?[A-Za-z_]\w*/,
  }
});
