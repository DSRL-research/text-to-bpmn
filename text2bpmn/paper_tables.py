"""The revised paper's tables, each rebuilt by one command from the committed runs and checked against the draft.

    python3 -m text2bpmn.paper_tables 7             # Table 7 -> runs/checks/final-3/tables/table7.{md,json}
    python3 -m text2bpmn.paper_tables all           # Tables 2-10, and runs/checks/final-3/tables/summary.md
    python3 -m text2bpmn.paper_tables 8 --woflan    # Table 8 with WOFLAN run again on all 180 PET models (minutes)
    python3 -m text2bpmn.paper_tables --list        # each table, its draft and its inputs

Each table is computed from saved outputs with the scorers the runs used: the
release runs (runs/final-3, runs/gliner-3; tag revision-final-3), idea 1c's
release run (runs/final-2), the method as submitted (runs/final; tag
revision-final) and its rerun that kept its answers and graphs
(runs/ideas/idea1b/pet_pairs). No LLM is asked and no recogniser is run; where
a measure needs the graph a run built from what it was told, the run is
replayed from its logged answers and the replay must rebuild the saved graph
(text2bpmn/pet_strict.py). Each table is laid out as its draft prints it, and
every number in it, with the numbers the draft's text reports beside it, is
compared with the draft. A difference is listed; those understood are
explained in KNOWN, and the command exits 1 on any other.

The numbering is the drafts' of November 2026 (DRAFTS). Table 1 compares the
literature and holds no measurement; no draft has a Table 11 or 12.

Two inputs are not in git: PET's gold relations as Neuberger et al. convert
them, for Tables 5, 8 and 9 (python3 -m text2bpmn.pet_strict --fetch, once);
and the recognisers' weights, whose parameter counts (Table 4) are read from the
record text2bpmn/checks/parameter_counts.py made from them
(runs/checks/final-3/tables/parameter_counts.json).
"""
import argparse
import hashlib
import json
import re
import tempfile
from collections import Counter
from functools import lru_cache
from pathlib import Path

from text2bpmn.checks.common import header, provenance, write

OUT = Path("runs/checks/final-3/tables")
PET = "pet_data/PETv1.1-relations.json"

# the drafts the numbers are taken from (file names in the authors' folder of drafts)
DRAFTS = {
    "main": "bpmn_springer_format_2_reviewing_1.pdf (2026-11-12; its .docx, 2026-11-12, has the same tables)",
    "s43": "s43.pdf (2026-11-13), Section 4.3",
    "s44": "s44.pdf (2026-11-13), Section 4.4",
    "s45": "s45-2.pdf (2026-11-17; s45-3.pdf is the same file), Section 4.5",
    "s46": "s46-2.pdf (2026-11-18), Section 4.6, version 3: the loan rows against the textbook reference (D12)",
    "changes": "changes_after_final_runs.pdf (2026-11-10), Part B4 (Section 4.2's text)",
}
TITLES = {
    1: "Comparison of approaches to process extraction from text",
    2: "Entity distribution (PET v1.1)",
    3: "Strict F1 per mention type on the 42 test sentences",
    4: "Entity recognition configurations on the 42 test sentences",
    5: "Flow relations on PET under the strict protocol, with gold entities",
    6: "The pairwise classifier on the 302 constructed pairs",
    7: "Lane assignment on PET",
    8: "Relation stages on the 45 documents of PET, with gold mentions",
    9: "Branch heads of PET's 75 decisions",
    10: "The reference processes",
}
WHERE = {1: "main", 2: "main", 3: "main", 4: "main", 5: "s43", 6: "s43", 7: "s44", 8: "s45", 9: "s45", 10: "s46"}


# --- what the drafts print ------------------------------------------------------------------
# Transcribed from the drafts; a range "a–b" in the text is written "[a, b]", minus signs as "-".
# The first cell of a row is its label and is not compared.

