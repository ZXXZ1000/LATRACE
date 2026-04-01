# C9 重写迁移备忘录

## 1. 文档定位

| 项目 | 值 |
|---|---|
| 基线提交 | `c9aebe1b`（2026-02-01，稳定绿色基线） |
| 对照提交 | `9559e5a3`（feature/api-upgrade-long-memory-agent HEAD）|
| 新增提交范围 | `833d4a40`（api_R4）、`06246568`（R5）+ 三次 merge |
| 作者 | P-PPT（外部协作者，PT-new-api 分支） |
| 当前工作分支 | `rewrite/memory-from-c9`（以最新全测为准） |
| 回溯原则 | 当前分支视为 c9 干净重写线；仅回溯 `feature/api-upgrade-long-memory-agent` 的 `c9..HEAD` 提交差异 |
| 本文目的 | 在 `rewrite/memory-from-c9` 上逐项回补新能力，**不搬运破坏性代码** |

---

## 2. c9 后新增了什么？（产品经理视角）

### 先说结论：c9 加了什么，新增代码又加了什么

**c9 基线时已经有的**：5 个语义接口（topic-timeline / entity-profile / quotes / relations / time-since），均通过 `/memory/v1/*` 路径暴露。它们已支持基础文本入参（如 `entity`、`topic`）并做简单名称匹配/归一化，但存在两个限制：1）解析链路较原始，缺少代词保护、长文本候选抽取、图检索→语义回退和 `complex_search` 控制；2）缺少面向事件证据链的统一 explain 语义接口（仅在底层 graph/v0 中有）。

**c9 之后、新增代码核心解决的问题**：将上述 5 个接口的“文本解析能力”从简单匹配升级为多策略解析，并新增 Explain，使语义接口总数达到 6 个，由系统负责“找到你说的是哪个事件/实体/话题”。

---

### 2.1 【P0 核心新增】用自然语言描述替代内部 ID：SemanticResolver

**解决的用户痛点**

Agent 在 c9 虽然可以传文本，但主要依赖简单名称匹配。遇到“我们上周讨论过的那件事”这类上下文描述时，命中率和稳定性不足，调用方仍经常需要维护额外 ID 映射。

**新增后的体验**

调用方传入 `event_text="我们上周讨论过的那个项目推进"` 或 `entity_text="张三"`，系统自动完成解析，返回结果时同时附上 `resolution_meta`（告诉调用方"我是怎么找到的"）。

**技术实现**

新建 `SemanticResolver` 类（`semantic_resolver.py`），分两条解析路径：

- **事件解析**（`resolve_event_id`）：图检索优先 → 语义候选回退（仅在 `complex_search=true` 时触发）
- **实体解析**（`resolve_entity_id`）：直接名称匹配 → 文本抽取候选 → 语义事件候选反查实体频次

新增请求参数 `complex_search: bool`（默认 `false`），控制是否允许走更慢但更强的语义回退路径。

---

### 2.2 【P0 核心新增】Explain 接口：从无到有的语义事件解释

**新增接口**：`POST /memory/explain` 及 `POST /memory/v1/explain`（**c9 时无此语义路由**）

**业务定位**：将原属于底层管理接口（`graph/v0/explain`）的能力正式打包为面向端侧产品的语义 API。

**新增能力与使用体验**：

1. **核心解析支持**：支持 `event_text`（自然语言描述）作为入参，系统先寻找匹配的事件再返回解释链。
2. **两阶段检索控制**：引入 `complex_search` 参数。当传 `true` 时，若直接图匹配失败，允许回退到较慢的“大模型生成语义候选”进行二次匹配。
3. **分辨率溯源**：返回 JSON 中自带 `resolution_meta` 结构，明确告知外层“本次是通过 ID 提供、图检索还是语义回退”找到的事件。
4. **输出截断与连带检索**：新参数 `max_evidence`（限制返回的语录条数）及 `include_knowledge`（是否连带查询知识图谱，默认 true）。

---

### 2.3 【P1 增强】Topic 查询：归一化能力增强 + Topic 复用

**影响接口**：`POST /memory/topic-timeline`、`POST /memory/time-since`

**c9 时现状**：已支持 `topic` 文本入参，并通过 `TopicNormalizer.normalize_event` 做基础归一化；但缺少“纯 topic 文本”的独立归一函数与跨会话 topic 复用机制。

**新增后的变化**：

