<#
.SYNOPSIS
    Build kit-fvaa as a standalone / onefile Windows executable with Nuitka.

.DESCRIPTION
    Requires: uv (project env), MSVC C compiler (VS 2022 Build Tools w/ VC++ workload) or gcc.
    Output goes to dist/. Never committed to git.

.PARAMETER Mode
    standalone = directory distribution (validation target, fastest startup)
    onefile    = single EXE distribution
    all        = build standalone first, then onefile (default)

.PARAMETER Verify
    After each build, launch the EXE and wait for its main window to appear,
    keep it alive a few seconds, then kill it. Reports PASS/FAIL.

.PARAMETER Jobs
    Parallel C compilation jobs (0 = let Nuitka decide).

.EXAMPLE
    pwsh -File scripts\build_windows_onefile.ps1
    pwsh -File scripts\build_windows_onefile.ps1 -Mode standalone -Verify
#>
[CmdletBinding()]
param(
    [ValidateSet('standalone', 'onefile', 'all')]
    [string]$Mode = 'all',
    [switch]$Verify,
    [int]$Jobs = 0
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$DistDir     = Join-Path $ProjectRoot 'dist'
$ExeName     = 'kit-fvaa.exe'
$EntryModule = 'main.py'
# Prefix of the GUI window title; used only for the -Verify smoke test.
$WindowTitlePrefix = 'Kit'

# ---------------------------------------------------------------------------
# 0. Tool checks: uv + a C compiler (Nuitka requirement, reported honestly).
# ---------------------------------------------------------------------------
$uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uv) { throw 'uv not found in PATH. Install: winget install astral-sh.uv' }

$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$msvcPath = $null
if (Test-Path $vswhere) {
    $msvcPath = & $vswhere -products * -latest `
        -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 `
        -property installationPath | Select-Object -First 1
}
$gcc = Get-Command gcc.exe -ErrorAction SilentlyContinue
if (-not $msvcPath -and -not $gcc) {
    throw @'
No C compiler found. Nuitka needs one of:
  1) MSVC: winget install Microsoft.VisualStudio.2022.BuildTools
     then add workload "Desktop development with C++" (VC++ x86/x64 build tools), or
  2) gcc via MinGW-w64: winget install MartinStorsjo.LLVM-MinGW
Re-run this script after installing.
'@
}
if ($msvcPath) { Write-Host "[ok] MSVC toolchain found: $msvcPath" }
else           { Write-Host "[ok] gcc found: $($gcc.Source)" }

# ---------------------------------------------------------------------------
# 1. Sync project environment (also installs the dev group: nuitka, zstandard).
# ---------------------------------------------------------------------------
Write-Host '==> uv sync'
& uv sync
if ($LASTEXITCODE -ne 0) { throw 'uv sync failed.' }

# ---------------------------------------------------------------------------
# 2. Locate ttkbootstrap package inside the uv venv (for data-file includes).
# ---------------------------------------------------------------------------
$ttkPkg = (& uv run python -c "import ttkbootstrap, os; print(os.path.dirname(ttkbootstrap.__file__))").Trim()
if (-not $ttkPkg -or -not (Test-Path $ttkPkg)) { throw "ttkbootstrap package dir not found: '$ttkPkg'" }
Write-Host "[ok] ttkbootstrap at: $ttkPkg"

# ---------------------------------------------------------------------------
# 3. Common Nuitka arguments.
#    Data files are included per-file (no bulk directory copies):
#      - elements/manifest.json + *.png : required by the Checkbutton
#        bootstyle "info-round-toggle" (Assets.recolor('switch_round', ...))
#      - icons/bootstrap.ttf + glyphmap.json + icon_metrics.json : required
#        by the default theme build itself (ttkbootstrap combobox style
#        renders its arrow via Icon.render -> bootstrap.ttf)
#      - app_icons/ttkbootstrap.ico     : window icon on win32 (ttkbootstrap.window)
#    Everything else (app_icons/ttkbootstrap.png fallback for macOS/Linux,
#    README/LICENSE files, requests* - note: requests IS imported statically
#    by tkhtmlview.html_parser and must stay) is not needed and stays out.
# ---------------------------------------------------------------------------
$commonArgs = @(
    '--enable-plugin=anti-bloat',
    '--enable-plugin=tk-inter',                 # bundle tcl/tk runtime (required since Nuitka 4.x)
    '--windows-console-mode=disable',           # GUI app: no console window
    '--output-dir=dist',
    "--output-filename=$ExeName",
    '--noinclude-pytest-mode=error',            # hard-fail the build if ever imported
    '--noinclude-setuptools-mode=error',
    '--noinclude-unittest-mode=error',
    '--noinclude-pydoc-mode=error',
    "--include-data-files=$ttkPkg/assets/elements/manifest.json=ttkbootstrap/assets/elements/manifest.json",
    "--include-data-files=$ttkPkg/assets/elements/*.png=ttkbootstrap/assets/elements/",
    "--include-data-files=$ttkPkg/assets/icons/bootstrap.ttf=ttkbootstrap/assets/icons/bootstrap.ttf",
    "--include-data-files=$ttkPkg/assets/icons/glyphmap.json=ttkbootstrap/assets/icons/glyphmap.json",
    "--include-data-files=$ttkPkg/assets/icons/icon_metrics.json=ttkbootstrap/assets/icons/icon_metrics.json",
    "--include-data-files=$ttkPkg/assets/app_icons/ttkbootstrap.ico=ttkbootstrap/assets/app_icons/ttkbootstrap.ico"
)
if ($Jobs -gt 0) { $commonArgs += "--jobs=$Jobs" }

