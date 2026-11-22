from __future__ import annotations

import asyncio
import io
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from odei_api.execution_worker import ExecutionWorker
from odei_api.services.execution_runs import ExecutionRun, ExecutionRunStatus
from odei_api.services.execution_sandbox import SandboxResult
from odei_api.services.workspace_snapshots import WorkspaceSnapshotIngestor


def make_archive():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("README.md", b"workspace")
    return stream.getvalue()


class Runs:
    def __init__(self, run):
        self.run = run
        self.available = run
        self.finished = None

    async def claim_next(self, **_kwargs):
        run, self.available = self.available, None
        return run

    async def mark_running(self, **_kwargs):
        return None

    async def mark_collecting(self, **_kwargs):
        pass

    async def heartbeat(self, **_kwargs):
        return datetime.now(timezone.utc)

    async def get(self, **_kwargs):
        return self.run

    async def finish(self, **kwargs):
        self.finished = kwargs
        return self.run


class Snapshots:
    def __init__(self, metadata, archive):
        self.metadata = metadata
        self.archive = archive

    async def get_archive_for_worker(self, **_kwargs):
        return self.metadata, self.archive


class Artifacts:
    def __init__(self):
        self.values = None

    async def put(self, **values):
        self.values = values
        return {"run_id": values["run_id"]}


class Registry:
    def get(self, profile_id):
        assert profile_id == "python-tests"
        return object()


class Sandbox:
    async def run(self, profile, workspace, *, arguments):
        assert Path(workspace, "README.md").read_bytes() == b"workspace"
        assert arguments == ()
        return SandboxResult(
            exit_code=0, stdout="passed", stderr="", duration_ms=10,
            timed_out=False, stdout_truncated=False, stderr_truncated=False,
        )


def make_run(digest, *, snapshot_id="snapshot-1"):
    return ExecutionRun(
        id="run-1", organization_id="org-1", project_id="project-1",
        task_id="task-1", requester_issuer="https://identity.example/",
        requester_subject="owner", profile_id="python-tests",
        snapshot_sha256=digest, snapshot_id=snapshot_id, arguments=(),
        status=ExecutionRunStatus.LEASED, version=1, attempts=1,
        worker_id="worker-test", lease_token="a" * 32,
        lease_expires_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_worker_verifies_snapshot_runs_sandbox_and_persists_result(tmp_path):
    archive = make_archive()
    digest_root = tmp_path / "digest"
    digest_root.mkdir()
    digest = WorkspaceSnapshotIngestor(digest_root).ingest(archive).sha256
    for child in digest_root.iterdir():
        if child.is_dir():
            import shutil
            shutil.rmtree(child)
    workspace_root = tmp_path / "worker"
    workspace_root.mkdir()
    run = make_run(digest)
    runs, artifacts = Runs(run), Artifacts()
    worker = ExecutionWorker(
        worker_id="worker-test", runs=runs,
        snapshots=Snapshots({
            "organization_id": "org-1", "project_id": "project-1",
            "task_id": "task-1", "sha256": digest,
        }, archive),
        artifacts=artifacts, registry=Registry(), sandbox=Sandbox(),
        workspace_root=workspace_root, tasks=object(), task_events=object(),
    )
    assert await worker.run_once() is True
    assert runs.finished["outcome"] is ExecutionRunStatus.COMPLETED
    assert runs.finished["tasks"] is worker.tasks
    assert artifacts.values["stdout"] == "passed"
    assert list(workspace_root.iterdir()) == []


@pytest.mark.asyncio
async def test_worker_fails_closed_when_snapshot_digest_does_not_match(tmp_path):
    archive = make_archive()
    workspace_root = tmp_path / "worker"
    workspace_root.mkdir()
    run = make_run("0" * 64)
    runs, artifacts = Runs(run), Artifacts()
    worker = ExecutionWorker(
        worker_id="worker-test", runs=runs,
        snapshots=Snapshots({
            "organization_id": "org-1", "project_id": "project-1",
            "task_id": "task-1", "sha256": "0" * 64,
        }, archive),
        artifacts=artifacts, registry=Registry(), sandbox=Sandbox(),
        workspace_root=workspace_root, tasks=object(), task_events=object(),
    )
    assert await worker.run_once() is True
    assert runs.finished["outcome"] is ExecutionRunStatus.FAILED
    assert artifacts.values is None
    assert list(workspace_root.iterdir()) == []
