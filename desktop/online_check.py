"""Explicit, bounded live diagnostics through the production Qt Worker.

Never runs on normal launch. Requests reference an existing local .env; passwords
are read into memory and never copied into requests, reports, logs or argv.
"""
from __future__ import annotations

import json
import logging
import sys
from dataclasses import replace
from pathlib import Path
from threading import Event

from gdt_tax.config import load_env_file
from gdt_tax.dates import parse_date
from gdt_tax.identity import account_fingerprint
from gdt_tax.run_hooks import RunBudget

from . import __version__
from .documents import document_id
from .services import RunConfig
from .settings_store import Preferences
from .state import job_output


def read_request(path: Path) -> dict:
    if path.stat().st_size > 16 * 1024:
        raise ValueError('LIVE_REQUEST_TOO_LARGE')
    request = json.loads(path.read_text(encoding='utf-8'))
    required = {'schema_version', 'env_file', 'username', 'output', 'report', 'periods', 'download'}
    if (not isinstance(request, dict) or not required.issubset(request)
            or set(request) - required - {'mode', 'dvc'}
            or request['schema_version'] != 1):
        raise ValueError('LIVE_REQUEST_SCHEMA_INVALID')
    if request.get('mode', 'tax') not in ('tax', 'gnt', 'notice'):
        raise ValueError('LIVE_MODE_INVALID')
    if (not isinstance(request.get('dvc', False), bool)
            or request.get('dvc', False) and request.get('mode', 'tax') != 'tax'):
        raise ValueError('LIVE_DVC_SCOPE_INVALID')
    if (not isinstance(request['username'], str) or not request['username'].strip()
            or not isinstance(request['download'], bool)
            or not isinstance(request['periods'], list) or not 1 <= len(request['periods']) <= 3):
        raise ValueError('LIVE_REQUEST_SCOPE_INVALID')
    for period in request['periods']:
        if not isinstance(period, dict) or set(period) != {'from', 'to'}:
            raise ValueError('LIVE_PERIOD_INVALID')
        start, end = parse_date(period['from']), parse_date(period['to'])
        if not 0 <= (end - start).days <= 30:
            raise ValueError('LIVE_PERIOD_LIMIT')
    for field in ('env_file', 'output', 'report'):
        if not isinstance(request[field], str) or not Path(request[field]).is_absolute():
            raise ValueError('LIVE_PATH_MUST_BE_ABSOLUTE')
    return request


def check_preferences() -> Preferences:
    return Preferences(solver='ddddocr', record_delay=0.5, page_delay=0.5,
                       jitter=0, retries=1, timeout=25, login_attempts=6, search_attempts=6)


def online_check(path: Path) -> int:
    from PySide6.QtCore import QThread, QTimer
    from PySide6.QtWidgets import QApplication

    from .jobs import Redactor, Worker
    from .sessions import ETaxSessionManager

    # No credential values or raw portal content reach console logs.
    logging.disable(logging.CRITICAL)
    request = read_request(path)
    credentials = load_env_file(Path(request['env_file']))
    if (credentials.get('GDT_USERNAME', '').casefold() != request['username'].casefold()
            or not credentials.get('GDT_PASSWORD')):
        raise ValueError('LIVE_CREDENTIAL_ACCOUNT_MISMATCH')
    report = Path(request['report'])
    if report.exists():
        raise ValueError('LIVE_REPORT_ALREADY_EXISTS')
    preferences = check_preferences()
    budget = RunBudget(max_seconds=300, max_requests=120, max_bytes=128 * 1024 * 1024,
                       max_pages=15, max_auth_attempts=6)
    config = RunConfig('login', Path(request['output']), username=request['username'],
        password=credentials['GDT_PASSWORD'], preferences=preferences, budget=budget,
        dvc=request.get('dvc', False))
    credentials.clear()
    config.validate()
    application = QApplication.instance() or QApplication([])
    application.setApplicationName('TaiHoSoThueOnlineCheck')
    manager = ETaxSessionManager()
    cancel = Event()
    redactor = Redactor(config)
    queue = [(config, 'login')]
    mode = request.get('mode', 'tax')
    for period in request['periods']:
        queue.append((replace(config, mode=mode, dry_run=True,
            output=job_output(config.output, config.username, mode),
            from_date=period['from'], to_date=period['to']), 'query'))
    results = []
    keep = []
    manual_required = []
    metadata = json.loads((Path(__file__).parent / 'resources/release.json').read_text(encoding='utf-8'))

    def finish():
        manager.close()
        payload = {'schema_version': 1, 'version': __version__, 'frozen': bool(getattr(sys, 'frozen', False)),
            'source_sha': metadata.get('source_sha', ''), 'account_key': account_fingerprint(config.username),
            'results': results, 'manual_captcha_required': bool(manual_required),
            'requests': budget.requests, 'bytes': budget.bytes_read, 'pages': budget.pages,
            'pass': not cancel.is_set() and not queue and bool(results)
                    and all(item['state'] == 'SUCCESS' for item in results)
                    and sum(item['operation'] == 'query' for item in results) == len(request['periods'])}
        report.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive output avoids overwriting earlier diagnostic evidence.
        with report.open('x', encoding='utf-8') as stream:
            json.dump(payload, stream, ensure_ascii=True, indent=2)
        application.exit(0 if payload['pass'] else 1)

    def start_next():
        if not queue or cancel.is_set():
            finish()
            return
        current, operation = queue.pop(0)
        thread = QThread()
        worker = Worker(current, cancel, redactor, manager)
        worker.moveToThread(thread)
        keep.append((thread, worker))

        def completed(result):
            results.append({'operation': operation, 'mode': current.mode, 'from': current.from_date, 'to': current.to_date,
                'dvc_enabled': current.dvc, 'sources': sorted({row['nguon'] for row in result.rows if row.get('nguon')}),
                'state': result.state, 'code': result.error_code, 'message': redactor(result.message),
                'discovered': result.discovered, 'downloaded': result.downloaded, 'reused': result.reused,
                'errors': result.errors, 'output': str(result.output),
                'attachments': [{key: value.get(key) for key in ('status', 'discovered', 'downloaded', 'reused', 'failed', 'discovery_failed')}
                                for value in result.attachment_results.values()]})
            if operation == 'login' and result.state != 'SUCCESS':
                queue.clear()
            if operation == 'query' and result.rows and request['download'] and result.state in {'SUCCESS', 'PARTIAL'}:
                row = result.rows[0]
                queue.insert(0, (replace(current, dry_run=False, action='download_selected',
                    output=result.output, target_ids=(document_id(current.mode, row),), input_rows=[dict(row)]), 'download'))
            if operation == 'download' and result.downloaded and result.state == 'SUCCESS':
                queue.insert(0, (current, 'reuse'))

        def manual(challenge):
            manual_required.append(True)
            challenge.respond(None)

        thread.started.connect(worker.run)
        worker.captcha.connect(manual)
        worker.done.connect(completed)
        worker.done.connect(thread.quit)
        worker.done.connect(worker.deleteLater)
        thread.finished.connect(start_next)
        thread.start()

    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(cancel.set)
    timer.start(300_000)
    QTimer.singleShot(0, start_next)
    return application.exec()
