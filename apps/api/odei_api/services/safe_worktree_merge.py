"""Conflict-safe local merge-back for isolated NEXUS Git worktrees."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path


class WorktreeMergeConflict(RuntimeError):
    """The worktree changes cannot be merged without conflicts or stale refs."""


class SafeWorktreeMerger:
    """Create a merge commit and update a target ref with compare-and-swap semantics.

    This operates only on a local repository. It never pushes or deploys.
    """

    def __init__(self, repository: str | Path) -> None:
        path = Path(repository)
        if path.is_symlink():
            raise ValueError("repository cannot be a symbolic link")
        self.repository = path.resolve(strict=True)
        if not (self.repository / ".git").exists():
            raise ValueError("repository must be a Git worktree")

    def merge_back(
        self,
        *,
        target_branch: str,
        expected_base_commit: str,
        worker_commit: str,
        message: str = "Merge isolated NEXUS job changes",
    ) -> str:
        if not re.fullmatch(r"[a-f0-9]{40,64}", expected_base_commit):
            raise ValueError("expected_base_commit must be a full Git object ID")
        if not re.fullmatch(r"[a-f0-9]{40,64}", worker_commit):
            raise ValueError("worker_commit must be a full Git object ID")
        if not isinstance(message, str) or not message.strip() or len(message) > 500:
            raise ValueError("merge message is invalid")
        checked = self._git("check-ref-format", "--branch", target_branch, check=False)
        if checked.returncode:
            raise ValueError("target_branch is invalid")
        ref = f"refs/heads/{target_branch}"
        current = self._git("rev-parse", "--verify", ref).stdout.strip()
        if current != expected_base_commit:
            raise WorktreeMergeConflict("target branch moved since the job was created")
        self._git("cat-file", "-e", f"{worker_commit}^{{commit}}")
        ancestry = self._git(
            "merge-base", "--is-ancestor", expected_base_commit, worker_commit,
            check=False,
        )
        if ancestry.returncode:
            raise WorktreeMergeConflict("worker commit is not based on the expected target")
        merged_tree = self._git(
            "merge-tree", "--write-tree", expected_base_commit, worker_commit,
            check=False,
        )
        if merged_tree.returncode:
            raise WorktreeMergeConflict("worktree changes conflict with the target branch")
        tree = merged_tree.stdout.splitlines()[0].strip()
        if not re.fullmatch(r"[a-f0-9]{40,64}", tree):
            raise WorktreeMergeConflict("Git did not produce a valid merged tree")
        # commit-tree does not inherit the identity configured by `git commit` flags.
        # Supply a stable, non-human service identity for this synthetic merge commit.
        commit = self._git(
            "-c", "user.name=ODEI NEXUS", "-c", "user.email=nexus@odei.invalid",
            "commit-tree", tree, "-p", expected_base_commit, "-p", worker_commit,
            "-m", message,
        ).stdout.strip()
        if not re.fullmatch(r"[a-f0-9]{40,64}", commit):
            raise WorktreeMergeConflict("Git did not produce a valid merge commit")
        updated = self._git(
            "update-ref", ref, commit, expected_base_commit, check=False,
        )
        if updated.returncode:
            raise WorktreeMergeConflict("target branch changed during merge-back")
        return commit

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", "-C", str(self.repository), *args],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if check and result.returncode:
            raise WorktreeMergeConflict("Git rejected the safe merge-back operation")
        return result
