import pytest

from odei_api.services.mac_environments import (
    MacEnvironmentConflict,
    MacEnvironmentError,
    MacEnvironmentNotFound,
    MongoMacEnvironmentStore,
    validate_environment_config,
)


class Result:
    def __init__(self, count): self.modified_count = count


class Collection:
    def __init__(self): self.record = None
    async def create_index(self, *_a, **_k): pass
    async def insert_one(self, doc, session=None):
        if self.record is not None:
            from pymongo.errors import DuplicateKeyError
            raise DuplicateKeyError("duplicate")
        self.record = doc
    async def find_one(self, query, session=None):
        return self.record if self.record and self.record["_id"] == query["_id"] else None
    async def update_one(self, query, update, session=None):
        record = self.record
        if not record or record["_id"] != query["_id"]:
            return Result(0)
        if "latest_version" in query and record["latest_version"] != query["latest_version"]:
            return Result(0)
        if "active_version" in query and record["active_version"] != query["active_version"]:
            return Result(0)
        selector = query.get("versions", {}).get("$elemMatch", {})
        revision = next((r for r in record["versions"] if all(
            (r.get(k) != v["$ne"] if isinstance(v, dict) and "$ne" in v else r.get(k) == v)
            for k, v in selector.items()
        )), None)
        if selector and revision is None:
            return Result(0)
        for key, value in update.get("$set", {}).items():
            if key.startswith("versions.$."):
                revision[key[len("versions.$."):]] = value
            else:
                record[key] = value
        if "$push" in update:
            record["versions"].append(update["$push"]["versions"])
        return Result(1)


@pytest.mark.asyncio
async def test_environment_requires_author_distinct_approval_and_compare_and_set_promotion():
    store = MongoMacEnvironmentStore(Collection())
    await store.initialize()
    draft = await store.create_draft(
        environment="staging", actor="author-1",
        config={"region": "eu-west-1", "replicas": 2},
        change_summary="Initial staging configuration",
    )
    assert draft["status"] == "draft"
    with pytest.raises(MacEnvironmentConflict):
        await store.submit_for_approval(
            environment="staging", version=1, expected_latest_version=1, actor="other",
        )
    await store.submit_for_approval(
        environment="staging", version=1, expected_latest_version=1, actor="author-1",
    )
    with pytest.raises(MacEnvironmentError):
        await store.approve(
            environment="staging", version=1, expected_latest_version=1, actor="author-1",
        )
    await store.approve(
        environment="staging", version=1, expected_latest_version=1, actor="reviewer-1",
    )
    with pytest.raises(MacEnvironmentConflict):
        await store.promote(
            environment="staging", version=1, expected_active_version=2,
            expected_latest_version=1, actor="deployer-1",
        )
    promoted = await store.promote(
        environment="staging", version=1, expected_active_version=0,
        expected_latest_version=1, actor="deployer-1",
    )
    assert promoted["active_version"] == 1
    assert promoted["versions"][0]["status"] == "promoted"


@pytest.mark.asyncio
async def test_rollback_creates_new_reviewable_revision_without_mutating_history():
    store = MongoMacEnvironmentStore(Collection())
    await store.create_draft(
        environment="production", actor="author-1",
        config={"replicas": 3}, change_summary="Initial",
    )
    await store.submit_for_approval(
        environment="production", version=1, expected_latest_version=1, actor="author-1",
    )
    await store.approve(
        environment="production", version=1, expected_latest_version=1, actor="reviewer-1",
    )
    await store.promote(
        environment="production", version=1, expected_active_version=0,
        expected_latest_version=1, actor="deployer-1",
    )
    rollback = await store.create_rollback_draft(
        environment="production", target_version=1, expected_latest_version=1,
        actor="operator-2", change_summary="Restore known good config",
    )
    assert rollback["version"] == 2
    assert rollback["rollback_of"] == 1
    assert rollback["status"] == "draft"
    record = await store.get("production")
    assert record["active_version"] == 1
    assert record["versions"][0]["status"] == "promoted"


def test_environment_configuration_rejects_plaintext_secrets_and_unbounded_values():
    with pytest.raises(MacEnvironmentError):
        validate_environment_config({"database_password": "plaintext"})
    assert validate_environment_config({"database_password": "secret://vault/prod/db"}) == {
        "database_password": "secret://vault/prod/db"
    }
    with pytest.raises(MacEnvironmentError):
        validate_environment_config({"x": "a" * 2049})


@pytest.mark.asyncio
async def test_missing_environment_and_stale_revision_are_explicit():
    store = MongoMacEnvironmentStore(Collection())
    with pytest.raises(MacEnvironmentNotFound):
        await store.get("staging")
    await store.create_draft(
        environment="staging", actor="author-1",
        config={"region": "eu-west-1"}, change_summary="Initial",
    )
    with pytest.raises(MacEnvironmentConflict):
        await store.update_draft(
            environment="staging", version=1, expected_latest_version=2,
            actor="author-1", config={"region": "us-east-1"},
            change_summary="Stale update",
        )


