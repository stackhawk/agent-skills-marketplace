"""Check the release layout that Claude and the other marketplaces consume."""

import json
import os
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


CURSOR_CATALOG = ".cursor-plugin/marketplace.json"
INSTALLERS = ("install.sh", "install.ps1", "cursor-legacy-rules.txt")
STOP_SCRIPT_ROOT = "${CURSOR_PLUGIN_ROOT}/"
NOT_ALWAYS_APPLIED = {"", "false", "no", "off", "0"}
RULE_SUFFIXES = (".mdc", ".md", ".markdown")


def cursor_folder(name):
    return f"bundles/{name}" if name == "wingman" else f"plugins/{name}"


def named_paths(folder, manifest, key, default):
    """The paths a Cursor manifest names for one component, which must exist; else the default
    path, when the plugin has it."""
    if key not in manifest:
        return [folder / default] if (folder / default).exists() else []
    value = manifest[key]
    paths = [folder / path for path in ([value] if isinstance(value, str) else value)]
    missing = [path for path in paths if not path.exists()]
    if missing:
        raise AssertionError(f"{folder}: the Cursor manifest names missing {key} paths {missing}")
    return paths


def is_router(rule):
    """A rule Cursor always applies: an alwaysApply value that is not clearly false."""
    frontmatter = re.match(r"---\r?\n(.*?)\r?\n---", rule.read_text(), re.DOTALL)
    values = re.findall(r"^alwaysApply:(.*)$", frontmatter.group(1) if frontmatter else "", re.MULTILINE)
    return any(
        value.split(" #")[0].strip().strip("'\"").strip().lower() not in NOT_ALWAYS_APPLIED for value in values
    )


def cursor_install(folder):
    """The router rules and the stop hook commands Cursor loads from one plugin folder."""
    root = ROOT / folder
    manifest = read_json(f"{folder}/.cursor-plugin/plugin.json")
    rules = []
    for path in named_paths(root, manifest, "rules", "rules"):
        found = sorted(path.rglob("*")) if path.is_dir() else [path]
        rules += [rule for rule in found if rule.is_file() and (rule.suffix in RULE_SUFFIXES or not path.is_dir())]
    stops = []
    for path in named_paths(root, manifest, "hooks", "hooks/hooks.json"):
        if path.is_file():
            events = json.loads(path.read_text())["hooks"]
            stops += [entry["command"] for entry in events.get("stop", [])]
            stops += [hook["command"] for group in events.get("Stop", []) for hook in group.get("hooks", [])]
    return [rule.relative_to(root).as_posix() for rule in rules if is_router(rule)], stops


class CursorLayoutTest(unittest.TestCase):
    """The Cursor outputs come from an agent-skills export (sync-agent-skills.py --export).

    A tag synced without the export has none of them, so the Cursor checks skip until the
    first export sync. The Claude wingman never carries Cursor files: the Cursor app imports
    Claude Code plugins, and they would load the router rule and the stop hook a second time
    next to the hawkscan dependency.
    """

    @classmethod
    def setUpClass(cls):
        sources = read_json("sources.json")
        cls.plugins = sources["plugins"]
        cls.version = sources["tag"].removeprefix("v")
        cls.cursor = (ROOT / CURSOR_CATALOG).is_file()

    def require_cursor(self):
        if not self.cursor:
            self.skipTest("no Cursor catalog: the synced tag predates the agent-skills export")

    def test_claude_wingman_carries_no_cursor_or_bundle_files(self):
        wingman = ROOT / "plugins" / "wingman"
        for part in (".cursor-plugin", "rules", "hooks/cursor", "copilot-skills", ".github"):
            self.assertFalse((wingman / part).exists(), part)
        self.assertEqual(list(wingman.rglob("*.mdc")), [])
        hooks = wingman / "hooks" / "hooks.json"
        events = json.loads(hooks.read_text()).get("hooks", {}) if hooks.is_file() else {}
        self.assertEqual([event for event in events if event.lower() == "stop"], [])

    def test_cursor_outputs_are_all_present_or_all_absent(self):
        outputs = [CURSOR_CATALOG, *(f"install/{name}" for name in INSTALLERS)]
        outputs += [f"{cursor_folder(name)}/.cursor-plugin/plugin.json" for name in self.plugins]
        present = {path: (ROOT / path).is_file() for path in outputs}
        self.assertEqual(set(present.values()), {self.cursor}, present)
        if not self.cursor:
            self.assertFalse((ROOT / "install").exists())
            self.assertEqual(list(ROOT.glob("*/*/.cursor-plugin")), [])

    def test_cursor_catalog_lists_the_released_folders(self):
        self.require_cursor()
        catalog = read_json(CURSOR_CATALOG)
        self.assertEqual([entry["name"] for entry in catalog["plugins"]], list(self.plugins))
        for entry in catalog["plugins"]:
            with self.subTest(plugin=entry["name"]):
                folder = cursor_folder(entry["name"])
                self.assertEqual(entry["source"], f"./{folder}")
                manifest = read_json(f"{folder}/.cursor-plugin/plugin.json")
                self.assertEqual(manifest["name"], entry["name"])
                self.assertEqual(manifest["version"], self.version)

    def test_cursor_installs_load_one_router_and_one_stop_hook_at_most(self):
        self.require_cursor()
        for name in self.plugins:
            with self.subTest(plugin=name):
                routers, stops = cursor_install(cursor_folder(name))
                self.assertLessEqual(len(routers), 1, routers)
                self.assertLessEqual(len(stops), 1, stops)
                for command in stops:
                    script = command.strip().strip('"')
                    self.assertTrue(script.startswith(STOP_SCRIPT_ROOT), command)
                    target = ROOT / cursor_folder(name) / script.removeprefix(STOP_SCRIPT_ROOT)
                    self.assertTrue(os.access(target, os.X_OK), target)

    def test_hawkscan_and_the_wingman_bundle_load_exactly_one_router_and_one_stop_hook(self):
        self.require_cursor()
        for folder in ("plugins/hawkscan", "bundles/wingman"):
            with self.subTest(folder=folder):
                routers, stops = cursor_install(folder)
                self.assertEqual(routers, ["rules/stackhawk.mdc"])
                self.assertEqual(len(stops), 1, stops)

    def test_cursor_installers_are_released(self):
        self.require_cursor()
        self.assertTrue(os.access(ROOT / "install" / "install.sh", os.X_OK))
        legacy = (ROOT / "install" / "cursor-legacy-rules.txt").read_text().splitlines()
        self.assertTrue([line for line in legacy if line.strip() and not line.startswith("#")])

    def test_scripts_and_the_legacy_rule_list_keep_lf_line_endings(self):
        # Git for Windows checks text out with CRLF by default. Bash then fails on install.sh
        # and the stop hook, and install.sh no longer matches the legacy rule names it reads.
        attributes = (ROOT / ".gitattributes").read_text().splitlines()
        self.assertIn("*.sh text eol=lf", attributes)
        self.assertIn("install/cursor-legacy-rules.txt text eol=lf", attributes)
        checked = [*ROOT.glob("*/*/hooks/cursor/stop.sh"), *ROOT.glob("install/*.sh"),
                   *ROOT.glob("install/cursor-legacy-rules.txt")]
        for path in checked:
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                self.assertNotIn(b"\r", path.read_bytes())


if __name__ == "__main__":
    unittest.main()
