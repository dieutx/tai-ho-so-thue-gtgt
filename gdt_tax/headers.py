"""Bộ header cho từng loại request gửi lên cổng Dịch vụ công.

Mục tiêu: request gửi đi **không bị nhìn ra là công cụ Python**. Trước đây mỗi chỗ
 gọi mạng tự ghép ``{**DEFAULT_HEADERS, ...}`` nên cùng một thay đổi phải sửa ở tám
nơi; module này là chỗ duy nhất biết một request thuộc loại nào và loại đó cần
header gì.

Hai profile, chọn bằng ``GDT_HEADER_PROFILE``/``--header-profile``:

``browser`` (mặc định)
    Gửi đúng bộ header Chrome thật gửi, theo từng loại request: ``sec-ch-ua*``,
    ``Sec-Fetch-*``, ``Upgrade-Insecure-Requests``, ``Accept``, ``Accept-Encoding``
    và thứ tự header giống Chrome. Đây là chế độ giúp cổng/WAF không phân biệt được
    request của công cụ với request của người dùng đang đăng nhập bằng trình duyệt.

``minimal``
    Đúng bộ header tối thiểu đã chạy ổn định trên cổng từ trước: ``User-Agent``,
    ``Accept-Language`` và header riêng của từng endpoint, còn lại để ``requests``
    tự thêm. Dùng khi cần loại trừ khả năng chính header gây lỗi.

Ba loại request, khác nhau ở ``Sec-Fetch-Dest``:

* ``page``  — mở trang HTML (``document``/``navigate``): trang đăng nhập, ``/tchs``,
  trang chi tiết, form tải dự phòng.
* ``xhr``   — AJAX/HTMX (``empty``/``cors``): đăng nhập, tra cứu, kiểm tra và tải
  ZIP.
* ``image`` — ảnh CAPTCHA (``image``/``no-cors``).

Những thứ bám theo cấu hình từng máy chứ không phải hằng số dung lượng như
``sec-ch-ua*`` được tính từ ``User-Agent`` **thực sự gửi đi**; :func:`reconcile_client_hints`
đặt lại chúng trong ``HttpClient`` sau khi gộp header cấu hình — nhờ vậy
``--header "User-Agent=..."`` không thể tạo ra cặp giá trị mâu thuẫn.

**Giới hạn đã biết.** Header chỉ là lớp rẻ nhất. Hai thứ còn khác browser thật và
không sửa được bằng header: (1) ``requests``/``urllib3`` chỉ nói HTTP/1.1, browser
thật dùng HTTP/2 qua ALPN; (2) dấu vân tay TLS (JA3/JA4) của urllib3 khác Chrome.
Cổng thuế hiện chỉ giới hạn ở tầng ứng dụng (429) nên hai điểm này không thành vấn
đề; nếu sau này cổng dùng WAF kiểm TLS/HTTP2 thì phải đổi lớp vận chuyển
(``curl_cffi``/``httpx[http2]``) chứ thêm header không giải quyết được. Xem mục
*Không bị nhận diện là Python* trong README.
"""

from __future__ import annotations

import importlib.util
import re
from collections.abc import Mapping
from functools import lru_cache
from typing import Any

from .constants import DEFAULT_HEADERS

PROFILE_MINIMAL = "minimal"
PROFILE_BROWSER = "browser"
PROFILES = (PROFILE_MINIMAL, PROFILE_BROWSER)
#: Mặc định gửi như browser: mục tiêu của công cụ là không bị nhận ra là Python.
DEFAULT_PROFILE = PROFILE_BROWSER

KIND_PAGE = "page"
KIND_XHR = "xhr"
KIND_IMAGE = "image"
#: ``Sec-Fetch-Dest`` và ``Sec-Fetch-Mode`` mà Chrome dùng cho từng loại request.
SEC_FETCH_KINDS = {
    KIND_PAGE: ("document", "navigate"),
    KIND_XHR: ("empty", "cors"),
    KIND_IMAGE: ("image", "no-cors"),
}

#: ``Accept`` của Chrome khi mở một trang HTML.
PAGE_ACCEPT = (
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
)
#: ``Accept`` của Chrome khi tải ảnh (thẻ ``<img>``).
IMAGE_ACCEPT = "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
#: ``Accept`` mà công cụ dùng cho CAPTCHA ở profile ``minimal``.
MINIMAL_IMAGE_ACCEPT = "image/*"

#: Tên các client hint — dùng để nhận ra và đặt lại chúng.
CLIENT_HINT_NAMES = ("sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform")

