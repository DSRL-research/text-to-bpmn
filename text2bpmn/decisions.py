"""Relation ideas 1 and 1b: ask the LLM about each decision, not about every pair.

    RunConfig(relation_mode="decisions"), or --relation-mode decisions     (idea 1)
    RunConfig(relation_mode="decisions2"), or --relation-mode decisions2   (idea 1b)
    RunConfig(relation_mode="decisions3"), or --relation-mode decisions3   (idea 1c)
    RunConfig(relation_mode="decisions4"), or --relation-mode decisions4   (idea 3)

The pairwise classifier is asked, for every element and the three after it,
which of five relations holds, with no answer for "none". On PET's gold spans
its answers cost 38 of the plain sequence flows the text order already gives
and gained no decision flow (runs/final/pet_classifier against
runs/final/pet_no_llm: F1 0.726 against 0.762).

Here the text-order chain is the default, and the LLM is asked one question
per decision the recogniser found: an XOR Gateway mention, or a Condition
Specification that no gateway before it absorbed. An else-marker ("Otherwise")
after a decision belongs to that decision and is no node of its own, as in the
pairwise mode. The question lists the steps after the decision, up to the next
gateway or MAX_STEPS steps, and asks for each whether it is done only when the
condition holds ("yes"), only when it does not ("no"), or after the decision
whatever its outcome ("after"). The first "after" ends the decision. The yes
steps, in text order, form one branch and the no steps the other; both
branches meet again at the first "after" step, or at whatever follows the
listed steps. A decision with no step in either branch does not choose between
anything: it stays in the chain, where the Validation Layer bypasses it. A
call that fails or an answer that does not parse leaves the chain as it is.

Idea 1b changes one thing. In idea 1 the next decision mention ends the
question, so a decision the text states in two mentions ("If no problems are
detected ..." / "If a problem is detected ...", which PET links as `same
gateway`) became two decisions in a row, with an empty "no" edge from the
first to the second: 69 of idea 1's edges on PET, none of them annotated
(text2bpmn/results/relation_idea_1.md). In 1b the question runs on past
decision mentions, up to MAX_ITEMS items, and asks of each whether it is
another case of the same decision ("same") or a decision of its own after
this one ("after"). A "same" mention is no node: it opens another branch of
the decision, and a step's "yes" means the case named last before it. With
two or more cases and no "no" step there is no default branch; with one case
the outcome that does nothing goes on to the step after the decision, as in
idea 1.

Parallel blocks are not built in these modes. In 1 and 1b an AND Gateway
mention stays in the chain like any gateway that branches nowhere, and ends a
question; a decision whose question it ends then joins its branches at that
parallel gateway, which waits for the branch not taken. WOFLAN found the
goods dispatch model of idea 1 unsound that way (2026-11-11). Idea 1c is 1b
with AND Gateway mentions left out of the model, as an else-marker is: they
carry no structure in a mode that builds no parallel blocks.

Idea 3 (relation_mode "decisions4") is 1c with one more question, one per
concurrency word (an AND Gateway mention), asked after every decision is
settled. It lists the steps around the word: up to MAX_BEFORE before it,
since PET's cues often follow the first line of work ("The clerk registers
the order. In the meantime, the warehouse picks the goods"), and up to
MAX_AFTER after it, never across a decision or into a decision's branches.
Each step is "before" the concurrent part, in line of work "a", "b" or "c",
or "after" every line is finished; the first "after" ends the block. With two
lines or more, the word becomes a parallel split, each line a branch in text
order, and the lines meet at the first "after" step, where the Validation
Layer puts the parallel join. A call that fails, or an answer with fewer than
two lines, leaves the word out, as in 1c, so without an LLM 3 builds what 1c
builds. A concurrency word inside a decision's branch is not asked about.
"""
import json
import re

from text2bpmn.guardrails import is_else_marker

