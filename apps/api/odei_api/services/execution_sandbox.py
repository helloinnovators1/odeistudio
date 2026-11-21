"""Ephemeral, policy-bounded OCI execution backend for trusted NEXUS workers.

This module deliberately exposes no HTTP route and accepts no user-selected
image, runtime flags, environment variables, or host paths. A trusted worker
must create a fresh workspace directory beneath its configured workspace root
and select a server-defined, digest-pinned SandboxProfile.
"""
from __future__ import annotations

import asyncio
import math
import os
import re
import stat
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


_IMAGE_DIGEST = re.compile(r"^[A-Za-z0-9._/:@-]+@sha256:[0-9a-f]{64}$")
_MAX_ARGUMENTS = 32
_MAX_ARGUMENT_CHARS = 1_024
_MAX_WORKSPACE_ENTRIES = 10_000
_STREAM_CHUNK_BYTES = 8_192


class SandboxError(RuntimeError):
    """Base error for safe execution setup and lifecycle failures."""


class SandboxUnavailable(SandboxError):
    """The configured OCI runtime is unavailable or cannot be invoked."""


class UnsafeSandboxWorkspace(SandboxError):
    """The workspace is not a fresh, contained, regular-file-only directory."""


@dataclass(frozen=True)
class SandboxProfile:
    """Trusted server-side execution profile; never deserialize from a request."""

    name: str
    image: str
    command: tuple[str, ...]
    timeout_seconds: int = 120
    memory_mb: int = 1_024
    cpus: float = 1.0
    pids_limit: int = 128
    tmpfs_mb: int = 64
    max_output_bytes: int = 256_000

    def validate(self) -> None:
        if not self.name or len(self.name) > 64 or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", self.name):
            raise ValueError("Sandbox profile name is invalid")
        if not _IMAGE_DIGEST.fullmatch(self.image):
            raise ValueError("Sandbox images must be pinned by a SHA-256 digest")
        if not self.command or len(self.command) > 16:
            raise ValueError("Sandbox profile must define a bounded command")
        if any(
            not isinstance(item, str) or not item or len(item) > _MAX_ARGUMENT_CHARS
            or "\x00" in item or "\r" in item or "\n" in item
            for item in self.command
        ):
            raise ValueError("Sandbox profile command is invalid")
        if not 1 <= self.timeout_seconds <= 600:
            raise ValueError("Sandbox timeout must be between 1 and 600 seconds")
        if not 128 <= self.memory_mb <= 8_192:
            raise ValueError("Sandbox memory must be between 128 and 8192 MB")
        if not math.isfinite(self.cpus) or not 0.1 <= self.cpus <= 4.0:
            raise ValueError("Sandbox CPU quota must be between 0.1 and 4 CPUs")
        if not 16 <= self.pids_limit <= 1_024:
            raise ValueError("Sandbox process limit must be between 16 and 1024")
        if not 16 <= self.tmpfs_mb <= 512:
            raise ValueError("Sandbox temporary storage must be between 16 and 512 MB")
        if not 1_024 <= self.max_output_bytes <= 1_048_576:
            raise ValueError("Sandbox output limit must be between 1 KB and 1 MB")


@dataclass(frozen=True)
class SandboxResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool
    stdout_truncated: bool
    stderr_truncated: bool


async def _capture_bounded(
    reader: asyncio.StreamReader, maximum: int
) -> tuple[bytes, bool]:
    output = bytearray()
    truncated = False
    while True:
        chunk = await reader.read(_STREAM_CHUNK_BYTES)
        if not chunk:
            break
        remaining = maximum - len(output)
        if remaining > 0:
            output.extend(chunk[:remaining])
        if len(chunk) > remaining:
            truncated = True
    return bytes(output), truncated


