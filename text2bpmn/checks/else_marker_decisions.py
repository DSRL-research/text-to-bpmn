"""Table 9's decision-level score split by whether the decision has an explicit else-marker.

    python3 -m text2bpmn.checks.else_marker_decisions [--neuberger DIR]
        # -> runs/checks/final-3/open_analyses/else_marker_decisions.{md,json}

Same data and definitions as text2bpmn/checks/method_analysis.py, part 3 (Table 9):
PET's gold decisions are its XOR Gateway mentions grouped by its own `same
gateway` links (Neuberger et al.'s conversion, ER 2024, fetched by
text2bpmn/pet_strict.py --fetch); a decision is *right* when the model's branch
heads equal the gold ones; the model is read as the strict comparison writes it
(pet_strict.render of a replay that answers every question with the logged
answer and must rebuild the saved graph; no LLM is called). The three runs are
the release run's method (runs/final-3/pet_decisions), its no-LLM control
(runs/final-3/pet_no_and) and the textual order (runs/final-3/pet_no_llm).

**Else-marker.** A decision has one when the clause opened by any of its gold
XOR Gateway mentions starts with a marker. The clause is the document text
from the mention's first character up to the first `,` `.` `;` or `:` at or
after the mention's end (PET's texts are tokenised, so "If not , the ..."
gives the clause "If not"). The markers, matched case-insensitively at the
clause's start, optionally after "or", "and" or "but" (MARKERS below):

- otherwise; else (so also "or else");
- in all other cases / in any other case / in every other case / in (the)
  other case(s);
- if not, if not so; if this / that / it / so is not (the case), if this /
  that / it is n't -- these only when nothing else follows in the clause, so
  that "If not already registered" or "If it is not available" (a negated
  condition with content of its own) is no marker.

As a check, the pipeline's own rule is also given: a gold XOR Gateway mention
whose whole text is an else-marker (guardrails.is_else_marker, the rule by which
the pipeline makes such a mention stand for the decision before it).

**Bootstrap.** For each group, the share right of two runs is compared with a
paired bootstrap over the documents that have at least one decision in the
group (1000 resamples, seed 0, percentile interval as method_analysis), so a
resample never has an empty group.
"""
import argparse
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

from text2bpmn import pet_strict as ps
from text2bpmn.checks import method_analysis as ma
from text2bpmn.guardrails import is_else_marker

OUT = Path("runs/checks/final-3/open_analyses/else_marker_decisions")
RUNS = {"the method (idea 3)": ("runs/final-3/pet_decisions", "decisions4"),
        "the method's no-LLM control": ("runs/final-3/pet_no_and", "decisions4"),
        "text order, no LLM": ("runs/final-3/pet_no_llm", "pairs")}
METHOD = "the method (idea 3)"
OTHERS = ["the method's no-LLM control", "text order, no LLM"]
RESAMPLES, SEED = 1000, 0
OUTCOMES = ["right: the same branch heads", "not built: one way on or none", "a wrong branch head",
            "an extra branch head", "a branch head missed"]
RIGHT = OUTCOMES[0]

CLAUSE_END = re.compile(r"[,.;:]")
LEAD = r"^\s*(?:(?:or|and|but)\s+)?"
END = r"\s*$"
MARKERS = [  # (name, pattern on the clause)
    ("otherwise", LEAD + r"otherwise\b"),
    ("else", LEAD + r"else\b"),
    ("in all/any/every/the other case(s)", LEAD + r"in\s+(?:all\s+|any\s+|every\s+|the\s+)?other\s+cases?\b"),
    ("if not (so)", LEAD + r"if\s+not(?:\s+so)?" + END),
    ("if this/that/it/so is not (the case)",
     LEAD + r"if\s+(?:this|that|it|so)\s+is\s+(?:not|n't)(?:\s+the\s+case)?" + END),
]


def clause(text, mention):
    """The clause a mention opens: from its start to the first , . ; or : at or after its end."""
    stop = CLAUSE_END.search(text, mention[2])
    return text[mention[1]:stop.start() if stop else len(text)].strip()


def marker_of(text):
    return next((name for name, pattern in MARKERS if re.match(pattern, text, re.I)), None)


