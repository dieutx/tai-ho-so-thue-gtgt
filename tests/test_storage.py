import csv
import io
import json
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path
from unittest import mock

from openpyxl import load_workbook

from gdt_tax.constants import METADATA_XLSX
from gdt_tax.errors import StorageError
from gdt_tax.models import CaseRecord
from gdt_tax.naming import zip_filename
from gdt_tax.storage import ZipStore, decode_zip_bytes, valid_zip, write_metadata
from tests.support import FakeResponse, cleanup_temporary_directory, sample_zip, zip_payload


def make_record(case_id: str = "11320250292469209") -> CaseRecord:
    return CaseRecord(
        ma_ho_so=case_id,
        nguon="ETAX",
        to_khai="TỜ KHAI THUẾ GIÁ TRỊ GIA TĂNG",
        ky_tinh_thue="12/2024",
        loai_to_khai="Chính thức",
    )


class ValidZipTests(unittest.TestCase):
    def test_zip_hop_le(self):
        self.assertTrue(valid_zip(sample_zip()))

    def test_du_lieu_khong_phai_zip(self):
        self.assertFalse(valid_zip(b"khong-phai-zip"))

    def test_zip_hong(self):
        self.assertFalse(valid_zip(b"PK\x03\x04du-lieu-hong"))

    def test_zip_vuot_gioi_han_bi_tu_choi_truoc_giai_nen(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
            archive.writestr("a.xml", b"a" * 20)
            archive.writestr("b.xml", b"b" * 20)
        data = buffer.getvalue()
        for name, limit in (
            ("MAX_ARCHIVE_BYTES", len(data) - 1),
            ("MAX_MEMBERS", 1),
            ("MAX_MEMBER_BYTES", 19),
            ("MAX_TOTAL_UNCOMPRESSED", 39),
        ):
            with self.subTest(name=name), mock.patch(f"gdt_tax.storage.{name}", limit):
                with mock.patch.object(zipfile.ZipFile, "testzip") as decompress:
                    self.assertFalse(valid_zip(data))
                    decompress.assert_not_called()
        self.assertTrue(valid_zip(data))

    def test_zip_co_ty_le_nen_bat_thuong_bi_tu_choi(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("bomb.xml", b"0" * 100_000)
        with mock.patch.object(zipfile.ZipFile, "testzip") as decompress:
            self.assertFalse(valid_zip(buffer.getvalue()))
            decompress.assert_not_called()

    def test_zip_hong_crc_bi_tu_choi(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
            archive.writestr("a.xml", b"unique-payload")
        self.assertFalse(valid_zip(buffer.getvalue().replace(b"unique-payload", b"broken-payload")))

    def test_zip_ma_hoa_bi_tu_choi_truoc_giai_nen(self):
        raw = bytearray(sample_zip())
        raw[6] |= 1
        central = raw.find(b"PK\x01\x02")
        raw[central + 8] |= 1
        with mock.patch.object(zipfile.ZipFile, "testzip") as decompress:
            self.assertFalse(valid_zip(bytes(raw)))
            decompress.assert_not_called()

    def test_loi_giai_nen_khong_lam_dung_chuong_trinh(self):
        with mock.patch.object(zipfile.ZipFile, "testzip", side_effect=zlib.error("bad data")):
            self.assertFalse(valid_zip(sample_zip()))


class DecodeZipTests(unittest.TestCase):
    def test_json_base64(self):
        response = FakeResponse(json_payload={"content": zip_payload()})
        data = decode_zip_bytes(response)
        self.assertIsNotNone(data)
        self.assertTrue(valid_zip(data))

    def test_nhi_phan_truc_tiep(self):
        response = FakeResponse(content=sample_zip())
        self.assertIsNotNone(decode_zip_bytes(response))

    def test_phan_hoi_loi_tra_none(self):
        self.assertIsNone(decode_zip_bytes(FakeResponse(content=b"loi may chu")))


class ZipStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self._tmp.name)
        self.store = ZipStore(self.directory)

    def tearDown(self):
        cleanup_temporary_directory(self._tmp)

    def test_luu_file_va_dat_ten(self):
        record = make_record()
        path = self.store.save(record, sample_zip())
        self.assertTrue(path.is_file())
        self.assertEqual(path.name, zip_filename(record))
        self.assertEqual(record.tep_zip, path.name)

    def test_khong_luu_zip_hong(self):
        self.assertIsNone(self.store.save(make_record(), b"hong"))

    def test_tim_thay_zip_da_tai(self):
        record = make_record()
        saved = self.store.save(record, sample_zip())
        again = self.store.find_existing(make_record())
        self.assertEqual(again, saved)

    def test_bo_qua_file_hong_cung_ten(self):
        record = make_record()
        (self.directory / zip_filename(record)).write_bytes(b"hong")
        self.assertIsNone(self.store.find_existing(record))

    def test_chua_co_file_thi_tra_none(self):
        self.assertIsNone(self.store.find_existing(make_record()))

    def test_resume_khong_doc_file_vuot_gioi_han(self):
        record = make_record()
        self.store.path_for(record).write_bytes(sample_zip())
        with mock.patch("gdt_tax.storage.MAX_ARCHIVE_BYTES", 1):
            with mock.patch.object(Path, "read_bytes") as read:
                self.assertIsNone(self.store.find_existing(record))
                read.assert_not_called()

    def test_khong_nham_file_cua_ho_so_khac_khi_ma_co_ky_tu_glob(self):
        # "[" và "]" là ký tự đặc biệt của glob: không escape thì
        # "*G[12]*.zip" khớp cả file "G1-khac.zip" của hồ sơ khác và bị đổi tên
        # thành của hồ sơ này — hồ sơ sẽ mang dữ liệu sai.
        (self.directory / "G1-khac.zip").write_bytes(sample_zip())
        self.assertIsNone(self.store.find_existing(make_record("G[12]")))
        self.assertTrue((self.directory / "G1-khac.zip").is_file())

    def test_van_tim_thay_file_cu_cua_dung_ho_so_co_ky_tu_glob(self):
        record = make_record("G[12]")
        (self.directory / "G[12]-ten-cu.zip").write_bytes(sample_zip())
        found = self.store.find_existing(record)
        self.assertIsNotNone(found)
        self.assertEqual(found.name, zip_filename(record))

    def test_save_from_response_giai_ma_base64(self):
        record = make_record()
        response = FakeResponse(json_payload={"content": zip_payload()})
        self.assertIsNotNone(self.store.save_from_response(record, response))

    def test_khong_nham_ma_ho_so_la_chuoi_con(self):
        for name in ("9123.zip", "1234__ten.zip", "prefix123.zip"):
            (self.directory / name).write_bytes(sample_zip())
        self.assertIsNone(self.store.find_existing(make_record("123")))
        self.assertEqual(len(list(self.directory.glob("*.zip"))), 3)

    def test_ghi_loi_khong_lam_hong_file_cu(self):
        record = make_record()
        saved = self.store.save(record, sample_zip())
        original = saved.read_bytes()
        with mock.patch("gdt_tax.storage.os.replace", side_effect=OSError("disk error")):
            with self.assertRaises(StorageError):
                self.store.save(record, sample_zip())
        self.assertEqual(saved.read_bytes(), original)
        self.assertEqual(list(self.directory.glob("*.tmp")), [])


class WriteMetadataTests(unittest.TestCase):
    EXCEL_HEADERS = [
        "STT",
        "Mã hồ sơ",
        "Tên tờ khai",
        "Kỳ tính thuế",
        "Loại tờ khai",
        "Lần nộp bổ sung",
        "Lần nộp",
        "Cơ quan thuế tiếp nhận",
        "Ngày nộp",
        "Trạng thái",
        "Hồ sơ đính kèm",
    ]

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self._tmp.name)

    def tearDown(self):
        cleanup_temporary_directory(self._tmp)

    def test_ghi_ca_csv_va_json(self):
        records = {"b": make_record("B-2"), "a": make_record("A-1")}
        csv_path, json_path = write_metadata(self.directory, records)

        with csv_path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual([row["ma_ho_so"] for row in rows], ["A-1", "B-2"])
        self.assertEqual(rows[0]["loai_to_khai"], "Chính thức")

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual([item["ma_ho_so"] for item in payload], ["A-1", "B-2"])
        self.assertIn("ky_tinh_thue", payload[0])

        workbook = load_workbook(self.directory / METADATA_XLSX, read_only=False)
        sheet = workbook["Danh sách tờ khai"]
        self.assertEqual([cell.value for cell in sheet[1]], self.EXCEL_HEADERS)
        self.assertEqual(sheet.max_row, 3)
        self.assertEqual([sheet.cell(row, 2).value for row in (2, 3)], ["A-1", "B-2"])
        self.assertEqual(sheet.freeze_panes, "A2")
        self.assertIn("DanhSachToKhai", sheet.tables)
        workbook.close()

    def test_khong_co_ho_so_thi_khong_ghi(self):
        self.assertIsNone(write_metadata(self.directory, {}))
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_chay_khoang_moi_khong_mat_metadata_khoang_cu(self):
        write_metadata(self.directory, [make_record("A")])
        write_metadata(self.directory, [make_record("B")])
        rows = json.loads((self.directory / "danh_sach_ho_so.json").read_text(encoding="utf-8"))
        self.assertEqual([row["ma_ho_so"] for row in rows], ["A", "B"])
        workbook = load_workbook(self.directory / METADATA_XLSX, read_only=True)
        sheet = workbook["Danh sách tờ khai"]
        self.assertEqual([sheet.cell(row, 2).value for row in (2, 3)], ["A", "B"])
        workbook.close()

    def test_excel_chan_cong_thuc_tu_du_lieu_cong(self):
        record = make_record("=HYPERLINK(\"https://invalid\")")
        write_metadata(self.directory, [record])
        workbook = load_workbook(self.directory / METADATA_XLSX, read_only=True)
        value = workbook["Danh sách tờ khai"].cell(2, 2).value
        workbook.close()
        self.assertEqual(value, "'=HYPERLINK(\"https://invalid\")")

    def test_dry_run_khong_xoa_tham_chieu_file_da_tai(self):
        record = make_record("A")
        record.tep_zip = "A.zip"
        write_metadata(self.directory, [record])
        write_metadata(self.directory, [make_record("A")])
        rows = json.loads((self.directory / "danh_sach_ho_so.json").read_text(encoding="utf-8"))
        self.assertEqual(rows[0]["tep_zip"], "A.zip")

    def test_metadata_hong_khong_bi_ghi_de(self):
        path = self.directory / "danh_sach_ho_so.json"
        path.write_text("{broken", encoding="utf-8")
        with self.assertRaises(StorageError):
            write_metadata(self.directory, [make_record()])
        self.assertEqual(path.read_text(encoding="utf-8"), "{broken")

    def test_danh_muc_nhom_chi_chua_ho_so_co_file_da_tai(self):
        downloaded = make_record("A")
        downloaded.tep_zip = "A.zip"
        downloaded.nhom_to_khai = "GTGT"
        write_metadata(self.directory, [downloaded, make_record("B")])
        groups = json.loads((self.directory / "phan_loai_ho_so.json").read_text(encoding="utf-8"))
        self.assertEqual(len(groups["groups"]["GTGT"]), 1)
        self.assertEqual(groups["groups"]["UNKNOWN"], [])


if __name__ == "__main__":
    unittest.main()
