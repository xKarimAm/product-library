"""Sync the public copy from private main in one command.

    py tools/sync_public.py -m "What changed" --words-file PATH   # check, sync, leakcheck, commit, push
    py tools/sync_public.py --dry-run --words-file PATH           # everything but the commit; changes nothing
    py tools/sync_public.py --selftest

The public repo gets the FILES of private main as one commit, never its history.
It refuses, before touching anything, when a sync could lose or leak something:

  - private is not on main, has uncommitted changes, or main is not pushed
  - public has uncommitted changes, or is not level with its origin
  - public holds work private main never had (someone pushed to public
    directly): a sync would delete it, so port it into private first
  - (PRIVATE_ONLY files, like the Dependabot config, are never copied)
  - there are no private words to check for (env LEAK_WORDS, or a
    --words-file with a LEAK_WORDS="a,b" line)

The commit is signed with the public clone's OWN git config (`git config --local`),
which must be a GitHub noreply address, and a UTC date. Never the global config. Public folder: env LIBRARY_PUBLIC_DIR, else ../product-library-public.
"""
import argparse
import io
import os
import re
import subprocess
import sys
import tarfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLIC = os.environ.get("LIBRARY_PUBLIC_DIR") or os.path.join(os.path.dirname(ROOT), "product-library-public")
# ponytail: files that live only in the public repo, kept through every sync. None today.
KEEP = set()
# Files that live only in private and never reach public: the Dependabot config,
# so its PRs open in private and arrive on public through a sync, never directly.
PRIVATE_ONLY = {".github/dependabot.yml"}
DEPTH = 300                 # how far back in private main a public sync point may be


def git(repo, *args, raw=False):
    r = subprocess.run(["git", "-C", repo] + list(args), capture_output=True)
    if r.returncode:
        sys.exit("git %s failed in %s:\n%s" % (" ".join(args), repo, r.stderr.decode(errors="replace")))
    return r.stdout if raw else r.stdout.decode("utf-8", "replace").strip()


def files(repo, rev):
    """{path: blob hash} at rev, minus KEEP and PRIVATE_ONLY. Blob hashes are
    content hashes, so the same file has the same hash in both repos."""
    out = {}
    for line in git(repo, "ls-tree", "-r", rev).splitlines():
        meta, path = line.split("\t", 1)
        if path not in KEEP and path not in PRIVATE_ONLY:
            out[path] = meta.split()[2]
    return out


def sync_point(public_files, private, depth=DEPTH):
    """The private main commit whose files public holds, or None: then public
    has work private never had."""
    for rev in git(private, "rev-list", "--first-parent", "-n", str(depth), "main").splitlines():
        if files(private, rev) == public_files:
            return rev
    return None


def leak_words(path):
    if os.environ.get("LEAK_WORDS", "").strip():
        return os.environ["LEAK_WORDS"]
    if path:
        with open(path, encoding="utf-8-sig") as fh:
            m = re.search(r'LEAK_WORDS="([^"]*)"', fh.read())
        if m and m.group(1).strip():
            return m.group(1)
    return ""


def identity(repo):
    """(name, email) from the repo's own config, or None. Only --local: the global
    config holds a real name. Only a noreply email, so no address ever leaks."""
    def get(key):
        r = subprocess.run(["git", "-C", repo, "config", "--local", "--get", key], capture_output=True, text=True)
        return r.stdout.strip()
    name, email = get("user.name"), get("user.email")
    return (name, email) if name and email.endswith("@users.noreply.github.com") else None


def prune_empty(root):
    """Remove folders a sync emptied (git tracks files, so they linger on disk)."""
    for d, subs, names in os.walk(root, topdown=False):
        if d != root and ".git" not in os.path.relpath(d, root).split(os.sep) and not os.listdir(d):
            os.rmdir(d)


