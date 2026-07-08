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

### P1 — data loss / broken behavior

- [ ] AB-01 P1 — Finish the Move-tool off-canvas preservation (HALF-DONE)
  Why: the drag handler re-pastes `layer.image` into a same-size blank canvas each step, so content dragged past the canvas edge is destroyed; `layer.mask` is not shifted with the image (masked layers desync).
  Where: `App/editor.py` CanvasWidget move-tool drag branch (~1460).
  State: the press handler (~1190) already saves undo state ("Move"), refuses locked layers, and snapshots `_move_orig_img` / `_move_orig_mask` / `_move_start` — but nothing consumes them yet.
  Fix: in the drag branch compute the cumulative offset from `_move_start` and re-paste from `_move_orig_img` (and shift `_move_orig_mask` identically) each step; clear the snapshots on mouse release / tool switch.

- [ ] AB-02 P1 — Duplicate shortcuts kill Select All / Deselect / Invert Selection
  Why: `Ctrl+A`, `Ctrl+D`, `Ctrl+Shift+I` are each bound to two QActions (Edit menu ~5785 and Select menu ~5908); Qt treats them as ambiguous and triggers NEITHER — all three shortcuts are dead.
  Fix: keep the shortcut on one action only, or add the same QAction object to both menus.

- [ ] AB-03 P1 — Whole-image geometry ops never transform layer masks → repaint crash
  Why: `_do_crop`, `resize_image`, `resize_canvas`, `rotate_image`, `flip_image` (and `flip_layer`/`rotate_layer`) leave `layer.mask` at the old size; `get_composite` then raises `ValueError: images do not match` on every repaint — the editor becomes unusable after cropping a masked document.
  Fix: apply the identical geometry op to `l.mask` when present (merge_down ~6712 shows the defensive pattern). For LayerGroup, recurse into children and update `_w`/`_h`.

- [ ] AB-04 P1 — LayerGroup `image` setter no-ops corrupt/destroy data
  Why: every `layer.image = ...` writer silently does nothing on a group: adjustments/filters via `_apply_to_active` push an undo state and mark dirty while changing nothing; **Merge Down onto a group computes the blend, assigns it into the void, then deletes the top layer — pixel destruction**; geometry ops leave group children untouched.
  Where: `App/editor.py` `_apply_to_active` (~6340), `merge_down` (~6702), geometry-op loops.
  Fix: in `_apply_to_active`/`merge_down`, refuse groups with a status message BEFORE save_state; geometry ops recurse into children. (The paint-tool press guard for groups is already in `mousePressEvent` ~1193.)

### P2 — editor correctness

- [ ] AB-05 P2 — `LayerGroup.image` squares child alpha
  Why: children composite via `result.paste(img, (0, 0), img)` onto a transparent base — PIL interpolates alpha too, so a 50%-opacity child renders at 25% inside a group (RGB also pre-darkened at soft edges).
  Fix: `result = Image.alpha_composite(result, img)` (~line 811). Add a pure-PIL regression test (50%-alpha child → composite alpha ≈128, not ≈64).

- [ ] AB-06 P2 — Translucent pencil/spray strokes punch holes
  Why: `_draw_brush_line` excludes pencil/spray from the `_stamp_over` compositing path (`use_soft = ... and (t not in ("spray", "pencil"))` ~1774); with `brush_opacity < 255` their ImageDraw fills REPLACE destination alpha. The press dab composites correctly, so strokes are visibly inconsistent.
  Fix: when translucent, composite pencil/spray segments via `_stamp_over` (keep the hard edge, no soft falloff).

- [ ] AB-07 P2 — Rotated-view interactions ignore `canvas_angle`
  Why: `view_transform()` is `s = R(pan + zoom·p)` but (a) pan drag adds the raw screen delta (~1404), (b) wheel zoom-to-cursor anchors on the un-rotated cursor point (~1692), (c) `_xform_drag` scale un-rotates only by the object angle (~2681). With a rotated view, panning moves the canvas the wrong way and zoom drifts.
  Fix: helper that un-rotates a screen-space delta/point by `canvas_angle`; use in all three sites.

