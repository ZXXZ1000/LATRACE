# LATRACE

Standalone extraction workspace for the `modules/memory` module from
`MOYAN_AGENT_INFRA`, prepared for open-source cleanup.

Current baseline:

- keep `modules.memory` import path unchanged
- preserve the original module layout for low-risk extraction
- move key docs into a cleaner open-source-ready structure
- provide a standalone `pyproject.toml` for `uv`-managed dependencies
- provide a slim Docker image that only targets the memory service
- provide a minimal Docker Compose stack for self-hosted `memory + qdrant + neo4j`
- keep the extraction scope limited to `modules/memory` rather than the full parent-repo SDK surface

Current layout:

- `modules/memory/`: copied module code
- `docs/`: selected top-level documents renamed for public-facing use
- `AGENTS.md`, `CLAUDE.md`: copied workspace instructions for reference
- `LICENSE`, `NOTICE`: Apache 2.0 licensing metadata
- `pyproject.toml`: standalone dependency definition
- `Dockerfile`: slim runtime image for `modules.memory.api.server`

Dependency strategy:

- default install keeps the API/server path lean
- optional extras are split by capability:
  - `milvus`
  - `local-embeddings`
  - `multimodal`
  - `gemini`
  - `mcp`

Quick start:

```bash
uv sync
uv run python -m uvicorn modules.memory.api.server:app --host 0.0.0.0 --port 8000
```

Optional capabilities:

```bash
uv sync --extra milvus
uv sync --extra local-embeddings --extra multimodal
uv sync --extra gemini --extra mcp
```

Docker:

```bash
docker build -t latrace-memory .
docker run --rm -p 8000:8000 --env-file .env latrace-memory
```

The single-image flow expects external Qdrant and Neo4j instances.

Docker Compose:

```bash
cp .env.example .env
docker compose up --build
```

This starts:

- `memory` on `http://127.0.0.1:8000`
- `qdrant` on `http://127.0.0.1:6333`
- `neo4j` on `bolt://127.0.0.1:7687` and `http://127.0.0.1:7474`

Known follow-up work:

- rebuild standalone CI around this smaller dependency graph
- audit docs and configs for private/internal assumptions
- decide whether benchmark/eval assets should live in a separate repo
