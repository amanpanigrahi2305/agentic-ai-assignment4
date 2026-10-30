# Assignment 4 · Kill it and resume: state, keys and a memory with provenance

Model: Mistral `ministral-14b-2512`, through Mistral's OpenAI-compatible API (`https://api.mistral.ai/v1`), the same for every run.

## Part A · Mark the plan, place the checkpoints

| Step | Tool (role) | Kind | Checkpoint |
|---|---|---|---|
| 1 | `issues_read` (read_issue) | read | none: no model call fills it, so a replay only reads the issue again |
| 2 | `code_search` (search_repo) | read | after: a model call fills its query, and the revision check may follow it |
| 3 | `code_read_file` (read_file) | read | after: a model call fills its path, and the comment's draft is written next |
| 4 | `pulls_open` (open_pr) | keyed write | before, sync: the PR's filled arguments are saved first, so a replay sends the same arguments and the same key |
| 5 | `issues_comment` (post_comment) | keyed write | before, sync: the checked draft is saved first |

The checkpoint after a read is saved after the revision check, so it holds the plan the run is on. The checkpoint before a write is saved after the write's arguments are fixed, so the replay window holds one write at most: the running one. When the draft says `file: none`, the PR step is skipped, nothing is written, and step 4 gets no checkpoint.

- **Durability mode, and why:** `sync`, for every save in the run. The run makes two writes that a person reads, so a checkpoint that is lost loses the arguments a replay needs. `async` can lose a save in the gap before it lands. `exit` loses every save in a crash. A sync save is one SQLite commit with `synchronous=FULL`: a few milliseconds, 3 to 5 times in a run, next to model calls that take seconds.
- **The weaker of the two writes, and why:** the comment. Both writes carry a key derived from the run, the plan step and the arguments. If the key were lost or changed (new arguments, or `KEY_MODE=uuid`), the PR would still be stopped: Assignment 3's check before every attempt also looks for an open PR by its branch, `repomind/issue-<n>`, which code fixes. The comment's check looks only by key, so nothing else would stop a second comment. Also, a PR can be closed, but a comment that someone has read cannot be taken back.

## Part B · Kill it at every step

**The hand walk, written before the matrix.** The crash you expect to be worst: `--die-during-step 5`.

**Scope and kill-step numbering.** I am considering the crash that poses the greatest risk of creating a duplicate, rather than the one that repeats the most work. The kill flags count steps in the order they first call a tool, not by the plan's step numbers. When the run opens a pull request, the comment is kill-step 5, so the flag is `--die-during-step 5`. When the draft says `file: none`, the PR step calls no tool, making the comment kill-step 4, so the same crash requires `--die-during-step 4`. The explanation below assumes the run opens a PR. This prediction is for derived keys, which are the default.

**Why this is the worst case.** The tracker commits the comment, but the process dies before receiving the response. The comment exists in the tracker, but the run has no record of the successful write: there is no `tool_call` line, no call-record entry, and no entry in `completed_calls`. When the run resumes, it executes the comment step again.

This is the most dangerous case for duplicate creation because the run cannot tell from its own records whether the comment was posted. The registry's idempotency-key check is what prevents a second comment. For pull requests, the registry also checks by branch, but comments do not have that additional check.

**Last checkpoint before the crash.** The last checkpoint is saved synchronously just before the comment is posted. At that point, `current_step` is 5, and `step_status` shows steps 1–4 as done and step 5 as running. Step 4 is skipped if the draft says `file: none`.

The `completed_calls` field contains the calls for steps 1–3 (step 2 can have more than one call if the plan was revised), and step 4's call with its key if a PR was opened. The `findings` field contains the checked draft and, when a PR is required, its arguments. There is no call record for step 5 because the process dies before the comment call's result can be saved.

**Steps between the checkpoint and the crash.** None. The checkpoint is saved immediately before the comment write. Steps 1–4 are already complete in the saved checkpoint, so the resumed run reuses their saved results rather than calling them again.

**Step running at the crash.** Step 5, `issues_comment`, is performing a keyed write. The tracker has committed the comment, but the process never receives the response and cannot record the result.

