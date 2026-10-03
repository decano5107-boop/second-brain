"""The config loader is called by every hook, so its contract is: never raise, never block,
and say once on stderr when it ignored something the user wrote."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from second_brain import config

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "brain.config.example.json"


class LoaderCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.warnings = []

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, content):
        p = self.dir / name
        p.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
        return p

    def load(self, content=None, **kw):
        path = self.write("c.json", content) if content is not None else None
        return config.load(path=path, warn=self.warnings.append, **kw)


class Defaults(LoaderCase):
    def test_no_file_gives_defaults_and_no_warning(self):
        cfg = config.load(path=self.dir / "missing.json", warn=self.warnings.append)
        self.assertEqual(cfg["lookup"]["max_hits"], 5)
        self.assertEqual(cfg["status"]["labels"], {"now": "Now", "next": "Next step"})
        self.assertEqual(cfg["domains"], {})
        self.assertIsNone(cfg["_source"])
        self.assertEqual(self.warnings, [])

    def test_defaults_are_not_shared_between_loads(self):
        a = self.load({})
        a["lookup"]["search_dirs"].append("stubs")
        b = self.load({})
        self.assertEqual(b["lookup"]["search_dirs"], ["maps", "sessions"])

    def test_paths_are_expanded(self):
        cfg = self.load({"vault": "~/v", "roots": {"inbox": "~/in"}, "librarian": {"sources": ["~/s"]}})
        home = os.path.expanduser("~")
        self.assertEqual(cfg["vault"], os.path.join(home, "v"))
        self.assertEqual(cfg["roots"]["inbox"], os.path.join(home, "in"))
        self.assertEqual(cfg["librarian"]["sources"], [os.path.join(home, "s")])


class Merging(LoaderCase):
    def test_nested_values_override_only_what_is_given(self):
        cfg = self.load({"status": {"labels": {"now": "Jetzt"}}})
        self.assertEqual(cfg["status"]["labels"], {"now": "Jetzt", "next": "Next step"})
        self.assertEqual(cfg["status"]["stale_days"], 30)

    def test_wrong_type_keeps_default_and_warns(self):
        cfg = self.load({"lookup": {"max_hits": "five"}})
        self.assertEqual(cfg["lookup"]["max_hits"], 5)
        self.assertEqual(len(self.warnings), 1)
        self.assertIn("lookup.max_hits", self.warnings[0])

    def test_bool_is_not_accepted_as_a_number(self):
        cfg = self.load({"status": {"stale_days": True}})
        self.assertEqual(cfg["status"]["stale_days"], 30)
        self.assertEqual(len(self.warnings), 1)

    def test_float_accepted_where_default_is_float(self):
        self.assertEqual(self.load({"lookup": {"timeout_seconds": 1}})["lookup"]["timeout_seconds"], 1)

    def test_unknown_key_is_a_warning_not_an_error(self):
        cfg = self.load({"lookup": {"max_hit": 3}})
        self.assertEqual(cfg["lookup"]["max_hits"], 5)
        self.assertIn("lookup.max_hit", self.warnings[0])

    def test_list_elements_must_be_strings(self):
        cfg = self.load({"lookup": {"search_dirs": [1, 2]}})
        self.assertEqual(cfg["lookup"]["search_dirs"], ["maps", "sessions"])
        self.assertEqual(len(self.warnings), 1)

    def test_counts_must_be_whole_numbers(self):
        cfg = self.load({"lookup": {"max_hits": 5.5}, "status": {"stale_days": 30.5}})
        self.assertEqual((cfg["lookup"]["max_hits"], cfg["status"]["stale_days"]), (5, 30))
        self.assertEqual(len(self.warnings), 2)

    def test_roots_values_must_be_paths(self):
        cfg = self.load({"roots": {"inbox": 3}})
        self.assertEqual(cfg["roots"], {})
        self.assertEqual(len(self.warnings), 1)

    def test_log_accepts_string_or_null(self):
        self.assertIsNone(self.load({"lookup": {"log": None}})["lookup"]["log"])
        self.assertTrue(self.load({"lookup": {"log": "~/l.jsonl"}})["lookup"]["log"].endswith("l.jsonl"))


class BrokenFiles(LoaderCase):
    def test_invalid_json_falls_back_to_defaults_with_one_warning(self):
        cfg = self.load("{ not json")
        self.assertEqual(cfg["lookup"]["max_hits"], 5)
        self.assertEqual(len(self.warnings), 1)

    def test_json_that_is_not_an_object(self):
        cfg = self.load("[1, 2]")
        self.assertIsNone(cfg["_source"])
        self.assertEqual(len(self.warnings), 1)

    def test_broken_first_candidate_falls_through_to_the_next(self):
        broken = self.write("broken.json", "{")
        good = self.write("good.json", {"lookup": {"max_hits": 2}})
        env = {config.ENV_VAR: str(broken)}
        original = config.candidate_paths
        config.candidate_paths = lambda env=None: [broken, good]
        try:
            cfg = config.load(env=env, warn=self.warnings.append)
        finally:
            config.candidate_paths = original
        self.assertEqual(cfg["lookup"]["max_hits"], 2)
        self.assertEqual(cfg["_source"], str(good))

    def test_env_var_is_the_first_candidate(self):
        p = self.write("env.json", {})
        self.assertEqual(config.candidate_paths({config.ENV_VAR: str(p)})[0], p)


class Domains(LoaderCase):
    def test_domain_fields_get_defaults(self):
        cfg = self.load({"domains": {"Research": {"keywords": ["Interview"]}}})
        d = cfg["domains"]["Research"]
        self.assertEqual(d["keywords"], ["interview"])
        self.assertEqual(d["projects"], [])
        self.assertFalse(d["curated"])

    def test_domain_order_is_preserved(self):
        names = ["Zeta", "Alpha", "Mid"]
        cfg = self.load({"domains": {n: {} for n in names}})
        self.assertEqual(list(cfg["domains"]), names)

    def test_bad_domain_values_are_dropped_with_a_warning(self):
        cfg = self.load({"domains": {"A": "not an object", "B": {"keywords": "interview", "colour": 1}}})
        self.assertNotIn("A", cfg["domains"])
        self.assertEqual(cfg["domains"]["B"]["keywords"], [])
        self.assertEqual(len(self.warnings), 3)

    def test_bad_domain_elements_warn_instead_of_vanishing(self):
        cfg = self.load({"domains": {"A": {"keywords": ["X", 3], "projects": [2],
                                           "folders": {"archive": "Clients"}}}})
        d = cfg["domains"]["A"]
        self.assertEqual((d["keywords"], d["projects"], d["folders"]), ([], [], {}))
        self.assertEqual(len(self.warnings), 3)

    def test_domains_not_an_object(self):
        cfg = self.load({"domains": ["Research"]})
        self.assertEqual(cfg["domains"], {})
        self.assertEqual(len(self.warnings), 1)


class Example(LoaderCase):
    def test_shipped_example_loads_without_warnings(self):
        cfg = config.load(path=EXAMPLE, warn=self.warnings.append)
        self.assertEqual(self.warnings, [])
        self.assertEqual(list(cfg["domains"]), ["Client-Work", "Design-System", "Research", "Studio"])
        self.assertTrue(cfg["domains"]["Studio"]["curated"])


if __name__ == "__main__":
    unittest.main()
