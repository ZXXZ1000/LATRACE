# 记忆模块使用指南（对齐当前实现：三键+作用域+图域限制）

记忆模块是一个拥有“向量大脑”和“关系大脑”的超级海马体。

- **向量大脑 (Qdrant)**：擅长模糊查找和感知相似性。比如，它能理解“喜欢吃苹果”和“爱吃水果”是相关的。
- **关系大脑 (Neo4j)**：擅长记住事物之间的明确关系。比如，“小明”是“小红”的“同事”。

---

## 快速上手：三种与“记忆”互动的方式

你可以通过三种方式来调用记忆模块，选择最适合你场景的一种即可。

---

## 核心模型与“三键”

为实现“对象级强隔离 + 域内优先降噪 + 会话打包”，写入与检索统一使用三类关键字段：

- `metadata.user_id: list[str]`：交互对象标识（可多值），来自人脸/声纹/主体识别或显式传入。强隔离主轴。
- `metadata.memory_domain: str`：记忆域（如 `work`/`home`/`system`/`general`）。域内优先检索、可按域治理 TTL/重要性。
- `metadata.run_id: str`：会话/任务上下文，用于“把一次任务的记忆打包”。

检索过滤体（SearchFilters）也以此为核心：`user_id (list) + user_match:any|all`、`memory_domain`、`run_id` 等。

提示：在 SDK/HTTP 调用时，建议总是传入 `user_id` 与 `memory_domain`，必要时补 `run_id`，可显著提升准确率与可解释性。

### 方式一：直接调用 (推荐)

这是最简单、最推荐的方式，尤其适合在 Agent 的工具（Tools）中使用。

```python
import asyncio
# 假设你已经有了一个名为 memory 的工具实例
# 它可以是 MemoryService, 也可以是 MemoryMCPAdapter
from your_agent_tools import memory 

async def main():
    # 1. 存入一条记忆
    # “我想让 AI 记住，我喜欢科幻电影”
    await memory.write(
        entries=[{
            "kind": "semantic", "modality": "text",
            "contents": ["我喜欢科幻电影"],
            "metadata": {"source": "user_preference"}
        }]
    )
    print("✅ 记忆已存入")

    # 2. 检索相关记忆
    # “AI，你还记得我喜欢什么类型的电影吗？”
    results = await memory.search(query="我喜欢什么电影", topk=1)
    
    if results["hits"]:
        # AI 从记忆中找到了线索
        recalled_memory = results["hits"][0]["entry"]["contents"][0]
        print(f"🧠 AI 回忆起：'{recalled_memory}'")
    else:
        print("🤔 AI 暂时没想起来...")

asyncio.run(main())
```

### 方式二：通过 HTTP API

如果你的 Agent 是用其他语言（如 Node.js, Go）编写的，或者需要跨进程通信，可以使用标准的 HTTP 接口。

```python
import requests

# 记忆模块服务的地址
MEMORY_API_BASE = "http://127.0.0.1:8000"

# 存入记忆
requests.post(f"{MEMORY_API_BASE}/write", json={
  "entries": [{"kind":"semantic", "modality":"text", "contents":["我喜欢科幻电影"]}]
})

# 检索记忆
response = requests.post(f"{MEMORY_API_BASE}/search", json={"query":"我喜欢什么电影"})
hits = response.json().get("hits", [])
if hits:
    print(f"🧠 AI 回忆起：'{hits[0]['entry']['contents'][0]}'")
```

### 方式三：通过 MCP 工具协议

如果你的 Agent 系统遵循 MCP (Master Control Program) 协议，可以直接调用 `memory.*` 工具。

```python
# 伪代码，展示在 Agent 中的调用形式
tool_result = await agent.call_tool(
    "memory.search",
    {"query": "我喜欢什么电影", "topk": 1}
)
```

---

## 核心操作：增删改查

### 记住事情 (Write)

你可以让 AI 记住任何事情，从一个简单的用户偏好，到一个复杂的场景。

**记住一个简单事实（带三键）：**
```python
await memory.write(
    entries=[{
        "kind": "semantic",  # 这是一个“事实”或“知识”
        "modality": "text",
        "contents": ["用户的名字是小明"],
        "metadata": {
            "user_id": ["user_123"],
            "memory_domain": "work",
            "run_id": "session-001"
        }
    }]
)
```