def classify(members, conditions, heads, built):
    """method_analysis.decision_outcomes's outcome for one gold decision."""
    own = conditions | {t for h, t in built if h in members and t[0] == "condition specification"}
    got = {t for h, t in built if h in members | own and t not in members | own}
    if got == heads:
        return RIGHT, got
    if len(got) <= 1 and len(heads) >= 2:
        return "not built: one way on or none", got
    if got < heads:
        return "a branch head missed", got
    if heads < got:
        return "an extra branch head", got
    return "a wrong branch head", got


def share(rows, run, documents):
    picked = [r for d in documents for r in rows[d]]
    return sum(r["outcomes"][run] == RIGHT for r in picked) / len(picked) if picked else float("nan")


def paired(rows, a, b, documents):
    rng = random.Random(SEED)
    point = share(rows, a, documents) - share(rows, b, documents)
    draws = sorted(share(rows, a, s) - share(rows, b, s)
                   for s in ([rng.choice(documents) for _ in documents] for _ in range(RESAMPLES)))
    return {"difference": point, "ci95": [draws[int(0.025 * RESAMPLES)], draws[int(0.975 * RESAMPLES) - 1]]}


def interaction(by_doc_with, by_doc_without, a, b, documents):
    """(a - b with a marker) - (a - b without), resampling all documents."""
    rng = random.Random(SEED)

    def value(sample):
        return ((share(by_doc_with, a, sample) - share(by_doc_with, b, sample))
                - (share(by_doc_without, a, sample) - share(by_doc_without, b, sample)))

    point = value(documents)
    draws = sorted(v for v in (value([rng.choice(documents) for _ in documents]) for _ in range(RESAMPLES))
                   if v == v)  # a resample with an empty group gives nan and is skipped
    return {"difference": point, "ci95": [draws[int(0.025 * len(draws))], draws[int(0.975 * len(draws)) - 1]],
            "resamples_used": len(draws)}


def analyse():
    gold = ps.load_gold()
    jobs = json.loads(Path(ps.PET_JOBS).read_text(encoding="utf-8"))["jobs"]
    built = {label: ma.rendered(folder, mode, jobs) for label, (folder, mode) in RUNS.items()}
    # the totals, as method_analysis computes them (part 3), to check the split against
    per_document = {label: ma.decision_outcomes(gold, b)[0] for label, b in built.items()}
    q15 = {label: dict(sum(pd.values(), Counter())) for label, pd in per_document.items()}
    q15_differences = {f"{METHOD} − {other}": ma.paired_share(per_document[METHOD], per_document[other], sorted(gold))
                       for other in OTHERS}
    rows = defaultdict(list)
    for d, document in sorted(gold.items()):
        text = document["text"]
        for members, conditions, heads in ma.gold_decisions(document):
            clauses = [clause(text, k) for k in sorted(members, key=lambda k: k[1])]
            found = [m for m in map(marker_of, clauses) if m]
            outcomes, got = {}, {}
            for label in RUNS:
                outcomes[label], g = classify(members, conditions, heads, built[label][d])
                got[label] = sorted(text[k[1]:k[2]] for k in g)
            rows[d].append({
                "document": d,
                "mentions": [text[k[1]:k[2]] for k in sorted(members, key=lambda k: k[1])],
                "clauses": clauses, "marker": found[0] if found else None,
                "pipeline_else_marker": any(is_else_marker(text[k[1]:k[2]]) for k in members),
                "gold_heads": sorted(text[k[1]:k[2]] for k in heads), "built_heads": got, "outcomes": outcomes})
    flat = [r for d in rows for r in rows[d]]
    for label in RUNS:  # the split must add up to those totals
        assert dict(Counter(r["outcomes"][label] for r in flat)) == q15[label], label

    result = {"q15_totals": q15, "q15_differences": q15_differences, "groups": {},
              "marker_list": [n for n, _ in MARKERS],
              "resamples": RESAMPLES, "seed": SEED}
    for scheme, has in (("text markers (primary)", lambda r: r["marker"] is not None),
                        ("pipeline rule (is_else_marker on the gold mention)", lambda r: r["pipeline_else_marker"])):
        split = {}
        for name, keep in (("with an else-marker", has), ("without", lambda r, has=has: not has(r))):
            by_doc = {d: [r for r in rows[d] if keep(r)] for d in rows}
            documents = sorted(d for d, rs in by_doc.items() if rs)
            n = sum(len(by_doc[d]) for d in documents)
            split[name] = {
                "decisions": n, "documents": len(documents),
                "right": {label: sum(r["outcomes"][label] == RIGHT for d in documents for r in by_doc[d])
                          for label in RUNS},
                "share_right": {label: share(by_doc, label, documents) for label in RUNS},
                "outcomes": {label: dict(Counter(r["outcomes"][label] for d in documents for r in by_doc[d]))
                             for label in RUNS},
                "differences": {f"{METHOD} − {other}": paired(by_doc, METHOD, other, documents) for other in OTHERS},
                "decisions_listed": [r for d in documents for r in by_doc[d]] if name.startswith("with") else None}
        with_, without = ({d: [r for r in rows[d] if keep(r)] for d in rows}
                          for keep in (has, lambda r, has=has: not has(r)))
        split["interaction"] = {f"({METHOD} − {other}) with − without": interaction(with_, without, METHOD, other,
                                                                                     sorted(rows))
                                for other in OTHERS}
        result["groups"][scheme] = split
    return result


