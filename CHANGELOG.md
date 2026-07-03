# Changelog

All notable changes to SwiftShot will be documented in this file.

## [v2.7.0] - 2026-07-03

Deep audit release: ~50 verified fixes across correctness, data safety, UX,
theming, accessibility and performance.

### Capture
- Freehand region capture now masks the result to the drawn shape (it
  silently produced the bounding rectangle before), including timed captures.
- Per-monitor capture and monitor-picker thumbnails grab via each monitor's
  own QScreen — correct under 125%/mixed DPI scaling.
- Timed-capture countdown is a small click-to-cancel corner badge that never
  steals focus; the old full-screen tinted overlay blocked all interaction
  with the desktop, defeating the feature's purpose.
- Camera sound plays when a capture completes instead of when the selection
  overlay grabs its backdrop.
- GIF output format works (routed through Pillow — Qt cannot encode GIF);
  failed direct saves surface a tray warning instead of failing silently.
- Scrolling capture refuses to target its own dialog.

### Hotkeys
- Rebinding takes effect immediately — no restart required.
- Digits, arrows, Tab, Insert, Delete, Home/End, PageUp/Down, Pause and
  ScrollLock recorded in Settings now actually fire (the parser only knew
  letters and F-keys, so those bindings were silently dead).
- Duplicate shortcut assignments are rejected with a clear warning.

### Editor
- Unsaved changes prompt Save/Discard/Cancel on close; app exit routes
  through the same prompt. Titles show a dirty marker.
- Removed the undeclared scipy dependency (warp tool, magnetic lasso and
  Bevel & Emboss crashed the whole app on first use in packaged builds).
- Unhandled errors no longer terminate the app: the crash handler logs to
  %APPDATA%\SwiftShot\crash.log and keeps your work open.
- Undo no longer strips layer masks, effects and groups.
- Ctrl+S no longer overwrites a stale .swiftshot project after switching
  documents; Open Recent loads projects with masks/effects/groups intact.
- Free Transform and Perspective handle dragging works (both tools were
  inert); selecting them from the toolbar no longer crashes.
- Quick Mask painting goes to the mask, not the layer image.
- Motion Blur works at all sizes; vibrance is ~1000x faster (vectorized);
  gradients render on transparent layers; soft-brush mask painting darkens
  instead of inverting; Merge Down respects layer masks.
- Layer Effects dialog no longer renders two stacked UIs with duplicate
  OK/Cancel buttons.
- Ctrl+V pastes from the OS clipboard when the internal clipboard is empty.
- Settings are wired: default color, line width, font size/family seed new
  editors, and "Reuse existing editor window" works (clean editors only).
- Channels-panel visibility debugging is no longer baked into saved files.

### Theming & accessibility
- Capture history, monitor picker, scrolling capture, OCR result and the
  pin/thumbnail context menus follow the light theme (they hardcoded the
  dark palette); control borders are visible on light surfaces.
- History thumbnails and monitor cards are keyboard-accessible (focus ring,
  Enter/Space activate, Delete removes, menu key opens the context menu);
  monitor picker accepts digit keys 1-9 and A for all monitors.
- Capture menu shortcut column uses real tab alignment.

### Reliability & performance
- Update notifications work when clicked (release page opens) and a
  "Download Update" entry is added to the tray menu.
- Clipboard watcher is event-driven (no 1-second polling), no longer misses
  same-size images, and ignores SwiftShot's own copies.
- Settings loaded/imported from JSON are type-validated and enum-checked, so
  malformed files cannot corrupt runtime settings; corrupt configs are
  backed up and logged. Reset to Defaults resets recent colors correctly.
- OCR of a region with no text reports "no text detected" instead of an
  install-Tesseract error dialog.
- Region overlay no longer converts the full multi-monitor screenshot on
  every repaint; window-picker animation stopped copying a window-sized
  pixmap 60 times per second; history search is debounced and escapes SQL
  LIKE wildcards.
- Removed dead settings (minimize-to-tray, language) and ~50 unused
  imports/locals; line endings normalized via .gitattributes.
- Test suite grew from 34 to 54 tests (regression coverage for the above).

## [v2.6.5] - 2026-06-16

- Added optional auto-OCR indexing for searchable capture history.
- Added SQLite-backed capture history with SHA-256 duplicate detection, thumbnail cache, and date/filename search.
- Added screenshot beautification presets that apply padding, rounded corners, and drop shadow after capture.
- Added ordered post-capture workflows so save, clipboard, and editor actions can run in sequence.
- Added a persisted dark/light theme option with WCAG contrast coverage.
- Added rich filename templates with app, window title, user, dimensions, and counter variables.
- Added lossless WebP as an output format for direct capture saves and editor exports.
- Added accessibility names/descriptions to capture and settings controls, plus keyboard activation for capture menu actions.
- Unified the image editor colors with the main Catppuccin Mocha application theme.
- Fixed editor smudge undefined-coordinate handling and removed runtime package installation from optional background removal.
- Added Windows CI for Ruff, pytest, and portable PyInstaller build verification.
- Added a pytest suite covering config persistence, version metadata, utility helpers, capture cropping, and OCR fallback behavior.
- Fixed README package and source line-count accuracy.
- Added confirmation prompts before deleting a single capture history item or clearing all capture history images.
- Fixed P0 packaging hygiene: centralized the app version, aligned licensing, corrected dependency declarations, removed editor auto-install bootstrap behavior, kept NumPy in builds, and removed hardcoded developer paths from launch/build artifacts.
- Added: Add files via upload
- Removed: Delete __pycache__ directory
- Removed: Delete SwiftShot directory
- Changed: Update README.md
- Create README.md
- up
- Added: Add files via upload
