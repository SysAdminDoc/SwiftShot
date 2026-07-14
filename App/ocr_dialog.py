"""
SwiftShot OCR Result Dialog
Standalone dialog for displaying OCR results.
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QApplication
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt


class OcrResultDialog(QDialog):
    """Dialog to show OCR results with copy-to-clipboard."""

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setWindowTitle("OCR Result — SwiftShot")
        self.setMinimumSize(320, 240)
        screen = QApplication.screenAt(self.geometry().center())
        screen = screen or QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            self.resize(min(640, int(available.width() * 0.85)),
                        min(420, int(available.height() * 0.85)))
        else:
            self.resize(600, 400)
        self.setAccessibleName("OCR result")
        self.setAccessibleDescription(
            "Review, edit, and copy text extracted from the selected image.")
        # Styling comes from the app-wide theme stylesheet.

        # Make the promise in the label true for every caller.
        QApplication.clipboard().setText(text)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        lbl = QLabel("Extracted text")
        lbl.setFont(QFont("Segoe UI", 11, QFont.Bold))
        layout.addWidget(lbl)

        self.status_label = QLabel("Copied automatically to the clipboard.")
        self.status_label.setTextFormat(Qt.PlainText)
        self.status_label.setWordWrap(True)
        self.status_label.setAccessibleName("Clipboard status")
        layout.addWidget(self.status_label)

        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(text)
        self.text_edit.setReadOnly(False)
        self.text_edit.setFont(QFont("Consolas", 10))
        self.text_edit.setAccessibleName("Extracted text")
        self.text_edit.setAccessibleDescription(
            "Editable OCR result. Copy again after making changes.")
        self.text_edit.textChanged.connect(self._mark_edited)
        layout.addWidget(self.text_edit)

        btn_layout = QHBoxLayout()
        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.setAccessibleName("Copy extracted text to clipboard")
        copy_btn.clicked.connect(self._copy)
        btn_layout.addWidget(copy_btn)

        close_btn = QPushButton("Close")
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _copy(self):
        QApplication.clipboard().setText(self.text_edit.toPlainText())
        self.status_label.setText("Copied the current text to the clipboard.")

    def _mark_edited(self):
        self.status_label.setText(
            "Edited text has not been copied. Select Copy to Clipboard when ready.")
