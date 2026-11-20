"""Every final experiment at the tagged code, from one command.

    python3 -m text2bpmn.run_final [--only NAME ...] [--model M] [--api-base URL]
    python3 -m text2bpmn.run_final --dry-run

At revision-final-3 the method's relation stage is relation idea 3: one LLM
question per decision and one per concurrency word, every model checked by
the soundness gate (text2bpmn/decisions.py, text2bpmn/soundness_gate.py,
RunConfig.relation_mode "decisions4"); Section 4.5 of the paper compares the
stages. At revision-final-2 it was idea 1c ("decisions3", runs/final-2). The
release run is six experiments, each in its own folder, runs/final-3/<name>/:

    1 pet_decisions   PET, 45 documents, on PET's gold spans, the method; scored
                      on PET's flows both ways (text2bpmn.pet_flow_eval)
    2 pet_no_llm      the pairwise mode with every answer UNKNOWN: the text-order
                      control, as runs/final/pet_no_llm
    3 pet_no_and      the method with every answer UNKNOWN: the text order with
                      parallel-gateway words left out, the method's own control
                      (as runs/final-2/pet_no_and: without answers, 3 builds what 1c builds)
    4 cases           the three case studies end to end, each scored against its
                      reference model (text2bpmn.compare)
    5 cases_no_llm    the same with every answer UNKNOWN
    6 coref_ablation  PET, 45 documents, recogniser and pipeline end to end, once
                      with FastCoref and once without; lane assignment scored
                      against PET's actor-performer relations (text2bpmn.lane_accuracy)

The experiments of the method as submitted (relation_mode "pairs") stay
selectable with --only, and are cited from runs/final at the tag
revision-final rather than rerun: table3_302 and corrected_302 (the 302-pair
benchmark, Table 3) and pet_classifier (PET with the pairwise classifier).
A rerun of pet_classifier on 2026-11-11 (runs/ideas/idea1b/pet_pairs) gave
runs/final's counts on all 45 documents.

Every run has the cache off and stops at startup if the LLM cannot be reached
or reports no model digest -- except the no-LLM controls, which point at a
closed port on purpose. Where the pipeline runs every document's ontology is
populated beside its other outputs, and each PET document keeps its model and
answers (process.json). Every folder gets run_record.json: the tag, commit,
model tag, digest and declared revision (llm.revision; from 2026-11-17),
every setting, start and end time and the command; the pipeline's own run
record is inside it.

A real run refuses to start unless the tree is clean and exactly at the tag
`revision-final-3`. --dry-run is the end-to-end test without a GPU: every
experiment in no-LLM mode against a closed port, on 3 PET documents and the 3
cases, into runs/dryrun/.

The output folders are git-ignored, so that the run records the pipeline takes
as each experiment starts are not marked dirty by the experiments before it.
Commit the results after the run with `git add -f runs/final-3`. runs/final
holds the six runs at revision-final, the method as submitted; runs/final-2
those at revision-final-2, idea 1c.
"""
import argparse
import contextlib
import dataclasses
import io
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from text2bpmn.run_config import RunConfig, _git_state, add_arguments, from_arguments

TAG = "revision-final-3"
PET_JOBS = "text2bpmn/baselines/pet_jobs.json"
CASES = ("loan", "goods_dispatch", "healthcare")
CLOSED_PORT = "http://127.0.0.1:1"
EXPERIMENTS = ("pet_decisions", "pet_no_llm", "pet_no_and", "cases", "cases_no_llm", "coref_ablation")
PAIRS = {"relation_mode": "pairs"}  # the method as submitted


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def no_llm(config):
    """No relation answers: a closed port, a short deadline, and the switch
    that lets a run start without its model."""
    return dataclasses.replace(config, allow_no_llm=True, api_base=CLOSED_PORT, llm_timeout=5)


def benchmark(name, config, out, dry):
    """Runs 1 and 2: text2bpmn.benchmark_relations, in its own process."""
    command = [sys.executable, "-m", "text2bpmn.benchmark_relations",
               "--sample-size", "3" if dry else "302", "--seed", "51",
               "--prompt", config.prompt, "--report", str(out / "benchmark.md"),
               "--model", config.llm_model, "--api-base", config.api_base, "--api-key", config.api_key,
               "--llm-timeout", str(config.llm_timeout), "--temperature", str(config.temperature),
               "--reasoning-max-chars", str(config.reasoning_max_chars)]
    # every LLM setting the pipeline runs use, so runs 1 and 2 ask the same way;
    # each is passed either way, since a setting left off the command line falls
    # back to the benchmark's default, not to this run's value
    command += ["--max-tokens", str(config.max_tokens or 0),
                "--no-thinking" if config.disable_thinking else "--thinking",
                "--constrained-output" if config.constrained_output else "--no-constrained-output"]
    if config.model_revision:
        command += ["--model-revision", config.model_revision]
    if config.allow_no_llm:
        command.append("--allow-no-llm")
    with open(out / "log.txt", "w", encoding="utf-8") as log:
        done = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    if done.returncode:
        raise RuntimeError(f"benchmark_relations exited with {done.returncode}; see {out / 'log.txt'}")
    run = json.loads((out / "benchmark_run.json").read_text(encoding="utf-8"))
    return {"command": command, "pipeline_run_record": run}


