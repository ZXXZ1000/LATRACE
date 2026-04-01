<div align="center">

<img src="./assets/logo.png" alt="LATRACE Logo" width="600">

# LATRACE

**Long-term Adaptive Trace for AI Context Engine**

*Give your AI the memory it deserves.* 🌌

Read this in [English](README.md) | [中文](README_zh.md)

<p align="center">
  <a href="https://github.com/ZXXZ1000/LATRACE/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg" alt="License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.11%2B-blue.svg" alt="Python"></a>
  <a href="https://github.com/ZXXZ1000/LATRACE/actions/workflows/ci.yml"><img src="https://github.com/ZXXZ1000/LATRACE/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/ZXXZ1000/LATRACE/releases"><img src="https://img.shields.io/github/v/release/ZXXZ1000/LATRACE?display_name=tag" alt="Release"></a>
  <a href="https://ghcr.io/zxxz1000/latrace-memory"><img src="https://img.shields.io/badge/GHCR-latrace--memory-2496ED?logo=docker&logoColor=white" alt="GHCR"></a>
  <a href="https://github.com/ZXXZ1000/LATRACE/pulls"><img src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg" alt="PRs Welcome"></a>
  <a href="https://fastapi.tiangolo.com"><img src="https://img.shields.io/badge/FastAPI-005571?style=flat&logo=fastapi" alt="FastAPI"></a>
  <a href="https://pydantic-docs.helpmanual.io/"><img src="https://img.shields.io/badge/Pydantic-e92063?style=flat&logo=pydantic&logoColor=white" alt="Pydantic"></a>
</p>

</div>

---

## 🎉 Recent Updates
- **[2026-04]** 🚀 LATRACE(formerly OmniMemory), is now officially open source!
- **[2026-04]** 🏆 Achieved **SOTA** memory retrieval performance on public benchmarks.

---

LATRACE is a **production-ready memory service** that gives your AI applications the ability to remember, learn, and evolve across conversations. Unlike simple RAG systems that just retrieve documents, LATRACE builds a **living knowledge graph** that understands context, relationships, and temporal dynamics.

**The Problem 🤕:** Most AI applications are amnesiac. They forget everything after each conversation, forcing users to repeat context and losing valuable insights over time.

**The Solution 💡:** LATRACE provides a structured, queryable memory layer that:
- 📚 **Remembers** user preferences, facts, and conversation history
- 🧠 **Understands** relationships between concepts through knowledge graphs
- ⏰ **Tracks** temporal evolution of information
- 🔍 **Retrieves** relevant context with hybrid search (vector + graph + BM25)
- 🎭 **Isolates** data by tenant/user/domain for multi-tenant SaaS

## 🚦 Start Here

