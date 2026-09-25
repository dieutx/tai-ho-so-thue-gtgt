"""Lớp HTTP dùng chung: nối URL, timeout, thử lại và ghi lại từng request.

Mọi request đi qua :meth:`HttpClient.request` đều được log một dòng ở mức
``INFO`` (phương thức, đường dẫn, tham số, mã trạng thái, thời gian, dung lượng)
và chi tiết header/body ở mức ``DEBUG``. Nhờ vậy chỉ cần chạy với ``-v`` hoặc
``--log-file`` là thấy đủ dữ liệu để sửa công cụ khi cổng Dịch vụ công đổi giao
diện; xem :mod:`gdt_tax.traffic` để biết cách che dữ liệu nhạy cảm và lưu file.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import requests

from .constants import BASE
from .errors import NetworkError
from .headers import (
    DEFAULT_PROFILE,
    PROFILE_BROWSER,
    browser_base_headers,
    chrome_order,
    reconcile_client_hints,
)
from .proxy import Proxy
from .traffic import (
    BODY_LOG_LIMIT,
    TrafficDumper,
    describe_body,
    describe_params,
    format_size,
    mask_headers,
    mask_secrets,
)

LOGGER_NAME = "gdt_tax.http"
#: Độ dài tối đa của phần tham số in ra dòng log ``INFO``.
PARAMS_LOG_LIMIT = 160
#: Header mặc định của ``requests.Session`` — ở profile ``browser`` chúng bị xoá vì
#: vừa tố cáo công cụ là Python vừa chen lên trước làm lệch thứ tự header.
REQUESTS_DEFAULT_HEADERS = ("User-Agent", "Accept-Encoding", "Accept", "Connection")


class HttpClient:
    """Bọc :class:`requests.Session` với vài hành vi dùng chung của cổng thuế.

    Cổng Dịch vụ công trả ``429 Too Many Requests`` khi tra cứu quá nhanh, nên
    lớp này tự nghỉ theo header ``Retry-After`` trước khi thử lại.

    ``extra_headers`` cho phép thêm hoặc ghi đè header cho **mọi** request ngay
    lúc chạy (``--header``/``GDT_EXTRA_HEADERS``), nên khi cổng yêu cầu thêm một
    header mới thì không phải chờ sửa mã nguồn. ``dump_dir`` bật ghi lại traffic
    thật để dựng fixture (``--dump-http``). ``proxy`` đẩy toàn bộ request qua proxy
    Việt Nam khi chạy trên máy ở nước ngoài (``--proxy``/``GDT_PROXY_URL``).
    """

    def __init__(
        self,
        *,
        base_url: str = BASE,
        timeout: int = 30,
        retries: int = 3,
        min_backoff: float = 5.0,
        default_backoff: float = 15.0,
        session: requests.Session | None = None,
        logger: logging.Logger | None = None,
        extra_headers: Mapping[str, str] | None = None,
        dump_dir: str | Path | None = None,
        header_profile: str = DEFAULT_PROFILE,
        proxy: Proxy | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = max(1, retries)
        self.min_backoff = min_backoff
        self.default_backoff = default_backoff
        self.session = session or requests.Session()
        self.logger = logger or logging.getLogger(LOGGER_NAME)
        self.extra_headers = dict(extra_headers or {})
        self.header_profile = header_profile
        self.proxy = proxy
        self.secrets = proxy.secrets() if proxy else ()
        #: Ghi lại request/response khi ``--dump-http`` được bật, ngược lại là ``None``.
        self.dumper = TrafficDumper(dump_dir, logger=self.logger) if dump_dir else None
        self._prepare_session()

    def _prepare_session(self) -> None:
        """Chuẩn bị session theo profile header.

        Ở profile ``browser``, header mặc định của ``requests`` (``User-Agent:
        python-requests/x.y``, ``Accept-Encoding: gzip, deflate``) bị xoá: chúng vừa
        tố cáo công cụ là Python, vừa chèn lên trước khiến thứ tự header không giống
        Chrome. :meth:`_merge_headers` bù lại bộ tối thiểu và sắp đúng thứ tự.
        """
        if self.header_profile != PROFILE_BROWSER:
            return
        pop = getattr(getattr(self.session, "headers", None), "pop", None)
        if not callable(pop):
            return
        for name in REQUESTS_DEFAULT_HEADERS:
            pop(name, None)

    def url(self, path: str) -> str:
        """Ghép đường dẫn tương đối thành URL đầy đủ."""
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self.base_url}{path}"

    def request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", self.timeout)
        headers = self._merge_headers(kwargs.get("headers"))
        if headers:
            kwargs["headers"] = headers
        url = self.url(path)
        params = kwargs.get("params")
        payload = kwargs.get("data") if kwargs.get("data") is not None else kwargs.get("json")
        sent_headers = self._effective_headers(headers)
        if self.proxy is not None:
            kwargs.setdefault("proxies", self.proxy.proxies())

        response: requests.Response | None = None
        for attempt in range(1, self.retries + 1):
            self._log_request(method, url, sent_headers, params, payload, attempt)
            started = time.monotonic()
            try:
                response = self.session.request(method, url, **kwargs)
            except requests.exceptions.RequestException as error:
                raise self._network_error(method, url, error) from error
            elapsed = time.monotonic() - started
            body = getattr(response, "content", b"") or b""
            self.logger.info(
                "HTTP %s %s%s → %s (%.2fs, %s)",
                method,
                url,
                self._describe_params(params),
                response.status_code,
                elapsed,
                format_size(len(body)),
            )
            self._log_response(response)
            if self.dumper is not None:
                self.dumper.record(
                    method=method,
                    url=url,
                    params=params,
                    headers=sent_headers,
                    body=payload,
                    response=response,
                    elapsed=elapsed,
                )
            if response.status_code != 429 or attempt == self.retries:
                return response
            delay = self._retry_delay(response)
            self.logger.warning(
                "Máy chủ giới hạn tần suất (HTTP 429); chờ %s giây rồi thử lại (lần %s/%s)...",
                delay,
                attempt + 1,
                self.retries,
            )
            time.sleep(delay)
        assert response is not None  # vòng lặp luôn chạy ít nhất một lần
        return response

    def get(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("POST", path, **kwargs)

    def close(self) -> None:
        self.session.close()

    def _merge_headers(self, headers: Mapping[str, str] | None) -> dict[str, str]:
        """Gộp header của request với header cấu hình lúc chạy.

        Header cấu hình (``--header``/``GDT_EXTRA_HEADERS``) thắng, để còn kịp
        ghi đè ``User-Agent`` hay ``Referer`` khi cổng đổi yêu cầu. Client hint
        ``sec-ch-ua*`` (chỉ có khi dùng ``--header-profile browser``) được tính lại
        theo ``User-Agent`` sau cùng để không gửi cặp giá trị mâu thuẫn.
        """
        merged = {str(name): str(value) for name, value in (headers or {}).items()}
        merged.update(self.extra_headers)
        merged = reconcile_client_hints(merged)
        if self.header_profile == PROFILE_BROWSER:
            # Session đã mất header mặc định, nên bù bộ tối thiểu của Chrome cho cả
            # những chỗ gọi thẳng ``http.get(...)`` không truyền header nào.
            for name, value in browser_base_headers().items():
                merged.setdefault(name, value)
            return chrome_order(merged)
        return merged

    def _effective_headers(self, headers: Mapping[str, str]) -> dict[str, str]:
        """Header thực sự được gửi: mặc định của session rồi tới header của request.

        Log và file dump dùng bản này để nhìn thấy đúng ``User-Agent``,
        ``Accept-Encoding``... mà cổng nhận được, thay vì chỉ header do portal đặt.
        """
        session_headers = getattr(self.session, "headers", None) or {}
        merged = {str(name): str(value) for name, value in session_headers.items()}
        merged.update(headers)
        return merged

    def _log_request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        params: Any,
        payload: Any,
        attempt: int,
    ) -> None:
        """Ghi lại request sắp gửi; chỉ tốn công khi log đang ở mức ``DEBUG``."""
        if not self.logger.isEnabledFor(logging.DEBUG):
            return
        self.logger.debug("GỬI %s %s (lần %s/%s)", method, url, attempt, self.retries)
        if params:
            self.logger.debug("  tham số: %s", describe_params(params, limit=BODY_LOG_LIMIT))
        if headers:
            self.logger.debug("  header: %s", mask_headers(headers))
        body = describe_body(payload, limit=BODY_LOG_LIMIT)
        if body:
            self.logger.debug("  body: %s", body)

    def _network_error(
        self, method: str, url: str, error: requests.exceptions.RequestException
    ) -> NetworkError:
        """Đổi lỗi của ``requests`` thành lỗi gọn, đã che mật khẩu proxy.

        Thông báo của ``requests`` thường chứa cả URL proxy kèm tài khoản, nên phải
        che trước khi đưa vào log.
        """
        detail = mask_secrets(str(error), self.secrets)
        message = f"Không gửi được {method} {url}: {detail}"
        if self.proxy is not None:
            message += (
                f" (qua proxy {self.proxy.label} — kiểm tra proxy còn sống và "
                "tài khoản còn hạn, hoặc bỏ GDT_PROXY_URL để đi trực tiếp)"
            )
        return NetworkError(message)

    def _log_response(self, response: requests.Response) -> None:
        """Ghi lại phản hồi vừa nhận, kèm body đã che và cắt bớt."""
        if not self.logger.isEnabledFor(logging.DEBUG):
            return
        self.logger.debug("  ← header: %s", mask_headers(getattr(response, "headers", {})))
        text = getattr(response, "text", "")
        if text:
            self.logger.debug("  ← body: %s", describe_body(text, limit=BODY_LOG_LIMIT))

    def _describe_params(self, params: Any) -> str:
        if not params:
            return ""
        return f"?{describe_params(params, limit=PARAMS_LOG_LIMIT)}"

    def _retry_delay(self, response: requests.Response) -> float:
        raw = response.headers.get("Retry-After", "")
        try:
            return max(self.min_backoff, float(raw))
        except (TypeError, ValueError):
            return self.default_backoff


__all__ = ["HttpClient", "PARAMS_LOG_LIMIT"]