PAPER = {
    2: {"rows": [["Activity", "502", "29.9"], ["Activity Data", "459", "27.3"], ["Actor", "449", "26.7"],
                 ["XOR Gateway", "117", "7.0"], ["Condition Specification", "80", "4.8"],
                 ["Further Specification", "64", "3.8"], ["AND Gateway", "8", "0.5"], ["Total", "1679", "100.0"]],
        "text": {"sentences": ("417", "main"), "relations": ("1832", "main"), "Flow relations": ("675", "main")}},
    3: {"rows": [["Activity", "62", "0.672", "0.872"], ["Activity Data", "59", "0.711", "0.775"],
                 ["Actor", "49", "0.874", "0.960"], ["Condition Specification", "10", "0.706", "0.750"],
                 ["Further Specification", "6", "0.000", "0.000"], ["XOR Gateway", "11", "0.900", "0.900"],
                 ["AND Gateway", "0", "-", "-"]]},
    4: {"rows": [["BERT", "fine-tuned, 315 sentences", "107.7M", "0.715 [0.640, 0.792]", "0.787 [0.714, 0.856]"],
                 ["GLiNER, small v2.1", "fine-tuned, 315 sentences", "152.6M", "0.849 [0.786, 0.906]",
                  "0.870 [0.816, 0.920]"],
                 ["GLiNER, medium v2.1", "fine-tuned, 315 sentences", "195.2M", "0.843 [0.787, 0.894]",
                  "0.880 [0.833, 0.923]"],
                 ["GLiNER, focal loss", "fine-tuned, 315 sentences", "152.6M", "0.861 [0.802, 0.913]",
                  "0.877 [0.830, 0.922]"],
                 ["GLiNER, hard negatives", "fine-tuned, 315 sentences", "152.6M", "0.802 [0.745, 0.856]",
                  "0.833 [0.780, 0.881]"],
                 ["GLiNER medium v2.1, zero-shot", "zero-shot", "195.2M", "0.110 [0.059, 0.161]", "0.186"],
                 ["GLiNER 2.5 base v1, zero-shot", "zero-shot", "193.6M", "0.194 [0.137, 0.253]", "0.417"]],
        "text": {"GLiNER small v2.1 - BERT, strict": ("+0.134 [0.085, 0.184]", "changes"),
                 "GLiNER small v2.1 - BERT, relaxed": ("+0.083 [0.038, 0.127]", "changes")}},
    5: {"rows": [["RuleRelEx [23]", "0.737", "0.796", "0.765", "0.762"],
                 ["BoostRelEx [23]", "0.881", "0.697", "0.777", "0.775"],
                 ["GPT-4o [Springer], none", "0.795", "0.723", "0.757", "0.755"],
                 ["GPT-4o [Springer], three documents", "0.854", "0.800", "0.826", "0.825"],
                 ["GPT-4-turbo [Springer], three documents", "0.862", "0.815", "0.838", "0.836"],
                 ["Llama 3 70B [Springer], three documents", "0.849", "0.788", "0.817", "0.814"],
                 ["Claude 3 Opus [Springer], three documents", "0.893", "0.859", "0.875", "0.871"],
                 ["Textual order (no LLM)", "0.797", "0.757", "0.777", "0.776"],
                 ["This method", "0.804", "0.807", "0.805", "0.805"]],
        "text": {"method - RuleRelEx": ("+0.043 [+0.016, +0.073]", "s43"),
                 "method - textual order": ("+0.028 [+0.008, +0.054]", "s43"),
                 "method - GPT-4o, none": ("+0.049 [-0.001, +0.104]", "s43"),
                 "method - GPT-4o, three": ("-0.020 [-0.064, +0.020]", "s43"),
                 "method - Claude 3 Opus, three": ("-0.066 [-0.110, -0.026]", "s43"),
                 "method, rule 1 alone (pooled)": ("0.610", "s43"),
                 "gold mentions (PET v1.1), of them exactly Neuberger et al.'s": ("1,679, 1,654", "s43"),
                 "the others: actors, activity data, activities": ("12, 12, 1", "s43"),
                 "of the others, in a Flow relation (PET v1.1 or theirs)": ("0", "s43")}},
    6: {"rows": [["CONDITION DEF", "48", "1.000", "1.000", "1.000", "48", "0", "0", "0", "0"],
                 ["TRUE BRANCH", "73", "0.785", "1.000", "0.880", "0", "73", "0", "0", "0"],
                 ["FALSE BRANCH", "69", "1.000", "0.710", "0.831", "0", "20", "49", "0", "0"],
                 ["SEQUENCE", "66", "1.000", "0.939", "0.969", "0", "0", "0", "62", "4"],
                 ["PARALLEL", "46", "0.920", "1.000", "0.958", "0", "0", "0", "0", "46"]],
        "text": {"accuracy": ("0.921 (278/302)", "s43"), "macro F1": ("0.927", "s43"),
                 "weighted F1": ("0.919", "s43"),
                 "FALSE BRANCH labelled TRUE BRANCH, of them without an else-marker": ("20, 20 of 23", "s43"),
                 "SEQUENCE labelled PARALLEL": ("4", "s43"),
                 "correct under the syntactic scheme": ("295 of 302 (97.7%)", "s43")}},
    7: {"rows": [["Of the recognised activities", "83.3% (315/378)", "76.9% (293/381)", "82.5% (306/371)"],
                 ["Of all 396 gold activities", "79.5%", "74.0%", "77.3%"],
                 ["With a pronoun as performer", "40.0% (22/55)", "0.0% (0/56)", "41.1% (23/56)"],
                 ["Without the 122 with a recipient", "82.6% (214/259)", "77.9% (204/262)", "81.7% (205/251)"],
                 ["Tasks in Main Process", "5.1%", "5.1%", "4.3%"]],
        "text": {"gold activities with a performer, documents": ("396, 43", "s44"),
                 "of them with an actor recipient": ("122", "s44"),
                 "with - without FastCoref, of recognised": ("+0.064 [+0.023, +0.114]", "s44"),
                 "with - without FastCoref, of all gold": ("+0.056 [+0.017, +0.104]", "s44"),
                 "GLiNER - BERT, of recognised": ("-0.009 [-0.050, +0.026]", "s44"),
                 "GLiNER - BERT, of all gold": ("-0.023 [-0.068, +0.015]", "s44")}},
    8: {"rows": [["Textual order (no LLM)", "0.762", "0.787", "0.776", "0 of 10", "0", "45/45"],
                 ["Pairwise classification", "0.726", "0.741", "0.702", "3 of 10 (+44)", "1,300", "40/45"],
                 ["Method without concurrency question", "0.773", "0.818", "0.784", "0 of 10", "78", "45/45"],
                 ["This method", "0.770", "0.828", "0.805", "5 of 10", "84", "45/45"]],
        "text": {"pairwise - textual order, three shapes": ("-0.036 [-0.063, -0.003]", "s45"),
                 "pairwise - textual order, all flows": ("-0.046 [-0.070, -0.022]", "s45"),
                 "pairwise, inserted gateways collapsed (strict, pooled)": ("0.675", "s45"),
                 "method - pairwise, three shapes": ("+0.043 [+0.015, +0.068]", "s45"),
                 "method - pairwise, all flows": ("+0.087 [+0.058, +0.116]", "s45"),
                 "method - pairwise, strict": ("+0.103 [+0.072, +0.137]", "s45"),
                 "method - textual order, three shapes": ("+0.008 [-0.013, +0.029]", "s45"),
                 "method - textual order, all flows": ("+0.041 [+0.017, +0.066]", "s45"),
                 "method - textual order, strict": ("+0.028 [+0.008, +0.054]", "s45"),
                 "method - method without concurrency question, strict": ("+0.020 [+0.004, +0.042]", "s45"),
                 "WOFLAN-rejected pairwise models that contain a parallel gateway": ("5 of 5", "s45"),
                 "the method's calls: decision, concurrency questions": ("78, 6", "s45"),
                 "decision answers with no branch (text order kept)": ("5", "s45"),
                 "PET's concurrency cues, of them asked about": ("8, 6", "s45"),
                 "the method's PET experiment, minutes (seconds)": ("12 (716)", "s45")}},
    9: {"rows": [["Textual order (no LLM)", "32", "38", "2", "0", "3", "0.427"],
                 ["Method without the LLM", "24", "46", "1", "0", "4", "0.320"],
                 ["This method", "37", "17", "15", "6", "0", "0.493"]],
        "text": {"decisions; with two, three or more, one branch head": ("75; 57, 11, 7", "s45"),
                 "method - method without the LLM": ("+0.173 [+0.070, +0.293]", "s45"),
                 "method - textual order": ("+0.067 [-0.026, +0.169]", "s45")}},
    10: {"rows": [["Loan, BERT, method", ".615 (4/2/3)", ".400 (1/1/2)", ".182 (1/4/5)", "23.49", "20 / 26", "0.511",
                   "0.489", "0.059"],
                  ["Loan, BERT, no LLM", ".615", ".000 (0/0/3)", ".182 (1/4/5)", "24.49", "15 / 26", "0.597", "0.403",
                   "0.059"],
                  ["Loan, GLiNER, method", ".500 (3/2/4)", ".400 (1/1/2)", ".400 (2/2/4)", "21.25", "18 / 26", "0.483",
                   "0.517", "0.133"],
                  ["Loan, GLiNER, no LLM", ".500", ".000", ".200 (1/3/5)", "27.25", "13 / 26", "0.699", "0.301",
                   "0.062"],
                  ["Goods dispatch, BERT, method", ".588 (5/5/2)", ".667 (4/2/2)", ".200 (2/10/6)", "40.91", "38 / 32",
                   "0.584", "0.416", "0.070"],
                  ["Goods dispatch, BERT, no LLM", ".588", ".000 (0/0/6)", ".118 (1/8/7)", "37.91", "23 / 32", "0.689",
                   "0.311", "0.025"],
                  ["Goods dispatch, GLiNER, method", ".750 (6/3/1)", ".500 (3/3/3)", ".118 (1/8/7)", "39.52", "36 / 32",
                   "0.581", "0.419", "0.024"],
                  ["Goods dispatch, GLiNER, no LLM", ".750", ".000", ".125 (1/7/7)", "33.52", "21 / 32", "0.632",
                   "0.368", "0.026"],
                  ["Healthcare, BERT, method", ".618 (17/15/6)", ".667 (6/0/6)", ".032 (1/34/27)", "114.12", "82 / 85",
                   "0.683", "0.317", "0.013"],
                  ["Healthcare, BERT, no LLM", ".618", ".000 (0/0/12)", ".034 (1/30/27)", "108.12", "67 / 85", "0.711",
                   "0.289", "0.014"],
                  ["Healthcare, GLiNER, method", ".627 (16/12/7)", ".667 (6/0/6)", ".172 (5/25/23)", "94.53", "75 / 85",
                   "0.591", "0.409", "0.074"],
                  ["Healthcare, GLiNER, no LLM", ".627", ".000", ".182 (5/22/23)", "95.53", "59 / 85", "0.663",
                   "0.337", "0.078"]],
         "text": {"task F1 with BERT, lowest and highest": ("59% and 62%", "s46"),
                  "gateways of the three references found with BERT and the LLM, of all; wrong": ("11 of 21; 3", "s46"),
                  "flows matching the references, BERT, with / without the LLM": ("4 / 3", "s46"),
                  "GED with / without the LLM, BERT: loan; goods dispatch; healthcare":
                      ("23.49 / 24.49; 40.91 / 37.91; 114.12 / 108.12", "s46"),
                  "flows the references do not have, BERT, with / without the LLM: goods dispatch; healthcare":
                      ("10 / 8; 34 / 30", "s46"),
                  "GED over the larger graph, BERT, with the LLM against without: loan, goods dispatch, healthcare":
                      ("lower, lower, higher", "s46"),
                  "footprint similarity, lowest to highest": ("0.01 to 0.13", "s46"),
                  "GLiNER against BERT, with the LLM": (
                      "tasks better on goods dispatch, healthcare, worse on loan; flows better on loan, healthcare; "
                      "GED lower on loan, goods dispatch, healthcare; more gateways found with BERT on goods dispatch",
                      "s46")}},
}

