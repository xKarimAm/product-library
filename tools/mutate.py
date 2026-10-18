"""Break the code on purpose, one change at a time, and require the selftest to
notice. An assert nothing can break is decoration, not a test."""
import os
import shutil
import subprocess
import sys
import tempfile

BS = chr(92)
Q = chr(39)
SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "coc.py")
base = open(SRC, encoding="utf-8").read()

MUTS = [
    # --- original set -----------------------------------------------------
    ("cwd read from line 1 only",
     "    for rec in _jsonl_lines(head):",
     "    for rec in list(_jsonl_lines(head))[:1]:"),
    ("stop at newest transcript",
     "        if not prompts:\n            continue",
     "        if not prompts:\n            break"),
    ("locale encoding instead of utf-8",
     'with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:',
     'with open(path, "r", encoding="cp1252", errors="replace") as fh:'),
    ("BOM not tolerated (plain utf-8)",
     'with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:',
     'with open(path, "r", encoding="utf-8", errors="replace") as fh:'),
    ("append-only log read from HEAD",
     "        lines = tail_lines(fp, 400)",
     "        lines = read_text(fp).splitlines()[:400]"),
    ("stoplist disabled",
     "MIN_PROMPT_CHARS = 12",
     "STOPLIST = set()\nMIN_PROMPT_CHARS = 0"),
    ("frontmatter quotes not stripped",
     "        return val[1:-1]",
     "        return val"),
    ("block scalars not expanded",
     "        if val in BLOCK_SCALARS:",
     "        if False:"),
    ("'>' folds with newlines not spaces",
     '                val = " ".join(c for c in chunk if c).strip()',
     "                val = chr(10).join(c for c in chunk if c).strip()"),
    ("block sequence blockers ignored",
     '        elif val == "":',
     "        elif False:"),
    ("plain-doc fallback removed",
     "    state = parse_frontmatter(txt) or parse_plain_state(txt)",
     "    state = parse_frontmatter(txt)"),
    ("plain-doc runs past next heading",
     '        elif not fence and re.match(r"^#{1,4}' + BS + 's", line):',
     "        elif False:"),
    ("EXTRA_ROOTS dedupe removed",
     "        if norm in seen or not os.path.isdir(path):",
     "        if not os.path.isdir(path):"),
    ("git invented for non-repo",
     '    if not os.path.isdir(os.path.join(path, ".git")):\n        return None',
     "    if False:\n        return None"),
    ("trivial-only prompt dropped",
     "        return prompts[-1:], session_id, True",
     "        return [], session_id, True"),
    ("bubble payload loses next_action",
     '    out["next_action"] = st.get("next_action")',
     '    out["next_action"] = None'),
    ("long status offered as a badge",
     '    short = raw if raw and len(raw) <= 24 and "\\n" not in raw else None',
     "    short = raw or None"),

    # --- fixes from the independent review --------------------------------
    ("cache keyed on whole seconds",
     "    return (kind, os.path.normcase(path), st.st_mtime_ns, st.st_size)",
     "    return (kind, os.path.normcase(path), int(st.st_mtime), st.st_size)"),
    ("column-0 sequence dashes ignored",
     '                seq = re.match(r"^' + BS + 's*-' + BS + 's+(.*)$", body[i])',
     '                seq = re.match(r"^' + BS + 's+-' + BS + 's+(.*)$", body[i])'),
    ("indented --- ends the frontmatter",
     '    end = next((i for i in range(1, len(lines)) if lines[i].rstrip() == "---"), None)',
     '    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)'),
    ("wrapped quoted scalar not joined",
     '        elif val[:1] in ("' + BS + '"", "' + Q + '") and not _closed(val):',
     "        elif False:"),
    ("non-list blockers invent one",
     "    if isinstance(parsed, list):\n"
     "        return [str(x) for x in parsed if str(x).strip()]\n"
     "    return []",
     "    if isinstance(parsed, list):\n"
     "        return [str(x) for x in parsed if str(x).strip()]\n"
     "    return [str(parsed)]"),
    ("RESUME matches 'Resumed'",
     "(RESUME|NEXT ACTION|NEXT STEP|PICK UP)" + BS + 'b"',
     '(RESUME|NEXT ACTION|NEXT STEP|PICK UP)"'),
    ("first **Updated:** wins, not newest",
     '        "last_updated": max(stamps) if stamps else None,',
     '        "last_updated": stamps[0] if stamps else None,'),
    ("log heading not fence-aware",
     '        if not fence and re.match(r"^#{2,4}' + BS + 's", line):',
     '        if re.match(r"^## ", line):'),
    ("no escalation past a cut record",
     "        if not good and truncated_tail(path):",
     "        if False:"),
    ("cwd only from the newest transcript",
     "    for _mtime, _size, path in tx:\n"
     "        cwd, branch = resolve_cwd(path)",
     "    for _mtime, _size, path in tx[:1]:\n"
     "        cwd, branch = resolve_cwd(path)"),
    ("scan cache never expires",
     '            and now - _scan_cache["at"] < SCAN_TTL):',
     "            and True):"),
    ("duplicate paths not collapsed",
     '        if rec["path"]:\n'
     '            norm = os.path.normcase(os.path.abspath(rec["path"]))',
     "        if False:\n"
     '            norm = os.path.normcase(os.path.abspath(rec["path"]))'),
    ("duplicate ids allowed",
     '        while rec["id"] in ids:',
     "        while False:"),
    ("batch-file launcher accepted",
     '        if cand and os.path.isfile(cand) and not cand.lower().endswith((".cmd", ".bat")):',
     "        if cand and os.path.isfile(cand):"),
    # --- catalog card and quoted evidence ----------------------------------
    ("quote never checked",
     '             not rec.get("proof_unquoted")),',
     "             True),"),
    ("card never checked",
     '             _has_proof(st.get("for")) and _has_proof(st.get("bet"))),',
     "             True),"),
    ("card needs only one line",
     ' and _has_proof(st.get("bet"))),',
     ' or _has_proof(st.get("bet"))),'),
    ("quote may cite a file outside the project",
     "            inside = fp.startswith(root + os.sep)",
     "            inside = True"),
    ("wrapped quote not normalised",
     ' not in " ".join(body.split()):',
     " not in body:"),
    ("scan never checks quotes",
     '        rec["proof_unquoted"] = unverified_quotes(',
     '        rec["proof_unquoted"] = [] or (lambda *a: [])('),
    # --- story: origin, chapters, PRs --------------------------------------
    ("user's own title ignored",
     '        title = s["custom"] or s["ai"]',
     '        title = s["ai"]'),
    ("first ai-title wins, not the latest",
     '            out["ai"] = rec["aiTitle"]',
     '            out["ai"] = out["ai"] or rec["aiTitle"]'),
    ("origin taken from the newest session",
     "    for mtime, _size, path in reversed(tx):          # tx is newest first",
     "    for mtime, _size, path in tx:"),
    ("filler counts as the origin",
     '            first = next((p for p in s["prompts"] if is_substantive(p)), None)',
     '            first = next((p for p in s["prompts"] if p), None)'),
    ("non-https PR link kept",
     '        elif kind == "pr-link" and str(rec.get("prUrl") or "").startswith("https://"):',
     '        elif kind == "pr-link" and rec.get("prUrl"):'),
    ("duplicate PR links kept",
     '            if pr["url"] not in seen:',
     "            if True:"),
    ("story never built",
     '        rec["origin"], rec["chapters"], rec["prs"] = project_story(tx)',
     '        rec["origin"], rec["chapters"], rec["prs"] = None, [], []'),
    ("card dropped from the payload",
     '    out["bet"] = st.get("bet")',
     '    out["bet"] = None'),
    # --- checked proof ----------------------------------------------------
    ("cited commit never checked",
     '             not rec.get("proof_unknown")),',
     "             True),"),
    ("scan never asks the repo",
     '        rec["proof_unknown"] = unknown_commits(',
     '        rec["proof_unknown"] = [] or (lambda *a: [])('),
    ("tree hash accepted as a commit",
     'h + "^{commit}"]',
     "h]"),
    ("missing commit not reported",
     "            missing.append(h)",
     "            pass"),
    # --- truth boundary ---------------------------------------------------
    ("commit counted checked with no repo to ask",
     "for h in PROOF_COMMIT_RE.findall(val) if has_repo or h in unknown]",
     "for h in PROOF_COMMIT_RE.findall(val)]"),
    ("stale state counted as fresh",
     '"ok": not rec.get("drift")}]',
     '"ok": True}]'),
    ("misquote counted as true",
     '"ok": rel not in unquoted}',
     '"ok": True}'),
    ("cited field still listed as only written",
     "        if not cites:\n            written.append(label)",
     "        if True:\n            written.append(label)"),
    ("truth dropped from the payload",
     '    out["truth"] = rec.get("truth")',
     '    out["truth"] = None'),
]

