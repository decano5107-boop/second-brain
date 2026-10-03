"""SessionEnd: write a session note — date, project, domain, files edited, turn count.

Deterministic: nothing here calls a model. When the project's status file was updated today
(the `wrap-up` skill does that), its two labelled lines become the note's summary. Otherwise the
summary is left as a marker that `lookup` recognises, so a note with nothing but metadata never
shows up as a pointer.
"""
import datetime
import json
import os
import re

from . import notes

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
PENDING = "summary pending"
SUMMARY_CHARS = 500
# User records that the harness injects rather than the person typing.
INJECTED = ("<command-", "<local-command", "<system-reminder>", "<task-notification>",
            "Caveat: The messages below", "[Request interrupted")


def _user_text(message):
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        return "\n".join(texts) if texts else None
    return None


def read_transcript(path, max_bytes=200 * 1024 * 1024):
    """Return (user_turns, edited_files). Unreadable lines and files are skipped, never raised."""
    turns, files = 0, set()
    try:
        f = notes.open_regular(path)                # never a FIFO or /dev/zero
        if os.fstat(f.fileno()).st_size > max_bytes:
            f.close()
            return turns, files
    except (OSError, ValueError, TypeError):
        return turns, files
    with f:
        for line in f:
            try:
                record = json.loads(line)
            except (ValueError, RecursionError):
                continue
            if not isinstance(record, dict) or record.get("isSidechain") or record.get("isMeta"):
                continue
            message = record.get("message") if isinstance(record.get("message"), dict) else {}
            if record.get("type") == "user":
                text = _user_text(message)
                if text is not None and text.strip() and not text.lstrip().startswith(INJECTED):
                    turns += 1
            elif record.get("type") == "assistant":
                for block in message.get("content") or []:
                    if (isinstance(block, dict) and block.get("type") == "tool_use"
                            and block.get("name") in EDIT_TOOLS):
                        tool_input = block.get("input") or {}
                        target = tool_input.get("file_path") or tool_input.get("notebook_path")
                        if isinstance(target, str) and target:
                            files.add(target)
    return turns, files


def find_status(cwd, cfg):
    """The nearest STATUS.md at or above cwd, without leaving the projects root."""
    root = cfg["projects_root"]
    here = os.path.abspath(cwd)
    inside = notes.is_within(here, root)
    for _ in range(12):
        candidate = os.path.join(here, cfg["status"]["file"])
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(here)
        if not inside or parent == here or not notes.is_within(parent, root):
            return None
        here = parent
    return None


def resolve_domain(cwd, status_path, cfg):
    if status_path:
        declared = notes.read_frontmatter(status_path).get("domain", "")
        if declared:
            return declared
    names = []
    here = os.path.abspath(cwd)
    while True:
        names.append(os.path.basename(here))
        parent = os.path.dirname(here)
        if parent == here or not notes.is_within(parent, cfg["projects_root"]) \
                or os.path.realpath(parent) == os.path.realpath(cfg["projects_root"]):
            break
        here = parent
    for name in names:                          # the innermost folder that a domain claims
        for domain, spec in cfg["domains"].items():
            if name in spec["projects"]:
                return domain
    return ""


MAX_PROJECT = 80


def project_name(cwd, status_path):
    name = ""
    if status_path:
        name = str(notes.read_frontmatter(status_path).get("project", "")) \
            or os.path.basename(os.path.dirname(status_path))
    name = name or os.path.basename(os.path.abspath(cwd).rstrip(os.sep)) or "session"
    return notes.md_text(name)[:MAX_PROJECT]


def status_summary(status_path, cfg, today):
    """The status file's Now / Next lines, if it was updated today; else []."""
    if not status_path:
        return []
    fields, body = notes.split_frontmatter(notes.read_text(status_path, 64 * 1024))
    if str(fields.get("updated", ""))[:10] != today:
        return []
    labels = cfg["status"]["labels"]
    lines = []
    for label in (labels["now"], labels["next"]):
        prefix = f"**{label}:**"
        text = next((ln.strip()[len(prefix):].strip() for ln in body if ln.strip().startswith(prefix)), "")
        if text:
            lines.append(f"- **{notes.md_text(label)}:** {text[:SUMMARY_CHARS]}")
    return lines


def render(today, project, domain, session_id, turns, files, transcript, summary=()):
    listed = "\n".join(f"- {notes.file_link(os.path.basename(f) or f, f)}" for f in sorted(files))
    lines = [
        "---",
        "type: session",
        f"generated: {notes.MARKER}",
        f"date: {today}",
        f"project: {notes.yaml_str(project)}",
        f"domain: {notes.yaml_str(domain)}",
        f"session_id: {session_id}",
        f"turns: {turns}",
        "tags: [session]",
        "---",
        "",
        f"# {today} · {notes.md_text(project)}",
        "",
        f"## Files edited ({len(files)})",
        listed or "_(none)_",
        "",
        "## Summary",
        *(summary or [f"- _({PENDING} · {turns} user turns)_"]),
        "",
        "## Links",
    ]
    if transcript:
        lines.append(f"- {notes.file_link('transcript', transcript)}")
    if domain:
        lines.append(f"- Map: [[{notes.safe_name(domain)}]]")
    return "\n".join(lines) + "\n"


def run(event, cfg, today=None):
    """Write the note for one SessionEnd event. Returns its path, or None when skipped."""
    vault = cfg["vault"]
    if not os.path.isdir(vault):                # no vault yet: never create folders unasked
        return None
    cwd = event.get("cwd") if isinstance(event.get("cwd"), str) and event.get("cwd") else os.getcwd()
    transcript = event.get("transcript_path") if isinstance(event.get("transcript_path"), str) else ""
    turns, files = read_transcript(transcript)
    if turns < cfg["capture"]["min_user_turns"] and not files:
        return None

    status_path = find_status(cwd, cfg)
    project = project_name(cwd, status_path)
    domain = resolve_domain(cwd, status_path, cfg)
    session_id = re.sub(r"[^0-9A-Za-z]", "", str(event.get("session_id") or ""))[:8] or "nosession"
    today = today or datetime.date.today().isoformat()

    out = os.path.join(vault, "sessions", f"{today}-{notes.slug(project)}-{session_id}.md")
    summary = status_summary(status_path, cfg, today)
    written = notes.write_owned(out, render(today, project, domain, session_id, turns, files,
                                            transcript, summary), vault)
    return out if written else None
