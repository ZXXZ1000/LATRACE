# Memory 文档索引（建议从 V2 开始读）

这份目录的目标很简单：让你在不了解历史的情况下，也能在 5 分钟内把 Memory 跑起来，并用对的“隔离键”写入/检索到对的数据。

> 重要：本目录下的 `*_v2.md` 是“当前推荐”；老文档保留但不再保证表述完全正确（尤其是早期的 header/隔离约定）。

---

## 1) 先读什么（V2）

- `modules/memory/docs/API_QUICKSTART_v2.md`
  - 如何启动 Memory API
  - `/write` `/search` 的最小正确调用（包含租户与隔离键）
  - 高层编排 API：`memory.session_write(...)` / `memory.retrieval(...)`（客户端库，无新端口）
- `modules/memory/docs/API Key 级别记忆清除（0313_open）.md`
  - API Key / tenant 级记忆清除的落地方案
  - 已按当前 `modules/memory` 代码对齐：鉴权、scope、Qdrant 多 collection、Neo4j、ingest store、gateway header/JWT 合同
  - 已补充并发边界、`dry_run`、恢复策略、Milvus / Router 注意事项、结构化审计与测试矩阵
  - 适合作为 Phase 1 / Phase 2 的施工说明
- `modules/memory/docs/架构演化方向.md`
  - 当前双内核现状：Legacy kernel vs TKG kernel
  - 两套内核在图、向量、检索编排层的耦合关系
  - 为什么 TKG 应该成为唯一未来内核，以及推荐的演化方向
- `modules/memory/docs/TKG与Zep对比及论文叙事方向.md`
  - Zep 论文与当前 TKG 实现的系统化对比
  - 哪些设计差异最可能解释 benchmark 提升
  - 如果要写成论文，应该如何组织主张、边界与实验故事
- `modules/memory/docs/TKG与Zep对比及论文叙事方向_v2.0.md`
  - 推荐作为论文工作主文档使用的 V2.0 版本
  - 从问题定义、Zep 原始叙事、MOYAN 理论演化、当前 TKG 实现到 benchmark 叙事形成一套完整闭环
  - 明确论文最安全的主张、最关键的差异点与必须补的实验
- `modules/memory/docs/TKG顶会论文规划路线图.md`
  - 面向未来 1 年的顶会论文组合规划
  - 对系统论文、可学习路由、多分辨率理论、公理体系四条线做收益/风险/投入评估
  - 给出推荐优先级、时间预算、投稿方向与资源分工建议
- `modules/memory/docs/TKG论文叙事方向_二次审视.md`
  - 结合理论演化文档、当前实现与 Zep 原文做的第二轮校准
  - 明确哪些点是论文安全主张，哪些只是架构愿景
  - 修正第一版 memo 中可能过强或不够精确的表述
- `modules/memory/docs/GRAPH_v1.md`
  - 图模型 v1 与“图扩展”的默认行为（几跳、白名单、上限与治理）
- `modules/memory/docs/RETRIEVAL_API_AND_WORKFLOW.md`
  - Qdrant/Neo4j 里分别存什么、如何用唯一 ID 对齐
  - `/search`（Qdrant ANN → Neo4j 邻域扩展 → 重排）与 `/graph/v1/search`（Graph-first）的全量 API 与端到端流程

---

## 2) 现状快照（你最容易踩坑的地方）

### 2.1 租户（Tenant）：开发模式 vs 生产模式

这套系统里，“tenant”是硬边界，但你怎么把 tenant 传进来取决于是否开启 auth。

- **开发/评测模式（默认）**：`memory.api.auth.enabled=false`
  - 必须传 Header：`X-Tenant-ID: <tenant>`，否则 400；
  - 且 `POST /search` 不会自动把 header 注入 filters，所以**仍然建议**显式传 `filters.tenant_id=<tenant>`，避免未来切换 auth/多租户数据时出现“串租户”的隐患。
