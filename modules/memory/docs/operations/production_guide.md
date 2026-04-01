# 记忆模块最小运维指南（内部 / 非 SaaS）

目的：在不引入容器化和重监控的前提下，给出可执行的最小运维清单，确保“真实嵌入 + 真实后端”跑通与基本可维护性。

## 1. 真实嵌入启用

- 图像（CLIP/OpenCLIP）
  - 安装（任选其一）：
    - 基础：`pip install open_clip_torch torch Pillow`
    - 使用 extras（推荐）：`pip install -e .[multimodal]`
  - 配置（`modules/memory/config/memory.config.yaml`）
    ```yaml
    memory:
      vector_store:
        embedding:
          image:
            provider: clip
            model: ViT-B-32
            dim: 512
    ```
  - 行为：
    - 写入：若 `MemoryEntry.vectors.image` 已有值，优先使用；否则从 `contents[0]` 检测 dataURL/base64 → 走图像编码；否则走文本编码（查询场景）。
    - 查询：`search_vectors()` 对 image 模态会将 query 视为文本，走文本编码器以实现 text→image 检索。

- 音频（ERes2NetV2）
  - 依赖（任选其一）：
    - 基础：`pip install torchaudio torch pydub speakerlab`
    - 使用 extras（推荐）：`pip install -e .[voice]`
  - 权重：将 `pretrained_eres2netv2w24s4ep4.ckpt` 放入 `modules/memorization_agent/ops/models/` 并修正 `voice_processing.py` 中路径（默认 `models/pretrained_eres2netv2w24s4ep4.ckpt`）。
  - 配置：`memory.config.yaml` 中 `embedding.audio.dim: 192`（已对齐）。
  - 说明：权重放置与依赖说明详见 `modules/memorization_agent/ops/README.weights.md`。

## 2. 后端与维度对齐

- Qdrant：
  - 集合建议：`memory_text(1536)`, `memory_image(512)`, `memory_audio(192)`，距离度量 `cosine`。
  - 若先写入再建集合，需确保集合维度与配置一致，否则 upsert 可能失败。
- Neo4j：
  - 建议提前执行脚本 `modules/memory/scripts/create_neo4j_indexes.py`（若已完善）以创建基本约束。

## 3. 健康与指标

- Memory API：
  - `GET /health` 返回向量/图后端健康信息；
  - `GET /metrics_prom` 返回基础指标（可被 Prometheus 抓取）。

## 4. 常见问题排查

- 向量维度不一致：
  - 现象：Qdrant upsert 400/422。
  - 检查：确认 `memory.config.yaml` 中 dim 与集合实际维度一致；音频已改为 192。
- CLIP 模型不可用：
  - 现象：编码回退（指标可能缺失），检索效果下降。
  - 检查：是否安装 `open_clip_torch/torch/Pillow`，网络可下载权重（或本地缓存）。
- ERes2Net 权重缺失：
  - 现象：音频嵌入失败或回退；
  - 处理：确认权重路径与权限，GPU 可用性（可先用 CPU 验证）。

## 5. 运行建议（内部阶段）

- 采样日志：先保持关闭，仅在问题诊断时按 1% 开启；
- 批处理写入：初期不建议，便于定位问题；
- 关系白名单：已内置（appears_in/said_by/located_in/equivalence/prefer/executed/describes/temporal_next/co_occurs）。

---

如需进一步自动化（Compose/K8s/监控看板），待系统整体稳定后再推进。
