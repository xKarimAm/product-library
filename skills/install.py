"""Install the /library-checkpoint skill into Claude Code.

Copies skills/library-checkpoint/ to ~/.claude/skills/library-checkpoint/. Run it
again after a `git pull` to update the skill. Product Library itself never writes
to ~/.claude; this script does, once, because you ran it.
"""
import os
import shutil
import sys

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "library-checkpoint")
DEST = os.path.join(os.path.expanduser("~"), ".claude", "skills", "library-checkpoint")


def main():
    if not os.path.isfile(os.path.join(SRC, "SKILL.md")):
        sys.exit("install: no SKILL.md in %s" % SRC)
    # ponytail: copies over, never deletes; a file dropped from the skill upstream
    # would linger in the installed copy. Clear DEST first if the skill ever splits.
    shutil.copytree(SRC, DEST, dirs_exist_ok=True)
    print("Installed /library-checkpoint in %s" % DEST)
    print("Start a new Claude Code session, then type /library-checkpoint at the end of your work.")


if __name__ == "__main__":
    main()
