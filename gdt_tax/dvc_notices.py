"""Thông báo đính kèm hồ sơ Dịch vụ công (tiếp nhận / chấp nhận / không chấp nhận).

Trang chi tiết hồ sơ DVC (``/tchs/files/detail/<mã hồ sơ>``) chứa modal
``#modalThongBao`` với danh sách thông báo của cơ quan thuế. Mỗi thông báo có
một liên kết ``downloadThongBao(this)`` mang ``data-id``; tải bằng
``POST /tchs/downloadthongbao`` (JSON ``{"idTbao": ..., "loaiTBao": ""}``,
header ``X-XSRF-TOKEN``). Cổng trả JSON::

    {"fileName": "Thong bao_10820260069828466.xml",
     "fileType": "xml",
     "content": "<base64>"}

Module này chỉ đọc/tải và lưu tệp; không parse nội dung văn bản.
"""

from __future__ import annotations

import base64
import logging
import os
import re
import tempfile
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup

from .atomic import replace_with_retry
from .errors import StorageError
from .identity import UNKNOWN, AttachmentKey, RecordKey
from .integrity import (
    matches_evidence,
    read_bounded,
    safe_destination,
    validate_pdf,
    validate_tax_zip,
    validate_xml,
    write_evidence,
)
from .naming import safe_filename_part

LOGGER_NAME = "gdt_tax.dvc_notices"
#: Tên thư mục con trong nơi lưu, mỗi hồ sơ một thư mục.
NOTICE_DIRECTORY = "thong-bao-dinh-kem"
#: Chặn tệp quá lớn trước khi ghi ra đĩa.
MAX_NOTICE_BYTES = 64 * 1024 * 1024
LOAI_TIEP_NHAN = "tiep-nhan"
LOAI_CHAP_NHAN = "chap-nhan"
LOAI_KHONG_CHAP_NHAN = "khong-chap-nhan"
LOAI_KHAC = "khac"
_DATE = re.compile(r"\b\d{1,2}:\d{2}\s+\d{1,2}/\d{1,2}/\d{4}\b")
_SPECIAL_LETTERS = str.maketrans({"đ": "d", "Đ": "D", "ð": "d", "Ð": "D"})


@dataclass
class DvcNotice:
    """Một thông báo đính kèm của hồ sơ DVC."""

    id: str
    title: str = ""
    sent_at: str = ""
    #: Liên kết dùng endpoint ``downloadthongbao-tdt`` thay vì ``downloadthongbao``.
    is_tdt: bool = False
    loai_tra_cuu: str = ""
    loai_tbao: str = ""

    def key(self, parent: RecordKey) -> AttachmentKey:
        return AttachmentKey(parent, ("legacy" if parent.source == "ETAX_LEGACY" else "tdt" if self.is_tdt else "dvc"), self.id,
                             self.loai_tra_cuu, self.loai_tbao)

    @property
    def loai(self) -> str:
        """Nhóm thông báo theo tiêu đề: tiếp nhận / chấp nhận / không chấp nhận."""
        text = _fold(self.title)
        if "tiep nhan" in text or "tiep nhan ho so" in text:
            return LOAI_TIEP_NHAN
        if "chap nhan/khong chap nhan" in text:
            return LOAI_KHAC
        if "khong chap nhan" in text or "khong duoc chap nhan" in text:
            return LOAI_KHONG_CHAP_NHAN
        if "chap nhan" in text or "xac nhan" in text:
            return LOAI_CHAP_NHAN
        return LOAI_KHAC


@dataclass
class NoticeFile:
    """Nội dung tải về của một thông báo."""

    file_name: str
    data: bytes
    file_type: str = ""

    @property
    def extension(self) -> str:
        suffix = Path(self.file_name).suffix.lstrip(".").lower()
        if re.fullmatch(r"[a-z0-9]{1,8}", self.file_type.lower()):
            return self.file_type.lower()
        if re.fullmatch(r"[a-z0-9]{1,8}", suffix):
            return suffix
        if self.data.lstrip()[:5] == b"%PDF-":
            return "pdf"
        if self.data.startswith(b"PK"):
            return "zip"
        if self.data.lstrip().startswith(b"<"):
            return "xml"
        return "bin"


def _fold(value: str) -> str:
    text = (value or "").translate(_SPECIAL_LETTERS)
    text = unicodedata.normalize("NFKD", text)
    return "".join(char for char in text if not unicodedata.combining(char)).casefold()


