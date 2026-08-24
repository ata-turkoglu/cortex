"""Production V2 acceptance evaluation entry point.

The acceptance itself lives beside the rest of the integration tests so it can use
the repository's deterministic external-provider adapters while exercising the real
upload, generation, cutover, and normal chat endpoint boundaries.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from ..query.cutover import CutoverEvaluation

PRODUCTION_SUITE_VERSION = "uploaded-file-production-v2/v1"
PRODUCTION_CASE_ID = "uploaded-file-v2-end-to-end"


@dataclass(frozen=True)
class ProductionEvaluationRunner:
    """Run the versioned V2-only production acceptance suite."""

    backend_root: Path = Path(__file__).resolve().parents[2]

    def run(self) -> dict[str, object]:
        """Execute isolated V2 acceptance and return a cutover-gate payload."""
        test_path = "tests/test_query_v2_uploaded_file_acceptance.py"
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            test_path,
            "-p",
            "no:cacheprovider",
        ]
        completed = subprocess.run(
            command,
            cwd=self.backend_root,
            capture_output=True,
            check=False,
            text=True,
        )
        evaluation = CutoverEvaluation(
            suite_version=PRODUCTION_SUITE_VERSION,
            total_cases=1,
            passed_cases=1 if completed.returncode == 0 else 0,
            score=1.0 if completed.returncode == 0 else 0.0,
            minimum_score=1.0,
            mandatory_failures=() if completed.returncode == 0 else (PRODUCTION_CASE_ID,),
        )
        return {
            "runtime": "v2",
            "suite": PRODUCTION_SUITE_VERSION,
            "case_id": PRODUCTION_CASE_ID,
            "command": command,
            "passed": evaluation.passed,
            "evaluation": evaluation.model_dump(mode="json"),
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
