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

- [ ] AB-17 P2 — Full PIL recomposite on every hover repaint
  Why: `mouseMoveEvent` calls `update()` unconditionally (~1388) and every `paintEvent` calls `get_composite()` — a full Python flatten of all layers/masks/fx per mouse event.
  Fix: cache the composite, invalidate on actual edits; also rebuild quick-mask/rubylith pixmaps only when their source changes (~2179, ~2357).

### Carried research items (from RESEARCH.md, still open)

- [ ] R-01 P2 — Windows Graphics Capture backend with GDI fallback
  GDI BitBlt returns black for hardware-accelerated/protected/some UWP windows; WGC captures them and unlocks recording. `CAPTUREBLT` quick-win is DONE — this is the full backend. Touches `App/capture.py` (probe + fallback), optional dep `windows-capture` or `winrt-Windows.Graphics.Capture`. Complexity: L.
- [ ] R-02 P2 — Split editor.py into modules
  8,200+ lines in one file. Start with zero-Qt-coupling units: `core.py` (scaling/PIL↔Qt/numpy/theme) and `layers.py` (`Layer`/`HistoryManager`/`LayerGroup`). Full suite must pass unchanged. Complexity: L (first two modules: M).

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

### P1 — security / data safety

- [ ] P1 — Auto-redact silently fails to redact on a group / mis-redacts on size-mismatched layers
  Why: `auto_redact` OCRs `self.get_composite()` (canvas-sized, origin = layers[0]) but draws the black boxes on `self.active_layer().image`; a `LayerGroup` active layer has a no-op image setter so `ImageDraw.Draw` mutates a throwaway composite — nothing is redacted, yet history is pushed and the doc marked dirty, so the user believes the PII is hidden. A differently-sized active layer (pasted/diff-overlay) gets boxes at the wrong coordinates.
  Evidence: `App/editor.py` `auto_redact` (draws on active layer) vs `LayerGroup.image` setter no-op (~848); RESEARCH.md "net-new bugs".
  Touches: `App/editor.py` — bake redaction onto a fresh full-canvas layer or into the composite, and/or refuse when `active_layer()` is a group or its size != composite size.
  Acceptance: redacting with a group (or a pasted smaller/larger layer) as the active layer actually blacks out the PII pixels; regression test on a group-active document.
  Complexity: M

### P2 — capture correctness / reliability (net-new bugs)

- [ ] P2 — Auto-redact over-matches numeric data and never asks for confirmation
  Why: the phone pattern `\+?\d[\d().-]{6,}\d` matches any 8+ run of digits/`().-` — dates (2026-07-12), order/ID numbers, ISBNs, prices — and `auto_redact` blacks them out with no preview, silently defacing legitimate data on e.g. a spreadsheet screenshot.
  Evidence: `App/ocr.py:_PII_PATTERNS` (phone entry); `App/editor.py:auto_redact` (no confirm step).
  Touches: `App/ocr.py` (tighten the phone pattern to plausible phone groupings), `App/editor.py` (show the matched boxes and confirm before drawing).
  Acceptance: a screenshot of a dates/prices table is not redacted; the user sees and confirms the matched regions first; unit test on `find_pii_words` false-positive cases.
  Complexity: M

- [ ] P2 — `get_composite` crashes on a size-mismatched layer with a non-Normal blend mode
  Why: `_blend` non-Normal modes call `ImageChops.multiply(base.convert("RGB"), top.convert("RGB"))`; a pasted layer keeps its clipboard dimensions, so a larger/smaller pasted layer with any non-Normal blend raises `images do not match`. `get_composite` runs on every repaint/hover/save/export → repeated crash dialogs (Normal mode is safe — paste clips).
  Evidence: `App/editor.py:_blend` (~6547); `paste_clipboard` keeps clipboard size (~6915).
  Touches: `App/editor.py` — crop/pad `top` to `base.size` at the top of `_blend` (or normalize pasted layers to canvas size on paste).
  Acceptance: pasting a larger image, setting Multiply, and repainting does not raise; regression test on `_blend` with mismatched sizes.
  Complexity: S

- [ ] P2 — CLI `--monitor` out-of-range silently writes a full-desktop image (exit 0)
  Why: `cli._capture` → `capture.capture_monitor` falls through the `0 <= idx < len(screens)` guard to `capture_fullscreen()`; a script asking for monitor 99 gets a wrong full-desktop image with a success exit code.
  Evidence: `App/capture.py:capture_monitor` (~327); `App/cli.py:_capture` (~63).
  Touches: `App/cli.py` — validate the monitor index against `QApplication.screens()` and return a non-zero error for out-of-range values.
  Acceptance: `swiftshot --monitor 99 --out x.png` errors with a non-zero exit and no file written; test covers it.
  Complexity: S

