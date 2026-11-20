"""The fine-tuned GLiNER as the pipeline's entity recogniser, at the tagged code.

    GLINER_PYTHON=<GLiNER venv>/bin/python python3 -m text2bpmn.run_gliner_arm [--only NAME ...] [--model M] [--api-base URL]
    GLINER_PYTHON=<GLiNER venv>/bin/python python3 -m text2bpmn.run_gliner_arm --dry-run

The question it answers: fine-tuned GLiNER beats the BERT recogniser on PET's
held-out sentences (0.849 against 0.715 strict micro F1, paired difference
+0.134 [0.085, 0.184], text2bpmn/results/ner_paired_bootstrap_315.md); does
that reach the models the pipeline builds? Everything is as in
text2bpmn/run_final.py's cases and coref_ablation except the recogniser,
and the relation stage is RunConfig's default, idea 3 since
revision-final-3 (idea 1c at revision-final-2, runs/gliner-2; the pairwise
classifier at revision-final-gliner, runs/gliner):

    1 cases_gliner         the three case studies end to end, prompt `corrected`, each
                           scored against its reference model; compare runs/final/cases
    2 cases_gliner_no_llm  the same with every relation answer UNKNOWN: what the
                           recogniser alone gives
    3 lanes_gliner         PET, 45 documents, with FastCoref, lane assignment scored
                           against PET's actor-performer relations; compare
                           runs/final/coref_ablation/with_coref

The recogniser is A-small-v2.1-315 (text2bpmn/baselines/train_all_315.sh), at
the threshold chosen for it on the development sentences
(text2bpmn/baselines/chosen_thresholds_315.json), read one sentence at a time
by text2bpmn/gliner_spans.py in GLiNER's own venv. It reads the same
coreference-resolved text the BERT recogniser reads (finder3.resolved_text),
and its spans enter the pipeline through finder3's injection path, so the
relation classifier, the Validation Layer and the scoring are the BERT runs'
own.

A real run refuses to start unless the tree is clean and exactly at the tag
`revision-final-3`. --dry-run: no LLM, 3 PET documents, into
runs/gliner_dryrun/. Real runs go to runs/gliner-3/ (git-ignored, like
runs/final-3/; commit with `git add -f runs/gliner-3`).
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from text2bpmn.run_config import RunConfig, _git_state, add_arguments, from_arguments
from text2bpmn.run_final import CASES, PET_JOBS, run_experiments

TAG = "revision-final-3"
GLINER_MODEL = "text2bpmn/baselines/finetuned_315/A-small-v2.1-315/best"
GLINER_NAME = "A-small-v2.1-315"
THRESHOLDS = "text2bpmn/baselines/chosen_thresholds_315.json"
EXPERIMENTS = ("cases_gliner", "cases_gliner_no_llm", "lanes_gliner")


def gliner_python():
    return os.environ.get("GLINER_PYTHON") or str(Path.home() / ".venvs/gliner-env/bin/python")


def threshold():
    return json.loads(Path(THRESHOLDS).read_text(encoding="utf-8"))[GLINER_NAME]["threshold"]


def gliner_spans(texts, out):
    """{document id: spans file entry} for {document id: resolved text}, from
    text2bpmn.gliner_spans run in GLiNER's venv; the file stays in `out`."""
    (out / "resolved_texts.json").write_text(json.dumps(texts, indent=1, ensure_ascii=False), encoding="utf-8")
    command = [gliner_python(), "-m", "text2bpmn.gliner_spans", "--model", GLINER_MODEL,
               "--texts", str(out / "resolved_texts.json"), "--out", str(out / "gliner_spans.json")]
    with open(out / "gliner_log.txt", "w", encoding="utf-8") as log:
        done = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    if done.returncode:
        raise RuntimeError(f"text2bpmn.gliner_spans exited with {done.returncode}; see {out / 'gliner_log.txt'}")
    record = json.loads((out / "gliner_spans.json").read_text(encoding="utf-8"))
    return record, command


def injected(document, at):
    """finder3's injection format: the text and the spans at or above `at`."""
    return {"text": document["text"], "spans": [s for s in document["spans"] if s["score"] >= at],
            "source": f"{GLINER_MODEL} at {at}, one sentence at a time"}


def recogniser(record, command, at):
    """What the run record keeps about the recogniser."""
    return {"model": GLINER_MODEL, "name": GLINER_NAME, "threshold": at,
            "threshold_from": THRESHOLDS, "read": record["read"], "floor": record["floor"],
            "weights_sha256": record["weights_sha256"], "python": record["python"],
            "versions": record["versions"], "command": command,
            "sentences_longer_than_the_model_reads":
                sum(d["sentences_longer_than_the_model_reads"] for d in record["documents"].values())}