GATEWAYS = ("exclusiveGateway", "parallelGateway")
LABELS = ("yes", "no", "after")
DECISION_LABELS = ("same", "after")
MAX_STEPS = 8
MAX_ITEMS = 10  # idea 1b: steps and decision mentions
MAIN_LANE = "Main Process"
# idea 3: the steps around a concurrency word
PARALLEL_LABELS = ("before", "a", "b", "c", "after")
LINES = ("a", "b", "c")
MAX_BEFORE = 3
MAX_AFTER = 6

INSTRUCTIONS = """You read a process description in which one decision is marked [D] and the \
steps that follow it are marked [1], [2], and so on.

For each marked step, say whether it is done
- "yes": only when the decision's condition holds,
- "no": only when the condition does not hold,
- "after": after the decision, whatever its outcome.

The first step you mark "after" ends the decision: mark it and every later step "after". \
If the marked words do not choose between alternatives at all, mark every step "after".

Example.
Text: The clerk checks the invoice. [D]If the amount exceeds 500 euros, the manager \
[1]approves it; otherwise the clerk [2]approves it. Then the invoice is [3]paid.
Decision [D]: If the amount exceeds 500 euros
Steps:
[1] Approves it (The manager)
[2] Approves it (The clerk)
[3] Paid the invoice
Answer: {"reasoning": "The manager approves large amounts and the clerk the others; the \
invoice is paid in both cases.", "step_1": "yes", "step_2": "no", "step_3": "after"}

Example.
Text: [D]If the customer is new, the agent [1]creates an account and [2]sends a welcome pack. \
The agent then [3]records the order.
Decision [D]: If the customer is new
Steps:
[1] Creates an account (The agent)
[2] Sends a welcome pack (The agent)
[3] Records the order (The agent)
Answer: {"reasoning": "The account and the welcome pack are for new customers only; every \
order is recorded.", "step_1": "yes", "step_2": "yes", "step_3": "after"}

Answer with JSON only: a short "reasoning", then one key per step, "step_1" to "step_N"."""

INSTRUCTIONS_SAME = """You read a process description in which one decision is marked [D] and \
what follows it is marked [1], [2], and so on: steps of the process, and further decisions.

For each marked step, say whether it is done
- "yes": only in the case named last before it: the condition of [D], or of a later decision \
you marked "same",
- "no": only when the condition of [D] does not hold, for example after "otherwise",
- "after": after the decision, whatever its outcome.

For each marked decision, say whether it is
- "same": another case of the decision [D] ("If it is not in stock" after "If it is in stock"),
- "after": a decision of its own, taken after [D] is settled.

The first item you mark "after" ends the decision: mark it and every later item "after". \
If the words of [D] do not choose between alternatives at all, mark every item "after".

Example.
Text: The clerk checks the invoice. [D]If the amount exceeds 500 euros, the manager \
[1]approves it; otherwise the clerk [2]approves it. Then the invoice is [3]paid.
Decision [D]: If the amount exceeds 500 euros
Marked:
[1] Approves it (The manager)
[2] Approves it (The clerk)
[3] Paid the invoice
Answer: {"reasoning": "The manager approves large amounts and the clerk the others; the \
invoice is paid in both cases.", "step_1": "yes", "step_2": "no", "step_3": "after"}

Example.
Text: [D]If the item is in stock, the clerk [1]ships it. [2]If it is not in stock, the clerk \
[3]orders it and [4]informs the customer. The clerk then [5]sends the invoice.
Decision [D]: If the item is in stock
Marked:
[1] Ships it (The clerk)
[2] decision: If it is not in stock
[3] Orders it (The clerk)
[4] Informs the customer (The clerk)
[5] Sends the invoice (The clerk)
Answer: {"reasoning": "[2] is the other case of the stock decision; ordering and informing \
belong to it; the invoice is sent in both cases.", "step_1": "yes", "step_2": "same", \
"step_3": "yes", "step_4": "yes", "step_5": "after"}

Example.
Text: [D]If the order is urgent, the clerk [1]calls the courier. [2]If the customer is abroad, \
the clerk [3]fills in a customs form.
Decision [D]: If the order is urgent
Marked:
[1] Calls the courier (The clerk)
[2] decision: If the customer is abroad
[3] Fills in a customs form (The clerk)
Answer: {"reasoning": "Whether the customer is abroad does not depend on urgency: [2] is a \
decision of its own.", "step_1": "yes", "step_2": "after", "step_3": "after"}

Answer with JSON only: a short "reasoning", then one key per marked item, "step_1" to "step_N"."""

