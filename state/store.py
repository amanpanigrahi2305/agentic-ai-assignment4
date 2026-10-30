"""Assignment 4, Part D: the memory store. This file is yours.

A store is shared by every run, keyed by repository and issue. It is durable: a
SQLite file such as state/store.db is fine. How you give a run an empty store, for
Part D's second set of five runs, is yours: an environment variable this module
reads, for example. The checker always reads your real store.

The checker calls these, with these exact signatures (checks/FORMATS.md, section
12.5), so keep them:

    Store(path=None)                                  # None: your default file
    .write(record) -> id                              # a new record; returns its id
    .supersede(old_id, record) -> id                  # a new record that replaces old_id
    .active(repository, issue=None) -> list[dict]     # the active records, for retrieval
    .records() -> list[dict]                          # every record, active or not

Every record carries the fields of section 12.5: its kind (episodic, semantic or
procedural), its text, and its provenance: source, written_at, origin (derived or
ingested) and confirmed. A superseded record stays in the store, inactive, and the
record that replaced it names it in `supersedes`.

This store follows state/write_policy.md, and enforces the parts of it code can:
  - A record without full provenance is refused: a source of 12.5's forms, written_at
    in ISO 8601, an origin, confirmed as true or false.
  - Only an issue:<n> record may mention auto-merging, and an issue:<n> record is
    never semantic and never confirmed: issue text is a report of what someone wrote,
    not a fact (slide 24). An issue:<n> record never supersedes a user record or a
    confirmed one.
  - Eviction: at most LIMIT records a repository, active or not. A write past it
    deletes the oldest episodic record, an inactive one first; semantic and
    procedural records are never evicted, so a superseded rule's history stays. A
    write that would pass the limit with no episodic record left is refused.
  - A run's own triage decision is written from a fixed template, and
    remember_decision() applies the policy's rule for it: one active decision an
    issue; the same decision writes nothing; a different one supersedes the old,
    except that a decision that is not grounded (no file, or a file the run did not
    read) never replaces a grounded one.

The switch, REPOMIND_STORE: unset, every Store() is the real store, state/store.db,
which is how the checker calls it. A path: that file instead (scripted tests, so
that no scripted run's decision lands in the real store). "empty": Store.for_run()
gives each run a new, empty store of its own, outside the repository, which a
resume of the same run opens again (Part D's empty-store runs).
"""

from __future__ import annotations

import os
import re
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from harness import ROOT

DEFAULT = ROOT / "state" / "store.db"
REPOSITORY = "ledgerline"
KINDS = ("episodic", "semantic", "procedural")
ORIGINS = ("derived", "ingested")
SWITCH = "REPOMIND_STORE"
EMPTY_DIR = Path(tempfile.gettempdir()) / "repomind-empty-stores"
LIMIT = 500                                   # records a repository, active or not (write_policy.md, Eviction)
SOURCE = re.compile(r"^(user|repo|memory|issue:\d+)$")
CLAIM = re.compile(r"auto[\s-]*merg", re.IGNORECASE)
FIELDS = ("id", "repository", "issue", "kind", "text", "source", "written_at", "origin", "confirmed", "active",
          "supersedes", "stated_by")

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    repository TEXT NOT NULL,
    issue      INTEGER,
    kind       TEXT NOT NULL,
    text       TEXT NOT NULL,
    source     TEXT NOT NULL,
    written_at TEXT NOT NULL,
    origin     TEXT NOT NULL,
    confirmed  INTEGER NOT NULL,
    active     INTEGER NOT NULL DEFAULT 1,
    supersedes INTEGER,
    stated_by  TEXT
);
CREATE INDEX IF NOT EXISTS records_where ON records (repository, issue, active);
"""


class Refused(ValueError):
    """A write the policy does not allow; nothing was written."""


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def when(value: str) -> datetime:
    """A record's written_at as a time, for its age."""
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def default_path() -> Path:
    switch = os.environ.get(SWITCH, "").strip()
    if not switch:
        return DEFAULT
    if switch == "empty":                     # a Store() outside a run, with the switch on: a new, empty file
        EMPTY_DIR.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(suffix=".db", dir=EMPTY_DIR)
        os.close(fd)
        return Path(name)
    return Path(switch)