- [ ] AB-08 P2 — `paste_clipboard` into an empty document: no history, no dirty mark
  Why: the branch that creates the Background layer (~6577) skips `save_state` and `_mark_dirty` — paste a screenshot into a fresh editor, close, and it is silently lost.

- [ ] AB-09 P2 — Ctrl+C with a selection never reaches the OS clipboard
  Why: `_smart_copy` → `copy_selection` (~6547) fills only the internal `self._clipboard`; the no-selection path DOES hit the OS clipboard — inconsistent and confusing.
  Fix: also place the selection bitmap on `QApplication.clipboard()` via `pil_to_qpixmap`.

- [ ] AB-10 P2 — Export clears the dirty flag
  Why: `export_png`/`export_webp` (~6493/6506) call `_set_dirty(False)`; exporting a flattened copy is not saving the layered document — closing then skips the unsaved-changes prompt and layers/masks/effects are lost.

- [ ] AB-11 P2 — `_jpeg_quality` leaks across documents
  Why: only reset in `__init__` and `save_image_as`; open A.jpg → save at quality 30 → open B.jpg → Ctrl+S silently saves B at 30 with no prompt.
  Fix: reset to None in every document-replacing path (same set as AB-12).

- [ ] AB-12 P2 — Document-replacing paths never confirm discarding unsaved work
  Why: `new_image`, `open_image`, `open_recent_file`, `load_pixmap`/`open_from_clipboard`, `_load_project_from` all drop the current document without checking `_dirty` — the only gate is `closeEvent`.
  Fix: shared `_confirm_discard()` (Save/Discard/Cancel like closeEvent) + a `_reset_document_state()` that clears `saved_paths`, guides, quick-mask state and `_jpeg_quality` (AB-11, AB-27).

- [ ] AB-13 P2 — Adjustments crash in mask-edit mode
  Why: `_apply_to_active` passes `l.mask.convert("RGB")` to funcs that do `r, g, b, a = img.split()` (hue/levels/curves/gamma/threshold raise "not enough values to unpack"; vibrance/sepia misbehave).
  Fix: convert the mask to RGBA before the func and back to L after, in the mask-edit branch (~6326).

- [ ] AB-14 P2 — Layer lock not enforced across edit paths
  Why: Delete/Cut selection (~6539), `_apply_to_active` (~6321), `insert_text_at` (~6894), `insert_note_at` (~7988), `AlignPanel._align` (~4403), and `ai_*` ops all modify locked layers; `flip_layer`/`rotate_layer`/`stroke_path`/`fill_path` correctly refuse.
  Fix: copy the existing `if layer.locked: status; return` pattern into the missing sites, BEFORE save_state.

- [ ] AB-15 P2 — Standalone editor: "Pin to Desktop" window garbage-collected instantly
  Why: when `swiftshot_app is None` the PinWindow only lives in a local (~8030) — it flashes and vanishes.
  Fix: keep a `self._standalone_pins` list; remove on the pin's `closed` signal.

- [ ] AB-16 P2 — History memory bloat: full-document deep copies
  Why: every `save_state` deep-copies every layer image, mask and group child; undo+redo stacks hold 30 snapshots each — a 5-layer 4K document can pin gigabytes after a painting session.
  Fix: per-layer or dirty-rect snapshots, or at minimum a byte-budget cap instead of a count cap. (`HistoryManager` ~629.)

- [ ] AB-17 P2 — Full PIL recomposite on every hover repaint
  Why: `mouseMoveEvent` calls `update()` unconditionally (~1388) and every `paintEvent` calls `get_composite()` — a full Python flatten of all layers/masks/fx per mouse event.
  Fix: cache the composite, invalidate on actual edits; also rebuild quick-mask/rubylith pixmaps only when their source changes (~2179, ~2357).

### P2 — app / capture

- [ ] AB-18 P2 — Auto-OCR freezes the GUI for up to 30 s per capture
  Why: with `CAPTURE_HISTORY_AUTO_OCR` on, `_on_capture` → `_history_ocr_text` runs the PowerShell WinRT OCR subprocess synchronously on the Qt thread (`App/app.py` ~700, ~732; `ocr.py` timeout=30). PowerShell cold start is routinely 2-5 s — every capture visibly hangs. Interactive `_do_ocr` (~648) has the same problem.
  Fix: run OCR in a worker (QThread/QRunnable); for history, UPDATE the row's `ocr_text` when it completes — `capture_history.py` ~481 already has the UPDATE path.

