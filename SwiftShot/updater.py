"""
SwiftShot Update Checker
Checks GitHub releases API in a background thread.
Shows a tray notification if a newer version is available.
"""

import json
import urllib.request
import urllib.error
from PyQt5.QtCore import QThread, pyqtSignal

from logger import log

GITHUB_REPO = "SysAdminDoc/SwiftShot"
RELEASES_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
CURRENT_VERSION = "2.0.0"


def _parse_version(v):
    """Parse 'v2.1.0' or '2.1.0' into tuple (2, 1, 0)."""
    v = v.strip().lstrip('v')
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
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))

            tag = data.get("tag_name", "")
            html_url = data.get("html_url", "")

            remote = _parse_version(tag)
            local = _parse_version(CURRENT_VERSION)

            if remote > local:
                log.info(f"Update available: {tag} (current: {CURRENT_VERSION})")
                self.update_available.emit(tag, html_url)
            else:
                log.info(f"Up to date (current: {CURRENT_VERSION}, latest: {tag})")

        except urllib.error.URLError as e:
            log.warning(f"Update check failed (network): {e}")
        except Exception as e:
            log.warning(f"Update check failed: {e}")
        finally:
            self.check_complete.emit()