### P2 — observability

- [ ] P2 — "Export Diagnostics" bundle command
  Why: only a rotating logger + `crash.log` exist; there is no one-command bundle to attach to a bug report. Cheapest observability win for a local tool.
  Evidence: RESEARCH.md observability; peers ship diagnostics export.
  Touches: `App/app.py` (tray menu action) + `App/cli.py` (a `--diagnostics` verb); zip `crash.log` + rotated logs + `swiftshot.json`/editor `config.json` (secrets stripped) + OS/Qt/Pillow/SQLite versions + a WGC-availability probe.
  Acceptance: the action writes a zip whose contents include the logs and a versions manifest; secrets are absent; verified on a sample run.
  Complexity: S

### P2 — features (evidence-backed gaps)

- [ ] P2 — Device/window/browser frames for the backdrop (extends the shipped solid/gradient backdrop)
  Why: the padded solid/gradient backdrop shipped; the remaining gap vs CleanShot X is a "framed inside a macOS/Windows window or browser chrome" preset. Pure Pillow (compose the capture inside a frame PNG or drawn chrome).
  Evidence: RESEARCH.md Competitive Landscape (CleanShot X); `App/utils.py` `apply_backdrop`.
  Touches: `App/utils.py` (frame assets/drawing), `App/config.py`, `App/settings_dialog.py` Frame tab.
  Acceptance: at least one window/browser frame preset renders around a capture; tested on a sample pixmap.
  Complexity: M

### P3 — polish / correctness

- [ ] P3 — `words_to_table` row clustering drifts on slanted/variable-baseline text
  Why: rows are grouped against the first word's `y` (never updated within a row, `row_y = ws[0]["y"]`), so a row whose baseline gradually rises/falls splits mid-row and scrambles the emitted TSV columns.
  Evidence: `App/ocr.py:words_to_table` (~215-231).
  Touches: `App/ocr.py` — cluster by a running row mean/median `y` (update as words are added).
  Acceptance: a synthetic slanted-baseline row stays one row; unit test on `words_to_table`.
  Complexity: S

- [ ] P3 — `compute_image_diff` hard-overwrites changed pixels though the docstring says "tinted"
  Why: `overlay[changed] = (255,0,0,255)` replaces changed regions with solid opaque red, discarding the underlying content; the docstring claims a tint, and near-identical images become large solid-red blocks.
  Evidence: `App/editor.py:compute_image_diff` (~121-135).
  Touches: `App/editor.py` — alpha-blend red over the base for changed pixels (or fix the docstring to match).
  Acceptance: changed regions show a red tint over the original content; existing diff test updated.
  Complexity: S

- [ ] P3 — Structured crash context in the editor excepthook
  Why: the editor's single excepthook logs the traceback but not the active tool / layer count / last history action, so crash reports lack the context to reproduce.
  Evidence: `App/editor.py` editor excepthook (see CLAUDE.md note); RESEARCH.md observability.
  Touches: `App/editor.py` — attach active tool, layer count, and last history label to the logged record.
  Acceptance: a forced editor exception logs the extra context alongside the traceback.
  Complexity: S

- [ ] P3 — Async history-OCR can update an already-evicted row (lost OCR text under burst)
  Why: `save_to_history` enforces `CAPTURE_HISTORY_MAX` immediately, so a rapid capture burst can delete the row/file before the background `_OcrWorker` finishes; `update_history_ocr` then no-ops and the computed OCR text is lost.
  Evidence: `App/app.py:_start_history_ocr`; `App/capture_history.py:save_to_history` eviction + `update_history_ocr`.
  Touches: `App/capture_history.py` — key the update by sha256 (survives rename) or skip if the row is gone; optionally defer eviction until OCR settles.
  Acceptance: a capture that survives the burst ends up with its OCR text; no crash when the row was evicted.
  Complexity: S



## Research-Driven Additions — support-module depth pass (2026-07-12)

Net-new, code-verified findings from auditing the less-examined support modules (build script, hotkeys, config, updater, pickers). Not duplicated above. Delete when done (no `[x]`).

### P2 — reliability (support modules)

