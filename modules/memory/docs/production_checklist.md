# 记忆层上线 Checklist（生产稳态）

本文用于指导将 `MOYAN_Agent_Infra/modules/memory`（记忆基建层）上线到生产或准生产环境时的准备与核验。

## 1. 前置条件与版本
- Python：3.11.x（全项目统一）
- 依赖安装：从仓库根目录
  - `pip install -e MOYAN_Agent_Infra[dev]`
- 运行方式：同进程直调（MemoryPort/Service）或跨进程 HTTP（FastAPI）

## 2. 配置与密钥（.env + YAML）
- 复制并编辑：`MOYAN_Agent_Infra/modules/memory/config/.env.example` → `.env`
- 统一使用 `.env` 注入，`memory.config.yaml` 支持 `${VAR}` 展开：
  - 向量库：`QDRANT_HOST`、`QDRANT_PORT`、`QDRANT_API_KEY?`
  - 图数据库：`NEO4J_URI`、`NEO4J_USER`、`NEO4J_PASSWORD`
  - LLM（可选）：`LLM_PROVIDER` + 对应 API Key（OpenRouter/OpenAI/DeepSeek/Qwen/GLM/Gemini 等）
  - 嵌入兜底（可选/按需）：
    - 文本：`EMBEDDING_PROVIDER`、`EMBEDDING_MODEL`、`EMBEDDING_DIM`
    - OpenAI-Compatible：`OPENAI_COMPAT_API_BASE`、`OPENAI_COMPAT_API_KEY`、`OPENAI_EMBEDDING_MODEL`
    - 图像（占位/可接 CLIP）：`IMAGE_EMBEDDING_PROVIDER`、`IMAGE_EMBEDDING_MODEL`、`IMAGE_EMBEDDING_DIM`
    - 语音（占位/可接 ERes2NetV2）：`AUDIO_EMBEDDING_PROVIDER`、`AUDIO_EMBEDDING_MODEL`、`AUDIO_EMBEDDING_DIM`
  - 运行时覆盖持久化（可选）：`MEMORY_RUNTIME_OVERRIDES`（默认：`modules/memory/config/runtime_overrides.json`）

## 3. 存储后端准备（Qdrant/Neo4j）
- Qdrant（Docker 示例）：
  - `docker run -d -p 6333:6333 --name qdrant qdrant/qdrant:latest`
  - 集合初始化（推荐）：
    - 调用 HTTP：`POST /admin/ensure_collections`
    - 或手动创建集合：
      - `memory_text`（向量维度与度量来自 YAML：默认 1536/cosine）
      - `memory_image`（默认 512/cosine，可选）
      - `memory_audio`（默认 256/cosine，可选）
  - HNSW 参数（建议）：`M≈32`、`ef_construction≈128`、`ef_search≈64`（按规模调优）
- Neo4j（Docker 示例）：
  - `docker run -d -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/<password> neo4j:5-community`
  - 启动后自动建约束：`:Entity(id) IS UNIQUE`（由驱动初始化）

## 4. 服务启动与健康检查
- 启动 HTTP 服务：
  - `uvicorn modules.memory.api.server:app --host 0.0.0.0 --port 8000`
- 健康检查：
  - `GET /health` → `{vectors:{status:ok}, graph:{status:ok}}`
- 集合初始化：
  - `POST /admin/ensure_collections` → `{ok:true}`

## 5. 指标与告警（Prometheus）
- 指标端点：`GET /metrics_prom`（文本）/ `GET /metrics`（JSON）
- 关键指标：
  - `memory_writes_total`、`memory_searches_total`、`memory_graph_rel_merges_total`、`memory_rollbacks_total`
  - `memory_search_latency_ms_sum`
  - 直方图：`memory_search_latency_ms_bucket/_sum/_count`
- 告警建议：
  - 搜索延迟 P95/P99 超阈值（如 >200ms / >500ms）
  - 回滚次数异常升高
  - 写入失败/集合不可用（结合服务日志）

## 6. 运行时热更新（权重/白名单）
- 查询：
  - `GET /config/search/rerank`、`GET /config/graph`
- 更新：
  - `POST /config/search/rerank`（`alpha_vector/beta_bm25/gamma_graph/delta_recency`）
  - `POST /config/graph`（`rel_whitelist/max_hops/neighbor_cap_per_seed`）
- 持久化：更新后自动保存到 `MEMORY_RUNTIME_OVERRIDES` 指定文件；服务启动自动加载。

## 7. 事件总线与主题（解耦）
- 事件总线在独立模块：`modules/event_bus`
- 记忆层事件发布为“可注入回调”：`MemoryService.set_event_publisher(publish)`
- 推荐主题：
  - `memory_ready`：写入成功（载荷：`version/count/clip_ids/ids/source_stats`）
  - 上层订阅该主题以驱动 UI/旁路任务；记忆层不自行耦合 event bus

## 8. 多模态嵌入兜底（何时与如何）
- 推荐生产路径：上游（m3/mem0）产出向量并写入 `MemoryEntry.vectors`（ETL 已优先使用）
- 兜底触发：`vectors` 缺失时，记忆层才使用 provider 生成；否则回退哈希
- 提供商（文本）：Gemini / OpenAI-Compatible（详见 `.env.example`）
- 提供商（图像/语音）：当前为占位（CLIP/ERes2NetV2），默认回退；后续可接入私有/云端端点

## 9. 安全/权限/审计
- API 暴露：`/write /update /delete /link` 建议置于内网或经 API Gateway 控制
- 高风险操作：delete/batch update 建议加鉴权与审计（上层控制）
- 审计：所有变更写入 SQLite/PG（当前为 SQLite），支持按 Version 回滚（`rollback_version`）

## 10. 备份/恢复/升级
- Qdrant：挂载持久卷（`/qdrant/storage`），备份 collections 数据
- Neo4j：挂载数据与日志卷（`/data /logs`），定期备份
- 升级：优先滚动升级；`/admin/ensure_collections` 用于检查/创建集合；Schema 变更需审慎评估

## 11. 验证路径（建议）
1) ETL 导入：VideoGraph pkl → `pkl_to_db.py --dry-run` 验证条数；随后小样本导入 InMem/真实后端
2) 搜索验证：`/search`（含 filters 与邻域）命中预期；latency 与指标正常
3) 更新/回滚：`/update` 后 `rollback_version` 恢复成功
4) 事件：注入发布回调，订阅 `memory_ready` 并验证载荷
5) 热更新：调整 rerank/graph 配置，确认实时生效且已持久化

## 12. 常见排障
- 模型/嵌入未生效：检查 `.env`、YAML 与网络；回退路径是否触发（哈希嵌入）
- Qdrant 过滤无命中：确认 payload keys（如 `metadata.source`）与集合/维度正确
- Neo4j 关系缺失：检查 `merge_nodes_edges` 入参与白名单；确认约束已建立
- 事件未收到：确认是否注入了 `set_event_publisher`；编排层是否注册订阅

## 13. 变更控制
- 配置变更：先在测试环境验证；生产通过运行时热更新并持久化，或变更 YAML 与 `.env`
- 权重与白名单：采用 `POST /config/...` 热更新，避免重启；必要时备份 `runtime_overrides.json`
- 版本回滚：保留审计存档，确认 `rollback_version` 可用

---

上线完成的标志：健康检查与集合集齐、写/搜/改/删/连全链路通过、事件发布可用、指标正常上报、热更新可持久化、文档与值班手册齐备。
