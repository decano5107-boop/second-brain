"""capture must never: crash on a bad transcript, write outside sessions/, create a vault the
user did not ask for, or count text the harness injected as the user's turns."""
import os
import unittest

from second_brain import capture
from tests.helpers import Sandbox, edit, user

TODAY = "2026-05-14"


class Capture(Sandbox):
    domains = {"Client-Work": {"projects": ["trailhead-app"]}, "Research": {"projects": ["kit"]}}

    def event(self, records=None, cwd=None, sid="abc12345-6789"):
        return {"cwd": cwd or os.path.join(self.projects, "trailhead-app"), "session_id": sid,
                "transcript_path": self.transcript(records or [])}

    def run_capture(self, *args, **kw):
        return capture.run(self.event(*args, **kw), self.cfg, today=TODAY)

    def test_writes_a_note_with_files_and_turns(self):
        f = os.path.join(self.projects, "trailhead-app", "src", "app.py")
        path = self.run_capture([user("a"), user("b"), edit(f), edit(f), user("c")])
        text = self.read(path)
        self.assertEqual(os.path.basename(path), f"{TODAY}-trailhead-app-abc12345.md")
        self.assertIn("turns: 3", text)
        self.assertIn("## Files edited (1)", text)
        self.assertIn('domain: "Client-Work"', text)
        self.assertIn(capture.PENDING, text)

    def test_skips_a_trivial_session(self):
        self.assertIsNone(self.run_capture([user("hi"), user("bye")]))
        self.assertEqual(os.listdir(os.path.join(self.vault, "sessions")), [])

    def test_one_edit_is_enough_even_with_few_turns(self):
        self.assertIsNotNone(self.run_capture([user("fix"), edit("/tmp/x.py", "Write")]))

    def test_injected_and_meta_records_are_not_turns(self):
        records = [user("<command-name>/clear</command-name>"), user("<system-reminder>x</system-reminder>"),
                   user("real", isMeta=True), user("real", isSidechain=True),
                   {"type": "user", "message": {"content": [{"type": "tool_result", "content": "ok"}]}},
                   user([{"type": "text", "text": "a real question"}])]
        turns, _ = capture.read_transcript(self.transcript(records))
        self.assertEqual(turns, 1)

    def test_notebook_edits_are_files(self):
        _, files = capture.read_transcript(self.transcript([edit("/n.ipynb", "NotebookEdit")]))
        self.assertEqual(files, {"/n.ipynb"})

    def test_garbage_transcript_lines_are_skipped(self):
        path = self.transcript(["not json", "[1,2]", '{"type": "user", "message": "str"}',
                                user("one"), user("two"), user("three")])
        self.assertEqual(capture.read_transcript(path)[0], 3)

    def test_missing_transcript_is_not_an_error(self):
        self.assertEqual(capture.read_transcript("/does/not/exist.jsonl"), (0, set()))
        event = {"cwd": self.projects, "session_id": "x", "transcript_path": "/nope"}
        self.assertIsNone(capture.run(event, self.cfg, today=TODAY))

    def test_no_vault_means_no_write(self):
        self.cfg["vault"] = os.path.join(self.root, "not-created")
        self.assertIsNone(self.run_capture([user("a"), user("b"), user("c")]))
        self.assertFalse(os.path.exists(self.cfg["vault"]))

    def test_hostile_names_stay_inside_sessions(self):
        cwd = os.path.join(self.projects, "..", "..", "etc")
        path = capture.run(self.event([user("a"), user("b"), user("c")], cwd=cwd, sid="../../x"),
                           self.cfg, today=TODAY)
        self.assertEqual(os.path.dirname(path), os.path.join(self.vault, "sessions"))
        self.assertNotIn("..", os.path.basename(path))

    def test_status_domain_beats_the_projects_list(self):
        self.status("trailhead-app", domain="Research")
        path = self.run_capture([user("a"), user("b"), user("c")])
        self.assertIn('domain: "Research"', self.read(path))

    def test_nested_folder_uses_the_parent_status_and_domain(self):
        self.status("kit", project="interview-kit")
        cwd = os.path.join(self.projects, "kit", "scripts", "deep")
        os.makedirs(cwd)
        path = self.run_capture([user("a"), user("b"), user("c")], cwd=cwd)
        text = self.read(path)
        self.assertIn('project: "interview-kit"', text)
        self.assertIn('domain: "Research"', text)

    def test_status_search_never_leaves_the_projects_root(self):
        self.write(os.path.join(self.root, "STATUS.md"), "---\ndomain: Leaked\n---\n")
        cwd = os.path.join(self.projects, "loose")
        os.makedirs(cwd)
        self.assertIsNone(capture.find_status(cwd, self.cfg))

    def test_summary_comes_from_a_status_updated_today(self):
        self.status("trailhead-app", now="beta shipped", nxt="read feedback", updated=TODAY)
        text = self.read(self.run_capture([user("a"), user("b"), user("c")]))
        self.assertIn("- **Now:** beta shipped", text)
        self.assertNotIn(capture.PENDING, text)

    def test_an_old_status_is_not_this_session_summary(self):
        self.status("trailhead-app", now="old news", updated="2026-01-01")
        text = self.read(self.run_capture([user("a"), user("b"), user("c")]))
        self.assertNotIn("old news", text)
        self.assertIn(capture.PENDING, text)

    def test_a_note_without_the_marker_is_never_overwritten(self):
        path = self.run_capture([user("a"), user("b"), user("c")])
        self.write(path, "---\ntype: session\n---\nmy own summary\n")
        self.assertIsNone(self.run_capture([user("a"), user("b"), user("c")]))
        self.assertIn("my own summary", self.read(path))

    def test_a_marked_note_is_refreshed_when_the_session_ends_again(self):
        path = self.run_capture([user("a"), user("b"), user("c")])
        self.assertEqual(self.run_capture([user("a"), user("b"), user("c"), user("d")]), path)
        self.assertIn("turns: 4", self.read(path))

    def test_quotes_in_project_names_keep_the_frontmatter_valid(self):
        self.status("odd", project='say "hi": now')
        path = capture.run(self.event([user("a"), user("b"), user("c")],
                                      cwd=os.path.join(self.projects, "odd")), self.cfg, today=TODAY)
        from second_brain import notes
        self.assertEqual(notes.read_frontmatter(path)["project"], 'say "hi": now')


if __name__ == "__main__":
    unittest.main()
