"""Table 2 recounted: mentions and relations per type in the PET file we use.

    python3 -m text2bpmn.checks.pet_counts

Counts PETv1.1 (pet_data/PETv1.1-relations.json): a mention is a run of one
type opening with its B- tag, as text2bpmn.pet_rules_eval reads them, and a
relation is one entry of a document's `relations`. Beside them, two published
sets of numbers:

- the revised paper's Table 2, Entity Distribution (mention counts only), as
  the draft of 2026-11-12 prints it (it was Table 1 in the drafts of
  2026-03-31 to 2026-04-07, before the comparison of approaches became Table 1);
  the same numbers, which text2bpmn.paper_tables 2 rebuilds with their shares;
- the PET paper, Bellan et al., arXiv 2203.04860, Table 2 (entity statistics)
  and Table 3 (relation statistics), as ar5iv renders it.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

from text2bpmn.checks.common import header, provenance, write
from text2bpmn.pet_rules_eval import PET_DEFAULT, load_documents

MENTIONS = ("Activity", "Activity Data", "Actor", "XOR Gateway", "Condition Specification",
            "Further Specification", "AND Gateway")
RELATIONS = ("flow", "uses", "actor performer", "actor recipient", "further specification", "same gateway")
OUR_TABLE_2 = {"Activity": 502, "Activity Data": 459, "Actor": 449, "XOR Gateway": 117,
               "Condition Specification": 80, "Further Specification": 64, "AND Gateway": 8}
PET_PAPER_MENTIONS = {"Activity": 501, "Activity Data": 452, "Actor": 439, "XOR Gateway": 117,
                      "Condition Specification": 80, "Further Specification": 64, "AND Gateway": 8}
PET_PAPER_RELATIONS = {"flow": 689, "uses": 477, "actor performer": 313, "actor recipient": 164,
                       "further specification": 64, "same gateway": 43}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", default=PET_DEFAULT)
    ap.add_argument("--out", default="runs/checks/pet_counts")
    args = ap.parse_args()
    raw = json.loads(Path(args.data).read_text(encoding="utf-8"))
    documents = load_documents(args.data)
    mentions = Counter(s["entity_group"] for d in documents for s in d["spans"])
    relations = Counter(r["relation-type"] for d in raw for r in d["relations"])
    sentences = sum(len(set(d["sentence-IDs"])) for d in raw)
    record = provenance(data=args.data, documents=len(raw), sentences=sentences)
    result = {"provenance": record, "mentions": dict(mentions), "relations": dict(relations),
              "our_table_2": OUR_TABLE_2, "pet_paper_mentions": PET_PAPER_MENTIONS,
              "pet_paper_relations": PET_PAPER_RELATIONS}
    lines = header("PET v1.1 recounted, beside the published numbers", record)
    lines += [f"{len(raw)} documents, {sentences} sentences.", "",
              "## Mentions", "", "| type | PET v1.1 file | our Table 2 | PET paper, Table 2 |", "|---|---|---|---|"]
    lines += [f"| {t} | {mentions[t]} | {OUR_TABLE_2[t]} | {PET_PAPER_MENTIONS[t]} |" for t in MENTIONS]
    lines += [f"| total | {sum(mentions[t] for t in MENTIONS)} | {sum(OUR_TABLE_2.values())} | "
              f"{sum(PET_PAPER_MENTIONS.values())} |", "",
              "## Relations", "", "| type | PET v1.1 file | our Table 2 | PET paper, Table 3 |", "|---|---|---|---|"]
    lines += [f"| {t} | {relations[t]} | - | {PET_PAPER_RELATIONS[t]} |" for t in RELATIONS]
    lines += [f"| total | {sum(relations[t] for t in RELATIONS)} | - | {sum(PET_PAPER_RELATIONS.values())} |", ""]
    print("wrote", write(args.out, "pet_counts", result, "\n".join(lines)))
    print("\n".join(lines[3:]))


if __name__ == "__main__":
    main()
