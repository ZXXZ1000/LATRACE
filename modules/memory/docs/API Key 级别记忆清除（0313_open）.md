# API Key 级别记忆清除（0313_open）

- 版本：v0.2
- 日期：2026-03-13
- 状态：open
- 性质：代码对齐版实施方案
- 推荐阅读对象：`modules/memory` 开发者、SaaS 网关接入方、上线运维

本文把“API Key 级别记忆清除”方案对齐到当前 `modules/memory` 实现，并根据评审意见补强了以下内容：

- 并发安全与重入保护
- `dry_run` 预览语义
- 限频建议
- 恢复/回滚边界
- Milvus / `VectorStoreRouter` 的实现深度
- 结构化审计
- 更完整的测试矩阵

---

## 1. 先说结论

这件事可以做，而且建议按下面这套更贴近当前代码的方式推进。

1. Memory 内部端点建议使用 `POST /memory/v1/clear`
   - 当前语义接口统一挂在 `/memory/v1/*`
   - 不建议新开一个风格不同的 `/v1/clear`

2. JWT 合同建议直接采用“方案 A”
   - `sub = api_key_id`
   - `tenant_id` 或 `tid` = account / tenant
   - 这是当前代码最兼容、改动最小的方案

3. Phase 1 先按 tenant 清即可
   - 当前 `auth.enabled=false` 时，`tenant_id` 来自 `X-Tenant-ID`
   - 如果 SaaS 网关已经把 stripped API key 映射为 tenant，那么“按 tenant 清”就是“按 key 清”

4. `confirm=false` 不建议直接报错
   - 更推荐把它定义为 `dry_run`
   - 先返回预计删除数量，再由 `confirm=true` 执行实际清除

5. 清除操作不是跨存储原子事务
   - Qdrant / Neo4j / SQLite(or PostgreSQL) 之间没有分布式事务
   - 接口必须显式支持 `partial_failure`
   - 实现必须是幂等、可重试

6. 必须正视并发边界
   - clear 与 clear 并发时，至少要做“同 tenant 单飞”
   - clear 与 ingest 并发时，如果不上写入闸门，不保证最终完全空
   - 最低要求是把这个边界写进合同；更推荐加锁 + 网关短暂阻断写入

7. 当前 Qdrant 删除不能只删一个 collection
   - 真实数据分散在 `text / image / audio / clip_image / face`
   - tenant 过滤字段是 `metadata.tenant_id`，不是顶层 `tenant_id`

8. Phase 2 不只是给 `session_write.py` 加字段
   - 当前向量元数据的写入点至少包括：
     - `modules/memory/application/graph_service.py`
     - `modules/memory/domain/dialog_tkg_vector_index_v1.py`
     - `modules/memory/session_write.py`

---

## 2. 当前代码现状（已核对）

### 2.1 鉴权与 tenant 解析

当前实现位于 `modules/memory/api/server.py`：

- `_authenticate_request()`：
  - `auth.enabled=false` 时，直接从 `X-Tenant-ID` 取 tenant
  - `auth.enabled=true` 时：
    - 优先读配置 header，默认 `X-API-Token`
    - 同时也支持回退解析 `Authorization: Bearer ...`
    - tenant 来自配置 claim（默认 `tenant_id`）或 `tid`
- `ctx.subject` 当前直接来自 JWT `sub`
- `_enforce_security()` 负责：
  - 鉴权
  - scope 检查
  - 可选签名校验

### 2.2 现有删除能力

当前已有：

- `POST /delete`
- `POST /batch_delete`
- `POST /graph/v0/admin/purge_source`

特点：

- 都是危险操作
- 都走 `await _enforce_security(request, require_signature=True)`
- `delete` / `batch_delete` 当前需要 `memory.admin`

### 2.3 向量层不是只存一个 collection

`modules/memory/infra/qdrant_store.py` 当前会按模态写入多个 collection：

- `text`
- `image`
- `audio`
- `clip_image`
- `face`

tenant 过滤字段在当前真实实现里是：

- `metadata.tenant_id`

不是顶层 `tenant_id`。

因此“清空某个 tenant 的向量”必须：

- 按 `metadata.tenant_id` 过滤
- 遍历所有已配置 collection

不能只删 `text` collection。

### 2.4 Ingest job store 已经有 `api_key_id`

当前两个 job store 都已有 `api_key_id`：

