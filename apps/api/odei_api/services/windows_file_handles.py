"""Read-only Windows file opens relative to already-open directory handles."""
from __future__ import annotations

import ctypes
import msvcrt
import os
import stat
from ctypes import wintypes
from pathlib import Path


class UnsafeWindowsPath(OSError):
    """A reparse point or unexpected filesystem object was encountered."""


FILE_LIST_DIRECTORY = 0x0001
FILE_READ_DATA = 0x0001
FILE_READ_ATTRIBUTES = 0x0080
SYNCHRONIZE = 0x00100000
FILE_SHARE_READ = 0x1
FILE_SHARE_WRITE = 0x2
FILE_SHARE_DELETE = 0x4
OPEN_EXISTING = 3
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
FILE_ATTRIBUTE_DIRECTORY = 0x10
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
FILE_OPEN = 1
FILE_DIRECTORY_FILE = 0x00000001
FILE_NON_DIRECTORY_FILE = 0x00000040
FILE_SYNCHRONOUS_IO_NONALERT = 0x00000020
OBJ_CASE_INSENSITIVE = 0x40
FILE_ATTRIBUTE_TAG_INFO_CLASS = 9


class _UnicodeString(ctypes.Structure):
    _fields_ = [
        ("Length", wintypes.USHORT),
        ("MaximumLength", wintypes.USHORT),
        ("Buffer", wintypes.LPWSTR),
    ]


class _ObjectAttributes(ctypes.Structure):
    _fields_ = [
        ("Length", wintypes.ULONG),
        ("RootDirectory", wintypes.HANDLE),
        ("ObjectName", ctypes.POINTER(_UnicodeString)),
        ("Attributes", wintypes.ULONG),
        ("SecurityDescriptor", wintypes.LPVOID),
        ("SecurityQualityOfService", wintypes.LPVOID),
    ]


class _IoStatusBlock(ctypes.Structure):
    _fields_ = [
        ("Status", ctypes.c_ssize_t),
        ("Information", ctypes.c_size_t),
    ]


class _FileAttributeTagInfo(ctypes.Structure):
    _fields_ = [
        ("FileAttributes", wintypes.DWORD),
        ("ReparseTag", wintypes.DWORD),
    ]


def _apis():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    ntdll = ctypes.WinDLL("ntdll")
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
        wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.GetFileInformationByHandleEx.argtypes = [
        wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD,
    ]
    kernel32.GetFileInformationByHandleEx.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    ntdll.NtCreateFile.argtypes = [
        ctypes.POINTER(wintypes.HANDLE), wintypes.ULONG,
        ctypes.POINTER(_ObjectAttributes), ctypes.POINTER(_IoStatusBlock),
        ctypes.c_void_p, wintypes.ULONG, wintypes.ULONG, wintypes.ULONG,
        wintypes.ULONG, ctypes.c_void_p, wintypes.ULONG,
    ]
    ntdll.NtCreateFile.restype = ctypes.c_long
    ntdll.RtlNtStatusToDosError.argtypes = [ctypes.c_long]
    ntdll.RtlNtStatusToDosError.restype = wintypes.ULONG
    return kernel32, ntdll