# differences from the draft that are understood: (table, row or text label, column) -> why
KNOWN = {
    (7, "Tasks in Main Process", "BERT, without"):
        "26 of 515 tasks = 5.05%, 5.0% to one place; lane_scores.json stores the share rounded to four places "
        "(0.0505), which prints as 5.1%",
    (7, "Tasks in Main Process", "GLiNER, with FastCoref"):
        "22 of 518 tasks = 4.25%, 4.2% to one place; lane_scores.json stores 0.0425, which the draft rounded up to "
        "4.3%",
    (8, "This method", "Parallel pairs"):
        "the draft's own rule puts the pairs built that PET does not annotate in brackets, as for pairwise "
        "classification; the method builds one (doc-3.5: one line of work split in two, which the draft's text "
        "describes)",
    (8, "pairwise, inserted gateways collapsed (strict, pooled)", "text"):
        "0.675 is the fold average; pooled, as Table 8's strict column, it is 0.676 "
        "(text2bpmn/results/pet_strict_flow.md)",
}


# --- formatting and comparison ----------------------------------------------------------------

NUMBER = re.compile(r"[-+]?(?:\d[\d,]*(?:\.\d+)?|\.\d+)")


def numbers(cell):
    return [float(t.replace(",", "")) for t in NUMBER.findall(str(cell).replace("−", "-"))]


def same(printed, ours):
    p, o = numbers(printed), numbers(ours)
    return p == o if p or o else str(printed).strip() == str(ours).strip()


def f3(x):
    return f"{x:.3f}"


def bare(x):
    """0.769 -> .769, as Table 10 prints F1."""
    return f"{x:.3f}"[1:] if 0 <= x < 1 else f"{x:.3f}"


def pct(n, d):
    return f"{100 * n / d:.1f}%"


def interval(d, signed=True):
    s = "+" if signed else ""
    lo, hi = d["ci95"] if "ci95" in d else (d["ci95_low"], d["ci95_high"])
    return f"{d['difference']:+.3f} [{lo:{s}.3f}, {hi:{s}.3f}]"


def compare_with_draft(number, table):
    """[(row, column, printed, ours, known reason or None)] where the numbers differ."""
    paper, out = PAPER.get(number, {}), []
    printed_rows, ours = paper.get("rows", []), table["rows"]
    if len(printed_rows) != len(ours):
        out.append(("rows", "count", str(len(printed_rows)), str(len(ours)), None))
    for printed, row in zip(printed_rows, ours):
        for column, a, b in zip(table["columns"][1:], printed[1:], row[1:]):
            if not same(a, b):
                out.append((row[0], column, a, b, KNOWN.get((number, row[0], column))))
    for label, (printed, _) in paper.get("text", {}).items():
        ours_value = table["text"].get(label)
        if ours_value is None or not same(printed, ours_value):
            out.append((label, "text", printed, ours_value, KNOWN.get((number, label, "text"))))
    return out


# --- shared inputs --------------------------------------------------------------------------------

@lru_cache(maxsize=None)
def _ner():
    from text2bpmn.ner_comparison import score_all
    spec = json.loads(Path("text2bpmn/baselines/comparison_spec_315.json").read_text(encoding="utf-8"))
    return {r["model"]: r for r in score_all(spec, "pet_test.json")}


@lru_cache(maxsize=None)
def _strict():
    from text2bpmn import pet_strict
    return pet_strict.compare()


@lru_cache(maxsize=None)
def _pet_documents():
    from text2bpmn.pet_rules_eval import load_documents
    return {d["name"]: d for d in load_documents(PET)}


