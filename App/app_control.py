"""Private local control channel used by the installer.

The protocol is deliberately tiny and local-only.  A second SwiftShot process
connects to the named Qt local server and asks the running tray process to use
its normal exit path.  The reply tells Setup whether every editor accepted the
close or whether an unsaved document kept the application open.
"""

import ctypes
import sys

from PyQt5.QtCore import QCoreApplication
from PyQt5.QtNetwork import QLocalServer, QLocalSocket


SERVER_NAME = "SwiftShot.ApplicationControl.v1"
SHUTDOWN_COMMAND = b"shutdown-for-update"
SHUTDOWN_SILENT_COMMAND = b"shutdown-for-update-silent"
REPLY_ACCEPTED = b"accepted"
REPLY_CANCELLED = b"cancelled"

EXIT_ACCEPTED = 0
EXIT_CANCELLED = 2
EXIT_UNAVAILABLE = 3


def register_application_restart():
    """Ask Windows to relaunch the tray app after an OS-managed restart.

    This is best-effort and intentionally separate from installer shutdown:
    Setup never relies on Restart Manager to force a dirty editor closed.
    """
    if sys.platform != "win32":
        return False
    try:
        register = ctypes.windll.kernel32.RegisterApplicationRestart
        register.argtypes = [ctypes.c_wchar_p, ctypes.c_uint]
        register.restype = ctypes.c_long
        return register("--minimized", 0) == 0
    except (AttributeError, OSError):
        return False


class ApplicationControlServer:
    """Receive installer control requests inside the running GUI process."""

    def __init__(self, controller, parent=None):
        self.controller = controller
        self.server = QLocalServer(parent)
        self.server.newConnection.connect(self._accept_connections)
        if not self.server.listen(SERVER_NAME):
            raise RuntimeError(
                f"Could not start the SwiftShot control channel: "
                f"{self.server.errorString()}"
            )

    def _accept_connections(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            socket.readyRead.connect(
                lambda current=socket: self._read_request(current)
            )
            if socket.bytesAvailable():
                self._read_request(socket)

    def _read_request(self, socket):
        if socket.property("swiftshotHandled"):
            return
        if not socket.canReadLine():
            return
        command = bytes(socket.readLine()).strip()
        if command not in (SHUTDOWN_COMMAND, SHUTDOWN_SILENT_COMMAND):
            socket.setProperty("swiftshotHandled", True)
            self._reply(socket, b"unsupported")
            return

        socket.setProperty("swiftshotHandled", True)
        accepted = self.controller.exit_app(
            allow_prompts=(command == SHUTDOWN_COMMAND)
        )
        self._reply(socket, REPLY_ACCEPTED if accepted else REPLY_CANCELLED)

    @staticmethod
    def _reply(socket, response):
        socket.write(response + b"\n")
        socket.flush()
        socket.waitForBytesWritten(1000)
        socket.disconnectFromServer()


def request_shutdown(non_interactive=False, timeout_ms=300_000):
    """Ask the running instance to close and return a process exit code.

    ``EXIT_UNAVAILABLE`` is distinct from cancellation so the installer can
    safely support upgrades from older releases that do not host this server.
    It always re-checks the mutex and never assumes a zero child exit code means
    that the application actually stopped.
    """
    owned_app = None
    if QCoreApplication.instance() is None:
        owned_app = QCoreApplication(sys.argv[:1])

    socket = QLocalSocket()
    socket.connectToServer(SERVER_NAME)
    if not socket.waitForConnected(3000):
        return EXIT_UNAVAILABLE

    command = SHUTDOWN_SILENT_COMMAND if non_interactive else SHUTDOWN_COMMAND
    if socket.write(command + b"\n") < 0 or not socket.waitForBytesWritten(3000):
        return EXIT_UNAVAILABLE
    if not socket.waitForReadyRead(timeout_ms):
        return EXIT_UNAVAILABLE

    response = bytes(socket.readAll()).strip()
    socket.disconnectFromServer()
    # Keep a local reference until all Qt objects above are torn down.
    _ = owned_app
    if response == REPLY_ACCEPTED:
        return EXIT_ACCEPTED
    if response == REPLY_CANCELLED:
        return EXIT_CANCELLED
    return EXIT_UNAVAILABLE
