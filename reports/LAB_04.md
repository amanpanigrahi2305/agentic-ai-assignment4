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

**The hand walk, written before the matrix.** The crash you expect to be worst:

- Its last checkpoint:
- The steps between it and the crash, and the step running at the crash:
- For each: its side effect, and what closes it (a key, a recorded result, or nothing):

**The matrix, derived keys.** Uncrashed run:

| Step | When | run_id | Comments | Open PRs | Matches its findings |
|---|---|---|---|---|---|

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
