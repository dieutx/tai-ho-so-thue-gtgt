"""Local SQLite projections and one-time, ownership-checked legacy import."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date, datetime
from pathlib import Path

from gdt_tax.identity import IdentityError, account_fingerprint
from gdt_tax.local_catalog import LocalCatalog
from gdt_tax.run_hooks import RunHooks

from .documents import FILE_LABELS, document_id
from .domain import INTEGRITY_INVALID, INTEGRITY_LABELS, INTEGRITY_NOT_CHECKED, INTEGRITY_UNVERIFIED
from .services import JobResult

CATALOGS = {
    "tax": "danh_sach_ho_so.json",
    "gnt": "danh_sach_giay_nop_tien.json",
    "notice": "danh_sach_thong_bao.json",
}
FOLDERS = {"tax": "to-khai", "gnt": "gnt", "notice": "thong-bao"}
DATE_FIELDS = {"tax": "ngay_nop", "gnt": "ngay_lap", "notice": "ngay_gui"}
FILE_FIELDS = {"tax": "tep_zip", "gnt": "tep_xml", "notice": "tep_pdf"}
LABELS = {"tax": "tờ khai", "gnt": "giấy nộp tiền", "notice": "thông báo thuế"}
#: Trường tệp của bản ghi cũ phải được giữ khi bản ghi mới (online) thiếu thông tin.
FILE_METADATA = ("_file_status", "_file_state", "_file_path", "_file_size", "_file_hash",
                 "_file_updated", "_file_reason", "_integrity_status", "_integrity_label")


def parse_date(value) -> date | None:
    """Đọc ``dd/MM/yyyy`` (kèm giờ) và một số định dạng cũ; không đoán bừa."""
    text = str(value or "").strip()
    if not text:
        return None
    text = text.split(" ")[0].split("T")[0]
    for pattern in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


def date_in_range(mode: str, row: dict, start: date | None, end: date | None) -> bool:
    """Ngày của dòng có nằm trong khoảng (bao gồm hai đầu); dòng chưa rõ ngày vẫn giữ."""
    when = parse_date(row.get(DATE_FIELDS.get(mode, "")))
    if when is None:
        return start is None and end is None
    if start is not None and when < start:
        return False
    if end is not None and when > end:
        return False
    return True


def row_key(mode: str, row: dict) -> str:
    key = document_id(mode, row)
    if key:
        return key
    return "|".join(str(row.get(name) or "").strip() for name in
                    ("nguon", "ma_ho_so", "ctu_id", "message_id", "ngay_nop", "ngay_lap", "ngay_gui"))


def read_catalog(mode: str, folder: str | Path) -> list[dict]:
    """Đọc danh mục JSON; thiếu tệp là danh sách rỗng, tệp hỏng báo lỗi rõ."""
    if mode not in CATALOGS:
        raise ValueError("Nghiệp vụ không hợp lệ")
    path = Path(folder) / CATALOGS[mode]
    if not path.is_file():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"Không đọc được {path.name}: {error}") from error
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"{path.name} không phải danh sách bản ghi")
    return rows


def dedupe(mode: str, rows: list[dict]) -> list[dict]:
    """Bỏ bản ghi trùng cùng khóa (giữ thứ tự); bản ghi sau bổ sung trường thiếu."""
    merged: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = row_key(mode, row)
        if not key.strip("|"):
            continue
        if key in merged:
            merged[key].update({k: v for k, v in row.items() if v not in (None, "")})
        else:
            merged[key] = dict(row)
    return list(merged.values())


def merge_rows(mode: str, existing: list[dict], incoming: list[dict]) -> list[dict]:
    """Gộp kết quả online vào dữ liệu local: một dòng cho mỗi hồ sơ, không mất tệp đã tải."""
    merged: dict[str, dict] = {}
    for row in existing or []:
        if isinstance(row, dict):
            merged[row_key(mode, row)] = dict(row)
    for row in incoming or []:
        if not isinstance(row, dict):
            continue
        key = row_key(mode, row)
        old = merged.get(key)
        if old is None:
            merged[key] = dict(row)
            continue
        combined = {**old, **row}
        for field in FILE_METADATA:
            if old.get(field) and not row.get(field):
                combined[field] = old[field]
        if old.get("_file_status") == "downloaded" and row.get("_file_status") in (None, "", "not_downloaded"):
            combined["_file_status"] = "downloaded"
        merged[key] = combined
    return list(merged.values())


def check_files(mode: str, rows: list[dict], folder: str | Path) -> list[dict]:
    """Đối chiếu tệp thật (tồn tại + kích thước) — không băm, không đọc nội dung."""
    root = Path(folder)
    file_field = FILE_FIELDS.get(mode, "")
    checked: list[dict] = []
    for row in rows:
        item = dict(row)
        name = str(item.get(file_field) or "")
        path = (root / name).resolve() if name else None
        if path is not None and not path.is_relative_to(root.resolve()):
            path = None
        size = 0
        if path is not None:
            try:
                size = path.stat().st_size if path.is_file() else 0
            except OSError:
                size = 0
        expected = item.get('_file_size')
        valid = (item.get('_file_status') == 'downloaded' and bool(item.get('_file_hash'))
                 and expected == size and item.get('_integrity_status') != INTEGRITY_INVALID)
        if valid and item.get('_file_mtime_ns') is not None:
            valid = path is not None and path.stat().st_mtime_ns == item['_file_mtime_ns']
        if path is not None and size > 0 and valid:
            item.update(_file_status="downloaded", _file_state=FILE_LABELS["downloaded"],
                        _file_path=str(path.resolve()), _file_size=size, _file_reason="",
                        _integrity_status=INTEGRITY_UNVERIFIED,
                        _integrity_label=INTEGRITY_LABELS[INTEGRITY_UNVERIFIED])
        else:
            reason = ("Tệp đã bị xóa hoặc di chuyển; bấm Tải tệp để lấy lại" if name
                      else "Danh mục không ghi tên tệp; bấm Tải tệp để lấy lại")
            item.update(_file_status="not_downloaded", _file_state=FILE_LABELS["not_downloaded"],
                        _file_path="", _file_size=0, _file_reason=reason,
                        _integrity_status=INTEGRITY_NOT_CHECKED,
                        _integrity_label=INTEGRITY_LABELS[INTEGRITY_NOT_CHECKED])
        checked.append(item)
    return checked


def account_dir(base: str | Path, username: str) -> Path:
    """Thư mục tài khoản đúng như ``state.job_output`` tạo ra, để đọc lại dữ liệu cũ."""
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", username)[:48].strip("_") or "tai-khoan"
    return Path(base) / f"{safe}-{hashlib.sha256(username.encode()).hexdigest()[:8]}"


def library_folders(base: str | Path, username: str, mode: str) -> list[Path]:
    """Các thư mục có thể chứa danh mục của tài khoản (kể cả ngách ``tai-moi``)."""
    root = account_dir(base, username)
    folders = [root / FOLDERS[mode], root / "tai-moi" / FOLDERS[mode]]
    return [folder for index, folder in enumerate(folders) if folder not in folders[:index]]


def catalog_view(base, username, mode, start=None, end=None, *, unknown=False, include_unknown=False,
                 migrate=False, hooks=None, account_type="DN"):
    """SELECT the visible range; no HTTP and no full inventory file verification."""
    from .documents import verify_rows
    from .state import job_output
    account_key = account_fingerprint(username)
    used = job_output(Path(base), username, mode, account_type)
    rows, keys, unknown_keys, review, problems = [], set(), set(), 0, []
    for folder in library_folders(base, username, mode):
        if not (folder / 'catalog.sqlite3').exists() and not (folder / CATALOGS[mode]).exists():
            continue
        try:
            catalog = LocalCatalog(folder, account_key)
            if migrate:
                report = catalog.import_json(mode)
                if report['state'] == 'IMPORTED':
                    imported = catalog.get_documents(mode)
                    catalog.upsert_documents(mode, verify_rows(mode, imported, folder, hooks))
            with catalog.connection() as db:
                keys.update(row[0] for row in db.execute('SELECT record_key FROM documents WHERE account_key=? AND mode=?', (account_key, mode)))
                unknown_keys.update(row[0] for row in db.execute('SELECT record_key FROM documents WHERE account_key=? AND mode=? AND document_date IS NULL', (account_key, mode)))
            review += catalog.get_counts(mode)['quarantined']
            selected = catalog.get_documents(mode, start, end, unknown=unknown)
            rows = merge_rows(mode, rows, check_files(mode, selected, folder))
            if include_unknown and not unknown and (start or end):
                # Hồ sơ thiếu ngày vẫn hiện (ngày "—") thay vì bị bỏ âm thầm
                # khi bỏ nhóm lọc "Ngày chưa xác định" khỏi giao diện.
                undated = catalog.get_documents(mode, unknown=True)
                rows = merge_rows(mode, rows, check_files(mode, undated, folder))
        except (OSError, ValueError, IdentityError, sqlite3.Error) as error:
            problems.append(str(error))
    result = JobResult('LOADED' if not problems else 'PARTIAL' if rows else 'ERROR',
                       '; '.join(problems) if problems else 'Hồ sơ trên máy — bấm Tra cứu để đối soát online',
                       used, rows=rows, discovered=len(rows), account_key=account_key, operation='library',
                       inventory_total=len(keys), unknown_dates=len(unknown_keys), quarantined=review)
    result.date_range = (str(start or ''), str(end or ''))
    return result


def load_library(config, hooks: RunHooks) -> JobResult:
    """Migrate trusted JSON once, then read SQLite for the three independent tabs."""
    base = Path(config.output)
    base.mkdir(parents=True, exist_ok=True)
    account_key = account_fingerprint(config.username)
    children: dict[str, JobResult] = {}
    total = 0
    for mode in ("tax", "gnt", "notice"):
        hooks.check()
        children[mode] = catalog_view(base, config.username, mode, config.from_date or None,
                                      config.to_date or None, migrate=True, hooks=hooks,
                                      account_type=getattr(config, 'account_type', 'DN'))
        total += len(children[mode].rows)
    failures = sum(1 for child in children.values() if child.state == "ERROR")
    message = (f"Đã nạp {total} hồ sơ từ máy — không gọi mạng" if not failures
               else f"Đã nạp {total} hồ sơ từ máy; {failures} nhóm lỗi danh mục")
    result = JobResult("LOADED", message, base, children=children)
    result.account_key = account_key
    result.date_range = (config.from_date, config.to_date)
    result.operation = "library"
    return result


__all__ = ["CATALOGS", "DATE_FIELDS", "FOLDERS", "LABELS", "account_dir", "check_files",
           "date_in_range", "dedupe", "library_folders", "load_library", "merge_rows",
           "parse_date", "read_catalog", "row_key"]
