---
name: wrap-up
description: Close a work session in one step by writing the project's STATUS.md — what is true now, the next concrete action, where to start, and what blocks it — so the next session starts warm. Use when the user says they are done or leaving ("wrap up", "I'm done for today", "save where I left off", "close this out", "/wrap-up"). It records state only; it does no further project work.
---

# wrap-up — leave the project resumable

People stop working the moment they have what they wanted, and the state of the project leaves
with them. This skill turns "I'm done" into an up-to-date `STATUS.md`, the file every later
session reads first. The session note and the cross-project board are refreshed by the
`second-brain` hooks when the session ends; if the status file was updated today, the session
note copies its two main lines as its summary.

## 1. Find the project

- The project is the folder under the projects root where this session worked.
- Use the nearest status file (default name `STATUS.md`): in the working directory first, then
  each parent folder up to, but not including, the projects root.
- If the session touched several projects, update each one. If the project is still unclear
  from the conversation and the files edited, ask one question — "Which project should I
  close?" — and wait.
- If there is no status file yet, create one with the frontmatter and the four lines below.

## 2. Write the four lines from the conversation

You write them; do not ask the user to dictate them. Be terse and concrete.

- **Now:** what is true at the end of this session — what shipped, what was decided, what
  state things are in. One line.
- **Next step:** the next action someone could start in five minutes, with its object and, if
  known, its date. "Send the revised estimate to the client on Tuesday", never "continue".
- **Where:** the files, commands or links needed to start without searching.
- **Blocked by:** what stops progress, with who or what can unblock it, or "nothing".

If the user added context when asking to wrap up, it overrides your inference.

Use the labels the project already uses. The defaults are `Now` and `Next step`; a project can
use other labels (for example in another language) as long as they match `status.labels` in the
second-brain config, because those two lines are what the board and the session note read.

## 3. Update the file

- Keep the frontmatter. Set `updated:` to today's date (run `date +%F`), and change `status:`
  only if the project really changed state (`active`, `parked`, `reference` or `done`).
- Replace only the four labelled lines. Everything else in the file belongs to the user.
- Do not commit, push or run anything else.

## 4. Confirm in two lines

Show the **Now** and **Next step** lines you wrote, and say the board refreshes when the
session ends. If the user wants it refreshed right away, run
`python3 -m second_brain board` from the second-brain folder.
