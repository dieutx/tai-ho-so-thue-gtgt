"""Solver CAPTCHA bằng ddddocr — ONNX, không cần torch hay paddle.

``ddddocr`` được huấn luyện riêng cho CAPTCHA một dòng chữ-số (đúng dạng ảnh
150×38 của cổng thuế), mô hình chỉ vài MB và chạy trên CPU nên nhanh hơn hẳn
EasyOCR. Đây là lựa chọn nên thử đầu tiên khi EasyOCR đọc sai nhiều.

Cài::

    pip install ddddocr onnxruntime

Dùng::

    GDT_CAPTCHA_SOLVER=ddddocr
"""

from __future__ import annotations

from .base import CaptchaSolver, normalize_text


class DdddOcrSolver(CaptchaSolver):
    """Đọc CAPTCHA bằng mô hình ONNX của ddddocr."""

    name = "ddddocr"

    def __init__(
        self,
        *,
        length: int | tuple[int, ...] | list[int] = 5,
        require_length: bool = True,
        beta: bool = False,
        show_ad: bool = False,
        import_onnx_path: str = "",
        charsets_path: str = "",
        **options: object,
    ) -> None:
        """``beta=True`` dùng mô hình mới hơn của ddddocr.

        Gói ddddocr có sẵn mô hình beta ``common.onnx``. Bản desktop đóng gói
        mô hình mặc định ``common_old.onnx`` và luôn dùng ``beta=False``.
        Mô hình tùy chỉnh dùng ``import_onnx_path`` cùng ``charsets_path``.
        """
        super().__init__(**options)
        # Cổng doanh nghiệp luôn dùng 5 ký tự; cổng cá nhân phát 4 hoặc 5 ký tự.
        values = length if isinstance(length, (tuple, list, set, frozenset)) else (length,)
        accepted = tuple(sorted({int(value) for value in values if int(value) > 0}))
        self.lengths = accepted or (5,)
        self.require_length = require_length
        self.beta = beta
        self.show_ad = show_ad
        self.import_onnx_path = import_onnx_path
        self.charsets_path = charsets_path
        self._ocr = None

    def _get_ocr(self):
        if self._ocr is None:
            import ddddocr  # ONNX + mô hình: chỉ nạp khi thực sự dùng

            kwargs: dict[str, object] = {"show_ad": self.show_ad, "beta": self.beta}
            if self.import_onnx_path:
                kwargs["import_onnx_path"] = self.import_onnx_path
            if self.charsets_path:
                kwargs["charsets_path"] = self.charsets_path
            self.logger.info("Đang nạp ddddocr...")
            self._ocr = ddddocr.DdddOcr(**kwargs)
        return self._ocr

    def solve(self, image: bytes) -> str:
        text = normalize_text(self._get_ocr().classification(image))
        if self.require_length and len(text) not in self.lengths:
            expected = "/".join(str(value) for value in self.lengths)
            self.logger.warning(
                "ddddocr đọc ra %r (%s ký tự, cần %s)", text, len(text), expected
            )
            return ""
        return text

    def close(self) -> None:
        self._ocr = None


__all__ = ["DdddOcrSolver"]
