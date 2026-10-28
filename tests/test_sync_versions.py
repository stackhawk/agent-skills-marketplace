"""Check that the sync takes the release version from the tag, not the tree."""

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "sync-agent-skills.py"
README = "word " * 50


def load_sync():
    spec = importlib.util.spec_from_file_location("sync_agent_skills", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if isinstance(text, str) else json.dumps(text, indent=2) + "\n")


def skill(name, version):
    return f"---\nname: {name}\nversion: {version}\ndescription: test\n---\nversion: 99\n"


def build_source(repo, in_tree_version):
    """A minimal agent-skills tree whose in-tree versions are `in_tree_version`."""
    manifest = lambda name, **extra: {"name": name, "version": in_tree_version, **extra}
    write(repo / "plugins/hawkscan/.claude-plugin/plugin.json", manifest("hawkscan"))
    write(repo / "plugins/hawkscan/skills/hawkscan/SKILL.md", skill("hawkscan", in_tree_version))
    write(repo / "plugins/hawkscan/README.md", README)
    wingman = repo / "plugins/wingman"
    write(wingman / ".claude-plugin/plugin.json", manifest("wingman", dependencies=["hawkscan"]))
    write(wingman / ".codex-plugin/plugin.json", manifest("wingman"))
    write(wingman / ".github/plugin/plugin.json", manifest("wingman", skills="./copilot-skills/"))
    write(wingman / "copilot-skills/hawkscan/SKILL.md", skill("hawkscan", in_tree_version))
    write(wingman / "README.md", README)
    catalog = {
        "name": "stackhawk",
        "plugins": [
            {"name": name, "source": f"./plugins/{name}", "version": in_tree_version}
            for name in ("hawkscan", "wingman")
        ],
    }
    write(repo / ".claude-plugin/marketplace.json", catalog)
    write(repo / ".codex-plugin/marketplace.json", catalog)
    # No VERSION file: the tag is the only place the release number lives.
    run = lambda *args: subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True
    )
    run("init", "-q")
    run("add", "-A")
    run("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "release")


class SyncVersionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        tmp = Path(self.tmp.name)
        self.source = tmp / "agent-skills"
        self.root = tmp / "marketplace"
        write(self.root / "overrides/wingman-bundle/README.md", README)
        write(self.root / "sources.json", {
            "repository": "stackhawk/agent-skills",
            "plugins": {"hawkscan": "plugins/hawkscan", "wingman": "plugins/wingman"},
        })
        self.sync = load_sync()
        self.sync.ROOT = self.root
        self.sync.SOURCES_FILE = self.root / "sources.json"

    def run_sync(self, in_tree_version, tag="v3.4.5"):
        build_source(self.source, in_tree_version)
        subprocess.run(["git", "-C", str(self.source), "tag", tag], check=True)
        argv = ["--source-repo", str(self.source), "--tag", tag]
        with mock.patch("sys.argv", ["sync", *argv]):
            self.sync.main()

    def versions(self):
        found = {}
        for path in sorted(self.root.glob("**/plugin.json")):
            found[str(path.relative_to(self.root))] = json.loads(path.read_text())["version"]
        for path in sorted(self.root.glob("**/SKILL.md")):
            frontmatter = path.read_text().split("---\n")[1]
            found[str(path.relative_to(self.root))] = next(
                line.split(":", 1)[1].strip()
                for line in frontmatter.splitlines() if line.startswith("version:")
            )
        return found

    def assert_stamped(self, version):
        found = self.versions()
        self.assertIn("bundles/wingman/copilot-skills/hawkscan/SKILL.md", found)
        self.assertIn("bundles/wingman/.github/plugin/plugin.json", found)
        self.assertIn("skills/hawkscan/SKILL.md", found)
        self.assertEqual(set(found.values()), {version}, found)
        for catalog in (".claude-plugin", ".github/plugin", ".agents/plugins", ".codex-plugin"):
            entries = json.loads((self.root / catalog / "marketplace.json").read_text())["plugins"]
            self.assertEqual({entry["version"] for entry in entries}, {version})
        # Only the frontmatter line changes; body text stays as upstream wrote it.
        body = (self.root / "skills/hawkscan/SKILL.md").read_text()
        self.assertTrue(body.endswith("---\nversion: 99\n"))

    def test_placeholder_versions_are_stamped_from_the_tag(self):
        self.run_sync("0.0.0")
        self.assert_stamped("3.4.5")
        sources = json.loads((self.root / "sources.json").read_text())
        self.assertEqual(sources["tag"], "v3.4.5")
        self.assertRegex(sources["sha"], r"^[0-9a-f]{40}$")

    def test_in_tree_versions_that_already_match_still_work(self):
        self.run_sync("3.4.5")
        self.assert_stamped("3.4.5")

    def test_moved_tag_is_still_rejected(self):
        self.run_sync("0.0.0")
        sources = json.loads((self.root / "sources.json").read_text())
        sources["sha"] = "0" * 40
        write(self.root / "sources.json", sources)
        with self.assertRaisesRegex(ValueError, "moved"):
            with mock.patch(
                "sys.argv",
                ["sync", "--source-repo", str(self.source), "--tag", "v3.4.5"],
            ):
                self.sync.main()


if __name__ == "__main__":
    unittest.main()
