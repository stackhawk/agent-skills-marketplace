#!/usr/bin/env python3
"""Regenerate the marketplace from a tagged local agent-skills checkout.

With --export, the sync publishes the payload that agent-skills scripts/export-marketplace.py
wrote for the tag: the Claude plugin snapshots, the Wingman bundle, the Cursor-only plugins, the
Cursor catalog and the installers. It checks the payload against its manifest before it reads it. Without --export,
it copies the plugin folders of the tag; that path is for tags older than the export, and it
refuses a tag that carries the Cursor adapter.
"""

import argparse
import copy
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
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
# The parts of wingman that only its bundle carries. Claude Code installs the dependencies of
# wingman, and the Cursor app imports Claude Code plugins by default (inferred from its 3.9.16
# code), so these parts in the Claude snapshot would load the dependency skills, the router rule
# or the stop hook a second time.
BUNDLE_ONLY = ("copilot-skills", ".github", ".cursor-plugin", "rules", "hooks/cursor")
EXPORT_MANIFEST = "export-manifest.json"
# Format 2 added the Cursor-only plugins (cursor-plugins/<name>) and the "cursor" map, which
# names the folder that the Cursor catalog installs each plugin from.
EXPORT_FORMAT = 2
EXPORT_MODES = {"100644", "100755"}
CURSOR_CATALOG = Path(".cursor-plugin/marketplace.json")
CURSOR_MANIFEST = Path(".cursor-plugin/plugin.json")
CURSOR_ROOT = "${CURSOR_PLUGIN_ROOT}/"
INSTALLERS = Path("install")
# A plugin whose Cursor install is not its Claude snapshot: wingman from its bundle, and each
# plugin of the export that Cursor installs from cursor-plugins/<name>. The Cursor app and the
# Cursor CLI import Claude Code plugins, so the Claude snapshot of such a plugin carries no
# Cursor file, and no Claude snapshot carries a Cursor rule or Cursor hook.
CURSOR_ONLY_ROOT = "cursor-plugins"
CURSOR_PARTS = (".cursor-plugin", "rules", "hooks/cursor")
CURSOR_RULES_AND_HOOKS = ("rules", "hooks/cursor")
INSTALLER_FILES = ("install.sh", "install.ps1", "cursor-legacy-rules.txt")
ROUTER_SKILL = "hawkscan"
RULE_SUFFIXES = (".mdc", ".md", ".markdown")
NOT_ALWAYS_APPLIED = {"", "false", "no", "off", "0"}
# Every path the sync writes; install() replaces each one. agent-skills
# scripts/ci/stage-marketplace-sync.sh stages exactly these paths and fails on any other change,
# so its PUBLISHED list must stay equal to this one.
PUBLISHED = (
    Path("plugins"), Path("bundles"), Path(CURSOR_ONLY_ROOT), Path("skills"), INSTALLERS, Path("sources.json"),
    Path(".claude-plugin/marketplace.json"), Path(".github/plugin/marketplace.json"),
    Path(".agents/plugins/marketplace.json"), Path(".codex-plugin/marketplace.json"),
    CURSOR_CATALOG,
)
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


def cursor_folder_choices(name):
    """The folders Cursor may install a catalog plugin from: wingman from its bundle, any other
    plugin from its Claude snapshot or from its Cursor-only folder."""
    if name == BUNDLE_NAME:
        return [f"bundles/{name}"]
    return [f"plugins/{name}", f"{CURSOR_ONLY_ROOT}/{name}"]


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


def refuse_cursor_adapter(archive_root, plugins):
    """Without --export, take only a tag older than the Cursor adapter.

    That path copies the tag's plugin folders as they are: the Claude wingman would carry the
    router rule and the stop hook, which Cursor loads a second time when it imports Claude Code
    plugins, and no Cursor catalog or installer would ship.
    """
    for name, upstream_path in plugins.items():
        parts = [CURSOR_MANIFEST.as_posix()]
        if name == BUNDLE_NAME:
            parts += ["rules", "hooks/cursor"]
        found = [part for part in parts if (archive_root / upstream_path / part).exists()]
        if found:
            raise ValueError(
                f"{name}: the tag carries Cursor files ({', '.join(found)}); "
                "sync it with --export and the agent-skills export of the tag"
            )


