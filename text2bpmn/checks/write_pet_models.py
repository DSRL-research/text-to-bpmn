"""Write a PET run's models as BPMN files, from the process.json each document saved.

    python3 -m text2bpmn.checks.write_pet_models runs/ideas/idea1b/pet_decisions2 --out OUT
    python3 -m text2bpmn.checks.xsd_validate OUT
    python3 -m text2bpmn.checks.soundness OUT

The PET flow runs (text2bpmn/run_final.py pet_flows) score the pipeline's
extraction and write no BPMN file, so their models were never checked against
the BPMN schema or for soundness. Since 2026-11-11 each document keeps its
extraction in process.json; this puts it through the Validation Layer and the
serializer exactly as a case-study run does (text2bpmn/checks/pilot_run.py),
one OUT/<document>/model.bpmn each. A model the Validation Layer refuses is
listed and gets no file.
"""
import argparse
import json
from pathlib import Path

from text2bpmn.bpmn_xml import to_xml
from text2bpmn.structure import validate


def write(run, out):
    written, refused = [], {}
    for saved in sorted(Path(run).glob("documents/*/process.json")):
        name = saved.parent.name
        try:
            process = validate(json.loads(saved.read_text(encoding="utf-8"))["structured_data"])
        except ValueError as e:
            refused[name] = str(e)
            continue
        folder = Path(out) / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "model.bpmn").write_text(to_xml(process, name), encoding="utf-8")
        written.append(name)
    return written, refused


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run", help="a PET run folder with documents/<name>/process.json")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    written, refused = write(args.run, args.out)
    print(f"{len(written)} models written to {args.out}; {len(refused)} refused by the Validation Layer")
    for name, error in refused.items():
        print(f"   {name}: {error}")


if __name__ == "__main__":
    main()