- [ ] AB-19 P2 — Settings "clipboard watcher" checkbox is never applied live and desyncs the tray toggle
  Why: `_apply_and_close` writes `config.CLIPBOARD_WATCHER_ENABLED`, but `show_settings` (app.py ~963) never starts/stops the watcher or syncs `self._clipboard_watcher_enabled` (captured once at init, ~38). The next tray toggle flips the STALE flag and overwrites config with the inverted value.
  Fix: after dialog accept, sync the flag and start/stop `_start_clipboard_watcher`/`_stop_clipboard_watcher` accordingly.

- [ ] AB-20 P2 — Second capture kills an in-flight countdown silently
  Why: `_capture_with_delay` (~279) and `_timed_capture_region` (~532) store the only reference to the parentless CountdownOverlay in `self._countdown`; a second trigger drops the first → widget deleted → its capture never fires, no log.
  Fix: cancel the prior countdown explicitly (log it) or keep a list.

- [ ] AB-21 P2 — History rows for externally deleted files starve the panel
  Why: `_history_entries` (capture_history.py ~141) applies the missing-file filter AFTER `LIMIT`, so dead rows permanently occupy LIMIT slots (panel can show far fewer than MAX, down to zero).
  Fix: purge rows whose file no longer exists during `_ensure_history_index` (it already scans the directory), not post-query.

### P3 — editor polish & correctness

- [ ] AB-22 P3 — Undo renames nested-group grandchildren to "X copy" (`HistoryManager._copy_layer` restores names only one level deep, ~663).
- [ ] AB-23 P3 — Warp tool: `_warp_orig` not cleared on undo → the next warp stroke records no history; `_warp_reset` (~4984) restores pixels without a history entry.
- [ ] AB-24 P3 — Drag-reorder keeps the numeric `active_layer_index` (clamped only, ~3689) → next stroke lands on the wrong layer. Remap by object identity.
- [ ] AB-25 P3 — Layer panel `refresh()` highlights the wrong row when groups are expanded (index math ignores child rows, ~3583).
- [ ] AB-26 P3 — `_expand_canvas_for_stroke` (~2905) shifts layers/masks/selection/pan but forgets `_guides` positions and `clone_source`.
- [ ] AB-27 P3 — Pan drag never emits `zoom_changed` (~1404) → rulers/navigator stay stale until the next wheel zoom. (Also: `_nav_update_cb` at ~894/~1168 is dead code.)
- [ ] AB-28 P3 — Gradient onto transparent pixels double-attenuates color (`_draw_gradient` ~2067 blends straight RGB but writes new alpha; needs un-premultiplied source-over: `rgb_out = (src·αs + dst·αd·(1-αs)) / α_out`).
- [ ] AB-29 P3 — Flood fill (~1814) and content-aware fill (~2842) are per-pixel Python loops — multi-second UI freezes on large areas; vectorize with numpy (no scipy — it is purged from this repo).
- [ ] AB-30 P3 — Tool tooltips advertise single-key shortcuts (V/M/B/E/S/R/T/P/N/G/I/H/X, ~5417-5519) that are never registered. Register QShortcuts (preferred) or drop them from tooltips.
- [ ] AB-31 P3 — `save_image_as` sets `file_path` but never clears `saved_path` (~6443): after Save-As-PNG from a loaded project, Ctrl+S silently overwrites the `.swiftshot` file.
- [ ] AB-32 P3 — Space-pan release restores `ArrowCursor` unconditionally (~7789), clobbering tool cursors until the next tool switch. Restore from the tool→cursor map.
- [ ] AB-33 P3 — `X` color swap (~7784) and eyedropper picks don't repaint the toolbar swatch/Color panel. Centralize change notification in `set_fg_color`/`set_bg_color`.
- [ ] AB-34 P3 — `closeEvent` (~8064) stops `march_timer` but not `_poll_timer` (2 s repeating) or `_panel_refresh_timer`; in standalone mode the poll fires on a closed window forever.
- [ ] AB-35 P3 — `svg_icon` default `color=C.TEXT_SEC` (~550) binds the dark-theme hex at import time, before `apply_editor_theme` rebinds `C`. Latent (all call sites pass a color) — make the default lazy.

