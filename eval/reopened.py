"""Assignment 4, Part D: measure the reopened issue, 4207, with the store and with an
empty one.

    python -m eval.reopened --with RID,RID,... --empty RID,RID,... [--write]

For each run: whether it passes (Assignment 1's check(), read from the tracker by
run_id), its tool calls (its tool_call lines), its tokens (run_end.totals.total_tokens),
what its first store_read returned, the file its comment names, and where that file
came from: read in this run, or taken from memory (named by a record the run read,
and not read). --write puts the two sets into reports/LAB_04.json as reopened.
"""

from __future__ import annotations

import argparse
import json

import yaml

from eval.check_triage import check
from harness import ROOT
from harness.formats import normalize_path, parse_triage_comment
from harness.tracker import Tracker
from state.store import Store

ISSUE = 4207


def trace(run_id: str) -> list[dict]:
    return [json.loads(line) for line in (ROOT / "runs" / f"{run_id}.jsonl").open()]


def one(run_id: str, tracker: Tracker, answer: dict, records: dict) -> dict:
    lines = trace(run_id)
    calls = [r for r in lines if r["type"] == "tool_call"]
    end = next((r for r in reversed(lines) if r["type"] == "run_end"), {})
    read = next((r for r in lines if r["type"] == "store_read"), {})
    write = next((r for r in lines if r["type"] == "store_write"), {})
    comments = tracker.comments(run_id=run_id, issue=ISSUE)
    file = parse_triage_comment(comments[0]["body"])[1] if comments else None
    was_read = any(r["name"] == "code_read_file" and not r["is_error"]
                   and normalize_path(r["input"].get("path")) == file for r in calls)
    seen = [records.get(i, "") for i in read.get("records") or []]
    origin = ("none" if file in (None, "none") else "read in this run" if was_read
              else "taken from memory" if any(file in t for t in seen) else "not read in this run")
    return {"run_id": run_id, "passes": check(tracker, run_id, ISSUE, answer), "tool_calls": len(calls),
            "tokens": (end.get("totals") or {}).get("total_tokens", 0), "store_read": read.get("records"),
            "file": file, "file_was": origin, "store_write": write.get("action"), "finished": bool(end)}


def summary(rows: list[dict]) -> dict:
    n = len(rows)
    return {"runs": n, "passes": sum(r["passes"] for r in rows),
            "mean_tool_calls": round(sum(r["tool_calls"] for r in rows) / n, 2) if n else None,
            "mean_tokens": round(sum(r["tokens"] for r in rows) / n, 1) if n else None,
            "run_ids": [r["run_id"] for r in rows]}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--with", dest="with_store", required=True, help="comma-separated run_ids, with the store")
    p.add_argument("--empty", required=True, help="comma-separated run_ids, each with an empty store")
    p.add_argument("--write", action="store_true", help="write reopened into reports/LAB_04.json")
    a = p.parse_args()
    key = yaml.safe_load((ROOT / "fixtures" / "answers.yaml").read_text())
    answer = {int(k): v for part in ("eval", "dev") for k, v in key[part].items()}[ISSUE]   # as the checker reads it
    tracker = Tracker()
    records = {r["id"]: r["text"] for r in Store().records()}
    out = {}
    for name, ids in (("with_store", a.with_store), ("empty_store", a.empty)):
        rows = [one(rid.strip(), tracker, answer, records) for rid in ids.split(",") if rid.strip()]
        for r in rows:
            print(name, json.dumps(r))
        out[name] = summary(rows)
        print(name, json.dumps(out[name]))
    if a.write:
        path = ROOT / "reports" / "LAB_04.json"
        report = json.loads(path.read_text())
        report["reopened"] = out
        path.write_text(json.dumps(report, indent=2) + "\n")
        print("wrote reopened to", path.relative_to(ROOT))


if __name__ == "__main__":
    main()