INSTRUCTIONS_PARALLEL = """You read a process description in which words that may say that \
steps happen at the same time are marked [P], and the steps around them are marked [1], [2], and \
so on.

For each marked step, say whether it is done
- "before": before the steps that happen at the same time begin,
- "a", "b" or "c": in one of the lines of work that run at the same time. Give each line its own \
letter; the steps of one line are done one after another,
- "after": once every line of work is finished.

Only steps at the start can be "before". The first step you mark "after" ends the lines of work: \
mark it and every later step "after". If the marked words do not put any steps side by side, mark \
every step "before".

Example.
Text: The clerk [1]registers the order. [P]In the meantime, the warehouse [2]picks the goods and \
[3]packs them. When both are done, the courier [4]collects the parcel.
Words [P]: In the meantime
Steps:
[1] Registers the order (The clerk)
[2] Picks the goods (The warehouse)
[3] Packs them (The warehouse)
[4] Collects the parcel (The courier)
Answer: {"reasoning": "Registering runs alongside picking and packing, which follow each other; \
the courier comes when both are done.", "step_1": "a", "step_2": "b", "step_3": "b", "step_4": "after"}

Example.
Text: The nurse [1]admits the patient. [P]Two things then happen at once: the doctor \
[2]examines the patient, and the lab [3]tests the blood sample. The doctor then [4]writes the \
diagnosis.
Words [P]: Two things then happen at once
Steps:
[1] Admits the patient (The nurse)
[2] Examines the patient (The doctor)
[3] Tests the blood sample (The lab)
[4] Writes the diagnosis (The doctor)
Answer: {"reasoning": "Admission comes first; the examination and the blood test run side by \
side; the diagnosis needs both.", "step_1": "before", "step_2": "a", "step_3": "b", "step_4": "after"}

Example.
Text: Once the manager [1]approves the budget, [P]three things are done in parallel: the designer \
[2]drafts the layout, the writer [3]writes the text and the buyer [4]orders the paper. The \
brochure is then [5]printed.
Words [P]: three things are done in parallel
Steps:
[1] Approves the budget (The manager)
[2] Drafts the layout (The designer)
[3] Writes the text (The writer)
[4] Orders the paper (The buyer)
[5] Printed the brochure
Answer: {"reasoning": "The budget comes first; layout, text and paper are three lines of work; \
printing waits for all three.", "step_1": "before", "step_2": "a", "step_3": "b", "step_4": "c", \
"step_5": "after"}

Answer with JSON only: a short "reasoning", then one key per step, "step_1" to "step_N"."""


def decision_schema(steps, reasoning_max_chars=None, kinds=None):
    """One key per marked item, closed to the labels of its kind (a step's
    three, or a decision mention's two); `reasoning` first, bounded as the
    relation schema bounds it."""
    kinds = kinds or ["step"] * steps
    reasoning = {"type": "string"}
    if reasoning_max_chars:
        reasoning["maxLength"] = reasoning_max_chars
    keys = [f"step_{k}" for k in range(1, steps + 1)]
    return {"type": "object",
            "properties": {"reasoning": reasoning,
                           **{k: {"type": "string", "enum": list(DECISION_LABELS if kind == "decision" else LABELS)}
                              for k, kind in zip(keys, kinds)}},
            "required": ["reasoning", *keys]}


def marked_text(context, decision, steps, mark="[D]"):
    """The text with [D] (or `mark`) before the decision's span and [k] before
    each step's."""
    marks = [(decision.get("start"), mark)] + [(s.get("start"), f"[{k}]") for k, s in enumerate(steps, 1)]
    text = context
    for at, mark in sorted((m for m in marks if m[0] is not None), reverse=True):
        text = text[:at] + mark + text[at:]
    return text