def _blob_id(data):
    """git's blob id of these bytes (what `git hash-object` prints), without git."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


# --- Table 2: PET's mentions --------------------------------------------------------------------

MENTION_TYPES = ("Activity", "Activity Data", "Actor", "XOR Gateway", "Condition Specification",
                 "Further Specification", "AND Gateway")


def table2(**_):
    raw = json.loads(Path(PET).read_text(encoding="utf-8"))
    mentions = Counter(s["entity_group"] for d in _pet_documents().values() for s in d["spans"])
    total = sum(mentions[t] for t in MENTION_TYPES)
    relations = Counter(r["relation-type"] for d in raw for r in d["relations"])
    rows = [[t, str(mentions[t]), f"{100 * mentions[t] / total:.1f}"] for t in MENTION_TYPES]
    rows.append(["Total", str(total), "100.0"])
    return {"columns": ["Entity type", "Count", "%"], "rows": rows,
            "text": {"sentences": str(sum(len(set(d["sentence-IDs"])) for d in raw)),
                     "relations": str(sum(relations.values())), "Flow relations": str(relations["flow"])},
            "checks": {"every mention is of one of the seven types": set(mentions) <= set(MENTION_TYPES)},
            "inputs": [PET], "command": "python3 -m text2bpmn.paper_tables 2"}


# --- Tables 3 and 4: entity recognition ------------------------------------------------------------

BERT_NER = "BERT 315, selected on dev (fine-tuned)"
GLINER_A = "GLiNER small v2.1 fine-tuned (315)"
NER_TYPES = ("Activity", "Activity Data", "Actor", "Condition Specification", "Further Specification",
             "XOR Gateway", "AND Gateway")


def table3(**_):
    results = _ner()
    bert, gliner = results[BERT_NER], results[GLINER_A]
    rows = []
    for t in NER_TYPES:
        support = bert["strict"]["per_label"][t]["support"]
        cell = lambda r: "-" if support == 0 else f3(r["strict"]["per_label"][t]["f1"])  # noqa: E731
        rows.append([t, str(support), cell(bert), cell(gliner)])
    return {"columns": ["Mention type", "Support", "BERT", "GLiNER small v2.1"], "rows": rows, "text": {},
            "inputs": ["text2bpmn/baselines/comparison_spec_315.json", "text2bpmn/baselines/test_bert_315_dev60.json",
                       "text2bpmn/baselines/TEST_ft_A-small-v2.1-315.json", "pet_test.json"],
            "command": "python3 -m text2bpmn.paper_tables 3"}


# (row, setting, parameter record row, ner_comparison model, relaxed interval printed)
CONFIGURATIONS = [
    ("BERT", "fine-tuned, 315 sentences", "BERT, fine-tuned", BERT_NER, True),
    ("GLiNER, small v2.1", "fine-tuned, 315 sentences", "GLiNER small v2.1, fine-tuned", GLINER_A, True),
    ("GLiNER, medium v2.1", "fine-tuned, 315 sentences", "GLiNER medium v2.1, fine-tuned",
     "GLiNER medium v2.1 fine-tuned (315)", True),
    ("GLiNER, focal loss", "fine-tuned, 315 sentences", "GLiNER, focal loss",
     "GLiNER small v2.1 fine-tuned, focal loss (315)", True),
    ("GLiNER, hard negatives", "fine-tuned, 315 sentences", "GLiNER, hard negatives",
     "GLiNER small v2.1 fine-tuned, hard negatives (315)", True),
    ("GLiNER medium v2.1, zero-shot", "zero-shot", "GLiNER medium v2.1, zero-shot", "GLiNER medium v2.1 (zero-shot)",
     False),
    ("GLiNER 2.5 base v1, zero-shot", "zero-shot", "GLiNER2.5 base v1, zero-shot", "GLiNER2.5 base v1 (zero-shot)",
     False),
]
PARAMETERS = OUT / "parameter_counts.json"


def _micro(result, criterion, with_interval=True):
    r = result[criterion]
    b = r["bootstrap_micro_f1"]
    return f"{r['micro']['f1']:.3f} [{b['ci95_low']:.3f}, {b['ci95_high']:.3f}]" if with_interval \
        else f"{r['micro']['f1']:.3f}"


def table4(**_):
    from text2bpmn.eval_ner import bootstrap_difference, load_pet, load_predictions
    from text2bpmn.ner_comparison import PET_SCOPE

    results = _ner()
    counted = json.loads(PARAMETERS.read_text(encoding="utf-8"))["models"]
    rows = [[row, setting, f"{counted[record]['millions']}M", _micro(results[model], "strict"),
             _micro(results[model], "relaxed", relaxed)]
            for row, setting, record, model, relaxed in CONFIGURATIONS]
    # the paired difference of Section 4.2's text, as text2bpmn/baselines/paired_bootstrap_315.py computes it
    gold = load_pet("pet_test.json")
    thresholds = json.loads(Path("text2bpmn/baselines/chosen_thresholds_315.json").read_text(encoding="utf-8"))

    def documents(spans, threshold):
        return [(sentence[1], predicted) for sentence, predicted in
                zip(gold, load_predictions(spans, len(gold), threshold))]

    a = documents("text2bpmn/baselines/TEST_ft_A-small-v2.1-315.json", thresholds["A-small-v2.1-315"]["threshold"])
    b = documents("text2bpmn/baselines/test_bert_315_dev60.json", None)
    text = {}
    for criterion in ("strict", "relaxed"):
        d = bootstrap_difference(a, b, criterion, scope=PET_SCOPE, resamples=1000, seed=0)
        text[f"GLiNER small v2.1 - BERT, {criterion}"] = interval(d)
    return {"columns": ["Configuration", "Setting", "Params", "Strict F1", "Relaxed F1 (IoU >= 0.5)"], "rows": rows,
            "text": text,
            "checks": {"parameter counts: the record's weights, each with its SHA-256":
                       {r: counted[r]["sha256"][:16] for _, _, r, _, _ in CONFIGURATIONS}},
            "inputs": ["text2bpmn/baselines/comparison_spec_315.json and the spans it lists", str(PARAMETERS)],
            "command": "python3 -m text2bpmn.paper_tables 4"}


# --- Table 5: the strict comparison -----------------------------------------------------------------

STRICT_ROWS = [("RuleRelEx [23]", "RuleRelEx (Bellan et al.'s rules)"), ("BoostRelEx [23]", "BoostRelEx"),
               ("GPT-4o [Springer], none", "gpt-4o-2024-05-13, 0-shot"),
               ("GPT-4o [Springer], three documents", "gpt-4o-2024-05-13, 3-shot"),
               ("GPT-4-turbo [Springer], three documents", "gpt-4-turbo-2024-04-09, 3-shot"),
               ("Llama 3 70B [Springer], three documents", "meta-llama/Meta-Llama-3-70B-Instruct, 3-shot"),
               ("Claude 3 Opus [Springer], three documents", "claude-3-opus-20240229, 3-shot"),
               ("Textual order (no LLM)", "text order, no LLM"),
               ("This method", "the method (idea 3), Qwen3.5-27B")]
METHOD_STRICT = "the method (idea 3), Qwen3.5-27B"
PAIRS_STRICT = "pair questions, as submitted (rerun at relation-idea-1b)"


def _mentions_against_neuberger():
    """PET v1.1's gold mentions (the spans the PET runs were given) against Neuberger et al.'s conversion of
    the same texts: how many coincide exactly (type and characters), and whether any other is an end of a Flow
    relation, in PET v1.1 or, overlapping, in theirs."""
    from text2bpmn import pet_strict as ps

    gold = ps.load_gold()
    jobs = {j["name"]: j for j in json.loads(Path(ps.PET_JOBS).read_text(encoding="utf-8"))["jobs"]}
    documents = _pet_documents()
    if not all(jobs[d]["text"] == gold[d]["text"] == documents[d]["text"] for d in gold):
        raise SystemExit("PET v1.1's texts and Neuberger et al.'s differ: their mentions cannot be compared")
    ours = {d: {(s["label"].lower(), s["start"], s["end"]) for s in jobs[d]["spans"]} for d in gold}
    others = [(d, k) for d in gold for k in ours[d] - set(gold[d]["mentions"])]
    kinds = Counter(k[0] for _, k in others)
    ends = {d: {(x["start"], x["end"]) for kind, a, b in documents[d]["relations"] if kind == "flow" for x in (a, b)}
            for d in gold}
    theirs = {d: {k for tag, h, t in gold[d]["relations"] if tag == "flow" for k in (h, t)} for d in gold}
    in_flow = sum((k[1], k[2]) in ends[d] or any(m[1] < k[2] and k[1] < m[2] for m in theirs[d]) for d, k in others)
    total = sum(map(len, ours.values()))
    return {"gold mentions (PET v1.1), of them exactly Neuberger et al.'s": f"{total:,}, {total - len(others):,}",
            "the others: actors, activity data, activities":
                f"{kinds['actor']}, {kinds['activity data']}, {kinds['activity']}",
            "of the others, in a Flow relation (PET v1.1 or theirs)": str(in_flow)}


def table5(**_):
    result = _strict()
    systems, differences = result["systems"], result["differences"]
    rows = [[row, f3(systems[s]["folds"]["p"]), f3(systems[s]["folds"]["r"]), f3(systems[s]["folds"]["f1"]),
             f3(systems[s]["pooled"]["f1"])] for row, s in STRICT_ROWS]
    text = {f"method - {label}": interval(differences[f"method − {key}"]) for label, key in (
        ("RuleRelEx", "RuleRelEx (Bellan et al.'s rules)"), ("textual order", "text order, no LLM"),
        ("GPT-4o, none", "gpt-4o-2024-05-13, 0-shot"), ("GPT-4o, three", "gpt-4o-2024-05-13, 3-shot"),
        ("Claude 3 Opus, three", "claude-3-opus-20240229, 3-shot"))}
    text["method, rule 1 alone (pooled)"] = f3(systems[f"{METHOD_STRICT}, rule 1 only"]["pooled"]["f1"])
    text.update(_mentions_against_neuberger())
    return {"columns": ["System", "P", "R", "F1 (folds)", "F1 (pooled)"], "rows": rows, "text": text,
            "checks": {"gold Flow relations": result["gold_flows"]},
            "inputs": ["text2bpmn/baselines/neuberger (pet_strict --fetch)", "runs/final-3/pet_decisions",
                       "runs/final-3/pet_no_llm"],
            "command": "python3 -m text2bpmn.paper_tables 5"}


# --- Table 6: the pairwise classifier on the 302 pairs ------------------------------------------------

TABLE3_RUN = Path("runs/final/table3_302")
LABEL_ORDER = ["CONDITION_DEF", "TRUE_BRANCH", "FALSE_BRANCH", "SEQUENCE", "PARALLEL"]


def table6(**_):
    from text2bpmn import relation_metrics as rm
    from text2bpmn import rescore_false_branch_schemes as fb
    from text2bpmn.guardrails import has_marker

    samples = rm.load_dataset("benchmark_silver_2.jsonl")
    predicted = rm.predictions_from_report(TABLE3_RUN / "benchmark.md", samples)
    res = rm.compute([s["label"] for s in samples], predicted)
    row_of = {l: i for i, l in enumerate(res["labels"])}
    column_of = {l: j for j, l in enumerate(res["predicted_columns"])}
    rows = []
    for label in LABEL_ORDER:
        m = res["per_class"][label]
        rows.append([label.replace("_", " "), str(m["support"]), f3(m["precision"]), f3(m["recall"]), f3(m["f1"])]
                    + [str(res["confusion_matrix"][row_of[label]][column_of[c]]) for c in LABEL_ORDER])
    # the same answers from the run's log, as rescore_false_branch_schemes reads them
    data = fb.load()
    given = fb.answers(TABLE3_RUN, data)
    unmarked = {i for i, d in enumerate(data) if d["label"] == "FALSE_BRANCH"
                and not (has_marker(d["entity_1"]) or has_marker(d["entity_2"]))}
    syntactic = sum(given[i] == ("TRUE_BRANCH" if i in unmarked else d["label"]) for i, d in enumerate(data))
    false_true = [i for i, d in enumerate(data) if d["label"] == "FALSE_BRANCH" and given[i] == "TRUE_BRANCH"]
    text = {"accuracy": f"{res['accuracy']:.3f} ({res['correct']}/{res['n']})", "macro F1": f3(res["macro_f1"]),
            "weighted F1": f3(res["weighted_f1"]),
            "FALSE BRANCH labelled TRUE BRANCH, of them without an else-marker":
                f"{len(false_true)}, {len(set(false_true) & unmarked)} of {len(unmarked)}",
            "SEQUENCE labelled PARALLEL": str(sum(d["label"] == "SEQUENCE" and given[i] == "PARALLEL"
                                                  for i, d in enumerate(data))),
            "correct under the syntactic scheme": f"{syntactic} of {len(data)} ({100 * syntactic / len(data):.1f}%)"}
    return {"columns": ["Label", "Pairs", "P", "R", "F1", "COND", "TRUE", "FALSE", "SEQ", "PAR"], "rows": rows,
            "text": text,
            "checks": {"the report's predictions equal the log's answers, pair for pair":
                       all(given[i] == predicted[i] for i in range(len(data)))},
            "inputs": ["benchmark_silver_2.jsonl", str(TABLE3_RUN / "benchmark.md"), str(TABLE3_RUN / "log.txt")],
            "command": "python3 -m text2bpmn.paper_tables 6"}


# --- Table 7: lanes -------------------------------------------------------------------------------------

LANE_ARMS = {"BERT, with FastCoref": ("runs/final-3/coref_ablation", "with_coref"),
             "BERT, without": ("runs/final-3/coref_ablation", "without_coref"),
             "GLiNER, with FastCoref": ("runs/gliner-3/lanes_gliner", "with_coref")}


def _lanes(folder, arm, exclude_recipients=False):
    from text2bpmn.lane_accuracy import MAIN_PROCESS, normalise, score_document

    rows, lanes = [], []
    for name, document in _pet_documents().items():
        d = Path(folder) / arm / name
        if (d / "extraction.json").exists() and (d / "log.txt").exists():
            r, l = score_document(d, document, exclude_recipients)
            rows += [{**x, "document": name} for x in r]
            lanes += l
    return rows, sum(normalise(l) == MAIN_PROCESS for l in lanes), len(lanes)


def table7(**_):
    from text2bpmn.compare_gliner_arm import counts, paired_difference

    arms, columns = {}, list(LANE_ARMS)
    checks = {}
    for label, (folder, arm) in LANE_ARMS.items():
        rows, main, tasks = _lanes(folder, arm)
        without, _, _ = _lanes(folder, arm, exclude_recipients=True)
        saved = json.loads((Path(folder) / "lane_scores.json").read_text(encoding="utf-8"))[arm]["rows"]
        checks[f"{label}: the rows equal the run's lane_scores.json"] = rows == saved
        arms[label] = {"rows": rows, "c": counts(rows), "x": counts(without), "main": main, "tasks": tasks}
    a = [arms[k] for k in columns]
    table = [
        ["Of the recognised activities"] + [f"{pct(x['c']['correct'], x['c']['recognised'])} "
                                            f"({x['c']['correct']}/{x['c']['recognised']})" for x in a],
        [f"Of all {a[0]['c']['gold']} gold activities"] + [pct(x["c"]["correct"], x["c"]["gold"]) for x in a],
        ["With a pronoun as performer"] + [f"{pct(x['c']['pronoun_correct'], x['c']['pronoun_recognised'])} "
                                           f"({x['c']['pronoun_correct']}/{x['c']['pronoun_recognised']})" for x in a],
        [f"Without the {a[0]['c']['gold'] - a[0]['x']['gold']} with a recipient"]
        + [f"{pct(x['x']['correct'], x['x']['recognised'])} ({x['x']['correct']}/{x['x']['recognised']})" for x in a],
        ["Tasks in Main Process"] + [pct(x["main"], x["tasks"]) for x in a]]
    coref, _ = paired_difference(arms["BERT, with FastCoref"]["rows"], arms["BERT, without"]["rows"])
    gliner, boot = paired_difference(arms["GLiNER, with FastCoref"]["rows"], arms["BERT, with FastCoref"]["rows"])
    text = {"gold activities with a performer, documents": f"{a[0]['c']['gold']}, {boot['documents']}",
            "of them with an actor recipient": str(a[0]["c"]["gold"] - a[0]["x"]["gold"]),
            "with - without FastCoref, of recognised": interval(coref["of_recognised"]),
            "with - without FastCoref, of all gold": interval(coref["of_gold"]),
            "GLiNER - BERT, of recognised": interval(gliner["of_recognised"]),
            "GLiNER - BERT, of all gold": interval(gliner["of_gold"])}
    checks["Main Process tasks, of all tasks"] = {k: f"{v['main']}/{v['tasks']}" for k, v in arms.items()}
    return {"columns": ["", *columns], "rows": table, "text": text, "checks": checks,
            "inputs": ["runs/final-3/coref_ablation", "runs/gliner-3/lanes_gliner", PET],
            "command": "python3 -m text2bpmn.paper_tables 7"}


# --- Table 8: relation stages ---------------------------------------------------------------------------

# (row, PET run, strict system, check folder whose WOFLAN record holds its models, record)
STAGES = [
    ("Textual order (no LLM)", "runs/final-3/pet_no_llm", "text order, no LLM", "pairs",
     ("runs/checks/final-3/soundness/soundness.json", "runs/checks/final-3/pet_models/pet_no_llm")),
    ("Pairwise classification", "runs/ideas/idea1b/pet_pairs", PAIRS_STRICT, "pairs",
     (str(OUT / "pet_pairs" / "soundness" / "soundness.json"), str(OUT / "pet_pairs" / "models"))),
    ("Method without concurrency question", "runs/final-2/pet_decisions", "idea 1c (revision-final-2)", "decisions3",
     ("runs/checks/final-2/soundness/soundness.json", "runs/checks/final-2/pet_models/pet_decisions")),
    ("This method", "runs/final-3/pet_decisions", METHOD_STRICT, "decisions4",
     ("runs/checks/final-3/soundness/soundness.json", "runs/checks/final-3/pet_models/pet_decisions")),
]
SUBMITTED_PAIRS = "runs/final/pet_classifier"


def _woflan_record(record, folder):
    entry = json.loads(Path(record).read_text(encoding="utf-8"))["folders"][folder]
    return entry["counts"].get("sound", 0), entry["models"], entry["per_model"]


def _woflan_again(run):
    """Every saved PET model of `run` written as BPMN and checked by WOFLAN now."""
    from text2bpmn.checks.soundness import check
    from text2bpmn.checks.write_pet_models import write as write_models

    with tempfile.TemporaryDirectory() as tmp:
        written, refused = write_models(run, tmp)
        per_model = {f"{name}/model.bpmn": {**check(Path(tmp) / name / "model.bpmn", 60),
                                             "parallel_gateway": _has_parallel_gateway(Path(tmp) / name / "model.bpmn")}
                     for name in written}
    return sum(m["status"] == "sound" for m in per_model.values()), len(written) + len(refused), per_model


def _has_parallel_gateway(path):
    import xml.etree.ElementTree as ET
    return any(e.tag.endswith("parallelGateway") for e in ET.parse(path).iter())


def table8(woflan=False, **_):
    from text2bpmn import relation_ideas as ri

    strict = _strict()
    records = {row: ri.records(run) for row, run, _, _, _ in STAGES}
    totals = {row: ri.totals(r.values()) for row, r in records.items()}
    rows, checks = [], {}
    for row, run, system, _, (record, folder) in STAGES:
        t = totals[row]
        c = t["concurrency"]
        found = f"{c['tp']} of {c['tp'] + c['fn']}" + (f" (+{c['fp']})" if c["fp"] else "")
        sound, models, per_model = _woflan_record(record, folder)
        if woflan:
            again = _woflan_again(run)
            checks[f"{row}: WOFLAN now, sound/models"] = f"{again[0]}/{again[1]} (record {sound}/{models})"
            sound, models, per_model = again
        rows.append([row, f3(t["scored"]["f1"]), f3(t["all"]["f1"]), f3(strict["systems"][system]["pooled"]["f1"]),
                     found, f"{t['calls'] - t['failed']:,}", f"{sound}/{models}"])
        if row == "Pairwise classification":
            rejected = [m for m, v in per_model.items() if v["status"] != "sound"]
            checks["the pairwise models WOFLAN rejects"] = sorted(rejected)
            if not woflan:  # their behaviour, by the soundness gate's token game (text2bpmn/soundness_gate.py)
                from text2bpmn.soundness_gate import check as token_game, graph_of_bpmn
                game = {m: token_game(*graph_of_bpmn(Path(folder) / m)) for m in per_model}
                checks["the pairwise models: the token game agrees with WOFLAN on every one"] = all(
                    game[m]["sound"] == (v["status"] == "sound") for m, v in per_model.items())
                checks["the rejected ones, by the token game"] = {m: game[m]["reason"] for m in sorted(rejected)}
            with_block = sum(per_model[m]["parallel_gateway"] if woflan else _has_parallel_gateway(Path(folder) / m)
                             for m in rejected)
    # the pairwise rerun stands for revision-final's run, which kept neither answers nor graphs
    submitted = ri.records(SUBMITTED_PAIRS)
    rerun = records["Pairwise classification"]
    checks["the rerun's counts equal revision-final's (runs/final/pet_classifier) on every document"] = \
        sorted(submitted) == sorted(rerun) and all(submitted[d]["counts"] == rerun[d]["counts"] for d in submitted)
    text_order, pairs, without, method = (records[r] for r, *_ in STAGES)
    d = strict["differences"]
    text = {"pairwise - textual order, three shapes": interval(ri.paired(pairs, text_order, "counts")),
            "pairwise - textual order, all flows": interval(ri.paired(pairs, text_order, "all_flows")),
            "pairwise, inserted gateways collapsed (strict, pooled)":
                f3(strict["systems"][f"{PAIRS_STRICT}, inserted gateways collapsed"]["pooled"]["f1"]),
            "method - pairwise, three shapes": interval(ri.paired(method, pairs, "counts")),
            "method - pairwise, all flows": interval(ri.paired(method, pairs, "all_flows")),
            "method - pairwise, strict": interval(d[f"method − {PAIRS_STRICT}"]),
            "method - textual order, three shapes": interval(ri.paired(method, text_order, "counts")),
            "method - textual order, all flows": interval(ri.paired(method, text_order, "all_flows")),
            "method - textual order, strict": interval(d["method − text order, no LLM"]),
            "method - method without concurrency question, strict": interval(d["method − idea 1c (revision-final-2)"])}
    text["WOFLAN-rejected pairwise models that contain a parallel gateway"] = \
        f"{with_block} of {len(checks['the pairwise models WOFLAN rejects'])}"
    from text2bpmn import pet_strict as ps
    from text2bpmn.checks.method_analysis import limits

    asked = limits(ps.load_gold())["PET"]
    seconds = json.loads(Path("runs/final-3/summary.json").read_text(encoding="utf-8"))["experiments"][
        "pet_decisions"]["seconds"]
    text["the method's calls: decision, concurrency questions"] = \
        f"{asked['decisions asked']}, {asked['concurrency words asked']}"
    text["decision answers with no branch (text order kept)"] = str(asked["no branch in the answer (text order kept)"])
    text["PET's concurrency cues, of them asked about"] = \
        f"{asked['concurrency words in the text']}, {asked['concurrency words asked']}"
    text["the method's PET experiment, minutes (seconds)"] = f"{round(seconds / 60)} ({round(seconds)})"
    checks["calls asked, failed (the text order's are all refused: no LLM)"] = \
        {row: f"{t['calls']}, {t['failed']}" for row, t in totals.items()}
    return {"columns": ["Relation stage", "Three shapes", "All flows", "Strict", "Parallel pairs", "Calls", "Sound"],
            "rows": rows, "text": text, "checks": checks,
            "inputs": [run for _, run, *_ in STAGES] + [record for *_, (record, _) in STAGES]
            + ["text2bpmn/baselines/neuberger (pet_strict --fetch)", SUBMITTED_PAIRS, "runs/final-3/summary.json"],
            "command": "python3 -m text2bpmn.paper_tables 8" + (" --woflan" if woflan else "")}


# --- Table 9: decisions -------------------------------------------------------------------------------------

DECISION_RUNS = {"Textual order (no LLM)": ("runs/final-3/pet_no_llm", "pairs"),
                 "Method without the LLM": ("runs/final-3/pet_no_and", "decisions4"),
                 "This method": ("runs/final-3/pet_decisions", "decisions4")}
OUTCOMES = ["right: the same branch heads", "not built: one way on or none", "a wrong branch head",
            "an extra branch head", "a branch head missed"]


def table9(**_):
    from text2bpmn import pet_strict as ps
    from text2bpmn.checks import method_analysis as ma

    gold = ps.load_gold()
    jobs = json.loads(Path(ps.PET_JOBS).read_text(encoding="utf-8"))["jobs"]
    documents = sorted(gold)
    outcomes = {row: ma.decision_outcomes(gold, ma.rendered(folder, mode, jobs))[0]
                for row, (folder, mode) in DECISION_RUNS.items()}
    rows = []
    for row, per_document in outcomes.items():
        total = sum(per_document.values(), Counter())
        rows.append([row] + [str(total.get(o, 0)) for o in OUTCOMES] + [f3(ma.share_right(per_document, documents))])
    heads = Counter(min(len(h), 3) for d in gold.values() for _, _, h in ma.gold_decisions(d))
    method = outcomes["This method"]
    text = {"decisions; with two, three or more, one branch head":
                f"{sum(heads.values())}; {heads[2]}, {heads[3]}, {heads[1]}",
            "method - method without the LLM": interval(ma.paired_share(method, outcomes["Method without the LLM"],
                                                                        documents)),
            "method - textual order": interval(ma.paired_share(method, outcomes["Textual order (no LLM)"], documents))}
    checks = {"decisions with no branch head in PET": heads.get(0, 0)}
    return {"columns": ["Relation stage", "Right", "Not built", "Wrong head", "Extra head", "Missed", "Share right"],
            "rows": rows, "text": text, "checks": checks,
            "inputs": [f for f, _ in DECISION_RUNS.values()] + ["text2bpmn/baselines/neuberger (pet_strict --fetch)"],
            "command": "python3 -m text2bpmn.paper_tables 9"}


# --- Table 10: the reference processes ------------------------------------------------------------------------

CASES = [("Loan", "loan"), ("Goods dispatch", "goods_dispatch"), ("Healthcare", "healthcare")]
CASE_ARMS = [("BERT, method", "runs/final-3/cases"), ("BERT, no LLM", "runs/final-3/cases_no_llm"),
             ("GLiNER, method", "runs/gliner-3/cases_gliner"), ("GLiNER, no LLM", "runs/gliner-3/cases_gliner_no_llm")]
RELEASE_TAG = "revision-final-3"


# Corrections made to a reference after the tag that change no score: the file
# at the tag with these replacements must equal the current file. healthcare:
# the lane "Familiy" spelt "Family" (compare.py reads no lane name, and no
# generated model puts a task of that lane in a "Family" lane, so CQ1 is the
# same).
SCORE_NEUTRAL_CORRECTIONS = {"healthcare": [('name="Familiy"', 'name="Family"')]}

# The git blob ids of text2bpmn/cases/<case>/reference.bpmn at revision-final-3 (commit 808815f), the
# references the release runs were scored against. Recorded here so that the check needs neither that
# history nor git; the loan's file is reference_authored.bpmn now.
REFERENCE_BLOBS_AT_TAG = {"goods_dispatch": "bbd7bb0553f00b5a34a033201595353246583498",
                          "healthcare": "d30ae559f703eb48c475f702e26b5b996a56f1c1",
                          "loan": "641421f8305481b324b5e25362d906b4009e94ed"}


def same_as_at_tag(case, ref):
    """True if ref is the file at the tag, or that file with the case's documented
    score-neutral corrections."""
    at_tag = REFERENCE_BLOBS_AT_TAG[case]
    data = Path(ref).read_bytes()
    if _blob_id(data) == at_tag:
        return True
    if Path(ref).name != "reference.bpmn" or case not in SCORE_NEUTRAL_CORRECTIONS:
        return False
    # undo the corrections, each of which must occur exactly once, and compare with the tag's file
    text = data.decode("utf-8")
    for old, new in reversed(SCORE_NEUTRAL_CORRECTIONS[case]):
        if text.count(new) != 1:
            return False
        text = text.replace(new, old)
    return _blob_id(text.encode("utf-8")) == at_tag


# Every case is scored against text2bpmn/cases/<case>/reference.bpmn. The loan's is the textbook's
# Solution 3.2 (D12); the runs were scored against the authored model now kept as AUTHORED_LOAN, and
# each loan folder keeps that score as comparison_authored.json beside its comparison.json.
AUTHORED_LOAN = Path("text2bpmn/cases/loan/reference_authored.bpmn")


def table10(**_):
    from text2bpmn.behaviour import compare_behaviour
    from text2bpmn.compare import compare, read_bpmn

    rows, checks, scores = [], {}, {}
    for case_label, case in CASES:
        ref = Path(f"text2bpmn/cases/{case}/reference.bpmn")
        if case == "loan":
            checks[f"loan: {AUTHORED_LOAN}, the reference the runs scored against, is the one at {RELEASE_TAG}"] = \
                same_as_at_tag(case, AUTHORED_LOAN)
        else:
            checks[f"{case}: {ref} is the reference at {RELEASE_TAG}" + (
                " (with its documented score-neutral corrections)" if case in SCORE_NEUTRAL_CORRECTIONS else "")] = \
                same_as_at_tag(case, ref)
        for arm_label, run in CASE_ARMS:
            model = Path(run) / case / "model.bpmn"
            now = compare(read_bpmn(ref), read_bpmn(model))
            saved = json.loads((Path(run) / case / "comparison.json").read_text(encoding="utf-8"))
            same_counts = lambda a, b: all(a[e][k] == b[e][k] for e in ("tasks", "gateways", "edges")  # noqa: E731
                                           for k in ("tp", "fp", "fn")) and a["ged"] == b["ged"]
            checks[f"{case}, {arm_label}: scored again from the XML = the run's comparison.json"] = same_counts(now, saved)
            if case == "loan":
                own = json.loads((Path(run) / case / "comparison_authored.json").read_text(encoding="utf-8"))
                checks[f"loan, {arm_label}: against {AUTHORED_LOAN.name}, scored again = the run's own score, "
                       "comparison_authored.json"] = same_counts(compare(read_bpmn(AUTHORED_LOAN), read_bpmn(model)), own)
            g = now["ged"]
            rged = g["ged"] / (g["generated_size"] + g["reference_size"])
            checks[f"{case}, {arm_label}: RGED = the saved rged_combined"] = round(rged, 3) == g["rged_combined"]
            footprint = compare_behaviour(str(ref), str(model))["behavioural_similarity"]
            scores[case, arm_label] = {**now, "footprint": footprint}
            cell = lambda e, short=False: bare(now[e]["f1"]) + ("" if short else  # noqa: E731
                                                                f" ({now[e]['tp']}/{now[e]['fp']}/{now[e]['fn']})")
            no_llm = arm_label.endswith("no LLM")
            rows.append([f"{case_label}, {arm_label}", cell("tasks", no_llm),
                         cell("gateways", arm_label == "GLiNER, no LLM"), cell("edges"), f"{g['ged']:.2f}",
                         f"{g['generated_size']} / {g['reference_size']}", f3(rged), f3(1 - rged), f3(footprint)])
    checks["tasks are the same with and without the LLM, for each recogniser and case"] = all(
        scores[c, f"{r}, method"]["tasks"] == scores[c, f"{r}, no LLM"]["tasks"]
        for _, c in CASES for r in ("BERT", "GLiNER"))
    return {"columns": ["Process, configuration", "Tasks", "Gateways", "Flows", "GED", "|G| gen./ref.", "RGED", "Sim",
                        "Footprint"],
            "rows": rows, "text": table10_text(scores), "checks": checks,
            "inputs": [run for _, run in CASE_ARMS] + [f"text2bpmn/cases/{c}/reference.bpmn" for _, c in CASES]
                      + [str(AUTHORED_LOAN)],
            "command": "python3 -m text2bpmn.paper_tables 10"}


def table10_text(scores):
    """The numbers Section 4.6's text reports with Table 10, from the same scores."""
    cases = [c for _, c in CASES]
    names = dict((c, label.lower()) for label, c in CASES)
    bert, bert_no = (lambda c: scores[c, "BERT, method"]), (lambda c: scores[c, "BERT, no LLM"])
    gliner = lambda c: scores[c, "GLiNER, method"]  # noqa: E731
    tasks = [s["tasks"]["f1"] for (c, arm), s in scores.items() if arm.startswith("BERT")]
    found = sum(bert(c)["gateways"]["tp"] for c in cases)
    of = sum(bert(c)["gateways"]["tp"] + bert(c)["gateways"]["fn"] for c in cases)
    wrong = sum(bert(c)["gateways"]["fp"] for c in cases)
    larger = lambda s: s["ged"]["ged"] / max(s["ged"]["generated_size"], s["ged"]["reference_size"])  # noqa: E731
    footprints = [s["footprint"] for s in scores.values()]
    where = lambda test: ", ".join(names[c] for c in cases if test(c))  # noqa: E731
    return {
        "task F1 with BERT, lowest and highest": f"{100 * min(tasks):.0f}% and {100 * max(tasks):.0f}%",
        "gateways of the three references found with BERT and the LLM, of all; wrong": f"{found} of {of}; {wrong}",
        "flows matching the references, BERT, with / without the LLM":
            f"{sum(bert(c)['edges']['tp'] for c in cases)} / {sum(bert_no(c)['edges']['tp'] for c in cases)}",
        "GED with / without the LLM, BERT: loan; goods dispatch; healthcare":
            "; ".join(f"{bert(c)['ged']['ged']:.2f} / {bert_no(c)['ged']['ged']:.2f}" for c in cases),
        "flows the references do not have, BERT, with / without the LLM: goods dispatch; healthcare":
            "; ".join(f"{bert(c)['edges']['fp']} / {bert_no(c)['edges']['fp']}" for c in ("goods_dispatch", "healthcare")),
        "GED over the larger graph, BERT, with the LLM against without: loan, goods dispatch, healthcare":
            ", ".join("lower" if larger(bert(c)) < larger(bert_no(c)) else "higher" for c in cases),
        "footprint similarity, lowest to highest": f"{min(footprints):.2f} to {max(footprints):.2f}",
        "GLiNER against BERT, with the LLM":
            f"tasks better on {where(lambda c: gliner(c)['tasks']['f1'] > bert(c)['tasks']['f1'])}, "
            f"worse on {where(lambda c: gliner(c)['tasks']['f1'] < bert(c)['tasks']['f1'])}; "
            f"flows better on {where(lambda c: gliner(c)['edges']['f1'] > bert(c)['edges']['f1'])}; "
            f"GED lower on {where(lambda c: gliner(c)['ged']['ged'] < bert(c)['ged']['ged'])}; "
            f"more gateways found with BERT on {where(lambda c: bert(c)['gateways']['tp'] > gliner(c)['gateways']['tp'])}",
    }


