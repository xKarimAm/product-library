"""Build the Product Library demo: six small real products plus a generated crowd (20 in all), each with git history, a
/coc-checkpoint state file and Claude transcripts in a DEMO-ONLY registry.

    py demo/make_demo.py            # build ../../coc-demo and self-check it
    py demo/make_demo.py --serve    # build, check, then run Product Library on the demo
    py demo/make_demo.py --code     # build, check, then open every demo project in VS Code

Every timestamp is relative to now, so rebuild right before showing it. Product Library is
pointed at the demo with COC_REGISTRY / COC_EXTRA_ROOTS; nothing here reads or
writes ~/.claude. The six products cover every state the dashboard can show:

    calculator        ship    gate PASS, real test proof, clean git
    chatbot-frontend  build   gate PASS, a decision waiting on you, dirty tree
    habit-tracker     verify  STALE: a commit landed after the checkpoint
    url-shortener     define  gate FAIL: filler next_action, unowned blocker, no proof
    pomodoro-timer    ship    gate PASS with a soft gap: proof cites a commit git does not have
    weather-widget    -       gate FAIL: no state file at all, dormant for weeks
"""
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
import uuid
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
OUT = os.environ.get("COC_DEMO_DIR") or os.path.join(os.path.dirname(REPO), "coc-demo")
MARK = ".coc-demo"          # only a folder carrying this is ever deleted
H = 3600
NOW = time.time()
TESTS = "TESTS"             # proof placeholder: replaced by the real unittest result
GRACE = 10                  # seconds of drift grace in the demo (COC's default is an hour)

# Ages are hours before now. A commit's file list says what that commit adds.
PROJECTS = [
    {
        "name": "calculator",
        "commits": [(26, "Calculator with + - * / and precedence", ["calculator.py", ".gitignore"]),
                    (3, "Add parentheses, unary minus and tests", ["test_calculator.py", "README.md"])],
        "sessions": [(26.5, ["build a command-line calculator in python without eval"]),
                     (22, ["add operator precedence"]), (18, ["support decimals and negative results"]),
                     (14, ["make error messages point at the bad character"]), (9, ["refactor the parser into tokens and grammar"]),
                     (5, ["profile it on a long expression"]),
                     (2.3, ["add parentheses and unary minus", "write unit tests including division by zero"])],
        "state_age": 2,
        "state": {"status": "done", "stage": "ship", "current_task": "v1 calculator",
                  "next_action": "tag v1.0 and add a usage example for parentheses to the README",
                  "proof": TESTS, "blockers": [],
                  "for": "anyone who wants exact arithmetic without eval()",
                  "bet": "a parser I trust beats a one-liner that can run arbitrary code"},
        "expect": {"gate": "pass", "gaps": [], "drift": None, "waiting": 0, "stage": "ship"},
    },
    {
        "name": "chatbot-frontend",
        "commits": [(30, "Chat UI: message log and canned replies", ["index.html", ".gitignore"]),
                    (2, "Typing indicator, README and tester feedback", ["README.md", "FEEDBACK.md"])],
        "sessions": [(30.5, ["build a chatbot front end in one html file"]),
                     (5, ["add a typing indicator"]),
                     # Ends BEFORE the checkpoint: the demo's 10s grace would flag a tail.
                     (0.75, ["make the message bubbles readable on a projector"])],
        "dirty": ("index.html", "\n<!-- wip: larger font for the projector -->\n"),
        "state_age": 0.7,
        "state": {"status": "active", "stage": "build", "current_task": "chat UI polish",
                  "next_action": "wire reply() in index.html to the chosen provider API",
                  "proof": "opened index.html in Chrome: greeting, typing indicator and 3 canned replies render",
                  "for": "people who want to try a model in a browser tab",
                  "bet": "FEEDBACK.md: 'I just want to try a model without installing anything'",
                  "blockers": ["Me [M]: pick the model provider (OpenRouter or Anthropic API)",
                               "DONE 2026-10-16: message bubbles render"]},
        "expect": {"gate": "pass", "gaps": [], "drift": None, "waiting": 1, "stage": "build"},
    },
    {
        "name": "habit-tracker",
        "commits": [(50, "Habit tracker CLI with JSON store", ["habits.py", ".gitignore", "README.md"]),
                    (1, "Streak keeps yesterday when today is unchecked", ["test_habits.py"])],
        "sessions": [(50.5, ["build a habit tracker cli with streaks"]),
                     (6.5, ["check the streak logic against real dates"])],
        "state_age": 6,
        "state": {"status": "active", "stage": "verify", "current_task": "streak edge cases",
                  "next_action": "run a week of real check-ins through habits.py and compare streaks by hand",
                  "proof": TESTS, "blockers": [],
                  "for": "me, building one habit at a time",
                  "bet": "a streak I can see keeps me going on bad days"},
        "expect": {"gate": "fail", "gaps": ["fresh"], "drift": "commit", "waiting": 0, "stage": "verify"},
    },
    {
        "name": "url-shortener",
        "commits": [(72, "Shortener sketch on http.server", ["shortener.py", ".gitignore", "README.md"])],
        "sessions": [(74, ["sketch a url shortener on the standard library"]),
                     (25, ["sketch the redirect handler", "continue"])],
        "state_age": 24,
        "state": {"status": "blocked", "stage": "define", "current_task": "scope the shortener",
                  "next_action": "continue", "proof": None,
                  "blockers": ["Sam [S]: confirm we can use the short.link domain",
                               "rate limiting is still undecided"]},
        "expect": {"gate": "fail", "gaps": ["next_action", "blockers_owned", "proof", "card"],
                   "drift": None, "waiting": 0, "stage": "define"},
    },
    {
        # The tests are real; the commit the proof cites was never made (squashed
        # away, or claimed and not done). COC asks git, so the citation fails.
        "name": "pomodoro-timer",
        "commits": [(9, "Pomodoro schedule and countdown", ["pomodoro.py", ".gitignore", "README.md"]),
                    (4, "Long break after every fourth round", ["test_pomodoro.py"])],
        "sessions": [(9.5, ["build a terminal pomodoro timer"]),
                     (4.5, ["add a long break after every fourth round, test it, commit and checkpoint"])],
        "state_age": 3.5,
        "fake_commit": "4f9e2a1",
        "state": {"status": "done", "stage": "ship", "current_task": "v1 pomodoro timer",
                  "next_action": "add a --work flag so the block length is not fixed at 25 minutes",
                  "proof": TESTS, "blockers": [],
                  "for": "me, when I need to focus for an hour",
                  "bet": "short timed blocks beat open-ended sessions"},
        "expect": {"gate": "pass", "gaps": ["proof_commit"], "drift": None, "waiting": 0, "stage": "ship"},
    },
    {
        "name": "weather-widget",
        "commits": [(24 * 40, "Idea notes", ["README.md", ".gitignore"])],
        "sessions": [(24 * 40 + 1, ["is a desktop weather widget worth building"])],
        "state_age": None,
        "expect": {"gate": "fail", "gaps": ["has_state"], "drift": None, "waiting": 0, "stage": None},
    },
]


