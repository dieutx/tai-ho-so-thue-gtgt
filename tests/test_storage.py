import csv
import json
import tempfile
import unittest
from pathlib import Path

from gdt_tax.models import CaseRecord
from gdt_tax.naming import zip_filename
from gdt_tax.storage import ZipStore, decode_zip_bytes, valid_zip, write_metadata
from tests.support import FakeResponse, sample_zip, zip_payload


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
        self._tmp.cleanup()

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


class WriteMetadataTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

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

    def test_khong_co_ho_so_thi_khong_ghi(self):
        self.assertIsNone(write_metadata(self.directory, {}))
        self.assertEqual(list(self.directory.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
