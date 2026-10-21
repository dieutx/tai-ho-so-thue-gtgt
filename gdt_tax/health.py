"""Local doctor and explicit public reachability probes; never authenticate/download."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from . import __version__
from .auth_outcomes import AuthOutcome, classify_response
from .constants import LEGACY_ETAX_BASE, LOGIN_PAGE
from .errors import GdtError
from .http import HttpClient
from .portal_profiles import PROFILE_VERSION, ROUTING_VERSION
from .run_hooks import RunBudget, RunHooks
from .schema_evidence import safe_schema_evidence

SOURCES = ('DVC', 'ETAX', 'ETAX_LEGACY', 'GNT', 'TB')
LIMIT = 2 * 1024 * 1024


def event(source, operation, *, outcome='UNTESTED', complete=False, counts=None, elapsed_ms=0, run_id=None):
    return {'schema_version': 'support-event-v1', 'trace_id': uuid.uuid4().hex,
            'run_id': run_id or uuid.uuid4().hex, 'operation_id': uuid.uuid4().hex,
            'source': source if source in SOURCES else 'UNKNOWN', 'operation': operation,
            'profile_version': PROFILE_VERSION if source == 'DVC' else 'legacy-v1',
            'routing_version': ROUTING_VERSION, 'outcome': outcome, 'complete': complete,
            'counts': counts or {}, 'elapsed_ms': round(elapsed_ms, 3)}


def analyze_response(response, source, operation):
    from .gnt.parsing import parse_gnt_table
    from .parsing import parse_record_table
    from .tb.parsing import parse_tb_table
    if len(response.content) > LIMIT:
        return event(source, operation, outcome='EVIDENCE_LIMIT')
    adapter = 'DVC' if source in {'DVC', 'ETAX'} else 'ETAX_LEGACY'
    outcome = classify_response(response, adapter, phase='login_submit' if operation == 'login' else 'operation')
    report = event(source, operation, outcome=outcome.value, complete=outcome == AuthOutcome.SUCCESS)
    report.update(http_status=response.status_code, payload_bytes=len(response.content),
                  payload_sha256=hashlib.sha256(response.content).hexdigest(),
                  schema=safe_schema_evidence(response.text))
    if operation == 'search' and outcome == AuthOutcome.SCHEMA_UNKNOWN:
        parsed = (parse_gnt_table(response.text) if source == 'GNT' else parse_tb_table(response.text) if source == 'TB'
                  else parse_record_table(response.text, source))
        diagnostics = parsed.diagnostics
        report.update(outcome=diagnostics.status, complete=diagnostics.complete,
                      counts={'candidate': diagnostics.candidate_count, 'parsed': diagnostics.parsed_count,
                              'skipped': diagnostics.skipped_count, 'duplicates': diagnostics.duplicate_count})
    return report


def public_probe(source, *, client_factory=HttpClient, clock=time.monotonic):
    hooks = RunHooks(budget=RunBudget(max_seconds=15, max_requests=1, max_bytes=LIMIT,
                                    max_pages=1, max_auth_attempts=1))
    client = client_factory(timeout=10, retries=1, hooks=hooks)
    started = clock()
    report = event(source, 'public_reachability')
    report.update(authenticated_capability='UNTESTED', business_operations='UNTESTED', http_reachable=False)
    try:
        # One unauthenticated GET; no redirect, credentials, solver or business query.
        path = LOGIN_PAGE if source in {'DVC', 'ETAX'} else LEGACY_ETAX_BASE + '/'
        response = client.get(path, allow_redirects=False)
        report.update(http_reachable=True, http_status=response.status_code,
                      outcome=classify_response(response, 'DVC' if source in {'DVC', 'ETAX'} else 'ETAX_LEGACY', phase='page').value,
                      schema=safe_schema_evidence(response.text))
    except GdtError as error:
        report['outcome'] = getattr(error, 'code', 'HTTP_TRANSPORT_ERROR')
    finally:
        client.close()
    report.update(elapsed_ms=round((clock() - started) * 1000, 3),
                  last_verified_at=datetime.now(timezone.utc).isoformat(),
                  verification_scope='public_get_only', environment={'python': platform.python_version(), 'system': platform.system()})
    return report


def doctor(folder=None):
    from .parser.registry import load_registry
    registry = load_registry()
    report = event('DVC', 'offline_validate_inputs' if folder else 'doctor')
    report.update(core_version=__version__, last_verified_at=None, live_verification='NOT_PERFORMED',
        mapping_registry_sha256=registry.fingerprint,
        mappings=[{'id': m.mapping_id, 'version': m.mapping_version, 'namespace': m.detect_namespace,
                   'fields': len(m.fields)} for m in registry.mappings()])
    if folder is not None:
        from .export import build_rows, load_inputs
        try:
            manifest, parsed, classified = load_inputs(folder)
            rows = build_rows(manifest, parsed, classified, allow_legacy=False)
            partial = sum(row.get('status') != 'MAPPED' or row.get('validation_status') == 'PARTIAL'
                          or row.get('classification_status') != 'OK' for row in rows)
            report.update(outcome='PARTIAL' if partial else 'VALIDATED', complete=partial == 0,
                          counts={'rows': len(rows), 'partial': partial})
        except (GdtError, OSError, ValueError, TypeError):
            report.update(outcome='OFFLINE_INPUT_INVALID', complete=False)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(prog='gdt-health', description=__doc__)
    parser.add_argument('--source', choices=SOURCES, default='DVC')
    parser.add_argument('--operation', choices=['login', 'search'], default='search')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--fixture', type=Path, help='Analyze a local response without exporting its body')
    mode.add_argument('--validate-inputs', type=Path, help='Read-only validation of an offline bundle')
    mode.add_argument('--probe', action='store_true', help='Explicit one-request public reachability probe; no authentication')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.probe:
            report = public_probe(args.source)
        elif args.fixture:
            with args.fixture.open('rb') as stream:
                data = stream.read(LIMIT + 1)
            text = data.decode('utf-8', errors='replace')
            def payload():
                return json.loads(text)
            report = analyze_response(SimpleNamespace(content=data, text=text, status_code=200,
                                      headers={}, url='', json=payload), args.source, args.operation)
        else:
            report = doctor(args.validate_inputs)
        report.setdefault('authenticated_capability', 'UNTESTED')
        output = json.dumps(report, ensure_ascii=False, indent=2)
        if args.output:
            from .storage import _atomic_write
            args.output.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(args.output, output.encode('utf-8'))
        else:
            print(output)
        if args.fixture or args.validate_inputs:
            return int(not report['complete'])
        return int(args.probe and (not report.get('http_reachable') or report.get('http_status', 500) >= 400))
    except (GdtError, OSError, ValueError):
        print('{"outcome":"HEALTH_INPUT_OR_OUTPUT_ERROR","complete":false}')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
