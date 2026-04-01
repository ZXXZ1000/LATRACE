# Memory v1.0 API & 配置快速指南（冻结面）

> 本文档定义 Memory 模块在 **v1.0** 阶段对外承诺的稳定接口与配置键，  
> 便于上层模块与外部系统集成，也作为后续演进的兼容性约束。

---

## 1. 稳定 Python API（同进程调用）

所有 Python 侧调用应通过包入口 `modules.memory` 获取公共对象：

```python
from modules.memory import create_service  # 工厂
from modules.memory.application.service import MemoryService
from modules.memory.application.graph_service import GraphService
from modules.memory.contracts.memory_models import MemoryEntry, Edge, SearchFilters, SearchResult
from modules.memory.contracts.graph_models import GraphUpsertRequest
```

### 1.1 MemoryService（统一记忆检索/写入）

**稳定方法：**

- `MemoryService.search(query: str, *, topk: int = 10, filters: SearchFilters | None = None, expand_graph: bool = True, threshold: float | None = None, scope: str | None = None, graph_params: dict | None = None) -> SearchResult`
  - 说明：向量召回 → 图邻域展开（可选）→ 混合重排（向量/BM25/图/时间）→ 返回 `hits/neighbors/hints/trace`。
  - 兼容性：  
    - v1.0 中 `query/topk/filters/expand_graph/threshold/scope` 为稳定参数；  
    - `graph_params` 仅用作运行时临时覆盖图扩展策略（max_hops/rel_whitelist 等），可选。

- `MemoryService.write(entries: list[MemoryEntry], links: list[Edge] | None = None, *, upsert: bool = True) -> None`
  - 说明：批量写入记忆条目及可选边；默认 upsert（按 id 合并）。

- `MemoryService.update(id: str, patch: dict, *, reason: str | None = None) -> None`  
- `MemoryService.delete(id: str, *, soft: bool = True, reason: str | None = None, confirm: bool | None = None) -> None`
  - 说明：用于修正/删除记忆；软删仅隐藏，硬删需显式 `confirm=True`。

- `MemoryService.list_places_by_time_range(...)`（签名见 `application/service.py`）
  - 说明：按时间范围 + SearchFilters 聚合 Places（用于 L1 场景“某段时间去了哪些地方”）。

> 约定：  
> - filters 使用 `SearchFilters`，三键：`tenant_id / user_id(list) / memory_domain` 是长期稳定字段。  
> - v1.0 不再变更 `SearchResult` 的顶层字段结构（hits / neighbors / hints / trace）。

### 1.2 GraphService（图谱查询与 Explain）

**主要稳定入口：**

- `GraphService.list_places(tenant_id: str, *, limit: int = 100) -> list[dict]`  
- `GraphService.list_events(tenant_id: str, *, place_id: str | None = None, limit: int = 100) -> list[dict]`
- `GraphService.explain_first_meeting(...)` / `explain_event_evidence(...)`

> 说明：GraphService 在 v1.0 中主要用于：  
> - 小规模图下的地点/事件列表查询；  
> - Explain 场景（首次相遇、事件证据链）；  
> 其返回结构在 v1.0 视为稳定；如需破坏性变更，将通过新增方法名承载。

---

## 2. 稳定 HTTP API（跨进程调用）

Memory API 基于 FastAPI，主要端点如下（`modules/memory/api/server.py`）：

### 2.1 记忆读写 API

- `POST /search`
  - Body：`{"query": str, "topk": int, "filters": {...}, "expand_graph": bool, "threshold": float | null, "scope": "session|domain|user|global"}`  
  - 返回：`SearchResult` JSON 形式。

- `POST /write`
  - Body：`{"entries": [MemoryEntry...], "links": [Edge...]}`。

- `POST /update`
  - Body：`{"id": str, "patch": {...}, "reason": str | null}`。

- `POST /delete`
  - Body：`{"id": str, "soft": bool, "reason": str | null, "confirm": bool | null}`。

> 说明：  
> - /search /write /update /delete 为 v1.0 稳定公共面；  
> - 任何需要破坏性变更（字段语义/结构）将通过新增路径（如 `/v2/search`）承载。

### 2.2 Graph v0.x API（时空图）

详见 `modules/memory/docs/graph_v0_usage.md`，这里只列稳定路径：

- 写入：`POST /graph/v0/upsert`（需要 `X-Tenant-ID` 头）  
- 查询：  
  - `GET /graph/v0/segments`  
  - `GET /graph/v0/entities/{id}/timeline`  
  - `GET /graph/v0/events` / `GET /graph/v0/events/{event_id}`  
  - `GET /graph/v0/places` / `GET /graph/v0/places/{place_id}`  
  - `GET /graph/v0/timeslices`
- 管理/治理端点（需 auth）：  
  - `POST /graph/v0/admin/build_event_relations`  
  - `POST /graph/v0/admin/build_timeslices`  
  - `POST /graph/v0/admin/build_cooccurs`（`mode=timeslice|event`）  
  - `POST /graph/v0/admin/ttl/cleanup`  
  - `GET  /graph/v0/admin/export_srot`

