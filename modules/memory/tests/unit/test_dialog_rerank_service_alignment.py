from __future__ import annotations

import benchmark.shared.adapters.rerank_service as bench_service
from benchmark.shared.adapters.rerank_types import EvidenceType as BenchEvidenceType
from benchmark.shared.adapters.rerank_types import RetrievalCandidate as BenchCandidate
from benchmark.shared.adapters.rerank_types import RerankConfig as BenchConfig

from modules.memory.application.rerank_dialog_v1 import (
    EvidenceType,
    RetrievalCandidate,
    RerankConfig,
    build_llm_client_from_fn,
    create_rerank_service,
)


def test_dialog_rerank_service_matches_benchmark_scores_and_ranks() -> None:
    def _llm(system_prompt: str, user_prompt: str) -> str:
        # passage 2 should win
        return '{"1": 0.1, "2": 0.9, "3": 0.2}'

    # benchmark
    bench_llm = type("LLM", (), {"generate": staticmethod(_llm)})
    bench_cfg = BenchConfig(enabled=True, model="llm", top_n=2)
    bench_candidates = [
        BenchCandidate(query_text="q", evidence_text="a", evidence_type=BenchEvidenceType.FACT, event_id="e1", base_score=2.0),
        BenchCandidate(query_text="q", evidence_text="b", evidence_type=BenchEvidenceType.EVENT, event_id="e2", base_score=1.0),
        BenchCandidate(query_text="q", evidence_text="c", evidence_type=BenchEvidenceType.REFERENCE, event_id="e3", base_score=0.5),
    ]
    bench = bench_service.create_rerank_service(bench_cfg, llm_client=bench_llm)
    bench_results = bench.rerank("q", bench_candidates)

    # ours
    ours_cfg = RerankConfig(enabled=True, model="llm", top_n=2)
    ours_candidates = [
        RetrievalCandidate(query_text="q", evidence_text="a", evidence_type=EvidenceType.FACT, event_id="e1", base_score=2.0),
        RetrievalCandidate(query_text="q", evidence_text="b", evidence_type=EvidenceType.EVENT, event_id="e2", base_score=1.0),
        RetrievalCandidate(query_text="q", evidence_text="c", evidence_type=EvidenceType.REFERENCE, event_id="e3", base_score=0.5),
    ]
    ours = create_rerank_service(ours_cfg, llm_client=build_llm_client_from_fn(_llm))
    ours_results = ours.rerank("q", ours_candidates)

    assert [r.candidate.event_id for r in ours_results] == [r.candidate.event_id for r in bench_results]
    for a, b in zip(ours_results, bench_results, strict=True):
        assert a.rank == b.rank
        assert abs(a.rerank_score - b.rerank_score) < 1e-9
        assert abs(a.final_score - b.final_score) < 1e-9
