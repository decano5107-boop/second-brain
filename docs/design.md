# Design

## The problem

An agent that works across many projects forgets everything between sessions. The usual fixes
fail in one of two ways:

- **Nothing is written down.** Every session starts cold, and "where did I leave this?" is
  answered by scrolling old transcripts or by the model guessing.
- **Everything is written down, and nothing reads it.** Notes pile up in a folder, the agent
  never opens them, and it re-derives facts that already exist on disk.

`second-brain` closes both gaps with plain Markdown files and a handful of deterministic
scripts. There is no database, no embedding index, no network call and no model call: the
notes are files you can open in a text editor or an Obsidian vault. The only external programs
are optional text extractors for PDFs and legacy Word files.

## The loop

```
   work in a project ──► wrap-up ──► STATUS.md ──► board ──► _BOARD.md
          │                                                     │
          ▼                                                     │
   session ends ──► capture ──► sessions/<date>-<project>.md    │
                                        │                       │
   local documents ──► librarian ──► stubs/<domain>/*.md        │
                                        │                       │
   domain config ──► maps ──► maps/<domain>.md ◄────────────────┘
                                        │
   next prompt ──► lookup ──► greps maps/ + sessions/ ──► "you already wrote about this"
```

| Component | Runs on | Reads | Writes |
|---|---|---|---|
| `capture` | `SessionEnd` hook | the session transcript, and the nearest `STATUS.md` | one session note |
| `board` | `SessionEnd` hook, and on demand | every `STATUS.md` under the projects root | `maps/_BOARD.md` |
| `lookup` | `UserPromptSubmit` hook | `maps/` and `sessions/` | up to `max_hits` pointers into the prompt context; on disk, only the optional log |
| `librarian` | on demand, or a scheduled job | local documents (PDF, Office, Markdown, text) | one stub note per document, and a state file that records what it already read |
| `maps` | on demand, or a scheduled job | the `domains` section of the config, session notes and stubs | one map note per domain, and `maps/_INDEX.md` |
| `wrap-up` skill | when you say you are done | the conversation | the project's `STATUS.md`; the board follows at session end |

## Rules every component follows

1. **Fail open.** A hook exits 0 whatever happens: an exception inside it is swallowed, a broken
   config falls back to the defaults, and `lookup` stops searching when its time budget runs out
   and answers with what it found. Losing a note is acceptable; losing a prompt or a session is
   not.
2. **Silent when there is nothing to say.** `lookup` injects context only when a note clears a
   relevance bar. A pointer that fires on every prompt is noise the model learns to ignore.
3. **Deterministic and local.** No model calls, no quota, no network. The same inputs produce
   the same files, so a test can assert on them.
4. **Plain files are the interface, and yours stay yours.** Every note is Markdown with YAML
   frontmatter, and every note these scripts write carries `generated: second-brain`. No
   component overwrites or deletes a file without that line: delete it from a note to take the
   note over by hand. The only other files are the librarian's state file and the optional
   lookup log.
5. **One config, no code edits.** Paths, domains, keywords and thresholds live in
   `brain.config.json`. The code ships with defaults that work on an empty machine.

## Configuration

The config is looked for in this order, and the first file that parses wins:

1. the path in `SECOND_BRAIN_CONFIG`;
2. `~/.config/second-brain/config.json`;
3. `brain.config.json` at the root of this repository or plugin install.

A file that is missing is skipped silently; a file that exists but does not parse, or has a
value of the wrong type, is skipped or ignored with a warning on stderr for each problem, and
the defaults apply. Types are checked down to list elements: a count must be a whole number and every list
holds strings. Everything in the file is optional; unknown keys are ignored with a warning so a
typo does not pass unnoticed. Domain keywords are matched case-insensitively. See [`examples/brain.config.example.json`](../examples/brain.config.example.json).

| Key | Default | Used by |
|---|---|---|
| `vault` | `~/second-brain` | all |
| `projects_root` | `~/code` | `board`, `capture`, `maps`, `wrap-up` |
| `roots` | `{}` | `maps` (named folders a map can link into, e.g. `inbox`, `archive`) |
| `status.file` | `STATUS.md` | `board`, `capture`, `wrap-up` |
| `status.labels.now` / `.next` | `Now` / `Next step` | `board`, `capture`, `wrap-up` (the bold labels they read and write) |
| `status.stale_days` | `30` | `board` (an `active` project untouched this long shows as stale) |
| `status.prune_dirs` | build and dependency folders, plus `_archive` and `_template` | `board` |
| `capture.min_user_turns` | `3` | `capture` (shorter sessions that touched no file are skipped) |
| `lookup.search_dirs` | `["maps", "sessions"]` | `lookup` |
| `lookup.max_hits` | `5` | `lookup` |
| `lookup.min_keywords` | `2` | `lookup` (distinct keywords a note must match, unless it matches an acronym) |
| `lookup.timeout_seconds` | `2` | `lookup` |
| `lookup.extra_stopwords` | `[]` | `lookup` (words never used as keywords; the built-in list is English) |
| `lookup.extra_acknowledgements` | `[]` | `lookup` (words that make a prompt a bare acknowledgement, such as "ok thanks"; the built-in list is English) |
| `lookup.log` | `null` | `lookup` (a JSONL path to calibrate the relevance bar; off by default) |
| `librarian.sources` | `[]` | `librarian` (folders to index) |
| `librarian.extensions` | common document types | `librarian` |
| `librarian.exclude_dirs` | build and dependency folders | `librarian` |
| `librarian.excerpt_chars` | `4000` | `librarian` |
| `domains` | `{}` | `capture`, `librarian`, `maps` |

