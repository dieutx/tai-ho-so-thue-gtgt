"""Chuẩn hoá cấu hình proxy cho mọi request ra cổng Dịch vụ công.

Cổng Dịch vụ công chặn IP nước ngoài, nên khi chạy trên VPS/máy chủ ngoài Việt Nam
thì mọi request phải đi qua một proxy Việt Nam. Module này nhận nhiều dạng chuỗi
cấu hình (mỗi nhà cung cấp proxy ghi một kiểu) và đổi về một dạng duy nhất:

    ``http://tài-khoản:mật-khẩu@host:port``      đầy đủ, có scheme
    ``host:port:tài-khoản:mật-khẩu``             dạng nhiều nhà cung cấp VN hay đưa
    ``tài-khoản:mật-khẩu@host:port``             thiếu scheme, mặc định ``http``
    ``socks5://tài-khoản:mật-khẩu@host:port``    proxy SOCKS (cần ``PySocks``)
    ``host:port``                                proxy không cần tài khoản

Hai điểm quan trọng:

* **Mật khẩu không bao giờ bị ghi ra log.** :meth:`Proxy.label` chỉ trả ``host:port``
  để in ra, còn :meth:`Proxy.secrets` cấp danh sách chuỗi cần che cho
  :class:`gdt_tax.logging_setup.SecretsFilter`.
* **Tài khoản có ký tự đặc biệt vẫn dùng được**: khi dựng lại URL, tài khoản và mật
  khẩu được percent-encode, nên mật khẩu chứa ``@``, ``:`` hay ``/`` không làm hỏng
  cấu hình.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from urllib.parse import quote, unquote, urlsplit

from .errors import ConfigError

DEFAULT_SCHEME = "http"
#: Scheme ``requests`` hỗ trợ (SOCKS cần thêm ``PySocks``).
SCHEMES = ("http", "https", "socks4", "socks4a", "socks5", "socks5h")
SOCKS_SCHEMES = ("socks4", "socks4a", "socks5", "socks5h")
DEFAULT_PORTS = {
    "http": 8080,
    "https": 8080,
    "socks4": 1080,
    "socks4a": 1080,
    "socks5": 1080,
    "socks5h": 1080,
}
SOCKS_HINT = 'Cài PySocks để dùng proxy SOCKS: pip install "requests[socks]"'


@dataclass(frozen=True)
class Proxy:
    """Một proxy đã chuẩn hoá, dùng được cho cả ``http`` và ``https``."""

    host: str
    port: int
    scheme: str = DEFAULT_SCHEME
    username: str = ""
    password: str = ""

    @property
    def url(self) -> str:
        """URL đầy đủ để ``requests`` dùng, đã percent-encode tài khoản."""
        auth = ""
        if self.username:
            auth = quote(self.username, safe="")
            if self.password:
                auth += f":{quote(self.password, safe='')}"
            auth += "@"
        return f"{self.scheme}://{auth}{self.host}:{self.port}"

    @property
    def label(self) -> str:
        """Định danh proxy để ghi log — không bao giờ chứa tài khoản/mật khẩu."""
        return f"{self.host}:{self.port} ({self.scheme})"

    def secrets(self) -> tuple[str, ...]:
        """Các chuỗi phải che khi ghi log hoặc khi tạo thông báo lỗi.

        Proxy không có tài khoản thì không có gì phải che. Chuỗi dài được trả
        trước để ``******`` thay trúng cả ``tài-khoản:mật-khẩu`` và URL đầy đủ,
        không chỉ mỗi mật khẩu — nhờ vậy tên tài khoản proxy cũng không lộ.
        """
        if not self.username:
            return ()
        values = [self.url]
        if self.password:
            values += [f"{self.username}:{self.password}", self.password]
        return tuple(sorted({value for value in values if value}, key=len, reverse=True))

    def proxies(self) -> dict[str, str]:
        """Tham số ``proxies`` của ``requests``: cùng proxy cho http và https."""
        return {"http": self.url, "https": self.url}


def _has_pysocks() -> bool:
    return importlib.util.find_spec("socks") is not None


def _port(value: str) -> int:
    text = (value or "").strip()
    if not text.isdigit():
        raise ConfigError(f"Proxy có port không hợp lệ: {value!r}")
    port = int(text)
    if not 1 <= port <= 65535:
        raise ConfigError(f"Proxy có port ngoài khoảng 1–65535: {port}")
    return port


def _validate(proxy: Proxy) -> Proxy:
    """Kiểm tra một proxy đã tách xong trường."""
    if not proxy.host:
        raise ConfigError("Proxy thiếu host. Ví dụ: GDT_PROXY_URL=1.2.3.4:8080:tai-khoan:mat-khau")
    if proxy.scheme not in SCHEMES:
        raise ConfigError(
            f"Proxy dùng scheme không hỗ trợ: {proxy.scheme!r}. Hợp lệ: {', '.join(SCHEMES)}"
        )
    if proxy.scheme in SOCKS_SCHEMES and not _has_pysocks():
        raise ConfigError(SOCKS_HINT)
    return proxy


def _from_url(text: str) -> Proxy:
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError as error:
        raise ConfigError(f"Proxy không hợp lệ: {text!r} ({error})") from error

    scheme = (parts.scheme or DEFAULT_SCHEME).lower()
    return _validate(
        Proxy(
            host=parts.hostname or "",
            port=port if port is not None else DEFAULT_PORTS.get(scheme, 0),
            scheme=scheme,
            username=unquote(parts.username or ""),
            password=unquote(parts.password or ""),
        )
    )


def _from_fields(text: str) -> Proxy:
    """Đọc dạng ``host:port`` hoặc ``host:port:tài-khoản:mật-khẩu``."""
    fields = text.split(":")
    if len(fields) == 2:
        host, port, username, password = fields[0], fields[1], "", ""
    elif len(fields) >= 4:
        # Mật khẩu có thể chứa ``:`` nên phần còn lại ghép lại.
        host, port, username = fields[0], fields[1], fields[2]
        password = ":".join(fields[3:])
    else:
        raise ConfigError(
            f"Proxy không hợp lệ: {text!r}. Cần 'host:port' hoặc 'host:port:tài-khoản:mật-khẩu'."
        )
    return _validate(
        Proxy(
            host=host.strip(),
            port=_port(port),
            username=username.strip(),
            password=password,
        )
    )


def parse_proxy(value: str) -> Proxy | None:
    """Đọc chuỗi cấu hình proxy; trả ``None`` khi để trống.

    Ném :class:`~gdt_tax.errors.ConfigError` khi chuỗi không đọc được, để lỗi hiện
    ra ngay lúc khởi động thay vì giữa lúc chạy.
    """
    text = (value or "").strip()
    if not text:
        return None
    if "://" in text:
        return _from_url(text)

    fields = text.split(":")
    # "host:port:tài-khoản:mật-khẩu" được ưu tiên khi trường thứ hai là port hợp lệ,
    # vì mật khẩu của dạng này có thể chứa "@" hoặc "/" (đủ để phá cách đọc như URL).
    if len(fields) >= 4 and fields[1].strip().isdigit():
        return _from_fields(text)
    if "@" in text:
        # Dạng thiếu scheme, ví dụ "tai-khoan:mat-khau@host:port".
        return _from_url(f"{DEFAULT_SCHEME}://{text}")
    return _from_fields(text)


__all__ = [
    "DEFAULT_PORTS",
    "DEFAULT_SCHEME",
    "SCHEMES",
    "SOCKS_HINT",
    "SOCKS_SCHEMES",
    "Proxy",
    "parse_proxy",
]
