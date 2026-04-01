# Phase 5 评估计划（语义 API 质量与覆盖率）

## 1. 目标
- 给 Phase 4 语义 API 建立可执行、可复现的质量门槛。
- 用数据验证“硬过滤 + 低污染”的设计是否成立。
- 为 Phase 6 上线提供 Go/No-Go 依据。

## 2. 评估范围
**语义 API**：
- `/memory/v1/topic-timeline`
- `/memory/v1/entity-profile`
- `/memory/v1/quotes`
- `/memory/v1/relations`
- `/memory/v1/time-since`

**覆盖率指标**（结构化字段）：
- `topic_path_coverage`
- `tags_coverage`
- `keywords_coverage`
- `_uncategorized_ratio`

## 3. 指标定义与门槛（建议）

### 3.1 覆盖率
| 指标 | 定义 | 门槛 |
| --- | --- | --- |
| topic_path_coverage | 事件中有 topic_path 的占比（事件口径） | ≥ 0.60 |
| tags_coverage | 事件中有 tags 的占比 | ≥ 0.60 |
| keywords_coverage | 事件中有 keywords 的占比 | ≥ 0.70 |
| _uncategorized_ratio | 落入 _uncategorized 的占比 | ≤ 0.30 |

### 3.2 语义 API
| API | 关键指标 | 门槛 |
| --- | --- | --- |
| topic-timeline | precision@k, order_consistency | ≥ 0.70, ≥ 0.95 |
| entity-profile | facts_precision, relations_precision | ≥ 0.70 |
| quotes | quote_relevance, speaker_precision | ≥ 0.70, ≥ 0.80 |
| relations | precision@k | ≥ 0.70 |
| time-since | last_mentioned_abs_err_days | ≤ 3 days |

> 说明：门槛为 Phase 5 建议值，可根据数据集规模与业务容忍度调整。

## 4. 数据集格式（JSONL）

统一要求：每行一个样本，必须带 `query_id`。

### 4.1 topic-timeline
```json
{"query_id":"tt-001","topic":"日本旅行","user_tokens":["u:1"],"expected_event_ids":["evt-1","evt-2"],"expected_order":["evt-1","evt-2"],"time_range":{"start":"2024-01-01"}}
```

### 4.2 entity-profile
```json
{"query_id":"ep-001","entity":"Alice","expected_facts":["Alice likes apples"],"expected_relations":["Bob"],"expected_recent_event_ids":["evt-3"]}
```

### 4.3 quotes
```json
{"query_id":"qt-001","entity":"Alice","expected_quotes":[{"utterance_id":"utt-1","speaker_id":"ent-1"}]}
```

### 4.4 relations
```json
{"query_id":"rel-001","entity":"Alice","expected_related_entities":["ent-2","ent-3"]}
```

### 4.5 time-since
```json
{"query_id":"ts-001","topic":"日本旅行","expected_last_mentioned":"2026-01-20T00:00:00Z"}
```

## 5. 脚本与运行方式

位置：`modules/memory/scripts/phase5/`

示例：
```bash
PYTHONPATH=. python modules/memory/scripts/phase5/eval_topic_timeline.py \
  --input modules/memory/data/phase5/ground_truth/topic_timeline.jsonl \
  --base-url http://127.0.0.1:8000 \
  --tenant-id t1 \
  --output modules/memory/outputs/phase5/topic_timeline_report.json
```

## 6. DoD（完成标准）
- 文档齐全：本计划 + 指标口径 + 样本格式
- 评估脚本可运行（输入/输出规范稳定）
- 生成基线报告（JSON）
- 指标满足门槛才允许进入 Phase 6

