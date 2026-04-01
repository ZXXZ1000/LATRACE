# Config Decision Log

## Policy

As of 2026-03-12:

- `modules/memory/config/memory.config.yaml` is the only formal default config.
- `modules/memory/config/runtime_overrides.json` is local runtime state and is not tracked.
- Experiment candidates must be recorded under `modules/memory/config/experiments/`.
- A candidate is promoted only after it beats the formal baseline on the target datasets
  without unacceptable latency regression and after repeated runs on stable ingest state.

## Promotion Criteria

1. The candidate must be expressed as a delta against `memory.config.yaml`.
2. The candidate must have a named experiment file under `config/experiments/`.
3. The candidate must show a measurable gain on the target benchmark set.
4. The candidate must be re-run on a fixed ingest state where retrieval-only A/B is fair.
5. If promoted, the delta is merged into `memory.config.yaml` and the experiment is marked
   as `promoted`.

## Formal Baseline

### 2026-03-12

- Baseline file:
  [2026-03-12_formal_baseline.yaml](/Users/zhaoxiang/工作/MOYAN/MOYAN_AGENT_INFRA/modules/memory/config/experiments/2026-03-12_formal_baseline.yaml)
- Decision:
  Promote the previously repo-carried runtime rerank values into `memory.config.yaml`
  and stop tracking `runtime_overrides.json`.
- Result:
  `rerank = {0.40, 0.50, 0.05, 0.05}`
  `lexical_hybrid.enabled = false`
  `qa = qwen-plus`
  `judge = gpt-4o-mini`

## Current Working Baseline

### 2026-03-13 Dialog V2 Knowledge 0.6

- Baseline file:
  [2026-03-13_dialog_v2_knowledge_0_6_working_baseline.yaml](/Users/zhaoxiang/工作/MOYAN/MOYAN_AGENT_INFRA/modules/memory/config/experiments/2026-03-13_dialog_v2_knowledge_0_6_working_baseline.yaml)
- Status:
  recorded as the current working baseline for outer-fusion tuning
- Decision:
  Temporarily hardcode `_DIALOG_V2_DEFAULT_WEIGHTS["knowledge"] = 0.6` in
  `modules/memory/retrieval.py` and treat that code-level change as the anchor baseline for
  the next tuning phase.
- Reason:
  On the fixed-state showcase run, the score improved from `15/19` to `19/19`. On the larger
  `conv-26` run with `topk=20`, the system reached `158/199` accuracy with
  `j_overall_binary = 0.8277`. This is strong enough to serve as the current search anchor,
  but not yet broad enough to be promoted into `memory.config.yaml`.
- Note:
  This is intentionally different from the formal config baseline. Until broader validation is
  complete, the formal source of truth remains `memory.config.yaml`, while this code-level
  working baseline is used for the next parameter search.

## Recorded Candidates

### 2026-03-12 Showcase BM25 Mid

- Candidate file:
  [2026-03-12_showcase_bm25_mid_top20_qwen_plus.yaml](/Users/zhaoxiang/工作/MOYAN/MOYAN_AGENT_INFRA/modules/memory/config/experiments/2026-03-12_showcase_bm25_mid_top20_qwen_plus.yaml)
- Status:
  recorded, not promoted
- Reason:
  It improved the showcase score from `13/19` to `14/19`, but the ingest path was still
  unstable across reruns. The gain is promising, but not yet clean enough to adopt as the
  single formal default.

### 2026-03-12 Showcase Lexical Toggle On Fixed State

- Candidate file:
  [2026-03-12_showcase_lexical_on_same_state.yaml](/Users/zhaoxiang/工作/MOYAN/MOYAN_AGENT_INFRA/modules/memory/config/experiments/2026-03-12_showcase_lexical_on_same_state.yaml)
- Status:
  recorded, not promoted
- Reason:
  This run used the exact same auto-generated tenant/user/session state from the baseline
  showcase run and only toggled `memory.search.lexical_hybrid.enabled` to `true`. The
  candidate stayed at `15/19`, and the wrong set remained `q08/q11/q12/q15`. This is the
  cleanest signal so far that lexical-first-stage alone is not enough to improve the current
  showcase state.
- Note:
  Candidate retrieval latency was much lower on the second pass, but this run reused an
  already warmed service state after the baseline pass. Until we explicitly control cache and
  cold/warm order, latency alone is not a promotion signal.

## Next Decision Gates

1. Use the working baseline `knowledge=0.6` as the starting point for outer-fusion tuning.
2. Search `knowledge x rrf_k` on `conv-26`, with `showcase_pack_v1` fixed-state as a
   regression guard.
3. Fine-tune `multi` only after a stable `knowledge x rrf_k` region appears.
4. Validate the winner on `conv-30` and additional held-out conversation samples.
5. Promote the winner into `memory.config.yaml` only after repeated isolated reruns.
