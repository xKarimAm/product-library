# Product Library (formerly COC, Center of Claude): agent map

The UI and docs say **Product Library**. Code keeps the old name on purpose: `coc.py`, `COC_*` env vars,
the `X-COC-Token` header and the `coc-checkpoint` skill. Don't rename those.

Local, read-only mission control over every folder Claude Code has run in. Two files do everything:

- `coc.py` is the backend: an HTTP server, scanner and parsers. Python stdlib only, so nothing to install.
- `index.html` is the frontend: one file with inline CSS and JS, served by `coc.py`. No build step.

```
py coc.py              # serve http://127.0.0.1:7777  (port: env COC_PORT)
py coc.py --selftest   # assert-based tests, no server, no network. MUST stay green.
```

Find code by **symbol name** (`grep -n "def gate" coc.py`), not by line number. Lines move.

## Data sources (what the scanner reads, never writes)

| Source | Location | Read by | Gives |
|---|---|---|---|
| Claude registry | `~/.claude/projects/<slug>/*.jsonl` | `transcripts`, `resolve_cwd`, `last_prompts` | real project path (`cwd` field, NEVER from the slug), git branch, last prompts, session count, newest activity time |
| Per-project memory | `~/.claude/projects/<slug>/memory/MEMORY.md` | `_build` | `memory` |
| Session state | `<project>/.claude/session-state.md` | `read_state` reads frontmatter via `parse_frontmatter`, or falls back to `parse_plain_state` | `status`, `stage`, `last_updated`, `current_task`, `next_action`, `proof`, `for`, `bet`, `blockers` (keys in `FM_SCALARS`; `for`/`bet` are the catalog card) |
| Append-only logs | `<project>/HANDOFF.md`, `PROJECT.md` | `read_logs` reads the TAIL (newest at the bottom) | last heading plus the last 60 lines |
| Git | `<project>/.git` | `git_info` runs a subprocess with list args | `branch`, `subject`, `committed` (ISO), `dirty` count |
| Plans | `~/.claude/plans/*.md` | `plans` | title, size, mtime |
| Extra folders | `EXTRA_ROOTS` constant, replaced per machine by env `COC_EXTRA_ROOTS` (`;`-separated) | `scan` | projects with no registry entry yet; missing folders are skipped |

**Who writes session-state.md:** the user-invoked skill `skills/coc-checkpoint/SKILL.md` (installed as a copy in
`~/.claude/skills/coc-checkpoint/`; re-copy after editing). Its `## Example` block is the format contract:
`selftest_checkpoint()` parses it verbatim, so changing the format means changing both together.

Frontmatter conventions: a blocker starting `Me [M]:` counts as waiting on the user
(`waiting_on_me`). Entries starting `DONE` are closed (`open_blockers`). The owner prefix
pattern `Name [X]:` is `OWNER_RE`.

## Backend: `coc.py` sections, in file order

