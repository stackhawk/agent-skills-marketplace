"""Check that the sync publishes an agent-skills export as is, and refuses a bad export.

An export is the payload of one agent-skills commit, written by its
scripts/export-marketplace.py. These tests build a small export in the same format.
"""

import hashlib
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "sync-agent-skills.py"
README = "word " * 50
VERSION = "3.4.5"
TAG = f"v{VERSION}"
# Catalog name -> upstream folder. stackhawk-api has another folder name, as in sources.json.
CURATED = {"hawkscan": "plugins/hawkscan", "stackhawk-api": "plugins/api", "wingman": "plugins/wingman"}
DEPENDENCIES = ["hawkscan", "stackhawk-api"]
# Catalog name -> the export folder that the Cursor catalog installs it from (format 2).
CURSOR = {"hawkscan": "cursor-plugins/hawkscan", "stackhawk-api": "plugins/stackhawk-api",
          "wingman": "bundles/wingman"}
ROUTER = "---\ndescription: StackHawk skills router.\nalwaysApply: true\n---\nrouter\n"
CONFIG_RULE = (
    "---\ndescription: StackHawk guidance for stackhawk.yml.\nglobs:\n"
    '  - "**/stackhawk.yml"\nalwaysApply: false\n---\nconfig\n'
)
STOP_COMMAND = '"${CURSOR_PLUGIN_ROOT}/hooks/cursor/stop.sh"'
STOP_HOOKS = {"version": 1, "hooks": {"stop": [{"command": STOP_COMMAND, "loop_limit": 1}]}}
PUBLISHED = [
    "plugins", "bundles", "cursor-plugins", "skills", "install", "sources.json",
    ".claude-plugin/marketplace.json", ".github/plugin/marketplace.json",
    ".agents/plugins/marketplace.json", ".codex-plugin/marketplace.json",
    ".cursor-plugin/marketplace.json",
]


def load_sync():
    spec = importlib.util.spec_from_file_location("sync_agent_skills_export", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path, content, executable=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content if isinstance(content, str) else json.dumps(content, indent=2) + "\n")
    path.chmod(0o755 if executable else 0o644)


def skill(name):
    return f"---\nname: {name}\nversion: 0.0.0-dev\ndescription: test\n---\nbody\n"


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout


def commit_and_tag(repo, tag):
    git(repo, "add", "-A")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", tag)
    git(repo, "tag", tag)
    return git(repo, "rev-parse", "HEAD").strip()


def write_source_plugins(repo, cursor_adapter=False):
    """The plugin folders of the tagged commit, which the sync without --export copies."""
    write(repo / "plugins/hawkscan/.claude-plugin/plugin.json", {"name": "hawkscan", "version": "0.0.0"})
    write(repo / "plugins/hawkscan/skills/hawkscan/SKILL.md", skill("hawkscan"))
    write(repo / "plugins/hawkscan/README.md", README)
    write(repo / "plugins/api/.claude-plugin/plugin.json", {"name": "stackhawk-api", "version": "0.0.0"})
    write(repo / "plugins/api/skills/api/SKILL.md", skill("api"))
    write(repo / "plugins/api/README.md", README)
    wingman = repo / "plugins/wingman"
    write(wingman / ".claude-plugin/plugin.json",
          {"name": "wingman", "version": "0.0.0", "dependencies": DEPENDENCIES})
    write(wingman / ".codex-plugin/plugin.json", {"name": "wingman", "version": "0.0.0"})
    write(wingman / ".github/plugin/plugin.json",
          {"name": "wingman", "version": "0.0.0", "skills": "./copilot-skills/"})
    for name in DEPENDENCIES:
        write(wingman / f"copilot-skills/{name}/SKILL.md", skill(name))
    write(wingman / "README.md", README)
    if cursor_adapter:
        write_cursor_files(wingman, "wingman", skills="./copilot-skills/")


def build_source(repo, cursor_adapter=False):
    """The agent-skills commit of the tag: its catalogs and plugin folders."""
    claude = {"name": "stackhawk", "plugins": [
        {"name": name, "source": f"./{folder}"} for name, folder in CURATED.items()]}
    write(repo / ".claude-plugin/marketplace.json", claude)
    write(repo / ".codex-plugin/marketplace.json", claude)
    write_source_plugins(repo, cursor_adapter)
    git(repo, "init", "-q")
    return commit_and_tag(repo, TAG)