# The crowd: generated products that turn six buildings into a skyline. Each is
# README + main.py with real git history, real transcripts and a checkpoint shaped
# by its scenario. Columns: name, what it is, scenario, sessions (tower height),
# hours since last touched, and the next step (for "waiting": the decision).
EXTRA = [
    # towers: months of work
    ("kanban-board", "Drag-and-drop kanban board in one HTML file", "pass", 31, 2, "persist column order across reloads"),
    ("invoice-parser", "Pull totals and due dates out of PDF invoices", "pass", 26, 6, "handle invoices whose total sits on page two"),
    ("meeting-notes-ai", "Summarise meeting transcripts into action items", "waiting", 28, 26, "Me [M]: pick the summary length for the default view"),
    # low-rise: finding their footing
    ("recipe-scaler", "Scale a recipe to any number of servings", "pass", 8, 3, "convert cups to grams for the five pantry staples"),
    ("snake-game", "Snake in the browser with a level editor", "stale", 6, 5, "add a pause screen"),
    ("expense-splitter", "Split a group trip's expenses fairly", "pass", 5, 30, "round settlements to the nearest cent without drift"),
    # tents: just started
    ("qr-generator", "QR codes with a logo in the middle", "nostate", 2, 8, None),
    ("unit-converter", "Unit converter with a fuzzy search box", "nostate", 1, 36, None),
    ("slack-digest-bot", "Daily digest of busy Slack channels", "soft", 3, 40, None),
    ("json-diff", "Readable diffs between two JSON files", "nostate", 2, 140, None),
    # dormant
    ("tetris-clone", "Tetris clone with a ghost piece", "dormant", 24, 24 * 70, "tune the lock delay"),
    ("screenshot-ocr", "Copy text out of any screenshot", "dormant", 8, 24 * 120, None),
]
LOTS = ["E--Prototypes-arcade-leaderboard", "E--Prototypes-home-inventory"]   # zoned, never built
STAGES = ["build", "verify", "ship"]
PROMPTS = ["add tests for the main path", "fix the crash when the input file is empty",
           "tidy the README and add a usage example", "make the output readable on a projector",
           "handle the edge case we found yesterday", "speed up the slow startup"]