- [ ] P2 — Hotkey recorder saves combos that silently never fire
  Why: for a key absent from `_VK_NAMES` and not A-Z/0-9, the recorder falls back to `QKeySequence(key).toString()`, producing names (`F13`, `+`, `[`, media keys) that `HotkeyManager._parse_combo` can't resolve against `VK_MAP`; `register()` then binds nothing while Settings shows the combo as saved.
  Evidence: `App/settings_dialog.py:170-174` (fallback) vs `App/hotkeys.py` `VK_MAP` / `_parse_combo` (~115-143).
  Touches: `App/settings_dialog.py` — only accept a recorded key whose resulting name is a `VK_MAP` key (or A-Z/0-9); otherwise reject the recording and keep the field unchanged.
  Acceptance: recording an unmappable key (e.g. F13) does not overwrite the field; every combo the recorder accepts actually fires; test asserts recorder output ⊆ VK_MAP-resolvable names.
  Complexity: S

- [ ] P2 — `PostThreadMessageW` undeclared argtypes → hook leak risk on live re-bind
  Why: `stop()` calls the shared `windll.user32.PostThreadMessageW(self._thread.ident, 0x0012, 0, 0)` with no `argtypes`, so the thread id is marshaled as signed 32-bit; a large thread id could target the wrong thread, the WM_QUIT never lands, and the old LL keyboard hook stays installed alongside the new one after a settings re-bind.
  Evidence: `App/hotkeys.py:295` (`stop()`).
  Touches: `App/hotkeys.py` — declare `PostThreadMessageW.argtypes = [DWORD, UINT, WPARAM, LPARAM]` and pass `wintypes.DWORD(self._thread.ident)`.
  Acceptance: repeated live hotkey re-binds leave exactly one keyboard hook installed; unit/manual check that `stop()` joins the hook thread each time.
  Complexity: S

### P3 — reliability / correctness (support modules)

- [ ] P3 — Config downgrade silently drops newer keys (upgrade round-trip data loss)
  Why: `save()` rewrites `swiftshot.json` using only `_get_saveable_keys()` (the running build's key set), so an older build erases newer keys (`BACKDROP_*`, `CAPTURE_COLOR_PICKER_HOTKEY`, …); on re-upgrade those settings revert to defaults.
  Evidence: `App/config.py:270` (`save()`), `:251` (unknown-key skip on load).
  Touches: `App/config.py` — capture unknown keys read from the file into a passthrough dict and re-emit them in `save()`.
  Acceptance: loading a config with an unknown key and saving preserves that key in the file; downgrade→upgrade round-trip keeps new-build settings.
  Complexity: S

- [ ] P3 — `UpdateChecker` QThread never joined on shutdown
  Why: the update-check QThread runs an up-to-10 s `urlopen`; quitting during it can emit "QThread: Destroyed while thread is still running" and deliver a queued signal to a torn-down object.
  Evidence: `App/app.py:118-120` (started, never `wait()`ed); `App/updater.py:33-76`.
  Touches: `App/app.py` `exit_app` — `self._update_checker.wait(...)` (or a cancel flag + short socket timeout) before teardown.
  Acceptance: quitting immediately after launch logs no QThread-destroyed warning; no crash.
  Complexity: S

- [ ] P3 — `monitor_picker` has no zero-display empty state
  Why: with `QApplication.screens()` empty (headless/RDP-no-console), the picker shows an "All Monitors (0)" button that emits `-1` (capture-all → empty capture) and a dead "press 1-9" subtitle.
  Evidence: `App/monitor_picker.py:195-216`.
  Touches: `App/monitor_picker.py` — if no screens, show "No displays detected" and disable/hide the capture buttons (or auto-reject).
  Acceptance: a no-display session shows the empty-state message and offers no invalid capture action.
  Complexity: S

- [ ] P3 — History panel re-hashes content-duplicate files on every open
  Why: `_index_file` uses `INSERT OR IGNORE` on the UNIQUE `sha256`, so a second file with identical content is never path-indexed and `_ensure_history_index` re-reads + re-hashes it on every panel open/search (repeated full-file SHA-256 on large dirs).
  Evidence: `App/capture_history.py:100-124` (`_index_file`), `~138` (`_ensure_history_index` "not in indexed").
  Touches: `App/capture_history.py` — record attempted-but-ignored paths (side table or path-keyed index) and dedupe visible entries at query time.
  Acceptance: opening the history panel twice does not re-hash already-seen content-duplicate files; verified via a hash-call counter in a test.
  Complexity: M
