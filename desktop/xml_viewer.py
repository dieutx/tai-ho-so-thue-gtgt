"""XML Viewer dùng chung cho phản hồi CQT và thông báo thuế.

Hai chế độ: **Nội dung dễ đọc** (chỉ các trường nhận diện được) và **XML gốc**
(nguyên văn, chỉ đọc). Parser dùng ``gdt_tax.parser.xml_reader.parse_xml``:
không resolve entity/DTD, không gọi mạng, có trần bytes. Nội dung hiển thị
được escape; ``QPlainTextEdit`` không thực thi HTML/script.

Viewer là modal và đọc tệp tại thời điểm mở, nên không tái sử dụng trạng thái
của tài liệu trước đó. ``owner_kind + owner_key + asset_key`` được giữ để truy
vết đúng nguồn, không trộn hai nghiệp vụ.
"""
from __future__ import annotations

import html
import shutil
from pathlib import Path
from typing import Any

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QFontDatabase
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
)

from gdt_tax.parser.xml_reader import XmlReadError, parse_xml

from .domain import (
    BUSINESS_LABELS,
    OWNER_DECLARATION,
    OWNER_FEEDBACK,
    OWNER_TAX_NOTICE,
    format_date,
)
from .feedback_labels import TYPE_LABELS
from .xml_content import contains_dtd, decode_xml, detect_encoding, readable_fields

MAX_VIEW_BYTES = 8 * 1024 * 1024

SOURCE_LABELS = {
    OWNER_FEEDBACK: 'Phản hồi CQT',
    OWNER_TAX_NOTICE: 'Thông báo thuế',
    OWNER_DECLARATION: 'Tệp tờ khai',
}
def _summary_parts(summary: Any) -> tuple[str, str, str]:
    number = (getattr(summary, 'notice_number', '') or getattr(summary, 'number', '')
              or getattr(summary, 'tax_notice_key', ''))
    result = getattr(summary, 'business_result', '')
    type_label = TYPE_LABELS.get(getattr(summary, 'feedback_type', ''), '')
    if not type_label:
        type_label = getattr(summary, 'notice_type', '') or ''
    issued = format_date(getattr(summary, 'issued_at', ''))
    return number, ' · '.join(part for part in (type_label, issued) if part), BUSINESS_LABELS.get(result, '')


