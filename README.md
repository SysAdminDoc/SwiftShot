<h1 align="center">SwiftShot</h1>

<p align="center">
  <strong>A fast, bloat-free screenshot tool for Windows.</strong><br>
  Full-featured Greenshot replacement — no plugins, no cloud, no telemetry.
</p>

<p align="center">
  <a href="#installation"><img alt="Windows 10/11" src="https://img.shields.io/badge/Windows-10%2F11-0078D6?logo=windows&logoColor=white"></a>
  <img alt="Version 2.8.0" src="https://img.shields.io/badge/Version-2.8.0-89b4fa">
  <a href="#license"><img alt="License: GPL-3.0" src="https://img.shields.io/badge/License-GPL--3.0-blue.svg"></a>
  <img alt="Python 3.12" src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white">
  <img alt="Lines of code" src="https://img.shields.io/badge/Lines_of_Code-18k-green">
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
| OAuth / API key infrastructure | No accounts, telemetry, or capture uploads |
| .NET Framework + 12 plugin DLLs | Python + three core packages |

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

A full layer-based editor opens after every capture (configurable) — closer
to a lightweight Photoshop than a markup bar.

- **Layers** — reorder, group, blend modes, per-layer opacity, layer masks,
  and non-destructive layer effects (drop shadow, glow, bevel, stroke,
  color/gradient overlay)
- **Selection** — rectangular/elliptical marquee, lasso, magnetic lasso,
  magic wand, select-by-color, Quick Mask, feather/expand/contract
- **Paint & retouch** — brush/pencil/spray/eraser with soft brushes, clone
  stamp, healing, dodge/burn/sponge/smudge, red-eye removal, content-aware
  fill, gradient and pattern fills
- **Shapes & text** — rectangles, ellipses, lines, arrows, polygons, stars,
  multi-line text with font picker, sticky notes
- **Transform** — move, crop with aspect presets, free transform,
  perspective, warp (move/grow/shrink/swirl), rotate/flip, resize
- **Adjust & filter** — brightness/contrast, levels, curves, HSL, vibrance,
  gamma, threshold, blurs (gaussian/box/motion), sharpen, artistic filters
- **Workflow** — undo history panel, guides and rulers, navigator, command
  palette, `.swiftshot` project files that preserve layers and masks,
  export to PNG/JPEG/WebP/BMP/TIFF, copy to clipboard, pin to desktop,
  OCR from the editor, unsaved-changes protection, and atomic crash-recovery
  journals with a restore/discard preview on the next launch

### Pin to Desktop

Pin any screenshot as an always-on-top borderless floating window. Drag to reposition, scroll to resize, right-click for opacity controls. Open as many as you want.

### Capture History

A SQLite-backed thumbnail panel of recent captures with duplicate detection,
thumbnail caching, date/filename/OCR search, and quick actions: re-open in
editor, copy to clipboard, pin to desktop, or delete. Startup runs a bounded
database health check; a damaged index is quarantined and rebuilt from the
untouched capture files with a visible notice. Auto-OCR indexing can be enabled
in Advanced settings.

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

```powershell
git clone https://github.com/SysAdminDoc/SwiftShot.git
cd SwiftShot
py -3.12 -m pip install -r requirements.txt
py -3.12 App\main.py
```

Requirements: CPython 3.12.x and Windows 10/11. Other Python versions exit
before loading the GUI with the exact command needed to use 3.12.

Commands in this README run from the repository root. From `App\`, the
equivalent launch and build commands are `py -3.12 main.py` and
`.\Build-SwiftShot.ps1`.

### Option 2: Portable Executable

Download `SwiftShot-Portable.exe` from [Releases](https://github.com/SysAdminDoc/SwiftShot/releases). Single file, no install, no Python needed. Run from anywhere.

### Option 3: Windows Installer

Download `SwiftShot-Setup.exe` from [Releases](https://github.com/SysAdminDoc/SwiftShot/releases). Includes Start Menu shortcut, optional auto-start, and a proper uninstaller in Add/Remove Programs.

---

## Building from Source

The build script creates both a portable `.exe` and a Windows installer. It
selects CPython 3.12 through the Windows launcher (even if another `python` is
first on `PATH`) and recreates an older build virtual environment automatically.

```powershell
# Full build (portable + installer)
.\App\Build-SwiftShot.ps1

# Portable only (no Inno Setup required)
.\App\Build-SwiftShot.ps1 -PortableOnly

# Clean rebuild
.\App\Build-SwiftShot.ps1 -Clean

