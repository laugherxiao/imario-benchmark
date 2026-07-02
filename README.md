# iMario Validity Benchmark

**Open, reproducible measurement of how well the iMario synthetic-audience engine predicts real human survey responses.**

Most synthetic-audience vendors publish a single percentage and no data, no code, no question list. This repo does the opposite: **the ground-truth distributions, the per-person synthetic answers, and a zero-dependency scorer are all here**, so anyone can reproduce our published numbers offline — no install, no account, no cost.

## Reproduce our numbers (no install, no account)

```bash
git clone https://github.com/laugherxiao/imario-benchmark && cd imario-benchmark
python score.py            # Python 3.9+ standard library only — nothing to install
```

Expected: the 11 quantitative populations average **88.9%** raw 1-TV, and US open-ended (`US_qual`) scores **81.8%** — matching what we publish. `score.py` reads the per-person answers under `verification/`, re-aggregates them into distributions, and scores them against the real survey distributions. Every headline number is something you re-derive locally, not something we ask you to trust. Details: [`verification/README.md`](verification/README.md).

We report the same metric the field uses, under its real name:

| Metric | Definition | Who reports it this way |
|---|---|---|
| **raw 1-TV** (we call it *distribution accuracy*) | `1 − ½·Σ|p−q|` — share of probability mass correctly allocated | Artificial Societies |
| **1-MAE** | `1 − (Σ|p−q|)/n_options` — mechanically ≥ 1-TV, grows with option count | Electric Twin |

> ⚠️ `raw 1-TV` and `1-MAE` are different yardsticks. Never compare one vendor's 1-MAE to another's 1-TV.

## Why you can trust it (and audit it yourself)

- **Frozen, public question bank** — questions + real distributions are fixed and checksummed (`data/checksums.sha256`) *before* answers are generated. No picking questions after seeing results.
- **Full disclosure** — every question is published, including the worst-scoring ones. Questions are removed only for the documented reasons in [`data/SENSITIVE_EXCLUDED.md`](data/SENSITIVE_EXCLUDED.md), never because a score was low.
- **Per-person evidence, not just aggregates** — `verification/` ships every individual synthetic answer. You re-aggregate them yourself (that's all `score.py` does). Faking a number would mean forging thousands of internally consistent per-person answers — for the open-ended questions, thousands of natural-language responses each consistent with its coding. Harder than just running the real thing.

## What's measured, honestly

The headline is **group distribution accuracy**: per question, how close the synthetic answer distribution is to the real human one. We report three tiers and never hide the hard questions:

- **novel** — no prior data for the question; the engine estimates from scratch. The floor that matters for new client questions.
- **trend** — a same-question wave exists from an earlier year; projected forward. Value decays as the prior ages.
- **covered** — a recent same-question prior exists.

The only exclusions are non-opinion admin/demographic items, degenerate items (one option ≥ 97%, no signal), and a documented sensitive list — never a score filter.

## Run your own study (live, on your account)

Verifying our published numbers is free and offline (above). To generate a **fresh cohort on your own questions and target audience** through the same production engine, use **[imario.ai](https://imario.ai)** (account + credits). That's the product; it is intentionally not part of this public repo — the engine and its data stay private, and this repo exists to let you *verify*, not to run the engine.

## Repo layout

```
score.py                       zero-dependency verifier — recompute every score from published answers
verification/                  per-population evidence + how-to (README)
  <pop>/                         11 quant populations (US, UK, CN, India, Japan, Brazil,
                                 France, Germany, Australia, SouthKorea, SO) + US_qual
    questions.json               {qid: {question, options}}
    real_distribution.json       {qid: [real probability per option]}
    synthetic_answers.jsonl      one row per simulated person: {persona_id, answers}
    personas.json                each person's sampling coordinates (audit cohort composition)
data/extraction/               scripts that build the question bank from official microdata
data/processed/                the question bank (aggregate) + 测试_*.csv per-country question lists
data/SENSITIVE_EXCLUDED.md     every excluded question id + reason category
data/checksums.sha256          integrity hashes for the question files
results/prod_v1/               the official run — aggregate distributions + scores
                               (per-person answers live in verification/, cleaned of internal fields)
tools/                         build_verification_bundle.py (maintainer: rebuild verification/)
METHODOLOGY.md                 sources, extraction, metric formulas, tier definitions
```

## Regenerate the question bank from raw microdata (optional)

The published question banks in `data/processed/` were built from official survey microdata by the scripts in `data/extraction/`. The **microdata itself is licensed and not redistributable** (Pew / CGSS / ANES terms), so it is not shipped here. To rebuild the identical question bank, download each source (free) into `data/raw/` and rerun:

| Survey (population) | Official source (free account may be required) | Download into |
|---|---|---|
| Pew Global Attitudes Spring 2025 (8 non-US countries) | https://www.pewresearch.org/global/dataset/spring-2025-survey-data/ | `data/raw/PEW-Global-2025/` |
| Pew American Trends Panel Wave 145 (US) | https://www.pewresearch.org/dataset/american-trends-panel-wave-145/ | `data/raw/PEW-US-W145_Apr24/` |
| CGSS 2023 (China) | http://cgss.ruc.edu.cn/ | `data/raw/CGSS-2023/` |
| ANES 2024 Time Series (US open-ended) | https://electionstudies.org/data-center/ | `data/raw/anes_timeseries_2024_csv_20260519/` |
| Stack Overflow 2025 Developer Survey | https://survey.stackoverflow.co/ | `data/raw/stackoverflow-2025/` |

```bash
pip install -e ".[extraction]"          # numpy / pandas / pyreadstat / pypdf / pdfplumber
python data/extraction/pew_process.py   # → data/processed/pew_global_2025_full.json
# (each script's header lists its exact source, output, and options)
```

## Datasets & licensing

We redistribute only **aggregate toplines** (not microdata), with attribution, from ANES, CGSS, Pew Research Center, and the Stack Overflow Developer Survey. See [DATA_LICENSE.md](DATA_LICENSE.md) and [METHODOLOGY.md](METHODOLOGY.md) for sources, extraction, metric formulas, tier definitions, and the sensitive-exclusion policy. Code is Apache-2.0 ([LICENSE](LICENSE)).