#: Thứ tự header mà Chrome gửi, xấp xỉ. ``Host`` và ``Content-Length`` do urllib3
#: tự thêm (Host luôn đứng đầu, Content-Length chèn sau các header của ta) nên
#: không điều khiển được; mọi header còn lại đi theo thứ tự này.
BROWSER_ORDER = (
    "Connection",
    "sec-ch-ua",
    "sec-ch-ua-mobile",
    "sec-ch-ua-platform",
    "Upgrade-Insecure-Requests",
    "User-Agent",
    "Accept",
    "Sec-Fetch-Site",
    "Sec-Fetch-Mode",
    "Sec-Fetch-User",
    "Sec-Fetch-Dest",
    "Referer",
    "Accept-Encoding",
    "Accept-Language",
)
_CHROME_POSITION = {
    name.lower(): position for position, name in enumerate(BROWSER_ORDER)
}

_CHROME_VERSION = re.compile(r"Chrome/(\d+)")
#: Dấu hiệu trong ``User-Agent`` → giá trị ``sec-ch-ua-platform`` tương ứng.
_PLATFORMS = (
    ("Windows NT", "Windows"),
    ("Android", "Android"),
    ("iPhone", "iOS"),
    ("iPad", "iOS"),
    ("Macintosh", "macOS"),
    ("Mac OS X", "macOS"),
    ("CrOS", "Chrome OS"),
    ("X11", "Linux"),
    ("Linux", "Linux"),
)


def _has_module(name: str) -> bool:
    """Kiểm tra một thư viện giải nén có sẵn trong môi trường hay không."""
    return importlib.util.find_spec(name) is not None


@lru_cache(maxsize=1)
def accept_encoding() -> str:
    """``Accept-Encoding`` giống Chrome, nhưng chỉ gồm codec thực sự giải nén được.

    Chrome gửi ``gzip, deflate, br, zstd``. Ở đây ``br`` chỉ được thêm khi có
    ``brotli``/``brotlicffi``, còn ``zstd`` **không bao giờ** được thêm: urllib3
    (tới 2.8) chỉ giải mã ``gzip``, ``deflate``, ``br``, ``x-gzip`` — khai thêm
    ``zstd`` là nhận về byte nén và ZIP tải về sẽ hỏng.
    """
    codecs = ["gzip", "deflate"]
    if _has_module("brotli") or _has_module("brotlicffi"):
        codecs.append("br")
    return ", ".join(codecs)


def chrome_order(headers: Mapping[str, str]) -> dict[str, str]:
    """Sắp header theo thứ tự Chrome gửi; header lạ giữ nguyên thứ tự cũ.

    Phải áp dụng cho **bộ header cuối cùng** vì ``requests`` gộp header của
    ``Session`` vào trước header của từng request (và giữ nguyên vị trí của khoá đã
    có), nên tự sắp xếp trong từng builder là chưa đủ. ``HttpClient`` xoá header
    mặc định của session ở profile ``browser`` rồi sắp lại ở đây.

    So khớp tên header không phân biệt hoa thường để ``--header "user-agent=..."``
    vẫn rơi đúng chỗ; ``sorted`` ổn định nên header lạ giữ nguyên thứ tự truyền vào.
    """

    def position(name: str) -> int:
        return _CHROME_POSITION.get(name.lower(), len(BROWSER_ORDER))

    return {name: headers[name] for name in sorted(headers, key=position)}


def browser_base_headers() -> dict[str, str]:
    """Bộ header tối thiểu mà Chrome luôn gửi, đúng thứ tự Chrome dùng.

    ``HttpClient`` dùng bộ này để bù lại những header mà ``requests`` không còn tự
    thêm (vì header mặc định của session đã bị xoá ở profile ``browser``).
    """
    return chrome_order(
        {
            "Connection": "keep-alive",
            "User-Agent": DEFAULT_HEADERS["User-Agent"],
            "Accept": "*/*",
            "Accept-Encoding": accept_encoding(),
            "Accept-Language": DEFAULT_HEADERS["Accept-Language"],
        }
    )


def client_hints(user_agent: str) -> dict[str, str]:
    """Client hint ``sec-ch-ua*`` khớp với ``user_agent``.

    Trả về ``{}`` khi ``User-Agent`` không phải Chrome (ví dụ người dùng ghi đè
    bằng Firefox) hoặc không nhận ra hệ điều hành — gửi hint sai còn tệ hơn không
    gửi.
    """
    match = _CHROME_VERSION.search(user_agent)
    if not match:
        return {}
    platform = next((name for token, name in _PLATFORMS if token in user_agent), "")
    if not platform:
        return {}
    version = match.group(1)
    return {
        "sec-ch-ua": (
            f'"Google Chrome";v="{version}", "Chromium";v="{version}", "Not:A-Brand";v="24"'
        ),
        "sec-ch-ua-mobile": "?1" if "Mobile" in user_agent else "?0",
        "sec-ch-ua-platform": f'"{platform}"',
    }


