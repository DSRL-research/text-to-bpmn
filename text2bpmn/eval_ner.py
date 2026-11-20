"""One entity-recognition evaluator, over character-offset spans.

    python3 -m text2bpmn.eval_ner --model PATH [--data pet_test.json]
        [--json OUT.json] [--markdown OUT.md] [--seqeval]

The published figures are accuracy 93.6% and F1 0.89, from
`evaluate.load("seqeval")` in process-visualizer/src/token_classification_alex/
train.py. In that library `overall_accuracy` is **token-level**: every token
counts, and most tokens are O, so a model that found no entity at all would
still score well. It is not comparable with a span-based result, and it is not
what a BPMN element depends on -- a half-matched span is not a usable activity.

This evaluator takes both gold and predictions as character spans,
[{start, end, label, score}], and reports:

- **strict** entity-level precision, recall and F1: the span must have the same
  start, the same end and the same label.
- **relaxed**: the same label and a character IoU of at least 0.5, so a span
  that caught the activity but took one word too many still counts.
- **token-level accuracy** over BIO tags, computed the way seqeval computes it,
  so the published number stays traceable -- and beside it the same accuracy
  over the tokens that carry an entity, which is what the O tags were hiding.

Both criteria match one-to-one, by optimal assignment, so one predicted span
can never satisfy two gold spans.

Predictions keep the offsets the token-classification pipeline returns with
`aggregation_strategy="simple"`. They deliberately do not pass through
finder3's `_clean_and_validate_activity` or `_clean_name`: those rewrite the
text of a span without moving its offsets, which would make every comparison
here meaningless.
"""
import argparse
import json
import random
from collections import Counter
from pathlib import Path

from scipy.optimize import linear_sum_assignment

RELAXED_IOU = 0.5
BOOTSTRAP_RESAMPLES = 1000


# --- the span shape, from either source -------------------------------------

def spans_from_bio(tokens, tags):
    """Gold spans from PET's token-and-BIO-tag annotation.

    The text is the tokens joined by single spaces, which is also the text the
    model is given, so the offsets refer to the same string on both sides.
    """
    text, spans, offset = " ".join(tokens), [], 0
    starts = []
    for token in tokens:
        starts.append(offset)
        offset += len(token) + 1

    current = None
    for index, (token, tag) in enumerate(zip(tokens, tags)):
        if tag == "O":
            current = None
            continue
        prefix, _, label = tag.partition("-")
        start, end = starts[index], starts[index] + len(token)
        # an I- tag whose label differs, or which follows no B-, starts a span:
        # the alternative is to drop the annotation
        if prefix == "B" or current is None or current["label"] != label:
            current = {"start": start, "end": end, "label": label, "score": 1.0,
                       "tokens": [token]}
            spans.append(current)
        else:
            current["end"] = end
            current["tokens"].append(token)
    return text, spans


def spans_from_pipeline(pipeline, text):
    """Predicted spans, with the pipeline's own offsets and nothing cleaned."""
    return [{"start": int(entity["start"]), "end": int(entity["end"]),
             "label": entity["entity_group"], "score": float(entity["score"]),
             "tokens": text[int(entity["start"]):int(entity["end"])].split()}
            for entity in pipeline(text)]


def load_pet(path):
    """[(text, gold spans, tokens, tags)] for a split, in either shape: the PET
    splits are a JSON array, the training files are JSON lines."""
    text = Path(path).read_text(encoding="utf-8")
    try:
        records = json.loads(text)
    except json.JSONDecodeError:
        records = [json.loads(line) for line in text.splitlines() if line.strip()]
    out = []
    for record in records:
        text, spans = spans_from_bio(record["tokens"], record["ner_tags"])
        out.append((text, spans, record["tokens"], record["ner_tags"]))
    return out


# --- matching ---------------------------------------------------------------

def iou(first, second):
    """Character intersection over union of two spans."""
    overlap = max(0, min(first["end"], second["end"]) - max(first["start"], second["start"]))
    union = max(first["end"], second["end"]) - min(first["start"], second["start"])
    return overlap / union if union else 0.0


def is_strict(gold, predicted):
    return (gold["start"], gold["end"], gold["label"]) == \
           (predicted["start"], predicted["end"], predicted["label"])


def is_relaxed(gold, predicted, threshold=RELAXED_IOU):
    return gold["label"] == predicted["label"] and iou(gold, predicted) >= threshold


