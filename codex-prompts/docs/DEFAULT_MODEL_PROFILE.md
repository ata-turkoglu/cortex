# Cortex Default Model Profile

## Target environment

- Windows 11
- i7-9750H
- 16 GB RAM
- GTX 1650
- Ollama available
- `qwen3:4b` is not sufficiently reliable for production Cortex workloads
- OpenAI API key available

## Production defaults

| Layer                         | Provider | Model                                                        |
| ----------------------------- | -------- | ------------------------------------------------------------ |
| Query Router                  | OpenAI   | gpt-5.6-luna                                                 |
| Metadata Extraction           | OpenAI   | gpt-5.6-luna                                                 |
| Conversation Summary          | OpenAI   | gpt-5.6-luna                                                 |
| Query Expansion               | OpenAI   | gpt-5.6-luna, disabled by default                            |
| Answer Generation             | OpenAI   | gpt-5.6-luna                                                 |
| Graph Entity Extraction       | OpenAI   | gpt-5.6-luna                                                 |
| Graph Relationship Extraction | OpenAI   | gpt-5.6-luna                                                 |
| Graph Community Summarization | OpenAI   | gpt-5.6-luna                                                 |
| GraphRAG Query Synthesis      | OpenAI   | gpt-5.6-luna                                                 |
| Embeddings                    | Ollama   | Installed shared KnowledgeOS model (currently bge-m3:latest) |
| Reranker                      | Local    | BGE family, configurable                                     |

## Optional quality profile

The user may manually assign `gpt-5.4-mini` to high-value extraction, graph, or answer layers.

Automatic escalation is disabled by default.

## Ollama

Ollama is optional. Cortex may list installed models and show pull commands, but it does not download or delete models in V1.

Small models such as `gemma3:1b` and `qwen3:1.7b` must be labeled experimental/offline and are not production defaults.

## Multilingual embedding profile

Generic default when installed:

- Provider: Ollama
- Model: `qwen3-embedding:0.6b`
- Purpose: multilingual and cross-lingual dense retrieval
- Installation command shown by Cortex:
  `ollama pull qwen3-embedding:0.6b`

Shared KnowledgeOS deployment override:

- Discover installed models from `http://host.docker.internal:11434/api/tags`.
- Use `bge-m3:latest` for embeddings when it is installed in KnowledgeOS.
- Do not download `qwen3-embedding:0.6b` automatically and do not create a
  second Ollama container or model volume for Cortex.

Optional:

- `bge-m3:567m` for comparative evaluation
- OpenAI `text-embedding-3-small` when the user explicitly chooses API embeddings

Changing the active embedding model or configuration requires a full dense reindex.