- `modules/memory/infra/async_ingest_job_store.py`
- `modules/memory/infra/pg_ingest_job_store.py`

也就是说：

- PostgreSQL / SQLite 的 schema 基础已经具备
- Phase 2 的主要难点不在 job store
- 难点在向量元数据写透、JWT/header 合同，以及多存储清除一致性

### 2.5 SaaS 网关在本仓库里的真实落点

当前仓库里的网关辅助模块不是 `index.js`，而是：

- `modules/saas_gateway/auth.py`
- `modules/saas_gateway/forward.py`

现状：

- `prepare_forward_headers()` 当前注入的是 `X-API-Key-Id`
- 既有对接文档里也出现过 `X-Principal-ApiKey-Id`

建议实现时：

- Memory 服务同时兼容两个 header
- 代码内统一收敛到一个 canonical 名字
- 网关改动优先落在 `modules/saas_gateway/forward.py` 一侧，而不是去找不存在的 `index.js`

### 2.6 当前 `sub` 已被当成 `api_key_id`

已核对的实际用法：

- `modules/memory/api/server.py`
  - ingest 创建 job 时：`api_key_id=(str(ctx.get("subject")) if ctx.get("subject") else None)`
  - retrieval / QA 的 usage context 里也复用了 `ctx.subject`

这意味着当前默认语义是：

- `sub = api_key_id`

这和“`sub=accountId`, `sid=apiKeyId`”不是同一套合同。

### 2.7 Milvus 在 Phase 2 不是零成本

当前 `MilvusStore`：

- `_scalar_fields()` 里没有 `api_key_id`
- `_build_expr()` 也没有 `api_key_id` 过滤语义

所以：

- Phase 1 如果部署不使用 Milvus，可以暂不实现
- 但如果部署启用了 `VectorStoreRouter` 或直接走 Milvus，`clear` 的能力必须一起补齐
- Phase 2 想支持 `scope="apikey"`，Milvus 不只是加一个 delete 方法，还需要 schema / scalar fields / expr 三处一起扩展

---

## 3. 实施前必须冻结的几个合同

### 3.1 路由合同

建议对外、对内统一成：

- 网关外部：`POST /api/v1/memory/v1/clear`
- Memory 内部：`POST /memory/v1/clear`

原因：

- 当前 `/memory/v1/*` 已经是语义接口命名空间
- 后续 `PATH_SCOPE_REQUIREMENTS` 也更容易维护

### 3.2 JWT 合同

这里有两个方向，但本文推荐只选“方案 A”。

**推荐方案 A：保持当前代码语义**

- `sub = api_key_id`
- `tenant_id` 或 `tid` = account / tenant
- 如需记录 account principal，新增 claim，例如 `aid` / `account_id`

优点：

- 对当前 `ctx.subject -> api_key_id` 的既有代码最兼容
- Phase 1 / Phase 2 改动最小
- 不会把现有 ingest / usage 链路静默改坏

**备选方案 B：改成 `sub=accountId`, `sid=apiKeyId`**

如果坚持这样做，Memory 侧必须新增显式解析逻辑，例如：

- `_resolve_api_key_id(ctx, request)`：
  - 先读 JWT `sid`
  - 再读 `X-API-Key-Id`
  - 再读 `X-Principal-ApiKey-Id`
  - 最后才 fallback 到 `ctx.subject`

否则当前 ingest / usage 链路会把 accountId 错写进 `api_key_id`。

### 3.3 Scope 合同

建议新增：

- `memory.clear`

但要注意当前 `_check_scope()` 对“无 scopes 的 legacy token”是放行的。

因此如果要把 clear 当成真正的权限边界，至少要满足以下两项之一：

- 网关保证内部 JWT 总是显式带 scope
- 或 Memory 对 `/memory/v1/clear` 做 stricter 检查，要求：
  - 必须显式有 `memory.clear`
  - 或有 `memory.admin`
  - 不能走“空 scopes 兼容放行”

### 3.4 Header 合同

建议 Memory 服务兼容读取：

- `X-API-Key-Id`
- `X-Principal-ApiKey-Id`

并在代码里声明 canonical 名字，例如：

- 代码 canonical：`X-API-Key-Id`
- `X-Principal-ApiKey-Id` 作为兼容别名

### 3.5 一致性合同

建议把 clear 的一致性语义在文档里写死：