class ContainerSandbox:
    """Run one command in a disposable, network-disabled OCI container.

    The host runtime must be configured by the deployment. The workspace must
    be a fresh direct child of workspace_root; it is the only host path mounted.
    The container receives no host environment variables or credentials.
    """

    def __init__(self, *, runtime_path: str | Path, workspace_root: str | Path) -> None:
        runtime = Path(runtime_path)
        root = Path(workspace_root)
        if runtime.is_symlink() or not runtime.is_file():
            raise SandboxUnavailable("The configured container runtime is not a regular file")
        if not os.access(runtime, os.X_OK):
            raise SandboxUnavailable("The configured container runtime is not executable")
        if root.is_symlink() or not root.is_dir():
            raise SandboxUnavailable("The execution workspace root must be an existing directory")
        self._runtime = str(runtime.resolve(strict=True))
        self._workspace_root = root.resolve(strict=True)
        if "," in str(self._workspace_root) or "\n" in str(self._workspace_root):
            raise SandboxUnavailable("The execution workspace root contains an unsupported path character")

    def _validate_workspace(self, workspace_dir: str | Path) -> Path:
        supplied = Path(workspace_dir)
        if supplied.is_symlink() or not supplied.is_dir():
            raise UnsafeSandboxWorkspace("Execution workspace must be an existing real directory")
        workspace = supplied.resolve(strict=True)
        if workspace.parent != self._workspace_root or workspace == self._workspace_root:
            raise UnsafeSandboxWorkspace("Execution workspace must be a direct child of the configured root")
        if "," in str(workspace) or "\n" in str(workspace):
            raise UnsafeSandboxWorkspace("Execution workspace path contains an unsupported character")

        entries = 0
        for base, directories, files in os.walk(workspace, topdown=True, followlinks=False):
            for name in directories + files:
                entries += 1
                if entries > _MAX_WORKSPACE_ENTRIES:
                    raise UnsafeSandboxWorkspace("Execution workspace contains too many entries")
                item = Path(base) / name
                try:
                    mode = item.lstat().st_mode
                except OSError as exc:
                    raise UnsafeSandboxWorkspace("Execution workspace changed during validation") from exc
                if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                    raise UnsafeSandboxWorkspace("Execution workspace contains a link or special file")
                if stat.S_ISREG(mode) and item.stat(follow_symlinks=False).st_nlink != 1:
                    raise UnsafeSandboxWorkspace("Execution workspace contains a hard-linked file")
        return workspace

    @staticmethod
    def _prepare_workspace_permissions(workspace: Path) -> None:
        """Make only the disposable snapshot writable by the unprivileged container UID."""
        for base, directories, files in os.walk(workspace, topdown=True, followlinks=False):
            for name in directories:
                os.chmod(Path(base) / name, 0o777, follow_symlinks=False)
            for name in files:
                item = Path(base) / name
                mode = item.lstat().st_mode
                os.chmod(item, 0o666 | (stat.S_IMODE(mode) & 0o111), follow_symlinks=False)
        os.chmod(workspace, 0o777)

    @staticmethod
    def _validate_arguments(arguments: Sequence[str]) -> tuple[str, ...]:
        if isinstance(arguments, (str, bytes)) or len(arguments) > _MAX_ARGUMENTS:
            raise ValueError("Execution arguments must be a bounded list of strings")
        result = tuple(arguments)
        if any(
            not isinstance(item, str) or len(item) > _MAX_ARGUMENT_CHARS
            or "\x00" in item or "\r" in item or "\n" in item
            for item in result
        ):
            raise ValueError("Execution argument is invalid")
        return result

    def build_run_arguments(
        self,
        profile: SandboxProfile,
        workspace: str | Path,
        *,
        container_name: str,
        arguments: Sequence[str] = (),
    ) -> tuple[str, ...]:
        """Build a shell-free, least-privilege runtime argument vector."""
        profile.validate()
        workspace_path = self._validate_workspace(workspace)
        extra = self._validate_arguments(arguments)
        if not re.fullmatch(r"odei-exec-[a-f0-9]{32}", container_name):
            raise ValueError("Sandbox container name is invalid")

        return (
            "run", "--rm", "--pull=never", "--name", container_name,
            "--network=none", "--read-only", "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--pids-limit", str(profile.pids_limit),
            "--memory", f"{profile.memory_mb}m",
            "--memory-swap", f"{profile.memory_mb}m",
            "--cpus", str(profile.cpus),
            "--ulimit", "nofile=1024:1024",
            "--tmpfs", f"/tmp:rw,nosuid,nodev,noexec,size={profile.tmpfs_mb}m",
            "--user", "65532:65532",
            "--workdir", "/workspace",
            "--mount", f"type=bind,src={workspace_path},dst=/workspace,rw",
            "--env", "HOME=/tmp",
            "--env", "PATH=/usr/local/bin:/usr/bin:/bin",
            "--env", "CI=1",
            "--env", "NO_COLOR=1",
            "--env", "PYTHONDONTWRITEBYTECODE=1",
            profile.image, *profile.command, *extra,
        )

    async def _remove_container(self, container_name: str) -> None:
        try:
            process = await asyncio.create_subprocess_exec(
                self._runtime, "rm", "--force", container_name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(process.wait(), timeout=5)
        except (OSError, asyncio.TimeoutError):
            return

    async def run(
        self,
        profile: SandboxProfile,
        workspace_dir: str | Path,
        *,
        arguments: Sequence[str] = (),
    ) -> SandboxResult:
        """Run a fixed-profile command and always attempt container cleanup."""
        profile.validate()
        workspace = self._validate_workspace(workspace_dir)
        self._prepare_workspace_permissions(workspace)
        extra = self._validate_arguments(arguments)
        container_name = "odei-exec-" + uuid.uuid4().hex
        command = (
            self._runtime,
            *self.build_run_arguments(
                profile, workspace, container_name=container_name, arguments=extra
            ),
        )
        started = time.monotonic()
        process: asyncio.subprocess.Process | None = None
        stdout_task: asyncio.Task | None = None
        stderr_task: asyncio.Task | None = None
        timed_out = False
        try:
            try:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    limit=65_536,
                )
            except OSError as exc:
                raise SandboxUnavailable("The configured OCI runtime could not be started") from exc

            assert process.stdout is not None and process.stderr is not None
            stdout_task = asyncio.create_task(
                _capture_bounded(process.stdout, profile.max_output_bytes)
            )
            stderr_task = asyncio.create_task(
                _capture_bounded(process.stderr, profile.max_output_bytes)
            )
            try:
                await asyncio.wait_for(process.wait(), timeout=profile.timeout_seconds)
            except asyncio.TimeoutError:
                timed_out = True
                await self._remove_container(container_name)
                if process.returncode is None:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=3)
                    except asyncio.TimeoutError:
                        process.kill()
                        await process.wait()

            stdout_bytes, stdout_truncated = await stdout_task
            stderr_bytes, stderr_truncated = await stderr_task
            return SandboxResult(
                exit_code=124 if timed_out else int(process.returncode or 0),
                stdout=stdout_bytes.decode("utf-8", errors="replace"),
                stderr=stderr_bytes.decode("utf-8", errors="replace"),
                duration_ms=max(0, int((time.monotonic() - started) * 1_000)),
                timed_out=timed_out,
                stdout_truncated=stdout_truncated,
                stderr_truncated=stderr_truncated,
            )
        except asyncio.CancelledError:
            if process is not None and process.returncode is None:
                await self._remove_container(container_name)
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=3)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
            raise
        finally:
            await self._remove_container(container_name)
            for task in (stdout_task, stderr_task):
                if task is not None and not task.done():
                    task.cancel()