def match(gold_spans, predicted_spans, criterion, threshold=RELAXED_IOU):
    """One-to-one pairs of (gold index, predicted index) under the criterion.

    An optimal assignment, so a predicted span that could satisfy two gold
    spans is credited for one of them only. Ties are broken towards the larger
    overlap, which matters only for the relaxed criterion.
    """
    if not gold_spans or not predicted_spans:
        return []
    eligible = is_strict if criterion == "strict" else \
        (lambda g, p: is_relaxed(g, p, threshold))
    costs = [[-(iou(gold, predicted) + 1.0) if eligible(gold, predicted) else 0.0
              for predicted in predicted_spans] for gold in gold_spans]
    rows, columns = linear_sum_assignment(costs)
    return [(int(row), int(column)) for row, column in zip(rows, columns)
            if eligible(gold_spans[row], predicted_spans[column])]


# --- metrics ----------------------------------------------------------------

def _prf(tp, fp, fn):
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(precision, 3),
            "recall": round(recall, 3), "f1": round(f1, 3)}


def document_counts(gold_spans, predicted_spans, criterion, threshold=RELAXED_IOU):
    """One document's true and false positives and negatives, per label.

    Matching is over every span, whatever its label; a label scope is applied
    when counting, so restricting the scope never changes which spans matched.
    """
    pairs = match(gold_spans, predicted_spans, criterion, threshold)
    matched_gold = {g for g, _ in pairs}
    matched_predicted = {p for _, p in pairs}
    tp, fp, fn = Counter(), Counter(), Counter()
    for g, _ in pairs:
        tp[gold_spans[g]["label"]] += 1
    for index, span in enumerate(gold_spans):
        if index not in matched_gold:
            fn[span["label"]] += 1
    for index, span in enumerate(predicted_spans):
        if index not in matched_predicted:
            fp[span["label"]] += 1
    return tp, fp, fn


def entity_level(documents, criterion, threshold=RELAXED_IOU, scope=None):
    """Per-label, micro and macro scores under one matching criterion.

    `documents` is [(gold spans, predicted spans)]. `scope` fixes the labels
    that are scored, so every model is averaged over the same set; a prediction
    whose label falls outside it is reported separately rather than counted as
    a false positive of a class nobody is scoring.
    """
    counts = [document_counts(gold, predicted, criterion, threshold)
              for gold, predicted in documents]
    tp = sum((c[0] for c in counts), Counter())
    fp = sum((c[1] for c in counts), Counter())
    fn = sum((c[2] for c in counts), Counter())

    labels = sorted(scope) if scope is not None else sorted(set(tp) | set(fp) | set(fn))
    outside = {label: fp[label] for label in sorted(set(fp) - set(labels)) if fp[label]}
    per_label = {}
    for label in labels:
        per_label[label] = _prf(tp[label], fp[label], fn[label])
        per_label[label]["support"] = tp[label] + fn[label]
    micro = _prf(sum(tp[l] for l in labels), sum(fp[l] for l in labels),
                 sum(fn[l] for l in labels))
    macro = {key: round(sum(per_label[l][key] for l in labels) / len(labels), 3)
             if labels else 0.0 for key in ("precision", "recall", "f1")}
    return {"criterion": criterion, "scope": labels, "per_label": per_label,
            "micro": micro, "macro": macro,
            "predictions_outside_the_scope": outside}


def bootstrap_micro_f1(documents, criterion, threshold=RELAXED_IOU, scope=None,
                       resamples=BOOTSTRAP_RESAMPLES, seed=0):
    """A percentile confidence interval for micro F1, resampling sentences.

    With 42 sentences a per-class figure of six spans says little; this says
    how much of the difference between two models the test set can support.
    Counts come from the matching already done, so no model is run again.
    """
    counts = [document_counts(gold, predicted, criterion, threshold)
              for gold, predicted in documents]
    labels = set(scope) if scope is not None else \
        {label for c in counts for counter in c for label in counter}

    def micro_f1(indices):
        tp = fp = fn = 0
        for index in indices:
            tp += sum(counts[index][0][l] for l in labels)
            fp += sum(counts[index][1][l] for l in labels)
            fn += sum(counts[index][2][l] for l in labels)
        return _prf(tp, fp, fn)["f1"]

    rng = random.Random(seed)
    size = len(counts)
    draws = sorted(micro_f1([rng.randrange(size) for _ in range(size)])
                   for _ in range(resamples))
    return {"point": micro_f1(range(size)),
            "mean": round(sum(draws) / len(draws), 3),
            "ci95_low": draws[int(0.025 * len(draws))],
            "ci95_high": draws[min(int(0.975 * len(draws)), len(draws) - 1)],
            "resamples": resamples, "seed": seed, "sentences": size}