- clear 是“多存储、幂等、best-effort”操作
- clear 不提供跨存储原子事务
- `confirm=false` 只返回预估，不写数据
- `confirm=true` 会执行删除
- 如果没有写入闸门，clear 不保证和并发 ingest 的全序关系

换句话说：

- `confirm=true` 只能保证“尽力清除 clear 开始前已经存在的数据”
- 不能保证“clear 返回后 tenant 永久为空”
- 想要更强保证，必须在网关层短暂阻断该 tenant 的新写入

---

## 4. API 设计建议

### 4.1 请求模型

建议新增：

```python
class ClearRequest(BaseModel):
    scope: Literal["tenant", "apikey"] = "tenant"
    api_key_id: Optional[str] = None
    confirm: bool = False  # false = dry_run, true = execute
    reason: Optional[str] = None
```

语义建议：

- `confirm=false`：
  - dry run
  - 返回预估删除数量
  - 不做任何写操作
- `confirm=true`：
  - 真正执行
  - `reason` 必填

### 4.2 响应模型

建议不要只返回聚合数字，而是把预估、实际结果、分存储详情都放进去：

```python
class ClearStoreResult(BaseModel):
    status: Literal["pending", "completed", "failed", "skipped"]
    estimated: int = 0
    deleted: int = 0
    error: Optional[str] = None


class ClearResponse(BaseModel):
    status: Literal["dry_run", "completed", "partial_failure", "rejected"]
    dry_run: bool = False
    tenant_id: str
    api_key_id: Optional[str] = None
    estimated_vectors: int = 0
    estimated_graph_nodes: int = 0
    estimated_ingest_jobs: int = 0
    cleared_vectors: int = 0
    cleared_graph_nodes: int = 0
    cleared_ingest_jobs: int = 0
    stores: Dict[str, ClearStoreResult] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
```

### 4.3 推荐返回语义

#### `confirm=false` → dry run

```json
{
  "status": "dry_run",
  "dry_run": true,
  "tenant_id": "tenant_x",
  "estimated_vectors": 1234,
  "estimated_graph_nodes": 56,
  "estimated_ingest_jobs": 78,
  "stores": {
    "qdrant": {"status": "completed", "estimated": 1234, "deleted": 0},
    "neo4j": {"status": "completed", "estimated": 56, "deleted": 0},
    "ingest_jobs": {"status": "completed", "estimated": 78, "deleted": 0}
  }
}
```

#### `confirm=true` → execute

```json
{
  "status": "completed",
  "dry_run": false,
  "tenant_id": "tenant_x",
  "cleared_vectors": 1234,
  "cleared_graph_nodes": 56,
  "cleared_ingest_jobs": 78
}
```

#### 部分失败

```json
{
  "status": "partial_failure",
  "dry_run": false,
  "tenant_id": "tenant_x",
  "cleared_vectors": 1234,
  "cleared_graph_nodes": 0,
  "cleared_ingest_jobs": 78,
  "warnings": [
    "neo4j purge failed, retry is safe"
  ]
}
```

---

## 5. Phase 1 设计（立即可落地）

### 5.1 适用边界

适用于当前部署：

- `auth.enabled=false`
- tenant 本身就是 stripped API key

此时：

- clear scope = tenant
- 不需要 vector metadata 中的 `api_key_id`

### 5.2 Memory 端点实现

建议新增：

- `POST /memory/v1/clear`

伪代码建议：

```python
@app.post("/memory/v1/clear", response_model=ClearResponse)
async def clear_memories(body: ClearRequest, request: Request):
    ctx = await _enforce_security(request, require_signature=True)
    tenant_id = str(ctx.get("tenant_id") or "")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="unauthorized")

    if body.scope != "tenant":
        raise HTTPException(status_code=400, detail="scope_not_supported_in_phase1")

    if body.confirm and not str(body.reason or "").strip():
        raise HTTPException(status_code=400, detail="reason_required")

    lock = await acquire_clear_lock(tenant_id)
    if not lock.acquired:
        raise HTTPException(status_code=409, detail="clear_in_progress")

    try:
        estimate = await estimate_clear(...)
        if not body.confirm:
            return dry_run_response(...)
        result = await execute_clear(...)
        return result
    finally:
        await lock.release()
```

这里建议 **保留 `require_signature=True`**，原因很简单：

- 现有 `delete` / `batch_delete` / `graph admin purge` 都要求签名
- clear 比它们更危险，不应降低安全等级

