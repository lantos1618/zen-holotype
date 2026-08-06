"""bootstrap/own.py -- the ownership checker.  `PLAN.md` stage 3.

Three features, one checker, one question: *what is this binding allowed to
do?*  `DESIGN.md`'s Ownership section is the law; this is one throwaway
implementation of it, run after sema and before gen_c.

    self :: @Self   a method that writes the receiver's OWN BYTES needs a
                    mutable receiver.  Shallow: a handle's methods are `:`
                    even when they change the world, so `Vec.grow` calling
                    `realloc` through an immutable `alloc` field compiles.
                    The test is `DESIGN.md`'s: would a bitwise copy of the
                    receiver see the change?  Here that is answered by
                    reading the DECLARATION -- never inferred from a body,
                    because an inferred requirement changes when the body
                    changes and silently breaks callers in other modules.

    consume         moves.  `drop` runs exactly once, so a `Drop` value
                    cannot be copied and a consumed binding is dead from the
                    move onwards.  Passing to a parameter is a BORROW.

    sendability     only `val` or `iso` crosses an actor boundary.  Actors
                    are stage 5 and `Ref` does not exist yet, so the SEND
                    side of this is not implemented -- see "Not yet" below.
                    The `consume` half already works: a send is a move, and
                    a move is a move whoever performs it.

Everything interesting is control flow, so the core is a small forward
dataflow over the AST.  The lattice is the set of DEAD PLACES; the join is
UNION -- `dead on any incoming path => dead after the join` -- and a loop
body is iterated to a fixpoint so the back edge is real.  It is
FLOW-SENSITIVE, NOT PATH-SENSITIVE: no condition is ever evaluated to decide
an edge is dead, so acceptance never depends on how clever constant folding
was that day.

A PLACE is a binding root plus a fixed field path: `p`, `p.left`.  A field is
a place the checker can name; an array ELEMENT is not, because the index is a
runtime value -- which is why `consume bufs[0]` is rejected outright rather
than tracked.

Not yet, and deliberately not faked:

    * the send check itself (`x is not sendable`).  `Actor`, `Context` and
      `Ref` are stage 5; there is no behavior to recognise a send at, and a
      checker that guessed from a method name would be a gate that cannot go
      red for the right reason.
"""

from __future__ import annotations

from bootstrap import ast as A
from bootstrap.ast import Diag

__all__ = ["check"]

# A closure body is walked at most this many times before the fixpoint is
# declared reached.  The lattice is a finite set of places and the transfer
# functions are monotone, so this is a guard against a bug in this file, not a
# limit on any program.
_FIXPOINT_ROUNDS = 8


# ---------------------------------------------------------------------------
# places
# ---------------------------------------------------------------------------


def _place_of(node):
    """The place an expression names, as `(root, field, field, ..)`, or None.

    Only a binding root and fixed field selections are places.  A call result
    is a temporary and an index is not a fixed selection, so neither is one.
    """
    if isinstance(node, A.Path):
        return (node.name,)
    if isinstance(node, A.Member):
        base = _place_of(node.base)
        return base + (node.name,) if base is not None else None
    return None


def _show(place):
    return ".".join(place)


def _dead_prefix(state, place):
    """The longest already-dead prefix of `place`, or None.

    `p.left` being dead makes `p.left.id` dead too: reading through a hole is
    the same use-after-move as reading the hole.
    """
    for i in range(1, len(place) + 1):
        if place[:i] in state:
            return place[:i]
    return None


def _revive(state, place):
    """`place` is whole again -- a fresh binding, or a write into the hole."""
    return frozenset(
        p for p in state if p[: len(place)] != place
    )


class _Bind:
    """One binding in scope: what it is allowed to do, and where it was
    written so a diagnostic can point at it."""

    __slots__ = ("name", "span", "mutable", "is_param", "is_scope", "depth")

    def __init__(self, name, span, mutable, is_param, is_scope, depth):
        self.name = name
        self.span = span
        self.mutable = mutable
        self.is_param = is_param
        self.is_scope = is_scope
        self.depth = depth


