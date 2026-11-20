"""Flow relations against prior work on PET, under Neuberger et al.'s strict scorer.

    python3 -m text2bpmn.pet_strict --fetch   # their PET conversion, folds and stored outputs
    python3 -m text2bpmn.pet_strict           # -> text2bpmn/results/pet_strict_flow.{md,json}

Reviewers R2-5, R2-23, R3-4 and R3-6 asked for a strict comparison with prior
work. The full strict protocol scores typed relations from extracted mentions;
this pipeline builds control flow, not typed relations, so what applies is the
Flow relation alone, with gold entities, which is the scenario in which
Neuberger et al. publish per-type results:

- **CoopIS 2023** (pet-baselines, arXiv:2305.03960): relation extraction from
  perfect entities, Fig. 7c and Tab. 1b. A relation is right iff its tag and
  both its arguments match; an argument is an entity, the set of its mentions,
  and a mention is its tag, sentence and exact tokens (data/model.py
  `to_tuple`). Counts per tag on each of five fixed folds (jsonl/fold_i), P, R
  and F1 per fold, averaged over the folds (main.py).
- **ER 2024** (llm-process-generation, branch er2024, arXiv:2407.18540): the
  same task for LLMs, one call per relation group (Flow on its own). A relation
  is (tag, head mention, tail mention), each prediction matched to at most one
  gold relation (eval/metrics.py), counts pooled over all 45 documents
  (experiments/parse.py). The paper prints only the overall score.

Both scorers are reimplemented here, not run: their code carries no licence,
and only their data files are read. The reimplementation reproduces what they
published from their own stored outputs (the rule-based baseline's Tab. 1b, and
every model's Tab. 2 row); the report shows those checks. For Flow, whose
arguments are behavioural mentions that no entity groups, entity-level and
mention-level matching coincide.

**From this pipeline's model to PET's Flow relations.** The pipeline does not
predict relations between mentions; it builds a process graph, and PET
annotates some of the same structure differently. The model graph (before the
Validation Layer) is written as Flow relations by four fixed rules, which only
restate what the model says:

1. a flow between two elements is a relation between the mentions they stand
   for; flows from the start event and into the end event have none;
2. a decision whose mention absorbed a condition is written decision ->
   condition, and the flows leaving it for its own case leave from the
   condition (PET's 80 decision -> condition and 79 condition -> step flows);
3. the flow leaving a decision for its other outcome leaves from the
   else-marker that stands for the decision, if one does ("otherwise" -> step,
   PET's convention);
4. the flow leaving a decision for a case opened by a second mention of it
   leaves from that mention, written with its condition as in rule 2.

The pairwise mode, the method as submitted, also inserts split and join
gateways that stand for no mention, in its parallel blocks. The four rules
leave the flows into and out of such a gateway out (rule 1 finds no mention
for them), which gives the pairwise row its higher score; collapsing the
gateway instead, each mention before it linked to each mention after it, is
reported beside it. The final method's gateways are all mentions, so neither
reading changes it.

What the model stands on is recovered by replaying the run: the pipeline runs
again on each document's gold spans, each question answered with the answer
the run logged, and the graph it builds must equal the saved one. The report
also gives the score with rule 1 alone.
"""
import argparse
import contextlib
import hashlib
import io
import json
import random
import urllib.request
from collections import defaultdict
from pathlib import Path

SOURCES = Path("text2bpmn/baselines/neuberger_sources.json")
FETCHED = Path("text2bpmn/baselines/neuberger")
PET_JOBS = "text2bpmn/baselines/pet_jobs.json"
OUT = Path("text2bpmn/results/pet_strict_flow")
ALL_NEW = "llm-process-generation/res/data/pet/all.new.jsonl"
FOLD = "pet-baselines/jsonl/fold_{}/test.json"
STORED = "pet-baselines/predictions/{}/fold-{}.json"
RESAMPLES, SEED = 1000, 0

# our runs: (label, folder, relation mode)
# the method is relation idea 3 since revision-final-3; idea 1c (revision-final-2) is kept beside it
OURS = [("text order, no LLM", "runs/final-3/pet_no_llm", "pairs"),
        # the method as submitted: its rerun at relation-idea-1b, whose counts equal
        # revision-final's (runs/final/pet_classifier) on every document and which,
        # unlike it, kept every answer and graph
        ("pair questions, as submitted (rerun at relation-idea-1b)", "runs/ideas/idea1b/pet_pairs", "pairs"),
        ("text order without concurrency words (the method's own control)", "runs/final-3/pet_no_and", "decisions4"),
        ("idea 1c (revision-final-2)", "runs/final-2/pet_decisions", "decisions3"),
        ("the method (idea 3), Qwen3.5-27B", "runs/final-3/pet_decisions", "decisions4")]