> Graph 接口在 v1.0 中整体视为 `v0` 代际的一部分，路径 `/graph/v0/*` 保持稳定；  
> 后续若引入破坏性 Schema/行为变更，将新增 `/graph/v1/*` 路径，v0 保持兼容读写。

### 2.3 可观测性与健康

- `GET /health`：健康检查（轻量）。  
- `GET /metrics_prom`：Prometheus 文本指标（详见 `modules/memory/observability`）。

---

## 3. v1.0 配置键（memory.config.yaml）

入口文件：`modules/memory/config/memory.config.yaml`（支持 env 展开 + Hydra 组合）。  
下列键在 v1.0 中视为**稳定配置面**，仅允许向后兼容扩展：

### 3.1 向量存储（Qdrant）

```yaml
memory:
  vector_store:
    kind: qdrant
    host: ${QDRANT_HOST}
    port: ${QDRANT_PORT}
    collections:
      text: memory_text
      image: memory_image
      audio: memory_audio
      clip_image: memory_clip_image
      face: memory_face
    embedding:
      provider: local | none | <vendor>
      model: jina-embeddings-v2-base-zh
      local_path: modules/memorization_agent/ops/models/jina-embeddings-v2-base-zh
      dim: 768
      normalize: true
      batch_size: 32
      distance: cosine
      image: {provider, model, dim}
      clip_image: {provider, model, dim}
      audio: {provider, model, dim}
      face: {dim}
    search:
      modality_weights:
        text: 1.0
        clip_image: 0.85
```

> 约定：  
> - 不会在 v1.0–1.x 中随意重命名 `collections` 键；  
> - `embedding` 下允许新增子键，但不会改变现有键语义。

### 3.2 图存储（Neo4j）

```yaml
memory:
  graph_store:
    kind: neo4j
    uri: ${NEO4J_URI}
    user: ${NEO4J_USER}
    password: ${NEO4J_PASSWORD}
    # database: 默认为 neo4j，可显式配置
```

### 3.3 治理/TTL/重要性

```yaml
memory:
  governance:
    ttl:
      episodic_default_seconds: 86400
      semantic_default_seconds: 0
    importance:
      text_boost: 0.1
      ctrl_boost: 0.1
    pinned:
      enabled: true
      rules: []
    per_domain_ttl:
      work: "30d"
      home: "90d"
      system: "7d"
    importance_overrides:
      work: 0.1
```

> TTL/importance 策略在 v1.0 中通过治理层实现，语义稳定；数值可按环境调整。

### 3.4 搜索/图扩展/缓存/重排

```yaml
memory:
  search:
    character_expansion: {...}
    ann:
      default_topk: 10
      threshold: 0.1
      default_modalities: [text, clip_image]
      default_all_modalities: false
    scoping:
      default_scope: global
      user_match_mode: any
      require_user: false
      fallback_order: [global, session, domain, user]
    graph:
      expand: true
      max_hops: 3
      rel_whitelist: [...]
      neighbor_cap_per_seed: 10
      restrict_to_user: true
      restrict_to_domain: true
      allow_cross_user: false
      allow_cross_domain: false
    cache:
      enabled: true
      ttl_seconds: 60
      max_entries: 256
    rerank:
      alpha_vector: 0.35
      beta_bm25: 0.50
      gamma_graph: 0.15
      delta_recency: 0.05
      user_boost: 0.0
      domain_boost: 0.15
      session_boost: 0.0
```

### 3.5 其他关键配置

- `memory.decider`：启用 LLM 决策的 ADD/UPDATE/DELETE/NONE；  
- `memory.llm`：文本/多模态模型选择；  
- `memory.events.publish_memory_ready`：是否在写入后发布事件；  
- `memory.api.auth`：API 级最小认证（Token）；  
- `memory.write.batch`：写入批处理开关与阈值；  
- `memory.reliability.retries/circuit_breaker`：重试与熔断策略。

> 这些键在 v1.0 视为稳定；后续版本以追加子键/可选字段为主，避免破坏现有配置。

---

## 4. 监控与指标（简要）

详细见 `modules/memory/observability/README.md`。  
核心指标类别：

- `memory_search_*`：搜索次数、延迟直方图、错误总数、缓存命中率；  
- `memory_graph_*`：图写入/查询次数、TTL 清理、Explain 命中率；  
- `memory_qdrant_*` / `memory_neo4j_*`：后端错误与重试情况；  
- `memory_ttl_cleanup_*`：TTL 清理成功/错误次数与节点/边数。

Grafana 面板：`modules/memory/observability/grafana_memory.json`。  
Prometheus 告警示例：`modules/memory/observability/alerts/memory_rules.yml`。

---

## 5. 版本与兼容性说明

- v1.0 起：  
  - 本文档列出的 Python API / HTTP 路径 / 配置键视为**稳定面**；  
  - 破坏性变更需通过：新增版本化路径（如 `/graph/v1/*`）、新增方法名或新增配置键来承载。  
- `PROCESS.md` 将持续记录各版本对这些契约的新增/扩展点，作为代码与文档之间的桥梁。