# Debug build (console window visible)
.\App\Build-SwiftShot.ps1 -Clean -DebugBuild
```

The script will:
1. Verify CPython 3.12.x and Inno Setup 6 (optional)
2. Create an isolated build venv with PyInstaller and stage the official,
   SHA3-verified SQLite 3.53.3 Windows runtime
3. Generate multi-resolution icon from source
4. Build and SQLite-version-probe `SwiftShot-Portable.exe` (single file)
5. Build and probe `SwiftShot-Setup.exe` via Inno Setup (if available)

Both outputs are fully self-contained — no Python or runtime needed on end-user machines.

> **Inno Setup** is only needed for the installer build. Get it free from [jrsoftware.org](https://jrsoftware.org/isdl.php). Portable builds work without it.

---

## Configuration

Settings are stored in `%APPDATA%\SwiftShot\swiftshot.json`. Access them from the tray icon menu or within the editor.

Available tabs: **General**, **Capture**, **Hotkeys**, **Output**, **Editor**,
**Frame**, **Advanced**. Every tab scrolls to fit the current work area and
text scale. Search matches setting labels and help text, then opens the owning
tab and focuses the real control. The **Frame** tab adds a border, drop shadow,
rounded corners, and an optional padded solid/gradient backdrop behind every
capture.

Notable settings include an ordered post-capture workflow (editor / save / clipboard), dark/light theme, beautification presets, output format (PNG, JPEG, BMP, GIF, TIFF, lossless WebP, or AVIF where supported), filename pattern, timed capture duration, clipboard watcher, and launch-at-startup.
Filename patterns support `{YYYY}`, `{MM}`, `{DD}`, `{hh}`, `{mm}`, `{ss}`, `{app}`, `{title}`, `{user}`, `{counter}`, `{w}`, and `{h}`.

Settings can be exported/imported as JSON and reset to defaults at any time.

### Timed Capture

Enable the timer checkbox in the capture menu or in Settings > Capture. The workflow is:

1. Press PrintScreen and select your region or window as usual
2. The overlay closes and a countdown begins (1–30 seconds, configurable)
3. Interact with the screen — hover tooltips, open context menus, type into fields
4. When the timer ends, SwiftShot takes a fresh screenshot of that exact region

This is designed for capturing UI elements that require manual interaction, like dropdown menus, hover states, or drag operations.

---

## Command-Line Interface

SwiftShot doubles as a scriptable capture tool. With any capture flag it runs
headless and exits without the tray:

```powershell
py -3.12 App\main.py --region 0,0,800,600 --out shot.png
py -3.12 App\main.py --fullscreen --out desktop.png
py -3.12 App\main.py --monitor 1 --out screen1.png
py -3.12 App\main.py --region 0,0,800,600 --ocr
py -3.12 App\main.py --diagnostics
```

`--out` picks the format from the file extension (png/jpg/webp/avif/bmp/tiff).
`--ocr` can be combined with `--out`. Without capture flags — or with a bare
image path — SwiftShot launches its tray application as usual. Release builds
accept the same arguments through `SwiftShot.exe`.

## Project Structure

Application modules live under `App/`:

```
main.py                 Tray/headless entry point, logging, crash handler
runtime_contract.py     Python-version and physical-pixel DPI policy
app_control.py          Local installer shutdown handshake
cli.py                  Scriptable headless capture (argparse)
app.py                  System tray, hotkey management, capture orchestration
capture.py              Screenshot engine (Win32 GDI + Qt fallback)
overlay.py              Region selector with edge snapping
window_picker.py        Window capture with animated highlight
editor.py               Layer-based image editor (8,500+ lines)
layers.py               Layer/group/history data model
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
safe_io.py              Bounded image/project input validation
diagnostics.py          Local support-bundle generation
recovery.py             Atomic dirty-document journals and recovery discovery
updater.py              GitHub release update checker
logger.py               Rotating file logger
utils.py                Virtual geometry, color helpers, startup registry
generate_icon.py        Programmatic icon generation for builds
```

28 Python modules — **18,000+ lines of code** — no capture upload service.

---

## Dependencies

| Package | Purpose |
|---|---|
| [PyQt5](https://pypi.org/project/PyQt5/) | GUI framework |
| [Pillow](https://pypi.org/project/Pillow/) | Image processing for scrolling capture stitching |
| [NumPy](https://pypi.org/project/numpy/) | Pixel math for editor filters and selection tools |

That's the core runtime. OCR uses the Windows built-in WinRT engine (no Python
package needed) with an optional local Tesseract + `pytesseract` fallback.
Background removal is also optional and requires `rembg`; its upstream package
[downloads a model on first use](https://github.com/danielgatis/rembg#models)
unless that model is already present in its cache.

### Network behavior

When **Check for updates** is enabled (the default), startup sends one HTTPS
GET to the GitHub Releases API for version metadata. Disable it in Settings >
Advanced for fully offline core operation. SwiftShot sends no screenshot,
clipboard, OCR, history, or configuration content. The optional `rembg`
first-use model download described above is controlled by that separately
installed package.

---

## Testing

```powershell
py -3.12 -m pip install -r requirements-dev.txt
py -3.12 -m pytest
```

---

## License

[GPL-3.0](LICENSE)
