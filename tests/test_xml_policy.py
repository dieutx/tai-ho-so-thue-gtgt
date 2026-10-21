"""Resource boundaries and semantically equivalent XML must agree across readers."""
from __future__ import annotations

import re
import unittest

from gdt_tax.inventory import profile_xml
from gdt_tax.parser.extract import extract_declaration
from gdt_tax.xml_policy import XmlPolicy, XmlReadError, parse_xml
from tests.test_parser import RETURN_XML


class XmlPolicyTests(unittest.TestCase):
    def test_exact_depth_nodes_and_bytes_boundaries(self):
        parse_xml(b'<r/>', XmlPolicy(max_bytes=4, max_depth=1, max_nodes=1))
        for data, policy, code in [
            (b'<r/> ', XmlPolicy(max_bytes=4), 'XML_TOO_LARGE'),
            (b'<r><x/></r>', XmlPolicy(max_depth=1), 'XML_TOO_DEEP'),
            (b'<r><x/><x/></r>', XmlPolicy(max_nodes=2), 'XML_TOO_MANY_NODES'),
        ]:
            with self.subTest(code=code), self.assertRaisesRegex(XmlReadError, code):
                parse_xml(data, policy)
        parse_xml(b'<r><x/></r>', XmlPolicy(max_depth=2, max_nodes=2))

    def test_declared_depth_is_shared_by_inventory_and_parser(self):
        data = b'<r>' * 101 + b'</r>' * 101
        self.assertEqual(profile_xml(data).status, 'error')
        self.assertEqual(extract_declaration(data).status, 'error')

    def test_dtd_is_rejected_without_resolving_entities(self):
        data = b'<!DOCTYPE r [<!ENTITY e SYSTEM "https://invalid.example/data">]><r>&e;</r>'
        with self.assertRaisesRegex(XmlReadError, 'XML_DTD_NOT_ALLOWED'):
            parse_xml(data)
        self.assertEqual(profile_xml(data).status, 'error')

    def test_prefix_and_default_namespace_extract_equivalent_values(self):
        prefixed = RETURN_XML.decode().replace('xmlns=', 'xmlns:p=')
        prefixed = re.sub(r'<(/?)([A-Za-z][A-Za-z0-9_]*)(?=[\s>])', r'<\1p:\2', prefixed).encode()
        before, after = extract_declaration(RETURN_XML), extract_declaration(prefixed)
        self.assertEqual(before.form_code, after.form_code)
        self.assertEqual(before.taxpayer, after.taxpayer)
        self.assertEqual(before.period, after.period)
        self.assertEqual([(x.code, x.value) for x in before.indicators], [(x.code, x.value) for x in after.indicators])
        self.assertEqual(profile_xml(RETURN_XML).namespace, profile_xml(prefixed).namespace)

    def test_appendix_metadata_does_not_override_main_return(self):
        appendix = b'<PLuc><maTKhai>wrong</maTKhai><mst>wrong</mst><CTieuTKhaiChinh><ct99>9</ct99></CTieuTKhaiChinh></PLuc>'
        data = RETURN_XML.replace(b'<HSoKhaiThue id="ID_1">', b'<HSoKhaiThue id="ID_1">'+appendix)
        parsed = extract_declaration(data)
        self.assertEqual(parsed.form_code, '842')
        self.assertEqual(parsed.taxpayer.tax_code, '0000000000')
        self.assertNotIn('ct99', [x.code for x in parsed.indicators])

    def test_wrapper_and_ambiguous_main_documents(self):
        xml = re.sub(br'<\?xml[^>]+\?>', b'', RETURN_XML)
        self.assertEqual(extract_declaration(b'<Envelope>'+xml+b'</Envelope>').form_code, '842')
        parsed = extract_declaration(b'<Envelope>'+xml+xml+b'</Envelope>')
        self.assertEqual(parsed.status, 'error')
        self.assertEqual(parsed.error, 'AMBIGUOUS_MAIN_DECLARATION')
