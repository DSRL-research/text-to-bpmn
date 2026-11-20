"""The final method's release run, looked at four ways that the scores do not show.

    python3 -m text2bpmn.checks.method_analysis      # -> text2bpmn/results/method_analysis.{md,json}

Everything is read from committed runs (runs/final-3, runs/final-2) and PET's
gold annotation as Neuberger et al. convert it (text2bpmn/pet_strict.py --fetch);
no model is run.

1. **Limits.** From the release run's logged answers: decisions whose window
   filled without an "after" (a branch may run past it), decisions ended by a
   later decision word after branch steps (where a nested decision would have
   been cut), second mentions absorbed, answers with no branch, concurrency
   words asked; and PET's flows that run backward in the text, which the
   method cannot build, except a concurrency word's flow back to a line of work
   that starts before it.
2. **The Validation Layer.** The layer run again on the saved graphs (it is
   deterministic), its log tallied by rule.
3. **Decisions, one by one.** PET does not annotate which steps belong to a
   branch, only flows, so a branch's extent cannot be scored. What can: whether
   each gold decision -- PET's XOR Gateway mentions grouped by its own `same
   gateway` links -- gets the right *branch heads*, the targets of the flows
   leaving its mentions or their conditions. The model is read as the strict
   comparison writes it (pet_strict.render, from a replay that must rebuild the
   saved graph). Scored for the method and, for context, for the text order,
   the method's own no-LLM control and idea 1c; the share right is set beside
   theirs with a paired bootstrap over documents (1000 resamples, seed 0).
4. **Errors.** The strict Flow errors of the method, by the kinds of mention
   they join, with two examples each.

Lanes without the activities that also have an actor recipient come from
text2bpmn/lane_accuracy.py --exclude-recipients and are included here.
"""
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

from text2bpmn import pet_strict as ps

OUT = Path("text2bpmn/results/method_analysis")
METHOD_RUN = "runs/final-3"
RUNS = {"the method (idea 3)": ("runs/final-3/pet_decisions", "decisions4"),
        "idea 1c": ("runs/final-2/pet_decisions", "decisions3"),
        "the method's no-LLM control": ("runs/final-3/pet_no_and", "decisions4"),
        "text order, no LLM": ("runs/final-3/pet_no_llm", "pairs")}
METHOD = "the method (idea 3)"
RESAMPLES, SEED = 1000, 0
LANE_ARMS = {"BERT, with FastCoref": ("runs/final-3/coref_ablation", "with_coref"),
             "BERT, without FastCoref": ("runs/final-3/coref_ablation", "without_coref"),
             "GLiNER A, with FastCoref": ("runs/gliner-3/lanes_gliner", "with_coref")}


# --- 1. limits ---------------------------------------------------------------------

def _answers(paths, key):
    out = []
    for path in paths:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        out += [a for a in (data[key] if key else data)["decisions"] if a.get("source") == "llm"]
    return out


def limits(gold):
    pet = _answers(sorted(Path(METHOD_RUN, "pet_decisions/documents").glob("*/process.json")), "relation_parsing")
    cases = _answers(sorted(Path(METHOD_RUN, "cases").glob("*/decisions.json")), None)
    result = {}
    for name, answers in (("PET", pet), ("cases", cases)):
        c = Counter()
        for a in answers:
            labels, items = a["label"].split(), a["node_B"].split(" | ")
            if a["node_A"].startswith("parallel: "):
                c["concurrency words asked"] += 1
                end = labels.index("after") if "after" in labels else len(labels)
                c["concurrency answers with two lines or more"] += len({x for x in labels[:end] if x in "abc"}) >= 2
                continue
            c["decisions asked"] += 1
            kinds = ["decision" if i.startswith("decision: ") else "step" for i in items]
            end = labels.index("after") if "after" in labels else len(labels)
            branched = any(x in ("yes", "no") for x in labels[:end])
            c["no branch in the answer (text order kept)"] += not branched
            c["second mentions absorbed ('same')"] += labels[:end].count("same")
            c["decisions that absorbed a second mention"] += "same" in labels[:end]
            if "after" not in labels:
                c["window full (10 items), no 'after'" if len(labels) == 10 else
                  "no 'after' before the text's end"] += 1
            if end < len(labels) and kinds[end] == "decision" and branched:
                c["ended by a later decision word after branch steps (possible nesting)"] += 1
        result[name] = dict(c)
    result["PET"]["concurrency words in the text"] = sum(1 for g in gold.values() for k in g["mentions"]
                                                         if k[0] == "and gateway")
    case_cues = 0
    for path in Path(METHOD_RUN, "cases").glob("*/extraction.json"):
        case_cues += sum(1 for e in json.loads(path.read_text(encoding="utf-8"))["entities_used"]
                         if e.get("label") == "AND Gateway")
    result["cases"]["concurrency words in the text (recognised)"] = case_cues
    flows = [(h, t) for g in gold.values() for tag, h, t in g["relations"] if tag == "flow"]
    result["PET"]["gold Flow relations"] = len(flows)
    backward = [(h, t) for h, t in flows if t[1] < h[1]]
    result["PET"]["gold Flow relations running backward in the text"] = len(backward)
    # a concurrency word's split can point back to a line of work that starts
    # before the word, which the concurrency question looks back to build
    result["PET"]["of them, from a concurrency word to a line before it"] = sum(1 for h, t in backward
                                                                               if h[0] == "and gateway")
    return result


