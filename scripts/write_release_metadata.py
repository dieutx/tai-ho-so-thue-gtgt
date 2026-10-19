"""Generate deterministic version fields and an actual build timestamp."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from desktop import __version__

root = Path(__file__).resolve().parents[1]
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
(root / 'packaging/version.txt').write_text(version, encoding='utf-8')
(root / 'desktop/resources/release.json').write_text(json.dumps({
    'version': __version__, 'built_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    'published': False, 'profile': 'Full / CPU OCR',
}, ensure_ascii=False, indent=2), encoding='utf-8')
