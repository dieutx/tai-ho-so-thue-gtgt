"""Read legacy catalogues without login; explicit safe copy into the account folder."""
from __future__ import annotations

import hashlib
import json
from dataclasses import fields
from pathlib import Path

from gdt_tax.gnt.models import GiayNopTien
from gdt_tax.gnt.portal import is_gnt_xml
from gdt_tax.gnt.storage import write_gnt_metadata
from gdt_tax.identity import IdentityError, account_fingerprint, key_from_row
from gdt_tax.integrity import matches_evidence, source_reference
from gdt_tax.local_catalog import LocalCatalog
from gdt_tax.models import CaseRecord
from gdt_tax.ownership import check_owner
from gdt_tax.run_hooks import RunCancelled, RunHooks
from gdt_tax.storage import _atomic_write, valid_zip, write_metadata
from gdt_tax.tb.models import ThongBao
from gdt_tax.tb.portal import is_tb_pdf
from gdt_tax.tb.storage import write_tb_metadata

from .services import JobResult, RunConfig

FORMATS = {
    "tax": ("danh_sach_ho_so.json", "danh_sach_to_khai.xlsx", "tep_zip", CaseRecord, write_metadata),
    "gnt": ("danh_sach_giay_nop_tien.json", "danh_sach_giay_nop_tien.xlsx", "tep_xml", GiayNopTien, write_gnt_metadata),
    "notice": ("danh_sach_thong_bao.json", "danh_sach_thong_bao.xlsx", "tep_pdf", ThongBao, write_tb_metadata),
}


def _copy_artifact(source: Path, output: Path, path: Path) -> None:
    source = source.resolve()
    output = output.resolve()
    path = path.resolve()
    if not path.is_relative_to(source):
        raise ValueError('Tệp nguồn nằm ngoài thư mục đã chọn')
    target = (output / path.relative_to(source)).resolve()
    if not target.is_relative_to(output):
        raise ValueError('Tên tệp không an toàn trong danh mục')
    pending = []
    for original, destination in ((path, target), (path.with_name(path.name + '.integrity.json'),
                                                   target.with_name(target.name + '.integrity.json'))):
        if destination.is_symlink() or not destination.resolve().is_relative_to(output):
            raise ValueError('Tệp hoặc evidence đích không an toàn')
        if not original.is_file():
            continue
        if not original.resolve().is_relative_to(source) or original.is_symlink():
            raise ValueError('Tệp hoặc evidence nguồn không an toàn')
        content = original.read_bytes()
        if destination.exists() and hashlib.sha256(destination.read_bytes()).digest() != hashlib.sha256(content).digest():
            raise ValueError('Tệp/evidence đích khác nguồn; giữ nguyên dữ liệu để xác minh')
        if not destination.exists():
            pending.append((destination, content))
    # Check both the document and its evidence before writing either file.
    for destination, content in pending:
        destination.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(destination, content)


def load_saved(config: RunConfig, hooks: RunHooks, *, copy_files: bool = False) -> JobResult:
    if config.source is None or not config.source.is_dir():
        raise ValueError("Chọn thư mục dữ liệu cũ tồn tại")
    name, report, file_key, model, writer = FORMATS[config.stage]
    source = config.source.resolve()
    rows = json.loads((source / name).read_text(encoding="utf-8"))
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("Danh mục cũ không đúng định dạng")
    output = config.output if copy_files else source
    result = JobResult("LOADED", "Đã mở danh mục lưu sẵn — chưa gọi mạng", output)
    catalog = None
    if copy_files:
        account = account_fingerprint(config.username)
        # An explicit copy must still have evidence of the source account.
        # Unowned legacy remains available through read-only saved mode.
        check_owner(source, account)
        catalog = LocalCatalog(output, account)
        catalog.backup()
        counts = catalog.upsert_documents(config.stage, rows)
        with catalog.connection() as db:
            accepted = {item[0] for item in db.execute('SELECT record_key FROM documents WHERE account_key=? AND mode=?',
                                                      (account, config.stage))}
        result.skipped += counts['quarantined']
        result.account_key = account
    copied = {}
    allowed = {f.name for f in fields(model)}
    try:
        for index, row in enumerate(rows):
            hooks.check()
            if catalog:
                try:
                    kind = {'tax': 'DECLARATION', 'gnt': 'GNT', 'notice': 'NOTICE'}[config.stage]
                    key = key_from_row(row, kind)
                    if not key.owned or key.account_key != account or key.serialize() not in accepted:
                        continue
                except IdentityError:
                    continue
            record = model(**{k: v for k, v in row.items() if k in allowed})
            filename = str(row.get(file_key) or "")
            valid = False
            if filename:
                path = (source / filename).resolve()
                if path.is_relative_to(source) and path.is_file():
                    valid = valid_zip(path.read_bytes()) if config.stage == "tax" else (is_gnt_xml(path.read_bytes()) if config.stage == "gnt" else is_tb_pdf(path.read_bytes()))
                    if copy_files:
                        media = {'tax': 'zip', 'gnt': 'gnt', 'notice': 'pdf'}[config.stage]
                        valid = valid and matches_evidence(path, path.read_bytes(), source_reference(record, media))
                if valid and copy_files:
                    _copy_artifact(source, output, path)
            if copy_files and catalog and config.stage == 'tax':
                from .notices import read_notices
                for notice in read_notices(source, record.ma_ho_so, parent_key=record.record_key):
                    hooks.check()
                    if notice.get('reference_status') != 'VERIFIED':
                        catalog.quarantine_metadata('tax', notice, 'IMPORT_ATTACHMENT_EVIDENCE_REQUIRED')
                        result.skipped += 1
                        continue
                    _copy_artifact(source, output, Path(notice['path']))
            if filename and not valid:
                result.skipped += 1
                setattr(record, file_key, "")
            result.rows.append(record.to_dict())
            result.downloaded += int(valid)
            result.discovered += 1
            if copy_files:
                copied[str(index)] = record
    except RunCancelled:
        result.state, result.message = "CANCELLED", "Đã dừng nhập dữ liệu; tệp nguồn giữ nguyên"
    else:
        if copy_files:
            result.state = "PARTIAL" if result.skipped else "SUCCESS"
            result.message = "Đã sao chép dữ liệu hợp lệ; tệp nguồn giữ nguyên"
    if catalog and copied:
        writer(output, copied)
    if (output / report).is_file():
        result.files = [output / report, output / name]
    return result