### 5.3 Scope 映射的正确写法

不要只是在 `PATH_SCOPE_REQUIREMENTS` 末尾 append 一条：

```python
"/memory/v1/clear": "memory.clear"
```

因为当前 `_required_scope_for_path()` 是按字典顺序做前缀匹配的，已有：

```python
"/memory/v1/": "memory.read"
```

如果 clear 规则排在后面，`/memory/v1/clear` 会先命中 `memory.read`。

建议二选一：

1. 把 `"/memory/v1/clear"` 插到 `"/memory/v1/"` 前面
2. 更稳：重构 `_required_scope_for_path()` / `_lookup_scope_mapping()`，改成“先 exact，后 prefix”

第二种更不容易再踩坑，也建议顺手补测试，避免后续再有子路径被前缀误吞掉。

### 5.4 删除执行建议：不要用 fail-fast `asyncio.gather`

原始草案里容易想到直接：

```python
await asyncio.gather(vec_delete(), graph_delete(), jobs_delete())
```

但对于 clear，更推荐：

1. 先做预估计数
2. 再按存储逐步执行，或使用 `gather(return_exceptions=True)`
3. 每个存储都单独记录 `estimated / deleted / error`
4. 最终汇总为 `completed` 或 `partial_failure`

推荐执行顺序：

1. Qdrant / Milvus
2. Neo4j
3. ingest_jobs

原因：

- `ingest_jobs` 保留到最后删除，更利于失败后的取证和重试定位
- 真删前先拿到预估值，也更利于审计和 dry run

---

## 6. 存储层实施建议

### 6.1 Qdrant

建议在 `modules/memory/infra/qdrant_store.py` 新增：

```python
async def count_by_filter(self, *, tenant_id: str, api_key_id: str | None = None) -> int:
    ...

async def delete_by_filter(self, *, tenant_id: str, api_key_id: str | None = None) -> int:
    ...
```

关键点：

- filter 字段用 `metadata.tenant_id`
- Phase 2 再追加 `metadata.api_key_id`
- 必须遍历 `self.collections.values()`
- 每个 collection 都先 `count` 再 `delete`
- 返回所有 collection 的总计数

### 6.2 InMem vector store

建议在 `modules/memory/infra/inmem_vector_store.py` 新增与 Qdrant 同名方法：

- `count_by_filter(...)`
- `delete_by_filter(...)`

作用：

- 让单测 / 本地 harness 可以验证 clear 的接口契约
- 不依赖真实 Qdrant

### 6.3 Milvus

Milvus 需要分两层看。

#### Phase 1

如果当前部署满足以下任一条件，Milvus 可以暂时跳过：

- 生产只使用 Qdrant
- `VectorStoreRouter` 不会把该 tenant 路由到 Milvus

但如果部署里真的启用了 Milvus 或 `VectorStoreRouter`，那就必须补齐：

- `count_by_filter(...)`
- `delete_by_filter(...)`

实现建议：

1. 复用 `_build_expr(filters)` 生成 `tenant_id == ...`
2. 用 paginated `collection.query(expr=..., output_fields=[id])` 统计预估数量
3. 用 `collection.delete(expr=expr)` 做删除
4. 遍历所有模态 collection

说明：

- Milvus 没必要强求和 Qdrant 完全同一套实现细节
- 但对外接口必须返回统一的 `estimated / deleted / error`

#### Phase 2

Milvus 要支持 `scope="apikey"`，还需要：

1. 在 `_scalar_fields()` 写入 `api_key_id`
2. 在 collection schema 中持久化该字段
3. 在 `_build_expr()` 增加 `api_key_id` 过滤

否则 Phase 2 只能在 Qdrant 场景下成立，Milvus 会掉队。

### 6.4 VectorStoreRouter

如果 clear 走 `svc.vectors`，那 `modules/memory/infra/vector_store_router.py` 也必须新增：

- `count_by_filter(...)`
- `delete_by_filter(...)`

否则只有底层 `QdrantStore` / `MilvusStore` 有方法，路由场景下 endpoint 会失效。

### 6.5 Neo4j

建议在 `modules/memory/infra/neo4j_store.py` 新增：

- `count_tenant_nodes(...)`
- `purge_tenant(...)`

实现建议：

- 分批：

```cypher
MATCH (n {tenant_id: $tenant})
WITH n LIMIT $batch
DETACH DELETE n
RETURN count(*) AS deleted
```

