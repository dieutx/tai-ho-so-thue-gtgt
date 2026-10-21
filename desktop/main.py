"""Development: python -m desktop.main. Frozen entry uses the same function."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    from desktop.crash_log import install_crash_log
    install_crash_log()
    parser = argparse.ArgumentParser(description="Tải Hồ Sơ Thuế desktop")
    parser.add_argument("--self-test", metavar="FIXTURE_DIRECTORY")
    parser.add_argument("--test-output")
    parser.add_argument("--test-report")
    parser.add_argument("--ui-check", metavar="OUTPUT_DIRECTORY")
    parser.add_argument("--ui-size", default="1024x728")
    parser.add_argument("--quit-after", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--online-check", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.online_check:
        from desktop.online_check import online_check
        return online_check(args.online_check)
    if args.self_test:
        from desktop.smoke import self_test
        return self_test(Path(args.self_test), Path(args.test_output), Path(args.test_report))
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from desktop.ui import MainWindow
    application = QApplication.instance() or QApplication(sys.argv[:1])
    application.setApplicationName("TaiHoSoThue")
    application.setOrganizationName("TaiHoSoThue")
    application.setStyle("Fusion")
    window = MainWindow()
    window.show()
    if args.ui_check:
        from desktop.smoke import ui_check
        QTimer.singleShot(100, lambda: ui_check(application, window, Path(args.ui_check), args.ui_size))
    if args.quit_after:
        QTimer.singleShot(args.quit_after, application.quit)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