def write_cursor_files(folder, name, skills=None):
    """The Cursor manifest, the router and config rules, and the stop hook of one plugin."""
    manifest = {"name": name, "version": VERSION}
    if skills:
        manifest["skills"] = skills
    manifest.update(rules="./rules/", hooks="./hooks/cursor/plugin-hooks.json")
    write(folder / ".cursor-plugin/plugin.json", manifest)
    write(folder / "rules/stackhawk.mdc", ROUTER)
    write(folder / "rules/stackhawk-config.mdc", CONFIG_RULE)
    write(folder / "hooks/cursor/plugin-hooks.json", STOP_HOOKS)
    write(folder / "hooks/cursor/stop.sh", "#!/usr/bin/env bash\nexit 0\n", executable=True)


def build_export(export, sha, extra_plugin=False):
    """A small export: Claude snapshots, the Wingman bundle, the Cursor-only hawkscan, the
    Cursor catalog, installers."""
    shutil.rmtree(export, ignore_errors=True)
    hawkscan = export / "plugins/hawkscan"
    write(hawkscan / ".claude-plugin/plugin.json", {"name": "hawkscan", "version": VERSION})
    write(hawkscan / "skills/hawkscan/SKILL.md", skill("hawkscan").replace("0.0.0-dev", VERSION))
    write(hawkscan / "README.md", README)
    # The Claude Code hooks stay in the Claude snapshot: they do nothing when Cursor runs them.
    write(hawkscan / "hooks/hooks.json", {"hooks": {"Stop": [{"hooks": [{"command": "stop"}]}]}})
    cursor_hawkscan = export / "cursor-plugins/hawkscan"
    write(cursor_hawkscan / "skills/hawkscan/SKILL.md", skill("hawkscan").replace("0.0.0-dev", VERSION))
    write_cursor_files(cursor_hawkscan, "hawkscan")
    api = export / "plugins/stackhawk-api"
    write(api / ".claude-plugin/plugin.json", {"name": "stackhawk-api", "version": VERSION})
    write(api / ".cursor-plugin/plugin.json", {"name": "stackhawk-api", "version": VERSION})
    write(api / "skills/api/SKILL.md", skill("api").replace("0.0.0-dev", VERSION))
    write(api / "README.md", README)
    claude_wingman = {"name": "wingman", "version": VERSION, "dependencies": DEPENDENCIES}
    write(export / "plugins/wingman/.claude-plugin/plugin.json", claude_wingman)
    write(export / "plugins/wingman/.codex-plugin/plugin.json", {"name": "wingman", "version": VERSION})
    write(export / "plugins/wingman/README.md", README)
    bundle = export / "bundles/wingman"
    write(bundle / ".claude-plugin/plugin.json", claude_wingman)
    write(bundle / ".codex-plugin/plugin.json", {"name": "wingman", "version": VERSION})
    write(bundle / ".github/plugin/plugin.json",
          {"name": "wingman", "version": VERSION, "skills": "./copilot-skills/"})
    for name in DEPENDENCIES:
        write(bundle / f"copilot-skills/{name}/SKILL.md", skill(name).replace("0.0.0-dev", VERSION))
    write(bundle / "README.md", README)
    write_cursor_files(bundle, "wingman", skills="./copilot-skills/")
    entries = [{"name": name, "source": f"./{CURSOR[name]}"} for name in CURATED]
    if extra_plugin:
        extra = export / "plugins/extra"
        write(extra / ".claude-plugin/plugin.json", {"name": "extra", "version": VERSION})
        write(extra / ".cursor-plugin/plugin.json", {"name": "extra", "version": VERSION})
        write(extra / "skills/extra/SKILL.md", skill("extra"))
        entries.insert(1, {"name": "extra", "source": "./plugins/extra"})
    write(export / ".cursor-plugin/marketplace.json", {"name": "stackhawk", "plugins": entries})
    write(export / "install/install.sh", "#!/usr/bin/env bash\necho install\n", executable=True)
    write(export / "install/install.ps1", "Write-Output install\n")
    write(export / "install/cursor-legacy-rules.txt", "# old rules\nstackhawk-old.mdc\n")
    plugins = dict(CURATED, extra="plugins/extra") if extra_plugin else dict(CURATED)
    cursor = dict(CURSOR, extra="plugins/extra") if extra_plugin else dict(CURSOR)
    write_manifest(export, sha, plugins=plugins, cursor=cursor)