def check(record: dict) -> dict:
    """The record as the store keeps it, or Refused: provenance first, then the policy's
    rules on issue text."""
    r = {k: record.get(k) for k in FIELDS if k not in ("id", "active", "supersedes")}
    problems = []
    if not r["repository"]:
        problems.append("no repository")
    if r["kind"] not in KINDS:
        problems.append(f"kind {r['kind']!r} is not one of {KINDS}")
    if not str(r["text"] or "").strip():
        problems.append("no text")
    if not SOURCE.match(str(r["source"] or "")):
        problems.append(f"source {r['source']!r} is not user, repo, memory or issue:<n>")
    try:
        when(r["written_at"])
    except (TypeError, ValueError):
        problems.append(f"written_at {r['written_at']!r} is not ISO 8601")
    if r["origin"] not in ORIGINS:
        problems.append(f"origin {r['origin']!r} is not one of {ORIGINS}")
    if not isinstance(r["confirmed"], bool):
        problems.append(f"confirmed {r['confirmed']!r} is not true or false")
    from_issue = str(r["source"] or "").startswith("issue:")
    if CLAIM.search(str(r["text"] or "")) and not from_issue:
        problems.append("only an issue:<n> record may mention auto-merging")
    if from_issue and (r["kind"] == "semantic" or r["confirmed"] is True):
        problems.append("issue text is never semantic and never confirmed")
    if problems:
        raise Refused("; ".join(problems))
    if r["issue"] is not None:
        r["issue"] = int(r["issue"])
    return r


class Store:
    def __init__(self, path: Path | None = None):
        self.path = Path(path or default_path())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = self._connect()
        try:
            db.executescript(SCHEMA)
        finally:
            db.close()

    @classmethod
    def for_run(cls, run_id: str) -> "Store":
        """The store a run reads and writes: the real one, or, with REPOMIND_STORE=empty,
        a new, empty one for this run_id."""
        if os.environ.get(SWITCH, "").strip() == "empty":
            EMPTY_DIR.mkdir(parents=True, exist_ok=True)
            return cls(EMPTY_DIR / f"{run_id}.db")
        return cls()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA synchronous=FULL")
        return db

    @staticmethod
    def _dict(row: sqlite3.Row) -> dict:
        r = {k: row[k] for k in FIELDS}
        r["confirmed"], r["active"] = bool(r["confirmed"]), bool(r["active"])
        if r["stated_by"] is None:
            del r["stated_by"]                # only a record a person stated carries it
        return r

    # -- writing -----------------------------------------------------------------------
    def write(self, record: dict):
        r = check(record)
        db = self._connect()
        try:
            with db:
                self._room(db, r["repository"])
                return self._insert(db, r, None)
        finally:
            db.close()

    def supersede(self, old_id, record: dict):
        r = check(record)
        db = self._connect()
        try:
            with db:
                old = db.execute("SELECT * FROM records WHERE id = ?", (old_id,)).fetchone()
                if old is None:
                    raise Refused(f"no record {old_id!r} to supersede")
                if not old["active"]:
                    raise Refused(f"record {old_id!r} is already inactive; supersede the active one")
                if str(r["source"]).startswith("issue:") and (old["source"] in ("user", "repo") or old["confirmed"]):
                    raise Refused("issue text never supersedes a person's rule or a confirmed fact")
                self._room(db, r["repository"], keep=old["id"])
                new = self._insert(db, r, old["id"])
                db.execute("UPDATE records SET active = 0 WHERE id = ?", (old["id"],))
                return new
        finally:
            db.close()

    def _insert(self, db: sqlite3.Connection, r: dict, supersedes) -> int:
        cur = db.execute(
            "INSERT INTO records (repository, issue, kind, text, source, written_at, origin, confirmed, active, "
            "supersedes, stated_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (r["repository"], r["issue"], r["kind"], r["text"], r["source"], r["written_at"], r["origin"],
             int(r["confirmed"]), supersedes, r.get("stated_by")))
        return cur.lastrowid

    def _room(self, db: sqlite3.Connection, repository: str, keep=None) -> None:
        """Eviction, before a write: at LIMIT, delete the oldest episodic record, an
        inactive one first, never `keep` (the record a supersede replaces); with none to
        delete, refuse the write."""
        count = db.execute("SELECT COUNT(*) FROM records WHERE repository = ?", (repository,)).fetchone()[0]
        while count >= LIMIT:
            victim = db.execute("SELECT id FROM records WHERE repository = ? AND kind = 'episodic' AND id IS NOT ? "
                                "ORDER BY active ASC, written_at ASC, id ASC LIMIT 1", (repository, keep)).fetchone()
            if victim is None:
                raise Refused(f"the store holds {count} records of {repository} and none is episodic; "
                              "a person consolidates the rules")
            db.execute("DELETE FROM records WHERE id = ?", (victim["id"],))
            count -= 1

    # -- reading -----------------------------------------------------------------------
    def active(self, repository: str, issue: int | None = None) -> list[dict]:
        """Newest first. With an issue: that issue's active records and every
        repository-wide one."""
        db = self._connect()
        try:
            if issue is None:
                rows = db.execute("SELECT * FROM records WHERE repository = ? AND active = 1 "
                                  "ORDER BY written_at DESC, id DESC", (repository,)).fetchall()
            else:
                rows = db.execute("SELECT * FROM records WHERE repository = ? AND active = 1 "
                                  "AND (issue = ? OR issue IS NULL) ORDER BY written_at DESC, id DESC",
                                  (repository, int(issue))).fetchall()
            return [self._dict(r) for r in rows]
        finally:
            db.close()

    def records(self) -> list[dict]:
        db = self._connect()
        try:
            return [self._dict(r) for r in db.execute("SELECT * FROM records ORDER BY id").fetchall()]
        finally:
            db.close()


