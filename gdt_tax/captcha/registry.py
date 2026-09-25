"""Sổ đăng ký bộ nhận dạng CAPTCHA.

Nhờ đăng ký theo đường dẫn ``module:ClassName`` và chỉ nạp khi thực sự dùng, gói
``gdt_tax`` không kéo theo ``easyocr``/``torch`` nếu bạn chọn solver khác.

Thêm solver của riêng bạn theo một trong hai cách:

1. Gọi :func:`register_solver` trong code của bạn (dùng khi import gói).
2. Khai báo qua biến môi trường, không cần sửa mã nguồn::

       GDT_CAPTCHA_PLUGINS=myocr=my_package.solver:MyOcrSolver
       GDT_CAPTCHA_SOLVER=myocr
"""

from __future__ import annotations

import importlib
from collections.abc import Iterable

from ..errors import CaptchaError
from .base import CaptchaSolver

BUILTIN_SOLVERS: dict[str, str] = {
    "easyocr": "gdt_tax.captcha.easyocr_solver:EasyOcrSolver",
    "manual": "gdt_tax.captcha.manual_solver:ManualSolver",
    "remote": "gdt_tax.captcha.remote_solver:RemoteHttpSolver",
}

_REGISTRY: dict[str, str] = dict(BUILTIN_SOLVERS)


def register_solver(name: str, target: str) -> None:
    """Đăng ký ``name`` trỏ tới lớp solver ở ``target`` (dạng ``module:ClassName``)."""
    if not name or ":" not in target:
        raise CaptchaError(
            f"Đăng ký solver không hợp lệ: name={name!r}, target={target!r}. "
            "target phải có dạng 'module:ClassName'."
        )
    _REGISTRY[name] = target


def register_plugins(spec: str | Iterable[str]) -> tuple[str, ...]:
    """Đăng ký nhiều solver từ chuỗi ``name=module:ClassName`` ngăn bằng dấu phẩy."""
    items = [spec] if isinstance(spec, str) else list(spec)
    registered: list[str] = []
    for item in items:
        for chunk in str(item).split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            name, _, target = chunk.partition("=")
            register_solver(name.strip(), target.strip())
            registered.append(name.strip())
    return tuple(registered)


def available_solvers() -> tuple[str, ...]:
    """Tên mọi solver đã đăng ký, sắp xếp để log/CLI hiển thị ổn định."""
    return tuple(sorted(_REGISTRY))


def create_solver(spec: str, **options: object) -> CaptchaSolver:
    """Tạo solver theo tên hoặc theo đường dẫn ``module:ClassName``."""
    target = _REGISTRY.get(spec)
    if target is None and ":" in spec:
        target = spec
    if not target:
        raise CaptchaError(
            f"Không có solver CAPTCHA tên {spec!r}. "
            f"Các solver có sẵn: {', '.join(available_solvers())}"
        )
    return _load(target)(**options)


def _load(target: str) -> type[CaptchaSolver]:
    module_name, _, attribute = target.partition(":")
    try:
        module = importlib.import_module(module_name)
    except ImportError as error:
        raise CaptchaError(
            f"Không nạp được module {module_name!r} cho solver CAPTCHA: {error}"
        ) from error
    try:
        solver_class = getattr(module, attribute)
    except AttributeError as error:
        raise CaptchaError(f"Module {module_name!r} không có {attribute!r}") from error
    if not issubclass(solver_class, CaptchaSolver):
        raise CaptchaError(f"{target} phải kế thừa CaptchaSolver")
    return solver_class


__all__ = [
    "BUILTIN_SOLVERS",
    "available_solvers",
    "create_solver",
    "register_plugins",
    "register_solver",
]
