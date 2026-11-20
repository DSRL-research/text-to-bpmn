"""The relation classifier's instructions, as data rather than a docstring.

`RunConfig.prompt` picks one by name, and every run records which.

- `corrected`, the default: `PUBLISHED` with rule 1 stated the way the
  pipeline uses the answer, "B follows A". It is the only change.
- `published`: the text behind the three case studies and the PET runs, pinned
  by `PUBLISHED_SHA256`.
- `table3`: the text behind Table 3 and the guardrail replay. The benchmark
  kept its own copy of the signature, whose rule 5 has no examples, so Table 3
  was not produced with `PUBLISHED`. Pinned by `TABLE3_SHA256`.
- `revised`: a broader rewrite, below; a measured arm, not the default.
- `corrected_none`: `CORRECTED` with a sixth answer, NONE, for a pair that is
  not directly connected; relation idea 2 (RunConfig.relation_mode "pairs2"),
  whose answer schema has the sixth label too.

A pinned text is never edited: a correction is a new entry, so the published
numbers can always be reproduced with the text that produced them.

What `REVISED` changes, and why each one:

- **The direction of SEQUENCE.** The published rule reads "SEQUENCE: A follows
  B chronologically", but `finder3._build_flows` asks about `(current,
  lookahead)` -- node_A earlier in the text, node_B later -- and builds the
  edge node_A -> node_B. The rule states the opposite of what the answer is
  used for, on the label that covers 334 of PET's 491 scored flows. The ten
  in-context examples contradict the rule as well (`sends a complaint ->
  reads the complaint` is SEQUENCE), so the model has been given a rule and ten
  counterexamples to it.
- **The pair's order is stated.** The pipeline always knows node_A comes first
  and never said so, though it is the most useful single fact for SEQUENCE.
- **An escape.** Five options presented as exhaustive left nowhere to go when
  none fits, and the model invented `UNKNOWN` -- 3 of the 14 failures in
  provenance/relation_failures_2026-10-07.md.
- **The prior.** The published examples are two of each label, where real pairs
  are overwhelmingly SEQUENCE. PARALLEL precision is already the weakest part
  of this classifier (provenance/parallel_precision.md), and a balanced example
  set argues for over-predicting it.
- The typo in rule 3.

Nothing here is claimed to help. It is written down so it can be measured
against PUBLISHED on the same documents.
"""
import hashlib
import json
from pathlib import Path

# The ten in-context demonstrations, two per label. Relative to the repository
# root, which is where every entry point is run from.
DEMONSTRATIONS = "benchmark_unseen.jsonl"

PUBLISHED = """
    Analyze the logical relationship between two process steps (Node A and Node B) based on the context.
    
    CRITICAL RULES:
    1. SEQUENCE: A follows B chronologically.
    2. CONDITION_DEF: Connects a Gateway/If-word to the Condition statement. (e.g. "If" -> "score < 600").
    3. TRUE_BRANCH: The action taken if the condition is MET/TRUE. 
       - Exampe: "If error, then stop." -> (error, stop) is TRUE_BRANCH.
       - Example: "If approved, process." -> (approved, process) is TRUE_BRANCH.
    4. FALSE_BRANCH: The action taken if the condition is NOT MET (Else/Otherwise).
       - Example: "Otherwise, reject." -> (Otherwise, reject) is FALSE_BRANCH.
       - Example: "If valid, save. Else, delete." -> (Else, delete) is FALSE_BRANCH.
    5. PARALLEL: Events happen simultaneously in separate parallel branches.
       - Example: "In parallel, task A and task B occur." -> (parallel, task A) is PARALLEL, (parallel, task B) is PARALLEL.
       - Example: "While process A happens, process B happens." -> (While, process A) is PARALLEL.
       - Example: "Meantime, the cashier prints the file." -> (Meantime, prints) is PARALLEL.
    """

# the exact text behind the case studies and the PET runs; the test fails if it drifts
PUBLISHED_SHA256 = "f5e9d9127dd1dd821962204a1341bc6112a7c0f05b9caa12827ea97378dba913"

