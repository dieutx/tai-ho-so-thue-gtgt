"""Versioned, allowlisted preferences. Credentials never enter this store."""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4


def check_writable_directory(target: Path) -> None:
    """One bounded probe; tempfile retries EACCES excessively on Windows."""
    probe = target / (".taihoso-probe-" + uuid4().hex + ".tmp")
    with probe.open("xb"):
        pass
    probe.unlink()


def default_output() -> Path:
    home = Path.home()
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
                documents = Path(os.path.expandvars(winreg.QueryValueEx(key, "Personal")[0]))
        except OSError:
            documents = home / "Documents"
    else:
        documents = home / "Documents"
    local_data = Path(os.environ.get("LOCALAPPDATA", str(home / ".local"))) / "TaiHoSoThue" / "HoSo"
    candidates = (local_data, documents, home) if "onedrive" in str(documents).lower() else (documents, local_data, home)
    for base in (*candidates, Path(tempfile.gettempdir())):
        try:
            target = base if base == local_data else base / "TaiHoSoThue"
            target.mkdir(parents=True, exist_ok=True)
            check_writable_directory(target)
            return target
        except OSError:
            continue
    raise OSError("Không tìm được thư mục có quyền ghi")


@dataclass
class Preferences:
    schema_version: int = 1
    output: str = ""
    solver: str = "ddddocr"
    timeout: int = 30
    retries: int = 3
    login_attempts: int = 10
    search_attempts: int = 6
    record_delay: float = 1.0
    page_delay: float = 3.0
    jitter: float = 0.3
    page_size: int = 10
    max_days: int = 31
    header_profile: str = "browser"
    cutoff: str = "01/07/2025"
    theme: str = "light"
    dvc_enabled: bool = True


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".config"))) / "TaiHoSoThue" / "settings.json"

    def load(self) -> Preferences:
        if not self.path.exists():
            return Preferences()
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("schema_version", 1) != 1:
            raise ValueError("Phiên bản settings chưa được hỗ trợ; giữ nguyên file cũ")
        defaults = asdict(Preferences())
        safe = {k: v for k, v in raw.items() if k in defaults and type(v) is type(defaults[k])}
        result = Preferences(**safe)
        if result.solver not in {"ddddocr", "manual"} or result.theme not in {"light", "dark"}:
            raise ValueError("Thiết lập CAPTCHA/giao diện không hợp lệ")
        return result

    def save(self, preferences: Preferences) -> None:
        if self.path.exists():
            current = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(current, dict) or current.get("schema_version", 1) != 1:
                raise ValueError("Giữ nguyên settings phiên bản chưa hỗ trợ; không ghi đè")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            temporary = self.path.with_name("." + self.path.name + "." + uuid4().hex + ".tmp")
            with temporary.open("xb") as stream:
                stream.write(json.dumps(asdict(preferences), ensure_ascii=False, indent=2).encode("utf-8"))
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.path)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