METHOD = OURS[-1][0]
# the published systems whose outputs are stored
BASELINES = {"RuleRelEx (Bellan et al.'s rules)": "rule-based-isolated", "BoostRelEx": "cat-boost-isolated"}
PUBLISHED_TAB1B = {"rule-based-isolated": (0.79, 0.66, 0.72), "cat-boost-isolated": (0.83, 0.82, 0.82)}
PUBLISHED_FLOW_F1 = {"cat-boost-isolated": 0.79}  # Fig. 7c; RuleRelEx's Flow value is not labelled there
LLM_TABLE = {  # (model, shots) -> (P, R, F1) as printed in ER 2024's Tab. 2 (GPT-4o's 1-shot: Tab. 1)
    ("gpt-4o-2024-05-13", 0): (0.88, 0.85, 0.86), ("gpt-4o-2024-05-13", 1): (0.90, 0.89, 0.89),
    ("gpt-4o-2024-05-13", 3): (0.90, 0.89, 0.89),
    ("gpt-4-turbo-2024-04-09", 0): (0.87, 0.79, 0.83), ("gpt-4-turbo-2024-04-09", 3): (0.89, 0.88, 0.88),
    ("gpt-4-0125-preview", 0): (0.87, 0.85, 0.86), ("gpt-4-0125-preview", 3): (0.89, 0.87, 0.88),
    ("gpt-3.5-turbo-0125", 0): (0.51, 0.06, 0.11), ("gpt-3.5-turbo-0125", 3): (0.74, 0.64, 0.69),
    ("claude-3-opus-20240229", 0): (0.86, 0.85, 0.86), ("claude-3-opus-20240229", 3): (0.92, 0.91, 0.91),
    ("claude-3-sonnet-20240229", 0): (0.78, 0.67, 0.72), ("claude-3-sonnet-20240229", 3): (0.91, 0.87, 0.89),
    ("meta-llama/Meta-Llama-3-70B-Instruct", 0): (0.76, 0.66, 0.70),
    ("meta-llama/Meta-Llama-3-70B-Instruct", 3): (0.88, 0.81, 0.84),
    ("Qwen/Qwen1.5-72B-Chat", 0): (0.61, 0.65, 0.63), ("Qwen/Qwen1.5-72B-Chat", 3): (0.74, 0.77, 0.75)}
# what the paired bootstrap sets the method beside
PAIRED = ["text order, no LLM", "pair questions, as submitted (rerun at relation-idea-1b)",
          "idea 1c (revision-final-2)", "RuleRelEx (Bellan et al.'s rules)",
          "gpt-4o-2024-05-13, 0-shot",
          "gpt-4o-2024-05-13, 3-shot", "claude-3-opus-20240229, 3-shot"]


# --- their files --------------------------------------------------------------------

def manifest():
    return json.loads(SOURCES.read_text(encoding="utf-8"))["files"]


def _local(entry):
    return FETCHED / entry["repo"].split("/")[1] / entry["path"]


def fetch():
    """Download every listed file at its commit and check its sha256."""
    for entry in manifest():
        path = _local(entry)
        if not (path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]):
            url = f"https://raw.githubusercontent.com/{entry['repo']}/{entry['commit']}/{entry['path']}"
            with urllib.request.urlopen(url, timeout=60) as response:
                body = response.read()
            if hashlib.sha256(body).hexdigest() != entry["sha256"]:
                raise SystemExit(f"{url} does not have the pinned sha256")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        print(f"   ok {entry['repo']}@{entry['commit'][:7]} {entry['path']}")


def checked(relative):
    """A fetched file (repository name/path), after checking it against the manifest."""
    entry = next(e for e in manifest() if f"{e['repo'].split('/')[1]}/{e['path']}" == relative)
    path = _local(entry)
    if not path.exists():
        raise SystemExit(f"{path} is missing: run python3 -m text2bpmn.pet_strict --fetch")
    if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
        raise SystemExit(f"{path} differs from the pinned file")
    return path


