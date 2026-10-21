"""Failure-injected GitLab replacement; no credentials/network/publish/build."""
from __future__ import annotations

import hashlib
import json
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts.release_transaction import (
    ASSETS,
    CHECKSUM,
    EXE,
    ReleaseError,
    Replacement,
    load_bundle,
)
from tests.support import temporary_directory

API = 'https://gitlab.com/api/v4/projects/synthetic'
TAG = 'desktop-v2.0.0'


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Response:
    def __init__(self, data=None, body=b'', status_code=200):
        self.data, self.body = data, body
        self.status_code = status_code

    def json(self):
        return deepcopy(self.data)

    def iter_content(self, size):
        for offset in range(0, len(self.body), 13):
            yield self.body[offset:offset + 13]

    def close(self):
        pass


class FakeGitLab:
    def __init__(self, failure=''):
        self.client = SimpleNamespace(headers={'PRIVATE-TOKEN': 'private-fixture-token'}, close=lambda: None)
        self.public = SimpleNamespace(close=lambda: None)
        self.failure, self.failed = failure, False
        self.calls = []
        self.linked = False
        self.block_rollback = False
        self.source = 'a' * 40
        old_exe = b'old-synthetic-not-executable'
        old_checksum = (sha(old_exe) + '  ' + EXE + '\n').encode()
        self.payloads, self.names = {}, {}
        links = []
        for index, (name, data) in enumerate(zip(ASSETS, (old_exe, old_checksum), strict=True), 10):
            url = 'https://gitlab.com/old-package/' + name
            self.payloads[url], self.names[url] = data, name
            links.append({'id': index, 'name': name, 'url': url, 'link_type': 'package',
                          'direct_asset_url': 'https://gitlab.com/project/-/releases/' + TAG + '/downloads/' + name})
        self.release = {'tag_name': TAG, 'description': 'old notes', 'assets': {'links': links}}

    def fail(self, stage):
        if not self.failed and self.failure == stage:
            self.failed = True
            raise RuntimeError('private-fixture-token must not be persisted')

    def request(self, client, method, url, **kwargs):
        self.calls.append((method, url))
        if '/repository/tags/' in url:
            self.assert_read_only(method)
            return Response({'commit': {'id': self.source}})
        if '/assets/links/' in url:
            if self.failed and self.block_rollback:
                raise RuntimeError('rollback unavailable')
            link = next(item for item in self.release['assets']['links'] if item['id'] == int(url.rsplit('/', 1)[1]))
            link['url'] = kwargs['json']['url']
            self.linked = True
            self.fail('link_' + link['name'])  # Fail after applying to test uncertain PUTs.
            return Response(link)
        if '/releases/' in url and '/downloads/' not in url:
            if method == 'PUT':
                if self.failed and self.block_rollback:
                    raise RuntimeError('rollback unavailable')
                self.release['description'] = kwargs['json']['description']
                self.fail('notes')
            elif method != 'GET':
                raise AssertionError('Replacement must not create/delete a release')
            return Response(self.release)
        if method == 'PUT':
            if client is not self.client:
                raise AssertionError('Upload requires API client')
            name = Path(kwargs['data'].name).name
            self.fail('upload_' + name)
            self.payloads[url] = kwargs['data'].read()
            self.names[url] = name
            return Response({})
        if method != 'GET':
            raise AssertionError('Unexpected mutation')
        direct = next((item for item in self.release['assets']['links'] if item['direct_asset_url'] == url), None)
        target = direct['url'] if direct else url
        if target not in self.names and kwargs.get('accepted_statuses') == (404,):
            return Response(status_code=404)
        name = self.names[target]
        stage = ('permalink_' if direct else 'public_' if client is self.public else 'verify_upload_') + name
        if not direct or self.linked:
            self.fail(stage)
        return Response(body=self.payloads[target])

    @staticmethod
    def assert_read_only(method):
        if method != 'GET':
            raise AssertionError('Tag must never move')