tmp = tempfile.mkdtemp()
env = dict(os.environ, PYTHONIOENCODING="utf-8")
# selftest_checkpoint reads skills/ next to coc.py; without it every mutant
# "fails" for the wrong reason. The unmutated copy must pass first.
shutil.copytree(os.path.join(os.path.dirname(SRC), "skills"), os.path.join(tmp, "skills"))
open(os.path.join(tmp, "coc.py"), "w", encoding="utf-8").write(base)
if subprocess.run(["py", os.path.join(tmp, "coc.py"), "--selftest"], capture_output=True,
                  env=env).returncode != 0:
    sys.exit("baseline selftest fails in the temp copy; mutation results would be meaningless")
missing, survived = [], []
for name, old, new in MUTS:
    if old not in base:
        print("  ?? PATTERN NOT FOUND: " + name)
        missing.append(name)
        continue
    p = os.path.join(tmp, "coc.py")
    open(p, "w", encoding="utf-8").write(base.replace(old, new, 1))
    r = subprocess.run(["py", p, "--selftest"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    if r.returncode == 0:
        print("  SURVIVED (test is blind): " + name)
        survived.append(name)
    else:
        lines = [l for l in (r.stderr or "").strip().splitlines() if l.strip()]
        why = lines[-1][:104] if lines else "?"
        print(("  caught: " + name + "\n          -> " + why)
              .encode("ascii", "replace").decode())

shutil.rmtree(tmp, ignore_errors=True)
bad = len(missing) + len(survived)
print("")
print("%d/%d mutations caught" % (len(MUTS) - bad, len(MUTS)))
if survived:
    print("BLIND SPOTS: " + ", ".join(survived))
if missing:
    print("STALE PATTERNS: " + ", ".join(missing))
sys.exit(1 if bad else 0)
