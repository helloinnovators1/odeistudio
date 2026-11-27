from __future__ import annotations

import hashlib
import os

import pytest

from odei_api.services.workspace_transaction_journal import (
    DurableWorkspaceJournal,
    WorkspaceJournalError,
    workspace_root_key,
)


def _patch(path: str, before: str, after: str) -> dict:
    return {
        "path": path,
        "operation": "update",
        "base_sha256": hashlib.sha256(before.encode()).hexdigest(),
        "result_sha256": hashlib.sha256(after.encode()).hexdigest(),
        "content": after,
    }


def test_pending_before_images_survive_journal_reopen(tmp_path):
    database = tmp_path / "private" / "journal.sqlite3"
    root_key = "a" * 64
    patch = _patch("src/main.py", "before", "after")
    journal = DurableWorkspaceJournal(database)

    transaction_id = journal.prepare(root_key, [patch], ["before"])
    del journal

    reopened = DurableWorkspaceJournal(database)
    pending = reopened.pending(root_key)
    assert len(pending) == 1
    assert pending[0]["transaction_id"] == transaction_id
    assert pending[0]["files"] == [{"patch": patch, "before": "before"}]


def test_terminal_commit_compacts_before_images_and_keeps_receipt(tmp_path):
    database = tmp_path / "journal.sqlite3"
    journal = DurableWorkspaceJournal(database)
    transaction_id = journal.prepare("b" * 64, [_patch("main.py", "old", "new")], ["old"])

    journal.finish(
        transaction_id, state="committed",
        receipt={"applied": ["main.py"], "rollback_required": False},
    )

    assert journal.pending("b" * 64) == []
    import sqlite3
    with sqlite3.connect(database) as connection:
        state, payload, receipt = connection.execute(
            "SELECT state, payload_json, receipt_json FROM patch_transactions WHERE transaction_id=?",
            (transaction_id,),
        ).fetchone()
    assert state == "committed"
    assert payload == "[]"
    assert '"main.py"' in receipt


def test_journal_rejects_oversized_or_mismatched_before_images(tmp_path):
    journal = DurableWorkspaceJournal(tmp_path / "journal.sqlite3")
    patch = _patch("main.py", "old", "new")
    with pytest.raises(ValueError, match="exactly one"):
        journal.prepare("c" * 64, [patch], [])
    huge = "x" * (5 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match="per-file limit"):
        journal.prepare("c" * 64, [patch], [huge])


def test_journal_rejects_invalid_root_identity_and_payload(tmp_path):
    journal = DurableWorkspaceJournal(tmp_path / "journal.sqlite3")
    with pytest.raises(ValueError, match="root key"):
        journal.prepare("not-a-root-key", [_patch("main.py", "old", "new")], ["old"])
    with pytest.raises(ValueError, match="between 1 and 20"):
        journal.prepare("d" * 64, [], [])


def test_root_key_is_stable_for_same_selection_and_does_not_expose_path(tmp_path):
    selected = tmp_path / "my-project"
    selected.mkdir()
    first = workspace_root_key(selected, "native-file-id-1")
    second = workspace_root_key(selected, "native-file-id-1")
    other_identity = workspace_root_key(selected, "native-file-id-2")
    assert first == second
    assert first != other_identity
    assert str(selected) not in first


@pytest.mark.skipif(os.name == "nt", reason="POSIX state-directory permission check")
def test_journal_creates_private_state_directory_and_database(tmp_path):
    database = tmp_path / "state" / "journal.sqlite3"
    DurableWorkspaceJournal(database)
    assert (database.parent.stat().st_mode & 0o777) == 0o700
    assert (database.stat().st_mode & 0o777) == 0o600


def test_journal_refuses_symlink_database(tmp_path):
    target = tmp_path / "target.sqlite3"
    target.touch()
    link = tmp_path / "journal.sqlite3"
    link.symlink_to(target)
    with pytest.raises(WorkspaceJournalError, match="symbolic link"):
        DurableWorkspaceJournal(link)


