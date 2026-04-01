# Memory API Quickstart（V2）

本文档只做三件事：
1) 把 Memory API 启起来；  
2) 用**正确的隔离键**写入/检索，保证“不串数据”；  
3) 给上层一个“够用、可演进”的高层编排入口：`memory.session_write(...)` / `memory.retrieval(...)`（客户端库，无新端口）。

---

## 0. 你需要先接受的现实（否则你会一直踩坑）

### 0.1 Tenant：开发/评测模式 vs 生产模式

这点是现状，不是理论：

- **开发/评测模式（默认）**：`memory.api.auth.enabled=false`
  - **必须**带 `X-Tenant-ID` 请求头，否则 400；
  - `POST /search` 不会自动把 header 注入 filters，所以**强烈建议**你也显式带上 `filters.tenant_id=<tenant>`，避免未来切换到 auth 模式或导入多租户数据后出现“串租户”的隐患。
- **生产模式（推荐）**：`memory.api.auth.enabled=true`
  - tenant 由 token/JWT 解析得到，不再依赖 `X-Tenant-ID`；
  - 仍建议在客户端/网关层显式记录 tenant（便于审计与排障），但不要把它当成唯一可信来源。

### 0.2 user_id 是“强隔离主轴”，scope 只是“降噪回退”

- 强隔离：`filters.user_id` + `filters.user_match=all`  
- 降噪回退：`scope=session|domain|user|global`（按配置回退链路尝试召回）

---

## 1. 启动服务（本地）

### 1.1 依赖（你自己确认）

- Python >= 3.12（本项目使用 `uv`）
- Qdrant（向量库）
- Neo4j（图存储，若你仅跑“纯向量”也可以先不接，但很多图能力会失效）

### 1.2 启动 Memory API

在仓库根目录执行：

```bash
uv run python -m modules.memory.api.server
```

默认配置文件：`modules/memory/config/memory.config.yaml`  
（可用 `MEMORY_CONFIG_PROFILE=production` 切生产姿态配置；生产会打开更多安全门控。）

健康检查：

```bash
curl -sS http://127.0.0.1:8000/health
```

---

## 2. HTTP：最小正确调用（写入 / 检索）

下面的例子刻意写得“啰嗦”，因为你只要漏掉一个隔离键，结果就会随机变坏。

### 2.1 写入（POST `/write`）

```bash
curl -sS http://127.0.0.1:8000/write \
  -H 'Content-Type: application/json' \
  -H 'X-Tenant-ID: demo' \
  -d '{
    "entries": [
      {
        "kind": "semantic",
        "modality": "text",
        "contents": ["用户喜欢科幻电影"],
        "metadata": {
          "user_id": ["u:alice"],
          "memory_domain": "dialog",
          "run_id": "run-001",
          "source": "manual"
        }
      }
    ],
    "upsert": true
  }'
```

说明：
- `X-Tenant-ID`：租户边界（默认 auth 关闭时必填）。
- `metadata.user_id`：强隔离 token（推荐使用 `u:<user_id>` 规范化；支持多 token）。
- `metadata.memory_domain/run_id`：用于检索降噪与回退链路。

### 2.1.1 生产姿态的额外要求（可选）

在生产配置下你可能会打开（推荐这么干）：

- `memory.api.auth.enabled=true`：要求 `X-API-Token`（见 `modules/memory/config/memory.config.yaml`）
- `memory.api.auth.signing.required=true`：写/删/连边等敏感请求要求签名
  - `X-Signature-Ts` + `X-Signature`（HMAC-SHA256，payload 为 `"{ts}.{path}.{body}"`）

本 quickstart 默认以“本地开发/评测姿态”为准（auth/signing 关闭），但文档里所有隔离键（tenant/user_id/domain/run_id）在生产一样成立。

重要：当前实现默认读取 `X-API-Token`（或你在配置里指定的 header），同时也支持回退解析 `Authorization: Bearer ...`。如果你走内网网关，仍建议统一转发为 `X-API-Token`，这样和现有签名/转发辅助逻辑最一致。

### 2.1.2 产品 APIK（用户隔离）怎么用？（你说的“不是 BYOK 的 key”）

你提到的 **APIK**，本质是“用户访问 Memory 的产品 key”，用于：

