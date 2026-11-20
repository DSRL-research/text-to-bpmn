"""The relation experiments: other ways of using the LLM, beside the final run.

    python3 -m text2bpmn.relation_ideas --idea 1b [--only NAME ...] [--model M] [--api-base URL]
    python3 -m text2bpmn.relation_ideas --idea 1b --dry-run
    python3 -m text2bpmn.relation_ideas --idea 1b --report      # once the run is back

Every idea is run and scored as runs/final runs and scores the method as
submitted: PET's 45 documents on PET's gold spans, scored on PET's flows
(text2bpmn/pet_flow_eval.py), and the three case studies end to end with the
BERT recogniser, scored against their reference models. --report sets each
beside the text order alone and the pairwise classifier, with a paired
bootstrap over documents, and writes text2bpmn/results/relation_idea_<N>.{md,json}.

PET is scored two ways. The first is the measure behind the final runs: three
flow shapes. The second, from 2026-11-11, scores every PET flow but the
condition folding, and does not count against a model the flows between two
mentions PET links as the same gateway (text2bpmn/pet_flow_eval.py). Only a
run made with a job file that has `all_flows` carries the second; runs/final
does not, so idea 1b reruns the text order and the pairwise classifier.

Idea 1, at the tag relation-idea-1:

    pet_decisions      PET, one question per decision (text2bpmn/decisions.py)
    cases_decisions    the cases, the same
    pet_no_parallel    PET, the pairwise classifier never asked about concurrency
                       (--parallel-detection off): how much of any difference
                       comes only from the parallel blocks, which idea 1 does
                       not build
    cases_no_parallel  the cases, the same

Idea 1b, at the tag relation-idea-1b, every PET run scored both ways:

    pet_no_llm         PET, the text order alone (as runs/final/pet_no_llm)
    pet_decisions      PET, idea 1 again, unchanged
    pet_decisions2     PET, idea 1b: later mentions of one decision are its other
                       cases (text2bpmn/decisions.py)
    cases_decisions2   the cases, idea 1b
    pet_pairs          PET, the pairwise classifier as submitted (as
                       runs/final/pet_classifier); last, as the longest

Idea 2, at the tag relation-idea-2, every PET run scored both ways, and set
beside idea 1b's run (its text order, pairwise and decision arms):

    pet_no_and         PET, the text order alone with parallel-gateway words
                       left out (1c with every answer UNKNOWN): 1c's own
                       control, since leaving the words out changes the chain
    pet_decisions3     PET, idea 1c: 1b with parallel-gateway words left out,
                       so no decision's branches meet at a parallel gateway
    cases_decisions3   the cases, idea 1c
    cases_pairs2       the cases, idea 2: the pair questions with a sixth
                       answer, NONE, asked only of neighbours and of pairs with
                       a gateway (relation_mode pairs2, prompt corrected_none)
    pet_pairs2         PET, idea 2

Idea 3, at the tag relation-idea-3, set beside the method's release run
(runs/final-2: 1c, its text order without parallel-gateway words, and the text
order), and scored a third way, on PET's pairs of parallel lines of work
(text2bpmn/pet_flow_eval.py); the release run's saved models are rescored for
it:

    pet_decisions4     PET, idea 3: 1c with one question per parallel-gateway
                       word, which can build a parallel block
                       (relation_mode decisions4)
    cases_decisions4   the cases, idea 3

Each design is fixed before its run, and every run is reported. A real run
refuses to start unless the tree is clean and exactly at the idea's tag.
--dry-run: no LLM, 3 PET documents and the 3 cases, into runs/ideas_dryrun/.
Real runs go to runs/ideas/ (git-ignored, like runs/final/; commit with
git add -f runs/ideas).
"""
import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

from text2bpmn.run_config import RunConfig, _git_state, add_arguments, from_arguments
from text2bpmn.run_final import CASES, cases, pet_flows, run_experiments