1. 新增 `normalize_topic_text` 独立函数（LRU 缓存），针对 topic 文本直接归一为 `topic_id/topic_path`
2. `TopicNormalizer` 从“事件归一化主入口”扩展为“与 `normalize_topic_text` 协同”的归一体系
3. 新建 `TopicRegistry`：同一租户/域内，相似 topic 复用已注册的 `topic_id`（Jaccard 相似度 ≥ 0.7），避免因同一话题表达不同而产生碎片化数据
4. `time-since` 新支持 `topic + entity` 联合约束（AND 语义，取交集）

---

### 2.4 【P1 增强】实体解析增强：代词保护 + 长文本候选抽取

**影响接口**：`/memory/entity-profile`、`/memory/relations`、`/memory/quotes` 中使用 `entity_text` 时

**新增后的变化**：

1. **代词保护**（可通过环境变量 `MEMORY_ENTITY_PRONOUN_GUARD` 开关）：传入"他/她/他们/it"等代词时，跳过实体解析直接返回空，避免误命中不相关实体
2. **长文本实体抽取**（可通过 `MEMORY_ENTITY_TEXT_EXTRACT_ENABLED` 开关）：从长句中先抽取候选实体名（英文大写专名词 + 中文姓名规则），再逐一解析，命中即返回

---

### 2.5 【P1 增强】图谱底层查询能力补齐

这些是内部能力，对外接口不变，但支撑了上述 P0/P1 功能的实现：

| 方法 | 位置 | c9 状态 | 作用 |
|---|---|---|---|
| `list_events_by_ids` | GraphService | 新增 | 批量拉取事件详情（支持 logical_id 映射） |
| `list_entities_by_ids` | GraphService | 新增 | 批量拉取实体详情 |
| `expand_neighbors` | GraphService | 新增（Service 层封装） | 多跳图谱邻居扩展（支持 rel_whitelist + hops 限制） |
| `event_id_by_logical_id` | GraphService | 新增 | logical_id → 内部 event_id 的反查 |
| `query_events_by_ids` | Neo4jStore | c9 已有（复用） | Cypher 批量查事件节点 |
| `query_entities_by_name` | Neo4jStore | c9 已有（增强） | 全文检索 + 精确匹配双路查找实体 |
| `query_entities_by_ids` | Neo4jStore | 新增 | Cypher 批量查实体节点 |
| `query_event_id_by_logical_id` | Neo4jStore | 新增 | 按 logical_id 属性反查内部节点 ID |

---

### 2.6 【P2 数据增强】对话写入中的 mention 识别

**场景**：对话中提到了某个实体（"我和张三讨论了…"），但这条对话的事件节点没有关联到"张三"实体。

**新增后的变化**：

1. 复用 Stage3 统一抽取器（LLM）已输出的 `events[].participants`
2. 在图构建主链路中消费 `participants`，补 `Event -[INVOLVES]→ Entity` 边（不再只依赖 speaker）
3. 消费 `knowledge[].mentions`，补 `Knowledge -[MENTIONS]→ Entity` 边（不再只作为 `Knowledge.data` 属性）

**说明**：这是“接通主链路”的实现，不依赖规则型 mention shadow 旁路。

---

### 2.7 【路由】`/memory/*` 短路径：已有功能的别名，非新能力

这是一个常见误解点，需要明确说清楚：

| 短路径 | 对应的已有接口 | 是否新功能 |
|---|---|---|
| `POST /memory/topic-timeline` | `POST /memory/v1/topic-timeline` | ❌ 别名，同一实现 |
| `POST /memory/time-since` | `POST /memory/v1/time-since` | ❌ 别名，同一实现 |
| `POST /memory/relations` | `POST /memory/v1/relations` | ❌ 别名，同一实现 |
| `POST /memory/quotes` | `POST /memory/v1/quotes` | ❌ 别名，同一实现 |
| `POST /memory/entity-profile` | `POST /memory/v1/entity-profile` | ❌ 别名，同一实现 |
| `POST /memory/explain` | `POST /memory/v1/explain` | ⚠️ 新接口对（c9 时两者都不存在） |

设计意图是降低调用方记忆负担（不用记 `/v1` 前缀），重写时**两个路径都要注册**，但只能有**一个 handler**。

---

## 3. 破坏性改动清单（重写时必须避免）

> 以下是原始新增代码（833d4a40 + 06246568）中已验证的破坏点，重写时**不得复制**。

### 3.1 路由重复注册（最严重）

原代码在 `server.py` 中同一路径注册了两个不同的 handler：

```
/memory/explain        → 出现 2 次（两套不同实现并存）
/memory/topic-timeline → 出现 2 次
/memory/relations      → 出现 2 次
/memory/quotes         → 出现 2 次
/memory/entity-profile → 出现 2 次
/memory/time-since     → 出现 2 次
（共 12 个路由重复）
```

