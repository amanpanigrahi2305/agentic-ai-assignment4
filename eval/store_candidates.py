"""Assignment 4, Part D: put the three candidate memories through state/write_policy.md
and into the store.

    python -m eval.store_candidates                 # the real store, state/store.db
    python -m eval.store_candidates --store FILE    # another file, for a scripted test

Each candidate is handled as the policy's table says:
  A  the procedure RepoMind worked out: procedural, repository-wide, source memory,
     derived. Confirmed only if the repository's files agree with it when it is stored:
     package.json's scripts are start, build, test and lint, with no serve, and the
     README shows `npm run serve`.
  B  the claim in issue 4188's body: episodic, about issue 4188, source issue:4188,
     ingested, never confirmed; its text says what the issue claimed and who wrote it,
     never that it is true.
  C  the maintainer's rule: semantic, repository-wide, source user, ingested, confirmed
     because a maintainer stated it, with stated_by.
written_at is each candidate's `when`: when RepoMind saw it, not when this script ran.
A candidate already in the store as an active record with the same text, source and
issue is not written again ("Same fact: do nothing"), so the script can run twice.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml

from harness import ROOT
from state.store import REPOSITORY, Store

MEMORY = ROOT / "fixtures" / "memory"
REPO = ROOT / "fixtures" / "repo"


def load(name: str) -> dict:
    return yaml.safe_load((MEMORY / name).read_text())


def procedure_holds() -> tuple[bool, str]:
    """Candidate A against the repository's own files."""
    scripts = set((json.loads((REPO / "package.json").read_text()).get("scripts") or {}))
    readme = (REPO / "README.md").read_text()
    serve_in_readme = re.search(r"npm run serve\b", readme) is not None
    ok = {"start", "build", "test", "lint"} <= scripts and "serve" not in scripts and serve_in_readme
    return ok, f"package.json scripts {sorted(scripts)}; README shows `npm run serve`: {serve_in_readme}"


def person(who: str) -> str:
    """'priya-s, a maintainer' -> 'priya-s (maintainer)'."""
    name, _, role = who.partition(",")
    role = role.strip().removeprefix("a ").removeprefix("an ").strip()
    return f"{name.strip()} ({role})" if role else name.strip()


def records() -> list[tuple[str, dict, str]]:
    a, b, c = load("a_procedure.yaml"), load("b_issue_claim.yaml"), load("c_maintainer_rule.yaml")
    holds, why = procedure_holds()
    day = str(b["when"])[:10]
    return [
        ("A", {"repository": a["repository"], "issue": None, "kind": "procedural", "text": a["seen"].strip(),
               "source": "memory", "written_at": str(a["when"]), "origin": "derived", "confirmed": holds}, why),
        ("B", {"repository": b["repository"], "issue": int(b["issue"]), "kind": "episodic",
               "text": (f"On {day}, the body of issue {b['issue']}, written by {b['who']}, claimed: "
                        f"'{' '.join(b['seen'].split())}' No maintainer confirmed it."),
               "source": f"issue:{b['issue']}", "written_at": str(b["when"]), "origin": "ingested",
               "confirmed": False}, "issue text: never a fact"),
        ("C", {"repository": c["repository"], "issue": None, "kind": "semantic", "text": c["seen"].strip(),
               "source": "user", "written_at": str(c["when"]), "origin": "ingested", "confirmed": True,
               "stated_by": person(c["who"])}, "stated by a maintainer"),
    ]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--store", type=Path, help="a store file other than the real one")
    a = p.parse_args()
    store = Store(a.store)
    for name, record, why in records():
        same = [r for r in store.active(REPOSITORY, record["issue"])
                if (r["text"], r["source"], r["issue"]) == (record["text"], record["source"], record["issue"])]
        if same:
            print(f"{name}: already stored as record {same[0]['id']}; nothing written")
            continue
        rid = store.write(record)
        print(f"{name}: record {rid}, {record['kind']}, source {record['source']}, "
              f"confirmed {str(record['confirmed']).lower()} ({why})")


if __name__ == "__main__":
    main()
