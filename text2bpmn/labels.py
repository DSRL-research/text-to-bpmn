"""How much of a reference label's meaning the generated label kept.

    python3 -m text2bpmn.labels --reference REF.bpmn --generated GEN.bpmn

The element counts in text2bpmn/compare.py say whether a task was found; they
say nothing about how well it is named, because a pair matches at a similarity
of 0.5 and is then simply counted. These measures report the naming itself,
which is where the case runs put the largest share of false positives: labels
such as "Develops new" or "Choose a", an activity whose object never reached
it.

Three views of a matched pair, all in [0, 1] and all reported, none of them
feeding the matcher -- changing the matcher's own similarity would move every
true and false positive in the paper:

- **lemma_jaccard**: overlap of lemmatised content words, so "checks the credit
  history" and "credit history check" count as the same words.
- **content_recall**: the share of the reference's content words present in the
  generated label. Jaccard punishes a longer label as much as a shorter one;
  this one isolates what was lost.
- **head_kept**: whether the generated label contains the head of the
  reference's last noun phrase -- the object of the step. "Develops new" has
  lost the head of "Develop new symptoms" and reads as a different activity.

WordNet similarity is reported too where the corpora are installed
(`python -m nltk.downloader wordnet wordnet_ic omw-1.4`), and left out with a
note where they are not, so the measure never silently becomes something else.
"""
import argparse
import json
from functools import lru_cache
from pathlib import Path

from text2bpmn.compare import DEFAULT_THRESHOLD, match_tasks, normalise, read_bpmn

STOPWORDS = {"the", "a", "an", "of", "to", "for", "and", "or", "is", "are", "be", "been",
             "with", "by", "on", "in", "at", "from", "this", "that", "it", "its", "their"}


@lru_cache(maxsize=1)
def _nlp():
    """spaCy, already a dependency for activity validation, lemmatises here too;
    it needs no downloaded corpus beyond the model the pipeline already uses."""
    import spacy
    return spacy.load("en_core_web_sm")


@lru_cache(maxsize=1)
def _wordnet():
    """WordNet and an information-content corpus, if they are installed."""
    try:
        from nltk.corpus import wordnet, wordnet_ic
        wordnet.synsets("process")  # raises LookupError when the corpus is absent
        return wordnet, wordnet_ic.ic("ic-brown.dat")
    except Exception:
        return None, None


@lru_cache(maxsize=512)
def content_words(label):
    """Lemmatised content words of a label, in order, without stopwords."""
    return tuple(token.lemma_.lower() for token in _nlp()(normalise(label))
                 if token.lemma_.lower() not in STOPWORDS and not token.is_punct)


@lru_cache(maxsize=512)
def head_word(label):
    """The head of the label's last noun phrase: what the step acts on."""
    doc = _nlp()(normalise(label))
    chunks = list(doc.noun_chunks)
    if chunks:
        return chunks[-1].root.lemma_.lower()
    nouns = [t for t in doc if t.pos_ in ("NOUN", "PROPN")]
    return nouns[-1].lemma_.lower() if nouns else ""


def wordnet_similarity(a, b):
    """Mean best Lin similarity between the labels' content words, or None."""
    wordnet, ic = _wordnet()
    if wordnet is None:
        return None
    scores = []
    for word in content_words(a):
        best = 0.0
        for other in content_words(b):
            for left in wordnet.synsets(word):
                for right in wordnet.synsets(other):
                    if left.pos() == right.pos() and left.pos() in ("n", "v"):
                        try:
                            best = max(best, left.lin_similarity(right, ic))
                        except Exception:
                            continue
        scores.append(best)
    return round(sum(scores) / len(scores), 3) if scores else None


def shares_a_word(first, second, prefix=5):
    """Whether two word sets have any word in common, allowing for hyphens and
    for the tagger's lemma: "Followups" and "follow-ups" are the same word, and
    "clarifies" lemmatises to "clarify" only when it is read as a verb."""
    if first & second:
        return True
    return any(a[:prefix] == b[:prefix] for a in first for b in second
               if len(a) >= prefix and len(b) >= prefix)