BUILDERS = {2: table2, 3: table3, 4: table4, 5: table5, 6: table6, 7: table7, 8: table8, 9: table9, 10: table10}


# --- the report ----------------------------------------------------------------------------------------------

def build(number, woflan=False):
    table = BUILDERS[number](woflan=woflan)
    table["differences"] = compare_with_draft(number, table)
    return table


def markdown(number, table, record):
    lines = header(f"Table {number}: {TITLES[number]}", record)
    lines += [f"Rebuilt by `{table['command']}` (text2bpmn/paper_tables.py) from {', '.join(f'`{i}`' for i in table['inputs'])}. "
              f"Draft: {DRAFTS[WHERE[number]]}.", "",
              "| " + " | ".join(table["columns"]) + " |", "|" + "---|" * len(table["columns"])]
    lines += ["| " + " | ".join(row) + " |" for row in table["rows"]]
    paper_text = PAPER.get(number, {}).get("text", {})
    if table["text"]:
        lines += ["", "With it, in the section's text:", "", "| value | rebuilt | draft |", "|---|---|---|"]
        for label, value in table["text"].items():
            printed = paper_text.get(label, ("–", None))
            lines.append(f"| {label} | {value} | {printed[0]}" + (f" ({DRAFTS[printed[1]].split(' (')[0]})"
                                                                   if printed[1] and printed[1] != WHERE[number] else "")
                         + " |")
    lines += ["", "## Against the draft", ""]
    cells = sum(len(r) - 1 for r in PAPER.get(number, {}).get("rows", [])) + len(paper_text)
    if not table["differences"]:
        lines.append(f"All {cells} values compared (cells and text values) are the draft's.")
    else:
        lines.append(f"{cells - len(table['differences'])} of {cells} values compared are the draft's; these differ:")
        lines.append("")
        for row, column, printed, ours, why in table["differences"]:
            lines.append(f"- {row}, {column}: draft {printed}, rebuilt {ours}" + (f". {why}" if why else
                                                                                   ". NOT EXPLAINED"))
    if table.get("checks"):
        lines += ["", "## Checks", ""]
        lines += [f"- {k}: {v}" for k, v in table["checks"].items()]
    return "\n".join(lines) + "\n"


