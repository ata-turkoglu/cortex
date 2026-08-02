#!/usr/bin/env python3
"""Create a lockfile-based dependency inventory without ambient-machine noise."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "reports" / "licenses"


def pinned_python_requirements() -> list[str]:
    return [
        line.strip()
        for requirement in (
            ROOT / "backend" / "requirements.lock",
            ROOT / "backend" / "requirements-dev.in",
        )
        if requirement.exists()
        for line in requirement.read_text(encoding="utf-8").splitlines()
        if "==" in line and not line.lstrip().startswith("#")
    ]


def javascript_packages() -> list[str]:
    packages: list[str] = []
    for manifest in (ROOT / "package.json", ROOT / "frontend" / "package.json"):
        if not manifest.exists():
            continue
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        for section in ("dependencies", "devDependencies", "optionalDependencies"):
            packages.extend(
                f"{name}@{version}"
                for name, version in payload.get(section, {}).items()
            )
    return sorted(set(packages))


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = {
        "note": "The report uses project manifests and lockfiles, never globally installed packages. Review listed licenses before distribution.",
        "javascript": {
            "lockfile": "pnpm-lock.yaml",
            "status": "requires-license-audit"
            if (ROOT / "pnpm-lock.yaml").exists()
            else "not-created",
            "packages": javascript_packages(),
        },
        "python": {
            "lockfile": "backend/requirements.lock",
            "packages": pinned_python_requirements(),
            "status": "requires-license-audit"
            if pinned_python_requirements()
            else "not-created",
        },
    }
    (OUTPUT / "inventory.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(f"Wrote {OUTPUT.relative_to(ROOT) / 'inventory.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
