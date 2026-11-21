from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

from odei_api.services.execution_sandbox import (
    ContainerSandbox,
    SandboxProfile,
    SandboxProfileNotFound,
    SandboxProfileRegistry,
    UnsafeSandboxWorkspace,
    _capture_bounded,
)


def profile(**overrides) -> SandboxProfile:
    values = {
        "name": "python-tests",
        "image": "ghcr.io/odei/python@sha256:" + "a" * 64,
        "command": ("python", "-m", "pytest"),
        "timeout_seconds": 30,
        "memory_mb": 512,
        "cpus": 1.0,
        "pids_limit": 64,
        "tmpfs_mb": 32,
        "max_output_bytes": 4_096,
    }
    values.update(overrides)
    return SandboxProfile(**values)


def runner(tmp_path: Path) -> tuple[ContainerSandbox, Path]:
    root = tmp_path / "workspaces"
    root.mkdir()
    return ContainerSandbox(runtime_path=sys.executable, workspace_root=root), root


def test_profile_requires_digest_pinned_image_and_bounded_command() -> None:
    with pytest.raises(ValueError, match="pinned"):
        profile(image="ghcr.io/odei/python:latest").validate()
    with pytest.raises(ValueError, match="command"):
        profile(command=()).validate()
    with pytest.raises(ValueError, match="timeout"):
        profile(timeout_seconds=601).validate()



def test_profile_registry_only_returns_registered_validated_profiles() -> None:
    approved = profile()
    registry = SandboxProfileRegistry([approved])
    assert registry.names == ("python-tests",)
    assert registry.get("python-tests") is approved
    with pytest.raises(SandboxProfileNotFound):
        registry.get("node-tests")
    with pytest.raises(SandboxProfileNotFound):
        registry.get("../python-tests")
    with pytest.raises(ValueError, match="At least one"):
        SandboxProfileRegistry([])
    with pytest.raises(ValueError, match="Duplicate"):
        SandboxProfileRegistry([approved, profile()])
    with pytest.raises(ValueError, match="pinned"):
        SandboxProfileRegistry([profile(image="ghcr.io/odei/python:latest")])


def test_runtime_arguments_enforce_network_and_privilege_boundaries(tmp_path: Path) -> None:
    sandbox, root = runner(tmp_path)
    workspace = root / "job-1"
    workspace.mkdir()
    (workspace / "main.py").write_text("print('safe')", encoding="utf-8")

    args = sandbox.build_run_arguments(
        profile(), workspace, container_name="odei-exec-" + "b" * 32,
        arguments=("-q",),
    )
    assert "--network=none" in args
    assert "--read-only" in args
    assert "--cap-drop=ALL" in args
    assert "--security-opt=no-new-privileges:true" in args
    assert "--pids-limit" in args
    assert "--memory-swap" in args
    assert "--tmpfs" in args
    assert "--user" in args
    assert "--privileged" not in args
    assert not any(item.startswith("OPENAI_API_KEY=") for item in args)
    image_index = args.index(profile().image)
    assert args[image_index + 1:] == ("python", "-m", "pytest", "-q")


def test_workspace_must_be_a_direct_child_and_must_not_contain_hardlinks(tmp_path: Path) -> None:
    sandbox, root = runner(tmp_path)
    nested = root / "nested"
    nested.mkdir()
    workspace = nested / "job"
    workspace.mkdir()
    with pytest.raises(UnsafeSandboxWorkspace, match="direct child"):
        sandbox.build_run_arguments(
            profile(), workspace, container_name="odei-exec-" + "c" * 32
        )

    workspace = root / "job"
    workspace.mkdir()
    source = workspace / "main.py"
    source.write_text("print('safe')", encoding="utf-8")
    alias = workspace / "alias.py"
    try:
        os.link(source, alias)
    except (OSError, NotImplementedError):
        pytest.skip("Hard links are unavailable in this test environment")
    with pytest.raises(UnsafeSandboxWorkspace, match="hard-linked"):
        sandbox.build_run_arguments(
            profile(), workspace, container_name="odei-exec-" + "d" * 32
        )


def test_workspace_symlinks_are_rejected(tmp_path: Path) -> None:
    sandbox, root = runner(tmp_path)
    workspace = root / "job"
    workspace.mkdir()
    target = workspace / "target.py"
    target.write_text("print('safe')", encoding="utf-8")
    link = workspace / "linked.py"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are unavailable in this test environment")
    with pytest.raises(UnsafeSandboxWorkspace, match="link or special"):
        sandbox.build_run_arguments(
            profile(), workspace, container_name="odei-exec-" + "e" * 32
        )


def test_bounded_output_capture_drains_and_truncates() -> None:
    async def scenario() -> tuple[bytes, bool]:
        reader = asyncio.StreamReader()
        reader.feed_data(b"abcdefgh")
        reader.feed_eof()
        return await _capture_bounded(reader, 4)

    output, truncated = asyncio.run(scenario())
    assert output == b"abcd"
    assert truncated is True


@pytest.mark.skipif(os.name == "nt", reason="POSIX executable shim used for OCI runtime contract test")
def test_runner_captures_output_and_exit_code_and_cleans_container(tmp_path: Path) -> None:
    runtime = tmp_path / "fake-runtime"
    runtime.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "if len(sys.argv) > 1 and sys.argv[1] == 'run':\n"
        " print('sandbox stdout')\n"
        " print('sandbox stderr', file=sys.stderr)\n"
        " raise SystemExit(7)\n"
        "raise SystemExit(0)\n",
        encoding="utf-8",
    )
    runtime.chmod(0o755)
    root = tmp_path / "workspaces"
    root.mkdir()
    workspace = root / "job"
    workspace.mkdir()
    (workspace / "main.py").write_text("print('test')", encoding="utf-8")
    sandbox = ContainerSandbox(runtime_path=runtime, workspace_root=root)

    result = asyncio.run(sandbox.run(profile(), workspace))

    assert result.exit_code == 7
    assert result.stdout.strip() == "sandbox stdout"
    assert result.stderr.strip() == "sandbox stderr"
    assert result.timed_out is False
    assert result.stdout_truncated is False
    assert result.stderr_truncated is False


@pytest.mark.skipif(os.name == "nt", reason="POSIX executable shim used for OCI runtime timeout test")
def test_runner_terminates_timed_out_runtime(tmp_path: Path) -> None:
    runtime = tmp_path / "slow-runtime"
    runtime.write_text(
        "#!/usr/bin/env python3\\n"
        "import sys, time\\n"
        "if len(sys.argv) > 1 and sys.argv[1] == 'run':\\n"
        " time.sleep(10)\\n"
        "raise SystemExit(0)\\n",
        encoding="utf-8",
    )
    runtime.chmod(0o755)
    root = tmp_path / "workspaces"
    root.mkdir()
    workspace = root / "job"
    workspace.mkdir()
    sandbox = ContainerSandbox(runtime_path=runtime, workspace_root=root)

    result = asyncio.run(sandbox.run(profile(timeout_seconds=1), workspace))

    assert result.timed_out is True
    assert result.exit_code == 124
