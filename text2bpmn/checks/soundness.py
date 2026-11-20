"""Task 3: soundness of every BPMN model in a folder, with WOFLAN.

    python3 -m text2bpmn.checks.soundness runs/pilot [runs/pilot_scripted ...] [--timeout 60]

Per model: pm4py.read_bpmn -> pm4py.convert_to_petri_net -> pm4py.check_soundness
(WOFLAN), each model in its own process with a timeout. The outcome is one of
sound, unsound, conversion_error, timeout, and an unsound model carries what
WOFLAN found: its diagnostic messages, dead tasks, places outside every
S-component, non-well-handled pairs and locking scenarios, each traced back to
BPMN element ids. pm4py names a transition after its BPMN node and a place
ent_<id> or exi_<id> after the node it enters or leaves.

For an unsound model the check also says whether the faulty region contains a
split whose join is of the other type -- an AND split merged by an XOR join or
the reverse, the mismatch that unpaired splits and joins produce -- or not.
"""
import argparse
import multiprocessing
import re
import time
import warnings
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from text2bpmn.checks.common import header, provenance, write

BPMN = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"
NODE_ID = re.compile(r"^(?:ent_|exi_)?(.*)$")


def _ids(items):
    """BPMN element ids behind Petri net places or transitions."""
    out = set()
    for item in items:
        name = getattr(item, "name", str(item))
        out.add(NODE_ID.match(str(name)).group(1))
    return sorted(out)


def _flatten(value):
    if isinstance(value, (list, tuple, set)):
        return [x for v in value for x in _flatten(v)]
    return [value]


def _check(path, queue):
    warnings.filterwarnings("ignore")
    import pm4py
    try:
        net, im, fm = pm4py.convert_to_petri_net(pm4py.read_bpmn(str(path)))
    except Exception as e:
        queue.put({"status": "conversion_error", "reason": f"{type(e).__name__}: {e}"})
        return
    try:
        sound, diag = pm4py.check_soundness(net, im, fm)
    except Exception as e:
        queue.put({"status": "conversion_error", "reason": f"WOFLAN failed: {type(e).__name__}: {e}"})
        return
    found = {str(getattr(k, "value", k)): v for k, v in diag.items()}
    result = {"status": "sound" if sound else "unsound",
              "messages": [str(m) for m in found.get("diagnostic_messages", [])],
              "petri_net": {"places": len(net.places), "transitions": len(net.transitions)}}
    if not sound:
        result["dead_tasks"] = _ids(found.get("dead_tasks") or [])
        result["uncovered_places"] = _ids(_flatten(found.get("uncovered_places_s_component") or []))
        result["not_well_handled_pairs"] = [_ids(pair) for pair in found.get("not_well_handled_pairs") or []]
        result["locking_scenarios"] = [str(s) for s in found.get("locking_scenarios") or []][:10]
        result["elements"] = sorted(set(result["dead_tasks"]) | set(result["uncovered_places"])
                                    | {i for pair in result["not_well_handled_pairs"] for i in pair})
    queue.put(result)


def check(path, timeout):
    queue = multiprocessing.Queue()
    worker = multiprocessing.Process(target=_check, args=(path, queue))
    start = time.perf_counter()
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        worker.terminate()
        worker.join()
        return {"status": "timeout", "reason": f"no answer within {timeout} s",
                "seconds": round(time.perf_counter() - start, 2)}
    result = queue.get() if not queue.empty() else {"status": "conversion_error",
                                                    "reason": f"worker exited with code {worker.exitcode}"}
    result["seconds"] = round(time.perf_counter() - start, 2)
    return result


def mismatched_joins(path):
    """Splits whose nearest downstream join is of the other gateway type."""
    root = ET.parse(path).getroot()
    process = root.find(BPMN + "process")
    kind = {}
    for element in process:
        tag = element.tag.replace(BPMN, "")
        if "id" in element.attrib:
            kind[element.get("id")] = tag
    succ = {}
    for flow in process.iter(BPMN + "sequenceFlow"):
        succ.setdefault(flow.get("sourceRef"), []).append(flow.get("targetRef"))
    preds = Counter(f.get("targetRef") for f in process.iter(BPMN + "sequenceFlow"))
    gateways = ("exclusiveGateway", "parallelGateway")
    out = []
    for node, tag in kind.items():
        if tag not in gateways or len(succ.get(node, [])) < 2:
            continue
        seen, frontier, join = {node}, list(succ[node]), None
        while frontier and join is None:
            nxt = []
            for n in frontier:
                if n in seen:
                    continue
                seen.add(n)
                if kind.get(n) in gateways and preds[n] >= 2:
                    join = n
                    break
                nxt += succ.get(n, [])
            frontier = nxt
        if join and kind[join] != tag:
            out.append({"split": node, "split_type": tag, "join": join, "join_type": kind[join]})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("folders", nargs="+")
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--out", default="runs/checks/soundness")
    args = ap.parse_args()
    record = provenance(folders=args.folders, timeout_seconds=args.timeout)
    result = {"provenance": record, "folders": {}}
    lines = header("Soundness (pm4py WOFLAN)", record)
    for folder in args.folders:
        models = {}
        for path in sorted(Path(folder).rglob("*.bpmn")):
            outcome = check(path, args.timeout)
            if outcome["status"] == "unsound":
                outcome["mismatched_split_join"] = mismatched_joins(path)
                outcome["cause"] = ("a split joined by a gateway of the other type"
                                    if outcome["mismatched_split_join"] else "other (see elements and messages)")
            models[str(path.relative_to(folder))] = outcome
        counts = Counter(m["status"] for m in models.values())
        result["folders"][folder] = {"models": len(models), "counts": dict(counts), "per_model": models}
        lines += [f"## {folder}", "",
                  ", ".join(f"{counts.get(s, 0)} {s}" for s in ("sound", "unsound", "conversion_error", "timeout"))
                  + f" of {len(models)} models.", ""]
        for name, m in models.items():
            if m["status"] != "sound":
                lines.append(f"- `{name}`: {m['status']}; {m.get('cause') or m.get('reason')}; "
                             f"elements {m.get('elements', [])}; {'; '.join(m.get('messages', []))[:300]}")
        lines.append("")
    print("wrote", write(args.out, "soundness", result, "\n".join(lines)))
    print("\n".join(lines[3:]))


if __name__ == "__main__":
    main()
