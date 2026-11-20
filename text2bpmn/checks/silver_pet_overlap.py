"""The 302-pair set against PET: does any fragment, or any candidate pair, come from PET?

    python3 -m text2bpmn.checks.silver_pet_overlap
        # -> text2bpmn/results/silver_pet_overlap.{md,json}

Every fragment of benchmark_silver_2.jsonl (302 pairs, 185 distinct texts) is
compared with all 45 documents of PET v1.1: pet_data/PETv1.1-relations.json,
and the sentence files pet_train.json (38 documents) and pet_test.json (7),
which are checked to hold the same 417 sentences. Nothing is learned or tuned.

Text is compared as lower-cased word tokens (the regex \\w+, so punctuation
and spacing do not count). For each fragment:

- exact: the fragment's token sequence occurs in a PET document's token
  sequence, and, separately, any sentence of the fragment equals a PET sentence;
- 8-gram overlap: the share of the fragment's word 8-grams that occur anywhere
  in PET (each document read as one token sequence, across sentence ends);
- highest similarity: the largest difflib.SequenceMatcher ratio,
  2 * matching tokens / (tokens of both), between the fragment and any window
  of 1, 2 or 3 consecutive sentences of one PET document, with the window, and
  the longest run of words the two share.

Each candidate pair (entity_1, entity_2) is looked for in PET at three levels:
a PET relation (any type) between two mentions whose texts are the two
entities, in either direction; both entities as the texts of mentions of one
PET document; both entities as word sequences in one PET sentence. A mention's
text is the span its BIO tags give; a relation, which PET gives head word to
head word, joins the mentions holding those words.

The output holds no time stamp or machine detail, so a second run gives the
same files; the inputs are named with their SHA-256.
"""
import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SET = "benchmark_silver_2.jsonl"
PET = "pet_data/PETv1.1-relations.json"
SPLITS = ("pet_train.json", "pet_test.json")
OUT = "text2bpmn/results"
N = 8
WINDOWS = (1, 2, 3)
TOP = 15
WORD = re.compile(r"\w+")