def question(context, decision, steps, name, lanes, kinds=None):
    """The user message: the marked text, the decision and the numbered items,
    each step with the actor it is in. Without `kinds`, idea 1's wording."""
    lines = [f"Text: {marked_text(context, decision, steps)}",
             f"Decision [D]: {name(decision)}", "Marked:" if kinds else "Steps:"]
    for k, (step, lane, kind) in enumerate(zip(steps, lanes, kinds or ["step"] * len(steps)), 1):
        if kind == "decision":
            lines.append(f"[{k}] decision: {name(step)}")
        else:
            lines.append(f"[{k}] {name(step)}" + (f" ({lane})" if lane and lane != MAIN_LANE else ""))
    return "\n".join(lines)


def parse_answer(content, steps, kinds=None):
    """The labels, one per item, from the model's reply; ValueError if the
    reply is not that."""
    kinds = kinds or ["step"] * steps
    text = content if isinstance(content, str) else (content or {}).get("text", "")
    match = re.search(r"\{.*\}", text or "", re.S)
    if not match:
        raise ValueError(f"no JSON object in the reply: {text!r:.200}")
    answer = json.loads(match.group(0))
    labels = []
    for k, kind in zip(range(1, steps + 1), kinds):
        allowed = DECISION_LABELS if kind == "decision" else LABELS
        label = str(answer.get(f"step_{k}", "")).strip().lower()
        if label not in allowed:
            raise ValueError(f"step_{k} is {answer.get(f'step_{k}')!r}, not one of {allowed}")
        labels.append(label)
    return labels


def branches(labels):
    """(yes, no, first_after): indices into the steps; first_after is None when
    no step is "after"."""
    first_after = next((i for i, label in enumerate(labels) if label == "after"), None)
    region = labels[:first_after] if first_after is not None else labels
    return ([i for i, label in enumerate(region) if label == "yes"],
            [i for i, label in enumerate(region) if label == "no"], first_after)


def ask_llm(lm, context, decision, steps, name, lanes, config, kinds=None):
    """One question to the run's LLM client, with the decision schema in place
    of the relation schema when answers are constrained. Returns the labels;
    raises if the call fails or the reply does not parse. With `kinds`, idea
    1b's question and instructions."""
    instructions = INSTRUCTIONS_SAME if kinds else INSTRUCTIONS
    messages = [{"role": "system", "content": instructions},
                {"role": "user", "content": question(context, decision, steps, name, lanes, kinds)}]
    options = {}
    if config.constrained_output:
        options["response_format"] = {"type": "json_schema", "json_schema": {
            "name": "decision", "schema": decision_schema(len(steps), config.reasoning_max_chars, kinds)}}
    reply = lm(messages=messages, **options)
    return parse_answer(reply[0] if reply else "", len(steps), kinds)


# --- idea 3: the concurrency question ------------------------------------------

def parallel_schema(steps, reasoning_max_chars=None):
    """As decision_schema, each key closed to PARALLEL_LABELS."""
    reasoning = {"type": "string"}
    if reasoning_max_chars:
        reasoning["maxLength"] = reasoning_max_chars
    keys = [f"step_{k}" for k in range(1, steps + 1)]
    return {"type": "object",
            "properties": {"reasoning": reasoning, **{k: {"type": "string", "enum": list(PARALLEL_LABELS)}
                                                      for k in keys}},
            "required": ["reasoning", *keys]}


def parallel_question(context, cue, steps, name, lanes):
    """The user message: the text with [P] and the steps marked, the words,
    and the numbered steps with the actor each is in."""
    lines = [f"Text: {marked_text(context, cue, steps, '[P]')}", f"Words [P]: {name(cue)}", "Steps:"]
    for k, (step, lane) in enumerate(zip(steps, lanes), 1):
        lines.append(f"[{k}] {name(step)}" + (f" ({lane})" if lane and lane != MAIN_LANE else ""))
    return "\n".join(lines)


