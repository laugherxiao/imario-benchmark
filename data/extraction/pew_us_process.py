"""pew_us_process.py — build the US question bank from the Pew American Trends Panel US Global
Attitudes survey (ATP Wave 145, fielded Apr 2024, n≈3,600), using the FULL questionnaire.

WHY THIS EXISTS
  Pew's international Global Attitudes file excludes the US (country code 1 is dropped; the 24
  public countries are codes 2-25). The US is fielded separately on the ATP. We measure the US
  synthetic population against the US's OWN full survey — exactly like CN=CGSS, UK=Pew-intl,
  etc. — NOT a cross-country subset. Every value-labelled opinion item with 2-7 substantive
  options becomes one cell; ATP demographic/profile/admin variables (F_*, weights, device, etc.)
  are excluded. ANES stays the US qualitative source.

RAW DATA — download from the official source first (free Pew account required)
  Pew American Trends Panel Wave 145 (Global Attitudes US 2024):
    https://www.pewresearch.org/dataset/american-trends-panel-wave-145/
  Drop the .sav in:  ../Pew-US-ATP/

RUN
  conda activate imario
  python data/extraction/pew_us_process.py
  # or a custom folder:
  python data/extraction/pew_us_process.py --dir "/path/to/us_sav_folder"

OUTPUT
  data/processed/pew_US_full.json   (audience = "United States adults")
"""
from __future__ import annotations
import argparse, json, re
from datetime import date
from pathlib import Path

import numpy as np
import pyreadstat
try:
    import pdfplumber
except ImportError:                      # PDF stem-restoration is optional
    pdfplumber = None

HERE = Path(__file__).resolve().parent
IB = HERE.parent.parent
RAW = IB / "data" / "raw"
PROC = IB / "data" / "processed"

DEFAULT_DIR = RAW / "PEW-US-W145_Apr24"
DEFAULT_OUT = PROC / "pew_US_full.json"
SOURCE_URL = "https://www.pewresearch.org/dataset/american-trends-panel-wave-145/"
MIN_BASE = 50

# non-substantive answer options — drop them, then keep questions with 2-7 real options left
BAD = ["don't know", "dont know", "refused", "no answer", "inapplicable", "no response",
       "declined", "not asked", "missing", "n/a", "no opinion", "skipped on web", "not sure"]

# ATP profile / admin / weighting variables — NOT survey opinion questions
ADMIN = re.compile(
    r"^(F_|WEIGHT|DEVICE|FORM|LANG|XW\d|DOV_|QKEY|XTABLET|XSPANISH|XHARDREFUSE|XMODE|"
    r"XTHANK|XWELCOME|XCONSENT|RESP|XID|XATTEMPT|XPANEL|XSAMPLE|XCASE|XBATCH)", re.I)


DEGENERATE = 0.97   # one option >= this share -> no signal to measure; drop


def is_bad(label: str) -> bool:
    s = str(label).lower().replace("’", "'").replace("‘", "'").replace("`", "'")
    return any(b in s for b in BAD)


def fill_blank_options(opts):
    n = len(opts)
    return [o if str(o).strip() else f"(scale point {i + 1} of {n})" for i, o in enumerate(opts)]


def base_name(n: str) -> str:
    return re.sub(r"_w\d+$", "", str(n).strip().lower())


def find_weight(cols) -> str | None:
    pref = [c for c in cols if c.lower() in ("weight", "weights", "wt", "finalweight")]
    if pref:
        return pref[0]
    cand = [c for c in cols if "weight" in c.lower()]
    return cand[0] if cand else None


