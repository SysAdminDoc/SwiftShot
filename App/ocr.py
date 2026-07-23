"""
SwiftShot OCR Module
Extracts text from images using available OCR engines.

Strategy (zero-dependency first):
  1. Windows 10/11 built-in OCR via PowerShell (WinRT OcrEngine)
  2. pytesseract (if Tesseract is installed)
  3. Graceful error with install instructions
"""

import os
import re
import sys
import subprocess
import tempfile

from logger import log


OCR_TIMEOUT_SECONDS = 30

# Lists the Windows recognizer languages actually installed (nothing is
# downloaded). Emits one BCP-47 tag per line.
_WIN_OCR_LANGS_SCRIPT = r'''
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
try {
    $null = [Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]
    foreach ($l in [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages) {
        Write-Output $l.LanguageTag
    }
} catch {
    Write-Error "OCR_ERROR: $($_.Exception.Message)"
    exit 1
}
'''


def _configured_ocr_language():
    """The persisted OCR language tag ('auto' when unset/unavailable)."""
    try:
        import config
        return getattr(config, "OCR_LANGUAGE", "auto") or "auto"
    except Exception:
        return "auto"


_PII_PATTERNS = [
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),   # email
    re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),                       # IPv4
    re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b"),      # MAC
]

_PHONE_SHAPE = re.compile(r"\+?[\d(][\d\s().-]{8,}\d")
_NON_DIGIT = re.compile(r"\D")


def _looks_like_phone(text):
    """A phone number, not a date/price/ID. Requires 10-15 digits (rejects
    8-digit dates and short ID runs) plus a phone separator or a leading '+'
    (a bare digit run is more likely an ID; a comma/decimal is a price)."""
    t = text.strip()
    if not _PHONE_SHAPE.fullmatch(t):
        return False
    digits = _NON_DIGIT.sub("", t)
    if not (10 <= len(digits) <= 15):
        return False
    return t.startswith("+") or bool(re.search(r"[\s().-]", t))


def find_pii_words(words):
    """Return the OCR word boxes whose text is an email/IP/MAC address or a
    phone number — used to auto-redact personal data. Word-level (multi-token
    phone numbers OCR'd as separate words may only partly match)."""
    out = []
    for wd in words:
        text = wd.get("text", "")
        if any(p.search(text) for p in _PII_PATTERNS) or _looks_like_phone(text):
            out.append(wd)
    return out


