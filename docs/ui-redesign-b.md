# Bàn giao nâng cấp UI theo b.md

## Kết quả
Sửa trực tiếp ứng dụng PySide6, entry point `desktop.main`, không thêm dependency.
Giữ JobController, RunConfig, RecordsModel/RecordsProxy, service tải và kho dữ liệu.

- Toolbar một hàng ở cửa sổ rộng, tự chuyển hàng khi hẹp; ngày tùy chỉnh trong popup, bổ sung preset 3/6 tháng theo quy ước addMonths hiện có.
- Bộ lọc có số điều kiện đang áp dụng; tổng kho chuyển vào tooltip, summary ghi rõ kỳ đang xem.
- Menu thao tác từng dòng mở bằng dấu ba chấm; tải chỉ chạy khi chọn đúng action, điều kiện busy/session giữ nguyên.
- Phản hồi CQT mở cửa sổ riêng, giữ nguyên panel, nguồn dữ liệu và handler XML.
- Nút dừng/progress chỉ hiện khi tác vụ chạy; lịch sử và đăng xuất vào menu cài đặt.
- Chuyển nơi lưu, thay đổi thư mục, mở thư mục và tùy chọn vào menu cài đặt; đường dẫn và control gốc được giữ.
- Hành động chính tra cứu và tải; tra cứu riêng trong menu cạnh nút chính.
- Bộ lọc và thao tác tải thiếu/thử lại/kiểm tra dùng control gốc trong popup.
- Bảng bỏ đường kẻ ô, lựa chọn nền nhạt, font Segoe UI 13px, token màu thống nhất.
- Drawer tối đa 400px, dành vùng bảng riêng khi rộng >=1200px; overlay khi hẹp. Esc/X giữ nguyên selection.
- Kỹ thuật, metadata, copy mã, xuất hồ sơ chuyển vào menu drawer, tiếp tục gọi control gốc.
- Phiên bản chuyển vào Giới thiệu. Công cụ nâng cao chia nhóm; lịch sử vẫn truy cập được.
- XML viewer ẩn nguồn kỹ thuật trong mục mở rộng, giới hạn kích thước theo màn hình; giữ copy/save/open và dữ liệu XML.

## Đối chiếu thay đổi
| Chức năng | Trước | Sau | Handler giữ lại | Kiểm thử |
|---|---|---|---|---|
| Tra cứu | Nút toolbar | Menu cạnh nút chính | start(True) | PASS, mock không mạng |
| Tra cứu và tải | Toolbar | Toolbar | start(False) | PASS, fixture |
| Nơi lưu/Thay đổi/Mở thư mục/Tùy chọn | Toolbar | Menu cài đặt | PathEdit, browse, open_output, task_options | PASS cấu trúc; mở Explorer NOT TESTED |
| Tìm kiếm/reset | Vùng kết quả | Vùng kết quả | proxy/reset_filters | PASS |
| Lọc tệp/CQT/loại thông báo | Vùng kết quả | Popup bộ lọc | set_file_filter/set_cqt_filter/set_type_filter | PASS |
| Tải thiếu/thử lại/kiểm tra | Nút thường trực | Popup bộ lọc | download_missing/retry_failed/verify_files | PASS hồi quy |
| Chọn hàng loạt | Thanh theo lựa chọn | Giữ nguyên | download_checked/refresh_checked/clear_selection | PASS |
| Copy/kỹ thuật/metadata/xuất ZIP | Drawer nhiều nút | Thao tác khác | copy_document_id/technical_details/raw_details/export_detail_bundle | PASS copy qua menu sau đổi dòng; export kỹ thuật giữ handler, chưa bấm mọi mục |
| Xem/tải/cập nhật hồ sơ | Chân drawer | Giữ nguyên | open_detail_file/download_detail | PASS hồi quy |
| Phản hồi CQT | Bảng dưới | Cửa sổ riêng, đóng bằng Esc/X | show_feedback_panel/open_feedback_asset | PASS hồi quy |
| XML copy/save/open | Viewer | Giữ nguyên | copy_xml/save_file/open_external | PASS bộ test viewer; ứng dụng OS NOT TESTED |
| Tài khoản/DN/CN | Header | Giữ nguyên | change_account_type/open_login/logout | PASS cô lập tài khoản; đăng nhập thật NOT TESTED |
| Lịch sử/cài đặt/giới thiệu | Header/footer | Menu cài đặt và các shortcut cũ | show_history/settings/show_release | Giữ handler; kiểm thử thủ công NOT TESTED |
| Công cụ nâng cao | Menu phẳng | Nhóm theo công việc | Tất cả action gốc giữ lại | PASS hồi quy; chạy từng công cụ thật NOT TESTED |

