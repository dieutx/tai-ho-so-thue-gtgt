"""Hợp đồng nghiệp vụ cho tờ khai, phản hồi CQT, thông báo thuế và tệp.

Đây là **logical model** theo MASTER_PLAN §4, không phải bảng DB. Mọi hàm ở
module này chỉ ánh xạ dữ liệu đã có (row ``dict`` của desktop hoặc ``notice``
do :func:`desktop.notices.read_notices` trả về) sang thực thể và quy tắc trạng
thái. Không gọi mạng, không đọc/ghi tệp, không tự bịa số/ngày/kết quả.

Bốn thực thể và khóa ổn định:

``DeclarationSubmission``
    Một hồ sơ/lần nộp. ``submission_key`` = tổ hợp có namespace
    ``taxpayer → source → mã hồ sơ → lần nộp/bổ sung``. Trong checkout gốc,
    mã hồ sơ (``ma_ho_so``) là khóa thực tế trong phạm vi thư mục tài khoản;
    composite key vẫn tách được hai lần nộp cùng kỳ hoặc cùng mã khác nguồn.

``SubmissionFeedback``
    Phản hồi CQT gắn với **một** ``submission_key``. ``feedback_key`` lấy từ
    ``reference_key`` (sidecar) nếu có, nếu không dùng ``relative_path`` của
    tệp — không dùng chỉ số hàng đang hiển thị.

``TaxNotice``
    Thông báo thuế độc lập của tab "Thông báo thuế". Không bao giờ được tạo
    từ phản hồi tờ khai và không tự gắn sang tờ khai chỉ vì trùng MST/kỳ/ngày.

``DocumentAsset``
    Tệp thực tế, có ``owner_kind`` + ``owner_key`` + ``asset_key`` để không
    lấy nhầm tài liệu giữa hai tab.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .notices import ACCEPTED, RECEIVED, REJECTED

# --- Trạng thái nghiệp vụ của CQT (độc lập với trạng thái tải tệp) ---
BUSINESS_NONE = "none"
BUSINESS_UNKNOWN = "unknown"
BUSINESS_RECEIVED = RECEIVED
BUSINESS_ACCEPTED = ACCEPTED
BUSINESS_REJECTED = REJECTED
BUSINESS_LABELS = {
    BUSINESS_NONE: "Chưa có phản hồi trong dữ liệu hiện có",
    BUSINESS_UNKNOWN: "Chưa xác định",
    BUSINESS_RECEIVED: "Đã tiếp nhận",
    BUSINESS_ACCEPTED: "Đã chấp nhận",
    BUSINESS_REJECTED: "Không chấp nhận",
}

# --- Trạng thái tải tệp (độc lập) ---
DOWNLOAD_NOT_DOWNLOADED = "not_downloaded"
DOWNLOAD_QUEUED = "queued"
DOWNLOADING = "downloading"
DOWNLOAD_DOWNLOADED = "downloaded"
DOWNLOAD_FAILED = "failed"
DOWNLOAD_SKIPPED = "skipped"
DOWNLOAD_STATUSES = frozenset({
    DOWNLOAD_NOT_DOWNLOADED, DOWNLOAD_QUEUED, DOWNLOADING,
    DOWNLOAD_DOWNLOADED, DOWNLOAD_FAILED, DOWNLOAD_SKIPPED,
})

# --- Toàn vẹn tệp (độc lập; hash khớp KHÔNG phải chữ ký số hợp lệ) ---
INTEGRITY_NOT_CHECKED = "not_checked"
INTEGRITY_UNVERIFIED = "unverified"
INTEGRITY_VERIFIED = "verified"
INTEGRITY_INVALID = "invalid"
INTEGRITY_LABELS = {
    INTEGRITY_NOT_CHECKED: "Chưa kiểm tra",
    INTEGRITY_UNVERIFIED: "Chưa xác minh tham chiếu",
    INTEGRITY_VERIFIED: "Đã đối chiếu checksum",
    INTEGRITY_INVALID: "Không khớp; cần kiểm tra",
}

OWNER_DECLARATION = "declaration_source"
OWNER_FEEDBACK = "submission_feedback"
OWNER_TAX_NOTICE = "tax_notice"

_KIND_TO_BUSINESS = {
    "tiep-nhan": BUSINESS_RECEIVED,
    "chap-nhan": BUSINESS_ACCEPTED,
    "khong-chap-nhan": BUSINESS_REJECTED,
}
_REFERENCE_TO_INTEGRITY = {
    "VERIFIED": INTEGRITY_VERIFIED,
    "INVALID": INTEGRITY_INVALID,
    "NOT_CHECKED": INTEGRITY_NOT_CHECKED,
    "LEGACY_UNVERIFIED": INTEGRITY_UNVERIFIED,
}
_CONTENT_TYPES = {
    "xml": "application/xml",
    "pdf": "application/pdf",
    "zip": "application/zip",
}


def fold_text(value: Any) -> str:
    """Chuẩn hóa để tìm kiếm không phân biệt hoa/thường và dấu tiếng Việt."""
    text = str(value or "").replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text)
    return "".join(char for char in text if not unicodedata.combining(char)).casefold()


def _text(row: dict) -> str:
    return str(row.get("trang_thai") or "")


def event_datetime(value: Any) -> datetime:
    """Đọc ngày/giờ từ dữ liệu cổng; không hợp lệ trả ``datetime.min``.

    Dùng cho sắp xếp ổn định, không dùng để kết luận nghiệp vụ.
    """
    raw = str(value or "").strip()
    for pattern in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
                    "%d-%m-%Y %H:%M:%S", "%d-%m-%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, pattern)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return datetime.min


def format_date(value: Any) -> str:
    """Hiển thị ngày theo ``dd/MM/yyyy`` (kèm giờ nếu có); giữ nguyên nếu lạ."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = event_datetime(raw)
    if parsed == datetime.min:
        return raw
    if parsed.hour or parsed.minute or parsed.second:
        return parsed.strftime("%d/%m/%Y %H:%M")
    return parsed.strftime("%d/%m/%Y")