**记住一个场景（包含关系）：**
```python
# 场景：小明在客厅打开了灯
# 我们需要记住“小明”、“客厅”、“灯”以及它们之间的关系

# 1. 定义参与该场景的实体
entry_ming = {"id": "ming", "kind": "semantic", "modality": "text", "contents": ["小明"]}
entry_light = {"id": "light_living", "kind": "semantic", "modality": "text", "contents": ["客厅的灯"]}
entry_living_room = {"id": "living_room", "kind": "semantic", "modality": "text", "contents": ["客厅"]}
entry_action = {"id": "action_1", "kind": "episodic", "modality": "text", "contents": ["小明打开了客厅的灯"]}

# 2. 定义它们之间的关系
links = [
    {"src_id": "ming", "dst_id": "action_1", "rel_type": "PERFORMED"},      # 小明 -> 执行了 -> 动作
    {"src_id": "action_1", "dst_id": "light_living", "rel_type": "ACTED_ON"}, # 动作 -> 作用于 -> 灯
    {"src_id": "light_living", "dst_id": "living_room", "rel_type": "LOCATED_IN"} # 灯 -> 位于 -> 客厅
]

# 3. 一次性写入记忆
await memory.write(entries=[entry_ming, entry_light, entry_living_room, entry_action], links=links)
```

### 回忆事情 (Search)

这是最常用的功能。你可以用自然语言来查询。

```python
# “客厅里发生了什么事？”
results = await memory.search(query="客厅里发生了什么", topk=3)

# `results` 中不仅有最相关的记忆片段，还有 `hints` 字段，
# 它是为 LLM 准备的浓缩摘要，可以直接送入 Prompt。
llm_context = results["hints"]
print(f"给 LLM 的参考材料：\n{llm_context}")
```

**使用过滤器进行精确回忆：**
```python
# “回忆一下和小明有关的、发生在客厅的事”
results = await memory.search(
    query="小明",
    filters={
        "metadata": {"user_id": "user_123"}, # 过滤元数据
        "rel_types": ["LOCATED_IN"]          # 只关心和“位置”有关的
    }
)
```

### 修正记忆 (Update)

AI 的记忆也可能出错或过时，我们可以修正它。

```python
# 假设之前记错了，小明其实喜欢的是动作电影
# 首先需要找到那条记忆的 ID
results = await memory.search(query="小明喜欢科幻电影", topk=1)
memory_id = results["hits"][0]["id"]

# 修正它
await memory.update(
    id=memory_id,
    patch={"contents": ["小明喜欢动作电影"]},
    reason="用户澄清了他的偏好"
)
```

### 忘记事情 (Delete)

**软删除 (推荐)**：
这更像是把记忆“归档”，而不是彻底销毁。它看不见了，但还能被找回来。
```python
await memory.delete(id=memory_id, soft=True, reason="用户要求忘记")
```

**硬删除 (慎用)**：
彻底从大脑中移除，无法恢复。默认需要二次确认。
```python
await memory.delete(id=memory_id, soft=False, reason="清理测试数据", confirm=True)
```

---

## 高级用法

### 多模检索（text/image/audio）

你可以同时对多种模态进行联合召回，并在记忆层统一重排（向量/图邻域/BM25/Recency）后返回结果。通过 `filters.modality` 精确控制要参与召回的模态。

- 默认行为：未显式指定 `filters.modality` 时，仅检索 `text` 集合。
- 可选值：`["text", "image", "audio"]` 的任意组合。

示例（HTTP API）：
```
curl -s http://127.0.0.1:8000/search \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "客厅 科幻 电影 海报",
    "topk": 5,
    "expand_graph": true,
    "filters": {
      "modality": ["text", "image", "audio"],
      "user_id": ["alice"],
      "memory_domain": "home",
      "run_id": "s1"
    }
  }'
```