def _starts(tokens):
    """Each token's offset in the text their files carry, the tokens joined by spaces."""
    starts, at = [], 0
    for token in tokens:
        starts.append(at)
        at += len(token) + 1
    return starts


def _key(tag, starts, tokens, indices):
    """A mention: its tag and its characters, which fix its sentence and tokens."""
    return (tag.lower(), starts[indices[0]], starts[indices[-1]] + len(tokens[indices[-1]]))


def load_gold():
    """{document: {"text", "mentions": [key], "relations": [(tag, head key, tail key)]}}
    from their mention-level PET (ER 2024)."""
    gold = {}
    for doc in map(json.loads, checked(ALL_NEW).open(encoding="utf-8")):
        tokens = [t["text"] for t in doc["tokens"]]
        starts = _starts(tokens)
        keys = [_key(m["type"], starts, tokens, m["tokenDocumentIndices"]) for m in doc["mentions"]]
        gold[doc["id"]] = {"text": " ".join(tokens), "mentions": keys,
                           "relations": [(r["type"].lower(), keys[r["headMentionIndex"]],
                                          keys[r["tailMentionIndex"]]) for r in doc["relations"]]}
    return gold


def load_folds():
    """Their five CoopIS 2023 test folds: [{document: {"entity_of", "relations",
    "by_tokens"}}], an entity being the frozenset of its mention keys."""
    folds = []
    for i in range(5):
        docs = {}
        for doc in map(json.loads, checked(FOLD.format(i)).open(encoding="utf-8")):
            tokens = [t["text"] for t in doc["tokens"]]
            starts, first = _starts(tokens), {}
            for index, token in enumerate(doc["tokens"]):
                first.setdefault(token["sentence_id"], index)
            keys = [_key(m["ner"], starts, tokens, [first[m["sentence_id"]] + k for k in m["token_indices"]])
                    for m in doc["mentions"]]
            entities = [frozenset(keys[k] for k in e["mention_indices"]) for e in doc["entities"]]
            docs[doc["id"]] = {
                "entity_of": {key: e for e in entities for key in e},
                "relations": [(r["type"].lower(), frozenset(keys[k] for k in r["head_entity"]["mention_indices"]),
                               frozenset(keys[k] for k in r["tail_entity"]["mention_indices"]))
                              for r in doc["relations"]],
                "by_tokens": {(m["ner"].lower(), m["sentence_id"], tuple(m["token_indices"])): key
                              for m, key in zip(doc["mentions"], keys)}}
        folds.append(docs)
    return folds


# --- the two scorers ----------------------------------------------------------------

def prf(gold, pred, ok):
    """metrics.Stats: P and R are 1 when there is nothing to find and nothing found."""
    p = 1.0 if pred == 0 and gold == 0 else 0.0 if pred == 0 else ok / pred
    r = 1.0 if gold == 0 and pred == 0 else 0.0 if gold == 0 else ok / gold
    return {"gold": gold, "pred": pred, "ok": ok, "p": p, "r": r, "f1": 0.0 if p + r == 0 else 2 * p * r / (p + r)}


def counts_2024(gold, pred, tag="flow"):
    """(gold, pred, ok) for one tag in one document: each prediction matched to at
    most one gold relation, duplicates counted, as ER 2024's eval/metrics.py does."""
    left, ok = [r for r in gold if r[0] == tag], 0
    n_gold = len(left)
    pred = [r for r in pred if r[0] == tag]
    for r in pred:
        if r in left:
            left.remove(r)
            ok += 1
    return n_gold, len(pred), ok


def counts_2023(gold, pred, tag="flow"):
    """(gold, pred, ok) for one tag in one document, as sets, as CoopIS 2023's _f1_stats does."""
    gold = {r for r in gold if r[0] == tag}
    pred = {r for r in pred if r[0] == tag}
    return len(gold), len(pred), len(gold & pred)


def pooled(per_document, documents=None):
    """ER 2024: counts summed over the documents, then P, R, F1."""
    rows = [per_document[d] for d in (documents if documents is not None else per_document)]
    return prf(*[sum(c[k] for c in rows) for k in range(3)])


def fold_mean(per_document, folds):
    """CoopIS 2023: P, R, F1 on each fold, then their means."""
    scores = [pooled(per_document, list(docs)) for docs in folds]
    return {k: sum(s[k] for s in scores) / len(scores) for k in ("p", "r", "f1")} | \
        {"f1_by_fold": [round(s["f1"], 3) for s in scores]}


