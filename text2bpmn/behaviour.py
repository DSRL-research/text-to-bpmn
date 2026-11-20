"""Behavioural comparison of two BPMN models, through their footprints.

    python3 -m text2bpmn.behaviour --reference REF.bpmn --generated GEN.bpmn

The element counts and the graph edit distance in text2bpmn/compare.py are
structural: they ask which nodes and edges a model has. A footprint asks what
the model can do -- for each pair of activities, whether one can follow the
other, and whether they can happen in either order (concurrency). Two models
can share most of their nodes and still permit quite different behaviour, which
is why the paper's claim that the comparison is structural rather than
functional needs a functional measure beside it to mean anything.

Footprints come from pm4py, which the project already depends on: each model is
converted to a Petri net and its footprint taken from the reachability graph.

Two numbers are reported, because they answer different questions:

- **pm4py's own `behavioral_similarity`**, on the models as they are. It
  compares activities by label, so a generated model whose steps are named
  differently scores near zero however well it behaves. That is the
  out-of-the-box number.
- **the relabelled comparison**, where each generated activity is renamed to
  the reference label it was matched with, by the same one-to-one matching the
  element counts use. Behaviour is then measured independently of naming. An
  activity that matched nothing keeps its own name and so contributes only
  false positives, as it should.
"""
import argparse
import json
import warnings
from pathlib import Path

from text2bpmn.compare import DEFAULT_THRESHOLD, match_tasks, prf, read_bpmn

RELATIONS = ("sequence", "parallel", "start_activities", "activities")


def _pm4py():
    warnings.filterwarnings("ignore")
    import pm4py
    return pm4py


def _key(name):
    """A label without its whitespace. pm4py and text2bpmn.compare read a
    multi-line label differently -- "Get 3 offers\nfrom logistic\ncompanies"
    comes back as "offersfrom logisticcompanies" from one and with single
    spaces from the other -- so neither spelling can be the thing matched on."""
    return "".join(str(name).split()).lower()


def footprints(path, display=None):
    """What the model permits: directly-follows pairs, concurrent pairs, the
    activities and the possible first activities.

    `display` renames the activities to the labels compare.py reads, so that
    footprints and task matching speak of activities by the same name.
    """
    pm4py = _pm4py()
    from pm4py.algo.discovery.footprints import algorithm as discover

    net, initial, final = pm4py.convert_to_petri_net(pm4py.read_bpmn(str(path)))
    found = discover.apply(net, initial, final)
    names = display or {}

    def rename(item):
        if isinstance(item, (tuple, list)):
            return tuple(names.get(_key(part), part) for part in item)
        return names.get(_key(item), item)

    return {key: {rename(item) for item in found.get(key, set())} for key in RELATIONS}


def relabel(found, names):
    """The same footprint with each activity renamed to its matched counterpart."""
    def rename(item):
        if isinstance(item, tuple):
            return tuple(names.get(part, part) for part in item)
        return names.get(item, item)

    return {key: {rename(item) for item in value} for key, value in found.items()}


def compare_behaviour(reference_path, generated_path, threshold=DEFAULT_THRESHOLD):
    reference_model, generated_model = read_bpmn(reference_path), read_bpmn(generated_path)
    mapping = match_tasks(reference_model, generated_model, threshold)
    names = {generated_model.nodes[g].name: reference_model.nodes[r].name
             for r, g in mapping.items()}

    reference = footprints(reference_path, {_key(n.name): n.name for n in reference_model.tasks})
    generated = relabel(
        footprints(generated_path, {_key(n.name): n.name for n in generated_model.tasks}), names)
    result = {"renamed": len(names), "relations": {}}
    for key in RELATIONS:
        expected, found = reference[key], generated[key]
        shared = expected & found
        union = expected | found
        result["relations"][key] = {
            **prf(len(shared), len(found - expected), len(expected - found)),
            "jaccard": round(len(shared) / len(union), 3) if union else 1.0,
            "reference": len(expected), "generated": len(found),
        }
    overall_expected = {(key, item) for key in RELATIONS[:3] for item in reference[key]}
    overall_found = {(key, item) for key in RELATIONS[:3] for item in generated[key]}
    union = overall_expected | overall_found
    result["behavioural_similarity"] = round(len(overall_expected & overall_found) / len(union), 3) \
        if union else 1.0
    result["missing_behaviour"] = sorted(f"{a} -> {b}" for a, b in reference["sequence"] - generated["sequence"])
    result["pm4py_behavioral_similarity"] = _pm4py_similarity(reference_path, generated_path)
    return result


def _pm4py_similarity(reference_path, generated_path):
    """pm4py's own measure, on the labels as they stand; None if it cannot run."""
    pm4py = _pm4py()
    try:
        return round(float(pm4py.behavioral_similarity(
            pm4py.read_bpmn(str(reference_path)), pm4py.read_bpmn(str(generated_path)))), 3)
    except Exception as error:  # a model it cannot convert, or a version without it
        return {"error": f"{type(error).__name__}: {error}"}


def to_markdown(result):
    lines = [f"Behavioural footprints, with {result['renamed']} generated activities renamed to the "
             f"reference labels they were matched with.", "",
             "| Relation | Reference | Generated | TP | FP | FN | Jaccard |", "|---|---|---|---|---|---|---|"]
    for key, scores in result["relations"].items():
        lines.append(f"| {key.replace('_', ' ')} | {scores['reference']} | {scores['generated']} | "
                     f"{scores['tp']} | {scores['fp']} | {scores['fn']} | {scores['jaccard']} |")
    pm4py_score = result["pm4py_behavioral_similarity"]
    if isinstance(pm4py_score, dict):  # the full message is kept in the JSON
        first = pm4py_score["error"].split(":")[0]
        reported = f"no answer ({first}: it could not convert the model)"
    else:
        reported = str(pm4py_score)
    lines += ["", f"Behavioural similarity {result['behavioural_similarity']} over the relabelled "
                  f"footprints, against {reported} from pm4py's own measure, which compares "
                  f"activities by label."]
    if result["missing_behaviour"]:
        lines += ["", "Orderings the reference permits and the generated model does not: "
                      + "; ".join(result["missing_behaviour"][:8])
                      + (", ..." if len(result["missing_behaviour"]) > 8 else "")]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--reference", required=True)
    ap.add_argument("--generated", required=True)
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("--json", help="write the full result here")
    args = ap.parse_args()
    result = compare_behaviour(args.reference, args.generated, args.threshold)
    print(to_markdown(result))
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n✅ Wrote {args.json}")


if __name__ == "__main__":
    main()
