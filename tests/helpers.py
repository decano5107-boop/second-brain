"""A throwaway machine per test: a vault, a projects root and a config pointing at both."""
import json
import os
import tempfile
import textwrap
import unittest

from second_brain import config


class Sandbox(unittest.TestCase):
    domains = {}
    overrides = {}

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self._tmp.name)
        self.vault = os.path.join(self.root, "vault")
        self.projects = os.path.join(self.root, "code")
        for sub in ("maps", "sessions", "stubs"):
            os.makedirs(os.path.join(self.vault, sub))
        os.makedirs(self.projects)
        raw = {"vault": self.vault, "projects_root": self.projects, "domains": self.domains}
        for key, value in self.overrides.items():
            raw[key] = value
        self.config_path = self.write(os.path.join(self.root, "config.json"), json.dumps(raw))
        self.warnings = []
        self.cfg = config.load(path=self.config_path, warn=self.warnings.append)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, path, content, mode="w"):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, mode, **({} if "b" in mode else {"encoding": "utf-8"})) as f:
            f.write(textwrap.dedent(content) if isinstance(content, str) else content)
        return path

    def read(self, path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    def status(self, folder, now="", nxt="", **fields):
        front = "".join(f"{k}: {v}\n" for k, v in fields.items())
        body = f"---\n{front}---\n\n# {folder}\n\n**Now:** {now}\n**Next step:** {nxt}\n"
        return self.write(os.path.join(self.projects, folder, "STATUS.md"), body)

    def transcript(self, records):
        path = os.path.join(self.root, "t.jsonl")
        self.write(path, "\n".join(r if isinstance(r, str) else json.dumps(r) for r in records) + "\n")
        return path


def user(text, **extra):
    return {"type": "user", "message": {"role": "user", "content": text}, **extra}


def edit(path, tool="Edit"):
    key = "notebook_path" if tool == "NotebookEdit" else "file_path"
    return {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "name": tool, "input": {key: path}}]}}
