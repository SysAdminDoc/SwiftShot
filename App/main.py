"""
SwiftShot - Screenshot Tool
Entry point with logging and update checking.
"""

import sys
import os


def main():
    # Early logging setup before anything else
    from logger import setup_logger, log
    setup_logger()
    log.info("SwiftShot starting up")

    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt

    # High-DPI support
    try:
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    except AttributeError:
        pass

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("SwiftShot")
    app.setOrganizationName("SwiftShot")

    # Apply global dark theme
    try:
        from theme import apply_dark_theme
        apply_dark_theme(app)
    except Exception as e:
        log.warning(f"Could not apply theme: {e}")

    # Config is auto-loaded during import
    from config import config
    log.info("Configuration loaded")

    # Start application
    from app import SwiftShotApp
    swiftshot = SwiftShotApp(app)
    swiftshot.start()

    exit_code = app.exec_()
    log.info(f"SwiftShot exited with code {exit_code}")
    sys.exit(exit_code)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Last-resort crash handler
        try:
            from logger import log
            log.critical(f"Unhandled exception: {e}", exc_info=True)
        except Exception:
            pass

        # Show error dialog if possible
        try:
            from PyQt5.QtWidgets import QApplication, QMessageBox
            if not QApplication.instance():
                QApplication(sys.argv)
            QMessageBox.critical(
                None, "SwiftShot Error",
                f"An unexpected error occurred:\n\n{str(e)}\n\n"
                "Check the log file for details."
            )
        except Exception:
            print(f"FATAL: {e}", file=sys.stderr)

        sys.exit(1)
