"""Native FIDO2 / WebAuthn security key dialog (Problem A4 fix)."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class WebAuthnDialog(QDialog):
    """Handles QWebEngineWebAuthUxRequest PIN, account selection, and touch prompts."""

    def __init__(self, request: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._request = request
        self.setWindowTitle("Security Key Verification")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        self._message = QLabel("Insert or touch your security key to continue.")
        self._message.setWordWrap(True)
        layout.addWidget(self._message)

        self._pin_input = QLineEdit()
        self._pin_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._pin_input.setPlaceholderText("Enter security key PIN")
        self._pin_input.hide()
        layout.addWidget(self._pin_input)

        self._account_list = QListWidget()
        self._account_list.hide()
        layout.addWidget(self._account_list)

        btn_row = QHBoxLayout()
        self._cancel_btn = QPushButton("Cancel")
        self._submit_btn = QPushButton("Continue")
        self._submit_btn.setObjectName("PrimaryButton")
        self._cancel_btn.clicked.connect(self._on_cancel)
        self._submit_btn.clicked.connect(self._on_submit)
        btn_row.addStretch(1)
        btn_row.addWidget(self._cancel_btn)
        btn_row.addWidget(self._submit_btn)
        layout.addLayout(btn_row)

        if hasattr(request, "stateChanged"):
            request.stateChanged.connect(self._sync_state)
        self._sync_state()

    def _sync_state(self, *_args: Any) -> None:
        state_name = str(getattr(self._request, "state", lambda: "")()).lower()
        self._pin_input.hide()
        self._account_list.hide()

        if "collectpin" in state_name:
            self._message.setText("Enter the PIN for your hardware security key:")
            self._pin_input.show()
            self._pin_input.setFocus()
        elif "selectaccount" in state_name:
            self._message.setText("Choose an account on your security key:")
            self._account_list.clear()
            for name in getattr(self._request, "userNames", lambda: [])():
                self._account_list.addItem(str(name))
            self._account_list.show()
        elif "failed" in state_name:
            self._message.setText("Security key verification failed. Retry or cancel.")
        elif "completed" in state_name or "cancelled" in state_name:
            self.accept()
        else:
            self._message.setText("Touch your security key to confirm sign-in.")

    def _on_submit(self) -> None:
        if self._pin_input.isVisible() and hasattr(self._request, "setPin"):
            self._request.setPin(self._pin_input.text())
        elif self._account_list.isVisible() and hasattr(self._request, "setSelectedAccount"):
            item = self._account_list.currentItem()
            if item is not None:
                self._request.setSelectedAccount(item.text())
        elif hasattr(self._request, "retry"):
            self._request.retry()

    def _on_cancel(self) -> None:
        if hasattr(self._request, "cancel"):
            self._request.cancel()
        self.reject()
