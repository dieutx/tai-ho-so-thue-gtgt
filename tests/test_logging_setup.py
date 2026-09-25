import io
import logging
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gdt_tax.logging_setup import configure_logging


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