def extra(i, name, about, kind, n, age, nxt):
    first = age + 24 * (3 + n % 9)
    newest = age + (0.3 if kind == "stale" else 0)       # stale: the commit is the newest work
    step = (first - newest) / max(1, n - 1)
    # The towers carry real code (demo/products/<name>/main.py, with a real
    # --selftest); the rest of the crowd is a stub that only says what it is.
    real = os.path.join(HERE, "products", name, "main.py")
    if os.path.exists(real):
        with open(real, encoding="utf-8") as fh:
            main = fh.read()
    else:
        main = ('"""%s."""\nimport sys\n\nif __name__ == "__main__":\n'
                '    print("OK" if "--selftest" in sys.argv else %r)\n' % (about, name + ": " + about))
    p = {
        "name": name,
        "files": {"README.md": "# %s\n\n%s.\n\n    py main.py\n" % (name, about), "main.py": main},
        "commits": [(first + 0.5, "Start " + name, ["README.md", ".gitignore"]),
                    (age if kind == "stale" else newest + 0.5, about, ["main.py"])],
        "sessions": [(first - k * step, ["build " + about[0].lower() + about[1:]] if k == 0
                      else [PROMPTS[(i + k) % len(PROMPTS)]]) for k in range(n)],
        "state_age": None,
        "expect": {"gate": "fail", "gaps": ["has_state"], "drift": None, "waiting": 0, "stage": None},
    }
    if nxt is None:
        if kind == "soft":
            p["state_age"] = newest - 0.1
            p["state"] = {"status": "blocked", "stage": "define", "current_task": about,
                          "next_action": "continue", "proof": None,
                          "blockers": ["the API quota is still unknown"]}
            p["expect"] = {"gate": "fail", "gaps": ["next_action", "blockers_owned", "proof", "card"],
                           "drift": None, "waiting": 0, "stage": "define"}
        return p
    stage = STAGES[i % 3]
    waiting = kind == "waiting"
    p["state_age"] = newest + (4 if kind == "stale" else -0.1)
    p["state"] = {"status": "active", "stage": stage, "current_task": about,
                  "next_action": "decide, then wire it into main.py" if waiting else nxt,
                  "proof": "py main.py --selftest -> OK",
                  "blockers": [nxt] if waiting else [],
                  "for": "me first, then friends who asked for it",
                  "bet": about + " in one step, instead of by hand"}
    p["expect"] = {"gate": "fail" if kind == "stale" else "pass", "gaps": ["fresh"] if kind == "stale" else [],
                   "drift": "commit" if kind == "stale" else None, "waiting": int(waiting), "stage": stage}
    return p


PROJECTS += [extra(i, *row) for i, row in enumerate(EXTRA)]

# The tallest tower quotes a user who never said that: the notes say two hours
# a week, the card claims two hours a day. Product Library reads the file.
_inv = next(p for p in PROJECTS if p["name"] == "invoice-parser")
_inv["files"]["NOTES.md"] = "Sam (accounts): we re-type every invoice total by hand,\nabout two hours a week.\n"
_inv["commits"][1] = (_inv["commits"][1][0], _inv["commits"][1][1], ["main.py", "NOTES.md"])
_inv["state"]["bet"] = "NOTES.md: 'we re-type every invoice total by hand, about two hours a day'"
_inv["expect"]["gaps"] = ["proof_quote"]