# --- The agent-skills export ---

def read_export_manifest(export):
    path = export / EXPORT_MANIFEST
    try:
        manifest = json.loads(path.read_text())
    except (OSError, ValueError) as problem:
        raise ValueError(f"cannot read the export manifest {path}: {problem}") from problem
    if not isinstance(manifest, dict):
        raise ValueError(f"{path} is not a JSON object")
    return manifest


def export_path_allowed(path, exported, cursor):
    """True for a path inside the export layout: plugins/<exported name>/, bundles/wingman/,
    cursor-plugins/<name>/ of a plugin that the cursor map installs from there, the Cursor
    catalog and the three installer files."""
    parts = path.split("/")
    if "\\" in path or any(part in ("", ".", "..") for part in parts):
        return False
    if path == CURSOR_CATALOG.as_posix():
        return True
    if parts[0] == INSTALLERS.as_posix():
        return len(parts) == 2 and parts[1] in INSTALLER_FILES
    if parts[0] == "plugins":
        return len(parts) > 2 and parts[1] in exported
    if parts[0] == "bundles":
        return len(parts) > 2 and parts[1] == BUNDLE_NAME
    if parts[0] == CURSOR_ONLY_ROOT:
        return len(parts) > 2 and parts[1] in exported and cursor.get(parts[1]) == f"{CURSOR_ONLY_ROOT}/{parts[1]}"
    return False


def required_export_files(plugins, cursor):
    """The files the published layout needs from the export."""
    required = {CURSOR_CATALOG.as_posix()}
    required.update(f"{INSTALLERS.as_posix()}/{name}" for name in INSTALLER_FILES)
    for name in plugins:
        required.add(f"plugins/{name}/.claude-plugin/plugin.json")
        required.add(f"{cursor[name]}/{CURSOR_MANIFEST.as_posix()}")
    if BUNDLE_NAME in plugins:
        bundle = cursor[BUNDLE_NAME]
        for manifest in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json", ".github/plugin/plugin.json"):
            required.add(f"{bundle}/{manifest}")
    return required


def listed_export_files(manifest):
    """path -> (mode, bytes, sha256) of every file the export manifest lists."""
    listed = {}
    for item in manifest.get("files") or []:
        valid = (
            isinstance(item, dict) and isinstance(item.get("path"), str)
            and item.get("mode") in EXPORT_MODES and isinstance(item.get("bytes"), int)
            and re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256")))
        )
        if not valid or item["path"] in listed:
            raise ValueError(f"{EXPORT_MANIFEST} has an invalid or repeated file entry: {item}")
        listed[item["path"]] = (item["mode"], item["bytes"], item["sha256"])
    return listed


def export_entries(export):
    """(relative path, is a folder) of every entry under export. Refuses a symlink or a special
    file (a FIFO would block a read) before anything reads it."""
    for dirpath, dirnames, filenames in os.walk(export):
        dirnames.sort()
        for name in sorted(dirnames + filenames):
            full = Path(dirpath) / name
            rel = full.relative_to(export).as_posix()
            mode = os.lstat(full).st_mode
            if stat.S_ISLNK(mode):
                raise ValueError(f"{rel} is a symlink; the export holds regular files only")
            if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise ValueError(f"{rel} is not a regular file; the export holds regular files only")
            yield rel, stat.S_ISDIR(mode)


def copy_export(source, destination):
    """Copy an export into the stage, so the sync checks and publishes the same bytes."""
    if not source.is_dir():
        raise ValueError(f"the export {source} is not a folder")
    destination.mkdir()
    for rel, is_folder in list(export_entries(source)):
        if is_folder:
            (destination / rel).mkdir()
        else:
            shutil.copy2(source / rel, destination / rel)