def period_key(value: Any) -> tuple[int, int, str]:
    """Khóa sắp xếp kỳ tính thuế: ``(năm, tháng, chuỗi gốc)``.

    Hỗ trợ ``Quý 3/2026``, ``Tháng 3/2026``, ``12/2024``, ``2026``. Không hiểu
    định dạng thì trả năm/tháng 0 để sắp xếp ổn định bằng chuỗi gốc.
    """
    text = fold_text(value)
    year_match = re.search(r"(?:19|20)\d{2}", text)
    year = int(year_match.group()) if year_match else 0
    quarter = re.search(r"quy\s*(\d)", text)
    month = re.search(r"thang\s*(\d{1,2})", text)
    if quarter:
        month_number = min(12, max(1, int(quarter.group(1)) * 3))
    elif month:
        month_number = min(12, max(1, int(month.group(1))))
    else:
        leading = re.match(r"\s*(\d{1,2})\s*[/-]\s*(?:19|20)\d{2}", text)
        month_number = int(leading.group(1)) if leading else 0
    return (year, month_number, text)


def business_status_from_text(value: Any) -> str:
    """Đọc trạng thái do cổng trả về; không suy diễn khi chuỗi không khớp."""
    text = fold_text(value)
    if not text:
        return BUSINESS_UNKNOWN
    if any(marker in text for marker in ("khong chap nhan", "khong duoc chap nhan", "tu choi")):
        return BUSINESS_REJECTED
    if "tiep nhan" in text:
        return BUSINESS_RECEIVED
    if "chap nhan" in text or "xac nhan" in text:
        return BUSINESS_ACCEPTED
    return BUSINESS_UNKNOWN


def download_status_from_row(row: dict) -> str:
    """Trạng thái tệp của một dòng; tách hoàn toàn khỏi trạng thái CQT."""
    value = str(row.get("_file_status") or DOWNLOAD_NOT_DOWNLOADED)
    return value if value in DOWNLOAD_STATUSES else DOWNLOAD_NOT_DOWNLOADED


def submission_key(row: dict, *, taxpayer_key: str = "") -> str:
    """Khóa ổn định có namespace cho một lần nộp.

    Giữ đủ 4 phần để hai hồ sơ cùng kỳ nhưng khác mã, khác nguồn hoặc khác
    lần nộp/bổ sung không bao giờ trùng khóa.
    """
    source_id = str(row.get("ma_ho_so") or "").strip()
    source = str(row.get("nguon") or "").strip()
    version = str(row.get("lan_nop") or row.get("lan_bo_sung") or "").strip()
    return "::".join([
        f"taxpayer={taxpayer_key}",
        f"source={source}",
        f"id={source_id}",
        f"version={version}",
    ])