# Depth: the story around each scenario, so the full view has something real in
# every section. Kept apart from PROJECTS on purpose: nothing here may change a
# gate, drift or stage outcome. History commits only land BETWEEN a product's
# first and last scenario commit, and extra sessions are all older than its
# checkpoint, so `expect` above stays true.
#   history: (age_h, message) - each commit appends that line to CHANGELOG.md
#   handoff: (age_h, title, [bullets]) - the append-only HANDOFF.md session log
#   memory:  Claude's per-project MEMORY.md (lives in the demo registry)
#   claude:  the project's CLAUDE.md
#   sessions: extra (age_h, [prompts]) on top of the scenario's own
#   branch:  work happens on this branch instead of main
#   prs:     (age_h, number) pull requests, linked from the nearest session
DEPTH = {
    "calculator": {
        "history": [(24, "Tokenizer: numbers, operators and whitespace"),
                    (21, "Fix: 2-3-4 was evaluated right to left"),
                    (17, "Decimals and negative results"),
                    (13, "Errors point at the bad character with a caret"),
                    (8, "Refactor: tokens and grammar in separate functions"),
                    (5, "40% faster on a 10,000-term expression")],
        "handoff": [(25, "Tokenizer works", ["numbers, + - * / and spaces tokenize", "next: precedence"]),
                    (12, "Error messages", ["`2 + * 3` now shows a caret under the `*`", "next: refactor before adding parentheses"]),
                    (2.2, "Parentheses and tests", ["unary minus and nested parentheses work",
                                                    "6 unit tests incl. division by zero, all green",
                                                    "next: tag v1.0 and document parentheses"])],
        "memory": "# Calculator memory\n\n- Never use eval(); the whole point is a parser we trust.\n"
                  "- Grammar: expr -> term (('+'|'-') term)*, term -> factor (('*'|'/') factor)*.\n"
                  "- Tests run with `py -m unittest`; keep them under a second.\n",
        "claude": "# Calculator\n\nRecursive-descent calculator, standard library only. No eval().\n"
                  "Run tests with `py -m unittest` before every commit.\n",
        "prs": [(20, 1), (12, 2), (4, 3)],
        "sessions": [(16, ["why does 2-3-4 give 3", "fix associativity for minus"]),
                     (11, ["add a caret under the bad character in error messages"]),
                     (7, ["split the parser into tokenize() and parse()"])],
    },
    "chatbot-frontend": {
        "history": [(27, "Message log scrolls to the newest reply"),
                    (22, "Canned replies rotate instead of repeating"),
                    (14, "Dark theme for the projector"),
                    (9, "Tester feedback round with three friends")],
        "handoff": [(28, "First chat UI", ["message log and input box in one HTML file", "replies are canned for now"]),
                    (8, "Tester feedback", ["3 friends tried it, notes in FEEDBACK.md", "all want it to run without installing anything"]),
                    (0.8, "Projector polish", ["bubbles readable at the back of a room",
                                               "blocked: which model provider to wire in (my call)"])],
        "memory": "# Chatbot front end memory\n\n- One HTML file, no build step, no framework.\n"
                  "- reply() is the only function that will call a model; keep it isolated.\n"
                  "- Provider choice is open: OpenRouter (many models) or Anthropic API (one key).\n",
        "claude": "# Chatbot front end\n\nSingle-file chat UI. Open index.html in a browser; nothing to install.\n",
        "sessions": [(20, ["make canned replies rotate"]), (12, ["add a dark theme for projectors"])],
        "prs": [(13, 1)],
    },
    "habit-tracker": {
        "history": [(46, "Check-in command and JSON store"),
                    (40, "Streak counter"),
                    (31, "Fix: streak reset at midnight UTC instead of local time"),
                    (20, "Weekly summary view")],
        "handoff": [(48, "CLI skeleton", ["`habits.py add` and `habits.py check` work"]),
                    (30, "Timezone bug", ["streaks broke at UTC midnight; now uses local dates"]),
                    (6.2, "Streak edge cases", ["unchecked today should keep yesterday's streak",
                                                "next: a week of real check-ins compared by hand"])],
        "memory": "# Habit tracker memory\n\n- Dates are LOCAL, never UTC: the midnight bug cost a day.\n"
                  "- Store is habits.json next to the script, git-ignored.\n",
        "claude": "# Habit tracker\n\nCLI habit tracker with streaks. `py habits.py --help`.\n",
        "sessions": [(36, ["why did my streak reset last night"]), (22, ["add a weekly summary"])],
        "prs": [(30, 1), (21, 2)],
        "branch": "streak-edge-cases",
    },
    "pomodoro-timer": {
        "history": [(7, "Countdown renders in place on one line"), (5, "Schedule builder with breaks")],
        "handoff": [(8.5, "Timer works", ["25/5 cycle counts down in the terminal"]),
                    (3.6, "Long breaks", ["every 4th break is 15 minutes", "3 tests green", "next: --work flag"])],
        "claude": "# Pomodoro timer\n\nTerminal timer. `py pomodoro.py 4` runs four rounds.\n",
    },
    "kanban-board": {
        "prs": [(150, 1), (60, 2), (3, 3)],
        "handoff": [(200, "Board skeleton", ["three columns, cards are plain text"]),
                    (80, "Drag and drop", ["native HTML drag events, no library"]),
                    (2.1, "Persistence", ["cards persist; column ORDER does not yet", "next: save column order"])],
        "memory": "# Kanban memory\n\n- No libraries: native drag-and-drop only.\n- State lives in localStorage under one key.\n",
    },
    "meeting-notes-ai": {
        "handoff": [(150, "Transcript parser", ["speaker turns parsed from .vtt files"]),
                    (26.5, "Summary length", ["short and long summaries both work", "waiting on me: pick the default length"])],
    },
}

