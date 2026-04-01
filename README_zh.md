<div align="center">

<img src="./assets/logo.png" alt="LATRACE Logo" width="600">

# LATRACE

**Long-term Adaptive Trace for AI Context Engine**

*赋予你的 AI 梦寐以求的记忆能力。* 🌌

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

## 🎉 最新动态 (Recent Updates)
- **[2026-04]** 🚀 LATRACE（原 OmniMemory）核心记忆基建正式开源发布！
- **[2026-04]** 🏆 在通用记忆提取的 Benchmark 测试中取得拔得头筹的 **SOTA** 成绩。

---

LATRACE 是一个**生产级的记忆服务**，赋予你的 AI 应用跨对话记忆、学习和进化的能力。不同于简单的 RAG 系统只检索离散文档，LATRACE 构建了一个**活的知识图谱**，能够深度理解上下文、实体关系以及时间流逝的动态变化。

**核心痛点 🤕：** 大多数 AI 应用都患有“失忆症”。它们在每次对话结束后就会遗忘一切，迫使用户不断重复背景信息，随时间流失了极其宝贵的用户洞察。

**解决方案 💡：** LATRACE 提供了一个结构化、高度可查询的记忆层：
- 📚 **精准记忆**：用户偏好、事实细节与历史对话轨迹
- 🧠 **深度理解**：通过内置知识图谱，洞悉概念间的隐性关系
- ⏰ **时间追踪**：感知信息的生命周期与时间演化
- 🔍 **智能检索**：结合了 向量 + 图谱 + BM25 的工业级混合检索
- 🎭 **数据隔离**：为多租户 SaaS 打造的严格租户/用户/领域隔离体系

## 🚦 从这里开始