def tax_notice_key(row: dict, *, taxpayer_key: str = "") -> str:
    """Khóa riêng của thông báo thuế độc lập (không dùng chung với tờ khai)."""
    return "::".join([
        f"taxpayer={taxpayer_key}",
        f"message_id={row.get('message_id') or ''}",
        f"ma_tbao={row.get('ma_tbao') or ''}",
    ])


@dataclass(frozen=True)
class DeclarationSubmission:
    submission_key: str
    taxpayer_key: str = ""
    declaration_type: str = ""
    tax_period: str = ""
    submission_version: str = ""
    submitted_at: str = ""
    tax_processing_status: str = BUSINESS_UNKNOWN
    download_status: str = DOWNLOAD_NOT_DOWNLOADED
    source: str = ""
    source_id: str = ""


@dataclass(frozen=True)
class SubmissionFeedback:
    feedback_key: str
    submission_key: str
    feedback_type: str = BUSINESS_UNKNOWN
    notice_number: str = ""
    issued_at: str = ""
    received_at: str = ""
    business_result: str = BUSINESS_UNKNOWN
    source_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TaxNotice:
    tax_notice_key: str
    taxpayer_key: str = ""
    notice_type: str = ""
    number: str = ""
    issued_at: str = ""
    received_at: str = ""
    business_result: str = BUSINESS_UNKNOWN
    download_status: str = DOWNLOAD_NOT_DOWNLOADED
    source_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentAsset:
    asset_key: str
    owner_kind: str
    owner_key: str
    path_or_handle: str = ""
    original_filename: str = ""
    content_type: str = ""
    source_id: str = ""
    checksum: str = ""
    size: int = 0
    downloaded_at: str = ""
    integrity_status: str = INTEGRITY_UNVERIFIED


def _feedback_key(notice: dict) -> str:
    return str(notice.get("reference_key") or notice.get("relative_path")
               or notice.get("path") or notice.get("name") or "")


def _feedback_type(notice: dict) -> str:
    # Chỉ tin loại đọc được từ XML đã parse; tên tệp không đủ để kết luận.
    if notice.get("read_status") != "PARSED":
        return BUSINESS_UNKNOWN
    return _KIND_TO_BUSINESS.get(str(notice.get("kind") or ""), BUSINESS_UNKNOWN)


def _business_result(notice: dict) -> str:
    state = str(notice.get("state") or "")
    if not state:
        return BUSINESS_UNKNOWN
    # Tệp có ownership nhưng chưa xác minh thì không dùng để kết luận.
    if notice.get("parent_key") and notice.get("reference_status") != "VERIFIED":
        return BUSINESS_UNKNOWN
    if state == REJECTED:
        return BUSINESS_REJECTED
    if state == ACCEPTED:
        return BUSINESS_ACCEPTED
    if state == RECEIVED:
        return BUSINESS_RECEIVED
    return BUSINESS_UNKNOWN


def _integrity(notice: dict) -> str:
    return _REFERENCE_TO_INTEGRITY.get(str(notice.get("reference_status") or ""),
                                        INTEGRITY_UNVERIFIED)


def feedback_from_notice(notice: dict, submission: str, *, key: str | None = None) -> SubmissionFeedback:
    """Ánh xạ một tệp thông báo đính kèm thành phản hồi của đúng lần nộp."""
    return SubmissionFeedback(
        feedback_key=key or _feedback_key(notice),
        submission_key=submission,
        feedback_type=_feedback_type(notice),
        notice_number=str(notice.get("so_thong_bao") or notice.get("ma_thong_bao") or ""),
        issued_at=str(notice.get("ngay_thong_bao") or ""),
        received_at="",
        business_result=_business_result(notice),
        source_metadata={
            "kind": notice.get("kind", ""),
            "kind_label": notice.get("kind_label", ""),
            "ten_thong_bao": notice.get("ten_thong_bao", ""),
            "ly_do": notice.get("ly_do", ""),
            "read_status": notice.get("read_status", ""),
            "reference_status": notice.get("reference_status", ""),
            "relative_path": notice.get("relative_path", ""),
            "sha256": notice.get("sha256", ""),
            "size": notice.get("size", 0),
        },
    )