**重写要求**：每个 method + path 组合有且只有一个 handler，通过 `SemanticService` 统一调用。

### 3.2 语义 API 开关默认关闭

```yaml
memory:
  api:
    semantic:
      enabled: false   # ← 导致 5 个测试 404
```

**重写要求**：默认值改为 `true`；开关的作用边界是"是否执行语义计算"，**不应该让接口对 `/api/list` 不可见**。

### 3.3 scope 映射缺失

原代码把 c9 时的前缀级覆盖规则（`/memory/v1/`、`/memory/state/`）改成了不完整的显式列表，漏配了大量子路径。

**重写要求**：恢复前缀级 scope 规则：
```python
PATH_SCOPE_REQUIREMENTS = {
    "/memory/v1/": "memory.read",
    "/memory/state/": "memory.read",
    # 仅新增写操作才需要显式声明
}
```

### 3.4 GraphService 方法签名不向后兼容

`explain_event_evidence`、`explain_first_meeting` 等方法新增了 `user_ids` 和 `memory_domain` 参数，但没有设置默认值，导致旧 mock/stub 调用时参数不匹配报错。

**重写要求**：所有新增参数必须有默认值（`user_ids: Optional[List[str]] = None`），保持向后兼容。

---

## 4. 算法实现细则（施工参考）

### 4.1 通用输入规范

所有语义接口共享以下输入归一化规则：

```
user_tokens 为空 → 归一为 ["u:{tenant_id}"]
memory_domain 为空 → 归一为 "dialog"
显式 ID 永远优先于文本解析
图检索命中优先于语义回退候选
```

### 4.2 事件解析算法（resolve_event_id）

```
输入：event_id, event_text, complex_search, topk

1. 若传 event_id → 直接返回，mode=provided
2. 若无 event_text → 返回 mode=missing
3. complex_search=true 路径：
   a. 熔断检查（_Breaker）→ 开路则返回 circuit_breaker_open
   b. 调 search_events_v1（含超时）
   c. 命中 → list_events_by_ids 做 logical_id → event_id 映射
   d. 未命中 → semantic_event_candidates 语义回退 → 再次 ID 映射
4. complex_search=false 路径：
   仅执行 search_events_v1，不走语义回退

输出：resolved_id + resolution（mode/candidates/error/fallback_from）
```

### 4.3 实体解析算法（resolve_entity_id）

```
输入：entity_id, entity_text, complex_search, topk

1. 若传 entity_id → 直接返回
2. 若无 entity_text → 返回 missing
3. MEMORY_ENTITY_TEXT_EXTRACT_ENABLED=true：
   → 从长文本抽候选名（中英文规则）
   → 逐候选调 resolve_entities，命中返回 entities_resolve_extracted
4. MEMORY_ENTITY_PRONOUN_GUARD=true 且文本为代词 → 跳过直接解析
5. 普通路径：resolve_entities(name=entity_text)，命中返回 entities_resolve
6. complex_search=false 且未命中 → 返回空候选
7. complex_search=true 且未命中：
   → semantic_event_candidates 得事件候选
   → list_events_by_ids 汇总 entity_ids 出现频次
   → list_entities_by_ids 回填实体名
   → 按"频次降序 + entity_id 升序"选 TopK

输出：resolved_id + resolution（event_candidates/candidates/extracted_candidates）
```

### 4.4 Topic 归一化算法（normalize_topic_text）

```
输入：topic_text

1. 空值 → 返回空归一结果
2. 含非 ASCII → 保留原字符，空白归一后转 "/" 路径
3. 纯 ASCII → 仅保留字母数字和 [ /-_.], 转小写后转路径
4. 按 [\s/._-]+ 分词，去重保序，最多保留 8 个 token
5. 产出：topic_id=topic_path, topic_path, tags, keywords

实现要求：LRU 缓存 maxsize=1024，避免重复计算
```

### 4.5 Topic Registry 匹配算法

```
输入：(tenant_id, memory_domain, topic_text)

1. normalize_topic_text → 得 query tags
2. 在同 scope 注册桶内做 Jaccard 相似度：
   score = |A∩B| / |A∪B|
3. 最高分且 score >= min_similarity（默认 0.7）→ 返回已注册 topic_id
4. 未命中 → 返回空（调用方自行注册）

容量限制：max_per_scope=2000
```

### 4.6 Explain 接口流程

