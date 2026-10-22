"""Adapters call the same pipelines/functions as the seven CLI entrypoints."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from gdt_tax import classify, export, inventory
from gdt_tax.config import Settings
from gdt_tax.errors import LegacyPageError, SchemaChangedError, StorageError
from gdt_tax.gnt.pipeline import GntPipeline
from gdt_tax.gnt.storage import write_gnt_metadata
from gdt_tax.http import HttpClient
from gdt_tax.identity import account_fingerprint, scope_targets
from gdt_tax.legacy_session import SessionExpired
from gdt_tax.parser.cli import PARSED_NAME, parse_manifest, write_parsed
from gdt_tax.parser.registry import load_registry
from gdt_tax.pipeline import Pipeline
from gdt_tax.proxy import parse_proxy
from gdt_tax.run_hooks import RunBudget, RunCancelled, RunHooks
from gdt_tax.storage import write_metadata
from gdt_tax.tb.pipeline import TbPipeline
from gdt_tax.tb.storage import write_tb_metadata

from .documents import KINDS, document_id, verify_rows
from .errors import storage_message
from .file_store import DesktopZipStore
from .notices import attachment_problem
from .settings_store import Preferences, check_writable_directory


@dataclass
class RunConfig:
    mode: str
    output: Path
    username: str = ""
    password: str = field(default="", repr=False)
    from_date: str = "01/06/2025"
    to_date: str = "30/06/2025"
    case_id: str = ""
    dry_run: bool = False
    source: Path | None = None
    stage: str = "all"
    preferences: Preferences = field(default_factory=Preferences)
    proxy: str = field(default="", repr=False)
    extra_headers: dict[str, str] = field(default_factory=dict, repr=False)
    dvc: bool = False
    filters: dict[str, str] = field(default_factory=dict)
    csv: bool = False
    forms_dir: str = ""
    rehash: bool = False
    batch_modes: tuple[str, ...] = ("tax", "gnt", "notice")
    action: str = ""
    target_ids: tuple[str, ...] | None = field(default=None, repr=False)
    input_rows: list[dict[str, Any]] = field(default_factory=list, repr=False)
    source_files: tuple[str, ...] = field(default=(), repr=False)
    report_path: Path | None = None
    budget: RunBudget | None = field(default=None, repr=False)

    def settings(self) -> Settings:
        p = self.preferences
        # Leave room for five automatic challenges followed by manual fallback.
        attempts = max(6, p.login_attempts) if p.solver == "ddddocr" else p.login_attempts
        searches = max(6, p.search_attempts) if p.solver == "ddddocr" else p.search_attempts
        return Settings.from_env(
            environ={}, env_file=None, username=self.username, password=self.password,
            from_date=self.from_date, to_date=self.to_date, download_dir=self.output,
            case_id=self.case_id if self.mode == "tax" else "", dry_run=self.dry_run,
            captcha_solver=p.solver, request_timeout=p.timeout, http_retries=p.retries,
            login_attempts=attempts, search_attempts=searches,
            pause_between_records=p.record_delay, pause_between_pages=p.page_delay,
            pause_jitter=p.jitter, page_size=p.page_size, max_days_per_search=p.max_days,
            header_profile=p.header_profile, proxy_url=self.proxy, extra_headers=self.extra_headers,
            etax_cutoff=p.cutoff, legacy_etax=True, dvc_enabled=self.dvc,
            log_file="", http_dump_dir="", captcha_plugins="", captcha_options={},
        )

    def normalized_selection(self) -> RunConfig:
        if self.mode not in ONLINE or self.target_ids is None and not self.case_id:
            return self
        settings = self.settings()
        sources = ({period.source for period in settings.periods() if settings.source_enabled(period.source)}
                   if self.mode == "tax" else {"GNT"} if self.mode == "gnt" else {"TB"})
        kind = {"tax": "DECLARATION", "gnt": "GNT", "notice": "NOTICE"}[self.mode]
        account = account_fingerprint(self.username)
        targets = (tuple(sorted(scope_targets(self.target_ids, account_key=account, sources=sources,
                                              document_kind=kind))) if self.target_ids is not None else None)
        case_id = (next(iter(scope_targets([self.case_id], account_key=account, sources=sources,
                                           document_kind=kind))) if self.case_id else "")
        return replace(self, target_ids=targets, case_id=case_id)

    def validate(self) -> None:
        if self.mode not in {"tax", "gnt", "notice", "offline", "login", "batch", "import", "saved"}:
            raise ValueError("Chế độ không hợp lệ")
        if self.action not in {"", "download_selected", "verify", "export_report"}:
            raise ValueError("Thao tác không hợp lệ")
        if self.action == "verify":
            return
        if self.action == 'export_report':
            if self.mode not in ONLINE:
                raise ValueError('Dùng chức năng Xuất Excel hiện có ở tab Phân tích XML')
            if self.report_path is None or self.report_path.suffix.lower() != '.xlsx':
                raise ValueError('Chọn tên tệp Excel .xlsx')
            self.report_path.parent.mkdir(parents=True, exist_ok=True)
            check_writable_directory(self.report_path.parent)
            return
        if self.mode == "offline":
            if self.source is None or not self.source.is_dir():
                raise ValueError("Chọn thư mục nguồn ZIP/XML tồn tại")
            if self.source_files and any(not Path(path).is_file() or not Path(path).resolve().is_relative_to(self.source.resolve())
                                         or Path(path).suffix.lower() not in {'.xml', '.zip'} for path in self.source_files):
                raise ValueError("Tệp đã chọn phải là XML/ZIP tồn tại trong thư mục nguồn")
            if self.stage not in {"all", "inventory", "parse", "classify", "export"}:
                raise ValueError("Bước offline không hợp lệ")
            if self.forms_dir and not Path(self.forms_dir).is_dir():
                raise ValueError("Thư mục mapping tùy chỉnh không tồn tại")
        elif self.mode != "saved":
            self.settings()
            self.normalized_selection()
        if self.mode in {"login", "saved"}:
            return
        if self.dry_run and self.mode in ONLINE:
            return  # GUI query writes neither attachments nor catalog/report files.
        self.output.mkdir(parents=True, exist_ok=True)
        check_writable_directory(self.output)


@dataclass
class JobResult:
    state: str
    message: str
    output: Path
    rows: list[dict[str, Any]] = field(default_factory=list)
    files: list[Path] = field(default_factory=list)
    discovered: int = 0
    downloaded: int = 0
    errors: int = 0
    skipped: int = 0
    children: dict[str, JobResult] = field(default_factory=dict)
    reused: int = 0
    issues: list[dict[str, str]] = field(default_factory=list)
    task_id: str = ""
    account_key: str = ""
    date_range: tuple[str, str] = ("", "")
    started_at: str = ""
    ended_at: str = ""
    operation: str = ""
    requested: int = 0
    error_code: str = ""
    attachment_results: dict[str, dict] = field(default_factory=dict)


ONLINE = {
    "tax": (Pipeline, write_metadata, "danh_sach_to_khai.xlsx"),
    "gnt": (GntPipeline, write_gnt_metadata, "danh_sach_giay_nop_tien.xlsx"),
    "notice": (TbPipeline, write_tb_metadata, "danh_sach_thong_bao.xlsx"),
}


def run_online(config: RunConfig, hooks: RunHooks, captcha: Any,
               logger: logging.Logger, http: Any = None, portal_factory: Any = None,
               *, close_resources: bool = True, propagate_auth: bool = False) -> JobResult:
    settings = config.settings()
    kind, writer, report = ONLINE[config.mode]
    http = http or HttpClient(timeout=settings.request_timeout, retries=settings.http_retries,
                              header_profile=settings.header_profile, proxy=parse_proxy(config.proxy),
                              extra_headers=config.extra_headers, hooks=hooks, logger=logger)
    kwargs = {"portal_factory": portal_factory} if portal_factory is not None else {}
    if config.mode == 'tax':
        kwargs['store'] = DesktopZipStore(config.output, logger, config.input_rows)
    pipeline = kind(settings, http, captcha, hooks=hooks, logger=logger,
                    persist_metadata=not config.dry_run and config.target_ids is None,
                    target_ids=set(config.target_ids) if config.target_ids is not None else None, **kwargs)
    result = JobResult("ERROR", "Tác vụ thất bại", config.output)
    metadata_saved = False
    verified_rows: list[dict] = []
    try:
        summary = pipeline.run()
        complete = summary.search_complete if config.mode == "tax" and config.dry_run else (True if config.dry_run else summary.complete)
        if config.target_ids is not None:
            complete = set(pipeline.target_ids or ()).issubset(pipeline.downloaded_ids) and getattr(summary, 'attachments_complete', True)
        result.skipped = getattr(summary, "skipped_periods", 0)
        result.state = "SUCCESS" if complete else "PARTIAL"
        result.message = "Tra cứu hoàn tất" if config.dry_run else "Thành công"
        if not complete:
            result.message = "Chưa đầy đủ — có hồ sơ hoặc đoạn ngày bị bỏ qua"
            primary_complete = (set(pipeline.target_ids or ()).issubset(pipeline.downloaded_ids)
                                if config.target_ids is not None else getattr(summary, 'primary_complete', False))
            if primary_complete and not getattr(summary, 'attachments_complete', True):
                result.message = 'Đã tải tệp hồ sơ chính; thông báo cơ quan thuế chưa đầy đủ'
        elif summary.discovered == 0:
            result.message = "Không có kết quả"
    except RunCancelled:
        result.state, result.message = "CANCELLED", "Đã dừng — còn dữ liệu chưa xử lý"
    except SchemaChangedError as error:
        result.state = "PARTIAL" if pipeline.records else "ERROR"
        result.message = str(error)
        result.errors = 1
    except SessionExpired as error:
        if propagate_auth:
            raise
        result.state, result.message = "ERROR", "Phiên ETAX hết hạn; đăng nhập lại để tiếp tục"
        result.error_code = error.code
    except LegacyPageError as error:
        # Unknown page structure is not evidence that authentication expired.
        if propagate_auth:
            raise
        result.state, result.message = "ERROR", str(error)
        result.error_code = error.code
    except (StorageError, PermissionError) as error:
        logger.error("%s", error)
        result.state = "ERROR"
        result.message = storage_message(error)
        if pipeline.active_record_id:
            pipeline.failed_ids.add(pipeline.active_record_id)
            pipeline.record_errors[pipeline.active_record_id] = result.message
    except Exception as error:
        result.state, result.message = "ERROR", str(error)
        result.error_code = getattr(error, 'code', '')
        if pipeline.active_record_id and pipeline.active_record_id not in pipeline.downloaded_ids:
            pipeline.failed_ids.add(pipeline.active_record_id)
            pipeline.record_errors[pipeline.active_record_id] = str(error)
    finally:
        # Flush a discovered record even if a detail request/captcha was cancelled.
        try:
            if pipeline.records:
                verified_rows = verify_rows(config.mode, [record.to_dict() for record in pipeline.records.values()],
                    config.output, failed_ids=pipeline.failed_ids, errors=pipeline.record_errors,
                    reused_ids=pipeline.reused_ids)
                _, id_field, file_field, *_ = KINDS[config.mode]
                for row in verified_rows:
                    setattr(pipeline.records[document_id(config.mode, row)], file_field, row.get(file_field, ""))
                try:
                    if not config.dry_run:
                        writer(config.output, pipeline.records)
                        metadata_saved = True
                except (StorageError, OSError) as error:
                    result.state = "ERROR"
                    result.message = storage_message(error, 'Không lưu được danh mục')
                    logger.error(result.message)
        finally:
            if close_resources:
                http.close()
                captcha.close()
    result.rows = verified_rows
    result.discovered = len(result.rows)
    result.downloaded = len(pipeline.downloaded_ids)
    missing = set(pipeline.target_ids or ()) - pipeline.records.keys()
    result.errors = max(result.errors, len(pipeline.failed_ids), int(result.state == "ERROR")) + len(missing)
    result.reused = len(pipeline.reused_ids)
    result.attachment_results = {key: item.to_dict() for key, item in getattr(pipeline, 'attachments', {}).items()}
    result.account_key = account_fingerprint(config.username)
    result.date_range = (config.from_date, config.to_date)
    result.operation = config.action or ('query' if config.dry_run else 'query_and_download')
    result.requested = len(config.target_ids) if config.target_ids is not None else (0 if config.dry_run else result.discovered)
    result.issues = [{"document_id": document_id(config.mode, row), "message": row["_error_message"]}
                     for row in result.rows if row.get("_error_message")]
    result.issues.extend({"document_id": key, "message": "Hồ sơ không còn trong kết quả tra cứu của kỳ đã chọn; chưa tải tệp."} for key in sorted(missing))
    for key, value in result.attachment_results.items():
        if message := attachment_problem(value):
            result.issues.append({'document_id': key, 'message': message})
    if result.state in {"ERROR", "PARTIAL"} and not result.issues:
        result.issues.append({"document_id": "", "message": result.message})
    # Only advertise reports actually produced by this job.
    if metadata_saved and (config.output / report).is_file():
        result.files = [config.output / report]
    return result


def _read(path: Path) -> dict:
    if not path.is_file():
        raise ValueError(f"Thiếu {path.name}; chạy bước trước trong cùng thư mục kết quả")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} không phải dữ liệu hợp lệ")
    return data


def run_offline(config: RunConfig, hooks: RunHooks, logger: logging.Logger) -> JobResult:
    root, output = config.source, config.output
    assert root is not None
    stages = ["inventory", "parse", "classify", "export"] if config.stage == "all" else [config.stage]
    result = JobResult("SUCCESS", "Thành công", output)
    skipped_ids: set[str] = set()
    for stage in stages:
        try:
            hooks.check()
            hooks.emit(stage=stage)
            logger.info("Offline: %s", stage)
            if stage == "inventory":
                cache = {} if config.rehash else inventory.load_cache(output / inventory.MANIFEST_NAME)
                manifest = inventory.scan_directory(root, metadata_path=root / "danh_sach_ho_so.json",
                                                     cache=cache, force=config.rehash, hooks=hooks,
                                                     selected_paths=[Path(p) for p in config.source_files] if config.source_files else None)
                result.files.append(inventory.write_manifest(manifest, output))
                result.files.extend(inventory.write_discovery(inventory.build_discovery(manifest), output))
                result.errors += len(manifest.errors) + sum(
                    a.status == "error" or (a.xml is not None and a.xml.status == "error")
                    for c in manifest.containers for a in c.members)
                result.discovered = len(manifest.containers)
            else:
                manifest_data = _read(output / inventory.MANIFEST_NAME)
                if Path(manifest_data.get("root", "")).resolve() != root.resolve():
                    raise ValueError("Manifest thuộc nguồn khác; chạy Kiểm kê lại với thư mục nguồn hiện tại")
                if config.source_files:
                    expected = {Path(p).relative_to(root).as_posix() for p in config.source_files}
                    actual = {c.get('rel_path') for c in manifest_data.get('containers', [])}
                    if expected != actual:
                        raise ValueError("Manifest thuộc bộ tệp khác; chạy Kiểm kê lại hoặc Chạy toàn bộ")
                if stage == "parse":
                    rows = parse_manifest(manifest_data, root, registry=load_registry(config.forms_dir or None), hooks=hooks)
                    result.files.append(write_parsed(rows, output, manifest=manifest_data))
                    result.rows = rows
                    result.discovered = len(rows)
                    result.errors += sum(r.get("status") == "error" for r in rows)
                    skipped_ids.update(str(r.get("artifact_id")) for r in rows if (r.get("status") == "NEED_MAPPING" or r.get("validation_status") == "PARTIAL"))
                    result.skipped = len(skipped_ids)
                elif stage == "classify":
                    registry = load_registry(config.forms_dir or None)
                    rows = classify.classify_manifest(manifest_data, registry=registry, hooks=hooks)
                    target = output / classify.CLASSIFICATION_NAME
                    classify._atomic_write_json(target, classify.classification_payload(manifest_data, rows, registry))
                    result.files.append(target)
                    skipped_ids.update(str(r.get("artifact_id")) for r in rows if r.get("status") != "OK")
                    result.skipped = len(skipped_ids)
                    if config.stage != "all":
                        result.rows, result.discovered = rows, len(rows)
                else:
                    parsed = _read(output / PARSED_NAME)
                    classified = _read(output / classify.CLASSIFICATION_NAME)
                    rows = export.filter_rows(export.build_rows(manifest_data, parsed, classified, allow_legacy=False), **config.filters)
                    hooks.check()
                    result.files.append(export.write_workbook(export.build_workbook(rows, manifest_data, parsed, classified), output / export.WORKBOOK_NAME))
                    if config.csv:
                        result.files.append(export.write_csv(output / "Tax_Return_Summary.csv", rows))
                    result.rows, result.discovered = rows, len(rows)
                    if config.stage == "export":
                        result.errors = sum(r.get("status") == "error" for r in rows)
                        result.skipped = sum((r.get("status") == "NEED_MAPPING" or r.get("validation_status") == "PARTIAL") or r.get("classification_status") != "OK" for r in rows)
            hooks.emit(discovered=result.discovered, downloaded=0)
            hooks.check()
        except RunCancelled:
            result.state, result.message = "CANCELLED", "Đã dừng — còn dữ liệu chưa xử lý"
            return result
        except Exception as error:
            result.state, result.message = "ERROR", f"Bước {stage}: {error}"
            result.errors += 1
            return result
    if result.errors or result.skipped:
        result.state, result.message = "PARTIAL", "Đã ghi kết quả; có lỗi hoặc mẫu chưa mapping/phân loại"
    elif result.discovered == 0:
        result.message = "Không có kết quả"
    return result
