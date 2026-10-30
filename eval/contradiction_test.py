"""Assignment 4, Part E, task 2: the contradiction test (slide 25): set a fact,
contradict it, check in a third session. Each session is its own process.

    session 1: python -m eval.store_candidates           # Part D: stores the maintainer's rule
    session 2: python -m eval.contradiction_test contradict
    session 3: python -m eval.contradiction_test retrieve [--write]

Session 2 stores a contradicting rule from the same maintainer, made up for the test,
as the first was stored (source user, about duplicates), and it supersedes the active
rule, as state/write_policy.md says a changed rule from a person does. Session 3 opens
the store fresh and retrieves the maintainer's rule on duplicates, and only that: the
active records from a user whose text is about duplicates. --write puts the IDs it
retrieved into reports/LAB_04.json as contradiction_test.
"""

from __future__ import annotations

import argparse
import json
import re

from harness import ROOT
from state.store import REPOSITORY, Store, now

ABOUT = re.compile(r"duplicate", re.IGNORECASE)
MAINTAINER = "priya-s (maintainer)"
NEW_RULE = ("For duplicates: label them `duplicate`, link the original, and close them after 14 days "
            "if the reporter has not replied.")


def rules(store: Store) -> list[dict]:
    """The maintainer's active rule on duplicates: what a run would be told to follow."""
    return [r for r in store.active(REPOSITORY) if r["source"] == "user" and ABOUT.search(r["text"])]


def contradict() -> None:
    store = Store()
    current = rules(store)
    if len(current) != 1:
        raise SystemExit(f"want exactly one active rule on duplicates to supersede; the store has {len(current)}")
    old = current[0]
    if old["text"] == NEW_RULE:
        print(f"record {old['id']} already states the new rule; nothing written")
        return
    record = {"repository": REPOSITORY, "issue": None, "kind": "semantic", "text": NEW_RULE, "source": "user",
              "written_at": now(), "origin": "ingested", "confirmed": True, "stated_by": MAINTAINER}
    new = store.supersede(old["id"], record)
    print(f"record {new} supersedes record {old['id']}: {NEW_RULE}")


def retrieve(write: bool) -> None:
    found = rules(Store())
    for r in found:
        print(json.dumps({k: r.get(k) for k in ("id", "kind", "source", "stated_by", "written_at", "confirmed",
                                                 "supersedes", "text")}))
    ids = [r["id"] for r in found]
    print("retrieved:", ids)
    if write:
        path = ROOT / "reports" / "LAB_04.json"
        report = json.loads(path.read_text())
        report["contradiction_test"] = ids
        path.write_text(json.dumps(report, indent=2) + "\n")
        print("wrote contradiction_test to", path.relative_to(ROOT))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("session", choices=["contradict", "retrieve"])
    p.add_argument("--write", action="store_true", help="session 3: write the IDs into reports/LAB_04.json")
    a = p.parse_args()
    contradict() if a.session == "contradict" else retrieve(a.write)


if __name__ == "__main__":
    main()
