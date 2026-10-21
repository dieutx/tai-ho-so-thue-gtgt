"""Live diagnostics require an explicit bounded request; tests never go online."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from desktop.online_check import check_preferences, read_request
from desktop.services import RunConfig
from tests.support import cleanup_temporary_directory


class OnlineCheckRequestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / 'request.json'
        self.request = {'schema_version': 1, 'username': 'synthetic', 'env_file': str(self.root / '.env'),
            'output': str(self.root / 'out'), 'report': str(self.root / 'report.json'),
            'download': True, 'periods': [{'from': '01/01/2013', 'to': '31/01/2013'}]}

    def tearDown(self):
        cleanup_temporary_directory(self.temp)

    def read(self):
        self.path.write_text(json.dumps(self.request), encoding='utf-8')
        return read_request(self.path)

    def test_explicit_valid_request_is_read_without_creating_output(self):
        self.assertEqual(self.read(), self.request)
        self.assertFalse(Path(self.request['output']).exists())
        self.assertFalse(Path(self.request['report']).exists())

    def test_live_preferences_pass_the_production_settings_contract(self):
        config = RunConfig('login', self.root, username='synthetic', password='synthetic-secret',
                           preferences=check_preferences())
        config.validate()
        self.assertEqual(config.settings().http_retries, 1)

    def test_only_reviewed_online_modes_are_accepted(self):
        for mode in ('tax', 'gnt', 'notice'):
            self.request['mode'] = mode
            self.assertEqual(self.read()['mode'], mode)
        for mode in ('batch', None, [], 'offline'):
            self.request['mode'] = mode
            with self.assertRaisesRegex(ValueError, 'MODE'):
                self.read()

    def test_explicit_dvc_routing_is_bounded_and_only_valid_for_tax(self):
        self.request['dvc'] = True
        self.assertTrue(self.read()['dvc'])
        for mode in ('gnt', 'notice'):
            self.request['mode'] = mode
            with self.assertRaisesRegex(ValueError, 'DVC_SCOPE'):
                self.read()
        self.request['mode'] = 'tax'
        for value in ('true', 1, None, []):
            self.request['dvc'] = value
            with self.assertRaisesRegex(ValueError, 'DVC_SCOPE'):
                self.read()

    def test_password_in_request_and_unbounded_dates_are_rejected(self):
        self.request['password'] = 'synthetic-should-never-be-in-request'
        with self.assertRaisesRegex(ValueError, 'SCHEMA'):
            self.read()
        del self.request['password']
        self.request['periods'][0]['to'] = '01/01/2015'
        with self.assertRaisesRegex(ValueError, 'PERIOD_LIMIT'):
            self.read()

    def test_scope_and_relative_paths_are_rejected(self):
        self.request['periods'] *= 4
        with self.assertRaisesRegex(ValueError, 'SCOPE'):
            self.read()
        self.request['periods'] = self.request['periods'][:1]
        self.request['output'] = 'relative-output'
        with self.assertRaisesRegex(ValueError, 'ABSOLUTE'):
            self.read()