- dry run 时只 count，不 delete
- 真删时循环到最后一批 `< batch_size`

同时建议在 `modules/memory/infra/inmem_graph_store.py` 补一个测试实现：

- `count_tenant_nodes(...)`
- `purge_tenant(...)`

### 6.6 Ingest job store

两个后端都建议补齐：

- `AsyncIngestJobStore.count_by_tenant(...)`
- `AsyncIngestJobStore.clear_by_tenant(...)`
- `PgIngestJobStore.count_by_tenant(...)`
- `PgIngestJobStore.clear_by_tenant(...)`

Phase 2 再加：

- `count_by_apikey(...)`
- `clear_by_apikey(...)`

---

## 7. 并发安全、重入与写入顺序

这是这份方案必须补充的重点。

### 7.1 clear 与 clear 并发

最低要求：

- 同一 tenant 同时只能有一个 clear 在执行

推荐实现：

- 单实例 / SQLite / 本地测试：
  - 进程内 `asyncio.Lock`
- PostgreSQL 后端：
  - `pg_try_advisory_lock(hash(tenant_id))`
- 多实例但不走 PG：
  - Redis lock 或网关层分布式锁

如果拿不到锁，建议返回：

- `409 clear_in_progress`
  或
- `423 locked`

### 7.2 clear 与 ingest 并发

必须明确写进合同：

- 如果 clear 执行期间允许该 tenant 继续 ingest，clear 结束后仍可能出现残留写入

原因：

- 进行中的 ingest 可能在 clear 开始前已通过鉴权，但在 clear 结束后才真正写入向量 / 图 / jobs

因此推荐分两个级别：

#### 最低可上线语义

- clear 不保证和并发写入的全序关系
- 文档明确声明：
  - “clear 返回后，若存在进行中的写入，请求方可能看到少量残留数据；重复 clear 是安全的”

#### 更强生产语义

- 网关在 `confirm=true` clear 开始后，短暂阻断该 tenant 的写入接口：
  - `/ingest`
  - `/ingest/dialog/v1`
  - `/write`
  - 以及其他写路径

推荐阻断策略：

- clear 持锁期间，网关对该 tenant 的新写请求返回 `409 tenant_clear_in_progress`

### 7.3 重复 clear 的语义

建议明确为幂等：

- 第一次 clear：删掉真实数据
- 第二次 clear：返回 0，不报错

---

## 8. 速率限制建议

文档不应只写“建议限频”，建议把默认值写清楚。

推荐：

- 每 tenant：
  - burst：`1 次 / 分钟`
  - sustained：`5 次 / 小时`

补充建议：

- `dry_run` 可与执行共用同一 bucket，也可以更宽松，例如：
  - `10 次 / 小时`
- `memory.admin` 的内部运维通道可单独放行，但必须有额外审计

速率限制落点优先建议：

- 网关侧实现
- `modules/saas_gateway/forward.py` 负责统一 header 注入
- 业务路由处按 `tenant_id` 做 bucket key

---

## 9. `dry_run` 与恢复策略

### 9.1 `confirm=false` 的语义

这里建议明确改成：

- `confirm=false` = dry run

优势：

- 客户端可以先预览“将删除多少”
- 用户体验比“直接 400”更好
- 审批流 / 控制台弹窗也更容易接

### 9.2 恢复能力的真实边界

这里也不应回避现实。

默认建议写死：

- clear 从 API 语义上是**不可逆**操作
- 服务端默认不提供“一键恢复”

如果上线环境需要恢复能力，建议作为运维能力，而不是塞进 clear 热路径：

- Qdrant：
  - 依赖集群快照 / 备份
- Neo4j：
  - 依赖外部 backup / restore
- ingest_jobs：
  - 依赖 SQLite 文件备份或 PostgreSQL PITR

### 9.3 是否要在 clear 前自动做快照

不建议默认启用请求路径内自动快照，原因：

- 时间不可控
- 成本高
- 失败模式复杂

更现实的做法是：

- 文档声明 clear 默认不可逆
- 如业务要求恢复，运维层面确保已有备份策略

---

## 10. 结构化审计建议

### 10.1 日志

不建议只打一条裸 `logger.warning(...)`。

建议使用结构化日志，至少包含：