def run(number, out=OUT, woflan=False, record=None):
    """record: the provenance, taken once before anything is written when several tables are."""
    table = build(number, woflan)
    record = record or provenance()
    result = {"table": number, "title": TITLES[number], "draft": DRAFTS[WHERE[number]], "provenance": record,
              **{k: v for k, v in table.items()}}
    write(out, f"table{number}", json.loads(json.dumps(result, default=str)), markdown(number, table, record))
    return table


def unexplained(table):
    return [d for d in table["differences"] if d[4] is None]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("table", nargs="?", help="a table number, 2-10, or all")
    ap.add_argument("--woflan", action="store_true", help="Table 8: run WOFLAN again on every model")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    if args.list or not args.table:
        for n, title in TITLES.items():
            print(f"Table {n}: {title} -- {DRAFTS[WHERE[n]]}"
                  + ("" if n in BUILDERS else " (the literature; no measurement to rebuild)"))
        return
    numbers_asked = sorted(BUILDERS) if args.table == "all" else [int(args.table)]
    if any(n not in BUILDERS for n in numbers_asked):
        raise SystemExit(f"tables {sorted(BUILDERS)} or all; Table 1 holds no measurement")
    summary, failed = ["# The paper's tables rebuilt from the committed runs", "",
                       "`python3 -m text2bpmn.paper_tables all`; one file per table beside this one.", "",
                       "| table | values compared (cells, text values) | differ from the draft | of them explained |", "|---|---|---|---|"], []
    record = provenance()
    for n in numbers_asked:
        table = run(n, args.out, args.woflan, record)
        paper = PAPER.get(n, {})
        cells = sum(len(r) - 1 for r in paper.get("rows", [])) + len(paper.get("text", {}))
        summary.append(f"| {n}: {TITLES[n]} | {cells} | {len(table['differences'])} | "
                       f"{len(table['differences']) - len(unexplained(table))} |")
        print(Path(args.out, f"table{n}.md").read_text(encoding="utf-8"))
        failed += [(n, d) for d in unexplained(table)]
    if args.table == "all":
        Path(args.out, "summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    if failed:
        raise SystemExit("differences from the draft not explained: "
                         + "; ".join(f"Table {n}, {d[0]}, {d[1]}: draft {d[2]}, rebuilt {d[3]}" for n, d in failed))


if __name__ == "__main__":
    main()
