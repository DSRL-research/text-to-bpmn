"""Measure the pipeline's attachment rules against PET's own relations.

    python3 -m text2bpmn.pet_rules_eval [--data pet_data/PETv1.1-relations.json]
        [--json OUT.json] [--markdown OUT.md]

The pipeline decides four things by rule rather than by model, and until now
each was judged by eye on three case studies:

| rule | what it decides | PET relation | instances |
|---|---|---|---|
| `_assign_lanes` | which actor performs an activity | `actor performer` | 399 |
| `_is_recipient` | which actor is only the recipient | `actor recipient` | 166 |
| `_metadata_owners` | which activity an object belongs to | `uses` | 486 |
| `_metadata_owners` | which activity a further specification belongs to | `further specification` | 64 |
| `_attach_conditions` | which gateway a condition qualifies | `flow`, gateway to condition | 80 |

PET annotates all of them, 45 documents' worth. This feeds PET's **gold**
entity spans to the rules, so what is measured is the rule and not the entity
recogniser: an error here is the pipeline's own reasoning, not a missed span.

Scores are per rule: a decision counts as correct when it names the same pair
PET annotates. A rule that declines to decide counts as a miss, never as a
free pass.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

RELATIONS = ("actor performer", "actor recipient", "uses", "further specification")
PET_DEFAULT = "pet_data/PETv1.1-relations.json"


def load_documents(path=PET_DEFAULT):
    """Each document as its text, its gold spans and its gold relation pairs.

    Spans carry the shape finder3 works with, offset into the tokens joined by
    single spaces, plus the sentence each came from so the rules can see
    sentence boundaries exactly as they do in the pipeline.
    """
    documents = []
    for document in json.loads(Path(path).read_text(encoding="utf-8")):
        tokens, tags = document["tokens"], document["ner_tags"]
        sentence_ids, word_ids = document["sentence-IDs"], document["tokens-IDs"]
        text, starts, offset = " ".join(tokens), [], 0
        for token in tokens:
            starts.append(offset)
            offset += len(token) + 1

        spans, current, by_head = [], None, {}
        for index, tag in enumerate(tags):
            if tag == "O":
                current = None
                continue
            prefix, _, label = tag.partition("-")
            if prefix == "B" or current is None or current["entity_group"] != label:
                current = {"entity_group": label, "start": starts[index],
                           "end": starts[index] + len(tokens[index]),
                           "word": tokens[index], "score": 1.0,
                           "sentence": sentence_ids[index]}
                spans.append(current)
                by_head[(sentence_ids[index], word_ids[index])] = current
            else:
                current["end"] = starts[index] + len(tokens[index])
                current["word"] = text[current["start"]:current["end"]]

        pairs = []
        for relation in document["relations"]:
            source = by_head.get((relation["source-head-sentence-ID"],
                                  relation["source-head-word-ID"]))
            target = by_head.get((relation["target-head-sentence-ID"],
                                  relation["target-head-word-ID"]))
            if source is not None and target is not None:
                pairs.append((relation["relation-type"], source, target))
        documents.append({"name": document["document name"], "text": text,
                          "spans": spans, "relations": pairs})
    return documents


def _extractor():
    """finder3's rules without its models: the rules need only spaCy."""
    import spacy

    from text2bpmn.finder3 import BPMNHybridExtractor
    from text2bpmn.run_config import RunConfig

    extractor = BPMNHybridExtractor.__new__(BPMNHybridExtractor)
    extractor.config = RunConfig()
    extractor.nlp_validator = spacy.load("en_core_web_sm")
    extractor.dspy_predictor = None
    return extractor


