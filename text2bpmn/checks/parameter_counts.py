"""Table 4's parameter counts, counted from the weights, and the record Table 4 is rebuilt from.

    python3 -m text2bpmn.checks.parameter_counts [--root DIR] [--hf-cache DIR]
        # -> runs/checks/final-3/tables/parameter_counts.{json,md}
    python3 -m text2bpmn.checks.parameter_counts --check [--root DIR]
        # recount whatever weights are present and compare with the committed record

The weights are not in git (.gitignore; README.md, "The recogniser weights", lists them with their
SHA-256): the fine-tuned recognisers live in the authors' working copy, at the
paths below relative to its root (--root, default this repository), and the
two zero-shot GLiNER checkpoints in the Hugging Face cache (--hf-cache, default
$HF_HUB_CACHE or ~/.cache/huggingface/hub) at the revisions pinned
below. So the counts are made once, where the
weights are, and written to a committed record; text2bpmn.paper_tables builds
Table 4 from that record, and --check recounts against it.

**What is counted.** The number of elements of every tensor the weights file
stores, nothing else (no config, no model class):

- a safetensors file (`model.safetensors`): the shapes in its JSON header;
- a PyTorch file (`pytorch_model.bin`, a zip holding a pickle): the sizes of
  its tensor records, read by an unpickler that resolves no class -- every
  global the pickle names becomes a stub that only notes a tensor's size, so
  nothing in the file is run, and no tensor data is read.

Each file's SHA-256 is recorded beside its count, so the record names the
weights it counted. For the fine-tuned GLiNER models the training run recorded
its own count, `sum(p.numel() for p in model.parameters())`
(text2bpmn/gliner_finetune.py:173, in each run.json as parameters_millions);
the record sets the two side by side.
"""
import argparse
import collections
import hashlib
import json
import os
import pickle
import struct
import zipfile
from math import prod
from pathlib import Path

from text2bpmn.checks.common import header, provenance, write

OUT = Path("runs/checks/final-3/tables")
NAME = "parameter_counts"
FINETUNED = "text2bpmn/baselines/finetuned_315/{}/best/pytorch_model.bin"
RUN_JSON = "text2bpmn/baselines/finetuned_315/{}/run.json"
# Table 4's configurations, in its order: (row, where the weights are, run.json of the training)
MODELS = [
    ("BERT, fine-tuned", ("root", "process-visualizer/src/token_classification_alex/bert_ner_315_dev60/"
                                  "model.safetensors"), None),
    ("GLiNER small v2.1, fine-tuned", ("root", FINETUNED.format("A-small-v2.1-315")),
     RUN_JSON.format("A-small-v2.1-315")),
    ("GLiNER medium v2.1, fine-tuned", ("root", FINETUNED.format("B-medium-v2.1-315")),
     RUN_JSON.format("B-medium-v2.1-315")),
    ("GLiNER, focal loss", ("root", FINETUNED.format("C-small-focal-315")), RUN_JSON.format("C-small-focal-315")),
    ("GLiNER, hard negatives", ("root", FINETUNED.format("D-small-hardneg-315")),
     RUN_JSON.format("D-small-hardneg-315")),
    # the zero-shot checkpoints, each at its pinned revision
    ("GLiNER medium v2.1, zero-shot", ("hf", "urchade/gliner_medium-v2.1",
                                       "40ec419335d09393f298636f471328b722c6da9e", "model.safetensors"), None),
    ("GLiNER2.5 base v1, zero-shot", ("hf", "fastino/gliner2.5-base-v1",
                                      "ca906247640776a07753514055be9726f9080ead", "model.safetensors"), None),
]


# --- counting --------------------------------------------------------------------------

def safetensors_shapes(path):
    """{tensor name: shape} from a safetensors file's header (8-byte length, then JSON)."""
    with open(path, "rb") as f:
        (length,) = struct.unpack("<Q", f.read(8))
        meta = json.loads(f.read(length))
    return {name: tuple(entry["shape"]) for name, entry in meta.items() if name != "__metadata__"}


class _TensorRecord:
    __slots__ = ("shape",)

    def __init__(self, shape):
        self.shape = tuple(int(n) for n in shape)


def _rebuild_tensor(storage, offset, size, *rest):
    return _TensorRecord(size)


def _rebuild_parameter(data, *rest):
    return data


class _Stub:
    """Stands for any class or function the pickle names; calling it builds nothing."""

    def __init__(self, *args, **kwargs):
        pass

    def __call__(self, *args, **kwargs):
        return _Stub()

    def __setstate__(self, state):
        pass


class _ShapesOnly(pickle.Unpickler):
    """Resolves no global from the file: tensors become their sizes, all else a stub."""

    def find_class(self, module, name):
        if (module, name) == ("collections", "OrderedDict"):
            return collections.OrderedDict
        if module == "torch._utils" and name.startswith("_rebuild_tensor"):
            return _rebuild_tensor
        if module == "torch._utils" and name.startswith("_rebuild_parameter"):
            return _rebuild_parameter
        return _Stub

    def persistent_load(self, pid):
        return None  # a storage: its data is never read


