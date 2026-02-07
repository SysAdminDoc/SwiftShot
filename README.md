<p align="center">
  <img src="swiftshot.png" alt="SwiftShot" width="128" height="128">
</p>

<h1 align="center">SwiftShot</h1>

<p align="center">
  <strong>A fast, bloat-free screenshot tool for Windows.</strong><br>
  Full-featured Greenshot replacement — no plugins, no cloud, no telemetry.
</p>

<p align="center">
  <a href="#installation"><img alt="Windows 10/11" src="https://img.shields.io/badge/Windows-10%2F11-0078D6?logo=windows&logoColor=white"></a>
  <a href="#license"><img alt="License: GPL-3.0" src="https://img.shields.io/badge/License-GPL--3.0-blue.svg"></a>
  <img alt="Python 3.8+" src="https://img.shields.io/badge/Python-3.8%2B-3776AB?logo=python&logoColor=white">
  <img alt="Lines of code" src="https://img.shields.io/badge/Lines_of_Code-7.6k-green">
</p>

---

## Why SwiftShot?

Greenshot is great, but it ships with a dozen cloud upload plugins, enterprise integrations, OAuth infrastructure, and a full .NET plugin loading system that most people never use. SwiftShot strips all of that out and focuses on what matters: capturing screenshots fast, annotating them, and getting back to work.

| Greenshot Bloat | SwiftShot |
|---|---|
| Imgur / Dropbox / Box / Flickr plugins | No cloud uploads — your screenshots stay local |
| Jira / Confluence integrations | No enterprise dependencies |
| Office COM interop | No Office requirement |
| Plugin discovery & loading system | No plugin overhead |
| OAuth / API key infrastructure | Zero network calls (except optional update check) |
| .NET Framework + 12 plugin DLLs | Python + PyQt5 — two packages |

## Features

### Capture Modes

- **PrintScreen Menu** — press PrintScreen and pick any mode from a popup
- **Region Capture** — drag to select with smart edge snapping to window borders
- **Freehand Region** — draw any arbitrary shape
- **Window Capture** — click any window with Greenshot-exact behavior (animated highlight, PgUp/PgDown to walk the window hierarchy)
- **Fullscreen / Per-Monitor** — capture one monitor or all of them
- **Last Region** — re-capture the same area instantly
- **Scrolling Capture** — auto-scroll and stitch an entire scrollable window into one tall image
- **OCR Region** — select an area and extract text using Windows built-in OCR or Tesseract
- **Timed Capture** — select your region first, then a countdown gives you time to hover tooltips, open menus, or interact with the screen before the shot fires

### Image Editor

A full annotation editor opens after every capture (configurable).

| Tool | Key | |
|------|:---:|---|
| Select / Pan | `V` | Pan canvas, drag-and-drop export |
| Crop | `C` | Crop with rule-of-thirds guides |
| Rectangle | `R` | Outlined or filled rectangles |
| Ellipse | `E` | Outlined or filled ellipses |
| Line | `L` | Straight lines |
| Arrow | `A` | Lines with arrowheads |
| Freehand | `F` | Free-form pen strokes |
| Text | `T` | Multi-line text with font picker |
| Highlight | `H` | Semi-transparent marker |
| Obfuscate | `O` | Pixelate or blur sensitive areas |
| Step Number | `N` | Auto-incrementing numbered badges |
| Ruler | `M` | Measure pixel distances |
| Eyedropper | `I` | Pick any color from the image |

**Additional editor features:** unlimited undo/redo, auto-crop, rotate/flip, brightness/contrast/grayscale/invert adjustments, border/shadow/rounded corners, image diff overlay, quick-annotate templates (bug report, tutorial, redact), zoom with Ctrl+scroll, pan with Space+drag, recent colors bar, drag-and-drop export to other apps, and dirty-state tracking.

### Pin to Desktop

Pin any screenshot as an always-on-top borderless floating window. Drag to reposition, scroll to resize, right-click for opacity controls. Open as many as you want.

### Capture History

A thumbnail panel of recent captures with quick actions: re-open in editor, copy to clipboard, pin to desktop, or delete.

### Clipboard Watcher

Monitors the clipboard and auto-opens the editor when a new image is copied from any application.

### Configurable Hotkeys

All shortcuts are remappable through Settings with a live key recorder — click the field, press your combo, done.

| Default Hotkey | Action |
|---|---|
| `PrintScreen` | Capture menu popup |
| `Alt+PrintScreen` | Window capture |
| `Ctrl+PrintScreen` | Fullscreen / monitor picker |
| `Shift+PrintScreen` | Last region re-capture |

OCR, freehand, and scrolling capture can also be bound to custom hotkeys.

