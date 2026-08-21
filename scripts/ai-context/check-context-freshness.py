#!/usr/bin/env python3
"""Require corresponding docs when mapped module files change."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAP_PATH = ROOT / ".ai" / "project-map.yaml"


def changed_paths() -> set[str]:
    commands = [
        ["git", "diff", "--name-only", "HEAD"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ]
    changed: set[str] = set()
    for command in commands:
        result = subprocess.run(
            command, cwd=ROOT, capture_output=True, text=True, check=False
        )
        if result.returncode == 0:
            changed.update(line for line in result.stdout.splitlines() if line)
    return changed


def main() -> int:
    project_map = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    changed = changed_paths()
    # An empty history is expected during repository bootstrap; validate only changed mapped areas.
    errors: list[str] = []
    modules = project_map["modules"]
    owning_paths: set[str] = set()
    for changed_path in changed:
        matches = [
            module
            for module in modules
            if changed_path == module["path"]
            or changed_path.startswith(module["path"].rstrip("/") + "/")
        ]
        if matches:
            most_specific_length = max(len(module["path"]) for module in matches)
            owning_paths.update(
                module["path"]
                for module in matches
                if len(module["path"]) == most_specific_length
            )
    for module in modules:
        touched = module["path"] in owning_paths
        documented = any(doc in changed for doc in module.get("docs", []))
        if touched and not documented:
            errors.append(f"{module['path']} changed without its mapped documentation")
    if errors:
        print(
            "Context freshness failed:",
            *[f"- {error}" for error in errors],
            sep="\n",
            file=sys.stderr,
        )
        return 1
    print("Context freshness passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
