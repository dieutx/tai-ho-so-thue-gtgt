"""Account-scoped document interactions for the v2 Qt workspace."""
from __future__ import annotations

import hashlib
import html
import json
import os
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QDate, QPoint, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
)

from .documents import (
    FILE_LABELS,
    counters,
    display_amount,
    document_id,
    document_label,
    remote_document_id,
)
from .domain import INTEGRITY_LABELS, INTEGRITY_NOT_CHECKED, submission_key
from .errors import issue_hint
from .library import catalog_view
from .notices import STATE_LABELS, attachment_totals, row_attachment_problem
from .services import RunConfig
from .table_model import COLUMNS


class V2InteractionMixin:
    def dates_changed(self, *_args):
        if self.applying_preset:
            return
        if not self.applying_preset:
            self.preset.blockSignals(True)
            self.preset.setCurrentIndex(self.preset.findData('custom'))
            self.preset.blockSignals(False)
        self.warning_update()
        self.apply_local_date_filter()

    def apply_preset(self, *_args):
        kind = self.preset.currentData()
        today = QDate.currentDate()
        if kind == 'custom':
            return
        end = today
        if kind == 'previous':
            prior = today.addMonths(-1)
            start = QDate(prior.year(), prior.month(), 1)
            end = start.addMonths(1).addDays(-1)
        elif kind == 'quarter':
            start = QDate(today.year(), ((today.month() - 1) // 3) * 3 + 1, 1)
        elif kind == 'year':
            start = QDate(today.year(), 1, 1)
        elif kind == 'twelve':
            start = today.addMonths(-12)
        else:
            start = QDate(today.year(), today.month(), 1)
        self.applying_preset = True
        self.from_date.setDate(start)
        self.to_date.setDate(end)
        self.applying_preset = False
        self.warning_update()
        self.apply_local_date_filter()

    def collapse_conditions(self, collapsed=True):
        self.conditions_collapsed = False
        self.config_panel.show()
        self.responsive()

    def save_tab(self):
        if not hasattr(self, 'model') or getattr(self, '_initializing', False):
            return
        state = self.tab_states[self.current_mode]
        state.rows, state.result = list(self.model.rows), self.result
        state.filter_text = self.search.text()
        state.status_filter = self.file_filter.currentData()
        state.cqt_filter = self.cqt_filter.currentData() or 'all'
        state.type_filter = self.type_filter.currentData() or ''
        state.scroll = self.table.verticalScrollBar().value()
        state.horizontal_scroll = self.table.horizontalScrollBar().value()
        state.sort_column = self.table.horizontalHeader().sortIndicatorSection()
        state.sort_descending = self.table.horizontalHeader().sortIndicatorOrder() == Qt.SortOrder.DescendingOrder
        state.column_widths = {
            key: self.table.columnWidth(index)
            for index, (key, _) in enumerate(COLUMNS[self.current_mode])
            if not self.table.isColumnHidden(index)
        }
        state.message = self.status.text()
        state.conditions_collapsed = self.conditions_collapsed
        state.last_task = self.last_task
        state.from_date = self.from_date.date().toString('dd/MM/yyyy')
        state.to_date = self.to_date.date().toString('dd/MM/yyyy')
        state.preset = self.preset.currentData() or 'custom'
        self.persist_ui_state()

    def mode_changed(self, index):
        if not hasattr(self, 'model'):
            return
        from .ui import MODES
        self.save_tab()
        self.close_drawer()
        if hasattr(self, 'feedback_panel'):
            self.feedback_panel.clear()
        self.current_mode = MODES[index]
        self.navigation.setCurrentIndex(index)
        offline = self.mode == 'offline'
        self.online_panel.setVisible(not offline)
        self.offline_panel.setVisible(offline)
        self.query.setVisible(not offline)
        self.batch_action.setVisible(not offline)
        self.file_filter.setVisible(not offline)
        self.cqt_filter.setVisible(self.mode == 'tax')
        self.type_filter.setVisible(self.mode == 'notice')
        for widget in [self.account_label, self.source_badge, self.account_button, self.logout_button]:
            widget.setVisible(not offline)
        state = self.tab_states[self.mode]
        self.restore_dates(state)
        self.result = state.result
        self.last_task = state.last_task
        self.model.reset(self.mode, state.rows)
        self.search.setText(state.filter_text)
        self.file_filter.setCurrentIndex(max(0, self.file_filter.findData(state.status_filter)))
        self.file_filter.view().setRowHidden(4, self.mode == 'notice')
        self.cqt_filter.setCurrentIndex(max(0, self.cqt_filter.findData(state.cqt_filter)))
        self.proxy_model.set_cqt_filter(state.cqt_filter)
        self.refresh_type_filter()
        index = self.type_filter.findData(state.type_filter)
        self.type_filter.setCurrentIndex(index if index >= 0 else 0)
        self.proxy_model.set_type_filter(self.type_filter.currentData() or '')
        column = state.sort_column
        if column < 0 or column >= len(COLUMNS[self.mode]):
            column = next((i for i, (key, _) in enumerate(COLUMNS[self.mode]) if key in {'ngay_nop', 'ngay_lap', 'ngay_gui'}), 0)
        self.table.sortByColumn(column, Qt.SortOrder.DescendingOrder if state.sort_descending else Qt.SortOrder.AscendingOrder)
        self.status.setText(state.message)
        self.populate_result(self.result)
        self.table.verticalScrollBar().setValue(state.scroll)
        self.table.horizontalScrollBar().setValue(state.horizontal_scroll)
        self.collapse_conditions(state.conditions_collapsed)
        self.warning_update()
        self.responsive()
        self.update_empty()
        if self.mode != 'offline' and not getattr(self, '_initializing', False):
            self.apply_local_date_filter()

    def restore_dates(self, state):
        self.applying_preset = True
        for widget, value in ((self.from_date, state.from_date), (self.to_date, state.to_date)):
            day = QDate.fromString(value, 'dd/MM/yyyy')
            if day.isValid():
                widget.setDate(day)
        self.preset.blockSignals(True)
        self.preset.setCurrentIndex(max(0, self.preset.findData(state.preset)))
        self.preset.blockSignals(False)
        self.applying_preset = False

    def set_file_filter(self):
        self.proxy_model.set_status_filter(self.file_filter.currentData())
        self.update_filtered_count()
        self.update_empty()

    def set_cqt_filter(self, *_args):
        if not hasattr(self, 'proxy_model'):
            return
        self.proxy_model.set_cqt_filter(self.cqt_filter.currentData() or 'all')
        self.update_filtered_count()
        self.update_empty()

    def set_type_filter(self, *_args):
        if not hasattr(self, 'proxy_model'):
            return
        self.proxy_model.set_type_filter(self.type_filter.currentData() or '')
        self.update_filtered_count()
        self.update_empty()

    def update_filtered_count(self, *_args):
        if not hasattr(self, 'filtered_label') or not hasattr(self, 'proxy_model'):
            return
        total = self.model.rowCount()
        visible = self.proxy_model.rowCount()
        self.filtered_label.setText(f'Hiển thị {visible}/{total}' if total else '')
        self.filtered_label.setVisible(bool(total))
        self.reset_filters_button.setEnabled(bool(
            self.search.text() or self.proxy_model.status_filter != 'all'
            or self.mode == 'tax' and self.proxy_model.cqt_filter != 'all'
            or self.mode == 'notice' and self.proxy_model.type_filter))
        if hasattr(self, 'selection_bar'):
            self.selection_changed()

    def reset_filters(self):
        """Khôi phục toàn bộ danh sách của tab; giữ kết quả và lựa chọn tải."""
        self.search.clear()
        self.file_filter.setCurrentIndex(0)
        self.cqt_filter.setCurrentIndex(0)
        self.type_filter.setCurrentIndex(0)
        self.update_filtered_count()
        self.update_empty()

    def load_local_library(self, *, after=None) -> bool:
        """Nạp danh mục đã lưu của tài khoản hiện tại trước mọi thao tác mạng."""
        account = self.controller.sessions.account
        base = str(self.output.text() or '').strip()
        if not account.username or not base:
            return False
        if self.controller.busy:
            return False
        config = RunConfig(
            'library', Path(base).expanduser(), username=account.username,
            account_type=account.account_type,
            from_date=self.from_date.date().toString('dd/MM/yyyy'),
            to_date=self.to_date.date().toString('dd/MM/yyyy'),
            preferences=replace(self.preferences),
        )
        self.local_after = after
        self.status.setText('Đang đọc hồ sơ đã lưu trên máy…')
        self.launch(config, clear=False)
        return True

    def apply_local_date_filter(self, *_args, completed=None):
        """Update visible rows; return the catalog outcome independently of the job."""
        if not hasattr(self, 'proxy_model') or getattr(self, '_initializing', False):
            return
        if (completed is None and self.result and self.result.operation == 'saved'
                and not (self.active_config and self.active_config.mode in {'tax', 'gnt', 'notice', 'batch'})):
            self.proxy_model.set_date_range(self.from_date.date().toPython(), self.to_date.date().toPython())
            self.update_filtered_count()
            self.update_empty()
            return
        account = self.controller.sessions.account
        if self.mode == 'offline' or not account.username:
            self.proxy_model.set_date_range(None, None)
            return
        try:
            selected = catalog_view(self.output.text(), account.username, self.mode,
                                    self.from_date.date().toString('dd/MM/yyyy'),
                                    self.to_date.date().toString('dd/MM/yyyy'),
                                    include_unknown=True, account_type=account.account_type)
        except Exception:
            self.status.setText('Không đọc được kho local; dữ liệu hiện tại được giữ. Kiểm tra nơi lưu và quyền sở hữu.')
            self.status.setToolTip(self.status.text())
            return
        if selected.state == 'ERROR':
            self.status.setText(selected.message)
            self.status.setToolTip(selected.message)
            return selected
        catalog_result = selected
        checked = set(self.model.checked)
        origin = completed or self.result
        if origin and origin.account_key == selected.account_key and origin.output == selected.output:
            selected.files = list(origin.files)
            if completed and completed.date_range == selected.date_range:
                # The catalog supplies the rows; the job remains the authority
                # for search completion, cancellation and errors in this range.
                selected = replace(completed, rows=selected.rows, discovered=selected.discovered,
                                   inventory_total=selected.inventory_total,
                                   unknown_dates=selected.unknown_dates, quarantined=selected.quarantined,
                                   state='PARTIAL' if selected.state == 'PARTIAL' and completed.state == 'SUCCESS' else completed.state,
                                   errors=max(1, completed.errors) if selected.state == 'PARTIAL' else completed.errors,
                                   message=completed.message + ('; ' + selected.message if selected.state == 'PARTIAL' else ''))
        self.result = selected
        self.proxy_model.set_date_range(None, None)
        self.model.reset(self.mode, selected.rows)
        self.model.checked = checked & {document_id(self.mode, row) for row in selected.rows}
        self.populate_result(selected)
        self.refresh_type_filter()
        self.close_drawer()
        if not self.controller.busy:
            self.status.setText('Hồ sơ trên máy — không gọi mạng' if selected.rows else
                                'Chưa có dữ liệu lưu trên máy trong kỳ này — bấm Tra cứu để đối soát')
        self.save_tab()
        self.update_filtered_count()
        self.update_empty()
        return catalog_result

    def refresh_type_filter(self, *_args):
        """Nạp loại thông báo thực có trong tab; không bịa nhóm không có dữ liệu."""
        if not hasattr(self, 'type_filter'):
            return
        current = self.type_filter.currentData() or ''
        self.type_filter.blockSignals(True)
        self.type_filter.clear()
        self.type_filter.addItem('Tất cả loại thông báo', '')
        if self.mode == 'notice':
            values = sorted({str(row.get('ten_thong_bao') or row.get('ma_tbao') or '').strip()
                             for row in self.model.rows} - {''})
            for value in values:
                self.type_filter.addItem(value, value)
        index = self.type_filter.findData(current)
        self.type_filter.setCurrentIndex(max(0, index))
        self.type_filter.blockSignals(False)
        if hasattr(self, 'proxy_model'):
            self.proxy_model.set_type_filter(self.type_filter.currentData() or '')

    def _remember_column_width(self, logical, _old, new):
        if getattr(self, '_applying_widths', False) or not hasattr(self, 'model'):
            return
        if 0 <= logical < len(COLUMNS[self.mode]):
            key = COLUMNS[self.mode][logical][0]
            self.tab_states[self.mode].column_widths[key] = int(new)

    def can_target_download(self):
        account = self.controller.sessions.account
        return bool(self.result and self.mode != 'offline' and all(self.result.date_range)
                    and self.result.operation in {'query', 'query_and_download', 'download_selected', 'library'}
                    and self.result.account_key == hashlib.sha256(account.username.encode()).hexdigest())

    def sync_actions(self):
        if not hasattr(self, 'missing_button'):
            return
        busy = self.controller.busy
        online = self.mode != 'offline'
        rows = self.model.rows if hasattr(self, 'model') else []
        count = counters(rows)
        can_download = self.can_target_download() and not busy
        if hasattr(self, 'model'):
            self.model.can_download = can_download
        self.missing_button.setVisible(online)
        self.missing_button.setEnabled(can_download and count['pending'] > 0)
        self.missing_button.setToolTip('Chỉ tải hồ sơ chưa có tệp trong toàn bộ kết quả của kỳ đã tra cứu; không phụ thuộc bộ lọc bảng'
                                       if self.can_target_download() else 'Tra cứu kỳ tương ứng bằng tài khoản hiện tại trước khi tải')
        self.retry_button.setVisible(online and count['failed'] > 0)
        self.retry_button.setEnabled(can_download and count['failed'] > 0)
        self.verify_button.setVisible(online and bool(rows))
        self.verify_button.setEnabled(not busy and bool(rows))
        folder = self.result.output if self.result else self.active_config.output if self.active_config else Path(self.output.text())
        exists = folder.is_dir()
        self.open_folder_button.setEnabled(exists)
        self.open_folder_button.setToolTip('Mở nơi lưu của kết quả hiện tại' if exists else 'Thư mục hồ sơ chưa tồn tại; sẽ được tạo khi tải')
        if hasattr(self, 'folder_button'):
            self.folder_button.setEnabled(exists)
        if hasattr(self, 'export_action'):
            self.export_action.setVisible(online)
            self.export_action.setEnabled(not busy and online and bool(rows))
        if hasattr(self, 'selection_bar'):
            self.selection_bar.setEnabled(not busy)
        if hasattr(self, 'detail_download'):
            self.detail_download.setText('Thử lại tệp' if self.detail_row and self.detail_row.get('_file_status') == 'failed' else 'Tải tệp')
            self.detail_download.setVisible(online)
            self.detail_download.setEnabled(can_download and bool(self.detail_row))
            self.detail_download.setToolTip('Chỉ tải tệp đang xem' if can_download else 'Tra cứu kỳ tương ứng bằng tài khoản hiện tại trước khi tải')

    def selection_changed(self):
        count = len(self.model.checked)
        self.selection_bar.setVisible(self.mode != 'offline' and count > 0)
        visible = set()
        if count:
            for index in range(self.proxy_model.rowCount()):
                source_row = self.proxy_model.source_row(self.proxy_model.index(index, 0))
                if source_row is not None:
                    visible.add(document_id(self.mode, self.model.rows[source_row]))
        hidden = len(self.model.checked - visible)
        self.selection_label.setText(f'Đã chọn {count} tệp' + (f' · {hidden} đang ẩn bởi bộ lọc' if hidden else ''))
        self.selection_label.setToolTip('Tải các tệp đã chọn sẽ tải cả tệp đang bị ẩn bởi bộ lọc. Bấm Bỏ chọn để xóa toàn bộ lựa chọn.')
        self.sync_actions()

    def clear_selection(self):
        self.model.checked.clear()
        if self.model.rowCount():
            self.model.dataChanged.emit(self.model.index(0, 0), self.model.index(self.model.rowCount() - 1, 0))
        self.selection_changed()

    def toggle_current_checkbox(self):
        index = self.table.currentIndex()
        if self.mode == 'offline' or self.controller.busy or not index.isValid():
            return
        source_row = self.proxy_model.source_row(index)
        if source_row is None or source_row >= len(self.model.rows):
            return
        key = document_id(self.mode, self.model.rows[source_row])
        self.model.setData(self.model.index(source_row, 0), Qt.CheckState.Unchecked if key in self.model.checked else Qt.CheckState.Checked,
                           Qt.ItemDataRole.CheckStateRole)

    def select_visible_header(self, column):
        if column != 0 or self.mode == 'offline' or self.controller.busy:
            return
        ids = set()
        for row in range(self.proxy_model.rowCount()):
            source_row = self.proxy_model.source_row(self.proxy_model.index(row, 0))
            if source_row is not None and source_row < len(self.model.rows):
                ids.add(document_id(self.mode, self.model.rows[source_row]))
        if ids and ids.issubset(self.model.checked):
            self.model.checked.difference_update(ids)
        else:
            self.model.checked.update(ids)
        if self.model.rowCount():
            self.model.dataChanged.emit(self.model.index(0, 0), self.model.index(self.model.rowCount() - 1, 0))
        self.selection_changed()

    def download_checked(self):
        self.download_rows([row for row in self.model.rows if document_id(self.mode, row) in self.model.checked])

    def download_missing(self):
        self.download_rows([row for row in self.model.rows if row.get('_file_status', 'not_downloaded') == 'not_downloaded'])

    def retry_failed(self):
        self.download_rows([row for row in self.model.rows if row.get('_file_status') == 'failed'])

    def download_rows(self, rows):
        if self.controller.busy or not rows:
            return
        if not self.can_target_download():
            self.error('Tra cứu kỳ tương ứng bằng tài khoản hiện tại trước khi tải các tệp này.')
            return
        from gdt_tax.identity import RecordKey
        account_key = self.result.account_key
        if any(RecordKey.parse(document_id(self.mode, row)).account_key != account_key for row in rows):
            self.error('Hồ sơ chưa có bằng chứng thuộc tài khoản hiện tại. Tra cứu lại kỳ tương ứng trước khi tải.')
            return
        if self.mode == 'tax' and not self.dvc and any(row.get('nguon') == 'DVC' for row in rows):
            self.error('Nguồn DVC đang tắt. Bật DVC trong Cài đặt trước khi tải các hồ sơ này.')
            return
        if not self.controller.sessions.account.password:
            self.open_login(after=lambda: self.download_rows(rows))
            return
        config = replace(self.make_config(self.mode), output=self.result.output,
                         from_date=self.from_date.date().toString('dd/MM/yyyy'),
                         to_date=self.to_date.date().toString('dd/MM/yyyy'),
                         case_id='', action='download_selected',
                         target_ids=tuple(dict.fromkeys(document_id(self.mode, row) for row in rows)),
                         input_rows=[dict(row) for row in rows])
        self.pending_rows = {document_id(self.mode, row): dict(row) for row in self.model.rows}
        self.launch(config, clear=False)

    def verify_files(self):
        if self.controller.busy or not self.result or self.mode == 'offline':
            return
        config = replace(self.make_config(self.mode), output=self.result.output, action='verify',
                         input_rows=[dict(row) for row in self.model.rows])
        self.launch(config, clear=False)

    def export_report(self):
        if self.controller.busy or not self.result or self.mode == 'offline':
            return
        parent = self.result.output if self.result.output.is_dir() else Path(self.output.text())
        suggested = parent / ('Bao_cao_' + self.mode + '_' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.xlsx')
        path, _ = QFileDialog.getSaveFileName(self, 'Xuất danh sách hiện tại; không sao chép tệp hồ sơ', str(suggested), 'Excel (*.xlsx)')
        if not path:
            return
        target = Path(path)
        if target.suffix.lower() != '.xlsx':
            target = target.with_suffix('.xlsx')
        config = replace(self.make_config(self.mode), output=self.result.output, source=self.result.output,
                         from_date=self.result.date_range[0] or self.from_date.date().toString('dd/MM/yyyy'),
                         to_date=self.result.date_range[1] or self.to_date.date().toString('dd/MM/yyyy'),
                         action='export_report', report_path=target, input_rows=[dict(row) for row in self.model.rows])
        self.launch(config, clear=False)

    def table_clicked(self, index):
        if not index.isValid() or COLUMNS[self.mode][index.column()][0] == '_selected':
            return
        key = COLUMNS[self.mode][index.column()][0]
        if key == '_notice_state':
            row = self.selected_row()
            if row:
                self.show_feedback_panel(row)
            return
        self.details()
        if key == '_action':
            row = self.selected_row()
            if not row:
                return
            if self.mode == 'notice':
                if row.get('_file_status') == 'downloaded':
                    self.open_notice_row(row)
                else:
                    self.download_rows([row])
                return
            if row.get('_file_status') == 'downloaded':
                self.open_detail_file()
            elif row:
                self.download_rows([row])

    def open_notices(self, index):
        """Mở bảng phản hồi của dòng đang chọn (CTA chính của cột)."""
        row = self.selected_row()
        if row:
            self.show_feedback_panel(row)

    def open_detail_notices(self):
        """Mở bảng phản hồi từ khung chi tiết."""
        if self.detail_row:
            self.show_feedback_panel(self.detail_row)

    def notice_menu(self, row):
        """Menu tương thích cho các tệp phản hồi đã tải (không tự mở)."""
        notices = row.get('_notices') or []
        menu = QMenu(self)
        if not notices:
            menu.addAction('Chưa có tệp phản hồi trong thư mục đã tải').setEnabled(False)
        for item in notices:
            label = STATE_LABELS.get(item.get('state'), 'Chưa xác định')
            number = item.get('so_thong_bao') or item.get('name') or ''
            action = menu.addAction(f'{label} · {number}', lambda notice=dict(item): self.open_notice(notice))
            action.setToolTip(item.get('ly_do') or item.get('ten_thong_bao') or '')
        if notices:
            menu.addSeparator()
            menu.addAction('Mở thư mục phản hồi', lambda notice=dict(notices[0]): self.open_notice(notice, folder=True))
        return menu

    def open_notice(self, notice, *, folder=False):
        """Mở tệp/thư mục phản hồi bằng ứng dụng mặc định (tương thích)."""
        value = notice.get('path')
        if not value:
            self.error('Chưa có tệp phản hồi trên máy; hãy tải lại.')
            return
        path = Path(value)
        target = path.parent if folder else path
        if not (target.is_dir() if folder else target.is_file()):
            self.error('Tệp phản hồi đã bị xóa hoặc di chuyển; hãy kiểm tra nơi lưu hoặc tải lại.')
            return
        self.open_path(target)

    def open_notice_link(self, url):
        if url.scheme() not in {'notice-file', 'notice-folder'} or not url.path().isdigit():
            return
        notices = (self.detail_row or {}).get('_notices') or []
        index = int(url.path())
        if index < len(notices):
            self.open_notice(notices[index], folder=url.scheme() == 'notice-folder')

    def taxpayer_key(self) -> str:
        return str(self.controller.sessions.account.username or '')

    def show_feedback_panel(self, row: dict) -> None:
        """Hiển thị bảng phản hồi con của **đúng** dòng được chọn."""
        if not row or not hasattr(self, 'feedback_panel'):
            return
        self.feedback_panel.show_for(row, taxpayer_key=self.taxpayer_key())
        self.feedback_panel.show()

    def refresh_feedback_panel(self) -> None:
        """Giữ bảng phản hồi đồng bộ sau khi tải/kiểm tra lại mà không đổi hồ sơ."""
        if not hasattr(self, 'feedback_panel') or not self.feedback_panel.isVisible():
            return
        key = self.feedback_panel.submission_key
        row = next((item for item in self.model.rows
                    if submission_key(item, taxpayer_key=self.taxpayer_key()) == key), None)
        if row is None:
            self.feedback_panel.clear()
        else:
            self.feedback_panel.show_for(row, taxpayer_key=self.taxpayer_key())

    def open_feedback_asset(self, item) -> None:
        """Mở XML Viewer nội bộ cho đúng tệp của một phản hồi."""
        path = Path(item.asset.path_or_handle)
        if not path.is_file():
            self.error('Tệp phản hồi đã bị xóa hoặc di chuyển; hãy kiểm tra nơi lưu hoặc tải lại.')
            return
        from .xml_viewer import XmlViewer
        XmlViewer.show_asset(self, item.asset, source_kind=item.asset.owner_kind, summary=item.feedback)

    def open_feedback_folder(self, item) -> None:
        path = Path(item.asset.path_or_handle)
        if path.is_file():
            self.open_path(path.parent)
        else:
            self.error('Thư mục chứa tệp phản hồi không còn tồn tại; hãy kiểm tra nơi lưu.')

    def open_notice_row(self, row: dict) -> None:
        """Mở XML Viewer cho thông báo thuế độc lập (không dùng selector tờ khai)."""
        from .domain import OWNER_TAX_NOTICE, tax_notice_from_row
        from .feedback_service import find_tax_notice_asset
        from .xml_viewer import XmlViewer
        asset = find_tax_notice_asset(row, taxpayer_key=self.taxpayer_key())
        if not asset or not Path(asset.path_or_handle).is_file():
            self.error('Tệp thông báo chưa có trên máy hoặc đã bị di chuyển; hãy tải lại.')
            return
        summary = tax_notice_from_row(row, taxpayer_key=self.taxpayer_key())
        XmlViewer.show_asset(self, asset, source_kind=OWNER_TAX_NOTICE, summary=summary)

    def save_feedback_asset(self, item) -> None:
        """Sao chép tệp phản hồi sang vị trí người dùng chọn; không sửa tệp gốc."""
        source = Path(item.asset.path_or_handle)
        if not source.is_file():
            self.error('Tệp phản hồi đã bị xóa hoặc di chuyển; không thể lưu.')
            return
        is_xml = item.asset.content_type == 'application/xml'
        suggested = str(Path.home() / (item.asset.original_filename or source.name))
        path, _ = QFileDialog.getSaveFileName(
            self, 'Lưu tệp phản hồi' if not is_xml else 'Lưu XML phản hồi',
            suggested, 'XML (*.xml);;Tất cả (*)' if is_xml else 'Tất cả (*)')
        if not path:
            return
        target = Path(path)
        try:
            if target.resolve() == source.resolve():
                self.error('Chọn vị trí khác để không ghi đè tệp phản hồi gốc.')
                return
            target.write_bytes(source.read_bytes())
        except OSError as error:
            self.error(f'Không lưu được tệp phản hồi: {error}')
            return
        self.status.setText(f'Đã lưu tệp phản hồi: {target.name}')

    def export_detail_bundle(self) -> None:
        if self.detail_row:
            self.export_submission(self.detail_row)

    def export_submission(self, row: dict) -> None:
        """Xuất ZIP tờ khai + chỉ phản hồi của chính lần nộp đang chọn."""
        if self.mode != 'tax' or not row or not row.get('ma_ho_so'):
            self.error('Chức năng Xuất hồ sơ chỉ áp dụng cho tờ khai đã tra cứu.')
            return
        if not self.result:
            self.error('Chưa có kết quả tra cứu để xuất hồ sơ.')
            return
        from .bundle import export_submission_bundle, safe_archive_name
        suggested = Path(self.result.output) / f'HoSo_{safe_archive_name(row.get("ma_ho_so") or "ho-so")}.zip'
        path, _ = QFileDialog.getSaveFileName(self, 'Xuất gói hồ sơ ZIP', str(suggested), 'ZIP (*.zip)')
        if not path:
            return
        target = Path(path)
        if target.suffix.lower() != '.zip':
            target = target.with_suffix('.zip')
        try:
            bundle = export_submission_bundle(row, target, taxpayer_key=self.taxpayer_key())
        except (OSError, ValueError) as error:
            self.error(f'Không xuất được gói hồ sơ: {error}')
            return
        message = f'Đã xuất {len(bundle.included)} tệp vào {target.name}.'
        self.status.setText(message)
        if bundle.missing:
            names = '\n'.join(f"- {item.get('name', '')}: {item.get('reason', '')}"
                              for item in bundle.missing[:8])
            self.error(f'{message}\nThiếu {len(bundle.missing)} tệp:\n{names}')

    def _technical_dialog(self, title: str, fields: list[tuple[str, str]], note: str = '') -> None:
        from .ui import button, fit_dialog
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for label, value in fields:
            line = QLineEdit(str(value or '—'))
            line.setReadOnly(True)
            line.setCursorPosition(0)
            line.setToolTip(str(value or ''))
            row = QHBoxLayout()
            row.addWidget(line, 1)
            row.addWidget(button('Sao chép', lambda _checked=False, text=str(value or ''):
                                 QApplication.clipboard().setText(text), 'Sao chép giá trị này'))
            form.addRow(label, row)
        layout.addLayout(form)
        if note:
            note_label = QLabel(note)
            note_label.setWordWrap(True)
            layout.addWidget(note_label)
        copy_all = button('Sao chép tất cả', lambda: QApplication.clipboard().setText(
            '\n'.join(f'{label}: {value}' for label, value in fields)))
        layout.addWidget(copy_all)
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        controls.rejected.connect(dialog.reject)
        layout.addWidget(controls)
        fit_dialog(dialog, 760, 480)
        dialog.exec()
        dialog.deleteLater()

    def technical_details(self) -> None:
        if not self.detail_row:
            return
        row = self.detail_row
        fields = [
            ('Tên tệp', Path(row.get('_file_path') or '').name),
            ('Đường dẫn đầy đủ', row.get('_file_path') or ''),
            ('Dung lượng', f"{int(row.get('_file_size') or 0):,} byte"),
            ('SHA-256', row.get('_file_hash') or ''),
            ('Nguồn tải', row.get('nguon') or ''),
            ('Thời điểm cập nhật tệp', row.get('_file_updated') or ''),
            ('Trạng thái tải', FILE_LABELS.get(row.get('_file_status'), 'Chưa tải')),
            ('Kiểm tra toàn vẹn', row.get('_integrity_label')
             or INTEGRITY_LABELS.get(INTEGRITY_NOT_CHECKED, 'Chưa kiểm tra')),
        ]
        self._technical_dialog('Thông tin kỹ thuật của hồ sơ', fields,
                               'SHA-256 không phải chữ ký số và không xác nhận hiệu lực pháp lý.')

    def show_feedback_technical(self, item) -> None:
        asset = item.asset
        fields = [
            ('Loại chủ sở hữu', asset.owner_kind),
            ('Khóa hồ sơ', asset.owner_key),
            ('Khóa tệp phản hồi', asset.asset_key),
            ('Tên tệp', asset.original_filename),
            ('Đường dẫn đầy đủ', asset.path_or_handle),
            ('Loại nội dung', asset.content_type or 'Chưa xác định'),
            ('Mã nguồn', asset.source_id or ''),
            ('SHA-256', asset.checksum or ''),
            ('Dung lượng', f'{asset.size:,} byte'),
            ('Tình trạng toàn vẹn', INTEGRITY_LABELS.get(asset.integrity_status, 'Chưa xác định')),
        ]
        self._technical_dialog('Thông tin kỹ thuật của phản hồi', fields,
                               'SHA-256 là đối chiếu nội bộ, không phải chữ ký số hợp lệ.')

    def details(self):
        row = self.selected_row()
        if row is None:
            return
        self.detail_row = row
        labels = {'tax': [('to_khai', 'Tờ khai'), ('ma_ho_so', 'Mã hồ sơ'), ('ky_tinh_thue', 'Kỳ tính thuế'),
                          ('ngay_nop', 'Ngày nộp'), ('trang_thai', 'Trạng thái CQT')],
                  'gnt': [('so_gnt', 'Số giấy nộp tiền'), ('ctu_id', 'Mã chứng từ'), ('ngay_lap', 'Ngày lập'),
                          ('so_tien', 'Số tiền'), ('trang_thai', 'Trạng thái nộp / phê duyệt')],
                  'notice': [('ten_thong_bao', 'Tên thông báo'), ('so_thong_bao', 'Số thông báo'),
                             ('co_quan_gui', 'Cơ quan phát hành'), ('ma_tbao', 'Mã loại thông báo'),
                             ('message_id', 'Mã thông báo'), ('ngay_gui', 'Ngày gửi'), ('trang_thai', 'Trạng thái xem')],
                  'offline': [('form_name', 'Mẫu / Tệp'), ('form_code', 'Mã mẫu'), ('form_version', 'Phiên bản'),
                              ('status', 'Kết quả parse'), ('source_inner_file', 'Nguồn XML'), ('source_zip', 'Nguồn ZIP')]}
        parts = ['<h3>Thông tin nghiệp vụ</h3>']
        for key, label in labels[self.mode]:
            if key == 'trang_thai' and self.mode == 'tax':
                value = self.model._cqt_status(row)
            elif key == 'so_tien':
                value = display_amount(row.get(key), str(row.get('loai_tien', '')))
            else:
                value = str(row.get(key) or '—')
            parts.append(f'<p><span style="color:#67768C">{label}</span><br><b>{html.escape(value)}</b></p>')
        if self.mode != 'offline':
            parts.append('<hr><h3>Tệp trên máy</h3>')
            for label, value in [('Trạng thái tải', FILE_LABELS.get(row.get('_file_status'), 'Chưa tải')),
                                 ('Cập nhật tệp', row.get('_file_updated') or '—'),
                                 ('Chi tiết', row.get('_error_message') or row.get('_file_reason') or '—')]:
                parts.append(f'<p><span style="color:#67768C">{label}</span><br>{html.escape(str(value))}</p>')
            parts.append('<p><span style="color:#67768C">Đường dẫn, dung lượng, SHA-256 và nguồn tải nằm trong Thông tin kỹ thuật.</span></p>')
            if self.mode == 'tax':
                notices = row.get('_notices') or []
                parts.append('<hr><h3>Phản hồi của cơ quan thuế</h3>')
                if problem := row_attachment_problem(row):
                    parts.append(f'<p style="color:#93631B">{html.escape(problem)}</p>')
                if not notices:
                    parts.append('<p><span style="color:#67768C">Chưa có phản hồi trong dữ liệu hiện có; chưa kết luận cổng không có thông báo.</span></p>')
                else:
                    parts.append(f'<p><b>{len(notices)} phản hồi</b> trong dữ liệu hiện có. '
                                 'Bấm <b>Xem phản hồi</b> để mở bảng chi tiết.</p>')
        else:
            parts.append('<p>Chỉ phân tích XML cục bộ; không xác thực chữ ký số hoặc tính đúng của nghĩa vụ thuế.</p>')
        self.detail_text.setHtml(''.join(parts))
        self.detail_open.setText('Xem file' if self.mode == 'tax' else 'Xem tệp')
        self.detail_open.setEnabled(bool(row.get('_file_path') and Path(row['_file_path']).is_file()))
        notices = row.get('_notices') or []
        self.detail_notices.setVisible(self.mode == 'tax')
        self.detail_notices.setEnabled(bool(notices))
        self.detail_notices.setText(f'Xem phản hồi ({len(notices)})' if notices else 'Chưa có phản hồi')
        if hasattr(self, 'detail_bundle'):
            self.detail_bundle.setVisible(self.mode == 'tax')
            self.detail_bundle.setEnabled(self.mode == 'tax' and bool(row.get('ma_ho_so')))
        self.sync_actions()
        self.position_drawer()
        self.drawer.show()
        self.drawer.raise_()

    def position_drawer(self):
        if not hasattr(self, 'drawer'):
            return
        parent = self.centralWidget()
        top = self.results_panel.mapTo(parent, QPoint(0, 0)).y()
        width = min(440, max(280, parent.width() // 2))
        self.drawer.setGeometry(max(0, parent.width() - width - 6), top, width, max(80, self.results_panel.height()))

    def close_drawer(self):
        if hasattr(self, 'drawer'):
            self.drawer.hide()
            self.detail_row = None

    def copy_document_id(self):
        if self.detail_row:
            QApplication.clipboard().setText(remote_document_id(self.mode, self.detail_row))

    def open_detail_file(self):
        if not self.detail_row:
            return
        if self.mode == 'notice':
            self.open_notice_row(self.detail_row)
            return
        target = self.detail_row.get('_file_path')
        if target and Path(target).is_file():
            if self.mode == 'tax' and Path(target).suffix.lower() == '.zip':
                self.open_declaration_file()
            else:
                self.open_path(Path(target))
        else:
            self.detail_row.update(_file_status='not_downloaded', _file_path='', _file_reason='Tệp đã bị xóa hoặc di chuyển; kiểm tra lại tệp trên máy')
            self.model.layoutChanged.emit()
            self.populate_result(self.result)
            self.details()

    def open_declaration_file(self) -> None:
        """Mở XML chính của tờ khai đã tải bằng ứng dụng mặc định (giữ nguyên ZIP)."""
        from gdt_tax.declaration_view import DeclarationViewError, declaration_xml
        source = Path(str((self.detail_row or {}).get('_file_path') or ''))
        try:
            xml = declaration_xml(source)
        except DeclarationViewError as error:
            self.error(str(error))
            if source.parent.is_dir():
                self.open_path(source.parent)
            return
        except OSError:
            self.error('Không đọc được tệp đã tải; kiểm tra quyền hoặc tải lại hồ sơ.')
            return
        self.open_path(xml)

    def download_detail(self):
        if self.detail_row:
            self.download_rows([self.detail_row])

    def raw_details(self):
        if not self.detail_row:
            return
        from .ui import fit_dialog
        dialog = QDialog(self)
        dialog.setWindowTitle('Metadata gốc và thông tin tệp')
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit(json.dumps(self.detail_row, ensure_ascii=False, indent=2))
        text.setReadOnly(True)
        layout.addWidget(text)
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        controls.rejected.connect(dialog.reject)
        layout.addWidget(controls)
        fit_dialog(dialog, 700, 500)
        dialog.exec()

    def context_menu(self, position):
        index = self.table.indexAt(position)
        if not index.isValid():
            return
        self.table.setCurrentIndex(index)
        row = self.selected_row()
        menu = QMenu(self)
        menu.addAction('Xem chi tiết', self.details)
        if self.mode == 'tax' and row.get('_notices'):
            menu.addAction('Xem phản hồi…', lambda: (self.table.setCurrentIndex(index), self.open_notices(index)))
        if self.mode == 'tax' and row.get('ma_ho_so'):
            menu.addAction('Xuất hồ sơ ZIP…', lambda: self.export_submission(row))
        if self.mode != 'offline':
            if row.get('_file_status') == 'downloaded':
                menu.addAction('Xem file' if self.mode == 'tax' else 'Mở tệp', lambda: (self.details(), self.open_detail_file()))
            else:
                action = menu.addAction('Tải riêng tệp này', lambda: self.download_rows([row]))
                action.setEnabled(self.can_target_download() and not self.controller.busy)
            menu.addAction('Sao chép mã đầy đủ', lambda: QApplication.clipboard().setText(document_id(self.mode, row)))
        menu.addAction('Mở thư mục', self.open_output)
        menu.addAction('Sao chép metadata', lambda: QApplication.clipboard().setText(json.dumps(row, ensure_ascii=False)))
        menu.exec(self.table.viewport().mapToGlobal(position))

    def populate_result(self, result):
        self.files.clear()
        self.outputs_menu.clear()
        rows = self.model.rows
        self.counts.setToolTip(('Kết quả theo khoảng ngày ' + ' – '.join(result.date_range) + '\n' if result and all(result.date_range) else '')
                              + 'Chỉ số theo toàn bộ danh sách của tài khoản/tab/khoảng ngày đã tra cứu; không thay đổi theo bộ lọc bảng.')
        if self.mode == 'offline':
            mapped = sum(r.get('status') == 'MAPPED' for r in rows)
            self.counts.setText(f"Bản ghi {len(rows) or (result.discovered if result else 0)}    Đã mapping {mapped}    Cần kiểm tra {result.skipped if result else 0}    Lỗi {result.errors if result else 0}")
        else:
            count = counters(rows)
            total = max(result.inventory_total, count['found']) if result else count['found']
            self.counts.setText(f"Kho: {total}  |  Kỳ đang xem: {count['found']}  |  Đã tải: {count['downloaded']}  |  Thiếu: {count['pending']}  |  Lỗi: {count['failed']}")
            if result:
                self.counts.setToolTip(f'Kho tích lũy của tài khoản/tab; không giảm khi đổi kỳ. Cần xác minh định danh: {result.quarantined}')
        if result:
            for path in result.files:
                self.files.addItem(path.name, str(path))
                self.outputs_menu.addAction(path.name, lambda target=path: self.open_path(target))
        self.outputs_menu.setEnabled(bool(result and result.files))
        self.report_button.setEnabled(bool(result and any(p.is_file() for p in result.files)))
        self.sync_actions()

    def on_state(self, state):
        labels = {'IDLE': 'Sẵn sàng', 'VALIDATING': 'Kiểm tra điều kiện…', 'RUNNING': 'Đang xử lý…',
                  'WAITING_CAPTCHA': 'Chờ nhập CAPTCHA…', 'STOPPING': 'Đang dừng an toàn…'}
        self.status.setText(labels.get(state, state))
        busy = self.controller.busy
        for widget in [self.tabs, self.navigation, self.settings_button, self.query, self.start_button]:
            widget.setEnabled(not busy)
        self.batch_action.setEnabled(not busy)
        self.stop_button.setEnabled(busy and state != 'STOPPING')
        self.progress.setRange(0, 0 if busy else 1)
        if state == 'STOPPING' and self.captcha_dialog:
            self.captcha_dialog.reject()
        self.sync_actions()
        self.update_empty()

    def on_progress(self, payload):
        from .ui import MODES, TITLES
        if 'captcha_message' in payload:
            self.status.setText(payload['captcha_message'])
        if 'session' in payload:
            self.refresh_account()
            if payload['session'] == 'AUTHENTICATING':
                self.status.setText('Đang đăng nhập eTax…')
        if 'stage' in payload:
            self.status.setText({'export': 'Đang xuất Excel…',
                                 'finalize': 'Đang kiểm tra tệp và hoàn tất danh mục…'}.get(
                                     payload['stage'], 'Đang phân tích XML cục bộ…'))
        if 'active_mode' in payload:
            self.status.setText('Đang xử lý: ' + TITLES[MODES.index(payload['active_mode'])])
        if ('record' in payload and self.active_config
                and self.active_config.mode in {'tax', 'gnt', 'notice', 'batch'}
                and not self.catalog_refresh_timer.isActive()):
            # Read committed rows on a bounded UI timer, including reused records
            # and the final partial batch. A record-count modulus misses both.
            self.catalog_refresh_timer.start()
        if 'record' in payload and self.active_config and self.active_config.mode != 'batch':
            row = dict(payload['record'])
            key = document_id(self.mode, row)
            old = self.pending_rows.get(key, {})
            state = payload.get('file_state', '')
            file_status = 'downloaded' if state in {'Đã tải', 'Đã có hợp lệ'} else 'failed' if state == 'Lỗi tải' else 'not_downloaded'
            if self.active_config.target_ids is not None and key not in self.active_config.target_ids:
                file_status = old.get('_file_status', 'not_downloaded')
            row.update(_file_status=file_status, _file_state=FILE_LABELS[file_status])
            self.pending_rows[key] = {**old, **row}
            done = payload.get('downloaded', 0)
            discovered = payload.get('discovered', 0)
            self.status.setText(f'Đang tra cứu · Đã tìm thấy {discovered} hồ sơ' if self.active_config.dry_run else
                                f'Đang xử lý · Đã tìm thấy {discovered} | Tệp hoàn tất: {done} | Lỗi: {payload.get("errors", 0)}')
            if self.active_config.target_ids:
                self.progress.setRange(0, len(self.active_config.target_ids))
                self.progress.setValue(done)
            self.populate_result(self.result)
            self.update_empty()
            self.refresh_feedback_panel()

    def on_completed(self, result):
        self.catalog_refresh_timer.stop()
        config, self.active_config = self.active_config, None
        self.last_task = result
        task_result = result
        self.refresh_account()
        if config and config.mode == 'login':
            self.save_login(config, result.state == 'SUCCESS')
            self.status.setText(result.message)
            after, self.after_login = self.after_login, None
            if result.state == 'SUCCESS':
                # LOCAL FIRST: danh mục trên máy hiện ra ngay, không cần bấm Tra cứu.
                self.load_local_library(after=after)
            elif result.state == 'ERROR':
                self.error(result.message)
        elif config and config.mode == 'library':
            for mode, child in result.children.items():
                state = self.tab_states[mode]
                state.result, state.rows, state.message = child, child.rows, child.message
            current = self.tab_states[self.mode]
            self.result = current.result
            self.model.reset(self.mode, current.rows)
            self.refresh_feedback_panel()
            self.populate_result(current.result)
            self.status.setText(result.message)
            self.status.setStyleSheet('color:#67768C;')
            self.status.setToolTip(result.message)
            self.apply_local_date_filter()
            after, self.local_after = self.local_after, None
            if after:
                QTimer.singleShot(0, after)
        else:
            previous = self.result
            if config and config.action in {'verify', 'export_report'} and previous:
                files = list(dict.fromkeys(result.files + previous.files))
                result = replace(previous, rows=result.rows or previous.rows, files=files)
            if result.children:
                for mode, child in result.children.items():
                    state = self.tab_states[mode]
                    state.result, state.rows, state.message = child, child.rows, child.message
                selected = self.tab_states[self.mode].result
            else:
                selected = result
            refresh_catalog = bool(config and config.mode in {'tax', 'gnt', 'notice', 'batch', 'import'})
            refresh_problem = ''
            if refresh_catalog:
                # Never replace the visible period with raw rows from a job
                # that may have finished after the user changed dates.
                projection = self.apply_local_date_filter(completed=selected)
                if projection is None or projection.state in {'ERROR', 'PARTIAL'}:
                    refresh_problem = self.status.toolTip() if projection is None else projection.message
                    result = replace(result, state='PARTIAL' if result.state == 'SUCCESS' else result.state,
                                     message=result.message + '; Không cập nhật đầy đủ kho trên máy: ' + refresh_problem,
                                     errors=max(1, result.errors),
                                     issues=result.issues + [{'document_id': '', 'message': refresh_problem}])
                    task_result = self.last_task = result
                selected = self.result
            else:
                self.result = selected
                self.model.reset(self.mode, selected.rows if selected else [])
            self.refresh_feedback_panel()
            if config and config.action not in {'verify', 'export_report'} and config.mode not in {'saved', 'import', 'library'}:
                self.history.insert(0, {'mode': config.mode, 'result': result, 'action': result.operation})
                self.history = self.history[:100]
            status_result = task_result if config and config.action in {'verify', 'export_report'} else result
            short = {'PARTIAL': 'Hoàn tất một phần · Xem chi tiết', 'CANCELLED': 'Đã dừng · Giữ tệp hoàn tất',
                     'ERROR': f'Có {max(1, status_result.errors)} lỗi · Xem chi tiết', 'LOADED': 'Đã mở dữ liệu lưu'}.get(status_result.state,
                     'Tra cứu hoàn tất' if config and config.dry_run else 'Đã hoàn tất')
            if config and config.action == 'verify' and status_result.state == 'SUCCESS':
                short = 'Đã kiểm tra tệp trên máy'
            elif config and config.action == 'export_report' and status_result.state == 'SUCCESS':
                short = 'Đã xuất danh sách Excel'
            elif status_result.state == 'SUCCESS' and status_result.discovered == 0:
                short = ('Online không trả hồ sơ; đang xem hồ sơ đã lưu' if refresh_catalog and self.model.rowCount()
                         else 'Không tìm thấy hồ sơ trong kỳ này')
            self.populate_result(selected)
            if refresh_catalog:
                if config.mode == 'import':
                    short += f" · Nhập từ máy: {task_result.discovered} | Cần kiểm tra: {task_result.skipped} | Lỗi: {task_result.errors}"
                elif config.action not in {'verify', 'export_report'}:
                    metrics = task_result.sync_metrics
                    short += f" · Online: {task_result.discovered} | Mới: {metrics.get('new', 0)} | Dùng lại: {task_result.reused} | Lỗi: {task_result.errors}"
                    requested = (config.from_date, config.to_date)
                    visible = (self.from_date.date().toString('dd/MM/yyyy'), self.to_date.date().toString('dd/MM/yyyy'))
                    short += ' · Tra cứu: ' + ' – '.join(requested)
                    if requested != visible:
                        short += ' · Đang xem: ' + ' – '.join(visible)
                    if self.proxy_model.rowCount() < self.model.rowCount():
                        short += f' · Đang lọc: {self.proxy_model.rowCount()}/{self.model.rowCount()}'
                if refresh_problem:
                    short += ' · Không cập nhật đầy đủ kho trên máy'
            self.status.setText("<a href='issues'>" + html.escape(short) + '</a>' if status_result.state in {'ERROR', 'PARTIAL'} else short)
            self.status.setStyleSheet('color:' + {'SUCCESS': '#15805B', 'PARTIAL': '#93631B', 'ERROR': '#C94242'}.get(status_result.state, '#67768C') + ';')
            self.status.setToolTip(status_result.message + '\n' + short)
            self.collapse_conditions(False)
            self.save_tab()
            self.update_empty()
        if self.captcha_dialog:
            self.captcha_dialog.reject()
        self.progress.setRange(0, 1)
        self.progress.setValue(1 if result.state in {'SUCCESS', 'PARTIAL', 'LOADED'} else 0)
        if self.close_pending:
            self.close()
        elif self.deferred_account_action:
            action, self.deferred_account_action = self.deferred_account_action, None
            QTimer.singleShot(0, action)

    def show_issues(self, result=None):
        from .ui import button, fit_dialog
        result = result or self.last_task or self.result
        if not result:
            self.show_logs()
            return
        dialog = QDialog(self)
        dialog.setWindowTitle('Tổng kết tác vụ và chi tiết lỗi')
        layout = QVBoxLayout(dialog)
        body = QTextBrowser()
        parts = [f'<h3>Tác vụ {html.escape(result.task_id or "hiện tại")}</h3>', f'<p>{html.escape(result.message)}</p>',
                 f'<p>Phát hiện {result.discovered} · Yêu cầu tải {result.requested} · Tệp hoàn tất trong tác vụ {result.downloaded} · Đã có hợp lệ {result.reused} · Lỗi {result.errors}</p>',
                 f'<p>Đoạn/nguồn chưa xử lý: {result.skipped}. Tệp đã có hợp lệ được giữ; không gộp bỏ qua nguồn thành tệp tải thành công.</p>',
                 f'<p>Nơi lưu: {html.escape(str(result.output))}</p>']
        for issue in result.issues:
            message = issue.get('message', '')
            parts.append(f'<p><b>{html.escape(document_label(issue.get("document_id") or ""))}</b><br>'
                         f'{html.escape(message)}<br><span style="color:#93631B">'
                         f'{html.escape(issue_hint(message))}</span></p>')
        attachments = getattr(result, 'attachment_results', {})
        if attachments:
            totals = attachment_totals(attachments)
            parts.append('<h4>Thông báo cơ quan thuế đính kèm</h4>'
                         f'<p>Phát hiện {totals["discovered"]} · Tải mới {totals["downloaded"]}'
                         f' · Có sẵn {totals["reused"]} · Lỗi tải {totals["failed"]}'
                         f' · Chưa đọc được danh sách {totals["discovery_failed"]} hồ sơ</p>')
        body.setHtml(''.join(parts))
        layout.addWidget(body)
        actions = QHBoxLayout()
        open_folder = button('Mở thư mục', lambda: self.open_path(result.output))
        open_folder.setEnabled(result.output.is_dir())
        actions.addWidget(open_folder)
        actions.addWidget(button('Nhật ký kỹ thuật', self.show_logs))
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(dialog.reject)
        actions.addWidget(close)
        layout.addLayout(actions)
        fit_dialog(dialog, 700, 450)
        dialog.exec()

    def show_history(self):
        from .ui import MODES, TITLES, button, fit_dialog
        account_key = hashlib.sha256(self.controller.sessions.account.username.encode()).hexdigest()
        entries = [entry for entry in self.history if entry['result'].account_key == account_key]
        dialog = QDialog(self)
        dialog.setWindowTitle('Lịch sử tải trong phiên làm việc — tài khoản hiện tại')
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel('100 tác vụ gần nhất trong phiên. Chọn một dòng để xem lỗi '
                                'hoặc thử lại mục lỗi cùng tab.'))
        table = QTableWidget(len(entries), 8)
        table.setHorizontalHeaderLabels(['Thời gian', 'Nhóm', 'Kỳ', 'Tìm thấy',
                                         'Tệp hoàn tất', 'Có sẵn', 'Lỗi', 'Kết quả'])
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for index, entry in enumerate(entries):
            result = entry['result']
            values = [result.ended_at[:19].replace('T', ' ') + ' UTC',
                      TITLES[MODES.index(entry['mode'])] if entry['mode'] in MODES else 'Nhiều nhóm',
                      ' – '.join(result.date_range), str(result.discovered), str(result.downloaded),
                      str(result.reused), str(result.errors), result.state]
            for column, value in enumerate(values):
                table.setItem(index, column, QTableWidgetItem(value))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table, 1)

        def failed_rows(result):
            return [row for row in result.rows if row.get('_file_status') == 'failed']

        def can_retry() -> bool:
            if table.currentRow() < 0:
                return False
            entry = entries[table.currentRow()]
            return (entry['mode'] == self.mode and bool(failed_rows(entry['result']))
                    and entry['result'].account_key == account_key)

        actions = QHBoxLayout()
        actions.addWidget(button('Xem tổng kết / lỗi',
                                 lambda: self.show_issues(entries[table.currentRow()]['result'])
                                 if table.currentRow() >= 0 else None))

        def retry_selected() -> None:
            if table.currentRow() < 0:
                return
            result = entries[table.currentRow()]['result']
            dialog.accept()
            QTimer.singleShot(0, lambda: self.retry_history_errors(result))

        retry = button('Thử lại mục lỗi', retry_selected,
                       'Chỉ thử lại các tệp lỗi của tác vụ đang chọn trong tab hiện tại')
        retry.setEnabled(False)
        actions.addWidget(retry)
        open_folder = button('Mở thư mục',
                             lambda: self.open_path(entries[table.currentRow()]['result'].output)
                             if table.currentRow() >= 0 else None)
        open_folder.setEnabled(False)
        actions.addWidget(open_folder)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(dialog.reject)
        actions.addWidget(close)

        def update_actions(*_args):
            selected = table.currentRow() >= 0
            open_folder.setEnabled(selected and entries[table.currentRow()]['result'].output.is_dir())
            retry.setEnabled(selected and can_retry())

        table.currentCellChanged.connect(update_actions)
        layout.addLayout(actions)
        fit_dialog(dialog, 1040, 520)
        dialog.exec()

    def retry_history_errors(self, result) -> None:
        """Thử lại các dòng lỗi của một tác vụ lịch sử trong tab hiện tại."""
        if not result:
            return
        failed = [row for row in result.rows if row.get('_file_status') == 'failed']
        if not failed:
            self.error('Tác vụ đã chọn không có tệp lỗi để thử lại.')
            return
        account_key = hashlib.sha256(self.controller.sessions.account.username.encode()).hexdigest()
        if result.account_key != account_key:
            self.error('Tác vụ thuộc tài khoản khác; đăng nhập đúng tài khoản rồi thử lại.')
            return
        self.result = result
        self.model.reset(self.mode, result.rows)
        self.download_rows(failed)

    def filtered_rows(self) -> list[dict]:
        """Các dòng đang hiển thị sau tìm kiếm/bộ lọc, theo đúng khóa nguồn."""
        rows: list[dict] = []
        for proxy_row in range(self.proxy_model.rowCount()):
            source = self.proxy_model.source_row(self.proxy_model.index(proxy_row, 0))
            if source is not None and source < len(self.model.rows):
                rows.append(self.model.rows[source])
        return rows

    def reconciliation_scope(self) -> str:
        parts = []
        if self.result and all(self.result.date_range):
            label = {'tax': 'Ngày nộp', 'gnt': 'Ngày lập', 'notice': 'Ngày gửi'}.get(self.mode, 'Khoảng tra cứu')
            parts.append(f'{label} {self.result.date_range[0]} – {self.result.date_range[1]}')
        if self.search.text().strip():
            parts.append(f'Tìm kiếm "{self.search.text().strip()}"')
        if self.file_filter.currentData() != 'all':
            parts.append(f'Lọc tải: {self.file_filter.currentText()}')
        if self.mode == 'tax' and self.cqt_filter.currentData() != 'all':
            parts.append(f'Lọc CQT: {self.cqt_filter.currentText()}')
        if self.mode == 'notice' and self.type_filter.currentData():
            parts.append(f'Loại thông báo: {self.type_filter.currentData()}')
        base = 'Kết quả tra cứu hiện tại của tài khoản/tab'
        if parts:
            base += '; ' + '; '.join(parts)
        return base + '. Chỉ phản ánh dữ liệu đã tải/đọc được, không xác nhận đầy đủ nghĩa vụ thuế.'

    def show_reconciliation(self) -> None:
        from PySide6.QtGui import QBrush, QColor

        from .reconciliation import (
            reconciliation_rows,
            write_reconciliation_csv,
            write_reconciliation_xlsx,
        )
        from .ui import button, fit_dialog
        rows = self.filtered_rows()
        if not rows:
            self.error('Không có dòng nào trong bộ lọc hiện tại để đối soát.')
            return
        scope = self.reconciliation_scope()
        records = reconciliation_rows(rows, taxpayer_key=self.taxpayer_key(), scope_note=scope)
        dialog = QDialog(self)
        dialog.setWindowTitle('Đối soát hồ sơ và phản hồi')
        layout = QVBoxLayout(dialog)
        note = QLabel(scope)
        note.setWordWrap(True)
        note.setObjectName('hint')
        layout.addWidget(note)
        preview = records[:500]
        if len(records) > len(preview):
            note.setText(scope + f' Đang hiển thị {len(preview)}/{len(records)} dòng; '
                                 f'xuất báo cáo sẽ gồm đủ {len(records)} dòng.')
        table = QTableWidget(len(preview), 8)
        table.setHorizontalHeaderLabels(['Mã hồ sơ', 'Loại tờ khai', 'Kỳ', 'Ngày nộp',
                                         'Trạng thái CQT', 'Số phản hồi', 'Kết quả phản hồi',
                                         'Trạng thái tải'])
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for index, record in enumerate(preview):
            values = [record['ma_ho_so'], record['to_khai'], record['ky_tinh_thue'], record['ngay_nop'],
                      record['cqt_status'], record['feedback_count'], record['feedback_result'],
                      record['file_status']]
            rejected = (str(record['feedback_result']).startswith('✕')
                        or record['cqt_status'] == 'Không chấp nhận')
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if rejected:
                    item.setForeground(QBrush(QColor('#C94242')))
                    item.setBackground(QBrush(QColor('#FDECEA')))
                elif str(record['feedback_result']).startswith('✓'):
                    item.setForeground(QBrush(QColor('#15805B')))
                table.setItem(index, column, item)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table, 1)

        def suggest(name: str) -> str:
            base = self.result.output if self.result else Path(self.output.text())
            return str(Path(base) / name)

        def save_csv() -> None:
            path, _ = QFileDialog.getSaveFileName(self, 'Xuất đối soát CSV',
                                                  suggest('Doi_soat.csv'), 'CSV (*.csv)')
            if not path:
                return
            target = Path(path)
            if target.suffix.lower() != '.csv':
                target = target.with_suffix('.csv')
            try:
                write_reconciliation_csv(target, records)
            except (OSError, ValueError) as error:
                self.error(f'Không xuất được CSV: {error}')
                return
            self.status.setText(f'Đã xuất đối soát CSV: {target.name}')

        def save_xlsx() -> None:
            path, _ = QFileDialog.getSaveFileName(self, 'Xuất đối soát Excel',
                                                  suggest('Doi_soat.xlsx'), 'Excel (*.xlsx)')
            if not path:
                return
            target = Path(path)
            if target.suffix.lower() != '.xlsx':
                target = target.with_suffix('.xlsx')
            try:
                write_reconciliation_xlsx(target, records, scope)
            except (OSError, ValueError) as error:
                self.error(f'Không xuất được Excel: {error}')
                return
            self.status.setText(f'Đã xuất đối soát Excel: {target.name}')

        actions = QHBoxLayout()
        actions.addWidget(button('Xuất CSV', save_csv))
        actions.addWidget(button('Xuất Excel', save_xlsx))
        actions.addStretch()
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(dialog.reject)
        actions.addWidget(close)
        layout.addLayout(actions)
        fit_dialog(dialog, 1100, 560)
        dialog.exec()

    def update_empty(self, *_args):
        if not hasattr(self, 'empty'):
            return
        self.empty.setVisible(self.proxy_model.rowCount() == 0)
        if self.proxy_model.rowCount():
            return
        if self.model.rowCount():
            message = 'Không có hồ sơ khớp tìm kiếm/bộ lọc.\nNhấn Xóa bộ lọc để xem lại toàn bộ danh sách.'
        elif self.controller.busy:
            message = 'Đang xử lý… Bạn có thể dừng an toàn; tệp hoàn tất được giữ.'
        elif self.result and self.result.state == 'ERROR':
            message = 'Không thể hoàn tất tác vụ. Nhấn Xem chi tiết ở thanh dưới để biết nguyên nhân và cách xử lý.'
        elif self.result and self.result.state in {'CANCELLED', 'PARTIAL'}:
            message = 'Tra cứu chưa đầy đủ nên chưa thể kết luận không có hồ sơ.\nChạy lại tra cứu hoặc xem tổng kết trong Lịch sử tải.'
        elif self.result and self.result.operation == 'library':
            message = ('Chưa có hồ sơ đã lưu trong khoảng ngày này.\nBạn có thể bấm Tra cứu để lấy dữ liệu từ cơ quan thuế.'
                       if not self.model.rowCount() else
                       'Không có hồ sơ đã lưu trong khoảng ngày đang chọn.\nĐổi ngày hoặc xóa bộ lọc để xem lại.')
        elif self.result:
            message = 'Không tìm thấy hồ sơ trong kỳ đã tra cứu.'
        elif self.mode == 'offline':
            message = 'Chọn hoặc kéo thả tệp/thư mục XML, ZIP rồi nhấn Chạy phân tích.\nChỉ đọc cục bộ, không cần đăng nhập.'
        else:
            message = 'Chọn kỳ rồi nhấn Tra cứu.\nTrạng thái cơ quan thuế và trạng thái tệp được hiển thị riêng.'
        self.empty.setText(message)

    def responsive(self):
        if not hasattr(self, 'table'):
            return
        width, height = self.width(), self.height()
        self.ultra = width < 850 or height < 560
        self.layout_root.setContentsMargins(8 if self.ultra else 12, 4 if self.ultra else 8, 8 if self.ultra else 12, 4 if self.ultra else 8)
        self.layout_root.setSpacing(4 if self.ultra else 7)
        self.navigation.setVisible(width < 600)
        self.tabs.setVisible(width >= 600)
        self.title.setText('Hồ Sơ Thuế' if width < 850 else 'Tải Hồ Sơ Thuế')
        self.account_label.setMinimumWidth(55)
        self.account_label.setMaximumWidth(90 if width < 1000 else 220)
        self.account_label.setSizePolicy(self.account_label.sizePolicy().horizontalPolicy(), self.account_label.sizePolicy().verticalPolicy())
        self.source_badge.setVisible(self.mode != 'offline' and width >= 1100)
        self.config_layout.setDirection(QHBoxLayout.Direction.TopToBottom if width < 1500 else QHBoxLayout.Direction.LeftToRight)
        self.result_tools.setDirection(QHBoxLayout.Direction.TopToBottom if width < 850 else QHBoxLayout.Direction.LeftToRight)
        self.output_label.setText('Nơi xuất' if self.mode == 'offline' else 'Nơi lưu')
        self.start_button.setText('Chạy phân tích' if self.mode == 'offline' else 'Tra cứu và tải')
        self.xml_notice.setVisible(self.mode == 'offline' and height >= 430)
        self.counts.setVisible(not (height < 400 and not self.model.rows))
        columns = COLUMNS[self.mode]
        hidden = {'source_zip'} if self.mode == 'offline' and width < 1100 else set()
        if self.mode == 'notice' and width < 1100:
            hidden.add('co_quan_gui')
        if width < 900:
            hidden.update({'ky_tinh_thue', 'so_tien', 'form_version'})
        row_height = 28 if height < 400 else 35 if self.ultra else 43
        self.table.verticalHeader().setDefaultSectionSize(row_height)
        self._applying_widths = True
        try:
            for index, (key, _) in enumerate(columns):
                self.table.setColumnHidden(index, key in hidden)
                self.table.horizontalHeader().setSectionResizeMode(index, QHeaderView.ResizeMode.Interactive)
                target = {'_selected': 34, '_action': 75, '_file_status': 83, '_notice_state': 130, 'ngay_nop': 128,
                          'ngay_lap': 128, 'ngay_gui': 128, 'trang_thai': 150,
                          'ten_thong_bao': 220, 'so_thong_bao': 150, 'co_quan_gui': 180,
                          'ky_tinh_thue': 95, 'so_tien': 120, 'form_code': 90,
                          'form_version': 80, 'status': 120}.get(key, 160)
                if width < 850:
                    target = {'_selected': 30, '_action': 65, '_file_status': 76, 'ngay_nop': 108,
                              'ngay_lap': 108, 'ngay_gui': 108, 'trang_thai': 112}.get(key, target)
                self.table.setColumnWidth(index, target)
            state = self.tab_states.get(self.mode)
            if state and state.column_widths:
                for index, (key, _) in enumerate(columns):
                    if key in state.column_widths and not self.table.isColumnHidden(index):
                        self.table.setColumnWidth(index, state.column_widths[key])
            self.table.horizontalHeader().setSectionResizeMode(0 if self.mode == 'offline' else 1, QHeaderView.ResizeMode.Stretch)
        finally:
            self._applying_widths = False
        self.position_drawer()
        self.refresh_account()

    def change_account_type(self, *_args):
        """Đổi DN ↔ CN: cô lập phiên/kho, không trộn hồ sơ giữa hai loại."""
        if getattr(self, '_changing_account_type', False):
            return
        selected = self.account_type.currentData() or 'DN'
        current = self.controller.sessions.account_type
        if selected == current:
            return
        if self.controller.busy:
            self._changing_account_type = True
            self.account_type.setCurrentIndex(max(0, self.account_type.findData(current)))
            self._changing_account_type = False
            self.error('Dừng tác vụ hiện tại trước khi đổi loại tài khoản.')
            return
        self.save_tab()
        self.controller.sessions.set_account_type(selected)
        self.preferences.account_type = selected
        try:
            self.store.save(self.preferences)
        except (OSError, ValueError, TypeError):
            pass
        self.clear_account_views()
        self.refresh_account()
        self.warning_update()
        self.status.setText('Đã chuyển sang tài khoản '
                            + ('cá nhân' if selected == 'CN' else 'doanh nghiệp')
                            + '. Hãy đăng nhập để tiếp tục.')

    def account_context_menu(self, point):
        menu = QMenu(self)
        action = menu.addAction('Sao chép MST / tài khoản đầy đủ',
                                lambda: QApplication.clipboard().setText(self.controller.sessions.account.username))
        action.setEnabled(bool(self.controller.sessions.account.username))
        menu.exec(self.account_label.mapToGlobal(point))

    def choose_xml_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, 'Chọn tệp XML hoặc ZIP cục bộ', self.input_path.text(), 'Hồ sơ XML/ZIP (*.xml *.zip)')
        if paths:
            self.set_source_files(paths)

    def clear_source_selection(self, *_args):
        self.source_files = ()
        self.source_info.clear()

    def set_source_files(self, paths):
        if self.controller.busy:
            return
        sources = [Path(path).resolve() for path in paths]
        if any(not path.is_file() or path.suffix.lower() not in {'.xml', '.zip'} for path in sources):
            self.error('Chọn tệp XML hoặc ZIP tồn tại trên máy.')
            return
        try:
            root = Path(os.path.commonpath([str(path.parent) for path in sources]))
        except ValueError:
            self.error('Chọn các tệp trong cùng ổ đĩa hoặc chọn từng thư mục nguồn.')
            return
        self.source_files = tuple(str(path) for path in sources)
        self.input_path.setText(str(root))
        self.source_info.setText(f'{len(sources)} tệp')
        self.source_info.setToolTip('\n'.join(str(path) for path in sources))
        self.stage.setCurrentIndex(0)

    def dragEnterEvent(self, event):
        if not self.controller.busy and event.mimeData().hasUrls() and all(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        if self.controller.busy:
            return
        sources = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        self.tabs.setCurrentIndex(3)
        if len(sources) == 1 and sources[0].is_dir():
            self.source_files = ()
            self.input_path.setText(str(sources[0]))
            self.source_info.clear()
            self.stage.setCurrentIndex(0)
        elif sources:
            self.set_source_files(sources)
        event.acceptProposedAction()
