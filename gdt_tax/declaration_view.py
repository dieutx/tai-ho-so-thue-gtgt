"""XML chính của một hồ sơ đã tải, tách ra từ ZIP gốc khi người dùng bấm "Xem file".

ZIP gốc chỉ được đọc: không đổi byte, không đổi tên, không thay evidence/hash hiện có.
XML tách ra là derived artifact đặt cạnh ZIP và gắn với nội dung ZIP qua hash trong
tên tệp, nên lần sau mở lại dùng đúng tệp đã tách mà không giải nén lại.

Không dùng ``extractall``: mọi member được kiểm tra (đường dẫn tuyệt đối, ``..``,
ổ đĩa/UNC, symlink), giới hạn dung lượng/số member/tỉ lệ nén lấy từ
:mod:`gdt_tax.archive_limits`, và chỉ XML đã qua :func:`gdt_tax.integrity.validate_xml`
mới được chấp nhận. ZIP có nhiều XML cùng loại sẽ báo mơ hồ thay vì tự chọn bừa.
"""
from __future__ import annotations

import hashlib
import re
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path, PurePosixPath

from .archive_limits import MAX_ARCHIVE_BYTES
from .atomic import replace_with_retry
from .integrity import read_bounded, validate_xml

#: Tờ khai được ưu tiên hơn thông báo khi ZIP chứa cả hai loại tài liệu.
KIND_PRIORITY = ("declaration", "notice")
_DRIVE = re.compile(r"^[A-Za-z]:")


class DeclarationViewError(Exception):
    """Lỗi có mã để UI hiển thị đúng và không mở sai tệp."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def declaration_xml(path: str | Path) -> Path:
    """Trả về đường dẫn XML chính của hồ sơ đã tải; tách một lần rồi dùng lại.

    ``path`` là ZIP đã tải (hoặc tệp XML có sẵn). ZIP gốc không bị sửa đổi.
    """
    source = Path(path)
    if source.suffix.lower() == ".xml":
        if source.is_file():
            return source
        raise DeclarationViewError("XML_MISSING", "Tệp XML không còn tồn tại; hãy kiểm tra nơi lưu.")
    if not source.is_file():
        raise DeclarationViewError("FILE_MISSING", "Tệp hồ sơ đã bị xóa hoặc di chuyển; hãy kiểm tra nơi lưu.")
    data = read_bounded(source, MAX_ARCHIVE_BYTES)
    derived = source.with_name(f"{source.stem}.{hashlib.sha256(data).hexdigest()[:12]}.xml")
    if derived.is_file() and derived.stat().st_size > 0:
        return derived
    member, payload = _primary_xml(data)
    _write_atomic(derived, payload)
    return derived


def _primary_xml(data: bytes) -> tuple[str, bytes]:
    """Chọn đúng một XML chính; sai/thiếu/mơ hồ đều là lỗi có mã."""
    from .storage import valid_zip

    if not valid_zip(data):
        raise DeclarationViewError(
            "ZIP_UNSAFE_OR_INVALID",
            "Tệp đã tải không phải ZIP hợp lệ hoặc vượt giới hạn an toàn; hãy tải lại hồ sơ.",
        )
    try:
        archive = zipfile.ZipFile(BytesIO(data))
    except (zipfile.BadZipFile, OSError) as error:  # pragma: no cover - valid_zip đã chặn
        raise DeclarationViewError("ZIP_INVALID", "Tệp đã tải không đọc được như ZIP.") from error
    found: list[tuple[int, str, bytes]] = []
    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            pure = PurePosixPath(name)
            unsafe = (pure.is_absolute() or ".." in pure.parts or _DRIVE.match(name)
                      or name.startswith("//") or (info.external_attr >> 16) & 0o170000 == 0o120000)
            if unsafe:
                raise DeclarationViewError(
                    "ZIP_UNSAFE_MEMBER",
                    "ZIP chứa đường dẫn không an toàn; không giải nén tệp này.",
                )
            if not name.lower().endswith(".xml"):
                continue
            payload = archive.read(info)
            for priority, kind in enumerate(KIND_PRIORITY):
                if validate_xml(payload, kind).ok:
                    found.append((priority, name, payload))
                    break
    if not found:
        raise DeclarationViewError(
            "ZIP_DOCUMENT_KIND_MISSING",
            "ZIP không chứa XML tờ khai/thông báo đã kiểm chứng; hãy mở thư mục để xem tệp đã tải.",
        )
    best = min(priority for priority, _, _ in found)
    primary = [(name, payload) for priority, name, payload in found if priority == best]
    if len(primary) > 1:
        names = ", ".join(name for name, _ in sorted(primary))
        raise DeclarationViewError(
            "ZIP_AMBIGUOUS_DOCUMENTS",
            f"ZIP có nhiều XML cùng loại ({names}); mở thư mục để chọn đúng tệp cần xem.",
        )
    return primary[0]


def _write_atomic(path: Path, data: bytes) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.",
                                         suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
        replace_with_retry(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


__all__ = ["DeclarationViewError", "declaration_xml"]
