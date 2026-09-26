"""Check the release layout that Claude and the other marketplaces consume."""

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parent.parent


def read_json(path):
    return json.loads((ROOT / path).read_text())


class ReleaseLayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = read_json("sources.json")
        cls.plugins = cls.sources["plugins"]
        cls.version = cls.sources["tag"].removeprefix("v")

    def test_claude_entries_resolve_to_released_plugins(self):
        catalog = read_json(".claude-plugin/marketplace.json")
        self.assertEqual(set(self.plugins), {entry["name"] for entry in catalog["plugins"]})
        self.assertNotIn("homepage", catalog)
        for entry in catalog["plugins"]:
            with self.subTest(plugin=entry["name"]):
                name = entry["name"]
                self.assertEqual(entry["source"], f"./plugins/{name}")
                self.assertEqual(entry["version"], self.version)
                root = ROOT / "plugins" / name
                manifest = json.loads((root / ".claude-plugin" / "plugin.json").read_text())
                self.assertEqual(manifest["name"], name)
                self.assertEqual(manifest["version"], self.version)
                for field in (
                    "privacyPolicyUrl", "termsOfServiceUrl", "supportUrl", "documentationUrl"
                ):
                    self.assertTrue(manifest[field].startswith("https://"))
                readme = (root / "README.md").read_text()
                self.assertGreaterEqual(len(re.findall(r"\b[\w-]+\b", readme)), 40)

    def test_component_plugins_have_skills_and_wingman_resolves_locally(self):
        for name in self.plugins:
            skills = list((ROOT / "plugins" / name / "skills").glob("*/SKILL.md"))
            if name == "wingman":
                self.assertEqual(skills, [])
                manifest = read_json("plugins/wingman/.claude-plugin/plugin.json")
                self.assertEqual(
                    set(manifest["dependencies"]),
                    {"hawkscan", "stackhawk-api", "stackhawk-data-seed", "stackhawk-optimize"},
                )
                self.assertTrue(set(manifest["dependencies"]).issubset(self.plugins))
            else:
                with self.subTest(plugin=name):
                    self.assertEqual(len(skills), 1)
                    self.assertTrue((ROOT / "skills" / name / "SKILL.md").is_file())

    def test_remote_catalogs_keep_the_same_release_pin(self):
        sha = self.sources["sha"]
        tag = self.sources["tag"]
        self.assertRegex(sha, r"^[0-9a-f]{40}$")
        for catalog_path, source_type in (
            (".agents/plugins/marketplace.json", "git-subdir"),
            (".codex-plugin/marketplace.json", "git-subdir"),
            (".github/plugin/marketplace.json", "github"),
        ):
            catalog = read_json(catalog_path)
            self.assertEqual(set(self.plugins), {entry["name"] for entry in catalog["plugins"]})
            for entry in catalog["plugins"]:
                with self.subTest(catalog=catalog_path, plugin=entry["name"]):
                    source = entry["source"]
                    self.assertEqual(entry["version"], self.version)
                    self.assertEqual(source["source"], source_type)
                    self.assertEqual(source["ref"], tag)
                    self.assertEqual(source["sha"], sha)
                    self.assertEqual(source["path"].removeprefix("./"), self.plugins[entry["name"]])


if __name__ == "__main__":
    unittest.main()
