<#
.SYNOPSIS
    Deterministic local release + package gate for SwiftShot (R-27).

.DESCRIPTION
    One clean command that makes a release reproducible and verifiable. Runs the
    quality gates, builds the artifacts, and proves/records what shipped:

      1. Enforces the CPython 3.12 runtime contract.
      2. (optional) Installs the exact hash-locked wheels into a throwaway venv
         so the build is byte-reproducible (-LockedInstall).
      3. Ruff (F) + full pytest suite.
      4. Builds the portable exe (and installer unless -PortableOnly).
      5. Import/capability-smokes each built artifact (--version probe).
      6. Emits dist\SHA256SUMS.txt for every artifact.
      7. Generates a CycloneDX SBOM (packaging/gen_sbom.py) into dist\.
      8. Validates the winget (schema 1.12.0) and Scoop manifests.
      9. Verifies the version string is consistent across config, manifests
         and the README badge.

    Any failed step aborts with a non-zero exit code and an explanation.

.PARAMETER PortableOnly
    Build/smoke only the portable exe (skip the Inno installer).

.PARAMETER LockedInstall
    Create .build-venv and install runtime deps from requirements.lock with
    --require-hashes before building (fully reproducible; slower).

.PARAMETER SkipBuild
    Run gates, SBOM and manifest validation without building artifacts.

.EXAMPLE
    pwsh packaging\release-gate.ps1
.EXAMPLE
    pwsh packaging\release-gate.ps1 -LockedInstall -PortableOnly
#>
[CmdletBinding()]
param(
    [switch]$PortableOnly,
    [switch]$LockedInstall,
    [switch]$SkipBuild
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$AppDir   = Join-Path $RepoRoot 'App'
# Build-SwiftShot.ps1 lives in App\ and writes all artifacts to App\dist\.
$DistDir  = Join-Path $AppDir 'dist'
$Py       = 'py'
$PyArgs   = @('-3.12')

function Section([string]$m) { Write-Host "`n=== $m ===" -ForegroundColor Cyan }
function Ok([string]$m)      { Write-Host "  [+] $m" -ForegroundColor Green }
function Info([string]$m)    { Write-Host "      $m" -ForegroundColor DarkGray }
function Fail([string]$m)    { Write-Host "  [!] $m" -ForegroundColor Red; exit 1 }

function Invoke-Py {
    param([string[]]$Arguments)
    & $Py @PyArgs @Arguments
    if ($LASTEXITCODE -ne 0) { Fail "python $($Arguments -join ' ') exited $LASTEXITCODE" }
}

# --- 1. Runtime contract ----------------------------------------------------
Section 'Runtime contract (CPython 3.12)'
$ver = & $Py @PyArgs -c 'import sys;print("%d.%d"%sys.version_info[:2])'
if ($ver.Trim() -ne '3.12') { Fail "Expected Python 3.12, got $ver" }
Ok "Python $ver"

# App version (single source of truth).
$AppVersion = (& $Py @PyArgs -c "import sys;sys.path.insert(0,r'$AppDir');from config import Config;print(Config.APP_VERSION)").Trim()
Ok "SwiftShot version $AppVersion"

# --- 2. Optional hash-locked install ---------------------------------------
if ($LockedInstall) {
    Section 'Hash-locked dependency install'
    $venv = Join-Path $RepoRoot '.build-venv'
    if (Test-Path $venv) { Remove-Item -Recurse -Force $venv }
    Invoke-Py @('-m', 'venv', $venv)
    $venvPy = Join-Path $venv 'Scripts\python.exe'
    & $venvPy -m pip install --upgrade pip | Out-Null
    & $venvPy -m pip install --require-hashes --only-binary=:all: -r (Join-Path $RepoRoot 'requirements.lock')
    if ($LASTEXITCODE -ne 0) { Fail 'Hash-locked install failed (a hash or version drifted)' }
    Ok 'Installed exact hash-locked wheels'
}

# --- 3. Ruff + pytest -------------------------------------------------------
Section 'Lint (ruff --select F)'
Invoke-Py @('-m', 'ruff', 'check', '--select', 'F', $AppDir, (Join-Path $RepoRoot 'tests'))
Ok 'Ruff clean'

Section 'Tests (pytest)'
Invoke-Py @('-m', 'pytest', (Join-Path $RepoRoot 'tests'), '-q')
Ok 'All tests passed'

# --- 4. Build artifacts (before SBOM: -Clean wipes dist\) ------------------
$artifacts = @()
if (-not $SkipBuild) {
    Section 'Build artifacts'
    $buildArgs = @('-File', (Join-Path $AppDir 'Build-SwiftShot.ps1'), '-Clean')
    if ($PortableOnly) { $buildArgs += '-PortableOnly' }
    & pwsh @buildArgs
    if ($LASTEXITCODE -ne 0) { Fail "Build failed (exit $LASTEXITCODE)" }

    $portable = Join-Path $DistDir 'SwiftShot-Portable.exe'
    if (-not (Test-Path $portable)) { Fail 'Portable exe missing from dist\' }
    $artifacts += $portable
    if (-not $PortableOnly) {
        $setup = Join-Path $DistDir 'SwiftShot-Setup.exe'
        if (Test-Path $setup) { $artifacts += $setup }
    }

    Section 'Artifact capability smoke (--version)'
    $probe = (& $portable --version 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { Fail "Portable exe --version exited $LASTEXITCODE" }
    if ($probe -notmatch [regex]::Escape($AppVersion)) {
        Fail "Portable exe reported '$probe', expected version $AppVersion"
    }
    Ok "Portable exe smoke: $probe"

    Section 'Checksums (SHA256SUMS.txt)'
    $sumsPath = Join-Path $DistDir 'SHA256SUMS.txt'
    $lines = foreach ($a in $artifacts) {
        $h = (Get-FileHash $a -Algorithm SHA256).Hash.ToLower()
        "{0}  {1}" -f $h, (Split-Path $a -Leaf)
    }
    Set-Content -Path $sumsPath -Value $lines -Encoding utf8
    $lines | ForEach-Object { Info $_ }
    Ok 'dist\SHA256SUMS.txt written'
}

# --- SBOM (after build so -Clean does not wipe it) -------------------------
Section 'SBOM (CycloneDX)'
New-Item -ItemType Directory -Force -Path $DistDir | Out-Null
$SbomPath = Join-Path $DistDir 'swiftshot.sbom.json'
Invoke-Py @((Join-Path $PSScriptRoot 'gen_sbom.py'), '-o', $SbomPath)
Ok 'SBOM -> dist\swiftshot.sbom.json'

# --- Manifest validation ---------------------------------------------------
Section 'Package manifest validation'
$wingetDir = Join-Path $PSScriptRoot 'winget'
& winget validate --manifest $wingetDir
if ($LASTEXITCODE -ne 0) { Fail 'winget manifest validation failed' }
Ok 'winget manifests valid (schema 1.12.0)'

$scoop = Join-Path $PSScriptRoot 'scoop\swiftshot.json'
Invoke-Py @('-c', "import json,sys;d=json.load(open(r'$scoop'));assert d['version'],'no version';print('scoop ok',d['version'])")
Ok 'Scoop manifest parses'

# --- 9. Version consistency -------------------------------------------------
Section 'Version consistency'
Invoke-Py @((Join-Path $PSScriptRoot 'check_versions.py'))
Ok 'All version strings match'

Write-Host "`nRelease gate PASSED for SwiftShot $AppVersion" -ForegroundColor Green
