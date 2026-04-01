# Graph v0.x — Usage Quickstart

说明：这里的 `v0.x` 指 **HTTP API 版本**（例如 `/graph/v0/*`），不是 TKG schema 版本。

适用范围：Memory 服务 Graph API v0 的写入与查询（含 TimeSlice、共现/因果、ASR/空间/状态/知识、身份治理待审），其节点/边语义以 `docs/时空知识记忆系统构建理论/3. Schema 层（What exactly in code）/TKG-Graph-v1.0-Ultimate.md` 为准。

## 端点与头
- 所有 Graph 接口需 `X-Tenant-ID` 头，禁止跨租户写/查。
- 写入：`POST /graph/v0/upsert`
  - 支持节点：MediaSegment, Evidence, UtteranceEvidence(ASR), Entity, Event, Place, TimeSlice, SpatioTemporalRegion, State, Knowledge。
  - 支持关系：SUMMARIZES, INVOLVES, OCCURS_AT, SUPPORTED_BY, NEXT_EVENT, CO_OCCURS_WITH, CAUSES, COVERS_SEGMENT, COVERS_EVENT, SPOKEN_BY, TEMPORALLY_CONTAINS, SPATIALLY_CONTAINS, HAS_STATE, DERIVED_FROM, EQUIV。
  - 身份治理：可随 upsert 上传 `pending_equivs`（待审核等价），服务端落库 PendingEquiv，后续经 admin 审批转为 EQUIV。
- 查询片段：`GET /graph/v0/segments?source_id=...&start=...&end=...&modality=...&limit=...`
- 实体时间线：`GET /graph/v0/entities/{entity_id}/timeline?limit=...`
- 事件：`GET /graph/v0/events?segment_id=...&entity_id=...&place_id=...&source_id=...&limit=...`
- 地点：`GET /graph/v0/places?name=...&segment_id=...&limit=...`
- 事件详情：`GET /graph/v0/events/{event_id}`（返回挂接的 segments/entities/places）
- 地点详情：`GET /graph/v0/places/{place_id}`（返回挂接的 events/segments）

## 依赖与前置
- Memory API（FastAPI + Uvicorn）需与 Neo4j、Qdrant 后端正常连通。
- Python 侧脚本与 fallback HTTP 写入依赖 `requests>=2.31`；若只通过 `GraphApiClient` 访问，确保该依赖已安装。
- 运行脚本前请准备 Neo4j 约束（`Neo4jStore.ensure_schema_v0` 会在服务初始化/启动时 best-effort 建索引，如失败可查看日志）以及必要的模型权重。

## 最小写入示例
```bash
cat >/tmp/upsert_demo.json <<'JSON'
{
  "segments": [
    {"id": "seg_demo", "tenant_id": "t1", "source_id": "video.mp4", "t_media_start": 0, "t_media_end": 4, "has_physical_time": false, "time_origin": "media"}
  ],
  "evidences": [
    {"id": "face_0", "tenant_id": "t1", "source_id": "video.mp4", "algorithm": "demo", "algorithm_version": "v1", "confidence": 0.9, "offset_in_segment": 0.0}
  ],
  "entities": [
    {"id": "person_1", "tenant_id": "t1", "type": "PERSON", "cluster_label": "person1"}
  ],
  "edges": [
    {"src_id": "seg_demo", "dst_id": "face_0", "rel_type": "CONTAINS_EVIDENCE", "tenant_id": "t1"},
    {"src_id": "face_0", "dst_id": "person_1", "rel_type": "BELONGS_TO_ENTITY", "tenant_id": "t1"}
  ]
}
JSON
curl -H "Content-Type: application/json" -H "X-Tenant-ID: t1" \
     -d @/tmp/upsert_demo.json \
     http://127.0.0.1:8002/graph/v0/upsert
```

## 查询示例
- 最近片段：
  `curl -H "X-Tenant-ID: t1" "http://127.0.0.1:8002/graph/v0/segments?limit=5"`
- 实体时间线：
  `curl -H "X-Tenant-ID: t1" "http://127.0.0.1:8002/graph/v0/entities/person_1/timeline"`
- 事件列表（按片段 + 实体 + 场所过滤）：
  `curl -H "X-Tenant-ID: t1" "http://127.0.0.1:8002/graph/v0/events?segment_id=seg_a&entity_id=person_1&place_id=place_lobby"`
- 场所列表（按名称模糊 + 覆盖片段过滤）：
  `curl -H "X-Tenant-ID: t1" "http://127.0.0.1:8002/graph/v0/places?name=Lobby&segment_id=seg_a"`

