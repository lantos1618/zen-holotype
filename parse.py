"""Tiny recursive-descent parser for a SUBSET of Zen surface syntax.

Small on purpose — we test imports + the type space, not the parser.

    { a, b } = core.vec                     # import
    pub Vec: { len: i32, cap: i32 }         # struct
    pub area = (v: Ptr<Vec>) i32 { len(v) * cap(v) }   # fn; body = statements

build.zen extras (Zig-style declarative build):
    b.add(Executable { name: "app", main: "main.zen", out_dir: "build" })   # method call + struct literal
    .Ok(b.config())                                                          # leading-dot ctor

Types: i32/i64/bool/void -> PrimT ; Ptr/MutPtr/RawPtr<T> -> PtrT ; else NameT.
Exprs: ints, strings, idents, field a.b, calls f(x), methods r.m(x),
       struct literals T{...}, + - * .
"""
from __future__ import annotations
import re
from nodes import (Dir, Prim, PrimT, NameT, PtrT, Field_, Struct, Variant,
                   EnumDecl, Param, Fn, Import, File,
                   Lit, Var, Field, Bin, Call, Str, StructLit, MethodCall, EnumCtor)

_TOKEN = re.compile(
    r'//[^\n]*|(?P<nl>\n)|[ \t\r]+|(?P<str>"[^"]*")|(?P<num>\d+)|(?P<id>@?[A-Za-z_]\w*)|(?P<punct>::=|[{}()<>:,=.+\-*])')
_PRIM = {p.value: p for p in Prim}
_DIR  = {d.value: d for d in Dir}


def tokenize(src: str):
    toks = []
    for m in _TOKEN.finditer(src):
        g = m.lastgroup
        if g == "nl":
            toks.append(("nl", "\n"))               # newlines separate statements
        elif g == "str":
            toks.append(("str", m.group()[1:-1]))
        elif g in ("num", "id", "punct"):
            toks.append((g, m.group()))
    toks.append(("eof", ""))
    return toks


def mk_type(name: str, args: list):
    if name in _PRIM:
        return PrimT(_PRIM[name])
    if name in _DIR:
        return PtrT(_DIR[name], args[0])
    return NameT(name, tuple(args))


class P:
    def __init__(self, toks, ns):
        self.toks, self.i, self.ns = toks, 0, ns

    def _skip_nl(self):
        while self.toks[self.i][0] == "nl":
            self.i += 1

    def peek(self):    self._skip_nl(); return self.toks[self.i]      # newlines are insignificant…
    def at(self, txt): self._skip_nl(); return self.toks[self.i][1] == txt
    def nxt(self):     self._skip_nl(); t = self.toks[self.i]; self.i += 1; return t
    def raw(self):     return self.toks[self.i]                       # …except where chaining must stop

    def eat(self, txt):
        k, t = self.nxt()
        if t != txt:
            raise SyntaxError(f"expected '{txt}' got '{t}'")
        return t

    def ident(self):
        k, t = self.nxt()
        if k != "id":
            raise SyntaxError(f"expected ident got '{t}'")
        return t

    # ── declarations ────────────────────────────────────────────────────
    def file(self) -> File:
        imports, decls = [], []
        while self.peek()[0] != "eof":
            if self.at("{"):
                imports.append(self.imp())
            else:
                pub = self.at("pub") and (self.eat("pub") or True)
                name = self.ident()
                if self.at(":"):
                    self.eat(":"); decls.append(self.typedef(name, pub))
                elif self.at("="):
                    self.eat("="); decls.append(self.fn(name, pub))
                else:
                    raise SyntaxError(f"unexpected '{self.peek()[1]}' after '{name}'")
        return File(self.ns, imports, decls)

    def imp(self) -> Import:
        self.eat("{"); names = [self.ident()]
        while self.at(","):
            self.eat(","); names.append(self.ident())
        self.eat("}"); self.eat("=")
        mod = self.ident()
        while self.at("."):
            self.eat("."); mod += "." + self.ident()
        return Import(names, mod)

    def typedef(self, name, pub):
        if self.at("{"):                                  # struct
            self.eat("{"); fields = [self.sfield()]
            while self.at(","):
                self.eat(","); fields.append(self.sfield())
            self.eat("}")
            return Struct(name, fields, pub)
        variants = [self.variant()]                       # enum
        while self.at(","):
            self.eat(","); variants.append(self.variant())
        return EnumDecl(name, variants, pub)

    def sfield(self):
        n = self.ident(); self.eat(":"); return Field_(n, self.type())

    def variant(self):
        n = self.ident()
        payload = None
        if self.at("("):
            self.eat("("); payload = self.type(); self.eat(")")
        return Variant(n, payload)

    def type(self):
        name = self.ident(); args = []
        if self.at("<"):
            self.eat("<"); args.append(self.type())
            while self.at(","):
                self.eat(","); args.append(self.type())
            self.eat(">")
        return mk_type(name, args)

    def fn(self, name, pub):
        self.eat("("); params = []
        if not self.at(")"):
            params.append(self.param())
            while self.at(","):
                self.eat(","); params.append(self.param())
        self.eat(")")
        ret = self.type()
        self.eat("{")
        stmts = []
        while not self.at("}") and self.peek()[0] != "eof":
            stmts.append(self.stmt())
        self.eat("}")
        return Fn(name, params, ret, stmts, pub)

    def param(self):
        n = self.ident(); self.eat(":"); return Param(n, self.type())

    # ── statements / expressions ────────────────────────────────────────
    def stmt(self):
        if self.at("."):                                  # .Ok(x) leading-dot ctor
            self.eat("."); name = self.ident()
            args = self.call_args() if self.at("(") else ()
            return EnumCtor(name, tuple(args))
        return self.expr()

    def call_args(self):
        self.eat("("); args = []
        if not self.at(")"):
            args.append(self.expr())
            while self.at(","):
                self.eat(","); args.append(self.expr())
        self.eat(")")
        return args

    def expr(self):
        return self.add()

    def add(self):
        e = self.mul()
        while self.raw()[1] in ("+", "-"):       # raw: an operator on the SAME line
            op = self.nxt()[1]; e = Bin(op, e, self.mul())
        return e

    def mul(self):
        e = self.post()
        while self.raw()[1] == "*":
            self.nxt(); e = Bin("*", e, self.post())
        return e

    def post(self):
        e = self.atom()
        while self.raw()[1] == ".":              # a '.' with no newline before it = chaining
            self.eat("."); name = self.ident()
            if self.at("("):
                e = MethodCall(e, name, tuple(self.call_args()))   # r.m(args)
            else:
                e = Field(e, name)                                 # r.field
        return e

    def atom(self):
        k, t = self.peek()
        if k == "str":
            self.nxt(); return Str(t)
        if k == "num":
            self.nxt(); return Lit(int(t))
        if t == "(":
            self.eat("("); e = self.expr(); self.eat(")"); return e
        name = self.ident()
        if self.at("("):
            return Call(name, tuple(self.call_args()))
        if self.at("{"):
            return self.struct_lit(name)
        return Var(name)

    def struct_lit(self, typename):
        self.eat("{"); fields = []
        if not self.at("}"):
            fields.append(self.lit_field())
            while self.at(","):
                self.eat(",")
                if self.at("}"):       # tolerate trailing comma
                    break
                fields.append(self.lit_field())
        self.eat("}")
        return StructLit(typename, tuple(fields))

    def lit_field(self):
        n = self.ident(); self.eat(":"); return (n, self.expr())


def parse(src: str, ns: str) -> File:
    return P(tokenize(src), ns).file()
