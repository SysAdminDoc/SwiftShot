#Requires -Version 5.1
<#
.SYNOPSIS
    SwiftShot Build System - Produces a professional installer AND portable executable.

.DESCRIPTION
    End-to-end build pipeline:
      1. Verifies Python 3.8+ and Inno Setup 6 (optional)
      2. Creates an isolated build venv with PyInstaller + Pillow
      3. Generates swiftshot.ico (multi-size, from generate_icon.py)
      4. Builds SwiftShot-Portable.exe  (PyInstaller --onefile)
      5. Builds SwiftShot\ directory     (PyInstaller --onedir)
      6. Packages SwiftShot-Setup.exe    (Inno Setup installer)

    All outputs land in the dist\ folder. Both executables are fully
    self-contained -- no Python or runtime required on end-user machines.

    Requirements (build machine only):
      - Python 3.8+
      - Inno Setup 6+ (optional, for installer; portable builds without it)

.PARAMETER PortableOnly
    Skip the Inno Setup installer build.

.PARAMETER InstallerOnly
    Skip the portable single-file build.

.PARAMETER Clean
    Remove all previous build artifacts before building.

.PARAMETER DebugBuild
    Build with console window visible for debugging.

.PARAMETER SkipIcon
    Skip icon generation (use existing swiftshot.ico).

.EXAMPLE
    .\Build-SwiftShot.ps1
    .\Build-SwiftShot.ps1 -PortableOnly
    .\Build-SwiftShot.ps1 -Clean -DebugBuild

.NOTES
    Author:  SwiftShot Project
    License: GPL-3.0
#>

[CmdletBinding()]
param(
    [switch]$PortableOnly,
    [switch]$InstallerOnly,
    [switch]$Clean,
    [switch]$DebugBuild,
    [switch]$SkipIcon
)

$ErrorActionPreference = 'Stop'
$ProgressPreference    = 'SilentlyContinue'

# -------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------
$AppName     = "SwiftShot"
$AppVersion  = "2.0.0"
$ProjectDir  = $PSScriptRoot
$DistDir     = Join-Path $ProjectDir "dist"
$BuildDir    = Join-Path $ProjectDir "build"
$VenvDir     = Join-Path $ProjectDir ".build-venv"
$IconName    = "swiftshot.ico"
$IconPath    = Join-Path $ProjectDir $IconName
$IssFile     = Join-Path $ProjectDir "SwiftShot.iss"
$IconGenScript = Join-Path $ProjectDir "generate_icon.py"

# Every .py file that ships with SwiftShot
$SourceFiles = @(
    "main.py", "app.py", "capture.py", "capture_menu.py", "config.py",
    "editor.py", "hotkeys.py", "monitor_picker.py", "ocr.py", "ocr_dialog.py",
    "overlay.py", "settings_dialog.py", "theme.py", "window_picker.py",
    "pin_window.py", "capture_history.py", "countdown_overlay.py",
    "scrolling_capture.py", "utils.py"
)

# Hidden imports for PyInstaller (lazy imports it can't detect)
$HiddenImports = @(
    "app", "config", "theme", "hotkeys", "capture", "capture_menu",
    "overlay", "window_picker", "monitor_picker", "editor",
    "settings_dialog", "ocr", "ocr_dialog", "pin_window",
    "capture_history", "countdown_overlay", "scrolling_capture", "utils",
    "PyQt5.QtPrintSupport", "PyQt5.sip",
    "PyQt5.QtCore", "PyQt5.QtGui", "PyQt5.QtWidgets"
)

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
function Write-Section([string]$msg) {
    Write-Host ""
    Write-Host ("=" * 70) -ForegroundColor Cyan
    Write-Host "  $msg" -ForegroundColor Cyan
    Write-Host ("=" * 70) -ForegroundColor Cyan
}

function Write-Step([string]$msg)    { Write-Host "  [-] $msg" -ForegroundColor Yellow }
function Write-OK([string]$msg)      { Write-Host "  [+] $msg" -ForegroundColor Green  }
function Write-Err([string]$msg)     { Write-Host "  [!] $msg" -ForegroundColor Red    }
function Write-Info([string]$msg)    { Write-Host "      $msg" -ForegroundColor DarkGray }
function Write-FileSize([string]$label, [string]$path) {
    if (Test-Path $path) {
        $size = [math]::Round((Get-Item $path).Length / 1MB, 1)
        Write-Host "  [+] ${label}: $(Split-Path $path -Leaf) (${size} MB)" -ForegroundColor Green
    }
}