# every experiment names its relation mode: the default changed to decisions3
# at revision-final-2, after these ideas ran with "pairs" as the default
PAIRS = {"relation_mode": "pairs"}
DECISIONS = {"relation_mode": "decisions"}
DECISIONS2 = {"relation_mode": "decisions2"}
IDEAS = {
    "1": {"pet_decisions": (pet_flows, "corrected", False, DECISIONS),
          "cases_decisions": (cases, "corrected", False, DECISIONS),
          "pet_no_parallel": (pet_flows, "corrected", False, {**PAIRS, "parallel_detection": "off"}),
          "cases_no_parallel": (cases, "corrected", False, {**PAIRS, "parallel_detection": "off"})},
    "1b": {"pet_no_llm": (pet_flows, "corrected", True, PAIRS),
           "pet_decisions": (pet_flows, "corrected", False, DECISIONS),
           "pet_decisions2": (pet_flows, "corrected", False, DECISIONS2),
           "cases_decisions2": (cases, "corrected", False, DECISIONS2),
           "pet_pairs": (pet_flows, "corrected", False, PAIRS)},
    "2": {"pet_no_and": (pet_flows, "corrected", True, {"relation_mode": "decisions3"}),
          "pet_decisions3": (pet_flows, "corrected", False, {"relation_mode": "decisions3"}),
          "cases_decisions3": (cases, "corrected", False, {"relation_mode": "decisions3"}),
          "cases_pairs2": (cases, "corrected_none", False, {"relation_mode": "pairs2"}),
          "pet_pairs2": (pet_flows, "corrected_none", False, {"relation_mode": "pairs2"})},
    "3": {"pet_decisions4": (pet_flows, "corrected", False, {"relation_mode": "decisions4"}),
          "cases_decisions4": (cases, "corrected", False, {"relation_mode": "decisions4"})},
}
# a run whose arms an idea's report shows beside its own, and whose reruns of
# the text order and the pairwise classifier it is compared with
EARLIER = {"2": "runs/ideas/idea1b", "3": "runs/final-2"}
# what each idea is compared with: the run's own rerun when it made one
REFERENCES = {"text order": ("pet_no_llm", "runs/final/pet_no_llm"),
              "pairs": ("pet_pairs", "runs/final/pet_classifier")}
# idea 3: the pairwise classifier's rerun with both measures, and the method it extends
MORE_REFERENCES = {"3": {"pairs": "runs/ideas/idea1b/pet_pairs", "the method (1c)": "runs/final-2/pet_decisions"}}
FINAL = {"text order, runs/final": "runs/final/pet_no_llm", "pairs, runs/final": "runs/final/pet_classifier"}
CASE_BASELINE = ("pairs, runs/final", "runs/final/cases")
SHAPES = ("sequence", "into a decision", "out of a branch")
MEASURES = {"scored": "counts", "all": "all_flows"}
JOBS = "text2bpmn/baselines/pet_jobs.json"
RESAMPLES, SEED = 1000, 0


def tag(idea):
    return f"relation-idea-{idea}"


def root(idea, dry_run):
    return Path("runs/ideas_dryrun" if dry_run else "runs/ideas") / f"idea{idea}"


# --- the report ------------------------------------------------------------