**Side effects and what closes each step.**

- **Step 4 — Open the pull request.** This step creates one PR from `repomind/issue-4201`, or no PR if the step is skipped because the draft says `file: none`. **Closed by: a recorded result.** When a PR is opened, its call and key are saved in `completed_calls`. The resumed run uses that record and does not open the PR again.

- **Step 5 — Post the comment.** This step creates one comment on issue 4201. **Closed by: the key.** When the run resumes, it saves another synchronous checkpoint and posts the draft saved in that checkpoint, rather than generating a new draft. The same `run_id`, plan step, and arguments produce the same idempotency key. Before attempting the write, the registry checks whether a comment with that key already exists. Since the tracker committed the original comment, the check finds it and returns the existing result without writing another comment.

  If a repeated write did reach the tracker, the key's unique constraint would mark it `replayed` and write nothing (`harness/tracker.py:19-20`). In this case, however, the registry's check stops the write before it reaches the tracker. Both protections depend on the same key.

**Expected tracker state after resume.** I expect the tracker to contain exactly one comment on issue 4201, with the body from the saved draft, and exactly one open PR from `repomind/issue-4201`. If the draft instead says `file: none`, there should be no PR. No second write should be created. Because the resumed run stops at the registry's key check, the tracker's attempts log should contain one comment row and, if a PR was opened, one PR row.

**Why the other crash points are less dangerous.** A kill at steps 1–3, after or during, only repeats reads, so it wastes time but does not risk duplicate writes. A kill at the PR write, after or during, leaves an uncertain write outcome too, but the registry can also check for an existing PR by branch. A `--die-after-step 5` crash has the same risk, because the comment is written and the resume runs step 5 again, but the trace and call record still show the comment call. With `--die-during-step 5`, the process dies before recording the call's result, leaving the tracker as the only place that confirms the comment exists.

**The matrix, derived keys.** Uncrashed run: `planned-4201-s01-4ee548`, the first run of 4201 after `make reset`. Its draft said `file: none`, so the PR step called no tool, and the run gave numbers to four steps (plan steps 1, 2, 3 and 5). So the matrix is kill-steps 1 to 4, after and during.

| Step | When | run_id | Comments | Open PRs | Matches its findings |
|---|---|---|---|---|---|
| 1 | after | `planned-4201-s01-81a449` | 1 | 0 | yes |
| 1 | during | `planned-4201-s01-c68058` | 1 | 0 | yes |
| 2 | after | `planned-4201-s01-5ba405` | 1 | 0 | yes |
| 2 | during | `planned-4201-s01-b6937c` | 1 | 0 | yes |
| 3 | after | `planned-4201-s01-52dfc6` | 1 | 0 | yes |
| 3 | during | `planned-4201-s01-d956cc` | 1 | 0 | yes |
| 4 | after | `planned-4201-s01-0909fe` | 1 | 0 | yes |
| 4 | during | `planned-4201-s01-913780` | 1 | 0 | yes |

In every case, the last checkpoint's findings say `file: none`, so no case opened a PR, and 0 open PRs is the correct count.

What each kill hit (the `killed` field in `runs/_ledger.jsonl`): kill-steps 1 to 3 hit the three reads, `issues_read`, `code_search` and `code_read_file`. Kill-step 4 hit the comment. After step 4, the comment returned and the process died before the code saw the result. During step 4, the tracker committed the comment and the process died before the reply. In both, the resume saved the step's sync checkpoint again, called `issues_comment` with the same key, and got `already there`. The tracker's attempts log for each run has one row: `comment`, `written`.

Runs that are not in the table:

- The first step-4 runs, `planned-4201-s01-5e532c` (after) and `planned-4201-s01-e708b8` (during). In both, a plan revision added a second search (and, in `5e532c`, a second file read) before the writes, so kill-step 4 was a read, not a write. Each left one comment that matches its findings. I ran step 4 again so that the kill lands on a write. The table shows the second runs, which are the latest for each case.
- Step 5, which the uncrashed run does not have, for the hand walk. In `planned-4201-s01-264483` (during step 5), a revision added a second search, so kill-step 5 was the comment. It left one comment, and the resume got `already there`. `--die-after-step 5` never fired in four tries (`planned-4201-s01-604e70`, `-746c50`, `-c4710a`, `-1a4aaa`): each of those runs gave numbers to four steps and finished uncrashed.