def _batch_for_recovery(project):
    before = (project / "main.py").read_text(encoding="utf-8")
    deleted = (project / "deleted.txt").read_text(encoding="utf-8")
    return [
        {
            "path": "main.py", "operation": "update",
            "base_sha256": hashlib.sha256(before.encode()).hexdigest(),
            "result_sha256": hashlib.sha256(b"after").hexdigest(),
            "content": "after",
        },
        {
            "path": "deleted.txt", "operation": "delete",
            "base_sha256": hashlib.sha256(deleted.encode()).hexdigest(),
            "result_sha256": None, "content": None,
        },
        {
            "path": "created.txt", "operation": "create",
            "base_sha256": None,
            "result_sha256": hashlib.sha256(b"created").hexdigest(),
            "content": "created",
        },
    ]


def test_registry_recovers_interrupted_batch_after_process_restart(tmp_path, monkeypatch):
    from odei_api.services import workspace_patch_apply
    from odei_api.services.workspace_handles import WorkspaceHandleRegistry

    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text("before", encoding="utf-8")
    (project / "deleted.txt").write_text("preserve me", encoding="utf-8")
    journal = DurableWorkspaceJournal(tmp_path / "state" / "journal.sqlite3")
    first_registry = WorkspaceHandleRegistry(journal=journal)
    workspace_id = first_registry.register_selected_root(project, allow_patch_apply=True)
    real_apply = workspace_patch_apply.apply_single_file_patch
    calls = {"count": 0}

    def simulate_process_crash(grant, item):
        calls["count"] += 1
        if calls["count"] == 3:
            raise KeyboardInterrupt("simulated abrupt process termination")
        return real_apply(grant, item)

    monkeypatch.setattr(workspace_patch_apply, "apply_single_file_patch", simulate_process_crash)
    with pytest.raises(KeyboardInterrupt):
        first_registry.apply_patch_batch(workspace_id, _batch_for_recovery(project))
    first_registry.close()
    monkeypatch.setattr(workspace_patch_apply, "apply_single_file_patch", real_apply)

    assert (project / "main.py").read_text(encoding="utf-8") == "after"
    assert not (project / "deleted.txt").exists()
    assert not (project / "created.txt").exists()

    restarted_registry = WorkspaceHandleRegistry(journal=journal)
    try:
        recovered_id = restarted_registry.register_selected_root(
            project, allow_patch_apply=True
        )
        assert restarted_registry.read_text(recovered_id, "main.py") == "before"
        assert not (project / "created.txt").exists()
        assert (project / "deleted.txt").read_text(encoding="utf-8") == "preserve me"
        assert journal.pending(
            workspace_root_key(
                project,
                f"posix:{os.stat(project).st_dev}:{os.stat(project).st_ino}",
            ) if os.name != "nt" else "0" * 64
        ) == []
    finally:
        restarted_registry.close()


def test_crash_recovery_preserves_external_edits_and_blocks_workspace_open(tmp_path, monkeypatch):
    from odei_api.services import workspace_patch_apply
    from odei_api.services.workspace_handles import WorkspaceHandleRegistry
    from odei_api.services.workspace_patch_apply import WorkspacePatchRecoveryRequired

    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text("before", encoding="utf-8")
    (project / "deleted.txt").write_text("preserve me", encoding="utf-8")
    journal = DurableWorkspaceJournal(tmp_path / "state" / "journal.sqlite3")
    registry = WorkspaceHandleRegistry(journal=journal)
    workspace_id = registry.register_selected_root(project, allow_patch_apply=True)
    real_apply = workspace_patch_apply.apply_single_file_patch
    calls = {"count": 0}

    def simulate_process_crash(grant, item):
        calls["count"] += 1
        if calls["count"] == 3:
            raise KeyboardInterrupt("simulated abrupt process termination")
        return real_apply(grant, item)

    monkeypatch.setattr(workspace_patch_apply, "apply_single_file_patch", simulate_process_crash)
    with pytest.raises(KeyboardInterrupt):
        registry.apply_patch_batch(workspace_id, _batch_for_recovery(project))
    registry.close()
    monkeypatch.setattr(workspace_patch_apply, "apply_single_file_patch", real_apply)

    (project / "main.py").write_text("edited by user", encoding="utf-8")
    restarted_registry = WorkspaceHandleRegistry(journal=journal)
    try:
        with pytest.raises(WorkspacePatchRecoveryRequired, match="conflicts"):
            restarted_registry.register_selected_root(
                project, allow_patch_apply=True
            )
        assert (project / "main.py").read_text(encoding="utf-8") == "edited by user"
        assert (project / "deleted.txt").read_text(encoding="utf-8") == "preserve me"
        assert not (project / "created.txt").exists()
    finally:
        restarted_registry.close()


