"""Pilot run, no LLM: the pipeline end to end on the 45 PET documents and the
three case-study inputs, to give the structural checks something to check.

    python3 -m text2bpmn.checks.pilot_run [--out runs/pilot] [--only DOC ...]

Every document gets its own folder, runs/pilot/<doc_id>/:

    model.bpmn       BPMN 2.0 XML, as `finder3 --bpmn` writes it
    ontology.owl     the populated BBO copy, as `finder3 --ontology-out` writes it
                     (ontology.py also leaves ontology_offline_ontology.owl beside
                     it: the input ontology without its unreachable UO import)
    extraction.json  finder3's whole result, as `finder3 -o` writes it
    decisions.json   the relation decision log: every pair asked, its label, why
    validation.json  every change the Validation Layer made, by rule
    run_record.json  tag, commit, packages, settings, LLM identity, timing, status
    log.txt          everything the pipeline printed for this document

and the folder gets summary.json and summary.md.

The models are loaded once and finder3 is called in-process, with the same
steps as finder3.main: process_text, then validate and to_xml. Run as one
command per document it would load the 1.1 GB checkpoint and FastCoref 48
times. No pipeline code is changed or patched.

No-LLM mode: --allow-no-llm with the server absent, so every relation call
fails and is logged as UNKNOWN. Cache off, prompt `corrected`.
"""
import argparse
import contextlib
import io
import json
import time
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

PET_JOBS = "text2bpmn/baselines/pet_jobs.json"
CASES = ("loan", "goods_dispatch", "healthcare")
PILOT_TEXTS = Path(__file__).parent / "pilot_texts"


