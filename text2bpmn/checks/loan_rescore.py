"""The four loan configurations of the release runs, scored once against the
textbook reference (decision D12) beside the authored one.

    python3 -m text2bpmn.checks.loan_rescore [--out runs/checks/final-3/loan_reference]

Nothing is run again. Each configuration's model is the saved model.bpmn of
the release run (runs/final-3, runs/gliner-3); it is scored with the code the
release run used, text2bpmn.compare.compare on read_bpmn of both files, as
text2bpmn/run_final.py does for every case, and with
text2bpmn.behaviour.compare_behaviour for the footprints. One threshold,
compare.DEFAULT_THRESHOLD, and nothing tuned.

Two references:

- authored: text2bpmn/cases/loan/reference_authored.bpmn, the reference the
  release runs were scored against. The run's saved score is reported as the
  old score -- comparison_authored.json where the run folder has one (all four
  loan folders since 2026-11-20, whose comparison.json is now the textbook
  score), comparison.json otherwise -- and the authored file is scored
  again here to check that it gives the saved numbers exactly
  (`reproduces_saved`). Where comparison_authored.json exists, comparison.json
  is checked to be the textbook score (`saved_textbook_matches`). The release run saved
  no footprint, so the old footprint similarity is computed here, against the
  authored file.
- textbook: text2bpmn/cases/loan/reference.bpmn, Solution 3.2 of the textbook.

Besides the counts, each comparison lists what was matched, recomputed from
the same functions compare() uses: the task pairs from compare.match_tasks
with their compare.similarity; the gateways by kind and role (compare counts
a gateway as matched by these keys, not one to one by node); and the
task-to-task edges (Model.task_edges) whose two ends map onto an edge of the
generated model. RGED is reported both ways compare.py computes it: over
|G1| + |G2| (rged_combined, Sim = similarity_combined = 1 - RGED) and over
max(|G1|, |G2|) (rged, similarity, the paper's Eq. 12).
"""
import argparse
import hashlib
import json
from pathlib import Path

from text2bpmn.behaviour import compare_behaviour
from text2bpmn.checks.common import header, provenance, write
from text2bpmn.compare import DEFAULT_THRESHOLD, compare, match_tasks, read_bpmn, similarity

CONFIGURATIONS = (("BERT, LLM", "runs/final-3/cases/loan"),
                  ("BERT, no LLM", "runs/final-3/cases_no_llm/loan"),
                  ("GLiNER, LLM", "runs/gliner-3/cases_gliner/loan"),
                  ("GLiNER, no LLM", "runs/gliner-3/cases_gliner_no_llm/loan"))
REFERENCES = (("authored", "text2bpmn/cases/loan/reference_authored.bpmn"),
              ("textbook", "text2bpmn/cases/loan/reference.bpmn"))
ELEMENTS = ("tasks", "gateways", "edges")
GED_FIELDS = ("ged", "reference_size", "generated_size", "rged_combined", "similarity_combined",
              "rged", "similarity")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def label(model, node_id):
    node = model.nodes[node_id]
    return node.name or node.id


def describe(model):
    """What a model holds, as compare.read_bpmn reads it."""
    kinds = {}
    for node in model.nodes.values():
        key = node.kind if node.kind != "gateway" else f"gateway {node.detail} {node.role}"
        kinds[key] = kinds.get(key, 0) + 1
    return {"size": model.size(), "nodes": len(model.nodes), "flows": len(model.flows), "kinds": kinds,
            "tasks": [t.name for t in model.tasks],
            "task_edges": [[label(model, s), label(model, t)] for s, t in model.task_edges()]}


def matched_elements(reference, generated, threshold=DEFAULT_THRESHOLD):
    """The elements behind compare()'s tasks, gateways and edges counts."""
    mapping = match_tasks(reference, generated, threshold)
    tasks = [{"reference": reference.nodes[r].name, "generated": generated.nodes[g].name,
              "similarity": round(similarity(reference.nodes[r].name, generated.nodes[g].name), 3)}
             for r, g in mapping.items()]

    def by_key(model):
        out = {}
        for g in model.gateways:
            out.setdefault(f"{g.detail}_{g.role}", []).append(g.name or g.id)
        return out

    ref_gw, gen_gw = by_key(reference), by_key(generated)
    gateways = [{"key": k, "reference": ref_gw.get(k, []), "generated": gen_gw.get(k, []),
                 "matched": min(len(ref_gw.get(k, [])), len(gen_gw.get(k, [])))}
                for k in sorted(set(ref_gw) | set(gen_gw))]

    generated_edges = set(generated.task_edges())
    matched, missed = [], []
    for s, t in reference.task_edges():
        pair = (mapping.get(s), mapping.get(t))
        target = matched if pair in generated_edges else missed
        target.append({"reference": [label(reference, s), label(reference, t)],
                       **({"generated": [label(generated, pair[0]), label(generated, pair[1])]}
                          if pair in generated_edges else {})})
    hit = {(mapping.get(s), mapping.get(t)) for s, t in reference.task_edges()}
    extra = [[label(generated, s), label(generated, t)] for s, t in sorted(generated_edges) if (s, t) not in hit]
    unmatched_ref = [t.name for t in reference.tasks if t.id not in mapping]
    unmatched_gen = [t.name for t in generated.tasks if t.id not in set(mapping.values())]
    best = {t.name: max(((similarity(t.name, r.name), r.name) for r in reference.tasks), default=(0.0, ""))
            for t in generated.tasks if t.name in unmatched_gen}
    return {"tasks": tasks, "unmatched_reference_tasks": unmatched_ref,
            "unmatched_generated_tasks": [{"generated": n, "closest_reference": best[n][1],
                                           "similarity": round(best[n][0], 3)} for n in unmatched_gen],
            "gateways": gateways, "edges_matched": matched, "edges_missed": missed, "edges_extra": extra}


