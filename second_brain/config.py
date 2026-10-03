"""Load brain.config.json over built-in defaults.

The loader never raises. A missing file is skipped silently; a file that does not parse, or a
value of the wrong type, produces one warning on stderr and falls back to the default, because
every caller is a hook that must not cost the user a prompt or a session.
"""
import copy
import json
import os
import sys
from pathlib import Path

BUILD_DIRS = [
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next",
    ".cache", "coverage", ".pytest_cache", ".turbo", "site-packages", ".obsidian",
]

DEFAULTS = {
    "vault": "~/second-brain",
    "projects_root": "~/code",
    "roots": {},
    "status": {
        "file": "STATUS.md",
        "labels": {"now": "Now", "next": "Next step"},
        "stale_days": 30,
        "prune_dirs": BUILD_DIRS + ["_archive", "_template"],
    },
    "capture": {
        "min_user_turns": 3,
    },
    "lookup": {
        "search_dirs": ["maps", "sessions"],
        "max_hits": 5,
        "min_keywords": 2,
        "timeout_seconds": 2.0,
        "extra_stopwords": [],
        "extra_acknowledgements": [],
        "log": None,
    },
    "librarian": {
        "sources": [],
        "extensions": [".pdf", ".docx", ".doc", ".rtf", ".odt", ".ods", ".odp", ".pptx", ".xlsx",
                       ".html", ".md", ".txt", ".csv"],
        "exclude_dirs": BUILD_DIRS,
        "excerpt_chars": 4000,
    },
    "domains": {},
}

DOMAIN_KEYS = {
    "summary": str,
    "projects": list,
    "folders": dict,
    "keywords": list,
    "neighbors": list,
    "curated": bool,
}

DEFAULTS_DOMAIN = {"summary": "", "projects": [], "folders": {}, "keywords": [],
                   "neighbors": [], "curated": False}

# Keys whose value is a filesystem path (or a list/dict of them) and gets ~ expanded.
PATH_KEYS = {("vault",), ("projects_root",), ("roots",), ("librarian", "sources"), ("lookup", "log")}

ENV_VAR = "SECOND_BRAIN_CONFIG"


def candidate_paths(env=None):
    env = os.environ if env is None else env
    paths = []
    if env.get(ENV_VAR):
        paths.append(Path(env[ENV_VAR]).expanduser())
    paths.append(Path("~/.config/second-brain/config.json").expanduser())
    paths.append(Path(__file__).resolve().parent.parent / "brain.config.json")
    return paths


def _stderr(msg):
    print(f"second-brain: {msg}", file=sys.stderr)


def _type_ok(default, value):
    if default is None:                       # optional path: null or a string
        return value is None or isinstance(value, str)
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(value, bool):               # bool is an int in Python; never a number here
        return False
    if isinstance(default, int):              # counts and limits: whole numbers only
        return isinstance(value, int)
    if isinstance(default, float):
        return isinstance(value, (int, float))
    if isinstance(default, list):             # every list in the config is a list of strings
        return isinstance(value, list) and all(isinstance(v, str) for v in value)
    if isinstance(default, dict) and not default:   # e.g. roots: name -> path
        return isinstance(value, dict) and all(isinstance(v, str) for v in value.values())
    return isinstance(value, type(default))


def _describe(default):
    if default is None:
        return "a string or null"
    if isinstance(default, bool):
        return "true or false"
    if isinstance(default, int):
        return "a whole number"
    if isinstance(default, float):
        return "a number"
    if isinstance(default, list):
        return "a list of strings"
    if isinstance(default, dict):
        return "an object"
    return "a string"


def _merge(defaults, user, where, warn):
    out = copy.deepcopy(defaults)
    for key, value in user.items():
        path = f"{where}.{key}" if where else key
        if key not in defaults:
            warn(f"unknown key '{path}' ignored")
            continue
        default = defaults[key]
        if isinstance(default, dict) and default and isinstance(value, dict):
            out[key] = _merge(default, value, path, warn)
        elif _type_ok(default, value):
            out[key] = copy.deepcopy(value)
        else:
            warn(f"'{path}' should be {_describe(default)}, got {json.dumps(value)[:60]}; using the default")
    return out


