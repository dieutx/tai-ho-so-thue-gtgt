"""CORE-01/02: inherited field snapshots plus synthetic schema mutations.

The golden file was generated from revision 3068ea9, before these contracts.
Original capture/anonymization provenance of inherited fixtures is unverified.
Every negative/metamorphic input here is generated in memory; no live account.
"""
from __future__ import annotations

import json
import logging
import tempfile
import unicodedata
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

from bs4 import BeautifulSoup

from desktop.services import RunConfig, run_online
from desktop.settings_store import Preferences
from gdt_tax.cli import main as tax_main
from gdt_tax.constants import SOURCE_ETAX_LEGACY
from gdt_tax.gnt.parsing import parse_gnt_table
from gdt_tax.parsing import parse_record_table
from gdt_tax.portals.etax import EtaxPortal
from gdt_tax.run_hooks import RunHooks
from gdt_tax.table_contracts import SCHEMAS
from gdt_tax.tb.parsing import parse_tb_table
from tests.support import FakeHttp, FakeResponse, StubCaptcha, cleanup_temporary_directory, fixture
from tests.test_etax_legacy import make_legacy_handler

GOLDEN = json.loads((Path(__file__).parent / "fixtures/portal_table_fields.golden.json").read_text(encoding="utf-8"))
CASES = {"ETAX": "etax_results.html", "DVC": "dvc_results_page1.html",
         "ETAX_LEGACY": "etax_legacy_results.html", "GNT": "gnt_results_page1.html", "TB": "tb_results_page1.html"}


def read(source, html):
    return parse_gnt_table(html) if source == "GNT" else parse_tb_table(html) if source == "TB" else parse_record_table(html, source)


def named_soup(source):
    soup = BeautifulSoup(fixture(CASES[source]), "lxml")
    if source == SOURCE_ETAX_LEGACY:
        table = soup.find("table")
        head = soup.new_tag("thead")
        row = soup.new_tag("tr")
        for text in SCHEMAS[source].labels:
            cell = soup.new_tag("th")
            cell.string = text
            row.append(cell)
        head.append(row)
        table.insert(0, head)
    return soup


