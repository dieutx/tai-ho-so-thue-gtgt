"""Qt worker, bounded log bridge and a cancellable GUI CAPTCHA rendezvous."""
from __future__ import annotations

import base64
import hashlib
import logging
import re
import time
from collections import deque
from dataclasses import replace
from datetime import datetime, timezone
from threading import Event, Lock
from uuid import uuid4

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot

from gdt_tax.captcha.base import CaptchaSolver, normalize_text
from gdt_tax.captcha.ddddocr_solver import DdddOcrSolver
from gdt_tax.errors import CaptchaError, StorageError
from gdt_tax.proxy import parse_proxy
from gdt_tax.redaction import redact_text
from gdt_tax.run_hooks import RunCancelled, RunHooks

from .documents import counters, verify_rows
from .errors import storage_message
from .services import JobResult, RunConfig, run_offline
from .sessions import ETaxSessionManager
from .state import job_output


class Redactor:
    def __init__(self, config: RunConfig) -> None:
        proxy = parse_proxy(config.proxy)
        values = [config.password, config.username, config.proxy,
                  base64.b64encode(config.password.encode()).decode() if config.password else ""]
        values.extend(config.extra_headers.values())
        if proxy:
            values.extend(proxy.secrets())
        self.secrets = sorted({x for x in values if x}, key=len, reverse=True)

    def __call__(self, text: str) -> str:
        for value in self.secrets:
            text = text.replace(value, "***")
        text = redact_text(text)
        text = re.sub(r"(?i)((?:password|matkhau|token|cookie|authorization|dse_sessionId|csrf)\s*[=:]\s*)[^\s,;]+", r"\1***", text)
        text = re.sub(r"(?<!\w)\d{10,}(?!\w)", "***", text)
        text = re.sub(r"(?i)([A-Z]:[\\/](?:Users|Documents and Settings)[\\/])[^\\/]+", r"\1***", text)
        return text


class LogBridge(logging.Handler):
    def __init__(self, redactor: Redactor) -> None:
        super().__init__(logging.INFO)
        self.redactor = redactor
        self.pending: deque[tuple[int, str]] = deque(maxlen=2000)
        self.lock_queue = Lock()

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        # Raw transport/HTML is intentionally never exposed in desktop logs.
        if message.startswith(("HTTP ", "LOGIN:", "GỬI ", "  ")):
            return
        with self.lock_queue:
            self.pending.append((record.levelno, self.redactor(message)))

    def drain(self) -> list[tuple[int, str]]:
        with self.lock_queue:
            batch = list(self.pending)
            self.pending.clear()
        return batch


class CaptchaRequest:
    def __init__(self, image: bytes, message: str = "Nhập mã CAPTCHA trong ảnh để tiếp tục.") -> None:
        self.image = image
        self.message = message
        self.ready = Event()
        self.answer: str | None = None

    def respond(self, value: str | None) -> None:
        self.answer = value
        self.ready.set()


