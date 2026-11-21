import pytest

from odei_api.services.patch_proposals import (
    MAX_FILE_BYTES,
    PatchProposalError,
    build_patch_proposal,
    sha256_text,
)


def test_builds_create_update_and_delete_review_changes() -> None:
    base = {"src/main.py": "print('old')\n", "obsolete.txt": "remove me\n"}
    changes = {
        "src/main.py": "print('new')\n",
        "docs/NEW.md": "# New\n",
        "obsolete.txt": None,
    }
    hashes = {
        "src/main.py": sha256_text(base["src/main.py"]),
        "docs/NEW.md": None,
        "obsolete.txt": sha256_text(base["obsolete.txt"]),
    }

    proposal = build_patch_proposal(base, changes, hashes)

    assert [item.operation for item in proposal.files] == ["create", "delete", "update"]
    assert {item.path for item in proposal.files} == set(changes)
    update = next(item for item in proposal.files if item.path == "src/main.py")
    assert update.base_sha256 == hashes["src/main.py"]
    assert update.result_sha256 == sha256_text(changes["src/main.py"])
    assert "-print('old')" in update.unified_diff
    assert "+print('new')" in update.unified_diff
    assert proposal.total_content_bytes == len("# New\nprint('new')\n".encode())


def test_rejects_stale_base_hash() -> None:
    with pytest.raises(PatchProposalError, match="Base hash mismatch"):
        build_patch_proposal(
            {"app.py": "old"},
            {"app.py": "new"},
            {"app.py": "0" * 64},
        )


@pytest.mark.parametrize(
    "path",
    [
        "../outside.txt",
        "/etc/passwd",
        "C:/Windows/win.ini",
        "src\\main.py",
        ".env",
        "config/credentials.json",
        "certs/private.pem",
        "node_modules/pkg/index.js",
    ],
)
def test_rejects_unsafe_or_sensitive_paths(path: str) -> None:
    with pytest.raises(PatchProposalError):
        build_patch_proposal({}, {path: "content"}, {path: None})


def test_rejects_case_insensitive_duplicates() -> None:
    with pytest.raises(PatchProposalError, match="duplicate"):
        build_patch_proposal(
            {},
            {"src/App.py": "a", "src/app.py": "b"},
            {"src/App.py": None, "src/app.py": None},
        )


def test_rejects_file_directory_collisions() -> None:
    with pytest.raises(PatchProposalError, match="parent directory"):
        build_patch_proposal(
            {},
            {"src": "file", "src/main.py": "child"},
            {"src": None, "src/main.py": None},
        )


def test_rejects_delete_of_missing_file() -> None:
    with pytest.raises(PatchProposalError, match="cannot be deleted"):
        build_patch_proposal({}, {"missing.txt": None}, {"missing.txt": None})


def test_rejects_binary_content() -> None:
    with pytest.raises(PatchProposalError, match="Binary content"):
        build_patch_proposal({}, {"image.txt": "a\x00b"}, {"image.txt": None})


def test_rejects_oversized_file() -> None:
    with pytest.raises(PatchProposalError, match="1 MB"):
        build_patch_proposal(
            {},
            {"large.txt": "x" * (MAX_FILE_BYTES + 1)},
            {"large.txt": None},
        )


def test_requires_exact_expected_hash_set() -> None:
    with pytest.raises(PatchProposalError, match="exactly one"):
        build_patch_proposal({}, {"new.txt": "text"}, {})


def test_rejects_more_than_twenty_file_changes() -> None:
    changes = {"file-%02d.txt" % index: "x" for index in range(21)}
    hashes = {path: None for path in changes}
    with pytest.raises(PatchProposalError, match="between 1 and 20"):
        build_patch_proposal({}, changes, hashes)


def test_rejects_new_file_when_base_has_parent_file() -> None:
    with pytest.raises(PatchProposalError, match="existing file as a parent"):
        build_patch_proposal(
            {"src": "existing file"},
            {"src/main.py": "child"},
            {"src/main.py": None},
        )


def test_rejects_file_when_base_has_descendant_files() -> None:
    with pytest.raises(PatchProposalError, match="replace an existing directory"):
        build_patch_proposal(
            {"src/main.py": "existing child"},
            {"src": "new file"},
            {"src": None},
        )


def test_rejects_oversized_base_snapshot_file() -> None:
    with pytest.raises(PatchProposalError, match="base file exceeds"):
        build_patch_proposal(
            {"large.txt": "x" * (MAX_FILE_BYTES + 1)},
            {"large.txt": "small"},
            {"large.txt": sha256_text("x" * (MAX_FILE_BYTES + 1))},
        )


def test_rejects_invalid_unicode_surrogates() -> None:
    with pytest.raises(PatchProposalError, match="valid UTF-8"):
        build_patch_proposal({}, {"new.txt": "\ud800"}, {"new.txt": None})


@pytest.mark.parametrize(
    "path",
    ["file.txt:secret", "CON", "NUL.txt", "folder/trailing. ", "bad|name.txt"],
)
def test_rejects_windows_reserved_path_components(path: str) -> None:
    with pytest.raises(PatchProposalError):
        build_patch_proposal({}, {path: "content"}, {path: None})


@pytest.mark.parametrize(
    "path",
    ["COM1.txt", "LPT9", "COM¹.log", "name" + "x" * 255 + ".txt"],
)
def test_rejects_windows_device_aliases_and_oversized_components(path: str) -> None:
    with pytest.raises(PatchProposalError):
        build_patch_proposal({}, {path: "content"}, {path: None})


def test_rejects_non_nfc_unicode_paths() -> None:
    decomposed = "cafe\\u0301.txt"
    with pytest.raises(PatchProposalError, match="Unicode NFC"):
        build_patch_proposal({}, {decomposed: "content"}, {decomposed: None})
