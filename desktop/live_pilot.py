"""Explicit, small authorized pilot with independent settings and strict quotas."""
from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QDate

from gdt_tax.run_hooks import RunBudget

from .settings_store import SettingsStore
from .ui import MainWindow


class PilotWindow(MainWindow):
    def __init__(self):
        self.pilot_root = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'TaiHoSoThue' / 'live-pilot'
        super().__init__(SettingsStore(self.pilot_root / 'settings.json'))
        self.setWindowTitle('Tải Hồ Sơ Thuế — Kiểm thử live có giới hạn')
        self.output.setText(str(self.pilot_root / 'HoSo'))
        self.preferences = replace(self.preferences, solver='manual', retries=1, login_attempts=1,
                                   search_attempts=1, record_delay=1, page_delay=1, jitter=.3)
        self.applying_preset = True
        self.from_date.setDate(QDate.currentDate().addDays(-6))
        self.to_date.setDate(QDate.currentDate())
        self.applying_preset = False
        self.status.setText('Pilot: tối đa 7 ngày, 5 hồ sơ, 40 yêu cầu/lượt; CAPTCHA nhập tay. Dừng khi 403/429/503.')
        self.batch_action.setVisible(False)

    def make_config(self, mode, dry_run=False):
        config = super().make_config(mode, dry_run)
        if mode != 'offline':
            config = replace(config, budget=RunBudget(max_requests=40, max_pages=2,
                              max_seconds=300, max_bytes=20 * 1024 * 1024, max_auth_attempts=2,
                              max_records=5, stop_on_http_errors=True, min_request_interval=1))
        return config

    def start_batch(self):
        self.error('Pilot chỉ chạy từng nghiệp vụ, tối đa 5 hồ sơ/lượt')

    def on_completed(self, result):
        config = self.active_config
        super().on_completed(result)
        self.pilot_root.mkdir(parents=True, exist_ok=True)
        summary = {'state': result.state, 'operation': result.operation,
                   'mode': config.mode if config else '', 'found_online': result.discovered,
                   'downloaded_or_reused': result.downloaded, 'reused': result.reused,
                   'errors': result.errors, 'error_code': result.error_code,
                   'requests': config.budget.requests if config and config.budget else 0,
                   'account': result.account_key[:8], 'task_id': result.task_id,
                   'started_at': result.started_at, 'ended_at': result.ended_at}
        report = self.pilot_root / ('pilot-' + result.task_id + '.json')
        report.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

    def launch(self, config, clear=True):
        if self.from_date.date().daysTo(self.to_date.date()) not in range(7):
            self.error('Chọn khoảng tối đa 7 ngày cho kiểm thử live')
            return
        return super().launch(config, clear)