class GuiCaptchaSolver(CaptchaSolver):
    name = "gui"
    AUTO_ATTEMPTS = 5

    def __init__(self, hooks: RunHooks, request, use_ocr: bool = True) -> None:
        super().__init__()
        self.hooks, self.request = hooks, request
        self.ocr = DdddOcrSolver() if use_ocr else None
        self.auto_failures = 0
        self.last_was_auto = False
        self.manual_fallback_pending = False

    def _check_manual_fallback(self) -> None:
        if self.ocr and self.manual_fallback_pending:
            message = ("Cổng chưa xác nhận yêu cầu sau lượt nhập tay CAPTCHA. Đã dừng để tránh hỏi mã liên tục. "
                       "Kiểm tra mã CAPTCHA, tài khoản/mật khẩu và kết nối, rồi thử lại tác vụ.")
            self.logger.warning(message)
            self.hooks.emit(captcha_message=message)
            raise CaptchaError(message)

    def rejected(self) -> None:
        self._check_manual_fallback()
        if self.last_was_auto:
            self.auto_failures += 1
            self.last_was_auto = False
            self.logger.warning("Cổng chưa chấp nhận yêu cầu dùng CAPTCHA tự động (lần %s/%s); chưa xác định nguyên nhân", self.auto_failures, self.AUTO_ATTEMPTS)
            self.hooks.emit(captcha_message=f"Yêu cầu dùng CAPTCHA tự động chưa được chấp nhận ({self.auto_failures}/{self.AUTO_ATTEMPTS})")

    def accepted(self) -> None:
        self.auto_failures = 0
        self.last_was_auto = False
        self.manual_fallback_pending = False

    def solve(self, image: bytes) -> str:
        self.hooks.check()
        self._check_manual_fallback()
        self.last_was_auto = False
        if self.ocr and self.auto_failures < self.AUTO_ATTEMPTS:
            attempt = self.auto_failures + 1
            self.hooks.emit(captcha_message=f"Đang đọc CAPTCHA tự động ({attempt}/{self.AUTO_ATTEMPTS})…")
            try:
                result = self.ocr.solve(image)
                if result:
                    self.last_was_auto = True
                    return result
                self.logger.warning("OCR trả kết quả rỗng hoặc sai độ dài (lần %s/%s)", attempt, self.AUTO_ATTEMPTS)
            except RunCancelled:
                raise
            except Exception as error:
                # Exception messages may contain local paths or private input.
                self.logger.warning("OCR lỗi %s (lần %s/%s)", type(error).__name__, attempt, self.AUTO_ATTEMPTS)
            self.hooks.check()
            self.auto_failures += 1
            if self.auto_failures < self.AUTO_ATTEMPTS:
                self.logger.info("Lấy ảnh CAPTCHA mới để thử tự động (%s/%s)", self.auto_failures + 1, self.AUTO_ATTEMPTS)
                return ""  # The portal's bounded retry fetches a fresh image.
        message = (f"Đã thử CAPTCHA tự động {self.AUTO_ATTEMPTS} lần nhưng chưa thành công. "
                   "Bạn vui lòng nhập mã trong ảnh để tiếp tục."
                   if self.ocr else "Bạn đang chọn chế độ nhập CAPTCHA bằng tay. Nhập mã trong ảnh để tiếp tục.")
        self.logger.warning(message)
        self.hooks.emit(captcha_message=message)
        challenge = CaptchaRequest(image, message)
        self.request(challenge)
        deadline = time.monotonic() + 180
        while not challenge.ready.wait(0.1):
            self.hooks.check()
            if time.monotonic() > deadline:
                raise RunCancelled("Hết thời gian nhập CAPTCHA")
        self.hooks.check()
        if challenge.answer is None:
            if self.hooks.cancel:
                self.hooks.cancel.set()
            raise RunCancelled("Đã hủy CAPTCHA")
        self.manual_fallback_pending = self.ocr is not None
        return normalize_text(challenge.answer)

    def close(self) -> None:
        if self.ocr:
            self.ocr.close()


class Worker(QObject):
    progress = Signal(object)
    captcha = Signal(object)
    done = Signal(object)

    def __init__(self, config: RunConfig, cancel: Event, redactor: Redactor, sessions: ETaxSessionManager) -> None:
        super().__init__()
        self.config, self.cancel, self.redactor = config, cancel, redactor
        self.sessions = sessions

    @Slot()
    def run(self) -> None:
        hooks = RunHooks(self.cancel, self.progress.emit)
        started_at = datetime.now(timezone.utc).isoformat()
        task_id = uuid4().hex[:12]
        try:
            hooks.check()
            self.config.validate()
            self.progress.emit({"state": "RUNNING"})
            logger = logging.getLogger("gdt_tax.desktop")
            if self.config.mode in {"import", "saved"}:
                from .migration import load_saved
                result = load_saved(self.config, hooks, copy_files=self.config.mode == "import")
                result.rows = verify_rows(self.config.stage, result.rows, result.output, hooks)
            elif self.config.mode == "offline":
                result = run_offline(self.config, hooks, logger)
            elif self.config.action == "verify":
                rows = verify_rows(self.config.mode, self.config.input_rows, self.config.output, hooks)
                counts = counters(rows)
                result = JobResult("SUCCESS", "Đã kiểm tra tệp trên máy", self.config.output,
                    rows=rows, discovered=len(rows), downloaded=counts["downloaded"], errors=counts["failed"])
            elif self.config.action == 'export_report':
                from .reports import export_document_report
                result = export_document_report(self.config, hooks)
            else:
                solver = GuiCaptchaSolver(hooks, self.captcha.emit, self.config.preferences.solver == "ddddocr")
                try:
                    if self.config.mode == "batch":
                        result = JobResult("SUCCESS", "Đã hoàn tất các tác vụ", self.config.output)
                        for mode in self.config.batch_modes:
                            config = replace(self.config, mode=mode, output=job_output(self.config.output, self.config.username, mode))
                            try:
                                hooks.check()
                                hooks.emit(active_mode=mode)
                                config.validate()
                                child = self.sessions.execute(config, hooks, solver, logger)
                            except RunCancelled:
                                result.state, result.message = "CANCELLED", "Đã dừng; các nhóm hoàn thành trước đó được giữ"
                                break
                            except Exception as error:
                                child = JobResult("ERROR", self.redactor(str(error)), config.output, errors=1)
                            result.children[mode] = child
                            result.files.extend(child.files)
                            result.discovered += child.discovered
                            result.downloaded += child.downloaded
                            result.errors += child.errors
                            result.skipped += child.skipped
                            result.reused += child.reused
                            result.requested += child.requested
                            result.issues.extend(child.issues)
                            if child.state == "CANCELLED":
                                result.state, result.message = child.state, child.message
                                break
                            if child.state != "SUCCESS":
                                result.state, result.message = "PARTIAL", "Hoàn tất một phần các tác vụ"
                    else:
                        result = self.sessions.execute(self.config, hooks, solver, logger)
                finally:
                    solver.close()
            result.message = self.redactor(result.message)
        except RunCancelled as error:
            result = JobResult("CANCELLED", str(error), self.config.output)
        except Exception as error:
            logging.getLogger('gdt_tax.desktop').error('Tác vụ thất bại: %s', self.redactor(str(error)))
            message = storage_message(error) if isinstance(error, (OSError, StorageError)) else str(error)
            result = JobResult("ERROR", self.redactor(message), self.config.output,
                               error_code=getattr(error, 'code', ''))
        result.task_id = task_id
        if result.state == 'ERROR' and not result.issues:
            result.errors = max(1, result.errors)
            result.issues.append({'document_id': '', 'message': result.message})
        result.operation = self.config.action or (self.config.mode if self.config.mode in {"offline", "login", "saved", "import"}
                                                  else "query" if self.config.dry_run else "query_and_download")
        result.started_at, result.ended_at = started_at, datetime.now(timezone.utc).isoformat()
        result.account_key = hashlib.sha256(self.config.username.encode()).hexdigest()
        result.date_range = (self.config.from_date, self.config.to_date)
        for item in [result, *result.children.values()]:
            item.message = self.redactor(item.message)
            item.account_key = result.account_key
            item.date_range = result.date_range
            item.operation = result.operation
            for issue in item.issues:
                issue["message"] = self.redactor(issue.get("message", ""))
            for row in item.rows:
                if row.get("_error_message"):
                    row["_error_message"] = self.redactor(row["_error_message"])
        self.done.emit(result)


