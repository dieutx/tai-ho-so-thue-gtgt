"""Giao diện dòng lệnh.

Chạy được trên cả Windows và Linux::

    python -m gdt_tax --from-date 01/01/2025 --to-date 31/01/2025 --output-dir download/2025-01

Mã thoát: ``0`` thành công, ``1`` chạy xong nhưng thiếu hồ sơ, ``2`` lỗi cấu hình.
"""

from __future__ import annotations

import argparse
import json
import logging
import platform
import sys

from . import __version__
from .captcha import available_solvers, create_solver, register_plugins
from .config import DEFAULT_ENV_FILE, Settings
from .errors import CaptchaError, ConfigError, GdtError
from .headers import PROFILE_BROWSER, PROFILE_MINIMAL, PROFILES, header_names
from .http import HttpClient
from .logging_setup import close_logging, configure_logging
from .pipeline import Pipeline
from .proxy import Proxy, parse_proxy

LOGGER_NAME = "gdt_tax"

EXIT_OK = 0
EXIT_INCOMPLETE = 1
EXIT_CONFIG_ERROR = 2

EXAMPLES = """\
Ví dụ:
  python -m gdt_tax --from-date 01/01/2025 --to-date 31/01/2025
  python -m gdt_tax --from-date 01/01/2026 --to-date 31/01/2026 --output-dir download/2026-01 --enable-dvc
  python -m gdt_tax --case-id 11320250292469209
  python -m gdt_tax --solver manual            # tự nhập CAPTCHA từng lần
  python -m gdt_tax --dry-run                  # chỉ tra cứu, không tải

Khi cổng đổi giao diện, chạy kèm các tham số chẩn đoán:
  python -m gdt_tax -v --log-file logs/run.log --dump-http http-dump
  python -m gdt_tax --header "Referer=https://dichvucong.gdt.gov.vn/tthc/tchs"
  python -m gdt_tax --header-profile minimal   # loại trừ lỗi do header (mặc định: browser)

Chạy trên máy ở nước ngoài (cổng chặn IP ngoài Việt Nam):
  python -m gdt_tax --proxy 1.2.3.4:8080:tai-khoan:mat-khau
"""


def parse_solver_options(items: list[str] | None) -> dict:
    """Đổi ``--solver-option KEY=VALUE`` thành dict (giá trị JSON nếu hợp lệ)."""
    options: dict = {}
    for item in items or []:
        key, _, raw = item.partition("=")
        key = key.strip()
        if not key:
            continue
        raw = raw.strip()
        try:
            options[key] = json.loads(raw)
        except json.JSONDecodeError:
            options[key] = raw
    return options


def parse_headers(items: list[str] | None) -> dict[str, str]:
    """Đổi ``--header Ten=Gia tri`` hoặc ``--header Ten: Gia tri`` thành dict.

    Nhận cả ``=`` và ``:`` vì đọc header kiểu HTTP quen tay hơn, còn ``=`` thì
    giống ``--solver-option``. Giá trị được giữ nguyên, kể cả khi có dấu ``:``.
    """
    headers: dict[str, str] = {}
    for item in items or []:
        positions = [index for index in (item.find("="), item.find(":")) if index > 0]
        if not positions:
            continue
        cut = min(positions)
        name, value = item[:cut].strip(), item[cut + 1 :].strip()
        if name:
            headers[name] = value
    return headers


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gdt-tax",
        description="Tải hồ sơ thuế: legacy trước cutoff; DVC tạm tắt mặc định.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--from-date", metavar="dd/mm/yyyy", help="Ngày bắt đầu tra cứu")
    parser.add_argument("--to-date", metavar="dd/mm/yyyy", help="Ngày kết thúc tra cứu")
    parser.add_argument("--case-id", help="Chỉ tải một mã hồ sơ cụ thể")
    parser.add_argument("--output-dir", help="Thư mục lưu ZIP và metadata")
    parser.add_argument(
        "--solver",
        help=f"Bộ nhận dạng CAPTCHA: {', '.join(available_solvers())}",
    )
    parser.add_argument(
        "--solver-option",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Tham số cho solver, lặp lại được nhiều lần",
    )
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE, help="File cấu hình dạng .env")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ tra cứu, không tải ZIP")
    parser.add_argument(
        "--list-solvers", action="store_true", help="Liệt kê solver CAPTCHA rồi thoát"
    )
    parser.add_argument(
        "--header",
        action="append",
        default=[],
        metavar="TÊN=GIÁ_TRỊ",
        help=(
            "Thêm hoặc ghi đè header cho mọi request, lặp lại được "
            "(dùng khi cổng yêu cầu header mới)"
        ),
    )
    parser.add_argument(
        "--log-file",
        metavar="FILE",
        help="Ghi thêm toàn bộ log ở mức chi tiết ra file (kèm header/body của request)",
    )
    parser.add_argument(
        "--dump-http",
        metavar="THƯ_MỤC",
        help="Lưu nguyên request/response ra thư mục để dựng fixture khi cổng đổi",
    )
    parser.add_argument(
        "--proxy",
        metavar="HOST:PORT:USER:PASS",
        help=(
            "Đi qua proxy cho mọi request, ví dụ 1.2.3.4:8080:tai-khoan:mat-khau "
            "hoặc http://tai-khoan:mat-khau@1.2.3.4:8080 (cần proxy Việt Nam khi "
            "chạy trên máy ở nước ngoài)"
        ),
    )
    parser.add_argument(
        "--legacy-etax",
        action="store_true",
        help=(
            "Dùng trực tiếp trang Thuế điện tử cũ trước cutoff (đã bật mặc định)"
        ),
    )
    parser.add_argument(
        "--header-profile",
        choices=list(PROFILES),
        help=(
            f"Bộ header gửi đi: {PROFILE_BROWSER} (mặc định, gửi Sec-Fetch-*, "
            f"sec-ch-ua* như Chrome thật) hoặc {PROFILE_MINIMAL} (để loại trừ lỗi "
            "do header)"
        ),
    )
    dvc = parser.add_mutually_exclusive_group()
    dvc.add_argument("--enable-dvc", dest="dvc_enabled", action="store_true", default=None,
                     help="Mở lại tra cứu trên dichvucong.gdt.gov.vn")
    dvc.add_argument("--disable-dvc", dest="dvc_enabled", action="store_false",
                     help="Tạm tắt DVC, kể cả khi GDT_DVC_ENABLED=true")
    parser.add_argument("-v", "--verbose", action="store_true", help="Log chi tiết")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def log_secrets(settings, proxy: Proxy | None) -> tuple[str, ...]:
    """Chuỗi phải che khi ghi log: thông tin proxy **và** mật khẩu tài khoản.

    Mật khẩu tài khoản vốn đã bị che theo tên trường ``matKhau`` khi ghi body,
    nhưng vẫn đưa vào đây để không lọt ra ở bất kỳ thông báo nào khác (log của
    thư viện ngoài, traceback, URL có tham số...).
    """
    values = list(proxy.secrets()) if proxy is not None else []
    if settings.password:
        values.append(settings.password)
    return tuple(values)


