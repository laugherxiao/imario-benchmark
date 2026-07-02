"""pew_process.py — turn the raw Pew Global Attitudes Spring 2025 download into one full
question-bank JSON, covering ALL 24 surveyed countries (not just the AI module).

WHAT THIS DOES
  Reads the labeled .sav file, finds every OPINION question (a value-labelled item carrying a
  "Q.." question label with 2-7 substantive options; DK/Refused/NA dropped), and computes the
  WEIGHTED response distribution PER COUNTRY. Each (question x country) becomes one cell, so the
  audience is per-country ("Japan adults", "India adults", ...).

RAW DATA — download from the official source first
  Pew Research Center · Spring 2025 Global Attitudes Survey:
    https://www.pewresearch.org/global/dataset/spring-2025-survey-data/
  After download+unzip you need the SPSS file (default location:
  ../Pew-Research-Center-Global-Attitudes-Spring-2025-Public/):
    - Pew Research Center Global Attitudes Spring 2025 Dataset.sav

RUN
  conda activate imario
  python data/extraction/pew_process.py
  # or point at a custom download:
  python data/extraction/pew_process.py --sav "/path/to/....sav"

OUTPUT
  data/processed/pew_global_2025_full.json
"""
from __future__ import annotations
import argparse, json, re
from datetime import date
from pathlib import Path

import numpy as np
import pyreadstat
try:
    import pdfplumber
except ImportError:                      # PDF item-restoration is optional
    pdfplumber = None

HERE = Path(__file__).resolve().parent
IB = HERE.parent.parent
RAW = IB / "data" / "raw"
PROC = IB / "data" / "processed"

DEFAULT_SAV = (RAW / "PEW-Global-2025"
               / "Pew Research Center Global Attitudes Spring 2025 Dataset.sav")
DEFAULT_OUT = PROC / "pew_global_2025_full.json"
SOURCE_URL = "https://www.pewresearch.org/global/dataset/spring-2025-survey-data/"

COUNTRY_VAR = "country"
Q_PREFIX = "Q"          # Pew opinion variables carry a "Q.." question label
MIN_BASE = 50           # minimum responses per (question x country) cell

BAD = ["don't know", "dont know", "refused", "no answer", "inapplicable", "no response",
       "declined", "not asked", "missing", "n/a", "haven't heard", "no opinion", "no response"]


DEGENERATE = 0.97   # one option >= this share -> no signal to measure; drop


def is_bad(label: str) -> bool:
    # normalize unicode apostrophes (Pew labels "Don't know" with U+2019) so straight-quote
    # patterns in BAD ("don't know") still match.
    s = str(label).lower().replace("’", "'").replace("‘", "'").replace("`", "'")
    return any(b in s for b in BAD)


def fill_blank_options(opts):
    # anchored numeric scales (e.g. ideology "Extreme left … Extreme right") label only the
    # endpoints; give the blank midpoints a positional label so no option is empty.
    n = len(opts)
    return [o if str(o).strip() else f"(scale point {i + 1} of {n})" for i, o in enumerate(opts)]


# ── text/option cleaning: strip Pew's own placeholders & battery formatting so the stored
# question reads exactly as asked (Q-number, "(SHORTENED)" stem marker, "[ASK IF…]"/"[FORM n]"
# routing tags, battery "b. <item>" prefixes, and option-text survey instructions). ──
def clean_q(s: str) -> str:
    s = re.sub(r"^\s*(?:/?\s*Q\w+)+\.?\s*", "", str(s))             # "Q7b." or split-form "Q34/Q36a."
    s = re.sub(r"\(SHORTENED\)\s*", "", s)                          # "(SHORTENED)"
    # survey-instruction brackets anywhere: [ASK IF…] [SPLIT FORM n] [FORM n] [INSERT…] [SHORTENED]
    s = re.sub(r"\[\s*(ASK IF|SPLIT FORM|FORM|INSERT|SHORTENED|READ|DO NOT READ|VOL)[^\]]*\]\s*", "", s, flags=re.I)
    s = re.sub(r"^\s*(\[[^\]]*\]\s*)+", "", s)                      # any remaining leading bracket marker
    ms = list(re.finditer(r"(?:^|\s)([a-z])\.\s+", s))             # battery item "b. Xi Jinping"
    if ms:
        m = ms[-1]; item = s[m.end():].strip(); stem = s[:m.start()].strip().rstrip(".– ")
        if item:
            s = f"{stem} — {item}" if stem else item
    return re.sub(r"\s+", " ", s).strip()


# ── matrix-label normalization ────────────────────────────────────────────────
# clean_q renders Pew battery items as "<stem> — <item>", but the stem keeps a placeholder
# ("…"/"..."/"each of the following"/"each leader"/"__") and the item is often cut at the SPSS
# ~240-char label limit. We fill the placeholder with the item, restoring truncated items from
# the questionnaire PDF (each battery item there is tagged "(GA 2025 ref: <var>)").
_PRED = r"is|are|was|were|would|will|do|does|did|should|has|have|had|can|could|may|might|applies?"
_UND = re.compile(r"_{2,}")
_PLACEHOLDER = re.compile(r"each of the following.*?(?=,\s|\sto\s|\s(?:" + _PRED + r")\s|\?|$)", re.I)
_THEFOLLOW = re.compile(r"the following\s+(?:statements?|things?|ideas?|items?)", re.I)
_EACHSIMPLE = re.compile(r"each (?:leader|one|country|nation)s?", re.I)
_ELLIP = re.compile(r"\s*(?:…|\.\.\.)\s*")


