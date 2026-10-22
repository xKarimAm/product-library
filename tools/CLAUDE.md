# tools/: test harnesses and probes (nothing here ships)

All Python stdlib. Browser-driving scripts need Google Chrome and go through `drive.py` (a small
Chrome DevTools Protocol client). Run them from the repo root.

| Script | Purpose | Needs a running server? |
|---|---|---|
| `leakcheck.py` | fails on a home-folder path, personal email, private IP, or any word in env `LEAK_WORDS`, in any tracked file. Run before every push | no |
| `sync_public.py` | the public sync in one command: guards (private main clean and pushed, public level with origin and holding nothing private never had), swaps in `git archive main`, leakcheck, one UTC commit as public's last author, push. `--dry-run` changes nothing; `--selftest` runs in CI | no |
| `mutate.py` | breaks `library.py` on purpose, one change at a time, and requires `--selftest` to fail | no |
| `http_battery.py` | HTTP-layer security checks over raw sockets (Host, token, path traversal, body limits) | starts its own |
| `drive.py` | tiny Chrome DevTools Protocol driver; other scripts import it. `attach()` pins `prefers-reduced-motion` to no-preference unless a `--reduced` run passes `--force-prefers-reduced-motion`, so results don't depend on the Windows "Animation effects" setting | - |
| `routes.py` | interaction and client-route checks against the hive DOM | yes |
| `shot.py` | screenshot plus DOM probe of the Product Library page | yes |
| `phase1.py` / `phase2.py` / `phase3.py` | acceptance checks for the villager phases (traffic, idle poses, cursor reactions) | yes |
| `err.py` | catches page JS errors before any script runs | yes |
| `build_poc.py` | builds `../poc_city.html`: a standalone copy of `index.html` with `poc_data.json` (falls back to `sample_data.json`) baked in, so it opens from file:// with no server. The city itself (towers, tents, roads, roster, day/night) lives in `index.html` | no |
| `pocprobe.py` | 53 geometry and mechanics checks on the POC city; exits 1 on failure | no (file://) |
| `make_gif.py` | records `docs/tour.gif` (the README tour) from the sample city: drawn cursor, STALE bubble, full view, report. Stdlib GIF encoder (per-frame median-cut palette, changed-rect frames); hides the clone's parent folder and home dir as `~` and refuses a frame that still shows one. `--selftest` = LZW round trip | yes, the sample city (`py sample/make_sample.py --serve`) |
| `poczoom.py`, `zoomcell.py`, `walkshot.py`, `sheet.py`, `greetsheet.py`, `msgcheck.py` | visual eyeball captures of sprites and the skyline | varies |

Data:

- `sample_data.json` holds made-up projects that are safe to commit.
- `poc_data*.json` holds real scans. It is git-ignored and must never be committed.

Where an API field is needed in a test, its name is documented in `../CLAUDE.md` (the `light()` payload).