# --- 2. the Validation Layer -------------------------------------------------------------

def validation_rules():
    from text2bpmn.structure import validate

    result = {}
    for name, pattern in (("PET", "pet_decisions/documents/*/process.json"), ("cases", "cases/*/extraction.json")):
        fired, models, kinds = Counter(), Counter(), Counter()
        paths = sorted(Path(METHOD_RUN).glob(pattern))
        for path in paths:
            process = validate(json.loads(path.read_text(encoding="utf-8"))["structured_data"])
            seen = set()
            for rule, message in process.log:
                if rule == "clean":
                    dropped = int(re.match(r"(\d+)", message).group(1))
                    if dropped:
                        fired["clean"] += dropped
                        seen.add("clean")
                    continue
                fired[rule] += 1
                seen.add(rule)
                kinds[f"{rule}: {re.sub(chr(39) + '[^' + chr(39) + ']*' + chr(39), '…', message).split(' -> ')[0]}"] += 1
            for rule in sorted(seen):  # a set's order changes with the hash seed; the report's must not
                models[rule] += 1
        result[name] = {"models": len(paths), "fired": dict(fired), "in_models": dict(models),
                        "kinds": dict(kinds.most_common())}
    return result


# --- 3 and 4. decisions and errors ------------------------------------------------------------

def rendered(folder, mode, jobs):
    replay = ps.Replay(mode)
    out = {}
    for job in jobs:
        saved = json.loads((Path(folder) / "documents" / job["name"] / "process.json").read_text(encoding="utf-8"))
        out[job["name"]] = {((h[0].lower(), h[1], h[2]), (t[0].lower(), t[1], t[2]))
                            for h, t in ps.render(replay(job, saved))}
    return out


def gold_decisions(document):
    """[(mentions, conditions, branch heads)] of one document's gold decisions."""
    xor = [k for k in document["mentions"] if k[0] == "xor gateway"]
    parent = {k: k for k in xor}

    def find(k):
        while parent[k] != k:
            k = parent[k]
        return k

    for tag, h, t in document["relations"]:
        if tag == "same gateway" and h in parent and t in parent:
            parent[find(h)] = find(t)
    groups = defaultdict(set)
    for k in xor:
        groups[find(k)].add(k)
    flows = {(h, t) for tag, h, t in document["relations"] if tag == "flow"}
    out = []
    for members in sorted(groups.values(), key=lambda m: min(k[1] for k in m)):
        conditions = {t for h, t in flows if h in members and t[0] == "condition specification"}
        heads = {t for h, t in flows if h in members | conditions and t not in members | conditions}
        out.append((members, conditions, heads))
    return out


