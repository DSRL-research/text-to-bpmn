import argparse
import uuid
import re
import spacy
import os
# torch, transformers and fastcoref are imported where they are used, not here.
# With spans injected from outside, neither the entity recogniser nor the
# coreference model runs, so a run needs neither library nor the 1.1 GB
# checkpoint; importing them at module level made every such run pay for all
# three. See text2bpmn/remote/README.md.

# --- NEW: Ontology Import ---
try:
    from owlready2 import *
except ImportError:
    print("⚠️ 'owlready2' not found. Ontology enrichment will be disabled.")
    print("   pip install owlready2")

import dspy
from dspy.teleprompt import LabeledFewShot
import json
import random
from pathlib import Path

from text2bpmn.cues import has_parallel_cue
from text2bpmn.guardrails import false_branch_guardrail, is_else_marker
from text2bpmn.prompts import DEFAULT_PROMPT, DEMONSTRATIONS, PROMPTS, load_demonstrations
from text2bpmn.relation_parsing import ParseFailureLog
from text2bpmn.run_config import RunConfig, add_arguments, from_arguments

# --- DSPy Configuration & Classes ---

# The signature's instructions are the prompt. They are not written here but
# taken by name from text2bpmn/prompts.py (RunConfig.prompt), so a run can use
# the text that produced a published number and records which one it used.
class BPMNFlowClassifier(dspy.Signature):
    context = dspy.InputField(desc="The natural language description of the process fragment.")
    node_A = dspy.InputField(desc="The source activity, gateway, or event.")
    node_B = dspy.InputField(desc="The target activity, gateway, or event.")
    relation = dspy.OutputField(desc="The relationship type. Options: [SEQUENCE, TRUE_BRANCH, FALSE_BRANCH, PARALLEL, CONDITION_DEF]")


class BPMNFlowClassifierNone(dspy.Signature):
    """Relation idea 2: the same fields, with NONE among the options."""
    context = dspy.InputField(desc="The natural language description of the process fragment.")
    node_A = dspy.InputField(desc="The source activity, gateway, or event.")
    node_B = dspy.InputField(desc="The target activity, gateway, or event.")
    relation = dspy.OutputField(desc="The relationship type. Options: [SEQUENCE, TRUE_BRANCH, FALSE_BRANCH, "
                                     "PARALLEL, CONDITION_DEF, NONE]")


def relation_signature(prompt=DEFAULT_PROMPT, none=False):
    """BPMNFlowClassifier with the named prompt as its instructions; with
    `none`, the signature whose options include NONE (relation idea 2)."""
    return (BPMNFlowClassifierNone if none else BPMNFlowClassifier).with_instructions(PROMPTS[prompt])

RELATION_LABELS = ("SEQUENCE", "TRUE_BRANCH", "FALSE_BRANCH", "PARALLEL", "CONDITION_DEF")
# relation idea 2 (relation_mode "pairs2"): a pair may also be not directly connected
RELATION_LABELS_NONE = RELATION_LABELS + ("NONE",)


def labels_for(config):
    return RELATION_LABELS_NONE if config.relation_mode == "pairs2" else RELATION_LABELS


def relation_schema(reasoning_max_chars=None, labels=RELATION_LABELS):
    """The shape ChainOfThought asks for, with the answer field closed to the
    five labels.

    `reasoning` stays first: it is what the method does, and reordering it
    would make the thinking follow the answer rather than produce it. With
    `reasoning_max_chars` the server's grammar closes the string at that
    length and must then emit the answer, so a reply can neither deliberate
    without end nor stop before answering: Qwen3.5-27B, with thinking off,
    wrote about 10,000 characters of reasoning for one PET pair and timed out
    on 11 of 123 (2026-11-04).
    """
    reasoning = {"type": "string"}
    if reasoning_max_chars:
        reasoning["maxLength"] = reasoning_max_chars
    return {"type": "object",
            "properties": {"reasoning": reasoning,
                           "relation": {"type": "string", "enum": list(labels)}},
            "required": ["reasoning", "relation"]}


class SchemaJSONAdapter(dspy.JSONAdapter):
    """JSONAdapter's prompt and parsing, one call per pair, and the LM's own
    response_format left in place.

    Without it, constrained output did not constrain the answer that was used.
    DSPy's default ChatAdapter expects `[[ ## relation ## ]]` markers, cannot
    read the JSON the schema forces, and so discarded every answer and asked
    again through JSONAdapter -- which replaces the schema with plain JSON
    mode for any server litellm does not list as supporting schemas, vLLM
    among them. Every pair cost two generations, and the answer kept came
    from the unconstrained second one (found 2026-11-04: a kept answer closed
    its JSON with no `relation` field, which the schema does not allow).

    Here the call goes straight to the base adapter: one request, decoded
    against the schema in the LM's settings, and a reply that does not parse
    is a failure, not a second request.
    """

    def __call__(self, lm, lm_kwargs, signature, demos, inputs):
        return dspy.Adapter.__call__(self, lm, lm_kwargs, signature, demos, inputs)

    async def acall(self, lm, lm_kwargs, signature, demos, inputs):
        return await dspy.Adapter.acall(self, lm, lm_kwargs, signature, demos, inputs)


def build_lm(config):
    """The relation classifier's LLM client, from the run's settings. The
    pipeline and the relation benchmark both build it here, so one run
    configuration means the same requests in both."""
    options = {}
    if config.disable_thinking:
        options["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
        print("     Thinking disabled via chat_template_kwargs.")
    if config.constrained_output:
        options["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "relation",
                            "schema": relation_schema(config.reasoning_max_chars, labels_for(config))}}
        print(f"     Answers constrained by schema: one of {len(labels_for(config))} labels, "
              f"reasoning at most {config.reasoning_max_chars} characters.")
    if config.max_tokens:
        options["max_tokens"] = config.max_tokens
    return dspy.LM(model=config.llm_model, api_base=config.api_base, api_key=config.api_key,
                   temperature=config.temperature, seed=config.seed, timeout=config.llm_timeout,
                   num_retries=0, cache=config.llm_cache, **options)


def configure_dspy(config):
    """Point DSPy at the run's LLM, with the adapter its settings need.

    Constrained output needs SchemaJSONAdapter; otherwise DSPy's default
    ChatAdapter, which falls back to JSON only when a reply does not parse.
    The pipeline and the relation benchmark both configure DSPy here.
    """
    adapter = SchemaJSONAdapter() if config.constrained_output else None
    dspy.settings.configure(lm=build_lm(config), adapter=adapter)
    return adapter


class BPMNRelationPredictor(dspy.Module):
    def __init__(self, prompt=DEFAULT_PROMPT, none=False):
        super().__init__()
        self.prog = dspy.ChainOfThought(relation_signature(prompt, none))
        
    def forward(self, context, node_A, node_B):
        return self.prog(context=context, node_A=node_A, node_B=node_B)


# NER model. bert_ner_315_dev60 (text2bpmn/train_ner.py, 2026-11-09) is trained
# on the 315 sentences of text2bpmn/clean_split.py, with its epoch chosen on the
# 60 development sentences, so the held-out split played no part in training or
# selection; its record is text2bpmn/baselines/bert_ner_315_dev60/. It emits the
# whole PET label set. checkpoint-564, the default from 2026-09-30 to
# 2026-11-09, has the same recipe but trained on all 375 sentences and was
# early-stopped and selected on the held-out split itself; it stays under
# my_final_benchmark/ for traceability. checkpoint-168, used until 2026-09-30,
# was trained on ~90 sentences with four labels
# (text2bpmn/results/eval_ner_checkpoint-168.md). Paths are relative to the
# repo root.
NER_MODEL_PATH = "./process-visualizer/src/token_classification_alex/bert_ner_315_dev60"
# Tokens shared by consecutive 512-token windows when a text is longer than one
NER_STRIDE = 128