def main(argv: list[str] | None = None) -> int:
    try:
        return _main(argv)
    finally:
        close_logging()


def _main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_solvers:
        try:
            configure_logging(args.verbose, log_file=args.log_file)
        except OSError as error:
            print(f"LỖI CẤU HÌNH: không mở được file log: {error}", file=sys.stderr)
            return EXIT_CONFIG_ERROR
        print("\n".join(available_solvers()))
        return EXIT_OK

    try:
        settings = Settings.from_env(
            env_file=args.env_file,
            from_date=args.from_date,
            to_date=args.to_date,
            case_id=args.case_id,
            download_dir=args.output_dir,
            captcha_solver=args.solver,
            captcha_options=parse_solver_options(args.solver_option) or None,
            dry_run=True if args.dry_run else None,
            extra_headers=parse_headers(args.header) or None,
            log_file=args.log_file,
            http_dump_dir=args.dump_http,
            header_profile=args.header_profile,
            proxy_url=args.proxy,
            legacy_etax=True if args.legacy_etax else None,
            dvc_enabled=args.dvc_enabled,
        )
    except (ConfigError, ValueError) as error:
        print(f"LỖI CẤU HÌNH: {error}", file=sys.stderr)
        return EXIT_CONFIG_ERROR

    proxy = parse_proxy(settings.proxy_url)
    try:
        configure_logging(
            args.verbose,
            log_file=settings.log_file or None,
            secrets=log_secrets(settings, proxy),
        )
    except OSError as error:
        print(f"LỖI CẤU HÌNH: không mở được file log: {error}", file=sys.stderr)
        return EXIT_CONFIG_ERROR

    logger = logging.getLogger(LOGGER_NAME)
    if proxy is not None:
        logger.info("Dùng proxy %s", proxy.label)
    logger.debug(
        "gdt-tax %s | Python %s | %s | header profile=%s",
        __version__,
        platform.python_version(),
        platform.platform(),
        settings.header_profile,
    )
    if settings.extra_headers:
        logger.debug("Header ghi đè: %s", header_names(settings.extra_headers))
    if not any(settings.source_enabled(p.source) for p in settings.periods()):
        logger.warning("Không có đoạn ngày được bật: DVC đang tạm tắt. Chọn ngày trước cutoff hoặc dùng --enable-dvc.")
        return EXIT_INCOMPLETE
    try:
        register_plugins(settings.captcha_plugins)
        captcha = create_solver(settings.captcha_solver, **settings.captcha_options)
    except CaptchaError as error:
        logger.error("%s", error)
        return EXIT_CONFIG_ERROR

    http = HttpClient(
        timeout=settings.request_timeout,
        retries=settings.http_retries,
        logger=logger,
        extra_headers=settings.extra_headers,
        dump_dir=settings.http_dump_dir or None,
        header_profile=settings.header_profile,
        proxy=proxy,
    )
    try:
        summary = Pipeline(settings, http, captcha, logger=logger).run()
    except (GdtError, OSError) as error:
        logger.error("%s", error)
        return EXIT_INCOMPLETE
    finally:
        http.close()
        captcha.close()

    logger.info("KẾT QUẢ: %s/%s hồ sơ đã tải, %s đoạn bị bỏ qua",
                summary.downloaded, summary.expected, summary.skipped_periods)
    if settings.dry_run:
        logger.info("Dry-run: tìm thấy %s hồ sơ, %s đoạn bị bỏ qua.", summary.discovered, summary.skipped_periods)
        return EXIT_OK if summary.search_complete else EXIT_INCOMPLETE
    if settings.case_id and summary.expected == 1 and summary.downloaded == 0:
        logger.warning(
            "Không tìm thấy hoặc không tải được %s trong khoảng ngày đã cấu hình",
            settings.case_id,
        )
    return EXIT_OK if summary.complete else EXIT_INCOMPLETE


__all__ = ["build_parser", "main", "parse_headers", "parse_solver_options"]