class XmlViewer(QDialog):
    def __init__(self, parent, asset, *, source_kind: str, summary: Any = None) -> None:
        super().__init__(parent)
        self.asset = asset
        self.source_kind = source_kind
        self.summary = summary
        self.path = Path(asset.path_or_handle)
        self.data = b''
        self.text = ''
        self.encoding = ''
        self.is_xml = asset.content_type == 'application/xml' or self.path.suffix.lower() == '.xml'
        self.error = ''
        self._build()
        self._load()

    @classmethod
    def show_asset(cls, parent, asset, *, source_kind: str, summary: Any = None) -> XmlViewer:
        dialog = cls(parent, asset, source_kind=source_kind, summary=summary)
        dialog.exec()
        dialog.deleteLater()
        return dialog

    def _build(self) -> None:
        self.setWindowTitle('Xem tài liệu')
        self.resize(980, 700)
        self.setMinimumSize(640, 420)
        layout = QVBoxLayout(self)
        self.title_label = QLabel()
        self.title_label.setObjectName('viewerTitle')
        self.title_label.setWordWrap(True)
        self.title_label.setToolTip(f'owner_kind={self.asset.owner_kind}\n'
                                    f'owner_key={self.asset.owner_key}\n'
                                    f'asset_key={self.asset.asset_key}')
        layout.addWidget(self.title_label)
        self.subtitle = QLabel()
        self.subtitle.setWordWrap(True)
        layout.addWidget(self.subtitle)
        self.tabs = QTabWidget()
        self.readable = QTextBrowser()
        self.readable.setOpenLinks(False)
        self.raw = QPlainTextEdit()
        self.raw.setReadOnly(True)
        self.raw.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.raw.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.tabs.addTab(self.readable, 'Nội dung dễ đọc')
        self.tabs.addTab(self.raw, 'XML gốc')
        layout.addWidget(self.tabs, 1)
        self.identity = QLabel()
        self.identity.setObjectName('hint')
        self.identity.setWordWrap(True)
        self.identity.setText(f'Nguồn kỹ thuật: {self.asset.owner_kind} · {self.asset.asset_key}')
        layout.addWidget(self.identity)
        actions = QHBoxLayout()
        self.copy_button = QPushButton('Sao chép XML')
        self.copy_button.clicked.connect(self.copy_xml)
        self.save_button = QPushButton('Lưu XML')
        self.save_button.clicked.connect(self.save_file)
        self.open_button = QPushButton('Mở bằng ứng dụng mặc định')
        self.open_button.clicked.connect(self.open_external)
        actions.addWidget(self.copy_button)
        actions.addWidget(self.save_button)
        actions.addWidget(self.open_button)
        actions.addStretch()
        close = QPushButton('Đóng')
        close.setToolTip('Đóng cửa sổ xem tài liệu')
        close.clicked.connect(self.reject)
        actions.addWidget(close)
        layout.addLayout(actions)
        if not self.is_xml:
            self.copy_button.setEnabled(False)
            self.save_button.setText('Lưu tệp')
            self.tabs.setTabText(1, 'Nội dung gốc')

    def _header(self) -> None:
        number, details, result = _summary_parts(self.summary) if self.summary is not None else ('', '', '')
        source = SOURCE_LABELS.get(self.source_kind, 'Tài liệu')
        label = number or self.asset.original_filename or self.path.name
        self.title_label.setText(f'{source} — {label}')
        parts = [details, f'Kết quả: {result}' if result else '']
        self.subtitle.setText(' · '.join(part for part in parts if part))

    def _load(self) -> None:
        self._header()
        if not self.path.is_file():
            self.error = 'Tệp không còn tồn tại hoặc đã bị di chuyển.'
            self._show_error(self.error)
            self.copy_button.setEnabled(False)
            self.save_button.setEnabled(False)
            self.open_button.setEnabled(False)
            return
        try:
            size = self.path.stat().st_size
        except OSError as error:
            self.error = f'Không đọc được thông tin tệp: {error}'
            self._show_error(self.error)
            self.copy_button.setEnabled(False)
            self.save_button.setEnabled(False)
            self.open_button.setEnabled(False)
            return
        if size > MAX_VIEW_BYTES:
            self.error = (f'Tệp lớn hơn {MAX_VIEW_BYTES // (1024 * 1024)} MiB; '
                          'không hiển thị toàn bộ trong ứng dụng. Dùng Lưu tệp hoặc Mở bằng ứng dụng.')
            self._show_error(self.error)
            self.copy_button.setEnabled(False)
            return
        try:
            self.data = self.path.read_bytes()
        except OSError as error:
            self.error = f'Không đọc được tệp: {error}'
            self._show_error(self.error)
            self.copy_button.setEnabled(False)
            self.save_button.setEnabled(False)
            self.open_button.setEnabled(False)
            return
        self.text, self.encoding = decode_xml(self.data)
        if not self.is_xml:
            self.raw.setPlainText('Tệp nhị phân (PDF/ZIP) — không hiển thị nội dung trong XML Viewer.')
            self.readable.setHtml(
                '<h3>Nội dung dễ đọc</h3>'
                '<p>Chưa hỗ trợ trình bày nội dung này. Đây là tệp PDF/ZIP; '
                'dùng <b>Mở bằng ứng dụng mặc định</b>.</p>')
            self.copy_button.setEnabled(False)
            return
        self.raw.setPlainText(self.text)
        warning = ''
        if contains_dtd(self.data):
            warning = 'XML có DOCTYPE/ENTITY; đã tắt phân giải entity và không gọi mạng.'
        try:
            root = parse_xml(self.data)
        except XmlReadError as error:
            parts = ['<h3>Nội dung dễ đọc</h3>']
            if warning:
                parts.append(f'<p style="color:#93631B">{html.escape(warning)}</p>')
            parts.append(f'<p style="color:#C94242">{html.escape(str(error))}</p>')
            parts.append('<p>Chưa hỗ trợ trình bày nội dung này. Vẫn xem được <b>XML gốc</b>.</p>')
            self.readable.setHtml(''.join(parts))
            return
        fields = readable_fields(root)
        self.readable.setHtml(self._readable_html(fields, warning))

    def _readable_html(self, fields: dict[str, str], warning: str) -> str:
        parts = ['<h3>Nội dung dễ đọc</h3>']
        if warning:
            parts.append(f'<p style="color:#93631B">{html.escape(warning)}</p>')
        if self.summary is not None:
            _, details, result = _summary_parts(self.summary)
            if details:
                parts.append(f'<p><span style="color:#67768C">Phân loại / ngày:</span> {html.escape(details)}</p>')
            if result:
                parts.append(f'<p><span style="color:#67768C">Kết quả đã đọc:</span> <b>{html.escape(result)}</b></p>')
        if fields:
            parts.append('<table cellspacing="0" cellpadding="4" width="100%">')
            for label, value in fields.items():
                parts.append(f'<tr><td style="color:#67768C;width:170px">{html.escape(label)}</td>'
                             f'<td><b>{html.escape(value)}</b></td></tr>')
            parts.append('</table>')
        else:
            parts.append('<p>Chưa hỗ trợ trình bày nội dung này. Xem tab <b>XML gốc</b>.</p>')
        parts.append('<p><span style="color:#67768C">Chỉ hiển thị trường nhận diện được; '
                     'không suy đoán thêm số/ngày/kết quả.</span></p>')
        return ''.join(parts)

    def _show_error(self, message: str) -> None:
        self.readable.setHtml('<h3>Nội dung dễ đọc</h3>'
                              f'<p style="color:#C94242">{html.escape(message)}</p>')
        self.raw.setPlainText('Không đọc được tệp.' if not self.text else self.text)

    def copy_xml(self) -> None:
        if not self.is_xml:
            return
        if not self.text:
            QMessageBox.information(self, 'Không có XML', 'Tệp này chưa đọc được nội dung XML.')
            return
        QApplication.clipboard().setText(self.text)

    def save_file(self) -> None:
        if not self.path.is_file():
            QMessageBox.warning(self, 'Không lưu được', 'Tệp gốc không còn tồn tại.')
            return
        suggested = str(Path.home() / (self.asset.original_filename or self.path.name))
        filters = 'XML (*.xml);;Tất cả (*)' if self.is_xml else 'Tất cả (*)'
        target, _ = QFileDialog.getSaveFileName(self, 'Lưu tệp', suggested, filters)
        if not target:
            return
        target_path = Path(target)
        try:
            if target_path.resolve() == self.path.resolve():
                QMessageBox.warning(self, 'Chọn vị trí khác', 'Không ghi đè tệp gốc.')
                return
            shutil.copyfile(self.path, target_path)
        except OSError as error:
            QMessageBox.warning(self, 'Không lưu được', f'Không ghi được tệp: {error}')
            return
        QMessageBox.information(self, 'Đã lưu', f'Đã lưu {target_path.name}.')

    def open_external(self) -> None:
        if not self.path.is_file():
            QMessageBox.warning(self, 'Không mở được', 'Tệp không còn tồn tại hoặc đã bị di chuyển.')
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.path.resolve()))):
            QMessageBox.warning(self, 'Không mở được', 'Windows chưa có ứng dụng mở loại tệp này.')


__all__ = [
    'MAX_VIEW_BYTES',
    'SOURCE_LABELS',
    'XmlViewer',
    'contains_dtd',
    'decode_xml',
    'detect_encoding',
    'readable_fields',
]
