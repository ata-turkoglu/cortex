#!/usr/bin/env python3
"""Validate Cortex's small, vendor-neutral AI navigation system."""

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAP_PATH = ROOT / ".ai" / "project-map.yaml"
ADAPTER = "# Cortex\n\nFollow the canonical repository instructions in [`AGENTS.md`](AGENTS.md).\n"


def read_map() -> dict:
    # The map deliberately uses JSON syntax, which is valid YAML 1.2, so Phase 1 needs no parser dependency.
    return json.loads(MAP_PATH.read_text(encoding="utf-8"))


def local_markdown_paths(path: Path) -> list[str]:
    links = re.findall(r"\[[^]]+\]\(([^)]+)\)", path.read_text(encoding="utf-8"))
    return [
        link.split("#", 1)[0]
        for link in links
        if link and "://" not in link and not link.startswith("mailto:")
    ]


def iter_markdown_files(excluded_directories: set[str]):
    """Walk Markdown without descending into inaccessible dependency directories."""
    for directory, names, filenames in os.walk(ROOT, topdown=True):
        names[:] = [name for name in names if name not in excluded_directories]
        for filename in filenames:
            if filename.endswith(".md"):
                yield Path(directory) / filename


def main() -> int:
    errors: list[str] = []
    try:
        project_map = read_map()
    except (OSError, json.JSONDecodeError) as error:
        print(f"Invalid project map: {error}", file=sys.stderr)
        return 1

    for entrypoint in project_map.get("entrypoints", []):
        if not (ROOT / entrypoint).exists():
            errors.append(f"missing entrypoint: {entrypoint}")
    for module in project_map.get("modules", []):
        for key in ("path", "context"):
            if not (ROOT / module[key]).exists():
                errors.append(f"missing module {key}: {module[key]}")
        for doc in module.get("docs", []):
            if not (ROOT / doc).is_file():
                errors.append(f"missing module documentation: {doc}")
    for required in project_map.get("documentation_rules", {}).values():
        for doc in required:
            if not (ROOT / doc).is_file():
                errors.append(f"missing required documentation: {doc}")
    for adapter in ("CLAUDE.md", "GEMINI.md"):
        if (ROOT / adapter).read_text(encoding="utf-8") != ADAPTER:
            errors.append(
                f"adapter is stale or contains duplicated instructions: {adapter}"
            )
    excluded = {".git", "node_modules", ".venv", "data", ".pnpm-store"}
    for markdown in iter_markdown_files(excluded):
        for link in local_markdown_paths(markdown):
            if not (markdown.parent / link).exists():
                errors.append(
                    f"broken local link in {markdown.relative_to(ROOT)}: {link}"
                )
    if errors:
        print(
            "Context validation failed:",
            *[f"- {error}" for error in errors],
            sep="\n",
            file=sys.stderr,
        )
        return 1
    print("Context validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
