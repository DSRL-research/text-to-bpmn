"""What every check records about itself, and how it finds a pilot's models."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from text2bpmn.run_config import _git_state, _version

PACKAGES = ("lxml", "pm4py", "rdflib", "pyshacl", "owlready2", "dspy", "transformers")
REPO = Path(__file__).resolve().parents[2]


def portable(value, repo=REPO, home=Path.home()):
    """A path as a report should carry it: relative inside the repository,
    "~/..." elsewhere under the home directory, so that no report names the
    machine it was made on. Lists, tuples and dicts are walked; anything that
    is not an absolute path is returned as it is."""
    if isinstance(value, dict):
        return {k: portable(v, repo, home) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(portable(v, repo, home) for v in value)
    if not isinstance(value, (str, Path)) or not Path(value).is_absolute():
        return value
    path = Path(value)
    for root, prefix in ((Path(repo), None), (Path(home), "~")):
        try:
            rest = path.relative_to(root)
        except ValueError:
            continue
        return str(rest) if prefix is None else f"{prefix}/{rest}"
    return str(value) if isinstance(value, Path) else value


def provenance(**extra):
    return {"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "code": _git_state(), "python": sys.version.split()[0],
            "packages": {p: _version(p) for p in PACKAGES}, **portable(extra)}


def documents(folder, filename):
    """(doc_id, path) for every document folder of a pilot that has `filename`."""
    return [(d.name, d / filename) for d in sorted(Path(folder).iterdir())
            if d.is_dir() and (d / filename).exists()]


def write(out, name, result, markdown):
    """`name`.json and `name`.md under `out`."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{name}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / f"{name}.md").write_text(markdown.rstrip() + "\n", encoding="utf-8")
    return out / f"{name}.md"


def header(title, record):
    code = record["code"]
    return [f"# {title}", "",
            f"Run {record['run_at']} at {code['describe']} ({code['commit'][:7]}, dirty: {code['dirty']}); "
            + ", ".join(f"{p} {v}" for p, v in record["packages"].items() if v) + ".", ""]