def bio_tags(tokens, spans):
    """BIO tags for these tokens under these spans, for the token-level view."""
    starts, offset = [], 0
    for token in tokens:
        starts.append((offset, offset + len(token)))
        offset += len(token) + 1
    tags = []
    for start, end in starts:
        covering = next((s for s in spans if s["start"] < end and start < s["end"]), None)
        if covering is None:
            tags.append("O")
        else:
            tags.append(("B-" if start <= covering["start"] else "I-") + covering["label"])
    return tags


def token_level(documents):
    """Accuracy over BIO tags, as seqeval computes it, and over entity tokens only."""
    total = correct = entity_total = entity_correct = 0
    for gold_tags, predicted_tags in documents:
        for gold, predicted in zip(gold_tags, predicted_tags):
            total += 1
            correct += gold == predicted
            if gold != "O":
                entity_total += 1
                entity_correct += gold == predicted
    return {"tokens": total,
            "accuracy": round(correct / total, 3) if total else 0.0,
            "entity_tokens": entity_total,
            "accuracy_on_entity_tokens": round(entity_correct / entity_total, 3)
            if entity_total else 0.0,
            "share_of_tokens_that_are_O": round(1 - entity_total / total, 3) if total else 0.0}


def load_predictions(path, sentences, score_threshold=None):
    """Predicted spans saved by a baseline run, aligned to the data's order.

    Scores are kept in the file so a threshold can be applied here rather than
    by running the model again, which is what keeps a held-out set to one pass.
    """
    saved = json.loads(Path(path).read_text(encoding="utf-8"))
    documents = saved["documents"] if isinstance(saved, dict) else saved
    if len(documents) != sentences:
        raise ValueError(f"{path} holds {len(documents)} sentences, the data has {sentences}")
    out = []
    for document in documents:
        spans = document["spans"]
        if score_threshold is not None:
            spans = [s for s in spans if s.get("score", 1.0) >= score_threshold]
        out.append([{k: s[k] for k in ("start", "end", "label", "score") if k in s}
                    for s in spans])
    return out


def assemble(data_path, predicted_documents, scope=None, emittable=None,
             threshold=RELAXED_IOU, bootstrap=BOOTSTRAP_RESAMPLES, seed=0,
             with_seqeval=False, model_name="predictions"):
    """Score predicted spans against a split, over a fixed label scope.

    `emittable` names the labels the model can produce at all. Those it cannot
    are reported with their support and left out of a second pair of averages,
    so a model is never credited or punished for a class it has no way of
    emitting.
    """
    gold = load_pet(data_path)
    spans, tags = [], []
    for (text, gold_spans, tokens, gold_tags), predicted in zip(gold, predicted_documents):
        spans.append((gold_spans, predicted))
        tags.append((list(gold_tags), bio_tags(tokens, predicted)))

    in_data = Counter(span["label"] for gold_spans, _ in spans for span in gold_spans)
    scope = sorted(scope) if scope is not None else sorted(in_data)
    cannot_emit = sorted(set(scope) - set(emittable)) if emittable is not None else []
    emitted_scope = [label for label in scope if label not in cannot_emit]

    result = {
        "model": model_name,
        "data": str(data_path),
        "sentences": len(spans),
        "gold_spans": sum(len(g) for g, _ in spans),
        "predicted_spans": sum(len(p) for _, p in spans),
        "label_scope": scope,
        "labels_the_model_can_emit": sorted(emittable) if emittable is not None else None,
        "cannot_emit": cannot_emit,
        "relaxed_iou_threshold": threshold,
        "token_level": token_level(tags),
    }
    for criterion in ("strict", "relaxed"):
        block = entity_level(spans, criterion, threshold, scope)
        block["micro_over_emittable_labels"] = entity_level(
            spans, criterion, threshold, emitted_scope)["micro"] if cannot_emit else block["micro"]
        block["macro_over_emittable_labels"] = entity_level(
            spans, criterion, threshold, emitted_scope)["macro"] if cannot_emit else block["macro"]
        if bootstrap:
            block["bootstrap_micro_f1"] = bootstrap_micro_f1(
                spans, criterion, threshold, scope, bootstrap, seed)
            if cannot_emit:
                block["bootstrap_micro_f1_over_emittable_labels"] = bootstrap_micro_f1(
                    spans, criterion, threshold, emitted_scope, bootstrap, seed)
        result[criterion] = block
    if with_seqeval:
        result["seqeval"] = _seqeval(tags)
    return result