def write_manifest(export, sha, version=VERSION, plugins=None, bundles=None, cursor=None):
    """Write export-manifest.json for the files the export holds now, as the exporter does."""
    manifest_path = export / "export-manifest.json"
    plugins = plugins or dict(CURATED)
    files = sorted(
        path for path in export.rglob("*") if path.is_file() and path != manifest_path
    )
    write(manifest_path, {
        "format": 2,
        "source": {"commit": sha},
        "version": version,
        "plugins": plugins,
        "bundles": bundles or {"wingman": plugins["wingman"]},
        "cursor": cursor or dict(CURSOR),
        "files": [
            {
                "path": path.relative_to(export).as_posix(),
                "mode": "100755" if path.stat().st_mode & 0o111 else "100644",
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in files
        ],
    })


def tree_state(root):
    """Every file under root with its bytes and executable bit."""
    return {
        path.relative_to(root).as_posix(): (path.read_bytes(), bool(path.stat().st_mode & 0o111))
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class SyncExportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        tmp = Path(self.tmp.name)
        self.source, self.export, self.root = tmp / "agent-skills", tmp / "export", tmp / "marketplace"
        self.sha = build_source(self.source)
        build_export(self.export, self.sha)
        write(self.root / "overrides/wingman-bundle/README.md", "bundle " + README)
        write(self.root / "sources.json", {"repository": "stackhawk/agent-skills", "plugins": CURATED})
        self.sync = load_sync()
        self.sync.ROOT = self.root
        self.sync.SOURCES_FILE = self.root / "sources.json"

    def run_sync(self, tag=TAG, export=True):
        argv = ["--source-repo", str(self.source), "--tag", tag]
        if export:
            argv += ["--export", str(self.export)]
        with mock.patch("sys.argv", ["sync", *argv]):
            with contextlib.redirect_stdout(io.StringIO()):
                self.sync.main()

    def assert_refused(self, pattern):
        """The sync refuses the export, and the marketplace stays as it was."""
        before = tree_state(self.root)
        with self.assertRaisesRegex(ValueError, pattern):
            self.run_sync()
        self.assertEqual(tree_state(self.root), before)

    def read(self, path):
        return json.loads((self.root / path).read_text())

    # --- The published layout ---

    def test_the_claude_wingman_has_no_cursor_files_and_the_bundle_has_them(self):
        self.run_sync()
        wingman = self.root / "plugins/wingman"
        self.assertEqual(
            sorted(path.relative_to(wingman).as_posix() for path in wingman.rglob("*") if path.is_file()),
            [".claude-plugin/plugin.json", ".codex-plugin/plugin.json", "README.md"],
        )
        bundle = self.root / "bundles/wingman"
        for part in (".cursor-plugin/plugin.json", "rules/stackhawk.mdc", "rules/stackhawk-config.mdc",
                     "hooks/cursor/plugin-hooks.json", "copilot-skills/hawkscan/SKILL.md"):
            self.assertTrue((bundle / part).is_file(), part)
        self.assertTrue(os.access(bundle / "hooks/cursor/stop.sh", os.X_OK))
        # Claude Code reads the bundle's Claude manifest too: it is the snapshot's, with the URLs.
        self.assertEqual(self.read("bundles/wingman/.claude-plugin/plugin.json"),
                         self.read("plugins/wingman/.claude-plugin/plugin.json"))
        self.assertIn("supportUrl", self.read("bundles/wingman/.claude-plugin/plugin.json"))
        self.assertEqual((bundle / "README.md").read_text(), "bundle " + README)

    def test_the_claude_hawkscan_has_no_cursor_files_and_its_cursor_only_folder_has_them(self):
        self.run_sync()
        hawkscan = self.root / "plugins/hawkscan"
        for part in (".cursor-plugin", "rules", "hooks/cursor"):
            self.assertFalse((hawkscan / part).exists(), part)
        self.assertTrue((hawkscan / "hooks/hooks.json").is_file())
        cursor_only = self.root / "cursor-plugins/hawkscan"
        for part in (".cursor-plugin/plugin.json", "rules/stackhawk.mdc", "rules/stackhawk-config.mdc",
                     "hooks/cursor/plugin-hooks.json", "skills/hawkscan/SKILL.md"):
            self.assertTrue((cursor_only / part).is_file(), part)
        self.assertTrue(os.access(cursor_only / "hooks/cursor/stop.sh", os.X_OK))
        self.assertIn(f"version: {VERSION}", (cursor_only / "skills/hawkscan/SKILL.md").read_text())

    def test_the_cursor_catalog_and_installers_are_published(self):
        self.run_sync()
        catalog = self.read(".cursor-plugin/marketplace.json")
        self.assertEqual(
            [(entry["name"], entry["source"]) for entry in catalog["plugins"]],
            [("hawkscan", "./cursor-plugins/hawkscan"), ("stackhawk-api", "./plugins/stackhawk-api"),
             ("wingman", "./bundles/wingman")],
        )
        for name, folder in CURSOR.items():
            manifest = self.read(f"{folder}/.cursor-plugin/plugin.json")
            self.assertEqual((manifest["name"], manifest["version"]), (name, VERSION))
        for name in ("install.sh", "install.ps1", "cursor-legacy-rules.txt"):
            self.assertEqual((self.root / "install" / name).read_bytes(),
                             (self.export / "install" / name).read_bytes(), name)
        self.assertTrue(os.access(self.root / "install/install.sh", os.X_OK))

    def test_the_cursor_files_are_published_byte_for_byte(self):
        self.run_sync()
        for path in (".cursor-plugin/marketplace.json", "cursor-plugins/hawkscan/rules/stackhawk.mdc",
                     "cursor-plugins/hawkscan/hooks/cursor/stop.sh", "bundles/wingman/rules/stackhawk.mdc",
                     "bundles/wingman/hooks/cursor/plugin-hooks.json",
                     "bundles/wingman/.cursor-plugin/plugin.json"):
            self.assertEqual((self.root / path).read_bytes(), (self.export / path).read_bytes(), path)

    def test_a_plugin_the_marketplace_does_not_curate_is_left_out(self):
        build_export(self.export, self.sha, extra_plugin=True)
        self.run_sync()
        self.assertFalse((self.root / "plugins/extra").exists())
        self.assertEqual(sorted(path.name for path in (self.root / "cursor-plugins").iterdir()), ["hawkscan"])
        names = [entry["name"] for entry in self.read(".cursor-plugin/marketplace.json")["plugins"]]
        self.assertEqual(names, list(CURATED))

    def test_the_sync_writes_only_the_published_paths(self):
        git(self.root, "init", "-q")
        commit_and_tag(self.root, "base")
        self.run_sync()
        changed = [line[3:] for line in git(self.root, "status", "--porcelain", "-uall").splitlines()]
        self.assertTrue(changed)
        for path in changed:
            with self.subTest(path=path):
                self.assertTrue(any(path == p or path.startswith(p + "/") for p in PUBLISHED), path)

    def test_the_published_paths_are_the_staging_contract(self):
        # agent-skills scripts/ci/stage-marketplace-sync.sh stages exactly these paths and fails
        # on any other change, so its PUBLISHED list must stay equal to this one.
        self.assertEqual([path.as_posix() for path in self.sync.PUBLISHED], PUBLISHED)

    def test_the_release_layout_checks_pass_on_a_synced_export(self):
        # The Cursor checks of test_release_layout skip on a tree synced without an export, so
        # run them here on a synced one, where a component plugin has no rules or hooks.
        import test_release_layout

        self.run_sync()
        shutil.copyfile(SCRIPT.parent.parent / ".gitattributes", self.root / ".gitattributes")
        with mock.patch.object(test_release_layout, "ROOT", self.root):
            suite = unittest.defaultTestLoader.loadTestsFromTestCase(test_release_layout.CursorLayoutTest)
            result = unittest.TestResult()
            suite.run(result)
        self.assertEqual([str(test) for test, _ in result.errors + result.failures], [])
        self.assertEqual(result.skipped, [])
        self.assertEqual(result.testsRun, suite.countTestCases())

    def test_a_second_sync_of_the_same_export_changes_nothing(self):
        self.run_sync()
        before = tree_state(self.root)
        self.run_sync()
        self.assertEqual(tree_state(self.root), before)

    # --- Refused exports ---

    def test_an_export_of_another_commit_is_refused(self):
        write_manifest(self.export, "0" * 40)
        self.assert_refused("the export is of 0{40}, the tag is")
        self.assertFalse((self.root / "plugins").exists())

    def test_an_export_of_another_version_is_refused(self):
        write_manifest(self.export, self.sha, version="3.4.6")
        self.assert_refused("the export is version 3.4.6")

    def test_an_export_that_maps_a_plugin_to_another_folder_is_refused(self):
        write_manifest(self.export, self.sha, plugins=dict(CURATED, **{"stackhawk-api": "plugins/other"}))
        self.assert_refused("maps stackhawk-api to plugins/other")

    def test_an_export_with_another_bundle_map_is_refused(self):
        write_manifest(self.export, self.sha, bundles={"wingman": "plugins/wingman", "other": "plugins/other"})
        self.assert_refused("bundles")

    def test_an_export_of_an_unknown_format_is_refused(self):
        manifest = json.loads((self.export / "export-manifest.json").read_text())
        for value in (1, 3):
            with self.subTest(format=value):
                write(self.export / "export-manifest.json", dict(manifest, format=value))
                self.assert_refused(f"unknown format {value}")

    def test_a_missing_export_manifest_is_refused(self):
        (self.export / "export-manifest.json").unlink()
        self.assert_refused("export-manifest.json")

    def test_a_changed_export_file_is_refused(self):
        (self.export / "bundles/wingman/rules/stackhawk.mdc").write_text("changed\n")
        self.assert_refused("bundles/wingman/rules/stackhawk.mdc differs from the export manifest")

    def test_an_export_file_with_another_mode_is_refused(self):
        (self.export / "cursor-plugins/hawkscan/hooks/cursor/stop.sh").chmod(0o644)
        self.assert_refused("cursor-plugins/hawkscan/hooks/cursor/stop.sh differs from the export manifest")

    def test_a_listed_file_missing_from_the_export_is_refused(self):
        (self.export / "install/install.ps1").unlink()
        self.assert_refused(r"missing \['install/install.ps1'\]")

    def test_a_file_the_manifest_does_not_list_is_refused(self):
        write(self.export / "plugins/hawkscan/skills/hawkscan/extra.md", "extra\n")
        self.assert_refused(r"not listed \['plugins/hawkscan/skills/hawkscan/extra.md'\]")

    def test_a_symlink_in_the_export_is_refused(self):
        (self.export / "plugins/hawkscan/link.md").symlink_to(self.export / "plugins/hawkscan/README.md")
        self.assert_refused("plugins/hawkscan/link.md is a symlink")

    def test_a_special_file_in_the_export_is_refused_without_reading_it(self):
        os.mkfifo(self.export / "plugins/hawkscan/pipe")
        self.assert_refused("plugins/hawkscan/pipe is not a regular file")

    def test_an_export_without_a_required_file_is_refused(self):
        for path in ("install/install.ps1", ".cursor-plugin/marketplace.json",
                     "plugins/stackhawk-api/.cursor-plugin/plugin.json",
                     "cursor-plugins/hawkscan/.cursor-plugin/plugin.json",
                     "bundles/wingman/.cursor-plugin/plugin.json",
                     "bundles/wingman/.github/plugin/plugin.json"):
            with self.subTest(path=path):
                build_export(self.export, self.sha)
                (self.export / path).unlink()
                write_manifest(self.export, self.sha)
                self.assert_refused(f"the export has no {path}")

    def test_an_unexpected_export_path_is_refused(self):
        for path in ("notes.txt", "install/extra.sh", "bundles/other/README.md", "plugins/unlisted/README.md",
                     ".cursor-plugin/plugin.json", "scripts/sync.py", "cursor-plugins/stackhawk-api/README.md",
                     "cursor-plugins/unlisted/README.md", "cursor-plugins/README.md"):
            with self.subTest(path=path):
                build_export(self.export, self.sha)
                write(self.export / path, "unexpected\n")
                write_manifest(self.export, self.sha)
                self.assert_refused(f"unexpected path in the export: {path}")

    def test_an_unsafe_manifest_path_is_refused(self):
        for path in ("../outside.txt", "/etc/passwd", "plugins/hawkscan/../../x", "plugins/./hawkscan/x"):
            with self.subTest(path=path):
                build_export(self.export, self.sha)
                manifest = json.loads((self.export / "export-manifest.json").read_text())
                manifest["files"].append({"path": path, "mode": "100644", "bytes": 0, "sha256": "0" * 64})
                write(self.export / "export-manifest.json", manifest)
                self.assert_refused("unexpected path in the export")

    def test_bundle_files_in_the_claude_wingman_are_refused(self):
        cases = {
            "rules/stackhawk.mdc": (ROUTER, "carries rules"),
            ".cursor-plugin/plugin.json": ({"name": "wingman"}, "carries .cursor-plugin"),
            "hooks/cursor/plugin-hooks.json": (STOP_HOOKS, "carries hooks/cursor"),
            "copilot-skills/hawkscan/SKILL.md": (skill("hawkscan"), "carries copilot-skills"),
            ".github/plugin/plugin.json": ({"name": "wingman"}, "carries .github"),
            "hooks/hooks.json": ({"hooks": {"Stop": [{"hooks": [{"command": "stop"}]}]}},
                                 "carries a stop hook in hooks/hooks.json"),
        }
        for path, (content, pattern) in cases.items():
            with self.subTest(path=path):
                build_export(self.export, self.sha)
                write(self.export / "plugins/wingman" / path, content)
                write_manifest(self.export, self.sha)
                self.assert_refused(f"the Claude snapshot of wingman {pattern}")

    def test_cursor_files_in_the_claude_snapshot_of_a_cursor_only_plugin_are_refused(self):
        cases = {
            ".cursor-plugin/plugin.json": {"name": "hawkscan"},
            "rules/stackhawk.mdc": ROUTER,
            "hooks/cursor/plugin-hooks.json": STOP_HOOKS,
        }
        for path, content in cases.items():
            with self.subTest(path=path):
                build_export(self.export, self.sha)
                write(self.export / "plugins/hawkscan" / path, content)
                write_manifest(self.export, self.sha)
                part = path.split("/")[0] if not path.startswith("hooks/") else "hooks/cursor"
                self.assert_refused(f"the Claude snapshot of hawkscan carries {part}; .*cursor-plugins/hawkscan")
        build_export(self.export, self.sha)
        write(self.export / "plugins/hawkscan/skills/hawkscan/router.mdc", ROUTER)
        write_manifest(self.export, self.sha)
        self.assert_refused("the Claude snapshot of hawkscan carries a Cursor rule")

    def test_a_cursor_rule_or_hook_in_any_claude_snapshot_is_refused(self):
        # stackhawk-api serves Cursor from its Claude snapshot, so its Cursor manifest may stay,
        # but a rule or a Cursor hook there would load next to the native Cursor install.
        for path, content in (("rules/stackhawk.mdc", ROUTER), ("hooks/cursor/plugin-hooks.json", STOP_HOOKS)):
            with self.subTest(path=path):
                build_export(self.export, self.sha)
                write(self.export / "plugins/stackhawk-api" / path, content)
                write_manifest(self.export, self.sha)
                self.assert_refused("the Claude snapshot of stackhawk-api carries")

    def test_an_export_without_a_cursor_folder_for_a_plugin_is_refused(self):
        cases = {
            "no cursor map": (None, "has no cursor map"),
            "wingman from plugins": (dict(CURSOR, wingman="plugins/wingman"),
                                     "installs wingman in Cursor from plugins/wingman"),
            "a plugin missing": ({k: v for k, v in CURSOR.items() if k != "stackhawk-api"},
                                 "installs stackhawk-api in Cursor from None"),
            "another folder": (dict(CURSOR, hawkscan="bundles/hawkscan"),
                               "installs hawkscan in Cursor from bundles/hawkscan"),
        }
        for label, (cursor, pattern) in cases.items():
            with self.subTest(case=label):
                build_export(self.export, self.sha)
                manifest = json.loads((self.export / "export-manifest.json").read_text())
                if cursor is None:
                    del manifest["cursor"]
                else:
                    manifest["cursor"] = cursor
                write(self.export / "export-manifest.json", manifest)
                self.assert_refused(pattern)

    def test_a_cursor_catalog_that_differs_from_the_cursor_map_is_refused(self):
        entries = [{"name": name, "source": f"./{CURSOR[name]}"} for name in CURATED]
        entries[0]["source"] = "./plugins/hawkscan"
        write(self.export / ".cursor-plugin/marketplace.json", {"name": "stackhawk", "plugins": entries})
        write_manifest(self.export, self.sha)
        self.assert_refused("Cursor catalog source of hawkscan is ./plugins/hawkscan, expected ./cursor-plugins/hawkscan")

    def test_a_claude_hook_without_a_stop_event_in_the_claude_wingman_is_accepted(self):
        write(self.export / "plugins/wingman/hooks/hooks.json",
              {"hooks": {"SessionStart": [{"hooks": [{"command": "start"}]}]}})
        write_manifest(self.export, self.sha)
        self.run_sync()
        self.assertTrue((self.root / "plugins/wingman/hooks/hooks.json").is_file())

    def test_a_second_router_rule_is_refused(self):
        # Any alwaysApply value that is not clearly false makes a router, however it is spelled.
        for value in ("true", "True", "'true'", "yes", "true # second"):
            with self.subTest(value=value):
                build_export(self.export, self.sha)
                write(self.export / "bundles/wingman/rules/second.mdc",
                      f"---\ndescription: second\nalwaysApply: {value}\n---\nrouter\n")
                write_manifest(self.export, self.sha)
                self.assert_refused("Cursor install of wingman loads 2 router rules")

    def test_a_second_router_in_another_spelling_of_the_frontmatter_is_refused(self):
        cases = {
            "a repeated key": "alwaysApply: false\nalwaysApply: true\n",
            "a list value": "alwaysApply:\n  - true\n",
        }
        for label, frontmatter in cases.items():
            with self.subTest(case=label):
                build_export(self.export, self.sha)
                write(self.export / "bundles/wingman/rules/second.mdc",
                      f"---\ndescription: second\n{frontmatter}---\nrouter\n")
                write_manifest(self.export, self.sha)
                self.assert_refused("Cursor install of wingman loads 2 router rules")

    def test_a_rule_file_that_the_manifest_names_counts_whatever_its_suffix(self):
        write(self.export / "bundles/wingman/extra/router.txt", ROUTER)
        manifest = json.loads((self.export / "bundles/wingman/.cursor-plugin/plugin.json").read_text())
        write(self.export / "bundles/wingman/.cursor-plugin/plugin.json",
              dict(manifest, rules=["./rules/", "./extra/router.txt"]))
        write_manifest(self.export, self.sha)
        self.assert_refused("Cursor install of wingman loads 2 router rules")

    def test_a_quoted_hawkscan_skill_name_still_needs_the_router(self):
        write(self.export / "bundles/wingman/copilot-skills/hawkscan/SKILL.md",
              skill("hawkscan").replace("name: hawkscan", 'name: "hawkscan"'))
        write(self.export / "bundles/wingman/rules/stackhawk.mdc", CONFIG_RULE)
        write_manifest(self.export, self.sha)
        self.assert_refused("carries the hawkscan skill with 0 router rules")

    def test_a_rule_that_is_clearly_not_always_applied_is_accepted(self):
        for value in ("false", "False", "no", "off", "0", '"false"', "|\n  false"):
            with self.subTest(value=value):
                build_export(self.export, self.sha)
                write(self.export / "bundles/wingman/rules/other.mdc",
                      f"---\ndescription: other\nalwaysApply: {value}\n---\nother\n")
                write_manifest(self.export, self.sha)
                self.run_sync()

    def test_a_cursor_install_of_hawkscan_without_one_router_and_one_stop_hook_is_refused(self):
        cases = {
            "no router": ("bundles/wingman/rules/stackhawk.mdc", CONFIG_RULE, "0 router rules"),
            "no stop hook": ("bundles/wingman/hooks/cursor/plugin-hooks.json",
                             {"version": 1, "hooks": {"stop": []}}, "0 stop hooks"),
            "two stop hooks": ("cursor-plugins/hawkscan/hooks/cursor/plugin-hooks.json",
                               {"version": 1, "hooks": {"stop": STOP_HOOKS["hooks"]["stop"] * 2}},
                               "2 stop hooks"),
            "a Claude stop hook too": ("cursor-plugins/hawkscan/hooks/cursor/plugin-hooks.json",
                                       {"version": 1, "hooks": {
                                           "stop": STOP_HOOKS["hooks"]["stop"],
                                           "Stop": [{"hooks": [{"command": STOP_COMMAND}]}]}},
                                       "2 stop hooks"),
        }
        for label, (path, content, pattern) in cases.items():
            with self.subTest(case=label):
                build_export(self.export, self.sha)
                write(self.export / path, content)
                write_manifest(self.export, self.sha)
                self.assert_refused(pattern)

    def test_a_stop_hook_that_cursor_cannot_run_is_refused(self):
        cases = {
            "relative command": ("./hooks/cursor/stop.sh", "does not start with"),
            "missing script": ('"${CURSOR_PLUGIN_ROOT}/hooks/cursor/gone.sh"', "missing or not executable"),
        }
        for label, (command, pattern) in cases.items():
            with self.subTest(case=label):
                build_export(self.export, self.sha)
                write(self.export / "bundles/wingman/hooks/cursor/plugin-hooks.json",
                      {"version": 1, "hooks": {"stop": [{"command": command}]}})
                write_manifest(self.export, self.sha)
                self.assert_refused(pattern)

    def test_a_cursor_manifest_path_that_does_not_exist_is_refused(self):
        manifest = json.loads((self.export / "bundles/wingman/.cursor-plugin/plugin.json").read_text())
        write(self.export / "bundles/wingman/.cursor-plugin/plugin.json", dict(manifest, rules="./gone/"))
        write_manifest(self.export, self.sha)
        self.assert_refused("names ./gone/, which does not exist")

    def test_a_cursor_catalog_that_points_elsewhere_or_misses_a_plugin_is_refused(self):
        cases = {
            "wingman from plugins": ([{"name": "hawkscan", "source": "./cursor-plugins/hawkscan"},
                                      {"name": "stackhawk-api", "source": "./plugins/stackhawk-api"},
                                      {"name": "wingman", "source": "./plugins/wingman"}],
                                     "Cursor catalog source of wingman is ./plugins/wingman"),
            "no stackhawk-api": ([{"name": "hawkscan", "source": "./cursor-plugins/hawkscan"},
                                  {"name": "wingman", "source": "./bundles/wingman"}],
                                 "Cursor catalog of the export has no stackhawk-api"),
        }
        for label, (entries, pattern) in cases.items():
            with self.subTest(case=label):
                build_export(self.export, self.sha)
                write(self.export / ".cursor-plugin/marketplace.json", {"name": "stackhawk", "plugins": entries})
                write_manifest(self.export, self.sha)
                self.assert_refused(pattern)

    def test_a_refused_export_leaves_an_earlier_sync_as_it_was(self):
        self.run_sync()
        (self.export / "install/install.sh").write_text("changed\n")
        self.assert_refused("install/install.sh differs from the export manifest")


class SyncWithoutExportTest(unittest.TestCase):
    """The sync without --export stays for tags older than the export."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        tmp = Path(self.tmp.name)
        self.source, self.export, self.root = tmp / "agent-skills", tmp / "export", tmp / "marketplace"
        write(self.root / "overrides/wingman-bundle/README.md", "bundle " + README)
        write(self.root / "sources.json", {"repository": "stackhawk/agent-skills", "plugins": CURATED})
        self.sync = load_sync()
        self.sync.ROOT = self.root
        self.sync.SOURCES_FILE = self.root / "sources.json"

    def run_sync(self, tag, export=False):
        argv = ["--source-repo", str(self.source), "--tag", tag]
        if export:
            argv += ["--export", str(self.export)]
        with mock.patch("sys.argv", ["sync", *argv]):
            with contextlib.redirect_stdout(io.StringIO()):
                self.sync.main()

    def test_a_tag_without_the_cursor_adapter_syncs_as_before(self):
        build_source(self.source)
        self.run_sync(TAG)
        self.assertTrue((self.root / "bundles/wingman/copilot-skills/hawkscan/SKILL.md").is_file())
        self.assertFalse((self.root / "plugins/wingman/copilot-skills").exists())
        self.assertFalse((self.root / ".cursor-plugin").exists())
        self.assertFalse((self.root / "install").exists())

    def test_a_tag_with_the_cursor_adapter_needs_the_export(self):
        build_source(self.source, cursor_adapter=True)
        with self.assertRaisesRegex(ValueError, "wingman: the tag carries Cursor files .*--export"):
            self.run_sync(TAG)
        self.assertFalse((self.root / "plugins").exists())

    def test_a_later_sync_without_the_export_removes_the_cursor_outputs(self):
        sha = build_source(self.source)
        build_export(self.export, sha)
        self.run_sync(TAG, export=True)
        self.assertTrue((self.root / "install/install.sh").is_file())
        write(self.source / "plugins/hawkscan/NOTES.md", "a later commit\n")
        commit_and_tag(self.source, "v3.4.6")
        self.run_sync("v3.4.6")
        self.assertFalse((self.root / ".cursor-plugin/marketplace.json").exists())
        self.assertFalse((self.root / "install").exists())
        self.assertFalse((self.root / "cursor-plugins").exists())
        self.assertEqual(list(self.root.glob("**/.cursor-plugin/plugin.json")), [])

    def test_a_failed_install_restores_every_path(self):
        sha = build_source(self.source)
        build_export(self.export, sha)
        self.run_sync(TAG, export=True)
        before = tree_state(self.root)
        write(self.source / "plugins/hawkscan/NOTES.md", "a later commit\n")
        commit_and_tag(self.source, "v3.4.6")
        real_replace = os.replace

        def failing_replace(src, dst):
            # Fail once the old paths are moved aside and install/ is already removed.
            if ".sync-stage-" in str(src) and str(src).endswith(".codex-plugin/marketplace.json"):
                raise OSError("disk full")
            return real_replace(src, dst)

        with mock.patch.object(self.sync.os, "replace", failing_replace):
            with self.assertRaisesRegex(OSError, "disk full"):
                self.run_sync("v3.4.6")
        self.assertEqual(tree_state(self.root), before)
        self.assertEqual(list(self.root.glob(".sync-*")), [])

    def test_an_interrupted_install_restores_every_path(self):
        sha = build_source(self.source)
        build_export(self.export, sha)
        self.run_sync(TAG, export=True)
        before = tree_state(self.root)
        real_replace = os.replace

        def interrupted_replace(src, dst):
            if ".sync-stage-" in str(src) and str(src).endswith("sources.json"):
                raise KeyboardInterrupt
            return real_replace(src, dst)

        with mock.patch.object(self.sync.os, "replace", interrupted_replace):
            with self.assertRaises(KeyboardInterrupt):
                self.run_sync(TAG, export=True)
        self.assertEqual(tree_state(self.root), before)

    def test_a_failed_restore_keeps_the_backup_and_names_it(self):
        sha = build_source(self.source)
        build_export(self.export, sha)
        self.run_sync(TAG, export=True)
        old_installer = (self.root / "install/install.sh").read_bytes()
        real_replace = os.replace

        def failing_replace(src, dst):
            if ".sync-stage-" in str(src) and str(src).endswith("sources.json"):
                raise OSError("disk full")
            if ".sync-backup-" in str(src) and str(src).endswith("install"):
                raise OSError("still full")
            return real_replace(src, dst)

        with mock.patch.object(self.sync.os, "replace", failing_replace):
            with self.assertRaisesRegex(RuntimeError, r"could not restore install; the old files are in .*\.sync-backup-"):
                self.run_sync(TAG, export=True)
        backups = list(self.root.glob(".sync-backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "install/install.sh").read_bytes(), old_installer)
        self.assertTrue((self.root / "plugins").is_dir())


if __name__ == "__main__":
    unittest.main()
