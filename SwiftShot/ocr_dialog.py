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
        self.setStyleSheet("""
            QDialog { background-color: #1e1e2e; }
            QLabel { color: #cdd6f4; background: transparent; }
            QTextEdit {
                background-color: #313244; color: #cdd6f4;
                border: 1px solid #45475a; border-radius: 6px;
                padding: 8px; font-family: 'Consolas'; font-size: 10pt;
            }
            QPushButton {
                background-color: #45475a; color: #cdd6f4;
                border: 1px solid #585b70; border-radius: 6px;
                padding: 8px 20px; font-size: 10pt;
            }
            QPushButton:hover { background-color: #585b70; border-color: #89b4fa; }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        lbl = QLabel("Extracted Text:")
        lbl.setFont(QFont("Segoe UI", 11, QFont.Bold))
        layout.addWidget(lbl)

        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(text)
        self.text_edit.setReadOnly(False)
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