- **生产模式（推荐）**：`memory.api.auth.enabled=true`
  - tenant 由 token/JWT 解析得到（不再依赖 `X-Tenant-ID`）；
  - 你仍可以额外传 `X-Tenant-ID` 做显式标注，但不应依赖它作为唯一来源。
  - 注意：当前实现默认读取 `X-API-Token`（或配置指定的 header），同时也支持回退解析 `Authorization: Bearer ...`；内网网关仍建议统一转发为 `X-API-Token`。

### 2.2 强隔离主轴：`metadata.user_id: list[str]`

- 写入：`metadata.user_id` 必须是 `list[str]`（服务端会尽力归一化，但别赌运气）。
- 检索：`filters.user_id: list[str]` + `filters.user_match: any|all`
  - `all`：必须同时命中列表里的全部 token（推荐用于“单对话/单产品+单用户”强隔离）
  - `any`：命中任意 token 即可（适合做“个人 + 公共”并集召回）

### 2.3 作用域（Scope）不是“隔离”，是“降噪回退链路”

- `run_id`：一次会话/任务的打包键（更像 session）。
- `memory_domain`：域（例如 `dialog` / `video` / `work`）。
- `memory_scope`：更细粒度隔离（例如每个视频/样本的稳定 hash）。
- `scope`（search 入参）控制服务端的回退顺序（例如 `session → domain → user → global`），用来“逐步放宽”召回范围，不是安全隔离替代品。

### 2.4 多端/设备隔离：不要发明新字段，复用 user_id token

当前 `SearchFilters` 的“强隔离轴”只有 `user_id(list)+user_match`。为了把“用户/产品/设备/公共”都纳入隔离，我们约定把它们编码为 **token** 放进同一个数组里：

- `u:{user_id}`：用户主体（必选）
- `p:{product_id}`：产品/应用（可选，做 B 端与 C 端双重隔离）
- `d:{device_id}`：设备/客户端实例（可选，用于同一用户多端隔离）
- `pub`：公共数据（可选，用于“用户私有 + 公共知识”合并召回）

推荐写入模式（越往下越“隔离更强”）：

- 用户跨端共享：`["u:alice"]`
- 用户 + 产品隔离：`["u:alice", "p:companion_bot"]`
- 用户 + 产品 + 设备隔离：`["u:alice", "p:companion_bot", "d:iphone15"]`

检索时的典型策略：

- 强隔离检索：`user_match="all"`（必须同时命中全部 token）
- 合并召回（包含公共）：`user_match="any"` + 传入 `["u:alice", "pub"]`（或由高层 `retrieval` 做两次检索融合）

### 2.5 两类 Key：产品 APIK（隔离/鉴权）vs BYOK（模型）

别混了：

- **产品 APIK**：用户携带我们的 key 在不同 MCP 客户端/设备上访问 Memory，用于鉴权与“用户隔离身份”的稳定来源。
  - 推荐用 `X-API-Token: <APIK>`（生产开启 auth 后生效）
  - 同时把用户隔离落实到 `user_tokens=["u:{user_uuid}", ...]`（由客户端库或上层负责生成/携带）
- **BYOK**：用户自带大模型 provider/key，仅用于抽取与 rerank（客户端库侧使用），不参与数据隔离。

当你未来外接 SaaS/企业 IdP（还没定哪家）时：

- 最小兼容策略：对齐 OIDC/JWT（JWKS 验签）并冻结我们内部需要的最小 claims（`tenant_id` + `sub`）；
- 最稳策略：在网关层把“任意 SaaS 的 token/claims”归一化成你们自己的内部 JWT，然后 Memory 只认这一套内部 JWT。

---

## 3) 老文档（Legacy / 仅供参考）

- `modules/memory/docs/API_QUICKSTART_v1.md`：v1 冻结面说明（字段/端点总体仍可参考，但缺少 V2 的高层编排 API 与若干现状修订）。
- `modules/memory/docs/USAGE.zh.md`：早期使用指南（内容较多，部分约定已演进）。
- `modules/memory/docs/graph_v0_usage.md`：图 v0 用法与脚本（v1 已扩展更多节点/边类型）。
