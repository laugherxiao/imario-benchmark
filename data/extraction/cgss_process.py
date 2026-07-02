"""cgss_process.py — turn the raw CGSS (Chinese General Social Survey) .dta download into one
full question-bank JSON. Audience is fixed to "China adults".

WHAT THIS DOES
  Reads the labeled Stata .dta file, finds every OPINION question (a value-labelled item with
  2-7 substantive options; 不知道/拒绝/不适用/缺失 etc. dropped), and computes the WEIGHTED
  response distribution over the substantive options. One cell per question.

  Processes the 2023 wave — the current test / ground-truth wave shipped in this public benchmark.

RAW DATA — download from the official source first
  CGSS is distributed by the Chinese National Survey Data Archive (CNSDA) / Renmin University:
    http://cgss.ruc.edu.cn/   |   https://www.cnsda.org/
  After download you need the Stata file (default location: ../CGSS/):
    - CGSS2023.dta

RUN
  conda activate imario
  python data/extraction/cgss_process.py                 # CGSS 2023
  python data/extraction/cgss_process.py --dta /path/to/CGSS2023.dta

OUTPUT
  data/processed/cgss_2023_full.json
"""
from __future__ import annotations
import argparse, json
from datetime import date
from pathlib import Path

import numpy as np
import pyreadstat

HERE = Path(__file__).resolve().parent
IB = HERE.parent.parent
RAW = IB / "data" / "raw"
PROC = IB / "data" / "processed"
SOURCE_URL = "http://cgss.ruc.edu.cn/"
MIN_BASE = 50

# answer labels that are NOT a substantive opinion (dropped before building the distribution).
# Kept in sync with the canonical builder so the pool matches the ingested prior library.
BAD = ["不知道", "拒绝", "不适用", "无法回答", "未回答", "未调查", "电话调查", "电调", "跳过", "跳答",
       "缺失", "不回答", "说不清", "本人无法回答", "不清楚",
       "don't know", "dont know", "refused", "no answer", "inapplicable", "no response",
       "declined", "not asked", "missing", "n/a", "na ", "haven't heard", "no opinion"]

DEGENERATE = 0.97   # one option >= this share -> no signal to measure; drop (per public benchmark policy)


def is_bad(label: str) -> bool:
    s = str(label)
    return any(b in s for b in BAD)


# CGSS demographic / administrative / profile variables — factual attributes, not opinions.
# Subjective self-placement (社会经济地位) and political participation (投票) are KEPT as opinion/behaviour.
import re as _re
_CN_DEMO = _re.compile(
    r"户口|政治面貌|工作.{0,3}(性质|经历|状况|单位)|单位或公司|居委会/村委会|居委会还是村委会|哪一年|第一次结婚|转为居民|"
    r"兼.{0,3}多份工作|社会保障|养老保险|医疗保险|公费医疗|教育程度|婚姻状况|^性别|"
    r"拥有.{0,4}(汽车|手机|住房)|单独使用的手机|工会会员|居住的地区属于|目前是否参加了以下社会保障|"
    r"配偶.{0,8}(政治面貌|工作|性质)|父亲|母亲|您的职业|雇有雇员|调查方式|"
    r"第\d+个?家庭成员|家庭成员.{0,4}(住在一起|住一起|与您住)|同住的家庭成员|他们都是哪些人|"
    r"几个.{0,10}(儿子|女儿|子女|孩子|兄弟|姐妹|人)|有几个|管理活动情况|管多少人|管理多少人|"
    r"^甲|^乙|甲的|乙的|多少钱|多少元|收入是多少|几套房|几处房|房子的产权|这座房子|产权属|拥有.{0,4}房")
_CN_KEEP = _re.compile(r"社会经济地位|是否参加了投票")


def clean_q(s: str) -> str:
    # Stata truncates long Chinese variable labels (80-byte limit), so battery items are stored as
    # "[N. <item>] <Q-code>. <stem-truncated>" — the distinguishing item lives ONLY in the leading
    # bracket. PRESERVE it (append to the stem) so different battery items stay DISTINCT; stripping it
    # collapses e.g. A28_1(报纸)/A28_2(杂志)/A30_3(逛街) into one identical stem -> wrong prior matches.
    s = str(s)
    s = _re.sub(r"^\s*\[\s*\]\s*", "", s)                      # empty bracket "[]" (truncated-away item)
    item = None
    # battery item lives in the leading bracket — either numbered "[3. item]" (2023) or bare
    # "[item]" (2021). Number is optional so BOTH waves get the item preserved + Q-code stripped.
    # leading "[N. item]" — allow an UNCLOSED bracket (Stata truncates at 80 bytes mid-item)
    m = _re.match(r"^\s*\[\s*([^\]]+?)\s*(?:\]|$)", s)
    if m:
        # item may be prefixed by a battery code: "C202." / "A." / "6."
        item = _re.sub(r"^(?:[A-Za-z]+\d*|\d+)[a-z]?[\.、\s]+", "", m.group(1).strip())
        s = s[m.end():]
    s = _re.sub(r"^\s*[A-Za-z]{1,4}\d*[a-z_]*[\.：:]\s*", "", s)   # Q-code "A30." "E36." "H12" "C2." "P12："
    s = _re.sub(r"\s+", " ", s).strip()
    # 2021 stems are often truncated to a bare code/fragment; then the item (a statement) IS the question
    if item and (len(s) < 6 or _re.match(r"^[A-Za-z0-9]+$", s)):
        return item.strip()
    s = _re.sub(r"\s+", " ", s).strip()
    # the battery item may also be an inline "…以下X…-item" hyphen already in the raw label
    if item is None:
        hm = _re.match(r"^(.*以下.*?)[-－]([^-－]{1,40})$", s)
        if hm:
            s, item = hm.group(1).strip(), hm.group(2).strip()
    if item:
        if not s:
            s = item
        else:
            # fill the "以下{X}" placeholder with the battery item; else attach with a colon
            m2 = _re.search(r"以下[一-鿿]{1,4}?(?=的|[，,：:、。]|$)", s)
            s = (s[:m2.start()] + item + s[m2.end():]) if m2 else f"{s}：{item}"
    return _re.sub(r"\s+", " ", s).strip()