### Region ↔ Window Toggle

Press `Space` during region selection to switch to window mode (and vice versa) without restarting the capture.

### Dark Theme

Full [Catppuccin Mocha](https://github.com/catppuccin/catppuccin) color scheme across every window, dialog, menu, and overlay.

---

## Installation

### Option 1: Run from Source

```bash
git clone https://github.com/SysAdminDoc/SwiftShot.git
cd SwiftShot
pip install -r requirements.txt
python main.py
```

Requirements: Python 3.8+ and Windows 10/11.

### Option 2: Portable Executable

Download `SwiftShot-Portable.exe` from [Releases](https://github.com/SysAdminDoc/SwiftShot/releases). Single file, no install, no Python needed. Run from anywhere.

### Option 3: Windows Installer

Download `SwiftShot-Setup.exe` from [Releases](https://github.com/SysAdminDoc/SwiftShot/releases). Includes Start Menu shortcut, optional auto-start, and a proper uninstaller in Add/Remove Programs.

---

## Building from Source

The build script creates both a portable `.exe` and a Windows installer. All you need is Python 3.8+ — everything else is handled automatically.

```powershell
# Full build (portable + installer)
.\Build-SwiftShot.ps1

# Portable only (no Inno Setup required)
.\Build-SwiftShot.ps1 -PortableOnly

# Clean rebuild
.\Build-SwiftShot.ps1 -Clean

# Debug build (console window visible)
.\Build-SwiftShot.ps1 -Clean -DebugBuild
```

The script will:
1. Verify Python 3.8+ and Inno Setup 6 (optional)
2. Create an isolated build venv with PyInstaller
3. Generate multi-resolution icon from source
4. Build `SwiftShot-Portable.exe` (single file, ~25 MB)
5. Build `SwiftShot-Setup.exe` via Inno Setup (if available)

Both outputs are fully self-contained — no Python or runtime needed on end-user machines.

> **Inno Setup** is only needed for the installer build. Get it free from [jrsoftware.org](https://jrsoftware.org/isdl.php). Portable builds work without it.

---

## Configuration

Settings are stored in `%APPDATA%\SwiftShot\swiftshot.json`. Access them from the tray icon menu or within the editor.

Available tabs: **General**, **Capture**, **Hotkeys**, **Output**, **Editor**, **Frame**, **Advanced**.

Notable settings include after-capture action (editor / save / clipboard), output format and filename pattern, timed capture duration, clipboard watcher, and launch-at-startup.

Settings can be exported/imported as JSON and reset to defaults at any time.

### Timed Capture

Enable the timer checkbox in the capture menu or in Settings > Capture. The workflow is:

1. Press PrintScreen and select your region or window as usual
2. The overlay closes and a countdown begins (1–30 seconds, configurable)
3. Interact with the screen — hover tooltips, open context menus, type into fields
4. When the timer ends, SwiftShot takes a fresh screenshot of that exact region

This is designed for capturing UI elements that require manual interaction, like dropdown menus, hover states, or drag operations.

---

## Project Structure

```
main.py                 Entry point, logging, crash handler
app.py                  System tray, hotkey management, capture orchestration
capture.py              Screenshot engine (Win32 GDI + Qt fallback)
overlay.py              Region selector with edge snapping
window_picker.py        Window capture with animated highlight
editor.py               Full annotation editor (1,920 lines)
config.py               JSON settings with backup, import/export
settings_dialog.py      Preferences UI with hotkey recorder
hotkeys.py              WH_KEYBOARD_LL global keyboard hook
capture_menu.py         PrintScreen popup menu with timer controls
ocr.py                  Windows WinRT OCR + Tesseract fallback
ocr_dialog.py           OCR result display
theme.py                Catppuccin Mocha dark theme
monitor_picker.py       Multi-monitor selection dialog
pin_window.py           Always-on-top floating screenshot windows
capture_history.py      Recent captures thumbnail panel
countdown_overlay.py    Animated countdown timer overlay
scrolling_capture.py    Auto-scroll and stitch capture
updater.py              GitHub release update checker
logger.py               Rotating file logger
utils.py                Virtual geometry, color helpers, startup registry
generate_icon.py        Programmatic icon generation for builds
```

22 Python modules — **7,600+ lines of code** — zero external services.

---

## Dependencies

| Package | Purpose |
|---|---|
| [PyQt5](https://pypi.org/project/PyQt5/) | GUI framework |
| [Pillow](https://pypi.org/project/Pillow/) | Image processing for scrolling capture stitching |

That's it. OCR uses the Windows built-in WinRT OCR engine (no install needed on Windows 10/11) with an optional Tesseract fallback.

---

## License

[GPL-3.0](LICENSE)