# Demo plans for the Plans page (COC_PLANS_DIR points here), never the real
# ~/.claude/plans. (age_h, file name, markdown body)
PLANS = [
    (3, "calculator-v1-1.md", "# Calculator v1.1: scientific mode\n\nAdd sqrt, ^ and parentheses-aware error hints.\n"),
    (20, "chatbot-provider.md", "# Chatbot: choose and wire a model provider\n\nCompare OpenRouter and the Anthropic API on cost and setup.\n"),
    (70, "habit-weekly-review.md", "# Habit tracker: weekly review screen\n\nOne screen per week: streaks, misses, notes.\n"),
    (200, "portfolio-cleanup.md", "# Portfolio cleanup: what to archive\n\nWalk the dormant district; archive or revive each.\n"),
]
CHANGE_POOL = ["Tidy README usage", "Handle empty input", "Clearer error messages", "Small refactor",
               "Add a --help flag", "Fix an off-by-one", "Speed up startup", "Rename for clarity"]


def depth_for(p):
    """DEPTH for a hero, or a short generated history for a crowd product, so
    every building has more than two commits behind it."""
    d = dict(DEPTH.get(p["name"], {}))
    if "history" not in d and len(p["commits"]) > 1:
        first, last = p["commits"][0][0], p["commits"][-1][0]
        n = 2 + len(p["name"]) % 4
        d["history"] = [(last + (first - last) * (k + 1) / (n + 1),
                         CHANGE_POOL[(len(p["name"]) + k) % len(CHANGE_POOL)]) for k in range(n)]
    return d


def iso(age_h):
    return datetime.fromtimestamp(NOW - age_h * H).astimezone().isoformat(timespec="seconds")


def stamp(path, age_h):
    os.utime(path, (NOW - age_h * H, NOW - age_h * H))


def _force_rm(func, path, _info):
    os.chmod(path, stat.S_IWRITE)     # git object files are read-only on Windows
    func(path)


def reset_out():
    if os.path.exists(OUT):
        if not os.path.exists(os.path.join(OUT, MARK)):
            sys.exit("refusing to delete %s: it was not made by make_demo.py" % OUT)
        try:
            shutil.rmtree(OUT, **({"onexc": _force_rm} if sys.version_info >= (3, 12) else {"onerror": _force_rm}))
        except OSError as e:
            # A running demo server holds files open, so the delete stops part
            # way - possibly after the marker went. Put it back, or every later
            # run would refuse to touch a folder that is still ours.
            open(os.path.join(OUT, MARK), "w").close()
            sys.exit("could not clear %s (%s).\nIs a demo server still running, or a terminal or "
                     "Explorer window open inside it? Close it, then run this again." % (OUT, e.strerror or e))
    os.makedirs(os.path.join(OUT, "registry"))
    open(os.path.join(OUT, MARK), "w").close()


def git(cwd, *args, age_h=None):
    env = dict(os.environ)
    if age_h is not None:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = iso(age_h)
    r = subprocess.run(["git", "-c", "user.name=Product Library Demo", "-c", "user.email=demo@example.invalid",
                        "-C", cwd] + list(args), env=env, capture_output=True, text=True)
    if r.returncode:
        sys.exit("git %s failed in %s:\n%s" % (" ".join(args), cwd, r.stderr))
    return r.stdout.strip()


def unittest_proof(path):
    r = subprocess.run([sys.executable, "-m", "unittest", "-q"], cwd=path, capture_output=True, text=True)
    ran = re.search(r"Ran (\d+) tests?", r.stderr)
    if r.returncode or not ran:
        sys.exit("tests failed in %s, refusing to record them as proof:\n%s" % (path, r.stderr))
    return "py -m unittest -> Ran %s tests, OK" % ran.group(1)