def is_nonopinion(q: str) -> bool:
    q = str(q)
    return bool(_CN_DEMO.search(q)) and not bool(_CN_KEEP.search(q))


def find_weight(cols) -> str | None:
    for c in cols:
        if c.lower() in ("weight", "weights", "wt", "wtss", "weight_raw", "wr"):
            return c
    for c in cols:
        if "weight" in c.lower():
            return c
    return None


def build(dta_path: Path) -> tuple[list, str]:
    df, meta = pyreadstat.read_dta(str(dta_path))
    print(f"loaded {len(df):,} rows x {len(df.columns)} columns", flush=True)
    vlab = dict(zip(meta.column_names, meta.column_labels))
    vvl = meta.variable_value_labels                       # var -> {code: label}
    wt = find_weight(meta.column_names)

    cells = []
    for v in meta.column_names:
        vl = vvl.get(v)
        if not vl:
            continue
        # clean FIRST, then test for non-opinion on the CLEANED text — the distinguishing battery item
        # (甲的/管理活动/几个儿子/房子产权…) only appears after clean_q appends "[N. item]" to the stem.
        q = clean_q(vlab.get(v) or v) or str(vlab.get(v) or v).strip()
        if len(q) < 4 or is_nonopinion(q):                 # empty stem / demographics / admin
            continue
        subs = {float(k): str(l) for k, l in vl.items() if not is_bad(l)}
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
        if d.sum() <= 0 or d.max() / d.sum() >= DEGENERATE:   # empty or degenerate (one option ~all)
            continue
        if len(set(subs[c] for c in codes)) != len(codes):    # duplicate option labels -> malformed
            continue
        cells.append({"var": v, "question": q, "audience": "China adults",
                      "options": [subs[c] for c in codes],
                      "distribution": (d / d.sum()).tolist(), "n": int(mask.sum())})
    return cells, (wt or "")


def main():
    ap = argparse.ArgumentParser(description="Build the CGSS full question-bank JSON (China adults).")
    ap.add_argument("--year", type=int, default=2023, help="CGSS wave (default 2023)")
    ap.add_argument("--dta", type=Path, default=None, help="explicit .dta path (overrides --year)")
    ap.add_argument("--out", type=Path, default=None, help="output JSON path (default data/cgss_<year>_full.json)")
    args = ap.parse_args()

    # public benchmark ships only the current test wave (CGSS 2023). Earlier waves (2021/2018) are
    # rebuilt in the private calibration library, not in this public repo.
    if args.dta:
        dta = args.dta
    elif args.year == 2023:
        dta = RAW / "CGSS-2023" / "CGSS2023.dta"
    else:
        raise SystemExit(f"CGSS {args.year} is an earlier wave — processed in the private calibration "
                         f"library, not this public benchmark repo (which ships only the 2023 test wave).")
    out = args.out or (PROC / f"cgss_{args.year}_full.json")
    if not dta.exists():
        raise SystemExit(f"missing raw file: {dta}\nDownload CGSS {args.year} from {SOURCE_URL}")

    cells, wt = build(dta)
    payload = {
        "dataset": f"CGSS {args.year} (Chinese General Social Survey)",
        "source_url": SOURCE_URL,
        "fieldwork_year": args.year,
        "audience_type": "national",
        "audiences": ["China adults"],
        "weight_variable": wt,
        "question_filter": "value-labelled opinion items, 2-7 substantive options, base n>=50, DK/Refused/NA excluded",
        "n_cells": len(cells),
        "n_unique_questions": len({c["question"] for c in cells}),
        "extracted_on": date.today().isoformat(),
        "cells": cells,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    print(f"CGSS {args.year}: {len(cells)} cells | {payload['n_unique_questions']} unique questions -> {out}")


if __name__ == "__main__":
    main()
