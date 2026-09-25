"""Quan sát traffic HTTP: che dữ liệu nhạy cảm, định dạng log và lưu file.

Module này phục vụ việc bảo trì. Khi cổng Dịch vụ công đổi giao diện, cách sửa
nhanh nhất là thay fixture trong ``tests/fixtures/`` rồi chạy lại test; nếu không
có sẵn HTML thật thì phải tự dò lại từ đầu. Vì vậy mọi request/response đi qua
:class:`~gdt_tax.http.HttpClient` đều có thể:

* được log một dòng ngắn ở mức ``INFO`` để nhìn thấy chuyện gì đang xảy ra,
* được log đầy đủ header/body ở mức ``DEBUG`` (``-v``, hoặc luôn có trong file
  log khi dùng ``--log-file``),
* được lưu nguyên văn ra file khi chạy với ``--dump-http``.

Header nhạy cảm (``Cookie``, ``Authorization``...) và trường nhạy cảm trong body
(``matKhau``, ``_csrf``...) luôn bị che bằng ``***`` trước khi ghi ra log hay ra
file, nên có thể gửi kèm log cho người khác mà không lộ phiên đăng nhập.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

LOGGER_NAME = "gdt_tax.traffic"

#: Header chứa phiên đăng nhập hoặc khoá truy cập — luôn bị che.
SENSITIVE_HEADERS = frozenset(
    {"cookie", "set-cookie", "authorization", "proxy-authorization", "x-xsrf-token"}
)
#: Trường trong body bị che (so khớp không phân biệt hoa thường).
SENSITIVE_FIELDS = frozenset(
    {"matkhau", "mat_khau", "password", "pwd", "_csrf", "token", "api_key"}
)
MASK = "***"
#: Độ dài tối đa của body khi in ra log.
BODY_LOG_LIMIT = 500
#: Giới hạn mặc định cho mỗi file dump (2 MB).
DEFAULT_MAX_BODY_BYTES = 2_000_000
_SLUG_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def mask_secrets(text: str, secrets: Iterable[str] = ()) -> str:
    """Thay mọi chuỗi bí mật (mật khẩu proxy...) trong ``text`` bằng ``***``.

    Dùng cho thông báo lỗi và cho :class:`gdt_tax.logging_setup.SecretsFilter`, vì
    lỗi mạng của ``requests`` thường in cả URL proxy kèm tài khoản.
    """
    masked = text
    for secret in secrets:
        if secret:
            masked = masked.replace(secret, MASK)
    return masked


def mask_headers(headers: Mapping[str, Any] | None) -> dict[str, str]:
    """Bản sao header đã che giá trị nhạy cảm; dùng cho cả log và file dump."""
    masked: dict[str, str] = {}
    for name, value in (headers or {}).items():
        masked[str(name)] = MASK if str(name).lower() in SENSITIVE_HEADERS else str(value)
    return masked


def mask_data(data: Any) -> Any:
    """Che giá trị của các trường nhạy cảm trong dict/list, giữ nguyên phần còn lại."""
    if isinstance(data, Mapping):
        return {
            key: (MASK if str(key).lower() in SENSITIVE_FIELDS else mask_data(value))
            for key, value in data.items()
        }
    if isinstance(data, (list, tuple)):
        if all(isinstance(item, (list, tuple)) and len(item) == 2 for item in data):
            # form-urlencoded dạng danh sách (tên, giá trị)
            return [
                (key, MASK if str(key).lower() in SENSITIVE_FIELDS else value)
                for key, value in data
            ]
        return [mask_data(item) for item in data]
    return data


def body_as_text(body: Any) -> str:
    """Đổi body bất kỳ thành chuỗi; cấu trúc dict/list được che rồi ghi dạng JSON."""
    if isinstance(body, bytes):
        return body.decode("utf-8", errors="replace")
    if body is None:
        return ""
    if isinstance(body, str):
        return body
    return json.dumps(mask_data(body), ensure_ascii=False, default=str)


def describe_body(body: Any, *, limit: int = BODY_LOG_LIMIT) -> str:
    """Body dạng một dòng đã che dữ liệu nhạy cảm, cắt bớt nếu quá dài."""
    text = body_as_text(body)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}… (+{len(text) - limit} ký tự)"


def describe_params(params: Any, *, limit: int = BODY_LOG_LIMIT) -> str:
    """Tham số query dạng ``ten=gia-tri&...`` đã che dữ liệu nhạy cảm.

    Viết giống query string thật để đọc log là đối chiếu được ngay với URL trên
    trình duyệt, thay vì phải tự dịch từ JSON.
    """
    if isinstance(params, Mapping):
        text = "&".join(
            f"{key}={MASK if str(key).lower() in SENSITIVE_FIELDS else value}"
            for key, value in params.items()
        )
    else:
        text = body_as_text(params)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}… (+{len(text) - limit} ký tự)"


def format_size(size: int) -> str:
    """Dung lượng dạng dễ đọc: ``812 B``, ``12.4 kB``, ``1.2 MB``."""
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} kB"
    return f"{size / (1024 * 1024):.1f} MB"


def slug(url: str) -> str:
    """Phần đường dẫn của URL, làm sạch để dùng được trong tên file."""
    without_scheme = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", "", url)
    path = without_scheme.split("/", 1)[-1] if "/" in without_scheme else without_scheme
    path = path.split("?", 1)[0]
    cleaned = _SLUG_UNSAFE.sub("-", path).strip("-")
    return (cleaned or "root")[:60]


class TrafficDumper:
    """Lưu từng cặp request/response thành file để dựng lại fixture khi cổng đổi.

    Mỗi lần chạy tạo một thư mục con theo thời điểm bắt đầu, nên chạy lại không
    ghi đè kết quả cũ. Mỗi cặp request/response thành tối đa ba file::

        <thời điểm>/0001-GET-ho-so-search.request.txt    phương thức, URL, header, body
        <thời điểm>/0001-GET-ho-so-search.response.txt   mã trạng thái, header, body
        <thời điểm>/0001-GET-ho-so-search.response.body  body nguyên bản (nhị phân)

    File ``.response.body`` giữ nguyên byte gốc nên có thể so sánh chính xác với
    phản hồi thật, còn ``.response.txt`` để đọc bằng mắt.
    """

    def __init__(
        self,
        directory: str | Path,
        *,
        max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
        logger: logging.Logger | None = None,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.max_body_bytes = max_body_bytes
        self.logger = logger or logging.getLogger(LOGGER_NAME)
        self.root = Path(directory) / clock().strftime("%Y%m%d-%H%M%S")
        self.count = 0

    def record(
        self,
        *,
        method: str,
        url: str,
        response: Any,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, Any] | None = None,
        body: Any = None,
        elapsed: float = 0.0,
    ) -> list[Path]:
        """Ghi một request và phản hồi của nó; trả về danh sách file đã tạo."""
        self.count += 1
        if self.count == 1:
            self.root.mkdir(parents=True, exist_ok=True)
            self.logger.info("Lưu traffic HTTP vào %s", self.root)

        stem = f"{self.count:04d}-{method.upper()}-{slug(url)}"
        paths = [self._write_request(stem, method, url, params, headers, body)]
        paths.extend(self._write_response(stem, response, elapsed))
        return paths

    def _write_request(
        self,
        stem: str,
        method: str,
        url: str,
        params: Mapping[str, Any] | None,
        headers: Mapping[str, Any] | None,
        body: Any,
    ) -> Path:
        lines = [f"{method.upper()} {url}"]
        if params:
            lines.append(f"tham số: {describe_params(params, limit=self.max_body_bytes)}")
        lines += ["", "[header]"]
        lines += [f"{name}: {value}" for name, value in mask_headers(headers).items()]
        text = describe_body(body, limit=self.max_body_bytes)
        if text:
            lines += ["", "[body]", text]
        return self._write_text(self.root / f"{stem}.request.txt", "\n".join(lines))

    def _write_response(self, stem: str, response: Any, elapsed: float) -> list[Path]:
        content = getattr(response, "content", b"") or b""
        status = getattr(response, "status_code", "-")
        lines = [
            f"HTTP {status} ({elapsed:.2f}s, {format_size(len(content))})",
            "",
            "[header]",
        ]
        lines += [
            f"{name}: {value}"
            for name, value in mask_headers(getattr(response, "headers", {})).items()
        ]
        body_text = describe_body(getattr(response, "text", ""), limit=self.max_body_bytes)
        if body_text:
            lines += ["", "[body]", body_text]

        paths = [self._write_text(self.root / f"{stem}.response.txt", "\n".join(lines))]
        if content:
            body_path = self.root / f"{stem}.response.body"
            if len(content) > self.max_body_bytes:
                truncated = content[: self.max_body_bytes]
                self._write_bytes(body_path, truncated)
                self.logger.warning(
                    "Body của %s vượt %s byte; file dump chỉ giữ phần đầu",
                    stem,
                    self.max_body_bytes,
                )
            else:
                self._write_bytes(body_path, content)
            paths.append(body_path)
        return paths

    def _write_text(self, path: Path, text: str) -> Path:
        path.write_text(text + "\n", encoding="utf-8")
        return path

    def _write_bytes(self, path: Path, data: bytes) -> Path:
        path.write_bytes(data)
        return path


__all__ = [
    "BODY_LOG_LIMIT",
    "DEFAULT_MAX_BODY_BYTES",
    "MASK",
    "SENSITIVE_FIELDS",
    "SENSITIVE_HEADERS",
    "TrafficDumper",
    "body_as_text",
    "describe_body",
    "describe_params",
    "format_size",
    "mask_data",
    "mask_headers",
    "mask_secrets",
    "slug",
]
