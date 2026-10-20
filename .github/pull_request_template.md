## Owning Issue / task

<!-- Link the owning Issue and related cross-repository Issues; priority and area. -->

## Base SHA / current full head SHA

<!-- Exact 40-character base/head IDs; recheck GitHub after changes. -->

## Problem, acceptance and scoped changes

<!-- State the measurable result, changed files and explicitly excluded work. -->

## Validation and negative cases

<!-- Local commands + actual results, not planned/assumed PASS. -->

## GitHub exact-head CI / Security / platforms

<!-- Links to actual runs at the current full head; Unknown is not PASS. -->

## Security, permissions and private data

<!-- No secrets or unauthorized device/prod changes; disclose new capabilities. -->

## Independent review, merge and rollback

<!-- Technical review is distinct from GitHub approval and owner merge authority. -->

## Remaining dependencies / follow-ups

## Project-specific mandatory checks

Assistant Hub: `PYTHONPATH=src python -m unittest discover -s tests -v`, `python -m compileall -q src tests scripts`, `PYTHONPATH=src python -m assistant_hub doctor`, `python scripts/check_public_tree.py --include-untracked`; Python 3.11/12/13 CI and offline Node UI checks. No private message/user data.

## Checklist

- [ ] Owning Issue and acceptance match the actual scope
- [ ] Diff and all new files inspected; unrelated work preserved
- [ ] Tests/negative cases done, or documentation-only exception explained
- [ ] Current full SHA and exact-head CI/Security/platform evidence recorded
- [ ] Existing stronger native gates preserved, not replaced by a smoke/no-op
- [ ] Secrets, user data, release/install/device access boundaries preserved
- [ ] Independent review and actual merge eligibility verified separately
- [ ] Known limitations, rollback and unverified evidence are explicit
