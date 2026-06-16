# Changelog

All notable changes to SwiftShot will be documented in this file.

## [v2.6.5] - 2026-06-16

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