def make_bundle(root):
    for folder in ('dist', 'desktop/resources', 'packaging'):
        (root / folder).mkdir(parents=True)
    inventories = {}
    for name in ('desktop', 'build-tools'):
        file = root / f'packaging/{name}-windows-py311.inventory.json'
        file.write_bytes(b'{}')
        inventories[file.name] = sha(file.read_bytes())
    info = {'version': '2.0.0', 'core_version': '1.0.0', 'source_sha': 'a' * 40,
            'built_at_utc': '2026-10-21T00:00:00+00:00', 'dependency_inventory_sha256': inventories}
    (root / 'desktop/resources/release.json').write_text(json.dumps(info))
    exe = b'new-synthetic-not-executable'
    (root / 'dist' / EXE).write_bytes(exe)
    (root / 'dist' / CHECKSUM).write_bytes((sha(exe) + '  ' + EXE + '\n').encode())
    assets = {name: {'sha256': sha((root / 'dist' / name).read_bytes()), 'bytes': (root / 'dist' / name).stat().st_size} for name in ASSETS}
    (root / 'dist/release-manifest.json').write_text(json.dumps({**info, 'schema_version': 1, 'tag': TAG, 'assets': assets,
        'source_gate_sha256': 'c' * 64, 'bundle_audit_sha256': 'd' * 64, 'frozen_reports_sha256': ['e' * 64, 'f' * 64]}))