## Part C · Break it on purpose

The same cases as Part B, kill-steps 1 to 4, after and during, with `KEY_MODE=uuid`, after `make reset`.

| Step | When | run_id | Comments | Comment IDs | Open PRs |
|---|---|---|---|---|---|
| 1 | after | `planned-4201-s01-7c3ac6` | 1 | 1 | 0 |
| 1 | during | `planned-4201-s01-ffbb6e` | 1 | 2 | 0 |
| 2 | after | `planned-4201-s01-bc408a` | 1 | 3 | 0 |
| 2 | during | `planned-4201-s01-4cdc3a` | 1 | 4 | 0 |
| 3 | after | `planned-4201-s01-cd5c08` | 1 | 5 | 0 |
| 3 | during | `planned-4201-s01-664b52` | 1 | 6 | 0 |
| 4 | after | `planned-4201-s01-9acde2` | 2 | 7, 8 | 0 |
| 4 | during | `planned-4201-s01-e0eecc` | 2 | 10, 11 | 0 |

Kill-steps 1 to 3 hit the three reads. Kill-step 4 hit the comment in both cases: after step 4, the comment returned and the process died before the code saw it; during step 4, the tracker committed the comment and the process died before the reply. In both runs the two comments have the same body, `label: bug` / `file: none`, and the tracker's attempts log has two `comment`, `written` rows with two different keys.

A run that is not in the table: the first try at during step 4, `planned-4201-s01-75fa87`. A plan revision added a step before the writes, so kill-step 4 was a file read. It left one comment (ID 9) and one open PR, its findings' file `src/notifications/templates.ts`. I ran the case again so that the kill lands on a write; `e0eecc` is the latest run for the case.

What the checkpoint did, and what the key did:

The checkpoint behaved the same way as it did in Part B. On resume, the system skipped the steps already marked as done and reused the draft saved in the checkpoint. As a result, both comments in each pair have the same body because the replay used the same arguments.

However, the checkpoint alone cannot prevent a duplicate write. It only records that the comment step was running; it cannot tell whether the tracker actually committed the comment before the process crashed. That is the job of the idempotency key. With `KEY_MODE=uuid`, though, a new key was generated for every attempt. In `9acde2`, the original comment used key `aadca262…`, while the replay used `85f02c98…`. Since the registry checks for an existing comment using its key only, it found no match. The tracker's unique constraint also found no duplicate key, so both attempts were recorded as `written`.

The PR would still have been protected by the branch check, but no kill in this matrix hit the PR write. The difference is that the checkpoint determines which steps run again, while the idempotency key determines whether replaying a step creates another write.

## Part D · A memory that can say where it came from

