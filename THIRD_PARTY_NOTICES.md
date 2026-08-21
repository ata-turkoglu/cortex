# Third-Party Notices

This file records the major third-party components distributed with Cortex. The exact
dependency inventory is generated from pinned manifests and lockfiles with
`python scripts/license-report.py`; review it before distribution.

| Component | Version | License source       | Purpose                    |
| --------- | ------- | -------------------- | -------------------------- |
| Node.js   | 24.0.2  | MIT                  | JavaScript runtime         |
| pnpm      | 10.4.1  | npm package metadata | JavaScript package manager |
| Python    | 3.11.11 | PSF-2.0              | Backend runtime            |
| FastAPI   | 0.115.8 | MIT                  | REST and OpenAPI server    |
| SQLAlchemy | 2.0.38 | MIT                 | SQLite ORM                 |
| Alembic   | 1.14.1  | MIT                  | Database migrations        |
| Dramatiq  | 1.17.1  | LGPL-3.0             | Durable job execution      |
| Docling   | 2.114.0 | MIT                  | Document normalization     |
| Qdrant client | 1.13.2 | Apache-2.0       | Vector-store adapter       |
| Redis client | 5.2.1 | MIT                | Worker broker client       |
| Neo4j Community | 2026.07.1 | GPL-3.0       | Persistent knowledge graph |
| Neo4j Python driver | 6.2.0 | Apache-2.0 AND Python-2.0 | Bolt adapter |
| Microsoft GraphRAG | 2.6.0 | MIT             | Extracted graph producer   |
| LlamaIndex Core | 0.12.32 | MIT             | Query/workflow adapters    |
| bm25s     | 0.3.9   | MIT                  | Sparse retrieval           |
| Sentence Transformers | 3.4.1 | Apache-2.0    | Local BGE reranking        |
| React     | 19.0.0  | MIT                  | Frontend runtime           |
| Vite      | 6.2.2   | MIT                  | Frontend build tooling     |
| PrimeReact | 10.9.2 | MIT                 | UI adapter implementation  |
| React Flow | 12.4.4 | MIT                 | Flow adapter implementation|
| Tailwind CSS | 3.4.17 | MIT               | Styling tooling            |
| lucide-react | 0.468.0 | ISC              | Icon registry implementation |
| Prettier  | 3.5.3   | npm package metadata | Formatting                 |
| ESLint    | 9.22.0  | npm package metadata | Frontend linting           |
| Black     | 25.1.0  | PyPI metadata        | Python formatting          |
| Ruff      | 0.9.10  | PyPI metadata        | Python linting             |

Distribution requires reviewing this file and the generated inventory for each newly introduced
dependency, particularly the LGPL-licensed Dramatiq component and its distribution obligations.
