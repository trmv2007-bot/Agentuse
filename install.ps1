# ═══════════════════════════════════════════════════════════════
#  AGENTUSE — one-shot installer for Windows (PowerShell)
#
#    git clone https://github.com/trmv2007-bot/Agentuse.git; cd Agentuse; .\install.ps1
#    # or remote one-shot:
#    irm https://raw.githubusercontent.com/trmv2007-bot/Agentuse/main/install.ps1 | iex
#
#  Requires Python 3.10+. If `python` prints "Python was not found; run
#  without arguments to install from the Microsoft Store…", that is Windows'
#  App Execution Alias stub, not Python — this installer detects it and tells
#  you exactly what to do.
# ═══════════════════════════════════════════════════════════════
$ErrorActionPreference = "Stop"
$RepoUrl = "https://github.com/trmv2007-bot/Agentuse.git"

function Say($m)  { Write-Host "[AGENTUSE] $m" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "  OK  $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  !   $m" -ForegroundColor Yellow }
function Die($m)  { Write-Host "  !!  $m" -ForegroundColor Red; exit 1 }

# -- run a native exe without letting its stderr kill the script ---------
# Windows PowerShell 5.1 converts a native command's stderr into a
# *terminating* error while $ErrorActionPreference is "Stop"
# (FullyQualifiedErrorId: NativeCommandError). That used to abort this
# installer mid-probe, before it could try the `py` launcher or print a
# useful message. Every external call therefore goes through here.
function Invoke-Native {
    param([Parameter(Mandatory = $true)][string[]]$Command)
    $exe  = $Command[0]
    $rest = @()
    if ($Command.Count -gt 1) { $rest = $Command[1..($Command.Count - 1)] }
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $text = (& $exe @rest 2>&1 | ForEach-Object { "$_" } | Out-String)
        $code = $LASTEXITCODE
    } catch {
        $text = ("$_" | Out-String)
        $code = 1
    } finally {
        $ErrorActionPreference = $prev
    }
    [pscustomobject]@{ Code = $code; Output = "$text".Trim() }
}

# ---- 1. locate the repo ----
if (-not (Test-Path "run.py")) {
    Say "not inside the repo — cloning…"
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Die "git is required — https://git-scm.com/download/win"
    }
    $target = Join-Path $env:USERPROFILE "Agentuse"
    if (Test-Path (Join-Path $target ".git")) {
        Ok "already cloned at $target"
    } else {
        $r = Invoke-Native -Command @("git", "clone", "--depth", "1", $RepoUrl, $target)
        if ($r.Code -ne 0) { Die "clone failed:`n$($r.Output)" }
    }
    Set-Location $target
}
Ok "repo: $(Get-Location)"

# ---- 2. find Python 3.10+ ----
# Candidates must be *executed*, not merely found: Windows ships a 0-byte
# Microsoft Store "App Execution Alias" at
#   %LOCALAPPDATA%\Microsoft\WindowsApps\python.exe
# which answers `Get-Command python` but only prints "Python was not found…"
# and exits non-zero. Presence checks pass; execution does not.
#
# NB: the probe must stay free of double quotes — Windows PowerShell 5.1 does
# not escape embedded " when handing arguments to a native exe. chr(46) is ".".
$Probe = 'import sys;print(*sys.version_info[:3],sep=chr(46));raise SystemExit(0 if sys.version_info>=(3,10) else 1)'

function Resolve-PythonExe([string]$Name) {
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $cmd -or -not $cmd.Source) { return $null }
    $path = $cmd.Source
    # Alias stubs sit *directly* in WindowsApps; a genuine Store Python lives
    # one level deeper, inside PythonSoftwareFoundation.Python.* — keep those.
    if ($path -match '\\WindowsApps\\[^\\]+$') { return $null }
    try {
        if ((Get-Item -LiteralPath $path -Force -ErrorAction Stop).Length -eq 0) { return $null }
    } catch { }
    return $path
}

# Runs one candidate. Returns @{ Version = "3.12.7"; Note = "" } when it is a
# working Python 3.10+, otherwise @{ Version = $null; Note = <why it failed> }.
function Test-Python([string[]]$Invoke) {
    $r = Invoke-Native -Command ($Invoke + @("-c", $Probe))
    $lines = @("$($r.Output)" -split "`r?`n")
    if ($r.Code -eq 0) {
        return @{ Version = "$($lines[-1])".Trim(); Note = "" }
    }
    $why = ""
    if ($lines.Count -gt 0) { $why = "$($lines[0])".Trim() }
    return @{ Version = $null; Note = $why }
}

