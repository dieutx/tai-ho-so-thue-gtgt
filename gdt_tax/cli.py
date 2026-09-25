"""Giao diện dòng lệnh.

Chạy được trên cả Windows và Linux::

    python -m gdt_tax --from-date 01/01/2025 --to-date 31/01/2025 --output-dir download/2025-01

Mã thoát: ``0`` thành công, ``1`` chạy xong nhưng thiếu hồ sơ, ``2`` lỗi cấu hình.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from . import __version__
from .captcha import available_solvers, create_solver, register_plugins
from .config import DEFAULT_ENV_FILE, Settings
from .errors import CaptchaError, ConfigError, GdtError
from .http import HttpClient
from .logging_setup import configure_logging
from .pipeline import Pipeline

LOGGER_NAME = "gdt_tax"

EXIT_OK = 0
EXIT_INCOMPLETE = 1
EXIT_CONFIG_ERROR = 2

EXAMPLES = """\
Ví dụ:
  python -m gdt_tax --from-date 01/01/2025 --to-date 31/01/2025
  python -m gdt_tax --from-date 01/01/2026 --to-date 31/01/2026 --output-dir download/2026-01
  python -m gdt_tax --case-id 11320250292469209
  python -m gdt_tax --solver manual            # tự nhập CAPTCHA từng lần
  python -m gdt_tax --dry-run                  # chỉ tra cứu, không tải
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gdt-tax",
        description="Tải hồ sơ thuế GTGT từ Cổng Dịch vụ công của Cục Thuế.",
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
    parser.add_argument("-v", "--verbose", action="store_true", help="Log chi tiết")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.verbose)

    if args.list_solvers:
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
        )
    except (ConfigError, ValueError) as error:
        print(f"LỖI CẤU HÌNH: {error}", file=sys.stderr)
        return EXIT_CONFIG_ERROR

    logger = logging.getLogger(LOGGER_NAME)
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
    )
    try:
        summary = Pipeline(settings, http, captcha, logger=logger).run()
    except GdtError as error:
        logger.error("%s", error)
        return EXIT_INCOMPLETE
    finally:
        http.close()
        captcha.close()

    logger.info("HOÀN TẤT: %s/%s hồ sơ đã tải", summary.downloaded, summary.expected)
    if settings.dry_run:
        logger.info("Dry-run: đã tra cứu %s hồ sơ, không tải file nào.", summary.expected)
        return EXIT_OK
    if settings.case_id and summary.expected == 1 and summary.downloaded == 0:
        logger.warning(
            "Không tìm thấy hoặc không tải được %s trong khoảng ngày đã cấu hình",
            settings.case_id,
        )
    return EXIT_OK if summary.complete else EXIT_INCOMPLETE


__all__ = ["build_parser", "main", "parse_solver_options"]