- `event_type`: `memory_clear`
- `tenant_id`
- `api_key_id`
- `scope`
- `dry_run`
- `initiator`
- `reason`
- `request_id`
- `duration_ms`
- `stores`
- `status`

示意：

```python
audit_logger.warning(
    "memory.clear",
    extra={
        "event_type": "memory_clear",
        "tenant_id": tenant_id,
        "api_key_id": resolved_api_key_id,
        "scope": body.scope,
        "dry_run": not body.confirm,
        "initiator": str(ctx.get("subject") or ""),
        "reason": body.reason,
        "request_id": _request_id_from_request(request),
        "status": status,
        "duration_ms": duration_ms,
        "stores": store_results,
    },
)
```

### 10.2 AuditStore

当前仓库已有 `modules/memory/infra/audit_store.py`。

建议 clear 完成后额外写一条 audit event，例如：

- `CLEAR_TENANT`
- `CLEAR_APIKEY`

这样后续排查时，不只依赖日志系统。

---

## 11. Phase 2 设计（auth.enabled=true 后）

### 11.1 什么时候需要 Phase 2

当出现这种模型时必须上：

- 一个 account / tenant 下有多个 API key
- 用户要求“只清除某一把 key 写入的记忆”

### 11.2 真正要补 `api_key_id` 元数据的写入点

不能只改一个地方。

当前至少需要覆盖这些向量元数据生成点：

1. `modules/memory/application/graph_service.py`
   - Event / Entity 的 TKG 向量条目都在这里构造 `MemoryEntry.metadata`

2. `modules/memory/domain/dialog_tkg_vector_index_v1.py`
   - 对话 utterance index 的 metadata 也在这里生成

3. `modules/memory/session_write.py`
   - session marker
   - fact entries
   - 写入前 metadata 收口逻辑

推荐做法：

- 新增统一 helper，例如 `_inject_api_key_metadata(metadata, api_key_id)`
- 避免每个调用点自己拼字段，减少漏改

### 11.3 API key 来源

推荐读取顺序：

1. JWT claim：`sid` 或约定好的 `api_key_id`
2. Header：`X-API-Key-Id`
3. Header：`X-Principal-ApiKey-Id`
4. fallback：`ctx.subject`

这样做的好处：

- 兼容未来新 JWT 合同
- 不打断当前 `sub=api_key_id` 的既有链路

### 11.4 Qdrant / Milvus 过滤条件

Phase 2 时向量删除条件应变成：

- tenant_id 必须存在
- api_key_id 作为 tenant 内进一步收窄

即：

- Qdrant：`metadata.tenant_id + metadata.api_key_id`
- Milvus：`tenant_id + api_key_id`

tenant 条件必须始终保留，避免错误的 key id 造成跨租户影响。

### 11.5 历史数据策略

推荐不做历史回填，采用双模式：

- 新写入数据：有 `api_key_id`
- 历史数据：无 `api_key_id`

当调用 `scope="apikey"` 时：

- 删除有 `api_key_id` 且匹配的记录
- 对无 `api_key_id` 的历史记录给出 warning

例如：

```json
{
  "status": "completed",
  "warnings": [
    "124 legacy vector points do not carry api_key_id and were not removed"
  ]
}
```

---

## 12. 建议的测试矩阵

### 12.1 API / Auth

新增或扩展：

- `modules/memory/tests/unit/test_api_auth_security.py`
  - `memory.clear` scope 可访问
  - 仅 `memory.read` 不可访问
  - `confirm=false` 返回 dry run
  - `confirm=true` 且 `reason` 缺失时返回 400
  - `require_signature=True` 且缺签名时返回 401

- `modules/memory/tests/unit/test_api_scope_coverage.py`
  - 确保 `/memory/v1/clear` 有显式 scope 覆盖
  - 验证 `/memory/v1/clear` 不会被 `/memory/v1/` 的 `memory.read` 前缀规则误命中

### 12.2 向量层

建议新增：

- Qdrant：
  - `count_by_filter` / `delete_by_filter` 使用 `metadata.tenant_id`
  - 多 collection 汇总计数正确
  - Phase 2 时附加 `metadata.api_key_id`

- InMem：
  - tenant 过滤删除
  - tenant + api_key_id 过滤删除

- Milvus / Router：
  - 有路由场景时，clear 不会因为缺方法而报错

### 12.3 图层

建议新增：

- `purge_tenant` 分批删完所有 tenant 节点
- 不会删除其他 tenant

