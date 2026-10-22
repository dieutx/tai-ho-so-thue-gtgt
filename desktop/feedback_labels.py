"""Shared feedback presentation labels; safe in core-only installations."""
from .domain import BUSINESS_ACCEPTED, BUSINESS_RECEIVED, BUSINESS_REJECTED, BUSINESS_UNKNOWN

TYPE_LABELS = {
    BUSINESS_RECEIVED: 'Tiếp nhận',
    BUSINESS_ACCEPTED: 'Chấp nhận',
    BUSINESS_REJECTED: 'Không chấp nhận',
    BUSINESS_UNKNOWN: 'Phản hồi khác / Chưa phân loại',
}
RESULT_PREFIX = {
    BUSINESS_ACCEPTED: '✓ ',
    BUSINESS_REJECTED: '✕ ',
    BUSINESS_RECEIVED: '• ',
    BUSINESS_UNKNOWN: '? ',
}
