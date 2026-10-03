"""Turn local documents into searchable stub notes, without moving them.

Each stub holds the document's path, size, date, domain and the first few thousand characters
of its text. Extraction is local: the standard library reads Office Open XML and OpenDocument
files directly; PDFs need `pdftotext` (poppler), and legacy .doc/.rtf need macOS `textutil`.
When a tool is missing, the stub is still written and stays findable by name and path.
"""
import datetime
import hashlib
import html
import os
import re
import shutil
import subprocess
import zipfile

from . import notes

STATE = os.path.join(".second-brain", "librarian-state.tsv")
UNSORTED = "Unsorted"
MAX_BYTES = 100 * 1024 * 1024
TEMP_SUFFIXES = (".crdownload", ".part", ".tmp", ".download")
RX_TAG = re.compile(r"<[^<>]*>")           # stops at the next '<', so it stays linear
MEMBER_BYTES = 4 * 1024 * 1024               # read cap per XML part, whatever its header claims
TOTAL_BYTES = 8 * 1024 * 1024


def _run(cmd, timeout=40):
    if not shutil.which(cmd[0]):
        return ""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, errors="replace",
                              timeout=timeout).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _zip_text(path, want, limit=60, key=None):
    """Text of the matching XML parts. Reads are capped in decompressed bytes, so a part that
    lies about its size in the zip header cannot expand without bound."""
    with zipfile.ZipFile(path) as z:
        names = sorted((n for n in z.namelist() if want(n)), key=key)[:limit]
        parts, budget = [], TOTAL_BYTES
        for name in names:
            if budget <= 0:
                break
            if z.getinfo(name).compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                continue                         # Office uses deflate; other codecs ignore read caps
            with z.open(name) as member:
                raw = member.read(min(MEMBER_BYTES, budget))
            budget -= len(raw)
            xml = raw.decode("utf-8", "replace")
            xml = re.sub(r"</(w:p|a:p|text:p|si|row)>", "\n", xml)
            parts.append(html.unescape(RX_TAG.sub(" ", xml)))
        return "\n".join(parts)


def _slide_order(name):
    m = re.search(r"(\d+)\.xml$", name)
    return int(m.group(1)) if m else 0


ZIP_FORMATS = {".docx", ".pptx", ".xlsx", ".odt", ".ods", ".odp"}
MAX_ZIP_BYTES = 25 * 1024 * 1024             # parsing a zip's directory costs memory per entry


def extract(path, max_chars):
    """Best-effort plain text. Never raises; returns '' when nothing can be read."""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in ZIP_FORMATS and os.path.getsize(path) > MAX_ZIP_BYTES:
            return ""                            # still indexed, by name and path
        if ext in {".md", ".txt", ".csv"}:
            return notes.read_text(path, max_chars * 2)
        if ext in {".html", ".htm"}:
            raw = notes.read_text(path, max_chars * 8)
            raw = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", raw)
            return html.unescape(RX_TAG.sub(" ", raw))
        if ext == ".docx":
            return _zip_text(path, lambda n: n == "word/document.xml")
        if ext == ".pptx":
            return _zip_text(path, lambda n: re.fullmatch(r"ppt/slides/slide\d+\.xml", n) is not None,
                             key=_slide_order)
        if ext == ".xlsx":
            return _zip_text(path, lambda n: n == "xl/sharedStrings.xml")
        if ext in {".odt", ".ods", ".odp"}:
            return _zip_text(path, lambda n: n == "content.xml")
        if ext == ".pdf":
            return _run(["pdftotext", "-q", "-l", "8", path, "-"])
        if ext in {".doc", ".rtf"}:
            return _run(["textutil", "-convert", "txt", "-stdout", path])
    except (OSError, zipfile.BadZipFile, KeyError, ValueError, RuntimeError):
        return ""
    return ""


def guess_domain(path, text, cfg):
    """A folder a domain claims beats keywords; keywords go in config order; else Unsorted."""
    parts = [p.lower() for p in os.path.normpath(path).split(os.sep)]
    for domain, spec in cfg["domains"].items():
        claimed = {f.lower() for names in spec["folders"].values() for f in names}
        if claimed & set(parts[:-1]):
            return domain
    blob = " " + re.sub(r"\s+", " ", f"{path} {text}".lower()) + " "
    for domain, spec in cfg["domains"].items():
        if any(k in blob for k in spec["keywords"]):
            return domain
    return UNSORTED


