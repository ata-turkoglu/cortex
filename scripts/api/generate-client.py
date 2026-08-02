"""Generate frontend OpenAPI client after backend is running.
Uses an explicit command rather than committing manually duplicated DTOs.
"""

from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
url = "http://localhost:4000/api/v1/openapi.json"
target = ROOT / "frontend" / "src" / "api" / "generated" / "openapi.json"


def main() -> int:
    target.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=10) as response:
        target.write_bytes(response.read())
    print(
        f"Wrote {target.relative_to(ROOT)}; run the configured client generator in the next API-contract phase."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