## Kiểm thử
Python: `.venv-release/Scripts/python.exe` (môi trường .venv không có PySide6).
Lệnh: `-m unittest tests.test_desktop_usability tests.test_desktop_v2 tests.test_xml_viewer tests.test_desktop tests.test_desktop_upgrade tests.test_desktop_notices tests.test_table_contracts tests.test_search_and_state -q`
Kết quả cuối: 167 tests, OK (gồm thêm tests.test_feedback_contract). Các bài lỗi HTTP/XML/ổ đĩa là tình huống fixture có chủ đích.
Capture: `scripts/capture_v2.py --size 1366x768` và `--size 1920x1080`, QT_QPA_PLATFORM=offscreen; cả hai JSON báo pass=true, bốn tab và drawer GNT; chặn socket mạng.
Bằng chứng cuối ở `.cache/final-redesign-tests.log`, `.cache/v2-fixture-ui/check-*.json` và PNG cùng thư mục. Chạy thêm capture_v2.py không tham số: 6 trường hợp 1080×660/1366×728 ở scale 1/1.25/1.5, cả bốn tab và drawer đạt. Đây là Qt offscreen scale, chưa phải kiểm tra thay DPI trực tiếp trên Windows.

Các test mới kiểm tra popup ngày/Esc, preset 3/6/12 tháng không khởi chạy job, sao chép đúng hồ sơ sau đổi dòng qua menu drawer, Esc cửa sổ phản hồi giữ tìm kiếm, chặn cả hai chế độ tra cứu khi busy, menu từng dòng không tự tải.

## Đo mật độ giao diện
So sánh HEAD trước nâng cấp với working tree, khởi tạo bằng SettingsStore trong thư mục tạm, cùng bốn tab và trạng thái chưa tra cứu. Đếm QPushButton/QComboBox/QLineEdit/QDateEdit/QLabel đang hiện trong cửa sổ chính, loại editor nội bộ và con của bảng. Không đếm từng ô bảng hoặc item menu ẩn. Phép đo gồm control và nhãn, không phải số chức năng.

| Tab | Trước | Sau | Giảm |
|---|---:|---:|---:|
| Tờ khai | 31 | 13 | 58,1% |
| Giấy nộp tiền | 30 | 13 | 56,7% |
| Thông báo thuế | 31 | 13 | 58,1% |
| XML | 23 | 14 | 39,1% |

Đạt mức giảm tối thiểu 30%; ba tab online vượt khoảng mục tiêu 30–50% trong trạng thái ban đầu. Khi có dữ liệu, bộ đếm/selection/progress xuất hiện theo ngữ cảnh nên tỷ lệ thay đổi. Bằng chứng `.cache/redesign-control-count.json`; script `.cache/measure_redesign.py`.

## File thay đổi
- `desktop/v2_layout.py`: tổ chức toolbar/menu, popup ngày, dialog phản hồi, shell và drawer dùng chung.
- `desktop/v2_interactions.py`: responsive, preset, summary, menu dòng, trạng thái tác vụ, vòng đời phản hồi.
- `desktop/ui.py`: theme và đóng phản hồi khi đổi tài khoản.
- `desktop/table_model.py`: cột thao tác dạng menu, giữ quyền xem menu khi chưa thể tải; từng action kiểm tra quyền tải.
- `desktop/xml_viewer.py`: nguồn kỹ thuật mở rộng, kích thước theo màn hình.
- `tests/test_desktop_usability.py`, `tests/test_desktop.py`: kiểm tra hành vi và cập nhật vị trí control.
- `scripts/capture_v2.py`: kiểm tra control ở bố cục mới bằng fixture có chặn socket.

## Chưa xác minh / giới hạn
- NOT TESTED: kết nối cổng thuế thật, đăng nhập tài khoản thật, mở Explorer/ứng dụng mặc định, thay DPI trên desktop Windows thật.
- NOT TESTED: bấm thủ công mọi menu export/đối soát/cài đặt và benchmark hàng chục nghìn hồ sơ. Giữ nguyên service/handler hiện hữu; không suy ra PASS từ việc giữ source.
- Bộ lọc chỉ cung cấp các trường backend/model đã hỗ trợ, không bổ sung giả bộ lọc chưa có như trạng thái đã xem thông báo.
- Không đổi schema, endpoint, cơ chế xác thực, quy tắc ghi tệp hay dữ liệu XML. Tất cả ghi/xóa của test nằm trong thư mục tạm/fixture.