def asset_from_notice(notice: dict, owner_kind: str, owner_key: str, *,
                      key: str | None = None) -> DocumentAsset:
    """Tệp thực tế của một phản hồi; khóa tệp độc lập với thứ tự hiển thị."""
    name = str(notice.get("name") or "")
    extension = Path(name).suffix.lstrip(".").lower()
    return DocumentAsset(
        asset_key=key or _feedback_key(notice),
        owner_kind=owner_kind,
        owner_key=owner_key,
        path_or_handle=str(notice.get("path") or ""),
        original_filename=name,
        content_type=_CONTENT_TYPES.get(extension, ""),
        source_id=str(notice.get("ma_thong_bao") or ""),
        checksum=str(notice.get("sha256") or ""),
        size=int(notice.get("size") or 0),
        downloaded_at="",
        integrity_status=_integrity(notice),
    )


def feedbacks_from_row(row: dict, *, taxpayer_key: str = "") -> list[SubmissionFeedback]:
    submission = submission_key(row, taxpayer_key=taxpayer_key)
    return [feedback_from_notice(notice, submission) for notice in row.get("_notices") or []]


def assets_from_row(row: dict, *, taxpayer_key: str = "") -> list[DocumentAsset]:
    submission = submission_key(row, taxpayer_key=taxpayer_key)
    return [asset_from_notice(notice, OWNER_FEEDBACK, submission)
            for notice in row.get("_notices") or []]


def aggregate_feedback_result(feedbacks: list[SubmissionFeedback]) -> str:
    """Trạng thái tổng hợp có quy tắc rõ ràng, không đoán.

    Thứ tự ưu tiên giữ đúng quy tắc đã kiểm chứng ở ``desktop.notices``:
    từ chối > chấp nhận > tiếp nhận. Danh sách rỗng là "chưa có phản hồi
    trong dữ liệu hiện có", không phải "đang chờ CQT".
    """
    results = {feedback.business_result for feedback in feedbacks}
    if not feedbacks:
        return BUSINESS_NONE
    if BUSINESS_REJECTED in results:
        return BUSINESS_REJECTED
    if BUSINESS_ACCEPTED in results:
        return BUSINESS_ACCEPTED
    if BUSINESS_RECEIVED in results:
        return BUSINESS_RECEIVED
    return BUSINESS_UNKNOWN


def has_conflicting_results(feedbacks: list[SubmissionFeedback]) -> bool:
    """Có cả chấp nhận lẫn từ chối → UI phải cho người dùng kiểm tra lại."""
    results = {feedback.business_result for feedback in feedbacks}
    return BUSINESS_ACCEPTED in results and BUSINESS_REJECTED in results


def submission_from_row(row: dict, *, taxpayer_key: str = "") -> DeclarationSubmission:
    """Tạo thực thể lần nộp từ row desktop; không suy ra trạng thái từ tệp."""
    if "_notices" in row:
        tax_status = aggregate_feedback_result(feedbacks_from_row(row, taxpayer_key=taxpayer_key))
    else:
        tax_status = business_status_from_text(_text(row))
    return DeclarationSubmission(
        submission_key=submission_key(row, taxpayer_key=taxpayer_key),
        taxpayer_key=taxpayer_key,
        declaration_type=str(row.get("to_khai") or row.get("ten_tthc") or ""),
        tax_period=str(row.get("ky_tinh_thue") or ""),
        submission_version=str(row.get("lan_nop") or row.get("lan_bo_sung") or ""),
        submitted_at=str(row.get("ngay_nop") or ""),
        tax_processing_status=tax_status,
        download_status=download_status_from_row(row),
        source=str(row.get("nguon") or ""),
        source_id=str(row.get("ma_ho_so") or ""),
    )


