"""Reproducible offline evaluation for NEXUS repository retrieval."""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from math import log2
from typing import Any


class RetrievalBenchmarkError(ValueError):
    """The labelled benchmark dataset or retrieval output is invalid."""


def _document_id(item: Mapping[str, Any]) -> str:
    explicit = item.get("document_id")
    if isinstance(explicit, str) and explicit.strip():
        return explicit
    path = item.get("path")
    if not isinstance(path, str) or not path.strip():
        raise RetrievalBenchmarkError("retrieval results require document_id or path")
    chunk_index = item.get("chunk_index")
    if chunk_index is None:
        return path
    if isinstance(chunk_index, bool) or not isinstance(chunk_index, int) or chunk_index < 0:
        raise RetrievalBenchmarkError("chunk_index must be a non-negative integer")
    return f"{path}#{chunk_index}"


def _validate_queries(queries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(queries, (str, bytes)) or not isinstance(queries, Sequence) or not queries:
        raise RetrievalBenchmarkError("benchmark must contain at least one labelled query")
    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in queries:
        if not isinstance(row, Mapping):
            raise RetrievalBenchmarkError("each benchmark query must be an object")
        query_id, query = row.get("query_id"), row.get("query")
        relevant = row.get("relevant_documents")
        if not isinstance(query_id, str) or not query_id.strip() or query_id in seen:
            raise RetrievalBenchmarkError("query_id values must be non-empty and unique")
        if not isinstance(query, str) or not query.strip():
            raise RetrievalBenchmarkError("query text must be non-empty")
        if (not isinstance(relevant, Sequence) or isinstance(relevant, (str, bytes))
                or not relevant or any(not isinstance(item, str) or not item.strip() for item in relevant)):
            raise RetrievalBenchmarkError("each query needs non-empty relevant_documents labels")
        if len(set(relevant)) != len(relevant):
            raise RetrievalBenchmarkError("relevant_documents labels must be unique")
        seen.add(query_id)
        validated.append({
            "query_id": query_id,
            "query": query,
            "relevant_documents": set(relevant),
        })
    return validated


def run_retrieval_benchmark(
    queries: Sequence[Mapping[str, Any]],
    search: Callable[[str, int], Sequence[Mapping[str, Any]]],
    *,
    corpus_id: str,
    query_set_version: str,
    embedding_model: str,
    k: int = 10,
) -> dict[str, Any]:
    """Run labelled queries and report macro Recall, Precision, MRR and nDCG@k."""
    if isinstance(k, bool) or not isinstance(k, int) or not 1 <= k <= 100:
        raise RetrievalBenchmarkError("k must be between 1 and 100")
    for name, value in (
        ("corpus_id", corpus_id),
        ("query_set_version", query_set_version),
        ("embedding_model", embedding_model),
    ):
        if not isinstance(value, str) or not value.strip() or len(value) > 256:
            raise RetrievalBenchmarkError(f"{name} must be a non-empty bounded string")
    labelled = _validate_queries(queries)
    per_query: list[dict[str, Any]] = []
    for row in labelled:
        raw_hits = search(row["query"], k)
        if not isinstance(raw_hits, Sequence) or isinstance(raw_hits, (str, bytes)):
            raise RetrievalBenchmarkError("retrieval callback must return a sequence of result objects")
        ranked: list[str] = []
        for hit in raw_hits:
            if not isinstance(hit, Mapping):
                raise RetrievalBenchmarkError("retrieval results must be objects")
            key = _document_id(hit)
            if key not in ranked:
                ranked.append(key)
            if len(ranked) == k:
                break
        relevant: set[str] = row["relevant_documents"]
        top = ranked[:k]
        found = [index for index, key in enumerate(top, start=1) if key in relevant]
        recall = len(found) / len(relevant)
        precision = len(found) / k
        reciprocal_rank = 1 / found[0] if found else 0.0
        dcg = sum(1 / log2(rank + 1) for rank in found)
        ideal_count = min(len(relevant), k)
        ideal_dcg = sum(1 / log2(rank + 1) for rank in range(1, ideal_count + 1))
        ndcg = dcg / ideal_dcg if ideal_dcg else 0.0
        per_query.append({
            "query_id": row["query_id"],
            f"recall@{k}": recall,
            f"precision@{k}": precision,
            f"mrr@{k}": reciprocal_rank,
            f"ndcg@{k}": ndcg,
            "relevant_count": len(relevant),
            "retrieved_count": len(top),
        })
    count = len(per_query)
    metric_names = (f"recall@{k}", f"precision@{k}", f"mrr@{k}", f"ndcg@{k}")
    return {
        "schema_version": 1,
        "corpus_id": corpus_id,
        "query_set_version": query_set_version,
        "embedding_model": embedding_model,
        "k": k,
        "query_count": count,
        "metrics": {
            name: sum(item[name] for item in per_query) / count
            for name in metric_names
        },
        "per_query": per_query,
    }
