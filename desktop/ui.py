"""Compact Qt Widgets workspace. Only tables and dialogs scroll."""
from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path

from PySide6.QtCore import (
    QDate,
    Qt,
    QTimer,
    QUrl,
)
from PySide6.QtGui import QDesktopServices, QFontDatabase, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from gdt_tax.config import load_env_file

from . import __version__
from .account_dialog import AccountDialog
from .jobs import CaptchaRequest, JobController
from .services import JobResult, RunConfig
from .settings_store import Preferences, SettingsStore, default_output
from .state import TabState, job_output
from .table_model import COLUMNS as COLUMNS
from .table_model import RecordsModel as RecordsModel
from .updates import RELEASES_URL, UpdateChecker
from .v2_interactions import V2InteractionMixin
from .v2_layout import build_workspace

MODES = ["tax", "gnt", "notice", "offline"]
TITLES = ["Tờ khai", "Giấy nộp tiền", "Thông báo thuế", "Phân tích XML"]


def fit_dialog(dialog: QWidget, width: int = 660, height: int = 560) -> None:
    area = dialog.screen().availableGeometry()
    dialog.resize(min(width, area.width() - 24), min(height, area.height() - 32))


def button(text: str, callback, tooltip: str = "") -> QPushButton:
    result = QPushButton(text)
    result.clicked.connect(callback)
    result.setToolTip(tooltip or text)
    result.setAccessibleName(tooltip or text)
    return result


def field(text: str, password: bool = False) -> QLineEdit:
    result = QLineEdit()
    result.setPlaceholderText(text)
    result.setAccessibleName(text)
    result.setToolTip(text)
    result.setMinimumWidth(30)
    if password:
        result.setEchoMode(QLineEdit.EchoMode.Password)
    return result


class PathEdit(QLineEdit):
    def __init__(self, label: str) -> None:
        super().__init__()
        self.full_path = ""
        self.setPlaceholderText(label)
        self.setAccessibleName(label)
        self.setMinimumWidth(35)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def setText(self, value: str) -> None:
        self.full_path = value
        self.setToolTip(value)
        self.refresh()

    def text(self) -> str:
        return super().text() if self.hasFocus() else self.full_path

    def refresh(self) -> None:
        super().setText(self.full_path if self.hasFocus() else self.fontMetrics().elidedText(Path(self.full_path).name if self.full_path else "", Qt.TextElideMode.ElideMiddle, max(10, self.width() - 14)))

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self.refresh()

    def focusOutEvent(self, event) -> None:
        self.full_path = super().text()
        super().focusOutEvent(event)
        self.setToolTip(self.full_path)
        self.refresh()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not self.hasFocus():
            self.refresh()


