"""Table 5's comparator sources: where text2bpmn/pet_strict.py pins Neuberger et al.'s files, and do the pins hold?

    python3 -m text2bpmn.checks.table5_sources [--fetched DIR] [--no-network]
        # -> runs/checks/final-3/open_analyses/table5_sources.{md,json}

pet_strict.py holds no commit itself: it reads the manifest
text2bpmn/baselines/neuberger_sources.json (SOURCES), which gives each file's
repository, commit, path and sha256, and --fetch downloads each from
raw.githubusercontent.com/<repo>/<commit>/<path> and checks the sha256 (fetch()).
This check lists every pin with its line in the manifest, asks GitHub with
`git ls-remote` which refs point at each pinned commit (no code is downloaded),
and checks the files already fetched (--fetched, read only) against the manifest.
"""
import argparse
import hashlib
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path

MANIFEST = Path("text2bpmn/baselines/neuberger_sources.json")
PET_STRICT = Path("text2bpmn/pet_strict.py")
OUT = Path("runs/checks/final-3/open_analyses/table5_sources")
PAPERS = {"JulianNeuberger/pet-baselines": "CoopIS 2023 (RuleRelEx, BoostRelEx; gold folds)",
          "JulianNeuberger/llm-process-generation": "ER 2024 (eight LLMs; gold all.new.jsonl)"}


def pins():
    """[(manifest line of the commit, repo, commit, path, sha256)]."""
    lines = MANIFEST.read_text(encoding="utf-8").splitlines()
    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]
    out, at = [], 0
    for entry in entries:
        # the entry's "commit" line, then its "path" line, in file order
        commit_line = next(i for i in range(at, len(lines)) if f'"commit": "{entry["commit"]}"' in lines[i])
        path_line = next(i for i in range(commit_line, len(lines)) if f'"path": "{entry["path"]}"' in lines[i])
        at = path_line + 1
        out.append({"repo": entry["repo"], "commit": entry["commit"], "path": entry["path"],
                    "sha256": entry["sha256"], "commit_line": commit_line + 1, "path_line": path_line + 1})
    return out


def code_lines():
    """The lines of pet_strict.py that point at the manifest, build the URL, and name the files it reads."""
    wanted = {"SOURCES = ": "manifest path", "raw.githubusercontent.com": "download URL built from repo/commit/path",
              "ALL_NEW = ": "ER 2024 gold", "FOLD = ": "CoopIS 2023 gold folds",
              "STORED = ": "CoopIS 2023 stored predictions", '"/answers/" not in': "ER 2024 answer files (llm_answers)",
              "BASELINES = ": "RuleRelEx / BoostRelEx prediction folders", "def fetch": "fetch()",
              "def checked": "checked(): sha256 check before every read"}
    out = []
    for number, line in enumerate(PET_STRICT.read_text(encoding="utf-8").splitlines(), 1):
        for key, what in wanted.items():
            if key in line:
                out.append({"line": number, "what": what, "code": line.strip()})
    return out


def ls_remote(repo):
    try:
        done = subprocess.run(["git", "ls-remote", f"https://github.com/{repo}"], capture_output=True, text=True,
                              timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"error": str(e)}
    if done.returncode:
        return {"error": done.stderr.strip()}
    refs = defaultdict(list)
    for line in done.stdout.splitlines():
        sha, ref = line.split("\t")
        refs[sha].append(ref)
    return {"refs": dict(refs)}


def analyse(fetched, network):
    listed = pins()
    by_repo = defaultdict(list)
    for p in listed:
        by_repo[(p["repo"], p["commit"])].append(p)
    repos = []
    for (repo, commit), files in by_repo.items():
        remote = ls_remote(repo) if network else {"error": "not asked (--no-network)"}
        refs = remote.get("refs", {}).get(commit, [])
        local = []
        for f in files:
            path = Path(fetched) / repo.split("/")[1] / f["path"]
            local.append(path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == f["sha256"])
        repos.append({"repo": repo, "url": f"https://github.com/{repo}", "paper": PAPERS.get(repo, ""),
                      "commit": commit, "manifest_commit_lines": [f["commit_line"] for f in files],
                      "files": [{"path": f["path"], "manifest_line": f["path_line"], "sha256": f["sha256"]}
                                for f in files],
                      "ls_remote": {"error": remote["error"]} if "error" in remote else
                      {"refs_at_pinned_commit": refs, "head": next((s for s, r in remote["refs"].items()
                                                                    if "HEAD" in r), None)},
                      "fetched_files_matching_sha256": f"{sum(local)}/{len(local)}"})
    return {"manifest": str(MANIFEST), "pet_strict_lines": code_lines(), "repositories": repos}


def markdown(r):
    lines = ["# Table 5 comparator sources: pins and their check", "",
             "Generated by `text2bpmn/checks/table5_sources.py`. `text2bpmn/pet_strict.py` holds no commit itself; "
             f"it reads the pins from `{r['manifest']}`.", "", "## pet_strict.py lines", "",
             "| line | what | code |", "|---|---|---|"]
    lines += [f"| {x['line']} | {x['what']} | `{x['code'][:110]}` |" for x in r["pet_strict_lines"]]
    for repo in r["repositories"]:
        ls = repo["ls_remote"]
        state = (f"refs at the pinned commit: {', '.join(ls['refs_at_pinned_commit']) or 'none (commit not a ref tip)'}"
                 f"; remote HEAD {ls['head']}" if "error" not in ls else f"not checked: {ls['error']}")
        lines += ["", f"## {repo['repo']} ({repo['paper']})", "",
                  f"- URL: {repo['url']}", f"- commit: `{repo['commit']}`",
                  f"- manifest lines with this commit: {', '.join(map(str, repo['manifest_commit_lines']))}",
                  f"- git ls-remote: {state}",
                  f"- fetched files matching the pinned sha256: {repo['fetched_files_matching_sha256']}", "",
                  "| manifest line | path |", "|---|---|"]
        lines += [f"| {f['manifest_line']} | `{f['path']}` |" for f in repo["files"]]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fetched", default="text2bpmn/baselines/neuberger",
                    help="folder pet_strict.py --fetch wrote to (read only)")
    ap.add_argument("--no-network", action="store_true")
    args = ap.parse_args()
    result = analyse(args.fetched, not args.no_network)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.with_suffix(".json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    text = markdown(result)
    OUT.with_suffix(".md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