示例（Python SDK）：
```python
from modules.memory.client import Memory
import asyncio

async def demo():
    m = Memory.from_defaults()
    # 联合检索 text+image，限制 topk=5
    res = await m.search(
        "客厅 科幻 电影 海报",
        user_id=["alice"], memory_domain="home", run_id="s1",
        topk=5, expand_graph=True,
        extra_filters={"modality": ["text", "image"]}
    )
    print(res["results"])  # 统一重排后的结果

asyncio.run(demo())
```

示例（MCP 工具）：
```python
tool_result = await mcp.call_tool(
  "memory.search",
  {
    "query": "客厅 科幻 电影 海报",
    "topk": 5,
    "expand_graph": True,
    "filters": {"modality": ["text", "image"]}
  }
)
```

提示：
- 多模联合召回后，记忆层会按分数统一重排，并整体截断 `topk`。如果对性能或精准度有要求，建议只选择与任务相关的模态（例如仅 `image`）。
- 目前 `image/audio` 的嵌入为占位实现（描述文本→向量），可在配置中替换为真实模型（如 CLIP/ERes2NetV2）；替换后无需改动上述调用方式。

### 按角色检索（P2）

有两种简单方式：

- 过滤式（SDK/HTTP）：
  - 在 `filters` 中添加 `character_id: ["Alice"]`，只返回该角色相关条目。

示例（HTTP）：
```
curl -s http://127.0.0.1:8000/search \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "Alice 在做什么？",
    "topk": 5,
    "filters": {"character_id": ["Alice"], "modality": ["text","image","audio"]}
  }' | jq '.hits[] | {id: .id, character: .entry.metadata.character_id, text: .entry.contents[0]}'
```

- 查询语法（自然语言）：
  - 在查询文本中写 `character:Alice` 或 `<character_Alice>`，系统会自动转换为 `filters.character_id=["Alice"]`，并在未指定模态时自动扩大到 `text/image/audio`。

示例（HTTP）：
```
curl -s http://127.0.0.1:8000/search \
  -H 'Content-Type: application/json' \
  -d '{"query": "character:Alice 最近在厨房做了什么？", "topk": 5}' \
  | jq '.hits[] | {id: .id, character: .entry.metadata.character_id, text: .entry.contents[0]}'
```

提示：
- 记忆条目需在写入时带有 `metadata.character_id`（Memorization Agent 已在 `img/voice` 节点映射时注入）。
- `memory.search.character_expansion.enabled` 默认开启，可在 `memory.config.yaml` 关闭该语法支持。

运行时热更新默认模态（管理接口）
```
# 查看当前 ANN 默认模态覆盖
curl -s http://127.0.0.1:8000/config/search/ann | jq

# 设置默认使用全部模态（如果 filters.modality 未显式指定）
curl -s http://127.0.0.1:8000/config/search/ann \
  -H 'Content-Type: application/json' \
  -d '{"default_all_modalities": true}' | jq

# 或者显式指定默认模态列表
curl -s http://127.0.0.1:8000/config/search/ann \
  -H 'Content-Type: application/json' \
  -d '{"default_modalities": ["text","image","audio"]}' | jq
```

### 多跳联想 (Multi-hop Search)

默认情况下，AI 会进行 1 跳联想（直接关系）。你可以让它想得更深一层（2跳），发现“朋友的朋友”这种间接关系。

```python
# 让 AI 在思考“小明”时，多想一层关系
# 这通常通过运行时配置或 HTTP 参数实现
# 例如，调用 /config/graph 接口
requests.post(f"{MEMORY_API_BASE}/config/graph", json={"max_hops": 2})

# 再次搜索，结果会包含更深层次的关联信息
results = await memory.search(query="小明")
```

### 缓存与批处理

- **搜索缓存**：对于重复的问题，记忆模块会自动使用缓存，光速返回答案，无需次次都去麻烦“大脑”。
- **写入批处理**：如果你有大量零碎信息要一次性告诉 AI，可以使用批处理模式，效率更高。

```python
# 伪代码，展示开启批处理
memory.enable_write_batching(enabled=True, max_items=50)

# 连续多次“告知”，但不会立刻写入
await memory.enqueue_write(entries=[...])
await memory.enqueue_write(entries=[...])

# 手动触发“消化”
await memory.flush_write_batch()
```

---

## 配置与维护

### HTTP API 快速参考（curl 示例）