def decision_outcomes(gold, built):
    """Per document, a Counter of outcomes; and two examples of each outcome."""
    per_document, examples = {}, defaultdict(list)
    for d, document in gold.items():
        c = Counter()
        for members, conditions, heads in gold_decisions(document):
            own = conditions | {t for h, t in built[d] if h in members and t[0] == "condition specification"}
            got = {t for h, t in built[d] if h in members | own and t not in members | own}
            if got == heads:
                kind = "right: the same branch heads"
            elif len(got) <= 1 and len(heads) >= 2:
                kind = "not built: one way on or none"
            elif got < heads:
                kind = "a branch head missed"
            elif heads < got:
                kind = "an extra branch head"
            else:
                kind = "a wrong branch head"
            c[kind] += 1
            if len(examples[kind]) < 2:
                text = lambda k: document["text"][k[1]:k[2]]  # noqa: E731
                first = min(members, key=lambda k: k[1])
                examples[kind].append(f"{d}: '{text(first)}' gold {sorted(map(text, heads))}, "
                                      f"built {sorted(map(text, got))}")
        per_document[d] = c
    return per_document, dict(examples)


def share_right(per_document, documents):
    right = sum(per_document[d]["right: the same branch heads"] for d in documents)
    total = sum(sum(per_document[d].values()) for d in documents)
    return right / total if total else 0.0


def paired_share(a, b, documents):
    rng = random.Random(SEED)
    point = share_right(a, documents) - share_right(b, documents)
    draws = sorted(share_right(a, s) - share_right(b, s)
                   for s in ([rng.choice(documents) for _ in documents] for _ in range(RESAMPLES)))
    return {"difference": point, "ci95": [draws[int(0.025 * RESAMPLES)], draws[int(0.975 * RESAMPLES) - 1]]}


def errors(gold, built):
    missed, extra, examples_missed, examples_extra = Counter(), Counter(), defaultdict(list), defaultdict(list)
    for d, document in gold.items():
        flows = {(h, t) for tag, h, t in document["relations"] if tag == "flow"}
        used = {k for pair in built[d] for k in pair}
        text = lambda k: document["text"][k[1]:k[2]]  # noqa: E731
        for h, t in sorted(flows - built[d]):
            kind = ("backward in the text (cannot be built)" if t[1] < h[1] else
                    "an end the model does not use" if h not in used or t not in used else f"{h[0]} -> {t[0]}")
            missed[kind] += 1
            if len(examples_missed[kind]) < 2:
                examples_missed[kind].append(f"{d}: '{text(h)}' -> '{text(t)}'")
        for h, t in sorted(built[d] - flows):
            kind = f"{h[0]} -> {t[0]}"
            extra[kind] += 1
            if len(examples_extra[kind]) < 2:
                examples_extra[kind].append(f"{d}: '{text(h)}' -> '{text(t)}'")
    return {"missed": dict(missed.most_common()), "missed_examples": dict(examples_missed),
            "extra": dict(extra.most_common()), "extra_examples": dict(examples_extra)}


def lanes_without_recipients():
    from text2bpmn.lane_accuracy import score_arm
    from text2bpmn.pet_rules_eval import PET_DEFAULT, load_documents

    documents = {d["name"]: d for d in load_documents(PET_DEFAULT)}
    out = {}
    for label, (folder, arm) in LANE_ARMS.items():
        both = {}
        for key, exclude in (("all", False), ("without_recipients", True)):
            r = score_arm(Path(folder) / arm, documents, exclude)
            both[key] = {k: r[k] for k in ("activities_with_a_gold_performer", "recognised", "in_performer_lane")}
            both[key]["correct"] = sum(x["correct"] for x in r["rows"] if x["recognised"])
        out[label] = both
    return out


# --- the report ----------------------------------------------------------------------

def analyse():
    gold = ps.load_gold()
    jobs = json.loads(Path(ps.PET_JOBS).read_text(encoding="utf-8"))["jobs"]
    built = {label: rendered(folder, mode, jobs) for label, (folder, mode) in RUNS.items()}
    documents = sorted(gold)
    outcomes, examples = {}, {}
    for label, b in built.items():
        per_document, ex = decision_outcomes(gold, b)
        outcomes[label] = (per_document, ex)
    totals = {label: dict(sum(pd.values(), Counter())) for label, (pd, _) in outcomes.items()}
    differences = {f"{METHOD} − {other}": paired_share(outcomes[METHOD][0], outcomes[other][0], documents)
                   for other in RUNS if other != METHOD}
    return {"limits": limits(gold), "validation_rules": validation_rules(),
            "decisions": {"totals": totals, "share_right": {label: share_right(pd, documents)
                                                            for label, (pd, _) in outcomes.items()},
                          "examples": outcomes[METHOD][1], "differences": differences},
            "errors": errors(gold, built[METHOD]), "lanes_without_recipients": lanes_without_recipients()}


