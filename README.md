# Product Library

(Formerly COC, Center of Claude. Files and env vars keep the `coc` name.)

A local, read-only dashboard over every project you run Claude Code in, drawn as a
pixel-art SimCity-style city. How far along a project is reads as its building (dirt lot, tent,
low-rise, tower), its colour is its state, and the city has villagers, traffic, a day/night
cycle, searchlights and a project rail with a colour legend.

**Presenting it?** `docs/presentation.html` is the short talk: what it is, why, what builders can
learn, the tech. Arrow keys move between slides.

**Going deeper:** `docs/lessons-learned.html` is an interactive
deck covering why this exists, how to read the city, every technology choice and
what it beat, the build story, and 33 lessons learned. It works as a presentation:
arrow keys move between chapters.

Python standard library only - nothing to install.

## Run the live dashboard

    py coc.py              # then open http://127.0.0.1:7777
    py coc.py --selftest   # assert-based checks, no server

## Live demo

    py demo/make_demo.py --serve   # then open http://127.0.0.1:7777

A 20-building demo city covering every state Product Library can show. **[DEMO.md](DEMO.md)** has the
setup, what each hero product demonstrates, a seven-minute talk track and troubleshooting.

## Your settings

Nothing machine-specific lives in the repo. Two environment variables personalise it:

- `COC_OWNER`: the name you write in blockers, e.g. `Sam` for `Sam [S]: pick a vendor`. Blockers
  starting with it count as "waiting on you". Default `Me`, matching `Me [M]: ...`.
- `COC_EXTRA_ROOTS`: extra project folders that have never had a Claude session, separated by `;`
  on Windows.

## Before you push

    py tools/leakcheck.py

It fails on any home-folder path, personal email or private IP in a tracked file. Put words only
you would recognise (your name, real project names) in `LEAK_WORDS`, comma separated, so the list
is never committed: `$env:LEAK_WORDS="name,project"; py tools/leakcheck.py`.

## Offline copy

`poc_city.html` is a standalone copy of the city that opens straight from disk. The copy in this
repo is built from **made-up demo projects** (`tools/demo_data.json`). To build it
from your own projects instead, save your server's `/api/projects` JSON as
`tools/poc_data.json` (git-ignored, never commit it) and run:

    py tools/build_poc.py
    py tools/pocprobe.py   # 53 checks, exits 1 on failure (needs Google Chrome)

Design notes and decisions: `docs/superpowers/specs/`. Project names in comments
and docs are placeholders.
