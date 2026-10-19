"""The only credential form. Password reveal lasts only while the eye is held."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
)


class AccountDialog(QDialog):
    def __init__(self, parent=None, username: str = "", password: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("Đăng nhập ETAX")
        form = QFormLayout(self)
        self.username = QLineEdit(username)
        self.username.setAccessibleName("MST / Tài khoản")
        self.password = QLineEdit(password)
        self.password.setAccessibleName("Mật khẩu GDT")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        reveal = QPushButton("Giữ để hiện")
        reveal.setAccessibleName("Giữ nút để xem mật khẩu")
        reveal.pressed.connect(lambda: self.password.setEchoMode(QLineEdit.EchoMode.Normal))
        reveal.released.connect(self.mask)
        row = QHBoxLayout()
        row.addWidget(self.password, 1)
        row.addWidget(reveal)
        form.addRow("MST / Tài khoản", self.username)
        form.addRow("Mật khẩu", row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Đăng nhập")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Hủy")
        buttons.accepted.connect(self.accept_if_valid)
        buttons.rejected.connect(self.reject)
        self.password.returnPressed.connect(self.accept_if_valid)
        form.addRow(buttons)
        self.resize(min(480, self.screen().availableGeometry().width() - 30), self.sizeHint().height())
        self.finished.connect(self.mask)
        self.credentials: tuple[str, str] | None = None

    def mask(self, *_args) -> None:
        self.password.setEchoMode(QLineEdit.EchoMode.Password)

    def accept_if_valid(self) -> None:
        if not self.username.text().strip():
            self.username.setFocus()
        elif not self.password.text():
            self.password.setFocus()
        else:
            self.credentials = (self.username.text().strip(), self.password.text())
            self.password.clear()
            self.accept()

    def reject(self) -> None:
        self.credentials = None
        self.password.clear()
        self.mask()
        super().reject()

    def take_credentials(self) -> tuple[str, str] | None:
        values, self.credentials = self.credentials, None
        return values
