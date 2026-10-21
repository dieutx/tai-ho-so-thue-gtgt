"""Conservative contracts for the declaration-specific legacy notice table."""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .dvc_notices import DvcNotice, NoticeList, _fold
from .table_contracts import normalize_label

DOWNLOAD = re.compile(r"\bdownloadFile\(\s*['\"]([0-9]+)['\"]\s*\)", re.I)


def parse_legacy_notice_list(html: str) -> NoticeList:
    soup = BeautifulSoup(html, 'lxml')
    tables = soup.select('table#tbl_tracuu')
    if len(tables) != 1:
        return NoticeList()
    table = tables[0]
    headers = [normalize_label(cell.get_text(' ', strip=True)) for cell in table.select('thead th')]
    expected = [normalize_label(label) for label in ('STT', 'Số thông báo/Mã giao dịch VAN', 'Thông báo', 'Ngày gửi', 'Người gửi')]
    if headers != expected:
        return NoticeList()
    notices = []
    seen = set()
    malformed = False
    rows = (table.find('tbody') or table).find_all('tr', recursive=False)
    for row in rows:
        cells = row.find_all('td', recursive=False)
        if not cells:
            continue
        if len(cells) == 1 and ('khong co thong bao' in _fold(row.get_text(' ', strip=True))):
            continue
        matches = DOWNLOAD.findall(str(row))
        if len(cells) != 5 or len(matches) != 1:
            malformed = True
            continue
        notice_id = matches[0]
        # The displayed notice/VAN reference is not the download messageId.
        # Bind identity to the reviewed handler on this row, never its label.
        if notice_id in seen:
            malformed = True
            continue
        seen.add(notice_id)
        title = re.sub(r'(?i)^v/v\s*:\s*', '', cells[2].get_text(' ', strip=True))
        notices.append(DvcNotice(id=notice_id, title=title, sent_at=cells[3].get_text(' ', strip=True)))
    text = _fold(soup.get_text(' ', strip=True))
    count = re.search(r'co\s+(\d+)\s+ban ghi', text)
    pagination = re.search(r'trang\s*\d+\s*/\s*(\d+)', text)
    if count and int(count[1]) != len(notices) or pagination and int(pagination[1]) > 1:
        malformed = True
    empty = not notices and ('khong co thong bao' in text or count is not None and int(count[1]) == 0)
    status = ('PARSED' if notices and not malformed else
              'EMPTY_CONFIRMED' if empty and not malformed else 'SCHEMA_UNKNOWN')
    return NoticeList(notices, status)


def legacy_notices(html: str) -> list[DvcNotice]:
    return parse_legacy_notice_list(html).notices
