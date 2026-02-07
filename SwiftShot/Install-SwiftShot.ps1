#Requires -Version 5.1
<#
.SYNOPSIS
    SwiftShot Installer - One-click setup for SwiftShot screenshot tool.

.DESCRIPTION
    This installer will:
      1. Detect or install Python 3.8+ (via winget)
      2. Create an isolated virtual environment
      3. Install PyQt5 and Pillow into the venv
      4. Extract the embedded program icon (.ico)
      5. Create a single-click launcher (SwiftShot.cmd)
      6. Create Desktop and Start Menu shortcuts
      7. Optionally add SwiftShot to Windows Startup

    After installation, double-click the Desktop shortcut or run SwiftShot.cmd.

.PARAMETER InstallDir
    Installation directory. Defaults to the script's own directory.

.PARAMETER NoShortcuts
    Skip creating Desktop and Start Menu shortcuts.

.PARAMETER AddToStartup
    Add SwiftShot to Windows Startup (launches on login).

.PARAMETER Uninstall
    Remove virtual environment, shortcuts, startup entry, and generated files.

.NOTES
    Author:  SwiftShot Project
    License: GPL-3.0
#>

[CmdletBinding()]
param(
    [string]$InstallDir = "",
    [switch]$NoShortcuts,
    [switch]$AddToStartup,
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# -------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------
$AppName         = "SwiftShot"
$AppVersion      = "1.0.0"
$PythonMinMajor  = 3
$PythonMinMinor  = 8
$VenvDir         = ".venv"
$LauncherName    = "SwiftShot.cmd"
$IconName        = "swiftshot.ico"
$RequiredModules = @("PyQt5", "Pillow")

if ([string]::IsNullOrEmpty($InstallDir)) {
    $InstallDir = $PSScriptRoot
}
$InstallDir = (Resolve-Path -Path $InstallDir -ErrorAction SilentlyContinue).Path
if ([string]::IsNullOrEmpty($InstallDir)) {
    $InstallDir = $PSScriptRoot
}

$VenvPath      = Join-Path $InstallDir $VenvDir
$LauncherPath  = Join-Path $InstallDir $LauncherName
$IconPath      = Join-Path $InstallDir $IconName
$MainScript    = Join-Path $InstallDir "main.py"
$DesktopDir    = [Environment]::GetFolderPath("Desktop")
$StartMenuDir  = Join-Path ([Environment]::GetFolderPath("Programs")) $AppName
$StartupDir    = [Environment]::GetFolderPath("Startup")

# -------------------------------------------------------------------
# Helper Functions
# -------------------------------------------------------------------

function Write-Banner {
    Write-Host ""
    Write-Host "  =============================================" -ForegroundColor Cyan
    Write-Host "   $AppName Installer v$AppVersion" -ForegroundColor Cyan
    Write-Host "   Debloated Screenshot Tool for Windows" -ForegroundColor DarkCyan
    Write-Host "  =============================================" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Step {
    param([string]$Message)
    Write-Host "  [*] $Message" -ForegroundColor White
}

function Write-OK {
    param([string]$Message)
    Write-Host "  [OK] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "  [!!] $Message" -ForegroundColor Yellow
}

function Write-Err {
    param([string]$Message)
    Write-Host "  [ERROR] $Message" -ForegroundColor Red
}

function Write-Info {
    param([string]$Message)
    Write-Host "        $Message" -ForegroundColor DarkGray
}

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host "  --- $Title ---" -ForegroundColor DarkCyan
}

# -------------------------------------------------------------------
# Uninstall
# -------------------------------------------------------------------

if ($Uninstall) {
    Write-Banner
    Write-Section "Uninstalling $AppName"

    # Remove venv
    if (Test-Path $VenvPath) {
        Write-Step "Removing virtual environment..."
        Remove-Item -Path $VenvPath -Recurse -Force
        Write-OK "Virtual environment removed."
    }

    # Remove launcher
    if (Test-Path $LauncherPath) {
        Remove-Item -Path $LauncherPath -Force
        Write-OK "Launcher removed."
    }

    # Remove generated icon
    if (Test-Path $IconPath) {
        Remove-Item -Path $IconPath -Force
        Write-OK "Icon removed."
    }

    # Remove Desktop shortcut
    $desktopLnk = Join-Path $DesktopDir "$AppName.lnk"
    if (Test-Path $desktopLnk) {
        Remove-Item -Path $desktopLnk -Force
        Write-OK "Desktop shortcut removed."
    }

    # Remove Start Menu folder
    if (Test-Path $StartMenuDir) {
        Remove-Item -Path $StartMenuDir -Recurse -Force
        Write-OK "Start Menu entry removed."
    }

    # Remove Startup shortcut
    $startupLnk = Join-Path $StartupDir "$AppName.lnk"
    if (Test-Path $startupLnk) {
        Remove-Item -Path $startupLnk -Force
        Write-OK "Startup entry removed."
    }

    Write-Host ""
    Write-OK "Uninstall complete. Source files were not removed."
    Write-Info "To fully remove, delete the $InstallDir directory."
    Write-Host ""
    return
}

# -------------------------------------------------------------------
# Install
# -------------------------------------------------------------------

Write-Banner

# Verify main.py exists
if (-not (Test-Path $MainScript)) {
    Write-Err "main.py not found in $InstallDir"
    Write-Err "Run this installer from the SwiftShot project directory."
    exit 1
}

# ===================================================================
# STEP 1: Find or Install Python
# ===================================================================
Write-Section "Step 1: Python Runtime"

function Find-Python {
    <#
    .DESCRIPTION
        Searches for a usable Python 3.8+ interpreter.
        Checks: python, python3, py launcher, common install paths, winget paths.
    #>
    $candidates = @(
        "python"
        "python3"
    )

    # Add common Windows install locations
    $commonPaths = @(
        "$env:LOCALAPPDATA\Programs\Python\Python*\python.exe"
        "$env:ProgramFiles\Python*\python.exe"
        "${env:ProgramFiles(x86)}\Python*\python.exe"
        "$env:LOCALAPPDATA\Microsoft\WindowsApps\python*.exe"
    )
    foreach ($pattern in $commonPaths) {
        $found = Get-ChildItem -Path $pattern -ErrorAction SilentlyContinue |
                 Sort-Object Name -Descending |
                 Select-Object -First 1
        if ($found) { $candidates += $found.FullName }
    }

    foreach ($cmd in $candidates) {
        try {
            $output = & $cmd --version 2>&1
            if ($output -match 'Python\s+(\d+)\.(\d+)') {
                $major = [int]$Matches[1]
                $minor = [int]$Matches[2]
                if ($major -ge $PythonMinMajor -and $minor -ge $PythonMinMinor) {
                    # Return the full path if possible
                    $resolved = (Get-Command $cmd -ErrorAction SilentlyContinue).Source
                    if ($resolved) { return $resolved }
                    return $cmd
                }
            }
        } catch { }
    }

    # Try py launcher
    try {
        $output = & py -3 --version 2>&1
        if ($output -match 'Python\s+(\d+)\.(\d+)') {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if ($major -ge $PythonMinMajor -and $minor -ge $PythonMinMinor) {
                return "py -3"
            }
        }
    } catch { }

    return $null
}

$PythonExe = Find-Python

if ($PythonExe) {
    $pyVer = & $PythonExe --version 2>&1
    Write-OK "Found $pyVer"
    Write-Info "Path: $PythonExe"
} else {
    Write-Warn "Python $PythonMinMajor.$PythonMinMinor+ not found."
    Write-Step "Attempting to install Python via winget..."

    $wingetAvailable = $false
    try {
        $null = Get-Command winget -ErrorAction Stop
        $wingetAvailable = $true
    } catch { }

    if ($wingetAvailable) {
        try {
            & winget install Python.Python.3.12 `
                --accept-source-agreements `
                --accept-package-agreements `
                --silent 2>&1 | Out-Null

            # Refresh PATH
            $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                        [System.Environment]::GetEnvironmentVariable("Path", "User")

            Start-Sleep -Seconds 2
            $PythonExe = Find-Python

            if ($PythonExe) {
                $pyVer = & $PythonExe --version 2>&1
                Write-OK "Installed $pyVer via winget."
            } else {
                Write-Err "Python was installed but could not be found on PATH."
                Write-Err "Please close and reopen PowerShell, then run this installer again."
                exit 1
            }
        } catch {
            Write-Err "Failed to install Python via winget: $_"
            Write-Err "Please install Python manually from https://www.python.org/downloads/"
            Write-Err "Make sure to check 'Add Python to PATH' during installation."
            exit 1
        }
    } else {
        Write-Err "Neither Python nor winget are available."
        Write-Host ""
        Write-Host "  Please install Python $PythonMinMajor.$PythonMinMinor+ manually:" -ForegroundColor Yellow
        Write-Host "  https://www.python.org/downloads/" -ForegroundColor White
        Write-Host ""
        Write-Host "  IMPORTANT: Check 'Add Python to PATH' during installation." -ForegroundColor Yellow
        Write-Host "  Then re-run this installer." -ForegroundColor Yellow
        Write-Host ""
        exit 1
    }
}

# ===================================================================
# STEP 2: Create Virtual Environment
# ===================================================================
Write-Section "Step 2: Virtual Environment"

if (Test-Path $VenvPath) {
    Write-OK "Virtual environment already exists."
    Write-Info "Path: $VenvPath"

    # Verify it's functional
    $venvPython = Join-Path $VenvPath "Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        Write-Warn "Venv appears broken. Recreating..."
        Remove-Item -Path $VenvPath -Recurse -Force
    }
}

if (-not (Test-Path $VenvPath)) {
    Write-Step "Creating virtual environment..."

    & $PythonExe -m venv $VenvPath 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        # Fallback: try with --without-pip then bootstrap pip
        Write-Warn "Standard venv creation failed. Trying fallback..."
        & $PythonExe -m venv --without-pip $VenvPath 2>&1 | Out-Null
    }

    if (Test-Path (Join-Path $VenvPath "Scripts\python.exe")) {
        Write-OK "Virtual environment created."
    } else {
        Write-Err "Failed to create virtual environment."
        Write-Err "Try running: $PythonExe -m venv $VenvPath"
        exit 1
    }
}

$VenvPython  = Join-Path $VenvPath "Scripts\python.exe"
$VenvPythonW = Join-Path $VenvPath "Scripts\pythonw.exe"
$VenvPip     = Join-Path $VenvPath "Scripts\pip.exe"

# Ensure pip is available in the venv
if (-not (Test-Path $VenvPip)) {
    Write-Step "Bootstrapping pip in virtual environment..."
    & $VenvPython -m ensurepip --upgrade 2>&1 | Out-Null
}

# ===================================================================
# STEP 3: Install Dependencies
# ===================================================================
Write-Section "Step 3: Dependencies"

Write-Step "Upgrading pip..."
& $VenvPython -m pip install --upgrade pip --quiet 2>&1 | Out-Null

foreach ($mod in $RequiredModules) {
    Write-Step "Installing $mod..."
    & $VenvPython -m pip install $mod --quiet 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to install $mod"
        exit 1
    }
    Write-OK "$mod installed."
}

# Verify imports
Write-Step "Verifying imports..."
$verifyScript = @"
import sys
try:
    import PyQt5.QtWidgets
    import PyQt5.QtGui
    import PyQt5.QtCore
    import PyQt5.QtPrintSupport
    import PIL
    print("ALL_OK")
except ImportError as e:
    print(f"IMPORT_FAIL:{e}")
    sys.exit(1)
"@

$result = & $VenvPython -c $verifyScript 2>&1
if ($result -match "ALL_OK") {
    Write-OK "All dependencies verified."
} else {
    Write-Err "Dependency verification failed: $result"
    exit 1
}

# ===================================================================
# STEP 4: Application Icon (embedded - no dependencies required)
# ===================================================================
Write-Section "Step 4: Application Icon"

if (Test-Path $IconPath) {
    Write-OK "Icon already exists: $IconName"
} else {
    Write-Step "Extracting embedded application icon..."

    # Multi-size ICO (16/24/32/48/64/128/256) embedded as base64.
    # Catppuccin Mocha themed camera icon - blue rounded rect + dark camera body.
    $iconB64 = "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"

    try {
        $iconBytes = [System.Convert]::FromBase64String($iconB64)
        [System.IO.File]::WriteAllBytes($IconPath, $iconBytes)
        Write-OK "Icon extracted: $IconName ($($iconBytes.Length) bytes, 7 sizes)"
    } catch {
        Write-Warn "Could not extract icon: $_"
        Write-Info "Shortcuts will use default icon."
    }
}

# ===================================================================
# STEP 5: Create Launcher
# ===================================================================
Write-Section "Step 5: Launcher"

# Determine pythonw.exe path (no console window)
$launcherExe = $VenvPythonW
if (-not (Test-Path $launcherExe)) {
    $launcherExe = $VenvPython
    Write-Warn "pythonw.exe not found, launcher will show a brief console flash."
}

# Create .cmd launcher
$launcherContent = @"
@echo off
REM ============================================
REM  SwiftShot Launcher
REM  Auto-generated by Install-SwiftShot.ps1
REM ============================================
cd /d "%~dp0"
start "" "$launcherExe" "%~dp0main.py" %*
"@

Set-Content -Path $LauncherPath -Value $launcherContent -Encoding ASCII
Write-OK "Launcher created: $LauncherName"

# Also create a VBS launcher for truly silent startup (no console flash at all)
$vbsLauncherPath = Join-Path $InstallDir "SwiftShot.vbs"
$vbsContent = @"
' SwiftShot Silent Launcher - No console window at all
' Auto-generated by Install-SwiftShot.ps1
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "$($InstallDir.Replace('\','\\'))"
WshShell.Run """$($launcherExe.Replace('\','\\'))"" ""$($MainScript.Replace('\','\\'))""", 0, False
Set WshShell = Nothing
"@

Set-Content -Path $vbsLauncherPath -Value $vbsContent -Encoding ASCII
Write-OK "Silent launcher created: SwiftShot.vbs"

# ===================================================================
# STEP 6: Create Shortcuts
# ===================================================================

if (-not $NoShortcuts) {
    Write-Section "Step 6: Shortcuts"

    function New-Shortcut {
        param(
            [string]$ShortcutPath,
            [string]$TargetPath,
            [string]$Arguments = "",
            [string]$WorkingDir = "",
            [string]$IconLocation = "",
            [string]$Description = ""
        )

        try {
            $shell = New-Object -ComObject WScript.Shell
            $shortcut = $shell.CreateShortcut($ShortcutPath)
            $shortcut.TargetPath = $TargetPath

            if ($Arguments) { $shortcut.Arguments = $Arguments }
            if ($WorkingDir) { $shortcut.WorkingDirectory = $WorkingDir }
            if ($Description) { $shortcut.Description = $Description }
            if ($IconLocation -and (Test-Path $IconLocation)) {
                $shortcut.IconLocation = "$IconLocation,0"
            }

            $shortcut.WindowStyle = 7  # Minimized (hidden for vbs)
            $shortcut.Save()
            [System.Runtime.InteropServices.Marshal]::ReleaseComObject($shell) | Out-Null
            return $true
        } catch {
            Write-Warn "Could not create shortcut: $ShortcutPath ($_)"
            return $false
        }
    }

    # Use the VBS launcher as the shortcut target for zero console flash
    $shortcutTarget = $vbsLauncherPath
    $shortcutTargetExe = "wscript.exe"

    # Desktop shortcut
    $desktopLnk = Join-Path $DesktopDir "$AppName.lnk"
    Write-Step "Creating Desktop shortcut..."
    $created = New-Shortcut `
        -ShortcutPath $desktopLnk `
        -TargetPath $shortcutTargetExe `
        -Arguments """$vbsLauncherPath""" `
        -WorkingDir $InstallDir `
        -IconLocation $IconPath `
        -Description "$AppName - Screenshot Tool"

    if ($created) {
        Write-OK "Desktop shortcut created."
    }

    # Start Menu shortcut
    Write-Step "Creating Start Menu entry..."
    if (-not (Test-Path $StartMenuDir)) {
        New-Item -Path $StartMenuDir -ItemType Directory -Force | Out-Null
    }

    $startMenuLnk = Join-Path $StartMenuDir "$AppName.lnk"
    $created = New-Shortcut `
        -ShortcutPath $startMenuLnk `
        -TargetPath $shortcutTargetExe `
        -Arguments """$vbsLauncherPath""" `
        -WorkingDir $InstallDir `
        -IconLocation $IconPath `
        -Description "$AppName - Screenshot Tool"

    if ($created) {
        Write-OK "Start Menu shortcut created."
    }

    # Uninstall shortcut in Start Menu
    $uninstallLnk = Join-Path $StartMenuDir "Uninstall $AppName.lnk"
    $created = New-Shortcut `
        -ShortcutPath $uninstallLnk `
        -TargetPath "powershell.exe" `
        -Arguments "-ExecutionPolicy Bypass -File ""$(Join-Path $InstallDir 'Install-SwiftShot.ps1')"" -Uninstall" `
        -WorkingDir $InstallDir `
        -IconLocation "" `
        -Description "Uninstall $AppName"

    if ($created) {
        Write-OK "Uninstall shortcut created in Start Menu."
    }
}

# ===================================================================
# STEP 7: Startup Entry (Optional)
# ===================================================================

if ($AddToStartup) {
    Write-Section "Step 7: Windows Startup"

    $startupLnk = Join-Path $StartupDir "$AppName.lnk"
    Write-Step "Adding to Windows Startup..."

    $created = New-Shortcut `
        -ShortcutPath $startupLnk `
        -TargetPath "wscript.exe" `
        -Arguments """$vbsLauncherPath""" `
        -WorkingDir $InstallDir `
        -IconLocation $IconPath `
        -Description "$AppName - Start on Login"

    if ($created) {
        Write-OK "$AppName will start automatically on login."
    }
} else {
    Write-Host ""
    Write-Info "TIP: To auto-start on login, re-run with -AddToStartup"
}

# ===================================================================
# Summary
# ===================================================================

Write-Host ""
Write-Host "  =============================================" -ForegroundColor Green
Write-Host "   INSTALLATION COMPLETE" -ForegroundColor Green
Write-Host "  =============================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Install Location:  $InstallDir" -ForegroundColor White
Write-Host "  Python Venv:       $VenvPath" -ForegroundColor DarkGray
Write-Host "  Launcher:          $LauncherPath" -ForegroundColor White
Write-Host "  Silent Launcher:   $vbsLauncherPath" -ForegroundColor DarkGray

if (Test-Path $IconPath) {
    Write-Host "  Icon:              $IconPath" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "  HOW TO LAUNCH:" -ForegroundColor Cyan
Write-Host "    - Double-click the '$AppName' shortcut on your Desktop" -ForegroundColor White
Write-Host "    - Or run: $LauncherPath" -ForegroundColor DarkGray
Write-Host "    - Or search '$AppName' in the Start Menu" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  HOW TO UNINSTALL:" -ForegroundColor DarkCyan
Write-Host "    .\Install-SwiftShot.ps1 -Uninstall" -ForegroundColor DarkGray
Write-Host "    Or use the Uninstall shortcut in the Start Menu." -ForegroundColor DarkGray
Write-Host ""

# ===================================================================
# Offer to Launch Now
# ===================================================================

$response = Read-Host "  Launch $AppName now? (Y/n)"
if ($response -ne 'n' -and $response -ne 'N') {
    Write-Step "Launching $AppName..."
    Start-Process "wscript.exe" -ArgumentList """$vbsLauncherPath""" -WorkingDirectory $InstallDir
    Write-OK "$AppName is running in the system tray."
}

Write-Host ""
