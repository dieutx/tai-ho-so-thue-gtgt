"""Virtualized table, typed sorting, independent file filters and selection."""
from __future__ import annotations

import json
from decimal import Decimal

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QCheckBox, QHeaderView

from .documents import FILE_LABELS, display_amount, document_id, event_datetime, needs_review

COLUMNS = {
    'tax': [('_selected', 'Chọn'), ('to_khai', 'Hồ sơ / Tờ khai'), ('ky_tinh_thue', 'Kỳ tính thuế'),
            ('ngay_nop', 'Ngày nộp'), ('trang_thai', 'Trạng thái thuế'), ('_file_status', 'Tệp ZIP'), ('_action', 'Thao tác')],
    'gnt': [('_selected', 'Chọn'), ('so_gnt', 'Số giấy nộp tiền'), ('ngay_lap', 'Ngày lập'),
            ('so_tien', 'Số tiền'), ('trang_thai', 'Trạng thái nộp / phê duyệt'), ('_file_status', 'Tệp XML'), ('_action', 'Thao tác')],
    'notice': [('_selected', 'Chọn'), ('ten_thong_bao', 'Số / Tên thông báo'), ('ngay_gui', 'Ngày gửi'),
               ('trang_thai', 'Trạng thái xem'), ('_file_status', 'Tệp PDF'), ('_action', 'Thao tác')],
    'offline': [('form_name', 'Mẫu / Tệp'), ('form_code', 'Mã mẫu'), ('form_version', 'Phiên bản'),
                ('status', 'Kết quả phân tích'), ('source_zip', 'Nguồn')],
}
EMPTY = QModelIndex()


class RecordsModel(QAbstractTableModel):
    selection_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: list[dict] = []
        self.mode = 'tax'
        self.checked: set[str] = set()
        self.can_download = False

    def reset(self, mode: str, rows: list[dict]) -> None:
        self.beginResetModel()
        self.mode, self.rows = mode, rows
        self.checked.clear()
        self.endResetModel()
        self.selection_changed.emit()

    def rowCount(self, parent=EMPTY):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=EMPTY):
        return 0 if parent.isValid() else len(COLUMNS[self.mode])

    def flags(self, index):
        flags = super().flags(index)
        if index.isValid() and COLUMNS[self.mode][index.column()][0] == '_selected':
            flags |= Qt.ItemFlag.ItemIsUserCheckable
        if index.isValid() and COLUMNS[self.mode][index.column()][0] == '_action':
            if not self.can_download and self.rows[index.row()].get('_file_status') != 'downloaded':
                flags &= ~Qt.ItemFlag.ItemIsEnabled
        return flags

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.CheckStateRole or not index.isValid() or index.column() != 0 or self.mode == 'offline':
            return False
        key = document_id(self.mode, self.rows[index.row()])
        if value in (Qt.CheckState.Checked, Qt.CheckState.Checked.value):
            self.checked.add(key)
        else:
            self.checked.discard(key)
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])
        self.selection_changed.emit()
        return True

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        key = COLUMNS[self.mode][index.column()][0]
        if role == Qt.ItemDataRole.CheckStateRole and key == '_selected':
            return Qt.CheckState.Checked if document_id(self.mode, row) in self.checked else Qt.CheckState.Unchecked
        if role == Qt.ItemDataRole.ToolTipRole:
            if key == '_selected':
                return 'Chọn tệp này; chọn toàn bộ kết quả đang hiển thị bằng tiêu đề Chọn'
            if key == '_file_status':
                return '\n'.join(str(row.get(k) or '') for k in ['_file_state', '_file_path', '_file_reason', '_error_message']).strip()
            return json.dumps(row, ensure_ascii=False, indent=2)
        if role == Qt.ItemDataRole.TextAlignmentRole and key == 'so_tien':
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ForegroundRole:
            if key == '_file_status':
                return QColor({'downloaded': '#15805B', 'failed': '#C94242'}.get(row.get(key), '#67768C'))
            if key == 'trang_thai' and needs_review(row):
                return QColor('#93631B')
            if key == 'trang_thai' and str(row.get(key, '')).casefold().startswith(('đã chấp nhận', 'nộp thuế thành công', 'đã xem')):
                return QColor('#15805B')
            if key == '_action':
                return QColor('#225DE9' if self.can_download or row.get('_file_status') == 'downloaded' else '#94A3B8')
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if key == '_selected':
            return ''
        if key == '_file_status':
            return FILE_LABELS.get(row.get(key, 'not_downloaded'), 'Chưa tải')
        if key == '_action':
            return 'Mở tệp' if row.get('_file_status') == 'downloaded' else 'Thử lại' if row.get('_file_status') == 'failed' else 'Tải tệp'
        if key == 'so_tien':
            return display_amount(row.get(key), str(row.get('loai_tien', '')))
        if key == 'to_khai':
            return str(row.get(key) or row.get('ten_tthc') or row.get('ma_ho_so') or '—')
        if key == 'so_gnt':
            value = str(row.get(key) or row.get('ctu_id') or '—')
            return value if len(value) < 29 else value[:11] + '…' + value[-13:]
        if key == 'ten_thong_bao':
            return '\n'.join(str(row.get(k) or '') for k in ['so_thong_bao', 'ten_thong_bao']).strip() or str(row.get('message_id', '—'))
        value = row.get(key)
        if self.mode == 'offline' and key == 'form_name' and not value:
            value = row.get('source_inner_file') or row.get('source_zip') or row.get('artifact_id')
        return '—' if value is None or value == '' else str(value)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if section == 0 and self.mode != 'offline' and role in {Qt.ItemDataRole.AccessibleTextRole, Qt.ItemDataRole.AccessibleDescriptionRole}:
            return 'Chọn hoặc bỏ chọn toàn bộ hồ sơ đang hiển thị. Ctrl+A khi ở bảng.'
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal and section == 0 and self.mode != 'offline':
                return ''
            return COLUMNS[self.mode][section][1] if orientation == Qt.Orientation.Horizontal else str(section + 1)
        if role == Qt.ItemDataRole.ToolTipRole and section == 0 and self.mode != 'offline':
            return 'Chọn / bỏ chọn toàn bộ kết quả đang hiển thị sau tìm kiếm và bộ lọc'
        if role == Qt.ItemDataRole.ToolTipRole and orientation == Qt.Orientation.Horizontal:
            return COLUMNS[self.mode][section][1]
        return None


