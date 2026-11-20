"""Fetch BBO -- the ontology the pipeline populates, its SHACL shapes and its
licence -- pinned to one commit and checked.

    python3 -m text2bpmn.checks.fetch_bbo [--force]

BBO (Annane, Aussenac and Kamel, MELODI, 2019) is GPL-3.0, so its files are
fetched rather than committed here. The commit and the SHA-256 of every file
are fixed below; a download that does not match is not written and the
script fails. The ontology lands where the pipeline looks for it,
BPMNbasedOntologyV1_2.owl in the repository root, and the shapes and licence
in text2bpmn/checks/shacl/; git ignores all three. Run it once from the
repository root before --ontology-out or any ontology check.
"""
import argparse
import hashlib
import urllib.request
from pathlib import Path

REPOSITORY = "AminaANNANE/BBO_BPMNbasedOntology"
COMMIT = "cb835bbac1f603d0c59a360322400cae50677039"  # master, 2019-06-26
RAW = f"https://raw.githubusercontent.com/{REPOSITORY}/{COMMIT}/"
HERE = Path(__file__).parent / "shacl"
FILES = {  # upstream name: (where it goes, SHA-256)
    "BPMNbasedOntologyV1_2.owl": (Path("BPMNbasedOntologyV1_2.owl"),
                                  "91509c7ebb04bcda6628b140b86237365ddc8055799612f9f92a55a875b3de39"),
    "SHACLshapes.ttl": (HERE / "SHACLshapes.ttl",
                        "509f7477b71602733d35ae23e01580efeffa87ed5315e9f9ec7e4b7e515b4094"),
    "LICENSE": (HERE / "LICENSE-BBO", "3743f7a4ab5132f7dbeb88e68097657ab8374e74b46b6402efbe80ccfb1b6488"),
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def fetch(force=False):
    HERE.mkdir(parents=True, exist_ok=True)
    for upstream, (path, expected) in FILES.items():
        if path.exists() and not force and sha256(path.read_bytes()) == expected:
            print(f"ok      {path} (already present)")
            continue
        with urllib.request.urlopen(RAW + upstream, timeout=60) as response:
            data = response.read()
        if sha256(data) != expected:
            raise SystemExit(f"checksum mismatch for {RAW + upstream}: got {sha256(data)}, expected {expected}")
        path.write_bytes(data)
        print(f"fetched {path} from {RAW + upstream}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true", help="download again even if present and valid")
    args = ap.parse_args()
    fetch(args.force)


if __name__ == "__main__":
    main()
