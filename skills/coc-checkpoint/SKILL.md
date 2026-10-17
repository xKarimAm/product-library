---
name: coc-checkpoint
description: Write this project's .claude/session-state.md checkpoint (stage, next action, proof, blockers) for Product Library.
disable-model-invocation: true
---

# coc-checkpoint

A **checkpoint** records where this project stands so the next session, and the Product Library dashboard,
can pick up without reading the transcript. You draft it, the user accepts it, and you write it.
Capture must take about thirty seconds of the user's time: draft every field yourself and ask only
for corrections.

## Steps

1. **Read.** Open `.claude/session-state.md` in the project root if it exists. Note its frontmatter
   keys and its body (everything after the closing `---`). Done when you know which keys exist and
   where the body starts, or that the file is absent.
2. **Gather.** Collect this session's facts: what changed, the last command that verified it and its
   result, `git log -1 --format="%h %s"` and `git status --porcelain` when the folder is a repo.
   Done when every field below has a source in this session or in the existing file.
3. **Draft.** Fill every field in [Fields](#fields). Show the user the whole frontmatter block once,
   then ask "Write this?". Done when the user accepts or gives edits; apply the edits and re-show
   only if they changed a field's meaning.
4. **Write.** Replace only the frontmatter block and keep the body byte-for-byte. A file with no
   frontmatter gets the block prepended above its existing content. A missing file gets the block
   plus one `## Notes` heading. Create `.claude/` if needed.
5. **Check.** Re-read the file. Done when line 1 is exactly `---`, the next line that is exactly
   `---` (column 0) closes the block, every value sits on one line, and `blockers` is valid JSON.

## Fields

Write each value on one line, in this key order. Double-quote any value containing `:` or `#`.

| Key | Value |
|---|---|
| `status` | one word: `active`, `paused`, `blocked` or `done` |
| `stage` | one word: `discover`, `define`, `build`, `verify` or `ship` (see [Stages](#stages)) |
| `last_updated` | now, ISO-8601 with offset, e.g. `2026-10-17T16:56:00+03:00` |
| `current_task` | the piece of work in flight, under 80 characters |
| `next_action` | the first concrete step a fresh session takes, specific enough to start without asking: name the file, command or decision |
| `proof` | the observable evidence that the last step worked, quoted from this session: a command with its result (`selftest OK`, `53/53 passed`), a commit hash written as `commit <hash>` (Product Library checks it exists in the repo), a quote written as `docs/notes.md: 'exact words'` (checked word for word against that file, inside this project), a URL. With no evidence yet, write `none yet - ` plus what would prove it |
| `for` | who this is for, in a few words: a person, a team, or `me, when ...`. The catalog card: future-you should know at a glance |
| `bet` | why it matters: what you are betting this will change or save. If it rests on evidence, quote it as `file: 'exact words'` |
| `blockers` | a JSON list on one line: `["Me [M]: pick a merge order", "Sam [A]: register the app"]`. Every open entry starts with its owner as `Name [Initial]:`. Closed entries start `DONE YYYY-MM-DD:`. Use `[]` when nothing blocks |

`Me [M]:` marks a decision waiting on the user; Product Library counts these as "waiting on you".

## Stages

| Stage | The project is... | Typical proof |
|---|---|---|
| `discover` | finding out whether the problem is real | an observation: who, when, what happened |
| `define` | pinning scope, outcome and the riskiest assumption | a written spec or decision |
| `build` | making the thing | a passing test or a commit |
| `verify` | checking it works for real | a run against real data, a screenshot, a probe result |
| `ship` | in users' hands | a deploy URL, a release tag, usage |

Pick the stage the work is in *now*. A project moves back a stage when new evidence reopens it.

## Example

```
---
status: active
stage: verify
last_updated: 2026-10-17T16:56:00+03:00
current_task: drift detection and readiness gate in COC
next_action: "rebuild poc_city.html with py tools/build_poc.py, then run py tools/pocprobe.py"
proof: "py coc.py --selftest -> selftest OK; commit 39be42f"
for: "me, picking a project back up after weeks away"
bet: "a note I can trust saves re-reading a whole transcript"
blockers: ["Me [M]: decide whether to push coc-drift-gate", "DONE 2026-10-17: traffic probe fixed"]
---
```
