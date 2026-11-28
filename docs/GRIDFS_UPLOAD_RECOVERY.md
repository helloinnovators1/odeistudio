# GridFS upload intents and crash recovery

ODEI snapshot archives and execution stdout/stderr are stored in GridFS. GridFS
file writes are not part of MongoDB multi-document transactions, so the API
must not assume that a metadata transaction can roll back a blob upload.

## Upload protocol

1. Create a tenant-scoped `gridfs_upload_intents` record in a MongoDB
   transaction that calls `fence_project_write`.
2. Persist a unique GridFS file ID for every target bucket in that intent
   before opening any upload stream.
3. Revalidate and renew the unexpired lease immediately before opening a stream, then upload through `open_upload_stream_with_id`. Each completed GridFS file
   includes `metadata.upload_intent_id`. A heartbeat renews the intent lease;
   the upload is cancelled if the lease is lost.
4. In one MongoDB transaction, fence the project again, insert the resource
   metadata, and transition the intent from `uploading` to `committed`.
   This transaction is the publication boundary. GridFS operations themselves
   are deliberately outside transactions.
5. On API startup and periodically, the snapshot and artifact retention
   workers reconcile only their own `resource_type`.

## Recovery rules

- An unexpired `uploading` intent is owned by its uploader and is not touched.
- An expired `uploading` intent is atomically claimed as `deleting` only
  after the lease expiry grace period.
- A `deleting` intent is a durable tombstone and is deliberately retained
  after a successful cleanup pass. Its preallocated file IDs allow cleanup of
  both completed `.files` documents and orphan `.chunks` records left by a
  process crash before GridFS finalized the file.
- Reconciliation repeats cleanup for retained tombstones, rotating bounded
  batches by the oldest cleanup timestamp. This covers a process that was
  paused beyond its lease, resumed after an earlier cleanup pass, and wrote
  additional chunks under its original file IDs. Tombstones must not be
  garbage-collected merely because one cleanup pass found no remaining blobs.
  They are currently retained indefinitely, so their count and oldest
  `last_cleanup_at` must be monitored. This creates unbounded metadata growth
  until a stronger late-writer exclusion mechanism is implemented; adding a
  TTL index or time-based tombstone purge would be unsafe.
- A `committed` intent is never used to delete blobs. Its intent record is
  removed after the committed-intent retention period.
- A partial cleanup leaves the intent in `deleting`; the next worker pass
  repeats the idempotent file/chunk cleanup. Successful passes also retain
  the tombstone and update its cleanup timestamp/pass count.
- Intent creation and publication both use the project write fence. A project
  entering deletion cannot admit a new upload or publish an upload that lost
  its lease.

## Operational constraints

- The upload lease is five minutes. It is renewed before stream creation and every 30 seconds while the upload remains active.
- Expired uploads receive a further two-minute reconciliation grace period.
- Reconciliation is bounded to at most 1,000 intents per pass.
- Snapshot and artifact workers filter by resource type so neither worker
  attempts to clean the other's GridFS buckets.
- The GridFS upload stream is never opened inside a MongoDB transaction;
  PyMongo documents that GridFS bucket operations are not supported inside
  multi-document transactions.

## Remaining lifecycle work

This protocol closes the known upload-before-metadata process-crash window for
these two GridFS resource types, subject to successful deployment and
replica-set fault-injection validation. It does not implement complete project
deletion. A future deletion coordinator must block new intents, wait for
in-flight upload leases to finish or expire, and drain all remaining project
writers and workers before deleting project resources.
