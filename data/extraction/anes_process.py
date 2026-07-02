"""anes_process.py — turn the raw ANES 2024 Time Series download into one full question-bank JSON.

WHAT THIS DOES
  Parses the ANES codebook PDF for each variable's (question wording, value labels), joins it
  with the CSV response file, and computes the WEIGHTED response distribution over the substantive
  answer options for every OPINION / ATTITUDE question (2-7 substantive options; demographics,
  admin and process variables are excluded). Audience is fixed to "United States adults".

RAW DATA — download from the official source first
  ANES 2024 Time Series Study:  https://electionstudies.org/data-center/2024-time-series-study/
  After download+unzip you need two files (default location: ../anes_timeseries_2024_csv_20260519/):
    - anes_timeseries_2024_csv_20260519.csv                  (the response data)
    - anes_timeseries_2024_userguidecodebook_20260519.pdf    (the codebook / value labels)

RUN
  conda activate imario
  python data/extraction/anes_process.py
  # or point at a custom download:
  python data/extraction/anes_process.py --csv /path/to/data.csv --codebook /path/to/codebook.pdf

OUTPUT
  data/processed/anes_2024_full.json
"""
from __future__ import annotations
import argparse, json, re
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from pypdf import PdfReader

HERE = Path(__file__).resolve().parent          # imario-benchmark/data/extraction
IB = HERE.parent.parent                          # imario-benchmark
RAW = IB / "data" / "raw"
PROC = IB / "data" / "processed"

# ── default raw-download locations (override on the CLI) ──────────────────────
DEFAULT_DIR = RAW / "anes_timeseries_2024_csv_20260519"
DEFAULT_CSV = DEFAULT_DIR / "anes_timeseries_2024_csv_20260519.csv"
DEFAULT_PDF = DEFAULT_DIR / "anes_timeseries_2024_userguidecodebook_20260519.pdf"
DEFAULT_OUT = PROC / "anes_2024_full.json"

WEIGHT = "V240105b"   # post-election full fresh cross-section weight
SOURCE_URL = "https://electionstudies.org/data-center/2024-time-series-study/"

# answer labels that are NOT a substantive opinion (dropped before building the distribution)
BAD = ["don't know", "dont know", "refused", "inapplicable", "no answer", "no response",
       "no post", "missing", "interview breakoff", "dk/rf", "establishment", "not asked"]
# variable TITLES that are demographics / admin / process (not an opinion question)
EXCLUDE_TITLE = ["WEIGHT", "LANGUAGE", "SAMPLE", "MODE", "FLAG", "VERSION", "TIMESTAMP", "ADMIN",
                 "STRATUM", "PSU", "DATE", "ID NUMBER", "CASE ID", "ZIP", "STATE FIPS", "COUNTY",
                 "AGE GROUP", "BIRTH", "GENDER", "RACE", "ETHNIC", "MARITAL", "EDUCATION LEVEL",
                 "HOUSEHOLD INCOME", "SEXUAL ORIENTATION", "BALLOT", "PARADATA", "DEVICE",
                 "PRE-ELECTION RAKED", "POST-ELECTION RAKED",
                 "COMPLETION", "CONSENT", "INTERVIEWER", "AUDIO", "CONTACT", "RECONTACT",
                 "BREAKOFF", "PROCESSING", "TIMING", "DISPOSITION", "ATTEMPT", "MAN OR WOMAN",
                 "INTERVIEW STATUS", "PRE/POST", "WHICH FORM", "RANDOM", "SPLIT", "ORDER",
                 "TYPE OF", "AVAILABILITY", "REGISTERED TO VOTE STATE"]


DEGENERATE = 0.97   # one option >= this share -> no signal to measure; drop

def is_bad(s: str) -> bool:
    s = str(s).lower().replace("’", "'").replace("‘", "'").replace("`", "'")
    return any(b in s for b in BAD)


_ANES_OPTS = re.compile(r"\s*\[[^\]]*\]?")


def _anes_matrix(q: str) -> str:
    """ANES battery: drop bracketed option lists, then fill a 'the following <X>' placeholder with
    the item trailing the stem's question mark (e.g. '...the following issue...? Illegal immigration'
    -> 'How important is Illegal immigration in the country today?')."""
    q = re.sub(r"\[([A-Za-z]+)/[A-Za-z/]+\]", r"\1", q)   # split-form "[Democrats/Republicans]" -> first
    q = re.sub(r"\s+", " ", _ANES_OPTS.sub(" ", q)).strip()  # drop remaining [option enumerations]
    m = re.search(r"[?.]\s+([A-Z][a-z].*)$", q)           # item trailing the stem (after "?" or ".")
    if m and re.search(r"\b(?:the )?following\b", q[:m.start() + 1]):
        item = m.group(1).strip().rstrip("?. ")
        return re.sub(r"\b(?:the )?following(?:\s+\w+)?\b", item, q[:m.start() + 1], count=1).strip()
    return q


