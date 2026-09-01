# Round 04 disposition

Gemini 3.7 Flash judged the fourth delta a genuine improvement and confirmed
that `LoopSite`, `RangeWalk`, `CallArgs`, and the earlier phase records are
domain owners rather than metric-oriented parameter bags.

## Bug findings

- The `gen_c_json.json_raw` control-byte claim is rejected for the current
  call graph. Its inputs are fixed JSON punctuation and Zen field identifiers,
  not user text. The stored `raw.len` is the runtime byte length; extra
  backslashes in C source spelling must not increase it.
- `Decoder.phase` is private and every call is dominated by a non-empty frame
  check. `set_phase` is reached only while parsing an object/array or finishing
  a value whose frame is still present. The unsigned subtraction is worth an
  internal invariant API in a later JSON pass, but no reachable underflow was
  found.
- `lsp_def.called_decl` was a real avoidable full scan after a hit, fixed by
  `d664dd8e4`. It still has linear worst-case lookup because the AST stores no
  parent index. A reverse call index is a future performance feature, not a
  correctness repair; expression IDs are tree-owned and cannot have multiple
  call parents.

## Next ranked work

The next independent lanes are `JsonLower` in `gen_c_json`,
`TryPropagation` in `gen_c_try`, match-coverage ownership in `sema_match`, an
ephemeral diagnostic `WorkspaceTurn`, and settled method-call ownership in
`gen_c_member`. These remain recommendations rather than an automatic fifth
wave.

The one negative metric is three additional same-folder aliases. They came
from explicit JSON grammar sharing and should be checked for re-export
necessity in the next round rather than hidden to improve the count.
