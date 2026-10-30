"""Assignment 4, Part E, task 3: what the checkpoint costs, structured and with the
conversation.

The runs measured are normal runs of the planned way with CHECKPOINT_CONVERSATION set
to a file: they save their checkpoints through the checkpointer as every run does, and
ways/planned.py saves a second copy of each, with every message the way had sent the
model so far, to that file (never to state/checkpoints.db).

    CHECKPOINT_CONVERSATION=state/checkpoints_with_conversation.db \\
        python run.py --way planned --issues 4201 --runs 3 --jobs 1
    python -m eval.checkpoint_bytes [--file state/checkpoints_with_conversation.db] [--write]

For each run in the file: the bytes its checkpoints take together (SQLite's summed
length of what was saved), in each store, and the number of checkpoints. --write puts
the means into reports/LAB_04.json as checkpoint_bytes.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from harness import ROOT
from state.checkpointer import Checkpointer, size_of

DEFAULT = ROOT / "state" / "checkpoints_with_conversation.db"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--file", type=Path, default=DEFAULT, help="the file with the conversation copies")
    p.add_argument("--write", action="store_true", help="write checkpoint_bytes into reports/LAB_04.json")
    a = p.parse_args()
    db = sqlite3.connect(a.file)
    runs = [r for (r,) in db.execute("SELECT run_id FROM checkpoints GROUP BY run_id ORDER BY MIN(seq)")]
    db.close()
    saver = Checkpointer()
    rows = []
    for rid in runs:
        structured, conversation = saver.size(rid), size_of(a.file, rid)
        rows.append((rid, len(saver.all(rid)), structured, conversation))
        print(f"{rid}: {rows[-1][1]} checkpoints, structured {structured:,} bytes, "
              f"with the conversation {conversation:,} bytes ({conversation / structured:.1f}x)")
    if not rows:
        raise SystemExit(f"no runs in {a.file}")
    out = {"structured": round(sum(r[2] for r in rows) / len(rows)),
           "with_conversation": round(sum(r[3] for r in rows) / len(rows)), "runs": len(rows)}
    print(json.dumps(out))
    if a.write:
        path = ROOT / "reports" / "LAB_04.json"
        report = json.loads(path.read_text())
        report["checkpoint_bytes"] = out
        path.write_text(json.dumps(report, indent=2) + "\n")
        print("wrote checkpoint_bytes to", path.relative_to(ROOT))


if __name__ == "__main__":
    main()