# -------------------------------------------------------------------
# Banner
# -------------------------------------------------------------------
Write-Host ""
Write-Host "  ____          _  __ _   ____  _           _   " -ForegroundColor Cyan
Write-Host " / ___|_      _(_)/ _| |_/ ___|| |__   ___ | |_ " -ForegroundColor Cyan
Write-Host " \___ \ \ /\ / / | |_| __\___ \| '_ \ / _ \| __|" -ForegroundColor Cyan
Write-Host "  ___) \ V  V /| |  _| |_ ___) | | | | (_) | |_ " -ForegroundColor Cyan
Write-Host " |____/ \_/\_/ |_|_|  \__|____/|_| |_|\___/ \__|" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Build System v${AppVersion}" -ForegroundColor DarkGray
Write-Host ""

# ===================================================================
# STEP 1: Clean (optional)
# ===================================================================
if ($Clean) {
    Write-Section "Cleaning Previous Builds"
    foreach ($dir in @($DistDir, $BuildDir, $VenvDir)) {
        if (Test-Path $dir) {
            Write-Step "Removing $(Split-Path $dir -Leaf)\"
            Remove-Item $dir -Recurse -Force
        }
    }
    foreach ($f in @("*.spec")) {
        Get-ChildItem $ProjectDir -Filter $f | ForEach-Object {
            Write-Step "Removing $($_.Name)"
            Remove-Item $_.FullName -Force
        }
    }
    Write-OK "Clean complete."
}

# ===================================================================
# STEP 2: Verify Prerequisites
# ===================================================================
Write-Section "Checking Prerequisites"

# --- Python ---
$Python = $null
foreach ($cmd in @('python', 'python3', 'py')) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match 'Python 3\.(\d+)') {
            $minor = [int]$Matches[1]
            if ($minor -ge 8) {
                $Python = $cmd
                Write-OK "Python: $ver"
                break
            }
        }
    } catch { }
}
if (-not $Python) {
    Write-Err "Python 3.8+ is required but not found on PATH."
    Write-Info "Download from: https://www.python.org/downloads/"
    exit 1
}

# --- Inno Setup (optional) ---
$ISCC = $null
if (-not $PortableOnly) {
    $isccPaths = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
        "${env:LOCALAPPDATA}\Programs\Inno Setup 6\ISCC.exe"
    )
    foreach ($p in $isccPaths) {
        if (Test-Path $p) { $ISCC = $p; break }
    }
    if (-not $ISCC) {
        try { $ISCC = (Get-Command iscc -ErrorAction Stop).Source } catch { }
    }
    if ($ISCC) {
        Write-OK "Inno Setup: $ISCC"
    } else {
        Write-Err "Inno Setup 6 not found. Installer build will be skipped."
        Write-Info "Download from: https://jrsoftware.org/isdl.php"
        if ($InstallerOnly) { exit 1 }
    }
}

# --- Source files ---
$missingSrc = @()
foreach ($f in $SourceFiles) {
    if (-not (Test-Path (Join-Path $ProjectDir $f))) { $missingSrc += $f }
}
if ($missingSrc.Count -gt 0) {
    Write-Err "Missing source files: $($missingSrc -join ', ')"
    exit 1
}
Write-OK "All $($SourceFiles.Count) source files present."

# ===================================================================
# STEP 3: Build Virtual Environment
# ===================================================================
Write-Section "Build Environment"

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

if (Test-Path $VenvPython) {
    Write-OK "Build venv exists: .build-venv\"
} else {
    Write-Step "Creating isolated build venv..."
    $ErrorActionPreference = 'Continue'
    & $Python -m venv $VenvDir
    $venvExit = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($venvExit -ne 0) {
        Write-Err "Failed to create venv."
        exit 1
    }
    Write-OK "Venv created."
}

