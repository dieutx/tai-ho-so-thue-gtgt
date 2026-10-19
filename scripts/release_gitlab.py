"""Release helper: credentials stay in memory and never enter URLs or output."""
import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from urllib.parse import quote

import requests
from gitlab_credential import read_token

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'dieutx/tai-ho-so-thue-gtgt'
API = 'https://gitlab.com/api/v4/projects/' + quote(PROJECT, safe='')


def session():
    token_file = ROOT / '.cache/gitlab-release-token.txt'
    token = token_file.read_text(encoding='utf-8-sig').strip() if token_file.exists() else None
    token = token or read_token() or next((os.environ[key] for key in ('GITLAB_TOKEN', 'GITLAB_ACCESS_TOKEN', 'GLAB_TOKEN') if os.environ.get(key)), None)
    if not token:
        result = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=gitlab.com\npath=' + PROJECT + '.git\n\n', text=True, capture_output=True, env=dict(os.environ, GIT_TERMINAL_PROMPT='0'), timeout=30)
        credential = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
        token = credential.get('password')
    if not token:
        raise SystemExit('No existing GitLab credential available')
    client = requests.Session()
    client.headers['PRIVATE-TOKEN'] = token
    probe = client.get(API, timeout=20)
    if probe.status_code == 401:
        del client.headers['PRIVATE-TOKEN']
        client.headers['Authorization'] = 'Bearer ' + token
    return client


def request(client, method, url, **kwargs):
    response = client.request(method, url, timeout=(20, 300), **kwargs)
    if not response.ok:
        raise SystemExit(f'GitLab {method} failed: HTTP {response.status_code}')
    return response


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['check', 'publish', 'verify'])
    version_info = json.loads((ROOT / 'desktop/resources/release.json').read_text(encoding='utf-8'))
    parser.add_argument('--tag', default='desktop-v' + version_info['version'])
    parser.add_argument('--notes', type=Path)
    args = parser.parse_args()
    client = session()
    if args.action == 'check':
        project = request(client, 'GET', API).json()
        releases = request(client, 'GET', API + '/releases').json()
        print(json.dumps({'project': project['path_with_namespace'], 'visibility': project['visibility'], 'permissions': project.get('permissions'), 'releases': [item['tag_name'] for item in releases]}, indent=2))
        return
    tag = args.tag
    version = tag.removeprefix('desktop-v').removeprefix('v')
    exe = ROOT / 'dist/TaiHoSoThue-Windows.exe'
    digest = hashlib.sha256(exe.read_bytes()).hexdigest()
    files = [exe, ROOT / 'dist/SHA256SUMS.txt']
    package_url = API + '/packages/generic/tai-ho-so-thue-windows/' + quote(version, safe='') + '/'
    if args.action == 'publish':
        if not args.notes:
            raise SystemExit('publish requires --notes FILE')
        if files[1].read_text(encoding='ascii').split()[0].lower() != digest:
            raise SystemExit('SHA256SUMS.txt does not match EXE')
        links = []
        for path in files:
            with path.open('rb') as stream:
                request(client, 'PUT', package_url + path.name, data=stream, headers={'Content-Type': 'application/octet-stream'})
            links.append({'name': path.name, 'url': package_url + path.name, 'direct_asset_path': '/' + path.name, 'link_type': 'package'})
        description = args.notes.read_text(encoding='utf-8')
        request(client, 'POST', API + '/releases', json={'name': 'Tải Hồ Sơ Thuế ' + version + ' — Windows', 'tag_name': tag, 'description': description, 'assets': {'links': links}})
    release = request(client, 'GET', API + '/releases/' + tag).json()
    link = next(item for item in release['assets']['links'] if item['name'] == exe.name)
    response = request(requests.Session(), 'GET', link['direct_asset_url'], stream=True)
    actual = hashlib.sha256()
    length = 0
    for block in response.iter_content(1024 * 1024):
        actual.update(block)
        length += len(block)
    if actual.hexdigest() != digest or length != exe.stat().st_size:
        raise SystemExit('Published file hash/size mismatch')
    result = {'tag': tag, 'release_url': release['_links']['self'], 'download_url': link['direct_asset_url'], 'bytes': length, 'sha256': digest, 'download_verified': True}
    (ROOT / '.cache/optimization/gitlab-published.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