def load_questionnaire_items(data_dir: Path) -> dict:
    """Map GA-2025 variable -> full battery item text from the questionnaire PDF
    (lines like 'b. China (GA 2025 ref: fav_china)'). {} if pdfplumber/PDF unavailable."""
    if pdfplumber is None:
        return {}
    pdfs = list(data_dir.glob("*Questionnaire*.pdf"))
    if not pdfs:
        return {}
    with pdfplumber.open(str(pdfs[0])) as pdf:
        flat = re.sub(r"\s+", " ", "\n".join((pg.extract_text() or "") for pg in pdf.pages))
    out = {}
    for item, var in re.findall(r"(?:^|\s)[a-z]\.\s+([^()]+?)\s*\(GA \d{4} ref:\s*([a-z0-9_]+)", flat, re.I):
        item = re.sub(r"\s*\[[^\]]*\]\s*", " ", item)          # drop routing "[Ask all in ... only]"
        out[var.lower()] = re.sub(r"\s+", " ", item).strip().rstrip(".,;")
    return out


def _tidy(s: str) -> str:
    s = re.sub(r"\b(?:to|of|as|about|in|for|toward)\s*([?.!,;:])", r"\1", s)  # drop dangling preposition
    s = re.sub(r"\s+([?.!,;:])", r"\1", s)
    return re.sub(r"\s+", " ", s).strip()


def recombine(item: str, stem: str) -> str:
    item, stem = item.strip(), stem.strip()
    # fill the FIRST placeholder (priority: __ > each-of-following-np > the-following-noun > … > each-simple)
    for rx, fill in ((_UND, item), (_PLACEHOLDER, item), (_THEFOLLOW, item), (_ELLIP, " " + item + " "), (_EACHSIMPLE, item)):
        if rx.search(stem):
            stem = rx.sub(fill, stem, count=1)
            break
    else:
        stem = f"{stem}: {item}"
    stem = _ELLIP.sub(" ", _UND.sub(" ", stem))            # clear leftover placeholders (double-placeholder batteries)
    return _tidy(stem)


def splice_options(q: str, options: list) -> str:
    """A forced-choice/scale '…' is a Pew answer placeholder (end OR mid: '...will be…' /
    '...ties with …?'); splice the options in at the '…' so the question reads in full."""
    if "…" not in q or not (2 <= len(options) <= 4):
        return q
    lc = lambda o: o if (len(o) >= 2 and o[:2].isupper()) else (o[:1].lower() + o[1:])
    tail = ", ".join(lc(o) for o in options[:-1]) + ", or " + lc(options[-1])
    out = re.sub(r"\?(\S)", r"? \1", q)
    out = re.sub(r"\s*…\s*", " " + tail + " ", out, count=1)
    out = re.sub(r"\s+([?.!,;:])", r"\1", re.sub(r"\s+", " ", out)).strip()
    return out if out[-1] in "?.!" else out + "?"


def _finish(out: str) -> str:
    return out if (out and out[-1] in '?.!”"…') else out + "?"


def normalize_matrix(q: str, var: str, var2item: dict) -> str:
    """Turn a Pew battery label into a natural question. Handles '<stem> — <item>',
    the letter-less '<stem> …? <item>' variant, and single-var '…'-answer placeholders."""
    # 1) "<stem> — <item>" battery
    parts = re.split(r"\s+[—–]\s+", q, 1)
    if len(parts) == 2:
        stem, item = parts
        item = var2item.get(var.lower()) or item
        item = re.sub(r"\s*\[[^\]]*\]\s*", " ", item).strip()   # drop routing from the sav item too
        return _finish(recombine(item, stem))
    # 2) letter-less item after the placeholder: "<stem> …? <item>" (e.g. some party-fav vars)
    m = re.search(r"(?:…|\.\.\.)\s*\?\s+(\S.*)$", q)
    if m and len(m.group(1).split()) <= 10:
        item = var2item.get(var.lower()) or m.group(1)
        item = re.sub(r"\s*\[[^\]]*\]\s*", " ", item).strip()
        return _finish(recombine(item, q[:m.start()].rstrip() + " …?"))
    # 3) single-variable answer placeholder (the options ARE the answer): keep "…" = "fill from options"
    return re.sub(r"\.\.\.", "…", q)


def clean_opt(o: str) -> str:
    o = re.sub(r"\s*\[[^\]]*\]", "", str(o))                        # "[Include in Australia and the U.S. only]"
    o = re.sub(r"\s*\((DO NOT READ|VOL\.?)\)", "", o, flags=re.I)
    return re.sub(r"\s+", " ", o).strip()


