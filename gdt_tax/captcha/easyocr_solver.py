"""Solver CAPTCHA mặc định: tiền xử lý ảnh bằng OpenCV rồi đọc bằng EasyOCR.

Ảnh CAPTCHA của cổng thuế có 5 ký tự, nền lốm đốm và đường kẻ gây nhiễu. Cách
làm: phóng to ảnh, thử vài ngưỡng nhị phân, đọc tất cả biến thể rồi chọn theo
số phiếu bầu và độ tin cậy — cách này ổn định hơn đọc một biến thể duy nhất.

``easyocr``/``torch`` chỉ được import khi solver này thực sự được dùng.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from .base import CaptchaSolver, normalize_text

ALLOWLIST = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
DEFAULT_LENGTH = 5
DEFAULT_SCALE = 5
DEFAULT_THRESHOLDS = (140, 170, 200)


class EasyOcrSolver(CaptchaSolver):
    """Đọc CAPTCHA bằng EasyOCR trên nhiều biến thể ảnh."""

    name = "easyocr"

    def __init__(
        self,
        *,
        languages: Sequence[str] = ("en",),
        gpu: bool = False,
        length: int = DEFAULT_LENGTH,
        scale: int = DEFAULT_SCALE,
        thresholds: Sequence[int] = DEFAULT_THRESHOLDS,
        allowlist: str = ALLOWLIST,
        **options: object,
    ) -> None:
        super().__init__(**options)
        self.languages = list(languages)
        self.gpu = gpu
        self.length = length
        self.scale = scale
        self.thresholds = tuple(thresholds)
        self.allowlist = allowlist
        self._reader = None

    def _get_reader(self):
        if self._reader is None:
            import easyocr  # import nặng: chỉ làm khi thực sự cần

            self.logger.info("Đang nạp EasyOCR (lần đầu có thể tải mô hình)...")
            self._reader = easyocr.Reader(self.languages, gpu=self.gpu)
        return self._reader

    def _variants(self, image: bytes) -> list:
        import cv2
        import numpy as np

        array = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
        if array is None:
            return []

        enlarged = cv2.resize(
            array, None, fx=self.scale, fy=self.scale, interpolation=cv2.INTER_CUBIC
        )
        gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY)
        variants = [enlarged, gray]
        for threshold in self.thresholds:
            _, binary = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)
            variants.append(binary)
        return variants

    def solve(self, image: bytes) -> str:
        reader = self._get_reader()
        candidates: list[tuple[float, str]] = []

        for variant in self._variants(image):
            for _, raw_text, confidence in reader.readtext(
                variant, detail=1, paragraph=False, allowlist=self.allowlist
            ):
                text = normalize_text(raw_text)
                if len(text) == self.length:
                    candidates.append((float(confidence), text))

        if not candidates:
            self.logger.warning("OCR không đọc được mã CAPTCHA nào")
            return ""

        votes = Counter(text for _, text in candidates)
        best_confidence: dict[str, float] = {}
        for confidence, text in candidates:
            best_confidence[text] = max(confidence, best_confidence.get(text, 0.0))

        best = max(votes, key=lambda text: (votes[text], best_confidence[text]))
        self.logger.debug("OCR chọn %r trong %s", best, candidates[:3])
        return best

    def close(self) -> None:
        self._reader = None


__all__ = ["ALLOWLIST", "EasyOcrSolver"]