def score(relations, gold, folds, tag="flow"):
    """Both protocols for one system: relations {document: [(tag, head key, tail key)]}
    at mention level, or at entity level when the system predicted entities."""
    per_2024 = {d: counts_2024(gold[d]["relations"], _mention_level(relations.get(d, [])), tag) for d in gold}
    entity_level = {}
    for docs in folds:
        for d, truth in docs.items():
            entity_level[d] = counts_2023(truth["relations"], _entity_level(relations.get(d, []), truth["entity_of"]),
                                          tag)
    return {"pooled": pooled(per_2024), "folds": fold_mean(entity_level, folds), "per_document": per_2024}


def _mention_level(relations):
    """A system that predicted entities is scored at mention level through each
    entity's single mention; Flow's arguments have one each."""
    out = []
    for tag, head, tail in relations:
        if isinstance(head, frozenset):
            if len(head) != 1 or len(tail) != 1:
                out.append((tag, ("several", tuple(sorted(head))), ("several", tuple(sorted(tail)))))
                continue
            head, tail = next(iter(head)), next(iter(tail))
        out.append((tag, head, tail))
    return out


def _entity_level(relations, entity_of):
    """Mention-level relations as tuples of the gold entities their mentions belong to."""
    as_entity = lambda m: m if isinstance(m, frozenset) else entity_of.get(m, frozenset({m}))  # noqa: E731
    return [(tag, as_entity(h), as_entity(t)) for tag, h, t in relations]


# --- the published systems' stored outputs --------------------------------------------

def stored_baseline(run, folds):
    """{document: entity-level relations} of a CoopIS 2023 prediction dump."""
    out = {}
    for i, docs in enumerate(folds):
        for doc in json.loads(checked(STORED.format(run, i)).read_text(encoding="utf-8")):
            by_tokens = docs[doc["name"]]["by_tokens"]
            keys = [by_tokens.get((m["tag"].lower(), m["sentence_index"], tuple(m["token_indices"])),
                                  ("predicted", m["tag"].lower(), m["sentence_index"], tuple(m["token_indices"])))
                    for m in doc["mentions"]]
            entities = [frozenset(keys[k] for k in e["mention_indices"]) for e in doc["entities"]]
            out[doc["name"]] = [(r["tag"].lower(), entities[r["head"]], entities[r["tail"]])
                                for r in doc["relations"]]
    return out


def parse_listing(answer, keys):
    """format/listing.py PetRelationListingFormattingStrategy.parse: tab-separated
    "tag head tail [explanation]", indices into the document's mentions."""
    out = []
    for line in answer.splitlines():
        if "\t" not in line:
            continue
        parts = line.split("\t")
        if len(parts) not in (3, 4):
            continue
        try:
            head, tail = int(parts[1]), int(parts[2])
        except ValueError:
            continue
        if head >= len(keys) or tail >= len(keys):
            continue
        out.append((parts[0].lower().strip(), keys[head], keys[tail]))
    return out


def llm_answers(gold):
    """{(model, shots): {document: mention-level relations}} from the ER 2024 answer
    files: each call's answer parsed, and later calls' relations added when new,
    as data/pet.py PetDocument.__add__ merges them."""
    runs = {}
    for entry in manifest():
        if "/answers/" not in entry["path"]:
            continue
        folds = json.loads(checked(f"{entry['repo'].split('/')[1]}/{entry['path']}").read_text(encoding="utf-8"))
        found = {}
        for fold in folds:
            for result in fold["results"]:
                keys = gold[result["original_id"]]["mentions"]
                merged = []
                for k, answer in enumerate(result["answers"]):
                    relations = parse_listing(answer, keys)
                    if k == 0:
                        merged = list(relations)
                    else:
                        merged += [r for r in relations if r not in merged]
                found[result["original_id"]] = merged
        meta = folds[0]["meta"]
        runs[(meta["model"], meta["num_shots"])] = found
    return runs


# --- our runs: replay, then PET's Flow relations ----------------------------------------