def pair_metrics(reference_label, generated_label):
    reference_words, generated_words = set(content_words(reference_label)), set(content_words(generated_label))
    union = reference_words | generated_words
    head = head_word(reference_label)
    metrics = {
        "reference": reference_label,
        "generated": generated_label,
        "lemma_jaccard": round(len(reference_words & generated_words) / len(union), 3) if union else 0.0,
        "content_recall": round(len(reference_words & generated_words) / len(reference_words), 3)
        if reference_words else 0.0,
        "head_kept": bool(head) and head in generated_words,
        "head": head,
    }
    similarity = wordnet_similarity(reference_label, generated_label)
    if similarity is not None:
        metrics["wordnet_lin"] = similarity
    return metrics


def label_metrics(reference, generated, threshold=DEFAULT_THRESHOLD):
    """Naming quality over the matched tasks, plus the labels of one word."""
    mapping = match_tasks(reference, generated, threshold)
    pairs = [pair_metrics(reference.nodes[r].name, generated.nodes[g].name)
             for r, g in mapping.items()]
    single = [t.name for t in generated.tasks if len(content_words(t.name)) <= 1]
    summary = {"matched": len(pairs),
               "single_word_labels": single,
               "wordnet": "installed" if _wordnet()[0] is not None else
                          "not installed (python -m nltk.downloader wordnet wordnet_ic omw-1.4)"}
    for key in ("lemma_jaccard", "content_recall"):
        summary[f"mean_{key}"] = round(sum(p[key] for p in pairs) / len(pairs), 3) if pairs else 0.0
    summary["head_kept"] = sum(p["head_kept"] for p in pairs)
    # a pair can match at the 0.5 threshold on character similarity alone, with
    # no word in common: "Perform Evaluation" was matched to "Inform the". Such
    # a pair is counted as a true positive by the element measures, so the
    # count belongs beside them.
    summary["matched_without_a_shared_word"] = [
        (p["reference"], p["generated"]) for p in pairs
        if not shares_a_word(set(content_words(p["reference"])), set(content_words(p["generated"])))]
    if pairs and "wordnet_lin" in pairs[0]:
        summary["mean_wordnet_lin"] = round(
            sum(p.get("wordnet_lin") or 0.0 for p in pairs) / len(pairs), 3)
    return {"summary": summary, "pairs": pairs}


def to_markdown(result):
    summary = result["summary"]
    lines = [f"Naming of the {summary['matched']} matched tasks: "
             f"mean lemma Jaccard {summary['mean_lemma_jaccard']}, "
             f"mean content recall {summary['mean_content_recall']}, "
             f"object head kept in {summary['head_kept']}/{summary['matched']}."]
    if summary["matched_without_a_shared_word"]:
        lines.append(f"Matched with no content word in common, so counted as found by the "
                     f"element measures while naming something else: "
                     f"{'; '.join(f'{r!r} as {g!r}' for r, g in summary['matched_without_a_shared_word'])}.")
    if "mean_wordnet_lin" in summary:
        lines.append(f"Mean WordNet (Lin) similarity {summary['mean_wordnet_lin']}.")
    else:
        lines.append(f"WordNet similarity: {summary['wordnet']}.")
    if summary["single_word_labels"]:
        lines.append(f"Generated labels of a single content word: "
                     f"{', '.join(repr(n) for n in summary['single_word_labels'])}.")
    lines += ["", "| Reference | Generated | Jaccard | Content recall | Object head kept |",
              "|---|---|---|---|---|"]
    for pair in sorted(result["pairs"], key=lambda p: p["lemma_jaccard"]):
        lines.append(f"| {pair['reference']} | {pair['generated']} | {pair['lemma_jaccard']} | "
                     f"{pair['content_recall']} | {'yes' if pair['head_kept'] else 'no (' + pair['head'] + ')'} |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--reference", required=True)
    ap.add_argument("--generated", required=True)
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("--json", help="write the full result here")
    args = ap.parse_args()
    result = label_metrics(read_bpmn(args.reference), read_bpmn(args.generated), args.threshold)
    print(to_markdown(result))
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n✅ Wrote {args.json}")


if __name__ == "__main__":
    main()