@pytest.mark.asyncio
async def test_new_revision_is_append_only_and_uses_latest_version_compare_and_set():
    store = MongoMacEnvironmentStore(Collection())
    await store.create_draft(
        environment="staging", actor="author-1",
        config={"replicas": 2}, change_summary="Initial",
    )
    revision = await store.create_revision(
        environment="staging", expected_latest_version=1, actor="author-2",
        config={"replicas": 4}, change_summary="Scale staging",
    )
    assert revision["version"] == 2
    assert revision["status"] == "draft"
    record = await store.get("staging")
    assert record["latest_version"] == 2
    assert record["versions"][0]["config"] == {"replicas": 2}
    with pytest.raises(MacEnvironmentConflict):
        await store.create_revision(
            environment="staging", expected_latest_version=1, actor="author-3",
            config={"replicas": 5}, change_summary="Stale scale",
        )


@pytest.mark.asyncio
async def test_only_verified_draft_author_can_edit_draft():
    store = MongoMacEnvironmentStore(Collection())
    await store.create_draft(
        environment="staging", actor="oidc-author",
        config={"replicas": 2}, change_summary="Initial",
    )
    with pytest.raises(MacEnvironmentConflict):
        await store.update_draft(
            environment="staging", version=1, expected_latest_version=1,
            actor="oidc-other", config={"replicas": 3},
            change_summary="Unauthorized edit",
        )
    updated = await store.update_draft(
        environment="staging", version=1, expected_latest_version=1,
        actor="oidc-author", config={"replicas": 4},
        change_summary="Author edit",
    )
    assert updated["versions"][0]["config"] == {"replicas": 4}


@pytest.mark.parametrize("key", ["region", "endpoint", "feature_flag"])
def test_secret_references_are_rejected_under_non_sensitive_keys(key):
    with pytest.raises(MacEnvironmentError, match="sensitive configuration key"):
        validate_environment_config({key: "secret://vault/prod/credential"})


@pytest.mark.parametrize("value", [123, True, None, {"token": "plaintext"}])
def test_sensitive_configuration_keys_reject_non_reference_values(value):
    with pytest.raises(MacEnvironmentError):
        validate_environment_config({"api_key": value})


@pytest.mark.parametrize("key", [
    "access_key", "signing_key", "encryption_key", "private_key",
    "refresh_token", "client_secret", "api-key",
])
def test_all_credential_key_variants_require_secret_references(key):
    with pytest.raises(MacEnvironmentError):
        validate_environment_config({key: "plaintext"})
    assert validate_environment_config({key: "secret://vault/prod/credential"}) == {
        key: "secret://vault/prod/credential"
    }


@pytest.mark.parametrize("reference", [
    "secret://vault/../production/db",
    "secret://vault/./production/db",
    "secret://vault//production/db",
    "secret://vault/",
])
def test_secret_references_reject_ambiguous_or_traversal_paths(reference):
    with pytest.raises(MacEnvironmentError):
        validate_environment_config({"database_password": reference})


@pytest.mark.asyncio
async def test_stale_draft_cannot_be_submitted_after_newer_revision_exists():
    store = MongoMacEnvironmentStore(Collection())
    await store.create_draft(
        environment="staging", actor="author-1",
        config={"region": "eu-west-1"}, change_summary="Initial",
    )
    await store.create_revision(
        environment="staging", expected_latest_version=1, actor="author-2",
        config={"region": "eu-central-1"}, change_summary="Newer revision",
    )
    with pytest.raises(MacEnvironmentConflict, match="latest draft"):
        await store.submit_for_approval(
            environment="staging", version=1, expected_latest_version=2, actor="author-1",
        )


@pytest.mark.asyncio
async def test_pending_revision_cannot_be_approved_after_newer_revision_exists():
    store = MongoMacEnvironmentStore(Collection())
    await store.create_draft(
        environment="staging", actor="author-1",
        config={"region": "eu-west-1"}, change_summary="Initial",
    )
    await store.submit_for_approval(
        environment="staging", version=1, expected_latest_version=1, actor="author-1",
    )
    await store.create_revision(
        environment="staging", expected_latest_version=1, actor="author-2",
        config={"region": "eu-central-1"}, change_summary="Newer revision",
    )
    with pytest.raises(MacEnvironmentConflict, match="latest revision"):
        await store.approve(
            environment="staging", version=1, expected_latest_version=2, actor="reviewer-1",
        )


@pytest.mark.asyncio
async def test_older_approved_revision_cannot_be_promoted_over_newer_draft():
    store = MongoMacEnvironmentStore(Collection())
    await store.create_draft(
        environment="staging", actor="author-1",
        config={"region": "eu-west-1"}, change_summary="Initial",
    )
    await store.submit_for_approval(
        environment="staging", version=1, expected_latest_version=1, actor="author-1",
    )
    await store.approve(
        environment="staging", version=1, expected_latest_version=1, actor="reviewer-1",
    )
    await store.create_revision(
        environment="staging", expected_latest_version=1, actor="author-2",
        config={"region": "eu-central-1"}, change_summary="Newer revision",
    )
    with pytest.raises(MacEnvironmentConflict, match="latest approved revision"):
        await store.promote(
            environment="staging", version=1, expected_active_version=0,
            expected_latest_version=2, actor="operator-1",
        )