Write-Step "Installing/upgrading build dependencies..."
$ErrorActionPreference = 'Continue'
& $VenvPython -m pip install --upgrade pip --quiet 2>&1 | Out-Null
& $VenvPython -m pip install --upgrade pyinstaller pillow pyqt5 --quiet 2>&1 | Out-Null
$pipExit = $LASTEXITCODE
$ErrorActionPreference = 'Stop'
if ($pipExit -ne 0) {
    Write-Err "Failed to install build dependencies."
    exit 1
}

# Verify PyInstaller
$ErrorActionPreference = 'Continue'
$pyiVer = & $VenvPython -m PyInstaller --version 2>&1
$ErrorActionPreference = 'Stop'
Write-OK "PyInstaller: $pyiVer"

# ===================================================================
# STEP 4: Generate Application Icon
# ===================================================================
Write-Section "Application Icon"

if ($SkipIcon -and (Test-Path $IconPath)) {
    Write-OK "Using existing icon: $IconName"
} elseif (Test-Path $IconGenScript) {
    Write-Step "Generating multi-size icon from generate_icon.py..."
    $ErrorActionPreference = 'Continue'
    & $VenvPython $IconGenScript 2>&1 | ForEach-Object { Write-Info $_.ToString() }
    $ErrorActionPreference = 'Stop'
    if (Test-Path $IconPath) {
        $icoSize = [math]::Round((Get-Item $IconPath).Length / 1KB, 1)
        Write-OK "Icon generated: $IconName (${icoSize} KB, 9 sizes: 16-256px)"
    } else {
        Write-Err "Icon generation failed. Build will continue without custom icon."
    }
} else {
    Write-Err "generate_icon.py not found and no swiftshot.ico exists."
    Write-Info "The build will use the default PyInstaller icon."
}

# ===================================================================
# STEP 5: PyInstaller Common Arguments
# ===================================================================
$commonArgs = @(
    "--name=SwiftShot"
    "--windowed"
    "--noconfirm"
    "--clean"
    "--paths=$ProjectDir"
)

# Hidden imports
foreach ($mod in $HiddenImports) {
    $commonArgs += "--hidden-import=$mod"
}

# Collect only the PyQt5 modules we actually use (not the entire framework)
$commonArgs += "--collect-submodules=PyQt5.QtCore"
$commonArgs += "--collect-submodules=PyQt5.QtGui"
$commonArgs += "--collect-submodules=PyQt5.QtWidgets"
$commonArgs += "--collect-submodules=PyQt5.QtPrintSupport"
$commonArgs += "--collect-submodules=PyQt5.sip"

# Bundle the .ico alongside the exe so the app can load it at runtime
if (Test-Path $IconPath) {
    $commonArgs += "--icon=$IconPath"
    $commonArgs += "--add-data=$IconPath;."
    # Also bundle the source PNG for runtime use
    $pngPath = Join-Path $ProjectDir "swiftshot.png"
    if (Test-Path $pngPath) {
        $commonArgs += "--add-data=$pngPath;."
    }
}

# Exclude bloat modules
foreach ($mod in @('tkinter','matplotlib','numpy','scipy','pandas',
                   'test','unittest','pydoc','doctest','lib2to3','setuptools',
                   'PyQt5.Qt3D','PyQt5.QtWebEngine','PyQt5.QtWebEngineCore',
                   'PyQt5.QtWebEngineWidgets','PyQt5.QtMultimedia',
                   'PyQt5.QtMultimediaWidgets','PyQt5.QtQml','PyQt5.QtQuick',
                   'PyQt5.QtSql','PyQt5.QtBluetooth','PyQt5.QtNfc',
                   'PyQt5.QtSensors','PyQt5.QtSerialPort','PyQt5.QtLocation',
                   'PyQt5.QtPositioning','PyQt5.QtRemoteObjects',
                   'PyQt5.QtWebSockets','PyQt5.QtWebChannel',
                   'PyQt5.QtDesigner','PyQt5.uic')) {
    $commonArgs += "--exclude-module=$mod"
}

if ($DebugBuild) {
    $commonArgs += "--debug=all"
    $commonArgs += "--console"
    Write-Info "Debug mode: console window will be visible."
}

