# Documentation map

Start with the five documents linked from the repository README. They define
the language, implementation stages, source style, and verification rules.

## Design references

- `design_fmt.md`, `design_json.md`, `design_lsp.md`, `design_meta.md`, and
  `design_vararg.md` record feature-specific decisions and remaining gaps.
- `QUALITY_PLAN.md` maps the path to one authoritative release gate in proposed
  builder-language terms, with a red-capable exit for every build card.
- `GEN_C_SHAPE.md` defines the current compiler-structure migration.
- `BACKENDS.md` describes supported generator selection and the generation/driver boundary.
- `SOURCE_OWNERSHIP_AUDIT.md` records the ownership decisions behind that
  migration.

- `BUILD_ITERATION.md` documents incremental builds and the fresh bootstrap.
- `PARALLEL_WORK.md` covers isolated build lanes and concurrent test shards.
- `PROFILE_REVIEW.md` records flame/profile evidence and the resulting optimizations.
- `ERGONOMICS_PLAN.md` outlines value-returning APIs, allocator lifetimes, and the path to simpler everyday Zen.
- `TEST_ITERATION.md` explains test timing reports and shared import discovery.
- `ARCHITECTURE.md` maps source ownership, compiler flow, capability boundaries, and tests.
- `GENERATED_FILES.md` identifies generated artifacts and disposable build cleanup.
- `REFACTOR_REVIEW.md` records the current structural review and measured changes.
- `TEST_REVIEW.md` maps consolidated smoke tests to their retained coverage.
- [USAGE_REPORT.md](USAGE_REPORT.md) describes the Zen tool for checked call
  evidence and source review packs captured from the same compilation input.

## Generated review artifacts

- `build/source_health/ZEN_SIGNATURES.md` is regenerated from every Zen source
  declaration by `scripts/zen_signature_inventory.py`.
- `build/source_health/SOURCE_HEALTH.md`, round JSON snapshots, external reviews,
  and source context packs are local outputs of the source-health scripts.
- `SOURCE_HEALTH_JUDGE.md` is the prompt contract for that external review.

Output paths above are relative to the repository root. `build/` is ignored:
generate these artifacts locally and do not commit them. The tracked
`docs/SOURCE_HEALTH.md`, `docs/ZEN_SIGNATURES.md`, and `docs/source_health/`
files remain historical snapshots; the scripts no longer update them by default.
Keep durable review decisions in maintained documentation. Regenerate measured
content instead of editing it by hand.

Generate an inventory and a local round, choosing a new round label:

```sh
python3 scripts/zen_signature_inventory.py
python3 scripts/zen_source_health.py --label round-NN --revision working-tree
python3 scripts/zen_review_pack.py --label round-NN
```

Each command accepts `--check` to check existing outputs. External review
remains a separate, explicit `zen_source_judge.py` invocation.

Historical bootstrap bug ledgers and agent-run transcripts are intentionally
not kept here. Once their reproducers are corpus tests, the tests are the
maintained record and git history is the archive.
