"""
SwiftShot OCR Result Dialog
Standalone dialog for displaying OCR results.
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QApplication
)
from PyQt5.QtGui import QFont


class OcrResultDialog(QDialog):
    """Dialog to show OCR results with copy-to-clipboard."""

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setWindowTitle("OCR Result - SwiftShot")
        self.setMinimumSize(500, 350)
        # Styling comes from the app-wide theme stylesheet.

        # Make the promise in the label true for every caller.
        QApplication.clipboard().setText(text)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        lbl = QLabel("Extracted text (already copied to your clipboard):")
        lbl.setFont(QFont("Segoe UI", 11, QFont.Bold))
        layout.addWidget(lbl)

        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(text)
        self.text_edit.setReadOnly(False)
        self.text_edit.setFont(QFont("Consolas", 10))
        self.text_edit.setAccessibleName("Extracted text")
        layout.addWidget(self.text_edit)

        btn_layout = QHBoxLayout()
        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.clicked.connect(self._copy)
        btn_layout.addWidget(copy_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _copy(self):
        QApplication.clipboard().setText(self.text_edit.toPlainText())
