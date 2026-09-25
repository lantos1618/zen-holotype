# Working on Zen

For the active parallel correctness sprint, read `docs/SPRINT_STAGEBOOK.md` and
resume only from its current checkpoint. Never reset, stash, or overwrite
pre-existing uncommitted work.

Read `docs/STYLE.md` before editing Zen source. `docs/DESIGN.md` specifies the
language; `docs/ERGONOMICS_PLAN.md` distinguishes implemented APIs from the
remaining ergonomic design. Follow the user's current instructions when they
change the intended design.

Use caller-chosen allocation, borrowed str views, meaningful returned values,
and cohesive receiver operations. Keep efficient shared-output append paths.
Do not introduce synonymous traversal APIs: loop overloads express the needed
callback shape. Do not invent defaults to bypass required initialization or
claim unsupported ownership guarantees.

Preserve existing work. Give parallel agents disjoint file ownership. Batch
related source edits, finish formatting before freezing the tree for an
integration test run, and regenerate the seed at integration rather than after
every helper change. Use `make check` for cached development checks, with
`FILTER` for a focused selection. Use `make verify` for fresh aggregate
verification; when regenerating the seed, use one `make -j1 seed verify`
invocation to share the build. Report any checks that remain incomplete.
Do not claim a numerical ergonomics target is
achieved merely because automated checks pass.

Generate source-health reports, signature inventories, round snapshots,
external reviews, and source context packs only in ignored
`build/source_health/`; do not commit generated review artifacts. The tracked
copies in `docs/` are historical snapshots. Keep durable decisions in maintained
documentation rather than refreshing those snapshots.