def clean_q(label: str, var: str) -> str:
    q = str(label or "").strip()
    # ATP labels sometimes prefix the var token, e.g. "ECON_SIT. How would you ..."
    q = re.sub(rf"^\s*{re.escape(base_name(var))}\.?\s*", "", q, flags=re.I)
    q = re.sub(r"^\s*/?\s*[A-Za-z0-9_]+\.\s+", "", q)           # var token incl. lowercase (NEWSSOURCEe_W124.) or "/Q36a."
    # Pew placeholders / battery formatting (same as the Global file)
    q = re.sub(r"\(SHORTENED\)\s*", "", q)
    q = re.sub(r"\[\s*(ASK IF|SPLIT FORM|FORM|INSERT|SHORTENED|READ|DO NOT READ|VOL)[^\]]*\]\s*", "", q, flags=re.I)
    q = re.sub(r"^\s*(\[[^\]]*\]\s*)+", "", q)
    ms = list(re.finditer(r"(?:^|\s)([a-z])\.\s+", q))
    if ms:
        m = ms[-1]; item = q[m.end():].strip(); stem = q[:m.start()].strip().rstrip(".– ")
        if item:
            q = f"{stem} — {item}" if stem else item
    return re.sub(r"\s+", " ", q).strip() or str(label).strip()


# ── matrix-label normalization ────────────────────────────────────────────────
# Pew ATP variable labels store battery items as "<item> // <shared stem>", and long
# stems are cut at the SPSS ~240-char label limit (e.g. "...think each of the followin").
# We turn each into a natural question, restoring truncated stems from the questionnaire PDF.
_PRED = r"is|are|was|were|would|will|do|does|did|should|has|have|had|can|could|may|might"
# placeholder = "each of the following" + optional noun phrase, up to a comma / " to " (infinitive)
# / a predicate verb / "?" / string end. A lone "." is NOT a boundary, so "in the U.S.?" is intact.
_PLACEHOLDER = re.compile(
    r"each of the following.*?(?=,\s|\sto\s|\s(?:" + _PRED + r")\s|\?|$)", re.I)
_STOP = re.compile(
    r"\b(RANDOMIZE|RESPONSE OPTIONS|PROGRAMMING|PIN |ASK |SHOW |DISPLAY|FORM \d|SCALE)|\[")


def load_questionnaire(data_dir: Path) -> tuple[str, dict]:
    """Flattened ATP questionnaire text (to restore SPSS-truncated stems) and a var->item map.
    ATP items are tagged 'VARNAME. <item>' (e.g. 'CONFID_XI. Chinese President Xi Jinping'), which
    lets us restore items the label truncated. Returns ('', {}) if pdfplumber/PDF unavailable."""
    if pdfplumber is None:
        return "", {}
    pdfs = list(data_dir.glob("*Questionnaire*.pdf"))
    if not pdfs:
        return "", {}
    with pdfplumber.open(str(pdfs[0])) as pdf:
        raw = "\n".join((pg.extract_text() or "") for pg in pdf.pages)
    flat = re.sub(r"\s+", " ", raw)
    items = {}
    for var, item in re.findall(
            r"\b([A-Z][A-Z0-9_]{2,})\.\s+([^.]+?)(?=\s+[A-Z][A-Z0-9_]{2,}\.|\s+(?:RANDOMIZE|SPLIT|SHOW|PROGRAMMING|RESPONSE|DISPLAY)|$)",
            flat):
        v = re.sub(r"_w\d+$", "", var.strip().lower())
        items.setdefault(v, re.sub(r"\s+", " ", item).strip().rstrip(".,;"))
    return flat, items


def _is_truncated(stem: str) -> bool:
    # a complete matrix stem ends in '?' / '…' / punctuation; a bare letter = SPSS cut mid-word
    s = stem.rstrip()
    return bool(s) and s[-1].isalpha() and not s.endswith("…")


def _pdf_complete(stem_trunc: str, pdf_flat: str):
    """Locate the full stem in the questionnaire by the truncated stem's clean prefix."""
    if not pdf_flat:
        return None
    pre = re.sub(r"\s+\S*$", "", stem_trunc.rstrip())        # drop trailing partial word
    pre = re.sub(r"\s+", " ", pre)[:70]
    idx = pdf_flat.find(pre)
    if idx < 0:
        idx = pdf_flat.find(re.sub(r"\s+", " ", stem_trunc)[:45])
        if idx < 0:
            return None
    tail = pdf_flat[idx:idx + 400]
    m = re.search(r"\?", tail)                                # stem ends at the first "?"
    if m:
        return tail[:m.end()].strip()
    m = _STOP.search(tail)                                    # else at a control/instruction token
    return tail[:m.start()].strip() if m else None


