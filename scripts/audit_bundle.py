"""Inspect allowlisted frozen contents and compare local secrets without printing them."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import marshal
import re
import tempfile
from pathlib import Path

from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader

from gdt_tax.config import load_env_file
from gdt_tax.proxy import parse_proxy


def audit_ocr(archive, modules: set[str], source_model: Path) -> dict:
    """Gate the exact classifier used by the desktop, including its charset code."""
    entries = {name.replace('\\', '/'): name for name in archive.toc}
    model = 'ddddocr/common_old.onnx'
    required = {
        model,
        'onnxruntime/capi/onnxruntime.dll',
        'onnxruntime/capi/onnxruntime_providers_shared.dll',
        'onnxruntime/capi/onnxruntime_pybind11_state.pyd',
    }
    required_modules = {
        'gdt_tax.captcha.ddddocr_solver', 'ddddocr', 'ddddocr.compat.v1',
        'ddddocr.core.ocr_engine', 'ddddocr.models.model_loader',
        'ddddocr.models.charset_manager', 'PIL.Image',
        'onnxruntime.capi.onnxruntime_inference_collection',
    }
    bundled_hash = hashlib.sha256(archive.extract(entries[model])).hexdigest() if model in entries else ''
    source_hash = hashlib.sha256(source_model.read_bytes()).hexdigest()
    missing = sorted(required - entries.keys())
    missing_modules = sorted(required_modules - modules)
    matches = bundled_hash == source_hash
    return {'pass': not missing and not missing_modules and matches,
            'model': model, 'model_sha256': bundled_hash, 'source_model_sha256': source_hash,
            'model_matches_source': matches, 'missing_files': missing, 'missing_modules': missing_modules}


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
    modules: set[str] = set()
    with tempfile.TemporaryDirectory(dir=root / ".cache") as temp:
        for name in names:
            if name.endswith(".pyz"):
                path = Path(temp) / "audit.pyz"
                path.write_bytes(archive.extract(name))
                pyz = ZlibArchiveReader(str(path))
                modules.update(pyz.toc)
                for module in pyz.toc:
                    if module == "tests" or module.startswith("tests."):
                        forbidden.append(module)
                    payload = marshal.dumps(pyz.extract(module))
                    leaks += int(any(secret in payload for secret in secrets))
            elif name.endswith((".json", ".md", ".txt", ".py", ".yaml", ".ps1")):
                payload = archive.extract(name)
                leaks += int(any(secret in payload for secret in secrets))
    spec = importlib.util.find_spec('ddddocr')
    if spec is None or spec.origin is None:
        raise RuntimeError('Build runtime is missing ddddocr')
    ocr = audit_ocr(archive, modules, Path(spec.origin).parent / 'common_old.onnx')
    report = {
        "pass": not forbidden and leaks == 0 and ocr['pass'],
        "archive_entries": len(names), "forbidden_entries": len(forbidden),
        "secret_matches": leaks,
        "qt_windows_plugin": any("qwindows.dll" in n for n in names),
        "form_mapping_json": len([n for n in names if "form_mappings" in n and n.endswith(".json")]),
        "bundled_ocr_models": len([n for n in names if n.endswith(".onnx")]),
        "ocr": ocr,
    }
    report['pass'] = report['pass'] and report['qt_windows_plugin'] and report['form_mapping_json'] > 0
    (root / ".cache/bundle-audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
