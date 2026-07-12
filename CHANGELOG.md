# Changelog

All notable changes to SwiftShot will be documented in this file.

## [Unreleased]

First batch of the 2026-07-07 deep-audit fixes (the remaining verified
findings live in ROADMAP.md as the prioritized "Audit Backlog").

### Added
- Tools ▸ Auto-Redact Personal Data: OCRs the image and blacks out emails,
  IP/MAC addresses, and phone numbers automatically.
- Global color picker: bind a hotkey (Settings ▸ Hotkeys ▸ Color Picker) to
  copy the pixel under the cursor as a hex code to the clipboard.
- Tools ▸ OCR – Copy as Table: clusters WinRT OCR word boxes into rows/columns
  and copies the result as TSV (paste straight into a spreadsheet), matching
  the Windows 11 Snipping Tool's table extraction.
- Packaging manifests for winget (`packaging/winget/`, validated with
  `winget validate`) and Scoop (`packaging/scoop/swiftshot.json`), both
  unsigned-friendly (Inno installer / portable exe). Release fills the SHA-256.
- Backdrop beautification: place captures on a padded solid or vertical-gradient
  background (Settings ▸ Frame ▸ Backdrop), the most-requested gap versus paid
  tools. Applies after the border/shadow/rounded frame in the capture funnel.
- Tools ▸ Compare With Image: overlays a pixel diff against another image as a
  new red-tinted layer and reports the percentage of pixels changed.
- Scriptable headless CLI: `swiftshot --region X,Y,W,H --out shot.png`,
  `--fullscreen`, `--monitor N`, and `--ocr` (prints recognized text to
  stdout). Runs and exits without the tray; a bare image path and
  `--minimized` still launch the GUI as before.

### Formats
- AVIF export is offered wherever WebP is (capture auto-save, Settings output
  format, editor Save-As and a new Export AVIF menu entry) — enabled only when
  the installed Pillow was built with libavif (the 12.3.0+ wheels are).

### Security & dependencies
- The update checker only surfaces a genuine GitHub release URL for this
  repository; any other `html_url` in the API response is ignored and
  replaced with the releases page, so a tampered response can't hand a
  `file://`/`javascript:` URL to the browser.
- OCR passes the image path to the WinRT PowerShell helper via an environment
  variable instead of a `-File` positional, so a path beginning with `-`
  can't be reinterpreted as a switch.
- The default save directory resolves via `CSIDL_DESKTOPDIRECTORY` (the
  on-disk Desktop folder) instead of the virtual `CSIDL_DESKTOP` root.
- Pillow floor raised to `>=12.3.0`, clearing six 2026 CVEs including
  CVE-2026-55798 (OS command injection), CVE-2026-55380 / CVE-2026-54060
  (excessive memory allocation) and CVE-2026-42309 (heap overflow). 12.3.0
  also bundles the native AVIF plugin.
- The build script now reports the bundled SQLite version and warns when it
  is below 3.50.2 (CVE-2025-6965), so a security release can't ship an
  unpatched history-DB engine unnoticed.

### Capture & history reliability
- Scrolling capture detects a fixed footer / sticky scrollbar (a bottom band
  identical across frames) and trims it from all but the last frame, so it is
  no longer stitched into the tall image once per scroll step.
- OCR now runs off the GUI thread. Auto-OCR indexing saves the history row
  immediately with no text and fills it in asynchronously, and interactive
  region OCR shows its result when the worker finishes — the 2-5 s WinRT
  PowerShell cold start no longer freezes the tray or editor on every capture.
- Starting a second capture while a countdown is running now cancels the
  first countdown explicitly (and logs it) instead of dropping its only
  reference, which garbage-collected the overlay so its capture never fired.
- The clipboard-watcher setting applies immediately when Settings is
  accepted, and the tray toggle stays in sync (it previously flipped a stale
  flag and wrote the inverted value back to config).
- Capture-history rows whose image file was deleted outside the app are
  purged during indexing, so dead rows can no longer occupy the panel's
  fixed slot budget and starve it down to zero visible captures.