class JobController(QObject):
    progress = Signal(object)
    captcha = Signal(object)
    completed = Signal(object)
    logs = Signal(object)
    state_changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.thread: QThread | None = None
        self.worker: Worker | None = None
        self.cancel = Event()
        self.bridge: LogBridge | None = None
        self.result: JobResult | None = None
        self.state = "IDLE"
        self.sessions = ETaxSessionManager()
        self.timer = QTimer(self)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self._drain)

    @property
    def busy(self) -> bool:
        return self.thread is not None

    def _state(self, state: str) -> None:
        self.state = state
        self.state_changed.emit(state)

    def start(self, config: RunConfig) -> bool:
        if self.busy:
            return False
        self.cancel = Event()
        redactor = Redactor(config)
        self.bridge = LogBridge(redactor)
        self.logger = logging.getLogger("gdt_tax")
        self.old_level = self.logger.level
        self.old_propagate = self.logger.propagate
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        self.logger.addHandler(self.bridge)
        self.result = None
        self.thread = QThread(self)
        self.worker = Worker(config, self.cancel, redactor, self.sessions)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._progress)
        self.worker.captcha.connect(self._captcha)
        self.worker.done.connect(self._done)
        self.worker.done.connect(self.worker.deleteLater)
        self.worker.done.connect(self.thread.quit)
        self.thread.finished.connect(self._finished)
        self._state("VALIDATING")
        self.timer.start()
        self.thread.start()
        return True

    @Slot(object)
    def _progress(self, payload) -> None:
        if "state" in payload and self.state != "STOPPING":
            self._state(payload["state"])
        self.progress.emit(payload)

    @Slot(object)
    def _captcha(self, request) -> None:
        if self.cancel.is_set():
            request.respond(None)
            return
        self._state("WAITING_CAPTCHA")
        self.captcha.emit(request)

    def resume(self) -> None:
        if self.busy and not self.cancel.is_set():
            self._state("RUNNING")

    def stop(self) -> None:
        if self.busy:
            self.cancel.set()
            self._state("STOPPING")

    @Slot(object)
    def _done(self, result) -> None:
        self.result = result

    @Slot()
    def _finished(self) -> None:
        self._drain()
        self.timer.stop()
        if self.bridge:
            self.logger.removeHandler(self.bridge)
            self.bridge.close()
        self.logger.setLevel(self.old_level)
        self.logger.propagate = self.old_propagate
        thread = self.thread
        self.thread, self.worker = None, None
        if thread:
            thread.deleteLater()
        if self.result:
            self._state(self.result.state)
            self.completed.emit(self.result)

    def _drain(self) -> None:
        if self.bridge:
            batch = self.bridge.drain()
            if batch:
                self.logs.emit(batch)
