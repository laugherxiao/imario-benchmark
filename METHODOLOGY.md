# Methodology

## Metrics

For a question with real distribution `p` and synthetic distribution `q` over the same `n` options:

- **Total variation** `TV = ½·Σ|pᵢ−qᵢ|` (equivalently the US-census *index of dissimilarity*: the share of probability mass that is misallocated).
- **raw 1-TV** = `1 − TV` — "distribution accuracy". This is Artificial Societies' headline metric: their worked example (human 70/30, synthetic 60/40 → 90%) is exactly `1 − TV`.
- **1-MAE** = `1 − (Σ|pᵢ−qᵢ|)/n`. Since `Σ|p−q| = 2·TV`, this equals `1 − 2·TV/n`. It is **mechanically ≥ raw 1-TV** and increases with the number of options, so it reports larger numbers. This is Electric Twin's convention. We publish it only so cross-vendor numbers are mappable; **never compare a 1-MAE to a 1-TV.**
- **response consistency** = for one persona answering the *same* question phrased many ways, the share landing on the modal answer; averaged over (persona, question). This is a *reliability* metric (answers are stable), not an *accuracy* metric (answers are correct). Artificial Societies reports 93%; standard LLM personas <50%.

Per-audience scores are the mean over that audience's questions, with a 95% confidence interval (normal approximation). Scaling the question set tightens the interval — that is the point of running hundreds of questions rather than a handful.

## Human-replication ceiling

Even re-running the identical survey on fresh respondents does not reproduce the first result exactly, because of sampling noise. We compute, per question, `1 − E[TV(resample_at_n, real)]` by multinomial resampling at the real survey's `n`. This is the highest score a perfect simulator could *expect*. Stanford (Park et al. 2024) and Twin-2K-500 independently put individual two-week self-consistency at ~81%; aggregated to groups this implies a group ceiling in the low-90s, consistent with our per-question computation. Scores are always shown against this ceiling so they are interpretable.

## Tiers (reported, never hidden)

- **novel** — no same-question prior; the engine estimates from model knowledge + similar-topic calibration. The honest floor for genuinely new client questions.
- **trend** — an earlier-year wave of the same question exists; the engine projects it to the survey year. Measured finding: prior value is **recency-gated** — a 5-year-old same-question prior barely beats novel; only a recent prior reaches the covered tier.
- **covered** — a recent same-question prior exists (highest tier; partly a memory check).

We score under **leave-one-out**: a question's own ground-truth row is never visible to the engine when predicting it, so "covered" never means "handed back the answer key".

## Curation policy (no score-based exclusion)

Every substantive opinion question is kept. The only removals are:
1. **Non-opinion** admin/demographic/screening items.
2. **Degenerate** items (one option ≥ 97% — no signal to measure).
3. **Sensitive** items on a documented list (`data/SENSITIVE_EXCLUDED.md`), each with a reason category, signed off for legal/safety reasons.

A question is **never** removed because it scored poorly. Hard questions stay in and pull the average down honestly — transparency is the point.

## Data sources & extraction

- **ANES 2024 Time Series** (United States, open-ended): weighted distributions over substantive options, extracted from the official codebook + CSV.
- **CGSS 2023** (China): weighted distributions from the official `.dta` microdata.
- **Pew Global Attitudes 2025** (UK, Japan, India, Brazil, France, Germany, Australia, South Korea): weighted distributions from the official `.sav` microdata.
- **Pew American Trends Panel Wave 145** (United States): the US is fielded separately from Pew's international file; weighted distributions from the official `.sav`.
- **Stack Overflow Developer Survey 2025** (professional developers): answer distributions from the public results CSV.

We redistribute only the computed **aggregate distributions**, never microdata. The scripts in `data/extraction/` document the transformation; download instructions and licensing are in `DATA_LICENSE.md`. `data/checksums.sha256` pins the questions and real distributions; `score.py` re-derives every score from the published per-person answers.

## What this benchmark does and does not claim

- It measures **group distribution fidelity** and **response reliability** on public attitude surveys. It does **not** claim individual-level prediction (predicting a specific person's answer); that is a different, harder estimand with much lower published ceilings.
- The synthetic cohort additionally produces real, readable open-ended answers (qualitative texture and follow-up interviews); the quantitative distribution is set by the engine and carried by the cohort, mirroring production exactly.
