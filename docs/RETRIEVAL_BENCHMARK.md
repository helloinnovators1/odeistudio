# NEXUS repository retrieval benchmark

The evaluator is \`odei_api.services.retrieval_benchmark.run_retrieval_benchmark\`.
It evaluates rankings returned by a supplied retrieval callback; that callback must
invoke the same authenticated, tenant-scoped retrieval implementation used by NEXUS.
The evaluator does not call an embedding service, manufacture relevance labels, or
pretend a synthetic fixture represents a production repository.

## Label format

Each query contains a unique \`query_id\`, non-empty \`query\`, and non-empty
\`relevant_documents\` list. A chunk ID is \`relative/path#chunk_index\`, matching
the repository index's \`path\` and \`chunk_index\` fields. Path-only IDs are
supported for path-level retrievers. Labels must be created and reviewed by the
corpus owner.

## Metrics

The report includes macro-averaged and per-query Recall@k, Precision@k (denominator
is k), MRR@k, and binary nDCG@k. It records corpus ID, query-set version, embedding
model identifier, k, and query count. Store the exact labelled corpus, retrieval
configuration, and raw report together so results can be reproduced.

## Example

    report = run_retrieval_benchmark(
        labelled_queries,
        lambda query, limit: authorized_repository_search(
            organization_id=organization_id,
            project_id=project_id,
            query=query,
            limit=limit,
        ),
        corpus_id="customer-approved-repository-snapshot-2026-11",
        query_set_version="owner-labelled-v1",
        embedding_model="text-embedding-3-small",
        k=10,
    )

The tests use small synthetic examples only to verify metric calculations. A
production-quality #86 acceptance run still requires an owner-approved corpus
and independently reviewed relevance labels. Do not report fixture metrics as
representative retrieval quality.