# ── non-opinion items to exclude (demographics / survey admin / conditional-base routing).
# These are not population-level opinion questions, so they don't belong in the opinion bank. ──
_NONOP = re.compile(
    r"gender of respondent|what is your age|\bage\b|highest level of school|level of education|"
    r"household income|your income|marital status|trade union|union member|landline|cell phone|"
    r"telephone use|were you born|citizenship|ethnic|registered residence|apprenticeship|"
    r"belonging to a particular social class|upper-middle class or lower|\[ASK IF|"
    r"not for point|point estimate|only groups with|do not use",
    re.I)
_NONOP_VAR = re.compile(r"^(weight|wt_|d_age_|d_income_|d_educ|d_caste|d_marital|d_relig|gender|age|region|reg_eth|political_scale)(_|$)", re.I)


def is_nonopinion(var: str, qlabel: str) -> bool:
    return bool(_NONOP_VAR.match(var or "")) or bool(_NONOP.search(qlabel or ""))


def find_weight(cols) -> str | None:
    for c in cols:
        if c.lower() in ("weight", "weights", "wt", "weight1", "finalweight", "wtss"):
            return c
    for c in cols:
        if "weight" in c.lower():
            return c
    return None


def build(sav_path: Path, var2item: dict | None = None) -> tuple[list, str]:
    var2item = var2item or {}
    df, meta = pyreadstat.read_sav(str(sav_path))
    print(f"loaded {len(df):,} rows x {len(df.columns)} columns", flush=True)
    vlab = dict(zip(meta.column_names, meta.column_labels))
    vvl = meta.variable_value_labels                       # var -> {code: label}
    wt = find_weight(meta.column_names)

    # opinion questions: value-labelled, Q-prefixed, 2-7 substantive options
    opinion_vars = []
    for v in meta.column_names:
        vl = vvl.get(v)
        qlabel = str(vlab.get(v) or "").strip()
        if not vl or not qlabel:
            continue
        if not re.match(rf"\s*{Q_PREFIX}\d", qlabel):
            continue
        if is_nonopinion(v, qlabel):                       # drop demographics/admin/routing
            continue
        subs = {float(k): clean_opt(l) for k, l in vl.items() if not is_bad(l)}
        if 2 <= len(subs) <= 7:
            opinion_vars.append((v, qlabel, subs))

    clab = vvl.get(COUNTRY_VAR, {})
    cells = []
    for code, cname in clab.items():
        sub = df[df[COUNTRY_VAR] == float(code)]
        if len(sub) < MIN_BASE:
            continue
        for v, q, subs in opinion_vars:
            codes = sorted(subs)
            s = sub[v]
            mask = s.isin(codes)
            if mask.sum() < MIN_BASE:
                continue
            if wt and wt in sub.columns and sub[wt].notna().any():
                w = sub.loc[mask, wt].fillna(1.0).values
                vals = sub.loc[mask, v].values
                d = np.array([w[vals == c].sum() for c in codes], dtype=float)
            else:
                vc = s[mask].value_counts()
                d = np.array([float(vc.get(c, 0)) for c in codes])
            if d.sum() <= 0 or d.max() / d.sum() >= DEGENERATE:   # empty or degenerate
                continue
            qclean = normalize_matrix(clean_q(q) or q, v, var2item)
            opts = fill_blank_options([subs[c] for c in codes])
            cells.append({"var": v, "question": splice_options(qclean, opts), "audience": f"{cname} adults",
                          "options": opts,
                          "distribution": (d / d.sum()).tolist(), "n": int(mask.sum())})
    return cells, (wt or "")


def main():
    ap = argparse.ArgumentParser(description="Build the Pew Global 2025 full question-bank JSON (24 countries).")
    ap.add_argument("--sav", type=Path, default=DEFAULT_SAV, help="Pew Spring 2025 .sav file")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output JSON path")
    args = ap.parse_args()

    if not args.sav.exists():
        raise SystemExit(f"missing raw file: {args.sav}\nDownload the Spring 2025 dataset from {SOURCE_URL}")

    var2item = load_questionnaire_items(args.sav.parent)
    print(f"questionnaire PDF: {len(var2item)} battery items for item restoration"
          if var2item else "questionnaire PDF: unavailable (using SAV item text)", flush=True)
    cells, wt = build(args.sav, var2item)
    audiences = sorted({c["audience"] for c in cells})
    payload = {
        "dataset": "Pew Research Center Global Attitudes — Spring 2025",
        "source_url": SOURCE_URL,
        "fieldwork_year": 2025,
        "audience_type": "per_country",
        "n_audiences": len(audiences),
        "audiences": audiences,
        "weight_variable": wt,
        "question_filter": "Q-prefixed opinion items, 2-7 substantive options, per-country base n>=50, DK/Refused/NA excluded",
        "n_cells": len(cells),
        "n_unique_questions": len({c["question"] for c in cells}),
        "extracted_on": date.today().isoformat(),
        "cells": cells,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    print(f"Pew Global 2025: {len(cells)} cells | {len(audiences)} countries | "
          f"{payload['n_unique_questions']} unique questions -> {args.out}")


if __name__ == "__main__":
    main()
