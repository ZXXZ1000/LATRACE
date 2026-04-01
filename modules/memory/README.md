# Memory（统一记忆服务：向量 + 图）

一句话：Memory 是一套“可治理、可解释、可演进”的记忆底座。它把 **向量召回（Qdrant）** 和 **时空知识图（Neo4j）** 合在一起，对上层暴露稳定的 `/search` `/write` 等接口，同时允许在其上构建更高层的编排 API（但不破坏底座契约）。

---

## 你应该从哪里开始读

- 文档索引（推荐从这里开始）：`modules/memory/docs/00_INDEX.md`
- Quickstart（V2，当前推荐）：`modules/memory/docs/API_QUICKSTART_v2.md`
- 图模型与图扩展（V1）：`modules/memory/docs/GRAPH_v1.md`

---

## 能力边界（别幻想）

- Memory 不是“万能推理机”。它的工作是：**把可检索的证据找出来，并把证据组织得更可解释**。
- 图扩展是受限的邻域展开器（默认 2–3 hop），用于补全“谁/何时/何地/因果/共现”的证据链；不是让你在图里做无限游走。

---

## 对外稳定面（v1.0 冻结面）

### 稳定 HTTP API（跨进程）

- 读写：`POST /search` `POST /write` `POST /update` `POST /delete` `POST /link` `POST /rollback`
- 图：`/graph/v0/*`（仍视为 v0 代际的一部分，但保持兼容）
- 运行态：`GET /health` `GET /metrics_prom` + 若干 `/config/*` 热配置端点

### 稳定 Python API（同进程）

从包入口 `modules.memory` 导入（禁止深层导入）：
- 合同模型：`MemoryEntry` `Edge` `SearchFilters` `SearchResult` `Version`
- 服务：`MemoryService` `GraphService`
- 工厂：`create_service()`（读取 `modules/memory/config/memory.config.yaml` + env）

> 破坏性变更不会改旧接口，而是新增版本化路径/方法承载（Never break userspace）。

---

## V2：高层编排 API（客户端库，无新端口）

这是上层（Control / QA / Benchmark / 产品）最应该依赖的两个门面：

- `memory.session_write(...)`
  - 文本/对话 →（可选 LLM 抽取）→ 调用现有 `POST /write`
  - 支持 BYOK：可传用户自带 `llm_provider/llm_api_key/llm_model`
  - 未提供 LLM 时按 `llm_policy=require|best_effort` 决定报错或退化写入
- `memory.retrieval(...)`
  - 高级检索编排（如 3 路并行检索 + 融合 + 可选 rerank + debug）
  - 底层只调用现有 `POST /search`（1 次或多次）

目标不是“堆功能”，而是把上层最容易写错的东西（隔离、检索融合、可选 rerank）收口到一个稳定门面里。

---

## 隔离与降噪：必须分清楚

你至少要理解 4 个键：

- **tenant（租户）**：Header `X-Tenant-ID` + `filters.tenant_id`（两者都要有）
- **user_id（强隔离主轴）**：`metadata.user_id: list[str]` + `filters.user_match=all`（推荐用 token：`u:`/`p:`/`d:`/`pub`）
- **memory_domain（域）**：`dialog` / `video` / `work`… 用于降噪与治理
- **run_id / memory_scope（更细粒度隔离）**：会话级/样本级/视频级隔离

如果你把 “scope 回退链路” 当成隔离手段，你迟早会串数据。

---

## 两类 Key：产品 APIK vs BYOK

- **产品 APIK（我们的 key）**：用于用户在不同 MCP 客户端/设备上访问 Memory，解决“鉴权 + 用户身份来源 + 审计/限流”。
  - 推荐生产开启 `memory.api.auth.enabled=true`，客户端走 `X-API-Token: <APIK>`；
  - 注意：当前实现不解析 `Authorization: Bearer ...`，token/JWT 必须放在 `X-API-Token`（或配置指定的 header）里；
  - 但数据隔离仍通过 `metadata.user_id[]` 的 token（`u:`/`p:`/`d:`/`pub`）落实。
- **BYOK（用户自带模型 key）**：仅用于抽取与 rerank（客户端库侧），不落库、不进后端。

外接 SaaS/IdP 尚未确定时，建议把“身份提供方”视为可插拔：

- Memory 冻结的最小合同只包含：`tenant_id`（可配置 claim 名）与 `sub`；
- 最稳做法是在网关层统一验签与 claims 归一化（签发你们的内部 JWT），Memory 只认内部 JWT，后续更换 SaaS 不动 Memory。

---

## 目录速览（按职责）

- `modules/memory/contracts/`：对外数据契约（Pydantic models）
- `modules/memory/api/`：FastAPI HTTP 服务
- `modules/memory/application/`：用例编排（search/write 主流程、缓存、治理）
- `modules/memory/infra/`：Qdrant/Neo4j/Audit 等出站适配
- `modules/memory/docs/`：模块文档（V2 文档从 `00_INDEX.md` 开始）
- `modules/memory/tests/`：单测/集成测试
