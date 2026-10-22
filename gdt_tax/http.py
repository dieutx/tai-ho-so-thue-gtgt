"""Lớp HTTP dùng chung: nối URL, timeout, thử lại và ghi lại từng request.

Mọi request đi qua :meth:`HttpClient.request` đều được log một dòng ở mức
``INFO`` (phương thức, đường dẫn, tham số, mã trạng thái, thời gian, dung lượng)
và metadata/header đã làm sạch cùng hash body ở mức ``DEBUG``. Chạy với ``-v`` hoặc
``--log-file`` là thấy đủ dữ liệu để sửa công cụ khi cổng Dịch vụ công đổi giao
diện; xem :mod:`gdt_tax.traffic` để biết cách che dữ liệu nhạy cảm và lưu file.
"""

from __future__ import annotations

import logging
import math
import tempfile
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import requests

from .auth_outcomes import raise_terminal
from .constants import BASE
from .errors import NetworkError
from .headers import (
    DEFAULT_PROFILE,
    PROFILE_BROWSER,
    browser_base_headers,
    chrome_order,
    reconcile_client_hints,
)
from .http_policy import (
    CAPTCHA_OPERATION,
    DOWNLOAD_OPERATION,
    PAGE_OPERATION,
    OperationPolicy,
    OriginPolicy,
)
from .proxy import Proxy
from .run_hooks import RunBudget, RunHooks
from .traffic import (
    BODY_LOG_LIMIT,
    TrafficDumper,
    body_fingerprint,
    describe_params,
    format_size,
    mask_headers,
    mask_secrets,
    safe_url,
)
from .verification import raise_for_portal_verification

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
    metadata (``--dump-http``); payload gốc cần bật private riêng. ``proxy`` đẩy request qua proxy
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
        hooks: RunHooks | None = None,
        origin_policy: OriginPolicy | None = None,
        max_backoff: float = 60.0,
        private_dump: bool = False,
    ) -> None:
        self.hooks = hooks or RunHooks()
        if self.hooks.budget is None:
            self.hooks.budget = RunBudget()
        self.origin_policy = origin_policy or OriginPolicy()
        if not all(math.isfinite(value) and value >= 0 for value in
                   (min_backoff, default_backoff, max_backoff)):
            raise ValueError("Backoff must be finite and nonnegative")
        self.max_backoff = max_backoff
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
        self.dumper = TrafficDumper(dump_dir, logger=self.logger, private=private_dump) if dump_dir else None
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
        if path.startswith("//") or "://" in path:
            return urljoin(self.base_url + "/", path)
        return urljoin(self.base_url + "/", path.lstrip("/"))

    def request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        if self.hooks.budget is None:
            self.hooks.budget = RunBudget()
        method = method.upper()
        operation = kwargs.pop("operation", None)
        if operation is None:
            endpoint = urlsplit(path).path.lower()
            template = (DOWNLOAD_OPERATION if "download" in endpoint else
                        CAPTCHA_OPERATION if "captcha" in endpoint or "imageservlet" in endpoint else
                        OperationPolicy() if endpoint.endswith("/request") else PAGE_OPERATION)
            operation = OperationPolicy(template.name, template.max_bytes,
                                        retry_safe=method in {"GET", "HEAD", "OPTIONS"}
                                        and not endpoint.endswith("/request"))
        if not isinstance(operation, OperationPolicy):
            raise ValueError("Invalid operation policy")
        kwargs.setdefault("timeout", self.timeout)
        follow_redirects = kwargs.pop("allow_redirects", True)
        kwargs["allow_redirects"] = False
        kwargs["stream"] = True
        headers = self._merge_headers(kwargs.get("headers"))
        if headers:
            kwargs["headers"] = headers
        url = self.url(path)
        self.origin_policy.validate(url)
        params = kwargs.get("params")
        payload = kwargs.get("data") if kwargs.get("data") is not None else kwargs.get("json")
        sent_headers = self._effective_headers(headers)
        if self.proxy is not None:
            kwargs.setdefault("proxies", self.proxy.proxies())

        response: requests.Response | None = None
        attempts = max(self.retries, operation.minimum_attempts) if operation.retry_safe else 1
        for attempt in range(1, attempts + 1):
            self.hooks.check()
            self._log_request(method, url, sent_headers, params, payload, attempt)
            started = time.monotonic()
            try:
                response = self._exchange(method, url, operation, follow_redirects, kwargs)
            except requests.exceptions.RequestException as error:
                raise self._network_error(method, url, error) from error
            elapsed = time.monotonic() - started
            body = getattr(response, "content", b"") or b""
            self.logger.info(
                "HTTP %s %s%s → %s (%.2fs, %s)",
                method,
                safe_url(url),
                self._describe_params(params),
                response.status_code,
                elapsed,
                format_size(len(body)),
            )
            raise_for_portal_verification(response)
            content_type = response.headers.get('content-type', '').lower()
            if (response.status_code in {502, 503, 504} or 'html' in content_type or 'json' in content_type
                    or body.lstrip()[:32].lower().startswith((b'<html', b'<!doctype html', b'{'))):
                adapter = 'ETAX_LEGACY' if urlsplit(url).hostname == 'thuedientu.gdt.gov.vn' else 'DVC'
                raise_terminal(response, adapter, phase='operation')
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
            if response.status_code != 429 or attempt == attempts:
                return response
            delay = self._retry_delay(response)
            self.logger.warning(
                "Máy chủ giới hạn tần suất (HTTP 429); chờ %s giây rồi thử lại (lần %s/%s)...",
                delay,
                attempt + 1,
                attempts,
            )
            self.hooks.pause(delay)
        assert response is not None  # vòng lặp luôn chạy ít nhất một lần
        return response

    def _exchange(self, method, url, operation, follow_redirects, kwargs):
        history = []
        options = dict(kwargs)
        for hop in range(6):
            self.hooks.check()
            budget = self.hooks.budget
            assert budget is not None
            budget.request()
            remaining = budget.remaining()
            configured = options.get("timeout", self.timeout)
            options["timeout"] = tuple(min(float(value), remaining) for value in configured) if isinstance(configured, tuple) else min(float(configured), remaining)
            response = self.session.request(method, url, **options)
            try:
                location = response.headers.get("Location") or response.headers.get("location")
                if follow_redirects and response.status_code in {301, 302, 303, 307, 308} and location:
                    if hop == 5:
                        raise NetworkError("HTTP_REDIRECT_LIMIT")
                    target = urljoin(url, location)
                    self.origin_policy.validate(target, previous=url)
                    history.append(response)
                    if response.status_code == 303 and method != "HEAD" or response.status_code in {301, 302} and method == "POST":
                        method = "GET"
                        for key in ("data", "json", "files"):
                            options.pop(key, None)
                        options["headers"] = {key: value for key, value in options.get("headers", {}).items()
                                              if key.casefold() not in {"content-type", "content-length", "transfer-encoding"}}
                    # Query params belong to the first request, not the redirect target.
                    options.pop("params", None)
                    url = target
                    continue
                self._buffer_response(response, operation.max_bytes)
                response.history = history
                return response
            finally:
                close = getattr(response, "close", None)
                if callable(close):
                    close()
        raise NetworkError("HTTP_REDIRECT_LIMIT")

    def _buffer_response(self, response, limit):
        length = response.headers.get("Content-Length") or response.headers.get("content-length")
        if length and str(length).isdigit() and int(length) > limit:
            raise NetworkError("HTTP_RESPONSE_TOO_LARGE")
        iterator = getattr(response, "iter_content", None)
        # Fakes without streaming support remain usable by embedded consumers.
        chunks = iterator(chunk_size=64 * 1024) if callable(iterator) else [response.content]
        total = 0
        with tempfile.SpooledTemporaryFile(max_size=1024 * 1024) as spool:
            for chunk in chunks:
                self.hooks.check()
                if not chunk:
                    continue
                assert self.hooks.budget is not None
                self.hooks.budget.consume(len(chunk))
                total += len(chunk)
                if total > limit:
                    raise NetworkError("HTTP_RESPONSE_TOO_LARGE")
                spool.write(chunk)
            spool.seek(0)
            response._content = spool.read()
        response._content_consumed = True

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
        self.logger.debug("GỬI %s %s (lần %s/%s)", method, safe_url(url), attempt, self.retries)
        if params:
            self.logger.debug("  tham số: %s", describe_params(params, limit=BODY_LOG_LIMIT))
        if headers:
            self.logger.debug("  header: %s", mask_headers(headers))
        body = body_fingerprint(payload)
        if body:
            self.logger.debug("  body: %s", body)

    def _network_error(
        self, method: str, url: str, error: requests.exceptions.RequestException
    ) -> NetworkError:
        """Đổi lỗi của ``requests`` thành lỗi gọn, đã che mật khẩu proxy.

        Thông báo của ``requests`` thường chứa cả URL proxy kèm tài khoản, nên phải
        che trước khi đưa vào log.
        """
        detail = mask_secrets(type(error).__name__, self.secrets)
        message = f"Không gửi được {method} {safe_url(url)}: {detail}"
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
        text = body_fingerprint(getattr(response, "content", b""))
        if text:
            self.logger.debug("  ← body: %s", text)

    def _describe_params(self, params: Any) -> str:
        if not params:
            return ""
        return f"?{describe_params(params, limit=PARAMS_LOG_LIMIT)}"

    def _retry_delay(self, response: requests.Response) -> float:
        raw = response.headers.get("Retry-After", "")
        try:
            delay = float(raw)
        except (TypeError, ValueError):
            try:
                when = parsedate_to_datetime(raw)
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
                delay = (when - datetime.now(timezone.utc)).total_seconds()
            except (TypeError, ValueError, OverflowError):
                delay = self.default_backoff
        if not math.isfinite(delay) or delay < 0:
            delay = self.default_backoff
        return min(self.max_backoff, max(self.min_backoff, delay))


__all__ = ["HttpClient", "PARAMS_LOG_LIMIT"]