- 在不同 MCP 客户端/不同设备上，稳定标识同一个用户（隔离身份来源）；
- 作为 Memory 服务的访问凭证（鉴权/限流/审计）。

约定（V2 文档层先冻结这条，代码实现后续跟上）：

- **APIK ≠ BYOK**：它不用于调用大模型，不参与抽取/rerank。
- 生产启用 auth 后，客户端应携带：
  - `X-API-Token: <APIK>`
- “用户隔离”仍然要落实到检索 filters 上：
  - 客户端库把 APIK 映射为稳定的 `user_tokens`（建议不要直接把原始 key 明文当 user_id；至少做一次不可逆映射/UUID）
  - 例如：`user_tokens=["u:{user_uuid}", "p:{product_id}", "d:{device_id}"]` + `user_match="all"`

> 说白了：APIK 解决“你是谁 + 你有没有权限”；`user_tokens` 解决“你能看到哪一份数据”。

### 2.2 检索（POST `/search`）

```bash
curl -sS http://127.0.0.1:8000/search \
  -H 'Content-Type: application/json' \
  -H 'X-Tenant-ID: demo' \
  -d '{
    "query": "我喜欢什么电影？",
    "topk": 10,
    "expand_graph": true,
    "filters": {
      "tenant_id": "demo",
      "user_id": ["u:alice"],
      "user_match": "all",
      "memory_domain": "dialog",
      "run_id": "run-001"
    }
  }'
```

注意：
- `filters.tenant_id` 必填（否则你在多租户数据里会乱套）。
- 单对话隔离：把 `run_id` 也放进去，并且 `scope="session"`（或交给服务端默认回退链路）。

### 2.3 事件向量检索与路由（dialog_v2 会用到）

这些端点用于 `dialog_v2` 的多路并行检索（E_event_vec / E_vec / K_vec / EN / T）。  
开发模式仍需 `X-Tenant-ID`。

#### 2.3.1 事件候选（POST `/search`）

用途：用事件向量索引召回 Event 作为 E_event_vec seeds（`source=tkg_dialog_event_index_v1`）。

```bash
curl -sS http://127.0.0.1:8000/search \
  -H 'Content-Type: application/json' \
  -H 'X-Tenant-ID: demo' \
  -d '{
    "query": "Caroline went to the museum",
    "topk": 10,
    "filters": {
      "tenant_id": "demo",
      "user_id": ["u:alice"],
      "memory_domain": "dialog",
      "source": ["tkg_dialog_event_index_v1"]
    }
  }'
```

返回：`hits=[{id, score, entry{contents, metadata{tkg_event_id, event_id, timestamp_iso...}}}]`

#### 2.3.2 实体解析（GET `/graph/v0/entities/resolve`）

用途：把人名/face id 映射为 Entity 节点（EN route）。

```bash
curl -sS "http://127.0.0.1:8000/graph/v0/entities/resolve?name=Caroline&type=PERSON&limit=5" \
  -H 'X-Tenant-ID: demo'
```

返回：`items=[{entity_id, name, score, ...}]`

#### 2.3.3 时间片范围检索（GET `/graph/v0/timeslices/range`）

用途：用时间范围召回 TimeSlice + 关联 Event（T route）。

```bash
curl -sS "http://127.0.0.1:8000/graph/v0/timeslices/range?start_iso=2024-01-01T00:00:00%2B00:00&end_iso=2024-01-01T23:59:59%2B00:00&kind=dialog_session&limit=50" \
  -H 'X-Tenant-ID: demo'
```

返回：`items=[{id, kind, t_abs_start, t_abs_end, event_ids, ...}]`

---

## 3. Python：高层编排 API（推荐给上层用）

> 提醒：本节是 **V2 计划中的客户端 API 规范**，目前处于“施工设计”阶段，代码实现会随后跟上。

目标：上层不要再自己拼一堆 `/search` 或 `/write`，而是调用两个“稳定门面”：

- `memory.session_write(...)`
  - 输入：文本/对话（messages 或纯文本）
  - 行为：抽取（可选）→ 调用现有 `POST /write` 写入
  - 支持 BYOK：可传 `llm_provider/llm_api_key/llm_model`（未提供时按 `llm_policy` 退化/报错）
