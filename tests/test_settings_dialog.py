"""Responsive settings-tab and control-focused search tests."""

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QScrollArea


@pytest.mark.parametrize("mode", ["dark", "light", "high-contrast"])
def test_every_settings_tab_scrolls_without_horizontal_clipping_at_200_percent(
        qapp, monkeypatch, mode):
    from config import config
    from settings_dialog import SettingsDialog

    monkeypatch.setattr(config, "THEME", "light" if mode == "light" else "dark")
    dialog = SettingsDialog()
    if mode == "high-contrast":
        # System high contrast replaces the application stylesheet with the
        # OS palette; layout and scrolling must remain identical.
        dialog.setStyleSheet("")
    available = qapp.primaryScreen().availableGeometry()
    assert dialog.width() <= max(420, int(available.width() * 0.9))
    assert dialog.height() <= max(360, int(available.height() * 0.9))

    dialog.resize(420, 360)
    font = QFont(dialog.font())
    font.setPointSize(max(18, font.pointSize() * 2))
    dialog.setFont(font)
    dialog.show()
    qapp.processEvents()
    try:
        vertical_scroll_tabs = []
        for index in range(dialog.tabs.count()):
            dialog.tabs.setCurrentIndex(index)
            qapp.processEvents()
            scroll = dialog.tabs.widget(index)
            assert isinstance(scroll, QScrollArea)
            assert scroll.widgetResizable()
            assert scroll.widget().width() == scroll.viewport().width()
            assert scroll.horizontalScrollBar().maximum() == 0
            if scroll.verticalScrollBar().maximum() > 0:
                vertical_scroll_tabs.append(dialog.tabs.tabText(index))
        assert {"General", "Hotkeys", "Frame", "Advanced"} <= set(
            vertical_scroll_tabs
        )
    finally:
        dialog.close()


def test_settings_search_uses_help_selects_tab_and_focuses_real_control(qapp):
    from settings_dialog import SettingsDialog

    dialog = SettingsDialog()
    dialog.show()
    qapp.processEvents()
    try:
        assert dialog.search_settings.accessibleName() == "Search settings"
        assert len(dialog._search_entries) == len({
            id(entry["widget"]) for entry in dialog._search_entries
        })

        dialog.search_settings.setText("window frame")
        qapp.processEvents()
        assert dialog.search_results.count() == 1
        assert "Backdrop window frame" in dialog.search_results.item(0).text()
        dialog._activate_first_search_result()
        qapp.processEvents()

        assert dialog.tabs.tabText(dialog.tabs.currentIndex()) == "Frame"
        assert qapp.focusWidget() is dialog.backdrop_frame
        assert dialog.backdrop_frame.property("settingsSearchMatch") is True
        assert dialog.backdrop_frame.graphicsEffect() is not None

        # This phrase comes from the spin box's help/tooltip, not just its label.
        dialog.search_settings.setText("countdown duration after region")
        qapp.processEvents()
        result_indices = {
            dialog.search_results.item(i).data(Qt.UserRole)
            for i in range(dialog.search_results.count())
        }
        assert len(result_indices) == dialog.search_results.count()
        matched_widgets = {
            dialog._search_entries[index]["widget"] for index in result_indices
        }
        assert matched_widgets == {dialog.timer_seconds}

        dialog.search_settings.clear()
        qapp.processEvents()
        assert dialog.search_results.isHidden()
        assert dialog._search_highlight is None
        assert dialog.backdrop_frame.property("settingsSearchMatch") is False
    finally:
        dialog.close()


def test_settings_keyboard_order_enters_visible_tab_controls(qapp):
    from settings_dialog import SettingsDialog

    dialog = SettingsDialog()
    dialog.show()
    qapp.processEvents()
    try:
        dialog.search_settings.setFocus()
        qapp.processEvents()
        QTest.keyClick(dialog.search_settings, Qt.Key_Tab)
        qapp.processEvents()
        assert qapp.focusWidget() is dialog.tabs.tabBar()

        visited = []
        for _ in range(5):
            current = qapp.focusWidget()
            QTest.keyClick(current, Qt.Key_Tab)
            qapp.processEvents()
            visited.append(qapp.focusWidget())
            if qapp.focusWidget() is dialog.launch_startup:
                break
        assert dialog.launch_startup in visited
        assert all(widget.isVisible() for widget in visited)
    finally:
        dialog.close()


def test_apply_failure_keeps_dialog_open_and_restores_runtime_settings(
        qapp, monkeypatch):
    import settings_dialog

    config = settings_dialog.config
    previous_theme = config.THEME
    dialog = settings_dialog.SettingsDialog()
    dialog.theme.setCurrentIndex(
        next(i for i in range(dialog.theme.count())
             if dialog.theme.itemData(i) != previous_theme)
    )
    warnings = []
    monkeypatch.setattr(config, "save", lambda: False)
    monkeypatch.setattr(
        settings_dialog.QMessageBox,
        "warning",
        staticmethod(lambda *args: warnings.append(args)),
    )

    dialog._apply_and_close()

    assert config.THEME == previous_theme
    assert dialog.result() == 0
    assert warnings and warnings[0][1] == "Settings Not Saved"
    dialog.close()
