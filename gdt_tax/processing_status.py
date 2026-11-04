"""Read explicit processing states from detail labels and dated history events."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime

from bs4 import BeautifulSoup, Tag


def fold(value: str) -> str:
    value = unicodedata.normalize('NFKD', value.replace('đ', 'd').replace('Đ', 'D'))
    return ''.join(c for c in value if not unicodedata.combining(c)).casefold()


def status_code(value: str) -> str:
    text = fold(value)
    # Combined notice titles describe a template, not an actual decision.
    if re.search(r'chap nhan\s*[/|]\s*khong chap nhan', text):
        return ''
    if any(marker in text for marker in ('khong chap nhan', 'khong duoc chap nhan', 'tu choi')):
        return 'rejected'
    if 'chap nhan' in text and not any(marker in text for marker in ('cho chap nhan', 'chua chap nhan')):
        return 'accepted'
    if 'tiep nhan' in text and not any(marker in text for marker in ('cho tiep nhan', 'chua tiep nhan')):
        return 'received'
    if any(marker in text for marker in ('cho chap nhan', 'chua chap nhan', 'cho tiep nhan', 'chua tiep nhan', 'dang xu ly')):
        return 'pending'
    return ''


def _event_time(text: str) -> datetime:
    values = []
    for expression, formats in (
        (r'\d{2}:\d{2}(?::\d{2})?\s+\d{2}/\d{2}/\d{4}',
         ('%H:%M:%S %d/%m/%Y', '%H:%M %d/%m/%Y')),
        (r'\d{2}/\d{2}/\d{4}(?:\s+\d{2}:\d{2}(?::\d{2})?)?',
         ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%d/%m/%Y')),
    ):
        for match in re.finditer(expression, text):
            for fmt in formats:
                try:
                    values.append(datetime.strptime(match.group(), fmt))
                    break
                except ValueError:
                    pass
    return max(values, default=datetime.min)


_STATUS_LABELS = {'trang thai', 'trang thai ho so', 'trang thai cqt', 'trang thai xu ly',
                  'trang thai tiep nhan', 'trang thai hien tai'}


def _labelled_status(node: Tag) -> str:
    for label in node.find_all(['p', 'label', 'dt', 'th', 'td', 'span', 'div', 'strong', 'b']):
        if fold(label.get_text(' ', strip=True)).strip(' :') not in _STATUS_LABELS:
            continue
        value = label.find_next_sibling()
        if value is None and label.parent is not None:
            value = label.parent.find_next_sibling()
        if isinstance(value, Tag):
            text = value.get_text(' ', strip=True)
            if not text:
                field = value.find('input')
                text = str(field.get('value') or '') if field else ''
            if status_code(text) and len(text) < 250:
                return text
    return ''


def detail_processing_status(html: str) -> str:
    """Use only visible labelled values/history, never notice/download titles.

    A dated event takes precedence over an undated summary. Without reliable
    dates, preserve document order within a history list (latest event last).
    Unrecognised markup yields no override of the search result.
    """
    soup = BeautifulSoup(html, 'lxml')
    for node in soup.select('script, style, template, [hidden], [aria-hidden="true"]'):
        node.decompose()
    for node in soup.select('[style]'):
        if node.attrs and re.search(r'display\s*:\s*none|visibility\s*:\s*hidden',
                                    str(node.get('style') or ''), re.I):
            node.decompose()
    events: list[tuple[datetime, int, str]] = []
    for index, node in enumerate(soup.select(
            '.timeline-step, .timeline-item, .timeline-event, .history-item, [data-processing-status]')):
        text = node.get_text(' ', strip=True)
        # Exclude file/notice lists even if they happen to use timeline styles.
        if node.select('a[download], [onclick*="download"], [data-id-tbao]'):
            continue
        state = str(node.get('data-processing-status') or '') or _labelled_status(node)
        if not state:
            labels = node.select('.status, .status-label, .timeline-title, .timeline-header, h4, h5, h6')
            state = next((item.get_text(' ', strip=True) for item in labels
                          if status_code(item.get_text(' ', strip=True))), '')
        if not status_code(state):
            continue
        events.append((_event_time(text), index, state))
    if events:
        return max(events)[2]
    return _labelled_status(soup)