| Section banner | Key symbols | Job |
|---|---|---|
| file reading | `_stat_key`, `read_text`, `tail_text` | per-file cache key `(path, mtime_ns, size)`; UTF-8 with BOM tolerated; tail reads |
| transcript scanning | `resolve_cwd`, `resolve_project`, `_prompts_in`, `last_prompts`, `is_substantive`, `STOPLIST`, `_story_in`, `project_story` | last real prompt; "continue"/"ok" are filler. The story: `origin` (first substantive prompt of the oldest session), `chapters` (Claude's `ai-title` per session, a user `custom-title` wins, the last record is current) and `prs` (`pr-link` records, https only, de-duplicated) |
| project folder | `parse_frontmatter`, `parse_plain_state`, `open_blockers`, `waiting_on_me` | session-state parsing (handles 3 real YAML shapes, no YAML library) |
| drift and the readiness gate | `drift`, `DRIFT_GRACE`, `_epoch`, `OWNER_RE`, `_has_proof`, `gate` | **Ported from Harness.** Drift: work newer than the state file by more than 1h. Gate: hard checks `has_state`, `next_action`, `fresh`; soft checks `blockers_owned`, `proof` (a `none yet` placeholder is not proof), `proof_commit` (every `commit <hash>` the proof cites exists in the repo; set by `unknown_commits` in `_build`), `proof_quote` (every `file: 'words'` in proof/for/bet is word for word in that file inside the project; `unverified_quotes`), `card` (both `for` and `bet` filled in). `truth`, `TRUTH_FIELDS`: the truth boundary, `checked` (every claim the scan verified, true or false: fresh, each cited commit with a repo to ask, each quote) vs `written` (filled-in fields citing nothing checked, plus open blockers) |
| (state and logs) | `read_state`, `_last_heading`, `read_logs`, `list_files`, `git_info`, `unknown_commits` (`git cat-file -e <hash>^{commit}`; no repo means nothing is unknown) | per-project enrichment |
| scanning | `_build` (one record per project), `scan` (2s TTL cache; registry builds run on an 8-thread pool because each waits on git), `_dedupe`, `LIGHT`, `light`, `plans` | builds the records the API returns |
| server | `TOKEN`, `ALLOWED_HOSTS`, `_find_vscode`, `Handler.do_GET`, `Handler.do_POST`, `serve` | HTTP layer |
| selftest | `selftest`, `selftest_regressions`, `selftest_gate`, `selftest_checkpoint`, `selftest_truth`, `selftest_story` | every case is a real trap that once failed |

## API (served by `Handler`)

Every `/api/*` call needs the header `X-COC-Token`. The token is injected into the page as
`{{TOKEN}}`. The Host header must be `127.0.0.1:7777` or `localhost:7777`.

| Method + path | Returns |
|---|---|
| `GET /api/projects` | list of `light(rec)` objects, newest first |
| `GET /api/project/<id>` | full `_build` record |
| `GET /api/blocked` | `{id, name, waiting, blockers}` for projects with blockers |
| `GET /api/plans` | `plans()` |
| `POST /api/open` body `{id, token}` | opens VS Code on that project. The id is looked up in the scan; a path is never accepted |
| `GET /`, `/blocked`, `/plans`, `/report`, `/p/<id>` | the `index.html` shell, with a CSP nonce and the token injected (`CLIENT_ROUTES`) |

### Fields: `light()` payload (what the city and the bubble use)

`id name path path_exists unresolved missing source sessions bytes last_activity prompts
prompt_trivial note session_id` + `status` (short badge, at most 24 chars, or null) `status_note` (long
status) `stage` (short badge or null) `proof for bet last_updated next_action has_state waiting_count blocker_count branch dirty resume`
+ **`drift`** (bool) **`gate`** (`"pass"|"fail"|null`) **`gate_next`** (the question to answer first) **`gap_count`**
+ `origin_prompt origin_at chapter_count latest_chapter pr_count` (the story, as counts)
+ **`truth`** (`{checked: [{what, ok}], written: [label]}` or null without a state file; same in the full record).

### Fields: full record (`_build`), returned by `/api/project/<id>`

Everything in `light()`, except that `drift` and `gate` are objects:
`drift = {by: "transcript"|"commit", state_at, activity_at, behind_hours} | null`,
`gate = {verdict, gaps: [{id, hard, question}], next} | null` (null when the folder is gone or unresolved).
Plus: `state {status,last_updated,current_task,next_action,raw,format}`, `state_file`, `blockers[]`,
`waiting[]`, `origin {prompt,at}|null`, `chapters[{title,at,session_id}]`, `prs[{number,repo,url,at}]`, `proof_unknown[]` (cited hashes git does not have), `proof_unquoted[]` (files whose quoted words are not in them), `logs[{name,size,heading,tail}]`, `files[{name,size,mtime}]`, `memory`,
`git {branch,subject,committed,dirty}`.

## Frontend: `index.html` sections (search the banner text)

CSS banners (`/* ---- name */`): header, the isometric hive, the hive, HTML overlays, the bots,
Phase 3 cursor proximity, the bubble, full sheet, toast/empty state, load-in.

JS banners, with what lives in each:

| Banner | Key functions | Job |
|---|---|---|
| helpers | `api` (fetch plus token), `esc` (ALWAYS escape before innerHTML), `ago`, `tier`, `el`, `toast` | |
| projection / layout | `iso`, `combDims`, `place`, `fit` | isometric hex-comb placement, scale from `#hive` width |
| draw | `roofOf` (state colour: clay waiting, red blocked, violet state, blue git, green transcripts, grey nothing), `drawHouse` (growth ladder: `drawLot` when `isLot`, `drawTent` when `isTent`, else a skyscraper whose height scales with work; class `stale` when `p.drift`; crane when active with state; searchlight `beam` on the tallest), `drawPlaque`, `sourcesOf` (the coloured blocks on a cell), `drawGraph` | SVG scene |
| the sprite / the traffic / Phase 3 | `botBody`, `villager`, `tick`, `dispatch`, `onMove`, `updateProx` | villagers, traffic, cursor reactions (decoration driven by state) |
| render | `layout`, `chipFor` (label chip; shows the `STALE` pill when `p.drift`) | |
| bubble | `openBubble`, `closeBubble`, `placeBubble` | click popover: stage + STALE badges in the header, NEXT (labelled "written before the latest work" when `p.drift`), last prompt, PROOF, GATE block (`gate`, `gap_count`, `gate_next`), sources, waiting-on-you |
| actions | `launch` (POST /api/open), `copy` | |
| sheets | `projectSheet` (full view `/p/<id>`: stale detail, full gate gap list, stage, proof), `blockedSheet`, `plansSheet`, `reportSheet` (`/report`: every project by gate verdict plus its truth boundary, checked vs only written down, built from `PROJECTS`, no extra API) | |
| city: day/night, avenues and traffic, RCI meter, roster panel | `applySky` (palette from the real clock; `?hour=` forces it), `drawRoads`, `spawnVehicles`, `buildMeter`, `buildRoster` (project rail plus the swatch legend) | the SimCity layer. CSS banners `city: ...` hold its styles, including `city: shine` (window flicker, stars, searchlights, blimp; all off under reduced motion) |
| routing / filter / data / bindings | `go`, `render`, `applyFilter`, `load` | client routes, search box (`#search`), data fetch |

CSP note: inline `style="..."` attributes are blocked. Set dynamic styles via `el.style.setProperty`.
## Other files

- `poc_city.html` is GENERATED by `tools/build_poc.py`: `index.html` with a data JSON baked in, so it opens from
  file://. Rebuild it after changing `index.html`. Don't hand-edit it.
- `tools/` holds test harnesses and probes; see `tools/CLAUDE.md`.
- `demo/make_demo.py` builds the live demo: copies `demo/products/*` (six tiny real apps) into
  `../coc-demo`, adds git history, a checkpoint state file and transcripts in a demo-only registry,
  then self-checks each product's expected gate/drift/stage through `coc.scan()`. `--serve` runs COC
  in-process with `COC_REGISTRY` (registry override), `COC_PLANS_DIR` (demo plans, never the real ones),
  `COC_EXTRA_ROOTS=""` (no extra folders) and
  `COC_DRIFT_GRACE=10`. Live actions on the built demo: `--commit <product>` (goes STALE in ~10s),
  `--checkpoint <product>` (passes again); `--rehearse` asserts that loop and resets. Change a
  product's scenario in `PROJECTS` and its `expect` together. `DEPTH` adds the story layer (history commits,
  HANDOFF.md, MEMORY.md, CLAUDE.md, extra sessions, a branch) and must never change a gate outcome: history only
  lands between a product's first and last scenario commit, extra sessions predate its checkpoint. Presenter guide: `DEMO.md`.
- `docs/presentation.html` is the short stage talk (what, why, lessons, tech); it embeds `poc_city.html`.
- `docs/lessons-learned.html` is the interactive deck about why it exists and the lessons learned.
- `docs/superpowers/specs/` holds design specs (villager traffic, SimCity city POC) with acceptance criteria.

## Rules

- Read-only. No code path may write, move or delete anything under a project folder or `~/.claude`.
- Stdlib only. No pip installs.
- Nothing personal in the repo: no machine paths, real names or real project scans. Machine-specific
  values come from env (`COC_OWNER`, `COC_EXTRA_ROOTS`). `py tools/leakcheck.py` must pass before a push.
- Any new parser or check gets a `selftest*` case that failed before the fix. `tools/mutate.py` checks that tests catch deliberate breakage.
- Windows: open text files with explicit `encoding="utf-8-sig"`; run subprocesses with list args, never a shell string.
