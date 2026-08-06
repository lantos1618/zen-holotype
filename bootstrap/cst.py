"""tree-sitter parse tree -> the AST of `bootstrap/CONTRACT.md`.

This module owns the mapping from grammar node names to AST classes, which is
why it owns `grammar/grammar.js` too: they are one decision written twice.

**Positions and trivia are attached here or never** (`PLAN.md` 0.2). Every node
carries a half-open `Span` with 1-based lines and 1-based BYTE columns, whose
`file` is relative to the compilation root; comments and blank runs are
attached to the nearest enclosing declaration, statement, member, match arm or
variant. The formatter is `parse |> print` over those fields, and the LSP dies
without them, so nothing downstream may drop either.

THE NODE MAP is the block of constants below, and it is the only place a
grammar node name appears as a string. `tree-sitter generate` has not been run
against `grammar.js` yet; when it is and a rule gets renamed, this table is the
whole edit.

    grammar node                 ast

    source_file                  Module
    declaration                  Struct | Enum | Alias | Function | Const | Import
      value struct_body            Struct        `Vec*<T> = { .. }`
      value enum_body              Enum          `Shape = A(T) | B`
      value function              Function        `= sig {..}` sealed / `::=` default
      value function_signature    Function        `= sig` required / `::=` hook
      value member_expression      Import         `Res*, Ok* = std.core.result`
      value identifier|generic     Alias          `Alias = Shape`
      value anything else          Const          `json_pkg = Package(..)`
    impl_declaration             Impl
    struct_body                  -> (fields, consts) of the Struct
    member_declaration           Field | Const | Function
    enum_body / enum_variant     Variant
    variant_payload              -> Variant.payload
    declaration_statement        Struct | Enum | Function   (in a body; no `;`)
    let_statement                Let | ExprStmt(Binary("=", ..))
    expression_statement         ExprStmt
    block                        Block
    function                     Lambda          (in expression position)
    function_signature           FnType          (in type position)
    parameters / parameter       Param
    type_parameters / _parameter TParam
    type_bound                   -> TParam.bound (Union when `+` joins several)
    identifier                   Path (expr) | Named (type)
    generic_type                 Named
    array_type                   ArrayType
    union_type                   Union (flattened)
    unit                         Unit (type) | Literal("unit", "()") (expr)
    self_type                    Named("@Self") | Path("@Self")
    inferred_type                Infer
    variadic_type                Named("...")
    call_expression              Call | Try (`.try()`) | Match (`.match({..})`)
    arguments / named_argument   Arg
    record / record_field        Record (entries: Arg | Function)
    match_block / match_arm      Arm
    member_expression            Member
    index_expression             Index
    unary_expression             Unary
    binary_expression            Binary
    consume_expression           Consume
    meta_expression              MetaCall
    scope_expression             ScopeRef
    array_literal                ArrayLit
    fixed_array_expression       FixedArray
    number/string/char/boolean   Literal
    wildcard_pattern             PatWild
    destructure_pattern          PatVariant(name, binder)
    path_pattern                 PatVariant(name, None)
    literals in pattern position PatLit
    line_comment / block_comment Trivia (never a node)

Diagnostics are collected, never raised: one bad file must not stop the run.
"""

from __future__ import annotations

import bisect
import importlib
import importlib.util
import os
import sys

