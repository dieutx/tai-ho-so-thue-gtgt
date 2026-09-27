"""Tiện ích dùng chung cho test: HTTP giả, solver giả, fixture và ZIP mẫu.

Các test chạy hoàn toàn offline: lớp :class:`FakeHttp` thay cho
``gdt_tax.http.HttpClient`` nên không có request nào ra Internet.
"""

from __future__ import annotations

import base64
import tempfile
import time
import zipfile
from collections import namedtuple
from io import BytesIO
from pathlib import Path

from gdt_tax.captcha.base import CaptchaSolver

FIXTURES = Path(__file__).parent / "fixtures"
Call = namedtuple("Call", "method path kwargs")


def cleanup_temporary_directory(directory: tempfile.TemporaryDirectory) -> None:
    """Thử lại WinError 145 do Windows giữ thư mục sau os.replace.

    Chỉ retry directory-not-empty; lỗi file log còn mở (32) vẫn phải lộ ra.
    """
    target = Path(directory.name).resolve()
    if target.parent != Path(tempfile.gettempdir()).resolve():
        raise ValueError("Chỉ dọn thư mục tạm trực tiếp do test tạo")
    for attempt in range(10):
        try:
            directory.cleanup()
            return
        except OSError as error:
            if getattr(error, "winerror", None) != 145 or attempt == 9:
                raise
            time.sleep(0.1)

PNG_HEADER = b"\x89PNG\r\n\x1a\n"
FAKE_CAPTCHA_BYTES = PNG_HEADER + b"0" * 600

LOGIN_HTML = '<html><head><meta name="csrf-token" content="csrf-login"></head></html>'
LANDING_HTML = '<html><body><input type="hidden" name="_csrf" value="csrf-landing"></body></html>'
DETAIL_HTML = '<html><body><input type="hidden" name="_csrf" value="csrf-detail"></body></html>'


def fixture(name: str) -> str:
    """Đọc một file HTML trong ``tests/fixtures``."""
    return (FIXTURES / name).read_text(encoding="utf-8")


def sample_zip(payload: bytes = b"<to-khai/>") -> bytes:
    """Tạo một ZIP hợp lệ trong bộ nhớ."""
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("to-khai.xml", payload)
    return buffer.getvalue()


def zip_payload(payload: bytes = b"<to-khai/>") -> str:
    """ZIP mã hoá Base64, đúng dạng cổng trả về trong JSON."""
    return base64.b64encode(sample_zip(payload)).decode("ascii")


class FakeResponse:
    """Phản hồi HTTP giả, đủ dùng cho code đang kiểm thử."""

    def __init__(
        self,
        text: str = "",
        *,
        status_code: int = 200,
        content: bytes | None = None,
        headers: dict | None = None,
        json_payload=None,
        url: str = "",
    ) -> None:
        self.status_code = status_code
        self._text = text
        self.content = content if content is not None else text.encode("utf-8")
        self.headers = headers or {}
        self._json = json_payload
        self.url = url

    @property
    def text(self) -> str:
        return self._text

    def json(self):
        if self._json is None:
            raise ValueError("Phản hồi không có JSON")
        return self._json


class FakeHttp:
    """Thay thế ``HttpClient``: định tuyến theo ``(method, đường dẫn)``."""

    def __init__(self, handler, base_url: str = "https://example.test/tthc") -> None:
        self.handler = handler
        self.base_url = base_url.rstrip("/")
        self.calls: list[Call] = []

    def url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self.base_url}{path}"

    def relative(self, path: str) -> str:
        """Bỏ tiền tố base URL để handler luôn nhận đường dẫn tương đối."""
        if path.startswith(self.base_url):
            return path[len(self.base_url):]
        if "://" in path:
            remainder = path.split("://", 1)[1]
            return "/" + remainder.split("/", 1)[1] if "/" in remainder else "/"
        return path

    def request(self, method: str, path: str, **kwargs) -> FakeResponse:
        relative = self.relative(path)
        call = Call(method, relative, kwargs)
        self.calls.append(call)
        response = self.handler(method, relative, kwargs)
        if response is None:
            raise AssertionError(f"Không có route cho {method} {relative}")
        return response

    def get(self, path: str, **kwargs) -> FakeResponse:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> FakeResponse:
        return self.request("POST", path, **kwargs)

    def close(self) -> None:  # tương thích HttpClient
        return None

    def paths(self, method: str | None = None) -> list[str]:
        return [c.path for c in self.calls if method is None or c.method == method]


class StubCaptcha(CaptchaSolver):
    """Solver giả: luôn trả về cùng một mã."""

    name = "stub"

    def __init__(self, code: str = "abcde") -> None:
        super().__init__()
        self.code = code
        self.images = 0

    def solve(self, image: bytes) -> str:
        self.images += 1
        return self.code


def route_of(path: str) -> str:
    """Bỏ query string để so khớp route."""
    return path.split("?", 1)[0]
