import io
import logging
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gdt_tax.logging_setup import SecretsFilter, configure_logging


class SecretsFilterTests(unittest.TestCase):
    def record(self, message: str, args=(), exc_text: str | None = None) -> logging.LogRecord:
        record = logging.LogRecord("urllib3.connectionpool", logging.DEBUG, "f", 1, message, args, None)
        record.exc_text = exc_text
        return record

    def test_che_mat_khau_trong_message(self):
        secrets_filter = SecretsFilter(["bi-mat", "u:bi-mat"])
        record = self.record("Bắt đầu kết nối http://u:bi-mat@1.2.3.4:8080")
        self.assertTrue(secrets_filter.filter(record))
        self.assertNotIn("bi-mat", record.getMessage())
        self.assertIn("***", record.getMessage())

    def test_che_ca_tham_so_noi_suy(self):
        record = self.record("proxy=%s", ("bi-mat",))
        SecretsFilter(["bi-mat"]).filter(record)
        self.assertEqual(record.getMessage(), "proxy=***")

    def test_che_ca_traceback_text(self):
        record = self.record("loi", exc_text="ProxyError: u:bi-mat@1.2.3.4")
        SecretsFilter(["u:bi-mat"]).filter(record)
        self.assertNotIn("bi-mat", record.exc_text)

    def test_khong_co_bi_mat_thi_khong_doi_gi(self):
        record = self.record("giu nguyen")
        SecretsFilter([]).filter(record)
        self.assertEqual(record.getMessage(), "giu nguyen")

    def test_duoc_gan_cho_moi_handler(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.log"
            console = io.StringIO()
            with mock.patch.object(sys, "stdout", console):
                configure_logging(log_file=path, secrets=["bi-mat"])
                logging.getLogger("urllib3.connectionpool").debug("qua http://u:bi-mat@1.2.3.4:8080")
                for handler in logging.getLogger().handlers:
                    handler.flush()
            text = path.read_text(encoding="utf-8")
        self.assertNotIn("bi-mat", text)
        self.assertIn("***", text)


class ConfigureLoggingTests(unittest.TestCase):
    def setUp(self):
        root = logging.getLogger()
        self.saved_level = root.level
        self.saved_handlers = list(root.handlers)

    def tearDown(self):
        root = logging.getLogger()
        for handler in list(root.handlers):
            if handler not in self.saved_handlers:
                handler.close()
                root.removeHandler(handler)
        root.setLevel(self.saved_level)

    def test_mac_dinh_chi_ghi_ra_man_hinh(self):
        console = io.StringIO()
        with mock.patch.object(sys, "stdout", console):
            configure_logging(verbose=False)
            logging.getLogger("gdt_tax.test").info("xin chao")
            logging.getLogger("gdt_tax.test").debug("chi tiet")
        self.assertIn("xin chao", console.getvalue())
        self.assertNotIn("chi tiet", console.getvalue())

    def test_file_log_luon_ghi_o_muc_debug(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "logs" / "run.log"
            console = io.StringIO()
            with mock.patch.object(sys, "stdout", console):
                configure_logging(verbose=False, log_file=path)
                logger = logging.getLogger("gdt_tax.test")
                logger.debug("chi tiet")
                logger.info("tom tat")
                for handler in logging.getLogger().handlers:
                    handler.flush()

            text = path.read_text(encoding="utf-8")
            existed = path.is_file()

        self.assertTrue(existed)
        self.assertIn("chi tiet", text)
        self.assertIn("tom tat", text)
        # File có tất cả, màn hình chỉ có INFO khi không dùng -v.
        self.assertIn("tom tat", console.getvalue())
        self.assertNotIn("chi tiet", console.getvalue())

    def test_file_log_ghi_them_khong_ghi_de(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.log"
            path.write_text("lan chay truoc\n", encoding="utf-8")
            console = io.StringIO()
            with mock.patch.object(sys, "stdout", console):
                configure_logging(verbose=False, log_file=path)
                logging.getLogger("gdt_tax.test").info("lan nay")
                for handler in logging.getLogger().handlers:
                    handler.flush()
            text = path.read_text(encoding="utf-8")
        self.assertIn("lan chay truoc", text)
        self.assertIn("lan nay", text)

    def test_verbose_bat_debug_ra_man_hinh(self):
        console = io.StringIO()
        with mock.patch.object(sys, "stdout", console):
            configure_logging(verbose=True)
            logging.getLogger("gdt_tax.test").debug("chi tiet")
        self.assertIn("chi tiet", console.getvalue())


if __name__ == "__main__":
    unittest.main()