以下示例假设服务运行在 `http://127.0.0.1:8000`。若开启了最小鉴权，请在请求头中附带 `X-API-Token: <你的token>`。

- 搜索（/search）
```
curl -s http://127.0.0.1:8000/search \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "我喜欢什么电影",
    "topk": 5,
    "expand_graph": true,
    "filters": {"user_id": ["alice"], "memory_domain": "work", "run_id": "session-001", "user_match": "any"}
  }' | jq '.hits[0]'
```

- 写入（/write）
```
curl -s http://127.0.0.1:8000/write \
  -H 'Content-Type: application/json' \
  -d '{
    "entries": [
      {"kind":"semantic","modality":"text","contents":["我爱科幻电影"],
       "metadata":{"user_id":["alice"],"memory_domain":"work","run_id":"session-001"}}
    ],
    "links": []
  }'
```

- 更新（/update）
```
curl -s http://127.0.0.1:8000/update \
  -H 'Content-Type: application/json' \
  -d '{
    "id": "<memory_id>",
    "patch": {"contents":["我爱动作电影"]},
    "reason": "用户澄清"
  }'
```

- 软/硬删除（/delete）
```
# 软删除（推荐，可回滚）
curl -s http://127.0.0.1:8000/delete -H 'Content-Type: application/json' \
  -d '{"id":"<memory_id>", "soft": true, "reason": "用户要求"}'

# 硬删除（谨慎，通常需要 confirm）
curl -s http://127.0.0.1:8000/delete -H 'Content-Type: application/json' \
  -d '{"id":"<memory_id>", "soft": false, "reason": "清理测试", "confirm": true}'
```

- 关系（/link）
```
curl -s http://127.0.0.1:8000/link -H 'Content-Type: application/json' \
  -d '{"src_id":"A","dst_id":"B","rel_type":"equivalence","confirm": true}'
```

- 回滚版本（/rollback）
```
curl -s http://127.0.0.1:8000/rollback -H 'Content-Type: application/json' \
  -d '{"version":"v-UPDATE-<memory_id>"}'
```

- 图配置热更（/config/graph）
```
# 查看当前覆盖
curl -s http://127.0.0.1:8000/config/graph | jq

# 仅开启 2 跳、限制邻居上限为 8
curl -s http://127.0.0.1:8000/config/graph -H 'Content-Type: application/json' \
  -d '{"max_hops": 2, "neighbor_cap_per_seed": 8}' | jq
```

- 重排权重热更（/config/search/rerank）
```
curl -s http://127.0.0.1:8000/config/search/rerank | jq
curl -s http://127.0.0.1:8000/config/search/rerank -H 'Content-Type: application/json' \
  -d '{"alpha_vector":0.5, "gamma_graph":0.25}' | jq
```

- 作用域与回退（/config/search/scoping）
```
curl -s http://127.0.0.1:8000/config/search/scoping | jq
curl -s http://127.0.0.1:8000/config/search/scoping -H 'Content-Type: application/json' \
  -d '{"default_scope":"domain","fallback_order":["session","domain","user"],"require_user":true}' | jq
```

- 指标（/metrics_prom）
```
curl -s http://127.0.0.1:8000/metrics_prom | head -n 20
```

### 最小鉴权（可选）

在 `memory.config.yaml` 中启用：
```
memory:
  api:
    auth:
      enabled: true
      header: X-API-Token
      token: ${MEMORY_API_TOKEN}
```

携带请求头：
```
curl -s http://127.0.0.1:8000/write \
  -H 'Content-Type: application/json' \
  -H 'X-API-Token: YOUR_TOKEN' \
  -d '{"entries":[{"kind":"semantic","modality":"text","contents":["demo"]}]}'
```

提示：也可用环境变量开启 `MEMORY_API_AUTH_ENABLED=true` 并通过 `MEMORY_API_TOKEN` 提供密钥，方便本地/容器化部署。

- **配置文件**：所有默认行为（如数据库地址、缓存时间、重排权重/作用域/图域限制等）都在 `memory.config.yaml` 与 `.env` 中定义。模块会同时加载根目录 `.env` 与 `modules/memory/config/.env`，后者优先覆盖（确保测试/沙箱更易控）。
- **健康检查**：访问 `/health` 接口，可以查看记忆模块的两个“大脑”是否都正常工作。
- **性能监控**：访问 `/metrics_prom` 接口，可以获取详细的性能指标（如响应时间、错误率、缓存命中率等），用于 Prometheus 监控。