def parse_codebook(pdf_path: Path) -> dict:
    """var -> {title, question, labels{code:label}} parsed from the codebook PDF."""
    txt = "\n".join(p.extract_text() for p in PdfReader(str(pdf_path)).pages)
    blocks = re.split(r"(?=\nV\d{6}[a-z]*)", txt)
    out = {}
    for b in blocks:
        m = re.match(r"\s*(V\d{6}[a-z]*)", b)
        if not m or "Value Labels" not in b:
            continue
        var = m.group(1)
        body = b[m.end():]                                   # after the V###### token
        title = body.split("\n", 1)[0].strip()               # first line = ALL-CAPS summary label
        rest = body.split("\n", 1)[1] if "\n" in body else ""
        # the real question sits between the title and the first value label; the PDF often splits it
        # across an inline "Question" divider and injects a running page header — stitch and strip both.
        cut = re.search(r"\n\s*-?\d+\.\s|\bValue Labels\b", rest)
        qbody = rest[:cut.start()] if cut else rest
        qbody = re.sub(r"\n\s*Question\s*\n", " ", qbody)     # stitch across the "Question" divider
        qbody = re.sub(r"\bQuestion\b", " ", qbody)           # any stray "Question" label
        qbody = re.sub(r"(?:PRE|POST)[‐\-]?\s*ELECTION SURVEY VARIABLES\s*\d*", " ", qbody, flags=re.I)  # running header
        qbody = re.sub(r"\d+\s+CODEBOOK:\s*VARIABLES", " ", qbody, flags=re.I)  # page-header noise
        qbody = re.sub(r"\s+", " ", qbody).strip()
        # the real question is normal-case; drop leading ALL-CAPS title/section words. A body with no
        # normal-case text at all is a summary/derived variable (no standalone question) -> skip it.
        mq = re.search(r"[A-Z][a-z].*$", qbody)
        if not mq:
            continue
        question = mq.group(0).strip()
        question = re.sub(r"\s*\[[^\]]*\]?\s*$", "", question).strip()   # trailing "[opt, opt, ...]" list
        question = re.sub(r"\?\s*[-–][^?]*$", "?", question).strip()     # trailing "? - opt - opt" list
        question = re.sub(r"\s*(?:CODEBOOK|Value Labels)\b.*$", "", question, flags=re.I).strip()  # residual noise
        question = _anes_matrix(question)                    # battery: fill "the following X" + drop [options]
        question = re.sub(r"\s*\?\s*\?+", "?", question).strip()   # collapse "? ?" left by removed brackets
        vl_section = b.split("Value Labels", 1)[1].split("Survey Question", 1)[0]
        labels = {}
        for lm in re.finditer(r"(-?\d+)\.\s*([^\n]+)", vl_section):
            labels[int(lm.group(1))] = lm.group(2).strip()
        out[var] = {"title": title, "question": question, "labels": labels}
    return out


def build(csv_path: Path, pdf_path: Path) -> list:
    cb = parse_codebook(pdf_path)
    print(f"codebook: {len(cb)} variables parsed", flush=True)
    df = pd.read_csv(csv_path, low_memory=False)
    w = pd.to_numeric(df[WEIGHT], errors="coerce") if WEIGHT in df.columns else None
    if w is None:
        print("WARN: weight column missing -> unweighted"); w = pd.Series(1.0, index=df.index)

    cells = []
    for var, info in cb.items():
        if var not in df.columns:
            continue
        if any(k in info["title"].upper() for k in EXCLUDE_TITLE):
            continue
        if len(str(info["question"]).strip()) < 8:
            continue
        subs = {c: l for c, l in info["labels"].items() if c >= 0 and not is_bad(l)}
        if not (2 <= len(subs) <= 7):
            continue
        codes = sorted(subs)
        col = pd.to_numeric(df[var], errors="coerce")
        mask = col.isin(codes) & w.notna() & (w > 0)
        if mask.sum() < 100:                       # need a usable base
            continue
        ww, vals = w[mask].values, col[mask].values
        d = np.array([ww[vals == c].sum() for c in codes], dtype=float)
        if d.sum() <= 0 or d.max() / d.sum() >= DEGENERATE:        # empty or degenerate -> no signal
            continue
        labels = [subs[c] for c in codes]
        if len(set(labels)) != len(labels):                       # duplicate option labels -> malformed
            continue
        cells.append({"var": var, "question": info["question"], "audience": "United States adults",
                      "options": labels, "distribution": (d / d.sum()).tolist(),
                      "n": int(mask.sum())})
    # dedup: same (audience, question) -> keep the largest-base cell (split-ballot / dup variables)
    best = {}
    for c in cells:
        k = (c["audience"], c["question"])
        if k not in best or c["n"] > best[k]["n"]:
            best[k] = c
    return list(best.values())


def main():
    ap = argparse.ArgumentParser(description="Build the ANES 2024 full question-bank JSON.")
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="ANES 2024 response CSV")
    ap.add_argument("--codebook", type=Path, default=DEFAULT_PDF, help="ANES 2024 codebook PDF")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output JSON path")
    args = ap.parse_args()

    for p in (args.csv, args.codebook):
        if not p.exists():
            raise SystemExit(f"missing raw file: {p}\nDownload the ANES 2024 Time Series Study from {SOURCE_URL}")

    cells = build(args.csv, args.codebook)
    unique_q = len({c["question"] for c in cells})
    payload = {
        "dataset": "ANES 2024 Time Series Study",
        "source_url": SOURCE_URL,
        "fieldwork_year": 2024,
        "audience_type": "national",
        "audiences": ["United States adults"],
        "weight_variable": WEIGHT,
        "question_filter": "opinion/attitude items, 2-7 substantive options, base n>=100, demographics/admin excluded",
        "n_cells": len(cells),
        "n_unique_questions": unique_q,
        "extracted_on": date.today().isoformat(),
        "cells": cells,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    print(f"ANES 2024: {len(cells)} variable-cells ({unique_q} unique questions) -> {args.out}")


if __name__ == "__main__":
    main()
