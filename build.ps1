#Requires -Version 5.1
<#
.SYNOPSIS
    SwiftShot Build Script - Packages SwiftShot as a standalone Windows executable.

.DESCRIPTION
    This script installs dependencies and uses PyInstaller to create a single-file
    Windows executable with no external dependencies required at runtime.

.NOTES
    Requirements: Python 3.8+ must be installed and on PATH.
    Run from the SwiftShot project directory.
#>

param(
    [switch]$Clean,
    [switch]$OneFile,
    [switch]$Debug
)

$ErrorActionPreference = 'Stop'
$ProjectDir = $PSScriptRoot
$DistDir = Join-Path $ProjectDir "dist"
$BuildDir = Join-Path $ProjectDir "build"

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  SwiftShot Build Script" -ForegroundColor Cyan
Write-Host "  Packaging standalone Windows executable..." -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# --- Check Python ---
$python = $null
foreach ($cmd in @('python', 'python3', 'py')) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match 'Python 3') {
            $python = $cmd
            Write-Host "[OK] Found: $ver" -ForegroundColor Green
            break
        }
    } catch { }
}

if (-not $python) {
    Write-Host "[ERROR] Python 3.8+ is required but not found on PATH." -ForegroundColor Red
    Write-Host "        Download from: https://www.python.org/downloads/" -ForegroundColor Yellow
    exit 1
}

# --- Clean ---
if ($Clean) {
    Write-Host "[INFO] Cleaning previous build artifacts..." -ForegroundColor Yellow
    @($DistDir, $BuildDir, (Join-Path $ProjectDir "*.spec")) | ForEach-Object {
        if (Test-Path $_) {
            Remove-Item $_ -Recurse -Force
            Write-Host "  Removed: $_" -ForegroundColor DarkGray
        }
    }
}

# --- Install dependencies ---
Write-Host ""
Write-Host "[INFO] Installing dependencies..." -ForegroundColor Yellow
& $python -m pip install --upgrade pip --quiet 2>&1 | Out-Null
& $python -m pip install -r (Join-Path $ProjectDir "requirements.txt") --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to install dependencies." -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Dependencies installed." -ForegroundColor Green

# --- Build with PyInstaller ---
Write-Host ""
Write-Host "[INFO] Building SwiftShot executable..." -ForegroundColor Yellow

$pyinstallerArgs = @(
    '--name=SwiftShot'
    '--windowed'                        # No console window
    '--noconfirm'
    '--clean'
    '--add-data=config.py;.'
    '--add-data=theme.py;.'
    '--add-data=app.py;.'
    '--add-data=capture.py;.'
    '--add-data=overlay.py;.'
    '--add-data=editor.py;.'
    '--add-data=hotkeys.py;.'
    '--add-data=settings_dialog.py;.'
    '--hidden-import=PyQt5.QtPrintSupport'
    '--hidden-import=PyQt5.sip'
    '--exclude-module=tkinter'
    '--exclude-module=matplotlib'
    '--exclude-module=numpy'
    '--exclude-module=scipy'
    '--exclude-module=pandas'
)

if ($OneFile) {
    $pyinstallerArgs += '--onefile'
    Write-Host "  Mode: Single-file executable" -ForegroundColor DarkGray
} else {
    $pyinstallerArgs += '--onedir'
    Write-Host "  Mode: Directory bundle" -ForegroundColor DarkGray
}

if ($Debug) {
    $pyinstallerArgs += '--debug=all'
    $pyinstallerArgs += '--console'  # Override windowed for debug
}

# Optional: Add icon if present
$iconPath = Join-Path $ProjectDir "swiftshot.ico"
if (Test-Path $iconPath) {
    $pyinstallerArgs += "--icon=$iconPath"
    Write-Host "  Icon: $iconPath" -ForegroundColor DarkGray
}

$mainScript = Join-Path $ProjectDir "main.py"
$pyinstallerArgs += $mainScript

Push-Location $ProjectDir
try {
    & $python -m PyInstaller @pyinstallerArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] PyInstaller build failed." -ForegroundColor Red
        exit 1
    }
} finally {
    Pop-Location
}

# --- Report ---
Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host "  BUILD SUCCESSFUL" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host ""

if ($OneFile) {
    $exePath = Join-Path $DistDir "SwiftShot.exe"
} else {
    $exePath = Join-Path $DistDir "SwiftShot" "SwiftShot.exe"
}

if (Test-Path $exePath) {
    $size = [math]::Round((Get-Item $exePath).Length / 1MB, 1)
    Write-Host "  Output: $exePath" -ForegroundColor White
    Write-Host "  Size:   ${size} MB" -ForegroundColor White
} else {
    $exePath = Join-Path $DistDir "SwiftShot"
    Write-Host "  Output: $exePath" -ForegroundColor White
}

Write-Host ""
Write-Host "  To create a single-file exe: .\build.ps1 -OneFile" -ForegroundColor DarkGray
Write-Host "  To debug build issues:       .\build.ps1 -Debug" -ForegroundColor DarkGray
Write-Host "  To clean first:              .\build.ps1 -Clean" -ForegroundColor DarkGray
Write-Host ""