def write_state(path, age_h, st):
    lines = ["---", "status: " + st["status"], "stage: " + st["stage"], "last_updated: " + iso(age_h),
             'current_task: "%s"' % st["current_task"], 'next_action: "%s"' % st["next_action"]]
    if st["proof"]:
        lines.append('proof: "%s"' % st["proof"])
    for key in ("for", "bet"):                 # the catalog card, when the scenario has one
        if st.get(key):
            lines.append('%s: "%s"' % (key, st[key]))
    lines += ["blockers: " + json.dumps(st["blockers"], ensure_ascii=False), "---", "", "## Notes", ""]
    fp = os.path.join(path, ".claude", "session-state.md")
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    with open(fp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    stamp(fp, age_h)


def session_title(prompt):
    """What Claude Code's ai-title looks like: the gist, sentence case, short."""
    t = prompt.strip().rstrip(".?!")
    t = t[0].upper() + t[1:]
    return t if len(t) <= 60 else t[:57].rsplit(" ", 1)[0] + "..."


def write_sessions(path, sessions, branch="main", prs=()):
    slug = re.sub(r"[^A-Za-z0-9]", "-", path)
    reg = os.path.join(OUT, "registry", slug)
    os.makedirs(reg)
    # Each PR is linked from the session closest to it in time.
    owner = {n: min(range(len(sessions)), key=lambda i: abs(sessions[i][0] - a)) for a, n in prs}
    for i, (age_h, prompts) in enumerate(sessions):
        sid = str(uuid.uuid4())
        rec = [{"type": "queue-operation", "sessionId": sid},
               {"type": "attachment", "cwd": path, "gitBranch": branch, "sessionId": sid}]
        for p in prompts:
            rec += [{"type": "user", "message": {"role": "user", "content": p}, "sessionId": sid},
                    {"type": "last-prompt", "lastPrompt": p, "sessionId": sid}]
        rec.append({"type": "ai-title", "aiTitle": session_title(prompts[0]), "sessionId": sid})
        name = os.path.basename(path)
        for a, n in prs:
            if owner[n] == i:
                rec.append({"type": "pr-link", "prNumber": n, "prRepository": "example-org/" + name,
                            "prUrl": "https://github.com/example-org/%s/pull/%d" % (name, n),
                            "timestamp": iso(a), "sessionId": sid})
        fp = os.path.join(reg, sid + ".jsonl")
        with open(fp, "w", encoding="utf-8") as fh:
            fh.write("".join(json.dumps(r) + "\n" for r in rec))
        stamp(fp, age_h)
    return reg


def build(p):
    path = os.path.join(OUT, p["name"])
    if "files" in p:                         # a generated crowd product
        os.makedirs(path)
        for rel, text in p["files"].items():
            with open(os.path.join(path, rel), "w", encoding="utf-8") as fh:
                fh.write(text)
    else:
        shutil.copytree(os.path.join(HERE, "products", p["name"]), path)
    with open(os.path.join(path, ".gitignore"), "w", encoding="utf-8") as fh:
        fh.write(".claude/\n__pycache__/\nhabits.json\n")
    st = p.get("state")
    if st and st["proof"] == TESTS:
        st = dict(st, proof=unittest_proof(path))
    d = depth_for(p)
    commits = [(a, m, list(f)) for a, m, f in p["commits"]]
    if d.get("claude"):
        with open(os.path.join(path, "CLAUDE.md"), "w", encoding="utf-8") as fh:
            fh.write(d["claude"])
        commits[0][2].append("CLAUDE.md")
    if d.get("handoff"):
        log = ["# Handoff log", "", "Each session appends one entry at the bottom."]
        for age_h, title, bullets in d["handoff"]:
            log += ["", "## %s: %s" % (iso(age_h)[:10], title), ""] + ["- " + b for b in bullets]
        with open(os.path.join(path, "HANDOFF.md"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(log) + "\n")
        commits[-1][2].append("HANDOFF.md")
    first, last = commits[0][0], commits[-1][0]
    story = sorted(commits + [(a, m, None) for a, m in d.get("history", []) if last < a < first],
                   key=lambda c: -c[0])
    git(path, "init", "-q", "-b", "main")
    changes = ["# Changelog", ""]
    for i, (age_h, msg, files) in enumerate(story):
        if files is None:                    # a history commit: one changelog line
            changes.append("- " + msg)
            with open(os.path.join(path, "CHANGELOG.md"), "w", encoding="utf-8") as fh:
                fh.write("\n".join(changes) + "\n")
            files = ["CHANGELOG.md"]
        if d.get("branch") and i == len(story) - 1:
            git(path, "checkout", "-q", "-b", d["branch"])
        git(path, "add", *files)
        git(path, "commit", "-q", "-m", msg, age_h=age_h)
    if st:
        if st["proof"]:
            cite = p.get("fake_commit") or git(path, "rev-parse", "--short", "HEAD")
            st = dict(st, proof=st["proof"] + "; commit " + cite)
        write_state(path, p["state_age"], st)
    if p.get("dirty"):
        rel, text = p["dirty"]
        with open(os.path.join(path, rel), "a", encoding="utf-8") as fh:
            fh.write(text)
    reg = write_sessions(path, p["sessions"] + d.get("sessions", []), d.get("branch", "main"),
                         d.get("prs", ()))
    if d.get("memory"):                      # Claude's own per-project notes, as the registry keeps them
        os.makedirs(os.path.join(reg, "memory"))
        with open(os.path.join(reg, "memory", "MEMORY.md"), "w", encoding="utf-8") as fh:
            fh.write(d["memory"])
    for f in os.listdir(path):               # README etc. must not look newer than the work
        if os.path.isfile(os.path.join(path, f)):
            stamp(os.path.join(path, f), p["commits"][-1][0])


def build_all():
    reset_out()
    # Products share nothing (git() copies its env, -C sets the folder), and each
    # waits on git subprocesses: in parallel the build takes seconds, not 15.
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(build, PROJECTS))         # list() re-raises a product's failure here
    for slug in LOTS:                        # a registry entry with nothing behind it
        os.makedirs(os.path.join(OUT, "registry", slug))
    os.makedirs(os.path.join(OUT, "plans"))
    for age_h, name, body in PLANS:
        fp = os.path.join(OUT, "plans", name)
        with open(fp, "w", encoding="utf-8") as fh:
            fh.write(body)
        stamp(fp, age_h)
    # One VS Code window with every demo project, so the audience can see the files.
    with open(os.path.join(OUT, "demo.code-workspace"), "w", encoding="utf-8") as fh:
        json.dump({"folders": [{"path": p["name"]} for p in PROJECTS]}, fh, indent=2)


def env():
    # Demo projects only, and a grace short enough that a live commit flips a
    # project to STALE while the audience watches.
    return dict(os.environ, COC_REGISTRY=os.path.join(OUT, "registry"), COC_EXTRA_ROOTS="",
                COC_PLANS_DIR=os.path.join(OUT, "plans"), COC_DRIFT_GRACE=str(GRACE),
                COC_TOUR=os.path.join(HERE, "tour.json"))   # the on-screen presenter guide


def scenario(name):
    p = next((p for p in PROJECTS if p["name"] == name), None)
    path = os.path.join(OUT, name)
    if not p or not os.path.isdir(path) or not os.path.exists(os.path.join(OUT, MARK)):
        sys.exit("no built demo product %r (one of: %s). Build first: py demo/make_demo.py"
                 % (name, ", ".join(q["name"] for q in PROJECTS)))
    return p, path


def live_commit(name):
    """A real commit made now, after the product's checkpoint: STALE in GRACE seconds."""
    global NOW
    NOW = time.time()                 # live actions stamp the real moment, not script start
    _, path = scenario(name)
    with open(os.path.join(path, "README.md"), "a", encoding="utf-8") as fh:
        fh.write("\nLive change at %s.\n" % datetime.now().strftime("%H:%M:%S"))
    git(path, "add", "README.md")
    git(path, "commit", "-q", "-m", "Live change during the demo", age_h=0)
    print("%s: committed %s. STALE in ~%ds; press F5 or wait for the 30s refresh."
          % (name, git(path, "rev-parse", "--short", "HEAD"), GRACE))


def live_checkpoint(name):
    """What /coc-checkpoint writes, done now: the product passes again."""
    global NOW
    NOW = time.time()
    p, path = scenario(name)
    if not p.get("state"):
        sys.exit("%s has no checkpoint scenario (it demonstrates 'no state at all')" % name)
    st = dict(p["state"])
    if st["proof"] == TESTS:
        st["proof"] = unittest_proof(path)
    if st["proof"]:
        st["proof"] += "; commit " + git(path, "rev-parse", "--short", "HEAD")
    write_state(path, 0, st)
    print("%s: checkpoint written. Fresh again on the next refresh." % name)


def rehearse():
    """The live moment, end to end, asserted through COC: PASS, commit, STALE, checkpoint, PASS."""
    import coc

    def gate_of(name):
        r = next(r for r in coc.scan(force=True) if r["name"] == name)
        return r["gate"]["verdict"], (r["drift"] or {}).get("by")

    assert gate_of("calculator") == ("pass", None), gate_of("calculator")
    live_commit("calculator")
    time.sleep(GRACE + 1)
    assert gate_of("calculator") == ("fail", "commit"), gate_of("calculator")
    live_checkpoint("calculator")
    assert gate_of("calculator") == ("pass", None), gate_of("calculator")
    print("rehearsal OK: calculator went PASS -> STALE -> PASS")


def check():
    """Scan the demo through COC itself and require every product's state."""
    os.environ.update(env())
    sys.path.insert(0, REPO)
    import coc
    got = {r["name"]: r for r in coc.scan(force=True)}
    bad = []
    print("%-17s %-7s %-5s %-34s %-10s %s" % ("project", "stage", "gate", "gaps", "drift", "waiting"))
    for p in PROJECTS:
        r = got.get(p["name"])
        if r is None:
            bad.append(p["name"] + ": not found by the scan")
            continue
        lt, g, d = coc.light(r), r["gate"] or {}, r["drift"] or {}
        seen = {"gate": g.get("verdict"), "gaps": [x["id"] for x in g.get("gaps", [])],
                "drift": d.get("by"), "waiting": lt["waiting_count"], "stage": lt["stage"]}
        print("%-17s %-7s %-5s %-34s %-10s %s" % (p["name"], seen["stage"], seen["gate"],
              ",".join(seen["gaps"]) or "-", seen["drift"] or "-", seen["waiting"]))
        bad += ["%s: %s is %r, want %r" % (p["name"], k, seen[k], v)
                for k, v in p["expect"].items() if seen[k] != v]
    if bad:
        sys.exit("DEMO CHECK FAILED\n  " + "\n  ".join(bad))
    for p in PROJECTS:                       # every building has a story: origin, a chapter per session
        r = got[p["name"]]
        if not r["origin"] or len(r["chapters"]) != r["sessions"]:
            bad.append("%s: origin %r, %d chapters for %d sessions"
                       % (p["name"], (r["origin"] or {}).get("prompt"), len(r["chapters"]), r["sessions"]))
    for name, d in DEPTH.items():            # the story layer landed where the UI reads it
        r = got[name]
        if len(r["prs"]) != len(d.get("prs", ())):
            bad.append("%s: %d PRs, want %d" % (name, len(r["prs"]), len(d.get("prs", ()))))
        if d.get("handoff") and not any(l["name"] == "HANDOFF.md" and l["heading"] for l in r["logs"]):
            bad.append(name + ": HANDOFF.md log missing")
        if d.get("memory") and not r["memory"]:
            bad.append(name + ": MEMORY.md missing")
        if d.get("branch") and (r["git"] or {}).get("branch") != d["branch"]:
            bad.append("%s: branch is %r, want %r" % (name, (r["git"] or {}).get("branch"), d["branch"]))
    if sorted(x["name"] for x in coc.plans()) != sorted(n for _a, n, _b in PLANS):
        bad.append("plans: not exactly the demo plans (the real ~/.claude/plans could show)")
    if bad:
        sys.exit("DEMO CHECK FAILED\n  " + "\n  ".join(bad))
    lots = [r for r in got.values() if r["unresolved"]]
    if len(lots) != len(LOTS):
        sys.exit("DEMO CHECK FAILED\n  %d empty lots, want %d" % (len(lots), len(LOTS)))
    print("demo check OK: %d products and %d empty lots in %s" % (len(PROJECTS), len(lots), OUT))


if __name__ == "__main__":
    for flag, act in (("--commit", live_commit), ("--checkpoint", live_checkpoint)):
        if flag in sys.argv:                   # live actions touch the built demo, never rebuild it
            i = sys.argv.index(flag)
            sys.exit(act(sys.argv[i + 1] if i + 1 < len(sys.argv) else ""))
    build_all()
    check()
    if "--rehearse" in sys.argv:
        rehearse()
        build_all()                            # leave the demo exactly as it starts on stage
        check()
    if "--code" in sys.argv:                  # open every demo project in one VS Code window
        import coc
        if not coc.VSCODE:
            sys.exit("VS Code not found. Open %s by hand." % os.path.join(OUT, "demo.code-workspace"))
        subprocess.Popen([coc.VSCODE, os.path.join(OUT, "demo.code-workspace")])
    if "--serve" in sys.argv:
        # In this process, not a child: check() already imported coc with the
        # demo env, and a child outlived its parent when the parent was killed.
        import coc
        coc.serve()