def pet_flows(name, config, out, dry):
    """Runs 3 and 4: the pipeline on PET's gold spans, scored on PET's flows
    with text2bpmn.pet_flow_eval, one populated ontology per document."""
    from text2bpmn.finder3 import BPMNHybridExtractor
    from text2bpmn.pet_flow_eval import aggregate, score_job, to_markdown

    bundle = json.loads(Path(PET_JOBS).read_text(encoding="utf-8"))
    jobs = bundle["jobs"][:3 if dry else None]
    extractor = BPMNHybridExtractor(config=config, ner_model_path=None)
    records = []
    (out / "records.jsonl").unlink(missing_ok=True)  # a rerun with --only starts this experiment afresh
    for index, job in enumerate(jobs, 1):
        folder = out / "documents" / job["name"]
        folder.mkdir(parents=True, exist_ok=True)
        extractor.config.ontology_out = str(folder / "ontology.owl")
        log, kept = io.StringIO(), {}
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            record = score_job(extractor, job, kept)
        (folder / "log.txt").write_text(log.getvalue(), encoding="utf-8")
        # the model as built and every answer it was built from, so the run
        # can be scored again without asking the LLM again
        (folder / "process.json").write_text(json.dumps(
            {k: kept["result"][k] for k in ("structured_data", "entities_used", "relation_parsing")},
            indent=1, ensure_ascii=False), encoding="utf-8")
        records.append(record)
        with open(out / "records.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"   [{index}/{len(jobs)}] {job['name']}: built {record['counts'].get('tp', 0)}, "
              f"{record['relation_failures']}/{record['relation_calls']} calls failed", flush=True)
    result = aggregate(records, bundle, extractor.run_record)
    result["prompt"] = config.prompt
    (out / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "result.md").write_text(to_markdown(result) + "\n", encoding="utf-8")
    return {"pipeline_run_record": extractor.run_record, "overall": result["overall"],
            "relation_failure_rate": result["relation_failure_rate"]}


def cases(name, config, out, dry):
    """Run 5: the three cases end to end, each scored against its reference."""
    from text2bpmn.checks.pilot_run import run_one
    from text2bpmn.compare import compare, read_bpmn
    from text2bpmn.finder3 import NER_MODEL_PATH, BPMNHybridExtractor

    extractor = BPMNHybridExtractor(config=config, ner_model_path=NER_MODEL_PATH)
    scores = {}
    for case in CASES:
        text = Path(f"text2bpmn/cases/{case}/input.txt").read_text(encoding="utf-8")
        record = run_one(extractor, case, text, out / case)
        if record["status"] == "failed":
            raise RuntimeError(f"{case}: {record['error']}")
        result = compare(read_bpmn(f"text2bpmn/cases/{case}/reference.bpmn"), read_bpmn(out / case / "model.bpmn"))
        (out / case / "comparison.json").write_text(json.dumps(result, indent=2, ensure_ascii=False),
                                                    encoding="utf-8")
        scores[case] = {k: result[k] for k in ("tasks", "gateways", "edges", "ged")}
        print(f"   {case}: tasks F1 {result['tasks']['f1']}, gateways F1 {result['gateways']['f1']}, "
              f"edges F1 {result['edges']['f1']}", flush=True)
    return {"pipeline_run_record": extractor.run_record, "scores": scores}


def coref_ablation(name, config, out, dry):
    """Run 6: the recogniser and pipeline on PET's 45 texts, with FastCoref as
    the pipeline runs it and without it. The second arm replaces the
    coreference step by the identity on this one extractor instance; finder3
    itself has no switch for it."""
    from text2bpmn.checks.pilot_run import run_one
    from text2bpmn.finder3 import NER_MODEL_PATH, BPMNHybridExtractor

    jobs = json.loads(Path(PET_JOBS).read_text(encoding="utf-8"))["jobs"][:3 if dry else None]
    extractor = BPMNHybridExtractor(config=config, ner_model_path=NER_MODEL_PATH)
    arms = {}
    for arm in ("with_coref", "without_coref"):
        if arm == "without_coref":
            extractor._resolve_coreferences = lambda text: text
        records = []
        for job in jobs:
            record = run_one(extractor, job["name"], job["text"], out / arm / job["name"])
            records.append(record)
            print(f"   {arm} {job['name']}: {record['status']}, {record.get('elements', {}).get('task', 0)} tasks, "
                  f"{record.get('lanes', 0)} lanes", flush=True)
        arms[arm] = records
        (out / arm / "records.json").write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    failed = [r["document"] for rs in arms.values() for r in rs if r["status"] == "failed"]
    if failed:
        raise RuntimeError(f"failed documents: {failed}")
    totals = {arm: {"documents": len(rs), "tasks": sum(r["elements"].get("task", 0) for r in rs),
                    "lanes": sum(r["lanes"] for r in rs), "flows": sum(r["flows"] for r in rs),
                    "relation_calls": sum(r["relation_calls"] for r in rs)} for arm, rs in arms.items()}
    from text2bpmn.lane_accuracy import score
    lanes, table = score(out)
    print(table, flush=True)
    for arm, scores in lanes.items():
        totals[arm]["lanes_scored"] = {k: v for k, v in scores.items() if k != "rows"}
    return {"pipeline_run_record": extractor.run_record, "totals": totals}