def save_spans(model_path, data_path, out_path):
    """Run a checkpoint once and save its spans in the shape a baseline run
    saves them, so a fine-tuned model and a zero-shot one are scored by exactly
    the same code afterwards."""
    import torch
    from transformers import AutoModelForTokenClassification, AutoTokenizer, pipeline

    model = AutoModelForTokenClassification.from_pretrained(model_path)
    recogniser = pipeline("token-classification", model=model,
                          tokenizer=AutoTokenizer.from_pretrained(model_path),
                          aggregation_strategy="simple",
                          device=0 if torch.cuda.is_available() else -1)
    emits = sorted({label.split("-", 1)[-1] for label in model.config.id2label.values()} - {"O"})
    documents = []
    for index, (text, _, _, _) in enumerate(load_pet(data_path)):
        documents.append({"id": f"{Path(data_path).stem}#{index}", "text": text,
                          "spans": spans_from_pipeline(recogniser, text)})
    record = {"model": str(model_path), "api": "transformers token-classification",
              "aggregation_strategy": "simple", "data": str(data_path),
              "labels_the_model_can_emit": emits,
              "sentences": len(documents),
              "spans": sum(len(d["spans"]) for d in documents)}
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps({"run": record, "documents": documents},
                                         indent=1, ensure_ascii=False), encoding="utf-8")
    return record


def pet_match(gold_tokens, predicted_tokens, relax_window=1):
    """PET's own matching rule, read from `petbenchmarks` 0.0.2.

    Two spans match when their token lists are equal, or when one is the other
    with up to `relax_window` words missing from the left end, the right end, or
    both. That is stricter than a character overlap: "the acceptance pack" and
    "acceptance pack" match, "the invoice with payment advice" and "the invoice"
    do not.
    """
    if gold_tokens == predicted_tokens:
        return True
    gold, predicted = list(gold_tokens), list(predicted_tokens)
    for left in range(relax_window + 1):
        for right in range(relax_window + 1):
            if left == right == 0:
                continue
            if gold[left:len(gold) - right or None] == predicted:
                return True
            if predicted[left:len(predicted) - right or None] == gold:
                return True
    return False


def pet_protocol(documents, scope=None, relax_window=1):
    """Scores the way PET's benchmark does: per document, then averaged over
    documents, with PET's matching rule.

    `documents` is [(gold spans, predicted spans)] for one document each, every
    span carrying its `tokens`. PET averages each class's precision, recall and
    F1 across documents, so a two-sentence document counts as much as a
    thirty-four-sentence one; a micro average over spans does not.
    """
    labels = sorted(scope) if scope is not None else sorted(
        {s["label"] for gold, _ in documents for s in gold})
    per_document = []
    for gold, predicted in documents:
        scores = {}
        for label in labels:
            golds = [s for s in gold if s["label"] == label]
            preds = [s for s in predicted if s["label"] == label]
            taken, tp = set(), 0
            for g in golds:
                for index, p in enumerate(preds):
                    if index in taken:
                        continue
                    if pet_match(g["tokens"], p["tokens"], relax_window):
                        taken.add(index)
                        tp += 1
                        break
            scores[label] = _prf(tp, len(preds) - tp, len(golds) - tp)
        per_document.append(scores)

    averaged = {}
    for label in labels:
        rows = [d[label] for d in per_document]
        # PET averages over every document, including those without the class
        averaged[label] = {key: round(sum(r[key] for r in rows) / len(rows), 3)
                           for key in ("precision", "recall", "f1")}
        averaged[label]["support"] = sum(r["tp"] + r["fn"] for r in rows)
    macro = {key: round(sum(averaged[l][key] for l in labels) / len(labels), 3)
             for key in ("precision", "recall", "f1")}
    return {"protocol": "petbenchmarks 0.0.2: token match relaxed by "
                        f"{relax_window} word, averaged over documents",
            "documents": len(per_document), "per_label": averaged, "macro": macro}