def refuse(why):
    sys.exit("sync_public: " + why)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("-m", "--message", default="Sync from private main")
    ap.add_argument("--words-file", help='a file holding a LEAK_WORDS="a,b" line (kept outside every repo)')
    ap.add_argument("--dry-run", action="store_true", help="stop before the commit and put public back")
    args = ap.parse_args()

    words = leak_words(args.words_file)
    if not words:
        refuse("no private words. Set env LEAK_WORDS or pass --words-file.")
    if not os.path.isdir(os.path.join(PUBLIC, ".git")):
        refuse("no public clone at %s (env LIBRARY_PUBLIC_DIR)" % PUBLIC)

    if git(ROOT, "branch", "--show-current") != "main":
        refuse("private is not on main")
    if git(ROOT, "status", "--porcelain"):
        refuse("private has uncommitted changes")
    git(ROOT, "fetch", "-q")
    if git(ROOT, "rev-parse", "main") != git(ROOT, "rev-parse", "origin/main"):
        refuse("private main is not level with origin/main: push or pull first")

    who = identity(PUBLIC)
    if not who:
        refuse("the public clone has no noreply identity of its own. Set it once:\n"
               '  git -C "%s" config user.name <handle>\n'
               '  git -C "%s" config user.email <id>+<handle>@users.noreply.github.com' % (PUBLIC, PUBLIC))
    if git(PUBLIC, "status", "--porcelain"):
        refuse("public has uncommitted changes")
    git(PUBLIC, "fetch", "-q")
    if git(PUBLIC, "rev-parse", "HEAD") != git(PUBLIC, "rev-parse", "@{u}"):
        refuse("public is not level with its origin: pull it (and port any new work into private) first")
    at = sync_point(files(PUBLIC, "HEAD"), ROOT)
    if not at:
        refuse("public holds work private main never had (pushed to public directly?).\n"
               "Port it into private first, or this sync would delete it.")
    print("public matches private %s; syncing private main %s" % (at[:7], git(ROOT, "rev-parse", "--short", "main")))

    # Swap the tree: every tracked public file except KEEP goes, private main's files arrive.
    for rel in git(PUBLIC, "ls-files", "-z").split("\0"):
        if rel and rel not in KEEP:
            os.remove(os.path.join(PUBLIC, rel))
    with tarfile.open(fileobj=io.BytesIO(git(ROOT, "archive", "main", raw=True))) as tar:
        members = [m for m in tar.getmembers() if m.name not in PRIVATE_ONLY]
        try:
            tar.extractall(PUBLIC, members=members, filter="data")
        except TypeError:                     # Python before 3.12 has no filter
            tar.extractall(PUBLIC, members=members)
    prune_empty(PUBLIC)
    git(PUBLIC, "add", "-A")
    changed = git(PUBLIC, "diff", "--cached", "--name-status")
    if not changed:
        print("already in sync: nothing to commit")
        return
    print(changed)

    def put_back():                           # public was clean when we started
        git(PUBLIC, "reset", "-q", "--hard", "HEAD")

    check = subprocess.run([sys.executable, os.path.join("tools", "leakcheck.py")], cwd=PUBLIC,
                           env=dict(os.environ, LEAK_WORDS=words))
    if check.returncode:
        put_back()
        refuse("leakcheck failed (above). Public is back as it was; fix private and run again.")
    if args.dry_run:
        put_back()
        print("dry run: leakcheck OK, nothing committed, public is back as it was")
        return

    name, email = who
    env = dict(os.environ, TZ="UTC", GIT_AUTHOR_NAME=name, GIT_AUTHOR_EMAIL=email,
               GIT_COMMITTER_NAME=name, GIT_COMMITTER_EMAIL=email)
    r = subprocess.run(["git", "-C", PUBLIC, "commit", "-q", "-m", args.message], env=env)
    if r.returncode:
        refuse("commit failed")
    git(PUBLIC, "push", "-q")
    print("pushed public %s as %s <%s>" % (git(PUBLIC, "rev-parse", "--short", "HEAD"), name, email))


def selftest():
    """The guard is the point: a public repo with work private never had must
    be refused, a KEEP file must not count, and an older sync point must be found."""
    import shutil
    import tempfile
    root = tempfile.mkdtemp(prefix="library-sync-")
    priv, pub = os.path.join(root, "priv"), os.path.join(root, "pub")
    KEEP.add("PUBLIC-ONLY.md")

    def write(repo, rel, text):
        with open(os.path.join(repo, rel), "w", encoding="utf-8") as fh:
            fh.write(text)

    def commit(repo, msg):
        git(repo, "add", "-A")
        git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", msg)

    for repo in (priv, pub):
        os.makedirs(repo)
        git(repo, "init", "-q", "-b", "main")
    write(priv, "a.txt", "one\n")
    commit(priv, "A")
    write(pub, "a.txt", "one\n")
    write(pub, "PUBLIC-ONLY.md", "public only\n")
    commit(pub, "sync A")
    write(priv, "a.txt", "two\n")
    os.makedirs(os.path.join(priv, ".github"))
    write(priv, ".github/dependabot.yml", "private only\n")
    commit(priv, "B")
    assert ".github/dependabot.yml" not in files(priv, "main"), "a PRIVATE_ONLY file counted"
    a = git(priv, "rev-parse", "main~1")
    assert sync_point(files(pub, "HEAD"), priv) == a, "an older sync point was not found"
    write(pub, "a.txt", "edited on public\n")
    commit(pub, "direct push")
    assert sync_point(files(pub, "HEAD"), priv) is None, "work only on public was not refused"
    os.environ.pop("LEAK_WORDS", None)
    wf = os.path.join(root, "words.md")
    write(root, "words.md", 'x\n$env:LEAK_WORDS="a b,c"; py tools/leakcheck.py\n')
    assert leak_words(wf) == "a b,c", leak_words(wf)
    assert leak_words(None) == ""
    assert identity(pub) is None, "signed without a local identity"
    git(pub, "config", "user.name", "someone")
    git(pub, "config", "user.email", "someone@example.com")
    assert identity(pub) is None, "a personal email was accepted"
    git(pub, "config", "user.email", "1+someone@users.noreply.github.com")
    assert identity(pub) == ("someone", "1+someone@users.noreply.github.com"), identity(pub)
    os.makedirs(os.path.join(pub, "gone", "deeper"))
    os.makedirs(os.path.join(pub, "kept"))
    write(pub, "kept/x.txt", "x\n")
    prune_empty(pub)
    assert not os.path.exists(os.path.join(pub, "gone")), "an emptied folder was left"
    assert os.path.isfile(os.path.join(pub, "kept", "x.txt")) and os.path.isdir(os.path.join(pub, ".git", "objects"))
    KEEP.discard("PUBLIC-ONLY.md")
    shutil.rmtree(root, ignore_errors=True)
    print("sync_public selftest OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        main()