- `memory.retrieval(...)`
  - 输入：query + strategy（如 `dialog_v1` / `video_v1`）
  - 行为：高级检索编排 → 调用现有 `POST /search`（1 次或多次）→ 融合 +（可选）rerank + debug
  - rerank 默认关闭，但启用时必须能跑通（同样支持 BYOK）

> 这两者都是“客户端库”：不引入新端口，不破坏既有 `/write` `/search`。

### 3.1 函数签名（草案，之后会一字一字对齐实现）

```python
def session_write(
    *,
    base_url: str,
    tenant_id: str,
    user_tokens: list[str],          # ["u:{user_id}", "p:{product_id}", "pub?" ...]
    user_match: str = "all",         # "all" 强隔离，"any" 合并多主体
    memory_domain: str,              # "dialog" / "video" / "work" / ...
    run_id: str | None = None,       # 会话/任务 id；可选但强烈建议提供
    messages: list[dict] | None = None,  # 对话 messages（role/content）
    text: str | None = None,         # 或者一段原始文本（二选一）
    extra_metadata: dict | None = None,
    # LLM 配置（抽取用）
    llm_provider: str | None = None,
    llm_api_key: str | None = None,
    llm_model: str | None = None,
    llm_policy: str = "best_effort",   # "require" | "best_effort"
) -> dict:
    ...


def retrieval(
    *,
    base_url: str,
    tenant_id: str,
    strategy: str = "dialog_v2",       # "dialog_v1" / "dialog_v2" / "video_v1" 等
    query: str,
    user_tokens: list[str],
    user_match: str = "all",
    memory_domain: str = "dialog",
    run_id: str | None = None,
    # 检索细节（topk 等由策略内部拆分为多路调用）
    topk: int = 30,
    debug: bool = False,
    # rerank 配置（默认关闭）
    rerank: dict | None = None,       # {"enabled": bool, "model": "llm|noop", ...}
    # LLM 配置（rerank / QA 用）
    llm_provider: str | None = None,
    llm_api_key: str | None = None,
    llm_model: str | None = None,
    llm_policy: str = "best_effort",
) -> dict:
    ...
```

返回结构（草案）：

- `session_write(...) -> {"version": "...", "written": int, "mode": "raw|extract" , "trace": {...}}`
- `retrieval(...) -> {"answer": str, "evidence": [...], "evidence_details": [...], "debug": {...}}`

### 3.2 命名约定：user_tokens / strategy

- `user_tokens` 推荐规范：
  - 个人用户：`["u:{user_id}"]`
  - 产品实例：`["u:{user_id}", "p:{product_id}"]`
  - 设备隔离：`["u:{user_id}", "p:{product_id}", "d:{device_id}"]`
  - 公共记忆：额外加一个 `"pub"`（具体策略后续在检索策略里定义是否合并）
- `strategy`：
  - `dialog_v1`：文本对话记忆检索（3 路并行，见下文）
  - `video_v1`：视频/多模态记忆检索（规划中）
  - V2/V3 版本通过追加 `_v2/_v3`，旧版本保持兼容。

### 3.3 调用示例（以 `dialog_v1` 为例）

```python
from modules.memory import session_write, retrieval

tenant_id = "demo"
base_url = "http://127.0.0.1:8000"

# 1) 写入：对话 →（可选抽取）→ /write
session_write(
    base_url=base_url,
    tenant_id=tenant_id,
    user_tokens=["u:alice", "p:companion_bot"],
    user_match="all",
    memory_domain="dialog",
    run_id="run-001",
    messages=[
        {"role": "user", "content": "我喜欢科幻电影。"},
        {"role": "assistant", "content": "明白了。你有特别喜欢的导演吗？"},
    ],
    llm_policy="best_effort",  # 未提供 key 时：不抽取也能写入（只写入 raw turn）
)

# 2) 检索：3 路并行（策略内定义）→ 融合 →（可选）rerank
res = retrieval(
    base_url=base_url,
    tenant_id=tenant_id,
    strategy="dialog_v1",
    query="我喜欢什么类型的电影？",
    user_tokens=["u:alice", "p:companion_bot"],
    user_match="all",
    memory_domain="dialog",
    run_id="run-001",
    rerank={"enabled": False},
    debug=True,
)

print(res["evidence"][:3])
```

---