def _prepared(extractor, document):
    """The spans as the pipeline has them when the rules run: cleaned, typed."""
    from text2bpmn.finder3 import CONDITION_LABELS

    spans = [dict(span) for span in document["spans"]]
    for index, span in enumerate(spans):
        span["id"] = index
        if span["entity_group"] in ("Activity", "TASK"):
            span["clean_name"] = extractor._clean_and_validate_activity(span["word"])
        else:
            span["clean_name"] = extractor._clean_name(span["word"])
        if span["entity_group"] in ("XOR Gateway", *CONDITION_LABELS):
            span["type"] = "exclusiveGateway"
        elif span["entity_group"] in ("AND Gateway", "Parallel Gateway"):
            span["type"] = "parallelGateway"
        elif span["entity_group"] in ("Actor", "AGENT"):
            span["type"] = "Lane"
        else:
            span["type"] = "task"
    return spans


def _prf(tp, fp, fn):
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(precision, 3),
            "recall": round(recall, 3), "f1": round(f1, 3)}


def evaluate(path=PET_DEFAULT):
    extractor = _extractor()
    documents = load_documents(path)

    scores = {name: Counter() for name in
              ("lane", "lane_by_name", "recipient", "object", "further specification",
               "condition")}
    mistakes = {name: [] for name in scores}

    for document in documents:
        spans = _prepared(extractor, document)
        text = document["text"]
        key = lambda span: (span["start"], span["end"])
        gold = {name: set() for name in RELATIONS}
        gold_pairs = {name: {} for name in RELATIONS}
        for relation, source, target in document["relations"]:
            if relation in gold:
                gold[relation].add((key(source), key(target)))
                gold_pairs[relation].setdefault(key(source), set()).add(key(target))

        # --- the lane rule, and the recipient exclusion inside it
        extractor._assign_lanes(spans, text)
        actors = {key(s): s for s in spans if s["type"] == "Lane"}
        for span in spans:
            if span["entity_group"] not in ("Activity", "TASK"):
                continue
            expected = gold_pairs["actor performer"].get(key(span), set())
            if not expected:
                continue
            picked = span.get("lane_actor")
            chosen = next((key(s) for s in spans if s.get("id") == picked), None) \
                if picked is not None else None
            # the lane a reader sees is the actor's name, so a different mention
            # of the same actor is the same lane; both readings are reported
            names = {actors[e]["clean_name"] for e in expected if e in actors}
            chosen_name = span.get("lane_hint")
            if chosen in expected:
                scores["lane"]["tp"] += 1
                scores["lane_by_name"]["tp"] += 1
            elif chosen is None:
                scores["lane"]["fn"] += 1
                scores["lane_by_name"]["fn"] += 1
                mistakes["lane"].append((document["name"], span["word"], "no actor chosen"))
            elif chosen_name in names:
                scores["lane"]["fp"] += 1          # right actor, another mention of it
                scores["lane_by_name"]["tp"] += 1
            else:
                scores["lane"]["fp"] += 1
                scores["lane_by_name"]["fp"] += 1
                mistakes["lane_by_name"].append(
                    (document["name"], span["word"],
                     f"chose {chosen_name!r}, PET says {sorted(names)}"))

        # a span PET calls a recipient should have been excluded as a performer
        recipients = {t for _, t in gold["actor recipient"]}
        performers = {t for _, t in gold["actor performer"]}
        for span_key, actor in actors.items():
            only_recipient = span_key in recipients and span_key not in performers
            flagged = bool(actor.get("recipient"))
            if only_recipient and flagged:
                scores["recipient"]["tp"] += 1
            elif only_recipient:
                scores["recipient"]["fn"] += 1
                mistakes["recipient"].append((document["name"], actor["word"],
                                              "not excluded, PET calls it only a recipient"))
            elif flagged and span_key in performers:
                scores["recipient"]["fp"] += 1
                mistakes["recipient"].append((document["name"], actor["word"],
                                              "excluded, but PET calls it a performer"))

        # --- object and further-specification attachment
        owners = extractor._metadata_owners(spans, text)
        for index, owner in owners.items():
            span = spans[index]
            relation = "uses" if span["entity_group"] == "Activity Data" \
                else "further specification" if span["entity_group"] == "Further Specification" \
                else None
            if relation is None:
                continue
            name = "object" if relation == "uses" else "further specification"
            expected = {s for s, t in gold[relation] if t == key(span)}
            if not expected:
                continue
            if key(spans[owner]) in expected:
                scores[name]["tp"] += 1
            else:
                scores[name]["fp"] += 1
                mistakes[name].append((document["name"], span["word"],
                                       f"attached to {spans[owner]['word']!r}"))
        attached = {key(spans[i]) for i in owners}
        for relation, name in (("uses", "object"),
                               ("further specification", "further specification")):
            for _, target in gold[relation]:
                if target not in attached:
                    scores[name]["fn"] += 1

        # --- condition folding: which gateway a condition qualifies
        conditions = [(s, t) for kind, s, t in document["relations"]
                      if kind == "flow" and s["entity_group"] == "XOR Gateway"
                      and t["entity_group"] == "Condition Specification"]
        if conditions:
            folded = extractor._attach_conditions([dict(s) for s in spans])
            kept = {(s["start"], s["end"]) for s in folded}
            for gateway, condition in conditions:
                # the rule folds a condition into the gateway before it; correct
                # when that condition is no longer a node of its own and the
                # gateway it joined is the annotated one
                gone = key(condition) not in kept
                nearest = max((s for s in spans if s["type"] == "exclusiveGateway"
                               and s["start"] < condition["start"]),
                              key=lambda s: s["start"], default=None)
                if gone and nearest is not None and key(nearest) == key(gateway):
                    scores["condition"]["tp"] += 1
                elif gone:
                    scores["condition"]["fp"] += 1
                    mistakes["condition"].append(
                        (document["name"], condition["word"],
                         f"folded into {nearest['word'] if nearest else None!r}, "
                         f"PET says {gateway['word']!r}"))
                else:
                    scores["condition"]["fn"] += 1

    result = {"data": str(path), "documents": len(documents),
              "rules": {name: _prf(c["tp"], c["fp"], c["fn"]) for name, c in scores.items()},
              "examples_of_error": {name: m[:6] for name, m in mistakes.items()}}
    return result