class AdvancedDialog(QDialog):
    def __init__(self, parent: MainWindow) -> None:
        super().__init__(parent)
        self.setWindowTitle("Cài đặt nâng cao")
        self.owner = parent
        self.fields: dict[str, QWidget] = {}
        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        form = QFormLayout(content)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        scroll.setWidget(content)
        layout.addWidget(scroll)
        definitions = [
            ("output", "Thư mục mặc định", "text"), ("solver", "CAPTCHA", ["ddddocr", "manual"]),
            ("timeout", "Timeout (giây)", (1, 600)), ("retries", "Số lần HTTP", (1, 20)),
            ("login_attempts", "Số lần đăng nhập", (1, 50)), ("search_attempts", "Số lần tra cứu", (1, 50)),
            ("record_delay", "Nghỉ giữa hồ sơ (giây)", (0.0, 120.0)),
            ("page_delay", "Nghỉ giữa trang (giây)", (0.0, 120.0)),
            ("jitter", "Jitter", (0.0, 1.0)), ("page_size", "Số dòng / trang", (1, 100)),
            ("max_days", "Ngày / đoạn", (1, 31)), ("header_profile", "Header profile", ["browser", "minimal"]),
            ("cutoff", "Cutoff dd/MM/yyyy", "text"), ("theme", "Giao diện", ["light", "dark"]),
        ]
        for name, label, kind in definitions:
            if kind == "text":
                widget = field(label)
            elif isinstance(kind, list):
                widget = QComboBox()
                widget.addItems(kind)
            elif isinstance(kind[0], float):
                widget = QDoubleSpinBox()
                widget.setRange(*kind)
            else:
                widget = QSpinBox()
                widget.setRange(*kind)
            widget.setAccessibleName(label)
            self.fields[name] = widget
            form.addRow(label, widget)
        self.proxy = field("Proxy — chỉ lưu trong phiên", True)
        self.proxy.setText(parent.proxy)
        form.addRow("Proxy (phiên)", self.proxy)
        self.headers = QPlainTextEdit(json.dumps(parent.extra_headers, ensure_ascii=False))
        self.headers.setMaximumHeight(85)
        form.addRow("Header JSON (phiên)", self.headers)
        self.dvc = QCheckBox("Bật DVC (mặc định bật; tính năng thử nghiệm)")
        self.dvc.setChecked(parent.dvc)
        form.addRow(self.dvc)
        note = QLabel("DVC được bật mặc định theo cấu hình mới; có thể tắt để chỉ dùng ETAX legacy. Không lưu tài khoản, mật khẩu, proxy hoặc header. Nhật ký chỉ ở trong phiên.")
        note.setWordWrap(True)
        form.addRow(note)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setObjectName("warning")
        layout.addWidget(self.error)
        controls = QHBoxLayout()
        controls.addWidget(button("Mặc định", self.reset))
        controls.addWidget(button("Nhập .env…", self.import_env))
        controls.addStretch()
        controls.addWidget(button("Hủy", self.reject))
        controls.addWidget(button("Áp dụng", self.apply))
        layout.addLayout(controls)
        self.populate(parent.preferences)
        fit_dialog(self)

    def populate(self, preferences: Preferences) -> None:
        for key, value in asdict(preferences).items():
            widget = self.fields.get(key)
            if isinstance(widget, QLineEdit):
                widget.setText(str(value))
            elif isinstance(widget, QComboBox):
                widget.setCurrentText(str(value))
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                widget.setValue(value)

    def reset(self) -> None:
        self.populate(Preferences(output=str(default_output())))
        self.proxy.clear()
        self.headers.setPlainText("{}")
        self.dvc.setChecked(True)

    def import_env(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Nhập cấu hình cũ", "", "Cấu hình (*.env);;Tất cả (*)")
        if not filename:
            return
        try:
            # Imports only supported settings, not arbitrary plugin code or remote solver URLs.
            values = load_env_file(filename)
            mapping = {"output": "DOWNLOAD_DIR", "solver": "CAPTCHA_SOLVER", "timeout": "REQUEST_TIMEOUT",
                       "retries": "HTTP_RETRIES", "login_attempts": "LOGIN_ATTEMPTS", "search_attempts": "SEARCH_ATTEMPTS",
                       "record_delay": "PAUSE_BETWEEN_RECORDS", "page_delay": "PAUSE_BETWEEN_PAGES",
                       "jitter": "PAUSE_JITTER", "page_size": "PAGE_SIZE", "max_days": "MAX_DAYS_PER_SEARCH",
                       "header_profile": "HEADER_PROFILE", "cutoff": "ETAX_CUTOFF"}
            data = asdict(self.owner.preferences)
            for key, env in mapping.items():
                if f"GDT_{env}" in values:
                    data[key] = type(data[key])(values[f"GDT_{env}"])
            if data["solver"] not in {"manual", "ddddocr"}:
                raise ValueError("Bản desktop chỉ đóng gói ddddocr và manual")
            self.populate(Preferences(**data))
            self.proxy.setText(values.get("GDT_PROXY_URL", ""))
            self.headers.setPlainText(values.get("GDT_EXTRA_HEADERS", "{}"))
            self.imported = values
            self.error.setText("Đã đọc cấu hình. Thông tin đăng nhập sẽ mở trong dialog tài khoản, chỉ dùng ở phiên này. DVC theo lựa chọn ở trên.")
        except (OSError, ValueError) as error:
            self.error.setText(f"Không nhập được cấu hình: {error}")

    def apply(self) -> None:
        try:
            values = asdict(self.owner.preferences)
            for key, widget in self.fields.items():
                if isinstance(widget, QLineEdit):
                    values[key] = widget.text().strip()
                elif isinstance(widget, QComboBox):
                    values[key] = widget.currentText()
                else:
                    values[key] = widget.value()
            values["dvc_enabled"] = self.dvc.isChecked()
            prefs = Preferences(**values)
            headers = json.loads(self.headers.toPlainText())
            if not isinstance(headers, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in headers.items()):
                raise ValueError("Header phải là JSON gồm tên và giá trị chuỗi")
            config = RunConfig("tax", Path(prefs.output or self.owner.output.text()), username="validation", password="validation",
                               preferences=prefs, proxy=self.proxy.text().strip(), extra_headers=headers)
            config.settings()
            self.owner.store.save(prefs)
            self.owner.preferences = prefs
            self.owner.proxy = self.proxy.text().strip()
            self.owner.extra_headers = headers
            self.owner.dvc = self.dvc.isChecked()
            if prefs.output:
                self.owner.output.setText(prefs.output)
            imported = getattr(self, "imported", {})
            credentials = (imported.get("GDT_USERNAME", ""), imported.get("GDT_PASSWORD", ""))
            if any(credentials):
                QTimer.singleShot(0, lambda values=credentials: self.owner.open_login(initial=values))
            self.imported = {}
            for key, widget in [("GDT_FROM_DATE", self.owner.from_date), ("GDT_TO_DATE", self.owner.to_date)]:
                parsed = QDate.fromString(imported.get(key, ""), "dd/MM/yyyy")
                if parsed.isValid():
                    widget.setDate(parsed)
            self.owner.apply_theme()
            self.owner.warning_update()
            self.accept()
        except Exception as error:
            # Do not echo header/proxy input or a JSON decoder's source text.
            self.error.setText("Thiết lập chưa hợp lệ. Kiểm tra ngày cutoff, proxy, JSON header và quyền ghi cấu hình. " + type(error).__name__)


class MainWindow(V2InteractionMixin, QMainWindow):
    def __init__(self, store: SettingsStore | None = None) -> None:
        super().__init__()
        # Qt's offscreen Windows backend does not enumerate installed fonts.
        # Use the same system fonts for deterministic screenshots/tests.
        if QApplication.platformName() == "offscreen" and not QFontDatabase.families():
            for name in ["segoeui.ttf", "segoeuib.ttf", "seguisym.ttf"]:
                QFontDatabase.addApplicationFont(str(Path("C:/Windows/Fonts") / name))
        self.setWindowTitle("Tải Hồ Sơ Thuế")
        self.setWindowIcon(QIcon(str(Path(__file__).parent / "resources" / "app.ico")))
        self.store = store or SettingsStore()
        self.startup_error = ""
        try:
            self.preferences = self.store.load()
        except (OSError, ValueError) as error:
            self.preferences = Preferences()
            self.startup_error = str(error)
        self.proxy, self.extra_headers, self.dvc = "", {}, self.preferences.dvc_enabled
        self.result: JobResult | None = None
        self.active_config: RunConfig | None = None
        self.log_history: list[tuple[int, str]] = []
        self.log_dialog: QDialog | None = None
        self.captcha_dialog: QDialog | None = None
        self.close_pending = False
        self.ultra = False
        self.current_mode = "tax"
        self.conditions_collapsed = False
        self.applying_preset = False
        self.source_files = ()
        self.pending_rows = {}
        self.history = []
        self.last_task = None
        self.tab_states = {mode: TabState() for mode in MODES}
        self.after_login = None
        self.deferred_account_action = None
        self.batch_modes = ("tax", "gnt", "notice")
        self.case_filter = ""
        self.controller = JobController(self)
        self.controller.state_changed.connect(self.on_state)
        self.controller.progress.connect(self.on_progress)
        self.controller.completed.connect(self.on_completed)
        self.controller.captcha.connect(self.on_captcha)
        self.controller.logs.connect(self.on_logs)
        self.build_ui()
        self.apply_theme()
        self.resize(1080, 670)
        self.warning_update()
        QTimer.singleShot(0, self.fit_screen)
        if self.startup_error:
            QTimer.singleShot(0, lambda: self.error(self.startup_error))

    def build_ui(self) -> None:
        build_workspace(self)

    def show_release(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Phiên bản và cập nhật")
        outer = QVBoxLayout(dialog)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        layout = QVBoxLayout(body)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        title = QLabel(f"Tải Hồ Sơ Thuế • v{__version__}")
        title.setObjectName("title")
        layout.addWidget(title)
        details = QLabel("Mới: một tài khoản/phiên ETAX cho ba nghiệp vụ; DVC mặc định bật và dùng phiên riêng; trạng thái thuế/tệp tách biệt; tải riêng/tải chọn lọc; preset kỳ; khung chi tiết và lịch sử; bản Full có OCR tự động.\n\nEXE chưa ký số. Thư mục dữ liệu và cấu hình nằm ngoài EXE.")
        details.setWordWrap(True)
        layout.addWidget(details)
        info = Path(__file__).parent / "resources" / "release.json"
        if info.is_file():
            try:
                release = json.loads(info.read_text(encoding="utf-8"))
                layout.addWidget(QLabel("Build: " + str(release.get("built_at_utc", "chưa ghi nhận"))))
                layout.addWidget(QLabel("Core: " + str(release.get('core_version', '1.0.0')) +
                                        " • Source: " + str(release.get('source_sha', 'chưa ghi nhận'))[:12]))
            except (OSError, ValueError):
                pass
        status = QLabel("Chỉ kết nối GitLab khi bạn bấm Kiểm tra bản mới. Không gửi thông tin tài khoản thuế.")
        status.setWordWrap(True)
        status.setOpenExternalLinks(True)
        layout.addWidget(status)
        check = button("Kiểm tra bản mới", lambda: None)
        checker = UpdateChecker(self)
        checker.done.connect(status.setText)
        checker.done.connect(lambda _message: check.setEnabled(True) if check.isVisible() else None)
        def start_check():
            status.setText("Đang kiểm tra trang phát hành…")
            check.setEnabled(False)
            checker.start()
        check.clicked.connect(start_check)
        layout.addWidget(check)
        layout.addWidget(button("Mở trang phát hành / tải cập nhật", lambda: QDesktopServices.openUrl(QUrl(RELEASES_URL))))
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        controls.rejected.connect(dialog.reject)
        outer.addWidget(controls)
        fit_dialog(dialog, 580, 370)
        dialog.exec()
        checker.done.disconnect()
        dialog.deleteLater()

    @property
    def mode(self) -> str:
        return MODES[self.tabs.currentIndex()]

    def warning_update(self, *_args) -> None:
        if not hasattr(self, "from_date"):
            return
        warning = self.mode == "tax" and not self.dvc and self.to_date.date() >= QDate.fromString(self.preferences.cutoff, "dd/MM/yyyy")
        self.warning.setText(f"Từ {self.preferences.cutoff}: chưa tra cứu DVC — kết quả có thể chưa đầy đủ" if warning else "")
        self.warning.setVisible(warning)
        date_type = {"tax": "ngày nộp tờ khai", "gnt": "ngày lập GNT", "notice": "ngày gửi/nộp thông báo", "offline": "offline"}[self.mode]
        self.online_panel.setToolTip("Khoảng tra cứu theo " + date_type)
        self.date_type.setText({"tax": "Ngày nộp", "gnt": "Ngày lập", "notice": "Ngày gửi", "offline": ""}[self.mode])
        self.refresh_account()

    def refresh_account(self) -> None:
        if not hasattr(self, "account_label"):
            return
        account = self.controller.sessions.account
        self.account_label.setText(self.fontMetrics().elidedText("MST: " + (account.username or "—"),
                                  Qt.TextElideMode.ElideMiddle, self.account_label.maximumWidth()))
        self.account_label.setToolTip(account.username)
        labels = {"DISCONNECTED": "Chưa đăng nhập", "AUTHENTICATING": "Đang đăng nhập", "CONNECTED": "ETAX: Đã kết nối", "EXPIRED": "Cần đăng nhập lại"}
        self.source_badge.setText(labels[account.state])
        self.source_badge.setStyleSheet("color:" + ("#15803D" if account.state == "CONNECTED" else "#92400E") + ";")
        self.source_badge.setToolTip("DVC: Thử nghiệm, phiên riêng" if self.dvc else "DVC: Chưa bật; ETAX legacy trước cutoff")
        self.account_button.setText("Đổi tài khoản" if account.username else "Đăng nhập")
        self.account_button.setToolTip(labels[account.state] + " • " + account.username)
        self.logout_button.setEnabled(bool(account.username))

    def apply_theme(self) -> None:
        dark = self.preferences.theme == "dark"
        bg, card, text, border, muted = ("#111827", "#1e293b", "#f1f5f9", "#475569", "#94a3b8") if dark else ("#F5F7FB", "#FFFFFF", "#17263D", "#E4EAF2", "#67768C")
        self.setStyleSheet(f"""
            QWidget {{font-family:'Segoe UI';font-size:12px;color:{text};}}
            QMainWindow,QDialog {{background:{bg};}}
            QMenu,QAbstractItemView {{background:{card};color:{text};}}
            QMenu::item:selected {{background:#2563EB;color:white;}}
            QLabel#title {{font-size:19px;font-weight:600;}}
            QLabel#warning {{color:{'#fbbf24' if dark else '#92400e'};padding:3px;}}
            QLineEdit,QDateEdit,QComboBox,QSpinBox,QDoubleSpinBox,QPlainTextEdit,QTableView {{background:{card};border:1px solid {border};border-radius:5px;padding:5px;selection-background-color:#2563EB;}}
            QTableView {{alternate-background-color:{bg};gridline-color:{border};padding:0;}}
            QHeaderView::section {{background:{bg};color:{muted};border:0;border-bottom:1px solid {border};padding:6px;}}
            QPushButton {{background:{card};border:1px solid {border};border-radius:6px;padding:6px 10px;}}
            QPushButton:hover,QPushButton:focus,QLineEdit:focus,QComboBox:focus {{border:1px solid #2563EB;}}
            QPushButton#primary {{background:#225DE9;color:white;}}
            QPushButton#account {{background:#0F766E;color:white;border-color:#0F766E;}}
            QPushButton#query {{background:#EFF6FF;color:#1D4ED8;border-color:#BFDBFE;}}
            QPushButton#stop {{background:#FFF1F2;color:#BE123C;border-color:#FECDD3;}}
            QPushButton#files {{background:#F5F3FF;color:#6D28D9;border-color:#DDD6FE;}}
            QPushButton#stop:disabled,QPushButton#primary:disabled,QPushButton#query:disabled {{background:{bg};color:{muted};border-color:{border};}}
            QFrame#drawer {{background:{card};border:1px solid {border};border-radius:8px;}}
            QTextBrowser {{background:{card};border:0;padding:6px;}}
            QLabel#counters {{font-weight:600;color:{text};}}
            QLabel#hint {{color:{muted};}}
            QLabel#empty {{color:{muted};font-size:14px;}}
            QPushButton:disabled {{color:{muted};background:{bg};}}
            QTabBar::tab {{padding:7px 12px;color:{muted};}}
            QTabBar::tab:selected {{background:{card};color:#{'93c5fd' if dark else '2563EB'};border-bottom:2px solid #2563EB;}}
            QScrollArea {{border:0;}}
            QProgressBar {{background:{border};border:0;}} QProgressBar::chunk {{background:#2563EB;}}
        """)

    def clear_account_views(self) -> None:
        for mode in ["tax", "gnt", "notice"]:
            self.tab_states[mode] = TabState()
        if self.mode != "offline":
            self.result = None
            self.last_task = None
            self.model.reset(self.mode, [])
            self.search.clear()
            self.file_filter.setCurrentIndex(0)
            self.close_drawer()
            self.collapse_conditions(False)
            self.status.setText("Sẵn sàng")
            self.populate_result(None)
            self.update_empty()

    def account_action_allowed(self, action) -> bool:
        if not self.controller.busy:
            return True
        answer = QMessageBox.question(self, "Dừng tác vụ trước", "Dừng an toàn tác vụ hiện tại trước khi đổi/đăng xuất tài khoản?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self.deferred_account_action = action
            self.controller.stop()
        return False

    def open_login(self, _checked=False, *, initial=None, after=None) -> None:
        if not self.account_action_allowed(lambda: self.open_login(initial=initial, after=after)):
            return
        account = self.controller.sessions.account
        dialog = AccountDialog(self, *(initial or (account.username, "")))
        accepted = dialog.exec()
        credentials = dialog.take_credentials()
        dialog.deleteLater()
        if not accepted or not credentials:
            return
        old_username = account.username
        self.controller.sessions.set_account(*credentials)
        if old_username != account.username:
            self.clear_account_views()
        self.after_login = after
        config = self.make_config("login")
        self.launch(config, clear=False)
        self.refresh_account()

    def logout(self) -> None:
        if not self.account_action_allowed(self.logout):
            return
        self.controller.sessions.logout()
        self.clear_account_views()
        self.refresh_account()

    def task_options(self) -> None:
        if self.mode == "offline":
            self.offline_options()
        elif self.mode == "tax":
            dialog = QDialog(self)
            dialog.setWindowTitle("Bộ lọc tờ khai")
            form = QFormLayout(dialog)
            case = field("Chỉ một mã hồ sơ trong khoảng ngày (tùy chọn)")
            case.setText(self.case_filter)
            form.addRow("Mã hồ sơ", case)
            controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            controls.accepted.connect(dialog.accept)
            controls.rejected.connect(dialog.reject)
            form.addRow(controls)
            fit_dialog(dialog, 520, 160)
            if dialog.exec():
                self.case_filter = case.text().strip()
        else:
            self.error("Khoảng ngày và thư mục lưu được dùng chung. GNT dùng ngày lập; thông báo dùng ngày gửi/nộp.")

    def batch_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Tra cứu và tải các nhóm liên tiếp")
        layout = QVBoxLayout(dialog)
        fields = []
        for mode, label in zip(MODES[:3], TITLES[:3], strict=True):
            check = QCheckBox(label)
            check.setChecked(mode in self.batch_modes)
            layout.addWidget(check)
            fields.append((mode, check))
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        controls.accepted.connect(dialog.accept)
        controls.rejected.connect(dialog.reject)
        layout.addWidget(controls)
        if dialog.exec():
            self.batch_modes = tuple(mode for mode, check in fields if check.isChecked())
            if self.batch_modes:
                self.start_batch()

    def start_batch(self) -> None:
        if not self.controller.sessions.account.password:
            self.open_login(after=self.start_batch)
            return
        self.launch(self.make_config("batch"))

    def import_legacy(self) -> None:
        if self.mode == "offline":
            self.error("Chọn thư mục nguồn cũ ở ô Nguồn; chạy Kiểm kê hoặc toàn bộ để tạo báo cáo mới.")
            return
        source = QFileDialog.getExistingDirectory(self, "Chọn thư mục dữ liệu cũ của đúng MST đang dùng")
        if not source:
            return
        copy = False
        if self.controller.sessions.account.username:
            answer = QMessageBox.question(self, "Nhập hay chỉ xem dữ liệu cũ?", "Dữ liệu có thuộc MST đang hiển thị và bạn muốn sao chép sang thư mục riêng? Chọn Không để chỉ xem danh mục, không thay đổi tệp.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            copy = answer == QMessageBox.StandardButton.Yes
        config = self.make_config("import" if copy else "saved")
        config.stage = self.mode
        config.source = Path(source)
        config.output = job_output(Path(self.output.text()), config.username, self.mode) if copy else Path(source)
        self.launch(config)

    def browse(self, widget: QLineEdit) -> None:
        path = QFileDialog.getExistingDirectory(self, "Chọn thư mục", widget.text())
        if path:
            widget.setText(path)
            if widget is self.input_path:
                self.source_files = ()
                self.source_info.clear()
                self.stage.setCurrentIndex(0)

    def error(self, text: str) -> None:
        message = QMessageBox(QMessageBox.Icon.Warning, "Tải Hồ Sơ Thuế", text,
                              QMessageBox.StandardButton.Ok, self)
        message.setTextFormat(Qt.TextFormat.PlainText)
        message.exec()

    def settings(self) -> None:
        dialog = AdvancedDialog(self)
        dialog.exec()
        dialog.deleteLater()

    def offline_options(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Bộ lọc báo cáo / Tùy chọn offline")
        form = QFormLayout(dialog)
        fields = {}
        for key, label in [("tax_group", "Nhóm thuế"), ("form_code", "Mã mẫu"), ("form_version", "Phiên bản mẫu"), ("period", "Kỳ (raw)"), ("filing_type", "Loại nộp"), ("status", "Trạng thái parse")]:
            widget = field(label + " — trống = tất cả")
            widget.setText(self.filters.get(key, ""))
            form.addRow(label, widget)
            fields[key] = widget
        csv = QCheckBox("Ghi thêm Tax_Return_Summary.csv")
        csv.setChecked(self.csv)
        rehash = QCheckBox("Băm lại toàn bộ nguồn")
        rehash.setChecked(self.rehash)
        forms = field("Thư mục mapping tùy chỉnh (tùy chọn)")
        forms.setText(self.forms_dir)
        form.addRow("Mapping", forms)
        form.addRow(csv)
        form.addRow(rehash)
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        controls.accepted.connect(dialog.accept)
        controls.rejected.connect(dialog.reject)
        form.addRow(controls)
        fit_dialog(dialog, 600, 440)
        if dialog.exec():
            self.filters = {k: w.text().strip() for k, w in fields.items() if w.text().strip()}
            self.csv, self.rehash, self.forms_dir = csv.isChecked(), rehash.isChecked(), forms.text().strip()

    def make_config(self, mode: str, dry_run: bool = False) -> RunConfig:
        account = self.controller.sessions.account
        base = Path(self.output.text()).expanduser().resolve()
        target = job_output(base, account.username, mode) if mode in MODES else base
        return RunConfig(mode, target, username=account.username if mode != "offline" else "", password=account.password if mode != "offline" else "",
            from_date=self.from_date.date().toString("dd/MM/yyyy"), to_date=self.to_date.date().toString("dd/MM/yyyy"),
            case_id=self.case_filter, dry_run=dry_run, source=Path(self.input_path.text()).expanduser().resolve() if self.input_path.text().strip() else None,
            stage=self.stage.currentData(), preferences=replace(self.preferences), proxy=self.proxy, extra_headers=dict(self.extra_headers),
            dvc=self.dvc, filters=dict(self.filters), csv=self.csv, forms_dir=self.forms_dir, rehash=self.rehash, batch_modes=self.batch_modes, source_files=self.source_files)

    def start(self, dry_run: bool) -> None:
        if self.controller.busy:
            return
        if self.mode != "offline" and not self.controller.sessions.account.password:
            self.open_login(after=lambda: self.start(dry_run))
            return
        self.launch(self.make_config(self.mode, dry_run))

    def launch(self, config: RunConfig, clear: bool = True) -> None:
        if not self.output.text().strip():
            self.error("Chọn thư mục lưu chung")
            return
        try:
            if config.mode not in {"offline", "saved"}:
                config.settings()
            if self.controller.start(config):
                self.active_config = config
                if clear:
                    self.result = None
                    self.model.reset(self.mode, [])
                    self.pending_rows = {}
                    self.populate_result(None)
                    self.update_empty()
        except Exception:
            self.error("Không bắt đầu được. Kiểm tra tài khoản, ngày, proxy và cài đặt nâng cao.")

    def on_captcha(self, request: CaptchaRequest) -> None:
        from PySide6.QtGui import QPixmap
        dialog = QDialog(self)
        self.captcha_dialog = dialog
        dialog.setWindowTitle("Nhập CAPTCHA")
        layout = QVBoxLayout(dialog)
        explanation = QLabel(request.message)
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        image = QPixmap()
        image.loadFromData(request.image)
        label = QLabel()
        label.setPixmap(image.scaled(300, 100, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        layout.addWidget(label)
        entry = field("Mã trong ảnh")
        layout.addWidget(entry)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(lambda: dialog.accept() if entry.text().strip() else None)
        buttons.rejected.connect(dialog.reject)
        entry.returnPressed.connect(lambda: dialog.accept() if entry.text().strip() else None)
        layout.addWidget(buttons)
        fit_dialog(dialog, 390, 270)
        entry.setFocus()
        accepted = dialog.exec()
        request.respond(entry.text() if accepted else None)
        self.captcha_dialog = None
        self.controller.resume()

    def on_logs(self, batch) -> None:
        self.log_history = (self.log_history + batch)[-5000:]
        self.log_button.setText(f"Nhật ký kỹ thuật ({len(self.log_history)})")
        if self.log_dialog:
            self.render_logs()

    def show_logs(self) -> None:
        if self.log_dialog:
            self.log_dialog.raise_()
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Nhật ký đã ẩn bí mật — giữ tối đa 5.000 dòng")
        layout = QVBoxLayout(dialog)
        self.log_filter = QComboBox()
        for label, level in [("Tất cả", 0), ("Cảnh báo trở lên", 30), ("Lỗi", 40)]:
            self.log_filter.addItem(label, level)
        layout.addWidget(self.log_filter)
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("background:#0F172A;color:#E2E8F0;")
        layout.addWidget(self.log_text, 1)
        layout.addWidget(button("Sao chép", lambda: QApplication.clipboard().setText(self.log_text.toPlainText())))
        self.log_dialog = dialog
        self.log_filter.currentIndexChanged.connect(self.render_logs)
        dialog.finished.connect(lambda _result: setattr(self, "log_dialog", None))
        self.render_logs()
        fit_dialog(dialog, 850, 500)
        dialog.show()

    def render_logs(self, *_args) -> None:
        threshold = self.log_filter.currentData()
        self.log_text.setPlainText("\n".join(message for level, message in self.log_history if level >= threshold))

    def open_path(self, path: Path) -> None:
        if not path.exists():
            self.error("Tệp hoặc thư mục không còn tồn tại")
        elif not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve()))):
            self.error("Windows chưa có ứng dụng mở loại tệp này")

    def open_output(self) -> None:
        path = self.result.output if self.result else (self.active_config.output if self.active_config else Path(self.output.text()))
        self.open_path(path)

    def open_report(self) -> None:
        if self.result and self.result.files:
            self.open_path(next((p for p in self.result.files if p.suffix == ".xlsx"), self.result.files[0]))

    def open_file_choice(self, index: int) -> None:
        value = self.files.itemData(index)
        if value:
            self.open_path(Path(value))

    def selected_row(self) -> dict | None:
        index = self.table.currentIndex()
        return self.model.rows[self.proxy_model.mapToSource(index).row()] if index.isValid() else None

    def show_subview(self, _index: int) -> None:
        pass  # Configuration and results remain visible together.

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.responsive()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self.windowHandle() and not getattr(self, "screen_connected", False):
            self.screen_connected = True
            self.windowHandle().screenChanged.connect(self.screen_changed)
            self.screen_changed(self.screen())

    def screen_changed(self, screen) -> None:
        old = getattr(self, "watched_screen", None)
        if old:
            try:
                old.availableGeometryChanged.disconnect(self.fit_screen)
            except (RuntimeError, TypeError):
                pass
        self.watched_screen = screen
        screen.availableGeometryChanged.connect(self.fit_screen)
        QTimer.singleShot(0, self.fit_screen)

    def fit_screen(self, *_args) -> None:
        area = self.screen().availableGeometry().adjusted(8, 8, -8, -8)
        frame = self.frameGeometry()
        extra_w, extra_h = frame.width() - self.width(), frame.height() - self.height()
        self.resize(min(self.width(), area.width() - extra_w), min(self.height(), area.height() - extra_h))
        frame = self.frameGeometry()
        self.move(max(area.left(), min(frame.left(), area.right() - frame.width() + 1)),
                  max(area.top(), min(frame.top(), area.bottom() - frame.height() + 1)))
        self.responsive()

    def closeEvent(self, event) -> None:
        if self.controller.busy:
            if not self.close_pending:
                answer = QMessageBox.question(self, "Dừng và đóng", "Tác vụ đang chạy. Dừng an toàn rồi đóng sau khi ghi xong dữ liệu?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                if answer == QMessageBox.StandardButton.Yes:
                    self.close_pending = True
                    self.controller.stop()
            event.ignore()
            return
        self.controller.sessions.close()
        self.proxy, self.extra_headers = "", {}
        event.accept()
