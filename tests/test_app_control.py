from pathlib import Path
import threading
import time


ROOT = Path(__file__).resolve().parents[1]


class _FakeSocket:
    def __init__(self, request):
        self.request = request
        self.properties = {}
        self.response = b""

    def property(self, name):
        return self.properties.get(name)

    def setProperty(self, name, value):
        self.properties[name] = value

    def canReadLine(self):
        return b"\n" in self.request

    def readLine(self):
        request, self.request = self.request, b""
        return request

    def write(self, data):
        self.response += data
        return len(data)

    def flush(self):
        return True

    def waitForBytesWritten(self, _timeout):
        return True

    def disconnectFromServer(self):
        pass


class _Controller:
    def __init__(self, accepted=True):
        self.accepted = accepted
        self.prompt_modes = []

    def exit_app(self, allow_prompts=True):
        self.prompt_modes.append(allow_prompts)
        return self.accepted


def _bare_server(controller):
    from app_control import ApplicationControlServer

    server = ApplicationControlServer.__new__(ApplicationControlServer)
    server.controller = controller
    return server


def test_interactive_shutdown_reports_acceptance():
    from app_control import SHUTDOWN_COMMAND

    controller = _Controller(accepted=True)
    socket = _FakeSocket(SHUTDOWN_COMMAND + b"\n")
    _bare_server(controller)._read_request(socket)

    assert controller.prompt_modes == [True]
    assert socket.response == b"accepted\n"


def test_silent_shutdown_refuses_dirty_session_without_prompting():
    from app_control import SHUTDOWN_SILENT_COMMAND

    controller = _Controller(accepted=False)
    socket = _FakeSocket(SHUTDOWN_SILENT_COMMAND + b"\n")
    _bare_server(controller)._read_request(socket)

    assert controller.prompt_modes == [False]
    assert socket.response == b"cancelled\n"


def test_unknown_control_request_never_exits_application():
    controller = _Controller()
    socket = _FakeSocket(b"force\n")
    _bare_server(controller)._read_request(socket)

    assert controller.prompt_modes == []
    assert socket.response == b"unsupported\n"


def test_local_control_round_trip(qapp):
    from PyQt5.QtNetwork import QLocalServer
    from app_control import (
        ApplicationControlServer,
        EXIT_ACCEPTED,
        SERVER_NAME,
        request_shutdown,
    )

    QLocalServer.removeServer(SERVER_NAME)
    controller = _Controller(accepted=True)
    server = ApplicationControlServer(controller, qapp)
    result = []
    client = threading.Thread(
        target=lambda: result.append(request_shutdown(timeout_ms=3000))
    )
    client.start()
    deadline = time.monotonic() + 5
    while client.is_alive() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    client.join(timeout=0.1)
    server.server.close()
    QLocalServer.removeServer(SERVER_NAME)

    assert not client.is_alive()
    assert result == [EXIT_ACCEPTED]
    assert controller.prompt_modes == [True]


def test_installer_has_no_forced_process_termination():
    script = (ROOT / "App" / "SwiftShot.iss").read_text(encoding="utf-8")
    lowered = script.lower()

    assert "taskkill" not in lowered
    assert "/f /im" not in lowered
    assert "closeapplications=no" in lowered
    assert "preparetoinstall" in lowered
    assert "checkformutexes('swiftshot_singleinstance')" in lowered
    assert "--shutdown-for-update" in lowered
    assert "waitforswiftshotexit" in lowered


def test_build_manifests_include_control_channel():
    build_script = (ROOT / "App" / "Build-SwiftShot.ps1").read_text(
        encoding="utf-8"
    )
    spec = (ROOT / "App" / "SwiftShot.spec").read_text(encoding="utf-8")

    assert '"app_control.py"' in build_script
    assert '"app_control"' in build_script
    assert '"PyQt5.QtNetwork"' in build_script
    assert "'app_control'" in spec
    assert "'PyQt5.QtNetwork'" in spec