GATEWAY_TYPES = ("exclusiveGateway", "parallelGateway")

# The seven PET mention types: what the recogniser emits and the only labels
# this pipeline handles. A span with any other label stops the run; the labels
# of older checkpoints (TASK_INFO, TASK, AGENT, CONDITION) used to be accepted
# here, and an unhandled one would silently have become a task.
PET_LABELS = ("Activity", "Activity Data", "Actor", "Further Specification",
              "XOR Gateway", "AND Gateway", "Condition Specification")
# Entity labels that describe an activity instead of being one (paper Sec. 4.1).
METADATA_LABELS = ("Activity Data", "Further Specification")
# PET marks the verb as the Activity and its object as Activity Data, so a task
# label needs both: "Prepared" + "the acceptance pack". Any further object stays
# as documentation.
OBJECT_LABELS = ("Activity Data",)
# The condition of a gateway, not a gateway itself.
CONDITION_LABELS = ("Condition Specification",)
NER_GATEWAY_LABELS = ("XOR Gateway", "AND Gateway")

# A span that is nothing but an else-marker ("Otherwise", "Else") is the point
# the false branch leaves from, never a step of its own.
# An actor the action is directed at is not the actor performing it. Which
# words mark that is measured against PET's actor-recipient relations
# (provenance/pet_rules_benchmark.md): "to" precedes 81 recipients and 6
# performers, while "from" precedes 4 performers and no recipient, so it is not
# here. A communication verb directly before an actor marks a recipient too --
# "informs the INQ" -- and accounts for 31 of the cases the prepositions miss.
RECIPIENT_PREPOSITIONS = ("to", "for")
RECIPIENT_VERBS = ("inform", "informs", "informed", "notify", "notifies", "notified",
                   "tell", "tells", "told", "advise", "advises", "advised")

# Where _post_process_split cuts an Activity span: after a sentence end, and
# around an "otherwise" inside it, which becomes a mention of its own. Only the
# one cue of text2bpmn.guardrails.FALSE_BRANCH_MARKERS that cannot also be part
# of a step: "else" in "asks someone else" and "if not" in "if not already
# registered" are not markers there.
ELSE_WORD = re.compile(r"\botherwise\b", re.I)
SPLIT_POINT = re.compile(r"[.?!](?=\s|$)|\botherwise\b", re.I)
PIECE_TRIM = " \t\n,;:.-"


def check_labels(entities):
    """Stop on a span whose label is not one of the seven PET types."""
    unknown = sorted({e['entity_group'] for e in entities} - set(PET_LABELS))
    if unknown:
        raise ValueError(f"entity labels outside the PET scheme: {unknown}. This pipeline "
                         f"handles {list(PET_LABELS)}; checkpoint-168's TASK_INFO is not "
                         f"supported (the submitted finder3.py in the repository root is).")

class SkipOntology(Exception):
    """No ontology output path was given."""


POSSESSIVE_PRONOUNS = {"his", "her", "hers", "its", "their", "theirs"}
PRONOUNS = {"he", "him", "she", "it", "they", "them", "this", "that", "these", "those",
            "himself", "herself", "itself", "themselves", "who"} | POSSESSIVE_PRONOUNS