def bootstrap_difference(first_documents, second_documents, criterion="strict",
                         threshold=RELAXED_IOU, scope=None,
                         resamples=BOOTSTRAP_RESAMPLES, seed=0):
    """A paired interval for the difference in micro F1 between two models.

    Both models are scored on the same sentences, so the sentences are resampled
    once and both models are rescored on that same resample. Comparing one
    model's interval with the other's is needlessly conservative: it throws away
    the pairing, which is most of the information when the test set is 42
    sentences.
    """
    labels = set(scope) if scope is not None else None

    def counts_of(documents):
        return [document_counts(gold, predicted, criterion, threshold)
                for gold, predicted in documents]

    first, second = counts_of(first_documents), counts_of(second_documents)
    if len(first) != len(second):
        raise ValueError("the two models were scored on different numbers of sentences")

    def micro(counts, indices):
        keys = labels if labels is not None else \
            {label for c in counts for counter in c for label in counter}
        tp = sum(counts[i][0][l] for i in indices for l in keys)
        fp = sum(counts[i][1][l] for i in indices for l in keys)
        fn = sum(counts[i][2][l] for i in indices for l in keys)
        return _prf(tp, fp, fn)["f1"]

    rng = random.Random(seed)
    size = len(first)
    whole = range(size)
    point = micro(first, whole) - micro(second, whole)
    draws = []
    for _ in range(resamples):
        indices = [rng.randrange(size) for _ in range(size)]
        draws.append(micro(first, indices) - micro(second, indices))
    draws.sort()
    favouring_first = sum(d > 0 for d in draws)
    return {"difference": round(point, 3),
            "ci95_low": round(draws[int(0.025 * len(draws))], 3),
            "ci95_high": round(draws[min(int(0.975 * len(draws)), len(draws) - 1)], 3),
            "resamples_favouring_first": favouring_first,
            "share_favouring_first": round(favouring_first / len(draws), 3),
            "excludes_zero": draws[int(0.025 * len(draws))] > 0,
            "resamples": resamples, "seed": seed, "sentences": size}


def evaluate(model_path, data_path, threshold=RELAXED_IOU, with_seqeval=False):
    import torch
    from transformers import AutoModelForTokenClassification, AutoTokenizer, pipeline

    model = AutoModelForTokenClassification.from_pretrained(model_path)
    recogniser = pipeline("token-classification", model=model,
                          tokenizer=AutoTokenizer.from_pretrained(model_path),
                          aggregation_strategy="simple",
                          device=0 if torch.cuda.is_available() else -1)
    emits = {label.split("-", 1)[-1] for label in model.config.id2label.values()} - {"O"}

    spans, tags = [], []
    for text, gold_spans, tokens, gold_tags in load_pet(data_path):
        predicted = spans_from_pipeline(recogniser, text)
        spans.append((gold_spans, predicted))
        tags.append(([t for t in gold_tags], bio_tags(tokens, predicted)))

    in_data = Counter(span["label"] for gold, _ in spans for span in gold)
    result = {
        "model": str(model_path),
        "data": str(data_path),
        "sentences": len(spans),
        "gold_spans": sum(len(gold) for gold, _ in spans),
        "predicted_spans": sum(len(predicted) for _, predicted in spans),
        "labels_the_model_can_emit": sorted(emits),
        "labels_in_the_data": sorted(in_data),
        "cannot_emit": sorted(set(in_data) - emits),
        "relaxed_iou_threshold": threshold,
        "strict": entity_level(spans, "strict"),
        "relaxed": entity_level(spans, "relaxed", threshold),
        "token_level": token_level(tags),
    }
    if with_seqeval:
        result["seqeval"] = _seqeval(tags)
    return result


def _seqeval(tag_documents):
    """seqeval's own overall numbers on the same data, for traceability with
    the published figures."""
    try:
        from seqeval.metrics import accuracy_score, f1_score, precision_score, recall_score
    except ImportError:
        return {"error": "seqeval is not installed"}
    gold = [g for g, _ in tag_documents]
    predicted = [p for _, p in tag_documents]
    return {"overall_precision": round(precision_score(gold, predicted, zero_division=0), 3),
            "overall_recall": round(recall_score(gold, predicted, zero_division=0), 3),
            "overall_f1": round(f1_score(gold, predicted, zero_division=0), 3),
            "overall_accuracy": round(accuracy_score(gold, predicted), 3)}