```
POST /memory/explain（或 /memory/v1/explain）

1. 校验语义开关（semantic.enabled）
2. 解析租户与用户上下文（tenant_id + user_tokens + memory_domain）
3. 调 resolve_event_id 解析目标事件
4. 未解析到 → 返回 event_not_resolved
5. 命中 → 调 graph_svc.explain_event_evidence(event_id, user_ids, memory_domain)
6. 按参数截断：max_evidence, include_knowledge
7. 返回：event_id + event + evidences + utterances + knowledge + resolution_meta
```

### 4.7 Topic Timeline 接口流程

```
POST /memory/topic-timeline（或 /memory/v1/topic-timeline）

入参优先级（从高到低）：
1. 显式 topic_id/topic_path → 直接查询
2. topic_text/topic → normalize → registry 命中 → 查询
3. event_text/event_id → resolve_event_id → 从事件提取 topic → 查询
4. complex_search=true 且前三者均失败 → 语义候选回退

输出：topic/topic_id/topic_path + timeline[] + total + resolution（可选）
```

### 4.8 Time Since 接口流程

```
POST /memory/time-since（或 /memory/v1/time-since）

1. topic 路径同 §4.7
2. entity 路径同 §4.3
3. topic + entity 同时存在 → 取事件集合交集（AND 语义）
4. 从候选事件集选最近时间戳，与当前 UTC 计算 days_ago（整数天）

输出：days_ago + last_event + mentions_count + resolved_entity/resolved_topic
```

### 4.9 Relations / Quotes / Entity Profile 流程

**Relations**

```
1. 解析主实体（entity_id 或 entity_text → resolve_entity_id）
2. 若传 other_entity_id/other_entity_text → 解析对端实体，查询 first_meeting
3. 调 expand_neighbors(seeds=[entity_id], max_hops, rel_whitelist, neighbor_cap_per_seed)
输出：entity_id + other_entity_id + first_meeting + neighbors[]
```

**Quotes**

```
1. 解析实体
2. 支持：实体视角 / topic 视角 / 混合视角
3. 对事件集逐一 explain_event_evidence 提取 raw_text
4. 按时间排序，截断到 limit

输出：entity_id + quotes[]（text/utterance_id/t_media_start/t_media_end/speaker_track_id）
```

**Entity Profile**

```
1. 传 entity_id 直接使用；传 entity_text → resolve_entity_id
2. 未解析到实体 → 返回稳定空结构 {entity: null, facts: [], recent_events: []}
3. 拉 entity_detail + entity_facts
4. list_events(entity_id, limit=limit_events) 取近期事件

输出：entity + recent_events[] + mentions_count
（命中/未命中均保持相同 schema，便于调用方统一处理）
```

### 4.10 Mention 抽取写入流程

```
Stage3 统一抽取器输出：
  - events[].participants
  - knowledge[].mentions

图构建主链路（build_dialog_graph_upsert_v1）消费上述字段：

1. 事件构建阶段：对 events[].participants 去重/规范化
2. 为 participant 复用/创建 Entity（同 session scope 下稳定 ID）
3. 写 Event -[INVOLVES]→ Entity（来源标记：dialog_tkg_unified_extractor_v1）
4. 知识构建阶段：对 knowledge[].mentions 去重/规范化
5. 为 mention 复用/创建 Entity
6. 写 Knowledge -[MENTIONS]→ Entity（来源标记：dialog_tkg_unified_extractor_v1）
```

---

## 5. 重写红线（Acceptance Criteria）

重写完成的验收标准，**每一条都是硬性要求**：

| # | 红线 | 验证方式 |
|---|---|---|
| 1 | 同一 method + path 有且只有一个 handler，无任何重复注册 | `grep -c "@app.post"` 找重复 |
| 2 | `memory.api.semantic.enabled` 默认 `true`；开关只影响语义执行，不影响接口在 `/api/list` 的可见性 | `test_api_list_endpoint.py` |
| 3 | PATH_SCOPE_REQUIREMENTS 保持 `/memory/v1/`、`/memory/state/` 前缀级覆盖 | `test_api_scope_coverage.py` |
| 4 | GraphService 所有新增参数有默认值（向后兼容） | `test_graph_explain_service.py` |
| 5 | SemanticService 作为唯一服务层，路由 handler 不内联业务逻辑 | Code Review |
| 6 | 全测通过，无 skip | `pytest modules/memory/tests -q` |

---

## 6. 阶段性回补计划（执行版）

### 6.1 依赖关系（先后顺序）

