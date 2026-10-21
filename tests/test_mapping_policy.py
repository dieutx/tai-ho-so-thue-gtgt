"""Mapping configurations must not silently overwrite or guess numeric values."""
from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path

from lxml import etree

from gdt_tax.parser.extract import extract_declaration
from gdt_tax.parser.registry import FormMapping, MappingError, MappingRegistry, load_registry
from gdt_tax.parser.xml_reader import normalize_number
from tests.test_parser import RETURN_XML, registry_with_gtgt


class NumberPolicyTests(unittest.TestCase):
    def test_explicit_decimal_and_locales(self):
        for raw, policy, expected in [('0.125','xml_decimal','0.125'), ('1.234','xml_decimal','1.234'),
                                      ('1.234','vi','1234'), ('1,234.56','en','1234.56'),
                                      ('-1.234,56','vi','-1234.56')]:
            with self.subTest(raw=raw,policy=policy):
                self.assertEqual(normalize_number(raw,policy),(expected,None))

    def test_ambiguous_and_bad_grouping_are_not_guessed(self):
        self.assertEqual(normalize_number('1.234'),(None,'AMBIGUOUS_NUMBER_FORMAT'))
        for raw, policy in [('12.34.56','auto'),('1,23,456','en'),('1.23,456','vi'),('1,234','xml_decimal')]:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_number(raw,policy),(None,'PARSE_VALUE_ERROR'))

    def test_mapping_decimal_format_reaches_extractor(self):
        registry = registry_with_gtgt()
        mapping = registry.lookup('842','2.8.3')
        mapping.fields['vat_payable'] = replace(mapping.fields['vat_payable'],numeric_format='xml_decimal')
        parsed = extract_declaration(RETURN_XML.replace(b'<ct43>-100</ct43>',b'<ct43>0.125</ct43>'),registry=registry)
        self.assertEqual(parsed.indicator('ct43').value,'0.125')


class RegistryPolicyTests(unittest.TestCase):
    def test_duplicate_requires_explicit_override_and_audit(self):
        registry = MappingRegistry()
        first = FormMapping('first','1','842','2.8.3')
        registry.add(first)
        with self.assertRaises(MappingError):
            registry.add(replace(first,mapping_id='second'))
        registry.add(replace(first,mapping_id='second'),replace=True)
        self.assertEqual(registry.overrides,[{'previous':'first','replacement':'second'}])

    def test_invalid_shapes_types_paths_and_dates_are_controlled(self):
        valid = {'mapping_id':'fixture','mapping_version':'1','form_code':'842',
                 'fields':{'value':{'indicator_code':'ct43'}}}
        invalid = [{'fields':['wrong']}, {'fields':{'value':{'indicator_code':'ct43','datatype':[]}}},
                   {'fields':{'value':{'indicator_code':'ct43','xpath':'a/../../b'}}},
                   {'detect':[]}, {'effective_from':'not-a-date'}, {'supported_versions':123}]
        for fragment in invalid:
            with self.subTest(fragment=fragment), tempfile.TemporaryDirectory() as directory:
                (Path(directory)/'mapping.json').write_text(json.dumps({**valid,**fragment}),encoding='utf8')
                with self.assertRaises(MappingError):
                    load_registry(directory,strict=True)
                registry = load_registry(directory,strict=False)
                self.assertEqual(len(registry),0)
                self.assertTrue(registry.diagnostics)

    def test_packaged_unknown_version_is_not_implicitly_mapped(self):
        registry = load_registry()
        self.assertIsNone(registry.lookup('842','9.9.9'))
        self.assertEqual(extract_declaration(RETURN_XML.replace(b'2.8.3',b'9.9.9'),registry=registry).status,'NEED_MAPPING')

    def test_unknown_namespace_does_not_use_registered_mapping(self):
        xml = RETURN_XML.replace(b'http://kekhaithue.gdt.gov.vn/TKhaiThue',b'urn:unverified')
        parsed = extract_declaration(xml,registry=load_registry())
        self.assertEqual(parsed.status,'NEED_MAPPING')
        self.assertIn('MAPPING_DOCUMENT_OR_DATE_MISMATCH',parsed.warnings)

    def test_effective_dates_require_known_period_and_correct_namespace(self):
        mapping = FormMapping('fixture','1','842',effective_from='2025-01-01',effective_to='2025-12-31',
                              detect_root='r',detect_namespace='urn:fixture')
        root = etree.fromstring(b'<r xmlns="urn:fixture"/>')
        self.assertFalse(mapping.matches_document(root))
        self.assertTrue(mapping.matches_document(root,date(2025,6,1)))
        self.assertFalse(mapping.matches_document(root,date(2026,1,1)))

    def test_mapping_hash_is_path_independent_and_tracks_policy(self):
        mapping = registry_with_gtgt().lookup('842','2.8.3')
        self.assertEqual(mapping.fingerprint,replace(mapping,source_path='other').fingerprint)
        self.assertNotEqual(mapping.fingerprint,replace(mapping,mapping_version='changed').fingerprint)

    def test_missing_required_indicator_marks_extraction_partial(self):
        registry = registry_with_gtgt()
        mapping = registry.lookup('842','2.8.3')
        mapping.fields['vat_payable'] = replace(mapping.fields['vat_payable'],required=True)
        parsed = extract_declaration(RETURN_XML.replace(b'<ct43>-100</ct43>',b''),registry=registry)
        self.assertEqual(parsed.status,'MAPPED')
        self.assertEqual(parsed.validation_status,'PARTIAL')
        self.assertFalse(parsed.extraction_complete)
        self.assertIn('EXTRACTION_INCOMPLETE',parsed.warnings)
