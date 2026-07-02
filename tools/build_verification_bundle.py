"""build_verification_bundle.py — MAINTAINER-ONLY tool.

Extract the PUBLIC verification bundle from an internal results/<version>/ run. Reads the
(gitignored) per-person artifacts and emits the clean, publishable verification/<pop>/ files that
the top-level score.py consumes.

What it publishes per population (verification/<pop>/):
    questions.json          qid -> {question, options}
    real_distribution.json  qid -> [real probs aligned to options]
    synthetic_answers.jsonl one row per simulated person: {persona_id, answers:{qid: option text}}
    personas.json           persona_id -> sampling attributes (age/gender/region/... only)

Deliberately STRIPPED (internal / not publishable): persona embeddings, full deep-persona text,
reflection notes, seeds. We keep the SAMPLING ATTRIBUTES so anyone can audit that the cohort's
composition matches the target quotas — that plus the per-person answers is the full anti-cherry-
pick evidence chain (answers can be re-aggregated into the distribution locally by score.py).

Run:
    python tools/build_verification_bundle.py --version v1
    python tools/build_verification_bundle.py --version v1 --pops CN UK
"""
import json
import argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent
IB = HERE.parent
RESULTS = IB / "results"
VDIR = IB / "verification"

# Populations published in the benchmark (source names as they appear in results/prod_v1). US quant
# is fielded as "US_pew" (US adults answering the Pew Global items) and published under "US".
POPS = ["US_pew", "UK", "CN", "India", "Japan", "Brazil", "France", "Germany",
        "Australia", "SouthKorea", "SO"]
DISPLAY = {"US_pew": "US"}   # internal result name -> published bundle directory name

# Open-ended (qualitative) questions — US only, coded against the ANES 2024 open-ends gold.
QUAL_QS = {
    "like_dem_candidate":    "Is there anything in particular about Kamala Harris, the Democratic presidential candidate, that might make you want to vote FOR her?",
    "dislike_dem_candidate": "Is there anything in particular about Kamala Harris that might make you want to vote AGAINST her?",
    "like_rep_candidate":    "Is there anything in particular about Donald Trump, the Republican presidential candidate, that might make you want to vote FOR him?",
    "dislike_rep_candidate": "Is there anything in particular about Donald Trump that might make you want to vote AGAINST him?",
    "like_dem_party":        "Is there anything in particular that you LIKE about the Democratic Party?",
    "dislike_dem_party":     "Is there anything in particular that you DON'T LIKE about the Democratic Party?",
    "like_rep_party":        "Is there anything in particular that you LIKE about the Republican Party?",
    "dislike_rep_party":     "Is there anything in particular that you DON'T LIKE about the Republican Party?",
}

def _attrs(sd: dict) -> dict:
    """Publishable sampling attributes: the structured quota COORDINATES the person was sampled
    into — the diversity dimensions the cohort was stratified on (they vary by population:
    urbanicity/region/education/hukou/ethnicity/... for CN, etc.). Anyone can tally these to audit
    that the cohort composition matches the target quotas.

    We deliberately do NOT publish the LLM-generated name / age / gender / free-text life story:
    those are free generation, not sampling controls, and are not what the benchmark binds answers
    to — publishing them would introduce apparent (but spurious) persona-vs-answer contradictions."""
    return dict((sd.get("sampling_point") or {}).get("coordinates") or {})


def build_pop(version: str, pop: str) -> bool:
    src = RESULTS / version
    dist_f = src / f"distributions_{pop}.json"
    resp_f = src / f"responses_{pop}.jsonl"
    cohort_f = src / f"cohort_{pop}.json"
    if not dist_f.exists() or not resp_f.exists():
        print(f"  {pop:12} SKIP (missing distributions/responses)")
        return False

    out = VDIR / DISPLAY.get(pop, pop)
    out.mkdir(parents=True, exist_ok=True)

    dists = json.loads(dist_f.read_text())
    questions = {c["qid"]: {"question": c["q"], "options": c["options"]} for c in dists}
    real = {c["qid"]: c["real"] for c in dists}
    (out / "questions.json").write_text(json.dumps(questions, ensure_ascii=False, indent=1))
    (out / "real_distribution.json").write_text(json.dumps(real, ensure_ascii=False, indent=1))

    # per-person answers: publish verbatim — this is the evidence score.py re-aggregates
    (out / "synthetic_answers.jsonl").write_text(resp_f.read_text())

    # persona sampling attributes (strip internal fields)
    if cohort_f.exists():
        personas = {}
        for i, sd in enumerate(json.loads(cohort_f.read_text()).get("personas", [])):
            personas[f"{pop}_{i}"] = _attrs(sd)
        (out / "personas.json").write_text(json.dumps(personas, ensure_ascii=False, indent=1))

    print(f"  {DISPLAY.get(pop, pop):12} {len(questions):4} questions -> verification/{DISPLAY.get(pop, pop)}/")
    return True


def build_qual(version: str) -> bool:
    """US qualitative (open-ended) bundle: per-person verbatims + their ANES-codebook codes, plus
    the real ANES gold coded-shares. score.py re-aggregates the codes into a mention-share
    distribution and scores it against gold — the open-question analogue of the quant path. The
    verbatims themselves are the strongest anti-cherry-pick evidence for the qualitative claim."""
    src = RESULTS / version
    dist_f = src / "distributions_qual_US.json"
    resp_f = src / "responses_qual_US.jsonl"
    if not dist_f.exists() or not resp_f.exists():
        print("  US_qual      SKIP (missing distributions_qual_US/responses_qual_US)")
        return False
    out = VDIR / "US_qual"
    out.mkdir(parents=True, exist_ok=True)
    dists = json.loads(dist_f.read_text())
    questions = {c["q"]: QUAL_QS.get(c["q"], c["q"]) for c in dists}
    gold = {c["q"]: c["gold"] for c in dists}
    (out / "questions.json").write_text(json.dumps(questions, ensure_ascii=False, indent=1))
    (out / "gold_shares.json").write_text(json.dumps(gold, ensure_ascii=False, indent=1))
    (out / "synthetic_verbatims.jsonl").write_text(resp_f.read_text())
    print(f"  US_qual      {len(questions):4} open questions -> verification/US_qual/")
    return True


def main():
    ap = argparse.ArgumentParser(description="Build the public verification bundle from an internal results/ run.")
    ap.add_argument("--version", default="prod_v1", help="results/<version>/ to extract from")
    ap.add_argument("--pops", nargs="*", default=POPS, help="populations to publish")
    ap.add_argument("--no-qual", action="store_true", help="skip the US qualitative (open-ended) bundle")
    args = ap.parse_args()

    if not (RESULTS / args.version).exists():
        raise SystemExit(f"no results/{args.version}/ directory")
    print(f"building verification bundle from results/{args.version}/")
    n = sum(build_pop(args.version, pop) for pop in args.pops)
    if not args.no_qual:
        build_qual(args.version)
    print(f"done: {n} quant populations + qual -> {VDIR}")


if __name__ == "__main__":
    main()
