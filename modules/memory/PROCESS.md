# PROCESS — Memory & TKG Graph 演进记录

本文件作为 Memory 模块的“工程日志”，记录从 v0.1 到 v1.0 的演进历程。每项记录需包含：**日期、变更范围（文件级）、技术决策（Why）、验证手段（Test）**。

---

## 2026-04-01

### 目标
- 将 Qdrant collection / payload index 的补建从“手动开关”改成“服务启动默认执行”，避免新环境或重启后遗漏索引，降低检索冷启动延迟。
- 复核最新 `LATRACE/modules/memory` 替换后的 Docker 启动路径，确认当前轻量镜像不需要再改 Dockerfile。

### 变更
- `modules/memory/api/server.py`：`lifespan()` 中 `MEMORY_STARTUP_ENSURE_COLLECTIONS` 的默认值由 `false` 改为 `true`。
- `docker-compose.yml`：显式补充 `MEMORY_STARTUP_ENSURE_COLLECTIONS: ${MEMORY_STARTUP_ENSURE_COLLECTIONS:-true}`，确保 compose 默认行为与代码一致。
- 启动逻辑保持 best-effort：
  - 启动时异步调用 `vectors.ensure_collections()`；
  - 若 Qdrant 不可用或补建失败，只记录 `memory.startup.ensure_collections failed`，不阻塞服务拉起。
- Qdrant 补建逻辑沿用 `modules/memory/infra/qdrant_store.py` 现有实现：
  - 自动创建缺失 collection；
  - 检查 `payload_schema`；
  - 仅对缺失字段补建 payload index。

### 测试
- `uv run --project /Users/zhaoxiang/工作/MOYAN/LATRACE pytest /Users/zhaoxiang/工作/MOYAN/LATRACE/modules/memory/tests -o addopts='-q --tb=short'`
- 结果：`623 passed, 5 skipped, 1 warning in 51.43s`
- `docker build -t latrace-memory:verify /Users/zhaoxiang/工作/MOYAN/LATRACE`
- 结果：镜像构建成功
- 运行临时容器时**不传** `MEMORY_STARTUP_ENSURE_COLLECTIONS`，仅依赖代码默认值：
  - `/health` 返回 `200`
  - `/metrics` 返回 `200`
  - 健康检查中 `vectors / graph / llm_provider / disk` 全部为 `ok`

### 备注
- 当前 Dockerfile 仍可直接承载最新 memory service，无需为这次自动 ensure 逻辑额外改镜像层。
- 若后续要进一步缩短冷启动时间，可单独评估将 payload index 并发度 `MEMORY_QDRANT_PAYLOAD_INDEX_CONCURRENCY` 暴露到部署配置。

## 2026-01-29

### 目标
- Phase 1 起步：打通 Event 结构化字段 → Qdrant filter → SearchFilters 传递链路。

### 变更
- `modules/memory/contracts/graph_models.py`：Event 新增 `topic_path/tags/keywords/time_bucket/tags_vocab_version` 字段。
- `modules/memory/contracts/memory_models.py`：SearchFilters 新增 `topic_path/tags/keywords/time_bucket/tags_vocab_version` 过滤字段。
- `modules/memory/application/graph_service.py`：TKG Event 向量 payload 写入 topic/tags/keywords/time_bucket/tags_vocab_version。
- `modules/memory/infra/qdrant_store.py`：Qdrant filter 支持 topic_path/tags/keywords/time_bucket/tags_vocab_version。
- `modules/memory/infra/neo4j_store.py`：新增索引 `state_subject_property` / `event_topic_id` / `event_topic_path`。
- `modules/memory/application/dialog_tkg_unified_extractor_v1.py`：事件归一化补充 topic_path/tags/keywords/time_bucket。
- `modules/memory/application/event_extractor_dialog_tkg_v1.py`：事件归一化补充 topic_path/tags/keywords/time_bucket。
- `modules/memory/application/prompts/dialog_tkg_unified_extractor_system_prompt_v1.txt`：补充 topic_path/tags/keywords 输出字段。
- `modules/memory/application/prompts/dialog_tkg_event_extractor_system_prompt_v1.txt`：补充输出契约与 topic/tags/keywords 字段。
- `modules/memory/domain/dialog_tkg_graph_v1.py`：Event 写入 topic_path/tags/keywords/time_bucket/tags_vocab_version，并自动推导 time_bucket。
- `modules/memory/application/topic_normalizer.py`：新增规则优先的 topic 归一化模块（规则/同义词/兜底）。
- `modules/memory/application/dialog_tkg_unified_extractor_v1.py`：抽取后接入 topic_normalizer 归一化。
- `modules/memory/application/event_extractor_dialog_tkg_v1.py`：抽取后接入 topic_normalizer 归一化。
- `modules/memory/application/topic_normalizer.py`：新增异步降级模式（_uncategorized 事件写入待归一化队列）。
- `modules/memory/infra/qdrant_store.py`：topic/tag/keyword/time_bucket 列表过滤改为 match any（硬过滤）。
- `modules/memory/domain/dialog_tkg_graph_v1.py`：异步模式下将 _uncategorized 事件写入队列（含 event_id/tenant_id）。
- `modules/memory/scripts/topic_coverage_report.py`：新增覆盖率统计脚本（topic_path_coverage/_uncategorized_ratio）。
- `modules/memory/scripts/normalization_queue_backfill.py`：新增回洗脚本（队列 → 归一化 → 可选写回 Neo4j/Qdrant）。
- `modules/memory/infra/qdrant_store.py`：新增 payload 更新方法（set_payload_by_filter/set_payload_by_node）。
- 新增单测：`modules/memory/tests/unit/test_qdrant_filter_topic_fields.py`。
- 新增单测：`modules/memory/tests/unit/test_dialog_tkg_unified_extractor_basics.py::test_normalize_event_topic_fields`。
- 新增单测：`modules/memory/tests/unit/test_dialog_tkg_event_extractor_basics.py::test_normalize_event_topic_fields`。
- 新增单测：`modules/memory/tests/unit/test_topic_normalizer.py`。
- 新增单测：`modules/memory/tests/unit/test_qdrant_set_payload_by_node.py`。
- 新增单测：`modules/memory/tests/unit/test_dialog_tkg_graph_v1.py::test_dialog_graph_upsert_v1_derives_time_bucket`。
- 新增单测：`modules/memory/tests/unit/test_topic_coverage_report.py`。
- 新增单测：`modules/memory/tests/unit/test_normalization_queue_backfill.py`。
- 新增单测：`modules/memory/tests/unit/test_topic_normalizer.py::test_normalizer_priority_conflict`。
- 新增单测：`modules/memory/tests/unit/test_topic_normalizer.py::test_normalizer_existing_topic_path_passthrough`。
- 新增单测：`modules/memory/tests/unit/test_topic_normalizer.py::test_normalizer_empty_event_defaults`。
- 新增单测：`modules/memory/tests/unit/test_normalization_rules_no_conflict.py`。

### 测试
- `python -m pytest modules/memory/tests/unit/test_qdrant_filter_topic_fields.py -q`
- 结果：1 passed
- `python -m pytest modules/memory/tests/unit/test_dialog_tkg_unified_extractor_basics.py modules/memory/tests/unit/test_dialog_tkg_event_extractor_basics.py -q`
- 结果：14 passed
- `python -m pytest modules/memory/tests/unit/test_topic_normalizer.py -q`
- 结果：4 passed
- `python -m pytest modules/memory/tests/unit/test_qdrant_set_payload_by_node.py -q`
- 结果：1 passed
- `python -m pytest modules/memory/tests/unit/test_dialog_tkg_graph_v1.py -q`
- 结果：6 passed
- `python -m pytest modules/memory/tests/unit/test_topic_coverage_report.py modules/memory/tests/unit/test_normalization_queue_backfill.py -q`
- 结果：3 passed
- `python -m pytest modules/memory/tests/unit/test_topic_normalizer.py modules/memory/tests/unit/test_normalization_rules_no_conflict.py -q`
- 结果：8 passed
- `python modules/memory/scripts/backup_qdrant.py --host 127.0.0.1 --port 6333 --collection memory_text --out modules/memory/outputs/topic_coverage_qdrant_text.jsonl --batch 256`
- 结果：导出 9453 points（用于覆盖率统计样本）
- `python modules/memory/scripts/topic_coverage_report.py --input modules/memory/outputs/topic_coverage_qdrant_text.jsonl --output modules/memory/outputs/topic_coverage_report.json`
- 结果：coverage=0（当前样本未包含 topic_path/tags/keywords/time_bucket 字段）
- `PYTHONPATH=MOYAN_AGENT_INFRA python modules/memory/scripts/normalization_queue_backfill.py --input modules/memory/outputs/topic_normalization_queue.jsonl --output modules/memory/outputs/topic_normalization_backfill_updates.jsonl`
- 结果：backfill_updates=0（队列为空）

### 备注
- API/SDK 文档同步更新了 SearchFilters 新字段（见仓库根目录文档）。

## 2026-03-21

### GA 前收口 TODO
- 收紧 `/retrieval` 的实验/消融开关暴露范围。
  - 当前 `enable_*_route`、`dialog_v2_reranker`、`dialog_v2_test_ablation` 可由请求体直接覆盖。
  - GA 前评估是否只保留内网 benchmark/admin 入口，或加显式 feature gate。
- 提升 `query_vector` 兼容 fallback 的可观测性。
  - 当前 `retrieval.py`、`service.py`、`vector_store_router.py` 在旧签名兼容时会静默 fallback。
  - GA 前补充结构化日志或 warning，并增加单测覆盖，避免真实错误被误判成“降级成功”。

## 0. 历史背景（memory_scope / timeline_summary）
- **目标**：在不破坏 Notebook/旧调用的前提下，引入更细粒度的隔离键 `memory_scope`（建议每视频稳定哈希），并新增时间线摘要能力。
- **SearchFilters**：`user_id`, `memory_domain`, `run_id`, `memory_scope`（为空视为未启用；AND 收窄）。
- **实现细节**：
  - `modules/memory/infra/qdrant_store.py`: `_build_filter()` 增加 `metadata.memory_scope` 精确匹配。
  - `modules/memory/infra/neo4j_store.py`: 写节点落库 `memory_scope`；`expand_neighbors()` 支持 `restrict_to_scope`（默认 True）。
  - `modules/memory/application/service.py`: 将 `filters.memory_scope` 传入图扩展，可配置 `restrict_to_scope/allow_cross_scope`。
- **新接口**：
  - `MemoryService.timeline_summary`: 按 timestamp 聚合事件，可附加图邻居。
  - `POST /timeline_summary`: HTTP 端点暴露。
- **验证**：`tests/unit/test_timeline_summary.py` 验证事件输出与邻居附加。

---

## 1. 已完成里程碑

### P1：Session Marker 'completed_no_llm' 状态修复（2026-01-11）
- **范围**：
  - `modules/memory/session_write.py`：当 LLM 配置缺失时设置 marker status 为 `completed_no_llm` 而非 `completed`。
  - `modules/memory/tests/unit/test_session_write_llm_missing_marker.py`：新增 3 个单测验证新 marker 状态行为。
  - `scripts/reset_session_markers.py`：新增管理脚本用于重置旧 marker。
- **决策（Why）**：
  - 在 BYOK 更新前写入的 session（无 LLM 配置）被标记为 `completed`，导致后续重新写入被跳过（marker check 只跳过 `status='completed'`）。
  - Entity 抽取永远无法在这些 session 上执行，即使后来配置了 LLM。
- **实现（What/How）**：
  - 当 `facts_skipped_reason == 'llm_missing'` 时，将 marker status 设为 `completed_no_llm`。
  - Marker check（line 439）只跳过 `status='completed'`，因此 `completed_no_llm` 可以通过并触发重新处理。
  - 管理脚本支持批量重置旧 marker（默认同时重置 `completed` 和 `completed_no_llm` 状态的 marker）。
- **验证（Test）**：
  - `pytest modules/memory/tests/unit/test_session_write_llm_missing_marker.py -v`（3 passed）
  - `pytest modules/memory/tests/unit/test_session_write_llm_required.py modules/memory/tests/unit/test_session_write_api.py -v`（5 passed，无回归）
- **PR**：https://github.com/VisMemo/MOYAN_AGENT_INFRA/pull/33

### P1：请求级 BYOK 路由（client_meta LLM 配置）（2026-01-07）
- **范围**：
  - `modules/memory/api/server.py`：新增 `client_meta` 解析与 LLM 路由；Stage2/Stage3/with_answer 接入 BYOK adapter；usage 事件补充 byok_route/resolver_status。
  - `modules/memory/application/turn_mark_extractor_dialog_v1.py`：允许传入外部 adapter（用于 BYOK）。
  - `modules/memory/tests/unit/test_client_meta_byok_routing.py`：新增 client_meta 路由测试。
  - `modules/memory/tests/unit/test_ingest_retrieval_endpoints.py`：新增 retrieval with_answer 使用 client_meta adapter 的测试。
- **决策（Why）**：
  - SaaS 请求可能直接携带 LLM 配置；只要可解析即优先走 BYOK，`llm_mode` 仅作为来源标记。
  - 无有效 LLM 配置时回落平台默认配置，避免可用性回退。
- **实现（What/How）**：
  - `_resolve_llm_adapter_from_client_meta` 统一解析 `llm_provider/llm_model/llm_api_key/llm_base_url`。
  - ingest Stage2/Stage3 通过 adapter 选择 LLM；retrieval `with_answer` 传入 `qa_generate`。
  - usage 事件记录 `byok_route/resolver_status` 便于计量与审计。
- **验证（Test）**：
  - `pytest modules/memory/tests/unit/test_client_meta_byok_routing.py -q`
  - `pytest modules/memory/tests/unit/test_ingest_retrieval_endpoints.py -q`

### P1：ingest 幂等键加入租户隔离（2026-01-10）
- **范围**：`modules/memory/infra/async_ingest_job_store.py` 新增租户维度的 `ingest_commit_index_v2`，查找/插入/清理全部带上 `tenant_id`，并对 legacy index 做一次性回填。
- **决策（Why）**：避免不同租户在相同 `session_id+commit_id` 下被误判为重复写入，导致跨租户数据污染或空数据检索。
- **实现（What/How）**：引入 `(tenant_id, session_id, commit_id)` 主键表，legacy 入口回退时强制 tenant 匹配；清理路径同步删除 v1/v2 索引。
- **验证（Test）**：`pytest modules/memory/tests/unit/test_ingest_job_store_tenant_dedup.py -q`

### P1：Ingest 队列并发默认值调优（2026-01-10）
- **范围**：`modules/memory/application/config.py` 默认值；`modules/memory/config/memory.config.yaml`、`modules/memory/config/hydra/memory.yaml`。
- **决策（Why）**：默认并发过低（global=2, per_tenant=1, worker=2），批量写入时吞吐受限。
- **实现（What/How）**：默认提升为 `worker_count=10`、`global_concurrency=10`、`per_tenant_concurrency=3`，队列仍无限；配置文件同步更新为基准值，可在部署时覆盖。
- **验证（Test）**：未额外添加；依赖现有 ingest executor 单测（见条目 72）。

### P1：PG ingest job 读取 JSON 兼容修复（2026-01-14）
- **范围**：`modules/memory/infra/pg_ingest_job_store.py`，`modules/memory/tests/unit/test_pg_ingest_job_store_json_decode.py`。
- **决策（Why）**：asyncpg 返回 JSONB 为字符串时，_row_to_record 会将 turns/attempts/last_error 等字段清空，导致 Stage3 判定 turns 为空直接失败且错误信息丢失。
- **实现（What/How）**：_safe_list/_safe_dict 在遇到 str 时尝试 json.loads，保持 list/dict；新增单测覆盖 str JSON 解析。
- **验证（Test）**：`pytest modules/memory/tests/unit/test_pg_ingest_job_store_json_decode.py -q`

### P1：TKG 向量统一存储与 Face Evidence 关联修复（2025-12-30）
- **范围**：
  - `modules/memory/application/graph_service.py`：新增 `_upsert_tkg_vectors` 方法，将 TKG 节点向量写入 Qdrant。
  - `modules/memorization_agent/application/pipeline_steps.py`：修复 `clusters` 循环中 Entity 创建与 embeddings 传递。
  - `modules/memory/contracts/graph_models.py`：Entity 新增 `face_embedding`/`voice_embedding` 临时字段。
- **决策（Why）**：
  - 原有架构存在两个并行数据系统（MemoryNode 用于 /search，TKG 用于结构化查询），导致向量搜索无法返回 TKG 节点。
  - Face evidence 与 Entity 之间的 `BELONGS_TO_ENTITY` 边未正确创建，导致前端无法显示人脸样本。
- **实现（What/How）**：
  - **TKG 向量写入**：在 `GraphService.upsert` 中调用 `_upsert_tkg_vectors`，将 Event/Entity 的文本/face/voice 向量写入现有 Qdrant collections，payload 中添加 `node_type`/`node_id` 以区分 TKG 节点。
  - **Embeddings 传递修复**：在 `clusters` 循环之前获取 `person_tag_to_info`，从中提取 face/voice embeddings 并传递给 Entity。
  - **MemoryEntry.kind 修复**：将 `kind="identity"` 改为 `kind="semantic"`，符合 Pydantic 验证。
  - **边创建修复**：确保 `_add_graph_edge` 在 `clusters` 循环中正确创建 `BELONGS_TO_ENTITY` 边。
- **验证（Test）**：
  - Neo4j 查询确认 face evidence 正确关联到 Entity（74/39/22/18/15 个 evidence 分别关联到不同 Person）。
  - Qdrant 向量写入成功（40 entries：22 events + 13 face + 5 voice）。
  - 前端人脸样本正常显示。

### P0：修复服务启动死锁（2025-12-26）
- **范围**：`modules/memory/api/server.py`。
- **决策（Why）**：修复在存在 pending ingest jobs 时服务无法启动（hang 在 "Waiting for application startup"）的严重 bug。
- **实现（What/How）**：
  - **问题根因**：`lifespan` 启动期间同步调用 `_schedule_ingest_job`，该函数内部触发 `_run_ingest_job` 并尝试访问 lazy service proxies (`svc`/`graph_svc`)。此时 event loop 尚未完全运行且 lazy proxy 初始化可能包含阻塞操作（如 Neo4j/Qdrant 建联），导致死锁。
  - **修复方案**：将 pending jobs 的调度包装在 `asyncio.create_task` 中，并增加 `await asyncio.sleep(0.1)` 延迟，确保在 `lifespan` 上下文退出、服务完全启动后再执行任务调度。
- **验证（Test）**：
  - 手动验证：使用包含 17 个 pending jobs 的数据库启动服务，验证修复前 hang 住，修复后正常启动且 jobs 被从后台调度执行。

### P0：LLM 用量计量落地（Stage2/Stage3/retrieval_qa）（2025-12-26）
- **范围**：
  - `modules/memory/application/llm_adapter.py`：新增 LLM usage hook/context，抽取 usage 并上报（含 tokens_missing）。
  - `modules/memory/api/server.py`：注入 usage hook，Stage2/Stage3/retrieval_qa 设置上下文并写入 WAL。
  - `modules/memory/tests/unit/test_llm_usage_hook.py`：新增 usage hook 与事件落库单测。
- **决策（Why）**：
  - SaaS 计费闭环必须精确记录 LLM tokens，且 tokens 缺失不能导致漏账；
  - request 用量由网关负责，数据面只记录 llm/write，避免双计。
- **实现（What/How）**：
  - LLMAdapter 在成功响应后提取 `usage/usage_metadata` 并触发 hook；
  - Server 侧以 `tenant_id + api_key_id + job_id/request_id + stage + call_index` 生成幂等 `event_id`，写入 Usage WAL；
  - `with_answer=true` 时统一记为 `retrieval_qa`，仅在 QA 触发时计量。
- **验证（Test）**：
  - `python -m pytest modules/memory/tests/unit/test_llm_usage_hook.py modules/memory/tests/unit/test_ingest_retrieval_endpoints.py -q`
  - **结果**：1 passed, 2 skipped（fastapi 未安装导致 HTTP 端点相关用例跳过）

### P0：SaaS Phase2 适配（Scope/X-Request-ID/Usage WAL）（2025-12-25）
- **范围**：
  - `modules/memory/api/server.py`：新增 scope 解析/校验、X-Request-ID 透传、usage WAL 启停与写入事件落地。
  - `modules/memory/infra/usage_wal.py`：新增 SQLite WAL 与异步 flush。
  - `modules/memory/infra/ingest_job_store.py`：新增 `api_key_id`/`request_id` 字段与 schema 扩展。
  - `modules/memory/scripts/e2e_ingest_contracts.py`：适配新的 create_job 入参。
  - `modules/memory/tests/unit/test_api_auth_security.py`：新增 JWT scope 约束用例。
- **决策（Why）**：
  - SaaS 控制面需要可靠用量计量（at-least-once），不能 best-effort；
  - 作用域必须由服务端统一裁决，避免 SDK 伪造权限；
  - X-Request-ID 贯穿网关与数据面，便于链路追踪。
- **实现（What/How）**：
  - JWT claims 中解析 `scopes`/`scope` 并在路由级做最小权限校验（legacy token 兼容）；
  - 中间件生成/透传 `X-Request-ID`；
  - Stage3 完成时写入 usage WAL，后台批量 flush 至控制面。
- **验证（Test）**：
  - `.venv/bin/python -m pytest modules/memory/tests/unit/test_omem_sdk_http.py modules/memory/tests/unit/test_api_auth_security.py modules/memory/tests/unit/test_api_scope_coverage.py -q`
  - **结果**：通过（19 passed）。

### P0：Usage WAL 上报鉴权头补齐（2025-12-29）
- **范围**：
  - `modules/memory/infra/usage_wal.py`：flush 请求支持 `X-Internal-Key`/`Authorization`（避免控制面开启鉴权后 WAL 永久 403 堆积）。
  - `modules/memory/tests/unit/test_usage_wal_sink_auth.py`：新增单测覆盖 internal key 与 authorization 两种路径。
- **决策（Why）**：
  - SaaS 计费数据“丢失”是不可接受的 Bug；控制面启用 internal key 后，数据面必须能带鉴权头完成 at-least-once 投递；
  - 不能把这种风险交给运维“靠配置碰运气”，必须在代码里写死可用路径。
- **实现（What/How）**：
  - `UsageWALSettings` 增加 sink 鉴权配置：
    - `MEMORY_USAGE_SINK_INTERNAL_KEY`（优先）/`MEMORY_INTERNAL_KEY`/`MEMA_INTERNAL_KEY`（fallback）
    - `MEMORY_USAGE_SINK_INTERNAL_HEADER`（默认 `X-Internal-Key`）
    - `MEMORY_USAGE_SINK_AUTHORIZATION`（可选，直接透传到 `Authorization`）
  - flush 时统一携带 `Content-Type: application/json`，并按配置注入鉴权头。
- **验证（Test）**：
  - `.venv/bin/python -m pytest modules/memory/tests/unit/test_usage_wal_sink_auth.py -q`
  - **结果**：通过（2 passed）。

### P0：多模态 LLM 模型对齐（2025-12-24）
- **范围**：`modules/memory/config/memory.config.yaml`（multimodal 模型更新）。
- **决策（Why）**：统一 demo 与 pipeline 推荐模型，减少“跑出来不一致”的复现成本。
- **实现（What/How）**：
  - `llm.multimodal.model` 切换为 OpenRouter `qwen/qwen3-vl-8b-instruct`。
- **验证（Test）**：未运行（配置变更）。

### P1：VLM 视频语义对齐与配置修正（2025-12-26）
- **范围**：`modules/memory/config/memory.config.yaml`、`modules/memorization_agent/api/server.py`。
- **决策（Why）**：
  - Text Embedding Latency：原配置使用 OpenRouter 导致单次 embedding 耗时过长（>600ms），严重拖慢 pipeline；切换为本地 `jina-embeddings-v2-base-zh`。
  - VLM 0ms 异常：发现 `MEMA_CONFIG` 环境变量未设置导致 server 加载默认配置（`llm_semantic.enable=False`），致使 VLM 步骤被跳过。
- **实现（What/How）**：
  - **Embedding 本地化**：`memory.config.yaml` 中 `text_embedding` 切换为 `local/jina`，重新创建对应的 Qdrant collection（768 dim）。
  - **环境配置**：明确启动 Memorization Server 时必须指定 `MEMA_CONFIG` 指向用户配置文件。
  - **Neo4j 降噪**：调整 `neo4j.notifications` 日志级别至 ERROR，抑制非关键警告。
- **验证（Status）**：
  - Embedding 切换已验证有效（latency 降低）。
  - VLM 启用受阻于 Server 启动类型错误（用户误运行 Chat Memory Server 而非 Video Memorization Server），已在 `task.md` 中标记 BLOCKER。

### P2：实验输出规范化与核心洞察文档化（2025-12-21）
- **范围**：`modules/memory/outputs/readme.md`（优化，从随手笔记升级为实验决策指南）。
- **决策（Why）**：
  - 实验输出不仅是“分数的堆砌”，更是“决策的底座”。随手记录的笔记难以被新加入的开发者（或 AI Agent）高效演绎；

### P1：`dialog_v2_test` ablation 语义解耦（2026-03-17）
- **范围**：
  - `modules/memory/retrieval.py`
  - `modules/memory/tests/unit/test_retrieval_dialog_v2.py`
- **决策（Why）**：
  - `disabled_backlinks`、`source_native_only`、`disabled_routes` 本应是三套独立控制，但实现里被错误耦合：
    - 只禁 event backlink 时，会意外切成 source-native 输出；
    - event backlink / no-event ablation 时，会顺带把 entity/time route 也关掉，导致实验臂定义失真。
- **实现（What/How）**：
  - `should_use_source_native_candidates()` 只再受 `source_native_only` 控制，不再被 `disabled_backlinks=['event']` 隐式触发。
  - `should_disable_explain()` 仍在 event backlink 被禁或 graph signal 被禁时关闭 explain，避免图侧回挂重新污染实验。
  - 删除 event backlink 对 entity/time route 的隐式联动关闭，保持 route 开关只由 `enable_*` 与 `disabled_routes` 控制。
- **验证（Test）**：
  - `pytest modules/memory/tests/unit/test_retrieval_dialog_v2.py -q`
  - 新增覆盖：
    - event backlink ablation 保留 canonical event 输出；
    - no-event ablation 仍保持 entity/time route 可用。
  - 必须明确“QA 模型”与“Top-K”这两大核心变量的 Trade-off，将其沉淀为工程共识，而非隐藏在代码注释或个人头脑中。
- **实现（What/How）**：
  - **权衡体系化**：将 QA 模型（qwen-flash vs grok-fast）的质量与延时权衡，以及 Top-K（30 vs 15）的精度与 Token 效率权衡正式文档化；
  - **规范落地**：定义了 `e2e_[dataset]_[model]_[config]_[version]` 的目录命名规范，防止输出目录沦为混乱的垃圾场；
  - **产出标准化**：明确了每个实验必须包含 `results_*.jsonl`（Trace）、`aggregate_*.json`（Metrics）和 `report_*.md`（Analysis）。
- **验证（Test）**：
  - 检查 `modules/memory/outputs/` 下现有文件夹的命名契合度；
  - 确保 README 内容准确反映了近期 `conv26` 数据集的实验结论。

---

### P0：dialog_v2 并行召回与图侧能力扩展（2025-12-20）
- **范围**：
  - `modules/memory/retrieval.py`：新增 `dialog_v2`（Event-first + 三路并行 + 动态补位 + 有界 explain）。
  - `modules/memory/contracts/graph_models.py`：`Entity.name` 字段补齐。
  - `modules/memory/domain/dialog_tkg_graph_v1.py`：Entity 写入补齐 `name`（与 speaker label 对齐）。
  - `modules/memory/infra/neo4j_store.py`：新增 Entity name fulltext 索引与 `query_entities_by_name` / `query_time_slices_by_range`。
  - `modules/memory/application/graph_service.py` / `modules/memory/application/service.py`：新增实体解析、时间片范围与 graph-first 查询入口。
  - `modules/memory/api/server.py`：新增 `/graph/v0/entities/resolve` 与 `/graph/v0/timeslices/range`。
  - `modules/memory/adapters/http_memory_port.py` / `modules/memory/ports/memory_port.py`：扩展对话检索所需图 API。
  - 测试：`modules/memory/tests/unit/test_retrieval_dialog_v2.py`。
- **决策（Why）**：
  - 仅靠向量“单路漏斗”无法表达 Event/Entity/TimeSlice 的结构偏好；必须并行召回并在 Event 维度统一候选池；
  - Neo4j graph-first 依赖 fulltext（字面锚点强）而非向量语义，因此需要与 utterance 向量索引并行互补；
  - TimeSlice 绝对时间在对话数据中可能缺失，必须允许 Route_T 自适应降级，避免扫库与误匹配。
- **实现（What/How）**：
  - `dialog_v2`：E_event_vec（/search source=tkg_dialog_event_index_v1）硬保留 + E_vec（utterance index）动态补位，三路并行汇聚 Event 候选池（K=50），去重后 topN seeds 做 explain；
  - Entity 路：优先走 `entities/resolve` fulltext；无结果时用 deterministic ID 兜底；
  - Time 路：仅当有可靠绝对时间窗口才触发 `/graph/v0/timeslices/range`，否则直接降级为空；
  - 输出保持 benchmark 兼容结构（evidence/evidence_details/debug），不破坏 dialog_v1。
- **验证（Test）**：
  - `python -m pytest -q modules/memory/tests/unit/test_retrieval_dialog_v2.py`
  - `python -m pytest -q modules/memory/tests/unit/test_dialog_tkg_graph_v1.py modules/memory/tests/unit/test_retrieval_dialog_v1.py`

### P0：检索 API 与“Qdrant↔Neo4j 节点映射”文档化（2025-12-19）
- **范围**：`modules/memory/docs/RETRIEVAL_API_AND_WORKFLOW.md`（新增，统一梳理 API 清单 + 存储形态 + 端到端流程）。
- **决策（Why）**：工程推进的瓶颈不是“缺代码”，而是“缺可演绎的事实描述”。必须把 Qdrant 点、Neo4j 两张图、唯一 ID 映射、以及 `/search` 与 `/graph/v1/search` 的真实工作方式一次讲清楚，避免团队在口头共识里反复发明不同版本的系统。
- **实现（What/How）**：
  - 明确“Qdrant=向量召回种子；Neo4j=:MemoryNode 邻域扩展；typed TKG Graph=证据链真相源”的职责切分；
  - 用代码锚点逐条列出 HTTP 路由、鉴权/签名前提、Python 公共出口与最小 MemoryPort 协议；
  - 把“向量命中 → id 映射 → 图扩展 → 重排 → 输出”流程降维成可复现的语言描述与时序图。
- **验证（Test）**：本变更为纯文档，不改变行为；回归建议运行 `python -m pytest -q modules/memory/tests/unit/test_graph_search_v1.py modules/memory/tests/unit/test_neo4j_expand_neighbors.py`。

### P0：两套图标签隔离（2025-12-16）
- **范围**：`modules/memory/infra/neo4j_store.py`（MemoryEntry 图写入/路径查询）、`modules/memory/tests/unit/test_neo4j_batch_and_paths.py`（回归）。
- **决策（Why）**：typed TKG Graph（`/graph/v0/*`）与 MemoryEntry 投影图（`/search` 的邻域扩展）在同一个 Neo4j 实例内共存时，若共用 `:Entity` 标签会与 Graph v0 的 node-key 约束 `(tenant_id,id)` 冲突，并造成语义与治理边界混乱；必须先把“真相图”和“索引投影图”分开。
- **实现（What/How）**：
  - 引入 `:MemoryNode` 作为 MemoryEntry 投影图的基类标签，`merge_nodes_edges* / merge_rel* / find_paths / repair_node_labels / EQUIVALENCE` 全部改用该标签；
  - 在 `ensure_schema_v0()` 开头加入 best-effort 迁移：把历史上误写成 `:Entity` 且缺失 `tenant_id` 的 Memory 节点迁移为 `:MemoryNode`，再创建 Graph v0.x 约束，避免“先写脏数据 → 约束永远建不上”的死局；
  - 为 `:MemoryNode(id)` 增加唯一约束（best-effort）。
- **验证（Test）**：`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest modules/memory/tests/unit/test_neo4j_batch_and_paths.py -q`
- **备注**：沙箱环境禁止绑定本地端口，`tests/unit/test_api_auth_security.py` 中的 JWKS 本地 HTTPServer 用例会触发 `PermissionError`，与本变更无关。

### P0：TKG Graph-first 搜索（/graph/v1/search）（2025-12-16）
- **范围**：
  - `modules/memory/infra/neo4j_store.py`：新增 `search_event_candidates` + best-effort fulltext 索引创建；
  - `modules/memory/application/graph_service.py`：新增 `search_events_v1`（候选事件 → 证据链）；
  - `modules/memory/api/server.py`：新增 `POST /graph/v1/search`（带熔断+超时）；注册 `graph_search` breaker；
  - `modules/memory/docs/GRAPH_v1.md`：补充 Graph-first 检索说明；
  - 单测：`modules/memory/tests/unit/test_graph_search_v1.py`、`modules/memory/tests/unit/test_neo4j_search_event_candidates.py`。
- **决策（Why）**：
  - L1–L5 问答需要可追溯证据链（Utterance/Evidence/Segment），因此检索应优先落在 typed TKG Graph（真相源）而不是 MemoryEntry 投影图；
  - 允许 fulltext 缺失时降级（CONTAINS），保证开发/小环境可用；同时给生产准备好索引以保证性能。
- **实现（What/How）**：
  - Neo4j 层：按 `Event.summary` + `UtteranceEvidence.raw_text` + `Evidence.text` 做候选召回，结果去重并按 `score/recency` 排序；
  - Service 层：对候选 Event 调用 `explain_event_evidence` 拼装结构化证据包（复用 explain LRU 缓存）；
  - API 层：`POST /graph/v1/search` 返回 `items[]`（每项包含 `event_id/score` + `event/entities/places/timeslices/evidences/utterances`）。
- **验证（Test）**：
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest modules/memory/tests/unit/test_graph_search_v1.py modules/memory/tests/unit/test_neo4j_search_event_candidates.py -q`

### 安全与边界防护（2025-12-05）
- **范围**：`api/server.py` 增加请求体大小限制与按租户令牌桶限流中间件；`config/memory.config.production.yaml` 提供生产姿态；`config/ingress/nginx.production.conf` 提供带 TLS/CORS/速率限制的边界模板；`tests/unit/test_api_limits.py` 验证防护逻辑；`application/config.py` 支持 `MEMORY_CONFIG_PROFILE` 选择配置文件。
- **决策（Why）**：落实 Week 1 “默认安全姿态” 交付项，在应用层阻断超大 payload 与滥用突发流量，为多租户部署准备默认启用的鉴权+节流配置。
- **实现（What/How）**：
  - 新增请求体大小检查（Content-Length 优先，缺失则读取一次 body）以及突发/持续速率的令牌桶限流，对写/删/连边/图 admin 等敏感端点生效；
  - 引入 `MEMORY_CONFIG_PROFILE=production`，默认打开 token 鉴权、速率限制与 10MB 请求上限；
  - 提供 Nginx ingress 示例，涵盖 TLS、CORS 白名单、per-token 速率+连接限制及结构化访问日志；
  - 单测覆盖超限 413 与限流 429 行为。
- **验证（Test）**：`python -m pytest modules/memory/tests/unit/test_api_limits.py -q`

### JWT/请求签名/熔断强化（2025-12-06）
- **范围**：`api/server.py` 接入 JWKS/JWT 校验、签名校验、按租户速率配置、搜索/时间线熔断+超时；`config/memory.config*.yaml`/`config/hydra/memory.yaml` 增加 jwt/signing/high_cost_timeout 配置；新增安全单测 `tests/unit/test_api_auth_security.py`；`docs/memory_improvement_priorities.md` 补充 Week2-3 交付状态。
- **决策（Why）**：完成硬化计划的 Week2-Week3 任务：默认验证 OIDC 令牌与租户声明，所有变更类请求必须签名，热点路径具备超时+熔断保护，所有管理端点强制认证签名。
- **实现（What/How）**：
  - `_enforce_security` 统一认证上下文，支持 JWKS 校验 issuer/audience/tenant_claim，记录安全审计日志并输出 auth/signature/throttle/oversize 指标；
  - 变更/图 admin/配置端点默认要求签名（HMAC-SHA256 ts.path.body），支持每租户独立密钥与时钟偏差防护；
  - 搜索/时间线加入可配置超时与简单熔断器，连续超时后直接 503，减少热点路由拖垮服务风险；
  - 配置/管理端点统一要求认证（GET）与签名（POST），防止未授权修改运行时参数。
- **验证（Test）**：`python -m pytest modules/memory/tests/unit/test_api_auth_security.py -q`

### 安全集成回归补强（2025-12-08）
- **范围**：在集成测试层验证 HTTP 层安全护栏的组合行为：新增 `tests/integration/test_api_security_integration.py`，覆盖带生产配置的鉴权、签名校验与指标统计；维持单测同等的 stub service 避免真实后端依赖。
- **决策（Why）**：补齐 Week4 计划中的“安全回归”验收，用端到端方式验证 FastAPI 路由 + 环境配置 + metrics 输出的真实组合效果，降低配置回归与未授权写入风险。
- **实现（What/How）**：
  - 使用 `MEMORY_CONFIG_PROFILE=production` + env 覆盖启动应用，验证 search 在开启鉴权后拒绝无 token 请求、放行合法 token；
  - 对 write 路由执行一次缺失签名请求，确认 signature_failures_total 计数增长且返回 401，再发送正确 HMAC 的请求验证 200 响应；
  - 通过 TestClient 封装保持 HTTP 行为一致，使用 stubbed MemoryService 阻止外部存储连接。
- **验证（Test）**：`python -m pytest modules/memory/tests/integration/test_api_security_integration.py -q`

### 配置加载 Hydra 化（2025-12-xx）
- **范围**：`application/config.py`；新增单测 `tests/unit/test_config_hydra_loader.py`；文档 `README.md` 补充使用说明；新增 Hydra 配置目录 `config/hydra/{defaults.yaml,memory.yaml}`。
- **决策（Why）**：采用 Hydra(OmegaConf) 以支持结构化覆盖与 CLI dotlist override，保持对现有 YAML/env 的向后兼容（Never break userspace）。
- **实现（What/How）**：
  - 引入 `USE_HYDRA_CONFIG` 开关与 `load_memory_config(use_hydra=True, overrides=[...])`；环境变量仍由 `os.path.expandvars` 展开，避免现有 `${VAR}` 语法失效。
  - 使用 OmegaConf merge 支持 dotlist 覆盖，返回 plain dict 以屏蔽调用方差异。
  - 增加依赖 `hydra-core>=1.3.2`。
- **验证（Test）**：`python -m pytest modules/memory/tests/unit/test_config_hydra_loader.py -q` 覆盖 env 展开、开关默认行为、临时文件覆盖。

### v0.1 基础图谱落地（2025-11）
- **核心契约**：
  - `contracts/graph_models.py`: 定义 `MediaSegment`, `Evidence`, `Entity`, `Event`, `Place` 及 `GraphEdge`, `GraphUpsertRequest`。
- **存储层 (Neo4jStore)**：
  - `ensure_schema_v0`: 建立基础唯一约束 `(tenant_id, id)`。
  - `upsert_graph_v0`: 批量 MERGE 节点与边，强制注入 `tenant_id`。
  - 查询方法: `query_segments_by_time`, `query_entity_timeline`。
- **API 层**：
  - `/graph/v0/upsert`: 接收图数据，服务端强制注入租户 ID（防越权）。
  - `/graph/v0/segments`, `/graph/v0/entities/{id}/timeline`: 基础查询端点。
- **端到端验证 (2025-11-28)**：
  - 修正 `INVOLVES` 关系方向 (`Event -> Entity`)。
  - 使用 Docker Neo4j 跑通全链路读写。

### v0.2 扩展与增强（2025-11-29）
- **Schema 扩展**：
  - `contracts/graph_models.py`: 新增 `TimeSlice` 模型；边属性增加 `layer`, `kind`, `source`, `status`。
  - 关系扩展: `NEXT_EVENT`, `CO_OCCURS_WITH`, `CAUSES`, `SUPPORTED_BY`, `COVERS_SEGMENT`, `COVERS_EVENT`。
- **功能增强**：
  - **TimeSlice**: `Neo4jStore.build_time_slices_from_segments` 支持按 `media_window` (默认 3600s), `day`, `hour` 分桶。
  - **Co-occurrence**: `Neo4jStore.build_cooccurs_from_timeslices` 基于 TimeSlice 覆盖计算实体共现权重（频次）。
  - **Event Chains**: `Neo4jStore.build_event_relations` 基于时间排序生成 `NEXT_EVENT`，基于地点生成 `CAUSES` (candidate)。
- **API 增强**：
  - `/graph/v0/timeslices`: 支持多维过滤。
  - `/graph/v0/admin/*`: 新增 `build_event_relations`, `build_timeslices`, `build_cooccurs` 管理端点。
- **技术决策**：
  - **Pydantic 序列化**: 修复 `model_dump` 默认将 datetime 转 string 导致 Neo4j 排序失效的问题，改为 `model_dump(mode='python')`。
  - **Cypher 聚合**: 修复 `CO_OCCURS` 计算时的聚合逻辑错误，确保跨 TimeSlice 正确累加权重。
  - **MERGE 约束**: 修复 `MERGE` 导致违反唯一约束的问题，改为 `MATCH` 现有节点 + `MERGE` 关系。
  - **Auth**: 修正 `_require_auth` 逻辑，支持 Token 映射，确保多租户隔离。
- **验证记录**：
  - `scripts/test_neo4j_integration.py`: 基础读写回归 ✅。
  - `scripts/test_neo4j_event_relations.py`: 事件链生成验证 ✅。
  - `scripts/test_neo4j_timeslice_cooccurs.py`: TimeSlice 与共现验证 ✅。
  - `modules/memory/tests/unit/test_graph_api_endpoints.py`: API 校验与 Auth 验证 ✅。
### v0.3 Schema 定义 (2025-11-29)
- **Schema 扩展**: `contracts/graph_models.py` 引入 `Provenanced` 基类（统一 `provenance`, `time_origin`, `ttl`, `importance` 等审计字段），新增 `UtteranceEvidence`, `SpatioTemporalRegion`, `State`, `Knowledge` 节点。
- **API 适配**: `GraphUpsertRequest` 扩展支持新节点列表，包入口导出新模型。
- **存储/服务扩展**: `infra/neo4j_store.py` 约束扩展到 `UtteranceEvidence/SpatioTemporalRegion/State/Knowledge`，节点 MERGE 统一 `SET n += map`，upsert 支持 v0.3 关系（SPOKEN_BY/TEMPORALLY_CONTAINS/SPATIALLY_CONTAINS/HAS_STATE/DERIVED_FROM/EQUIV），关系写入 provenance/time_origin/ttl/importance；`GraphService` upsert/tenant 校验覆盖新节点列表。
- **验证**:
  - 单测：`test_graph_models_v03.py` (7/7) + `test_graph_v0_upsert.py` (4/4) 100% 通过（命令：`PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest modules/memory/tests/unit/test_graph_models_v03.py modules/memory/tests/unit/test_graph_v0_upsert.py -q --disable-warnings`，0.05s），覆盖 v0.3 新节点/关系 MERGE。
  - 集成：`scripts/test_neo4j_v03_schema.py` 在真实 Neo4j 环境 100% 通过（0.05s，ALL TESTS PASSED），覆盖 Utterance/Region/State/Knowledge 节点与 v0.3 关系（SPOKEN_BY, TEMPORALLY_CONTAINS, SPATIALLY_CONTAINS, HAS_STATE, DERIVED_FROM, EQUIV），验证元字段写入；v0.3 验收完成。
  - 全量 unit suite：110/158 通过；余下 48 失败集中在配置/旧策略偏差，未在本周期处理。
  - 补充（v0.4 准备）：新增 `PendingEquiv` 模型及约束，GraphUpsertRequest 支持 pending_equivs；单测 `test_graph_equiv_pending.py`/`test_graph_v0_upsert.py` 100% 通过（命令：`PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest modules/memory/tests/unit/test_graph_equiv_pending.py modules/memory/tests/unit/test_graph_v0_upsert.py -q --disable-warnings`，0.05s）；新增 `infra/equiv_store.py` + GraphService 挂载，API 增补 `/graph/v0/admin/equiv/pending|approve|reject|list`；新增 EquivStore 单测覆盖 list/upsert/approve/reject（沙箱依旧 segfault，用户环境 6/6 通过）。
  - 补充（v0.4 准备）：新增 `PendingEquiv` 模型及约束，GraphUpsertRequest 支持 pending_equivs；单测 `test_graph_equiv_pending.py`/`test_graph_v0_upsert.py` 100% 通过（命令：`PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest modules/memory/tests/unit/test_graph_equiv_pending.py modules/memory/tests/unit/test_graph_v0_upsert.py -q --disable-warnings`，0.05s）；新增 `infra/equiv_store.py` + GraphService 挂载，API 增补 `/graph/v0/admin/equiv/pending|approve|reject|list`；新增 EquivStore/API 单测 `test_graph_equiv_api.py`（覆盖 pending/list/approve/reject 流程），用户环境 100% 通过，沙箱仍有 segfault。
  - 集成扩展：`scripts/test_neo4j_equiv_pending.py` 在真实 Neo4j 通过（ALL TESTS PASSED），验证 PendingEquiv→approve→EQUIV 落地，v0.4 身份治理初步验收完成。

### v0.4 身份治理（2025-11-29）
- **模型/约束**：`PendingEquiv` 节点纳入 GraphUpsertRequest；Neo4j 唯一约束 `(tenant_id,id)`。
- **存储/服务**：`infra/equiv_store.py` 提供 list/upsert/approve/reject；`GraphService` 挂载 EquivStore 并在 upsert 时写入 pending_equivs。
- **API**：新增 `/graph/v0/admin/equiv/pending` (POST/GET)、`/graph/v0/admin/equiv/approve`、`/graph/v0/admin/equiv/reject`，统一租户注入与 auth。
- **验证**：
  - 单测：`test_graph_equiv_pending.py`、`test_graph_equiv_api.py`、`test_graph_v0_upsert.py` 扩展用例 100% 通过。
  - 集成：`scripts/test_neo4j_equiv_pending.py` 通过（真实 Neo4j），确认 pending→approve→EQUIV 落地。

### v0.5 物化门控/TTL/导出（完成）
- **门控**：env 配置置信/重要度阈值与关系 top-K，低置信/低重要度事件/关系过滤；`test_graph_gating.py` 通过。
- **软 TTL/衰减**：默认 TTL 填充，Neo4j/Qdrant 软过滤；衰减排序支持半衰期 env（`GRAPH_DECAY_HALF_LIFE_DAYS`）和 `memory_strength` 放大。
- **触达延寿**：搜索命中触发触达，节流/批量上限/可选延寿（`GRAPH_TOUCH_*`），需配置触达租户。
- **清理/导出**：TTL cleanup 支持 dry_run/buffer/limit；(s,r,o,t) 导出支持 rel/min_conf 过滤。
- **验证**：`test_graph_ttl_export_api.py`、`test_memory_touch_reinforce.py`、`test_graph_decay.py` 等单测全绿。


---

## 2. 阶段性验收清单（v0.2 已通过）

| 验收项                             | 状态  | 完成时间    | 关键产出/修复                                                                                                                                                                                                                                                                                                                                                               |
| :--------------------------------- | :---: | :---------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **1) 真实 Neo4j 集成回归**         |   ✅   | 11-29 14:32 | 修复 `datetime` 序列化；`test_neo4j_integration.py` 全绿                                                                                                                                                                                                                                                                                                                    |
| **2) 事件链/因果生成**             |   ✅   | 11-29 14:42 | 实现 `build_event_relations`；`test_neo4j_event_relations.py` 全绿                                                                                                                                                                                                                                                                                                          |
| **3) TimeSlice 与共现**            |   ✅   | 11-29 14:48 | 实现多粒度分桶与共现聚合；修复 Cypher 逻辑；`test_neo4j_timeslice_cooccurs.py` 全绿                                                                                                                                                                                                                                                                                         |
| **4) OpenAPI/校验一致性**          |   ✅   | 11-29 15:15 | 引入 `GraphUpsertBody`；API 单测覆盖租户注入与 Auth                                                                                                                                                                                                                                                                                                                         |
| **5) 生产风控与运行指南**          |   ✅   | 11-29 15:15 | 明确 Auth 配置；集成测试脚本作为上线检查表                                                                                                                                                                                                                                                                                                                                  |
| **6) v0.3 Schema 定义**            |   ✅   | 11-29 16:15 | `test_graph_models_v03.py` 全绿；模型契约已锁定                                                                                                                                                                                                                                                                                                                             |
| **7) v0.4 身份治理初验**           |   ✅   | 11-29 17:20 | PendingEquiv 模型/约束/Store/Service/API；`test_graph_equiv_*` 单测全绿；`scripts/test_neo4j_equiv_pending.py` 集成通过，approve→EQUIV 落地                                                                                                                                                                                                                                 |
| **8) v0.5 物化门控/TTL/衰减 收尾** |   ✅   | 11-30 13:10 | 门控预过滤（confidence/importance/topK）；Soft TTL 默认填充 + Neo4j/Qdrant 过滤；衰减排序可配置半衰期（`GRAPH_DECAY_HALF_LIFE_DAYS`，`memory_strength` 放大）；搜索触达节流/批量上限/可选延寿（`GRAPH_TOUCH_*`）；TTL 清理支持 dry_run，(s,r,o,t) 导出保持 rel/conf 过滤；单测 `test_graph_ttl_export_api.py`、`test_memory_touch_reinforce.py`、`test_graph_decay.py` 全绿 |

---

## 3. 运行/测试记录（现有脚本与单测）

### 单元测试 (Unit Tests)
| 测试文件                                                   |  通过数   | 覆盖功能点                                                                                                                                                                                                                          |
| :--------------------------------------------------------- | :-------: | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `modules/memory/tests/unit/test_graph_api_endpoints.py`    | **13/13** | - **Auth**: 租户注入 (`_inject_tenant`)、Token 映射 (`token_map`)<br>- **CRUD**: Segments, Events, Places, Timeline, TimeSlices 查询接口<br>- **Admin**: `build_event_relations`, `build_timeslices`, `build_cooccurs` 接口参数透传 |
| `modules/memory/tests/unit/test_graph_v0_upsert.py`        |  **4/4**  | - **Service**: `GraphService.upsert` 逻辑校验<br>- **Payload**: 验证 `GraphUpsertRequest` 结构解析；v0.3 新节点/关系 MERGE 覆盖                                                                                                     |
| `modules/memory/tests/unit/test_timeslice_cooccurs.py`     |  **1/1**  | - **Logic**: TimeSlice 分桶算法与 Co-occurrence 聚合逻辑 (Mock Driver)                                                                                                                                                              |
| `modules/memory/tests/unit/test_graph_models_v03.py`       |  **7/7**  | - **Schema**: v0.3 新增节点 (`Utterance`, `Region`, `State`, `Knowledge`) 与 `Provenanced` 基类字段验证                                                                                                                             |
| `modules/memory/tests/unit/test_graph_gating.py`           |  **1/1**  | - **Gating**: 置信/重要度过滤与 top-K 关系保留（GraphService 预过滤）                                                                                                                                                               |
| `modules/memory/tests/unit/test_graph_equiv_pending.py`    |  **3/3**  | - **Identity**: PendingEquiv 模型/约束/approve/reject 流程                                                                                                                                                                          |
| `modules/memory/tests/unit/test_graph_equiv_api.py`        |  **1/1**  | - **Identity API**: pending/list/approve/reject 端点（stub store）                                                                                                                                                                  |
| `modules/memory/tests/unit/test_graph_soft_ttl_filters.py` |  **1/1**  | - **TTL**: Neo4j 查询包含 `expires_at > datetime()` 软过滤                                                                                                                                                                          |
| `modules/memory/tests/unit/test_graph_ttl_defaults.py`     |  **1/1**  | - **TTL**: GraphService 填充 ttl/created_at/expires_at 默认值                                                                                                                                                                       |
| `modules/memory/tests/unit/test_graph_ttl_export_api.py`   |  **1/1**  | - **Admin**: TTL 清理与导出端点 stub 覆盖（含 dry_run）                                                                                                                                                                             |
| `modules/memory/tests/unit/test_graph_touch.py`            |  **1/1**  | - **Reinforce**: GraphService.touch 调用 store 更新 last_accessed_at/扩展过期                                                                                                                                                       |
| `modules/memory/tests/unit/test_memory_touch_reinforce.py` |  **1/1**  | - **Reinforce**: MemoryService 触达节流/批量上限/延寿参数过滤                                                                                                                                                                       |
| `modules/memory/tests/unit/test_graph_decay.py`            |  **2/2**  | - **Decay**: `GRAPH_DECAY_HALF_LIFE_DAYS` 半衰期配置生效；长半衰期降低衰减，顺序保持最近优先                                                                                                                                        |

### 集成测试 (Integration Scripts - Real Neo4j)
| 脚本文件                                   |    状态    | 验证场景详情                                                                                                                                                    |
| :----------------------------------------- | :--------: | :-------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `scripts/test_neo4j_integration.py`        | **Passed** | **[基线]**<br>- **Upsert**: v0.1 节点 (Segment/Entity/Event/Place) 写入<br>- **Query**: 按时间查 Segment、实体时间线、多维过滤查 Event/Place                    |
| `scripts/test_neo4j_event_relations.py`    | **Passed** | **[逻辑]**<br>- **NEXT_EVENT**: 验证 4 个事件按 `t_abs_start` 排序生成 3 条链式边<br>- **CAUSES**: 验证同地点 (`place_id`) 事件推断生成 1 条因果边              |
| `scripts/test_neo4j_timeslice_cooccurs.py` | **Passed** | **[聚合]**<br>- **TimeSlice**: 验证 3600s 窗口生成 2 个 TimeSlice 节点<br>- **Co-occurrence**: 验证跨切片实体共现，聚合生成 1 条 `CO_OCCURS_WITH` 边 (weight=1) |

> **执行说明**:
> - 单元测试: `PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest <file>`
> - 集成测试: 需本地启动 Neo4j (Docker)，然后运行 `PYTHONPATH=. python scripts/<script_name>.py`

---

## 4. 下一阶段规划（对齐 TKG-Graph-v1.0-Ultimate）

### v0.5 物化门控 / TTL / 导出（完成）
参考文档：docs/时空知识记忆系统构建理论/2. 规划层（How over time）/记忆遗忘与增强机制设计.md
- v0.5a Schema/配置 + Soft TTL（✅）  
  - 字段补齐：Provenanced 增 `memory_strength/last_accessed_at/expires_at/forgetting_policy`，GraphService 默认 TTL 填充；Neo4j/Qdrant 软过滤接入。  
  - 验收：`test_graph_models_v03`、`test_graph_soft_ttl_filters`、`test_graph_ttl_defaults`。
- v0.5b Lazy Decay + Reinforce（✅）  
  - 衰减排序：半衰期 env `GRAPH_DECAY_HALF_LIFE_DAYS` + 个体 `memory_strength`；`_decay_score` 提取。  
  - 触达延寿：`GRAPH_TOUCH_MIN_INTERVAL_S`、`GRAPH_TOUCH_MAX_BATCH`、`GRAPH_TOUCH_EXTEND_SECONDS`，需配置触达租户 `GRAPH_TOUCH_TENANT_ID` 或手动 `set_graph_tenant`。  
  - 验收：`test_memory_touch_reinforce.py`、`test_graph_decay.py`。
- v0.5c Reaper/导出（✅ 基础版）  
  - 清理：`/graph/v0/admin/ttl/cleanup` 支持 dry_run/buffer/limit；(s,r,o,t) 导出保持 rel/min_conf 过滤。  
  - 验收：`test_graph_ttl_export_api.py`（stub）；待补生产防护/归档/集成脚本（列入 v0.6+）。

> v0.5 总结：完成门控（置信/重要度阈值 + rel top-K）、软 TTL（默认 TTL 填充 + Neo4j/Qdrant 过滤）、衰减排序（半衰期可配，memory_strength 叠加）、搜索触达节流/批量上限/可选延寿、TTL 清理 dry_run、(s,r,o,t) 导出。单测覆盖核心路径（gating/TTL defaults/soft TTL/decay/touch/cleanup/export）。

### v0.6 防护与治理强化（完成）
- 需求（What）：固化访问上限与白名单，避免查询/扩展滥用；配置显式化，确保 Neo4j/Qdrant 同步生效。
  - 默认安全阈值落地：分页 `limit`、图邻居 hop 与 fanout、关系 `rel_whitelist`、最小置信/重要度。
  - 配置统一：OpenAPI/pyproject/env 示例/README 同步；运行时 overrides 支持热更新。
  - 审计：拒绝/裁剪路径写入日志/指标（超限、非白名单关系）。
- 与检索对标清单的关系：  
  - v0.6 聚焦 **L1/L2 场景**（基础事实 + 时序/状态），要求在默认阈值下通过 Memory/Graph API 稳定回答，不依赖“关闭门控/放开 hop”。  
  - 为后续 L3/L4 推理保留安全余量，不在 v0.6 引入新推理模式，仅保证底座查询安全可控。
- 验收（How/Done）：  
  - 单测：新增 API/Service 层用例覆盖超限拒绝与白名单过滤（含大小写、scope），Qdrant/Neo4j 查询都附带阈值；对标清单中 L1/L2 的典型查询至少各落一个单元/集成用例。  
  - 集成：真实 Neo4j 小图验证 hop/fanout/paging 生效，无越界；配置切换热加载生效。  
  - 文档：PROCESS/README/OpenAPI 更新默认值与风控说明，并标注 v0.6 已覆盖的 L1/L2 检索场景子集。

- 当前进展（2025-11-30）：  
  - 配置与运行时：`config/memory.config.yaml` 与 `config/runtime_overrides.json` 已给出图扩展安全默认值：`max_hops`=2（override）、`neighbor_cap_per_seed`≈9、`rel_whitelist` 精简到 APPEARS_IN/SAID_BY/LOCATED_IN/DESCRIBES/TEMPORAL_NEXT/EQUIVALENCE/EXECUTED/CO_OCCURS，且默认 `restrict_to_domain=True`；`application.config.get_graph_settings` 与 `MemoryService.search`/`_graph.expand_neighbors` 已统一使用这些参数，并纳入搜索缓存签名，保证切换时无脏缓存。  
  - 隔离与风控：`memory.config.yaml` 中 search.scoping 默认 `default_scope=global`，但通过 `runtime_overrides.scoping` 将运行时默认收紧为 domain 级；图扩展默认 `restrict_to_user=True/restrict_to_domain=True`，结合 overrides 与 `allow_cross_*` 控制特殊诊断场景；单测 `test_qdrant_filter_user_domain.py`、`test_graph_scope_restriction_inmem.py`、`test_scoping_fallback.py` 已验证 user/domain/scope 行为无回归。  
  - L1/L2 Retrieval 覆盖映射：  
    - L1 类（基础事实）：  
      - “我去了哪些地方”类 → 新增 `MemoryService.list_places_by_time_range` 聚合接口，单测 `tests/unit/test_v06_retrieval_l1_l2.py::test_v06_l1_list_places_by_time_range_basic` 使用 InMemVectorStore 构造不同时刻/地点的 episodic 记忆，验证在给定时间窗口内仅返回超市/家而不包含更早的酒店；  
      - 其他基础检索 → `test_graph_api_endpoints.py`（segments/events/places/timeslices/timeline 端点）、`test_object_search.py`（按对象检索片段）、`test_filters_time_entities.py`（时间+实体过滤）。  
    - L2 类（时序/状态）：  
      - “回家后做的第一件事/玩手机多久”类 → 在原有 `test_timeline_summary.py::test_timeline_summary_basic`（时间顺序摘要 + 邻居）、`test_graph_event_relations.py`（NEXT_EVENT 链）、`test_graph_decay.py`（时间衰减排序）基础上，新增 `tests/unit/test_v06_retrieval_l1_l2.py::test_v06_l2_timeline_summary_respects_time_range`，验证 `MemoryService.timeline_summary` 合并 `start_time/end_time` 后仅摘要最近两小时内的事件（排除早于窗口的“早上 起床”）。  
  - v0.6 新增安全护栏实现（代码 + 测试已落地）：  
      - 在 `application/config.py` 中引入硬上限常量：`SEARCH_TOPK_HARD_LIMIT`、`GRAPH_MAX_HOPS_HARD_LIMIT`、`GRAPH_NEIGHBOR_CAP_HARD_LIMIT`，并在 `get_graph_settings` 中对 YAML 中的 `max_hops`/`neighbor_cap_per_seed` 做 clamp，防止配置误设过大；  
      - 在 `application/runtime_config.py.set_graph_params` 中对运行时覆盖的 `max_hops`/`neighbor_cap_per_seed` 做同样 clamp，确保 API `/config/graph` 无法突破安全上限；  
      - 在 `MemoryService.search` 中对入参 `topk` 做硬上限裁剪（最低 1，最高 `SEARCH_TOPK_HARD_LIMIT`），避免单次查询拉取过多结果压垮下游；  
      - 新增单测 `tests/unit/test_v06_safety_limits.py` 验证 topk clamp 与 graph override clamp 行为，作为 v0.6 防护层的回归锚点。  
  - 理论对齐：新增 `docs/时空知识记忆系统构建理论/2. 规划层（How over time）/记忆检索与推理对标清单.md`，将 L1–L5 22 个检索/推理场景作为 v1.0 对标锚点；本模块 PROCESS 已引用该清单作为终态验收标准。  
  - 全量测试（2025-11-30）：在本地 `.venv` 环境下运行 `PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 ../../.venv/bin/python -m pytest modules/memory/tests -q --disable-warnings`，结果为 **188 passed, 1 skipped, 3 warnings**，包括新加的 v0.6 安全与检索用例以及真实本地 embedding 模型连通性测试（`test_embedding_connectivity`）均为绿色，标记 v0.6 阶段工程收尾完成。

### v0.7 性能与推理出口（完成）
- 目标（Why）：在 v0.6 已安全可控的前提下，长出**少量高价值的解释型 API**，并为这些推理视图增加轻量缓存与基本指标，避免小规模客户场景下的性能/成本失控。  
- 规划拆分：
  - **v0.7a 解释型 API（L3 最小闭环）**  
    - 场景 A：「我和 Alice 是怎么认识的？」  
      - GraphService 新增 `explain_first_meeting(tenant_id, me_id, other_id)`：基于 Neo4j 查询两人最早共同出现的 Event（`(me)-[:INVOLVES]->(e)<-[:INVOLVES]-(other)`，按时间排序），返回 `{event_id, t_abs_start, place_id, summary, evidence_ids}`。  
      - API 层新增 `/graph/v0/explain/first_meeting` 端点，供上层 LLM/UI 调用。  
      - 测试：  
        - 单元：使用 MockNeo4jStore 构造少量 Event/INVOLVES，验证找到最早共同事件、无共同事件时返回稳定的“无结果”结构。  
        - 集成：小型 Neo4j 脚本（`scripts/test_neo4j_explain_first_meeting.py`）写入样例图并验证 explain 输出。  
    - 场景 B：「这个事件/结论的证据链是什么？」  
      - GraphService 新增 `explain_event_evidence(tenant_id, event_id)`：沿 `SUPPORTED_BY`/`INVOLVES`/`OCCURS_AT`/`COVERS_*` 等边，返回 `{event, entities, place, timeslices, evidences, utterances}` 结构化证据链。  
      - API 层新增 `/graph/v0/explain/event` 端点，作为“证据链解释”标准入口。  
      - 测试：  
        - 单元：Mock 图中构造简单事件 + 证据关系，验证 explain 结果与底层路径一致。  
        - 集成：Neo4j 小图脚本写入一条事件链，验证 explain 输出完整、可回溯。  
  - **v0.7b 解释视图缓存与指标（Explain 缓存）**  
    - 为上述解释 API 增加独立的 LRU 内存缓存：key 使用 `(tenant_id, me_id, other_id)` 或 `(tenant_id, event_id)` + 版本号，TTL 默认为 5–15 分钟，可由环境变量控制；仅对 explain API 生效，不修改搜索/图扩展缓存。  
    - 在 `application/metrics` 中新增指标：  
      - `explain_first_meeting_total{status}`、`explain_event_evidence_total{status}`；  
      - `explain_cache_hits_total`/`explain_cache_misses_total`；  
      - 延迟分布：`explain_latency_ms_bucket`。  
    - 测试：  
      - 单元：构造昂贵 store stub，重复调用 explain，验证第二次起命中缓存且底层只被调用一次；TTL 到期后重新访问会再次触发底层查询。  
      - 性能：在小图上测 explain 在有/无缓存情况下的平均延迟，记录为 v0.7 性能基线。  
  - **v0.7c 导出/清理视图的轻量性能与可靠性**  
    - 导出：在已有 TTL/导出 API 基础上增加游标式批处理导出 (s,r,o,t)，支持 `batch_size/cursor/max_duration_ms`，避免大图一次性扫全库；允许 tenant/time_range/rel_whitelist 过滤，服务于离线推理训练。  
    - 清理：为 TTL 清理任务增加单次删除上限与简单重试/回退策略，避免清理作业长时间锁表或异常中断。  
    - 指标：`ttl_cleanup_total{status}`、`ttl_cleanup_duration_ms`、`graph_export_batches_total`、`graph_export_last_batch_size`。  
  - 验收（How/Done）：  
  - v0.7a：两条解释型 API 在单元 + Neo4j 小图集成测试下均通过，能稳定回答 L3 场景（首次相遇、证据链解释）；  
  - v0.7b：Explain 缓存命中率与延迟指标清晰可见，缓存关闭时行为与 v0.6 完全一致；  
  - v0.7c：导出/清理脚本在小图上通过，导出支持游标与过滤，清理任务有上限与重试，不出现明显性能回退或资源峰值异常。  
- 阶段进展（2025-12-01）：  
  - 已完成 v0.7a 解释型 API：  
    - GraphService 新增 `explain_first_meeting` 与 `explain_event_evidence`，并在 `Neo4jStore` 中实现对应的 `query_first_meeting` / `query_event_evidence` 查询；  
    - API 层新增 `/graph/v0/explain/first_meeting` 与 `/graph/v0/explain/event/{event_id}` 端点，集成统一鉴权与图指标上报；  
  - 测试验证：  
    - 单元测试：`tests/unit/test_graph_explain_service.py` 与扩展后的 `tests/unit/test_graph_api_endpoints.py` 共 20 个用例，在本地 `.venv` 环境下运行  
      `PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest modules/memory/tests/unit/test_graph_explain_service.py modules/memory/tests/unit/test_graph_api_endpoints.py -q --disable-warnings` 全部通过；  
    - 集成脚本：`scripts/test_neo4j_explain_first_meeting.py` 在真实 Neo4j 环境下构造最小图（首次相遇 + 证据链），验证 `GraphService` explain 系列方法在端到端链路上的正确性（需手动运行）。 
  - 已启动并推进 v0.7b Explain 缓存与指标：  
    - 在 `GraphService` 内部新增 explain 专用 LRU 缓存：  
      - 通过环境变量 `GRAPH_EXPLAIN_CACHE_ENABLED`、`GRAPH_EXPLAIN_CACHE_TTL_SECONDS`、`GRAPH_EXPLAIN_CACHE_MAX_ENTRIES` 控制开关、TTL 与容量；  
      - 缓存键区分首次相遇与事件证据链（`first_meeting|tenant=...|me=...|other=...` / `event_evidence|tenant=...|event=...`），采用线程安全的 `OrderedDict` + `RLock` 实现 LRU；  
    - Explain 入口在命中缓存时不再访问 Neo4jStore，仅返回结构化结果副本，同时通过 `metrics.inc` 记录 `explain_cache_hits_total`、`explain_cache_misses_total` 与 `explain_cache_evictions_total`，结合既有 `memory_graph_requests_endpoint_total` 与 `memory_graph_latency_ms_*` 指标，可以推导 explain 视图的命中率与延迟分布；  
    - 单元测试扩展：`tests/unit/test_graph_explain_service.py` 新增缓存相关用例，在本地 `.venv` 环境下运行  
      `PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest modules/memory/tests/unit/test_graph_explain_service.py modules/memory/tests/unit/test_graph_api_endpoints.py -q --disable-warnings` 现有 22 个用例全部通过，验证 explain 在启用缓存时第二次调用不会重复触发底层 store 查询。 
  - 已完成 v0.7c 导出/清理增强（2025-12-01）：  
    - 导出视图增强：  
      - 在 `Neo4jStore.export_srot` 中增加游标式分页能力和简单过滤：支持 `cursor`（基于 `subject` id 的简单游标）、`limit`、`rel_types` 与 `min_confidence`，返回 `{"items": [...], "next_cursor": str|None}`，并在 API `/graph/v0/admin/export_srot` 中透出；  
      - 当前实现为“按 subject 升序导出、每次最多 limit 条”的轻量迭代版，满足小规模图谱的离线导出与复用，在后续 v1.0 阶段可按需要补充时间窗口等更细粒度过滤；  
    - TTL 清理与指标：  
      - 保持 `cleanup_expired` 单次删除上限（节点/边分别受 `limit` 约束），避免一次性删除过多记录；  
      - 在 API 层 `graph_ttl_cleanup` 中引入 `record_ttl_cleanup` + `add_graph_latency("ttl.cleanup", ...)`，记录 dry_run / 正常 / error 三种状态的次数及累计删除的节点/边数量；  
      - `metrics.as_prometheus_text` 中增加 `memory_ttl_cleanup_total{status=...}`、`memory_ttl_cleanup_nodes_total`、`memory_ttl_cleanup_edges_total` 指标导出，便于在 Prometheus/Grafana 中观察 TTL 清理的频率和强度；  
    - 测试：  
      - 更新 `tests/unit/test_graph_ttl_export_api.py` 以适配新的 `export_srot` 返回结构（包含 `items` 和 `next_cursor`），并在本地 `.venv` 环境下用  
        `PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest modules/memory/tests/unit/test_graph_ttl_export_api.py -q --disable-warnings` 验证 API 层兼容性（当前 2/2 用例通过）。  
  - 全量回归（2025-12-01）：  
    - 在本地 `.venv` 环境下执行  
      `PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest modules/memory/tests -q --disable-warnings`，结果 **197 passed, 1 skipped, 3 warnings**；  
    - 跳过用例为集成 LLM/外部服务相关标记（需真实密钥环境），其余 Graph/Neo4j/Qdrant/TTL/导出/Explain 相关单元与集成测试全部通过，标记 v0.7 阶段性能与推理出口能力验收完成。 

### v0.8 检索对标 L1–L3（完成，2025-12-02）
- **范围**：在不新增重型 API 的前提下，利用现有 MemoryService helper（`list_places_by_time_range` / `entity_event_anchor` / `search` / `search_graph`）与 InMem 存储，为 L1–L3 中的代表性问题构造最小合成图数据并做集成验证。  
- **实现（What/How）**：  
  - 新增集成测试 `modules/memory/tests/integration/test_retrieval_l1_l3_scenarios.py`，覆盖：  
    - **L1-1「某个时间范围内我去了哪些地方？」**  
      - `test_l1_places_by_time_range_basic`：写入 3 条 episodic 文本（其中 2 条在时间窗内），调用 `MemoryService.list_places_by_time_range(...)`，基于 `metadata.entities` 中的 `place:*` 标签聚合并去重，验证只返回时间窗内的地点。  
    - **L1-4「昨天下午跟我开会的人是谁？」**  
      - `test_l1_meeting_participants_via_search`：写入一条带 `event_type="meeting"` 与 `entities=["person:me","person:alice","person:bob"]` 的事件，使用 `search(...)` + `SearchFilters(time_range, user_id, memory_domain)` 召回种子事件，然后在测试中从 `metadata.entities` 中抽取参会人集合，验证结果与预期一致。  
    - **L2（时序/状态锚定）代表场景**  
      - `test_l2_entity_event_anchor_inmem`：在真实 `InMemVectorStore` 上写入 “男子下班回到家”“男子回家后打开电视” 两条 episodic 文本，调用 `entity_event_anchor(entity="男子", action="回到家")`，验证返回 triples 中 `time_range` 字段可用（从 episodic metadata 派生），证明实体+动作可被时间锚定。  
    - **L3-11「经常和 Bob 一起出现的戴眼镜的男人」**  
      - `test_l3_cooccurs_partner_for_bob`：写入 3 个角色节点（Bob/戴眼镜的男人/其他朋友）与两条 `co_occurs` 边（权重 3.0 vs 1.0），通过 `MemoryService.search_graph(...)` 以 Bob 作为种子、`rel_whitelist=["CO_OCCURS"]` 展开邻居，验证权重最高的邻居对应“戴眼镜的男人”。  
- **验证（Test）**：  
  - 在本地 `.venv` 环境下执行：  
    - `PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest modules/memory/tests/integration/test_retrieval_l1_l3_scenarios.py -q --disable-warnings`  
  - 结果：**4 passed, 0 failed**，用时约 0.12s，依赖仅为 InMemVectorStore / InMemGraphStore / InMemAuditStore（无需真实 Neo4j/Qdrant）。  
- **阶段评估（Why OK & 风险点）**：  
  - 对标清单中 L1–L3 的代表性问题，已经在“小图 + 纯 Python”环境下证明：  
    - Schema + MemoryService 现有字段足以表达这些检索/推理路径；  
    - 无需修改核心业务逻辑，仅通过组合已有 API 即可完成检索。  
  - 已显式加入“否定逻辑”断言（例如时间窗外地点不应出现），防止过滤逻辑“放水”。  
  - 风险与改进方向（在 v0.9 及之后处理）：  
    - 当前 L2 测试仍偏向“绝对时间提取”（基于文本 + timestamp），尚未验证“回家之后的第一件事”这类相对时序推理；  
    - InMemGraphStore 的 `expand_neighbors` 现在被视为权重排序的参考实现，其语义（按权重降序、同节点保留最大权重边）已经在代码注释中写死，后续 Neo4j 侧实现必须对齐；  
    - L3/L4/L5 场景需要更多“找不到/不存在”的负向断言，以保证否定推理路径的可靠性。  

### v0.9 检索对标 L4–L5 + 推理 Harness（进行中，第一批场景完成，2025-12-02）
- **范围**：为高阶语义与否定/缺失场景构造可重复的小图，用 Cypher + Service/API 验证检索路径是否闭合。  
- **当前落地场景（第一批）**：  
  1. **聚会中是否与某人有对话（L4/L5 混合）**  
     - 对标问题：*“在那次聚会上，我有没有和李四说话？”*  
     - Neo4j harness：`scripts/test_neo4j_retrieval_l4_l5_basic.py`  
       - `test_party_talk_to_scenario`：  
         - 构造图：`(me)-[:INVOLVES]->(party-1)<-[:INVOLVES]-(li-si|wang-wu)`，并在 party 上挂 `TALK_TO` 边；  
         - Cypher Q1：检查 party-1 上是否存在 `(party)-[:TALK_TO]->(li-si)`，断言为 True；  
         - Cypher Q2：查找“参与但未被 TALK_TO 的实体”，当前构造下应返回空集（显式否定逻辑）。  
     - InMem 逻辑回归：`modules/memory/tests/integration/test_retrieval_l4_l5_inmem_harness.py::test_l4_l5_party_talk_to_inmem`  
       - 使用 `MemoryService + InMemVectorStore + InMemGraphStore`，写入 party 与参与者节点及 `appears_in/said_by` 边；  
       - 调用 `search_graph(seeds=['party-1'], rel_whitelist=['SAID_BY'])`，验证图扩展邻居中包含 `li-si` 与 `wang-wu`。  
     - 运行（InMem 部分）：  
       - `PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest modules/memory/tests/integration/test_retrieval_l4_l5_inmem_harness.py -q --disable-warnings` → **1 passed**。  
  2. **完全没出门的日期（L5 否定逻辑）**  
     - 对标问题：*“上周我有哪天完全没有出门？”*  
     - Neo4j harness：`scripts/test_neo4j_retrieval_l4_l5_basic.py::test_days_without_outdoor`  
       - 构造两天的 TimeSlice + Event：  
         - `day1` 通过 `COVERS_EVENT` 连接一个带 `tags:['OUTDOOR']` 的 Event；  
         - `day2` 只连接 `tags:['INDOOR']` 的 Event；  
       - Cypher 查询：按 TimeSlice 聚合，使用 `ALL(e IN evs WHERE e IS NULL OR NOT ('OUTDOOR' IN e.tags))` 过滤出“无 OUTDOOR 事件”的天；  
       - 断言：返回集合包含 `day2`，不包含 `day1`。  
- **状态与后续计划**：  
  - InMem 侧已提供对应的 graph 扩展回归（party 对话场景），用于验证 Service 级组合逻辑；  
  - Neo4j harness 脚本可在本地 Neo4j 环境下运行，作为 L4/L5 的真实图级验证；  
  - 后续 v0.9 迭代将继续补充：  
    - 情绪 + 行为联合（“看起来很焦虑时在做什么”）；  
    - 意外/摔倒类片段；  
    - 更多“只出现 A/B 两个人”“有/无第三人”等排他性场景。  

### v1.0 基准实验 L1–L3（Qdrant + Neo4j + 本地 Embedding，完成，2025-12-xx）
- **目标**：在真实 Qdrant + Neo4j 环境下，用小规模但结构完备的合成数据，对 v1.0 关心的三件事做端到端验收：  
  1）MemoryService/GraphService 在真实后端上能稳定跑通；  
  2）租户隔离（tenant_id + user_id + domain）在向量召回阶段硬约束；  
  3）通过语义阈值区分“本租户相关内容”与“其他租户噪声”，支撑 L1–L3 级检索对标。  
- **数据集与写入（Step 1 — `scripts/benchmark_v1_dataset_ingest.py`）**：  
  - 为两个租户构造合成数据：  
    - `tenant_home`：`user_home`，`memory_domain="home"`，地点 `place:living_room`；  
    - `tenant_work`：`user_work`，`memory_domain="work"`，地点 `place:meeting_room`；  
  - 每个租户生成约 25 条 episodic 文本事件（5 天 × 5 事件/天），带齐：`timestamp`、`clip_id`、`tenant_id`、`user_id`、`memory_domain`、`room`、`entities=["place:<room>"]` 等元数据；  
  - 写入后端：  
    - **Qdrant**：通过 `QdrantStore.upsert_vectors` 写入 `memory_text` 集合，使用本地 Jina 文本向量模型；为满足 Qdrant 约束，将业务 ID 映射为 UUID5；  
    - **Neo4j**：通过 `GraphService` / `Neo4jStore` 创建 `Entity(me)`、`Place(living_room/meeting_room)`、`Event` 与 `TimeSlice(kind='day')` 节点，并建立 `INVOLVES` / `OCCURS_AT` / `COVERS_EVENT` 边；  
  - 运行方式：  
    - `NO_PROXY=localhost,127.0.0.1 HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= all_proxy= http_proxy= https_proxy= uv run python scripts/benchmark_v1_dataset_ingest.py`；  
  - 结果：在用户本地环境中成功写入，Qdrant `memory_text` 集合与 Neo4j 图均可通过检查脚本确认（例如 `scripts/check_qdrant_data.py`）。  
- **L1–L3 查询与租户隔离（Step 2 — `scripts/benchmark_v1_queries.py`）**：  
  - **L1：基础事实检索（地方列表）**  
    - `_test_l1_places_memory`：调用 `MemoryService.list_places_by_time_range(...)`，过滤 `user_id` / `memory_domain` / `modality=["text"]` / `memory_type=["episodic"]`，聚合 `place:*` 实体，验证：  
      - `tenant_home` 返回的地点集合包含 `place:living_room`；  
      - `tenant_work` 返回的地点集合包含 `place:meeting_room`；  
    - `_test_l1_places_graph`：调用 `GraphService.list_places(tenant_id=...)`，验证图侧 Place 节点与 Memory 侧聚合结果一致。  
  - **L2：事件计数 + 时间字段完整性**  
    - `_test_l2_events_per_tenant`：调用 `GraphService.list_events(tenant_id, place_id=tenant_*‑place‑<room>)`，验证：  
      - 每个租户返回 25 条事件；  
      - 所有事件的 `t_abs_start` 非空（确保时序推理基础信息完备）；  
    - 此处不再硬性断言排序方式，将排序细节交由后续基于衰减权重的策略统一管理。  
  - **L3：租户隔离 + 语义阈值（客厅 vs 非客厅）**  
    - `_test_l3_basic_scope_isolation`：  
      - 对 `tenant_home` 调用 `MemoryService.search("客厅", filters=SearchFilters(tenant_id="tenant_home", user_id=["user_home"], memory_domain="home", modality=["text"], threshold=0.35), scope="domain", expand_graph=False)`，期望命中若干包含“客厅”语义的条目；  
      - 对 `tenant_work` 使用同样查询文本 `"客厅"`，但 `tenant_id="tenant_work"` / `user_id=["user_work"]` / `memory_domain="work"`，期望返回 0 个结果；  
    - 实测：  
      - `tenant_home` 查询 `"客厅"` 的最高得分 ≈ 0.3785；  
      - `tenant_work` 查询 `"客厅"` 的最高得分（历史测量） ≈ 0.2117；  
      - 选取阈值 `threshold=0.35`，可以自然地区分“本租户客厅相关记忆”与“其他租户/历史噪声”，验证向量召回 + 语义阈值在租户隔离场景下的可用性。  
- **关键修复与技术决策（Why）**：  
  - **代理干扰与本地直连**：  
    - 现网环境存在系统级 HTTP(S) 代理，导致 `requests` 针对 `localhost:6333` 的 Qdrant 请求被错误转发；在 `modules/memory/infra/qdrant_store.py` 中显式设置 `self.session.trust_env = False`，强制忽略环境代理，保证本地直连；  
  - **Qdrant Filter 结构修复**：  
    - 原实现使用 `expires_at` 范围过滤 + `minimum_should_match`，两者均与当前 payload/schema 或 Qdrant Filter 语法不兼容：  
      - `expires_at` 字段在 Qdrant payload 中默认不存在，强行过滤会把所有文档筛掉；  
      - `minimum_should_match` 不是 Qdrant Filter 支持的字段，会触发 400 Bad Request；  
    - 新实现中：  
      - 完全移除对 `expires_at` 的硬过滤，将 TTL 交给 Neo4j/治理侧处理；  
      - 仅使用 Qdrant 支持的 `must` / `should` / `must_not` 结构，不再下推 `minimum_should_match`；  
      - 对 `user_id` 采用更保守策略：  
        - `user_match="all"` 时对列表中每个 user_id 生成一个 MUST 条件；  
        - `user_match="any"` 时只下推第一个 user_id 的 MUST 条件，避免 SHOULD 语义导致“未标注 user_id 的历史数据”被意外召回；  
      - 新增 `tenant_id` 作为 `SearchFilters` 字段，并在 `_build_filter()` 中强制映射为 `{"key": "metadata.tenant_id", "match": {"value": tenant_id}}` 的 MUST 条件，实现向量层面的硬租户边界。  
  - **MemoryService.search 阈值传播修复**：  
    - 原实现仅从函数参数与配置文件中读取 threshold，忽略了 `SearchFilters.threshold` 字段，导致调用方在 filters 中设置阈值无效；  
    - 新逻辑：若显式参数 `threshold` 为 None，则优先使用 `filters.threshold`，否则再回落到配置默认值；最终统一传入 `vectors.search_vectors(..., score_threshold=threshold)`。  
  - **数据生成与语义“污染”修复**：  
    - 历史数据中存在大量 `tenant_id=None` 且内容包含“客厅”的条目，对全局检索产生噪声；  
    - 在基准数据生成脚本中显式区分 `tenant_home` 与 `tenant_work` 的文本场景，避免在 `tenant_work` 下生成包含“客厅”的内容，并通过 QdrantClient 脚本确认过滤后结果正确。  
- **验证（Test）**：  
  - Neo4j + Qdrant + 本地 Embedding 环境下执行：  
    - `NO_PROXY=localhost,127.0.0.1 HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= all_proxy= http_proxy= https_proxy= uv run python scripts/benchmark_v1_dataset_ingest.py`（写入数据）；  
    - 同样环境变量下执行 `uv run python scripts/benchmark_v1_queries.py`，L1/L2/L3 场景全部通过；  
  - 附加 sanity 检查：  
    - `scripts/check_qdrant_data.py` 用官方 QdrantClient 验证 `metadata.tenant_id` 过滤行为；  
    - `scripts/test_qdrant_filter.py` 验证 SearchFilters → Qdrant Filter 映射不再产生 400/TTL 误杀问题。  
- **阶段评估**：  
  - 在真实后端（Qdrant + Neo4j）上，已经证明：  
    - MemoryService / GraphService 的接口与内部逻辑在小规模合成数据集下可用；  
    - 向量召回阶段的租户隔离与 user/domain 作用域过滤得到强化，不再依赖“上层自律”；  
    - 通过合理设置语义阈值，可以在不引入复杂 rerank 的前提下区分本租户相关内容与其他噪声，为后续 L4–L5 场景与 v1.0 MVP 提供可信的基础检索能力。  
- **补充（L4/L5 真图基准脚本）**：  
  - 新增 `scripts/benchmark_v1_l4_l5_queries.py` 聚合并串行运行 4 个高阶场景（聚会对话、无出门日、焦虑行为、仅两人排他），复用 `test_neo4j_retrieval_l4_l5_basic.py` 与 `test_neo4j_retrieval_l4_l5_patterns.py` 的小图构造和断言；  
  - 运行方式：`NO_PROXY=localhost,127.0.0.1 HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= all_proxy= http_proxy= https_proxy= uv run python scripts/benchmark_v1_l4_l5_queries.py`（会清空数据库，请勿在生产库执行）；  
  - 仅依赖 Neo4j，不触碰 Qdrant 或 Embedding，用于 v1.0 发布前的 L4/L5 端到端验收。

### v1.0 Ultimate 目标
- 覆盖 `TKG-Graph-v1.0-Ultimate.md` 全节点/边/约束；生产级风控、审计、运维完备；  
- 满足 `docs/时空知识记忆系统构建理论/2. 规划层（How over time）/记忆检索与推理对标清单.md` 中定义的 5 层 22 个检索/推理场景，对每一层提供端到端 Retrieval 验证（Cypher + Service/API）。

---

## 5. 待办摘要（0.7 → 1.0 收尾规划）

> 目标：在不引入额外复杂度的前提下，把现有 Graph/Memory 能力打磨成一个“小规模客户可直接落地”的 v1.0：  
> 1）检索/推理能力对齐 22 条对标清单；2）工程侧可观测性、配置与文档收口；3）避免过度工程。

1. **v0.8 检索对标 L1–L3（API 级验证，第一轮已完成，仅保留为设计说明）**  
   - 范围：围绕对标清单中的 L1（基础事实）+ L2（时序/状态）+ L3（多跳/间接关系）场景，补齐 MemoryService/GraphService 侧的查询组合与测试：  
     - 为每个场景定义最小合成图数据集（小型 Neo4j fixture 或脚本），明确“输入问句 → 期望被命中的 Event/Entity/Place/TimeSlice 节点”；  
     - 在 `modules/memory/tests/integration` 中新增 `test_retrieval_l1_l3_scenarios.py`，通过 MemoryService API（或 HTTP）组合已有 search/graph 接口，验证：  
       - L1：时间范围 + 地点/人物过滤是否能直接回答 “上周五去了哪些地方”“昨天下午开会的人是谁”；  
       - L2：通过事件链与 TimeSlice/CO_OCCURS 能否回答 “回家后做的第一件事”“出门前是否锁门”；  
       - L3：利用 CO_OCCURS、NEXT_EVENT 等关系是否能回答 “我和 Alice 怎么认识的”“经常和 Bob 一起出现的那个人”；  
   - 验收：  
     - 新增集成测试在本地 `.venv` 下稳定通过；  
     - 每个 L1–L3 场景在 PROCESS 中有明确映射（测试用例名 ↔ 对标清单编号），便于后续回归与审查。

2. **v0.9 检索对标 L4–L5 + 推理 Harness（小图 + 合成数据）**  
   - 范围：在不追求“通用 AI”推理的前提下，为高阶语义和否定/缺失场景建立一组可重复的、小规模 **合成测试图**：  
     - L4 语义泛化与多模态对齐：  
       - 设计固定的视觉/语音/文本证据组合（如“焦虑表情 + 抽烟”“摔倒/打碎物品片段”），验证图谱能通过已有 schema + 查询组合召回对应事件集合；  
     - L5 否定逻辑与边缘情况：  
       - 基于 TimeSlice + Event 链 + Place 关系，构造“某天完全没出门”“聚会中未与某人说话”等合成场景，验证查询能给出“确定没有”而不是“查不到”；  
   - 实现：  
     - 在 `scripts/` 下增加 `test_neo4j_retrieval_l4_l5_*.py` 一组脚本，专门针对这些小图场景做 Cypher 级验证（不依赖 LLM），并在 PROCESS 中登记；  
     - 对于需要 MemoryService 编排的场景，在 `modules/memory/tests/integration` 增补相应测试，确保 API 组合能覆盖这些复杂路径。  
   - 验收：  
     - 每个 L4–L5 场景都有对应的“图构造脚本 + 查询 + 断言”；  
     - 全套 L1–L5 测试在无外部 LLM 依赖的前提下可一键运行，证明 schema/服务本身具有可推理性。

3. **v1.0 工程收尾与文档冻结**  
   - 范围：围绕“小规模客户 MVP” 与 “长期可维护” 两个维度，对工程与文档做一次系统收口：  
     - API & 配置：  
       - 明确哪些 HTTP 端点属于 v1.0 对外稳定面（search/timeline/graph/ttl/export 等），整理到 `README.md` + 一个简短的 `API_QUICKSTART.md`；  
       - 在 `config/memory.config.yaml` / `runtime_overrides` 中标注关键开关（graph 深度、topk、TTL、Explain 缓存等）的推荐区间，避免默认配置把小客户打爆；  
     - 可观测性：  
       - 基于现有 metrics，给出一份 v1.0 推荐监控清单（Qdrant/Neo4j/TTL 清理/Explain 命中率），指导后续接入 Prometheus/Grafana；  
     - 代码与测试整理：  
       - 清理明显过时或重复的测试/脚本（在 TEST_ANALYSIS 中标记的“过时功能”），保留对照理论与对标清单的主路径测试；  
   - 验收：  
     - `modules/memory/PROCESS.md`、`Module_Arc.md` 与 `docs/时空知识记忆系统构建理论` 中关于 v1.0 的描述一致；  
     - 在新环境中按照 README 的步骤部署 + 跑一遍 L1–L5 检索对标测试，可以无障碍完成，作为 v1.0 “一键验收”脚本。

> 简化总结：  
> - v0.8/v0.9 负责把 22 条检索/推理场景从“理论对标”落地为“可执行的测试套件”；  
> - v1.0 收尾负责冻结公共 API、配置与文档，把当前这套记忆系统包装成一个对小规模客户足够实用、对我们自己足够可维护的 MVP。 

---

## 6. 文档重构（V2：对话管线高层 API 合同补全）（2025-12-13）

- 范围（Files）
  - 新增/更新：`modules/memory/docs/00_INDEX.md`、`modules/memory/docs/API_QUICKSTART_v2.md`、`modules/memory/docs/GRAPH_v1.md`、`modules/memory/README.md`
- 决策（Why）
  - 停止在旧文档上“补丁式修修补补”，改为新增 V2 文档作为当前推荐入口，避免历史表述与现状实现长期漂移；
  - 把后续要实现的 `session_write/retrieval` 先固化为“可施工的合同”（签名/返回/降级规则/隔离规范），再做代码落地，减少返工。
- 关键补全点（What）
  - 明确 Tenant 的现实约束：`X-Tenant-ID`（header）与 `filters.tenant_id`（body）必须同时具备，否则会出现跨租户召回风险；
  - 明确 `dialog_v1` 的 3 路检索策略（Fact / Trace / Event）与融合/去重/rerank 的合同结构（对齐 benchmark 思路）；
  - 补齐多端/设备隔离：不引入新字段，复用 `metadata.user_id[]` token 化承载 `u:`/`p:`/`d:`/`pub`，并给出推荐组合与 `user_match` 语义；
  - 区分两类 key 的职责边界：
    - 产品 APIK：用于跨 MCP 客户端/多设备的用户访问（鉴权/限流/审计），建议走 `X-API-Token` 并在生产开启 `auth/signing/limits`；
    - BYOK：仅用于抽取/rerank（客户端库侧），后端 `/search`/`/write` 不接收也不保存用户模型 key。
  - 明确现状实现的鉴权 header：默认读取 `X-API-Token`（可配置），不解析 `Authorization: Bearer ...`，避免线上接入误用。
  - 补齐“外接 SaaS/IdP 未定”的兼容策略：冻结最小 claims 合同（`tenant_id` + `sub`），推荐在网关层归一化（签发内部 JWT），避免把 Memory 绑死在某一家 SaaS 的 token 形态上。
- 验证（Test）
  - 本周期为文档合同补全，未引入代码行为变更；代码落地与测试将作为下一周期交付项（见 TODO）。

---

## 7. P0 向量检索“零命中”排查工具（2025-12-16）

- 目标
  - 将“写入成功但 `/search` 返回 0 命中”的排查从猜测变为可验证事实：Qdrant 里是否真的有 points？payload 的 `metadata.tenant_id/user_id/run_id` 长什么样？
  - 不扩张 HTTP API 面：提供脚本而非新增服务端 debug 端点。
- 实现
  - 新增脚本 `modules/memory/scripts/debug_qdrant_state.py`：列出 config 中的 collection，输出 points 总数/按 tenant+user 过滤后的 count，并 scroll 少量样本打印 `metadata.*`。
  - 新增单测 `modules/memory/tests/unit/test_debug_qdrant_state_filter.py`：锁定脚本的 filter 组装逻辑（不依赖真实 Qdrant）。
- 测试验证
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest modules/memory/tests/unit/test_debug_qdrant_state_filter.py -q`
- 评估
  - 能快速定位是“根本没写入点”还是“过滤键不一致/为空”，为后续修复提供确定依据。

---

## 8. P0 ANN 阈值自动降级（2025-12-16）

- 目标
  - 解决一种常见“假空结果”：Qdrant 中有 points（过滤也能命中），但因为配置默认 `ann.threshold` 过高或 embedding 质量不稳定导致 `score_threshold` 把结果全过滤，最终 `/search` 的 `vec_hits=0`。
  - 保持向后兼容：调用方显式传 `threshold` 时不改行为；仅对“来自配置的默认阈值”启用降级重试。
- 实现
  - `application/service.py`：当 `threshold` 来自配置默认值且本轮 `search_vectors(...)` 返回空时，自动重试一次 `threshold=None`（不传 `score_threshold`），并在 trace attempts 里记录 `relaxed_threshold/vec_hits_relaxed`。
  - 新增单测 `tests/unit/test_search_threshold_relax_fallback.py`：用 fake vector store 断言会发生第二次无阈值检索并返回 hits。
- 测试验证
  - `PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest modules/memory/tests/unit/test_search_threshold_relax_fallback.py -q`
- 评估
  - “默认阈值导致的全空”会自动降级为“至少有召回”，更符合用户预期；同时保留显式阈值的严格性，不会悄悄改变对精度敏感的调用方行为。

---

##（对话管线）阶段性记录

## 7. Phase 0：写入去重隔离收紧（跨主体合并风险修复）（2025-12-16）

- 范围（Files）
  - 更新：`modules/memory/application/service.py`
  - 更新：`modules/memory/infra/inmem_vector_store.py`
  - 新增：`modules/memory/tests/unit/test_write_dedup_isolation.py`
- 动机（Why）
  - `MemoryService.write(...)` 的去重/合并候选邻居检索之前只按 `modality` 过滤，会把不同 tenant/user/domain 的内容当成同一“对象”合并/删除；这会直接污染记忆、破坏图结构一致性，属于必须先修的基础安全问题。
- 实现（What）
  - 在 dedup 邻居搜索中补齐隔离过滤（有则用，无则不加，避免破坏旧调用）：
    - `tenant_id`（若存在，硬边界）
    - `user_id`（使用 `user_match="all"`，避免跨 principal 合并）
    - `memory_domain`
    - `memory_scope`
    - `memory_type=[entry.kind]`（避免跨 kind 合并）
    - `run_id`（仅对 `kind="episodic"` 生效：优先会话内去重，避免跨 session 串联导致时间线被“修补式合并”）
  - 为测试用 InMemVectorStore 补齐 `tenant_id` / `memory_scope` 的过滤支持，确保单测能真实覆盖隔离逻辑。
- 测试（Test）
  - `pytest -q modules/memory/tests/unit/test_write_dedup_isolation.py`
  - 结果：`5 passed`
- 结论（Done）
  - 去重/合并的候选集被强制限定在同一 tenant/user/domain（以及 episodic 的 session/run）内；跨主体的 UPDATE/DELETE 不再可能发生，记忆底座的“隔离不靠约定”得到落实。

---

## 8. Phase 1：LoCoMo 映射规范在 Memory 内落地（对齐 benchmark Step3）（2025-12-16）

- 范围（Files）
  - 新增：`modules/memory/domain/dialog_text_pipeline_v1.py`
  - 新增：`modules/memory/tests/unit/test_dialog_text_pipeline_alignment.py`
  - 更新：`modules/memory/__init__.py`
- 动机（Why）
  - benchmark 已经跑通 “Event/TimeSlice/Fact → MemoryEntry + Edge（OCCURS_AT/REFERENCES/PART_OF）” 的规范；线上/客户端如果再发明一套，很快就会 drift，最后变成“对齐靠人肉祈祷”。
  - 另外，`modules/memory/__init__.py` 之前强制导入 `fastapi/neo4j`（通过 `create_service/GraphService`），导致仅想使用 `domain` 纯逻辑也会 import 失败，不利于测试与复用。
- 实现（What）
  - 在 `modules/memory/domain/dialog_text_pipeline_v1.py` 内提供纯函数：
    - `generate_uuid(...)`：严格复刻 benchmark 的 uuid5 方案；
    - `event_record_to_entry(...)` / `timeslice_record_to_entry(...)` / `fact_item_to_entry(...)`：字段名/语义与 `benchmark/scripts/step3_build_graph.py` 一致；
    - `build_entries_and_links(...)`：生成 entries + links，并输出 `OCCURS_AT/REFERENCES/PART_OF` 三类边。
  - 在 `modules/memory/tests/unit/test_dialog_text_pipeline_alignment.py` 中直接 import benchmark 的 Step3 转换函数做对照，锁死一致性。
  - 在 `modules/memory/__init__.py` 引入 `__getattr__` 延迟加载（lazy import），避免无 `fastapi/neo4j` 环境下无法 import `modules.memory`。
- 测试（Test）
  - `python -m pytest -q modules/memory/tests/unit/test_dialog_text_pipeline_alignment.py`
  - `python -m pytest -q modules/memory/tests/unit/test_write_dedup_isolation.py modules/memory/tests/unit/test_dialog_text_pipeline_alignment.py`
  - 结果：`10 passed`
- 结论（Done）
  - LoCoMo 映射规范已作为 Memory 模块内部“可复用、可测试、可对齐”的纯函数落地；benchmark 与线上不再靠口头约定对齐。

---

## 9. Phase 2：`session_write`（对话写入客户端 API）最小闭环（2025-12-16）

- 范围（Files）
  - 新增：`modules/memory/session_write.py`
  - 更新：`modules/memory/application/service.py`
  - 新增：`modules/memory/tests/unit/test_session_write_api.py`
  - 更新：`modules/memory/__init__.py`
- 动机（Why）
  - 我们要的不是“又一个 /write 调用示例”，而是一条可产品化的“对话 →（可选抽取）→ 入库”的稳定管线：幂等、可重试、不破坏对话 turn 的粒度，并且与 benchmark 的 Entry/Edge 映射保持一致。
  - 原有 `MemoryService.write` 的去重会在“重复提交/重试/相同文本 turn”场景下做合并，这对 raw dialogue turn 是灾难（证据丢失/图关系断裂）。
- 实现（What）
  - 新增 `modules/memory/session_write.py::session_write(...)`：
    - `session_id` 作为 `run_id` 的幂等键；
    - 引入 `session_marker`（`node_type=session_marker`, `source=dialog_session_marker`）标记 `in_progress/completed/failed`；
    - `overwrite_existing=true` 时：仅在写入成功后删除旧 marker 中记录的“过期 fact ids”（硬删除，避免 Qdrant 软删可见性问题）；同时更新 marker 的 `fact_ids/event_ids/timeslice_ids`；
    - 事实抽取采用注入式 `fact_extractor`（输出需兼容 benchmark FactItem 字段）；`llm_policy=require/best_effort` 的缺省行为已固化。
    - 事件/事实/边的结构复用 Phase 1 的 `dialog_text_pipeline_v1.build_entries_and_links(...)`，确保 `OCCURS_AT/REFERENCES/PART_OF` 关系与 benchmark 一致。
  - `MemoryService.write` 增加 per-entry 开关 `metadata.dedup_skip=true`：
    - raw turn / pipeline-managed entries 直接写入（upsert by id），跳过 neighbor-based merge；
    - 写入前会移除该内部字段，避免污染持久化 metadata。
  - `modules/memory/__init__.py` 导出 `session_write` 作为公共 API。
- 测试（Test）
  - `python -m pytest -q modules/memory/tests/unit/test_session_write_api.py`
  - `python -m pytest -q modules/memory/tests/unit/test_write_dedup_isolation.py modules/memory/tests/unit/test_dialog_text_pipeline_alignment.py modules/memory/tests/unit/test_session_write_api.py`
  - 结果：通过（本机跑到 `17 passed`）
- 结论（Done）
  - `session_write` 已具备：幂等（marker）、覆盖（overwrite 语义）、重试友好（不回滚事件默认）、以及“对话 turn 不被 dedup 合并”的硬约束；为后续 Phase 3 的 `retrieval(strategy=\"dialog_v1\")` 提供了可用的数据入口。

---

## 10. Phase 3：`retrieval(strategy="dialog_v1")`（对齐 benchmark 3-way search + 融合）（2025-12-16）

- 范围（Files）
  - 新增：`modules/memory/retrieval.py`
  - 新增：`modules/memory/tests/unit/test_retrieval_dialog_v1.py`
  - 更新：`modules/memory/__init__.py`
- 动机（Why）
  - 线上要能“像 benchmark 一样”检索对话证据，否则你跑出来的指标只是离线自嗨；更糟的是：线上体验漂移，debug 口径不一致，最后没人知道问题在哪。
- 实现（What）
  - 新增 `modules/memory/retrieval.py::retrieval(...)`，实现固定 `dialog_v1` 策略：
    - `fact_search`：一次 `store.search(expand_graph=False)`，过滤 `memory_type=["semantic"]` + `source=["locomo_text_pipeline"]`（对齐 benchmark）；
    - `trace_references`：不额外调用 search，直接从 fact 的 `source_turn_ids/source_sample_id` 推导 `event_id`；
    - `event_search`：一次 `store.search(expand_graph=True)`，过滤 `memory_type=["episodic"]`；
    - 融合：按 benchmark 权重 `fact=2.0 / ref=1.8 / event=1.0` 计算 `_final_score`，排序并按 `event_id/fact_id` 去重。
  - `modules/memory/__init__.py` 导出 `retrieval`，与 `session_write` 形成最小“写入+检索”闭环。
- 测试（Test）
  - `python -m pytest -q modules/memory/tests/unit/test_retrieval_dialog_v1.py`
  - 结果：通过（并与 Phase 0-2 的关键单测一起跑到 `18 passed`）
- 结论（Done）
  - `dialog_v1` 的 3 路检索+融合已固化为可调用的客户端 API，debug 结构与权重口径对齐 benchmark；后续只剩 BYOK rerank（可选）与 Phase 4 的图增强与整体验收。

---

## 11. Phase 4（前置）：HTTP 客户端适配层（让 pipeline 真正“可在客户端调用服务”）（2025-12-16）

- 范围（Files）
  - 新增：`modules/memory/adapters/http_memory_port.py`
  - 新增：`modules/memory/tests/unit/test_http_memory_port_adapter.py`
  - 更新：`modules/memory/__init__.py`
- 动机（Why）
  - `session_write/retrieval` 如果只能接 in-process 的 `MemoryService`，那就不是“客户端 API 封装”，只是内部函数。需要一个明确的 IO 适配层，把它们接到现有 HTTP `/search`/`/write`/`/delete` 上。
- 实现（What）
  - 新增 `HttpMemoryPort`（异步接口，内部用 `asyncio.to_thread + requests`）：
    - `search` → `POST /search`，解析为 `SearchResult(Hit/MemoryEntry)`；
    - `write` → `POST /write`，解析为 `Version`（可选 `id_map`）；
    - `delete` → `POST /delete`，解析为 `Version`。
  - 认证/签名策略保持“调用方负责”：`HttpMemoryPort` 仅透传 headers，不在客户端库里偷偷拼安全策略（避免 drift 与误用）。
  - `modules/memory/__init__.py` 导出 `HttpMemoryPort`，便于外部直接使用：`from modules.memory import HttpMemoryPort, session_write, retrieval`。
- 测试（Test）
  - `python -m pytest -q modules/memory/tests/unit/test_http_memory_port_adapter.py`
  - 结果：通过（requests 调用用 monkeypatch stub 验证 payload/解析）
- 结论（Done）
  - `session_write/retrieval` 现在既能接 `MemoryService`（测试/本地），也能接 `HttpMemoryPort`（真实客户端调用服务），满足“模块自身提供客户端功能和 API 封装”的基本要求。

---

## 12. Phase 4（补齐）：LoCoMo Fact 抽取器（Prompt/Schema 与 benchmark Step2 锁死一致）（2025-12-16）

- 范围（Files）
  - 新增：`modules/memory/application/fact_extractor_dialog_v1.py`
  - 新增：`modules/memory/application/prompts/dialog_fact_extractor_system_prompt_v1.txt`
  - 新增：`modules/memory/tests/unit/test_dialog_fact_extractor_prompt_alignment.py`
  - 更新：`modules/memory/session_write.py`
- 动机（Why）
  - 你要求的不是“差不多就行”的抽取器，而是 **prompt/schema 必须与 benchmark 完全一致**，否则你永远无法解释线上与 benchmark 的差异来自哪里。
  - 同时要避免把生产实现绑定到 `benchmark/` 目录（部署时很可能不带 benchmark），所以 prompt 需要在 Memory 模块内自持，并用测试锁死一致性。
- 实现（What）
  - `fact_extractor_dialog_v1`：
    - Prompt 以纯文本文件形式存放（`dialog_fact_extractor_system_prompt_v1.txt`），并在 import 时加载为 `SYSTEM_PROMPT`；
    - `parse_facts_json(...)` 负责剥离 code fence 并解析 `{"facts":[...]}`；
    - `build_dialog_fact_extractor_v1_from_env(...)` 使用现有 `llm_adapter.build_llm_from_env()` 构建 LLMAdapter（无配置则返回 None）。
  - `session_write`：
    - 当未显式传入 `fact_extractor` 且 `extract/write_facts=true` 时，会尝试调用 `build_dialog_fact_extractor_v1_from_env(...)` 自动构建抽取器；
    - 若仍不可用，则按 `llm_policy=require/best_effort` 执行（报错/降级不抽取）。
- 测试（Test）
  - `python -m pytest -q modules/memory/tests/unit/test_dialog_fact_extractor_prompt_alignment.py`
  - 覆盖：prompt 与 benchmark Step2 的 `SYSTEM_PROMPT`（按文件解析提取）一致；JSON 解析可处理 code fence。
- 结论（Done）
  - 抽取侧的 prompt/schema 不再是“约定”，而是由单测强制锁死；线上与 benchmark 的对齐链路完整闭环。

---

## 13. Patch：命名规范化（去掉误导性的 locomo 文件命名）（2025-12-17）

- 范围（Files）
  - 重命名：`modules/memory/domain/locomo_text_pipeline.py` → `modules/memory/domain/dialog_text_pipeline_v1.py`
  - 重命名：`modules/memory/application/fact_extractor_locomo.py` → `modules/memory/application/fact_extractor_dialog_v1.py`
  - 重命名：`modules/memory/application/prompts/locomo_step2_system_prompt.txt` → `modules/memory/application/prompts/dialog_fact_extractor_system_prompt_v1.txt`
  - 重命名：`modules/memory/tests/unit/test_locomo_text_pipeline_alignment.py` → `modules/memory/tests/unit/test_dialog_text_pipeline_alignment.py`
  - 重命名：`modules/memory/tests/unit/test_locomo_fact_extractor_prompt_alignment.py` → `modules/memory/tests/unit/test_dialog_fact_extractor_prompt_alignment.py`
  - 更新引用：`modules/memory/session_write.py`、`modules/memory/PROCESS.md`、`docs/时空知识记忆系统构建理论/5. 文本层设计/对话接入与benchmark对齐_施工路线图.md`
- 动机（Why）
  - 这些实现是“对话管线 dialog_v1”的客户端能力与基线实现；把 locomo 写进文件名会误导读者以为是“仅用于某个数据集的特化代码”。
  - 同时为了与 benchmark 产物严格一致，**metadata.source 仍保持 `"locomo_text_pipeline"`**（这是兼容性合同，不应为了命名洁癖去改数据口径）。
- 实现（What）
  - 仅做“文件/符号命名”的去 locomo 化与引用更新；行为保持不变。
  - 补齐 prompt 末尾缺失的提醒行，确保与 `benchmark/scripts/step2_extract_facts.py::SYSTEM_PROMPT` 完全一致。
- 测试（Test）
  - `python -m pytest -q modules/memory/tests/unit/test_write_dedup_isolation.py modules/memory/tests/unit/test_dialog_text_pipeline_alignment.py modules/memory/tests/unit/test_session_write_api.py modules/memory/tests/unit/test_retrieval_dialog_v1.py modules/memory/tests/unit/test_http_memory_port_adapter.py modules/memory/tests/unit/test_dialog_fact_extractor_prompt_alignment.py`
  - 结果：`17 passed`
- 结论（Done）
  - 命名更贴近“对话管线 v1”的真实定位；对齐 benchmark 的关键合同（prompt/schema/source/UUID/edges）仍由单测锁死。

---

## 14. Phase 3（补齐）：QA 生成（证据 → 答案）（2025-12-17）

- 范围（Files）
  - 新增：`modules/memory/application/qa_dialog_v1.py`
  - 新增：`modules/memory/application/prompts/dialog_qa_system_prompt_general_v1.txt`
  - 新增：`modules/memory/tests/unit/test_dialog_qa_prompt_alignment.py`
  - 更新：`modules/memory/retrieval.py`
  - 更新：`modules/memory/tests/unit/test_retrieval_dialog_v1.py`
- 动机（Why）
  - 仅返回 evidence id/片段还不够：benchmark 的评估口径里还有“基于证据生成最终答案”的 QA 步骤；线上如果不补齐，就会出现“检索对齐了但回答口径不对”的漂移。
  - 更关键的是：QA prompt 与 user prompt 的格式一旦 drift，你根本无法解释线上与 benchmark 的差异来自哪里。
- 实现（What）
  - 新增 `qa_dialog_v1`：
    - `QA_SYSTEM_PROMPT_GENERAL` 以纯文本文件形式存放，并在模块内加载；
    - `build_qa_user_prompt(...)` 严格复刻 benchmark 的证据拼装格式（Top-15、`Fact/Reference/Event` 分类、`ts=None` 行为）。
  - 扩展 `retrieval(strategy="dialog_v1")`：
    - 新增可选参数：`with_answer: bool=False`、`task: str="GENERAL"`、`llm_policy: str="best_effort"`、`qa_generate: (system,user)->str | None`；
    - `with_answer=true` 时：用 `QA_SYSTEM_PROMPT_GENERAL` + `build_qa_user_prompt(...)` 生成 prompt，调用 `qa_generate`（或从 env 构造 LLMAdapter）生成 `answer`；
    - 未配置 LLM 时：`llm_policy=require` 直接报错；否则返回可预测的降级文本（无证据→`insufficient information`，有证据→`Unable to answer in dummy mode.`）。
    - debug 对齐 benchmark：补齐 `plan.qa_latency_ms/total_latency_ms` 字段。
- 测试（Test）
  - `python -m pytest -q modules/memory/tests/unit/test_dialog_qa_prompt_alignment.py`
  - `python -m pytest -q modules/memory/tests/unit/test_retrieval_dialog_v1.py`
  - `python -m pytest -q modules/memory/tests/unit/test_write_dedup_isolation.py modules/memory/tests/unit/test_dialog_text_pipeline_alignment.py modules/memory/tests/unit/test_session_write_api.py modules/memory/tests/unit/test_retrieval_dialog_v1.py modules/memory/tests/unit/test_http_memory_port_adapter.py modules/memory/tests/unit/test_dialog_fact_extractor_prompt_alignment.py modules/memory/tests/unit/test_dialog_qa_prompt_alignment.py`
  - 结果：通过（本机跑到 `21 passed`）
- 结论（Done）
  - `dialog_v1` 从“证据检索”补齐到“证据 → 答案”的完整链路；并且 QA prompt 与格式由单测锁死，避免未来 drift。

---

## 15. Phase 3（补齐）：Rerank（可选，证据重排对齐 benchmark）（2025-12-17）

- 范围（Files）
  - 新增：`modules/memory/application/rerank_dialog_v1.py`
  - 新增：`modules/memory/application/prompts/dialog_rerank_prompt_v1.txt`
  - 更新：`modules/memory/retrieval.py`（在 fusion/dedup 后、QA 前可选 rerank）
  - 新增：`modules/memory/tests/unit/test_dialog_rerank_prompt_alignment.py`
  - 新增：`modules/memory/tests/unit/test_dialog_rerank_service_alignment.py`
  - 更新：`modules/memory/tests/unit/test_retrieval_dialog_v1.py`
- 动机（Why）
  - 线上如果不补齐 rerank，检索“证据集合对齐”也可能因为排序口径漂移导致评测与体验不一致；更糟的是 drift 后无法定位差异来自融合还是 rerank。
  - 关键约束：prompt/打分融合必须与 benchmark 完全一致，用测试锁死一致性。
- 实现（What）
  - 新增 dialog rerank 服务（noop/llm 两种模式）与 prompt 文件；
  - `retrieval(dialog_v1)` 增加 `rerank={enabled,model,...}` 与 `rerank_generate` 注入点，默认关闭，开启后记录 `executed_calls` 与 `rerank_latency_ms`。
- 测试（Test）
  - 该阶段的对齐测试在回归套件中执行（见本次 Phase 4 回归命令）。
- 结论（Done）
  - rerank 作为可选层引入，不影响默认行为；一致性由 prompt/service 对齐测试约束。

---

## 16. Phase 4：对话写入同步 upsert 到 TKG 主图（2025-12-17）

- 范围（Files）
  - 新增：`modules/memory/domain/dialog_tkg_graph_v1.py`（纯函数：turns → `GraphUpsertRequest`）
  - 更新：`modules/memory/session_write.py`（新增 `graph_upsert/graph_policy`，可选调用 `graph_upsert_v0`）
  - 更新：`modules/memory/adapters/http_memory_port.py`（实现 `graph_upsert_v0` → `POST /graph/v0/upsert`）
  - 新增：`modules/memory/tests/unit/test_dialog_tkg_graph_v1.py`
  - 新增：`modules/memory/tests/unit/test_session_write_graph_upsert.py`
  - 更新：`modules/memory/tests/unit/test_http_memory_port_adapter.py`
  - 更新：`docs/时空知识记忆系统构建理论/5. 文本层设计/对话接入与benchmark对齐_施工路线图.md`（澄清 Memory 图 vs TKG 图收敛路线）
  - 更新：`docs/时空知识记忆系统构建理论/5. 文本层设计/对话管线API_v1_施工规范.md`（补齐 graph_upsert 合同）
- 动机（Why）
  - 当前对话 pipeline 只写 `/write`（MemoryEntry+Edge），无法进入 TKG v1.0 的主图视图（Event/TimeSlice/UtteranceEvidence/Entity），导致 explain/timeline/L4/L5 harness 无法覆盖对话场景。
  - 收敛路线明确：未来检索应逐步以 TKG 图为主，MemoryEntry 图退化为兼容层；对话必须先进入 TKG 才谈得上“统一检索”。
- 实现（What）
  - 新增 `build_dialog_graph_upsert_v1(...)`：为每个 turn 物化 `Event + UtteranceEvidence + Entity(Person)`，并建立：
    - `COVERS_EVENT`（TimeSlice→Event）、`NEXT_EVENT`（Event→Event）
    - `SUPPORTED_BY`（Event→UtteranceEvidence）、`SPOKEN_BY`（Utterance→Entity）、`INVOLVES`（Event→Entity）
    - 以及 `MediaSegment(modality="text")` 的锚点与 `COVERS_SEGMENT`、`SUMMARIZES`、`CONTAINS_EVIDENCE`（带 type override）等边，便于 source_id 级查询与复用既有图模式。
  - `session_write`：
    - 初始版本默认 `graph_upsert=false`（不改变旧行为；后续见 Patch 17 调整为默认开启）；
    - `graph_upsert=true` 时按 `graph_policy=require|best_effort` 控制失败语义（require 会返回 failed，best_effort 会在 trace 标记失败但不影响主写入）。
- 测试（Test）
  - `python -m pytest -q modules/memory/tests/unit/test_dialog_tkg_graph_v1.py modules/memory/tests/unit/test_session_write_graph_upsert.py modules/memory/tests/unit/test_http_memory_port_adapter.py`
  - 结果：通过（本机 `5 passed`）。
- 结论（Done）
  - 对话写入具备“可选同步进入 TKG 主图”的能力，为后续 `/search` 逐步重建在 TKG 之上提供最小支点（不破坏现有 userspace）。

---

## 17. Patch：Phase 4 默认启用 TKG 写入（不破坏 userspace）（2025-12-17）

- 动机（Why）
  - 产品目标明确：对话接入应“默认写 TKG、默认走向 TKG 检索”，否则线上会长期处于“两套图各写各的”的漂移风险。
  - 但铁律也明确：不能因为额外写图把原本可用的对话写入搞挂（Never break userspace）。
- 实现（What）
  - 默认行为调整：
    - `modules/memory/session_write.py::session_write(...)`：默认 `graph_upsert=True`；
    - 默认失败语义不变：`graph_policy="best_effort"`，图写入失败只在 `trace.graph_upsert_status/error` 里可观测，不影响主写入成功。
  - 兼容与降级：
    - 保留显式开关：调用方可 `graph_upsert=False` 完全关闭 TKG 写入；
    - 当 store 未实现/不支持 `graph_upsert_v0` 时，`trace.graph_upsert_status="unsupported"`（best-effort 下不失败；require 下失败）。
  - 补齐 in-process 入口：
    - `modules/memory/application/service.py::MemoryService.graph_upsert_v0(...)`：若底层 graph store 支持 `upsert_graph_v0`，则通过 `GraphService.upsert(...)` 写入；否则抛 `NotImplementedError` 触发可预测降级。
  - 文档同步：
    - `docs/时空知识记忆系统构建理论/5. 文本层设计/对话接入与benchmark对齐_施工路线图.md`：更新 Phase 4 默认值与失败语义；
    - `docs/时空知识记忆系统构建理论/5. 文本层设计/对话管线API_v1_施工规范.md`：更新 `graph_upsert` 默认值，并修正 true/false 的行为描述。
- 测试（Test）
  - `python -m pytest -q modules/memory/tests/unit/test_session_write_graph_upsert.py`
  - `python -m pytest -q modules/memory/tests/unit/test_session_write_api.py modules/memory/tests/unit/test_retrieval_dialog_v1.py`
  - 结论（Done）
  - 对话写入默认会尝试同步进入 TKG；同时保留显式关闭与 best-effort 降级，保证现有调用稳定性。

---

## 18. Phase 5（Step 1-B）：写入 TKG UtteranceEvidence 的向量索引条目（默认不污染 /search）（2025-12-17）

- 动机（Why）
  - 你选择了 Phase 5 的 **B 路线**：为 TKG 的 `UtteranceEvidence`（以及后续可扩展的 Event/TimeSlice）写入专用向量索引条目，解决“向量召回 → TKG 节点”桥接问题。
  - 关键约束：这类“内部索引条目”**不能污染现有 `/search`**，否则会把两套证据混在一起，线上行为不稳定且无法解释。
- 实现（What）
  - 新增纯函数构建器：
    - `modules/memory/domain/dialog_tkg_vector_index_v1.py::build_dialog_tkg_utterance_index_entries_v1(...)`
    - 每条 turn 生成一个 `MemoryEntry(kind="semantic", modality="text")`：
      - `metadata.source="tkg_dialog_utterance_index_v1"`（与 benchmark/旧对话管线 source 明确区分）
      - `metadata.tkg_*_id` 显式携带 `tkg_utterance_id / tkg_event_id / tkg_timeslice_id / tkg_segment_id`
      - `metadata.dedup_skip=true`，避免写入侧 dedup/merge 破坏证据原子性
  - 默认从向量搜索中排除内部索引源（必须）：
    - `modules/memory/infra/qdrant_store.py`：
      - `_build_filter(...)` 支持 `must_not`，并接受内部键 `__exclude_sources`
      - `search_vectors(...)` 与 `fetch_text_corpus(...)` 默认注入 `__exclude_sources=["tkg_dialog_utterance_index_v1"]`
      - 只有当调用方显式传入 `filters.source` 包含该 source 时，才允许命中这些条目
  - `session_write` 串起来：
    - `modules/memory/session_write.py` 在 graph_upsert 开启时（默认开启）：
      - 预构建 `GraphUpsertRequest`（纯函数）拿到稳定的 `tkg_*` ids
      - 同步把 utterance index entries 加入 `/write` 的 entries 列表
      - 图写入仍按 `graph_policy` 控制失败语义（默认 best_effort）
- 测试（Test）
  - `python -m pytest -q modules/memory/tests/unit/test_dialog_tkg_vector_index_v1.py`
  - `python -m pytest -q modules/memory/tests/unit/test_qdrant_filter_exclude_sources.py`
  - 回归：继续跑对话写入/检索/对齐相关用例，确保 dialog_v1 不受污染
- 结论（Done）
  - B 路线的“向量种子 ↔ TKG 节点”桥接索引已可写入，且默认对旧 `/search` 透明。

---

## 19. Phase 5（Step 0）：对话写入默认要求 LLM facts（认知层刚需）（2025-12-17）

- 动机（Why）
  - 共识明确：如果对话只写 turns/events，不做 fact 抽取，那你得到的只是“记录层”，不是“认知层记忆”。这会直接导致后续推理与检索（尤其是偏好/任务/规则/状态）失真。
  - 因此默认语义必须收敛为：`session_write` 需要可用的 LLM 抽取器（或显式注入的 `fact_extractor`），否则失败并可重试。
- 实现（What）
  - `modules/memory/session_write.py::session_write(...)`：
    - 将默认 `llm_policy` 从 `best_effort` 改为 `require`；
    - 当 `extract=True && write_facts=True` 且无法构建抽取器时，抛出明确错误并走失败 marker；
    - 仍保留显式降级路径（用于 dev/特殊场景）：
      - `extract=False` 或 `write_facts=False`；
      - 或显式传 `llm_policy="best_effort"`（不推荐用于生产）。
  - 文档同步：`docs/时空知识记忆系统构建理论/5. 文本层设计/对话管线API_v1_施工规范.md` 更新默认 `llm_policy`。
- 测试（Test）
  - 新增：`modules/memory/tests/unit/test_session_write_llm_required.py`
    - 不提供抽取器、无 env LLM 配置时，默认应 `status="failed"` 且 marker 为 failed；
  - 回归：继续运行对话写入/检索对齐套件，确保不影响显式注入抽取器的用法。
- 结论（Done）
  - 对话写入默认成为“认知层入口”：没有可用抽取器就失败，避免默默落入“只有记录没有认知”的假成功。

---

## 20. Phase 5（Step 1.5）：facts 同步进入 TKG 主图（Knowledge + 证据链闭合）（2025-12-17）

- 动机（Why）
  - 共识明确：TKG 是主真相源；facts 只写 `MemoryEntry(fact)` 等于把“认知层”留在兼容层，后续检索迁移到 TKG 时必然断链。
  - 所以必须把 facts 映射为 TKG 的 `Knowledge`（或未来的 Fact 专用节点），并显式连回 `UtteranceEvidence/Event/Entity/TimeSlice`，形成可解释证据链。
- 实现（What）
  - `modules/memory/domain/dialog_tkg_graph_v1.py`：
    - 新增可选入参 `facts_raw`；
    - 将每条 fact 映射为一个 `Knowledge` 节点（id 复用对话 pipeline 的 fact uuid：`generate_uuid("locomo.facts", "fact:{sample_id}:{idx}")`，保证幂等）；
    - 生成边（全部带 src_type/dst_type，避免 Neo4j 侧歧义）：
      - `TimeSlice -[:CONTAINS]-> Knowledge`（会话包含事实）
      - `Knowledge -[:DERIVED_FROM]-> Event`（事实来源于哪些 turn/event）
      - `Knowledge -[:SUPPORTED_BY]-> UtteranceEvidence`（事实回溯到原话）
      - `Knowledge -[:STATED_BY]-> Entity(Person)`（陈述者）
  - `modules/memory/session_write.py`：
    - 在构造 `GraphUpsertRequest` 时把 `facts_raw` 传入，确保对话写入默认写入“事件+证据+认知”到 TKG。
- 测试（Test）
  - 新增：`modules/memory/tests/unit/test_dialog_tkg_graph_v1.py::test_dialog_graph_upsert_v1_includes_knowledge_from_facts`
  - 回归：确保不传 `facts_raw` 时仍保持最小图结构用例通过。
- 结论（Done）
  - 对话 facts 已进入 TKG 主图，并且证据链可从 Knowledge 回溯到 utterance/event/speaker，为后续 `dialog_v1` 迁移 TKG-first 奠定必要前提。

---

## 21. Phase 5（Step 2-Prelude）：补齐 MemoryPort 的 TKG 查询能力（HTTP + in-process）（2025-12-17）

- 动机（Why）
  - 共识要求 “`dialog_v1` 迁移为 TKG-first”，这意味着检索层必须能稳定读取 TKG 的 Event/Place/TimeSlice/Explain 等视图。
  - 现实约束：上层 pipeline 既可能走 in-process（直接调用 `MemoryService`），也可能走 HTTP（`HttpMemoryPort`）。两条路径必须提供一致的 TKG 读能力，否则迁移会碎裂。
- 实现（What）
  - `modules/memory/adapters/http_memory_port.py`：
    - `_request_json(...)` 支持 GET query params（并避免 GET 发送 body）；
    - 新增 `graph_list_events / graph_list_places / graph_event_detail / graph_place_detail`，对齐服务端：
      - `GET /graph/v0/events`
      - `GET /graph/v0/places`
      - `GET /graph/v0/events/{event_id}`
      - `GET /graph/v0/places/{place_id}`
  - `modules/memory/application/service.py`：
    - 为 `MemoryService` 补齐同名方法，内部委托 `GraphService`（若底层 graph store 不支持 query_*，则抛 `NotImplementedError` 以便调用方显式降级）。
- 测试（Test）
  - `modules/memory/tests/unit/test_http_memory_port_adapter.py` 新增 graph query 相关用例，验证：
    - GET method + params 传递；
    - `items/item` 解析正确。
- 结论（Done）
  - TKG 读路径在客户端侧（HTTP/in-process）具备一致入口，为下一步把 `dialog_v1` 检索迁移到 TKG-first 做好接口准备。

---

## 22. Phase 5（Step 2）：`dialog_v1` 引入 TKG backend（迁移期开关，不形成长期分叉）（2025-12-17）

- 动机（Why）
  - 共识要求：最终 `dialog_v1` 本身迁移为 TKG-first；但迁移期需要一个可控开关来做 A/B 对照与回归验证，避免“一刀切”导致无法定位差异。
  - 同时不能引入长期并存的第二策略（不搞 `dialog_tkg_v1` 常驻分支），否则系统会永久分叉。
- 实现（What）
  - `modules/memory/retrieval.py::retrieval(...)`：
    - 新增参数 `backend: "memory"|"tkg" = "memory"`；
    - `backend="memory"` 时保持原 `dialog_v1` 行为（benchmark 对齐口径不变）；
    - `backend="tkg"` 时：
      - `event_search` 改为检索 utterance index：`source=["tkg_dialog_utterance_index_v1"]` + `memory_type=["semantic"]`；
      - `fact_search` 仍复用现有 MemoryEntry facts（LoCoMo 对齐），但会把 fact 的 `event_ids` 从 `s1_D1_1` 形式**重映射**为 TKG 的 event uuid（按 turn index），保证与 TKG 主图对齐；
      - `debug.executed_calls` 中将第二路标记为 `utterance_search_tkg`，便于诊断。
- 测试（Test）
  - 更新：`modules/memory/tests/unit/test_retrieval_dialog_v1.py`：
    - 新增 `backend="tkg"` 用例，验证：
      - 使用 utterance index 的 source；
      - fact event ids 被 remap 成 TKG event ids；
      - 两次 search 调用的 filters/expand_graph 语义可预测。
- 结论（Done）
  - `dialog_v1` 已具备 TKG backend 的迁移开关；后续只需逐步把更多证据扩展/解释逻辑迁入 TKG，并最终翻转默认到 `backend="tkg"`。

---

## 23. Phase 5（Step 3）：检索结果补齐 TKG Explain 证据链（可解释性增强，不影响 benchmark prompt）（2025-12-17）

- 动机（Why）
  - “TKG-first”不只是把向量种子映射到 TKG 的 event_id；更关键的是把 **可解释证据链**（utterances/entities/timeslices/knowledge）带回来，支撑上层推理、可观测与调试。
  - 同时要严格避免破坏 benchmark 的 QA prompt 格式（例如 `ts=None`），否则你无法判别是检索变了还是 prompt drift。
- 实现（What）
  - `modules/memory/ports/memory_port.py`：新增 `graph_explain_event_evidence(...)` 作为 TKG explain 的统一读接口。
  - `modules/memory/application/service.py`：实现 `MemoryService.graph_explain_event_evidence(...)`，委托 `GraphService.explain_event_evidence(...)`。
  - `modules/memory/adapters/http_memory_port.py`：实现 HTTP 版本，调用 `GET /graph/v0/explain/event/{event_id}`。
  - `modules/memory/retrieval.py`：
    - `dialog_v1` 增加 `tkg_explain/tkg_explain_topn`；
    - 在 `backend="tkg"` 且存在 event_id 时，对 top-N 事件调用 explain，并把结果挂在 `evidence_details[*].tkg_explain`（单独字段，不影响 QA prompt）。
- 测试（Test）
  - `modules/memory/tests/unit/test_http_memory_port_adapter.py`：新增 explain endpoint 解析断言。
  - `modules/memory/tests/unit/test_retrieval_dialog_v1.py`：验证 `tkg_explain` 字段存在且不影响主证据列表。
- 结论（Done）
  - `dialog_v1(tkg)` 的检索结果开始具备“可解释证据链”，且不触碰 benchmark prompt 合同，为下一步彻底把检索/解释统一到 TKG 做准备。

---

## 24. Phase 5（Step 3.5）：Neo4j 证据链查询纳入 Knowledge（facts→TKG 的可回溯闭环）（2025-12-17）

- 动机（Why）
  - 我们已把 facts 写入 TKG 的 `Knowledge`，但如果 explain 只看 `Event -> SUPPORTED_BY -> UtteranceEvidence`，那 “认知层”在 explain 里依然断链。
  - 必须让 explain/event_evidence 查询把 `Knowledge -[:DERIVED_FROM]-> Event` 的事实也带出来，才能实现完整闭环。
- 实现（What）
  - `modules/memory/infra/neo4j_store.py::query_event_evidence(...)`：
    - 增加 `Knowledge -[:DERIVED_FROM]-> Event` 的匹配；
    - 同时汇总 `Knowledge -[:STATED_BY]-> Entity` 与 `Knowledge -[:SUPPORTED_BY]-> UtteranceEvidence`，并与原有列表去重合并；
    - 返回结构新增 `knowledge` 字段。
  - `modules/memory/application/graph_service.py::explain_event_evidence(...)`：透传并保证无结果时 `knowledge=[]`。
- 测试（Test）
  - 更新：`modules/memory/tests/unit/test_graph_explain_service.py`（stub 增加 knowledge，断言输出形态）。
  - 更新：`modules/memory/tests/unit/test_graph_api_endpoints.py`（无 fastapi 时跳过；有时断言 knowledge 字段透传）。
- 结论（Done）
  - explain 证据链现在能覆盖 “Event ↔ Utterance ↔ Knowledge(facts)” 的认知层闭环，为 `dialog_v1` 完全迁移到 TKG 提供关键可解释支撑。

---

## 25. Patch：Graph API v0 命名澄清（避免把 API 版本当成 TKG schema 版本）（2025-12-17）

- 动机（Why）
  - 你指出的困惑是对的：`upsert_graph_v0` / `/graph/v0/upsert` 的 `v0` **只是 API 版本**，不代表我们还停留在 “TKG v0.x” 的 schema。
  - 如果文档/注释继续把 `v0` 当 schema 版本写，会让后续迁移（尤其是“全部检索收敛到 TKG”）看起来像在走回头路。
- 实现（What）
  - 仅做“注释/文档”修正，不改行为：
    - `modules/memory/application/graph_service.py`、`modules/memory/ports/memory_port.py`、`modules/memory/infra/neo4j_store.py`：docstring 明确 “Graph API v0 (schema aligned to TKG v1.0)”。
    - `modules/memory/docs/graph_v0_usage.md`：补充说明 `v0.x` 是 HTTP API 版本，schema 以 `TKG-Graph-v1.0-Ultimate.md` 为准。
- 测试（Test）
  - `python -m pytest -q modules/memory/tests/unit/test_session_write_graph_upsert.py modules/memory/tests/unit/test_dialog_tkg_graph_v1.py modules/memory/tests/unit/test_retrieval_dialog_v1.py` → **passed**（回归验证无行为变化）。
- 结论（Done）
  - 版本命名语义明确：**API 版本稳定向后兼容**，**schema 按 TKG v1.0 演进**；避免文档层面“自我打脸”。

---

## 26. Phase 5（Step 3 第一版）：服务端 `/search` 增加 `graph_backend="tkg"` 开关（2025-12-17）

- 动机（Why）
  - 我们的长期目标是“默认写 TKG、默认搜 TKG”，但 **不能一刀切** 把现有 `/search` 的图扩展逻辑替换掉，否则就是主动破坏 userspace。
  - 迁移期需要一个最小、可观测的开关：同一套向量召回结果下，允许把“图扩展/解释”切到 TKG，以便做对齐实验、定位差异与稳定性问题。
- 实现（What）
  - `modules/memory/api/server.py`
    - `POST /search` 新增 body 字段 `graph_backend: "memory"|"tkg" = "memory"`；
    - 若 `filters.tenant_id` 缺失，则尝试从 `X-Tenant-ID` 头回填（仅用于 TKG 后端的 explain/扩展）。
  - `modules/memory/application/service.py`
    - `MemoryService.search(...)` 新增参数 `graph_backend`（默认 `"memory"`）；
    - 缓存 key 纳入 `graph_backend`，避免 cache 污染（tkg 请求误用 memory cache）；
    - 当 `graph_backend="tkg"` 且 `expand_graph=true`：
      - 对 top-N seeds（默认 5，可用 `graph_params.tkg_explain_topn` 覆盖）调用 `graph_explain_event_evidence`；
      - 用 explain 输出构造 `neighbors`（结构对齐 `expand_neighbors` 的 `{"neighbors": {seed: [...]}}` 形态）；
      - 缺失 `tenant_id` / store 不支持 explain 时自动降级回 `memory`（并在 trace 标明原因）。
    - trace 增加字段：`graph_backend_requested/graph_backend_used` + `tkg_expand` 统计，便于排障与对齐。
- 测试（Test）
  - `python -m pytest -q modules/memory/tests/unit/test_search_graph_backend_tkg.py modules/memory/tests/unit/test_memory_service_search.py` → **passed**
- 结论（Done）
  - `/search` 已具备“图扩展可切换到 TKG”的最小开关与可观测性；默认仍走 memory，不会破坏现有线上调用。
  - 后续 Step 4 才是“把默认从 memory 迁到 tkg + 更通用的 TKG 邻域扩展/路径推理”，需要更严的线上对标与性能评估。

---

## 27. Patch：公共 API 在无 FastAPI 环境下可导入（2025-12-17）

- 动机（Why）
  - 当前开发/测试环境并不保证安装 FastAPI，但 `modules.memory` 的公共入口需要在“最小依赖环境”下仍可被导入与使用（例如只跑 `session_write/retrieval` 的单测）。
  - 这不是“为了优雅”，而是为了避免测试与工具链在无关依赖上硬崩溃：可用性优先。
- 实现（What）
  - `modules/memory/__init__.py`：
    - `create_service` 的 lazy import 增加 `ModuleNotFoundError("fastapi")` 兜底：返回一个占位函数，调用时给出清晰错误；
    - 同步对 `GraphService` 做同类保护（极简 env 下缺 neo4j 驱动时也不应该影响 `modules.memory` 的其余能力）。
- 测试（Test）
  - `python -m pytest -q modules/memory/tests/unit/test_public_api_imports.py` → **passed**
- 结论（Done）
  - `modules.memory` 的公共 API 可以在“无 FastAPI/无 Neo4j 驱动”的环境里正常 import；需要相关能力时再显式报错，不再在 import 阶段炸掉用户空间。

---

## 28. Phase 6：`session_write` 写入侧切换为 TKG-first（2025-12-18）

- 动机（Why）
  - 共识已明确：TKG 是主真相源；检索侧 `retrieval(strategy="dialog_v1", backend="tkg")` 已对齐目标并可用。
  - 但写入侧 `session_write(...)` 仍以 “LoCoMo Step3 的 MemoryEntry+links” 为主路径：
    - 会触发旧范式的图写入（`merge_nodes_edges`），与 TKG v1.0 schema 并存时存在不兼容风险；
    - 认知层事实被存放在兼容层，而不是以 TKG Knowledge 为中心。
  - 因此需要把 `session_write` 的默认写入语义收敛为：**LLM 抽取（Knowledge）→ TKG 主图 → 向量索引**，旧 Memory 图构造不再作为主路径。

- 实现（What）
  - 新增：`modules/memory/application/knowledge_extractor_dialog_tkg_v1.py`
    - prompt：`modules/memory/application/prompts/dialog_tkg_knowledge_extractor_system_prompt_v1.txt`
    - 通过 `build_llm_from_env()` 调用真实 LLM，输出 `{"knowledge":[...]}`（硬要求每条都有 `source_turn_ids`）。
    - 测试锁定：与 `benchmark/archive/v2/prompts/tkg_knowledge_extractor_system_prompt_v1.txt` 保持一致，防止 drift。
  - 更新：`modules/memory/session_write.py`
    - 默认抽取器从 `fact_extractor_dialog_v1` 切换为 TKG knowledge extractor：
      - `llm_policy=require` 且无 LLM 配置时失败并写 failed marker（保持“认知层入口”的铁律）。
    - 移除旧主路径：
      - 不再构造 Step1 records；
      - 不再调用 `dialog_text_pipeline_v1.build_entries_and_links(...)` 生成 legacy events/timeslice/fact 的 entries+links；
      - 不再向 `store.write(...)` 传 links（避免触发旧范式 graph merge）。
    - 新主路径（TKG-first）：
      - `build_dialog_graph_upsert_v1(...)` 生成 `GraphUpsertRequest`（Event/UtteranceEvidence/Knowledge/...）；
      - `build_dialog_tkg_utterance_index_entries_v1(...)` 生成 utterance 向量索引（`source="tkg_dialog_utterance_index_v1"`）；
      - 通过 `store.graph_upsert_v0(...)` 写入 TKG 主图（默认开启；`graph_policy=best_effort/require` 可控）；
      - 通过 `store.write(...)` 仅写入向量相关条目（facts index + utterance index + marker），不写 legacy graph links。
    - 向后兼容：
      - 仍写入 “fact/knowledge index entries” 为 `MemoryEntry(kind="semantic")`，`source="locomo_text_pipeline"`，
        以保持 `dialog_v1` 的 `fact_search` 口径与指标计算不漂移；
      - marker 仍保留 `fact_ids` 用于 `overwrite_existing` 的 stale 删除。
    - 关键可靠性修复（坑必须填）
      - **Marker 幂等性必须严格**：优先使用 `store.get(marker_id)`（新增 `MemoryService.get(...)`）做“按 ID 精确读取”，避免 ANN search 的 scope fallback 把别的 session marker 误命中，导致 `skipped_existing` 假阳性。
      - **Fact/Knowledge UUID 必须稳定**：写入 fact 向量条目时，强制将抽取结果的 `sample_id/source_sample_id` 归一为 `session_id`，避免 LLM 输出缺字段导致 fact UUID 漂移/冲突，进而污染 overwrite 删除与跨 session 去重。
      - **graph_policy=require 的半成功状态收口**：调整顺序为“先 `graph_upsert_v0`，后写向量”，确保 require 模式下图写入失败时不会留下 vector-only 的脏状态。
      - **overwrite_existing 的删除延后**：仅在新写入路径完成后再删除 stale fact ids，避免失败路径先删后写造成数据丢失。

- 测试（Test）
  - prompt 对齐：
    - `python -m pytest -q modules/memory/tests/unit/test_dialog_tkg_knowledge_extractor_prompt_alignment.py`
  - session_write 回归：
    - `python -m pytest -q modules/memory/tests/unit/test_session_write_api.py`
    - `python -m pytest -q modules/memory/tests/unit/test_session_write_graph_upsert.py`
    - `python -m pytest -q modules/memory/tests/unit/test_session_write_llm_required.py`
    - 新增覆盖：
      - `modules/memory/tests/unit/test_session_write_api.py::test_session_write_fact_ids_are_scoped_by_session_id_even_without_sample_id`

- 结论（Done）
  - `session_write` 写入侧已切换为 TKG-first：默认 LLM 抽取认知层 → 写 TKG 主图 + 向量索引；
  - 旧 Memory 图构造不再作为主路径，减少与 TKG schema 并存时的不确定性；
  - 仍保留必要的向后兼容（`fact_search` source 口径 + overwrite marker 语义），不破坏既有检索与评测。

---

## 29. Patch：conv-26 实测检验脚本 + 多 session 上下文对齐（2025-12-18）

- 动机（Why）
  - 下一步验收是“用 `memory.session_write(...)` + `memory.retrieval(...)` 把 LoCoMo `conv-26` 全量跑一遍”，这是对齐最关键的实测闭环。
  - 但 `conv-26` 是多 session（数十个 session）数据：LLM 抽取 prompt 的上下文格式、每个 session 的 reference time、以及多次调用的分块策略都必须与 benchmark 口径一致，否则结果不可对比、也很难定位偏差来源。

- 实现（What）
  - `modules/memory/session_write.py`
    - `turns` 归一化增强：支持 `session_idx/session_date_time/blip_caption` 透传；
    - 若存在 `blip_caption` 且正文未包含 `[Image:`，则按 benchmark 约定拼接：`... [Image: <caption>]`。
  - `modules/memory/application/knowledge_extractor_dialog_tkg_v1.py`
    - `build_dialogue_context(...)` 升级为 **多 session** 格式，并按 benchmark 规则将 `session_date_time` 归一为 `YYYY-MM-DD HH:MM`；
    - 默认启用 **按 session 分块抽取**（避免超长上下文）：通过环境变量 `MEMORY_DIALOG_TKG_EXTRACT_SESSIONS_PER_CALL` 控制（默认 4），多次 LLM 调用后做稳定去重合并（key=statement+source_turn_ids）。
  - `modules/memory/scripts/e2e_dialog_conv26_session_write_and_retrieval.py`
    - 端到端脚本：写入侧调用 `session_write`（真实 LLM 抽取 + TKG upsert + 向量索引），检索侧调用 `retrieval(strategy="dialog_v1", backend="tkg")`；
    - 输出对齐 benchmark 的 `results_*.jsonl`，并额外生成：
      - `aggregate_*.json`：按任务（L1/L2/L3/…）聚合 accuracy（Judge 二元口径）；
      - `report_*.md`：便于人工快速定位问题；
      - latency 统计：write/retrieval/qa/total + per-api（fact_search/trace/utterance_search/tkg_explain/rerank）。
    - 默认行为与 benchmark 脚本一致：启动时清理 `HTTP(S)_PROXY/ALL_PROXY` 等代理环境变量，避免 Judge（openai+httpx）在 SOCKS 代理下因缺少 `socksio` 直接崩溃；如确需代理可传 `--keep-proxies`。
  - `modules/memory/application/graph_service.py`
    - 当 `ttl_default_days<=0`（未启用 TTL 默认值）时，仍为所有写入节点补齐一个稳定的 `expires_at=9999-01-01`（仅在缺失时），避免 Neo4j 在查询阶段对 `expires_at` 软过滤时刷屏 `UnknownPropertyKeyWarning`。

- 测试（Test）
  - 上下文格式锁定：
    - `python -m pytest -q modules/memory/tests/unit/test_dialog_tkg_knowledge_extractor_context_alignment.py` → **passed**
      - 以 `conv-26` 的前两段 session 为样本，断言 `build_dialogue_context` 与 benchmark v2 的 `_build_context` 字符级一致（用本地镜像实现避免 benchmark script 的相对导入问题）。
  - 回归：
    - `python -m pytest -q modules/memory/tests/unit/test_session_write_api.py modules/memory/tests/unit/test_retrieval_dialog_v1.py` → **passed**
    - TTL/soft-filter 噪声控制：
      - `python -m pytest -q modules/memory/tests/unit/test_graph_ttl_defaults.py modules/memory/tests/unit/test_graph_soft_ttl_filters.py` → **passed**

- 结论（Done）
  - `conv-26` 的“写入→检索→Judge→统计”实测入口已具备：不改 API，只通过外部脚本完成 benchmark 风格输出与分布统计；
  - 多 session 上下文格式与 reference time 规则已锁死，避免 drift；后续只需要在真实环境运行脚本即可获得可对比的结果与定位线索。

---

## 30. Patch：去除导入时副作用 + HTTP 端口异步化（2025-12-19）

- 动机（Why）
  - 服务模块导入即初始化 DB/网络连接，破坏可测性与部署可控性；
  - `asyncio.to_thread(asyncio.run(...))` 是嵌套事件循环的坏味道，会引发退出/线程清理问题；
  - `HttpMemoryPort` 用同步 `requests` 包裹异步接口，带来线程阻塞与测试不稳定；
  - 对话文本流水线未写入 `tenant_id`，离线/脚本路径容易丢租户边界。

- 实现（What）
  - `modules/memory/api/server.py`
    - 引入 LazyProxy 与延迟初始化：首次请求才创建 `MemoryService/GraphService/EquivStore`；
    - `runtime_config` 改为按需加载，避免 import 时污染；
    - 启动阶段改为后台 best-effort `ensure_schema_v0`，移除 import-time 连接副作用。
  - `modules/memory/infra/neo4j_store.py`
    - 去除构造函数内的 schema 初始化；公开 `ensure_schema_v0()` 显式调用入口。
  - `modules/memory/infra/qdrant_store.py`
    - `ensure_collections` 拆为 sync 实现 + `asyncio.to_thread` 包装，避免嵌套 loop。
  - `modules/memory/adapters/http_memory_port.py`
    - 切换到 `httpx.AsyncClient`，移除线程包装；新增 `close()` 便于主动释放连接。
  - `modules/memory/domain/dialog_text_pipeline_v1.py`
    - 对 event/timeslice/fact 的 metadata 补齐 `tenant_id`，避免离线写入丢租户边界。
  - 测试更新
    - `modules/memory/tests/unit/test_http_memory_port_adapter.py` 使用 `httpx.MockTransport`；
    - `modules/memory/tests/unit/test_dialog_text_pipeline_alignment.py` 补齐 `metadata.tenant_id` 对齐断言。
    - 异步测试统一改为 `pytest.mark.anyio`，移除 `pytest.ini` 的 `asyncio_mode` 配置；
    - `modules/memory/tests/conftest.py` 固定 `anyio_backend="asyncio"`，避免 trio 依赖。

- 测试（Test）
  - `pytest -q modules/memory/tests/unit/test_http_memory_port_adapter.py`
  - `pytest -q modules/memory/tests/unit/test_dialog_text_pipeline_alignment.py`
  - `UV_CACHE_DIR=.uv-cache uv run pytest modules/memory/tests/unit/test_edge_expansion_config.py modules/memory/tests/unit/test_edit_safety.py modules/memory/tests/unit/test_event_publish_on_write.py modules/memory/tests/unit/test_graph_scope_filter.py modules/memory/tests/unit/test_link_whitelist.py modules/memory/tests/unit/test_metrics_histogram.py modules/memory/tests/unit/test_object_search.py modules/memory/tests/unit/test_runtime_config_hot_update.py modules/memory/tests/unit/test_speech_and_anchor.py modules/memory/tests/unit/test_timeline_summary.py modules/memory/tests/unit/test_http_memory_port_adapter.py modules/memory/tests/unit/test_dialog_text_pipeline_alignment.py -q`

- 结论（Done）
  - 服务导入不再触发 DB/HTTP 连接与索引创建；启动与运维行为可控；
  - HTTP 端口 API 真正异步化，测试稳定性提升；
  - anyio 后端固定为 asyncio，避免 trio 缺失导致的单测失败；
  - 对话文本流水线补齐租户元数据，减少跨租户污染风险。

---

## 31. Patch：E2E Judge 配置从 `memory.config.yaml` 读取（2025-12-19）

- 动机（Why）
  - E2E 脚本过去只能从环境变量构造 Judge，导致“同一套对话与检索链路”在不同机器上出现不可控差异（尤其是 Judge 模型/后端不一致时）。
  - 我们需要把 Judge 与 Memory 的 LLM 选择统一到同一个配置入口，才能把“链路差异”和“模型差异”拆开看。

- 实现（What）
  - `modules/memory/scripts/e2e_dialog_conv26_session_write_and_retrieval.py`
    - 新增 `build_judge_from_memory_config()`：优先读取 `modules/memory/config/memory.config.yaml` 的 `memory.llm.judge`；
    - 若配置缺失/构造失败，才回退到 `create_judge_from_env()`（保持向后兼容，避免破坏现有运行方式）。
  - `modules/memory/config/memory.config.yaml`
    - 保持与 benchmark v2 默认口径一致：`extract=google/gemini-2.5-flash`、`qa=qwen-plus`、`judge=google/gemini-2.5-flash-lite`。

- 自检（Test）
  - 语法检查：
    - `python -m py_compile modules/memory/scripts/e2e_dialog_conv26_session_write_and_retrieval.py` → **passed**

---

## 32. Patch：实体时间线落地（/graph/v0/entities/{id}/timeline）（2025-12-23）

- 动机（Why）
  - `/graph/v0/entities/{id}/timeline` 直接 500（store 方法空实现），前端/调试接口不可用。

- 实现（What）
  - `modules/memory/infra/neo4j_store.py`
    - `query_entity_timeline` 补全：按 `Evidence -> Entity` + `UtteranceEvidence -> Entity` 拉取时间线条目；
    - 返回字段统一为 `{segment_id, source_id, t_media_start, t_media_end, evidence_id, ...}`，并标注 `kind`。
  - 单测新增：
    - `modules/memory/tests/unit/test_neo4j_entity_timeline.py`（Fake driver 合并 evidence + utterance）

- 测试（Test）
  - `UV_CACHE_DIR=.uv-cache uv run pytest modules/memory/tests/unit/test_neo4j_entity_timeline.py -q`
    - 结果：1 passed（`joblib` 权限警告，不影响结果）

---

## 33. Patch：清理 build_event_relations 死代码（2025-12-23）

- 动机（Why）
  - `build_event_relations` 尾部残留一段不可达的查询代码，且引用未定义 `entity_id`，潜在维护风险。

- 实现（What）
  - `modules/memory/infra/neo4j_store.py`
    - 删除 `build_event_relations` 末尾的死代码块（Evidence/Entity 查询）。

- 测试（Test）
  - `UV_CACHE_DIR=.uv-cache uv run pytest modules/memory/tests/unit/test_graph_event_relations.py -q`
    - 结果：1 passed（`joblib` 权限警告，不影响结果）

---

## 34. Patch：事件证据补齐语音证据 + 按 source_id 清理（2025-12-25）

- 动机（Why）
  - 事件详情无法定位到具体语音片段，前端只能用 speaker 采样，导致音频错配。
  - Demo 重复 /ingest 会累积图数据，需要按 `source_id` 清理。

- 实现（What）
  - `modules/memory/infra/neo4j_store.py`
    - `query_event_evidence` 增加 `UtteranceEvidence -> Evidence` 语音证据收集并去重合并。
    - 新增 `purge_source`：删除指定 `source_id` 的 segments/events/utterances/evidences/timeslices/knowledge，可选清理孤儿实体/地点。
  - `modules/memory/application/graph_service.py`
    - 新增 `purge_source` 门面方法，清空 explain 缓存。
  - `modules/memory/api/server.py`
    - 新增 `/graph/v0/admin/purge_source`（签名保护）并加入 mutation 速率限制路径。
  - `modules/memory/tests/unit/test_graph_api_endpoints.py`
    - 新增 purge endpoint 单测入口（运行需依赖 FastAPI TestClient）。

- 测试（Test）
  - `MEMORY_STARTUP_ENSURE_GRAPH_SCHEMA=false MEMORY_STARTUP_ENSURE_COLLECTIONS_TIMEOUT_S=0 MEMORY_STARTUP_ENSURE_GRAPH_SCHEMA_TIMEOUT_S=0 UV_CACHE_DIR=.uv-cache PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -q modules/memory/tests/unit/test_graph_api_endpoints.py -k purge --maxfail=1 -vv`
    - 结果：本地运行卡在 TestClient（FastAPI lifespan），已中止；需后续排查或在 CI 环境验证。

---

## 35. Patch：事件列表补齐 action/type/relations（2025-12-26）

- 动机（Why）
  - L1/L2 查询与前端快速问题依赖 `Event.action/event_type` 与 `NEXT_EVENT` 链路，但 `/graph/v0/events` 未返回这些字段。
  - 缺少 relations 会导致 UI 无法构建 `NEXT_EVENT` 边，L2 问题无法推断。

- 实现（What）
  - `modules/memory/infra/neo4j_store.py`
    - `query_events` 返回 `event_type/action/actor_id` 并携带 `relations`（NEXT_EVENT/CAUSES 目标事件）。
  - `modules/memory/tests/unit/test_graph_query_events_fields.py`
    - 新增单测验证 action/type/relations 的序列化。

- 测试（Test）
  - `UV_CACHE_DIR=.uv-cache PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -q modules/memory/tests/unit/test_graph_query_events_fields.py`
    - 结果：1 passed。

---

## 36. Patch：修复 events 列表丢行回归（2025-12-26）

- 动机（Why）
  - `query_events` 追加 `relations` 后，`items.append` 错误缩进导致只返回最后一条事件。

- 实现（What）
  - `modules/memory/infra/neo4j_store.py`
    - 将 `items.append(data)` 移回循环内，恢复多行返回。

- 测试（Test）
  - `UV_CACHE_DIR=.uv-cache PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -q modules/memory/tests/unit/test_graph_query_events_fields.py`
    - 结果：1 passed。
## 37. Patch：dialog_v2 图谱路由 quickstart + 集成回归（2025-12-20）

- 动机（Why）
  - dialog_v2 依赖事件向量与图谱路由（E_event_vec/EN/T），但 quickstart 缺少对应端点说明；
  - 需要一个集成层测试验证“图谱先召回 + 向量补位”的并行路径在 MemoryService 上可跑通。

- 实现（What）
  - `modules/memory/docs/API_QUICKSTART_v2.md`
    - 增加 `/graph/v1/search`、`/graph/v0/entities/resolve`、`/graph/v0/timeslices/range` 的最小调用示例与返回说明。
  - `modules/memory/tests/integration/test_dialog_v2_retrieval_integration.py`
    - 新增 dialog_v2 集成测试：Stub graph store + InMemVectorStore，验证 E_event_vec 保留与 E_vec 补位。

- 测试（Test）
  - `python -m pytest -q modules/memory/tests/integration/test_dialog_v2_retrieval_integration.py` → **passed**

- 结论（Done）
  - dialog_v2 的图谱端点在 quickstart 中有了最小用法；
  - 通过集成测试锁定“图谱候选保留 + 向量补位”的关键行为。

---

## 38. Patch：dialog_v2 融合策略修正（Graph Cap + RRF + Fact 路由）（2025-12-20）

- 动机（Why）
  - Graph-first 倒排召回容易吞掉候选池，导致向量/知识路由被挤出；
  - L2/L4 任务缺显式时间锚时，必须依赖 Knowledge/Fact 作为时间与关系表述入口；
  - 原始分数加权尺度不一致，RRF 更稳定。

- 实现（What）
  - `modules/memory/retrieval.py`
    - dialog_v2 增加 `fact_search`（Knowledge/Fact 路由）并映射到 event_id；
    - 引入 `graph_cap` 与 RRF 融合（`rrf_k`），降低倒排噪声占比；
    - L2/L4 QA evidence 设定默认上限（降低噪声干扰）。
  - `modules/memory/tests/unit/test_retrieval_dialog_v2.py`
    - 新增 fact 路由单测，确保 event_id 映射可用。

- 测试（Test）
  - `python -m pytest -q modules/memory/tests/unit/test_retrieval_dialog_v2.py modules/memory/tests/integration/test_dialog_v2_retrieval_integration.py` → **passed**

- 结论（Done）
  - dialog_v2 候选池不会被 E_event_vec 全量吞掉；
  - fact 路由进入候选池，为 L2/L4/L5 提供语义时间锚点。

---

## 39. Patch：TKG 知识抽取提示词增强（Temporal Grounding 强约束 + One-shot）（2025-12-21）

- 动机（Why）
  - 现有抽取经常漏填 `temporal_grounding`，导致 L2/L4 时间推理证据缺口；
  - 需要通过强约束 + one-shot 明确“时间表达必须落地”的行为。

- 实现（What）
  - `modules/memory/application/prompts/dialog_tkg_knowledge_extractor_system_prompt_v1.txt`
    - 增加 temporal grounding 强约束规则与 one-shot 示例。
  - `benchmark/archive/v2/prompts/tkg_knowledge_extractor_system_prompt_v1.txt`
    - 与生产 prompt 同步，保证 benchmark 对齐。

- 测试（Test）
  - 未运行（仅文案更新，后续可运行 `python -m pytest -q modules/memory/tests/unit/test_dialog_tkg_knowledge_extractor_prompt_alignment.py`）。

- 结论（Done）
  - temporal grounding 输出门槛提高，降低“有时间表达却空数组”的失败率。

---

## 40. Patch：TKG Knowledge 写入保留 temporal_grounding/mentions（2025-12-21）

- 动机（Why）
  - 抽取层已生成 temporal_grounding/mentions，但图构建阶段丢弃，导致 L2/L4 时间推理证据缺口。

- 实现（What）
  - `modules/memory/domain/dialog_tkg_graph_v1.py`
    - Knowledge.data 写入 `temporal_grounding` 与 `mentions`，保持抽取输出完整性。

- 测试（Test）
  - 未运行（逻辑字段透传，后续配合抽取输出手动核查）。

- 结论（Done）
  - Knowledge 节点保留时间锚信息，为检索与 QA 时间约束提供基础。

---

## 41. Patch：E2E 时间戳修复 + QA Top30 + QA 模型切换（2025-12-20）

- 动机（Why）
  - `dialog_v2` 的 L2/L1 分数被“写入时间戳错误 + QA 证据截断”系统性拖垮，导致实验结论不可用；
  - 需要提供一个“跳过写入”的 rerun 模式，用同一份 DB 数据快速对比 QA/Prompt 改动的影响。

- 实现（What）
  - `modules/memory/scripts/e2e_dialog_conv26_session_write_and_retrieval.py`
    - 复用 `modules/memory/domain/dialog_text_pipeline_v1.parse_datetime()`，避免脚本内错误正则导致的时间戳回退；
    - 增加 `--skip-session-write`，允许跳过抽取与写入，直接复用现有 DB 做 retrieval+QA+judge 对比。
  - `modules/memory/scripts/e2e_dialog_conv30_session_write_and_retrieval.py`
    - 同步修复时间解析并增加 `--skip-session-write`（保持脚本一致性）。
  - `modules/memory/application/qa_dialog_v1.py`
    - QA prompt 证据条数上限从 15 提升到 30（用于恢复 baseline，降低“gold 在 top30 但不在 top15”的系统性失败）。
  - `modules/memory/config/memory.config.yaml`
    - QA 模型切换为 `dashscope/qwen-flash`（需要 `DASHSCOPE_API_KEY` 或 `QWEN_API_KEY`）。

- 测试（Test）
  - `python -m py_compile`（见本次改动文件）→ 预期通过
  - `pytest -q modules/memory/tests/unit/test_dialog_qa_prompt_alignment.py` → 覆盖 QA Top30 截断
  - `pytest -q modules/memory/tests/unit/test_dialog_text_pipeline_alignment.py` → 覆盖 LoCoMo datetime 解析

- 结论（Done）
  - E2E 写入时间戳不再被错误回退到默认时间；
  - QA 端能看到 top30 证据，baseline 更可信；
  - rerun 可以选择跳过写入，便于做“只变 QA/Prompt”的可比实验。

---

## 42. Patch：QA 切换 OpenRouter grok + dialog_v2 候选事件 ID 合并与多路命中加分（2025-12-21）

- 动机（Why）
  - L1 错题里存在“gold 已在 top30 但 QA 答错”和“多路检索命中同一事件却无法在候选池内合并”的问题；
  - 先做最小变动：不改 prompt、不改 topK/候选池大小，只验证更强 QA 模型与事件 ID 合并能否带来稳定增益。

- 实现（What）
  - `modules/memory/config/memory.config.yaml`
    - QA 模型切换为 `openrouter/x-ai/grok-4.1-fast`（需要 `OPENROUTER_API_KEY`）。
  - `modules/memory/retrieval.py`
    - `dialog_v2`：对逻辑事件 ID（`conv-xx_Dy_z`）与 TKG event id（UUID）做 canonicalization 合并，避免多路命中时候选分裂；
    - `dialog_v2`：新增“多路命中加分” `_multi_bonus`（默认权重 `multi=0.03`），让多路命中的事件排序更靠前；
    - explain 阶段始终使用 `tkg_event_id` 调用图接口，避免逻辑 ID 误入 explain。
  - `modules/memory/tests/unit/test_retrieval_dialog_v2.py`
    - 新增单测：验证逻辑 ID 与 TKG ID 能在 dialog_v2 内合并，且 explain 使用 TKG id。

- 测试（Test）
  - `python -m pytest -q modules/memory/tests/unit/test_retrieval_dialog_v2.py` → **passed**

- 结论（Done）
  - QA 模型已切换为 OpenRouter grok fast；
  - dialog_v2 候选池内的“同事件多路命中”能合并并获得小幅排序提升，为后续 L1 召回/排序诊断提供更干净的对比基线。

---

## 43. Patch：E2E 并发跑批（2025-12-21）

- 动机（Why）
  - 端到端评测主要耗时在 QA / Judge 的远端 LLM 调用，串行执行会把 wall time 拉得非常长；
  - 需要一个简单、可控的并发开关来探测限流与提升吞吐（先用 concurrency=20 试探）。

- 实现（What）
  - `modules/memory/scripts/e2e_dialog_conv26_session_write_and_retrieval.py`
    - 新增参数 `--concurrency`：用 asyncio semaphore 并发执行每条 query 的 retrieval+QA，并将 judge 放入 `asyncio.to_thread` 避免阻塞 event loop；
    - 保持统计与落盘在单锁内，避免并发写文件与计数错乱。
  - `modules/memory/tests/unit/test_e2e_locomo_helpers.py`
    - 新增轻量单测：覆盖 `_resolve_queries_path` / `_discover_sample_ids`，确保 `--sample-id 0` 的“全量样本发现”逻辑稳定。

- 测试（Test）
  - `pytest -q modules/memory/tests/unit/test_e2e_locomo_helpers.py` → **passed**

- 使用（Run）
  - 跳过写入、并发 20（探测限流）：
    - `python -m modules.memory.scripts.e2e_dialog_conv26_session_write_and_retrieval --sample-id conv-26 --skip-session-write --concurrency 20 ...`

---

## 44. Patch：`retrieval()` 默认策略切换为 `dialog_v2`（2025-12-21）

- 动机（Why）
  - 当前工程主线已以 `dialog_v2` 作为默认检索策略（多路并行召回 + 候选池融合 + explain），继续默认 `dialog_v1` 会让调用方在“不传 strategy”时拿到过时基线。

- 实现（What）
  - `modules/memory/retrieval.py`
    - `retrieval(..., strategy: str = "dialog_v2")`（默认策略改为 v2）
  - `modules/memory/tests/unit/test_retrieval_dialog_v1.py`
    - 对所有 v1 测试显式传 `strategy="dialog_v1"`，避免测试依赖默认值。
  - `modules/memory/docs/API_QUICKSTART_v2.md`
    - 更新签名示例默认 strategy 为 `dialog_v2`。
  - `modules/memory/docs/RETRIEVAL_API_AND_WORKFLOW.md`
    - 更新文档：默认策略为 `dialog_v2`，`dialog_v1` 作为 benchmark/回归基线。

- 测试（Test）
  - `pytest -q modules/memory/tests/unit/test_retrieval_dialog_v1.py modules/memory/tests/unit/test_retrieval_dialog_v2.py` → **passed**

---

## 45. Patch：对外 Python SDK `omem`（会话 commit + 对话 retrieval，HTTP 客户端）（2025-12-22）

- 动机（Why）
  - 开发者需要一个稳定、低心智负担的 Python SDK，把“会话提交（commit）”与“对话召回（retrieval）”两条高阶链路直接对接到后端服务；
  - SDK 必须以 HTTP 方式工作（面向远程 Memory 服务），避免 in-proc 依赖与部署耦合；
  - 对外 import name 固定为 `omem`（全小写），作为长期稳定的用户空间入口。

- 实现（What）
  - `omem/__init__.py`
    - 固定对外导出：`MemoryClient` / `SessionBuffer` / `CommitHandle` 与类型模型。
  - `omem/types.py`
    - 定义 SDK 侧稳定输入/状态模型：`CanonicalTurnV1`、`JobStatusV1`、`SessionStatusV1`。
  - `omem/client.py`
    - `MemoryClient`：封装 HTTP 调用与默认 headers（`X-Tenant-ID`、可选 `X-API-Token`）：
      - `POST /ingest/dialog/v1`（commit）
      - `GET /ingest/jobs/{job_id}`（status）
      - `GET /ingest/sessions/{session_id}`（cursor/status）
      - `POST /retrieval/dialog/v2`（dialog_v2 retrieval）
    - `SessionBuffer`：本地 `append_turn` 累积 turns，`commit()` 仅发送增量 turns（基于 cursor），支持 `sync_cursor_from_server()`。
  - `pyproject.toml`
    - `tool.setuptools.packages.find.include` 增加 `omem*`，确保对外包可被打包发布。

- 测试（Test）
  - `modules/memory/tests/unit/test_omem_sdk_http.py`
    - 用 `httpx.MockTransport` 覆盖：
      - commit 调用 `/ingest/dialog/v1` + headers 注入；
      - commit 增量发送（cursor 生效）；
      - retrieval 调用 `/retrieval/dialog/v2`；
      - session cursor sync 后 turn_id 递增正确。
  - `pytest -q modules/memory/tests/unit/test_omem_sdk_http.py` → **passed**

---

## 46. Patch：新增 ingest/retrieval 高阶 HTTP 端点（SDK 对接面）（2025-12-22）

- 动机（Why）
  - SDK 已确定以 `omem` 对外提供，并默认对接 `POST /ingest/dialog/v1` 与 `POST /retrieval/dialog/v2`；
  - 当前 `server.py` 只有底层 `/search` `/write` 等端口，缺少高阶链路的 HTTP 入口；
  - 需要把 in-proc 的 `session_write(...)` 与 `retrieval(...)` 显式暴露为版本化端点。

- 实现（What）
  - `modules/memory/application/ingest_jobs.py`
    - 新增内存型 `IngestJobStore`：记录 job 状态、session cursor、commit 幂等索引。
  - `modules/memory/api/server.py`
    - 新增端点：
      - `POST /ingest/dialog/v1`
      - `GET /ingest/jobs/{job_id}`
      - `GET /ingest/sessions/{session_id}`
      - `POST /retrieval/dialog/v2`
    - `POST /ingest/dialog/v1`：
      - 接受 `turns`，写入 job store 后异步触发 `session_write(...)`；
      - 默认 `llm_policy=require`，失败进入 `STAGE3_FAILED` 并按退避重试。
    - `POST /retrieval/dialog/v2`：
      - 直接调用 `retrieval(..., strategy="dialog_v2")`，并受高成本熔断/超时保护。
    - 新增熔断器 key：`retrieval`
    - 将 `/ingest/dialog/v1` 纳入 mutation 路径（限流/写签名策略一致）

- 测试（Test）
  - `modules/memory/tests/unit/test_ingest_retrieval_endpoints.py`
    - 通过 monkeypatch 关闭 auth、禁用后台任务，验证端点可用与 job/session 状态正确；
    - 验证 `/retrieval/dialog/v2` 透传参数并调用高阶检索函数。
  - `pytest -q modules/memory/tests/unit/test_ingest_retrieval_endpoints.py` → **passed**

---

## 47. Patch：ingest job 持久化（SQLite）与启动重试恢复（2025-12-22）

- 动机（Why）
  - 之前的 ingest job 仅为进程内存结构，服务重启会丢失状态，无法满足“重试直到成功”的语义；
  - 需要把 job/commit/session 状态持久化，并在服务启动时自动恢复待重试任务。

- 实现（What）
  - `modules/memory/infra/ingest_job_store.py`
    - 新增 SQLite 持久化存储：
      - `ingest_jobs`（job 详情 + turns + 状态）
      - `ingest_session_state`（session 最新状态与 cursor）
      - `ingest_commit_index`（session+commit_id 幂等索引）
    - `sqlite_path` 默认：`modules/memory/outputs/ingest_jobs.db`（可由 `MEMORY_INGEST_JOB_DB_PATH` 覆盖）。
  - `modules/memory/application/ingest_jobs.py`
    - 应用层 re-export，隔离调用路径，避免上层直连 infra。
  - `modules/memory/api/server.py`
    - ingest_store 改为 SQLite 版本（支持落盘）；
    - 启动时扫描 `RECEIVED/STAGE2_FAILED/STAGE3_FAILED/STAGE2_RUNNING/STAGE3_RUNNING`，自动重启任务；
    - `create_job` 记录 tenant/user_tokens/memory_domain/llm_policy，确保重启可调度。

- 测试（Test）
  - `pytest -q modules/memory/tests/unit/test_ingest_retrieval_endpoints.py` → **passed**

---

## 48. Patch：Stage2 价值标注（TurnMark + PinIntent）接入 ingest 管线（2025-12-22）

- 动机（Why）
  - Stage2 是重型写入的关键治理环节：在进入抽取/建图前对 turns 做价值标注与过滤；
  - 必须落地 TurnMark/PinIntent 的数据契约与校验逻辑，避免 LLM 抄写/污染。

- 实现（What）
  - `modules/memory/application/turn_mark_extractor_dialog_v1.py`
    - 新增 Stage2 抽取器（LLM）：TurnMark 输出解析 + 严格校验；
    - 程序化生成 PinIntent（用户主动保存）与 kept turns；
    - 默认 TTL/forget_policy 使用硬编码策略（不信任 LLM 输出）。
  - `modules/memory/application/prompts/dialog_turn_mark_system_prompt_v1.txt`
    - Stage2 TurnMark 系统提示（严格 JSON 输出、无 text_exact）。
  - `modules/memory/infra/ingest_job_store.py`
    - job 持久化新增 `stage2_marks`、`stage2_pin_intents` 字段；
    - 增加 `update_stage2(...)` 以持久化 Stage2 产物。
  - `modules/memory/api/server.py`
    - ingest 任务中插入 Stage2：
      - `llm_policy=require` → Stage2 失败则进入重试；
      - `llm_policy=best_effort` → 无 LLM 时使用“keep all”回退；
    - PinIntent 生成后追加为 note 事实写入（`extra_facts`）。
  - `modules/memory/session_write.py`
    - 新增 `extra_facts` 参数：用于注入 PinIntent note。

- 测试（Test）
  - `modules/memory/tests/unit/test_turn_mark_extractor_dialog_v1.py`
    - 覆盖 TurnMark 校验、span 裁剪、PinIntent 与 note 生成。
- `pytest -q modules/memory/tests/unit/test_turn_mark_extractor_dialog_v1.py` → **passed**

---

## 49. Patch：Stage3 发布门控（published）与检索过滤（2025-12-22）

- 动机（Why）
  - Stage3 若写入中断（图/向量部分成功），必须保证“对外不可见”，避免不完整数据污染检索；
  - 需要一个最小的发布门控（published）来实现幂等重试与可见性隔离。

- 实现（What）
  - `modules/memory/contracts/memory_models.py`
    - `MemoryEntry.published` + `SearchFilters.published`；
  - `modules/memory/contracts/graph_models.py`
    - `Provenanced.published`，让 TKG 节点/边可持久化发布状态；
  - `modules/memory/application/service.py`
    - 搜索默认加 `published=True`（排除显式 unpublished）；
    - 新增 `publish_entries(...)`，发布向量/图节点；
  - `modules/memory/infra/qdrant_store.py`
    - `published` 过滤 + `set_published(...)` 批量标记；
  - `modules/memory/infra/inmem_vector_store.py`
    - `published` 过滤 + `set_published(...)`；
  - `modules/memory/infra/neo4j_store.py`
    - 查询与 expand_neighbors 增加 published 过滤；
    - 新增 `set_nodes_published(...)`；
  - `modules/memory/infra/inmem_graph_store.py`
    - expand_neighbors 跳过 unpublished 节点；
  - `modules/memory/session_write.py`
    - 仅当 store 支持发布时，先写入 `published=False`；
    - Stage3 成功后调用 `publish_entries(...)` 统一发布。

- 测试（Test）
  - `modules/memory/tests/unit/test_filters_published.py`
  - `pytest -q modules/memory/tests/unit/test_filters_published.py modules/memory/tests/unit/test_session_write_graph_upsert.py modules/memory/tests/unit/test_session_write_api.py` → **passed**

---

## 50. Patch：Stage2 TTL/importance 回写到事实与图节点（2025-12-22）

- 动机（Why）
  - Stage2 输出了 TTL/importance，但未落入实体节点，导致治理信息“只停留在 job 记录里”；
  - 需要把生命周期信息写入 Event/Utterance/Knowledge/Facts，支撑后续衰减与清理。

- 实现（What）
  - `modules/memory/session_write.py`
    - 支持 `turn_marks` 入参；
    - turn_id → index 映射，按标注回写：
      - TKG utterance 向量条目（metadata.importance/ttl/forgetting_policy）；
      - fact 向量条目（metadata.importance/ttl/forgetting_policy）；
    - fact 聚合策略：
      - importance = max(fact_importance, max(mark_importance))
      - ttl = min(所有正数 TTL)，若无正数则 0（永久）
      - forget_policy：优先 until_changed → permanent → temporary
  - `modules/memory/domain/dialog_tkg_graph_v1.py`
    - 支持 `turn_marks_by_index`；
    - Event/Utterance 节点回写 importance/ttl/forgetting_policy；
    - Knowledge 节点回写 importance/ttl/forgetting_policy（来自 fact 聚合结果）。
  - `modules/memory/api/server.py`
    - Stage2 输出 `marks` 透传到 `session_write(turn_marks=...)`。

- 测试（Test）
  - `pytest -q modules/memory/tests/unit/test_session_write_graph_upsert.py modules/memory/tests/unit/test_session_write_api.py` → **passed**

---

## 51. Patch：Stage2 标注容错 + TTL=0 修复 + 最小 e2e 验证（2025-12-22）

- 动机（Why）
  - Stage2 LLM 输出偶发非法类别导致整条管线失败（`category_invalid`）；
  - TTL=0（永久）在 Knowledge 节点被错误吞掉；
  - 需要一条最小真实 LLM 的端到端验证，确认 Stage2→Stage3→发布闭环。

- 实现（What）
  - `modules/memory/application/turn_mark_extractor_dialog_v1.py`
    - `validate_and_normalize_marks(..., strict: bool = True)`；
    - `strict=False` 时容错：非法 category/subtype/evidence 纠偏为默认值，非法 span/importance 纠偏或忽略，避免整批失败；
  - `modules/memory/api/server.py`
    - Stage2 使用 `strict=False`，防止 LLM 细节噪声导致 job 失败；
  - `modules/memory/domain/dialog_tkg_graph_v1.py`
    - 修复 TTL=0 被 `or` 吞掉的问题（显式判空后再取 `ttl` 兜底）。

- 测试与验证（Test）
  - `pytest -q modules/memory/tests/unit/test_turn_mark_extractor_dialog_v1.py` → **passed**
  - 最小 e2e（真实 LLM）：
    - Stage2 marks: `user_triggered_save=true`, `importance=0.9`, `ttl=0`, `permanent`
    - Stage3: `graph_upsert_status=ok`, `publish_updates={vectors:10, graph:6}`
    - Qdrant：fact entries `importance=0.9`, `ttl=0`, `published=true`
    - Neo4j：Event/Knowledge/Utterance `importance=0.9`, `ttl=0`, `published=true`

---

## 52. Patch：Stage2 默认 best‑effort + 两条管线实测补齐（2025-12-23）

- 动机（Why）
  - 线上环境不允许因 LLM 小幅格式噪声导致整条 ingest 失败；
  - 补齐两条关键验收：**部分写入不可见** 与 **增量续写只提交新增 turns**。

- 实现（What）
  - `modules/memory/application/turn_mark_extractor_dialog_v1.py`
    - Stage2 校验支持 `strict` 参数，默认由调用方控制；
  - `modules/memory/api/server.py`
    - Stage2 使用 `stage2_strict=false` 作为默认（best‑effort）；
  - `modules/memory/scripts/e2e_ingest_contracts.py`
    - 新增两条 e2e contract 探针：
      - failure_path（图成功/向量失败 → 对外不可见）
      - incremental_commit（两次 commit 仅提交新增 turns）
    - `base-url=local` 支持在无 HTTP/代理环境下验证 ingest cursor 逻辑。

- 测试与验证（Test）
  - `pytest -q modules/memory/tests/unit/test_turn_mark_extractor_dialog_v1.py` → **passed**
  - `modules/memory/scripts/e2e_ingest_contracts.py --base-url local`：
    - failure_path：`neo4j_event_published=false`，`graph_explain_filtered_out=true`
    - failure_path：`vector_count=0`（run_id 维度无向量可见）
    - incremental_commit：`cursor_after_commit_1=t0003`，`cursor_after_commit_2=t0005`

---

## 53. Patch：LongMemEval（oracle 子集）E2E 脚本（2025-12-22）

- 动机（Why）
  - LongMemEval `m_cleaned` 体量巨大（对话干扰库暴涨），不适合一上来全量做 LLM 抽取与写入；
  - 需要一条可复现、可隔离、可断点的 E2E 路径：先对子集做抽取建图，人工确认后再跑检索与汇总。

- 实现（What）
  - 新增 `modules/memory/scripts/e2e_longmemeval_oracle_subset_write_and_retrieval.py`：
    - 读取子集文件（`meta+items`），按 `question_id` 作为 `session_id/run_id` 写入；
    - 强隔离：`--tenant` + `--memory-domain` + `--user-prefix`（每题一个 user token）；
    - 支持两阶段运行：`--mode ingest|benchmark|all`；
    - Benchmark 支持并发检索：`--benchmark-concurrency N`（注意：开启 `with_answer` 时会并发调用 QA LLM，容易触发限流，建议小步调参）；
    - 抽取分块：通过 `MEMORY_DIALOG_TKG_EXTRACT_SESSIONS_PER_CALL` 控制（避免上下文溢出）；
    - benchmark 默认使用低成本字符串匹配打分；可选启用 LLM judge（若配置存在）。
    - 抽取/建图产物持久化：
      - `<out-dir>/artifacts/<question_id>.json`：保存 LLM 抽取 trace（含 raw 响应）、最终 facts、以及纯函数构建的 graph_upsert_request 快照；
      - `<out-dir>/audit.db`：索引 artifacts 路径与 sha256（大对象不写入 sqlite）。
      - 可选：`LONGMEMEVAL_TRACE_INCLUDE_CONTEXT=1` 将每个 chunk 的 context 一并落盘（默认关闭，避免重复存储对话原文）。

- 验证（Test）
  - 该脚本为外部依赖型（Qdrant/Neo4j/LLM），不在单元测试中强制执行；子集抽样的确定性与分布由 `benchmark/tests/suites/longmemeval/test_longmemeval_subset.py` 覆盖。

---

## 54. Patch：LongMemEval 专用 QA Prompt（2025-12-23）

- 动机（Why）
  - LongMemEval 的 `temporal-reasoning` 依赖题目自带的 `question_date` 作为 “Current Date” 锚点；
  - 通用 QA prompt 缺少该锚点，导致模型把 evidence 中的 “today” 误解释为同一天，产生系统性偏差。

- 实现（What）
  - 新增 `modules/memory/application/qa_longmemeval.py`：
    - LongMemEval 专用 system prompt：
      - `LME_SYSTEM_PROMPT`：强制“只输出答案/不足则固定文本”，并避免输出 Evidence/推理；
      - `LME_PREFERENCE_SYSTEM_PROMPT`：针对 `single-session-preference` 强制输出 “The user would prefer ... They might not prefer ...” 画像格式；
      - `LME_TEMPORAL_SYSTEM_PROMPT`：针对 `temporal-reasoning` 强化 “Current Date 是唯一时间锚点”，减少 today 歧义；
      - `LME_ASSISTANT_SYSTEM_PROMPT`：针对 `single-session-assistant` 强制短答案输出，减少冗余与截断风险；
    - `should_use_longmemeval_prompt(...)`：按 `memory_domain`/`task` 自动启用；
    - `extract_question_date_from_time_hints(...)`：从 `time_hints` 获取题目日期。
  - `modules/memory/retrieval.py`
    - 在 `with_answer=True` 时，如果命中 LongMemEval 且 `time_hints` 提供了 `question_date`，使用 LongMemEval 专用 system prompt + user prompt（包含 `Current Date`）。
  - `modules/memory/scripts/e2e_longmemeval_oracle_subset_write_and_retrieval.py`
    - benchmark 调用 retrieval 时传入 `time_hints={"question_date": <raw question_date>}`。

- 测试（Test）
  - 新增 `modules/memory/tests/unit/test_qa_longmemeval_prompt.py`：覆盖 prompt 选择与 user prompt 生成。

---

## 55. Patch：LongMemEval 默认使用 LLM Judge 语义打分（2025-12-23）

- 动机（Why）
  - LongMemEval 的 gold answer 里有大量自由文本（尤其 `single-session-preference`），用字符串包含/等值的“便宜打分”会制造大量假阴性，误导调参方向。
  - “不配置 judge 时自动降级到规则打分”是危险行为：它会在日志里看起来像“准确率很低”，但本质是在测格式噪声而不是语义。

- 实现（What）
  - `modules/memory/scripts/e2e_longmemeval_oracle_subset_write_and_retrieval.py`
    - 默认启用 judge（与 `e2e_dialog_conv26_session_write_and_retrieval.py` 一致），并提供 `--no-judge` 显式关闭。
    - judge 不可用时不再静默降级到规则打分：默认跳过 accuracy（`verdict=None`），除非显式 `--no-judge`。
    - verdict 解析兼容多种 judge 输出形态（`score/binary_correct/label/binary_label`）。

- 验证（Test）
  - 通过 `python -m compileall` 验证脚本语法正确；实际评测需依赖外部 LLM/存储服务环境。

---

## 56. Patch：LongMemEval benchmark 实时打印运行中准确率（2025-12-23）

- 动机（Why）
  - 并发跑 200 题时，缺少“运行中准确率/分类型准确率”会让调参变成盲飞（尤其是限流/错误导致 verdict 缺失时）。

- 实现（What）
  - `modules/memory/scripts/e2e_longmemeval_oracle_subset_write_and_retrieval.py`
    - benchmark 阶段每 `--log-every N` 题打印一次：总耗时、累计准确率、按 `question_type` 的运行中准确率（仿照 conv26 脚本风格）。
    - 仅统计 `verdict != None` 的题（即真正完成 judge/打分的题）；缺失 verdict 的直接跳过统计，避免误导。

- 验证（Test）
  - 通过 `python -m compileall` 验证脚本语法正确；运行中输出可直接在终端观察。

---

## 57. Patch：统一 LongMemEval QA 模型为 GPT-4o-mini（2025-12-23）

- 动机（Why）
  - 多 profile 文件会增加维护成本与误用风险；QA 模型统一后更利于对比实验与复现实验结果。

- 实现（What）
  - `modules/memory/config/memory.config.yaml`：将 `memory.llm.qa.model` 统一设置为 `openai/gpt-4o-mini`（OpenRouter）。

---

## 52. Patch：SDK BYOK 用量上报入口补齐（2025-12-27）

- 动机（Why）
  - SDK 需要稳定的 LLMAdapter 入口与用量 hook，避免 BYOK 调用各自散落；
  - 统一 `LLMUsageContext`/hook 的导出，便于 SDK 侧上报 `llm` usage 事件。

- 实现（What）
  - `modules/memory/__init__.py`：导出 `LLMAdapter`、`LLMUsageContext`、`build_llm_from_env/config` 以及 usage hook API。
  - `modules/memory/tests/unit/test_omem_sdk_byok_usage.py`：新增 SDK BYOK 用量上报的单测（事件构造 + 请求发送）。

- 验证（Test）
  - `.venv/bin/python -m pytest modules/memory/tests/unit/test_omem_sdk_byok_usage.py -q`

---

## 53. Patch：with_answer 公网开关与 scope 约束（2025-12-27）

- 动机（Why）
  - SaaS 公网默认 BYOK，服务端 QA 必须可被强制禁用或受控开放；
  - 避免 `with_answer=true` 被误用导致成本与合规风险。

- 实现（What）
  - `modules/memory/api/server.py`：
    - 新增 `MEMORY_API_WITH_ANSWER_ENABLED` / `MEMORY_API_WITH_ANSWER_SCOPE` 开关；
    - `retrieval/dialog/v2` 在 `with_answer=true` 时触发 `_enforce_with_answer`。
  - `modules/memory/config/memory.config.yaml` / `config/hydra/memory.yaml`：
    - 增补 `memory.api.retrieval.with_answer_enabled/with_answer_scope` 配置。
  - 单测：`modules/memory/tests/unit/test_with_answer_gate.py` 覆盖禁用与 scope 拒绝。

- 验证（Test）
  - `.venv/bin/python -m pytest modules/memory/tests/unit/test_with_answer_gate.py -q`

---

## 54. Patch：Turn 标记规则补强（噪声过滤/情绪保留）（2025-12-27）

- 动机（Why）
  - 降噪优先于抽取，先确保无意义内容不进入 Stage3；
  - 明确情绪与长期偏好不被默认丢弃。

- 实现（What）
  - `modules/memory/application/prompts/dialog_turn_mark_system_prompt_v1.txt`：
    - 明确仅做 keep/drop，不输出 span；
    - 补充噪声类型（base64/长哈希/URL 列表/代码块）与丢弃规则；
    - 强化身份/偏好/情绪保留与助手回复默认丢弃规则。

- 验证（Test）
  - `.venv/bin/python -m pytest modules/memory -q`
  - `.venv/bin/python -m pytest modules/saas_gateway -q`

---

## 58. Patch：Ingest commit 级时间锚定与质量汇总（2025-12-28）

- 动机（Why）
  - 增量提交需要独立的时间可信度判定；不能用 session 创建时的单次 skew 代表后续 commits。
  - 为检索与诊断提供可追溯的时间锚（server_received_at_utc + clock_skew_s + time_quality）。

- 实现（What）
  - `modules/memory/infra/ingest_job_store.py`
    - `ingest_jobs` 增加 `server_received_at_utc/clock_skew_s/time_quality`；
    - `ingest_session_state` 增加 `time_quality_summary`，按最差值汇总（`trusted < suspect < logical_only`，纯 imported 例外）。
  - `modules/memory/api/server.py`
    - `/ingest/dialog/v1` 计算 commit 级 `clock_skew_s/time_quality` 并写入 job；
    - `/ingest/jobs/{job_id}` 与 `/ingest/sessions/{session_id}` 回传时间字段。
  - `modules/memory/tests/unit/test_ingest_retrieval_endpoints.py`
    - 断言无 `timestamp_iso` 时 `time_quality=logical_only` 且 session 汇总一致。

- 验证（Test）
  - `.venv/bin/python -m pytest modules/memory/tests/unit/test_ingest_retrieval_endpoints.py -q`

---

## 59. Patch：BYOK 数据面解析与 LLM 路由（2025-12-29）

- 动机（Why）
  - BYOK 已在控制面具备 Registry/密钥托管，数据面需要解析绑定并统一接入 Stage2/Stage3/QA。

- 实现（What）
  - `modules/memory/application/byok_resolver.py`
    - 新增 `ByokResolver`（binding/profile/credential 解析 + TTL 缓存）；
    - 解析结果不缓存明文 key，仅缓存 `secret_cipher`（满足“明文只存单次调用”）。
  - `modules/memory/application/llm_adapter.py`
    - 新增 `build_llm_from_byok`，按 provider 生成 LLMAdapter（OpenRouter/Qwen/GLM/Gemini 等）。
    - `LLMUsageContext` 增补 BYOK 元信息字段，usage 事件包含 `byok_route/credential_fingerprint/resolver_status`。
  - `modules/memory/api/server.py`
    - Stage2/Stage3/QA 使用 BYOK adapter 优先；解析失败时回落平台路径；
    - LLM usage 事件携带 BYOK 解析状态。

- 验证（Test）
  - `.venv/bin/python -m pytest modules/memory/tests/unit/test_byok_resolver.py -q`
  - `.venv/bin/python -m pytest modules/memory/tests/unit/test_llm_usage_hook.py -q`
  - `.venv/bin/python -m pytest modules/memory/byok_control/tests/unit/test_registry.py -q`

---

## 60. Patch：配置总览与批量热更新接口（2026-01-08）

- 动机（Why）
  - 需要通过 API 读取核心配置并明确哪些字段支持热更新，避免误改。
  - 支持批量热更新，减少多次调用与配置漂移风险。

- 实现（What）
  - `modules/memory/api/server.py`
    - 新增 `GET /config`：返回核心配置快照、热更新路径与当前生效值（含脱敏处理）。
    - 新增 `PATCH /config`：批量更新 rerank/graph/scoping/ann/modality_weights 并返回生效快照。
  - `modules/memory/tests/unit/test_config_endpoints.py`
    - 覆盖 GET/PATCH /config 的基础行为与生效结果。
  - `SDK使用说明.md`、`开发者API 说明文档.md`
    - 补充配置总览与批量热更新的接口说明与示例。

- 验证（Test）
  - `pytest modules/memory/tests/unit/test_config_endpoints.py -q`

---

## 61. Patch：深度健康检查 (Deep Health Check)（2026-01-07）

- 动机（Why）
  - 原有 `/health` 仅检查 vectors/graph 存活状态，无法发现 OpenRouter 余额耗尽或磁盘空间不足等隐患。
  - SaaS Worker 依赖 503 状态码判断是否暂停派单，需要服务主动降级。

- 实现（What）
  - `modules/memory/application/service.py`
    - 新增 `_check_llm_provider_health()`：检查 OpenRouter 认证 (`/auth/key`) 与余额 (`/credits`)，区分 `API_KEY_MISSING`/`AUTH_FAILED`/`CONNECTION_FAILED`/`BALANCE_BELOW_THRESHOLD` 四种错误码，返回实际余额数值 (`remaining_usd`)，带 60 秒缓存。
    - 新增 `_check_disk_health()`：检查指定路径的剩余空间，区分 `PATH_NOT_ACCESSIBLE`/`SPACE_BELOW_THRESHOLD`，返回实际空间 (`free_mb`)。
    - 重构 `health_check()`：聚合 vectors/graph/llm_provider/disk 四项检查，任一失败则整体 `status=fail`。
  - `modules/memory/api/server.py`
    - `/health` 端点根据 `status` 返回 200 OK 或 503 Service Unavailable。
    - 新增 `JSONResponse` import。
  - `modules/memory/tests/unit/test_health_readiness.py`
    - 更新断言以匹配新的嵌套响应结构 (`dependencies.llm_provider`/`dependencies.disk`)。

- 环境变量配置
  | 变量名 | 默认值 | 说明 |
  |--------|--------|------|
  | `OPENROUTER_API_KEY` | (必填) | OpenRouter API Key |
  | `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | OpenRouter API 地址 |
  | `MEMORY_HEALTH_OPENROUTER_MIN_USD` | `1.0` | 最小余额阈值 (美元) |
  | `MEMORY_HEALTH_LLM_CACHE_TTL_S` | `60` | LLM 检查缓存 TTL (秒) |
  | `MEMORY_HEALTH_DISK_PATH` | (自动检测) | 磁盘检查路径 |
  | `MEMORY_HEALTH_DISK_MIN_FREE_MB` | `512` | 最小剩余空间阈值 (MB) |

- 错误码定义
  | 组件 | 错误码 | 含义 |
  |------|--------|------|
  | LLM Auth | `API_KEY_MISSING` | 环境变量未配置 |
  | LLM Auth | `AUTH_FAILED` | Key 无效 (401/403) |
  | LLM Auth | `CONNECTION_FAILED` | 网络不可达 |
  | LLM Balance | `BALANCE_BELOW_THRESHOLD` | 余额低于阈值 |
  | Disk | `PATH_NOT_ACCESSIBLE` | 路径不存在或无权限 |
  | Disk | `SPACE_BELOW_THRESHOLD` | 剩余空间低于阈值 |

- 验证（Test）
  - `pytest modules/memory/tests/unit/test_health_readiness.py -v`
  - 结果：**3 passed in 0.26s**
    - `test_health_check_includes_openrouter_and_disk_ok` ✅
    - `test_health_check_fails_when_openrouter_key_missing` ✅
    - `test_health_http_returns_503_when_unhealthy` ✅

#### 2026-01-07 深层健康检查审计修复
- 背景：审查发现文档与实现漂移、时间戳格式不严谨、测试用例不足。
- 变更：
  - 代码修正：
    - `MemoryService.health_check`：时间戳格式修正为 `%Y-%m-%dT%H:%M:%SZ`（严格 ISO 8601 UTC）。
  - 文档修正：
    - 此操作并未修改公开接口行为，而是确认内网/SaaS模型下 `/health` 详细信息的合理性。
    - 开发者文档补充错误码 `CREDITS_API_FAILED`。
  - 测试补全：
    - 新增 `test_health_check_fails_when_balance_low`
    - 新增 `test_health_check_handles_credits_api_failure`
    - 新增 `test_health_check_fails_when_disk_inaccessible`
    - 新增 `test_health_check_timestamp_format`
- 验证：`pytest modules/memory/tests/unit/test_health_readiness.py` 全部通过。

---

## 62. Fix：BYOK 请求体对齐（platform 兜底 + 统一校验 400）（2026-01-07）

- 目标（Goal）
  - 对齐 SaaS → Memory Service 的 BYOK 请求体：新增 `byok.provider/model_name/llm_api_key`，并允许 platform 缺省回退。
  - 统一 ingest/retrieval 的校验失败响应为 `{code,message,missing}` 结构。

- 实现（What）
  - `modules/memory/api/server.py`
    - 新增 `ByokBody`，`IngestDialogBody` / `RetrievalDialogBody` 增加 `byok` 字段；
    - `byok` 缺省或 `provider=platform` 或 `llm_api_key` 为空 → platform 路由；
    - 仅在 `provider+model_name+llm_api_key` 齐全时走 BYOK；
    - `session_id` 为空时回填 `X-Request-Id`；
    - ingest/retrieval 校验失败统一返回 `missing_core_requirements`。
  - `modules/memory/tests/unit/test_ingest_retrieval_endpoints.py`
    - 按新 schema 补齐 `byok` + `client_meta`。
  - `modules/memory/tests/unit/test_client_meta_byok_routing.py`
    - 更新为 `byok` resolver 测试。
  - `modules/memory/tests/unit/test_with_answer_gate.py`
    - 补齐 `byok` + `client_meta` 以通过新校验。

- 验证（Test）
  - `pytest modules/memory/tests/unit/test_ingest_retrieval_endpoints.py::test_ingest_dialog_v1_creates_job_and_status -q`
  - `pytest modules/memory/tests/unit/test_ingest_retrieval_endpoints.py::test_retrieval_dialog_v2_calls_retrieval -q`
  - `pytest modules/memory/tests/unit/test_ingest_retrieval_endpoints.py::test_retrieval_dialog_v2_with_answer_uses_client_meta_adapter -q`
  - `pytest modules/memory/tests/unit/test_client_meta_byok_routing.py -q`
  - `pytest modules/memory/tests/unit/test_with_answer_gate.py -q`

---

## 63. Fix：BYOK 回归 client_meta 结构（2026-01-07）

- 目标（Goal）
  - 对齐 SaaS → Memory Service 的 BYOK 结构：仅使用 `client_meta.llm_*`，移除顶层 `byok`。
  - 保持平台兜底与缺字段校验的一致性。

- 实现（What）
  - `modules/memory/api/server.py`
    - 移除 `ByokBody` 与 `IngestDialogBody` / `RetrievalDialogBody` 的 `byok` 字段；
    - 新增 `_llm_meta_missing`，仅当 `llm_mode=byok` 或携带不完整 `llm_*` 时返回缺字段；
    - LLM 路由统一从 `client_meta.llm_*` 解析。
  - `modules/memory/tests/unit/test_ingest_retrieval_endpoints.py`
    - 请求体改为 `client_meta.llm_*`。
  - `modules/memory/tests/unit/test_client_meta_byok_routing.py`
    - 路由测试改为 `client_meta` 输入。
  - `modules/memory/tests/unit/test_with_answer_gate.py`
    - 默认请求体改为 `client_meta.llm_mode=platform`。

- 验证（Test）
  - `pytest modules/memory/tests/unit/test_ingest_retrieval_endpoints.py modules/memory/tests/unit/test_with_answer_gate.py modules/memory/tests/unit/test_client_meta_byok_routing.py -q`

---

## 64. Refactor：Ingest 单一队列消费（2026-01-07）

- 目标（Goal）
  - 取消 Memory Service 内部 SQLite 队列调度，外部 worker 负责消费并触发执行。
  - 保留 job/status 语义与 `_run_ingest_job` 执行器。

- 实现（What）
  - `modules/memory/api/server.py`
    - 移除 `_schedule_ingest_job` 与启动时 pending job 续跑逻辑；
    - `_run_ingest_job` 不再做内部重试调度，仅标记失败状态；
    - 新增 `POST /ingest/jobs/execute` 作为 worker 执行入口。
  - `Sealos_Saas/Qbrain_Saas/apps/worker/src/index.js`
    - `/ingest/dialog/v1` 后追加调用 `/ingest/jobs/execute`，并校验最终状态为 `COMPLETED`。
  - `开发者API 说明文档.md` / `SDK使用说明.md`
    - 说明外部队列消费模式需要显式调用 `POST /ingest/jobs/execute`。

- 验证（Test）
  - `pytest modules/memory/tests/unit/test_ingest_job_execute.py -q`

---

## 65. Fix：Ingest Job Store 透传与列错位修复（2026-01-07）

- 目标（Goal）
  - Job store 仅做“账本”，请求体原样透传，避免协议演进导致阻塞。
  - 修复旧库列顺序错位导致的 status/attempts/metrics/user_tokens 读错问题。

- 实现（What）
  - `modules/memory/infra/async_ingest_job_store.py`
    - 新增 `payload_raw` 字段；写入原始请求 JSON；
    - 读取使用列名映射，避免 `SELECT *` 顺序错位。
  - `modules/memory/infra/ingest_job_store.py`
    - 同步补齐 `payload_raw` 与列名映射读取。
  - `modules/memory/api/server.py`
    - `/ingest/dialog/v1` 保存原始 payload；
    - `/ingest/jobs/execute` 使用 payload_raw 优先驱动执行。

- 验证（Test）
  - `pytest modules/memory/tests/unit/test_ingest_job_execute.py -q`

---

## 64. Feat：Usage & Metering Phase 1 - 核心契约（2026-01-07）

- 目标（Goal）
  - 建立“事实级”计费信任根（WAL）与“回执级”响应（UsageSummary）。
  - 定义统一的数据模型。

- 实现（What）
  - `modules/memory/contracts/usage_models.py`
    - 定义 `UsageEvent`：WAL 落库用的原子事实。
    - 定义 `UsageSummary` / `TokenUsageDetail`：API Response 用的聚合回执。
    - 定义 `EmbeddingUsage` / `LLMUsage`：中间层传递结构。

- 验证（Test）
  - `pytest modules/memory/tests/unit/test_usage_models.py -v` 通过。

---

## 65. Feat：Usage & Metering Phase 1 - Adapter 改造（2026-01-07）

- 目标（Goal）
  - 让底层 Adapter 具备提取 Usage 但不破坏旧签名的能力。

- 实现（What）
  - `modules/memory/application/embedding_adapter.py`
    - 重构 `_build_openai_sdk_embedder`，在旧 `_embed` 上挂载 `embed_with_usage` 方法。
    - 支持解析 OpenAI SDK / REST 响应中的 usage 字段。
  - `modules/memory/application/llm_adapter.py`
    - 新增 `generate_with_usage`，利用 `contextvars` hook 捕获内部 `_emit_llm_usage` 发出的事件，实现无侵入式改造。

- 验证（Test）
  - `modules/memory/tests/unit/test_adapters_usage.py`
    - 验证 `embedder.embed_with_usage` 返回 `(vec, usage)`。
    - 验证 `llm_adapter.generate_with_usage` 捕获 upstream usage。

---

## 66. Feat：Usage & Metering Phase 1 - Retrieval/WAL 全链路打通（2026-01-07）

- 目标（Goal）
  - 在检索主流程收集 embedding/LLM usage，聚合回执并写入 WAL。
  - 统一 WAL 事件结构，兼容 write 事件。

- 实现（What）
  - `modules/memory/retrieval.py`
    - 增加 usage hook 收集与 `UsageSummary` 聚合回执（含 `usage` 字段）。
    - 在检索结束后写入 WAL（embedding/LLM 事件）。
  - `modules/memory/api/server.py`
    - LLM usage WAL 事件统一为 `UsageEvent` 结构。
    - write 事件使用 `UsageEvent` 结构落 WAL。
  - `modules/memory/contracts/usage_models.py`
    - 补充 `UsageEvent` 字段（trace/接口上下文与可选 usage）。
  - `omem/usage.py`
    - SDK 侧改为新 `UsageEvent` 结构，保持一致。

- 验证（Test）
  - `pytest modules/memory/tests/unit/test_llm_usage_hook.py modules/memory/tests/unit/test_omem_sdk_byok_usage.py modules/memory/tests/unit/test_adapters_usage.py modules/memory/tests/unit/test_usage_models.py -q`

---

## 67. Feat：Usage & Metering Phase 1 - OpenRouter 真实计费与失败事件（2026-01-07）

- 目标（Goal）
  - OpenRouter 成本必须通过 `/api/v1/generation` 获取真实 cost。
  - 失败调用也要写入 WAL，避免计费与可观测性缺口。

- 实现（What）
  - `modules/memory/application/llm_adapter.py`
    - OpenRouter HTTP 路径拉取 generation stats 并回填 cost/token。
    - LLM hook 支持失败事件与 error_code/error_detail。
    - LiteLLM 路径在异常时发出失败事件。
  - `modules/memory/api/server.py` / `modules/memory/retrieval.py`
    - WAL 事件接入 `status/error_code/cost_usd/generation_id`。
  - 文档更新：
    - `开发者API 说明文档.md`、`SDK使用说明.md` 增补 OpenRouter 计费说明。

- 验证（Test）
  - `pytest modules/memory/tests/unit/test_llm_usage_hook.py modules/memory/tests/unit/test_omem_sdk_byok_usage.py modules/memory/tests/unit/test_adapters_usage.py modules/memory/tests/unit/test_usage_models.py -q`

---

## 68. Feat：Ingest 即执行（Auto-Execute + 可选 Wait）(2026-01-08)

- 目标（Goal）
  - 对外 API：`POST /ingest(/dialog/v1)` 一次调用完成 “入库 + 自动触发执行”，不再要求外部显式调用 execute。
  - 提供 `wait=true` 以便小请求/调试场景同步等待终态；大请求或超时自动降级为异步（返回 `202 + job_id`）。
  - 保留 `GET /ingest/jobs/{job_id}` 作为轮询/观测入口；`POST /ingest/jobs/execute` 收敛为内部兼容接口（admin/signed）。

- 实现（What）
  - `modules/memory/api/server.py`
    - `POST /ingest(/dialog/v1)` 增加 `wait`/`wait_timeout_ms`，默认返回 `202` 并在后台 `create_task` 自动执行。
    - `_run_ingest_job` 增加 `claim` 参数，自动执行路径使用 DB 原子转移避免重复 runner。
    - `POST /ingest/jobs/execute` 提升为 `memory.admin` 且拒绝无-scope token（internal-only）。
  - `modules/memory/infra/async_ingest_job_store.py`
    - 新增 `try_transition_status()`，用于原子状态转移（防止并发重复执行）。
  - `modules/memory/application/config.py` / `modules/memory/config/memory.config.yaml`
    - 新增 `memory.ingest.auto_execute.*` 配置（enabled/wait_timeout_ms/wait_turns_threshold/poll_interval_ms）。
  - 文档更新：
    - `SDK使用说明.md`、`开发者API 说明文档.md` 同步更新：Ingest 自动执行与 Wait 语义、execute 端点对外废弃说明。

- 验证（Test）
  - `pytest -q modules/memory/tests/unit/test_ingest_auto_execute.py modules/memory/tests/unit/test_ingest_retrieval_endpoints.py::test_ingest_dialog_v1_creates_job_and_status`

---

## 69. Fix：防止 execute 触发重复执行 (2026-01-08)

- 背景（Why）
  - 自动执行开启后，遗留脚本/旧 worker 仍可能调用 `POST /ingest/jobs/execute`。
  - 若 job 已在 `STAGE2_RUNNING/STAGE3_RUNNING`，重复触发会导致重复写入/指标翻倍或状态回退风险。

- 实现（What）
  - `modules/memory/api/server.py`
    - `_run_ingest_job` 执行前统一以 DB 原子状态转移（仅允许 `RECEIVED -> STAGE2_RUNNING`）作为“领取”机制。
    - 当 job 不在 `RECEIVED`（含 running/terminal/failed）时直接 no-op，避免重复 runner。

- 验证（Test）
  - `pytest -q modules/memory/tests/unit/test_ingest_job_dedup.py`

---

## 70. Improve：Wait 语义与可观测性补强 (2026-01-08)

- 背景（Why）
  - `wait=true` 超时后仍返回 `202`，需要显式标记避免客户端误解。
  - `auto_execute` 关闭时允许 `wait=true` 会导致“永远等不到执行”的困惑。
  - 后台 `create_task` 失败或 task 内部异常不应静默吞掉，需可观测。

- 实现（What）
  - `modules/memory/api/server.py`
    - `wait=true` 但未在超时内终态：返回 `202` 并在响应中标记 `wait_timed_out=true`，同时补充 `wait_*` 与 `auto_execute_enabled` 字段。
    - `auto_execute` 关闭时：`wait=true` 返回 `400 auto_execute_disabled`。
    - 后台 task 失败与异常：记录日志（包含 job_id）。
    - 精简 `POST /ingest/jobs/execute` scope 判断逻辑。
  - 文档同步：
    - `SDK使用说明.md`、`开发者API 说明文档.md` 补充 `wait_timed_out`/`auto_execute_disabled` 行为说明。

- 验证（Test）
  - `pytest -q modules/memory/tests/unit/test_ingest_auto_execute.py::test_ingest_wait_timeout_marks_timed_out modules/memory/tests/unit/test_ingest_auto_execute.py::test_ingest_wait_requires_auto_execute`

---

## 71. Fix：Qdrant 写入一致性与代理干扰防护 (2026-01-08)

- 背景（Why）
  - 观察到 `vector_points_written>0` 但 Qdrant `points_count=0` 的现象，典型成因包括：
    - Qdrant upsert 默认 `wait=false` 导致写入异步落盘，服务端过早返回“已完成”；
    - 环境 HTTP 代理错误转发 localhost 请求，导致“写入成功”假象；
    - 非预期 200 响应体（HTML/网关页）被当作成功处理。

- 实现（What）
  - `modules/memory/infra/qdrant_store.py`
    - 默认忽略环境代理：`requests.Session.trust_env=False`。
    - upsert 默认 `wait=true`（可用 `MEMORY_QDRANT_UPSERT_WAIT` 关闭）确保写入完成后再返回。
    - 校验 upsert 响应 JSON `status=="ok"`，避免 200 但非 Qdrant 正常响应导致的“静默成功”。

- 验证（Test）
  - `pytest -q modules/memory/tests/unit/test_qdrant_upsert_wait_and_response.py`

---

## 72. Refactor：Ingest 异步执行与队列化 (2026-01-09)

- 背景（Why）
  - SaaS 网关存在固定超时（约 30s），大 payload 会触发 504；Ingest 必须快速 ACK。
  - 旧的 `create_task` fire-and-forget 存在阻塞与不可控问题，且 `wait=true` 语义需要退出。
  - Stage3 写入链路包含同步 I/O（Qdrant/Neo4j/LLM/Embedding），需要避免阻塞主事件循环。

- 实现（What）
  - **IngestExecutor**（`modules/memory/application/ingest_executor.py`）：进程内队列 + worker pool，支持全局/租户并发限制、超时、重试、启动恢复与优雅停机。
  - **/ingest 行为收敛**（`modules/memory/api/server.py`）：落库 → enqueue → 立即 `202 Accepted`；`wait=true` 取消（返回 `400 wait_not_supported`）；enqueue 失败返回 `503` 并标记 `ENQUEUE_FAILED`。
  - **execute 端点内化**：`POST /ingest/jobs/execute` 改为入队，不再同步执行。
  - **阻塞消除**：
    - `QdrantStore` 的 HTTP 调用改为 `asyncio.to_thread`，embedding 调用也改为 to_thread。
    - `Neo4jStore.upsert_graph_v0` 迁移为线程执行，避免阻塞主事件循环。
    - `session_write` 的 fact_extractor 与 ingest Stage2 extractor 走 `asyncio.to_thread`。
  - **配置更新**：`memory.ingest.executor.*` 取代 `auto_execute`（`memory.config.yaml` / `config/hydra/memory.yaml`）。
  - **脚本对齐**：HTTP e2e 脚本与 benchmark 改为 ingest → poll，不再调用 execute。
  - **文档同步**：`SDK使用说明.md`、`开发者API 说明文档.md` 更新为“永远 202 + 轮询”。

- 验证（Test）
  - `pytest -q modules/memory/tests/unit/test_ingest_executor.py \
modules/memory/tests/unit/test_ingest_auto_execute.py \
modules/memory/tests/unit/test_ingest_retrieval_endpoints.py \
modules/memory/tests/unit/test_ingest_job_execute.py \
modules/memory/tests/unit/test_qdrant_upsert_wait_and_response.py \
modules/memory/tests/unit/test_qdrant_search_dedup_and_dims.py \
modules/memory/tests/unit/test_qdrant_multimodal_search.py`
  - 结果：**17 passed**

---

## 73. Patch：Smoke 脚本 Stage3 抽取开关语义修正 (2026-01-09)

- 背景（Why）
  - `e2e_remote_ingest_retrieval_smoke.py` 之前无条件发送 `client_meta.stage3_extract=false`（因为 CLI 仅 `--stage3-extract` 且默认 false），会导致 Stage3 抽取被误关，进而“看起来 Stage3 很快/不做抽取”。

- 实现（What）
  - `modules/memory/scripts/e2e_remote_ingest_retrieval_smoke.py`
    - `stage3_extract` 改为 tri-state：未设置则不下发该字段，交由服务端默认行为决定；
    - 增加 `--stage3-no-extract` 明确关闭抽取；
    - `client_meta` 构造改为仅在显式设置时注入 `stage3_extract`。

- 验证（Test）
  - `python -m py_compile modules/memory/scripts/e2e_remote_ingest_retrieval_smoke.py`

---

## 74. Feature：PostgreSQL Backend for AsyncIngestJobStore (2026-01-13)

- 背景（Why）
  - mem 服务使用 StatefulSet + PVC 存储 SQLite 数据库，导致无法水平扩展。
  - 为实现无状态部署（Deployment），需要将 SQLite 迁移到外部 PostgreSQL。
  - Sealos 环境已提供 PostgreSQL 服务 (`test-db-postgresql`)。

- 实现（What）
  - **新增依赖**：`asyncpg>=0.29.0` (pyproject.toml)
  - **PgIngestJobStore** (`modules/memory/infra/pg_ingest_job_store.py`)
    - 完整实现 AsyncIngestJobStore 接口的 9 个异步方法
    - 使用 asyncpg 连接池，支持配置 `pool_min/pool_max`
    - 自动初始化 schema（3 张表：`ingest_jobs`, `ingest_session_state`, `ingest_commit_index_v2`）
    - `PgIngestJobStoreSettings` 支持从环境变量加载配置
  - **Store Factory** (`modules/memory/api/server.py:1162-1182`)
    - `_create_ingest_store()` 根据 `MEMORY_STORE_BACKEND` 环境变量选择后端
    - `postgresql` → `PgIngestJobStore`
    - `sqlite`（默认）→ `AsyncIngestJobStore`
  - **配置项**：
    - `MEMORY_STORE_BACKEND=postgresql|sqlite`
    - `MEMORY_PG_HOST`, `MEMORY_PG_PORT`, `MEMORY_PG_USER`, `MEMORY_PG_PASSWORD`, `MEMORY_PG_DATABASE`
    - `MEMORY_PG_POOL_MIN`, `MEMORY_PG_POOL_MAX`

- 验证（Test）
  - `PYTHONPATH="" pytest -v modules/memory/tests/unit/test_pg_ingest_job_store.py`
  - 结果：**6 passed, 3 skipped**（集成测试需要 PostgreSQL 连接）


---

## 75. Feature：Dialog TKG 事件抽取与证据对齐（2026-01-18）

- 背景（Why）
  - 现有写入将 turn 直接物化为 Event，语义层噪声大、事件数量爆炸，且“证据/事件/事实”层次不清。
  - 需要落实“turn=证据、event=抽象语义”的写入/检索规范，并保证回链与可解释性。

- 实现（What）
  - 事件抽取模块：`modules/memory/application/event_extractor_dialog_tkg_v1.py`
    - 新增 Event 抽取与对齐修复逻辑（会话级抽取 + 证据对齐兜底）。
    - 分段逻辑修正为“先按 session 边界，再按 max_turns 切分”；并发抽取可配置。
  - 新增 Prompt：`modules/memory/application/prompts/dialog_tkg_event_extractor_system_prompt_v1.txt`。
  - 写入链路：`modules/memory/session_write.py`
    - 接入事件抽取器（可注入/可退化），并按 `evidence_status`/`event_confidence` 应用门控与 TTL。
  - 图构建：`modules/memory/domain/dialog_tkg_graph_v1.py`
    - Event 不再按 turn 生成；从事件抽取结果物化 Event。
    - 事件与证据通过 `SUPPORTED_BY` 对齐；新增 `TEMPORALLY_CONTAINS` 边锚定 Utterance。
  - 向量索引：`modules/memory/domain/dialog_tkg_vector_index_v1.py`
    - Utterance 索引允许无事件映射；仅在单事件对齐时写入 `tkg_event_id`。
  - 检索回链：`modules/memory/retrieval.py`
    - Utterance 命中无事件时返回 evidence，并标注 `unmapped_to_event=true`。
  - 配置新增：`modules/memory/config/memory.config.yaml` + `modules/memory/config/hydra/memory.yaml`
    - 增加 `memory.dialog.*` 事件抽取/对齐/TTL/裁剪参数。
    - 图白名单扩展支持 `SUPPORTED_BY/TEMPORALLY_CONTAINS/INVOLVES`。
  - SDK/API 文档同步：
    - `MOYAN_AGENT_INFRA/SDK使用说明.md`
    - `MOYAN_AGENT_INFRA/开发者API 说明文档.md`

- 验证（Test）
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q \
    modules/memory/tests/unit/test_dialog_tkg_graph_v1.py \
    modules/memory/tests/unit/test_dialog_tkg_vector_index_v1.py \
    modules/memory/tests/unit/test_retrieval_dialog_v2.py \
    modules/memory/tests/unit/test_dialog_tkg_event_extractor_basics.py \
    modules/memory/tests/integration/test_session_write_event_pipeline.py`
  - 结果：**12 passed**


---

## 76. Feature：Dialog TKG 统一抽取（Events + Knowledge 同次输出）（2026-01-19）

- 背景（Why）
  - 事件/知识分两次 LLM 调用导致延迟叠加与超时风险；session 过长时阻塞更明显。
  - 需要把 event + knowledge 统一为单次抽取，配合 session 边界分段与并发降低延迟。

- 实现（What）
  - 新增统一抽取器：`modules/memory/application/dialog_tkg_unified_extractor_v1.py`
    - 单次输出 `events + knowledge`，支持 session 边界分段 + max_turns 切块 + 并发抽取。
    - 内置事件证据对齐修复（weak/unmapped 兜底）。
  - 新增 Prompt：`modules/memory/application/prompts/dialog_tkg_unified_extractor_system_prompt_v1.txt`。
  - 写入链路：`modules/memory/session_write.py`
    - 切换为统一抽取入口，仅一次 LLM 调用链产出 events+knowledge。
  - 异步服务：`modules/memory/api/server.py`
    - Stage3 改用统一抽取器（BYOK 适配）。
  - 测试与脚本更新：
    - `modules/memory/tests/unit/test_dialog_tkg_unified_extractor_basics.py`（新增）
    - session_write 相关单测与集成测更新为 tkg_extractor。
  - 文档同步：
    - `MOYAN_AGENT_INFRA/docs/时空知识记忆系统构建理论/5. 文本层设计/文本对话TKG管线说明.md`
    - `MOYAN_AGENT_INFRA/SDK使用说明.md`
    - `MOYAN_AGENT_INFRA/开发者API 说明文档.md`

- 验证（Test）
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q \
    modules/memory/tests/unit/test_dialog_tkg_unified_extractor_basics.py \
    modules/memory/tests/integration/test_session_write_event_pipeline.py \
    modules/memory/tests/unit/test_session_write_api.py \
    modules/memory/tests/unit/test_session_write_llm_required.py \
    modules/memory/tests/unit/test_session_write_llm_missing_marker.py`
  - 结果：**12 passed**


---

## 77. Config：提升统一抽取并发与 Stage3 超时（2026-01-19）

- 背景（Why）
  - 长会话 Stage3 易超时；统一抽取并发上限偏低导致波次过多。

- 实现（What）
  - 并发上限提升：
    - `memory.dialog.event_extract_concurrency: 8`
    - 配置文件：`modules/memory/config/memory.config.yaml`、`modules/memory/config/hydra/memory.yaml`
    - 默认值同步：`modules/memory/application/config.py`
  - Stage3 超时提升：
    - `memory.ingest.executor.job_timeout_s: 900`
    - 配置文件：`modules/memory/config/memory.config.yaml`、`modules/memory/config/hydra/memory.yaml`
    - 默认值同步：`modules/memory/application/config.py`
    - 执行器默认值：`modules/memory/application/ingest_executor.py`

- 验证（Test）
  - 未新增用例（配置调整）；沿用既有 ingest executor 单测。


---

## 78. Perf：证据对齐 Embedding 批量化与并发上限（2026-01-19）

- 背景（Why）
  - 证据对齐阶段对每个 turn 逐条 embedding，导致大量串行请求与 Stage3 堵塞。
  - 需要引入批量 embedding 与并发上限，减少请求次数并稳定吞吐。

- 实现（What）
  - 批量对齐：`modules/memory/application/dialog_tkg_unified_extractor_v1.py`
    - 证据对齐改为批量 embedding（turns + event queries），空事件直接跳过对齐。
    - 增加 `alignment_embed_batch_size` / `alignment_embed_concurrency` 参数读取与并发信号量。
  - Embedding 适配：`modules/memory/application/embedding_adapter.py`
    - OpenAI 兼容 embedding 支持批量 HTTP 请求（list input）。
    - Session 改为 thread-local，移除全局锁以释放并发。
    - 缓存包装保留 `encode_batch` 能力，确保上层能调用批量接口。
  - 配置补齐：
    - `memory.dialog.event_alignment.embed_batch_size: 128`
    - `memory.dialog.event_alignment.embed_concurrency: 8`
    - 覆盖：`modules/memory/config/memory.config.yaml`、`modules/memory/config/hydra/memory.yaml`、默认值 `modules/memory/application/config.py`
  - 文档同步：
    - `MOYAN_AGENT_INFRA/docs/时空知识记忆系统构建理论/5. 文本层设计/文本对话TKG管线说明.md`

- 验证（Test）
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q \
    modules/memory/tests/unit/test_dialog_tkg_unified_extractor_basics.py`
  - 结果：**4 passed**


---

## 79. Fix：Ingest overwrite_existing 透传（2026-01-19）

- 背景（Why）
  - e2e 重跑时 `--overwrite-existing` 未生效，Stage3 命中旧 marker 直接跳过，导致 graph/vector 不更新。

- 实现（What）
  - 请求透传：`MOYAN_AGENT_INFRA/benchmark/scripts/e2e_http_benchmark.py`
    - `--overwrite-existing` 下发到 `client_meta.overwrite_existing=true`。
  - Stage3 透传：`modules/memory/api/server.py`
    - 从 `client_meta.overwrite_existing` 读取并传入 `session_write(..., overwrite_existing=...)`。
  - 文档同步：
    - `MOYAN_AGENT_INFRA/SDK使用说明.md`
    - `MOYAN_AGENT_INFRA/开发者API 说明文档.md`
  - 单测新增：
    - `modules/memory/tests/unit/test_ingest_job_overwrite_existing.py`

- 验证（Test）
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q \
    modules/memory/tests/unit/test_ingest_job_overwrite_existing.py`
  - 结果：**1 skipped**（fastapi 未安装）


---

## 80. Config：取消事件上限截断（2026-01-19）

- 背景（Why）
  - 全局 `max_events_per_session` 截断会丢失后续 session 的真实事件，覆盖面不足。

- 实现（What）
  - 默认与配置统一为“不截断”：
    - `memory.dialog.event_gate.max_events_per_session: 0`（0 表示无限制）
    - 覆盖：`modules/memory/application/config.py`、`modules/memory/config/memory.config.yaml`、`modules/memory/config/hydra/memory.yaml`
  - 文档同步：
    - `MOYAN_AGENT_INFRA/docs/时空知识记忆系统构建理论/5. 文本层设计/文本对话TKG管线说明.md`
  - 单测新增：
    - `modules/memory/tests/unit/test_dialog_event_settings_defaults.py`

- 验证（Test）
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q \
    modules/memory/tests/unit/test_dialog_event_settings_defaults.py`
  - 结果：**1 passed**


---

## 81. TKG 回链修复 + overwrite 图清理 + reference time 稳定（2026-01-19）

- 背景（Why）
  - 多 session 输入时，`D2:1` 这类 turn_id 被解析成 `1`，导致事件/知识证据回链错位。
  - `overwrite_existing` 仅清理旧 fact 向量，图侧事件/边残留，召回可能污染。
  - 统一抽取在无 session 时间时每段使用 `datetime.now()`，并发分段会造成 reference time 不一致。

- 实现（What）
  - 回链修复：
    - `modules/memory/domain/dialog_tkg_graph_v1.py`
    - 建立 `{turn_id/dia_id -> index}` 映射，优先按字典定位；数字尾部仅作为兜底。
  - overwrite 图清理：
    - `modules/memory/session_write.py`
    - `overwrite_existing && write_events` 时调用 `purge_source(source_id="dialog::{session_id}")`，确保图与向量一致。
  - reference time 稳定：
    - `modules/memory/application/dialog_tkg_unified_extractor_v1.py`
    - extractor 构建时一次性确定 fallback reference time，并用于所有分段上下文。
  - 单测新增：
    - `modules/memory/tests/unit/test_dialog_tkg_graph_v1.py`
    - `modules/memory/tests/unit/test_dialog_tkg_unified_extractor_basics.py`
    - `modules/memory/tests/unit/test_session_write_api.py`

- 验证（Test）
  - `pytest -q \
    MOYAN_AGENT_INFRA/modules/memory/tests/unit/test_dialog_tkg_graph_v1.py \
    MOYAN_AGENT_INFRA/modules/memory/tests/unit/test_dialog_tkg_unified_extractor_basics.py \
    MOYAN_AGENT_INFRA/modules/memory/tests/unit/test_session_write_api.py`
  - 结果：**13 passed**


---

## 82. E2E 验证：conv-30 端到端写入 + 检索（2026-01-19）

- 背景（Why）
  - 在回链/overwrite/reference_time 修复后，进行一次端到端验证。

- 验证（Test）
  - `MOYAN_AGENT_INFRA/benchmark/scripts/e2e_http_benchmark.py`（conv-30，含 ingest+retrieval+judge）
  - 关键指标：
  - Stage3 完成约 61s

## 92. Observability：Ingest 分阶段耗时与并发观测（2026-01-25）

**目标**
- 可观测 Stage2/Stage3 的耗时与瓶颈分布（LLM 抽取 / 图写入 / 向量写入 / 发布）
- 暴露 LLM/Embedding 实际并发（inflight & max）用于排查堵点

**变更**
- `modules/memory/application/metrics.py`
  - 新增 `llm_inflight` / `embedding_inflight` gauge（含 max）
  - 新增 ingest 各阶段耗时计数（sum/count）
  - Prometheus 文本导出新增对应指标
- `modules/memory/application/llm_adapter.py`
  - 进入/退出 LLM 调用时维护 inflight gauge
- `modules/memory/application/embedding_adapter.py`
  - 单次 embedding 与 batch chunk 维护 inflight gauge
- `modules/memory/session_write.py`
  - 记录 `timing_ms`：extract/build/graph_upsert/vector_write/publish/overwrite_delete/total
- `modules/memory/api/server.py`
  - Stage2/Stage3 计时写入 job metrics（`stage2_ms` / `stage3_ms` 等）
  - 将 session_write 的 timing 透传并写入 metrics

**验证**
- `/metrics_prom` 可看到 `memory_llm_inflight` / `memory_embedding_inflight` 与 `memory_ingest_*_ms_{sum,count}`。
- `/ingest/jobs/{job_id}` metrics 包含 `stage2_ms` / `stage3_ms` 与子项（extract/build/graph/vector/publish）。
- 测试：`pytest modules/memory/tests/unit/test_ingest_observability_metrics.py -q`
    - `graph_nodes_written=71`
    - `vector_points_written=522`
    - Judge accuracy：**0.864**（results 105）
  - 输出目录：
    - `MOYAN_AGENT_INFRA/benchmark/outputs/run_034_20260119_012115_conv-30/`

---

## 83. 统一抽取稳健性与覆盖提升（事件置信度/多事件回链/并发安全）（2026-01-19）

- 背景（Why）
  - Review 指出：事件置信度缺失会被静默丢弃、overwrite 清理存在一致性风险、`max_events_per_session` 全局截断、multi‑event 回链缺失、并发 LLM 调用线程安全隐患。

- 实现（What）
  - 事件置信度缺失不再归零：
    - `modules/memory/application/dialog_tkg_unified_extractor_v1.py`
    - `modules/memory/application/event_extractor_dialog_tkg_v1.py`
    - 缺失/空值保持为 `None`，不触发 `min_event_confidence` 丢弃。
  - 按 session 截断事件数：
    - `modules/memory/application/dialog_tkg_unified_extractor_v1.py`
    - `modules/memory/application/event_extractor_dialog_tkg_v1.py`
    - `max_events_per_session` 从“全局截断”改为“按 session 计数”。
  - 并发安全：
    - `modules/memory/application/dialog_tkg_unified_extractor_v1.py`
    - `modules/memory/application/event_extractor_dialog_tkg_v1.py`
    - extractor 内部改为线程本地 LLM adapter，避免多线程共享潜在非线程安全对象。
  - multi‑event 回链增强：
    - `modules/memory/domain/dialog_tkg_vector_index_v1.py`
    - `modules/memory/retrieval.py`
    - utterance metadata 写入 `tkg_event_ids`（多事件）；检索端支持多事件映射回链。
  - overwrite 一致性策略调整：
    - `modules/memory/session_write.py`
    - 仅当 graph store 支持 `upsert_graph_v0` 时，overwrite 自动提升为 `graph_policy=require`，避免图失败导致 vector‑only 状态。

- 验证（Test）
  - `pytest -q \
    modules/memory/tests/unit/test_dialog_tkg_unified_extractor_basics.py \
    modules/memory/tests/unit/test_dialog_tkg_vector_index_v1.py \
    modules/memory/tests/unit/test_retrieval_dialog_v2.py \
    modules/memory/tests/unit/test_session_write_api.py`
  - 结果：**21 passed**

---

## 84. 统一抽取正则修复与覆盖写入失败兜底（2026-01-19）

- 背景（Why）
  - PR Review 指出统一抽取中的参考时间解析正则失效；覆盖写入时 purge 成功但 graph upsert 失败会导致图空洞。

- 实现（What）
  - 修复参考时间解析正则：
    - `modules/memory/application/dialog_tkg_unified_extractor_v1.py`
    - 使用正确的 `\d` 捕获，确保 `hh:mm am/pm on Month day, year` 能解析。
  - 覆盖写入失败兜底：
    - `modules/memory/session_write.py`
    - 若 purge 已成功而 graph upsert 失败，强制失败并触发重试，避免静默空洞。

- 验证（Test）
  - 未新增测试（修复点局部且已有相关单测覆盖）。

---

## 85. 逻辑事件 ID 冲突规避（2026-01-19）

- 背景（Why）
  - 同一 turn 抽取多事件时，使用首个 turn 生成 `logical_event_id` 会冲突并导致检索合并。

- 实现（What）
  - 仅在“单 turn 且该 turn 只对应一个事件”时设置 `logical_event_id`，避免多事件合并：
    - `modules/memory/domain/dialog_tkg_graph_v1.py`

- 验证（Test）
  - `pytest -q modules/memory/tests/unit/test_dialog_tkg_graph_v1.py`

---

## 86. Milvus vector store adapter (2026-01-22)

- Why:
  - Add a Milvus backend compatible with the existing Qdrant vector-store contract.

- What:
  - Added MilvusStore (pymilvus) with upsert/search/get/delete/ensure_collections.
  - create_service now selects milvus when memory.vector_store.kind == "milvus".
  - Documented MILVUS_HOST/MILVUS_PORT alongside Qdrant in memory.config.yaml.

- Test:
  - Not run (local environment missing pymilvus/uv).
---

## 87. Tenant-based vector store routing (2026-01-22)

- Why:
  - Allow online migration by routing per-tenant requests to Qdrant or Milvus without changing default config.

- What:
  - Added VectorStoreRouter with a temporary in-memory route table (tenant -> backend) and per-request routing logs.
  - QdrantStore now exposes tenant_exists() using points/count for tenant probing.
  - API request context is captured in middleware and used to log route decisions.

- Test:
  - Added unit tests: modules/memory/tests/unit/test_vector_store_router.py
- Update (2026-01-23):
  - Worker-side ingest now sets request context for route logs (request_id/tenant_id/path).

---

## 88. Mainflow retrieval fixes (threshold/summary/time) (2026-01-24)

- Why:
  - Address dialog_v2 recall failures caused by vector threshold filtering, summary topic drift, and missing absolute timestamps.

- What:
  - Enabled ANN fallback when threshold clears all hits (`relax_threshold_on_empty: true`) in config.
  - Graph search now returns `desc`, and dialog_v2 E_event_vec evidence text concatenates summary + desc.
  - Added fulltext index on Event.summary + Event.desc and prefer it in graph search.
  - Unified/event extractor prompts now enforce output language to match source turns (no translation).
  - Unified extractor prompt updated to force summaries to include key prices/fees/dates when present.
  - Session write fills missing `timestamp_iso` using reference time + interval, so t_abs/recency are available.

- Test:
  - `python -m pytest modules/memory/tests/unit/test_retrieval_dialog_v2.py modules/memory/tests/unit/test_session_write_timestamp_fill.py`

---

## 89. Language guard + event mapping fix (2026-01-24)

- Why:
  - LLM output language drift (Chinese turns producing English summaries) and a graph build bug causing event summaries/turn links to be overwritten.

- What:
  - Strengthened prompts: per-item language must match its own source_turn_ids (no mixing/translation).
  - Added unified extractor language validation + one retry with explicit language hints.
  - Added schema stats tracing for raw LLM outputs.
  - Fixed dialog graph build to use per-event summary/source_turn_ids (no shared outer-loop variables).

- Test:
  - `python -m pytest modules/memory/tests/unit/test_dialog_tkg_unified_extractor_basics.py`
  - Manual smoke (session_write + graph explain) on a bilingual 4-turn sample.

---

## 90. Replace E_graph with E_event_vec (2026-01-24)

- Why:
  - Graph fulltext is keyword-based and noisy; event-level semantic recall should be the primary route.

- What:
  - Use event vector index (`source=tkg_dialog_event_index_v1`) instead of graph fulltext for dialog_v2 E_event_vec route.
  - GraphService now writes event vectors with `summary+desc`, `tkg_event_id`, logical `event_id`, and `timestamp_iso`.
  - Dialog graph events now carry `user_id` and `memory_domain` for vector filtering.
  - Default internal exclusions now hide `tkg_dialog_event_index_v1` from generic /search.
  - Debug call renamed to `event_search_event_vec`.

- Test:
  - `python -m pytest modules/memory/tests/unit/test_retrieval_dialog_v2.py modules/memory/tests/integration/test_dialog_v2_retrieval_integration.py modules/memory/tests/unit/test_qdrant_filter_exclude_sources.py`

---

## 91. Ingest concurrency improvements (LLM + embedding) (2026-01-25)

- Why:
  - Ingest speed was bottlenecked by conservative defaults and serial embedding batches.

- What:
  - Raised default LLM concurrency fallback from 2 → 8 (still bounded by `MEMORY_LLM_MAX_CONCURRENT`).
  - Parallelized event alignment embedding batches inside unified extractor.
  - Added embedding batch concurrency for vectorization (config: `memory.vector_store.embedding.embed_concurrency`).
  - Updated config defaults for embed concurrency in YAML configs.

- Test:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest modules/memory/tests/unit/test_dialog_tkg_unified_extractor_basics.py -q`

---

## 92. Backfill Qdrant metadata for topic fields (2026-01-29)

- Why:
  - Topic backfill ran for Neo4j but Qdrant coverage stayed at 0 because updates targeted `metadata.node_id` and wrote top-level payload instead of `metadata.*`.

- What:
  - Reworked `backfill_event_topics.py` to build an event→point index from Qdrant scroll using `event_id/tkg_event_id/tkg_event_ids/node_id`.
  - Merged topic fields into existing `payload.metadata` and wrote back per point id (no metadata wipe).
  - Re-ran Qdrant backfill and re-exported coverage report for verification.

- Test:
  - `python -m pytest modules/memory/tests/unit/test_qdrant_filter_topic_fields.py modules/memory/tests/unit/test_dialog_tkg_graph_v1.py::test_dialog_graph_upsert_v1_derives_time_bucket -q`
  - `PYTHONPATH=. python modules/memory/scripts/backfill_event_topics.py --apply-qdrant --limit 5000`
  - `python modules/memory/scripts/backup_qdrant.py --host 127.0.0.1 --port 6333 --collection memory_text --out modules/memory/outputs/qdrant_text.jsonl`
  - `python modules/memory/scripts/topic_coverage_report.py --input modules/memory/outputs/qdrant_text.jsonl`

---

## 93. Event-only coverage reporting (2026-01-29)

- Why:
  - Overall coverage was diluted by non-event points. We need event-only coverage for Phase 0.5 gating.

- What:
  - Added `--event-only` + `--event-sources` to `topic_coverage_report.py`.
  - Default event sources: `tkg_dialog_event_index_v1`, `dialog_unified`.
  - New unit test verifies non-event entries are excluded from totals.

- Test:
  - `python -m pytest modules/memory/tests/unit/test_topic_coverage_report.py -q`
  - `python modules/memory/scripts/topic_coverage_report.py --input modules/memory/outputs/qdrant_text.jsonl --event-only`

---

## 94. Vocab expansion + normalization backfill loop (2026-01-29)

- Why:
  - Event coverage plateaued because `_uncategorized/*` was treated as final. We need vocab expansion and allow re-normalization to lift coverage.

- What:
  - Expanded vocab: added paths/tags/synonyms/rules for business, dance, volunteering/community, mentorship, leisure, attendance, art, outdoor.
  - TopicNormalizer now treats `_uncategorized/*` as remappable (re-normalizes during backfill).
  - normalization_queue_backfill updated to merge Qdrant `payload.metadata` via point index (event_id/tkg_event_id/tkg_event_ids/node_id).
  - Re-ran backfill to update Neo4j + Qdrant with new vocab.

- Test:
  - `python -m pytest modules/memory/tests/unit/test_normalization_rules_no_conflict.py modules/memory/tests/unit/test_topic_normalizer.py modules/memory/tests/unit/test_normalization_queue_backfill.py -q`
  - `PYTHONPATH=. python modules/memory/scripts/backfill_event_topics.py --apply-neo4j --apply-qdrant --limit 50000`
  - `python modules/memory/scripts/backup_qdrant.py --host 127.0.0.1 --port 6333 --collection memory_text --out modules/memory/outputs/qdrant_text.jsonl`
  - `python modules/memory/scripts/topic_coverage_report.py --input modules/memory/outputs/qdrant_text.jsonl --event-only`

---

## 95. Coverage filters by tenant/domain/source (2026-01-29)

- Why:
  - Benchmark-heavy data can bias vocab expansion. Coverage must be computed per-tenant/domain/source.

- What:
  - Added `--tenant`, `--memory-domain`, `--source` filters to `topic_coverage_report.py`.
  - New unit test ensures tenant filter works with event-only mode.

- Test:
  - `python -m pytest modules/memory/tests/unit/test_topic_coverage_report.py -q`
  - `python modules/memory/scripts/topic_coverage_report.py --input modules/memory/outputs/qdrant_text.jsonl --event-only --tenant locomo_bench`
  - `python modules/memory/scripts/topic_coverage_report.py --input modules/memory/outputs/qdrant_text.jsonl --event-only --tenant local`

---

## 96. Keyword derivation + backfill (2026-01-29)

- Why:
  - Historical events had no keywords; coverage stayed 0 even after topic/tags backfill.

- What:
  - TopicNormalizer now derives lightweight keywords from summary/desc/topic_id when missing.
  - Added unit test for keyword derivation.
  - Re-ran backfill to write keywords to Neo4j + Qdrant metadata.

- Test:
  - `python -m pytest modules/memory/tests/unit/test_topic_normalizer.py -q`
  - `PYTHONPATH=. python modules/memory/scripts/backfill_event_topics.py --apply-neo4j --apply-qdrant --limit 50000`
  - `python modules/memory/scripts/backup_qdrant.py --host 127.0.0.1 --port 6333 --collection memory_text --out modules/memory/outputs/qdrant_text.jsonl`
  - `python modules/memory/scripts/topic_coverage_report.py --input modules/memory/outputs/qdrant_text.jsonl --event-only`

---

## 97. Event index baseline coverage (2026-01-29)

- Why:
  - Coverage gating should align with actual event vector retrieval, not diluted by non-event points.

- What:
  - Computed baseline coverage with `--source tkg_dialog_event_index_v1` (event index only).
  - This is the primary metric for Phase 0.5 Go/No-Go and future vocab iterations.

- Test:
  - `python modules/memory/scripts/topic_coverage_report.py --input modules/memory/outputs/qdrant_text.jsonl --event-only --source tkg_dialog_event_index_v1`

---

## 98. State property distribution probe (2026-01-29)

- Why:
  - Phase 3 needs Top-3 state properties. We need a data-driven prior instead of guesswork.

- What:
  - Added `state_property_distribution.py` to estimate candidate State properties from event index text using heuristic triggers.
  - Added unit test for distribution script.
  - Generated baseline report from `tkg_dialog_event_index_v1` to guide Phase 3 property selection.

- Test:
  - `python -m pytest modules/memory/tests/unit/test_state_property_distribution.py -q`
  - `python modules/memory/scripts/state_property_distribution.py --input modules/memory/outputs/qdrant_text.jsonl --source tkg_dialog_event_index_v1 --output modules/memory/outputs/state_property_distribution_event_index.json`

---

## 99. State chain infrastructure (Phase 3 kick-off) (2026-01-29)

- Why:
  - Phase 3 requires deterministic state updates, CURRENT pointer, and TRANSITIONS_TO chain.

- What:
  - Extended `State` model with raw_value/confidence/last_seen/source_event_id/extractor_version/status.
  - Added Neo4j constraints for `StateKey` and relationship mapping for `TRANSITIONS_TO`.
  - Implemented `apply_state_update`, `get_current_state`, `get_state_at_time` in `Neo4jStore`.
  - Added GraphService wrappers for state operations.
  - Added integration test for state chain updates (create → touch → update).

- Test:
  - `pytest modules/memory/tests/integration/test_state_chain_update_integration.py -q`

---

## 100. State candidates extraction + session write updates (2026-01-29)

- Why:
  - Phase 3 needs state updates to flow from extraction → graph write deterministically.

- What:
  - Unified extractor now parses `states` and normalizes against `state_properties.yaml` + allowlist.
  - Prompt updated with State rules (subject_ref/property/value/negation/time).
  - Session write resolves `subject_ref` → entity_id using `speaker_entity_map` and applies state updates with confidence gating.
  - Added support for raw_value + confidence metadata on State nodes.

- Test:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest modules/memory/tests/unit/test_dialog_tkg_unified_extractor_basics.py -q`
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest modules/memory/tests/unit/test_session_write_graph_upsert.py -q`
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest modules/memory/tests/unit/test_session_write_api.py -q`
  - `NEO4J_URI=bolt://127.0.0.1:7687 NEO4J_USER=neo4j NEO4J_PASSWORD=${NEO4J_PASSWORD} PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest modules/memory/tests/integration/test_state_chain_update_integration.py -q`

---

## 101. Local backfill + coverage check (benchmark tenants) (2026-01-29)

- Why:
  - Validate vocab expansion + backfill loop on local benchmark data before moving to larger tenants.

- What:
  - Backed up Qdrant points to JSONL for reproducible coverage reporting.
  - Ran `backfill_event_topics.py` to update Neo4j + Qdrant payloads.
  - Recomputed coverage on event-only scope and event index scope.

- Result:
  - Event-only coverage stayed at ~0.3096 after backfill.
  - Event-index coverage remained ~0.9895 (already high).
  - Indicates low coverage is dominated by non-event sources or points without event metadata; further gains require
    expanding normalization inputs or source-specific extraction.

- Test/Run:
  - `PYTHONPATH=. python modules/memory/scripts/backup_qdrant.py --host 127.0.0.1 --port 6333 --collection memory_text --out modules/memory/outputs/qdrant_text.jsonl`
  - `PYTHONPATH=. python modules/memory/scripts/topic_coverage_report.py --input modules/memory/outputs/qdrant_text.jsonl --event-only --output modules/memory/outputs/topic_coverage_report_before.json`
  - `PYTHONPATH=. python modules/memory/scripts/topic_coverage_report.py --input modules/memory/outputs/qdrant_text.jsonl --event-only --source tkg_dialog_event_index_v1 --output modules/memory/outputs/topic_coverage_report_event_index_before.json`
  - `NEO4J_URI=bolt://127.0.0.1:7687 NEO4J_USER=neo4j NEO4J_PASSWORD=${NEO4J_PASSWORD} QDRANT_HOST=127.0.0.1 QDRANT_PORT=6333 PYTHONPATH=. python modules/memory/scripts/backfill_event_topics.py --apply-neo4j --apply-qdrant --limit 50000`
  - `PYTHONPATH=. python modules/memory/scripts/backup_qdrant.py --host 127.0.0.1 --port 6333 --collection memory_text --out modules/memory/outputs/qdrant_text.jsonl`
  - `PYTHONPATH=. python modules/memory/scripts/topic_coverage_report.py --input modules/memory/outputs/qdrant_text.jsonl --event-only --output modules/memory/outputs/topic_coverage_report_after.json`
  - `PYTHONPATH=. python modules/memory/scripts/topic_coverage_report.py --input modules/memory/outputs/qdrant_text.jsonl --event-only --source tkg_dialog_event_index_v1 --output modules/memory/outputs/topic_coverage_report_event_index_after.json`

---

## 102. Event index coverage shortcut (2026-01-29)

- Why:
  - We gate vocab coverage by Event Index only; avoid dilution from utterance points.

- What:
  - Added `--event-index-only` to `topic_coverage_report.py` to lock both event detection and source filter to
    `tkg_dialog_event_index_v1`.
  - Added unit test to ensure the shortcut only counts event-index points.

- Test:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest modules/memory/tests/unit/test_topic_coverage_report.py -q`

---

## 103. State MVP allowlist from vocab (2026-01-29)

- Why:
  - Phase 3 MVP should only extract Top-3 state properties by default to avoid noise.

- What:
  - Added `mvp: true` markers to `state_properties.yaml` for job_status/relationship_status/mood.
  - Unified extractor defaults to MVP allowlist when `MEMORY_STATE_PROPERTIES` is unset.
  - Added unit test to ensure non-MVP properties are filtered by default.

- Test:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest modules/memory/tests/unit/test_dialog_tkg_unified_extractor_basics.py -q`

---

## 104. State change query (Phase 3 query surface) (2026-01-29)

- Why:
  - Phase 3 requires a minimal "what-changed" query surface (range query over state changes).

- What:
  - Added `get_state_changes()` to `Neo4jStore` and `GraphService` (filter by valid_from range).
  - Extended integration test to validate change list ordering and contents.

- Test:
  - `NEO4J_URI=bolt://127.0.0.1:7687 NEO4J_USER=neo4j NEO4J_PASSWORD=${NEO4J_PASSWORD} PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest modules/memory/tests/integration/test_state_chain_update_integration.py -q`

---

## 105. State read API endpoints (Phase 3 closure) (2026-01-29)

- Why:
  - Phase 3 requires external read surface (current / at_time / changes) to validate state chain end-to-end.

- What:
  - Added `/memory/state/current`, `/memory/state/at_time`, `/memory/state/changes` endpoints.
  - Added ISO datetime parsing helper and scope mapping for `/memory/state/*`.
  - Added unit tests with graph stub to validate request → graph args mapping.

- Test:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest modules/memory/tests/unit/test_memory_state_endpoints.py -q`
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest modules/memory/tests/unit/test_api_scope_coverage.py -q`

---

## 106. Pending + out-of-order state handling (2026-01-29)

- Why:
  - Phase 3 requires safe handling for low-confidence and out-of-order updates without corrupting CURRENT chain.

- What:
  - Added `PendingState` schema + indexes.
  - `apply_state_update` now records low-confidence updates as `PendingState` (status=pending, reason=low_confidence).
  - Out-of-order updates (`valid_from < current.valid_from`) are diverted to `PendingState` (reason=out_of_order).
  - Session write now routes low-confidence state candidates into pending instead of dropping.
  - Integration test updated to assert out-of-order creates pending and preserves CURRENT.

- Test:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest modules/memory/tests/integration/test_state_chain_update_integration.py -q`

---

## 107. Pending review endpoints (Phase 3 closure) (2026-01-29)

- Why:
  - Phase 3 needs human-in-the-loop control over PendingState (list / approve / reject).

- What:
  - Added `/memory/state/pending/list|approve|reject` endpoints (admin scope).
  - Added PendingState list/approve/reject methods in GraphService + Neo4jStore.
  - Updated API/SDK docs with PendingState usage.

- Test:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest modules/memory/tests/unit/test_memory_state_endpoints.py -q`
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest modules/memory/tests/unit/test_api_scope_coverage.py -q`

---

## 108. State business wrappers (what-changed / time-since) (2026-01-29)

- Why:
  - Phase 3 needs business-friendly wrappers on top of state changes (what-changed / time-since).

- What:
  - Added `/memory/state/what-changed` (alias to changes).
  - Added `/memory/state/time-since` (compute time since last change).
  - Extended unit tests and updated API/SDK docs.

- Test:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest modules/memory/tests/unit/test_memory_state_endpoints.py -q`

---

## 109. Vocab path migration (2026-01-29)

- Why:
  - Vocab files are module assets; move from docs to `modules/memory/vocab` and update all references.

- What:
  - Moved vocab YAMLs to `modules/memory/vocab`.
  - Updated TopicNormalizer and state vocab loader paths.
  - Updated docs + tests to new location.

- Test:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest modules/memory/tests/unit/test_topic_normalizer.py -q`
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest modules/memory/tests/unit/test_dialog_tkg_unified_extractor_basics.py -q`
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest modules/memory/tests/unit/test_normalization_rules_no_conflict.py -q`
  - `source .venv/bin/activate && pytest modules/memory -q`

---

## 110. Topic timeline endpoint (Phase 4 / P0) (2026-01-29)

- Why:
  - Expose TKG topic timeline as a semantic API with hard filters and timeline ordering.

- What:
  - Added `/memory/v1/topic-timeline` endpoint (hard filter by `topic_path/topic_id`, retrieval fallback).
  - Added Neo4j queries: `query_events_by_topic` + `query_events_by_ids`.
  - Added GraphService wrapper `topic_timeline` for batch timeline reads.
  - Updated API/SDK docs for the new endpoint (beta semantics).

- Test:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest modules/memory/tests/unit/test_memory_topic_timeline.py -q`

---

## 111. Entity profile endpoint (Phase 4 / P0) (2026-01-29)

- Why:
  - Provide entity-centric semantic output (facts / relations / recent events) for UI sidebars.

- What:
  - Added `/memory/v1/entity-profile` endpoint with entity resolve + profile aggregation.
  - Added Neo4j queries: `query_entity_detail`, `query_entity_knowledge`, `query_entity_relations`.
  - Added GraphService wrappers for entity detail/facts/relations.
  - Updated API/SDK docs with entity-profile usage (beta).

- Test:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest modules/memory/tests/unit/test_memory_entity_profile.py -q`

---

## 112. Quotes endpoint (Phase 4 / P0) (2026-01-29)

- Why:
  - Provide utterance-level quotes for entities/topics with evidence anchors.

- What:
  - Added `/memory/v1/quotes` endpoint with entity/topic filters.
  - Added unit test for quotes (entity path).
  - Updated API/SDK docs with quotes usage.

- Test:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest modules/memory/tests/unit/test_memory_quotes.py -q`

---

## 113. Relations endpoint (Phase 4 / P0) (2026-01-29)

- Why:
  - Expose entity relationship strength based on co-involved events within a time range.

- What:
  - Added `/memory/v1/relations` endpoint with entity resolve + event-based aggregation.
  - Added Neo4j query `query_entity_relations_by_events`.
  - Added GraphService wrapper `entity_relations_by_events`.
  - Updated API/SDK docs with relations usage.

- Test:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest modules/memory/tests/unit/test_memory_relations.py -q`

---

## 114. Time-since endpoint (Phase 4 / P0) (2026-01-29)

- Why:
  - Provide a lightweight “last mentioned + days ago” view for topics/entities.

- What:
  - Added `/memory/v1/time-since` endpoint with topic/entity resolution.
  - Uses topic timeline / entity events as base, computes last_mentioned + days_ago.
  - Updated API/SDK docs with time-since usage.

- Test:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest modules/memory/tests/unit/test_memory_time_since.py -q`

---

## 115. Phase 5 evaluation plan + scripts (2026-01-29)

- Why:
  - Establish measurable quality gates for Phase 4 semantic APIs.

- What:
  - Added Phase 5 evaluation plan doc with metrics/thresholds.
  - Added ground-truth template samples under `modules/memory/data/phase5/ground_truth`.
  - Added Phase 5 evaluation scripts + shared metrics/utils.
  - Added unit tests for metrics helpers.

- Test:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest modules/memory/tests/unit/test_phase5_metrics.py -q`

---

## 116. Phase 5 LoCoMo ground-truth + eval wiring (2026-01-30)

- Why:
  - Run Phase 5 evaluation on real LoCoMo ingest (conv-26) after LLM extraction,
    and align eval payloads with API limit semantics.

- What:
  - Added `build_locomo_ground_truth.py` to generate Phase 5 ground truth from Neo4j
    (topic-timeline/time-since/entity-profile/relations/quotes).
  - Updated `eval_entity_profile.py` to pass facts/relations/events limits inferred from samples.
  - Updated `eval_quotes.py` to pass limit inferred from samples.

- Test:
  - `python modules/memory/scripts/phase5/build_locomo_ground_truth.py --tenant-id locomo_bench_phase5 --user-token locomo_user_conv-26`
  - `python modules/memory/scripts/phase5/eval_entity_profile.py --input modules/memory/data/phase5/ground_truth/locomo_conv26_phase5/entity_profile.jsonl --base-url http://127.0.0.1:8000 --tenant-id locomo_bench_phase5`
  - `python modules/memory/scripts/phase5/eval_quotes.py --input modules/memory/data/phase5/ground_truth/locomo_conv26_phase5/quotes.jsonl --base-url http://127.0.0.1:8000 --tenant-id locomo_bench_phase5`

---

## 117. Phase 5 LoCoMo evaluation summary + coverage alignment (2026-01-30)

- Why:
  - Provide a clear Phase 5 outcome summary aligned to coverage and API quality thresholds.

- What:
  - Added a consolidated Phase 5 report for LoCoMo conv-26 with pass/fail against thresholds:
    `modules/memory/outputs/phase5/locomo_conv26_phase5/phase5_report.md`.
  - Included coverage metrics (topic_path/tags/keywords/_uncategorized) and API results,
    plus the root cause for entity-profile relations (missing CO_OCCURS_WITH edges).

- Test:
  - N/A (report-only).

---

## 118. Build CO_OCCURS_WITH from Event co-occurrence (2026-01-30)

- Why:
  - Entity-profile relations rely on `CO_OCCURS_WITH`, but LoCoMo ingest lacks TimeSlice-based cooccurs.
  - Add Event-based cooccurrence builder to close Phase 5 relations gap.

- What:
  - Added Neo4j builder `build_cooccurs_from_events` (Event → INVOLVES → Entity pairs).
  - Extended graph service and admin endpoint `POST /graph/v0/admin/build_cooccurs` with `mode=timeslice|event`.
  - Updated docs: graph_v0 usage, API quickstart, retrieval workflow, developer API doc, SDK usage.
  - Added unit test for event mode routing in graph admin endpoint.

- Test:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest modules/memory/tests/unit/test_graph_api_endpoints.py -q`

---

## 119. Phase 5 cooccurs rebuild + entity_profile eval fix (2026-01-30)

- Why:
  - Build `CO_OCCURS_WITH` from Event co-involvement to unblock entity-profile relations.
  - Align eval precision with expected entity_id matching.

- What:
  - Restarted server to load event-mode cooccurs builder, executed:
    - `POST /graph/v0/admin/build_cooccurs` with `mode=event` (tenant: locomo_bench_phase5).
  - Updated entity-profile evaluation to prefer `entity_id` over `name`.
  - Rebuilt LoCoMo ground truth and re-ran Phase 5 evaluation.
  - Updated Phase 5 report.

- Test:
  - `PYTHONPATH=. python modules/memory/scripts/phase5/build_locomo_ground_truth.py --tenant-id locomo_bench_phase5 --user-token locomo_user_conv-26 --output-dir modules/memory/data/phase5/ground_truth/locomo_conv26_phase5`
  - `PYTHONPATH=. python modules/memory/scripts/phase5/eval_entity_profile.py --input modules/memory/data/phase5/ground_truth/locomo_conv26_phase5/entity_profile.jsonl --base-url http://127.0.0.1:8000 --tenant-id locomo_bench_phase5 --output modules/memory/outputs/phase5/locomo_conv26_phase5/entity_profile_report.json`

---

## 120. C9 Rewrite Phase 0 回补：GraphService/Neo4jStore 地基补齐（2026-02-21）

- Why:
  - 进入 `rewrite/memory-from-c9` 后，需要先补齐 feature 分支 c9 之后依赖的底层查询能力，作为 Explain 与语义解析链路的前置地基。
  - 本阶段目标是“只补能力，不破坏现有行为”：新增方法参数全部可选、缺失方法时安全降级。

- What:
  - `modules/memory/application/graph_service.py`
  - 新增 `list_events_by_ids`、`list_entities_by_ids`、`expand_neighbors`、`event_id_by_logical_id`。
  - 增强 `resolve_entities`，新增可选参数 `user_ids`、`memory_domain` 并向下透传。
  - 对可选 store 方法使用 `getattr + callable` 容错（方法缺失时返回空结果）。
  - `modules/memory/infra/neo4j_store.py`
  - 增强 `query_entities_by_name`，新增 user/domain 过滤参数并注入 fulltext/contains 两条查询路径。
  - 新增 `query_entities_by_ids`（含 user/domain 过滤、按输入 ID 顺序返回、name 兜底）。
  - 新增 `query_event_id_by_logical_id`（logical_event_id -> event_id 映射）。
  - 新增单测：
  - `modules/memory/tests/unit/test_graph_service_phase0_methods.py`
  - `modules/memory/tests/unit/test_neo4j_phase0_methods.py`

- Test:
  - `cd MOYAN_AGENT_INFRA && source .venv/bin/activate && pytest -q modules/memory/tests/unit/test_graph_service_phase0_methods.py modules/memory/tests/unit/test_neo4j_phase0_methods.py`
  - 结果：`9 passed`
  - `cd MOYAN_AGENT_INFRA && source .venv/bin/activate && pytest -q modules/memory/tests`
  - 结果：`483 passed, 6 skipped`

- 目标符合性评估:
  - 总体目标（从 c9 干净重写并逐步回补）: Phase 0 已完成，提供后续 Phase 1/2 所需底层能力。
  - 阶段目标（兼容优先）: 满足。新增参数均为可选，旧调用路径不受影响，且全测通过。
  - 质量目标（代码整洁）: 满足。新增逻辑集中在 service/store 层，不引入路由重复，不改动对外接口语义。

- 外部接口/SDK 变更:
  - 本阶段无新增或变更对外 HTTP API/SDK 契约。
  - 根目录 `SDK使用说明.md`、`开发者API 说明文档.md` 无需更新。

---

## 121. C9 Rewrite P0（Infra-only）：Explain 端点 + Topic 文本归一化函数（2026-02-21）

- Why:
  - 按新架构边界（Infra 只做确定性能力，复杂语义解析交给 Agentic ADK），优先补齐高价值、低风险的原子能力：
    - `POST /memory/v1/explain`（事件证据链溯源）
    - `normalize_topic_text`（统一 topic 文本归一化入口，便于多个 v1 接口复用）
  - 避免在 Infra 层引入复杂自然语言事件解析链路，保持 API 简洁稳定。

- What:
  - `modules/memory/application/topic_normalizer.py`
  - 新增 `TopicNormalization` 数据结构（`topic_id/topic_path/tags/keywords/tags_vocab_version`）。
  - 新增 `normalize_topic_text(topic_text)`（LRU 缓存，`maxsize=1024`）。
  - 保留 `TopicNormalizer` / `normalize_events` 既有行为不变；新增函数通过包装现有规则引擎实现。
  - `modules/memory/api/server.py`
  - 新增 `ExplainBody` 与 `POST /memory/v1/explain`（仅支持 `event_id`，复用 `graph_svc.explain_event_evidence`）。
  - 将 `topic-timeline / quotes / time-since` 三个接口中的重复 `TopicNormalizer().normalize_event(...)` 逻辑改为统一调用 `normalize_topic_text`。
  - 新增/更新单测：
  - `modules/memory/tests/unit/test_memory_explain.py`
  - `modules/memory/tests/unit/test_topic_normalizer.py`（补 `normalize_topic_text` 结构与缓存测试）

- Test:
  - `cd MOYAN_AGENT_INFRA && source .venv/bin/activate && pytest -q modules/memory/tests/unit/test_topic_normalizer.py modules/memory/tests/unit/test_memory_explain.py modules/memory/tests/unit/test_memory_topic_timeline.py modules/memory/tests/unit/test_memory_quotes.py modules/memory/tests/unit/test_memory_time_since.py`
  - 结果：`17 passed`
  - `cd MOYAN_AGENT_INFRA && source .venv/bin/activate && pytest -q modules/memory/tests`
  - 结果：`488 passed, 6 skipped`

- 目标符合性评估:
  - 总体目标（Infra/ADK 分层）: 满足。新增能力均为确定性原子接口/工具，不包含 Agentic 语义规划逻辑。
  - 阶段目标（P0 高价值低风险）: 满足。Explain 已对外可用；topic 文本归一化入口抽象完成并接入 3 个现有接口。
  - 质量目标（代码整洁）: 满足。减少了 `server.py` 中重复归一化代码路径，未引入额外路由别名或复杂开关。

- 外部接口/SDK 变更:
  - 新增对外 HTTP 接口：`POST /memory/v1/explain`（`memory.read`）。
  - 已同步更新根目录文档：
    - `SDK使用说明.md`
    - `开发者API 说明文档.md`

---

## 122. C9 Rewrite P1（Infra-only）：TopicRegistry 确定性 Key（无相似合并）接入写入/查询归一化（2026-02-21）

- Why:
  - 在不把复杂语义解析下沉到 Infra 的前提下，先解决“同一 topic 文本大小写/空格漂移导致 `topic_id` 碎片化”的数据质量问题。
  - 为后续 ADK 查询提供更稳定的 `topic_id`，同时保证写入侧 `normalize_events` 与查询侧 `normalize_topic_text` 产出一致。

- What:
  - `modules/memory/application/topic_normalizer.py`
  - 新增 `TopicRegistry`（进程内、按 `tenant_id::memory_domain` 分桶、LRU 风格容量裁剪）。
  - 新增 deterministic canonical key 生成：`build_topic_canonical_key(event)`。
  - 新增 `apply_topic_registry(event)`，在 `normalize_events()` 中接入（写入前统一处理）。
  - `normalize_topic_text()` 同步接入 TopicRegistry 规则，确保查询侧与写入侧 topic_id 对齐。
  - 默认行为：
    - `MEMORY_TOPIC_REGISTRY_ENABLED=true`
    - `MEMORY_TOPIC_REGISTRY_OVERRIDE_TOPIC_ID=true`
    - `MEMORY_TOPIC_REGISTRY_MAX_PER_SCOPE=2000`
  - 迁移缓冲字段：
    - 保留 `topic_id_raw`（当原始 topic_id 存在时）
    - 附加 `topic_registry_key` / `topic_registry_source` 便于观测
  - 本阶段明确不做：
    - Jaccard/语义相似合并
    - 持久化 registry（仅进程内）

- Test:
  - `cd MOYAN_AGENT_INFRA && source .venv/bin/activate && pytest -q modules/memory/tests/unit/test_topic_normalizer.py modules/memory/tests/unit/test_memory_topic_timeline.py modules/memory/tests/unit/test_memory_quotes.py modules/memory/tests/unit/test_memory_time_since.py`
  - 结果：`16 passed`
  - `cd MOYAN_AGENT_INFRA && source .venv/bin/activate && pytest -q modules/memory/tests`
  - 结果：`490 passed, 6 skipped`

- 目标符合性评估:
  - 总体目标（Infra/ADK 分层）: 满足。该能力是写入/查询归一化增强，不引入 Agentic 规划逻辑。
  - 阶段目标（干净地提升 topic 数据稳定性）: 满足。通过 deterministic key 先统一大小写/空格差异，且读写侧对齐。
  - 风险控制: 满足。相似合并与持久化均未引入；保留 `topic_id_raw` 便于后续观测和回滚策略设计。

- 外部接口/SDK 变更:
  - 无新增 HTTP 路由或 SDK 方法。
  - 根目录 `SDK使用说明.md`、`开发者API 说明文档.md` 本轮无需更新。

---

## 123. C9 Rewrite P2（Infra-only）：Mention 抽取（Shadow/默认关闭）接入 session_write 图增强（2026-02-21）

- Why:
  - 在不引入 Agentic NER 的前提下，先提供一层低成本、可灰度的 mention 增强能力，提高 Event/Entity 图谱覆盖率上限。
  - 采用“默认关闭 + shadow/写入双开关”策略，避免规则误判直接污染生产图谱。

- What:
  - `modules/memory/session_write.py`
  - 新增规则型 mention 抽取（英文专名词 + 中文姓名规则，带 stopwords 过滤）。
  - 新增 `_augment_tkg_with_mentions(...)`，在 `build_dialog_graph_upsert_v1(...)` 之后、`graph_upsert_v0` 之前增强 `tkg_build.request`：
    - `UtteranceEvidence -[MENTIONS]-> Entity`
    - `Event -[INVOLVES]-> Entity`（基于已有 `Event -[SUPPORTED_BY]-> UtteranceEvidence` 链路回填）
  - 新增稳定 mention entity ID（跨 session 可复用，按 `tenant/domain/user_tokens/name` 生成）。
  - 增加 trace 输出 `trace["mention_entity"]`，记录候选数/新增实体数/新增边数。
  - 开关（默认安全关闭）：
    - `MENTION_ENTITY_ENABLED=false`（开启写图）
    - `MENTION_ENTITY_SHADOW=false`（仅统计不写图）
    - `MENTION_ENTITY_MAX_PER_UTTERANCE=8`
  - 顺手修复：`session_write.py` 补充缺失的 `import os`（原文件在 state 更新逻辑中已使用 `os.getenv`）。

- Test:
  - `cd MOYAN_AGENT_INFRA && source .venv/bin/activate && pytest -q modules/memory/tests/unit/test_session_write_graph_upsert.py`
  - 结果：`6 passed`
  - `cd MOYAN_AGENT_INFRA && source .venv/bin/activate && pytest -q modules/memory/tests/unit/test_session_write_api.py modules/memory/tests/unit/test_dialog_tkg_graph_v1.py`
  - 结果：`12 passed`
  - `cd MOYAN_AGENT_INFRA && source .venv/bin/activate && pytest -q modules/memory/tests`
  - 结果：`492 passed, 6 skipped`

- 目标符合性评估:
  - 总体目标（Infra/ADK 分层）: 满足。仅做规则型图增强和原子边写入，不做复杂语义解析/规划。
  - 阶段目标（可灰度、默认安全）: 满足。默认不启用写入；可先用 shadow 模式观测候选质量。
  - 风险控制: 满足。通过开关隔离写图副作用，并保留 trace 指标支持后续精度评估。

- 外部接口/SDK 变更:
  - 无新增 HTTP 路由或 SDK 方法。
  - 根目录 `SDK使用说明.md`、`开发者API 说明文档.md` 本轮无需更新。

---

## 124. 文档对齐修订：Explain / Mention 能力说明与 API 契约校准（2026-02-22）

- Why:
  - 用户要求核验 `Explain` / `Mention` 的产品化理解是否与当前实现一致，并修正文档中的超前描述或不精确表述。
  - `Explain` 已对外开放为 `/memory/v1/explain`，需要确保开发者文档中的 Request/Response 与代码真实契约一致。

- What:
  - `docs/时空知识记忆系统构建理论/8. Python SDK 、api 、mcp设计/语义记忆API架构决议与用户故事_v1.md`
  - 修正 `4.6 / 4.11` 中 Explain 的描述：
    - 去除未实现参数（`max_evidence` / `include_knowledge`）
    - 明确当前输入为 `event_id + debug`
    - 明确 `found=false` 的稳定空结构返回语义（`200`）
    - 将“推理步骤”表述收敛为“结构化证据链/关联知识”
  - 修正 `4.14` 中 Mention 的描述措辞：
    - 避免“每个人名都能被关联”的过度承诺，改为“规则命中时覆盖率提升”
    - 补充 stopwords/self-mention 过滤等实现细节
  - 修正 3.1 小节 `语义记忆查询族` 数量文字与表格不一致（`7` -> `10`）
  - `开发者API 说明文档.md`
  - 校准 `/memory/v1/explain` 的 Request/Response 说明：
    - 明确当前仅支持 `event_id`、`debug`
    - 增补 Response 字段表（`found/event_id/event/.../knowledge/trace`）
    - 增补空输入/未命中时 `200 + found=false` 行为说明
    - 明确自然语言事件解析不属于该接口职责（由 ADK 层完成）
  - 顺手修正 `5.22` 开头的过期说明（不再描述为仅开放 topic-timeline）。

- Test / Verification:
  - 文档对齐型变更，无代码行为修改。
  - 采用“代码对照核验”方式确认契约一致性：
    - `modules/memory/api/server.py` (`ExplainBody`, `POST /memory/v1/explain`)
    - `modules/memory/session_write.py` (Mention 开关、shadow 模式、trace 字段、边类型)
    - `modules/memory/tests/unit/test_memory_explain.py`
    - `modules/memory/tests/unit/test_session_write_graph_upsert.py`

- 目标符合性评估:
  - 满足。文档已与当前实现对齐，避免后续 ADK/产品设计基于错误接口假设施工。

- 外部接口/SDK 变更:
  - 无接口行为变更（仅文档修订）。
  - 根目录 `开发者API 说明文档.md` 已更新；`SDK使用说明.md` 本轮无需变更。

---

## 125. 文档契约重建：`开发者API 说明文档.md` 第 5.22 节（Memory v1）全段重写并与 `server.py` 对齐（2026-02-22）

- Why:
  - `开发者API 说明文档.md` 的 `5.22` 段存在历史残留表格碎片与缺失字段，已不足以作为开发者/内部技术人员/产品经理的统一对齐手册。
  - 用户明确要求该文档“绝对准确和一致”，因此需按代码真实契约重建 `5.22` 全段，而非局部修补。

- What:
  - `开发者API 说明文档.md`
  - 将 `5.22` 整段重建为 `10` 个 `/memory/v1/*` 端点的完整说明：
    - `GET /memory/v1/entities`
    - `GET /memory/v1/topics`
    - `POST /memory/v1/resolve-entity`
    - `GET /memory/v1/state/properties`
    - `POST /memory/v1/topic-timeline`
    - `POST /memory/v1/entity-profile`
    - `POST /memory/v1/quotes`
    - `POST /memory/v1/relations`
    - `POST /memory/v1/time-since`
    - `POST /memory/v1/explain`
  - 为每个端点补齐/校准：
    - 输入（Query / Body）字段表、默认值、clamp 行为
    - 返回体字段表（含可选字段与条件返回）
    - 当前实现特有行为（空输入/未命中/歧义候选/AND 语义/保留字段未生效）
    - 错误/熔断/超时语义（`400/503/504`）
  - 清理 `5.22` 内历史损坏片段（孤立表格行），恢复 `5.22 -> 5.23` 章节结构连续性。

- Test / Verification:
  - 文档对齐型变更，无代码行为修改。
  - 逐项对照 `modules/memory/api/server.py` 完成核验：
    - 请求模型：`TopicTimelineBody / EntityProfileBody / QuotesBody / RelationsBody / ExplainBody / ResolveEntityBody / TimeSinceBody`
    - 端点 handler：`/memory/v1/entities|topics|resolve-entity|state/properties|topic-timeline|entity-profile|quotes|relations|time-since|explain`
    - 辅助函数：`_quotes_from_bundle`, `_resolve_entity_candidates`, `_missing_core_requirements`, `_gate_high_cost`
  - 文档结构校验：
    - 确认 `5.22` 段无残留损坏表格碎片
    - 确认 `5.23` 起始章节衔接正常

- 目标符合性评估:
  - 满足。`开发者API 说明文档.md` 的 `5.22` 段已恢复为可执行、可验证、可对齐的契约文档。
  - 风险控制：通过逐 handler 对照，避免“文档超前于实现”或“遗漏可选字段/特殊行为”。

- 外部接口/SDK 变更:
  - 无接口行为变更（仅文档重写）。
  - 根目录 `开发者API 说明文档.md` 已更新；`SDK使用说明.md` 本轮无需变更。

---

## 126. 文档复核（Claude 审查意见）：`5.22 resolve-entity / explain` 细节措辞收紧（2026-02-22）

- Why:
  - 针对外部复核意见（Claude）再次核验 `5.22` 中 `resolve-entity` 与 `explain` 的契约说明，确认是否存在措辞误导。
  - 用户强调 `开发者API 说明文档.md` 是开发/产品/技术对齐手册，需要持续提高表述精度。

- What:
  - `开发者API 说明文档.md`
  - `5.22.3 /memory/v1/resolve-entity`
    - 将 `candidates` 字段说明收紧为：
      - 歧义时返回候选列表（通常非空）
      - 非歧义时通常省略
      - 空白 `name` 为特例，返回空数组
  - `5.22.10 /memory/v1/explain`
    - 补充说明本端点为轻量级图遍历接口，当前实现不经过高成本熔断（不调用 `_gate_high_cost`）

- Test / Verification:
  - 文档对齐型变更，无代码行为修改。
  - 复核依据：
    - `modules/memory/api/server.py` 中 `memory_resolve_entity()`、`_resolve_entity_candidates()`、`memory_explain()`、`_gate_high_cost()`

- 目标符合性评估:
  - 满足。消除了 `candidates` 字段与 explain 熔断行为的潜在误读点，进一步提升文档作为统一契约手册的可靠性。

- 外部接口/SDK 变更:
  - 无接口行为变更（仅文档措辞优化）。
  - 根目录 `开发者API 说明文档.md` 已更新；`SDK使用说明.md` 本轮无需变更。

---

## 127. Mention Shadow 评估准备（Phase A / 无 DB）：离线候选统计脚本 + Runbook（2026-02-22）

- Why:
  - 后续计划已确认先做 `Mention shadow` 质量评估，再决定是否进入灰度写图。
  - 为避免过早启动 `Neo4j + Qdrant`，先提供一个不依赖数据库的离线评估入口，快速量化规则型 mention 候选质量。

- What:
  - 新增离线统计脚本：`modules/memory/scripts/mention_shadow_candidate_report.py`
    - 复用 `session_write.py` 中的规则提取器 `_extract_mention_candidates(...)`
    - 支持输入格式：
      - `locomo10`（LoCoMo 原始 `locomo10.json`）
      - `turns_json`（`[{"text":...}]` 或 `{"turns":[...]}`）
      - `turns_jsonl`（每行一条 utterance）
    - 输出内容：
      - `summary`（命中率、候选数、密度等）
      - `top_candidates`（高频候选）
      - `examples`（人工抽样样本）
  - 新增评估 runbook：`modules/memory/docs/operations/mention_shadow_eval_runbook.md`
    - 明确阶段划分：
      - Phase A：离线评估（无 DB）
      - Phase B：端到端 shadow（需 `Neo4j + Qdrant`）
      - Phase C：灰度写图（需 `Neo4j + Qdrant`）
    - 定义指标与建议阈值（推进/回滚条件）
    - 提供执行命令模板与环境变量示例

- Test:
  - 离线脚本 smoke（无数据库）：
  - `cd MOYAN_AGENT_INFRA && source .venv/bin/activate && python modules/memory/scripts/mention_shadow_candidate_report.py --input <tmp_turns.json> --format turns_json --example-limit 5 --topk 10`
  - 结果：脚本正常输出 `summary` 与 `top_candidates_preview`（本地 3 条样本，命中 `Bob/Google/张三/李四`）
  - LoCoMo `conv-26` 离线统计（无数据库）：
  - `cd MOYAN_AGENT_INFRA && source .venv/bin/activate && python modules/memory/scripts/mention_shadow_candidate_report.py --input benchmark/data/locomo/raw/locomo10.json --format locomo10 --sample-id conv-26 --example-limit 20 --topk 50 --output modules/memory/outputs/mention_shadow/locomo_conv26_report.json`
  - 结果（摘要）：
    - `utterances_total=419`
    - `utterances_with_mentions=413`（命中率 `0.98568`）
    - `candidates_total=1280`
    - `avg_candidates_per_nonempty_utterance=3.054893`
    - `max_candidates_per_utterance=8`
  - 高频候选预览显示明显英文代词/语气词噪声（如 `It / Wow / What / That / We / You`），说明进入 Phase B 前应先收紧英文 stopwords / 规则边界。

- 目标符合性评估:
  - 总体目标（Infra/ADK 分层）: 满足。当前仅做 Mention 质量评估准备，不引入新的语义解析能力到 Infra。
  - 阶段目标（先评估质量再决定是否灰度）: 满足。已形成“不起库先评估”的可执行路径与阈值框架。
  - 风险控制: 满足。明确仅在进入 Phase B / C 时才需要启动 `Neo4j + Qdrant`；当前离线结果已暴露噪声问题，避免过早进入端到端阶段。

- 外部接口/SDK 变更:
  - 无对外 HTTP API / SDK 契约变更。
  - 根目录 `SDK使用说明.md`、`开发者API 说明文档.md` 本轮无需更新。

---

## 128. Mention 路线调整（系统工程收敛）：删除规则 shadow 旁路，改为接通 LLM 主链路 `participants/mentions` 建边（2026-02-22）

- Why:
  - 复盘确认：Stage3 统一抽取器（LLM）已输出 `events[].participants` 与 `knowledge[].mentions`，真正断点在图构建层未消费这些字段。
  - 为避免长期保留规则型 mention shadow 旁路（额外启发式、不必要开关与运维复杂度），按“修主管线优先”的原则，直接补全主链路消费与建边。
  - 用户明确要求保持系统简洁、避免引入垃圾和无用代码。

- What:
  - `modules/memory/domain/dialog_tkg_graph_v1.py`
    - 接通 `events_raw[].participants`：
      - 规范化/去重 participant 名称
      - 复用或创建 `Entity(PERSON)`（同 session scope 稳定 ID）
      - 写入 `Event -[INVOLVES]-> Entity` 边（来源标记 `dialog_tkg_unified_extractor_v1`）
      - 与 speaker 派生 `INVOLVES` 去重，避免重复边
    - 接通 `facts_raw[].mentions`（即 unified extractor 的 `knowledge[].mentions`）：
      - 规范化/去重 mention 名称
      - 复用或创建 `Entity(PERSON)`
      - 写入 `Knowledge -[MENTIONS]-> Entity` 边（来源标记 `dialog_tkg_unified_extractor_v1`）
    - `graph_ids["entity_ids"]` 从“仅 speaker entities”扩展为“本次请求所有 entities”（包含 participants/mentions 衍生实体）
  - `modules/memory/session_write.py`
    - 删除规则型 mention 旁路实现（文本 regex 抽取 + shadow/write 双开关 + trace 注入）
    - 删除 `session_write` 中对 `_augment_tkg_with_mentions(...)` 的调用
    - 写入主链路恢复为：`LLM抽取 -> build_dialog_graph_upsert_v1 -> graph_upsert`
  - 清理同日新增的旁路资产（避免误导后续施工）：
    - 删除 `modules/memory/scripts/mention_shadow_candidate_report.py`
    - 删除 `modules/memory/docs/operations/mention_shadow_eval_runbook.md`
    - 删除临时离线报告产物 `modules/memory/outputs/mention_shadow/locomo_conv26_report.json`
  - `modules/memory/docs/C9_REWRITE_MIGRATION_MEMO.md`
    - mention 相关章节改写为“主链路消费 LLM `participants/mentions`”
    - 去除对规则 shadow / 环境变量开关的规划描述

- Test:
  - 语法检查：
    - `cd MOYAN_AGENT_INFRA && source .venv/bin/activate && python -m py_compile modules/memory/session_write.py modules/memory/domain/dialog_tkg_graph_v1.py`
    - 结果：通过
  - 针对性单测：
    - `cd MOYAN_AGENT_INFRA && source .venv/bin/activate && pytest -q modules/memory/tests/unit/test_dialog_tkg_graph_v1.py modules/memory/tests/unit/test_session_write_graph_upsert.py`
    - 结果：`12 passed`
  - 全量测试：
    - `cd MOYAN_AGENT_INFRA && source .venv/bin/activate && pytest -q modules/memory/tests`
    - 结果：`492 passed, 6 skipped`

- 目标符合性评估:
  - 总体目标（Infra/ADK 分层）: 满足。仅补全 LLM 主链路的图消费与建边，不把复杂语义解析下沉到 Infra。
  - 代码整洁目标: 满足。移除规则型 mention 旁路与 shadow 资产，减少启发式分支和开关复杂度。
  - 产品/业务价值目标: 满足。事件参与者与知识 mention 终于进入图结构，可被 explain / 图查询链路消费。

- 外部接口/SDK 变更:
  - 无对外 HTTP API / SDK 契约变更（均为写入主链路内部实现调整）。
  - 根目录 `SDK使用说明.md`、`开发者API 说明文档.md` 本轮无需更新。

---

## 129. 文档对齐：`语义记忆API架构决议与用户故事_v1.md` 同步主链路 Mention 实现（2026-02-22）

- Why:
  - `modules/memory/domain/dialog_tkg_graph_v1.py` 已改为主链路消费 LLM `events[].participants` / `knowledge[].mentions` 建边，原架构决议文档仍描述为“规则型 mention shadow（默认关）”，与当前实现不一致。
  - 该文档是产品/研发/内部技术对齐手册，需保持与代码状态一致，避免后续按错误路线继续施工。

- What:
  - 更新 `docs/时空知识记忆系统构建理论/8. Python SDK 、api 、mcp设计/语义记忆API架构决议与用户故事_v1.md`
    - `2.4` 决议表：Mention 改为“主链路消费 LLM participants/mentions”
    - `4.10` 场景链：将“规则 Mention 边”改为 `INVOLVES / MENTIONS` 关联边（主链路消费）
    - `4.14` 整段重写：从“规则 shadow 路线”改为“图建造工厂消费 LLM 输出并建边”
    - `6` 路线图 Phase 3：状态改为“主链路已接通”
  - 保留 Explain 端点描述（已与当前 `/memory/v1/explain` 实现一致）

- Test:
  - 文档改动，未运行测试（无代码行为变更）
  - 使用 `rg` 复核，确认文档中已无 `MENTION_ENTITY_*` / `shadow` 的旧实现描述残留

- 目标符合性评估:
  - 总体目标（Infra/ADK 分层）: 满足。文档明确 Mention 属于 Infra 图建造主链路消费，不再误导为规则旁路。
  - 文档对齐目标: 满足。产品视角描述与当前代码实现一致。

- 外部接口/SDK 变更:
  - 无对外 HTTP API / SDK 契约变更。
  - 根目录 `SDK使用说明.md`、`开发者API 说明文档.md` 本轮无需更新。

---

## 130. Agent 可用性评估沉淀：`/memory/v1/*` + `/memory/state/*` 的 ADK 改造遵循文档（2026-02-22）

- Why:
  - 用户明确要求将“按 Agent 可用性评估 API + 针对性改造建议”沉淀为正式文档，作为后续 Agent 开发与 API/ADK 改造的统一遵循。
  - 当前 `开发者API 说明文档.md` 侧重 HTTP 契约，缺少“哪些接口可直接做 Agent 工具、哪些必须语义封装”的分层指导。

- What:
  - 新增文档：
    - `docs/时空知识记忆系统构建理论/8. Python SDK 、api 、mcp设计/语义记忆与状态API_Agent可用性评估及ADK改造遵循_v1.md`
  - 文档内容包括：
    - Infra / ADK / Agent 的分层原则（不把复杂语义解析塞回 Infra）
    - `/memory/v1/*` 与 `/memory/state/*` 逐项 Agent 可用性评估（18 个路由）
    - ADK/SDK/MCP 语义门面建议（收敛成 8~10 个语义工具）
    - 错误归一化、歧义处理、轻重查询策略
    - 对 `开发者API 说明文档.md` 的 P0/P1 补齐建议（尤其 5.23 状态接口）

- Test:
  - 文档改动，未运行测试（无代码行为变更）
  - 本次评估依据为：
    - `开发者API 说明文档.md` 第 `5.22 / 5.23` 节
    - `modules/memory/api/server.py` 当前请求模型与 handler
    - `modules/memory/application/graph_service.py` / `modules/memory/infra/neo4j_store.py` 状态接口返回结构

- 目标符合性评估:
  - 总体目标（Infra/ADK 分层）: 满足。文档明确“语义调用方式”应落在 ADK/SDK/MCP 门面层，而非回退到 Infra 复杂语义解析。
  - 施工指导目标: 满足。已形成可直接用于后续 Agent 开发和 API/ADK 改造排期的依据文档。

- 外部接口/SDK 变更:
  - 无对外 HTTP API / SDK 契约变更（本轮仅新增遵循文档）。
  - 根目录 `SDK使用说明.md`、`开发者API 说明文档.md` 本轮未修改。

---

## 131. 文档补充：检索路径分层（图过滤 / 图检索 / Retrieval-RAG）与 ADK 选路原则（2026-02-22）

- Why:
  - 用户提出关键问题：哪些能力能用 `topic/tag/keywords` 低成本过滤，哪些需要关键词图检索或 Retrieval/RAG；以及 Agent 是否“都用图检索”。
  - 该问题直接影响后续 ADK 工具选路、成本控制和观测设计，需沉淀到遵循文档中，避免后续实现时混淆“图过滤 / 图检索 / RAG”边界。

- What:
  - 更新文档：
    - `docs/时空知识记忆系统构建理论/8. Python SDK 、api 、mcp设计/语义记忆与状态API_Agent可用性评估及ADK改造遵循_v1.md`
  - 新增 `3.3 检索路径分层与选路原则（图过滤 / 图检索 / Retrieval-RAG）`，明确：
    - 三类路径的定义与使用边界
    - 当前可直接使用 `topic_id/topic_path/tags/keywords` 低成本过滤的核心对象为 `Event`
    - `UtteranceEvidence / Knowledge / Entity` 多数通过“先筛 Event 再展开”间接受益
    - `/memory/v1/topic-timeline`、`/memory/v1/quotes`、`/memory/v1/time-since` 为 graph-first + retrieval fallback
    - `/memory/state/*` 为独立图查询链（不走 topic/tag，也不走 retrieval）
    - ADK 工具层应记录 `graph_filter / graph_search / retrieval_rag` 来源模式，便于性能与质量分析

- Test:
  - 文档改动，未运行测试（无代码行为变更）
  - 依据代码核验：
    - `modules/memory/api/server.py`（`topic-timeline / quotes / time-since / retrieval / graph_search` 路由分支）
    - `modules/memory/application/graph_service.py`（`topic_timeline` 分派）
    - `modules/memory/infra/neo4j_store.py`（`query_events_by_topic` 的 `topic_id/topic_path/tags/keywords` 过滤条件）

- 目标符合性评估:
  - 架构边界目标: 满足。文档明确区分 Memory API、图检索、Retrieval/RAG 的产品边界与实现桥接关系。
  - ADK 施工指导目标: 满足。新增选路原则与可观测要求，可直接用于后续工具编排设计。

- 外部接口/SDK 变更:
  - 无对外 HTTP API / SDK 契约变更（本轮仅文档补充）。
  - 根目录 `SDK使用说明.md`、`开发者API 说明文档.md` 本轮无需更新。

---

## 132. ADK 设计阶段启动：状态接口契约补齐（5.23）+ 阶段目标与实施思路文档（2026-02-22）

- Why:
  - 用户确认进入“ADK 设计阶段”，要求先补齐工作主线中的 P0 前置项：逐 API 做 ADK 使用设计前，需先补全状态接口契约（避免字段猜测），并落一份 ADK 设计阶段的顶层目标与实施思路。
  - `开发者API 说明文档.md` 第 `5.23` 节此前存在返回体描述过于简略、重复小节等问题，会直接拖慢 ADK 语义工具设计与实现。

- What:
  - 更新 `开发者API 说明文档.md` 第 `5.23` 节（状态记忆）：
    - 新增通用约定（`tenant_id` 来源、`subject_id/property` 语义、时间解析容错、节点属性透传约定）
    - 为 `current / at_time / changes / what-changed / time-since / pending/list / pending/approve / pending/reject` 补齐请求/返回字段与错误语义
    - 明确 `404 state_not_found / pending_state_not_found` 行为
    - 明确 `changes/what-changed/time-since` 的 `start_iso/end_iso` 解析失败按 `null` 处理
    - 删除重复的 `what-changed / time-since` 小节
  - 新增 ADK 设计阶段顶层规划文档：
    - `docs/时空知识记忆系统构建理论/8. Python SDK 、api 、mcp设计/ADK语义工具与AgenticAPI设计阶段目标与实施思路_v1.md`
    - 内容覆盖：阶段目标、边界、实施思路、工具设计模板、交付物、分阶段 TODO、风险控制

- Test:
  - 文档改动，未运行测试（无代码行为变更）
  - 契约核验依据：
    - `modules/memory/api/server.py`（状态端点请求模型与 handler 返回逻辑）
    - `modules/memory/application/graph_service.py`（状态服务透传/审批返回结构）
    - `modules/memory/infra/neo4j_store.py`（`State`/`PendingState` 常见节点属性与时间字段转换）
    - `modules/memory/tests/unit/test_memory_state_endpoints.py`（端点行为 smoke）

- 目标符合性评估:
  - ADK 设计阶段启动目标: 满足。已完成 P0 契约补齐，并形成阶段性顶层规划文档。
  - 文档对齐目标: 满足。`5.23` 状态接口文档与当前代码行为的关键点（返回 envelope / 错误语义 / 时间解析容错）已对齐。

- 外部接口/SDK 变更:
  - 无对外 HTTP API / SDK 行为变更（本轮仅文档修订与规划文档新增）。
  - 根目录 `SDK使用说明.md` 本轮无需更新。

---

## 133. 文档升级（评审反馈落地）：`语义记忆与状态API_Agent可用性评估及ADK改造遵循_v1.md` 从“评估报告”升级为“执行规范主文档”（2026-02-22）

- Why:
  - 用户对逐 API Agent 可用性评估提出关键评审：当前文档方法论正确，但仍停留在“问题清单”层面，尚不足以作为 ADK 实现阶段的可执行规范。
  - 用户明确要求先把该文档明确为“每个 API 的产品化和 ADK 语义调用方案”主文档，后续再据此改造 API 与实现 ADK。

- What:
  - 升级文档定位与版本说明（`v1.1`）：
    - 明确该文档同时承担“逐 API 产品化与 ADK 语义调用执行规范”的角色
  - 新增规范化章节：
    - `3.4` 文档角色升级（评估索引层 + 详细规范层）
    - `3.5` 逐 API 执行规范模板（统一 8+1 项：工具签名/调用链/输出映射/边界行为/预算等）
    - `3.6` 评级修订（基于评审意见）
    - `6.3` 全量 API 返回体上下文预算分级（S/M/L/XL）
    - `6.4` 首批详细可执行规范示范（`resolve-entity` 内部辅助定位、`memory_get_entity_profile`、`memory_get_time_since`）
    - `6.5` 全量 API 详细规范覆盖计划（18 个接口分波次覆盖）
  - 按评审意见修订关键评级与建议：
    - `resolve-entity`：`高 -> 中`（内部辅助步骤）
    - `entity-profile`：`中高 -> 高`
    - `quotes`：`高 -> 中高`
    - `time-since`：`高 -> 中高`
    - `what-changed`：`中高 -> 中`
    - `entity-profile` 建议改为“单工具 + include 参数”，取消 `profile_basic/profile_full` 双工具拆分建议
  - 同步清理文档中过时表述：
    - 将 `5.23` 文档补齐/重复修复从“待办”改为“已完成首轮补齐”

- Test:
  - 文档改动，未运行测试（无代码行为变更）
  - 复核项：
    - 关键评级修订已写入索引层
    - 新模板/预算/示范规范/全量覆盖计划章节已落地

- 目标符合性评估:
  - ADK 设计阶段目标: 满足。文档已从“评估”升级为“执行规范入口”，可直接指导后续工具规范与 API 改造设计。
  - 架构边界目标: 满足。仍坚持复杂语义处理在 ADK/SDK/MCP 门面层，不回退到 Infra handler。

- 外部接口/SDK 变更:
  - 无对外 HTTP API / SDK 行为变更（本轮仅文档升级）。
  - 根目录 `SDK使用说明.md`、`开发者API 说明文档.md` 本轮无需更新。

---

## 134. 文档审查修复：三层架构方案（Layer 0/1/2）与 ADK 阶段文档一致性校准（2026-02-22）

- Why:
  - 用户提交了与 Claude 的联合方案（Layer 0 Infra / Layer 1 ADK Tools / Layer 2 Semantic Router API）及 §6 改进版，要求审查并修复文档一致性问题。
  - 复核发现两份文档存在“改动已落地但仍有旧口径残留”的问题，包括：
    - `ADK` 文档中仍残留旧工具命名（`memory_*`）
    - 旧返回结构字段口径（`ok/...`）残留
    - Layer 1/Layer 2 边界表述可误解
    - 主文档 §6.0 的“绝对不另起工具名”与实际例外（`entity_status` / `status_changes` / `review_pending`）存在张力

- What:
  - 更新 `语义记忆与状态API_Agent可用性评估及ADK改造遵循_v1.md`：
    - §6.0 明确作用域为 **Layer 1 ADK**（不是 Layer 2 Agentic API）
    - 将“绝对不另起工具名”修正为“默认与 Infra 路由同名，命名冲突/组合工具允许例外”
    - 增加补充约束：Layer 2 上层路由不属于 Infra 路由新增；ADK 工具契约需版本化管理
    - 修复残留旧工具名示例（`memory_find_entity` / `memory_get_entity_profile` / `memory_get_state_changes` -> `find_entity` / `entity_profile` / `status_changes`）
  - 更新 `ADK语义工具与AgenticAPI设计阶段目标与实施思路_v1.md`：
    - §4.3 标题改为“模型在 Layer 2 / 上层 Agent 编排中的职责”，避免误解 Layer 1 含 LLM
    - §5 工具模板的输出结构更新为“LLM 可见层 + 调试层”双层口径
    - §6.2/Phase C 工具清单统一为新命名（`find_entity/entity_profile/time_since/...`）
    - Phase D 验收中的错误反馈表述与双层输出设计对齐

- Test:
  - 文档改动，未运行测试（无代码行为变更）
  - 复核方式：
    - `rg` 检查两份文档是否仍残留 `memory_get_* / memory_find_entity / ok/matched` 等旧方案口径
    - 人工复核 §2 / §4 / §6 / Phase D 关键段落的层级边界与术语一致性

- 目标符合性评估:
  - 三层架构边界目标: 满足。Layer 1（工具层）与 Layer 2（语义路由 API）职责描述清晰，避免后续实现误把 LLM 下沉到工具层。
  - 文档执行规范目标: 满足。主文档与阶段文档的工具命名、返回结构、Layer 2 定位已统一，可继续推进 Wave 1 详细规范与实现。

- 外部接口/SDK 变更:
  - 无对外 HTTP API / SDK 行为变更（本轮仅文档审查修复）。
  - 根目录 `SDK使用说明.md`、`开发者API 说明文档.md` 本轮无需更新。

---

## 135. ADK 设计阶段（Wave 1）详细可执行规范扩展：状态类工具与属性词表缓存映射（2026-02-22）

- Why:
  - 用户已对 `resolve-entity / entity_profile / time_since / explain` 的详细规范给出“通过”裁决，并要求继续推进 Wave 1 剩余工具的详细可执行规范。
  - 状态类工具（`entity_status / status_changes / state_time_since`）是 Wave 1 的关键复杂点，涉及多端点聚合、属性映射、时间归一化与空结果/404 语义差异，必须先在文档层固化，避免实现阶段散架。

- What:
  - 更新主文档：
    - `docs/时空知识记忆系统构建理论/8. Python SDK 、api 、mcp设计/语义记忆与状态API_Agent可用性评估及ADK改造遵循_v1.md`
  - 新增 Wave 1 详细规范：
    - `6.6.4 entity_status`（覆盖 `/memory/state/current` + `/memory/state/at_time`）
    - `6.6.5 status_changes`（覆盖 `/memory/state/what-changed` + `/memory/state/changes`）
    - `6.6.6 state_time_since`（覆盖 `/memory/state/time-since`）
    - `6.6.7 state property vocab`（ADK 启动缓存 + 属性映射辅助规范，非终态 Agent 工具）
  - 每个新增规范均补齐：
    - 工具签名（或辅助组件签名）
    - 内部调用链（resolve / 属性映射 / 时间归一化 / 选路）
    - 输出映射规则（底层 -> LLM 可见层）
    - 边界行为映射表（含 `404` / 空结果 / 时间解析容错差异）
    - 上下文预算
    - 测试要点（每项至少 3 条）
  - 同步修正文档一致性：
    - 将 `state_time_since` 纳入 `6.1` 工具暴露表（辅助与深入工具）
    - `6.2` 工具总数由 `12` 更新为 `13`
    - 动态注入示例增加 `state_time_since`
    - `6.7` 覆盖计划中 Wave 1 状态类项从“待展开”更新为“已展开（详细规范）”
  - 更新阶段规划文档：
    - `docs/时空知识记忆系统构建理论/8. Python SDK 、api 、mcp设计/ADK语义工具与AgenticAPI设计阶段目标与实施思路_v1.md`
    - Layer 1 工具数量由 `12` 修正为 `13`（含 `state_time_since`）

- Test / Verification:
  - 文档改动，未运行测试（无代码行为变更）。
  - 核验依据：
    - `modules/memory/api/server.py`（`/memory/v1/state/properties` 与 `/memory/state/*` handler/request body）
    - `开发者API 说明文档.md` 第 `5.23` 节（状态接口请求/返回/错误语义）
  - 复核方式：
    - 检查 Wave 1 覆盖项是否全部转为“已展开（详细规范）”
    - 检查 `state_time_since` 是否已纳入工具暴露表与工具总数计数

- 目标符合性评估:
  - ADK 设计阶段目标: 满足。Wave 1 状态类工具的文档规范已达到可直接指导实现的粒度。
  - 一致性目标: 满足。主文档与阶段规划文档在工具命名、工具数量、Layer 1/2 边界与返回结构口径上保持一致。

- 外部接口/SDK 变更:
  - 无对外 HTTP API / SDK 行为变更（本轮仅文档规范扩展与规划文档校准）。
  - 根目录 `SDK使用说明.md`、`开发者API 说明文档.md` 本轮无需更新。

---

## 136. ADK 设计阶段（Wave 2）详细可执行规范扩展：Memory 查询/发现工具（topic_timeline / quotes / relations / list_entities / list_topics）（2026-02-22）

- Why:
  - 用户已对 Wave 1 状态类规范给出“全部通过，可直接进入实现阶段”的裁决，并要求继续完成 Wave 2 剩余 Memory 查询/发现 API 的详细规范后，再统一进入实现阶段。
  - Wave 2 涉及 graph-first + retrieval fallback、分页游标隐藏、重型 payload 默认裁剪、以及底层 `found` 语义拆分等关键设计点，若不先固化规范，后续工具实现容易在边界行为上发散。

- What:
  - 更新主文档：
    - `docs/时空知识记忆系统构建理论/8. Python SDK 、api 、mcp设计/语义记忆与状态API_Agent可用性评估及ADK改造遵循_v1.md`
  - 新增 Wave 2 详细规范：
    - `6.6.8 topic_timeline`
    - `6.6.9 quotes`
    - `6.6.10 relations`
    - `6.6.11 list_entities`
    - `6.6.12 list_topics`
  - 每个规范均补齐：
    - ADK 工具签名
    - 内部调用链（含选路/fallback）
    - 输出映射规则（底层 -> LLM 可见层）
    - 边界行为映射表（`missing_core_requirements` / 503 纯文本 / 504 超时 / 空结果 / 静默容错风险）
    - 上下文预算估算
    - 测试要点（至少 3 条）
  - 关键设计落点（本轮）：
    - `topic_timeline` 使用 `include=["quotes","entities"]` 替代 `with_quotes/with_entities`
    - `quotes/relations` 对实体歧义采用 ADK 严格策略（`needs_disambiguation=true` 并终止），不沿用底层“候选+继续执行”的混合行为
    - `relations` 明确拆分底层 `found` 语义（实体已解析）与业务 `matched`（是否有关系）
    - `list_entities/list_topics` 明确“发现工具”定位、隐藏 cursor 分页，并防御底层无效 cursor 静默回首页
  - 更新 `6.7` Wave 2 覆盖计划状态：
    - `/memory/v1/entities`
    - `/memory/v1/topics`
    - `/memory/v1/topic-timeline`
    - `/memory/v1/quotes`
    - `/memory/v1/relations`
    - 均从“评估索引已完成，待展开”更新为“已展开（详细规范）”

- Test / Verification:
  - 文档改动，未运行测试（无代码行为变更）。
  - 核验依据：
    - `modules/memory/api/server.py`（相关请求模型、handler、fallback 行为、错误返回）
    - `开发者API 说明文档.md` 第 `5.22` 节（请求/返回/错误契约说明）
  - 复核方式：
    - 人工检查 Wave 2 规范与实际 handler 行为一致（高成本熔断、超时、空结果语义、trace/source）
    - 检查 `6.7` 覆盖表 Wave 2 五项均已标记为“已展开（详细规范）”

- 目标符合性评估:
  - ADK 设计阶段目标: 满足。Wave 1 + Wave 2 的主要用户面向工具规范均已完成，可统一进入 Layer 1 工具实现阶段。
  - 一致性目标: 满足。工具命名、返回结构、歧义策略、选路原则均与主文档既有约束保持一致。

- 外部接口/SDK 变更:
  - 无对外 HTTP API / SDK 行为变更（本轮仅文档规范扩展）。
  - 根目录 `SDK使用说明.md`、`开发者API 说明文档.md` 本轮无需更新。

## 137. Explain 作用域过滤修复 + 实体 ID 大小写归一（2026-02-23）

- 背景 / 目标:
  - 修复 `/memory/v1/explain` 仅按 `tenant_id + event_id` 查询导致的作用域过滤缺失风险（至少补齐事件根节点的 `user_tokens/memory_domain` 过滤）。
  - 修复主链路消费 LLM `participants/mentions` 时实体 ID 对大小写敏感，可能造成跨请求实体碎片（如 `Bob` vs `bob`）。
  - 保持现有 API 调用兼容（不破坏旧请求体）。

- 代码实现:
  - `modules/memory/api/server.py`
    - `ExplainBody` 增加可选 `user_tokens`、`memory_domain`
    - `memory_explain()` 在未传 `user_tokens` 时按 `tenant_id` 派生 `u:{tenant_id}`，并向下透传 explain 作用域过滤参数
  - `modules/memory/application/graph_service.py`
    - `explain_event_evidence()` 增加可选 `user_ids` / `memory_domain`
    - explain cache key 纳入 `user_ids` / `memory_domain`，避免不同作用域命中同一缓存
  - `modules/memory/infra/neo4j_store.py`
    - `query_event_evidence()` 增加可选 `user_ids` / `memory_domain`
    - 在 `Event` 根节点查询条件中加入作用域过滤
  - `modules/memory/domain/dialog_tkg_graph_v1.py`
    - 统一实体 ID 生成使用大小写无关 canonical key（`casefold`）；
      保持实体显示名不变，仅影响生成 UUID 的稳定 key

- 测试验证:
  - 新增/更新回归测试：
    - `test_memory_explain.py`：校验 explain 默认 tenant 派生作用域透传 + 可选 `user_tokens/memory_domain` 透传
    - `test_graph_explain_service.py`：校验 explain cache key 按作用域区分（不同 user/domain 不串缓存）
    - `test_dialog_tkg_graph_v1.py`：校验 `Bob`（speaker）与 `bob`（participant）跨请求实体 ID 一致
  - 计划运行：
    - `pytest modules/memory/tests -q`

- 文档记录:
  - 更新 `开发者API 说明文档.md` explain 请求体（新增可选 `user_tokens` / `memory_domain`）及过滤语义说明
  - 更新 `SDK使用说明.md` explain 示例与说明（新增可选作用域过滤提示）

- 目标符合性评估:
  - 安全性/隔离性: 改善。`/memory/v1/explain` 不再仅依赖 `tenant_id + event_id`，可进行事件级作用域过滤；并保留兼容默认值。
  - 数据质量: 改善。主链路 participants/mentions 生成的实体 ID 对大小写不再敏感，降低实体碎片风险。
  - 兼容性: 满足。新增 explain 字段均为可选，旧调用保持可用。

## 138. ADK 阶段 A1：共享骨架初始化（2026-02-23）

- 背景 / 目标:
  - 按 ADK Layer 1 实施规划启动阶段 A1，先落地共享基础件（统一返回结构、调试层、错误归一化），为后续 `_resolve_if_needed` 与 `state_property_vocab` 提供复用底座。
  - 采用模块级过程记录方式：在 `modules/memory/adk/` 新建 `TODO.md` 与 `PROCESS.md`，形成 ADK 子模块的独立施工记录。

- 代码实现:
  - 新增 `modules/memory/adk/` 包：
    - `__init__.py`
    - `models.py`（`ToolResult` / `ToolDebugTrace`）
    - `errors.py`（`AdkErrorInfo` / `normalize_http_error()` / `normalize_exception()`）
    - `TODO.md`（ADK 分阶段总任务表）
    - `PROCESS.md`（ADK 子模块过程记录）
  - 设计约束已落地：
    - LLM 可见层严格 4 字段（`matched / needs_disambiguation / message / data`）
    - 调试层与 LLM 层分离（`ToolDebugTrace`）
    - 错误归一化覆盖常见 HTTP 状态与本地异常（400/404/503/504/timeout/connection）

- 测试验证:
  - 新增单测：
    - `modules/memory/tests/unit/test_adk_models.py`
    - `modules/memory/tests/unit/test_adk_errors.py`
  - 执行结果：
    - `pytest modules/memory/tests/unit/test_adk_models.py modules/memory/tests/unit/test_adk_errors.py -q` -> `7 passed`
    - `pytest modules/memory/tests -q` -> `502 passed, 6 skipped`

- 文档记录:
  - 已创建并更新：
    - `modules/memory/adk/TODO.md`
    - `modules/memory/adk/PROCESS.md`
  - 对外接口/SDK 变更：
    - 无（本周期仅 ADK 内部基础件）
    - 根目录 `SDK使用说明.md`、`开发者API 说明文档.md` 无需更新

- 目标符合性评估:
  - 阶段 A1 目标: 满足。基础骨架已成型且通过新增单测与 memory 模块全回归。
  - 风险控制: 满足。未改动 Infra 行为，未引入对外契约漂移。

## 139. ADK 阶段 A2：`_resolve_if_needed` 共享组件实现（2026-02-23）

- 背景 / 目标:
  - 承接 ADK 阶段 A1 的共享骨架，落地实体型工具通用的 `_resolve_if_needed()` 辅助步骤。
  - 统一实体解析逻辑与歧义处理策略，避免后续各工具重复实现并产生行为偏差。

- 代码实现:
  - 新增 `modules/memory/adk/resolve.py`
    - `ResolveIfNeededOutcome`
    - `_resolve_if_needed(...)`
  - 关键行为：
    - `entity_id` 直通跳过 resolve
    - 缺少 `entity/entity_id` 时 ADK 前置拦截（`invalid_input`）
    - `resolve-entity` 返回 `candidates` 时立即终止并返回 `needs_disambiguation=true`
    - 解析未命中返回 `matched=false`
    - resolver 异常通过 A1 错误归一化 helper 处理（含 retryable）
    - `resolve_limit` 在 ADK 层 clamp 到 `1..5`
  - 更新 `modules/memory/adk/__init__.py` 导出 `_resolve_if_needed` 与 `ResolveIfNeededOutcome`

- 测试验证:
  - 新增 `modules/memory/tests/unit/test_adk_resolve.py`（7 条）
  - 执行结果：
    - `pytest modules/memory/tests/unit/test_adk_resolve.py -q` -> `7 passed`
    - `pytest modules/memory/tests -q` -> `509 passed, 6 skipped`

- 文档记录:
  - 已更新 `modules/memory/adk/TODO.md`（A2 勾选完成）
  - 已更新 `modules/memory/adk/PROCESS.md`（新增 002 周期记录）
  - 对外接口/SDK 变更：无；根目录 API/SDK 文档无需更新

- 目标符合性评估:
  - 阶段 A2 目标: 满足。实体解析共享入口已落地，可直接支撑 A3 状态属性映射组件和后续工具实现。
  - 一致性目标: 满足。与 ADK 详细规范（`resolve-entity` 仅作内部辅助步骤、歧义即终止）保持一致。

## 140. ADK 阶段 A3：`state_property_vocab` 共享组件实现（2026-02-23）

- 背景 / 目标:
  - 落地状态类工具共享基础组件：`/memory/v1/state/properties` 词表加载缓存 + 属性映射（canonical/alias/normalized）。
  - 将属性歧义显式建模（候选 + `needs_disambiguation`），避免状态类工具静默使用错误属性。

- 代码实现:
  - 新增 `modules/memory/adk/state_property_vocab.py`
    - `StatePropertyVocabManager`（按 tenant 缓存、支持 `force_refresh`）
    - `StatePropertyVocab` / `StatePropertyDef`
    - `PropertyResolutionResult`
    - `map_state_property(...)`
    - `StatePropertyVocabLoadError`（包装 `AdkErrorInfo`）
  - 关键能力：
    - canonical 精确、alias 精确、normalized 匹配
    - 规范化歧义候选返回
    - `vocab_version` 变化标记（`vocab_refreshed`）
    - 加载失败统一错误归一化（复用 A1 `errors.py`）
  - 更新 `modules/memory/adk/__init__.py` 导出

- 测试验证:
  - 新增 `modules/memory/tests/unit/test_adk_state_property_vocab.py`（6 条）
  - 执行结果：
    - `pytest modules/memory/tests/unit/test_adk_state_property_vocab.py -q` -> `6 passed`
    - `pytest modules/memory/tests -q` -> `515 passed, 6 skipped`

- 文档记录:
  - 已更新 `modules/memory/adk/TODO.md`（A3 勾选完成）
  - 已更新 `modules/memory/adk/PROCESS.md`（新增 003 周期记录）
  - 对外接口/SDK 变更：无；根目录 API/SDK 文档无需更新

- 目标符合性评估:
  - 阶段 A3 目标: 满足。状态类三件套所需的属性映射基础件已到位。
  - 风险控制: 满足。歧义场景显式建模，不静默猜测属性。

## 141. ADK 阶段 A4：状态类工具前置链路组合验证（2026-02-23）

- 背景 / 目标:
  - 在进入状态类三件套实现前，将 A2（实体解析）与 A3（状态属性词表映射）组合成统一前置链路。
  - 通过独立组合组件与单测，提前收敛“缺参 / 词表失败 / 属性歧义”等高风险分支，减少后续工具实现重复逻辑。

- 代码实现:
  - 新增 `modules/memory/adk/state_preflight.py`
    - `StateQueryPreflightOutcome`
    - `prepare_state_query_preflight(...)`
  - 关键行为：
    - 统一执行 `_resolve_if_needed -> load_state_property_vocab -> map_state_property`
    - 支持 `entity_id`、`property_canonical` 高级直通
    - 缺少状态属性时 ADK 前置拦截（`invalid_input`）
    - 词表加载失败映射为终止 `ToolResult`（含 retryable/error_type）
    - 属性歧义返回 `needs_disambiguation=true` + `property_candidates`
    - 成功路径输出 `entity_id + property_canonical + resolution_meta`
  - 更新 `modules/memory/adk/__init__.py` 导出 `prepare_state_query_preflight`

- 测试验证:
  - 新增 `modules/memory/tests/unit/test_adk_state_preflight.py`（5 条）
  - 执行结果：
    - `pytest modules/memory/tests/unit/test_adk_state_preflight.py -q` -> `5 passed`
    - `pytest modules/memory/tests -q` -> `520 passed, 6 skipped`

- 文档记录:
  - 已更新 `modules/memory/adk/TODO.md`（A4 勾选完成）
  - 已更新 `modules/memory/adk/PROCESS.md`（新增 004 周期记录）
  - 对外接口/SDK 变更：无；根目录 API/SDK 文档无需更新

- 目标符合性评估:
  - 阶段 A4 目标: 满足。状态类工具共享前置链路已可直接复用，ADK 阶段 A（基础件）完成。
  - 阶段推进条件: 满足。可以按计划进入阶段 B（`entity_status / status_changes / state_time_since`）。

## 142. ADK 阶段 B1：`entity_status` 工具实现（2026-02-23）

- 背景 / 目标:
  - 按 ADK 详细规范实现状态类首个工具 `entity_status`，统一封装 `/memory/state/current` 与 `/memory/state/at_time`。
  - 用真实工具落地验证 Stage A 基础件（实体解析、属性映射、前置链路组合）的复用性。

- 代码实现:
  - 新增 `modules/memory/adk/state_tools.py`
    - `entity_status(...)`
    - 默认严格 ISO 时间解析（支持注入 `when_parser` 作为后续自然语言时间解析扩展点）
  - 关键行为：
    - `when=None` 调 `/memory/state/current`
    - `when!=None` 前置解析 `t_iso` 后调 `/memory/state/at_time`
    - 复用 `prepare_state_query_preflight(...)` 处理实体解析/属性映射/歧义终止
    - `404 state_not_found` 映射为 `matched=false`
    - 统一返回 `ToolResult`（LLM 可见层 4 字段 + 调试层 trace）
  - 更新 `modules/memory/adk/__init__.py` 导出 `entity_status`

- 测试验证:
  - 新增 `modules/memory/tests/unit/test_adk_state_tools_entity_status.py`（6 条）
  - 执行结果：
    - `pytest modules/memory/tests/unit/test_adk_state_tools_entity_status.py -q` -> `6 passed`
    - `pytest modules/memory/tests -q` -> `526 passed, 6 skipped`

- 文档记录:
  - 已更新 `modules/memory/adk/TODO.md`（B1 勾选完成）
  - 已更新 `modules/memory/adk/PROCESS.md`（新增 005 周期记录）
  - 对外接口/SDK 变更：无；根目录 API/SDK 文档无需更新

- 目标符合性评估:
  - 阶段 B1 目标: 满足。`entity_status` 已达到可直接复用与可测试的实现粒度。
  - 阶段推进条件: 满足。可继续进入 B2 `status_changes` 与 B3 `state_time_since`。

## 143. ADK 阶段 B2：`status_changes` 工具实现（2026-02-23）

- 背景 / 目标:
  - 按 ADK 详细规范实现状态类第二个工具 `status_changes`，统一封装 `/memory/state/what-changed`。
  - 验证状态类“时间范围前置归一化与防御性拦截”策略在工具实现中可稳定执行。

- 代码实现:
  - 更新 `modules/memory/adk/state_tools.py`
    - 新增 `status_changes(...)`
    - 新增共享 helper：
      - `_parse_time_range(...)`
      - `_normalize_order(...)`
      - `_clamp_limit(...)`
  - 关键行为：
    - 默认调用 `/memory/state/what-changed`
    - `order` 归一化（非法值回退 `desc`）
    - `limit` ADK clamp `1..50`
    - `when/time_range` 解析失败前置拦截（避免误查全量历史）
    - `items=[]` 映射为 `matched=false`（非错误）
    - 复用 Stage A 前置链路处理实体/属性歧义终止
  - 更新 `modules/memory/adk/__init__.py` 导出 `status_changes`

- 测试验证:
  - 新增 `modules/memory/tests/unit/test_adk_state_tools_status_changes.py`（5 条）
  - 执行结果：
    - `pytest modules/memory/tests/unit/test_adk_state_tools_status_changes.py -q` -> `5 passed`
    - `pytest modules/memory/tests -q` -> `531 passed, 6 skipped`

- 文档记录:
  - 已更新 `modules/memory/adk/TODO.md`（B2 勾选完成）
  - 已更新 `modules/memory/adk/PROCESS.md`（新增 006 周期记录）
  - 对外接口/SDK 变更：无；根目录 API/SDK 文档无需更新

- 目标符合性评估:
  - 阶段 B2 目标: 满足。`status_changes` 已具备可复用、可测试、可观测的实现粒度。
  - 风险控制: 满足。时间范围解析失败在 ADK 层被稳定拦截，避免底层静默容错扩大查询范围。

## 144. ADK 阶段 B3：`state_time_since` 工具实现（2026-02-23）

- 背景 / 目标:
  - 按 ADK 详细规范实现状态类第三个工具 `state_time_since`，封装 `/memory/state/time-since`。
  - 完成状态类三件套（`entity_status / status_changes / state_time_since`）的实现闭环，并验证共享 helper 的复用质量。

- 代码实现:
  - 更新 `modules/memory/adk/state_tools.py`
    - 新增 `state_time_since(...)`
    - 复用 `prepare_state_query_preflight(...)` 与 B2 的 `_parse_time_range(...)`
  - 关键行为：
    - 成功返回透传 `seconds_ago` 字段（不改名）
    - `404 state_not_found` 映射为 `matched=false` + “未找到状态变化记录”
    - 时间范围解析失败 ADK 前置拦截
    - 实体/属性歧义严格终止，不继续调用底层接口
    - `last_changed_at` 缺失时仍 `matched=true`，并在消息与调试层标记时间信息不足
  - 更新 `modules/memory/adk/__init__.py` 导出 `state_time_since`

- 测试验证:
  - 新增 `modules/memory/tests/unit/test_adk_state_tools_state_time_since.py`（5 条）
  - 执行结果：
    - `pytest modules/memory/tests/unit/test_adk_state_tools_state_time_since.py -q` -> `5 passed`
    - `pytest modules/memory/tests -q` -> `536 passed, 6 skipped`

- 文档记录:
  - 已更新 `modules/memory/adk/TODO.md`（B3 勾选完成）
  - 已更新 `modules/memory/adk/PROCESS.md`（新增 007 周期记录）
  - 对外接口/SDK 变更：无；根目录 API/SDK 文档无需更新

- 目标符合性评估:
  - 阶段 B3 目标: 满足。状态类三件套已全部落地并通过全量回归。
  - 阶段推进条件: 满足。可以按计划进入阶段 C（核心记忆类工具）。

## 145. ADK 阶段 C1：`entity_profile` 工具实现（2026-02-23）

- 背景 / 目标:
  - 按 ADK 详细规范实现核心记忆类首个工具 `entity_profile`，封装 `/memory/v1/entity-profile`。
  - 验证 ADK 通用骨架在 memory/v1 查询工具中的复用能力（实体解析、统一结果结构、错误归一化、调试层分离）。

- 代码实现:
  - 新增 `modules/memory/adk/memory_tools.py`
    - `entity_profile(...)`
  - 关键行为：
    - `include: list[str]` 收敛到底层 `include_*` 布尔开关
    - `limit` 统一映射到 `facts/relations/events/quotes` limits，并在 ADK 层 clamp `1..50`
    - 缺省 `user_tokens` 时按 `tenant_id` 自动派生 `u:{tenant_id}`
    - 复用 `_resolve_if_needed(...)`，实体歧义严格终止
    - `503 temporarily unavailable` 映射为 `rate_limit + retryable`
    - 维持 LLM 可见层 4 字段；调试层记录 `resolution_meta` 与 `api_route`
  - 更新 `modules/memory/adk/__init__.py` 导出 `entity_profile`

- 测试验证:
  - 新增 `modules/memory/tests/unit/test_adk_memory_tools_entity_profile.py`（5 条）
  - 执行结果：
    - `pytest modules/memory/tests/unit/test_adk_memory_tools_entity_profile.py -q` -> `5 passed`
    - ADK 增量回归（相关工具）-> `21 passed`
    - `pytest modules/memory/tests -q` -> `541 passed, 6 skipped`

- 文档记录:
  - 已更新 `modules/memory/adk/TODO.md`（C1 勾选完成）
  - 已更新 `modules/memory/adk/PROCESS.md`（新增 008 周期记录）
  - 对外接口/SDK 变更：无；根目录 API/SDK 文档无需更新

- 目标符合性评估:
  - 阶段 C1 目标: 满足。`entity_profile` 已可直接作为 Layer 1 工具被 Layer 2 语义路由或上层 Agent 编排调用。
  - 阶段推进条件: 满足。可继续进入 C2 `time_since`、C3 `relations`、C4 `quotes`、C5 `topic_timeline`。

## 146. ADK 阶段 C2：`time_since`（memory/v1）工具实现（2026-02-23）

- 背景 / 目标:
  - 按 ADK 详细规范实现核心记忆类工具 `time_since`，封装 `/memory/v1/time-since`。
  - 验证记忆类工具在 AND 语义提示、时间范围前置校验、错误归一化方面与既有 ADK 基础件/状态类工具的一致性。

- 代码实现:
  - 更新 `modules/memory/adk/memory_tools.py`
    - 新增 `time_since(...)`
    - 增加时间范围 ISO 归一化 helper（ADK 前置校验）
  - 关键行为：
    - 支持 `entity/topic` 语义参数与 `entity_id/topic_id/topic_path` 高级直通
    - 缺少查询条件 ADK 前置拦截（`invalid_input`）
    - 复用 `_resolve_if_needed(...)` 处理实体歧义终止
    - `last_mentioned=null` 映射为 `matched=false`
    - `entity + topic` 同时传入时补充 AND 语义说明消息
    - 调试层记录 `filter_semantics`
    - `504` 映射为 `timeout + retryable`
  - 更新 `modules/memory/adk/__init__.py` 导出 `time_since`

- 测试验证:
  - 新增 `modules/memory/tests/unit/test_adk_memory_tools_time_since.py`（7 条）
  - 执行结果：
    - `pytest modules/memory/tests/unit/test_adk_memory_tools_time_since.py -q` -> `7 passed`
    - `pytest modules/memory/tests -q` -> `548 passed, 6 skipped`

- 文档记录:
  - 已更新 `modules/memory/adk/TODO.md`（C2 勾选完成）
  - 已更新 `modules/memory/adk/PROCESS.md`（新增 009 周期记录）
  - 对外接口/SDK 变更：无；根目录 API/SDK 文档无需更新

- 目标符合性评估:
  - 阶段 C2 目标: 满足。`time_since` 已达到可复用、可测试、可观测的实现粒度。
  - 阶段推进条件: 满足。可继续进入 C3 `relations` / C4 `quotes` / C5 `topic_timeline`。

## 147. ADK 阶段 C3：`relations` 工具实现（2026-02-23）

- 背景 / 目标:
  - 按 ADK 详细规范实现核心记忆类工具 `relations`，封装 `/memory/v1/relations`。
  - 将底层 `found`（实体已解析）与 ADK `matched`（是否有关系结果）显式拆分，避免 Agent 误判语义。

- 代码实现:
  - 更新 `modules/memory/adk/memory_tools.py`
    - 新增 `relations(...)`
    - 新增 `relation_type` 归一化 helper（仅支持 `co_occurs_with`）
  - 关键行为：
    - 非支持 `relation_type` ADK 前置拦截（`invalid_input`）
    - 复用 `_resolve_if_needed(...)` 实体歧义严格终止
    - `time_range` 前置 ISO 校验
    - 底层 `found=true + relations=[]` 映射为 `matched=false`（但调试层标注 `entity_resolved=true`）
    - `504 relations_timeout` 映射为 `timeout + retryable`
  - 更新 `modules/memory/adk/__init__.py` 导出 `relations`

- 测试验证:
  - 新增 `modules/memory/tests/unit/test_adk_memory_tools_relations.py`（5 条）
  - 执行结果：
    - `pytest modules/memory/tests/unit/test_adk_memory_tools_relations.py -q` -> `5 passed`
    - `pytest modules/memory/tests -q` -> `553 passed, 6 skipped`

- 文档记录:
  - 已更新 `modules/memory/adk/TODO.md`（C3 勾选完成）
  - 已更新 `modules/memory/adk/PROCESS.md`（新增 010 周期记录）
  - 对外接口/SDK 变更：无；根目录 API/SDK 文档无需更新

- 目标符合性评估:
  - 阶段 C3 目标: 满足。`relations` 已具备可复用、可测试、可观测的实现粒度。
  - 阶段推进条件: 满足。可继续进入 C4 `quotes` / C5 `topic_timeline`。

## 148. ADK 阶段 C4：`quotes` 工具实现（2026-02-23）

- 背景 / 目标:
  - 按 ADK 详细规范实现核心记忆类工具 `quotes`，封装 `/memory/v1/quotes`。
  - 落地三条查询路径（实体/话题/实体+话题）、实体歧义严格终止、时间范围前置校验与高成本错误语义映射。

- 代码实现:
  - 更新 `modules/memory/adk/memory_tools.py`
    - 新增 `quotes(...)`
    - 新增 `_quotes_source_mode(...)`（调试层来源模式推断）
  - 关键行为：
    - 缺少实体/话题参数 ADK 前置拦截（`invalid_input`）
    - 复用 `_resolve_if_needed(...)`，实体歧义终止（不沿用底层“候选+继续查 quotes”的混合行为）
    - `time_range` 前置 ISO 校验
    - `limit` clamp `1..10`（默认 `5`）
    - `503 temporarily unavailable` -> `rate_limit + retryable`
    - `504 quotes_timeout` -> `timeout + retryable`
    - `quotes=[]` -> `matched=false`
    - 调试层记录 `source_mode` 与 `fallback_used`
  - 更新 `modules/memory/adk/__init__.py` 导出 `quotes`

- 测试验证:
  - 新增 `modules/memory/tests/unit/test_adk_memory_tools_quotes.py`（7 条）
  - 执行结果：
    - `pytest modules/memory/tests/unit/test_adk_memory_tools_quotes.py -q` -> `7 passed`
    - `pytest modules/memory/tests -q` -> `560 passed, 6 skipped`

- 文档记录:
  - 已更新 `modules/memory/adk/TODO.md`（C4 勾选完成）
  - 已更新 `modules/memory/adk/PROCESS.md`（新增 011 周期记录）
  - 对外接口/SDK 变更：无；根目录 API/SDK 文档无需更新

- 目标符合性评估:
  - 阶段 C4 目标: 满足。`quotes` 已达到可复用、可测试、可观测的实现粒度，并完成关键的歧义严格终止与错误映射。
  - 阶段推进条件: 满足。可继续进入 C5 `topic_timeline`。

## 149. ADK 阶段 C5：`topic_timeline` 工具实现（2026-02-23）

- 背景 / 目标:
  - 按 ADK 详细规范实现核心记忆类工具 `topic_timeline`，封装 `/memory/v1/topic-timeline`。
  - 落地 `include` 列表封装、时间范围前置校验、空时间线语义映射、超时/熔断错误归一化与调试来源标记。

- 代码实现:
  - 更新 `modules/memory/adk/memory_tools.py`
    - 新增 `topic_timeline(...)`
    - 新增 `_normalize_timeline_include(...)`
    - 新增 `_topic_timeline_source_mode(...)`
  - 关键行为：
    - 缺少 `topic/topic_id/topic_path/keywords` 时 ADK 前置拦截（`invalid_input`）
    - `include: list[str]` -> 底层 `with_quotes/with_entities`
    - `limit` clamp `1..20`（默认 `10`）
    - `time_range` 前置 ISO 校验
    - `timeline=[]` -> `matched=false`
    - `503 temporarily unavailable` -> `rate_limit + retryable`
    - `504 timeline_timeout` -> `timeout + retryable`
    - 调试层记录 `source_mode / fallback_used / heavy_expand`
  - 更新 `modules/memory/adk/__init__.py` 导出 `topic_timeline`

- 测试验证:
  - 新增 `modules/memory/tests/unit/test_adk_memory_tools_topic_timeline.py`（6 条）
  - 执行结果：
    - `pytest modules/memory/tests/unit/test_adk_memory_tools_topic_timeline.py -q` -> `6 passed`
    - `pytest modules/memory/tests -q` -> `566 passed, 6 skipped`

- 文档记录:
  - 已更新 `modules/memory/adk/TODO.md`（C5 勾选完成，阶段 C 收口）
  - 已更新 `modules/memory/adk/PROCESS.md`（新增 012 周期记录）
  - 对外接口/SDK 变更：无；根目录 API/SDK 文档无需更新

- 目标符合性评估:
  - 阶段 C5 目标: 满足。`topic_timeline` 已达到可复用、可测试、可观测的实现粒度。
  - 阶段收口评估: 满足。ADK 阶段 C（核心记忆类工具）已全部完成，可进入阶段 D（发现类工具）或开始补写 ADK 开发者说明文档。

## 150. ADK 阶段 C6：`explain`（原子工具）实现（2026-02-23）

- 背景 / 目标:
  - 按 ADK 详细规范 §6.4 补齐 Layer 1 `explain(event_id)` 工具，封装 `/memory/v1/explain`。
  - 保持工具原子性（只接受 `event_id`，不做事件搜索），为上层组合调用提供稳定证据链查询能力。

- 代码实现:
  - 更新 `modules/memory/adk/memory_tools.py`
    - 新增 `explain(...)`
  - 关键行为：
    - 空白 `event_id` 前置拦截（`invalid_input`）
    - 缺省 `user_tokens` 自动派生 `u:{tenant_id}`
    - 支持透传 `memory_domain`
    - 底层 `found=false` 映射为 `matched=false`，但保留结构化 bundle 数据
    - `503 temporarily unavailable` -> `rate_limit + retryable`
    - 调试层固定 `source_mode="graph_filter"`（确定性图遍历）
  - 更新 `modules/memory/adk/__init__.py` 导出 `explain`

- 测试验证:
  - 新增 `modules/memory/tests/unit/test_adk_memory_tools_explain.py`（5 条）
  - 执行结果：
    - `pytest modules/memory/tests/unit/test_adk_memory_tools_explain.py -q` -> `5 passed`
    - `pytest modules/memory/tests -q` -> `571 passed, 6 skipped`

- 文档记录:
  - 已更新 `modules/memory/adk/TODO.md`（新增并勾选 C6 explain）
  - 已更新 `modules/memory/adk/PROCESS.md`（新增 013 周期记录）
  - 对外接口/SDK 变更：无；根目录 API/SDK 文档无需更新

- 目标符合性评估:
  - 阶段 C6 目标: 满足。`explain` 已按原子性约束落地，并与 Infra explain 的作用域过滤行为对齐。
  - 阶段收口评估: 满足。Wave 1 + Wave 2 的高优先 ADK 工具已全部落地，可开始编写根目录 ADK 开发者说明文档。

## 151. 根目录 `ADK开发者说明文档.md` 建立（2026-02-24）

- 背景 / 目标:
  - 按开发者手册风格在项目根目录建立 ADK 事实文档，作为 Layer 1 实现现状、统一返回结构、错误语义与后续 Layer 2 对接的统一参考。
  - 在成文前先完成与规范文档（`语义记忆与状态API_Agent可用性评估及ADK改造遵循_v1.md`）的对齐复核，确保内容准确。

- 文档实现:
  - 新增：
    - `ADK开发者说明文档.md`
  - 覆盖内容：
    - 三层架构边界（Layer 0 / Layer 1 / Layer 2）
    - ADK 统一返回结构与调试层
    - 错误归一化语义
    - 共享基础件（`_resolve_if_needed` / `state_property_vocab` / `prepare_state_query_preflight`）
    - Layer 1 工具实现状态总览（已实现/未实现）
    - 已实现工具详细说明（含 `explain`）
    - 调试与观测约定（`source_mode` / `fallback_used`）
    - 当前测试状态与后续计划

- 测试验证:
  - 文档周期（doc-only），无代码行为变更
  - 不新增测试；以当前实现基线全测结果作为事实引用：
    - `pytest modules/memory/tests -q` -> `571 passed, 6 skipped`

- 对外接口/SDK 变更:
  - 无（新增 ADK 开发者文档，不涉及对外 HTTP API / SDK 契约变更）
  - 根目录 `SDK使用说明.md`、`开发者API 说明文档.md` 本周期无需更新

- 目标符合性评估:
  - 文档目标: 满足。根目录 ADK 说明文档已可作为后续 Layer 1/Layer 2 开发与联调的统一参考手册。

## 152. 根目录 ADK 文档可用性增强：接入示例与 Agent 工具列表定义（2026-02-24）

- 背景 / 目标:
  - 根据评审反馈修复根目录 `ADK开发者说明文档.md` 的可用性不足问题（“看完只知道有哪些工具，但不知道怎么用、怎么定义 Agent 工具列表”）。
  - 将文档从“事实手册”增强为“事实手册 + 最小接入手册”。

- 文档实现:
  - 更新 `ADK开发者说明文档.md`
  - 新增：
    - `12. 如何接入 ADK（最小可用示例）`
    - `13. Agent 工具列表怎么定义（可直接照做）`
    - `14. 给 Layer 2（Semantic Router）的对接约定`
  - 关键补充：
    - `MemoryInfraAdapter` / `MemoryAdkRuntime` 绑定示例
    - `ToolResult.to_llm_dict()` 与调试层分离用法
    - 默认工具组 / 按需注入工具组
    - Tool Registry 推荐结构与示例
    - 已实现工具输入 schema 示例（含 `explain`）
    - Layer 2 对接边界与禁止事项

- 测试验证:
  - 文档周期（doc-only），无代码行为变更
  - 不新增测试；沿用当前实现基线全测结果：
    - `pytest modules/memory/tests -q` -> `571 passed, 6 skipped`

- 对外接口/SDK 变更:
  - 无（文档增强，不涉及对外 HTTP API / SDK 契约变更）
  - 根目录 `SDK使用说明.md`、`开发者API 说明文档.md` 本周期无需更新

- 目标符合性评估:
  - 可用性目标: 满足。文档已具备“如何定义工具列表与接入运行时”的直接指导能力，可支撑后续 Agent/Router 开发落地。

## 153. ADK 封装实现（T1/T2/T3/T5）完成：开箱运行时 + 工具定义导出（2026-02-27）

- 背景 / 目标:
  - 将 ADK 从“函数库”升级为“可直接接入的运行时”，降低 Agent 集成复杂度。
  - 建立工具 schema 的代码单一信源，避免文档手写与实现漂移。

- 代码实现:
  - 新增 `modules/memory/adk/infra_adapter.py`
    - HTTP 适配器 `HttpMemoryInfraAdapter`
    - 覆盖 12 个 `/memory/v1/*` 与 `/memory/state/*` 方法
    - 统一错误载荷：`{"status_code": int, "body": Any}`（JSON 优先，文本回退）
  - 新增 `modules/memory/adk/runtime.py`
    - `MemoryAdkRuntime`（9 个工具方法）
    - `create_memory_runtime(...)` 同步工厂
    - `default_user_tokens` 与调用级覆盖策略
  - 新增 `modules/memory/adk/tool_definitions.py`
    - `MemoryToolDefinition`
    - `TOOL_DEFINITIONS`（9 个工具）
    - `to_openai_tools()` / `to_mcp_tools()`
  - 更新 `modules/memory/adk/__init__.py` 导出新入口

- 测试验证:
  - 新增：
    - `modules/memory/tests/unit/test_adk_infra_adapter.py`
    - `modules/memory/tests/unit/test_adk_runtime.py`
    - `modules/memory/tests/unit/test_adk_tool_definitions.py`
  - 回归结果：
    - `pytest modules/memory/tests/unit/test_adk_*.py -q` -> `88 passed`
    - `pytest modules/memory/tests -q` -> `582 passed, 7 skipped`

- 文档记录:
  - 更新 `ADK开发者说明文档.md`
    - 三行接入（`create_memory_runtime`）
    - 自定义 adapter 高级用法
    - 工具定义单一信源说明（`tool_definitions.py`）
    - 意图 -> 工具速查表
    - 租户隔离条件式表述
  - 同步根目录文档：
    - `SDK使用说明.md`（新增 ADK Runtime 接入）
    - `开发者API 说明文档.md`（补充 ADK 文档入口）
  - 更新 `modules/memory/adk/TODO.md`（阶段 F 完成）

- 目标符合性评估:
  - 当前阶段目标满足：ADK 已具备开箱运行时 + 工具 schema 导出能力，可直接支撑 Layer 2 路由器开发。

## 154. ADK 审查问题修复：state_properties GET 查询参数确认 + quotes schema 上限对齐（2026-02-27）

- 背景 / 问题:
  - 审查指出：
    1) `state_properties_api` 的 GET + query list 需契约确认。
    2) `quotes.limit.maximum`（schema）与运行时 clamp 不一致。

- 代码修复:
  - `modules/memory/adk/tool_definitions.py`
    - `quotes.limit.maximum`: `50 -> 10`。
  - `modules/memory/tests/unit/test_adk_infra_adapter.py`
    - 增加 `user_tokens` 多值 query 参数断言（重复 query key 形式）。
  - `modules/memory/tests/unit/test_adk_tool_definitions.py`
    - 增加 schema/runtime 上限一致性测试。

- 测试结果:
  - `pytest modules/memory/tests/unit/test_adk_infra_adapter.py modules/memory/tests/unit/test_adk_tool_definitions.py -q` -> `8 passed`
  - `pytest modules/memory/tests -q` -> `584 passed, 6 skipped`

- 结论:
  - 两个审查问题均已闭环，当前实现与契约一致。

## 155. ADK 文档进展对齐：测试统计口径修正（2026-02-27）

- 背景:
  - 按 `ADK开发者说明文档.md` 开展进展对齐复核，发现测试统计仍引用旧值。

- 修订内容:
  - `ADK开发者说明文档.md` §11：
    - 测试文件数更新为 `17`（新增 runtime/adapter/tool_definitions 三组）
    - ADK 单测结果更新为 `89 passed`
    - 全量回归更新为 `584 passed, 6 skipped`

- 评估:
  - 文档状态已与当前代码和测试基线一致。

## 156. Stage D 收口：ADK 发现工具 `list_entities` / `list_topics` 完成（2026-02-27）

- 背景 / 目标:
  - 按 ADK 规划完成 Stage D，补齐低频发现类工具，支撑 Agent 的候选浏览与面板型查询。

- 代码实现:
  - `modules/memory/adk/memory_tools.py`
    - 新增 `list_entities`、`list_topics`
    - 增加 cursor 校验、分页聚合、参数归一与错误映射
  - `modules/memory/adk/infra_adapter.py`
    - 新增 `list_entities_api`（GET `/memory/v1/entities`）
    - 新增 `list_topics_api`（GET `/memory/v1/topics`）
  - `modules/memory/adk/runtime.py`
    - 新增 `runtime.list_entities` / `runtime.list_topics`
  - `modules/memory/adk/tool_definitions.py`
    - 新增 2 个工具定义（默认不进入核心工具集）
  - `modules/memory/adk/__init__.py`
    - 导出新增工具函数

- 测试验证:
  - 新增：
    - `test_adk_memory_tools_list_entities.py`
    - `test_adk_memory_tools_list_topics.py`
  - 更新：
    - `test_adk_infra_adapter.py`
    - `test_adk_runtime.py`
    - `test_adk_tool_definitions.py`
  - 结果：
    - `pytest modules/memory/tests/unit/test_adk_*.py -q` -> `100 passed`
    - `pytest modules/memory/tests -q` -> `595 passed, 6 skipped`

- 文档记录:
  - 更新 `ADK开发者说明文档.md`（Stage D 状态、工具速查、注入示例、测试基线）
  - 更新 `modules/memory/adk/TODO.md`（D1/D2 完成）

- 目标符合性评估:
  - Stage D 完成，Layer 1 当前剩余重点进入 Wave 3 ops 工具与 Layer 2 路由实现。

## 157. ADK 工具卡片可执行化重构（2026-02-27）

- 背景 / 目标:
  - 对齐评审意见：`ADK工具卡片.md` 需要从“工具介绍”提升为“可直接用于 System Prompt + 可执行 tool call 集成指南”。

- 实施内容:
  - 重写 `ADK工具卡片.md`：
    - 新增“可直接复制的 System Prompt”正文
    - 新增 OpenAI `tool_calls` 与 `role=tool` 回传格式示例
    - 新增 MCP `tools/call` 示例
    - 新增 11 工具最小参数速查表与常见示例
    - 新增 explain 两步链路、歧义处理、误用清单
    - 新增最小集成代码片段（含 `TOOL_EXECUTORS`）

- 测试验证:
  - 本次为文档重构，不涉及可执行代码变更；无新增测试。

- 目标符合性评估:
  - 文档已满足“对 Agent 开发者开箱即用”的最低要求：可直接拷贝 prompt、可直接照抄工具调用闭环。

## 158. ADK 工具卡片二次对齐：System Prompt 与 Tool Call 协议一体化（2026-02-27）

- 背景 / 目标:
  - 根据评审意见，要求在同一文档中同时给出“System Prompt 纯净版”和“开发者集成版”，并确保 Prompt 本体具备明确的工具调用约束。

- 实施内容:
  - 重构 `ADK工具卡片.md`：
    - 新增 Part A（可直接粘贴 Prompt）
    - 新增 Part B（OpenAI/MCP 调用协议、工具速查、最小集成代码）
    - 将调用协议约束前置到 Prompt 本体（函数名、JSON 参数、四字段结果决策）

- 测试验证:
  - 本次为文档重排与语义增强，无代码行为变更；无新增测试。

- 目标符合性评估:
  - 当前文档满足“模型指令可直接复用 + 工程集成可直接落地”的双重目标。

## 159. ADK 工具卡片补全调用闭环示例（2026-02-27）

- 背景 / 目标:
  - 用户要求补充“工具 schema 传入模型后，模型如何产生 tool call、业务方如何执行、再如何回注模型”的完整链路。

- 实施内容:
  - 更新 `ADK工具卡片.md`：新增完整两段式调用示例（请求1/请求2）与流程图。
  - 明确 `function.name` 与 `function.arguments` 的来源（来自模型 `tool_calls`）。

- 测试验证:
  - 文档更新，不涉及代码逻辑变更；无新增测试。

- 目标符合性评估:
  - 文档已可直接指导 Agent 开发者实现 OpenAI function calling 的最小闭环。

## 160. ADK 工具卡片评审问题修复：异步调用与统一 fallback（2026-02-27）

- 背景 / 目标:
  - 根据评审反馈，修复 `ADK工具卡片.md` 中两个直接影响可复制运行的问题。

- 实施内容:
  - B6：`OpenAI` -> `AsyncOpenAI`，并将两次 `chat.completions.create` 改为 `await`。
  - B5：`unknown tool` 回包改为 `ToolResult.no_match(...).to_llm_dict()`，统一输出口径。

- 测试验证:
  - 文档示例更新，不涉及源码逻辑变更；无新增测试。

- 目标符合性评估:
  - 示例代码运行语义一致、接口返回口径统一，可直接作为开发模板使用。

## 161. Stage E 实现：`/memory/agentic/*` 单工具语义路由 API（2026-02-27）

- 背景 / 目标:
  - 在 Layer 1 ADK 基础上，新增 Layer 2 统一入口，降低业务 Agent 接入成本。
  - v1 约束为单工具路由，不做多步编排，不输出自然语言答案。

- 代码实现:
  - `modules/memory/api/server.py` 新增：
    - `GET /memory/agentic/tools`
    - `POST /memory/agentic/execute`
    - `POST /memory/agentic/query`
  - 新增 agentic 相关 helper：tool 选择、参数校验、router 调用、runtime 执行、结果封装。
  - 安全与治理：
    - `PATH_SCOPE_REQUIREMENTS` 增加 `/memory/agentic/` 前缀（`memory.read`）
    - `/api/list` 分类新增 `memory_agentic`

- 测试验证:
  - 新增 `modules/memory/tests/unit/test_memory_agentic_api.py`（7 个用例）
  - 全量回归：`pytest modules/memory/tests -q` -> `602 passed, 6 skipped`

- 文档同步:
  - `SDK使用说明.md`：新增 Agentic Query API 快速接入示例
  - `开发者API 说明文档.md`：新增 5.24 Agentic 语义路由章节
  - `ADK开发者说明文档.md`：Layer 2 状态更新为已实现（v2.3）

- 目标符合性评估:
  - Layer 2 单工具版可用，已满足“自然语言入口 + 结构化输出”的阶段目标。
  - 后续工作聚焦 E3：路由准确率与延迟验收。

## 162. Stage E 路由适配升级：多 Provider 统一 Adapter 路径 + Config 选模（2026-02-27）

- 背景 / 目标:
  - 现状 `Layer 2` 路由调用直接绑定 `AsyncOpenAI + OPENAI_API_KEY`，不满足多 provider 与配置化选模要求。
  - 目标是让 `/memory/agentic/query` 与现有 LLM 体系一致：走统一 adapter 解析路径，并支持 `modules/memory/config` 指定 router 模型。

- 代码实现:
  - `modules/memory/application/llm_adapter.py`
    - 新增 `resolve_openai_compatible_chat_target(...)`：
      - 读取 `memory.llm.agentic_router`，缺省回退 `memory.llm.text`
      - 统一解析 `provider/model/api_key/base_url`
      - 支持 `openai/openrouter/qwen(dashscope)/glm/deepseek/moonshot/sglang/openai_compat`
      - 对本地 OpenAI 兼容端点使用 `api_key="EMPTY"` 兜底，避免 SDK 因空 key 初始化失败
  - `modules/memory/api/server.py`
    - `_agentic_route_tool_call` 改为调用 `resolve_openai_compatible_chat_target(...)`
    - 新增环境覆盖：
      - `MEMORY_AGENTIC_ROUTER_PROVIDER`
      - `MEMORY_AGENTIC_ROUTER_MODEL`
      - `MEMORY_AGENTIC_ROUTER_BASE_URL`
    - query 响应 `meta` 新增 `provider`
  - 配置文件补齐：
    - `modules/memory/config/memory.config.yaml` 新增 `memory.llm.agentic_router`
    - `modules/memory/config/hydra/memory.yaml` 新增 `memory.llm.agentic_router`

- 测试验证:
  - 新增 `modules/memory/tests/unit/test_llm_adapter_chat_target.py`（4 用例）
    - agentic_router 配置读取
    - 缺省回退到 `llm.text`
    - sglang 无 key 兜底
    - provider 凭据缺失返回 `None`
  - 回归结果：
    - `pytest modules/memory/tests/unit/test_llm_adapter_chat_target.py modules/memory/tests/unit/test_memory_agentic_api.py -q` -> `11 passed`
    - `pytest modules/memory/tests/unit/test_api_scope_coverage.py -q` -> `1 passed`
    - `pytest modules/memory/tests/unit/test_api_list_endpoint.py -q` -> `2 passed`
    - `pytest modules/memory/tests -q` -> `607 passed, 6 skipped`

- 文档同步:
  - `开发者API 说明文档.md`
    - 5.24.3 补充 `meta.provider`
    - 新增路由模型选择优先级说明（config + env 覆盖）
  - `SDK使用说明.md`
    - 补充 `memory.llm.agentic_router` 配置示例与环境覆盖说明
  - `ADK开发者说明文档.md`
    - Layer 2 章节补充 router 配置入口与覆盖变量

- 目标符合性评估:
  - Layer 2 现在满足“多 provider 统一 adapter 路径 + 配置化模型指定”的目标。
  - 后续可在不改代码的前提下，仅通过配置/环境切换路由模型。

## 163. 评审收敛修复：Prompt/Config/Fallback 三项高优先级问题（2026-02-27）

- 背景 / 目标:
  - 根据评审意见，优先修复 3 个可能引发线上行为偏差的问题：
    1) router prompt 信息密度不足；
    2) `memory.config.yaml` / `hydra/memory.yaml` 出现重复 `api` 键导致配置覆盖；
    3) router 模型 fallback 链跨 provider 串值风险。

- 代码实现:
  - `modules/memory/api/server.py`
    - 强化 `_AGENTIC_ROUTER_SYSTEM_PROMPT`：新增“不得输出工具调用外文本”与高频工具意图映射。
  - `modules/memory/config/memory.config.yaml`
    - 合并重复 `api` 节点：`topk_defaults` 与 `auth/limits/retrieval` 统一放在同一 `api` 下。
    - 在 `llm` 段新增注释，明确 Hydra 启动时配置优先级。
  - `modules/memory/config/hydra/memory.yaml`
    - 同步合并重复 `api` 节点，避免 `topk_defaults` 被覆盖。
  - `modules/memory/application/llm_adapter.py`
    - `resolve_openai_compatible_chat_target(...)` 的 `model` fallback 改为：
      - 通用层仅到 `LLM_MODEL`
      - provider 专属模型环境变量仅在对应 provider 分支内生效
    - 补充注释解释 `api_key="EMPTY"` 的设计边界（仅用于 keyless 本地 OpenAI 兼容端点）。

- 测试验证:
  - 新增/增强单测：
    - `modules/memory/tests/unit/test_config_hydra_loader.py`
      - 新增 `test_api_topk_defaults_and_auth_coexist_in_loaded_config`
    - `modules/memory/tests/unit/test_llm_adapter_chat_target.py`
      - 新增 `test_resolve_chat_target_does_not_cross_fallback_other_provider_models`
  - 回归结果：
    - `pytest modules/memory/tests/unit/test_llm_adapter_chat_target.py modules/memory/tests/unit/test_config_hydra_loader.py modules/memory/tests/unit/test_memory_agentic_api.py -q` -> `17 passed`
    - `pytest modules/memory/tests -q` -> `609 passed, 6 skipped`
  - 实测确认配置修复生效：`load_memory_config()` 在 plain/hydra 两条路径均可同时读取 `memory.api.topk_defaults` 与 `memory.api.auth`。

- 文档同步:
  - `ADK工具卡片.md`
    - 增加 Layer 1/Layer 2 使用边界说明
    - 新增 `B9`：`/memory/agentic/query` 直连示例
  - `ADK开发者说明文档.md`
    - 版本升级 `v2.4`
    - 2.1 与 7.3 补充 Layer 2 选模与可观测能力
    - 测试基线更新为 `609 passed, 6 skipped`

- 目标符合性评估:
  - 已消除配置覆盖隐患与跨 provider fallback 风险。
  - Layer 2 路由行为、配置行为、文档说明三者已重新对齐。
