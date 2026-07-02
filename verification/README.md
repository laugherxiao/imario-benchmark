# Verifying the iMario benchmark

Every headline number on the iMario benchmark can be re-derived here, on your own machine, with
**zero dependencies** beyond the Python standard library. The top-level [`score.py`](../score.py)
does **not** call any iMario service or model — it reads the synthetic answers we published (one row
per simulated person) and recomputes every score. This lets you confirm the numbers are the honest
aggregate of individual answers, not a hand-picked distribution.

## Quick start

```bash
python score.py                      # score every population
python score.py CN UK                # just these
python score.py --per-question US_qual   # per-question breakdown
```

Expected output: the quantitative populations average **88.9%** raw 1-TV, and **US_qual** scores
**81.8%** — matching the published site.

## What's in each bundle (`verification/<pop>/`)

**Quantitative** (closed questions — every population except `US_qual`):

| file | contents |
|---|---|
| `questions.json` | `{qid: {question, options}}` |
| `real_distribution.json` | `{qid: [real probability per option]}` — the official survey topline |
| `synthetic_answers.jsonl` | one row per simulated person: `{persona_id, answers: {qid: chosen option}}` |
| `personas.json` | each person's **sampling coordinates** (the quota cell they were drawn into) |

**Qualitative** (`US_qual/` — open-ended answers, coded against the ANES 2024 open-ends):

| file | contents |
|---|---|
| `questions.json` | `{qid: question text}` |
| `gold_shares.json` | `{qid: {category: real ANES coded share}}` |
| `synthetic_verbatims.jsonl` | per person: `{persona_id, open: {qid: {text, codes}}}` |

## How the score is computed

- **Quant.** For each question, tally which option each person chose → a synthetic distribution.
  Score = `1 − TVD(real, synthetic)`, where `TVD = ½ · Σ|real − synthetic|` (total variation
  distance). The population score is the mean over its questions.
- **Qual.** For each open question, tally the codebook categories mentioned across all verbatims →
  a mention-share distribution. Score = `1 − TVD(gold, mention-share)`.

`score.py` implements exactly this and nothing else — read it, it's ~120 lines.

## Why you can trust it (and audit it yourself)

- **Frozen, public question bank.** The questions and their real distributions are published and
  fixed *before* answers are generated; the shipped question set is checksummed in
  [`checksums.sha256`](../checksums.sha256). You can't pick questions after seeing the results.
- **Full disclosure.** Every question is published, including the worst-scoring ones. Questions are
  removed only for the documented reasons in [`data/SENSITIVE_EXCLUDED.md`](../data/SENSITIVE_EXCLUDED.md)
  — never because a score was low.
- **Per-person evidence, not just aggregates.** We publish every individual answer. You re-aggregate
  them yourself (that is all `score.py` does). Faking the numbers would mean forging thousands of
  internally consistent per-person answers — for the open-ended questions, thousands of natural-language
  responses each consistent with its coding. That is harder than just running the real thing.
- **Sampling audit.** `personas.json` lets you tally each cohort's composition against the target
  quotas the population was stratified on.

## What's *not* here, and how to get it

- **Raw survey microdata** is licensed (Pew / CGSS / ANES terms) and cannot be redistributed. Download
  it free from the official sources and regenerate the *identical* question bank with the scripts in
  [`data/extraction/`](../data/extraction/) — each script's header lists its source and download link.
- **The generation engine** (how the synthetic people are created and how they answer) is not open
  source. Verifying our published numbers does not require it — that is the entire point of this
  folder. To run your own studies with the engine, see [imario.ai](https://imario.ai).