function Invoke-NuitkaBuild {
    param([string]$BuildMode)
    $report = "dist/nuitka-report-$BuildMode.xml"
    Write-Host "==> uv run python -m nuitka main.py --mode=$BuildMode (report: $report)"
    & uv run python -m nuitka $EntryModule "--mode=$BuildMode" $commonArgs "--report=$report"
    if ($LASTEXITCODE -ne 0) { throw "Nuitka $BuildMode build failed (exit $LASTEXITCODE)." }
}

function Get-BuiltExe {
    param([string]$BuildMode)
    if ($BuildMode -eq 'onefile') { return Join-Path $DistDir $ExeName }
    return Join-Path $DistDir 'main.dist' | Join-Path -ChildPath $ExeName
}

function Test-BuiltExe {
    param([string]$ExePath, [string]$BuildMode)
    if (-not (Test-Path $ExePath)) { throw "Expected output not found: $ExePath" }
    $bytes = (Get-Item $ExePath).Length
    Write-Host ("[build:{0}] {1} ({2:N0} bytes)" -f $BuildMode, $ExePath, $bytes)

    if (-not $Verify) { return }

    Write-Host "==> smoke test: launching $ExePath"
    $proc = Start-Process -FilePath $ExePath -WorkingDirectory $DistDir -PassThru
    # NOTE: for onefile builds the window belongs to the extracted CHILD process,
    # not to the bootstrap process we started, so poll all processes for a
    # window whose title starts with the app title prefix.
    $deadline = (Get-Date).AddSeconds(45)
    $win = $null
    try {
        while ((Get-Date) -lt $deadline) {
            Start-Sleep -Milliseconds 500
            if ($proc.HasExited -and -not $win) { break }
            $win = Get-Process -Name ([IO.Path]::GetFileNameWithoutExtension($ExeName)) -ErrorAction SilentlyContinue |
                Where-Object { $_.MainWindowTitle -and $_.MainWindowTitle.StartsWith($WindowTitlePrefix) } |
                Select-Object -First 1
            if ($win) { break }
        }
        if (-not $win) {
            if ($proc.HasExited) {
                throw "Bootstrap process exited early with code $($proc.ExitCode) (no window appeared)."
            }
            throw "Window starting with '$WindowTitlePrefix' not detected within 45s."
        }
        Write-Host ("[verify:{0}] window detected: '{1}' (pid {2}) - keeping alive 5s..." -f $BuildMode, $win.MainWindowTitle, $win.Id)
        Start-Sleep -Seconds 5
        $win.Refresh()
        if ($win.HasExited) { throw 'Process exited on its own during the 5s hold.' }
        Write-Host ("[verify:{0}] PASS" -f $BuildMode)
    }
    finally {
        foreach ($p in @($win, $proc)) {
            if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
        }
        Write-Host '    (test process stopped)'
    }
}

# ---------------------------------------------------------------------------
# 4. Clean previous artifacts, then build.
# ---------------------------------------------------------------------------
if (Test-Path $DistDir) {
    Write-Host '==> cleaning dist/'
    Remove-Item $DistDir -Recurse -Force
}
New-Item -ItemType Directory -Path $DistDir | Out-Null

$modes = if ($Mode -eq 'all') { @('standalone', 'onefile') } else { @($Mode) }
foreach ($m in $modes) {
    Invoke-NuitkaBuild -BuildMode $m
    Test-BuiltExe -ExePath (Get-BuiltExe -BuildMode $m) -BuildMode $m
}

Write-Host '==> done. Artifacts:'
Get-ChildItem $DistDir | ForEach-Object {
    if ($_.PSIsContainer) {
        $size = (Get-ChildItem $_.FullName -Recurse -File | Measure-Object Length -Sum).Sum
        Write-Host ("    {0}/  ({1:N0} bytes)" -f $_.Name, $size)
    } else {
        Write-Host ("    {0}  ({1:N0} bytes)" -f $_.Name, $_.Length)
    }
}