# Version info file -- gives the exe professional Properties tab info
$VersionFile = Join-Path $ProjectDir "version_info.txt"
if (-not (Test-Path $VersionFile)) {
    Write-Step "Generating version info for exe properties..."
    $versionContent = @"
# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(2, 0, 0, 0),
    prodvers=(2, 0, 0, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          u'040904B0',
          [StringStruct(u'CompanyName', u'SwiftShot Project'),
           StringStruct(u'FileDescription', u'SwiftShot Screenshot Tool'),
           StringStruct(u'FileVersion', u'2.0.0.0'),
           StringStruct(u'InternalName', u'SwiftShot'),
           StringStruct(u'LegalCopyright', u'Copyright (C) 2025 SwiftShot Project. GPL-3.0'),
           StringStruct(u'OriginalFilename', u'SwiftShot.exe'),
           StringStruct(u'ProductName', u'SwiftShot'),
           StringStruct(u'ProductVersion', u'2.0.0.0')])
      ]
    ),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"@
    Set-Content -Path $VersionFile -Value $versionContent -Encoding UTF8
    Write-OK "version_info.txt generated (exe Properties tab metadata)."
}
$commonArgs += "--version-file=$VersionFile"

$mainScript = Join-Path $ProjectDir "main.py"

# ---------------------------------------------------------------
# PyInstaller has issues when the project path contains spaces or
# parentheses (DLL resolution fails in onedir mode).  Detect this
# and use a sanitized temp workdir for the build step.
# ---------------------------------------------------------------
$UnsafePath = $ProjectDir -match '[\s\(\)]'
$OrigProjectDir = $ProjectDir
if ($UnsafePath) {
    $SafeBuildRoot = Join-Path $env:TEMP "SwiftShot-Build"
    if (Test-Path $SafeBuildRoot) { Remove-Item $SafeBuildRoot -Recurse -Force }
    Write-Step "Path contains spaces/parentheses - copying source to safe build path..."
    New-Item -Path $SafeBuildRoot -ItemType Directory -Force | Out-Null

    # Copy only what PyInstaller needs
    foreach ($f in $SourceFiles) {
        Copy-Item (Join-Path $ProjectDir $f) $SafeBuildRoot -Force
    }
    if (Test-Path $IconPath) {
        Copy-Item $IconPath $SafeBuildRoot -Force
    }
    $pngPath = Join-Path $ProjectDir "swiftshot.png"
    if (Test-Path $pngPath) {
        Copy-Item $pngPath $SafeBuildRoot -Force
    }
    if (Test-Path $VersionFile) {
        Copy-Item $VersionFile $SafeBuildRoot -Force
    }
    Copy-Item (Join-Path $ProjectDir "requirements.txt") $SafeBuildRoot -Force -ErrorAction SilentlyContinue

    # Update paths for PyInstaller
    $BuildProjectDir = $SafeBuildRoot
    $mainScript      = Join-Path $SafeBuildRoot "main.py"
    $IconPathSafe    = Join-Path $SafeBuildRoot $IconName
    $VersionFileSafe = Join-Path $SafeBuildRoot "version_info.txt"

    # Rebuild commonArgs with safe paths
    $commonArgs = @(
        "--name=SwiftShot"
        "--windowed"
        "--noconfirm"
        "--clean"
        "--paths=$BuildProjectDir"
    )
    foreach ($mod in $HiddenImports) {
        $commonArgs += "--hidden-import=$mod"
    }
    $commonArgs += "--collect-submodules=PyQt5.QtCore"
    $commonArgs += "--collect-submodules=PyQt5.QtGui"
    $commonArgs += "--collect-submodules=PyQt5.QtWidgets"
    $commonArgs += "--collect-submodules=PyQt5.QtPrintSupport"
    $commonArgs += "--collect-submodules=PyQt5.sip"
    if (Test-Path $IconPathSafe) {
        $commonArgs += "--icon=$IconPathSafe"
        $commonArgs += "--add-data=$IconPathSafe;."
        $pngPathSafe = Join-Path $SafeBuildRoot "swiftshot.png"
        if (Test-Path $pngPathSafe) {
            $commonArgs += "--add-data=$pngPathSafe;."
        }
    }
    foreach ($mod in @('tkinter','matplotlib','numpy','scipy','pandas',
                       'test','unittest','pydoc','doctest','lib2to3','setuptools',
                       'PyQt5.Qt3D','PyQt5.QtWebEngine','PyQt5.QtWebEngineCore',
                       'PyQt5.QtWebEngineWidgets','PyQt5.QtMultimedia',
                       'PyQt5.QtMultimediaWidgets','PyQt5.QtQml','PyQt5.QtQuick',
                       'PyQt5.QtSql','PyQt5.QtBluetooth','PyQt5.QtNfc',
                       'PyQt5.QtSensors','PyQt5.QtSerialPort','PyQt5.QtLocation',
                       'PyQt5.QtPositioning','PyQt5.QtRemoteObjects',
                       'PyQt5.QtWebSockets','PyQt5.QtWebChannel',
                       'PyQt5.QtDesigner','PyQt5.uic')) {
        $commonArgs += "--exclude-module=$mod"
    }
    if ($DebugBuild) {
        $commonArgs += "--debug=all"
        $commonArgs += "--console"
    }
    $commonArgs += "--version-file=$VersionFileSafe"

    Write-OK "Safe build path: $SafeBuildRoot"
} else {
    $BuildProjectDir = $ProjectDir
}

