"""score.py — reproduce the iMario benchmark's headline number from the PUBLISHED per-person
answers, with ZERO dependencies beyond the Python standard library.

This is the anti-cherry-pick audit tool. It does NOT call any iMario service or model — it takes
the synthetic answers we already published (one row per simulated person) and re-derives every
score locally, so you can confirm our numbers are the honest aggregate of individual answers and
not a hand-picked distribution.

For each population under verification/<pop>/ it reads:
    questions.json          {qid: {"question": ..., "options": [...]}}
    real_distribution.json  {qid: [real probability per option, aligned to options]}
    synthetic_answers.jsonl {"persona_id": ..., "answers": {qid: chosen option text}}

then AGGREGATES the individual answers into a synthetic distribution and scores it against the
real distribution with the exact metric the benchmark reports:
    TVD  = 0.5 * Σ |real_i - synth_i|      (total variation distance)
    1-TV = 1 - TVD                          (raw 1-TV — the headline number, per question)
population score = mean of per-question 1-TV, with a 95% confidence interval.

Run:
    python score.py                 # every population under verification/
    python score.py CN UK           # only these
    python score.py --per-question CN   # also dump each question's score
"""
import json
import sys
import math
import argparse
from pathlib import Path
from collections import Counter

HERE = Path(__file__).resolve().parent
VDIR = HERE / "verification"


def tvd(real: dict, synth: dict, keys: list) -> float:
    """Total variation distance between two distributions over the same option keys."""
    return 0.5 * sum(abs(real.get(k, 0.0) - synth.get(k, 0.0)) for k in keys)


def mean_ci(xs: list):
    """Mean and 95% confidence interval half-width."""
    n = len(xs)
    if n == 0:
        return 0.0, 0.0
    m = sum(xs) / n
    sd = (sum((x - m) ** 2 for x in xs) / (n - 1)) ** 0.5 if n > 1 else 0.0
    return m, (1.96 * sd / math.sqrt(n) if n > 1 else 0.0)


def _score_quant(d: Path, pop: str) -> dict:
    """Closed questions: aggregate each person's chosen option into a synthetic distribution,
    score it against the real distribution."""
    questions = json.loads((d / "questions.json").read_text())          # qid -> {question, options}
    real_raw = json.loads((d / "real_distribution.json").read_text())   # qid -> [probs]

    counts = {qid: Counter() for qid in questions}
    n_units = 0
    for line in (d / "synthetic_answers.jsonl").read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        n_units += 1
        for qid, ans in (rec.get("answers") or {}).items():
            if qid not in questions or ans is None:
                continue
            opts = questions[qid]["options"]
            if ans in opts:                                    # answer text is drawn from options
                counts[qid][str(opts.index(ans) + 1)] += 1

    per_q = []
    for qid, qinfo in questions.items():
        opts = qinfo["options"]
        keys = [str(i + 1) for i in range(len(opts))]
        cnt = counts[qid]
        tot = sum(cnt.values())
        if tot == 0:                                           # nobody answered -> not scorable
            continue
        synth = {k: cnt.get(k, 0) / tot for k in keys}
        real = {str(i + 1): float(real_raw[qid][i]) for i in range(len(opts))}
        per_q.append({"qid": qid, "n": tot, "one_tv": 1 - tvd(real, synth, keys)})

    m, c = mean_ci([q["one_tv"] for q in per_q])
    return {"pop": pop, "kind": "quant", "n_units": n_units, "n_questions": len(per_q),
            "raw_1tv": m, "raw_1tv_ci": c, "per_q": per_q}


def _score_qual(d: Path, pop: str) -> dict:
    """Open-ended questions: aggregate each person's assigned codes into a mention-share
    distribution over the codebook, score it against the real (ANES) gold coded-shares."""
    gold = json.loads((d / "gold_shares.json").read_text())             # q -> {category: share}

    codes_by_q = {q: [] for q in gold}
    seen = set()
    for line in (d / "synthetic_verbatims.jsonl").read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        seen.add(rec.get("persona_id"))
        for q, ans in (rec.get("open") or {}).items():
            if q in codes_by_q and ans and ans.get("codes"):
                codes_by_q[q].append(ans["codes"])

    per_q = []
    for q, gshares in gold.items():
        cats = list(gshares.keys())
        counts = {cat: 0.0 for cat in cats}
        for codes in codes_by_q[q]:
            for cat in codes:
                if cat in counts:
                    counts[cat] += 1.0
        tot = sum(counts.values())
        if tot == 0:
            continue
        synth = {cat: counts[cat] / tot for cat in cats}       # mention-share over the codebook
        goldd = {cat: float(gshares.get(cat, 0.0)) for cat in cats}
        per_q.append({"qid": q, "n": len(codes_by_q[q]), "one_tv": 1 - tvd(goldd, synth, cats)})

    m, c = mean_ci([x["one_tv"] for x in per_q])
    return {"pop": pop, "kind": "qual", "n_units": len(seen), "n_questions": len(per_q),
            "raw_1tv": m, "raw_1tv_ci": c, "per_q": per_q}


def score_pop(pop: str) -> dict:
    """Score one bundle. Detects quant (per-person option answers) vs qual (per-person verbatims)."""
    d = VDIR / pop
    if (d / "synthetic_verbatims.jsonl").exists():
        return _score_qual(d, pop)
    return _score_quant(d, pop)


def main():
    ap = argparse.ArgumentParser(description="Recompute the iMario benchmark raw 1-TV from published per-person answers.")
    ap.add_argument("pops", nargs="*", help="populations to score (default: all under verification/)")
    ap.add_argument("--per-question", action="store_true", help="also print each question's 1-TV")
    args = ap.parse_args()

    if not VDIR.exists():
        raise SystemExit(f"no verification/ directory at {VDIR}")
    pops = args.pops or sorted(p.name for p in VDIR.iterdir() if p.is_dir())

    print(f"{'population':16}{'kind':>6}{'n':>7}{'questions':>11}{'raw 1-TV':>12}")
    print("-" * 53)
    scored = []
    for pop in pops:
        try:
            s = score_pop(pop)
        except FileNotFoundError:
            print(f"{pop:16}{'(no bundle)':>29}")
            continue
        scored.append(s)
        print(f"{pop:16}{s['kind']:>6}{s['n_units']:7}{s['n_questions']:11}{s['raw_1tv'] * 100:10.1f}% ±{s['raw_1tv_ci'] * 100:.1f}")
        if args.per_question:
            for q in s["per_q"]:
                print(f"    {q['qid']:30} n={q['n']:<5} 1-TV={q['one_tv'] * 100:5.1f}%")

    quant = [s for s in scored if s["kind"] == "quant"]
    if len(quant) > 1:
        overall = sum(s["raw_1tv"] for s in quant) / len(quant)
        print("-" * 53)
        print(f"{'MEAN (quant)':16}{'':6}{'':7}{'':11}{overall * 100:10.1f}%")


if __name__ == "__main__":
    main()
