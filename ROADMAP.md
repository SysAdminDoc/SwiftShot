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

### Carried research items (from RESEARCH.md, still open)

- [ ] R-02b P3 — Continue the editor.py split (optional follow-on)
  `layers.py` (`Layer`/`HistoryManager`/`LayerGroup`) is extracted. A further
  `core.py` (scaling/DPI, PIL↔Qt helpers `pil_to_qimage`/`qpixmap_to_pil`,
  numpy `np_*` helpers, theme `class C`/`apply_editor_theme`) could follow, but
  those helpers are Qt/theme-coupled and used pervasively, so the risk/reward is
  lower than the layer-model extraction. Only if editor.py churn warrants it.

## Planned Features

### Capture
- Multi-monitor DPI-aware scroll capture (currently single-monitor friendly)
- Scrolling capture for web apps using DevTools protocol where available (Chromium-only enhancement)
- Camera overlay and green-screen keying for "me + screen" tutorial captures
- GIF / MP4 short-recording with edit-after-capture frame picker

### Editor
- Magic wand / heal tool (LaMa ONNX) for object removal
- Speech bubble tool
- Badge / number-sequence tool with custom shape presets
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





## Research-Driven Additions — support-module depth pass (2026-07-12)

Net-new, code-verified findings from auditing the less-examined support modules (build script, hotkeys, config, updater, pickers). Not duplicated above. Delete when done (no `[x]`).

## Research-Driven Additions

### P1

- [ ] R-27 P1 — Build a deterministic local release and package gate
  Why: Broad lower bounds, a floating PyInstaller, unvalidated frozen outputs, stale winget schema/placeholders, and no artifact smoke make releases non-reproducible.
  Evidence: requirements files, `App/Build-SwiftShot.ps1`, `App/SwiftShot.spec`, `packaging/winget`, `packaging/scoop`; pip secure-install guidance; ShareX checksummed assets. Cross-reference blocked R-07 signing and AB-38 update integrity rather than duplicating them.
  Touches: dependency constraints/hashes, build script/spec, package manifests, release checks/tests.
  Acceptance: A clean local command installs exact hash-locked Windows wheels, runs pytest/Ruff, builds supported portable/installer forms, launches/import-smokes each artifact, verifies CLI/editor/history/OCR capability probes, emits checksums plus dependency SBOM, upgrades winget to schema 1.12.0, fills release URLs/hashes, and validation-installs winget/Scoop manifests; identical inputs record tool/runtime versions and produce explainable diffs.
  Complexity: L

### P2

- [ ] R-29 P2 — Preserve the captured cursor as an editable layer
  Why: Cursor pixels are baked into the screenshot, preventing QA/tutorial users from hiding, moving, or correcting them.
  Evidence: `App/capture.py` cursor composition; Snagit editable cursor; ksnip movable cursor annotation.
  Touches: `App/capture.py`, capture result model, `App/editor.py`, project serialization/tests.
  Acceptance: Capture returns cursor bitmap, hotspot, position, and visibility separately; the editor creates a named movable/hideable layer without offset drift at mixed DPI; flattening matches legacy output by default; projects round-trip the cursor metadata and old projects still load.
  Complexity: M

- [ ] R-30 P2 — Expose OCR language discovery and remediation
  Why: WinRT OCR depends on installed Windows OCR languages and Tesseract availability, but users cannot see or select the effective recognizer language.
  Evidence: `App/ocr.py`; Windows `OcrEngine.AvailableRecognizerLanguages` platform contract.
  Touches: `App/ocr.py`, OCR settings/status, diagnostics, OCR tests.
  Acceptance: Settings list detected WinRT and Tesseract languages/backends, allow an explicit or automatic choice, explain how to install a missing Windows/Tesseract pack, persist stable language identifiers, and fall back visibly; no language model downloads occur without user action.
  Complexity: M

- [ ] R-31 P2 — Add local history favorites and tags with a reversible migration
  Why: OCR search and time ordering cannot preserve important captures or organize recurring documentation without renaming/moving files.
  Evidence: `App/capture_history.py` schema/search; Snagit library tags; CleanShot history workflow.
  Touches: capture-history schema/UI/search, migration/rollback helpers, diagnostics/tests.
  Acceptance: A versioned transaction adds favorites and user tags, filters/searches them, protects favorites from count-based retention unless explicitly confirmed, backs up before migration, and can rebuild without losing image files; optional source-app/window metadata is off by default and redacted from diagnostics.
  Complexity: M

- [ ] R-32 P2 — Finish live and system-following theme switching
  Why: Existing editor windows embed palette values and generated icons at construction, so changing Preferences updates tray/new windows but cannot safely repaint an open unsaved editor; there is also no system-theme mode or live OS theme/high-contrast change listener.
  Where: `App/editor.py`, `App/theme.py`, `App/app.py`, `App/settings_dialog.py`