def _clean_domains(domains, warn):
    clean = {}
    for name, spec in domains.items():
        if not isinstance(spec, dict):
            warn(f"domain '{name}' should be an object; ignored")
            continue
        entry = copy.deepcopy(DEFAULTS_DOMAIN)
        for key, value in spec.items():
            want = DOMAIN_KEYS.get(key)
            where = f"domains.{name}.{key}"
            if want is None:
                warn(f"unknown key '{where}' ignored")
            elif want is list and not (isinstance(value, list) and all(isinstance(v, str) for v in value)):
                warn(f"'{where}' should be a list of strings; using the default")
            elif want is dict and not (isinstance(value, dict) and all(
                    isinstance(v, list) and all(isinstance(f, str) for f in v) for v in value.values())):
                warn(f"'{where}' should map each root name to a list of folder names; using the default")
            elif not isinstance(value, want):
                warn(f"'{where}' should be {_describe(DEFAULTS_DOMAIN[key])}; using the default")
            else:
                entry[key] = copy.deepcopy(value)
        entry["keywords"] = [k.lower() for k in entry["keywords"] if k.strip()]
        clean[name] = entry
    return clean


def _expand(value):
    if isinstance(value, str):
        return os.path.expanduser(value)
    if isinstance(value, list):
        return [_expand(v) for v in value]
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    return value


def load(path=None, env=None, warn=None):
    """Return the merged config as a plain dict. Never raises."""
    warn = warn or _stderr
    user, source = {}, None
    for candidate in ([Path(path).expanduser()] if path else candidate_paths(env)):
        if not candidate.is_file():
            continue
        try:
            parsed = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError, RecursionError) as exc:
            warn(f"could not read {candidate}: {exc}; trying the next location")
            continue
        if not isinstance(parsed, dict):
            warn(f"{candidate} is not a JSON object; trying the next location")
            continue
        user, source = parsed, str(candidate)
        break

    domains = user.pop("domains", {}) if isinstance(user.get("domains", {}), dict) else {}
    if "domains" in user:                     # present but not an object
        warn("'domains' should be an object; ignored")
        user.pop("domains")
    cfg = _merge(DEFAULTS, user, "", warn)
    cfg["domains"] = _clean_domains(domains, warn)

    for keys in PATH_KEYS:
        node = cfg
        for k in keys[:-1]:
            node = node[k]
        node[keys[-1]] = _expand(node[keys[-1]])
    _require_absolute(cfg, warn)
    cfg["_source"] = source
    return cfg


def _require_absolute(cfg, warn):
    """A relative path would resolve against whatever folder a hook happens to run in."""
    for key in ("vault", "projects_root"):
        if not os.path.isabs(cfg[key]):
            warn(f"'{key}' must be an absolute path or start with ~; using the default")
            cfg[key] = os.path.expanduser(DEFAULTS[key])
    for name, path in list(cfg["roots"].items()):
        if not os.path.isabs(path):
            warn(f"'roots.{name}' must be an absolute path or start with ~; ignored")
            del cfg["roots"][name]
    sources = cfg["librarian"]["sources"]
    if any(not os.path.isabs(p) for p in sources):
        warn("'librarian.sources' entries must be absolute paths or start with ~; relative ones ignored")
        cfg["librarian"]["sources"] = [p for p in sources if os.path.isabs(p)]
    if cfg["lookup"]["log"] and not os.path.isabs(cfg["lookup"]["log"]):
        warn("'lookup.log' must be an absolute path or start with ~; logging is off")
        cfg["lookup"]["log"] = None


def vault_path(cfg, *parts):
    return os.path.join(cfg["vault"], *parts)


if __name__ == "__main__":
    print(json.dumps(load(), indent=2, ensure_ascii=False))