def words(text):
    return WORD.findall(text.lower())


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ngrams(tokens, n=N):
    return {tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def contains(haystack, needle):
    """Whether the token list `needle` occurs contiguously in `haystack`."""
    if not needle:
        return False
    first, k = needle[0], len(needle)
    return any(haystack[i:i + k] == needle for i, t in enumerate(haystack) if t == first)


def mentions(doc):
    """Each BIO span of a PET document: (sentence, first word, last word, type, text)."""
    spans, current = [], None
    for tag, token, sentence, word in zip(doc["ner_tags"], doc["tokens"], doc["sentence-IDs"], doc["tokens-IDs"]):
        inside = tag.startswith("I-") and current and current[0] == sentence and current[3] == tag[2:]
        if inside:
            current[2] = word
            current[4].append(token)
            continue
        if current:
            spans.append(current)
        current = [sentence, word, word, tag[2:], [token]] if tag != "O" else None
    if current:
        spans.append(current)
    return [(s, a, b, kind, " ".join(words(" ".join(toks)))) for s, a, b, kind, toks in spans]


def load_pet():
    docs = json.loads((REPO / PET).read_text(encoding="utf-8"))
    pet = []
    for doc in docs:
        sentences = {}
        for token, sentence in zip(doc["tokens"], doc["sentence-IDs"]):
            sentences.setdefault(sentence, []).append(token)
        spans = mentions(doc)
        at = {(s, w): span for span in spans for w in range(span[1], span[2] + 1) for s in [span[0]]}
        relations = []
        for r in doc["relations"]:
            source = at.get((r["source-head-sentence-ID"], r["source-head-word-ID"]))
            target = at.get((r["target-head-sentence-ID"], r["target-head-word-ID"]))
            if source and target:
                relations.append((source[4], target[4], r["relation-type"]))
        pet.append({"name": doc["document name"],
                    "sentences": [sentences[k] for k in sorted(sentences)],
                    "sentence_words": [words(" ".join(sentences[k])) for k in sorted(sentences)],
                    "words": words(" ".join(doc["tokens"])),
                    "mentions": {span[4] for span in spans},
                    "relations": relations})
    # the two sentence files hold the same sentences as the relations file
    split_sentences = {}
    for name in SPLITS:
        for row in json.loads((REPO / name).read_text(encoding="utf-8")):
            split_sentences[(row["document name"], row["sentence-ID"])] = row["tokens"]
    whole = {(d["name"], k): s for d in pet for k, s in enumerate(d["sentences"])}
    if split_sentences != whole:
        raise SystemExit(f"{' and '.join(SPLITS)} do not hold the sentences of {PET}")
    return pet


def best_window(fragment, pet):
    """The PET window of 1-3 consecutive sentences most similar to `fragment`."""
    best = (-1.0, None)
    matcher = SequenceMatcher(None, autojunk=False)
    matcher.set_seq2(fragment)
    for d in pet:
        sw = d["sentence_words"]
        for size in WINDOWS:
            for start in range(len(sw) - size + 1):
                window = [w for s in sw[start:start + size] for w in s]
                matcher.set_seq1(window)
                if matcher.real_quick_ratio() <= best[0] or matcher.quick_ratio() <= best[0]:
                    continue
                ratio = matcher.ratio()
                if ratio > best[0]:
                    run = matcher.find_longest_match(0, len(window), 0, len(fragment)).size
                    best = (ratio, {"document": d["name"], "sentences": [start, start + size - 1],
                                    "text": " ".join(t for s in d["sentences"][start:start + size] for t in s),
                                    "longest_shared_run": run})
    return best


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    rows = [json.loads(line) for line in (REPO / SET).read_text(encoding="utf-8").splitlines() if line.strip()]
    texts = list(dict.fromkeys(r["text"] for r in rows))
    pairs_of = {t: [r for r in rows if r["text"] == t] for t in texts}
    pet = load_pet()
    pet_grams = set().union(*(ngrams(d["words"]) for d in pet))
    pet_sentences = {" ".join(s) for d in pet for s in d["sentence_words"]}

    fragments = []
    for number, text in enumerate(texts, 1):
        tokens = words(text)
        grams = ngrams(tokens)
        shared = sorted(" ".join(g) for g in grams & pet_grams)
        own_sentences = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]
        ratio, window = best_window(tokens, pet)
        fragments.append({
            "fragment": number, "text": text, "pairs": len(pairs_of[text]), "words": len(tokens),
            "exact_in_pet": any(contains(d["words"], tokens) for d in pet),
            "sentence_equal_to_a_pet_sentence": any(" ".join(words(s)) in pet_sentences for s in own_sentences),
            "eight_grams": len(grams), "eight_grams_in_pet": len(grams & pet_grams),
            "eight_gram_share": round(len(grams & pet_grams) / len(grams), 4) if grams else None,
            "shared_eight_grams": shared,
            "highest_similarity": round(ratio, 4), "most_similar_pet_window": window})

    candidates = []
    for k, r in enumerate(rows, 1):
        e1, e2 = " ".join(words(r["entity_1"])), " ".join(words(r["entity_2"]))
        as_relation = sorted({f"{d['name']}: {a} -> {b} ({kind})" for d in pet for a, b, kind in d["relations"]
                              if {a, b} == {e1, e2}})
        as_mentions = sorted(d["name"] for d in pet if e1 in d["mentions"] and e2 in d["mentions"])
        in_sentence = sorted({f"{d['name']}, sentence {i}" for d in pet for i, s in enumerate(d["sentence_words"])
                              if contains(s, e1.split()) and contains(s, e2.split())})
        candidates.append({"pair": k, "text": r["text"], "entity_1": r["entity_1"], "entity_2": r["entity_2"],
                           "label": r["label"], "as_pet_relation": as_relation,
                           "as_mentions_of_one_document": as_mentions, "in_one_pet_sentence": in_sentence})

    # each entity on its own, to show what the pair levels could have found
    entities = sorted({" ".join(words(r[k])) for r in rows for k in ("entity_1", "entity_2")})
    pet_mentions = set().union(*(d["mentions"] for d in pet))
    entity_mentions = [e for e in entities if e in pet_mentions]
    entity_in_sentence = [e for e in entities
                          if any(contains(s, e.split()) for d in pet for s in d["sentence_words"])]

    counts = {
        "fragments": len(texts), "pairs": len(rows),
        "pet_documents": len(pet), "pet_sentences": sum(len(d["sentences"]) for d in pet),
        "pet_relations_mapped": sum(len(d["relations"]) for d in pet),
        "fragments_exact_in_pet": sum(f["exact_in_pet"] for f in fragments),
        "fragments_with_a_sentence_equal_to_a_pet_sentence": sum(f["sentence_equal_to_a_pet_sentence"]
                                                                 for f in fragments),
        "fragments_shorter_than_8_words": sum(f["eight_grams"] == 0 for f in fragments),
        "fragments_sharing_an_8_gram": sum(f["eight_grams_in_pet"] > 0 for f in fragments),
        "pairs_as_a_pet_relation": sum(bool(c["as_pet_relation"]) for c in candidates),
        "pairs_as_mentions_of_one_pet_document": sum(bool(c["as_mentions_of_one_document"]) for c in candidates),
        "pairs_in_one_pet_sentence": sum(bool(c["in_one_pet_sentence"]) for c in candidates),
        "distinct_entities": len(entities),
        "entities_that_are_pet_mention_texts": entity_mentions,
        "entities_that_occur_in_a_pet_sentence": entity_in_sentence,
        "pairs_with_one_entity_a_pet_mention_text": sum(
            " ".join(words(r["entity_1"])) in pet_mentions or " ".join(words(r["entity_2"])) in pet_mentions
            for r in rows),
    }
    similarity = sorted(fragments, key=lambda f: (-f["highest_similarity"], f["fragment"]))
    bands = Counter()
    for f in fragments:
        for edge in (0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3):
            if f["highest_similarity"] >= edge:
                bands[edge] += 1
    inputs = {p: sha256(REPO / p) for p in (SET, PET, *SPLITS)}
    result = {"script": "text2bpmn/checks/silver_pet_overlap.py",
              "script_sha256": sha256(Path(__file__)), "inputs_sha256": inputs,
              "python": sys.version.split()[0], "counts": counts,
              "similarity_at_least": {str(k): bands[k] for k in sorted(bands, reverse=True)},
              "fragments": fragments, "candidate_pairs": candidates}

    def cell(text, limit=None):
        text = text.replace("|", "\\|")
        return text if limit is None or len(text) <= limit else text[:limit - 1] + "…"

    lines = ["# The 302-pair set against PET", "",
             "`python3 -m text2bpmn.checks.silver_pet_overlap` (text2bpmn/checks/silver_pet_overlap.py, "
             f"SHA-256 `{result['script_sha256'][:16]}…`). Inputs, SHA-256:", ""]
    lines += [f"- `{p}` `{h}`" for p, h in inputs.items()]
    lines += ["", f"The set: {counts['pairs']} pairs from {counts['fragments']} distinct fragments. "
              f"PET: {counts['pet_documents']} documents, {counts['pet_sentences']} sentences "
              f"(`pet_train.json` and `pet_test.json` hold the same sentences as `{PET}`), "
              f"{counts['pet_relations_mapped']} relations. Words are lower-cased `\\w+` tokens.", "",
              "## Exact and near-duplicate matches", "",
              "| measure | fragments |", "|---|---|",
              f"| fragment found verbatim in a PET document | {counts['fragments_exact_in_pet']} |",
              f"| fragment with a sentence equal to a PET sentence | "
              f"{counts['fragments_with_a_sentence_equal_to_a_pet_sentence']} |",
              f"| fragment sharing at least one word 8-gram with PET | {counts['fragments_sharing_an_8_gram']} "
              f"(of {counts['fragments'] - counts['fragments_shorter_than_8_words']} with 8 words or more) |"]
    for edge, n in result["similarity_at_least"].items():
        lines.append(f"| highest similarity to a PET window at least {edge} | {n} |")
    lines += ["", f"Highest similarity: SequenceMatcher ratio over words against every window of "
              f"{', '.join(map(str, WINDOWS))} consecutive sentences of one PET document; the fragments with "
              f"the highest values, then every fragment sharing an 8-gram:", "",
              "| # | fragment | pairs | similarity | longest shared run (words) | 8-grams in PET | PET window |",
              "|---|---|---|---|---|---|---|"]
    listed = similarity[:TOP] + [f for f in similarity[TOP:] if f["eight_grams_in_pet"]]
    for f in listed:
        w = f["most_similar_pet_window"]
        span = f"{w['sentences'][0]}" if w["sentences"][0] == w["sentences"][1] else "{}-{}".format(*w["sentences"])
        lines.append(f"| {f['fragment']} | {cell(f['text'])} | {f['pairs']} | {f['highest_similarity']:.3f} | "
                     f"{w['longest_shared_run']} | {f['eight_grams_in_pet']}/{f['eight_grams']} | "
                     f"{w['document']}, sentence {span}: {cell(w['text'])} |")
    shared = [f for f in fragments if f["shared_eight_grams"]]
    if shared:
        lines += ["", "The 8-grams shared with PET:", ""]
        lines += [f"- fragment {f['fragment']}: " + "; ".join(f"\"{g}\"" for g in f["shared_eight_grams"])
                  for f in shared]
    lines += ["", "## Candidate pairs", "", "| level | pairs |", "|---|---|",
              f"| a PET relation (any type) joins two mentions with the pair's texts | "
              f"{counts['pairs_as_a_pet_relation']} |",
              f"| both entities are mentions of one PET document | {counts['pairs_as_mentions_of_one_pet_document']} |",
              f"| both entities occur in one PET sentence | {counts['pairs_in_one_pet_sentence']} |", "",
              f"Each entity on its own: of the {counts['distinct_entities']} distinct entity texts, "
              f"{len(entity_mentions)} are the text of a PET mention "
              f"({', '.join(repr(e) for e in entity_mentions) or 'none'}; one side of "
              f"{counts['pairs_with_one_entity_a_pet_mention_text']} pairs), and {len(entity_in_sentence)} occur "
              f"in a PET sentence ({', '.join(repr(e) for e in entity_in_sentence) or 'none'})."]
    found = [c for c in candidates if c["as_pet_relation"] or c["as_mentions_of_one_document"]
             or c["in_one_pet_sentence"]]
    if found:
        lines += ["", "| pair | entity_1 | entity_2 | label | PET relation | mentions of one document | one sentence |",
                  "|---|---|---|---|---|---|---|"]
        for c in found:
            lines.append(f"| {c['pair']} | {cell(c['entity_1'])} | {cell(c['entity_2'])} | {c['label']} | "
                         f"{cell('; '.join(c['as_pet_relation']) or '–')} | "
                         f"{cell(', '.join(c['as_mentions_of_one_document']) or '–', 120)} | "
                         f"{cell('; '.join(c['in_one_pet_sentence']) or '–', 120)} |")
    out = Path(args.out)
    if not out.is_absolute():
        out = REPO / out
    out.mkdir(parents=True, exist_ok=True)
    (out / "silver_pet_overlap.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                                                 encoding="utf-8")
    (out / "silver_pet_overlap.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:40]))
    print("wrote", out / "silver_pet_overlap.md")


if __name__ == "__main__":
    main()