class BPMNHybridExtractor:
    def __init__(self, ner_model_path=NER_MODEL_PATH, rel_model_path="./bert-relation-classifier",
                 config=None):
        print(f"🚀 Loading AI Engine (Finder 3.0)...")
        # Seed, LLM settings and the record written with every run (ticket C9)
        self.config = (config or RunConfig()).apply()
        self.config.ner_model_path = ner_model_path or "(spans injected)"
        self.relation_log = ParseFailureLog(labels_for(self.config))

        # 1. Load Token Classification (NER) Model, unless spans are injected
        self.ner_pipeline = None
        if ner_model_path:
            import torch
            from transformers import pipeline
            print(f"   - Loading NER from {ner_model_path}...")
            # stride: a text longer than the model's 512 tokens is read in
            # overlapping windows. Without it everything past the 512th token
            # was dropped without a message, the last third of PET's longest
            # documents among it; a text that fits one window is unchanged.
            self.ner_pipeline = pipeline(
                "token-classification",
                model=ner_model_path,
                aggregation_strategy="simple",
                stride=NER_STRIDE,
                device=0 if torch.cuda.is_available() else -1
            )

        # 2. Load Relation Extraction Model (The Logic Engine)
        # 2. Initialize DSPy Logic Engine (Replacing BERT)
        print(f"   - Initializing DSPy Logic Engine...")
        # Outside the try below: a missing or malformed file is an error, not
        # a zero-shot run that reports nothing about it
        train_examples = load_demonstrations(DEMONSTRATIONS)
        print(f"     Loaded {len(train_examples)} demonstrations from {DEMONSTRATIONS}.")
        # No try/except here: a setup failure used to leave the predictor unset,
        # and the run carried on with every relation UNKNOWN
        configure_dspy(self.config)

        # Compile Predictor
        uncompiled_predictor = BPMNRelationPredictor(self.config.prompt,
                                                     none=self.config.relation_mode == "pairs2")
        teleprompter = LabeledFewShot(k=self.config.few_shot_k)
        self.dspy_predictor = teleprompter.compile(student=uncompiled_predictor, trainset=train_examples)

        # Which model answers, by digest, and which commit and tag asked it
        self.run_record = self.config.describe()
        self.config.require_llm(self.run_record)
        print("     ✅ DSPy Engine Ready.")
        print(f"     Run: seed {self.config.seed}, temperature {self.config.temperature}, "
              f"prompt {self.config.prompt}, cache {self.config.llm_cache}, "
              f"model {self.run_record['llm']}")


        # 3. Coreference resolution, loaded on first use: a run with injected
        # spans never resolves pronouns, because the offsets it is given refer
        # to the text as it stands.
        self._coref_model = None

        print("🧠 Loading Linguistic Validator...")
        # 4. Load Spacy for Verb/Noun checking
        try:
            self.nlp_validator = spacy.load("en_core_web_sm")
        except OSError:
            print("⚠️ Spacy model 'en_core_web_sm' not found. Downloading...")
            from spacy.cli import download
            download("en_core_web_sm")
            self.nlp_validator = spacy.load("en_core_web_sm")
        
        # 5. Initialize Ontology Populator
        self.ontology_file = self.config.ontology_file
        if os.path.exists(self.ontology_file):
            print(f"📚 Ontology file found: {self.ontology_file}")
        else:
            print(f"⚠️ Ontology file not found: {self.ontology_file}")

    @property
    def coref_model(self):
        """Loaded the first time a pronoun is resolved, not at construction.

        A run with injected spans never resolves pronouns, so it never pays for
        fastcoref or the CUDA stack underneath it.
        """
        if getattr(self, "_coref_model", None) is None:
            import torch
            from fastcoref import FCoref
            print("🔗 Loading Coreference Engine...")
            self._coref_model = FCoref(device='cuda:0' if torch.cuda.is_available() else 'cpu')
        return self._coref_model

    @coref_model.setter
    def coref_model(self, model):
        self._coref_model = model

    def resolved_text(self, text):
        """The text the entity recogniser sees: pronouns replaced, whitespace
        normalised. Exposed so another recogniser can be run on the same string
        and its character offsets still line up."""
        return " ".join(self._resolve_coreferences(text).split())

    def process_text(self, text, entities=None):
        """Structure a description.

        `entities` injects spans from a recogniser that cannot run in this
        process -- GLiNER needs a newer `transformers` than the rest of this
        pipeline -- as {"text": the resolved text, "spans": [{start, end,
        label, score}]}. The text must be the one those offsets refer to, and
        it is used as the context, so the two recognisers are compared on
        identical input.
        """
        print(f"\n--- Processing Input ---")
        self.relation_log = ParseFailureLog(labels_for(self.config))  # per document

        if entities is not None:
            clean_text = entities["text"]
            raw_entities = [{"entity_group": s["label"], "word": clean_text[s["start"]:s["end"]],
                             "start": int(s["start"]), "end": int(s["end"]),
                             "score": float(s.get("score", 1.0))}
                            for s in sorted(entities["spans"], key=lambda s: s["start"])]
            print(f"   (Debug) Injected {len(raw_entities)} spans from "
                  f"{entities.get('source', 'a file')}")
            # the text the offsets refer to, as the line below gives it for the
            # pipeline's own recogniser (text2bpmn.lane_accuracy reads both)
            print(f"   (Debug) Injected text: {clean_text}")
        else:
            # Step 1: Resolve Pronouns ("He" -> "The Manager")
            clean_text = self.resolved_text(text)
            print(f"   (Debug) Coref Resolved: {clean_text}")

            # Step 2: Extract Entities using AI Model
            raw_entities = self.ner_pipeline(clean_text)
        print(f"   (Debug) Raw Entities: {[e['word'] for e in raw_entities]}")
        check_labels(raw_entities)
        
        if entities is not None:
            # Injected spans skip the repair steps below. Merging word pieces,
            # snapping to word boundaries and splitting across a full stop all
            # exist to fix what token classification does to a span, and they
            # move its offsets; a span given from outside is already whole, and
            # its offsets are what the caller will compare against.
            split_entities = raw_entities
        else:
            # Step 3: Fix Tokenization Artifacts ("##ing")
            cleaned_entities = self._snap_to_words(self._merge_subwords(raw_entities), clean_text)
            print(f"   (Debug) Cleaned Entities: {[e['word'] for e in cleaned_entities]}")

            # Step 3.5: Post-Process (Split merged entities)
            # "Sends email. Otherwise rejected" -> [Sends email, Otherwise, rejected]
            split_entities = self._post_process_split(cleaned_entities)
        
        print("\n--- Split Entities ---")
        print(split_entities)

        # Step 4: Build BPMN Structure (Logic & Linking)
        process_data = self._structure_process_data(split_entities, clean_text)
        
        # Step 5: Ontology Enrichment, only when a path to write to was given
        try:
             if not self.config.ontology_out:
                 raise SkipOntology()
             self._populate_ontology(process_data)
             print(f"✅ Ontology Enrichment Complete: {self.config.ontology_out}")
        except SkipOntology:
             pass
        except Exception as e:
             print(f"❌ Ontology Enrichment Failed: {e}")
             import traceback
             traceback.print_exc()

        parsing = self.relation_log.summary()
        print(f"   Relation parse failures: {parsing['failures']}/{parsing['calls']}")
        return {
            "structured_data": process_data,
            # which span became which element, so a span-level annotation can be
            # compared with the model the pipeline built from it
            "entities_used": [{"start": e.get("start"), "end": e.get("end"),
                               "label": e.get("entity_group"), "id": e.get("id"),
                               "type": e.get("type"), "name": e.get("clean_name")}
                              for e in split_entities],
            "relation_parsing": parsing,
            "run_config": getattr(self, "run_record", None) or self.config.describe()
        }

    # ... [Same helper methods as finder2.py] ...
    def _resolve_coreferences(self, text):
        """Replace pronouns with the entity they refer to.

        Only pronouns are rewritten. The original replaced every mention in a
        cluster with its head, so a single clustering error renamed an actor:
        FastCoref grouped "the Loan Officer" with "The Financial Officer", and
        every activity after that point moved into the wrong lane.
        """
        try:
            preds = self.coref_model.predict(texts=[text])
            clusters = preds[0].get_clusters(as_strings=False)
            replacements = []
            for cluster in clusters:
                spans = [(start, end) for start, end in cluster]
                antecedent = next((text[start:end] for start, end in spans
                                   if not self._is_pronoun(text[start:end])), None)
                if antecedent is None:
                    continue  # pronouns all the way down; nothing to resolve to
                for start, end in spans:
                    mention = text[start:end]
                    if not self._is_pronoun(mention):
                        continue
                    replacement = antecedent
                    if mention.strip().lower() in POSSESSIVE_PRONOUNS:
                        replacement += "'s"
                    replacements.append((start, end, replacement))
            replacements.sort(key=lambda r: r[0], reverse=True)
            resolved_text = list(text)
            for start, end, replacement in replacements:
                resolved_text[start:end] = list(replacement)
            return "".join(resolved_text)
        except Exception as e:
            print(f"⚠️ Coref Warning: {e}")
            return text

    @staticmethod
    def _is_pronoun(span):
        words = span.strip().lower().split()
        return len(words) == 1 and words[0].strip(".,;:'\"") in PRONOUNS

    def _merge_subwords(self, entities):
        merged = []
        for curr in entities:
            if not merged:
                merged.append(curr)
                continue
            prev = merged[-1]
            is_subword = curr['word'].startswith("##")
            same_label = (prev['entity_group'] == curr['entity_group'])
            if same_label and is_subword:
                clean_word = curr['word'].replace("##", "")
                if is_subword: prev['word'] += clean_word
                else: prev['word'] += " " + clean_word
                prev['end'] = curr['end'] 
                prev['score'] = max(prev['score'], curr['score'])
            else:
                curr['word'] = curr['word'].replace("##", "")
                merged.append(curr)
        return merged

    @staticmethod
    def _snap_to_words(entities, text):
        """Extend every span to whole words.

        Token classification tags word pieces, and a word whose middle piece is
        tagged differently comes back cut: "clarifies" was returned as "c" +
        "##ifies", which merge to "cifies". A span that starts or ends inside a
        word is extended to the word's own boundaries and re-read from the text.
        """
        for e in entities:
            if e.get("start") is None or e.get("end") is None:
                continue
            start, end = e["start"], e["end"]
            while start > 0 and not text[start - 1].isspace():
                start -= 1
            while end < len(text) and not text[end].isspace():
                end += 1
            e["start"], e["end"], e["word"] = start, end, text[start:end]
        return entities

    def _post_process_split(self, entities):
        """Split an Activity span that runs across a sentence end or swallows an
        else-marker.

        The marker becomes a mention of its own, labelled XOR Gateway as PET
        labels it (12 of its 13 gold occurrences of "otherwise"), so the
        else-marker handling and the FALSE_BRANCH guardrail see it. Before, it
        stayed inside the following Activity piece, whose cleaning then cut it
        off at the verb: "Sends email. Otherwise rejected" became "Sends email"
        and "Rejected", with no marker left. Each piece gets its own offsets;
        the pieces used to keep the whole span's.
        """
        final_entities = []
        for ent in entities:
            if ent['entity_group'] != "Activity":
                final_entities.append(ent)
                continue
            pieces = self._split_activity(ent)
            if len(pieces) > 1:
                print(f"   ✂️ Splitting Merged Entity: {ent['word']!r} -> "
                      f"{[(p['entity_group'], p['word']) for p in pieces]}")
            final_entities.extend(pieces)
        return final_entities

    @staticmethod
    def _split_activity(ent):
        text, base = ent['word'], ent.get('start')
        bounds, position = [], 0
        for cut in SPLIT_POINT.finditer(text):
            bounds.append((position, cut.start(), "Activity"))
            if ELSE_WORD.fullmatch(cut.group()):
                bounds.append((cut.start(), cut.end(), "XOR Gateway"))
            position = cut.end()
        bounds.append((position, len(text), "Activity"))
        if len(bounds) == 1:
            return [ent]
        pieces = []
        for start, end, group in bounds:
            while start < end and text[start] in PIECE_TRIM:
                start += 1
            while end > start and text[end - 1] in PIECE_TRIM:
                end -= 1
            if start == end:
                continue
            piece = dict(ent, word=text[start:end], entity_group=group)
            if base is not None:
                piece['start'], piece['end'] = base + start, base + end
            pieces.append(piece)
        return pieces

    def _relation_needed(self, current, candidate, context, neighbour=False):
        """Whether this pair's answer can change the model.

        Relation idea 2 (relation_mode "pairs2") asks only about the element
        right after `current` and about pairs with a gateway in them, whatever
        `parallel_detection` says: two steps further apart than that are not
        directly connected unless a decision connects them.
        """
        if self.config.relation_mode == "pairs2":
            return neighbour or current['type'] in GATEWAY_TYPES or candidate['type'] in GATEWAY_TYPES
        return self._relation_needed_as_submitted(current, candidate, context)

    def _relation_needed_as_submitted(self, current, candidate, context):
        """The rule of the method as submitted.

        It can when either side is a gateway (the branch patterns and the type
        correction read it), or when the pair may form a parallel block. Asking
        about every remaining pair is waste (ticket C8), so concurrency is
        looked for where the text signals it, unless `parallel_detection` says
        "all" or "off".
        """
        if current['type'] in GATEWAY_TYPES or candidate['type'] in GATEWAY_TYPES:
            return True
        mode = self.config.parallel_detection
        if mode == "all":
            return True
        if mode == "cues":
            return has_parallel_cue(context, current, candidate)
        return False

    def _filter_parallel(self, current, peers, context, previous_node_id, data):
        """Which PARALLEL answers may actually form a block.

        One answer in one direction, with nothing in the text to support it, is
        thin evidence for a construct as consequential as a parallel block: in
        the goods dispatch case it produced twelve parallel gateways where the
        reference has two. Each guard is separate so its effect is reportable.
        """
        if not peers:
            return peers
        config = self.config

        if config.parallel_anchor_guard and previous_node_id:
            # a step the sequence already arrives at is a successor, not the head
            # of a concurrent region: "Invites three" then "Selects one"
            arrives = any(f['target'] == current['id']
                          and f.get('relation') in (None, "SEQUENCE")
                          for f in data['flows'])
            if arrives and any(f['source'] == previous_node_id
                               and f['target'] == current['id'] for f in data['flows']):
                print(f"   ⛔ not anchoring a block on '{current['clean_name']}': "
                      f"it already follows another step")
                return []

        kept = []
        for peer in peers:
            if config.parallel_require_cue and not has_parallel_cue(context, current, peer):
                print(f"   ⛔ dropping PARALLEL '{current['clean_name']}' ~ "
                      f"'{peer['clean_name']}': no concurrency cue in the text")
                continue
            if config.parallel_mutual:
                reverse = self._predict_relation(context, peer, current)
                if reverse != "PARALLEL":
                    print(f"   ⛔ dropping PARALLEL '{current['clean_name']}' ~ "
                          f"'{peer['clean_name']}': the reverse answer was {reverse}")
                    continue
            kept.append(peer)
        return kept

    @staticmethod
    def _relation_text(entity):
        """What the model is asked about: the composed label, not the bare span.

        An activity's NER span is the verb alone ("carried", "check"), because
        its object is a separate Activity Data span that this pipeline folds
        into the label. Asked about the bare verbs, the model cannot tell what
        either step does, and two concurrent checks ("Carried the appraisal of
        the property", "Check credit history") are indistinguishable.
        """
        return entity.get('clean_name') or entity['word']

    def _predict_relation(self, context, entity1, entity2):
        """Relation label from the LLM, or UNKNOWN if the call fails or the
        answer names no label (ticket C7). Every call, decision and failure is
        recorded in self.relation_log."""
        node_A, node_B = self._relation_text(entity1), self._relation_text(entity2)
        pair = {"node_A": node_A, "node_B": node_B}
        if not self.dspy_predictor:
            return self.relation_log.error("no LLM predictor configured", **pair)
        if self.config.two_phase:
            from text2bpmn.two_phase import classify, is_hard

            reason = is_hard(node_A, node_B)
            if reason:
                try:
                    label, _ = classify(
                        context, node_A, node_B, model=self.config.llm_model,
                        api_base=self.config.api_base, api_key=self.config.api_key,
                        backend=self.config.backend,
                        signature_text=PROMPTS[self.config.prompt],
                        temperature=self.config.temperature,
                        timeout=self.config.llm_timeout,
                        disable_thinking=self.config.disable_thinking)
                except Exception as e:
                    print(f"Two-phase error: {e}")
                    return self.relation_log.error(e, **pair)
                print(f"   ⇄ two-phase ({reason}): {node_A!r} -> {node_B!r} = {label}")
                return self.relation_log.parse(label, **pair)
        try:
            pred = self.dspy_predictor(context=context, node_A=node_A, node_B=node_B)
        except Exception as e:
            print(f"DSPy Error: {e}")
            return self.relation_log.error(e, **pair)
        return self.relation_log.parse(pred.relation, **pair)


    def _ask_decision(self, context, decision, steps, lanes, kinds=None):
        """Relation ideas 1 and 1b (text2bpmn/decisions.py): a label for each
        item after one decision ("yes", "no" or "after" for a step, "same" or
        "after" for a decision mention, which only 1b lists), or None when the
        call fails or the reply does not parse. Each question is one call in
        self.relation_log, its items joined in node_B."""
        from text2bpmn.decisions import ask_llm

        pair = {"node_A": self._relation_text(decision),
                "node_B": " | ".join(("decision: " if kind == "decision" else "") + self._relation_text(s)
                                     for s, kind in zip(steps, kinds or ["step"] * len(steps)))}
        if not self.dspy_predictor:
            self.relation_log.error("no LLM predictor configured", **pair)
            return None
        try:
            labels = ask_llm(dspy.settings.lm, context, decision, steps, self._relation_text, lanes,
                             self.config, kinds)
        except Exception as e:
            print(f"Decision question failed: {e}")
            self.relation_log.error(e, **pair)
            return None
        print(f"   🔁 decision {pair['node_A']!r}: {labels}")
        self.relation_log.answered(" ".join(labels), **pair)
        return labels

    def _ask_parallel(self, context, cue, steps, lanes):
        """Relation idea 3 (text2bpmn/decisions.py): a label for each step
        around one concurrency word ("before", "a", "b", "c" or "after"), or
        None when the call fails or the reply does not parse. One call in
        self.relation_log, node_A "parallel: " and the word."""
        from text2bpmn.decisions import ask_parallel_llm

        pair = {"node_A": "parallel: " + self._relation_text(cue),
                "node_B": " | ".join(self._relation_text(s) for s in steps)}
        if not self.dspy_predictor:
            self.relation_log.error("no LLM predictor configured", **pair)
            return None
        try:
            labels = ask_parallel_llm(dspy.settings.lm, context, cue, steps, self._relation_text, lanes,
                                      self.config)
        except Exception as e:
            print(f"Concurrency question failed: {e}")
            self.relation_log.error(e, **pair)
            return None
        print(f"   ⇉ {pair['node_A']!r}: {labels}")
        self.relation_log.answered(" ".join(labels), **pair)
        return labels

    # --- Symbolic Guardrails ---
    def _is_valid_transition(self, source, target, relation):
        """
        Enforce BPMN Rules (The Symbolic Guardrail).
        """
        src_type = source.get('type', 'task')
        tgt_type = target.get('type', 'task')
        
        # Rule 1: End Events cannot have outgoing flows
        if src_type == 'endEvent':
            return False
            
        # Rule 2: Start Events cannot have incoming flows (handled by flow construction, but good check)
        # (This function checks a specific proposed link)
        
        # Rule 3: Branching Integrity
        # If we have a FALSE_BRANCH, the source MUST be a Gateway.
        # (We handle Type Correction elsewhere, but this blocks if correction failed)
        
        return True

    def _structure_process_data(self, entities, context):
        data = { "participants": set(), "elements": [], "flows": [] }
        current_lane = "Main Process"
        data["participants"].add(current_lane)
        
        # Create Start Event
        start_id = "StartEvent_1"
        data["elements"].append({ "id": start_id, "name": "Start", "type": "startEvent", "lane": current_lane })
        
        # Pre-process Entities (Assign IDs and clean names)
        for item in entities:
            item['id'] = f"{item['entity_group']}_{uuid.uuid4().hex[:8]}"
            if item['entity_group'] == "Activity":
                item['clean_name'] = self._clean_and_validate_activity(item['word'])  # None: dropped below
            else:
                item['clean_name'] = self._clean_name(item['word'])
                
        # Filter valid
        entities = [e for e in entities if e.get('clean_name')]

        # Metadata spans describe an activity; they are not steps (Sec. 4.1)
        entities = self._attach_task_info(entities, context)

        # Initial Type Assignment (NER based)
        for e in entities:
            if e['entity_group'] in ["XOR Gateway", *CONDITION_LABELS]:
                e['type'] = "exclusiveGateway"
            elif e['entity_group'] == "AND Gateway":
                e['type'] = "parallelGateway"
            elif e['entity_group'] == "Actor":
                 e['type'] = "Lane"  # Special handling
            else:
                e['type'] = "task"

        # An activity belongs to the actor its own sentence names. PET writes the
        # actor as often after the verb as before it ("the appraisal ... carried
        # out by a property appraiser"), so carrying the most recently seen actor
        # forward put such an activity in the previous actor's lane (R2.18).
        self._assign_lanes(entities, context)

        # A Condition Specification states a gateway's condition, so it belongs in
        # that gateway's label; one with no gateway before it stays a decision.
        entities = self._attach_conditions(entities)

        # Relation ideas 1, 1b, 1c and 3: the text-order chain, one question per
        # decision (and, in 3, one per concurrency word)
        mode = self.config.relation_mode
        if mode in ("decisions", "decisions2", "decisions3", "decisions4"):
            from text2bpmn.decisions import build
            return build(entities, lambda decision, steps, lanes, kinds=None:
                         self._ask_decision(context, decision, steps, lanes, kinds),
                         alternatives=mode in ("decisions2", "decisions3", "decisions4"),
                         drop_and_mentions=mode in ("decisions3", "decisions4"),
                         ask_parallel=(lambda cue, steps, lanes: self._ask_parallel(context, cue, steps, lanes))
                         if mode == "decisions4" else None,
                         gate=mode == "decisions4")
                
        # Main Loop
        previous_node_id = start_id
        last_gateway_id = None  # the decision an else-marker's branches leave from
        consumed = set()  # wired into a parallel block already; do not re-link
        i = 0
        while i < len(entities):
            current = entities[i]

            if current['id'] in consumed:
                i += 1
                continue

            # Handle Participants (Lanes)
            if current['type'] == "Lane":
                if not current.get('recipient'):
                    current_lane = current['clean_name']
                    data["participants"].add(current_lane)
                i += 1
                continue
                
            # "Otherwise" labels the branch that leaves the decision before it:
            # it is not a step, and not a second decision either. Its branches are
            # wired from that decision instead, and it is drawn as no node at all.
            # The marker still carries the lookahead, so the C2 guardrail fires on
            # it as before. With no decision before it there is nothing to carry
            # the branches, and the marker stays a node of its own.
            aliased = (is_else_marker(current['word']) and current['type'] in GATEWAY_TYPES
                       and last_gateway_id is not None)
            branch_source = last_gateway_id if aliased else current['id']

            # The actor named in this element's own sentence sets the lane; with
            # none, the lane carries forward from the sequence.
            if current.get('lane_hint'):
                current_lane = current['lane_hint']
                data["participants"].add(current_lane)

            # Add Element to Data, unless a branch pattern above already added it
            # (branch targets are only skipped when they directly follow the gateway)
            if not aliased and not any(el['id'] == current['id'] for el in data["elements"]):
                data["elements"].append({
                    "id": current['id'],
                    "name": current['clean_name'],
                    "type": current['type'],
                    "lane": current_lane,
                    "metadata": current.get('metadata', [])
                })
            
            if current['type'] in GATEWAY_TYPES and not aliased:
                last_gateway_id = current['id']

            # 1. Connect from Previous (Standard Sequence). Keep the flow, so that a
            #    parallel block can reroute it through its split gateway.
            default_flow = None
            already_linked = any(f['target'] == current['id'] for f in data['flows'])
            if previous_node_id and not already_linked and not aliased:
                default_flow = { "id": f"Flow_{uuid.uuid4().hex[:8]}", "source": previous_node_id,
                                 "target": current['id'], "relation": "SEQUENCE" }
                data["flows"].append(default_flow)
            
            # 2. Lookahead for Logic (Branching)
            candidates = []
            relations_map = {}
            idx = i + 1
            while len(candidates) < 3 and idx < len(entities):
                if entities[idx]['type'] != "Lane" and entities[idx]['id'] not in consumed:
                    candidates.append(entities[idx])
                idx += 1

            # First pass: predict all relations for lookahead candidates
            for next_ent in candidates:
                if not self._relation_needed(current, next_ent, context, neighbour=next_ent is candidates[0]):
                    self.relation_log.skip(node_A=self._relation_text(current),
                                           node_B=self._relation_text(next_ent))
                    continue
                relation = self._predict_relation(context, current, next_ent)

                # --- SYMBOLIC GUARDRAIL (Text-Based) ---
                # The else-marker is the source of the FALSE_BRANCH edge (ticket C2)
                # NONE (relation idea 2) stands where SEQUENCE did, so the
                # else-marker guardrail treats it the same way
                guarded = false_branch_guardrail("SEQUENCE" if relation == "NONE" else relation,
                                                 current['word'], next_ent['word'],
                                                 self.config.guardrail_mode)
                if guarded == "SEQUENCE":
                    guarded = relation
                if guarded != relation:
                    print(f"   🛡️ Guardrail: Forcing FALSE_BRANCH for '{current['word']}' -> '{next_ent['word']}' due to keyword.")
                    self.relation_log.guardrail(guarded, node_A=self._relation_text(current),
                                                node_B=self._relation_text(next_ent))
                relation = guarded

                relations_map[next_ent['id']] = relation

            # ──────────────────────────────────────────────────────────────────────
            # FIX #2: TYPE CORRECTION PASS
            # If DSPy says an entity is a branch TARGET (TRUE/FALSE/PARALLEL),
            # it cannot itself be a gateway — it must be a task (activity).
            # This prevents the cascading misclassification bug where branch
            # activities tagged as Condition Specification get treated as gateways.
            # ──────────────────────────────────────────────────────────────────────
            for next_ent in candidates:
                rel = relations_map.get(next_ent['id'])
                if rel in ("TRUE_BRANCH", "FALSE_BRANCH", "PARALLEL"):
                    if next_ent['entity_group'] in NER_GATEWAY_LABELS:
                        # NER read a branch marker here ("if", "In case of"). Being
                        # named as a branch's target says which way the branch runs,
                        # not that the marker is a step; only a span this pipeline
                        # typed from a CONDITION label is corrected below.
                        continue
                    if next_ent['type'] in ("exclusiveGateway", "parallelGateway"):
                        print(f"   🔧 Type Correction: '{next_ent['clean_name']}' "
                              f"{next_ent['type']} → task (it's a branch target, not a decision node)")
                        next_ent['type'] = "task"
                        # Also fix any element already appended to data["elements"]
                        for el in data["elements"]:
                            if el["id"] == next_ent["id"]:
                                el["type"] = "task"
                                break

            # ── CONDITION_DEF ────────────────────────────────────────────────────
            # The candidate states this gateway's condition ("If" -> "the score is
            # above 750"), so it belongs in the gateway's label, not in a task box
            # of its own.
            if current['type'] in GATEWAY_TYPES:
                for next_ent in candidates:
                    if relations_map.get(next_ent['id']) != "CONDITION_DEF":
                        continue
                    if next_ent['entity_group'] == "Activity":
                        continue  # NER says this is a step; a step is not a condition
                    if current.get('has_condition'):
                        continue  # one condition per gateway, as for Condition Specification
                    condition = next_ent['clean_name']
                    if condition and condition.lower() not in current['clean_name'].lower():
                        merged = f"{current['clean_name']} {condition[0].lower() + condition[1:]}".strip()
                        current['clean_name'] = merged
                        for element in data["elements"]:
                            if element["id"] == current['id']:
                                element["name"] = merged
                        print(f"   🏷️ Condition folded into gateway: {merged!r}")
                        current['has_condition'] = True
                    consumed.add(next_ent['id'])

            # Recalculate branch lists AFTER type correction
            def branch_targets(*relations):
                """Candidates in a branch role. A span that is only an else-marker
                is the branch's label, so it is never one of its targets."""
                return [e for e in candidates if relations_map.get(e['id']) in relations
                        and not is_else_marker(e['word'])]

            # Concurrency is between activities: a gateway named as a PARALLEL peer
            # ("In case of small amounts" beside "If everything is ready") is a
            # decision, not work running at the same time.
            parallel_branches = [e for e in branch_targets("PARALLEL") if e['type'] == "task"]
            parallel_branches = self._filter_parallel(current, parallel_branches, context,
                                                      previous_node_id, data)
            xor_branches      = branch_targets("TRUE_BRANCH", "FALSE_BRANCH")

            # ── PARALLEL GATEWAY PATTERN ──────────────────────────────────────────
            if current['type'] == "parallelGateway" and parallel_branches:
                split_gw_id = current['id']
                print(f"   🔀 PARALLEL gateway '{current['clean_name']}' (split) detected.")

                # Create a JOIN parallel gateway node
                join_gw_id = f"ParallelGateway_join_{uuid.uuid4().hex[:8]}"
                join_gw = {"id": join_gw_id, "name": "+", "type": "parallelGateway", "lane": current_lane}
                data["elements"].append(join_gw)

                for branch_ent in parallel_branches:
                    print(f"      - Branch: '{branch_ent['clean_name']}'")

                    # ──────────────────────────────────────────────────────────────
                    # FIX #1: ADD branch entity to elements BEFORE wiring flows.
                    # Previously these entities were skipped by the i+=1 loop below
                    # and never reached the "Add Element" block at the top, leaving
                    # flows that pointed to non-existent elements.
                    # ──────────────────────────────────────────────────────────────
                    if not any(el['id'] == branch_ent['id'] for el in data["elements"]):
                        data["elements"].append({
                            "id": branch_ent['id'],
                            "name": branch_ent['clean_name'],
                            "type": branch_ent['type'],
                            "lane": branch_ent.get('lane_hint') or current_lane,
                            "metadata": branch_ent.get('metadata', [])
                        })

                    # Connect split gateway → branch entity
                    data["flows"].append({
                        "id": f"Flow_{uuid.uuid4().hex[:8]}",
                        "source": split_gw_id,
                        "target": branch_ent['id'],
                        "name": "",
                        "relation": "PARALLEL"
                    })
                    # Connect branch entity → join gateway
                    data["flows"].append({
                        "id": f"Flow_{uuid.uuid4().hex[:8]}",
                        "source": branch_ent['id'],
                        "target": join_gw_id,
                        "name": "",
                        "relation": "PARALLEL"
                    })

                # Remove the default sequence flow that was already added from
                # previous_node → split_gw (that's fine), but also remove any
                # default flow from split_gw → first parallel branch that was
                # added at the top of the NEXT iteration (which won't happen now
                # because we skip). However, the split_gw → first_candidate flow
                # would have been added in the NEXT iteration's "already_linked"
                # check. Since we skip them, this is safe.

                # Linear flow continues FROM the join gateway
                previous_node_id = join_gw_id

                # The branches are wired; mark them used, as the synthesised
                # block below does. Skipping only the mentions directly after
                # the gateway let a branch behind an Actor mention be processed
                # again, and the flow then left the block from that branch
                # instead of the join.
                consumed.update(e['id'] for e in parallel_branches)
            
            # ── SYNTHESISED PARALLEL BLOCK ───────────────────────────────────────
            # No AND Gateway mention anchors this block: PET's training data has
            # 8 AND Gateway spans in 417 sentences, none in the test split, so the
            # recogniser rarely emits one. Concurrency then comes from the relation:
            # `current` and its PARALLEL peers run at the same time, between a
            # split and a join gateway.
            elif current['type'] == "task" and parallel_branches:
                group = [current] + parallel_branches
                print(f"   🔀 PARALLEL block: '{current['clean_name']}' with "
                      f"{[p['clean_name'] for p in parallel_branches]}")

                # Every flow already entering `current` now enters the split,
                # with its label and relation: the default sequence flow, or a
                # decision's branch when `current` is that branch's first step.
                # Only the default flow used to be moved, so a branch edge into
                # `current` stayed beside a new edge from the decision to the
                # split, and the block's join waited for the branch not taken.
                entering = [f for f in data["flows"] if f["target"] == current["id"]]
                split_gw_id = f"ParallelGateway_split_{uuid.uuid4().hex[:8]}"
                join_gw_id = f"ParallelGateway_join_{uuid.uuid4().hex[:8]}"
                for gateway_id in (split_gw_id, join_gw_id):
                    data["elements"].append({"id": gateway_id, "name": "+", "type": "parallelGateway",
                                             "lane": current_lane, "metadata": []})
                for flow in entering:
                    flow["target"] = split_gw_id
                if not entering and previous_node_id:
                    data["flows"].append({"id": f"Flow_{uuid.uuid4().hex[:8]}",
                                          "source": previous_node_id, "target": split_gw_id,
                                          "relation": "SEQUENCE"})

                for member in group:
                    if not any(el['id'] == member['id'] for el in data["elements"]):
                        data["elements"].append({"id": member['id'], "name": member['clean_name'],
                                                 "type": member['type'],
                                                 "lane": member.get('lane_hint') or current_lane,
                                                 "metadata": member.get('metadata', [])})
                    data["flows"].append({"id": f"Flow_{uuid.uuid4().hex[:8]}", "source": split_gw_id,
                                          "target": member['id'], "name": "", "relation": "PARALLEL"})
                    data["flows"].append({"id": f"Flow_{uuid.uuid4().hex[:8]}", "source": member['id'],
                                          "target": join_gw_id, "name": "", "relation": "PARALLEL"})

                previous_node_id = join_gw_id
                consumed.update(peer['id'] for peer in parallel_branches)

            # ── XOR / EXCLUSIVE GATEWAY PATTERN ──────────────────────────────────
            elif current['type'] == "exclusiveGateway" and xor_branches:
                print(f"   🔁 XOR gateway '{current['clean_name']}' detected.")

                wired = {}  # outcome -> the last element wired for it
                for next_ent in xor_branches:
                    relation = relations_map[next_ent['id']]
                    # An else-marker introduces the false branch and nothing else,
                    # whichever way the model labelled the pair.
                    flow_name = "No" if aliased else \
                        ("Yes" if relation == "TRUE_BRANCH" else "No")

                    # ──────────────────────────────────────────────────────────────
                    # FIX #1 (XOR variant): Also add XOR branch targets to elements
                    # if they haven't been added yet (same root cause as parallel).
                    # ──────────────────────────────────────────────────────────────
                    if not any(el['id'] == next_ent['id'] for el in data["elements"]):
                        data["elements"].append({
                            "id": next_ent['id'],
                            "name": next_ent['clean_name'],
                            "type": next_ent['type'],
                            "lane": next_ent.get('lane_hint') or current_lane,
                            "metadata": next_ent.get('metadata', [])
                        })

                    # An exclusive split has one flow per outcome. A second
                    # target with the same outcome continues that branch rather
                    # than leaving the decision a second time: "Invites three" and
                    # "Selects one" are both the large-amounts branch, in order.
                    if self._is_valid_transition(current, next_ent, relation):
                        data["flows"].append({
                            "id": f"Flow_{uuid.uuid4().hex[:8]}",
                            "source": wired.get(flow_name, branch_source),
                            "target": next_ent['id'],
                            "name": "" if flow_name in wired else flow_name,
                            "relation": relation if flow_name not in wired else "SEQUENCE"
                        })
                    wired[flow_name] = next_ent['id']

                # Skip XOR branch targets so they don't get a redundant
                # default sequence flow added at the top of the loop
                branch_ids = {e['id'] for e in xor_branches}
                next_i = i + 1
                while next_i < len(entities) and entities[next_i]['id'] in branch_ids:
                    next_i += 1

                # After XOR, flow continues from whichever branch leads onward.
                # For now, keep previous_node_id as the gateway so that the
                # next non-branch entity gets a default sequence from the gateway.
                # (In a full merge you'd add a converging gateway, but this matches
                # the original intent.)
                previous_node_id = branch_source

                # Advance past the consumed branch entities
                i = next_i - 1  # -1 because the bottom of loop does i += 1
            
            # ── DEFAULT: LINEAR SEQUENCE FLOW ─────────────────────────────────────
            else:
                previous_node_id = branch_source
            
            i += 1
            
        # Create End Event & Link unconnected nodes
        end_id = "EndEvent_1"
        # A branch can be wired twice: once from the decision and once from the
        # else-marker aliased to it. One edge per pair survives, the labelled one.
        unique = {}
        for flow in data["flows"]:
            key = (flow["source"], flow["target"])
            if key not in unique or (flow.get("name") and not unique[key].get("name")):
                unique[key] = flow
        data["flows"] = list(unique.values())

        data["elements"].append({ "id": end_id, "name": "End", "type": "endEvent", "lane": current_lane })
        
        source_ids = set(f['source'] for f in data['flows'])
        for node in data["elements"]:
            if node['type'] != "endEvent" and node['id'] not in source_ids:
                data["flows"].append({ "id": f"Flow_{uuid.uuid4().hex[:8]}", "source": node['id'],
                                       "target": end_id, "relation": "SEQUENCE" })

        # Built as a set to de-duplicate; returned as a sorted list so the
        # result is JSON-serializable and its order is stable across runs.
        data["participants"] = sorted(data["participants"])
        return data

    def _clean_and_validate_activity(self, text):
        """Clean an Activity span, or return None if it is not an activity.

        - verbal ("performs a credit check"): trimmed to start at the verb
        - nominal ("risk assessment", "shipping"): kept, cleaned
        - neither a verb nor a noun ("the"), or a word-piece fragment of two
          characters or fewer ("ti"): rejected
        """
        text = text.replace("##", "").strip(" .,-:;")
        if len(text) <= 2:
            return None
        doc = self.nlp_validator(text)
        for token in doc:
            if token.pos_ == "VERB":
                cleaned = text[token.idx:].strip()
                return cleaned[0].upper() + cleaned[1:]
        if any(token.pos_ in ("NOUN", "PROPN") for token in doc):
            return text[0].upper() + text[1:]
        return None

    def _attach_task_info(self, entities, context=""):
        """Move each metadata span (Activity Data, Further Specification)
        into the metadata of the activity it belongs to and drop it from the
        entity list, so it never becomes a task or joins relation prediction.
        One object completes its activity's label; the rest describe it."""
        owners = self._metadata_owners(entities, context)

        # The object that completes a label is the one closest to the activity,
        # not the first in reading order: "assess" takes "the applicant's
        # eligibility" beside it, not "risk" from the clause before.
        completes = {}
        for i, owner in owners.items():
            if entities[i]['entity_group'] not in OBJECT_LABELS:
                continue
            best = completes.get(owner)
            if best is None or self._span_gap(entities[i], entities[owner]) < \
                               self._span_gap(entities[best], entities[owner]):
                completes[owner] = i

        for i, owner in owners.items():
            activity = entities[owner]
            if completes.get(owner) == i:
                object_text = entities[i]['clean_name']
                activity['clean_name'] = f"{activity['clean_name']} {object_text[0].lower() + object_text[1:]}".strip()
            else:
                activity.setdefault('metadata', []).append(entities[i]['clean_name'])
        return [e for e in entities if e['entity_group'] not in METADATA_LABELS]

    def _assign_lanes(self, entities, context=""):
        """Record for each element the actor named in its own sentence, if any.

        Reading order alone will not do: an actor is as often named after its
        activity as before it. An element whose sentence names no actor gets no
        hint and inherits the lane in force at that point in the sequence.
        """
        for e in entities:
            if e['type'] == "Lane" and self._is_recipient(e, context):
                e['recipient'] = True
        actors = [i for i, e in enumerate(entities)
                  if e['type'] == "Lane" and not e.get('recipient')]
        for i, e in enumerate(entities):
            if e['type'] == "Lane":
                continue
            owner = self._nearest_in_sentence(entities, actors, i, context,
                                              same_sentence_only=True, sentences_back=1)
            if owner is not None:
                e['lane_hint'] = entities[owner]['clean_name']
                # which mention was chosen, not only its name: an actor named
                # many times is many spans, and the choice has to be checkable
                e['lane_actor'] = entities[owner].get('id', owner)
        return entities

    def _metadata_owners(self, entities, context=""):
        """Which activity each metadata span belongs to, as {span: activity}.

        Separated from _attach_task_info so the rule can be measured against
        PET's own `uses` and `further specification` relations rather than only
        judged by eye on a case study.
        """
        activities = [i for i, e in enumerate(entities)
                      if e['entity_group'] == "Activity"]
        owners = {}
        for i, e in enumerate(entities):
            if e['entity_group'] in METADATA_LABELS:
                owner = self._nearest_in_sentence(entities, activities, i, context)
                if owner is not None:
                    owners[i] = owner
        return owners

    @staticmethod
    def _is_recipient(entity, context):
        """Whether the action is directed at this actor ("sent **to the
        applicant**") rather than performed by it. A performer is named as the
        subject, or after "by" in the passive; a recipient after "to" or "for",
        and naming no lane keeps the performer's lane in force.
        """
        if entity.get("start") is None:
            return False
        before = context[:entity["start"]].rstrip().rsplit(" ", 1)[-1].strip(",;:(").lower()
        return before in RECIPIENT_PREPOSITIONS or before in RECIPIENT_VERBS

    @staticmethod
    def _span_gap(a, b):
        """Characters between two spans, in either order."""
        if a.get("start") is None or b.get("start") is None:
            return 10 ** 6
        return min(abs(b["start"] - a["end"]), abs(a["start"] - b["end"]))

    @staticmethod
    def _nearest_in_sentence(entities, candidates, index, context="",
                             same_sentence_only=False, sentences_back=0):
        """The candidate span this span belongs to: the closest in its sentence.

        Direction cannot be assumed, because passive voice puts the object
        before its verb ("the acceptance pack is prepared"). The sentence is
        the boundary, so an object never attaches across a full stop. An owner
        in another sentence is a last resort, and none at all when
        `same_sentence_only`.

        `sentences_back` allows an owner that many sentences earlier, and only
        earlier, when the sentence itself has none. In PET's actor-performer
        relations the performer is never in a later sentence, and 26 of the 57
        activities whose performer the sentence-bounded rule cannot see have it
        in the sentence immediately before.
        """
        if not candidates:
            return None
        span = entities[index]
        if span.get("start") is None:
            if same_sentence_only:
                return None
            before = [a for a in candidates if a < index]
            return before[-1] if before else candidates[0]

        def sentence_of(position):
            return sum(context.count(mark, 0, position) for mark in ".;!?")

        here = sentence_of(span["start"])

        def distance(a):
            other = entities[a]
            if other.get("start") is None:
                return abs(a - index) * 1000
            back = here - sentence_of(other["start"])
            if back == 0:
                penalty = 0
            elif 0 < back <= sentences_back:
                penalty = 1_000 * back      # preferred only when the sentence has none
            else:
                penalty = 10_000
            return BPMNHybridExtractor._span_gap(span, other) + penalty

        best = min(candidates, key=distance)
        if same_sentence_only and distance(best) >= 10_000:
            return None
        return best

    def _attach_conditions(self, entities):
        """Fold each Condition Specification span into the gateway it qualifies."""
        kept = []
        for i, e in enumerate(entities):
            if e['entity_group'] not in CONDITION_LABELS:
                kept.append(e)
                continue
            gateway = next((g for g in reversed(kept) if g['type'] in GATEWAY_TYPES), None)
            if gateway is None:  # nothing to qualify: it stays a decision of its own
                kept.append(e)
                continue
            condition = e['clean_name']
            if not condition or condition.lower() in gateway['clean_name'].lower():
                continue
            if gateway.get('has_condition'):  # one condition per gateway; the rest describe it
                gateway.setdefault('metadata', []).append(condition)
                continue
            gateway['clean_name'] = f"{gateway['clean_name']} {condition[0].lower() + condition[1:]}".strip()
            gateway['has_condition'] = True
        return kept

    def _clean_name(self, text):
        text = text.replace("##", "").strip(" .,-:;")
        if text: 
            return text[0].upper() + text[1:]
        return text

    # --- NEW: Ontology Populator Logic ---
    def _populate_ontology(self, process_data):
        """Write the populated ontology, via text2bpmn.ontology, which also runs
        from a saved extraction without this class's models."""
        from text2bpmn.ontology import populate
        summary = populate(process_data, self.ontology_file, self.config.ontology_out)
        print(f"   💾 Saved Enriched Ontology to {summary['out']}: "
              f"{summary['classes']}, relations {summary['relations']}, "
              f"{len(summary['lanes'])} actors")
        return summary


