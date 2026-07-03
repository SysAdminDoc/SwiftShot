"""
SwiftShot - Screenshot Tool
Entry point with logging and update checking.
"""

import sys


def _install_excepthook():
    """Log unhandled exceptions instead of letting PyQt5 abort the process.

    PyQt5 >= 5.5 calls qFatal() (process abort) for unhandled Python
    exceptions raised inside Qt slots unless a sys.excepthook is installed.
    A screenshot tool must never lose a user's unsaved editor work to a
    single bad slot, so log it and keep running.
    """
    def hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        try:
            from logger import log
            log.critical("Unhandled exception",
                         exc_info=(exc_type, exc_value, exc_tb))
        except Exception:
            pass
    sys.excepthook = hook


def main():
    # Early logging setup before anything else
    from logger import setup_logger, log
    setup_logger()
    _install_excepthook()
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

    # Config is auto-loaded during import
    from config import config
    log.info("Configuration loaded")

    # Apply global theme
    try:
        from theme import apply_theme
        apply_theme(app, config.THEME)
    except Exception as e:
        log.warning(f"Could not apply theme: {e}")

    # Start application
    from app import SwiftShotApp
    swiftshot = SwiftShotApp(app)
    swiftshot.start()

    exit_code = app.exec_()
    log.info(f"SwiftShot exited with code {exit_code}")
    sys.exit(exit_code)


if __name__ == "__main__":
    # Prevent PyInstaller onefile builds from re-launching the app when
    # a bundled library spawns a subprocess.
    import multiprocessing
    multiprocessing.freeze_support()
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
