"""Small helpers shared by every component: frontmatter, slugs, links and safe writes."""
import json
import os
import re
import secrets
import stat
import urllib.parse


def split_frontmatter(text):
    """Return (fields, body_lines). Reads the flat `key: value` subset of YAML these notes use."""
    lines = text.splitlines()
    fields = {}
    if not lines or lines[0].strip() != "---":
        return fields, lines
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return fields, lines[i + 1:]
        key, sep, value = line.partition(":")
        if not sep or not key.strip() or key.startswith((" ", "\t")):
            continue
        fields[key.strip()] = _scalar(value)
    return {}, lines                            # unterminated frontmatter: treat it all as body


def _scalar(value):
    value = value.strip()
    if value.startswith('"'):
        try:
            decoded, _end = json.JSONDecoder().raw_decode(value)
            if isinstance(decoded, str):
                return decoded
        except ValueError:
            pass
    elif value.startswith("'"):
        end = value.find("'", 1)
        if end > 0:
            return value[1:end]
    return re.split(r"\s+#", value, maxsplit=1)[0].strip()


def open_regular(path):
    """Open a regular file for reading as text. A FIFO, device or socket raises OSError instead
    of blocking the hook forever (O_NONBLOCK makes the open itself return at once)."""
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError(f"not a regular file: {path}")
        return os.fdopen(fd, encoding="utf-8", errors="replace")
    except BaseException:
        os.close(fd)
        raise


def read_text(path, limit):
    """At most `limit` characters of a regular file; '' for anything unreadable."""
    try:
        with open_regular(path) as f:
            return f.read(limit)
    except (OSError, ValueError):
        return ""


def read_frontmatter(path, limit=8192):
    return split_frontmatter(read_text(path, limit))[0]


def yaml_str(value):
    """A double-quoted YAML scalar. JSON string syntax is valid YAML and escapes everything."""
    return json.dumps(str(value), ensure_ascii=False)


def slug(text, limit=60):
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:limit].strip("-")
    return s or "untitled"


def safe_name(text, limit=80):
    """A single path component that keeps readable case: no separators, no dot-only names."""
    s = re.sub(r"[^\w.\- ]+", "-", text or "", flags=re.UNICODE).strip(" .-")[:limit]
    return s or "untitled"


def file_link(label, path):
    target = "file://" + urllib.parse.quote(os.path.abspath(path), safe="/:._-~")
    return f"[{md_text(label)}]({target})"


def md_text(text):
    """Text safe to put inside a Markdown link label or a table cell."""
    return re.sub(r"\s+", " ", str(text)).replace("|", "\\|").replace("[", "(").replace("]", ")").strip()


MARKER = "second-brain"
_DIR_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


def _open_parent(path, root):
    """A descriptor for the folder `path` goes in, reached one component at a time from `root`
    without following any symlink below it, creating missing folders. Raises OSError when a
    component is a symlink or the path leaves root. (`root` itself may be a symlink: that is the
    user's choice of where the vault lives.)"""
    rel = os.path.relpath(os.path.abspath(os.path.dirname(path)), os.path.abspath(root))
    if rel == os.pardir or rel.startswith(os.pardir + os.sep) or os.path.isabs(rel):
        raise OSError(f"outside the vault: {path}")
    fd = os.open(root, _DIR_FLAGS)
    try:
        for part in ([] if rel == os.curdir else rel.split(os.sep)):
            try:
                os.mkdir(part, 0o755, dir_fd=fd)
            except FileExistsError:
                pass
            child = os.open(part, _DIR_FLAGS | _NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _owned_at(dir_fd, name):
    try:
        st = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    except FileNotFoundError:
        return True
    if not stat.S_ISREG(st.st_mode):
        return False
    fd = os.open(name, os.O_RDONLY | _NOFOLLOW | getattr(os, "O_NONBLOCK", 0), dir_fd=dir_fd)
    with os.fdopen(fd, encoding="utf-8", errors="replace") as f:
        return split_frontmatter(f.read(8192))[0].get("generated") == MARKER


def owned(path):
    """True when the file does not exist yet or is a regular file carrying the marker."""
    folder, name = os.path.split(path)
    try:
        fd = os.open(folder, _DIR_FLAGS)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    try:
        return _owned_at(fd, name)
    except OSError:
        return False
    finally:
        os.close(fd)


def _replace(dir_fd, folder, tmp, name):
    if os.replace in os.supports_dir_fd:
        os.replace(tmp, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        return
    # No renameat here (CPython on macOS): rename by path. The temp file exists only in the
    # pinned folder, so if the path was swapped to point elsewhere the rename fails instead.
    if not os.path.samestat(os.stat(folder), os.fstat(dir_fd)):
        raise OSError(f"folder changed while writing: {folder}")
    os.replace(os.path.join(folder, tmp), os.path.join(folder, name))


def write_in_vault(path, content, root, require_owned=True):
    """Atomically write `path` inside `root`. With require_owned, only a missing file or one that
    carries the marker is replaced. Returns False, and writes nothing, when refused."""
    try:
        dir_fd = _open_parent(path, root)
    except OSError:
        return False
    try:
        name = os.path.basename(path)
        try:
            st = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
            if not stat.S_ISREG(st.st_mode):
                return False
        except FileNotFoundError:
            pass
        if require_owned and not _owned_at(dir_fd, name):
            return False
        tmp = f".tmp-{secrets.token_hex(8)}.md"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW, 0o644, dir_fd=dir_fd)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", errors="surrogateescape") as f:
                f.write(content)
            _replace(dir_fd, os.path.dirname(os.path.abspath(path)), tmp, name)
        except BaseException:
            try:
                os.unlink(tmp, dir_fd=dir_fd)
            except OSError:
                pass
            raise
        return True
    finally:
        os.close(dir_fd)


def write_owned(path, content, root):
    """Write a note this package owns, inside the vault. See write_in_vault."""
    try:
        return write_in_vault(path, content, root, require_owned=True)
    except OSError:
        return False


def remove_owned(path, root):
    """Delete a note only if it carries the marker and lies inside the vault."""
    try:
        dir_fd = _open_parent(path, root)
    except OSError:
        return False
    try:
        name = os.path.basename(path)
        if not os.path.lexists(path) or not _owned_at(dir_fd, name):
            return False
        os.unlink(name, dir_fd=dir_fd)
        return True
    except OSError:
        return False
    finally:
        os.close(dir_fd)


def is_within(path, root):
    try:
        return os.path.commonpath([os.path.realpath(path), os.path.realpath(root)]) == os.path.realpath(root)
    except ValueError:
        return False