TEST_TEXT = """The Financial Officer performs a credit history check on the applicant. Subsequently, the System conducts the loan risk assessment. At the same time, the Property Appraiser carries out the property appraisal. Once the loan risk assessment and the property appraisal are complete, the Loan Officer assesses the applicant's eligibility. If the applicant is eligible, the Loan Officer prepares the acceptance pack and sends the acceptance pack to the applicant. Otherwise, the Loan Officer rejects the application"""


def main():
    parser = argparse.ArgumentParser(description="Extract a process structure from a text file.")
    parser.add_argument("input", nargs="?", help="text file to process (default: the built-in test text)")
    parser.add_argument("-o", "--output", help="write the result, including the run config, as JSON")
    parser.add_argument("--bpmn", help="also write the BPMN 2.0 diagram here")
    parser.add_argument("--dump-text", metavar="FILE",
                        help="write the coreference-resolved text and stop, so another "
                             "recogniser can be run on exactly that string")
    parser.add_argument("--entities", metavar="FILE",
                        help="use spans from this file instead of the NER model "
                             "({text, spans: [{start, end, label, score}]})")
    parser.add_argument("--svg", help="also draw the diagram here (implies --bpmn)")
    add_arguments(parser)
    args = parser.parse_args()

    text = open(args.input, encoding="utf-8").read() if args.input else TEST_TEXT
    entities = None
    if args.entities:
        entities = json.loads(Path(args.entities).read_text(encoding="utf-8"))
        if "documents" in entities:  # as text2bpmn.gliner_baseline saves them
            document = entities["documents"][0]
            entities = {"text": document["text"], "spans": document["spans"],
                        "source": entities.get("run", {}).get("model", args.entities)}
        entities.setdefault("source", args.entities)
    extractor = BPMNHybridExtractor(config=from_arguments(args),
                                    ner_model_path=NER_MODEL_PATH if not args.entities else None)
    if args.dump_text:
        Path(args.dump_text).write_text(extractor.resolved_text(text), encoding="utf-8")
        print(f"✅ Wrote {args.dump_text}")
        return
    result = extractor.process_text(text, entities)

    if args.bpmn or args.svg:
        from text2bpmn.bpmn_xml import to_xml
        from text2bpmn.render import render
        from text2bpmn.structure import validate
        name = Path(args.input).stem if args.input else "process"
        bpmn_path = Path(args.bpmn or Path(args.svg).with_suffix(".bpmn"))
        bpmn_path.write_text(to_xml(validate(result["structured_data"]), name), encoding="utf-8")
        print(f"✅ Wrote {bpmn_path}")
        if args.svg:
            Path(args.svg).write_text(render(bpmn_path), encoding="utf-8")
            print(f"✅ Wrote {args.svg}")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"✅ Wrote {args.output}")
    else:
        print("\n--- Final JSON Output ---")
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