# the method's experiments take RunConfig's relation_mode (decisions4); those
# of the method as submitted name theirs
RUNNERS = {"pet_decisions": (pet_flows, "corrected", False),
           "pet_no_llm": (pet_flows, "corrected", True, PAIRS),
           "pet_no_and": (pet_flows, "corrected", True),
           "cases": (cases, "corrected", False), "cases_no_llm": (cases, "corrected", True),
           "coref_ablation": (coref_ablation, "corrected", False),
           "table3_302": (benchmark, "table3", False, PAIRS), "corrected_302": (benchmark, "corrected", False, PAIRS),
           "pet_classifier": (pet_flows, "corrected", False, PAIRS)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", nargs="+", choices=list(RUNNERS))
    ap.add_argument("--dry-run", action="store_true",
                    help="no LLM, 3 PET documents and the 3 cases, into runs/dryrun/")
    ap.add_argument("--out", help="default runs/final-3, or runs/dryrun with --dry-run")
    add_arguments(ap)
    args = ap.parse_args()
    if args.llm_cache:
        raise SystemExit("the final runs never use the cache")
    if args.prompt != "corrected" or args.allow_no_llm or args.relation_mode != RunConfig.relation_mode:
        raise SystemExit("--prompt, --allow-no-llm and --relation-mode are set per experiment here, "
                         "not on the command line")
    base = from_arguments(args, llm_cache=False)
    code = _git_state()
    if not args.dry_run and (code["describe"] != TAG or code["dirty"]):
        raise SystemExit(f"the final runs start only on a clean tree exactly at {TAG}; "
                         f"this is {code['describe']} (dirty: {code['dirty']})")
    root = Path(args.out or ("runs/dryrun" if args.dry_run else "runs/final-3"))
    failed = run_experiments(args.only or EXPERIMENTS, RUNNERS, base, code, root, args.dry_run)
    sys.exit(1 if failed else 0)


def run_experiments(names, runners, base, code, root, dry_run):
    """Each experiment in its own folder under `root`, with its run record and
    one summary.json over all of them; the names of those that failed.
    `runners` maps a name to (runner, prompt, whether it is a no-LLM control),
    optionally with a dict of further RunConfig settings for that experiment.
    Shared with text2bpmn/run_gliner_arm.py and text2bpmn/relation_ideas.py."""
    summary = {"dry_run": dry_run, "code": code, "command": sys.argv, "started": now(), "experiments": {}}
    for name in names:
        runner, prompt, control, *settings = runners[name]
        config = dataclasses.replace(base, prompt=prompt, **(settings[0] if settings else {}))
        if control or dry_run:
            config = no_llm(config)
        out = root / name
        out.mkdir(parents=True, exist_ok=True)
        record = {"experiment": name, "dry_run": dry_run, "started": now(), "code": code,
                  "command": sys.argv, "config": dataclasses.asdict(config), "llm": config.llm_identity()}
        print(f"== {name} (prompt {prompt}{', no LLM' if config.allow_no_llm else ''})", flush=True)
        start = time.perf_counter()
        try:
            record.update(runner(name, config, out, dry_run), status="ok")
        except (Exception, SystemExit) as e:
            record.update(status="failed", error=f"{type(e).__name__}: {e}")
            print(f"   failed: {record['error']}", flush=True)
        record.update(finished=now(), seconds=round(time.perf_counter() - start, 1))
        (out / "run_record.json").write_text(json.dumps(record, indent=2, ensure_ascii=False, default=str),
                                             encoding="utf-8")
        summary["experiments"][name] = {k: record.get(k) for k in
                                        ("status", "error", "seconds", "overall", "scores", "totals")}
    summary["finished"] = now()
    (root / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str),
                                       encoding="utf-8")
    failed = [n for n, e in summary["experiments"].items() if e["status"] != "ok"]
    print(f"{len(summary['experiments']) - len(failed)} of {len(summary['experiments'])} experiments ok"
          + (f"; failed: {failed}" if failed else "") + f"; summary in {root / 'summary.json'}")
    return failed


if __name__ == "__main__":
    main()
