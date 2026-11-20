"""The GLiNER arm beside the BERT runs it repeats, from the committed outputs.

Cases: <BERT run>/cases (BERT, with the LLM) against <GLiNER run>/cases_gliner
and cases_gliner_no_llm, with each count, since the reference models are
small. Lanes: <BERT run>/coref_ablation/with_coref against
<GLiNER run>/lanes_gliner/with_coref, the same 396 gold activities in the same
order, with a paired bootstrap over the documents that have any (43 of the
45; 1000 resamples, seed 0) of the difference in each share; and, the same
way, BERT with FastCoref against BERT without it (the coreference ablation's
two arms).

    python3 -m text2bpmn.compare_gliner_arm             # the method as submitted: runs/final, runs/gliner
                                                        # -> text2bpmn/results/gliner_arm_comparison.{md,json}
    python3 -m text2bpmn.compare_gliner_arm --release   # the release runs: runs/final-3, runs/gliner-3
                                                        # -> runs/checks/final-3/tables/gliner_arm_comparison.{md,json}
    python3 -m text2bpmn.compare_gliner_arm --bert-run R --gliner-run G --out PATH

Without flags it reads runs/final (tag revision-final) and runs/gliner (tag
revision-final-gliner), as it did before --release existed; the paper's
Table 7 is the release runs' (text2bpmn.paper_tables 7).
"""
import argparse
import json
import random
from pathlib import Path

CASES = ("loan", "goods_dispatch", "healthcare")
# (BERT run, GLiNER run, report path without suffix, what the report names them)
SUBMITTED = ("runs/final", "runs/gliner", "text2bpmn/results/gliner_arm_comparison",
             "`runs/final` (tag revision-final, BERT `bert_ner_315_dev60`) and `runs/gliner` (tag "
             "revision-final-gliner, GLiNER A-small-v2.1-315 at 0.85, one sentence at a time). Same Qwen3.5-27B-FP8 "
             "server, prompt `corrected`.")
RELEASE = ("runs/final-3", "runs/gliner-3", "runs/checks/final-3/tables/gliner_arm_comparison",
           "`runs/final-3` and `runs/gliner-3` (tag revision-final-3, the release runs: BERT `bert_ner_315_dev60`, "
           "GLiNER A-small-v2.1-315 at 0.85, one sentence at a time). Same Qwen3.5-27B-FP8 server, relation mode "
           "`decisions4`.")
# the method as submitted, as this module always read it
CASE_ARMS = {"BERT, LLM": "runs/final/cases",
             "GLiNER, LLM": "runs/gliner/cases_gliner",
             "GLiNER, no LLM": "runs/gliner/cases_gliner_no_llm"}
LANES = {"BERT": "runs/final/coref_ablation/lane_scores.json",
         "GLiNER": "runs/gliner/lanes_gliner/lane_scores.json"}
OUT = Path(SUBMITTED[2])
RESAMPLES, SEED = 1000, 0


def case_arms(bert_run, gliner_run):
    return {"BERT, LLM": f"{bert_run}/cases",
            "GLiNER, LLM": f"{gliner_run}/cases_gliner",
            "GLiNER, no LLM": f"{gliner_run}/cases_gliner_no_llm"}


def lane_files(bert_run, gliner_run):
    return {"BERT": f"{bert_run}/coref_ablation/lane_scores.json",
            "GLiNER": f"{gliner_run}/lanes_gliner/lane_scores.json"}


def cases(arms=None):
    table = {}
    for arm, folder in (arms or CASE_ARMS).items():
        for case in CASES:
            # every arm as scored against the reference the runs used: each loan folder's
            # comparison.json is the textbook score (D12), its own comparison_authored.json
            saved = Path(folder, case, "comparison_authored.json")
            if not saved.exists():
                saved = Path(folder, case, "comparison.json")
            c = json.loads(saved.read_text(encoding="utf-8"))
            table.setdefault(case, {})[arm] = {
                **{e: {k: c[e][k] for k in ("tp", "fp", "fn", "f1")} for e in ("tasks", "gateways", "edges")},
                "ged": c["ged"]["ged"]}
    return table


