"""Lớp HTTP dùng chung: nối URL, timeout và tự thử lại khi bị giới hạn tần suất."""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from .constants import BASE

LOGGER_NAME = "gdt_tax.http"


class HttpClient:
    """Bọc :class:`requests.Session` với vài hành vi dùng chung của cổng thuế.

    Cổng Dịch vụ công trả ``429 Too Many Requests`` khi tra cứu quá nhanh, nên
    lớp này tự nghỉ theo header ``Retry-After`` trước khi thử lại.
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
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = max(1, retries)
        self.min_backoff = min_backoff
        self.default_backoff = default_backoff
        self.session = session or requests.Session()
        self.logger = logger or logging.getLogger(LOGGER_NAME)

    def url(self, path: str) -> str:
        """Ghép đường dẫn tương đối thành URL đầy đủ."""
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self.base_url}{path}"

    def request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", self.timeout)
        response: requests.Response | None = None
        for attempt in range(self.retries):
            response = self.session.request(method, self.url(path), **kwargs)
            if response.status_code != 429 or attempt == self.retries - 1:
                return response
            delay = self._retry_delay(response)
            self.logger.warning(
                "Máy chủ giới hạn tần suất (HTTP 429); chờ %s giây rồi thử lại...", delay
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

    def _retry_delay(self, response: requests.Response) -> float:
        raw = response.headers.get("Retry-After", "")
        try:
            return max(self.min_backoff, float(raw))
        except (TypeError, ValueError):
            return self.default_backoff


__all__ = ["HttpClient"]