- The write policy, in brief: `state/write_policy.md`. A run writes to the store only at its end, after it posts its comment; nothing is written mid-run, and a run that escalates writes nothing. RepoMind keeps what was expensive to derive (a procedure, a run's triage decision), what a person with standing stated, and what it checked against the repository's files. Issue text is kept only as an unconfirmed, episodic record of what the issue claimed. Every record carries its source, `written_at` (when the information was first seen), its origin and `confirmed`. A contradicted fact or a changed rule supersedes the old record, which stays in the store, inactive. Each issue has one active triage decision: the same decision writes nothing, and a decision with no file read never replaces one that read its file. `state/store.py` enforces the hard rules in code: it refuses a record without full provenance, a mention of auto-merging outside an `issue:<n>` record, and issue text stored as semantic or confirmed.
- The three candidates, and how each was stored: by `eval/store_candidates.py`, into `state/store.db`, as records 1, 2 and 3. Each `written_at` is the candidate's `when`. A and C are repository-wide (`issue: null`), so every run reads them; B is about issue 4188, and a run sees it only on 4188, never in the planner's context.

| Candidate | Stored? | Kind | source | origin | confirmed | Invites |
|---|---|---|---|---|---|---|
| A | yes, word for word (record 1) | procedural | `memory` | `derived` | `true`: `package.json`'s scripts and the README agreed with it when it was stored | staleness |
| B | yes, as what the issue claimed, never as a fact (record 2) | episodic | `issue:4188` | `ingested` | `false` | poisoning |
| C | yes, word for word, with `stated_by: priya-s (maintainer)` (record 3) | semantic | `user` | `ingested` | `true`: a maintainer stated it | contradiction when it changes |

- Eviction: the size, the rule, and how long an entry lives at your write rate: 500 records a repository, inactive ones counted. At the limit, a write deletes the oldest episodic record, an inactive one first; semantic and procedural records are never evicted, only superseded, so a changed rule keeps its history. The write rate: under the policy's decision rule, my 28 completed runs of 4201 would have written 7 decisions (0.25 a run), and the six runs of 4207 with the real store wrote 1 (the seed run's; the five after it reached the same decision). At an assumed 5 runs a day, an entry lives 500 ÷ (0.25 × 5) = 400 days; in the worst case, one record every run, 100 days.

| Issue 4207, five runs each | With the store | Empty store |
|---|---|---|
| Passes | 0 of 5 | 0 of 5 |
| Mean tool calls | 5.8 | 6.0 |
| Mean tokens | 12,648 | 12,054 |

The store did not help on 4207: a measured null result. The seed run, `planned-4207-s01-191224`, wrote decision record 4, `file: none`. With the store, each run's `store_read` returned records 4, 1 and 3 before its first search; with an empty store, each returned none. All ten runs named `file: none`, so no run named a file it read, and none took one from memory: the only decision in memory said there was no file. Each run with the store reached the same decision, so the decision rule wrote nothing more (`same`). The cause is in the search, not in the store. `code_search` matches a literal substring of one line (`tools/search_repo.py:111`), and Mistral searched for phrases such as `weekly scheduled export`, which no line holds: all 33 searches in the eleven runs of 4207 returned no results. Each run then guessed a path that does not exist, `src/scheduler.ts` in nine of them. The store cost about 594 tokens a run (+4.9%): the memory block in each fill call. The tool calls differ only by revisions: five in the plan, one fewer when the PR is skipped, and one more for each search a revision adds.

## Part E · Answer from your own runs

1. Your prediction against the matrix:

The uncrashed run (`planned-4201-s01-4ee548`) drafted `file: none`, so the comment was kill-step 4. The worst case I named therefore ran as `--die-during-step 4` (`913780`). My walk predicted this shift. Most of the walk held for that case. Four parts were wrong or never tested.

What held:
- The last checkpoint was the sync one before the comment. The resume restored `current_step` 5 (`913780`, `0909fe`).
- No step ran between that checkpoint and the crash. After the resume, only the comment ran, with 0 model calls and 0 tokens.
- The key closed the comment. The resume saved the comment's checkpoint again, and `issues_comment` returned `already there`. The attempts log has one row: `comment`, `written`. `264483` (kill-step 5, after a revision) shows the same: comment 16, key `3bea836b…`.
- The tracker held one comment and no PR in all 8 cases. That is the `file: none` half of my prediction.
- Part C shows the other side. With random keys, both kills at the comment left two comments (`9acde2`: 7 and 8; `e0eecc`: 10 and 11).

