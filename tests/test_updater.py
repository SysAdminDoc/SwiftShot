"""The updater must only surface a genuine GitHub release URL for this repo,
never an arbitrary URL from the API response (defense-in-depth)."""

import json


class _Resp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode()

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _run_checker(qapp, monkeypatch, payload):
    import updater
    monkeypatch.setattr(updater.urllib.request, "urlopen",
                        lambda *a, **k: _Resp(payload))
    checker = updater.UpdateChecker()
    emitted = []
    checker.update_available.connect(lambda tag, url: emitted.append((tag, url)))
    checker.run()
    return emitted


def test_untrusted_update_url_is_replaced(qapp, monkeypatch):
    emitted = _run_checker(qapp, monkeypatch, {
        "tag_name": "v999.0.0",
        "html_url": "file:///etc/passwd",
    })
    assert emitted
    _tag, url = emitted[0]
    assert url == "https://github.com/SysAdminDoc/SwiftShot/releases"


def test_legit_github_url_is_kept(qapp, monkeypatch):
    good = "https://github.com/SysAdminDoc/SwiftShot/releases/tag/v999.0.0"
    emitted = _run_checker(qapp, monkeypatch, {
        "tag_name": "v999.0.0",
        "html_url": good,
    })
    assert emitted and emitted[0][1] == good
