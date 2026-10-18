# Talk: Product Library (about 10 minutes)

Deck: `docs/presentation.html` (6 slides). Then the live app, where the guide on screen
carries the demo: 14 steps, each with what to say, what to do, and what is really in the repo.

## On the presenting laptop, before you start
1. Windows Settings > Accessibility > Visual effects > **Animation effects ON**.
2. In the repo folder (wherever you cloned it):
   `py demo/make_demo.py --rehearse` must print **rehearsal OK**.
3. `py demo/make_demo.py --serve`, then open `http://127.0.0.1:7777` in a **new tab** (starts at step 1).
4. Open a second terminal in the same repo folder for the two live commands.
   Optional: `py demo/make_demo.py --code` opens every demo project in VS Code (it rebuilds the demo: run it before `--serve`).
5. Open the deck in another tab. F11 for full screen.

Keys: **PgDn / PgUp** move the deck AND the guide (a clicker sends these). **T** hides the guide.

---

## The deck (about 3 minutes)

**1. Product Library (15s)**
"Every project I've started with Claude Code, drawn as a city. The city is fun. The point is that it
checks its own notes."

**2. It started with one file (60s): the heart of the talk**
Point at the file on the slide.
"At the end of every Claude Code session, Claude writes this: session-state.md. The stage, the next
step, the proof it worked, the blockers. I loved it. Then I'd come back weeks later, read 'next: tag
v1.0', and not know if it was still true. Maybe I'd already done it. Maybe the proof was made up.
That question, is this note still true, is why I built this."
"git log tells you what happened. It never tells you the note is out of date."

**3. Three ways a note lies (45s)**
"Out of date: work landed after it was written. A commit that was never made: ask git. A quote that
doesn't match its file: check it word for word."
"No AI grades any of this. Same input, same answer, every time."

**4. Checked, or only written down (30s)**
"So every project's note gets split in two: what the machine checked, and what's just words.
On the demo city, 22 of 26 checks hold, and 76 lines are only someone's word. Words are fine.
They just shouldn't look like facts."

**5. Live demo (5s)**
"Let me show you." Switch to the app tab.

## The app (about 6 minutes)
Follow the guide panel at the top left. Read the big text to the audience; the gold DO line is
for you. PgDn after each step. Steps 4 and 5 are the live commands:

    py demo/make_demo.py --commit calculator
    py demo/make_demo.py --checkpoint calculator

Wait ten seconds after the first one, then F5. The guide stays on its step through F5.
On the last step, press T to hide the guide, then switch back to the deck.

## The deck, last slide (30s)
**6. End every session with three things**
"A next step, and 'continue' doesn't count. Proof it worked. Who owns each blocker. Then check the
note against the work before you trust it. Thank you. Questions?"

---

## Likely questions
- **"Why not just a README?"** "A README doesn't know it's out of date. This compares it to the work."
- **"What if nobody writes the checkpoint?"** "Then the gate fails. No note is a finding, not a pass."
- **"Why not let a model grade it?"** "A model can make up evidence. These checks can't."
- **"Does '6 tests pass' get checked?"** "No, that's still words. The commit next to it is what's checked. I say so on screen."
- **"Who is it for?"** "Anyone juggling many Claude Code projects. With two projects, git log is enough."
- **"Does it send anything anywhere?"** "No. Local, read-only, bound to 127.0.0.1, a token on every call."
- **"Can I use it?"** "github.com/xxthemayourxx/product-library. MIT."

## If something goes wrong
- City not moving: Animation effects is off (step 1 above).
- Guide not showing: you opened the real app (`py coc.py`), not `make_demo.py --serve`.
- `--commit` didn't flip it: wait the full ten seconds, then F5.
- Port 7777 busy: another Product Library is running. Close it first.
