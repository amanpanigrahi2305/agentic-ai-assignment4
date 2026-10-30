# CHANGES.md

Three lines per assignment: what it added, what it removed, what it constrained.
Removals are logged like additions.

## Assignment 1
- **Added:** a bounded tool loop; four ways to triage an issue (a direct call, a workflow, an agent, and a hybrid of the two); a grounded success check that reads the tracker; a results script
- **Removed:** nothing
- **Constrained:** every agent run to three bounds checked in code (steps, tokens, wall clock); success to what the tracker holds for the run's ID

## Assignment 2
- **Added:** a plan written as data before the issue is read; a validator with four checks; an executor that runs only the plan's steps; one checkpoint that may revise the plan; a second pass before the comment; detectors and a diff over traces; a progress file and a compaction
- **Removed:** the model's choice of the next tool, in the planned way
- **Constrained:** every tool call to a step of a validated plan; revisions to steps not yet done; the comment to drafts that pass the second pass

## Assignment 3
- **Added:** five rewritten tool definitions with examples, among them open_pr; a boundary check before every call; errors that name the fix; harness-derived idempotency keys, a check before every write attempt and a read-back after a timeout; the call record; a fail-closed hook
- **Removed:** free-text tool descriptions and free-form filters; protocol detail in anything the model sees
- **Constrained:** every write to be safe to retry, and to a person when its outcome cannot be read back; the comment to the last write, after the PR

## Assignment 4
- **Added:** a SQLite checkpointer with three durability modes (`sync`, `async` and `exit`), which saves the five required fields but never the conversation, and which RepoMind uses in `sync`; checkpointing at the planned points: after every search and file read, and before every write; resume support that loads a run's latest checkpoint, rebuilds the executor from the saved state, skips calls that have already finished, and replays unfinished writes using their saved arguments; a memory write policy covering when and what to store, how records are updated, provenance requirements and eviction, including rules for all three candidates; a shared memory store with provenance on every record, supersession instead of simple appends, a 500-record limit, validation enforced in code, one active triage decision per issue, and an option to use an empty store through `REPOMIND_STORE`; a store read before the first search, whose records are included in every fill call with their kind, source and age but are never passed to the planner, and a store write at the end of each run of its triage decision and any rule it was given; a paragraph in the executor's prompt explaining how to treat each kind of memory; scripts for storing the three candidates and for measuring the reopened issue, the contradiction case and checkpoint size; a switch that saves each checkpoint again with the conversation in a separate file (Part E); Part F switches for telling a run a fact, placing it in one of four locations, padding the context, and compacting the fill calls' history into a list of tools and paths; Mistral's `ministral-14b-2512` model and its pricing line
- **Removed:** state that existed only in the process, including the executor's results, plan version, draft and PR arguments, which a crash previously lost, leaving nothing to resume from; the behavior of rebuilding a resumed write through a fresh model call; the starter's rule that treated an argument as open (still to be filled) only if it started with `$fill`, under which the first real run posted the planner's template as `label: triage` and `file: $fill`
- **Constrained:** every write to a synchronous checkpoint for its own plan step, saved before the write begins; a resumed write to the arguments saved in its checkpoint, keeping its idempotency key unchanged; an argument to count as filled only when no `$fill` remains anywhere in it; every store record to complete provenance (one of the four allowed source forms, an ISO 8601 timestamp, an origin and a `confirmed` value), or the store rejects it; issue text to `issue:<n>` records, which are never semantic or confirmed, never supersede a person's rule, never reach the planner, and are the only records allowed to mention auto-merging; each issue to one active triage decision, and a decision made without reading its file never replaces one whose file was read; each repository's store to 500 records, evicting the oldest episodic records first and never rules or procedures; store writes to the end of a run that successfully posted its comment