def records(folder):
    """{document: record}; a run made before the third measure gets it from
    the models it saved, when it saved them."""
    path = Path(folder) / "records.jsonl"
    if not path.exists():
        return {}
    rows = (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    found = {r["document"]: r for r in rows}
    saved = {d: Path(folder) / "documents" / d / "process.json" for d in found}
    if found and any("concurrency" not in r for r in found.values()) and all(p.exists() for p in saved.values()):
        from text2bpmn.pet_flow_eval import score_concurrency_saved
        jobs = {j["name"]: j for j in json.loads(Path(JOBS).read_text(encoding="utf-8"))["jobs"]}
        for d, r in found.items():
            r.setdefault("concurrency", score_concurrency_saved(
                jobs[d], json.loads(saved[d].read_text(encoding="utf-8"))))
    return found


def prf(c):
    tp, fp, fn = c["tp"], c["fp"], c["fn"]
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": 2 * p * r / (p + r) if p + r else 0.0}


def summed(rows, key):
    c = Counter(tp=0, fp=0, fn=0, unmapped=0)
    for r in rows:
        c.update({k: r[key].get(k, 0) for k in ("tp", "fp", "fn", "unmapped")})
    return c


def totals(rows):
    rows = list(rows)
    shapes = {s: Counter() for s in SHAPES}
    for r in rows:
        for s in SHAPES:
            shapes[s].update(r["by_shape"].get(s, {}))
    out = {"documents": len(rows), "calls": sum(r["relation_calls"] for r in rows),
           "failed": sum(r["relation_failures"] for r in rows),
           "shapes": {s: {"built": v["tp"], "missed": v["fn"]} for s, v in shapes.items()}}
    for measure, key in MEASURES.items():
        if all(key in r for r in rows):
            c = summed(rows, key)
            out[measure] = prf(c) | {"unmapped": c["unmapped"]}
    if rows and all("concurrency" in r for r in rows):
        c = summed(rows, "concurrency")
        out["concurrency"] = prf(c) | {"unmapped": c["unmapped"]}
    return out


def paired(a, b, key="counts"):
    """F1(a) - F1(b) on one measure, over the documents both have, with a 95%
    interval from resampling documents; None if either lacks the measure."""
    names = sorted(set(a) & set(b))
    if not names or not all(key in a[n] and key in b[n] for n in names):
        return None
    rng = random.Random(SEED)

    def f1(rows):
        return prf(summed(rows, key))["f1"]

    point = f1([a[n] for n in names]) - f1([b[n] for n in names])
    draws = sorted(f1([a[n] for n in s]) - f1([b[n] for n in s])
                   for s in ([rng.choice(names) for _ in names] for _ in range(RESAMPLES)))
    return {"documents": len(names), "difference": point,
            "ci95": [draws[int(0.025 * RESAMPLES)], draws[int(0.975 * RESAMPLES) - 1]]}


def report(idea, folder=None):
    folder = Path(folder or root(idea, False))
    own = {name: records(folder / name) for name in IDEAS[idea] if name.startswith("pet_")}
    final = {label: records(path) for label, path in FINAL.items()}
    earlier = Path(EARLIER[idea]) if idea in EARLIER else None
    before = {f"{earlier.name}: {d.name}": records(d) for d in sorted(earlier.glob("pet_*"))} \
        if earlier and earlier.is_dir() else {}
    more = {label: records(path) for label, path in MORE_REFERENCES.get(idea, {}).items()}
    result = {"idea": idea, "folder": str(folder), "pet": {}, "differences": {}, "cases": {}}
    for name, rows in {**final, **before, **own}.items():
        if rows:
            result["pet"][name] = totals(rows.values())
    references = {}
    for label, (name, path) in REFERENCES.items():
        found = [own.get(name)] + ([records(earlier / name)] if earlier else []) + [records(path)]
        references[label] = next((rows for rows in found if rows), None)
    references.update({label: rows for label, rows in more.items() if rows})
    # 1c leaves parallel-gateway words out, which changes the chain itself; so
    # does 3, when no answer builds a block
    no_and = own.get("pet_no_and") or (records(earlier / "pet_no_and") if earlier else {})
    own_control = {"pet_decisions3": ("text order without parallel-gateway words", own.get("pet_no_and")),
                   "pet_decisions4": ("text order without parallel-gateway words", no_and)}
    for name, rows in own.items():
        if not rows or name in ("pet_no_llm", "pet_pairs", "pet_no_and"):
            continue
        result["differences"][name] = {
            f"{name} − {label}": {measure: paired(rows, ref, key) for measure, key in MEASURES.items()}
            for label, ref in [*references.items(), own_control.get(name, (None, None))] if ref}
    for case in CASES:
        arms = [CASE_BASELINE] + ([(f"{earlier.name}: {d.name}", d) for d in sorted(earlier.glob("cases*"))]
                                  if earlier and earlier.is_dir() else []) + \
               [(n, folder / n) for n in IDEAS[idea] if n.startswith("cases_")]
        for name, path in arms:
            comparison = Path(path) / case / "comparison.json"
            if comparison.exists():
                c = json.loads(comparison.read_text(encoding="utf-8"))
                result["cases"].setdefault(case, {})[name] = {
                    **{e: {k: c[e][k] for k in ("tp", "fp", "fn", "f1")} for e in ("tasks", "gateways", "edges")},
                    "ged": c["ged"]["ged"]}
    return result


def markdown(result):
    def measure(t, m):
        return f"{t[m]['precision']:.3f} | {t[m]['recall']:.3f} | **{t[m]['f1']:.3f}**" if m in t else "– | – | –"

    lines = [f"# Relation idea {result['idea']}", "",
             f"Generated by `text2bpmn/relation_ideas.py --report` from `{result['folder']}` and "
             "`runs/final`. PET: 45 documents on PET's gold spans (`text2bpmn/pet_flow_eval.py`); an edge "
             "counts when it is direct or passes through one gateway. *Scored*: the three flow shapes behind "
             "the final runs. *All flows*: every PET flow but the condition folding, flows between two "
             "mentions of one gateway counted neither way.", "",
             "| arm | scored P | R | F1 | all flows P | R | F1 | sequence | into a decision | out of a branch "
             "| calls | failed |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, t in result["pet"].items():
        shapes = " | ".join(f"{t['shapes'][s]['built']}/{t['shapes'][s]['built'] + t['shapes'][s]['missed']}"
                            for s in SHAPES)
        lines.append(f"| {name} | {measure(t, 'scored')} | {measure(t, 'all')} | {shapes} | "
                     f"{t['calls']} | {t['failed']} |")
    side = {name: t["concurrency"] for name, t in result["pet"].items() if "concurrency" in t}
    if side:
        lines += ["", "Pairs of steps PET puts in parallel lines of work (the third measure; "
                  "`text2bpmn/pet_flow_eval.py`): built side by side / PET's pairs, and pairs built side by "
                  "side that PET does not have:", "", "| arm | built | wrong |", "|---|---|---|"]
        for name, c in side.items():
            lines.append(f"| {name} | {c['tp']}/{c['tp'] + c['fn']} | {c['fp']} |")
    if result["differences"]:
        lines += ["", f"F1 differences, paired bootstrap over documents ({RESAMPLES} resamples, seed {SEED}):", ""]
        for against in result["differences"].values():
            for label, by_measure in against.items():
                shown = [f"{m} {d['difference']:+.3f} [{d['ci95'][0]:+.3f}, {d['ci95'][1]:+.3f}]"
                         for m, d in by_measure.items() if d]
                lines.append(f"- {label}: " + "; ".join(shown))
    if result["cases"]:
        lines += ["", "Case studies with the BERT recogniser, F1 (TP/FP/FN); GED lower is better:", "",
                  "| case | arm | tasks | gateways | edges | GED |", "|---|---|---|---|---|---|"]
        for case, arms in result["cases"].items():
            for name, r in arms.items():
                cell = lambda e: f"{r[e]['f1']:.3f} ({r[e]['tp']}/{r[e]['fp']}/{r[e]['fn']})"  # noqa: E731
                lines.append(f"| {case} | {name} | {cell('tasks')} | {cell('gateways')} | {cell('edges')} | "
                             f"{r['ged']} |")
    return "\n".join(lines) + "\n"


# --- the run ---------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--idea", required=True, choices=sorted(IDEAS))
    ap.add_argument("--only", nargs="+")
    ap.add_argument("--dry-run", action="store_true", help="no LLM, 3 PET documents and the 3 cases")
    ap.add_argument("--report", action="store_true", help="score a run that is back, here; no LLM needed")
    ap.add_argument("--out", help="default runs/ideas/idea<N>, or runs/ideas_dryrun/idea<N> with --dry-run")
    add_arguments(ap)
    args = ap.parse_args()
    if args.report:
        result = report(args.idea, args.out)
        text = markdown(result)
        out = Path(f"text2bpmn/results/relation_idea_{args.idea}")
        if not args.out:
            out.with_suffix(".json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            out.with_suffix(".md").write_text(text, encoding="utf-8")
        print(text)
        return
    if args.llm_cache:
        raise SystemExit("these runs never use the cache")
    if args.prompt != "corrected" or args.allow_no_llm or args.relation_mode != RunConfig.relation_mode \
            or args.parallel_detection != "all":
        raise SystemExit("--prompt, --allow-no-llm, --relation-mode and --parallel-detection are set "
                         "per experiment here, not on the command line")
    unknown = set(args.only or ()) - set(IDEAS[args.idea])
    if unknown:
        raise SystemExit(f"idea {args.idea} has no experiment {sorted(unknown)}; it has {list(IDEAS[args.idea])}")
    base = from_arguments(args, llm_cache=False)
    code = _git_state()
    if not args.dry_run and (code["describe"] != tag(args.idea) or code["dirty"]):
        raise SystemExit(f"idea {args.idea} runs only on a clean tree exactly at {tag(args.idea)}; "
                         f"this is {code['describe']} (dirty: {code['dirty']})")
    folder = Path(args.out) if args.out else root(args.idea, args.dry_run)
    failed = run_experiments(args.only or list(IDEAS[args.idea]), IDEAS[args.idea], base, code, folder,
                             args.dry_run)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
