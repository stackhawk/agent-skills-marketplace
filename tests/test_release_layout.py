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
                installed = re.findall(r"/plugin install ([\w-]+)@stackhawk", readme)
                self.assertTrue(set(installed).issubset(self.plugins), installed)

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

    def test_copilot_and_codex_catalogs_use_this_repository(self):
        self.assertRegex(self.sources["sha"], r"^[0-9a-f]{40}$")
        for catalog_path, local in (
            (".agents/plugins/marketplace.json", True),
            (".codex-plugin/marketplace.json", True),
            (".github/plugin/marketplace.json", False),
        ):
            catalog = read_json(catalog_path)
            self.assertEqual(set(self.plugins), {entry["name"] for entry in catalog["plugins"]})
            for entry in catalog["plugins"]:
                with self.subTest(catalog=catalog_path, plugin=entry["name"]):
                    name = entry["name"]
                    folder = "bundles" if name == "wingman" else "plugins"
                    expected = f"./{folder}/{name}"
                    source = {"source": "local", "path": expected} if local else expected
                    self.assertEqual(entry["source"], source)
                    self.assertEqual(entry["version"], self.version)
                    self.assertTrue((ROOT / expected / ".claude-plugin" / "plugin.json").is_file())

    def test_wingman_bundle_stays_outside_claude_listed_folders(self):
        claude = read_json(".claude-plugin/marketplace.json")
        self.assertFalse(any(entry["source"].startswith("./bundles") for entry in claude["plugins"]))
        self.assertFalse((ROOT / "plugins" / "wingman" / "copilot-skills").exists())
        self.assertFalse((ROOT / "plugins" / "wingman" / ".github").exists())
        bundles = [path.name for path in (ROOT / "bundles").iterdir() if not path.name.startswith(".")]
        self.assertEqual(bundles, ["wingman"])

        bundle = ROOT / "bundles" / "wingman"
        dependencies = read_json("plugins/wingman/.claude-plugin/plugin.json")["dependencies"]
        for manifest_path in (".github/plugin/plugin.json", ".codex-plugin/plugin.json"):
            with self.subTest(manifest=manifest_path):
                manifest = json.loads((bundle / manifest_path).read_text())
                self.assertEqual(manifest["name"], "wingman")
                self.assertEqual(manifest["version"], self.version)
                self.assertEqual(manifest["skills"], "./copilot-skills/")
        names = {
            re.search(r"^name:[ \t]*(\S+)", path.read_text(), re.MULTILINE).group(1)
            for path in (bundle / "copilot-skills").glob("*/SKILL.md")
        }
        self.assertEqual(names, set(dependencies))
        self.assertEqual(list(bundle.glob("skills/*/SKILL.md")), [])

    def test_wingman_bundle_readme_describes_bundled_skills(self):
        bundle_readme = (ROOT / "bundles" / "wingman" / "README.md").read_text()
        override = (ROOT / "overrides" / "wingman-bundle" / "README.md").read_text()
        self.assertEqual(bundle_readme, override)
        self.assertNotEqual(bundle_readme, (ROOT / "plugins" / "wingman" / "README.md").read_text())
        self.assertIn("copilot-skills/", bundle_readme)
        dependencies = read_json("plugins/wingman/.claude-plugin/plugin.json")["dependencies"]
        for name in dependencies:
            self.assertIn(f"`{name}`", bundle_readme)


if __name__ == "__main__":
    unittest.main()
