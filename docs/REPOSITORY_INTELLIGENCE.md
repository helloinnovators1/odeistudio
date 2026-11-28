# Repository intelligence

ODEI repository intelligence is project-scoped and reads from the newest active workspace snapshot. It does not crawl an arbitrary filesystem path or use a caller-supplied repository URL.

## Authorization and source

Every endpoint requires an authenticated principal, active organization membership, and owner or active project membership. The indexer selects the latest unexpired snapshot using both `organization_id` and `project_id`; it verifies the snapshot metadata again before reading the GridFS archive and checks the extracted manifest digest against the stored digest.

The snapshot ingestion and repository index filters are applied before source text is persisted. Index records are scoped by organization, project, and immutable revision ID. Each result includes file SHA-256, snapshot ID, and index revision for provenance.

## Endpoints

All routes are under `/api/v1/organizations/{organization_id}/projects/{project_id}/repository-index`.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | Read active index state and coverage metadata |
| POST | `/` | Build/publish an index from the latest workspace snapshot |
| GET | `/search?q=...` | Case-insensitive exact substring search (optional `case_sensitive=true`) or bounded regular-expression search (`regex=true`) |
| GET | `/symbols?name=...` | Find symbol definitions |
| GET | `/references?name=...` | Find cross-file identifier references |
| GET | `/dependency-graph` | Read import edges |
| POST | `/semantic-search` | Retrieve semantically similar code chunks |

Every retrieval verifies that the active index still references the newest unexpired project snapshot. If a newer snapshot arrives after indexing, search/symbol/reference/graph/semantic retrieval fails closed with `REPOSITORY_INDEX_STALE`; the index-state endpoint reports `stale: true`. Refresh rechecks the latest snapshot immediately before publishing to avoid publishing a superseded snapshot.\n\nIndex refresh requires JSON `{"cloud_embedding_consent": true}`. Semantic search requires `{"query": "...", "cloud_model_consent": true}`. These explicit confirmations are required before repository excerpts or the query are sent to the configured OpenAI embedding provider.

## Persistence and bounds

- MongoDB stores immutable index revisions for files, symbols, references, imports, chunks, and the active project revision pointer.
- New revision records are staged with the active-pointer update and success audit event in one MongoDB transaction. Failed/uncertain unpublished-revision cleanup checks the active pointer and removes orphan rows in a snapshot transaction, avoiding a read-then-delete race with an uncertain publish commit.
- Superseded revisions receive a one-hour retirement window for in-flight readers. All index documents expire no later than their source snapshot.
- Indexing is bounded to 5,000 files, 1 MiB per file, 64 MiB total extracted text, a 50 MiB archive, 500 embedding chunks, 25,000 symbols, 50,000 references, and 10,000 import edges.
- Unchanged file/chunk hashes reuse project-scoped embeddings. Index state reports when chunk or analysis limits truncated coverage.
- Exact and semantic retrieval return snippets rather than whole files. Raw source is not written to audit metadata.

## Analysis coverage

Python symbols and references use the Python AST. JavaScript and TypeScript definitions/imports use bounded lexical analysis; identifier references are heuristic and can include false positives. Import graph targets preserve module names and do not claim complete package resolution. Semantic ranking uses cosine similarity over the bounded stored embedding set, not a separately provisioned Atlas Vector Search index.

 
Regular-expression searches use a dedicated regex engine with a 20 ms per-line timeout, a 2 second request-wide budget, a 256-character expression limit, and explicit timeout/invalid-expression errors. Exact literal search remains the default. Search results retain file hash, index revision, and snapshot provenance.