def check_export_files(export, listed):
    """The export holds exactly the listed files, as regular files with the listed content."""
    found = {rel for rel, is_folder in export_entries(export) if not is_folder} - {EXPORT_MANIFEST}
    missing, unlisted = sorted(set(listed) - found), sorted(found - set(listed))
    if missing or unlisted:
        raise ValueError(f"the export files differ from its manifest: missing {missing}, not listed {unlisted}")
    for rel, expected in sorted(listed.items()):
        full = export / rel
        data = full.read_bytes()
        mode = "100755" if full.stat().st_mode & 0o111 else "100644"
        if (mode, len(data), hashlib.sha256(data).hexdigest()) != expected:
            raise ValueError(f"{rel} differs from the export manifest")


def load_export(export, sha, version, plugins):
    """Check an agent-skills export (its scripts/export-marketplace.py) before it is used.

    The export is the payload of one agent-skills commit: Claude-oriented plugin snapshots
    named by catalog name, the Wingman bundle, the Cursor-only plugins, the Cursor catalog and
    the installers. It must be of the tag's commit and version, map every curated plugin to its
    upstream folder in sources.json, and name the folder Cursor installs it from. It must hold
    exactly the files its manifest lists, each with the listed sha256, size and mode, only
    inside the export layout, and every file the published layout needs. A plugin of the export
    that sources.json does not curate is not published.

    Returns the folder that Cursor installs each curated plugin from.
    """
    manifest = read_export_manifest(export)
    if manifest.get("format") != EXPORT_FORMAT:
        raise ValueError(f"{EXPORT_MANIFEST} has an unknown format {manifest.get('format')!r}")
    commit = (manifest.get("source") or {}).get("commit")
    if commit != sha:
        raise ValueError(f"the export is of {commit}, the tag is {sha}")
    if manifest.get("version") != version:
        raise ValueError(f"the export is version {manifest.get('version')}, the tag is {version}")
    exported = manifest.get("plugins") or {}
    for name, upstream_path in plugins.items():
        if exported.get(name) != upstream_path:
            raise ValueError(f"the export maps {name} to {exported.get(name)}, sources.json to {upstream_path}")
    if manifest.get("bundles") != {BUNDLE_NAME: exported.get(BUNDLE_NAME)}:
        raise ValueError(f"the export bundles {manifest.get('bundles')}, expected only {BUNDLE_NAME}")
    cursor = manifest.get("cursor")
    if not isinstance(cursor, dict):
        raise ValueError(f"{EXPORT_MANIFEST} has no cursor map")
    for name in plugins:
        if cursor.get(name) not in cursor_folder_choices(name):
            raise ValueError(f"the export installs {name} in Cursor from {cursor.get(name)}, "
                             f"expected one of {cursor_folder_choices(name)}")
    listed = listed_export_files(manifest)
    for rel in sorted(listed):
        if not export_path_allowed(rel, exported, cursor):
            raise ValueError(f"unexpected path in the export: {rel}")
    curated = {name: cursor[name] for name in plugins}
    for rel in sorted(required_export_files(plugins, curated)):
        if rel not in listed:
            raise ValueError(f"the export has no {rel}")
    check_export_files(export, listed)
    return curated


# --- What Cursor loads ---

def frontmatter_values(text, key):
    """The values of one key in the frontmatter of a rule or SKILL.md, one per occurrence. A
    block value (`key: |` or `key:` followed by indented lines) is its lines joined; a list
    item keeps its leading "- "."""
    frontmatter = re.match(r"---\r?\n(.*?)\r?\n---", text, flags=re.DOTALL)
    lines = frontmatter.group(1).splitlines() if frontmatter else []
    values = []
    for index, line in enumerate(lines):
        if not line.startswith(f"{key}:"):
            continue
        value = line[len(key) + 1:].split(" #")[0].strip()
        if value in ("", "|", ">", "|-", ">-", "|+", ">+"):
            block = []
            for following in lines[index + 1:]:
                if not following.startswith((" ", "\t", "-")):
                    break
                block.append(following.strip())
            value = " ".join(block)
        values.append(value.strip("'\"").strip())
    return values