_WIN_OCR_SCRIPT = r'''
# The image path arrives via an environment variable, not a -File parameter,
# so a path that begins with '-' can never be reinterpreted as a switch.
$ImagePath = $env:SWIFTSHOT_OCR_PATH

# Windows PowerShell 5.1 encodes redirected stdout in the OEM code page by
# default; Python decodes it as UTF-8. Force UTF-8 so non-ASCII OCR text
# (accents, quotes, non-Latin scripts) survives the pipe intact.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

try {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime

    $null = [Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]
    $null = [Windows.Graphics.Imaging.BitmapDecoder,Windows.Foundation,ContentType=WindowsRuntime]
    $null = [Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
    $null = [Windows.Storage.Streams.RandomAccessStream,Windows.Storage.Streams,ContentType=WindowsRuntime]

    $asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and
        $_.GetParameters().Count -eq 1 -and
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
    })[0]

    function Await($WinRtTask, $ResultType) {
        $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
        $netTask = $asTask.Invoke($null, @($WinRtTask))
        $netTask.Wait(-1) | Out-Null
        $netTask.Result
    }

    $storageFile = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($ImagePath)) `
                         ([Windows.Storage.StorageFile])

    $stream = Await ($storageFile.OpenAsync([Windows.Storage.FileAccessMode]::Read)) `
                    ([Windows.Storage.Streams.IRandomAccessStream])

    $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) `
                     ([Windows.Graphics.Imaging.BitmapDecoder])

    $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) `
                    ([Windows.Graphics.Imaging.SoftwareBitmap])

    # A specific BCP-47 tag (SWIFTSHOT_OCR_LANG) creates the engine from that
    # language; "auto"/empty follows the user's Windows language profile. The
    # requested language must already be installed — nothing is downloaded.
    $lang = $env:SWIFTSHOT_OCR_LANG
    if ($lang -and $lang -ne 'auto') {
        $null = [Windows.Globalization.Language,Windows.Foundation,ContentType=WindowsRuntime]
        $langObj = New-Object Windows.Globalization.Language $lang
        $ocrEngine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($langObj)
        if ($null -eq $ocrEngine) {
            Write-Error "OCR_ERROR: No OCR engine for language '$lang'. Install it under Settings > Time & language > Language & region > (language) > Optional features > Language pack."
            exit 1
        }
    } else {
        $ocrEngine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
        if ($null -eq $ocrEngine) {
            Write-Error "OCR_ERROR: No OCR engine available for your language settings."
            exit 1
        }
    }

    $ocrResult = Await ($ocrEngine.RecognizeAsync($bitmap)) `
                       ([Windows.Media.Ocr.OcrResult])

    if ($env:SWIFTSHOT_OCR_MODE -eq 'words') {
        # One word per line: X<TAB>Y<TAB>W<TAB>H<TAB>Text (for table detection).
        foreach ($line in $ocrResult.Lines) {
            foreach ($word in $line.Words) {
                $r = $word.BoundingRect
                Write-Output ("{0}`t{1}`t{2}`t{3}`t{4}" -f `
                    [int]$r.X, [int]$r.Y, [int]$r.Width, [int]$r.Height, $word.Text)
            }
        }
    } else {
        Write-Output $ocrResult.Text
    }

    $stream.Dispose()
}
catch {
    Write-Error "OCR_ERROR: $($_.Exception.Message)"
    exit 1
}
'''


def ocr_pixmap(pixmap):
    """Run OCR on a QPixmap. Returns extracted text string."""
    log.info("Starting OCR on pixmap")
    tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    tmp_path = tmp.name
    tmp.close()

    try:
        if not pixmap.save(tmp_path, 'PNG'):
            raise OSError("Qt could not encode the OCR image as PNG")
        result = ocr_file(tmp_path)
        log.info(f"OCR extracted {len(result)} characters")
        return result
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def ocr_file(image_path):
    """Run OCR on an image file. Returns extracted text string."""
    image_path = os.path.abspath(image_path)

    # An explicit "tesseract:<lang>" selection forces the Tesseract path with
    # that language and skips WinRT entirely (visible, deterministic).
    configured = _configured_ocr_language()
    tess_lang = configured.split(":", 1)[1] if configured.startswith("tesseract:") else None

    # Strategy 1: Windows built-in OCR (unless a Tesseract language was chosen)
    if sys.platform == 'win32' and tess_lang is None:
        try:
            return _ocr_windows(image_path)
        except Exception as e:
            win_error = str(e)
    else:
        win_error = "Tesseract language selected" if tess_lang else "Not on Windows"

    # Strategy 2: pytesseract
    tess_error = None
    try:
        return _ocr_tesseract(image_path, lang=tess_lang)
    except ImportError:
        tess_error = "pytesseract not installed"
    except Exception as e:
        tess_error = str(e)

    raise RuntimeError(
        f"OCR failed.\n\n"
        f"Windows OCR: {win_error}\n"
        f"Tesseract OCR: {tess_error}\n\n"
        f"To use Tesseract OCR as fallback:\n"
        f"  1. Install Tesseract: winget install UB-Mannheim.TesseractOCR\n"
        f"  2. Install Python binding: pip install pytesseract\n"
        f"  3. Ensure tesseract.exe is on your PATH"
    )