def _fold_map(entities, gateway_types, condition_labels):
    """{gateway entity id: [condition entities]} by finder3._attach_conditions's own
    rule, computed beside it, with the names it would give."""
    names, has, kept, folded = {}, set(), [], defaultdict(list)
    for e in entities:
        if e["entity_group"] not in condition_labels:
            kept.append(e)
            names[e["id"]] = e.get("clean_name") or ""
            continue
        gateway = next((g for g in reversed(kept) if g["type"] in gateway_types), None)
        if gateway is None:
            kept.append(e)
            names[e["id"]] = e.get("clean_name") or ""
            continue
        condition = e["clean_name"]
        if not condition or condition.lower() in names[gateway["id"]].lower():
            folded[gateway["id"]].append(e)  # already in the gateway's words
            continue
        folded[gateway["id"]].append(e)
        if gateway["id"] in has:
            continue
        names[gateway["id"]] = f"{names[gateway['id']]} {condition[0].lower() + condition[1:]}".strip()
        has.add(gateway["id"])
    return dict(folded), names


def _else_markers(entities, decisions_mode, drop_and):
    """{decision id: [else-marker entities standing for it]}: in a decision mode as
    decisions.nodes_in_order skips them, in the pairwise mode as finder3's chain does."""
    from text2bpmn.decisions import GATEWAYS
    from text2bpmn.guardrails import is_else_marker
    out, last = defaultdict(list), None
    for e in entities:
        if e["type"] == "Lane":
            continue
        if is_else_marker(e["word"]) and e["type"] in GATEWAYS and last is not None:
            out[last].append(e)
            continue
        if decisions_mode and drop_and and e["type"] == "parallelGateway":
            continue
        if e["type"] in GATEWAYS:
            last = e["id"]
    return dict(out)


class Replay:
    """The pipeline on PET's gold spans, each relation question answered with the
    answer a saved run logged for it, and what its relation stage stood on."""

    def __init__(self, mode):
        from text2bpmn.finder3 import BPMNHybridExtractor
        from text2bpmn.run_config import RunConfig
        self.mode = mode
        config = RunConfig(relation_mode=mode, allow_no_llm=True, api_base="http://127.0.0.1:1", llm_timeout=5,
                           ontology_out="")
        with contextlib.redirect_stdout(io.StringIO()):
            self.extractor = BPMNHybridExtractor(config=config, ner_model_path=None)

    def __call__(self, job, saved):
        from text2bpmn import decisions
        from text2bpmn.finder3 import CONDITION_LABELS, GATEWAY_TYPES

        x, seen = self.extractor, {}
        logged = defaultdict(list)
        for r in saved["relation_parsing"].get("decisions", []):
            if r.get("source") == "llm":  # a failed call is logged as UNKNOWN and answered nothing
                logged[(r["node_A"], r["node_B"])].append(r["label"])
            elif r.get("source") == "guardrail" and r.get("model_label"):
                # the pairwise mode logs a guarded answer under the guardrail's label and the
                # model's own as model_label; the replay asks the guardrail again
                logged[(r["node_A"], r["node_B"])].append(r["model_label"])

        def ask_decision(context, decision, steps, lanes, kinds=None):
            pair = (x._relation_text(decision),
                    " | ".join(("decision: " if kind == "decision" else "") + x._relation_text(s)
                               for s, kind in zip(steps, kinds or ["step"] * len(steps))))
            answers = logged.get(pair)
            return answers.pop(0).split() if answers else None  # unlogged: the call failed

        def ask_parallel(context, cue, steps, lanes):  # relation idea 3 (relation_mode decisions4)
            pair = ("parallel: " + x._relation_text(cue), " | ".join(x._relation_text(s) for s in steps))
            answers = logged.get(pair)
            return answers.pop(0).split() if answers else None

        def predict(context, entity1, entity2):  # the pairwise mode: each pair's logged answer
            answers = logged.get((x._relation_text(entity1), x._relation_text(entity2)))
            return answers.pop(0) if answers else "UNKNOWN"  # unlogged: the call failed

        original_attach, original_plan = x._attach_conditions, decisions.plan

        def attach(entities):
            seen["folded"], names = _fold_map(entities, GATEWAY_TYPES, CONDITION_LABELS)
            kept = original_attach(entities)
            assert all(names[e["id"]] == (e.get("clean_name") or "") for e in kept), "fold rule out of step"
            seen["entities"] = kept
            return kept

        def plan(nodes, ask, alternatives=False):
            seen["nodes"], seen["plans"] = nodes, original_plan(nodes, ask, alternatives)
            return seen["plans"]

        x._attach_conditions, x._ask_decision, x._ask_parallel, x._predict_relation, decisions.plan = \
            attach, ask_decision, ask_parallel, predict, plan
        try:
            spans = [{"start": s["start"], "end": s["end"], "label": s["label"], "score": 1.0} for s in job["spans"]]
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                result = x.process_text(job["text"], entities={"text": job["text"], "spans": spans, "source": "replay"})
        finally:
            del x._attach_conditions, x._ask_decision, x._ask_parallel, x._predict_relation
            decisions.plan = original_plan
        _same_graph(result, saved)
        seen["result"] = result
        seen["decisions_mode"] = self.mode.startswith("decisions")
        return seen