- **5 分钟本地自部署**：跳转到[快速接入](#quick-start)
- **通过 HTTP 集成**：查看 [API 官方文档](docs/api_reference.md)
- **了解公开 Benchmark 范围**：从 [Benchmark 指南](docs/benchmark_guide.md) 开始
- **参与共建**：阅读 [CONTRIBUTING.md](CONTRIBUTING.md)

## 🎯 核心特性

### 🏗️ 生产级架构支持
- 🖼️ **多模态记忆**：原生支持文本、图像、音频、视频的上下文关联
- 🗄️ **混合存储引擎**：向量数据库 (Qdrant/Milvus) + 图数据库 (Neo4j) + 关系型存储 (PostgreSQL)
- 🏢 **租户隔离**：真正的多租户设计，构筑坚不可摧的数据边界
- ⚡ **全异步处理**：基于作业队列的后台数据摄取，保障主链路性能

### 🚀 极致的性能与扩展性
- 📦 **高性能批处理**：完美应对高并发、高吞吐的数据写入场景
- 🐇 **智能多级缓存**：Redis 支撑的热点记忆缓存机制
- 🎛️ **高度可配的检索**：支持自定义权重的混合排序方案（BM25 + 向量相似度 + 图遍历）
- 🛡️ **底层资源管理**：自带连接池、严格的超时控制与退避重试策略

### 🔒 满足企业级需求 (Enterprise-Ready)
- 🔑 **身份认证**：基于 JWT 和项目级 API 鉴权体系
- 📜 **不可篡改的审计日志**：完整的操作轨迹，满足行业合规要求
- 💰 **成本与用量监控**：Token 消耗一目了然
- 🔭 **系统可观测性**：基于 OpenTelemetry 的结构化日志与追踪链路

### 🎨 极致的开发者体验
- 🔌 **开箱即用的 API**：标准的 RESTful API 与随时可查的 OpenAPI 交互文档
- 🛡️ **严格的类型安全**：采用 Pydantic v2 提供坚实的请求/响应校验
- 🧩 **无缝平替集成**：只需修改几行代码，即可替换您现有的极简记忆组件
- 🐳 **Docker-Ready**：通过 Docker Compose 一键拉起完整后端基础设施


## 🎪 为什么选择 LATRACE？

### 🏆 业界顶尖的 Benchmark 评估结果

我们在权威系统长文记忆基准测试 **LoCoMo** 与 **LongMemEval** 中均取得了 **全网第一（SOTA）** 的压倒性成绩。特别在时序提取、跨会话多跳追踪以及知识更新迭代方面，LATRACE 展现出了惊人的优势。

<div align="center">
<img src="./assets/data%20chart.png" alt="LATRACE Benchmark 数据对比图" width="800">
</div>

### 📊 记忆能力对比

| 核心能力 | LATRACE | 传统 RAG | 其他轻量记忆方案 |
|---------|---------|----------|--------------|
| 🧠 **记忆数据结构** | 向量 + 图谱 + 关系型 | 仅包含向量 | 单一 JSON 或 文本滑动窗口 |
| ⏰ **时间线感知** | ✅ 原生支持时间线追踪 | ❌ 无法感知 | ⚠️ 仅保留近期片段 |
| 🏢 **多租户隔离** | ✅ 极其严格的项目/用户隔离 | ❌ 需开发者自行处理 | ❌ 需自行处理 |
| 🔄 **前后端状态同步** | ✅ 全面实时同步 | ❌ 仅后端维护 | ⚠️ 部分支持 |
| 📊 **架构可观测性** | ✅ 内置 OpenTelemetry | ⚠️ 各不相同 | ❌ 完全黑盒 |

### 🛠️ 支持的底层存储引擎

| 存储类型 | 支持的引擎列表 | 当前状态 |
|---------|--------------|---------|
| **向量搜索 (Vector)** | Qdrant, Milvus, Chroma | 🟢 生产就绪 |
| **知识图谱 (Graph)** | Neo4j, Memgraph | 🟢 生产就绪 |
| **元数据与审计 (RDBMS)**| PostgreSQL, SQLite | 🟢 生产就绪 |
| **热点缓存 (KV Cache)** | Redis | 🟢 生产就绪 |


## 🚀 快速接入

### 📋 环境要求
- 🐍 Python 3.11+
- 🐳 Docker & Docker Compose (用于快速本地部署)

<a id="quick-start"></a>

### 🐳 方式一：Docker Compose（强烈推荐）

```bash
# 1. 克隆代码仓库
git clone https://github.com/ZXXZ1000/LATRACE.git
cd latrace

# 2. 从模板复制环境变量
cp .env.example .env

# 3. 一键启动所有基础组件服务 (Memory API + Qdrant + Neo4j)
docker compose up --build
```

🌐 **各项服务入口地址：**
- 🧠 Memory API: `http://localhost:8000`
- 🔍 Qdrant 控制台: `http://localhost:6333`
- 🕸️ Neo4j 可视化图谱: `http://localhost:7474`

### 📦 方式 1.5：直接拉取已发布的 Docker 镜像

如果你只想使用 LATRACE 的 Memory API 容器，可以直接从 GitHub Container Registry 拉取：

```bash
docker pull ghcr.io/zxxz1000/latrace-memory:latest
docker run --rm -p 8000:8000 --env-file .env ghcr.io/zxxz1000/latrace-memory:latest
```

这个镜像里只包含应用服务本身，不包含 Qdrant 和 Neo4j，所以它们仍然需要单独启动，或者连接到你已经有的外部实例。

## 🔁 CI / CD

- Pull Request 会对 `modules/memory` 运行完整的 `ruff` 和 `pytest` 检查。
- 依赖私有凭据的 embedding 连通性检查在开源默认 CI 中会跳过；如果你希望强制执行，请配置提供商凭据并设置 `REQUIRE_EMBEDDING_CONNECTIVITY=1`。
- 合并到 `main` 后，会自动把 Docker 镜像发布到 GitHub Container Registry。
- 你可以直接通过 `docker pull ghcr.io/zxxz1000/latrace-memory:latest` 获取最新镜像。
- 如果你是在仓库外单独使用这个镜像，仍然需要自己拉取并启动兼容版本的 `Qdrant` 和 `Neo4j` 镜像，再通过环境变量或 compose 配置把它们和 LATRACE 服务联通起来。

### 💻 方式二：纯本地开发环境配置

```bash
# 1. 使用 uv 极速安装依赖
uv sync

# 2. (可选) 安装本地嵌入与多模态解析能力
uv sync --extra local-embeddings --extra multimodal

# 3. 配置环境变量
cp .env.example .env
# 自行修改 .env 文件中的数据库连接与模型 API Key 等

# 4. 启动后端服务器
uv run python -m uvicorn modules.memory.api.server:app --host 0.0.0.0 --port 8000
```


## 📖 核心功能示例 (Step-by-step)

### 1️⃣ 创建一个全新的记忆会话 (Session)

```python
import httpx

client = httpx.Client(base_url="http://localhost:8000")

# 初始化会话，自动处理多租户与领域隔离
response = client.post("/api/v1/sessions", json={
    "tenant": "my-app",
    "user_id": "user-123",
    "memory_domain": "conversation"
})
session_id = response.json()["session_id"]
```

### 2️⃣ 存储对话与事件片段 (Ingestion)

```python
# 将对话抛入记忆网关，系统将自动异步处理向量化及图谱节点生成
client.post(f"/api/v1/sessions/{session_id}/ingest", json={
    "messages": [
        {"role": "user", "content": "我下个月计划去山里徒步，带点什么好？"},
        {"role": "assistant", "content": "太棒了！徒步是很好的放松方式，建议带上登山杖和防风衣。"}
    ]
})
```

### 3️⃣ 智能提取上下文 (Retrieval)

```python
# 当用户下次对话时，精准地找回相关线索
response = client.post(f"/api/v1/sessions/{session_id}/retrieve", json={
    "query": "关于我近期的爱好和计划，你记得些什么？",
    "top_k": 5
})

memories = response.json()["results"]
for memory in memories:
    print(f"[{memory['score']:.2f}] {memory['content']}")
```


## 🏗️ 系统架构总览

```text
┌─────────────────────────────────────────────────────────┐
│                  LATRACE 记忆 API                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   内容摄入   │  │   检索引擎   │  │  系统管理    │  │
│  │  (Ingestion) │  │ (Retrieval)  │  │ (Management) │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
└─────────┼──────────────────┼──────────────────┼─────────┘
          │                  │                  │
    ┌─────▼─────┐      ┌────▼────┐       ┌────▼────┐
    │  异步作业 │      │ 混合调度│       │ 审计记录 │
    │   队列    │      │ (Hybrid)│       │          │
    └─────┬─────┘      └────┬────┘       └────┬────┘
          │                 │                  │
    ┌─────▼─────────────────▼──────────────────▼─────┐
    │              底层存储适配层                      │
    │  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
    │  │ 向量引擎 │  │ 图谱引擎 │  │ 关系型库 │      │
    │  │          │  │          │  │          │      │
    │  │ (Qdrant) │  │ (Neo4j)  │  │ PostgreSQL│     │
    │  └──────────┘  └──────────┘  └──────────┘      │
    └──────────────────────────────────────────────────┘
```


## 🎯 典型的业务场景

- 🤖 **陪伴型与垂类 AI 助手**：为你的 Agent 注入灵魂，赋予它长效记忆，不仅记得用户习惯，更能随着互动时间拉长而“懂你”。
- 📚 **智能知识管理中枢**：不再是机械死板的文件库，而是一个能自动发现概念关系、随时间生长的活体知识大脑。
- 🎓 **自适应教育平台**：全生命周期追踪学习痛点与进度，根据理解深度的演进，给出“千人千面”的内容分发建议。
- 🛍️ **电商私域个性化服务**：不仅记住你的购买记录，更能基于历史行为推演你的显性与隐性购买意图。
- 🏥 **隐私级医疗随访系统**：支持跨周期的患者跟踪对话记录，确保极端严苛的数据安全和多租户合规隔离要求。


## 📚 更多资源

- 🔗 [API 官方文档](docs/api_reference.md) - 核心 REST 接口的全解剖与分层指南
- 🤖 [ADK 开发者指南](docs/adk_integration.md) - Agent 开发套件，快速接入大语言模型 (OpenAI规范) 与 MCP 工具链
- 🏢 [租户隔离说明（English）](docs/tenant_isolation.md) - 面向外部开发者的隔离层级、作用边界与分区建议
- 🧪 [Benchmark 指南](docs/benchmark_guide.md) - 公开 benchmark 范围、评估路径与发布状态
- 🤝 [开发者共建手册](CONTRIBUTING.md) - 贡献流程、测试要求与审查约定
- 🐳 [Docker Compose 栈](docker-compose.yml) - 本地自部署的最小运行栈


## 🤝 技术支持与开源贡献

我们欢迎任何形式的贡献、Issue 反馈和 Pull Request。开始前请先查阅 [CONTRIBUTING.md](CONTRIBUTING.md) 了解参与方式。我会亲自审查并合并已经准备好的 PR。
如有任何问题，请联系邮箱：[zx19970301@gmail.com](mailto:zx19970301@gmail.com)。


## 📄 开源许可证 (License)

LATRACE 全面拥抱开源生态，代码基于 [Apache License 2.0](LICENSE) 协议发布。

---

<div align="center">

**Built with ❤️ for the AI community**

[⭐ 回 GitHub 点赞支持](https://github.com/ZXXZ1000/LATRACE) | [📖 API 官方文档](docs/api_reference.md) | [🧪 Benchmark 指南](docs/benchmark_guide.md) | [💬 参与讨论](https://github.com/ZXXZ1000/LATRACE/discussions)

</div>
