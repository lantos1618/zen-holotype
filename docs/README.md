# Documentation map

Start with the five documents linked from the repository README. They define
the language, implementation stages, source style, and verification rules.

## Design references

- `design_fmt.md`, `design_json.md`, `design_lsp.md`, `design_meta.md`, and
  `design_vararg.md` record feature-specific decisions and remaining gaps.
- `QUALITY_PLAN.md` maps the path to one authoritative release gate in proposed
  builder-language terms, with a red-capable exit for every build card.
- `GEN_C_SHAPE.md` defines the current compiler-structure migration.
- `SOURCE_OWNERSHIP_AUDIT.md` records the ownership decisions behind that
  migration.

## Generated review artifacts

- `ZEN_SIGNATURES.md` is regenerated from every Zen source declaration by
  `scripts/zen_signature_inventory.py`.
- `SOURCE_HEALTH.md` and `source_health/` retain comparable metrics and the
  external review for each cleanup round.
- `SOURCE_HEALTH_JUDGE.md` is the prompt contract for that external review.

These files are evidence, not language specification. Regenerate them instead
of editing their measured content by hand.

Historical bootstrap bug ledgers and agent-run transcripts are intentionally
not kept here. Once their reproducers are corpus tests, the tests are the
maintained record and git history is the archive.
