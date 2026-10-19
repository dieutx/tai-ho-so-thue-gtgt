"""Run logical work-area/DPI matrix with Qt offscreen and retain PNG evidence."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

MATRIX = [(w, h - 40, scale) for w, h in [(1920, 1080), (1366, 768), (1280, 720), (1080, 700), (1024, 768), (1024, 600)] for scale in (1, 1.25, 1.5)]


def main() -> int:
    output = Path(".cache/ui-matrix").resolve()
    for width, height, scale in MATRIX:
        env = dict(os.environ, QT_SCALE_FACTOR=str(scale), QT_QPA_PLATFORM="offscreen")
        subprocess.run([sys.executable, "-m", "desktop.main", "--ui-check", str(output),
                        "--ui-size", f"{width}x{height}"], env=env, check=True, timeout=45)
    reports = [json.loads(path.read_text()) for path in output.glob("check-*.json")]
    print(json.dumps({"checks": len(reports), "pass": all(r["pass"] for r in reports)}, indent=2))
    return 0 if len(reports) == len(MATRIX) and all(r["pass"] for r in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
