# SwiftShot

**A comprehensive, debloated screenshot tool for Windows.**

A feature-complete Greenshot replacement, built from scratch without any 3rd-party integrations, plugin system, or cloud upload bloat. All of Greenshot's core features, plus extras.

## What's Removed vs Greenshot

| Greenshot Bloat | SwiftShot |
|-----------------|-----------|
| Imgur / Dropbox / Box / Flickr plugins | No cloud uploads |
| Jira / Confluence plugins | No enterprise integrations |
| Office COM interop | No Office dependencies |
| Plugin discovery / loading system | No plugin overhead |
| OAuth / API key infrastructure | Zero network calls |
| .NET Framework + 12 plugin DLLs | Python + 2 packages |

## What's Included (Feature Parity + Extras)

### PrintScreen Capture Menu
Press **PrintScreen** to get a popup menu with every capture mode:
- **Screen 1 / 2 / 3** -- capture a specific monitor (shows resolution)
- **All Screens** -- capture the full virtual desktop
- **Window Mode** -- Greenshot-style interactive window picker
- **Region** -- rectangular region drag-select
- **Region (Freehand)** -- draw any shape, captures bounding box
- **Last Region** -- re-capture previous area
- **OCR Region** -- select an area, extract text via OCR
- **Open from File / Clipboard**

### Window Capture (Greenshot-Exact)
Matches Greenshot's `CaptureForm.cs` behavior precisely:
- MediumSeaGreen semi-transparent overlay (exact Greenshot colors)
- 700ms Quintic ease-out animation from cursor to window bounds
- **PgDown** to drill into child window elements (browser viewports, panels, frames)
- **PgUp** to return to parent window
- **Space** to toggle to Region capture mode (and back)
- **Z** to toggle zoom magnifier
- **Arrow keys** to nudge cursor 1px, **Ctrl+Arrow** for 10px
- **Enter/Click** to confirm, **Escape** to cancel
- Pre-enumerated window detection (no self-overlay interference)

### OCR (Text Extraction)
- Uses Windows 10/11 built-in OCR engine (zero dependencies on Win10+)
- Falls back to Tesseract/pytesseract if available
- Available from capture menu, editor toolbar, and editor menu (Ctrl+Shift+O)
- Results auto-copied to clipboard

### Image Editor
Full annotation toolkit:
- **Select/Pan** -- click-drag to pan the canvas, scroll wheel to scroll, Space+drag panning with any tool
- **Crop** with rule-of-thirds grid overlay
- **Rectangle / Ellipse** (filled or outline)
- **Line / Arrow** (proper arrowhead geometry)
- **Freehand** drawing
- **Text** (with font selection)
- **Highlight** (semi-transparent overlay)
- **Obfuscate** (pixelate/blur sensitive areas)
- **Step Numbers** (numbered circles for tutorials)
- **OCR** button to extract text from current image
- 50-level undo/redo stack
- Auto-crop, rotate, flip
- Zoom 25%-400% (Ctrl+Scroll, Ctrl+0 fit, Ctrl+1 100%)
- Save: PNG, JPEG (quality 1-100%), BMP, GIF, TIFF
- Copy to clipboard, Print

## Installation

### One-Click Installer (Recommended)
```powershell
.\Install-SwiftShot.ps1
```

The installer handles everything:
1. Finds or installs Python 3.8+ (via winget)
2. Creates an isolated virtual environment
3. Installs PyQt5 and Pillow
4. Generates a program icon
5. Creates Desktop and Start Menu shortcuts
6. Optionally launches immediately

#### Installer Options
```powershell
.\Install-SwiftShot.ps1                # Standard install
.\Install-SwiftShot.ps1 -AddToStartup  # Also add to Windows Startup
.\Install-SwiftShot.ps1 -NoShortcuts   # Skip creating shortcuts
.\Install-SwiftShot.ps1 -Uninstall     # Remove venv, shortcuts, startup
```

### Manual / Dev Setup
```
pip install PyQt5 Pillow
python main.py
```

### Build Standalone .exe (Optional)
```powershell
.\build.ps1 -OneFile    # Output: dist\SwiftShot.exe
```

## Keyboard Shortcuts

### Global Hotkeys
| Key | Action |
|-----|--------|
| `PrintScreen` | Capture menu (all modes) |
| `Alt + PrintScreen` | Window capture (interactive) |
| `Ctrl + PrintScreen` | Fullscreen / monitor picker |
| `Shift + PrintScreen` | Last region re-capture |

### During Window Capture
| Key | Action |
|-----|--------|
| `PgDown` | Drill into child window elements |
| `PgUp` | Return to parent window |
| `Space` | Toggle to Region mode |
| `Z` | Toggle zoom magnifier |
| `Arrow keys` | Nudge cursor 1px |
| `Ctrl + Arrows` | Nudge cursor 10px |
| `Enter / Click` | Confirm capture |
| `Escape` | Cancel |

### During Region Capture
| Key | Action |
|-----|--------|
| `Space` | Toggle to Window mode |
| `Escape` | Cancel |

### Editor
| Key | Action |
|-----|--------|
| `V` | Select/Pan tool |
| `C` | Crop |
| `R` / `E` / `L` / `A` | Rectangle / Ellipse / Line / Arrow |
| `F` / `T` / `H` / `O` / `N` | Freehand / Text / Highlight / Obfuscate / Step |
| `Ctrl+Z` / `Ctrl+Y` | Undo / Redo |
| `Ctrl+S` | Quick Save |
| `Ctrl+Shift+C` | Copy to clipboard |
| `Ctrl+Shift+O` | OCR (extract text) |
| `Ctrl+P` | Print |
| `Ctrl+=` / `Ctrl+-` | Zoom in/out |
| `Ctrl+0` / `Ctrl+1` | Zoom to fit / 100% |
| `Space + drag` | Pan canvas (any tool) |
| `Middle-click drag` | Pan canvas (any tool) |
| `Scroll wheel` | Scroll canvas |
| `Ctrl + Scroll` | Zoom |

## Project Structure

```
SwiftShot/
    Install-SwiftShot.ps1   # <-- RUN THIS (one-click installer)
    main.py                  # Entry point, dependency check, DPI awareness
    app.py                   # System tray, hotkeys, capture orchestration
    capture.py               # Screen capture (fullscreen, window, region)
    capture_menu.py          # PrintScreen popup menu with all modes
    overlay.py               # Region selection (rectangle + freehand)
    window_picker.py         # Greenshot-exact interactive window capture
    monitor_picker.py        # Multi-monitor selection dialog
    ocr.py                   # OCR engine (Windows OCR + Tesseract fallback)
    editor.py                # Full image editor with all tools + OCR
    hotkeys.py               # Global hotkey registration (Win32 API)
    settings_dialog.py       # Preferences UI
    config.py                # Settings persistence (JSON)
    theme.py                 # Dark theme (Catppuccin Mocha)
    build.ps1                # PyInstaller build script (optional)
    requirements.txt         # Python dependencies
```

## Configuration

Settings are stored in JSON:
- **Windows:** `%APPDATA%\SwiftShot\swiftshot.json`
- **Linux:** `~/.config/SwiftShot/swiftshot.json`

## License

GPL-3.0 (same as Greenshot)
