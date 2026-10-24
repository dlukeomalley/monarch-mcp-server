---
name: eng-rig
description: Write, debug, refactor or review first-party code using the shared engineering standard, the project's checks, and independent review. Includes application code, scripts, tooling, notebooks and fleet-local helpers.
---

# Engineering workflow

Read the project's instructions, declared toolchain and
[shared engineering standard](references/engineering-standard.md) before designing
or editing code. Find the current owner and real callers. Preserve the task's scope,
existing edits and authorization; this skill grants no additional permissions.

Choose the smallest design justified by the task and surviving code. For a change
to a shared boundary or storage/protocol contract, record the design and challenge
it independently before implementation. Keep a mechanical edit mechanical.

For a behavioral defect, reproduce it through its actual owner before correction.
Keep the failing witness, fix or remove the responsible code, and check structural
twins. Use tests for required behavior, not as a reason to retain an unused API.
For unchanged behavior, run the checks relevant to the actual edit.

Use the project's pinned environment and existing type, lint, native test and
commit gates. If the project lacks a working gate or its dependencies, establish
that configuration explicitly; do not substitute a green neighboring checkout.
Fix findings at their owners and retain necessary third-party limits.

At a review checkpoint, use the installed eng-rig reviewer in an independent
read-only context against the candidate source. Follow the project's review command
and the runner's help. Inspect the returned findings and coverage, reproduce and
triage them, repair surviving issues, then rerun affected checks and review.
An exit-zero report, a timeout or an unread owner is not a clean review.

Keep executable work and its evidence at their owned project or artifact location.
Cite a stable source version and useful line ranges, or an artifact readers can
open. Report what changed, verified behavior, unresolved findings and coverage gaps.
If tooling or review is blocked, preserve the work and say what remains unchecked.