def _recombine(item: str, stem: str) -> str:
    item, stem = item.strip(), stem.strip()
    core = re.sub(r"\s*(?:…|\.\.\.)\s*$", "", stem).strip()  # strip trailing ellipsis up front
    had_ellipsis = core != stem
    # 1) "each of the following <np>" placeholder -> item (keeps trailing predicate/clause)
    if _PLACEHOLDER.search(core):
        out = re.sub(r"\s+", " ", _PLACEHOLDER.sub(item, core, count=1)).strip()
        if had_ellipsis and out and out[-1].isalpha():
            out += "…"        # stem was "…-then-options" (e.g. "...has been…"); keep it
        return out
    # 2) generic "the following [things]" -> item
    if re.search(r"the following", core, re.I):
        return re.sub(r"\s+", " ", re.sub(r"the following(\s+things)?", item, core, count=1, flags=re.I)).strip()
    # 3) trailing ellipsis, no placeholder -> append item ("...opinion of" + "China")
    if had_ellipsis:
        return re.sub(r"\s+", " ", f"{core} {item}").strip()
    # 4) fallback
    return f"{core}: {item}"


def splice_options(q: str, options: list) -> str:
    """A forced-choice/scale '…' is a Pew answer placeholder (end OR mid: '...will be…' /
    '...ties with …?'); splice the options in at the '…' so the question reads in full."""
    if "…" not in q or not (2 <= len(options) <= 4):
        return q
    lc = lambda o: o if (len(o) >= 2 and o[:2].isupper()) else (o[:1].lower() + o[1:])
    tail = ", ".join(lc(o) for o in options[:-1]) + ", or " + lc(options[-1])
    out = re.sub(r"\?(\S)", r"? \1", q)                          # fix "?Democracy" spacing
    out = re.sub(r"\s*…\s*", " " + tail + " ", out, count=1)     # splice at the "…"
    out = re.sub(r"\s+([?.!,;:])", r"\1", re.sub(r"\s+", " ", out)).strip()
    return out if out[-1] in "?.!" else out + "?"


def normalize_matrix(q: str, var: str = "", pdf_flat: str = "", var2item: dict | None = None) -> str:
    """Turn a Pew-ATP battery label into a natural question. Handles the W145 style
    '<item> // <stem>' and the W124/2023 style where the item sits after the placeholder or was
    truncated away (restored from the PDF's 'VARNAME. <item>' map)."""
    var2item = var2item or {}
    if " // " in q:                                          # W145 style: <item> // <stem>
        item, stem = q.split(" // ", 1)
        item, stem = item.strip(), stem.strip()
        if _is_truncated(stem):
            full = _pdf_complete(stem, pdf_flat)
            if full:
                stem = full
    else:                                                    # W124 style
        item = var2item.get(base_name(var).lower())
        if item:                                             # authoritative PDF item -> also restore the full stem
            stem = _pdf_complete(q, pdf_flat) or q           # (handles items AND stems the label truncated)
        elif re.search(r"…|each of the following", q):       # no PDF item: text after the placeholder IS the item
            m = re.search(r"(?:…|each of the following[^?]*\??)\s+(\S.+)$", q)
            if not m:
                return q
            item, stem = m.group(1).strip(), q[:m.start(1)].strip()
        else:
            return q
    out = _recombine(item, stem)
    out = re.sub(r"\bto do ([A-Z])", r"to \1", out)          # "best age to do Get married" -> "to Get married"
    if out and out[-1] not in '?.!”"…':
        out += "?"
    return out


def clean_opt(o: str) -> str:
    o = re.sub(r"\s*\[[^\]]*\]", "", str(o))
    o = re.sub(r"\s*\((DO NOT READ|VOL\.?)\)", "", o, flags=re.I)
    return re.sub(r"\s+", " ", o).strip()


# content-level non-opinion items the ATP ADMIN regex doesn't catch (e.g. subjective social-class
# self-placement, education/income/marital follow-ups)
_NONOP = re.compile(
    r"belonging to a particular social class|upper-middle class or lower|gender of respondent|"
    r"what is your age|highest level of school|household income|marital status|\[ASK IF", re.I)