def score(reference_path, generated_path):
    reference, generated = read_bpmn(reference_path), read_bpmn(generated_path)
    result = compare(reference, generated)        # as run_final.py scores every case
    elements = matched_elements(reference, generated)
    assert len(elements["tasks"]) == result["tasks"]["tp"]
    assert sum(g["matched"] for g in elements["gateways"]) == result["gateways"]["tp"]
    assert len(elements["edges_matched"]) == result["edges"]["tp"]
    assert len(elements["edges_extra"]) == result["edges"]["fp"]
    behaviour = compare_behaviour(reference_path, generated_path)
    return {"comparison": result, "matched": elements,
            "footprint": {"behavioural_similarity": behaviour["behavioural_similarity"],
                          "pm4py_behavioral_similarity": behaviour["pm4py_behavioral_similarity"],
                          "relations": behaviour["relations"], "renamed": behaviour["renamed"],
                          "missing_behaviour": behaviour["missing_behaviour"]}}


def differences(saved, now, path=""):
    """Where two comparison results disagree, by key path."""
    if isinstance(saved, dict) and isinstance(now, dict):
        return [d for k in sorted(set(saved) | set(now))
                for d in differences(saved.get(k), now.get(k), f"{path}.{k}" if path else k)]
    if isinstance(saved, (list, tuple)) and isinstance(now, (list, tuple)):
        if len(saved) != len(now):
            return [path]
        return [d for i, (a, b) in enumerate(zip(saved, now)) for d in differences(a, b, f"{path}[{i}]")]
    if isinstance(saved, float) or isinstance(now, float):
        return [] if saved is not None and now is not None and abs(saved - now) < 1e-9 else [path]
    return [] if saved == now else [path]


def saved_authored_comparison(folder):
    """The run's own score against the authored reference: comparison_authored.json
    where comparison.json has been replaced by the textbook score, else comparison.json."""
    authored = Path(folder, "comparison_authored.json")
    return authored if authored.exists() else Path(folder, "comparison.json")


def prf_cell(m):
    return (f"{m['tp']}/{m['fp']}/{m['fn']} | {m['precision']:.3f} | {m['recall']:.3f} | {m['f1']:.3f}")