def cases_gliner(name, config, out, dry):
    """Runs 1 and 2: the cases with GLiNER's spans, as run_final.cases with BERT's."""
    from text2bpmn.checks.pilot_run import run_one
    from text2bpmn.compare import compare, read_bpmn
    from text2bpmn.finder3 import BPMNHybridExtractor

    extractor = BPMNHybridExtractor(config=config, ner_model_path=None)
    texts = {case: Path(f"text2bpmn/cases/{case}/input.txt").read_text(encoding="utf-8") for case in CASES}
    record, command = gliner_spans({case: extractor.resolved_text(t) for case, t in texts.items()}, out)
    at = threshold()
    scores = {}
    for case in CASES:
        result_record = run_one(extractor, case, texts[case], out / case,
                                entities=injected(record["documents"][case], at))
        if result_record["status"] == "failed":
            raise RuntimeError(f"{case}: {result_record['error']}")
        result = compare(read_bpmn(f"text2bpmn/cases/{case}/reference.bpmn"), read_bpmn(out / case / "model.bpmn"))
        (out / case / "comparison.json").write_text(json.dumps(result, indent=2, ensure_ascii=False),
                                                    encoding="utf-8")
        scores[case] = {k: result[k] for k in ("tasks", "gateways", "edges", "ged")}
        print(f"   {case}: tasks F1 {result['tasks']['f1']}, gateways F1 {result['gateways']['f1']}, "
              f"edges F1 {result['edges']['f1']}", flush=True)
    return {"pipeline_run_record": extractor.run_record, "recogniser": recogniser(record, command, at),
            "scores": scores}


def lanes_gliner(name, config, out, dry):
    """Run 3: PET's 45 texts with GLiNER's spans, FastCoref on, as the
    with_coref arm of run_final.coref_ablation with BERT's."""
    from text2bpmn.checks.pilot_run import run_one
    from text2bpmn.finder3 import BPMNHybridExtractor
    from text2bpmn.lane_accuracy import score

    jobs = json.loads(Path(PET_JOBS).read_text(encoding="utf-8"))["jobs"][:3 if dry else None]
    extractor = BPMNHybridExtractor(config=config, ner_model_path=None)
    record, command = gliner_spans({job["name"]: extractor.resolved_text(job["text"]) for job in jobs}, out)
    at = threshold()
    arm = "with_coref"
    records = []
    for job in jobs:
        r = run_one(extractor, job["name"], job["text"], out / arm / job["name"],
                    entities=injected(record["documents"][job["name"]], at))
        records.append(r)
        print(f"   {arm} {job['name']}: {r['status']}, {r.get('elements', {}).get('task', 0)} tasks, "
              f"{r.get('lanes', 0)} lanes", flush=True)
    (out / arm / "records.json").write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    failed = [r["document"] for r in records if r["status"] == "failed"]
    if failed:
        raise RuntimeError(f"failed documents: {failed}")
    totals = {arm: {"documents": len(records), "tasks": sum(r["elements"].get("task", 0) for r in records),
                    "lanes": sum(r["lanes"] for r in records), "flows": sum(r["flows"] for r in records),
                    "relation_calls": sum(r["relation_calls"] for r in records)}}
    lanes, table = score(out)
    print(table, flush=True)
    totals[arm]["lanes_scored"] = {k: v for k, v in lanes[arm].items() if k != "rows"}
    return {"pipeline_run_record": extractor.run_record, "recogniser": recogniser(record, command, at),
            "totals": totals}


RUNNERS = {"cases_gliner": (cases_gliner, "corrected", False),
           "cases_gliner_no_llm": (cases_gliner, "corrected", True),
           "lanes_gliner": (lanes_gliner, "corrected", False)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", nargs="+", choices=EXPERIMENTS)
    ap.add_argument("--dry-run", action="store_true", help="no LLM, 3 PET documents, into runs/gliner_dryrun/")
    ap.add_argument("--out", help="default runs/gliner-3, or runs/gliner_dryrun with --dry-run")
    add_arguments(ap)
    args = ap.parse_args()
    if args.llm_cache:
        raise SystemExit("the final runs never use the cache")
    if args.prompt != "corrected" or args.allow_no_llm or args.relation_mode != RunConfig.relation_mode:
        raise SystemExit("--prompt, --allow-no-llm and --relation-mode are set per experiment here, "
                         "not on the command line")
    if not Path(GLINER_MODEL).is_dir() or not Path(gliner_python()).exists():
        raise SystemExit(f"needs the GLiNER model in {GLINER_MODEL} and GLiNER's venv at {gliner_python()} "
                         "(set GLINER_PYTHON)")
    base = from_arguments(args, llm_cache=False)
    code = _git_state()
    if not args.dry_run and (code["describe"] != TAG or code["dirty"]):
        raise SystemExit(f"the GLiNER arm starts only on a clean tree exactly at {TAG}; "
                         f"this is {code['describe']} (dirty: {code['dirty']})")
    root = Path(args.out or ("runs/gliner_dryrun" if args.dry_run else "runs/gliner-3"))
    failed = run_experiments(args.only or EXPERIMENTS, RUNNERS, base, code, root, args.dry_run)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
