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
    with pytest.raises(ValueError, match="aggregate"):
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