def is_nonopinion(qlabel: str) -> bool:
    return bool(_NONOP.search(qlabel or ""))


def build_us(sav_path: Path, pdf_flat: str = "", var2item: dict | None = None):
    var2item = var2item or {}
    df, meta = pyreadstat.read_sav(str(sav_path))
    print(f"loaded {len(df):,} rows x {len(df.columns)} columns", flush=True)
    vvl = meta.variable_value_labels
    vlab = dict(zip(meta.column_names, meta.column_labels))
    wt = find_weight(meta.column_names)

    cells = []
    for v in meta.column_names:
        if ADMIN.search(v):
            continue
        vl = vvl.get(v)
        qlabel = str(vlab.get(v) or "").strip()
        if not vl or not qlabel:
            continue
        if is_nonopinion(qlabel):                          # drop demographics/admin/routing
            continue
        subs = {float(k): clean_opt(l) for k, l in vl.items() if not is_bad(l)}
        if not (2 <= len(subs) <= 7):
            continue
        codes = sorted(subs)
        s = df[v]
        mask = s.isin(codes)
        if mask.sum() < MIN_BASE:
            continue
        if wt and wt in df.columns and df[wt].notna().any():
            w = df.loc[mask, wt].fillna(1.0).values
            vals = df.loc[mask, v].values
            d = np.array([w[vals == c].sum() for c in codes], dtype=float)
        else:
            vc = s[mask].value_counts()
            d = np.array([float(vc.get(c, 0)) for c in codes])
        if d.sum() <= 0 or d.max() / d.sum() >= DEGENERATE:
            continue
        opts = fill_blank_options([subs[c] for c in codes])
        cells.append({"var": base_name(v),
                      "question": splice_options(normalize_matrix(clean_q(qlabel, v), v, pdf_flat, var2item), opts),
                      "audience": "United States adults", "options": opts,
                      "distribution": (d / d.sum()).tolist(), "n": int(mask.sum())})
    return cells, (wt or "")


def main():
    ap = argparse.ArgumentParser(description="Build the US Pew-ATP (W145) FULL question bank.")
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR, help="folder with the ATP W145 .sav")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output JSON path")
    args = ap.parse_args()

    if not args.dir.exists():
        raise SystemExit(f"missing US data folder: {args.dir}\nDownload ATP W145 (free Pew account): {SOURCE_URL}")
    savs = sorted(args.dir.glob("*.sav"))
    if not savs:
        raise SystemExit(f"no .sav files found in {args.dir}")

    pdf_flat, var2item = load_questionnaire(args.dir)
    print(f"questionnaire PDF: {f'loaded ({len(var2item)} items) for stem/item restoration' if pdf_flat else 'unavailable (skipping PDF completion)'}", flush=True)

    all_cells, wt = [], ""
    seen = set()
    for sav in savs:
        cells, w = build_us(sav, pdf_flat, var2item)
        wt = wt or w
        for c in cells:
            if c["var"] in seen:
                continue
            seen.add(c["var"])
            all_cells.append(c)
        print(f"  {sav.name}: weight={w or 'none'} | {len(cells)} opinion questions", flush=True)

    payload = {
        "dataset": "Pew Research Center — American Trends Panel Wave 145 (Global Attitudes US, 2024)",
        "source_url": SOURCE_URL,
        "fieldwork_year": 2024,
        "audience_type": "per_country",
        "n_audiences": 1,
        "audiences": ["United States adults"],
        "weight_variable": wt,
        "question_filter": "value-labelled opinion items, 2-7 substantive options, base n>=50, "
                           "ATP profile/admin vars (F_*, weights, device) excluded, DK/Refused dropped",
        "n_cells": len(all_cells),
        "n_unique_questions": len({c["question"] for c in all_cells}),
        "extracted_on": date.today().isoformat(),
        "cells": all_cells,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    print(f"\nUS Pew-ATP W145: {len(all_cells)} opinion questions -> {args.out}")


if __name__ == "__main__":
    main()