A **domain** is a topic you want a map for. Each one can declare:

```json
"Research": {
  "summary": "User interviews, surveys and synthesis.",
  "projects": ["interview-kit"],
  "folders":  {"archive": ["Research"], "inbox": ["interviews"]},
  "keywords": ["interview", "survey", "persona"],
  "neighbors": ["Client-Work"],
  "curated": false
}
```

- `projects` — project folder names; `capture` tags a session in one of them with this domain
  when the project's `STATUS.md` does not declare `domain:` itself.
- `folders` — folder names under a named root. `maps` links each one under its root; `librarian`
  files a document into this domain when any folder in the document's path has one of these
  names, whatever the root and whatever the case.
- `keywords` — when no folder decides, `librarian` files a document here if its path or text
  contains one. The first domain that matches wins, in config order.
- `neighbors` — maps link to each other, so the vault reads as a graph.
- `curated: true` — `maps` never overwrites this domain's map; you maintain it by hand.

## The `STATUS.md` contract

Each project keeps one status file at its root. A nested folder can have its own, and it
becomes its own row on the board; `capture` uses the nearest one at or above the working
directory, without leaving the projects root.

```markdown
---
project: trailhead-app
status: active        # active | parked | reference | done
updated: 2026-05-14
domain: Client-Work   # optional; overrides the domain's `projects` list
---

# trailhead-app

**Now:** onboarding flow shipped to the beta group; crash on Android 12 fixed.
**Next step:** read the first week of beta feedback and cut the settings screen.
```

Only the frontmatter and the two bold lines are parsed; the rest of the file is yours. The
labels come from `status.labels`, so a `STATUS.md` written in another language works unchanged.

## Decisions and their reasons

**Grep, not embeddings.** `lookup` runs on every prompt with a two-second budget. A keyword
grep over a few hundred Markdown files finishes in milliseconds, needs no index to keep fresh,
and its misses are explainable. Only content counts: a link matches by its label, never by its
target, and the headings and navigation lines of generated notes are template text that every
map shares, so they never match. The cost is recall on paraphrase; the relevance bar is tuned to
prefer silence over a wrong pointer.

**`lookup` does not search `stubs/` by default.** Stubs carry text extracted from documents
you did not write — downloads, attachments, other people's decks. Putting that text into the
model's context on every prompt is a prompt-injection path. Maps and session notes are written
by you or by these scripts. You can add `stubs` to `lookup.search_dirs`; the pointers are
labelled as data either way.

**`SessionEnd` work stays small.** Claude Code gives `SessionEnd` hooks a short time budget.
`capture` reads one transcript and writes one file; `board` walks the projects root with the
prune list and never opens anything but `STATUS.md`. Neither touches the network.

**Session notes are skeletons until the project says otherwise.** `capture` records what is
certain without a model: the date, the project, the files that were edited and the number of
turns. If the project's `STATUS.md` was updated today — which is what `wrap-up` does — its
`Now` and `Next step` lines become the note's summary. Otherwise the note is marked
`summary pending`, and `lookup` ignores it until someone writes a summary and removes the
marker, because a note with only metadata matches many prompts and says nothing.

**Nothing is created unasked.** Every component is a no-op until the vault folder exists;
`python3 -m second_brain init` creates it. Installing the hooks never makes a folder appear in
your home directory.

**Generated files are marked, and only marked files are overwritten.** A map you wrote, a
stub you annotated or a board you replaced by hand is never touched again, and a symlink
planted where a note should go is not followed. The cost: a document whose hand-edited stub is
kept gets a second, fresh stub if its domain changes. Files whose name starts with `_` (the
board and the index) list every project or domain, so they would match every prompt; `lookup`
skips them.

**Every input is bounded.** Notes, transcripts and documents can be planted by anyone who can
write a file on your disk, so nothing is trusted to be small or well-formed. Only regular files
are opened (a FIFO or a device never blocks a hook); every read has a byte cap; every line is cut
before a regular expression sees it, and the expressions are linear; the prompt is mined only in
its first few thousand characters; Office files are decompressed with a byte budget whatever
their headers claim; each pointer `lookup` injects is capped in length; and a write goes ahead
only if the folder it lands in is reached from the vault one component at a time without
following a symlink. Office parts compressed with anything but deflate are not read, and Office
files over 25 MB are indexed by name only. One residue: where Python cannot rename relative to a
folder descriptor (CPython on macOS), the final rename goes by path; a process that can rewrite
the vault while a hook runs has a window inside that single call. Paths in the
config must be absolute, because a relative one would resolve against whatever folder a hook
runs in.

**`STATUS.md` is the source, `_BOARD.md` is the mirror.** Each project owns its own state; the
board is regenerated from scratch and never edited by hand, so it cannot drift.

**Stale is computed, not declared.** A project marked `active` whose `updated:` date is older
than `status.stale_days` is shown as stale. Without this, every row on a board eventually says
"active" and the word stops meaning anything.

## Out of scope

- Summarising sessions with a model. The `wrap-up` skill does that inside the agent, where the
  conversation already is; the hooks stay deterministic.
- Syncing, sharing or encrypting the vault. It is a folder: use whatever you already use.
- Watching folders for new files. Run `librarian` from a scheduled job if you want that.
