"""Lexical cues for concurrency.

The recogniser rarely emits an AND Gateway mention (PET has 8 in 417
sentences), so a parallel block mostly comes from a PARALLEL relation between
two activities. Asking about every activity
pair costs an LLM call each (ticket C8), so the question can be restricted to
pairs whose text carries a concurrency cue: the constructions the relation
classifier was written for ("In parallel...", "While...", "Meantime..."), plus
"both", which marks a join of concurrent work.

Cue gating misses concurrency the text only implies, so it is not the default:
`parallel_detection` is "all", and "cues" trades that recall for fewer calls.
"off" skips the question entirely, which is how the pipeline behaved before
parallel blocks were supported.
"""
import re

PARALLEL_CUES = ("in parallel", "at the same time", "simultaneous", "concurrent", "meanwhile",
                 "in the meantime", "meantime", "while", "during", "at once", "alongside",
                 # "Once both A and B have been performed" marks a join of concurrent work
                 "both")
LEAD_IN = 40  # characters before the first entity, where a leading cue sits


def has_parallel_cue(context, first, second):
    """Whether a concurrency cue covers the span of these two entities."""
    starts = [e.get("start") for e in (first, second) if e.get("start") is not None]
    ends = [e.get("end") for e in (first, second) if e.get("end") is not None]
    if starts and ends:
        window = context[max(0, min(starts) - LEAD_IN):max(ends)]
    else:  # no offsets (hand-built entities): fall back to the labels themselves
        window = f"{first.get('word', '')} {second.get('word', '')}"
    window = re.sub(r"\s+", " ", window).lower()
    return any(cue in window for cue in PARALLEL_CUES)
