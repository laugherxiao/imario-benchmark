# Excluded questions

This file lists every question removed from the public benchmark and the reason. **Questions are never removed because they scored poorly** — only for the documented categories below. The full set of retained questions (including hard, low-scoring ones) ships in `data/processed/` and per-population under `verification/`.

## Exclusion categories

- `admin` — non-opinion administrative/screening/demographic item (removed automatically in extraction).
- `degenerate` — one option ≥ 97% of responses; no signal to measure (removed automatically).
- `sensitive` — legal/safety/policy exclusion, signed off by the maintainers. Listed by id + category only; the question text is not reproduced when itself sensitive.

## Sensitive exclusions (manual, signed off)

| id | dataset | reason category | sign-off |
|---|---|---|---|
| _(none yet — to be populated after the full measurement pass and review)_ | | | |

> Process: run the full benchmark on all retained questions, publish the complete per-question results, then review for legal/safety-sensitive items only. Any item moved here is logged above with a category and a maintainer sign-off, never with a score justification.
