"""Reason freely, then answer under constraint.

The relation classifier fails in a particular way: on hard pairs the model
deliberates at length and never commits to a label. 8 of the 14 failures
measured in the development repository (2026-10-07) are that, and none of
the eight replies names a single label -- six name all five while thinking
aloud -- so the answer cannot be read back out of the prose.

Constraining the whole reply (`--constrained-output`) fixes the format and
takes the thinking away with it. This is the other option: let the model think
with nothing constraining it, cut it off at a trigger, and decode only the
answer against the five labels.

Two requests rather than a decoder hook:

1. unconstrained, stopped at `ANSWER:`, with a token budget;
2. the same prompt plus the reasoning it just produced plus `ANSWER:`, decoded
   under a constraint that admits nothing but the five labels.

The second request is about five tokens, so the cost is the first one. That is
why `is_hard` exists: the point is to spend it only on the pairs that earn it.

vLLM constrains with `guided_choice`, which admits exactly one of a list of
strings. Ollama has no equivalent, so there the same job is done with a JSON
schema whose single property is an enum -- a few more tokens, same guarantee.

Nothing here runs through DSPy: a two-phase decode is not something a DSPy
signature can express, so the calls are made directly and the answer is handed
back to the same `parse_relation` everything else uses.
"""
import re

from text2bpmn.relation_metrics import LABELS

TRIGGER = "ANSWER:"
# the gateway markers that appear as a node in their own right; these are where
# the deliberation ran away ("Checks -> Or", "Takes her computer -> Whereas")
MARKERS = {"or", "and", "if", "else", "otherwise", "whereas", "while", "meantime",
           "meanwhile", "then", "when", "unless", "but", "however", "afterwards"}
CONDITION_OPENERS = ("if ", "whether ", "in case ", "once ", "provided ")


# words that carry no identity: counting them made "Receives the form" and
# "Files the form" look 0.67 alike, which sent an ordinary sequence pair down
# the expensive path in the first smoke test
STOPWORDS = {"a", "an", "the", "of", "to", "for", "in", "on", "at", "by", "with",
             "and", "or", "this", "that", "these", "those", "it", "its", "his",
             "her", "their", "is", "are", "was", "were", "be", "been"}


def _words(text):
    return [w for w in re.findall(r"[a-z]+", (text or "").lower())
            if w and w not in STOPWORDS]


def overlap(a, b):
    """How much two node labels share, as a share of the shorter one.

    Mirrored activities -- "Confirmes the changes of the INQ" against
    "Rejectes the changes of the INQ" -- are what the model deliberates over
    longest, and they are exactly the pairs this catches.
    """
    first, second = set(_words(a)), set(_words(b))
    if not first or not second:
        return 0.0
    return len(first & second) / min(len(first), len(second))


def is_hard(node_a, node_b, threshold=0.6):
    """Whether this pair is worth the second call, and why.

    The three shapes that account for nearly every measured failure. Returns
    the reason rather than a bare True so a run can report what it spent its
    budget on.
    """
    for node in (node_a, node_b):
        if (node or "").strip().lower() in MARKERS:
            return "a gateway marker as a node"
    for node in (node_a, node_b):
        if (node or "").strip().lower().startswith(CONDITION_OPENERS):
            return "a condition specification as a node"
    if overlap(node_a, node_b) >= threshold:
        return "two near-identical activities"
    return None


def build_prompt(signature_text, context, node_a, node_b):
    """The question, in the same terms the DSPy signature puts it.

    It does not ask for the trigger. The first version did, and the model
    obliged by writing `ANSWER:` as its first token, where `stop` fired and the
    reasoning came back empty -- the phase did nothing at all. Asking for the
    reasoning and withholding the answer is what makes phase one phase one.
    """
    return (f"{signature_text.strip()}\n\n"
            f"Context: {context}\n"
            f"node_A: {node_a}\n"
            f"node_B: {node_b}\n\n"
            f"Which of {', '.join(LABELS)} describes how node_A relates to node_B? "
            f"Explain your reasoning in a few sentences. Do not state the label yet.")


ASK_FOR_THE_LABEL = (f"{TRIGGER} Reply with exactly one of "
                     f"{', '.join(LABELS)} and nothing else.")


def no_thinking(backend):
    """The keyword arguments that stop a hybrid model reasoning first.

    vLLM forwards `chat_template_kwargs` into the chat template, which is where
    Qwen3 and Qwen3.5 decide whether to open a `<think>` block. Ollama has no
    equivalent, so there is nothing to send and an empty dict is right.

    This has to reach *both* phases. It did not, and the consequence was total:
    phase two allows 16 tokens, a `<think>` block consumes all of them, the
    content names no label, and every hard pair resolves to UNKNOWN. A whole
    45-document run was lost that way.
    """
    return {"chat_template_kwargs": {"enable_thinking": False}} \
        if backend == "openai" else {}


def constraint(backend, disable_thinking=False):
    """The keyword arguments that close the decoder to the five labels.

    `disable_thinking` is merged into the same `extra_body`, because passing it
    separately would hand `completion` the keyword twice.
    """
    if backend == "openai":          # vLLM and anything speaking its API
        body = {"guided_choice": list(LABELS)}
        if disable_thinking:
            body.update(no_thinking(backend))
        return {"extra_body": body}
    return {"response_format": {     # Ollama
        "type": "json_schema",
        "json_schema": {"name": "relation", "schema": {
            "type": "object",
            "properties": {"relation": {"type": "string", "enum": list(LABELS)}},
            "required": ["relation"]}}}}


def answer_from(text):
    """The label in a constrained reply, whichever shape it came back in."""
    from text2bpmn.relation_parsing import parse_relation
    return parse_relation(text)


def classify(context, node_a, node_b, *, model, api_base, api_key="ollama",
             backend="ollama", signature_text="", temperature=0.0, timeout=120,
             reasoning_tokens=384, disable_thinking=False, completion=None):
    """One pair, in two phases. Returns (label, record).

    `completion` is litellm's by default and is injected in the tests, so the
    two phases can be checked without a server.
    """
    if completion is None:
        import litellm
        completion = litellm.completion

    prompt = build_prompt(signature_text, context, node_a, node_b)
    common = dict(model=model, api_base=api_base, api_key=api_key,
                  temperature=temperature, timeout=timeout)

    # phase one is unconstrained in its content, but a hybrid model still has
    # to be told not to reason: native thinking is what this design replaces,
    # and leaving it on spends the budget inside <think> instead of on prose
    thinking = no_thinking(backend) if disable_thinking else {}
    free = {"extra_body": thinking} if thinking else {}

    thought = completion(messages=[{"role": "user", "content": prompt}],
                         max_tokens=reasoning_tokens, **free, **common)
    reasoning = (thought.choices[0].message.content or "").strip()

    decided = completion(
        messages=[{"role": "user", "content": prompt},
                  {"role": "assistant", "content": reasoning},
                  {"role": "user", "content": ASK_FOR_THE_LABEL}],
        max_tokens=16, **constraint(backend, disable_thinking), **common)
    raw = (decided.choices[0].message.content or "").strip()

    label = answer_from(raw)
    return label, {"node_A": node_a, "node_B": node_b, "reasoning_characters": len(reasoning),
                   "raw_answer": raw, "label": label, "phase": "two"}