def test_conflicted_transaction_keeps_recovery_payload_and_scoped_receipt(tmp_path):
    journal = DurableWorkspaceJournal(tmp_path / "journal.sqlite3")
    root_key = "e" * 64
    patch = _patch("main.py", "before", "after")
    transaction_id = journal.prepare(root_key, [patch], ["before"])
    journal.finish(
        transaction_id, state="conflict",
        receipt={"recovery_conflicts": ["main.py"]},
    )

    pending = journal.pending(root_key)
    assert pending[0]["transaction_id"] == transaction_id
    assert pending[0]["files"] == [{"patch": patch, "before": "before"}]
    assert journal.receipt(root_key, transaction_id) == {
        "transaction_id": transaction_id,
        "state": "conflict",
        "receipt": {"recovery_conflicts": ["main.py"]},
    }
    assert journal.receipt("f" * 64, transaction_id) is None

def test_journal_rejects_casefolded_duplicate_paths_and_traversal(tmp_path):
    journal = DurableWorkspaceJournal(tmp_path / "journal.sqlite3")
    first = _patch("src/Main.py", "old", "new")
    second = _patch("src/main.py", "old", "new")
    with pytest.raises(ValueError, match="duplicate paths"):
        journal.prepare("1" * 64, [first, second], ["old", "old"])
    unsafe = _patch("../outside.py", "old", "new")
    with pytest.raises(ValueError, match="path is invalid"):
        journal.prepare("2" * 64, [unsafe], ["old"])


def test_journal_rejects_before_image_hash_mismatch_and_invalid_operation(tmp_path):
    journal = DurableWorkspaceJournal(tmp_path / "journal.sqlite3")
    patch = _patch("main.py", "old", "new")
    with pytest.raises(ValueError, match="hashes are inconsistent"):
        journal.prepare("3" * 64, [patch], ["different"])
    invalid = {**patch, "operation": "move"}
    with pytest.raises(ValueError, match="operation or content hashes"):
        journal.prepare("4" * 64, [invalid], ["old"])


def test_journal_enforces_combined_before_and_after_byte_budget(tmp_path):
    journal = DurableWorkspaceJournal(tmp_path / "journal.sqlite3")
    before = "b" * (900 * 1024)
    after = "a" * (900 * 1024)
    patches = [
        {
            "path": f"module_{index}.py", "operation": "update",
            "base_sha256": hashlib.sha256(before.encode()).hexdigest(),
            "result_sha256": hashlib.sha256(after.encode()).hexdigest(),
            "content": after,
        }
        for index in range(3)
    ]
    with pytest.raises(ValueError, match="aggregate"):
        journal.prepare("5" * 64, patches, [before, before, before])


