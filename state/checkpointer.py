"""Assignment 4, Part A: the checkpointer. This file is yours.

A checkpointer saves one run's state, so its checkpoints are keyed by the run's
run_id (frameworks call one run's line of checkpoints a thread). Save them on a
durable backend: a SQLite file such as state/checkpoints.db is fine; an in-memory
store is not, because it dies with the process. A sync save is on disk before
save() returns.

The checker calls these, with these exact signatures (checks/FORMATS.md, section
12.4), so keep them:

    Checkpointer(path=None)                    # None: your default file
    .save(run_id, checkpoint, *, step, mode)   # one checkpoint; mode is sync, async or exit
    .last(run_id) -> dict | None               # the run's latest checkpoint, or None
    .all(run_id) -> list[dict]                 # every checkpoint the run saved, oldest first
    .runs() -> list[str]                       # every run_id that has a checkpoint

A checkpoint is a dict of exactly the five fields in harness.formats.CHECKPOINT_FIELDS:
plan, step_status, completed_calls (each with its idempotency key), findings and
current_step. Everything in it must serialize, and the conversation is not in it.
Every save is also a trace line, trace.event("checkpoint", step=..., mode=...),
which your way writes.

The three durability modes (Lecture 4, slide 12), as save() writes them:
  - sync: written and committed before save() returns, with SQLite's synchronous
    mode FULL, so a kill -9 the next instant cannot lose it;
  - async: handed to a background thread and save() returns at once; a crash
    before the thread commits loses it;
  - exit: kept in memory until flush(), which runs when the process exits
    normally; a crash loses every exit checkpoint of the run.
The mode is one per run (RepoMind's is sync, ways/planned.py, DURABILITY); the
checkpointer takes whatever mode it is given.
"""

from __future__ import annotations

import atexit
import json
import queue
import sqlite3
import threading
import time
from pathlib import Path

from harness import ROOT
from harness.formats import CHECKPOINT_FIELDS, DURABILITY_MODES

DEFAULT = ROOT / "state" / "checkpoints.db"
CONVERSATION_KEYS = ("conversation", "messages", "history", "transcript")

SCHEMA = """
CREATE TABLE IF NOT EXISTS checkpoints (
    seq      INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id   TEXT NOT NULL,
    step     TEXT,
    mode     TEXT NOT NULL,
    saved_at TEXT NOT NULL,
    data     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS checkpoints_run ON checkpoints (run_id, seq);
"""


def conversation_in(value, path: str = "checkpoint") -> str | None:
    """Where a checkpoint holds a conversation, or None: a key FORMATS.md 12.4 forbids,
    or a list of chat messages (objects with role and content)."""
    if isinstance(value, dict):
        for key, inner in value.items():
            if str(key).lower() in CONVERSATION_KEYS:
                return f"{path}.{key}"
            found = conversation_in(inner, f"{path}.{key}")
            if found:
                return found
    elif isinstance(value, list):
        if any(isinstance(v, dict) and "role" in v and "content" in v for v in value):
            return path
        for i, inner in enumerate(value):
            found = conversation_in(inner, f"{path}[{i}]")
            if found:
                return found
    return None


class Checkpointer:
    def __init__(self, path: Path | None = None):
        self.path = Path(path or DEFAULT)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._pending: list[tuple] = []        # exit mode: kept until flush()
        self._queue: queue.Queue | None = None  # async mode: the background writer's work
        self._lock = threading.Lock()
        with self._connect() as db:
            db.executescript(SCHEMA)
        atexit.register(self.flush)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30)
        db.execute("PRAGMA synchronous=FULL")   # a commit is on disk before it returns
        return db

    def _insert(self, rows: list[tuple]) -> None:
        if not rows:
            return
        db = self._connect()
        try:
            with db:
                db.executemany("INSERT INTO checkpoints (run_id, step, mode, saved_at, data) VALUES (?, ?, ?, ?, ?)",
                               rows)
        finally:
            db.close()

    # -- writing -----------------------------------------------------------------------
    def save(self, run_id: str, checkpoint: dict, *, step, mode: str = "sync") -> None:
        if mode not in DURABILITY_MODES:
            raise ValueError(f"mode is one of {DURABILITY_MODES}, not {mode!r}")
        if set(checkpoint) != set(CHECKPOINT_FIELDS):
            raise ValueError(f"a checkpoint has exactly the fields {CHECKPOINT_FIELDS}; this one has {sorted(checkpoint)}")
        where = conversation_in(checkpoint)
        if where:
            raise ValueError(f"a checkpoint never holds the conversation; found one at {where}")
        data = json.dumps({k: checkpoint[k] for k in CHECKPOINT_FIELDS})   # raises if anything will not serialize
        row = (run_id, json.dumps(step), mode, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), data)
        if mode == "sync":
            self._insert([row])
        elif mode == "async":
            self._writer().put(row)
        else:
            with self._lock:
                self._pending.append(row)

    def _writer(self) -> queue.Queue:
        with self._lock:
            if self._queue is None:
                self._queue = queue.Queue()
                threading.Thread(target=self._drain_forever, daemon=True).start()
            return self._queue

    def _drain_forever(self) -> None:
        while True:
            row = self._queue.get()
            try:
                self._insert([row])
            finally:
                self._queue.task_done()

    def flush(self) -> None:
        """Write every async and exit checkpoint still in memory. Runs at a normal exit;
        a kill -9 never reaches it, which is what those two modes risk."""
        if self._queue is not None:
            self._queue.join()
        with self._lock:
            rows, self._pending = self._pending, []
        self._insert(rows)

    # -- reading -----------------------------------------------------------------------
    def _rows(self, sql: str, args: tuple = ()) -> list:
        if self._queue is not None:
            self._queue.join()   # this process sees its own async saves once they land
        db = self._connect()
        try:
            return db.execute(sql, args).fetchall()
        finally:
            db.close()

    def last(self, run_id: str) -> dict | None:
        rows = self._rows("SELECT data FROM checkpoints WHERE run_id = ? ORDER BY seq DESC LIMIT 1", (run_id,))
        return json.loads(rows[0][0]) if rows else None

    def all(self, run_id: str) -> list[dict]:
        return [json.loads(d) for (d,) in self._rows("SELECT data FROM checkpoints WHERE run_id = ? ORDER BY seq",
                                                     (run_id,))]

    def runs(self) -> list[str]:
        return [r for (r,) in self._rows("SELECT run_id FROM checkpoints GROUP BY run_id ORDER BY MIN(seq)")]

    def size(self, run_id: str) -> int:
        """The bytes one run's checkpoints take together, as saved (Part E)."""
        rows = self._rows("SELECT COALESCE(SUM(LENGTH(CAST(data AS BLOB))), 0) FROM checkpoints WHERE run_id = ?",
                          (run_id,))
        return int(rows[0][0])
