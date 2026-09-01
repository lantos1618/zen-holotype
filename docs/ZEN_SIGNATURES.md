# Zen source signature inventory

Generated from every `src/**/*.zen` file by
`python3 scripts/zen_signature_inventory.py`. The extractor uses the
repository's tree-sitter grammar, preserves multiline source spelling,
and omits implementation bodies. An omitted function return is rendered
as `()` so the body-free declaration remains an explicit signature.

This is an inventory, not an architectural recommendation. Imports and
constants are included so aliases and public surfaces are not mistaken for
free functions during a later ownership review.
The corresponding decisions are in
[`SOURCE_OWNERSHIP_AUDIT.md`](SOURCE_OWNERSHIP_AUDIT.md).

## Coverage

| Item | Count |
| --- | ---: |
| Zen files | 227 |
| Top-level declarations | 7202 |
| Types | 358 |
| Enums | 94 |
| Aliases | 0 |
| Implementations | 76 |
| Functions | 4029 |
| Constants | 175 |
| Imports and re-exports | 2470 |

## Files

### `src/fmt/fmt.zen`

27 declarations (types: 1, functions: 12, imports and re-exports: 14).

#### Types

```zen
Render* = {
    text*: String,
    diags*: Vec<Diag>,
    faithful*: bool,
}
```

#### Functions

```zen
render* = (a: Alloc, lexed: Lexed) Res<Render, AllocError>

rejected = (a: Alloc, diags: Vec<Diag>) Res<Render, AllocError>

printed = (a: Alloc, src: Src, tree: Ast, m: Module, lexed: Lexed)
          Res<Render, AllocError>

write_module* = (
    out  :: Out,
    a    : Alloc,
    al   : Aligned,
    src  : Src,
    tree : Ast,
    m    : Module
) Res<(), AllocError>

write_trivia = (out :: Out, tree: Ast, run: TriviaRun) Res<(), AllocError>

write_decl = (
    out  :: Out,
    a    : Alloc,
    al   : Aligned,
    src  : Src,
    tree : Ast,
    m    : Module,
    i    : usize,
    d    : Decl
) Res<(), AllocError>

next_start = (tree: Ast, m: Module, i: usize) Pos

run_start = (tree: Ast, run: TriviaRun) Res<Pos>

unchanged_tokens = (a: Alloc, before: Lexed, text: str) Res<bool, AllocError>

same_stream = (before: Lexed, after: Lexed) bool

every_token_same = (before: Lexed, after: Lexed) bool

token_same = (before: Lexed, after: Lexed, i: usize) bool
```

#### Imports and re-exports

```zen
Alloc, AllocError = std.mem

str, String = std.text

Vec = std.collections

Range = std.core

Pos, TriviaRun = std.ast.ast_span

Ast = std.ast.ast_arena

Module, Decl = std.ast.ast_node

scan, Source, Lexed, text_of = std.lex.lex

Diag, Parser, module = std.parse.parse

Src* = fmt.fmt_src

Out* = fmt.fmt_out

Aligned* = fmt.fmt_decl

align_columns = fmt.fmt_decl

break_lines = fmt.fmt_break
```

### `src/fmt/fmt_break.zen`

54 declarations (types: 3, functions: 39, constants: 1, imports and re-exports: 11).

#### Types

```zen
Item = {
    lo: usize,
    hi: usize,
}

Cand = {
    lo: usize,
    hi: usize,
    line: usize,
    end_line: usize,
    sep: u8,
    parens: bool,
    vetoes: bool,
    params: bool,
    fill: bool,
    items: Vec<Item>,
}

Edit = {
    from: usize,
    to: usize,
    text: String,
}
```

#### Functions

```zen
break_lines* = (a: Alloc, file: str, text: str) Res<String, AllocError>

rounds = (a: Alloc, file: str, text: str, join: bool)
         Res<String, AllocError>

one_round = (a: Alloc, file: str, text: str, join: bool)
            Res<String, AllocError>

round_clean = (a: Alloc, text: str, lexed: Lexed, join: bool)
              Res<String, AllocError>

copy_of* = (a: Alloc, text: str) Res<String, AllocError>

collect = (a: Alloc, src: Src, tree: Ast, m: Module)
          Res<Vec<Cand>, AllocError>

no_list = () Res<(), AllocError>

add_call = (a: Alloc, src: Src, cands :: Vec<Cand>, c: Call)
           Res<(), AllocError>

add_array = (
    a     : Alloc,
    src   : Src,
    tree  : Ast,
    cands :: Vec<Cand>,
    e     : Expr,
    al    : ArrayLit
) Res<(), AllocError>

add_decl = (a: Alloc, src: Src, cands :: Vec<Cand>, d: Decl)
           Res<(), AllocError>

add_params = (
    a     : Alloc,
    src   : Src,
    cands :: Vec<Cand>,
    ps    : Vec<Param>,
    span  : Span
) Res<(), AllocError>

add_union = (
    a     : Alloc,
    src   : Src,
    tree  : Ast,
    cands :: Vec<Cand>,
    t     : Type,
    u     : Union
) Res<(), AllocError>

add_enum = (a: Alloc, src: Src, cands :: Vec<Cand>, e: Enum)
           Res<(), AllocError>

in_order = (cands :: Vec<Cand>) ()

before = (x: Cand, y: Cand) bool

judge = (
    a     : Alloc,
    src   : Src,
    cands : Vec<Cand>,
    edits :: Vec<Edit>,
    join  : bool
) Res<(), AllocError>

break_and_mark = (
    a     : Alloc,
    src   : Src,
    c     : Cand,
    edits :: Vec<Edit>,
    moved :: Vec<bool>,
    i     : usize
) Res<(), AllocError>

relaid = (
    src   : Src,
    cands : Vec<Cand>,
    moved : Vec<bool>,
    c     : Cand,
    join  : bool
) bool

inside_moved = (cands: Vec<Cand>, moved: Vec<bool>, c: Cand) bool

wraps_one_list = (cands: Vec<Cand>, c: Cand) bool

ends_the_item = (cands: Vec<Cand>, c: Cand, only: Item) bool

may_join = (src: Src, c: Cand) bool

uncommented = (src: Src, from: usize, to: usize) bool

opens_comment = (src: Src, at: usize, to: usize) bool

too_wide = (src: Src, c: Cand) bool

shares_line = (src: Src, cands: Vec<Cand>, c: Cand) bool

packed_width = (src: Src, c: Cand) usize

collapsed = (src: Src, from: usize, to: usize) usize

may_relay = (src: Src, c: Cand) bool

one_line = (src: Src, from: usize, to: usize) bool

clean_gap = (src: Src, from: usize, to: usize, sep: u8) bool

emit_join = (a: Alloc, c: Cand, edits :: Vec<Edit>) Res<(), AllocError>

emit_break = (a: Alloc, src: Src, c: Cand, edits :: Vec<Edit>)
             Res<bool, AllocError>

stacked_gaps = (a: Alloc, c: Cand, edits :: Vec<Edit>, nl: str)
               Res<(), AllocError>

filled_gaps = (
    a      : Alloc,
    c      : Cand,
    edits  :: Vec<Edit>,
    nl     : str,
    indent : usize
) Res<(), AllocError>

item_width = (c: Cand, i: usize) usize

rewrites = (src: Src, edits: Vec<Edit>, was: usize) bool

in_byte_order = (edits :: Vec<Edit>) ()

apply = (a: Alloc, text: str, edits: Vec<Edit>) Res<String, AllocError>
```

#### Constants

```zen
WIDTH*: usize = 80
```

#### Imports and re-exports

```zen
Alloc, AllocError = std.mem

str, String = std.text

Vec = std.collections

Range = std.core

Span = std.ast.ast_span

Ast = std.ast.ast_arena

ExprId, TypeId, BlockId = std.ast.ast_id

Module, Decl, Type, Expr, Call, ArrayLit, Union, Enum, Param = std.ast.ast_node

scan, Source, Lexed = std.lex.lex

Parser, module = std.parse.parse

Src = fmt.fmt_src
```

### `src/fmt/fmt_decl.zen`

46 declarations (types: 3, functions: 30, imports and re-exports: 13).

#### Types

```zen
Pad = {
    from: usize,
    to: usize,
    width: usize,
}

Aligned* = {
    pads :: Vec<Pad>,
    record = (self :: @Self, line: usize, p: Pad) Res<(), AllocError>
    pad_at = (self: @Self, line: usize) Pad
    padded* = (self: @Self, a: Alloc, src: Src, from: usize, to: usize,
               line: usize) Res<String, AllocError>
    line_stop = (self: @Self, src: Src, ln: usize, at: usize, to: usize) usize
}

Op = {
    end: Pos,
    at: usize,
    width: usize,
}
```

#### Functions

```zen
no_pad = () Pad

Aligned* = (a: Alloc, src: Src, tree: Ast, m: Module)
           Res<Aligned, AllocError>

align_expr = (al :: Aligned, src: Src, tree: Ast, e: Expr) Res<(), AllocError>

align_type = (al :: Aligned, src: Src, t: Type) Res<(), AllocError>

align_decl = (al :: Aligned, src: Src, d: Decl) Res<(), AllocError>

align_block_decls = (al :: Aligned, src: Src, b: Block) Res<(), AllocError>

unaligned = () Res<(), AllocError>

align_arms = (al :: Aligned, src: Src, tree: Ast, mt: Match)
             Res<(), AllocError>

pad_arm = (
    al   :: Aligned,
    src  : Src,
    tree : Ast,
    mt   : Match,
    i    : usize,
    col  : usize
) Res<(), AllocError>

pad_one = (
    al   :: Aligned,
    src  : Src,
    tree : Ast,
    mt   : Match,
    i    : usize,
    arm  : Arm,
    col  : usize
) Res<(), AllocError>

arrow_col = (src: Src, tree: Ast, mt: Match, i: usize) usize

movable = (src: Src, tree: Ast, mt: Match, i: usize, arm: Arm) bool

alone = (mt: Match, i: usize, arm: Arm) bool

no_op = () Op

align_binds = (al :: Aligned, src: Src, tree: Ast, b: Block)
              Res<(), AllocError>

joins = (src: Src, tree: Ast, b: Block, i: usize) bool

stmt_line = (b: Block, i: usize, first: bool) usize

align_run = (
    al   :: Aligned,
    src  : Src,
    tree : Ast,
    b    : Block,
    from : usize,
    to   : usize
) Res<(), AllocError>

pad_bind = (
    al   :: Aligned,
    src  : Src,
    tree : Ast,
    b    : Block,
    i    : usize,
    col  : usize
) Res<(), AllocError>

op_at = (src: Src, tree: Ast, b: Block, i: usize) Op

bind_op = (src: Src, tree: Ast, s: Stmt, bd: Bind) Op

name_end = (tree: Ast, bd: Bind) Pos

op_width = (src: Src, at: usize, to: usize) usize

align_params = (al :: Aligned, src: Src, ps: Vec<Param>)
               Res<(), AllocError>

pad_param = (al :: Aligned, src: Src, ps: Vec<Param>, i: usize, col: usize)
            Res<(), AllocError>

param_op = (src: Src, ps: Vec<Param>, i: usize) Op

name_op = (src: Src, p: Param) Op

align_columns* = (a: Alloc, file: str, text: str) Res<String, AllocError>

columns_clean = (a: Alloc, text: str, lexed: Lexed) Res<String, AllocError>

colon_width = (src: Src, at: usize, to: usize) usize
```

#### Imports and re-exports

```zen
Alloc, AllocError = std.mem

str, String = std.text

Vec = std.collections

Range = std.core

Pos = std.ast.ast_span

ExprId, TypeId, BlockId = std.ast.ast_id

Ast = std.ast.ast_arena

Expr, Match, Arm, Block, Stmt, Bind = std.ast.ast_node

Module, Decl, Type, Param = std.ast.ast_node

scan, Source, Lexed = std.lex.lex

Parser, module = std.parse.parse

Src = fmt.fmt_src

copy_of = fmt.fmt_break
```

### `src/fmt/fmt_out.zen`

6 declarations (types: 1, functions: 1, constants: 1, imports and re-exports: 3).

#### Types

```zen
Out* = {
    text* :: String,
    started :: bool = false,
    owed :: bool = false,
    say* = (self :: @Self, s: str) Res<(), AllocError>
    say_at* = (self :: @Self, col: usize, s: str) Res<(), AllocError>
    blank* = (self :: @Self) Res<(), AllocError>
    open = (self :: @Self) Res<(), AllocError>
    view* = (self: @Self) str
}
```

#### Functions

```zen
Out* = (a: Alloc) Res<Out, AllocError>
```

#### Constants

```zen
FIRST*: usize = 1
```

#### Imports and re-exports

```zen
Alloc, AllocError = std.mem

str, String = std.text

Range = std.core
```

### `src/fmt/fmt_src.zen`

8 declarations (types: 1, functions: 2, imports and re-exports: 5).

#### Types

```zen
Src* = {
    text*: str,
    starts: Vec<usize>,
    offset* = (self: @Self, p: Pos) usize
    column_of = (self: @Self, p: Pos) usize
    lines* = (self: @Self) usize
    line_at* = (self: @Self, line: usize) usize
    after_line* = (self: @Self, line: usize) usize
    all_spaces* = (self: @Self, from: usize, to: usize) bool
    past_spaces* = (self: @Self, from: usize, to: usize) usize
    skip_space* = (self: @Self, from: usize, to: usize) usize
    all_space* = (self: @Self, from: usize, to: usize) bool
    bounded = (self: @Self, at: usize) usize
    slice_at* = (self: @Self, from: usize, to: usize) str
    trim_back* = (self: @Self, from: usize, to: usize) usize
}
```

#### Functions

```zen
col_index = (col: usize) usize

Src* = (a: Alloc, text: str) Res<Src, AllocError>
```

#### Imports and re-exports

```zen
Alloc, AllocError = std.mem

str = std.text

Vec = std.collections

Range = std.core

Pos = std.ast.ast_span
```

### `src/gen/gen.zen`

12 declarations (imports and re-exports: 12).

#### Imports and re-exports

```zen
Emit*, order*, INDENT*                   = gen.gen_emit

USR*, GEN*, RES_PATH*                    = gen.gen_name

comp*, count*, path*, path_with*, segments* = gen.gen_name

sym_type*, sym_fn*, sym_variant*         = gen.gen_name

sym_member*, sym_local*, sym_value*, sym_gen* = gen.gen_name

qualify*, tcode*                              = gen.gen_name

GenFault*, GenDiag*, render_gen*         = gen.gen_diag

message*, detail*                        = gen.gen_diag

CBackend*, emit_program*, render_symbol_map*, Dest* = gen.gen_c

lower_program*, emit_header*             = gen.gen_c

emit_unit*, unit_used*                   = gen.gen_c

ctype*, C_STANDARD*, emit_types*         = gen.gen_c
```

### `src/gen/gen_c/gen_c.zen`

43 declarations (imports and re-exports: 43).

#### Imports and re-exports

```zen
CBackend* = gen.gen_c.gen_c_state

LocalSlot*, Closure* = gen.gen_c.gen_c_frame

unsupported*, unresolved*, untyped*, ambiguous* = gen.gen_c.gen_c_report

sub*, any_open*, inst_at* = gen.gen_c.gen_c_mono

recv_inst*, settled_inst*, inst_open* = gen.gen_c.gen_c_mono

enter_tparams*, leave_tparams*, enter_struct_tparams* = gen.gen_c.gen_c_mono

temp*, init_temp* = gen.gen_c.gen_c_flow

emit_program*, plain_ctx*, body_ctx* = gen.gen_c.gen_c_decl

is_res* = gen.gen_c.gen_c_type

render_symbol_map* = gen.gen_c.gen_c_decl

emit_main* = gen.gen_c.gen_c_main

lower_program*, emit_header*, emit_unit*, unit_used* = gen.gen_c.gen_c_decl

ctype*, declarator*, spellable*, is_unit* = gen.gen_c.gen_c_type

c_prim*, is_c_integer*, is_signed*, request_type* = gen.gen_c.gen_c_type

emit_types* = gen.gen_c.gen_c_layout

Dest*, block*, deliver*, stmt* = gen.gen_c.gen_c_stmt

expr*, ty_of*, spills*, spills_anywhere* = gen.gen_c.gen_c_expr

lower_meta_or_access*, lower_meta_count* = gen.gen_c.gen_c_expr

lower_access*, type_const* = gen.gen_c.gen_c_read

lower_meta_walk*, lower_meta_proj* = gen.gen_c.gen_c_meta

lower_unary*, lower_binary*, c_op* = gen.gen_c.gen_c_op

lower_call*, signature_of* = gen.gen_c.gen_c_call

complete_inst*, call_ret_type* = gen.gen_c.gen_c_infer

lower_match* = gen.gen_c.gen_c_flow

lower_try* = gen.gen_c.gen_c_try

lower_loop* = gen.gen_c.gen_c_loop

is_loop_shape*, loop_result_type*, Shape* = gen.gen_c.gen_c_shape

Fold*, lower_fold* = gen.gen_c.gen_c_fold

supplies_bounds*, range_impl*, range_element_type* = gen.gen_c.gen_c_range

handle_depth*, lower_handle_call* = gen.gen_c.gen_c_handle

inlines*, inline_call*, inline_method* = gen.gen_c.gen_c_inline

closure_slot*, lower_closure_call*, takes_lambda* = gen.gen_c.gen_c_inline

inline_result_type*, inline_ret* = gen.gen_c.gen_c_settle

is_ptr_member*, lower_ptr_member*, lower_null_ptr* = gen.gen_c.gen_c_ptr

is_format_door*, lower_format_door* = gen.gen_c.gen_c_fmt

CapabilityKind*, capability_kind*, lower_capability* = gen.gen_c.gen_c_cap

is_fat*, Slot*, slots_of*, fat_value* = gen.gen_c.gen_c_fat

needs_fat*, write_fat_value* = gen.gen_c.gen_c_fat

convert*, lower_fat_call* = gen.gen_c.gen_c_bound

lower_index*, index_type* = gen.gen_c.gen_c_index

array_of*, write_array_index*, lower_array_walk* = gen.gen_c.gen_c_array

lower_array_lit*, lower_fixed_array*, write_array_def* = gen.gen_c.gen_c_array

C_STANDARD*, comment* = gen.gen_c.gen_c_runtime
```

### `src/gen/gen_c/gen_c_actor.zen`

68 declarations (types: 1, functions: 44, imports and re-exports: 23).

#### Types

```zen
BehaviorHit* = {
    site*: Site,
    f*: Function,
    mi*: usize,
}
```

#### Functions

```zen
ref_of_actor* = (be :: CBackend, ty: TyId) Res<Res<TyId>, AllocError>

actor_ref = (be :: CBackend, n: TyNamed) Res<Res<TyId>, AllocError>

actor_named_type = (be :: CBackend, name: str) Res<Res<TyId>, AllocError>

named_type_at = (be :: CBackend, name: str, qname: str)
                Res<Res<TyId>, AllocError>

actor_path = (name: str) str

behavior_of* = (be :: CBackend, actor: TyId, name: str)
               Res<Res<BehaviorHit>, AllocError>

behavior_at = (
    be    :: CBackend,
    s     : Site,
    name  : str,
    found :: Vec<BehaviorHit>
) Res<(), AllocError>

decl_name_at = (be: CBackend, s: Site) str

behavior_in = (
    be    :: CBackend,
    s     : Site,
    name  : str,
    id    : ImplId,
    found :: Vec<BehaviorHit>
) Res<(), AllocError>

behavior_members = (
    be    :: CBackend,
    s     : Site,
    name  : str,
    ms    : Vec<Member>,
    found :: Vec<BehaviorHit>
) Res<(), AllocError>

emit_actor_floor* = (be :: CBackend, out :: Emit) Res<(), AllocError>

write_actor_floor = (be :: CBackend, out :: Emit) Res<(), AllocError>

write_actor_worker = (be :: CBackend, out :: Emit) Res<(), AllocError>

write_actor_send_floor = (be :: CBackend, out :: Emit) Res<(), AllocError>

write_actor_start_floor = (be :: CBackend, out :: Emit) Res<(), AllocError>

write_actor_stop_floor = (be :: CBackend, out :: Emit) Res<(), AllocError>

emit_actor_defs* = (be :: CBackend, out :: Emit) Res<(), AllocError>

actor_defs_loop = (be :: CBackend, out :: Emit) Res<(), AllocError>

emit_actor_globals* = (be :: CBackend, out :: Emit) Res<(), AllocError>

write_actor_shutdown* = (be :: CBackend, out :: Emit) Res<(), AllocError>

lower_actor_stop* = (
    be  :: CBackend,
    a   : Access,
    rty : TyId,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

lower_actor_send* = (
    be       :: CBackend,
    id       : ExprId,
    c        : Call,
    a        : Access,
    rty      : TyId,
    actor_ty : TyId,
    ctx      : Ctx,
    out      :: String
) Res<(), AllocError>

write_actor_send = (
    be       :: CBackend,
    id       : ExprId,
    c        : Call,
    a        : Access,
    rty      : TyId,
    actor_ty : TyId,
    hit      : BehaviorHit,
    ctx      : Ctx,
    out      :: String
) Res<(), AllocError>

write_message_record = (be :: CBackend, n: usize, sig: Vec<TyId>)
                       Res<String, AllocError>

write_behavior_turn = (
    be       :: CBackend,
    n        : usize,
    payload  : str,
    actor_ty : TyId,
    hit      : BehaviorHit,
    sig      : Vec<TyId>
) Res<String, AllocError>

write_send_value = (
    be      :: CBackend,
    c       : Call,
    a       : Access,
    rty     : TyId,
    ret     : TyId,
    payload : str,
    turn    : str,
    f       : Function,
    sig     : Vec<TyId>,
    ctx     : Ctx,
    out     :: String
) Res<(), AllocError>

direct_str_count = (be: CBackend, sig: Vec<TyId>) usize

is_direct_str = (be: CBackend, ty: TyId) bool

write_slice_descriptor = (
    be      :: CBackend,
    slices  : str,
    at      : usize,
    message : str,
    arg     : usize
) Res<(), AllocError>

lower_actor_spawn* = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    a   : Access,
    rty : TyId,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

spawn_ref = (
    be     :: CBackend,
    id     : ExprId,
    c      : Call,
    a      : Access,
    rty    : TyId,
    ret    : TyId,
    ref_ty : TyId,
    ctx    : Ctx,
    out    :: String
) Res<(), AllocError>

spawn_types = (
    be       :: CBackend,
    id       : ExprId,
    c        : Call,
    a        : Access,
    rty      : TyId,
    ret      : TyId,
    ref_ty   : TyId,
    actor_ty : TyId,
    ctx      : Ctx,
    out      :: String
) Res<(), AllocError>

spawn_known = (
    be         :: CBackend,
    id         : ExprId,
    c          : Call,
    a          : Access,
    rty        : TyId,
    ret        : TyId,
    ref_ty     : TyId,
    actor_ty   : TyId,
    context_ty : TyId,
    arena_ty   : TyId,
    ctx        : Ctx,
    out        :: String
) Res<(), AllocError>

write_actor_spawn = (
    be         :: CBackend,
    c          : Call,
    a          : Access,
    rty        : TyId,
    ret        : TyId,
    ref_ty     : TyId,
    actor_ty   : TyId,
    context_ty : TyId,
    arena_ty   : TyId,
    state_ty   : TyId,
    alloc_ty   : TyId,
    ctx        : Ctx,
    out        :: String
) Res<(), AllocError>

write_actor_record = (
    be      :: CBackend,
    name    : str,
    actor   : TyId,
    context : TyId,
    arena   : TyId
) Res<(), AllocError>

write_started_callback = (be :: CBackend, n: usize, rec: str, actor: TyId)
                         Res<String, AllocError>

add_lifecycle_callback = (
    be      :: CBackend,
    name    : String,
    rec     : str,
    actor   : TyId,
    hit     : BehaviorHit,
    context : bool
)
                         Res<(), AllocError>

behavior_symbol = (be :: CBackend, actor: TyId, hit: BehaviorHit)
                  Res<String, AllocError>

write_stopped_callback = (
    be    :: CBackend,
    n     : usize,
    rec   : str,
    actor : TyId,
    arena : TyId
)
                         Res<String, AllocError>

drop_symbol = (be :: CBackend, ty: TyId) Res<Res<String>, AllocError>

write_spawn_value = (
    be         :: CBackend,
    c          : Call,
    a          : Access,
    rty        : TyId,
    ret        : TyId,
    ref_ty     : TyId,
    actor_ty   : TyId,
    context_ty : TyId,
    arena_ty   : TyId,
    state_ty   : TyId,
    alloc_ty   : TyId,
    rec        : str,
    started    : str,
    stopped    : str,
    ctx        : Ctx,
    out        :: String
) Res<(), AllocError>

write_failed_spawn_drop = (
    be    :: CBackend,
    cell  : str,
    actor : TyId,
    arena : TyId
) Res<(), AllocError>

init_actor_fields = (
    be          :: CBackend,
    cell        : str,
    arena_state : str,
    env         : str,
    actor       : str,
    actor_ty    : TyId,
    context_ty  : TyId,
    arena_ty    : TyId,
    state_ty    : TyId,
    alloc_ty    : TyId,
    started     : str,
    stopped     : str
) Res<(), AllocError>

write_ref_value = (
    be     :: CBackend,
    ref_ty : TyId,
    cell   : str,
    out    :: String
) Res<(), AllocError>
```

#### Imports and re-exports

```zen
AllocError = std.mem

Vec = std.collections

Range = std.core

str, String = std.text

ExprId, Access, Call, Function, Member = std.ast

Def = sema.sema_def

ImplId = sema.sema_id

TyId, TyNamed = sema.sema_ty

Ctx = sema.sema_check

Inst = sema.sema_inst

Emit = gen.gen_emit

sym_gen, sym_member = gen.gen_name

CBackend = gen.gen_c.gen_c_state

Site, site_of, method_sig, member_symbol = gen.gen_c.gen_c_member

has_body, decl_name, impl_member = gen.gen_c.gen_c_impl

impl_bound_type = sema.sema_supply

ctype, field_of, pointee = gen.gen_c.gen_c_type

expr = gen.gen_c.gen_c_expr

recv_inst = gen.gen_c.gen_c_mono

temp, payload_type, write_assign_ok, write_assign_err = gen.gen_c.gen_c_flow

write_assign_ok_unit = gen.gen_c.gen_c_flow

by_ref = gen.gen_c.gen_c_arg

fat_value = gen.gen_c.gen_c_fat
```

### `src/gen/gen_c/gen_c_alloc.zen`

43 declarations (types: 2, functions: 22, imports and re-exports: 19).

#### Types

```zen
RawFn* = {
    site*: Site,
    f*: Function,
}

Created* = {
    elem*: TyId,
    raw_ret*: TyId,
    ret*: TyId,
}
```

#### Functions

```zen
alloc_raw* = (be :: CBackend, rty: TyId, name: str)
             Res<Res<RawFn>, AllocError>

raw_of = (be :: CBackend, rty: TyId) Res<Res<RawFn>, AllocError>

raw_at_site = (be :: CBackend, s: Site) Res<Res<RawFn>, AllocError>

raw_from_impl = (be :: CBackend, s: Site) Res<Res<RawFn>, AllocError>

create_type* = (be :: CBackend, c: Call, a: Access, rty: TyId, ctx: Ctx)
               Res<Res<TyId>, AllocError>

created_type = (be :: CBackend, c: Call, rty: TyId, r: RawFn, ctx: Ctx)
               Res<Res<TyId>, AllocError>

created = (be :: CBackend, c: Call, rty: TyId, r: RawFn, ctx: Ctx)
          Res<Res<Created>, AllocError>

created_of = (be :: CBackend, t: TypeId, rty: TyId, r: RawFn, ctx: Ctx)
             Res<Res<Created>, AllocError>

created_at = (be :: CBackend, elem: TyId, rt: TyId)
             Res<Res<Created>, AllocError>

created_res = (be :: CBackend, elem: TyId, rt: TyId, x: TyRes)
              Res<Res<Created>, AllocError>

created_named = (be :: CBackend, elem: TyId, rt: TyId, x: TyRes, n: TyNamed)
                Res<Res<Created>, AllocError>

created_ptr = (be :: CBackend, elem: TyId, rt: TyId, x: TyRes, n: TyNamed)
              Res<Res<Created>, AllocError>

raw_result = (be :: CBackend, rty: TyId, r: RawFn) Res<TyId, AllocError>

lower_create* = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    a   : Access,
    rty : TyId,
    ctx : Ctx,
    out :: String
) Res<bool, AllocError>

write_create = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    a   : Access,
    rty : TyId,
    r   : RawFn,
    ctx : Ctx,
    out :: String
) Res<bool, AllocError>

nothing_to_make = (be :: CBackend, id: ExprId, out :: String)
                  Res<bool, AllocError>

write_made = (
    be  :: CBackend,
    a   : Access,
    rty : TyId,
    r   : RawFn,
    x   : Created,
    ctx : Ctx,
    out :: String
) Res<bool, AllocError>

rebuild_at_elem = (be :: CBackend, call: str, x: Created, out :: String)
                  Res<bool, AllocError>

raw_call = (
    be   :: CBackend,
    recv : ExprId,
    rty  : TyId,
    r    : RawFn,
    x    : Created,
    ctx  : Ctx,
    out  :: String
) Res<bool, AllocError>

write_raw_call = (
    be   :: CBackend,
    recv : ExprId,
    rty  : TyId,
    r    : RawFn,
    x    : Created,
    sig  : Vec<TyId>,
    inst : Inst,
    ctx  : Ctx,
    out  :: String
) Res<bool, AllocError>

write_raw_slot = (
    be   :: CBackend,
    recv : ExprId,
    rty  : TyId,
    r    : RawFn,
    x    : Created,
    sig  : Vec<TyId>,
    ctx  : Ctx,
    out  :: String
) Res<bool, AllocError>

write_static_raw = (
    be   :: CBackend,
    recv : ExprId,
    rty  : TyId,
    r    : RawFn,
    x    : Created,
    sig  : Vec<TyId>,
    inst : Inst,
    ctx  : Ctx,
    out  :: String
) Res<bool, AllocError>
```

#### Imports and re-exports

```zen
ExprId, Access, Call, Function, TypeId, Member = std.ast

AllocError = std.mem

Vec = std.collections

str, String = std.text

TyId, TyNamed, TyRes = sema.sema_ty

Ctx = sema.sema_check

Inst = sema.sema_inst

self_ctx = sema.sema_member

CBackend = gen.gen_c.gen_c_state

untyped = gen.gen_c.gen_c_report

sub, recv_inst, inst_open, any_open = gen.gen_c.gen_c_mono

request_type = gen.gen_c.gen_c_type

Site, site_of, method_sig, member_symbol, member_at = gen.gen_c.gen_c_member

by_arity, impl_member_of = gen.gen_c.gen_c_impl

write_arg = gen.gen_c.gen_c_arg

convert, write_sizeof, slot_call = gen.gen_c.gen_c_bound

init_temp = gen.gen_c.gen_c_flow

is_fat = gen.gen_c.gen_c_fat

ptr_at = gen.gen_c.gen_c_ptr
```

### `src/gen/gen_c/gen_c_arg.zen`

18 declarations (functions: 8, imports and re-exports: 10).

#### Functions

```zen
arg_text* = (
    be   :: CBackend,
    c    : Call,
    i    : usize,
    want : TyId,
    ctx  : Ctx,
    out  :: String
) Res<(), AllocError>

str_arg* = (be :: CBackend, c: Call, i: usize, ctx: Ctx, out :: String)
          Res<(), AllocError>

recv_arg* = (c: Call, recv: Res<ExprId>) Res<ExprId>

arg_value* = (c: Call, i: usize) Res<ExprId>

write_arg* = (
    be    :: CBackend,
    value : ExprId,
    i     : usize,
    f     : Function,
    sig   : Vec<TyId>,
    ctx   : Ctx,
    out   :: String
) Res<(), AllocError>

write_arg_at* = (
    be    :: CBackend,
    value : ExprId,
    i     : usize,
    hold  : bool,
    f     : Function,
    sig   : Vec<TyId>,
    ctx   : Ctx,
    out   :: String
) Res<(), AllocError>

by_ref* = (f: Function, i: usize) bool

write_address* = (
    be    :: CBackend,
    value : ExprId,
    ctx   : Ctx,
    want  : TyId,
    out   :: String
) Res<(), AllocError>
```

#### Imports and re-exports

```zen
ExprId, Call, Function = std.ast

AllocError = std.mem

Vec = std.collections

String = std.text

TyId = sema.sema_ty

Ctx = sema.sema_check

CBackend = gen.gen_c.gen_c_state

expr, value_held = gen.gen_c.gen_c_expr

declare_temp = gen.gen_c.gen_c_flow

address_of = gen.gen_c.gen_c_fat
```

### `src/gen/gen_c/gen_c_array.zen`

34 declarations (functions: 16, constants: 1, imports and re-exports: 17).

#### Functions

```zen
array_of* = (be :: CBackend, id: TyId) Res<TyArray>

write_array_def* = (be :: CBackend, out :: Emit, name: str, a: TyArray)
                   Res<(), AllocError>

storage_count = (a: TyArray) usize

lower_array_lit* = (
    be   :: CBackend,
    id   : ExprId,
    a    : ArrayLit,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

literal_ty = (be :: CBackend, id: ExprId, ctx: Ctx, want: TyId)
             Res<TyId, AllocError>

lower_fixed_array* = (
    be   :: CBackend,
    id   : ExprId,
    f    : FixedArray,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

write_elems = (
    be    :: CBackend,
    id    : ExprId,
    elems : Vec<ExprId>,
    ty    : TyId,
    ctx   : Ctx,
    out   :: String
) Res<(), AllocError>

write_compound = (
    be    :: CBackend,
    elems : Vec<ExprId>,
    ty    : TyId,
    a     : TyArray,
    ctx   : Ctx,
    out   :: String
) Res<(), AllocError>

elem_held = (
    be    : CBackend,
    multi : bool,
    last  : usize,
    i     : usize,
    e     : ExprId
) bool

last_caller = (be: CBackend, elems: Vec<ExprId>) usize

write_elem_list = (
    be    :: CBackend,
    elems : Vec<ExprId>,
    a     : TyArray,
    ctx   : Ctx,
    out   :: String
) Res<(), AllocError>

write_array_index* = (
    be      :: CBackend,
    ix      : Index,
    base_ty : TyId,
    a       : TyArray,
    ctx     : Ctx,
    out     :: String
) Res<(), AllocError>

write_checked = (
    be  :: CBackend,
    ix  : Index,
    a   : TyArray,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

helper_of = (be :: CBackend, ity: TyId) str

lower_array_walk* = (
    be   :: CBackend,
    sh   : Shape,
    one  : ExprId,
    rty  : TyId,
    a    : TyArray,
    lam  : Lambda,
    ctx  : Ctx,
    want : TyId,
    fold : Fold,
    out  :: String
) Res<(), AllocError>

write_pass_value = (be :: CBackend, rng: str, counter: str, out :: String)
                   Res<(), AllocError>
```

#### Constants

```zen
ELEMS* : str = "zg_elems"
```

#### Imports and re-exports

```zen
ExprId, ArrayLit, FixedArray, Index, Lambda = std.ast

AllocError = std.mem

Vec = std.collections

str, String = std.text

TyId, TyArray = sema.sema_ty

Ctx = sema.sema_check

Emit = gen.gen_emit

GEN = gen.gen_name

CBackend = gen.gen_c.gen_c_state

unsupported = gen.gen_c.gen_c_report

Shape = gen.gen_c.gen_c_shape

Fold = gen.gen_c.gen_c_fold

ctype, declarator, request_type, is_signed = gen.gen_c.gen_c_type

expr, ty_of, value_held, has_call = gen.gen_c.gen_c_expr

write_position = gen.gen_c.gen_c_op

open_result, close_pass, run_body = gen.gen_c.gen_c_loop

declare_usize, settle_res, walk_temp = gen.gen_c.gen_c_loop
```

### `src/gen/gen_c/gen_c_assoc.zen`

44 declarations (functions: 20, imports and re-exports: 24).

#### Functions

```zen
lower_assoc_call* = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    a   : Access,
    ty  : TyId,
    ctx : Ctx,
    out :: String
)
                    Res<bool, AllocError>

lower_type_assoc = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    a   : Access,
    ty  : TyId,
    ctx : Ctx,
    out :: String
)
                   Res<bool, AllocError>

lower_module_call = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    a   : Access,
    mi  : usize,
    ctx : Ctx,
    out :: String
)
                    Res<bool, AllocError>

lower_module_def = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    d   : Def,
    ctx : Ctx,
    out :: String
) Res<bool, AllocError>

module_construct = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    d   : Def,
    ctx : Ctx,
    out :: String
) Res<bool, AllocError>

lower_module_fn = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    d   : Def,
    ctx : Ctx,
    out :: String
) Res<bool, AllocError>

module_fn_decl = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    d   : Def,
    f   : Function,
    ctx : Ctx,
    out :: String
) Res<bool, AllocError>

refuse_module_fn = (be :: CBackend, id: ExprId, out :: String)
                   Res<bool, AllocError>

write_module_call = (
    be   :: CBackend,
    c    : Call,
    d    : Def,
    f    : Function,
    sig  : Vec<TyId>,
    inst : Inst,
    ctx  : Ctx,
    out  :: String
)
                    Res<bool, AllocError>

assoc_at_site = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    a   : Access,
    ty  : TyId,
    s   : Site,
    ctx : Ctx,
    out :: String
) Res<bool, AllocError>

assoc_member = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    a   : Access,
    ty  : TyId,
    s   : Site,
    m   : Member,
    ctx : Ctx,
    out :: String
)
               Res<bool, AllocError>

keep_assoc = (
    be    :: CBackend,
    found : Vec<Member>,
    ty    : TyId,
    s     : Site,
    out   :: Vec<Member>
) Res<(), AllocError>

keep_if_assoc = (
    be  :: CBackend,
    m   : Member,
    ty  : TyId,
    s   : Site,
    out :: Vec<Member>
) Res<(), AllocError>

keep_receiverless = (
    be  :: CBackend,
    m   : Member,
    f   : Function,
    ty  : TyId,
    s   : Site,
    out :: Vec<Member>
) Res<(), AllocError>

takes_receiver = (be :: CBackend, f: Function, ty: TyId, s: Site)
                 Res<bool, AllocError>

first_is_self = (be :: CBackend, p: Param, ty: TyId, s: Site)
                Res<bool, AllocError>

write_assoc_call = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    a   : Access,
    ty  : TyId,
    s   : Site,
    f   : Function,
    ctx : Ctx,
    out :: String
)
                   Res<bool, AllocError>

refuse_open = (be :: CBackend, id: ExprId, out :: String)
              Res<bool, AllocError>

emit_assoc_call = (
    be   :: CBackend,
    c    : Call,
    a    : Access,
    ty   : TyId,
    s    : Site,
    f    : Function,
    sig  : Vec<TyId>,
    inst : Inst,
    ctx  : Ctx,
    out  :: String
) Res<bool, AllocError>

write_assoc_arg = (
    be   :: CBackend,
    arg  : Arg,
    i    : usize,
    hold : bool,
    f    : Function,
    sig  : Vec<TyId>,
    ctx  : Ctx,
    out  :: String
)
                   Res<(), AllocError>
```

#### Imports and re-exports

```zen
ExprId, Member = std.ast

Function, Param, Access, Call, Arg = std.ast

AllocError = std.mem

Vec = std.collections

String = std.text

TyId = sema.sema_ty

Ctx = sema.sema_check

Inst = sema.sema_inst

Def, decl_at = sema.sema_def

self_ctx = sema.sema_member

module_named_by = sema.sema_module

param_type = sema.sema_denote

sym_fn = gen.gen_name

CBackend = gen.gen_c.gen_c_state

unsupported = gen.gen_c.gen_c_report

any_open, recv_inst, inst_open = gen.gen_c.gen_c_mono

enter_struct_tparams, leave_tparams = gen.gen_c.gen_c_mono

signature_of, plain, write_extern = gen.gen_c.gen_c_call

write_arg_at = gen.gen_c.gen_c_arg

holds = gen.gen_c.gen_c_expr

construct = gen.gen_c.gen_c_build

Site, site_of, member_at, method_sig = gen.gen_c.gen_c_member

member_symbol = gen.gen_c.gen_c_member

by_arity, has_body = gen.gen_c.gen_c_impl
```

### `src/gen/gen_c/gen_c_bound.zen`

77 declarations (functions: 49, imports and re-exports: 28).

#### Functions

```zen
convert* = (be :: CBackend, code: str, src: TyId, dst: TyId, out :: String)
           Res<(), AllocError>

convert_kind = (
    be   :: CBackend,
    code : str,
    src  : TyId,
    dst  : TyId,
    out  :: String
) Res<(), AllocError>

convert_set = (
    be   :: CBackend,
    code : str,
    src  : TyId,
    dst  : TyId,
    out  :: String
) Res<(), AllocError>

tags_as_member = (be :: CBackend, src: TyId, dst: TyId) bool

convert_named = (
    be   :: CBackend,
    code : str,
    dst  : TyId,
    n    : TyNamed,
    out  :: String
) Res<(), AllocError>

write_cast* = (be :: CBackend, code: str, dst: TyId, out :: String)
             Res<(), AllocError>

convert_res = (
    be   :: CBackend,
    code : str,
    src  : TyId,
    dst  : TyId,
    d    : TyRes,
    out  :: String
) Res<(), AllocError>

rebuild_res = (
    be   :: CBackend,
    code : str,
    src  : TyId,
    s    : TyRes,
    dst  : TyId,
    d    : TyRes,
    out  :: String
) Res<(), AllocError>

fail_arm = (
    be  :: CBackend,
    tmp : str,
    s   : TyRes,
    d   : TyRes,
    dst : TyId,
    out :: String
) Res<(), AllocError>

res_arm = (
    be  :: CBackend,
    tmp : str,
    v   : str,
    sp  : TyId,
    dp  : TyId,
    dst : TyId,
    out :: String
) Res<(), AllocError>

bare_arm = (be :: CBackend, v: str, dst: TyId, out :: String)
           Res<(), AllocError>

payload_arm = (
    be  :: CBackend,
    tmp : str,
    v   : str,
    sp  : TyId,
    dp  : TyId,
    dst : TyId,
    out :: String
) Res<(), AllocError>

arm_head = (be :: CBackend, v: str, dst: TyId, out :: String)
           Res<(), AllocError>

lower_fat_call* = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    a   : Access,
    rty : TyId,
    s   : Site,
    f   : Function,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

lower_answered_call = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    a   : Access,
    rty : TyId,
    s   : Site,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

member_answered = (be :: CBackend, f: Function, rty: TyId, name: str) bool

bound_answered = (be :: CBackend, rty: TyId, name: str) bool

table_answered = (be :: CBackend, mi: usize, bound: str, name: str) bool

impls_answered = (be :: CBackend, ids: Vec<ImplId>, bound: str, name: str)
                 bool

one_impl = (be :: CBackend, id: ImplId, bound: str, name: str) bool

impl_supplies = (tree: Ast, im: Impl, bound: str, name: str) bool

bound_of = (tree: Ast, tid: TypeId) str

supplies_body = (members: Vec<Member>, name: str) bool

owner_name = (be :: CBackend, rty: TyId) str

slot_call* = (
    be   :: CBackend,
    recv : str,
    tty  : TyId,
    name : str,
    args : str,
    argc : usize,
    out  :: String
) Res<Res<Slot>, AllocError>

write_named_slot = (
    be   :: CBackend,
    recv : str,
    slot : Slot,
    args : str,
    out  :: String
) Res<Res<Slot>, AllocError>

pick_slot = (slots: Vec<Slot>, name: str, args: usize) Res<Slot>

settle_call = (
    be   :: CBackend,
    id   : ExprId,
    c    : Call,
    a    : Access,
    rty  : TyId,
    s    : Site,
    slot : Slot,
    ctx  : Ctx,
    out  :: String
)
              Res<(), AllocError>

read_slot = (
    be       :: CBackend,
    c        : Call,
    rty      : TyId,
    s        : Site,
    slot     : Slot,
    ctx      : Ctx,
    declared :: Vec<TyId>,
    targs    :: Inst
)
            Res<TyId, AllocError>

fat_ret_type* = (be :: CBackend, c: Call, a: Access, ctx: Ctx)
                Res<Res<TyId>, AllocError>

slot_ret_type = (be :: CBackend, c: Call, rty: TyId, slot: Slot, ctx: Ctx)
                Res<Res<TyId>, AllocError>

settled_ret_type = (
    be   :: CBackend,
    c    : Call,
    rty  : TyId,
    s    : Site,
    slot : Slot,
    ctx  : Ctx
) Res<Res<TyId>, AllocError>

declared_params = (
    be   :: CBackend,
    f    : Function,
    sctx : Ctx,
    out  :: Vec<TyId>
) Res<(), AllocError>

declared_param = (
    be   :: CBackend,
    p    : Param,
    i    : usize,
    sctx : Ctx,
    out  :: Vec<TyId>
) Res<(), AllocError>

add_declared = (be :: CBackend, p: Param, sctx: Ctx, out :: Vec<TyId>)
               Res<(), AllocError>

infer_targs = (
    be       :: CBackend,
    c        : Call,
    declared : Vec<TyId>,
    ctx      : Ctx,
    out      :: Inst
) Res<(), AllocError>

infer_one = (
    be       :: CBackend,
    arg      : Arg,
    i        : usize,
    declared : Vec<TyId>,
    ctx      : Ctx,
    out      :: Inst
) Res<(), AllocError>

infer_against = (be :: CBackend, arg: Arg, d: TyId, ctx: Ctx, out :: Inst)
                Res<(), AllocError>

targs_settled = (be: CBackend, slot: Slot, targs: Inst) bool

all_closed = (be: CBackend, targs: Inst) bool

emit_fat_call = (
    be       :: CBackend,
    c        : Call,
    a        : Access,
    rty      : TyId,
    slot     : Slot,
    declared : Vec<TyId>,
    ret      : TyId,
    targs    : Inst,
    ctx      : Ctx,
    out      :: String
) Res<(), AllocError>

fat_args = (
    be       :: CBackend,
    c        : Call,
    slot     : Slot,
    declared : Vec<TyId>,
    targs    : Inst,
    ctx      : Ctx,
    out      :: String
) Res<(), AllocError>

fat_arg = (
    be       :: CBackend,
    arg      : Arg,
    i        : usize,
    hold     : bool,
    slot     : Slot,
    declared : Vec<TyId>,
    targs    : Inst,
    ctx      : Ctx,
    out      :: String
)
          Res<(), AllocError>

fat_sizes = (be :: CBackend, targs: Inst, out :: String)
            Res<(), AllocError>

fat_size = (be :: CBackend, targs: Inst, i: usize, out :: String)
           Res<(), AllocError>

write_sizeof* = (be :: CBackend, t: TyId, out :: String)
               Res<(), AllocError>

fat_result = (
    be    :: CBackend,
    slot  : Slot,
    ret   : TyId,
    targs : Inst,
    call  : str,
    out   :: String
) Res<(), AllocError>

fat_effect = (be :: CBackend, call: str, out :: String)
             Res<(), AllocError>

fat_value_back = (
    be   :: CBackend,
    slot : Slot,
    real : TyId,
    call : str,
    out  :: String
) Res<(), AllocError>
```

#### Imports and re-exports

```zen
ExprId = std.ast

Function, Param, Access, Call, Arg, Impl, Member, TypeId = std.ast

AllocError = std.mem

Vec = std.collections

str, String = std.text

Ast = std.ast

ImplId = sema.sema_id

Range = std.core

TyId, TyNamed, TyRes, is_failure = sema.sema_ty

Ctx = sema.sema_check

Inst, has_var = sema.sema_inst

self_ctx = sema.sema_member

param_type = sema.sema_denote

sym_member, sym_variant = gen.gen_name

qualify = gen.gen_name

RES_PATH = gen.gen_name

CBackend = gen.gen_c.gen_c_state

unsupported = gen.gen_c.gen_c_report

sub_with, enter_tparams, leave_tparams = gen.gen_c.gen_c_mono

unify, arg_type = gen.gen_c.gen_c_mono

enter_struct_tparams = gen.gen_c.gen_c_mono

ctype, is_unit, request_type, is_ptr_named, declared_ret = gen.gen_c.gen_c_type

expr, ty_of, value_held, holds = gen.gen_c.gen_c_expr

write_set_value = gen.gen_c.gen_c_widen

init_temp = gen.gen_c.gen_c_flow

Site, site_of = gen.gen_c.gen_c_member

Slot, slots_of = gen.gen_c.gen_c_fat

has_body = gen.gen_c.gen_c_impl
```

### `src/gen/gen_c/gen_c_build.zen`

38 declarations (types: 2, functions: 17, imports and re-exports: 19).

#### Types

```zen
Storage = {
    decl: Struct,
    inst: Inst,
    ctx: Ctx,
    field_name = (self: @Self, be :: CBackend, a: Arg, i: usize)
                 Res<str, AllocError>
    name_at = (self: @Self, be :: CBackend, i: usize)
              Res<str, AllocError>
    is_stored = (self: @Self, be :: CBackend, m: Member) bool
    has_named = (self: @Self, be :: CBackend, name: str) bool
    ty_of = (self: @Self, be :: CBackend, name: str) TyId
}

Initialisers = {
    call: Call,
    fields: Storage,
    ty: TyId,
    call_ctx: Ctx,
    write = (self: @Self, be :: CBackend, out :: String)
            Res<(), AllocError>
    defaults = (self: @Self, be :: CBackend, seen: usize, out :: String)
               Res<usize, AllocError>
    default_one = (self: @Self, be :: CBackend, m: Member, seen: usize,
                   out :: String) Res<usize, AllocError>
    member_default = (self: @Self, be :: CBackend, m: Member, name: str,
                      seen: usize, out :: String) Res<usize, AllocError>
    write_default = (self: @Self, be :: CBackend, v: ExprId, name: str,
                     seen: usize, out :: String) Res<usize, AllocError>
    default_value = (self: @Self, be :: CBackend, v: ExprId, name: str,
                     out :: String) Res<(), AllocError>
    supplies = (self: @Self, be :: CBackend, name: str) bool
    arg_supplies = (self: @Self, be :: CBackend, a: Arg, i: usize,
                    name: str) bool
    supplied = (self: @Self, be :: CBackend, a: Arg, i: usize, hold: bool,
                seen: usize, out :: String) Res<usize, AllocError>
    designated = (self: @Self, be :: CBackend, a: Arg, name: str,
                  hold: bool, seen: usize, out :: String)
                 Res<usize, AllocError>
    write_one = (self: @Self, be :: CBackend, a: Arg, name: str,
                 hold: bool, out :: String) Res<(), AllocError>
}
```

#### Functions

```zen
construct* = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    d   : Def,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

construct_type = (be :: CBackend, id: ExprId, d: Def, ctx: Ctx)
                 Res<TyId, AllocError>

construct_decl = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    x   : Decl,
    d   : Def,
    ty  : TyId,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

construct_struct = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    s   : Struct,
    d   : Def,
    ty  : TyId,
    ctx : Ctx,
    out :: String
)
                   Res<(), AllocError>

settle_construction = (
    be  :: CBackend,
    c   : Call,
    s   : Struct,
    d   : Def,
    ty  : TyId,
    ctx : Ctx
) Res<TyId, AllocError>

inferred_construction = (
    be  :: CBackend,
    c   : Call,
    s   : Struct,
    d   : Def,
    ty  : TyId,
    ctx : Ctx
) Res<TyId, AllocError>

unify_field = (
    be    :: CBackend,
    a     : Arg,
    i     : usize,
    s     : Struct,
    empty : Inst,
    dctx  : Ctx,
    ctx   : Ctx,
    out   :: Inst
) Res<(), AllocError>

rebuilt_type = (be :: CBackend, d: Def, s: Struct, found: Inst, ty: TyId)
               Res<TyId, AllocError>

keep_arg = (found: Inst, v: TyId, out :: Vec<TyId>) Res<(), AllocError>

prim_named = (be :: CBackend, s: Struct, ty: TyId) Res<TyId, AllocError>

designator = (be :: CBackend, ty: TyId, name: str, out :: String)
             Res<(), AllocError>

is_prim_ty = (be :: CBackend, ty: TyId) bool

layout_open = (be :: CBackend, s: Struct, d: Def, ty: TyId)
    Res<bool, AllocError>

write_literal = (
    be  :: CBackend,
    c   : Call,
    s   : Struct,
    d   : Def,
    ty  : TyId,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

write_initialisers = (
    be  :: CBackend,
    c   : Call,
    s   : Struct,
    d   : Def,
    ty  : TyId,
    ctx : Ctx,
    out :: String
)
                     Res<(), AllocError>

declared_value = (m: Member) Res<ExprId>

decl_ctx_of = (be :: CBackend, d: Def) Ctx
```

#### Imports and re-exports

```zen
ExprId, Decl, Struct, Member = std.ast

Call, Arg = std.ast

AllocError = std.mem

Vec = std.collections

str, String = std.text

TyId, is_prim = sema.sema_ty

Def, decl_at = sema.sema_def

Ctx = sema.sema_check

Inst, tparam_vars, has_var = sema.sema_inst

sym_member = gen.gen_name

CBackend = gen.gen_c.gen_c_state

unsupported = gen.gen_c.gen_c_report

constructed, recv_inst, intern_named = gen.gen_c.gen_c_mono

unify, arg_type, enter_tparams, leave_tparams = gen.gen_c.gen_c_mono

ctype, field_type, request_type, has_storage = gen.gen_c.gen_c_type

expr, ty_of = gen.gen_c.gen_c_expr

is_pure_value = gen.gen_c.gen_c_const

holds, value_held = gen.gen_c.gen_c_expr

Call = std.ast
```

### `src/gen/gen_c/gen_c_call.zen`

104 declarations (types: 2, functions: 60, imports and re-exports: 42).

#### Types

```zen
CallSite = {
    id: ExprId,
    c: Call,
    recv: Res<ExprId>,
    ctx: Ctx,
    resolve = (self: @Self, be :: CBackend, name: str, want: TyId,
               out :: String) Res<(), AllocError>
    add_travelled = (self: @Self, be :: CBackend, name: str,
                     found :: Vec<Def>) Res<(), AllocError>
    selected = (self: @Self, be :: CBackend, name: str, found: Vec<Def>,
                want: DeclId, dest: TyId, out :: String)
               Res<(), AllocError>
    only = (self: @Self, be :: CBackend, name: str, found: Vec<Def>,
            dest: TyId, out :: String) Res<(), AllocError>
    lower = (self: @Self, be :: CBackend, d: Def, want: TyId,
             out :: String) Res<(), AllocError>
    lower_resolved = (self: @Self, be :: CBackend, d: Def, want: TyId,
                      out :: String) Res<(), AllocError>
    lower_decl = (self: @Self, be :: CBackend, d: Def, x: Decl,
                  want: TyId, out :: String) Res<(), AllocError>
    lower_fn = (self: @Self, be :: CBackend, d: Def, f: Function,
                dest: TyId, out :: String) Res<(), AllocError>
    inline_or_call = (self: @Self, be :: CBackend, d: Def, f: Function,
                      out :: String) Res<(), AllocError>
    floor_or_call = (self: @Self, be :: CBackend, d: Def, f: Function,
                     out :: String) Res<(), AllocError>
    json_or_format = (self: @Self, be :: CBackend, d: Def, f: Function,
                      out :: String) Res<(), AllocError>
    format_or_call = (self: @Self, be :: CBackend, d: Def, f: Function,
                      out :: String) Res<(), AllocError>
    convert_or_call = (self: @Self, be :: CBackend, d: Def, f: Function,
                       out :: String) Res<(), AllocError>
    lower_narrow = (self: @Self, be :: CBackend, d: Def, out :: String)
                   Res<(), AllocError>
    plain_or_foreign = (self: @Self, be :: CBackend, d: Def, f: Function,
                        out :: String) Res<(), AllocError>
    foreign = (self: @Self, be :: CBackend, d: Def, f: Function,
               out :: String) Res<(), AllocError>
    foreign_at = (self: @Self, be :: CBackend, d: Def, f: Function,
                  sig: Vec<TyId>, out :: String) Res<(), AllocError>
    signature = (self: @Self, be :: CBackend, d: Def, f: Function,
                 out :: String) Res<(), AllocError>
    settled = (self: @Self, be :: CBackend, d: Def, f: Function,
               sig: Vec<TyId>, inst: Inst, out :: String)
              Res<(), AllocError>
    reachable = (self: @Self, be :: CBackend, d: Def, f: Function,
                 sig: Vec<TyId>, inst: Inst, out :: String)
                Res<(), AllocError>
    emit = (self: @Self, be :: CBackend, f: Function, sig: Vec<TyId>,
            sym: str, out :: String) Res<(), AllocError>
}

ForeignCall = {
    site: CallSite,
    def: Def,
    fn: Function,
    sig: Vec<TyId>,
    ret: TyId,
    write = (self: @Self, be :: CBackend, out :: String)
            Res<(), AllocError>
    raw = (self: @Self, be :: CBackend, out :: String)
          Res<(), AllocError>
    from_binding = (self: @Self, be :: CBackend, id: CBindingId,
                    out :: String) Res<(), AllocError>
    binding = (self: @Self, be :: CBackend, raw: CBinding, out :: String)
              Res<(), AllocError>
    headers = (self: @Self, be :: CBackend, raw: CBinding, out :: String)
              Res<(), AllocError>
}
```

#### Functions

```zen
res_value* = (
    be      :: CBackend,
    id      : ExprId,
    want    : TyId,
    variant : str,
    out     :: String
) Res<(), AllocError>

write_res_tagged = (be :: CBackend, want: TyId, variant: str, out :: String)
                   Res<(), AllocError>

write_res_payload* = (
    be      :: CBackend,
    id      : ExprId,
    want    : TyId,
    variant : str,
    value   : ExprId,
    payload : TyId,
    ctx     : Ctx,
    out     :: String
)
                     Res<(), AllocError>

run_for_effect = (be :: CBackend, value: ExprId, payload: TyId, ctx: Ctx)
                 Res<(), AllocError>

writes_nothing = (be: CBackend, value: ExprId) bool

write_payload_init = (
    be      :: CBackend,
    variant : str,
    value   : ExprId,
    payload : TyId,
    ctx     : Ctx,
    out     :: String
)
                     Res<(), AllocError>

lower_call* = (
    be   :: CBackend,
    id   : ExprId,
    c    : Call,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

lower_name_callee = (
    be   :: CBackend,
    id   : ExprId,
    c    : Call,
    name : str,
    ctx  : Ctx,
    want : TyId,
    out  :: String
)
                    Res<(), AllocError>

lower_indirect = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

write_indirect = (
    be     :: CBackend,
    c      : Call,
    params : Vec<TyId>,
    ctx    : Ctx,
    out    :: String
) Res<(), AllocError>

write_indirect_arg = (
    be     :: CBackend,
    a      : Arg,
    i      : usize,
    hold   : bool,
    params : Vec<TyId>,
    ctx    : Ctx,
    out    :: String
) Res<(), AllocError>

lower_named_call = (
    be   :: CBackend,
    id   : ExprId,
    c    : Call,
    name : str,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

lower_sugar_or_plain = (
    be   :: CBackend,
    id   : ExprId,
    c    : Call,
    name : str,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

is_sugar = (be :: CBackend, name: str, ctx: Ctx) Res<bool, AllocError>

undeclared = (be :: CBackend, name: str, ctx: Ctx) Res<bool, AllocError>

is_res_ctor* = (name: str) bool

lower_res_ctor = (
    be   :: CBackend,
    id   : ExprId,
    c    : Call,
    name : str,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

lower_res_arg = (
    be   :: CBackend,
    id   : ExprId,
    c    : Call,
    name : str,
    r    : TyRes,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

lower_plain_call* = (
    be   :: CBackend,
    id   : ExprId,
    c    : Call,
    name : str,
    recv : Res<ExprId>,
    ctx  : Ctx,
    want : TyId,
    out  :: String
)
                    Res<(), AllocError>

travelled_for = (
    be    :: CBackend,
    name  : str,
    r     : ExprId,
    ctx   : Ctx,
    found :: Vec<Def>
) Res<(), AllocError>

keep_travelled = (be :: CBackend, d: Def, rty: TyId, found :: Vec<Def>)
                 Res<(), AllocError>

add_receiving = (be :: CBackend, d: Def, rty: TyId, found :: Vec<Def>)
                Res<(), AllocError>

receives = (be :: CBackend, d: Def, rty: TyId) Res<bool, AllocError>

first_is = (be :: CBackend, sig: Vec<TyId>, rty: TyId)
           Res<bool, AllocError>

has_def = (found: Vec<Def>, id: DeclId) bool

def_with_id* = (found: Vec<Def>, want: DeclId) Res<Def>

checked_narrow = (d: Def, f: Function) bool

write_extern* = (
    be   :: CBackend,
    id   : ExprId,
    c    : Call,
    d    : Def,
    f    : Function,
    sig  : Vec<TyId>,
    recv : Res<ExprId>,
    ctx  : Ctx,
    out  :: String
) Res<(), AllocError>

bad_c_binding = (be :: CBackend, id: ExprId, why: str, out :: String)
                Res<(), AllocError>

foreign_ret = (be :: CBackend, d: Def, f: Function)
              Res<TyId, AllocError>

foreign_types_spellable = (be: CBackend, ret: TyId, sig: Vec<TyId>) bool

foreign_proto = (
    be   :: CBackend,
    name : str,
    f    : Function,
    ret  : TyId,
    sig  : Vec<TyId>,
    out  :: String
) Res<(), AllocError>

foreign_params = (be :: CBackend, f: Function, sig: Vec<TyId>, out :: String)
                 Res<(), AllocError>

convert_target = (d: Def, f: Function) Res<str>

convert_shape = (f: Function) bool

bodyless = (f: Function) bool

after_to = (name: str) str

keep_prim = (target: str) Res<str>

lower_convert = (
    be     :: CBackend,
    c      : Call,
    d      : Def,
    target : str,
    recv   : Res<ExprId>,
    ctx    : Ctx,
    out    :: String
)
                Res<(), AllocError>

write_convert = (
    be     :: CBackend,
    d      : Def,
    v      : ExprId,
    target : str,
    ctx    : Ctx,
    out    :: String
) Res<(), AllocError>

plain_fault = (be :: CBackend, d: Def) str

decl_fault = (x: Decl) str

signature_of* = (be :: CBackend, d: Def, inst: Inst, sig :: Vec<TyId>)
                Res<bool, AllocError>

params_into = (
    be   :: CBackend,
    d    : Def,
    f    : Function,
    inst : Inst,
    sig  :: Vec<TyId>
) Res<bool, AllocError>

plain* = (f: Function) bool

collect_params = (
    be     :: CBackend,
    d      : Def,
    params : Vec<Param>,
    inst   : Inst,
    sig    :: Vec<TyId>
) Res<bool, AllocError>

add_param = (
    be   :: CBackend,
    t    : TypeId,
    ctx  : Ctx,
    inst : Inst,
    sig  :: Vec<TyId>
) Res<(), AllocError>

write_call_args* = (
    be    :: CBackend,
    c     : Call,
    first : usize,
    f     : Function,
    sig   : Vec<TyId>,
    ctx   : Ctx,
    out   :: String
) Res<(), AllocError>

write_written_args = (
    be    :: CBackend,
    c     : Call,
    first : usize,
    f     : Function,
    sig   : Vec<TyId>,
    ctx   : Ctx,
    out   :: String
) Res<(), AllocError>

write_to_pack = (
    be    :: CBackend,
    c     : Call,
    first : usize,
    slot  : usize,
    f     : Function,
    sig   : Vec<TyId>,
    ctx   : Ctx,
    out   :: String
) Res<(), AllocError>

write_pack = (
    be    :: CBackend,
    c     : Call,
    first : usize,
    slot  : usize,
    pack  : TyId,
    ctx   : Ctx,
    out   :: String
) Res<(), AllocError>

is_forwarded_pack = (
    be    :: CBackend,
    c     : Call,
    first : usize,
    slot  : usize,
    pack  : TyId,
    ctx   : Ctx
) Res<bool, AllocError>

pack_typed_arg = (
    be    :: CBackend,
    c     : Call,
    first : usize,
    slot  : usize,
    pack  : TyId,
    ctx   : Ctx
) Res<bool, AllocError>

same_as_pack = (be :: CBackend, v: ExprId, pack: TyId, ctx: Ctx)
               Res<bool, AllocError>

write_forwarded = (
    be    :: CBackend,
    c     : Call,
    first : usize,
    slot  : usize,
    pack  : TyId,
    ctx   : Ctx,
    out   :: String
) Res<(), AllocError>

write_spread = (
    be    :: CBackend,
    c     : Call,
    first : usize,
    slot  : usize,
    pack  : TyId,
    ctx   : Ctx,
    out   :: String
) Res<(), AllocError>

write_run = (
    be    :: CBackend,
    c     : Call,
    first : usize,
    slot  : usize,
    pack  : TyId,
    ctx   : Ctx,
    out   :: String
) Res<(), AllocError>

write_pack_elems = (
    be    :: CBackend,
    c     : Call,
    first : usize,
    slot  : usize,
    elem  : TyId,
    ctx   : Ctx,
    out   :: String
) Res<(), AllocError>

write_receiver = (
    be   :: CBackend,
    recv : Res<ExprId>,
    c    : Call,
    f    : Function,
    sig  : Vec<TyId>,
    ctx  : Ctx,
    out  :: String
)
                 Res<usize, AllocError>

write_recv_expr = (
    be   :: CBackend,
    base : ExprId,
    c    : Call,
    f    : Function,
    sig  : Vec<TyId>,
    ctx  : Ctx,
    out  :: String
)
                  Res<usize, AllocError>
```

#### Imports and re-exports

```zen
ExprId = std.ast

Decl, Function = std.ast

Access, Call, Arg = std.ast

Param, TypeId = std.ast

ModuleOrigin, CBinding, CBindingId = std.ast

AllocError = std.mem

Vec = std.collections

str, String = std.text

Range = std.core

DeclId = sema.sema_id

TyId, TyRes = sema.sema_ty

Def, decl_at = sema.sema_def

Ctx = sema.sema_check

Inst = sema.sema_inst

type_from_ast = sema.sema_denote

satisfies_bound = sema.sema_bound

pack_slot, pack_elem = sema.sema_vararg

sym_member, sym_variant, sym_fn = gen.gen_name

RES_PATH = gen.gen_name

CBackend = gen.gen_c.gen_c_state

unsupported, unresolved, untyped, ambiguous = gen.gen_c.gen_c_report

sub_with, any_open, inst_at = gen.gen_c.gen_c_mono

settled_inst, inst_open, enter_tparams, leave_tparams = gen.gen_c.gen_c_mono

complete_inst = gen.gen_c.gen_c_infer

ctype, is_unit, has_storage, c_prim, spellable, declared_ret = gen.gen_c.gen_c_type

c_prim_known = gen.gen_c.gen_c_type

lower_checked_narrow = gen.gen_c.gen_c_num

expr, ty_of, want_of = gen.gen_c.gen_c_expr

value_held, holds = gen.gen_c.gen_c_expr

Dest, deliver = gen.gen_c.gen_c_stmt

is_print, lower_print = gen.gen_c.gen_c_print

lower_dot_call = gen.gen_c.gen_c_member

lower_loop = gen.gen_c.gen_c_loop

is_loop_shape = gen.gen_c.gen_c_shape

inlines, inline_call, closure_slot = gen.gen_c.gen_c_inline

is_null_ptr, lower_null_ptr = gen.gen_c.gen_c_ptr

lower_closure_call = gen.gen_c.gen_c_inline

construct = gen.gen_c.gen_c_build

is_format_door, lower_format_door = gen.gen_c.gen_c_fmt

is_json_door, lower_json_door = gen.gen_c.gen_c_json

recv_arg, arg_value, write_arg_at = gen.gen_c.gen_c_arg

call_callee = sema.sema_call
```

### `src/gen/gen_c/gen_c_cap.zen`

48 declarations (enums: 1, functions: 23, imports and re-exports: 24).

#### Enums

```zen
CapabilityKind* = NotCapability
    | MemAlloc
    | MemPage
    | MemRelease
    | FsWrite
    | FsRead
    | FsLock
    | FsRemove
    | FsProbe
    | LockUnlock
    | EnvVar
    | ActorSpawn
    | ActorStop
    | ClockRead
    | ThreadsSleep
    | ThreadsSpawn
    | ThreadsJoin
    | ConsolePrint
    | StdinRead
    | ScopeDefer
```

#### Functions

```zen
capability_kind* = (be :: CBackend, rty: TyId, name: str) CapabilityKind

owner_of = (be :: CBackend, rty: TyId) str

capability_owner = (be :: CBackend, n: TyNamed) str

lower_capability* = (
    be   :: CBackend,
    kind : CapabilityKind,
    id   : ExprId,
    c    : Call,
    a    : Access,
    rty  : TyId,
    mi   : usize,
    f    : Function,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

lower_typed_capability = (
    be   :: CBackend,
    kind : CapabilityKind,
    id   : ExprId,
    c    : Call,
    a    : Access,
    rty  : TyId,
    mi   : usize,
    f    : Function,
    ctx  : Ctx,
    out  :: String
) Res<(), AllocError>

cap_param = (be :: CBackend, rty: TyId, mi: usize, f: Function)
            Res<TyId, AllocError>

lower_capability_kind = (
    be   :: CBackend,
    kind : CapabilityKind,
    id   : ExprId,
    c    : Call,
    a    : Access,
    rty  : TyId,
    ret  : TyId,
    aty  : TyId,
    ctx  : Ctx,
    out  :: String
) Res<(), AllocError>

cap_ret = (be :: CBackend, rty: TyId, mi: usize, f: Function)
          Res<TyId, AllocError>

lower_alloc = (
    be  :: CBackend,
    id  : ExprId,
    a   : Access,
    rty : TyId,
    ret : TyId,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

with_state = (
    be  :: CBackend,
    id  : ExprId,
    a   : Access,
    rty : TyId,
    ret : TyId,
    pty : TyId,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

write_arena = (
    be   :: CBackend,
    a    : Access,
    rty  : TyId,
    ret  : TyId,
    pty  : TyId,
    cell : TyId,
    ctx  : Ctx,
    out  :: String
) Res<(), AllocError>

write_malloc = (be :: CBackend, tmp: str, cell: TyId, extra: str)
               Res<(), AllocError>

write_oom_guard = (be :: CBackend, a: Access, tmp: str)
                  Res<(), AllocError>

set_field = (be :: CBackend, tmp: str, cell: TyId, name: str, value: str)
            Res<(), AllocError>

write_arrow_set = (be :: CBackend, tmp: str, name: str, value: str)
                  Res<(), AllocError>

lower_page = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    ret : TyId,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

page_cell = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    ret : TyId,
    pty : TyId,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

write_page = (
    be   :: CBackend,
    c    : Call,
    ret  : TyId,
    cell : TyId,
    ctx  : Ctx,
    out  :: String
) Res<(), AllocError>

write_page_malloc = (be :: CBackend, raw: str, cty: str, szt: str)
                    Res<(), AllocError>

write_page_header = (
    be   :: CBackend,
    raw  : str,
    cty  : str,
    cell : TyId,
    szt  : str,
    prev : str
) Res<(), AllocError>

write_page_ok = (be :: CBackend, ret: TyId, cty: str, raw: str, dst: str)
                Res<(), AllocError>

lower_release = (be :: CBackend, c: Call, ctx: Ctx, out :: String)
                Res<(), AllocError>

prev_text = (be :: CBackend, c: Call, ctx: Ctx, out :: String)
            Res<(), AllocError>
```

#### Imports and re-exports

```zen
ExprId, Function, Access, Call = std.ast

AllocError = std.mem

str, String = std.text

TyId, TyNamed = sema.sema_ty

Ctx = sema.sema_check

sym_member, sym_gen = gen.gen_name

CBackend = gen.gen_c.gen_c_state

unsupported = gen.gen_c.gen_c_report

sub = gen.gen_c.gen_c_mono

ctype, request_type, declared_ret, field_of, pointee = gen.gen_c.gen_c_type

expr = gen.gen_c.gen_c_expr

arg_text = gen.gen_c.gen_c_arg

temp, payload_type = gen.gen_c.gen_c_flow

write_assign_ok, write_assign_err = gen.gen_c.gen_c_flow

close_else, close_brace, open_null_test = gen.gen_c.gen_c_flow

lower_probe, lower_write, lower_read, lower_remove, lower_lock, lower_unlock = gen.gen_c.gen_c_fs

lower_stdin_read = gen.gen_c.gen_c_stdin

lower_env_var = gen.gen_c.gen_c_env

lower_console_print, is_console_print = gen.gen_c.gen_c_print

is_defer, lower_defer = gen.gen_c.gen_c_scope

write_position = gen.gen_c.gen_c_op

lower_clock_read = gen.gen_c.gen_c_clock

lower_sleep, lower_spawn, lower_join = gen.gen_c.gen_c_threads

lower_actor_spawn, lower_actor_stop = gen.gen_c.gen_c_actor
```

### `src/gen/gen_c/gen_c_clock.zen`

15 declarations (functions: 5, imports and re-exports: 10).

#### Functions

```zen
emit_clock* = (be :: CBackend, out :: Emit) Res<(), AllocError>

write_clock = (be :: CBackend, out :: Emit) Res<(), AllocError>

write_read = (be :: CBackend, out :: Emit, fn: str, which: str)
             Res<(), AllocError>

lower_clock_read* = (
    be   :: CBackend,
    c    : Call,
    name : str,
    ret  : TyId,
    ctx  : Ctx,
    out  :: String
) Res<(), AllocError>

clock_fn = (name: str) str
```

#### Imports and re-exports

```zen
Call = std.ast

AllocError = std.mem

str, String = std.text

TyId = sema.sema_ty

Ctx = sema.sema_check

Emit = gen.gen_emit

sym_member = gen.gen_name

CBackend = gen.gen_c.gen_c_state

ctype = gen.gen_c.gen_c_type

comment = gen.gen_c.gen_c_runtime
```

### `src/gen/gen_c/gen_c_const.zen`

37 declarations (functions: 22, imports and re-exports: 15).

#### Functions

```zen
lower_global_value* = (
    be   :: CBackend,
    id   : ExprId,
    text : str,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

lower_variant_value = (
    be   :: CBackend,
    id   : ExprId,
    text : str,
    want : TyId,
    ctx  : Ctx,
    out  :: String
) Res<(), AllocError>

lower_bare_variant = (
    be   :: CBackend,
    id   : ExprId,
    d    : Def,
    text : str,
    want : TyId,
    out  :: String
) Res<(), AllocError>

lower_def_value = (
    be   :: CBackend,
    id   : ExprId,
    d    : Def,
    text : str,
    want : TyId,
    out  :: String
) Res<(), AllocError>

lower_const = (
    be   :: CBackend,
    id   : ExprId,
    d    : Def,
    text : str,
    want : TyId,
    out  :: String
) Res<(), AllocError>

lower_const_decl = (
    be   :: CBackend,
    id   : ExprId,
    x    : Decl,
    d    : Def,
    text : str,
    want : TyId,
    out  :: String
) Res<(), AllocError>

lower_const_value* = (
    be   :: CBackend,
    id   : ExprId,
    k    : Const,
    d    : Def,
    want : TyId,
    out  :: String
) Res<(), AllocError>

is_pure_value* = (be :: CBackend, id: ExprId, ctx: Ctx) bool

pure_elems = (be :: CBackend, elems: Vec<ExprId>, ctx: Ctx) bool

is_pure_name = (be :: CBackend, text: str, ctx: Ctx) bool

global_is_pure_name = (be :: CBackend, text: str, ctx: Ctx) bool

variant_is_pure_name = (be :: CBackend, text: str, ctx: Ctx) bool

is_pure_access = (be :: CBackend, a: Access, ctx: Ctx) bool

has_type_const = (be :: CBackend, a: Access, ctx: Ctx) bool

found_const = (r: Res<TypeConst>) bool

is_pure_pair = (be :: CBackend, b: Binary, ctx: Ctx) bool

is_pure_call = (be :: CBackend, c: Call, ctx: Ctx) bool

pure_callee = (be :: CBackend, c: Call, d: Def, ctx: Ctx) bool

pure_args = (be :: CBackend, c: Call, ctx: Ctx) bool

callee_def = (be :: CBackend, callee: ExprId, ctx: Ctx) Res<Def>

def_named = (be :: CBackend, text: str, ctx: Ctx) Res<Def>

is_struct_def = (d: Def) bool
```

#### Imports and re-exports

```zen
ExprId, Decl, Const = std.ast

Literal, Binary, Unary, Access, Call, Name, ArrayLit, FixedArray = std.ast

AllocError = std.mem

Vec = std.collections

str, String = std.text

TyId = sema.sema_ty

Def, decl_at = sema.sema_def

Ctx = sema.sema_check

CBackend = gen.gen_c.gen_c_state

unresolved, unsupported = gen.gen_c.gen_c_report

expr = gen.gen_c.gen_c_expr

base_decl, type_const, TypeConst = gen.gen_c.gen_c_read

intern_named, write_variant_value = gen.gen_c.gen_c_read

plain_ctx = gen.gen_c.gen_c_decl

is_null_ptr = gen.gen_c.gen_c_ptr
```

### `src/gen/gen_c/gen_c_decl.zen`

111 declarations (functions: 71, constants: 1, imports and re-exports: 39).

#### Functions

```zen
emit_program* = (be :: CBackend, mi: usize, out :: Emit)
                Res<(), AllocError>

lower_program* = (be :: CBackend, mi: usize) Res<(), AllocError>

emit_prelude = (be :: CBackend, out :: Emit) Res<(), AllocError>

emit_c_headers = (be :: CBackend, out :: Emit) Res<(), AllocError>

seed = (be :: CBackend, mi: usize) Res<(), AllocError>

seed_module = (be :: CBackend, m: Module, mi: usize) Res<(), AllocError>

seed_decl = (be :: CBackend, m: Module, mi: usize, di: usize)
            Res<(), AllocError>

seed_function = (be :: CBackend, m: Module, mi: usize, d: Decl)
                Res<(), AllocError>

seed_named = (be :: CBackend, m: Module, mi: usize, f: Function)
             Res<(), AllocError>

seed_defs = (be :: CBackend, mi: usize, f: Function) Res<(), AllocError>

seed_def = (be :: CBackend, d: Def) Res<(), AllocError>

seed_root = (be :: CBackend, d: Def) Res<(), AllocError>

is_function = (d: Def) bool

drain = (be :: CBackend) Res<(), AllocError>

more = (be :: CBackend, fi: usize, mi: usize) bool

report_overrun = (be :: CBackend, fi: usize, mi: usize) Res<(), AllocError>

overrun_at_fn = (be :: CBackend, fi: usize) Res<(), AllocError>

overrun_at_method = (be :: CBackend, mi: usize) Res<(), AllocError>

overrun_at_decl = (be :: CBackend, m: MethodRef) Res<(), AllocError>

lower_queued = (be :: CBackend, i: usize) Res<(), AllocError>

lower_queued_method = (be :: CBackend, i: usize) Res<(), AllocError>

lower_def = (be :: CBackend, d: Def) Res<(), AllocError>

lower_decl = (be :: CBackend, d: Def, x: Decl) Res<(), AllocError>

lower_function = (be :: CBackend, d: Def, x: Decl, f: Function)
                 Res<(), AllocError>

lower_body = (be :: CBackend, d: Def, x: Decl, f: Function, blk: BlockId)
             Res<(), AllocError>

lower_method_ref = (be :: CBackend, m: MethodRef) Res<(), AllocError>

method_in_decl = (be :: CBackend, m: MethodRef, x: Decl)
                 Res<(), AllocError>

method_member = (be :: CBackend, m: MethodRef, s: Struct)
                Res<(), AllocError>

supplied_member = (be :: CBackend, m: MethodRef) Res<(), AllocError>

by_sig = (be :: CBackend, m: MethodRef, found: Vec<Member>)
         Res<Res<Member>, AllocError>

member_with_sig = (be :: CBackend, m: MethodRef, found: Vec<Member>)
                  Res<Res<Member>, AllocError>

keep_same_sig = (
    be   :: CBackend,
    m    : MethodRef,
    mem  : Member,
    kept :: Vec<Member>
) Res<(), AllocError>

keep_if_same_sig = (
    be   :: CBackend,
    m    : MethodRef,
    mem  : Member,
    f    : Function,
    kept :: Vec<Member>
) Res<(), AllocError>

same_tys = (a: Vec<TyId>, b: Vec<TyId>) bool

method_body = (be :: CBackend, m: MethodRef, mem: Member)
              Res<(), AllocError>

method_fn = (be :: CBackend, m: MethodRef, mem: Member, f: Function)
            Res<(), AllocError>

method_shape = (
    be  :: CBackend,
    m   : MethodRef,
    mem : Member,
    f   : Function,
    blk : BlockId
) Res<(), AllocError>

method_tparam_owner = (be :: CBackend, f: Function, mi: usize, queued: str)
                      Res<str, AllocError>

method_self = (be :: CBackend, m: MethodRef) Res<TyId, AllocError>

generic_recv = (be: CBackend, ty: TyId) bool

open_self = (be :: CBackend, m: MethodRef) Res<TyId, AllocError>

lower_shape = (
    be      :: CBackend,
    f       : Function,
    blk     : BlockId,
    qname   : str,
    name    : str,
    span    : Span,
    sctx    : Ctx,
    self_ty : TyId,
    mi      : usize
)
              Res<(), AllocError>

return_type* = (be :: CBackend, f: Function, ctx: Ctx)
              Res<TyId, AllocError>

plain_ctx* = (be :: CBackend, mi: usize) Ctx

body_ctx* = (be :: CBackend, mi: usize, ret: TyId) Ctx

self_body_ctx* = (
    be       :: CBackend,
    mi       : usize,
    ret      : TyId,
    self_ty  : TyId,
    has_self : bool
) Ctx

bind_params = (be :: CBackend, f: Function, ctx: Ctx, sig :: Vec<TyId>)
              Res<(), AllocError>

bind_param = (be :: CBackend, p: Param, ctx: Ctx, sig :: Vec<TyId>)
             Res<(), AllocError>

write_proto = (
    be    :: CBackend,
    qname : str,
    name  : str,
    span  : Span,
    f     : Function,
    ret   : TyId,
    sig   : Vec<TyId>,
    out   :: String
)
              Res<(), AllocError>

write_params = (be :: CBackend, f: Function, sig: Vec<TyId>, out :: String)
               Res<(), AllocError>

write_param_list = (
    be  :: CBackend,
    f   : Function,
    sig : Vec<TyId>,
    out :: String
) Res<(), AllocError>

write_param = (
    be  :: CBackend,
    p   : Param,
    i   : usize,
    sig : Vec<TyId>,
    out :: String
) Res<(), AllocError>

ref_declarator* = (be :: CBackend, ty: TyId, name: str, out :: String)
                  Res<(), AllocError>

slot_index = (be :: CBackend, name: str, span: Span, out :: String)
             Res<(), AllocError>

write_param_slot* = (
    be   :: CBackend,
    name : str,
    span : Span,
    s    : LocalSlot,
    out  :: String
) Res<(), AllocError>

check_spellable = (
    be   :: CBackend,
    name : str,
    span : Span,
    ret  : TyId,
    sig  : Vec<TyId>
) Res<(), AllocError>

report_unspellable = (be :: CBackend, name: str, span: Span, t: TyId)
                     Res<(), AllocError>

write_body = (
    be       :: CBackend,
    blk      : BlockId,
    mi       : usize,
    ret      : TyId,
    self_ty  : TyId,
    has_self : bool
) Res<(), AllocError>

destination = (be :: CBackend, ret: TyId) Dest

keep = (be :: CBackend, qname: str, sig: Vec<TyId>, proto: String, span: Span)
       Res<(), AllocError>

render_symbol_map* = (be :: CBackend, out :: String) Res<(), AllocError>

write_symbol_at = (be :: CBackend, i: usize, out :: String)
                  Res<(), AllocError>

write_symbol_row = (symbol: str, span: Span, out :: String)
                   Res<(), AllocError>

write_map_field = (text: str, out :: String) Res<(), AllocError>

emit_protos = (be :: CBackend, out :: Emit) Res<(), AllocError>

write_proto_line = (out :: Emit, proto: String) Res<(), AllocError>

emit_bodies = (be :: CBackend, out :: Emit) Res<(), AllocError>

write_body_at = (be :: CBackend, out :: Emit, i: usize)
                Res<(), AllocError>

emit_header* = (be :: CBackend, out :: Emit) Res<(), AllocError>

emit_unit* = (
    be   :: CBackend,
    root : usize,
    u    : usize,
    seq  : Vec<usize>,
    out  :: Emit
)
             Res<(), AllocError>

unit_used* = (be: CBackend, u: usize) bool
```

#### Constants

```zen
MAX_FUNCTIONS* : usize = 8192
```

#### Imports and re-exports

```zen
Module, Decl, Function, Param, Span = std.ast

BlockId, Struct, Enum, Member = std.ast

AllocError = std.mem

Vec = std.collections

str, String = std.text

Range = std.core

TyId = sema.sema_ty

Def, decl_at = sema.sema_def

Ctx = sema.sema_check

Inst = sema.sema_inst

owner_of = sema.sema_inst

param_type = sema.sema_denote

self_ctx = sema.sema_member

ty_at = sema.sema_cand

Emit, order = gen.gen_emit

sym_fn, sym_local = gen.gen_name

GenFault = gen.gen_diag

CBackend, MethodRef, FnOrigin = gen.gen_c.gen_c_state

LocalSlot = gen.gen_c.gen_c_frame

sub, enter_tparams, leave_tparams = gen.gen_c.gen_c_mono

open_named = gen.gen_c.gen_c_mono

enter_struct_tparams = gen.gen_c.gen_c_mono

signature_of = gen.gen_c.gen_c_call

ctype, declarator, spellable, is_unit, has_storage, is_res = gen.gen_c.gen_c_type

declared_ret = gen.gen_c.gen_c_type

closure_storage = gen.gen_c.gen_c_report

emit_types = gen.gen_c.gen_c_layout

Dest, block = gen.gen_c.gen_c_stmt

takes_closure = gen.gen_c.gen_c_inline

impl_member_at, by_arity, kept_or_arity = gen.gen_c.gen_c_impl

method_sig, generic_method_sig = gen.gen_c.gen_c_member

emit_main = gen.gen_c.gen_c_main

emit_banner, emit_floor, emit_helpers, emit_print, emit_stderr = gen.gen_c.gen_c_runtime

emit_fs, emit_scope, emit_scope_floor = gen.gen_c.gen_c_runtime

emit_stdin = gen.gen_c.gen_c_stdin

emit_env = gen.gen_c.gen_c_env

emit_clock = gen.gen_c.gen_c_clock

emit_threads, emit_spawn_envs = gen.gen_c.gen_c_threads

emit_actor_floor, emit_actor_defs = gen.gen_c.gen_c_actor
```

### `src/gen/gen_c/gen_c_display.zen`

49 declarations (enums: 1, functions: 29, constants: 4, imports and re-exports: 15).

#### Enums

```zen
ConsoleStream = Stdout | Stderr
```

#### Functions

```zen
console_display* = (be :: CBackend, ty: TyId, text: str)
                   Res<bool, AllocError>

stderr_console* = (be :: CBackend, ty: TyId, text: str)
                  Res<bool, AllocError>

stream_display = (be :: CBackend, ty: TyId, text: str, stream: ConsoleStream)
                 Res<bool, AllocError>

display_at_site = (
    be     :: CBackend,
    ty     : TyId,
    s      : Site,
    text   : str,
    stream : ConsoleStream
)
                  Res<bool, AllocError>

display_fn = (be :: CBackend, s: Site) Res<Res<Function>, AllocError>

sink_form = (be: CBackend, found: Vec<Member>) Res<Function>

member_function = (m: Res<Member>) Res<Function>

write_display_call = (
    be     :: CBackend,
    ty     : TyId,
    s      : Site,
    f      : Function,
    text   : str,
    stream : ConsoleStream
) Res<bool, AllocError>

with_console = (
    be     :: CBackend,
    ty     : TyId,
    s      : Site,
    f      : Function,
    text   : str,
    stream : ConsoleStream
)
               Res<bool, AllocError>

emit_display = (
    be   :: CBackend,
    ty   : TyId,
    s    : Site,
    f    : Function,
    text : str,
    sink : str
) Res<bool, AllocError>

sink_display* = (
    be   :: CBackend,
    ty   : TyId,
    text : str,
    sink : str,
    out  :: String
) Res<bool, AllocError>

sink_display_at = (
    be   :: CBackend,
    ty   : TyId,
    s    : Site,
    text : str,
    sink : str,
    out  :: String
) Res<bool, AllocError>

sink_display_fn = (
    be   :: CBackend,
    ty   : TyId,
    s    : Site,
    f    : Function,
    text : str,
    sink : str,
    out  :: String
)
                  Res<bool, AllocError>

wrote_display = (
    be   :: CBackend,
    ty   : TyId,
    s    : Site,
    f    : Function,
    text : str,
    sink : str,
    out  :: String
) Res<bool, AllocError>

display_call = (
    be   :: CBackend,
    ty   : TyId,
    s    : Site,
    f    : Function,
    text : str,
    sink : str,
    out  :: String
) Res<(), AllocError>

write_sink_arg = (f: Function, sink: str, out :: String)
                 Res<(), AllocError>

stream_sink = (be :: CBackend, out :: String, stream: ConsoleStream)
              Res<bool, AllocError>

sink_ty = (be :: CBackend) Res<Res<TyId>, AllocError>

sink_named = (be :: CBackend, d: Def) Res<Res<TyId>, AllocError>

write_console = (
    be     :: CBackend,
    ty     : TyId,
    out    :: String,
    stream : ConsoleStream
)
                Res<bool, AllocError>

finish_console = (be :: CBackend, ty: TyId, inits: str, out :: String)
                 Res<bool, AllocError>

console_slot = (
    be     :: CBackend,
    s      : Slot,
    out    :: String,
    stream : ConsoleStream
)
               Res<bool, AllocError>

write_slot_init = (
    be     :: CBackend,
    s      : Slot,
    out    :: String,
    stream : ConsoleStream
)
                  Res<bool, AllocError>

console_name = (
    out    :: String,
    member : str,
    stream : ConsoleStream
) Res<(), AllocError>

console_body = (member: str, stream: ConsoleStream) str

byte_body = (member: str, stream: ConsoleStream) str

need_console_fn = (be :: CBackend, s: Slot, name: str, stream: ConsoleStream)
                  Res<(), AllocError>

emit_console_fn = (
    be     :: CBackend,
    s      : Slot,
    name   : str,
    stream : ConsoleStream
)
                   Res<(), AllocError>

console_head = (be :: CBackend, s: Slot, name: str, out :: String)
               Res<(), AllocError>
```

#### Constants

```zen
DISPLAY_MEMBER: str = "toString"

SINK_NAME: str = "Sink"

SINK_WRITE: str = "write"

SINK_WRITE_BYTE: str = "write_byte"
```

#### Imports and re-exports

```zen
Member, Function = std.ast

AllocError = std.mem

Vec = std.collections

str, String = std.text

TyId = sema.sema_ty

Def = sema.sema_def

sym_variant, RES_PATH = gen.gen_name

CBackend = gen.gen_c.gen_c_state

ctype, request_type = gen.gen_c.gen_c_type

recv_inst = gen.gen_c.gen_c_mono

Site, site_of, member_at = gen.gen_c.gen_c_member

impl_member_of, by_arity = gen.gen_c.gen_c_impl

by_ref = gen.gen_c.gen_c_arg

method_sig, member_symbol = gen.gen_c.gen_c_member

Slot, slots_of, thunk_param = gen.gen_c.gen_c_fat
```

### `src/gen/gen_c/gen_c_env.zen`

17 declarations (functions: 5, imports and re-exports: 12).

#### Functions

```zen
emit_env* = (be :: CBackend, out :: Emit) Res<(), AllocError>

write_env = (out :: Emit) Res<(), AllocError>

lower_env_var* = (
    be  :: CBackend,
    c   : Call,
    ret : TyId,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

write_getenv_call = (be :: CBackend, got: str, name: str)
                    Res<(), AllocError>

open_absent_test = (be :: CBackend, got: str) Res<(), AllocError>
```

#### Imports and re-exports

```zen
Call = std.ast

AllocError = std.mem

str, String = std.text

TyId = sema.sema_ty

Ctx = sema.sema_check

Emit = gen.gen_emit

CBackend = gen.gen_c.gen_c_state

declare_temp = gen.gen_c.gen_c_flow

comment = gen.gen_c.gen_c_runtime

str_arg = gen.gen_c.gen_c_arg

close_else, close_brace = gen.gen_c.gen_c_flow

write_assign_ok, write_assign_none = gen.gen_c.gen_c_flow
```

### `src/gen/gen_c/gen_c_expr.zen`

125 declarations (enums: 3, functions: 78, constants: 1, imports and re-exports: 43).

#### Enums

```zen
TySource = ScopeRef | Frame(TyId) | Backend(TyId) | Sema(TyId) | Unanswered

Door = Set | Hoist | Widen | Fat | Plain

Spill = Unsettled | Effect | Valued
```

#### Functions

```zen
spills* = (be: CBackend, id: ExprId) bool

spills_anywhere* = (be: CBackend, id: ExprId) bool

call_spills = (be: CBackend, c: Call) bool

holds* = (be: CBackend, c: Call, pos: usize, first: usize) bool

reorderable* = (be: CBackend, c: Call, first: usize) bool

may_reorder* = (be: CBackend, c: Call) bool

recv_slots = (be: CBackend, c: Call) usize

recv_calls = (be: CBackend, c: Call) bool

position_calls = (be: CBackend, c: Call, pos: usize, first: usize) bool

any_arg_calls = (be: CBackend, c: Call) bool

last_call_arg = (be: CBackend, c: Call) usize

later = (at: usize, i: usize, yes: bool) usize

infix_operand_held* = (be: CBackend, b: Binary) bool

has_call* = (be: CBackend, id: ExprId) bool

has_call_walk = (be: CBackend, id: ExprId) Res<bool, AllocError>

has_call_push2 = (
    work :: Vec<ExprId>,
    a    : ExprId,
    b    : ExprId
) Res<(), AllocError>

holdable* = (be: CBackend, id: ExprId) bool

ty_of* = (be :: CBackend, id: ExprId, ctx: Ctx, want: TyId)
         Res<TyId, AllocError>

ty_source = (be :: CBackend, id: ExprId, ctx: Ctx, want: TyId)
            Res<TySource, AllocError>

sema_source = (be :: CBackend, id: ExprId, ctx: Ctx)
              Res<TySource, AllocError>

local_answer = (be :: CBackend, id: ExprId) Res<Res<TyId>, AllocError>

field_slot = (be :: CBackend, a: Access) Res<Res<TyId>, AllocError>

known_field = (be :: CBackend, base: TyId, name: str)
              Res<Res<TyId>, AllocError>

named_slot = (be :: CBackend, name: str) Res<TyId>

value_slot = (be :: CBackend, s: LocalSlot) Res<TyId>

keep_known = (be :: CBackend, ty: TyId) Res<TyId>

ptr_answer = (be :: CBackend, id: ExprId, ctx: Ctx, want: TyId)
             Res<Res<TyId>, AllocError>

ptr_call_answer = (be :: CBackend, c: Call, ctx: Ctx, want: TyId)
                  Res<Res<TyId>, AllocError>

ptr_dot_answer = (be :: CBackend, c: Call, a: Access, ctx: Ctx, want: TyId)
                 Res<Res<TyId>, AllocError>

settled_answer = (be :: CBackend, id: ExprId, ctx: Ctx, got: TyId, want: TyId)
                 Res<TyId, AllocError>

opaque_answer = (be :: CBackend, id: ExprId, ctx: Ctx, got: TyId)
                Res<TyId, AllocError>

settle_open = (be :: CBackend, id: ExprId, ctx: Ctx, got: TyId, want: TyId)
              Res<TyId, AllocError>

settle_inlined = (be :: CBackend, id: ExprId, ctx: Ctx, got: TyId)
                 Res<TyId, AllocError>

settle_call = (be :: CBackend, id: ExprId, ctx: Ctx, got: TyId)
              Res<TyId, AllocError>

fallback_type = (be :: CBackend, id: ExprId, ctx: Ctx, want: TyId)
                Res<TyId, AllocError>

call_type = (be :: CBackend, c: Call, ctx: Ctx, want: TyId)
            Res<TyId, AllocError>

named_call_type = (be :: CBackend, name: str, ctx: Ctx, want: TyId)
                  Res<TyId, AllocError>

declared_call_type = (be :: CBackend, name: str, ctx: Ctx, want: TyId)
                     Res<TyId, AllocError>

sugar_call_type = (be :: CBackend, name: str, want: TyId)
                  Res<TyId, AllocError>

def_call_type = (be :: CBackend, found: Vec<Def>, want: TyId)
                Res<TyId, AllocError>

def_result_type = (be :: CBackend, d: Def, want: TyId)
                  Res<TyId, AllocError>

function_ret = (be :: CBackend, d: Def, want: TyId) Res<TyId, AllocError>

decl_ret = (be :: CBackend, d: Def, x: Decl, want: TyId)
           Res<TyId, AllocError>

written_ret = (be :: CBackend, ret: Res<TypeId>, ctx: Ctx, want: TyId)
              Res<TyId, AllocError>

try_value_type = (be :: CBackend, operand: ExprId, ctx: Ctx, want: TyId)
                 Res<TyId, AllocError>

res_type_of* = (be :: CBackend, id: ExprId, ctx: Ctx)
               Res<TyId, AllocError>

expr* = (be :: CBackend, id: ExprId, ctx: Ctx, want: TyId, out :: String)
        Res<(), AllocError>

door_of = (be :: CBackend, id: ExprId, ctx: Ctx, want: TyId)
          Res<Door, AllocError>

fat_expr = (
    be   :: CBackend,
    id   : ExprId,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

value_expr* = (
    be   :: CBackend,
    id   : ExprId,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

spill_temp = (
    be   :: CBackend,
    id   : ExprId,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

spill_of = (be :: CBackend, ty: TyId) Spill

want_of* = (be :: CBackend, id: ExprId, ctx: Ctx) Res<TyId, AllocError>

settled_place = (be :: CBackend, ty: TyId) bool

spill_effect = (
    be  :: CBackend,
    id  : ExprId,
    ctx : Ctx,
    ty  : TyId,
    out :: String
) Res<(), AllocError>

spill_valued = (
    be  :: CBackend,
    id  : ExprId,
    ctx : Ctx,
    ty  : TyId,
    out :: String
) Res<(), AllocError>

value_held* = (
    be   :: CBackend,
    id   : ExprId,
    ctx  : Ctx,
    want : TyId,
    hold : bool,
    out  :: String
) Res<(), AllocError>

hold_value = (
    be   :: CBackend,
    id   : ExprId,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

write_expr = (
    be   :: CBackend,
    id   : ExprId,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

lower_consume = (
    be   :: CBackend,
    x    : Consume,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

release_moved = (be :: CBackend, id: ExprId) Res<(), AllocError>

lower_paren = (
    be   :: CBackend,
    id   : ExprId,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

lower_literal = (
    be   :: CBackend,
    id   : ExprId,
    l    : Literal,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

lower_int_literal = (text: str, out :: String) Res<(), AllocError>

over_i64 = (text: str) bool

lower_str_literal = (be :: CBackend, l: Literal, out :: String)
                    Res<(), AllocError>

decoded_len* = (raw: str) usize

lower_meta_or_access* = (
    be   :: CBackend,
    id   : ExprId,
    a    : Access,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

chain_count = (be :: CBackend, call_id: ExprId, out :: String)
              Res<(), AllocError>

lower_meta_name = (text: str, out :: String) Res<(), AllocError>

lower_meta_count* = (
    be  :: CBackend,
    t   : TypeId,
    out :: String
) Res<(), AllocError>

lower_name = (
    be   :: CBackend,
    id   : ExprId,
    text : str,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

write_name_slot* = (
    be   :: CBackend,
    name : str,
    span : Span,
    slot : LocalSlot,
    out  :: String
) Res<(), AllocError>

named_hole* = (be :: CBackend, name: str, out :: String)
              Res<Res<TyId>, AllocError>

hole_text = (be :: CBackend, name: str, s: LocalSlot, out :: String)
            Res<Res<TyId>, AllocError>

write_local = (be :: CBackend, text: str, slot: LocalSlot, out :: String)
              Res<(), AllocError>

write_deref = (be :: CBackend, text: str, slot: LocalSlot, out :: String)
              Res<(), AllocError>

lower_global_name = (
    be   :: CBackend,
    id   : ExprId,
    text : str,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>
```

#### Constants

```zen
I64_MAX_DIGITS: str = "9223372036854775807"
```

#### Imports and re-exports

```zen
ExprId, Block, Span = std.ast

Decl, Consume = std.ast

Literal, Binary, Unary, Match = std.ast

Access, Call = std.ast

TypeId = std.ast

AllocError = std.mem

Vec = std.collections

str, String = std.text

Range = std.core

TyId = sema.sema_ty

Def, decl_at = sema.sema_def

Ctx = sema.sema_check

type_of = sema.sema_type

type_from_ast = sema.sema_denote

sym_local = gen.gen_name

CBackend = gen.gen_c.gen_c_state

LocalSlot = gen.gen_c.gen_c_frame

sub, constructed, unsettled = gen.gen_c.gen_c_mono

has_var = sema.sema_inst

loop_result_type = gen.gen_c.gen_c_shape

unsupported, closure_storage = gen.gen_c.gen_c_report

declarator, is_unit, has_storage = gen.gen_c.gen_c_type

lower_access = gen.gen_c.gen_c_read

access_field_type = gen.gen_c.gen_c_read

lower_array_lit, lower_fixed_array = gen.gen_c.gen_c_array

request_type = gen.gen_c.gen_c_type

Dest, deliver, destination_type = gen.gen_c.gen_c_stmt

lower_call, res_value, is_res_ctor = gen.gen_c.gen_c_call

call_callee = sema.sema_call

needs_hoist, hoist_expr = gen.gen_c.gen_c_hoist

needs_widen, widen_expr, needs_set, set_expr = gen.gen_c.gen_c_widen

is_print, body_end = gen.gen_c.gen_c_print

call_ret_type = gen.gen_c.gen_c_infer

lower_unary, lower_binary, binary_type = gen.gen_c.gen_c_op

lower_index, index_type = gen.gen_c.gen_c_index

is_ptr_member, ptr_member_type = gen.gen_c.gen_c_ptr

create_type = gen.gen_c.gen_c_alloc

field_of = gen.gen_c.gen_c_type

inline_result_type = gen.gen_c.gen_c_settle

needs_fat, write_fat_value = gen.gen_c.gen_c_fat

release_binding = gen.gen_c.gen_c_own

lower_scope_ref, is_scope_ref, scope_type = gen.gen_c.gen_c_scope

lower_global_value = gen.gen_c.gen_c_const
```

### `src/gen/gen_c/gen_c_fat.zen`

94 declarations (types: 1, functions: 69, imports and re-exports: 24).

#### Types

```zen
Slot* = {
    name*: str,
    f*: Function,
    sym*: String,
    params*: Vec<TyId>,
    ret*: TyId,
    elems*: usize,
}
```

#### Functions

```zen
is_fat* = (be: CBackend, ty: TyId) bool

fat_decl* = (be: CBackend, ty: TyId) Res<Struct>

fat_named = (be: CBackend, n: TyNamed) Res<Struct>

fat_struct = (d: Decl) Res<Struct>

behaviour_only = (s: Struct) Res<Struct>

behaviour_count = (s: Struct) usize

storage_count = (s: Struct) usize

is_behaviour = (m: Member) bool

is_storage = (m: Member) bool

slots_of* = (be :: CBackend, ty: TyId, out :: Vec<Slot>)
            Res<(), AllocError>

collect_slots = (be :: CBackend, ty: TyId, s: Struct, out :: Vec<Slot>)
                Res<(), AllocError>

collect_slot = (be :: CBackend, ty: TyId, m: Member, out :: Vec<Slot>)
               Res<(), AllocError>

add_slot = (be :: CBackend, ty: TyId, f: Function, out :: Vec<Slot>)
           Res<(), AllocError>

add_slot_at = (
    be  :: CBackend,
    ty  : TyId,
    s   : Site,
    f   : Function,
    out :: Vec<Slot>
) Res<(), AllocError>

carry_inst = (from: Inst, out :: Inst) Res<(), AllocError>

carry_one = (from: Inst, i: usize, out :: Inst) Res<(), AllocError>

carry_bound = (from: Inst, i: usize, v: TyId, out :: Inst)
              Res<(), AllocError>

erase_tparams = (be :: CBackend, f: Function, owner: str, out :: Inst)
                Res<(), AllocError>

erase_one = (
    be    :: CBackend,
    tp    : TParam,
    owner : str,
    byte  : TyId,
    out   :: Inst
) Res<(), AllocError>

erased_params = (
    be    :: CBackend,
    f     : Function,
    sctx  : Ctx,
    erase : Inst,
    out   :: Vec<TyId>
) Res<(), AllocError>

erased_param = (
    be    :: CBackend,
    p     : Param,
    i     : usize,
    sctx  : Ctx,
    erase : Inst,
    out   :: Vec<TyId>
) Res<(), AllocError>

add_erased = (
    be    :: CBackend,
    p     : Param,
    sctx  : Ctx,
    erase : Inst,
    out   :: Vec<TyId>
) Res<(), AllocError>

erased_ret = (be :: CBackend, f: Function, sctx: Ctx, erase: Inst)
             Res<TyId, AllocError>

slot_sym = (be :: CBackend, f: Function, out: Vec<Slot>)
           Res<String, AllocError>

number_sym = (sym :: String, n: usize) Res<(), AllocError>

same_named = (out: Vec<Slot>, name: str) usize

slot_field* = (be :: CBackend, s: Slot, out :: String)
              Res<(), AllocError>

slot_param = (be :: CBackend, p: TyId, out :: String) Res<(), AllocError>

request_slots* = (be :: CBackend, ty: TyId) Res<(), AllocError>

request_slot_types = (be :: CBackend, ty: TyId) Res<(), AllocError>

request_slot = (be :: CBackend, s: Slot) Res<(), AllocError>

request_if_real = (be :: CBackend, t: TyId) Res<(), AllocError>

request_named_only = (be :: CBackend, t: TyId) Res<(), AllocError>

fat_value* = (
    be   :: CBackend,
    addr : str,
    cty  : TyId,
    tty  : TyId,
    out  :: String
) Res<(), AllocError>

slot_init = (be :: CBackend, s: Slot, cty: TyId, out :: String)
            Res<(), AllocError>

thunk_for = (be :: CBackend, s: Slot, cty: TyId)
            Res<Res<String>, AllocError>

thunk_at_site = (be :: CBackend, s: Slot, cty: TyId, cs: Site)
                Res<Res<String>, AllocError>

supplied_thunk = (be :: CBackend, s: Slot, cty: TyId, cs: Site)
                 Res<Res<String>, AllocError>

write_thunk = (be :: CBackend, s: Slot, cty: TyId, cs: Site, f: Function)
              Res<Res<String>, AllocError>

real_sig = (
    be    :: CBackend,
    cty   : TyId,
    cs    : Site,
    f     : Function,
    owner : str,
    inst  : Inst,
    out   :: Vec<TyId>
) Res<(), AllocError>

add_real = (
    be   :: CBackend,
    p    : Param,
    sctx : Ctx,
    inst : Inst,
    out  :: Vec<TyId>
) Res<(), AllocError>

thunk_name = (out :: String, sym: str) Res<(), AllocError>

emit_thunk = (
    be   :: CBackend,
    s    : Slot,
    cty  : TyId,
    f    : Function,
    sig  : Vec<TyId>,
    sym  : str,
    name : str
) Res<(), AllocError>

thunk_head = (be :: CBackend, s: Slot, name: str, out :: String)
             Res<(), AllocError>

size_ty = (be :: CBackend) TyId

thunk_param* = (be :: CBackend, p: TyId, stem: str, i: usize, out :: String)
              Res<(), AllocError>

thunk_body = (
    be  :: CBackend,
    s   : Slot,
    cty : TyId,
    f   : Function,
    sig : Vec<TyId>,
    sym : str,
    out :: String
)
             Res<(), AllocError>

thunk_recv = (be :: CBackend, cty: TyId, f: Function, out :: String)
             Res<(), AllocError>

recv_by_ref = (f: Function) bool

thunk_arg = (
    be  :: CBackend,
    s   : Slot,
    sig : Vec<TyId>,
    i   : usize,
    out :: String
) Res<(), AllocError>

scales = (be: CBackend, s: Slot, i: usize) bool

is_count = (be: CBackend, s: Slot, i: usize) bool

is_usize = (be: CBackend, t: TyId) bool

is_run = (be: CBackend, s: Slot, i: usize) bool

is_pointer* = (be: CBackend, t: TyId) bool

scaled_arg = (be :: CBackend, nm: str, out :: String) Res<(), AllocError>

cast_arg = (
    be  :: CBackend,
    s   : Slot,
    sig : Vec<TyId>,
    i   : usize,
    nm  : str,
    out :: String
) Res<(), AllocError>

needs_fat* = (be :: CBackend, id: ExprId, ctx: Ctx, want: TyId)
             Res<bool, AllocError>

value_is_concrete = (be :: CBackend, id: ExprId, ctx: Ctx, want: TyId)
                    Res<bool, AllocError>

is_concrete = (be: CBackend, ty: TyId) bool

is_named = (be: CBackend, ty: TyId) bool

write_fat_value* = (
    be   :: CBackend,
    code : str,
    cty  : TyId,
    want : TyId,
    out  :: String
) Res<(), AllocError>

address_of* = (be :: CBackend, code: str, cty: TyId, out :: String)
             Res<(), AllocError>

write_amp = (code: str, out :: String) Res<(), AllocError>

spill_address = (be :: CBackend, code: str, cty: TyId, out :: String)
                Res<(), AllocError>

is_place = (code: str) bool

place_bytes = (code: str) bool

is_place_byte = (b: u8) bool

has_call = (code: str) bool
```

#### Imports and re-exports

```zen
ExprId, Decl, Struct, Member = std.ast

Function, Param, TParam = std.ast

AllocError = std.mem

Vec = std.collections

str, String = std.text

Range = std.core

TyId, TyNamed = sema.sema_ty

decl_at = sema.sema_def

Ctx = sema.sema_check

Inst, has_var = sema.sema_inst

self_ctx = sema.sema_member

param_type = sema.sema_denote

sym_member, sym_fn, sym_gen, qualify = gen.gen_name

USR, GEN = gen.gen_name

CBackend, MethodRef = gen.gen_c.gen_c_state

sub_with, intern_var, recv_inst = gen.gen_c.gen_c_mono

enter_tparams, leave_tparams, enter_struct_tparams = gen.gen_c.gen_c_mono

ctype, declarator, is_unit, request_type, declared_ret = gen.gen_c.gen_c_type

is_ptr_named = gen.gen_c.gen_c_type

ty_of = gen.gen_c.gen_c_expr

init_temp = gen.gen_c.gen_c_flow

Site, site_of, member_at = gen.gen_c.gen_c_member

impl_member, bodied_fn = gen.gen_c.gen_c_impl

write_cast = gen.gen_c.gen_c_bound
```

### `src/gen/gen_c/gen_c_floor.zen`

33 declarations (types: 1, functions: 13, constants: 1, imports and re-exports: 18).

#### Types

```zen
Floor = {
    name: str,
    fn: Function,
}
```

#### Functions

```zen
is_floor_door* = (be: CBackend, name: str, f: Function) bool

lower_floor_door* = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    a   : Access,
    rty : TyId,
    s   : Site,
    f   : Function,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

floor_of = (be :: CBackend, s: Site, sctx: Ctx, ret: TyId)
           Res<Res<Floor>, AllocError>

named_floor = (be :: CBackend, s: Site, sctx: Ctx, ret: TyId, name: str)
              Res<Res<Floor>, AllocError>

keep_floor = (
    be   :: CBackend,
    sctx : Ctx,
    ret  : TyId,
    name : str,
    m    : Member,
    out  :: Vec<Floor>
) Res<(), AllocError>

keep_floor_fn = (
    be   :: CBackend,
    sctx : Ctx,
    ret  : TyId,
    name : str,
    g    : Function,
    out  :: Vec<Floor>
) Res<(), AllocError>

floor_shape = (be :: CBackend, g: Function, sctx: Ctx)
              Res<bool, AllocError>

takes_str = (be :: CBackend, g: Function, sctx: Ctx) Res<bool, AllocError>

param_is_str = (be :: CBackend, p: Param, sctx: Ctx) Res<bool, AllocError>

keep_if_answers = (
    be   :: CBackend,
    sctx : Ctx,
    ret  : TyId,
    name : str,
    g    : Function,
    out  :: Vec<Floor>
) Res<(), AllocError>

answer_of = (be :: CBackend, g: Function, sctx: Ctx) Res<TyId, AllocError>

open_floor = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    a   : Access,
    rty : TyId,
    s   : Site,
    w   : Floor,
    ret : TyId,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

write_floor_door = (
    be   :: CBackend,
    id   : ExprId,
    c    : Call,
    a    : Access,
    rty  : TyId,
    s    : Site,
    w    : Floor,
    ret  : TyId,
    sig  : Vec<TyId>,
    inst : Inst,
    ctx  : Ctx,
    out  :: String
) Res<(), AllocError>
```

#### Constants

```zen
RAW_FLOOR: str = "add"
```

#### Imports and re-exports

```zen
ExprId, Function, Param, Member, Call, Access = std.ast

AllocError = std.mem

Vec = std.collections

str, String = std.text

TyId = sema.sema_ty

Ctx = sema.sema_check

Inst = sema.sema_inst

self_ctx = sema.sema_member

type_from_ast, param_type = sema.sema_denote

CBackend = gen.gen_c.gen_c_state

unsupported = gen.gen_c.gen_c_report

declare_temp = gen.gen_c.gen_c_flow

arg_value, write_arg, by_ref = gen.gen_c.gen_c_arg

Site, member_at, method_sig, member_symbol = gen.gen_c.gen_c_member

recv_inst, inst_open, any_open = gen.gen_c.gen_c_mono

Piece, write_pieces, write_ok, write_done = gen.gen_c.gen_c_sink

bodyless, sink_door_shape = gen.gen_c.gen_c_sink

FORMAT_DOOR, SINK_FLOOR = gen.gen_c.gen_c_sink
```

### `src/gen/gen_c/gen_c_flow.zen`

81 declarations (types: 1, functions: 54, imports and re-exports: 26).

#### Types

```zen
PatternSite = {
    ty: TyId,
    place: str,
    at = (self: @Self, ty: TyId, place: str) PatternSite
    open = (self: @Self, be :: CBackend, arm: Arm, i: usize)
           Res<(), AllocError>
    cond = (self: @Self, be :: CBackend, pid: PatternId, out :: String)
           Res<(), AllocError>
    destructure_cond = (
        self: @Self,
        be   :: CBackend,
        d    : Destructure,
        out  :: String
    ) Res<(), AllocError>
    plain_ctor_cond = (self: @Self, be :: CBackend, d: Destructure,
                       out :: String) Res<(), AllocError>
    member_ctor_cond = (self: @Self, be :: CBackend, d: Destructure,
                        mty: TyId, out :: String) Res<(), AllocError>
    leaf_cond = (self: @Self, be :: CBackend, pid: PatternId,
                 out :: String) Res<(), AllocError>
    leaf_tag_cond = (self: @Self, be :: CBackend, pat: Pattern,
                     out :: String) Res<(), AllocError>
    payload_cond = (self: @Self, be :: CBackend, d: Destructure,
                    out :: String) Res<(), AllocError>
    nested_cond = (self: @Self, be :: CBackend, d: Destructure,
                   ty: TyId, out :: String) Res<(), AllocError>
    write_nested_cond = (self: @Self, be :: CBackend, d: Destructure,
                         ty: TyId, out :: String) Res<(), AllocError>
    literal_cond = (self: @Self, be :: CBackend, pat: Pattern,
                    l: Literal, out :: String) Res<(), AllocError>
    str_cond = (self: @Self, be :: CBackend, pat: Pattern, l: Literal,
                out :: String) Res<(), AllocError>
    name_cond = (self: @Self, be :: CBackend, q: QualifiedName,
                 out :: String) Res<(), AllocError>
    set_name_cond = (self: @Self, be :: CBackend, text: str,
                     out :: String) Res<(), AllocError>
    set_name_arm = (self: @Self, be :: CBackend, mty: TyId, text: str,
                    out :: String) Res<(), AllocError>
    leaf_case_cond = (self: @Self, be :: CBackend, case: str,
                      out :: String) Res<(), AllocError>
    tag_cond = (self: @Self, be :: CBackend, q: QualifiedName,
                out :: String) Res<(), AllocError>
    tag_name = (self: @Self, be :: CBackend, name: str, out :: String)
               Res<(), AllocError>
    bind = (self: @Self, be :: CBackend, pid: PatternId)
           Res<(), AllocError>
    bind_name = (self: @Self, be :: CBackend, q: QualifiedName)
                Res<(), AllocError>
    bind_payload = (self: @Self, be :: CBackend, d: Destructure)
                   Res<(), AllocError>
    enum_bind_payload = (self: @Self, be :: CBackend, d: Destructure)
                        Res<(), AllocError>
    bind_unit_payload = (self: @Self, be :: CBackend, pid: PatternId)
                        Res<(), AllocError>
    bind_unit_name = (self: @Self, be :: CBackend, name: str)
                     Res<(), AllocError>
    set_bind_payload = (self: @Self, be :: CBackend, d: Destructure,
                        mty: TyId) Res<(), AllocError>
    bind_inner = (self: @Self, be :: CBackend, d: Destructure, ty: TyId)
                 Res<(), AllocError>
}
```

#### Functions

```zen
lower_match* = (
    be   :: CBackend,
    node : Expr,
    m    : Match,
    ctx  : Ctx,
    ty   : TyId,
    dst  : Dest
) Res<(), AllocError>

declare_temp* = (be :: CBackend, ty: TyId, name: str) Res<(), AllocError>

temp* = (be :: CBackend, ty: TyId, stem: str) Res<String, AllocError>

init_temp* = (be :: CBackend, ty: TyId, stem: str, value: str)
             Res<String, AllocError>

first_arm = (be :: CBackend, cond: str) Res<(), AllocError>

chain_arm = (be :: CBackend, cond: str) Res<(), AllocError>

close_arms = (be :: CBackend, node: Expr, m: Match) Res<(), AllocError>

close_chain = (be :: CBackend, node: Expr, m: Match) Res<(), AllocError>

write_unreachable = (be :: CBackend, node: Expr, m: Match)
                    Res<(), AllocError>

leaf_of = (pat: Pattern) str

bare_payload = (be :: CBackend, d: Destructure) Res<(), AllocError>

narrows = (be :: CBackend, pid: PatternId, st: TyId) bool

payload_place = (
    be      :: CBackend,
    variant : str,
    scrut   : str,
    out     :: String
) Res<(), AllocError>

set_member_place = (
    be     :: CBackend,
    member : TyId,
    scrut  : str,
    out    :: String
) Res<(), AllocError>

report_nested = (be :: CBackend, inner: Pattern) Res<(), AllocError>

bool_cond = (text: str, scrut: str, out :: String) Res<(), AllocError>

negate = (scrut: str, out :: String) Res<(), AllocError>

equality = (scrut: str, text: str, out :: String) Res<(), AllocError>

write_str_cond = (l: Literal, scrut: str, out :: String)
                 Res<(), AllocError>

str_bytes_cond = (l: Literal, scrut: str, n: usize, out :: String)
                 Res<(), AllocError>

unsupported_cond = (be :: CBackend, pat: Pattern, out :: String)
                   Res<(), AllocError>

leaf_name_of = (be :: CBackend, mty: TyId) Res<str, AllocError>

last_segment_str = (qname: String) str

bind_local = (be :: CBackend, name: str, ty: TyId, init: str)
             Res<(), AllocError>

is_variant* = (be :: CBackend, st: TyId, name: str) bool

res_has = (r: TyRes, name: str) bool

failure_name = (r: TyRes, name: str) bool

enum_has = (be :: CBackend, n: TyNamed, name: str) bool

decl_has = (d: Decl, name: str) bool

variants_have = (variants: Vec<Variant>, name: str) bool

enum_path* = (be :: CBackend, st: TyId, out :: String) Res<(), AllocError>

payload_type* = (be :: CBackend, st: TyId, variant: str) Res<TyId>

res_payload = (be :: CBackend, r: TyRes, variant: str) Res<TyId>

res_error_payload = (be :: CBackend, r: TyRes, variant: str) Res<TyId>

non_unit = (be :: CBackend, id: TyId) Res<TyId>

enum_payload = (be :: CBackend, n: TyNamed, variant: str) Res<TyId>

decl_payload = (be :: CBackend, n: TyNamed, d: Decl, variant: str)
               Res<TyId>

variant_payload = (
    be       :: CBackend,
    n        : TyNamed,
    variants : Vec<Variant>,
    variant  : str
) Res<TyId>

collect_payload = (
    be       :: CBackend,
    n        : TyNamed,
    variants : Vec<Variant>,
    variant  : str,
    found    :: Vec<TyId>
) Res<(), AllocError>

keep_payload = (
    be      :: CBackend,
    n       : TyNamed,
    v       : Variant,
    variant : str,
    ctx     : Ctx,
    inst    : Inst,
    found   :: Vec<TyId>
)
               Res<(), AllocError>

add_payload_type = (
    be    :: CBackend,
    n     : TyNamed,
    v     : Variant,
    ctx   : Ctx,
    inst  : Inst,
    found :: Vec<TyId>
) Res<(), AllocError>

first_payload = (be :: CBackend, found: Vec<TyId>) Res<TyId>

write_assign_none* = (be :: CBackend, ret: TyId, dst: str)
                    Res<(), AllocError>

write_assign_ok_unit* = (be :: CBackend, ret: TyId, dst: str)
                       Res<(), AllocError>

write_assign_ok* = (be :: CBackend, ret: TyId, payload: str, dst: str)
                  Res<(), AllocError>

write_assign_err* = (be :: CBackend, ret: TyId, name: str, dst: str)
                   Res<(), AllocError>

write_err_payload = (be :: CBackend, ety: TyId, name: str, out :: String)
                    Res<(), AllocError>

write_err_variant = (be :: CBackend, ety: TyId, name: str, out :: String)
                    Res<(), AllocError>

res_head = (be :: CBackend, ret: TyId, variant: str)
           Res<String, AllocError>

finish_res = (be :: CBackend, value :: String, dst: str)
             Res<(), AllocError>

open_rc_test* = (be :: CBackend, rc: str) Res<(), AllocError>

open_null_test* = (be :: CBackend, raw: str) Res<(), AllocError>

close_else* = (be :: CBackend) Res<(), AllocError>

close_brace* = (be :: CBackend) Res<(), AllocError>
```

#### Imports and re-exports

```zen
Expr, Match, Arm, Pattern, PatternId = std.ast

Literal, Decl, Enum, Variant = std.ast

Destructure, QualifiedName = std.ast

AllocError = std.mem

Vec = std.collections

str, String = std.text

Range = std.core

TyId, TyNamed, TyRes, is_failure = sema.sema_ty

decl_at = sema.sema_def

Ctx = sema.sema_check

Inst = sema.sema_inst

last_segment = sema.sema_match

member_of = sema.sema_union

sym_local, sym_member, sym_variant = gen.gen_name

sym_union_member = gen.gen_name

RES_PATH = gen.gen_name

GenFault = gen.gen_diag

CBackend = gen.gen_c.gen_c_state

enter_struct_tparams, leave_tparams = gen.gen_c.gen_c_mono

declarator, is_unit, variant_type, decl_ctx = gen.gen_c.gen_c_type

decl_inst = gen.gen_c.gen_c_type

write_qname = gen.gen_c.gen_c_layout

Dest, deliver = gen.gen_c.gen_c_stmt

res_type_of, decoded_len = gen.gen_c.gen_c_expr

is_str = gen.gen_c.gen_c_read

write_position = gen.gen_c.gen_c_op
```

### `src/gen/gen_c/gen_c_fmt.zen`

34 declarations (types: 1, functions: 13, imports and re-exports: 20).

#### Types

```zen
FormatCall = {
    id: ExprId,
    c: Call,
    d: Def,
    f: Function,
    recv: Res<ExprId>,
    ctx: Ctx,
}
```

#### Functions

```zen
is_format_door* = (be: CBackend, d: Def, f: Function) bool

is_alloc_door = (be: CBackend, d: Def, f: Function) bool

lower_format_door* = (
    be   :: CBackend,
    id   : ExprId,
    c    : Call,
    d    : Def,
    f    : Function,
    recv : Res<ExprId>,
    ctx  : Ctx,
    out  :: String
) Res<(), AllocError>

lower_alloc_door = (
    be   :: CBackend,
    site : FormatCall,
    out  :: String
) Res<(), AllocError>

empty_form = (be :: CBackend, d: Def) Res<Res<Def>, AllocError>

keep_empty = (be :: CBackend, x: Def, out :: Vec<Def>)
             Res<(), AllocError>

lower_with_empty = (
    be   :: CBackend,
    site : FormatCall,
    e    : Def,
    out  :: String
) Res<(), AllocError>

door_return = (be :: CBackend, d: Def, f: Function) Res<TyId, AllocError>

write_door = (
    be   :: CBackend,
    site : FormatCall,
    e    : Def,
    buf  : TyId,
    ret  : TyId,
    out  :: String
) Res<(), AllocError>

write_empty_call = (
    be   :: CBackend,
    site : FormatCall,
    e    : Def,
    ret  : TyId,
    tmp  : str
) Res<(), AllocError>

write_alloc = (be :: CBackend, e: Def, a: ExprId, ctx: Ctx, out :: String)
              Res<(), AllocError>

write_buffer_pieces = (
    be   :: CBackend,
    site : FormatCall,
    buf  : TyId,
    ret  : TyId,
    tmp  : str,
    done : usize
) Res<(), AllocError>

write_failure_arm = (
    be   :: CBackend,
    ret  : TyId,
    tmp  : str,
    fail : usize,
    done : usize
) Res<(), AllocError>
```

#### Imports and re-exports

```zen
ExprId, Function, Call = std.ast

AllocError = std.mem

Vec = std.collections

str, String = std.text

TyId = sema.sema_ty

Def, decl_at = sema.sema_def

Ctx = sema.sema_check

Inst = sema.sema_inst

sym_member = gen.gen_name

GenFault = gen.gen_diag

CBackend = gen.gen_c.gen_c_state

unsupported = gen.gen_c.gen_c_report

expr = gen.gen_c.gen_c_expr

declare_temp = gen.gen_c.gen_c_flow

signature_of = gen.gen_c.gen_c_call

recv_arg = gen.gen_c.gen_c_arg

write_assign_err = gen.gen_c.gen_c_flow

is_sink_door, lower_sink_door, bodyless = gen.gen_c.gen_c_sink

last_is_variadic, call_symbol, lower_pieces_into = gen.gen_c.gen_c_sink

write_jump_unless_ok, write_goto, write_done = gen.gen_c.gen_c_sink
```

### `src/gen/gen_c/gen_c_fold.zen`

36 declarations (types: 1, functions: 17, imports and re-exports: 18).

#### Types

```zen
Fold* = {
    cell*: str,
    ty*: TyId,
    has*: bool,
}
```

#### Functions

```zen
no_fold* = (be :: CBackend) Res<Fold, AllocError>

lower_fold* = (
    be   :: CBackend,
    id   : ExprId,
    sh   : Shape,
    args : Vec<ExprId>,
    lam  : Lambda,
    ctx  : Ctx,
    want : TyId,
    out  :: String
)
             Res<(), AllocError>

lower_seeded = (
    be   :: CBackend,
    id   : ExprId,
    sh   : Shape,
    args : Vec<ExprId>,
    seed : ExprId,
    lam  : Lambda,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

acc_type = (be :: CBackend, seed: ExprId, ctx: Ctx, want: TyId)
           Res<TyId, AllocError>

settled_acc = (be :: CBackend, got: TyId, want: TyId)
              Res<TyId, AllocError>

lower_with_acc = (
    be   :: CBackend,
    id   : ExprId,
    sh   : Shape,
    args : Vec<ExprId>,
    seed : ExprId,
    aty  : TyId,
    lam  : Lambda,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

bind_acc* = (be :: CBackend, sh: Shape, lam: Lambda, fold: Fold)
           Res<(), AllocError>

acc_slot = (sh: Shape) usize

result_element* = (be :: CBackend, id: ExprId, ctx: Ctx)
                 Res<Res<TyId>, AllocError>

seed_element = (be :: CBackend, seed: ExprId, ctx: Ctx)
               Res<Res<TyId>, AllocError>

seed_arg = (be :: CBackend, id: ExprId) Res<ExprId>

fold_seed = (be :: CBackend, id: ExprId, f: Function) Res<ExprId>

is_fold = (be :: CBackend, f: Function) bool

seed_before_body = (be :: CBackend, id: ExprId) Res<ExprId>

call_seed = (be :: CBackend, c: Call) Res<ExprId>

write_fold_result* = (be :: CBackend, st: LoopFrame, fold: Fold)
                     Res<(), AllocError>

write_ok_acc = (be :: CBackend, st: LoopFrame, fold: Fold)
               Res<(), AllocError>
```

#### Imports and re-exports

```zen
ExprId, Lambda, Function, Call = std.ast

AllocError = std.mem

Vec = std.collections

str, String = std.text

TyId = sema.sema_ty

Ctx = sema.sema_check

sym_member, sym_variant, RES_PATH = gen.gen_name

CBackend = gen.gen_c.gen_c_state

LoopFrame = gen.gen_c.gen_c_frame

unsupported = gen.gen_c.gen_c_report

ctype, declarator, res_value = gen.gen_c.gen_c_type

ty_of = gen.gen_c.gen_c_expr

Dest, deliver = gen.gen_c.gen_c_stmt

lower_walk, settle_res, bind_element = gen.gen_c.gen_c_loop

Shape, shape_of, loop_element, loop_fn_at = gen.gen_c.gen_c_shape

arg_value, recv_of = gen.gen_c.gen_c_shape

has_var = sema.sema_inst

literal_default = sema.sema_ty
```

### `src/gen/gen_c/gen_c_frame.zen`

11 declarations (types: 5, imports and re-exports: 6).

#### Types

```zen
LocalSlot* = {
    name*: str,
    index*: usize,
    ty*: TyId,
    by_ref*: bool,
    handle*: usize,
    closure*: usize,
    is_closure* = (self: @Self) bool
    is_handle* = (self: @Self) bool
    is_value* = (self: @Self) bool
}

Closure* = {
    lam*: Lambda,
    ptys*: Vec<TyId>,
    ret*: TyId,
    home*: usize,
    check_home*: usize,
    floor*: usize,
    inst*: Inst,
    ctx*: Ctx,
}

LoopFrame* = {
    brk*: usize,
    cnt*: usize,
    result*: str,
    has_result*: bool,
    ty*: TyId,
    depth*: usize,
}

DropEntry* = {
    name*: str,
    index*: usize,
    ty*: TyId,
    live*: usize,
}

BlockFrame* = {
    mark*: usize,
    rec*: usize,
}
```

#### Imports and re-exports

```zen
str = std.text

Vec = std.collections

TyId = sema.sema_ty

Ctx = sema.sema_check

Inst = sema.sema_inst

Lambda = std.ast
```

### `src/gen/gen_c/gen_c_fs.zen`

48 declarations (types: 3, functions: 27, imports and re-exports: 18).

#### Types

```zen
FsResult = {
    ret: TyId,
    rc: str,
    dst: str,
    chain = (self: @Self, be :: CBackend, n: usize)
            Res<(), AllocError>
    branch = (self: @Self, be :: CBackend, n: usize)
             Res<(), AllocError>
}

FsSite = {
    id: ExprId,
    c: Call,
    ret: TyId,
    ctx: Ctx,
    path = (self: @Self, be :: CBackend, i: usize, out :: String)
           Res<(), AllocError>
    reject = (self: @Self, be :: CBackend, what: str, out :: String)
             Res<(), AllocError>
    lock = (self: @Self, be :: CBackend, out :: String)
           Res<(), AllocError>
    lock_value = (self: @Self, be :: CBackend, lty: TyId, out :: String)
                 Res<(), AllocError>
    read = (self: @Self, be :: CBackend, aty: TyId, out :: String)
           Res<(), AllocError>
    read_string = (self: @Self, be :: CBackend, sty: TyId, aty: TyId,
                   out :: String) Res<(), AllocError>
    read_run = (self: @Self, be :: CBackend, sty: TyId, vty: TyId,
                aty: TyId, out :: String) Res<(), AllocError>
}

FsRead = {
    id: ExprId,
    ret: TyId,
    sty: TyId,
    vty: TyId,
    aty: TyId,
    al: str,
    path: str,
    want: str,
    got: str,
    rc: str,
    dst: str,
    body = (self: @Self, be :: CBackend) Res<(), AllocError>
    run = (self: @Self, be :: CBackend, slot: Slot, call: str)
          Res<(), AllocError>
    write_ok = (self: @Self, be :: CBackend, buf: str)
               Res<(), AllocError>
    write_vec = (self: @Self, be :: CBackend, buf: str, out :: String)
                Res<(), AllocError>
}
```

#### Functions

```zen
lower_probe* = (be :: CBackend, c: Call, name: str, ctx: Ctx, out :: String)
              Res<(), AllocError>

probe_test = (name: str) str

lower_write* = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    ret : TyId,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

write_fs_call = (be :: CBackend, rc: str, fn: str, first: str, second: str)
                Res<(), AllocError>

lower_lock* = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    ret : TyId,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

write_lock_call = (be :: CBackend, rc: str, path: str, fd: str)
                  Res<(), AllocError>

lower_unlock* = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    a   : Access,
    rty : TyId,
    ret : TyId,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

unlock_line = (be :: CBackend, field: str) Res<(), AllocError>

arrow_field = (be :: CBackend, addr: str, name: str, out :: String)
              Res<(), AllocError>

lower_remove* = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    ret : TyId,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

write_remove_call = (be :: CBackend, rc: str, yes: str, path: str)
                   Res<(), AllocError>

lower_read* = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    ret : TyId,
    aty : TyId,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

hold_alloc = (
    be  :: CBackend,
    c   : Call,
    aty : TyId,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

write_size_call = (be :: CBackend, rc: str, path: str, want: str)
                  Res<(), AllocError>

unsupported_line = (be :: CBackend, id: ExprId, what: str)
                   Res<(), AllocError>

declare_ptr = (be :: CBackend, name: str) Res<(), AllocError>

read_ok_payload = (be :: CBackend, run: str, buf: str)
                  Res<(), AllocError>

open_not_ok = (be :: CBackend, run: str) Res<(), AllocError>

write_read_call = (
    be   :: CBackend,
    rc   : str,
    path : str,
    buf  : str,
    want : str,
    got  : str
) Res<(), AllocError>

write_vec_field = (
    be    :: CBackend,
    vty   : TyId,
    name  : str,
    value : str,
    out   :: String,
    first : bool
) Res<(), AllocError>

write_named_init = (
    be    :: CBackend,
    name  : str,
    value : str,
    out   :: String,
    first : bool
) Res<(), AllocError>

fs_name = (n: usize) str

fs_name_2 = (n: usize) str

fs_name_3 = (n: usize) str

fs_name_4 = (n: usize) str

fs_chain* = (be :: CBackend, ret: TyId, rc: str, dst: str, n: usize)
           Res<(), AllocError>

open_ordinal_test = (be :: CBackend, rc: str, n: usize)
                    Res<(), AllocError>
```

#### Imports and re-exports

```zen
ExprId = std.ast

Call, Access = std.ast

AllocError = std.mem

str, String = std.text

TyId = sema.sema_ty

Ctx = sema.sema_check

sym_member, sym_variant, sym_gen, RES_PATH = gen.gen_name

CBackend = gen.gen_c.gen_c_state

unsupported = gen.gen_c.gen_c_report

ctype, request_type, field_of = gen.gen_c.gen_c_type

declare_temp, init_temp, payload_type = gen.gen_c.gen_c_flow

write_assign_ok, write_assign_ok_unit, write_assign_err = gen.gen_c.gen_c_flow

close_else, close_brace, open_rc_test = gen.gen_c.gen_c_flow

Slot = gen.gen_c.gen_c_fat

slot_call = gen.gen_c.gen_c_bound

address_of = gen.gen_c.gen_c_fat

expr = gen.gen_c.gen_c_expr

arg_text, str_arg = gen.gen_c.gen_c_arg
```

### `src/gen/gen_c/gen_c_handle.zen`

36 declarations (functions: 19, imports and re-exports: 17).

#### Functions

```zen
handle_depth* = (be :: CBackend, base: ExprId) usize

slot_handle = (be :: CBackend, name: str) usize

lower_handle_call* = (
    be    :: CBackend,
    id    : ExprId,
    c     : Call,
    a     : Access,
    depth : usize,
    ctx   : Ctx,
    out   :: String
)
                     Res<(), AllocError>

handle_verb = (
    be   :: CBackend,
    id   : ExprId,
    c    : Call,
    name : str,
    fr   : LoopFrame,
    ctx  : Ctx,
    out  :: String
)
              Res<(), AllocError>

leave_pass = (be :: CBackend, fr: LoopFrame, out :: String)
             Res<(), AllocError>

handle_break = (
    be   :: CBackend,
    id   : ExprId,
    c    : Call,
    name : str,
    fr   : LoopFrame,
    ctx  : Ctx,
    out  :: String
)
               Res<(), AllocError>

write_break = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    fr  : LoopFrame,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

break_keep = (be :: CBackend, c: Call) str

break_fits = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    fr  : LoopFrame,
    ctx : Ctx
) Res<(), AllocError>

break_value_fits = (
    be    :: CBackend,
    value : ExprId,
    fr    : LoopFrame,
    ctx   : Ctx,
    id    : ExprId
) Res<(), AllocError>

break_literal_fits = (be :: CBackend, value: ExprId, payload: TyId)
                     Res<(), AllocError>

break_range_fault = (be :: CBackend, value: ExprId, payload: TyId)
                    Res<(), AllocError>

break_type_fault = (
    be      :: CBackend,
    id      : ExprId,
    got     : TyId,
    payload : TyId
) Res<(), AllocError>

name_of_or = (be :: CBackend, ty: TyId) Res<String, AllocError>

write_break_value = (be :: CBackend, c: Call, fr: LoopFrame, ctx: Ctx)
                    Res<(), AllocError>

assign_ok = (be :: CBackend, value: ExprId, fr: LoopFrame, ctx: Ctx)
            Res<(), AllocError>

write_ok_payload = (
    be      :: CBackend,
    value   : ExprId,
    payload : TyId,
    ctx     : Ctx,
    line    :: String
) Res<(), AllocError>

ok_payload = (be :: CBackend, ty: TyId) Res<TyId, AllocError>

jump_to = (be :: CBackend, stem: str, n: usize, out :: String)
          Res<(), AllocError>
```

#### Imports and re-exports

```zen
ExprId, Access, Call = std.ast

AllocError = std.mem

str, String = std.text

TyId = sema.sema_ty

Ctx = sema.sema_check

literal_overflows = sema.sema_trap

sym_member, sym_variant = gen.gen_name

RES_PATH = gen.gen_name

CBackend = gen.gen_c.gen_c_state

LoopFrame = gen.gen_c.gen_c_frame

GenFault = gen.gen_diag

unsupported = gen.gen_c.gen_c_report

ctype, is_unit = gen.gen_c.gen_c_type

expr = gen.gen_c.gen_c_expr

bare_name = gen.gen_c.gen_c_stmt

write_label = gen.gen_c.gen_c_loop

unwind_to = gen.gen_c.gen_c_own
```

### `src/gen/gen_c/gen_c_hoist.zen`

11 declarations (functions: 3, imports and re-exports: 8).

#### Functions

```zen
needs_hoist* = (be :: CBackend, id: ExprId, ctx: Ctx, want: TyId)
               Res<bool, AllocError>

lifts_into = (be :: CBackend, id: ExprId, ctx: Ctx, want: TyId, r: TyRes)
             Res<bool, AllocError>

hoist_expr* = (
    be   :: CBackend,
    id   : ExprId,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>
```

#### Imports and re-exports

```zen
ExprId = std.ast

AllocError = std.mem

String = std.text

TyId, TyRes = sema.sema_ty

Ctx = sema.sema_check

CBackend = gen.gen_c.gen_c_state

ty_of = gen.gen_c.gen_c_expr

write_res_payload = gen.gen_c.gen_c_call
```

### `src/gen/gen_c/gen_c_impl.zen`

43 declarations (functions: 33, imports and re-exports: 10).

#### Functions

```zen
by_arity* = (be: CBackend, found: Vec<Member>, arity: usize) Res<Member>

kept_or_arity* = (
    be    : CBackend,
    kept  : Vec<Member>,
    found : Vec<Member>,
    arity : usize
) Res<Member>

member_takes = (be: CBackend, m: Member, arity: usize) bool

fn_takes = (be: CBackend, f: Function, arity: usize) bool

without_arity = (found: Vec<Member>) Res<Member>

any_function = (found: Vec<Member>) bool

is_function = (m: Member) bool

impl_member* = (be :: CBackend, decl: DeclId, name: str)
               Res<Res<Function>, AllocError>

impl_member_of* = (be :: CBackend, decl: DeclId, name: str, arity: usize)
                  Res<Res<Function>, AllocError>

member_fn_of = (m: Res<Member>) Res<Function>

bodied_fn* = (found: Vec<Member>) Res<Function>

member_fn = (m: Member) Res<Function>

impl_field* = (be :: CBackend, im: Impl, name: str)
              Res<Res<ExprId>, AllocError>

keep_field_value = (m: Member, name: str, out :: Vec<ExprId>)
                   Res<(), AllocError>

add_field_value = (m: Member, out :: Vec<ExprId>) Res<(), AllocError>

add_written_value = (fl: Field, out :: Vec<ExprId>) Res<(), AllocError>

impl_member_at* = (
    be   :: CBackend,
    decl : DeclId,
    name : str,
    out  :: Vec<Member>
) Res<(), AllocError>

decl_name* = (be :: CBackend, decl: DeclId) str

type_name = (d: Decl) str

generic_enum* = (be :: CBackend, decl: DeclId) bool

generic_enum_decl = (d: Decl) bool

collect_impl_fn = (
    be   :: CBackend,
    decl : DeclId,
    i    : ImplId,
    name : str,
    out  :: Vec<Member>
) Res<(), AllocError>

impl_fn_at = (be :: CBackend, i: ImplId, name: str, out :: Vec<Member>)
             Res<(), AllocError>

keep_impl_fn = (
    be   :: CBackend,
    i    : ImplId,
    im   : Impl,
    name : str,
    out  :: Vec<Member>
) Res<(), AllocError>

keep_bound_default = (
    be   :: CBackend,
    i    : ImplId,
    im   : Impl,
    name : str,
    out  :: Vec<Member>
) Res<(), AllocError>

keep_named_fn = (m: Member, name: str, out :: Vec<Member>)
                Res<(), AllocError>

add_bodied = (m: Member, out :: Vec<Member>) Res<(), AllocError>

add_if_bodied = (m: Member, f: Function, out :: Vec<Member>)
                Res<(), AllocError>

has_body* = (f: Function) bool

alias_of* = (
    be   :: CBackend,
    decl : DeclId,
    name : str
) Res<Res<str>, AllocError>

keep_alias = (
    be   :: CBackend,
    i    : ImplId,
    decl : DeclId,
    name : str,
    out  :: Vec<str>
) Res<(), AllocError>

impl_alias_at = (be :: CBackend, i: ImplId, name: str, out :: Vec<str>)
                Res<(), AllocError>

add_alias = (be :: CBackend, x: ExprId, out :: Vec<str>) Res<(), AllocError>
```

#### Imports and re-exports

```zen
Decl, Struct, Enum, Member, Function, Impl, Field, ExprId = std.ast

AllocError = std.mem

Vec = std.collections

str = std.text

Range = std.core

DeclId, ImplId = sema.sema_id

decl_at = sema.sema_def

tail_is_pack = sema.sema_vararg

CBackend = gen.gen_c.gen_c_state

last_is_variadic = gen.gen_c.gen_c_sink
```

### `src/gen/gen_c/gen_c_index.zen`

36 declarations (functions: 16, imports and re-exports: 20).

#### Functions

```zen
lower_index* = (
    be  :: CBackend,
    id  : ExprId,
    ix  : Index,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

index_not_array = (
    be  :: CBackend,
    id  : ExprId,
    ix  : Index,
    rty : TyId,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

index_type* = (be :: CBackend, ix: Index, ctx: Ctx, want: TyId)
              Res<TyId, AllocError>

not_array_index_type = (be :: CBackend, rty: TyId, want: TyId)
                       Res<TyId, AllocError>

ptr_element = (be :: CBackend, rty: TyId, want: TyId) TyId

member_index_type = (be :: CBackend, rty: TyId, want: TyId)
                    Res<TyId, AllocError>

site_index_type = (be :: CBackend, rty: TyId, s: Site, want: TyId)
                  Res<TyId, AllocError>

index_ret = (be :: CBackend, rty: TyId, s: Site, f: Function)
            Res<TyId, AllocError>

is_raw_ptr = (be :: CBackend, rty: TyId) bool

write_subscript = (be :: CBackend, ix: Index, ctx: Ctx, out :: String)
                  Res<(), AllocError>

index_through_member = (
    be  :: CBackend,
    id  : ExprId,
    ix  : Index,
    rty : TyId,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

index_member = (
    be  :: CBackend,
    id  : ExprId,
    ix  : Index,
    rty : TyId,
    s   : Site,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

supplied_index = (
    be  :: CBackend,
    id  : ExprId,
    ix  : Index,
    rty : TyId,
    s   : Site,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

no_index = (be :: CBackend, id: ExprId, out :: String)
           Res<(), AllocError>

write_index_call = (
    be  :: CBackend,
    id  : ExprId,
    ix  : Index,
    rty : TyId,
    s   : Site,
    f   : Function,
    ctx : Ctx,
    out :: String
)
                   Res<(), AllocError>

emit_index_call = (
    be   :: CBackend,
    ix   : Index,
    rty  : TyId,
    s    : Site,
    f    : Function,
    sig  : Vec<TyId>,
    inst : Inst,
    ctx  : Ctx,
    out  :: String
) Res<(), AllocError>
```

#### Imports and re-exports

```zen
ExprId, Member, Function, Index = std.ast

AllocError = std.mem

Vec = std.collections

String = std.text

TyId = sema.sema_ty

Ctx = sema.sema_check

Inst = sema.sema_inst

self_ctx = sema.sema_member

CBackend = gen.gen_c.gen_c_state

unsupported = gen.gen_c.gen_c_report

sub_with, any_open, recv_inst, inst_open = gen.gen_c.gen_c_mono

enter_struct_tparams, leave_tparams = gen.gen_c.gen_c_mono

is_ptr_named, declared_ret = gen.gen_c.gen_c_type

expr, ty_of = gen.gen_c.gen_c_expr

has_call = gen.gen_c.gen_c_expr

write_arg, write_arg_at = gen.gen_c.gen_c_arg

Site, site_of, member_at = gen.gen_c.gen_c_member

bodied_fn, impl_member = gen.gen_c.gen_c_impl

method_sig, member_symbol = gen.gen_c.gen_c_member

array_of, write_array_index = gen.gen_c.gen_c_array
```

### `src/gen/gen_c/gen_c_infer.zen`

31 declarations (types: 5, functions: 5, imports and re-exports: 21).

#### Types

```zen
InferCall = {
    call: Call,
    recv: Res<ExprId>,
    ctx: Ctx,
    complete = (self: @Self, be :: CBackend, d: Def, f: Function,
                settled: Inst) Res<Inst, AllocError>
    infer = (self: @Self, be :: CBackend, d: Def, f: Function)
            Res<Inst, AllocError>
}

UnifyCall = {
    declared: Vec<TyId>,
    ctx: Ctx,
    receiver = (self: @Self, be :: CBackend, recv: Res<ExprId>, out :: Inst)
               Res<(), AllocError>
    arg = (self: @Self, be :: CBackend, value: ExprId, i: usize,
           out :: Inst) Res<(), AllocError>
    declared_arg = (self: @Self, be :: CBackend, value: ExprId, i: usize,
                    out :: Inst) Res<(), AllocError>
    packed_arg = (self: @Self, be :: CBackend, value: ExprId, i: usize,
                  slot: usize, out :: Inst) Res<(), AllocError>
    swallowed = (self: @Self, be :: CBackend, value: ExprId, slot: usize,
                  out :: Inst) Res<(), AllocError>
    against = (self: @Self, be :: CBackend, value: ExprId, d: TyId,
               out :: Inst) Res<(), AllocError>
}

ReturnCall = {
    id: ExprId,
    call: Call,
    recv: Res<ExprId>,
    ctx: Ctx,
    want: TyId,
    resolve = (self: @Self, be :: CBackend) Res<TyId, AllocError>
    accessed = (self: @Self, be :: CBackend, a: Access)
               Res<TyId, AllocError>
    with_recv = (self: @Self, recv: Res<ExprId>) ReturnCall
    named = (self: @Self, be :: CBackend, name: str)
            Res<TyId, AllocError>
    definition = (self: @Self, be :: CBackend, d: Def)
                 Res<TyId, AllocError>
    function = (self: @Self, be :: CBackend, d: Def, f: Function)
               Res<TyId, AllocError>
}

MemberReturn = {
    site: Site,
    receiver: TyId,
    supplied = (self: @Self, be :: CBackend, name: str)
               Res<Res<TyId>, AllocError>
    settled = (self: @Self, be :: CBackend, f: Function)
              Res<Res<TyId>, AllocError>
    declared = (self: @Self, be :: CBackend, f: Function, inst: Inst)
               Res<TyId, AllocError>
}

ImplAccess = {
    access: Access,
    ctx: Ctx,
    resolve = (self: @Self, be :: CBackend) Res<Res<TyId>, AllocError>
}
```

#### Functions

```zen
complete_inst* = (
    be      :: CBackend,
    c       : Call,
    d       : Def,
    f       : Function,
    settled : Inst,
    recv    : Res<ExprId>,
    ctx     : Ctx
)
                  Res<Inst, AllocError>

decl_ctx = (d: Def) Ctx

written_param = (be :: CBackend, p: Param, dctx: Ctx, out :: Vec<TyId>)
                Res<(), AllocError>

against_pack = (be: CBackend, pack: TyId, actual: TyId) TyId

call_ret_type* = (
    be   :: CBackend,
    id   : ExprId,
    c    : Call,
    ctx  : Ctx,
    want : TyId
) Res<TyId, AllocError>
```

#### Imports and re-exports

```zen
ExprId, Decl, Function, Param = std.ast

Access, Call, Member = std.ast

AllocError = std.mem

Vec = std.collections

str = std.text

TyId = sema.sema_ty

Def, decl_at = sema.sema_def

Ctx = sema.sema_check

Inst = sema.sema_inst

type_from_ast = sema.sema_denote

pack_slot, pack_elem = sema.sema_vararg

CBackend = gen.gen_c.gen_c_state

declared_ret = gen.gen_c.gen_c_type

inst_at, inst_open, settled_inst = gen.gen_c.gen_c_mono

sub_with, unify, arg_type = gen.gen_c.gen_c_mono

enter_tparams, leave_tparams = gen.gen_c.gen_c_mono

fat_ret_type = gen.gen_c.gen_c_bound

impl_member_at, bodied_fn = gen.gen_c.gen_c_impl

site_of, method_sig = gen.gen_c.gen_c_member

Site = gen.gen_c.gen_c_member

recv_inst = gen.gen_c.gen_c_mono
```

### `src/gen/gen_c/gen_c_inline.zen`

71 declarations (functions: 43, constants: 1, imports and re-exports: 27).

#### Functions

```zen
spelled_lambda* = (be: CBackend, id: ExprId) Res<Lambda>

inlines* = (be: CBackend, c: Call, f: Function) bool

takes_lambda* = (be: CBackend, c: Call) bool

is_lambda* = (be: CBackend, id: ExprId) bool

takes_closure* = (be: CBackend, f: Function) bool

param_is_fn = (be: CBackend, p: Param) bool

type_is_fn = (be: CBackend, t: TypeId) bool

closure_slot* = (be :: CBackend, name: str) Res<LocalSlot>

keep_closure = (s: LocalSlot) Res<LocalSlot>

inline_call* = (
    be   :: CBackend,
    id   : ExprId,
    c    : Call,
    d    : Def,
    f    : Function,
    recv : Res<ExprId>,
    ctx  : Ctx,
    out  :: String
)
               Res<(), AllocError>

inline_free = (
    be   :: CBackend,
    id   : ExprId,
    c    : Call,
    d    : Def,
    f    : Function,
    recv : Res<ExprId>,
    ctx  : Ctx,
    out  :: String
)
              Res<(), AllocError>

inline_method* = (
    be   :: CBackend,
    id   : ExprId,
    c    : Call,
    a    : Access,
    rty  : TyId,
    decl : DeclId,
    f    : Function,
    ctx  : Ctx,
    out  :: String
)
                 Res<(), AllocError>

inline_member = (
    be   :: CBackend,
    id   : ExprId,
    c    : Call,
    a    : Access,
    rty  : TyId,
    decl : DeclId,
    f    : Function,
    ctx  : Ctx,
    out  :: String
)
                Res<(), AllocError>

run_called_body = (
    be   :: CBackend,
    id   : ExprId,
    f    : Function,
    argv : Vec<ExprId>,
    ptys : Vec<TyId>,
    ret  : TyId,
    bctx : Ctx,
    inst : Inst,
    ctx  : Ctx,
    out  :: String
) Res<(), AllocError>

run_settled = (
    be   :: CBackend,
    f    : Function,
    argv : Vec<ExprId>,
    ptys : Vec<TyId>,
    ret  : TyId,
    bctx : Ctx,
    inst : Inst,
    ctx  : Ctx,
    out  :: String
) Res<(), AllocError>

run_block = (
    be   :: CBackend,
    f    : Function,
    blk  : BlockId,
    argv : Vec<ExprId>,
    ptys : Vec<TyId>,
    ret  : TyId,
    bctx : Ctx,
    inst : Inst,
    ctx  : Ctx,
    out  :: String
) Res<(), AllocError>

write_result = (be :: CBackend, keeps: bool, result: str, out :: String)
               Res<(), AllocError>

dest_of = (keeps: bool, result: str) Dest

wants_value = (be :: CBackend, ret: TyId) bool

open_temp = (be :: CBackend, ret: TyId, result :: String)
            Res<(), AllocError>

bind_params = (
    be    :: CBackend,
    f     : Function,
    argv  : Vec<ExprId>,
    ptys  : Vec<TyId>,
    home  : usize,
    chome : usize,
    ctx   : Ctx
)
              Res<(), AllocError>

bind_param = (
    be    :: CBackend,
    f     : Function,
    argv  : Vec<ExprId>,
    ptys  : Vec<TyId>,
    i     : usize,
    home  : usize,
    chome : usize,
    ctx   : Ctx
) Res<(), AllocError>

bind_valued = (
    be    :: CBackend,
    p     : Param,
    argv  : Vec<ExprId>,
    ptys  : Vec<TyId>,
    i     : usize,
    home  : usize,
    chome : usize,
    ctx   : Ctx
) Res<(), AllocError>

bind_one = (
    be    :: CBackend,
    p     : Param,
    value : ExprId,
    pty   : TyId,
    home  : usize,
    chome : usize,
    ctx   : Ctx
) Res<(), AllocError>

bind_closure = (
    be    :: CBackend,
    id    : ExprId,
    p     : Param,
    l     : Lambda,
    pty   : TyId,
    home  : usize,
    chome : usize,
    ctx   : Ctx
) Res<(), AllocError>

fn_parts = (be :: CBackend, pty: TyId, ptys :: Vec<TyId>)
           Res<TyId, AllocError>

copy_fn_types = (ft: TyFn, ptys :: Vec<TyId>) Res<TyId, AllocError>

bind_value = (be :: CBackend, p: Param, value: ExprId, pty: TyId, ctx: Ctx)
             Res<(), AllocError>

lower_closure_call* = (
    be   :: CBackend,
    id   : ExprId,
    c    : Call,
    s    : LocalSlot,
    ctx  : Ctx,
    want : TyId,
    out  :: String
)
                      Res<(), AllocError>

run_closure = (
    be   :: CBackend,
    id   : ExprId,
    c    : Call,
    cl   : Closure,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

run_lambda = (
    be   :: CBackend,
    id   : ExprId,
    c    : Call,
    cl   : Closure,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

instantiate_closure = (be :: CBackend, cl: Closure, inst: Inst)
                      Res<Closure, AllocError>

closure_ret = (be :: CBackend, cl: Closure, want: TyId)
              Res<TyId, AllocError>

want_or_unit = (be :: CBackend, want: TyId) Res<TyId, AllocError>

lower_args = (
    be   :: CBackend,
    c    : Call,
    cl   : Closure,
    ctx  : Ctx,
    argt :: Vec<String>,
    hnd  :: Vec<usize>
) Res<(), AllocError>

lower_one_arg = (
    be   :: CBackend,
    c    : Call,
    cl   : Closure,
    i    : usize,
    ctx  : Ctx,
    argt :: Vec<String>,
    hnd  :: Vec<usize>
)
                Res<(), AllocError>

lower_arg_value = (
    be    :: CBackend,
    value : ExprId,
    cl    : Closure,
    i     : usize,
    ctx   : Ctx,
    argt  :: Vec<String>,
    hnd   :: Vec<usize>
)
                  Res<(), AllocError>

bind_lambda_params = (
    be   :: CBackend,
    cl   : Closure,
    argt : Vec<String>,
    hnd  : Vec<usize>
) Res<(), AllocError>

bind_lambda_param = (
    be   :: CBackend,
    cl   : Closure,
    argt : Vec<String>,
    hnd  : Vec<usize>,
    i    : usize
) Res<(), AllocError>

bind_lambda_named = (
    be   :: CBackend,
    cl   : Closure,
    argt : Vec<String>,
    hnd  : Vec<usize>,
    i    : usize,
    p    : Param
)
                    Res<(), AllocError>

bind_passed_handle = (be :: CBackend, p: Param, ty: TyId, depth: usize)
                     Res<(), AllocError>

bind_copied_arg = (
    be   :: CBackend,
    argt : Vec<String>,
    i    : usize,
    p    : Param,
    ty   : TyId
) Res<(), AllocError>

declare_bound = (be :: CBackend, p: Param, ty: TyId, text: str)
                Res<(), AllocError>
```

#### Constants

```zen
INLINE_DEPTH* : usize = 12
```

#### Imports and re-exports

```zen
ExprId, BlockId, Lambda, Param, TypeId, Paren = std.ast

Function, Access, Call = std.ast

AllocError = std.mem

Vec = std.collections

str, String = std.text

Range = std.core

DeclId = sema.sema_id

TyId, TyFn = sema.sema_ty

Def = sema.sema_def

Ctx, Binding = sema.sema_check

Inst, has_var = sema.sema_inst

self_ctx = sema.sema_member

sym_local, sym_gen = gen.gen_name

CBackend = gen.gen_c.gen_c_state

LocalSlot, Closure = gen.gen_c.gen_c_frame

unsupported, unresolved = gen.gen_c.gen_c_report

has_body = gen.gen_c.gen_c_impl

handle_depth = gen.gen_c.gen_c_handle

inst_at, settled_inst, recv_inst, sub, sub_with = gen.gen_c.gen_c_mono

enter_tparams, leave_tparams, enter_struct_tparams = gen.gen_c.gen_c_mono

declarator, is_unit = gen.gen_c.gen_c_type

expr = gen.gen_c.gen_c_expr

Dest, block = gen.gen_c.gen_c_stmt

plain_ctx, body_ctx, self_body_ctx, ref_declarator = gen.gen_c.gen_c_decl

write_address = gen.gen_c.gen_c_arg

arguments, param_types, call_bindings, inline_ret = gen.gen_c.gen_c_settle

compose, settle_params, settled = gen.gen_c.gen_c_settle
```

### `src/gen/gen_c/gen_c_json.zen`

39 declarations (functions: 18, constants: 1, imports and re-exports: 20).

#### Functions

```zen
is_json_door* = (d: Def, f: Function) bool

lower_json_door* = (
    be   :: CBackend,
    id   : ExprId,
    c    : Call,
    d    : Def,
    recv : Res<ExprId>,
    ctx  : Ctx,
    out  :: String
) Res<(), AllocError>

json_receiver = (
    be       :: CBackend,
    id       : ExprId,
    c        : Call,
    door     : Def,
    receiver : ExprId,
    ctx      : Ctx,
    out      :: String
) Res<(), AllocError>

json_result = (
    be       :: CBackend,
    id       : ExprId,
    c        : Call,
    door     : Def,
    value_ty : TyId,
    value    : str,
    ctx      : Ctx,
    out      :: String
) Res<(), AllocError>

json_empty = (
    be   :: CBackend,
    c    : Call,
    door : Def,
    dst  : str,
    ctx  : Ctx
) Res<bool, AllocError>

json_empty_param = (be :: CBackend, empty: Def) Res<TyId, AllocError>

json_empty_def = (be :: CBackend) Res<Res<Def>, AllocError>

json_guard_result = (be :: CBackend, result: str, done: usize)
                    Res<(), AllocError>

json_value = (
    be     :: CBackend,
    id     : ExprId,
    ty     : TyId,
    value  : str,
    buffer : str,
    ret    : TyId,
    result : str,
    done   : usize
) Res<(), AllocError>

json_primitive = (
    be     :: CBackend,
    id     : ExprId,
    name   : str,
    value  : str,
    buffer : str,
    ret    : TyId,
    result : str,
    done   : usize
) Res<(), AllocError>

json_named = (
    be     :: CBackend,
    id     : ExprId,
    ty     : TyId,
    named  : TyNamed,
    value  : str,
    buffer : str,
    ret    : TyId,
    result : str,
    done   : usize
) Res<(), AllocError>

json_record = (
    be     :: CBackend,
    id     : ExprId,
    ty     : TyId,
    named  : TyNamed,
    value  : str,
    buffer : str,
    ret    : TyId,
    result : str,
    done   : usize
) Res<(), AllocError>

json_fields = (
    be     :: CBackend,
    id     : ExprId,
    ty     : TyId,
    named  : TyNamed,
    record : Struct,
    value  : str,
    buffer : str,
    ret    : TyId,
    result : str,
    done   : usize
) Res<(), AllocError>

json_raw = (
    be     :: CBackend,
    raw    : str,
    buffer : str,
    ret    : TyId,
    result : str,
    done   : usize
) Res<(), AllocError>

json_write = (
    be     :: CBackend,
    helper : str,
    buffer : str,
    value  : str,
    ret    : TyId,
    result : str,
    done   : usize
) Res<(), AllocError>

json_helper = (be :: CBackend, name: str) Res<Res<Def>, AllocError>

json_helper_ret = (be :: CBackend, d: Def) Res<TyId, AllocError>

json_unsupported = (
    be     :: CBackend,
    id     : ExprId,
    buffer : str,
    ret    : TyId,
    result : str,
    done   : usize
) Res<(), AllocError>
```

#### Constants

```zen
JSON_MODULE: str = "std.json.json_meta"
```

#### Imports and re-exports

```zen
Decl, Struct, Member, Function, ExprId, Call = std.ast

AllocError = std.mem

Vec = std.collections

str, String = std.text

Range = std.core

TyId, TyNamed = sema.sema_ty

Def, decl_at = sema.sema_def

Ctx = sema.sema_check

Inst = sema.sema_inst

param_type = sema.sema_denote

GenFault = gen.gen_diag

CBackend = gen.gen_c.gen_c_state

expr, ty_of = gen.gen_c.gen_c_expr

declare_temp, write_assign_err = gen.gen_c.gen_c_flow

field_type, request_type = gen.gen_c.gen_c_type

decl_ctx, decl_inst = gen.gen_c.gen_c_type

enter_struct_tparams, leave_tparams = gen.gen_c.gen_c_mono

call_symbol, bodyless, write_done, write_goto = gen.gen_c.gen_c_sink

sym_member = gen.gen_name

unsupported = gen.gen_c.gen_c_report
```

### `src/gen/gen_c/gen_c_layout.zen`

81 declarations (functions: 60, imports and re-exports: 21).

#### Functions

```zen
emit_types* = (be :: CBackend, out :: Emit) Res<(), AllocError>

emit_typedef = (be :: CBackend, out :: Emit, i: usize) Res<(), AllocError>

emit_tags = (be :: CBackend, out :: Emit, seq: Vec<usize>)
            Res<(), AllocError>

emit_tag_block = (be :: CBackend, out :: Emit, seen: Vec<String>)
                 Res<(), AllocError>

collect_tags = (be :: CBackend, i: usize, seen :: Vec<String>)
               Res<(), AllocError>

collect_tags_of = (be :: CBackend, id: TyId, seen :: Vec<String>)
                  Res<(), AllocError>

collect_union_tags = (
    be   :: CBackend,
    id   : TyId,
    u    : TyUnion,
    seen :: Vec<String>
) Res<(), AllocError>

add_union_tag = (
    be    :: CBackend,
    id    : TyId,
    m     : TyId,
    value : usize,
    seen  :: Vec<String>
) Res<(), AllocError>

collect_res_tags = (be :: CBackend, r: TyRes, seen :: Vec<String>)
                   Res<(), AllocError>

collect_enum_tags = (
    be   :: CBackend,
    id   : TyId,
    n    : TyNamed,
    seen :: Vec<String>
) Res<(), AllocError>

collect_decl_tags = (
    be   :: CBackend,
    id   : TyId,
    n    : TyNamed,
    d    : Decl,
    seen :: Vec<String>
) Res<(), AllocError>

write_enum_tags = (
    be    :: CBackend,
    id    : TyId,
    n     : TyNamed,
    e     : Enum,
    qname : str,
    seen  :: Vec<String>
) Res<(), AllocError>

variant_ranks = (
    be       :: CBackend,
    id       : TyId,
    n        : TyNamed,
    variants : Vec<Variant>,
    ranks    :: Vec<usize>
)
                Res<(), AllocError>

canonical_members = (be :: CBackend, id: TyId) Res<Vec<TyId>>

collect_ranks = (
    be       :: CBackend,
    n        : TyNamed,
    variants : Vec<Variant>,
    members  : Vec<TyId>,
    ranks    :: Vec<usize>
)
                Res<(), AllocError>

variant_rank = (
    be      :: CBackend,
    n       : TyNamed,
    v       : Variant,
    members : Vec<TyId>,
    ctx     : Ctx,
    inst    : Inst
) Res<usize>

rank_within = (members: Vec<TyId>, t: TyId) Res<usize>

write_ranked_tags = (
    be       :: CBackend,
    variants : Vec<Variant>,
    ranks    : Vec<usize>,
    qname    : str,
    seen     :: Vec<String>
)
                    Res<(), AllocError>

write_variant_tags = (
    be       :: CBackend,
    variants : Vec<Variant>,
    qname    : str,
    seen     :: Vec<String>
) Res<(), AllocError>

add_tag = (
    be      :: CBackend,
    seen    :: Vec<String>,
    qname   : str,
    variant : str,
    value   : usize
) Res<(), AllocError>

has_line = (seen: Vec<String>, text: str) bool

write_qname* = (be :: CBackend, out :: String, n: TyNamed)
               Res<(), AllocError>

write_dotted = (out :: String, name: str) Res<(), AllocError>

define_type = (be :: CBackend, out :: Emit, i: usize) Res<(), AllocError>

define_fresh = (be :: CBackend, out :: Emit, i: usize) Res<(), AllocError>

define_deps = (be :: CBackend, out :: Emit, i: usize) Res<(), AllocError>

define_dep = (be :: CBackend, out :: Emit, id: TyId) Res<(), AllocError>

by_value_deps = (be :: CBackend, id: TyId, deps :: Vec<TyId>)
                Res<(), AllocError>

union_deps = (be :: CBackend, members: Vec<TyId>, deps :: Vec<TyId>)
             Res<(), AllocError>

res_deps = (be :: CBackend, r: TyRes, deps :: Vec<TyId>)
           Res<(), AllocError>

keep_composite = (be :: CBackend, id: TyId, deps :: Vec<TyId>)
                 Res<(), AllocError>

decl_deps = (be :: CBackend, n: TyNamed, deps :: Vec<TyId>)
            Res<(), AllocError>

decl_kind_deps = (be :: CBackend, n: TyNamed, d: Decl, deps :: Vec<TyId>)
                 Res<(), AllocError>

field_deps = (
    be      :: CBackend,
    members : Vec<Member>,
    ctx     : Ctx,
    inst    : Inst,
    deps    :: Vec<TyId>
) Res<(), AllocError>

variant_deps = (
    be       :: CBackend,
    n        : TyNamed,
    variants : Vec<Variant>,
    ctx      : Ctx,
    inst     : Inst,
    deps     :: Vec<TyId>
) Res<(), AllocError>

write_definition = (be :: CBackend, out :: Emit, name: str, id: TyId)
                   Res<(), AllocError>

write_union_def = (be :: CBackend, out :: Emit, name: str, u: TyUnion)
                  Res<(), AllocError>

add_union_payload = (
    be       :: CBackend,
    payloads :: Vec<TyId>,
    names    :: Vec<String>,
    m        : TyId
) Res<(), AllocError>

push_union_payload = (
    be       :: CBackend,
    payloads :: Vec<TyId>,
    names    :: Vec<String>,
    m        : TyId
) Res<(), AllocError>

write_res_def = (be :: CBackend, out :: Emit, name: str, r: TyRes)
                Res<(), AllocError>

add_payload = (
    be       :: CBackend,
    payloads :: Vec<TyId>,
    names    :: Vec<String>,
    id       : TyId,
    variant  : str
) Res<(), AllocError>

push_payload = (
    be       :: CBackend,
    payloads :: Vec<TyId>,
    names    :: Vec<String>,
    id       : TyId,
    variant  : str
) Res<(), AllocError>

write_named_def = (
    be   :: CBackend,
    out  :: Emit,
    name : str,
    n    : TyNamed,
    id   : TyId
) Res<(), AllocError>

write_decl_def = (
    be   :: CBackend,
    out  :: Emit,
    name : str,
    n    : TyNamed,
    d    : Decl,
    id   : TyId
) Res<(), AllocError>

write_struct_or_fat = (
    be   :: CBackend,
    out  :: Emit,
    name : str,
    s    : Struct,
    ctx  : Ctx,
    inst : Inst,
    id   : TyId
)
                      Res<(), AllocError>

write_fat_def = (be :: CBackend, out :: Emit, name: str, id: TyId)
                Res<(), AllocError>

write_slot_line = (be :: CBackend, out :: Emit, s: Slot)
                  Res<(), AllocError>

write_struct_def = (
    be   :: CBackend,
    out  :: Emit,
    name : str,
    s    : Struct,
    ctx  : Ctx,
    inst : Inst
) Res<(), AllocError>

storage_types = (
    be   :: CBackend,
    s    : Struct,
    ctx  : Ctx,
    inst : Inst,
    out  :: Vec<TyId>
) Res<(), AllocError>

refuse_dropped_field = (be :: CBackend, m: Member) Res<(), AllocError>

write_fields_def = (
    be     :: CBackend,
    out    :: Emit,
    name   : str,
    s      : Struct,
    ctx    : Ctx,
    inst   : Inst,
    fields : Vec<TyId>
)
                   Res<(), AllocError>

write_field = (be :: CBackend, out :: Emit, m: Member, t: TyId)
              Res<(), AllocError>

write_enum_def = (
    be   :: CBackend,
    out  :: Emit,
    name : str,
    n    : TyNamed,
    e    : Enum,
    ctx  : Ctx,
    inst : Inst
) Res<(), AllocError>

open_struct = (out :: Emit, name: str) Res<(), AllocError>

close_struct = (out :: Emit) Res<(), AllocError>

write_opaque = (out :: Emit, name: str) Res<(), AllocError>

write_union = (
    be       :: CBackend,
    out      :: Emit,
    payloads : Vec<TyId>,
    names    : Vec<String>
) Res<(), AllocError>

write_union_body = (
    be       :: CBackend,
    out      :: Emit,
    payloads : Vec<TyId>,
    names    : Vec<String>
) Res<(), AllocError>

write_union_member = (
    be    :: CBackend,
    out   :: Emit,
    names : Vec<String>,
    i     : usize,
    t     : TyId
) Res<(), AllocError>

write_member_line = (be :: CBackend, out :: Emit, name: str, t: TyId)
                    Res<(), AllocError>
```

#### Imports and re-exports

```zen
Decl, Struct, Enum, Variant, Member = std.ast

AllocError = std.mem

Vec = std.collections

str, String = std.text

Range = std.core

TyId, TyNamed, TyRes, TyUnion, is_failure = sema.sema_ty

decl_at = sema.sema_def

Ctx = sema.sema_check

Emit, order = gen.gen_emit

sym_type, sym_variant, sym_member = gen.gen_name

RES_PATH = gen.gen_name

sym_union_variant, sym_union_member = gen.gen_name

CBackend = gen.gen_c.gen_c_state

GenFault = gen.gen_diag

declarator, is_unit, has_storage = gen.gen_c.gen_c_type

field_type, variant_type, decl_ctx, close_types = gen.gen_c.gen_c_type

decl_inst = gen.gen_c.gen_c_type

Inst = sema.sema_inst

any_open, enter_struct_tparams, leave_tparams = gen.gen_c.gen_c_mono

Slot, is_fat, slots_of, slot_field = gen.gen_c.gen_c_fat

write_array_def = gen.gen_c.gen_c_array
```

### `src/gen/gen_c/gen_c_loop.zen`

66 declarations (functions: 40, imports and re-exports: 26).

#### Functions

```zen
lower_loop* = (
    be   :: CBackend,
    id   : ExprId,
    c    : Call,
    f    : Function,
    recv : Res<ExprId>,
    ctx  : Ctx,
    want : TyId,
    out  :: String
)
              Res<(), AllocError>

lower_with_body = (
    be   :: CBackend,
    id   : ExprId,
    f    : Function,
    args : Vec<ExprId>,
    body : ExprId,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

lambda_at* = (be :: CBackend, id: ExprId) Res<Lambda>

lower_shaped = (
    be   :: CBackend,
    id   : ExprId,
    f    : Function,
    args : Vec<ExprId>,
    lam  : Lambda,
    ctx  : Ctx,
    want : TyId,
    out  :: String
)
               Res<(), AllocError>

lower_walk* = (
    be   :: CBackend,
    id   : ExprId,
    sh   : Shape,
    args : Vec<ExprId>,
    lam  : Lambda,
    ctx  : Ctx,
    want : TyId,
    fold : Fold,
    out  :: String
)
             Res<(), AllocError>

first_lead = (be :: CBackend, args: Vec<ExprId>) Res<ExprId>

lower_led = (
    be   :: CBackend,
    id   : ExprId,
    sh   : Shape,
    one  : ExprId,
    lam  : Lambda,
    ctx  : Ctx,
    want : TyId,
    fold : Fold,
    out  :: String
)
            Res<(), AllocError>

lower_impl_walk = (
    be   :: CBackend,
    id   : ExprId,
    sh   : Shape,
    one  : ExprId,
    rty  : TyId,
    lam  : Lambda,
    ctx  : Ctx,
    want : TyId,
    fold : Fold,
    out  :: String
) Res<(), AllocError>

is_cond = (be :: CBackend, one: ExprId, ctx: Ctx)
          Res<bool, AllocError>

lower_forever = (
    be   :: CBackend,
    id   : ExprId,
    sh   : Shape,
    cond : Res<ExprId>,
    lam  : Lambda,
    ctx  : Ctx,
    want : TyId,
    fold : Fold,
    out  :: String
) Res<(), AllocError>

write_cond_guard = (be :: CBackend, one: ExprId, brk: usize, ctx: Ctx)
                   Res<(), AllocError>

write_cond_value = (be :: CBackend, one: ExprId, brk: usize, ctx: Ctx)
                   Res<(), AllocError>

write_cond_body = (be :: CBackend, lam: Lambda, brk: usize, ctx: Ctx)
                  Res<(), AllocError>

lower_range = (
    be   :: CBackend,
    id   : ExprId,
    sh   : Shape,
    one  : ExprId,
    lam  : Lambda,
    ctx  : Ctx,
    want : TyId,
    fold : Fold,
    out  :: String
) Res<(), AllocError>

lower_range_impl = (
    be   :: CBackend,
    id   : ExprId,
    sh   : Shape,
    one  : ExprId,
    rty  : TyId,
    lam  : Lambda,
    ctx  : Ctx,
    want : TyId,
    fold : Fold,
    out  :: String
) Res<(), AllocError>

lower_settled = (
    be   :: CBackend,
    id   : ExprId,
    sh   : Shape,
    one  : ExprId,
    rty  : TyId,
    lam  : Lambda,
    ctx  : Ctx,
    want : TyId,
    fold : Fold,
    out  :: String
) Res<(), AllocError>

settle_res* = (be :: CBackend, want: TyId, elem: TyId)
             Res<TyId, AllocError>

lower_bounded = (
    be   :: CBackend,
    id   : ExprId,
    sh   : Shape,
    one  : ExprId,
    rty  : TyId,
    lam  : Lambda,
    ctx  : Ctx,
    want : TyId,
    fold : Fold,
    out  :: String
) Res<(), AllocError>

walk_temp* = (be :: CBackend, one: ExprId, rty: TyId, ctx: Ctx)
             Res<String, AllocError>

declare_usize* = (be :: CBackend, name: str) Res<(), AllocError>

assign_member = (be :: CBackend, target: str, base: str, member: str)
                Res<(), AllocError>

open_result* = (be :: CBackend, want: TyId, out :: String)
              Res<LoopFrame, AllocError>

wants_result = (be :: CBackend, want: TyId) bool

open_result_temp = (be :: CBackend, want: TyId, result :: String)
                   Res<(), AllocError>

run_body* = (
    be      :: CBackend,
    sh      : Shape,
    lam     : Lambda,
    counter : str,
    base    : str,
    value   : str,
    ety     : TyId,
    fold    : Fold,
    ctx     : Ctx
)
           Res<(), AllocError>

discard_body = (be :: CBackend, lam: Lambda, ctx: Ctx)
               Res<(), AllocError>

bind_handle = (be :: CBackend, lam: Lambda) Res<(), AllocError>

handle_name = (lam: Lambda) str

bind_threaded = (
    be      :: CBackend,
    sh      : Shape,
    lam     : Lambda,
    counter : str,
    base    : str,
    value   : str,
    ety     : TyId
) Res<(), AllocError>

bind_named = (
    be      :: CBackend,
    sh      : Shape,
    lam     : Lambda,
    counter : str,
    base    : str,
    value   : str,
    ety     : TyId
) Res<(), AllocError>

bind_pair = (
    be      :: CBackend,
    lam     : Lambda,
    counter : str,
    base    : str,
    value   : str,
    ety     : TyId
) Res<(), AllocError>

bind_single = (
    be      :: CBackend,
    sh      : Shape,
    lam     : Lambda,
    counter : str,
    base    : str,
    value   : str,
    ety     : TyId
) Res<(), AllocError>

bind_index = (
    be      :: CBackend,
    lam     : Lambda,
    i       : usize,
    counter : str,
    base    : str
) Res<(), AllocError>

bind_offset = (be :: CBackend, p: Param, counter: str, base: str)
              Res<(), AllocError>

bind_element* = (
    be    :: CBackend,
    lam   : Lambda,
    i     : usize,
    value : str,
    ety   : TyId
) Res<(), AllocError>

write_offset = (counter: str, base: str, out :: String)
               Res<(), AllocError>

open_counter = (be :: CBackend, counter :: String) Res<(), AllocError>

close_pass* = (be :: CBackend, st: LoopFrame, counter: str, fold: Fold)
             Res<(), AllocError>

step_counter = (be :: CBackend, counter: str) Res<(), AllocError>

write_label* = (be :: CBackend, stem: str, n: usize) Res<(), AllocError>
```

#### Imports and re-exports

```zen
ExprId, Lambda = std.ast

Function, Param = std.ast

Call = std.ast

AllocError = std.mem

Vec = std.collections

str, String = std.text

TyId = sema.sema_ty

Ctx = sema.sema_check

sym_member, sym_gen, sym_variant = gen.gen_name

RES_PATH = gen.gen_name

CBackend = gen.gen_c.gen_c_state

LoopFrame = gen.gen_c.gen_c_frame

Shape, shape_of = gen.gen_c.gen_c_shape

Fold, no_fold, lower_fold, bind_acc = gen.gen_c.gen_c_fold

write_fold_result = gen.gen_c.gen_c_fold

unsupported = gen.gen_c.gen_c_report

ctype, declarator = gen.gen_c.gen_c_type

intern_res_open = gen.gen_c.gen_c_mono

has_var = sema.sema_inst

expr, ty_of = gen.gen_c.gen_c_expr

Dest, block = gen.gen_c.gen_c_stmt

supplies_bounds = gen.gen_c.gen_c_range

bind_text = gen.gen_c.gen_c_range

is_res = gen.gen_c.gen_c_type

lower_supplied = gen.gen_c.gen_c_range

array_of, lower_array_walk = gen.gen_c.gen_c_array
```

### `src/gen/gen_c/gen_c_main.zen`

42 declarations (functions: 27, imports and re-exports: 15).

#### Functions

```zen
emit_main* = (be :: CBackend, mi: usize, out :: Emit) Res<(), AllocError>

write_main = (be :: CBackend, d: Def, out :: Emit) Res<(), AllocError>

write_entry = (be :: CBackend, d: Def, f: Function, out :: Emit)
              Res<(), AllocError>

main_head = (wants_argv: bool) str

signature = (be :: CBackend, f: Function, mi: usize, sig :: Vec<TyId>)
            Res<(), AllocError>

add_sig = (be :: CBackend, t: TypeId, ctx: Ctx, sig :: Vec<TyId>)
          Res<(), AllocError>

write_entry_args = (be :: CBackend, sig: Vec<TyId>, out :: String)
                   Res<(), AllocError>

write_entry_arg = (be :: CBackend, t: TyId, out :: String)
                  Res<(), AllocError>

write_env_value = (be :: CBackend, t: TyId, out :: String)
                  Res<(), AllocError>

argv_field = (be :: CBackend, t: TyId) Res<Res<TyId>, AllocError>

argv_rows = (be :: CBackend, sig: Vec<TyId>, out :: Vec<TyId>)
            Res<(), AllocError>

emit_argv_vec = (be :: CBackend, v: TyId, out :: Emit)
                Res<(), AllocError>

write_argv_local = (be :: CBackend, v: TyId, out :: Emit)
                   Res<(), AllocError>

write_empty_rows = (be :: CBackend, v: TyId, out :: Emit)
                   Res<(), AllocError>

write_rows_guard = (be :: CBackend, v: TyId, out :: Emit)
                   Res<(), AllocError>

write_filled_rows = (be :: CBackend, v: TyId, out :: Emit)
                    Res<(), AllocError>

write_vec_literal = (
    be   :: CBackend,
    v    : TyId,
    data : str,
    n    : str,
    out  :: String
) Res<(), AllocError>

write_zero = (be :: CBackend, t: TyId, out :: String) Res<(), AllocError>

write_zero_struct = (be :: CBackend, t: TyId, out :: String)
                    Res<(), AllocError>

write_exit = (
    be       :: CBackend,
    ret      : TyId,
    call     : str,
    has_argv : bool,
    out      :: Emit
) Res<(), AllocError>

write_res_exit = (
    be       :: CBackend,
    r        : TyRes,
    ret      : TyId,
    call     : str,
    has_argv : bool,
    out      :: Emit
) Res<(), AllocError>

write_ok_value = (be :: CBackend, r: TyRes, out :: String)
                 Res<(), AllocError>

write_ok_payload = (out :: String) Res<(), AllocError>

write_plain_exit = (
    be       :: CBackend,
    ret      : TyId,
    call     : str,
    has_argv : bool,
    out      :: Emit
) Res<(), AllocError>

write_int_exit = (be :: CBackend, call: str, has_argv: bool, out :: Emit)
                 Res<(), AllocError>

write_void_exit = (
    be       :: CBackend,
    ret      : TyId,
    call     : str,
    has_argv : bool,
    out      :: Emit
) Res<(), AllocError>

write_argv_drop = (be :: CBackend, has_argv: bool, out :: Emit)
                  Res<(), AllocError>
```

#### Imports and re-exports

```zen
Function, TypeId = std.ast

AllocError = std.mem

Vec = std.collections

str, String = std.text

TyId, TyRes = sema.sema_ty

Def, decl_at = sema.sema_def

Ctx = sema.sema_check

Inst = sema.sema_inst

Emit = gen.gen_emit

sym_fn, sym_member, sym_variant, RES_PATH = gen.gen_name

CBackend = gen.gen_c.gen_c_state

emit_actor_globals, write_actor_shutdown = gen.gen_c.gen_c_actor

ctype, is_c_integer = gen.gen_c.gen_c_type

field_of = gen.gen_c.gen_c_type

plain_ctx, return_type = gen.gen_c.gen_c_decl
```

### `src/gen/gen_c/gen_c_member.zen`

102 declarations (types: 2, enums: 1, functions: 52, imports and re-exports: 47).

#### Types

```zen
Dot = {
    id: ExprId,
    c: Call,
    a: Access,
}

Site* = {
    ty*: TyId,
    decl*: DeclId,
    qname*: str,
    generic*: bool,
}
```

#### Enums

```zen
MethodKind = Inlined
    | PtrMember(TyId)
    | Cap(CapabilityKind)
    | AllocCreate
    | FloorDoor
    | FatSlot
    | Ordinary
```

#### Functions

```zen
lower_dot_call* = (
    be   :: CBackend,
    id   : ExprId,
    c    : Call,
    a    : Access,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

lower_marked_dot = (
    be   :: CBackend,
    id   : ExprId,
    c    : Call,
    a    : Access,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

lower_resolved_dot = (
    be   :: CBackend,
    d    : Dot,
    ctx  : Ctx,
    want : TyId,
    out  :: String
)
                     Res<(), AllocError>

lower_static_call = (
    be   :: CBackend,
    d    : Dot,
    ty   : TyId,
    ctx  : Ctx,
    want : TyId,
    out  :: String
)
                    Res<(), AllocError>

case_ty = (be :: CBackend, d: Dot, base: TyId, ctx: Ctx)
          Res<TyId, AllocError>

write_variant_call = (be :: CBackend, d: Dot, ty: TyId, ctx: Ctx, out :: String)
                     Res<(), AllocError>

write_case_value = (
    be  :: CBackend,
    c   : Call,
    ty  : TyId,
    cs  : Case,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

no_payload = (be :: CBackend, c: Call, cs: Case) bool

write_payload_arg = (be :: CBackend, c: Call, cs: Case, ctx: Ctx, out :: String)
                    Res<(), AllocError>

lower_receiver_call = (
    be   :: CBackend,
    d    : Dot,
    ctx  : Ctx,
    want : TyId,
    out  :: String
)
                      Res<(), AllocError>

lower_receiver_site = (
    be   :: CBackend,
    d    : Dot,
    rty  : TyId,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

with_site = (
    be   :: CBackend,
    d    : Dot,
    s    : Site,
    ctx  : Ctx,
    want : TyId,
    out  :: String
)
            Res<(), AllocError>

supplied_or_ufcs = (
    be   :: CBackend,
    d    : Dot,
    s    : Site,
    ctx  : Ctx,
    want : TyId,
    out  :: String
)
                   Res<(), AllocError>

supplied_or_refused = (
    be   :: CBackend,
    d    : Dot,
    s    : Site,
    m    : Member,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

declared_member = (
    be   :: CBackend,
    d    : Dot,
    s    : Site,
    m    : Member,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

supplied_member = (
    be   :: CBackend,
    d    : Dot,
    s    : Site,
    m    : Member,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

pick_member = (be :: CBackend, c: Call, s: Site, found: Vec<Member>, ctx: Ctx)
              Res<Res<Member>, AllocError>

member_that_fits = (
    be    :: CBackend,
    c     : Call,
    s     : Site,
    found : Vec<Member>,
    ctx   : Ctx
)
                   Res<Res<Member>, AllocError>

keep_fits = (
    be      :: CBackend,
    m       : Member,
    s       : Site,
    actuals : Vec<Actual>,
    kept    :: Vec<Member>
) Res<(), AllocError>

keep_if_fits = (
    be      :: CBackend,
    m       : Member,
    f       : Function,
    s       : Site,
    actuals : Vec<Actual>,
    kept    :: Vec<Member>
) Res<(), AllocError>

call_actuals = (be :: CBackend, c: Call, ctx: Ctx, out :: Vec<Actual>)
               Res<(), AllocError>

arg_actual = (be :: CBackend, x: Arg, ctx: Ctx) Res<Actual, AllocError>

site_of* = (be :: CBackend, rty: TyId) Res<Res<Site>, AllocError>

named_site = (
    be  :: CBackend,
    rty : TyId,
    n   : TyNamed
) Res<Res<Site>, AllocError>

prim_site = (be :: CBackend, rty: TyId, name: str) Res<Res<Site>, AllocError>

type_qname = (be :: CBackend, ty: TyId, out :: String) Res<(), AllocError>

member_at* = (be :: CBackend, s: Site, name: str, out :: Vec<Member>)
             Res<(), AllocError>

struct_member = (d: Decl, name: str, out :: Vec<Member>) Res<(), AllocError>

keep_named = (st: Struct, name: str, out :: Vec<Member>) Res<(), AllocError>

method_kind = (be :: CBackend, d: Dot, s: Site, f: Function, ctx: Ctx)
              Res<MethodKind, AllocError>

is_fat_slot = (be: CBackend, rty: TyId, f: Function) bool

lower_method = (
    be   :: CBackend,
    d    : Dot,
    s    : Site,
    f    : Function,
    ctx  : Ctx,
    want : TyId,
    out  :: String
)
               Res<(), AllocError>

lower_ordinary_method = (
    be  :: CBackend,
    d   : Dot,
    s   : Site,
    f   : Function,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

write_method_call = (
    be  :: CBackend,
    d   : Dot,
    s   : Site,
    f   : Function,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

method_call_sig = (
    be   :: CBackend,
    s    : Site,
    f    : Function,
    inst : Inst,
    sig  :: Vec<TyId>
) Res<(), AllocError>

method_inst = (be :: CBackend, d: Dot, s: Site, f: Function, ctx: Ctx)
              Res<Inst, AllocError>

emit_method_call = (
    be   :: CBackend,
    d    : Dot,
    s    : Site,
    f    : Function,
    sig  : Vec<TyId>,
    inst : Inst,
    ctx  : Ctx,
    out  :: String
) Res<(), AllocError>

member_symbol* = (
    be   :: CBackend,
    ty   : TyId,
    s    : Site,
    name : str,
    sig  : Vec<TyId>,
    inst : Inst
) Res<String, AllocError>

method_sig* = (
    be   :: CBackend,
    rty  : TyId,
    decl : DeclId,
    f    : Function,
    mi   : usize,
    inst : Inst,
    sig  :: Vec<TyId>
) Res<(), AllocError>

generic_method_sig* = (
    be    :: CBackend,
    rty   : TyId,
    decl  : DeclId,
    f     : Function,
    mi    : usize,
    owner : str,
    inst  : Inst,
    sig   :: Vec<TyId>
) Res<(), AllocError>

add_method_param = (
    be   :: CBackend,
    p    : Param,
    sctx : Ctx,
    inst : Inst,
    sig  :: Vec<TyId>
) Res<(), AllocError>

lower_eq_call* = (
    be  :: CBackend,
    lhs : ExprId,
    rhs : ExprId,
    rty : TyId,
    ctx : Ctx,
    out :: String
) Res<bool, AllocError>

eq_fn = (be :: CBackend, s: Site) Res<Res<Function>, AllocError>

write_eq = (
    be  :: CBackend,
    lhs : ExprId,
    rhs : ExprId,
    s   : Site,
    f   : Function,
    ctx : Ctx,
    out :: String
) Res<bool, AllocError>

emit_eq = (
    be   :: CBackend,
    lhs  : ExprId,
    rhs  : ExprId,
    s    : Site,
    f    : Function,
    sig  : Vec<TyId>,
    inst : Inst,
    ctx  : Ctx,
    out  :: String
) Res<bool, AllocError>

lower_ufcs = (
    be   :: CBackend,
    d    : Dot,
    rty  : TyId,
    ctx  : Ctx,
    want : TyId,
    out  :: String
)
             Res<(), AllocError>

ufcs_or_impl = (
    be   :: CBackend,
    d    : Dot,
    rty  : TyId,
    ctx  : Ctx,
    want : TyId,
    out  :: String
)
               Res<(), AllocError>

impl_alias = (
    be   :: CBackend,
    d    : Dot,
    rty  : TyId,
    ctx  : Ctx,
    want : TyId,
    out  :: String
)
             Res<(), AllocError>

reaches = (be :: CBackend, rty: TyId, name: str, arity: usize)
          Res<bool, AllocError>

any_at_arity = (be: CBackend, found: Vec<Found>, arity: usize) bool

fn_takes_args = (be: CBackend, ty: TyId, arity: usize) bool

variadic_takes = (be: CBackend, f: TyFn, arity: usize) bool
```

#### Imports and re-exports

```zen
ExprId, Decl, Struct, Member = std.ast

Function, Param, Access, Call, Arg = std.ast

Lambda = std.ast

AllocError = std.mem

Vec = std.collections

str, String = std.text

Range = std.core

DeclId = sema.sema_id

TyId, TyNamed, TyFn, Prim = sema.sema_ty

Def, decl_at = sema.sema_def

Ctx = sema.sema_check

Inst = sema.sema_inst

Found, base_of, members_of, self_ctx = sema.sema_member

Actual = sema.sema_call

recv_sig_fits, ty_at, tail_swallows = sema.sema_cand

Case, cases_of, find_case = sema.sema_case

is_case = sema.sema_match

sym_fn, sym_member, sym_variant, qualify = gen.gen_name

CBackend, MethodRef = gen.gen_c.gen_c_state

unsupported, unresolved = gen.gen_c.gen_c_report

sub, sub_with, any_open, recv_inst, inst_open = gen.gen_c.gen_c_mono

intern_var, unify, arg_type = gen.gen_c.gen_c_mono

owner_of = sema.sema_inst

enter_tparams, enter_struct_tparams, leave_tparams = gen.gen_c.gen_c_mono

ctype, is_unit = gen.gen_c.gen_c_type

expr, ty_of, want_of = gen.gen_c.gen_c_expr

has_call, holds = gen.gen_c.gen_c_expr

unsettled = gen.gen_c.gen_c_mono

lower_plain_call, write_call_args = gen.gen_c.gen_c_call

write_arg, write_arg_at = gen.gen_c.gen_c_arg

handle_depth, lower_handle_call = gen.gen_c.gen_c_handle

inlines, inline_method = gen.gen_c.gen_c_inline

is_ptr_member, lower_ptr_member = gen.gen_c.gen_c_ptr

lower_create, alloc_raw = gen.gen_c.gen_c_alloc

CapabilityKind, capability_kind, lower_capability = gen.gen_c.gen_c_cap

is_fat = gen.gen_c.gen_c_fat

lower_fat_call = gen.gen_c.gen_c_bound

lower_assoc_call = gen.gen_c.gen_c_assoc

lower_meta_walk, lower_meta_proj = gen.gen_c.gen_c_meta

sink_door_shape = gen.gen_c.gen_c_sink

is_floor_door, lower_floor_door = gen.gen_c.gen_c_floor

by_arity, bodied_fn, impl_member, kept_or_arity = gen.gen_c.gen_c_impl

has_body = gen.gen_c.gen_c_impl

impl_member_at = gen.gen_c.gen_c_impl

alias_of = gen.gen_c.gen_c_impl

generic_enum = gen.gen_c.gen_c_impl

ref_of_actor, lower_actor_send = gen.gen_c.gen_c_actor
```

### `src/gen/gen_c/gen_c_meta.zen`

18 declarations (functions: 5, imports and re-exports: 13).

#### Functions

```zen
lower_meta_walk* = (
    be    :: CBackend,
    id    : ExprId,
    c     : Call,
    names : Vec<str>,
    ctx   : Ctx,
    out   :: String
) Res<(), AllocError>

walk_unrolled = (
    be    :: CBackend,
    lam   : Lambda,
    names : Vec<str>,
    ctx   : Ctx
) Res<(), AllocError>

walk_pass = (
    be    :: CBackend,
    brk   : usize,
    lam   : Lambda,
    fname : str,
    unit  : TyId,
    ctx   : Ctx
) Res<(), AllocError>

bind_walk_params = (be :: CBackend, lam: Lambda) Res<(), AllocError>

lower_meta_proj* = (
    be   :: CBackend,
    id   : ExprId,
    a    : Access,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>
```

#### Imports and re-exports

```zen
ExprId, Access, Call, Ident, Lambda = std.ast

AllocError = std.mem

Vec = std.collections

str, String = std.text

TyId = sema.sema_ty

Ctx = sema.sema_check

CBackend = gen.gen_c.gen_c_state

LoopFrame = gen.gen_c.gen_c_frame

unsupported = gen.gen_c.gen_c_report

block, Dest = gen.gen_c.gen_c_stmt

lower_access = gen.gen_c.gen_c_read

write_label = gen.gen_c.gen_c_loop

spelled_lambda = gen.gen_c.gen_c_inline
```

### `src/gen/gen_c/gen_c_mono.zen`

53 declarations (functions: 40, imports and re-exports: 13).

#### Functions

```zen
intern_named* = (c :: Checker, d: Def, args: Vec<TyId>)
                Res<TyId, AllocError>

intern_var* = (c :: Checker, name: str, owner: str) Res<TyId, AllocError>

intern_res_open* = (c :: Checker, value: TyId) Res<TyId, AllocError>

constructed* = (be :: CBackend, d: Def) Res<TyId, AllocError>

decl_vars = (c :: Checker, d: Def, out :: Vec<TyId>) Res<(), AllocError>

decl_vars_of = (c :: Checker, d: Def, x: Decl, out :: Vec<TyId>)
               Res<(), AllocError>

decl_tparams_of = (c :: Checker, d: Def, x: Decl, out :: Vec<TyId>)
                  Res<(), AllocError>

open_named* = (be :: CBackend, decl: DeclId) Res<Res<TyId>, AllocError>

open_named_decl = (be :: CBackend, decl: DeclId, x: Decl)
                  Res<Res<TyId>, AllocError>

open_enum_named = (be :: CBackend, decl: DeclId, e: Enum)
                  Res<Res<TyId>, AllocError>

open_struct_named = (be :: CBackend, decl: DeclId, s: Struct)
                    Res<Res<TyId>, AllocError>

named_at = (
    c     :: Checker,
    decl  : DeclId,
    qname : str,
    name  : str,
    args  : Vec<TyId>
) Res<TyId, AllocError>

inst_at* = (be :: CBackend, id: ExprId) Res<Inst, AllocError>

recv_inst* = (be :: CBackend, rty: TyId) Res<Inst, AllocError>

sub* = (be :: CBackend, ty: TyId) Res<TyId, AllocError>

sub_with* = (be :: CBackend, ty: TyId, inst: Inst) Res<TyId, AllocError>

unsettled* = (be: CBackend, ty: TyId) bool

any_unsettled = (be: CBackend, list: Vec<TyId>) bool

any_open* = (be: CBackend, sig: Vec<TyId>) bool

inst_open* = (be: CBackend, inst: Inst) bool

settled_inst* = (
    be      :: CBackend,
    tparams : Vec<TParam>,
    owner   : str,
    inst    : Inst
) Res<Inst, AllocError>

settle_one = (
    be    :: CBackend,
    tp    : TParam,
    owner : str,
    inst  : Inst,
    out   :: Inst
) Res<(), AllocError>

settle_bound = (be :: CBackend, v: TyId, t: TyId, out :: Inst)
               Res<(), AllocError>

unify* = (be :: CBackend, declared: TyId, actual: TyId, out :: Inst)
         Res<(), AllocError>

unify_named = (be :: CBackend, n: TyNamed, actual: TyId, out :: Inst)
              Res<(), AllocError>

unify_args = (be :: CBackend, ds: Vec<TyId>, ts: Vec<TyId>, out :: Inst)
             Res<(), AllocError>

unify_each = (be :: CBackend, ds: Vec<TyId>, ts: Vec<TyId>, out :: Inst)
             Res<(), AllocError>

unify_at = (be :: CBackend, d: TyId, ts: Vec<TyId>, i: usize, out :: Inst)
           Res<(), AllocError>

unify_res = (be :: CBackend, r: TyRes, actual: TyId, out :: Inst)
            Res<(), AllocError>

unify_res_parts = (be :: CBackend, r: TyRes, q: TyRes, out :: Inst)
                  Res<(), AllocError>

arg_type* = (be :: CBackend, id: ExprId, ctx: Ctx, want: TyId)
            Res<TyId, AllocError>

local_type = (be :: CBackend, id: ExprId) Res<TyId>

slot_ty = (be :: CBackend, name: str) Res<TyId>

enter_tparams* = (be :: CBackend, tparams: Vec<TParam>, owner: str)
                 Res<usize, AllocError>

enter_one = (be :: CBackend, tp: TParam, owner: str) Res<(), AllocError>

leave_tparams* = (be :: CBackend, mark: usize) Res<(), AllocError>

enter_struct_tparams* = (be :: CBackend, decl: DeclId)
                        Res<usize, AllocError>

enter_decl_tparams = (be :: CBackend, decl: DeclId, d: Decl)
                     Res<(), AllocError>

enter_enum_of = (be :: CBackend, decl: DeclId, e: Enum)
                Res<(), AllocError>

enter_struct_of = (be :: CBackend, decl: DeclId, s: Struct)
                  Res<(), AllocError>
```

#### Imports and re-exports

```zen
Decl, Enum, Struct, TParam, ExprId = std.ast

AllocError = std.mem

Vec = std.collections

str = std.text

Range = std.core

DeclId = sema.sema_id

TyId, TyNamed, TyRes = sema.sema_ty

Def, decl_at = sema.sema_def

Checker, Ctx = sema.sema_check

Inst, subst, has_var, inst_of_named, owner_of = sema.sema_inst

tparam_vars = sema.sema_inst

CBackend = gen.gen_c.gen_c_state

ty_of = gen.gen_c.gen_c_expr
```

### `src/gen/gen_c/gen_c_num.zen`

9 declarations (functions: 1, imports and re-exports: 8).

#### Functions

```zen
lower_checked_narrow* = (
    be    :: CBackend,
    id    : ExprId,
    value : ExprId,
    src   : TyId,
    ret   : TyId,
    ctx   : Ctx,
    out   :: String
) Res<(), AllocError>
```

#### Imports and re-exports

```zen
ExprId = std.ast

AllocError = std.mem

String = std.text

TyId = sema.sema_ty

Ctx = sema.sema_check

CBackend = gen.gen_c.gen_c_state

expr = gen.gen_c.gen_c_expr

temp, write_assign_none, write_assign_ok = gen.gen_c.gen_c_flow
```

### `src/gen/gen_c/gen_c_op.zen`

79 declarations (types: 1, enums: 2, functions: 54, constants: 2, imports and re-exports: 20).

#### Types

```zen
Rung = {
    id: ExprId,
    lhs: ExprId,
    operand: TyId,
    folds: bool,
}
```

#### Enums

```zen
NegKind = Float | Folded(str) | Checked

OpKind = ShortCircuit | Infix | Helper(str) | Dispatched | Refused
```

#### Functions

```zen
lower_unary* = (
    be   :: CBackend,
    node : Expr,
    u    : Unary,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

wrap_unary = (
    be      :: CBackend,
    op      : str,
    operand : ExprId,
    ctx     : Ctx,
    want    : TyId,
    out     :: String
) Res<(), AllocError>

lower_negate = (
    be   :: CBackend,
    node : Expr,
    u    : Unary,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

negate_kind = (be: CBackend, u: Unary, prim: str) NegKind

int_digits = (be: CBackend, id: ExprId) Res<str>

literal_digits = (l: Literal) Res<str>

write_negative_literal = (digits: str, out :: String) Res<(), AllocError>

write_neg = (digits: str, out :: String) Res<(), AllocError>

negate_checked = (
    be   :: CBackend,
    node : Expr,
    u    : Unary,
    prim : str,
    ctx  : Ctx,
    ty   : TyId,
    out  :: String
) Res<(), AllocError>

lower_binary* = (
    be   :: CBackend,
    node : Expr,
    b    : Binary,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

binary_type* = (be :: CBackend, b: Binary, ctx: Ctx, want: TyId)
               Res<TyId, AllocError>

operand_answer = (be :: CBackend, b: Binary, ctx: Ctx, want: TyId)
                 Res<TyId, AllocError>

is_comparison* = (op: BinOp) bool

op_kind = (be: CBackend, b: Binary, operand: TyId) OpKind

arith_kind = (prim: str) OpKind

write_short_circuit = (
    be      :: CBackend,
    b       : Binary,
    bool_ty : TyId,
    ctx     : Ctx,
    out     :: String
) Res<(), AllocError>

open_guard = (be :: CBackend, op: BinOp, tmp: str) Res<(), AllocError>

negation = (op: BinOp) str

operand_type = (be :: CBackend, b: Binary, ctx: Ctx, want: TyId)
               Res<TyId, AllocError>

rhs_type = (be :: CBackend, b: Binary, ctx: Ctx, want: TyId)
           Res<TyId, AllocError>

usable = (be :: CBackend, id: TyId) bool

lower_eq_op = (
    be      :: CBackend,
    b       : Binary,
    ctx     : Ctx,
    operand : TyId,
    out     :: String
) Res<(), AllocError>

write_equality = (be :: CBackend, op: BinOp, text: str, out :: String)
                 Res<(), AllocError>

is_equality = (op: BinOp) bool

is_negated = (op: BinOp) bool

scalar = (be: CBackend, id: TyId) bool

write_infix = (
    be      :: CBackend,
    b       : Binary,
    op      : str,
    ctx     : Ctx,
    operand : TyId,
    out     :: String
) Res<(), AllocError>

lower_lhs = (
    be   :: CBackend,
    id   : ExprId,
    held : bool,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

spine_ahead = (be: CBackend, id: ExprId, held: bool) bool

binary_ahead = (be: CBackend, id: ExprId) bool

close_infix = (
    be      :: CBackend,
    b       : Binary,
    op      : str,
    ctx     : Ctx,
    operand : TyId,
    out     :: String
) Res<(), AllocError>

c_op* = (op: BinOp) str

helper_stem* = (op: BinOp) str

traps* = (op: BinOp) bool

call_helper = (
    be      :: CBackend,
    node    : Expr,
    b       : Binary,
    prim    : str,
    ctx     : Ctx,
    operand : TyId,
    out     :: String
) Res<(), AllocError>

open_helper = (be :: CBackend, b: Binary, prim: str, out :: String)
              Res<(), AllocError>

close_helper = (
    be      :: CBackend,
    node    : Expr,
    b       : Binary,
    ctx     : Ctx,
    operand : TyId,
    out     :: String
) Res<(), AllocError>

write_trap_args = (be :: CBackend, node: Expr, b: Binary, out :: String)
                  Res<(), AllocError>

spine_lhs = (
    be   :: CBackend,
    id   : ExprId,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

rung_at = (be :: CBackend, id: ExprId, ctx: Ctx, want: TyId)
          Res<Rung, AllocError>

base_rung = (id: ExprId, want: TyId) Rung

binary_rung = (be :: CBackend, id: ExprId, b: Binary, ctx: Ctx, want: TyId)
              Res<Rung, AllocError>

operand_rung = (be :: CBackend, id: ExprId, b: Binary, ctx: Ctx, want: TyId)
               Res<Rung, AllocError>

level_type = (be :: CBackend, b: Binary, ctx: Ctx, want: TyId)
             Res<TyId, AllocError>

plain_level = (be :: CBackend, b: Binary, ctx: Ctx, want: TyId)
              Res<TyId, AllocError>

comparison_level = (be :: CBackend, b: Binary, ctx: Ctx, want: TyId)
                   Res<TyId, AllocError>

comparison_rhs = (be :: CBackend, b: Binary, ctx: Ctx, want: TyId)
                 Res<TyId, AllocError>

infix_shaped = (be: CBackend, b: Binary, operand: TyId) bool

open_rung = (be :: CBackend, rungs: Vec<Rung>, at: usize, out :: String)
            Res<(), AllocError>

close_rung = (
    be    :: CBackend,
    rungs : Vec<Rung>,
    at    : usize,
    ctx   : Ctx,
    out   :: String
) Res<(), AllocError>

close_node = (
    be   :: CBackend,
    node : Expr,
    rung : Rung,
    ctx  : Ctx,
    out  :: String
) Res<(), AllocError>

open_op = (be :: CBackend, b: Binary, operand: TyId, out :: String)
          Res<(), AllocError>

close_op = (
    be      :: CBackend,
    node    : Expr,
    b       : Binary,
    operand : TyId,
    ctx     : Ctx,
    out     :: String
) Res<(), AllocError>

write_position* = (be :: CBackend, file: str, span: Span, out :: String)
                  Res<(), AllocError>
```

#### Constants

```zen
I64_MIN_DIGITS: str = "9223372036854775808"

I64_MIN_C: str = "(-9223372036854775807LL - 1LL)"
```

#### Imports and re-exports

```zen
Expr, ExprId, Span = std.ast

Literal, BinOp, Binary, Unary = std.ast

AllocError = std.mem

Vec = std.collections

str, String = std.text

Range = std.core

TyId = sema.sema_ty

Ctx, is_logical = sema.sema_check

type_of = sema.sema_type

CBackend = gen.gen_c.gen_c_state

unsupported = gen.gen_c.gen_c_report

sub = gen.gen_c.gen_c_mono

is_c_integer = gen.gen_c.gen_c_type

lower_eq_call = gen.gen_c.gen_c_member

init_temp = gen.gen_c.gen_c_flow

expr, ty_of, spills_anywhere = gen.gen_c.gen_c_expr

infix_operand_held, value_held = gen.gen_c.gen_c_expr

needs_set = gen.gen_c.gen_c_widen

needs_hoist = gen.gen_c.gen_c_hoist

needs_fat = gen.gen_c.gen_c_fat
```

### `src/gen/gen_c/gen_c_own.zen`

64 declarations (functions: 49, imports and re-exports: 15).

#### Functions

```zen
enter_block* = (be :: CBackend, id: BlockId) Res<(), AllocError>

block_record = (be :: CBackend, id: BlockId) Res<usize, AllocError>

open_record = (be :: CBackend) Res<usize, AllocError>

leave_block* = (be :: CBackend, keep: str) Res<(), AllocError>

unwind_to* = (be :: CBackend, depth: usize, keep: str)
             Res<(), AllocError>

unwind_frames = (be :: CBackend, depth: usize, n: usize, keep: str)
                Res<(), AllocError>

run_frame = (be :: CBackend, i: usize, keep: str) Res<(), AllocError>

run_cleanup = (be :: CBackend, f: BlockFrame, i: usize, keep: str)
              Res<(), AllocError>

frame_end = (be :: CBackend, i: usize) usize

run_defers = (be :: CBackend, rec: usize) Res<(), AllocError>

unwind_drops = (be :: CBackend, mark: usize, end: usize, keep: str)
               Res<(), AllocError>

drop_range = (be :: CBackend, mark: usize, end: usize, keep: str)
             Res<(), AllocError>

drop_unless_kept = (be :: CBackend, e: DropEntry, keep: str)
                   Res<(), AllocError>

note_drop* = (be :: CBackend, name: str, index: usize, ty: TyId)
             Res<(), AllocError>

own_binding = (be :: CBackend, name: str, index: usize, ty: TyId)
              Res<(), AllocError>

open_live_flag = (be :: CBackend) Res<usize, AllocError>

release_binding* = (be :: CBackend, name: str) Res<(), AllocError>

clear_if_named = (be :: CBackend, e: DropEntry, name: str)
                 Res<(), AllocError>

write_clear = (be :: CBackend, live: usize) Res<(), AllocError>

displace* = (be :: CBackend, name: str) Res<(), AllocError>

displace_one = (be :: CBackend, e: DropEntry) Res<(), AllocError>

has_drop* = (be :: CBackend, ty: TyId) Res<bool, AllocError>

site_has_drop = (be :: CBackend, s: Site) Res<bool, AllocError>

write_drop = (be :: CBackend, e: DropEntry) Res<(), AllocError>

drop_through = (be :: CBackend, e: DropEntry, s: Site)
               Res<(), AllocError>

guarded_drop = (be :: CBackend, e: DropEntry, s: Site, f: Function)
               Res<(), AllocError>

flagged_drop = (be :: CBackend, e: DropEntry, s: Site, f: Function)
               Res<(), AllocError>

call_drop = (be :: CBackend, e: DropEntry, s: Site, f: Function)
            Res<(), AllocError>

by_address = (f: Function) bool

write_drop_call = (be :: CBackend, e: DropEntry, sym: str, addr: bool)
                  Res<(), AllocError>

ampersand = (addr: bool) str

drop_fn* = (be :: CBackend, decl: DeclId) Res<Res<Function>, AllocError>

collect_drop = (
    be    :: CBackend,
    decl  : DeclId,
    i     : ImplId,
    found :: Vec<Function>
) Res<(), AllocError>

drop_in_impl = (be :: CBackend, i: ImplId, found :: Vec<Function>)
               Res<(), AllocError>

keep_drop_member = (be :: CBackend, im: Impl, found :: Vec<Function>)
                   Res<(), AllocError>

bounds_drop = (be :: CBackend, im: Impl) bool

scan_drop_members = (im: Impl, found :: Vec<Function>)
                    Res<(), AllocError>

keep_bodied_drop = (m: Member, found :: Vec<Function>)
                   Res<(), AllocError>

add_bodied = (m: Member, found :: Vec<Function>) Res<(), AllocError>

add_if_bodied = (f: Function, found :: Vec<Function>)
                Res<(), AllocError>

writes_scope* = (be :: CBackend, id: BlockId) bool

stmt_writes_scope = (be :: CBackend, s: Stmt) bool

expr_writes_scope = (be :: CBackend, id: ExprId) bool

opt_writes_scope = (be :: CBackend, id: Res<ExprId>) bool

binary_writes_scope = (be :: CBackend, b: Binary) bool

binary_below = (be :: CBackend, id: ExprId) Res<Binary>

call_writes_scope = (be :: CBackend, c: Call) bool

match_writes_scope = (be :: CBackend, m: Match) bool

elems_write_scope = (be :: CBackend, elems: Vec<ExprId>) bool
```

#### Imports and re-exports

```zen
Expr, ExprId, BlockId, Block, Stmt, Bind = std.ast

Decl, Member, Function = std.ast

Impl, Call, Access, Match, Binary, Try = std.ast

AllocError = std.mem

Vec = std.collections

str, String = std.text

Range = std.core

DeclId, ImplId = sema.sema_id

TyId = sema.sema_ty

sym_local, sym_gen = gen.gen_name

CBackend = gen.gen_c.gen_c_state

decl_name = gen.gen_c.gen_c_impl

DropEntry, BlockFrame = gen.gen_c.gen_c_frame

recv_inst = gen.gen_c.gen_c_mono

Site, site_of, method_sig, member_symbol = gen.gen_c.gen_c_member
```

### `src/gen/gen_c/gen_c_print.zen`

68 declarations (types: 1, enums: 1, functions: 49, constants: 3, imports and re-exports: 14).

#### Types

```zen
FmtAt* = {
    what*: FmtWhat,
    keep*: usize,
    next*: usize,
}
```

#### Enums

```zen
FmtWhat* = Byte
         | Hole
         | Pair
         | Named(str)
         | NoName
```

#### Functions

```zen
is_print* = (name: str) bool

is_console_print* = (name: str) bool

stream_of = (name: str) str

pair = (stream: str, stdout: str, stderr: str) str

lower_print* = (be :: CBackend, c: Call, name: str, ctx: Ctx, out :: String)
               Res<(), AllocError>

lower_console_print* = (
    be   :: CBackend,
    c    : Call,
    name : str,
    ret  : TyId,
    ctx  : Ctx,
    out  :: String
) Res<(), AllocError>

write_pieces = (
    be     :: CBackend,
    c      : Call,
    name   : str,
    stream : str,
    ctx    : Ctx
) Res<(), AllocError>

write_args = (
    be     :: CBackend,
    c      : Call,
    stream : str,
    ctx    : Ctx
) Res<(), AllocError>

write_from = (
    be     :: CBackend,
    c      : Call,
    first  : Arg,
    stream : str,
    ctx    : Ctx
) Res<(), AllocError>

format_of = (be :: CBackend, id: ExprId) Res<str>

literal_format = (l: Literal) Res<str>

write_values = (
    be     :: CBackend,
    c      : Call,
    from   : usize,
    stream : str,
    ctx    : Ctx
) Res<(), AllocError>

write_value_at = (
    be     :: CBackend,
    c      : Call,
    i      : usize,
    stream : str,
    ctx    : Ctx
) Res<(), AllocError>

write_format = (
    be     :: CBackend,
    c      : Call,
    id     : ExprId,
    raw    : str,
    stream : str,
    ctx    : Ctx
) Res<(), AllocError>

write_surplus = (
    be     :: CBackend,
    c      : Call,
    used   : usize,
    stream : str,
    ctx    : Ctx
) Res<(), AllocError>

write_what = (
    be     :: CBackend,
    c      : Call,
    id     : ExprId,
    at     : FmtAt,
    used   : usize,
    stream : str,
    ctx    : Ctx
) Res<(), AllocError>

write_named = (
    be     :: CBackend,
    id     : ExprId,
    at     : FmtAt,
    name   : str,
    stream : str
) Res<(), AllocError>

ends_run* = (at: FmtAt) bool

arguments_taken* = (what: FmtWhat) usize

fmt_at* = (raw: str, i: usize, end: usize) FmtAt

at_no_hole = (raw: str, i: usize, end: usize) FmtAt

at_no_pair = (raw: str, i: usize, end: usize) FmtAt

at_ident = (raw: str, i: usize, end: usize, j: usize) FmtAt

body_end* = (raw: str) usize

is_hole = (raw: str, i: usize, end: usize) bool

is_doubled_brace = (raw: str, i: usize, end: usize) bool

opens_name = (raw: str, i: usize, end: usize) bool

ident_end = (raw: str, from: usize, end: usize) usize

report_in_format* = (
    be    :: CBackend,
    id    : ExprId,
    at    : FmtAt,
    fault : GenFault
) Res<(), AllocError>

at_span = (lit: Span, from: usize, to: usize) Span

step_of = (raw: str, i: usize) usize

write_hole = (
    be     :: CBackend,
    c      : Call,
    id     : ExprId,
    at     : FmtAt,
    used   : usize,
    stream : str,
    ctx    : Ctx
) Res<(), AllocError>

write_piece = (
    be     :: CBackend,
    raw    : str,
    start  : usize,
    stop   : usize,
    stream : str
) Res<(), AllocError>

write_chunk = (be :: CBackend, piece: str, stream: str) Res<(), AllocError>

decoded_bytes* = (piece: str) usize

write_value = (
    be     :: CBackend,
    arg    : ExprId,
    stream : str,
    ctx    : Ctx
) Res<(), AllocError>

write_typed = (
    be     :: CBackend,
    arg    : ExprId,
    ty     : TyId,
    prim   : str,
    text   : str,
    stream : str
) Res<(), AllocError>

printer* = (prim: str, stream: str) str

scalar_printer = (prim: str, stream: str) str

number_printer = (prim: str, stream: str) str

integer_printer = (prim: str, stream: str) str

signed_printer = (prim: str, stream: str) str

cast_of* = (prim: str) str

scalar_cast = (prim: str) str

number_cast = (prim: str) str

integer_cast = (prim: str) str

write_write = (be :: CBackend, fn: str, cast: str, text: str)
              Res<(), AllocError>

write_display = (
    be     :: CBackend,
    arg    : ExprId,
    ty     : TyId,
    text   : str,
    stream : str
) Res<(), AllocError>

print_fault = (be :: CBackend, arg: ExprId) Res<(), AllocError>
```

#### Constants

```zen
NOT_A_HOLE* : str = "a format hole is {} or {name}, and this is neither"

HOLE_WITHOUT_ARGUMENT* : str = "a format hole with no argument left"

ARGUMENT_WITHOUT_HOLE* : str = "an argument with no format hole left"
```

#### Imports and re-exports

```zen
ExprId, Literal = std.ast

Call, Arg, Span, Pos = std.ast

AllocError = std.mem

str, String = std.text

Range = std.core

is_ident_start, is_ident_cont = std.core

TyId, is_float = sema.sema_ty

Ctx = sema.sema_check

GenFault = gen.gen_diag

sym_variant, RES_PATH = gen.gen_name

CBackend = gen.gen_c.gen_c_state

is_c_integer, is_signed, ctype = gen.gen_c.gen_c_type

expr, ty_of, named_hole = gen.gen_c.gen_c_expr

console_display, stderr_console = gen.gen_c.gen_c_display
```

### `src/gen/gen_c/gen_c_ptr.zen`

34 declarations (types: 2, enums: 1, functions: 18, imports and re-exports: 13).

#### Types

```zen
PtrTypeSite = {
    c: Call,
    name: str,
    rty: TyId,
    ctx: Ctx,
    want: TyId,
    resolve = (self: @Self, be :: CBackend) Res<TyId, AllocError>
    after_read = (self: @Self, be :: CBackend) Res<TyId, AllocError>
    after_shift = (self: @Self, be :: CBackend) Res<TyId, AllocError>
    after_bytes = (self: @Self, be :: CBackend) Res<TyId, AllocError>
    after_null = (self: @Self, be :: CBackend) Res<TyId, AllocError>
    target_type = (self: @Self, be :: CBackend) Res<TyId, AllocError>
    target_ptr = (self: @Self, be :: CBackend)
                 Res<Res<TyId>, AllocError>
    ptr_of_written = (self: @Self, be :: CBackend, t: TypeId)
                     Res<Res<TyId>, AllocError>
}

PtrCall = {
    id: ExprId,
    site: PtrTypeSite,
    et: TyId,
    base: str,
    lower = (self: @Self, be :: CBackend, out :: String)
            Res<(), AllocError>
    after_read = (self: @Self, be :: CBackend, out :: String)
                 Res<(), AllocError>
    after_write = (self: @Self, be :: CBackend, out :: String)
                  Res<(), AllocError>
    after_offset = (self: @Self, be :: CBackend, out :: String)
                   Res<(), AllocError>
    after_back = (self: @Self, be :: CBackend, out :: String)
                 Res<(), AllocError>
    after_bytes = (self: @Self, be :: CBackend, out :: String)
                  Res<(), AllocError>
    after_copy = (self: @Self, be :: CBackend, out :: String)
                 Res<(), AllocError>
    after_same = (self: @Self, be :: CBackend, out :: String)
                 Res<(), AllocError>
    same = (self: @Self, be :: CBackend, out :: String)
           Res<(), AllocError>
    read = (self: @Self, be :: CBackend, out :: String)
           Res<(), AllocError>
    write = (self: @Self, be :: CBackend, out :: String)
            Res<(), AllocError>
    run = (self: @Self, be :: CBackend, out :: String)
          Res<(), AllocError>
    shift = (self: @Self, be :: CBackend, op: str, out :: String)
            Res<(), AllocError>
    byte_size = (self: @Self, be :: CBackend, out :: String)
                Res<(), AllocError>
    copy_from = (self: @Self, be :: CBackend, out :: String)
                Res<(), AllocError>
    count_bytes = (self: @Self, be :: CBackend, out :: String)
                  Res<(), AllocError>
    scaled_bytes = (self: @Self, be :: CBackend, i: usize,
                    out :: String) Res<(), AllocError>
    reinterpret = (self: @Self, be :: CBackend, out :: String)
                  Res<(), AllocError>
    index_arg = (self: @Self, be :: CBackend, i: usize, out :: String)
                Res<(), AllocError>
    value_arg = (self: @Self, be :: CBackend, i: usize, want: TyId,
                 out :: String) Res<(), AllocError>
}
```

#### Enums

```zen
PtrUnitPolicy = PtrLower | PtrRefuse | PtrZero
```

#### Functions

```zen
is_ptr_member* = (be :: CBackend, rty: TyId, name: str) bool

named_ptr = (be :: CBackend, rty: TyId) bool

ptr_verb = (name: str) bool

elem_of = (be :: CBackend, rty: TyId) Res<TyId, AllocError>

ptr_member_type* = (
    be   :: CBackend,
    c    : Call,
    a    : Access,
    rty  : TyId,
    ctx  : Ctx,
    want : TyId
) Res<TyId, AllocError>

ptr_unit_policy = (be: CBackend, et: TyId, name: str) PtrUnitPolicy

lower_ptr_member* = (
    be   :: CBackend,
    id   : ExprId,
    c    : Call,
    a    : Access,
    rty  : TyId,
    ctx  : Ctx,
    want : TyId,
    out  :: String
)
                    Res<(), AllocError>

lower_ptr_call = (
    be   :: CBackend,
    id   : ExprId,
    c    : Call,
    a    : Access,
    rty  : TyId,
    et   : TyId,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

lower_zero_run = (
    be  :: CBackend,
    c   : Call,
    a   : Access,
    rty : TyId,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

discard_ptr_arg = (
    be   :: CBackend,
    c    : Call,
    i    : usize,
    want : TyId,
    ctx  : Ctx
) Res<(), AllocError>

address = (
    be   :: CBackend,
    base : ExprId,
    rty  : TyId,
    ctx  : Ctx,
    out  :: String
) Res<(), AllocError>

keep_ptr = (be :: CBackend, want: TyId) Res<TyId>

ptr_at* = (be :: CBackend, n: TyNamed, elem: TyId) Res<TyId, AllocError>

intern_ptr = (c :: Checker, n: TyNamed, qname: str, args: Vec<TyId>)
             Res<TyId, AllocError>

write_reinterpret = (be :: CBackend, pt: TyId, base: str, out :: String)
                    Res<(), AllocError>

is_null_ptr* = (name: str) bool

lower_null_ptr* = (be :: CBackend, id: ExprId, want: TyId, out :: String)
                  Res<(), AllocError>

write_null = (be :: CBackend, want: TyId, out :: String)
             Res<(), AllocError>
```

#### Imports and re-exports

```zen
ExprId, Access, Call, TypeId = std.ast

AllocError = std.mem

Vec = std.collections

str, String = std.text

TyId, TyNamed = sema.sema_ty

Checker, Ctx = sema.sema_check

CBackend = gen.gen_c.gen_c_state

untyped, unsupported = gen.gen_c.gen_c_report

sub = gen.gen_c.gen_c_mono

ctype, request_type = gen.gen_c.gen_c_type

write_qname = gen.gen_c.gen_c_layout

expr = gen.gen_c.gen_c_expr

Dest, deliver = gen.gen_c.gen_c_stmt
```

### `src/gen/gen_c/gen_c_range.zen`

67 declarations (types: 1, functions: 40, imports and re-exports: 26).

#### Types

```zen
RangeImpl* = {
    decl*: DeclId,
    mi*: usize,
    start*: ExprId,
    end*: ExprId,
    at*: Res<Function>,
}
```

#### Functions

```zen
supplies_bounds* = (be :: CBackend, rty: TyId) bool

has_field = (be :: CBackend, rty: TyId, name: str) bool

decl_has_field = (be :: CBackend, decl: DeclId, name: str) bool

struct_has_field = (s: Struct, name: str) bool

range_impl* = (be :: CBackend, rty: TyId) Res<Res<RangeImpl>, AllocError>

primitive_range_impl = (be :: CBackend, p: Prim)
                       Res<Res<RangeImpl>, AllocError>

named_range_impl = (be :: CBackend, n: TyNamed)
                   Res<Res<RangeImpl>, AllocError>

keep_range_impl = (
    be  :: CBackend,
    n   : TyNamed,
    i   : ImplId,
    out :: Vec<RangeImpl>
) Res<(), AllocError>

range_impl_at = (
    be  :: CBackend,
    n   : TyNamed,
    i   : ImplId,
    out :: Vec<RangeImpl>
) Res<(), AllocError>

keep_if_range = (
    be  :: CBackend,
    n   : TyNamed,
    im  : Impl,
    out :: Vec<RangeImpl>
) Res<(), AllocError>

add_range_impl = (
    be  :: CBackend,
    n   : TyNamed,
    im  : Impl,
    mi  : usize,
    out :: Vec<RangeImpl>
) Res<(), AllocError>

add_from_start = (
    be  :: CBackend,
    n   : TyNamed,
    im  : Impl,
    mi  : usize,
    s   : ExprId,
    out :: Vec<RangeImpl>
) Res<(), AllocError>

impl_fn = (be :: CBackend, im: Impl, name: str)
          Res<Res<Function>, AllocError>

keep_bodied_fn = (m: Member, name: str, out :: Vec<Function>)
                 Res<(), AllocError>

add_bodied_fn = (m: Member, out :: Vec<Function>) Res<(), AllocError>

add_if_bodied = (f: Function, out :: Vec<Function>) Res<(), AllocError>

range_pass_type* = (be :: CBackend, rty: TyId) Res<Res<TyId>, AllocError>

array_pass = (be :: CBackend, a: TyArray) Res<Res<TyId>, AllocError>

stored_or_supplied_pass = (be :: CBackend, rty: TyId)
                          Res<Res<TyId>, AllocError>

index_pass = (be :: CBackend) Res<Res<TyId>, AllocError>

impl_pass = (be :: CBackend, rty: TyId) Res<Res<TyId>, AllocError>

at_pass = (be :: CBackend, rty: TyId, ri: RangeImpl)
          Res<Res<TyId>, AllocError>

at_ret = (be :: CBackend, rty: TyId, ri: RangeImpl, f: Function)
         Res<Res<TyId>, AllocError>

keep_res = (be :: CBackend, got: TyId) Res<TyId>

range_element_type* = (be :: CBackend, rty: TyId)
                      Res<Res<TyId>, AllocError>

lower_supplied* = (
    be   :: CBackend,
    id   : ExprId,
    sh   : Shape,
    one  : ExprId,
    rty  : TyId,
    lam  : Lambda,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

lower_impl_range = (
    be   :: CBackend,
    id   : ExprId,
    sh   : Shape,
    one  : ExprId,
    rty  : TyId,
    ri   : RangeImpl,
    lam  : Lambda,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

lower_impl_walk = (
    be   :: CBackend,
    id   : ExprId,
    sh   : Shape,
    one  : ExprId,
    rty  : TyId,
    ri   : RangeImpl,
    pass : TyId,
    lam  : Lambda,
    ctx  : Ctx,
    want : TyId,
    out  :: String
)
                  Res<(), AllocError>

bind_self = (be :: CBackend, ri: RangeImpl, rty: TyId, rng: str)
            Res<(), AllocError>

self_name = (be :: CBackend, ri: RangeImpl) str

first_param_name = (f: Function) str

bind_text* = (be :: CBackend, name: str, ty: TyId, text: str)
            Res<(), AllocError>

supplied_bound* = (
    be     :: CBackend,
    ri     : RangeImpl,
    rty    : TyId,
    value  : ExprId,
    target : str,
    rng    : str
) Res<(), AllocError>

impl_ctx = (be :: CBackend, ri: RangeImpl, ret: TyId, self_ty: TyId) Ctx

take_pass* = (
    be      :: CBackend,
    ri      : RangeImpl,
    rty     : TyId,
    pass    : TyId,
    counter : str,
    brk     : usize,
    rng     : str,
    value   :: String
)
            Res<(), AllocError>

run_at = (
    be      :: CBackend,
    ri      : RangeImpl,
    rty     : TyId,
    pass    : TyId,
    f       : Function,
    counter : str,
    brk     : usize,
    rng     : str,
    value   :: String
)
         Res<(), AllocError>

inline_at = (
    be      :: CBackend,
    ri      : RangeImpl,
    rty     : TyId,
    pass    : TyId,
    f       : Function,
    counter : str,
    rng     : str,
    tmp     : str
)
            Res<(), AllocError>

bind_index_param = (
    be       :: CBackend,
    f        : Function,
    usize_ty : TyId,
    counter  : str
) Res<(), AllocError>

run_at_body = (be :: CBackend, f: Function, ictx: Ctx, pass: TyId, tmp: str)
              Res<(), AllocError>

write_pass_guard = (be :: CBackend, tmp: str, brk: usize)
                   Res<(), AllocError>
```

#### Imports and re-exports

```zen
ExprId, Lambda = std.ast

Function = std.ast

Impl, Member, Field, Struct = std.ast

AllocError = std.mem

Vec = std.collections

str, String = std.text

DeclId, ImplId = sema.sema_id

TyId, TyNamed, TyArray, Prim = sema.sema_ty

Def = sema.sema_def

Ctx = sema.sema_check

self_ctx = sema.sema_member

impl_bound_type = sema.sema_supply

sym_local, sym_member, sym_variant = gen.gen_name

RES_PATH = gen.gen_name

CBackend = gen.gen_c.gen_c_state

unsupported = gen.gen_c.gen_c_report

declarator, declared_ret, struct_decl, res_value, is_res = gen.gen_c.gen_c_type

intern_res_open, recv_inst, sub_with = gen.gen_c.gen_c_mono

enter_struct_tparams, leave_tparams = gen.gen_c.gen_c_mono

Dest, block, deliver = gen.gen_c.gen_c_stmt

write_label, open_result, close_pass = gen.gen_c.gen_c_loop

Shape = gen.gen_c.gen_c_shape

run_body, declare_usize, settle_res, walk_temp = gen.gen_c.gen_c_loop

no_fold = gen.gen_c.gen_c_fold

array_of = gen.gen_c.gen_c_array

impl_field = gen.gen_c.gen_c_impl
```

### `src/gen/gen_c/gen_c_read.zen`

69 declarations (types: 2, functions: 43, imports and re-exports: 24).

#### Types

```zen
TypeConst* = {
    k: Const,
    d: Def,
}

Computed = {
    value: ExprId,
    decl: DeclId,
    mi: usize,
    ty: TyId,
    bound: TyId,
}
```

#### Functions

```zen
lower_access* = (
    be   :: CBackend,
    id   : ExprId,
    a    : Access,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

lower_type_or_field = (
    be   :: CBackend,
    id   : ExprId,
    a    : Access,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

lower_recv_const_or_field = (
    be   :: CBackend,
    id   : ExprId,
    a    : Access,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

recv_const = (be :: CBackend, a: Access, ctx: Ctx)
             Res<Res<TypeConst>, AllocError>

named_recv_const = (be :: CBackend, n: TyNamed, name: str)
                   Res<Res<TypeConst>, AllocError>

same_decl = (d: Def, n: TyNamed) bool

type_const* = (be :: CBackend, a: Access, ctx: Ctx)
             Res<Res<TypeConst>, AllocError>

named_type_const = (be :: CBackend, base: str, name: str, ctx: Ctx)
                   Res<Res<TypeConst>, AllocError>

decl_const = (be :: CBackend, base: str, name: str, ctx: Ctx)
             Res<Res<TypeConst>, AllocError>

collect_type_const = (
    be   :: CBackend,
    d    : Def,
    name : str,
    out  :: Vec<TypeConst>
) Res<(), AllocError>

collect_decl_const = (
    be   :: CBackend,
    x    : Decl,
    d    : Def,
    name : str,
    out  :: Vec<TypeConst>
) Res<(), AllocError>

collect_struct_const = (
    s    : Struct,
    d    : Def,
    name : str,
    out  :: Vec<TypeConst>
) Res<(), AllocError>

keep_const = (m: Member, d: Def, name: str, out :: Vec<TypeConst>)
             Res<(), AllocError>

keep_named_const = (k: Const, d: Def, name: str, out :: Vec<TypeConst>)
                   Res<(), AllocError>

base_decl* = (be :: CBackend, base: ExprId, ctx: Ctx) Res<TyId>

enum_named = (be :: CBackend, text: str, ctx: Ctx) Res<TyId>

enum_def_named = (be :: CBackend, text: str, ctx: Ctx) Res<TyId>

first_enum = (be :: CBackend, found: Vec<Def>) Res<TyId>

enum_type_of = (be :: CBackend, d: Def) Res<TyId>

intern_named* = (be :: CBackend, d: Def) Res<TyId>

write_variant_value* = (
    be      :: CBackend,
    id      : ExprId,
    ty      : TyId,
    want    : TyId,
    variant : str,
    out     :: String
) Res<(), AllocError>

nullary_ty* = (be :: CBackend, ty: TyId, want: TyId) TyId

expected_enum = (be :: CBackend, ty: TyId, want: TyId) Res<TyId>

enum_qname = (be :: CBackend, ty: TyId, out :: String) Res<(), AllocError>

access_field_type* = (be :: CBackend, a: Access, ctx: Ctx, want: TyId)
                     Res<TyId, AllocError>

write_field_access = (
    be  :: CBackend,
    id  : ExprId,
    a   : Access,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

write_selected_field = (
    be    :: CBackend,
    id    : ExprId,
    a     : Access,
    rty   : TyId,
    found : Vec<Computed>,
    ctx   : Ctx,
    out   :: String
)
                       Res<(), AllocError>

keep_supplied_by = (found: Vec<Computed>, b: TyId, kept :: Vec<Computed>)
                   Res<(), AllocError>

keep_if_bound = (cf: Computed, b: TyId, kept :: Vec<Computed>)
                Res<(), AllocError>

write_stored_field = (
    be  :: CBackend,
    a   : Access,
    rty : TyId,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

supplied_fields = (
    be   :: CBackend,
    rty  : TyId,
    name : str,
    out  :: Vec<Computed>
) Res<(), AllocError>

named_supplied = (
    be   :: CBackend,
    n    : TyNamed,
    rty  : TyId,
    name : str,
    out  :: Vec<Computed>
) Res<(), AllocError>

declares_own = (be: CBackend, id: DeclId, name: str) bool

struct_has_member = (s: Struct, name: str) bool

impls_supplying = (
    be   :: CBackend,
    n    : TyNamed,
    rty  : TyId,
    name : str,
    out  :: Vec<Computed>
) Res<(), AllocError>

local_supplied = (
    be   :: CBackend,
    n    : TyNamed,
    rty  : TyId,
    i    : ImplId,
    name : str,
    out  :: Vec<Computed>
) Res<(), AllocError>

supplied_in_impl = (
    be   :: CBackend,
    n    : TyNamed,
    rty  : TyId,
    i    : ImplId,
    name : str,
    out  :: Vec<Computed>
) Res<(), AllocError>

impl_supplied_value = (
    be   :: CBackend,
    n    : TyNamed,
    rty  : TyId,
    im   : Impl,
    name : str,
    out  :: Vec<Computed>
)
                      Res<(), AllocError>

add_computed = (
    be   :: CBackend,
    n    : TyNamed,
    rty  : TyId,
    im   : Impl,
    name : str,
    v    : ExprId,
    out  :: Vec<Computed>
) Res<(), AllocError>

write_computed_field = (
    be    :: CBackend,
    a     : Access,
    rty   : TyId,
    found : Vec<Computed>,
    ctx   : Ctx,
    out   :: String
)
                       Res<(), AllocError>

write_supplied_value = (
    be  :: CBackend,
    a   : Access,
    rty : TyId,
    cf  : Computed,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

field_name = (be :: CBackend, rty: TyId, name: str, out :: String)
             Res<(), AllocError>

is_str* = (be :: CBackend, rty: TyId) bool
```

#### Imports and re-exports

```zen
ExprId, Decl, Struct, Member = std.ast

Const, Access, Impl = std.ast

AllocError = std.mem

Vec = std.collections

str, String = std.text

DeclId, ImplId = sema.sema_id

TyId, TyNamed = sema.sema_ty

Def, decl_at = sema.sema_def

Ctx = sema.sema_check

has_var* = sema.sema_inst

alias_enum = sema.sema_denote

impl_bound_type, bound_member_type = sema.sema_supply

sym_member, sym_variant = gen.gen_name

CBackend = gen.gen_c.gen_c_state

unsupported = gen.gen_c.gen_c_report

constructed, recv_inst = gen.gen_c.gen_c_mono

enter_struct_tparams, leave_tparams = gen.gen_c.gen_c_mono

ctype, struct_decl, has_storage = gen.gen_c.gen_c_type

write_qname = gen.gen_c.gen_c_layout

bind_text = gen.gen_c.gen_c_range

impl_field = gen.gen_c.gen_c_impl

expr, ty_of = gen.gen_c.gen_c_expr

field_of = gen.gen_c.gen_c_type

lower_const_value = gen.gen_c.gen_c_const
```

### `src/gen/gen_c/gen_c_report.zen`

12 declarations (functions: 5, imports and re-exports: 7).

#### Functions

```zen
closure_storage* = (
    be   :: CBackend,
    span : Span,
    slot : LocalSlot,
    what : str
) Res<bool, AllocError>

unsupported* = (be :: CBackend, id: ExprId, what: str, out :: String)
               Res<(), AllocError>

unresolved* = (be :: CBackend, id: ExprId, name: str, out :: String)
              Res<(), AllocError>

untyped* = (be :: CBackend, id: ExprId, what: str, out :: String)
           Res<(), AllocError>

ambiguous* = (be :: CBackend, id: ExprId, name: str, out :: String)
             Res<(), AllocError>
```

#### Imports and re-exports

```zen
ExprId = std.ast.ast_id

Span = std.ast.ast_span

str, String = std.text

AllocError = std.mem

GenFault = gen.gen_diag

CBackend = gen.gen_c.gen_c_state

LocalSlot = gen.gen_c.gen_c_frame
```

### `src/gen/gen_c/gen_c_runtime.zen`

61 declarations (functions: 55, constants: 1, imports and re-exports: 5).

#### Functions

```zen
comment* = (out :: Emit, text: str) Res<(), AllocError>

emit_banner* = (out :: Emit) Res<(), AllocError>

emit_floor* = (out :: Emit) Res<(), AllocError>

emit_trap = (out :: Emit) Res<(), AllocError>

emit_index = (out :: Emit) Res<(), AllocError>

emit_print* = (be :: CBackend, out :: Emit) Res<(), AllocError>

write_float_scratch = (out :: Emit) Res<(), AllocError>

write_print = (out :: Emit) Res<(), AllocError>

emit_stderr* = (be :: CBackend, out :: Emit) Res<(), AllocError>

write_stderr = (out :: Emit) Res<(), AllocError>

emit_scope_floor* = (be :: CBackend, out :: Emit) Res<(), AllocError>

write_scope_floor = (out :: Emit) Res<(), AllocError>

emit_scope* = (be :: CBackend, out :: Emit) Res<(), AllocError>

write_scope = (be :: CBackend, out :: Emit) Res<(), AllocError>

write_defer_envs = (be :: CBackend, out :: Emit) Res<(), AllocError>

write_env_line = (out :: Emit, text: String) Res<(), AllocError>

write_defer_union = (be :: CBackend, out :: Emit) Res<(), AllocError>

write_union_member = (out :: Emit, n: usize) Res<(), AllocError>

write_defer_runtime = (out :: Emit) Res<(), AllocError>

write_defer_push = (out :: Emit) Res<(), AllocError>

write_defer_run = (out :: Emit) Res<(), AllocError>

emit_fs* = (be :: CBackend, out :: Emit) Res<(), AllocError>

write_fs = (out :: Emit) Res<(), AllocError>

write_fs_error = (out :: Emit) Res<(), AllocError>

write_fs_ordinals = (out :: Emit) Res<(), AllocError>

write_fs_path = (out :: Emit) Res<(), AllocError>

write_fs_kind = (out :: Emit) Res<(), AllocError>

write_fs_size = (out :: Emit) Res<(), AllocError>

write_fs_write = (out :: Emit) Res<(), AllocError>

write_fs_remove = (out :: Emit) Res<(), AllocError>

write_fs_read = (out :: Emit) Res<(), AllocError>

write_fs_lock = (out :: Emit) Res<(), AllocError>

write_fs_unlock = (out :: Emit) Res<(), AllocError>

emit_helpers* = (be :: CBackend, out :: Emit) Res<(), AllocError>

emit_family = (out :: Emit, prim: str) Res<(), AllocError>

open_helper = (out :: Emit, ct: str, prim: str, op: str, pos: bool)
              Res<(), AllocError>

close_helper = (out :: Emit) Res<(), AllocError>

checked = (out :: Emit, ct: str, prim: str, op: str, builtin: str)
          Res<(), AllocError>

fallback = (out :: Emit, ct: str, prim: str, op: str) Res<(), AllocError>

c_symbol* = (op: str) str

signed_guard = (out :: Emit, prim: str, op: str) Res<(), AllocError>

signed_sub_or_mul = (out :: Emit, op: str, hi: str, lo: str)
                    Res<(), AllocError>

two_sided = (
    out     :: Emit,
    lead    : str,
    hi      : str,
    hi_tail : str,
    lead2   : str,
    lo      : str,
    lo_tail : str
) Res<(), AllocError>

signed_mul_guard = (out :: Emit, hi: str, lo: str) Res<(), AllocError>

quadrant = (out :: Emit, sign: str, lead: str, bound: str, tail: str)
           Res<(), AllocError>

unsigned_guard = (out :: Emit, prim: str, op: str) Res<(), AllocError>

unsigned_sub_or_mul = (out :: Emit, op: str, hi: str) Res<(), AllocError>

one_sided = (out :: Emit, lead: str, bound: str, tail: str)
            Res<(), AllocError>

wrapped_return = (out :: Emit, ct: str, uct: str, sym: str)
                 Res<(), AllocError>

divide = (out :: Emit, ct: str, prim: str, op: str, sym: str, signed: bool)
         Res<(), AllocError>

write_min_guard = (out :: Emit, prim: str) Res<(), AllocError>

wrapping = (out :: Emit, ct: str, uct: str, prim: str, op: str, sym: str)
           Res<(), AllocError>

unsigned_of* = (ct: str) str

max_macro* = (prim: str) str

min_macro* = (prim: str) str
```

#### Constants

```zen
C_STANDARD* : str = "C99 (ISO/IEC 9899:1999)"
```

#### Imports and re-exports

```zen
AllocError = std.mem

str, String = std.text

Emit, order = gen.gen_emit

CBackend = gen.gen_c.gen_c_state

c_prim, is_signed = gen.gen_c.gen_c_type
```

### `src/gen/gen_c/gen_c_scope.zen`

63 declarations (functions: 46, imports and re-exports: 17).

#### Functions

```zen
is_scope_ref* = (be :: CBackend, id: ExprId) bool

scope_type* = (be :: CBackend, ctx: Ctx) Res<TyId, AllocError>

scope_named = (be :: CBackend, d: Def) Res<TyId, AllocError>

lower_scope_ref* = (be :: CBackend, id: ExprId, out :: String)
                   Res<(), AllocError>

innermost_record = (be :: CBackend) usize

record_of = (be :: CBackend, i: usize) usize

write_record_ref = (be :: CBackend, rec: usize, out :: String)
                   Res<(), AllocError>

is_defer* = (be :: CBackend, rty: TyId, name: str) bool

scope_receiver = (be :: CBackend, rty: TyId) bool

lower_defer* = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    a   : Access,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

scope_operand = (be :: CBackend, base: ExprId, ctx: Ctx, out :: String)
                Res<(), AllocError>

write_scope_value = (be :: CBackend, base: ExprId, ctx: Ctx, out :: String)
                    Res<(), AllocError>

slot_name = (be :: CBackend, id: ExprId) Res<str>

write_scope_local = (be :: CBackend, id: ExprId, name: str, out :: String)
                    Res<(), AllocError>

write_scope_slot* = (
    be   :: CBackend,
    name : str,
    span : Span,
    slot : LocalSlot,
    out  :: String
) Res<(), AllocError>

defer_arg = (
    be   :: CBackend,
    id   : ExprId,
    g    : Arg,
    recv : str,
    ctx  : Ctx,
    out  :: String
) Res<(), AllocError>

defer_lambda = (
    be   :: CBackend,
    id   : ExprId,
    l    : Lambda,
    recv : str,
    ctx  : Ctx,
    out  :: String
) Res<(), AllocError>

register_closure = (
    be   :: CBackend,
    id   : ExprId,
    l    : Lambda,
    recv : str,
    ctx  : Ctx,
    out  :: String
) Res<(), AllocError>

write_env_type = (be :: CBackend, n: usize, caps: Vec<LocalSlot>)
                 Res<(), AllocError>

write_env_struct = (be :: CBackend, n: usize, caps: Vec<LocalSlot>)
                   Res<(), AllocError>

write_env_field = (be :: CBackend, s: LocalSlot, text :: String)
                  Res<(), AllocError>

ref_field = (be :: CBackend, ty: TyId, name: str, text :: String)
            Res<(), AllocError>

env_name = (be :: CBackend, n: usize, out :: String) Res<(), AllocError>

write_thunk = (
    be   :: CBackend,
    n    : usize,
    l    : Lambda,
    caps : Vec<LocalSlot>,
    ctx  : Ctx
) Res<(), AllocError>

thunk_proto = (be :: CBackend, n: usize, out :: String)
              Res<(), AllocError>

write_prologue = (be :: CBackend, n: usize, caps: Vec<LocalSlot>)
                 Res<(), AllocError>

write_unpack = (be :: CBackend, n: usize, caps: Vec<LocalSlot>)
               Res<(), AllocError>

write_unpack_one = (be :: CBackend, s: LocalSlot) Res<(), AllocError>

write_registration = (
    be   :: CBackend,
    id   : ExprId,
    n    : usize,
    caps : Vec<LocalSlot>,
    recv : str
)
                     Res<(), AllocError>

fill_record = (
    be   :: CBackend,
    n    : usize,
    caps : Vec<LocalSlot>,
    cell :: String
) Res<(), AllocError>

copy_capture = (be :: CBackend, s: LocalSlot, cell: str)
               Res<(), AllocError>

write_defer_call = (
    be   :: CBackend,
    id   : ExprId,
    n    : usize,
    cell : str,
    recv : str
) Res<(), AllocError>

write_defer_env_args = (be :: CBackend, cell: str, line :: String)
                       Res<(), AllocError>

write_env_args = (cell: str, line :: String) Res<(), AllocError>

captures* = (be :: CBackend, id: BlockId, out :: Vec<LocalSlot>)
            Res<(), AllocError>

stmt_captures = (be :: CBackend, s: Stmt, out :: Vec<LocalSlot>)
                Res<(), AllocError>

bind_captures = (be :: CBackend, b: Bind, out :: Vec<LocalSlot>)
                Res<(), AllocError>

expr_captures = (be :: CBackend, id: ExprId, out :: Vec<LocalSlot>)
                Res<(), AllocError>

try_captures = (be :: CBackend, t: Try, out :: Vec<LocalSlot>)
               Res<(), AllocError>

pair_captures = (
    be  :: CBackend,
    a   : ExprId,
    b   : ExprId,
    out :: Vec<LocalSlot>
) Res<(), AllocError>

call_captures = (be :: CBackend, c: Call, out :: Vec<LocalSlot>)
                Res<(), AllocError>

match_captures = (be :: CBackend, m: Match, out :: Vec<LocalSlot>)
                 Res<(), AllocError>

elem_captures = (be :: CBackend, elems: Vec<ExprId>, out :: Vec<LocalSlot>)
                Res<(), AllocError>

keep_capture = (be :: CBackend, name: str, out :: Vec<LocalSlot>)
               Res<(), AllocError>

keep_value_slot = (be :: CBackend, s: LocalSlot, out :: Vec<LocalSlot>)
                  Res<(), AllocError>

held = (out: Vec<LocalSlot>, s: LocalSlot) bool
```

#### Imports and re-exports

```zen
Expr, ExprId, BlockId, Block, Stmt, Bind, Span = std.ast

Decl, Lambda, Call, Arg, Access, Match, Try = std.ast

AllocError = std.mem

Vec = std.collections

str, String = std.text

Range = std.core

TyId = sema.sema_ty

Def = sema.sema_def

Ctx = sema.sema_check

sym_local, sym_gen = gen.gen_name

CBackend = gen.gen_c.gen_c_state

LocalSlot = gen.gen_c.gen_c_frame

unsupported, closure_storage = gen.gen_c.gen_c_report

intern_named = gen.gen_c.gen_c_mono

ctype, declarator, is_scope_named = gen.gen_c.gen_c_type

Dest, block = gen.gen_c.gen_c_stmt

write_position = gen.gen_c.gen_c_op
```

### `src/gen/gen_c/gen_c_settle.zen`

69 declarations (functions: 47, imports and re-exports: 22).

#### Functions

```zen
arguments* = (be :: CBackend, c: Call, recv: Res<ExprId>, argv :: Vec<ExprId>)
            Res<(), AllocError>

param_types* = (
    be   :: CBackend,
    f    : Function,
    dctx : Ctx,
    inst : Inst,
    ptys :: Vec<TyId>
) Res<(), AllocError>

add_param_type = (
    be   :: CBackend,
    p    : Param,
    dctx : Ctx,
    inst : Inst,
    ptys :: Vec<TyId>
) Res<(), AllocError>

inline_ret* = (
    be    :: CBackend,
    f     : Function,
    dctx  : Ctx,
    inst  : Inst,
    extra :: Inst,
    argv  : Vec<ExprId>,
    ctx   : Ctx
)
             Res<TyId, AllocError>

call_bindings* = (
    be    :: CBackend,
    argv  : Vec<ExprId>,
    ptys  : Vec<TyId>,
    ctx   : Ctx,
    extra :: Inst
) Res<(), AllocError>

settle_from_arg_at = (
    be    :: CBackend,
    i     : usize,
    argv  : Vec<ExprId>,
    ptys  : Vec<TyId>,
    ctx   : Ctx,
    extra :: Inst
)
                     Res<(), AllocError>

settle_from_arg = (
    be    :: CBackend,
    value : ExprId,
    i     : usize,
    ptys  : Vec<TyId>,
    ctx   : Ctx,
    extra :: Inst
)
                  Res<(), AllocError>

settle_from_value = (
    be    :: CBackend,
    value : ExprId,
    i     : usize,
    ptys  : Vec<TyId>,
    ctx   : Ctx,
    extra :: Inst
)
                    Res<(), AllocError>

settle_bare = (
    be    :: CBackend,
    value : ExprId,
    t     : TyId,
    ctx   : Ctx,
    extra :: Inst
) Res<(), AllocError>

bind_arg_type = (
    be    :: CBackend,
    value : ExprId,
    v     : TyId,
    ctx   : Ctx,
    extra :: Inst
) Res<(), AllocError>

settle_params* = (
    be    :: CBackend,
    raws  : Vec<TyId>,
    extra : Inst,
    ptys  :: Vec<TyId>
) Res<(), AllocError>

compose* = (be :: CBackend, inst: Inst, extra: Inst) Res<Inst, AllocError>

carry = (be :: CBackend, inst: Inst, extra: Inst, i: usize, full :: Inst)
        Res<(), AllocError>

carry_arg = (
    be    :: CBackend,
    inst  : Inst,
    extra : Inst,
    i     : usize,
    v     : TyId,
    full  :: Inst
) Res<(), AllocError>

carry_extra = (extra: Inst, i: usize, full :: Inst) Res<(), AllocError>

bind_extra = (extra: Inst, i: usize, v: TyId, full :: Inst)
             Res<(), AllocError>

settle_from_body = (
    be    :: CBackend,
    l     : Lambda,
    i     : usize,
    ptys  : Vec<TyId>,
    ctx   : Ctx,
    extra :: Inst
) Res<(), AllocError>

lambda_ret_is_open = (be :: CBackend, l: Lambda, ctx: Ctx)
                     Res<bool, AllocError>

ret_var = (be :: CBackend, i: usize, ptys: Vec<TyId>) Res<TyId>

fn_ret_var = (be :: CBackend, t: TyId) Res<TyId>

keep_var = (be :: CBackend, t: TyId) Res<TyId>

bind_body_type = (
    be    :: CBackend,
    l     : Lambda,
    v     : TyId,
    i     : usize,
    ptys  : Vec<TyId>,
    ctx   : Ctx,
    extra :: Inst
)
                 Res<(), AllocError>

peek_params = (be :: CBackend, l: Lambda, i: usize, ptys: Vec<TyId>)
              Res<(), AllocError>

peek_fn_params = (be :: CBackend, l: Lambda, t: TyId) Res<(), AllocError>

peek_each_param = (be :: CBackend, l: Lambda, params: Vec<TyId>)
                  Res<(), AllocError>

peek_param_at = (be :: CBackend, l: Lambda, params: Vec<TyId>, i: usize)
                Res<(), AllocError>

peek_param_named = (be :: CBackend, p: Param, params: Vec<TyId>, i: usize)
                   Res<(), AllocError>

peek_declare = (be :: CBackend, name: str, ty: TyId) Res<(), AllocError>

declare_peek_slot = (be :: CBackend, name: str, ty: TyId)
                    Res<(), AllocError>

lambda_value_type = (be :: CBackend, l: Lambda, ctx: Ctx)
                    Res<TyId, AllocError>

value_or_unit = (be :: CBackend, e: ExprId, ctx: Ctx, unit: TyId)
                Res<TyId, AllocError>

settled* = (be :: CBackend, t: TyId) bool

range_element = (
    be    :: CBackend,
    got   : TyId,
    argv  : Vec<ExprId>,
    ctx   : Ctx,
    extra :: Inst
) Res<TyId, AllocError>

element_of = (be :: CBackend, got: TyId, r: ExprId, ctx: Ctx, extra :: Inst)
             Res<TyId, AllocError>

walk_elements = (be :: CBackend, got: TyId, elem: TyId, extra :: Inst)
                Res<TyId, AllocError>

index_res = (be :: CBackend, got: TyId, rs: TyRes, elem: TyId, extra :: Inst)
            Res<TyId, AllocError>

usize_bound = (
    be    :: CBackend,
    got   : TyId,
    v     : TyId,
    elem  : TyId,
    extra :: Inst
) Res<TyId, AllocError>

inline_result_type* = (be :: CBackend, id: ExprId, ctx: Ctx, got: TyId)
                      Res<TyId, AllocError>

call_result = (be :: CBackend, id: ExprId, c: Call, ctx: Ctx, got: TyId)
              Res<TyId, AllocError>

callee_name = (be :: CBackend, c: Call) Res<str>

named_result = (
    be   :: CBackend,
    id   : ExprId,
    c    : Call,
    name : str,
    ctx  : Ctx,
    got  : TyId
) Res<TyId, AllocError>

pick_def = (be :: CBackend, id: ExprId, found: Vec<Def>) Res<Def>

sole_of = (found: Vec<Def>) Res<Def>

def_result = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    d   : Def,
    ctx : Ctx,
    got : TyId
) Res<TyId, AllocError>

decl_result = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    d   : Def,
    x   : Decl,
    ctx : Ctx,
    got : TyId
) Res<TyId, AllocError>

fn_result = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    d   : Def,
    f   : Function,
    ctx : Ctx,
    got : TyId
) Res<TyId, AllocError>

computed_result = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    d   : Def,
    f   : Function,
    ctx : Ctx
) Res<TyId, AllocError>
```

#### Imports and re-exports

```zen
ExprId, Lambda, Param = std.ast

Decl, Function, Access, Call = std.ast

AllocError = std.mem

Vec = std.collections

str = std.text

Range = std.core

TyId, TyRes = sema.sema_ty

Def, decl_at = sema.sema_def

Ctx = sema.sema_check

tail_expr = sema.sema_hoist

Inst, has_var = sema.sema_inst

param_type, type_from_ast = sema.sema_denote

CBackend = gen.gen_c.gen_c_state

sub_with, inst_at, settled_inst = gen.gen_c.gen_c_mono

enter_tparams, leave_tparams = gen.gen_c.gen_c_mono

declared_ret = gen.gen_c.gen_c_type

ty_of = gen.gen_c.gen_c_expr

def_with_id = gen.gen_c.gen_c_call

plain_ctx = gen.gen_c.gen_c_decl

range_element_type = gen.gen_c.gen_c_range

inlines = gen.gen_c.gen_c_inline

recv_of = gen.gen_c.gen_c_shape
```

### `src/gen/gen_c/gen_c_shape.zen`

52 declarations (types: 1, functions: 32, imports and re-exports: 19).

#### Types

```zen
Shape* = {
    wants_index*: bool,
    wants_value*: bool,
    wants_acc*: bool,
    lead*: usize,
}
```

#### Functions

```zen
is_loop_shape* = (be :: CBackend, f: Function) bool

takes_handle = (be :: CBackend, params: Vec<Param>) bool

param_is_handle_body = (be :: CBackend, p: Param) bool

type_is_handle_body = (be :: CBackend, tid: TypeId) bool

first_is_handle = (be :: CBackend, params: Vec<Param>) bool

param_names_handle = (be :: CBackend, p: Param) bool

type_named = (be :: CBackend, tid: TypeId) str

loop_result_type* = (
    be   :: CBackend,
    id   : ExprId,
    ctx  : Ctx,
    got  : TyId,
    want : TyId
) Res<TyId, AllocError>

loop_fn_at* = (be :: CBackend, id: ExprId) Res<Function>

loop_fn_of = (be :: CBackend, did: DeclId) Res<Function>

loop_fn_decl = (be :: CBackend, x: Decl) Res<Function>

keep_loop = (be :: CBackend, f: Function) Res<Function>

settled_loop_type = (
    be   :: CBackend,
    id   : ExprId,
    ctx  : Ctx,
    got  : TyId,
    want : TyId
) Res<TyId, AllocError>

loop_element* = (be :: CBackend, id: ExprId, ctx: Ctx)
               Res<Res<TyId>, AllocError>

arg_element = (be :: CBackend, r: ExprId, ctx: Ctx, usize_ty: TyId)
              Res<Res<TyId>, AllocError>

broken_element_want* = (be :: CBackend, id: ExprId, ctx: Ctx, want: TyId)
                       Res<TyId, AllocError>

broken_element* = (be :: CBackend, id: ExprId, ctx: Ctx)
                  Res<TyId, AllocError>

join_break_args* = (be :: CBackend, span: Span, ctx: Ctx)
                   Res<Res<TyId>, AllocError>

break_value_site = (be: CBackend, x: ExprId) bool

owned_elsewhere* = (
    be   :: CBackend,
    site : Span,
    span : Span
) Res<bool, AllocError>

break_arg_type* = (be :: CBackend, x: ExprId, ctx: Ctx)
                  Res<Res<TyId>, AllocError>

range_arg* = (be :: CBackend, id: ExprId) Res<ExprId>

call_range_arg = (be :: CBackend, c: Call) Res<ExprId>

recv_of* = (be :: CBackend, callee: ExprId) Res<ExprId>

leading_arg = (c: Call) Res<ExprId>

arg_value* = (c: Call, i: usize) Res<ExprId>

shape_of* = (be :: CBackend, f: Function) Res<Shape, AllocError>

body_params = (be :: CBackend, f: Function, out :: Vec<Param>)
              Res<(), AllocError>

collect_fn_params = (be :: CBackend, p: Param, out :: Vec<Param>)
                    Res<(), AllocError>

copy_fn_params = (be :: CBackend, tid: TypeId, out :: Vec<Param>)
                 Res<(), AllocError>

add_params = (params: Vec<Param>, out :: Vec<Param>) Res<(), AllocError>

names_after_first = (params: Vec<Param>, name: str) bool
```

#### Imports and re-exports

```zen
ExprId = std.ast

Decl, Function, Param, TypeId = std.ast

Access, Call, Span = std.ast

inside = std.ast

AllocError = std.mem

Vec = std.collections

str = std.text

Range = std.core

DeclId = sema.sema_id

TyId = sema.sema_ty

has_var = sema.sema_inst

decl_at = sema.sema_def

is_handle_ty = sema.sema_handle

Ctx = sema.sema_check

CBackend = gen.gen_c.gen_c_state

ty_of = gen.gen_c.gen_c_expr

range_element_type = gen.gen_c.gen_c_range

result_element = gen.gen_c.gen_c_fold

settle_res = gen.gen_c.gen_c_loop
```

### `src/gen/gen_c/gen_c_sink.zen`

80 declarations (types: 5, functions: 43, constants: 2, imports and re-exports: 30).

#### Types

```zen
BufferCall = {
    id: ExprId,
    c: Call,
    addr: str,
    cty: TyId,
    fail: usize,
    recv: Res<ExprId>,
    ctx: Ctx,
    at_decl = (self: @Self, be :: CBackend, d: Def) Res<bool, AllocError>
    into = (self: @Self, be :: CBackend, d: Def, f: Function) Res<bool, AllocError>
}

SinkValue = { id: ExprId, ty: TyId, text: str }

Piece* = {
    sink: str,
    sty: TyId,
    floor: str,
    tmp*: str,
    done*: usize,
    id: ExprId,
    module: usize,
    rty: TyId,
    ret: TyId,
    write_typed = (self: @Self, be :: CBackend, a: ExprId, ty: TyId,
                   text: str) Res<(), AllocError>
    value_call = (self: @Self, be :: CBackend, ty: TyId, text: str,
                  out :: String) Res<bool, AllocError>
    wider_call = (self: @Self, be :: CBackend, ty: TyId, prim: str,
                  text: str, out :: String) Res<bool, AllocError>
    write_wider = (self: @Self, be :: CBackend, v: SinkValue)
                   Res<(), AllocError>
    through_sink = (self: @Self, be :: CBackend, v: SinkValue)
                   Res<(), AllocError>
    sink_at_door = (self: @Self, be :: CBackend, v: SinkValue, d: Def)
                   Res<(), AllocError>
    sink_over_receiver = (self: @Self, be :: CBackend, v: SinkValue,
                          d: Def, f: Function)
                          Res<(), AllocError>
    wider_is_sound = (self: @Self, be :: CBackend, sty: TyId)
                     Res<bool, AllocError>
    write_through_sink = (self: @Self, be :: CBackend, v: SinkValue,
                          d: Def, sty: TyId, wret: TyId)
                          Res<(), AllocError>
    wider_guarded = (self: @Self, be :: CBackend, call: str, wtmp: str)
                    Res<(), AllocError>
    hole_fault = (self: @Self) str
    scalar_call = (self: @Self, be :: CBackend, ty: TyId, prim: str,
                   text: str, out :: String) Res<bool, AllocError>
    sink_write = (self: @Self, be :: CBackend, text: str, out :: String)
                 Res<bool, AllocError>
    floor_write = (self: @Self, text: str, out :: String)
                  Res<bool, AllocError>
    slot_write = (self: @Self, be :: CBackend, text: str, out :: String)
                 Res<bool, AllocError>
    writer_call = (self: @Self, be :: CBackend, name: str, cast: str,
                   text: str, out :: String) Res<bool, AllocError>
    write_intrinsic_call = (self: @Self, be :: CBackend, cast: str, text: str,
                            out :: String) Res<bool, AllocError>
    write_writer_call = (self: @Self, be :: CBackend, w: Def, cast: str,
                         text: str, out :: String) Res<bool, AllocError>
    write_guarded = (self: @Self, be :: CBackend, call: str)
                    Res<(), AllocError>
    unsupported = (self: @Self, be :: CBackend, id: ExprId, what: str)
                  Res<(), AllocError>
}

SinkWalk = {
    c: Call,
    p: Piece,
    ctx: Ctx,
    write = (self: @Self, be :: CBackend, first: ExprId, used: usize)
            Res<(), AllocError>
    write_values = (self: @Self, be :: CBackend, first: ExprId, used: usize)
                   Res<(), AllocError>
    walk_format = (self: @Self, be :: CBackend, id: ExprId, raw: str,
                   used0: usize) Res<(), AllocError>
    write_what = (self: @Self, be :: CBackend, id: ExprId, at: FmtAt,
                  used: usize) Res<(), AllocError>
    write_named = (self: @Self, be :: CBackend, id: ExprId, at: FmtAt,
                   name: str) Res<(), AllocError>
    write_hole = (self: @Self, be :: CBackend, id: ExprId, at: FmtAt,
                  used: usize) Res<(), AllocError>
    write_surplus = (self: @Self, be :: CBackend, used: usize)
                    Res<(), AllocError>
    write_rest = (self: @Self, be :: CBackend, used: usize)
                 Res<(), AllocError>
    write_chunk = (self: @Self, be :: CBackend, raw: str, start: usize,
                   stop: usize) Res<(), AllocError>
    write_literal = (self: @Self, be :: CBackend, piece: str)
                    Res<(), AllocError>
    write_value = (self: @Self, be :: CBackend, a: ExprId)
                  Res<(), AllocError>
}

DoorCall = {
    id: ExprId,
    c: Call,
    d: Def,
    f: Function,
    recv: Res<ExprId>,
    ctx: Ctx,
    lower = (self: @Self, be :: CBackend, out :: String) Res<(), AllocError>
    write = (self: @Self, be :: CBackend, ret: TyId, sty: TyId, sink: str,
             out :: String) Res<(), AllocError>
}
```

#### Functions

```zen
is_sink_door* = (be: CBackend, d: Def, f: Function) bool

sink_door_shape* = (be: CBackend, f: Function) bool

bodyless* = (f: Function) bool

last_is_variadic* = (be: CBackend, f: Function) bool

tail_is_variadic = (be: CBackend, f: Function, i: usize) bool

variadic_param = (be: CBackend, p: Param) bool

variadic_type = (be: CBackend, t: TypeId) bool

door_decl = (be :: CBackend) Res<Res<Def>, AllocError>

keep_door = (be :: CBackend, x: Def, out :: Vec<Def>) Res<(), AllocError>

keep_shaped = (be :: CBackend, g: Function, x: Def, out :: Vec<Def>)
              Res<(), AllocError>

door_fn = (be :: CBackend, d: Def) Res<Function>

decl_fn = (dec: Decl) Res<Function>

lower_pieces_into* = (
    be   :: CBackend,
    id   : ExprId,
    c    : Call,
    addr : str,
    cty  : TyId,
    fail : usize,
    recv : Res<ExprId>,
    ctx  : Ctx
)
                     Res<bool, AllocError>

buffer_sink = (
    be   :: CBackend,
    addr : str,
    cty  : TyId,
    sty  : TyId,
    out  :: String
) Res<(), AllocError>

lower_sink_door* = (
    be   :: CBackend,
    id   : ExprId,
    c    : Call,
    d    : Def,
    f    : Function,
    recv : Res<ExprId>,
    ctx  : Ctx,
    out  :: String
) Res<(), AllocError>

declared_type = (be :: CBackend, d: Def, t: Res<TypeId>)
                Res<TyId, AllocError>

sink_type = (be :: CBackend, d: Def, f: Function) Res<TyId, AllocError>

door_ctx = (d: Def) Ctx

write_sink_temp = (
    be   :: CBackend,
    c    : Call,
    recv : Res<ExprId>,
    sty  : TyId,
    ctx  : Ctx,
    out  :: String
) Res<bool, AllocError>

spill_sink = (
    be  :: CBackend,
    a   : ExprId,
    sty : TyId,
    ctx : Ctx,
    out :: String
) Res<bool, AllocError>

write_ok* = (be :: CBackend, ret: TyId, tmp: str) Res<(), AllocError>

fmt_arg = (c: Call, recv: Res<ExprId>) Res<ExprId>

fmt_index = (recv: Res<ExprId>) usize

write_pieces* = (
    be    :: CBackend,
    c     : Call,
    first : ExprId,
    used0 : usize,
    p     : Piece,
    ctx   : Ctx
) Res<(), AllocError>

format_of = (be: CBackend, id: ExprId) str

literal_format = (l: Literal) str

names_out_of_memory = (be :: CBackend, ret: TyId) bool

writer_of = (prim: str) str

number_writer = (prim: str) str

integer_writer = (prim: str) str

signed_writer = (prim: str) str

module_fn = (be :: CBackend, mi: usize, name: str)
            Res<Res<Def>, AllocError>

module_decl = (be :: CBackend, mi: usize, name: str)
              Res<Res<Def>, AllocError>

keep_fn = (be :: CBackend, x: Def, out :: Vec<Def>)
          Res<(), AllocError>

keep_fn_decl = (dec: Decl, x: Def, out :: Vec<Def>)
               Res<(), AllocError>

keep_bodied = (be :: CBackend, x: Def, out :: Vec<Def>)
              Res<(), AllocError>

keep_bodied_decl = (dec: Decl, x: Def, out :: Vec<Def>)
                   Res<(), AllocError>

keep_bodied_fn = (fn: Function, x: Def, out :: Vec<Def>)
                 Res<(), AllocError>

call_symbol* = (be :: CBackend, d: Def, out :: String)
               Res<(), AllocError>

write_jump_unless_ok* = (be :: CBackend, tmp: str, done: usize)
                        Res<(), AllocError>

write_goto* = (be :: CBackend, done: usize) Res<(), AllocError>

write_done* = (be :: CBackend, done: usize) Res<(), AllocError>

done_name = (be :: CBackend, done: usize) Res<String, AllocError>
```

#### Constants

```zen
FORMAT_DOOR*: str = "fmt"

SINK_FLOOR*: str = "write"
```

#### Imports and re-exports

```zen
ExprId, Decl, Function, Param, Call = std.ast

Literal, TypeId = std.ast

AllocError = std.mem

Vec = std.collections

str, String = std.text

Range = std.core

TyId = sema.sema_ty

Def, decl_at = sema.sema_def

Ctx = sema.sema_check

Inst = sema.sema_inst

param_type = sema.sema_denote

satisfies_bound = sema.sema_bound

sym_fn, sym_gen, sym_variant, RES_PATH = gen.gen_name

GenFault = gen.gen_diag

CBackend = gen.gen_c.gen_c_state

unsupported = gen.gen_c.gen_c_report

ctype = gen.gen_c.gen_c_type

is_c_integer, is_signed = gen.gen_c.gen_c_type

expr, ty_of, named_hole = gen.gen_c.gen_c_expr

declare_temp, is_variant, payload_type = gen.gen_c.gen_c_flow

write_assign_err = gen.gen_c.gen_c_flow

signature_of = gen.gen_c.gen_c_call

recv_arg, arg_value, by_ref = gen.gen_c.gen_c_arg

body_end, decoded_bytes, cast_of = gen.gen_c.gen_c_print

FmtAt, fmt_at, ends_run, arguments_taken = gen.gen_c.gen_c_print

report_in_format, NOT_A_HOLE = gen.gen_c.gen_c_print

HOLE_WITHOUT_ARGUMENT, ARGUMENT_WITHOUT_HOLE = gen.gen_c.gen_c_print

slot_call = gen.gen_c.gen_c_bound

fat_value = gen.gen_c.gen_c_fat

sink_display = gen.gen_c.gen_c_display
```

### `src/gen/gen_c/gen_c_state.zen`

20 declarations (types: 3, enums: 1, functions: 2, imports and re-exports: 14).

#### Types

```zen
MethodRef* = {
    self_ty*: TyId,
    decl*: DeclId,
    name*: str,
    sig*: Vec<TyId>,
    qname*: str,
}

Cleanup* = {
    blocks*: Vec<BlockFrame>,
    drops*: Vec<DropEntry>,
}

CBackend* = {
    tree*: Ast,
    check* :: Checker,
    buf :: Emit,
    diags :: Vec<GenDiag>,
    type_names* :: Vec<String>,
    type_ids* :: Vec<TyId>,
    type_done* :: Vec<bool>,
    helper_types* :: Vec<String>,
    print_used :: bool,
    stderr_used :: bool,
    fbuf_used :: bool,
    fs_used :: bool,
    stdin_used :: bool,
    env_used :: bool,
    clock_used :: bool,
    threads_used :: bool,
    spawn_used :: bool,
    spawn_envs :: Vec<String>,
    spawn_sites :: usize,
    actor_used :: bool,
    actor_defs :: Vec<String>,
    actor_sites :: usize,
    fn_queue* :: Vec<Def>,
    m_queue* :: Vec<MethodRef>,
    fn_insts :: Vec<Inst>,
    m_insts :: Vec<Inst>,
    inst* :: Inst,
    fn_seen :: Vec<String>,
    fn_names* :: Vec<String>,
    fn_protos* :: Vec<String>,
    fn_bodies* :: Vec<String>,
    fn_origins :: Vec<FnOrigin>,
    fn_units* :: Vec<usize>,
    unit :: usize,
    externs :: bool,
    ffi* :: bool,
    extern_names* :: Vec<String>,
    extern_protos* :: Vec<String>,
    c_headers* :: Vec<String>,
    locals :: Vec<LocalSlot>,
    declared :: Vec<String>,
    loops :: Vec<LoopFrame>,
    blocks :: Vec<BlockFrame>,
    drops :: Vec<DropEntry>,
    scope_used :: bool,
    defer_envs :: Vec<String>,
    defer_env_ids :: Vec<usize>,
    defer_sites :: usize,
    closures :: Vec<Closure>,
    depth* :: usize,
    floor* :: usize,
    tmp* :: usize,
    alloc*: Alloc,
    diag_count* = (self: @Self) usize
    diag_at* = (self: @Self, i: usize) Res<GenDiag>
    render_diags* = (self: @Self, out :: String) Res<(), AllocError>
    report* = (self :: @Self, file: str, span: Span, fault: GenFault)
              Res<(), AllocError>
    report_expr* = (self :: @Self, id: ExprId, fault: GenFault)
                   Res<(), AllocError>
    types* = (self: @Self) Types
    world* = (self: @Self) World
    type_index* = (self: @Self, name: str) Res<usize>
    queue_type* = (self :: @Self, name: String, id: TyId)
                  Res<(), AllocError>
    type_name_at* = (self: @Self, i: usize) str
    type_id_at* = (self: @Self, i: usize) Res<TyId>
    is_done* = (self: @Self, i: usize) bool
    mark_done* = (self :: @Self, i: usize) Res<(), AllocError>
    need_helpers* = (self :: @Self, prim: str) Res<(), AllocError>
    has_helpers = (self: @Self, prim: str) bool
    add_helpers = (self :: @Self, prim: str) Res<(), AllocError>
    need_print* = (self :: @Self) ()
    uses_print* = (self: @Self) bool
    need_stderr* = (self :: @Self) ()
    uses_stderr* = (self: @Self) bool
    need_fbuf* = (self :: @Self) ()
    uses_fbuf* = (self: @Self) bool
    need_fs* = (self :: @Self) ()
    uses_fs* = (self: @Self) bool
    need_stdin* = (self :: @Self) ()
    uses_stdin* = (self: @Self) bool
    need_env* = (self :: @Self) ()
    uses_env* = (self: @Self) bool
    need_clock* = (self :: @Self) ()
    uses_clock* = (self: @Self) bool
    need_threads* = (self :: @Self) ()
    uses_threads* = (self: @Self) bool
    need_spawn* = (self :: @Self) ()
    uses_spawn* = (self: @Self) bool
    next_spawn* = (self :: @Self) usize
    add_spawn_env* = (self :: @Self, text: String) Res<(), AllocError>
    spawn_env_count* = (self: @Self) usize
    spawn_env_at* = (self: @Self, i: usize) Res<String>
    need_actor* = (self :: @Self) ()
    uses_actor* = (self: @Self) bool
    next_actor_site* = (self :: @Self) usize
    add_actor_def* = (self :: @Self, text: String) Res<(), AllocError>
    actor_def_count* = (self: @Self) usize
    actor_def_at* = (self: @Self, i: usize) Res<String>
    need_scope* = (self :: @Self) ()
    uses_scope* = (self: @Self) bool
    next_defer* = (self :: @Self) usize
    add_defer_env* = (self :: @Self, text: String, n: usize)
                     Res<(), AllocError>
    defer_env_count* = (self: @Self) usize
    defer_env_at* = (self: @Self, i: usize) Res<String>
    defer_env_id* = (self: @Self, i: usize) usize
    open_block* = (self :: @Self, rec: usize) Res<(), AllocError>
    close_block* = (self :: @Self) Res<(), AllocError>
    forget_drops = (self :: @Self, mark: usize) Res<(), AllocError>
    block_depth* = (self: @Self) usize
    block_at* = (self: @Self, i: usize) Res<BlockFrame>
    hold_cleanup* = (self :: @Self) Res<Cleanup, AllocError>
    restore_cleanup* = (self :: @Self, held: Cleanup) ()
    drop_count* = (self: @Self) usize
    drop_at* = (self: @Self, i: usize) Res<DropEntry>
    own_binding* = (self :: @Self, e: DropEntry) Res<(), AllocError>
    write* = (self :: @Self, s: str) Res<(), AllocError>
    writeln* = (self :: @Self, s: str) Res<(), AllocError>
    fmt* = (self :: @Self, fmt: str, args: ...) Res<(), AllocError>
    newline* = (self :: @Self) Res<(), AllocError>
    indent* = (self :: @Self) ()
    dedent* = (self :: @Self) ()
    text* = (self: @Self) str
    set_line* = (self :: @Self, dst: str, value: str) Res<(), AllocError>
    open_buf* = (self :: @Self) Res<(), AllocError>
    take_buf* = (self :: @Self) Res<Emit, AllocError>
    put_buf* = (self :: @Self, held: Emit) ()
    need_function* = (self :: @Self, d: Def, inst: Inst, sym: str)
                     Res<(), AllocError>
    seen_function = (self: @Self, sym: str) bool
    enable_ffi* = (self :: @Self) ()
    need_extern* = (self :: @Self, name: str, proto: String)
                   Res<bool, AllocError>
    need_c_header* = (self :: @Self, path: str, system: bool)
                     Res<bool, AllocError>
    keep_c_header = (self :: @Self, path: str, system: bool)
                    Res<bool, AllocError>
    need_method* = (self :: @Self, m: MethodRef, inst: Inst, sym: str)
                   Res<(), AllocError>
    need_thunk* = (self :: @Self, sym: str) Res<bool, AllocError>
    claim_thunk = (self :: @Self, sym: str) Res<bool, AllocError>
    push_method = (self :: @Self, m: MethodRef, inst: Inst, sym: str)
                  Res<(), AllocError>
    push_function = (self :: @Self, d: Def, inst: Inst, sym: str)
                    Res<(), AllocError>
    remember = (self :: @Self, sym: str) Res<(), AllocError>
    queued_inst* = (self: @Self, i: usize) Res<Inst>
    queued_m_inst* = (self: @Self, i: usize) Res<Inst>
    enter_inst* = (self :: @Self, inst: Inst) ()
    add_function* = (self :: @Self, name: String, proto: String,
                     body: String) Res<(), AllocError>
    add_source_function* = (self :: @Self, name: String, proto: String,
                            body: String, span: Span) Res<(), AllocError>
    keep_function = (self :: @Self, name: String, proto: String,
                     body: String, origin: FnOrigin) Res<(), AllocError>
    origin_of* = (self: @Self, i: usize) FnOrigin
    enter_unit* = (self :: @Self, mi: usize) ()
    unit_of* = (self: @Self, i: usize) usize
    use_externs* = (self :: @Self) ()
    linkage* = (self: @Self) str
    mark* = (self: @Self) usize
    release* = (self :: @Self, mark: usize) Res<(), AllocError>
    declare* = (self :: @Self, name: str, ty: TyId, by_ref: bool)
               Res<usize, AllocError>
    reserve* = (self :: @Self, name: str) Res<usize, AllocError>
    publish* = (self :: @Self, name: str, n: usize, ty: TyId, by_ref: bool)
               Res<(), AllocError>
    declare_closure* = (self :: @Self, name: str, cl: Closure)
                       Res<(), AllocError>
    closure_at* = (self: @Self, i: usize) Res<Closure>
    detach* = (self :: @Self, mark: usize, saved :: Vec<LocalSlot>)
              Res<(), AllocError>
    reattach* = (self :: @Self, saved: Vec<LocalSlot>) Res<(), AllocError>
    enter_frame* = (self :: @Self, floor: usize) ()
    enter_call* = (self :: @Self) ()
    leave_call* = (self :: @Self) ()
    declare_handle* = (self :: @Self, name: str, ty: TyId, depth: usize)
                      Res<(), AllocError>
    push_loop* = (self :: @Self, frame: LoopFrame) Res<(), AllocError>
    pop_loop* = (self :: @Self) Res<(), AllocError>
    loop_depth* = (self: @Self) usize
    loop_frame* = (self: @Self, depth: usize) Res<LoopFrame>
    declared_count = (self: @Self, name: str) usize
    slot_of* = (self: @Self, name: str) Res<LocalSlot>
    bound_in_frame* = (self: @Self, name: str) bool
    reset_frame* = (self :: @Self) Res<(), AllocError>
    next_tmp* = (self :: @Self) usize
    fresh_name* = (self :: @Self, stem: str) Res<String, AllocError>
}
```

#### Enums

```zen
FnOrigin* = Generated | Source(Span)
```

#### Functions

```zen
valid_c_header = (path: str) bool

CBackend* = (a: Alloc, tree: Ast, check: Checker) Res<CBackend, AllocError>
```

#### Imports and re-exports

```zen
Ast, ExprId, Span = std.ast

str, String = std.text

Alloc, AllocError = std.mem

Vec = std.collections

Range = std.core

DeclId = sema.sema_id

TyId, Types = sema.sema_ty

World, Def = sema.sema_def

Checker = sema.sema_check

Inst = sema.sema_inst

Emit = gen.gen_emit

GenDiag, GenFault, render_gen = gen.gen_diag

sym_gen = gen.gen_name

LocalSlot, Closure, LoopFrame, DropEntry, BlockFrame = gen.gen_c.gen_c_frame
```

### `src/gen/gen_c/gen_c_stdin.zen`

26 declarations (functions: 11, imports and re-exports: 15).

#### Functions

```zen
emit_stdin* = (be :: CBackend, out :: Emit) Res<(), AllocError>

write_stdin = (out :: Emit) Res<(), AllocError>

lower_stdin_read* = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    ret : TyId,
    aty : TyId,
    ctx : Ctx,
    out :: String
)
                   Res<(), AllocError>

declare_pointer = (be :: CBackend, ty: TyId, name: str)
                  Res<(), AllocError>

hold_buffer = (be :: CBackend, c: Call, aty: TyId, ctx: Ctx, buf: str)
              Res<(), AllocError>

hold_count = (be :: CBackend, c: Call, usize_ty: TyId, ctx: Ctx, want: str)
             Res<(), AllocError>

write_stdin_call = (be :: CBackend, rc: str, buf: str, want: str, got: str)
                   Res<(), AllocError>

advance_len = (be :: CBackend, buf: str, got: str) Res<(), AllocError>

arrow = (ptr: str, name: str, out :: String) Res<(), AllocError>

io_chain = (be :: CBackend, ret: TyId, rc: str, dst: str)
           Res<(), AllocError>

open_full_test = (be :: CBackend, rc: str) Res<(), AllocError>
```

#### Imports and re-exports

```zen
ExprId = std.ast

Call = std.ast

AllocError = std.mem

str, String = std.text

TyId = sema.sema_ty

Ctx = sema.sema_check

sym_member = gen.gen_name

Emit = gen.gen_emit

CBackend = gen.gen_c.gen_c_state

ctype, request_type = gen.gen_c.gen_c_type

declare_temp = gen.gen_c.gen_c_flow

comment = gen.gen_c.gen_c_runtime

close_else, close_brace, open_rc_test = gen.gen_c.gen_c_flow

arg_text = gen.gen_c.gen_c_arg

write_assign_ok, write_assign_err = gen.gen_c.gen_c_flow
```

### `src/gen/gen_c/gen_c_stmt.zen`

68 declarations (enums: 1, functions: 48, imports and re-exports: 19).

#### Enums

```zen
Dest* = Discard | Return | Into(str)
```

#### Functions

```zen
block* = (be :: CBackend, id: BlockId, ctx: Ctx, want: TyId, dst: Dest)
         Res<(), AllocError>

tail_index = (blk: Block, dst: Dest) usize

stmt_tail = (blk: Block, dst: Dest) usize

value_stmt_index = (blk: Block) usize

last_expr_index = (blk: Block) usize

wants_value* = (dst: Dest) bool

close_block = (
    be   :: CBackend,
    blk  : Block,
    ctx  : Ctx,
    want : TyId,
    dst  : Dest,
    tail : usize
) Res<(), AllocError>

has_cleanup = (be :: CBackend) bool

frame_has_cleanup = (be :: CBackend) bool

plain_close = (
    be   :: CBackend,
    blk  : Block,
    ctx  : Ctx,
    want : TyId,
    dst  : Dest,
    tail : usize
) Res<(), AllocError>

cleaned_close = (
    be   :: CBackend,
    blk  : Block,
    ctx  : Ctx,
    want : TyId,
    dst  : Dest,
    tail : usize
) Res<(), AllocError>

returning_close = (
    be   :: CBackend,
    blk  : Block,
    ctx  : Ctx,
    want : TyId,
    tail : usize
) Res<(), AllocError>

unit_return = (
    be   :: CBackend,
    blk  : Block,
    ctx  : Ctx,
    want : TyId,
    tail : usize
) Res<(), AllocError>

spilled_return = (
    be   :: CBackend,
    blk  : Block,
    ctx  : Ctx,
    want : TyId,
    tail : usize
) Res<(), AllocError>

keep_name = (be :: CBackend, blk: Block, tail: usize) str

tail_stmt_name = (be :: CBackend, blk: Block, tail: usize) str

stmt_at_name = (be :: CBackend, blk: Block, tail: usize) str

stmt_value_name = (be :: CBackend, s: Stmt) str

nested_keep_name = (be :: CBackend, id: BlockId) str

bare_name* = (be :: CBackend, id: ExprId) str

close_value = (
    be   :: CBackend,
    blk  : Block,
    ctx  : Ctx,
    want : TyId,
    dst  : Dest,
    tail : usize
) Res<(), AllocError>

close_tail = (
    be   :: CBackend,
    blk  : Block,
    ctx  : Ctx,
    want : TyId,
    dst  : Dest,
    tail : usize
) Res<(), AllocError>

deliver_stmt = (
    be   :: CBackend,
    blk  : Block,
    ctx  : Ctx,
    want : TyId,
    dst  : Dest,
    tail : usize
) Res<(), AllocError>

deliver_expr_stmt = (
    be   :: CBackend,
    s    : Stmt,
    ctx  : Ctx,
    want : TyId,
    dst  : Dest
) Res<(), AllocError>

close_valueless = (be :: CBackend, dst: Dest) Res<(), AllocError>

deliver* = (be :: CBackend, id: ExprId, ctx: Ctx, want: TyId, dst: Dest)
           Res<(), AllocError>

deliver_spilling = (
    be   :: CBackend,
    id   : ExprId,
    ctx  : Ctx,
    want : TyId,
    dst  : Dest
) Res<(), AllocError>

destination_type* = (be :: CBackend, id: ExprId, ctx: Ctx, want: TyId)
                    Res<TyId, AllocError>

deliver_simple = (
    be   :: CBackend,
    id   : ExprId,
    ctx  : Ctx,
    want : TyId,
    dst  : Dest
) Res<(), AllocError>

write_dest* = (be :: CBackend, dst: Dest, text: str) Res<(), AllocError>

assign_line = (be :: CBackend, name: str, text: str) Res<(), AllocError>

return_line = (be :: CBackend, text: str) Res<(), AllocError>

discard_line = (be :: CBackend, text: str) Res<(), AllocError>

stmt* = (be :: CBackend, s: Stmt, ctx: Ctx) Res<(), AllocError>

lower_nested = (be :: CBackend, id: BlockId, ctx: Ctx) Res<(), AllocError>

lower_expr_stmt = (be :: CBackend, s: Stmt, id: ExprId, ctx: Ctx)
                  Res<(), AllocError>

lower_bind = (be :: CBackend, s: Stmt, b: Bind, ctx: Ctx)
             Res<(), AllocError>

bind_name = (be :: CBackend, name: str, b: Bind, ty: TyId, ctx: Ctx)
            Res<(), AllocError>

is_store = (be :: CBackend, name: str, b: Bind) bool

binding_type = (be :: CBackend, b: Bind, ctx: Ctx) Res<TyId, AllocError>

inferred_type = (be :: CBackend, b: Bind, ctx: Ctx, unknown: TyId)
                Res<TyId, AllocError>

settled_value_type = (be :: CBackend, b: Bind, ctx: Ctx, unknown: TyId)
                     Res<TyId, AllocError>

slot_type = (be :: CBackend, b: Bind) Res<TyId>

named_slot_type = (be :: CBackend, target: ExprId) Res<TyId>

declare_local = (be :: CBackend, name: str, b: Bind, ty: TyId, ctx: Ctx)
                Res<(), AllocError>

assign_target = (be :: CBackend, b: Bind, ty: TyId, ctx: Ctx)
                Res<(), AllocError>

store_plain = (be :: CBackend, b: Bind, ty: TyId, ctx: Ctx)
              Res<(), AllocError>

store_displacing = (
    be   :: CBackend,
    name : str,
    b    : Bind,
    ty   : TyId,
    ctx  : Ctx
) Res<(), AllocError>
```

#### Imports and re-exports

```zen
Expr, ExprId, BlockId, Block, Stmt, Bind = std.ast

Decl = std.ast

Match = std.ast

AllocError = std.mem

str, String = std.text

TyId = sema.sema_ty

Ctx = sema.sema_check

subst = sema.sema_inst

stmt_type = sema.sema_type

type_from_ast = sema.sema_denote

settled_array = sema.sema_place

sym_local = gen.gen_name

GenFault = gen.gen_diag

CBackend = gen.gen_c.gen_c_state

lower_match = gen.gen_c.gen_c_flow

lower_try = gen.gen_c.gen_c_try

declarator, is_unit, has_storage = gen.gen_c.gen_c_type

expr, ty_of, spills = gen.gen_c.gen_c_expr

enter_block, leave_block, note_drop, displace = gen.gen_c.gen_c_own
```

### `src/gen/gen_c/gen_c_threads.zen`

56 declarations (functions: 33, imports and re-exports: 23).

#### Functions

```zen
emit_threads* = (be :: CBackend, out :: Emit) Res<(), AllocError>

write_sleep = (be :: CBackend, out :: Emit) Res<(), AllocError>

emit_spawn_floor = (out :: Emit) Res<(), AllocError>

emit_spawn_envs* = (be :: CBackend, out :: Emit) Res<(), AllocError>

lower_sleep* = (
    be  :: CBackend,
    c   : Call,
    ret : TyId,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

lower_spawn* = (
    be  :: CBackend,
    id  : ExprId,
    c   : Call,
    ret : TyId,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

spawn_arg = (
    be  :: CBackend,
    id  : ExprId,
    g   : Arg,
    ret : TyId,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

spawn_lambda = (
    be  :: CBackend,
    id  : ExprId,
    l   : Lambda,
    ret : TyId,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

spawn_ret = (
    be  :: CBackend,
    id  : ExprId,
    l   : Lambda,
    ret : TyId,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

spawn_typed = (
    be  :: CBackend,
    id  : ExprId,
    l   : Lambda,
    rt  : TypeId,
    ret : TyId,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

spawn_res = (
    be  :: CBackend,
    id  : ExprId,
    l   : Lambda,
    rty : TyId,
    ret : TyId,
    ctx : Ctx,
    out :: String
) Res<(), AllocError>

spawn_env_name = (be :: CBackend, n: usize, out :: String)
                 Res<(), AllocError>

write_spawn_env = (be :: CBackend, n: usize, caps: Vec<LocalSlot>)
                  Res<(), AllocError>

write_spawn_struct = (be :: CBackend, n: usize, caps: Vec<LocalSlot>)
                     Res<(), AllocError>

write_spawn_field = (be :: CBackend, s: LocalSlot, text :: String)
                    Res<(), AllocError>

spawn_ref_field = (be :: CBackend, ty: TyId, name: str, text :: String)
                  Res<(), AllocError>

write_spawn_fn = (
    be   :: CBackend,
    n    : usize,
    l    : Lambda,
    caps : Vec<LocalSlot>,
    rty  : TyId,
    ctx  : Ctx
) Res<(), AllocError>

spawn_fn_proto = (
    be   :: CBackend,
    n    : usize,
    rty  : TyId,
    caps : Vec<LocalSlot>,
    out  :: String
) Res<(), AllocError>

spawn_fn_params = (be :: CBackend, n: usize, out :: String)
                  Res<(), AllocError>

write_spawn_prologue = (be :: CBackend, n: usize, caps: Vec<LocalSlot>)
                       Res<(), AllocError>

write_spawn_unpack = (be :: CBackend, caps: Vec<LocalSlot>)
                     Res<(), AllocError>

write_spawn_unpack_one = (be :: CBackend, s: LocalSlot)
                         Res<(), AllocError>

write_spawn_tramp = (be :: CBackend, n: usize, rty: TyId)
                    Res<(), AllocError>

write_spawn_call = (
    be   :: CBackend,
    n    : usize,
    caps : Vec<LocalSlot>,
    ret  : TyId,
    out  :: String
) Res<(), AllocError>

malloc_spawn_env = (
    be   :: CBackend,
    n    : usize,
    caps : Vec<LocalSlot>,
    rec  :: String
) Res<(), AllocError>

copy_spawn_capture = (be :: CBackend, s: LocalSlot, cell: str)
                     Res<(), AllocError>

write_spawn_ok = (be :: CBackend, ret: TyId, pt: str, dst: str)
                 Res<(), AllocError>

write_spawn_thread = (be :: CBackend, ret: TyId, tty: TyId, pt: str, dst: str)
                     Res<(), AllocError>

lower_join* = (
    be   :: CBackend,
    id   : ExprId,
    c    : Call,
    a    : Access,
    rty  : TyId,
    want : TyId,
    ctx  : Ctx,
    out  :: String
) Res<(), AllocError>

join_want = (be :: CBackend, id: ExprId, want: TyId, ctx: Ctx)
            Res<Res<TyId>, AllocError>

join_memo = (be :: CBackend, id: ExprId, ctx: Ctx)
            Res<Res<TyId>, AllocError>

join_res_ok = (be :: CBackend, t: TyId) bool

join_settled = (
    be   :: CBackend,
    a    : Access,
    rty  : TyId,
    want : TyId,
    ctx  : Ctx,
    out  :: String
) Res<(), AllocError>
```

#### Imports and re-exports

```zen
ExprId, Call, Arg, Lambda, Access, TypeId = std.ast

AllocError = std.mem

Vec = std.collections

str, String = std.text

Range = std.core

TyId = sema.sema_ty

Ctx = sema.sema_check

type_from_ast = sema.sema_denote

Emit = gen.gen_emit

sym_member, sym_gen, sym_local = gen.gen_name

CBackend = gen.gen_c.gen_c_state

LocalSlot = gen.gen_c.gen_c_frame

comment = gen.gen_c.gen_c_runtime

arg_text = gen.gen_c.gen_c_arg

unsupported = gen.gen_c.gen_c_report

spelled_lambda = gen.gen_c.gen_c_inline

captures = gen.gen_c.gen_c_scope

expr, want_of = gen.gen_c.gen_c_expr

ctype, declarator = gen.gen_c.gen_c_type

temp, payload_type = gen.gen_c.gen_c_flow

Dest, block = gen.gen_c.gen_c_stmt

write_assign_ok, write_assign_err = gen.gen_c.gen_c_flow

settled = gen.gen_c.gen_c_settle
```

### `src/gen/gen_c/gen_c_try.zen`

88 declarations (enums: 1, functions: 64, imports and re-exports: 23).

#### Enums

```zen
Carry = Same | Variant(str) | Member(TyId) | Copy | Retag
```

#### Functions

```zen
lower_try* = (
    be      :: CBackend,
    id      : ExprId,
    node    : Expr,
    operand : ExprId,
    error   : Res<ExprId>,
    ctx     : Ctx,
    want    : TyId,
    dst     : Dest
) Res<(), AllocError>

lower_try_res = (
    be      :: CBackend,
    id      : ExprId,
    node    : Expr,
    operand : ExprId,
    error   : Res<ExprId>,
    r       : TyRes,
    rt      : TyId,
    ctx     : Ctx,
    want    : TyId,
    dst     : Dest
) Res<(), AllocError>

write_guard = (
    be    :: CBackend,
    node  : Expr,
    error : Res<ExprId>,
    r     : TyRes,
    tmp   : str,
    ctx   : Ctx
)
              Res<(), AllocError>

map_and_propagate = (
    be   :: CBackend,
    node : Expr,
    map  : ExprId,
    r    : TyRes,
    tmp  : str,
    ctx  : Ctx
) Res<(), AllocError>

map_error = (
    be   :: CBackend,
    node : Expr,
    map  : ExprId,
    r    : TyRes,
    want : TyRes,
    tmp  : str,
    ctx  : Ctx
) Res<(), AllocError>

try_lambda = (be: CBackend, id: ExprId) Res<Lambda>

lower_try_mapper = (
    be     :: CBackend,
    l      : Lambda,
    from   : TyId,
    into   : TyId,
    tmp    : str,
    mapped : str,
    unit   : bool,
    ctx    : Ctx
) Res<(), AllocError>

bind_try_error = (be :: CBackend, p: Param, ty: TyId, tmp: str)
                 Res<(), AllocError>

write_mapped_return = (
    be     :: CBackend,
    want   : TyRes,
    mapped : str,
    unit   : bool,
    ctx    : Ctx
) Res<(), AllocError>

propagate = (be :: CBackend, node: Expr, r: TyRes, tmp: str, ctx: Ctx)
            Res<(), AllocError>

propagate_into = (
    be   :: CBackend,
    node : Expr,
    r    : TyRes,
    want : TyRes,
    tmp  : str,
    ctx  : Ctx
) Res<(), AllocError>

propagate_failure = (
    be   :: CBackend,
    node : Expr,
    r    : TyRes,
    want : TyRes,
    tmp  : str,
    ctx  : Ctx
) Res<(), AllocError>

propagate_error = (
    be   :: CBackend,
    node : Expr,
    r    : TyRes,
    want : TyRes,
    tmp  : str,
    ctx  : Ctx
) Res<(), AllocError>

propagate_wider = (
    be   :: CBackend,
    node : Expr,
    r    : TyRes,
    want : TyRes,
    tmp  : str,
    ctx  : Ctx
) Res<(), AllocError>

same_set = (be :: CBackend, got: TyId, want: TyId) bool

widen_or_report = (
    be   :: CBackend,
    node : Expr,
    r    : TyRes,
    want : TyRes,
    tmp  : str,
    ctx  : Ctx
) Res<(), AllocError>

widen_into_enum = (
    be   :: CBackend,
    node : Expr,
    r    : TyRes,
    want : TyRes,
    tmp  : str,
    ctx  : Ctx
) Res<(), AllocError>

widen_into_set = (
    be   :: CBackend,
    node : Expr,
    r    : TyRes,
    want : TyRes,
    tmp  : str,
    ctx  : Ctx
) Res<(), AllocError>

retag_or_report = (
    be   :: CBackend,
    node : Expr,
    r    : TyRes,
    want : TyRes,
    tmp  : str,
    ctx  : Ctx
) Res<(), AllocError>

retaggable = (be :: CBackend, from_set: TyId, to_set: TyId) bool

within = (be :: CBackend, from_set: TyId, to_set: TyId) bool

all_tagged = (be :: CBackend, from_set: TyId, to_set: TyId) bool

no_member_untagged = (
    be       :: CBackend,
    from_set : TyId,
    to_set   : TyId,
    members  : Vec<TyId>
) bool

untagged = (
    be       :: CBackend,
    from_set : TyId,
    to_set   : TyId,
    members  : Vec<TyId>
) Res<usize>

both_tagged = (be :: CBackend, from_set: TyId, to_set: TyId, m: TyId) bool

tagged = (be :: CBackend, set: TyId, m: TyId) bool

named_tagged = (be :: CBackend, set: TyId, m: TyId) bool

carrier* = (be :: CBackend, set: TyId, err: TyId) Res<str>

named_carrier = (be :: CBackend, n: TyNamed, err: TyId) Res<str>

decl_carrier = (be :: CBackend, n: TyNamed, d: Decl, err: TyId) Res<str>

variant_carrying = (
    be       :: CBackend,
    n        : TyNamed,
    variants : Vec<Variant>,
    err      : TyId
) Res<str>

collect_carrier = (
    be       :: CBackend,
    n        : TyNamed,
    variants : Vec<Variant>,
    err      : TyId,
    found    :: Vec<str>
) Res<(), AllocError>

keep_carrier = (
    be    :: CBackend,
    n     : TyNamed,
    v     : Variant,
    err   : TyId,
    ctx   : Ctx,
    inst  : Inst,
    found :: Vec<str>
)
               Res<(), AllocError>

carries = (
    be   :: CBackend,
    n    : TyNamed,
    v    : Variant,
    err  : TyId,
    ctx  : Ctx,
    inst : Inst
) bool

forms_agree = (got: ResForm, want: ResForm) bool

report_widening = (be :: CBackend, node: Expr) Res<(), AllocError>

write_propagation = (
    be   :: CBackend,
    r    : TyRes,
    want : TyRes,
    tmp  : str,
    ctx  : Ctx,
    into : Carry
) Res<(), AllocError>

write_built = (
    be   :: CBackend,
    r    : TyRes,
    want : TyRes,
    tmp  : str,
    ctx  : Ctx,
    into : Carry
) Res<(), AllocError>

write_copy = (be :: CBackend, r: TyRes, tmp: str, ctx: Ctx)
             Res<(), AllocError>

write_retag = (be :: CBackend, r: TyRes, want: TyRes, tmp: str, ctx: Ctx)
              Res<(), AllocError>

write_return = (be :: CBackend, w: str) Res<(), AllocError>

write_payload_copy = (be :: CBackend, w: str, tmp: str) Res<(), AllocError>

read_payload = (v: str, out :: String) Res<(), AllocError>

read_tag = (v: str, out :: String) Res<(), AllocError>

write_tag_map = (
    be       :: CBackend,
    from_set : TyId,
    to_set   : TyId,
    w        : str,
    tmp      : str
) Res<(), AllocError>

open_switch = (be :: CBackend, tmp: str) Res<(), AllocError>

write_tag_case = (
    be       :: CBackend,
    from_set : TyId,
    to_set   : TyId,
    m        : TyId,
    w        : str
) Res<(), AllocError>

write_member_tag = (be :: CBackend, set: TyId, m: TyId, out :: String)
                   Res<(), AllocError>

write_variant_tag = (be :: CBackend, set: TyId, m: TyId, out :: String)
                    Res<(), AllocError>

write_named_tag = (be :: CBackend, set: TyId, v: str, out :: String)
                  Res<(), AllocError>

write_carrier_decl = (be :: CBackend, r: TyRes, w: str, ctx: Ctx)
                     Res<(), AllocError>

write_carrier_copy = (be :: CBackend, w: str, tmp: str)
                     Res<(), AllocError>

failure_tag = (be :: CBackend, r: TyRes, out :: String) Res<(), AllocError>

carry_error = (
    be   :: CBackend,
    want : TyRes,
    tmp  : str,
    into : Carry,
    out  :: String
) Res<(), AllocError>

write_err_init = (
    be   :: CBackend,
    want : TyRes,
    tmp  : str,
    into : Carry,
    out  :: String
) Res<(), AllocError>

read_error = (tmp: str, out :: String) Res<(), AllocError>

read_ok_payload = (tmp: str, out :: String) Res<(), AllocError>

wrap_error* = (
    be      :: CBackend,
    set     : TyId,
    variant : str,
    payload : str,
    out     :: String
) Res<(), AllocError>

wrap_set_error = (
    be     :: CBackend,
    set    : TyId,
    member : TyId,
    tmp    : str,
    out    :: String
) Res<(), AllocError>

set_qname = (be :: CBackend, set: TyId, out :: String) Res<(), AllocError>

unwrap = (
    be   :: CBackend,
    id   : ExprId,
    r    : TyRes,
    want : TyId,
    tmp  : str,
    ctx  : Ctx,
    dst  : Dest
) Res<(), AllocError>

write_unwrap = (be :: CBackend, tmp: str, dst: Dest) Res<(), AllocError>

write_hoisted_unwrap = (
    be      :: CBackend,
    want    : TyId,
    payload : TyId,
    tmp     : str,
    dst     : Dest
) Res<(), AllocError>

write_ok_init = (tmp: str, out :: String) Res<(), AllocError>
```

#### Imports and re-exports

```zen
Expr, ExprId, Decl, Enum, Variant, Lambda, Param, Paren = std.ast

AllocError = std.mem

Vec = std.collections

str, String = std.text

Range = std.core

TyId, TyNamed, TyRes, ResForm, is_failure = sema.sema_ty

decl_at = sema.sema_def

Ctx = sema.sema_check

Inst = sema.sema_inst

sym_member, sym_variant, sym_local = gen.gen_name

RES_PATH = gen.gen_name

sym_union_variant = gen.gen_name

GenFault = gen.gen_diag

CBackend = gen.gen_c.gen_c_state

enter_struct_tparams, leave_tparams = gen.gen_c.gen_c_mono

ctype, declarator, is_unit, variant_type, decl_ctx, decl_inst = gen.gen_c.gen_c_type

write_qname = gen.gen_c.gen_c_layout

Dest, write_dest, deliver, block = gen.gen_c.gen_c_stmt

res_type_of = gen.gen_c.gen_c_expr

needs_hoist = gen.gen_c.gen_c_hoist

write_set_value = gen.gen_c.gen_c_widen

declare_temp = gen.gen_c.gen_c_flow

unwind_to = gen.gen_c.gen_c_own
```

### `src/gen/gen_c/gen_c_type.zen`

81 declarations (functions: 62, imports and re-exports: 19).

#### Functions

```zen
ctype* = (be :: CBackend, id: TyId, out :: String) Res<(), AllocError>

maybe_ptr = (be :: CBackend, id: TyId, n: TyNamed, out :: String)
            Res<(), AllocError>

maybe_scope = (be :: CBackend, id: TyId, n: TyNamed, out :: String)
              Res<(), AllocError>

maybe_named_ctype = (be :: CBackend, id: TyId, n: TyNamed, out :: String)
                    Res<(), AllocError>

foreign_binding = (be: CBackend, n: TyNamed) Res<COpaque>

is_ptr_named* = (n: TyNamed) bool

is_scope_named* = (n: TyNamed) bool

pointee* = (be :: CBackend, id: TyId) Res<TyId>

res_value* = (be :: CBackend, id: TyId) Res<TyId>

is_res* = (be :: CBackend, id: TyId) bool

ptr_ctype = (be :: CBackend, n: TyNamed, out :: String)
            Res<(), AllocError>

elem_ctype = (be :: CBackend, t: TyId, out :: String) Res<(), AllocError>

write_opaque_ptr = (be :: CBackend, raw: COpaque, out :: String)
                   Res<(), AllocError>

write_elem_ctype = (be :: CBackend, t: TyId, out :: String)
                   Res<(), AllocError>

named_ctype = (be :: CBackend, id: TyId, out :: String) Res<(), AllocError>

declarator* = (be :: CBackend, id: TyId, name: str, out :: String)
              Res<(), AllocError>

spellable* = (be: CBackend, id: TyId) bool

named_spellable = (be: CBackend, n: TyNamed) bool

pointer_element_spellable = (be: CBackend, id: TyId) bool

has_storage* = (be: CBackend, id: TyId) bool

is_unit* = (be: CBackend, id: TyId) bool

c_prim* = (name: str) str

c_prim_known* = (name: str) bool

is_c_integer* = (name: str) bool

is_signed* = (name: str) bool

request_type* = (be :: CBackend, id: TyId) Res<(), AllocError>

request_defined = (be :: CBackend, id: TyId) Res<(), AllocError>

is_foreign_opaque = (be: CBackend, id: TyId) bool

is_scope_type* = (be :: CBackend, id: TyId) bool

ptr_element = (be :: CBackend, id: TyId) Res<TyId>

named_element = (n: TyNamed) Res<TyId>

queue_definition = (be :: CBackend, id: TyId) Res<(), AllocError>

close_types* = (be :: CBackend) Res<(), AllocError>

request_children = (be :: CBackend, i: usize) Res<(), AllocError>

request_members = (be :: CBackend, id: TyId) Res<(), AllocError>

request_union_members = (be :: CBackend, members: Vec<TyId>)
                        Res<(), AllocError>

request_named_members = (be :: CBackend, n: TyNamed, id: TyId)
                        Res<(), AllocError>

request_res_members = (be :: CBackend, r: TyRes) Res<(), AllocError>

request_if_composite = (be :: CBackend, id: TyId) Res<(), AllocError>

request_if_named = (be :: CBackend, id: TyId) Res<(), AllocError>

request_decl_members = (be :: CBackend, n: TyNamed) Res<(), AllocError>

request_from_decl = (be :: CBackend, n: TyNamed, d: Decl)
                    Res<(), AllocError>

decl_inst* = (be :: CBackend, n: TyNamed) Res<Inst, AllocError>

request_fields = (
    be      :: CBackend,
    members : Vec<Member>,
    ctx     : Ctx,
    inst    : Inst
) Res<(), AllocError>

request_variants = (
    be       :: CBackend,
    n        : TyNamed,
    variants : Vec<Variant>,
    ctx      : Ctx,
    inst     : Inst
) Res<(), AllocError>

struct_decl* = (be: CBackend, decl: DeclId) Res<Struct>

decl_ctx* = (be :: CBackend, n: TyNamed) Ctx

declared_ret* = (be :: CBackend, f: Function, ctx: Ctx)
                Res<TyId, AllocError>

field_type* = (be :: CBackend, m: Member, ctx: Ctx, inst: Inst)
              Res<TyId>

variant_type* = (
    be   :: CBackend,
    n    : TyNamed,
    v    : Variant,
    ctx  : Ctx,
    inst : Inst
) Res<TyId>

union_member_type = (be :: CBackend, n: TyNamed, v: Variant) Res<TyId>

bare_variant_type = (be :: CBackend, n: TyNamed, v: Variant) Res<TyId>

named_of = (be :: CBackend, found: Vec<Def>) Res<TyId>

interned_named = (be :: CBackend, d: Def) Res<TyId>

resolved = (be :: CBackend, t: TypeId, ctx: Ctx, inst: Inst) Res<TyId>

substituted = (be :: CBackend, id: TyId, inst: Inst) Res<TyId>

field_of* = (be :: CBackend, ty: TyId, name: str)
            Res<Res<TyId>, AllocError>

named_field_of = (be :: CBackend, n: TyNamed, name: str)
                 Res<Res<TyId>, AllocError>

collect_field = (
    be   :: CBackend,
    d    : Decl,
    name : str,
    ctx  : Ctx,
    inst : Inst,
    out  :: Vec<TyId>
) Res<(), AllocError>

keep_fields = (
    be   :: CBackend,
    s    : Struct,
    name : str,
    ctx  : Ctx,
    inst : Inst,
    out  :: Vec<TyId>
) Res<(), AllocError>

keep_named_field = (
    be   :: CBackend,
    m    : Member,
    name : str,
    ctx  : Ctx,
    inst : Inst,
    out  :: Vec<TyId>
) Res<(), AllocError>

add_field_type = (
    be   :: CBackend,
    m    : Member,
    ctx  : Ctx,
    inst : Inst,
    out  :: Vec<TyId>
) Res<(), AllocError>
```

#### Imports and re-exports

```zen
Decl, Struct, Enum, Variant, Member = std.ast

COpaque, CTypeBinding = std.ast

Function, TypeId = std.ast

AllocError = std.mem

Vec = std.collections

str, String = std.text

Range = std.core

TyId, TyNamed, TyRes, c_integer, is_failure = sema.sema_ty

DeclId = sema.sema_id

Def, decl_at = sema.sema_def

Ctx = sema.sema_check

type_from_ast = sema.sema_denote

union_reading = sema.sema_union

sym_type, is_c_identifier = gen.gen_name

CBackend = gen.gen_c.gen_c_state

Inst = sema.sema_inst

sub_with, enter_struct_tparams, leave_tparams = gen.gen_c.gen_c_mono

intern_named = gen.gen_c.gen_c_mono

request_slots = gen.gen_c.gen_c_fat
```

### `src/gen/gen_c/gen_c_widen.zen`

29 declarations (functions: 17, imports and re-exports: 12).

#### Functions

```zen
needs_widen* = (be :: CBackend, id: ExprId, ctx: Ctx, want: TyId)
               Res<bool, AllocError>

widens_into = (be :: CBackend, id: ExprId, ctx: Ctx, want: TyId, w: TyRes)
              Res<bool, AllocError>

settled = (be :: CBackend, cty: TyId) bool

res_widens = (be :: CBackend, cty: TyId, want: TyId, w: TyRes) bool

res_parts_widen = (be :: CBackend, cty: TyId, w: TyRes) bool

parts_widen = (be :: CBackend, g: TyRes, w: TyRes) bool

error_widens = (be :: CBackend, g: TyRes, w: TyRes) bool

member_reaches_set = (be :: CBackend, got: TyId, want: TyId) bool

is_set = (be :: CBackend, ty: TyId) bool

widen_expr* = (
    be   :: CBackend,
    id   : ExprId,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

needs_set* = (be :: CBackend, id: ExprId, ctx: Ctx, want: TyId)
            Res<bool, AllocError>

member_reaches_set = (
    be   :: CBackend,
    id   : ExprId,
    ctx  : Ctx,
    want : TyId,
    wide : TyId
) Res<bool, AllocError>

settled_member = (be: CBackend, cty: TyId, want: TyId, wide: TyId) bool

variant_carries = (be: CBackend, want: TyId, member: TyId) bool

is_named_or_res = (be: CBackend, cty: TyId) bool

set_expr* = (
    be   :: CBackend,
    id   : ExprId,
    ctx  : Ctx,
    want : TyId,
    out  :: String
) Res<(), AllocError>

write_set_value* = (
    be     :: CBackend,
    code   : str,
    member : TyId,
    set    : TyId,
    out    :: String
) Res<(), AllocError>
```

#### Imports and re-exports

```zen
ExprId = std.ast

AllocError = std.mem

str, String = std.text

TyId, TyRes, is_failure = sema.sema_ty

Ctx = sema.sema_check

CBackend = gen.gen_c.gen_c_state

expr, ty_of, value_expr = gen.gen_c.gen_c_expr

convert = gen.gen_c.gen_c_bound

carrier, wrap_error = gen.gen_c.gen_c_try

ctype = gen.gen_c.gen_c_type

sym_union_variant, sym_union_member = gen.gen_name

has_var = sema.sema_inst
```

### `src/gen/gen_diag.zen`

10 declarations (types: 1, enums: 1, functions: 5, imports and re-exports: 3).

#### Types

```zen
GenDiag* = {
    file*: str,
    span*: Span,
    fault*: GenFault,
}
```

#### Enums

```zen
GenFault* = Unsupported(str)
          | Unresolved(str)
          | Ambiguous(str)
          | Untyped(str)
          | Unspellable(str)
          | Overrun(usize)
```

#### Functions

```zen
render_gen* = (d: GenDiag, out :: String) Res<(), AllocError>

message* = (fault: GenFault) str

detail* = (fault: GenFault, out :: String) Res<(), AllocError>

write_quoted = (out :: String, w: str) Res<(), AllocError>

write_bound = (out :: String, n: usize) Res<(), AllocError>
```

#### Imports and re-exports

```zen
Span = std.ast.ast_span

str, String = std.text

AllocError = std.mem
```

### `src/gen/gen_emit.zen`

17 declarations (types: 1, functions: 10, constants: 1, imports and re-exports: 5).

#### Types

```zen
Emit* = {
    text :: String,
    depth :: usize,
    fresh :: bool,
    bytes* = (self :: @Self, s: str) Res<(), AllocError>
    run = (self :: @Self, s: str) Res<(), AllocError>
    open_run = (self :: @Self, s: str) Res<(), AllocError>
    byte* = (self :: @Self, b: u8) Res<(), AllocError>
    open_byte = (self :: @Self, b: u8) Res<(), AllocError>
    number* = (self :: @Self, v: usize) Res<(), AllocError>
    line* = (self :: @Self) Res<(), AllocError>
    say* = (self :: @Self, s: str) Res<(), AllocError>
    open_line = (self :: @Self) Res<(), AllocError>
    write_indent = (self :: @Self) Res<(), AllocError>
    indent* = (self :: @Self) ()
    dedent* = (self :: @Self) ()
    view* = (self: @Self) str
    len* = (self: @Self) usize
    into_string* = (self: @Self) String
}
```

#### Functions

```zen
Emit* = (a: Alloc) Res<Emit, AllocError>

order* = (a: Alloc, keys: Vec<String>) Res<Vec<usize>, AllocError>

merge_pass = (
    src   : Vec<usize>,
    dst   :: Vec<usize>,
    keys  : Vec<String>,
    width : usize
)
             Res<(), AllocError>

smaller = (a: usize, b: usize) usize

merge_run = (
    src   : Vec<usize>,
    dst   :: Vec<usize>,
    keys  : Vec<String>,
    start : usize,
    mid   : usize,
    end   : usize
) Res<(), AllocError>

right_first = (
    src   : Vec<usize>,
    keys  : Vec<String>,
    left  : usize,
    mid   : usize,
    right : usize,
    end   : usize
) bool

copy_order = (src: Vec<usize>, dst :: Vec<usize>) Res<(), AllocError>

earlier = (keys: Vec<String>, i: usize, j: usize) bool

view_at = (keys: Vec<String>, i: usize) str

put = (out :: Vec<usize>, i: usize, v: usize) Res<(), AllocError>
```

#### Constants

```zen
INDENT* : usize = 4
```

#### Imports and re-exports

```zen
Alloc, AllocError = std.mem

str, String = std.text

Vec = std.collections

Range = std.core

before = std.text
```

### `src/gen/gen_name.zen`

48 declarations (functions: 36, constants: 3, imports and re-exports: 9).

#### Functions

```zen
comp* = (out :: String, name: str) Res<(), AllocError>

plain_comp = (out :: String, name: str) Res<(), AllocError>

escaped_comp = (out :: String, name: str) Res<(), AllocError>

is_c_identifier* = (name: str) bool

write_count = (out :: String, n: usize) Res<(), AllocError>

count* = (out :: String, n: usize) Res<(), AllocError>

path* = (out :: String, qname: str) Res<(), AllocError>

path_with* = (out :: String, qname: str, tail: str) Res<(), AllocError>

segments* = (qname: str) usize

write_segments = (out :: String, qname: str) Res<(), AllocError>

qualify* = (out :: String, scope: str, leaf: str) Res<(), AllocError>

sym_type* = (out :: String, a: Alloc, types: Types, world: World, id: TyId)
            Res<(), AllocError>

type_stem = (out :: String, types: Types, id: TyId) Res<(), AllocError>

prefix_of = (types: Types, id: TyId) str

sym_fn* = (
    out   :: String,
    types : Types,
    world : World,
    qname : str,
    sig   : Vec<TyId>,
    inst  : Inst
) Res<(), AllocError>

write_targs = (out :: String, types: Types, world: World, inst: Inst)
              Res<(), AllocError>

write_targ = (
    out   :: String,
    types : Types,
    world : World,
    inst  : Inst,
    i     : usize
) Res<(), AllocError>

sym_variant* = (out :: String, qname: str, variant: str)
               Res<(), AllocError>

sym_member* = (out :: String, name: str) Res<(), AllocError>

sym_union_variant* = (
    out    :: String,
    types  : Types,
    world  : World,
    set    : TyId,
    member : TyId
) Res<(), AllocError>

sym_union_member* = (
    out    :: String,
    types  : Types,
    world  : World,
    member : TyId
) Res<(), AllocError>

sym_union_member_gen = (
    out    :: String,
    types  : Types,
    world  : World,
    member : TyId
) Res<(), AllocError>

sym_local* = (out :: String, name: str, n: usize) Res<(), AllocError>

write_shadow = (out :: String, n: usize) Res<(), AllocError>

sym_value* = (out :: String, qname: str) Res<(), AllocError>

sym_gen* = (out :: String, stem: str, n: usize) Res<(), AllocError>

tcode* = (out :: String, types: Types, world: World, id: TyId)
         Res<(), AllocError>

tcode_prim = (out :: String, name: str) Res<(), AllocError>

tcode_scalar = (out :: String, name: str) Res<(), AllocError>

tcode_of_named = (out :: String, types: Types, world: World, n: TyNamed)
                 Res<(), AllocError>

tcode_res = (out :: String, types: Types, world: World, r: TyRes)
            Res<(), AllocError>

tcode_array = (out :: String, types: Types, world: World, a: TyArray)
              Res<(), AllocError>

tcode_fn = (
    out    :: String,
    types  : Types,
    world  : World,
    params : Vec<TyId>,
    ret    : TyId
) Res<(), AllocError>

tcode_list = (out :: String, types: Types, world: World, items: Vec<TyId>)
             Res<(), AllocError>

tcode_section = (
    out   :: String,
    types : Types,
    world : World,
    tag   : str,
    items : Vec<TyId>
) Res<(), AllocError>

write_module_segments = (out :: String, world: World, decl: DeclId)
                        Res<(), AllocError>
```

#### Constants

```zen
USR* : str = "zu_"

GEN* : str = "zg_"

RES_PATH* : str = "std.core.result.Res"
```

#### Imports and re-exports

```zen
str, String = std.text

Vec = std.collections

Alloc, AllocError = std.mem

Hasher, Range = std.core

TyId, Types, TyNamed, TyRes, TyArray = sema.sema_ty

res_arity, is_failure = sema.sema_ty

World = sema.sema_def

DeclId = sema.sema_id

Inst = sema.sema_inst
```

### `src/lsp/lsp.zen`

22 declarations (imports and re-exports: 22).

#### Imports and re-exports

```zen
WirePos*, WireRange*, LineRun*, Step*, to_pos*, to_wire*, run_of*, step_at* = lsp.lsp_pos

write_wire*, write_range*, write_whole*, wire_at*, units_of* = lsp.lsp_pos

wire_range*, whole_range* = lsp.lsp_pos

Envelope*, FrameFault*, frame_at*, write_frame* = lsp.lsp_frame

short_by* = lsp.lsp_frame

Tell*, TypeAt*, ValueAt*, told_at*, is_nothing* = std.ast.ast_named

Hover*, hover_at*, hover_in*, hover_with*, no_type* = lsp.lsp_hover

Target*, Defn*, definition_at*, definition_in* = lsp.lsp_def

definition_with*, no_target*, write_location* = lsp.lsp_def

Sym*, symbols_at*, write_symbols* = lsp.lsp_symbol

write_edits* = lsp.lsp_fmt

Item*, Trigger*, DUMMY*, complete_at*, complete_in* = lsp.lsp_compl

complete_shared*, sort_items*, write_items* = lsp.lsp_compl

FILE_SCHEME*, path_of*, uri_at* = lsp.lsp_uri

Built* = lsp.lsp_built

Spot*, Diagnostics*, Shared*, publish*, ERROR* = lsp.lsp_diag

write_capabilities*, SEMANTIC_TOKENS* = lsp.lsp_reply

Colour*, Classed*, index_of*, name_of*, colour_of* = lsp.lsp_colour

write_legend*, write_tokens*, sort_classes* = lsp.lsp_colour

classify* = lsp.lsp_names

Server*, serve* = lsp.lsp_serve

Drain*, serve_stdio* = lsp.lsp_stdio
```

### `src/lsp/lsp_action.zen`

24 declarations (types: 2, functions: 9, imports and re-exports: 13).

#### Types

```zen
Action = { name: str, module: str }

ActionTextEdit = {
    range: WireRange,
    newText: str,
}
```

#### Functions

```zen
write_actions* = (
    c    : Checker,
    t    : Alloc,
    file : str,
    text : str,
    uri  : str,
    sl   : usize,
    sc   : usize,
    el   : usize,
    ec   : usize,
    out  :: String
) Res<(), AllocError>

offer = (
    c     : Checker,
    t     : Alloc,
    file  : str,
    d     : Diag,
    from  : Pos,
    upto  : Pos,
    found :: Vec<Action>
) Res<(), AllocError>

offer_name = (c: Checker, t: Alloc, name: str, found :: Vec<Action>)
             Res<(), AllocError>

offer_def = (
    c     : Checker,
    t     : Alloc,
    name  : str,
    d     : Def,
    found :: Vec<Action>,
    seen  :: Vec<str>
)
            Res<(), AllocError>

offer_at = (
    c     : Checker,
    t     : Alloc,
    name  : str,
    mi    : usize,
    table : ModuleTable,
    found :: Vec<Action>,
    seen  :: Vec<str>
) Res<(), AllocError>

covers = (span: Span, from: Pos, upto: Pos) bool

insert_at = (c: Checker, file: str, text: str) WirePos

write_offerings = (
    c     : Checker,
    t     : Alloc,
    file  : str,
    text  : str,
    uri   : str,
    found : Vec<Action>,
    out   :: String
) Res<(), AllocError>

write_action = (
    t    : Alloc,
    a    : Action,
    at   : WirePos,
    uri  : str,
    list :: Nest,
    out  :: String
) Res<(), AllocError>
```

#### Imports and re-exports

```zen
str, String = std.text

Vec = std.collections

Alloc, AllocError = std.mem

Range = std.core

Pos, Span = std.ast.ast_span

module_index_of = std.ast.ast_named

before = std.ast.ast_find

Checker = sema.sema_check

Diag = sema.sema_diag

Def, module_display = sema.sema_def

ModuleTable = sema.sema_def

to_pos, to_wire, WirePos, WireRange = lsp.lsp_pos

written, obj, arr, Nest, to_json = std.json
```

### `src/lsp/lsp_built.zen`

25 declarations (types: 3, implementations: 1, functions: 5, imports and re-exports: 16).

#### Types

```zen
Spot* = {
    uri*: str,
    message*: str,
    span*: Span,
    note*: Res<Note>,
}

Inner = {
    root: str,
    entry: str,
    b: Build,
    c: Checker,
    spots: Vec<Spot>,
    classed :: Map<str, Vec<Classed>>,
}

Built* = {
    arena :: Arena,
    cur :: Res<Inner>,
    stale :: bool = false,
    matches* = (self: @Self, root: str, entry: str) bool
    ensure* = (self :: @Self, env: Env, root: str, entry: str,
               uris: Vec<str>, docs: Map<str, str>) Res<(), AllocError>
    invalidate* = (self :: @Self) ()
    rebuild = (self :: @Self, env: Env, root: str, entry: str,
               uris: Vec<str>, docs: Map<str, str>) Res<(), AllocError>
    checker* = (self: @Self) Res<Checker>
    root* = (self: @Self) str
    spots* = (self: @Self) Res<Vec<Spot>>
    classed_for* = (self :: @Self, a: Alloc, uri: str)
                   Res<Vec<Classed>, AllocError>
}
```

#### Implementations

```zen
Built.impl(Drop, {
    drop = (self :: @Self) ()
})
```

#### Functions

```zen
Built* = (env: Env) Built

from_build = (b: Build, a: Alloc, root: str, spots :: Vec<Spot>)
             Res<(), AllocError>

add_parse = (
    a     : Alloc,
    root  : str,
    said  : str,
    span  : Span,
    note  : Res<Note>,
    spots :: Vec<Spot>
) Res<(), AllocError>

from_check = (c : Checker, a: Alloc, root: str, spots :: Vec<Spot>)
             Res<(), AllocError>

add_sema = (
    c     : Checker,
    a     : Alloc,
    root  : str,
    file  : str,
    span  : Span,
    fault : SemaFault,
    spots :: Vec<Spot>
) Res<(), AllocError>
```

#### Imports and re-exports

```zen
str, String = std.text

Vec, Map = std.collections

Alloc, AllocError, Arena = std.mem

Range = std.core

Span = std.ast.ast_span

Note = std.parse.parse_diag

Checker = sema.sema_check

SemaFault, message, write_detail = sema.sema_diag

Build = zen.zen_build

Classed = lsp.lsp_colour

classify = lsp.lsp_names

uri_at, path_of = lsp.lsp_uri

own_str = lsp.lsp_reply

written = std.json

relative_to = zen.zen_path

check_workspace = lsp.lsp_query
```

### `src/lsp/lsp_colour.zen`

24 declarations (types: 2, enums: 1, implementations: 1, functions: 13, imports and re-exports: 7).

#### Types

```zen
Painter = {
    line :: usize,
    character :: usize,
    source_at :: usize,
    source_units :: usize,
    put = (self :: @Self, line: usize, character: usize, length: usize,
           colour: Colour, runs :: Nest, out :: String) Res<(), AllocError>
    paint = (self :: @Self, text: str, token: Token, colour: Colour,
             runs :: Nest, out :: String) Res<(), AllocError>
    character_at = (self :: @Self, text: str, upto: usize) usize
    run = (self :: @Self, text: str, line: usize, character: usize,
           from: usize, upto: usize, colour: Colour, runs :: Nest,
           out :: String)
          Res<(), AllocError>
}

Classed* = {
    line*: usize,
    col*: usize,
    colour*: Colour,
}
```

#### Enums

```zen
Colour* = Keyword
    | Text
    | Number
    | Comment
    | Operator
    | Variable
    | Type
    | Function
    | Parameter
```

#### Implementations

```zen
Classed.impl(Ordered, {
    before = (self: @Self, other: @Self) bool
})
```

#### Functions

```zen
index_of* = (colour: Colour) usize

name_of* = (colour: Colour) str

write_legend* = (out :: String) Res<(), AllocError>

listed = (colour: Colour, types :: Nest, out :: String)
         Res<(), AllocError>

colour_of* = (kind: TokenKind) Res<Colour>

break_in = (text: str, from: usize, stop: usize) usize

classed_at = (names: Vec<Classed>, line: usize, col: usize) Res<Classed>

before_start = (cl: Classed, line: usize, col: usize) bool

is_start = (cl: Classed, line: usize, col: usize) bool

sort_classes* = (names :: Vec<Classed>) Res<(), AllocError>

write_tokens* = (
    a     : Alloc,
    name  : str,
    text  : str,
    names : Vec<Classed>,
    out   :: String
) Res<(), AllocError>

settled = (token: Token, lexical: Colour, names: Vec<Classed>) Colour

zero_based = (line: usize) usize
```

#### Imports and re-exports

```zen
str, String = std.text

Vec, Ordered = std.collections

Alloc, AllocError = std.mem

Range = std.core

scan, Source, Token, TokenKind = std.lex

write_text, written, obj, arr, Nest = std.json

step_at, units_of = lsp.lsp_pos
```

### `src/lsp/lsp_compl.zen`

50 declarations (types: 7, implementations: 2, functions: 13, constants: 10, imports and re-exports: 18).

#### Types

```zen
Item* = {
    label*: str,
    kind*: usize,
}

Trigger* = {
    text*: str,
    prefix*: str,
    dot*: bool,
}

MemberAnswer = {
    workspace : str,
    path      : str,
    patched   : str,
    items     : Vec<Item>,
}

MemberCache* = {
    arena :: Arena,
    cur   :: Res<MemberAnswer>,
    stale :: bool = false,
    builds* :: usize = 0,
    invalidate* = (self :: @Self) ()
    complete* = (
        self      :: @Self,
        env       : Env,
        a         : Alloc,
        workspace : str,
        path      : str,
        text      : str,
        line      : usize,
        character : usize,
        out       :: Vec<Item>
    ) Res<bool, AllocError>
    matches = (self: @Self, workspace: str, path: str, patched: str) bool
    refill = (self :: @Self, env: Env, workspace: str, path: str,
              patched: str) Res<(), AllocError>
    filtered = (self: @Self, prefix: str, out :: Vec<Item>)
               Res<(), AllocError>
}

Completion = {
    c    : Checker,
    a    : Alloc,
    file : str,
    add = (self :: @Self, trig: Trigger, out :: Vec<Item>)
          Res<(), AllocError>
    member_items = (self :: @Self, prefix: str, out :: Vec<Item>)
                   Res<(), AllocError>
    access_named = (self: @Self, name: str) Res<Access>
    base_items = (self :: @Self, ac: Access, prefix: str,
                  out :: Vec<Item>) Res<(), AllocError>
    named_base_items = (self :: @Self, base: str, prefix: str,
                        out :: Vec<Item>) Res<(), AllocError>
    items_of_type = (self :: @Self, ty: TyId, prefix: str,
                     out :: Vec<Item>) Res<(), AllocError>
    known_type_items = (self :: @Self, ty: TyId, prefix: str,
                        out :: Vec<Item>) Res<(), AllocError>
    collect_members = (self: @Self, ty: TyId, cands :: Vec<Item>)
                      Res<(), AllocError>
    collect_named = (self: @Self, n: TyNamed, cands :: Vec<Item>)
                    Res<(), AllocError>
    collect_impls = (self: @Self, n: TyNamed, cands :: Vec<Item>)
                    Res<(), AllocError>
    collect_impl = (self: @Self, name: str, iid: ImplId,
                    cands :: Vec<Item>) Res<(), AllocError>
    collect_prim = (self: @Self, name: str, cands :: Vec<Item>)
                   Res<(), AllocError>
    offers = (self: @Self, prefix: str, out :: Vec<Item>)
             Res<Offers, AllocError>
}

Offers = {
    completion : Completion,
    prefix     : str,
    seen       :: Map<str, bool>,
    items      :: Vec<Item>,
    scope_items = (self :: @Self) Res<(), AllocError>
    table_names = (self :: @Self, mi: usize, table: usize)
                  Res<(), AllocError>
    offer_global = (self :: @Self, mi: usize, name: str)
                   Res<(), AllocError>
    keyword_items = (self :: @Self) Res<(), AllocError>
    offer_member = (self :: @Self, ty: TyId, cand: Item)
                   Res<(), AllocError>
    visible = (self: @Self, ty: TyId, name: str)
              Res<bool, AllocError>
    offer = (self :: @Self, label: str, kind: usize)
            Res<(), AllocError>
    remember = (self :: @Self, item: Item) Res<(), AllocError>
    append_to = (self: @Self, out :: Vec<Item>) Res<(), AllocError>
    known = (self: @Self, label: str) bool
}

CompletionItem = {
    label: str,
    kind: usize,
}
```

#### Implementations

```zen
Item.impl(Ordered, {
    before = (self: @Self, other: @Self) bool
})

MemberCache.impl(Drop, {
    drop = (self :: @Self) ()
})
```

#### Functions

```zen
MemberCache* = (env: Env) MemberCache

complete_at* = (
    a         : Alloc,
    text      : str,
    line      : usize,
    character : usize,
    out       :: Vec<Item>
) Res<(), AllocError>

complete_in* = (
    env       : Env,
    a         : Alloc,
    workspace : str,
    path      : str,
    text      : str,
    line      : usize,
    character : usize,
    out       :: Vec<Item>
)
               Res<(), AllocError>

complete_shared* = (
    c         : Checker,
    a         : Alloc,
    rel       : str,
    text      : str,
    line      : usize,
    character : usize,
    out       :: Vec<Item>
)
                   Res<bool, AllocError>

items_from = (
    c    : Checker,
    a    : Alloc,
    file : str,
    trig : Trigger,
    out  :: Vec<Item>
) Res<(), AllocError>

trigger_at = (a: Alloc, text: str, line: usize, character: usize)
             Res<Trigger, AllocError>

patched = (a: Alloc, text: str, from: usize, offset: usize, upto: usize)
          Res<Trigger, AllocError>

no_access = () Access

member_names = (ms: Vec<Member>, cands :: Vec<Item>) Res<(), AllocError>

global_kind = (k: DefKind) usize

sort_items* = (items :: Vec<Item>) Res<(), AllocError>

write_items* = (a: Alloc, items: Vec<Item>, out :: String)
               Res<(), AllocError>

write_item = (a: Alloc, it: Item, offers :: Nest, out :: String)
             Res<(), AllocError>
```

#### Constants

```zen
METHOD*: usize = 2

FUNCTION*: usize = 3

FIELD*: usize = 5

CLASS*: usize = 7

ENUM*: usize = 13

KEYWORD*: usize = 14

ENUM_MEMBER*: usize = 20

CONSTANT*: usize = 21

STRUCT*: usize = 22

DUMMY*: str = "zen_wip"
```

#### Imports and re-exports

```zen
str, String = std.text

Vec, Map, Ordered = std.collections

Alloc, AllocError, Arena = std.mem

Range = std.core

ExprId, Access, Member, Impl, Ident, nowhere = std.ast

module_index_of = std.ast.ast_named

Checker = sema.sema_check

TyId, TyNamed = sema.sema_ty

Def, DefKind, decl_at = sema.sema_def

Found, members_of, first_hidden = sema.sema_member

Case, cases_of = sema.sema_case

def_type = sema.sema_type

ImplId = sema.sema_id

to_pos, run_of = lsp.lsp_pos

check_standalone, check_build = lsp.lsp_query

obj, arr, Nest, written, to_json = std.json

own_str = lsp.lsp_reply

KEYWORD_COUNT, keyword_at = std.lex
```

### `src/lsp/lsp_def.zen`

48 declarations (types: 3, functions: 28, imports and re-exports: 17).

#### Types

```zen
Target* = {
    found*: bool,
    uri*: str,
    start*: WirePos,
    end*: WirePos,
}

Location = {
    uri: str,
    range: WireRange,
}

Defn* = {
    found*: bool,
    span*: Span,
}
```

#### Functions

```zen
definition_at* = (
    a         : Alloc,
    uri       : str,
    text      : str,
    line      : usize,
    character : usize
) Res<Target, AllocError>

definition_in* = (
    env       : Env,
    a         : Alloc,
    workspace : str,
    path      : str,
    uri       : str,
    text      : str,
    line      : usize,
    character : usize
)
                 Res<Target, AllocError>

definition_with* = (
    env       : Env,
    c         : Checker,
    a         : Alloc,
    root      : str,
    docs      : Map<str, str>,
    uri       : str,
    text      : str,
    rel       : str,
    line      : usize,
    character : usize
)
                   Res<Target, AllocError>

placed = (
    env  : Env,
    a    : Alloc,
    root : str,
    docs : Res<Map<str, str>>,
    uri  : str,
    text : str,
    rel  : str,
    d    : Defn
) Res<Target, AllocError>

wired_target = (
    env  : Env,
    a    : Alloc,
    root : str,
    docs : Res<Map<str, str>>,
    uri  : str,
    text : str,
    rel  : str,
    span : Span
) Res<Target, AllocError>

disk_text = (env: Env, a: Alloc, path: str) str

sought = (c : Checker, a: Alloc, file: str, p: Pos) Res<Defn, AllocError>

import_module_defn = (c : Checker, a: Alloc, file: str, p: Pos)
                     Res<Defn, AllocError>

module_defn = (c : Checker, a: Alloc, q: QualifiedName)
              Res<Defn, AllocError>

type_defn = (c : Checker, a: Alloc, id: TypeId, file: str)
            Res<Defn, AllocError>

value_defn = (c : Checker, a: Alloc, id: ExprId, file: str, p: Pos)
             Res<Defn, AllocError>

name_defn = (c : Checker, a: Alloc, id: ExprId, text: str, file: str)
            Res<Defn, AllocError>

global_defn = (c : Checker, a: Alloc, text: str, file: str)
              Res<Defn, AllocError>

access_defn = (
    c    : Checker,
    a    : Alloc,
    id   : ExprId,
    ac   : Access,
    file : str,
    p    : Pos
) Res<Defn, AllocError>

member_defn = (c : Checker, a: Alloc, ac: Access, file: str)
              Res<Defn, AllocError>

static_defn = (c : Checker, a: Alloc, ac: Access, file: str)
              Res<Defn, AllocError>

typed_base_defn = (c : Checker, a: Alloc, base: str, name: str, file: str)
                  Res<Defn, AllocError>

variant_or_member = (c : Checker, a: Alloc, d: Def, name: str)
                    Res<Defn, AllocError>

variant_defn = (c : Checker, d: Def, name: str) Res<Span>

found_defn = (c : Checker, a: Alloc, ty: TyId, name: str)
             Res<Defn, AllocError>

called_decl = (c : Checker, id: ExprId) Res<DeclId>

callee_of = (c : Checker, eid: ExprId, id: ExprId) Res<DeclId>

decl_defn = (c : Checker, id: DeclId) Res<Defn, AllocError>

module_index = (c : Checker, file: str) Res<usize>

defn_of = (span: Span) Res<Defn, AllocError>

no_defn = () Res<Defn, AllocError>

no_target* = () Target

write_location* = (a: Alloc, t: Target, out :: String) Res<(), AllocError>
```

#### Imports and re-exports

```zen
str, String = std.text

Vec, Map = std.collections

Alloc, AllocError = std.mem

Range = std.core

ExprId, TypeId, Span, Pos, Access, Function, QualifiedName = std.ast

in_span, nowhere = std.ast

Checker = sema.sema_check

TyId = sema.sema_ty

Def, decl_at, dotted = sema.sema_def

def_type = sema.sema_type

DeclId = sema.sema_id

Found, members_of, first_found = sema.sema_member

to_pos, to_wire, WirePos, WireRange = lsp.lsp_pos

path_of, uri_at = lsp.lsp_uri

told_at, module_index_of = std.ast.ast_named

check_standalone, check_build = lsp.lsp_query

to_json = std.json
```

### `src/lsp/lsp_diag.zen`

32 declarations (types: 3, implementations: 1, functions: 14, constants: 1, imports and re-exports: 13).

#### Types

```zen
Diagnostic = {
    range: WireRange,
    severity: usize,
    source: str,
    message: str,
}

Shared* = {
    c*: Res<Checker>,
    root*: str,
}

Diagnostics* = {
    a: Alloc,
    owed :: str = "",
    showing :: Vec<str>,
    closing :: Vec<str>,
    built :: Built,
    fresh :: bool = false,
    said :: Map<str, str>,
    owes* = (self :: @Self, uri: str) ()
    stales* = (self :: @Self, uri: str) ()
    closed* = (self :: @Self, uri: str, next: str)
              Res<(), AllocError>
    classes_for* = (self :: @Self, t: Alloc, uri: str)
                   Res<Vec<Classed>, AllocError>
    shared* = (self :: @Self, env: Env, workspace: str, uris: Vec<str>,
               docs: Map<str, str>, path: str, t: Alloc)
              Res<Shared, AllocError>
    settled* = (self :: @Self, env: Env, workspace: str, uris: Vec<str>,
                docs: Map<str, str>, t: Alloc, out :: String)
               Res<(), AllocError>
    clear_closed = (self :: @Self, env: Env, t: Alloc, uris: Vec<str>,
                    docs: Map<str, str>, out :: String)
                   Res<(), AllocError>
    build_owed = (self :: @Self, env: Env, workspace: str, uris: Vec<str>,
                  docs: Map<str, str>, t: Alloc, out :: String)
                 Res<(), AllocError>
    told = (self :: @Self, env: Env, root: str, entry: str, uri: str,
            uris: Vec<str>, docs: Map<str, str>, t: Alloc, out :: String)
           Res<(), AllocError>
    say_all = (self :: @Self, env: Env, t: Alloc, uri: str, uris: Vec<str>,
               docs: Map<str, str>, spots: Vec<Spot>, out :: String)
              Res<(), AllocError>
    remember_showing = (self :: @Self, now: Vec<str>) Res<(), AllocError>
    say_one = (self :: @Self, env: Env, t: Alloc, uri: str, uris: Vec<str>,
               docs: Map<str, str>, spots: Vec<Spot>, out :: String)
              Res<(), AllocError>
    send = (self :: @Self, uri: str, body: String, out :: String)
           Res<(), AllocError>
    take_back = (self :: @Self, env: Env, t: Alloc, uri: str, now: Vec<str>,
                 uris: Vec<str>, docs: Map<str, str>, spots: Vec<Spot>,
                 out :: String) Res<(), AllocError>
}
```

#### Implementations

```zen
Diagnostics.impl(Drop, {
    drop = (self :: @Self) ()
})
```

#### Functions

```zen
Diagnostics* = (a: Alloc, env: Env) Diagnostics

gone = (u: str, uri: str, now: Vec<str>) bool

uris_of = (spots: Vec<Spot>, into :: Vec<str>) Res<(), AllocError>

text_of = (env: Env, t: Alloc, uri: str, docs: Map<str, str>) str

on_disk = (env: Env, t: Alloc, path: str) str

publish* = (a: Alloc, uri: str, text: str, spots: Vec<Spot>, out :: String)
           Res<(), AllocError>

write_notification = (
    a     : Alloc,
    uri   : str,
    text  : str,
    spots : Vec<Spot>,
    body  :: String
) Res<(), AllocError>

one_of = (a: Alloc, s: Spot, uri: str, text: str, items :: Nest, out :: String)
         Res<(), AllocError>

written_at = (a: Alloc, s: Spot, text: str, items :: Nest, out :: String)
             Res<(), AllocError>

write_spot = (a: Alloc, s: Spot, text: str, out :: String)
             Res<(), AllocError>

write_plain_spot = (a: Alloc, s: Spot, text: str, out :: String)
                   Res<(), AllocError>

write_noted_spot = (a: Alloc, s: Spot, text: str, out :: String)
                   Res<(), AllocError>

write_note = (
    a    : Alloc,
    s    : Spot,
    text : str,
    spot :: Nest,
    out  :: String
) Res<(), AllocError>

write_related = (
    a    : Alloc,
    uri  : str,
    n    : Note,
    text : str,
    spot :: Nest,
    out  :: String
)
                Res<(), AllocError>
```

#### Constants

```zen
ERROR*: usize = 1
```

#### Imports and re-exports

```zen
str, String = std.text

Vec, Map = std.collections

Alloc, AllocError = std.mem

Note = std.parse.parse_diag

Checker = sema.sema_check

root_for, relative_to = zen.zen_path

WireRange, wire_range, write_range = lsp.lsp_pos

obj, arr, Nest, written, to_json = std.json

write_frame = lsp.lsp_frame

path_of = lsp.lsp_uri

own_str = lsp.lsp_reply

Built, Spot* = lsp.lsp_built

Classed = lsp.lsp_colour
```

### `src/lsp/lsp_fmt.zen`

11 declarations (types: 1, functions: 4, imports and re-exports: 6).

#### Types

```zen
TextEdit = {
    range: WireRange,
    newText: str,
}
```

#### Functions

```zen
write_edits* = (a: Alloc, text: str, out :: String) Res<(), AllocError>

rendered = (a: Alloc, text: str, lexed: Lexed, out :: String)
           Res<(), AllocError>

no_edits = (out :: String) Res<(), AllocError>

whole_edit = (a: Alloc, text: str, shaped: str, out :: String)
             Res<(), AllocError>
```

#### Imports and re-exports

```zen
str, String = std.text

Alloc, AllocError = std.mem

scan, Source, Lexed = std.lex

render = fmt.fmt

WireRange, whole_range = lsp.lsp_pos

arr, to_json = std.json
```

### `src/lsp/lsp_frame.zen`

23 declarations (types: 1, enums: 1, functions: 13, constants: 4, imports and re-exports: 4).

#### Types

```zen
Envelope* = {
    body*: str,
    next*: usize,
}
```

#### Enums

```zen
FrameFault* = NoBlank(usize) | NoLength(usize) | BadLength(usize) | Short(usize)
```

#### Functions

```zen
byte* = (f: FrameFault) usize

why* = (f: FrameFault) str

partial* = (f: FrameFault) bool

frame_at* = (bytes: str, at: usize) Res<Envelope, FrameFault>

short_by* = (bytes: str, at: usize) usize

missing = (bytes: str, end: usize) usize

blank_at = (bytes: str, at: usize) Res<usize, FrameFault>

length_in = (bytes: str, at: usize, blank: usize) Res<usize, FrameFault>

line_end = (bytes: str, from: usize, blank: usize) usize

is_length = (bytes: str, from: usize, stop: usize) bool

trimmed = (bytes: str, from: usize, stop: usize) str

blankish = (b: u8) bool

write_frame* = (body: str, out :: String) Res<(), AllocError>
```

#### Constants

```zen
NAME*: str = "content-length:"

BLANK*: str = "\r\n\r\n"

BLANK_LEN*: usize = 4

CRLF_LEN*: usize = 2
```

#### Imports and re-exports

```zen
str, String, parse_usize = std.text

Range = std.core

AllocError = std.mem

to_lower = std.core.byte
```

### `src/lsp/lsp_hover.zen`

57 declarations (types: 2, functions: 40, constants: 3, imports and re-exports: 12).

#### Types

```zen
Hover* = {
    found*: bool,
    shown*: str,
    start*: WirePos,
    end*: WirePos,
}

Shown = {
    joined: str,
    all: bool,
}
```

#### Functions

```zen
hover_at* = (a: Alloc, name: str, text: str, line: usize, character: usize)
            Res<Hover, AllocError>

hover_in* = (
    env       : Env,
    a         : Alloc,
    workspace : str,
    path      : str,
    text      : str,
    line      : usize,
    character : usize
) Res<Hover, AllocError>

hover_with* = (
    c         : Checker,
    a         : Alloc,
    rel       : str,
    text      : str,
    line      : usize,
    character : usize
) Res<Hover, AllocError>

no_type* = () Hover

said = (c : Checker, a: Alloc, text: str, t: Tell) Res<Hover, AllocError>

nothing_found = () Res<Hover, AllocError>

wired = (text: str, span: Span, known: bool, out :: String)
        Res<Hover, AllocError>

write_written_ty = (
    c   : Checker,
    id  : TypeId,
    out :: String
) Res<bool, AllocError>

write_ty = (c : Checker, id: TypeId, out :: String) Res<bool, AllocError>

write_ty_named = (c : Checker, id: TyId, out :: String) Res<bool, AllocError>

write_ty_value = (c : Checker, id: TyId, out :: String) Res<bool, AllocError>

write_named = (c : Checker, id: TyId, n: TyNamed, out :: String)
              Res<bool, AllocError>

write_prim = (c : Checker, id: TyId, p: Prim, out :: String)
             Res<bool, AllocError>

write_prelude_note = (c : Checker, d: Def, out :: String) Res<(), AllocError>

write_decl_note = (c : Checker, dd: Decl, all: bool, out :: String)
                  Res<(), AllocError>

joiner = (doc: str) str

write_members = (c : Checker, dd: Decl, shown: Shown, out :: String)
                Res<(), AllocError>

write_member_run = (c : Checker, ms: Vec<Member>, all: bool, body :: String)
                   Res<(), AllocError>

write_one_member = (
    c     : Checker,
    m     : Member,
    all   : bool,
    names :: Vec<str>,
    body  :: String
) Res<(), AllocError>

write_typed = (
    c    : Checker,
    show : bool,
    name : str,
    ty   : Res<TypeId>,
    body :: String
) Res<(), AllocError>

write_type_suffix = (c : Checker, ty: Res<TypeId>, body :: String)
                    Res<(), AllocError>

write_fn_member = (
    c     : Checker,
    f     : Function,
    all   : bool,
    names :: Vec<str>,
    body  :: String
) Res<(), AllocError>

write_variant_run = (c : Checker, vs: Vec<Variant>, body :: String)
                    Res<(), AllocError>

write_payload = (c : Checker, payload: Res<TypeId>, body :: String)
                Res<(), AllocError>

separate = (body :: String) Res<(), AllocError>

doc_block = (a: Alloc, tree: Ast, run: TriviaRun) Res<str, AllocError>

ended = (doc: str) bool

terminal = (b: u8) bool

after_last_blank = (tree: Ast, run: TriviaRun) usize

add_doc_line = (line: str, doc :: String) Res<(), AllocError>

comment_text = (text: str) str

write_val = (c : Checker, e: ExprId, out :: String) Res<bool, AllocError>

write_ty_id = (c : Checker, id: TyId, out :: String) Res<bool, AllocError>

poison_free = (c : Checker, id: TyId) bool

all_poison_free = (c : Checker, ids: Vec<TyId>) bool

write_decl_sig = (
    c   : Checker,
    f   : Function,
    out :: String
) Res<bool, AllocError>

write_tparams = (f: Function, out :: String) Res<(), AllocError>

write_opt_ty = (c : Checker, t: Res<TypeId>, out :: String)
               Res<bool, AllocError>

an_answer = () Res<bool, AllocError>

no_answer = () Res<bool, AllocError>
```

#### Constants

```zen
EXPORTED_ONLY: bool = false

WHOLE_SHAPE: bool = true

MEMBERS: str = "members: "
```

#### Imports and re-exports

```zen
str, String = std.text

Vec = std.collections

Range = std.core

Alloc, AllocError = std.mem

Ast, Decl, ExprId, Member, TypeId, Span, Function, TriviaRun = std.ast

Variant = std.ast

Checker = sema.sema_check

TyId, TyNamed, Prim = sema.sema_ty

Def, decl_at = sema.sema_def

to_pos, to_wire, WirePos = lsp.lsp_pos

Tell, told_at = std.ast.ast_named

check_standalone, check_build = lsp.lsp_query
```

### `src/lsp/lsp_names.zen`

32 declarations (types: 1, functions: 20, imports and re-exports: 11).

#### Types

```zen
Classes = {
    file: str,
    rows :: Vec<Classed>,
}
```

#### Functions

```zen
classify* = (a: Alloc, c: Checker, file: str)
           Res<Vec<Classed>, AllocError>

class_as = (
    a      : Alloc,
    span   : Span,
    colour : Colour,
    out    :: Classes
) Res<(), AllocError>

decl_sites = (a: Alloc, c: Checker, out :: Classes)
             Res<(), AllocError>

module_sites = (a: Alloc, m: Module, out :: Classes)
               Res<(), AllocError>

nested_sites = (a: Alloc, tree: Ast, out :: Classes)
               Res<(), AllocError>

block_sites = (a: Alloc, b: Block, out :: Classes)
              Res<(), AllocError>

decl_site = (a: Alloc, d: Decl, out :: Classes)
            Res<(), AllocError>

fn_site = (a: Alloc, f: Function, out :: Classes)
          Res<(), AllocError>

member_sites = (
    a       : Alloc,
    name    : Span,
    members : Vec<Member>,
    out     :: Classes
) Res<(), AllocError>

member_site = (a: Alloc, m: Member, out :: Classes)
              Res<(), AllocError>

written_types = (a: Alloc, c: Checker, out :: Classes)
               Res<(), AllocError>

written_type = (
    a   : Alloc,
    c   : Checker,
    tid : TypeId,
    out :: Classes
) Res<(), AllocError>

named_site = (
    a   : Alloc,
    c   : Checker,
    tid : TypeId,
    n   : Named,
    out :: Classes
) Res<(), AllocError>

expr_sites = (a: Alloc, c: Checker, out :: Classes)
             Res<(), AllocError>

expr_site = (
    a   : Alloc,
    c   : Checker,
    id  : ExprId,
    out :: Classes
) Res<(), AllocError>

param_site = (
    a    : Alloc,
    c    : Checker,
    id   : ExprId,
    span : Span,
    out  :: Classes
) Res<(), AllocError>

call_site = (
    a   : Alloc,
    c   : Checker,
    id  : ExprId,
    k   : Call,
    out :: Classes
) Res<(), AllocError>

callee_site = (
    a   : Alloc,
    c   : Checker,
    d   : Decl,
    k   : Call,
    out :: Classes
) Res<(), AllocError>

fn_callee = (
    a   : Alloc,
    c   : Checker,
    k   : Call,
    out :: Classes
) Res<(), AllocError>

type_callee = (
    a    : Alloc,
    c    : Checker,
    k    : Call,
    decl : str,
    out  :: Classes
) Res<(), AllocError>
```

#### Imports and re-exports

```zen
str = std.text

Alloc, AllocError = std.mem

Vec = std.collections

Range = std.core

Ast, Module, Decl, Block = std.ast

Struct, Enum, Alias, Impl, Member, Function, Named, Call, Match, Try = std.ast

Span, ExprId, TypeId, BlockId = std.ast

Checker = sema.sema_check

decl_at = sema.sema_def

Classed, Colour, sort_classes = lsp.lsp_colour

written = std.json
```

### `src/lsp/lsp_pos.zen`

24 declarations (types: 4, functions: 14, imports and re-exports: 6).

#### Types

```zen
WirePos* = {
    line*: usize,
    character*: usize,
}

WireRange* = {
    start*: WirePos,
    end*: WirePos,
}

LineRun* = {
    start*: usize,
    end*: usize,
}

Step* = {
    units*: usize,
    bytes*: usize,
}
```

#### Functions

```zen
run_of* = (text: str, line: usize) LineRun

end_of = (text: str, from: usize) usize

step_at* = (text: str, at: usize) Step

to_pos* = (text: str, line: usize, character: usize) Pos

to_wire* = (text: str, p: Pos) WirePos

wire_at* = (text: str, line: usize, col: usize) WirePos

wire_range* = (text: str, span: Span) WireRange

whole_range* = (text: str) WireRange

units_of* = (text: str, from: usize, upto: usize) usize

target_of = (run: LineRun, col: usize) usize

write_wire* = (a: Alloc, p: WirePos, out :: String) Res<(), AllocError>

write_whole* = (a: Alloc, text: str, out :: String) Res<(), AllocError>

past_last_line = (text: str) usize

write_range* = (a: Alloc, text: str, span: Span, out :: String)
              Res<(), AllocError>
```

#### Imports and re-exports

```zen
str, String = std.text

Range = std.core

Alloc, AllocError = std.mem

Pos, Span = std.ast.ast_span

codepoint_at, UTF8_MIN_4 = std.text.text_utf8

to_json = std.json
```

### `src/lsp/lsp_query.zen`

16 declarations (types: 2, functions: 4, imports and re-exports: 10).

#### Types

```zen
CheckedBuild* = {
    root*: str,
    rel*: str,
    c*: Checker,
}

WorkspaceCheck* = {
    b*: Build,
    c*: Checker,
}
```

#### Functions

```zen
parse_standalone = (a: Alloc, name: str, text: str) Res<Parser, AllocError>

check_standalone* = (a: Alloc, name: str, text: str)
                    Res<Checker, AllocError>

check_workspace* = (
    env   : Env,
    a     : Alloc,
    root  : str,
    entry : str,
    docs  : Map<str, str>
) Res<WorkspaceCheck, AllocError>

check_build* = (env: Env, a: Alloc, workspace: str, path: str, text: str)
               Res<CheckedBuild, AllocError>
```

#### Imports and re-exports

```zen
str = std.text

Map = std.collections

Alloc, AllocError = std.mem

scan, Source = std.lex

Parser = std.parse

Ast = std.ast

Checker = sema.sema_check

check_all = sema.sema_decl

Build = zen.zen_build

root_for, relative_to, std_root_for = zen.zen_path
```

### `src/lsp/lsp_reply.zen`

30 declarations (types: 3, enums: 2, functions: 17, constants: 1, imports and re-exports: 7).

#### Types

```zen
FaultText = { why: str, at: Res<usize> }

MarkupContent = {
    kind: str,
    value: str,
}

HoverResult = {
    contents: MarkupContent,
    range: WireRange,
}
```

#### Enums

```zen
Request* = Initialize
    | Shutdown
    | Hover
    | Definition
    | Outline
    | Completion
    | Colour
    | Format
    | Action
    | Unknown

RpcFault* = ParseError | MethodNotFound | InvalidParams | NotInitialized
```

#### Functions

```zen
method_of* = (tree: Jsons, req: JsonId) str

params_of* = (tree: Jsons, req: JsonId) JsonId

param* = (tree: Jsons, req: JsonId, name: str) JsonId

string_at* = (tree: Jsons, obj: JsonId, name: str) str

number_at* = (tree: Jsons, obj: JsonId, name: str) usize

result* = (tree: Jsons, rid: JsonId, body: str, msg :: String)
          Res<(), AllocError>

failed* = (
    tree : Jsons,
    rid  : JsonId,
    code : RpcFault,
    why  : str,
    msg  :: String
) Res<(), AllocError>

head = (tree: Jsons, rid: JsonId, msg :: String) Res<Nest, AllocError>

parse_error* = (f: JsonFault, msg :: String) Res<(), AllocError>

write_fault = (f: JsonFault, msg :: String) Res<(), AllocError>

fault_text = (f: JsonFault) FaultText

write_hover* = (a: Alloc, h: Hover, out :: String) Res<(), AllocError>

write_target* = (a: Alloc, t: Target, body :: String) Res<(), AllocError>

write_capabilities* = (out :: String) Res<(), AllocError>

request_of* = (method: str) Request

rpc_code = (f: RpcFault) usize

own_str* = (a: Alloc, s: str) Res<str, AllocError>
```

#### Constants

```zen
SEMANTIC_TOKENS*: str = "textDocument/semanticTokens/full"
```

#### Imports and re-exports

```zen
str, String = std.text

Alloc, AllocError = std.mem

Jsons, JsonId, write_text, written, obj, Nest,
    JsonFault, to_json = std.json

Hover = lsp.lsp_hover

Target, write_location = lsp.lsp_def

WireRange = lsp.lsp_pos

write_legend = lsp.lsp_colour
```

### `src/lsp/lsp_serve.zen`

29 declarations (types: 1, implementations: 1, functions: 4, imports and re-exports: 23).

#### Types

```zen
Server* = {
    a: Alloc,
    env: Env,
    docs_arena :: Arena,
    workspace :: str = "",
    docs :: Map<str, str>,
    open :: Vec<str>,
    notes :: Diagnostics,
    members :: MemberCache,
    ready :: bool,
    stopping :: bool,
    stopped* = (self: @Self) bool
    completion_builds* = (self: @Self) usize
    one* = (self :: @Self, t: Alloc, body: str, out :: String)
           Res<(), AllocError>
    route = (self :: @Self, t: Alloc, tree: Jsons, req: JsonId, msg :: String)
            Res<(), AllocError>
    requested = (self :: @Self, t: Alloc, tree: Jsons, req: JsonId,
                 method: str, rid: JsonId, msg :: String)
                Res<(), AllocError>
    answered = (self :: @Self, t: Alloc, tree: Jsons, req: JsonId,
                method: str, rid: JsonId, msg :: String)
               Res<(), AllocError>
    initialized = (self :: @Self, t: Alloc, tree: Jsons, req: JsonId,
                   rid: JsonId, msg :: String) Res<(), AllocError>
    unknown = (self :: @Self, t: Alloc, tree: Jsons, rid: JsonId, method: str,
               msg :: String) Res<(), AllocError>
    notified = (self :: @Self, tree: Jsons, req: JsonId, method: str)
               Res<(), AllocError>
    watched = (self :: @Self, tree: Jsons, req: JsonId)
              Res<(), AllocError>
    opened = (self :: @Self, tree: Jsons, req: JsonId) Res<(), AllocError>
    changed = (self :: @Self, tree: Jsons, req: JsonId) Res<(), AllocError>
    closed = (self :: @Self, tree: Jsons, req: JsonId)
             Res<(), AllocError>
    forget = (self :: @Self, uri: str) Res<(), AllocError>
    remember = (self :: @Self, uri: str, text: str) Res<(), AllocError>
    stored = (self :: @Self, uri: str, text: str) Res<(), AllocError>
    changed_to = (self :: @Self, uri: str, text: str) Res<(), AllocError>
    listed = (self :: @Self, uri: str) Res<str, AllocError>
    replace_docs = (self :: @Self, uri: str, text: Res<str>)
                   Res<(), AllocError>
    settled* = (self :: @Self, t: Alloc, out :: String) Res<(), AllocError>
    unopened = (self :: @Self, tree: Jsons, rid: JsonId, msg :: String)
               Res<(), AllocError>
    hovered = (self :: @Self, t: Alloc, tree: Jsons, req: JsonId, rid: JsonId,
               msg :: String) Res<(), AllocError>
    coloured = (self :: @Self, t: Alloc, tree: Jsons, req: JsonId,
                rid: JsonId, msg :: String) Res<(), AllocError>
    build_for = (self :: @Self, path: str, t: Alloc) Res<Shared, AllocError>
    shared_hover = (self :: @Self, t: Alloc, uri: str, text: str,
                    line: usize, character: usize, body :: String)
                   Res<(), AllocError>
    write_hovered = (self :: @Self, a: Alloc, h: Hover, body :: String)
                    Res<(), AllocError>
    defined = (self :: @Self, t: Alloc, tree: Jsons, req: JsonId, rid: JsonId,
               msg :: String) Res<(), AllocError>
    write_definition = (self :: @Self, t: Alloc, uri: str, text: str,
                        line: usize, character: usize, body :: String)
                       Res<(), AllocError>
    outlined = (self :: @Self, t: Alloc, tree: Jsons, req: JsonId, rid: JsonId,
                msg :: String) Res<(), AllocError>
    formatted = (self :: @Self, t: Alloc, tree: Jsons, req: JsonId,
                 rid: JsonId, msg :: String) Res<(), AllocError>
    acted = (self :: @Self, t: Alloc, tree: Jsons, req: JsonId, rid: JsonId,
             msg :: String) Res<(), AllocError>
    shared_actions = (self :: @Self, t: Alloc, uri: str, text: str,
                      sl: usize, sc: usize, el: usize, ec: usize,
                      body :: String) Res<(), AllocError>
    completed = (self :: @Self, t: Alloc, tree: Jsons, req: JsonId,
                 rid: JsonId, msg :: String) Res<(), AllocError>
    write_completion = (self :: @Self, t: Alloc, uri: str, text: str,
                        line: usize, character: usize, body :: String)
                       Res<(), AllocError>
    shared_completion = (self :: @Self, c: Checker, t: Alloc, root: str,
                         path: str, text: str, line: usize, character: usize,
                         body :: String) Res<bool, AllocError>
    patched_completion = (self :: @Self, t: Alloc, path: str, text: str,
                          line: usize, character: usize, body :: String)
                         Res<(), AllocError>
}
```

#### Implementations

```zen
Server.impl(Drop, {
    drop = (self :: @Self) ()
})
```

#### Functions

```zen
Server* = (a: Alloc, env: Env) Server

server_with_docs = (a: Alloc, env: Env, docs_arena :: Arena) Server

serve* = (s :: Server, input: str, out :: String) Res<(), AllocError>

frame_fault = (f: FrameFault, out :: String) Res<(), AllocError>
```

#### Imports and re-exports

```zen
str, String = std.text

Vec, Map = std.collections

Range = std.core

Alloc, AllocError, Arena = std.mem

Checker = sema.sema_check

Jsons, JsonId, written, read = std.json

FrameFault, frame_at, write_frame = lsp.lsp_frame

Hover, hover_at, hover_in, hover_with = lsp.lsp_hover

definition_at, definition_in, definition_with = lsp.lsp_def

Sym, symbols_at, write_symbols = lsp.lsp_symbol

write_edits = lsp.lsp_fmt

Item, MemberCache, complete_at, complete_shared = lsp.lsp_compl

sort_items, write_items = lsp.lsp_compl

write_tokens = lsp.lsp_colour

Diagnostics, Shared = lsp.lsp_diag

write_actions = lsp.lsp_action

relative_to = zen.zen_path

method_of, params_of, param, string_at, number_at = lsp.lsp_reply

result, failed, parse_error, write_hover, write_target = lsp.lsp_reply

write_capabilities = lsp.lsp_reply

RpcFault, own_str = lsp.lsp_reply

request_of = lsp.lsp_reply

path_of = lsp.lsp_uri
```

### `src/lsp/lsp_stdio.zen`

14 declarations (types: 1, functions: 8, imports and re-exports: 5).

#### Types

```zen
Drain* = {
    at*: usize,
    framed*: bool,
}
```

#### Functions

```zen
serve_stdio* = (env: Env, a: Alloc) Res<i32, AllocError>

after_drain = (server :: Server, t: Alloc) Res<(), AllocError>

arrived = (env: Env, held :: Vec<u8>, n: usize) Res<bool, AllocError>

at_least_one = (n: usize) usize

drain = (server :: Server, t: Alloc, held: str, at: usize)
        Res<Drain, AllocError>

answered = (server :: Server, t: Alloc, body: str) Res<(), AllocError>

fault_line = (f: FrameFault, framed: bool) ()

exit_code = (stopped: bool, framed: bool) i32
```

#### Imports and re-exports

```zen
str, String, str_at = std.text

Vec = std.collections

Alloc, AllocError = std.mem

Server = lsp.lsp_serve

FrameFault, frame_at, short_by, partial = lsp.lsp_frame
```

### `src/lsp/lsp_symbol.zen`

22 declarations (types: 3, functions: 6, constants: 5, imports and re-exports: 8).

#### Types

```zen
Sym* = {
    name*: str,
    kind*: usize,
    span*: Span,
    name_span*: Span,
}

SymbolLocation = {
    uri: str,
    range: WireRange,
}

SymbolInformation = {
    name: str,
    kind: usize,
    location: SymbolLocation,
    selectionRange: WireRange,
}
```

#### Functions

```zen
symbols_at* = (a: Alloc, text: str, out :: Vec<Sym>) Res<(), AllocError>

module_syms = (m: Module, out :: Vec<Sym>) Res<(), AllocError>

decl_sym = (d: Decl, out :: Vec<Sym>) Res<(), AllocError>

add_sym = (out :: Vec<Sym>, id: Ident, kind: usize, span: Span)
        Res<(), AllocError>

write_symbols* = (a: Alloc, uri: str, text: str, syms: Vec<Sym>, out :: String)
                 Res<(), AllocError>

write_sym = (a: Alloc, s: Sym, uri: str, text: str, list :: Nest, out :: String)
            Res<(), AllocError>
```

#### Constants

```zen
CLASS*: usize = 5

ENUM*: usize = 10

FUNCTION*: usize = 12

CONSTANT*: usize = 14

STRUCT*: usize = 23
```

#### Imports and re-exports

```zen
str, String = std.text

Vec = std.collections

Alloc, AllocError = std.mem

scan, Source = std.lex

Parser = std.parse

Ast, Module, Decl, Span, Ident = std.ast

WireRange, wire_range = lsp.lsp_pos

written, arr, Nest, to_json = std.json
```

### `src/lsp/lsp_uri.zen`

7 declarations (functions: 3, constants: 2, imports and re-exports: 2).

#### Functions

```zen
path_of* = (uri: str) str

remote_path = (uri: str) str

uri_at* = (a: Alloc, root: str, rel: str) Res<str, AllocError>
```

#### Constants

```zen
FILE_SCHEME*: str = "file://"

REMOTE_SCHEME: str = "vscode-remote://"
```

#### Imports and re-exports

```zen
str, String = std.text

Alloc, AllocError = std.mem
```

### `src/sema/sema.zen`

48 declarations (imports and re-exports: 48).

#### Imports and re-exports

```zen
DeclId*, MemberId*, ImplId*, owner*, member_at* = sema.sema_id

Inst*, InstEdge*, subst*, subst_list*    = sema.sema_inst

has_var*                                 = sema.sema_inst

inst_of_named*, unify*, unify_list*      = sema.sema_inst

tparam_vars*, owner_of*, zip*            = sema.sema_inst

TyId*, Ty*, Types*                       = sema.sema_ty

Prim*, TyNamed*, TyFn*, TyUnion*, TyVar* = sema.sema_ty

ResForm*, TyRes*                         = sema.sema_ty

res_arity*, is_failure*                  = sema.sema_ty

SemaFault*, Diag*, message*, render*     = sema.sema_diag

NameFault*, TypeFault*, PairFault*       = sema.sema_diag

check_module_graph*                      = sema.sema_cycle

DefKind*, Def*, ImportBinding*           = sema.sema_def

ModuleTable*, World*, dotted*, decl_at*  = sema.sema_def

PRELUDE*, last_segment*                  = sema.sema_def

Checker*, Ctx*, Binding*                 = sema.sema_check

is_prim*, is_integer*, is_float*         = sema.sema_ty

type_of*, block_type*                    = sema.sema_type

type_from_ast*                           = sema.sema_denote

Case*, cases_of*, case_payload*          = sema.sema_case

PatKind*, Pat*, Pats*, PatMatrix*        = sema.sema_match

match_type*, useful*, is_case*           = sema.sema_match

join*                                    = sema.sema_join

Found*, Base*, access_type*, members_of* = sema.sema_member

computed_member*                         = sema.sema_member

impl_members*, bound_members*            = sema.sema_supply

bound_member_type*, impl_bound_type*     = sema.sema_supply

check_impl*, satisfies_bound*, required* = sema.sema_bound

Cand*, TBound*, Actual*                  = sema.sema_call

call_type*, check_overloads*             = sema.sema_call

same_signature*, swallows*               = sema.sema_call

cands_of*, matches*, travelled_cands*    = sema.sema_cand

check_binary*                            = sema.sema_trap

const_int*, fits*                        = sema.sema_const

check_all*, check_module*, check_function* = sema.sema_decl

check_layout*                            = sema.sema_layout

check_own*, Own*, OwnVar*, Place*        = sema.sema_own

find_var*, path_root*, var_type*         = sema.sema_own

place_type*, refuse*, var_mutable*       = sema.sema_own

check_drop_copy*, is_drop_type*                           = sema.sema_drop

check_receiver*                          = sema.sema_recv

receiver_is_mutable*                     = sema.sema_recv

check_scope_returned*, check_scope_stored* = sema.sema_scope

check_scope_captured*, call_escapes*       = sema.sema_scope

is_construction*                           = sema.sema_scope

check_depth*                             = sema.sema_depth

check_varargs*, pack_elem*, pack_slot*   = sema.sema_vararg

tail_is_pack*, written_pack*, VARARG*    = sema.sema_vararg
```

### `src/sema/sema_apply.zen`

72 declarations (functions: 49, imports and re-exports: 23).

#### Functions

```zen
construct* = (c :: Checker, id: ExprId, call: Call, d: Def, ctx: Ctx)
            Res<TyId, AllocError>

settled_ctor_type = (
    c       :: Checker,
    call    : Call,
    d       : Def,
    ctx     : Ctx,
    vars    : Vec<TyId>,
    applied : TyId
)
                    Res<TyId, AllocError>

ctor_type_from_args = (
    c       :: Checker,
    call    : Call,
    d       : Def,
    ctx     : Ctx,
    vars    : Vec<TyId>,
    applied : TyId
)
                      Res<TyId, AllocError>

rebuilt_ctor_type = (c :: Checker, d: Def, vars: Vec<TyId>, inst: Inst)
                    Res<TyId, AllocError>

unify_ctor_arg = (
    c       :: Checker,
    a       : Arg,
    applied : TyId,
    ctx     : Ctx,
    inst    :: Inst
) Res<(), AllocError>

unify_ctor_field = (
    c       :: Checker,
    a       : Arg,
    name    : str,
    applied : TyId,
    ctx     : Ctx,
    inst    :: Inst
) Res<(), AllocError>

variant_call_type* = (
    c    :: Checker,
    call : Call,
    ty   : TyId,
    name : str,
    ctx  : Ctx
) Res<TyId, AllocError>

variant_has_type = (c: Checker, call: Call, ty: TyId) bool

variant_literal = (
    c    :: Checker,
    call : Call,
    ty   : TyId,
    name : str,
    inst : Inst
) Res<(), AllocError>

settle_variant_at* = (
    c    :: Checker,
    id   : ExprId,
    got  : TyId,
    want : TyId,
    ctx  : Ctx
) Res<TyId, AllocError>

applied_at_own_vars = (c :: Checker, ty: TyId) Res<TyId, AllocError>

named_with_decl_vars = (c :: Checker, ty: TyId, n: TyNamed)
                       Res<TyId, AllocError>

enum_tparam_vars = (c :: Checker, d: Decl, owner: str, out :: Vec<TyId>)
                   Res<(), AllocError>

payload_says = (
    c    :: Checker,
    call : Call,
    ty   : TyId,
    cs   : Case,
    ctx  : Ctx,
    inst :: Inst
) Res<(), AllocError>

settled_arg_ty = (c :: Checker, a: Arg, ctx: Ctx) Res<TyId, AllocError>

ctor_args = (c :: Checker, call: Call, d: Def, ctx: Ctx, out :: Vec<TyId>)
            Res<(), AllocError>

written_ctor_args = (
    c     :: Checker,
    targs : Vec<TypeId>,
    ctx   : Ctx,
    out   :: Vec<TyId>
) Res<(), AllocError>

decl_tparams = (c :: Checker, d: Def, out :: Vec<TyId>)
               Res<(), AllocError>

decl_tparams_of = (c :: Checker, d: Def, dec: Decl, out :: Vec<TyId>)
                  Res<(), AllocError>

instantiate* = (
    c       :: Checker,
    id      : ExprId,
    call    : Call,
    k       : Cand,
    actuals : Vec<Actual>,
    ctx     : Ctx
) Res<TyId, AllocError>

instantiated_ret = (
    c       :: Checker,
    id      : ExprId,
    call    : Call,
    k       : Cand,
    actuals : Vec<Actual>,
    ctx     : Ctx
)
                   Res<TyId, AllocError>

note_edge = (c :: Checker, id: ExprId, k: Cand, inst: Inst)
            Res<(), AllocError>

arg_for = (v: TyId, inst: Inst) TyId

call_inst = (
    c       :: Checker,
    call    : Call,
    k       : Cand,
    actuals : Vec<Actual>,
    ctx     : Ctx
) Res<Inst, AllocError>

written_targs = (c :: Checker, call: Call, k: Cand, inst :: Inst, ctx: Ctx)
                Res<(), AllocError>

bind_written = (
    c     :: Checker,
    targs : Vec<TypeId>,
    k     : Cand,
    inst  :: Inst,
    ctx   : Ctx
) Res<(), AllocError>

infer_targs = (c :: Checker, k: Cand, actuals: Vec<Actual>, inst :: Inst)
              Res<(), AllocError>

infer_at = (
    c       :: Checker,
    k       : Cand,
    actuals : Vec<Actual>,
    i       : usize,
    inst    :: Inst
) Res<(), AllocError>

infer_from = (c :: Checker, param: TyId, a: Actual, inst :: Inst)
             Res<(), AllocError>

infer_from_bounds = (c :: Checker, k: Cand, inst :: Inst)
                    Res<(), AllocError>

infer_one_bound = (c :: Checker, k: Cand, tb: TBound, inst :: Inst)
                  Res<(), AllocError>

infer_through_bound = (c :: Checker, bound: TyId, g: TyId, inst :: Inst)
                      Res<(), AllocError>

same_head = (c: Checker, a: TyId, b: TyId) bool

head_is = (c: Checker, x: TyNamed, b: TyId) bool

infer_own_bound = (c :: Checker, bound: TyId, g: TyId, inst :: Inst)
                  Res<(), AllocError>

unify_index_space = (
    c        :: Checker,
    bs       : Vec<TyId>,
    gs       : Vec<TyId>,
    usize_ty : TyId,
    inst     :: Inst
) Res<(), AllocError>

settled_or_index = (c: Checker, t: TyId, usize_ty: TyId) TyId

named_args = (c :: Checker, ty: TyId, out :: Vec<TyId>)
             Res<(), AllocError>

infer_impl_bound = (c :: Checker, bound: TyId, g: TyId, inst :: Inst)
                   Res<(), AllocError>

infer_array_bound = (c :: Checker, bound: TyId, elem: TyId, inst :: Inst)
                    Res<(), AllocError>

unify_array_elem = (c :: Checker, bound: TyId, elem: TyId, inst :: Inst)
                   Res<(), AllocError>

infer_named_impl = (c :: Checker, bound: TyId, n: TyNamed, inst :: Inst)
                   Res<(), AllocError>

impl_bound_at = (c :: Checker, bound: TyId, n: TyNamed)
                Res<Res<TyId>, AllocError>

impl_bound_from = (
    c     :: Checker,
    ids   : Vec<ImplId>,
    i     : usize,
    bound : TyId,
    n     : TyNamed
) Res<Res<TyId>, AllocError>

impl_bound_or_next = (
    c     :: Checker,
    ids   : Vec<ImplId>,
    i     : usize,
    id    : ImplId,
    bound : TyId,
    n     : TyNamed
) Res<Res<TyId>, AllocError>

impl_applied = (c :: Checker, id: ImplId, bound: TyId, n: TyNamed)
               Res<Res<TyId>, AllocError>

impl_applied_local = (c :: Checker, id: ImplId, bound: TyId, n: TyNamed)
                     Res<Res<TyId>, AllocError>

impl_applied_of = (c :: Checker, im: Impl, bound: TyId, n: TyNamed)
                  Res<Res<TyId>, AllocError>

applied_at_recv = (c :: Checker, got: TyId, n: TyNamed)
                  Res<Res<TyId>, AllocError>
```

#### Imports and re-exports

```zen
Expr, ExprId, Call, Arg = std.ast

Decl, Enum, Struct, TypeId, Impl = std.ast

AllocError = std.mem

Vec = std.collections

str = std.text

Range = std.core

ImplId = sema.sema_id

TyId, TyNamed, literal_default = sema.sema_ty

Def, decl_at = sema.sema_def

Checker, Ctx = sema.sema_check

Inst, InstEdge, subst, unify, tparam_vars, zip = sema.sema_inst

has_var, inst_of_named = sema.sema_inst

Cand, TBound, Actual = sema.sema_call

ty_at = sema.sema_cand

impl_bound_type = sema.sema_supply

type_of = sema.sema_type

type_from_ast = sema.sema_denote

check_literal = sema.sema_trap

array_range_shape = sema.sema_bound

case_payload, Case, cases_of, find_case = sema.sema_case

check_ctor_fields = sema.sema_hoist

check_ctor_shape = sema.sema_bound

Found, members_of = sema.sema_member
```

### `src/sema/sema_bound.zen`

81 declarations (types: 1, functions: 63, imports and re-exports: 17).

#### Types

```zen
Owed = {
    m: Member,
    span: Span,
}
```

#### Functions

```zen
check_impl* = (c :: Checker, id: ImplId, mi: usize) Res<(), AllocError>

check_one_impl = (c :: Checker, im: Impl, id: ImplId, mi: usize)
                 Res<(), AllocError>

check_home = (c :: Checker, im: Impl, id: ImplId, mi: usize)
             Res<(), AllocError>

target_defs = (c :: Checker, name: str, mi: usize, out :: Vec<Def>)
              Res<(), AllocError>

home_is = (c :: Checker, d: Def, im: Impl, id: ImplId, mi: usize)
          Res<(), AllocError>

orphan = (c :: Checker, im: Impl, id: ImplId, d: Def) Res<(), AllocError>

module_named = (c: Checker, mi: usize) str

check_impl_body = (c :: Checker, im: Impl, id: ImplId, mi: usize)
                  Res<(), AllocError>

owed = (c :: Checker, im: Impl, m: Member, span: Span) Res<(), AllocError>

required* = (m: Member) bool

missing = (c :: Checker, span: Span, name: str) Res<(), AllocError>

check_ctor_shape* = (c :: Checker, call: Call, ty: TyId, span: Span)
                    Res<(), AllocError>

check_ctor_seats = (c :: Checker, call: Call, ty: TyId, span: Span)
                   Res<(), AllocError>

refuse_surplus_arg = (c :: Checker, call: Call, ty: TyId)
                     Res<bool, AllocError>

refuse_surplus_one = (c :: Checker, a: Arg, i: usize, ty: TyId)
                     Res<bool, AllocError>

arg_fits_field = (c :: Checker, a: Arg, i: usize, ty: TyId)
                 Res<(), AllocError>

positional_arg_fits = (c :: Checker, a: Arg, i: usize, ty: TyId)
                      Res<(), AllocError>

named_arg_fits = (c :: Checker, a: Arg, name: str, ty: TyId)
                 Res<(), AllocError>

arg_value_fits = (c :: Checker, a: Arg, want: TyId) Res<(), AllocError>

fits_or_refuse = (c :: Checker, a: Arg, got: TyId, want: TyId)
                 Res<(), AllocError>

want_is_res = (c :: Checker, want: TyId) bool

refuse_unless_bound = (c :: Checker, span: Span, got: TyId, want: TyId)
                      Res<(), AllocError>

absent_fields = (c :: Checker, call: Call, ty: TyId, span: Span)
                Res<(), AllocError>

absent_field = (c :: Checker, call: Call, ty: TyId, at: Owed)
               Res<(), AllocError>

seat_written = (c :: Checker, call: Call, ty: TyId, name: str)
               Res<bool, AllocError>

arg_writes_seat = (c :: Checker, a: Arg, i: usize, ty: TyId, name: str)
                  Res<bool, AllocError>

ctor_required = (c :: Checker, m: Member, ty: TyId)
                Res<bool, AllocError>

written_res = (c :: Checker, t: Res<TypeId>, owner: TyId)
              Res<bool, AllocError>

ctor_missing = (c :: Checker, span: Span, name: str) Res<(), AllocError>

satisfies_bound* = (c :: Checker, ty: TyId, bound: TyId)
                   Res<bool, AllocError>

actor_receives = (c :: Checker, ty: TyId, bound: TyId)
                 Res<bool, AllocError>

receive_bound = (c: Checker, bound: TyId) bool

actor_impl_receives = (
    c     :: Checker,
    n     : TyNamed,
    ty    : TyId,
    bound : TyId
) Res<bool, AllocError>

actor_impl_has_receive = (
    c        :: Checker,
    im       : Impl,
    n        : TyNamed,
    ty       : TyId,
    expected : TyId
) Res<bool, AllocError>

actor_bound = (c: Checker, ty: TyId) bool

member_is = (
    c        :: Checker,
    expected : TyId,
    m        : Member,
    n        : TyNamed,
    ty       : TyId
) Res<bool, AllocError>

impls_bound = (c :: Checker, ty: TyId, bound: TyId) Res<bool, AllocError>

prim_impls_bound = (c :: Checker, p: Prim, bound: TyId) Res<bool, AllocError>

array_satisfies = (c: Checker, bound: TyId) bool

array_range_shape* = (c: Checker, bound: TyId) bool

bound_declares = (c: Checker, bound: TyId, name: str) bool

decl_declares = (c: Checker, n: TyNamed, name: str) bool

struct_declares = (d: Decl, name: str) bool

is_field = (m: Member) bool

named_impls_bound = (c :: Checker, n: TyNamed, bound: TyId)
                    Res<bool, AllocError>

local_bound_is = (c :: Checker, id: ImplId, n: TyNamed, bound: TyId)
                 Res<bool, AllocError>

impl_bound_is = (c :: Checker, id: ImplId, n: TyNamed, bound: TyId)
                Res<bool, AllocError>

bound_matches = (c :: Checker, im: Impl, mi: usize, bound: TyId)
                Res<bool, AllocError>

check_bounds* = (c :: Checker, cand: Cand, actuals: Vec<Actual>, at: Span)
                Res<(), AllocError>

check_one_bound = (
    c       :: Checker,
    cand    : Cand,
    tb      : TBound,
    actuals : Vec<Actual>,
    at      : Span
) Res<(), AllocError>

param_of_var = (c: Checker, cand: Cand, name: str) Res<usize>

var_named = (c: Checker, id: TyId, name: str, owner: str) bool

bound_at = (
    c       :: Checker,
    tb      : TBound,
    actuals : Vec<Actual>,
    i       : usize,
    at      : Span
) Res<(), AllocError>

check_actual_bound = (c :: Checker, tb: TBound, a: Actual, at: Span)
                     Res<(), AllocError>

unbounded = (c: Checker, ty: TyId) bool

prove_bound = (c :: Checker, tb: TBound, a: Actual, at: Span)
              Res<(), AllocError>

bound_not_satisfied = (c :: Checker, tb: TBound, a: Actual, at: Span)
                      Res<(), AllocError>

check_eq* = (c :: Checker, b: Binary, operand: TyId) Res<(), AllocError>

is_eq_op = (op: BinOp) bool

dispatches_eq = (c: Checker, ty: TyId) bool

scalar_eq = (c: Checker, ty: TyId) bool

prove_eq = (c :: Checker, b: Binary, operand: TyId) Res<(), AllocError>

eq_needs_impl = (c :: Checker, b: Binary, operand: TyId)
                Res<(), AllocError>
```

#### Imports and re-exports

```zen
Decl, Struct, Impl, Member, Call, Arg, TypeId = std.ast

Field, Const, Function, Span, Binary, BinOp = std.ast

AllocError = std.mem

Vec = std.collections

str = std.text

Range = std.core

ImplId = sema.sema_id

TyId, TyNamed, Prim, is_prim = sema.sema_ty

Def, decl_at = sema.sema_def

SemaFault, NameFault, TypeFault, ExportFault = sema.sema_diag

Checker = sema.sema_check

opaque, Found, members_of, member_type = sema.sema_member

bound_members, bound_member_type, has_member, impl_span, impl_bound_type = sema.sema_supply

storage_seat_name = sema.sema_supply

Cand, TBound, Actual = sema.sema_call

ty_at, is_tvar = sema.sema_cand

res_sugar = sema.sema_denote
```

### `src/sema/sema_call.zen`

106 declarations (types: 4, functions: 71, imports and re-exports: 31).

#### Types

```zen
Cand* = {
    id*: DeclId,
    name*: str,
    owner*: str,
    params*: Vec<TyId>,
    ret*: TyId,
    tvars*: Vec<TyId>,
    tbounds*: Vec<TBound>,
    generic*: bool,
    span*: Span,
}

TBound* = {
    name*: str,
    bound*: TyId,
}

Actual* = {
    ty*: TyId,
    is_lambda*: bool,
    arity*: usize,
    named*: bool,
    span*: Span,
}

CallCheck = {
    id: ExprId,
    node: Expr,
    call: Call,
    ctx: Ctx,
    actuals :: Vec<Actual>,
    run = (self :: @Self, c :: Checker) Res<TyId, AllocError>
    load_actuals = (self :: @Self, c :: Checker) Res<(), AllocError>
    named = (self :: @Self, c :: Checker, name: str)
            Res<TyId, AllocError>
    print_or_call = (self :: @Self, c :: Checker, name: str)
                    Res<TyId, AllocError>
    local_or_decl = (self :: @Self, c :: Checker, name: str)
                    Res<TyId, AllocError>
    local_signature = (self :: @Self, c :: Checker, ty: TyId)
                      Res<TyId, AllocError>
    decl = (
        self    :: @Self,
        c       :: Checker,
        name    : str,
        recv    : Res<TyId>,
        actuals : Vec<Actual>
    ) Res<TyId, AllocError>
    construct_or_fail = (
        self  :: @Self,
        c     :: Checker,
        name  : str,
        recv  : Res<TyId>,
        cands : Vec<Cand>
    ) Res<TyId, AllocError>
    unresolved = (
        self  :: @Self,
        c     :: Checker,
        name  : str,
        recv  : Res<TyId>,
        cands : Vec<Cand>
    ) Res<TyId, AllocError>
    construct_def = (self :: @Self, c :: Checker, d: Def)
                    Res<TyId, AllocError>
    chosen = (self :: @Self, c :: Checker, k: Cand, actuals: Vec<Actual>)
             Res<TyId, AllocError>
    member = (self :: @Self, c :: Checker, ac: Access)
             Res<TyId, AllocError>
    ordinary_member = (self :: @Self, c :: Checker, ac: Access)
                      Res<TyId, AllocError>
    static_member = (self :: @Self, c :: Checker, ac: Access, ty: TyId)
                    Res<TyId, AllocError>
    receiver = (self :: @Self, c :: Checker, ac: Access, b: Base)
               Res<TyId, AllocError>
    known_receiver = (self :: @Self, c :: Checker, ac: Access, b: Base)
                     Res<TyId, AllocError>
    reachable = (
        self  :: @Self,
        c     :: Checker,
        ac    : Access,
        b     : Base,
        found : Vec<Found>
    ) Res<TyId, AllocError>
    method = (self :: @Self, c :: Checker, found: Vec<Found>)
             Res<TyId, AllocError>
    by_arity = (self :: @Self, c :: Checker, found: Vec<Found>)
               Res<TyId, AllocError>
    first_found = (self :: @Self, c :: Checker, found: Vec<Found>)
                  Res<TyId, AllocError>
    ufcs = (self :: @Self, c :: Checker, ac: Access, b: Base)
           Res<TyId, AllocError>
    indirect = (self :: @Self, c :: Checker) Res<TyId, AllocError>
    signature = (self :: @Self, c :: Checker, ty: TyId, off: usize)
                Res<TyId, AllocError>
}
```

#### Functions

```zen
CallCheck = (a: Alloc, id: ExprId, node: Expr, call: Call, ctx: Ctx)
            CallCheck

call_callee* = (tree: Ast, call: Call) Expr

call_callee_at = (tree: Ast, id: ExprId) Expr

call_type* = (c :: Checker, id: ExprId, node: Expr, call: Call, ctx: Ctx)
             Res<TyId, AllocError>

actuals_of = (c :: Checker, args: Vec<Arg>, ctx: Ctx, out :: Vec<Actual>)
             Res<(), AllocError>

actual_of = (c :: Checker, a: Arg, ctx: Ctx) Res<Actual, AllocError>

spelled_lambda* = (c :: Checker, id: ExprId) Res<Lambda>

is_named = (a: Arg) bool

lambda_actual = (c :: Checker, l: Lambda, a: Arg) Res<Actual, AllocError>

value_actual = (c :: Checker, a: Arg, ctx: Ctx) Res<Actual, AllocError>

print_type = (c :: Checker, call: Call) Res<TyId, AllocError>

is_print_sugar = (name: str) bool

is_res_ctor = (name: str) bool

res_ctor_type = (c :: Checker, name: str, actuals: Vec<Actual>)
                Res<TyId, AllocError>

err_res = (c :: Checker, e: TyId) Res<TyId, AllocError>

first_ty = (c :: Checker, actuals: Vec<Actual>) Res<TyId, AllocError>

instantiate_sig = (c :: Checker, id: ExprId, ty: TyId, actuals: Vec<Actual>)
                  Res<TyId, AllocError>

instantiate_fn_sig = (
    c       :: Checker,
    id      : ExprId,
    ty      : TyId,
    f       : TyFn,
    actuals : Vec<Actual>
) Res<TyId, AllocError>

first_matching = (
    c       :: Checker,
    cands   : Vec<Cand>,
    actuals : Vec<Actual>
) Res<Res<Cand>, AllocError>

no_such_method = (c :: Checker, call: Call, name: str, ty: TyId)
                 Res<TyId, AllocError>

report_no_method = (c :: Checker, call: Call, name: str, ty: TyId)
                   Res<TyId, AllocError>

callee_name_span = (c: Checker, call: Call) Span

type_def_of = (defs: Vec<Def>) Res<Def>

no_overload = (c :: Checker, node: Expr, name: str, cands: Vec<Cand>)
              Res<TyId, AllocError>

args_handle_check = (
    c      :: Checker,
    args   : Vec<Arg>,
    params : Vec<TyId>,
    off    : usize,
    ctx    : Ctx
) Res<(), AllocError>

settled_params = (c :: Checker, id: ExprId, k: Cand, out :: Vec<TyId>)
                 Res<(), AllocError>

arg_lambdas = (
    c      :: Checker,
    args   : Vec<Arg>,
    params : Vec<TyId>,
    off    : usize,
    ctx    : Ctx
) Res<(), AllocError>

arg_lambda = (c :: Checker, id: ExprId, params: Vec<TyId>, i: usize, ctx: Ctx)
             Res<(), AllocError>

lambda_body = (c :: Checker, id: ExprId, l: Lambda, sig: TyId, ctx: Ctx)
              Res<(), AllocError>

resolve_lambda_inst = (
    c    :: Checker,
    id   : ExprId,
    l    : Lambda,
    sig  : TyId,
    ptys : Vec<TyId>,
    ctx  : Ctx
) Res<(), AllocError>

lambda_param = (c :: Checker, p: Param, ptys: Vec<TyId>, i: usize, ctx: Ctx)
               Res<TyId, AllocError>

sig_param = (c :: Checker, ptys: Vec<TyId>, i: usize) Res<TyId, AllocError>

settled_or_poison = (c :: Checker, ty: TyId) Res<TyId, AllocError>

recv_off = (call: Call, actuals: Vec<Actual>) usize

arg_literals* = (c :: Checker, args: Vec<Arg>, params: Vec<TyId>, off: usize)
               Res<(), AllocError>

param_literal = (c :: Checker, id: ExprId, params: Vec<TyId>, i: usize)
                Res<(), AllocError>

param_wants = (c :: Checker, id: ExprId, want: TyId) Res<(), AllocError>

param_holds = (c :: Checker, id: ExprId, want: TyId) Res<(), AllocError>

settled_param = (c: Checker, want: TyId) bool

refuse_actor_payloads = (c :: Checker, recv: TyId, actuals: Vec<Actual>)
                         Res<(), AllocError>

actor_payload_unsafe = (c: Checker, ty: TyId) bool

pick_fitting = (c :: Checker, found: Vec<Found>, actuals: Vec<Actual>)
               Res<Res<Found>, AllocError>

found_fits = (
    c       :: Checker,
    f       : Found,
    actuals : Vec<Actual>
) Res<bool, AllocError>

fn_params = (c :: Checker, ty: TyId, out :: Vec<TyId>)
            Res<(), AllocError>

copy_tys = (xs: Vec<TyId>, out :: Vec<TyId>) Res<(), AllocError>

pick_arity = (c: Checker, found: Vec<Found>, want: usize) Res<Found>

fn_arity_is = (c: Checker, ty: TyId, want: usize) bool

sig_args_handle_check = (
    c    :: Checker,
    node : Expr,
    call : Call,
    ty   : TyId,
    off  : usize,
    ctx  : Ctx
) Res<(), AllocError>

sig_lambdas = (c :: Checker, call: Call, ty: TyId, off: usize, ctx: Ctx)
              Res<(), AllocError>

fn_ret = (c :: Checker, node: Expr, ty: TyId) Res<TyId, AllocError>

not_callable = (c :: Checker, node: Expr, ty: TyId) Res<TyId, AllocError>

check_overloads* = (c :: Checker, mi: usize, name: str)
                   Res<(), AllocError>

check_pair = (c :: Checker, name: str, cands: Vec<Cand>, i: usize, j: usize)
             Res<(), AllocError>

check_against = (
    c     :: Checker,
    name  : str,
    a     : Cand,
    cands : Vec<Cand>,
    j     : usize
) Res<(), AllocError>

compare = (c :: Checker, name: str, a: Cand, b: Cand) Res<(), AllocError>

compare_same_arity = (c :: Checker, name: str, a: Cand, b: Cand)
                     Res<(), AllocError>

same_signature* = (c: Checker, a: Cand, b: Cand) bool

same_fn_signature* = (c: Checker, a: TyId, b: TyId) bool

same_params = (c: Checker, a: Vec<TyId>, b: Vec<TyId>) bool

same_param = (c: Checker, x: TyId, y: TyId) bool

maybe_swallow = (c :: Checker, name: str, a: Cand, b: Cand)
                Res<(), AllocError>

swallows* = (c: Checker, a: Cand, b: Cand) bool

all_eat = (c: Checker, g: Cand, k: Cand) bool

eats = (c: Checker, x: TyId, y: TyId, owner: str) bool

var_of = (c: Checker, x: TyId, owner: str) bool

structural_eats = (c: Checker, x: TyId, y: TyId, owner: str) bool

fn_eats = (c: Checker, f: TyFn, y: TyId, owner: str) bool

named_eats = (c: Checker, n: TyNamed, y: TyId, owner: str) bool

all_eats = (c: Checker, xs: Vec<TyId>, ys: Vec<TyId>, owner: str) bool

duplicate = (c :: Checker, name: str, a: Cand, b: Cand) Res<(), AllocError>

ambiguous = (c :: Checker, name: str, a: Cand, b: Cand) Res<(), AllocError>
```

#### Imports and re-exports

```zen
Expr, ExprId, Call, Arg, Access, Lambda, Param, Span, Paren, nowhere = std.ast

Ast = std.ast.ast_arena

Alloc, AllocError = std.mem

Vec = std.collections

str = std.text

Range = std.core

DeclId = sema.sema_id

TyId, TyFn, TyNamed = sema.sema_ty

Def = sema.sema_def

SemaFault, NameFault, TypeFault, PairFault = sema.sema_diag

Checker, Ctx = sema.sema_check

refuse_handle_argument = sema.sema_handle

meta_refused = sema.sema_meta

meta_member_call, MetaCall = sema.sema_meta

construct, instantiate, variant_call_type = sema.sema_apply

Inst, subst, subst_list, unify_list = sema.sema_inst

is_case = sema.sema_match

Found, Base, base_of, members_of, actor_spawn_ret, ref_of_actor = sema.sema_member

is_type_def, opaque, first_found = sema.sema_member

static_access = sema.sema_static

first_hidden, hidden_member = sema.sema_member

check_bounds = sema.sema_bound

check_literal = sema.sema_trap

check_arms, check_arms_agree = sema.sema_hoist

bound_declares = sema.sema_supply

type_of, block_type = sema.sema_type

push_tparams, module_name = sema.sema_inst

param_type, type_from_ast = sema.sema_denote

alias_module, module_not_a_value = sema.sema_module

cands_of, travelled_cands, matches = sema.sema_cand

ty_at, is_tvar, recv_sig_fits = sema.sema_cand
```

### `src/sema/sema_cand.zen`

55 declarations (functions: 41, imports and re-exports: 14).

#### Functions

```zen
travelled_cands* = (
    c    :: Checker,
    name : str,
    recv : Res<TyId>,
    out  :: Vec<Cand>
) Res<(), AllocError>

travelled_of = (c :: Checker, name: str, rty: TyId, out :: Vec<Cand>)
               Res<(), AllocError>

travelled_def = (c :: Checker, d: Def, rty: TyId, out :: Vec<Cand>)
                Res<(), AllocError>

keep_travelled = (c :: Checker, k: Cand, rty: TyId, out :: Vec<Cand>)
                 Res<(), AllocError>

takes_receiver = (c :: Checker, k: Cand, rty: TyId) Res<bool, AllocError>

has_cand = (out: Vec<Cand>, id: DeclId) bool

cands_of* = (c :: Checker, mi: usize, name: str, out :: Vec<Cand>)
            Res<(), AllocError>

cand_of = (c :: Checker, d: Def, out :: Vec<Cand>) Res<(), AllocError>

cand_from_decl = (c :: Checker, d: Def, dec: Decl, out :: Vec<Cand>)
                 Res<(), AllocError>

add_cand = (c :: Checker, d: Def, dec: Decl, f: Function, out :: Vec<Cand>)
           Res<(), AllocError>

make_cand = (c :: Checker, d: Def, dec: Decl, f: Function)
            Res<Cand, AllocError>

push_fn_tparams = (c :: Checker, f: Function, owner: str) Res<(), AllocError>

collect_bounds = (c :: Checker, f: Function, ctx: Ctx, out :: Vec<TBound>)
                 Res<(), AllocError>

tparam_bounds = (c :: Checker, tp: TParam, ctx: Ctx, out :: Vec<TBound>)
                Res<(), AllocError>

matches* = (c :: Checker, cand: Cand, actuals: Vec<Actual>)
           Res<bool, AllocError>

any_named = (actuals: Vec<Actual>) bool

by_arity = (c :: Checker, cand: Cand, actuals: Vec<Actual>)
           Res<bool, AllocError>

fixed_matches = (c :: Checker, cand: Cand, actuals: Vec<Actual>)
                Res<bool, AllocError>

variadic_matches = (c :: Checker, cand: Cand, actuals: Vec<Actual>)
                   Res<bool, AllocError>

marker_matches = (c :: Checker, cand: Cand, actuals: Vec<Actual>)
                 Res<bool, AllocError>

pack_sig_fits* = (
    c       :: Checker,
    ps      : Vec<TyId>,
    actuals : Vec<Actual>,
    off     : usize,
    slot    : usize
) Res<bool, AllocError>

pack_arity_fits = (
    c       :: Checker,
    ps      : Vec<TyId>,
    actuals : Vec<Actual>,
    off     : usize,
    fixed   : usize
) Res<bool, AllocError>

prefix_then_pack = (
    c       :: Checker,
    ps      : Vec<TyId>,
    actuals : Vec<Actual>,
    off     : usize,
    fixed   : usize
) Res<bool, AllocError>

pack_tail_fits = (
    c       :: Checker,
    actuals : Vec<Actual>,
    fixed   : usize,
    pack    : TyId
) Res<bool, AllocError>

pack_forwarded = (c :: Checker, actuals: Vec<Actual>, fixed: usize, pack: TyId)
            Res<bool, AllocError>

spread_fits = (c :: Checker, actuals: Vec<Actual>, fixed: usize, elem: TyId)
              Res<bool, AllocError>

pack_element_of = (c: Checker, pack: TyId) TyId

fits_at_ty = (c :: Checker, actuals: Vec<Actual>, i: usize, want: TyId)
             Res<bool, AllocError>

is_variadic = (c: Checker, cand: Cand) bool

tail_swallows* = (c: Checker, tail: TyId) bool

all_fit = (c :: Checker, cand: Cand, actuals: Vec<Actual>, n: usize)
          Res<bool, AllocError>

fits_at = (c :: Checker, cand: Cand, actuals: Vec<Actual>, i: usize)
          Res<bool, AllocError>

fits = (c :: Checker, a: Actual, p: TyId) Res<bool, AllocError>

value_fits = (c :: Checker, a: Actual, p: TyId) Res<bool, AllocError>

recv_sig_fits* = (c :: Checker, ps: Vec<TyId>, actuals: Vec<Actual>)
                 Res<bool, AllocError>

recv_fixed_fits = (c :: Checker, ps: Vec<TyId>, actuals: Vec<Actual>)
                  Res<bool, AllocError>

args_fit = (c :: Checker, ps: Vec<TyId>, actuals: Vec<Actual>)
           Res<bool, AllocError>

arg_fits_at = (c :: Checker, ps: Vec<TyId>, actuals: Vec<Actual>, i: usize)
              Res<bool, AllocError>

closure_fits = (c: Checker, p: TyId, arity: usize) bool

is_tvar* = (c: Checker, id: TyId) bool

ty_at* = (v: Vec<TyId>, i: usize) TyId
```

#### Imports and re-exports

```zen
Decl, Function, TParam = std.ast

AllocError = std.mem

Vec = std.collections

str = std.text

Range = std.core

DeclId = sema.sema_id

TyId = sema.sema_ty

Def, decl_at = sema.sema_def

Checker, Ctx, UNRESOLVED = sema.sema_check

tparam_vars = sema.sema_inst

Cand, TBound, Actual = sema.sema_call

satisfies_bound = sema.sema_bound

type_from_ast, param_type = sema.sema_denote

pack_elem, pack_slot = sema.sema_vararg
```

### `src/sema/sema_case.zen`

27 declarations (types: 1, functions: 16, imports and re-exports: 10).

#### Types

```zen
Case* = {
    name*: str,
    payload*: TyId,
    has_payload*: bool,
}
```

#### Functions

```zen
cases_of* = (c :: Checker, ty: TyId, out :: Vec<Case>) Res<bool, AllocError>

case_payload* = (c :: Checker, ty: TyId, name: str) Res<TyId, AllocError>

case_arity* = (c :: Checker, ty: TyId, name: str, wrote_sub: bool)
              Res<usize, AllocError>

find_case* = (cases: Vec<Case>, name: str) Res<Case>

bool_to_arity = (b: bool) usize

bool_cases = (c :: Checker, name: str, out :: Vec<Case>) Res<bool, AllocError>

add_bool = (c :: Checker, out :: Vec<Case>) Res<bool, AllocError>

res_cases = (c :: Checker, r: TyRes, out :: Vec<Case>) Res<bool, AllocError>

add_err = (c :: Checker, r: TyRes, out :: Vec<Case>) Res<(), AllocError>

add_none = (c :: Checker, out :: Vec<Case>) Res<(), AllocError>

named_cases = (c :: Checker, n: TyNamed, out :: Vec<Case>)
              Res<bool, AllocError>

enum_cases = (c :: Checker, d: Decl, n: TyNamed, out :: Vec<Case>)
             Res<bool, AllocError>

variant_cases = (c :: Checker, e: Enum, n: TyNamed, out :: Vec<Case>)
                Res<bool, AllocError>

add_members = (c :: Checker, e: Enum, n: TyNamed, out :: Vec<Case>)
              Res<bool, AllocError>

add_variants = (c :: Checker, e: Enum, n: TyNamed, out :: Vec<Case>)
               Res<bool, AllocError>

variant_payload* = (c :: Checker, v: Variant, ctx: Ctx) Res<TyId, AllocError>
```

#### Imports and re-exports

```zen
Decl, Enum, Variant = std.ast

AllocError = std.mem

Vec = std.collections

str = std.text

Range = std.core

TyId, TyNamed, TyRes = sema.sema_ty

decl_at = sema.sema_def

Checker, Ctx = sema.sema_check

type_from_ast = sema.sema_denote

union_reading, union_member = sema.sema_union
```

### `src/sema/sema_check.zen`

30 declarations (types: 4, functions: 10, constants: 1, imports and re-exports: 15).

#### Types

```zen
Binding* = {
    name*: str,
    ty*: TyId,
    mutable*: bool,
    param*: bool,
    span*: Span,
}

WalkBind* = {
    h_name*: str,
    h_span*: Span,
    f_name*: str,
    f_span*: Span,
    field*: str,
}

Ctx* = {
    module*: usize,
    ret*: TyId,
    has_ret*: bool,
    self_ty*: TyId,
    has_self*: bool,
}

Checker* = {
    tree*: Ast,
    world* :: World,
    types* :: Types,
    diags :: Vec<Diag>,
    expr_memo* :: Map<ExprId, TyId>,
    type_memo* :: Map<TypeId, TyId>,
    meta_memo* :: Map<TypeId, str>,
    meta_count_memo* :: Map<TypeId, usize>,
    meta_walks* :: Map<ExprId, Vec<str>>,
    meta_name_reads* :: Map<ExprId, bool>,
    meta_projs* :: Map<ExprId, bool>,
    walk_stack :: Vec<WalkBind>,
    walk_now :: Vec<str>,
    meta_recheck :: usize,
    supply_memo* :: Map<ExprId, TyId>,
    call_memo* :: Map<ExprId, DeclId>,
    param_memo* :: Map<ExprId, bool>,
    callee_access* :: Map<ExprId, bool>,
    inst_memo* :: Map<ExprId, Inst>,
    edges :: Vec<InstEdge>,
    owner_now :: str = "",
    set_memo* :: Map<TyId, TyId>,
    raised :: Vec<TyId>,
    locals :: Vec<Binding>,
    block_base :: usize,
    tvars :: Vec<Binding>,
    bounds :: Vec<Binding>,
    alloc*: Alloc,
    diag_count* = (self: @Self) usize
    diag_at* = (self: @Self, i: usize) Res<Diag>
    type_store* = (self: @Self) Types
    resolved_call* = (self: @Self, id: ExprId) Res<DeclId>
    resolve_call* = (self :: @Self, id: ExprId, d: DeclId)
                    Res<(), AllocError>
    meta_str* = (self: @Self, t: TypeId) Res<str>
    meta_count_of* = (self: @Self, t: TypeId) Res<usize>
    meta_walk_of* = (self: @Self, id: ExprId) Res<Vec<str>>
    meta_name_read* = (self: @Self, id: ExprId) bool
    meta_proj* = (self: @Self, id: ExprId) bool
    walk_row* = (self: @Self) Res<WalkBind>
    push_walk* = (self :: @Self, b: WalkBind) Res<(), AllocError>
    pop_walk* = (self :: @Self) ()
    push_walk_now* = (self :: @Self, name: str) Res<(), AllocError>
    pop_walk_now* = (self :: @Self) ()
    walk_field_now* = (self: @Self) Res<str>
    rechecking* = (self: @Self) bool
    enter_recheck* = (self :: @Self) ()
    leave_recheck* = (self :: @Self) ()
    meta_count_type* = (self :: @Self) Res<TyId, AllocError>
    resolved_inst* = (self: @Self, id: ExprId) Res<Inst>
    resolve_inst* = (self :: @Self, id: ExprId, inst: Inst)
                    Res<(), AllocError>
    note_edge* = (self :: @Self, e: InstEdge) Res<(), AllocError>
    edge_count* = (self: @Self) usize
    edge_at* = (self: @Self, i: usize) Res<InstEdge>
    enter_owner* = (self :: @Self, owner: str) ()
    owner_of_body* = (self: @Self) str
    modules* = (self: @Self) World
    render_diags* = (self: @Self, out :: String) Res<(), AllocError>
    report* = (self :: @Self, file: str, span: Span, fault: SemaFault)
              Res<(), AllocError>
    mark* = (self: @Self) usize
    enter_block* = (self :: @Self) usize
    leave_block* = (self :: @Self, was: usize) ()
    lookup_here* = (self: @Self, name: str) Res<Binding>
    bind* = (self :: @Self, name: str, ty: TyId, mutable: bool, param: bool)
            Res<(), AllocError>
    bind_at* = (self :: @Self, name: str, ty: TyId, mutable: bool,
                param: bool, span: Span) Res<(), AllocError>
    release* = (self :: @Self, mark: usize) Res<(), AllocError>
    detach_locals* = (self :: @Self, mark: usize, saved :: Vec<Binding>)
                     Res<(), AllocError>
    reattach_locals* = (self :: @Self, saved: Vec<Binding>)
                       Res<(), AllocError>
    tvar_mark* = (self: @Self) usize
    push_tvar* = (self :: @Self, name: str, ty: TyId) Res<(), AllocError>
    release_tvars* = (self :: @Self, mark: usize) Res<(), AllocError>
    lookup_tvar* = (self: @Self, name: str) Res<Binding>
    bound_mark* = (self: @Self) usize
    push_bound* = (self :: @Self, name: str, ty: TyId) Res<(), AllocError>
    release_bounds* = (self :: @Self, mark: usize) Res<(), AllocError>
    has_bound* = (self: @Self, ty: TyId) bool
    is_bounded* = (self: @Self, name: str) bool
    bounds_of* = (self: @Self, name: str, out :: Vec<TyId>)
                 Res<(), AllocError>
    lookup* = (self: @Self, name: str) Res<Binding>
    assignable* = (self: @Self, got: TyId, want: TyId) bool
    array_assignable = (self: @Self, got: TyId, want: TyId) bool
    array_fits = (self: @Self, g: TyArray, want: TyId) bool
    res_assignable = (self: @Self, got: TyId, want: TyId) bool
    res_fits = (self: @Self, g: TyRes, want: TyId) bool
    res_parts_fit = (self: @Self, g: TyRes, w: TyRes) bool
    uninstantiated = (self: @Self, got: TyId, want: TyId) bool
    same_type* = (self: @Self, a: TyId, b: TyId) bool
    same_applied = (self: @Self, got: TyId, want: TyId) bool
    applied_to = (self: @Self, g: TyNamed, want: TyId) bool
    args_agree = (self: @Self, g: Vec<TyId>, w: Vec<TyId>) bool
    wrote_no_args = (self: @Self, w: Vec<TyId>) bool
    every_arg_agrees = (self: @Self, g: Vec<TyId>, w: Vec<TyId>) bool
    arg_disagrees = (self: @Self, g: Vec<TyId>, w: Vec<TyId>, i: usize) bool
    arg_unlike = (self: @Self, a: TyId, w: Vec<TyId>, i: usize) bool
    raised_mark* = (self: @Self) usize
    access_at* = (self: @Self, id: ExprId) Res<Access>
    raise* = (self :: @Self, e: TyId) Res<(), AllocError>
    take_raised* = (self :: @Self, mark: usize, out :: Vec<TyId>)
                   Res<(), AllocError>
    set_of* = (self: @Self, id: TyId) TyId
    set_assignable = (self: @Self, got: TyId, want: TyId) bool
    literal_fits = (self: @Self, got: TyId, want: TyId) bool
    float_fits = (self: @Self, got: TyId, want: TyId) bool
    coerce* = (self :: @Self, file: str, span: Span, got: TyId, want: TyId,
               name: str) Res<(), AllocError>
    mismatch* = (self :: @Self, file: str, span: Span, got: TyId, want: TyId,
                 name: str) Res<(), AllocError>
    nullary_settles* = (self: @Self, got: TyId, want: TyId) bool
    check_not* = (self :: @Self, u: Unary, inner: TyId)
                 Res<TyId, AllocError>
    check_logical* = (self :: @Self, b: Binary, lhs: TyId, rhs: TyId)
                     Res<(), AllocError>
    logical_operands = (self :: @Self, b: Binary, lhs: TyId, rhs: TyId)
                       Res<(), AllocError>
    is_unknown* = (self: @Self, id: TyId) bool
    is_infer* = (self: @Self, id: TyId) bool
    is_var* = (self: @Self, id: TyId) bool
    prim_name* = (self: @Self, id: TyId) str
    is_literal_ty* = (self: @Self, id: TyId) bool
    is_int_literal = (self: @Self, id: TyId) bool
    is_float_literal = (self: @Self, id: TyId) bool
}
```

#### Functions

```zen
Checker* = (a: Alloc, tree: Ast) Res<Checker, AllocError>

check_import_gate = (c :: Checker) Res<(), AllocError>

report_blocked = (c :: Checker, b: ImportBinding) Res<(), AllocError>

Ctx* = (module: usize, none: TyId) Ctx

is_predicate* = (op: BinOp) bool

is_logical* = (op: BinOp) bool

forms_fit* = (got: ResForm, want: ResForm) bool

undecided_or = (f: ResForm, failure: bool) bool

absence_into_failure* = (got: ResForm, want: ResForm) bool

both_failures* = (got: ResForm, want: ResForm) bool
```

#### Constants

```zen
UNRESOLVED* : TyId = TyId(index: 0)
```

#### Imports and re-exports

```zen
Ast, ExprId, TypeId, Span = std.ast

nowhere = std.ast

BinOp, Unary, Binary, Access = std.ast

Alloc, AllocError = std.mem

Vec, Map = std.collections

str, String = std.text

Range = std.core

DeclId = sema.sema_id

TyId, Types, ResForm, TyRes, TyNamed, TyArray = sema.sema_ty

is_integer, is_float = sema.sema_ty

World, ImportBinding = sema.sema_def

module_display = sema.sema_def

Diag, SemaFault, TypeFault = sema.sema_diag

ExportFault = sema.sema_diag

Inst, InstEdge = sema.sema_inst
```

### `src/sema/sema_const.zen`

64 declarations (functions: 51, constants: 4, imports and re-exports: 9).

#### Functions

```zen
counted_array* = (c :: Checker, elem: TyId, id: ExprId, ctx: Ctx)
                Res<TyId, AllocError>

count_refused = (c :: Checker, id: ExprId) Res<TyId, AllocError>

written_count = (node: Expr) str

count_int = (c :: Checker, id: ExprId, ctx: Ctx) Res<Res<i64>, AllocError>

count_through_name = (c :: Checker, id: ExprId, ctx: Ctx)
                     Res<Res<i64>, AllocError>

count_of_const = (c :: Checker, text: str, ctx: Ctx)
                 Res<Res<i64>, AllocError>

count_of_def = (c: Checker, d: Def) Res<i64>

const_def* = (c :: Checker, text: str, ctx: Ctx) Res<Res<Def>, AllocError>

len_of* = (v: i64) usize

last_digit = (v: i64) usize

const_int* = (c: Checker, id: ExprId) Res<i64>

const_within = (c: Checker, id: ExprId, left: usize) Res<i64>

const_node = (c: Checker, node: Expr, left: usize) Res<i64>

const_literal* = (l: Literal) Res<i64>

const_unary = (c: Checker, u: Unary, left: usize) Res<i64>

negate = (c: Checker, id: ExprId, left: usize) Res<i64>

const_binary = (c: Checker, b: Binary, left: usize) Res<i64>

const_rhs = (c: Checker, b: Binary, x: i64, left: usize) Res<i64>

const_prim_const = (c: Checker, a: Access) Res<i64>

prim_const_value = (type_name: str, member: str) Res<i64>

float_bits = (type_name: str, member: str) Res<i64>

named_const = (type_name: str, member: str) Res<i64>

min_or_bits = (type_name: str, member: str) Res<i64>

bits_const = (type_name: str, member: str) Res<i64>

fold* = (op: BinOp, x: i64, y: i64) Res<i64>

add_i64 = (x: i64, y: i64) Res<i64>

sub_i64 = (x: i64, y: i64) Res<i64>

mul_i64 = (x: i64, y: i64) Res<i64>

small = (v: i64) bool

fits* = (v: i64, name: str) Res<bool>

signed_of = (name: str) bool

max_of* = (name: str) Res<i64>

min_of* = (name: str) Res<i64>

signed_max = (name: str) Res<i64>

signed_max_16 = (name: str) Res<i64>

signed_max_32 = (name: str) Res<i64>

signed_min = (name: str) Res<i64>

signed_min_16 = (name: str) Res<i64>

signed_min_32 = (name: str) Res<i64>

unsigned_min = (name: str) Res<i64>

unsigned_max = (name: str) Res<i64>

unsigned_max_16 = (name: str) Res<i64>

unsigned_max_32 = (name: str) Res<i64>

bits_of_i64_max* = (name: str) Res<i64>

bits_of_i64_min* = (name: str) Res<i64>

bits_of* = (name: str) Res<i64>

bits_16 = (name: str) Res<i64>

bits_32 = (name: str) Res<i64>

bits_64 = (name: str) Res<i64>

bits_float = (name: str) Res<i64>

bits_width = (name: str) i64
```

#### Constants

```zen
I64_MAX* : i64 = 9223372036854775807

I64_MIN* : i64 = -9223372036854775807 - 1

FOLD_LIMIT* : i64 = 2147483647

FOLD_DEPTH: usize = 256
```

#### Imports and re-exports

```zen
Expr, ExprId, Binary, BinOp, Literal = std.ast

Unary, Access, Paren, Name, Const = std.ast

AllocError = std.mem

Vec = std.collections

str = std.text

TyId, is_integer = sema.sema_ty

SemaFault, NameFault = sema.sema_diag

Def, decl_at = sema.sema_def

Checker, Ctx = sema.sema_check
```

### `src/sema/sema_cycle.zen`

55 declarations (types: 2, functions: 47, imports and re-exports: 6).

#### Types

```zen
ConstSite = {
    module: usize,
    span:   Span,
}

Edge = {
    from: usize,
    to:   usize,
}
```

#### Functions

```zen
check_module_graph* = (a: Alloc, tree: Ast, w: World, out :: String)
                      Res<usize, AllocError>

self_imports = (a: Alloc, tree: Ast, w: World, out :: String)
               Res<usize, AllocError>

module_self_imports = (
    a    : Alloc,
    tree : Ast,
    w    : World,
    mi   : usize,
    out  :: String
) Res<usize, AllocError>

decls_self_import = (a: Alloc, w: World, m: Module, mi: usize, out :: String)
                    Res<usize, AllocError>

decl_self_import = (
    a   : Alloc,
    w   : World,
    m   : Module,
    d   : Decl,
    mi  : usize,
    out :: String
) Res<usize, AllocError>

import_self = (
    a   : Alloc,
    w   : World,
    m   : Module,
    im  : Import,
    mi  : usize,
    out :: String
) Res<usize, AllocError>

say_self_import = (m: Module, at: Span, out :: String)
                  Res<usize, AllocError>

const_cycles = (a: Alloc, tree: Ast, w: World, out :: String)
               Res<usize, AllocError>

cycles_in = (a: Alloc, tree: Ast, w: World, es: Vec<Edge>, out :: String)
            Res<usize, AllocError>

cycle_at = (
    a    : Alloc,
    tree : Ast,
    w    : World,
    es   : Vec<Edge>,
    mi   : usize,
    out  :: String
) Res<usize, AllocError>

report_component = (
    a      : Alloc,
    tree   : Ast,
    w      : World,
    es     : Vec<Edge>,
    mi     : usize,
    onward : Vec<usize>,
    out    :: String
)
                   Res<usize, AllocError>

component_of = (a: Alloc, es: Vec<Edge>, mi: usize, onward: Vec<usize>)
               Res<Vec<usize>, AllocError>

keep_if_mutual = (
    a    : Alloc,
    es   : Vec<Edge>,
    mi   : usize,
    j    : usize,
    comp :: Vec<usize>
) Res<(), AllocError>

add_if_reaches = (
    a    : Alloc,
    es   : Vec<Edge>,
    mi   : usize,
    j    : usize,
    comp :: Vec<usize>
) Res<(), AllocError>

first_named = (w: World, comp: Vec<usize>, mi: usize) bool

module_name_of = (w: World, mi: usize) str

say_cycle = (
    a    : Alloc,
    tree : Ast,
    w    : World,
    es   : Vec<Edge>,
    mi   : usize,
    comp : Vec<usize>,
    out  :: String
) Res<usize, AllocError>

write_hop = (out :: String, name: str, k: usize) Res<(), AllocError>

shortest_cycle = (a: Alloc, es: Vec<Edge>, start: usize, comp: Vec<usize>)
                 Res<Vec<usize>, AllocError>

visit_edge = (
    e      : Edge,
    from   : usize,
    at     : usize,
    start  : usize,
    comp   : Vec<usize>,
    order  :: Vec<usize>,
    prev   :: Vec<usize>,
    closed :: Vec<usize>
)
             Res<(), AllocError>

take_edge = (
    to     : usize,
    at     : usize,
    start  : usize,
    comp   : Vec<usize>,
    order  :: Vec<usize>,
    prev   :: Vec<usize>,
    closed :: Vec<usize>
)
            Res<(), AllocError>

close_cycle = (at: usize, closed :: Vec<usize>) Res<(), AllocError>

open_edge = (
    to    : usize,
    at    : usize,
    comp  : Vec<usize>,
    order :: Vec<usize>,
    prev  :: Vec<usize>
) Res<(), AllocError>

unwind_cycle = (
    a      : Alloc,
    order  : Vec<usize>,
    prev   : Vec<usize>,
    closed : Vec<usize>,
    start  : usize
) Res<Vec<usize>, AllocError>

reach_from = (a: Alloc, es: Vec<Edge>, start: usize)
             Res<Vec<usize>, AllocError>

step_reach = (e: Edge, from: usize, seen :: Vec<usize>, front :: Vec<usize>)
             Res<(), AllocError>

const_edges = (a: Alloc, tree: Ast, w: World) Res<Vec<Edge>, AllocError>

const_sites = (a: Alloc, tree: Ast) Res<Vec<ConstSite>, AllocError>

module_const_sites = (tree: Ast, mi: usize, sites :: Vec<ConstSite>)
                     Res<(), AllocError>

decl_const_sites = (m: Module, mi: usize, sites :: Vec<ConstSite>)
                   Res<(), AllocError>

keep_const_site = (d: Decl, mi: usize, sites :: Vec<ConstSite>)
                  Res<(), AllocError>

name_edges = (
    a     : Alloc,
    tree  : Ast,
    w     : World,
    sites : Vec<ConstSite>,
    e     : Expr,
    es    :: Vec<Edge>
) Res<(), AllocError>

site_edges = (
    a     : Alloc,
    w     : World,
    sites : Vec<ConstSite>,
    at    : Span,
    name  : str,
    es    :: Vec<Edge>
) Res<(), AllocError>

site_of = (sites: Vec<ConstSite>, at: Span) Res<usize>

site_module = (sites: Vec<ConstSite>, k: usize) Res<usize>

encloses = (outer: Span, at: Span) bool

resolved_edges = (a: Alloc, w: World, mi: usize, name: str, es :: Vec<Edge>)
                 Res<(), AllocError>

keep_const_edge = (d: Def, mi: usize, es :: Vec<Edge>) Res<(), AllocError>

is_const = (k: DefKind) bool

add_edge = (from: usize, to: usize, es :: Vec<Edge>) Res<(), AllocError>

has_edge = (es: Vec<Edge>, from: usize, to: usize) bool

edge_span = (a: Alloc, tree: Ast, w: World, from: usize, to: usize)
            Res<Span, AllocError>

module_edge_span = (a: Alloc, w: World, m: Module, to: usize)
                   Res<Span, AllocError>

keep_import_span = (
    a     : Alloc,
    w     : World,
    d     : Decl,
    to    : usize,
    spans :: Vec<Span>
) Res<(), AllocError>

keep_if_names = (
    a     : Alloc,
    w     : World,
    im    : Import,
    to    : usize,
    spans :: Vec<Span>
) Res<(), AllocError>

names_module = (w: World, path: str, mi: usize) bool

write_where = (out :: String, at: Span) Res<(), AllocError>
```

#### Imports and re-exports

```zen
Ast, Module, Decl, Expr, Import, Pos, Span, ExprId, nowhere = std.ast

Alloc, AllocError = std.mem

Vec = std.collections

str, String = std.text

Range = std.core

World, Def, DefKind, dotted, module_display = sema.sema_def
```

### `src/sema/sema_decl.zen`

72 declarations (functions: 44, imports and re-exports: 28).

#### Functions

```zen
check_module* = (c :: Checker, mi: usize) Res<(), AllocError>

check_all* = (c :: Checker) Res<(), AllocError>

check_table = (c :: Checker, t: ModuleTable, mi: usize)
              Res<(), AllocError>

check_overload_sets = (c :: Checker, t: ModuleTable, mi: usize)
                      Res<(), AllocError>

one_set = (c :: Checker, d: Def, mi: usize, seen :: Vec<str>)
          Res<(), AllocError>

new_set = (c :: Checker, name: str, mi: usize, seen :: Vec<str>)
          Res<(), AllocError>

is_fn_def = (k: DefKind) bool

has_name = (seen: Vec<str>, name: str) bool

check_bodies = (c :: Checker, mi: usize) Res<(), AllocError>

check_decls = (c :: Checker, m: Module, mi: usize) Res<(), AllocError>

check_decl = (c :: Checker, d: Decl, m: Module, mi: usize)
             Res<(), AllocError>

const_body = (c :: Checker, k: Const, mi: usize) Res<(), AllocError>

const_fits = (c :: Checker, id: ExprId, t: TypeId, got: TyId, ctx: Ctx)
             Res<(), AllocError>

enum_payloads = (c :: Checker, e: Enum, mi: usize) Res<(), AllocError>

check_members = (c :: Checker, e: Enum, mi: usize)
                Res<(), AllocError>

report_member_miss = (c :: Checker, e: Enum, at: usize)
                     Res<(), AllocError>

binds_nothing = (c :: Checker, mi: usize, name: str) Res<bool, AllocError>

binds_a_type = (c :: Checker, mi: usize, name: str) Res<bool, AllocError>

struct_bodies = (c :: Checker, s: Struct, m: Module, mi: usize)
                Res<(), AllocError>

check_member_overloads = (c :: Checker, s: Struct, self_ty: TyId, mi: usize)
                         Res<(), AllocError>

compare_member_signatures = (
    c       :: Checker,
    a       : Member,
    b       : Member,
    self_ty : TyId,
    mi      : usize
) Res<(), AllocError>

check_fields = (c :: Checker, s: Struct) Res<(), AllocError>

unique_field = (c :: Checker, name: Ident, seen :: Vec<Ident>)
               Res<(), AllocError>

impl_bodies = (c :: Checker, im: Impl, m: Module, mi: usize)
              Res<(), AllocError>

field_value = (
    c       :: Checker,
    mem     : Member,
    im      : Impl,
    self_ty : TyId,
    mi      : usize
) Res<(), AllocError>

supplies_fn = (c :: Checker, ty: TyId) Res<bool, AllocError>

named_self = (c :: Checker, name: str, mi: usize) Res<TyId, AllocError>

enter_target_tvars = (c :: Checker, name: str, mi: usize)
                     Res<(), AllocError>

target_decl = (c :: Checker, name: str, mi: usize)
              Res<Res<Def>, AllocError>

target_tvars = (c :: Checker, d: Def, mi: usize) Res<(), AllocError>

target_decl_tvars = (c :: Checker, d: Decl, mi: usize)
                    Res<(), AllocError>

member_body = (
    c       :: Checker,
    mem     : Member,
    self_ty : TyId,
    m       : Module,
    mi      : usize
) Res<(), AllocError>

member_fn_body = (
    c       :: Checker,
    f       : Function,
    self_ty : TyId,
    m       : Module,
    mi      : usize
) Res<(), AllocError>

check_function* = (c :: Checker, f: Function, m: Module, mi: usize)
                  Res<(), AllocError>

check_signature = (
    c       :: Checker,
    f       : Function,
    self_ty : Res<TyId>,
    m       : Module,
    mi      : usize
) Res<(), AllocError>

check_body = (
    c       :: Checker,
    f       : Function,
    body    : BlockId,
    self_ty : Res<TyId>,
    m       : Module,
    mi      : usize
) Res<(), AllocError>

body_ctx = (c :: Checker, f: Function, mi: usize, self_ty: Res<TyId>)
           Res<Ctx, AllocError>

self_or_poison = (self_ty: Res<TyId>, poison: TyId) TyId

self_ty_given = (self_ty: Res<TyId>) bool

is_res = (c: Checker, ty: TyId) bool

enter_generics = (c :: Checker, f: Function, owner: str, mi: usize)
                 Res<(), AllocError>

push_bounds = (c :: Checker, tp: TParam, ctx: Ctx) Res<(), AllocError>

bind_params = (c :: Checker, f: Function, ctx: Ctx) Res<(), AllocError>

qualified = (c :: Checker, m: Module, f: Function) Res<str, AllocError>
```

#### Imports and re-exports

```zen
Module, Decl, Function, TParam, BlockId, Ident = std.ast

Struct, Impl, Member, Enum = std.ast

ExprId, TypeId, Const, Field = std.ast

AllocError = std.mem

Vec = std.collections

str, String = std.text

Range = std.core

TyId = sema.sema_ty

Def, DefKind, ModuleTable, decl_at = sema.sema_def

Checker, Ctx = sema.sema_check

SemaFault, NameFault, PairFault = sema.sema_diag

check_impl = sema.sema_bound

check_overloads, same_fn_signature = sema.sema_call

check_depth = sema.sema_depth

check_varargs = sema.sema_vararg

check_layout = sema.sema_layout

type_of, block_type = sema.sema_type

bound_member_type = sema.sema

type_from_ast, param_type = sema.sema_denote

decl_as_type = sema.sema_type

enter_struct_tvars, member_type = sema.sema_member

variant_payload = sema.sema_case

owner_of, push_tparams = sema.sema_inst

settle_raised = sema.sema_raise

check_return = sema.sema_hoist

check_literal = sema.sema_trap

check_arms = sema.sema_hoist

check_own = sema.sema_own
```

### `src/sema/sema_def.zen`

39 declarations (types: 5, enums: 1, functions: 24, constants: 2, imports and re-exports: 7).

#### Types

```zen
Def* = {
    name*: str,
    qname*: str,
    kind*: DefKind,
    id*: DeclId,
    exported*: bool,
    span*: Span,
}

ImportBinding* = {
    name*: str,
    module*: str,
    exported*: bool,
    span*: Span,
}

ModuleTable* = {
    name*: str,
    index*: u32,
    defs* :: Vec<Def>,
    imports* :: Vec<ImportBinding>,
    impls* :: Vec<ImplId>,
}

WorldIndex = {
    exported :: Map<str, Vec<Def>>,
    impls :: Map<str, Vec<ImplId>>,
    members :: Map<DeclId, Map<str, Vec<usize>>>,
}

World* = {
    tables :: Vec<ModuleTable>,
    exact :: Map<str, usize>,
    folders :: Map<str, usize>,
    index: Ptr<WorldIndex>,
    alloc: Alloc,
    count* = (self: @Self) usize
    table_at* = (self: @Self, i: usize) Res<ModuleTable>
    module_name* = (self: @Self, id: DeclId) str
    index_of* = (self: @Self, name: str) Res<usize>
    member_rows* = (self: @Self, id: DeclId, name: str) Res<Vec<usize>>
    defs_of* = (self: @Self, mi: usize, name: str, out :: Vec<Def>)
               Res<(), AllocError>
    first_def_of* = (self: @Self, mi: usize, name: str)
                    Res<Res<Def>, AllocError>
    first_after_own = (self: @Self, mi: usize, name: str)
                      Res<Res<Def>, AllocError>
    first_own* = (self: @Self, mi: usize, name: str) Res<Def>
    first_prelude_of* = (self: @Self, name: str)
                        Res<Res<Def>, AllocError>
    first_prelude_for = (self: @Self, mi: usize, name: str)
                        Res<Res<Def>, AllocError>
    first_imported = (self: @Self, mi: usize, name: str)
                     Res<Res<Def>, AllocError>
    first_exported = (self: @Self, mi: usize, name: str)
                     Res<Res<Def>, AllocError>
    first_exports = (self: @Self, mi: usize, name: str, seen :: Vec<usize>)
                    Res<Res<Def>, AllocError>
    first_exported_own = (self: @Self, mi: usize, name: str) Res<Def>
    first_follow = (self: @Self, mi: usize, name: str,
                    seen :: Vec<usize>, reexport: bool)
                   Res<Res<Def>, AllocError>
    first_follow_fresh = (self: @Self, mi: usize, name: str,
                          seen :: Vec<usize>, reexport: bool)
                         Res<Res<Def>, AllocError>
    first_follow_imports = (self: @Self, t: ModuleTable, name: str,
                            seen :: Vec<usize>, reexport: bool)
                           Res<Res<Def>, AllocError>
    binds_name* = (self: @Self, mi: usize, name: str) bool
    prelude_defs = (self: @Self, mi: usize, name: str, out :: Vec<Def>)
                   Res<(), AllocError>
    prelude_index* = (self: @Self) Res<usize>
    prelude_exports = (self: @Self, p: usize, mi: usize, name: str,
                       out :: Vec<Def>) Res<(), AllocError>
    exported_defs* = (self: @Self, p: usize, name: str, out :: Vec<Def>)
                     Res<(), AllocError>
    prelude_of* = (self: @Self, name: str, out :: Vec<Def>)
                  Res<(), AllocError>
    is_prelude_decl* = (self: @Self, id: DeclId, name: str)
                       Res<bool, AllocError>
    exported_named* = (self: @Self, name: str, out :: Vec<Def>)
                      Res<(), AllocError>
    own_defs* = (self: @Self, mi: usize, name: str, out :: Vec<Def>)
                Res<(), AllocError>
    imported_defs* = (self: @Self, mi: usize, name: str, out :: Vec<Def>)
                     Res<(), AllocError>
    exports_of* = (self: @Self, mi: usize, name: str, out :: Vec<Def>,
                   seen :: Vec<usize>) Res<(), AllocError>
    follow = (self: @Self, mi: usize, name: str, out :: Vec<Def>,
              seen :: Vec<usize>, reexport: bool) Res<(), AllocError>
    follow_fresh = (self: @Self, mi: usize, name: str, out :: Vec<Def>,
                    seen :: Vec<usize>, reexport: bool) Res<(), AllocError>
    follow_imports = (self: @Self, t: ModuleTable, name: str, out :: Vec<Def>,
                      seen :: Vec<usize>, reexport: bool) Res<(), AllocError>
    follow_one = (self: @Self, binding: ImportBinding, name: str,
                  out :: Vec<Def>, seen :: Vec<usize>) Res<(), AllocError>
    impls_named* = (self: @Self, tree: Ast, target: str, out :: Vec<ImplId>)
                   Res<(), AllocError>
    blocked_imports* = (self: @Self, tree: Ast, mi: usize,
                        out :: Vec<ImportBinding>) Res<(), AllocError>
    blocked_in = (self: @Self, tree: Ast, t: ModuleTable, mi: usize,
                  out :: Vec<ImportBinding>) Res<(), AllocError>
    blocked_one = (self: @Self, tree: Ast, b: ImportBinding, mi: usize,
                   out :: Vec<ImportBinding>) Res<(), AllocError>
    blocked_from = (self: @Self, tree: Ast, b: ImportBinding, other: usize,
                    mi: usize, out :: Vec<ImportBinding>)
                   Res<(), AllocError>
    exports_name* = (self: @Self, tree: Ast, mi: usize, name: str,
                     seen :: Vec<usize>) Res<bool, AllocError>
    variant_defs* = (self: @Self, tree: Ast, mi: usize, name: str,
                     out :: Vec<Def>) Res<(), AllocError>
    exports_variant = (self: @Self, tree: Ast, mi: usize, name: str,
                       hits :: Vec<Def>, seen :: Vec<usize>, reexport: bool)
                      Res<(), AllocError>
    variant_walk = (self: @Self, tree: Ast, mi: usize, name: str,
                    hits :: Vec<Def>, seen :: Vec<usize>, reexport: bool)
                   Res<(), AllocError>
    variant_table = (self: @Self, tree: Ast, t: ModuleTable, name: str,
                     hits :: Vec<Def>, seen :: Vec<usize>, reexport: bool)
                    Res<(), AllocError>
    variant_each = (self: @Self, tree: Ast, t: ModuleTable, name: str,
                    hits :: Vec<Def>, seen :: Vec<usize>, reexport: bool)
                   Res<(), AllocError>
    variant_hop = (self: @Self, tree: Ast, b: ImportBinding, name: str,
                   hits :: Vec<Def>, seen :: Vec<usize>, reexport: bool)
                  Res<(), AllocError>
    variant_hop_to = (self: @Self, tree: Ast, module: str, name: str,
                      hits :: Vec<Def>, seen :: Vec<usize>)
                     Res<(), AllocError>
    impl_at* = (self: @Self, tree: Ast, id: ImplId) Res<Impl>
}
```

#### Enums

```zen
DefKind* = StructDef | EnumDef | AliasDef | FunctionDef | ConstDef
```

#### Functions

```zen
World* = (a: Alloc, tree: Ast) Res<World, AllocError>

add_module = (
    w     :: World,
    index :: WorldIndex,
    a     : Alloc,
    tree  : Ast,
    m     : Module,
    i     : usize,
    mi    : u32
) Res<(), AllocError>

index_table = (index :: WorldIndex, a: Alloc, tree: Ast, t: ModuleTable)
              Res<(), AllocError>

index_export = (index :: Map<str, Vec<Def>>, a: Alloc, d: Def)
               Res<(), AllocError>

index_impl = (index :: Map<str, Vec<ImplId>>, a: Alloc, target: str, id: ImplId)
             Res<(), AllocError>

index_members = (
    index   :: Map<DeclId, Map<str, Vec<usize>>>,
    a       : Alloc,
    id      : DeclId,
    members : Vec<Member>
) Res<(), AllocError>

set_first = (index :: Map<str, usize>, name: str, at: usize)
            Res<(), AllocError>

index_decl = (
    t  :: ModuleTable,
    a  : Alloc,
    m  : Module,
    d  : Decl,
    mi : u32,
    di : u32
) Res<(), AllocError>

add_def = (
    t        :: ModuleTable,
    a        : Alloc,
    m        : Module,
    name     : Ident,
    kind     : DefKind,
    exported : bool,
    id       : DeclId,
    span     : Span
) Res<(), AllocError>

add_imports = (t :: ModuleTable, a: Alloc, im: Import) Res<(), AllocError>

dotted* = (a: Alloc, q: QualifiedName) Res<str, AllocError>

last_segment* = (name: str) str

decl_at* = (tree: Ast, id: DeclId) Res<Decl>

copy_defs = (src: Vec<Def>, out :: Vec<Def>) Res<(), AllocError>

copy_impls = (src: Vec<ImplId>, out :: Vec<ImplId>) Res<(), AllocError>

collect_named = (defs: Vec<Def>, name: str, out :: Vec<Def>)
                Res<(), AllocError>

collect_exported = (defs: Vec<Def>, name: str, out :: Vec<Def>)
                   Res<(), AllocError>

imports_name = (t: ModuleTable, name: str) bool

collect_variant = (
    tree  : Ast,
    t     : ModuleTable,
    name  : str,
    gated : bool,
    out   :: Vec<Def>
) Res<(), AllocError>

enum_has_variant = (tree: Ast, d: Def, name: str) bool

named_variant = (e: Enum, name: str) bool

module_display* = (name: str) str

cut_before = (name: str) usize

visited = (seen: Vec<usize>, mi: usize) bool
```

#### Constants

```zen
PRELUDE*: str = "std.core"

PRELUDE_FILE*: str = "std.core.core"
```

#### Imports and re-exports

```zen
Ast, Module, Decl, Ident, Span, QualifiedName, Member = std.ast

Import, Impl, Enum = std.ast

Alloc, AllocError, Ptr = std.mem

Vec, Map = std.collections

str, String = std.text

Range = std.core

DeclId, ImplId = sema.sema_id
```

### `src/sema/sema_denote.zen`

38 declarations (functions: 25, imports and re-exports: 13).

#### Functions

```zen
type_from_ast* = (c :: Checker, id: TypeId, ctx: Ctx)
                 Res<TyId, AllocError>

memoized_type* = (c :: Checker, id: TypeId, ctx: Ctx)
                 Res<TyId, AllocError>

compute_type* = (c :: Checker, id: TypeId, ctx: Ctx)
               Res<TyId, AllocError>

type_kind* = (c :: Checker, node: Type, ctx: Ctx) Res<TyId, AllocError>

self_type* = (c :: Checker, ctx: Ctx) Res<TyId, AllocError>

union_type* = (c :: Checker, members: Vec<TypeId>, ctx: Ctx)
             Res<TyId, AllocError>

fn_type* = (c :: Checker, f: FnType, ctx: Ctx) Res<TyId, AllocError>

param_type* = (c :: Checker, p: Param, ctx: Ctx) Res<TyId, AllocError>

array_type* = (c :: Checker, t: ArrayType, ctx: Ctx)
             Res<TyId, AllocError>

named_type* = (
    c    :: Checker,
    node : Type,
    name : Ident,
    args : Vec<TypeId>,
    ctx  : Ctx
) Res<TyId, AllocError>

res_sugar* = (c :: Checker, name: str, mi: usize)
             Res<bool, AllocError>

res_type* = (c :: Checker, args: Vec<TyId>) Res<TyId, AllocError>

res_failure_of* = (c :: Checker, args: Vec<TyId>, value: TyId)
                 Res<TyId, AllocError>

declared_type* = (
    c    :: Checker,
    node : Type,
    name : Ident,
    args : Vec<TyId>,
    ctx  : Ctx
) Res<TyId, AllocError>

tvar_or_declared* = (
    c    :: Checker,
    node : Type,
    name : Ident,
    args : Vec<TyId>,
    ctx  : Ctx
) Res<TyId, AllocError>

lookup_named* = (
    c    :: Checker,
    node : Type,
    name : Ident,
    args : Vec<TyId>,
    ctx  : Ctx
) Res<TyId, AllocError>

declared_or_alias* = (c :: Checker, d: Def, args: Vec<TyId>)
                    Res<TyId, AllocError>

alias_type* = (c :: Checker, d: Def, args: Vec<TyId>)
             Res<TyId, AllocError>

alias_decl_type* = (c :: Checker, d: Def, args: Vec<TyId>)
                  Res<TyId, AllocError>

alias_written_type* = (c :: Checker, al: Alias, d: Def, args: Vec<TyId>)
                     Res<TyId, AllocError>

alias_target_of* = (c :: Checker, al: Alias, d: Def) Res<TyId, AllocError>

alias_enum* = (c :: Checker, d: Def) Res<TyId>

enum_named_by* = (c :: Checker, ty: TyId) Res<TyId>

enum_decl_of* = (c :: Checker, n: TyNamed, ty: TyId) Res<TyId>

unresolved_type* = (c :: Checker, node: Type, name: Ident)
                  Res<TyId, AllocError>
```

#### Imports and re-exports

```zen
Type, TypeId, Ident, Alias, Enum = std.ast

Param, ArrayType, FnType = std.ast

AllocError = std.mem

Vec = std.collections

TyId, TyNamed, is_prim = sema.sema_ty

Def, decl_at = sema.sema_def

named_or_union = sema.sema_union

SemaFault, NameFault = sema.sema_diag

Checker, Ctx, UNRESOLVED = sema.sema_check

alias_module = sema.sema_module

counted_array = sema.sema_const

def_type = sema.sema_type

push_tparams, module_name = sema.sema_inst
```

### `src/sema/sema_depth.zen`

50 declarations (types: 2, functions: 34, constants: 1, imports and re-exports: 13).

#### Types

```zen
Frame = {
    name: str,
    span: Span,
    size: usize,
}

Walk = {
    frames :: Vec<Frame>,
    visited :: Map<str, bool>,
    done :: bool = false,
    over_budget = (self: @Self) bool
    blamed = (self: @Self) usize
    widens = (self: @Self, i: usize) bool
    frame_size = (self: @Self, i: usize) usize
}
```

#### Functions

```zen
Walk* = (a: Alloc) Walk

check_depth* = (c :: Checker) Res<(), AllocError>

fn_roots = (c :: Checker, w :: Walk) Res<(), AllocError>

fn_root_at = (c :: Checker, i: usize, w :: Walk) Res<(), AllocError>

root_if_settled = (c :: Checker, e: InstEdge, w :: Walk)
                  Res<(), AllocError>

enter = (
    c     :: Checker,
    name  : str,
    span  : Span,
    owner : str,
    tvars : Vec<TyId>,
    args  : Vec<TyId>,
    w     :: Walk
)
        Res<(), AllocError>

enter_now = (
    c     :: Checker,
    name  : str,
    span  : Span,
    owner : str,
    tvars : Vec<TyId>,
    args  : Vec<TyId>,
    w     :: Walk
)
            Res<(), AllocError>

expand = (
    c     :: Checker,
    owner : str,
    tvars : Vec<TyId>,
    args  : Vec<TyId>,
    w     :: Walk
) Res<(), AllocError>

expand_fresh = (
    c     :: Checker,
    owner : str,
    tvars : Vec<TyId>,
    args  : Vec<TyId>,
    key   : str,
    w     :: Walk
)
               Res<(), AllocError>

out_edge = (c :: Checker, owner: str, i: usize, inst: Inst, w :: Walk)
           Res<(), AllocError>

follow = (c :: Checker, owner: str, e: InstEdge, inst: Inst, w :: Walk)
         Res<(), AllocError>

follow_subst = (c :: Checker, e: InstEdge, inst: Inst, w :: Walk)
               Res<(), AllocError>

type_roots = (c :: Checker, w :: Walk) Res<(), AllocError>

type_root_at = (c :: Checker, i: usize, w :: Walk) Res<(), AllocError>

type_root = (c :: Checker, n: TyNamed, w :: Walk) Res<(), AllocError>

enter_type = (
    c    :: Checker,
    name : str,
    span : Span,
    id   : DeclId,
    args : Vec<TyId>,
    w    :: Walk
) Res<(), AllocError>

enter_type_now = (
    c    :: Checker,
    name : str,
    span : Span,
    id   : DeclId,
    args : Vec<TyId>,
    w    :: Walk
) Res<(), AllocError>

expand_type = (c :: Checker, id: DeclId, args: Vec<TyId>, w :: Walk)
              Res<(), AllocError>

expand_decl = (
    c    :: Checker,
    d    : Decl,
    id   : DeclId,
    args : Vec<TyId>,
    w    :: Walk
) Res<(), AllocError>

expand_struct = (
    c    :: Checker,
    s    : Struct,
    id   : DeclId,
    args : Vec<TyId>,
    w    :: Walk
) Res<(), AllocError>

expand_fields = (
    c    :: Checker,
    s    : Struct,
    mi   : usize,
    args : Vec<TyId>,
    key  : str,
    w    :: Walk
) Res<(), AllocError>

struct_inst = (
    c    :: Checker,
    s    : Struct,
    mi   : usize,
    args : Vec<TyId>,
    inst :: Inst
) Res<(), AllocError>

field_edge = (
    c      :: Checker,
    m      : Member,
    mi     : usize,
    poison : TyId,
    inst   : Inst,
    w      :: Walk
) Res<(), AllocError>

field_target = (
    c      :: Checker,
    m      : Member,
    mi     : usize,
    poison : TyId,
    inst   : Inst,
    w      :: Walk
) Res<(), AllocError>

field_step = (c :: Checker, n: TyNamed, span: Span, w :: Walk)
             Res<(), AllocError>

blame = (c :: Checker, w :: Walk) Res<(), AllocError>

settled = (c: Checker, args: Vec<TyId>) bool

args_size = (c: Checker, args: Vec<TyId>) usize

list_size = (c: Checker, list: Vec<TyId>, i: usize) usize

item_size = (c: Checker, list: Vec<TyId>, i: usize) usize

ty_size = (c: Checker, t: TyId) usize

node_key = (c :: Checker, owner: str, args: Vec<TyId>)
           Res<str, AllocError>

key_part = (c :: Checker, args: Vec<TyId>, i: usize, out :: String)
           Res<(), AllocError>

add_key = (c :: Checker, t: TyId, out :: String) Res<(), AllocError>
```

#### Constants

```zen
DEPTH_BUDGET: usize = 24
```

#### Imports and re-exports

```zen
Decl, Struct, Member, Field, Span, nowhere = std.ast

Alloc, AllocError = std.mem

Vec, Map = std.collections

str, String = std.text

Range = std.core

DeclId = sema.sema_id

TyId, TyNamed = sema.sema_ty

SemaFault, NameFault = sema.sema_diag

decl_at = sema.sema_def

Checker = sema.sema_check

Inst, InstEdge, subst, subst_list = sema.sema_inst

has_var, zip, owner_of = sema.sema_inst

enter_struct_tvars, member_type = sema.sema_member
```

### `src/sema/sema_diag.zen`

37 declarations (types: 6, enums: 1, functions: 26, imports and re-exports: 4).

#### Types

```zen
NameFault* = { name*: str }

ExportFault* = { name*: str, module*: str }

CaptureFault* = {
    place*: str,
    at*: Span,
}

TypeFault* = {
    name*: str,
    expected*: TyId,
    found*: TyId,
}

PairFault* = {
    name*: str,
    first*: Span,
    second*: Span,
}

Diag* = {
    file*: str,
    span*: Span,
    fault*: SemaFault,
}
```

#### Enums

```zen
SemaFault* =
      UndefinedName(NameFault)
    | NotExported(ExportFault)
    | NotWritable(ExportFault)
    | ModuleNotAValue(ExportFault)
    | NoSuchField(TypeFault)
    | MemberNeedsValue(TypeFault)
    | Rebound(PairFault)
    | TypeMismatch(TypeFault)
    | ArmsDisagree(TypeFault)
    | DiscardedValue(TypeFault)
    | NotCallable(TypeFault)
    | MethodNotValue(TypeFault)
    | LiteralOutOfRange(TypeFault)
    | ActorPayload(NameFault)
    | NoOverload(NameFault)
    | DuplicateSignature(PairFault)
    | AmbiguousOverload(PairFault)
    | ImplMissingField(NameFault)
    | CtorMissingField(NameFault)
    | CtorNamesNoMember(TypeFault)
    | CtorSurplusArgument(TypeFault)
    | CtorNamesConstant(TypeFault)
    | DuplicateField(PairFault)
    | OrphanImpl(ExportFault)
    | AmbiguousMember(PairFault)
    | BoundNotSatisfied(TypeFault)
    | EqNeedsImpl(TypeFault)
    | ComputedFieldAssign(NameFault)
    | ComputedFieldAddress(NameFault)
    | TryOutsideRes(TypeFault)
    | TryNeedsRes(TypeFault)
    | TryAbsenceIntoFailure(TypeFault)
    | TryArgNeedsErr(TypeFault)
    | NoErrorConversion(TypeFault)
    | InferredSetExported(NameFault)
    | HoistAmbiguous(TypeFault)
    | HoistNotSuccess(NameFault)
    | VarargNotLast(NameFault)
    | VarargElement(NameFault)
    | NotExhaustive(NameFault)
    | UnreachableArm(NameFault)
    | NotACase(NameFault)
    | ConstPattern(NameFault)
    | ProvenOverflow(NameFault)
    | ProvenDivideByZero(NameFault)
    | ProvenIndexOutOfBounds(NameFault)
    | InfiniteSize(NameFault)
    | InstantiationDepth(NameFault)
    | MetaNotImplemented(NameFault)
    | CountNotComptime(NameFault)
    | ComptimeBudget(NameFault)
    | ConsumedUse(NameFault)
    | NeedsMutableReceiver(NameFault)
    | ImmutableWrite(NameFault)
    | SnapshottedReceiver(NameFault)
    | PartiallyMoved(NameFault)
    | ConsumeNotAPlace(NameFault)
    | ConsumeThroughHandle(NameFault)
    | CopyOfDropValue(NameFault)
    | ScopeEscapes(NameFault)
    | ArenaEscapes(NameFault)
    | HandleNotAValue(NameFault)
    | ConsumedByCapture(CaptureFault)
```

#### Functions

```zen
message* = (fault: SemaFault) str

render* = (self: Diag, types: Types, out :: String) Res<(), AllocError>

write_detail* = (fault: SemaFault, types: Types, out :: String)
                Res<(), AllocError>

write_name = (out :: String, f: NameFault) Res<(), AllocError>

write_ctor_missing = (out :: String, f: NameFault) Res<(), AllocError>

write_ctor_constant = (out :: String, types: Types, f: TypeFault)
                      Res<(), AllocError>

write_missing = (out :: String, f: NameFault) Res<(), AllocError>

write_const_pattern = (out :: String, f: NameFault) Res<(), AllocError>

write_orphan = (out :: String, f: ExportFault) Res<(), AllocError>

write_member* = (out :: String, types: Types, f: TypeFault)
                Res<(), AllocError>

write_ctor_surplus = (out :: String, types: Types, f: TypeFault)
                      Res<(), AllocError>

write_method_value = (out :: String, types: Types, f: TypeFault)
                     Res<(), AllocError>

write_needs_value = (out :: String, types: Types, f: TypeFault)
                    Res<(), AllocError>

write_needs_eq = (out :: String, types: Types, f: TypeFault)
                 Res<(), AllocError>

write_discarded = (out :: String, types: Types, f: TypeFault)
                  Res<(), AllocError>

write_place = (out :: String, f: NameFault, tail: str) Res<(), AllocError>

write_capture = (out :: String, f: CaptureFault) Res<(), AllocError>

write_export = (out :: String, f: ExportFault) Res<(), AllocError>

write_unwritable = (out :: String, f: ExportFault) Res<(), AllocError>

write_module = (out :: String, f: ExportFault) Res<(), AllocError>

write_arms = (out :: String, types: Types, f: TypeFault)
             Res<(), AllocError>

write_types = (out :: String, types: Types, f: TypeFault)
              Res<(), AllocError>

write_literal = (out :: String, types: Types, f: TypeFault)
                Res<(), AllocError>

write_pair = (out :: String, f: PairFault) Res<(), AllocError>

write_at = (out :: String, span: Span) Res<(), AllocError>

quote = (out :: String, name: str) Res<(), AllocError>
```

#### Imports and re-exports

```zen
Span = std.ast.ast_span

str, String = std.text

AllocError = std.mem

TyId, Types = sema.sema_ty
```

### `src/sema/sema_drop.zen`

23 declarations (functions: 12, imports and re-exports: 11).

#### Functions

```zen
check_drop_copy* = (c :: Checker, o :: Own, b: Bind, ctx: Ctx)
                   Res<(), AllocError>

drop_copy_of_record* = (c :: Checker, o :: Own, r: Record)
                        Res<(), AllocError>

drop_copy_of_elems* = (c :: Checker, o :: Own, elems: Vec<ExprId>)
                       Res<(), AllocError>

drop_copy_of_elem = (c :: Checker, o :: Own, id: ExprId)
                     Res<(), AllocError>

drop_copy_of_name = (c :: Checker, o :: Own, node: Expr, text: str)
                    Res<(), AllocError>

refuse_if_drop = (c :: Checker, span: Span, ty: TyId, text: str)
                 Res<(), AllocError>

is_drop_type* = (c :: Checker, ty: TyId) Res<bool, AllocError>

named_is_drop = (c :: Checker, n: TyNamed) Res<bool, AllocError>

keep_drop_impl = (c :: Checker, n: TyNamed, id: ImplId, hits :: Vec<bool>)
                 Res<(), AllocError>

note_drop_impl = (c :: Checker, id: ImplId, hits :: Vec<bool>)
                 Res<(), AllocError>

add_if_drop = (c :: Checker, im: Impl, hits :: Vec<bool>)
              Res<(), AllocError>

bound_named_drop = (c :: Checker, im: Impl) bool
```

#### Imports and re-exports

```zen
Expr, Bind, Impl, Span = std.ast

Record = std.ast.ast_node

ExprId = std.ast.ast_id

AllocError = std.mem

Vec = std.collections

str = std.text

ImplId = sema.sema_id

TyId, TyNamed = sema.sema_ty

Checker, Ctx = sema.sema_check

SemaFault, NameFault = sema.sema_diag

Own, find_var, var_type, refuse = sema.sema_own
```

### `src/sema/sema_effect.zen`

15 declarations (functions: 9, imports and re-exports: 6).

#### Functions

```zen
check_statement* = (
    c     :: Checker,
    block : Block,
    i     : usize,
    n     : usize,
    s     : Stmt,
    ty    : TyId
) Res<(), AllocError>

is_tail = (block: Block, i: usize, n: usize) bool

check_discarded = (c :: Checker, s: Stmt, ty: TyId) Res<(), AllocError>

discarded_expr = (c :: Checker, s: Stmt, e: ExprStmt, ty: TyId)
                 Res<(), AllocError>

statement_value = (c: Checker, ty: TyId) bool

pure_read = (c :: Checker, id: ExprId) bool

pure_match = (c :: Checker, m: Match) bool

pure_arms = (c :: Checker, arms: Vec<Arm>) bool

report_discarded = (c :: Checker, s: Stmt, ty: TyId) Res<(), AllocError>
```

#### Imports and re-exports

```zen
Vec = std.collections

AllocError = std.mem

Block, Stmt, ExprStmt, Match, Arm, ExprId = std.ast

TyId = sema.sema_ty

Checker = sema.sema_check

SemaFault, TypeFault = sema.sema_diag
```

### `src/sema/sema_handle.zen`

19 declarations (functions: 9, constants: 2, imports and re-exports: 8).

#### Functions

```zen
is_handle_ty* = (c :: Checker, ty: TyId) bool

is_handle_decl* = (c :: Checker, mi: usize, name: str) bool

handle_spelling* = (c :: Checker, id: ExprId) str

refuse_handle_at* = (c :: Checker, id: ExprId) Res<(), AllocError>

refuse_handle_value* = (c :: Checker, id: ExprId, got: TyId)
                        Res<(), AllocError>

refuse_handle_argument* = (c :: Checker, a: Arg, want: TyId, ctx: Ctx)
                          Res<(), AllocError>

refuse_unless_inward* = (c :: Checker, a: Arg, want: TyId)
                        Res<(), AllocError>

formal_takes_handle* = (c :: Checker, ty: TyId) Res<bool, AllocError>

fn_param_has_handle* = (c :: Checker, ps: Vec<TyId>) Res<bool, AllocError>
```

#### Constants

```zen
HANDLE_MODULE* : str = "std.core.loop.loop_handle"

HANDLE_NAME* : str = "LoopHandle"
```

#### Imports and re-exports

```zen
Arg, ExprId = std.ast

AllocError = std.mem

str = std.text

Vec = std.collections

Range = std.core

TyId = sema.sema_ty

Checker, Ctx = sema.sema_check

SemaFault, NameFault = sema.sema_diag
```

### `src/sema/sema_hoist.zen`

60 declarations (enums: 1, functions: 46, imports and re-exports: 13).

#### Enums

```zen
Blame* = Position | Arms
```

#### Functions

```zen
hoist_check* = (c :: Checker, file: str, span: Span, got: TyId, want: TyId)
               Res<(), AllocError>

hoist_into = (c :: Checker, file: str, span: Span, got: TyId, want: TyId)
             Res<(), AllocError>

hoist_into_res = (
    c    :: Checker,
    file : str,
    span : Span,
    got  : TyId,
    want : TyId,
    r    : TyRes
) Res<(), AllocError>

count_carriers = (
    c    :: Checker,
    file : str,
    span : Span,
    got  : TyId,
    want : TyId,
    r    : TyRes
) Res<(), AllocError>

lone_failure = (c :: Checker, file: str, span: Span, err: bool)
               Res<(), AllocError>

countable = (c: Checker, r: TyRes) bool

carries_failure = (c: Checker, got: TyId, r: TyRes) bool

settled = (c: Checker, t: TyId) bool

two_readings = (c :: Checker, file: str, span: Span, got: TyId, want: TyId)
               Res<(), AllocError>

failure_never_lifts = (c :: Checker, file: str, span: Span)
                      Res<(), AllocError>

check_return* = (c :: Checker, body: BlockId, ctx: Ctx, got: TyId)
                Res<(), AllocError>

tail_fits = (c :: Checker, blk: Block, id: ExprId, got: TyId, want: TyId)
            Res<(), AllocError>

return_fits = (c :: Checker, blk: Block, id: ExprId, got: TyId, want: TyId)
              Res<(), AllocError>

refuse_return = (
    c    :: Checker,
    blk  : Block,
    node : Expr,
    got  : TyId,
    want : TyId
) Res<(), AllocError>

res_return = (
    c    :: Checker,
    blk  : Block,
    node : Expr,
    got  : TyId,
    want : TyId,
    r    : TyRes
) Res<(), AllocError>

lift_or_refuse = (
    c    :: Checker,
    blk  : Block,
    node : Expr,
    got  : TyId,
    want : TyId,
    r    : TyRes
) Res<(), AllocError>

was_written = (node: Expr) bool

lands_somewhere = (c: Checker, got: TyId, r: TyRes) bool

wrong_return = (c :: Checker, blk: Block, node: Expr, got: TyId, want: TyId)
               Res<(), AllocError>

value_was_asked_for = (c: Checker, blk: Block, got: TyId, want: TyId) bool

written_value = (blk: Block) bool

unit_ty = (c: Checker, t: TyId) bool

hoist_at = (c :: Checker, id: ExprId, got: TyId, want: TyId)
           Res<(), AllocError>

tail_expr* = (c: Checker, blk: Block) Res<ExprId>

last_stmt_expr = (c: Checker, blk: Block) Res<ExprId>

last_stmt_of = (c: Checker, stmts: Vec<Stmt>) Res<ExprId>

stmt_tail_expr = (c: Checker, s: Stmt) Res<ExprId>

check_arms* = (c :: Checker, id: ExprId, want: TyId) Res<(), AllocError>

check_arms_agree* = (c :: Checker, id: ExprId) Res<(), AllocError>

arms_owe = (c :: Checker, id: ExprId, want: TyId, blame: Blame)
           Res<(), AllocError>

arms_within = (c :: Checker, m: Match, want: TyId, blame: Blame)
              Res<(), AllocError>

arm_within = (c :: Checker, id: ExprId, want: TyId, blame: Blame)
             Res<(), AllocError>

arm_fits = (c :: Checker, id: ExprId, node: Expr, want: TyId, blame: Blame)
           Res<(), AllocError>

arm_agrees = (c :: Checker, node: Expr, got: TyId, want: TyId, blame: Blame)
             Res<(), AllocError>

refuse_arm = (c :: Checker, node: Expr, got: TyId, want: TyId, blame: Blame)
             Res<(), AllocError>

arm_into_res = (
    c     :: Checker,
    node  : Expr,
    got   : TyId,
    want  : TyId,
    r     : TyRes,
    blame : Blame
) Res<(), AllocError>

arm_refused = (c :: Checker, node: Expr, got: TyId, want: TyId, blame: Blame)
              Res<(), AllocError>

arms_disagree = (c :: Checker, node: Expr, got: TyId, want: TyId)
                Res<(), AllocError>

check_ctor_fields* = (c :: Checker, call: Call, ty: TyId, ctx: Ctx)
                     Res<(), AllocError>

check_ctor_field = (c :: Checker, a: Arg, i: usize, ty: TyId, ctx: Ctx)
                   Res<(), AllocError>

check_positional_field = (
    c   :: Checker,
    a   : Arg,
    i   : usize,
    ty  : TyId,
    ctx : Ctx
) Res<(), AllocError>

check_named_field = (
    c    :: Checker,
    a    : Arg,
    at   : Span,
    name : str,
    ty   : TyId,
    ctx  : Ctx
)
                    Res<(), AllocError>

ctor_no_member = (c :: Checker, a: Arg, name: str, ty: TyId)
                 Res<(), AllocError>

ctor_field_or_constant = (
    c    :: Checker,
    a    : Arg,
    f    : Found,
    name : str,
    at   : Span,
    ty   : TyId,
    ctx  : Ctx
) Res<(), AllocError>

ctor_names_constant = (
    c    :: Checker,
    a    : Arg,
    name : str,
    at   : Span,
    ty   : TyId,
    ctx  : Ctx
)
                      Res<(), AllocError>

field_fits = (c :: Checker, a: Arg, want: TyId, ctx: Ctx)
             Res<(), AllocError>
```

#### Imports and re-exports

```zen
Expr, ExprId, Block, BlockId, Stmt, Call, Arg, Span = std.ast

Match = std.ast

AllocError = std.mem

Vec = std.collections

str = std.text

TyId, TyRes = sema.sema_ty

SemaFault, NameFault, TypeFault = sema.sema_diag

Checker, Ctx = sema.sema_check

Found, members_of = sema.sema_member

storage_seat_name = sema.sema_supply

check_literal = sema.sema_trap

type_of = sema.sema_type

refuse_handle_value = sema.sema_handle
```

### `src/sema/sema_id.zen`

13 declarations (types: 3, implementations: 6, functions: 2, constants: 1, imports and re-exports: 1).

#### Types

```zen
DeclId* = {
    module*: u32,
    decl*: u32,
}

MemberId* = {
    module*: u32,
    decl*: u32,
    member*: u32,
}

ImplId* = {
    decl*: DeclId,
}
```

#### Implementations

```zen
DeclId.impl(Eq, {
    eq ::= (self: @Self, other: @Self) bool
})

DeclId.impl(Hash, {
    hash = (self: @Self, hasher :: Hasher) u64
})

MemberId.impl(Eq, {
    eq ::= (self: @Self, other: @Self) bool
})

MemberId.impl(Hash, {
    hash = (self: @Self, hasher :: Hasher) u64
})

ImplId.impl(Eq, {
    eq ::= (self: @Self, other: @Self) bool
})

ImplId.impl(Hash, {
    hash = (self: @Self, hasher :: Hasher) u64
})
```

#### Functions

```zen
owner* = (self: MemberId) DeclId

member_at* = (self: DeclId, i: u32) MemberId
```

#### Constants

```zen
MIX* : u64 = 1099511628211
```

#### Imports and re-exports

```zen
Eq, Hash, Hasher = std.core
```

### `src/sema/sema_inst.zen`

47 declarations (types: 2, functions: 37, imports and re-exports: 8).

#### Types

```zen
Inst* = {
    vars :: Vec<TyId>,
    args :: Vec<TyId>,
    len* = (self: @Self) usize
    var_at* = (self: @Self, i: usize) Res<TyId>
    arg_at* = (self: @Self, i: usize) Res<TyId>
    bind* = (self :: @Self, v: TyId, arg: TyId) Res<(), AllocError>
    push = (self :: @Self, v: TyId, arg: TyId) Res<(), AllocError>
    bound* = (self: @Self, v: TyId) bool
    lookup* = (self: @Self, v: TyId) Res<TyId>
}

InstEdge* = {
    from_owner*: str,
    to_owner*: str,
    to_name*: str,
    to_tvars*: Vec<TyId>,
    args*: Vec<TyId>,
    span*: Span,
}
```

#### Functions

```zen
Inst* = (a: Alloc) Inst

subst* = (c :: Checker, ty: TyId, inst: Inst) Res<TyId, AllocError>

subst_kind = (c :: Checker, ty: TyId, inst: Inst) Res<TyId, AllocError>

subst_named = (c :: Checker, n: TyNamed, ty: TyId, inst: Inst)
              Res<TyId, AllocError>

rebuild_named = (c :: Checker, n: TyNamed, inst: Inst)
                Res<TyId, AllocError>

subst_res = (c :: Checker, r: TyRes, ty: TyId, inst: Inst)
            Res<TyId, AllocError>

unchanged = (a: TyId, b: TyId, x: TyId, y: TyId) bool

rebuild_res = (c :: Checker, value: TyId, error: TyId, form: ResForm)
              Res<TyId, AllocError>

subst_fn = (c :: Checker, f: TyFn, ty: TyId, inst: Inst)
           Res<TyId, AllocError>

subst_union = (c :: Checker, members: Vec<TyId>, ty: TyId, inst: Inst)
              Res<TyId, AllocError>

subst_list* = (c :: Checker, src: Vec<TyId>, inst: Inst, out :: Vec<TyId>)
              Res<(), AllocError>

has_var* = (c: Checker, ty: TyId) bool

any_has_var = (c: Checker, list: Vec<TyId>) bool

tparam_vars* = (
    c       :: Checker,
    tparams : Vec<TParam>,
    owner   : str,
    out     :: Vec<TyId>
) Res<(), AllocError>

push_tparams* = (c :: Checker, tparams: Vec<TParam>, owner: str)
                Res<(), AllocError>

owner_of* = (c :: Checker, mi: usize, name: str) Res<str, AllocError>

module_name* = (c: Checker, mi: usize) str

inst_of_named* = (c :: Checker, n: TyNamed) Res<Inst, AllocError>

fill_from_decl = (c :: Checker, n: TyNamed, inst :: Inst)
                 Res<(), AllocError>

fill_from_struct = (c :: Checker, n: TyNamed, d: Decl, inst :: Inst)
                   Res<(), AllocError>

fill_tparams = (c :: Checker, n: TyNamed, s: Struct, inst :: Inst)
               Res<(), AllocError>

fill_enum_tparams = (c :: Checker, n: TyNamed, e: Enum, inst :: Inst)
                    Res<(), AllocError>

zip* = (c :: Checker, vars: Vec<TyId>, args: Vec<TyId>, inst :: Inst)
       Res<(), AllocError>

zip_one = (
    c    :: Checker,
    vars : Vec<TyId>,
    args : Vec<TyId>,
    i    : usize,
    inst :: Inst
) Res<(), AllocError>

zip_arg = (c :: Checker, v: TyId, args: Vec<TyId>, i: usize, inst :: Inst)
          Res<(), AllocError>

unify* = (c :: Checker, param: TyId, actual: TyId, inst :: Inst)
         Res<(), AllocError>

bind_actual = (c :: Checker, param: TyId, actual: TyId, inst :: Inst)
              Res<(), AllocError>

usable_actual = (c: Checker, actual: TyId) bool

unify_named = (c :: Checker, n: TyNamed, actual: TyId, inst :: Inst)
              Res<(), AllocError>

unify_args = (c :: Checker, n: TyNamed, m: TyNamed, inst :: Inst)
             Res<(), AllocError>

unify_res = (c :: Checker, r: TyRes, actual: TyId, inst :: Inst)
            Res<(), AllocError>

unify_res_parts = (c :: Checker, r: TyRes, s: TyRes, inst :: Inst)
                  Res<(), AllocError>

unify_fn = (c :: Checker, f: TyFn, actual: TyId, inst :: Inst)
           Res<(), AllocError>

unify_fn_parts = (c :: Checker, f: TyFn, g: TyFn, inst :: Inst)
                 Res<(), AllocError>

unify_list* = (
    c       :: Checker,
    params  : Vec<TyId>,
    actuals : Vec<TyId>,
    inst    :: Inst
) Res<(), AllocError>

unify_at = (
    c       :: Checker,
    params  : Vec<TyId>,
    actuals : Vec<TyId>,
    i       : usize,
    inst    :: Inst
) Res<(), AllocError>

unify_actual_at = (
    c       :: Checker,
    p       : TyId,
    actuals : Vec<TyId>,
    i       : usize,
    inst    :: Inst
) Res<(), AllocError>
```

#### Imports and re-exports

```zen
Decl, Struct, Enum, TParam, Span = std.ast

Alloc, AllocError = std.mem

Vec = std.collections

str, String = std.text

Range = std.core

TyId, TyNamed, TyRes, TyFn, ResForm = sema.sema_ty

decl_at = sema.sema_def

Checker = sema.sema_check
```

### `src/sema/sema_join.zen`

21 declarations (functions: 18, imports and re-exports: 3).

#### Functions

```zen
join* = (c :: Checker, a: TyId, b: TyId) Res<TyId, AllocError>

keep_or_settle = (c :: Checker, a: TyId, b: TyId) Res<TyId, AllocError>

settle_reversed = (c :: Checker, a: TyId, b: TyId) Res<TyId, AllocError>

settled_literal = (c :: Checker, a: TyId, b: TyId) Res<TyId, AllocError>

literal_reversed = (c :: Checker, a: TyId, b: TyId) Res<TyId, AllocError>

concrete = (c: Checker, id: TyId) bool

settled_res = (c :: Checker, a: TyId, b: TyId) Res<TyId, AllocError>

settled_form = (c :: Checker, a: TyId, b: TyId, rb: TyRes)
               Res<TyId, AllocError>

carried_value = (c :: Checker, a: TyId, b: TyId, rb: TyRes)
                Res<TyId, AllocError>

at_form = (c :: Checker, value: TyId, rb: TyRes) Res<TyId, AllocError>

merged_or_first = (c :: Checker, a: TyId, b: TyId) Res<TyId, AllocError>

merge_against = (c :: Checker, a: TyId, b: TyId, ra: TyRes)
                Res<TyId, AllocError>

merge_failures = (c :: Checker, a: TyId, ra: TyRes, rb: TyRes)
                 Res<TyId, AllocError>

merged_failure = (c :: Checker, ra: TyRes, rb: TyRes) Res<TyId, AllocError>

open_value = (c: Checker, id: TyId) Res<TyId>

keep_settled = (c: Checker, value: TyId) Res<TyId>

unsettled = (c: Checker, id: TyId) bool

open_res = (c: Checker, id: TyId) bool
```

#### Imports and re-exports

```zen
AllocError = std.mem

TyId, TyRes, is_failure = sema.sema_ty

Checker = sema.sema_check
```

### `src/sema/sema_layout.zen`

24 declarations (types: 2, functions: 11, imports and re-exports: 11).

#### Types

```zen
Frame = {
    id: DeclId,
    site: Ident,
}

Layout = {
    path :: Vec<Frame>,
    done :: Vec<DeclId>,
    all = (self :: @Self, c :: Checker) Res<(), AllocError>
    module = (self :: @Self, c :: Checker, mi: usize) Res<(), AllocError>
    table = (self :: @Self, c :: Checker, t: ModuleTable)
            Res<(), AllocError>
    root = (self :: @Self, c :: Checker, d: Def) Res<(), AllocError>
    enter = (self :: @Self, c :: Checker, id: DeclId, s: Struct, site: Ident)
            Res<(), AllocError>
    walk = (self :: @Self, c :: Checker, id: DeclId, s: Struct, site: Ident)
           Res<(), AllocError>
    field = (self :: @Self, c :: Checker, m: Member) Res<(), AllocError>
    typed = (self :: @Self, c :: Checker, f: Field) Res<(), AllocError>
    edge_from_top = (self :: @Self, c :: Checker, t: TypeId, site: Ident)
                    Res<(), AllocError>
    edge_from = (
        self :: @Self,
        c     :: Checker,
        fr    : Frame,
        t     : TypeId,
        site  : Ident
    ) Res<(), AllocError>
    step = (self :: @Self, c :: Checker, next: DeclId, site: Ident)
           Res<(), AllocError>
    descend = (self :: @Self, c :: Checker, next: DeclId, site: Ident)
              Res<(), AllocError>
    close = (self :: @Self, c :: Checker, k: usize, site: Ident)
            Res<(), AllocError>
    seal = (self :: @Self, k: usize) Res<(), AllocError>
}
```

#### Functions

```zen
Layout = (a: Alloc) Layout

check_layout* = (c :: Checker) Res<(), AllocError>

named_decl = (c: Checker, ty: TyId) Res<DeclId>

struct_of = (c: Checker, id: DeclId) Res<Struct>

monomorphic_struct = (x: Decl) Res<Struct>

index_on = (path: Vec<Frame>, id: DeclId) Res<usize>

at_is = (path: Vec<Frame>, i: usize, id: DeclId) bool

contains = (done: Vec<DeclId>, id: DeclId) bool

site_at = (path: Vec<Frame>, i: usize, fallback: Ident) Ident

earlier = (a: Ident, b: Ident) Ident

earlier_pos = (x: Pos, y: Pos) bool
```

#### Imports and re-exports

```zen
Decl, Struct, Member, Field = std.ast

Ident, Pos, TypeId = std.ast

Alloc, AllocError = std.mem

Vec = std.collections

Range = std.core

DeclId = sema.sema_id

TyId = sema.sema_ty

Def, ModuleTable, decl_at = sema.sema_def

SemaFault, NameFault = sema.sema_diag

Checker, Ctx = sema.sema_check

type_from_ast = sema.sema_denote
```

### `src/sema/sema_match.zen`

101 declarations (types: 3, enums: 1, functions: 80, imports and re-exports: 17).

#### Types

```zen
Pat* = {
    kind*: PatKind,
    name*: str,
    binder*: str,
    sub*: usize,
    has_sub*: bool,
    span*: Span,
}

Pats* = {
    rows :: Vec<Pat>,
    alloc: Alloc,
    add* = (self :: @Self, p: Pat) Res<usize, AllocError>
    at* = (self: @Self, i: usize) Pat
    wild* = (self :: @Self, span: Span) Res<usize, AllocError>
    norm_literal = (self :: @Self, node: Pattern, l: Literal)
                   Res<usize, AllocError>
    sub_index = (self :: @Self, head: Pat) Res<usize, AllocError>
    complete = (self: @Self, has: bool, m: PatMatrix, cases: Vec<Case>) bool
    all_roots_present = (self: @Self, m: PatMatrix, cases: Vec<Case>) bool
    root_present = (self: @Self, m: PatMatrix, name: str) bool
}

PatMatrix* = {
    cells :: Vec<usize>,
    width*: usize,
    n* :: usize,
    alloc: Alloc,
    at* = (self: @Self, r: usize, k: usize) usize
    add_row* = (self :: @Self, row: Vec<usize>) Res<(), AllocError>
}
```

#### Enums

```zen
PatKind* = WildPat | CtorPat | LitPat
```

#### Functions

```zen
Pats* = (a: Alloc) Pats

PatMatrix* = (a: Alloc, width: usize) PatMatrix

match_type* = (c :: Checker, node: Expr, mt: Match, ctx: Ctx)
              Res<TyId, AllocError>

norm_arms = (
    c    :: Checker,
    ps   :: Pats,
    mt   : Match,
    sty  : TyId,
    rows :: Vec<usize>,
    ctx  : Ctx
) Res<(), AllocError>

norm_pattern* = (c :: Checker, ps :: Pats, pid: PatternId, ty: TyId, ctx: Ctx)
                Res<usize, AllocError>

norm_destructure = (
    c    :: Checker,
    ps   :: Pats,
    node : Pattern,
    d    : Destructure,
    ty   : TyId,
    ctx  : Ctx
) Res<usize, AllocError>

plain_ctor = (
    c    :: Checker,
    ps   :: Pats,
    node : Pattern,
    d    : Destructure,
    ty   : TyId,
    text : str,
    ctx  : Ctx
) Res<usize, AllocError>

norm_set_ctor = (
    c      :: Checker,
    ps     :: Pats,
    node   : Pattern,
    d      : Destructure,
    member : str,
    mty    : TyId,
    ctx    : Ctx
) Res<usize, AllocError>

norm_name = (
    c    :: Checker,
    ps   :: Pats,
    node : Pattern,
    pn   : PatName,
    ty   : TyId,
    ctx  : Ctx
) Res<usize, AllocError>

norm_set_name = (
    c    :: Checker,
    ps   :: Pats,
    node : Pattern,
    pn   : PatName,
    ty   : TyId,
    text : str,
    ctx  : Ctx
) Res<usize, AllocError>

norm_qualified = (
    c    :: Checker,
    ps   :: Pats,
    node : Pattern,
    pn   : PatName,
    ty   : TyId,
    text : str,
    ctx  : Ctx
) Res<usize, AllocError>

norm_member_dot = (
    c    :: Checker,
    ps   :: Pats,
    node : Pattern,
    pn   : PatName,
    ty   : TyId,
    leaf : str,
    ctx  : Ctx
) Res<usize, AllocError>

norm_binder = (
    c    :: Checker,
    ps   :: Pats,
    node : Pattern,
    text : str,
    ty   : TyId,
    ctx  : Ctx
) Res<usize, AllocError>

not_a_case = (c :: Checker, ty: TyId, text: str) Res<bool, AllocError>

names_const = (c :: Checker, text: str, ctx: Ctx) Res<bool, AllocError>

is_case* = (c :: Checker, ty: TyId, name: str) Res<bool, AllocError>

last_segment* = (q: QualifiedName) str

segment_at* = (q: QualifiedName, i: usize) str

check_coverage = (
    c    :: Checker,
    ps   :: Pats,
    node : Expr,
    mt   : Match,
    sty  : TyId,
    rows : Vec<usize>
) Res<(), AllocError>

checkable* = (c: Checker, sty: TyId) bool

run_coverage = (
    c    :: Checker,
    ps   :: Pats,
    node : Expr,
    sty  : TyId,
    rows : Vec<usize>
) Res<(), AllocError>

check_reachable = (c :: Checker, ps :: Pats, sty: TyId, rows: Vec<usize>)
                  Res<(), AllocError>

arm_reachable = (
    c    :: Checker,
    ps   :: Pats,
    sty  : TyId,
    rows : Vec<usize>,
    i    : usize
) Res<(), AllocError>

report_unreachable = (c :: Checker, ps :: Pats, rows: Vec<usize>, i: usize)
                     Res<(), AllocError>

check_exhaustive = (
    c    :: Checker,
    ps   :: Pats,
    node : Expr,
    sty  : TyId,
    rows : Vec<usize>
) Res<(), AllocError>

report_not_exhaustive = (
    c    :: Checker,
    ps   :: Pats,
    node : Expr,
    sty  : TyId,
    m    : PatMatrix
) Res<(), AllocError>

first_uncovered = (
    c     :: Checker,
    ps    :: Pats,
    m     : PatMatrix,
    sty   : TyId,
    cases : Vec<Case>
) Res<str, AllocError>

pick_name = (take: bool, name: str, so_far: str) str

case_open = (c :: Checker, ps :: Pats, m: PatMatrix, sty: TyId, cs: Case)
            Res<bool, AllocError>

case_pattern = (c :: Checker, ps :: Pats, cs: Case) Res<usize, AllocError>

useful* = (
    c     :: Checker,
    ps    :: Pats,
    m     : PatMatrix,
    q     : Vec<usize>,
    types : Vec<TyId>
) Res<bool, AllocError>

useful_head = (
    c     :: Checker,
    ps    :: Pats,
    m     : PatMatrix,
    q     : Vec<usize>,
    types : Vec<TyId>
) Res<bool, AllocError>

useful_ctor = (
    c     :: Checker,
    ps    :: Pats,
    m     : PatMatrix,
    q     : Vec<usize>,
    types : Vec<TyId>,
    head  : Pat
) Res<bool, AllocError>

useful_lit = (
    c     :: Checker,
    ps    :: Pats,
    m     : PatMatrix,
    q     : Vec<usize>,
    types : Vec<TyId>,
    head  : Pat
) Res<bool, AllocError>

useful_wild = (
    c     :: Checker,
    ps    :: Pats,
    m     : PatMatrix,
    q     : Vec<usize>,
    types : Vec<TyId>
) Res<bool, AllocError>

head_is_ctor = (p: Pat, name: str) bool

useful_split = (
    c     :: Checker,
    ps    :: Pats,
    m     : PatMatrix,
    q     : Vec<usize>,
    types : Vec<TyId>,
    cases : Vec<Case>
) Res<bool, AllocError>

useful_one_case = (
    c     :: Checker,
    ps    :: Pats,
    m     : PatMatrix,
    q     : Vec<usize>,
    types : Vec<TyId>,
    cs    : Case
) Res<bool, AllocError>

useful_default = (
    c     :: Checker,
    ps    :: Pats,
    m     : PatMatrix,
    q     : Vec<usize>,
    types : Vec<TyId>
) Res<bool, AllocError>

payload_arity = (cs: Case) usize

specialise = (
    c     :: Checker,
    ps    :: Pats,
    m     : PatMatrix,
    name  : str,
    arity : usize
) Res<PatMatrix, AllocError>

spec_row = (
    c     :: Checker,
    ps    :: Pats,
    out   :: PatMatrix,
    m     : PatMatrix,
    r     : usize,
    name  : str,
    arity : usize
) Res<(), AllocError>

spec_wild = (
    c     :: Checker,
    ps    :: Pats,
    out   :: PatMatrix,
    m     : PatMatrix,
    r     : usize,
    arity : usize,
    head  : Pat
) Res<(), AllocError>

spec_ctor = (
    c     :: Checker,
    ps    :: Pats,
    out   :: PatMatrix,
    m     : PatMatrix,
    r     : usize,
    name  : str,
    arity : usize,
    head  : Pat
)
            Res<(), AllocError>

spec_keep = (
    c     :: Checker,
    ps    :: Pats,
    out   :: PatMatrix,
    m     : PatMatrix,
    r     : usize,
    arity : usize,
    head  : Pat
) Res<(), AllocError>

specialise_lit = (c :: Checker, ps :: Pats, m: PatMatrix, text: str)
                 Res<PatMatrix, AllocError>

lit_row = (
    c    :: Checker,
    ps   :: Pats,
    out  :: PatMatrix,
    m    : PatMatrix,
    r    : usize,
    text : str
) Res<(), AllocError>

keeps_lit = (p: Pat, text: str) bool

default_matrix = (c :: Checker, ps :: Pats, m: PatMatrix)
                 Res<PatMatrix, AllocError>

default_row = (
    c   :: Checker,
    ps  :: Pats,
    out :: PatMatrix,
    m   : PatMatrix,
    r   : usize
) Res<(), AllocError>

is_wild = (p: Pat) bool

emit_row = (
    c      :: Checker,
    out    :: PatMatrix,
    m      : PatMatrix,
    r      : usize,
    arity  : usize,
    filler : usize
) Res<(), AllocError>

arm_types = (
    c    :: Checker,
    ps   :: Pats,
    mt   : Match,
    sty  : TyId,
    rows : Vec<usize>,
    ctx  : Ctx
) Res<TyId, AllocError>

arm_type = (
    c    :: Checker,
    ps   :: Pats,
    mt   : Match,
    sty  : TyId,
    rows : Vec<usize>,
    i    : usize,
    ctx  : Ctx
) Res<TyId, AllocError>

arm_body_type = (c :: Checker, mt: Match, i: usize, ctx: Ctx)
                Res<TyId, AllocError>

arm_value_type = (c :: Checker, id: ExprId, ctx: Ctx)
                 Res<TyId, AllocError>

arm_paren_type = (c :: Checker, id: ExprId, inner: ExprId, ctx: Ctx)
                 Res<TyId, AllocError>

arm_closure_type = (c :: Checker, id: ExprId, l: Lambda, ctx: Ctx)
                   Res<TyId, AllocError>

bind_pattern* = (c :: Checker, ps: Pats, i: usize, ty: TyId)
                Res<(), AllocError>

bind_binder = (c :: Checker, p: Pat, ty: TyId) Res<(), AllocError>

bind_sub = (c :: Checker, ps: Pats, p: Pat, ty: TyId) Res<(), AllocError>

bind_payload = (c :: Checker, ps: Pats, p: Pat, ty: TyId)
               Res<(), AllocError>

wild_pat* = (span: Span) Pat

binder_pat = (name: str, span: Span) Pat

ctor_pat = (name: str, span: Span) Pat

sub_pat = (name: str, sub: usize, span: Span) Pat

dot_pat* = (c :: Checker, ps :: Pats, member: str, leaf: str, span: Span)
           Res<usize, AllocError>

leaf_hole = (c :: Checker, ps :: Pats, leaf: str, span: Span)
            Res<usize, AllocError>

member_leaf = (c :: Checker, ps :: Pats, mty: TyId, text: str, span: Span)
              Res<usize, AllocError>

member_name = (c :: Checker, mty: TyId) str

last_segment_str = (qname: str) str

last_len = (qname: str) usize

lit_pat = (text: str, span: Span) Pat

row_at = (v: Vec<usize>, i: usize) usize

head_ty = (types: Vec<TyId>) TyId

prefix_matrix = (c :: Checker, rows: Vec<usize>, k: usize)
                Res<PatMatrix, AllocError>

one_row = (c :: Checker, rows: Vec<usize>, i: usize)
          Res<Vec<usize>, AllocError>

one_ty = (c :: Checker, sty: TyId) Res<Vec<TyId>, AllocError>

append_tail = (out :: Vec<usize>, src: Vec<usize>) Res<(), AllocError>

append_tys = (out :: Vec<TyId>, src: Vec<TyId>) Res<(), AllocError>
```

#### Imports and re-exports

```zen
Expr, ExprId, Span, Literal, nowhere = std.ast

Pattern, PatName, Destructure, PatternId = std.ast

Match, QualifiedName, Lambda = std.ast

Alloc, AllocError = std.mem

Vec = std.collections

str = std.text

Range, is_upper = std.core

TyId = sema.sema_ty

member_of = sema.sema_union

SemaFault, NameFault = sema.sema_diag

Checker, Ctx, UNRESOLVED = sema.sema_check

Case, cases_of, case_payload, case_arity = sema.sema_case

find_case = sema.sema_case

type_of, lambda_type = sema.sema_type

join = sema.sema_join

const_def = sema.sema_const

push_tparams, module_name = sema.sema_inst
```

### `src/sema/sema_member.zen`

89 declarations (types: 2, functions: 65, imports and re-exports: 22).

#### Types

```zen
Found* = {
    name*: str,
    ty*: TyId,
    computed*: bool,
    constant*: bool,
    mutable*: bool,
    exported*: bool,
    module*: usize,
    bound*: TyId,
    span*: Span,
}

Base* = {
    ty*: TyId,
    is_type*: bool,
}
```

#### Functions

```zen
access_type* = (c :: Checker, id: ExprId, node: Expr, ac: Access, ctx: Ctx)
               Res<TyId, AllocError>

member_access = (c :: Checker, id: ExprId, node: Expr, ac: Access, ctx: Ctx)
                Res<TyId, AllocError>

base_of* = (c :: Checker, id: ExprId, ctx: Ctx) Res<Base, AllocError>

value_base = (c :: Checker, id: ExprId, ctx: Ctx) Res<Base, AllocError>

named_base = (c :: Checker, id: ExprId, node: Expr, text: str, ctx: Ctx)
             Res<Base, AllocError>

bound_base = (c :: Checker, id: ExprId, b: Binding) Res<Base, AllocError>

global_base = (c :: Checker, node: Expr, text: str, ctx: Ctx)
              Res<Base, AllocError>

decl_base = (c :: Checker, node: Expr, text: str, ctx: Ctx)
            Res<Base, AllocError>

is_type_def* = (k: DefKind) bool

value_access* = (
    c    :: Checker,
    id   : ExprId,
    node : Expr,
    ac   : Access,
    ty   : TyId,
    ctx  : Ctx
) Res<TyId, AllocError>

opaque* = (c: Checker, ty: TyId) bool

foreign_tvar = (c: Checker, ty: TyId) bool

in_scope_tvar = (c: Checker, name: str, ty: TyId) bool

known_access = (
    c    :: Checker,
    id   : ExprId,
    node : Expr,
    ac   : Access,
    ty   : TyId,
    ctx  : Ctx
) Res<TyId, AllocError>

first_hidden* = (found: Vec<Found>, mi: usize) Res<Found>

hidden_from = (f: Found, mi: usize) bool

hidden_member* = (c :: Checker, ac: Access, f: Found) Res<TyId, AllocError>

module_of = (c :: Checker, f: Found) str

pick = (
    c     :: Checker,
    id    : ExprId,
    node  : Expr,
    ac    : Access,
    ty    : TyId,
    found : Vec<Found>,
    ctx   : Ctx
) Res<TyId, AllocError>

first_type = (c :: Checker, id: ExprId, ty: TyId, found: Vec<Found>)
             Res<TyId, AllocError>

settled = (c :: Checker, id: ExprId, ty: TyId, f: Found)
          Res<TyId, AllocError>

select = (
    c     :: Checker,
    id    : ExprId,
    node  : Expr,
    ac    : Access,
    ty    : TyId,
    found : Vec<Found>
) Res<TyId, AllocError>

ambiguous = (c :: Checker, node: Expr, ac: Access, found: Vec<Found>)
            Res<TyId, AllocError>

span_of = (found: Vec<Found>, i: usize) Span

method_not_value = (c :: Checker, id: ExprId, fn_ty: TyId)
                   Res<TyId, AllocError>

ufcs_or_missing = (c :: Checker, node: Expr, ac: Access, ty: TyId, ctx: Ctx)
                  Res<TyId, AllocError>

no_such_field = (c :: Checker, node: Expr, ac: Access, ty: TyId)
                Res<TyId, AllocError>

found_of = (c :: Checker, ac: Access, ctx: Ctx) Res<Res<Found>, AllocError>

computed_member* = (c :: Checker, ac: Access, ctx: Ctx)
                   Res<bool, AllocError>

writable_member* = (c :: Checker, ac: Access, ctx: Ctx)
                   Res<(), AllocError>

written_from = (c :: Checker, ac: Access, f: Found, ctx: Ctx)
               Res<(), AllocError>

not_writable = (c :: Checker, ac: Access, f: Found) Res<(), AllocError>

first_found* = (found: Vec<Found>) Res<Found>

members_of* = (c :: Checker, ty: TyId, name: str, out :: Vec<Found>)
              Res<(), AllocError>

behavior_members = (c :: Checker, ty: TyId, name: str, out :: Vec<Found>)
                   Res<(), AllocError>

behavior_set = (c :: Checker, a: TyId, name: str, out :: Vec<Found>)
               Res<(), AllocError>

behavior_bounds = (
    c     :: Checker,
    owner : str,
    a     : TyId,
    name  : str,
    out   :: Vec<Found>
) Res<(), AllocError>

behavior_impls = (
    c    :: Checker,
    n    : TyNamed,
    a    : TyId,
    name : str,
    out  :: Vec<Found>
) Res<(), AllocError>

behavior_in = (
    c    :: Checker,
    n    : TyNamed,
    a    : TyId,
    name : str,
    id   : ImplId,
    out  :: Vec<Found>
) Res<(), AllocError>

send_members = (
    c     :: Checker,
    ms    : Vec<Member>,
    a     : TyId,
    name  : str,
    id    : ImplId,
    actor : TyId,
    out   :: Vec<Found>
)
               Res<(), AllocError>

send_found = (
    c     :: Checker,
    m     : Member,
    a     : TyId,
    name  : str,
    id    : ImplId,
    actor : TyId,
    out   :: Vec<Found>
) Res<(), AllocError>

message_type = (c :: Checker, full: TyId) Res<TyId, AllocError>

message_fn = (c :: Checker, sig: TyFn) Res<TyId, AllocError>

ref_of_actor* = (c :: Checker, ty: TyId) Res<Res<TyId>, AllocError>

actor_ref = (c :: Checker, n: TyNamed) Res<Res<TyId>, AllocError>

actor_type = (c :: Checker) Res<Res<TyId>, AllocError>

actor_error_type = (c :: Checker) Res<Res<TyId>, AllocError>

actor_spawn_ret* = (
    c        :: Checker,
    recv     : TyId,
    name     : str,
    actor    : TyId,
    ordinary : TyId
) Res<TyId, AllocError>

is_actor_spawn = (c: Checker, recv: TyId, name: str) bool

spawn_result = (c :: Checker, actor: TyId, ordinary: TyId)
               Res<TyId, AllocError>

actor_named_type = (c :: Checker, name: str) Res<Res<TyId>, AllocError>

actor_path = (name: str) str

prim_members = (
    c    :: Checker,
    p    : Prim,
    ty   : TyId,
    name : str,
    out  :: Vec<Found>
) Res<(), AllocError>

bound_reachable = (
    c     :: Checker,
    tname : str,
    ty    : TyId,
    name  : str,
    out   :: Vec<Found>
) Res<(), AllocError>

bound_member = (
    c     :: Checker,
    bound : TyId,
    ty    : TyId,
    name  : str,
    out   :: Vec<Found>
) Res<(), AllocError>

bound_span = (c: Checker, bound: TyId) Span

decl_span* = (c: Checker, id: DeclId) Span

named_members = (
    c    :: Checker,
    n    : TyNamed,
    ty   : TyId,
    name : str,
    out  :: Vec<Found>
) Res<(), AllocError>

struct_members = (
    c    :: Checker,
    s    : Struct,
    n    : TyNamed,
    ty   : TyId,
    name : str,
    out  :: Vec<Found>
) Res<(), AllocError>

enter_struct_tvars* = (c :: Checker, s: Struct, mi: usize)
                     Res<(), AllocError>

add_own = (
    c      :: Checker,
    m      : Member,
    name   : str,
    mi     : usize,
    ty     : TyId,
    poison : TyId,
    inst   : Inst,
    out    :: Vec<Found>
)
          Res<(), AllocError>

member_type* = (c :: Checker, m: Member, mi: usize, self_ty: TyId)
               Res<TyId, AllocError>

self_ctx* = (c :: Checker, mi: usize, self_ty: TyId) Res<Ctx, AllocError>

opt_type = (c :: Checker, t: Res<TypeId>, ctx: Ctx) Res<TyId, AllocError>

fn_member_type = (c :: Checker, f: Function, ctx: Ctx)
                 Res<TyId, AllocError>
```

#### Imports and re-exports

```zen
Expr, ExprId, Access, Span, TypeId, nowhere = std.ast

Struct, Member = std.ast

Field, Const, Function = std.ast

AllocError = std.mem

Vec = std.collections

str = std.text

DeclId, ImplId = sema.sema_id

TyId, TyNamed, TyFn, Prim = sema.sema_ty

Def, DefKind, decl_at, module_display = sema.sema_def

SemaFault, TypeFault, PairFault = sema.sema_diag

ExportFault = sema.sema_diag

Checker, Ctx, Binding = sema.sema_check

Inst, subst, inst_of_named, owner_of, push_tparams = sema.sema_inst

is_prim = sema.sema_ty

impl_members, bound_member_types = sema.sema_supply

impl_bound_type, impl_span = sema.sema_supply

type_of = sema.sema_type

type_from_ast, param_type = sema.sema_denote

global_name_type, def_type = sema.sema_type

static_value = sema.sema_static

meta_access, meta_len_chain, is_count_chain = sema.sema_meta

meta_name_fold, meta_refused, walk_name, WalkName = sema.sema_meta
```

### `src/sema/sema_meta.zen`

70 declarations (enums: 2, functions: 56, imports and re-exports: 12).

#### Enums

```zen
WalkName* = WalkNone | WalkHandle | WalkField

MetaCall* = Answered(TyId) | Ordinary
```

#### Functions

```zen
meta_type* = (c :: Checker, node: Expr, ctx: Ctx) Res<TyId, AllocError>

meta_access* = (c :: Checker, ac: Access, ctx: Ctx)
               Res<TyId, AllocError>

meta_len_chain* = (c :: Checker, ac: Access, ctx: Ctx)
                  Res<TyId, AllocError>

chain_callee* = (c :: Checker, callee_id: ExprId, ctx: Ctx)
                Res<TyId, AllocError>

counted_base = (c :: Checker, base: ExprId, ctx: Ctx)
               Res<TyId, AllocError>

meta_form = (
    c      :: Checker,
    target : Expr,
    m      : Meta,
    ac     : Access,
    ctx    : Ctx
) Res<TyId, AllocError>

meta_fold = (
    c      :: Checker,
    target : Expr,
    t      : TypeId,
    ctx    : Ctx
) Res<TyId, AllocError>

meta_count_fold = (c :: Checker, target: Expr, t: TypeId, ctx: Ctx)
                  Res<TyId, AllocError>

meta_count = (
    c      :: Checker,
    target : Expr,
    t      : TypeId,
    ty     : TyId,
    ctx    : Ctx
) Res<TyId, AllocError>

written_count = (
    c      :: Checker,
    node   : Type,
    target : Expr,
    t      : TypeId,
    ty     : TyId,
    ctx    : Ctx
) Res<TyId, AllocError>

counted_decl = (
    c      :: Checker,
    name   : str,
    target : Expr,
    t      : TypeId,
    ty     : TyId,
    ctx    : Ctx
) Res<TyId, AllocError>

count_fields = (c :: Checker, s: Struct) Res<usize, AllocError>

counted_record = (
    c      :: Checker,
    key    : TypeId,
    s      : Struct,
    target : Expr
) Res<TyId, AllocError>

counted_alias = (c :: Checker, al: Alias, owner: Def, target: Expr, t: TypeId)
                Res<TyId, AllocError>

resolved_count = (c :: Checker, target: Expr, t: TypeId, ty: TyId)
                 Res<TyId, AllocError>

meta_decl = (
    c      :: Checker,
    target : Expr,
    t      : TypeId,
    ty     : TyId,
    ctx    : Ctx
) Res<TyId, AllocError>

written_kind = (
    c      :: Checker,
    node   : Type,
    target : Expr,
    t      : TypeId,
    ty     : TyId,
    ctx    : Ctx
) Res<TyId, AllocError>

written_decl = (
    c      :: Checker,
    name   : str,
    target : Expr,
    t      : TypeId,
    ty     : TyId,
    ctx    : Ctx
) Res<TyId, AllocError>

written_alias = (c :: Checker, al: Alias, owner: Def, target: Expr, t: TypeId)
                Res<TyId, AllocError>

meta_record = (c :: Checker, key: TypeId, name: str) Res<TyId, AllocError>

resolved_decl = (c :: Checker, target: Expr, t: TypeId, ty: TyId)
                Res<TyId, AllocError>

meta_refused* = (c :: Checker, node: Expr) Res<TyId, AllocError>

is_count_chain* = (c :: Checker, ac: Access) bool

walk_name* = (c: Checker, text: str) WalkName

span_eq = (a: Span, b: Span) bool

meta_name_fold* = (c :: Checker, id: ExprId, node: Expr, ac: Access)
                  Res<TyId, AllocError>

meta_member_call* = (
    c    :: Checker,
    id   : ExprId,
    node : Expr,
    call : Call,
    ac   : Access,
    ctx  : Ctx
) Res<MetaCall, AllocError>

walk_call_or_ordinary = (
    c    :: Checker,
    id   : ExprId,
    node : Expr,
    call : Call,
    ac   : Access,
    ctx  : Ctx
) Res<MetaCall, AllocError>

walk_verb = (c :: Checker, node: Expr, call: Call, ac: Access)
            Res<MetaCall, AllocError>

walk_proj_or_ordinary = (
    c    :: Checker,
    id   : ExprId,
    node : Expr,
    call : Call,
    ac   : Access,
    ctx  : Ctx
) Res<MetaCall, AllocError>

is_projection = (c :: Checker, call: Call, ac: Access) bool

meta_projection = (
    c    :: Checker,
    id   : ExprId,
    node : Expr,
    ac   : Access,
    ctx  : Ctx
) Res<TyId, AllocError>

project_field = (
    c     :: Checker,
    id    : ExprId,
    node  : Expr,
    ac    : Access,
    fname : str,
    ctx   : Ctx
) Res<TyId, AllocError>

no_projection = (c :: Checker, node: Expr, fname: str, ty: TyId)
                Res<TyId, AllocError>

project_found = (c :: Checker, id: ExprId, node: Expr, f: Found)
                Res<TyId, AllocError>

projectable = (c: Checker, f: Found) bool

walk_projection_type* = (c :: Checker, id: ExprId, ctx: Ctx)
                        Res<Res<TyId>, AllocError>

reproject = (c :: Checker, id: ExprId, fname: str, ctx: Ctx)
            Res<Res<TyId>, AllocError>

field_type_of = (c :: Checker, rty: TyId, fname: str)
                Res<TyId, AllocError>

meta_walk_chain* = (
    c    :: Checker,
    id   : ExprId,
    node : Expr,
    call : Call,
    ac   : Access,
    ctx  : Ctx
) Res<TyId, AllocError>

walk_over_fields = (
    c    :: Checker,
    id   : ExprId,
    node : Expr,
    call : Call,
    ac   : Access,
    ctx  : Ctx
) Res<TyId, AllocError>

walk_root = (
    c    :: Checker,
    id   : ExprId,
    node : Expr,
    call : Call,
    f    : Access,
    ctx  : Ctx
) Res<TyId, AllocError>

walk_typed = (
    c      :: Checker,
    id     : ExprId,
    target : Expr,
    call   : Call,
    t      : TypeId,
    ctx    : Ctx
) Res<TyId, AllocError>

walk_with_body = (
    c      :: Checker,
    id     : ExprId,
    target : Expr,
    t      : TypeId,
    lam    : Lambda,
    ctx    : Ctx
) Res<TyId, AllocError>

walk_fields_of = (
    c      :: Checker,
    target : Expr,
    t      : TypeId,
    ty     : TyId,
    ctx    : Ctx,
    out    :: Vec<str>
) Res<bool, AllocError>

written_walk = (
    c      :: Checker,
    node   : Type,
    target : Expr,
    ty     : TyId,
    ctx    : Ctx,
    out    :: Vec<str>
) Res<bool, AllocError>

walked_decl = (
    c      :: Checker,
    name   : str,
    target : Expr,
    ty     : TyId,
    ctx    : Ctx,
    out    :: Vec<str>
) Res<bool, AllocError>

walked_alias = (
    c      :: Checker,
    al     : Alias,
    owner  : Def,
    target : Expr,
    out    :: Vec<str>
) Res<bool, AllocError>

resolved_walk = (c :: Checker, target: Expr, ty: TyId, out :: Vec<str>)
                Res<bool, AllocError>

walk_collect = (c :: Checker, s: Struct, out :: Vec<str>)
               Res<(), AllocError>

walk_check = (c :: Checker, lam: Lambda, names: Vec<str>, ctx: Ctx)
             Res<(), AllocError>

walk_pass = (
    c       :: Checker,
    lam     : Lambda,
    fname   : str,
    unknown : TyId,
    ctx     : Ctx
) Res<(), AllocError>

walk_pass_with = (
    c       :: Checker,
    lam     : Lambda,
    p0      : Param,
    p1      : Param,
    fname   : str,
    unknown : TyId,
    ctx     : Ctx
) Res<(), AllocError>

is_walk_chain* = (c :: Checker, call: Call, ac: Access) bool

walk_body_arg = (c :: Checker, call: Call) bool

walk_lambda_shape = (c :: Checker, lam: Lambda) bool
```

#### Imports and re-exports

```zen
Expr, Type, TypeId, Access, Meta, Alias, Call, Struct = std.ast

ExprId, Lambda, Param, Span = std.ast

AllocError = std.mem

Vec = std.collections

str = std.text

TyId = sema.sema_ty

Checker, Ctx, WalkBind = sema.sema_check

SemaFault, NameFault, TypeFault = sema.sema_diag

Def, decl_at = sema.sema_def

type_from_ast, alias_target_of = sema.sema_denote

Found, base_of, members_of = sema.sema_member

block_type, type_of = sema.sema_type
```

### `src/sema/sema_module.zen`

28 declarations (functions: 16, imports and re-exports: 12).

#### Functions

```zen
module_named_by* = (c :: Checker, ty: TyId) Res<usize>

alias_module* = (c :: Checker, id: DeclId) Res<usize>

alias_target = (c :: Checker, al: Alias, id: DeclId) Res<usize>

alias_target_type = (c :: Checker, t: TypeId, id: DeclId) Res<usize>

module_for_target = (c :: Checker, n: Named, id: DeclId) Res<usize>

target_module = (c :: Checker, n: Named) Res<usize>

names_a_type = (c :: Checker, name: str, mi: usize) bool

module_not_a_value* = (c :: Checker, span: Span, name: str, mi: usize)
                     Res<TyId, AllocError>

module_access* = (c :: Checker, node: Expr, ac: Access, mi: usize)
                Res<TyId, AllocError>

module_def_type = (c :: Checker, d: Def) Res<TyId, AllocError>

module_ctor_type = (c :: Checker, d: Def) Res<TyId, AllocError>

module_fn_type = (c :: Checker, d: Def) Res<TyId, AllocError>

decl_fn_type = (c :: Checker, d: Def, f: Function) Res<TyId, AllocError>

ret_type = (c :: Checker, f: Function, ctx: Ctx) Res<TyId, AllocError>

not_exported = (c :: Checker, ac: Access, mi: usize)
              Res<TyId, AllocError>

module_name = (c :: Checker, mi: usize) str
```

#### Imports and re-exports

```zen
Expr, Access, Span, TypeId, Named = std.ast

Alias, Function = std.ast

AllocError = std.mem

Vec = std.collections

str = std.text

DeclId = sema.sema_id

TyId = sema.sema_ty

Def, decl_at, module_display = sema.sema_def

SemaFault, ExportFault = sema.sema_diag

Checker, Ctx = sema.sema_check

def_type, decl_as_type = sema.sema_type

type_from_ast, param_type = sema.sema_denote
```

### `src/sema/sema_operand.zen`

10 declarations (functions: 4, imports and re-exports: 6).

#### Functions

```zen
operands_agree* = (c :: Checker, b: Binary, lhs: TyId, rhs: TyId)
                  Res<(), AllocError>

rhs_operand = (c :: Checker, b: Binary, lhs: TyId, rhs: TyId)
              Res<(), AllocError>

settled_agree = (c :: Checker, b: Binary, lhs: TyId, rhs: TyId)
                Res<(), AllocError>

mixed_operands = (c :: Checker, b: Binary, lhs: TyId, rhs: TyId)
                 Res<(), AllocError>
```

#### Imports and re-exports

```zen
Binary = std.ast

AllocError = std.mem

str = std.text

TyId, is_integer = sema.sema_ty

Checker = sema.sema_check

check_literal = sema.sema_trap
```

### `src/sema/sema_own.zen`

94 declarations (types: 3, functions: 69, constants: 1, imports and re-exports: 21).

#### Types

```zen
OwnVar* = {
    name*: str,
    ty*: TyId,
    mutable*: bool,
    owned*: bool,
    scoped*: bool,
    arena*: bool,
    span*: Span,
}

Place* = {
    root*: usize,
    field*: str,
    span*: Span,
}

Own* = {
    vars :: Vec<OwnVar>,
    dead :: Vec<Place>,
    pinned* :: Vec<Pin>,
    escaped* :: usize,
    method* :: str,
    body* :: BlockId,
    alloc*: Alloc,
}
```

#### Functions

```zen
Own* = (a: Alloc) Res<Own, AllocError>

check_own* = (c :: Checker, f: Function, body: BlockId, ctx: Ctx)
             Res<(), AllocError>

receiver_method = (f: Function, ctx: Ctx) str

first_param_is_self = (f: Function) bool

own_params = (c :: Checker, o :: Own, f: Function) Res<(), AllocError>

own_param = (c :: Checker, o :: Own, p: Param) Res<(), AllocError>

own_block = (c :: Checker, o :: Own, id: BlockId, ctx: Ctx)
            Res<(), AllocError>

own_stmt = (c :: Checker, o :: Own, s: Stmt, ctx: Ctx) Res<(), AllocError>

own_bind = (c :: Checker, o :: Own, b: Bind, ctx: Ctx) Res<(), AllocError>

own_target = (c :: Checker, o :: Own, b: Bind, ctx: Ctx)
             Res<(), AllocError>

bind_name = (
    c    :: Checker,
    o    :: Own,
    b    : Bind,
    text : str,
    span : Span,
    ctx  : Ctx
) Res<(), AllocError>

declare_var = (
    c    :: Checker,
    o    :: Own,
    b    : Bind,
    text : str,
    span : Span,
    ctx  : Ctx
) Res<(), AllocError>

revive_field = (c :: Checker, o :: Own, a: Access, ctx: Ctx)
               Res<(), AllocError>

own_expr = (c :: Checker, o :: Own, id: ExprId, ctx: Ctx)
           Res<(), AllocError>

own_binary = (c :: Checker, o :: Own, first: Binary, ctx: Ctx)
             Res<(), AllocError>

own_try = (c :: Checker, o :: Own, t: Try, ctx: Ctx)
          Res<(), AllocError>

own_pair = (c :: Checker, o :: Own, a: ExprId, b: ExprId, ctx: Ctx)
           Res<(), AllocError>

own_elems = (c :: Checker, o :: Own, elems: Vec<ExprId>, ctx: Ctx)
            Res<(), AllocError>

own_record = (c :: Checker, o :: Own, entries: Vec<Member>, ctx: Ctx)
             Res<(), AllocError>

own_member_value = (c :: Checker, o :: Own, m: Member, ctx: Ctx)
                   Res<(), AllocError>

opt_expr = (c :: Checker, o :: Own, e: Res<ExprId>, ctx: Ctx)
           Res<(), AllocError>

use_name = (c :: Checker, o :: Own, node: Expr, id: ExprId, text: str)
           Res<(), AllocError>

use_access = (
    c    :: Checker,
    o    :: Own,
    node : Expr,
    id   : ExprId,
    a    : Access,
    ctx  : Ctx
) Res<(), AllocError>

access_base_text = (c :: Checker, base: ExprId) str

report_if_dead = (
    c     :: Checker,
    o     :: Own,
    span  : Span,
    root  : usize,
    field : str
) Res<(), AllocError>

report_consumed = (
    c     :: Checker,
    o     :: Own,
    span  : Span,
    root  : usize,
    field : str
) Res<(), AllocError>

own_consume = (c :: Checker, o :: Own, x: Consume, ctx: Ctx)
              Res<(), AllocError>

consume_name = (c :: Checker, o :: Own, id: ExprId, text: str)
               Res<(), AllocError>

consume_field = (c :: Checker, o :: Own, node: Expr, a: Access, ctx: Ctx)
                Res<(), AllocError>

consume_field_of = (
    c    :: Checker,
    o    :: Own,
    node : Expr,
    a    : Access,
    root : usize
) Res<(), AllocError>

kill_field = (c :: Checker, o :: Own, node: Expr, a: Access, root: usize)
             Res<(), AllocError>

check_partial_moves = (c :: Checker, o :: Own, mark: usize)
                      Res<(), AllocError>

check_partial_move = (c :: Checker, o :: Own, i: usize)
                     Res<(), AllocError>

report_partial = (c :: Checker, o :: Own, i: usize) Res<(), AllocError>

has_dead_field = (o: Own, root: usize) bool

own_call = (c :: Checker, o :: Own, id: ExprId, k: Call, ctx: Ctx)
           Res<(), AllocError>

own_args = (c :: Checker, o :: Own, k: Call, ctx: Ctx)
           Res<(), AllocError>

own_arg = (
    c       :: Checker,
    o       :: Own,
    a       : Arg,
    repeats : bool,
    escapes : bool,
    ctx     : Ctx
) Res<(), AllocError>

repeating_body = (c :: Checker, k: Call) bool

own_lambda = (
    c       :: Checker,
    o       :: Own,
    l       : Lambda,
    ctx     : Ctx,
    repeats : bool,
    escapes : bool
) Res<(), AllocError>

report_back_edge = (c :: Checker, o :: Own, dmark: usize)
                   Res<(), AllocError>

report_moved_again = (c :: Checker, o :: Own, i: usize)
                     Res<(), AllocError>

own_match = (c :: Checker, o :: Own, m: Match, ctx: Ctx)
            Res<(), AllocError>

own_arm = (
    c      :: Checker,
    o      :: Own,
    a      : Arm,
    dmark  : usize,
    joined :: Vec<Place>,
    ctx    : Ctx
) Res<(), AllocError>

take_dead = (o :: Own, mark: usize, out :: Vec<Place>)
            Res<(), AllocError>

find_var* = (o: Own, text: str) Res<usize>

path_root* = (c :: Checker, o :: Own, id: ExprId) Res<usize>

var_mutable* = (o: Own, text: str) bool

captures_scope* = (o: Own, text: str) bool

refuse_handle_captured* = (
    c    :: Checker,
    o    :: Own,
    node : Expr,
    id   : ExprId,
    text : str
) Res<(), AllocError>

arena_var* = (o: Own, text: str) bool

scoped_var* = (o: Own, text: str) bool

scoped_at = (o: Own, i: usize) bool

owned_at* = (o: Own, root: usize) bool

is_dead = (o: Own, root: usize, field: str) bool

kill = (o :: Own, root: usize, field: str, span: Span)
       Res<(), AllocError>

revive = (o :: Own, root: usize, field: str) Res<(), AllocError>

keep_other = (p: Place, root: usize, field: str, kept :: Vec<Place>)
             Res<(), AllocError>

take_all = (o :: Own) Res<(), AllocError>

own_release = (o :: Own, mark: usize) Res<(), AllocError>

keep_below = (p: Place, mark: usize, kept :: Vec<Place>)
             Res<(), AllocError>

keep_pin = (p: Pin, mark: usize, kept :: Vec<Pin>) Res<(), AllocError>

take_all_pins = (o :: Own) Res<(), AllocError>

place_name* = (c :: Checker, o :: Own, root: usize, field: str)
             Res<str, AllocError>

dotted_name = (c :: Checker, base: str, field: str) Res<str, AllocError>

memo_type = (c :: Checker, id: ExprId) TyId

place_type* = (c :: Checker, o :: Own, id: ExprId) TyId

var_type* = (o: Own, text: str) TyId

refuse* = (c :: Checker, span: Span, fault: SemaFault) Res<(), AllocError>
```

#### Constants

```zen
UNTYPED* : TyId = TyId(index: 0)
```

#### Imports and re-exports

```zen
Expr, ExprId, Block, BlockId, Stmt, Bind = std.ast

Decl, Member, Function, Param = std.ast

Call, Arg, Access, Match, Arm, Lambda, Index, Consume = std.ast

Span, Name, Paren, Try, Unary, Binary = std.ast

Record, FixedArray, Field, Const = std.ast

Alloc, AllocError = std.mem

Vec = std.collections

str, String = std.text

Range = std.core

TyId = sema.sema_ty

Checker, Ctx = sema.sema_check

SemaFault, NameFault = sema.sema_diag

check_receiver, check_write_place = sema.sema_recv

check_scope_returned, check_scope_stored = sema.sema_scope

check_scope_captured, is_scope_value, call_escapes = sema.sema_scope

check_arena_returned, is_arena_backed = sema.sema_scope

scope_alias = sema.sema_scope

Pin, pin_captured, refuse_pinned, refuse_pinned_at = sema.sema_pin

check_drop_copy = sema.sema_drop

is_handle_ty, refuse_handle_at = sema.sema_handle

spelled_lambda = sema.sema_call
```

### `src/sema/sema_pin.zen`

11 declarations (types: 1, functions: 5, imports and re-exports: 5).

#### Types

```zen
Pin* = {
    root*: usize,
    span*: Span,
}
```

#### Functions

```zen
pin_captured* = (c :: Checker, o :: Own, node: Expr, text: str)
                Res<(), AllocError>

pinned_at* = (o: Own, root: usize) bool

first_pin* = (o: Own, root: usize) Res<Pin>

refuse_pinned* = (c :: Checker, o :: Own, span: Span, text: str)
                 Res<(), AllocError>

refuse_pinned_at* = (c :: Checker, o :: Own, span: Span, root: usize)
                    Res<(), AllocError>
```

#### Imports and re-exports

```zen
Expr, Span = std.ast

Range = std.core

Checker = sema.sema_check

SemaFault, CaptureFault = sema.sema_diag

find_var, owned_at, Own = sema.sema_own
```

### `src/sema/sema_place.zen`

33 declarations (functions: 19, imports and re-exports: 14).

#### Functions

```zen
bind_stmt* = (c :: Checker, b: Bind, ctx: Ctx) Res<TyId, AllocError>

plain_write = (b: Bind) bool

assign_binding = (c :: Checker, b: Bind) Res<Binding>

check_rebound* = (c :: Checker, b: Bind) Res<bool, AllocError>

rebound_of = (c :: Checker, b: Bind) Res<Binding>

settled_binding = (found: Res<Binding>) Res<Binding>

report_rebound = (c :: Checker, b: Bind, old: Binding)
                 Res<bool, AllocError>

bind_want* = (c :: Checker, b: Bind, got: TyId, ctx: Ctx)
             Res<TyId, AllocError>

store_want = (c :: Checker, old: TyId, got: TyId) Res<TyId, AllocError>

place_want* = (c :: Checker, id: ExprId, got: TyId, ctx: Ctx)
              Res<TyId, AllocError>

settled_array* = (c :: Checker, ty: TyId) Res<TyId, AllocError>

settled_elem = (c :: Checker, ty: TyId, a: TyArray) Res<TyId, AllocError>

check_assign* = (c :: Checker, b: Bind, got: TyId, want: TyId, ctx: Ctx)
               Res<(), AllocError>

written_want = (c :: Checker, b: Bind, want: TyId) Res<(), AllocError>

bind_target* = (c :: Checker, b: Bind, ty: TyId, ctx: Ctx)
              Res<(), AllocError>

bind_name = (
    c      :: Checker,
    b      : Bind,
    name   : str,
    target : Expr,
    ty     : TyId,
    ctx    : Ctx
)
           Res<(), AllocError>

fresh_or_refused = (
    c      :: Checker,
    b      : Bind,
    name   : str,
    target : Expr,
    ty     : TyId,
    ctx    : Ctx
)
                   Res<(), AllocError>

assign_access* = (c :: Checker, target: Expr, a: Access, ctx: Ctx)
                Res<(), AllocError>

no_storage* = (c :: Checker, target: Expr, a: Access) Res<(), AllocError>
```

#### Imports and re-exports

```zen
Expr, ExprId, Bind, Access = std.ast

AllocError = std.mem

str = std.text

TyId, TyArray, literal_default = sema.sema_ty

Checker, Ctx, Binding = sema.sema_check

SemaFault, NameFault, PairFault = sema.sema_diag

computed_member, writable_member = sema.sema_member

check_literal = sema.sema_trap

const_def = sema.sema_const

check_arms, check_arms_agree = sema.sema_hoist

type_of = sema.sema_type

type_from_ast = sema.sema_denote

settle_variant_at = sema.sema_apply

refuse_handle_value = sema.sema_handle
```

### `src/sema/sema_raise.zen`

22 declarations (functions: 16, imports and re-exports: 6).

#### Functions

```zen
settle_raised* = (
    c    :: Checker,
    f    : Function,
    ctx  : Ctx,
    got  : TyId,
    mark : usize
) Res<(), AllocError>

inferred_error = (c :: Checker, ret: TyId) Res<TyId>

infer_hole = (c :: Checker, r: TyRes) Res<TyId>

settle_signature = (
    c      :: Checker,
    f      : Function,
    ctx    : Ctx,
    got    : TyId,
    raised :: Vec<TyId>
) Res<(), AllocError>

report_if_exported = (c :: Checker, f: Function) Res<(), AllocError>

report_hole = (c :: Checker, f: Function) Res<(), AllocError>

hole_span = (c :: Checker, f: Function) Res<Span>

res_hole_span = (c :: Checker, id: TypeId) Res<Span>

arg_span = (c :: Checker, args: Vec<TypeId>, i: usize) Res<Span>

body_error = (c :: Checker, got: TyId, raised :: Vec<TyId>)
             Res<(), AllocError>

keep_error = (c :: Checker, r: TyRes, raised :: Vec<TyId>)
             Res<(), AllocError>

carries_error = (c :: Checker, r: TyRes) bool

real_error = (c :: Checker, r: TyRes) bool

write_ret = (c :: Checker, f: Function, ctx: Ctx, set: TyId)
            Res<(), AllocError>

write_ret_memo = (c :: Checker, id: TypeId, ctx: Ctx, set: TyId)
                 Res<(), AllocError>

write_settled = (c :: Checker, id: TypeId, r: TyRes, set: TyId)
                Res<(), AllocError>
```

#### Imports and re-exports

```zen
Function, TypeId, Span = std.ast

AllocError = std.mem

Vec = std.collections

TyId, TyRes = sema.sema_ty

Checker, Ctx = sema.sema_check

SemaFault, NameFault = sema.sema_diag
```

### `src/sema/sema_recv.zen`

33 declarations (functions: 22, imports and re-exports: 11).

#### Functions

```zen
check_receiver* = (c :: Checker, o :: Own, k: Call, ctx: Ctx)
                  Res<(), AllocError>

check_method_call = (c :: Checker, o :: Own, a: Access, ctx: Ctx)
                    Res<(), AllocError>

check_receiver_path = (c :: Checker, o :: Own, a: Access, ctx: Ctx)
                      Res<(), AllocError>

require_mutable = (c :: Checker, o :: Own, a: Access) Res<(), AllocError>

snapshotted = (c :: Checker, o :: Own, arg: ExprId, root: usize) bool

check_snapshotted = (c :: Checker, o :: Own, k: Call, root: usize)
                    Res<(), AllocError>

place_mutable = (c :: Checker, o :: Own, id: ExprId) bool

link_mutable = (c :: Checker, o :: Own, a: Access) bool

check_write_place* = (c :: Checker, o :: Own, id: ExprId)
                     Res<(), AllocError>

refuse_immutable_link = (c :: Checker, o :: Own, node: Expr, id: ExprId)
                        Res<(), AllocError>

refuse_link = (c :: Checker, o :: Own, node: Expr, nm: str)
              Res<(), AllocError>

immutable_link = (c :: Checker, o :: Own, id: ExprId) Res<str>

name_link = (o: Own, text: str) Res<str>

access_link = (c :: Checker, o :: Own, a: Access) Res<str>

field_link = (c: Checker, ty: TyId, name: str) Res<str>

wants_mutable = (c: Checker, ty: TyId, name: str) bool

receiver_is_mutable* = (m: Member) bool

first_param_mutable = (f: Function) bool

field_mutable = (c: Checker, ty: TyId, name: str) bool

member_is_mutable = (m: Member) bool

own_member* = (c: Checker, ty: TyId, name: str) Res<Member>

named_member = (c: Checker, n: TyNamed, name: str) Res<Member>
```

#### Imports and re-exports

```zen
Expr, ExprId = std.ast

Struct, Member, Function = std.ast

Call, Access, Index, Name, Paren, Field, Const = std.ast

AllocError = std.mem

str = std.text

TyId, TyNamed = sema.sema_ty

decl_at = sema.sema_def

Checker, Ctx = sema.sema_check

SemaFault, NameFault = sema.sema_diag

Own, var_mutable, path_root = sema.sema_own

place_type, refuse = sema.sema_own
```

### `src/sema/sema_scope.zen`

55 declarations (functions: 40, imports and re-exports: 15).

#### Functions

```zen
check_scope_returned* = (c :: Checker, o :: Own, id: BlockId, b: Block)
                         Res<(), AllocError>

check_scope_stored* = (c :: Checker, id: ExprId, k: Call)
                      Res<(), AllocError>

is_construction* = (c :: Checker, id: ExprId) bool

decl_is_struct = (c :: Checker, d: DeclId) bool

refuse_scope_args = (c :: Checker, k: Call) Res<(), AllocError>

refuse_scope_expr = (c :: Checker, id: ExprId) Res<(), AllocError>

check_scope_captured* = (c :: Checker, o :: Own, span: Span, text: str)
                        Res<(), AllocError>

scope_escape = (c :: Checker, o :: Own, id: ExprId) Res<ExprId>

scope_escape_of = (c :: Checker, o :: Own, id: ExprId) Res<ExprId>

named_scope = (c :: Checker, o :: Own, id: ExprId, text: str) Res<ExprId>

scope_escape_in_args = (c :: Checker, o :: Own, k: Call) Res<ExprId>

scope_escapes = (c :: Checker, o :: Own, id: ExprId) bool

scope_alias* = (c :: Checker, o :: Own, id: ExprId) bool

refuse_scope_returned = (
    c  :: Checker,
    o  :: Own,
    id : ExprId
) Res<(), AllocError>

refuse_scope_node = (c :: Checker, o :: Own, at: ExprId) Res<(), AllocError>

scope_fault_name = (node: Expr) str

scope_carries = (c :: Checker, o :: Own, id: ExprId) bool

may_carry_scope = (c: Checker, ty: TyId) bool

is_scope_value* = (c :: Checker, id: ExprId) bool

call_escapes* = (c :: Checker, o :: Own, k: Call) bool

member_escapes = (c :: Checker, o :: Own, a: Access) bool

member_takes_alloc = (c :: Checker, m: Member) bool

takes_alloc = (c :: Checker, f: Function) bool

param_is_alloc = (c :: Checker, p: Param) bool

type_is_alloc = (c :: Checker, tid: TypeId) bool

check_arena_returned* = (c :: Checker, o :: Own, id: BlockId, b: Block)
                        Res<(), AllocError>

refuse_if_arena = (c :: Checker, o :: Own, id: ExprId) Res<(), AllocError>

is_arena_backed* = (c :: Checker, o :: Own, id: ExprId) bool

is_arena_ty = (c :: Checker, ty: TyId) bool

draws_on_arena = (c :: Checker, o :: Own, id: ExprId) bool

arena_name = (c :: Checker, o :: Own, id: ExprId) Res<str>

arena_name_of = (c :: Checker, o :: Own, id: ExprId) Res<str>

named_arena = (o: Own, text: str) Res<str>

arena_name_in_call = (c :: Checker, o :: Own, k: Call) Res<str>

arena_name_of_callee = (c :: Checker, o :: Own, id: ExprId) Res<str>

arena_name_in_args = (c :: Checker, o :: Own, k: Call) Res<str>

arg_draws_on_arena = (c :: Checker, o :: Own, k: Call, i: usize) bool

holds_pointer = (c :: Checker, o :: Own, id: ExprId) bool

carries_address = (c :: Checker, ty: TyId) bool

is_pointerish = (name: str) bool
```

#### Imports and re-exports

```zen
ExprId, BlockId, Block, Call, Struct = std.ast

Paren, Access, Member, Function, Param, Span, TypeId = std.ast

Try, Name, Expr = std.ast

AllocError = std.mem

str = std.text

Range = std.core

DeclId = sema.sema_id

decl_at = sema.sema_def

Checker = sema.sema_check

tail_expr = sema.sema_hoist

SemaFault, NameFault = sema.sema_diag

refuse, Own, place_type, captures_scope = sema.sema_own

arena_var, scoped_var, UNTYPED = sema.sema_own

TyId = sema.sema_ty

own_member = sema.sema_recv
```

### `src/sema/sema_spine.zen`

9 declarations (functions: 4, imports and re-exports: 5).

#### Functions

```zen
spine_ahead* = (c: Checker, id: ExprId) bool

seed_left_spine* = (c :: Checker, id: ExprId, ctx: Ctx)
                  Res<(), AllocError>

below = (c: Checker, id: ExprId) Res<ExprId>

left_of = (node: Expr) Res<ExprId>
```

#### Imports and re-exports

```zen
Expr, ExprId, Binary = std.ast

AllocError = std.mem

Vec = std.collections

Checker, Ctx = sema.sema_check

type_of = sema.sema_type
```

### `src/sema/sema_static.zen`

24 declarations (functions: 11, imports and re-exports: 13).

#### Functions

```zen
static_value* = (
    c    :: Checker,
    id   : ExprId,
    node : Expr,
    ac   : Access,
    ty   : TyId,
    ctx  : Ctx
) Res<TyId, AllocError>

needs_value = (
    c       :: Checker,
    node    : Expr,
    ac      : Access,
    ty      : TyId,
    carried : TyId
) Res<TyId, AllocError>

static_access* = (
    c    :: Checker,
    id   : ExprId,
    node : Expr,
    ac   : Access,
    ty   : TyId,
    ctx  : Ctx
) Res<TyId, AllocError>

type_access = (
    c    :: Checker,
    id   : ExprId,
    node : Expr,
    ac   : Access,
    ty   : TyId,
    ctx  : Ctx
) Res<TyId, AllocError>

variant_type* = (c :: Checker, ty: TyId, name: str) Res<TyId, AllocError>

variant_value = (c :: Checker, ty: TyId, cs: Case) Res<TyId, AllocError>

variant_ctor = (c :: Checker, ty: TyId, cs: Case) Res<TyId, AllocError>

static_member = (
    c    :: Checker,
    id   : ExprId,
    node : Expr,
    ac   : Access,
    ty   : TyId,
    ctx  : Ctx
) Res<TyId, AllocError>

has_prim_const = (c: Checker, ty: TyId, name: str) bool

prim_const_type = (c :: Checker, ty: TyId, name: str)
                  Res<TyId, AllocError>

numeric_prim = (c: Checker, ty: TyId) bool
```

#### Imports and re-exports

```zen
Expr, ExprId, Access = std.ast

AllocError = std.mem

Vec = std.collections

str = std.text

TyId = sema.sema_ty

is_integer, is_float = sema.sema_ty

SemaFault, TypeFault = sema.sema_diag

Checker, Ctx = sema.sema_check

Case, cases_of, find_case = sema.sema_case

is_case = sema.sema_match

module_named_by, module_access = sema.sema_module

value_access = sema.sema_member

union_carrier = sema.sema_union
```

### `src/sema/sema_supply.zen`

46 declarations (functions: 32, imports and re-exports: 14).

#### Functions

```zen
impl_members* = (
    c    :: Checker,
    n    : TyNamed,
    ty   : TyId,
    name : str,
    out  :: Vec<Found>
) Res<(), AllocError>

local_impl = (
    c    :: Checker,
    n    : TyNamed,
    ty   : TyId,
    name : str,
    id   : ImplId,
    out  :: Vec<Found>
) Res<(), AllocError>

impl_supplies = (
    c    :: Checker,
    n    : TyNamed,
    ty   : TyId,
    name : str,
    id   : ImplId,
    out  :: Vec<Found>
) Res<(), AllocError>

supplied = (
    c    :: Checker,
    n    : TyNamed,
    ty   : TyId,
    name : str,
    id   : ImplId,
    im   : Impl,
    out  :: Vec<Found>
) Res<(), AllocError>

supplied_types = (
    c       :: Checker,
    im      : Impl,
    bound   : TyId,
    name    : str,
    self_ty : TyId,
    out     :: Vec<TyId>
) Res<(), AllocError>

keep_reachable = (
    m             : Member,
    name          : str,
    supplied_here : bool,
    kept          :: Vec<Member>
) Res<(), AllocError>

impl_bound_type* = (c :: Checker, im: Impl, mi: usize)
                   Res<TyId, AllocError>

enter_impl_target_tvars = (c :: Checker, target: str, mi: usize)
                          Res<(), AllocError>

enter_def_tvars = (c :: Checker, d: Def, mi: usize) Res<(), AllocError>

enter_decl_tvars = (c :: Checker, d: Decl, mi: usize) Res<(), AllocError>

has_body = (m: Member) bool

add_supplied = (
    c     :: Checker,
    ty    : TyId,
    bound : TyId,
    name  : str,
    id    : ImplId,
    out   :: Vec<Found>
) Res<(), AllocError>

bound_member_type* = (c :: Checker, bound: TyId, name: str, self_ty: TyId)
                     Res<TyId, AllocError>

bound_member_types* = (
    c       :: Checker,
    bound   : TyId,
    name    : str,
    self_ty : TyId,
    out     :: Vec<TyId>
) Res<(), AllocError>

member_types = (
    c       :: Checker,
    bound   : TyId,
    ms      : Vec<Member>,
    self_ty : TyId,
    out     :: Vec<TyId>
) Res<(), AllocError>

enter_bound_tvars = (c :: Checker, bound: TyId, mi: usize)
                    Res<(), AllocError>

enter_named_tvars = (c :: Checker, n: TyNamed, mi: usize)
                    Res<(), AllocError>

bound_members* = (c :: Checker, bound: TyId, out :: Vec<Member>)
                 Res<(), AllocError>

storage_seat_name* = (c :: Checker, ty: TyId, i: usize)
                     Res<str, AllocError>

storage_member = (m: Member) bool

bound_decl_members = (c :: Checker, n: TyNamed, out :: Vec<Member>)
                     Res<(), AllocError>

copy_struct_members = (d: Decl, out :: Vec<Member>) Res<(), AllocError>

add_all_members = (s: Struct, out :: Vec<Member>) Res<(), AllocError>

bound_module = (c: Checker, bound: TyId) usize

bound_declares* = (c :: Checker, ty: TyId, name: str)
                  Res<bool, AllocError>

impls_declare = (c :: Checker, n: TyNamed, name: str)
                Res<bool, AllocError>

impl_declares = (c :: Checker, n: TyNamed, name: str, id: ImplId)
                Res<bool, AllocError>

impl_bound_declares = (c :: Checker, n: TyNamed, name: str, id: ImplId)
                      Res<bool, AllocError>

bound_of_impl_declares = (c :: Checker, n: TyNamed, name: str, im: Impl)
                         Res<bool, AllocError>

prim_impls_declare = (c :: Checker, p: Prim, name: str)
                     Res<bool, AllocError>

has_member* = (members: Vec<Member>, name: str) bool

impl_span* = (c: Checker, id: ImplId) Span
```

#### Imports and re-exports

```zen
Span = std.ast

Decl, Struct, Impl, Member, Field = std.ast

Function = std.ast

AllocError = std.mem

Vec = std.collections

str = std.text

Range = std.core

ImplId = sema.sema_id

TyId, TyNamed, Prim = sema.sema_ty

Def, decl_at = sema.sema_def

Checker, Ctx = sema.sema_check

Found, member_type = sema.sema_member

enter_struct_tvars, decl_span = sema.sema_member

type_from_ast = sema.sema_denote
```

### `src/sema/sema_trap.zen`

47 declarations (functions: 38, imports and re-exports: 9).

#### Functions

```zen
check_binary* = (c :: Checker, b: Binary, ty: TyId) Res<(), AllocError>

check_divisor = (c :: Checker, b: Binary, ty: TyId) Res<(), AllocError>

divisor_is = (c :: Checker, b: Binary, ty: TyId, d: i64)
             Res<(), AllocError>

divide_by_zero = (c :: Checker, b: Binary) Res<(), AllocError>

min_over_minus_one = (c :: Checker, b: Binary, ty: TyId, d: i64)
                     Res<(), AllocError>

check_min_numerator = (c :: Checker, b: Binary, ty: TyId)
                      Res<(), AllocError>

numerator_is_min = (c :: Checker, b: Binary, ty: TyId, n: i64)
                   Res<(), AllocError>

numerator_matches_min = (c :: Checker, b: Binary, ty: TyId, n: i64, name: str)
                        Res<(), AllocError>

check_overflow = (c :: Checker, b: Binary, ty: TyId) Res<(), AllocError>

with_lhs = (c :: Checker, b: Binary, ty: TyId, x: i64) Res<(), AllocError>

with_both = (c :: Checker, b: Binary, ty: TyId, x: i64, y: i64)
            Res<(), AllocError>

check_fits = (c :: Checker, b: Binary, ty: TyId, v: i64)
             Res<(), AllocError>

fits_or_say = (c :: Checker, b: Binary, ty: TyId, v: i64, name: str)
              Res<(), AllocError>

overflow = (c :: Checker, b: Binary, name: str) Res<(), AllocError>

check_literal* = (c :: Checker, id: ExprId, want: TyId)
                 Res<(), AllocError>

element_agrees* = (c :: Checker, id: ExprId, elem: TyId)
                  Res<(), AllocError>

elements_within = (c :: Checker, id: ExprId, want: TyId)
                  Res<(), AllocError>

array_elements = (c :: Checker, id: ExprId, a: TyArray) Res<(), AllocError>

arm_arrays = (c :: Checker, m: Match, a: TyArray) Res<(), AllocError>

elem_literals = (c :: Checker, lit: ArrayLit, elem: TyId)
                Res<(), AllocError>

literal_within = (c :: Checker, id: ExprId, want: TyId)
                 Res<(), AllocError>

arm_literals = (c :: Checker, m: Match, want: TyId) Res<(), AllocError>

folded_within = (c :: Checker, id: ExprId, want: TyId) Res<(), AllocError>

unfoldable_within = (c :: Checker, id: ExprId, want: TyId) Res<(), AllocError>

literal_kind_within = (c :: Checker, id: ExprId, l: Literal, want: TyId)
                      Res<(), AllocError>

value_within = (c :: Checker, id: ExprId, want: TyId, v: i64)
               Res<(), AllocError>

out_of_range = (c :: Checker, id: ExprId, want: TyId) Res<(), AllocError>

literal_overflows* = (c: Checker, id: ExprId, want: TyId) bool

int_literal_overflows = (c: Checker, id: ExprId, name: str) bool

fits_says = (c: Checker, v: i64, name: str) bool

written_literal = (c: Checker, node: Expr) Res<str, AllocError>

literal_int = (c: Checker, node: Expr) Res<i64>

literal_neg = (c: Checker, u: Unary) Res<i64>

negate_literal = (c: Checker, id: ExprId) Res<i64>

check_index* = (c :: Checker, node: Expr, x: Index, a: TyArray)
               Res<(), AllocError>

index_within = (c :: Checker, node: Expr, x: Index, i: i64, count: usize)
               Res<(), AllocError>

out_of_bounds = (c :: Checker, node: Expr, x: Index) Res<(), AllocError>

written_index = (c: Checker, x: Index) str
```

#### Imports and re-exports

```zen
Expr, ExprId, Binary, Literal = std.ast

Unary, Paren, Index, Match, ArrayLit = std.ast

AllocError = std.mem

str = std.text

TyId, TyArray, is_integer = sema.sema_ty

SemaFault, NameFault, TypeFault = sema.sema_diag

Checker = sema.sema_check

const_int, const_literal, fits, fold = sema.sema_const

len_of, min_of = sema.sema_const
```

### `src/sema/sema_try.zen`

35 declarations (functions: 24, imports and re-exports: 11).

#### Functions

```zen
try_type* = (
    c       :: Checker,
    at      : Span,
    operand : ExprId,
    error   : Res<ExprId>,
    ctx     : Ctx
)
           Res<TyId, AllocError>

try_not_res* = (c :: Checker, at: Span, got: TyId, ctx: Ctx)
              Res<TyId, AllocError>

try_needs_res* = (c :: Checker, at: Span, got: TyId)
                Res<TyId, AllocError>

try_res* = (
    c     :: Checker,
    at    : Span,
    r     : TyRes,
    got   : TyId,
    error : Res<ExprId>,
    ctx   : Ctx
)
          Res<TyId, AllocError>

try_outside_res* = (c :: Checker, at: Span, got: TyId)
                  Res<TyId, AllocError>

try_into* = (
    c     :: Checker,
    at    : Span,
    r     : TyRes,
    got   : TyId,
    error : Res<ExprId>,
    ctx   : Ctx
)
           Res<TyId, AllocError>

try_transform = (
    c    :: Checker,
    at   : Span,
    id   : ExprId,
    r    : TyRes,
    want : TyRes,
    got  : TyId,
    ctx  : Ctx
) Res<TyId, AllocError>

failure_form = (form: ResForm) bool

try_transform_needs_failure = (
    c     :: Checker,
    at    : Span,
    got   : TyId,
    want  : TyId,
    value : TyId
) Res<TyId, AllocError>

try_transform_expr = (
    c     :: Checker,
    id    : ExprId,
    from  : TyId,
    into  : TyId,
    value : TyId,
    ctx   : Ctx
) Res<TyId, AllocError>

try_lambda_at = (c: Checker, id: ExprId) Res<Lambda>

try_mapper = (
    c    :: Checker,
    id   : ExprId,
    l    : Lambda,
    from : TyId,
    into : TyId,
    ctx  : Ctx
) Res<(), AllocError>

try_mapper_arity = (
    c    :: Checker,
    id   : ExprId,
    l    : Lambda,
    from : TyId,
    into : TyId
) Res<(), AllocError>

check_try_mapper = (
    c    :: Checker,
    l    : Lambda,
    from : TyId,
    into : TyId,
    ctx  : Ctx
) Res<(), AllocError>

bind_try_mapper_param = (c :: Checker, p: Param, from: TyId, ctx: Ctx)
                        Res<(), AllocError>

try_merge* = (c :: Checker, at: Span, r: TyRes, want: TyRes, got: TyId)
            Res<TyId, AllocError>

try_absence* = (c :: Checker, at: Span, got: TyId, value: TyId, err: TyId)
              Res<TyId, AllocError>

try_set* = (c :: Checker, at: Span, r: TyRes, want: TyRes)
          Res<TyId, AllocError>

try_into_absence* = (c :: Checker, at: Span, r: TyRes, want: TyRes)
                   Res<TyId, AllocError>

failure_into_absence = (got: ResForm, want: ResForm) bool

try_contained* = (c :: Checker, at: Span, r: TyRes, want: TyRes)
                Res<TyId, AllocError>

try_raises* = (c :: Checker, r: TyRes) Res<TyId, AllocError>

try_declared* = (c :: Checker, at: Span, r: TyRes, want: TyRes)
               Res<TyId, AllocError>

try_no_conversion* = (c :: Checker, at: Span, r: TyRes, want: TyRes)
                    Res<TyId, AllocError>
```

#### Imports and re-exports

```zen
ExprId, Span, Lambda, Paren, Param = std.ast

AllocError = std.mem

Vec = std.collections

TyId, TyRes, ResForm = sema.sema_ty

SemaFault, TypeFault = sema.sema_diag

Checker, Ctx = sema.sema_check

absence_into_failure, both_failures = sema.sema_check

type_of = sema.sema_type

block_type = sema.sema_type

param_type, type_from_ast = sema.sema_denote

push_tparams, module_name = sema.sema_inst
```

### `src/sema/sema_ty.zen`

29 declarations (types: 9, enums: 2, implementations: 2, functions: 10, imports and re-exports: 6).

#### Types

```zen
TyId* = { index*: u32 }

Prim* = { name*: str }

TyNamed* = {
    decl*: DeclId,
    name*: str,
    args*: Vec<TyId>,
}

TyFn* = {
    params*: Vec<TyId>,
    ret*: TyId,
}

TyUnion* = {
    members*: Vec<TyId>,
}

TyArray* = {
    elem*: TyId,
    count*: usize,
}

TyVar* = {
    name*: str,
    owner*: str,
}

TyRes* = {
    value*: TyId,
    error*: TyId,
    form*: ResForm,
}

Types* = {
    kinds :: Vec<Ty>,
    keys :: Vec<String>,
    by_key :: Map<str, TyId>,
    count :: u32,
    alloc: Alloc,
    at* = (self: @Self, id: TyId) Ty
    kind_at* = (self: @Self, i: usize) Ty
    key_at* = (self: @Self, id: TyId) str
    count_of* = (self: @Self) u32
    intern* = (self :: @Self, key: str, kind: Ty) Res<TyId, AllocError>
    fresh = (self :: @Self, key: str, kind: Ty) Res<TyId, AllocError>
    prim* = (self :: @Self, name: str) Res<TyId, AllocError>
    unit* = (self :: @Self) Res<TyId, AllocError>
    bool_ty* = (self :: @Self) Res<TyId, AllocError>
    str_ty* = (self :: @Self) Res<TyId, AllocError>
    infer* = (self :: @Self) Res<TyId, AllocError>
    unknown* = (self :: @Self) Res<TyId, AllocError>
    named* = (self :: @Self, decl: DeclId, qname: str, name: str, args: Vec<TyId>)
             Res<TyId, AllocError>
    declared = (self :: @Self, decl: DeclId, qname: str, name: str,
                args: Vec<TyId>) Res<TyId, AllocError>
    res_absence* = (self :: @Self, value: TyId) Res<TyId, AllocError>
    res_failure* = (self :: @Self, value: TyId, error: TyId)
                   Res<TyId, AllocError>
    res_open* = (self :: @Self, value: TyId) Res<TyId, AllocError>
    res_form = (self :: @Self, value: TyId, error: TyId, form: ResForm)
               Res<TyId, AllocError>
    array* = (self :: @Self, elem: TyId, count: usize)
             Res<TyId, AllocError>
    var* = (self :: @Self, name: str, owner: str) Res<TyId, AllocError>
    fn_ty* = (self :: @Self, params: Vec<TyId>, ret: TyId) Res<TyId, AllocError>
    union_ty* = (self :: @Self, members: Vec<TyId>) Res<TyId, AllocError>
    merge* = (self :: @Self, a: TyId, b: TyId) Res<TyId, AllocError>
    set_has* = (self: @Self, set: TyId, member: TyId) bool
    set_within* = (self: @Self, narrow: TyId, wide: TyId) bool
    members_of* = (self: @Self, set: TyId, out :: Vec<TyId>) Res<(), AllocError>
    copy_members = (self: @Self, out :: Vec<TyId>, members: Vec<TyId>)
                   Res<(), AllocError>
    write_name* = (self: @Self, id: TyId, out :: String) Res<(), AllocError>
    name_of* = (self: @Self, id: TyId) Res<String, AllocError>
    write_res = (self: @Self, r: TyRes, out :: String) Res<(), AllocError>
    write_res_error = (self: @Self, r: TyRes, out :: String) Res<(), AllocError>
    write_named = (self: @Self, n: TyNamed, out :: String) Res<(), AllocError>
    write_arg_names = (self: @Self, args: Vec<TyId>, out :: String)
                      Res<(), AllocError>
    write_fn = (self: @Self, f: TyFn, out :: String) Res<(), AllocError>
    write_array = (self: @Self, a: TyArray, out :: String)
                  Res<(), AllocError>
    write_union = (self: @Self, u: TyUnion, out :: String) Res<(), AllocError>
    write_args = (self: @Self, key :: String, args: Vec<TyId>)
                 Res<(), AllocError>
    write_args_run = (self: @Self, key :: String, args: Vec<TyId>)
                     Res<(), AllocError>
    build_union = (self :: @Self, canon: Vec<TyId>) Res<TyId, AllocError>
    flatten_into = (self: @Self, out :: Vec<TyId>, members: Vec<TyId>)
                   Res<(), AllocError>
    sort_unique_into = (self: @Self, out :: Vec<TyId>, src: Vec<TyId>)
                       Res<(), AllocError>
    insert_ordered = (self: @Self, out :: Vec<TyId>, id: TyId)
                     Res<(), AllocError>
    before = (self: @Self, a: TyId, b: TyId) bool
    vec_has = (self: @Self, haystack: Vec<TyId>, needle: TyId) bool
    all_within = (self: @Self, members: Vec<TyId>, wide: TyId) bool
}
```

#### Enums

```zen
ResForm* = Absence | Failure | Open

Ty* = Prim(Prim)
    | Res(TyRes)
    | Named(TyNamed)
    | Fn(TyFn)
    | Union(TyUnion)
    | Array(TyArray)
    | Var(TyVar)
    | Infer
    | Unknown
```

#### Implementations

```zen
TyId.impl(Eq, {
    eq ::= (self: @Self, other: @Self) bool
})

TyId.impl(Hash, {
    hash = (self: @Self, hasher :: Hasher) u64
})
```

#### Functions

```zen
is_prim* = (name: str) bool

is_integer* = (name: str) bool

fixed_integer* = (name: str) bool

c_integer* = (name: str) bool

is_float* = (name: str) bool

literal_default* = (name: str) str

res_arity* = (form: ResForm) usize

is_failure* = (form: ResForm) bool

Types* = (a: Alloc) Types

put* = (out :: Vec<TyId>, i: usize, v: TyId) Res<(), AllocError>
```

#### Imports and re-exports

```zen
Alloc, AllocError = std.mem

Vec, Map = std.collections

str, String = std.text

Eq, Hash, Hasher = std.core

Range = std.core

DeclId = sema.sema_id
```

### `src/sema/sema_type.zen`

69 declarations (functions: 37, imports and re-exports: 32).

#### Functions

```zen
type_of* = (c :: Checker, id: ExprId, ctx: Ctx) Res<TyId, AllocError>

compute_expr* = (c :: Checker, id: ExprId, ctx: Ctx)
               Res<TyId, AllocError>

expr_kind* = (c :: Checker, id: ExprId, node: Expr, ctx: Ctx)
             Res<TyId, AllocError>

lambda_type* = (c :: Checker, l: Lambda) Res<TyId, AllocError>

array_lit_type* = (c :: Checker, a: ArrayLit, ctx: Ctx)
                 Res<TyId, AllocError>

fixed_array_type* = (c :: Checker, f: FixedArray, ctx: Ctx)
                   Res<TyId, AllocError>

element_of = (c: Checker, ty: TyId) TyId

index_element_type* = (c :: Checker, node: Expr, x: Index, ctx: Ctx)
                     Res<TyId, AllocError>

array_element = (c :: Checker, node: Expr, x: Index, a: TyArray)
               Res<TyId, AllocError>

literal_type* = (c :: Checker, l: Literal) Res<TyId, AllocError>

name_type* = (c :: Checker, id: ExprId, node: Expr, text: str, ctx: Ctx)
            Res<TyId, AllocError>

bound_name_type = (c :: Checker, id: ExprId, b: Binding)
                  Res<TyId, AllocError>

unbound_name_type* = (c :: Checker, node: Expr, text: str, ctx: Ctx)
                    Res<TyId, AllocError>

none_type* = (c :: Checker) Res<TyId, AllocError>

global_name_type* = (c :: Checker, node: Expr, text: str, ctx: Ctx)
                   Res<TyId, AllocError>

value_def_type* = (c :: Checker, node: Expr, d: Def) Res<TyId, AllocError>

variant_name_type* = (c :: Checker, node: Expr, text: str, ctx: Ctx)
                    Res<TyId, AllocError>

bare_variant_type = (c :: Checker, d: Def, text: str)
                   Res<TyId, AllocError>

unresolved_name* = (c :: Checker, node: Expr, text: str)
                  Res<TyId, AllocError>

def_type* = (c :: Checker, d: Def) Res<TyId, AllocError>

def_alias_type* = (c :: Checker, d: Def) Res<TyId, AllocError>

decl_as_type* = (c :: Checker, d: Def) Res<TyId, AllocError>

const_type* = (c :: Checker, d: Def) Res<TyId, AllocError>

const_decl_type = (c :: Checker, x: Decl, d: Def) Res<TyId, AllocError>

written_or_value = (c :: Checker, k: Const, ctx: Ctx) Res<TyId, AllocError>

binary_type* = (c :: Checker, node: Expr, b: Binary, ctx: Ctx)
              Res<TyId, AllocError>

arith_type* = (c :: Checker, lhs: TyId, rhs: TyId) Res<TyId, AllocError>

unary_type* = (c :: Checker, node: Expr, u: Unary, ctx: Ctx)
             Res<TyId, AllocError>

addr_type* = (c :: Checker, node: Expr, u: Unary, inner: TyId, ctx: Ctx)
            Res<TyId, AllocError>

addr_of_access* = (
    c     :: Checker,
    node  : Expr,
    a     : Access,
    inner : TyId,
    ctx   : Ctx
) Res<TyId, AllocError>

no_address* = (c :: Checker, node: Expr, a: Access, inner: TyId)
             Res<TyId, AllocError>

refuse_handle_tail* = (c :: Checker, block: Block, got: TyId)
                      Res<(), AllocError>

tail_node = (block: Block) Res<ExprId>

last_stmt_expr = (block: Block) Res<ExprId>

block_type* = (c :: Checker, id: BlockId, ctx: Ctx)
              Res<TyId, AllocError>

walk_stmts* = (c :: Checker, block: Block, ctx: Ctx)
             Res<TyId, AllocError>

stmt_type* = (c :: Checker, s: Stmt, ctx: Ctx) Res<TyId, AllocError>
```

#### Imports and re-exports

```zen
Expr, ExprId, Literal = std.ast

Decl, Const = std.ast

Block, BlockId, Stmt = std.ast

Binary, Unary, Bind, Match, Access, Call, Lambda = std.ast

ArrayLit, FixedArray, Index = std.ast

AllocError = std.mem

Vec = std.collections

str = std.text

TyId, TyArray = sema.sema_ty

Def, decl_at = sema.sema_def

SemaFault, NameFault = sema.sema_diag

Checker, Ctx, Binding = sema.sema_check

is_predicate = sema.sema_check

try_type = sema.sema_try

alias_module, module_not_a_value = sema.sema_module

match_type = sema.sema_match

access_type, computed_member = sema.sema_member

variant_type = sema.sema_static

call_type = sema.sema_call

meta_type = sema.sema_meta

meta_refused, walk_name, walk_projection_type = sema.sema_meta

WalkName = sema.sema_meta

bind_stmt = sema.sema_place

is_handle_ty, refuse_handle_at = sema.sema_handle

check_binary, check_index, check_literal = sema.sema_trap

element_agrees = sema.sema_trap

check_arms, check_arms_agree = sema.sema_hoist

check_statement = sema.sema_effect

check_eq = sema.sema_bound

operands_agree = sema.sema_operand

seed_left_spine, spine_ahead = sema.sema_spine

type_from_ast, self_type, declared_or_alias = sema.sema_denote
```

### `src/sema/sema_union.zen`

38 declarations (functions: 29, imports and re-exports: 9).

#### Functions

```zen
named_or_union* = (c :: Checker, d: Def, args: Vec<TyId>)
                  Res<TyId, AllocError>

record_set = (c :: Checker, id: TyId, decl: DeclId) Res<(), AllocError>

record_if_union = (c :: Checker, id: TyId, decl: DeclId)
                  Res<(), AllocError>

compute_set = (c :: Checker, id: TyId, decl: DeclId) Res<(), AllocError>

collect_members = (c :: Checker, decl: DeclId, out :: Vec<TyId>)
                  Res<(), AllocError>

decl_members = (c :: Checker, decl: DeclId, d: Decl, out :: Vec<TyId>)
               Res<(), AllocError>

enum_members = (c :: Checker, decl: DeclId, e: Enum, out :: Vec<TyId>)
               Res<(), AllocError>

union_member* = (c :: Checker, decl: DeclId, name: str)
                Res<TyId, AllocError>

member_named = (c :: Checker, d: Def) Res<TyId, AllocError>

member_type = (c :: Checker, decl: DeclId, name: str) Res<TyId, AllocError>

union_carrier* = (c :: Checker, ty: TyId, name: str) Res<TyId, AllocError>

named_carrier = (c :: Checker, n: TyNamed, name: str) Res<TyId, AllocError>

variant_named = (c :: Checker, decl: DeclId, name: str) bool

member_of* = (c :: Checker, ty: TyId, name: str) Res<TyId>

union_member_named = (c :: Checker, u: TyUnion, name: str) Res<TyId>

named_member_of = (c :: Checker, ty: TyId, n: TyNamed, name: str)
                  Res<TyId>

member_declares = (c :: Checker, m: TyId, variant: str) bool

member_is = (c :: Checker, m: TyId, name: str) bool

decl_is_named* = (c :: Checker, decl: DeclId, name: str) bool

decl_kind_names = (d: Decl, name: str) bool

decl_has_variant* = (c :: Checker, decl: DeclId, name: str) bool

decl_names_variant = (d: Decl, name: str) bool

enum_names_variant = (e: Enum, name: str) bool

union_reading* = (c :: Checker, decl: DeclId) bool

enum_union_reading = (c :: Checker, decl: DeclId, d: Decl) bool

no_nominal_variant = (c :: Checker, decl: DeclId, e: Enum) bool

every_variant_named = (c :: Checker, decl: DeclId, e: Enum) bool

names_a_type = (c :: Checker, decl: DeclId, v: Variant) bool

defs_named = (c :: Checker, decl: DeclId, name: str) bool
```

#### Imports and re-exports

```zen
Decl, Enum, Variant = std.ast

AllocError = std.mem

Vec = std.collections

str = std.text

Range = std.core

DeclId = sema.sema_id

TyId, TyNamed, TyUnion = sema.sema_ty

Def, decl_at = sema.sema_def

Checker = sema.sema_check
```

### `src/sema/sema_vararg.zen`

31 declarations (functions: 22, constants: 1, imports and re-exports: 8).

#### Functions

```zen
pack_elem* = (types: Types, t: TyId) Res<TyId>

named_pack_elem = (n: TyNamed) Res<TyId>

pack_slot* = (types: Types, params: Vec<TyId>) Res<usize>

tail_slot = (types: Types, params: Vec<TyId>, i: usize) Res<usize>

slot_of = (types: Types, t: TyId, i: usize) Res<usize>

tail_is_pack* = (tree: Ast, f: Function) bool

param_is_pack = (tree: Ast, f: Function, i: usize) bool

check_varargs* = (c :: Checker) Res<(), AllocError>

written_pack* = (node: Type) bool

check_mentions = (c :: Checker, found: Vec<TypeId>) Res<(), AllocError>

check_mention = (c :: Checker, t: TypeId, tails: Vec<TypeId>)
                Res<(), AllocError>

check_element = (c :: Checker, t: TypeId) Res<(), AllocError>

element_ok = (c: Checker, t: TypeId) bool

element_is_pack = (c: Checker, args: Vec<TypeId>) bool

report_pack = (c :: Checker, t: TypeId, fault: SemaFault) Res<(), AllocError>

collect_tails = (c :: Checker, out :: Vec<TypeId>) Res<(), AllocError>

module_tails = (m: Module, out :: Vec<TypeId>) Res<(), AllocError>

decl_tails = (d: Decl, out :: Vec<TypeId>) Res<(), AllocError>

member_tails = (members: Vec<Member>, out :: Vec<TypeId>)
               Res<(), AllocError>

fn_tail = (f: Function, out :: Vec<TypeId>) Res<(), AllocError>

tail_param = (f: Function, i: usize, out :: Vec<TypeId>)
             Res<(), AllocError>

has_id = (ids: Vec<TypeId>, want: TypeId) bool
```

#### Constants

```zen
VARARG*: str = "vararg"
```

#### Imports and re-exports

```zen
Ast, Module, Decl, Function, Struct, Impl, Member, Type, TypeId = std.ast

AllocError = std.mem

Vec = std.collections

str = std.text

Range = std.core

TyId, Types, TyNamed = sema.sema_ty

Checker = sema.sema_check

SemaFault, NameFault = sema.sema_diag
```

### `src/std/actor/actor.zen`

2 declarations (imports and re-exports: 2).

#### Imports and re-exports

```zen
Actor*, Ref*, ActorError*, ActorStartError* = std.actor.actor_core

Context*, Receive* = std.actor.actor_context
```

### `src/std/actor/actor_context.zen`

4 declarations (types: 2, imports and re-exports: 2).

#### Types

```zen
Context* = {
    env*: Env,
    alloc*: Alloc,
}

Receive*<T> = {
    receive* = (self :: @Self, ctx: Context, message: T) ()
}
```

#### Imports and re-exports

```zen
Env = std.env

Alloc = std.mem
```

### `src/std/actor/actor_core.zen`

4 declarations (types: 2, enums: 2).

#### Types

```zen
Ref*<A> = {
    id: u64,
    stop* = (self: @Self) ()
}

Actor* = {}
```

#### Enums

```zen
ActorError* = Closed | Full

ActorStartError* = OutOfMemory | Unavailable
```

### `src/std/ast/ast.zen`

17 declarations (imports and re-exports: 17).

#### Imports and re-exports

```zen
Pos*, Span*, TriviaKind*, Trivia*, TriviaRun*, no_trivia*, nowhere* = std.ast.ast_span

Ident*, QualifiedName* = std.ast.ast_span

ExprId*, TypeId*, PatternId*, BlockId*, CBindingId* = std.ast.ast_id

BinOp*, UnOp*, Form*, LiteralKind*, Literal* = std.ast.ast_node

Type*, TypeKind*, Named*, Union*, FnType*, ArrayType* = std.ast.ast_node

Pattern*, PatternKind*, PatName*, Destructure* = std.ast.ast_node

Expr*, ExprKind*, Name*, Paren*, ArrayLit*, FixedArray* = std.ast.ast_node

Lambda*, Call*, Arg*, Match*, Arm*, Try*, Record* = std.ast.ast_node

Access*, Index*, Unary*, Binary*, Consume*, Meta* = std.ast.ast_node

Stmt*, StmtKind*, Bind*, ExprStmt*, Block* = std.ast.ast_node

Decl*, DeclKind*, Struct*, Enum*, Variant*, Alias* = std.ast.ast_node

Function*, Impl*, Import*, ImportName*, Const* = std.ast.ast_node

Member*, MemberKind*, Field*, Param*, TParam* = std.ast.ast_node

Module*, ModuleOrigin*, CHeader*, COpaque*, CTypeBinding*, CBinding* = std.ast.ast_node

functions* = std.ast.ast_node

Ast* = std.ast.ast_arena

NodeRef*, node_at*, expr_node_at*, in_span*, before*, inside* = std.ast.ast_find
```

### `src/std/ast/ast_arena.zen`

15 declarations (types: 2, functions: 4, constants: 1, imports and re-exports: 8).

#### Types

```zen
NodeArena<T> = {
    pages :: Vec<Ptr<T>>,
    len :: usize = 0,
    alloc: Alloc,
    add = (self :: @Self, value: T) Res<(), AllocError>
    at = (self: @Self, i: usize) T
}

Ast* = {
    modules :: Vec<Module>,
    module_origins :: Vec<ModuleOrigin>,
    c_bindings :: Vec<CBinding>,
    exprs :: NodeArena<Expr>,
    types :: NodeArena<Type>,
    patterns :: NodeArena<Pattern>,
    blocks :: NodeArena<Block>,
    trivia :: Vec<Trivia>,
    expr_count :: u32 = 0,
    type_count :: u32 = 0,
    pattern_count :: u32 = 0,
    block_count :: u32 = 0,
    c_binding_count :: u32 = 0,
    alloc: Alloc,
    add_expr* = (self :: @Self, node: Expr) Res<ExprId, AllocError>
    add_type* = (self :: @Self, node: Type) Res<TypeId, AllocError>
    add_pattern* = (self :: @Self, node: Pattern) Res<PatternId, AllocError>
    add_block* = (self :: @Self, node: Block) Res<BlockId, AllocError>
    add_module* = (self :: @Self, node: Module) Res<(), AllocError>
    add_c_module* = (self :: @Self, node: Module, binding: CBinding)
                    Res<CBindingId, AllocError>
    expr_at* = (self: @Self, id: ExprId) Expr
    type_at* = (self: @Self, id: TypeId) Type
    pattern_at* = (self: @Self, id: PatternId) Pattern
    block_at* = (self: @Self, id: BlockId) Block
    module_count* = (self: @Self) usize
    module_at* = (self: @Self, i: usize) Res<Module>
    module_origin_at* = (self: @Self, i: usize) Res<ModuleOrigin>
    c_binding_at* = (self: @Self, id: CBindingId) Res<CBinding>
    c_type_at* = (self: @Self, module: u32, decl: u32) Res<CTypeBinding>
    expr_ids* = (self: @Self) usize
    type_ids* = (self: @Self) usize
    pattern_ids* = (self: @Self) usize
    block_ids* = (self: @Self) usize
    trivia_count* = (self: @Self) usize
    exprs_each* = (self: @Self, body: (id: ExprId, node: Expr) ()) ()
    types_each* = (self: @Self, body: (id: TypeId, node: Type) ()) ()
    types_where* = (self: @Self, keep: (node: Type) bool, out :: Vec<TypeId>)
                   Res<(), AllocError>
    patterns_each* = (self: @Self, body: (id: PatternId, node: Pattern) ()) ()
    blocks_each* = (self: @Self, body: (id: BlockId, node: Block) ()) ()
    trivia_mark* = (self: @Self) usize
    add_trivia* = (self :: @Self, item: Trivia) Res<(), AllocError>
    trivia_run* = (self: @Self, mark: usize) TriviaRun
    trivia_at* = (self: @Self, run: TriviaRun, i: usize) Trivia
}
```

#### Functions

```zen
NodeArena = <T>(a: Alloc) NodeArena<T>

c_type_in = (binding: CBinding, decl: u32) Res<CTypeBinding>

stale = (what: str, index: usize, len: usize) ()

Ast* = (a: Alloc) Ast
```

#### Constants

```zen
NODE_PAGE: usize = 256
```

#### Imports and re-exports

```zen
Alloc, AllocError, Ptr, null_ptr = std.mem

str = std.text

Range = std.core

Trivia, TriviaRun = std.ast.ast_span

ExprId, TypeId, PatternId, BlockId, CBindingId = std.ast.ast_id

Expr, Type, Pattern, Block, Module = std.ast.ast_node

ModuleOrigin, CBinding = std.ast.ast_node

CTypeBinding = std.ast.ast_node
```

### `src/std/ast/ast_find.zen`

12 declarations (enums: 1, functions: 7, imports and re-exports: 4).

#### Enums

```zen
NodeRef* = ExprNode(ExprId)
    | TypeNode(TypeId)
    | PatternNode(PatternId)
    | BlockNode(BlockId)
```

#### Functions

```zen
in_span* = (span: Span, file: str, p: Pos) bool

before* = (a: Pos, b: Pos) bool

inside* = (inner: Span, outer: Span) bool

node_at* = (tree: Ast, file: str, p: Pos) Res<NodeRef>

expr_node_at* = (tree: Ast, file: str, p: Pos) Res<ExprId>

take = (cand: Span, file: str, p: Pos, have: bool, best: Span) bool

empty_span = () Span
```

#### Imports and re-exports

```zen
str = std.text

Pos, Span = std.ast.ast_span

ExprId, TypeId, PatternId, BlockId = std.ast.ast_id

Ast = std.ast.ast_arena
```

### `src/std/ast/ast_id.zen`

14 declarations (types: 5, implementations: 8, imports and re-exports: 1).

#### Types

```zen
ExprId* = { index*: u32 }

TypeId* = { index*: u32 }

PatternId* = { index*: u32 }

BlockId* = { index*: u32 }

CBindingId* = { index*: u32 }
```

#### Implementations

```zen
ExprId.impl(Eq, {
    eq ::= (self: @Self, other: @Self) bool
})

ExprId.impl(Hash, {
    hash = (self: @Self, hasher :: Hasher) u64
})

TypeId.impl(Eq, {
    eq ::= (self: @Self, other: @Self) bool
})

TypeId.impl(Hash, {
    hash = (self: @Self, hasher :: Hasher) u64
})

PatternId.impl(Eq, {
    eq ::= (self: @Self, other: @Self) bool
})

PatternId.impl(Hash, {
    hash = (self: @Self, hasher :: Hasher) u64
})

BlockId.impl(Eq, {
    eq ::= (self: @Self, other: @Self) bool
})

BlockId.impl(Hash, {
    hash = (self: @Self, hasher :: Hasher) u64
})
```

#### Imports and re-exports

```zen
Eq, Hash, Hasher = std.core.core
```

### `src/std/ast/ast_named.zen`

33 declarations (types: 2, enums: 1, functions: 22, imports and re-exports: 8).

#### Types

```zen
TypeAt* = {
    span*: Span,
    id*: TypeId,
}

ValueAt* = {
    span*: Span,
    id*: ExprId,
}
```

#### Enums

```zen
Tell* = Nothing
    | Sig(Function)
    | OfType(TypeAt)
    | OfValue(ValueAt)
    | Imported(Ident)
```

#### Functions

```zen
told_at* = (tree: Ast, file: str, p: Pos) Tell

is_nothing* = (t: Tell) bool

module_index_of* = (tree: Ast, file: str) Res<usize>

pick = (have: Tell, cand: Tell) Tell

named_at = (tree: Ast, file: str, p: Pos) Tell

stmt_named = (s: Stmt, file: str, p: Pos) Tell

decl_told = (d: Decl, file: str, p: Pos) Tell

import_told = (im: Import, file: str, p: Pos) Tell

imported_told = (name: Ident, file: str, p: Pos) Tell

fn_told = (f: Function, file: str, p: Pos) Tell

params_told = (ps: Vec<Param>, file: str, p: Pos) Tell

param_told = (prm: Param, file: str, p: Pos) Tell

const_told = (cn: Const, file: str, p: Pos) Tell

members_told = (ms: Vec<Member>, file: str, p: Pos) Tell

member_told = (m: Member, file: str, p: Pos) Tell

field_told = (span: Span, t: Res<TypeId>, v: Res<ExprId>, hit: bool) Tell

node_told = (tree: Ast, file: str, p: Pos) Tell

expr_told = (tree: Ast, e: ExprId) Tell

pick_bound = (have: Tell, s: Stmt, span: Span, e: ExprId) Tell

bind_told = (have: Tell, b: Bind, span: Span, e: ExprId) Tell

at_type = (span: Span, id: TypeId, hit: bool) Tell

at_value = (span: Span, id: ExprId, hit: bool) Tell
```

#### Imports and re-exports

```zen
str = std.text

Range = std.core

Pos, Span = std.ast.ast_span

ExprId, TypeId = std.ast.ast_id

Ast = std.ast.ast_arena

Decl, Function, Param, Member, Const, Bind, Stmt = std.ast.ast_node

Ident, Import = std.ast

node_at, in_span = std.ast.ast_find
```

### `src/std/ast/ast_node.zen`

65 declarations (types: 49, enums: 12, functions: 1, imports and re-exports: 3).

#### Types

```zen
Literal* = {
    kind*: LiteralKind,
    text*: str,
}

Type* = {
    kind*: TypeKind,
    span*: Span,
    leading*: TriviaRun,
    trailing*: TriviaRun,
}

Named* = {
    name*: Ident,
    args*: Vec<TypeId>,
}

Union* = {
    members*: Vec<TypeId>,
}

FnType* = {
    tparams*: Vec<TParam>,
    params*: Vec<Param>,
    params_span*: Span,
    ret*: TypeId,
}

ArrayType* = {
    elem*: TypeId,
    count*: ExprId,
}

Pattern* = {
    kind*: PatternKind,
    span*: Span,
    leading*: TriviaRun,
    trailing*: TriviaRun,
}

PatName* = {
    name*: QualifiedName,
}

Destructure* = {
    name*: QualifiedName,
    binder*: PatternId,
}

Expr* = {
    kind*: ExprKind,
    span*: Span,
    leading*: TriviaRun,
    trailing*: TriviaRun,
}

Name* = {
    text*: str,
}

Paren* = {
    inner*: ExprId,
}

ArrayLit* = {
    elems*: Vec<ExprId>,
}

FixedArray* = {
    type*: TypeId,
    elems*: Vec<ExprId>,
    args_span*: Span,
}

Lambda* = {
    tparams*: Vec<TParam>,
    params*: Vec<Param>,
    params_span*: Span,
    ret*: Res<TypeId>,
    body*: BlockId,
}

Call* = {
    callee*: ExprId,
    targs*: Vec<TypeId>,
    args*: Vec<Arg>,
    args_span*: Span,
}

Arg* = {
    name*: Res<Ident>,
    value*: ExprId,
    span*: Span,
    leading*: TriviaRun,
    trailing*: TriviaRun,
}

Match* = {
    scrutinee*: ExprId,
    name_span*: Span,
    arms*: Vec<Arm>,
    arms_span*: Span,
}

Arm* = {
    pattern*: PatternId,
    arrow_span*: Span,
    body*: ExprId,
    span*: Span,
    leading*: TriviaRun,
    trailing*: TriviaRun,
}

Try* = {
    operand*: ExprId,
    name_span*: Span,
    error*: Res<ExprId>,
}

Record* = {
    entries*: Vec<Member>,
}

Access* = {
    base*: ExprId,
    name*: Ident,
}

Index* = {
    base*: ExprId,
    index*: ExprId,
    op_span*: Span,
}

Unary* = {
    op*: UnOp,
    op_span*: Span,
    operand*: ExprId,
}

Binary* = {
    op*: BinOp,
    op_span*: Span,
    lhs*: ExprId,
    rhs*: ExprId,
}

Consume* = {
    operand*: ExprId,
}

Meta* = {
    value*: Res<ExprId>,
    name*: Res<Ident>,
    type*: Res<TypeId>,
}

Stmt* = {
    kind*: StmtKind,
    span*: Span,
    leading*: TriviaRun,
    trailing*: TriviaRun,
}

Bind* = {
    target*: ExprId,
    type*: Res<TypeId>,
    mutable*: bool,
    value*: ExprId,
}

ExprStmt* = {
    expr*: ExprId,
}

Block* = {
    stmts*: Vec<Stmt>,
    value*: Res<ExprId>,
    span*: Span,
    leading*: TriviaRun,
    trailing*: TriviaRun,
}

Decl* = {
    kind*: DeclKind,
    span*: Span,
    leading*: TriviaRun,
    trailing*: TriviaRun,
}

Struct* = {
    name*: Ident,
    exported*: bool,
    tparams*: Vec<TParam>,
    members*: Vec<Member>,
    body_span*: Span,
}

Enum* = {
    name*: Ident,
    exported*: bool,
    tparams*: Vec<TParam>,
    variants*: Vec<Variant>,
    leading_bar*: Res<Span>,
}

Variant* = {
    name*: Ident,
    payload*: Res<TypeId>,
    span*: Span,
    leading*: TriviaRun,
    trailing*: TriviaRun,
}

Alias* = {
    name*: Ident,
    exported*: bool,
    tparams*: Vec<TParam>,
    target*: TypeId,
}

Function* = {
    name*: Ident,
    exported*: bool,
    form*: Form,
    tparams*: Vec<TParam>,
    params*: Vec<Param>,
    params_span*: Span,
    ret*: Res<TypeId>,
    body*: Res<BlockId>,
}

Impl* = {
    target*: Ident,
    bound*: TypeId,
    members*: Vec<Member>,
    body_span*: Span,
}

Import* = {
    names*: Vec<ImportName>,
    module*: QualifiedName,
}

ImportName* = {
    name*: Ident,
    exported*: bool,
    span*: Span,
    leading*: TriviaRun,
    trailing*: TriviaRun,
}

Const* = {
    name*: Ident,
    exported*: bool,
    mutable*: bool,
    type*: Res<TypeId>,
    value*: ExprId,
}

Member* = {
    kind*: MemberKind,
    span*: Span,
    leading*: TriviaRun,
    trailing*: TriviaRun,
    name* = (self: @Self) Ident
    named* = (self: @Self, n: str) bool
    exported* = (self: @Self) bool
    mutable* = (self: @Self) bool
}

Field* = {
    name*: Ident,
    exported*: bool,
    mutable*: bool,
    type*: Res<TypeId>,
    value*: Res<ExprId>,
}

Param* = {
    name*: Ident,
    mutable*: bool,
    type*: Res<TypeId>,
    span*: Span,
    leading*: TriviaRun,
    trailing*: TriviaRun,
    binder* = (self: @Self) str
}

TParam* = {
    name*: Ident,
    bounds*: Vec<TypeId>,
    span*: Span,
    leading*: TriviaRun,
    trailing*: TriviaRun,
}

CHeader* = {
    path*: str,
    system*: bool,
}

COpaque* = {
    decl*: u32,
    spelling*: str,
}

CBinding* = {
    headers*: Vec<CHeader>,
    types*: Vec<CTypeBinding>,
}

Module* = {
    name*: str,
    decls*: Vec<Decl>,
    span*: Span,
    leading*: TriviaRun,
    trailing*: TriviaRun,
}
```

#### Enums

```zen
BinOp* = Add
    | Sub
    | Mul
    | Div
    | Rem
    | AddWrap
    | SubWrap
    | MulWrap
    | Equal
    | NotEqual
    | Less
    | LessEq
    | Greater
    | GreaterEq
    | And
    | Or

UnOp* = Not | Neg | Addr

Form* = Required | Sealed | Default | Hook

LiteralKind* = Int | Float | Str | Char | Bool

TypeKind* = Named(Named)
    | Union(Union)
    | Fn(FnType)
    | Array(ArrayType)
    | Unit
    | SelfType
    | Infer
    | Variadic

PatternKind* = Name(PatName)
    | Destructure(Destructure)
    | Wild
    | Literal(Literal)

ExprKind* = Name(Name)
    | Literal(Literal)
    | Unit
    | SelfType
    | Scope
    | Meta(Meta)
    | Paren(Paren)
    | Array(ArrayLit)
    | FixedArray(FixedArray)
    | Lambda(Lambda)
    | Call(Call)
    | Match(Match)
    | Try(Try)
    | Record(Record)
    | Access(Access)
    | Index(Index)
    | Unary(Unary)
    | Binary(Binary)
    | Consume(Consume)
    | Block(BlockId)

StmtKind* = Bind(Bind) | Expr(ExprStmt) | Decl(Decl) | Block(BlockId)

DeclKind* = Struct(Struct)
    | Enum(Enum)
    | Alias(Alias)
    | Function(Function)
    | Impl(Impl)
    | Import(Import)
    | Const(Const)

MemberKind* = Field(Field) | Const(Const) | Function(Function)

CTypeBinding* = | Opaque(COpaque)

ModuleOrigin* = Source | CBinding(CBindingId)
```

#### Functions

```zen
functions* = (self: Module, a: Alloc) Res<Vec<Function>, AllocError>
```

#### Imports and re-exports

```zen
Span, Ident, QualifiedName, TriviaRun = std.ast.ast_span

ExprId, TypeId, PatternId, BlockId, CBindingId = std.ast.ast_id

Alloc, AllocError = std.mem
```

### `src/std/ast/ast_span.zen`

10 declarations (types: 6, enums: 1, implementations: 1, functions: 2).

#### Types

```zen
Pos* = {
    line*: usize,
    col*: usize,
    before* = (self: @Self, other: @Self) bool
    at_or_after* = (self: @Self, other: @Self) bool
}

Span* = {
    file*: str,
    start*: Pos,
    end*: Pos,
}

Trivia* = {
    kind*: TriviaKind,
    text*: str,
    span*: Span,
}

TriviaRun* = {
    at*: usize,
    len*: usize,
}

Ident* = {
    text*: str,
    span*: Span,
}

QualifiedName* = {
    segments*: Vec<Ident>,
    span*: Span,
}
```

#### Enums

```zen
TriviaKind* = LineComment | BlockComment | Blank
```

#### Implementations

```zen
Pos.impl(Display, {
    toString ::= (self: @Self, out :: Sink) Res<(), WriteError>
})
```

#### Functions

```zen
no_trivia* = () TriviaRun

nowhere* = () Span
```

### `src/std/build/build.zen`

51 declarations (types: 17, enums: 9, implementations: 4, functions: 5, constants: 10, imports and re-exports: 6).

#### Types

```zen
Module* = {
    functions* = (self: @Self, a: Alloc) Res<Vec<Function>, AllocError>
}

Function* = {}

StableName* = {
    stable_name* ::= (self: @Self) str
}

Target* = {
    os*: Os,
    arch*: Arch,
    abi*: Abi,
    clang_triple* = (self: @Self) Res<str>
}

Package* = {
    url*: str,
    version*: str,
    hash*: str,
}

Dep* = {
    name*: str,
}

Exe* = {
    src*: Path,
    deps*: Vec<Dep>,
    optimize* :: str = "speed",
    strip* :: bool = false,
    out* :: Res<Path> = None,
}

Lib* = {
    src*: Path,
    libs*: Vec<str>,
    paths*: Vec<str>,
}

Extern* = {
    src*: Path,
    libs*: Vec<str>,
    paths*: Vec<str>,
}

CImport* = {
    headers*: Vec<str>,
    include_paths*: Vec<str>,
    defines*: Vec<str>,
    libraries*: Vec<str>,
    target*: Target,
}

Test* = {
    tests*: Vec<Function>,
    deps*: Vec<Dep>,
}

Bench* = {
    benches*: Vec<Function>,
    budgets*: Vec<Budget>,
}

Budget* = {
    name*: str,
    ns_op*: u64,
    allocs_op*: u64,
    bytes_op*: u64,
}

BuildArgs* = {
    root*: str,
    emission* :: Emission = Emission.Check,
    entry* :: str = "",
    std_root* :: str = "",
    symbol_map* :: str = "",
    ffi* :: bool = false,
    repeat* :: usize = 1,
    permute* :: Permutation = Permutation.Natural,
    emits* = (self: @Self) bool
    writes_file* = (self: @Self) bool
}

ProjectArgs* = {
    root* :: str = ".",
    target* :: str = "",
    std_root* :: str = "",
    argv*: Vec<str>,
    args_at* :: usize = 0,
}

BuildFlags* = {
    root* :: str = "",
    out* :: str = "",
    dir* :: str = "",
    entry* :: str = "",
    std_root* :: str = "",
    symbol_map* :: str = "",
    emit_c* :: bool = false,
    ffi* :: bool = false,
    repeat* :: usize = 1,
    permute* :: str = "",
    set_root* = (self :: @Self, value: str) ()
    set_out* = (self :: @Self, value: str) ()
    set_dir* = (self :: @Self, value: str) ()
    set_entry* = (self :: @Self, value: str) ()
    set_std_root* = (self :: @Self, value: str) ()
    set_symbol_map* = (self :: @Self, value: str) ()
    set_repeat* = (self :: @Self, value: usize) ()
    set_permute* = (self :: @Self, value: str) ()
    enable_emit_c* = (self :: @Self) ()
    enable_ffi* = (self :: @Self) ()
    apply_switch* = (self :: @Self, flag: BuildFlag) ()
    apply_setting* = (self :: @Self, flag: BuildFlag, value: str) ()
    compiles_source* = (self: @Self) bool
    finish* = (self: @Self) Res<BuildArgs, BuildArgFault>
    emission = (self: @Self) Emission
}

Builder* = {
    os*: Os,
    arch*: Arch,
    env*: Env,
    alloc*: Alloc,
    args*: BuildArgs = BuildArgs(root: ""),
    module* = (self: @Self, path: Path) Module
    target* = (self: @Self) Target
    add* ::= (self :: @Self, name: str, pkg: Package) Res<Dep, BuildError>
    remove* ::= (self :: @Self, name: str) Res<(), BuildError>
    exe* = (self :: @Self, name: str, target: Exe) Res<(), BuildError>
    lib* = (self :: @Self, name: str, target: Lib) Res<Dep, BuildError>
    extern* = (self :: @Self, name: str, target: Extern) Res<Dep, BuildError>
    c_import* = (self :: @Self, name: str, import: CImport)
        Res<Dep, BuildError>
    test* = (self :: @Self, name: str, target: Test) Res<(), BuildError>
    bench* = (self :: @Self, name: str, target: Bench) Res<(), BuildError>
    budget* = (self :: @Self, d: Duration) ()
}
```

#### Enums

```zen
BuildFault* = NotFound | FetchFailed | VersionConflict | HashMismatch

BuildError* = BuildFault | AllocError

Os* = Macos | Linux | Windows

Arch* = X86_64 | Arm64

Abi* = Gnu | Musl | Msvc | Darwin

Emission* = Check | CStdout | CFile(str) | CDir(str)

Permutation* = Natural | Reverse | Rotate | Interleave

BuildArgFault* = MissingRoot | MissingEmit

BuildFlag* = EmitC
    | EmitDir
    | Out
    | Entry
    | StdRoot
    | SymbolMap
    | Repeat
    | Permute
    | Ffi
```

#### Implementations

```zen
Os.impl(StableName, {
    stable_name = (self: @Self) str
})

Arch.impl(StableName, {
    stable_name = (self: @Self) str
})

Abi.impl(StableName, {
    stable_name = (self: @Self) str
})

Permutation.impl(StableName, {
    stable_name = (self: @Self) str
})
```

#### Functions

```zen
index* = (self: Permutation, n: usize, i: usize) usize

interleaved = (n: usize, i: usize) usize

permutation* = (text: str) Permutation

build_options* = (a: Alloc) Res<Options<BuildFlag>, AllocError>

repeat_count = (text: str) usize
```

#### Constants

```zen
FLAG_EMIT_C*: str = "--emit-c"

FLAG_EMIT_DIR*: str = "--emit-c-dir"

FLAG_OUT*: str = "-o"

FLAG_ENTRY*: str = "--entry"

FLAG_STD*: str = "--std"

FLAG_SYMBOL_MAP*: str = "--symbol-map"

FLAG_REPEAT*: str = "--repeat"

FLAG_PERMUTE*: str = "--permute"

FLAG_FFI*: str = "--ffi"

ZEN_STD_ENV*: str = "ZEN_STD"
```

#### Imports and re-exports

```zen
Alloc = std.mem

Env = std.env

Vec = std.collections

str = std.text

Range = std.core

Options, options = std.cli
```

### `src/std/cli/cli.zen`

13 declarations (types: 4, functions: 4, constants: 1, imports and re-exports: 4).

#### Types

```zen
Spec*<T> = {
    name*: str,
    id*: T,
    value*: bool,
}

Item*<T> = {
    named*: Res<T>,
    word*: str,
}

Options*<T> = {
    rules :: Vec<Spec<T>>,
    flag* = (self :: @Self, name: str, id: T) Res<(), AllocError>
    setting* = (self :: @Self, name: str, id: T) Res<(), AllocError>
    args* = (self: @Self, argv: Vec<str>, start: usize) Args<T>
}

Args*<T> = {
    argv: Vec<str>,
    rules: Vec<Spec<T>>,
    at :: usize,
    bad* :: str,
    done* = (self: @Self) bool
    clean* = (self: @Self) bool
    next* = (self :: @Self) Res<Item<T>>
    reject* = (self :: @Self, word: str) ()
    find = (self: @Self, word: str) Res<Spec<T>>
    value_for = (self :: @Self, id: T, option: str) Res<Item<T>>
    word_at = (self: @Self, index: usize) str
}
```

#### Functions

```zen
options* = <T>(a: Alloc) Options<T>

is_flag* = (word: str) bool

is_word* = (word: str) bool

arg_at* = (argv: Vec<str>, index: usize) str
```

#### Constants

```zen
OPTIONS_END*: str = "--"
```

#### Imports and re-exports

```zen
Alloc, AllocError = std.mem

str = std.text

Vec = std.collections

Range = std.core
```

### `src/std/collections/collections.zen`

4 declarations (imports and re-exports: 4).

#### Imports and re-exports

```zen
Vec* = std.collections.collections_vec

Map* = std.collections.collections_map

vararg* = std.collections.collections_vararg

sort*, Ordered* = std.collections.collections_sort
```

### `src/std/collections/collections_map.zen`

15 declarations (types: 2, functions: 4, constants: 5, imports and re-exports: 4).

#### Types

```zen
Entry<K, V> = {
    hash: u64,
    key: K,
    value: V,
}

Map*<K: Eq + Hash, V> = {
    entries :: Vec<Entry<K, V>>,
    slots :: Vec<usize>,
    alloc: Alloc,
    set* = (self :: @Self, key: K, value: V) Res<(), AllocError>
    get* = (self: @Self, key: K) Res<V>
    len* = (self: @Self) usize
    pairs* = (self: @Self, body: (
        h     : LoopHandle,
        key   : K,
        value : V
    ) ()) ()
    place = (self :: @Self, s: usize, entry: Entry<K, V>) Res<(), AllocError>
    append = (self :: @Self, s: usize, entry: Entry<K, V>) Res<(), AllocError>
    insert = (self :: @Self, entry: Entry<K, V>) Res<(), AllocError>
    index_of = (self: @Self, h: u64, key: K) Res<usize>
    settle = (self: @Self, h: u64, key: K) Res<usize>
    walk = (self: @Self, h: u64, key: K, n: usize) Res<usize>
    settles = (self: @Self, s: usize, h: u64, key: K) bool
    confirms = (self: @Self, i: usize, h: u64, key: K) bool
    reserve = (self :: @Self) Res<(), AllocError>
    rehash = (self :: @Self) Res<(), AllocError>
    refill = (self :: @Self) Res<(), AllocError>
    relink = (self :: @Self, i: usize) Res<(), AllocError>
}
```

#### Functions

```zen
to_usize = (self: u64) usize

empty_slots = (a: Alloc, n: usize) Res<Vec<usize>, AllocError>

put = <T>(v :: Vec<T>, i: usize, value: T) Res<(), AllocError>

Map* = <K: Eq + Hash, V>(a: Alloc) Map<K, V>
```

#### Constants

```zen
SLOT_EMPTY: usize = 0

SLOTS_MIN: usize = 8

LOAD_NUM: usize = 3

LOAD_DEN: usize = 4

SMALL_MAX: usize = 6
```

#### Imports and re-exports

```zen
Alloc, AllocError = std.mem

Range = std.core.range

Vec = std.collections.collections_vec

LoopHandle = std.core.loop.loop_handle
```

### `src/std/collections/collections_sort.zen`

9 declarations (types: 1, functions: 5, imports and re-exports: 3).

#### Types

```zen
Ordered* = {
    before* = (self: @Self, other: @Self) bool
}
```

#### Functions

```zen
sort*<T: Ordered> = (xs :: Vec<T>) Res<(), AllocError>

sink<T> = (xs :: Vec<T>, at: usize) Res<(), AllocError>

out_of_order<T> = (xs: Vec<T>, j: usize) bool

swap_at<T> = (xs :: Vec<T>, j: usize) Res<(), AllocError>

swap_pair<T> = (xs :: Vec<T>, j: usize, lft: T, rgt: T) Res<(), AllocError>
```

#### Imports and re-exports

```zen
Vec        = std.collections.collections_vec

Range      = std.core.range

AllocError = std.mem
```

### `src/std/collections/collections_vararg.zen`

4 declarations (types: 1, implementations: 1, imports and re-exports: 2).

#### Types

```zen
vararg*<T> = {
    data: Ptr<T>,
    len*: usize,
    get* = (self: @Self, i: usize) Res<T>
    index* = (self: @Self, i: usize) T
    is_empty* = (self: @Self) bool
}
```

#### Implementations

```zen
vararg.impl(Range<T>, {
    start: 0,
    end: self.len,
    at ::= (self: @Self, index: usize) Res<T>
})
```

#### Imports and re-exports

```zen
Ptr = std.mem

Range = std.core.range
```

### `src/std/collections/collections_vec.zen`

5 declarations (types: 1, implementations: 1, functions: 1, imports and re-exports: 2).

#### Types

```zen
Vec*<T> = {
    data :: Ptr<T> = null_ptr<T>(),
    len* :: usize = 0,
    capacity :: usize = 0,
    alloc: Alloc,
    add* = (self :: @Self, value: T) Res<(), AllocError>
    get* = (self: @Self, i: usize) Res<T>
    ptr* = (self: @Self) Ptr<T>
    set* = (self :: @Self, i: usize, value: T) Res<()>
    take* = (self :: @Self, i: usize) Res<T>
    clear* = (self :: @Self) ()
    reserve* = (self :: @Self, n: usize) Res<(), AllocError>
    grow_by* = (self :: @Self, n: usize) Res<(), AllocError>
    grow = (self :: @Self) Res<(), AllocError>
    reallocate = (self :: @Self, cap: usize) Res<(), AllocError>
}
```

#### Implementations

```zen
Vec.impl(Range<T>, {
    start: 0,
    end: self.len,
    at ::= (self: @Self, index: usize) Res<T>
})
```

#### Functions

```zen
Vec* = <T>(a: Alloc) Vec<T>
```

#### Imports and re-exports

```zen
Alloc, AllocError, Ptr, null_ptr = std.mem

Range = std.core.range
```

### `src/std/core/bool.zen`

5 declarations (types: 1, implementations: 1, functions: 2, imports and re-exports: 1).

#### Types

```zen
bool* = {}
```

#### Implementations

```zen
bool.impl(Eq, { eq ::= (self: @Self, other: @Self) bool  })
```

#### Functions

```zen
then* = <T>(b: bool, f: () T) Res<T>

ensure* = <E>(b: bool, reason: E) Res<(), E>
```

#### Imports and re-exports

```zen
Eq = std.core.eq
```

### `src/std/core/byte.zen`

32 declarations (functions: 21, constants: 11).

#### Functions

```zen
is_ascii* = (b: u8) bool

is_digit* = (b: u8) bool

is_lower* = (b: u8) bool

is_upper* = (b: u8) bool

is_alpha* = (b: u8) bool

is_alnum* = (b: u8) bool

is_space* = (b: u8) bool

is_ident_start* = (b: u8) bool

is_ident_cont*  = (b: u8) bool

is_hex_digit* = (b: u8) bool

digit_value* = (b: u8) Res<u8>

digit* = (n: u8) u8

digit* = (n: u64) u8

digit* = (n: i64) u8

digit* = (n: usize) u8

hex_value* = (b: u8) Res<u8>

to_lower* = (b: u8) u8

to_upper* = (b: u8) u8

hex_digit* = (nibble: u8) u8

hex_digit* = (nibble: u64) u8

hex_usize* = (b: u8) Res<usize>
```

#### Constants

```zen
DIGIT_ZERO* : u8 = '0'

DIGIT_NINE* : u8 = '9'

LOWER_A*    : u8 = 'a'

LOWER_F*    : u8 = 'f'

LOWER_Z*    : u8 = 'z'

UPPER_A*    : u8 = 'A'

UPPER_F*    : u8 = 'F'

UPPER_Z*    : u8 = 'Z'

CASE_GAP*   : u8 = 32

ASCII_MAX*  : u8 = 127

HEX_BASE*   : u8 = 16
```

### `src/std/core/core.zen`

24 declarations (imports and re-exports: 24).

#### Imports and re-exports

```zen
Res*, Ok*, Err*, None*, ok_or*, value_or*, map_err*, replace_err* = std.core.result

then*, ensure*, bool* = std.core.bool

Drop* = std.core.drop

Scope* = std.core.scope

i8*, i16*, i32*, i64* = std.core.num

u8*, u16*, u32*, u64*, usize* = std.core.num

f32*, f64* = std.core.num

pow2* = std.core.num

ToU16*, ToU32*, ToU64*, ToUsize*,
    ToI16*, ToI32*, ToI64*, ToF64* = std.core.num

is_ascii*, is_digit*, is_lower*, is_upper*, is_alpha*, is_alnum*,
    is_space*, is_ident_start*, is_ident_cont*, is_hex_digit*,
    digit_value*, digit*, hex_value*, hex_usize*,
    to_lower*, to_upper*, hex_digit* = std.core.byte

loop*, find*, filter*, map*, LoopHandle* = std.core.loop

Range* = std.core.range

Eq*, is_in* = std.core.eq

Hash*, Hasher* = std.core.hash

Display* = std.core.display

IoError*, WriteError*, Sink* = std.core.io

Path*, join_path* = std.core.path

Duration* = std.core.time

str*, String* = std.text

Vec*, Map*, Ordered*, vararg* = std.collections

Alloc*, AllocError*, Arena*, Mem*, Ptr*, null_ptr* = std.mem

Env*, ArgError*,
    Console*, Stdin*, Fs*, FsError*,
    Net*, Threads*, Thread*, ThreadError* = std.env

Actor*, Ref*, ActorError*, ActorStartError* = std.actor.actor_core

Context* = std.actor.actor_context
```

### `src/std/core/display.zen`

4 declarations (types: 1, imports and re-exports: 3).

#### Types

```zen
Display* = {
    dump* ::= (self: @Self, out :: Sink) Res<(), WriteError>
    toString* ::= (self: @Self, out :: Sink) Res<(), WriteError>
    toString* = (self: @Self, a: Alloc) Res<String, WriteError>
}
```

#### Imports and re-exports

```zen
Alloc = std.mem

String = std.text

Sink, WriteError = std.core.io
```

### `src/std/core/drop.zen`

1 declarations (types: 1).

#### Types

```zen
Drop* = {
    drop* = (self :: @Self) ()
}
```

### `src/std/core/eq.zen`

2 declarations (types: 1, functions: 1).

#### Types

```zen
Eq* = {
    eq* = (self: @Self, other: @Self) bool
    ne* = (self: @Self, other: @Self) bool
}
```

#### Functions

```zen
is_in* = <T: Eq, R: Range<T>>(x: T, xs: R) bool
```

### `src/std/core/hash.zen`

4 declarations (types: 2, constants: 2).

#### Types

```zen
Hasher* = {
    state :: u64 = HASH_SEED,
    write_u8* = (self :: @Self, byte: u8) ()
    write_u64* = (self :: @Self, value: u64) ()
    finish* = (self: @Self) u64
}

Hash* = {
    hash* = (self: @Self, hasher :: Hasher) u64
}
```

#### Constants

```zen
HASH_SEED: u64 = 5381

HASH_MULT: u64 = 1000003
```

### `src/std/core/io.zen`

3 declarations (types: 1, enums: 2).

#### Types

```zen
Sink* = {
    write* = (self :: @Self, bytes: str) Res<(), WriteError>
    write_byte* = (self :: @Self, b: u8) Res<(), WriteError>
}
```

#### Enums

```zen
IoError* = Closed
          | Full
          | Invalid
          | Interrupted

WriteError* = IoError | AllocError
```

### `src/std/core/loop/loop.zen`

4 declarations (imports and re-exports: 4).

#### Imports and re-exports

```zen
Range*               = std.core.range

LoopHandle*          = std.core.loop.loop_handle

loop*                = std.core.loop.loop_iter

find*, filter*, map* = std.core.loop.loop_find
```

### `src/std/core/loop/loop_find.zen`

10 declarations (functions: 3, imports and re-exports: 7).

#### Functions

```zen
find*<R: Range<T>, T> = (range: R, pred: (value: T) bool) Res<T>

filter*<R: Range<T>, T> = (range: R, alloc: Alloc, pred: (
    value : T
) bool) Res<Vec<T>>

map*<R: Range<T>, T, U> = (range: R, alloc: Alloc, body: (
    h     : LoopHandle,
    index : usize,
    value : T
) U) Res<Vec<U>>
```

#### Imports and re-exports

```zen
Res, Ok, None = std.core.result

then          = std.core.bool

Alloc         = std.mem

Vec           = std.collections

Range         = std.core.range

LoopHandle    = std.core.loop.loop_handle

loop          = std.core.loop.loop_iter
```

### `src/std/core/loop/loop_handle.zen`

1 declarations (types: 1).

#### Types

```zen
LoopHandle* = {
    next* = (self: @Self) ()
    break* = (self: @Self) ()
    break*<T> = (self: @Self, value: T) ()
}
```

### `src/std/core/loop/loop_iter.zen`

10 declarations (functions: 7, imports and re-exports: 3).

#### Functions

```zen
loop*<T> = (body: (h: LoopHandle) ()) Res<T>

loop*<T> = (body: (h: LoopHandle, index: usize) ()) Res<T>

loop*<T> = (cond: () bool, body: (h: LoopHandle) ()) Res<T>

loop*<T> = (cond: bool, body: (h: LoopHandle) ()) Res<T>

loop*<R: Range<T>, T> = (range: R, body: (
    h     : LoopHandle,
    index : usize,
    value : T
) ()) Res<T>

loop*<R: Range<T>, T> = (range: R, body: (h: LoopHandle, value: T) ()) Res<T>

loop*<R: Range<T>, T, A> = (range: R, init: A, body: (
    h     : LoopHandle,
    index : usize,
    value : T,
    acc   : A
) A) Res<A>
```

#### Imports and re-exports

```zen
LoopHandle = std.core.loop.loop_handle

Range      = std.core.range

Res        = std.core.result
```

### `src/std/core/num.zen`

77 declarations (types: 19, implementations: 31, functions: 25, imports and re-exports: 2).

#### Types

```zen
i8* = {
    MIN*: i8 = -128,
    MAX*: i8 = 127,
    BITS*: usize = 8,
}

i16* = {
    MIN*: i16 = -32768,
    MAX*: i16 = 32767,
    BITS*: usize = 16,
}

i32* = {
    MIN*: i32 = -2147483648,
    MAX*: i32 = 2147483647,
    BITS*: usize = 32,
}

i64* = {
    MIN*: i64 = -9223372036854775808,
    MAX*: i64 = 9223372036854775807,
    BITS*: usize = 64,
}

u8* = {
    MIN*: u8 = 0,
    MAX*: u8 = 255,
    BITS*: usize = 8,
}

u16* = {
    MIN*: u16 = 0,
    MAX*: u16 = 65535,
    BITS*: usize = 16,
}

u32* = {
    MIN*: u32 = 0,
    MAX*: u32 = 4294967295,
    BITS*: usize = 32,
}

u64* = {
    MIN*: u64 = 0,
    MAX*: u64 = 18446744073709551615,
    BITS*: usize = 64,
}

usize* = {
    MIN*: usize = 0,
    MAX*: usize = 18446744073709551615,
    BITS*: usize = 64,
}

f32* = {
    MIN*: f32 = -340282346638528859811704183484516925440.0,
    MAX*: f32 = 340282346638528859811704183484516925440.0,
    BITS*: usize = 32,
}

f64* = {
    MIN*: f64 = -179769313486231570814527423731704356798070567525844996598917476803157260780028538760589558632766878171540458953514382464234321326889464182768467546703537516986049910576551282076245490090389328944075868508455133942304583236903222948165808559332123348274797826204144723168738177180919299881250404026184124858368.0,
    MAX*: f64 = 179769313486231570814527423731704356798070567525844996598917476803157260780028538760589558632766878171540458953514382464234321326889464182768467546703537516986049910576551282076245490090389328944075868508455133942304583236903222948165808559332123348274797826204144723168738177180919299881250404026184124858368.0,
    BITS*: usize = 64,
}

ToU16* = { widen_u16* = (self: @Self) u16 }

ToU32* = { widen_u32* = (self: @Self) u32 }

ToU64* = { widen_u64* = (self: @Self) u64 }

ToUsize* = { widen_usize* = (self: @Self) usize }

ToI16* = { widen_i16* = (self: @Self) i16 }

ToI32* = { widen_i32* = (self: @Self) i32 }

ToI64* = { widen_i64* = (self: @Self) i64 }

ToF64* = { widen_f64* = (self: @Self) f64 }
```

#### Implementations

```zen
u8.impl(ToU16, { widen_u16 = to_u16 })

u8.impl(ToU32, { widen_u32 = to_u32 })

u8.impl(ToU64, { widen_u64 = to_u64 })

u8.impl(ToI32, { widen_i32 = to_i32 })

u8.impl(ToI64, { widen_i64 = to_i64 })

u16.impl(ToU32, { widen_u32 = to_u32 })

u16.impl(ToU64, { widen_u64 = to_u64 })

u16.impl(ToI64, { widen_i64 = to_i64 })

u32.impl(ToU64, { widen_u64 = to_u64 })

u32.impl(ToUsize, { widen_usize = to_usize })

u32.impl(ToI64, { widen_i64 = to_i64 })

usize.impl(ToU64, { widen_u64 = to_u64 })

u8.impl(ToUsize, { widen_usize = to_usize })

u16.impl(ToUsize, { widen_usize = to_usize })

i8.impl(ToI16, { widen_i16 = to_i16 })

i8.impl(ToI32, { widen_i32 = to_i32 })

i8.impl(ToI64, { widen_i64 = to_i64 })

i16.impl(ToI32, { widen_i32 = to_i32 })

i16.impl(ToI64, { widen_i64 = to_i64 })

i32.impl(ToI64, { widen_i64 = to_i64 })

i32.impl(ToF64, { widen_f64 = to_f64 })

f32.impl(ToF64, { widen_f64 = to_f64 })

i8.impl(Eq, { eq ::= (self: @Self, other: @Self) bool  })

i16.impl(Eq, { eq ::= (self: @Self, other: @Self) bool  })

i32.impl(Eq, { eq ::= (self: @Self, other: @Self) bool  })

i64.impl(Eq, { eq ::= (self: @Self, other: @Self) bool  })

u8.impl(Eq, { eq ::= (self: @Self, other: @Self) bool  })

u16.impl(Eq, { eq ::= (self: @Self, other: @Self) bool  })

u32.impl(Eq, { eq ::= (self: @Self, other: @Self) bool  })

u64.impl(Eq, { eq ::= (self: @Self, other: @Self) bool  })

usize.impl(Eq, { eq ::= (self: @Self, other: @Self) bool  })
```

#### Functions

```zen
to_u16* = (self: u8) u16

to_u32* = (self: u8) u32

to_u64* = (self: u8) u64

to_u32* = (self: u16) u32

to_u64* = (self: u16) u64

to_u64* = (self: u32) u64

to_usize* = (self: u32) usize

to_u64* = (self: usize) u64

to_usize* = (self: u8) usize

to_usize* = (self: u16) usize

to_i16* = (self: i8) i16

to_i32* = (self: i8) i32

to_i64* = (self: i8) i64

to_i32* = (self: i16) i32

to_i64* = (self: i16) i64

to_i64* = (self: i32) i64

to_i32* = (self: u8) i32

to_i64* = (self: u8) i64

to_i64* = (self: u16) i64

to_i64* = (self: u32) i64

to_f64* = (self: i32) f64

to_f64* = (self: f32) f64

to_u8* = (self: usize) Res<u8>

to_u8* = (self: u32) Res<u8>

pow2* = (self: usize) usize
```

#### Imports and re-exports

```zen
Eq = std.core.eq

Res, Ok, None = std.core.result
```

### `src/std/core/path.zen`

5 declarations (types: 1, functions: 4).

#### Types

```zen
Path* = {
    text*: str,
    parent* = (self: @Self) Res<Path>
    name* = (self: @Self) str
    ext* = (self: @Self) Res<str>
}
```

#### Functions

```zen
Path* = (text: str) Path

Path* = (a: Alloc, fmt: str, args: ...) Res<Path, AllocError>

join_path* = (a: Alloc, dir: str, file: str) Res<String, AllocError>

join* = (a: Alloc, base: Path, rest: str) Res<Path, AllocError>
```

### `src/std/core/range.zen`

2 declarations (types: 1, imports and re-exports: 1).

#### Types

```zen
Range*<T> = {
    start*: usize,
    end*: usize,
    at* ::= (self: @Self, index: usize) Res<T>
}
```

#### Imports and re-exports

```zen
Res = std.core.result
```

### `src/std/core/result.zen`

6 declarations (enums: 2, functions: 4).

#### Enums

```zen
Res*<T> = Ok(T) | None

Res*<T, E> = Ok(T) | Err(E)
```

#### Functions

```zen
ok_or* = <T, E>(r: Res<T>, reason: E) Res<T, E>

value_or* = <T>(r: Res<T>, fallback: T) T

map_err* = <T, E, F>(r: Res<T, E>, f: (error: E) F) Res<T, F>

replace_err* = <T, E, F>(r: Res<T, E>, reason: F) Res<T, F>
```

### `src/std/core/scope.zen`

1 declarations (types: 1).

#### Types

```zen
Scope* = {
    defer* = (self: @Self, f: () ()) ()
}
```

### `src/std/core/time.zen`

22 declarations (types: 1, enums: 1, functions: 15, constants: 4, imports and re-exports: 1).

#### Types

```zen
Duration* = {
    ns*: u64,
}
```

#### Enums

```zen
Unit* = Nano | Micro | Milli | Second | Minute
```

#### Functions

```zen
nanos*   = (n: u64) Duration

micros*  = (n: u64) Duration

millis*  = (n: u64) Duration

seconds* = (n: u64) Duration

minutes* = (n: u64) Duration

nanos_of*   = (self: Duration) u64

micros_of*  = (self: Duration) u64

millis_of*  = (self: Duration) u64

seconds_of* = (self: Duration) u64

minutes_of* = (self: Duration) u64

unit_of* = (self: Duration) Unit

count_in* = (self: Duration, u: Unit) u64

suffix* = (u: Unit) str

add* = (self: Duration, other: Duration) Duration

sub* = (self: Duration, other: Duration) Res<Duration>
```

#### Constants

```zen
NS_PER_MICRO*  : u64 = 1000

NS_PER_MILLI*  : u64 = 1000000

NS_PER_SECOND* : u64 = 1000000000

NS_PER_MINUTE* : u64 = 60000000000
```

#### Imports and re-exports

```zen
Res = std.core.result
```

### `src/std/env/env.zen`

20 declarations (types: 9, enums: 3, implementations: 1, functions: 1, imports and re-exports: 6).

#### Types

```zen
Console* = {
    println* = (self: @Self, fmt: str, args: ...) Res<(), IoError>
    errorln* = (self: @Self, fmt: str, args: ...) Res<(), IoError>
}

Stdin* = {
    read* = (self: @Self, buf :: Vec<u8>, n: usize) Res<usize, IoError>
}

Fs* = {
    read* = (self: @Self, a: Alloc, path: str) Res<String, FsError>
    exists* = (self: @Self, path: str) bool
    is_dir* = (self: @Self, path: str) bool
    write* = (self: @Self, path: str, bytes: str) Res<(), FsError>
    remove* = (self: @Self, path: str) Res<bool, FsError>
    lock* = (self: @Self, path: str) Res<Lock, FsError>
}

Lock* = {
    fd: i32,
    unlock* = (self :: @Self) ()
}

Net* = {
    http* = (self: @Self, a: Alloc) HttpClient
}

Thread* = {
    id: u64,
    join* = <T>(self: @Self) Res<T, ThreadError>
}

Threads* = {
    spawn* = <T>(self: @Self, a: Alloc, body: () Res<T, ThreadError>) Res<Thread, ThreadError>
    sleep* = (self: @Self, ms: u64) ()
}

Clock* = {
    since_start* = (self: @Self) Duration
    unix*        = (self: @Self) Duration
}

Env* = {
    argv*: Vec<str>,
    out*: Console,
    in*: Stdin,
    mem*: Mem,
    fs*: Fs,
    net*: Net,
    proc*: Process,
    threads*: Threads,
    clock*: Clock,
    var* = (self: @Self, name: str) Res<str>
    args* = <T>(self: @Self) Res<T, ArgError>
    spawn* = <A: Actor>(self: @Self, actor: A) Res<Ref<A>, ActorStartError>
}
```

#### Enums

```zen
ArgError* = Missing(str) | Parse(str)

FsError* = NotFound
         | Denied
         | IsDir
         | Exists
         | Failed
         | OutOfMemory

ThreadError* = SpawnFailed | Panicked
```

#### Implementations

```zen
Lock.impl(Drop, {
    drop = (self :: @Self) ()
})
```

#### Functions

```zen
fs_message* = (error: FsError) str
```

#### Imports and re-exports

```zen
Alloc, Mem = std.mem

Vec = std.collections

str, String = std.text

HttpClient = std.net.http

Actor, Ref, ActorStartError = std.actor.actor_core

ProcError, ProcOutput, Process = std.proc
```

### `src/std/json/json.zen`

4 declarations (imports and re-exports: 4).

#### Imports and re-exports

```zen
JsonId*, Run*, Pair*, Json*, Jsons*,
    write_text*, written*, Nest*, obj*, arr* = std.json.json_write

JsonFault*, MAX_NESTING*, Reader*, read*,
    fine* = std.json.json_read

JsonEvent*, Decoder* = std.json.json_stream

to_json* = std.json.json_meta
```

### `src/std/json/json_meta.zen`

19 declarations (functions: 16, imports and re-exports: 3).

#### Functions

```zen
to_json* = <T>(self: T, a: Alloc) Res<String, AllocError>

write_raw* = (out :: String, value: str) Res<(), AllocError>

write_str* = (out :: String, value: str) Res<(), AllocError>

write_string* = (out :: String, value: String) Res<(), AllocError>

write_bool* = (out :: String, value: bool) Res<(), AllocError>

write_i8* = (out :: String, value: i8) Res<(), AllocError>

write_i16* = (out :: String, value: i16) Res<(), AllocError>

write_i32* = (out :: String, value: i32) Res<(), AllocError>

write_i64* = (out :: String, value: i64) Res<(), AllocError>

write_u8* = (out :: String, value: u8) Res<(), AllocError>

write_u16* = (out :: String, value: u16) Res<(), AllocError>

write_u32* = (out :: String, value: u32) Res<(), AllocError>

write_u64* = (out :: String, value: u64) Res<(), AllocError>

write_usize* = (out :: String, value: usize) Res<(), AllocError>

write_f32* = (out :: String, value: f32) Res<(), AllocError>

write_f64* = (out :: String, value: f64) Res<(), AllocError>
```

#### Imports and re-exports

```zen
Alloc, AllocError = std.mem

str, String = std.text

write_text = std.json.json_write
```

### `src/std/json/json_read.zen`

23 declarations (types: 1, enums: 1, functions: 5, constants: 11, imports and re-exports: 5).

#### Types

```zen
Reader* = {
    text: str,
    a: Alloc,
    at :: usize,
    depth :: usize,
    value* = (self :: @Self, tree :: Jsons) Res<JsonId, JsonFault>
    atom = (self :: @Self, tree :: Jsons, b: u8) Res<JsonId, JsonFault>
    word = (self :: @Self, tree :: Jsons, spelling: str, v: Json)
           Res<JsonId, JsonFault>
    number = (self :: @Self, tree :: Jsons) Res<JsonId, JsonFault>
    number_text = (self :: @Self) Res<str, JsonFault>
    integer_part = (self :: @Self) Res<(), JsonFault>
    fraction_part = (self :: @Self) Res<(), JsonFault>
    exponent_part = (self :: @Self) Res<(), JsonFault>
    at_least_one_digit = (self :: @Self) Res<(), JsonFault>
    digits = (self :: @Self) ()
    digit_here = (self: @Self) bool
    array = (self :: @Self, tree :: Jsons) Res<JsonId, JsonFault>
    object = (self :: @Self, tree :: Jsons) Res<JsonId, JsonFault>
    member = (self :: @Self, tree :: Jsons) Res<Pair, JsonFault>
    close = (self :: @Self, b: u8) Res<(), JsonFault>
    string = (self :: @Self, tree :: Jsons) Res<JsonId, JsonFault>
    text_at = (self :: @Self) Res<str, JsonFault>
    raw_or_decoded = (self :: @Self) Res<str, JsonFault>
    decoded = (self :: @Self, from: usize) Res<str, JsonFault>
    copy_one = (self :: @Self, b: u8, out :: String) Res<(), JsonFault>
    escape = (self :: @Self, out :: String) Res<(), JsonFault>
    unicode = (self :: @Self, out :: String) Res<(), JsonFault>
    low_half = (self :: @Self, hi: u32, out :: String) Res<(), JsonFault>
    four_hex = (self :: @Self) Res<u32, JsonFault>
    peek = (self: @Self) Res<u8, JsonFault>
    here = (self: @Self, b: u8) bool
    byte_if = (self :: @Self, b: u8) bool
    spaces = (self :: @Self) ()
    space_here = (self: @Self) bool
    down = (self :: @Self) Res<(), JsonFault>
    up = (self :: @Self) ()
}
```

#### Enums

```zen
JsonFault* = Unexpected(usize)
           | Truncated(usize)
           | BadEscape(usize)
           | BadNumber(usize)
           | TooDeep(usize)
           | Trailing(usize)
           | NoMemory
```

#### Functions

```zen
read* = (a: Alloc, tree :: Jsons, text: str) Res<JsonId, JsonFault>

decode_text_token* = (a: Alloc, raw: str) Res<String, JsonFault>

number_token* = (a: Alloc, raw: str) Res<String, JsonFault>

simple = (b: u8) Res<u8>

fine* = () Res<(), JsonFault>
```

#### Constants

```zen
MAX_NESTING*: usize = 64

BACKSPACE*: u8 = 8

FORM_FEED*: u8 = 12

ZERO_U32*: u32 = 0

HEX_BASE_U32*: u32 = 16

SURROGATE_HI_MIN*: u32 = 55296

SURROGATE_HI_MAX*: u32 = 56319

SURROGATE_LO_MIN*: u32 = 56320

SURROGATE_LO_MAX*: u32 = 57343

SURROGATE_SPAN*: u32 = 1024

ASTRAL_BASE*: u32 = 65536
```

#### Imports and re-exports

```zen
str, String, push_utf8 = std.text

Vec = std.collections

Alloc, AllocError = std.mem

Range = std.core

Jsons, Json, JsonId, Pair = std.json.json_write
```

### `src/std/json/json_stream.zen`

20 declarations (types: 2, enums: 3, functions: 10, imports and re-exports: 5).

#### Types

```zen
Frame = { phase: Phase }

Decoder* = {
    a: Alloc,
    frames :: Vec<Frame>,
    token :: String,
    mode :: Mode,
    key :: bool,
    slash :: bool,
    hex_left :: usize,
    token_at :: usize,
    at :: usize,
    root_done :: bool,
    finished :: bool,
    feed* = <B: Range<u8>>(
        self   :: @Self,
        bytes  : B,
        events :: Vec<JsonEvent>
    ) Res<(), JsonFault>
    feed_open = <B: Range<u8>>(
        self   :: @Self,
        bytes  : B,
        events :: Vec<JsonEvent>
    ) Res<(), JsonFault>
    feed_byte* = (
        self   :: @Self,
        byte   : u8,
        events :: Vec<JsonEvent>
    ) Res<(), JsonFault>
    step = (
        self   :: @Self,
        b      : u8,
        events :: Vec<JsonEvent>
    ) Res<bool, JsonFault>
    ready = (
        self   :: @Self,
        b      : u8,
        events :: Vec<JsonEvent>
    ) Res<bool, JsonFault>
    root_ready = (
        self   :: @Self,
        b      : u8,
        events :: Vec<JsonEvent>
    ) Res<bool, JsonFault>
    frame_ready = (
        self   :: @Self,
        b      : u8,
        events :: Vec<JsonEvent>
    ) Res<bool, JsonFault>
    start_key = (self :: @Self, b: u8) Res<bool, JsonFault>
    start_value = (
        self   :: @Self,
        b      : u8,
        events :: Vec<JsonEvent>
    ) Res<bool, JsonFault>
    open_object = (
        self   :: @Self,
        events :: Vec<JsonEvent>
    ) Res<bool, JsonFault>
    open_array = (
        self   :: @Self,
        events :: Vec<JsonEvent>
    ) Res<bool, JsonFault>
    open = (self :: @Self, frame: Frame) Res<(), JsonFault>
    close_object = (
        self   :: @Self,
        events :: Vec<JsonEvent>
    ) Res<bool, JsonFault>
    close_array = (
        self   :: @Self,
        events :: Vec<JsonEvent>
    ) Res<bool, JsonFault>
    begin_quoted = (self :: @Self, key: bool) Res<bool, JsonFault>
    quoted = (
        self   :: @Self,
        b      : u8,
        events :: Vec<JsonEvent>
    ) Res<bool, JsonFault>
    quoted_plain = (
        self   :: @Self,
        b      : u8,
        events :: Vec<JsonEvent>
    ) Res<bool, JsonFault>
    finish_quoted = (
        self   :: @Self,
        events :: Vec<JsonEvent>
    ) Res<bool, JsonFault>
    begin_atom = (self :: @Self, b: u8) Res<bool, JsonFault>
    atom_byte = (
        self   :: @Self,
        b      : u8,
        events :: Vec<JsonEvent>
    ) Res<bool, JsonFault>
    finish_atom = (
        self   :: @Self,
        events :: Vec<JsonEvent>
    ) Res<(), JsonFault>
    value_done = (self :: @Self) ()
    phase = (self: @Self) Phase
    set_phase = (self :: @Self, phase: Phase) ()
    finish* = (
        self   :: @Self,
        events :: Vec<JsonEvent>
    ) Res<(), JsonFault>
}
```

#### Enums

```zen
JsonEvent* = ObjectStart
    | ObjectEnd
    | ArrayStart
    | ArrayEnd
    | Key(String)
    | Text(String)
    | Number(String)
    | Bool(bool)
    | Null

Mode = Ready | Quoted | Atom

Phase = ObjectKeyOrEnd
    | ObjectKey
    | ObjectColon
    | ObjectValue
    | ObjectCommaOrEnd
    | ArrayValueOrEnd
    | ArrayValue
    | ArrayCommaOrEnd
```

#### Functions

```zen
Decoder* = (a: Alloc) Res<Decoder, JsonFault>

json_space = (b: u8) bool

atom_start = (b: u8) bool

atom_end = (b: u8) bool

simple_escape = (b: u8) bool

atom_event = (a: Alloc, raw: str, base: usize) Res<JsonEvent, JsonFault>

keyword_start = (raw: str) bool

decoded_text = (a: Alloc, raw: str, base: usize) Res<String, JsonFault>

checked_number = (a: Alloc, raw: str, base: usize) Res<String, JsonFault>

shift = (f: JsonFault, base: usize) JsonFault
```

#### Imports and re-exports

```zen
str, String = std.text

Vec = std.collections

Alloc = std.mem

Range = std.core

JsonFault, decode_text_token, number_token,
    MAX_NESTING = std.json.json_read
```

### `src/std/json/json_write.zen`

19 declarations (types: 5, enums: 1, functions: 7, constants: 1, imports and re-exports: 5).

#### Types

```zen
JsonId* = { index*: usize }

Run* = {
    at*: usize,
    len*: usize,
}

Pair* = {
    key*: str,
    value*: JsonId,
}

Jsons* = {
    nodes :: Vec<Json>,
    items :: Vec<JsonId>,
    pairs :: Vec<Pair>,
    at* = (self: @Self, id: JsonId) Json
    add* = (self :: @Self, v: Json) Res<JsonId, AllocError>
    add_items* = (self :: @Self, ids: Vec<JsonId>) Res<Run, AllocError>
    add_pairs* = (self :: @Self, ps: Vec<Pair>) Res<Run, AllocError>
    field* = (self: @Self, id: JsonId, name: str) Res<JsonId>
    scan = (self: @Self, run: Run, name: str) Res<JsonId>
    item* = (self: @Self, id: JsonId, i: usize) Res<JsonId>
    text* = (self: @Self, id: JsonId) Res<str>
    whole* = (self: @Self, id: JsonId) Res<usize>
    write* = (self: @Self, id: JsonId, out :: String) Res<(), AllocError>
    write_items = (self: @Self, run: Run, out :: String) Res<(), AllocError>
    write_pairs = (self: @Self, run: Run, out :: String) Res<(), AllocError>
}

Nest* = {
    said :: bool,
    ends: u8,
    next* = (self :: @Self, out :: String) Res<(), AllocError>
    key* = (self :: @Self, name: str, out :: String) Res<(), AllocError>
    text* = (self :: @Self, name: str, v: str, out :: String)
            Res<(), AllocError>
    close* = (self: @Self, out :: String) Res<(), AllocError>
}
```

#### Enums

```zen
Json* = Null
      | Bool(bool)
      | Num(str)
      | Text(str)
      | Arr(Run)
      | Obj(Run)
```

#### Functions

```zen
Jsons* = (a: Alloc) Jsons

written* = () Res<(), AllocError>

obj* = (out :: String) Res<Nest, AllocError>

arr* = (out :: String) Res<Nest, AllocError>

write_text* = (s: str, out :: String) Res<(), AllocError>

escaped = (b: u8, out :: String) Res<(), AllocError>

hex_escape = (b: u8, out :: String) Res<(), AllocError>
```

#### Constants

```zen
SPACE*: u8 = ' '
```

#### Imports and re-exports

```zen
str, String = std.text

Vec = std.collections

Alloc, AllocError = std.mem

Range = std.core

hex_digit, HEX_BASE = std.core.byte
```

### `src/std/lex/lex.zen`

10 declarations (imports and re-exports: 10).

#### Imports and re-exports

```zen
Pos*, Span*, TokenKind*, Token*, Source*  = std.lex.lex_token

text_of*, kind_name*                      = std.lex.lex_token

LexFault*, Diag*, message*                = std.lex.lex_diag

ByteClass*, class_of*, is_escape*         = std.lex.lex_byte

BOM_FIRST*, BOM_SECOND*, BOM_THIRD*       = std.text.text_utf8

Cursor*, cursor_at*                       = std.lex.lex_cursor

punct_of*, punct_kind*                    = std.lex.lex_punct

Lexer*, Lexed*                            = std.lex.lex_state

Digits*, digits_of*                       = std.lex.lex_literal

scan*, Keyword*, KEYWORD_COUNT*, keyword_at*, is_keyword*, is_zen_name*
                                          = std.lex.lex_scan
```

### `src/std/lex/lex_byte.zen`

4 declarations (enums: 1, functions: 3).

#### Enums

```zen
ByteClass* =
      Space
    | Slash
    | Quote
    | Apos
    | Digit
    | Letter
    | At
    | Other
```

#### Functions

```zen
is_escape* = (b: u8) bool

class_of* = (b: u8) ByteClass

opener_class = (b: u8) ByteClass
```

### `src/std/lex/lex_cursor.zen`

5 declarations (types: 1, functions: 1, imports and re-exports: 3).

#### Types

```zen
Cursor* = {
    src: str,
    offset :: usize,
    line :: usize,
    col :: usize,
    is_done* = (self: @Self) bool
    peek* = (self: @Self) Res<u8>
    peek* = (self: @Self, ahead: usize) Res<u8>
    at_byte* = (self: @Self, b: u8) bool
    at_byte* = (self: @Self, ahead: usize, b: u8) bool
    pos* = (self: @Self) Pos
    bump* = (self :: @Self) ()
    bump_while* = (self :: @Self, keep: (b: u8) bool) ()
    at_bom* = (self: @Self) bool
    step = (self :: @Self) ()
}
```

#### Functions

```zen
cursor_at* = (src: str) Cursor
```

#### Imports and re-exports

```zen
Pos = std.lex.lex_token

BOM_FIRST, BOM_SECOND, BOM_THIRD = std.text.text_utf8

str = std.text
```

### `src/std/lex/lex_diag.zen`

5 declarations (types: 1, enums: 1, functions: 1, imports and re-exports: 2).

#### Types

```zen
Diag* = {
    file*: str,
    fault*: LexFault,
    span*: Span,
}
```

#### Enums

```zen
LexFault* =
      UnterminatedString
    | StringSpansLine
    | UnterminatedChar
    | CharSpansLine
    | EmptyChar
    | CharTooLong
    | UnknownEscape
    | UnterminatedEscape
    | UnterminatedComment
    | LeadingZero
    | FloatNeedsDigit
    | SuffixOnNumber
    | IntegerOutOfRange
    | UnknownAtName
    | MisplacedBom
    | StrayByte
```

#### Functions

```zen
message* = (fault: LexFault) str
```

#### Imports and re-exports

```zen
Span = std.lex.lex_token

str = std.text
```

### `src/std/lex/lex_literal.zen`

20 declarations (types: 1, functions: 13, imports and re-exports: 6).

#### Types

```zen
Digits* = {
    value*: u64,
    overflow*: bool,
}
```

#### Functions

```zen
string* = (lx :: Lexer) Res<(), AllocError>

character* = (lx :: Lexer) Res<(), AllocError>

close_char = (lx :: Lexer, from: Pos) Res<(), AllocError>

overlong_char = (lx :: Lexer, from: Pos) Res<(), AllocError>

escape* = (lx :: Lexer) Res<bool, AllocError>

number* = (lx :: Lexer) Res<(), AllocError>

fraction = (lx :: Lexer) Res<bool, AllocError>

after_dot = (lx :: Lexer) Res<bool, AllocError>

suffix = (lx :: Lexer) Res<(), AllocError>

emit_int = (lx :: Lexer, whole: str, from: Pos) Res<(), AllocError>

has_leading_zero = (whole: str) bool

digits_of* = (s: str) Digits

add_digit = (acc: Digits, b: u8) Digits
```

#### Imports and re-exports

```zen
Lexer = std.lex.lex_state

Pos, TokenKind = std.lex.lex_token

LexFault = std.lex.lex_diag

is_escape = std.lex.lex_byte

AllocError = std.mem

str = std.text
```

### `src/std/lex/lex_punct.zen`

9 declarations (functions: 7, imports and re-exports: 2).

#### Functions

```zen
punct_of* = (b: u8) Res<TokenKind>

punct_kind* = (cur :: Cursor, b: u8, single: TokenKind) TokenKind

solo* = (cur :: Cursor, kind: TokenKind) TokenKind

pair* = (
    cur    :: Cursor,
    second : u8,
    both   : TokenKind,
    single : TokenKind
) TokenKind

dot_kind* = (cur :: Cursor) TokenKind

colon_kind* = (cur :: Cursor) TokenKind

equals_kind* = (cur :: Cursor) TokenKind
```

#### Imports and re-exports

```zen
TokenKind = std.lex.lex_token

Cursor = std.lex.lex_cursor
```

### `src/std/lex/lex_scan.zen`

29 declarations (types: 1, functions: 19, constants: 1, imports and re-exports: 8).

#### Types

```zen
Keyword* = { text*: str, kind*: TokenKind }
```

#### Functions

```zen
scan* = (alloc: Alloc, source: Source) Res<Lexed, AllocError>

strip_bom = (lx :: Lexer) ()

step = (lx :: Lexer) Res<(), AllocError>

dispatch = (lx :: Lexer, b: u8) Res<(), AllocError>

skip = (lx :: Lexer) Res<(), AllocError>

slash = (lx :: Lexer) Res<(), AllocError>

line_comment = (lx :: Lexer) Res<(), AllocError>

block_comment = (lx :: Lexer) Res<(), AllocError>

name = (lx :: Lexer) Res<(), AllocError>

keyword_at* = (i: usize) Res<Keyword>

keyword_of = (word: str) Res<Keyword>

word_kind = (word: str) TokenKind

is_keyword* = (word: str) bool

is_zen_name* = (word: str) bool

at_name = (lx :: Lexer) Res<(), AllocError>

at_kind = (word: str) Res<TokenKind>

punctuation = (lx :: Lexer, b: u8) Res<(), AllocError>

stray = (lx :: Lexer) Res<(), AllocError>

begins_no_token = (b: u8) bool
```

#### Constants

```zen
KEYWORD_COUNT*: usize = 3
```

#### Imports and re-exports

```zen
Lexer, Lexed = std.lex.lex_state

TokenKind, Source = std.lex.lex_token

LexFault = std.lex.lex_diag

class_of = std.lex.lex_byte

punct_of, punct_kind = std.lex.lex_punct

string, character, number = std.lex.lex_literal

Alloc, AllocError = std.mem

str = std.text
```

### `src/std/lex/lex_state.zen`

8 declarations (types: 2, functions: 1, imports and re-exports: 5).

#### Types

```zen
Lexer* = {
    source: Source,
    cur* :: Cursor,
    tokens* :: Vec<Token>,
    diags* :: Vec<Diag>,
    emit* = (self :: @Self, kind: TokenKind, from: Pos) Res<(), AllocError>
    report* = (self :: @Self, fault: LexFault, from: Pos) Res<(), AllocError>
    span_from* = (self: @Self, from: Pos) Span
    since* = (self: @Self, from: Pos) str
}

Lexed* = {
    source*: Source,
    tokens*: Vec<Token>,
    diags*: Vec<Diag>,
    is_clean* = (self: @Self) bool
}
```

#### Functions

```zen
Lexer* = (alloc: Alloc, source: Source) Lexer
```

#### Imports and re-exports

```zen
Pos, Span, Token, TokenKind, Source = std.lex.lex_token

Diag, LexFault = std.lex.lex_diag

Cursor, cursor_at = std.lex.lex_cursor

Alloc, AllocError = std.mem

Vec = std.collections
```

### `src/std/lex/lex_token.zen`

10 declarations (types: 4, enums: 1, implementations: 2, functions: 2, imports and re-exports: 1).

#### Types

```zen
Pos* = {
    offset*: usize,
    line*: usize,
    col*: usize,
}

Span* = {
    start*: Pos,
    end*: Pos,
}

Source* = {
    file*: str,
    text*: str,
}

Token* = {
    kind*: TokenKind,
    span*: Span,
}
```

#### Enums

```zen
TokenKind* =
      Ident
    | Int(u64)
    | Float
    | Str
    | Char
    | True | False
    | Consume
    | AtSelf | AtMeta | AtScope
    | LineComment | BlockComment
    | ParenOpen | ParenClose
    | BracketOpen | BracketClose
    | BraceOpen | BraceClose
    | Comma | Semicolon | Dot | Ellipsis
    | Colon | ColonColon | ColonColonEq
    | Eq | EqEq | Arrow
    | Bang | BangEq
    | Lt | LtEq | Gt | GtEq
    | Amp | AmpAmp
    | Bar | BarBar
    | Plus | PlusWrap
    | Minus | MinusWrap
    | Star | StarWrap
    | Slash | Percent
    | Eof
```

#### Implementations

```zen
Pos.impl(Display, {
    toString ::= (self: @Self, out :: Sink) Res<(), WriteError>
})

TokenKind.impl(Eq, {
    eq ::= (self: @Self, other: @Self) bool
})
```

#### Functions

```zen
text_of* = (source: Source, token: Token) str

kind_name* = (kind: TokenKind) str
```

#### Imports and re-exports

```zen
str = std.text
```

### `src/std/mem/mem.zen`

3 declarations (imports and re-exports: 3).

#### Imports and re-exports

```zen
AllocError*, Alloc* = std.mem.mem_alloc

Arena*, Mem*, Page* = std.mem.mem_arena

Ptr*, null_ptr* = std.mem.mem_ptr
```

### `src/std/mem/mem_alloc.zen`

3 declarations (types: 1, enums: 1, imports and re-exports: 1).

#### Types

```zen
Alloc* = {
    raw* = (self: @Self, size: usize, align: usize) Res<Ptr<u8>, AllocError>
    realloc* = <T>(self: @Self, p: Ptr<T>, count: usize) Res<Ptr<T>, AllocError>
    free* ::= <T>(self: @Self, p: Ptr<T>) ()
    create* ::= <T>(self: @Self) Res<Ptr<T>, AllocError>
}
```

#### Enums

```zen
AllocError* = | OutOfMemory
```

#### Imports and re-exports

```zen
Ptr = std.mem.mem_ptr
```

### `src/std/mem/mem_arena.zen`

12 declarations (types: 4, implementations: 2, functions: 1, constants: 3, imports and re-exports: 2).

#### Types

```zen
Page* = {
    prev: Ptr<Page>,
    base: Ptr<u8>,
    size: usize,
}

ArenaState = {
    mem: Mem,
    head :: Ptr<Page>,
    next :: usize,
}

Arena* = {
    state: Ptr<ArenaState>,
    bump = (self: @Self, s: ArenaState, size: usize, align: usize) Res<Ptr<u8>, AllocError>
    chain = (self: @Self, size: usize, align: usize) Res<Ptr<u8>, AllocError>
    extend_latest = (self: @Self, src: Ptr<u8>, old: usize, want: usize) bool
    extend_nonempty = (self: @Self, src: Ptr<u8>, old: usize, want: usize) bool
}

Mem* = {
    alloc* = (self: @Self) Arena
    page* = (self: @Self, size: usize, prev: Ptr<Page>) Res<Ptr<Page>, AllocError>
    release* = <T>(self: @Self, region: Ptr<T>) ()
}
```

#### Implementations

```zen
Arena.impl(Alloc, {
    raw = (self: @Self, size: usize, align: usize) Res<Ptr<u8>, AllocError>
    realloc = <T>(self: @Self, p: Ptr<T>, count: usize) Res<Ptr<T>, AllocError>
    free = <T>(self: @Self, p: Ptr<T>) ()
})

Arena.impl(Drop, {
    drop = (self :: @Self) ()
})
```

#### Functions

```zen
align_up = (offset: usize, align: usize) usize
```

#### Constants

```zen
PAGE_BYTES: usize = 65536

HEADER_BYTES: usize = usize.BITS / 8

ALIGN_MAX: usize = 16
```

#### Imports and re-exports

```zen
Alloc, AllocError = std.mem.mem_alloc

Ptr = std.mem.mem_ptr
```

### `src/std/mem/mem_ptr.zen`

2 declarations (types: 1, functions: 1).

#### Types

```zen
Ptr*<T> = {
    addr: usize,
    read* = (self: @Self, index: usize) T
    write* = (self: @Self, index: usize, value: T) ()
    offset* = (self: @Self, count: usize) Ptr<T>
    back* = (self: @Self, count: usize) Ptr<T>
    bytes* = (self: @Self, count: usize) usize
    copy_from* = (self: @Self, src: Ptr<T>, count: usize) ()
    to* = <U>(self: @Self) Ptr<U>
    is_null* = (self: @Self) bool
    same* = (self: @Self, other: Ptr<T>) bool
}
```

#### Functions

```zen
null_ptr* = <T>() Ptr<T>
```

### `src/std/net/dns.zen`

6 declarations (types: 1, enums: 1, functions: 1, imports and re-exports: 3).

#### Types

```zen
DnsAddr* = {
    ip*: String,
    is_v6*: bool,
}
```

#### Enums

```zen
DnsError* = NotFound | Failed
```

#### Functions

```zen
resolve* = (a: Alloc, host: str) Res<DnsAddr, DnsError>
```

#### Imports and re-exports

```zen
Alloc = std.mem

Res = std.core

ResolvedAddr, SocketFault, resolve_addr = std.net.socket
```

### `src/std/net/http/http.zen`

11 declarations (types: 1, imports and re-exports: 10).

#### Types

```zen
HttpClient* = {
    post_into* = (self: @Self, a: Alloc, url: str, headers: Vec<str>,
                  body: str, out :: Sink)
                  Res<HttpResponseMeta, HttpError>
    post* = (self: @Self, a: Alloc, url: str, headers: Vec<str>, body: str)
            Res<HttpResponse, HttpError>
}
```

#### Imports and re-exports

```zen
Alloc = std.mem

str, String = std.text

Res = std.core

Sink = std.core.io

Vec = std.collections

HttpError*, HttpResponseMeta*, HttpResponse* = std.net.http.http_types

parse_response_into*, parse_response* = std.net.http.http_decode

http_url, build_request = std.net.http.http_request

Stream, connect_stream, write, close = std.net.http.http_transport

read_response_into = std.net.http.http_decode
```

### `src/std/net/http/http_decode.zen`

21 declarations (types: 2, enums: 1, functions: 9, constants: 2, imports and re-exports: 7).

#### Types

```zen
ChunkDecoder = {
    phase ::             ChunkPhase,
    size ::              usize,
    digits ::            usize,
    left ::              usize,
    trailer_has_bytes :: bool,
    done = (self: @Self) bool
    feed = (self :: @Self, bytes: str, out :: Sink)
           Res<(), HttpError>
    feed_data = (self :: @Self, bytes: str, at: usize, out :: Sink)
                Res<usize, HttpError>
    step = (self :: @Self, b: u8) Res<(), HttpError>
    size_byte = (self :: @Self, b: u8) Res<(), HttpError>
    extension_byte = (self :: @Self, b: u8) Res<(), HttpError>
    size_lf = (self :: @Self, b: u8) Res<(), HttpError>
    data_lf = (self :: @Self, b: u8) Res<(), HttpError>
    trailer_byte = (self :: @Self, b: u8) Res<(), HttpError>
    trailer_lf = (self :: @Self, b: u8) Res<(), HttpError>
    expect = (self :: @Self, got: u8, want: u8, next: ChunkPhase)
             Res<(), HttpError>
    to = (self :: @Self, next: ChunkPhase) Res<(), HttpError>
    finish = (self: @Self) Res<(), HttpError>
}

ResponseBody = {
    a:          Alloc,
    meta:       HttpResponseMeta,
    prefetched: str,
    into = (self: @Self, s: Stream, out :: Sink) Res<(), HttpError>
    chunked = (self: @Self, s: Stream, out :: Sink)
              Res<(), HttpError>
    known_length = (self: @Self, s: Stream, out :: Sink)
                   Res<(), HttpError>
    read_exact = (self: @Self, s: Stream, n: usize, out :: Sink)
                 Res<(), HttpError>
    until_eof = (self: @Self, s: Stream, out :: Sink)
                Res<(), HttpError>
}
```

#### Enums

```zen
ChunkPhase = Size
    | Extension
    | SizeLf
    | Data
    | DataCr
    | DataLf
    | Trailer
    | TrailerLf
    | TrailerEndLf
    | Done
```

#### Functions

```zen
parse_status_line = (line: str) Res<i32, HttpError>

final_coding_is_chunked = (value: str) Res<bool, HttpError>

parse_headers = (block: str) Res<HttpResponseMeta, HttpError>

sink_write = (out :: Sink, bytes: str) Res<(), HttpError>

chunk_decoder = () ChunkDecoder

body_forbidden = (self: HttpResponseMeta) bool

read_response_into* = (s: Stream, a: Alloc, out :: Sink)
                      Res<HttpResponseMeta, HttpError>

parse_response_into* = (raw: str, out :: Sink)
                       Res<HttpResponseMeta, HttpError>

parse_response* = (raw: str, a: Alloc) Res<HttpResponse, HttpError>
```

#### Constants

```zen
HEADER_END: str = "\r\n\r\n"

HTTP_HEAD_MAX: usize = 65536
```

#### Imports and re-exports

```zen
Alloc = std.mem

str, String, str_at = std.text

Res, ok_or = std.core

Sink = std.core.io

Vec = std.collections

HttpError, HttpResponseMeta, HttpResponse = std.net.http.http_types

Stream, read, read_eof = std.net.http.http_transport
```

### `src/std/net/http/http_request.zen`

8 declarations (functions: 2, imports and re-exports: 6).

#### Functions

```zen
http_url* = (url: str) Res<ParsedUrl, HttpError>

build_request* = (
    parsed  : ParsedUrl,
    a       : Alloc,
    headers : Vec<str>,
    body    : str
) Res<String, HttpError>
```

#### Imports and re-exports

```zen
Alloc = std.mem

str, String = std.text

Res = std.core

Vec = std.collections

ParsedUrl, parse_url = std.net.url

HttpError = std.net.http.http_types
```

### `src/std/net/http/http_transport.zen`

17 declarations (enums: 1, implementations: 1, functions: 7, imports and re-exports: 8).

#### Enums

```zen
Stream* = Tcp(TcpStream) | Tls(TlsStream)
```

#### Implementations

```zen
Stream.impl(Drop, {
    drop = (self :: @Self) ()
})
```

#### Functions

```zen
http_from_tcp_err* = (e: TcpError) HttpError

http_from_tls_err* = (e: TlsError) HttpError

connect_stream* = (parsed: ParsedUrl, a: Alloc) Res<Stream, HttpError>

write* = (self: Stream, bytes: str) Res<(), HttpError>

read* = (
    self : Stream,
    a    : Alloc,
    buf  :: Vec<u8>,
    n    : usize
) Res<usize, HttpError>

read_eof* = (self: Stream, a: Alloc, buf :: Vec<u8>, n: usize)
            Res<usize, HttpError>

close* = (self: Stream) ()
```

#### Imports and re-exports

```zen
Alloc = std.mem

str = std.text

Res, Drop = std.core

Vec = std.collections

TcpStream, TcpError = std.net.tcp

TlsStream, TlsError = std.net.tls

ParsedUrl = std.net.url

HttpError = std.net.http.http_types
```

### `src/std/net/http/http_types.zen`

5 declarations (types: 2, enums: 1, imports and re-exports: 2).

#### Types

```zen
HttpResponseMeta* = {
    status*:             i32,
    content_length*:     usize,
    has_content_length*: bool,
    chunked*:            bool,
}

HttpResponse* = {
    status*: i32,
    body*:   String,
}
```

#### Enums

```zen
HttpError* = ConnectFailed
    | TlsFailed
    | SendFailed
    | RecvFailed
    | DecodeFailed
    | BodyWriteFailed(WriteError)
    | Status(i32)
```

#### Imports and re-exports

```zen
String = std.text

WriteError = std.core.io
```

### `src/std/net/http2/http2.zen`

3 declarations (imports and re-exports: 3).

#### Imports and re-exports

```zen
H2Error*, H2StreamError*, H2Response*, H2Head*, H2Chunk*, MAX_SEND*, h2_chunk* = std.net.http2.http2_types

H2Client*, post_once* = std.net.http2.http2_client

huf_decode*, hpack_status* = std.net.http2.http2_hpack
```

### `src/std/net/http2/http2_client.zen`

16 declarations (types: 3, enums: 1, functions: 1, imports and re-exports: 11).

#### Types

```zen
H2ReadState = { status :: i32, got_final :: bool, done :: bool }

H2Data = {
    bytes:       H2Chunk,
    credit:      usize,
    stream_open: bool,
}

H2Client* = {
    stream   :: Stream,
    sid      :: u32,
    open     :: bool,
    secure   :  bool,
    host     :  String,
    path     :  String,
    init_win :: usize,
    send_win :: usize,
    send_debt :: usize,
    conn_win :: usize,
    active   :: u32,
    got_peer_settings :: bool,
    got_goaway :: bool,
    peer_last :: usize,
    connect* = (a: Alloc, url: str) Res<H2Client, H2Error>
    send_post = (self :: @Self, a: Alloc, headers: Vec<str>, body: str)
                Res<u32, H2Error>
    post_stream* = <R: Actor + Receive<H2Chunk>>(
        self     :: @Self,
        a        : Alloc,
        body     : str,
        receiver : Ref<R>
    ) Res<(), H2StreamError>
    stream_response = <R: Actor + Receive<H2Chunk>>(
        self     :: @Self,
        a        : Alloc,
        sid      : u32,
        receiver : Ref<R>
    ) Res<(), H2StreamError>
    stream_failed = (self :: @Self, error: H2Error) Res<(), H2StreamError>
    receiver_refused = (
        self   :: @Self,
        unread : bool,
        error  : ActorError
    ) Res<(), H2StreamError>
    read_response_into = (self :: @Self, a: Alloc, sid: u32, out :: Sink)
                         Res<i32, H2Error>
    next_response_event = (
        self  :: @Self,
        a     : Alloc,
        sid   : u32,
        state :: H2ReadState
    ) Res<H2Event, H2Error>
    headers_event = (
        self  : @Self,
        a     : Alloc,
        f     : Frame,
        state :: H2ReadState
    ) Res<H2Event, H2Error>
    decode_headers = (
        self  : @Self,
        a     : Alloc,
        f     : Frame,
        state :: H2ReadState
    ) Res<H2Head, H2Error>
    data_event = (
        self  : @Self,
        f     : Frame,
        state :: H2ReadState
    ) Res<H2Event, H2Error>
    restore_recv_window = (
        self        :: @Self,
        a           : Alloc,
        sid         : u32,
        payload_len : usize,
        stream_open : bool
    ) Res<(), H2Error>
    post_into* = (
        self    :: @Self,
        a       : Alloc,
        headers : Vec<str>,
        body    : str,
        out     :: Sink
    ) Res<i32, H2Error>
    post* = (self :: @Self, a: Alloc, headers: Vec<str>, body: str)
            Res<H2Response, H2Error>
    close* = (self :: @Self, a: Alloc) ()
    write_goaway = (self: @Self, a: Alloc, last: usize)
                   Res<(), H2Error>
    add_conn_credit = (self :: @Self, inc: usize) Res<(), H2Error>
    add_stream_credit = (self :: @Self, inc: usize) Res<(), H2Error>
    control = (self :: @Self, a: Alloc, f: Frame) Res<bool, H2Error>
    apply_settings = (self :: @Self, f: Frame) Res<(), H2Error>
}
```

#### Enums

```zen
H2Event = Headers(H2Head) | Data(H2Data)
```

#### Functions

```zen
post_once* = (
    a       : Alloc,
    url     : str,
    headers : Vec<str>,
    body    : str
) Res<H2Response, H2Error>
```

#### Imports and re-exports

```zen
Alloc = std.mem

str, String = std.text

Res = std.core

Sink = std.core

Vec = std.collections

ParsedUrl = std.net.url

Actor, ActorError, Receive, Ref = std.actor

H2Error, H2StreamError, H2Response, H2Head, H2Chunk, h2_chunk, FrameType, FLAG_END_STREAM, FLAG_ACK, FLAG_END_HEADERS, SET_HEADER_TABLE, SET_INITIAL_WINDOW, MAX_SEND, WINDOW, DEFAULT_WINDOW, MAX_WINDOW, PREFACE = std.net.http2.http2_types

Stream, http_url, stream_write, stream_close, dial, alpn_check = std.net.http2.http2_transport

Frame, read_frame, write_frame, settings_add, u32_add, u31_of = std.net.http2.http2_frame

hpack_response_headers, hpack_trailer_headers, block_add_header, block_add_user_header = std.net.http2.http2_hpack
```

### `src/std/net/http2/http2_frame.zen`

14 declarations (types: 2, functions: 6, imports and re-exports: 6).

#### Types

```zen
H2Range* = { from*: usize, len*: usize }

Frame* = {
    ftype*:   FrameType,
    flags*:   u8,
    sid*:     u32,
    payload*: Vec<u8>,
    has_flag* = (self: @Self, flag: u8) bool
    content_range* = (self: @Self) Res<H2Range, H2Error>
}
```

#### Functions

```zen
read_frame* = (s: Stream, a: Alloc) Res<Frame, H2Error>

add_wire_byte = (out :: String, value: usize) Res<(), H2Error>

write_frame* = (
    s       : Stream,
    a       : Alloc,
    ftype   : FrameType,
    flags   : u8,
    sid     : u32,
    payload : str
) Res<(), H2Error>

settings_add* = (blk :: String, id: usize, val: usize) Res<(), H2Error>

u32_add* = (blk :: String, val: usize) Res<(), H2Error>

u31_of* = (payload: Vec<u8>, at: usize) Res<usize, H2Error>
```

#### Imports and re-exports

```zen
Alloc = std.mem

str, String = std.text

Res = std.core

Vec = std.collections

H2Error, FrameType, frame_type, wire, FLAG_PADDED, FLAG_PRIORITY, MAX_RECV = std.net.http2.http2_types

Stream, stream_write, read_n = std.net.http2.http2_transport
```

### `src/std/net/http2/http2_hpack.zen`

34 declarations (types: 4, functions: 20, constants: 5, imports and re-exports: 5).

#### Types

```zen
H2Int = { val: usize, pos: usize }

H2Str = { value: String, pos: usize }

H2Field = { name: String, value: String, pos: usize }

DecodedHeaders = {
    status :: Res<i32>,
    pseudo :: bool,
    bad_pseudo :: bool,
}
```

#### Functions

```zen
static_name = (idx: usize) str

static_value = (idx: usize) str

static_find = (name: str, value: str) usize

static_find_name = (name: str) usize

read_int = (buf: Vec<u8>, pos: usize, prefix: usize) Res<H2Int, H2Error>

block_add_int* = (
    blk    :: String,
    flags  : u8,
    prefix : usize,
    val    : usize
) Res<(), H2Error>

block_add_str* = (blk :: String, s: str) Res<(), H2Error>

huf_decode* = (
    buf  : Vec<u8>,
    a    : Alloc,
    from : usize,
    len  : usize
) Res<String, H2Error>

read_string = (buf: Vec<u8>, a: Alloc, pos: usize) Res<H2Str, H2Error>

decode_headers = (
    buf  : Vec<u8>,
    a    : Alloc,
    from : usize,
    len  : usize
) Res<DecodedHeaders, H2Error>

add_decoded = (self :: DecodedHeaders, name: str, value: str)
              Res<(), H2Error>

hpack_response_headers* = (
    buf  : Vec<u8>,
    a    : Alloc,
    from : usize,
    len  : usize
) Res<H2Head, H2Error>

hpack_trailer_headers* = (
    buf  : Vec<u8>,
    a    : Alloc,
    from : usize,
    len  : usize
) Res<H2Head, H2Error>

hpack_status* = (
    buf  : Vec<u8>,
    a    : Alloc,
    from : usize,
    len  : usize
) Res<i32, H2Error>

read_name_value = (
    buf      : Vec<u8>,
    a        : Alloc,
    pos      : usize,
    name_idx : usize
) Res<H2Field, H2Error>

block_add_header* = (blk :: String, name: str, value: str) Res<(), H2Error>

block_add_lower = (blk :: String, s: str) Res<(), H2Error>

header_skipped = (name: str) bool

block_add_user_header* = (blk :: String, line: str) Res<(), H2Error>

static_find_name_folded = (name: str) usize
```

#### Constants

```zen
STATIC_NAMES: [str, 62] = [
    "", ":authority", ":method", ":method", ":path", ":path",
    ":scheme", ":scheme", ":status", ":status", ":status", ":status",
    ":status", ":status", ":status", "accept-charset", "accept-encoding", "accept-language",
    "accept-ranges", "accept", "access-control-allow-origin", "age", "allow", "authorization",
    "cache-control", "content-disposition", "content-encoding", "content-language", "content-length", "content-location",
    "content-range", "content-type", "cookie", "date", "etag", "expect",
    "expires", "from", "host", "if-match", "if-modified-since", "if-none-match",
    "if-range", "if-unmodified-since", "last-modified", "link", "location", "max-forwards",
    "proxy-authenticate", "proxy-authorization", "range", "referer", "refresh", "retry-after",
    "server", "set-cookie", "strict-transport-security", "transfer-encoding", "user-agent", "vary",
    "via", "www-authenticate",
]

HUF_SYMTAB: [u8, 257] = [
        48, 49, 50, 97, 99, 101, 105, 111, 115, 116, 32, 37, 45, 46, 47, 51,
        52, 53, 54, 55, 56, 57, 61, 65, 95, 98, 100, 102, 103, 104, 108, 109,
        110, 112, 114, 117, 58, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76,
        77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 89, 106, 107, 113, 118,
        119, 120, 121, 122, 38, 42, 44, 59, 88, 90, 33, 34, 40, 41, 63, 39,
        43, 124, 35, 62, 0, 36, 64, 91, 93, 126, 94, 125, 60, 96, 123, 92,
        195, 208, 128, 130, 131, 162, 184, 194, 224, 226, 153, 161, 167, 172, 176, 177,
        179, 209, 216, 217, 227, 229, 230, 129, 132, 133, 134, 136, 146, 154, 156, 160,
        163, 164, 169, 170, 173, 178, 181, 185, 186, 187, 189, 190, 196, 198, 228, 232,
        233, 1, 135, 137, 138, 139, 140, 141, 143, 147, 149, 150, 151, 152, 155, 157,
        158, 165, 166, 168, 174, 175, 180, 182, 183, 188, 191, 197, 231, 239, 9, 142,
        144, 145, 148, 159, 171, 206, 215, 225, 236, 237, 199, 207, 234, 235, 192, 193,
        200, 201, 202, 205, 210, 213, 218, 219, 238, 240, 242, 243, 255, 203, 204, 211,
        212, 214, 221, 222, 223, 241, 244, 245, 246, 247, 248, 250, 251, 252, 253, 254,
        2, 3, 4, 5, 6, 7, 8, 11, 12, 14, 15, 16, 17, 18, 19, 20,
        21, 23, 24, 25, 26, 27, 28, 29, 30, 31, 127, 220, 249, 10, 13, 22,
        0,
    ]

HUF_FIRST_CODE: [u32, 31] = [
        0, 0, 0, 0, 0, 0, 20, 92, 248, 0, 1016, 2042, 4090, 8184, 16380, 32764, 0, 0, 0, 524272, 1048550, 2097116, 4194258, 8388568, 16777194, 33554412, 67108832, 134217694, 268435426, 0, 1073741820,
    ]

HUF_COUNT: [u32, 31] = [
        0, 0, 0, 0, 0, 10, 26, 32, 6, 0, 5, 3, 2, 6, 2, 3, 0, 0, 0, 3, 8, 13, 26, 29, 12, 4, 15, 19, 29, 0, 4,
    ]

HUF_FIRST_IDX: [u32, 31] = [
        0, 0, 0, 0, 0, 0, 10, 36, 68, 0, 74, 79, 82, 84, 90, 92, 0, 0, 0, 95, 98, 106, 119, 145, 174, 186, 190, 205, 224, 0, 253,
    ]
```

#### Imports and re-exports

```zen
Alloc = std.mem

str, String, str_at = std.text

Res = std.core

Vec = std.collections

H2Error, H2Head = std.net.http2.http2_types
```

### `src/std/net/http2/http2_transport.zen`

18 declarations (enums: 1, functions: 9, imports and re-exports: 8).

#### Enums

```zen
Stream* = Tcp(TcpStream) | Tls(TlsStream)
```

#### Functions

```zen
http_url* = (url: str) Res<ParsedUrl, H2Error>

from_tcp_err = (e: TcpError) H2Error

from_tls_err = (e: TlsError) H2Error

stream_write* = (s: Stream, bytes: str) Res<(), H2Error>

stream_read* = (
    s   : Stream,
    a   : Alloc,
    buf :: Vec<u8>,
    n   : usize
) Res<usize, H2Error>

stream_close* = (s: Stream) ()

read_n* = (s: Stream, a: Alloc, buf :: Vec<u8>, n: usize) Res<(), H2Error>

dial* = (parsed: ParsedUrl, a: Alloc) Res<Stream, H2Error>

alpn_check* = (s: Stream, a: Alloc) Res<(), H2Error>
```

#### Imports and re-exports

```zen
Alloc = std.mem

str, str_at = std.text

Res = std.core

Vec = std.collections

TcpStream, TcpError = std.net.tcp

TlsStream, TlsError = std.net.tls

ParsedUrl, parse_url = std.net.url

H2Error = std.net.http2.http2_types
```

### `src/std/net/http2/http2_types.zen`

28 declarations (types: 2, enums: 4, implementations: 1, functions: 3, constants: 13, imports and re-exports: 5).

#### Types

```zen
H2Response* = {
    status*: i32,
    body*:   String,
}

H2Chunk* = {
    bytes :: [u8, MAX_SEND],
    len*:  usize,
    get* = (self: @Self, at: usize) Res<u8>
    append_to* = (self: @Self, out :: String) Res<(), AllocError>
    write_to* = (self: @Self, out :: Sink) Res<(), WriteError>
    copy* = (self: @Self, a: Alloc) Res<String, AllocError>
}
```

#### Enums

```zen
H2Error* = ConnectFailed
    | TlsFailed
    | SendFailed
    | RecvFailed
    | DecodeFailed
    | ProtocolFailed
    | Closed
    | Status(i32)

H2Head* = Informational(i32) | Response(i32) | Trailers

H2StreamError* = Http(H2Error) | Receiver(ActorError)

FrameType* = Data
    | Headers
    | Priority
    | Reset
    | Settings
    | Push
    | Ping
    | GoAway
    | WindowUpdate
    | Continuation
    | Unknown(u8)
```

#### Implementations

```zen
H2Chunk.impl(Range<u8>, {
    start: 0,
    end: self.len,
    at ::= (self: @Self, index: usize) Res<u8>
})
```

#### Functions

```zen
h2_chunk* = (src: str) Res<H2Chunk, H2Error>

frame_type* = (raw: u8) FrameType

wire* = (kind: FrameType) u8
```

#### Constants

```zen
MAX_SEND*: usize = 16384

FLAG_END_STREAM*:  u8 = 1

FLAG_ACK*:         u8 = 1

FLAG_END_HEADERS*: u8 = 4

FLAG_PADDED*:      u8 = 8

FLAG_PRIORITY*:    u8 = 32

SET_HEADER_TABLE*:   usize = 1

SET_INITIAL_WINDOW*: usize = 4

WINDOW*: usize = 16777216

DEFAULT_WINDOW*: usize = 65535

MAX_WINDOW*: usize = 2147483647

MAX_RECV*: usize = 1048576

PREFACE*: str = "PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n"
```

#### Imports and re-exports

```zen
str, String = std.text

Range, Res = std.core

Sink, WriteError = std.core

ActorError = std.actor

Alloc, AllocError = std.mem
```

### `src/std/net/socket/socket.zen`

29 declarations (types: 4, enums: 1, implementations: 1, functions: 11, constants: 7, imports and re-exports: 5).

#### Types

```zen
AddrInfo = {
    flags: i32,
    family: i32,
    socktype: i32,
    protocol: i32,
    address_len: u32,
    address: Ptr<u8>,
    canonical_name: Ptr<u8>,
    next: Ptr<AddrInfo>,
}

ResolvedAddr* = {
    ip*: String,
    is_v6*: bool,
}

SocketFd* = {
    raw: i32,
    raw_handle* = (self: @Self) i32
    send* = (
        self  : @Self,
        bytes : Ptr<u8>,
        len   : usize,
        flags : i32
    ) Res<usize, SocketFault>
    send* = (self: @Self, bytes: str) Res<(), SocketFault>
    recv* = (
        self  : @Self,
        bytes : Ptr<u8>,
        len   : usize,
        flags : i32
    ) Res<usize, SocketFault>
    recv* = (self: @Self, bytes: Ptr<u8>, len: usize)
            Res<usize, SocketFault>
}

Socket* = {
    raw: i32,
    open :: bool = true,
    tcp_connect* = (a: Alloc, host: str, port: u16)
                   Res<Socket, SocketFault>
    handle* = (self: @Self) SocketFd
    write* = (self: @Self, bytes: str) Res<(), SocketFault>
    read* = (self: @Self, buf :: Vec<u8>, n: usize)
            Res<usize, SocketFault>
    close* = (self :: @Self) ()
}
```

#### Enums

```zen
SocketFault* = ConnectFault | WriteFault | ReadFault | PeerClosed
```

#### Implementations

```zen
Socket.impl(Drop, {
    drop = (self :: @Self) ()
})
```

#### Functions

```zen
socket = (domain: i32, kind: i32, protocol: i32) i32

connect = (fd: i32, address: Ptr<u8>, address_len: u32) i32

send = (fd: i32, bytes: Ptr<u8>, len: usize, flags: i32) usize

recv = (fd: i32, bytes: Ptr<u8>, len: usize, flags: i32) usize

close = (fd: i32) i32

getaddrinfo = (
    host    : Ptr<u8>,
    service : Ptr<u8>,
    hints   : Ptr<AddrInfo>,
    answer  : Ptr<Ptr<AddrInfo>>
) i32

freeaddrinfo = (answer: Ptr<AddrInfo>) ()

getnameinfo = (
    address     : Ptr<u8>,
    address_len : u32,
    host        : Ptr<u8>,
    host_len    : u32,
    service     : Ptr<u8>,
    service_len : u32,
    flags       : i32
) i32

hints = (a: Alloc, fault: SocketFault) Res<Vec<AddrInfo>, SocketFault>

addresses = (
    a            : Alloc,
    host         : Ptr<u8>,
    service      : Ptr<u8>,
    alloc_fault  : SocketFault,
    lookup_fault : SocketFault
)
            Res<Vec<Ptr<AddrInfo>>, SocketFault>

resolve_addr* = (a: Alloc, host: str) Res<ResolvedAddr, SocketFault>
```

#### Constants

```zen
AF_UNSPEC: i32 = 0

AF_INET6: i32 = 10

SOCK_STREAM: i32 = 1

IPPROTO_TCP: i32 = 6

MSG_NOSIGNAL: i32 = 16384

NI_MAXHOST: usize = 1025

NI_NUMERICHOST: i32 = 1
```

#### Imports and re-exports

```zen
Alloc, AllocError, Ptr, null_ptr = std.mem

str, String, str_at = std.text

Res = std.core

Drop = std.core

Vec = std.collections
```

### `src/std/net/tcp.zen`

10 declarations (types: 1, enums: 1, implementations: 1, functions: 1, imports and re-exports: 6).

#### Types

```zen
TcpStream* = {
    socket :: Socket,
    connect* = (a: Alloc, host: str, port: u16) Res<TcpStream, TcpError>
    write* = (self: @Self, bytes: str) Res<(), TcpError>
    read* = (self: @Self, a: Alloc, buf :: Vec<u8>, n: usize)
            Res<usize, TcpError>
    close* = (self :: @Self) ()
}
```

#### Enums

```zen
TcpError* = ConnectFailed | WriteFailed | ReadFailed | Closed
```

#### Implementations

```zen
TcpStream.impl(Drop, {
    drop = (self :: @Self) ()
})
```

#### Functions

```zen
tcp_error = (fault: SocketFault) TcpError
```

#### Imports and re-exports

```zen
Alloc = std.mem

str = std.text

Res = std.core

Drop = std.core

Vec = std.collections

Socket, SocketFault = std.net.socket
```

### `src/std/net/tls/tls.zen`

39 declarations (types: 1, enums: 1, implementations: 1, functions: 24, constants: 6, imports and re-exports: 6).

#### Types

```zen
TlsStream* = {
    socket :: Socket,
    alloc: Alloc,
    ssl: Ptr<u8>,
    ctx: Ptr<u8>,
    open :: bool = true,
    connect* = (a: Alloc, host: str, port: u16) Res<TlsStream, TlsError>
    connect_h2* = (a: Alloc, host: str, port: u16)
                  Res<TlsStream, TlsError>
    alpn* = (self: @Self, a: Alloc, buf :: Vec<u8>)
            Res<usize, TlsError>
    write* = (self: @Self, bytes: str) Res<(), TlsError>
    read* = (self: @Self, a: Alloc, buf :: Vec<u8>, n: usize)
            Res<usize, TlsError>
    read_nonempty = (self: @Self, a: Alloc, buf :: Vec<u8>, n: usize)
                    Res<usize, TlsError>
    close* = (self :: @Self) ()
}
```

#### Enums

```zen
TlsError* = ConnectFailed | TlsFailed | WriteFailed | ReadFailed | Closed
```

#### Implementations

```zen
TlsStream.impl(Drop, {
    drop = (self :: @Self) ()
})
```

#### Functions

```zen
TLS_client_method = () Ptr<u8>

SSL_CTX_new = (method: Ptr<u8>) Ptr<u8>

SSL_CTX_free = (ctx: Ptr<u8>) ()

SSL_CTX_set_default_verify_paths = (ctx: Ptr<u8>) i32

SSL_CTX_set_verify = (ctx: Ptr<u8>, mode: i32, callback: Ptr<()>) ()

SSL_CTX_set_alpn_protos = (
    ctx           : Ptr<u8>,
    protocols     : Ptr<u8>,
    protocols_len : u32
) i32

SSL_new = (ctx: Ptr<u8>) Ptr<u8>

SSL_free = (ssl: Ptr<u8>) ()

SSL_set_fd = (ssl: Ptr<u8>, fd: i32) i32

SSL_ctrl = (ssl: Ptr<u8>, command: i32, larg: i64, parg: Ptr<()>) i64

SSL_set_hostflags = (ssl: Ptr<u8>, flags: u32) ()

SSL_set1_host = (ssl: Ptr<u8>, host: Ptr<u8>) i32

SSL_connect = (ssl: Ptr<u8>) i32

SSL_get_verify_result = (ssl: Ptr<u8>) i64

SSL_get0_alpn_selected = (
    ssl          : Ptr<u8>,
    selected     : Ptr<Ptr<u8>>,
    selected_len : Ptr<u32>
) ()

SSL_write_ex = (
    ssl     : Ptr<u8>,
    bytes   : Ptr<u8>,
    len     : usize,
    written : Ptr<usize>
) i32

SSL_read_ex = (
    ssl   : Ptr<u8>,
    bytes : Ptr<u8>,
    len   : usize,
    read  : Ptr<usize>
) i32

SSL_get_error = (ssl: Ptr<u8>, rc: i32) i32

SSL_shutdown = (ssl: Ptr<u8>) i32

alpn_h2 = (a: Alloc) Res<Vec<u8>, TlsError>

tls_dial = (a: Alloc, host: str, port: u16, h2: bool)
           Res<TlsStream, TlsError>

wrap_socket = (a: Alloc, socket :: Socket, host: str, h2: bool)
              Res<TlsStream, TlsError>

wrap_ctx = (
    a      : Alloc,
    socket :: Socket,
    host_c : Vec<u8>,
    h2     : bool,
    ctx    : Ptr<u8>
) Res<TlsStream, TlsError>

wrap_ssl = (a: Alloc, socket :: Socket, host_c: Vec<u8>, ctx: Ptr<u8>)
           Res<TlsStream, TlsError>
```

#### Constants

```zen
SSL_VERIFY_PEER: i32 = 1

SSL_CTRL_SET_TLSEXT_HOSTNAME: i32 = 55

X509_CHECK_FLAG_NO_PARTIAL_WILDCARDS: u32 = 4

SSL_ERROR_WANT_READ: i32 = 2

SSL_ERROR_WANT_WRITE: i32 = 3

SSL_ERROR_ZERO_RETURN: i32 = 6
```

#### Imports and re-exports

```zen
Alloc, AllocError, Ptr, null_ptr = std.mem

str = std.text

Res = std.core

Drop = std.core

Vec = std.collections

Socket = std.net.socket
```

### `src/std/net/url.zen`

5 declarations (types: 1, enums: 1, functions: 1, imports and re-exports: 2).

#### Types

```zen
ParsedUrl* = {
    scheme*: str,
    host*:   str,
    port*:   u16,
    path*:   str,
}
```

#### Enums

```zen
UrlError* = | Invalid
```

#### Functions

```zen
parse_url* = (url: str) Res<ParsedUrl, UrlError>
```

#### Imports and re-exports

```zen
str = std.text

Res, ok_or = std.core
```

### `src/std/parse/parse.zen`

9 declarations (imports and re-exports: 9).

#### Imports and re-exports

```zen
Diag*, Note*, diag*, diag_at* = std.parse.parse_diag

Token*, TokenKind* = std.parse.parse_token

Parser*, Mark*, MAX_DEPTH* = std.parse.parser

module*, declaration* = std.parse.parse_decl

block* = std.parse.parse_stmt

expr* = std.parse.parse_expr

type* = std.parse.parse_type

pattern* = std.parse.parse_pattern

arms* = std.parse.parse_match
```

### `src/std/parse/parse_decl.zen`

39 declarations (functions: 26, imports and re-exports: 13).

#### Functions

```zen
module* = (p :: Parser, name: str) Res<Module, AllocError>

recover* = (p :: Parser) Res<(), AllocError>

declaration* = (p :: Parser, module_level: bool) Res<Decl, AllocError>

impl_decl = (p :: Parser, m: Mark) Res<Decl, AllocError>

impl_ahead* = (p :: Parser) bool

named_decl = (p :: Parser, m: Mark, module_level: bool) Res<Decl, AllocError>

decl_names = (
    p       :: Parser,
    names   :: Vec<ImportName>,
    tparams :: Vec<TParam>
) Res<(), AllocError>

one_decl_name = (
    p       :: Parser,
    tparams :: Vec<TParam>
) Res<ImportName, AllocError>

decl_value = (
    p            :: Parser,
    m            : Mark,
    names        : Vec<ImportName>,
    tparams      : Vec<TParam>,
    written      : Res<TypeId>,
    mutable      : bool,
    module_level : bool
) Res<Decl, AllocError>

head_name = (p: Parser, names: Vec<ImportName>) ImportName

struct_decl = (
    p       :: Parser,
    m       : Mark,
    head    : ImportName,
    tparams : Vec<TParam>
) Res<Decl, AllocError>

enum_decl = (
    p       :: Parser,
    m       : Mark,
    head    : ImportName,
    tparams : Vec<TParam>
) Res<Decl, AllocError>

bar_span = (p :: Parser) Res<Res<Span>, AllocError>

one_variant = (p :: Parser) Res<Variant, AllocError>

variant_payload = (p :: Parser) Res<Res<TypeId>, AllocError>

fn_decl = (
    p       :: Parser,
    m       : Mark,
    head    : ImportName,
    tparams : Vec<TParam>,
    mutable : bool
) Res<Decl, AllocError>

fn_value* = (
    p          :: Parser,
    name       : Ident,
    exported   : bool,
    tparams    : Vec<TParam>,
    rebindable : bool
) Res<Function, AllocError>

typed_params = (p :: Parser, ps: Vec<Param>) Res<(), AllocError>

fn_body = (p :: Parser) Res<Res<BlockId>, AllocError>

has_body = (p: Parser, body: Res<BlockId>) bool

form_of = (rebindable: bool, body: bool) Form

merge_tparams = (p: Parser, head: Vec<TParam>, own: Vec<TParam>) Vec<TParam>

alias_decl = (
    p       :: Parser,
    m       : Mark,
    head    : ImportName,
    tparams : Vec<TParam>
) Res<Decl, AllocError>

import_decl = (
    p     :: Parser,
    m     : Mark,
    names : Vec<ImportName>
) Res<Decl, AllocError>

const_decl = (
    p       :: Parser,
    m       : Mark,
    head    : ImportName,
    written : Res<TypeId>,
    mutable : bool
) Res<Decl, AllocError>

add_decl* = (p :: Parser, kind: DeclKind, m: Mark) Res<Decl, AllocError>
```

#### Imports and re-exports

```zen
AllocError = std.mem

Span, Pos, Ident, no_trivia = std.ast.ast_span

TypeId, BlockId = std.ast.ast_id

Decl, DeclKind, Struct, Enum, Alias, Function, Impl, Import, Const = std.ast.ast_node

Member, Variant, ImportName, Param, TParam, Form, Module = std.ast.ast_node

TokenKind = std.parse.parse_token

Parser, Mark = std.parse.parser

expr = std.parse.parse_expr

type, written_type = std.parse.parse_type

value_shape, delim_step, ret_ahead = std.parse.parse_lookahead

body_block = std.parse.parse_stmt

qualified_name = std.parse.parse_pattern

struct_members, record_body, params_list, type_params = std.parse.parse_member
```

### `src/std/parse/parse_diag.zen`

8 declarations (types: 2, functions: 4, imports and re-exports: 2).

#### Types

```zen
Note* = {
    message*: str,
    span*: Span,
}

Diag* = {
    message*: str,
    span*: Span,
    note*: Res<Note>,
}
```

#### Functions

```zen
diag* = (message: str, span: Span) Diag

diag_at* = (message: str, span: Span, note_message: str, note_span: Span) Diag

say* = (self: Diag) ()

truncated* = (message: str, at: Span, ended: bool, end: Pos) str
```

#### Imports and re-exports

```zen
Pos, Span = std.ast.ast_span

before = std.ast.ast_find
```

### `src/std/parse/parse_expr.zen`

59 declarations (functions: 46, imports and re-exports: 13).

#### Functions

```zen
expr* = (p :: Parser) Res<ExprId, AllocError>

expr_guarded = (p :: Parser) Res<ExprId, AllocError>

expr_here = (p :: Parser) Res<ExprId, AllocError>

consume_expr = (p :: Parser, m: Mark) Res<ExprId, AllocError>

precedence* = (kind: TokenKind) usize

binary_op = (kind: TokenKind) BinOp

binary_from = (p :: Parser, m: Mark, min: usize) Res<ExprId, AllocError>

binary_step = (
    p    :: Parser,
    m    : Mark,
    prec : usize,
    lhs  : ExprId
) Res<ExprId, AllocError>

unary_at = (p :: Parser, m: Mark) Res<ExprId, AllocError>

unary_expr = (p :: Parser, m: Mark, op: UnOp) Res<ExprId, AllocError>

unary_operand = (p :: Parser, m: Mark) Res<ExprId, AllocError>

postfix = (p :: Parser, m: Mark) Res<ExprId, AllocError>

starts_expr* = (p :: Parser) bool

postfix_continues = (p :: Parser) bool

postfix_step = (p :: Parser, m: Mark, base: ExprId) Res<ExprId, AllocError>

targs_call = (p :: Parser, m: Mark, base: ExprId) Res<ExprId, AllocError>

after_dot = (p :: Parser, m: Mark, base: ExprId) Res<ExprId, AllocError>

dot_target = (
    p    :: Parser,
    m    : Mark,
    base : ExprId,
    name : Ident
) Res<ExprId, AllocError>

match_expr = (
    p         :: Parser,
    m         : Mark,
    scrutinee : ExprId,
    name_span : Span
) Res<ExprId, AllocError>

try_expr = (
    p         :: Parser,
    m         : Mark,
    operand   : ExprId,
    name_span : Span
) Res<ExprId, AllocError>

index_expr = (p :: Parser, m: Mark, base: ExprId) Res<ExprId, AllocError>

call_expr = (
    p      :: Parser,
    m      : Mark,
    callee : ExprId,
    targs  : Vec<TypeId>
) Res<ExprId, AllocError>

args* = (p :: Parser, out :: Vec<Arg>) Res<Span, AllocError>

one_arg = (p :: Parser) Res<Arg, AllocError>

named_arg_name = (p :: Parser) Res<Res<Ident>, AllocError>

arg_value = (p :: Parser) Res<ExprId, AllocError>

record_expr = (p :: Parser) Res<ExprId, AllocError>

primary = (p :: Parser, m: Mark) Res<ExprId, AllocError>

name_expr = (p :: Parser, m: Mark) Res<ExprId, AllocError>

literal_expr = (
    p    :: Parser,
    m    : Mark,
    kind : LiteralKind
) Res<ExprId, AllocError>

word_expr = (p :: Parser, m: Mark, kind: ExprKind) Res<ExprId, AllocError>

meta_expr = (p :: Parser, m: Mark) Res<ExprId, AllocError>

typed_meta = (p :: Parser, m: Mark) Res<ExprId, AllocError>

value_meta = (p :: Parser, m: Mark) Res<ExprId, AllocError>

paren_or_lambda = (p :: Parser, m: Mark) Res<ExprId, AllocError>

paren_expr = (p :: Parser, m: Mark) Res<ExprId, AllocError>

unit_expr = (p :: Parser, m: Mark) Res<ExprId, AllocError>

grouped_expr = (p :: Parser, m: Mark, open: Span) Res<ExprId, AllocError>

generic_lambda = (p :: Parser, m: Mark) Res<ExprId, AllocError>

lambda* = (p :: Parser, m: Mark, tps: Vec<TParam>) Res<ExprId, AllocError>

bracket_expr = (p :: Parser, m: Mark) Res<ExprId, AllocError>

fixed_array = (p :: Parser, m: Mark) Res<ExprId, AllocError>

array_lit = (p :: Parser, m: Mark) Res<ExprId, AllocError>

elem_list = (
    p       :: Parser,
    out     :: Vec<ExprId>,
    close   : TokenKind,
    message : str
) Res<Span, AllocError>

poison_expr* = (p :: Parser) Res<ExprId, AllocError>

add_expr* = (p :: Parser, kind: ExprKind, m: Mark) Res<ExprId, AllocError>
```

#### Imports and re-exports

```zen
AllocError = std.mem

Span, Ident, no_trivia = std.ast.ast_span

ExprId, TypeId = std.ast.ast_id

Expr, ExprKind, Name, Paren, ArrayLit, FixedArray, Lambda, Call, Arg = std.ast.ast_node

Match, Arm, Try, Record, Access, Index, Unary, Binary, Consume, Meta = std.ast.ast_node

Literal, LiteralKind, UnOp, BinOp, Param, TParam, Member = std.ast.ast_node

TokenKind = std.parse.parse_token

Parser, Mark = std.parse.parser

type, type_args, starts_type, written_type = std.parse.parse_type

lambda_ahead, fixed_array_ahead, targs_ahead = std.parse.parse_lookahead

arms = std.parse.parse_match

body_block = std.parse.parse_stmt

record_body, params_list, type_params = std.parse.parse_member
```

### `src/std/parse/parse_lookahead.zen`

39 declarations (enums: 1, functions: 35, imports and re-exports: 3).

#### Enums

```zen
ValueShape* = StructValue
    | EnumValue
    | FnValue
    | PathValue
    | AliasValue
    | ExprValue
```

#### Functions

```zen
live_at* = (p :: Parser, from: usize) usize

live_kind* = (p :: Parser, from: usize) TokenKind

lambda_ahead* = (p :: Parser) bool

ret_start* = (kind: TokenKind) bool

fn_value_after* = (kind: TokenKind) bool

fixed_array_ahead* = (p :: Parser) bool

targs_ahead* = (p :: Parser) bool

group_end_at = (p :: Parser, from: usize) usize

angles_end_at = (p :: Parser, from: usize) usize

group_items_at = (p :: Parser, from: usize, to: usize) usize

delim_step* = (kind: TokenKind, depth: usize) usize

angle_step = (kind: TokenKind, depth: usize) usize

angle_stop = (kind: TokenKind) bool

down = (d: usize) usize

value_shape* = (p :: Parser, module_level: bool) ValueShape

paren_shape = (p :: Parser) ValueShape

angle_shape = (p :: Parser) ValueShape

ident_shape = (p :: Parser, module_level: bool) ValueShape

variant_ahead = (p :: Parser) bool

path_or_alias = (p :: Parser) ValueShape

closes_value = (p :: Parser, j: usize) bool

continues_expr = (kind: TokenKind) bool

decl_head_ahead* = (p :: Parser, module_level: bool) bool

head_shape_ahead = (p :: Parser) bool

generic_head_ahead = (p :: Parser, j: usize) bool

assign_head_ahead = (p :: Parser, after: TokenKind, j: usize) bool

assigns = (p: Parser, kind: TokenKind) bool

declares_value = (p :: Parser, j: usize) bool

declares_fn = (p :: Parser, j: usize, kind: TokenKind) bool

declares_enum = (p :: Parser, j: usize, kind: TokenKind) bool

bar_after = (p :: Parser, j: usize) bool

ret_ahead* = (p :: Parser) bool

member_head_ahead* = (p :: Parser) bool

binder_after_head = (p :: Parser) bool

binds = (kind: TokenKind) bool
```

#### Imports and re-exports

```zen
TokenKind, is_trivia = std.parse.parse_token

Parser = std.parse.parser

starts_type_kind = std.parse.parse_type
```

### `src/std/parse/parse_match.zen`

12 declarations (functions: 3, imports and re-exports: 9).

#### Functions

```zen
arms* = (p :: Parser, out :: Vec<Arm>) Res<Span, AllocError>

one_arm = (p :: Parser) Res<Arm, AllocError>

arm_body = (p :: Parser) Res<ExprId, AllocError>
```

#### Imports and re-exports

```zen
AllocError = std.mem

Span = std.ast.ast_span

ExprId = std.ast.ast_id

Arm = std.ast.ast_node

TokenKind = std.parse.parse_token

Parser = std.parse.parser

pattern = std.parse.parse_pattern

expr = std.parse.parse_expr

block_expr = std.parse.parse_stmt
```

### `src/std/parse/parse_member.zen`

31 declarations (functions: 22, imports and re-exports: 9).

#### Functions

```zen
struct_members* = (p :: Parser, out :: Vec<Member>) Res<Span, AllocError>

record_body* = (p :: Parser, out :: Vec<Member>) Res<Span, AllocError>

member_list = (
    p     :: Parser,
    out   :: Vec<Member>,
    typed : bool
) Res<Span, AllocError>

one_member = (p :: Parser, typed: bool) Res<Member, AllocError>

member_kind = (
    p        :: Parser,
    name     : Ident,
    exported : bool,
    tparams  : Vec<TParam>,
    typed    : bool
) Res<MemberKind, AllocError>

after_colon = (
    p        :: Parser,
    name     : Ident,
    exported : bool,
    tparams  : Vec<TParam>,
    typed    : bool,
    mutable  : bool
) Res<MemberKind, AllocError>

typed_member = (
    p        :: Parser,
    name     : Ident,
    exported : bool,
    mutable  : bool
) Res<MemberKind, AllocError>

split_r4 = (
    p        :: Parser,
    name     : Ident,
    exported : bool,
    mutable  : bool,
    t        : TypeId,
    value    : Res<ExprId>
) Res<MemberKind, AllocError>

supplied_member = (
    p        :: Parser,
    name     : Ident,
    exported : bool,
    mutable  : bool
) Res<MemberKind, AllocError>

after_assign = (
    p          :: Parser,
    name       : Ident,
    exported   : bool,
    tparams    : Vec<TParam>,
    rebindable : bool,
    typed      : bool
) Res<MemberKind, AllocError>

no_type_member = (
    p          :: Parser,
    name       : Ident,
    exported   : bool,
    rebindable : bool
) Res<MemberKind, AllocError>

fn_member_ahead = (p :: Parser) bool

fn_member = (
    p          :: Parser,
    name       : Ident,
    exported   : bool,
    tparams    : Vec<TParam>,
    rebindable : bool
) Res<MemberKind, AllocError>

member_value = (p :: Parser) Res<Res<ExprId>, AllocError>

has_value* = (p: Parser, value: Res<ExprId>) bool

the_value* = (p: Parser, value: Res<ExprId>) ExprId

params_list* = (p :: Parser, out :: Vec<Param>) Res<Span, AllocError>

one_param = (p :: Parser) Res<Param, AllocError>

param_type = (p :: Parser) Res<Res<TypeId>, AllocError>

type_params* = (p :: Parser, out :: Vec<TParam>) Res<(), AllocError>

one_tparam = (p :: Parser) Res<TParam, AllocError>

type_bounds = (p :: Parser, out :: Vec<TypeId>) Res<(), AllocError>
```

#### Imports and re-exports

```zen
AllocError = std.mem

Span, Ident = std.ast.ast_span

TypeId, ExprId = std.ast.ast_id

Member, MemberKind, Field, Const, Param, TParam = std.ast.ast_node

TokenKind = std.parse.parse_token

Parser = std.parse.parser

expr = std.parse.parse_expr

type, written_type = std.parse.parse_type

fn_value = std.parse.parse_decl
```

### `src/std/parse/parse_pattern.zen`

17 declarations (functions: 11, imports and re-exports: 6).

#### Functions

```zen
pattern* = (p :: Parser) Res<PatternId, AllocError>

pattern_guarded = (p :: Parser) Res<PatternId, AllocError>

pattern_here = (p :: Parser) Res<PatternId, AllocError>

name_or_wild = (p :: Parser, m: Mark) Res<PatternId, AllocError>

wild_pattern = (p :: Parser, m: Mark) Res<PatternId, AllocError>

literal_pattern = (
    p    :: Parser,
    m    : Mark,
    kind : LiteralKind
) Res<PatternId, AllocError>

path_pattern = (p :: Parser, m: Mark) Res<PatternId, AllocError>

destructure_pattern = (
    p    :: Parser,
    m    : Mark,
    name : QualifiedName
) Res<PatternId, AllocError>

qualified_name* = (p :: Parser) Res<QualifiedName, AllocError>

poison_pattern* = (p :: Parser) Res<PatternId, AllocError>

add_pattern* = (
    p    :: Parser,
    kind : PatternKind,
    m    : Mark
) Res<PatternId, AllocError>
```

#### Imports and re-exports

```zen
AllocError = std.mem

Ident, QualifiedName, no_trivia = std.ast.ast_span

PatternId = std.ast.ast_id

Pattern, PatternKind, PatName, Destructure, Literal, LiteralKind = std.ast.ast_node

TokenKind, WILDCARD = std.parse.parse_token

Parser, Mark = std.parse.parser
```

### `src/std/parse/parse_stmt.zen`

31 declarations (functions: 21, imports and re-exports: 10).

#### Functions

```zen
block* = (p :: Parser) Res<BlockId, AllocError>

block_guarded = (p :: Parser) Res<BlockId, AllocError>

block_here = (p :: Parser) Res<BlockId, AllocError>

body_block* = (p :: Parser) Res<BlockId, AllocError>

block_expr* = (p :: Parser) Res<ExprId, AllocError>

one_item = (p :: Parser, stmts :: Vec<Stmt>) Res<Res<ExprId>, AllocError>

nested_block = (p :: Parser, stmts :: Vec<Stmt>, m: Mark) Res<(), AllocError>

ident_item = (
    p     :: Parser,
    stmts :: Vec<Stmt>,
    m     : Mark
) Res<Res<ExprId>, AllocError>

binding_item = (
    p     :: Parser,
    stmts :: Vec<Stmt>,
    m     : Mark
) Res<Res<ExprId>, AllocError>

impl_item = (p :: Parser, stmts :: Vec<Stmt>, m: Mark) Res<(), AllocError>

decl_item = (p :: Parser, stmts :: Vec<Stmt>, m: Mark) Res<(), AllocError>

expr_item = (
    p     :: Parser,
    stmts :: Vec<Stmt>,
    m     : Mark
) Res<Res<ExprId>, AllocError>

tail_value = (p :: Parser, value: ExprId) Res<Res<ExprId>, AllocError>

bind_typed = (
    p      :: Parser,
    stmts  :: Vec<Stmt>,
    m      : Mark,
    target : ExprId
) Res<(), AllocError>

bind = (
    p       :: Parser,
    stmts   :: Vec<Stmt>,
    m       : Mark,
    target  : ExprId,
    mutable : bool
) Res<(), AllocError>

bind_rest = (
    p       :: Parser,
    stmts   :: Vec<Stmt>,
    m       : Mark,
    target  : ExprId,
    t       : Res<TypeId>,
    mutable : bool
) Res<(), AllocError>

expr_stmt = (
    p     :: Parser,
    stmts :: Vec<Stmt>,
    m     : Mark,
    e     : ExprId
) Res<(), AllocError>

push* = (
    p     :: Parser,
    stmts :: Vec<Stmt>,
    kind  : StmtKind,
    m     : Mark
) Res<(), AllocError>

skip_one = (p :: Parser) Res<(), AllocError>

no_value = (p: Parser) Res<ExprId>

poison_block* = (p :: Parser) Res<BlockId, AllocError>
```

#### Imports and re-exports

```zen
AllocError = std.mem

no_trivia = std.ast.ast_span

ExprId, TypeId, BlockId = std.ast.ast_id

Block, Stmt, StmtKind, Bind, ExprStmt, Decl, Expr, ExprKind = std.ast.ast_node

TokenKind = std.parse.parse_token

Parser, Mark = std.parse.parser

expr, add_expr = std.parse.parse_expr

type = std.parse.parse_type

declaration, impl_ahead = std.parse.parse_decl

decl_head_ahead = std.parse.parse_lookahead
```

### `src/std/parse/parse_token.zen`

5 declarations (functions: 2, constants: 1, imports and re-exports: 2).

#### Functions

```zen
empty_eof* = () Token

is_trivia* = (kind: TokenKind) bool
```

#### Constants

```zen
WILDCARD*: str = "_"
```

#### Imports and re-exports

```zen
Token*, TokenKind*, Source*, Lexed*, text_of*, kind_name* = std.lex.lex

Pos, Span = std.lex.lex
```

### `src/std/parse/parse_type.zen`

29 declarations (functions: 20, imports and re-exports: 9).

#### Functions

```zen
type* = (p :: Parser) Res<TypeId, AllocError>

written_type* = (p :: Parser) Res<Res<TypeId>, AllocError>

union_type = (p :: Parser) Res<TypeId, AllocError>

union_rest = (p :: Parser, m: Mark, first: TypeId) Res<TypeId, AllocError>

primary_type = (p :: Parser) Res<TypeId, AllocError>

primary_type_at = (p :: Parser, m: Mark) Res<TypeId, AllocError>

primary_type_here = (p :: Parser, m: Mark) Res<TypeId, AllocError>

named_or_infer = (p :: Parser, m: Mark) Res<TypeId, AllocError>

token_type = (p :: Parser, kind: TypeKind, m: Mark) Res<TypeId, AllocError>

named_type = (p :: Parser, m: Mark) Res<TypeId, AllocError>

type_args* = (p :: Parser, out :: Vec<TypeId>) Res<(), AllocError>

array_type = (p :: Parser, m: Mark) Res<TypeId, AllocError>

paren_type = (p :: Parser, m: Mark) Res<TypeId, AllocError>

fn_type = (p :: Parser, m: Mark) Res<TypeId, AllocError>

named_params = (p :: Parser, ps: Vec<Param>) Res<(), AllocError>

fn_type_rest = (
    p    :: Parser,
    m    : Mark,
    tps  : Vec<TParam>,
    ps   : Vec<Param>,
    span : Span
) Res<TypeId, AllocError>

starts_type* = (p :: Parser) bool

starts_type_kind* = (kind: TokenKind) bool

poison_type* = (p :: Parser) Res<TypeId, AllocError>

add_type* = (p :: Parser, kind: TypeKind, m: Mark) Res<TypeId, AllocError>
```

#### Imports and re-exports

```zen
AllocError = std.mem

Span, Ident, no_trivia = std.ast.ast_span

TypeId = std.ast.ast_id

Type, TypeKind, Named, Union, FnType, ArrayType, Param, TParam = std.ast.ast_node

TokenKind, WILDCARD = std.parse.parse_token

Parser, Mark = std.parse.parser

expr = std.parse.parse_expr

params_list, type_params = std.parse.parse_member

ret_ahead = std.parse.parse_lookahead
```

### `src/std/parse/parser.zen`

11 declarations (types: 2, functions: 3, constants: 1, imports and re-exports: 5).

#### Types

```zen
Mark* = {
    start*: Pos,
    leading*: TriviaRun,
    bare* = (self: @Self) Mark
}

Parser* = {
    tokens: Vec<Token>,
    source*: Source,
    at* :: usize = 0,
    tree* :: Ast,
    diags* :: Vec<Diag>,
    prev_end* :: Pos = Pos(line: 1, col: 1),
    gap_line :: usize = 1,
    pending :: TriviaRun,
    depth :: usize = 0,
    run_base :: usize = 0,
    anchor :: Span,
    too_deep* :: bool = false,
    said :: bool = false,
    alloc*: Alloc,
    peek* = (self: @Self) Token
    at_text* = (self: @Self, want: str) bool
    eof_token = (self: @Self) Token
    last_token = (self: @Self) Token
    span_of* = (self: @Self, t: Token) Span
    text* = (self: @Self, t: Token) str
    peek_next* = (self: @Self) Token
    peek_n* = (self: @Self, n: usize) Token
    tokens_len* = (self: @Self) usize
    token_kind_at* = (self: @Self, k: usize) TokenKind
    at_kind* = (self: @Self, kind: TokenKind) bool
    at_eof* = (self: @Self) bool
    here_span* = (self: @Self) Span
    here* = (self: @Self) Pos
    span_from* = (self: @Self, start: Pos) Span
    open* = (self :: @Self) Mark
    ident* = (self :: @Self, message: str) Res<Ident, AllocError>
    ident_here = (self :: @Self) Res<Ident, AllocError>
    ident_missing = (self :: @Self, message: str) Res<Ident, AllocError>
    skip* = (self :: @Self) Res<(), AllocError>
    nothing* = (self: @Self) Res<(), AllocError>
    empty_span* = (self: @Self) Span
    gap_span* = (self: @Self) Span
    bump* = (self :: @Self) Res<Token, AllocError>
    drain* = (self :: @Self) Res<(), AllocError>
    token_at = (self: @Self, k: usize) Token
    keep_trivia = (self :: @Self, t: Token) Res<(), AllocError>
    blank_before = (self :: @Self, t: Token) Res<(), AllocError>
    keep_blank = (self :: @Self, t: Token) Res<(), AllocError>
    eat* = (self :: @Self, kind: TokenKind) Res<bool, AllocError>
    expect* = (self :: @Self, kind: TokenKind, message: str) Res<bool, AllocError>
    took = (self :: @Self) Res<bool, AllocError>
    missed = (self :: @Self, message: str) Res<bool, AllocError>
    expect_after* = (self :: @Self, kind: TokenKind, message: str) Res<bool, AllocError>
    missed_after = (self :: @Self, message: str) Res<bool, AllocError>
    expect_close* = (self :: @Self, kind: TokenKind, message: str, open: Span) Res<bool, AllocError>
    unclosed = (self :: @Self, message: str, open: Span) Res<bool, AllocError>
    error* = (self :: @Self, message: str) Res<(), AllocError>
    error_at* = (self :: @Self, message: str, span: Span) Res<(), AllocError>
    say = (self :: @Self, message: str, span: Span) Res<(), AllocError>
    hushed = (self: @Self) bool
    resume* = (self :: @Self) ()
    claim_leading* = (self :: @Self) TriviaRun
    claim_trailing* = (self :: @Self, end: Pos) TriviaRun
    claim_trailing_at = (self :: @Self, end: Pos) TriviaRun
    claim_rest* = (self :: @Self) TriviaRun
    claim_close* = (self :: @Self) TriviaRun
    enter* = (self :: @Self) Res<(), AllocError>
    run_from* = (self :: @Self) usize
    run_until* = (self :: @Self, was: usize) ()
    leave* = (self :: @Self) ()
    unwind* = (self :: @Self, links: usize) ()
}
```

#### Functions

```zen
Parser* = (a: Alloc, lexed: Lexed) Parser

Parser* = (a: Alloc, lexed: Lexed, tree: Ast) Parser

trivia_kind* = (self: TokenKind) TriviaKind
```

#### Constants

```zen
MAX_DEPTH*: usize = 304
```

#### Imports and re-exports

```zen
Alloc, AllocError = std.mem

Ast = std.ast.ast_arena

Span, Pos, Trivia, TriviaKind, TriviaRun, no_trivia, Ident = std.ast.ast_span

Token, TokenKind, Source, Lexed, is_trivia, text_of, empty_eof = std.parse.parse_token

Diag, diag, diag_at, truncated = std.parse.parse_diag
```

### `src/std/proc/proc.zen`

16 declarations (types: 3, enums: 1, functions: 8, imports and re-exports: 4).

#### Types

```zen
ProcOutput* = {
    code*: i32,
    out*:  String,
    err*:  String,
}

Capture = {
    code  : Ptr<i32>,
    out   : Ptr<Ptr<u8>>,
    out_n : Ptr<usize>,
    err   : Ptr<Ptr<u8>>,
    err_n : Ptr<usize>,
}

Process* = {
    run* = (self: @Self, a: Alloc, cwd: str, cmd: str) Res<ProcOutput, ProcError>
    run_argv* = (self: @Self, a: Alloc, cwd: str, argv: Vec<str>)
                Res<ProcOutput, ProcError>
    run_argv_inherit* = (self: @Self, a: Alloc, cwd: str, argv: Vec<str>)
                        Res<i32, ProcError>
}
```

#### Enums

```zen
ProcError* = SpawnFailed | WaitFailed | ReadFailed
```

#### Functions

```zen
zg_proc_run = (
    cwd      : str,
    cmd      : str,
    code_out : Ptr<i32>,
    out_buf  : Ptr<Ptr<u8>>,
    out_len  : Ptr<usize>,
    err_buf  : Ptr<Ptr<u8>>,
    err_len  : Ptr<usize>
) i32

zg_proc_run_argv = (
    cwd      : str,
    argv     : Ptr<str>,
    argc     : usize,
    code_out : Ptr<i32>,
    out_buf  : Ptr<Ptr<u8>>,
    out_len  : Ptr<usize>,
    err_buf  : Ptr<Ptr<u8>>,
    err_len  : Ptr<usize>
) i32

zg_proc_run_argv_inherit = (
    cwd      : str,
    argv     : Ptr<str>,
    argc     : usize,
    code_out : Ptr<i32>
) i32

free = (p: Ptr<()>) ()

proc_error = (rc: i32) ProcError

string_from_c = (a: Alloc, p: Ptr<u8>, n: usize) Res<String, ProcError>

capture_slots = (a: Alloc) Res<Capture, ProcError>

capture_result = (a: Alloc, slots: Capture, rc: i32)
                 Res<ProcOutput, ProcError>
```

#### Imports and re-exports

```zen
Alloc, AllocError, Ptr, null_ptr = std.mem

str, String, str_at = std.text

Vec = std.collections

Res, ok_or = std.core
```

### `src/std/std.zen`

28 declarations (imports and re-exports: 28).

#### Imports and re-exports

```zen
Res*, Ok*, Err*, None*, ok_or*, value_or*, map_err*, replace_err*, then*, ensure*, bool* = std.core

Drop*, Scope* = std.core

i8*, i16*, i32*, i64* = std.core

u8*, u16*, u32*, u64*, usize* = std.core

f32*, f64* = std.core

loop*, find*, filter*, map*, LoopHandle*, Range* = std.core

Eq*, Hash*, Hasher*, Display* = std.core

IoError*, WriteError*, Sink*, Path*, join_path*, Duration* = std.core

AllocError*, Alloc*, Arena*, Mem*, Ptr*, null_ptr* = std.mem

str*, String*, count*, replace_once*,
    parse_i32*, parse_i64*, parse_u16*, parse_usize* = std.text

Vec*, Map* = std.collections

Spec*, Item*, Options*, Args*, options*, is_flag*, is_word*, arg_at*, OPTIONS_END* = std.cli

JsonId*, Run*, Pair*, Json*, Jsons*,
    write_text*, written*, Nest*, obj*, arr*,
    JsonFault*, MAX_NESTING*, Reader*, read*,
    fine*, to_json* = std.json

Env*, Console*, Stdin*, Fs*, FsError*, fs_message*, Lock*,
    Net*, ArgError* = std.env

Threads*, Thread*, ThreadError* = std.env

ProcError*, ProcOutput*, Process* = std.proc

HttpClient*, HttpResponse*, HttpResponseMeta*, HttpError* = std.net.http

H2Client*, H2Response*, H2Error*, H2StreamError*, H2Head*, H2Chunk*,
    MAX_SEND*, h2_chunk*, post_once* =
    std.net.http2

TcpStream*, TcpError* = std.net.tcp

TlsStream*, TlsError* = std.net.tls

DnsAddr*, DnsError*, resolve* = std.net.dns

TestError*, Tester*, Bencher*, BenchStats* = std.test

BuildError*, BuildFault*, Package*, Builder*, Budget* = std.build

Os*, Arch*, Abi*, StableName*, Target*, Dep*, Exe*, Lib*, Extern*, CImport* = std.build

Test*, Bench* = std.build

Emission*, Permutation*, BuildArgs*, ProjectArgs*, BuildFlags*, BuildFlag*, BuildArgFault* = std.build

Actor*, Ref*, ActorError*, ActorStartError* = std.actor.actor_core

Context*, Receive* = std.actor.actor_context
```

### `src/std/test/test.zen`

7 declarations (types: 3, enums: 1, imports and re-exports: 3).

#### Types

```zen
Tester* = {
    env*: Env,
    alloc*: Alloc,
    expect* = (self: @Self, cond: bool) Res<(), TestError>
    expect_eq* = <T: Eq>(self: @Self, a: T, b: T) Res<(), TestError>
}

Bencher* = {
    env*: Env,
    alloc*: Alloc,
    iter* = (self: @Self, f: () ()) BenchStats
}

BenchStats* = {
    ns_op*: u64,
    allocs_op*: u64,
    bytes_op*: u64,
}
```

#### Enums

```zen
TestError* = | Failed(str)
```

#### Imports and re-exports

```zen
Alloc = std.mem

Env = std.env

str = std.text
```

### `src/std/text/text.zen`

5 declarations (imports and re-exports: 5).

#### Imports and re-exports

```zen
str*, str_at*, before*, STR_HASH_SEED*, STR_HASH_MULT*,
    contains*, count*, starts_with*, ends_with*,
    trim*, trim_start*, trim_end*, eq_ignore_case*, Split*, split* =
    std.text.text_str

String*, replace_once* = std.text.text_string

Utf8Error*, Codepoint*, Codepoints*,
    codepoints*, codepoint_at*, validate_utf8*, count_codepoints*,
    UTF8_ASCII_MAX*, UTF8_CONT_MIN*, UTF8_LEAD_MIN*, UTF8_LEAD_2_MIN*,
    UTF8_LEAD_3_MIN*, UTF8_LEAD_4_MIN*, UTF8_LEAD_MAX*, UTF8_CONT_SCALE*,
    UTF8_MIN_3*, UTF8_MIN_4*, UTF8_SURROGATE_MIN*, UTF8_SURROGATE_MAX*,
    UTF8_MAX_CODEPOINT*, UTF8_MAX_LEN*, push_utf8* = std.text.text_utf8

FmtStep*, fmt_next*, add_u64*, add_i64*, add_bool*, add_f64* = std.text.text_fmt

parse_i32*, parse_i64*, parse_u16*, parse_usize* = std.text.text_num
```

### `src/std/text/text_fmt.zen`

21 declarations (types: 1, functions: 16, imports and re-exports: 4).

#### Types

```zen
FmtStep* = {
    literal*: str,
    hole*: bool,
    name*: str,
    bad*: bool,
    next*: usize,
}
```

#### Functions

```zen
opens_hole = (f: str, i: usize) bool

opens_pair = (f: str, i: usize) bool

opens_name = (f: str, i: usize) bool

break_at = (f: str, from: usize) Res<usize>

ident_end = (f: str, from: usize) usize

fmt_next* = (f: str, from: usize) FmtStep

step_at = (f: str, from: usize, i: usize) FmtStep

step_not_hole = (f: str, from: usize, i: usize) FmtStep

step_named = (f: str, from: usize, i: usize, j: usize) FmtStep

rest_step = (f: str, from: usize) FmtStep

fmt* = (out :: Sink, fmt: str, args: ...) Res<(), WriteError>

add_u64* = (out :: Sink, v: u64) Res<(), WriteError>

add_i64* = (out :: Sink, v: i64) Res<(), WriteError>

add_digits = (out :: Sink, v: i64) Res<(), WriteError>

add_bool* = (out :: Sink, v: bool) Res<(), WriteError>

add_f64* = (out :: Sink, v: f64) Res<(), WriteError>
```

#### Imports and re-exports

```zen
str = std.text.text_str

Sink, WriteError = std.core.io

is_ident_start, is_ident_cont = std.core

digit = std.core.byte
```

### `src/std/text/text_num.zen`

5 declarations (functions: 4, imports and re-exports: 1).

#### Functions

```zen
parse_i64* = (self: str) Res<i64>

parse_usize* = (self: str) Res<usize>

parse_u16* = (self: str) Res<u16>

parse_i32* = (self: str) Res<i32>
```

#### Imports and re-exports

```zen
DIGIT_ZERO, digit_value = std.core.byte
```

### `src/std/text/text_str.zen`

27 declarations (types: 2, implementations: 4, functions: 15, constants: 2, imports and re-exports: 4).

#### Types

```zen
str* = {
    data: Ptr<u8>,
    len*: usize,
    is_empty* = (self: @Self) bool
    is_identifier* = (self: @Self) bool
    ptr* = (self: @Self) Ptr<u8>
    get* = (self: @Self, i: usize) Res<u8>
    index* = (self: @Self, i: usize) u8
    slice* = (self: @Self, from: usize, to: usize) str
    copy_into* = (self: @Self, dst: Ptr<u8>) ()
    find* = (self: @Self, needle: u8) Res<usize>
    find* = (self: @Self, needle: str) Res<usize>
    rfind* = (self: @Self, needle: u8) Res<usize>
}

Split* = {
    bytes*: str,
    sep*: u8,
    from :: usize = 0,
    done :: bool = false,
    next* = (self :: @Self) Res<str>
}
```

#### Implementations

```zen
Split.impl(Range<str>, {
    start: 0,
    end: self.bytes.len + 1,
    at ::= (self: @Self, index: usize) Res<str>
})

str.impl(Eq, {
    eq ::= (self: @Self, other: @Self) bool
})

str.impl(Hash, {
    hash ::= (self: @Self, hasher :: Hasher) u64
})

str.impl(Range<u8>, {
    start: 0,
    end: self.len,
    at ::= (self: @Self, index: usize) Res<u8>
})
```

#### Functions

```zen
str_at* = (data: Ptr<u8>, len: usize) str

contains* = (self: str, needle: u8) bool

contains* = (self: str, needle: str) bool

count* = (self: str, needle: str) usize

matches_at = (self: str, from: usize, other: str) bool

starts_with* = (self: str, head: str) bool

ends_with* = (self: str, tail: str) bool

trim* = (self: str) Res<str>

trim_start* = (self: str) Res<str>

trim_end* = (self: str) Res<str>

eq_ignore_case* = (self: str, other: str) bool

same_folded = (self: str, other: str) bool

piece_at = (s: str, sep: u8, k: usize) Res<str>

split* = (self: str, sep: u8) Split

before* = (self: str, other: str) bool
```

#### Constants

```zen
STR_HASH_SEED*: u64 = 14695981039346656037

STR_HASH_MULT*: u64 = 1099511628211
```

#### Imports and re-exports

```zen
Ptr = std.mem.mem

Eq, Hash, Hasher = std.core.core

Range, loop, to_lower = std.core.core

is_ident_start, is_ident_cont = std.core.core
```

### `src/std/text/text_string.zen`

12 declarations (types: 1, implementations: 1, functions: 4, imports and re-exports: 6).

#### Types

```zen
String* = {
    data :: Vec<u8>,
    fmt* = (self :: @Self, fmt: str, args: ...) Res<(), AllocError>
    view* = (self: @Self) str
    len* = (self: @Self) usize
    is_empty* = (self: @Self) bool
    clear* = (self :: @Self) ()
    add* = (self :: @Self, s: str) Res<(), AllocError>
    add* = (self :: @Self, b: u8) Res<(), AllocError>
    write_usize* = (self :: @Self, value: usize) Res<(), AllocError>
    write_hex_fixed* = (
        self   :: @Self,
        value  : u64,
        digits : usize
    ) Res<(), AllocError>
}
```

#### Implementations

```zen
String.impl(Sink, {
    write = (self :: @Self, bytes: str) Res<(), WriteError>
    write_byte = (self :: @Self, b: u8) Res<(), WriteError>
})
```

#### Functions

```zen
String* = (a: Alloc) Res<String, AllocError>

String* = (a: Alloc, fmt: str, args: ...) Res<String, AllocError>

c_text* = (self: str, a: Alloc) Res<Vec<u8>, AllocError>

replace_once* = (
    self        : str,
    a           : Alloc,
    needle      : str,
    replacement : str
) Res<String, AllocError>
```

#### Imports and re-exports

```zen
Vec = std.collections.collections

Alloc, AllocError = std.mem.mem

str, str_at = std.text.text_str

Sink, WriteError = std.core.io

Range = std.core.range

digit, hex_digit = std.core.byte
```

### `src/std/text/text_utf8.zen`

40 declarations (types: 2, enums: 1, functions: 17, constants: 17, imports and re-exports: 3).

#### Types

```zen
Codepoint* = {
    value*: u32,
    len*: usize,
}

Codepoints* = {
    bytes: str,
    at* :: usize,
    is_done* = (self: @Self) bool
    next* = (self :: @Self) Res<u32, Utf8Error>
}
```

#### Enums

```zen
Utf8Error* = | Invalid(usize) | InvalidCodepoint(u32)
```

#### Functions

```zen
codepoints* = (s: str) Codepoints

codepoint_at* = (s: str, at: usize) Res<Codepoint, Utf8Error>

validate_utf8* = (s: str) Res<(), Utf8Error>

count_codepoints* = (s: str) Res<usize, Utf8Error>

sequence_len = (lead: u8) usize

continuation = (s: str, at: usize) Res<u32, Utf8Error>

two_byte = (s: str, at: usize, lead: u8) Res<Codepoint, Utf8Error>

three_byte = (s: str, at: usize, lead: u8) Res<Codepoint, Utf8Error>

four_byte = (s: str, at: usize, lead: u8) Res<Codepoint, Utf8Error>

push_utf8* = (v: u32, out :: String) Res<(), Utf8Error | AllocError>

scalar = (v: u32) bool

encoded_len = (v: u32) usize

past = (v: u32, bound: u32) usize

two_wide = (v: u32, out :: String) Res<(), Utf8Error | AllocError>

three_wide = (v: u32, out :: String) Res<(), Utf8Error | AllocError>

four_wide = (v: u32, out :: String) Res<(), Utf8Error | AllocError>

narrow = (v: u32) Res<u8, Utf8Error>
```

#### Constants

```zen
UTF8_ASCII_MAX*: u8 = 128

UTF8_CONT_MIN*: u8 = 128

UTF8_LEAD_MIN*: u8 = 192

UTF8_LEAD_2_MIN*: u8 = 194

UTF8_LEAD_3_MIN*: u8 = 224

UTF8_LEAD_4_MIN*: u8 = 240

UTF8_LEAD_MAX*: u8 = 245

UTF8_CONT_SCALE*: u32 = 64

UTF8_MIN_3*: u32 = 2048

UTF8_MIN_4*: u32 = 65536

UTF8_SURROGATE_MIN*: u32 = 55296

UTF8_SURROGATE_MAX*: u32 = 57343

UTF8_MAX_CODEPOINT*: u32 = 1114111

UTF8_MAX_LEN*: usize = 4

BOM_FIRST*: u8 = 239

BOM_SECOND*: u8 = 187

BOM_THIRD*: u8 = 191
```

#### Imports and re-exports

```zen
str = std.text.text_str

String = std.text.text_string

AllocError = std.mem.mem
```

### `src/zen/zen.zen`

29 declarations (functions: 16, imports and re-exports: 13).

#### Functions

```zen
main = (env: Env) Res<i32, AllocError>

project_cli = (env: Env, a: Alloc, job: ProjectArgs, execute: bool)
              Res<i32, AllocError>

build_cli = (env: Env, a: Alloc, job: BuildArgs) Res<i32, AllocError>

later = (env: Env, alloc: Alloc, name: str) Res<i32, AllocError>

not_yet = (name: str) Res<i32, AllocError>

lsp = (env: Env, a: Alloc) Res<i32, AllocError>

paired = (env: Env, a: Alloc, from: str, to: str) Res<i32, AllocError>

arg = (env: Env, i: usize) str

file_arg = (env: Env, i: usize) str

lsp_usage = () Res<i32, AllocError>

answer = (env: Env, a: Alloc, from: str, to: str) Res<i32, AllocError>

replies = (env: Env, a: Alloc, input: str, to: str) Res<i32, AllocError>

unreadable = (path: str, e: FsError) Res<i32, AllocError>

unwritable = (path: str, e: FsError) Res<i32, AllocError>

usage = (word: str) Res<i32, AllocError>

missing = (flag: str) Res<i32, AllocError>
```

#### Imports and re-exports

```zen
Alloc, AllocError = std.mem

str, String = std.text

FsError = std.env

BuildArgs, ProjectArgs = std.build

Cli*, FmtJob*, cli*, USAGE* = zen.zen_cli

Build* = zen.zen_build

fs_message* = std.env

Unit* = zen.zen_path

std_root_for = zen.zen_path

build* = zen.zen_run

project = zen.zen_project

format* = zen.zen_fmt

Server, serve, serve_stdio = lsp
```

### `src/zen/zen_build.zen`

25 declarations (types: 1, functions: 1, imports and re-exports: 23).

#### Types

```zen
Build* = {
    env*: Env,
    alloc*: Alloc,
    root*: str,
    std_root* :: str = "",
    faults* :: usize = 0,
    units* :: usize = 0,
    ffi :: bool = false,
    enable_ffi* = (self :: @Self) ()
    diags* :: Vec<Diag>,
    permute* :: Permutation = Permutation.Natural,
    walk_order* = (self :: @Self, order: Permutation) ()
    set_std_root* = (self :: @Self, path: str) ()
    std_base = (self: @Self) str
    root_for_path = (self: @Self, path: str) str
    overlay* :: Map<str, str>,
    speaking* :: bool = true,
    entry_rel* :: str = "",
    tree* :: Ast,
    walk* = (self :: @Self, entry: Unit) Res<(), AllocError>
    seed_prelude = (self :: @Self, seen :: Vec<Unit>) Res<(), AllocError>
    seed_prelude_folder = (self :: @Self, seen :: Vec<Unit>)
                          Res<(), AllocError>
    dotted_path = (self: @Self, dotted: str, folder: bool)
                  Res<str, AllocError>
    front = (self :: @Self, u: Unit, seen :: Vec<Unit>) Res<(), AllocError>
    read = (self :: @Self, path: str) Res<str>
    read_disk = (self :: @Self, path: str) Res<str>
    fs_fault = (self :: @Self, path: str, e: FsError) Res<str>
    report = (self :: @Self, d: Diag) Res<(), AllocError>
    lex_it = (self :: @Self, u: Unit, text: str, seen :: Vec<Unit>)
             Res<(), AllocError>
    lex_faults = (self :: @Self, lexed: Lexed) Res<(), AllocError>
    parse_it = (self :: @Self, u: Unit, lexed: Lexed, seen :: Vec<Unit>)
               Res<(), AllocError>
    imports_of = (self :: @Self, m: Module, seen :: Vec<Unit>)
                 Res<(), AllocError>
    enqueue = (self :: @Self, q: QualifiedName, seen :: Vec<Unit>)
              Res<(), AllocError>
    import_root = (self :: @Self, q: QualifiedName) str
    import_path = (self :: @Self, flat: str, folder: str) Res<str>
    import_path_disk = (self :: @Self, flat: str, folder: str) Res<str>
    import_path_folder = (self :: @Self, folder: str) Res<str>
    missing_import = (self :: @Self, q: QualifiedName, flat: str, folder: str)
                     Res<(), AllocError>
    folder_root = (self :: @Self, path: str, seen :: Vec<Unit>)
                  Res<(), AllocError>
    queue_folder_root = (self :: @Self, dir: str, path: str, seen :: Vec<Unit>)
                        Res<(), AllocError>
    queue = (self :: @Self, path: str, seen :: Vec<Unit>)
            Res<(), AllocError>
    queue_fresh = (self :: @Self, path: str, seen :: Vec<Unit>)
                  Res<(), AllocError>
    alias_of = (self :: @Self, al: Alias, seen :: Vec<Unit>)
               Res<(), AllocError>
    alias_named = (self :: @Self, n: Named, seen :: Vec<Unit>)
                  Res<(), AllocError>
    probe = (self :: @Self, name: str, seen :: Vec<Unit>)
            Res<(), AllocError>
    whole* = (self :: @Self, named: str, docs: Map<str, str>)
             Res<Checker, AllocError>
    checked* = (self :: @Self) Res<Checker, AllocError>
    back_end* = (self :: @Self, job: BuildArgs) Res<(), AllocError>
    check_tree = (self :: @Self, job: BuildArgs) Res<(), AllocError>
    main_check = (self :: @Self, c :: Checker, job: BuildArgs)
                 Res<usize, AllocError>
    missing_main = (self :: @Self, c :: Checker, job: BuildArgs)
                   Res<usize, AllocError>
    root_declares_main = (self :: @Self, c :: Checker) Res<usize, AllocError>
    no_main = (self :: @Self) Res<usize, AllocError>
    emit = (self :: @Self, c :: Checker, job: BuildArgs) Res<(), AllocError>
    emit_one = (self :: @Self, c :: Checker, job: BuildArgs) Res<(), AllocError>
    emit_many = (self :: @Self, c :: Checker, job: BuildArgs, dir: str)
                Res<(), AllocError>
    deliver = (self :: @Self, job: BuildArgs, out: Emit) Res<(), AllocError>
    write_out = (self :: @Self, path: str, out: Emit) Res<(), AllocError>
    write_failed = (self :: @Self, path: str, e: FsError) Res<(), AllocError>
    tally* = (self: @Self) ()
    diag_count* = (self: @Self) usize
    diag_at* = (self: @Self, i: usize) Res<Diag>
    code* = (self: @Self) i32
}
```

#### Functions

```zen
Build* = (a: Alloc, env: Env, root: str) Build
```

#### Imports and re-exports

```zen
Alloc, AllocError = std.mem

str, String = std.text

Vec, Map = std.collections

Range, Path = std.core

FsError, fs_message = std.env

Ast = std.ast.ast_arena

Module, Alias, Named = std.ast.ast_node

Pos, Span, QualifiedName = std.ast.ast_span

message = std.lex.lex

Diag, diag, say = std.parse.parse_diag

scan, Source, Lexed = std.lex.lex

Parser, module = std.parse.parse

Checker, check_all = sema.sema

PRELUDE, last_segment = sema.sema

check_module_graph = sema.sema

Def = sema.sema

Emit, CBackend, emit_program = gen.gen

BuildArgs, Emission, Permutation = std.build

slash_for = zen.zen_path

unit_at, candidate, joined, relative_to = zen.zen_path

ENTRY, entry_of = zen.zen_path

Unit* = zen.zen_path

emit_units, write_symbol_map = zen.zen_write
```

### `src/zen/zen_build_plan.zen`

25 declarations (types: 7, enums: 3, functions: 6, imports and re-exports: 9).

#### Types

```zen
CImportNode* = {
    name*: str,
    spec*: CImport,
    dep*: Dep,
}

LibNode* = {
    name*: str,
    spec*: Lib,
    dep*: Dep,
}

ExternNode* = {
    name*: str,
    spec*: Extern,
    dep*: Dep,
}

ExeNode* = {
    name*: str,
    spec*: Exe,
}

BuildPlan* = {
    target*: Target,
    imports* :: Vec<CImportNode>,
    libs* :: Vec<LibNode>,
    externs* :: Vec<ExternNode>,
    exes* :: Vec<ExeNode>,
}

Local = {
    name: str,
    value: Value,
}

Executor = {
    alloc: Alloc,
    tree: Ast,
    builder: str,
    locals :: Vec<Local>,
    plan :: BuildPlan,
    block = (self :: @Self, body: Block) Res<(), PlanError>
    bind = (self :: @Self, b: Bind) Res<(), PlanError>
    eval = (self :: @Self, id: ExprId) Res<Value, PlanError>
    eval_try = (self :: @Self, t: Try) Res<Value, PlanError>
    text = (self: @Self, raw: str, at: Span) Res<Value, PlanError>
    array = (self :: @Self, ids: Vec<ExprId>, at: Span)
            Res<Value, PlanError>
    array_nonempty = (self :: @Self, ids: Vec<ExprId>, at: Span)
                     Res<Value, PlanError>
    call = (self :: @Self, id: ExprId, c: Call, at: Span)
           Res<Value, PlanError>
    free_call = (self :: @Self, name: str, c: Call, at: Span)
                Res<Value, PlanError>
    path_call = (self :: @Self, c: Call, at: Span)
                Res<Value, PlanError>
    path_arg = (self :: @Self, c: Call, i: usize, at: Span)
               Res<Value, PlanError>
    access_call = (self :: @Self, id: ExprId, c: Call, a: Access, at: Span)
                  Res<Value, PlanError>
    value_call = (self :: @Self, c: Call, a: Access, at: Span)
                 Res<Value, PlanError>
    local_add = (self :: @Self, c: Call, a: Access, at: Span)
                Res<Value, PlanError>
    add_dep_local = (self :: @Self, name: str, c: Call, at: Span)
                    Res<Value, PlanError>
    push_dep = (self :: @Self, name: str, dep: Dep, at: Span)
               Res<Value, PlanError>
    replace_local = (self :: @Self, i: usize, name: str, value: Value)
                    Res<Value, PlanError>
    builder_access = (self: @Self, a: Access) bool
    builder_call = (self :: @Self, name: str, c: Call, at: Span)
                   Res<Value, PlanError>
    add_import = (self :: @Self, c: Call, at: Span)
                 Res<Value, PlanError>
    add_lib = (self :: @Self, c: Call, at: Span) Res<Value, PlanError>
    add_extern = (self :: @Self, c: Call, at: Span)
                 Res<Value, PlanError>
    add_exe = (self :: @Self, c: Call, at: Span) Res<Value, PlanError>
    unique = (self: @Self, name: str) Res<(), PlanError>
    name_arg = (self :: @Self, c: Call, at: Span) Res<str, PlanError>
    arg = (self: @Self, c: Call, i: usize, at: Span)
          Res<ExprId, PlanError>
    one_arg = (self: @Self, c: Call, at: Span) Res<ExprId, PlanError>
    record = (self: @Self, id: ExprId) Res<Record, PlanError>
    field = (self: @Self, r: Record, name: str) Res<ExprId, PlanError>
    texts_field = (self :: @Self, r: Record, name: str)
                  Res<Vec<str>, PlanError>
    deps_field = (self :: @Self, r: Record, name: str)
                 Res<Vec<Dep>, PlanError>
    path_field = (self :: @Self, r: Record, name: str)
                 Res<Path, PlanError>
    target_field = (self :: @Self, r: Record, name: str)
                   Res<Target, PlanError>
    optional_path_field = (self :: @Self, r: Record, name: str) Res<Path>
    optional_text_field = (
        self    :: @Self,
        r       : Record,
        name    : str,
        fallback: str
    ) str
    optional_bool_field = (
        self    :: @Self,
        r       : Record,
        name    : str,
        fallback: bool
    ) bool
    local = (self: @Self, name: str, at: Span) Res<Value, PlanError>
    has_local = (self: @Self, name: str) bool
    local_index = (self: @Self, name: str) Res<usize>
}
```

#### Enums

```zen
PlanFault* = MissingBuild(str)
    | CheckedFaults
    | MissingField(Span)
    | UnknownName(Span)
    | DuplicateTarget(str)
    | Unsupported(Span)

PlanError* = OutOfMemory | Refused(PlanFault)

Value = UnitValue
    | TextValue(str)
    | BoolValue(bool)
    | PathValue(Path)
    | TargetValue(Target)
    | DepValue(Dep)
    | EmptyList
    | TextList(Vec<str>)
    | DepList(Vec<Dep>)
    | PathOption(Res<Path>)
```

#### Functions

```zen
plan* = (a: Alloc, tree: Ast, check: Checker, target: Target)
        Res<BuildPlan, PlanError>

plan_function = (
    a      : Alloc,
    tree   : Ast,
    target : Target,
    f      : Function
) Res<BuildPlan, PlanError>

execute_function = (
    a       : Alloc,
    tree    : Ast,
    target  : Target,
    builder : str,
    body    : Block
) Res<BuildPlan, PlanError>

failed_value = (fault: PlanFault) Res<Value, PlanError>

build_function = (tree: Ast) Res<Function, PlanError>

function_in = (tree: Ast, module: usize) Res<Function, PlanError>
```

#### Imports and re-exports

```zen
Alloc, AllocError = std.mem

str = std.text

Vec = std.collections

Path = std.core

Ast, ExprId, Expr, Call, Access, Record, Block, Function, Span, Try = std.ast

nowhere = std.ast

Stmt, Bind, Member, Field = std.ast

Checker = sema.sema

CImport, Lib, Extern, Exe, Dep, Target = std.build
```

### `src/zen/zen_c_import.zen`

11 declarations (types: 2, functions: 4, imports and re-exports: 5).

#### Types

```zen
CImportRequest* = {
    spec*: CImport,
    identity*: String,
    attach_module* = (
        self : @Self,
        a    : Alloc,
        node : Module,
        tree :: Ast,
    ) Res<CImportModule, AllocError>
}

CImportModule* = {
    module*: usize,
    binding*: CBindingId,
}
```

#### Functions

```zen
request* = (a: Alloc, spec: CImport) Res<CImportRequest, AllocError>

target = (out :: String, selected: Target) Res<(), AllocError>

add_piece = (out :: String, value: str) Res<(), AllocError>

add_list = (out :: String, name: str, values: Vec<str>)
           Res<(), AllocError>
```

#### Imports and re-exports

```zen
Alloc, AllocError = std.mem

str, String = std.text

Vec = std.collections

Target, CImport = std.build

Ast, Module, CHeader, CTypeBinding, CBinding, CBindingId = std.ast
```

### `src/zen/zen_c_translate.zen`

35 declarations (types: 4, enums: 1, functions: 20, imports and re-exports: 10).

#### Types

```zen
ClangExit* = {
    code*: i32,
    message*: str,
}

CModule* = {
    source*: String,
    declarations*: usize,
}

CTranslation* = {
    module*: CModule,
    identity*: String,
}

CAttachedTranslation* = {
    source*: String,
    attached*: CImportModule,
    identity*: String,
    declarations*: usize,
}
```

#### Enums

```zen
CTranslateFault* = NoMemory
    | Process(ProcError)
    | ClangFailed(ClangExit)
    | OneHeaderRequired
    | UnsupportedTarget
    | UnsafeArgument(str)
    | InvalidAst(str)
    | UnsupportedFunction(str)
    | UnsupportedType(str)
    | IdentityMismatch
    | GeneratedLex(usize)
    | GeneratedParse(usize)
```

#### Functions

```zen
attach* = (
    a           : Alloc,
    name        : str,
    request     : CImportRequest,
    translation : CTranslation,
    tree        :: Ast,
) Res<CAttachedTranslation, CTranslateFault>

translate* = (
    env     : Env,
    a       : Alloc,
    cwd     : str,
    request : CImportRequest
) Res<CTranslation, CTranslateFault>

translate_ast* = (a: Alloc, text: str) Res<CModule, CTranslateFault>

clang_command = (a: Alloc, clang: str, spec: CImport)
                Res<String, CTranslateFault>

shell_word = (out :: String, word: str) Res<(), CTranslateFault>

emit_function = (tree: Jsons, node: JsonId, out :: String)
                Res<(), CTranslateFault>

forbidden_function = (tree: Jsons, node: JsonId, name: str)
                     Res<(), CTranslateFault>

no_body = (tree: Jsons, node: JsonId, name: str)
          Res<(), CTranslateFault>

emit_params = (tree: Jsons, node: JsonId, out :: String)
              Res<(), CTranslateFault>

type_name = (tree: Jsons, node: JsonId) Res<str, CTranslateFault>

zen_type = (c: str, allow_void: bool) Res<str, CTranslateFault>

direct = (tree: Jsons, node: JsonId) bool

array = (tree: Jsons, id: JsonId, where: str) Res<Run, CTranslateFault>

item = (tree: Jsons, id: JsonId, i: usize) Res<JsonId, CTranslateFault>

field = (tree: Jsons, id: JsonId, name: str)
        Res<JsonId, CTranslateFault>

optional_text = (tree: Jsons, id: JsonId, name: str) Res<str>

text_field = (tree: Jsons, id: JsonId, name: str)
             Res<str, CTranslateFault>

text_field_in = (tree: Jsons, id: JsonId, owner: str, name: str)
                Res<str, CTranslateFault>

text_value = (tree: Jsons, id: JsonId, name: str)
             Res<str, CTranslateFault>

json_read = (a: Alloc, tree :: Jsons, text: str)
            Res<JsonId, CTranslateFault>
```

#### Imports and re-exports

```zen
Alloc, AllocError = std.mem

str, String = std.text

Vec = std.collections

Json, JsonId, Jsons, Run, read = std.json

ProcError = std.proc

CImport = std.build

Ast, Module = std.ast

Source, Lexed, scan, is_zen_name = std.lex

Parser = std.parse

CImportRequest, CImportModule = zen.zen_c_import
```

### `src/zen/zen_cli.zen`

30 declarations (types: 1, enums: 2, functions: 13, constants: 6, imports and re-exports: 8).

#### Types

```zen
FmtJob* = {
    argv*: Vec<str>,
    check*: bool,
    paths* = (self: @Self, a: Alloc) Res<Vec<str>, AllocError>
}
```

#### Enums

```zen
Cli* = Build(BuildArgs)
     | Project(ProjectArgs)
     | Run(ProjectArgs)
     | Fmt(FmtJob)
     | Later(str)
     | Usage(str)
     | Missing(str)

FmtFlag = | Check
```

#### Functions

```zen
cli* = (env: Env, argv: Vec<str>) Res<Cli, AllocError>

command = (env: Env, a: Alloc, argv: Vec<str>, name: str)
          Res<Cli, AllocError>

not_build = (a: Alloc, argv: Vec<str>, name: str) Res<Cli, AllocError>

not_written = (name: str) Cli

is_later = (name: str) bool

fmt_of = (a: Alloc, argv: Vec<str>) Res<Cli, AllocError>

fmt_options = (a: Alloc) Res<Options<FmtFlag>, AllocError>

word_count = (word: str) usize

fmt_verdict = (argv: Vec<str>, check: bool, bad: str, words: usize) Cli

job_of = (env: Env, a: Alloc, argv: Vec<str>) Res<Cli, AllocError>

project_of = (env: Env, a: Alloc, argv: Vec<str>, run: bool)
             Res<Cli, AllocError>

project_marker = (env: Env, a: Alloc, root: str) bool

verdict = (args: BuildFlags, bad: str) Cli
```

#### Constants

```zen
ARGS*: usize = 2

USAGE*: str = "usage: zen build [<project-or-target>]\n       zen run [<project-or-target>] [-- <args>...]\n       zen build <root> [--entry <file>] [--std <path>] [--ffi] [--symbol-map <file>] --emit-c -o <file.c>\n       zen build <root> [--entry <file>] [--std <path>] [--ffi] [--symbol-map <file>] --emit-c-dir <dir>\n       zen fmt [--check] <file.zen>..."

COMMAND_FMT: str = "fmt"

COMMAND_TEST: str = "test"

COMMAND_LSP: str = "lsp"

FLAG_FMT_CHECK: str = "--check"
```

#### Imports and re-exports

```zen
Alloc, AllocError = std.mem

str = std.text

Vec = std.collections

Range = std.core

Env = std.env

BuildArgs, ProjectArgs, BuildFlags, build_options = std.build

FLAG_EMIT_C, ZEN_STD_ENV = std.build

Options, options, is_word, arg_at, OPTIONS_END = std.cli
```

### `src/zen/zen_fmt.zen`

9 declarations (types: 1, enums: 1, functions: 1, imports and re-exports: 6).

#### Types

```zen
Fmt = {
    env: Env,
    alloc: Alloc,
    check: bool,
    faults :: usize = 0,
    unformatted :: usize = 0,
    one = (self :: @Self, path: str) Res<(), AllocError>
    route = (self :: @Self, path: str) Res<Outcome, AllocError>
    folder = (self :: @Self, path: str) Res<Outcome, AllocError>
    bytes_of = (self :: @Self, path: str) Res<Outcome, AllocError>
    unreadable = (self :: @Self, path: str, e: FsError) Res<Outcome, AllocError>
    scan_it = (self :: @Self, path: str, text: String) Res<Outcome, AllocError>
    lex_diags = (self :: @Self, lexed: Lexed) Res<Outcome, AllocError>
    print_it = (self :: @Self, path: str, text: String, lexed: Lexed)
               Res<Outcome, AllocError>
    syntax_diags = (self :: @Self, out: Render) Res<Outcome, AllocError>
    settled = (self :: @Self, path: str, text: String, out: Render)
              Res<Outcome, AllocError>
    unfaithful = (self :: @Self, path: str) Res<Outcome, AllocError>
    same_or_not = (self :: @Self, path: str, text: String, out: Render)
                  Res<Outcome, AllocError>
    change = (self :: @Self, path: str, out: Render) Res<Outcome, AllocError>
    name_it = (self :: @Self, path: str) Res<Outcome, AllocError>
    write_it = (self :: @Self, path: str, out: Render) Res<Outcome, AllocError>
    verdict = (self: @Self, files: usize) Res<i32, AllocError>
}
```

#### Enums

```zen
Outcome = Same | Wrote | Differs | Failed
```

#### Functions

```zen
format* = (env: Env, alloc: Alloc, job: FmtJob) Res<i32, AllocError>
```

#### Imports and re-exports

```zen
Alloc, AllocError = std.mem

str, String = std.text

FsError, fs_message = std.env

scan, Source, Lexed, message = std.lex.lex

Render, render = fmt.fmt

FmtJob = zen.zen_cli
```

### `src/zen/zen_path.zen`

29 declarations (types: 1, functions: 20, constants: 2, imports and re-exports: 6).

#### Types

```zen
Unit* = {
    name*: str,
    path*: str,
    rel*:  str,
}
```

#### Functions

```zen
module_name* = (a: Alloc, root: str, path: str) Res<str, AllocError>

std_root_for* = (env: Env, a: Alloc) str

std_root_beside_program = (env: Env, a: Alloc) str

root_for* = (env: Env, a: Alloc, floor: str, path: str) str

source_root = (a: Alloc, project: str, path: str) str

holds_its_own_name = (env: Env, a: Alloc, dir: str) bool

holds_build_zen = (env: Env, a: Alloc, dir: str) bool

relative_to* = (root: str, path: str) str

under = (root: str, path: str) bool

dot_for = (b: u8) u8

slash_for* = (b: u8) u8

last_of* = (q: QualifiedName) str

unit_at* = (a: Alloc, root: str, path: str) Res<Unit, AllocError>

candidate* = (env: Env, a: Alloc, root: str, name: str) Res<Unit, AllocError>

entry_of* = (env: Env, a: Alloc, root: str, named: str)
            Res<Unit, AllocError>

entry_named = (env: Env, a: Alloc, root: str, named: str)
              Res<Unit, AllocError>

entry_probed = (env: Env, a: Alloc, root: str) Res<Unit, AllocError>

entry_after_main = (env: Env, a: Alloc, root: str) Res<Unit, AllocError>

file_of* = (env: Env, a: Alloc, root: str, q: QualifiedName)
           Res<str, AllocError>

joined* = (a: Alloc, root: str, q: QualifiedName, folder: bool)
          Res<str, AllocError>
```

#### Constants

```zen
EXT_BYTES : usize = 4

ENTRY*: str = "main"
```

#### Imports and re-exports

```zen
Alloc, AllocError = std.mem

str, String = std.text

Range, Path = std.core

join_path = std.core.path

QualifiedName = std.ast.ast_span

ZEN_STD_ENV = std.build
```

### `src/zen/zen_project.zen`

27 declarations (functions: 18, imports and re-exports: 9).

#### Functions

```zen
project* = (env: Env, a: Alloc, job: ProjectArgs, execute: bool)
           Res<i32, AllocError>

project_present = (env: Env, a: Alloc, job: ProjectArgs, execute: bool)
                  Res<i32, AllocError>

host_target = () Target

execute_plan = (
    env     : Env,
    a       : Alloc,
    job     : ProjectArgs,
    planned : BuildPlan,
    execute : bool
) Res<i32, AllocError>

select_exe = (planned: BuildPlan, named: str, execute: bool)
             Res<Res<ExeNode>, str>

build_selected = (
    env      : Env,
    a        : Alloc,
    job      : ProjectArgs,
    planned  : BuildPlan,
    selected : Res<ExeNode>
) Res<i32, AllocError>

build_and_run = (
    env      : Env,
    a        : Alloc,
    job      : ProjectArgs,
    planned  : BuildPlan,
    selected : Res<ExeNode>
) Res<i32, AllocError>

build_exe = (
    env     : Env,
    a       : Alloc,
    job     : ProjectArgs,
    planned : BuildPlan,
    exe     : ExeNode
) Res<Res<String>, AllocError>

compile_exe = (
    env       : Env,
    a         : Alloc,
    job       : ProjectArgs,
    exe       : ExeNode,
    generated : str
) Res<bool, AllocError>

link_exe = (
    env       : Env,
    a         : Alloc,
    job       : ProjectArgs,
    planned   : BuildPlan,
    deps      : Vec<Dep>,
    optimize  : str,
    strip     : bool,
    generated : str,
    output    : str
)
            Res<bool, AllocError>

add_dep = (
    a       : Alloc,
    root    : str,
    planned : BuildPlan,
    name    : str,
    argv    :: Vec<str>
) Res<(), AllocError>

add_link_options = (
    a     : Alloc,
    root  : str,
    paths : Vec<str>,
    libs  : Vec<str>,
    argv  :: Vec<str>
) Res<(), AllocError>

add_std_floors = (
    env       : Env,
    a         : Alloc,
    std_root  : str,
    generated : str,
    argv      :: Vec<str>
) Res<(), AllocError>

run_captured = (env: Env, a: Alloc, argv: Vec<str>)
               Res<bool, AllocError>

ensure_parent = (env: Env, a: Alloc, path: str) Res<bool, AllocError>

run_program = (env: Env, a: Alloc, job: ProjectArgs, program: str)
              Res<i32, AllocError>

output_path = (
    a      : Alloc,
    root   : str,
    target : Target,
    name   : str,
    chosen : Res<Path>
) Res<String, AllocError>

project_path = (a: Alloc, root: str, path: str) Res<String, AllocError>
```

#### Imports and re-exports

```zen
Alloc, AllocError = std.mem

str, String = std.text

Path, Range, join_path = std.core

Map, Vec = std.collections

BuildArgs, ProjectArgs, Emission, Target, Os, Arch, Abi, Dep = std.build

Build = zen.zen_build

run_once = zen.zen_run

entry_of = zen.zen_path

BuildPlan, ExeNode, plan = zen.zen_build_plan
```

### `src/zen/zen_run.zen`

14 declarations (functions: 8, imports and re-exports: 6).

#### Functions

```zen
build* = (env: Env, a: Alloc, job: BuildArgs) Res<i32, AllocError>

run_once* = (env: Env, a: Alloc, job: BuildArgs) Res<i32, AllocError>

at_least_one = (n: usize) usize

job_for = (a: Alloc, job: BuildArgs, i: usize) Res<BuildArgs, AllocError>

numbered = (a: Alloc, job: BuildArgs, i: usize) Res<BuildArgs, AllocError>

numbered_emission = (a: Alloc, emission: Emission, i: usize)
                    Res<Emission, AllocError>

numbered_path = (a: Alloc, path: str, i: usize) Res<String, AllocError>

max_code = (l: i32, r: i32) i32
```

#### Imports and re-exports

```zen
Alloc, AllocError = std.mem

String = std.text

Range = std.core

BuildArgs, Emission = std.build

Build = zen.zen_build

entry_of = zen.zen_path
```

### `src/zen/zen_write.zen`

18 declarations (functions: 9, imports and re-exports: 9).

#### Functions

```zen
emit_units* = (
    a          : Alloc,
    env        : Env,
    tree       : Ast,
    c          :: Checker,
    dir        : str,
    ffi        : bool,
    symbol_map : str
)
              Res<usize, AllocError>

write_units = (
    a          : Alloc,
    env        : Env,
    tree       : Ast,
    be         :: CBackend,
    dir        : str,
    hdr        : Emit,
    symbol_map : str
) Res<usize, AllocError>

write_symbol_map* = (a: Alloc, env: Env, be :: CBackend, path: str)
                    Res<usize, AllocError>

write_symbol_map_at = (a: Alloc, env: Env, be :: CBackend, path: str)
                      Res<usize, AllocError>

write_unit = (
    env  : Env,
    tree : Ast,
    be   :: CBackend,
    dir  : str,
    seq  : Vec<usize>,
    u    : usize
) Res<usize, AllocError>

write_unit_at = (
    env  : Env,
    tree : Ast,
    be   :: CBackend,
    dir  : str,
    seq  : Vec<usize>,
    u    : usize
) Res<usize, AllocError>

unit_file* = (tree: Ast, u: usize, out :: String) Res<(), AllocError>

write_at = (a: Alloc, env: Env, dir: str, name: str, bytes: str)
           Res<usize, AllocError>

unit_write_failed = (path: str, e: FsError) Res<usize, AllocError>
```

#### Imports and re-exports

```zen
Alloc, AllocError = std.mem

str, String = std.text

Vec = std.collections

Range = std.core

FsError, fs_message = std.env

Ast = std.ast.ast_arena

Checker = sema.sema

Emit, CBackend, order, render_symbol_map = gen.gen

lower_program, emit_header, emit_unit, unit_used = gen.gen
```
