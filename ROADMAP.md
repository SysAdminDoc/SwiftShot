# SwiftShot Roadmap

Roadmap for SwiftShot - a fast, bloat-free Greenshot replacement for Windows (Python + PyQt5 + Win32 GDI + WinRT OCR). Focus: adding the handful of features users actually miss from Greenshot + CleanShot X without bringing the bloat back.

## AI Working Instructions (read before touching the backlog)

1. Read `CLAUDE.md` first — stack, build commands, architecture notes, gotchas. It is the source of truth.
2. House style: one-line ifs/semicolons are intentional (`ruff` E701/E702 stay noisy); only `py -3.12 -m ruff check --select F App tests` must be clean. LF line endings are pinned via `.gitattributes` — edit with tooling that preserves them, never shell redirection.
3. Verify every change: `py -3.12 -m pytest tests -q` (80 passing as of 2026-07-07) must stay green. Add a regression test for every fix that is headless-testable (offscreen `qapp` fixture in `tests/conftest.py`; bind editor methods to a stub instead of constructing the full `ImageEditor` — see `tests/test_project_io.py` for the pattern).
4. The backlog items below were produced by a 2026-07-07 multi-agent audit and each was verified by tracing the actual code path. Line numbers are approximate — locate by symbol name. If an item turns out to be already fixed or wrong when you trace it, delete it (don't force a change).
5. When you finish an item, DELETE it from this file (git history is the record — no `[x]` checkmarks). Commit in logical batches with conventional-commit messages; no AI authorship anywhere in git.
6. Item AB-01 is HALF-DONE and should be finished first — its press-side changes are already in the tree.

## Audit Backlog (2026-07-07)

### P2 — editor correctness

- [ ] AB-07 P2 — Rotated-view interactions ignore `canvas_angle`
  Why: `view_transform()` is `s = R(pan + zoom·p)` but (a) pan drag adds the raw screen delta (~1404), (b) wheel zoom-to-cursor anchors on the un-rotated cursor point (~1692), (c) `_xform_drag` scale un-rotates only by the object angle (~2681). With a rotated view, panning moves the canvas the wrong way and zoom drifts.
  Fix: helper that un-rotates a screen-space delta/point by `canvas_angle`; use in all three sites.

- [ ] AB-17 P2 — Full PIL recomposite on every hover repaint
  Why: `mouseMoveEvent` calls `update()` unconditionally (~1388) and every `paintEvent` calls `get_composite()` — a full Python flatten of all layers/masks/fx per mouse event.
  Fix: cache the composite, invalidate on actual edits; also rebuild quick-mask/rubylith pixmaps only when their source changes (~2179, ~2357).

### Carried research items (from RESEARCH.md, still open)

- [ ] R-01 P2 — Windows Graphics Capture backend with GDI fallback
  GDI BitBlt returns black for hardware-accelerated/protected/some UWP windows; WGC captures them and unlocks recording. `CAPTUREBLT` quick-win is DONE — this is the full backend. Touches `App/capture.py` (probe + fallback), optional dep `windows-capture` or `winrt-Windows.Graphics.Capture`. Complexity: L.
- [ ] R-02 P2 — Split editor.py into modules
  8,200+ lines in one file. Start with zero-Qt-coupling units: `core.py` (scaling/PIL↔Qt/numpy/theme) and `layers.py` (`Layer`/`HistoryManager`/`LayerGroup`). Full suite must pass unchanged. Complexity: L (first two modules: M).
- [ ] R-03 P2 — Editor accessibility pass
  Zero accessible metadata, no `setTabOrder`, no shortcut registry in the editor (capture surfaces already have names + a test). Primary controls need accessible names/descriptions, tab order, and coverage in `tests/test_accessibility.py`. Complexity: M.
- [ ] R-04 P2 — Tests for the remaining untested capture surfaces
  `overlay.py` (region select / edge snap) and `window_picker.py` (window-hierarchy walk) still have no coverage. (DONE: `scrolling_capture` stitching, `pin_window` scaling, and the editor compositor now have tests.) Complexity: M.
- [ ] R-09 P3 — OCR "copy as table" for structured captures
  Detect column/row structure from WinRT OCR word boxes; emit TSV/HTML to clipboard; fall back to flat text. Complexity: M.

## Planned Features

### Capture
- Multi-monitor DPI-aware scroll capture (currently single-monitor friendly)
- Scrolling capture for web apps using DevTools protocol where available (Chromium-only enhancement)
- Camera overlay and green-screen keying for "me + screen" tutorial captures
- GIF / MP4 short-recording with edit-after-capture frame picker
- Color-picker global hotkey that captures color under cursor to clipboard as hex

### Editor
- Magic wand / heal tool (LaMa ONNX) for object removal
- Speech bubble tool
- Badge / number-sequence tool with custom shape presets
- Auto-redact patterns (emails, phone numbers, IP/MAC)
- Vector export to SVG alongside PNG

### Pin & workflow
- Multiple pin windows snapping to grid with saved layouts
- Pinned window annotations (scribble directly on a pinned shot and it updates)
- Drag-to-reference: any pinned image is a drag source for other apps
- Quick-share targets: Imgur anonymous, self-hosted endpoint, clipboard, file
- Watch folder - auto-ingest images dropped into a configured folder

### OCR
- Translate OCR output via offline translation model or user-chosen API
- Barcode/QR decoder tool
- OCR-region capture returns both image and recognized text in clipboard

### Performance & robustness
- Migrate PyQt5 -> PyQt6
- Static-link build to trim .exe size and cold-start time
- Per-version auto-update via GitHub Releases (signed) — see AB-38 for the integrity requirement

### Config & deployment
- Portable-mode flag (settings next to exe) for USB stick use
- Admin-install MSIX with winget manifest
- Context-menu integration (right-click a file -> "Open in SwiftShot editor")

## Competitive Research

- **Greenshot** - the baseline. SwiftShot intentionally strips plugins; document clearly what's missing (Imgur-one-click, Office export) and whether each is on the roadmap.
- **ShareX** - kitchen sink with upload destinations and workflow chains; SwiftShot should *not* re-add cloud plugins but can take the "upload destination" concept as an optional user-configured endpoint.
- **CleanShot X** (macOS, paid) - best-in-class scroll capture + GIF recording + instant overlay of last capture. Scroll capture and GIF recording are the two biggest remaining gaps.
- **Shottr** (macOS) - smart OCR + measurement tool; already mirrored for OCR and ruler. Copy their OCR-overlay UX that shows recognized text anchored to image regions.
- **Flameshot** (cross-platform, GPL) - simple edit bar after capture; similar philosophy. Match their hotkey discoverability (on-screen key hints during capture).

## Nice-to-Haves

- Relicense evaluation: GPL-3 -> MIT if all non-MIT transitive deps can be swapped out (would simplify distribution and align with house style)
- Dedicated "tutorial screenshot" preset stack (step-numbers + arrow + highlight + blur)
- Notion/Obsidian/Markdown clipboard-copy export ("paste as markdown image link")
- Built-in quick edit via single-key toolbar hover, no click required
- Per-app capture profiles (saved hotkeys + preset per foreground app)
- Plugin SDK - minimal Python file drops a new tool into the editor toolbar
- Linux port via X11/Wayland screenshot APIs as a longer-term stretch

## Open-Source Research (Round 2)

### Related OSS Projects
- https://github.com/greenshot/greenshot — Upstream reference; plugin model Greenshot supports (that SwiftShot intentionally drops) is worth documenting to not re-add accidentally
- https://github.com/ShareX/ShareX — Feature-rich C# alt; region/window/scrolling/timed/OCR capture, 80+ upload destinations, built-in editor
- https://github.com/flameshot-org/flameshot — C++/Qt cross-platform; great inline annotation UX
- https://github.com/ksnip/ksnip — Qt Greenshot-parity without Electron; "lightweight Greenshot" ethos parallels SwiftShot
- https://github.com/MaartenBaert/ssr — SimpleScreenRecorder, pipeline for adding a screencast mode
- https://github.com/scrotwm/scrot — Simple CLI capture; reference for CLI mode
- https://github.com/topics/screenshot-tool — Topic hub

### Features to Borrow
- ShareX scrolling-capture (stitch-scroll) — SwiftShot lacks this; important for docs/long pages
- Flameshot's inline toolbar pinned to the selection rectangle — rotates as selection moves, feels more modern than floating toolbar
- Ksnip's multi-selection shapes with drag-handle resize after commit (rare in Greenshot clones)
- ShareX workflow automation — "After capture -> [OCR, annotate, save, copy path, upload]" as a user-defined pipeline
- Timed capture + region lock (ShareX) — great for capturing menus that close on focus loss
- Built-in OCR (Tesseract) producing selectable text under the pixels (ShareX)
- CLI mode with argparse flags (`swiftshot --region 0,0,800,600 --out file.png`) for scripting (scrot precedent)

### Patterns & Architectures Worth Studying
- Annotation as immediate-mode canvas layer using PyQt6 QGraphicsScene (Flameshot's scene-graph approach translates cleanly)
- Plugin SDK ethos — Greenshot's failure mode was loading enterprise plugins nobody needed; SwiftShot should keep plugins optional and drop-in-folder style (`%APPDATA%\SwiftShot\Plugins\*.py`) with `Tool(ABC)` contract
- DPI-aware capture path; on multi-monitor with mixed DPI, enumerate via Win32 `EnumDisplayMonitors` + per-monitor-v2 context
- File-naming template system (`{app}_{yyyy-MM-dd_HH-mm-ss}`) with variable registry — ShareX's template engine is a good reference
- Clipboard-history integration for "paste as markdown image link" (Obsidian/Notion workflow)

## Research-Driven Additions

New items from the 2026-07-12 research pass (see RESEARCH.md). Do not duplicate the AB/R backlog above — these are net-new and code-verified or evidence-backed. When done, DELETE the item (no `[x]` checkmarks).

### P1 — security / data safety

### P2 — capture correctness / reliability (net-new bugs)

### P2 — features (evidence-backed gaps)

- [ ] P2 — Beautify backgrounds + device/window/browser frames + padding + aspect presets
  Why: every 2026 review names gradient/solid backgrounds and device/OS-window frames as THE gap in free Windows tools (even ShareX beautify is "border yes, gradient background / frame no"); it's the highest differentiation-per-effort and needs zero new native deps (pure Pillow/NumPy). Extends the existing Frame step (border/shadow/rounded only).
  Evidence: RESEARCH.md Competitive Landscape (CleanShot X, screensnap.pro, screenhance.com); `App/utils.py:81-187` (beautify/frame funnel).
  Touches: `App/utils.py` (add background fill/gradient, padding, framed presets), `App/config.py` (settings keys), `App/settings_dialog.py` Frame tab, editor export preview.
  Acceptance: capture funnel can render a screenshot on a padded gradient/solid background and inside at least one window/browser frame; settings expose presets; tested on a sample pixmap.
  Complexity: M

- [ ] P2 — winget manifest + Scoop bucket for the unsigned Inno EXE / portable zip
  Why: winget accepts unsigned EXE/MSI installers and Scoop accepts portable zips — both peers (ShareX, Greenshot) distribute this way, no signing needed. The existing "Admin-install MSIX with winget manifest" item mis-couples winget to MSIX/signing (rejected in RESEARCH.md). This decouples discoverability from a cert.
  Evidence: https://github.com/microsoft/winget-pkgs ; https://bjansen.github.io/scoop-apps/extras/sharex/ .
  Touches: new `manifests/` YAML (winget, with SHA256 + silent-install args), a Scoop `.json` pointing at the portable exe/zip, release checklist in CLAUDE.md.
  Acceptance: `winget install SysAdminDoc.SwiftShot` and a Scoop manifest install validate locally (`winget validate`, `scoop install` from the manifest url).
  Complexity: M

### P3 — hardening / polish

- [ ] P3 — Validate the update URL scheme/host before opening it
  Why: `updater.py` takes `html_url` verbatim from the GitHub JSON and `app._open_update_page` passes it to `webbrowser.open`; a compromised/MITM'd response could hand a `file://`/`javascript:` URL to the shell. Low exploitability (HTTPS to GitHub) but cheap defense-in-depth.
  Evidence: `App/updater.py:53,60`; `App/app.py:112-114`.
  Touches: `App/updater.py` or `App/app.py` — reject unless `html_url.startswith("https://github.com/SysAdminDoc/SwiftShot/")`.
  Acceptance: a crafted non-GitHub `html_url` is ignored (logged), not opened; test covers it.
  Complexity: S

- [ ] P3 — Default save directory uses the wrong CSIDL
  Why: `get_output_directory` calls `SHGetFolderPathW(None, 0x0000, ...)` = `CSIDL_DESKTOP` (virtual namespace root) instead of `CSIDL_DESKTOPDIRECTORY` (`0x0010`, the on-disk folder); guarded by `isdir` + `~/Desktop` fallback so impact is low, but it can silently mis-resolve.
  Evidence: `App/config.py:357`.
  Touches: `App/config.py` — change constant to `0x0010`.
  Acceptance: default output dir resolves to the real Desktop folder path on a standard profile.
  Complexity: S

- [ ] P3 — Harden the OCR PowerShell invocation
  Why: `_ocr_windows` passes the image path as a `powershell -File <script> -ImagePath <path>` positional; low real risk (subprocess uses an argv list, no shell) but a user-chosen/history path beginning with `-` is ambiguous. Pass the path via env var or stdin.
  Evidence: `App/ocr.py:145-153`.
  Touches: `App/ocr.py` (and `_WIN_OCR_SCRIPT` to read `$env:SWIFTSHOT_OCR_PATH`).
  Acceptance: OCR still works; a path starting with `-` OCRs correctly; no `-File` positional path.
  Complexity: S

- [ ] P3 — Image Comparer / diff panel
  Why: ShareX 21 shipped an image-diff tool; useful for QA/design regressions and cheap as a NumPy pixel-diff over two loaded images.
  Evidence: RESEARCH.md (ShareX 21.0.0, 2026-07-03).
  Touches: `App/editor.py` (small compare panel / dialog), menu entry.
  Acceptance: load two images, see a highlighted diff (and % changed); works headless in a unit test on two arrays.
  Complexity: M
