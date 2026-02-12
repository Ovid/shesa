#!/usr/bin/env bash
# Launch the Shesha arXiv Web Explorer.
# Handles venv creation, dependency installation, frontend build, and startup.
#
# Usage:
#   ./run-web.sh                      # defaults
#   ./run-web.sh --model gpt-5-mini   # pass args to shesha-web
#   ./run-web.sh --port 8080          # custom port
#   ./run-web.sh --no-browser         # don't open browser
#   ./run-web.sh --rebuild            # force frontend rebuild

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
FRONTEND_DIR="$SCRIPT_DIR/src/shesha/experimental/web/frontend"
FRONTEND_DIST="$FRONTEND_DIR/dist"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[shesha]${NC} $*"; }
warn()  { echo -e "${YELLOW}[shesha]${NC} $*"; }
error() { echo -e "${RED}[shesha]${NC} $*" >&2; }

# --- Parse our own flags (strip --rebuild before passing to shesha-web) ---
REBUILD=false
SHESHA_ARGS=()
for arg in "$@"; do
    if [ "$arg" = "--rebuild" ]; then
        REBUILD=true
    else
        SHESHA_ARGS+=("$arg")
    fi
done

# --- Check prerequisites ---
check_command() {
    if ! command -v "$1" &>/dev/null; then
        error "$1 is required but not found. $2"
        exit 1
    fi
}

check_command python3 "Install from https://www.python.org/downloads/"
check_command node    "Install from https://nodejs.org/"
check_command npm     "Install from https://nodejs.org/"
check_command docker  "Install from https://www.docker.com/get-started/"

# Check Python version >= 3.12
PYVER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYMAJOR=$(echo "$PYVER" | cut -d. -f1)
PYMINOR=$(echo "$PYVER" | cut -d. -f2)
if [ "$PYMAJOR" -lt 3 ] || { [ "$PYMAJOR" -eq 3 ] && [ "$PYMINOR" -lt 12 ]; }; then
    error "Python 3.12+ required, found $PYVER"
    exit 1
fi

# Check for an API key
if [ -z "${OPENAI_API_KEY:-}" ] && [ -z "${ANTHROPIC_API_KEY:-}" ] && [ -z "${LITELLM_API_KEY:-}" ]; then
    warn "No LLM API key detected (OPENAI_API_KEY, ANTHROPIC_API_KEY, or LITELLM_API_KEY)."
    warn "Set one before querying papers. Continuing anyway..."
fi

# Check Docker is running
if ! docker info &>/dev/null 2>&1; then
    warn "Docker daemon is not running. Start Docker Desktop before querying papers."
fi

# --- Virtual environment ---
if [ ! -d "$VENV_DIR" ]; then
    info "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

# --- Python dependencies ---
# Install/update if shesha-web command doesn't exist or pyproject.toml is newer
MARKER="$VENV_DIR/.shesha-web-installed"
if [ ! -f "$MARKER" ] || [ "$SCRIPT_DIR/pyproject.toml" -nt "$MARKER" ]; then
    info "Installing Python dependencies..."
    pip install -q -e ".[web]"
    touch "$MARKER"
else
    info "Python dependencies up to date."
fi

# --- Frontend build ---
if [ "$REBUILD" = true ] || [ ! -d "$FRONTEND_DIST" ]; then
    info "Building frontend..."
    (cd "$FRONTEND_DIR" && npm install --silent && npm run build)
else
    info "Frontend already built. Use --rebuild to force."
fi

# --- Launch ---
info "Starting Shesha arXiv Web Explorer..."
exec shesha-web "${SHESHA_ARGS[@]}"
