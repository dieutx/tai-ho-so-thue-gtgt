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
    QHBoxLayout,
    QHeaderView,
    QLabel,
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
from .state import TabState
from .table_model import COLUMNS


class V2InteractionMixin:
    def dates_changed(self, *_args):
        if not self.applying_preset:
            self.preset.blockSignals(True)
            self.preset.setCurrentIndex(self.preset.findData('custom'))
            self.preset.blockSignals(False)
        self.warning_update()
        if self.result and all(self.result.date_range) and self.result.date_range != (
                self.from_date.date().toString('dd/MM/yyyy'), self.to_date.date().toString('dd/MM/yyyy')):
            self.status.setText('Điều kiện đã đổi; danh sách vẫn thuộc kỳ đã tra cứu trước đó')

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

    def collapse_conditions(self, collapsed=True):
        self.conditions_collapsed = bool(collapsed and self.mode != 'offline')
        self.config_panel.setVisible(not self.conditions_collapsed)
        self.condition_summary.setVisible(self.conditions_collapsed)
        dates = self.result.date_range if self.result and all(self.result.date_range) else (
            self.from_date.date().toString('dd/MM/yyyy'), self.to_date.date().toString('dd/MM/yyyy'))
        path = self.result.output if self.result else Path(self.output.text())
        self.summary_text.setText(f'Kỳ {dates[0]} – {dates[1]}  ·  Nơi lưu: {path.name}')
        self.summary_text.setToolTip(f'Kết quả kỳ {dates[0]} – {dates[1]}\n{path}')
        self.responsive()

    def save_tab(self):
        if not hasattr(self, 'model'):
            return
        state = self.tab_states[self.current_mode]
        state.rows, state.result = list(self.model.rows), self.result
        state.filter_text = self.search.text()
        state.status_filter = self.file_filter.currentData()
        state.scroll = self.table.verticalScrollBar().value()
        state.horizontal_scroll = self.table.horizontalScrollBar().value()
        state.sort_column = self.table.horizontalHeader().sortIndicatorSection()
        state.sort_descending = self.table.horizontalHeader().sortIndicatorOrder() == Qt.SortOrder.DescendingOrder
        state.message = self.status.text()
        state.conditions_collapsed = self.conditions_collapsed
        state.last_task = self.last_task

    def mode_changed(self, index):
        if not hasattr(self, 'model'):
            return
        from .ui import MODES
        self.save_tab()
        self.close_drawer()
        self.current_mode = MODES[index]
        self.navigation.setCurrentIndex(index)
        offline = self.mode == 'offline'
        self.online_panel.setVisible(not offline)
        self.offline_panel.setVisible(offline)
        self.query.setVisible(not offline)
        self.batch_action.setVisible(not offline)
        self.file_filter.setVisible(not offline)
        for widget in [self.account_label, self.source_badge, self.account_button, self.logout_button]:
            widget.setVisible(not offline)
        state = self.tab_states[self.mode]
        self.result = state.result
        self.last_task = state.last_task
        self.model.reset(self.mode, state.rows)
        self.search.setText(state.filter_text)
        self.file_filter.setCurrentIndex(max(0, self.file_filter.findData(state.status_filter)))
        self.file_filter.view().setRowHidden(4, self.mode == 'notice')
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

    def set_file_filter(self):
        self.proxy_model.set_status_filter(self.file_filter.currentData())
        self.update_empty()

    def can_target_download(self):
        account = self.controller.sessions.account
        return bool(self.result and self.mode != 'offline' and all(self.result.date_range)
                    and self.result.operation in {'query', 'query_and_download', 'download_selected'}
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
        self.edit_conditions.setEnabled(not busy)
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
        self.selection_label.setText(f'Đã chọn {count} tệp')
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
                         from_date=self.result.date_range[0], to_date=self.result.date_range[1],
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
        self.details()
        if COLUMNS[self.mode][index.column()][0] == '_action':
            row = self.selected_row()
            if row and row.get('_file_status') == 'downloaded':
                self.open_detail_file()
            elif row:
                self.download_rows([row])

    def details(self):
        row = self.selected_row()
        if row is None:
            return
        self.detail_row = row
        labels = {'tax': [('to_khai', 'Tờ khai'), ('ma_ho_so', 'Mã hồ sơ'), ('ky_tinh_thue', 'Kỳ tính thuế'),
                          ('ngay_nop', 'Ngày nộp'), ('trang_thai', 'Trạng thái thuế')],
                  'gnt': [('so_gnt', 'Số giấy nộp tiền'), ('ctu_id', 'Mã chứng từ'), ('ngay_lap', 'Ngày lập'),
                          ('so_tien', 'Số tiền'), ('trang_thai', 'Trạng thái nộp / phê duyệt')],
                  'notice': [('ten_thong_bao', 'Tên thông báo'), ('so_thong_bao', 'Số thông báo'),
                             ('message_id', 'Mã thông báo'), ('ngay_gui', 'Ngày gửi'), ('trang_thai', 'Trạng thái xem')],
                  'offline': [('form_name', 'Mẫu / Tệp'), ('form_code', 'Mã mẫu'), ('form_version', 'Phiên bản'),
                              ('status', 'Kết quả parse'), ('source_inner_file', 'Nguồn XML'), ('source_zip', 'Nguồn ZIP')]}
        parts = ['<h3>Thông tin nghiệp vụ</h3>']
        for key, label in labels[self.mode]:
            value = display_amount(row.get(key), str(row.get('loai_tien', ''))) if key == 'so_tien' else str(row.get(key) or '—')
            parts.append(f'<p><span style="color:#67768C">{label}</span><br><b>{html.escape(value)}</b></p>')
        if self.mode != 'offline':
            parts.append('<hr><h3>Tệp trên máy</h3>')
            for label, value in [('Trạng thái tệp', FILE_LABELS.get(row.get('_file_status'), 'Chưa tải')),
                                 ('Đường dẫn', row.get('_file_path') or row.get('tep_zip') or row.get('tep_xml') or row.get('tep_pdf') or 'Chưa có'),
                                 ('Dung lượng', f"{row.get('_file_size', 0):,} byte"),
                                 ('Cập nhật tệp', row.get('_file_updated') or '—'),
                                 ('Chi tiết', row.get('_error_message') or row.get('_file_reason') or '—'),
                                 ('SHA-256', row.get('_file_hash') or '—')]:
                parts.append(f'<p><span style="color:#67768C">{label}</span><br>{html.escape(str(value))}</p>')
        else:
            parts.append('<p>Chỉ phân tích XML cục bộ; không xác thực chữ ký số hoặc tính đúng của nghĩa vụ thuế.</p>')
        self.detail_text.setHtml(''.join(parts))
        self.detail_open.setEnabled(bool(row.get('_file_path') and Path(row['_file_path']).is_file()))
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
        target = self.detail_row.get('_file_path')
        if target and Path(target).is_file():
            self.open_path(Path(target))
        else:
            self.detail_row.update(_file_status='not_downloaded', _file_path='', _file_reason='Tệp đã bị xóa hoặc di chuyển; kiểm tra lại tệp trên máy')
            self.model.layoutChanged.emit()
            self.populate_result(self.result)
            self.details()

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
        if self.mode != 'offline':
            if row.get('_file_status') == 'downloaded':
                menu.addAction('Mở tệp', lambda: (self.details(), self.open_detail_file()))
            else:
                action = menu.addAction('Tải riêng tệp này', lambda: self.download_rows([row]))
                action.setEnabled(self.can_target_download() and not self.controller.busy)
            menu.addAction('Sao chép mã đầy đủ', lambda: QApplication.clipboard().setText(remote_document_id(self.mode, row)))
        menu.addAction('Mở thư mục', self.open_output)
        menu.addAction('Sao chép metadata', lambda: QApplication.clipboard().setText(json.dumps(row, ensure_ascii=False)))
        menu.exec(self.table.viewport().mapToGlobal(position))

    def populate_result(self, result):
        self.files.clear()
        self.outputs_menu.clear()
        rows = self.model.rows
        self.counts.setToolTip(('Kết quả kỳ ' + ' – '.join(result.date_range) + '\n' if result and all(result.date_range) else '')
                              + 'Chỉ số theo toàn bộ danh sách của tài khoản/tab/kỳ đã tra cứu; không thay đổi theo bộ lọc bảng.')
        if self.mode == 'offline':
            mapped = sum(r.get('status') == 'MAPPED' for r in rows)
            self.counts.setText(f"Bản ghi {len(rows) or (result.discovered if result else 0)}    Đã mapping {mapped}    Cần kiểm tra {result.skipped if result else 0}    Lỗi {result.errors if result else 0}")
        else:
            count = counters(rows)
            self.counts.setText(f"Tìm thấy {count['found']}    Đã tải {count['downloaded']}    Chưa tải {count['pending']}    Tải lỗi {count['failed']}")
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
        for widget in [self.config_panel, self.tabs, self.navigation, self.settings_button, self.query, self.start_button]:
            widget.setEnabled(not busy)
        self.batch_action.setEnabled(not busy)
        self.stop_button.setEnabled(busy and state != 'STOPPING')
        self.progress.setRange(0, 0 if busy else 1)
        if not busy:
            self.progress.setValue(0)
        if state == 'STOPPING' and self.captcha_dialog:
            self.captcha_dialog.reject()
        self.sync_actions()

    def on_progress(self, payload):
        from .ui import MODES, TITLES
        if 'captcha_message' in payload:
            self.status.setText(payload['captcha_message'])
        if 'session' in payload:
            self.refresh_account()
            if payload['session'] == 'AUTHENTICATING':
                self.status.setText('Đang đăng nhập eTax…')
        if 'stage' in payload:
            self.status.setText('Đang xuất Excel…' if payload['stage'] == 'export' else 'Đang phân tích XML cục bộ…')
        if 'active_mode' in payload:
            self.status.setText('Đang xử lý: ' + TITLES[MODES.index(payload['active_mode'])])
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
            self.model.reset(self.mode, list(self.pending_rows.values()))
            done = payload.get('downloaded', 0)
            target = len(self.active_config.target_ids) if self.active_config.target_ids is not None else payload.get('discovered', 0)
            self.status.setText('Đang tra cứu hồ sơ…' if self.active_config.dry_run else f'Đang tải {done}/{target} · Lỗi {payload.get("errors", 0)}')
            if self.active_config.target_ids:
                self.progress.setRange(0, len(self.active_config.target_ids))
                self.progress.setValue(done)
            self.populate_result(self.result)
            self.update_empty()

    def on_completed(self, result):
        config, self.active_config = self.active_config, None
        self.last_task = result
        task_result = result
        self.refresh_account()
        if config and config.mode == 'login':
            self.save_login(config, result.state == 'SUCCESS')
            self.status.setText(result.message)
            after, self.after_login = self.after_login, None
            if result.state == 'SUCCESS' and after:
                QTimer.singleShot(0, after)
            elif result.state == 'ERROR':
                self.error(result.message)
        else:
            previous = self.result
            if config and config.action in {'verify', 'export_report'} and previous:
                files = list(dict.fromkeys(result.files + previous.files))
                result = replace(previous, rows=result.rows or previous.rows, files=files)
            elif config and config.target_ids and previous:
                updates = {document_id(self.mode, row): row for row in result.rows}
                result.rows = [{**row, **updates.get(document_id(self.mode, row), {})} for row in previous.rows]
                issue_map = {issue.get('document_id'): issue.get('message') for issue in result.issues}
                for row in result.rows:
                    key = document_id(self.mode, row)
                    if key in config.target_ids and row.get('_file_status') != 'downloaded' and (key in issue_map or result.state == 'ERROR'):
                        row.update(_file_status='failed', _error_message=issue_map.get(key) or result.message)
                result.discovered = len(result.rows)
                result.files = previous.files
            if result.children:
                for mode, child in result.children.items():
                    self.tab_states[mode] = TabState(result=child, rows=child.rows, message=child.message, conditions_collapsed=True)
                selected = self.tab_states[self.mode].result
            else:
                selected = result
            self.result = selected
            self.model.reset(self.mode, selected.rows if selected else [])
            if config and config.action not in {'verify', 'export_report'} and config.mode not in {'saved', 'import'}:
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
                short = 'Không tìm thấy hồ sơ trong kỳ này'
            self.status.setText("<a href='issues'>" + short + '</a>' if status_result.state in {'ERROR', 'PARTIAL'} else short)
            self.status.setStyleSheet('color:' + {'SUCCESS': '#15805B', 'PARTIAL': '#93631B', 'ERROR': '#C94242'}.get(status_result.state, '#67768C') + ';')
            self.status.setToolTip(status_result.message)
            self.populate_result(selected)
            if config and config.mode in {'tax', 'gnt', 'notice'} and result.state in {'SUCCESS', 'PARTIAL'}:
                self.collapse_conditions(True)
            self.save_tab()
            self.update_empty()
        if self.captcha_dialog:
            self.captcha_dialog.reject()
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
            parts.append(f'<p><b>{html.escape(document_label(issue.get("document_id") or ""))}</b><br>{html.escape(issue.get("message", ""))}</p>')
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
        layout.addWidget(QLabel('100 tác vụ gần nhất trong phiên. Dữ liệu cũ: Công cụ nâng cao → Đọc dữ liệu cũ.'))
        table = QTableWidget(len(entries), 7)
        table.setHorizontalHeaderLabels(['Thời gian', 'Nhóm', 'Kỳ', 'Tệp hoàn tất', 'Có sẵn', 'Lỗi', 'Kết quả'])
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for index, entry in enumerate(entries):
            result = entry['result']
            values = [result.ended_at[:19].replace('T', ' ') + ' UTC', TITLES[MODES.index(entry['mode'])] if entry['mode'] in MODES else 'Nhiều nhóm',
                      ' – '.join(result.date_range), str(result.downloaded), str(result.reused), str(result.errors), result.state]
            for column, value in enumerate(values):
                table.setItem(index, column, QTableWidgetItem(value))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table, 1)
        actions = QHBoxLayout()
        actions.addWidget(button('Xem tổng kết / lỗi', lambda: self.show_issues(entries[table.currentRow()]['result']) if table.currentRow() >= 0 else None))
        open_folder = button('Mở thư mục', lambda: self.open_path(entries[table.currentRow()]['result'].output) if table.currentRow() >= 0 else None)
        open_folder.setEnabled(False)
        table.currentCellChanged.connect(lambda *_args: open_folder.setEnabled(table.currentRow() >= 0 and entries[table.currentRow()]['result'].output.is_dir()))
        actions.addWidget(open_folder)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(dialog.reject)
        actions.addWidget(close)
        layout.addLayout(actions)
        fit_dialog(dialog, 950, 480)
        dialog.exec()

    def update_empty(self, *_args):
        if not hasattr(self, 'empty'):
            return
        self.empty.setVisible(self.proxy_model.rowCount() == 0)
        if self.proxy_model.rowCount():
            return
        if self.model.rowCount():
            message = 'Không có hồ sơ khớp tìm kiếm/bộ lọc. Thử chọn Tất cả hồ sơ.'
        elif self.controller.busy:
            message = 'Đang xử lý… Bạn có thể dừng an toàn; tệp hoàn tất được giữ.'
        elif self.result and self.result.state == 'ERROR':
            message = 'Không thể hoàn tất tác vụ. Nhấn Xem chi tiết ở thanh dưới để biết nguyên nhân và cách xử lý.'
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
        self.output_label.setText('Nơi xuất' if self.mode == 'offline' else 'Nơi lưu')
        self.start_button.setText('Chạy phân tích' if self.mode == 'offline' else 'Tra cứu và tải')
        self.xml_notice.setVisible(self.mode == 'offline' and height >= 430)
        self.counts.setVisible(not (height < 400 and not self.model.rows))
        columns = COLUMNS[self.mode]
        hidden = {'source_zip'} if self.mode == 'offline' and width < 1100 else set()
        if width < 900:
            hidden.update({'ky_tinh_thue', 'so_tien', 'form_version'})
        self.table.verticalHeader().setDefaultSectionSize(28 if height < 400 else 35 if self.ultra else 43)
        for index, (key, _) in enumerate(columns):
            self.table.setColumnHidden(index, key in hidden)
            self.table.horizontalHeader().setSectionResizeMode(index, QHeaderView.ResizeMode.Interactive)
            target = {'_selected': 34, '_action': 75, '_file_status': 83, 'ngay_nop': 128,
                      'ngay_lap': 128, 'ngay_gui': 128, 'trang_thai': 145,
                      'ky_tinh_thue': 95, 'so_tien': 120, 'form_code': 90,
                      'form_version': 80, 'status': 120}.get(key, 160)
            if width < 850:
                target = {'_selected': 30, '_action': 65, '_file_status': 76, 'ngay_nop': 108,
                          'ngay_lap': 108, 'ngay_gui': 108, 'trang_thai': 112}.get(key, target)
            self.table.setColumnWidth(index, target)
        self.table.horizontalHeader().setSectionResizeMode(0 if self.mode == 'offline' else 1, QHeaderView.ResizeMode.Stretch)
        self.position_drawer()
        self.refresh_account()

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