- Save-As no longer leaves the `.swiftshot` project path set, so a
  subsequent Ctrl+S overwrites the file you just saved to, not the project.
- Standalone editor (no tray app): "Pin to Desktop" windows are retained
  instead of being garbage-collected the instant they open.
- Freehand (transparent-outside) captures no longer get a rectangular
  background/border/shadow drawn over their bounding box — beautify and the
  post-capture frame are skipped when a capture intentionally carries an
  alpha shape, so the drawn outline is preserved.
- Capture-history SQLite connections are now always closed. The previous
  `with sqlite3.connect(...)` only committed the transaction and left the
  connection (and its file handle) open, leaking one per capture/history op
  over a long tray session.

### Editor — performance
- Undo history is now capped by an estimated memory budget (512 MB) in
  addition to the state count, so a long painting session on a large,
  multi-layer document no longer pins gigabytes of snapshots.
- Flood fill (paint-bucket) is vectorized (numpy colour-match + scanline
  region grow) instead of a per-pixel Python BFS, so large fills no longer
  freeze the UI for seconds.
- Content-aware fill uses a vectorized diffusion inpaint (seed + iterative
  blur-and-restore) instead of a per-pixel random-patch search, so filling a
  large selection is fast and blends the surrounding colours in smoothly.

### Accessibility
- The image editor, its canvas, every toolbar tool button, and the layer-panel
  controls (layer list, opacity, blend mode, visibility, lock) now expose
  accessible names/descriptions for screen readers.

### Editor — polish
- Panning, zoom-to-cursor, and free-transform scaling now behave correctly
  when the canvas view is rotated (they used raw screen deltas before, so the
  canvas moved the wrong way and zoom drifted under a rotated view).
- Off-canvas paint expansion also shifts guides and the clone-stamp source
  into the grown canvas, so they no longer point at the wrong place.
- "Clear Capture History" reports the number of captures the panel actually
  shows (deduped) rather than a raw file count that could include hidden
  duplicate-content files.
- Undo/redo clear in-progress warp and move snapshots, so the next warp
  stroke records its own history entry and neither operates on stale layers.
- The layer panel highlights the correct row for the active layer even when
  groups above it are expanded.
- Reordering layers by drag keeps the same layer active (it followed the old
  slot number before, so the next stroke could land on a different layer).
- Gradients drawn on transparent pixels keep full color instead of being
  darkened twice (proper straight-alpha source-over compositing).
- Single-key tool shortcuts advertised in the toolbar tooltips (e.g. V, E, T,
  P, N, I) are now actually registered and switch tools.
- The Settings save-folder field is validated on apply: a nonexistent path
  offers to create the folder instead of silently falling back to Desktop.
- Undo no longer renames the grandchildren of nested groups to "… copy".
- Releasing Space after a temporary pan restores the active tool's cursor
  instead of forcing a plain arrow.
- The X foreground/background swap, eyedropper picks, and the swatch's
  right-click swap now repaint the toolbar color swatch immediately.
- Panning with the mouse keeps the rulers and navigator in sync (they only
  followed wheel zoom before).
- The editor's poll and panel-refresh timers stop when the window closes, so
  a standalone editor no longer ticks on a closed window.
- Icon default color is resolved at draw time so it follows the active theme.

### Editor — correctness fixes
- Layer groups composite children with proper source-over alpha, so a
  50%-opacity child no longer renders at 25% (and soft edges no longer
  darken) inside a group.
- Translucent pencil and spray strokes composite over the layer instead of
  replacing its alpha, so they no longer punch transparent holes.
- Adjustments applied while editing a layer mask no longer crash (the mask
  is handed to the adjustment as RGBA, not RGB).
- Exporting a flattened PNG/WebP no longer clears the unsaved-changes flag —
  export isn't the same as saving the layered `.swiftshot` project, so the
  close prompt still fires.
- Ctrl+C with an active selection now also places the bitmap on the OS
  clipboard, matching the no-selection copy path.
- Pasting into an empty document records history and marks it dirty, so the
  pasted image is protected by the unsaved-changes prompt.
