# A map of `bootstrap/gen_c.py`

`bootstrap/gen_c.py` is 6917 lines, and this document points into it by line number several hundred times.

Those numbers are checked, not asserted: **`make refmap`** reads every `symbol (line)` and `file:line` claim below and verifies it against the file on disk, so a stale coordinate fails the build instead of misleading a reader. Run it after any edit to either file.

What the gate cannot check is whether a paragraph *describes* the right thing — only that its coordinates resolve. `scripts/refmap.py` says so in its own header, and lists what else it leaves to a human.

This page used to open by naming the revision it was written against. That is deliberately gone: the name was wrong, in a way no reader could have caught — at the commit it cited, the file was a different size than the same sentence claimed. A document that has to be trusted about which code it describes is a document that cannot be checked, so the gate reads the code instead.

---

# 0. Orientation

`/home/ubuntu/zenc/bootstrap/gen_c.py` — the whole backend is one module. Consumers: `/home/ubuntu/zenc/bootstrap/bootstrap.py:331` calls it as `text, gen_diags = gen_c.generate(graph, sema=sema, root=root)`, and only after sema/own produced zero diagnostics (`bootstrap.py:309-332`). So gen_c may assume a well-formed program but still degrades to diagnostics rather than guesses.

Corpus that pins its behavior: `/home/ubuntu/zenc/tests/corpus/codegen/` (`c_keywords_*.zen`, `c_libc_names.zen`, `c_reserved_identifiers.zen`, `mangle_generic_instantiation.zen`, `mangle_module_collision/`, `nesting_{blocks,calls,expr,match}.zen`, `literal_boundaries_{signed,unsigned}.zen`, `struct_return_*.zen`) plus `/home/ubuntu/zenc/tests/determinism/`.

---

# 1. Top-level structure

## 1.1 Entry point

```python
def generate(program, sema=None, root=None, sources=None):      # gen_c.py:6895
    emitter = Emitter(program, sema=sema, root=root, sources=sources)
    text = emitter.emit()
    seen = []; out = []
    for diag in emitter.diags:
        key = (str(f(diag, "span", "")), str(f(diag, "message", diag)))
        if key in seen: continue
        seen.append(key); out.append(diag)
    return text, tuple(out)

emit = generate                                                  # gen_c.py:6917
```

Returns `(C source text: str, diagnostics: tuple)`. Diagnostics are de-duplicated on `(span, message)` — "a type resolved for a prototype and again for a body is one bug" (6903). Never raises; `Emitter.error` (1723) appends `ast.Diag`.

`program` is duck-typed: `modules_of` (600) accepts a `modules.ModuleGraph` (has `.modules` dict + `.lookup`), a dict, a list, or a bare `ast.Module`. `self.graph` is set only when the object has both `.modules` and `.lookup` (974-1001).

## 1.2 Top-level names

Constants/tables: `C_STANDARD` (157), `USR="zu_"` / `GEN="zg_"` (159-160), `MAX_INSTANCES=8192`, `MAX_FUNCTIONS=8192`, `MAX_EXPR_DEPTH=24`, `INLINE_DEPTH=32` (162-170), `ENVMARK="\x01env\x01"` (175), `PRIMS` (291), `INT_LIMITS` (310), `INT_VALUES` (325), `NUMERIC` (339), `UNIT`/`UNKNOWN`/`INFER` (360), `ARITH`/`WRAPPING`/`COMPARE` (6366), `_LVALUE` (removed -- the lvalue test is now the `_is_lvalue` function, 6350-6362), `_IDENT` (206), `_ESCAPES` (6427).

Free functions: `_sibling` (117), `kind` (187), `f` (191), `_diag` (195), mangling `comp/clist/path_code/sym_type/tcode_named/sym_fn/sym_variant/sym_member/sym_local/sym_value` (209-271), `has_unknown` (345), `prim` (376), `tcode` (380), `is_int` (402), `int_info` (428), `union_of` (454), `_skip_trivia` (526), `modules_of` (600), `module_parts` (632), `_tparam_names` (681), `_is_variadic` (685), `_bare_name` (691), `_type_args` (696), `_block_value` (705), `_bound_apps` (720), `_bound_names` (741), `_is_fn_field` (791), `is_loop_shape` (6243), `erase` (6265), `refine` (6285), `is_handle` (6303), `_writes_scope` (6307), `paren` (6374), `parse_int` (6380), `int_literal` (6396), `float_literal` (6418), `decode_str` (6438), `decode_char` (6468), `c_string` (6476), `_checked_helpers` (6782), `generate` (6895).

Classes: `SourceMap` (483), `Positions` (547), `Decl` (646), `Emitter` (843), `FnCtx` (2326).

Runtime string constants: `BANNER` (6499), `INCLUDES` (6518), `PRELUDE_TYPES` (6528), `PRELUDE_TRAP` (6542), `PRELUDE_SCOPE` (6583), `DEFER_RUNTIME` (6595), `PRELUDE_PRINT` (6630), `HELPERS = _checked_helpers()` (6887).

## 1.3 The two-phase pipeline

`Emitter.__init__` (844-880) builds the declaration tables via `_collect()` (889); then:

```python
def emit(self):                                                  # gen_c.py:1728
    roots = [d for d in self.by_name.get("main", []) if d.dkind == "fn"]
    if not roots:
        roots = [d for ds in self.by_name.values() for d in ds if d.dkind == "fn"]
    for decl in sorted(roots, key=lambda d: d.parts):
        if decl.tparams:
            continue  # a generic is emitted per instantiation
        self.request_fn(decl, ())
    self.drain()
    return self.assemble()
```

Whole-program, demand-driven from `main` only (1730-1734) — an unreachable std member never has to compile. `drain` (1744) pops a **sorted** worklist:

```python
self.worklist.sort(key=lambda item: item[0])   # by mangled cname
cname, decl, targs, self_ty = self.worklist.pop(0)
self.emit_fn(cname, decl, targs, self_ty)
```
with a `MAX_FUNCTIONS` guard that reports "gen_c reached its bound on the functions one program may lower" (1760). That guard counts FUNCTIONS EMITTED and shared its constant with `MAX_INSTANCES`, which counts generic TYPE instantiations in a different loop; the two are separate now, and the message names the bound rather than whichever std function sorted first.

## 1.4 Output section order — exact

```python
def assemble(self):                                              # gen_c.py:2030
    entry = self.entry_point()      # FIRST: main can register one last type
    types = self.emit_types()
    out = []
    out.append(BANNER)
    out.append(INCLUDES)
    out.append(self.prelude())
    out.append(types)
    out.append(self.defer_section())
    out.append("/* ---- prototypes ---- */\n")
    for cname in sorted(self.protos):
        out.append(self.protos[cname] + "\n")
    out.append("\n/* ---- definitions ---- */\n\n")
    for cname in sorted(self.bodies):
        out.append(self.bodies[cname] + "\n")
    out.append(entry)
    return "".join(out)
```

So the physical file is:

1. `BANNER` comment (6499-6516)
2. `INCLUDES` — 6 headers (6518-6526)
3. `prelude()` (2084-2096): `PRELUDE_TYPES` + `PRELUDE_TRAP`, then `PRELUDE_SCOPE` iff `"scope" in self.needs`, then `PRELUDE_PRINT` iff `"print" in self.needs`, then `HELPERS[name] for name in sorted(self.helpers)`
4. `emit_types()` (2120-2143): `/* ---- types ---- */`, then **all** `typedef struct X X;` forward decls (`for cname in sorted(self.types)`), blank line, then one program-wide `enum { ... }` of variant tags (`for name in sorted(self.consts)`), then struct/union bodies in `topo()` order
5. `defer_section()` (2098-2118): capture structs `zg_envN`, the `zg_defer_env` union, then `DEFER_RUNTIME` — emitted only if `"scope" in self.needs`
6. `/* ---- prototypes ---- */` + every `self.protos[cname]` sorted by cname
7. `/* ---- definitions ---- */` + every `self.bodies[cname]` sorted by cname
8. `entry_point()` — the `int main(int, char**)` shim

Note the ordering subtlety at `assemble` 2030-2048: `entry_point()` is *computed* before `emit_types()` (it can `request_type`) but *appended last*.

## 1.5 The declaration model

`Decl` (646-678) `__slots__ = ("parts","node","dkind","name","tparams","module","owner","otparams")`. `dkind ∈ {"type","fn","value","variant"}`. Owner type params come **first**: `tparams = self.otparams + tuple(tparams)` (658) — "a method of `Vec<T>` is generic in T whether or not it declares any type parameters of its own, so ... an instantiation is (receiver args + call args)". `key` = `(module, owner or "", name)` (654). `scope_parts` = module parts + `(owner,)` and for an impl entry that is the **target** type, not the trait (`scope_parts` 672-678).

`_collect` (889) does impls **last** (889-901). `_collect_decl` (903) registers: Struct/Enum/Alias as `"type"`; every enum variant as its own `"variant"` decl (`Ok`, `Err`, `None` are importable names — `_collect_decl` 910-919); struct fn-fields as `"fn"` with `otparams=_tparam_names(node)`; struct fields with a default and no type, and `consts`, as `"value"`; `Function` as `"fn"`; `Impl` entries as `base + (target, trait, ename)` with `dk = "fn" if kind(entry) in ("Function","Lambda") else "value"` (962-964) — the trait component in `parts[-2]` is how `drop_impl`/`impl_entry`/`trait_methods` tell an impl entry from a type's own method; `Let`/`Const` as `"value"`.