本指南旨在提供一个清晰、友好的上手体验。更详细的 API 参数和高级功能，请参考 `memory_toolspec.json` 和端到端测试脚本 `e2e_final_test.py`。

---

## SDK 门面（Memory 类，P0）

为方便在 Python 侧直接调用，提供了轻量的 SDK：`modules/memory/client.py`。

示例：

```python
import asyncio
from modules.memory.client import Memory

async def demo():
    m = Memory.from_defaults()  # 读取 YAML + .env 构建

    # 1) 写入一条事实（不做抽取）
    r = await m.add("我 喜欢 科幻 电影", user_id="alice", memory_domain="home", run_id="s1", infer=False)
    print(r)

    # 2) 检索（域内优先）
    s = await m.search("科幻", user_id="alice", memory_domain="home", scope="domain", topk=3)
    print(s["results"])  # mem0 风格的 results 列表

    # 3) 更新与历史
    mid = s["results"][0]["id"]
    await m.update(mid, "我 很 喜欢 科幻 电影", reason="refine")
    hist = await m.history(mid)
    print(hist)

asyncio.run(demo())
```

说明：
- `add(data, *, user_id, memory_domain, run_id=None, infer=True)`：
  - data 可为字符串或消息数组（`[{role, content}]`），infer=True 时强制使用 mem0 风格的“消息→事实”抽取（依赖 .env 的 LLM 配置）。
  - SDK 写入会自动补齐三键：`user_id`（可多值）、`memory_domain`、`run_id`。
- `add_entries(entries, links=None, *, user_id, memory_domain, run_id=None)`：
  - 结构化入口（如 M3 视频图谱产物）——直接落库，SDK 负责补齐三键。
- `search(query, *, user_id, memory_domain=None, run_id=None, scope=None, user_match='any', topk=10)`：
  - 作用域与回退逻辑在服务层生效，默认 `domain`，无命中回退 `user` 等；
  - 结果为 mem0 风格的 `results=[{id, memory, metadata, event}]`。
- `get/update/history/delete/delete_all`：
  - `history` 基于审计存储返回该条目的编辑轨迹；
  - `delete_all` 采用小规模安全循环删除（需 `confirm=True`），大规模请改用服务端 `/batch_delete`。

注意：
- P0 为便捷门面，真实大规模批量清理、跨语言调用请使用 HTTP 接口与批量操作。

---

## 作用域与回退（Scoping & Fallback）

- 默认作用域：`domain`。若同域无命中，自动回退 `session → domain → user`（可配置）。
- 过滤：`user_id` 支持 `user_match=any|all`；`memory_domain`/`run_id` 精确匹配；并支持 `modality/source/entities/time_range` 等。
- 搜索缓存：键已纳入 `scope`、最终过滤体以及图参数签名，避免切换图开关/作用域时的错误命中。

示例（域内优先，必要时回退）：
```python
res = await memory.search(
  query="我喜欢什么电影",
  user_id=["alice"], memory_domain="home", run_id="s1",
  scope="domain", topk=5
)
```

HTTP 运行时调参（/config/search/scoping）：
```bash
curl -sS http://127.0.0.1:8000/config/search/scoping \
  -H 'Content-Type: application/json' \
  -d '{
    "default_scope": "domain",
    "user_match_mode": "any",
    "fallback_order": ["session", "domain", "user"],
    "require_user": false
  }'
```

---

## 图邻域限制与跨域开关

- 默认仅在相同 `user_id ∧ memory_domain` 内展开邻域，以降低噪声、提升可控性。
- 可通过运行时开关允许跨域/跨用户（管理/诊断场景）：
  - HTTP：`POST /config/graph` body 支持 `max_hops`、`rel_whitelist`、`neighbor_cap_per_seed`，以及 `restrict_to_user`、`restrict_to_domain`、`allow_cross_user`、`allow_cross_domain`。
  - 代码：`runtime_config.set_graph_params(allow_cross_domain=True, allow_cross_user=True)`。

