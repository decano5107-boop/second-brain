"""Regenerate maps/_BOARD.md from every STATUS.md under the projects root.

The board is a mirror, never a source: it is rebuilt from scratch on every run, so editing it
by hand is pointless and it cannot drift from the projects it describes.
"""
import datetime
import os

from . import notes

BOARD = "_BOARD.md"
ORDER = {"active": 0, "stale": 1, "reference": 2, "parked": 3, "done": 4}
ICON = {"active": "🟢", "stale": "🟡", "reference": "📘", "parked": "⏸️", "done": "✅"}
CELL = 160


def status_files(cfg):
    root = cfg["projects_root"]
    prune = set(cfg["status"]["prune_dirs"])
    name = cfg["status"]["file"]
    for folder, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in prune and not d.startswith("."))
        if name in files and os.path.isfile(os.path.join(folder, name)):   # no FIFOs or devices
            yield os.path.join(folder, name)


def labelled_line(body, label):
    prefix = f"**{label}:**"
    for line in body:
        text = line.strip()
        if text.startswith(prefix):
            return text[len(prefix):].strip()
    return ""


def parse(path, cfg):
    text = notes.read_text(path, 64 * 1024)
    if not text:
        return None
    fields, body = notes.split_frontmatter(text)
    folder = os.path.dirname(path)
    rel = os.path.relpath(folder, cfg["projects_root"])
    updated = fields.get("updated", "")
    if not _date(updated):
        updated = datetime.date.fromtimestamp(os.path.getmtime(path)).isoformat()
    return {
        "dir": folder,
        "project": fields.get("project") or (os.path.basename(folder) if rel == "." else rel),
        "status": (fields.get("status") or "active").lower(),
        "updated": updated[:10],
        "now": labelled_line(body, cfg["status"]["labels"]["now"]),
        "next": labelled_line(body, cfg["status"]["labels"]["next"]),
    }


def _date(text):
    try:
        return datetime.date.fromisoformat(str(text)[:10])
    except ValueError:
        return None


def effective_status(row, today, stale_days):
    if row["status"] == "active":
        updated = _date(row["updated"])
        if updated and (today - updated).days > stale_days:
            return "stale"
    return row["status"]


def build(cfg, today=None):
    today = today or datetime.date.today()
    rows = []
    for path in status_files(cfg):
        row = parse(path, cfg)
        if row:
            row["status"] = effective_status(row, today, cfg["status"]["stale_days"])
            rows.append(row)
    rows.sort(key=lambda r: r["project"].lower())
    rows.sort(key=lambda r: r["updated"], reverse=True)
    rows.sort(key=lambda r: ORDER.get(r["status"], len(ORDER)))

    labels = cfg["status"]["labels"]
    out = [
        "---", "type: board", f"generated: {notes.MARKER}", f"updated: {today.isoformat()}", "tags: [board]", "---", "",
        "# Board", "",
        f"> Generated from every `{cfg['status']['file']}` under the projects root on "
        f"{today.isoformat()}. Edit the projects, not this file.", "",
        f"| Status | Project | {notes.md_text(labels['now'])} | {notes.md_text(labels['next'])} | Updated |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        out.append("| {} {} | {} | {} | {} | {} |".format(
            ICON.get(r["status"], "•"), notes.md_text(r["status"]),
            notes.file_link(r["project"], r["dir"]),
            notes.md_text(r["now"])[:CELL], notes.md_text(r["next"])[:CELL], r["updated"]))
    out += ["", f"_{len(rows)} projects._", ""]
    return "\n".join(out)


def write(cfg, today=None):
    """Rebuild the board. Returns its path, or None when there is no vault or the file there
    was not written by second-brain."""
    if not os.path.isdir(cfg["vault"]):
        return None
    path = os.path.join(cfg["vault"], "maps", BOARD)
    return path if notes.write_owned(path, build(cfg, today), cfg["vault"]) else None
