# Safe Workspace Snapshot Ingestion

This module accepts a bounded ZIP byte stream and extracts it into a fresh, random direct child of a worker-owned workspace root. It never calls ZIP extractall and never trusts archive paths.

Controls include compressed archive size, entry count, per-file and aggregate expanded size, compression ratio, supported compression methods, encrypted-entry rejection, normalized case-insensitive duplicate rejection, Windows-reserved path rejection, path traversal and absolute-path rejection, symlink/special-file rejection, file/directory prefix conflict detection, known credential-path exclusions (.env files other than safe templates, VCS/SSH/cloud credential directories, private-key and registry credential files), exclusive file creation, no-follow final file opens where supported, content hashing, and cleanup on failure.

The resulting digest is a deterministic manifest digest over sorted normalized relative paths, file sizes and per-file SHA-256 hashes. It is not a digest of the raw ZIP container.

This module is not yet wired to an authenticated upload route or object store. The caller must enforce explicit user consent, tenant/project authorization, approved workspace version and retention policy. The worker root must be private to the worker process. The snapshot is an input to a disposable sandbox, not a writable path on the user's local machine.


## Durable API storage

The authenticated execution API now validates the archive before storing its original bytes in MongoDB GridFS. Tenant-scoped metadata records the content-manifest digest and expiry. Metadata is not TTL-deleted independently of its GridFS blob; scheduled cleanup must remove expired blobs and preserve snapshots still referenced by active runs. See EXECUTION_API.md.
