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
param([string]$ImagePath)

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

    Write-Output $ocrResult.Text

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


def _ocr_windows(image_path):
    """Use Windows 10/11 WinRT OcrEngine via PowerShell."""
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
        result = subprocess.run(
            [
                'powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                '-File', script_path, '-ImagePath', image_path
            ],
            capture_output=True, text=True, timeout=30,
            encoding='utf-8', errors='replace',
            creationflags=creation_flags
        )
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass

    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()

    stderr = result.stderr.strip()
    if 'OCR_ERROR' in stderr:
        raise RuntimeError(stderr.split('OCR_ERROR:')[-1].strip())

    if result.stdout.strip():
        return result.stdout.strip()

    raise RuntimeError(f"Windows OCR returned no text. stderr: {stderr}")


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
        import pytesseract
        return True
    except ImportError:
        pass
    return False
