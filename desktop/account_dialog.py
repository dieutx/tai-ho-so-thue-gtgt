"""The only credential form. Password reveal lasts only while the eye is held."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
)

from .account_store import AccountStore, AccountStoreError


class AccountDialog(QDialog):
    def __init__(self, parent=None, username: str = "", password: str = "", *, store=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Đăng nhập ETAX")
        form = QFormLayout(self)
        self.store = store if store is not None else AccountStore()
        self.accounts = QComboBox()
        self.accounts.setEditable(True)
        self.accounts.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.accounts.setAccessibleName('Danh sách MST đã lưu')
        self.username = self.accounts.lineEdit()
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
        form.addRow("MST / Tài khoản", self.accounts)
        form.addRow("Mật khẩu", row)
        self.remember = QCheckBox('Lưu mật khẩu trên máy này')
        self.remember.setChecked(True)
        form.addRow(self.remember)
        self.forget = QPushButton('Quên tài khoản đã lưu')
        self.forget.clicked.connect(self.forget_account)
        form.addRow(self.forget)
        self.message = QLabel('Chọn MST đã lưu hoặc nhập tài khoản mới. Mật khẩu được lưu bằng Windows Credential Manager sau khi đăng nhập thành công.')
        self.message.setWordWrap(True)
        form.addRow(self.message)
        try:
            self.accounts.addItems(self.store.accounts())
        except AccountStoreError as error:
            self.message.setText(str(error))
            self.remember.setChecked(False)
            self.remember.setEnabled(False)
        self.username.textChanged.connect(self.select_account)
        self.username.setText(username)
        self.select_account(username)
        if password:
            self.password.setText(password)
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

    def select_account(self, username: str) -> None:
        self.password.clear()
        self.mask()
        saved = self.accounts.findText(username) >= 0 and bool(username)
        self.forget.setEnabled(saved)
        if saved:
            try:
                self.password.setText(self.store.password(username) or '')
            except AccountStoreError as error:
                self.message.setText(str(error))

    def forget_account(self) -> None:
        username = self.username.text()
        try:
            self.store.forget(username)
        except AccountStoreError as error:
            self.message.setText(str(error))
            return
        index = self.accounts.findText(username)
        if index >= 0:
            self.accounts.removeItem(index)
        self.username.setText(username)
        self.password.clear()
        self.forget.setEnabled(False)
        self.message.setText('Đã xóa mật khẩu đã lưu cho tài khoản này.')

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