# ===================================================================
# STEP 6: Build Portable Executable (onefile)
# ===================================================================
if (-not $InstallerOnly) {
    Write-Section "Building Portable Executable (onefile)"
    Write-Step "Running PyInstaller (single file)..."

    $portableTmpDir = Join-Path $DistDir "_portable_tmp"
    $onefileArgs = $commonArgs + @(
        "--onefile"
        "--distpath=$portableTmpDir"
        $mainScript
    )

    Push-Location $BuildProjectDir
    try {
        $ErrorActionPreference = 'Continue'
        & $VenvPython -m PyInstaller @onefileArgs 2>&1 | ForEach-Object {
            $line = $_.ToString()
            if ($line -match "ERROR|FATAL") { Write-Err $line }
            elseif ($line -match "WARNING" -and $line -notmatch "previously imported") { Write-Info $line }
        }
        $ErrorActionPreference = 'Stop'
        if ($LASTEXITCODE -ne 0) {
            Write-Err "PyInstaller (onefile) failed with exit code $LASTEXITCODE."
            Pop-Location
            exit 1
        }
    } finally {
        Pop-Location
    }

    $tmpExe      = Join-Path $portableTmpDir "SwiftShot.exe"
    $portableExe = Join-Path $DistDir "SwiftShot-Portable.exe"
    if (Test-Path $tmpExe) {
        New-Item -Path $DistDir -ItemType Directory -Force | Out-Null
        Move-Item $tmpExe $portableExe -Force
        Remove-Item $portableTmpDir -Recurse -Force -ErrorAction SilentlyContinue
        Write-FileSize "Portable" $portableExe
    } else {
        Write-Err "Portable build output not found."
        exit 1
    }
}

# ===================================================================
# STEP 7: Build Installer Package (onedir)
# ===================================================================
if (-not $PortableOnly) {
    Write-Section "Building Installer Package (onedir)"
    Write-Step "Running PyInstaller (directory bundle)..."

    # Output the onedir to the ORIGINAL project's dist folder
    $onedirDistPath = Join-Path $OrigProjectDir "dist"
    $onedirArgs = $commonArgs + @(
        "--onedir"
        "--distpath=$onedirDistPath"
        $mainScript
    )

    Push-Location $BuildProjectDir
    try {
        $ErrorActionPreference = 'Continue'
        & $VenvPython -m PyInstaller @onedirArgs 2>&1 | ForEach-Object {
            $line = $_.ToString()
            if ($line -match "ERROR|FATAL") { Write-Err $line }
            elseif ($line -match "WARNING" -and $line -notmatch "previously imported") { Write-Info $line }
        }
        $ErrorActionPreference = 'Stop'
        if ($LASTEXITCODE -ne 0) {
            Write-Err "PyInstaller (onedir) failed with exit code $LASTEXITCODE."
            Pop-Location
            exit 1
        }
    } finally {
        Pop-Location
    }

    $onedirExe = Join-Path $DistDir "SwiftShot\SwiftShot.exe"
    if (Test-Path $onedirExe) {
        # Copy icon into the onedir output so it's always beside the exe
        if (Test-Path $IconPath) {
            Copy-Item $IconPath (Join-Path $DistDir "SwiftShot\swiftshot.ico") -Force
        }
        $pngSrc = Join-Path $OrigProjectDir "swiftshot.png"
        if (Test-Path $pngSrc) {
            Copy-Item $pngSrc (Join-Path $DistDir "SwiftShot\swiftshot.png") -Force
        }
        $totalSize = [math]::Round(((Get-ChildItem (Join-Path $DistDir "SwiftShot") -Recurse | Measure-Object -Property Length -Sum).Sum) / 1MB, 1)
        Write-OK "Installer package: dist\SwiftShot\ (${totalSize} MB total)"
    } else {
        Write-Err "Onedir build output not found."
        exit 1
    }
}

