"""Read legacy catalogues without login; explicit safe copy into the account folder."""
from __future__ import annotations

import hashlib
import json
from dataclasses import fields

from gdt_tax.gnt.models import GiayNopTien
from gdt_tax.gnt.portal import is_gnt_xml
from gdt_tax.gnt.storage import write_gnt_metadata
from gdt_tax.models import CaseRecord
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
    copied = {}
    allowed = {f.name for f in fields(model)}
    try:
        for index, row in enumerate(rows):
            hooks.check()
            record = model(**{k: v for k, v in row.items() if k in allowed})
            filename = str(row.get(file_key) or "")
            valid = False
            if filename:
                path = (source / filename).resolve()
                if path.is_relative_to(source) and path.is_file():
                    valid = valid_zip(path.read_bytes()) if config.stage == "tax" else (is_gnt_xml(path.read_bytes()) if config.stage == "gnt" else is_tb_pdf(path.read_bytes()))
                if valid and copy_files:
                    target = (output / filename).resolve()
                    if not target.is_relative_to(output.resolve()):
                        raise ValueError("Tên tệp không an toàn trong danh mục")
                    if target.exists() and hashlib.sha256(target.read_bytes()).digest() != hashlib.sha256(path.read_bytes()).digest():
                        raise ValueError("Thư mục đích có tệp khác nội dung; giữ nguyên cả hai thư mục, chọn đích mới")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if not target.exists():
                        _atomic_write(target, path.read_bytes())
            if filename and not valid:
                result.skipped += 1
                setattr(record, file_key, "")
            result.rows.append(record.to_dict())
            result.downloaded += int(valid)
            result.discovered += 1
            if copy_files:
                copied[str(index)] = record
                writer(output, copied)
    except RunCancelled:
        result.state, result.message = "CANCELLED", "Đã dừng nhập dữ liệu; tệp nguồn giữ nguyên"
    else:
        if copy_files:
            result.state = "PARTIAL" if result.skipped else "SUCCESS"
            result.message = "Đã sao chép dữ liệu hợp lệ; tệp nguồn giữ nguyên"
    if (output / report).is_file():
        result.files = [output / report, output / name]
    return result
