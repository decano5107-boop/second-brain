"""The board must reflect every status file and nothing else, and a row's text must never
break the table."""
import datetime
import os

from second_brain import board
from tests.helpers import Sandbox

TODAY = datetime.date(2026, 5, 14)


class Board(Sandbox):
    def rows(self):
        text = board.build(self.cfg, TODAY)
        return [ln for ln in text.splitlines() if ln.startswith("| ") and not ln.startswith("| Status")]

    def test_one_row_per_status_file(self):
        self.status("a", "doing a", "next a", status="active", updated="2026-05-10")
        self.status("b", "doing b", "next b", status="done", updated="2026-05-12")
        rows = self.rows()
        self.assertEqual(len(rows), 2)
        self.assertIn("doing a", rows[0])
        self.assertIn("done", rows[1])

    def test_active_but_untouched_becomes_stale(self):
        self.status("old", status="active", updated="2026-03-01")
        self.status("fresh", status="active", updated="2026-05-13")
        rows = self.rows()
        self.assertIn("🟢 active", rows[0])
        self.assertIn("🟡 stale", rows[1])

    def test_order_is_status_then_newest(self):
        self.status("p1", status="parked", updated="2026-05-13")
        self.status("a1", status="active", updated="2026-05-01")
        self.status("a2", status="active", updated="2026-05-12")
        names = [r.split("|")[2] for r in self.rows()]
        self.assertTrue(names[0].strip().startswith("[a2]"))
        self.assertTrue(names[1].strip().startswith("[a1]"))
        self.assertTrue(names[2].strip().startswith("[p1]"))

    def test_pipes_and_newlines_cannot_break_the_table(self):
        self.status("x", now="a | b | c", updated="2026-05-13")
        row = self.rows()[0]
        self.assertEqual(row.count(" | "), 4)                  # five cells, four separators
        self.assertIn("a \\| b \\| c", row)

    def test_pruned_and_hidden_folders_are_skipped(self):
        self.status("real", updated="2026-05-13")
        for hidden in ("node_modules/pkg", ".git/x", "_archive/old"):
            self.write(os.path.join(self.projects, hidden, "STATUS.md"), "**Now:** no\n")
        self.assertEqual(len(self.rows()), 1)

    def test_custom_labels_read_status_files_in_another_language(self):
        self.cfg["status"]["labels"] = {"now": "Jetzt", "next": "Nächster Schritt"}
        self.write(os.path.join(self.projects, "de", "STATUS.md"),
                   "---\nupdated: 2026-05-13\n---\n**Jetzt:** in Arbeit\n**Nächster Schritt:** prüfen\n")
        text = board.build(self.cfg, TODAY)
        self.assertIn("| Jetzt | Nächster Schritt |", text)
        self.assertIn("in Arbeit", text)
        self.assertIn("prüfen", text)

    def test_no_frontmatter_uses_the_file_date_and_folder_name(self):
        path = self.write(os.path.join(self.projects, "group", "leaf", "STATUS.md"), "**Now:** x\n")
        stamp = datetime.datetime(2026, 5, 13).timestamp()
        os.utime(path, (stamp, stamp))
        row = self.rows()[0]
        self.assertIn("[group/leaf]", row)
        self.assertIn("2026-05-13", row)

    def test_missing_projects_root_gives_an_empty_board(self):
        self.cfg["projects_root"] = os.path.join(self.root, "nope")
        self.assertIn("_0 projects._", board.build(self.cfg, TODAY))

    def test_write_needs_a_vault(self):
        self.cfg["vault"] = os.path.join(self.root, "none")
        self.assertIsNone(board.write(self.cfg, TODAY))
        self.assertFalse(os.path.exists(self.cfg["vault"]))

    def test_a_hand_written_board_is_never_replaced(self):
        mine = self.write(os.path.join(self.vault, "maps", "_BOARD.md"), "# my own board\n")
        self.assertIsNone(board.write(self.cfg, TODAY))
        self.assertEqual(self.read(mine), "# my own board\n")

    def test_a_symlink_in_place_of_the_board_is_not_followed(self):
        target = self.write(os.path.join(self.root, "elsewhere.md"), "keep\n")
        os.symlink(target, os.path.join(self.vault, "maps", "_BOARD.md"))
        self.assertIsNone(board.write(self.cfg, TODAY))
        self.assertEqual(self.read(target), "keep\n")

    def test_write_puts_the_board_in_maps(self):
        path = board.write(self.cfg, TODAY)
        self.assertEqual(path, os.path.join(self.vault, "maps", "_BOARD.md"))