- Layer lock is now enforced on delete/cut selection, adjustments/filters,
  text, sticky notes, layer alignment, and the AI background-remove/upscale
  tools (they previously modified locked layers).

### Editor — unsaved-work protection
- New / Open / Open-Recent / Open-Project / paste-from-clipboard now prompt
  to save unsaved changes before replacing the document (previously the only
  gate was closing the window, so these paths silently discarded work).
- Loading a new document resets per-document state: the `.swiftshot` project
  path, remembered JPEG quality, saved paths, guides, and any active quick
  mask no longer leak from the previous document (a stale project path could
  make Ctrl+S overwrite the wrong file; stale JPEG quality re-saved silently).
- Internal: a single `pil_to_qimage` helper builds detached QImages with an
  explicit stride for both the paint path and pixmap conversion, removing a
  latent use-after-free footgun in the canvas paint event.

### Editor — data-loss fixes
- Move tool no longer destroys content dragged past the canvas edge: each
  drag step re-pastes from a pristine snapshot using the cumulative offset
  from the press point, and the layer mask is shifted with the image so
  masked layers stay in sync.
- Crop/Resize/Resize-Canvas/Rotate/Flip (whole-image and per-layer) now
  transform layer masks alongside the image and recurse into groups
  (updating group size). Previously masks were left at the old size and the
  editor crashed with 'images do not match' on the next repaint after
  cropping a masked document; groups kept stale children.