def _truthy(value) -> bool:
    return str(value or "").strip().casefold() not in {"", "0", "false", "none"}


@dataclass
class NoticeList:
    notices: list[DvcNotice] = field(default_factory=list)
    status: str = 'SCHEMA_UNKNOWN'


def parse_notice_list(html: str) -> NoticeList:
    """Đọc danh sách thông báo trong modal ``#modalThongBao`` của trang chi tiết."""
    if not html:
        return NoticeList()
    soup = BeautifulSoup(html, "lxml")
    modals = soup.select('#modalThongBao')
    if len(modals) != 1:
        return NoticeList()
    scope = modals[0]
    notices: list[DvcNotice] = []
    seen: set[tuple] = set()
    malformed = False
    for anchor in scope.find_all("a"):
        notice_id = str(anchor.get("data-id") or "").strip()
        candidate = notice_id or 'downloadThongBao' in str(anchor.get('onclick') or '')
        if not notice_id or "downloadThongBao" not in str(anchor.get("onclick") or ""):
            malformed = malformed or bool(candidate)
            continue
        key = (notice_id, _truthy(anchor.get('data-is-thue-dien-tu')),
               str(anchor.get('data-loaitracuu') or ''),
               str(anchor.get('data-loai-tbao') or anchor.get('data-loaibao') or ''))
        if key in seen:
            continue
        seen.add(key)
        row = anchor.find_parent("div", class_="row") or anchor.parent
        title, sent_at = _notice_text(row)
        notices.append(
            DvcNotice(
                id=notice_id,
                title=title,
                sent_at=sent_at,
                is_tdt=_truthy(anchor.get("data-is-thue-dien-tu")),
                loai_tra_cuu=str(anchor.get("data-loaitracuu") or "").strip(),
                loai_tbao=str(anchor.get("data-loai-tbao") or anchor.get("data-loaibao") or "").strip(),
            )
        )
    empty = ('khong co thong bao' in _fold(scope.get_text(' ', strip=True))
             or scope.get('data-empty') == 'true')
    return NoticeList(notices, 'PARSED' if notices and not malformed and not empty
                      else 'EMPTY_CONFIRMED' if empty and not notices and not malformed else 'SCHEMA_UNKNOWN')


def parse_notices(html: str) -> list[DvcNotice]:
    """Compatibility reader; orchestration must use the completeness result."""
    return parse_notice_list(html).notices


def _notice_text(row) -> tuple[str, str]:
    if row is None:
        return "", ""
    title = ""
    block = row.select_one(".fw-bold")
    if block is not None:
        title = block.get_text(" ", strip=True)
    sent_at = ""
    column = row.select_one(".col-md-9") or row
    for element in column.find_all("div", recursive=False):
        text = element.get_text(" ", strip=True)
        if _DATE.search(text):
            sent_at = text
            break
    if not title:
        texts = [d.get_text(" ", strip=True) for d in column.find_all("div", recursive=False)]
        title = next((text for text in texts if text and not _DATE.search(text)), "")
    return re.sub(r"(?i)^v/v\s*:\s*", "", title).strip(), sent_at


def notice_filename(case_id: str | RecordKey, notice: DvcNotice, extension: str) -> str:
    """Tên tệp ổn định, bắt đầu bằng ``messageId`` để lần sau bỏ qua tệp đã có."""
    parts = [
        safe_filename_part(notice.id, 50),
        safe_filename_part(notice.loai, 30),
        safe_filename_part(_parent_key(case_id).remote_id, 40),
    ]
    if notice.title:
        parts.append(safe_filename_part(notice.title, 60))
    suffix = extension if re.fullmatch(r"[a-z0-9]{1,8}", extension.lower()) else "bin"
    return "__".join(parts) + f".{suffix.lower()}"


