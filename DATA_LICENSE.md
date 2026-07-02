# Data sources, attribution, and redistribution

This repository redistributes only **aggregate topline distributions** (the percentage of respondents choosing each option, weighted), computed from publicly released survey datasets. **No respondent-level microdata is included or redistributed.** Aggregate, non-identifiable statistics are republished here for reproducibility, with attribution to the original investigators.

| Dataset | Audience | Provider | Source / obtain microdata |
|---|---|---|---|
| ANES 2024 Time Series | United States adults (open-ended) | American National Election Studies | https://electionstudies.org (register + download) |
| CGSS 2023 | China adults | Chinese General Social Survey, Renmin University | http://cnsda.org (register + download) |
| Pew Global Attitudes 2025 | UK, Japan, India, Brazil, France, Germany, Australia, South Korea | Pew Research Center | https://www.pewresearch.org/global/datasets/ |
| Pew American Trends Panel Wave 145 | United States adults | Pew Research Center | https://www.pewresearch.org/dataset/american-trends-panel-wave-145/ |
| Stack Overflow Developer Survey 2025 | professional developers | Stack Overflow | https://survey.stackoverflow.co/ |

The original investigators and funding agencies bear no responsibility for the analyses or interpretations presented here.

## Reproducing the datasets from source

The scripts in `data/extraction/` document the transformation from the official microdata to the shipped question banks in `data/processed/*.json` (weighted distribution over substantive options; admin/demographic and degenerate items dropped). To regenerate from scratch, download the official microdata per the links above and run the extractors (see the README's "Regenerate the question bank" section). The questions and real distributions are pinned by `data/checksums.sha256`, and `score.py` re-derives every published score from the per-person answers.

## Per-question sample size (`n`)

Each question carries the **survey-level** respondent count for its dataset (ANES 2024 ≈ 5,521; CGSS 2023 = 11,326; Pew Global 2025 ≈ 1,000 per country). Per-question weighted bases vary slightly and are typically within a few percent of these; `n` is used only to compute the sampling-noise human-replication ceiling.

## License of the redistributed aggregates

The computed aggregate distributions in `data/processed/` and `verification/` are provided for research and reproducibility under the same terms as this repository's code (Apache-2.0), subject to the attribution requirements above. If any provider's terms restrict redistribution of derived aggregates, those terms govern and we will remove the affected items on request.