def parse_parallel(content, steps):
    """The labels, one per step; ValueError if the reply is not that."""
    text = content if isinstance(content, str) else (content or {}).get("text", "")
    match = re.search(r"\{.*\}", text or "", re.S)
    if not match:
        raise ValueError(f"no JSON object in the reply: {text!r:.200}")
    answer = json.loads(match.group(0))
    labels = []
    for k in range(1, steps + 1):
        label = str(answer.get(f"step_{k}", "")).strip().lower()
        if label not in PARALLEL_LABELS:
            raise ValueError(f"step_{k} is {answer.get(f'step_{k}')!r}, not one of {PARALLEL_LABELS}")
        labels.append(label)
    return labels


def parallel_lines(labels):
    """(start, lines, end): the index of the first step in a line of work, each
    line's step indices in text order, and the index of the first "after" step
    (len(labels) when there is none). None when fewer than two lines are named
    before the first "after", or a "before" step comes after a line has begun."""
    end = next((i for i, label in enumerate(labels) if label == "after"), len(labels))
    start = next((i for i in range(end) if labels[i] in LINES), None)
    if start is None or "before" in labels[start:end]:
        return None
    lines = [[i for i in range(start, end) if labels[i] == letter] for letter in LINES]
    lines = [line for line in lines if line]
    return (start, lines, end) if len(lines) >= 2 else None


def ask_parallel_llm(lm, context, cue, steps, name, lanes, config):
    """One concurrency question to the run's LLM client, as ask_llm."""
    messages = [{"role": "system", "content": INSTRUCTIONS_PARALLEL},
                {"role": "user", "content": parallel_question(context, cue, steps, name, lanes)}]
    options = {}
    if config.constrained_output:
        options["response_format"] = {"type": "json_schema", "json_schema": {
            "name": "parallel", "schema": parallel_schema(len(steps), config.reasoning_max_chars)}}
    reply = lm(messages=messages, **options)
    return parse_parallel(reply[0] if reply else "", len(steps))


def parallel_plan(nodes, cues, decisions, ask):
    """{position where a block starts: its plan} for every concurrency word
    whose answer names two lines of work or more. A plan has the word's
    gateway element, each line's step positions, and the position where the
    flow goes on. No step of a block is a decision, is in a decision's
    branches (decisions: the decision plans) or is in an earlier block.
    cues: (entity, element, position of the first node after it).
    ask(cue entity, step entities, step lanes) gives the labels or None."""
    taken = {k for k, (_, element) in enumerate(nodes) if element["type"] in GATEWAYS}
    for k, p in decisions.items():
        taken.update(range(k, p["goes_on"]))
    blocks = {}
    for entity, gateway, at in cues:
        before, j = [], at - 1
        while j >= 0 and j not in taken and len(before) < MAX_BEFORE:
            before.insert(0, j)
            j -= 1
        after, j = [], at
        while j < len(nodes) and j not in taken and len(after) < MAX_AFTER:
            after.append(j)
            j += 1
        window = before + after
        if len(window) < 2:
            continue
        labels = ask(entity, [nodes[j][0] for j in window], [nodes[j][1]["lane"] for j in window])
        found = parallel_lines(labels) if labels is not None else None
        if found is None:
            continue
        start, lines, end = found
        goes_on = window[end] if end < len(window) else window[-1] + 1
        blocks[window[start]] = {"gateway": gateway, "lines": [[window[i] for i in line] for line in lines],
                                 "goes_on": goes_on}
        taken.update(range(window[start], goes_on))
    return blocks