def _span_flows(result):
    """The graph's flows with element ids replaced by their spans, for comparison."""
    span_of = {u["id"]: (u["start"], u["end"]) for u in result["entities_used"]}
    span_of.update({"StartEvent_1": (-1, -1), "EndEvent_1": (-2, -2)})
    # a gateway the pairwise mode inserts has a new random id in every run
    return sorted((span_of.get(f["source"], (-3, -3)), span_of.get(f["target"], (-3, -3)),
                   f.get("name", ""), f.get("relation", "")) for f in result["structured_data"]["flows"])


def _same_graph(replayed, saved):
    if _span_flows(replayed) != _span_flows(saved):
        raise AssertionError("the replay does not rebuild the saved graph")


def render(seen, rules=True, collapse=False):
    """PET-style Flow relations [(head span, tail span)] from a replayed model, by
    the module's four rules (rule 1 alone with rules=False). A span is (label, start, end).
    collapse: a gateway that stands for no mention is replaced by flows from each
    element before it to each element after it; by default its flows are left out."""
    result = seen["result"]
    span = {u["id"]: (u["label"], u["start"], u["end"]) for u in result["entities_used"] if u.get("id")}
    data = result["structured_data"]
    elements = {e["id"] for e in data["elements"]}
    flows = _collapsed(data["flows"], {e for e in elements if e not in span} - {"StartEvent_1", "EndEvent_1"}) \
        if collapse else data["flows"]
    folded = {g: [(c["entity_group"], c["start"], c["end"]) for c in cs]
              for g, cs in seen.get("folded", {}).items()} if rules else {}
    otherwise = {d: [e["id"] for e in es]
                 for d, es in _else_markers(seen["entities"], seen["decisions_mode"], drop_and=True).items()} \
        if rules else {}
    # a case opened by a second mention: (decision id, the flow's name) -> that mention's entity id
    cases = {}
    if rules and seen.get("plans"):
        nodes = seen["nodes"]
        for k, p in seen["plans"].items():
            for (name, _, _), j in zip(p["cases"][1:], sorted(p.get("absorbed", ()))):
                cases.setdefault((nodes[k][1]["id"], name), nodes[j][0]["id"])
    out = []

    def add(head, tail):
        if head is not None and tail is not None and (head, tail) not in out:
            out.append((head, tail))

    def outcome(mention_id_or_span):
        """The head for a branch named by a mention: its condition, if it absorbed one."""
        head = span.get(mention_id_or_span, mention_id_or_span)
        conditions = folded.get(mention_id_or_span, [])
        if conditions:
            add(head, conditions[0])
            return conditions[0]
        return head

    for f in flows:
        source, tail = f["source"], span.get(f["target"])
        if source not in elements or source not in span:
            continue
        relation, name = f.get("relation", "SEQUENCE"), f.get("name", "")
        if not rules:
            add(span[source], tail)
        elif relation == "FALSE_BRANCH" and otherwise.get(source):
            add(outcome(otherwise[source][0]), tail)
        elif relation == "TRUE_BRANCH" and (source, name) in cases:
            add(outcome(cases[(source, name)]), tail)
        elif relation == "FALSE_BRANCH":
            add(span[source], tail)
        else:
            add(outcome(source), tail)
    return out


def _collapsed(flows, unnamed):
    """The flows with each path through gateways that stand for no mention
    replaced by a direct flow, keeping the first flow's relation and name."""
    if not unnamed:
        return flows
    after = defaultdict(list)
    for f in flows:
        after[f["source"]].append(f["target"])

    def reach(node, seen):
        out = []
        for target in after[node]:
            if target in unnamed and target not in seen:
                out += reach(target, seen | {target})
            elif target not in unnamed:
                out.append(target)
        return out

    out = []
    for f in flows:
        if f["source"] in unnamed:
            continue
        targets = reach(f["target"], {f["target"]}) if f["target"] in unnamed else [f["target"]]
        out += [{**f, "target": target} for target in targets]
    return out