def markdown(r):
    lines = ["# Q15's decision-level score, split by an explicit else-marker", "",
             "Generated by `text2bpmn/checks/else_marker_decisions.py` from the release run "
             "(`runs/final-3/pet_decisions`, `pet_no_and`, `pet_no_llm`) and PET's gold decisions as Q15 "
             "(`text2bpmn/checks/method_analysis.py`, part 3). See the module docstring for the marker list "
             "and how it is matched.", "",
             f"Q15 totals reproduced: " + "; ".join(f"{k} {v.get(RIGHT, 0)}/{sum(v.values())} right"
                                                   for k, v in r["q15_totals"].items()) + "; all 75 decisions, "
             "paired bootstrap over the 45 documents as Q15: " +
             "; ".join(f"{k} {v['difference']:+.3f} [{v['ci95'][0]:+.3f}, {v['ci95'][1]:+.3f}]"
                       for k, v in r["q15_differences"].items()), ""]
    for scheme, split in r["groups"].items():
        lines += [f"## {scheme}", "", "| group | decisions (documents) | " + " | ".join(RUNS) + " |",
                  "|---|---|" + "---|" * len(RUNS)]
        for name in ("with an else-marker", "without"):
            g = split[name]
            lines.append(f"| {name} | {g['decisions']} ({g['documents']}) | " +
                         " | ".join(f"{g['share_right'][k]:.3f} ({g['right'][k]}/{g['decisions']})" for k in RUNS)
                         + " |")
        lines += ["", f"Paired bootstrap over the group's documents ({r['resamples']} resamples, seed {r['seed']}), "
                  "share right:", ""]
        for name in ("with an else-marker", "without"):
            for k, v in split[name]["differences"].items():
                lines.append(f"- {name}: {k}: {v['difference']:+.3f} [{v['ci95'][0]:+.3f}, {v['ci95'][1]:+.3f}]")
        for k, v in split["interaction"].items():
            lines.append(f"- {k} (all 45 documents resampled, {v['resamples_used']} resamples with both groups): "
                         f"{v['difference']:+.3f} [{v['ci95'][0]:+.3f}, {v['ci95'][1]:+.3f}]")
        lines += ["", "Outcomes:", ""]
        for name in ("with an else-marker", "without"):
            for k in RUNS:
                o = split[name]["outcomes"][k]
                lines.append(f"- {name}, {k}: " + ", ".join(f"{x} {o[x]}" for x in OUTCOMES if x in o))
        lines += ["", "Decisions with an else-marker:", "",
                  "| document | mentions | marker | clause | gold heads | " + " | ".join(RUNS) + " |",
                  "|---|---|---|---|---|" + "---|" * len(RUNS)]
        for row in split["with an else-marker"]["decisions_listed"]:
            marked = [c for c in row["clauses"] if marker_of(c)] or ["(pipeline rule)"]
            lines.append(f"| {row['document']} | {' / '.join(row['mentions'])} | {row['marker'] or '-'} | "
                         f"{marked[0]} | {', '.join(row['gold_heads'])} | " +
                         " | ".join(row["outcomes"][k].split(":")[0] for k in RUNS) + " |")
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--neuberger", default=str(ps.FETCHED),
                    help="folder of the files pet_strict.py --fetch downloaded (checked against their sha256)")
    args = ap.parse_args()
    ps.FETCHED = Path(args.neuberger)
    result = analyse()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.with_suffix(".json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    text = markdown(result)
    OUT.with_suffix(".md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