def _same_activities(*arms):
    keys = [[(r["document"], r["activity"]) for r in rows] for rows in arms]
    if any(k != keys[0] for k in keys[1:]):
        raise SystemExit("the lane runs do not score the same gold activities in the same order")


def lane_rows(files=None, arm="with_coref"):
    rows = {name: json.loads(Path(p).read_text(encoding="utf-8"))[arm]["rows"] for name, p in (files or LANES).items()}
    _same_activities(*rows.values())
    return rows


def counts(rows):
    recognised = [r for r in rows if r["recognised"]]
    pronoun = [r for r in recognised if r["pronoun"]]
    return {"gold": len(rows), "recognised": len(recognised),
            "correct": sum(r["correct"] for r in recognised),
            "pronoun_recognised": len(pronoun), "pronoun_correct": sum(r["correct"] for r in pronoun)}


def shares(c):
    return {"of_recognised": c["correct"] / c["recognised"], "of_gold": c["correct"] / c["gold"]}


def paired_difference(first, second, resamples=RESAMPLES, seed=SEED):
    """share(first) - share(second), of the recognised and of all gold activities, with a
    95% interval from resampling the documents (the same gold activities in both)."""
    _same_activities(first, second)
    documents = sorted({r["document"] for r in second})
    per_document = {d: (counts([r for r in first if r["document"] == d]),
                        counts([r for r in second if r["document"] == d])) for d in documents}
    rng = random.Random(seed)
    differences = {"of_recognised": [], "of_gold": []}
    for _ in range(resamples):
        sample = [per_document[rng.choice(documents)] for _ in documents]
        total = [{k: sum(s[i][k] for s in sample) for k in sample[0][i]} for i in (0, 1)]
        a, b = shares(total[0]), shares(total[1])
        for k in differences:
            differences[k].append(a[k] - b[k])
    point = {k: shares(counts(first))[k] - shares(counts(second))[k] for k in differences}
    return ({k: {"difference": point[k],
                 "ci95": [sorted(v)[int(0.025 * resamples)], sorted(v)[int(0.975 * resamples) - 1]]}
             for k, v in differences.items()},
            {"unit": "document", "documents": len(documents), "resamples": resamples, "seed": seed})


def lanes(files=None):
    rows = lane_rows(files)
    bert, gliner = rows["BERT"], rows["GLiNER"]
    result = {arm: {**counts(r), **shares(counts(r))} for arm, r in rows.items()}
    pairs = list(zip(gliner, bert))
    both = [(g, b) for g, b in pairs if g["recognised"] and b["recognised"]]
    result["overlap"] = {
        "recognised_by_both": len(both),
        "right_in_gliner_only": sum(g["correct"] and not b["correct"] for g, b in both),
        "right_in_bert_only": sum(b["correct"] and not g["correct"] for g, b in both),
        "recognised_by_gliner_only": sum(g["recognised"] and not b["recognised"] for g, b in pairs),
        "recognised_by_bert_only": sum(b["recognised"] and not g["recognised"] for g, b in pairs)}
    result["gliner_minus_bert"], result["bootstrap"] = paired_difference(gliner, bert)
    ablation = json.loads(Path((files or LANES)["BERT"]).read_text(encoding="utf-8"))
    if "without_coref" in ablation:
        without = ablation["without_coref"]["rows"]
        result["BERT without FastCoref"] = {**counts(without), **shares(counts(without))}
        result["with_minus_without_coref"], _ = paired_difference(bert, without)
    return result