```
GraphService/Neo4jStore 新增方法（地基）
            ↓
      SemanticResolver
       ↙           ↘
  Explain 接口      5个既有接口解析升级

独立支线：
- TopicNormalizer 增强 + TopicRegistry
- Mention 抽取（写入链路）
```

关键约束：

- 每个阶段结束必须全测绿，不接受“中间态破测试”的提交。
- 路由改造遵循“一个 path 一个 handler”，禁止复制一套新 handler。

### 6.2 Phase 0（地基）：GraphService + Neo4jStore 补齐

目标：先补底层依赖，确保后续 Resolver/Explain 可直接挂接。

任务：

- 在 `graph_service.py` 新增：
  - `list_events_by_ids`
  - `list_entities_by_ids`
  - `expand_neighbors`
  - `event_id_by_logical_id`
- 在 `neo4j_store.py` 新增：
  - `query_entities_by_ids`
  - `query_event_id_by_logical_id`
- 增强 `query_entities_by_name`（保持兼容）
- 所有新增参数必须有默认值（如 `user_ids=None`、`memory_domain=None`）

验收：

- 现有全测继续为绿
- 新方法对应单测通过

预估：0.5 天

### 6.3 Phase 1（核心）：SemanticResolver + Explain

目标：完成“从无到有”的 Explain 语义能力与解析主链路。

任务：

- 新建 `semantic_resolver.py`：
  - `resolve_event_id`
  - `resolve_entity_id`
  - 含 `complex_search` 双阶段控制与熔断处理
- 新建 `semantic_api_models.py`（Explain 等请求模型）
- 在 `server.py` 新增：
  - `POST /memory/explain`
  - `POST /memory/v1/explain`
  - 两个装饰器指向同一个 handler
- Handler 保持薄层：参数解析 -> 调 Resolver/Service -> 返回
- 配置补齐 `memory.api.semantic.enabled`，默认 `true`

明确暂不做：

- 不改 5 个既有接口解析逻辑（留到 Phase 2）
- 不补 `/memory/*` 其他短路径别名（留到 Phase 2）

验收：

- `test_semantic_resolver.py`
- `test_semantic_api_endpoints.py`
- 全测保持绿

预估：1.0-1.5 天

### 6.4 Phase 2（增强）：5 个既有接口解析升级 + Topic 增强

目标：将 c9 的“简单匹配”升级为“多策略解析”，实现体验跃迁。

任务：

- 在以下接口接入 Resolver（保留原始默认路径，`complex_search=true` 时走新链路）：
  - `entity-profile`
  - `quotes`
  - `relations`
  - `topic-timeline`
  - `time-since`
- 补齐 `normalize_topic_text` 独立函数（LRU 缓存）与 `TopicNormalization`
- 新建 `TopicRegistry`（Jaccard 相似匹配）
- 实体增强开关：
  - `MEMORY_ENTITY_PRONOUN_GUARD`
  - `MEMORY_ENTITY_TEXT_EXTRACT_ENABLED`
- 新增 `/memory/*` 短路径别名（仅新增装饰器，不新增 handler）

验收：

- `test_topic_normalizer.py`
- `test_graph_search_v1.py`
- `test_memory_entity_profile.py`
- `test_memory_quotes.py`
- `test_memory_relations.py`
- `test_memory_time_since.py`
- `test_memory_topic_timeline.py`
- `test_api_scope_coverage.py`
- `test_api_list_endpoint.py`
- 全测保持绿

预估：1.5-2.0 天

### 6.5 Phase 3（写入增强）：Mention 抽取

目标：提升图谱可读数据质量，为读取接口提供更高覆盖。

任务：

- 接通主链路：消费 `events[].participants` → `Event -[INVOLVES] -> Entity`
- 接通主链路：消费 `knowledge[].mentions` → `Knowledge -[MENTIONS] -> Entity`
- 保持图构建层去重（避免与 speaker 派生 INVOLVES 重复）
- 不引入规则型 mention shadow 旁路（避免额外启发式与开关复杂度）

验收：

- session_write / dialog_tkg 相关单测通过
- 全测保持绿

预估：0.5 天

### 6.6 全量验收与超越标准

全量验收命令：

```bash
python -m pytest modules/memory/tests -q --disable-warnings
```

要求：

- 0 failed
- scope 覆盖完整
- 无重复路由
- `SemanticService` 成为唯一服务入口

“超越 feature 分支”判定口径：

- 功能覆盖：与 `feature/api-upgrade-long-memory-agent` 对齐并补齐
- 工程质量：0 重复路由、签名向后兼容、全测绿
- 可维护性：路由薄层 + 服务层收敛 + 可灰度开关