def always_applied(rule_text):
    """True when any alwaysApply value of the rule is not clearly false (false, no, off, 0).

    A YAML reader takes True, "true", `true # note` or a list as true, so a second router rule
    must not pass because of how it is spelled; a repeated key counts as a router when any of
    its values does. agent-skills scripts/check-marketplace-layout.py counts router rules with
    the same rule (it reads the last value of a repeated key).
    """
    return any(value.lower() not in NOT_ALWAYS_APPLIED for value in frontmatter_values(rule_text, "alwaysApply"))


def frontmatter_name(skill_file):
    names = frontmatter_values(skill_file.read_text(), "name")
    return names[0] if names and names[0] else None


def stop_commands(hooks):
    """The commands of the stop hooks in a hooks file, in the Cursor and the Claude format."""
    events = hooks.get("hooks") if isinstance(hooks, dict) else None
    if not isinstance(events, dict):
        return []
    commands = [str(item.get("command", "")) for item in events.get("stop", []) if isinstance(item, dict)]
    for group in events.get("Stop", []):
        if isinstance(group, dict):
            commands += [str(item.get("command", "")) for item in group.get("hooks", []) if isinstance(item, dict)]
    return commands


def cursor_paths(stage, folder, manifest, key, default):
    """The existing paths of one component of a Cursor manifest. A path the manifest names
    replaces the default one, and it must exist inside the plugin folder."""
    root = (stage / folder).resolve()
    value = manifest.get(key, default)
    paths = [value] if isinstance(value, str) else value
    if not isinstance(paths, list) or not all(isinstance(path, str) for path in paths):
        raise ValueError(f"{folder}/{CURSOR_MANIFEST}: {key} must be a path or a list of paths")
    found = []
    for path in paths:
        full = (root / path).resolve()
        if full != root and root not in full.parents:
            raise ValueError(f"{folder}/{CURSOR_MANIFEST}: {key} names {path}, outside the plugin")
        if full.exists():
            found.append(full)
        elif key in manifest:
            raise ValueError(f"{folder}/{CURSOR_MANIFEST}: {key} names {path}, which does not exist")
    return found


def cursor_install(stage, folder):
    """The router rules, stop hook commands and skill names Cursor loads from one plugin folder."""
    root = (stage / folder).resolve()
    manifest = json.loads((root / CURSOR_MANIFEST).read_text())
    rules = []
    for path in cursor_paths(stage, folder, manifest, "rules", "rules"):
        if path.is_dir():
            rules += [rule for rule in sorted(path.rglob("*")) if rule.is_file() and rule.suffix in RULE_SUFFIXES]
        else:
            rules.append(path)  # a rule file the manifest names counts whatever its suffix
    routers = [f"{folder}/{rule.relative_to(root).as_posix()}" for rule in rules if always_applied(rule.read_text())]
    stops = []
    for path in cursor_paths(stage, folder, manifest, "hooks", "hooks/hooks.json"):
        stops += stop_commands(json.loads(path.read_text()))
    skills = set()
    for path in cursor_paths(stage, folder, manifest, "skills", "skills"):
        for skill_file in sorted(path.glob("*/SKILL.md")):
            skills.add(frontmatter_name(skill_file) or skill_file.parent.name)
    return routers, stops, skills


def check_stop_command(stage, folder, label, command):
    command = command.strip()
    script = command.split('"')[1] if command.startswith('"') else command.split(" ")[0]
    if not script.startswith(CURSOR_ROOT):
        raise ValueError(f"{label}: stop command {command} does not start with {CURSOR_ROOT}; "
                         "Cursor runs plugin stop hooks from the workspace root")
    root = (stage / folder).resolve()
    target = (root / script[len(CURSOR_ROOT):]).resolve()
    if root not in target.parents or not target.is_file() or not os.access(target, os.X_OK):
        raise ValueError(f"{label}: stop command names {folder}/{script[len(CURSOR_ROOT):]}, "
                         "which is missing or not executable")