def tax_notice_from_row(row: dict, *, taxpayer_key: str = "") -> TaxNotice:
    """Thực thể thông báo thuế độc lập; không nhận dữ liệu phản hồi tờ khai."""
    return TaxNotice(
        tax_notice_key=tax_notice_key(row, taxpayer_key=taxpayer_key),
        taxpayer_key=taxpayer_key,
        notice_type=str(row.get("ten_thong_bao") or row.get("ma_tbao") or ""),
        number=str(row.get("so_thong_bao") or ""),
        issued_at=str(row.get("ngay_gui") or ""),
        received_at="",
        # ``trang_thai`` của tab này là trạng thái xem, không phải kết quả CQT.
        business_result=BUSINESS_UNKNOWN,
        download_status=download_status_from_row(row),
        source_metadata={key: row.get(key) for key in (
            "message_id", "ma_tbao", "ma_thong_bao", "ten_thong_bao", "so_thong_bao",
            "ngay_gui", "co_quan_gui", "trang_thai", "tep_pdf")},
    )


def declaration_asset(row: dict, *, taxpayer_key: str = "") -> DocumentAsset:
    """ZIP/XML nguồn của lần nộp (không phải phản hồi CQT)."""
    submission = submission_key(row, taxpayer_key=taxpayer_key)
    path = str(row.get("_file_path") or "")
    filename = str(row.get("tep_zip") or row.get("tep_xml") or Path(path).name or "")
    extension = Path(filename or path).suffix.lstrip(".").lower()
    return DocumentAsset(
        asset_key=submission,
        owner_kind=OWNER_DECLARATION,
        owner_key=submission,
        path_or_handle=path,
        original_filename=filename,
        content_type=_CONTENT_TYPES.get(extension, ""),
        source_id=str(row.get("ma_ho_so") or ""),
        checksum=str(row.get("_file_hash") or ""),
        size=int(row.get("_file_size") or 0),
        downloaded_at=str(row.get("_file_updated") or ""),
        integrity_status=(INTEGRITY_UNVERIFIED if download_status_from_row(row) == DOWNLOAD_DOWNLOADED
                          else INTEGRITY_NOT_CHECKED),
    )


def tax_notice_asset(row: dict, *, taxpayer_key: str = "") -> DocumentAsset:
    """Tệp PDF của thông báo thuế độc lập (owner_kind khác phản hồi)."""
    key = tax_notice_key(row, taxpayer_key=taxpayer_key)
    path = str(row.get("_file_path") or "")
    filename = str(row.get("tep_pdf") or Path(path).name or "")
    return DocumentAsset(
        asset_key=key,
        owner_kind=OWNER_TAX_NOTICE,
        owner_key=key,
        path_or_handle=path,
        original_filename=filename,
        content_type=_CONTENT_TYPES.get("pdf", ""),
        source_id=str(row.get("message_id") or ""),
        checksum=str(row.get("_file_hash") or ""),
        size=int(row.get("_file_size") or 0),
        downloaded_at=str(row.get("_file_updated") or ""),
        integrity_status=(INTEGRITY_UNVERIFIED if download_status_from_row(row) == DOWNLOAD_DOWNLOADED
                          else INTEGRITY_NOT_CHECKED),
    )


__all__ = [
    "BUSINESS_ACCEPTED",
    "BUSINESS_LABELS",
    "BUSINESS_NONE",
    "BUSINESS_RECEIVED",
    "BUSINESS_REJECTED",
    "BUSINESS_UNKNOWN",
    "DOWNLOAD_DOWNLOADED",
    "DOWNLOAD_FAILED",
    "DOWNLOAD_NOT_DOWNLOADED",
    "DOWNLOAD_QUEUED",
    "DOWNLOAD_SKIPPED",
    "DOWNLOAD_STATUSES",
    "DOWNLOADING",
    "DeclarationSubmission",
    "DocumentAsset",
    "INTEGRITY_INVALID",
    "INTEGRITY_LABELS",
    "INTEGRITY_NOT_CHECKED",
    "INTEGRITY_UNVERIFIED",
    "INTEGRITY_VERIFIED",
    "OWNER_DECLARATION",
    "OWNER_FEEDBACK",
    "OWNER_TAX_NOTICE",
    "SubmissionFeedback",
    "TaxNotice",
    "aggregate_feedback_result",
    "asset_from_notice",
    "assets_from_row",
    "business_status_from_text",
    "declaration_asset",
    "download_status_from_row",
    "event_datetime",
    "feedback_from_notice",
    "feedbacks_from_row",
    "fold_text",
    "format_date",
    "has_conflicting_results",
    "period_key",
    "submission_from_row",
    "submission_key",
    "tax_notice_asset",
    "tax_notice_from_row",
    "tax_notice_key",
]