Where it was wrong, or never tested:
- The PR was never tested. Each graded run drafted `file: none`, so no graded run opened a PR. My claims that a recorded result closes the PR, that the branch check stops a second PR, and that one PR remains have no evidence. In Part C, `75fa87` opened a PR, but its kill hit a file read before both writes.
- Kills at steps 1 to 3 repeat more than reads. At kill-steps 1 and 2, no checkpoint existed yet: the first one is saved after the first search, once the code sees the result. So each resume started the whole run again, under the same run_id, with a new plan from the planner, every read and every fill. The resumed halves made 5 to 7 model calls and used 8,130 to 12,913 tokens. At kill-step 3, the resume started at the checkpoint after step 2. It ran the step-3 fill (a model call) again, and also the read after an "after" kill. My walk was right that none of these cases risked a duplicate: each left one comment.
- A kill-step number does not always mean the same plan step. My walk allowed for the `file: none` shift, but not for revisions. In `5e532c` (after) and `e708b8` (during), a revision added a search, so kill-step 4 hit a read. I ran step 4 again (`0909fe`, `913780`). In `264483`, a revision made kill-step 5 the comment.
- `--die-after-step 5` never fired. In four tries (`604e70`, `746c50`, `c4710a`, `1a4aaa`), each run gave numbers to only four steps and finished uncrashed. The same crash after the comment did run, as `--die-after-step 4` (`0909fe`). The key closed it, and one comment was left.

2. The contradiction test, and the record IDs the third session retrieved:

Three sessions, each a separate process, on the real store (`state/store.db`):
- Session 1, `python -m eval.store_candidates` (Part D), stored candidate C as record 3: semantic, `source: user`, `stated_by: priya-s (maintainer)`, `confirmed: true`.
- Session 2, `python -m eval.contradiction_test contradict`, stored a made-up rule from the same maintainer, in the same way, as record 5: "For duplicates: label them `duplicate`, link the original, and close them after 14 days if the reporter has not replied." It superseded record 3: record 5 has `supersedes: 3`, and record 3 is now inactive. Record 3 stays in the store.
- Session 3, `python -m eval.contradiction_test retrieve --write`, opened the store again. It retrieved the active rule on duplicates through the store's `active()` call, the one a run's read uses, and kept the records from a `user` about duplicates. It retrieved **[5]**.

One process can pass from what it holds in memory. Three processes show that the supersession is on disk, and that a later session reads only the new rule. An append-only store would have returned [3, 5]: two active rules that contradict each other ("never close them" and "close them after 14 days"). The checker's supersession row gives 6 of 6.

3. What your checkpoint cost, structured and with the conversation, and over how many runs:

The mean of 5 normal real-model runs of 4201 (`3b5418`, `471015`, `479c40`, `e1dbe0`, `1a0d02`), for all of one run's checkpoints together:
- structured: **21,277 bytes**;
- with the conversation: **142,842 bytes**;
- so the conversation makes the checkpoints 6.7 times larger (6.1 to 7.4 times, run by run).

Method: each run saved its checkpoints through my checkpointer, as every run does. `ways/planned.py` also saved a second copy of each checkpoint to a separate file (`state/checkpoints_with_conversation.db`): the same five fields, plus every message the way had sent the model so far. The size is SQLite's summed `LENGTH` of the saved data (`python -m eval.checkpoint_bytes`). All five runs drafted `file: none`, so none saved a PR checkpoint.

Where the bytes come from: `3b5418` saved 5 checkpoints and 19,459 bytes. Of these, 8,906 bytes are the plan, because each checkpoint holds the whole plan. `completed_calls` is 9,067 bytes, and 5,719 of them are tool results: the issue text, the search results and the file contents. Each checkpoint holds every call so far, so the size grows with each search that a revision adds. The run with one revision saved 3 checkpoints and 9,210 bytes. The runs with two revisions saved 5 or 6 checkpoints and 19,459 to 32,054 bytes. The conversation itself is 121,737 of the 141,286 bytes in `3b5418`'s copies, because each copy holds every message so far, and each fill message holds the earlier steps' results again.

A resume needs none of the conversation. `restore()` reads only the five fields, and every derived-key case resumed correctly without it (crash matrix, derived keys: 20 of 20). This agrees with slide 14: a checkpoint holds enough to rebuild, not so much that it gets costly.

4. Is what you built durable execution?

