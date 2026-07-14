"""Shared accessibility helpers for SwiftShot's custom Qt surfaces."""

import re

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractButton, QAbstractItemView, QAbstractSlider, QAbstractSpinBox,
    QComboBox, QLineEdit, QScrollBar, QTabWidget, QWidget,
)


MIN_TARGET_SIZE = 24


def _plain_text(value):
    """Turn button/tooltip/QObject labels into a short spoken name."""
    value = str(value or "").replace("&", "").strip()
    if not value:
        return ""
    value = value.splitlines()[0].strip()
    value = re.sub(r"\s*\([^)]*(?:shortcut|Ctrl|Alt|Shift|F\d)[^)]*\)\s*$",
                   "", value, flags=re.IGNORECASE)
    return value.rstrip(":")


def _attribute_names(root):
    """Map controls to their stable Python attribute name when available."""
    result = {}
    for owner in (root, *root.findChildren(QWidget)):
        for name, value in vars(owner).items():
            if isinstance(value, QWidget) and not name.startswith("qt_"):
                spoken = name.strip("_").replace("_", " ").strip().title()
                if spoken:
                    result.setdefault(id(value), spoken)
            elif isinstance(value, dict):
                for key, child in value.items():
                    if isinstance(child, QWidget):
                        spoken = str(key).strip("_").replace("_", " ").strip().title()
                        if spoken:
                            result.setdefault(id(child), spoken)
    return result


def _is_internal_child(widget):
    name = widget.objectName()
    if name.startswith("qt_"):
        return True
    if isinstance(widget, QScrollBar):
        return True
    parent = widget.parent()
    while isinstance(parent, QWidget):
        if isinstance(parent, QComboBox):
            return True
        parent = parent.parent()
    return isinstance(widget, QLineEdit) and isinstance(widget.parent(), QAbstractSpinBox)


def configure_accessible_controls(root):
    """Name, focus and size native controls on a composite Qt surface.

    Native Qt controls already expose their role, state and action through
    UI Automation. This function supplies the missing application-specific
    name/description and prevents icon-only controls from dropping out of the
    keyboard focus order. It returns the controls covered by the release gate.
    """
    kinds = (
        QAbstractButton, QComboBox, QAbstractSpinBox, QLineEdit,
        QAbstractSlider, QAbstractItemView, QTabWidget,
    )
    attribute_names = _attribute_names(root)
    controls = []
    for widget in root.findChildren(kinds):
        if _is_internal_child(widget):
            continue
        controls.append(widget)
        tooltip = _plain_text(widget.toolTip())
        text = _plain_text(widget.text()) if isinstance(widget, QAbstractButton) else ""
        name = _plain_text(widget.accessibleName())
        if not name:
            name = tooltip or text or attribute_names.get(id(widget), "")
        if not name:
            if isinstance(widget, QTabWidget):
                name = "Editor panels"
        if not name:
            # This is a deterministic last resort for third-party/internal
            # composite controls. Project controls should normally be named by
            # a tooltip, visible label or stable owner attribute above.
            role = widget.metaObject().className().lstrip("Q").replace("Widget", "")
            name = f"SwiftShot {role}"
        widget.setAccessibleName(name)
        if tooltip and not widget.accessibleDescription() and tooltip != name:
            widget.setAccessibleDescription(tooltip)
        widget.setProperty("swiftshotAccessibleControl", True)

        if widget.focusPolicy() == Qt.NoFocus:
            widget.setFocusPolicy(Qt.StrongFocus)
        if isinstance(widget, QAbstractButton):
            widget.setMinimumSize(
                max(MIN_TARGET_SIZE, widget.minimumWidth()),
                max(MIN_TARGET_SIZE, widget.minimumHeight()),
            )
        elif isinstance(widget, (QAbstractSlider, QComboBox, QAbstractSpinBox,
                                 QLineEdit)):
            widget.setMinimumHeight(max(MIN_TARGET_SIZE, widget.minimumHeight()))
    return controls
