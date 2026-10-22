"""Bảng con phản hồi CQT của **một** lần nộp (detail table, không popup lồng).

Dùng ``desktop.feedback_service.list_feedback_items`` để bảo đảm đúng owner và
đúng thứ tự. Panel không đọc ``_notices`` của dòng khác và không tự gắn thông
báo thuế độc lập vào tờ khai.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .domain import (
    BUSINESS_ACCEPTED,
    BUSINESS_LABELS,
    BUSINESS_RECEIVED,
    BUSINESS_REJECTED,
    BUSINESS_UNKNOWN,
    format_date,
    submission_key,
)
from .feedback_service import FeedbackItem, list_feedback_items

TYPE_LABELS = {
    BUSINESS_RECEIVED: 'Tiếp nhận',
    BUSINESS_ACCEPTED: 'Chấp nhận',
    BUSINESS_REJECTED: 'Không chấp nhận',
    BUSINESS_UNKNOWN: 'Phản hồi khác / Chưa phân loại',
}
RESULT_PREFIX = {
    BUSINESS_ACCEPTED: '✓ ',
    BUSINESS_REJECTED: '✕ ',
    BUSINESS_RECEIVED: '• ',
    BUSINESS_UNKNOWN: '? ',
}
RESULT_COLORS = {
    BUSINESS_ACCEPTED: '#15805B',
    BUSINESS_REJECTED: '#C94242',
    BUSINESS_RECEIVED: '#67768C',
    BUSINESS_UNKNOWN: '#67768C',
}
COLUMNS = ['STT', 'Loại phản hồi', 'Số / Mã thông báo', 'Ngày thông báo',
           'Ngày nhận', 'Kết quả', 'XML']


class FeedbackPanel(QWidget):
    """Panel master-detail: mỗi dòng là một phản hồi, mở đúng tệp của dòng đó."""

    open_asset = Signal(object)
    save_asset = Signal(object)
    open_folder = Signal(object)
    technical = Signal(object)
    closed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName('feedbackPanel')
        self.setAccessibleName('Bảng phản hồi của cơ quan thuế')
        self.items: list[FeedbackItem] = []
        self.row: dict = {}
        self.taxpayer_key = ''
        self.submission_key = ''
        self.setMinimumHeight(190)
        self.setMaximumHeight(360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(4)
        header = QHBoxLayout()
        self.title = QLabel('Phản hồi CQT')
        self.title.setObjectName('feedbackTitle')
        header.addWidget(self.title, 1)
        self.close_button = QPushButton('Đóng')
        self.close_button.setToolTip('Đóng bảng phản hồi và quay lại danh sách')
        self.close_button.setAccessibleName('Đóng bảng phản hồi')
        self.close_button.clicked.connect(self._close)
        header.addWidget(self.close_button)
        layout.addLayout(header)
        self.empty = QLabel()
        self.empty.setWordWrap(True)
        self.empty.setObjectName('feedbackEmpty')
        self.empty.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.empty)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setWordWrap(False)
        self.table.setAlternatingRowColors(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setMinimumSectionSize(42)
        self.table.setAccessibleName('Phản hồi của cơ quan thuế cho tờ khai đang chọn')
        self.table.cellActivated.connect(self._activate)
        layout.addWidget(self.table, 1)
        self.table.hide()

    def _close(self) -> None:
        self.hide()
        self.closed.emit()

    def current_item(self) -> FeedbackItem | None:
        index = self.table.currentRow()
        return self.items[index] if 0 <= index < len(self.items) else None

    def _activate(self, row: int, _column: int) -> None:
        if 0 <= row < len(self.items):
            self.open_asset.emit(self.items[row])

    def _secondary_menu(self, row: int) -> QMenu:
        item = self.items[row]
        menu = QMenu(self)
        menu.addAction('Mở bằng ứng dụng mặc định',
                       lambda: self.open_asset.emit(item))
        menu.addAction('Lưu tệp…', lambda: self.save_asset.emit(item))
        menu.addAction('Mở thư mục chứa tệp', lambda: self.open_folder.emit(item))
        menu.addSeparator()
        menu.addAction('Thông tin kỹ thuật', lambda: self.technical.emit(item))
        return menu

    def _cell(self, text: str, *, tooltip: str = '', align=None) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        if tooltip:
            item.setToolTip(tooltip)
        if align is not None:
            item.setTextAlignment(align)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    def _file_actions(self, row: int, item: FeedbackItem) -> QWidget:
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        path = Path(item.asset.path_or_handle)
        available = bool(item.asset.path_or_handle) and path.is_file()
        is_xml = item.asset.content_type == 'application/xml'
        primary = QPushButton('Xem XML' if is_xml else 'Mở tệp')
        primary.setToolTip(('Xem XML của phản hồi này' if is_xml
                            else 'Mở tệp phản hồi bằng ứng dụng mặc định')
                           if available else 'Chưa có tệp phản hồi trên máy')
        primary.setEnabled(available)
        primary.clicked.connect(lambda _checked=False, item=item: self.open_asset.emit(item))
        layout.addWidget(primary)
        more = QPushButton('⋯')
        more.setToolTip('Thao tác khác cho tệp phản hồi')
        more.setAccessibleName('Thao tác khác cho tệp phản hồi')
        more.setFixedWidth(28)
        more.clicked.connect(lambda _checked=False, row=row: self._secondary_menu(row).exec(
            more.mapToGlobal(more.rect().bottomLeft())))
        layout.addWidget(more)
        return box

    def show_for(self, row: dict, *, taxpayer_key: str = '') -> None:
        """Dựng lại toàn bộ bảng từ đúng snapshot của ``row``."""
        self.row = dict(row)
        self.taxpayer_key = taxpayer_key
        self.submission_key = submission_key(row, taxpayer_key=taxpayer_key)
        self.items = list_feedback_items(row, taxpayer_key=taxpayer_key)
        name = str(row.get('to_khai') or row.get('ma_ho_so') or 'tờ khai')
        self.title.setText(f'Phản hồi CQT — {name} ({len(self.items)})')
        self.table.setRowCount(0)
        if not self.items:
            problem = str(row.get('_feedback_problem') or '')
            self.table.hide()
            self.empty.setText((problem + '\n' if problem else '')
                               + 'Chưa có phản hồi trong dữ liệu hiện có. Khi tải hồ sơ, '
                                 'phản hồi của cơ quan thuế (nếu có) sẽ xuất hiện ở đây.')
            self.empty.show()
            return
        self.empty.hide()
        self.table.show()
        self.table.setRowCount(len(self.items))
        for index, item in enumerate(self.items):
            feedback = item.feedback
            result = feedback.business_result
            number = feedback.notice_number or '—'
            self.table.setItem(index, 0, self._cell(str(index + 1),
                                                    align=Qt.AlignmentFlag.AlignCenter))
            self.table.setItem(index, 1, self._cell(
                TYPE_LABELS.get(feedback.feedback_type, TYPE_LABELS[BUSINESS_UNKNOWN])))
            self.table.setItem(index, 2, self._cell(number, tooltip=number))
            self.table.setItem(index, 3, self._cell(format_date(feedback.issued_at) or '—',
                                                    tooltip=feedback.issued_at or 'Chưa có ngày thông báo'))
            self.table.setItem(index, 4, self._cell(format_date(feedback.received_at) or '—',
                                                    tooltip='Chưa có ngày nhận trong dữ liệu'))
            result_item = self._cell(RESULT_PREFIX.get(result, '') + BUSINESS_LABELS.get(result, 'Chưa xác định'))
            result_item.setForeground(QBrush(QColor(RESULT_COLORS.get(result, '#67768C'))))
            self.table.setItem(index, 5, result_item)
            self.table.setCellWidget(index, 6, self._file_actions(index, item))
        header = self.table.horizontalHeader()
        for column, width in enumerate((45, 128, 190, 118, 100, 150)):
            self.table.setColumnWidth(column, width)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.table.resizeRowsToContents()

    def clear(self) -> None:
        self.items = []
        self.row = {}
        self.submission_key = ''
        self.table.setRowCount(0)
        self.title.setText('Phản hồi CQT')
        self.empty.clear()
        self.hide()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._close()
            event.accept()
            return
        super().keyPressEvent(event)


__all__ = ['FeedbackPanel', 'COLUMNS', 'TYPE_LABELS']
