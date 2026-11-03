# Initial repository review

Prepared from the custom bridge source for a private repository. No production
credential/config/state files, private chat exports or infrastructure inventories
are included. Owner approval and a verified destination are required before upload.

## Result

The original seven source/dependency files were compared by SHA256 with the live
bridge. All matched the reviewed baseline. A production check read 21 tasks from
each service, reported 0 persisted review items, and the existing 14 tests passed.
The timer remained active; no task data was changed by that check. The draft
fixes below are additional changes and have not been installed in production.

- 16 offline tests pass on both the local machine and the production Linux dependency
 environment (Python 3.13.5), covering merge conflicts, interrupted creates, missing
 counterparts, pagination and the new read-check regression cases.
- Example paths target a generic install directory; server addresses, actual
 project/view/list IDs and the original public information domain were removed.
- A dependency lock, setup/recovery instructions and credential exclusions are
 included. No automatic installer runs or changes a production system.
- No open-source license selected. Keep private pending an owner license decision.

## Fixes in this draft

The original `--check` could detect a new field conflict or missing task during
its scan but still report zero review items because it counted only issues already
persisted in SQLite. The draft counts those newly detected issues in memory without
writing either task service or changing the merge baseline. Two regression tests
prove those boundaries. Placeholder project/view IDs also fail before networking.

These changes are in the repository draft only. The running production bridge has
not been replaced by this draft. Validation of the existing worker is separate.

## Limits and follow-up

Conflict recovery remains manual. There is no notification service. Google Tasks
has no per-list OAuth grant, so app-level scope restrictions are essential. The
bridge deliberately does not synchronize deletion, attachments, recurrence,
subtasks or precise times. A fresh independent-account installation has not been
performed in this review; repeat the documented disposable-task validation before
using a new deployment with important tasks.

Production source hashes and live validation are recorded privately with the
owner's infrastructure evidence, not published in this generic repository.

## Fresh automated preparation

The local preparation service collected the approved live source on 2026-11-02T18:09:14.492504+00:00. Source hashes matched the reviewed baseline. It reproduced the reviewed fix, verified the dependency lock, parsed Python syntax, scanned private-data patterns and ran 16 offline tests with networking and credential paths isolated. Unknown source changes require a new review; this is not an autonomous semantic security audit. No upload was performed.
