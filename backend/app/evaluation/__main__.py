import argparse
import json
from pathlib import Path

from .production import ProductionEvaluationRunner


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Cortex V2 production acceptance")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = ProductionEvaluationRunner().run()
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