def torch_zip_shapes(path):
    """{tensor name: shape} from a PyTorch zip file's data.pkl, without running it."""
    with zipfile.ZipFile(path) as archive:
        member = next((n for n in archive.namelist() if n.endswith("/data.pkl") or n == "data.pkl"), None)
        if member is None:
            raise ValueError(f"{path}: not a PyTorch zip file (no data.pkl)")
        import io
        state = _ShapesOnly(io.BytesIO(archive.read(member))).load()
    if isinstance(state, dict) and "state_dict" in state and isinstance(state["state_dict"], dict):
        state = state["state_dict"]
    return {name: value.shape for name, value in state.items() if isinstance(value, _TensorRecord)}


def shapes(path):
    with open(path, "rb") as f:
        magic = f.read(4)
    return torch_zip_shapes(path) if magic == b"PK\x03\x04" else safetensors_shapes(path)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def count(path):
    found = shapes(path)
    return {"format": "safetensors" if Path(path).suffix == ".safetensors" else "pytorch zip",
            "tensors": len(found), "parameters": sum(prod(s) for s in found.values()),
            "sha256": sha256(path)}


# --- the record ------------------------------------------------------------------------

def hf_cache(explicit=None):
    return Path(explicit or os.environ.get("HF_HUB_CACHE")
                or Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub")


def locate(where, root, cache):
    """(path on this machine, how the record names it)."""
    if where[0] == "root":
        return Path(root) / where[1], where[1]
    _, repo, revision, filename = where
    folder = Path(cache) / ("models--" + repo.replace("/", "--")) / "snapshots" / revision
    return folder / filename, f"hf://{repo}@{revision}/{filename}"


def counts(root=".", cache=None):
    """Every model of MODELS whose weights are present, counted; the absent ones listed."""
    cache = hf_cache(cache)
    rows, absent = {}, []
    for row, where, run_json in MODELS:
        path, named = locate(where, root, cache)
        if not path.exists():
            absent.append(named)
            continue
        entry = {"weights": named, **count(path)}
        entry["millions"] = round(entry["parameters"] / 1e6, 1)
        if run_json:
            recorded = json.loads(Path(run_json).read_text(encoding="utf-8"))
            entry["training_record"] = {"file": run_json, "parameters_millions": recorded["parameters_millions"],
                                        "base_model": recorded["base_model"]}
        rows[row] = entry
    return rows, absent


def markdown(result):
    lines = header("Table 4's parameter counts, from the weights", result["provenance"])
    lines += ["Elements of every tensor each weights file stores (safetensors header, or the tensor sizes of a "
              "PyTorch pickle read without running it); `text2bpmn/checks/parameter_counts.py`. M = 10^6.", "",
              "| configuration | parameters | M | tensors | training run's own count (M) | weights | SHA-256 |",
              "|---|---|---|---|---|---|---|"]
    for row, e in result["models"].items():
        own = e.get("training_record", {}).get("parameters_millions", "–")
        lines.append(f"| {row} | {e['parameters']:,} | {e['millions']} | {e['tensors']} | {own} | "
                     f"`{e['weights']}` | `{e['sha256'][:16]}…` |")
    if result["absent"]:
        lines += ["", "Not counted, the weights being absent here: " + ", ".join(f"`{a}`" for a in result["absent"])
                  + "."]
    return "\n".join(lines) + "\n"


def check(record_path, root=".", cache=None):
    """Recount what is present; differences from the committed record."""
    record = json.loads(Path(record_path).read_text(encoding="utf-8"))["models"]
    found, absent = counts(root, cache)
    problems = [f"{row}: {k} {e[k]} here, {record[row][k]} in the record"
                for row, e in found.items() for k in ("parameters", "sha256") if row in record and e[k] != record[row][k]]
    problems += [f"{row}: counted here, not in the record" for row in found if row not in record]
    return found, absent, problems


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".", help="the working copy that holds the weights (default: here)")
    ap.add_argument("--hf-cache", help="the Hugging Face hub cache (default $HF_HUB_CACHE or ~/.cache/huggingface/hub)")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--check", action="store_true", help="compare with the committed record; write nothing")
    args = ap.parse_args()
    if args.check:
        found, absent, problems = check(Path(args.out) / f"{NAME}.json", args.root, args.hf_cache)
        print(f"{len(found)} counted, {len(absent)} absent; "
              + ("all equal to the record" if not problems else "differences:\n  " + "\n  ".join(problems)))
        raise SystemExit(1 if problems else 0)
    rows, absent = counts(args.root, args.hf_cache)
    if absent:
        raise SystemExit("weights not found, so the record would be incomplete: " + ", ".join(absent))
    result = {"provenance": provenance(), "models": rows, "absent": absent}
    print(write(args.out, NAME, result, markdown(result)).read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
