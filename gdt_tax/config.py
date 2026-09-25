"""Cấu hình chạy: đọc từ file ``.env`` rồi tới biến môi trường.

Thứ tự ưu tiên (cao nhất trước):

1. Tham số dòng lệnh (truyền vào ``Settings.from_env(..., **overrides)``)
2. Biến môi trường đang có trong tiến trình
3. File ``.env`` (dùng khi phát triển ở máy cá nhân)

Mọi biến đều có tiền tố ``GDT_`` để không lẫn với biến khác.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import Any

from .constants import SOURCE_DVC, SOURCE_ETAX
from .dates import (
    ETAX_CUTOFF_DEFAULT,
    MAX_DAYS_PER_SEARCH_DEFAULT,
    parse_date,
    split_periods,
)
from .errors import ConfigError
from .headers import DEFAULT_PROFILE, PROFILES
from .models import SearchPeriod

ENV_PREFIX = "GDT_"
DEFAULT_ENV_FILE = ".env"
#: ddddocr được chọn mặc định: đọc đúng 6/6 mẫu CAPTCHA thật của cổng, nhanh hơn
#: easyocr khoảng 50 lần và không cần torch. Xem bảng so sánh trong README.
DEFAULT_CAPTCHA_SOLVER = "ddddocr"


def load_env_file(path: str | Path = DEFAULT_ENV_FILE) -> dict[str, str]:
    """Đọc file ``.env`` dạng ``KEY=VALUE``; bỏ qua dòng trống và dòng chú thích."""
    values: dict[str, str] = {}
    path = Path(path)
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        values[key] = value.strip().strip('"').strip("'")
    return values


class _Env:
    """Đọc và kiểm tra kiểu dữ liệu cho một tập biến môi trường."""

    def __init__(self, values: Mapping[str, str]) -> None:
        self.values = values

    def _raw(self, name: str, default: str) -> str:
        return self.values.get(f"{ENV_PREFIX}{name}", default)

    def text(self, name: str, default: str = "") -> str:
        return self._raw(name, default).strip()

    def integer(self, name: str, default: int) -> int:
        raw = self._raw(name, str(default)).strip()
        try:
            return int(raw)
        except ValueError as error:
            raise ConfigError(f"{ENV_PREFIX}{name} phải là số nguyên, nhận được {raw!r}") from error

    def number(self, name: str, default: float) -> float:
        raw = self._raw(name, str(default)).strip()
        try:
            return float(raw)
        except ValueError as error:
            raise ConfigError(f"{ENV_PREFIX}{name} phải là số, nhận được {raw!r}") from error

    def boolean(self, name: str, default: bool = False) -> bool:
        raw = self._raw(name, str(default)).strip().lower()
        if raw in {"1", "true", "yes", "y", "co", "có"}:
            return True
        if raw in {"0", "false", "no", "n", "khong", "không", ""}:
            return False
        raise ConfigError(f"{ENV_PREFIX}{name} phải là true/false, nhận được {raw!r}")

    def text_map(self, name: str) -> dict[str, str]:
        """Đọc một đối tượng JSON phẳng và đổi mọi giá trị thành chuỗi."""
        return {str(key): str(value) for key, value in self.json(name).items()}

    def json(self, name: str, default: dict[str, Any] | None = None) -> dict[str, Any]:
        raw = self._raw(name, "").strip()
        if not raw:
            return dict(default or {})
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ConfigError(f"{ENV_PREFIX}{name} phải là JSON hợp lệ: {error}") from error
        if not isinstance(parsed, dict):
            raise ConfigError(f"{ENV_PREFIX}{name} phải là một đối tượng JSON")
        return parsed


@dataclass(frozen=True)
class Settings:
    """Toàn bộ tham số của một lần chạy."""

    username: str
    password: str
    from_date: date
    to_date: date
    download_dir: Path
    case_id: str = ""
    captcha_solver: str = DEFAULT_CAPTCHA_SOLVER
    captcha_options: Mapping[str, Any] = field(default_factory=dict)
    captcha_plugins: str = ""
    etax_cutoff: date = ETAX_CUTOFF_DEFAULT
    max_days_per_search: int = MAX_DAYS_PER_SEARCH_DEFAULT
    page_size: int = 10
    login_attempts: int = 10
    search_attempts: int = 6
    request_timeout: int = 30
    http_retries: int = 3
    pause_between_records: float = 1.0
    pause_between_pages: float = 3.0
    #: Tỉ lệ ngẫu nhiên (0–1) cộng thêm vào mỗi lần nghỉ để nhịp không đều như máy.
    pause_jitter: float = 0.3
    dry_run: bool = False
    #: Header thêm hoặc ghi đè cho mọi request, để xử lý nhanh khi cổng đổi yêu cầu
    #: mà chưa cần sửa mã nguồn (``--header``/``GDT_EXTRA_HEADERS``).
    extra_headers: Mapping[str, str] = field(default_factory=dict)
    #: File ghi thêm toàn bộ log ở mức DEBUG (``--log-file``/``GDT_LOG_FILE``).
    log_file: str = ""
    #: Thư mục lưu nguyên request/response để dựng fixture (``--dump-http``).
    http_dump_dir: str = ""
    #: Bộ header gửi đi: ``minimal`` (mặc định) hoặc ``browser``. Xem gdt_tax.headers.
    header_profile: str = DEFAULT_PROFILE

    # --- Dẫn xuất ---
    def periods(self) -> list[SearchPeriod]:
        """Danh sách đoạn tra cứu cần chạy, theo thứ tự thời gian."""
        return list(
            split_periods(
                self.from_date,
                self.to_date,
                cutoff=self.etax_cutoff,
                max_days=self.max_days_per_search,
            )
        )

    def validate(self) -> None:
        if not self.username:
            raise ConfigError(
                "Thiếu GDT_USERNAME. Hãy đặt biến môi trường hoặc ghi vào file .env."
            )
        if not self.password:
            raise ConfigError(
                "Thiếu GDT_PASSWORD. Hãy đặt biến môi trường hoặc ghi vào file .env."
            )
        if self.from_date > self.to_date:
            raise ConfigError("GDT_FROM_DATE phải nhỏ hơn hoặc bằng GDT_TO_DATE")
        if self.max_days_per_search < 1:
            raise ConfigError("GDT_MAX_DAYS_PER_SEARCH phải lớn hơn 0")
        if self.page_size < 1:
            raise ConfigError("GDT_PAGE_SIZE phải lớn hơn 0")
        if self.pause_jitter < 0:
            raise ConfigError("GDT_PAUSE_JITTER không được là số âm")
        if not all(isinstance(name, str) and name for name in self.extra_headers):
            raise ConfigError("GDT_EXTRA_HEADERS phải là đối tượng JSON với khoá là tên header")
        if self.header_profile not in PROFILES:
            raise ConfigError(
                f"GDT_HEADER_PROFILE phải là {' hoặc '.join(PROFILES)}, nhận được "
                f"{self.header_profile!r}"
            )

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        env_file: str | Path | None = DEFAULT_ENV_FILE,
        **overrides: Any,
    ) -> Settings:
        """Tạo cấu hình từ môi trường; ``overrides`` là các giá trị từ dòng lệnh."""
        values: dict[str, str] = {}
        if env_file:
            values.update(load_env_file(env_file))
        values.update(dict(os.environ if environ is None else environ))
        env = _Env(values)

        def pick(key: str, fallback: Any) -> Any:
            value = overrides.get(key)
            return fallback if value is None else value

        try:
            from_raw = pick("from_date", env.text("FROM_DATE", "01/09/2026"))
            to_raw = pick("to_date", env.text("TO_DATE", "25/09/2026"))
            cutoff_raw = pick("etax_cutoff", env.text("ETAX_CUTOFF", ""))
            settings = cls(
                username=pick("username", env.text("USERNAME")),
                password=pick("password", env.text("PASSWORD")),
                from_date=parse_date(from_raw),
                to_date=parse_date(to_raw),
                download_dir=Path(pick("download_dir", env.text("DOWNLOAD_DIR", "download"))),
                case_id=pick("case_id", env.text("CASE_ID")),
                captcha_solver=pick("captcha_solver", env.text("CAPTCHA_SOLVER", DEFAULT_CAPTCHA_SOLVER)),
                captcha_options=pick("captcha_options", env.json("CAPTCHA_OPTIONS")) or {},
                captcha_plugins=env.text("CAPTCHA_PLUGINS"),
                etax_cutoff=parse_date(cutoff_raw) if cutoff_raw else ETAX_CUTOFF_DEFAULT,
                max_days_per_search=env.integer("MAX_DAYS_PER_SEARCH", MAX_DAYS_PER_SEARCH_DEFAULT),
                page_size=env.integer("PAGE_SIZE", 10),
                login_attempts=env.integer("LOGIN_ATTEMPTS", 10),
                search_attempts=env.integer("SEARCH_ATTEMPTS", 6),
                request_timeout=env.integer("REQUEST_TIMEOUT", 30),
                http_retries=env.integer("HTTP_RETRIES", 3),
                pause_between_records=env.number("PAUSE_BETWEEN_RECORDS", 1.0),
                pause_between_pages=env.number("PAUSE_BETWEEN_PAGES", 3.0),
                pause_jitter=env.number("PAUSE_JITTER", 0.3),
                dry_run=bool(pick("dry_run", env.boolean("DRY_RUN", False))),
                extra_headers=pick("extra_headers", env.text_map("EXTRA_HEADERS")) or {},
                log_file=pick("log_file", env.text("LOG_FILE")),
                http_dump_dir=pick("http_dump_dir", env.text("HTTP_DUMP_DIR")),
                header_profile=pick("header_profile", env.text("HEADER_PROFILE", DEFAULT_PROFILE)),
            )
        except ValueError as error:  # parse_date
            raise ConfigError(str(error)) from error

        settings.validate()
        return settings

    def with_download_dir(self, directory: str | Path) -> Settings:
        return replace(self, download_dir=Path(directory))


__all__ = [
    "DEFAULT_CAPTCHA_SOLVER",
    "DEFAULT_ENV_FILE",
    "ENV_PREFIX",
    "Settings",
    "SOURCE_DVC",
    "SOURCE_ETAX",
    "load_env_file",
]
