# ═══════════════════════════════════════════════════════════════
#  AGENTUSE — one-shot installer for Windows (PowerShell)
#
#    git clone https://github.com/trmv2007-bot/Agentuse.git; cd Agentuse; .\install.ps1
#    # or remote one-shot:
#    irm https://raw.githubusercontent.com/trmv2007-bot/Agentuse/main/install.ps1 | iex
# ═══════════════════════════════════════════════════════════════
$ErrorActionPreference = "Stop"
$RepoUrl = "https://github.com/trmv2007-bot/Agentuse.git"

function Say($m)  { Write-Host "[AGENTUSE] $m" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "  OK  $m" -ForegroundColor Green }
function Die($m)  { Write-Host "  !!  $m" -ForegroundColor Red; exit 1 }

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
        git clone --depth 1 $RepoUrl $target
        if ($LASTEXITCODE -ne 0) { Die "clone failed" }
    }
    Set-Location $target
}
Ok "repo: $(Get-Location)"

# ---- 2. find Python 3.10+ ----
$py = $null
foreach ($c in @("python", "py")) {
    if (Get-Command $c -ErrorAction SilentlyContinue) {
        & $c -c "import sys; raise SystemExit(0 if sys.version_info>=(3,10) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) { $py = $c; break }
    }
}
if (-not $py) { Die "Python 3.10+ not found — https://www.python.org/downloads/ (tick 'Add to PATH')" }
$ver = & $py --version 2>&1
Ok "python: $ver"

# ---- 3. venv + dependencies ----
if (-not (Test-Path ".venv")) {
    Say "creating virtual environment…"
    & $py -m venv .venv
    if ($LASTEXITCODE -ne 0) { Die "venv creation failed" }
}
$vpy = Join-Path (Get-Location) ".venv\Scripts\python.exe"
if (-not (Test-Path $vpy)) { Die "venv python missing — delete .venv and rerun" }
Say "installing dependencies (fastapi, uvicorn, httpx, bs4, lxml)…"
& $vpy -m pip install -q --upgrade pip
& $vpy -m pip install -q -r requirements.txt
if ($LASTEXITCODE -ne 0) { Die "dependency install failed" }
Ok "dependencies installed"

# ---- 4. boot ----
Write-Host ""
Write-Host "  ====================================================" -ForegroundColor Cyan
Write-Host "    A G E N T U S E  —  GRID COMING ONLINE" -ForegroundColor Cyan
Write-Host "    SpaceGrid :  http://localhost:8000" -ForegroundColor Cyan
Write-Host "    Ctrl+C to take the grid offline" -ForegroundColor Cyan
Write-Host "  ====================================================" -ForegroundColor Cyan
Write-Host ""
& $vpy run.py