class SelectionHeader(QHeaderView):
    """Real header checkbox; scope is all rows visible through the proxy."""
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.checkbox = QCheckBox(self.viewport())
        self.checkbox.setTristate(True)
        self.checkbox.setAccessibleName('Chọn tất cả hồ sơ đang hiển thị')
        self.checkbox.setToolTip('Chọn / bỏ chọn tất cả hồ sơ đang hiển thị sau bộ lọc')
        self.checkbox.clicked.connect(lambda _checked: self.sectionClicked.emit(0))

    def mousePressEvent(self, event):
        proxy = self.parent().model()
        self._checkbox_pressed = bool(event.button() == Qt.MouseButton.LeftButton and self.logicalIndexAt(event.position().toPoint()) == 0
                                      and proxy and proxy.sourceModel().mode != 'offline')
        if self._checkbox_pressed:
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if getattr(self, '_checkbox_pressed', False):
            self._checkbox_pressed = False
            if self.logicalIndexAt(event.position().toPoint()) == 0:
                self.sectionClicked.emit(0)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def paintSection(self, painter, rect, logical_index):
        super().paintSection(painter, rect, logical_index)
        proxy = self.parent().model()
        model = proxy.sourceModel() if proxy else None
        if logical_index != 0 or model is None or model.mode == 'offline':
            if model is not None and model.mode == 'offline':
                self.checkbox.hide()
            return
        visible = set()
        for row in range(proxy.rowCount()):
            source_row = proxy_source_row(proxy, proxy.index(row, 0))
            if source_row is not None and source_row < model.rowCount():
                visible.add(document_id(model.mode, model.rows[source_row]))
        self.checkbox.setGeometry(rect.center().x() - 8, rect.center().y() - 8, 18, 18)
        self.checkbox.blockSignals(True)
        self.checkbox.setCheckState(Qt.CheckState.Checked if visible and visible.issubset(model.checked)
                                    else Qt.CheckState.PartiallyChecked if visible & model.checked else Qt.CheckState.Unchecked)
        self.checkbox.blockSignals(False)
        self.checkbox.show()


def proxy_source_row(proxy: QSortFilterProxyModel, index: QModelIndex) -> int | None:
    """Đổi chỉ số của proxy thành dòng nguồn, an toàn với chỉ số cũ.

    Qt 6.8 có thể crash trong ``mapToSource`` khi bảng vừa được reset/lọc lại
    (mapping bị xoá) mà chỉ số vẫn mang dòng của mapping cũ. Gọi ``rowCount()``
    trước để Qt dựng lại mapping, rồi kiểm tra biên trước khi map.
    """
    if not index.isValid() or index.model() is not proxy:
        return None
    row, column = index.row(), index.column()
    if row < 0 or column < 0 or row >= proxy.rowCount() or column >= proxy.columnCount():
        return None
    mapped = proxy.mapToSource(index)
    return mapped.row() if mapped.isValid() else None


class RecordsProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.query_text = ''
        self.status_filter = 'all'

    def source_row(self, index: QModelIndex) -> int | None:
        """Dòng nguồn của một chỉ số proxy; ``None`` nếu chỉ số đã cũ/không hợp lệ."""
        return proxy_source_row(self, index)

    def setFilterFixedString(self, text):
        self.query_text = text.casefold().strip()
        self.invalidateFilter()

    def set_status_filter(self, status):
        self.status_filter = status
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()
        row = model.rows[source_row]
        if self.query_text and self.query_text not in ' '.join(str(v) for k, v in row.items() if not k.startswith('_')).casefold():
            return False
        status = row.get('_file_status', 'not_downloaded')
        return self.status_filter == 'all' or (self.status_filter == 'review' and needs_review(row)) or status == self.status_filter

    def lessThan(self, left, right):
        model = self.sourceModel()
        key = COLUMNS[model.mode][left.column()][0]
        first, second = model.rows[left.row()], model.rows[right.row()]
        if key in {'ngay_nop', 'ngay_lap', 'ngay_gui'}:
            return event_datetime(first.get(key)) < event_datetime(second.get(key))
        if key == 'so_tien':
            from .documents import amount_value
            a, b = amount_value(first.get(key)), amount_value(second.get(key))
            return (a if a is not None else Decimal('-Infinity')) < (b if b is not None else Decimal('-Infinity'))
        return str(first.get(key) or '').casefold() < str(second.get(key) or '').casefold()