class TableContractTests(unittest.TestCase):
    def test_all_fields_match_pre_contract_snapshots(self):
        for name, expected in GOLDEN["cases"].items():
            with self.subTest(name=name):
                parsed = read(expected["source"], fixture(name))
                self.assertEqual(len(parsed.records), len(expected["rows"]))
                # New identity metadata is additive; every pre-contract field stays exact.
                self.assertEqual([{key: row.to_dict()[key] for key in old}
                                  for row, old in zip(parsed.records, expected["rows"], strict=True)], expected["rows"])

    def test_named_column_permutations_and_added_columns_preserve_fields(self):
        for source in CASES:
            with self.subTest(source=source):
                baseline = [r.to_dict() for r in read(source, fixture(CASES[source])).records]
                soup = named_soup(source)
                table = soup.find("table")
                for row in table.find_all("tr"):
                    nodes = row.find_all(["td", "th"], recursive=False)
                    if not nodes:
                        continue
                    row.clear()
                    for cell in reversed(nodes):
                        row.append(cell)
                    extra = soup.new_tag("th" if row.find_parent("thead") else "td")
                    extra.string = "Ghi chú mới" if extra.name == "th" else "synthetic extra"
                    row.insert(2, extra)
                parsed = read(source, str(soup))
                self.assertEqual(parsed.diagnostics.status, "PARSED")
                self.assertEqual([r.to_dict() for r in parsed.records], baseline)

    def test_aliases_unicode_and_multilevel_colspan_headers(self):
        for source in CASES:
            with self.subTest(source=source):
                soup = named_soup(source)
                head = soup.find("thead")
                for cell in head.find_all(["td", "th"]):
                    cell.string = unicodedata.normalize("NFD", cell.get_text().upper())
                group_row = soup.new_tag("tr")
                group = soup.new_tag("th", colspan=str(len(head.find_all(["td", "th"]))))
                group.string = "Nhóm cột"
                group_row.append(group)
                head.insert(0, group_row)
                parsed = read(source, str(soup))
                self.assertEqual(parsed.diagnostics.status, "PARSED")
                self.assertEqual(len(parsed.records), 2)

    def test_missing_named_date_column_is_explicit_schema_change(self):
        for source in CASES:
            with self.subTest(source=source):
                soup = named_soup(source)
                field_index = SCHEMAS[source].fields.index(SCHEMAS[source].date_fields[0])
                soup.find("thead").find_all(["th", "td"])[field_index].decompose()
                parsed = read(source, str(soup))
                self.assertEqual(parsed.diagnostics.status, "SCHEMA_CHANGED")
                self.assertEqual(parsed.records, [])
                self.assertIn(SCHEMAS[source].date_fields[0], " ".join(parsed.diagnostics.reasons))

    def test_partial_page_keeps_good_rows_and_raw_rejection_evidence(self):
        for source in CASES:
            with self.subTest(source=source):
                soup = named_soup(source)
                rows = [row for row in soup.find("table").find_all("tr") if row.find_parent("thead") is None]
                rows[1].find_all("td", recursive=False)[-1].decompose()
                parsed = read(source, str(soup))
                self.assertEqual(parsed.diagnostics.status, "SCHEMA_CHANGED")
                self.assertEqual((parsed.diagnostics.candidate_count, parsed.diagnostics.parsed_count, parsed.diagnostics.skipped_count), (2, 1, 1))
                self.assertEqual(len(parsed.records), 1)
                self.assertTrue(parsed.diagnostics.row_issues[0]["raw_cells"])

    def test_changed_handler_and_headerless_date_place_swap_cannot_look_empty(self):
        html = fixture("etax_legacy_results.html")
        changed = read("ETAX_LEGACY", html.replace("downloadTkhai", "unknownHandler"))
        self.assertEqual(changed.diagnostics.status, "SCHEMA_CHANGED")
        self.assertEqual(changed.diagnostics.candidate_count, 2)
        soup = BeautifulSoup(html, "lxml")
        for row in soup.find("table").find_all("tr"):
            cells = row.find_all("td", recursive=False)
            cells[7].string, cells[9].string = cells[9].get_text(), cells[7].get_text()
        swapped = read("ETAX_LEGACY", str(soup))
        self.assertEqual(swapped.diagnostics.status, "SCHEMA_CHANGED")
        self.assertIn("INVALID_DATE_COLUMN:ngay_nop", swapped.diagnostics.reasons)

    def test_named_data_attributes_take_priority_over_unrecognized_labels(self):
        soup = named_soup("DVC")
        for row in soup.find("table").find_all("tr"):
            cells = row.find_all(["th", "td"], recursive=False)
            for index, cell in enumerate(cells):
                cell["data-field"] = SCHEMAS["DVC"].fields[index]
                if cell.name == "th":
                    cell.string = "label changed"
        parsed = read("DVC", str(soup))
        self.assertEqual(parsed.diagnostics.status, "PARSED")
        self.assertEqual(len(parsed.records), 2)

    def test_empty_requires_known_marker_and_context_not_pagination(self):
        for source in CASES:
            with self.subTest(source=source):
                schema = SCHEMAS[source]
                if source == SOURCE_ETAX_LEGACY:
                    html = fixture("etax_legacy_empty.html")
                else:
                    soup = named_soup(source)
                    table = soup.find("table")
                    for row in list(table.find_all("tr")):
                        if row.find_parent("thead") is None:
                            row.decompose()
                    marker = soup.new_tag("div")
                    marker.string = schema.empty_markers[0]
                    (soup.select_one(schema.container) if schema.container else soup.body).append(marker)
                    html = str(soup)
                self.assertEqual(read(source, html).diagnostics.status, "EMPTY_CONFIRMED")
                self.assertEqual(read(source, html.replace(schema.empty_markers[0], "unknown empty message")).diagnostics.status, "SCHEMA_CHANGED")
                self.assertEqual(read(source, '<div id="totalPage">0</div>').diagnostics.status, "SCHEMA_CHANGED")

    def test_auxiliary_tables_and_data_colspan_do_not_become_records(self):
        for source in CASES:
            with self.subTest(source=source):
                soup = named_soup(source)
                auxiliary = BeautifulSoup('<table><tbody><tr><td>unrelated</td><td>data</td></tr></tbody></table>', "lxml").find("table")
                (soup.body or soup).insert(0, auxiliary)
                self.assertEqual(len(read(source, str(soup)).records), 2)
                row = [row for row in soup.find_all("table")[1].find_all("tr") if row.find_parent("thead") is None][0]
                row.find("td")["colspan"] = "2"
                self.assertEqual(read(source, str(soup)).diagnostics.status, "SCHEMA_CHANGED")

    def test_schema_drift_does_not_reset_captcha_failures(self):
        captcha = Mock()
        portal = EtaxPortal(FakeHttp(lambda *_: None), captcha, Mock(header_profile="minimal"))
        result = portal._page_result(FakeResponse('<div id="goToPage_tdt" max="1"></div>'))
        self.assertEqual(result.diagnostics.status, "SCHEMA_CHANGED")
        captcha.accepted.assert_not_called()
        captcha.rejected.assert_not_called()

    def test_download_identity_must_agree_with_named_id_column(self):
        for source in ("ETAX", "DVC", "ETAX_LEGACY"):
            with self.subTest(source=source):
                soup = named_soup(source)
                cells = soup.find("table").find("tbody").find("tr").find_all("td", recursive=False) if source != "ETAX_LEGACY" else soup.find("table").find_all("tr")[1].find_all("td", recursive=False)
                cells[SCHEMAS[source].fields.index("ma_ho_so")].string = "DIFFERENT-1"
                parsed = read(source, str(soup))
                self.assertEqual(parsed.diagnostics.status, "SCHEMA_CHANGED")
                self.assertEqual(len(parsed.records), 1)

    def test_invalid_counter_is_not_silently_assigned(self):
        soup = named_soup("ETAX")
        soup.find("tbody").find("tr").find_all("td")[5].string = "synthetic-invalid-counter"
        parsed = read("ETAX", str(soup))
        self.assertEqual(parsed.diagnostics.status, "SCHEMA_CHANGED")
        self.assertIn("INVALID_COUNTER_COLUMN:lan_nop", parsed.diagnostics.reasons)


class TablePipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        cleanup_temporary_directory(self.temp)

    def config(self):
        return RunConfig("tax", self.root / "dry", username="synthetic-user", password="fake-secret",
            from_date="01/01/2020", to_date="31/01/2020", dry_run=True,
            preferences=Preferences(record_delay=0, page_delay=0, jitter=0, login_attempts=1, search_attempts=4))

    def test_gui_keeps_partial_rows_without_requery_and_dry_run_writes_nothing(self):
        soup = BeautifulSoup(fixture("etax_legacy_results.html"), "lxml")
        soup.find("table").find_all("tr")[1].find("td").decompose()
        state = {"query_html": str(soup)}
        http = FakeHttp(make_legacy_handler(state))
        result = run_online(self.config(), RunHooks(), StubCaptcha(), logging.getLogger("gdt_tax.test"), http=http)
        self.assertEqual(result.state, "PARTIAL")
        self.assertEqual(result.discovered, 1)
        self.assertIn("SCHEMA_CHANGED", result.message)
        self.assertGreater(result.errors, 0)
        queries = [call for call in http.calls if (call.kwargs.get("data") or {}).get("dse_nextEventName") == "query"]
        self.assertEqual(len(queries), 1)
        self.assertFalse(self.config().output.exists())

    def test_cli_schema_failure_returns_nonzero(self):
        config = self.config()
        http = FakeHttp(make_legacy_handler({"query_html": fixture("etax_legacy_results.html").replace("downloadTkhai", "unknownHandler")}))
        with patch("gdt_tax.cli.Settings.from_env", return_value=replace(config.settings(), dry_run=True)), patch(
                "gdt_tax.cli.create_solver", return_value=StubCaptcha()), patch("gdt_tax.cli.HttpClient", return_value=http):
            self.assertNotEqual(tax_main(["--env-file", str(self.root / "absent.env")]), 0)

    def test_pipeline_empty_without_diagnostics_is_not_confirmed(self):
        from gdt_tax.models import PageResult
        from gdt_tax.pipeline import Pipeline
        portal = Mock(source="ETAX_LEGACY")
        portal.search.return_value = PageResult(total_pages=0, http_status=200)
        pipeline = Pipeline(self.config().settings(), FakeHttp(lambda *_: None), StubCaptcha(), sleep=lambda _: None)
        from gdt_tax.errors import SearchError
        with self.assertRaises(SearchError):
            pipeline._search_page(portal, self.config().settings().periods()[0], 1)