def to_markdown(result):
    titles = {"lane": "which actor performs an activity, exact mention",
              "lane_by_name": "which actor performs an activity, by actor name",
              "recipient": "actor excluded as only a recipient (`actor recipient`)",
              "object": "which activity an object belongs to (`uses`)",
              "further specification": "which activity a further specification belongs to",
              "condition": "which gateway a condition qualifies (`flow`)"}
    lines = [f"The pipeline's attachment rules against PET's own relations, "
             f"{result['documents']} documents, PET's gold entity spans as input "
             f"so the rule is measured and not the recogniser.", "",
             "| Rule | TP | FP | FN | Precision | Recall | F1 |", "|---|---|---|---|---|---|---|"]
    for name, scores in result["rules"].items():
        lines.append(f"| {titles.get(name, name)} | {scores['tp']} | {scores['fp']} | "
                     f"{scores['fn']} | {scores['precision']} | {scores['recall']} | "
                     f"{scores['f1']} |")
    for name, errors in result["examples_of_error"].items():
        if errors:
            lines += ["", f"**{titles.get(name, name)}** — examples of what it got wrong:"]
            for document, span, detail in errors:
                lines.append(f"- {document}: {span!r} — {detail}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", default=PET_DEFAULT)
    ap.add_argument("--json")
    ap.add_argument("--markdown")
    args = ap.parse_args()
    result = evaluate(args.data)
    text = to_markdown(result)
    print(text)
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n✅ Wrote {args.json}")
    if args.markdown:
        Path(args.markdown).write_text(text + "\n", encoding="utf-8")
        print(f"✅ Wrote {args.markdown}")


if __name__ == "__main__":
    main()
