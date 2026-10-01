#!/usr/bin/env python3
"""Regenerate the marketplace from a tagged local agent-skills checkout."""

import argparse
import copy
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile


ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = ROOT / "sources.json"
GIT_REPO = "stackhawk/agent-skills"
URL_FIELDS = {
    "privacyPolicyUrl": "https://www.stackhawk.com/privacy-policy/",
    "termsOfServiceUrl": "https://www.stackhawk.com/terms-of-service/",
    "supportUrl": "https://docs.stackhawk.com/support/",
    "documentationUrl": "https://docs.stackhawk.com/ai-security/agent-skills/claude-code/",
}
BUNDLE_NAME = "wingman"
BUNDLE_SKILLS = "./copilot-skills/"
SKILLS_README = """# GENERATED - do not edit

Produced by `scripts/sync-agent-skills.py` from the pinned `agent-skills` tag.
Edit source skills in `stackhawk/agent-skills` and run the sync script for a new
release. These copies serve the `skills` CLI, which ignores plugin catalogs.
Claude Code, Codex, and Copilot install plugins through their catalogs.
"""


def git(repo, *args):
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, check=True
    )
    return result.stdout


def git_json(repo, sha, path):
    return json.loads(git(repo, "show", f"{sha}:{path}"))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def extract_plugins(repo, sha, paths, destination):
    archive = git(repo, "archive", sha, *paths)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar:
            relative = PurePosixPath(member.name)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError(f"Unsafe archive path: {member.name}")
            target = destination.joinpath(*relative.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                source = tar.extractfile(member)
                if source is None:
                    raise ValueError(f"Cannot read archive file: {member.name}")
                target.write_bytes(source.read())
                target.chmod(member.mode & 0o777)
            else:
                raise ValueError(f"Unsupported archive entry: {member.name}")


def checked_source_path(entry, expected):
    source = entry["source"]
    actual = source["path"] if isinstance(source, dict) else source
    if actual.removeprefix("./") != expected:
        raise ValueError(f"{entry['name']} source is {actual}, expected {expected}")


def prepare_plugins(stage, archive_root, plugins, version):
    for name, upstream_path in plugins.items():
        destination = stage / "plugins" / name
        shutil.copytree(archive_root / upstream_path, destination)
        manifest_path = destination / ".claude-plugin" / "plugin.json"
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("name") != name or manifest.get("version") != version:
            raise ValueError(
                f"{upstream_path} manifest name or version differs from {name} {version}"
            )
        if name == "wingman":
            dependencies = manifest.get("dependencies", [])
            if not dependencies or any(dependency not in plugins for dependency in dependencies):
                raise ValueError("wingman dependencies must name plugins in this marketplace")
        manifest.update(URL_FIELDS)
        write_json(manifest_path, manifest)

        readme = destination / "README.md"
        if not readme.is_file():
            override = ROOT / "overrides" / name / "README.md"
            if not override.is_file():
                raise ValueError(f"{name} needs a README.md for directory submission")
            shutil.copyfile(override, readme)
        text = readme.read_text()
        text = text.replace(
            "/plugin marketplace add stackhawk/claude-skills",
            "/plugin marketplace add stackhawk/agent-skills-marketplace",
        ).replace(
            "/plugin marketplace add stackhawk/agent-skills\n",
            "/plugin marketplace add stackhawk/agent-skills-marketplace\n",
        ).replace(
            f"/plugin install {PurePosixPath(upstream_path).name}@stackhawk",
            f"/plugin install {name}@stackhawk",
        ).replace(
            "https://support.stackhawk.com", URL_FIELDS["supportUrl"]
        )
        readme.write_text(text)
        if len(re.findall(r"\b[\w-]+\b", readme.read_text())) < 40:
            raise ValueError(f"{name} README.md has fewer than 40 words")
        if name == BUNDLE_NAME:
            split_bundle(stage, destination, manifest["dependencies"])


def split_bundle(stage, snapshot, dependencies):
    """Move wingman's bundled skills out of the folders the Claude catalog lists.

    Copilot and Codex have no plugin dependencies, so they install the bundle
    with copies of the dependency skills. Claude installs the dependencies, and
    the directory reviews every folder its catalog lists, so its snapshot keeps
    only the manifests and README. The upstream README describes the Claude
    install, so the bundle gets its own README from overrides/.
    """
    bundle = stage / "bundles" / BUNDLE_NAME
    shutil.copytree(snapshot, bundle)
    bundle_readme = ROOT / "overrides" / f"{BUNDLE_NAME}-bundle" / "README.md"
    if not bundle_readme.is_file():
        raise ValueError(f"{BUNDLE_NAME} bundle needs {bundle_readme.relative_to(ROOT)}")
    shutil.copyfile(bundle_readme, bundle / "README.md")
    copilot_manifest = json.loads((bundle / ".github" / "plugin" / "plugin.json").read_text())
    if copilot_manifest.get("skills") != BUNDLE_SKILLS:
        raise ValueError(f"{BUNDLE_NAME} Copilot manifest must load {BUNDLE_SKILLS}")
    # Codex ignores dependencies too. Remove this when stackhawk/agent-skills
    # scripts/generate-wingman-skills.sh writes the key in a released tag.
    codex_path = bundle / ".codex-plugin" / "plugin.json"
    codex_manifest = json.loads(codex_path.read_text())
    if codex_manifest.setdefault("skills", BUNDLE_SKILLS) != BUNDLE_SKILLS:
        raise ValueError(f"{BUNDLE_NAME} Codex manifest must load {BUNDLE_SKILLS}")
    write_json(codex_path, codex_manifest)
    bundled = set()
    for skill_file in (bundle / BUNDLE_SKILLS).glob("*/SKILL.md"):
        match = re.search(r"^name:[ \t]*(\S+)", skill_file.read_text(), flags=re.MULTILINE)
        if not match:
            raise ValueError(f"{skill_file} has no frontmatter name")
        bundled.add(match.group(1))
    if bundled != set(dependencies):
        raise ValueError(f"{BUNDLE_NAME} bundles {sorted(bundled)}, expected {sorted(dependencies)}")
    shutil.rmtree(snapshot / BUNDLE_SKILLS)
    shutil.rmtree(snapshot / ".github")


def prepare_standalone_skills(stage, plugins):
    skills_root = stage / "skills"
    skills_root.mkdir()
    for name in plugins:
        if name == "wingman":
            continue
        candidates = list((stage / "plugins" / name / "skills").glob("*/SKILL.md"))
        if len(candidates) != 1:
            raise ValueError(f"{name} must have exactly one standalone skill")
        shutil.copytree(candidates[0].parent, skills_root / name)
        skill_file = skills_root / name / "SKILL.md"
        text = skill_file.read_text()
        text, count = re.subn(
            r"^name:[ \t]*.*$", f"name: {name}", text, count=1, flags=re.MULTILINE
        )
        if count != 1:
            raise ValueError(f"{name} skill has no frontmatter name")
        skill_file.write_text(text)
    (skills_root / "README.md").write_text(SKILLS_README)


def prepare_catalogs(stage, repo, sha, tag, plugins):
    version = tag[1:]
    claude_source = git_json(repo, sha, ".claude-plugin/marketplace.json")
    codex_source = git_json(repo, sha, ".codex-plugin/marketplace.json")
    claude_entries = {entry["name"]: entry for entry in claude_source["plugins"]}
    codex_entries = {entry["name"]: entry for entry in codex_source["plugins"]}
    if not set(plugins).issubset(claude_entries) or not set(plugins).issubset(codex_entries):
        raise ValueError("An upstream catalog is missing a curated plugin")

    claude = {
        key: copy.deepcopy(value)
        for key, value in claude_source.items()
        if key != "homepage"
    }
    copilot = copy.deepcopy(claude)
    codex = copy.deepcopy(codex_source)
    claude["plugins"] = []
    copilot["plugins"] = []
    codex["plugins"] = []
    for name, upstream_path in plugins.items():
        original = claude_entries[name]
        checked_source_path(original, upstream_path)
        entry = copy.deepcopy(original)
        entry["source"] = f"./plugins/{name}"
        entry["version"] = version
        claude["plugins"].append(entry)

        # The marketplace commit that a user clones pins every relative source.
        local_path = f"./bundles/{name}" if name == BUNDLE_NAME else f"./plugins/{name}"
        copilot_entry = copy.deepcopy(original)
        copilot_entry["source"] = local_path
        copilot_entry["version"] = version
        copilot["plugins"].append(copilot_entry)

        codex_original = codex_entries[name]
        checked_source_path(codex_original, upstream_path)
        codex_entry = copy.deepcopy(codex_original)
        codex_entry["source"] = {"source": "local", "path": local_path}
        codex_entry["version"] = version
        codex_entry.setdefault("description", original.get("description"))
        codex_entry.setdefault("homepage", original.get("homepage"))
        codex["plugins"].append(codex_entry)

    write_json(stage / ".claude-plugin" / "marketplace.json", claude)
    write_json(stage / ".github" / "plugin" / "marketplace.json", copilot)
    write_json(stage / ".agents" / "plugins" / "marketplace.json", codex)
    write_json(stage / ".codex-plugin" / "marketplace.json", codex)


def install(stage):
    paths = [
        Path("plugins"), Path("bundles"), Path("skills"), Path("sources.json"),
        Path(".claude-plugin/marketplace.json"),
        Path(".github/plugin/marketplace.json"),
        Path(".agents/plugins/marketplace.json"),
        Path(".codex-plugin/marketplace.json"),
    ]
    with tempfile.TemporaryDirectory(prefix=".sync-backup-", dir=ROOT) as backup_name:
        backup = Path(backup_name)
        touched = []
        try:
            for relative in paths:
                target = ROOT / relative
                old = backup / relative
                new = stage / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    old.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(target, old)
                touched.append(relative)
                os.replace(new, target)
        except OSError:
            for relative in reversed(touched):
                target = ROOT / relative
                if target.is_dir():
                    shutil.rmtree(target)
                elif target.exists():
                    target.unlink()
                old = backup / relative
                if old.exists():
                    os.replace(old, target)
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-repo", required=True, type=Path,
        help="Local agent-skills Git checkout",
    )
    parser.add_argument("--tag", required=True, help="Release tag, for example v2.5.1")
    args = parser.parse_args()
    match = re.fullmatch(r"v(\d+\.\d+\.\d+)", args.tag)
    if not match:
        parser.error("--tag must be a vX.Y.Z release tag")
    version = match.group(1)
    source = json.loads(SOURCES_FILE.read_text())
    if source.get("repository") != GIT_REPO:
        raise ValueError(f"sources.json repository must be {GIT_REPO}")
    plugins = source["plugins"]
    if not plugins or any(not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) for name in plugins):
        raise ValueError("sources.json has an invalid plugin name")
    if any(not re.fullmatch(r"plugins/[a-z0-9-]+", path) for path in plugins.values()):
        raise ValueError("sources.json has an invalid upstream path")
    sha = git(args.source_repo, "rev-parse", f"{args.tag}^{{commit}}").decode().strip()
    if source.get("tag") == args.tag and source.get("sha") != sha:
        raise ValueError(f"Tag {args.tag} moved from recorded SHA {source['sha']} to {sha}")
    source_version = git(args.source_repo, "show", f"{sha}:VERSION").decode().strip()
    if source_version != version:
        raise ValueError(f"Tag {args.tag} has VERSION={source_version}, expected {version}")

    with tempfile.TemporaryDirectory(prefix=".sync-stage-", dir=ROOT) as stage_name:
        stage = Path(stage_name)
        archive_root = stage / "upstream"
        archive_root.mkdir()
        extract_plugins(args.source_repo, sha, list(plugins.values()), archive_root)
        prepare_plugins(stage, archive_root, plugins, version)
        prepare_standalone_skills(stage, plugins)
        prepare_catalogs(stage, args.source_repo, sha, args.tag, plugins)
        source["tag"] = args.tag
        source["sha"] = sha
        write_json(stage / "sources.json", source)
        install(stage)
    skill_count = len(plugins) - int("wingman" in plugins)
    print(
        f"Synced {len(plugins)} plugins and {skill_count} standalone skills "
        f"from {args.tag} ({sha})"
    )


if __name__ == "__main__":
    main()
