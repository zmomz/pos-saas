"""ISSUE-098 — clean the atoms.dev/MGX scaffold residue in services/storage.py.

#30 decided to KEEP the storage service (make-it-work), so the residue is cleaned
in place rather than deleted. The leftover scaffold smells were:

  * a Chinese docstring (``统一的 OSS 服务请求方法``) on the request helper,
  * a wrong return annotation on ``rename_object`` (``-> dict`` while it returns a
    ``RenameResponse``),
  * copy-paste log strings — ``delete_object`` logged "Failed to rename object"
    and ``create_download_url`` logged "Failed to create upload URL".

These guards keep the residue from creeping back.
"""
import inspect
from pathlib import Path

from schemas.storage import RenameResponse
from services.storage import StorageService

_SOURCE = Path(__file__).resolve().parents[1] / "services" / "storage.py"


def _source() -> str:
    return _SOURCE.read_text(encoding="utf-8")


def test_no_cjk_residue_in_storage_source():
    """No CJK (Chinese/Japanese/Korean) characters remain in the module — the
    scaffold's Chinese comments are translated to English."""
    cjk = [ch for ch in _source() if "一" <= ch <= "鿿"]
    assert not cjk, f"CJK residue still present in services/storage.py: {''.join(cjk)!r}"


def test_rename_object_return_annotation_is_rename_response():
    """``rename_object`` returns a ``RenameResponse`` — its annotation must match,
    not the leftover ``dict``."""
    assert inspect.signature(StorageService.rename_object).return_annotation is RenameResponse


def test_log_strings_are_not_copy_pasted():
    """``delete_object`` / ``create_download_url`` log their own operation, not the
    copy-pasted "rename"/"upload" strings."""
    src = _source()
    delete_src = src.split("async def delete_object", 1)[1].split("async def ", 1)[0]
    assert "Failed to rename object" not in delete_src
    assert "Failed to delete object" in delete_src

    download_src = src.split("async def create_download_url", 1)[1].split("async def ", 1)[0]
    assert "Failed to create upload URL" not in download_src
    assert "Failed to create download URL" in download_src