Three indexes: `self.decls[(scope_parts, name)]`, `self.by_key[(module, owner, name)]`, `self.by_name[name]` (853-855). `lookup` (974) asks the module graph first (visibility is `modules.py`'s job), then the local table walking `parts` outward, then `by_name` module-agnostically.

---

# 2. Name mangling — exact

## 2.1 The scheme (docstring 26-82)

Two prefixes, and **every** identifier in the output is under one of them: `zu_` from a user name, `zg_` compiler-generated. Neither starts with `_`, so C11 7.1.3 reserved identifiers are unreachable; `zu_` cannot produce `zg_`. `main` is the sole exception.

```
comp  := <decimal byte length> <bytes>
list  := <decimal count> "_" comp*
```
A length is read as the maximal digit run; a Zen identifier cannot start with a digit, so the parse is unique. `alpha`+`beta_gamma` → `2_5alpha10beta_gamma`; `alpha_beta`+`gamma` → `2_10alpha_beta5gamma`.

## 2.2 Literal mangling source (gen_c.py:206-271)

```python
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def comp(name: str) -> str:
    """One length-prefixed component."""
    text = str(name)
    if not _IDENT.match(text):
        # Zen identifiers are ASCII by the grammar; anything else is encoded
        # rather than emitted raw, and the caller raises a diagnostic.
        text = "x" + "".join("%02x" % b for b in text.encode("utf-8"))
    return "%d%s" % (len(text), text)


def clist(items) -> str:
    """A counted list of already-encoded strings."""
    items = tuple(items)
    return "%d_%s" % (len(items), "".join(items))


def path_code(parts) -> str:
    return clist([comp(p) for p in parts])


def sym_type(parts, args=()) -> str:
    return USR + tcode_named(parts, args)


def tcode_named(parts, args=()) -> str:
    out = "t" + path_code(parts)
    args = tuple(args)
    if args:
        out += "I" + clist([tcode(a) for a in args])
    return out


def sym_fn(parts, sig=(), targs=(), self_ty=None) -> str:
    out = USR + "f" + path_code(parts)
    sig = tuple(sig)
    if sig:
        out += "O" + clist([tcode(t) for t in sig])
    targs = tuple(targs)
    if targs:
        out += "I" + clist([tcode(t) for t in targs])
    if self_ty is not None:
        out += "S" + tcode(self_ty)
    return out


def sym_variant(parts) -> str:
    return USR + "e" + path_code(parts)


def sym_member(name) -> str:
    return USR + "m" + comp(name)


def sym_local(name, n=1) -> str:
    return USR + "l" + comp(name) + ("" if n <= 1 else "_%d" % n)


def sym_value(parts) -> str:
    return USR + "v" + path_code(parts)
```

Note `sym_value` is declared but **never called** — module-level bindings are inlined at their use site (`ex_Path` 2821-2862), which is exactly what the docstring at 58-61 reserves it for.

## 2.3 Type encoding — `tcode` (364-383)

```python
def tcode(t) -> str:
    """The name of a type.  A pure function of the type, and injective."""
    if t is None:
        return "q"
    k = t[0]
    if k == "prim":
        return "b" + comp(t[1])
    if k == "named":
        return tcode_named(t[1], t[2])
    if k == "ptr":
        return "p" + tcode(t[1])
    if k == "array":
        return "a%d_%s" % (t[1], tcode(t[2]))
    if k == "fn":
        return "f" + tcode(t[1]) + clist([tcode(p) for p in t[2]])
    if k == "union":
        return "u" + clist(sorted(tcode(m) for m in t[1]))
    if k == "unit":
        return "z"
    return "q"
```

Tag letters lowercase, `I`/`O`/`S` uppercase — no tag can be mistaken for the start of a length-prefixed component. `Box<i32>` in module `gamma` → `t2_5gamma3BoxI1_b3i32`. `str` renders as `b3str` when there is no `str` type declaration, else as its named type.

## 2.4 Which sites mangle, and how

| site | producer | call site |
|---|---|---|
| named type / monomorphised instance | `USR + tcode(t)` | `request_type` 1212-1229 |
| structural type (array/union/fn) | `GEN + tcode(t)` | `request_type` 1217 |
| function / method / instantiation | `sym_fn(decl.parts, sig, targs, self_ty)` | `request_fn` 1774; `entry_point` 2265-2313 |
| enum constant (tag) | `sym_variant(parts + (vname,))` | `_request_named` 1264, `make_variant` 4136-4151, `pat_conds` 5848-5891/5848-5891, `match_enum` 5934-6005, `ex_Try` 6033-6055 |
| struct member / enum payload member | `sym_member(name)` | `emit_type` 2170-2225/2170, field read in `ex_Member` 2897-2937, `construct_type` 3323-3362, `make_variant` 4136-4151 |
| trait slot | `sym_member(name) + ("" if seen[name]==1 else "_%d" % seen[name])` | `trait_slots` 1400 |
| local / parameter | `sym_local(name, n)` with a **per-function** counter | `FnCtx.declare` 2398-2405 |
| struct tag | the *same string* as the typedef | `emit_types` 2120-2143 `typedef struct %s %s;` |
| label | `GEN + stem + tmpcounter` | `FnCtx.label` 4243-4245 |
| temporary | `"%st%d" % (GEN, self.tmp)` | `new_tmp` 2383-2388 |

`FnCtx.declare` (2398-2405):
```python
def declare(self, name, ty, byref=False):
    n = self.counts.get(name, 0) + 1
    self.counts[name] = n
    cname = sym_local(name, n)
    self.scopes[-1][name] = ("(*%s)" % cname if byref else cname, ty)
    return cname
```
`self.counts` is per-`FnCtx`, not per-scope, so the *second* `x` anywhere in a function body becomes `zu_l1x_2`. A `::` (mutable) parameter is stored as `(*zu_l4self)` so every reader downstream is oblivious (`declare` 2398-2405).

Generated identifiers (all `zg_`): `zg_t<N>` temporaries; `zg_brk<N>`/`zg_cnt<N>` loop labels; `zg_fmt<N>` format-done label; `zg_blk<N>` scope record; `zg_cap<N>` capture instance; `zg_live<N>` drop flag; `zg_d<N>` defer thunk, `zg_env<N>` its capture struct, `zg_u<N>` its member in the `zg_defer_env` union, `zg_c<i>` capture fields; `zg_v<mangled-fn-minus-zu_>` trait thunk (`cname = GEN + "v" + target[len(USR):]`, 1606); `zg_console_write`/`zg_console_write_byte`, composed rather than written (`console_thunk` 1651-1680); `zg_a<i>` thunk params; `zg_self`, `zg_tag`, `zg_data`, `zg_pad`, `zg_elems`, `zg_m<tcode>`, `zg_tag<tcode>`, `zg_n`, `zg_slot`, `zg_fn`, `zg_env`, `zg_none`, `zg_argc`, `zg_argv`.

## 2.5 C reserved words / reserved identifier classes

Handled as an **identifier class, not a keyword list** (docstring 33-39): because every user identifier is mangled with a `zu_<tag>` prefix and a length prefix, no C keyword, no standard-header macro and no `_`-leading reserved identifier is expressible. `comp()` is the only escape hatch: a non-ASCII/non-identifier name becomes `x` + lowercase hex of its UTF-8 bytes (212-216), and the caller is expected to also raise a diagnostic.

Evidence corpus: `tests/corpus/codegen/c_keywords_c89.zen`, `c_keywords_c99_c11.zen`, `c_keywords_c23.zen`, `c_keywords_declaration_positions.zen`, `c_libc_names.zen`, `c_reserved_identifiers.zen`.

---

# 3. Trap emission — exact

## 3.1 Trap runtime (`PRELUDE_TRAP`, gen_c.py:6625-6581) — verbatim

```c
/* A trap is for a bug (DESIGN.md).  It prints file:line:col and aborts with
 * 134; the position is the operator token.  Note that no check below ever
 * performs the operation first: signed overflow is undefined behaviour in C,
 * and an after-the-fact test is one the optimizer is entitled to delete. */
static void zg_trap(const char *file, unsigned long line, unsigned long col,
                    const char *what) {
    fflush(stdout);
    fprintf(stderr, "%s:%lu:%lu: trap: %s\n", file, line, col, what);
    fflush(stderr);
    exit(134);
}

static void zg_unreachable(const char *file, unsigned long line,
                           unsigned long col) {
    zg_trap(file, line, col, "unreachable match arm");
}

#if defined(__GNUC__) && (__GNUC__ >= 5)
#define ZG_HAS_OVERFLOW_BUILTINS 1
#elif defined(__has_builtin)
#if __has_builtin(__builtin_add_overflow)
#define ZG_HAS_OVERFLOW_BUILTINS 1
#endif
#endif

static size_t zg_idx_u(uint64_t i, size_t len, const char *file,
                       unsigned long line, unsigned long col) {
    if (i >= (uint64_t)len) zg_trap(file, line, col, "index out of bounds");
    return (size_t)i;
}

static size_t zg_idx_s(int64_t i, size_t len, const char *file,
                       unsigned long line, unsigned long col) {
    if (i < 0 || (uint64_t)i >= (uint64_t)len)
        zg_trap(file, line, col, "index out of bounds");
    return (size_t)i;
}
```

`zg_trap` is `fflush(stdout)` **before** the stderr write and after — so stdout ordering is deterministic in the `.stderr` corpus. Exit code 134 (SIGABRT-equivalent), via `exit`, not `abort()`.

Trap message strings, complete set: `"integer overflow"`, `"divide by zero"`, `"index out of bounds"`, `"unreachable match arm"` (via `zg_unreachable`), `"too many deferred closures on one block"` (`DEFER_RUNTIME` 6595-6628).

## 3.2 The checked-helper generator (`_checked_helpers` 6699-6801) — verbatim

```python
def _checked_helpers():
    """One checked helper per (operation, integer type).

    Emitted only for the types a program uses, sorted, so the set never leaks
    an iteration order into the file.
    """
    unsigned_of = {
        "int8_t": "uint8_t",
        "int16_t": "uint16_t",
        "int32_t": "uint32_t",
        "int64_t": "uint64_t",
        "ptrdiff_t": "size_t",
    }
    out = {}
    for name, (signed, bits, cmin, cmax) in sorted(INT_LIMITS.items()):
        ct = PRIMS[name]
        uct = unsigned_of.get(ct, ct)
        cast = "(%s)" % ct
        args = "const char *file, unsigned long line, unsigned long col"
        sig = "static %s zg_%%s_%s(%s a, %s b, %s)" % (ct, name, ct, ct, args)

        if signed:
            add_slow = (
                "    if ((b > 0 && a > %s - b) || (b < 0 && a < %s - b))\n"
                "        zg_trap(file, line, col, \"integer overflow\");\n"
                "    return %s((%s)a + (%s)b);\n" % (cmax, cmin, cast, uct, uct)
            )
            sub_slow = (
                "    if ((b < 0 && a > %s + b) || (b > 0 && a < %s + b))\n"
                "        zg_trap(file, line, col, \"integer overflow\");\n"
                "    return %s((%s)a - (%s)b);\n" % (cmax, cmin, cast, uct, uct)
            )
            mul_slow = (
                "    if (a > 0) {\n"
                "        if (b > 0) { if (a > %s / b) zg_trap(file, line, col, \"integer overflow\"); }\n"
                "        else { if (b < %s / a) zg_trap(file, line, col, \"integer overflow\"); }\n"
                "    } else if (a < 0) {\n"
                "        if (b > 0) { if (a < %s / b) zg_trap(file, line, col, \"integer overflow\"); }\n"
                "        else { if (b < %s / a) zg_trap(file, line, col, \"integer overflow\"); }\n"
                "    }\n"
                "    return %s((%s)a * (%s)b);\n"
                % (cmax, cmin, cmin, cmax, cast, uct, uct)
            )
        else:
            add_slow = (
                "    if (a > %s - b) zg_trap(file, line, col, \"integer overflow\");\n"
                "    return %s(a + b);\n" % (cmax, cast)
            )
            sub_slow = (
                "    if (a < b) zg_trap(file, line, col, \"integer overflow\");\n"
                "    return %s(a - b);\n" % cast
            )
            mul_slow = (
                "    if (b != 0 && a > %s / b) zg_trap(file, line, col, \"integer overflow\");\n"
                "    return %s(a * b);\n" % (cmax, cast)
            )

        for op, builtin, slow in (
            ("add", "__builtin_add_overflow", add_slow),
            ("sub", "__builtin_sub_overflow", sub_slow),
            ("mul", "__builtin_mul_overflow", mul_slow),
        ):
            body = (
                (sig % op)
                + " {\n"
                + "#ifdef ZG_HAS_OVERFLOW_BUILTINS\n"
                + "    %s r;\n" % ct
                + "    if (%s(a, b, &r)) zg_trap(file, line, col, \"integer overflow\");\n" % builtin
                + "    return r;\n"
                + "#else\n"
                + slow
                + "#endif\n}\n\n"
            )
            out["%s_%s" % (op, name)] = body

        div_guard = (
            "    if (b == 0) zg_trap(file, line, col, \"divide by zero\");\n"
        )
        if signed:
            # i32.MIN / -1 is overflow wearing division's clothes, and it
            # faults identically on x86: the message must say overflow.
            div_guard += (
                "    if (a == %s && b == -1) zg_trap(file, line, col, \"integer overflow\");\n"
                % cmin
            )
        out["div_%s" % name] = (sig % "div") + " {\n" + div_guard + "    return %s(a / b);\n}\n\n" % cast
        out["mod_%s" % name] = (sig % "mod") + " {\n" + div_guard + "    return %s(a %% b);\n}\n\n" % cast

        wsig = "static %s zg_%%s_%s(%s a, %s b)" % (ct, name, ct, ct)
        if signed:
            for op, sym in (("wadd", "+"), ("wsub", "-"), ("wmul", "*")):
                out["%s_%s" % (op, name)] = (
                    (wsig % op)
                    + " {\n    return %s((%s)a %s (%s)b);\n}\n\n" % (cast, uct, sym, uct)
                )
        else:
            for op, sym in (("wadd", "+"), ("wsub", "-"), ("wmul", "*")):
                out["%s_%s" % (op, name)] = (
                    (wsig % op) + " {\n    return %s(a %s b);\n}\n\n" % (cast, sym)
                )
    out["idx_u"] = ""  # defined in PRELUDE_TRAP
    out["idx_s"] = ""
    return out
```

Concretely, for `i32` (`ct = int32_t`, `uct = uint32_t`, `cmin = INT32_MIN`, `cmax = INT32_MAX`) the emitted `add` helper is:

```c
static int32_t zg_add_i32(int32_t a, int32_t b, const char *file, unsigned long line, unsigned long col) {
#ifdef ZG_HAS_OVERFLOW_BUILTINS
    int32_t r;
    if (__builtin_add_overflow(a, b, &r)) zg_trap(file, line, col, "integer overflow");
    return r;
#else
    if ((b > 0 && a > INT32_MAX - b) || (b < 0 && a < INT32_MIN - b))
        zg_trap(file, line, col, "integer overflow");
    return (int32_t)((uint32_t)a + (uint32_t)b);
#endif
}
```

and:

```c
static int32_t zg_div_i32(int32_t a, int32_t b, const char *file, unsigned long line, unsigned long col) {
    if (b == 0) zg_trap(file, line, col, "divide by zero");
    if (a == INT32_MIN && b == -1) zg_trap(file, line, col, "integer overflow");
    return (int32_t)(a / b);
}
static int32_t zg_mod_i32(int32_t a, int32_t b, const char *file, unsigned long line, unsigned long col) {
    if (b == 0) zg_trap(file, line, col, "divide by zero");
    if (a == INT32_MIN && b == -1) zg_trap(file, line, col, "integer overflow");
    return (int32_t)(a % b);
}
static int32_t zg_wadd_i32(int32_t a, int32_t b) { return (int32_t)((uint32_t)a + (uint32_t)b); }
static int32_t zg_wsub_i32(int32_t a, int32_t b) { return (int32_t)((uint32_t)a - (uint32_t)b); }
static int32_t zg_wmul_i32(int32_t a, int32_t b) { return (int32_t)((uint32_t)a * (uint32_t)b); }
```

**`__builtin_*_overflow` is used only for add/sub/mul, for all ten integer types** (`i8 i16 i32 i64 isize u8 u16 u32 u64 usize`, `INT_LIMITS` 309-321), and only under `ZG_HAS_OVERFLOW_BUILTINS`. Division/modulo never use a builtin. Wrapping ops never trap and take no position argument; signed wrapping goes through the unsigned type to avoid UB (`isize` maps to `size_t`).

## 3.3 Call sites

**Binary arithmetic** — `fold_binary` (3191-3230). Note that the checked result is **always spilled into a temporary**:

```python
if op in ARITH:
    if is_int(ty):
        base = {"+": "add", "-": "sub", "*": "mul", "/": "div", "%": "mod"}[op]
        name = "%s_%s" % (base, ty[1])
        self.e.helpers.add(name)
        file, line, col = self.e.pos.operator(node, lhs, rhs)
        out = "%s%s(%s, %s, %s, %d, %d)" % (
            GEN, name, lcode, rcode, c_string(file.encode("utf-8")), line, col)
        tmp = self.new_tmp(ty)
        self.line("%s = %s;" % (tmp, out))
        return (tmp, ty)
    return ("(%s %s %s)" % (paren(lcode), op, paren(rcode)), ty)
```
So `a + b` at i32 emits:
```c
int32_t zg_t3;
zg_t3 = zg_add_i32(zu_l1a, zu_l1b, "m.zen", 7, 11);
```
Float/non-int arithmetic falls through to plain C `(a + b)`.

**Wrapping** (3166-3172):
```python
if op in WRAPPING:
    base = {"+%": "wadd", "-%": "wsub", "*%": "wmul"}[op]
    if is_int(ty):
        name = "%s_%s" % (base, ty[1])
        self.e.helpers.add(name)
        return ("%s%s(%s, %s)" % (GEN, name, lcode, rcode), ty)
    return ("(%s %s %s)" % (paren(lcode), op[0], paren(rcode)), ty)
```
Not spilled — it cannot trap. Non-int falls back to `op[0]`, i.e. `+%` becomes `+`.

**Unary minus** — `ex_Unary` (3125-3149). Negative literals are folded (no trap); a runtime negation is `0 - x`:
```python
if is_int(ty):
    file, line, col = self.e.pos.of(node)
    helper = "sub_" + ty[1]
    self.e.helpers.add(helper)
    return ("%s%s(0, %s, %s, %d, %d)" % (GEN, helper, code,
            c_string(file.encode("utf-8")), line, col), ty)
```
Position here is `pos.of(node)` (node start), **not** the operator-gap scan.

**Fixed-array bounds check** — `ex_Index` (3092-3123):
```python
if bty is not None and bty[0] == "array":
    file, line, col = self.e.pos.operator(node, base, index)
    helper = "idx_u" if not (is_int(ity) and int_info(ity)[0] < 0) else "idx_s"
    self.e.helpers.add(helper)
    checked = "%s%s(%s, %d, %s, %d, %d)" % (
        GEN, helper, icode, bty[1], c_string(file.encode("utf-8")), line, col)
    return ("%s.%selems[%s]" % (paren(bcode), GEN, checked), bty[2])
```
i.e. `arr.zg_elems[zg_idx_u(i, 8, "m.zen", 3, 9)]`. A **`Ptr<T>` index is unchecked** — `("%s[%s]" % (paren(bcode), icode), bty[1])` (3042-3044) — "a raw pointer carries no length ... and `Vec.get` returns a Res instead". A named type's `s[i]` becomes a call to its own `index` method (3094).

`self.e.helpers` is a `set`, drained sorted at `prelude()` 1870. `HELPERS["idx_u"]`/`["idx_s"]` are `""` because those two live in `PRELUDE_TRAP` unconditionally (6542-6581).

**Unreachable match arm** — `match_enum` (5934-6005) when there is no wildcard arm:
```python
file, line, col = self.e.pos.of(node)
self.line("default: %sunreachable(%s, %d, %d);" % (GEN, c_string(file.encode("utf-8")), line, col))
```

## 3.4 The operator position

`Positions.operator` (571-592): if the node has an `op_span`, use it; otherwise scan the source text **between** the left operand's end and the right operand's start, skipping whitespace, `//` and `/* */` (`_skip_trivia`, 526-544), and take the first real byte's `(line, col)`. Fallback is `self.of(node)`. Source text comes from `SourceMap` (483-523), which reads from `root` on disk or from the `sources` dict. File names are made relative to `root` and `\`-normalised to `/` (`relfile`, 554-562), so no absolute path reaches the output. `__FILE__` is never emitted.

---

# 4. C type mapping

## 4.1 The resolved type model (docstring 274-289)

Types are plain hashable tuples:
```
("prim", name) | ("named", (path...), (args...)) | ("ptr", T)
("array", count, T) | ("fn", ret, (params...)) | ("union", (members sorted by tcode))
("unit",) | ("unknown",) | ("variadic",) | ("lambda", ...) | ("loop", n)
```
The last two are FnCtx-internal binding markers, never types (`bind_closure` 4247-4274, `lower_loop` 4413-4530).

## 4.2 Primitives (`PRIMS`, 291-307)

```python
PRIMS = {
    "i8": "int8_t",   "i16": "int16_t", "i32": "int32_t", "i64": "int64_t",
    "u8": "uint8_t",  "u16": "uint16_t","u32": "uint32_t","u64": "uint64_t",
    "usize": "size_t","isize": "ptrdiff_t",
    "f32": "float",   "f64": "double",  "bool": "bool",
    "str": GEN + "str",  "()": "void",
}
```

`resolve_type` (1064) special-cases: `Ptr`/`RawPtr` → `("ptr", arg or u8)`; `...` → `("variadic",)`; any name in `NUMERIC` → `prim(name)` **even though std declares `i32` etc. as struct bodies** carrying `MIN`/`MAX`/`BITS` (1082-1088); `@Self` → `self_ty` or the enclosing type; `Alias` transparently resolves to its target.

## 4.3 `ctype` (1170-1193)

```python
def ctype(self, t):
    if t is None or t == UNKNOWN:
        return "int"  # a diagnostic has already been raised
    k = t[0]
    if k == "prim":
        name = t[1]
        if name == "str" and self.type_decl("str"):
            return self.request_type(("named", self.type_decl("str").parts, ()))
        return PRIMS.get(name, "int")
    if k == "unit":
        return "void"
    if k == "ptr":
        inner = self.ctype(t[1])
        return inner + " *"
    if k in ("named", "array", "union"):
        if k == "named" and self.is_scope_ty(t):
            self.needs.add("scope")
            return GEN + "scope *"
        return self.request_type(t)
    if k == "fn":
        return GEN + "closure"
    return "int"
```

- **`str`** — `zg_str` (`typedef struct zg_str { unsigned char *data; size_t len; }`, 6283) *unless* std declares a `str` type, in which case the user's struct wins and its members are read through `sym_member` (`str_names`/`str_literal` 2840-2852). `str_names` hardcodes the member names `"data"` and `"len"`.
- **Function type** → `zg_closure` (`{ void *fn; void *env; }`, 6535). This is essentially vestigial: closures are inlined, never materialised (`ex_Lambda` 6193-6203 errors).
- **`Scope`** → `zg_scope *` (pointer to the enclosing block's record).
- **`()`** → `void`.
- Everything nominal/array/union → `request_type` mangled name.

`declarator(t, name)` (1203): pointer spellings bind to the name (`int32_t *x`), everything else gets a space. `fnptr(ret, params, name)` (1195): `ret (*name)(void *, params..)` — the receiver is always erased to `void *`, one slot per method serves every impl.

## 4.4 Emitted layouts (`emit_type`, 2170-2225)

**struct**:
```c
struct zu_t...Point { int32_t zu_m1x; int32_t zu_m1y; };
```
An empty struct gets `char zg_pad;` (C11 6.7.2.1p1 requires a member) — "one byte, in exactly one place, so a bare Empty and an Empty field agree" (2178). Function-typed fields are **skipped** — "a method is a function, not storage" (1274).

**enum — tag + union**:
```python
lines.append("struct %s {\n    int32_t %stag;\n" % (cname, GEN))
payloads = [(v, p) for v, p in variants if p is not None]
if payloads:
    lines.append("    union {\n")
    for vname, pty in payloads:
        lines.append("        %s;\n" % self.declarator(pty, sym_member(vname)))
    lines.append("    } %sdata;\n" % GEN)
lines.append("};\n\n")
```
i.e.
```c
struct zu_t..ResI2_b3i323Err {
    int32_t zg_tag;
    union {
        int32_t zu_m2Ok;
        zu_t..Error zu_m3Err;
    } zg_data;
};
```
The union is omitted entirely when no variant carries a payload. Payload member is named after the **variant**, `sym_member(vname)`. A `()` payload becomes `None` — "`Ok(())` carries nothing; a void member is illegal C" (1296).

Tag constants are one **program-wide** C enum, emitted at `emit_types` 2120-2143, keyed by declaration not instantiation (`_request_named` 1193-1272):
```python
for i, (vname, _p) in enumerate(variants):
    # Res<i32, E> and Res<i32, F> share `Ok`, and emitting the constant per
    # instance is a C redefinition.
    self.consts[sym_variant(tuple(parts) + (vname,))] = i
```
so the tag value is the variant's **declaration index**.

**trait (fat value)** — a struct that declares fn-fields and **no storage** (`trait_decl`, 1348-1358):
```c
struct zu_t..Display {
    void *zg_self;
    zg_str (*zu_m8toString)(void *, ...);
};
```
Slot order is declaration order (`trait_slots`, 1342-1387); duplicate names get `_2`, `_3`. Slot parameter/return types are **erased** (`erase`, 6265-6282: `Ptr<T>` → `Ptr<u8>`, named type args erased recursively), and **one trailing `size_t` per erased type parameter of the member** is appended (1406-1407) — the element size the erasure dropped, Zig-`std.mem.Allocator` style.

**array** (`[T, N]`):
```c
struct zg_a4_b3i32 { int32_t zg_elems[4]; };
```
`max(t[1], 1)` — a zero-length array is illegal C (2162).

**union** (`A | B`, structural):
```c
enum { zg_tag<tcodeA> = 0, zg_tag<tcodeB> = 1, };
struct zg_u2_... {
    int32_t zg_tag;
    union { A zg_m<tcodeA>; B zg_m<tcodeB>; } zg_data;
};
```
Members `sorted(t[1], key=tcode)` (2215), so `A|B` and `B|A` are the same C type and the same name.

**opaque** (unknown decl or a non-union Alias): `struct X { char zg_pad; };` (2124).

## 4.5 `Res<T>` vs `Res<T, E>`

Both are ordinary enums; they are two *different declarations sharing a name*, disambiguated by arity everywhere:

- `type_decl(name, parts, arity)` (1019-1038) picks by `len(d.tparams) == arity`, falling back to an `Alias`, then to `got[0]`.
- `_request_named` (1193-1272) picks the candidate whose `len(d.tparams) == len(args)`.
- `filled_ret` (1819-1847) rewrites a declared `Res<T, _>` into `Res<T, <inferred set>>` by asking `sema.error_set_ast(fnode)`, memoised on `id(fnode)` — "the one funnel every caller reads a return type through, so a caller and a callee can never disagree about what `_` turned out to be".

Their C names differ because `tcode` includes the argument list: `zu_t3_3std4core6result3ResI1_b3i32` vs `...ResI2_b3i32<E>`.

`Vec`/`Map`/`String` are **not** special-cased: they are ordinary std structs, monomorphised through `request_type`. The only container the compiler knows intrinsically is the fixed array `[T, N]` (which "satisfies Range intrinsically" — `range_bounds` 5209-5231).

Coercion `T` → `Res<T>` happens in `coerce` (2604-2628) and fires **only when exactly one variant carries that payload type**:
```python
carriers = [v for v, p in info[2] if p is not None and p == ty]
if len(carriers) != 1:
    return code
return self.make_variant(want, carriers[0], code)
```
"Only success lifts: `Err` and `None` are always written."

## 4.6 Building a fat value (`fat_value`, 1682-1719)

```python
inits = [".%sself = (void *)%s" % (GEN, code)]
inits += [".%s = %s" % (slot, fn) for slot, fn in slots]
return "((%s){ %s })" % (self.ctype(trait), ", ".join(inits))
```
Each slot is a `thunk` (1598-1649): a `static` shim `zg_v<mangled>(void *zg_self, ...)` that casts the receiver (`(T *)zg_self` if the impl declared `self :: @Self`, else `(*(T *)zg_self)`), `convert`s each argument from the erased type to the real one, calls the real function, and `convert`s the result back. A missing impl member gives a `NULL` slot (1708). Un-implemented slots are never a cast of a function pointer — "a cast of the function pointer would be undefined; a shim is a call".

`convert` (1556-1588) **rebuilds** — pointers are cast, tagged unions are reconstructed variant by variant as a nested conditional; nothing reinterprets.

---

# 5. Determinism

The module docstring 7-24 is the binding contract. Every emission site sorts. Complete inventory of `sorted()` (verified by grep):

| line | what | key |
|---|---|---|
| 396 | union `tcode` members | `sorted(tcode(m) for m in t[1])` — string sort of member codes |
| 468 | `union_of` normalisation | `key=tcode` |
| 629 | `modules_of` | `key=lambda pair: pair[0]` (module path tuple) |
| — | trait deps — **this sort is gone**: a trait's slots are function pointers, so `type_order` is now `()` and nothing is sorted (`_request_named` 1222-1231 says why) |
| 1322 | `_deps` | `sorted(set(out))` |
| 1737 | `emit()` roots | `key=lambda d: d.parts` |
| 1762 | `drain()` worklist | `key=lambda item: item[0]` (mangled cname) |
| 2030-2048 | `assemble` prototypes | `sorted(self.protos)` (cname) |
| 2030-2048 | `assemble` definitions | `sorted(self.bodies)` (cname) |
| 2084-2096 | `prelude` arithmetic helpers | `sorted(self.helpers)` (helper name) |
| 2098-2118, 2098-2118 | `defer_section` capture structs and union members | `sorted(self.defer_envs)` (site number) |
| 2120-2143 | `emit_types` todo | `sorted(self.types)` |
| 2120-2143 | `emit_types` forward typedefs | `sorted(self.types)` |
| 2120-2143 | `emit_types` enum tag constants | `sorted(self.consts)` (mangled constant name) |
| 2120-2143 | `emit_types` type bodies | `self.topo(sorted(bodies))` |
| 2145-2168, 2145-2168 | `topo` ready set / cycle break | `sorted(...)` by name |
| 2182 | `emit_type` union members | `key=tcode` |
| 2265-2313 | `entry_point` main pick | `key=lambda d: d.parts` |
| 3795-3824 | `trait_methods` | `key=lambda d: d.parts` |
| 3963-4010 | `pick_overload` candidates | `key=lambda d: d.parts` |
| 4579-4591 | `free_fn` | `key=lambda d: d.parts` |
| 4593-4611 | `sink_door` | `key=lambda d: d.parts` |
| 5604-5631 | `console_sink` Sink lookup | `key=lambda d: d.parts` |
| 6782-6884 | `_checked_helpers` table build | `sorted(INT_LIMITS.items())` |

Other determinism mechanisms:

- **No counter takes part in a name.** A monomorphised instance's name is `tcode` of the type, a pure function of the type (docstring 20-23) — "two instantiations of the same type from different modules produce one name regardless of which was seen first". `mangle_generic_instantiation.zen` and `mangle_module_collision/` gate this.
- **Temporaries are per function**, numbered by the deterministic emission traversal; `FnCtx.tmp` starts at 0 for every function (2297). `peek`/`peek_block` **restore** `self.tmp` after a speculative lowering (3457-3478, 3411-3430), so a discarded lowering does not perturb numbering.
- **No pointer, `id()`, timestamp, env var, locale or absolute path** reaches the output. `id()` *is* used, but only as a memo key for `_rets` (1833-1835) — never emitted.
- **Nothing is emitted from a `set`.** `self.helpers` and `self.needs` are sets, consumed sorted / by membership test.
- `c_string` (6476-6492) emits **octal** escapes, not hex — "which also keeps the determinism scanner's pointer-shaped-hex check quiet" (6478).
- `defer_thunk` caches on `(body text, capture layout)` (1985-1987, 906), so two lowerings of one closure become one function and a *discarded* speculative lowering does not leave an unreferenced static behind (`defer_thunk` 1930-1933).
- Dicts (`self.types`, `self.protos`, `self.bodies`, `self.decls`, `self.by_name`, ...) are lookup structures only.

`Makefile:52-56` documents the harness: byte-identical C, five checks that gen_c is a pure function of input; `bootstrap.py:384` raises "bootstrap: gen_c is nondeterministic" if a double run differs.

---

# 6. Expression lowering — statement vs expression

## 6.1 The core contract

```python
def expr(self, node, want=None):                                # gen_c.py:2777
    """-> (C expression text, resolved type).  May emit statements."""
    if node is None:
        return ("0", UNKNOWN)
    self.depth += 1
    try:
        if self.depth > MAX_EXPR_DEPTH:
            code, ty = self._expr(node, want)
            if ty not in (UNIT, UNKNOWN) and not code.isidentifier():
                tmp = self.new_tmp(ty)
                self.line("%s = %s;" % (tmp, code))
                return (tmp, ty)
            return (code, ty)
        return self._expr(node, want)
    finally:
        self.depth -= 1
```

Every lowering returns `(code, type)` **and is allowed to have already appended statements to `ctx.lines`**. That is the whole answer to "C has no block expressions": anything that needs statements emits them, declares a `zg_tN` result temporary, and hands back the temporary's name. Header comment at 2270-2273: "gen_c may not assume its output nesting is bounded by its input nesting, so a match, a block-as-value and any operation that traps all spill, and an expression deeper than MAX_EXPR_DEPTH spills too." (`tests/corpus/codegen/nesting_*.zen`.)

`_expr` dispatches by class **name** via `getattr(self, "ex_" + kind(node))` (2801); an unknown node is a diagnostic, never a crash.

`new_tmp` (2383-2388) declares at the current indent and returns the name; it declares **nothing** for `UNIT`/`None` types but still burns a counter value.

`line` / `open` / `close` (2376-2378) manage an indent level; `self.text()` joins.

## 6.2 Blocks as values

```python
def ex_Block(self, node, want=None):                            # gen_c.py:5635
    if want in (None, UNKNOWN):
        # ... lower speculatively, then lower again with the answer as `want`.
        # Without this a block has no type to report, and a `.match` whose arms
        # are ALL blocks therefore types as `()`: no result temporary is
        # allocated and every arm's value is dropped, with no diagnostic and a
        # zero in its place.
        found = self.peek_block(node)
        if found not in (None, UNIT, UNKNOWN):
            want = found
    result = None
    if want not in (None, UNIT, UNKNOWN):
        result = self.new_tmp(want)
    self.push()
    self.open()
    value = self.block_value(node, want)
    if result is not None and value is not None:
        self.line("%s = %s;" % (result, value))
    self.close()
    self.pop()
    return (result if result is not None else "0", want or UNIT)
```

So a block-as-value becomes `T zg_tN; { ...stmts...; zg_tN = <tail>; }` and the expression text is `zg_tN`. A block is lowered **twice** when its type is unknown — `peek_block` (3480-3499) lowers into a buffer that is discarded:
```python
saved = (list(self.lines), self.tmp, self.indent, len(self.e.diags))
self.push()
try:
    self.block_value(node, INFER)
    return self.blk_ty
finally:
    self.pop()
    self.lines, self.tmp, self.indent = saved[0], saved[1], saved[2]
    del self.e.diags[saved[3]:]
```
`INFER` (360) is the third state alongside `None` (no expectation, nothing reading) and a real type: "a block has to tell those two apart to report the type of its own tail".

`_block_body` (2537-2602) is where the tail rules live:

```python
stmts = list(f(block, "stmts", ()) or ())
value = f(block, "value")
if value is None and want not in (None, UNIT, UNKNOWN) and stmts:
    # "`0;` closes a `Res<i32, E>` function exactly as `Ok(0);` does"
    last = stmts[-1]
    if kind(last) == "ExprStmt":
        _code, ty = self.peek(f(last, "expr"))
        if ty not in (UNIT, None):
            value = f(last, "expr")
            stmts = stmts[:-1]
for stmt in stmts:
    self.stmt(stmt)
here = len(self.dscopes) - 1
entries = self.dscopes[here]
if value is None:
    self.blk_ty = UNIT
    self.exit_scope(here)
    return None
code, ty = self.expr(value, None if want is INFER else want)
if want is not INFER:
    code = self.coerce(code, ty, want)
rty = ty if want in (None, UNKNOWN) or want is INFER else want
self.blk_ty = rty
if rty == UNIT and code not in ("", "0"):
    # a tail expression of type `()` is the block's value in name only:
    # nothing can read it, so it has to RUN here.
    self.line("(void)(%s);" % code)
    self.exit_scope(here)
    return "0"
if not entries and self.sscopes[here] is None:
    return code
if rty in (None, UNIT, UNKNOWN):
    self.exit_scope(here, code)
    return code
# the block's value is read BEFORE its defers and its bindings die, so
# it is spilled to a temporary and the cleanup runs against that
tmp = self.new_tmp(rty)
self.line("%s = %s;" % (tmp, code))
self.exit_scope(here, code)
return tmp
```

`block_value` (2506-2519) wraps it with the RAII/defer scope stacks (`dscopes`, `sscopes`) and returns the value expression or `None`.

## 6.3 `.match` in value position

```python
def ex_Match(self, node, want=None):                            # gen_c.py:5662
    scrut = f(node, "scrutinee")
    arms = list(f(node, "arms", ()) or ())
    scode, sty = self.expr(scrut)
    ty = want
    if ty in (None, UNKNOWN):
        ty = self.arm_type(arms)
    result = None
    if ty not in (None, UNIT, UNKNOWN):
        result = self.new_tmp(ty)
    tmp = self.new_tmp(sty) if sty not in (None, UNIT, UNKNOWN) else None
    if tmp:
        self.line("%s = %s;" % (tmp, scode))
        scode = tmp

    if sty is not None and sty[0] == "prim" and sty[1] == "bool":
        self.match_bool(node, scode, arms, result, ty)
    elif sty is not None and sty[0] == "named" and self.e.enum_info(sty):
        self.match_enum(node, scode, sty, arms, result, ty)
    else:
        self.match_scalar(node, scode, arms, result, ty)
    return (result if result is not None else "0", ty or UNIT)
```

The scrutinee is **always** spilled to a temporary first (so it is evaluated once). The result is a temporary; each arm assigns it (`arm_body` 5788-5816). Three lowerings:

- **bool** → `if (s) { ... } else { ... }`, arms matched by `PatLit`/`PatVariant` text `"true"`/`"false"`, `PatWild` as the default for both sides (5820-5838).
- **enum** → a C `switch (s.zg_tag)`. Arms are **grouped by outer variant** because two `case` labels for one tag is not legal C; everything below the tag is an `if/else` chain inside the case (`match_enum` 5934-6005). Payload is `s.zg_data.zu_m<Variant>`. No wildcard ⇒ `default: zg_unreachable(...)`.
- **scalar** → an `if / else if / else` chain on `s == <literal text>` (5792-5815).

`arm_body` (5788-5816) handles the void case: `elif result is None and value and value not in ("", "0"): self.line("(void)(%s);" % value)` — "an arm whose body is a call returning `()` still has to RUN".

`arm_type` (5689-5736) computes the match's type when nothing expected one: every arm is peeked (`peek_block` for a Block, `peek` otherwise); **literal arms only contribute a fallback**; non-literal arms are merged with `wider_arm`. `wider_arm` (5765-5786) implements the *only* widening: `Res<T>` vs `Res<T,E>` → the two-arg one; `Res<T,E1>` vs `Res<T,E2>` → `Res<T, union_of([E1, E2])>`.

Pattern matching itself: `pat_conds` (5848-5891) recurses to arbitrary depth, producing a `conds` list and a `binds` list. A bare string payload name is a **variant test** if the payload type declares such a variant and a **binding** otherwise (`Left(Blank)` vs `Left(cell)`, 5857-5860).

## 6.4 `.try()`

```python
def ex_Try(self, node, want=None):                              # gen_c.py:6033
    operand = f(node, "operand")
    code, ty = self.expr(operand)
    info = self.e.enum_info(ty) if ty is not None and ty[0] == "named" else None
    if info is None:
        self.e.error(node, "`.try()` needs a Res value")
        return (code, ty)
    variants = info[2]
    names = [v for v, _ in variants]
    ok = "Ok" if "Ok" in names else names[0]
    payload = dict(variants).get(ok)
    tmp = self.new_tmp(ty)
    self.line("%s = %s;" % (tmp, code))
    self.open(
        "if (%s.%stag != %s) {"
        % (tmp, GEN, sym_variant(self.e.variant_parts(ty, ok)))
    )
    self.emit_propagate(node, tmp, ty, ok)
    self.close()
    if payload is None:
        return ("0", UNIT)
    return ("%s.%sdata.%s" % (tmp, GEN, sym_member(ok)), payload)
```

Emits:
```c
Res_T_E zg_t5;
zg_t5 = <operand>;
if (zg_t5.zg_tag != zu_e..Ok) {
    <full-frame unwind>
    return <rebuilt error>;
}
```
and the expression value is `zg_t5.zg_data.zu_m2Ok`.

`emit_propagate` (6057-6094) first `self.unwind_to(0)` — "every early exit is a scope exit", and the error lives in a *temporary*, which is never dropped, so the whole frame can unwind before the return is built. Then it picks the target variant (`Err`, then `None`, then any non-Ok name), and widens the payload with `widen_error`. When widening returns `None`:
```python
self.e.error(node, "no implicit error conversion: this error is not "
                   "part of the set this function returns -- widen the "
                   "declared set, there is no From")
```

Error-set widening (`widen_error` 6104-6140) is four cases: into a structural `("union", ...)` via `into_union` (a `zg_tag<tcode>` / `zg_m<tcode>` assignment), into a named union-of-types enum by variant name, `spread_set` (one nested `?:` arm per member of a named set, recursively, with a `seen` cycle guard), and `per_member` (one arm per structural union member). All produce **pure conditional expressions**, no statements, and the arm order is the declaration's / the sorted union's, so the text is a pure function of the two types.

## 6.5 `bool.then` — not special-cased

There is **no** `then` handling in gen_c. `src/std/core/bool.zen:21` declares
```
then* = <T>(b: bool, f: () T) Res<T> { ... }
```
an ordinary generic function with a body and a closure parameter. It reaches `emit_call` (4153-4231), which at 4153-4231 routes it to inlining:
```python
if any(kind(v) == "Lambda" for v in argnodes) and f(fnode, "body") is not None:
    return self.inline_call(decl, fnode, node, argnodes, targs, want, receiver)
```
`refine(ty, want)` (6285-6300) is what fills `then`'s `T` from the call site when the closure body says nothing — its docstring names `then<T>` explicitly.

## 6.6 Lambdas and closures

Header comment 4038-4043: "a lambda is never a value here: passing one inlines the callee, and calling the parameter it was bound to inlines the lambda."

- `ex_Lambda` (6193-6203) is a hard error: "a closure here would have to escape its frame; an escaping closure needs an Alloc (DESIGN.md)".
- `bind_closure` (4247-4274) binds a parameter name to a marker, **carrying the frame it was written in**:
```python
self.scopes[-1][name] = (name, ("lambda", lam, pty, home,
                                (self.subst, self.parts, self.self_ty),
                                self.floor))
```
  `home` is the caller's depth, taken by `inline_call` **before** it pushes the callee's frame. `self.floor` beside it is where the WRITING function's own body begins, which is not `home`: `home` is where the lambda was written and the floor is where the body it was written in started. `inline_lambda` restores both, so a lambda's `x = ..` on a name its own writer had already bound stays that writer's store. It used to be `len(self.scopes)` read inside `bind_closure`, i.e. after the push, so the rewind below kept the callee's frame and every name the callee bound — its parameters, the receiver bound under the first parameter's name, and its own locals, which `block_value` puts in that same frame — was in scope for a closure written at the call site. `(b > 0).then(() { println("{}", b) })` printed `true`, because `bool.then`'s first parameter is spelled `b`. Pinned by `tests/corpus/std/bool_then_closure_keeps_its_own_names.zen`.
- `inline_call` (4276-4343): resolves type args, `result = new_tmp(ret)`, pushes a scope, binds the receiver to `params[0]`'s name, evaluates non-lambda arguments into declared locals (with `coerce`, so an Arena reaching an `alloc: Alloc` parameter builds the fat record), binds lambda arguments via `bind_closure`, swaps `(subst, parts, self_ty)` to the callee's, emits `{ ... }` around `block_value(body, ret)`, assigns `result`, restores. Guarded by `INLINE_DEPTH` (170-170).
- `inline_lambda` (4345-4409): the arguments are lowered **at the call site** *before* the frame moves; then
```python
home = None
if len(marker) > 4:
    home = (self.scopes, self.subst, self.parts, self.self_ty, self.floor)
    self.scopes = self.scopes[:marker[3]]
    self.subst, self.parts, self.self_ty = marker[4]
    self.floor = marker[5]
```
— the scope stack is truncated back to the depth the closure was *written* at, so `find`'s own `range.loop((h, value){..})` cannot shadow the caller's `h`. Then params are declared and assigned, `{ ... }` is emitted around `block_value(lam.body, ret)`, result assigned, and the frame restored. Handle/`("loop",…)`-typed params are aliased rather than copied (4196-4197).
- The **one** closure that becomes a real C function is a `defer` closure: `Emitter.defer_thunk` (1923-1970). Its body is lowered *before* its capture struct is named, using the `ENVMARK = "\x01env\x01"` placeholder, so two lowerings of one closure compare equal and dedupe through `_defer_cache`; the name is patched in with `.replace(ENVMARK, env or "void")` at 1967-1986. Captures are computed by `captures` (5379-5413) walking the lambda for `Path` nodes that resolve in this frame, excluding names bound inside it, and excluding `lambda`/`loop`/`fn`-typed bindings.

## 6.7 The loop family

`is_loop_shape` (6243-6262) recognises a loop **by shape**, not by module/name: a bodyless function whose last parameter is an `FnType` whose first inner parameter's type is `Named("LoopHandle")`. `emit_call` 4153-4231 routes those to `lower_loop`.

`lower_loop` (4413-4530) — full lowering:

- Inner parameter *names* decide the shape: `wants_index = "index" in names[1:]`, `wants_value`, `wants_acc` (4433).
- Labels `brk`, `cnt` (4436). Non-local exits are `goto`, **not** C `break`/`continue`: "an inlined body can sit inside a `switch` that a match produced, where a C `break` would leave the switch and not the loop" (4417).
- The result type, when nothing asked: `Res<elem>` built from `type_decl("Res", parts, 1)` (1019-1038) — "a loop whose value nothing asked for still HAS one, and the `.match` on it needs its type". `result` is pre-set to `none_of(ret)`.
- Ranged form: three `size_t` temporaries `counter`, `limit`, `base`, then `while (counter < limit) {`. `index` is `(counter - base)` and `value` is the range's element — "on `Range(10, 13)` they are 0,1,2 and 10,11,12" (4478).
- `wants_index` without a range: `counter = 0` then `for (;;)`.
- A parameterless leading lambda is a `while cond`: `for (;;) { <cond inlined>; if (!c) { goto brk; } ...` (3936-3942).
- Otherwise `for (;;)`.
- `self.loops.append((brk, cnt, result, ret, acc, len(self.dscopes)))` and the handle is `("loop", len(self.loops))`.
- The body is inlined via `inline_lambda` at the accumulator's type; `acc` is re-assigned from the body's value.
- Tail: `cnt: ;`, `counter = counter + 1;`, `}`, `brk: ;`, then `result = ok_of(ret, acc)`.

`lower_handle` (5321-5348) lowers `h.next()` / `h.break(v)`:
```python
if name == "next":
    self.unwind_to(ddepth)
    self.line("goto %s;" % cnt)
    return ("0", UNIT)
if name == "break":
    ... self.line("%s = %s;" % (result, self.ok_of(ret, code, node)))
    self.unwind_to(ddepth, code)
    self.line("goto %s;" % brk)
    return ("0", UNIT)
```
Both unwind the RAII/defer scopes down to the loop's own depth first.

`range_value` (5270-5301): an array walks `base.zg_elems[counter]`; a named Range with no `at` walks its own index space (`counter` as `usize`) — "which is what makes `Range(0, 5)` a bare C for-loop"; otherwise `at(counter)` is called and a non-`Ok` result `goto`s the break label.

## 6.8 Other expression forms worth pinning

- **`&&` / `||`** — short-circuit with the RHS's *statements* guarded (3097-3106):
```python
lcode, _ = self.expr(lhs, prim("bool"))
tmp = self.new_tmp(prim("bool"))
self.line("%s = %s;" % (tmp, lcode))
self.open("if (%s%s) {" % ("" if op == "&&" else "!", paren(tmp)))
rcode, _ = self.expr(rhs, prim("bool"))
self.line("%s = %s;" % (tmp, rcode))
self.close()
return (tmp, prim("bool"))
```
- **Assignment as expression** (`ex_Binary` 3159-3211) emits the store and returns the target.
- **Binary spine** (3107-3141) is walked with an explicit loop, not recursion — "`a + b + c + ..` is LEFT-nested, so one python frame per term turns a long line into a RecursionError -- and 'a crash is not a diagnostic'". The type hint propagates down the spine only through `ARITH`/`WRAPPING` ops; at the base, an unannotated int literal on the left takes its width from a peek of the right operand (3115-3119).
- **`==` on a named type** becomes the `Eq` impl's `eq` call, statically resolved (`eq_call`, 3754-3768); `!=` wraps it in `(!...)`. "a C `==` on a struct is not even legal C."
- **`consume x`** (`ex_Consume`, 3151-3157) is a no-op on the value; it calls `kill_drop` to clear the drop flag.
- **Struct literal** (`construct_type`, 3290-3329): `((T){ .zu_mx = ..., .zu_my = ... })`, in **declared field order**, positional args filled by index, `((T){0})` when nothing is supplied.
- **Fixed array / array literal** (`ex_FixedArray`/`ex_ArrayLit` 6212-6222): `((T){ { e0, e1 } })` — note the doubled brace for the `zg_elems` member.
- **`ex_Record`** (6224-6228) and **`ex_MetaCall`** (6237-6239) are errors.
- `paren` (6374-6377) only wraps when the code is neither an identifier nor already fully parenthesised.
- `int_literal` (6396-6415): unsigned always `((uint32_t)5ULL)`; `INT_MIN` spelled `((int32_t)(-2147483647LL - 1LL))`; otherwise `((int32_t)5LL)`. Gated by `tests/corpus/codegen/literal_boundaries_{signed,unsigned}.zen`.

## 6.9 RAII / drop / defer interleaving

`FnCtx.dscopes` / `sscopes` (2356-2359) follow the **emitted braces**, not `self.scopes` (which `inline_lambda` rewinds). `track_drop` (2443-2451) registers only `let` bindings whose type has a direct `Drop` impl; a name `consume`d anywhere program-wide gets an `int zg_liveN = 1;` flag (`track_drop` 2443-2451, `consumed_names` 1470-1487 is deliberately a program-wide over-approximation: "Over-approximating costs an unread `int` on a frame; under-approximating costs a double free"). `exit_scope` (2489-2496) runs `zg_scope_run(&rec)` **before** any drop, then `unwind` walks the block's entries in reverse declaration order, skipping any binding whose C name appears in the block's value expression:
```python
for cname, ty, flag in reversed(entries):
    if keep and re.search(r"\b%s\b" % re.escape(cname), keep):
        continue
    self.emit_drop(cname, ty, flag)
```

---

# 7. The runtime prologue — literal

`BANNER` (6499-6516), formatted with `C_STANDARD`:
```c
/* Generated by the Zen bootstrapper (bootstrap/gen_c.py).  Do not edit.
 *
 * Language: C99 (ISO/IEC 9899:1999).  Compile with -std=c99.
 *
 * This file is deterministic: the same sources produce byte-identical C.
 * It contains no timestamp, no absolute path and no address; every position
 * below is a literal string taken from the AST, relative to the compilation
 * root.  See tests/determinism/README.md.
 *
 * Every identifier derived from Zen source is mangled behind `zu_`, and every
 * identifier this compiler invents is behind `zg_`.  Neither begins with an
 * underscore, so neither collides with the identifiers C11 7.1.3 reserves to
 * the implementation, and no C keyword or standard-header macro can reach the
 * output.  `main` is the one name the C standard fixes.
 */
```

`INCLUDES` (6518-6526) — exactly six, always:
```c
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
```

`PRELUDE_TYPES` (6528-6540) — always:
```c
/* ---- runtime ---- */

typedef struct zg_str { unsigned char *data; size_t len; } zg_str;

/* A trait value is a fat value (DESIGN.md): a receiver plus function
 * pointers, copied by value, never boxed and never allocated. */
typedef struct zg_closure { void *fn; void *env; } zg_closure;

static int zg_argc;
static char **zg_argv;
```

`PRELUDE_TRAP` — always (quoted in full in §3.1).

`PRELUDE_SCOPE` (6583-6593) — only when `"scope" in self.needs`:
```c
/* `@scope` is the enclosing block as a value (DESIGN.md), so a Scope is a
 * pointer to the block's own record.  The record holds the deferred closures
 * AND their captures: the closure outlives the frame that registered it, and
 * the block outlives the closure by construction, so the block is the only
 * storage that is certainly still alive -- which is why defer needs no
 * allocator and no escaping-closure machinery. */
typedef struct zg_scope zg_scope;
#define ZG_DEFER_MAX 32
```

`DEFER_RUNTIME` (6595-6628) — emitted at the end of `defer_section()`, *after* the per-site `zg_envN` structs and the `zg_defer_env` union:
```c
typedef struct zg_defer_slot {
    void (*zg_fn)(void *);
    zg_defer_env zg_env;
} zg_defer_slot;

struct zg_scope {
    int zg_n;
    zg_defer_slot zg_slot[ZG_DEFER_MAX];
};

static void zg_defer(zg_scope *s, void (*fn)(void *), const void *env,
                     size_t n, const char *file, unsigned long line,
                     unsigned long col) {
    if (s->zg_n >= ZG_DEFER_MAX)
        zg_trap(file, line, col, "too many deferred closures on one block");
    s->zg_slot[s->zg_n].zg_fn = fn;
    if (n) memcpy(&s->zg_slot[s->zg_n].zg_env, env, n);
    s->zg_n++;
}

/* LIFO, and BEFORE the block's drops.  The slot is copied out and the count
 * lowered before the call, so a closure that registers another one on the
 * same block reuses the slot it is standing in without overwriting its own
 * captures -- and running an already-run scope is a no-op. */
static void zg_scope_run(zg_scope *s) {
    while (s->zg_n > 0) {
        zg_defer_slot slot = s->zg_slot[s->zg_n - 1];
        s->zg_n--;
        slot.zg_fn(&slot.zg_env);
    }
}
```
The union header (`defer_section` 2098-2118):
```python
out.append("typedef union %sdefer_env {\n    char %snone;\n" % (GEN, GEN))
for n in sorted(self.defer_envs):
    out.append("    %senv%d %su%d;\n" % (GEN, n, GEN, n))
out.append("} %sdefer_env;\n\n" % GEN)
```
— "A slot's env is a union over every capture record in the program, so it is exactly as large and as aligned as the largest one -- no guessed byte count".

`PRELUDE_PRINT` (6630-6641) — only when `"print" in self.needs`:
```c
/* println: std owns this once it exists (DESIGN.md routes it through the Env
 * in scope).  Until then these are the writes gen_c lowers `{}` into: decimal
 * with no separators, and exactly one newline per println. */
static void zg_print_bytes(const char *s, size_t n) { fwrite(s, 1, n, stdout); }
static void zg_print_i64(int64_t v) { fprintf(stdout, "%lld", (long long)v); }
static void zg_print_u64(uint64_t v) { fprintf(stdout, "%llu", (unsigned long long)v); }
static void zg_print_f64(double v) { fprintf(stdout, "%g", v); }
static void zg_print_bool(bool v) { zg_print_bytes(v ? "true" : "false", v ? 4u : 5u); }
static void zg_print_nl(void) { fputc('\n', stdout); }
```

## Allocation

There is **no allocator in the prelude**. `malloc`/`free` appear only in `lower_mem` (4826-4893), the lowering of the three bodyless `Mem` members:
- `Mem.alloc` → `malloc(sizeof(State))`, initialise `mem`/`head`/`next`, return `((Arena){ .zu_mstate = p })`.
- `Mem.page` → `malloc(sizeof(Page) + size)`, `Err(<first payloadless variant of Err's type>)` on NULL, else fill `prev`/`base`/`size` and return `Ok((Page *)raw)`.
- `Mem.release` → `free((void *)p);`.

Everything above that (Arena, Vec, String, Map) is ordinary Zen. `alloc.create<T>()` is lowered to `raw(sizeof(T), 16)` + `Ptr.to` (`lower_create` 4743-4770; the `16` is hardcoded ALIGN_MAX). `Ptr<T>`'s members are lowered to C directly (`ptr_method` 3910-3961): `read`→`p[i]`, `write`→`p[i] = v;`, `offset`→`(p + n)`, `back`→`(p - n)`, `bytes`→`(sizeof(T) * (size_t)n)`, `copy_from`→`memcpy(...)`, `is_null`→`(p == NULL)`, `to<U>`→`((U *)p)`.

## The `main` shim (`entry_point`, 2265-2313)

```python
body = ["int main(int argc, char **argv) {\n"]
body.append("    %sargc = argc;\n    %sargv = argv;\n" % (GEN, GEN))
call = "%s(%s)" % (cname, ", ".join(args) if nparams else "")
info = self.enum_info(ret) if ret[0] == "named" else None
if info:
    names = [v for v, _ in info[2]]
    ok = "Ok" if "Ok" in names else names[0]
    body.append("    %s r = %s;\n" % (self.ctype(ret), call))
    payload = dict(info[2]).get(ok)
    if payload is not None and is_int(payload):
        body.append("    if (r.%stag == %s) return (int)r.%sdata.%s;\n" % ...)
    else:
        body.append("    if (r.%stag == %s) return 0;\n" % ...)
    body.append("    return 1;\n")
elif is_int(ret):
    body.append("    return (int)%s;\n" % call)
else:
    body.append("    %s;\n    return 0;\n" % call)
body.append("}\n")
```
Zen `main`'s parameters are passed zeroed (`(T){0}` or `0`, 2234). A `Res`-returning main exits `1` on error; a `Res<i32,…>` main returns the Ok payload.

---

# 8. Special cases that smell test-driven

Ranked roughly by how load-bearing they are for a reimplementation:

1. **`_sibling` import shim** (117-149). `bootstrap/ast.py` shadows stdlib `ast`, and `dataclasses`→`inspect`→`ast`, so the shadowing is an *import error at startup*, not a style issue. Package import first, file-path load as fallback.
2. **Binary spine walked with a loop** (3107-3141). Explicitly: "one python frame per term turns a long line into a RecursionError -- and 'a crash is not a diagnostic' (TESTING.md). Raising the interpreter's limit only moves the number."
3. **`MAX_EXPR_DEPTH = 24` spilling** (169-169) plus `spill` along a folded spine (3213-3222). "per TESTING.md"; `tests/corpus/codegen/nesting_expr.zen`.
4. **`ex_Block` double-lowering** (5635-5660). The comment names the failure exactly: "a `.match` whose arms are ALL blocks therefore types as `()`: no result temporary is allocated and every arm's value is dropped, with no diagnostic and a zero in its place."
5. **`arm_type` consults every arm, not the first informative one** (`arm_type` 5689-5736): "`true => Ok(())` beside `false => report(n)` types the match `Res<()>`, and the second arm's `Res<(), AllocError>` then has nowhere to go".
6. **`by_param_types` overload scoring** (4012-4065): "`digit(d: u64)` beside `digit(d: i64)` ... Resolving them by file order picks the wrong one half the time, and on `0 - (v % 10)` that is a spurious trap." Score is `(-bad, hits)`; numeric literals and lambdas contribute `None`.
7. **The literal-width hint from the *other* operand** (3115-3119): "`0 - (v % 10)` on an i64 stays an i64 instead of being narrowed to the literal's default and trapping."
8. **`type_member` reads a constant at its declared type** (2902-2917): "`MAX*: i64 = 9223372036854775807` ... Lowering it at the literal's default width truncates the value and, worse, makes the arithmetic that follows unable to overflow -- the trap silently stops existing."
9. **`Ptr.to<U>` must change the element type** (`ptr_method` 3910-3961) — the longest bug postmortem in the file: "Arena.realloc reads its usize header through `.to<usize>()`, so as a no-op that read is ONE BYTE, and every Vec whose buffer reaches 256 bytes silently loses the rows written before each grow -- `512 & 0xFF == 0`, so `keep` is 0 and copy_from copies nothing."
10. **`_LVALUE` accepting `(*p).f.g`** (`_LVALUE` is gone -- commit 0109bc2a replaced the regex with `_is_lvalue` (6350-6362), whose comment above it now carries this postmortem): "Missing it copies the field into a temporary, so `self.entries.add(..)` grows a copy and the caller keeps the old one -- a silent wrong answer rather than a compile error."
11. **`ENVMARK` (175) + `_defer_cache` (876, 1955-1969)**: "a thunk registered by a discarded lowering would otherwise sit in the output as an unreferenced static."
12. **`peek` (3457-3478) / `peek_block` (3480-3499) roll back diagnostics** — plus seven other ad-hoc `mark = len(self.diags)` / `del self.diags[mark:]` pairs at 1424/1454, 1547/1555, 3644/3647, 3928/3930, 5062/5065, 5143/5147, 5319/5309. Speculative work must report nothing.
13. **`bind_closure` carries the scope depth and the `(subst, parts, self_ty)` triple** (`bind_closure` 4247-4274), restored by `inline_call` (4276-4343): "`find`'s own `range.loop((h, value) { .. })` would otherwise shadow a caller's `h` -- silently, with a different value rather than with an error."
14. **`h.break`/`h.next` are `goto`, not `break`/`continue`** (4416-4419): an inlined body can sit inside a match's `switch`.
15. **Enum tag constants keyed on the declaration, not the instance** (1294): "Res<i32, E> and Res<i32, F> share `Ok`, and emitting the constant per instance is a C redefinition."
16. **Empty struct gets `char zg_pad;`** (composed, never written: 2124, 2129-2131) and zero-length array becomes `[1]` (2162) — `tests/corpus/codegen/struct_return_zero_field.zen`.
17. **`Ok(())` drops its payload** (1296, 4141): "a void member is illegal C".
18. **`_block_body`'s trailing-`ExprStmt`-as-value rule** (2554) and the `rty == UNIT` → `(void)(...)` rule (2581-2586): "`() { cleanup(x) }` emitting nothing at all."
19. **`emit_types` loops up to 8 times** (2120-2143) because emitting a definition can register a new type; `topo` (2145-2168) breaks a by-value cycle by name *and* reports a diagnostic, so emission still terminates.
20. **`entry_point()` computed before `emit_types()`** (2120-2143): "`main` first: it can register one last type."
21. **`emit()` seeds from `main` only** (1730-1734): "keeps an unused std member -- one supplied by an impl gen_c cannot dispatch yet -- from failing a program that never calls it."
22. **`consumed_names` is program-wide** (1470-1487), not per-function, because bodies arrive inlined into their callers.
23. **`unwind(keep=...)` regex-scans the block's value expression** (`unwind` 2476-2487): "Leaving it undropped leaks; dropping it is a use-after-free, and only one of those two is recoverable."
24. **`c_string` uses octal, never hex** (6476-6492) — partly to keep the determinism scanner's pointer-shaped-hex check quiet.
25. **`is_tparam` heuristic fallback** (3516-3524): `len(name) <= 2 and name[0].isupper()`. Explicitly acknowledged as insufficient — "`signed = <unsigned>(typedef: unsigned) unsigned` is generic in `unsigned`, and a shape heuristic cannot know that" — hence the `tparams` argument threaded through `unify`.
26. **`emit_call`'s bodyless-with-owner path** (4153-4231) emits `memset(&tmp, 0, sizeof tmp);` alongside the diagnostic "gen_c has no trait dispatch yet" — a placeholder value so the surrounding C still compiles.
27. **`full_of` picks `IoError.Full`** (4618): two error sets meet at `add`, DESIGN.md has no conversion, so the reason is *named* rather than invented.
28. **`console_sink` with `self = NULL`** (4805-4832) and `console_thunk` (1651-1680): the runtime *is* the Sink impl; printing a Display allocates nothing.
29. **`lower_print`'s hole/argument mismatch tolerance** (`lower_print` 5506-5542): a `{}` with no argument prints the literal `"{}"`; extra arguments are appended.
30. **`fmt_pieces`** (4564-4577): the *entire* format language — `{}` is a hole, "every other byte -- including a lone `{` and every `}` -- is literal."
31. **`module_named` three-tier search** (2990-3013): last path component, then a one-hop alias whose target names a module, then any component — "so a type never loses to a module".

### Code-quality oddities you should not replicate

- **`_lower_intrinsic` (5158-5207)**: the `if decl.owner == "Mem"` block sits *above* the triple-quoted string, so that string is not a docstring at all — it is a no-op expression statement in the middle of the function.
- **`lower_mem` line 4826-4893**: `self.e.convert(value, None, mt) if False else value` — a permanently-dead conditional.
- **`lower_loop` line 4413-4530**: `values = [(handle[0] and "0", handle)]` — `handle[0]` is the constant string `"loop"`, so this is an obfuscated `("0", handle)`.
- **`emit_fn` line 1869**: `"return (%s){0};" % self.ctype(ret) if ret[0] != "prim" else "return 0;"` — the `%` binds tighter than the ternary, so the format applies to the first branch only; it works, but it reads as a bug.
- **`range_bounds` line 5209-5231** returns `("0", str(ty[1]))` — the array length as a *decimal string*, not a C expression, relying on the caller only interpolating it.
- **`sym_value`** (270) is dead code.
- **`Emitter.thunk`'s `slot` parameter** (1598) is unused; same for `console_thunk`'s `slot` (1651).
