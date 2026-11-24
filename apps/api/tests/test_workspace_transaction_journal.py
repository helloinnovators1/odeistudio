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