class ReleaseTransactionTests(unittest.TestCase):
    def test_release_cli_replace_routes_through_verified_transaction(self):
        from scripts import release_gitlab
        with temporary_directory() as directory:
            root = Path(directory)
            make_bundle(root)
            notes = root / 'notes.md'
            notes.write_text('new notes')
            fake = FakeGitLab()
            output = StringIO()
            with patch.object(release_gitlab, 'ROOT', root), patch.object(release_gitlab, 'API', API), patch.object(release_gitlab, 'session', return_value=fake.client), patch.object(release_gitlab.requests, 'Session', return_value=fake.public), patch.object(release_gitlab, 'request', side_effect=fake.request), patch('sys.argv', ['release_gitlab.py', 'replace', '--tag', TAG, '--notes', str(notes)]), redirect_stdout(output):
                release_gitlab.main()
            result = json.loads(output.getvalue())
            self.assertEqual(result['status'], 'VERIFIED')
            self.assertEqual(set(result['assets']), set(ASSETS))
            self.assertNotIn('private-fixture-token', output.getvalue())
            self.assertFalse(any(method == 'POST' for method, _ in fake.calls))

    def transaction(self, fake):
        return Replacement(fake.client, fake.public, fake.request, API)

    def test_success_preserves_ids_permalinks_tag_and_rerun_is_idempotent(self):
        with temporary_directory() as directory:
            root = Path(directory)
            make_bundle(root)
            fake = FakeGitLab()
            before = deepcopy(fake.release)
            result = self.transaction(fake).replace(root, TAG, 'new notes')
            self.assertEqual(result['status'], 'VERIFIED')
            for old, new in zip(before['assets']['links'], fake.release['assets']['links'], strict=True):
                self.assertEqual((old['id'], old['direct_asset_url']), (new['id'], new['direct_asset_url']))
            self.assertFalse(any(method == 'POST' or method != 'GET' and '/repository/tags/' in url for method, url in fake.calls))
            count = len([call for call in fake.calls if call[0] == 'PUT'])
            self.assertTrue(self.transaction(fake).replace(root, TAG, 'new notes')['already_current'])
            self.assertEqual(len([call for call in fake.calls if call[0] == 'PUT']), count)
            self.assertEqual(self.transaction(fake).verify(root, TAG)['status'], 'VERIFIED')
            state = (root / '.cache/release-recovery' / (TAG + '.json')).read_text()
            self.assertNotIn('private-fixture-token', state)

    def test_every_upload_link_notes_and_public_verification_failure_rolls_back(self):
        stages = ['upload_' + name for name in ASSETS] + ['verify_upload_' + name for name in ASSETS] + [
            'link_' + name for name in ASSETS] + ['notes'] + ['public_' + name for name in ASSETS] + ['permalink_' + name for name in ASSETS]
        for stage in stages:
            with self.subTest(stage=stage), temporary_directory() as directory:
                root = Path(directory)
                make_bundle(root)
                fake = FakeGitLab(stage)
                original = deepcopy(fake.release)
                with self.assertRaisesRegex(ReleaseError, 'ROLLED_BACK'):
                    self.transaction(fake).replace(root, TAG, 'new notes')
                self.assertEqual(fake.release, original)
                state = json.loads((root / '.cache/release-recovery' / (TAG + '.json')).read_text())
                self.assertEqual(state['status'], 'ROLLED_BACK')
                self.assertNotIn('private-fixture-token', json.dumps(state))
                self.assertFalse(any(method == 'POST' for method, _ in fake.calls))

    def test_recovery_is_durable_when_compensation_fails(self):
        with temporary_directory() as directory:
            root = Path(directory)
            make_bundle(root)
            fake = FakeGitLab('notes')
            fake.block_rollback = True
            original = deepcopy(fake.release)
            with self.assertRaisesRegex(ReleaseError, 'RECOVERY_REQUIRED'):
                self.transaction(fake).replace(root, TAG, 'new notes')
            path = root / '.cache/release-recovery' / (TAG + '.json')
            snapshot = json.loads(path.read_text())['snapshot']
            with self.assertRaisesRegex(ReleaseError, 'RECOVERY_REQUIRED'):
                self.transaction(fake).replace(root, TAG, 'different notes')
            self.assertEqual(json.loads(path.read_text())['snapshot'], snapshot)
            fake.block_rollback = False
            self.assertEqual(self.transaction(fake).recover(path)['status'], 'ROLLED_BACK')
            self.assertEqual(fake.release, original)

    def test_preflight_rejects_source_version_build_hash_and_checksum_before_upload(self):
        for variant in ('tag_source', 'version', 'source', 'checksum', 'asset', 'inventory'):
            with self.subTest(variant=variant), temporary_directory() as directory:
                root = Path(directory)
                make_bundle(root)
                fake = FakeGitLab()
                if variant == 'tag_source':
                    fake.source = 'b' * 40
                elif variant in {'version', 'source'}:
                    path = root / 'desktop/resources/release.json'
                    info = json.loads(path.read_text())
                    info['version' if variant == 'version' else 'source_sha'] = 'changed'
                    path.write_text(json.dumps(info))
                else:
                    path = root / ('packaging/desktop-windows-py311.inventory.json' if variant == 'inventory' else 'dist/' + (CHECKSUM if variant == 'checksum' else EXE))
                    path.write_bytes(b'corrupt')
                with self.assertRaises(ReleaseError):
                    self.transaction(fake).replace(root, TAG, 'new notes')
                self.assertFalse(any(method == 'PUT' for method, _ in fake.calls))

    def test_hash_mismatch_after_public_switch_rolls_back(self):
        with temporary_directory() as directory:
            root = Path(directory)
            make_bundle(root)
            fake = FakeGitLab()
            original = deepcopy(fake.release)
            request = fake.request
            corrupted = False
            def corrupt_public(client, method, url, **kwargs):
                nonlocal corrupted
                result = request(client, method, url, **kwargs)
                if client is fake.public and fake.linked and not corrupted and '/downloads/' in url:
                    corrupted = True
                    return Response(body=b'mismatch')
                return result
            transaction = Replacement(fake.client, fake.public, corrupt_public, API)
            with self.assertRaisesRegex(ReleaseError, 'ROLLED_BACK'):
                transaction.replace(root, TAG, 'new notes')
            self.assertEqual(fake.release, original)

    def test_unexpected_concurrent_change_is_preserved_for_manual_recovery(self):
        with temporary_directory() as directory:
            root = Path(directory)
            make_bundle(root)
            fake = FakeGitLab('notes')
            original_request = fake.request
            def concurrent(client, method, url, **kwargs):
                try:
                    return original_request(client, method, url, **kwargs)
                except RuntimeError:
                    fake.release['description'] = 'another operator update'
                    raise
            transaction = Replacement(fake.client, fake.public, concurrent, API)
            with self.assertRaisesRegex(ReleaseError, 'RECOVERY_REQUIRED'):
                transaction.replace(root, TAG, 'new notes')
            self.assertEqual(fake.release['description'], 'another operator update')

    def test_urls_with_credentials_or_queries_are_rejected_without_mutation(self):
        with temporary_directory() as directory:
            root = Path(directory)
            make_bundle(root)
            for url in ('https://gitlab.com/file?token=private-fixture-token', 'https://user:secret@gitlab.com/file', 'https://other.test/file'):
                fake = FakeGitLab()
                fake.release['assets']['links'][0]['url'] = url
                with self.assertRaisesRegex(ReleaseError, 'URL_UNSAFE'):
                    self.transaction(fake).replace(root, TAG, 'notes')
                self.assertFalse(any(method == 'PUT' for method, _ in fake.calls))

    def test_crash_after_final_verification_can_resume_without_mutating_links(self):
        with temporary_directory() as directory:
            root = Path(directory)
            make_bundle(root)
            fake = FakeGitLab()
            transaction = self.transaction(fake)
            transaction.replace(root, TAG, 'new notes')
            path = root / '.cache/release-recovery' / (TAG + '.json')
            state = json.loads(path.read_text())
            state['status'] = 'UPLOADS_VERIFIED'  # Simulate exit before writing the final receipt.
            path.write_text(json.dumps(state))
            writes = sum(method == 'PUT' for method, _ in fake.calls)
            self.assertTrue(transaction.replace(root, TAG, 'new notes')['already_current'])
            self.assertEqual(json.loads(path.read_text())['status'], 'VERIFIED')
            self.assertEqual(writes, sum(method == 'PUT' for method, _ in fake.calls))

    def test_retry_after_second_upload_failure_reuses_the_verified_first_package(self):
        with temporary_directory() as directory:
            root = Path(directory)
            make_bundle(root)
            fake = FakeGitLab('upload_' + CHECKSUM)
            transaction = self.transaction(fake)
            with self.assertRaisesRegex(ReleaseError, 'ROLLED_BACK'):
                transaction.replace(root, TAG, 'new notes')
            first_uploads = [url for method, url in fake.calls if method == 'PUT' and '/packages/' in url and url.endswith('.exe')]
            self.assertEqual(len(first_uploads), 1)
            transaction.replace(root, TAG, 'new notes')
            self.assertEqual([url for method, url in fake.calls if method == 'PUT' and '/packages/' in url and url.endswith('.exe')], first_uploads)

    def test_checksum_semantics_and_missing_gate_receipts_fail_preflight(self):
        for variant in ('checksum_semantics', 'gate_receipt'):
            with self.subTest(variant=variant), temporary_directory() as directory:
                root = Path(directory)
                make_bundle(root)
                path = root / 'dist/release-manifest.json'
                manifest = json.loads(path.read_text())
                if variant == 'checksum_semantics':
                    checksum = root / 'dist' / CHECKSUM
                    checksum.write_text('0' * 64 + '  ' + EXE + '\n')
                    manifest['assets'][CHECKSUM] = {'sha256': sha(checksum.read_bytes()), 'bytes': checksum.stat().st_size}
                else:
                    manifest.pop('source_gate_sha256')
                path.write_text(json.dumps(manifest))
                with self.assertRaises(ReleaseError):
                    load_bundle(root, TAG)