def ours(folder, mode, jobs, replay=None):
    """{document: [("flow", head key, tail key)]}: by the four rules, by rule 1
    alone, and by the four rules with gateways that stand for no mention collapsed."""
    replay = replay or Replay(mode)
    rendered, plain, collapsed = {}, {}, {}
    for job in jobs:
        saved = json.loads((Path(folder) / "documents" / job["name"] / "process.json").read_text(encoding="utf-8"))
        seen = replay(job, saved)
        for target, rules, collapse in ((rendered, True, False), (plain, False, False), (collapsed, True, True)):
            relations = []
            for head, tail in render(seen, rules, collapse):
                relations.append(("flow", (head[0].lower(), head[1], head[2]), (tail[0].lower(), tail[1], tail[2])))
            target[job["name"]] = relations
    return rendered, plain, collapsed


# --- comparison ----------------------------------------------------------------------

def paired(a, b, documents):
    """F1(a) - F1(b), pooled over documents, with a 95% interval from resampling
    documents (seed 0)."""
    rng = random.Random(SEED)
    f1 = lambda rows, docs: pooled(rows, docs)["f1"]  # noqa: E731
    point = f1(a, documents) - f1(b, documents)
    draws = sorted(f1(a, s) - f1(b, s) for s in ([rng.choice(documents) for _ in documents]
                                                  for _ in range(RESAMPLES)))
    return {"difference": point, "ci95": [draws[int(0.025 * RESAMPLES)], draws[int(0.975 * RESAMPLES) - 1]]}


def compare(extra=()):
    """extra: further runs of ours, (label, folder, relation mode), each also set beside the method."""
    gold, folds = load_gold(), load_folds()
    jobs = json.loads(Path(PET_JOBS).read_text(encoding="utf-8"))["jobs"]
    systems, checks = {}, {"tab1b": {}, "table2": {}}
    for label, run in BASELINES.items():
        predicted = stored_baseline(run, folds)
        systems[label] = score(predicted, gold, folds)
        micro = fold_mean_micro(predicted, folds)
        checks["tab1b"][label] = {"rescored": micro, "published": PUBLISHED_TAB1B[run],
                                  "published_flow_f1": PUBLISHED_FLOW_F1.get(run)}
    for (model, shots), predicted in sorted(llm_answers(gold).items()):
        label = f"{model}, {shots}-shot"
        systems[label] = score(predicted, gold, folds)
        total = [0, 0, 0]
        for d in gold:  # every tag either side has, invented ones included, as their scorer counts
            for t in {r[0] for r in gold[d]["relations"]} | {r[0] for r in predicted.get(d, [])}:
                total = [a + b for a, b in zip(total, counts_2024(gold[d]["relations"], predicted.get(d, []), t))]
        checks["table2"][label] = {"rescored": prf(*total), "published": LLM_TABLE.get((model, shots))}
    for label, folder, mode in [*OURS, *extra]:
        rendered, plain, collapsed = ours(folder, mode, jobs)
        systems[label] = score(rendered, gold, folds)
        systems[f"{label}, rule 1 only"] = score(plain, gold, folds)
        if collapsed != rendered:  # only the pairwise mode inserts gateways that stand for no mention
            systems[f"{label}, inserted gateways collapsed"] = score(collapsed, gold, folds)
    documents = sorted(gold)
    method = systems[METHOD]["per_document"]
    differences = {f"method − {other}": paired(method, systems[other]["per_document"], documents)
                   for other in PAIRED if other in systems}
    for label, _, _ in extra:
        differences[f"{label} − method"] = paired(systems[label]["per_document"], method, documents)
        for other in PAIRED:
            if other in systems:
                differences[f"{label} − {other}"] = paired(systems[label]["per_document"],
                                                           systems[other]["per_document"], documents)
    return {"systems": {k: {m: v[m] for m in ("pooled", "folds")} for k, v in systems.items()},
            "checks": checks, "differences": differences,
            "gold_flows": sum(1 for d in gold for r in gold[d]["relations"] if r[0] == "flow")}


def fold_mean_micro(predicted, folds):
    """CoopIS 2023's overall score: micro over tags on each fold, averaged over folds."""
    scores = []
    for docs in folds:
        total = [0, 0, 0]
        for d, truth in docs.items():
            for tag in {r[0] for r in truth["relations"]} | {r[0] for r in predicted.get(d, [])}:
                for k, v in enumerate(counts_2023(truth["relations"], predicted.get(d, []), tag)):
                    total[k] += v
        scores.append(prf(*total))
    return {k: sum(s[k] for s in scores) / len(scores) for k in ("p", "r", "f1")}