# ---------------------------------------------------------------------------
# the checker
# ---------------------------------------------------------------------------


class _Checker:
    def __init__(self, graph, sema, root=""):
        self.graph = graph
        self.sema = sema
        self.root = root
        self.diags = []
        self.quiet = 0
        self._ctors = None
        self._declared = []      # per-block, for the partial-move check

        # per-function state, saved and restored around every nested lambda
        self.binds = {}
        self.ctx = None
        self.mod = None
        self.fn_name = ""
        self.self_mutable = None  # None when the function has no `self`
        self.lambda_depth = 0
        self.escaping = []  # ((names visible at the escape boundary), ..)

    # -- diagnostics --------------------------------------------------------

    def error(self, span, message, notes=()):
        """Collected, never raised (`CONTRACT.md`): one bad function is not
        the run."""
        if self.quiet or span is None:
            return
        self.diags.append(Diag(span=span, message=message, notes=tuple(notes)))

    def results(self):
        seen, out = set(), []
        for d in self.diags:
            key = (d.span.file, d.span.start, d.message)
            if key in seen:
                continue
            seen.add(key)
            out.append(d)
        out.sort(key=lambda d: (d.span.file, d.span.start, d.message))
        return tuple(out)

    # -- sema queries -------------------------------------------------------
    #
    # sema is asked, never re-implemented.  Every query runs muted: sema has
    # already reported everything it has to say, and a second opinion on the
    # same node would be a duplicate diagnostic with a worse span.

    def type_of(self, node):
        if node is None or self.ctx is None:
            return None
        try:
            return self.sema.type_of(node, self.ctx)
        except Exception:
            return None

    def typedef_of(self, ty):
        """The declaration a type came from.

        A qname sema could not qualify comes back as `@Vec` -- it means "the
        Vec that is in scope somewhere", so the tree-wide index by name and
        arity is the fallback, and it is the same index sema itself falls back
        to (`builtin_named`).
        """
        if ty is None:
            return None
        try:
            if ty.kind == "prim":
                return self.sema.prim_decls.get(ty.name)
            if ty.kind != "named":
                return None
            td = self.sema.types.get(ty.name)
            if td is not None:
                return td
            base = ty.name.rsplit(".", 1)[-1].lstrip("@")
            index = self.sema.global_by_name
            return index.get((base, len(ty.args))) or index.get((base, None))
        except Exception:
            return None

    def field_of(self, ty, name):
        td = self.typedef_of(ty)
        if td is None:
            return None
        for f in td.fields:
            if isinstance(f, A.Field) and f.name == name:
                return f
        return None

    def methods_of(self, ty, name):
        """Every declaration of `name` reachable through a dot on `ty`.

        A method is a `Function` in the struct's own field tuple, or an entry
        an impl supplies.  Free ufcs functions are deliberately NOT consulted:
        resolving them means redoing overload resolution, and a wrong answer
        there would reject a correct program.
        """
        td = self.typedef_of(ty)
        if td is None:
            return ()
        out = []
        for f in td.fields:
            if isinstance(f, A.Function) and f.name == name:
                out.append(f)
        try:
            impls = self.sema.impls_of(td.qname)
        except Exception:
            impls = ()
        for im in impls:
            for e in getattr(im, "entries", ()) or ():
                if isinstance(e, A.Function) and e.name == name:
                    out.append(e)
        return tuple(out)

    def implements(self, ty, trait_name):
        td = self.typedef_of(ty)
        if td is None:
            return False
        try:
            impls = self.sema.impls_of(td.qname)
        except Exception:
            return False
        for im in impls:
            trait = getattr(im, "trait_name", None) or getattr(im, "trait", "")
            if str(trait).rsplit(".", 1)[-1] == trait_name:
                return True
        return False

    def is_drop(self, ty):
        """A type the compiler calls `drop` on -- so a copy would drop twice.

        A handle is not one: `Alloc` is an interface and an `Alloc` value is
        two words pointing at an arena.  The ARENA is `Drop`.
        """
        return self.implements(ty, "Drop")

    def is_alloc(self, ty):
        """The `Alloc` interface, or anything that implements it -- an Arena
        passed straight to `spawn` is still the Alloc the escaping closure
        needs."""
        if ty is None:
            return False
        name = str(getattr(ty, "name", "") or "")
        return (name.rsplit(".", 1)[-1].lstrip("@") == "Alloc"
                or self.implements(ty, "Alloc"))

    def is_scope_ty(self, ty):
        if ty is None:
            return False
        name = getattr(ty, "name", "") or ""
        return str(name).rsplit(".", 1)[-1] == "Scope"

    def is_struct_name(self, name):
        try:
            td = self.sema.lookup_type(self.mod, name)
        except Exception:
            return False
        return td is not None and getattr(td, "kind", "") == "struct"

    # -- mutability ---------------------------------------------------------

    def place_mutable(self, node):
        """May this expression be written through?

        Mutability composes down the path: every link from the binding to the
        receiver has to permit the write.  Anything the checker cannot name --
        a call result, an unknown field -- is a temporary or an unknown, and
        both are permissive: rejecting what is not understood turns a checker
        into a wall.
        """
        if isinstance(node, A.Path):
            bind = self.binds.get(node.name)
            return True if bind is None else bind.mutable
        if isinstance(node, A.Member):
            field = self.field_of(self.type_of(node.base), node.name)
            if field is None:
                return True  # a method, an impl-supplied name, or unknown
            return bool(field.mutable) and self.place_mutable(node.base)
        if isinstance(node, A.Index):
            return self.place_mutable(node.base)
        return True  # a temporary is uniquely this expression's own

    def root_span(self, node):
        """The first byte of the place, which is the root identifier.  A
        `Member` span already starts there; this keeps that true if it ever
        stops being."""
        while isinstance(node, (A.Member, A.Index)):
            node = node.base
        return node.span if isinstance(node, A.Node) else None

    # ======================================================================
    # entry
    # ======================================================================

    def run(self):
        sema = self.sema
        # sema's instantiation sets are gen_c's input.  Asking `type_of` a
        # question can instantiate, so the sets are restored afterwards and
        # this pass is invisible downstream.
        saved_fns = dict(getattr(sema, "fn_instances", {}) or {})
        saved_types = dict(getattr(sema, "type_instances", {}) or {})
        ndiags = len(getattr(sema, "diags", []) or [])
        sema._muted = getattr(sema, "_muted", 0) + 1
        try:
            for mi in sorted(getattr(sema, "mods", ()), key=lambda m: m.dotted):
                try:
                    self.check_module(mi)
                except Exception as exc:  # never raise: one bad module is not the run
                    self.error(getattr(mi.node, "span", None),
                               "internal error in the ownership checker: %s" % (exc,))
        finally:
            sema._muted -= 1
            sema.fn_instances = saved_fns
            sema.type_instances = saved_types
            del sema.diags[ndiags:]
        return self.results()

    def check_module(self, mi):
        self.mod = mi
        node = getattr(mi, "node", None)
        if node is None:
            return
        for decl in getattr(node, "decls", ()) or ():
            if isinstance(decl, A.Function):
                self.check_fn(decl, None)
            elif isinstance(decl, A.Struct):
                for f in decl.fields:
                    if isinstance(f, A.Function):
                        self.check_fn(f, self.self_ty_of(mi, decl.name))
            elif isinstance(decl, A.Impl):
                target = self.self_ty_of(mi, decl.target)
                for e in decl.entries:
                    if isinstance(e, A.Function):
                        self.check_fn(e, target)

    def self_ty_of(self, mi, name):
        """`@Self` for a method declared on `name`, as sema spells it."""
        try:
            td = self.sema.lookup_type(mi, name)
        except Exception:
            return None
        if td is None:
            return None
        import bootstrap.sema as S

        return S.named(td.qname, tuple(
            S.var_ty(getattr(tp, "name", "T")) for tp in td.tparams))

    # -- one function -------------------------------------------------------

    def check_fn(self, fn, self_ty):
        if fn.body is None:
            return
        import bootstrap.sema as S

        subst = (("@Self", self_ty),) if self_ty is not None else ()
        ctx = S.Ctx(self.mod, S.Scope(), subst=subst, quiet=True)
        self.ctx = ctx
        self.binds = {}
        self.fn_name = fn.name
        self.self_mutable = None
        self.lambda_depth = 0
        self.escaping = []

        for p in fn.params:
            ty = None
            if p.ty is not None:
                try:
                    ty = self.sema.resolve_type(p.ty, ctx, want_error=False)
                except Exception:
                    ty = None
            ctx.scope.put(p.name, S.Sym("value", ty or S.ANY, mutable=bool(p.mutable)))
            self.binds[p.name] = _Bind(p.name, p.span, bool(p.mutable), True,
                                       self.is_scope_ty(ty), 0)
            if p.name == "self":
                self.self_mutable = bool(p.mutable)

        try:
            state = self.block(fn.body, frozenset(), new_scope=False)
        except RecursionError:
            return
        except Exception as exc:
            self.error(fn.span,
                       "internal error in the ownership checker: %s" % (exc,))
            return

        # `@scope` is the enclosing BLOCK as a value, so handing it back to a
        # caller hands back a frame that is already gone.
        self.check_no_scope_escapes(fn.body.value)

    def check_no_scope_escapes(self, value):
        if isinstance(value, A.ScopeRef):
            self.error(value.span, _SCOPE_ESCAPES)
        elif isinstance(value, A.Path):
            bind = self.binds.get(value.name)
            if bind is not None and bind.is_scope:
                self.error(value.span, _SCOPE_ESCAPES)

    # ======================================================================
    # the dataflow
    # ======================================================================

    def visit(self, node, state):
        if node is None or not isinstance(node, A.Node):
            return state
        handler = _HANDLERS.get(type(node).__name__)
        if handler is not None:
            return handler(self, node, state)
        for child in A.children(node):
            state = self.visit(child, state)
        return state

    def visit_all(self, nodes, state):
        for n in nodes:
            state = self.visit(n, state)
        return state

    # -- uses ---------------------------------------------------------------

    def use(self, node, state):
        """Reading a place.  A dead place has no value to read: the move
        already handed it to someone else, and `drop` runs exactly once."""
        place = _place_of(node)
        if place is None:
            return state
        if place[0] not in self.binds:
            return state
        dead = _dead_prefix(state, place)
        if dead is not None:
            self.error(self.root_span(node),
                       "%s was consumed: the move ended that name, and drop "
                       "runs exactly once" % _show(dead))
        self.check_scope_capture(node, place)
        return state

    def check_scope_capture(self, node, place):
        """A `Scope` may be passed INWARD but never captured by a closure that
        outlives the block -- one direction only, down the stack."""
        if not self.escaping:
            return
        bind = self.binds.get(place[0])
        if bind is None or not bind.is_scope:
            return
        if place[0] in self.escaping[-1]:
            self.error(self.root_span(node), _SCOPE_ESCAPES)

    # -- statements ---------------------------------------------------------

    def block(self, node, state, new_scope=True):
        import bootstrap.sema as S

        saved_binds = dict(self.binds) if new_scope else None
        saved_ctx = self.ctx
        if new_scope:
            self.ctx = self.ctx.with_scope(self.ctx.scope.child())
        declared = []
        self._declared.append(declared)
        try:
            state = self.visit_all(node.stmts, state)
            state = self.visit(node.value, state)
            state = self.partial_moves(declared, state)
        finally:
            self._declared.pop()
            if new_scope:
                self.binds = saved_binds
                self.ctx = saved_ctx
        return state

    def partial_moves(self, declared, state):
        """A partially moved value reaching the end of its scope.

        `drop` runs on the whole value, and the moved field is not there to
        drop.  Move all of it or none of it.
        """
        for bind in declared:
            place = (bind.name,)
            if place in state:
                continue  # moved whole: nothing left here to drop
            if any(p[: 1] == place and len(p) > 1 for p in state):
                self.error(bind.span,
                           "%s is partially moved: drop runs on the whole "
                           "value, so move all of it or none of it" % bind.name)
        return state

    def v_block(self, node, state):
        return self.block(node, state)

    def v_let(self, node, state):
        name = node.name
        if not isinstance(name, str):
            # `self.len = ..` parses as a Let with a place for a name
            return self.assign(name, node.value, state)
        state = self.visit(node.value, state)
        self.check_copy(node.value, state)
        self.declare(name, node, state)
        return _revive(state, (name,))

    def declare(self, name, node, state):
        import bootstrap.sema as S

        ty = self.type_of(node.value)
        if node.ty is not None:
            try:
                ty = self.sema.resolve_type(node.ty, self.ctx, want_error=False) or ty
            except Exception:
                pass
        self.ctx.scope.put(name, S.Sym("value", ty or S.ANY,
                                       mutable=bool(node.mutable)))
        is_scope = self.is_scope_ty(ty) or isinstance(node.value, A.ScopeRef)
        bind = _Bind(name, node.span, bool(node.mutable), False, is_scope,
                     self.lambda_depth)
        self.binds[name] = bind
        if self._declared:
            self._declared[-1].append(bind)

    def check_copy(self, value, state):
        """`g = f` on a `Drop` type cannot copy -- both would drop.

        There is no `Clone`: want a second one, construct a second one.  The
        move is written at the use site, and only there.
        """
        if _place_of(value) is None:
            return
        if not self.is_drop(self.type_of(value)):
            return
        self.error(value.span,
                   "cannot copy a Drop value: drop runs exactly once, so write "
                   "`consume` to move it, or construct a second one")

    def v_expr_stmt(self, node, state):
        return self.visit(node.expr, state)

    # -- expressions --------------------------------------------------------

    def v_path(self, node, state):
        return self.use(node, state)

    def v_member(self, node, state):
        if _place_of(node) is not None:
            return self.use(node, state)
        return self.visit(node.base, state)

    def v_index(self, node, state):
        state = self.visit(node.base, state)
        return self.visit(node.index, state)

    def v_binary(self, node, state):
        if node.op == "=":
            return self.assign(node.lhs, node.rhs, state)
        state = self.visit(node.lhs, state)
        return self.visit(node.rhs, state)

    def assign(self, target, value, state):
        state = self.visit(value, state)
        if target is None:
            return state
        if not self.place_mutable(target):
            root = target
            while isinstance(root, (A.Member, A.Index)):
                root = root.base
            if (isinstance(root, A.Path) and root.name == "self"
                    and self.self_mutable is False):
                # the requirement is DECLARED, never inferred from the body:
                # upgrading `bump` to `::` here would silently break every
                # caller in another module the next time the body changes.
                self.error(target.span, _MUT_RECEIVER % self.fn_name)
            else:
                self.error(target.span,
                           "cannot write through an immutable binding: `%s` is "
                           "declared `:`, and `::` is what permits a write"
                           % _show(_place_of(target) or ("<place>",)))
        place = _place_of(target)
        if place is not None:
            state = _revive(state, place)
        return state

    def v_consume(self, node, state):
        operand = node.operand
        if isinstance(operand, A.Index):
            # the index is a runtime value, so "which element is dead" is not
            # a fact the compiler holds -- and the array still drops them all
            self.error(operand.span,
                       "cannot consume an array element: the index is a runtime "
                       "value, so the compiler cannot know which element died")
            return self.visit(operand, state)
        place = _place_of(operand)
        if place is None:
            return self.visit(operand, state)
        bind = self.binds.get(place[0])
        if len(place) > 1 and (bind is None or bind.is_param):
            # you may only move what this frame owns.  A parameter is a
            # borrow, and a handle is two words pointing at what someone else
            # owns -- moving out of either leaves every other copy holding a
            # hole nothing can mark dead.
            self.error(operand.span,
                       "cannot consume through a handle: a parameter is a "
                       "borrow, so only what this frame owns can be moved")
            return state
        dead = _dead_prefix(state, place)
        if dead is not None:
            self.error(self.root_span(operand),
                       "%s was consumed: the move ended that name, and drop "
                       "runs exactly once" % _show(dead))
            return state
        if bind is None:
            return state
        return state | {place}

    def v_match(self, node, state):
        """Arms are ALTERNATIVE paths: exactly one runs.  The join is union --
        dead on any incoming path is dead after -- and no condition is ever
        evaluated to decide an edge cannot be taken."""
        state = self.visit(node.scrutinee, state)
        if not node.arms:
            return state
        out = state
        for arm in node.arms:
            saved = dict(self.binds)
            saved_ctx = self.ctx
            self.ctx = self.ctx.with_scope(self.ctx.scope.child())
            try:
                self.bind_pattern(arm.pattern)
                out = out | self.visit(arm.body, state)
            finally:
                self.binds = saved
                self.ctx = saved_ctx
        return out

    def bind_pattern(self, pattern):
        """An arm's payload binder is a FRESH name: `Ok(f)` shadows an outer
        `f`, consumed or not, and reporting the outer one's death inside the
        arm would be a false positive.

        `cst.py` hands back a nested pattern as a node but a NULLARY
        CONSTRUCTOR as a bare string -- `Left(Blank)` arrives with
        `binder="Blank"`, and `Blank` there is a case of the payload type, not
        a name being bound.  Binding it would shadow a real binding of the
        same name and silently drop the case, so the constructor index is
        consulted first.
        """
        import bootstrap.sema as S

        binder = getattr(pattern, "binder", None)
        if not isinstance(binder, str) or binder == "_":
            return
        if binder in self.constructors():
            return
        self.ctx.scope.put(binder, S.Sym("value", S.ANY, mutable=False))
        self.binds[binder] = _Bind(binder, pattern.span, True, False, False,
                                   self.lambda_depth)

    def constructors(self):
        """Every enum case and every type name in the program, tree-wide.

        Tree-wide and not scope-aware on purpose: the question is only "could
        this string be a constructor rather than a binder", and answering it
        too widely costs a shadowed binder its freshness -- which is what the
        outer binding already gives it.
        """
        if self._ctors is not None:
            return self._ctors
        names = set()
        for td in list(getattr(self.sema, "types", {}).values()):
            names.add(td.name)
            for v in getattr(td, "variants", ()) or ():
                vname = getattr(v, "name", None)
                if isinstance(vname, str):
                    names.add(vname)
        self._ctors = names
        return names

    def v_call(self, node, state):
        callee = node.callee
        args = [a.value if isinstance(a, A.Arg) else a for a in node.args]

        if isinstance(callee, A.Member):
            state = self.visit(callee.base, state)
            self.check_receiver(callee)
        else:
            state = self.visit(callee, state)
            self.check_scope_stored(callee, node.args)

        # An ESCAPING closure is the one that takes an Alloc: it may outlive
        # the block it was written in, so what it captures outlives it too.
        escapes = any(self.is_alloc(self.type_of(a)) for a in args)
        for arg in args:
            if isinstance(arg, A.Lambda) and escapes:
                state = self.lambda_edge(arg, state, escaping=True)
            else:
                state = self.visit(arg, state)
        return state

    def check_scope_stored(self, callee, args):
        """Storing `@scope` in a struct is the first of the three ways out."""
        if not isinstance(callee, A.Path) or not self.is_struct_name(callee.name):
            return
        for a in args:
            value = a.value if isinstance(a, A.Arg) else a
            if isinstance(value, A.ScopeRef):
                self.error(value.span, _SCOPE_ESCAPES)
            elif isinstance(value, A.Path):
                bind = self.binds.get(value.name)
                if bind is not None and bind.is_scope:
                    self.error(value.span, _SCOPE_ESCAPES)

    def check_receiver(self, callee):
        """`::` on a receiver is the ordinary binding marker doing its
        ordinary job on the ordinary first parameter.

        Shallow, and that is the point: a handle's methods are `:` even when
        they change the world, so `self.alloc.realloc(..)` through an
        immutable `alloc` field is legal and every collection keeps an
        immutable allocator.
        """
        methods = self.methods_of(self.type_of(callee.base), callee.name)
        if not methods:
            return
        for fn in methods:
            if not fn.params:
                return
            first = fn.params[0]
            if first.name != "self" or not first.mutable:
                return  # an overload that does not write the receiver's bytes
        if not self.place_mutable(callee.base):
            self.error(self.root_span(callee.base), _MUT_RECEIVER % callee.name)

    def v_lambda(self, node, state):
        return self.lambda_edge(node, state, escaping=False)

    def lambda_edge(self, node, state, escaping):
        """A closure body is an EDGE, never opaque and never straight-line.

        It may run zero times, and it may run again: `DESIGN.md` puts nothing
        in a signature that says which, so the checker assumes both.  Zero
        times is why the join with the state before it is a union; again is
        why the body is iterated to a fixpoint, which is what makes the second
        iteration of a loop see the binding the first one moved.
        """
        entry = state
        self.quiet += 1
        try:
            for _ in range(_FIXPOINT_ROUNDS):
                out = self.lambda_body(node, entry, escaping)
                nxt = entry | out
                if nxt == entry:
                    break
                entry = nxt
        finally:
            self.quiet -= 1
        out = self.lambda_body(node, entry, escaping)
        return state | entry | out

    def lambda_body(self, node, state, escaping):
        import bootstrap.sema as S

        saved_binds = dict(self.binds)
        saved_ctx = self.ctx
        self.ctx = self.ctx.with_scope(self.ctx.scope.child())
        self.lambda_depth += 1
        if escaping:
            self.escaping.append(frozenset(self.binds))
        try:
            for p in node.params:
                # A closure parameter's type comes from the signature it is
                # passed to, and so does its `::` -- neither is written here,
                # so neither is assumed.
                self.ctx.scope.put(p.name, S.Sym("value", S.ANY, mutable=True))
                self.binds[p.name] = _Bind(p.name, p.span, True, True, False,
                                           self.lambda_depth)
            return self.visit(node.body, state)
        finally:
            if escaping:
                self.escaping.pop()
            self.lambda_depth -= 1
            self.binds = saved_binds
            self.ctx = saved_ctx

    def v_scope_ref(self, node, state):
        return state

    def v_function(self, node, state):
        return state  # a nested declaration, checked where it is declared

    def v_record(self, node, state):
        for e in node.entries:
            if isinstance(e, A.Arg):
                state = self.visit(e.value, state)
        return state


