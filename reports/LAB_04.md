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

| Step | When | run_id | Comments | Comment IDs | Open PRs |
|---|---|---|---|---|---|

What the checkpoint did, and what the key did:

## Part D · A memory that can say where it came from

- The write policy, in brief:
- The three candidates, and how each was stored:

| Candidate | Stored? | Kind | source | origin | confirmed | Invites |
|---|---|---|---|---|---|---|
| A | | | | | | |
| B | | | | | | |
| C | | | | | | |

- Eviction: the size, the rule, and how long an entry lives at your write rate:

| Issue 4207, five runs each | With the store | Empty store |
|---|---|---|
| Passes | | |
| Mean tool calls | | |
| Mean tokens | | |

## Part E · Answer from your own runs

1. Your prediction against the matrix:
2. The contradiction test, and the record IDs the third session retrieved:
3. What your checkpoint cost, structured and with the conversation, and over how many runs:
4. Is what you built durable execution?
5. Which abstraction?

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