def to_markdown(result, record):
    lines = header("Loan: the release runs' models against the textbook reference (D12)", record)
    lines += ["Each saved model.bpmn scored with text2bpmn.compare.compare (as run_final.py) and "
              "text2bpmn.behaviour.compare_behaviour, against the authored reference the release runs "
              "used (`old`; the counts and GED are the run's saved score -- comparison_authored.json where the "
              "folder has one, else comparison.json -- and the footprint is computed "
              "here) and against the textbook's Solution 3.2 (`new`). RGED = GED / (|G1| + |G2|) "
              "(compare.py `rged_combined`), Sim = 1 - RGED (`similarity_combined`); the Eq. 12 values over "
              "max(|G1|, |G2|) are in the last two columns. Footprint = behavioural similarity of the "
              "relabelled footprints (behaviour.py).", "", "## References", "",
              "| reference | file | nodes | flows | \\|G\\| | tasks | task edges | gateways (kind role: n) |",
              "|---|---|---|---|---|---|---|---|"]
    for name, ref in result["references"].items():
        gateways = ", ".join(f"{k[8:]}: {v}" for k, v in sorted(ref["kinds"].items()) if k.startswith("gateway"))
        lines.append(f"| {name} | `{ref['path']}` | {ref['nodes']} | {ref['flows']} | {ref['size']} | "
                     f"{len(ref['tasks'])} | {len(ref['task_edges'])} | {gateways} |")
    lines += ["", "## Scores", "",
              "| configuration | ref | tasks TP/FP/FN | P | R | F1 | gateways TP/FP/FN | P | R | F1 | "
              "flows TP/FP/FN | P | R | F1 | GED | \\|G\\| gen | \\|G\\| ref | RGED | Sim | footprint | "
              "RGED max | Sim max |", "|---" * 23 + "|"]
    for config, entry in result["configurations"].items():
        for ref, key in (("old", "saved"), ("new", "textbook")):
            c = entry["saved_comparison"] if key == "saved" else entry["textbook"]["comparison"]
            footprint = entry["authored" if key == "saved" else "textbook"]["footprint"]["behavioural_similarity"]
            g = c["ged"]
            lines.append(f"| {config} | {ref} | " + " | ".join(prf_cell(c[e]) for e in ELEMENTS)
                         + f" | {g['ged']} | {g['generated_size']} | {g['reference_size']} | "
                           f"{g['rged_combined']} | {g['similarity_combined']} | {footprint} | "
                           f"{g['rged']} | {g['similarity']} |")
    lines += ["", "The authored reference scored again here gives the run's saved score exactly: "
              + ", ".join(f"{c} {'yes' if e['reproduces_saved'] else 'NO ' + str(e['differences'])} "
                          f"(`{Path(e['saved_comparison_file']).name}`)"
                          for c, e in result["configurations"].items()) + "."]
    lines += [f"In `{Path(e['saved_comparison_file']).parent}`, comparison.json is the textbook score: "
              f"{'yes' if e['saved_textbook_matches'] else 'NO'}."
              for e in result["configurations"].values() if "saved_textbook_matches" in e]
    lines += [""]

    for config, entry in result["configurations"].items():
        lines += [f"## {config}: what was matched", "", f"Model `{entry['model']}`.", ""]
        for ref in ("authored", "textbook"):
            m = entry[ref]["matched"]
            lines += [f"### against the {ref} reference ({'old' if ref == 'authored' else 'new'})", "",
                      "Tasks (reference <- generated, similarity): "
                      + ("; ".join(f"{t['reference']} <- {t['generated']} ({t['similarity']})" for t in m["tasks"])
                         or "none") + ".",
                      "Reference tasks unmatched: " + (", ".join(m["unmatched_reference_tasks"]) or "none")
                      + ". Generated tasks unmatched (closest reference task by compare.similarity, "
                        "whether or not it is assigned to another task; similarity): "
                      + (", ".join(f"{t['generated']} ({t['closest_reference']}, {t['similarity']})"
                                   for t in m["unmatched_generated_tasks"]) or "none") + ".",
                      "Gateways (kind_role: reference / generated, matched): "
                      + "; ".join(f"{g['key']}: {len(g['reference'])} / {len(g['generated'])}, {g['matched']}"
                                  for g in m["gateways"]) + ".",
                      "Flows matched (reference edge = generated edge): "
                      + ("; ".join(f"{' -> '.join(e['reference'])} = {' -> '.join(e['generated'])}"
                                   for e in m["edges_matched"]) or "none") + ".",
                      "Reference flows missed: " + ("; ".join(" -> ".join(e["reference"]) for e in m["edges_missed"])
                                                    or "none") + ".",
                      "Generated flows extra: " + ("; ".join(" -> ".join(e) for e in m["edges_extra"]) or "none")
                      + ".", ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="runs/checks/final-3/loan_reference")
    args = ap.parse_args()
    record = provenance(threshold=DEFAULT_THRESHOLD,
                        references={n: {"path": p, "sha256": sha256(p)} for n, p in REFERENCES},
                        models={c: {"path": f"{f}/model.bpmn", "sha256": sha256(f"{f}/model.bpmn")}
                                for c, f in CONFIGURATIONS})
    result = {"provenance": record,
              "references": {n: {"path": p, **describe(read_bpmn(p))} for n, p in REFERENCES},
              "configurations": {}}
    for config, folder in CONFIGURATIONS:
        model = f"{folder}/model.bpmn"
        saved_file = saved_authored_comparison(folder)
        saved = json.loads(saved_file.read_text(encoding="utf-8"))
        entry = {"model": model, "saved_comparison_file": str(saved_file),
                 "saved_comparison": saved, "generated": describe(read_bpmn(model))}
        for name, path in REFERENCES:
            entry[name] = score(path, model)
        diff = differences(saved, entry["authored"]["comparison"])
        entry.update(reproduces_saved=not diff, differences=diff)
        if saved_file.name == "comparison_authored.json":
            textbook_saved = json.loads(Path(folder, "comparison.json").read_text(encoding="utf-8"))
            entry["saved_textbook_matches"] = not differences(textbook_saved, entry["textbook"]["comparison"])
        result["configurations"][config] = entry
    print("wrote", write(args.out, "loan_rescore", result, to_markdown(result, record)))


if __name__ == "__main__":
    main()