# --- sibling import --------------------------------------------------------
# `bootstrap/ast.py` shares its name with the standard library, so how it is
# reached depends on how the bootstrapper was started. Try the package form
# first (`python3 -m bootstrap.bootstrap`, the recommended one), then the
# script form, then the file itself.
def _load_ast():
    try:
        from . import ast as module  # type: ignore[attr-defined]

        return module
    except (ImportError, ValueError):
        pass
    try:
        module = importlib.import_module("ast")
        if hasattr(module, "Module") and hasattr(module, "PatVariant"):
            return module
    except ImportError:
        pass
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ast.py")
    spec = importlib.util.spec_from_file_location("zen_bootstrap_ast", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("zen_bootstrap_ast", module)
    spec.loader.exec_module(module)
    return module


def _load_lex():
    """`bootstrap/lex.py`, reached however this process was started — same
    three-way dance as `_load_ast`, and for the same reason."""
    try:
        from . import lex as module  # type: ignore[attr-defined]

        return module
    except (ImportError, ValueError):
        pass
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lex.py")
    spec = importlib.util.spec_from_file_location("zen_bootstrap_lex", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("zen_bootstrap_lex", module)
    spec.loader.exec_module(module)
    return module


A = _load_ast()
L = _load_lex()

Span = A.Span
Trivia = A.Trivia
Diag = A.Diag


# ===========================================================================
# THE NODE MAP — every grammar node name the walker knows, in one block.
# Nothing below this point spells a node name any other way.
# ===========================================================================

SOURCE_FILE = "source_file"

DECLARATION = "declaration"
DECLARATION_NAME = "declaration_name"
DECLARATION_STATEMENT = "declaration_statement"
EXPORT_MARKER = "export_marker"
IMPL_DECLARATION = "impl_declaration"

STRUCT_BODY = "struct_body"
MEMBER_DECLARATION = "member_declaration"
ENUM_BODY = "enum_body"
ENUM_VARIANT = "enum_variant"
VARIANT_PAYLOAD = "variant_payload"

BLOCK = "block"
LET_STATEMENT = "let_statement"
EXPRESSION_STATEMENT = "expression_statement"

FUNCTION = "function"
FUNCTION_SIGNATURE = "function_signature"
PARAMETERS = "parameters"
PARAMETER = "parameter"
TYPE_PARAMETERS = "type_parameters"
TYPE_PARAMETER = "type_parameter"
TYPE_BOUND = "type_bound"

IDENTIFIER = "identifier"
GENERIC_TYPE = "generic_type"
TYPE_ARGUMENTS = "type_arguments"
ARRAY_TYPE = "array_type"
UNION_TYPE = "union_type"
UNIT = "unit"
SELF_TYPE = "self_type"
INFERRED_TYPE = "inferred_type"
VARIADIC_TYPE = "variadic_type"

PARENTHESIZED_EXPRESSION = "parenthesized_expression"
SCOPE_EXPRESSION = "scope_expression"
META_EXPRESSION = "meta_expression"
TYPED_META_ARGUMENT = "typed_meta_argument"
ARRAY_LITERAL = "array_literal"
FIXED_ARRAY_EXPRESSION = "fixed_array_expression"
CALL_EXPRESSION = "call_expression"
ARGUMENTS = "arguments"
NAMED_ARGUMENT = "named_argument"
RECORD = "record"
RECORD_FIELD = "record_field"
MATCH_BLOCK = "match_block"
MATCH_ARM = "match_arm"
ARROW = "=>"  # the one anonymous token a diagnostic has to name
MEMBER_EXPRESSION = "member_expression"
INDEX_EXPRESSION = "index_expression"
UNARY_EXPRESSION = "unary_expression"
BINARY_EXPRESSION = "binary_expression"
CONSUME_EXPRESSION = "consume_expression"

NUMBER_LITERAL = "number_literal"
STRING_LITERAL = "string_literal"
CHAR_LITERAL = "char_literal"
BOOLEAN_LITERAL = "boolean_literal"

WILDCARD_PATTERN = "wildcard_pattern"
DESTRUCTURE_PATTERN = "destructure_pattern"
PATH_PATTERN = "path_pattern"

LINE_COMMENT = "line_comment"
BLOCK_COMMENT = "block_comment"
COMMENTS = (LINE_COMMENT, BLOCK_COMMENT)

ERROR = "ERROR"

# field names, same rule: spelled once
F_NAME = "name"
F_VALUE = "value"
F_TYPE = "type"
F_OPERATOR = "operator"
F_MUTABILITY = "mutability"
F_EXPORTED = "exported"
F_TYPE_PARAMETERS = "type_parameters"
F_TYPE_ARGUMENTS = "type_arguments"
F_PARAMETERS = "parameters"
F_RETURN_TYPE = "return_type"
F_BODY = "body"
F_TARGET = "target"
F_TRAIT = "trait"
F_METHOD = "method"
F_FUNCTION = "function"
F_ARGUMENTS = "arguments"
F_OBJECT = "object"
F_PROPERTY = "property"
F_ARRAY = "array"
F_INDEX = "index"
F_LEFT = "left"
F_RIGHT = "right"
F_OPERAND = "operand"
F_ELEMENT = "element"
F_LENGTH = "length"
F_PATTERN = "pattern"
F_BINDER = "binder"
F_PAYLOAD = "payload"
F_BOUND = "bound"
F_ARGUMENT = "argument"

# the two names the language reserves for the non-local-exit intrinsics.
# `.try()` is `Try`, not a Call; `.match({..})` is `Match`, not a Call.
TRY_METHOD = "try"
MATCH_METHOD = "match"
IMPL_METHOD = "impl"

# `Function.form`, keyed by (operator, has body) — DESIGN.md's method table.
FORM_BY_OPERATOR = {
    ("=", True): "sealed",
    ("=", False): "required",
    ("::=", True): "default",
    ("::=", False): "hook",
}

MUTABLE_MARKER = "::"

# TESTING.md: "Decide the depth limit and emit an error at it." Deeper than
# this is a diagnostic, never a crash. The deepest thing the corpus builds on
# purpose is ~560 levels; the `must-fail` fixture is 10,000.
MAX_NEST = 2000

# Nothing below nests: a declaration, a statement and a function each hold
# their nesting rather than being it, so the run of nested constructs a depth
# diagnostic names STARTS after one of these. That is what makes the arrow
# point at the outermost `(` of `v = ((((..` and at the outermost `{` of the
# statement, rather than at the function body that happens to enclose both.
NOT_NESTING = frozenset(
    (
        SOURCE_FILE,
        DECLARATION,
        DECLARATION_STATEMENT,
        LET_STATEMENT,
        EXPRESSION_STATEMENT,
        IMPL_DECLARATION,
        FUNCTION,
        FUNCTION_SIGNATURE,
        LINE_COMMENT,
        BLOCK_COMMENT,
    )
)

# where a MISSING node means "an expression belongs here"
EXPRESSION_HOLES = frozenset(
    (
        BINARY_EXPRESSION,
        UNARY_EXPRESSION,
        CONSUME_EXPRESSION,
        PARENTHESIZED_EXPRESSION,
        INDEX_EXPRESSION,
        MEMBER_EXPRESSION,
        ARGUMENTS,
        NAMED_ARGUMENT,
        ARRAY_LITERAL,
        LET_STATEMENT,
        EXPRESSION_STATEMENT,
        MATCH_ARM,
        RECORD_FIELD,
    )
)


# ===========================================================================
# tree-sitter, behind one guard
# ===========================================================================

_TREE_SITTER_HELP = (
    "bootstrap/cst.py needs the `tree_sitter` python package and a compiled "
    "Zen grammar.\n"
    "  pip install tree_sitter\n"
    "  cd grammar && npx tree-sitter generate && npx tree-sitter build -o zen.so\n"
    "Point ZEN_TREE_SITTER_LIB at the shared object if it is not at "
    "grammar/zen.so."
)

_LANGUAGE = None
_PARSER = None

GRAMMAR_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "grammar"
)


def load_language():
    """The compiled Zen grammar, however this machine happens to have it."""
    global _LANGUAGE
    if _LANGUAGE is not None:
        return _LANGUAGE
    try:
        import tree_sitter
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(_TREE_SITTER_HELP) from exc

    # 1. the packaged binding, if someone published one
    try:
        import tree_sitter_zen  # type: ignore

        _LANGUAGE = tree_sitter.Language(tree_sitter_zen.language())
        return _LANGUAGE
    except Exception:
        pass

    # 2. a shared object built from grammar/src/parser.c
    candidates = [
        os.environ.get("ZEN_TREE_SITTER_LIB"),
        os.path.join(GRAMMAR_DIR, "zen.so"),
        os.path.join(GRAMMAR_DIR, "build", "zen.so"),
    ]
    for path in candidates:
        if not path or not os.path.exists(path):
            continue
        for build in (
            lambda: tree_sitter.Language(path, "zen"),  # py-tree-sitter < 0.22
            lambda: tree_sitter.Language(_dlopen_language(path)),  # >= 0.22
        ):
            try:
                _LANGUAGE = build()
                return _LANGUAGE
            except Exception:
                continue
    raise RuntimeError(_TREE_SITTER_HELP)


def _dlopen_language(path):  # pragma: no cover - environment dependent
    import ctypes

    lib = ctypes.cdll.LoadLibrary(path)
    fn = getattr(lib, "tree_sitter_zen")
    fn.restype = ctypes.c_void_p
    return fn()


def parser():
    """One parser, however this binding spells "use this language".

    py-tree-sitter < 0.22 wants `set_language`; >= 0.22 wants the `language`
    property or the constructor. 0.21 ACCEPTS `Parser(language)` and quietly
    ignores it, so the constructor form is tried last, never first.
    """
    global _PARSER
    if _PARSER is None:
        import tree_sitter

        language = load_language()
        instance = tree_sitter.Parser()
        if hasattr(instance, "set_language"):
            instance.set_language(language)
        else:
            try:
                instance.language = language
            except (AttributeError, TypeError):  # pragma: no cover
                instance = tree_sitter.Parser(language)
        _PARSER = instance
    return _PARSER


# ===========================================================================
# trivia
# ===========================================================================


class _TriviaStore:
    """Every comment and every blank run in the file, claimed at most once.

    A node claims, as `leading`, every unclaimed piece that ends before it
    begins — so a comment attaches to the innermost declaration, statement,
    member, arm or variant that follows it — and, as `trailing`, one comment
    that starts after it on the same line. Anything nobody claims lands on the
    Module, where the formatter can still find it.
    """

    def __init__(self, source: bytes, file: str, root):
        self.file = file
        self.source = source
        self._line_starts = [0]
        for i, byte in enumerate(source):
            if byte == 0x0A:
                self._line_starts.append(i + 1)
        self.items: list = []  # (start_byte, end_byte, Trivia)
        self.used: list = []
        self._cursor = 0  # everything before this is claimed
        self._collect(source, root)

    # -- construction --

    def _pos(self, byte: int) -> tuple:
        row = bisect.bisect_right(self._line_starts, byte) - 1
        return (row + 1, byte - self._line_starts[row] + 1)

    def _span(self, start: int, end: int) -> Span:
        return Span(self.file, self._pos(start), self._pos(end))

    def _add(self, start: int, end: int, kind: str) -> None:
        text = self.source[start:end].decode("utf-8", "replace")
        self.items.append((start, end, Trivia(self._span(start, end), text, kind)))
        self.used.append(False)

    def _collect(self, source: bytes, root) -> None:
        # iterative: a file of 10,000 nested parens is a `must-fail` fixture,
        # not a stack overflow (TESTING.md, "deep nesting")
        leaves: list = []
        stack = [root]
        while stack:
            node = stack.pop()
            if node.child_count == 0:
                leaves.append(node)
                continue
            stack.extend(reversed(node.children))
        cursor = 0
        for leaf in leaves:
            gap = source[cursor : leaf.start_byte]
            # a run of >= 2 newlines between tokens is one blank-line trivia
            if gap.count(b"\n") >= 2:
                self._add(cursor, leaf.start_byte, "blank")
            if leaf.type in COMMENTS:
                self._add(leaf.start_byte, leaf.end_byte, leaf.type)
            cursor = max(cursor, leaf.end_byte)

    # -- claiming --

    def _advance(self) -> None:
        while self._cursor < len(self.items) and self.used[self._cursor]:
            self._cursor += 1

    def leading(self, start_byte: int) -> tuple:
        out = []
        self._advance()
        for i in range(self._cursor, len(self.items)):
            start, end, trivia = self.items[i]
            if start >= start_byte:
                break
            if self.used[i] or end > start_byte:
                continue
            self.used[i] = True
            out.append(trivia)
        self._advance()
        return tuple(out)

    def trailing(self, end_byte: int, end_line: int) -> tuple:
        self._advance()
        for i in range(self._cursor, len(self.items)):
            start, _end, trivia = self.items[i]
            if start < end_byte or self.used[i]:
                continue
            if trivia.kind == "blank":
                return ()
            if trivia.span.start[0] != end_line:
                return ()
            self.used[i] = True
            return (trivia,)
        return ()

    def leftovers(self) -> tuple:
        out = []
        for i, (_s, _e, trivia) in enumerate(self.items):
            if not self.used[i]:
                self.used[i] = True
                out.append(trivia)
        return tuple(out)


def _nests(node) -> bool:
    """Whether this node is one LEVEL of a nested run, rather than the thing
    that holds one. A function's body is the function, not a level inside it,
    which is what makes the outermost `{` of `main`'s body a boundary and the
    `{` after it the start of a run."""
    if node.type in NOT_NESTING:
        return False
    parent = node.parent
    return not (node.type == BLOCK and parent is not None and parent.type == FUNCTION)


def outermost(node):
    """Where a too-deep run STARTS. A depth diagnostic anchored at level 2001
    points 2000 levels past the mistake; the fix goes at the outermost `(` or
    `{`, so that is what it names."""
    top = node
    parent = node.parent
    while parent is not None and _nests(parent):
        top = parent
        parent = parent.parent
    return top


# ===========================================================================
# the walker
# ===========================================================================


class Converter:
    def __init__(self, source: bytes, file: str, root):
        self.source = source
        self.file = file
        self.diags: list = []
        self.depth = 0
        self._too_deep = False
        self.trivia = _TriviaStore(source, file, root)

    def deep(self, node) -> bool:
        """One diagnostic for a file that nests past MAX_NEST, then silence:
        "one syntax error must not cascade into fifty" (TESTING.md)."""
        if self.depth <= MAX_NEST:
            return False
        if not self._too_deep:
            self._too_deep = True
            self.error(
                outermost(node), f"nesting too deep: nests deeper than {MAX_NEST}"
            )
        return True

    # -- primitives --

    def span(self, node) -> Span:
        start, end = node.start_point, node.end_point
        return Span(self.file, (start[0] + 1, start[1] + 1), (end[0] + 1, end[1] + 1))

    def text(self, node) -> str:
        if node is None:
            return ""
        return self.source[node.start_byte : node.end_byte].decode("utf-8", "replace")

    def error(self, node, message: str, notes: tuple = ()) -> None:
        self.diags.append(Diag(self.span(node), message, notes))

    def lead(self, node) -> tuple:
        return self.trivia.leading(node.start_byte)

    def trail(self, node) -> tuple:
        return self.trivia.trailing(node.end_byte, node.end_point[0] + 1)

    def kids(self, node) -> list:
        """Named children, minus comments and error nodes."""
        if node is None:
            return []
        return [
            c
            for c in node.children
            if c.is_named and c.type not in COMMENTS and c.type != ERROR
        ]

    def field(self, node, name: str):
        return None if node is None else node.child_by_field_name(name)

    def fields(self, node, name: str) -> list:
        if node is None:
            return []
        return [c for c in node.children_by_field_name(name) if c.type != ERROR]

    # ===================================================================
    # module
    # ===================================================================

    def module(self, root, name: str, path: str):
        decls: list = []
        imports: list = []
        for child in self.kids(root):
            item = self.module_item(child)
            if item is None:
                continue
            if isinstance(item, A.Import):
                imports.append(item)
            else:
                decls.append(item)
        span = self.span(root)
        return A.Module(
            name,
            path,
            tuple(decls),
            tuple(imports),
            span=span,
            leading=(),
            trailing=self.trivia.leftovers(),
        )

    def module_item(self, node):
        if node.type == DECLARATION:
            return self.declaration(node)
        if node.type == IMPL_DECLARATION:
            return self.impl(node)
        self.error(node, f"unexpected {node.type} at module level")
        return None

    # ===================================================================
    # declarations
    #
    # ONE grammar rule; what it declares is read off the shape of its value
    # (grammar.js R1a). This function is that table.
    # ===================================================================

    def declaration(self, node):
        leading = self.lead(node)
        names = self.fields(node, F_NAME)
        annotation = self.field(node, F_TYPE)
        operator = self.text(self.field(node, F_OPERATOR))
        value = self.field(node, F_VALUE)
        span = self.span(node)

        if not names or value is None:
            self.error(node, "malformed declaration")
            return None

        kind = value.type
        if len(names) > 1 and kind not in (MEMBER_EXPRESSION, IDENTIFIER):
            self.error(node, "only an import binds several names at once")

        result = None
        if kind == STRUCT_BODY:
            result = self.struct(names[0], value, span)
        elif kind == ENUM_BODY:
            result = self.enum(names[0], value, span)
        elif kind in (FUNCTION, FUNCTION_SIGNATURE):
            result = self.function(names[0], operator, value, span)
        elif kind == MEMBER_EXPRESSION and self.dotted_path(value) is not None:
            result = self.import_(names, value, span)
        elif kind in (IDENTIFIER, GENERIC_TYPE):
            name, exported, tparams = self.declaration_name(names[0])
            if tparams:
                self.error(names[0], "a type alias takes no type parameters")
            result = A.Alias(name, exported, self.type(value), span=span)
        else:
            name, exported, tparams = self.declaration_name(names[0])
            if tparams:
                self.error(names[0], "a constant takes no type parameters")
            result = A.Const(
                name,
                exported,
                self.type(annotation) if annotation is not None else None,
                self.expr(value),
                span=span,
            )

        if result is None:
            return None
        return A.replace(result, leading=leading, trailing=self.trail(node))

    def declaration_statement(self, node):
        """A declaration inside a body. Same shapes, minus the ones that would
        be a statement — and, like every declaration, no `;` (grammar.js R2)."""
        leading = self.lead(node)
        name_node = self.field(node, F_NAME)
        operator = self.text(self.field(node, F_OPERATOR))
        value = self.field(node, F_VALUE)
        span = self.span(node)
        if name_node is None or value is None:
            self.error(node, "malformed declaration")
            return None
        if value.type == STRUCT_BODY:
            result = self.struct(name_node, value, span)
        elif value.type == ENUM_BODY:
            result = self.enum(name_node, value, span)
        else:
            result = self.function(name_node, operator, value, span)
        if result is None:
            return None
        return A.replace(result, leading=leading, trailing=self.trail(node))

    def declaration_name(self, node) -> tuple:
        """-> (name, exported, tparams)"""
        if node.type != DECLARATION_NAME:
            return (self.text(node), False, ())
        name = self.text(self.field(node, F_NAME))
        exported = self.field(node, F_EXPORTED) is not None
        tparams = self.type_parameters(self.field(node, F_TYPE_PARAMETERS))
        return (name, exported, tparams)

    def struct(self, name_node, body, span):
        name, exported, tparams = self.declaration_name(name_node)
        fields: list = []
        consts: list = []
        for member in self.kids(body):
            if member.type != MEMBER_DECLARATION:
                self.error(member, f"unexpected {member.type} in a struct body")
                continue
            item = self.member(member)
            if item is None:
                continue
            (consts if isinstance(item, A.Const) else fields).append(item)
        return A.Struct(name, exported, tparams, tuple(fields), tuple(consts), span=span)

    def member(self, node):
        """A struct member is a field, a constant, or a method.

            width: f64               Field(mutable=False)
            data :: Vec<u8>          Field(mutable=True)
            verbose :: bool = false  Field(mutable=True, default=..)   [R4]
            MAX: i32 = 2147483647    Const                             [R4]
            add* = sig {..}          Function(form="sealed")
            free* ::= sig            Function(form="hook")

        `:` plus a value is a constant, `::` plus a value is a field with a
        default: that is the only difference, and it is R4 in grammar.js.
        """
        leading = self.lead(node)
        name, exported, tparams = self.declaration_name(self.field(node, F_NAME))
        span = self.span(node)
        mutability = self.field(node, F_MUTABILITY)
        operator = self.field(node, F_OPERATOR)
        type_node = self.field(node, F_TYPE)
        value_node = self.field(node, F_VALUE)

        if mutability is not None:
            mutable = self.text(mutability) == MUTABLE_MARKER
            ty = self.type(type_node)
            if value_node is not None and not mutable:
                result = A.Const(name, exported, ty, self.expr(value_node), span=span)
            else:
                default = None if value_node is None else self.expr(value_node)
                result = A.Field(name, exported, ty, mutable, default, span=span)
        elif value_node is not None and value_node.type in (FUNCTION, FUNCTION_SIGNATURE):
            result = self.function(
                self.field(node, F_NAME), self.text(operator), value_node, span
            )
        elif value_node is not None:
            result = A.Const(name, exported, None, self.expr(value_node), span=span)
        else:
            self.error(node, "malformed struct member")
            return None
        if tparams and isinstance(result, (A.Field, A.Const)):
            self.error(node, "only a function member takes type parameters")
        return A.replace(result, leading=leading, trailing=self.trail(node))

    def enum(self, name_node, body, span):
        name, exported, tparams = self.declaration_name(name_node)
        variants = []
        for child in self.kids(body):
            if child.type != ENUM_VARIANT:
                self.error(child, f"unexpected {child.type} in an enum")
                continue
            variants.append(self.variant(child))
        return A.Enum(name, exported, tparams, tuple(variants), span=span)

    def variant(self, node):
        leading = self.lead(node)
        name = self.text(self.field(node, F_NAME))
        payload_node = self.field(node, F_PAYLOAD)
        payload = None
        if payload_node is not None:
            payload = self.type(self.field(payload_node, F_TYPE))
        return A.Variant(
            name,
            payload,
            span=self.span(node),
            leading=leading,
            trailing=self.trail(node),
        )

    def function(self, name_node, operator: str, value, span):
        name, exported, name_tparams = self.declaration_name(name_node)
        value_tparams = self.type_parameters(self.field(value, F_TYPE_PARAMETERS))
        if name_tparams and value_tparams:
            self.error(
                value,
                "type parameters on both sides of the `=`; write them once",
            )
        tparams = name_tparams + value_tparams
        params = self.parameters(self.field(value, F_PARAMETERS), "declaration")
        ret_node = self.field(value, F_RETURN_TYPE)
        ret = self.type(ret_node) if ret_node is not None else A.Unit(span=span)
        body_node = self.field(value, F_BODY)
        body = None if body_node is None else self.block(body_node)
        form = FORM_BY_OPERATOR[(operator or "=", body is not None)]
        return A.Function(name, exported, tparams, params, ret, body, form, span=span)

    def import_(self, name_nodes, value, span):
        names = []
        for name_node in name_nodes:
            name, exported, tparams = self.declaration_name(name_node)
            if tparams:
                self.error(name_node, "an import binds a name, not a generic")
            names.append((name, exported))
        return A.Import(tuple(names), self.dotted_path(value), span=span)

    def dotted_path(self, node):
        """`std.core.result` -> "std.core.result"; None when the chain is not
        a plain dotted path (which makes it an ordinary expression)."""
        parts = []
        while node is not None and node.type == MEMBER_EXPRESSION:
            parts.append(self.text(self.field(node, F_PROPERTY)))
            node = self.field(node, F_OBJECT)
        if node is None or node.type != IDENTIFIER:
            return None
        parts.append(self.text(node))
        return ".".join(reversed(parts))

    def impl(self, node):
        leading = self.lead(node)
        method = self.text(self.field(node, F_METHOD))
        if method != IMPL_METHOD:
            self.error(node, f"`{method}` is not a declaration; only `.impl` is")
            return None
        target = self.text(self.field(node, F_TARGET))
        trait = self.text(self.field(node, F_TRAIT))
        entries = self.record_entries(self.field(node, F_BODY))
        return A.Impl(
            target,
            trait,
            entries,
            span=self.span(node),
            leading=leading,
            trailing=self.trail(node),
        )

    # ===================================================================
    # parameters and type parameters
    # ===================================================================

    def parameters(self, node, form: str) -> tuple:
        """`form` is "declaration", "type" or "closure".

        A parameter with no `:` is a hole, but WHICH hole depends on where the
        list is. `(a, b) i32` on a declaration is missing its types; `(i32,
        i32) i32` in type position is missing its NAMES — DESIGN.md's
        overloading section: "Function types must name their parameters." The
        two read identically to the grammar and must not read identically to
        the user. Only a closure infers either (grammar.js D13).
        """
        out = []
        for child in self.kids(node):
            if child.type != PARAMETER:
                continue
            name = self.text(self.field(child, F_NAME))
            mutability = self.field(child, F_MUTABILITY)
            type_node = self.field(child, F_TYPE)
            if type_node is None and form == "type":
                self.error(
                    child,
                    f"expected a parameter name: a function type must name its "
                    f"parameters, and `{name}` is a type where the name belongs",
                )
            elif type_node is None and form == "declaration":
                self.error(
                    child,
                    f"parameter `{name}` needs a type: "
                    "only a closure infers its parameter types",
                )
            out.append(
                A.Param(
                    name,
                    None if type_node is None else self.type(type_node),
                    mutability is not None
                    and self.text(mutability) == MUTABLE_MARKER,
                    span=self.span(child),
                    leading=self.lead(child),
                    trailing=self.trail(child),
                )
            )
        return tuple(out)

    def type_parameters(self, node) -> tuple:
        out = []
        for child in self.kids(node):
            if child.type != TYPE_PARAMETER:
                continue
            bound_node = self.field(child, F_BOUND)
            out.append(
                A.TParam(
                    self.text(self.field(child, F_NAME)),
                    self.bound(bound_node),
                    span=self.span(child),
                )
            )
        return tuple(out)

    def bound(self, node):
        """`Eq + Hash` has no node in CONTRACT.md; a several-bound list is
        carried as a `Union` and is an INTERSECTION. Announced, not smuggled."""
        if node is None:
            return None
        types = [self.type(c) for c in self.kids(node)]
        if not types:
            return None
        if len(types) == 1:
            return types[0]
        return A.Union(tuple(types), span=self.span(node))

    # ===================================================================
    # types
    # ===================================================================

    def type(self, node):
        if node is None:
            return None
        self.depth += 1
        try:
            return None if self.deep(node) else self._type(node)
        finally:
            self.depth -= 1

    def _type(self, node):
        kind = node.type
        span = self.span(node)
        if kind == IDENTIFIER:
            return A.Named(self.text(node), (), span=span)
        if kind == SELF_TYPE:
            return A.Named("@Self", (), span=span)
        if kind == VARIADIC_TYPE:
            return A.Named("...", (), span=span)
        if kind == GENERIC_TYPE:
            args = tuple(
                self.type(c) for c in self.kids(self.field(node, F_ARGUMENTS))
            )
            return A.Named(self.text(self.field(node, F_NAME)), args, span=span)
        if kind == ARRAY_TYPE:
            return A.ArrayType(
                self.type(self.field(node, F_ELEMENT)),
                self.expr(self.field(node, F_LENGTH)),
                span=span,
            )
        if kind == UNION_TYPE:
            return A.Union(tuple(self.union_members(node)), span=span)
        if kind == UNIT:
            return A.Unit(span=span)
        if kind == INFERRED_TYPE:
            return A.Infer(span=span)
        if kind == FUNCTION_SIGNATURE:
            ret_node = self.field(node, F_RETURN_TYPE)
            return A.FnType(
                self.parameters(self.field(node, F_PARAMETERS), "type"),
                self.type(ret_node) if ret_node is not None else A.Unit(span=span),
                span=span,
            )
        self.error(node, f"{kind} is not a type")
        return A.Infer(span=span)

    def union_members(self, node):
        """Flat, never nested — CONTRACT.md says so about `Union`."""
        for side in (self.field(node, F_LEFT), self.field(node, F_RIGHT)):
            if side is None:
                continue
            if side.type == UNION_TYPE:
                yield from self.union_members(side)
            else:
                yield self.type(side)

    # ===================================================================
    # statements and blocks
    # ===================================================================

    def block(self, node):
        self.depth += 1
        try:
            if self.deep(node):
                return A.Block((), None, span=self.span(node))
            return self._block(node)
        finally:
            self.depth -= 1

    def _block(self, node):
        stmts = []
        tail = self.field(node, F_VALUE)
        for child in self.kids(node):
            if tail is not None and child.id == tail.id:
                continue
            stmt = self.statement(child)
            if stmt is not None:
                stmts.append(stmt)
        return A.Block(
            tuple(stmts),
            None if tail is None else self.expr(tail),
            span=self.span(node),
        )

    def statement(self, node):
        kind = node.type
        if kind == DECLARATION_STATEMENT:
            return self.declaration_statement(node)
        if kind == LET_STATEMENT:
            return self.let(node)
        if kind == EXPRESSION_STATEMENT:
            leading = self.lead(node)
            inner = self.kids(node)
            if not inner:
                self.error(node, "empty statement")
                return None
            return A.ExprStmt(
                self.expr(inner[0]),
                span=self.span(node),
                leading=leading,
                trailing=self.trail(node),
            )
        if kind == BLOCK:
            leading = self.lead(node)
            return A.replace(
                self.block(node), leading=leading, trailing=self.trail(node)
            )
        self.error(node, f"{kind} is not a statement")
        return None

    def let(self, node):
        leading = self.lead(node)
        target = self.field(node, F_TARGET)
        annotation = self.field(node, F_TYPE)
        operator = self.text(self.field(node, F_OPERATOR))
        value = self.expr(self.field(node, F_VALUE))
        span = self.span(node)
        if target.type == IDENTIFIER:
            result = A.Let(
                self.text(target),
                self.type(annotation) if annotation is not None else None,
                operator == "::=",
                value,
                span=span,
            )
        else:
            # `self.len = self.len + 1;` — CONTRACT.md has no assignment node,
            # so an assignment is a Binary whose operator is `=`. Announced.
            if operator == "::=":
                self.error(node, "`::=` declares a binding; assignment is `=`")
            if annotation is not None:
                self.error(node, "an assignment target takes no type")
            result = A.ExprStmt(
                A.Binary("=", self.expr(target), value, span=span), span=span
            )
        return A.replace(result, leading=leading, trailing=self.trail(node))

    # ===================================================================
    # expressions
    # ===================================================================

    def expr(self, node):
        if node is None:
            return None
        self.depth += 1
        try:
            return None if self.deep(node) else self._expr(node)
        finally:
            self.depth -= 1

    def _expr(self, node):
        kind = node.type
        span = self.span(node)

        if kind == IDENTIFIER:
            return A.Path(self.text(node), span=span)
        if kind == SELF_TYPE:
            return A.Path("@Self", span=span)
        if kind == SCOPE_EXPRESSION:
            return A.ScopeRef(span=span)
        if kind == NUMBER_LITERAL:
            text = self.text(node)
            return A.Literal("float" if "." in text else "int", text, span=span)
        if kind == STRING_LITERAL:
            return A.Literal("str", self.text(node), span=span)
        if kind == CHAR_LITERAL:
            return A.Literal("char", self.text(node), span=span)
        if kind == BOOLEAN_LITERAL:
            return A.Literal("bool", self.text(node), span=span)
        if kind == UNIT:
            # `()` in expression position. CONTRACT.md has no unit node, so it
            # is a literal whose kind is "unit". Announced.
            return A.Literal("unit", "()", span=span)
        if kind == PARENTHESIZED_EXPRESSION:
            # CONTRACT.md has no Paren node: the printer re-inserts parens from
            # precedence. Announced.
            inner = self.kids(node)
            return self.expr(inner[0]) if inner else None
        if kind == META_EXPRESSION:
            return self.meta(node)
        if kind == ARRAY_LITERAL:
            return A.ArrayLit(
                tuple(self.expr(c) for c in self.kids(node)), span=span
            )
        if kind == FIXED_ARRAY_EXPRESSION:
            return A.FixedArray(
                self.type(self.field(node, F_TYPE)),
                tuple(
                    a.value
                    for a in self.arguments(self.field(node, F_ARGUMENTS))
                ),
                span=span,
            )
        if kind == FUNCTION:
            ret_node = self.field(node, F_RETURN_TYPE)
            if self.field(node, F_TYPE_PARAMETERS) is not None:
                self.error(node, "a closure takes no type parameters")
            return A.Lambda(
                self.parameters(self.field(node, F_PARAMETERS), "closure"),
                self.type(ret_node) if ret_node is not None else None,
                self.block(self.field(node, F_BODY)),
                span=span,
            )
        if kind == CALL_EXPRESSION:
            return self.call(node)
        if kind == MEMBER_EXPRESSION:
            return A.Member(
                self.expr(self.field(node, F_OBJECT)),
                self.text(self.field(node, F_PROPERTY)),
                span=span,
            )
        if kind == INDEX_EXPRESSION:
            return A.Index(
                self.expr(self.field(node, F_ARRAY)),
                self.expr(self.field(node, F_INDEX)),
                span=span,
            )
        if kind == UNARY_EXPRESSION:
            return A.Unary(
                self.text(self.field(node, F_OPERATOR)),
                self.expr(self.field(node, F_OPERAND)),
                span=span,
            )
        if kind == BINARY_EXPRESSION:
            # every binary operator is left-associative (grammar.js D1), so a
            # long chain is a long LEFT spine. Fold it iteratively: `0 + 1 +
            # 1 + ..` with 10,000 terms is a corpus program (a 10MB single
            # line, TESTING.md), not a stack overflow. Only genuine structural
            # nesting counts against MAX_NEST.
            spine = []
            left = node
            while left is not None and left.type == BINARY_EXPRESSION:
                spine.append(left)
                left = self.field(left, F_LEFT)
            result = self.expr(left)
            for step in reversed(spine):
                result = A.Binary(
                    self.text(self.field(step, F_OPERATOR)),
                    result,
                    self.expr(self.field(step, F_RIGHT)),
                    span=self.span(step),
                )
            return result
        if kind == CONSUME_EXPRESSION:
            return A.Consume(self.expr(self.field(node, F_VALUE)), span=span)
        if kind == RECORD:
            return A.Record(self.record_entries(node), span=span)
        if kind == FUNCTION_SIGNATURE:
            self.error(node, "a function signature is a type, not a value")
            return None
        self.error(node, f"{kind} is not an expression")
        return None

    def meta(self, node):
        argument = self.field(node, F_ARGUMENT)
        span = self.span(node)
        if argument is not None and argument.type == TYPED_META_ARGUMENT:
            # `@meta(self: @Self)` — DESIGN.md admits three readings and settles
            # none (A-META-ARG). CONTRACT.md lets MetaCall.arg be a Type, so the
            # type is what is kept and the name is dropped.
            return A.MetaCall(self.type(self.field(argument, F_TYPE)), span=span)
        return A.MetaCall(self.expr(argument), span=span)

    def call(self, node):
        span = self.span(node)
        callee_node = self.field(node, F_FUNCTION)
        targs_node = self.field(node, F_TYPE_ARGUMENTS)
        args_node = self.field(node, F_ARGUMENTS)
        raw_args = self.kids(args_node)

        if callee_node is not None and callee_node.type == MEMBER_EXPRESSION:
            method = self.text(self.field(callee_node, F_PROPERTY))
            base_node = self.field(callee_node, F_OBJECT)
            # `A.impl(B, {..})` is a call that DECLARES, and DESIGN.md writes it
            # only at module level. In statement position it would have to say
            # what its scope is, and nothing does.
            if method == IMPL_METHOD:
                self.error(
                    node,
                    "`.impl` declares an impl, so it is legal only at module "
                    "level, never inside a body",
                )
                return None
            # `.try()` is the non-local-exit intrinsic, not a method call
            if method == TRY_METHOD and not raw_args and targs_node is None:
                return A.Try(self.expr(base_node), span=span)
            # `.match({ pat => expr, .. })`
            if (
                method == MATCH_METHOD
                and targs_node is None
                and len(raw_args) == 1
                and raw_args[0].type == MATCH_BLOCK
            ):
                return A.Match(
                    self.expr(base_node), self.arms(raw_args[0]), span=span
                )

        targs = tuple(self.type(c) for c in self.kids(targs_node))
        return A.Call(
            self.expr(callee_node), targs, self.arguments(args_node), span=span
        )

    def arguments(self, node) -> tuple:
        out = []
        for child in self.kids(node):
            span = self.span(child)
            if child.type == NAMED_ARGUMENT:
                out.append(
                    A.Arg(
                        self.text(self.field(child, F_NAME)),
                        self.expr(self.field(child, F_VALUE)),
                        span=span,
                    )
                )
            elif child.type == RECORD:
                out.append(
                    A.Arg(None, A.Record(self.record_entries(child), span=span), span=span)
                )
            elif child.type == MATCH_BLOCK:
                self.error(child, "match arms outside `.match`")
            else:
                out.append(A.Arg(None, self.expr(child), span=span))
        return tuple(out)

    def record_entries(self, node) -> tuple:
        """The `{..}` of `A.impl(B, {..})` and of `b.exe("x", {..})`.

        `name: value` supplies a value (`Arg`); `name = sig {..}` /
        `name ::= sig {..}` supplies a method (`Function`, carrying its form).
        """
        out = []
        for child in self.kids(node):
            if child.type != RECORD_FIELD:
                self.error(child, f"unexpected {child.type} in a record")
                continue
            leading = self.lead(child)
            name_node = self.field(child, F_NAME)
            operator = self.field(child, F_OPERATOR)
            value_node = self.field(child, F_VALUE)
            span = self.span(child)
            if (
                operator is not None
                and value_node is not None
                and value_node.type in (FUNCTION, FUNCTION_SIGNATURE)
            ):
                entry = self.function(
                    name_node, self.text(operator), value_node, span
                )
            else:
                name, exported, _tparams = self.declaration_name(name_node)
                if exported:
                    self.error(child, "a supplied field is not exported here")
                entry = A.Arg(name, self.expr(value_node), span=span)
            out.append(A.replace(entry, leading=leading, trailing=self.trail(child)))
        return tuple(out)

    # ===================================================================
    # match
    # ===================================================================

    def arms(self, node) -> tuple:
        out = []
        for child in self.kids(node):
            if child.type != MATCH_ARM:
                self.error(child, f"unexpected {child.type} in match arms")
                continue
            leading = self.lead(child)
            value_node = self.field(child, F_VALUE)
            body = (
                self.block(value_node)
                if value_node is not None and value_node.type == BLOCK
                else self.expr(value_node)
            )
            out.append(
                A.Arm(
                    self.pattern(self.field(child, F_PATTERN)),
                    body,
                    span=self.span(child),
                    leading=leading,
                    trailing=self.trail(child),
                )
            )
        return tuple(out)

    def pattern(self, node):
        if node is None:
            return None
        kind = node.type
        span = self.span(node)
        if kind == WILDCARD_PATTERN:
            return A.PatWild(span=span)
        if kind == PATH_PATTERN:
            return A.PatVariant(self.text(node), None, span=span)
        if kind == DESTRUCTURE_PATTERN:
            return A.PatVariant(
                self.text(self.field(node, F_NAME)),
                self.binder(self.field(node, F_BINDER)),
                span=span,
            )
        if kind == NUMBER_LITERAL:
            text = self.text(node)
            return A.PatLit("float" if "." in text else "int", text, span=span)
        if kind == STRING_LITERAL:
            return A.PatLit("str", self.text(node), span=span)
        if kind == CHAR_LITERAL:
            return A.PatLit("char", self.text(node), span=span)
        if kind == BOOLEAN_LITERAL:
            return A.PatLit("bool", self.text(node), span=span)
        self.error(node, f"{kind} is not a pattern")
        return A.PatWild(span=span)

    def binder(self, node):
        """`PatVariant.binder` is a NAME whenever one is written — `Ok(n)`,
        `Ok(_)`, and `Left(Blank)`, which is a name until sema knows whether
        `Blank` is a variant. A nested pattern (`Left(Full(n))`) has no name to
        give, so the binder is the inner Pattern NODE. CONTRACT.md types this
        field `str | None`; carrying a node here widens it, and that is
        announced rather than smuggled."""
        if node is None:
            return None
        if node.type == WILDCARD_PATTERN:
            return "_"
        if node.type == PATH_PATTERN and "." not in self.text(node):
            return self.text(node)
        return self.pattern(node)


# ===========================================================================
# entry points
# ===========================================================================


def _line_starts(source: bytes) -> list:
    starts = [0]
    for i, byte in enumerate(source):
        if byte == 0x0A:
            starts.append(i + 1)
    return starts


def _at(starts: list, byte: int) -> tuple:
    """A byte offset as (1-based line, 1-based BYTE column)."""
    row = bisect.bisect_right(starts, byte) - 1
    return (row + 1, byte - starts[row] + 1)


def _lex_diags(source: bytes, file: str) -> list:
    """`lex.py` scans the same bytes first, because tree-sitter parses without
    diagnosing: an ERROR node carries no message and often no useful span. Its
    offsets become Spans here — this is the only place lexical offsets meet the
    line table."""
    _tokens, raw = L.scan(source)
    if not raw:
        return []
    starts = _line_starts(source)
    out = []
    for start, end, message, notes in raw:
        out.append(
            Diag(
                Span(file, _at(starts, start), _at(starts, end)),
                message,
                tuple(
                    (Span(file, _at(starts, s), _at(starts, e)), text)
                    for s, e, text in notes
                ),
            )
        )
    return out


def _point(point) -> tuple:
    return (point[0] + 1, point[1] + 1)


def _arm_arrow(node, parent):
    """An ERROR sitting directly in a match block is an arm the parser could
    not read. When it holds a pattern and then more tokens with no `=>` among
    them, the `=>` is what is missing, and it belongs in front of the arm's
    body — which is where the fix goes, not where the arm began."""
    if parent is None or parent.type != MATCH_BLOCK:
        return None
    kids = list(node.children)
    if len(kids) < 2 or any(c.type == ARROW for c in kids):
        return None
    return kids[1]


def _dangling_bar(node, source: bytes):
    """A `|` promises another variant. When the name after it is MISSING, the
    parser resumes at the next declaration and reports the hole there — so the
    diagnostic lands on the line BELOW the mistake, naming a token the author
    did not write. The bar is where the fix goes, so scan back to it."""
    if not node.is_missing or node.type != "identifier":
        return None
    i = node.start_byte
    while i > 0 and source[i - 1 : i].isspace():
        i -= 1
    return i - 1 if source[i - 1 : i] == b"|" else None


def _syntax_diag(node, parent, file: str, source: bytes):
    """`parent` is threaded rather than read off the node: py-tree-sitter
    reports a MISSING leaf's parent as the token before it."""
    span = Span(file, _point(node.start_point), _point(node.end_point))
    if node.is_missing:
        bar = _dangling_bar(node, source)
        if bar is not None:
            starts = _line_starts(source)
            at = _at(starts, bar)
            return Diag(Span(file, at, _at(starts, bar + 1)),
                        "expected variant: a `|` promises another one")
        if parent is not None and parent.type in EXPRESSION_HOLES:
            return Diag(span, "expected expression")
        return Diag(span, f"expected `{node.type}`")
    if not source[node.end_byte :].strip():
        # the error runs to the end of the file: the text simply stops, so the
        # position that names the mistake is where it stops
        end = _point(node.end_point)
        return Diag(
            Span(file, end, end),
            "unexpected end of file: this declaration is not finished",
        )
    body = _arm_arrow(node, parent)
    if body is not None:
        return Diag(
            Span(file, _point(body.start_point), _point(body.end_point)),
            "expected `=>`: a match arm is `pattern => expr`",
        )
    text = source[node.start_byte : node.end_byte].decode("utf-8", "replace")
    head = text.strip().splitlines()[0][:40] if text.strip() else ""
    return Diag(span, f"syntax error near `{head}`")


def _syntax_diags(root, file: str, source: bytes) -> list:
    """One diagnostic per ERROR / MISSING node. TESTING.md: one syntax error
    must not cascade into fifty, so only the outermost is reported."""
    out = []
    stack = [(root, None)]
    while stack:
        node, parent = stack.pop()
        if not node.has_error:
            continue
        if node.type == ERROR or node.is_missing:
            out.append(_syntax_diag(node, parent, file, source))
            continue
        stack.extend((c, node) for c in reversed(node.children))
    out.sort(key=lambda d: (d.span.start, d.message))
    return out


def parse_source(source, path: str, name: str = ""):
    """-> (Module | None, diagnostics).

    `path` is the file, RELATIVE TO THE COMPILATION ROOT — it lands in every
    span this file produces, and `gen_c` emits those, so an absolute path here
    breaks determinism (`CONTRACT.md`).
    """
    if isinstance(source, str):
        source = source.encode("utf-8")
    # The scanner runs FIRST and its verdict is final: a file that does not lex
    # has no token stream to parse, so walking it would report tree-sitter's
    # opinion of the wreckage on top of the real mistake (TESTING.md, "one
    # syntax error must not cascade into fifty").
    lexical = _lex_diags(source, path)
    if lexical:
        return None, tuple(lexical)
    # MAX_NEST levels of AST, a few python frames each; the guard reports,
    # the interpreter must not give out first
    if sys.getrecursionlimit() < 10 * MAX_NEST:
        sys.setrecursionlimit(10 * MAX_NEST)
    tree = parser().parse(source)
    root = tree.root_node
    diags = _syntax_diags(root, path, source)
    if diags:
        # Same rule as a lexical error, one stage later: a tree with an ERROR
        # in it is not a program, and walking it hands sema a hole to report a
        # second time (`b = 2 +;` -> "expected expression" AND "undefined name
        # ``"). One mistake, one diagnostic.
        return None, tuple(diags)
    if not name:
        name = os.path.splitext(os.path.basename(path))[0]
    converter = Converter(source, path, root)
    module = converter.module(root, name, path)
    return module, tuple(diags) + tuple(converter.diags)


def parse_file(path, root=""):
    """Read a file and parse it. `root` is the compilation root; the span file
    is the path relative to it."""
    with open(path, "rb") as handle:
        source = handle.read()
    relative = os.path.relpath(path, root) if root else path
    return parse_source(source, relative.replace(os.sep, "/"))