# ===================================================================
# STEP 8: Build Inno Setup Installer
# ===================================================================
if (-not $PortableOnly -and $ISCC) {
    Write-Section "Building Windows Installer (Inno Setup)"

    if (-not (Test-Path $IssFile)) {
        Write-Err "Inno Setup script not found: SwiftShot.iss"
    } else {
        $onedirCheck = Join-Path $DistDir "SwiftShot\SwiftShot.exe"
        if (-not (Test-Path $onedirCheck)) {
            Write-Err "PyInstaller output missing. Run build without -PortableOnly first."
        } else {
            Write-Step "Compiling installer with ISCC..."
            $ErrorActionPreference = 'Continue'
            & $ISCC /Q $IssFile 2>&1 | ForEach-Object {
                $line = $_.ToString()
                if ($line -match "Error") { Write-Err $line }
                else { Write-Info $line }
            }
            $isccExit = $LASTEXITCODE
            $ErrorActionPreference = 'Stop'
            if ($isccExit -ne 0) {
                Write-Err "Inno Setup compilation failed."
            } else {
                $setupExe = Join-Path $DistDir "SwiftShot-Setup.exe"
                if (Test-Path $setupExe) {
                    Write-FileSize "Installer" $setupExe
                } else {
                    Write-Err "Installer exe not found in dist\."
                }
            }
        }
    }
} elseif (-not $PortableOnly -and -not $ISCC) {
    Write-Section "Installer Build (SKIPPED)"
    Write-Info "Inno Setup 6 not found. Install from: https://jrsoftware.org/isdl.php"
}

# ===================================================================
# Summary
# ===================================================================
Write-Host ""
Write-Host ("=" * 70) -ForegroundColor Green
Write-Host "  BUILD COMPLETE" -ForegroundColor Green
Write-Host ("=" * 70) -ForegroundColor Green
Write-Host ""

$setupExe    = Join-Path $DistDir "SwiftShot-Setup.exe"
$portableExe = Join-Path $DistDir "SwiftShot-Portable.exe"
$outputs = 0

if (Test-Path $portableExe) {
    $size = [math]::Round((Get-Item $portableExe).Length / 1MB, 1)
    Write-Host "  PORTABLE    dist\SwiftShot-Portable.exe  (${size} MB)" -ForegroundColor White
    Write-Host "              Single file. Run from anywhere. No install needed." -ForegroundColor DarkGray
    Write-Host ""
    $outputs++
}
if (Test-Path $setupExe) {
    $size = [math]::Round((Get-Item $setupExe).Length / 1MB, 1)
    Write-Host "  INSTALLER   dist\SwiftShot-Setup.exe     (${size} MB)" -ForegroundColor White
    Write-Host "              Start Menu + Desktop shortcut. Optional auto-start." -ForegroundColor DarkGray
    Write-Host "              Professional uninstaller in Add/Remove Programs." -ForegroundColor DarkGray
    Write-Host ""
    $outputs++
}

if ($outputs -eq 0) {
    Write-Host "  No outputs produced. Check errors above." -ForegroundColor Red
} else {
    Write-Host "  Both outputs are fully self-contained." -ForegroundColor DarkGray
    Write-Host "  No Python, no runtime, no dependencies on end-user machines." -ForegroundColor DarkGray
}

# Clean up temp safe build dir if used
if ($UnsafePath -and (Test-Path $SafeBuildRoot)) {
    Remove-Item $SafeBuildRoot -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host ""