## 4. 检索策略：`dialog_v1` 的 3 路并行（规划对齐 Benchmark）

`retrieval(strategy="dialog_v1", ...)` 的目标是把当前 benchmark 中效果最好的“3 路检索 + 融合 + 可选 rerank”固化下来，对上层暴露一个统一的“对话检索”API。

设计草图（对齐 `benchmark/shared/adapters/moyan_memory_qa_adapter.py::_execute_fixed_3way_search` 的精神，而非逐行复制）：

1. **Fact Search**（语义事实）  
   - 调用一次 `/search`：
     - `filters.memory_type=["semantic"]`
     - `filters.memory_domain="dialog"`
     - `filters.user_id=user_tokens`, `filters.user_match=user_match`
     - 以及 pipeline 自己写入的 `source`（例如 `"locomo_text_pipeline"`）  
   - 结果视为“Fact 证据”，记录 `fact_id`、`source_turn_ids` 等。

2. **Trace References**（事实回溯到事件）  
   - 不额外调用 `/search`，而是从 Fact 的 `source_turn_ids/source_sample_id` 推导出对应的 Event id；
   - 构造一批“引用证据”（`source="reference_trace"`），分数可基于 Fact 分数做一个衰减因子。

3. **Event Search**（原始对话片段）  
   - 再调用一次 `/search`：
     - `filters.memory_type=["episodic"]`
     - 其他 filters 与 Fact Search 一致；
   - 命中的 event 作为“原文证据”（`source="event_search"`）。

4. **融合 + 归一化 + 去重**
   - 给三路检索结果赋不同的 source 权重（例如 fact > reference > event），形成 `_final_score`;
   - 按 `_final_score` 排序后，对 (event_id/fact_id) 做去重（保证同一个事件只出现一次）。

5. **可选 rerank**
   - 如果 `rerank.enabled=true` 且 `llm_policy` 允许：
     - 取 Top-K 作为 candidate pool；
     - 用 LLM 读 query+evidence，输出新分数，形成 `final_score`；
   - 否则跳过 rerank，直接使用 `_final_score`。

6. **输出结构**
   - `evidence`: `[event_id,...]` 的列表（少量扁平 id，用于对标/评估）
   - `evidence_details`: 每条包含 `event_id/fact_id/source/text/score/fact_type/...`
   - `debug`：
     - `plan.latency_ms/retrieval_latency_ms/qa_latency_ms/total_latency_ms`
     - `executed_calls`: 记录各路 `/search` 调用及命中数量/错误

> 以上是策略级别的“合同说明”，真正实现时会严格按这个结构落代码和测试，确保 benchmark 与线上使用走同一套路径。

---

## 5. BYOK（用户自带模型 Key）的行为约定

两处会用到 LLM：
- `session_write` 的抽取（facts/preferences/tasks/rules）
- `retrieval` 的可选 rerank（默认关闭）

统一约定一个开关：`llm_policy`

- `llm_policy="require"`
  - 未提供 `llm_api_key`（且环境/配置也没有可用 LLM）→ 直接报错
- `llm_policy="best_effort"`（默认）：
  - `session_write`：跳过抽取，只写入可落库的基础信息（例如 raw turn / summary），但仍然正常写库；
  - `retrieval`：禁用 rerank，退化为纯融合排序；
  - debug 中应清晰标出 `llm_used=false` 与降级原因，避免“默默变笨”。

LLM 的 provider/模型选择优先级（规划与现有 `llm_adapter` 对齐）：

1. 显式传入的 `llm_provider/llm_api_key/llm_model`；
2. Memory config 中的 LLM 选择（`memory.llm.*`）；
3. 环境变量驱动的自动选择（OPENAI/OPENROUTER/DEEPSEEK/QWEN/GLM/GEMINI 等）；
4. 都没有时，若 `llm_policy="best_effort"` → 降级；若为 `"require"` → 抛错。

### 5.1 安全边界（非常关键）

- BYOK 的 `llm_api_key` **只在客户端库进程内使用**，用于：
  - `session_write` 的抽取；
  - `retrieval` 的 rerank（若启用）。
- Memory 后端服务（`POST /write`/`POST /search`）**不接收也不保存**用户的模型 key。

---

## 6. 生产开启指南（auth / signing / limits）——它们分别解决什么问题？

