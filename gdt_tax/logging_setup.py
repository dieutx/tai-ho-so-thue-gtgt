"""Cấu hình log ra màn hình và (nếu muốn) ra file cho cả Windows và Linux."""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterable
from pathlib import Path

from .traffic import mask_secrets

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%H:%M:%S"
_OWNED_HANDLERS: set[logging.Handler] = set()


class SecretsFilter(logging.Filter):
    """Che mật khẩu (proxy, CAPTCHA ngoài...) khỏi mọi bản ghi log.

    Cần đến lớp này vì mật khẩu proxy còn xuất hiện trong log của thư viện khác,
    ví dụ ``urllib3`` in ra địa chỉ proxy kèm tài khoản. Filter gắn ở handler nên
    áp dụng cho mọi logger, không chỉ ``gdt_tax``.

    Giới hạn: chỉ che phần ``message`` và ``exc_text`` của bản ghi; traceback do
    Python tự in ra (khi có lỗi ngoài dự kiến) không đi qua đây. Vì vậy
    ``HttpClient`` mới đổi lỗi mạng thành ``NetworkError`` đã che sẵn.
    """

    def __init__(self, secrets: Iterable[str] = ()) -> None:
        super().__init__()
        self.secrets = tuple(secret for secret in secrets if secret)

    def filter(self, record: logging.LogRecord) -> bool:
        if not self.secrets:
            return True
        message = record.getMessage()
        masked = mask_secrets(message, self.secrets)
        if masked != message:
            record.msg = masked
            record.args = ()
        if record.exc_text:
            record.exc_text = mask_secrets(record.exc_text, self.secrets)
        return True


def configure_logging(
    verbose: bool = False,
    log_file: str | Path | None = None,
    secrets: Iterable[str] = (),
) -> None:
    """Bật log ra stdout, tránh lỗi mã hóa tiếng Việt trên Windows.

    Khi có ``log_file``, ghi thêm toàn bộ log vào file đó ở mức ``DEBUG`` — kể cả
    header và body của từng request (đã che dữ liệu nhạy cảm). Nhờ vậy người dùng
    có sẵn một file đầy đủ để gửi kèm khi cổng đổi giao diện, không phải chạy lại
    ở chế độ verbose.
    """
    _reconfigure_streams()
    close_logging()

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    handlers: list[logging.Handler] = [console]

    if log_file:
        file_handler = _file_handler(log_file)
        file_handler.setLevel(logging.DEBUG)
        handlers.append(file_handler)

    if secrets:
        secrets_filter = SecretsFilter(secrets)
        for handler in handlers:
            handler.addFilter(secrets_filter)

    _OWNED_HANDLERS.update(handlers)

    logging.basicConfig(
        level=logging.DEBUG if (verbose or log_file) else logging.INFO,
        format=LOG_FORMAT,
        datefmt=DATE_FORMAT,
        handlers=handlers,
        force=True,
    )


def close_logging() -> None:
    """Giải phóng handler do CLI tạo, kể cả khi main() chạy nhiều lần trên Windows."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        if handler in _OWNED_HANDLERS:
            root.removeHandler(handler)
            handler.close()
            _OWNED_HANDLERS.discard(handler)


def _reconfigure_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def _file_handler(log_file: str | Path) -> logging.FileHandler:
    """Mở file log ở chế độ ghi thêm, tạo thư mục cha nếu còn thiếu."""
    path = Path(log_file)
    if not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    return handler


__all__ = ["DATE_FORMAT", "LOG_FORMAT", "SecretsFilter", "close_logging", "configure_logging"]
