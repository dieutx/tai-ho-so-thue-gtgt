"""Xuất gói hồ sơ ZIP: tờ khai + **chỉ** phản hồi của chính lần nộp đó.

Không gộp thông báo thuế độc lập. Không theo symlink, không ghi đè tệp nguồn,
không dùng đường dẫn tuyệt đối/`..` trong archive. Tệp thiếu được ghi rõ trong
``manifest.json`` thay vì bị bỏ qua âm thầm.
"""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gdt_tax.atomic import replace_with_retry

from .domain import submission_key
from .feedback_service import list_feedback_items

MANIFEST_NAME = 'manifest.json'
SCHEMA_VERSION = 'submission-bundle-v1'
MAX_NAME = 120
_INVALID_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


@dataclass
class BundleResult:
    path: Path
    included: list[str] = field(default_factory=list)
    missing: list[dict] = field(default_factory=list)
    manifest: dict = field(default_factory=dict)


def safe_archive_name(name: str, maximum: int = MAX_NAME) -> str:
    """Tên tệp an toàn trong ZIP; giữ Unicode nhưng bỏ ký tự đường dẫn/cấm."""
    base = re.split(r'[\\/]', str(name or 'tep'))[-1]
    base = _INVALID_CHARS.sub('-', base).strip('. ')
    if not base:
        base = 'tep'
    suffix = Path(base).suffix
    if len(base) > maximum:
        base = Path(base).stem[:max(1, maximum - len(suffix) - 1)] + suffix
    return base


def _unique(archive_name: str, used: set[str]) -> str:
    candidate = archive_name
    index = 2
    while candidate.casefold() in used:
        parent, name = archive_name.rsplit('/', 1) if '/' in archive_name else ('', archive_name)
        stem, suffix = Path(name).stem, Path(name).suffix
        renamed = f'{stem}#{index}{suffix}'
        candidate = f'{parent}/{renamed}' if parent else renamed
        index += 1
    used.add(candidate.casefold())
    return candidate


def _file_digest(path: Path, chunk_size: int = 1024 * 1024) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open('rb') as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def export_submission_bundle(row: dict, target: str | Path, *, taxpayer_key: str = '') -> BundleResult:
    """Tạo ZIP cho một lần nộp; trả danh sách tệp đã đóng gói và tệp thiếu."""
    target = Path(target)
    if target.suffix.lower() != '.zip':
        target = target.with_suffix('.zip')
    if target.is_dir():
        raise ValueError('Đường dẫn xuất phải là tệp ZIP, không phải thư mục.')
    key = submission_key(row, taxpayer_key=taxpayer_key)
    manifest: dict[str, Any] = {
        'schema_version': SCHEMA_VERSION,
        'submission_key': key,
        'taxpayer_key': taxpayer_key,
        'source': row.get('nguon') or '',
        'source_id': row.get('ma_ho_so') or '',
        'declaration': {},
        'feedback': [],
        'missing': [],
        'notice_policy': 'Chỉ phản hồi của lần nộp này; không gộp thông báo thuế độc lập.',
    }
    used: set[str] = set()
    files: list[tuple[str, Path]] = []

    def add(kind: str, path: Path, original: str, metadata: dict) -> str | None:
        source = Path(path)
        if not original:
            original = source.name
        if not source.is_file() or source.is_symlink():
            manifest['missing'].append({'kind': kind, 'name': original,
                                        'reason': 'Tệp không còn tồn tại hoặc không phải tệp thường'})
            return None
        archive_name = _unique(f'{kind}/{safe_archive_name(original)}', used)
        try:
            digest, size = _file_digest(source)
        except OSError:
            manifest['missing'].append({'kind': kind, 'name': original,
                                        'reason': 'Không đọc được tệp'})
            return None
        files.append((archive_name, source))
        entry = {
            **metadata,
            'archive_name': archive_name,
            'original_filename': original,
            'sha256': digest,
            'size': size,
        }
        if kind == 'to-khai':
            manifest['declaration'] = entry
        else:
            manifest['feedback'].append(entry)
        return archive_name

    declaration = Path(str(row.get('_file_path') or ''))
    declaration_name = str(row.get('tep_zip') or declaration.name or row.get('ma_ho_so') or 'to-khai.zip')
    add('to-khai', declaration, declaration_name, {
        'source_id': row.get('ma_ho_so') or '',
        'type': row.get('to_khai') or '',
        'period': row.get('ky_tinh_thue') or '',
        'submitted_at': row.get('ngay_nop') or '',
        'integrity': row.get('_integrity_status') or 'unverified',
    })

    for item in list_feedback_items(row, taxpayer_key=taxpayer_key):
        asset = item.asset
        add('phan-hoi', Path(asset.path_or_handle), asset.original_filename, {
            'feedback_key': item.feedback.feedback_key,
            'type': item.feedback.feedback_type,
            'number': item.feedback.notice_number,
            'issued_at': item.feedback.issued_at,
            'result': item.feedback.business_result,
            'integrity': asset.integrity_status,
        })

    if not files:
        raise ValueError('Không có tệp hồ sơ hoặc phản hồi nào để xuất; '
                         'hãy tải hồ sơ/phản hồi trước.')
    for _, source in files:
        if target.resolve() == source.resolve():
            raise ValueError('Không ghi đè tệp hồ sơ gốc; chọn tên ZIP khác.')

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=f'.{target.name}.',
                                         suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
            for archive_name, source in files:
                archive.write(source, arcname=archive_name)
            archive.writestr(MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2))
        replace_with_retry(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return BundleResult(path=target, included=[name for name, _ in files],
                        missing=list(manifest['missing']), manifest=manifest)


__all__ = ['BundleResult', 'MANIFEST_NAME', 'SCHEMA_VERSION', 'export_submission_bundle',
           'safe_archive_name']