### 12.4 Job store

建议新增：

- SQLite `count_by_tenant` / `clear_by_tenant`
- PostgreSQL `count_by_tenant` / `clear_by_tenant`
- Phase 2 的 `count_by_apikey` / `clear_by_apikey`

### 12.5 关键安全与幂等场景

这一组是本次评审新增强调的重点：

- 跨租户安全测试
  - tenant_A clear 后，tenant_B 的数据完全不受影响
  - 三大存储都要验

- 空租户 clear
  - tenant 下无数据时返回 0
  - 不应报错

- 重复 clear 幂等性
  - 连续两次 clear 同一个 tenant
  - 第二次应返回 0

- clear 并发保护
  - 同 tenant 两次 clear 并发
  - 第二个请求应收到 `409 clear_in_progress` 或 `423 locked`

- clear 与 ingest 并发
  - 如果无写入闸门，文档声明残留是允许的
  - 如果实现了闸门，验证新写入被阻断

---

## 13. 推荐的实施顺序

### 13.1 第一阶段：Memory 侧先闭环

先在 `modules/memory` 内完成：

1. `count_by_filter` / `delete_by_filter`
2. `count_tenant_nodes` / `purge_tenant`
3. `count_by_tenant` / `clear_by_tenant`
4. `POST /memory/v1/clear`
5. `dry_run` / `partial_failure` / 审计
6. 单测与集成测试

这样做的好处：

- 不依赖网关先改完
- 可以先通过内部调用或测试桩验证行为

### 13.2 第二阶段：网关接入

网关侧再补：

1. 外部路由 `POST /api/v1/memory/v1/clear`
2. 转发头注入
3. 内部 JWT scope
4. 限频
5. 可选写入闸门

这里建议再次强调真实改动落点：

- `modules/saas_gateway/forward.py`
- `modules/saas_gateway/auth.py`

不要去找不存在的 `index.js`。

### 13.3 第三阶段：Phase 2 元数据写透

最后再做：

1. 写入路径补 `api_key_id`
2. `scope="apikey"` 路径
3. 历史数据 warning
4. Milvus schema / expr 扩展

不要把它和 Phase 1 混在同一批，否则联调面会显著变大。

---

## 14. 相对原始草案的关键修正

### 14.1 路由路径修正

原草案写的是：

- Memory：`/v1/clear`

更贴合当前代码的建议是：

- Memory：`/memory/v1/clear`

### 14.2 Qdrant filter 字段修正

原草案写的是：

- `tenant_id`

当前真实实现应使用：

- `metadata.tenant_id`

Phase 2 也应写成：

- `metadata.api_key_id`

### 14.3 Qdrant 删除范围修正

原草案默认像是在删单 collection。

当前真实实现必须考虑：

- `text / image / audio / clip_image / face` 多 collection

### 14.4 JWT claim 修正

原草案使用：

- `sub = accountId`
- `sid = apiKeyId`

但当前 Memory 代码默认把：

- `sub` 当成 `api_key_id`

所以实施前必须先定合同，不能直接照抄原方案。

### 14.5 Gateway 文件位置修正

原草案写的是：

- `index.js`

当前仓库实际可复用的是：

- `modules/saas_gateway/auth.py`
- `modules/saas_gateway/forward.py`

---

## 15. 推荐的最小可施工版本

如果只追求最快把 Phase 1 真正跑起来，建议最小切片是：

1. Memory 新增 `POST /memory/v1/clear`
2. `PATH_SCOPE_REQUIREMENTS` 正确加入 `memory.clear`
3. Qdrant 新增 `count_by_filter` / `delete_by_filter`
4. Neo4j 新增 `count_tenant_nodes` / `purge_tenant`
5. `AsyncIngestJobStore` 与 `PgIngestJobStore` 新增 `count_by_tenant` / `clear_by_tenant`
6. clear endpoint 支持 `dry_run`
7. clear endpoint 走 `require_signature=True`
8. clear endpoint 返回 `stores + warnings + status`
9. 网关转发 `X-API-Token + X-Tenant-ID + X-API-Key-Id + X-Request-ID`
10. 网关限频默认 `1/min + 5/hour`

Phase 2 再单独做：

1. `api_key_id` 写透到所有向量 metadata
2. `scope="apikey"`
3. 历史数据 warning
4. Milvus schema 扩展

这样风险最低，也最符合当前仓库的真实结构。