def markdown(case_table, lane_result, source=SUBMITTED[3]):
    def cell(e):
        return f"{e['f1']:.3f} ({e['tp']}/{e['fp']}/{e['fn']})"

    lines = ["# The GLiNER arm beside BERT", "",
             f"Generated by `text2bpmn/compare_gliner_arm.py` from {source}", "",
             "## Case studies", "",
             "F1 with (TP/FP/FN); GED is an upper bound, lower is better.", "",
             "| case | arm | tasks | gateways | edges | GED |", "|---|---|---|---|---|---|"]
    for case, arms in case_table.items():
        for arm, r in arms.items():
            lines.append(f"| {case} | {arm} | {cell(r['tasks'])} | {cell(r['gateways'])} | "
                         f"{cell(r['edges'])} | {r['ged']} |")
    pct = "{:.1%}".format
    lines += ["", "## Lanes: 45 PET documents, FastCoref on", "",
              "| recogniser | gold activities | recognised | in the performer's lane, of recognised | "
              "of all gold | pronoun performer, of recognised |", "|---|---|---|---|---|---|"]
    for arm in ("BERT", "GLiNER"):
        r = lane_result[arm]
        lines.append(f"| {arm} | {r['gold']} | {r['recognised']} | {pct(r['of_recognised'])} ({r['correct']}) | "
                     f"{pct(r['of_gold'])} | {pct(r['pronoun_correct'] / r['pronoun_recognised'])} "
                     f"({r['pronoun_correct']} of {r['pronoun_recognised']}) |")
    o, d = lane_result["overlap"], lane_result["gliner_minus_bert"]
    b = lane_result["bootstrap"]
    labels = (("of_recognised", "share of recognised activities in the performer's lane"),
              ("of_gold", "share of all gold activities in the performer's lane"))
    lines += ["",
              f"GLiNER − BERT, paired bootstrap over the {b['documents']} documents with a gold performer "
              f"({b['resamples']} resamples, seed {b['seed']}):", ""]
    for k, label in labels:
        lines.append(f"- {label}: {d[k]['difference']:+.3f} [{d[k]['ci95'][0]:+.3f}, {d[k]['ci95'][1]:+.3f}]")
    lines += ["",
              f"Of the {o['recognised_by_both']} activities both recognise, {o['right_in_gliner_only']} are in the "
              f"right lane only with GLiNER and {o['right_in_bert_only']} only with BERT. "
              f"{o['recognised_by_bert_only']} are recognised only by BERT, {o['recognised_by_gliner_only']} "
              f"only by GLiNER.", ""]
    if "with_minus_without_coref" in lane_result:
        w, c = lane_result["with_minus_without_coref"], lane_result["BERT without FastCoref"]
        lines += [f"BERT with FastCoref − BERT without it (the coreference ablation; without it "
                  f"{pct(c['of_recognised'])} ({c['correct']}/{c['recognised']}) of recognised, "
                  f"{pct(c['of_gold'])} of all gold), the same bootstrap:", ""]
        for k, label in labels:
            lines.append(f"- {label}: {w[k]['difference']:+.3f} [{w[k]['ci95'][0]:+.3f}, {w[k]['ci95'][1]:+.3f}]")
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--release", action="store_true", help="the release runs, runs/final-3 and runs/gliner-3")
    ap.add_argument("--bert-run", help="a run folder with cases/ and coref_ablation/")
    ap.add_argument("--gliner-run", help="a run folder with cases_gliner/, cases_gliner_no_llm/ and lanes_gliner/")
    ap.add_argument("--out", help="report path without suffix")
    args = ap.parse_args()
    bert_run, gliner_run, out, source = RELEASE if args.release else SUBMITTED
    if args.bert_run or args.gliner_run:
        if not (args.bert_run and args.gliner_run and args.out):
            raise SystemExit("--bert-run and --gliner-run go together, with --out")
        bert_run, gliner_run, out = args.bert_run, args.gliner_run, args.out
        source = f"`{bert_run}` (BERT) and `{gliner_run}` (GLiNER)."
    out = Path(args.out or out)
    case_table, lane_result = cases(case_arms(bert_run, gliner_run)), lanes(lane_files(bert_run, gliner_run))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps({"cases": case_table, "lanes": lane_result}, indent=2),
                                        encoding="utf-8")
    text = markdown(case_table, lane_result, source)
    out.with_suffix(".md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