## Danh mục control/handler có sẵn trước thay đổi
Danh mục dưới trích từ source HEAD bằng AST, để đối chiếu cả các chức năng ít dùng. Các control không nêu thay đổi ở trên giữ nguyên vị trí và handler.

| File | Control hoặc signal gốc | Handler |
|---|---|---|
| desktop/v2_layout.py:73 | 'v' + __version__ | `self.show_release` |
| desktop/v2_layout.py:81 | self.account_type.currentChanged.connect | `self.change_account_type` |
| desktop/v2_layout.py:87 | self.account_label.customContextMenuRequested.connect | `self.account_context_menu` |
| desktop/v2_layout.py:91 | 'Đăng nhập' | `self.open_login` |
| desktop/v2_layout.py:94 | '' | `self.logout` |
| desktop/v2_layout.py:97 | '' | `self.settings` |
| desktop/v2_layout.py:113 | 'Tải ngay' | `self.download_update` |
| desktop/v2_layout.py:116 | 'Để sau' | `self.dismiss_update` |
| desktop/v2_layout.py:124 | self.tabs.currentChanged.connect | `self.mode_changed` |
| desktop/v2_layout.py:127 | self.navigation.currentIndexChanged.connect | `self.tabs.setCurrentIndex` |
| desktop/v2_layout.py:165 | self.preset.currentIndexChanged.connect | `self.apply_preset` |
| desktop/v2_layout.py:172 | self.input_path.textEdited.connect | `self.clear_source_selection` |
| desktop/v2_layout.py:178 | 'Chọn thư mục ZIP/XML…' | `lambda: self.browse(self.input_path)` |
| desktop/v2_layout.py:179 | 'Chọn tệp XML/ZIP…' | `self.choose_xml_files` |
| desktop/v2_layout.py:201 | 'Mở thư mục' | `self.open_output` |
| desktop/v2_layout.py:203 | 'Tùy chọn' | `self.task_options` |
| desktop/v2_layout.py:205 | 'Tra cứu' | `lambda: self.start(True)` |
| desktop/v2_layout.py:207 | 'Tra cứu và tải' | `lambda: self.start(False)` |
| desktop/v2_layout.py:234 | 'Xóa bộ lọc' | `self.reset_filters` |
| desktop/v2_layout.py:266 | 'Tải chưa tải' | `self.download_missing` |
| desktop/v2_layout.py:267 | 'Thử lại tệp lỗi' | `self.retry_failed` |
| desktop/v2_layout.py:268 | 'Kiểm tra tệp' | `self.verify_files` |
| desktop/v2_layout.py:280 | 'Cập nhật đã chọn' | `self.refresh_checked` |
| desktop/v2_layout.py:290 | self.search.textChanged.connect | `self.proxy_model.setFilterFixedString` |
| desktop/v2_layout.py:291 | self.search.textChanged.connect | `self.update_empty` |
| desktop/v2_layout.py:292 | self.search.textChanged.connect | `self.update_filtered_count` |
| desktop/v2_layout.py:293 | self.file_filter.currentIndexChanged.connect | `lambda: self.set_file_filter()` |
| desktop/v2_layout.py:294 | self.cqt_filter.currentIndexChanged.connect | `self.set_cqt_filter` |
| desktop/v2_layout.py:295 | self.type_filter.currentIndexChanged.connect | `self.set_type_filter` |
| desktop/v2_layout.py:296 | self.model.modelReset.connect | `self.update_filtered_count` |
| desktop/v2_layout.py:297 | self.model.modelReset.connect | `self.refresh_type_filter` |
| desktop/v2_layout.py:298 | self.proxy_model.modelReset.connect | `self.update_filtered_count` |
| desktop/v2_layout.py:299 | self.proxy_model.rowsInserted.connect | `lambda *_args: self.update_filtered_count()` |
| desktop/v2_layout.py:300 | self.proxy_model.rowsRemoved.connect | `lambda *_args: self.update_filtered_count()` |
| desktop/v2_layout.py:301 | self.proxy_model.layoutChanged.connect | `self.update_filtered_count` |
| desktop/v2_layout.py:302 | self.model.selection_changed.connect | `self.selection_changed` |
| desktop/v2_layout.py:309 | self.model.selection_changed.connect | `self.table.horizontalHeader().viewport().update` |
| desktop/v2_layout.py:317 | self.table.horizontalHeader().sectionClicked.connect | `self.select_visible_header` |
| desktop/v2_layout.py:318 | self.table.horizontalHeader().sectionResized.connect | `self._remember_column_width` |
| desktop/v2_layout.py:321 | self.table.clicked.connect | `self.table_clicked` |
| desktop/v2_layout.py:322 | self.table.activated.connect | `lambda _index: self.details()` |
| desktop/v2_layout.py:324 | self.table.customContextMenuRequested.connect | `self.context_menu` |
| desktop/v2_layout.py:339 | self.model.modelReset.connect | `self.update_empty` |
| desktop/v2_layout.py:340 | self.proxy_model.modelReset.connect | `self.update_empty` |
| desktop/v2_layout.py:341 | self.proxy_model.rowsInserted.connect | `lambda *_args: self.update_empty()` |
| desktop/v2_layout.py:342 | self.proxy_model.rowsRemoved.connect | `lambda *_args: self.update_empty()` |
| desktop/v2_layout.py:345 | self.feedback_panel.open_asset.connect | `self.open_feedback_asset` |
| desktop/v2_layout.py:346 | self.feedback_panel.save_asset.connect | `self.save_feedback_asset` |
| desktop/v2_layout.py:347 | self.feedback_panel.open_folder.connect | `self.open_feedback_folder` |
| desktop/v2_layout.py:348 | self.feedback_panel.technical.connect | `self.show_feedback_technical` |
| desktop/v2_layout.py:354 | self.files.activated.connect | `self.open_file_choice` |
| desktop/v2_layout.py:356 | 'Dừng' | `self.controller.stop` |
| desktop/v2_layout.py:362 | self.status.linkActivated.connect | `lambda _url: self.show_issues()` |
| desktop/v2_layout.py:372 | 'Lịch sử tải' | `self.show_history` |
| desktop/v2_layout.py:375 | 'Mở thư mục' | `self.open_output` |
| desktop/v2_layout.py:376 | 'Mở báo cáo' | `self.open_report` |
| desktop/v2_layout.py:377 | 'Xuất danh sách Excel…' | `self.export_report` |
| desktop/v2_layout.py:378 | 'Đối soát và xuất báo cáo…' | `self.show_reconciliation` |
| desktop/v2_layout.py:380 | 'Nhật ký kỹ thuật (0)' | `self.show_logs` |
| desktop/v2_layout.py:381 | 'Kiểm tra lại tệp trên máy' | `self.verify_files` |
| desktop/v2_layout.py:383 | 'Tải các nhóm liên tiếp…' | `self.batch_dialog` |
| desktop/v2_layout.py:384 | 'Đọc / sao chép dữ liệu cũ…' | `self.import_legacy` |
| desktop/v2_layout.py:385 | 'Xem hồ sơ đã lưu trên máy…' | `self.open_local_account` |
| desktop/v2_layout.py:397 | '' | `self.close_drawer` |
| desktop/v2_layout.py:409 | 'Xem phản hồi' | `self.open_detail_notices` |
| desktop/v2_layout.py:415 | 'Xuất hồ sơ' | `self.export_detail_bundle` |
| desktop/v2_layout.py:422 | 'Xem file' | `self.open_detail_file` |
| desktop/v2_layout.py:423 | 'Tải tệp' | `self.download_detail` |
| desktop/v2_layout.py:162 | widget.dateChanged.connect | `self.dates_changed` |
| desktop/v2_layout.py:200 | 'Thay đổi' | `lambda: self.browse(self.output)` |
| desktop/v2_layout.py:279 | 'Tải các tệp đã chọn' | `self.download_checked` |
| desktop/v2_layout.py:283 | 'Bỏ chọn' | `self.clear_selection` |
| desktop/v2_layout.py:406 | 'Sao chép mã' | `self.copy_document_id` |
| desktop/v2_layout.py:407 | 'Thông tin kỹ thuật' | `self.technical_details` |
| desktop/v2_layout.py:418 | 'Metadata gốc' | `self.raw_details` |
| desktop/v2_layout.py:438 | action.triggered.connect | `callback` |
| desktop/v2_layout.py:444 | action.triggered.connect | `callback` |
| desktop/ui.py:70 | result.clicked.connect | `callback` |
| desktop/ui.py:309 | self.catalog_refresh_timer.timeout.connect | `self.apply_local_date_filter` |
| desktop/ui.py:323 | self.controller.state_changed.connect | `self.on_state` |
| desktop/ui.py:324 | self.controller.progress.connect | `self.on_progress` |
| desktop/ui.py:325 | self.controller.completed.connect | `self.on_completed` |
| desktop/ui.py:326 | self.controller.captcha.connect | `self.on_captcha` |
| desktop/ui.py:327 | self.controller.logs.connect | `self.on_logs` |
| desktop/ui.py:351 | checker.found.connect | `self.show_update_banner` |
| desktop/ui.py:451 | 'Kiểm tra bản mới' | `lambda: None` |
| desktop/ui.py:453 | checker.done.connect | `status.setText` |
| desktop/ui.py:454 | checker.done.connect | `lambda _message: check.setEnabled(True) if check.isVisible() else None` |
| desktop/ui.py:459 | check.clicked.connect | `start_check` |
| desktop/ui.py:463 | controls.rejected.connect | `dialog.reject` |
| desktop/ui.py:693 | 'Đăng nhập tài khoản khác…' | `lambda: self.open_login(initial=('', ''))` |
| desktop/ui.py:750 | controls.accepted.connect | `dialog.accept` |
| desktop/ui.py:751 | controls.rejected.connect | `dialog.reject` |
| desktop/ui.py:827 | controls.accepted.connect | `dialog.accept` |
| desktop/ui.py:828 | controls.rejected.connect | `dialog.reject` |
| desktop/ui.py:913 | buttons.accepted.connect | `lambda: dialog.accept() if entry.text().strip() else None` |
| desktop/ui.py:914 | buttons.rejected.connect | `dialog.reject` |
| desktop/ui.py:915 | entry.returnPressed.connect | `lambda: dialog.accept() if entry.text().strip() else None` |
| desktop/ui.py:947 | self.log_filter.currentIndexChanged.connect | `self.render_logs` |
| desktop/ui.py:948 | dialog.finished.connect | `lambda _result: setattr(self, 'log_dialog', None)` |
| desktop/ui.py:1002 | screen.availableGeometryChanged.connect | `self.fit_screen` |
| desktop/ui.py:179 | 'Mặc định' | `self.reset` |
| desktop/ui.py:180 | 'Nhập .env…' | `self.import_env` |
| desktop/ui.py:182 | 'Hủy' | `self.reject` |
| desktop/ui.py:183 | 'Áp dụng' | `self.apply` |
| desktop/ui.py:387 | 'Tải bản cập nhật' | `download` |
| desktop/ui.py:388 | 'Bỏ qua' | `self.dismiss_update` |
| desktop/ui.py:461 | 'Mở trang phát hành / tải cập nhật' | `lambda: QDesktopServices.openUrl(QUrl(RELEASES_URL))` |
| desktop/ui.py:690 | username | `lambda _checked=False, name=username: self.open_login(initial=(name, ''))` |
| desktop/ui.py:945 | 'Sao chép' | `lambda: QApplication.clipboard().setText(self.log_text.toPlainText())` |
| desktop/ui.py:991 | self.windowHandle().screenChanged.connect | `self.screen_changed` |
| desktop/ui.py:730 | controls.accepted.connect | `dialog.accept` |
| desktop/ui.py:731 | controls.rejected.connect | `dialog.reject` |
| desktop/xml_viewer.py:119 | self.copy_button.clicked.connect | `self.copy_xml` |
| desktop/xml_viewer.py:121 | self.save_button.clicked.connect | `self.save_file` |
| desktop/xml_viewer.py:123 | self.open_button.clicked.connect | `self.open_external` |
| desktop/xml_viewer.py:130 | close.clicked.connect | `self.reject` |
| desktop/feedback_panel.py:78 | self.close_button.clicked.connect | `self._close` |
| desktop/feedback_panel.py:99 | self.table.cellActivated.connect | `self._activate` |
| desktop/feedback_panel.py:118 | 'Mở bằng ứng dụng mặc định' | `lambda: self.open_asset.emit(item)` |
| desktop/feedback_panel.py:120 | 'Lưu tệp…' | `lambda: self.save_asset.emit(item)` |
| desktop/feedback_panel.py:121 | 'Mở thư mục chứa tệp' | `lambda: self.open_folder.emit(item)` |
| desktop/feedback_panel.py:123 | 'Thông tin kỹ thuật' | `lambda: self.technical.emit(item)` |
| desktop/feedback_panel.py:148 | primary.clicked.connect | `lambda _checked=False, item=item: self.open_asset.emit(item)` |
| desktop/feedback_panel.py:154 | more.clicked.connect | `lambda _checked=False, row=row: self._secondary_menu(row).exec(more.mapToGlobal(more.rect().bottomLeft()))` |
