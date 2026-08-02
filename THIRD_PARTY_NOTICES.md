# Third-Party Notices

This file records third-party components distributed with Cortex. Phase 1 contains only
development-tool declarations; feature phases must add their runtime dependencies and
licenses before they are used.

| Component | Version | License source       | Purpose                    |
| --------- | ------- | -------------------- | -------------------------- |
| Node.js   | 24.x    | nodejs.org           | JavaScript runtime         |
| pnpm      | 10.4.1  | npm package metadata | JavaScript package manager |
| Python    | 3.10.x  | python.org           | Backend runtime            |
| Prettier  | 3.5.3   | npm package metadata | Formatting                 |
| ESLint    | 9.22.0  | npm package metadata | Frontend linting           |
| Black     | 25.1.0  | PyPI metadata        | Python formatting          |
| Ruff      | 0.9.10  | PyPI metadata        | Python linting             |

Run `python scripts/license-report.py` after dependencies are installed to generate a
machine-readable inventory in `reports/licenses/`. Distribution requires reviewing this
file and the generated reports for each newly introduced dependency.
