"""Source UI evidence populated only through real adapters + existing fixtures."""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def capture(size: str) -> None:
    from PySide6.QtCore import QPoint, QRect
    from PySide6.QtWidgets import QApplication

    from desktop.documents import document_id
    from desktop.services import RunConfig, run_offline, run_online
    from desktop.settings_store import Preferences, SettingsStore
    from desktop.ui import MainWindow
    from gdt_tax.run_hooks import RunHooks
    from tests.support import FakeHttp, FakeResponse, StubCaptcha
    from tests.test_etax_legacy import make_legacy_handler
    from tests.test_gnt import make_gnt_handler
    from tests.test_tb import make_tb_handler
    scale = float(os.environ.get('QT_SCALE_FACTOR', '1'))
    width, height = map(int, size.split('x'))
    output = Path('.cache/v2-fixture-ui').resolve()
    output.mkdir(parents=True, exist_ok=True)
    data = output / 'data' / (size + '-' + str(scale))
    data.mkdir(parents=True, exist_ok=True)
    prefs = Preferences(output=str(data), record_delay=0, page_delay=0, jitter=0, login_attempts=1, search_attempts=1)
    store = SettingsStore(data / 'settings.json')
    store.save(prefs)
    app = QApplication.instance() or QApplication([])
    window = MainWindow(store)
    window.controller.sessions.set_account('fixture-user', 'fixture-secret')
    window.show()
    app.processEvents()
    failures = []
    for mode, factory in [('tax', make_legacy_handler), ('gnt', make_gnt_handler), ('notice', make_tb_handler), ('offline', None)]:
        window.close_drawer()
        window.tabs.setCurrentIndex(['tax', 'gnt', 'notice', 'offline'].index(mode))
        config = RunConfig(mode, data / mode, username='fixture-user', password='fixture-secret', preferences=prefs,
                           dry_run=mode != 'offline', source=Path('tests/fixtures').resolve(),
                           from_date='01/06/2025' if mode == 'tax' else '01/09/2026',
                           to_date='30/06/2025' if mode == 'tax' else '30/09/2026')
        if mode == 'offline':
            config.validate()
            result = run_offline(config, RunHooks(), logging.getLogger('fixture'))
            window.input_path.setText(str(config.source))
        else:
            result = run_online(config, RunHooks(), StubCaptcha(), logging.getLogger('fixture'), http=FakeHttp(factory({})))
            first = result.rows[0]
            download = replace(config, dry_run=False, target_ids=(document_id(mode, first),), input_rows=[first])
            download.validate()
            saved = run_online(download, RunHooks(), StubCaptcha(), logging.getLogger('fixture'), http=FakeHttp(factory({})))
            updates = {document_id(mode, row): row for row in saved.rows}
            result.rows = [{**row, **updates.get(document_id(mode, row), {})} for row in result.rows]
            if mode == 'gnt' and len(result.rows) > 1:
                second = result.rows[1]
                failed = replace(config, dry_run=False, target_ids=(document_id(mode, second),), input_rows=[second])
                result = run_online(failed, RunHooks(), StubCaptcha(), logging.getLogger('fixture'),
                                    http=FakeHttp(factory({'download_response': FakeResponse(status_code=500)})))
        window.result = result
        window.model.reset(mode, result.rows)
        window.populate_result(result)
        window.status.setText('Có 1 lỗi tải · Fixture' if result.errors and mode != 'offline' else
                              'Phân tích hoàn tất một phần · Fixture' if mode == 'offline' else 'Tra cứu hoàn tất · Fixture')
        window.collapse_conditions(mode != 'offline')
        window.warning.setText('Ảnh kiểm thử fixture • Không kết nối cổng thuế, không dùng dữ liệu thuế thật')
        window.warning.show()
        window.resize(int(width / scale), int(height / scale))
        app.processEvents()
        area = QRect(0, 0, int(width / scale), int(height / scale))
        with patch.object(window, 'screen', return_value=SimpleNamespace(availableGeometry=lambda workarea=area: workarea)):
            window.fit_screen()
        app.processEvents()
        for control in [window.table, window.stop_button, window.history_button, window.menu_button,
                        window.config_panel if mode == 'offline' else window.condition_summary]:
            top = control.mapTo(window, QPoint(0, 0))
            bottom = control.mapTo(window, control.rect().bottomRight())
            if not control.isVisible() or not window.rect().contains(top) or not window.rect().contains(bottom):
                failures.append(mode + ': clipped/hidden ' + type(control).__name__)
        window.grab().save(str(output / f'{mode}-{size}-{scale}.png'))
        if mode == 'gnt':
            window.table.setCurrentIndex(window.proxy_model.mapFromSource(window.model.index(1, 1)))
            window.details()
            app.processEvents()
            window.grab().save(str(output / f'gnt-detail-{size}-{scale}.png'))
            if not window.centralWidget().rect().contains(window.drawer.geometry()):
                failures.append('drawer outside central widget')
    window.close()
    report = {'pass': not failures, 'fixture_only': True, 'size': size, 'scale': scale, 'errors': failures}
    (output / f'check-{size}-{scale}.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    if failures:
        raise AssertionError(failures)


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    parser = argparse.ArgumentParser()
    parser.add_argument('--size')
    args = parser.parse_args()
    if args.size:
        with patch('socket.socket.connect', side_effect=AssertionError('fixture capture used network')):
            capture(args.size)
        return
    for size in ['1080x660', '1366x728']:
        for scale in ['1', '1.25', '1.5']:
            subprocess.run([sys.executable, str(Path(__file__)), '--size', size],
                           env=dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_SCALE_FACTOR=scale), check=True, timeout=60)
    print('PASS: six populated fixture UI cases, four tabs and GNT drawer')


if __name__ == '__main__':
    main()