def _attributes(kernel32, handle) -> int:
    info = _FileAttributeTagInfo()
    if not kernel32.GetFileInformationByHandleEx(
        handle, FILE_ATTRIBUTE_TAG_INFO_CLASS, ctypes.byref(info), ctypes.sizeof(info)
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    return int(info.FileAttributes)


def _check_type(kernel32, handle, *, directory: bool) -> None:
    attributes = _attributes(kernel32, handle)
    if attributes & FILE_ATTRIBUTE_REPARSE_POINT:
        raise UnsafeWindowsPath("Reparse points are not followed")
    if bool(attributes & FILE_ATTRIBUTE_DIRECTORY) != directory:
        raise UnsafeWindowsPath("Filesystem object has an unexpected type")


def _open_child(kernel32, ntdll, parent, name: str, *, directory: bool):
    if not name or "\\" in name or "/" in name or name in {".", ".."}:
        raise UnsafeWindowsPath("Invalid path component")
    name_buffer = ctypes.create_unicode_buffer(name)
    name_bytes = len(name.encode("utf-16-le"))
    unicode_name = _UnicodeString(
        Length=name_bytes,
        MaximumLength=name_bytes + 2,
        Buffer=ctypes.cast(name_buffer, wintypes.LPWSTR),
    )
    object_attributes = _ObjectAttributes(
        Length=ctypes.sizeof(_ObjectAttributes),
        RootDirectory=parent,
        ObjectName=ctypes.pointer(unicode_name),
        Attributes=OBJ_CASE_INSENSITIVE,
        SecurityDescriptor=None,
        SecurityQualityOfService=None,
    )
    io_status = _IoStatusBlock()
    child = wintypes.HANDLE()
    access = FILE_READ_ATTRIBUTES | SYNCHRONIZE
    options = FILE_SYNCHRONOUS_IO_NONALERT | 0x00200000
    if directory:
        access |= FILE_LIST_DIRECTORY
        options |= FILE_DIRECTORY_FILE
    else:
        access |= FILE_READ_DATA
        options |= FILE_NON_DIRECTORY_FILE
    status = ntdll.NtCreateFile(
        ctypes.byref(child), access, ctypes.byref(object_attributes),
        ctypes.byref(io_status), None, 0,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        FILE_OPEN, options, None, 0,
    )
    if status < 0:
        unsigned_status = status & 0xFFFFFFFF
        # STATUS_FILE_IS_A_DIRECTORY is returned when FILE_NON_DIRECTORY_FILE
        # is used against a directory. Preserve a useful, stable Python error.
        if unsigned_status == 0xC00000BA:
            raise IsADirectoryError("Requested path is not a regular file")
        if unsigned_status == 0xC0000103:
            raise NotADirectoryError("A parent path component is not a directory")
        raise ctypes.WinError(ntdll.RtlNtStatusToDosError(status))
    try:
        _check_type(kernel32, child, directory=directory)
        return child
    except Exception:
        kernel32.CloseHandle(child)
        raise


def open_readonly_file(root: str | Path, parts: tuple[str, ...]) -> tuple[int, os.stat_result]:
    """Open a regular file beneath root using held parent-directory handles."""
    if os.name != "nt":
        raise OSError("Native Windows file handles are only available on Windows")
    if not parts:
        raise UnsafeWindowsPath("A file path is required")
    kernel32, ntdll = _apis()
    root_handle = kernel32.CreateFileW(
        str(root),
        FILE_LIST_DIRECTORY | FILE_READ_ATTRIBUTES | SYNCHRONIZE,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        None, OPEN_EXISTING,
        FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT,
        None,
    )
    if root_handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())

    directories = []
    file_handle = None
    try:
        _check_type(kernel32, root_handle, directory=True)
        parent = root_handle
        for component in parts[:-1]:
            child = _open_child(kernel32, ntdll, parent, component, directory=True)
            directories.append(child)
            parent = child
        file_handle = _open_child(
            kernel32, ntdll, parent, parts[-1], directory=False
        )
        descriptor = msvcrt.open_osfhandle(
            int(file_handle.value), os.O_RDONLY | getattr(os, "O_BINARY", 0)
        )
        file_handle = None  # The CRT descriptor now owns this handle.
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise UnsafeWindowsPath("Opened object is not a regular file")
            return descriptor, metadata
        except Exception:
            os.close(descriptor)
            raise
    finally:
        if file_handle is not None:
            kernel32.CloseHandle(file_handle)
        for handle in reversed(directories):
            kernel32.CloseHandle(handle)
        kernel32.CloseHandle(root_handle)


# FILE_INFO_BY_HANDLE_CLASS values from winbase.h.
_FILE_ID_BOTH_DIRECTORY_INFO = 10
_FILE_ID_BOTH_DIRECTORY_RESTART_INFO = 11
_ERROR_NO_MORE_FILES = 18
_DIRECTORY_ENTRY_FIXED_SIZE = 104


class _FileIdBothDirInfo(ctypes.Structure):
    _fields_ = [
        ("NextEntryOffset", wintypes.DWORD),
        ("FileIndex", wintypes.DWORD),
        ("CreationTime", ctypes.c_longlong),
        ("LastAccessTime", ctypes.c_longlong),
        ("LastWriteTime", ctypes.c_longlong),
        ("ChangeTime", ctypes.c_longlong),
        ("EndOfFile", ctypes.c_longlong),
        ("AllocationSize", ctypes.c_longlong),
        ("FileAttributes", wintypes.DWORD),
        ("FileNameLength", wintypes.DWORD),
        ("EaSize", wintypes.DWORD),
        ("ShortNameLength", ctypes.c_byte),
        ("ShortName", wintypes.WCHAR * 12),
        ("FileId", ctypes.c_longlong),
        ("FileName", wintypes.WCHAR * 1),
    ]


def open_directory_handle(path: str | Path):
    """Open a selected directory without following its final reparse point."""
    if os.name != "nt":
        raise OSError("Native Windows handles are only available on Windows")
    kernel32, _ = _apis()
    handle = kernel32.CreateFileW(
        str(path),
        FILE_LIST_DIRECTORY | FILE_READ_ATTRIBUTES | SYNCHRONIZE,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        None, OPEN_EXISTING,
        FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT,
        None,
    )
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        _check_type(kernel32, handle, directory=True)
        return kernel32, handle
    except Exception:
        kernel32.CloseHandle(handle)
        raise


