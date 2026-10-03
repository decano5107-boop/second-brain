"""maps may overwrite only what it wrote itself."""
import datetime
import os

from second_brain import maps, notes
from tests.helpers import Sandbox

TODAY = datetime.date(2026, 5, 14)


class Maps(Sandbox):
    overrides = {"roots": {"archive": "/archive"}}
    domains = {
        "Client-Work": {"summary": "Paid work.", "projects": ["trailhead-app"],
                        "folders": {"archive": ["Clients"], "missing-root": ["x"]},
                        "neighbors": ["Research"]},
        "Research": {},
        "Studio": {"curated": True},
        "a/b": {},
    }

    def generate(self):
        return maps.generate(self.cfg, TODAY, log=lambda _m: None)

    def map_path(self, name):
        return os.path.join(self.vault, "maps", name + ".md")

    def test_writes_every_non_curated_map_and_an_index(self):
        written = {os.path.basename(p) for p in self.generate()}
        self.assertEqual(written, {"Client-Work.md", "Research.md", "a-b.md", "_INDEX.md"})
        self.assertFalse(os.path.exists(self.map_path("Studio")))

    def test_map_contents(self):
        self.generate()
        text = self.read(self.map_path("Client-Work"))
        self.assertIn("Paid work.", text)
        self.assertIn("[trailhead-app](file://", text)
        self.assertIn("archive: [Clients](file:///archive/Clients)", text)
        self.assertIn("root `missing-root` is not in `roots`", text)
        self.assertIn("[[Research]]", text)

    def test_hand_written_maps_are_never_overwritten(self):
        mine = self.write(self.map_path("Research"), "# My own research map\n")
        self.generate()
        self.assertEqual(self.read(mine), "# My own research map\n")

    def test_generated_maps_are_refreshed(self):
        self.generate()
        self.write(os.path.join(self.vault, "sessions", "2026-05-13-kit-a1.md"),
                   '---\ntype: session\ndate: 2026-05-13\nproject: "kit"\ndomain: "Research"\n---\n')
        self.generate()
        self.assertIn("[[2026-05-13-kit-a1]]", self.read(self.map_path("Research")))

    def test_recent_sessions_and_documents_are_listed_newest_first(self):
        for day in ("01", "09", "05"):
            self.write(os.path.join(self.vault, "sessions", f"2026-05-{day}-p-x.md"),
                       f'---\ntype: session\ndate: 2026-05-{day}\ndomain: "Research"\n---\n')
        self.write(os.path.join(self.vault, "stubs", "Research", "deck-1.md"),
                   '---\ntype: stub\ntitle: "Deck"\ndomain: "Research"\nmodified: 2026-05-02\n---\n')
        self.generate()
        text = self.read(self.map_path("Research"))
        self.assertLess(text.index("2026-05-09"), text.index("2026-05-05"))
        self.assertIn("## Documents (1)", text)
        self.assertIn("[[deck-1]] — Deck", text)

    def test_domain_names_cannot_escape_maps(self):
        self.generate()
        self.assertTrue(notes.is_within(self.map_path("a-b"), os.path.join(self.vault, "maps")))
        self.assertFalse(os.path.exists(os.path.join(self.vault, "maps", "a")))

    def test_no_vault_writes_nothing(self):
        self.cfg["vault"] = os.path.join(self.root, "none")
        self.assertEqual(self.generate(), [])
        self.assertFalse(os.path.exists(self.cfg["vault"]))