_BACKWARDS = "1. SEQUENCE: A follows B chronologically."

# The release prompt: the pipeline asks about (earlier, later) and builds the
# edge earlier -> later, so a SEQUENCE answer means B follows A.
CORRECTED = PUBLISHED.replace(_BACKWARDS, "1. SEQUENCE: B follows A chronologically.")
assert CORRECTED != PUBLISHED

# benchmark_relations.py's own copy, which produced Table 3: identical up to
# rule 5, which it states without examples
TABLE3 = PUBLISHED.split("    5. PARALLEL")[0] + "    5. PARALLEL: Events happen simultaneously.\n    "
TABLE3_SHA256 = "46639cf5d46330adb879f062e83c8c65cc666c305746e2b6cbdbf6afd186f050"

REVISED = """
    Decide how two process steps relate, using the context.

    The two steps are given in the order they appear in the text: node_A
    appears before node_B.

    Choose exactly one:

    1. SEQUENCE: node_B happens after node_A, with no condition between them.
       - "The clerk receives the form. The clerk files the form."
         (receives the form, files the form) is SEQUENCE.
    2. CONDITION_DEF: node_A is a gateway or an "If" word, and node_B states the
       condition it tests.
       - "If the score is high, accept." -> (If, the score is high) is CONDITION_DEF.
    3. TRUE_BRANCH: node_B is what happens when the condition in node_A holds.
       - "If approved, process it." -> (approved, process it) is TRUE_BRANCH.
    4. FALSE_BRANCH: node_B is what happens when the condition does not hold;
       node_A is the else-marker.
       - "If valid, save. Else, delete." -> (Else, delete) is FALSE_BRANCH.
    5. PARALLEL: node_A and node_B run at the same time, in separate branches.
       - "In parallel, task A and task B occur." -> (In parallel, task A) is PARALLEL.
       - "While process A happens, process B happens." -> (While, process A) is PARALLEL.

    Most pairs are SEQUENCE. Choose PARALLEL only where the text says the two
    happen at the same time, not merely that both are done.

    If none of the five fits, answer with the closest one. Do not invent a
    label that is not in the list.
    """

# Relation idea 2: the five labels of CORRECTED, unchanged, and a way out. With
# five labels and no answer for "not connected", every pair asked got a
# relation; on PET a third of the answers were a branch, a condition or
# concurrency, and the pairwise pipeline lost 38 sequence flows to them.
CORRECTED_NONE = CORRECTED.rstrip() + """
    6. NONE: node_A and node_B are not directly connected: node_B neither directly
       follows node_A nor belongs to a branch or the condition of node_A.
       - "If approved, ship the goods; otherwise reject the order." -> (ship the goods, reject the order) is NONE.
       - "If the form is complete, file it. Then notify the clerk." -> (If, notify the clerk) is NONE.
    """

PROMPTS = {"corrected": CORRECTED, "published": PUBLISHED, "table3": TABLE3, "revised": REVISED,
           "corrected_none": CORRECTED_NONE}
DEFAULT_PROMPT = "corrected"


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def load_demonstrations(path=DEMONSTRATIONS):
    """The demonstrations as DSPy examples.

    A missing file, a malformed row or an empty file is an error. The
    pipeline used to run zero-shot when the file was not found, and to skip a
    row it could not read, so a run started from the wrong directory produced
    different numbers and said only that it had found no data.
    """
    import dspy

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"few-shot demonstrations not found: {path.resolve()} "
                                f"(run from the repository root)")
    examples = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            examples.append(dspy.Example(context=row["text"], node_A=row["entity_1"],
                                         node_B=row["entity_2"], relation=row["label"])
                            .with_inputs("context", "node_A", "node_B"))
        except (ValueError, KeyError, TypeError) as e:
            raise ValueError(f"{path}:{number}: not a demonstration: {e!r}") from e
    if not examples:
        raise ValueError(f"{path}: no demonstrations")
    return examples
