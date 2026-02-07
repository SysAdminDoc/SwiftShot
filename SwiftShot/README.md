# SwiftShot v2.0

**A comprehensive, debloated screenshot tool for Windows.**

A feature-complete Greenshot replacement built from scratch without any 3rd-party integrations, plugin system, or cloud upload bloat.

## What's Removed vs Greenshot

| Greenshot Bloat | SwiftShot |
|---|---|
| Imgur / Dropbox / Box / Flickr plugins | No cloud uploads |
| Jira / Confluence plugins | No enterprise integrations |
| Office COM interop | No Office dependencies |
| Plugin discovery / loading system | No plugin overhead |
| OAuth / API key infrastructure | Zero network calls |
| .NET Framework + 12 plugin DLLs | Python + 2 packages |

## Features

### Capture Modes
- **PrintScreen** popup menu with every capture mode
- **Region** with smart edge snapping and color picker
- **Freehand Region** -- draw any shape
- **Window Capture** -- Greenshot-exact behavior (700ms quintic ease-out animation, PgDown/PgUp hierarchy navigation)
- **Fullscreen / Per-monitor** capture
- **Last Region** re-capture
- **Scrolling Capture** -- auto-scroll and stitch full scrollable windows
- **OCR Region** -- extract text via Windows built-in OCR or Tesseract
- **Timed Capture** with animated countdown overlay

### Image Editor
| Tool | Key | Description |
|------|-----|-------------|
| Select | V | Pan and select |
| Crop | C | Crop with rule-of-thirds guide |
| Rectangle | R | Draw rectangles |
| Ellipse | E | Draw ellipses |
| Line | L | Straight lines |
| Arrow | A | Arrows with arrowheads |
| Freehand | F | Freehand strokes |
| Text | T | Multi-line text annotations |
| Highlight | H | Semi-transparent highlight |
| Obfuscate | O | Pixelate or blur sensitive areas |
| Step Number | N | Auto-incrementing numbered circles |
| Ruler | M | Measure pixel distances |
| Eyedropper | I | Pick color from image |

**Editor extras:** Undo/Redo (deep-copied state), Auto-crop, Rotate/Flip, Border/Shadow/Rounded Corners, Image Diff overlay, Quick-Annotate Templates, Zoom (Ctrl+scroll), Pan (Space+drag), Dirty state tracking, Save/Copy/Print/Pin.

### Pin to Desktop
Always-on-top borderless floating screenshot windows. Drag to move, scroll to resize, right-click for opacity controls.

### Capture History
Thumbnail panel of recent captures with quick actions (re-open, copy, pin, delete).

### Clipboard Watcher
Auto-detect new clipboard images and open them in the editor.

### Global Hotkeys
| Hotkey | Action |
|--------|--------|
| PrintScreen | Capture menu popup |
| Alt+PrintScreen | Window capture |
| Ctrl+PrintScreen | Monitor picker / fullscreen |
| Shift+PrintScreen | Last region re-capture |

### Dark Theme
Full Catppuccin Mocha color scheme throughout.

## Installation

```
pip install -r requirements.txt
python main.py
```

## Build

```powershell
.\Build-SwiftShot.ps1
```

## File Structure

```
main.py               Entry point
app.py                System tray + capture orchestration
capture.py            Screenshot capture (Win32 + Qt)
overlay.py            Region selector + edge snapping + color picker
window_picker.py      Greenshot-exact window capture
editor.py             Full annotation editor
config.py             JSON settings with backup
hotkeys.py            WH_KEYBOARD_LL global hotkeys
ocr.py                Windows WinRT OCR + Tesseract
theme.py              Catppuccin Mocha dark theme
settings_dialog.py    Preferences UI
capture_menu.py       PrintScreen popup menu
monitor_picker.py     Multi-monitor selection
pin_window.py         Always-on-top floating windows
capture_history.py    Recent captures panel
countdown_overlay.py  Timed capture countdown
scrolling_capture.py  Scrolling window capture
utils.py              Shared utilities
```

## License
GPL-3.0
