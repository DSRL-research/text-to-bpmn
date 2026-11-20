# BPMN Synthetic Data Generation Prompt

You are an expert in **Business Process Model and Notation (BPMN 2.0)** and procedural logic.

## Goal
Generate **200 unique, realistic business process scenarios** and extract the logical relationships between steps. Output the result in **JSONL** format (one valid JSON object per line).

## The 5 Logical Relationships (Labels)

1.  **SEQUENCE**: Process flows linearly. Step A finishes, then Step B starts.
    *   *Example*: "The user submits the form. The system validates the data." -> `(submits, validates) = SEQUENCE`
2.  **CONDITION_DEF**: Defines a specific condition for a gateway. Connects a Gateway (or "If") to the Condition text.
    *   *Example*: "If the amount is over $500..." -> `(If, amount is over $500) = CONDITION_DEF`
3.  **TRUE_BRANCH**: The path taken if a condition is met (Positive Flow).
    *   *Example*: "If the amount is over $500, the manager must approve." -> `(amount is over $500, manager must approve) = TRUE_BRANCH`
4.  **FALSE_BRANCH**: The path taken if a condition is NOT met (Negative Flow / Else / Otherwise).
    *   *Example*: "If the score is low, reject the application." -> `(score is low, reject) = FALSE_BRANCH` (Implies: If score is low -> Stop/Reject. Sometimes 'Else' is explicit, sometimes implicit).
    *   *Example*: "Otherwise, the system sends a rejection email." -> `(Otherwise, sends rejection) = FALSE_BRANCH`
5.  **PARALLEL**: Two activities happen at the same time (AND Gateway).
    *   *Example*: "The system archives the document while sending a notification." -> `(archives, sending) = PARALLEL`

## Output Format (JSONL)
Each line must be a JSON object with:
*   `text`: **The FULL sentence context**. Do not truncate or modify the wording. This is what the model "sees".
*   `entity_1`: The specific text snippet (substring) of the source step.
*   `entity_2`: The specific text snippet (substring) of the target step.
*   `label`: One of the 5 labels above.

**IMPORTANT**: 
1. `text` must be the **FULL logical context**.
   - **CRITICAL**: If the logic spans two sentences (e.g., "If X. Otherwise Y."), you MUST include **BOTH** sentences in the `text` field for ALL generated lines. **Do not split them.**
   - Example: `text`: "If the score is low, reject. Otherwise, approve." (Used for both the Reject and Approve lines).
2. `entity_1` / `entity_2`: Are just the specific substrings within that full text.

## Few-Shot Examples (Use these as templates)

### Combined Branching (If Condition X, Else Y)
**Context**: "If the customer is a VIP, apply a 20% discount. Otherwise, apply standard pricing."
(Note: The `text` field below includes BOTH sentences for all entries).

```json
{"text": "If the customer is a VIP, apply a 20% discount. Otherwise, apply standard pricing.", "entity_1": "If", "entity_2": "customer is a VIP", "label": "CONDITION_DEF"}
{"text": "If the customer is a VIP, apply a 20% discount. Otherwise, apply standard pricing.", "entity_1": "customer is a VIP", "entity_2": "apply a 20% discount", "label": "TRUE_BRANCH"}
{"text": "If the customer is a VIP, apply a 20% discount. Otherwise, apply standard pricing.", "entity_1": "Otherwise", "entity_2": "apply standard pricing", "label": "FALSE_BRANCH"}
```

**Context**: "If the stock is sufficient, ship the order. If not, trigger a backorder."
```json
{"text": "If the stock is sufficient, ship the order. If not, trigger a backorder.", "entity_1": "stock is sufficient", "entity_2": "ship the order", "label": "TRUE_BRANCH"}
{"text": "If the stock is sufficient, ship the order. If not, trigger a backorder.", "entity_1": "If not", "entity_2": "trigger a backorder", "label": "FALSE_BRANCH"}
```

### Standard Examples
```json
{"text": "The warehouse clerk packs the item and then ships it to the customer.", "entity_1": "packs the item", "entity_2": "ships it", "label": "SEQUENCE"}
{"text": "If the verification fails, the process is terminated immediately.", "entity_1": "verification fails", "entity_2": "process is terminated", "label": "TRUE_BRANCH"}
{"text": "If the verification fails, the process is terminated immediately.", "entity_1": "If", "entity_2": "verification fails", "label": "CONDITION_DEF"}
{"text": "Otherwise, the support agent tickets the issue.", "entity_1": "Otherwise", "entity_2": "tickets the issue", "label": "FALSE_BRANCH"}
{"text": "The manufacturing phase begins while the marketing team prepares the campaign.", "entity_1": "manufacturing phase begins", "entity_2": "marketing team prepares", "label": "PARALLEL"}
```

## Instructions for Generation
1.  **Diverse Domains**: Generate examples from Banking, Insurance, Healthcare, IT Support, Logistics, and HR.
2.  **Complex Logic**: Don't just do "SEQUENCE". Ensure at least **40%** of examples involve Branching (True/False) or Parallelism.
3.  **Variability**: Use different phrasings ("If...", "In case of...", "Should the...", "Simultaneously...", "After...").

**Generate 200 entries now.**