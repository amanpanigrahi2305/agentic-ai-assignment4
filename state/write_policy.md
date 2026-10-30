# RepoMind's Write Policy

This policy defines what RepoMind can store in `state/store.py`. All runs share the same store, while each run has its own checkpoint. The checkpoint preserves the state of an individual run; the store preserves knowledge across runs. A record is written to the store only when it meets the rules described below.

## When to Write

- A run writes to the store only at the end, after successfully posting its comment.
- A run that escalates, is held by the second pass, or fails does not write anything.
- If a run crashes, it writes nothing at the time of the crash. Its resumed execution writes once, at the end. The rules in the "How" section ensure that replaying the same write does not create another record.
- Outside a run, a script may write a record once its claim has been checked or stated. This applies to the three candidates and to a rule explicitly stated by a person with standing.
- Nothing is written during a run. A search result, file read, draft, revision, or second-pass result is not enough to justify a write because a later step could still change the outcome.

## What to Store

RepoMind keeps three types of memory:

1. **Expensive to derive:** A procedure that took a run several steps to work out (candidate A), or a run's triage decision, which costs a full run to produce.
2. **Stated:** A rule provided word for word by a person with standing, along with who stated it and when (candidate C). If a run is given a maintainer's rule, it writes that rule at the end in the same way.
3. **Confirmed:** A fact that RepoMind has checked against the repository's files.

RepoMind does not store:

- Search results, file contents, plans, drafts, or conversation history.
- An unverified guess, except as a run's own episodic decision, which is always unconfirmed.
- Issue text as an established fact. Anyone can write an issue, so its contents are stored only as an episodic, unconfirmed record of what the issue claimed (candidate B).
- The state of a run, because the checkpoint already holds it.

**A run's own record.** Every run that successfully posts its comment produces one triage decision, including runs where the file is `none`. This decision is worth retaining because it takes a full run to produce. A `file: none` decision tells a later run that an earlier run found no file. The seed run for issue 4207 must also leave a decision for subsequent runs. The rules in the "How" section decide whether the decision is written as a new record.

The record's text comes from a fixed template populated with fields from the run itself:

    On <date>, run <run_id> triaged issue <n> as <label>, file <path or none>.
    The file was <read in this run | taken from memory | not read in this run | none>.
    It <opened | did not open> a PR.

"Taken from memory" means a record the run read named the file, and the run did not read it; "not read in this run" means the run named a file it neither read nor found in memory.

The template never copies text from an issue, comment, or repository file. Only an `issue:<n>` record may mention auto-merging. If a run's record would mention auto-merging, the run does not write that record.

## How to Write

- **New fact:** Insert a new record.
- **Same fact:** Do nothing. Keep the existing active record.
- **Contradicted fact:** Write a new record with `supersedes: <old id>` and mark the old record inactive. Keep the old record in the store, but ensure only one record for that fact remains active.
- **Changed rule from a person:** A new rule on the same subject, stated by a person with standing, supersedes the previous rule rather than sitting alongside it. For example, "close duplicates after 14 days" from priya-s supersedes candidate C.
- **Claim from an issue:** It can never supersede a `user` record or a fact confirmed against the repository.
- **Contradicted procedure:** If the repository's files contradict a stored procedure, the corrected procedure must first be checked against the files, then supersede the old one.
- **New run decision for an existing issue:** Each issue has only one active triage decision. A decision is *grounded* when its file is not `none` and the run read that file in this run. If the new label and file match the active decision, write nothing. If either differs, the new decision supersedes the old one, unless the old one is grounded and the new one is not: then write nothing, and the grounded decision stays active. A run that found no file never replaces a run that read one. In my runs of issue 4201, `planned-4201-s01-75fa87` read its file and named it, and the next run, `planned-4201-s01-e0eecc`, drafted `file: none`; a rule where the latest decision always wins would have replaced the first with the second.

## Provenance

Every record must include the following fields:

- `source`: `user` for a person with standing, `issue:<n>` for text from an issue, `repo` for facts from the repository's own files, or `memory` for RepoMind's own work.
- `written_at`: An ISO 8601 timestamp representing when RepoMind first encountered the information, if it saw it before storing it (such as a candidate's `when`). Otherwise, use the time the record is stored. This ensures the record's age reflects how old the knowledge is, rather than how old the database row is.
- `origin`: `derived` if RepoMind worked out the information itself; `ingested` if it read the information from an external source, such as an issue, a person's comment, or a note supplied to a run.
- `confirmed`:
  - `true` if a person with standing stated the information, or if RepoMind checked it against the repository's files when storing it.
  - `false` for all issue text and every run's own decision. Nothing outside the run verifies that decision. Only a person with standing could confirm it, and RepoMind currently has no such signal.
  - A record does not become confirmed simply because it is old or because multiple runs repeat it.
  - Confirmation does not make a record permanent. A later rule from a person with standing can still supersede it.
- `stated_by`: The person and their role, for every record stated by a person. Other records do not have this field.
- `issue`: `null` for repository-wide information, such as a procedure or rule. Use the issue number for records about a specific issue, such as a run's decision or an issue's claim.

**Record kinds:**

- `episodic`: Something that happened at a particular time, such as a run's decision or what an issue said.
- `semantic`: Something currently considered true, such as a rule stated by a person with standing or a fact confirmed against the repository's files.
- `procedural`: Instructions for how to do something in this repository.

Text from an issue is never `semantic`, and a run's unverified guess is never `semantic`.

## The Three Candidates

| Candidate | Stored? | Kind | issue | source | origin | confirmed | written_at | Invites |
|---|---|---|---|---|---|---|---|---|
| A | Yes, word for word | procedural | `null` | `memory` | `derived` | `true`: checked against `package.json` and the README when stored | `2026-10-02T14:12:09Z` | staleness |
| B | Yes, as an episode, never as a fact | episodic | `4188` | `issue:4188` | `ingested` | `false` | `2026-09-30T08:41:37Z` | poisoning |
| C | Yes, word for word, with `stated_by: priya-s (maintainer)` | semantic | `null` | `user` | `ingested` | `true`: stated by a maintainer | `2026-09-21T16:05:52Z` | contradiction when it changes |

- **Candidate A:** Its `issue` is `null` because the procedure applies to every UI bug in Ledgerline, not just issue 4191. The script that stores it checks it against the repository first: `package.json`'s scripts are `start`, `build`, `test` and `lint`, with no `serve`, and the README shows `npm run serve`. If that check fails, A is stored with `confirmed: false`. Each read displays its age, making it possible to identify when the procedure may be stale.
- **Candidate B:** Its text is: "On 2026-09-30, the body of issue 4188, written by tk-dev-91, an account outside the team, claimed: '<the claim, word for word>'. No maintainer confirmed it." A run reads it only on issue 4188, and it is never passed to the planner.
- **Candidate C:** Its `issue` is `null` because it is a repository-wide rule. If the rule changes, the new rule supersedes candidate C.

## Eviction

- **Size limit:** Each repository can have up to 500 records. Inactive records count toward this limit.
- **Eviction rule:** The store uses age-based decay with the 500-record limit. Reads rank records newest first and display each record's age. When a write would push the store above 500 records, it deletes the oldest episodic record, preferring an inactive record before an active one.
- **Record kinds:** Only episodic records (run decisions and issue claims) are eligible for eviction. Procedural and semantic records do not expire because of age or size. They leave the active set only when superseded by a new record. Superseded rules remain in the store as inactive records, preserving the history of what changed. There should be relatively few such rules. If the store ever holds 500 records and none of them is episodic, the write is refused and logged, and a person consolidates the rules.
- **Estimated record lifetime:** The estimate is based on the store size divided by the number of records written per run and the number of runs per day:

  - **Records per run:** At most one record per run, or two when a maintainer's rule is supplied to the run. Under the "How" rules, my 28 completed real-model runs on issue 4201 would have written 7 records: the first decision, and 6 that superseded it. That is 0.25 records per run.
  - **Runs per day:** Five. Ledgerline opens about one issue per day (issues 4201–4206 were opened between September 8 and 13). Re-runs and reopened issues add to that total. On October 28, my normal workload was 3 real runs. October 29 had 25 runs, but that was a crash-matrix testing day.
  - **Worst case:** 500 ÷ (1 × 5) = **100 days**.
  - **At the measured rate:** 500 ÷ (0.25 × 5) = **400 days**.
  - **On a test day like October 29:** 500 ÷ (1 × 25) = 20 days. Scripted and test runs should therefore use a separate store file.
  - **Issue 4207:** It was reopened 54 days after being closed (2026-08-19 to 2026-10-12). Even at the worst-case retention estimate of 100 days, its previous decision should still be available when the issue returns.

## Reading Memory (Optional)

- Before its first search, a run reads `active("ledgerline", <issue>)`. It records the read using `trace.event("store_read", issue=..., records=[<ids>])`.
- Each record is shown alongside the calls that fill the plan's steps, with the newest records first. The context includes the record's kind, source, age, `confirmed` status, and `stated_by` when present.
- The planner may also see these records, but it must never receive an `issue:<n>` record. Those records contain text that anyone can write.
- A run treats each type of record differently:
  - A confirmed `user` rule is an instruction and must be followed.
  - A procedure is a method to use, with its age taken into account.
  - An earlier run's decision is a lead, not an answer. The run must search and read the relevant file before relying on its path.
  - An `issue:<n>` record is only a report of what someone wrote and must never be acted on.
- When an issue is reopened, the run displays the reopened date next to each stored decision. Any decision older than that date is considered stale.
