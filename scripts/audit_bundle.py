"""Inspect allowlisted frozen contents and compare local secrets without printing them."""
from __future__ import annotations

import json
import marshal
import re
import tempfile
from pathlib import Path

from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader

from gdt_tax.config import load_env_file
from gdt_tax.proxy import parse_proxy


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    archive = CArchiveReader(str(root / "dist/TaiHoSoThue-Windows.exe"))
    names = list(archive.toc)
    forbidden = [n for n in names if re.search(r"(^|[/\\])(\.env|\.git|download|logs|tests)([/\\]|$)", n)]
    source = load_env_file(root / ".env")
    values = [source.get(key, "") for key in ["GDT_USERNAME", "GDT_PASSWORD", "GDT_PROXY_URL"]]
    proxy = parse_proxy(source.get("GDT_PROXY_URL", ""))
    if proxy:
        values.extend(proxy.secrets())
    secrets = [v.encode("utf-8") for v in values if len(v) >= 5]
    leaks = 0
    with tempfile.TemporaryDirectory(dir=root / ".cache") as temp:
        for name in names:
            if name.endswith(".pyz"):
                path = Path(temp) / "audit.pyz"
                path.write_bytes(archive.extract(name))
                pyz = ZlibArchiveReader(str(path))
                for module in pyz.toc:
                    if module == "tests" or module.startswith("tests."):
                        forbidden.append(module)
                    payload = marshal.dumps(pyz.extract(module))
                    leaks += int(any(secret in payload for secret in secrets))
            elif name.endswith((".json", ".md", ".txt", ".py", ".yaml", ".ps1")):
                payload = archive.extract(name)
                leaks += int(any(secret in payload for secret in secrets))
    report = {
        "pass": not forbidden and leaks == 0,
        "archive_entries": len(names), "forbidden_entries": len(forbidden),
        "secret_matches": leaks,
        "qt_windows_plugin": any("qwindows.dll" in n for n in names),
        "form_mapping_json": len([n for n in names if "form_mappings" in n and n.endswith(".json")]),
        "bundled_ocr_models": len([n for n in names if n.endswith(".onnx")]),
    }
    (root / ".cache/bundle-audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
