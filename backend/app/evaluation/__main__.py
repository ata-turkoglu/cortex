import argparse
import json
from pathlib import Path

from .production import ProductionEvaluationRunner


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Cortex V2 production acceptance")
    parser.add_argument(
        "--historical-v1",
        action="store_true",
        help="run the isolated legacy synthetic benchmark instead of production acceptance",
    )
    parser.add_argument("--suite", type=Path, default=Path("evaluation/golden.json"))
    parser.add_argument("--tag")
    parser.add_argument("--case")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--allow-incompatible-baseline", action="store_true")
    parser.add_argument("--accept-baseline", type=Path)
    args = parser.parse_args()
    if not args.historical_v1:
        report = ProductionEvaluationRunner().run()
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
        return 0 if report["passed"] else 1

    from .runner import EvaluationRunner, compare_baseline, load_suite

    report = EvaluationRunner(load_suite(args.suite)).run(tag=args.tag, case_id=args.case)
    if args.baseline:
        report = compare_baseline(
            report, args.baseline, allow_incompatible=args.allow_incompatible_baseline
        )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    if args.accept_baseline:
        if args.accept_baseline.exists():
            raise FileExistsError("refusing to overwrite an accepted baseline")
        args.accept_baseline.parent.mkdir(parents=True, exist_ok=True)
        args.accept_baseline.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    succeeded = (
        report["summary"]["failed"] == 0
        and report["summary"].get("invalid", 0) == 0
        and report.get("baseline", {}).get("passed", True)
    )
    return 0 if succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
