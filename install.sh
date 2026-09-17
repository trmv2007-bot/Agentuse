#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  AGENTUSE — one-shot installer for Linux / macOS
#
#    bash install.sh                     (from the repo)
#    bash -c "$(curl -fsSL <raw-url>)"   (remote one-shot)
#
#  Finds Python 3.10+, creates an isolated .venv, installs deps,
#  boots the SpaceGrid on http://localhost:8000
# ═══════════════════════════════════════════════════════════════
set -u

REPO_URL="https://github.com/trmv2007-bot/Agentuse.git"
CYAN='\033[36m'; GREEN='\033[32m'; AMBER='\033[33m'; RED='\033[31m'; DIM='\033[2m'; OFF='\033[0m'

say()  { printf "${CYAN}[AGENTUSE]${OFF} %s\n" "$1"; }
ok()   { printf "${GREEN}  ✓${OFF} %s\n" "$1"; }
warn() { printf "${AMBER}  !${OFF} %s\n" "$1"; }
die()  { printf "${RED}  ✗ %s${OFF}\n" "$1"; exit 1; }

# ---- 1. locate the repo (clone if we're not inside it) ----
if [ ! -f "run.py" ]; then
    say "not inside the repo — cloning…"
    command -v git >/dev/null 2>&1 || die "git is required (install git, then rerun)"
    TARGET="${HOME}/Agentuse"
    [ -d "$TARGET/.git" ] && ok "already cloned at $TARGET" || git clone --depth 1 "$REPO_URL" "$TARGET" || die "clone failed"
    cd "$TARGET" || die "cannot cd $TARGET"
fi
ok "repo: $(pwd)"

# ---- 2. find a Python >= 3.10 ----
PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3 python; do
    command -v "$c" >/dev/null 2>&1 || continue
    if "$c" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
        PY="$c"; break
    fi
done
[ -n "$PY" ] || die "Python 3.10+ not found — install it (https://python.org or your package manager)"
ok "python: $($PY --version 2>&1) ($($PY -c 'import sys;print(sys.executable)'))"

# ---- 3. virtualenv (self-heal on debian/ubuntu if venv module missing) ----
if ! "$PY" -m venv .venv 2>/dev/null; then
    warn "venv module unavailable — attempting to install it…"
    if command -v apt-get >/dev/null 2>&1; then
        SUDO=""; [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1 && SUDO="sudo"
        $SUDO apt-get install -y python3-venv python3-pip >/dev/null 2>&1 || \
        $SUDO apt-get install -y python3.$("$PY" -c 'import sys;print(f"{sys.version_info[1]}")')-venv >/dev/null 2>&1 || true
    fi
    "$PY" -m venv .venv 2>/dev/null || warn "venv unavailable — falling back to a direct install"
fi

VPY=".venv/bin/python"
if [ -x "$VPY" ]; then
    ok "venv: .venv/"
    say "installing dependencies (fastapi, uvicorn, httpx, bs4, lxml)…"
    "$VPY" -m pip install -q --upgrade pip 2>/dev/null || true
    "$VPY" -m pip install -q -r requirements.txt || die "dependency install failed"
else
    warn "no venv — installing into user site…"
    "$PY" -m pip install -q --user -r requirements.txt 2>/dev/null || \
        "$PY" -m pip install -q --break-system-packages -r requirements.txt || die "dependency install failed"
    VPY="$PY"
fi
ok "dependencies installed"

# ---- 4. boot ----
echo
printf "${CYAN}  ╔══════════════════════════════════════════════╗${OFF}\n"
printf "${CYAN}  ║   A G E N T U S E  —  GRID COMING ONLINE     ║${OFF}\n"
printf "${CYAN}  ║   SpaceGrid →  http://localhost:8000         ║${OFF}\n"
printf "${CYAN}  ║   Ctrl+C to take the grid offline            ║${OFF}\n"
printf "${CYAN}  ╚══════════════════════════════════════════════╝${OFF}\n"
echo
PORT="${AGENTUSE_PORT:-8000}" exec "$VPY" run.py