def decode_notice_response(response) -> NoticeFile | None:
    """Giải mã phản hồi tải thông báo (JSON base64 hoặc tệp nhị phân trực tiếp)."""
    if response is None or getattr(response, "status_code", 0) != 200:
        return None
    if len(getattr(response, "content", b"")) > (MAX_NOTICE_BYTES + 2) // 3 * 4 + 4096:
        return None
    file_name = ""
    file_type = ""
    data = b""
    payload = None
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        if not payload.get("content"):
            return None
        if not isinstance(payload["content"], str) or len(payload["content"]) > (MAX_NOTICE_BYTES + 2) // 3 * 4:
            return None
        try:
            encoded = "".join(str(payload["content"]).split())
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError):
            return None
        file_name = str(payload.get("fileName") or "")
        file_type = str(payload.get("fileType") or "")
    else:
        data = bytes(getattr(response, "content", b"") or b"")
        stripped = data.lstrip()
        if not (stripped[:5] == b"%PDF-" or data.startswith(b"PK") or stripped.startswith(b"<")):
            return None
    if not data or len(data) > MAX_NOTICE_BYTES:
        return None
    result = validate_notice(data)
    actual_type = "xml" if result.kind == "notice" else result.kind
    if not result.ok or file_type and file_type.lower() != actual_type:
        return None
    return NoticeFile(file_name=file_name, data=data, file_type=actual_type)


def validate_notice(data: bytes):
    if data.startswith(b"%PDF-"):
        return validate_pdf(data)
    if data.startswith(b"PK"):
        return validate_tax_zip(data, required_kind="notice")
    return validate_xml(data, "notice")


def _parent_key(case_id: str | RecordKey) -> RecordKey:
    return case_id if isinstance(case_id, RecordKey) else RecordKey(UNKNOWN, UNKNOWN, "DECLARATION", case_id)


def notice_source(case_id: str | RecordKey, notice: DvcNotice) -> dict:
    parent = _parent_key(case_id)
    return {"parent_remote_id": parent.remote_id, "parent_record_key": parent.serialize(),
            "record_key": notice.key(parent).serialize(), "source": notice.key(parent).source,
            "kind": "attachment", "remote_id": notice.id,
            "loai_tra_cuu": notice.loai_tra_cuu, "loai_tbao": notice.loai_tbao,
            "account_key": parent.account_key}


class NoticeStore:
    """Lưu tệp thông báo đính kèm theo từng hồ sơ."""

    def __init__(self, root: str | Path, logger: logging.Logger | None = None) -> None:
        self.root = Path(root)
        self.logger = logger or logging.getLogger(LOGGER_NAME)

    def directory_for(self, case_id: str | RecordKey) -> Path:
        return self.root / safe_filename_part(_parent_key(case_id).remote_id, 60)

    def find_existing(self, case_id: str | RecordKey, notice_id: str | DvcNotice) -> Path | None:
        # A bare ID has no route provenance; it cannot safely select an attachment.
        if isinstance(notice_id, str):
            return None
        notice = notice_id
        directory = self.directory_for(case_id)
        if not directory.is_dir():
            return None
        prefix = safe_filename_part(notice.id, 50) + "__"
        for path in directory.glob(prefix + "*"):
            try:
                if not path.is_file():
                    continue
                data = read_bounded(path, MAX_NOTICE_BYTES)
                if validate_notice(data).ok and matches_evidence(path, data, notice_source(case_id, notice), require=True):
                    return path
            except OSError:
                continue
        return None

    def save(self, case_id: str | RecordKey, notice: DvcNotice, payload: NoticeFile) -> Path | None:
        result = validate_notice(payload.data)
        if not result.ok:
            self.logger.error("ATTACHMENT_%s: %s", result.code, notice.id)
            return None
        directory = self.directory_for(case_id)
        directory.mkdir(parents=True, exist_ok=True)
        extension = "xml" if result.kind == "notice" else result.kind
        path = safe_destination(directory / notice_filename(case_id, notice, extension),
                                payload.data, notice_source(case_id, notice))
        try:
            _atomic_write(path, payload.data)
            write_evidence(path, result, notice_source(case_id, notice))
        except StorageError as error:
            self.logger.error("Không ghi được thông báo %s: %s", notice.id, error)
            return None
        self.logger.info("Đã lưu thông báo đính kèm %s (%s bytes)", path.name, f"{len(payload.data):,}")
        return path


def _atomic_write(path: Path, data: bytes) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.",
                                         suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        replace_with_retry(temporary, path)
    except OSError as error:
        raise StorageError(f"Không ghi được {path}: {error}") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


__all__ = [
    "DvcNotice",
    "NoticeFile",
    "NoticeStore",
    "MAX_NOTICE_BYTES",
    "NOTICE_DIRECTORY",
    "decode_notice_response",
    "notice_filename",
    "parse_notices",
]
