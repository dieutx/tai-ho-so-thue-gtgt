"""Cấu hình log ra màn hình và (nếu muốn) ra file cho cả Windows và Linux."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%H:%M:%S"


def configure_logging(verbose: bool = False, log_file: str | Path | None = None) -> None:
    """Bật log ra stdout, tránh lỗi mã hóa tiếng Việt trên Windows.

    Khi có ``log_file``, ghi thêm toàn bộ log vào file đó ở mức ``DEBUG`` — kể cả
    header và body của từng request (đã che dữ liệu nhạy cảm). Nhờ vậy người dùng
    có sẵn một file đầy đủ để gửi kèm khi cổng đổi giao diện, không phải chạy lại
    ở chế độ verbose.
    """
    _reconfigure_streams()

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    handlers: list[logging.Handler] = [console]

    if log_file:
        file_handler = _file_handler(log_file)
        file_handler.setLevel(logging.DEBUG)
        handlers.append(file_handler)

    logging.basicConfig(
        level=logging.DEBUG if (verbose or log_file) else logging.INFO,
        format=LOG_FORMAT,
        datefmt=DATE_FORMAT,
        handlers=handlers,
        force=True,
    )


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


__all__ = ["DATE_FORMAT", "LOG_FORMAT", "configure_logging"]