def markdown(result):
    lines = ["# Flow relations on PET under Neuberger et al.'s strict scorer", "",
             "Generated by `text2bpmn/pet_strict.py`. Flow relations only, gold entities, exact matching of both "
             f"arguments ({result['gold_flows']} gold Flow relations in 45 documents). *Folds*: CoopIS 2023's "
             "protocol, P, R and F1 on each of their five test folds, averaged. *Pooled*: ER 2024's, counts "
             "summed over the 45 documents. Prior systems are rescored from their own stored outputs.", "",
             "| system | folds P | R | F1 | pooled P | R | F1 |", "|---|---|---|---|---|---|---|"]
    for name, s in result["systems"].items():
        f, p = s["folds"], s["pooled"]
        lines.append(f"| {name} | {f['p']:.3f} | {f['r']:.3f} | **{f['f1']:.3f}** | {p['p']:.3f} | {p['r']:.3f} | "
                     f"**{p['f1']:.3f}** |")
    lines += ["", f"Differences in pooled F1, paired bootstrap over documents ({RESAMPLES} resamples, "
              f"seed {SEED}); *method* is {METHOD}:", ""]
    for what, d in result["differences"].items():
        lines.append(f"- {what}: {d['difference']:+.3f} [{d['ci95'][0]:+.3f}, {d['ci95'][1]:+.3f}]")
    lines += ["", "**Read with:**", "",
              "- **BoostRelEx**: its stored predictions are not those of the published run (overall "
              "0.790 against Tab. 1b's 0.82; CatBoost training is not deterministic). The published Flow F1 is "
              "0.79 (Fig. 7c), with no P or R.",
              "- **What each system saw of PET**: BoostRelEx was trained on the other four folds; a k-shot LLM "
              "row had the k most similar other PET documents, with their gold relations, as examples; "
              "RuleRelEx's rules were written for PET. The method has no PET example in its prompt, but its "
              "relation stage was revised after looking at its errors on PET (provenance/"
              "relation_stage_2026-11-11.md), so PET is partly its development set.",
              "- **The four rules** were fixed before the first score; *rule 1 only* shows what they account for. "
              "They write the model's own structure in PET's conventions (a condition between a decision and its "
              "branch, an else-marker heading the other branch) and add nothing the model does not say.",
              "- **Folds** for the LLM rows partition their pooled run by CoopIS 2023's folds; ER 2024 reported "
              "pooled scores. The method, the text order and the LLMs used no training split, so their two "
              "columns differ only in the averaging.", ""]
    lines += ["", "The scorers reproduce what was published, from the published systems' stored outputs "
              "(overall, all relation types):", "", "| system | rescored P / R / F1 | published |", "|---|---|---|"]
    for label, c in result["checks"]["tab1b"].items():
        r = c["rescored"]
        lines.append(f"| {label} (CoopIS 2023, Tab. 1b) | {r['p']:.3f} / {r['r']:.3f} / {r['f1']:.3f} | "
                     f"{' / '.join(f'{v:.2f}' for v in c['published'])}"
                     + (f"; Flow F1 {c['published_flow_f1']:.2f} (Fig. 7c)" if c["published_flow_f1"] else "") + " |")
    for label, c in result["checks"]["table2"].items():
        r = c["rescored"]
        published = " / ".join(f"{v:.2f}" for v in c["published"]) if c["published"] else "–"
        lines.append(f"| {label} (ER 2024) | {r['p']:.3f} / {r['r']:.3f} / {r['f1']:.3f} | {published} |")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fetch", action="store_true", help="download and check their files")
    ap.add_argument("--arm", nargs=3, action="append", default=[], metavar=("LABEL", "FOLDER", "MODE"),
                    help="score another PET run of ours as well (with --out)")
    ap.add_argument("--out", help=f"report path without suffix (default {OUT})")
    args = ap.parse_args()
    if args.fetch:
        fetch()
        return
    if args.arm and not args.out:
        raise SystemExit("--arm writes to its own report: give --out")
    result = compare([tuple(a) for a in args.arm])
    out = Path(args.out) if args.out else OUT
    out.with_suffix(".json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    text = markdown(result)
    out.with_suffix(".md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