- Adjustments/filters and Merge Down refuse to run on a layer group instead
  of silently discarding the result (a group's image buffer is computed from
  its children and can't be written to): applying an adjustment no longer
  marks the document dirty while changing nothing, and merging onto a group
  no longer deletes the top layer after throwing the blend away.
- Select All / Deselect / Invert Selection shortcuts (Ctrl+A / Ctrl+D /
  Ctrl+Shift+I) work again — they were bound to two menu actions each, which
  Qt treats as ambiguous and fires neither.

### Capture & display scaling
- The process is now per-monitor DPI-aware with Qt scaling off, so widget
  coordinates equal physical screen pixels at every display scale factor.
  Previously 150%/175%/200% scaling broke every capture surface (overlay,
  pickers, crops, cursor draw) by mixing logical and physical coordinates.
- GDI fullscreen capture uses `SRCCOPY | CAPTUREBLT` (layered windows such
  as tooltips no longer capture black), interprets the blit as RGB32 (stray
  alpha bytes from layered windows no longer punch transparent holes into
  saved PNGs), and calls GetDIBits only after deselecting the bitmap.
- Multi-monitor capture no longer photographs the monitor-picker dialog:
  the grab fires only after the dialog has closed and had a paint cycle.
- Scrolling capture: Cancel/Esc/close actually stops the capture loop (it
  kept auto-scrolling the target window after dismissal), and the
  always-on-top progress dialog moves out of (or hides from) the capture
  rect instead of being stitched into every frame.
- Window picker and snap-edge detection skip DWM-cloaked windows (other
  virtual desktops, suspended UWP apps) — hovering can no longer select an
  invisible window. Child-window enumeration uses EnumChildWindows instead
  of an unsafe manual GW_CHILD/GW_HWNDNEXT walk over foreign processes.
- Win+PrintScreen (and any Win+key combo) passes through to Windows instead
  of being hijacked by the bare-key hotkey binding.
- Hotkey re-binding no longer risks orphaning the old keyboard hook: the
  WM_QUIT post is retried until it lands and a failed join is logged.
- Countdown badge derives remaining time from a monotonic clock instead of
  counting nominal timer ticks, so timed captures fire on time under load.

### Reliability & config
- The app version is no longer persisted into swiftshot.json and can no
  longer be overwritten by a config/import file. Older builds pinned the
  running version string to the release that wrote the config, making the
  updater nag "update available" forever after any upgrade.
- Numeric settings from config/import files are clamped to their Settings-UI
  ranges. A hand-edited `CAPTURE_HISTORY_MAX: 0` made the history pruner
  delete every capture immediately after saving it.
- Windows OCR output is decoded correctly: PowerShell 5.1 emits redirected
  stdout in the OEM code page, so non-ASCII OCR text (accents, quotes,
  non-Latin scripts) arrived as mojibake. The OCR script now forces UTF-8.
- Single-instance guard: a second SwiftShot exits immediately instead of
  fighting over the keyboard hook and log file (creates the
  `SwiftShot_SingleInstance` mutex the installer's AppMutex already checks).
- The installer's "open with SwiftShot" file association works: an image
  path on the command line now opens in the editor (previously the argument
  was ignored); the startup shortcut's `--minimized` flag is tolerated.
- "Launch at startup" failures are surfaced (message + log) instead of
  silently doing nothing; settings export failures and the capture
  win32→Qt fallback are logged; the corrupt-config message no longer claims
  a backup was saved when the backup copy itself failed.

### Editor
- `.swiftshot` project format v3: group layers round-trip with their exact
  size (previously a first-in-list or oversized group reloaded at 800×600 —
  silent data loss), children keep their name/visibility/opacity/blend
  mode/lock/mask/effects (previously all reset to defaults), groups keep
  their own masks, and nested groups survive. Legacy v2 files load with the
  group size taken from the saved composite. Project save/load failures are
  logged with tracebacks; the active-layer index is validated on load.
- Free Transform can be undone: the undo snapshot used to capture the
  already-transformed pixels, so Ctrl+Z after committing a transform was a
  permanent no-op.
- The Move tool records an undo step and refuses locked layers. (Off-canvas
  content preservation while moving is AB-01 in ROADMAP.md.)
- Paint tools refuse to target a layer group instead of silently discarding
  the stroke while still pushing a bogus undo entry.

### Tests
- 80 tests (75 → 80): project-format v3 round-trip (group size, child
  metadata/masks, nested groups, group masks/effects) and the legacy-v2
  group-size regression.

## [v2.8.0] - 2026-07-03

Audit-backlog drain: the verified-but-deferred findings from the v2.7.0 deep
audit, fixed end-to-end with regression tests (54 → 75 tests).

### Editor — correctness
- Rotate View no longer breaks mouse-to-image mapping. A single view
  transform (rotate-about-centre → pan → zoom) is shared by painting and
  coordinate mapping, and the rubylith/quick-mask overlays follow it.
- Semi-transparent brush, pen and shape strokes now composite over the layer
  instead of punching a translucency hole (proper source-over blending).
- Align panel aligns a layer's actual content bounding box (layers are
  canvas-sized, so it was a no-op that still cost an undo step); already-aligned
  content records no undo entry.
- Off-canvas stroke expansion now grows LayerGroups (their children and
  dimensions) and resizes the selection mask, fixing group misalignment and
  later composite/paste size-mismatch errors.
- Clone stamp near an image edge clips its source to the image, so it no
  longer paints transparent-black holes from crop() padding.
- Quick Mask can be cancelled with Esc, restoring the prior selection (the
  saved state was never read before).
- JPEG save asks for quality once per document and mattes transparency onto
  white instead of black.

### Editor — theming & performance
- The editor honours the light theme (its palette was bound to the dark set
  at import); transparency checker and slider border are theme-aware.
- Soft-brush stamp, healing and dodge/burn/sponge/smudge retouch are
  vectorized (were per-pixel Python loops); content-aware fill shows a busy
  cursor.
- Panel refreshes are coalesced into one debounced update instead of a
  per-paint singleShot flood; the marching-ants timer idles when hidden.
- Magnetic lasso previews the snapped edge as the cursor moves between clicks.

### Capture
- Mouse-pointer capture renders the real cursor shape (I-beam, hand, resize)
  via DrawIconEx, reconstructing alpha for legacy cursors, instead of a
  generic drawn arrow.
- Scrolling capture packs WM_MOUSEWHEEL coordinates as signed words (fixes
  negative multi-monitor positions) and keeps the smallest matching overlap
  so repeating content isn't over-trimmed.

### Settings
- The Frame tab (border / drop shadow / rounded corners) is wired to a
  post-capture frame step with enable toggles; the editor Obfuscate action
  honours the configured strength and pixelate/blur mode. The orphan
  editor highlight-colour setting (no consumer) was removed.

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