### P3 — support modules

- [ ] AB-36 P3 — Save-directory free text in Settings is unvalidated; nonexistent paths silently fall back to Desktop (`settings_dialog.py` ~798 + `config.get_output_directory`). Validate on apply; warn or offer to create.
- [ ] AB-37 P3 — `sha256 TEXT UNIQUE` + `INSERT OR IGNORE` in the history DB makes duplicate-content files invisible in the panel while "Delete all N" counts them (`capture_history.py` ~55, ~96). Decide: index duplicates, or dedupe only at capture time.
- [ ] AB-38 P3 — Updater is notify-only today (opens the GitHub release page — no download to verify). IF in-app download ever ships, it MUST verify a published SHA-256 / signed manifest before anything executable lands on disk. (Rescoped from the earlier "verify update-download integrity" item, whose premise was wrong.)

### Carried research items (from RESEARCH.md, still open)

- [ ] R-01 P2 — Windows Graphics Capture backend with GDI fallback
  GDI BitBlt returns black for hardware-accelerated/protected/some UWP windows; WGC captures them and unlocks recording. `CAPTUREBLT` quick-win is DONE — this is the full backend. Touches `App/capture.py` (probe + fallback), optional dep `windows-capture` or `winrt-Windows.Graphics.Capture`. Complexity: L.
- [ ] R-02 P2 — Split editor.py into modules
  8,200+ lines in one file. Start with zero-Qt-coupling units: `core.py` (scaling/PIL↔Qt/numpy/theme) and `layers.py` (`Layer`/`HistoryManager`/`LayerGroup`). Full suite must pass unchanged. Complexity: L (first two modules: M).
- [ ] R-03 P2 — Editor accessibility pass
  Zero accessible metadata, no `setTabOrder`, no shortcut registry in the editor (capture surfaces already have names + a test). Primary controls need accessible names/descriptions, tab order, and coverage in `tests/test_accessibility.py`. Complexity: M.
- [ ] R-04 P2 — Tests for untested capture modules and editor image-math
  `overlay.py`, `scrolling_capture.py` (stitching is pure-testable), `window_picker.py`, `pin_window.py`, editor filters/adjustments/compositor have no coverage. Complexity: M.
- [ ] R-05 P2 — Scrolling-capture stitching: auto-ignore static bottom edge
  Fixed footers/sticky scrollbars mis-stitch; diff consecutive frames to drop static bottom chrome (ShareX 17 approach). Touches `_find_overlap`. Add a synthetic frame-set test. Complexity: M.
- [ ] R-06 P2 — Extract a shared QImage-from-bytes helper
  `pil_to_qpixmap` copies + passes `bytesPerLine`; `CanvasWidget.paintEvent` does neither and relies on a local staying alive until `drawImage`. One helper, both sites, always sets stride and detaches. Complexity: S.
- [ ] R-07 P2 — Sign release binaries (operator-gated: needs cert / Azure Trusted Signing)
  Unsigned EXE + installer trigger SmartScreen friction. Touches Build-SwiftShot.ps1 (signtool), SwiftShot.iss.
- [ ] R-08 P3 — AVIF export alongside WebP
  Pillow 11.3+ wheels bundle AVIF — probe `Image.SAVE` support at runtime and add "avif" to `OUTPUT_FILE_FORMAT_CHOICES`/save paths only when available. Touches `utils.save_pixmap`, config, settings, editor export menu. Complexity: S.
- [ ] R-09 P3 — OCR "copy as table" for structured captures
  Detect column/row structure from WinRT OCR word boxes; emit TSV/HTML to clipboard; fall back to flat text. Complexity: M.
- [ ] R-10 P3 — Scriptable CLI
  `swiftshot --region x,y,w,h --out file.png`, `--fullscreen`, `--ocr` headless. NOTE: `main.py` now handles a bare image-path argument (file association) and ignores `--minimized` — build argparse around that. Complexity: M.

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