def to_markdown(result):
    token = result["token_level"]
    lines = [f"`{Path(result['model']).name}` on {result['sentences']} sentences of "
             f"{Path(result['data']).name}: {result['gold_spans']} gold spans, "
             f"{result['predicted_spans']} predicted.", "",
             f"Token-level accuracy over BIO tags **{token['accuracy']}** "
             f"({token['tokens']} tokens, {token['share_of_tokens_that_are_O']} of them O), "
             f"against **{token['accuracy_on_entity_tokens']}** over the "
             f"{token['entity_tokens']} tokens that carry an entity.", ""]
    if result["cannot_emit"]:
        lines += [f"Labels in the data this model cannot emit: "
                  f"{', '.join(result['cannot_emit'])}.", ""]
    if "seqeval" in result:
        s = result["seqeval"]
        lines += [f"seqeval on the same data: F1 {s.get('overall_f1')}, "
                  f"accuracy {s.get('overall_accuracy')} (the published pair's definitions).", ""]
    for criterion in ("strict", "relaxed"):
        block = result[criterion]
        heading = "exact start, end and label" if criterion == "strict" \
            else f"label and character IoU >= {result['relaxed_iou_threshold']}"
        lines += [f"### {criterion.capitalize()} ({heading})", "",
                  "| Entity | Precision | Recall | F1 | Support |", "|---|---|---|---|---|"]
        for label, scores in block["per_label"].items():
            note = "  (cannot be emitted)" if label in result["cannot_emit"] else ""
            lines.append(f"| {label}{note} | {scores['precision']} | {scores['recall']} | "
                         f"{scores['f1']} | {scores['support']} |")
        lines += [f"| **micro** | {block['micro']['precision']} | {block['micro']['recall']} | "
                  f"{block['micro']['f1']} | {block['micro']['tp'] + block['micro']['fn']} |",
                  f"| **macro** | {block['macro']['precision']} | {block['macro']['recall']} | "
                  f"{block['macro']['f1']} | |", ""]
        if "bootstrap_micro_f1" in block:
            ci = block["bootstrap_micro_f1"]
            lines.append(f"micro F1 {ci['point']}, bootstrap 95% CI "
                         f"[{ci['ci95_low']}, {ci['ci95_high']}] "
                         f"({ci['resamples']} resamples over {ci['sentences']} sentences, "
                         f"seed {ci['seed']}).")
        if result.get("cannot_emit"):
            emittable = block.get("micro_over_emittable_labels", {})
            lines.append(f"Over the {len(block['scope']) - len(result['cannot_emit'])} labels this "
                         f"model can emit: micro F1 {emittable.get('f1')}, macro F1 "
                         f"{block.get('macro_over_emittable_labels', {}).get('f1')}.")
        if block.get("predictions_outside_the_scope"):
            lines.append(f"Predictions of labels outside the scope, not counted: "
                         f"{block['predictions_outside_the_scope']}.")
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", help="a checkpoint to run; omit with --predictions")
    ap.add_argument("--predictions", help="spans saved by a baseline run, scored without a model")
    ap.add_argument("--score-threshold", type=float,
                    help="keep saved predictions at or above this score")
    ap.add_argument("--scope", nargs="+", help="the labels to score, for every model alike")
    ap.add_argument("--emittable", nargs="+",
                    help="the labels this model can produce; the others are reported as such")
    ap.add_argument("--bootstrap", type=int, default=BOOTSTRAP_RESAMPLES)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--data", default="pet_test.json")
    ap.add_argument("--iou", type=float, default=RELAXED_IOU,
                    help=f"IoU needed for a relaxed match (default {RELAXED_IOU})")
    ap.add_argument("--seqeval", action="store_true",
                    help="also report seqeval's own overall numbers, as the paper did")
    ap.add_argument("--json")
    ap.add_argument("--markdown")
    args = ap.parse_args()

    if args.predictions:
        sentences = len(load_pet(args.data))
        result = assemble(args.data, load_predictions(args.predictions, sentences,
                                                      args.score_threshold),
                          scope=args.scope, emittable=args.emittable, threshold=args.iou,
                          bootstrap=args.bootstrap, seed=args.seed, with_seqeval=args.seqeval,
                          model_name=args.predictions)
    elif args.model:
        result = evaluate(args.model, args.data, args.iou, args.seqeval)
    else:
        ap.error("give either --model or --predictions")
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
