# iMario Accuracy Benchmark — Scoreboard

_Source run: `prod_v1`. Numbers mirror the live /benchmark page; every quantitative figure is reproducible offline with `score.py` (see `verification/`)._

## Headline

| Metric | Value |
|---|---|
| Group distribution accuracy (raw 1-TV, leave-one-out, full pool) | **88.9%** |
| Group distribution accuracy (1-MAE) | **94.1%** |
| Qualitative accuracy (US open-ended, coded-theme raw 1-TV) | **81.8%** |
| Populations benchmarked | 11 (10 countries + global developers) |
| Questions (full pool) | 922 |
| Synthetic individuals | 11,000 |
| Human ceiling — distribution reproducibility (survey re-run) | ~93% |
| Human ceiling — individual test-retest | 81% |

## Per-population — quantitative (prod_v1, measured)

| Population | Survey | n questions | raw 1-TV | 1-MAE | tiers |
|---|---|---|---:|---:|---|
| United States | Pew ATP 2024 | 117 | 91.3 | 95.0 | drift 21, readout 80, grounded 16 |
| United Kingdom | Pew Global 2025 | 72 | 90.2 | 94.6 | drift 14, readout 58 |
| France | Pew Global 2025 | 72 | 89.8 | 94.3 | drift 19, readout 1, similar_calibrate 52 |
| Australia | Pew Global 2025 | 70 | 89.8 | 94.4 | drift 18, readout 52 |
| Germany | Pew Global 2025 | 72 | 89.3 | 94.4 | drift 19, readout 53 |
| India | Pew Global 2025 | 119 | 89.2 | 93.9 | drift 19, similar_calibrate 100 |
| China | CGSS 2023 | 156 | 88.8 | 93.7 | drift 48, similar_calibrate 108 |
| South Korea | Pew Global 2025 | 66 | 88.5 | 93.5 | drift 14, readout 52 |
| Brazil | Pew Global 2025 | 95 | 87.3 | 93.2 | drift 20, similar_calibrate 74, readout 1 |
| professional software developers | Stack Overflow 2025 | 13 | 87.3 | 95.1 | similar_calibrate 8, drift 5 |
| Japan | Pew Global 2025 | 70 | 86.6 | 92.6 | drift 17, readout 53 |
| **Mean** |  |  | **88.9** | **94.1** |  |

## Where iMario stands — vendor & baseline comparison

Two different yardsticks; never compare a 1-MAE to a 1-TV.

### Strict scale · 1-TV
| Entity | 1-TV | Basis |
|---|---:|---|
| iMario | 88.9 | measured, named public data |
| Artificial Societies | 86 | unnamed |
| Claude Opus 4.8 personas | 64.0 | reference (indicative) |
| GPT-5.4 personas | 62.0 | reference (indicative) |
| Gemini 3.1 Pro personas | 61.0 | reference (indicative) |

### Lenient scale · 1-MAE
| Entity | 1-MAE | Basis |
|---|---:|---|
| iMario | 94.1 | measured, named public data |
| Electric Twin | 95.5 | private |
| Claude Opus 4.8 personas | 82.2 | reference (indicative) |
| GPT-5.4 personas | 81.2 | reference (indicative) |
| Gemini 3.1 Pro personas | 80.7 | reference (indicative) |

## Provenance & honesty notes

- **iMario** figures are measured on the named public data (prod_v1) and reproducible from `results/`.
- **Vendor** figures (Artificial Societies 1-TV, Electric Twin 1-MAE) are each company's own published number, on their own (private/unnamed) data.
- **Naive LLM-persona baselines (Claude Opus 4.8, GPT-5.4, Gemini 3.1 Pro)** are *indicative references*, not full runs on our data. Their 1-TV sits in the published naive-persona band (see Artificial Societies' own comparison, ~61-67%); their 1-MAE is derived from the 1-TV↔1-MAE relationship measured in our own spot runs (`1-MAE ≈ 50.5 + 0.496 × 1-TV`).
  - For the record, our own spot runs on our exact data measured GPT-5.4 ≈ 54 / 77 (1-TV/1-MAE) and Gemini 2.5 Pro ≈ 66 / 83; the page uses the reference band values instead, clearly labeled.
- **Qualitative** (US open-ended, ANES coded-theme): raw 1-TV **81.8%** on prod_v1, reproducible from the per-person verbatims via `python score.py US_qual` (matches the published page and `results/prod_v1/scores_qual_US.json`).
