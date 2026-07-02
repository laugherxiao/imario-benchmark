# Changelog

## v1.0.0

Initial public benchmark.

- **Independent verification** — `score.py`, a zero-dependency scorer (Python 3.9+ standard library) that recomputes every published number from the per-person synthetic answers under `verification/`. No install, no account, no cost.
- **Metrics**: `raw 1-TV` (distribution accuracy) and `1-MAE`, reported under the field's own names.
- **Coverage**: 11 quantitative populations — US, UK, China, Japan, India, Brazil, France, Germany, Australia, South Korea, and professional developers — plus US open-ended (ANES coded open-ends).
- **Datasets**: aggregate toplines only, no microdata — ANES 2024, CGSS 2023, Pew Global 2025, Pew ATP Wave 145, Stack Overflow 2025.
- **Official run**: `results/prod_v1/` (aggregate distributions + scores); the per-person answers behind them ship in `verification/`.
- Engine behind the published predictions: production readout = gpt-5.5 + similar-topic calibration.
- To run your own study live on the engine (your questions, your audience), see imario.ai — a paid product, not part of this repo.