def check_cursor_install(stage, name, folder):
    """A Cursor install of one catalog plugin loads at most one router rule and one stop hook,
    and exactly one of each when it carries the hawkscan skill."""
    routers, stops, skills = cursor_install(stage, folder)
    label = f"Cursor install of {name}"
    if len(routers) > 1:
        raise ValueError(f"{label} loads {len(routers)} router rules ({', '.join(routers)}); "
                         "Cursor must load at most one always-applied rule")
    if len(stops) > 1:
        raise ValueError(f"{label} loads {len(stops)} stop hooks; at most one may run")
    if ROUTER_SKILL in skills and (len(routers), len(stops)) != (1, 1):
        raise ValueError(f"{label} carries the {ROUTER_SKILL} skill with {len(routers)} router rules "
                         f"and {len(stops)} stop hooks; expected one of each")
    for command in stops:
        check_stop_command(stage, folder, label, command)


def check_claude_snapshots(stage, plugins, cursor=None):
    """Cursor imports Claude Code plugins next to the one native Cursor install, so a Claude
    snapshot must not bring a second router rule or stop hook.

    The Claude snapshot of wingman carries no part that only its bundle may carry, and no stop
    hook. With an export (cursor maps each plugin to its Cursor folder), no Claude snapshot
    carries a Cursor rule or Cursor hook, and the snapshot of a plugin that Cursor installs from
    another folder carries no Cursor file at all.
    """
    for name in cursor or {}:
        snapshot = stage / "plugins" / name
        own = cursor[name] == f"plugins/{name}"
        for part in CURSOR_RULES_AND_HOOKS if own else CURSOR_PARTS:
            if (snapshot / part).exists():
                raise ValueError(f"the Claude snapshot of {name} carries {part}; "
                                 f"Cursor imports Claude Code plugins, so only {cursor[name]} may carry it")
        if not own and any(snapshot.rglob("*.mdc")):
            raise ValueError(f"the Claude snapshot of {name} carries a Cursor rule; only {cursor[name]} may carry one")
    if BUNDLE_NAME not in plugins:
        return
    snapshot = stage / "plugins" / BUNDLE_NAME
    for part in BUNDLE_ONLY:
        if (snapshot / part).exists():
            raise ValueError(f"the Claude snapshot of {BUNDLE_NAME} carries {part}; "
                             f"only bundles/{BUNDLE_NAME} may carry it")
    hooks = snapshot / "hooks" / "hooks.json"
    if hooks.is_file() and stop_commands(json.loads(hooks.read_text())):
        raise ValueError(f"the Claude snapshot of {BUNDLE_NAME} carries a stop hook in hooks/hooks.json; "
                         "the hawkscan dependency carries the only one")


# --- The published layout ---

def checked_source_path(entry, expected):
    source = entry["source"]
    actual = source["path"] if isinstance(source, dict) else source
    if actual.removeprefix("./") != expected:
        raise ValueError(f"{entry['name']} source is {actual}, expected {expected}")


def stamp_versions(plugin, version):
    """Write the release-tag version into every file the plugin carries one in.

    Tagged commits may hold a placeholder or the real number; either way the
    tag is the source of truth.
    """
    for manifest_path in (
        plugin / ".claude-plugin" / "plugin.json",
        plugin / ".codex-plugin" / "plugin.json",
        plugin / ".github" / "plugin" / "plugin.json",
        plugin / CURSOR_MANIFEST,
    ):
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text())
            manifest["version"] = version
            write_json(manifest_path, manifest)
    # Covers plugin skills and, for wingman, the copilot-skills copies.
    for skill_file in plugin.glob("**/SKILL.md"):
        text = skill_file.read_text()
        frontmatter = re.match(r"---\n.*?\n---\n", text, flags=re.DOTALL)
        if not frontmatter:
            continue
        head, count = re.subn(
            r"^version:[ \t]*.*$", f"version: {version}", frontmatter.group(0),
            count=1, flags=re.MULTILINE,
        )
        if count:
            skill_file.write_text(head + text[frontmatter.end():])


