"""Truy xuất phản hồi CQT theo **một lần nộp** và thông báo thuế độc lập.

Lớp này là ranh giới nghiệp vụ cho UI (S02+):

* ``get_feedback_for_submission`` / ``list_feedback_items`` chỉ trả phản hồi
  của đúng dòng tờ khai được chọn.
* ``list_tax_notices`` chỉ trả văn bản của tab "Thông báo thuế"; không bao giờ
  đọc ``_notices`` của tờ khai và không tự gắn theo MST/kỳ/ngày.

Không có cache toàn cục: mỗi lần gọi dựng lại từ snapshot của dòng. Vì khóa
``submission_key`` được truyền tường minh, chuyển hồ sơ A → B không thể trả
nhầm dữ liệu của A.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .domain import (
    BUSINESS_LABELS,
    BUSINESS_NONE,
    DocumentAsset,
    SubmissionFeedback,
    TaxNotice,
    aggregate_feedback_result,
    asset_from_notice,
    event_datetime,
    feedback_from_notice,
    has_conflicting_results,
    submission_key,
    tax_notice_asset,
    tax_notice_from_row,
    tax_notice_key,
)
from .notices import row_attachment_problem

OWNER_FEEDBACK = "submission_feedback"


@dataclass(frozen=True)
class FeedbackItem:
    """Một phản hồi và tệp tương ứng, cùng một ``asset_key``."""

    feedback: SubmissionFeedback
    asset: DocumentAsset


@dataclass(frozen=True)
class FeedbackSummary:
    submission_key: str
    count: int
    status: str
    status_label: str
    conflict: bool
    problem: str


def _canonical_key(notice: dict) -> str:
    return str(notice.get("reference_key") or notice.get("relative_path")
               or notice.get("path") or notice.get("name") or "")


def _sort_key(notice: dict) -> tuple:
    return (
        event_datetime(notice.get("ngay_thong_bao")),
        str(notice.get("so_thong_bao") or ""),
        str(notice.get("name") or ""),
    )


def list_feedback_items(row: dict, *, taxpayer_key: str = "") -> list[FeedbackItem]:
    """Trả đúng N phản hồi của một lần nộp, mới nhất trước.

    ``reference_key`` trùng (cùng bản ghi có nhiều tệp) được giữ riêng bằng
    hậu tố ``#n`` thay vì âm thầm gộp mất dữ liệu.
    """
    notices = sorted(row.get("_notices") or [], key=_sort_key, reverse=True)
    submission = submission_key(row, taxpayer_key=taxpayer_key)
    seen: dict[str, int] = {}
    items: list[FeedbackItem] = []
    for notice in notices:
        base = _canonical_key(notice)
        if not base:
            continue
        occurrence = seen.get(base, 0) + 1
        seen[base] = occurrence
        key = base if occurrence == 1 else f"{base}#{occurrence}"
        items.append(FeedbackItem(
            feedback=feedback_from_notice(notice, submission, key=key),
            asset=asset_from_notice(notice, OWNER_FEEDBACK, submission, key=key),
        ))
    return items


def get_feedback_for_submission(row: dict, *, taxpayer_key: str = "") -> list[SubmissionFeedback]:
    """API tương đương ``getFeedbackForSubmission(submissionKey)``."""
    return [item.feedback for item in list_feedback_items(row, taxpayer_key=taxpayer_key)]


def list_feedback_assets(row: dict, *, taxpayer_key: str = "") -> list[DocumentAsset]:
    return [item.asset for item in list_feedback_items(row, taxpayer_key=taxpayer_key)]


def find_feedback_item(row: dict, key: str, *, taxpayer_key: str = "") -> FeedbackItem | None:
    """Tìm đúng phản hồi/tệp theo khóa; không dùng chỉ số hàng hiển thị."""
    for item in list_feedback_items(row, taxpayer_key=taxpayer_key):
        if item.feedback.feedback_key == key or item.asset.asset_key == key:
            return item
    return None


def feedback_summary(row: dict, *, taxpayer_key: str = "") -> FeedbackSummary:
    items = list_feedback_items(row, taxpayer_key=taxpayer_key)
    feedbacks = [item.feedback for item in items]
    status = aggregate_feedback_result(feedbacks)
    return FeedbackSummary(
        submission_key=submission_key(row, taxpayer_key=taxpayer_key),
        count=len(items),
        status=status,
        status_label=BUSINESS_LABELS.get(status, BUSINESS_LABELS[BUSINESS_NONE]),
        conflict=has_conflicting_results(feedbacks),
        problem=row_attachment_problem(row),
    )


def _rows(rows: dict | Iterable[dict]) -> list[dict]:
    return [rows] if isinstance(rows, dict) else list(rows)


def list_tax_notices(rows: dict | Iterable[dict], *, taxpayer_key: str = "") -> list[TaxNotice]:
    """Danh sách thông báo thuế **độc lập**, không đọc ``_notices`` của tờ khai."""
    seen: set[str] = set()
    notices: list[TaxNotice] = []
    for row in _rows(rows):
        if not any(row.get(key) for key in ("message_id", "so_thong_bao", "ten_thong_bao")):
            continue
        mapped = tax_notice_from_row(row, taxpayer_key=taxpayer_key)
        if mapped.tax_notice_key in seen:
            continue
        seen.add(mapped.tax_notice_key)
        notices.append(mapped)
    notices.sort(key=lambda item: event_datetime(item.issued_at), reverse=True)
    return notices


def list_tax_notice_assets(rows: dict | Iterable[dict], *, taxpayer_key: str = "") -> list[DocumentAsset]:
    seen: set[str] = set()
    assets: list[DocumentAsset] = []
    for row in _rows(rows):
        if not any(row.get(key) for key in ("message_id", "so_thong_bao", "ten_thong_bao")):
            continue
        key = tax_notice_key(row, taxpayer_key=taxpayer_key)
        if key in seen:
            continue
        seen.add(key)
        assets.append(tax_notice_asset(row, taxpayer_key=taxpayer_key))
    return assets


def find_tax_notice_asset(row: dict, *, taxpayer_key: str = "") -> DocumentAsset | None:
    if not any(row.get(key) for key in ("message_id", "so_thong_bao", "ten_thong_bao")):
        return None
    return tax_notice_asset(row, taxpayer_key=taxpayer_key)


class RequestGate:
    """Chống response cũ ghi đè khi người dùng chuyển hồ sơ nhanh (AC15).

    UI gọi ``begin()`` trước khi tải và chỉ render nếu ``is_current(token)``
    còn đúng; chuyển hồ sơ gọi ``invalidate()``.
    """

    def __init__(self) -> None:
        self._version = 0

    def begin(self) -> int:
        self._version += 1
        return self._version

    def invalidate(self) -> int:
        self._version += 1
        return self._version

    def is_current(self, token: int) -> bool:
        return token == self._version


__all__ = [
    "FeedbackItem",
    "FeedbackSummary",
    "RequestGate",
    "feedback_summary",
    "find_feedback_item",
    "find_tax_notice_asset",
    "get_feedback_for_submission",
    "list_feedback_assets",
    "list_feedback_items",
    "list_tax_notice_assets",
    "list_tax_notices",
]