def open_child_directory_handle(parent, name: str):
    """Open one child directory relative to a held parent handle."""
    kernel32, ntdll = _apis()
    return _open_child(kernel32, ntdll, parent, name, directory=True)


def close_directory_handle(kernel32, handle) -> None:
    """Close a native directory handle."""
    if handle and not kernel32.CloseHandle(handle):
        raise ctypes.WinError(ctypes.get_last_error())


def iter_directory_entries(handle):
    """Yield (name, attributes, size) from a held directory handle.

    The enumeration cursor belongs to this handle. No child path is resolved
    during enumeration. Reparse points are reported as attributes so callers
    can skip them before attempting to descend.
    """
    kernel32, _ = _apis()
    kernel32.GetFileInformationByHandleEx.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
    ]
    kernel32.GetFileInformationByHandleEx.restype = wintypes.BOOL
    buffer = ctypes.create_string_buffer(64 * 1024)
    first = True

    while True:
        info_class = (
            _FILE_ID_BOTH_DIRECTORY_RESTART_INFO
            if first else _FILE_ID_BOTH_DIRECTORY_INFO
        )
        success = kernel32.GetFileInformationByHandleEx(
            handle, info_class, ctypes.byref(buffer), ctypes.sizeof(buffer)
        )
        if not success:
            error = ctypes.get_last_error()
            if error in {_ERROR_NO_MORE_FILES, 2}:
                return
            raise ctypes.WinError(error)
        first = False

        offset = 0
        while True:
            if offset + _DIRECTORY_ENTRY_FIXED_SIZE > ctypes.sizeof(buffer):
                raise OSError("Invalid Windows directory enumeration buffer")
            address = ctypes.addressof(buffer) + offset
            entry = ctypes.cast(
                address, ctypes.POINTER(_FileIdBothDirInfo)
            ).contents
            name_length = int(entry.FileNameLength)
            name_offset = _DIRECTORY_ENTRY_FIXED_SIZE
            if (
                name_length % 2
                or offset + name_offset + name_length > ctypes.sizeof(buffer)
            ):
                raise OSError("Invalid Windows directory entry name length")
            name = ctypes.wstring_at(address + name_offset, name_length // 2)
            yield name, int(entry.FileAttributes), max(0, int(entry.EndOfFile))
            next_offset = int(entry.NextEntryOffset)
            if next_offset == 0:
                break
            if (
                next_offset < _DIRECTORY_ENTRY_FIXED_SIZE
                or offset + next_offset >= ctypes.sizeof(buffer)
            ):
                raise OSError("Invalid Windows directory entry offset")
            offset += next_offset


def read_child_text(parent, name: str, *, max_bytes: int = 1_000_000) -> str | None:
    """Read a small UTF-8 file relative to a held directory handle.

    Missing, reparse-point, non-regular, oversized and non-UTF-8 files are
    treated as unavailable metadata (for example, an unsafe .gitignore).
    """
    kernel32, ntdll = _apis()
    handle = None
    descriptor = None
    try:
        handle = _open_child(kernel32, ntdll, parent, name, directory=False)
        descriptor = msvcrt.open_osfhandle(
            int(handle.value), os.O_RDONLY | getattr(os, "O_BINARY", 0)
        )
        handle = None  # The descriptor owns the native handle.
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > max_bytes:
            return None
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            data = stream.read(max_bytes + 1)
        if len(data) > max_bytes or b"\x00" in data:
            return None
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return None
    except (OSError, UnsafeWindowsPath):
        return None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if handle is not None:
            kernel32.CloseHandle(handle)


def open_readonly_file_from_handle(
    root_handle, parts: tuple[str, ...]
) -> tuple[int, os.stat_result]:
    """Open a workspace file relative to an already-authorized root handle."""
    if os.name != "nt":
        raise OSError("Native Windows file handles are only available on Windows")
    if not parts:
        raise UnsafeWindowsPath("A file path is required")
    kernel32, ntdll = _apis()
    directories = []
    file_handle = None
    try:
        _check_type(kernel32, root_handle, directory=True)
        parent = root_handle
        for component in parts[:-1]:
            child = _open_child(kernel32, ntdll, parent, component, directory=True)
            directories.append(child)
            parent = child
        file_handle = _open_child(kernel32, ntdll, parent, parts[-1], directory=False)
        descriptor = msvcrt.open_osfhandle(
            int(file_handle.value), os.O_RDONLY | getattr(os, "O_BINARY", 0)
        )
        file_handle = None
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise UnsafeWindowsPath("Opened object is not a regular file")
            return descriptor, metadata
        except Exception:
            os.close(descriptor)
            raise
    finally:
        if file_handle is not None:
            kernel32.CloseHandle(file_handle)
        for handle in reversed(directories):
            kernel32.CloseHandle(handle)
