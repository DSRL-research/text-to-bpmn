"""Repeated PET runs: does a second run of a relation stage give the same counts on all 45 documents?

    python3 -m text2bpmn.checks.repeated_runs

Two pairs of runs of the same stage on the 45 PET documents, made at
different times on the same server:

- the final method (idea 3): runs/ideas/idea3/pet_decisions4 (tag
  relation-idea-3, 2026-11-12) and runs/final-3/pet_decisions (tag
  revision-final-3, the release run);
- pairwise classification: runs/final/pet_classifier (tag revision-final,
  the method as submitted) and its rerun runs/ideas/idea1b/pet_pairs (tag
  relation-idea-1b).

Each run's records.jsonl holds one record per document, read with
text2bpmn.relation_ideas.records as the tables read it. For every document,
the counts (the three shapes scored, `counts`) and every other field the two
records share are compared. Nothing is written; the command exits 1 when a
pair differs.
"""
import sys

from text2bpmn import relation_ideas as ri

PAIRS = (
    ("the final method (idea 3)", "runs/ideas/idea3/pet_decisions4", "runs/final-3/pet_decisions"),
    ("pairwise classification", "runs/final/pet_classifier", "runs/ideas/idea1b/pet_pairs"),
)


def compare(first, second):
    a, b = ri.records(first), ri.records(second)
    shared = sorted(set(a) & set(b))
    counts = [d for d in shared if a[d]["counts"] != b[d]["counts"]]
    fields = sorted({k for d in shared for k in set(a[d]) & set(b[d])} - {"document"})
    other = {k: [d for d in shared if a[d][k] != b[d][k]] for k in fields if k in a[shared[0]]}
    return {"documents": (len(a), len(b), len(shared)), "counts_differ": counts,
            "fields_differ": {k: v for k, v in other.items() if v}, "fields": fields}


def main():
    failed = False
    for name, first, second in PAIRS:
        r = compare(first, second)
        n_a, n_b, n_shared = r["documents"]
        same = n_a == n_b == n_shared == 45 and not r["counts_differ"]
        failed |= not same
        print(f"{name}: {first} ({n_a} documents) and {second} ({n_b}); counts identical on all "
              f"{n_shared} documents: {same}")
        if r["counts_differ"]:
            print("  counts differ on:", ", ".join(r["counts_differ"]))
        differ = r["fields_differ"]
        print(f"  the other fields compared ({', '.join(f for f in r['fields'] if f != 'counts')}): "
              + ("identical" if not differ else "differ: " + "; ".join(f"{k} on {len(v)}" for k, v in differ.items())))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
