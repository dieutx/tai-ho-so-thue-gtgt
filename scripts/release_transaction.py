"""Verified release replacement with durable compensating recovery, no tag mutation."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import quote, urlsplit

EXE = 'TaiHoSoThue-Windows.exe'
CHECKSUM = 'SHA256SUMS.txt'
ASSETS = (EXE, CHECKSUM)
MAX_ASSET = 2 * 1024 * 1024 * 1024


class ReleaseError(RuntimeError):
    pass


def digest(path):
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(block)
    return sha.hexdigest()


def write_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(json.dumps(state, indent=2).encode('utf-8'))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def safe_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.hostname != 'gitlab.com' or parsed.port not in {None, 443}
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ReleaseError('RELEASE_URL_UNSAFE')
    return url


def checksum_matches(data, expected):
    try:
        fields = data.decode('ascii').split()
        return len(fields) == 2 and fields[0].lower() == expected and fields[1].lstrip('*') == EXE
    except UnicodeDecodeError:
        return False


def load_bundle(root, tag):
    if not re.fullmatch(r'desktop-v\d+\.\d+\.\d+', tag):
        raise ReleaseError('RELEASE_TAG_INVALID')
    info = json.loads((root / 'desktop/resources/release.json').read_text(encoding='utf-8'))
    manifest = json.loads((root / 'dist/release-manifest.json').read_text(encoding='utf-8'))
    if not isinstance(info, dict) or not isinstance(manifest, dict) or not isinstance(manifest.get('assets'), dict):
        raise ReleaseError('RELEASE_MANIFEST_INVALID')
    if manifest.get('schema_version') != 1 or manifest.get('tag') != tag or tag != 'desktop-v' + info['version']:
        raise ReleaseError('RELEASE_VERSION_TAG_MISMATCH')
    for field in ('version', 'core_version', 'source_sha', 'built_at_utc', 'dependency_inventory_sha256'):
        if not info.get(field) or info[field] != manifest.get(field):
            raise ReleaseError('RELEASE_BUILD_PROVENANCE_MISMATCH')
    if not re.fullmatch(r'[0-9a-f]{40}', info['source_sha']):
        raise ReleaseError('RELEASE_SOURCE_SHA_INVALID')
    hashes = [manifest.get('source_gate_sha256'), manifest.get('bundle_audit_sha256'),
              *(manifest.get('frozen_reports_sha256') or [])]
    if len(hashes) != 4 or any(not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value) for value in hashes):
        raise ReleaseError('RELEASE_GATE_EVIDENCE_MISSING')
    if set(manifest['assets']) != set(ASSETS):
        raise ReleaseError('RELEASE_ASSET_SET_MISMATCH')
    for name in ASSETS:
        path = root / 'dist' / name
        item = manifest['assets'][name]
        if not 0 < path.stat().st_size <= MAX_ASSET or item != {'sha256': digest(path), 'bytes': path.stat().st_size}:
            raise ReleaseError('RELEASE_LOCAL_ASSET_MISMATCH')
    if (root / 'dist' / CHECKSUM).stat().st_size > 4096 or not checksum_matches((root / 'dist' / CHECKSUM).read_bytes(), manifest['assets'][EXE]['sha256']):
        raise ReleaseError('RELEASE_CHECKSUM_MISMATCH')
    for name, expected in info['dependency_inventory_sha256'].items():
        if Path(name).name != name or digest(root / 'packaging' / name) != expected:
            raise ReleaseError('RELEASE_INVENTORY_MISMATCH')
    return manifest


def download_evidence(client, request, url, expected=None, *, capture=False, missing_ok=False):
    response = request(client, 'GET', safe_url(url), stream=True, accepted_statuses=(404,) if missing_ok else ())
    if missing_ok and response.status_code == 404:
        response.close()
        return None, b''
    sha, size, chunks = hashlib.sha256(), 0, []
    limit = 4096 if capture else min(MAX_ASSET, expected['bytes'] if expected else MAX_ASSET)
    try:
        for block in response.iter_content(1024 * 1024):
            size += len(block)
            if size > limit:
                raise ReleaseError('RELEASE_DOWNLOAD_SIZE_MISMATCH')
            sha.update(block)
            if capture:
                chunks.append(block)
    finally:
        response.close()
    observed = {'sha256': sha.hexdigest(), 'bytes': size}
    if expected is not None and observed != expected:
        raise ReleaseError('RELEASE_DOWNLOAD_HASH_MISMATCH')
    return observed, b''.join(chunks)


class Replacement:
    def __init__(self, client, public_client, request, api):
        self.client, self.public, self.request, self.api = client, public_client, request, api

    def json(self, method, path, **kwargs):
        return self.request(self.client, method, self.api + path, **kwargs).json()

    def current(self, tag):
        release = self.json('GET', '/releases/' + quote(tag, safe=''))
        revision = self.json('GET', '/repository/tags/' + quote(tag, safe=''))['commit']['id']
        selected = {}
        for name in ASSETS:
            matches = [item for item in release['assets']['links'] if item['name'] == name]
            if len(matches) != 1 or type(matches[0]['id']) is not int or matches[0]['id'] <= 0:
                raise ReleaseError('RELEASE_LINK_IDS_INVALID')
            item = matches[0]
            selected[name] = {'id': item['id'], 'name': name, 'url': safe_url(item['url']),
                'direct_asset_url': safe_url(item['direct_asset_url']), 'link_type': item.get('link_type', 'package')}
        if release['tag_name'] != tag:
            raise ReleaseError('RELEASE_TAG_CHANGED')
        if len({item['id'] for item in selected.values()}) != len(ASSETS):
            raise ReleaseError('RELEASE_LINK_IDS_INVALID')
        return {'tag': tag, 'source_sha': revision, 'description': release['description'], 'links': selected}

    def verify_state(self, snapshot):
        current = self.current(snapshot['tag'])
        if current != {key: snapshot[key] for key in ('tag', 'source_sha', 'description', 'links')}:
            raise ReleaseError('RELEASE_STATE_CHANGED')
        for name in ASSETS:
            download_evidence(self.public, self.request, current['links'][name]['direct_asset_url'], snapshot['assets'][name])

    def link_payload(self, link, url):
        return {'name': link['name'], 'url': safe_url(url), 'direct_asset_path': '/' + link['name'], 'link_type': link['link_type']}

    def put_link(self, tag, link, url):
        self.json('PUT', '/releases/' + quote(tag, safe='') + '/assets/links/' + str(link['id']),
                  json=self.link_payload(link, url))

    def restore(self, state, path):
        old = state['snapshot']
        try:
            current = self.current(old['tag'])
            if current['source_sha'] != old['source_sha'] or current['description'] not in {old['description'], state['new_description']}:
                raise ReleaseError('RELEASE_CONCURRENT_CHANGE')
            for name in ASSETS:
                actual, previous = current['links'][name], old['links'][name]
                if actual['id'] != previous['id'] or actual['direct_asset_url'] != previous['direct_asset_url'] or actual['url'] not in {previous['url'], state['new_urls'][name]}:
                    raise ReleaseError('RELEASE_CONCURRENT_CHANGE')
            # Attempt all compensations even if an individual response fails.
            for name in ASSETS:
                try:
                    self.put_link(old['tag'], old['links'][name], old['links'][name]['url'])
                except (Exception, SystemExit):
                    pass
            try:
                self.json('PUT', '/releases/' + quote(old['tag'], safe=''), json={'description': old['description']})
            except (Exception, SystemExit):
                pass
            self.verify_state(old)
            state['status'] = 'ROLLED_BACK'
        except (Exception, SystemExit):
            state['status'] = 'RECOVERY_REQUIRED'
        write_state(path, state)
        return state['status']

    def replace(self, root, tag, description):
        bundle = load_bundle(root, tag)
        old = self.current(tag)
        if old['source_sha'] != bundle['source_sha']:
            raise ReleaseError('RELEASE_TAG_SOURCE_MISMATCH')
        path = root / '.cache/release-recovery' / (tag + '.json')
        if path.exists():
            prior = json.loads(path.read_text(encoding='utf-8'))
            if prior.get('status') not in {'VERIFIED', 'ROLLED_BACK'}:
                if (prior.get('assets') == bundle['assets'] and prior.get('new_description') == description
                        and old['description'] == description
                        and all(old['links'][name]['url'] == prior.get('new_urls', {}).get(name) for name in ASSETS)):
                    self.verify(root, tag)
                    prior['status'] = 'VERIFIED'
                    write_state(path, prior)
                    return {'status': 'VERIFIED', 'tag': tag, 'assets': bundle['assets'], 'already_current': True}
                raise ReleaseError('RELEASE_RECOVERY_REQUIRED: ' + str(path))
        old['assets'] = {}
        for name in ASSETS:
            item, content = download_evidence(self.public, self.request, old['links'][name]['direct_asset_url'], capture=name == CHECKSUM)
            old['assets'][name] = item
            if name == CHECKSUM and not checksum_matches(content, old['assets'][EXE]['sha256']):
                raise ReleaseError('RELEASE_EXISTING_CHECKSUM_MISMATCH')
        package = self.api + '/packages/generic/tai-ho-so-thue-windows/' + quote(bundle['version'], safe='') + '/'
        urls = {name: package + Path(name).stem + '-' + bundle['assets'][name]['sha256'] + Path(name).suffix for name in ASSETS}
        if all(old['links'][name]['url'] == urls[name] and old['assets'][name] == bundle['assets'][name] for name in ASSETS) and old['description'] == description:
            return {'status': 'VERIFIED', 'tag': tag, 'source_sha': bundle['source_sha'], 'assets': bundle['assets'], 'already_current': True}
        state = {'schema_version': 1, 'status': 'PREPARED', 'snapshot': old,
                 'new_description': description, 'new_urls': urls, 'assets': bundle['assets']}
        write_state(path, state)
        mutated = False
        try:
            for name in ASSETS:
                existing, _ = download_evidence(self.client, self.request, urls[name], bundle['assets'][name], missing_ok=True)
                if existing is None:
                    with (root / 'dist' / name).open('rb') as stream:
                        self.request(self.client, 'PUT', urls[name], data=stream, headers={'Content-Type': 'application/octet-stream'})
                    download_evidence(self.client, self.request, urls[name], bundle['assets'][name])
            state['status'] = 'UPLOADS_VERIFIED'
            write_state(path, state)
            # Recheck the snapshot before the first mutable link update.
            if self.current(tag) != {key: old[key] for key in ('tag', 'source_sha', 'description', 'links')}:
                raise ReleaseError('RELEASE_CONCURRENT_CHANGE')
            for name in reversed(ASSETS):
                mutated = True  # A timeout can occur after the server applied a PUT.
                self.put_link(tag, old['links'][name], urls[name])
            self.json('PUT', '/releases/' + quote(tag, safe=''), json={'description': description})
            current = self.current(tag)
            if current['source_sha'] != old['source_sha'] or current['description'] != description:
                raise ReleaseError('RELEASE_FINAL_STATE_MISMATCH')
            for name in ASSETS:
                link = current['links'][name]
                if link['id'] != old['links'][name]['id'] or link['direct_asset_url'] != old['links'][name]['direct_asset_url'] or link['url'] != urls[name]:
                    raise ReleaseError('RELEASE_FINAL_LINK_MISMATCH')
                # Verify both immutable public package and stable permalink paths.
                download_evidence(self.public, self.request, urls[name], bundle['assets'][name])
                download_evidence(self.public, self.request, link['direct_asset_url'], bundle['assets'][name])
            state['status'] = 'VERIFIED'
            write_state(path, state)
            return {'status': 'VERIFIED', 'tag': tag, 'source_sha': bundle['source_sha'],
                    'assets': bundle['assets'], 'recovery_file': str(path), 'already_current': False}
        except (Exception, SystemExit) as error:
            state['failure_type'] = type(error).__name__  # Never persist an exception/token/body.
            if mutated:
                status = self.restore(state, path)
            else:
                try:
                    self.verify_state(old)
                    state['status'] = 'ROLLED_BACK'
                except (Exception, SystemExit):
                    state['status'] = 'RECOVERY_REQUIRED'
                write_state(path, state)
                status = state['status']
            raise ReleaseError('RELEASE_REPLACE_FAILED: ' + status + '; recovery=' + str(path)) from None

    def recover(self, path):
        state = json.loads(path.read_text(encoding='utf-8'))
        if state.get('schema_version') != 1 or not re.fullmatch(r'desktop-v\d+\.\d+\.\d+', state['snapshot']['tag']):
            raise ReleaseError('RELEASE_RECOVERY_INVALID')
        for name in ASSETS:
            safe_url(state['snapshot']['links'][name]['url'])
            safe_url(state['new_urls'][name])
        status = self.restore(state, path)
        if status != 'ROLLED_BACK':
            raise ReleaseError('RELEASE_RECOVERY_REQUIRED')
        return {'status': status, 'tag': state['snapshot']['tag'], 'recovery_file': str(path)}

    def verify(self, root, tag):
        bundle = load_bundle(root, tag)
        current = self.current(tag)
        if current['source_sha'] != bundle['source_sha']:
            raise ReleaseError('RELEASE_TAG_SOURCE_MISMATCH')
        for name in ASSETS:
            for url in (current['links'][name]['url'], current['links'][name]['direct_asset_url']):
                download_evidence(self.public, self.request, url, bundle['assets'][name])
        return {'status': 'VERIFIED', 'tag': tag, 'source_sha': bundle['source_sha'], 'assets': bundle['assets']}