No. It is a recovery aid. Slide 40's three questions give two noes and a partial yes.
- Does it notice that the run died? No. No process watches the runs. When the harness's kill switch (`--die-after-step`, `--die-during-step`) stops a run, the runner prints "killed <run_id>" and adds `killed` to the ledger, but that comes from the kill switch itself. A real crash leaves only a trace with no `run_end` line, and nobody knows until someone looks.
- Does it restart the run without a person? No. Each resume in the matrices was `python run.py --resume <run_id>`, from the matrix script, which a person started.
- Does it stop finished work being done twice? Partly.
  - Tool calls: yes, back to the last checkpoint. `completed_calls` acts as a journal up to each checkpoint. No finished call before the last checkpoint ran again (resume, not restart: 8 of 8). A call after the last checkpoint runs again, such as the file read after kill-step 3.
  - Model calls: only what the checkpoint keeps. The checkpoint holds the plan, the checked draft and the PR's arguments, so a resume after the first checkpoint does not call the planner again, and a resume at the comment made no model call. No journal holds the other model calls. A kill at step 1 or 2, before the first checkpoint, repeated the whole run (5 to 7 model calls). A kill at step 3 repeated the step-3 fill.
  - The call in flight: the key closes it, as slide 37 says. With derived keys, all 8 cases left one comment. With random keys, both kills at the comment left two.

My answers match slide 42's row for LangGraph alone: no, no, and finished steps not run again. Slide 42's cells are the vendors' claims. Mine come from my own runs.

What I would add:
- A supervisor: a small service that finds runs with a `run_start`, no `run_end`, and no live process (from a heartbeat file, for example). It runs `run.py --resume <run_id>` itself, with a retry limit, and then gives the run to a person.
- A true journal: record every finished call, tool or model, with its result, as it returns, and replay from it on a resume. The call record (`runs/<run_id>.calls.jsonl`) already logs tool calls, but `restore()` does not read it, and no record holds the model calls. The journal's cost (slide 37) is code that makes the same calls in the same order. My executor does that once the plan and each model reply come from the journal.
- First, a cheaper step: a sync checkpoint right after the plan is validated. Then a kill at step 1 or 2 keeps the plan, and does not call the planner again.

5. Which abstraction?

The four questions, in order:
- Do I know the steps and their order in advance? Yes, for each run, before any step runs. The planner writes the plan at the start. The validator checks it, and the schema check fixes its end: the PR, then the comment, last. The executor runs the steps in order, and runs nothing off the plan. A revision can add or change a search, but it goes through the same checks. This adds a graph: built from a validated plan for each run, not fixed in code.
- Do runs outlive a single process? Yes. A killed run resumes in a new process under the same run_id (Part B), and later runs read the store again (Part D). This adds checkpoints on disk: sync, in SQLite, with a shared store next to them.
- Do steps have irreversible side effects? Yes: the PR and the comment. This adds a key on every write. The key comes from the run, the plan step and the arguments, and the registry checks before each attempt (a PR by branch, a comment by key). Today a half-done run does not have to finish on its own, because a person resumes it. When RepoMind triages each new issue unattended, it must, and this answer then adds durable execution (item 4).
- Do I want to own the context myself? Yes. My code builds each fill call's message: the step, the plan's notes, the memory block (each record's kind, source and age) and the earlier results. It keeps the store's records, and so every `issue:<n>` record, out of the planner. Part F depends on this control. This adds my own harness.

The design: a graph from a validated plan, run by my own harness, with sync checkpoints on disk and a key on every write. That is RepoMind now. Durable execution comes next, when runs must finish without a person.

One thing that slide 44 says no framework decides: what to checkpoint, and where. I decided it from the plan, not the clock (Part A): after each search and file read, and sync before each write, with the five fields and never the conversation. My runs tested it. The sync checkpoint before the comment closed the worst crash (item 1). Leaving out the conversation kept a run's checkpoints at 21,277 bytes, not 142,842 (item 3). The runs also show a gap: there is no checkpoint after the plan, so a kill at step 1 or 2 calls the planner again.

## Part F · Find the boundary that lost it

The fact, word for word, and what the comment states when a run uses it:

| Case | The lost run | Where it lost the fact (trace and request record) | The fix | The fixed run |
|---|---|---|---|---|
| Attention | | | | |
| Compaction | | | | |
| The session | | | | |

The session case's stated run:

## AI assistance

Which tool, what it wrote, and what you checked.