_MUT_RECEIVER = ("%s needs a mutable receiver: it is declared `self :: @Self`, "
                 "so it writes the receiver's own bytes and the binding must "
                 "be `::`")

_SCOPE_ESCAPES = ("@scope may not escape: it names the enclosing block, which "
                  "is gone by the time anything outside could use it. It may "
                  "be passed inward, never out")


_HANDLERS = {
    "Block": _Checker.v_block,
    "Let": _Checker.v_let,
    "ExprStmt": _Checker.v_expr_stmt,
    "Path": _Checker.v_path,
    "Member": _Checker.v_member,
    "Index": _Checker.v_index,
    "Binary": _Checker.v_binary,
    "Consume": _Checker.v_consume,
    "Match": _Checker.v_match,
    "Call": _Checker.v_call,
    "Lambda": _Checker.v_lambda,
    "ScopeRef": _Checker.v_scope_ref,
    "Function": _Checker.v_function,
    "Record": _Checker.v_record,
}


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------


def check(graph, sema=None, root=""):
    """Every ownership diagnostic in the program, sorted, deduplicated.

    Returns an empty tuple when sema did not run: with no types there is no
    receiver rule and no `Drop`, and guessing would be worse than silence.
    """
    if sema is None:
        return ()
    return _Checker(graph, sema, root).run()
