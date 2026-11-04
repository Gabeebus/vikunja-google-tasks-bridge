# Bridge validation review

The updated setup was tested on Debian 13 with Python 3.13 and Vikunja v2.7.1,
using a separate Google test account and a disposable local Vikunja instance.
No production credentials, task data, configuration, chat exports or inventories
are included in this repository.

## Verified

- Anonymous public clone and pull, dependency installation, and the original 24 offline tests on Linux.
- The expanded 27-test suite passes locally, including three rich-description regressions; a fresh source-bound Linux worker receipt is required before publishing this revision.
- Dedicated non-login service user, private configuration and credential ownership.
- Fresh Google authorization and offline token refresh; five dedicated task lists.
- Actual manual CLI runs and the systemd service/timer using the test accounts.
- Titles, notes, date-only due dates and column changes in both directions.
- Completion, reopening, new task import, and unchanged reruns without duplicates
  or changes to either service's update timestamps (two disposable tasks).

## Corrections prepared

The README now includes public cloning, prerequisites, the virtualenv authorization
command, private writable configuration, and complete service setup. Bootstrap
checks all list-name collisions before creation and resumes interrupted creation.
Private JSON saves use unique temporary files and atomic replacement. Authorization
timeouts give a readable recovery message without saving a token. First registration
now preserves existing Vikunja HTML and appends only the sync marker. Title changes
preserve registered rich notes; intentional Google notes edits remain plain text.

## Limits

These checks cover the tested versions and a small disposable workload. They do
not establish compatibility with every deployment or constitute a security audit.
Deletion, attachments, recurrence, subtasks and precise due times are not synced.
Google Tasks authorization is account-wide; the configured list restriction is
an application boundary. Conflict recovery remains manual.

The repository is public. No open-source license has been selected. Production
installation of these corrections and uploading the reviewed update are separate
owner-controlled actions. Screenshots require separate review before publication.
