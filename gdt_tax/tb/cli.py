"""Giao diện dòng lệnh cho luồng thông báo của cơ quan thuế.

Chạy được trên cả Windows và Linux::

    python -m gdt_tax.tb --from-date 01/08/2026 --to-date 30/09/2026
    gdt-tb --from-date 01/08/2026 --to-date 30/09/2026 --output-dir download/tb-2026-08-09

Tải PDF thông báo trên trang Thuế điện tử cũ (etaxnnt) và xuất
``danh_sach_thong_bao.xlsx``. Không parse nội dung PDF.

Mã thoát: ``0`` thành công, ``1`` chạy xong nhưng thiếu file, ``2`` lỗi cấu hình.
"""

from __future__ import annotations

import argparse
import logging
import platform
import sys

from .. import __version__
from ..captcha import available_solvers, create_solver, register_plugins
from ..cli import (
    EXIT_CONFIG_ERROR,
    EXIT_INCOMPLETE,
    EXIT_OK,
    log_secrets,
    parse_headers,
    parse_solver_options,
    personal_captcha_options,
)
from ..config import DEFAULT_ENV_FILE, Settings
from ..errors import CaptchaError, ConfigError, GdtError
from ..headers import PROFILE_BROWSER, PROFILE_MINIMAL, PROFILES, header_names
from ..http import HttpClient
from ..logging_setup import close_logging, configure_logging, configure_streams
from ..proxy import parse_proxy
from .pipeline import TbPipeline

LOGGER_NAME = "gdt_tax.tb"

EXAMPLES = """\
Ví dụ:
  python -m gdt_tax.tb --from-date 01/08/2026 --to-date 30/09/2026
  python -m gdt_tax.tb --from-date 01/08/2026 --to-date 31/08/2026 --output-dir download/tb-2026-08
  python -m gdt_tax.tb --dry-run                 # chỉ tra cứu, không tải PDF
  gdt-tb --from-date 01/01/2026 --to-date 31/03/2026
  gdt-tb --account-type CN --from-date 01/01/2026 --to-date 31/03/2026

Kết quả trong --output-dir:
  <số thông báo>__<messageId>.pdf
  danh_sach_thong_bao.xlsx / .csv / .json

Chẩn đoán khi cổng đổi giao diện (dùng chung với gdt-tax):
  python -m gdt_tax.tb -v --log-file logs/tb.log --dump-http http-dump-tb
  python -m gdt_tax.tb --header-profile minimal
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gdt-tb",
        description=(
            "Tải thông báo của cơ quan thuế trên trang Thuế điện tử cũ và xuất Excel tổng hợp."
        ),
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--from-date", metavar="dd/mm/yyyy", help="Từ ngày nộp")
    parser.add_argument("--to-date", metavar="dd/mm/yyyy", help="Đến ngày nộp")
    parser.add_argument("--output-dir", help="Thư mục lưu PDF và danh mục thông báo")
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
    parser.add_argument(
        "--account-type",
        choices=("DN", "CN"),
        help=("Loại tài khoản: DN = doanh nghiệp (mặc định), "
              "CN = cá nhân trên canhan.gdt.gov.vn"),
    )
    parser.add_argument("--dry-run", action="store_true", help="Chỉ tra cứu, không tải PDF")
    parser.add_argument(
        "--list-solvers", action="store_true", help="Liệt kê solver CAPTCHA rồi thoát"
    )
    parser.add_argument(
        "--header",
        action="append",
        default=[],
        metavar="TÊN=GIÁ_TRỊ",
        help="Thêm hoặc ghi đè header cho mọi request, lặp lại được nhiều lần",
    )
    parser.add_argument(
        "--log-file",
        metavar="FILE",
        help="Ghi log chẩn đoán đã làm sạch, không ghi payload gốc",
    )
    parser.add_argument(
        "--dump-http",
        metavar="THƯ_MỤC",
        help="Lưu metadata/hash HTTP đã làm sạch vào thư mục chẩn đoán",
    )
    parser.add_argument("--dump-http-private", action="store_true", default=None,
                        help="Bật raw response trong thư mục PRIVATE; không dùng cho gói hỗ trợ")
    parser.add_argument(
        "--proxy",
        metavar="HOST:PORT:USER:PASS",
        help="Đi qua proxy cho mọi request (cần proxy Việt Nam khi chạy ở nước ngoài)",
    )
    parser.add_argument(
        "--header-profile",
        choices=list(PROFILES),
        help=f"Bộ header gửi đi: {PROFILE_BROWSER} (mặc định) hoặc {PROFILE_MINIMAL}",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Log chi tiết")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_streams()
    try:
        return _main(argv)
    finally:
        close_logging()


def _main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

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
            download_dir=args.output_dir,
            captcha_solver=args.solver,
            captcha_options=parse_solver_options(args.solver_option) or None,
            dry_run=True if args.dry_run else None,
            extra_headers=parse_headers(args.header) or None,
            log_file=args.log_file,
            http_dump_dir=args.dump_http,
            http_dump_private=args.dump_http_private,
            header_profile=args.header_profile,
            proxy_url=args.proxy,
            account_type=args.account_type,
            dvc_enabled=False if args.account_type == "CN" else None,
            etax_cutoff="01/01/2100" if args.account_type == "CN" else None,
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
        "gdt-tb %s | Python %s | %s | header profile=%s",
        __version__,
        platform.python_version(),
        platform.platform(),
        settings.header_profile,
    )
    if settings.extra_headers:
        logger.debug("Header ghi đè: %s", header_names(settings.extra_headers))

    try:
        register_plugins(settings.captcha_plugins)
        captcha_options = (personal_captcha_options(settings.captcha_solver, settings.captcha_options)
                           if settings.account_type == "CN" else settings.captcha_options)
        captcha = create_solver(settings.captcha_solver, **captcha_options)
    except CaptchaError as error:
        logger.error("%s", error)
        return EXIT_CONFIG_ERROR

    http = HttpClient(
        timeout=settings.request_timeout,
        retries=settings.http_retries,
        logger=logger,
        extra_headers=settings.extra_headers,
        dump_dir=settings.http_dump_dir or None,
        private_dump=settings.http_dump_private,
        header_profile=settings.header_profile,
        proxy=proxy,
    )
    try:
        summary = TbPipeline(settings, http, captcha, logger=logger).run()
    except (GdtError, OSError) as error:
        logger.error("%s", error)
        return EXIT_INCOMPLETE
    finally:
        http.close()
        captcha.close()

    logger.info(
        "KẾT QUẢ thông báo: %s/%s đã tải, %s đoạn",
        summary.downloaded, summary.discovered, summary.periods,
    )
    if settings.dry_run:
        logger.info("Dry-run: tìm thấy %s thông báo.", summary.discovered)
        return EXIT_OK
    return EXIT_OK if summary.complete else EXIT_INCOMPLETE


__all__ = ["build_parser", "main"]