---

## 指标总览（Prometheus）

- 核心：`memory_searches_total`、`memory_writes_total`、`memory_search_latency_ms_*`。
- 作用域与过滤：`memory_search_scope_total{scope=...}`、`memory_search_filter_applied_total{key=user|domain|session}`。
- 缓存：`memory_search_cache_hits_total`、`memory_search_cache_hits_scope_total{scope=...}`、`memory_search_cache_evictions_total`。
- 域分布：`memory_domain_distribution_total{domain=...}`。
- 重试/熔断：`memory_backend_retries_total`、`memory_circuit_breaker_open_total`。

---

## 治理策略（按域 TTL/重要性）

- 在 `memory.config.yaml` 的 `memory.governance` 中配置：
  - `per_domain_ttl`: 如 `work: "30d"`, `home: "90d"`, `system: "7d"`；`0` 表示长期保留。
  - `importance_overrides`: 对不同域进行加法微调（范围仍强制在 `[0,1]`）。
- 写入时自动应用，除非条目显式设置 `ttl_pinned=True` 或 `importance_pinned=True`。

---

## LLM 抽取与 .env 提示

- SDK `add(..., infer=True)` 默认启用 mem0 风格“消息→事实”抽取；
- LLM/Embedding 配置优先从 `modules/memory/config/.env` 读取并覆盖根 `.env`；
- OpenRouter 集成遵循 LiteLLM 规范，模型名可直接设为 `x-ai/grok-4-fast:free`，适配器会自动处理路由（无需手动 `api_base`）。

注意：Qdrant 端的 `time_range` 目前仅支持数值时间戳范围过滤（epoch 秒）。若传 ISO 字符串，将被跳过；可在写入时同时存一份数值时间戳，或在检索前转换为数值。

---

## HTTP curl 示例合集

以下示例假设服务监听在 `http://127.0.0.1:8000`。

- 写入（/write）
  - 记住一条语义记忆（带三键）：
  ```bash
  curl -sS http://127.0.0.1:8000/write \
    -H 'Content-Type: application/json' \
    -d '{
      "entries": [{
        "kind": "semantic",
        "modality": "text",
        "contents": ["我 喜欢 科幻 电影"],
        "metadata": {"user_id": ["alice"], "memory_domain": "home", "run_id": "s1"}
      }]
    }'
  ```

- 检索（/search）
  - 域内优先检索（必要时回退），展开 1 跳邻域：
  ```bash
  curl -sS http://127.0.0.1:8000/search \
    -H 'Content-Type: application/json' \
    -d '{
      "query": "科幻",
      "topk": 5,
      "expand_graph": true,
      "filters": {"user_id": ["alice"], "memory_domain": "home", "run_id": "s1"}
    }'
  ```

- 运行时调整图参数（/config/graph）
  - 允许跨域邻域展开（诊断/审计场景），同时设为最多 2 跳：
  ```bash
  curl -sS http://127.0.0.1:8000/config/graph \
    -H 'Content-Type: application/json' \
    -d '{
      "max_hops": 2,
      "allow_cross_domain": true,
      "allow_cross_user": false
    }'
  ```
  - 恢复默认（仅域内 + 对象内）：
  ```bash
  curl -sS http://127.0.0.1:8000/config/graph \
    -H 'Content-Type: application/json' \
    -d '{
      "max_hops": 1,
      "restrict_to_user": true,
      "restrict_to_domain": true,
      "allow_cross_domain": false,
      "allow_cross_user": false
    }'
  ```

- 运行时调整重排权重（/config/search/rerank）
  - 临时提升图贡献与会话加分：
  ```bash
  curl -sS http://127.0.0.1:8000/config/search/rerank \
    -H 'Content-Type: application/json' \
    -d '{
      "gamma_graph": 0.25,
      "session_boost": 0.20
    }'
  ```
  - 查看当前覆盖：
  ```bash
  curl -sS http://127.0.0.1:8000/config/search/rerank
  ```

- 导出指标（/metrics_prom）
  - 直接输出 Prometheus 文本：
  ```bash
  curl -sS http://127.0.0.1:8000/metrics_prom
  ```
