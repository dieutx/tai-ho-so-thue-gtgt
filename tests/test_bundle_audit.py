"""A missing/corrupt classifier must fail the release audit, not just be counted."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.support import cleanup_temporary_directory


@unittest.skipUnless(importlib.util.find_spec('PyInstaller'), 'Release tooling is optional')
class BundleAuditTests(unittest.TestCase):
    def test_incomplete_or_changed_ocr_bundle_is_rejected(self):
        from scripts.audit_bundle import audit_ocr
        modules = {'gdt_tax.captcha.ddddocr_solver', 'ddddocr', 'ddddocr.compat.v1',
                   'ddddocr.core.ocr_engine', 'ddddocr.models.model_loader',
                   'ddddocr.models.charset_manager', 'PIL.Image',
                   'onnxruntime.capi.onnxruntime_inference_collection'}
        entries = {'ddddocr/common_old.onnx': b'expected-model',
                   'onnxruntime/capi/onnxruntime.dll': b'',
                   'onnxruntime/capi/onnxruntime_providers_shared.dll': b'',
                   'onnxruntime/capi/onnxruntime_pybind11_state.pyd': b''}
        temp = tempfile.TemporaryDirectory()
        try:
            model = Path(temp.name) / 'common_old.onnx'
            model.write_bytes(b'expected-model')
            def check(files, python_modules):
                archive = SimpleNamespace(toc=files, extract=files.__getitem__)
                return audit_ocr(archive, python_modules, model)
            self.assertTrue(check(entries, modules)['pass'])
            for omitted in entries:
                with self.subTest(missing=omitted):
                    result = check({k: v for k, v in entries.items() if k != omitted}, modules)
                    self.assertFalse(result['pass'])
                    self.assertIn(omitted, result['missing_files'])
            corrupted = {**entries, 'ddddocr/common_old.onnx': b'wrong-model'}
            self.assertFalse(check(corrupted, modules)['model_matches_source'])
            missing_charset = check(entries, modules - {'ddddocr.models.charset_manager'})
            self.assertFalse(missing_charset['pass'])
            self.assertIn('ddddocr.models.charset_manager', missing_charset['missing_modules'])
        finally:
            cleanup_temporary_directory(temp)
