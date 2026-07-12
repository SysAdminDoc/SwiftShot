"""
SwiftShot OCR Module
Extracts text from images using available OCR engines.

Strategy (zero-dependency first):
  1. Windows 10/11 built-in OCR via PowerShell (WinRT OcrEngine)
  2. pytesseract (if Tesseract is installed)
  3. Graceful error with install instructions
"""

import os
import sys
import subprocess
import tempfile

from logger import log


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

    $ocrEngine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    if ($null -eq $ocrEngine) {
        Write-Error "OCR_ERROR: No OCR engine available for your language settings."
        exit 1
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
        pixmap.save(tmp_path, 'PNG')
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

    # Strategy 1: Windows built-in OCR
    if sys.platform == 'win32':
        try:
            return _ocr_windows(image_path)
        except Exception as e:
            win_error = str(e)
    else:
        win_error = "Not on Windows"

    # Strategy 2: pytesseract
    tess_error = None
    try:
        return _ocr_tesseract(image_path)
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
        pixmap.save(tmp_path, 'PNG')
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
    row_y = ws[0]["y"]
    for wd in ws[1:]:
        if abs(wd["y"] - row_y) <= row_tol:
            cur.append(wd)
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


def _ocr_windows(image_path, mode="text"):
    """Use Windows 10/11 WinRT OcrEngine via PowerShell. mode 'words' emits
    per-word bounding boxes (X\\tY\\tW\\tH\\tText) for table detection."""
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
        result = subprocess.run(
            [
                'powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                '-File', script_path
            ],
            capture_output=True, text=True, timeout=30,
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


def _ocr_tesseract(image_path):
    """Use pytesseract (requires Tesseract installed)."""
    import pytesseract
    from PIL import Image
    img = Image.open(image_path)
    text = pytesseract.image_to_string(img)
    return text.strip()


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
