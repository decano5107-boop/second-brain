"""The hook scripts as Claude Code runs them: a subprocess, JSON on stdin, exit code 0 always."""
import json
import os
import subprocess
import sys

from tests.helpers import Sandbox, user

HOOKS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks")


class Hooks(Sandbox):
    def run_hook(self, name, stdin, config=None):
        env = {"PATH": os.environ.get("PATH", ""), "HOME": self.root,
               "SECOND_BRAIN_CONFIG": config or self.config_path}
        return subprocess.run([sys.executable, os.path.join(HOOKS, name)], input=stdin,
                              capture_output=True, text=True, env=env, timeout=30)

    def test_session_end_writes_the_note_and_the_board(self):
        os.makedirs(os.path.join(self.projects, "app"))
        event = {"cwd": os.path.join(self.projects, "app"), "session_id": "s1",
                 "transcript_path": self.transcript([user("a"), user("b"), user("c")])}
        result = self.run_hook("session_end.py", json.dumps(event))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(os.listdir(os.path.join(self.vault, "sessions"))), 1)
        self.assertTrue(os.path.exists(os.path.join(self.vault, "maps", "_BOARD.md")))

    def test_prompt_lookup_prints_json_only_when_it_has_something(self):
        self.write(os.path.join(self.vault, "maps", "Research.md"), "---\ntype: map\n---\ninterview synthesis\n")
        hit = self.run_hook("prompt_lookup.py", json.dumps({"prompt": "the interview synthesis please"}))
        miss = self.run_hook("prompt_lookup.py", json.dumps({"prompt": "unrelated words entirely here"}))
        self.assertEqual((hit.returncode, miss.returncode), (0, 0))
        self.assertIn("maps/Research.md", json.loads(hit.stdout)["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(miss.stdout, "")

    def test_garbage_input_and_broken_config_still_exit_zero_silently(self):
        broken = self.write(os.path.join(self.root, "broken.json"), "{")
        for name in ("session_end.py", "prompt_lookup.py"):
            for stdin in ("", "not json", "[1,2]", '{"prompt": 5, "cwd": 7, "transcript_path": []}'):
                result = self.run_hook(name, stdin, config=broken)
                self.assertEqual(result.returncode, 0, (name, stdin, result.stderr))
                self.assertEqual(result.stdout, "", (name, stdin))

    def test_the_plugin_manifest_points_at_real_scripts(self):
        with open(os.path.join(HOOKS, "hooks.json"), encoding="utf-8") as f:
            manifest = json.load(f)
        commands = [h["command"] for groups in manifest["hooks"].values() for g in groups for h in g["hooks"]]
        for command in commands:
            script = command.split("/hooks/", 1)[1].rstrip('"')
            self.assertTrue(os.path.isfile(os.path.join(HOOKS, script)), command)
