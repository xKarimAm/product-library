## Summary

<!-- What problem does this solve? Link the issue with "Fixes #123" when there is one. -->

## Change and scope

<!-- The approach, and what is intentionally left out. -->

- [ ] Still read-only: nothing writes into a project folder or `~/.claude`.
- [ ] Still standard library only: no new dependency, no build step.
- [ ] Nothing personal: no real names, machine paths or real project scans.

## Evidence

<!-- List only commands that actually ran, with what you saw. For a fix, show the
failure before and the selftest case that now catches it. -->

- `python3 library.py --selftest`: result
- `python3 tools/leakcheck.py`: result
- Screenshot or other check (if the city looks different):

## Author readiness

<!-- The human owner fills this in. An AI agent must leave these boxes to a human.
See CONTRIBUTING.md. -->

Human owner: <!-- @GitHub-handle -->

- [ ] I reviewed the final diff, understand it and its edge cases, and take responsibility for it, including AI-assisted work.
- [ ] The evidence above is from this version of the change, and I noted what was not checked.
- [ ] This PR is ready for review.
