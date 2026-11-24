import pytest

from odei_api.services.parallel_jobs import (
    GitWorktreeManager,
    MongoParallelJobStore,
    ParallelJobConflict,
)


class Result:
    def __init__(self, modified_count=1):
        self.modified_count = modified_count


class Cursor:
    def __init__(self, rows):
        self.rows = rows
    def sort(self, *_):
        return self
    def limit(self, _):
        return self
    async def to_list(self, length=None):
        return self.rows[:length]


class Collection:
    def __init__(self):
        self.rows = {}
        self.events = []
    async def create_index(self, *_args, **_kwargs):
        return None
    async def insert_one(self, row):
        self.rows[row.get("_id", row.get("job_id"))] = dict(row)
        self.events.append(dict(row))
    async def insert_many(self, rows, ordered=True):
        for row in rows:
            self.rows[row["_id"]] = dict(row)
    async def delete_one(self, query):
        self.rows.pop(query["_id"], None)
    def find(self, query):
        rows = list(self.rows.values())
        for key, value in query.items():
            if isinstance(value, dict) and "$lte" in value:
                rows = [r for r in rows if r.get(key) and r[key] <= value["$lte"]]
            elif isinstance(value, dict) and "$in" in value:
                rows = [r for r in rows if r.get(key) in value["$in"]]
            elif isinstance(value, dict) and "$gt" in value:
                rows = [r for r in rows if r.get(key) and r[key] > value["$gt"]]
            elif value is not None and not isinstance(value, dict):
                rows = [r for r in rows if (value in r.get(key, []) if isinstance(r.get(key), list) else r.get(key) == value)]
        return Cursor(rows)
    async def find_one(self, query):
        rows = await self.find(query).to_list(100)
        return rows[0] if rows else None
    async def find_one_and_update(self, query, update, return_document=None):
        row = await self.find_one(query)
        if row is None:
            return None
        row.update(update.get("$set", {}))
        for key, amount in update.get("$inc", {}).items():
            row[key] = row.get(key, 0) + amount
        return row
    async def update_one(self, query, update):
        row = await self.find_one(query)
        if row is None:
            return Result(0)
        row.update(update.get("$set", {}))
        for key, amount in update.get("$inc", {}).items():
            row[key] = row.get(key, 0) + amount
        return Result()
    async def update_many(self, query, update):
        rows = await self.find(query).to_list(1000)
        for row in rows:
            row.update(update.get("$set", {}))
            for key, amount in update.get("$inc", {}).items():
                row[key] = row.get(key, 0) + amount
        return Result(len(rows))


@pytest.mark.asyncio
async def test_parallel_jobs_claim_checkpoint_and_resume_with_lease():
    jobs, groups, events = Collection(), Collection(), Collection()
    store = MongoParallelJobStore(jobs, groups, events)
    await store.initialize()
    await store.create_group(
        organization_id="org", project_id="project", group_id="group",
        jobs=[{"job_id": "one"}, {"job_id": "two", "depends_on": ["one"]}],
    )
    claimed = await store.claim_next(worker_id="worker-a")
    assert claimed.id == "one" and claimed.attempt == 1
    saved = await store.checkpoint(
        organization_id="org", job_id="one", worker_id="worker-a",
        lease_token=claimed.lease_token, expected_version=claimed.version,
        checkpoint={"step": 2, "cursor": "abc"},
    )
    assert saved.checkpoint_sha256
    done = await store.finish(
        organization_id="org", job_id="one", worker_id="worker-a",
        lease_token=claimed.lease_token, expected_version=saved.version, outcome="completed",
    )
    assert done.status == "completed"
    next_job = await store.claim_next(worker_id="worker-b")
    assert next_job.id == "two"


@pytest.mark.asyncio
async def test_checkpoint_rejects_stale_lease_and_bounds_payload():
    jobs, groups, events = Collection(), Collection(), Collection()
    store = MongoParallelJobStore(jobs, groups, events)
    await store.create_group(
        organization_id="org", project_id="project", group_id="g",
        jobs=[{"job_id": "job"}],
    )
    job = await store.claim_next(worker_id="worker")
    with pytest.raises(ParallelJobConflict):
        await store.checkpoint(
            organization_id="org", job_id="job", worker_id="other",
            lease_token=job.lease_token, expected_version=job.version,
            checkpoint={"step": 1},
        )
    with pytest.raises(ValueError, match="size limit"):
        await store.checkpoint(
            organization_id="org", job_id="job", worker_id="worker",
            lease_token=job.lease_token, expected_version=job.version,
            checkpoint={"data": "x" * 300_000},
        )


@pytest.mark.asyncio
async def test_dependency_cycles_and_unknown_dependencies_are_rejected():
    store = MongoParallelJobStore(Collection(), Collection(), Collection())
    with pytest.raises(ValueError, match="dependencies"):
        await store.create_group(
            organization_id="org", project_id="project", group_id="g",
            jobs=[{"job_id": "a", "depends_on": ["b"]}],
        )
    with pytest.raises(ValueError, match="cycle"):
        await store.create_group(
            organization_id="org", project_id="project", group_id="g",
            jobs=[{"job_id": "a", "depends_on": ["b"]}, {"job_id": "b", "depends_on": ["a"]}],
        )


def test_worktree_manager_requires_safe_repository_and_base_commit(tmp_path):
    import subprocess
    repository = tmp_path / "repo"
    root = tmp_path / "worktrees"
    repository.mkdir()
    root.mkdir()
    subprocess.run(["git", "init", str(repository)], check=True, capture_output=True)
    (repository / "README.md").write_text("hello", encoding="utf-8")
    subprocess.run(["git", "-C", str(repository), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repository), "-c", "user.name=Test", "-c",
         "user.email=test@example.com", "commit", "-m", "init"],
        check=True, capture_output=True,
    )
    commit = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"], text=True).strip()
    manager = GitWorktreeManager(repository, root)
    worktree = manager.create(job_id="job-1", base_commit=commit)
    assert (worktree / "README.md").read_text(encoding="utf-8") == "hello"
    manager.remove(worktree)
    with pytest.raises(ValueError):
        manager.create(job_id="../escape", base_commit=commit)

@pytest.mark.asyncio
async def test_worker_can_renew_only_its_current_lease():
    jobs, groups, events = Collection(), Collection(), Collection()
    store = MongoParallelJobStore(jobs, groups, events)
    await store.create_group(
        organization_id="org", project_id="project", group_id="lease-group",
        jobs=[{"job_id": "lease-job"}],
    )
    job = await store.claim_next(worker_id="worker-a")
    await store.heartbeat(
        organization_id="org", job_id=job.id, worker_id="worker-a",
        lease_token=job.lease_token, lease_seconds=90,
    )
    with pytest.raises(ParallelJobConflict):
        await store.heartbeat(
            organization_id="org", job_id=job.id, worker_id="worker-b",
            lease_token=job.lease_token, lease_seconds=90,
        )