### 查询参数说明
| 端点 | 参数 | 说明 |
| --- | --- | --- |
| `/graph/v0/events` | `segment_id` | 仅返回通过 `SUMMARIZES` 关联的目标片段事件 |
|  | `entity_id` | 仅返回 `INVOLVES` 指向该实体的事件 |
|  | `place_id` | 仅返回 `OCCURS_AT` 指向该地点的事件 |
|  | `source_id` | 仅返回关联媒体源的事件（需事件存在 `SUMMARIZES` → `MediaSegment`） |
|  | `relation` | 过滤事件间关系（如 `NEXT_EVENT`/`CAUSES`） |
|  | `layer` | 过滤边层级（`fact`/`semantic`/`hypothesis`） |
|  | `status` | 因果候选状态（`candidate`/`accepted`/`rejected`） |
| `/graph/v0/places` | `name` | 模糊匹配（忽略大小写） |
|  | `segment_id` | 仅返回包含该片段的地点（经事件 → 片段链路） |
|  | `covers_timeslice` | 仅返回被指定 TimeSlice 覆盖的地点 |
|  | `limit` | 上限 500 条，默认 100 |
| `/graph/v0/timeslices` | `kind` | `physical`/`media`/`logical` |
|  | `covers_segment` | 按覆盖的 MediaSegment 过滤 |
|  | `covers_event` | 按覆盖的 Event 过滤 |

## 管理端构建与身份治理端点（需认证）

- 事件链/因果生成  
  `POST /graph/v0/admin/build_event_relations`  
  Body: `{"source_id": str|null, "place_id": str|null, "limit": 1000, "create_causes": true}`  
  效果：按 t_abs_start 排序生成 NEXT_EVENT(kind=observed, layer=fact)，同地点相邻生成 CAUSES(status=candidate, layer=hypothesis)。

- 时间窗口切片  
  `POST /graph/v0/admin/build_timeslices`  
  Body: `{"window_seconds": 3600.0, "source_id": str|null, "modality": str|null, "modes": ["media_window","day","hour"]}`  
  效果：按媒体时间窗口/小时/天分桶 MediaSegment，创建 TimeSlice(kind=media_window/media_hour/media_day) + COVERS_SEGMENT。

- 共现聚合  
  `POST /graph/v0/admin/build_cooccurs`  
  Body: `{"min_weight": 1.0, "mode": "timeslice" | "event"}`  
  效果：  
  - `mode=timeslice`：基于 TimeSlice 覆盖聚合 CO_OCCURS_WITH（weight 累加，layer=semantic, kind=timeslice）。  
  - `mode=event`：基于 Event 共现聚合 CO_OCCURS_WITH（weight=事件共现次数，layer=semantic, kind=event）。  

- 身份治理（v0.4 起步）  
  - `POST /graph/v0/admin/equiv/pending`：写入待审等价候选（仅租户注入，需 auth）。
  - `GET /graph/v0/admin/equiv/pending`：按 status（pending/approved/rejected）列出，默认 pending。
  - `POST /graph/v0/admin/equiv/approve`：审批通过，生成 EQUIV 边（同租户）。
  - `POST /graph/v0/admin/equiv/reject`：拒绝，更新 PendingEquiv 状态。

- 物化门控（v0.5 起步）  
  - 配置（环境变量或服务初始化）：`GRAPH_GATING_CONFIDENCE_THRESHOLD`、`GRAPH_GATING_IMPORTANCE_THRESHOLD`、`GRAPH_GATING_REL_TOPK`。  
  - 行为：低于置信/重要度阈值的事件/关系不写入；同源关系按 weight/置信排序保留 top-K，默认 top-K=100（可调）。  
  - Soft TTL：Neo4j 查询已加 `expires_at > now` 软过滤；Provenanced 字段增加 `memory_strength/last_accessed_at/expires_at/forgetting_policy` 以支撑衰减/过期策略；Qdrant 过滤已接入。  
  - 触达/延寿：搜索命中可触发 GraphService.touch，支持节流（`GRAPH_TOUCH_MIN_INTERVAL_S`、`GRAPH_TOUCH_MAX_BATCH`）、可选延寿秒数（`GRAPH_TOUCH_EXTEND_SECONDS`）；需配置触达租户 `GRAPH_TOUCH_TENANT_ID` 或在服务层调用 `set_graph_tenant`。
  - 衰减排序：`GRAPH_DECAY_HALF_LIFE_DAYS` 控制半衰期（默认 1 天）；节点可携带 `memory_strength` 作为个体半衰期放大因子。

- TTL 清理与导出（v0.5c 起步）  
  - `POST /graph/v0/admin/ttl/cleanup`：按租户清理过期节点/边（基于 ttl+created_at，支持 buffer_hours、limit、dry_run，需 auth）。  
  - `GET /graph/v0/admin/export_srot`：导出 `(subject, relation, object, time_origin, t_ref)` 视图，支持 rel 列表与 min_confidence 过滤。
  - 清理策略：提供干跑模式（dry_run）预览删除数量；Reaper 仍为基础版本，生产需配合备份/权限管控。

> 提示：生产环境必须开启 auth + token→tenant 映射；admin 端点仅供受控场景使用。

