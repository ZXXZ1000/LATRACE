# TKG Graph（V1）与图扩展（Graph Expansion）

这份文档解决一个核心问题：**“图到底怎么帮检索？”**  
别把它神化：图扩展不是推理引擎，它是一个受限的邻域展开器，用来把“向量召回的点”连成“可解释的证据网”。

---

## 0. 先分清楚：这里其实有“两张图”

在同一个 Neo4j 里，我们维护两套用途不同的数据：

1) **Typed TKG Graph（真相源 / ground truth）**  
   - **合同模型**：`modules/memory/contracts/graph_models.py`（`GraphUpsertRequest`）  
   - **写入入口**：`POST /graph/v0/upsert`（强制 `tenant_id`）  
   - **节点/边**：`MediaSegment / Evidence / UtteranceEvidence / Entity / Event / TimeSlice / ...`  
   - **定位**：用于 L1–L5 的“证据链与结构化查询”，答案需要可回溯到 Evidence/Utterance/Segment。

2) **MemoryEntry Projection Graph（索引投影 / 可丢可重建）**  
   - **合同模型**：`modules/memory/contracts/memory_models.py`（`MemoryEntry` + `Edge`）  
   - **写入入口**：`POST /write`  
   - **Neo4j 标签**：`modules/memory/infra/neo4j_store.py` 中以 `:MemoryNode` 落库（避免与 typed graph 的 `:Entity` 约束冲突）  
   - **定位**：服务 `/search` 的“邻域展开器”用它做 2–3 hop 补充证据，主要服务召回与可解释性，不应被当作最终真相。

一句话：**typed graph 是事实与证据的权威存储；MemoryEntry 图是为检索加速的投影层。**

## 1. V1 图模型：以代码为准

图的请求模型在这里：`modules/memory/contracts/graph_models.py`

`GraphUpsertRequest` 当前包含（非穷尽，只列主干）：

- 时空载体
  - `MediaSegment`：媒体片段（含 t_media_start/end）
  - `TimeSlice`：时间切片（多粒度，含 t_abs_start/end 与 t_media_start/end）
  - `SpatioTemporalRegion`：空间区域/房间/区域层级
- 证据
  - `Evidence`：算法证据（bbox/span/embedding_ref 等）
  - `UtteranceEvidence`：ASR 语句证据（说话内容 + 时间）
- 抽象实体与语义
  - `Entity`：人物/物体/概念（可接 identity registry）
  - `Event`：事件（摘要 + 绝对时间）
  - `Knowledge`：结构化知识/事实（可带 registry_status）
  - `State`：状态机/属性在某时间段的取值
- `GraphEdge`：统一边模型（rel_type + confidence/weight/layer/kind/source…）

> 终极蓝图参考：`docs/时空知识记忆系统构建理论/3. Schema 层（What exactly in code）/TKG-Graph-v1.0-Ultimate.md`  
> Memory 模块以“可落地、可治理”为先，不会一次把蓝图里所有推理边都物化。

---

## 2. 图扩展在 Memory.search 里的位置

`modules/memory/application/service.py::MemoryService.search` 的主链路是：

1) 向量召回（Qdrant）
2) （可选）图邻域展开（Neo4j）
3) 混合重排（vector/BM25/graph/recency）
4) 输出 `hits + neighbors + hints + trace`

“图扩展”发生在第 2 步：它以向量命中的 entry 作为 seed，在图里展开邻居，产出 neighbors 结构与额外的 graph signals（用于 rerank）。

> 注意：这里的“展开”指 **MemoryEntry Projection Graph（:MemoryNode）** 的邻域扩展；  
> typed TKG Graph（`/graph/v0/*`）有独立的查询面与解释型接口（如 `/graph/v0/explain/*`）。

## 2.1 Graph-first 检索（/graph/v1/search）：直接在“真相图”里找答案

当你想让 LLM 做 L1–L5 问答，最靠谱的路径是：**先在 typed TKG Graph 里定位 Event，再把 Evidence/Utterance/Segment 证据链一起返回**。

- **端点**：`POST /graph/v1/search`
- **入参**：
  - `query`：自然语言问题或关键词
  - `topk`：返回多少个候选事件（默认 10）
  - `source_id`（可选）：只在某个视频/来源内检索
  - `include_evidence`：是否返回证据链（默认 true）
- **返回**：`items[]`，每个 item 包含候选 `event_id/score`，以及 `event/entities/places/timeslices/evidences/utterances` 证据包。

实现位置：
- `modules/memory/infra/neo4j_store.py::search_event_candidates`：优先用 Neo4j fulltext 索引（`tkg_event_summary_v1 / tkg_utterance_text_v1 / tkg_evidence_text_v1`），缺失则降级为 `CONTAINS`；
- `modules/memory/application/graph_service.py::search_events_v1`：对候选事件调用 `explain_event_evidence` 拼装证据链（带 LRU 缓存）。