def ocr_words_pixmap(pixmap):
    """Run word-box OCR on a QPixmap. Returns list of {x,y,w,h,text}."""
    tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    tmp_path = tmp.name
    tmp.close()
    try:
        if not pixmap.save(tmp_path, 'PNG'):
            raise OSError("Qt could not encode the OCR image as PNG")
        return ocr_words_file(tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def ocr_words_file(image_path):
    """Word-box OCR (Windows WinRT only). Returns list of {x,y,w,h,text};
    empty list if unavailable."""
    if sys.platform != 'win32':
        return []
    raw = _ocr_windows(os.path.abspath(image_path), mode="words")
    words = []
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        try:
            x, y, w, h = (int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]))
        except ValueError:
            continue
        text = "\t".join(parts[4:])
        if text:
            words.append({"x": x, "y": y, "w": w, "h": h, "text": text})
    return words


def words_to_table(words):
    """Cluster OCR word boxes into rows/columns and emit a TSV table string.
    Rows are grouped by vertical position; a tab is inserted between words with
    a wide horizontal gap, a space otherwise. Falls back to '' for no words."""
    if not words:
        return ""
    ws = sorted(words, key=lambda d: (d["y"], d["x"]))
    heights = sorted(d["h"] for d in ws)
    med_h = heights[len(heights) // 2] or 1
    row_tol = med_h * 0.6
    col_gap = med_h * 1.2

    rows = []
    cur = [ws[0]]
    row_y = ws[0]["y"]      # running mean baseline of the current row
    for wd in ws[1:]:
        if abs(wd["y"] - row_y) <= row_tol:
            cur.append(wd)
            # Track the running mean so a gradually-drifting baseline (skewed
            # scans, superscripts) stays one row instead of splitting mid-row.
            row_y = sum(w["y"] for w in cur) / len(cur)
        else:
            rows.append(cur)
            cur = [wd]
            row_y = wd["y"]
    rows.append(cur)

    lines = []
    for row in rows:
        row = sorted(row, key=lambda d: d["x"])
        parts = [row[0]["text"]]
        for prev, wd in zip(row, row[1:]):
            gap = wd["x"] - (prev["x"] + prev["w"])
            parts.append("\t" if gap > col_gap else " ")
            parts.append(wd["text"])
        lines.append("".join(parts))
    return "\n".join(lines)


def _ocr_windows(image_path, mode="text", language=None):
    """Use Windows 10/11 WinRT OcrEngine via PowerShell. mode 'words' emits
    per-word bounding boxes (X\\tY\\tW\\tH\\tText) for table detection.
    language is a BCP-47 tag or 'auto'/None to follow the language profile."""
    script_tmp = tempfile.NamedTemporaryFile(
        suffix='.ps1', mode='w', delete=False, encoding='utf-8'
    )
    script_path = script_tmp.name
    script_tmp.write(_WIN_OCR_SCRIPT)
    script_tmp.close()

    try:
        creation_flags = 0
        if sys.platform == 'win32':
            creation_flags = subprocess.CREATE_NO_WINDOW
        run_env = dict(os.environ)
        run_env['SWIFTSHOT_OCR_PATH'] = os.path.abspath(image_path)
        run_env['SWIFTSHOT_OCR_MODE'] = mode
        run_env['SWIFTSHOT_OCR_LANG'] = language or _configured_ocr_language()
        result = subprocess.run(
            [
                'powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                '-File', script_path
            ],
            capture_output=True, text=True, timeout=OCR_TIMEOUT_SECONDS,
            encoding='utf-8', errors='replace',
            creationflags=creation_flags, env=run_env
        )
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass

    stderr = result.stderr.strip()
    if 'OCR_ERROR' in stderr:
        raise RuntimeError(stderr.split('OCR_ERROR:')[-1].strip())

    if result.returncode == 0:
        # Empty output with a clean exit means the engine ran and simply
        # found no text -- that is a valid result, not an error.
        return result.stdout.strip()

    raise RuntimeError(
        f"Windows OCR failed (exit code {result.returncode}). stderr: {stderr}")


def _ocr_tesseract(image_path, lang=None):
    """Use pytesseract (requires Tesseract installed). lang is a Tesseract
    language code (e.g. 'deu') or None for the default."""
    import pytesseract
    from PIL import Image
    # Explicitly close the decoder before ocr_pixmap() removes its temporary
    # file. Relying on CPython refcounting left the file locked with alternate
    # Pillow plugins/runtimes and leaked handles during repeated OCR batches.
    kwargs = {"timeout": OCR_TIMEOUT_SECONDS}
    if lang:
        kwargs["lang"] = lang
    with Image.open(image_path) as img:
        text = pytesseract.image_to_string(img, **kwargs)
    return text.strip()


# ── Language discovery / remediation (R-30) ──────────────────────────────────
def _parse_lang_tags(text):
    """Parse newline-separated BCP-47 tags; dedupe preserving order."""
    seen = []
    for line in (text or "").splitlines():
        tag = line.strip()
        if tag and "OCR_ERROR" not in tag and tag not in seen:
            seen.append(tag)
    return seen


def _parse_tesseract_langs(text):
    """Parse `tesseract --list-langs` output (a header line then one lang per
    line). 'osd' is an orientation model, not a language — drop it."""
    langs = []
    for line in (text or "").splitlines():
        t = line.strip()
        if not t or t.lower().startswith("list of available") or t == "osd":
            continue
        # A language code is a short token with no spaces.
        if " " not in t and "/" not in t and "\\" not in t:
            langs.append(t)
    return langs


def available_windows_ocr_languages():
    """Installed WinRT recognizer language tags (empty off Windows/on error)."""
    if sys.platform != 'win32':
        return []
    script_tmp = tempfile.NamedTemporaryFile(
        suffix='.ps1', mode='w', delete=False, encoding='utf-8')
    script_path = script_tmp.name
    script_tmp.write(_WIN_OCR_LANGS_SCRIPT)
    script_tmp.close()
    try:
        result = subprocess.run(
            ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
             '-File', script_path],
            capture_output=True, text=True, timeout=OCR_TIMEOUT_SECONDS,
            encoding='utf-8', errors='replace',
            creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception:
        return []
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass
    if result.returncode != 0:
        return []
    return _parse_lang_tags(result.stdout)


def available_tesseract_languages():
    """Installed Tesseract languages via `tesseract --list-langs` ([] if none)."""
    try:
        result = subprocess.run(
            ['tesseract', '--list-langs'],
            capture_output=True, text=True, timeout=OCR_TIMEOUT_SECONDS,
            encoding='utf-8', errors='replace',
            creationflags=(subprocess.CREATE_NO_WINDOW
                           if sys.platform == 'win32' else 0))
    except Exception:
        return []
    # tesseract prints the list to stderr on some builds, stdout on others.
    return _parse_tesseract_langs((result.stdout or "") + "\n" + (result.stderr or ""))


def ocr_language_status():
    """Discovery + remediation snapshot for the Settings UI:
    {selected, windows: [...], tesseract: [...], effective, install_hint}."""
    selected = _configured_ocr_language()
    win = available_windows_ocr_languages()
    tess = available_tesseract_languages()
    if selected != "auto" and selected in win:
        effective = selected
    elif win:
        effective = "auto (" + win[0] + ")"
    elif tess:
        effective = "tesseract:" + tess[0]
    else:
        effective = "none"
    hint = ("Add a Windows OCR language under Settings > Time & language > "
            "Language & region > (language) > Language options > install the "
            "language pack. For Tesseract, install a traineddata pack "
            "(e.g. winget install UB-Mannheim.TesseractOCR) and add languages.")
    return {"selected": selected, "windows": win, "tesseract": tess,
            "effective": effective, "install_hint": hint}


def is_ocr_available():
    """Quick check if any OCR engine is available."""
    if sys.platform == 'win32':
        try:
            import platform
            version_str = platform.version().split('.')[-1]
            # Safely parse build number (handles insider builds with letters)
            build = int(''.join(c for c in version_str if c.isdigit()) or '0')
            if build >= 10240:
                return True
        except Exception:
            pass
    try:
        import pytesseract  # noqa: F401 -- availability probe
        return True
    except ImportError:
        pass
    return False
