#!/usr/bin/env python3
"""Generate thin AI-tool adapters from canonical AGENTS.md files."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAP_PATH = ROOT / ".ai" / "project-map.yaml"
ADAPTERS = {
    "CLAUDE.md": (
        "# Cortex\n\n"
        "Follow the canonical repository instructions in [`AGENTS.md`](AGENTS.md).\n"
    ),
    "GEMINI.md": (
        "# Cortex\n\n"
        "Follow the canonical repository instructions in [`AGENTS.md`](AGENTS.md).\n"
    ),
}
SCOPED_ADAPTER = (
    "# Cortex scoped context\n\n"
    "Follow the canonical scoped instructions in [`AGENTS.md`](AGENTS.md).\n"
)


def main() -> int:
    for name, content in ADAPTERS.items():
        (ROOT / name).write_text(content, encoding="utf-8", newline="\n")
    project_map = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    scoped_paths = project_map.get("scoped_adapters", [])
    for relative_path in scoped_paths:
        directory = ROOT / relative_path
        if not (directory / "AGENTS.md").is_file():
            raise FileNotFoundError(f"missing scoped AGENTS.md: {relative_path}/AGENTS.md")
        (directory / "CLAUDE.md").write_text(
            SCOPED_ADAPTER, encoding="utf-8", newline="\n"
        )
    print(f"Generated {len(ADAPTERS) + len(scoped_paths)} thin adapters.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