def documents():
    """(doc_id, text) for the 45 PET documents, the three cases, then the
    pilot-only texts with explicit parallel blocks (pilot_texts/).

    PET ships tokens, not text; pet_jobs.json joins them with single spaces
    ("has degraded ."), which is the text every PET run here has used.
    """
    jobs = json.loads(Path(PET_JOBS).read_text(encoding="utf-8"))["jobs"]
    docs = [(job["name"], job["text"]) for job in jobs]
    docs += [(f"case-{case}", Path(f"text2bpmn/cases/{case}/input.txt").read_text(encoding="utf-8"))
             for case in CASES]
    docs += [(f"pilot-{path.stem}", path.read_text(encoding="utf-8"))
             for path in sorted(PILOT_TEXTS.glob("*.txt"))]
    return docs


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_one(extractor, doc_id, text, folder, entities=None):
    """`entities`, when given, are spans from a recogniser outside this process
    (finder3.process_text), so the pipeline's own recogniser does not run."""
    from text2bpmn.bpmn_xml import to_xml
    from text2bpmn.structure import validate

    folder.mkdir(parents=True, exist_ok=True)
    ontology = folder / "ontology.owl"
    extractor.config.ontology_out = str(ontology)
    record = {"document": doc_id, "words": len(text.split()), "started": now()}
    log = io.StringIO()
    start = time.perf_counter()
    try:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            result = extractor.process_text(text, entities=entities)
            process = validate(result["structured_data"])
            (folder / "model.bpmn").write_text(to_xml(process, doc_id), encoding="utf-8")
        (folder / "extraction.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        (folder / "decisions.json").write_text(
            json.dumps(result["relation_parsing"], indent=2, ensure_ascii=False), encoding="utf-8")
        (folder / "validation.json").write_text(json.dumps({
            "rule_counts": dict(Counter(rule for rule, _ in process.log)),
            "changes": [{"rule": rule, "change": change} for rule, change in process.log],
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        # process_text reports a failed ontology step and carries on, so the
        # file's presence is the test
        status = "ok" if ontology.exists() else "ontology_failed"
        kinds = Counter(n.kind for n in process.nodes.values())
        record.update(status=status, elements=dict(kinds), flows=len(process.flows),
                      lanes=len({n.lane for n in process.nodes.values()}),
                      relation_calls=result["relation_parsing"]["calls"],
                      relation_failures=result["relation_parsing"]["failures"],
                      relations_not_asked=result["relation_parsing"]["skipped"])
    except Exception as e:
        record.update(status="failed", error=f"{type(e).__name__}: {e}",
                      traceback=traceback.format_exc())
    record["seconds"] = round(time.perf_counter() - start, 2)
    record["finished"] = now()
    (folder / "log.txt").write_text(log.getvalue(), encoding="utf-8")
    run = dict(extractor.run_record)
    run["config"] = dict(run["config"], ontology_out=str(ontology))
    (folder / "run_record.json").write_text(
        json.dumps({**run, "document": record}, indent=2, ensure_ascii=False), encoding="utf-8")
    return record


def summarise(records, run_record, load_seconds, total_seconds, out, title="Pilot run, no LLM"):
    ok = [r for r in records if r["status"] == "ok"]
    failed = [r for r in records if r["status"] != "ok"]
    summary = {"documents": len(records), "finished": len(ok), "failed": len(failed),
               "scripted_llm": bool(run_record.get("scripted_llm")),
               "model_load_seconds": load_seconds, "total_seconds": total_seconds,
               "document_seconds": round(sum(r["seconds"] for r in records), 2),
               "run_record": run_record, "records": records}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    code = run_record["code"]
    lines = [f"# {title} ({run_record['run_at']})", "",
             f"Code {code['describe']} ({code['commit'][:7]}, dirty: {code['dirty']}), "
             f"prompt `{run_record['config']['prompt']}`, cache {run_record['config']['llm_cache']}, "
             f"allow_no_llm {run_record['config']['allow_no_llm']}, LLM reachable: "
             f"{run_record['llm'].get('reachable')}.", "",
             f"{len(ok)} of {len(records)} documents finished, {len(failed)} failed. "
             f"Models loaded in {load_seconds} s; documents took {summary['document_seconds']} s; "
             f"{total_seconds} s in all.", ""]
    if failed:
        lines += ["## Failed", ""] + [f"- `{r['document']}`: {r['status']} -- {r.get('error', '')}"
                                     for r in failed] + [""]
    lines += ["## Per document", "",
              "| document | status | words | seconds | tasks | XOR | AND | flows | lanes | calls | failed calls |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in records:
        e = r.get("elements", {})
        lines.append(f"| {r['document']} | {r['status']} | {r['words']} | {r['seconds']} | "
                     f"{e.get('task', '')} | {e.get('exclusiveGateway', '')} | "
                     f"{e.get('parallelGateway', '')} | {r.get('flows', '')} | {r.get('lanes', '')} | "
                     f"{r.get('relation_calls', '')} | {r.get('relation_failures', '')} |")
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="runs/pilot")
    ap.add_argument("--only", nargs="*", help="run only these document ids")
    args = ap.parse_args()

    from text2bpmn.finder3 import NER_MODEL_PATH, BPMNHybridExtractor
    from text2bpmn.run_config import RunConfig

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    docs = [d for d in documents() if not args.only or d[0] in args.only]
    begin = time.perf_counter()
    config = RunConfig(allow_no_llm=True, llm_cache=False, prompt="corrected")
    extractor = BPMNHybridExtractor(config=config, ner_model_path=NER_MODEL_PATH)
    load_seconds = round(time.perf_counter() - begin, 2)

    records = []
    for index, (doc_id, text) in enumerate(docs, 1):
        record = run_one(extractor, doc_id, text, out / doc_id)
        records.append(record)
        print(f"[{index}/{len(docs)}] {doc_id}: {record['status']} in {record['seconds']} s"
              + (f" -- {record['error']}" if record.get("error") else ""), flush=True)
    summary = summarise(records, extractor.run_record, load_seconds,
                        round(time.perf_counter() - begin, 2), out)
    print(f"{summary['finished']}/{summary['documents']} finished; summary in {out / 'summary.md'}")


if __name__ == "__main__":
    main()
