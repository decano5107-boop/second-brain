"""The shipped demo is the README's first impression; it has to run clean on a new machine."""
import contextlib
import importlib.util
import io
import os
import tempfile
import unittest

from second_brain import lookup

RUN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples", "demo", "run.py")


class Demo(unittest.TestCase):
    def test_demo_builds_a_vault_and_the_lookups_behave(self):
        spec = importlib.util.spec_from_file_location("demo_run", RUN)
        demo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(demo)
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()) as out:
            cfg = demo.main(["run.py", os.path.join(tmp, "demo")])
            names = sorted(os.listdir(os.path.join(cfg["vault"], "maps")))
            sessions = os.listdir(os.path.join(cfg["vault"], "sessions"))
            first = lookup.context_for(demo.PROMPTS[0], cfg)
            last = lookup.context_for(demo.PROMPTS[-1], cfg)
        self.assertEqual(names, ["Client-Work.md", "Design-System.md", "Research.md", "_BOARD.md", "_INDEX.md"])
        self.assertEqual(len(sessions), 2)
        self.assertIn("sessions/", first)
        self.assertIsNone(last)
        self.assertIn("🟡 stale", out.getvalue())

    def test_demo_refuses_an_existing_folder(self):
        spec = importlib.util.spec_from_file_location("demo_run", RUN)
        demo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(demo)
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(SystemExit):
            demo.main(["run.py", tmp])