@pytest.mark.skipif(os.name != "posix", reason="POSIX directory-fsync crash boundary")
@pytest.mark.parametrize(
    ("operation", "crash_on_fsync"),
    [("update", 2), ("delete", 1), ("create", 2)],
)
def test_restart_recovers_crash_after_namespace_mutation_before_directory_flush(
    tmp_path, monkeypatch, operation, crash_on_fsync,
):
    from odei_api.services.workspace_handles import WorkspaceHandleRegistry

    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text("before", encoding="utf-8")
    (project / "deleted.py").write_text("preserve", encoding="utf-8")
    journal = DurableWorkspaceJournal(tmp_path / "state" / "journal.sqlite3")
    registry = WorkspaceHandleRegistry(journal=journal)
    workspace_id = registry.register_selected_root(project, allow_patch_apply=True)

    if operation == "update":
        item = {
            "path": "main.py", "operation": "update",
            "base_sha256": hashlib.sha256(b"before").hexdigest(),
            "result_sha256": hashlib.sha256(b"after").hexdigest(),
            "content": "after",
        }
    elif operation == "delete":
        item = {
            "path": "deleted.py", "operation": "delete",
            "base_sha256": hashlib.sha256(b"preserve").hexdigest(),
            "result_sha256": None, "content": None,
        }
    else:
        item = {
            "path": "created.py", "operation": "create",
            "base_sha256": None,
            "result_sha256": hashlib.sha256(b"created").hexdigest(),
            "content": "created",
        }

    real_fsync = os.fsync
    calls = {"count": 0}

    def crash_at_flush_boundary(descriptor):
        calls["count"] += 1
        if calls["count"] == crash_on_fsync:
            raise KeyboardInterrupt("simulated host crash at filesystem flush boundary")
        return real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", crash_at_flush_boundary)
    with pytest.raises(KeyboardInterrupt):
        registry.apply_patch_batch(workspace_id, [item])
    registry.close()
    monkeypatch.setattr(os, "fsync", real_fsync)

    restarted = WorkspaceHandleRegistry(journal=journal)
    try:
        recovered_id = restarted.register_selected_root(project, allow_patch_apply=True)
        if operation == "update":
            assert restarted.read_text(recovered_id, "main.py") == "before"
        elif operation == "delete":
            assert restarted.read_text(recovered_id, "deleted.py") == "preserve"
        else:
            assert not (project / "created.py").exists()
        pending = journal.pending(
            workspace_root_key(
                project,
                f"posix:{os.stat(project).st_dev}:{os.stat(project).st_ino}",
            ) if os.name != "nt" else "0" * 64
        )
        assert pending == []
    finally:
        restarted.close()


@pytest.mark.parametrize("operation", ["create", "update", "delete"])
def test_batch_compensates_when_native_namespace_operation_mutates_then_raises(
    tmp_path, monkeypatch, operation,
):
    from odei_api.services import workspace_patch_apply
    from odei_api.services.workspace_handles import WorkspaceHandleRegistry

    project = tmp_path / "project"
    project.mkdir()
    target = project / "target.py"
    before = "before"
    after = "after"
    if operation != "create":
        target.write_text(before, encoding="utf-8")
    content = after if operation != "delete" else None
    patch = {
        "path": "target.py",
        "operation": operation,
        "base_sha256": hashlib.sha256(before.encode()).hexdigest() if operation != "create" else None,
        "result_sha256": hashlib.sha256(after.encode()).hexdigest() if content is not None else None,
        "content": content,
    }
    registry = WorkspaceHandleRegistry(
        journal=DurableWorkspaceJournal(tmp_path / "state" / "journal.sqlite3")
    )
    workspace_id = registry.register_selected_root(project, allow_patch_apply=True)
    calls = {"count": 0}

    if operation == "create":
        original = workspace_patch_apply.os.unlink

        def fail_after_create(path, *args, **kwargs):
            if isinstance(path, str) and path.startswith(".odei-") and calls["count"] == 0:
                calls["count"] += 1
                raise OSError("injected cleanup failure after hard-link create")
            return original(path, *args, **kwargs)

        monkeypatch.setattr(workspace_patch_apply.os, "unlink", fail_after_create)
    elif operation == "update":
        original = workspace_patch_apply.os.replace

        def replace_then_fail(*args, **kwargs):
            result = original(*args, **kwargs)
            if calls["count"] == 0:
                calls["count"] += 1
                raise OSError("injected failure after atomic replacement")
            return result

        monkeypatch.setattr(workspace_patch_apply.os, "replace", replace_then_fail)
    else:
        original = workspace_patch_apply.os.unlink

        def unlink_then_fail(path, *args, **kwargs):
            result = original(path, *args, **kwargs)
            if path == "target.py" and calls["count"] == 0:
                calls["count"] += 1
                raise OSError("injected failure after atomic deletion")
            return result

        monkeypatch.setattr(workspace_patch_apply.os, "unlink", unlink_then_fail)

    try:
        with pytest.raises(workspace_patch_apply.WorkspacePatchBatchError) as caught:
            registry.apply_patch_batch(workspace_id, [patch])
        assert caught.value.rollback_complete is True
        if operation == "create":
            assert not target.exists()
        else:
            assert target.read_text(encoding="utf-8") == before
    finally:
        registry.close()
