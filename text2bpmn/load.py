"""Read the extraction output of finder3.py.

finder3 returns {"structured_data": {"participants", "elements", "flows"}}.
Outputs saved before the revision are the printed Python dict (single quotes,
sets), not JSON, so both forms are accepted.
"""
import ast
import json
from pathlib import Path


def load_extraction(path):
    text = Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = ast.literal_eval(text)
    data = data.get("structured_data", data)
    return {
        "participants": sorted(data.get("participants", [])),
        "elements": [dict(e) for e in data["elements"]],
        "flows": [dict(f) for f in data["flows"]],
    }