$candidates = @()

# 2a. the py launcher — most reliable on Windows, ignores the Store stub
if (Get-Command py -ErrorAction SilentlyContinue) { $candidates += , @("py", "-3") }

# 2b. python / python3 on PATH (stub-filtered)
foreach ($name in @("python", "python3")) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if (-not $cmd) { continue }
    $exe = Resolve-PythonExe $name
    if (-not $exe) { Warn "ignoring Microsoft Store stub for '$name' ($($cmd.Source))"; continue }
    $candidates += , @($exe)
}

# 2c. well-known install folders, for when nothing is on PATH at all
$patterns = @("C:\Python3*\python.exe")
if ($env:LOCALAPPDATA) {
    $patterns += "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe"
    $patterns += "$env:LOCALAPPDATA\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.*\python.exe"
}
if ($env:ProgramFiles) { $patterns += "$env:ProgramFiles\Python3*\python.exe" }
$pf86 = [System.Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
if ($pf86) { $patterns += "$pf86\Python3*\python.exe" }
foreach ($pat in $patterns) {
    $hits = @(Get-ChildItem -Path $pat -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName)
    foreach ($h in $hits) { $candidates += , @($h) }
}

$pyInvoke = $null
$pyver = $null
$tried = @()
$failures = @()
foreach ($cand in $candidates) {
    $label = ($cand -join " ")
    if ($tried -contains $label) { continue }
    $tried += $label
    $res = Test-Python -Invoke $cand
    if ($res.Version) { $pyInvoke = $cand; $pyver = $res.Version; break }
    $failures += ("{0}  ->  {1}" -f $label, $res.Note)
}

if (-not $pyInvoke) {
    Write-Host ""
    Write-Host "  !!  Python 3.10+ not found." -ForegroundColor Red
    if ($failures.Count -gt 0) {
        Write-Host "      Looked at:" -ForegroundColor Red
        foreach ($f in $failures) { Write-Host "        $f" -ForegroundColor DarkGray }
    }
    Write-Host ""
    Write-Host "      Install Python from https://www.python.org/downloads/ and TICK" -ForegroundColor Yellow
    Write-Host "      'Add python.exe to PATH' — or, from this same terminal:" -ForegroundColor Yellow
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host ""
        Write-Host "          winget install -e --id Python.Python.3.12" -ForegroundColor White
    }
    Write-Host ""
    Write-Host "      Already installed but still failing? Windows' Microsoft Store" -ForegroundColor Yellow
    Write-Host "      shortcut is shadowing it. Turn it off:" -ForegroundColor Yellow
    Write-Host "          Settings -> Apps -> Advanced app settings -> App execution aliases" -ForegroundColor White
    Write-Host "          -> switch OFF  python.exe  and  python3.exe" -ForegroundColor White
    Write-Host "      then open a NEW terminal and run this installer again." -ForegroundColor Yellow
    Write-Host ""
    exit 1
}
Ok "python: Python $pyver  ($($pyInvoke -join ' '))"

# ---- 3. venv + dependencies ----
if (-not (Test-Path ".venv")) {
    Say "creating virtual environment…"
    $r = Invoke-Native -Command ($pyInvoke + @("-m", "venv", ".venv"))
    if ($r.Code -ne 0) { Die "venv creation failed:`n$($r.Output)" }
}
$vpy = Join-Path (Get-Location) ".venv\Scripts\python.exe"
if (-not (Test-Path $vpy)) { Die "venv python missing — delete .venv and rerun" }
Say "installing dependencies (fastapi, uvicorn, httpx, bs4, lxml)…"
$null = Invoke-Native -Command @($vpy, "-m", "pip", "install", "-q", "--upgrade", "pip")
$r = Invoke-Native -Command @($vpy, "-m", "pip", "install", "-q", "-r", "requirements.txt")
if ($r.Code -ne 0) { Die "dependency install failed:`n$($r.Output)" }
Ok "dependencies installed"

# ---- 4. boot ----
Write-Host ""
Write-Host "  ====================================================" -ForegroundColor Cyan
Write-Host "    A G E N T U S E  —  GRID COMING ONLINE" -ForegroundColor Cyan
Write-Host "    SpaceGrid :  http://localhost:8000" -ForegroundColor Cyan
Write-Host "    Ctrl+C to take the grid offline" -ForegroundColor Cyan
Write-Host "  ====================================================" -ForegroundColor Cyan
Write-Host ""
$ErrorActionPreference = "Continue"   # let the server log to stderr freely
& $vpy run.py