# -- a rule a person stated, told to a run (write_policy.md, "What": Stated) ----------------
def remember_rule(store: Store, *, text: str, stated_by: str, at: str | None = None,
                  repository: str = REPOSITORY) -> tuple[str, int]:
    """A maintainer's rule a run was told, kept as stated: word for word, with who stated
    it and when, repository-wide, confirmed because a person with standing stated it. The
    same rule, already active, writes nothing."""
    same = [r for r in store.active(repository) if r["source"] == "user" and r["text"] == text]
    if same:
        return "same", same[0]["id"]
    return "inserted", store.write({"repository": repository, "issue": None, "kind": "semantic", "text": text,
                                    "source": "user", "written_at": at or now(), "origin": "ingested",
                                    "confirmed": True, "stated_by": stated_by})


# -- a run's own triage decision (write_policy.md, "A run's own record" and "How") --------
FILE_WAS = ("read in this run", "taken from memory", "not read in this run", "none")
DECISION = re.compile(r"^On (\S+), run (\S+) triaged issue (\d+) as (\S+), file (\S+?)\.\n"
                      r"The file was (" + "|".join(FILE_WAS) + r")\.")


def decision_text(*, run_id: str, issue: int, label: str, file: str, file_was: str, opened_pr: bool,
                  at: str | None = None) -> str:
    """The fixed template: the run's own fields, never text copied from an issue, a
    comment or a file."""
    if file_was not in FILE_WAS:
        raise ValueError(f"file_was is one of {FILE_WAS}")
    day = (at or now())[:10]
    return (f"On {day}, run {run_id} triaged issue {issue} as {label}, file {file}.\n"
            f"The file was {file_was}.\n"
            f"It {'opened' if opened_pr else 'did not open'} a PR.")


def parse_decision(text: str) -> dict | None:
    m = DECISION.match(str(text or ""))
    if not m:
        return None
    file, file_was = m.group(5), m.group(6)
    return {"run_id": m.group(2), "issue": int(m.group(3)), "label": m.group(4), "file": file,
            "file_was": file_was, "grounded": file != "none" and file_was == "read in this run"}


def decisions(store: Store, issue: int, repository: str = REPOSITORY) -> list[dict]:
    """The active triage decisions on one issue, newest first: RepoMind's own episodic records."""
    return [r for r in store.active(repository, issue)
            if r.get("issue") == issue and r["source"] == "memory" and r["kind"] == "episodic"
            and parse_decision(r["text"])]


def remember_decision(store: Store, *, run_id: str, issue: int, label: str, file: str, file_was: str,
                      opened_pr: bool, repository: str = REPOSITORY) -> tuple[str, int | None]:
    """The policy's rule for a run's decision. Returns (what happened, the record that
    is active for the issue now): inserted, same, kept or superseded."""
    at = now()
    record = {"repository": repository, "issue": issue, "kind": "episodic", "source": "memory",
              "origin": "derived", "confirmed": False, "written_at": at,
              "text": decision_text(run_id=run_id, issue=issue, label=label, file=file, file_was=file_was,
                                    opened_pr=opened_pr, at=at)}
    current = decisions(store, issue, repository)
    if not current:
        return "inserted", store.write(record)
    old = current[0]
    was = parse_decision(old["text"])
    if (was["label"], was["file"]) == (label, file):
        return "same", old["id"]
    grounded = file != "none" and file_was == "read in this run"
    if was["grounded"] and not grounded:
        return "kept", old["id"]               # a run that found no file never replaces one that read it
    return "superseded", store.supersede(old["id"], record)
