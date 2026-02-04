#Requires -Version 5.1
<#
.SYNOPSIS
    SwiftShot Installer - One-click setup for SwiftShot screenshot tool.

.DESCRIPTION
    This installer will:
      1. Detect or install Python 3.8+ (via winget)
      2. Create an isolated virtual environment
      3. Install PyQt5 and Pillow into the venv
      4. Generate a program icon (.ico)
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
# STEP 4: Generate Application Icon
# ===================================================================
Write-Section "Step 4: Application Icon"

if (Test-Path $IconPath) {
    Write-OK "Icon already exists: $IconName"
} else {
    Write-Step "Generating application icon..."

    $iconScript = @"
import sys
try:
    from PIL import Image, ImageDraw, ImageFont
    sizes = [(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)]
    images = []
    for size in sizes:
        img = Image.new('RGBA', size, (0,0,0,0))
        draw = ImageDraw.Draw(img)
        w, h = size
        pad = max(1, w // 16)
        # Rounded rect background
        draw.rounded_rectangle([pad, pad, w-pad-1, h-pad-1],
                               radius=max(2, w//5),
                               fill=(137, 180, 250, 255))
        # Camera body
        bx1, by1 = int(w*0.18), int(h*0.28)
        bx2, by2 = int(w*0.82), int(h*0.75)
        draw.rounded_rectangle([bx1, by1, bx2, by2],
                               radius=max(1, w//12),
                               fill=(30, 30, 46, 255))
        # Lens circle
        cx, cy = w//2, int(h*0.48)
        lr = int(w*0.16)
        draw.ellipse([cx-lr, cy-lr, cx+lr, cy+lr], fill=(137, 180, 250, 255))
        # Inner lens
        ilr = max(1, lr//2)
        draw.ellipse([cx-ilr, cy-ilr, cx+ilr, cy+ilr], fill=(30, 30, 46, 255))
        # Flash
        fx = int(w*0.25)
        fy = int(h*0.32)
        fs = max(1, w//10)
        draw.rectangle([fx, fy, fx+fs, fy+max(1,fs//2)], fill=(249, 226, 175, 255))
        images.append(img)
    images[0].save(sys.argv[1], format='ICO', sizes=[(s[0],s[1]) for s in sizes],
                   append_images=images[1:])
    print("ICON_OK")
except Exception as e:
    print(f"ICON_FAIL:{e}")
"@

    $result = & $VenvPython -c $iconScript $IconPath 2>&1
    if ($result -match "ICON_OK") {
        Write-OK "Icon generated: $IconName"
    } else {
        Write-Warn "Could not generate icon: $result"
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