- **Self-host in 5 minutes**: Jump to [Quick Start](#quick-start)
- **Integrate over HTTP**: Read the [API Reference](docs/api_reference.md)
- **Understand benchmark scope**: Start from the [Benchmark Guide](docs/benchmark_guide.md)
- **Contribute**: Open the [Contributing Guide](CONTRIBUTING.md)

## 🎯 Core Features

### 🏗️ Production-Grade Architecture
- 🖼️ **Multi-modal Memory**: Text, images, audio, video support
- 🗄️ **Hybrid Storage**: Vector DB (Qdrant/Milvus) + Graph DB (Neo4j) + Relational DB (PostgreSQL)
- 🏢 **Tenant Isolation**: Built-in multi-tenancy with strict data boundaries
- ⚡ **Async Processing**: Background ingestion with job queue management

### 🚀 Performance & Scalability
- 📦 **Batch Processing**: Efficient bulk operations for high-throughput scenarios
- 🐇 **Smart Caching**: Redis-backed caching for frequently accessed memories
- 🎛️ **Configurable Retrieval**: Fine-tuned ranking with BM25, vector similarity, and graph traversal
- 🛡️ **Resource Management**: Connection pooling, timeout controls, retry strategies

### 🔒 Enterprise-Ready
- 🔑 **Authentication**: JWT-based auth with project-level API keys
- 📜 **Audit Logging**: Complete audit trail for compliance
- 💰 **Usage Tracking**: Token usage and cost monitoring
- 🔭 **Observability**: Structured logging with OpenTelemetry support

### 🎨 Developer Experience
- 🔌 **Clean API**: RESTful HTTP API with comprehensive OpenAPI docs
- 🛡️ **Type Safety**: Full Pydantic models for request/response validation
- 🧩 **Easy Integration**: Drop-in replacement for existing memory solutions
- 🐳 **Docker Ready**: One-command deployment with Docker Compose


## 📚 Public Docs

- [API Reference](docs/api_reference.md)
- [ADK Integration Guide](docs/adk_integration.md)
- [Tenant Isolation](docs/tenant_isolation.md)


## 🎪 Why LATRACE?

### 🏆 Benchmark SOTA

We recently achieved **State-of-the-Art (SOTA)** performance on both the **LoCoMo** and **LongMemEval** benchmarks, significantly outperforming all existing memory solutions in temporal reasoning, cross-session multihop tracking, and knowledge updates.

<div align="center">
<img src="./assets/data%20chart.png" alt="LATRACE Benchmark Data" width="800">
</div>

### 📊 Capability Comparison

| Capability | LATRACE | Traditional RAG | Agentic Memory (Simple) |
|------------|---------|-----------------|-------------------------|
| 🧠 **Memory Structure** | Vector + Graph + RDBMS | Vector Only | JSON / Text Window |
| ⏰ **Temporal Flow** | ✅ Native Timeline | ❌ None | ⚠️ Short-term only |
| 🏢 **Multi-Tenancy** | ✅ Strict Isolation | ❌ DIY | ❌ DIY |
| 🔄 **State Sync** | ✅ Frontend-Backend Synced | ❌ Backend Only | ⚠️ Partial |
| 📊 **Observability** | ✅ OpenTelemetry built-in | ⚠️ Varies | ❌ Black-box |

### 🛠️ Storage Engine Support

| Component | Supported Engines | Status |
|-----------|------------------|--------|
| **Vector Search** | Qdrant, Milvus, Chroma | 🟢 Production Ready |
| **Graph DB** | Neo4j, Memgraph | 🟢 Production Ready |
| **Metadata DB** | PostgreSQL, SQLite | 🟢 Production Ready |
| **KV Cache** | Redis | 🟢 Production Ready |


<a id="quick-start"></a>

## 🚀 Quick Start

### 📋 Prerequisites
- 🐍 Python 3.11+
- 🐳 Docker & Docker Compose (for local development)

### 🐳 Option 1: Docker Compose (Recommended)

```bash
# 1. Clone the repository
git clone https://github.com/ZXXZ1000/LATRACE.git
cd latrace

# 2. Copy environment template
cp .env.example .env

# 3. Start all services (memory + qdrant + neo4j)
docker compose up --build
```

🌐 **Services will be available at:**
- 🧠 Memory API: `http://localhost:8000`
- 🔍 Qdrant: `http://localhost:6333`
- 🕸️ Neo4j Browser: `http://localhost:7474`

### 📦 Option 1.5: Pull the Published Docker Image Directly

If you only want the LATRACE Memory API container, you can pull the published image directly from GitHub Container Registry:

```bash
docker pull ghcr.io/zxxz1000/latrace-memory:latest
docker run --rm -p 8000:8000 --env-file .env ghcr.io/zxxz1000/latrace-memory:latest
```

This image contains only the application service. Qdrant and Neo4j are not bundled inside the image, so you still need to run them separately or point the app to existing external instances.

## 🔁 CI / CD

- Pull requests run full `modules/memory` checks with `ruff` and `pytest`.
- Secret-backed embedding connectivity is skipped by default in open-source CI. Set `REQUIRE_EMBEDDING_CONNECTIVITY=1` together with provider credentials if you want to enforce it.
- Merges to `main` publish the Docker image to GitHub Container Registry.
- You can pull the latest image directly with `docker pull ghcr.io/zxxz1000/latrace-memory:latest`.
- If you use the published image outside this repository, you still need to pull and run compatible Qdrant and Neo4j images yourself, then wire them to the LATRACE service with the right environment variables or compose setup.

### 💻 Option 2: Local Development

```bash
# 1. Install dependencies with uv
uv sync

# 2. Optional: Install extra capabilities
uv sync --extra local-embeddings --extra multimodal

# 3. Set up environment variables
cp .env.example .env
# Edit .env with your configuration

# 4. Start the server
uv run python -m uvicorn modules.memory.api.server:app --host 0.0.0.0 --port 8000
```


## 📖 Step-by-step Usage

### 1️⃣ Create a Memory Session

```python
import httpx

client = httpx.Client(base_url="http://localhost:8000")

# Create a session
response = client.post("/api/v1/sessions", json={
    "tenant": "my-app",
    "user_id": "user-123",
    "memory_domain": "conversation"
})
session_id = response.json()["session_id"]
```

### 2️⃣ Store Memories

```python
# Add a conversation to memory
client.post(f"/api/v1/sessions/{session_id}/ingest", json={
    "messages": [
        {"role": "user", "content": "I love hiking in the mountains"},
        {"role": "assistant", "content": "That's wonderful! Mountain hiking is great exercise."}
    ]
})
```

### 3️⃣ Retrieve Relevant Context

```python
# Query memories
response = client.post(f"/api/v1/sessions/{session_id}/retrieve", json={
    "query": "What are my hobbies?",
    "top_k": 5
})

memories = response.json()["results"]
for memory in memories:
    print(f"[{memory['score']:.2f}] {memory['content']}")
```


## 🏗️ Architecture

```text
┌─────────────────────────────────────────────────────────┐
│                     LATRACE Memory API                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   Ingestion  │  │   Retrieval  │  │  Management  │  │
│  │   Pipeline   │  │    Engine    │  │   Services   │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
└─────────┼──────────────────┼──────────────────┼─────────┘
          │                  │                  │
    ┌─────▼─────┐      ┌────▼────┐       ┌────▼────┐
    │  Job      │      │ Hybrid  │       │  Audit  │
    │  Queue    │      │ Search  │       │  Store  │
    └─────┬─────┘      └────┬────┘       └────┬────┘
          │                 │                  │
    ┌─────▼─────────────────▼──────────────────▼─────┐
    │           Storage Layer (Adapters)              │
    │  ┌──────────┐  ┌──────────┐  ┌──────────┐     │
    │  │  Vector  │  │  Graph   │  │   RDBMS  │     │
    │  │  Store   │  │  Store   │  │  Store   │     │
    │  │ (Qdrant) │  │ (Neo4j)  │  │  (PG)    │     │
    │  └──────────┘  └──────────┘  └──────────┘     │
    └─────────────────────────────────────────────────┘
```


## 🎯 Use Cases

- 🤖 **AI Assistants & Chatbots**: Build conversational AI that remembers user preferences, past interactions, and context across sessions.
- 📚 **Knowledge Management**: Create intelligent knowledge bases that understand relationships between concepts and evolve over time.
- 🎓 **Educational Platforms**: Track student learning progress, adapt content based on understanding, and provide personalized recommendations.
- 🛍️ **E-commerce Personalization**: Remember customer preferences, purchase history, and browsing patterns for better recommendations.
- 🏥 **Healthcare Applications**: Maintain patient interaction history while ensuring strict data isolation and compliance.


## 📚 More Resources

- 🔗 [API Reference](docs/api_reference.md) - Comprehensive REST API mapping and layers
- 🤖 [ADK Integration Guide](docs/adk_integration.md) - ADK Runtime for seamless LLM Agent integration (MCP/OpenAI)
- 🏢 [Tenant Isolation](docs/tenant_isolation.md) - Isolation model for tenants, users, apps, and sessions
- 🧪 [Benchmark Guide](docs/benchmark_guide.md) - Public benchmark scope, evaluation path, and publication status
- 🤝 [Contributing Guide](CONTRIBUTING.md) - Contribution flow, testing expectations, and review norms
- 🐳 [Docker Compose Stack](docker-compose.yml) - Minimal self-hosted stack for local deployment


## 🤝 Support & Contributing

We welcome contributions, issue reports, and pull requests. Please see [CONTRIBUTING.md](CONTRIBUTING.md) for how to get started. I will personally review and merge PRs once they are ready.
If you run into any issues, please contact us at [zx19970301@gmail.com](mailto:zx19970301@gmail.com).


## 📄 License

LATRACE is licensed under the [Apache License 2.0](LICENSE).

---

<div align="center">

**Built with ❤️ for the AI community**

[⭐ Star us on GitHub](https://github.com/ZXXZ1000/LATRACE) | [📖 API Reference](docs/api_reference.md) | [🧪 Benchmark Guide](docs/benchmark_guide.md) | [💬 Discussions](https://github.com/ZXXZ1000/LATRACE/discussions)

</div>
