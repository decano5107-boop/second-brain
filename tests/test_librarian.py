"""The librarian reads documents other people wrote. It must file them predictably, never
re-read an unchanged file, never index the vault into itself, and never let a document's text
or name break the stub it writes."""
import io
import os
import zipfile

from second_brain import librarian, notes
from tests.helpers import Sandbox


def office(path, members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, xml in members.items():
            z.writestr(name, xml)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(buf.getvalue())
    return path


class Librarian(Sandbox):
    domains = {
        "Client-Work": {"folders": {"archive": ["Clients"]}, "keywords": ["invoice", "proposal"]},
        "Research": {"folders": {"archive": ["Research"]}, "keywords": ["interview"]},
    }

    def docs(self, *parts):
        return os.path.join(self.root, "docs", *parts)

    def quiet(self, paths):
        return librarian.process(paths, self.cfg, log=lambda _m: None)

    def stubs(self):
        out = []
        for folder, _dirs, files in os.walk(os.path.join(self.vault, "stubs")):
            out += [os.path.join(folder, f) for f in files]
        return sorted(out)

    def test_office_formats_are_read_without_external_tools(self):
        docx = office(self.docs("a.docx"), {"word/document.xml": "<w:p><w:t>Quarterly proposal</w:t></w:p>"})
        xlsx = office(self.docs("b.xlsx"), {"xl/sharedStrings.xml": "<si><t>Invoice 42</t></si>"})
        odt = office(self.docs("c.odt"), {"content.xml": "<text:p>Open &amp; document</text:p>"})
        self.assertIn("Quarterly proposal", librarian.extract(docx, 1000))
        self.assertIn("Invoice 42", librarian.extract(xlsx, 1000))
        self.assertIn("Open & document", librarian.extract(odt, 1000))

    def test_slides_come_out_in_slide_order(self):
        members = {f"ppt/slides/slide{i}.xml": f"<a:p>slide-{i}</a:p>" for i in (10, 2, 1)}
        text = librarian.extract(office(self.docs("d.pptx"), members), 1000)
        self.assertLess(text.index("slide-1"), text.index("slide-2"))
        self.assertLess(text.index("slide-2"), text.index("slide-10"))

    def test_broken_files_give_empty_text_not_an_error(self):
        bad = self.write(self.docs("broken.docx"), "not a zip")
        self.assertEqual(librarian.extract(bad, 1000), "")
        self.assertEqual(self.quiet([bad]), 1)                  # still findable by name

    def test_folder_beats_keywords(self):
        path = self.write(self.docs("Research", "notes.txt"), "the invoice for the interview")
        self.assertEqual(librarian.guess_domain(path, "invoice", self.cfg), "Research")

    def test_keywords_in_config_order_then_unsorted(self):
        self.assertEqual(librarian.guess_domain("/x/a.txt", "an interview and an invoice", self.cfg), "Client-Work")
        self.assertEqual(librarian.guess_domain("/x/a.txt", "nothing here", self.cfg), librarian.UNSORTED)

    def test_unchanged_files_are_not_reprocessed(self):
        path = self.write(self.docs("a.txt"), "interview")
        self.assertEqual(self.quiet([path]), 1)
        self.assertEqual(self.quiet([path]), 0)
        self.write(path, "interview, revised and longer")
        self.assertEqual(self.quiet([path]), 1)
        self.assertEqual(len(self.stubs()), 1)

    def test_a_document_that_changes_domain_leaves_no_old_stub(self):
        path = self.write(self.docs("a.txt"), "interview")
        self.quiet([path])
        self.write(path, "an invoice now, much longer than before")
        self.quiet([path])
        stubs = self.stubs()
        self.assertEqual(len(stubs), 1)
        self.assertIn(os.sep + "Client-Work" + os.sep, stubs[0])

    def test_skips_temp_hidden_symlinked_and_unlisted_files(self):
        real = self.write(self.docs("real.txt"), "x")
        skipped = [self.write(self.docs(n), "x") for n in (".hidden.txt", "~$lock.docx", "a.txt.crdownload", "a.exe")]
        link = self.docs("link.txt")
        os.symlink(real, link)
        self.assertEqual(self.quiet(skipped + [link]), 0)

    def test_walk_prunes_excluded_dirs_and_the_vault(self):
        self.write(self.docs("keep.txt"), "x")
        self.write(self.docs("node_modules", "pkg", "readme.md"), "x")
        self.write(os.path.join(self.vault, "maps", "m.md"), "x")
        found = list(librarian.walk([self.docs(), self.root], self.cfg))
        self.assertTrue(any(p.endswith("keep.txt") for p in found))
        self.assertFalse(any("node_modules" in p for p in found))
        self.assertFalse(any(p.startswith(self.vault) for p in found))

    def test_vault_files_are_never_indexed(self):
        inside = self.write(os.path.join(self.vault, "maps", "m.md"), "interview")
        self.assertEqual(self.quiet([inside]), 0)

    def test_hostile_names_and_text_cannot_break_the_stub(self):
        name = 'a "quoted": name\n---\nevil.txt'.replace("\n", " ")
        path = self.write(self.docs(name), "```\n---\ntype: map\n```")
        self.quiet([path])
        stub = self.stubs()[0]
        fields = notes.read_frontmatter(stub)
        self.assertEqual(fields["type"], "stub")
        self.assertEqual(fields["title"], name)
        body = self.read(stub).split("```text", 1)[1]
        self.assertEqual(body.count("```"), 1)                  # only the closing fence
        self.assertTrue(notes.is_within(stub, os.path.join(self.vault, "stubs")))

    def test_hand_edited_stubs_are_neither_overwritten_nor_deleted(self):
        path = self.write(self.docs("a.txt"), "interview")
        self.quiet([path])
        stub = self.stubs()[0]
        self.write(stub, "---\ntype: stub\n---\nmy notes on this document\n")
        self.write(path, "an invoice now, much longer than before")
        self.quiet([path])
        self.assertIn("my notes", self.read(stub))              # kept, and not deleted either
        self.assertEqual(len(self.stubs()), 2)                   # the new domain gets its own stub

    def test_no_vault_writes_nothing(self):
        self.cfg["vault"] = os.path.join(self.root, "none")
        path = self.write(self.docs("a.txt"), "x")
        self.assertEqual(self.quiet([path]), 0)
        self.assertFalse(os.path.exists(self.cfg["vault"]))