这节专门回答你说的：“要上 SSE/线上时，这些开关怎么开、起什么作用？”

### 6.1 `auth.enabled`：鉴权 + 多租户 tenant 解析

配置位置：`modules/memory/config/memory.config.yaml` → `memory.api.auth`

- 作用：
  - 让服务端从 token/JWT 得到 `tenant_id`（多租户硬边界）；
  - 拒绝未授权访问；
  - 为“按租户限流/审计”提供可信身份上下文。

实现要点（以代码为准）：
- token/jwt 的 header 名默认是 `X-API-Token`（可配置）；
- 若配置了 `jwt.jwks_url`，服务端会用 JWKS 验签并读取 claims：
  - `tenant_id` 来自你配置的 `tenant_claim`（默认 `tenant_id`），或退化读取 `tid`；
  - `sub` 会记录到 auth context（`subject`），但目前不会自动写入数据层，需要上层映射成 `u:{user_uuid}` token；
- 如果没配 JWKS，则按 `token_map` / `static_token` 走最简单的鉴权模式。

### 6.1.1 SaaS/IdP 还没定？怎么“保留接口”不绑死一家

结论先说死：**把身份体系当成可插拔适配器**，我们只冻结“我们需要的最小 claims 合同”，其余都通过配置/网关归一化。

我们建议你冻结的最小合同（对任何 SaaS 都适用）：

- 必须有一个“租户”字段：`tenant_claim`（默认用 `tenant_id`，或者你也可以配置成 `tid/organization_id/...`）
- 必须有一个“用户主体”字段：`sub`（OIDC 标准字段，建议直接用它作为 `user_uuid` 的来源）
- 可选扩展字段（以后再说，不影响现在接入）：
  - `product_id`（B 端产品隔离）
  - `device_id`（多端隔离）
  - `scopes/roles`（权限）

**推荐落地方式（二选一，二者都与任意 SaaS 兼容）：**

- 选项 A：直通 OIDC JWT（最少组件）
  - 每个环境只对接一个 IdP/JWKS；
  - 配置 `jwks_url/issuer/audience/tenant_claim`；
  - 客户端/边界网关把 `Authorization: Bearer <JWT>` **转发/映射**到 `X-API-Token: <JWT>`（不是因为服务端完全不支持 `Authorization`，而是为了和当前内网转发、签名与文档约定保持一致）。

- 选项 B：网关归一化（最稳、最推荐给“还没定 SaaS”的阶段）
  - 外部任何 SaaS/IdP → 网关验签/换票/归一化 claims；
  - 网关签发你们自己的“内部 JWT”（claims 一致：`tenant_id` + `sub`）；
  - Memory 只认这一套内部 JWT（最省心，后续换 SaaS 不动 Memory）。

> 关键点：你现在不需要决定 SaaS 用哪家；你只需要决定“我们内部认什么 claims”。

典型配置（示意）：

- 固定 token（最简单，适合内网/小规模）：
  - `enabled: true`
  - `token: ${MEMORY_API_TOKEN}`
  - `tenant_id: ${MEMORY_API_TENANT_ID}`
- token_map（多租户，但不想上 JWT）：
  - `enabled: true`
  - `token_map: { "<tokenA>": "tenantA", "<tokenB>": "tenantB" }`
- JWT/JWKS（标准 OIDC）：
  - `enabled: true`
  - `jwt.jwks_url/audience/issuer/tenant_claim`

### 6.2 `signing.required`：保护写操作“不可伪造/不可重放”

配置位置：`modules/memory/config/memory.config.yaml` → `memory.api.auth.signing`

- 作用：
  - 防止有人拿到 token 后随意伪造写入；
  - 防止重放旧请求（ts 有时钟偏差上限）。

你需要在客户端/网关层生成签名头：
- `X-Signature-Ts: <unix_ts>`
- `X-Signature: hmac_sha256(secret, f"{ts}.{path}.{raw_body}")`

### 6.3 `limits.*`：把“打爆服务”的风险变成可控失败

配置位置：`modules/memory/config/memory.config.yaml` → `memory.api.limits`

- 作用：
  - 请求体大小上限（避免一次写入把服务打死）；
  - 按租户令牌桶限流（避免流量突刺）；
  - 高开销端点超时（search/timeline_summary）。
