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


def _set_dpi_awareness():
    """Make the process per-monitor DPI-aware with Qt scaling OFF.

    Capture math requires logical == physical pixels everywhere. Qt's
    AA_EnableHighDpiScaling rounds the per-monitor factor to whole numbers —
    1.0 at 100%/125% (a no-op) but 2.0 at 150%+, where every capture surface
    (overlay, pickers, crop rects, cursor draw) would mix logical widget
    coordinates with physical GDI pixels. Setting DPI awareness ourselves
    before Qt initializes keeps widget coordinates in physical screen pixels
    at every scale factor (the editor scales its own UI via _UI_SCALE).
    """
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        try:
            # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 (Win10 1703+)
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError, OSError):
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Win 8.1+
            except (AttributeError, OSError):
                ctypes.windll.user32.SetProcessDPIAware()       # Vista+
    except Exception:
        from logger import log
        log.warning("Could not set DPI awareness", exc_info=True)


def _acquire_single_instance():
    """Hold the named mutex the installer's AppMutex directive checks.

    Returns False if another SwiftShot instance already owns it — a second
    instance would fight over the global keyboard hook and the log file.
    The handle is intentionally leaked; the OS releases it at process exit.
    """
    if sys.platform != 'win32':
        return True
    try:
        import ctypes
        ERROR_ALREADY_EXISTS = 183
        handle = ctypes.windll.kernel32.CreateMutexW(None, False, "SwiftShot_SingleInstance")
        if handle and ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            return False
    except Exception:
        pass  # never block startup on a guard failure
    return True


def main():
    # Early logging setup before anything else
    from logger import setup_logger, log
    setup_logger()
    _install_excepthook()

    # Private installer handshake.  This must run before CLI routing and the
    # single-instance mutex so a short-lived second process can ask the owning
    # tray process to follow its normal Save/Discard/Cancel close path.
    if "--shutdown-for-update" in sys.argv[1:]:
        from app_control import request_shutdown
        sys.exit(request_shutdown(
            non_interactive="--non-interactive" in sys.argv[1:]
        ))

    # Headless scriptable capture (swiftshot --region/--fullscreen/--monitor).
    # Runs and exits without the tray; DPI awareness must be set first so
    # region coordinates are physical pixels. Returns None for the GUI path.
    _set_dpi_awareness()
    import cli
    cli_code = cli.run(sys.argv[1:])
    if cli_code is not None:
        sys.exit(cli_code)

    log.info("SwiftShot starting up")

    if not _acquire_single_instance():
        log.info("Another SwiftShot instance is running; exiting")
        return

    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt

    try:
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

    # Hold the server wrapper for the lifetime of the event loop.  Failure is
    # logged but does not make capture functionality unavailable.
    try:
        from app_control import ApplicationControlServer, register_application_restart
        swiftshot._control_server = ApplicationControlServer(swiftshot, app)
        if not register_application_restart():
            log.debug("Windows application restart registration unavailable")
    except Exception:
        log.warning("Could not start application control channel", exc_info=True)

    # The installer's optional file association launches "SwiftShot.exe <image>";
    # its startup shortcut passes --minimized (a no-op for a tray app).
    import os
    for arg in sys.argv[1:]:
        if not arg.startswith('-') and os.path.isfile(arg):
            swiftshot.open_image_file(arg)
            break

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
