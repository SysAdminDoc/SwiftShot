"""
SwiftShot Update Checker
Checks GitHub releases API in a background thread.
Shows a tray notification if a newer version is available.
"""

import json
import re
import urllib.request
import urllib.error
from PyQt5.QtCore import QThread, pyqtSignal

from logger import log
from config import config

GITHUB_REPO = "SysAdminDoc/SwiftShot"
RELEASES_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
UPDATE_TIMEOUT_SECONDS = 3
MAX_RESPONSE_BYTES = 1024 * 1024


def _parse_version(v):
    """Parse 'v2.1.0' or '2.1.0' into tuple (2, 1, 0)."""
    v = v.strip().lstrip('v')
    match = re.match(r"\d+(?:\.\d+)*", v)
    v = match.group(0) if match else "0"
    parts = []
    for p in v.split('.'):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


class UpdateChecker(QThread):
    """Background thread that checks GitHub for new releases."""

    update_available = pyqtSignal(str, str)  # (new_version, download_url)
    check_complete = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self):
        try:
            req = urllib.request.Request(
                RELEASES_URL,
                headers={"Accept": "application/vnd.github.v3+json",
                         "User-Agent": "SwiftShot-UpdateChecker"}
            )
            with urllib.request.urlopen(
                    req, timeout=UPDATE_TIMEOUT_SECONDS) as resp:
                payload = resp.read(MAX_RESPONSE_BYTES + 1)
            if len(payload) > MAX_RESPONSE_BYTES:
                raise ValueError("GitHub release response exceeded 1 MiB")
            data = json.loads(payload.decode('utf-8'))
            if not isinstance(data, dict):
                raise ValueError("GitHub release response was not an object")

            tag = data.get("tag_name", "")
            html_url = data.get("html_url", "")
            if not isinstance(tag, str) or not re.fullmatch(
                    r"v?\d+(?:\.\d+){1,3}(?:[-+][0-9A-Za-z.-]+)?", tag):
                raise ValueError("GitHub release response had an invalid version tag")
            if not isinstance(html_url, str):
                html_url = ""

            # Only ever hand a real GitHub release URL for this repo to the
            # shell — a compromised/MITM'd response must not deliver a
            # file://, javascript: or arbitrary URL to webbrowser.open.
            if not html_url.startswith(f"https://github.com/{GITHUB_REPO}/"):
                log.warning(f"Ignoring untrusted update URL: {html_url!r}")
                html_url = f"https://github.com/{GITHUB_REPO}/releases"

            remote = _parse_version(tag)
            local = _parse_version(config.APP_VERSION)

            if remote > local and not self.isInterruptionRequested():
                log.info(f"Update available: {tag} (current: {config.APP_VERSION})")
                self.update_available.emit(tag, html_url)
            else:
                log.info(f"Up to date (current: {config.APP_VERSION}, latest: {tag})")

        except urllib.error.URLError as e:
            log.warning(f"Update check failed (network): {e}")
        except Exception as e:
            log.warning(f"Update check failed: {e}")
        finally:
            self.check_complete.emit()
