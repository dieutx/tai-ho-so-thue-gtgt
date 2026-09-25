"""Solver CAPTCHA bằng PaddleOCR.

PaddleOCR mạnh về văn bản nói chung; với CAPTCHA nhỏ của cổng thuế (150×38) nó
vẫn đọc được nhưng phần *phát hiện dòng chữ* đôi khi tách ảnh thành hai ô, nên
kết quả phải gộp lại và bỏ ký tự ngoài ``A-Za-z0-9``. Vì vậy solver này dùng
tuỳ chọn ``preprocess`` (phóng to + nhị phân hoá) cho ảnh nhỏ.

Cài::

    pip install "paddleocr>=2.7,<3" paddlepaddle

Dùng::

    GDT_CAPTCHA_SOLVER=paddleocr

Solver tự nhận biết API: ``PaddleOCR 2.x`` dùng ``.ocr()``, ``3.x`` dùng
``.predict()``, nên nâng cấp PaddleOCR không làm hỏng công cụ.
"""

from __future__ import annotations

from collections.abc import Sequence

from .base import CaptchaSolver, normalize_text

DEFAULT_SCALE = 4
DEFAULT_THRESHOLDS = (160,)


class PaddleOcrSolver(CaptchaSolver):
    """Đọc CAPTCHA bằng PaddleOCR."""

    name = "paddleocr"

    def __init__(
        self,
        *,
        lang: str = "en",
        length: int = 5,
        require_length: bool = True,
        use_angle_cls: bool = False,
        show_log: bool = False,
        preprocess: bool = True,
        scale: int = DEFAULT_SCALE,
        thresholds: Sequence[int] = DEFAULT_THRESHOLDS,
        **options: object,
    ) -> None:
        super().__init__(**options)
        self.lang = lang
        self.length = length
        self.require_length = require_length
        self.use_angle_cls = use_angle_cls
        self.show_log = show_log
        self.preprocess = preprocess
        self.scale = scale
        self.thresholds = tuple(thresholds)
        self._ocr = None
        self._uses_predict = False

    def _get_ocr(self):
        if self._ocr is None:
            from paddleocr import PaddleOCR  # nặng: chỉ nạp khi thực sự dùng

            self.logger.info("Đang nạp PaddleOCR...")
            try:
                # PaddleOCR 2.x
                self._ocr = PaddleOCR(
                    lang=self.lang, use_angle_cls=self.use_angle_cls, show_log=self.show_log
                )
            except (TypeError, ValueError):
                # PaddleOCR 3.x đã bỏ các tham số trên.
                self._ocr = PaddleOCR(lang=self.lang)
            self._uses_predict = hasattr(self._ocr, "predict") and not hasattr(
                self._ocr, "ocr"
            )
        return self._ocr

    def _prepare(self, image: bytes):
        import cv2
        import numpy as np

        array = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
        if array is None or not self.preprocess:
            return array
        enlarged = cv2.resize(
            array, None, fx=self.scale, fy=self.scale, interpolation=cv2.INTER_CUBIC
        )
        gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, self.thresholds[0], 255, cv2.THRESH_BINARY)
        return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)

    def solve(self, image: bytes) -> str:
        ocr = self._get_ocr()
        prepared = self._prepare(image)
        if prepared is None:
            return ""

        try:
            if self._uses_predict:
                result = ocr.predict(input=prepared)
            else:
                result = ocr.ocr(prepared, cls=self.use_angle_cls)
        except TypeError:
            result = ocr.ocr(prepared)

        text = normalize_text("".join(self._extract_texts(result)))
        if self.require_length and len(text) != self.length:
            self.logger.warning(
                "PaddleOCR đọc ra %r (%s ký tự, cần %s)", text, len(text), self.length
            )
            return ""
        return text

    @staticmethod
    def _extract_texts(result) -> list[str]:
        """Đọc kết quả của cả PaddleOCR 2.x (list lồng nhau) và 3.x (dict)."""
        texts: list[str] = []
        for page in result or []:
            if hasattr(page, "get"):  # PaddleOCR 3.x: OCRResult giống dict
                texts.extend(str(item) for item in (page.get("rec_texts") or []))
                continue
            for line in page or []:  # PaddleOCR 2.x: [[box, (text, score)], ...]
                if len(line) >= 2 and isinstance(line[1], (list, tuple)) and line[1]:
                    texts.append(str(line[1][0]))
        return texts

    def close(self) -> None:
        self._ocr = None


__all__ = ["PaddleOcrSolver"]
