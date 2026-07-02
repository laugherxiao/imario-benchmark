"""so_process.py — turn the raw Stack Overflow 2025 Developer Survey download into one full
question-bank JSON. Audience is fixed to "professional software developers" (the niche population
used for the audience-conditioning A/B in benchmark.md 0.8).

WHAT THIS DOES
  Filters to professional developers (MainBranch == "I am a developer by profession"), then for
  every single-select OPINION / BEHAVIOR question (a multiple-choice column with 2-15 substantive
  answers; demographics, survey-routing "...Choice" items and free-text/numeric columns excluded)
  computes the real answer distribution. The survey is unweighted, so distributions are raw counts
  renormalized over the answers actually present.

RAW DATA — download from the official source first
  Stack Overflow Annual Developer Survey 2025 (raw results):
    https://survey.stackoverflow.co/   ->  "Download Full Data Set"
  After download+unzip you need (default location: ../imario-benchmark/data/stackoverflow/):
    - survey_results_public.csv   (one row per respondent)
    - survey_results_schema.csv   (qname -> full question wording)

RUN
  conda activate imario
  python data/extraction/so_process.py
  # or point at a custom download:
  python data/extraction/so_process.py --dir /path/to/stackoverflow

OUTPUT
  data/processed/stackoverflow_2025_full.json
"""
from __future__ import annotations
import argparse, json, re
from datetime import date
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
IB = HERE.parent.parent
RAW = IB / "data" / "raw"
PROC = IB / "data" / "processed"

DEFAULT_DIR = RAW / "stackoverflow-2025"
DEFAULT_OUT = PROC / "stackoverflow_2025_full.json"
SOURCE_URL = "https://survey.stackoverflow.co/"

PRO_DEV = "I am a developer by profession"     # MainBranch value defining the audience
AUDIENCE = "professional software developers"
MIN_BASE = 100                                  # minimum responses per question
MIN_OPTS, MAX_OPTS = 2, 15

# demographics / firmographics — excluded for parity with the ANES/CGSS/Pew opinion pools
DEMOGRAPHIC = {"MainBranch", "Age", "EdLevel", "Employment", "OrgSize", "Industry",
               "Country", "Currency", "DevType", "YearsCode", "YearsCodePro"}
# survey-routing / meta questions ("would you like to be asked about X?") — not opinions
def is_routing(qname: str) -> bool:
    return qname.endswith("Choice") or qname in {"TechEndorseIntro", "LearnCodeChoose"}


# content-level non-opinion items not covered by the DEMOGRAPHIC var set (job role, account
# ownership, work situation) — factual profile, not opinion/behavior of interest
_NONOP_WORDING = re.compile(
    r"individual contributor|people manager|stack overflow account|"
    r"current work situation|work situation|completed an apprenticeship|what is your age|"
    r"highest level of|how old are you|where do you live|which country",
    re.I)
DEGENERATE = 0.97   # one option >= this share -> no signal to measure; drop


def build(data_dir: Path) -> list:
    public = data_dir / "survey_results_public.csv"
    schema = data_dir / "survey_results_schema.csv"
    df = pd.read_csv(public, low_memory=False)
    print(f"loaded {len(df):,} respondents x {len(df.columns)} columns", flush=True)
    dev = df[df["MainBranch"] == PRO_DEV]
    print(f"professional developers: {len(dev):,}", flush=True)

    # qname -> full question wording (first occurrence)
    wording = {}
    if schema.exists():
        sdf = pd.read_csv(schema)
        for _, r in sdf.drop_duplicates("qname").iterrows():
            wording[str(r["qname"])] = str(r["question"])

    cells = []
    for c in df.columns:
        if c in DEMOGRAPHIC or is_routing(c):
            continue
        if df[c].dtype != object:
            continue
        nonnull = dev[c].dropna().astype(str)
        if len(nonnull) < MIN_BASE:
            continue
        if nonnull.str.contains(";").any():        # multi-select column -> skip
            continue
        vc = nonnull.value_counts()
        if not (MIN_OPTS <= len(vc) <= MAX_OPTS):
            continue
        if _NONOP_WORDING.search(str(wording.get(c, c))):   # drop job-role/account/work-situation
            continue
        options = list(vc.index)                   # ordered by frequency, desc
        total = float(vc.sum())
        if max(vc) / total >= DEGENERATE:          # degenerate (one option ~all) -> no signal
            continue
        cells.append({"var": c, "question": wording.get(c, c), "audience": AUDIENCE,
                      "options": options, "distribution": [float(vc[o] / total) for o in options],
                      "n": int(total)})
    return cells


def main():
    ap = argparse.ArgumentParser(description="Build the Stack Overflow 2025 full question-bank JSON (pro devs).")
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR, help="folder with survey_results_public.csv + schema")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output JSON path")
    args = ap.parse_args()

    if not (args.dir / "survey_results_public.csv").exists():
        raise SystemExit(f"missing survey_results_public.csv in: {args.dir}\n"
                         f"Download the 2025 Developer Survey full data set from {SOURCE_URL}")

    cells = build(args.dir)
    payload = {
        "dataset": "Stack Overflow Annual Developer Survey 2025",
        "source_url": SOURCE_URL,
        "fieldwork_year": 2025,
        "audience_type": "niche",
        "audiences": [AUDIENCE],
        "weight_variable": "",   # survey is unweighted
        "question_filter": "single-select opinion/behavior items, 2-15 options, base n>=100, demographics & routing excluded",
        "n_cells": len(cells),
        "n_unique_questions": len({c["question"] for c in cells}),
        "extracted_on": date.today().isoformat(),
        "cells": cells,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    print(f"Stack Overflow 2025: {len(cells)} questions (pro devs) -> {args.out}")


if __name__ == "__main__":
    main()
