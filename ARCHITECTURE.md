# ARCHITECTURE.md · RepoMind on the seven layers

For each layer: what does this job, and where is it enforced. Cite code as a file
path and line number joined by a colon, inside backticks; a checker opens every
reference (`checks/FORMATS.md`, section 8). A layer held only by a sentence in a
prompt (any file under `prompts/`) is **EMPTY**, and so is a layer nothing does
yet. Status is one of: present, partial (say what is missing), or **EMPTY**. Each
assignment brings this file up to date.

What each layer is for (Lecture 1, slides 42 to 44):

- **Model**: reasoning, choosing tools, generating text.
- **Harness**: runs the loop, builds each prompt, trims old history.
- **Tools**: where the system acts on the world.
- **Memory & State**: what survives a step, a session, a restart.
- **Control & Policy**: what the system may do, and when it must ask.
- **Observability**: a step-by-step record of what it did.
- **Evaluation**: measuring quality, before and after release.

The table below describes RepoMind's architecture at the end of Assignment 4.

| Layer | What does this job | Where it is enforced | Status |
|---|---|---|---|
| Model | The configured model is Mistral's `ministral-14b-2512` (`settings.yaml:24`), accessed only through the metered client. | `harness/client.py:150` | present |
| Harness | Runs the loop with three bounds checked in code. Validates the plan before execution and allows the executor to run only the plan's steps. Builds each fill call's prompt in code, with store records in a separate block. Part F adds optional history compaction that never touches the issue, along with a note kept outside the history. | `agent/loop.py:38`, `ways/planned.py:206`, `ways/planned.py:328`, `ways/planned.py:422`, `ways/planned.py:388`, `ways/planned.py:360` | present |
| Tools | Provides five namespaced tools through one registry. Every call is checked at the boundary before execution. Every write uses a harness-generated key, which is checked before each attempt and read back after a timeout. Every attempt is included in the call record. | `tools/__init__.py:166`, `tools/__init__.py:249`, `tools/__init__.py:254`, `tools/__init__.py:271`, `tools/__init__.py:315` | present |
| Memory & State | Keeps a run's progress file outside the model's context. Uses a SQLite checkpointer that saves the five fields, never the conversation, and synchronously saves to disk before returning. Checkpoints are saved after every search and file read, and synchronously before every write. Resume loads the latest checkpoint and rebuilds the executor from it. A shared memory store keeps records with provenance, supersedes outdated records instead of simply appending, and applies eviction. Each run reads the store before its first search and writes its triage decision at the end. | `ways/notes.py:67`, `state/checkpointer.py:112`, `state/checkpointer.py:97`, `ways/planned.py:273`, `ways/planned.py:575`, `ways/planned.py:600`, `ways/planned.py:171`, `ways/planned.py:639`, `state/store.py:180`, `state/store.py:190`, `state/store.py:217`, `ways/planned.py:407`, `ways/planned.py:448` | partial: A person must start each resume. Model calls are not journaled, and the first checkpoint is saved only after the first search, so a crash before that point causes the run to be planned again. The store retrieves records only by issue, newest first, with no content-based search. It also did not help with reopened issue 4207: 0 of 5 passes with the store and 0 of 5 without it. |
| Control & Policy | Runs a hook before every call and denies the call if the hook fails. Sends writes that cannot be confirmed to a person for review. The second pass holds drafts that still fail. The store rejects records without complete provenance and issue text presented as fact. Only issue records can mention auto-merging, and issue text cannot supersede a person's rule. | `tools/__init__.py:221`, `ways/planned.py:296`, `ways/planned.py:567`, `state/store.py:113`, `state/store.py:136`, `state/store.py:201` | partial: The hook currently allows every call. |
| Observability | Records one trace line per model call and tool call, and saves the plan as data before execution. Logs a `checkpoint` line after every save, a `store_read` line with the records retrieved by a run, a `store_write` line for every write at the end of a run, and a `compaction` line with its size. | `agent/loop.py:50`, `ways/planned.py:178`, `ways/planned.py:616`, `ways/planned.py:414`, `ways/planned.py:480`, `ways/planned.py:404` | partial: Traces are available, but there are no alerts. A run that crashes leaves a trace without a `run_end` event, and nothing reports the failure. |
| Evaluation | Uses a grounded check that reads the tracker rather than relying on the agent's output. Includes scripts to measure the reopened issue with and without the store, test contradictions, and compare checkpoint sizes with and without the conversation. | `eval/check_triage.py:7`, `eval/reopened.py:59`, `eval/contradiction_test.py:66`, `eval/checkpoint_bytes.py:31` | partial: Evaluation is offline only. |

**Empty layers: 0 of 7.** Four layers are still partial: Memory & State, Control & Policy, Observability, and Evaluation.
