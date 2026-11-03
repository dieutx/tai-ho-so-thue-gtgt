"""Bounded HTTP measurements containing counts/timings only, never request data."""
from __future__ import annotations

from collections import Counter, deque


class HttpMetrics:
    def __init__(self):
        self.count = 0
        self.bytes = 0
        self.statuses: Counter[str] = Counter()
        self.categories: Counter[str] = Counter()
        self.samples: deque[float] = deque(maxlen=2048)

    def record(self, category: str, status: int | None, elapsed: float, size: int):
        self.count += 1
        self.bytes += size
        self.statuses[str(status // 100) + 'xx' if status else 'transport_error'] += 1
        self.categories[category if category in {'page', 'captcha', 'download', 'portal', 'search', 'login'} else 'portal'] += 1
        self.samples.append(max(0, elapsed) * 1000)

    def snapshot(self) -> dict:
        samples = sorted(self.samples)
        return {'requests': self.count, 'bytes': self.bytes, 'status_classes': dict(self.statuses),
                'categories': dict(self.categories), 'latency_sample_count': len(samples),
                'latency_p50_ms': samples[(len(samples) - 1) // 2] if samples else 0,
                'latency_p95_ms': samples[int((len(samples) - 1) * .95)] if samples else 0}
