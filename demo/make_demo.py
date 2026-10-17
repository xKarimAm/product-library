"""Build the Product Library demo: six small real products plus a generated crowd (20 in all), each with git history, a
/coc-checkpoint state file and Claude transcripts in a DEMO-ONLY registry.

    py demo/make_demo.py            # build ../../coc-demo and self-check it
    py demo/make_demo.py --serve    # build, check, then run Product Library on the demo

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
                  "proof": TESTS, "blockers": []},
        "expect": {"gate": "pass", "gaps": [], "drift": None, "waiting": 0, "stage": "ship"},
    },
    {
        "name": "chatbot-frontend",
        "commits": [(30, "Chat UI: message log and canned replies", ["index.html", ".gitignore"]),
                    (2, "Typing indicator and README", ["README.md"])],
        "sessions": [(30.5, ["build a chatbot front end in one html file"]),
                     (5, ["add a typing indicator"]),
                     # Ends BEFORE the checkpoint: the demo's 10s grace would flag a tail.
                     (0.75, ["make the message bubbles readable on a projector"])],
        "dirty": ("index.html", "\n<!-- wip: larger font for the projector -->\n"),
        "state_age": 0.7,
        "state": {"status": "active", "stage": "build", "current_task": "chat UI polish",
                  "next_action": "wire reply() in index.html to the chosen provider API",
                  "proof": "opened index.html in Chrome: greeting, typing indicator and 3 canned replies render",
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
                  "proof": TESTS, "blockers": []},
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
        "expect": {"gate": "fail", "gaps": ["next_action", "blockers_owned", "proof"],
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
                  "proof": TESTS, "blockers": []},
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
    p = {
        "name": name,
        "files": {"README.md": "# %s\n\n%s.\n\n    py main.py\n" % (name, about),
                  "main.py": '"""%s."""\nimport sys\n\nif __name__ == "__main__":\n'
                             '    print("OK" if "--selftest" in sys.argv else %r)\n' % (about, name + ": " + about)},
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
            p["expect"] = {"gate": "fail", "gaps": ["next_action", "blockers_owned", "proof"],
                           "drift": None, "waiting": 0, "stage": "define"}
        return p
    stage = STAGES[i % 3]
    waiting = kind == "waiting"
    p["state_age"] = newest + (4 if kind == "stale" else -0.1)
    p["state"] = {"status": "active", "stage": stage, "current_task": about,
                  "next_action": "decide, then wire it into main.py" if waiting else nxt,
                  "proof": "py main.py --selftest -> OK",
                  "blockers": [nxt] if waiting else []}
    p["expect"] = {"gate": "fail" if kind == "stale" else "pass", "gaps": ["fresh"] if kind == "stale" else [],
                   "drift": "commit" if kind == "stale" else None, "waiting": int(waiting), "stage": stage}
    return p


PROJECTS += [extra(i, *row) for i, row in enumerate(EXTRA)]


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
        shutil.rmtree(OUT, **({"onexc": _force_rm} if sys.version_info >= (3, 12) else {"onerror": _force_rm}))
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
    lines += ["blockers: " + json.dumps(st["blockers"], ensure_ascii=False), "---", "", "## Notes", ""]
    fp = os.path.join(path, ".claude", "session-state.md")
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    with open(fp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    stamp(fp, age_h)


def write_sessions(path, sessions):
    slug = re.sub(r"[^A-Za-z0-9]", "-", path)
    reg = os.path.join(OUT, "registry", slug)
    os.makedirs(reg)
    for age_h, prompts in sessions:
        sid = str(uuid.uuid4())
        rec = [{"type": "queue-operation", "sessionId": sid},
               {"type": "attachment", "cwd": path, "gitBranch": "main", "sessionId": sid}]
        for p in prompts:
            rec += [{"type": "user", "message": {"role": "user", "content": p}, "sessionId": sid},
                    {"type": "last-prompt", "lastPrompt": p, "sessionId": sid}]
        fp = os.path.join(reg, sid + ".jsonl")
        with open(fp, "w", encoding="utf-8") as fh:
            fh.write("".join(json.dumps(r) + "\n" for r in rec))
        stamp(fp, age_h)


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
    git(path, "init", "-q", "-b", "main")
    for age_h, msg, files in p["commits"]:
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
    write_sessions(path, p["sessions"])
    for f in os.listdir(path):               # README etc. must not look newer than the work
        if os.path.isfile(os.path.join(path, f)):
            stamp(os.path.join(path, f), p["commits"][-1][0])


def build_all():
    reset_out()
    for p in PROJECTS:
        build(p)
    for slug in LOTS:                        # a registry entry with nothing behind it
        os.makedirs(os.path.join(OUT, "registry", slug))


def env():
    # Demo projects only, and a grace short enough that a live commit flips a
    # project to STALE while the audience watches.
    return dict(os.environ, COC_REGISTRY=os.path.join(OUT, "registry"), COC_EXTRA_ROOTS="",
                COC_DRIFT_GRACE=str(GRACE))


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
    if "--serve" in sys.argv:
        # In this process, not a child: check() already imported coc with the
        # demo env, and a child outlived its parent when the parent was killed.
        import coc
        coc.serve()