## 流水线对接（memorization_agent）
- `routing_ctx.tenant_id` 必填；`memory_api_url` 指向 Memory API（含端口）。
- 切片输出包含 `segment_id/source_id/start/end`，用于写 MediaSegment/NEXT_SEGMENT。
- 检测结果放 `ctx["detections"]`：dict，键为类型（如 `face`/`object`），值为列表，字段至少 `id` 与 `clip_id`（或 `segment_id`），可选 `score`/`bbox`/`timestamp`/`model`/`version`/`text`。
- 聚类结果放 `ctx["clusters"]`：列表，每项含 `id`（实体）、`type`（PERSON/OBJECT/PLACE/OTHER）、`evidence_ids`（挂到 BELONGS_TO_ENTITY），可选 `label`/`name`/`score`。
- `step_write_memory` 会自动构建 MediaSegment/NEXT_SEGMENT、Evidence/CONTAINS_EVIDENCE、Entity/BELONGS_TO_ENTITY 并调用 `/graph/v0/upsert`。

## 工具脚本
- `scripts/graph_v0_ingest_video.py`：按时间窗切视频写 MediaSegment+NEXT_SEGMENT。
- `scripts/run_pipeline_stub.py`：轻量假检测/聚类 → graph upsert → 打印实体时间线。

## 注意
- v0.1 流水线（`step_write_memory`）已默认写 Event/Place 以及 `SUMMARIZES` / `INVOLVES` / `OCCURS_AT`，确保 `ctx["scene_labels"]` 与 `semantic_objects` 结构填充。
- 任何写入/查询都强制匹配 `tenant_id`，请求头缺失会被拒绝。

## Schema 字段字典

| 节点 | 字段 | 类型 | 说明 |
| --- | --- | --- | --- |
| `MediaSegment` | `id` | str | 片段主键（`clip_id::segment_idx`） |
|  | `source_id` | str | 原视频/音频源标识 |
|  | `t_media_start` / `t_media_end` | float | 媒体时间轴（秒） |
|  | `modality` | str | `video`/`audio`/`text`/`mixed` |
| `Evidence` | `algorithm` / `version` | str | 检测器信息 |
|  | `confidence` | float | 0~1 |
|  | `offset_in_segment` | float | 相对片段秒数 |
| `Entity` | `type` | str | `PERSON` / `OBJECT` / `PLACE` / `OTHER` |
|  | `cluster_label` | str | 聚类标签 |
| `Event` | `summary` | str | 语义概述 |
|  | `t_abs_start` / `t_abs_end` | datetime | 绝对时间，可为空 |
|  | `importance` | int | 0~10 重要性等级 |
| `Place` | `name` | str | 地点名称 |
|  | `area_type` | str | 业务自定义（如 LAB/ROOM） |

| 边 | 方向 | 说明 |
| --- | --- | --- |
| `NEXT_SEGMENT` | `MediaSegment -> MediaSegment` | 时间顺序 |
| `CONTAINS_EVIDENCE` | `MediaSegment -> Evidence` | 片段包含的检测结果 |
| `BELONGS_TO_ENTITY` | `Evidence -> Entity` | 检测归属实体 |
| `SUMMARIZES` | `Event -> MediaSegment` | 事件总结的片段 |
| `INVOLVES` | `Event -> Entity` | 事件涉及的实体 |
| `OCCURS_AT` | `Event -> Place` | 事件发生地点 |
| `NEXT_EVENT` | `Event -> Event` | 事件时间序列（可带 kind/layer/status/confidence） |
| `CO_OCCURS_WITH` | `Entity -> Entity` | 实体共现（语义层） |
| `CAUSES` | `Event -> Event` | 因果候选/假设（status/layer 控制） |
| `SUPPORTED_BY` | `Event|Entity -> Evidence` | 审计/证据绑定 |
| `COVERS_SEGMENT`/`COVERS_EVENT` | `TimeSlice -> MediaSegment|Event` | TimeSlice 覆盖关系 |

## 版本治理
- Graph schema 采用 SemVer：`v0.1.x` 为兼容版本，仅在 `GraphUpsertRequest` 发生破坏性变更时才升 `0.2.0`。
- **新增字段**：只能追加可选字段；旧客户端不需要修改。
- **弃用字段**：以 `DeprecationWarning` + 文档标记提醒，至少保留两个次版本。
- HTTP 端点路径固定在 `/graph/v0/*`，一旦需要破坏性行为（字段语义/返回结构变化），通过新增 `/graph/v1/*` 端点承载，旧版本持续可用。

## 服务边界与演进策略

- GraphService：专注 TKG v0.1/v0.2 Schema（MediaSegment/Evidence/Entity/Event/Place/TimeSlice + v0.2 边），负责严格租户/时间校验、图写入与查询。与 Neo4j 直接交互。
- MemoryService：统一记忆检索（向量 + 老图邻域）。不直接处理 v0.2 高阶边，保持现有接口兼容。
- 并行模式：短期两者并行，编排层按需调用 GraphService 获取 TKG 能力；MemoryService 继续承担主搜索/写入职责。
- 演进：如需统一，可在上层编排组合；避免 GraphService 反向调用 MemoryService 以免循环依赖。