---

## 3. 默认几跳？为什么不是越多越好？

蓝图建议：API 默认 2–3 hop（见 `TKG-Graph-v1.0-Ultimate.md` 的查询约束）。

Memory 当前配置：

- 配置文件默认：`modules/memory/config/memory.config.yaml`
  - `memory.search.graph.max_hops: 3`
- 运行时覆盖默认：`modules/memory/config/runtime_overrides.json`
  - `max_hops: 2`

结论（你应该按这个理解）：
- **默认有效值通常是 2 跳**（因为 runtime override 盖住了 YAML）。
- 2–3 跳的直觉：
  - 1 hop：从事件到直接证据（“这句话/这段视频”）
  - 2 hop：从事件连到参与者/地点/时间片（“谁/在哪/何时”）
  - 3 hop：触及更高阶的时序证据链或共现关系（但噪声与成本都会上升）

> 经验法则：你不是在“找真理”，你是在“找证据”。超过 3 跳，通常是在用成本换幻觉。

---

## 4. 图扩展的治理：白名单、上限与隔离

图扩展必须是“可控”的，否则它会把你的检索变成随机游走。

### 4.1 关系白名单（rel_whitelist）

配置：`memory.search.graph.rel_whitelist`  
只允许在白名单关系上扩展，避免把弱关系/推理关系无限放大。

### 4.2 fanout 上限（neighbor_cap_per_seed）

配置：`memory.search.graph.neighbor_cap_per_seed`  
限制每个 seed 最多展开多少邻居，防止单个高连接节点把结果淹没。

### 4.3 隔离限制（restrict_to_*）

配置（并支持运行时覆盖）：
- `restrict_to_user`
- `restrict_to_domain`
- `restrict_to_scope`
- `allow_cross_user/domain/scope`

默认应该是“收紧”的：同用户、同域、同 scope 内扩展；诊断/管理场景才显式放开。

---

## 5. 典型关系与查询路径（L1/L2 问题怎么落在图上）

这里不讲所有关系，只列对“对话+日常行为”最有用的一小撮。

### 5.1 常用关系（示意表）

- `TEMPORAL_NEXT`：事件时序链（A 之后是 B）
- `OCCURS_AT`：事件发生在某个时间片/地点
- `APPEARS_IN / SAID_BY`：人物出现在片段/说了某句话
- `SUPPORTED_BY`：高层事件/知识由哪些 UtteranceEvidence 支撑
- `CO_OCCURS`：实体/事件在同一 TimeSlice 里高频共现

你可以粗略地按下面的方式理解“几跳”：

- 从一个 Event 出发：
  - 1 hop：
    - `Event -[:SUPPORTED_BY]-> UtteranceEvidence`（原话证据）
    - `Event -[:OCCURS_AT]-> TimeSlice`（在哪一段时间发生）
  - 2 hop：
    - `Event -[:OCCURS_AT]-> TimeSlice -[:CONTAINS]-> 其他 Event`（同一时间段发生了什么）
    - `Event -[:SUPPORTED_BY]-> UtteranceEvidence -[:SAID_BY]-> Entity`（谁说的）
  - 3 hop：
    - `Event -[:TEMPORAL_NEXT]-> Event_next -[:SUPPORTED_BY]-> UtteranceEvidence`（“回家后做的第一件事”）
    - `Entity -[:APPEARS_IN]-> Segment -[:OCCURS_AT]-> TimeSlice`（某人在哪些时段频繁出现）

### 5.2 一个简单例子：为什么默认 2–3 hop 就够了

问题：**“我回家后做的第一件事是什么？”**

脑补一条路径：

1) 向量召回找到与 “回家” 最接近的事件 `Event_home_arrive`；
2) 图扩展：
   - 用 `TEMPORAL_NEXT` 找出时间上紧跟其后的事件 `Event_after_home`（1 hop）；
   - 再通过 `SUPPORTED_BY` 拿到原始 UtteranceEvidence（2 hop），得到这件事的自然语言描述；
3) 返回时，向量分数 + 图信号一起用于重排，把 `Event_after_home` 排在最前。

再往外扩 4、5 hop，大概率是在乱走（例如“很久以后的一次出游”），与这个问题的回答相关性迅速下降。

---

## 6. 如何在线调参（不改代码）

Memory API 提供热配置端点（生产可要求签名）：

- `POST /config/graph`
  - `{"max_hops": 2, "neighbor_cap_per_seed": 9, "rel_whitelist": [...]}`

查看当前 override：

- `GET /config/graph`

> 注意：服务端有硬上限 clamp（防止你把 max_hops/topk 调到离谱导致服务被打爆）。