def nodes_in_order(entities, drop_and_mentions=False, cues=None):
    """(entity, element) for every entity that becomes a node, in text order,
    each in the lane in force at its position, as the pairwise mode's chain
    puts it; and the participants. Idea 1c leaves AND Gateway mentions out;
    given a list as `cues`, idea 3 keeps each there as (entity, element,
    position of the first node after it)."""
    lane, participants, nodes, last_gateway = MAIN_LANE, {MAIN_LANE}, [], None
    for e in entities:
        if e["type"] == "Lane":
            if not e.get("recipient"):
                lane = e["clean_name"]
                participants.add(lane)
            continue
        if e.get("lane_hint"):
            lane = e["lane_hint"]
            participants.add(lane)
        if is_else_marker(e["word"]) and e["type"] in GATEWAYS and last_gateway is not None:
            continue  # the decision before it carries its branch
        element = {"id": e["id"], "name": e["clean_name"], "type": e["type"], "lane": lane,
                   "metadata": e.get("metadata", [])}
        if drop_and_mentions and e["type"] == "parallelGateway":
            if cues is not None:
                cues.append((e, element, len(nodes)))
            continue
        nodes.append((e, element))
        if e["type"] in GATEWAYS:
            last_gateway = e["id"]
    return nodes, participants


def _decision_plan(cases, no, goes_on, absorbed=()):
    return {"cases": cases, "no": no, "goes_on": goes_on, "absorbed": set(absorbed)}


def plan(nodes, ask, alternatives=False):
    """{position of a decision: its plan} for every decision whose answer
    branches. A plan has the decision's cases, each (flow name, relation,
    positions of its steps), the positions of the steps done when it does
    not hold, the position where the flow goes on, and, in idea 1b, the
    positions of the decision mentions it absorbed. ask(decision entity, item
    entities, item lanes[, item kinds]) gives the labels or None."""
    plans, absorbed = {}, set()
    for k, (entity, element) in enumerate(nodes):
        if element["type"] != "exclusiveGateway" or k in absorbed:
            continue
        window = []
        for j in range(k + 1, len(nodes)):
            kind = nodes[j][1]["type"]
            if alternatives:
                if kind == "parallelGateway" or len(window) == MAX_ITEMS:
                    break
            elif kind in GATEWAYS or len(window) == MAX_STEPS:
                break
            window.append(j)
        if not window:
            continue
        items = [nodes[j][0] for j in window]
        lanes = [nodes[j][1]["lane"] for j in window]
        if not alternatives:
            labels = ask(entity, items, lanes)
            if labels is None:
                continue
            yes, no, first_after = branches(labels)
            if not yes and not no:
                continue
            goes_on = window[first_after] if first_after is not None else window[-1] + 1
            plans[k] = _decision_plan([("Yes", "TRUE_BRANCH", [window[i] for i in yes])],
                                      [window[i] for i in no], goes_on)
            continue
        kinds = ["decision" if nodes[j][1]["type"] == "exclusiveGateway" else "step" for j in window]
        labels = ask(entity, items, lanes, kinds)
        if labels is None:
            continue
        cases, no, mentions, goes_on = [("Yes", "TRUE_BRANCH", [])], [], [], window[-1] + 1
        for j, label in zip(window, labels):
            if label == "after":
                goes_on = j
                break
            if label == "same":
                mentions.append(j)
                cases.append((nodes[j][1]["name"], "TRUE_BRANCH", []))
            elif label == "yes":
                cases[-1][2].append(j)
            else:
                no.append(j)
        if not no and not any(steps for _, _, steps in cases):
            continue
        plans[k] = _decision_plan(cases, no, goes_on, mentions)
        absorbed.update(mentions)
    return plans


def build(entities, ask, alternatives=False, drop_and_mentions=False, ask_parallel=None, gate=False):
    """finder3's process data ({participants, elements, flows}) from the
    prepared entities: the text-order chain, with each answered decision's
    branches split off it and joined again, and, given ask_parallel (idea 3),
    each answered concurrency word's lines of work. With `gate`, a model that
    is not sound is taken back to one that is (text2bpmn/soundness_gate.py)."""
    cues = [] if ask_parallel else None
    nodes, participants = nodes_in_order(entities, drop_and_mentions, cues)
    plans = plan(nodes, ask, alternatives)
    blocks = parallel_plan(nodes, cues, plans, ask_parallel) if ask_parallel else {}
    data = assemble(nodes, participants, plans, blocks)
    return gated(nodes, participants, plans, blocks, data) if gate else data