def markdown(r):
    lines = ["# The final method's release run: limits, the Validation Layer, decisions, errors", "",
             "Generated by `text2bpmn/checks/method_analysis.py` from `runs/final-3` (and `runs/final-2` for 1c). "
             "See the module's docstring for what each part counts.", "", "## 1. Limits", "",
             "| | PET | cases |", "|---|---|---|"]
    keys = list(dict.fromkeys([*r["limits"]["PET"], *r["limits"]["cases"]]))
    for k in keys:
        lines.append(f"| {k} | {r['limits']['PET'].get(k, '–')} | {r['limits']['cases'].get(k, '–')} |")
    lines += ["", "## 2. The Validation Layer (rules fired, and in how many models)", "",
              "| rule | PET | cases |", "|---|---|---|"]
    rules = list(dict.fromkeys([*r["validation_rules"]["PET"]["fired"], *r["validation_rules"]["cases"]["fired"]]))
    cell = lambda part, rule: (f"{r['validation_rules'][part]['fired'].get(rule, 0)} in "  # noqa: E731
                               f"{r['validation_rules'][part]['in_models'].get(rule, 0)} of "
                               f"{r['validation_rules'][part]['models']}")
    for rule in ["clean", "types", "metadata", "connect", *[x for x in rules if x not in
                                                            ("clean", "types", "metadata", "connect")]]:
        lines.append(f"| {rule} | {cell('PET', rule)} | {cell('cases', rule)} |")
    lines += ["", "By kind:", ""]
    for part in ("PET", "cases"):
        lines += [f"- {part}: " + "; ".join(f"{k} ({n})" for k, n in r["validation_rules"][part]["kinds"].items())]
    d = r["decisions"]
    outcomes = ["right: the same branch heads", "not built: one way on or none", "a wrong branch head",
                "an extra branch head", "a branch head missed"]
    lines += ["", "## 3. Decisions, one by one (PET's gold decisions, branch heads)", "",
              "| | " + " | ".join(outcomes) + " | share right |", "|---" * (len(outcomes) + 2) + "|"]
    for label, t in d["totals"].items():
        lines.append(f"| {label} | " + " | ".join(str(t.get(o, 0)) for o in outcomes) +
                     f" | {d['share_right'][label]:.3f} |")
    lines += ["", f"Paired bootstrap over documents ({RESAMPLES} resamples, seed {SEED}), share right:", ""]
    lines += [f"- {k}: {v['difference']:+.3f} [{v['ci95'][0]:+.3f}, {v['ci95'][1]:+.3f}]"
              for k, v in d["differences"].items()]
    lines += ["", "Examples, the method:", ""]
    for kind, ex in d["examples"].items():
        lines += [f"- {kind}: " + " | ".join(ex)]
    e = r["errors"]
    lines += ["", "## 4. The method's strict Flow errors", "",
              f"Missed gold flows: {sum(e['missed'].values())}.", "", "| kind | count | examples |", "|---|---|---|"]
    lines += [f"| {k} | {n} | {' ; '.join(e['missed_examples'][k])} |" for k, n in e["missed"].items()]
    lines += ["", f"Built flows PET does not have: {sum(e['extra'].values())}.", "",
              "| kind | count | examples |", "|---|---|---|"]
    lines += [f"| {k} | {n} | {' ; '.join(e['extra_examples'][k])} |" for k, n in e["extra"].items()]
    lines += ["", "## Lanes without the activities that also have an actor recipient", "",
              "| arm | all | without them |", "|---|---|---|"]
    for label, both in r["lanes_without_recipients"].items():
        a, w = both["all"], both["without_recipients"]
        lines.append(f"| {label} | {a['in_performer_lane']:.1%} ({a['correct']}/{a['recognised']}) | "
                     f"{w['in_performer_lane']:.1%} ({w['correct']}/{w['recognised']}) |")
    return "\n".join(lines) + "\n"


def main():
    result = analyse()
    OUT.with_suffix(".json").write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str),
                                        encoding="utf-8")
    text = markdown(result)
    OUT.with_suffix(".md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