def reconcile_client_hints(headers: Mapping[str, str]) -> dict[str, str]:
    """Đặt lại client hint theo ``User-Agent`` thực sự sẽ gửi, hoặc bỏ hẳn nếu lệch.

    ``HttpClient`` gọi hàm này sau khi gộp header cấu hình, nên ``--header`` ghi đè
    ``User-Agent`` vẫn cho ra bộ hint đúng theo ``User-Agent`` mới.
    """
    lowered = {str(name).lower() for name in headers}
    if not any(name in lowered for name in CLIENT_HINT_NAMES):
        return dict(headers)

    remaining = {name: value for name, value in headers.items() if name.lower() not in CLIENT_HINT_NAMES}
    user_agent = next(
        (value for name, value in headers.items() if name.lower() == "user-agent"), ""
    )
    remaining.update(client_hints(user_agent))
    return remaining


def _with_browser_headers(headers: dict[str, str], *, kind: str, site: str) -> dict[str, str]:
    """Thêm mọi dấu hiệu browser của Chrome cho một loại request."""
    dest, mode = SEC_FETCH_KINDS[kind]
    headers.update({"Sec-Fetch-Site": site, "Sec-Fetch-Mode": mode, "Sec-Fetch-Dest": dest})
    headers.setdefault("Accept-Encoding", accept_encoding())
    headers.update(client_hints(headers.get("User-Agent", "")))
    if site == "none":
        # Điều hướng đầu tiên trong phiên không có trang nguồn, nên browser không
        # gửi Referer. Gửi kèm sẽ tự mâu thuẫn với Sec-Fetch-Site: none.
        headers.pop("Referer", None)
    return chrome_order(headers)


def build_page_headers(
    *,
    profile: str = DEFAULT_PROFILE,
    site: str = "same-origin",
    headers: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Header cho một lần mở trang HTML (điều hướng), ví dụ ``GET /tthc/tchs``.

    ``site`` là ``Sec-Fetch-Site``: ``none`` cho lần điều hướng đầu tiên trong phiên,
    ``same-origin`` khi đã ở trong cổng (bấm link sang trang khác, gửi form).
    ``headers`` là header riêng của endpoint (``Referer``, ``Origin``...), ghi đè
    giá trị mặc định khi trùng tên.
    """
    result = {**DEFAULT_HEADERS, **(headers or {})}
    if profile != PROFILE_BROWSER:
        return result
    result.setdefault("Accept", PAGE_ACCEPT)
    # "?1" = điều hướng do người dùng phát động (bấm link, gửi form, gõ địa chỉ).
    result["Sec-Fetch-User"] = "?1"
    result["Upgrade-Insecure-Requests"] = "1"
    return _with_browser_headers(result, kind=KIND_PAGE, site=site)


def build_xhr_headers(
    *,
    profile: str = DEFAULT_PROFILE,
    accept: str = "*/*",
    site: str = "same-origin",
    headers: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Header cho request AJAX/HTMX (``fetch``/``XMLHttpRequest``).

    ``accept`` nên là ``*/*`` như ``fetch`` mặc định, hoặc giá trị riêng mà endpoint
    trông đợi (HTMX dùng ``text/html-partial``).
    """
    result = {**DEFAULT_HEADERS, "Accept": accept, **(headers or {})}
    if profile != PROFILE_BROWSER:
        return result
    return _with_browser_headers(result, kind=KIND_XHR, site=site)


def build_image_headers(
    *,
    profile: str = DEFAULT_PROFILE,
    site: str = "same-origin",
    headers: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Header cho ảnh CAPTCHA, tương đương một thẻ ``<img>``."""
    accept = IMAGE_ACCEPT if profile == PROFILE_BROWSER else MINIMAL_IMAGE_ACCEPT
    result = {**DEFAULT_HEADERS, "Accept": accept, **(headers or {})}
    if profile != PROFILE_BROWSER:
        return result
    return _with_browser_headers(result, kind=KIND_IMAGE, site=site)


def header_names(headers: Mapping[str, Any] | None) -> str:
    """Danh sách tên header, dùng cho log cấu hình (không in giá trị)."""
    return ", ".join(sorted(str(name) for name in (headers or {})))


__all__ = [
    "BROWSER_ORDER",
    "CLIENT_HINT_NAMES",
    "DEFAULT_PROFILE",
    "accept_encoding",
    "browser_base_headers",
    "chrome_order",
    "KIND_IMAGE",
    "KIND_PAGE",
    "KIND_XHR",
    "SEC_FETCH_KINDS",
    "IMAGE_ACCEPT",
    "MINIMAL_IMAGE_ACCEPT",
    "PAGE_ACCEPT",
    "PROFILES",
    "PROFILE_BROWSER",
    "PROFILE_MINIMAL",
    "build_image_headers",
    "build_page_headers",
    "build_xhr_headers",
    "client_hints",
    "header_names",
    "reconcile_client_hints",
]