def gated(nodes, participants, plans, blocks, data):
    """The soundness gate: while the model is not sound, undo the riskiest of
    what was built, the parallel blocks first and then the decisions' branches,
    the last of each first. The record goes into the data as `soundness_gate`."""
    from text2bpmn.soundness_gate import verdict

    first = verdict(data)
    found, dropped = first, []
    plans, blocks = dict(plans), dict(blocks)
    while not found["sound"] and (blocks or plans):
        if blocks:
            k = max(blocks)
            dropped.append({"parallel block": blocks.pop(k)["gateway"]["name"]})
        else:
            k = max(plans)
            plans.pop(k)
            dropped.append({"decision": nodes[k][1]["name"]})
        data = assemble(nodes, participants, plans, blocks)
        found = verdict(data)
    data["soundness_gate"] = {"sound": bool(found["sound"]), "as_built": first, "undone": dropped}
    return data


def assemble(nodes, participants, plans, blocks):
    """The process data from the nodes in text order, the decisions' plans and
    the parallel blocks."""
    elements = [{"id": "StartEvent_1", "name": "Start", "type": "startEvent", "lane": MAIN_LANE}]
    flows, added = [], set()

    def add(position):
        element = nodes[position][1]
        if element["id"] not in added:
            added.add(element["id"])
            elements.append(element)
        return element["id"]

    def link(source, target, name="", relation="SEQUENCE"):
        flows.append({"id": f"Flow_{len(flows) + 1:04d}", "source": source, "target": target,
                      "name": name, "relation": relation})

    waiting = [("StartEvent_1", "", "SEQUENCE")]  # sources the next node continues from
    k = 0
    while k < len(nodes):
        if k in blocks:  # idea 3: a parallel split, its lines, and on at the first "after" step
            b = blocks[k]
            split = b["gateway"]["id"]
            elements.append(b["gateway"])
            added.add(split)
            for source, name, relation in waiting:
                link(source, split, name, relation)
            waiting = []
            for line in b["lines"]:
                link(split, add(line[0]))
                for a, c in zip(line, line[1:]):
                    link(add(a), add(c))
                waiting.append((add(line[-1]), "", "SEQUENCE"))
            k = b["goes_on"]
            continue
        node = add(k)
        for source, name, relation in waiting:
            link(source, node, name, relation)
        waiting = [(node, "", "SEQUENCE")]
        if k not in plans:
            k += 1
            continue
        p = plans[k]
        waiting = []
        several = len(p["cases"]) > 1
        for branch, name, relation in [(steps, name, relation) for name, relation, steps in p["cases"]] + \
                                      [(p["no"], "No", "FALSE_BRANCH")]:
            if not branch:
                if not (several and relation == "FALSE_BRANCH"):
                    waiting.append((node, name, relation))  # the outcome that does nothing
                continue
            link(node, add(branch[0]), name, relation)
            for a, b in zip(branch, branch[1:]):
                link(add(a), add(b))
            waiting.append((add(branch[-1]), "", "SEQUENCE"))
        k = p["goes_on"]

    end_lane = elements[-1].get("lane", MAIN_LANE)
    elements.append({"id": "EndEvent_1", "name": "End", "type": "endEvent", "lane": end_lane})
    for source, name, relation in waiting:
        link(source, "EndEvent_1", name, relation)
    sources = {f["source"] for f in flows}
    for element in elements:
        if element["type"] != "endEvent" and element["id"] not in sources:
            link(element["id"], "EndEvent_1")
    unique = {}
    for flow in flows:  # one flow per pair, the labelled one
        key = (flow["source"], flow["target"])
        if key not in unique or (flow["name"] and not unique[key]["name"]):
            unique[key] = flow
    return {"participants": sorted(participants), "elements": elements, "flows": list(unique.values())}