def is_document(path, cfg):
    name = os.path.basename(path)
    if name.startswith((".", "~$")) or name.lower().endswith(TEMP_SUFFIXES):
        return False
    if os.path.splitext(name)[1].lower() not in cfg["librarian"]["extensions"]:
        return False
    try:
        return os.path.isfile(path) and not os.path.islink(path) and os.path.getsize(path) <= MAX_BYTES
    except OSError:
        return False


def render(path, cfg):
    limit = cfg["librarian"]["excerpt_chars"]
    text = extract(path, limit)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    domain = guess_domain(path, text, cfg)
    stat = os.stat(path)
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    size_kb = max(1, round(stat.st_size / 1024))
    excerpt = text[:limit].strip() or "_(no extractable text — findable by name and path)_"
    body = "\n".join([
        "---",
        "type: stub",
        f"generated: {notes.MARKER}",
        f"title: {notes.yaml_str(os.path.basename(path))}",
        f"domain: {notes.yaml_str(domain)}",
        f"filetype: {ext or 'file'}",
        f"size_kb: {size_kb}",
        f"source: {notes.yaml_str(path)}",
        f"modified: {datetime.date.fromtimestamp(stat.st_mtime).isoformat()}",
        "tags: [stub]",
        "---",
        "",
        f"# {notes.md_text(os.path.basename(path))}",
        "",
        f"{notes.file_link('Open the file', path)} · `{ext}` · {size_kb} KB · [[{notes.safe_name(domain)}]]",
        "",
        "## Excerpt",
        "",
        "```text",
        excerpt.replace("```", "'''"),
        "```",
        "",
    ])
    return domain, body


def stub_path(path, domain, cfg):
    digest = hashlib.sha1(os.path.abspath(path).encode("utf-8", "surrogateescape")).hexdigest()[:8]
    name = notes.slug(os.path.splitext(os.path.basename(path))[0], 50)
    return os.path.join(cfg["vault"], "stubs", notes.safe_name(domain), f"{name}-{digest}.md")


def load_state(cfg):
    state = {}
    try:
        with notes.open_regular(os.path.join(cfg["vault"], STATE)) as f:
            for line in f:
                path, sep, stamp = line.rstrip("\n").rpartition("\t")
                if sep:
                    state[path] = stamp
    except OSError:
        pass
    return state


def save_state(cfg, state):
    target = os.path.join(cfg["vault"], STATE)
    body = "".join(f"{path}\t{stamp}\n" for path, stamp in sorted(state.items()))
    if not notes.write_in_vault(target, body, cfg["vault"], require_owned=False):
        raise OSError(f"refusing to write the librarian state: {target} is not a regular file in the vault")


def walk(folders, cfg):
    excluded = set(cfg["librarian"]["exclude_dirs"])
    vault = os.path.realpath(cfg["vault"])
    for top in folders:
        for folder, dirs, files in os.walk(top):
            dirs[:] = sorted(d for d in dirs if d not in excluded and not d.startswith(".")
                             and os.path.realpath(os.path.join(folder, d)) != vault)
            for name in sorted(files):
                yield os.path.join(folder, name)


def process(paths, cfg, log=print):
    """Write or refresh a stub for each changed document. Returns how many were written."""
    if not os.path.isdir(cfg["vault"]):
        log(f"no vault at {cfg['vault']}; run `python3 -m second_brain init` first")
        return 0
    state = load_state(cfg)
    written = 0
    for raw in paths:
        path = os.path.abspath(raw)
        if notes.is_within(path, cfg["vault"]) or not is_document(path, cfg):
            continue
        stamp = f"{os.path.getmtime(path)}:{os.path.getsize(path)}"
        if state.get(path) == stamp:
            continue
        try:
            domain, body = render(path, cfg)
            target = stub_path(path, domain, cfg)
            if not notes.write_owned(target, body, cfg["vault"]):
                log(f"  = {path}: its stub is not owned by second-brain or not inside the vault; left as is")
                continue
            for old in _stale_copies(path, target, cfg):
                notes.remove_owned(old, cfg["vault"])
        except (OSError, ValueError) as exc:
            log(f"  ! skipped {path}: {exc}")
            continue
        state[path] = stamp
        written += 1
        log(f"  + [{domain}] {os.path.basename(path)}")
    save_state(cfg, state)
    return written


def _stale_copies(path, target, cfg):
    """A document whose domain changed leaves its old stub behind; find it by the path hash."""
    suffix = os.path.basename(target)
    root = os.path.join(cfg["vault"], "stubs")
    if not os.path.isdir(root):
        return []
    found = []
    for domain_dir in os.listdir(root):
        candidate = os.path.join(root, domain_dir, suffix)
        if candidate != target and os.path.isfile(candidate):
            found.append(candidate)
    return found