def prepare_plugins(stage, sources, plugins, version, bundle_source=None):
    """Copy each plugin from sources[name]. bundle_source, from an export, is the Wingman bundle."""
    for name, upstream_path in plugins.items():
        destination = stage / "plugins" / name
        shutil.copytree(sources[name], destination)
        manifest_path = destination / ".claude-plugin" / "plugin.json"
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("name") != name:
            raise ValueError(f"{upstream_path} manifest name differs from {name}")
        stamp_versions(destination, version)
        manifest["version"] = version
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
            split_bundle(stage, destination, manifest["dependencies"], version, bundle_source)


def split_bundle(stage, snapshot, dependencies, version, bundle_source=None):
    """Keep wingman's bundled skills out of the folders the Claude catalog lists.

    Copilot, Codex and Cursor have no plugin dependencies, so they install the bundle
    with copies of the dependency skills. Claude installs the dependencies, and
    the directory reviews every folder its catalog lists, so its snapshot keeps
    only the manifests and README. The upstream README describes the Claude
    install, so the bundle gets its own README from overrides/.

    Without an export, the bundle is the tag's wingman folder, and the snapshot loses the
    bundle's skills and Copilot manifest. An agent-skills export already carries the bundle,
    with the Cursor manifest, rules and stop hook that the Claude snapshot must not carry; the
    bundle gets the snapshot's Claude manifest.
    """
    bundle = stage / "bundles" / BUNDLE_NAME
    if bundle_source is None:
        shutil.copytree(snapshot, bundle)
    else:
        shutil.copytree(bundle_source, bundle)
        stamp_versions(bundle, version)
        shutil.copyfile(snapshot / ".claude-plugin" / "plugin.json", bundle / ".claude-plugin" / "plugin.json")
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
        name = frontmatter_name(skill_file)
        if not name:
            raise ValueError(f"{skill_file} has no frontmatter name")
        bundled.add(name)
    if bundled != set(dependencies):
        raise ValueError(f"{BUNDLE_NAME} bundles {sorted(bundled)}, expected {sorted(dependencies)}")
    if bundle_source is None:
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


def prepare_cursor_only(stage, export, cursor, version):
    """Copy each Cursor-only plugin of the export to cursor-plugins/<name> and stamp it."""
    for name, folder in cursor.items():
        if folder == f"{CURSOR_ONLY_ROOT}/{name}":
            shutil.copytree(export / folder, stage / folder)
            stamp_versions(stage / folder, version)


def prepare_cursor(stage, export, plugins, cursor):
    """The Cursor catalog of the export for the curated plugins, in sources.json order, and
    the installers. Each Cursor install must load what check_cursor_install allows."""
    catalog = json.loads((export / CURSOR_CATALOG).read_text())
    entries = {}
    for entry in catalog.get("plugins", []):
        if entry.get("name") in entries:
            raise ValueError(f"the Cursor catalog of the export lists {entry.get('name')} twice")
        entries[entry.get("name")] = entry
    published = []
    for name in plugins:
        if name not in entries:
            raise ValueError(f"the Cursor catalog of the export has no {name}")
        expected = f"./{cursor[name]}"
        if entries[name].get("source") != expected:
            raise ValueError(f"Cursor catalog source of {name} is {entries[name].get('source')}, expected {expected}")
        manifest = json.loads((stage / cursor[name] / CURSOR_MANIFEST).read_text())
        if manifest.get("name") != name:
            raise ValueError(f"{cursor[name]}/{CURSOR_MANIFEST} names {manifest.get('name')}, expected {name}")
        check_cursor_install(stage, name, cursor[name])
        published.append(entries[name])
    write_json(stage / CURSOR_CATALOG, {**catalog, "plugins": published})
    (stage / INSTALLERS).mkdir()
    for name in INSTALLER_FILES:
        shutil.copy2(export / INSTALLERS / name, stage / INSTALLERS / name)


