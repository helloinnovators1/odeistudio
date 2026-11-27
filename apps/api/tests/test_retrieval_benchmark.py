from __future__ import annotations

import pytest

from odei_api.services.retrieval_benchmark import (
    RetrievalBenchmarkError,
    run_retrieval_benchmark,
)


def test_benchmark_reports_recall_precision_mrr_and_ndcg_for_real_rankings():
    queries = [
        {
            "query_id": "q1",
            "query": "where is project authorization checked",
            "relevant_documents": ["services/projects.py#0", "services/project_access.py#1"],
        },
        {
            "query_id": "q2",
            "query": "how are snapshots retained",
            "relevant_documents": ["services/workspace_snapshot_store.py#2"],
        },
    ]
    results = {
        "where is project authorization checked": [
            {"path": "services/projects.py", "chunk_index": 0},
            {"path": "services/unrelated.py", "chunk_index": 3},
            {"path": "services/project_access.py", "chunk_index": 1},
        ],
        "how are snapshots retained": [
            {"path": "services/unrelated.py", "chunk_index": 1},
            {"path": "services/workspace_snapshot_store.py", "chunk_index": 2},
        ],
    }

    report = run_retrieval_benchmark(
        queries, lambda query, _k: results[query],
        corpus_id="owner-approved-corpus-v1",
        query_set_version="queries-2026-11-27-v1",
        embedding_model="text-embedding-3-small",
        k=3,
    )

    assert report["query_count"] == 2
    assert report["metrics"]["recall@3"] == pytest.approx(1.0)
    assert report["metrics"]["precision@3"] == pytest.approx(0.5)
    assert report["metrics"]["mrr@3"] == pytest.approx(0.75)
    assert report["metrics"]["ndcg@3"] < 1.0
    assert report["per_query"][0]["mrr@3"] == 1.0
    assert report["per_query"][1]["mrr@3"] == 0.5


def test_benchmark_deduplicates_ranked_documents_before_scoring():
    report = run_retrieval_benchmark(
        [{"query_id": "q", "query": "needle", "relevant_documents": ["src/a.py#0"]}],
        lambda _query, _k: [
            {"path": "src/no.py", "chunk_index": 0},
            {"path": "src/no.py", "chunk_index": 0},
            {"path": "src/a.py", "chunk_index": 0},
        ],
        corpus_id="fixture",
        query_set_version="fixture-v1",
        embedding_model="fixture-embedding",
        k=3,
    )
    assert report["metrics"]["mrr@3"] == pytest.approx(0.5)


@pytest.mark.parametrize("queries", [[], [{"query_id": "q", "query": "x", "relevant_documents": []}]])
def test_benchmark_rejects_missing_relevance_labels(queries):
    with pytest.raises(RetrievalBenchmarkError):
        run_retrieval_benchmark(
            queries, lambda _query, _k: [],
            corpus_id="fixture", query_set_version="v1",
            embedding_model="fixture",
        )


def test_benchmark_rejects_duplicate_query_ids_and_invalid_k():
    query = {"query_id": "q", "query": "needle", "relevant_documents": ["a"]}
    with pytest.raises(RetrievalBenchmarkError):
        run_retrieval_benchmark(
            [query, query], lambda _query, _k: [],
            corpus_id="fixture", query_set_version="v1",
            embedding_model="fixture",
        )
    with pytest.raises(RetrievalBenchmarkError):
        run_retrieval_benchmark(
            [query], lambda _query, _k: [],
            corpus_id="fixture", query_set_version="v1",
            embedding_model="fixture", k=0,
        )
