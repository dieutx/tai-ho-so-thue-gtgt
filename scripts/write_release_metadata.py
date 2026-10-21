"""Generate deterministic version fields and an actual build timestamp."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from desktop import __version__
from gdt_tax import __version__ as core_version


def write_metadata(root: Path, source_sha: str):
    if not re.fullmatch(r'[0-9a-f]{40}', source_sha):
        raise ValueError('BUILD_SOURCE_SHA_INVALID')
    parts = tuple(int(x) for x in __version__.split('.')) + (0,)
    dot = '.'.join(str(x) for x in parts)
    version = f'''VSVersionInfo(ffi=FixedFileInfo(filevers={parts}, prodvers={parts}, mask=0x3f,
     flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0,0)),
     kids=[StringFileInfo([StringTable('040904B0',[
     StringStruct('CompanyName','TaiHoSoThue'),
     StringStruct('FileDescription','Tai Ho So Thue - Windows Desktop Full'),
     StringStruct('FileVersion','{dot}'),
     StringStruct('OriginalFilename','TaiHoSoThue-Windows.exe'),
     StringStruct('ProductName','Tai Ho So Thue'),
     StringStruct('ProductVersion','{__version__}')])]),
     VarFileInfo([VarStruct('Translation',[1033,1200])])])
    '''
    (root / 'packaging/version.txt').write_text(version.strip() + '\n', encoding='utf-8')
    (root / 'desktop/resources/release.json').write_text(json.dumps({
        'version': __version__, 'built_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'published': False, 'profile': 'Full / CPU OCR',
        'core_version': core_version, 'source_sha': source_sha,
        'dependency_inventory_sha256': {name: hashlib.sha256((root / 'packaging' / name).read_bytes()).hexdigest()
            for name in ('desktop-windows-py311.inventory.json', 'build-tools-windows-py311.inventory.json')},
    }, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    root = Path(__file__).resolve().parents[1]
    sha = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    if os.environ.get('CI_COMMIT_SHA', sha) != sha:
        raise SystemExit('BUILD_CI_SOURCE_MISMATCH')
    changes = subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain', '--untracked-files=no'], text=True)
    generated = {'desktop/resources/release.json', 'packaging/version.txt'}
    if any(line[3:].replace('\\', '/') not in generated for line in changes.splitlines()):
        raise SystemExit('BUILD_SOURCE_DIRTY')
    write_metadata(root, sha)


if __name__ == '__main__':
    main()