def remove_empty_parents(path):
    parent = path.parent
    while parent != ROOT and parent.is_dir() and not any(parent.iterdir()):
        parent.rmdir()
        parent = parent.parent


def restore(touched, backup):
    """Put each touched published path back from the backup; return those that did not come back."""
    failed = []
    for relative in reversed(touched):
        target, old = ROOT / relative, backup / relative
        try:
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            elif os.path.lexists(target):
                target.unlink()
            if os.path.lexists(old):
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(old, target)
            else:
                remove_empty_parents(target)
        except OSError:
            failed.append(relative.as_posix())
    return failed


def install(stage):
    """Move every published path from the stage into ROOT; remove one the stage lacks.

    A sync without --export writes no Cursor catalog and no installers, so it removes those
    of an earlier sync rather than leave them for another release. On any error or interrupt,
    every path goes back as it was. If a path cannot go back, the backup stays in ROOT and the
    error names it.
    """
    backup = Path(tempfile.mkdtemp(prefix=".sync-backup-", dir=ROOT))
    touched = []
    try:
        for relative in PUBLISHED:
            target, old, new = ROOT / relative, backup / relative, stage / relative
            if os.path.lexists(target):
                old.parent.mkdir(parents=True, exist_ok=True)
                os.replace(target, old)
            touched.append(relative)
            if os.path.lexists(new):
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(new, target)
            else:
                remove_empty_parents(target)
    except BaseException as problem:
        failed = restore(touched, backup)
        if failed:
            raise RuntimeError(f"the sync could not restore {', '.join(failed)}; the old files are in {backup}") from problem
        shutil.rmtree(backup)
        raise
    shutil.rmtree(backup)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-repo", required=True, type=Path,
        help="Local agent-skills Git checkout",
    )
    parser.add_argument("--tag", required=True, help="Release tag, for example v2.5.1")
    parser.add_argument(
        "--export", type=Path,
        help="Payload of the tag from agent-skills scripts/export-marketplace.py "
        "(plugins, the Wingman bundle, the Cursor-only plugins, the Cursor catalog and installers)",
    )
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

    with tempfile.TemporaryDirectory(prefix=".sync-stage-", dir=ROOT) as stage_name:
        stage = Path(stage_name)
        if args.export:
            export = stage / "export"
            copy_export(args.export.resolve(), export)
            cursor = load_export(export, sha, version, plugins)
            sources = {name: export / "plugins" / name for name in plugins}
            prepare_plugins(stage, sources, plugins, version, export / "bundles" / BUNDLE_NAME)
            prepare_cursor_only(stage, export, cursor, version)
        else:
            cursor = None
            archive_root = stage / "upstream"
            archive_root.mkdir()
            extract_plugins(args.source_repo, sha, list(plugins.values()), archive_root)
            refuse_cursor_adapter(archive_root, plugins)
            sources = {name: archive_root / path for name, path in plugins.items()}
            prepare_plugins(stage, sources, plugins, version)
        check_claude_snapshots(stage, plugins, cursor)
        prepare_standalone_skills(stage, plugins)
        prepare_catalogs(stage, args.source_repo, sha, args.tag, plugins)
        if args.export:
            prepare_cursor(stage, export, plugins, cursor)
        source["tag"] = args.tag
        source["sha"] = sha
        write_json(stage / "sources.json", source)
        install(stage)
    skill_count = len(plugins) - int("wingman" in plugins)
    cursor = ", the Cursor catalog and the installers" if args.export else ""
    print(
        f"Synced {len(plugins)} plugins, {skill_count} standalone skills{cursor} "
        f"from {args.tag} ({sha})"
    )


if __name__ == "__main__":
    main()
