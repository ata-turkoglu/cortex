#!/usr/bin/env python3
"""Generate thin AI-tool adapters from the canonical root instruction file."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADAPTERS = {
    "CLAUDE.md": "# Cortex\n\nFollow the canonical repository instructions in [`AGENTS.md`](AGENTS.md).\n",
    "GEMINI.md": "# Cortex\n\nFollow the canonical repository instructions in [`AGENTS.md`](AGENTS.md).\n",
}


def main() -> int:
    for name, content in ADAPTERS.items():
        (ROOT / name).write_text(content, encoding="utf-8", newline="\n")
    print(f"Generated {len(ADAPTERS)} thin adapters.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
