#!/usr/bin/env bash
#
# OpenHarness installer for macOS and Linux.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/iamikunnnnn/Bobby/main/install/install.sh | bash
#
set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
REPO_OWNER="iamikunnnnn"
REPO_NAME="Bobby"
CHANNEL="${INSTALL_CHANNEL:-curl-install}"
UPGRADE="${INSTALL_UPGRADE:-false}"
HAS_PYTHON=false
HAS_UV=false
HAS_GIT=false

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()    { echo -e "${CYAN}  [INFO]${NC} $*"; }
ok()      { echo -e "${GREEN}  [OK]${NC} $*"; }
warn()    { echo -e "${YELLOW}  [WARN]${NC} $*"; }
err()     { echo -e "${RED}  [ERROR]${NC} $*"; }

banner() {
    echo ""
    echo -e "  ${CYAN}╔══════════════════════════════════════╗${NC}"
    echo -e "  ${CYAN}║       OpenHarness Installer          ║${NC}"
    echo -e "  ${CYAN}╚══════════════════════════════════════╝${NC}"
    echo ""
}

get_harness_home() {
    if [[ -n "${OPENHARNESS_HOME:-}" ]]; then
        echo "$OPENHARNESS_HOME"
    else
        echo "$HOME/.openharness"
    fi
}

refresh_path() {
    export PATH="$(bash -l -c 'echo $PATH' 2>/dev/null || echo $PATH)"
}

# ---------------------------------------------------------------------------
# Dependency checks
# ---------------------------------------------------------------------------
check_python() {
    refresh_path
    if command -v python3 &>/dev/null; then
        local ver
        ver=$(python3 --version 2>&1)
        ok "Python found: $ver"
        HAS_PYTHON=true
        return 0
    elif command -v python &>/dev/null; then
        local ver
        ver=$(python --version 2>&1)
        ok "Python found: $ver"
        HAS_PYTHON=true
        return 0
    fi
    err "Python 3.12+ is required. Install: https://www.python.org/downloads/"
    return 1
}

install_uv() {
    refresh_path
    if command -v uv &>/dev/null; then
        ok "uv found: $(uv --version)"
        HAS_UV=true
        return 0
    fi
    info "Installing uv..."
    # Try brew first (macOS)
    if [[ "$(uname)" == "Darwin" ]] && command -v brew &>/dev/null; then
        brew install uv 2>/dev/null && refresh_path && command -v uv &>/dev/null && {
            ok "uv installed via brew"
            HAS_UV=true
            return 0
        }
    fi
    # Try pip
    pip install uv 2>/dev/null && refresh_path && command -v uv &>/dev/null && {
        ok "uv installed via pip"
        HAS_UV=true
        return 0
    }
    # Try official installer
    curl -fsSL https://astral.sh/uv/install.sh | sh 2>/dev/null && refresh_path && command -v uv &>/dev/null && {
        ok "uv installed via official script"
        HAS_UV=true
        return 0
    }
    err "Could not install uv. Install manually: curl -fsSL https://astral.sh/uv/install.sh | sh"
    return 1
}

check_git() {
    if command -v git &>/dev/null; then
        ok "Git found: $(git --version)"
        HAS_GIT=true
        return 0
    fi
    err "Git is required."
    return 1
}

# ---------------------------------------------------------------------------
# Install functions
# ---------------------------------------------------------------------------
init_directory_structure() {
    local home="$1"
    local dirs=(
        "$home"
        "$home/config"
        "$home/session"
        "$home/memory"
        "$home/skills/user"
        "$home/workspace/.tasks"
        "$home/agents/prompts"
        "$home/.openharness"
    )
    for dir in "${dirs[@]}"; do
        mkdir -p "$dir"
    done
    ok "Directory structure created at $home"
}

install_harness_source() {
    local home="$1"
    local repo_dir="$home/repo"

    # Upgrade: git pull + uv sync
    if [[ -d "$repo_dir" ]] && [[ "$UPGRADE" == "true" ]]; then
        info "Updating source code..."
        cd "$repo_dir"
        git pull
        uv sync
        ok "Updated to latest version"
        cd - > /dev/null
        return 0
    fi

    # Fresh install
    if [[ -d "$repo_dir" ]]; then
        ok "Source repo already exists at $repo_dir"
        # Still run uv sync if venv is missing
        if [[ -d "$repo_dir/.venv" ]]; then
            return 0
        fi
    fi

    if [[ ! -d "$repo_dir" ]]; then
        info "Cloning repository..."
        git clone "https://github.com/$REPO_OWNER/$REPO_NAME.git" "$repo_dir"
        ok "Cloned to $repo_dir"
    fi

    info "Installing dependencies (uv sync)..."
    cd "$repo_dir"
    uv sync
    cd - > /dev/null

    if [[ -d "$repo_dir/.venv" ]]; then
        ok "Dependencies installed"
        return 0
    fi
    err "uv sync failed - venv not created"
    return 1
}

init_default_configs() {
    local home="$1"
    local config_dir="$home/config"
    local repo_dir="$home/repo"
    local defaults_dir="$repo_dir/install/defaults"

    # Fallback: download defaults if repo not available
    if [[ ! -d "$defaults_dir" ]]; then
        defaults_dir="$home/defaults_temp"
        mkdir -p "$defaults_dir"
        local base_url="https://raw.githubusercontent.com/$REPO_OWNER/$REPO_NAME/main/install/defaults"
        for file in harness.yaml mcp.yaml skill.yaml .env.example user_profile.md; do
            curl -fsSL -o "$defaults_dir/$file" "$base_url/$file" 2>/dev/null || \
                warn "Could not download default config: $file"
        done
    fi

    for file in harness.yaml mcp.yaml skill.yaml; do
        local src="$defaults_dir/$file"
        local dst="$config_dir/$file"
        if [[ -f "$dst" ]]; then
            echo "  Skipped $file (already exists)"
        elif [[ -f "$src" ]]; then
            cp "$src" "$dst"
            ok "Installed $file"
        fi
    done

    # Copy .env.example and .env
    local env_example_dst="$home/.env.example"
    local env_dst="$home/.env"
    local env_src="$defaults_dir/.env.example"
    if [[ ! -f "$env_example_dst" ]] && [[ -f "$env_src" ]]; then
        cp "$env_src" "$env_example_dst"
        ok "Installed .env.example"
    fi
    if [[ ! -f "$env_dst" ]] && [[ -f "$env_src" ]]; then
        cp "$env_src" "$env_dst"
        ok "Installed .env"
    fi

    # Copy user_profile.md
    local profile_dst="$home/memory/user_profile.md"
    local profile_src="$defaults_dir/user_profile.md"
    if [[ ! -f "$profile_dst" ]] && [[ -f "$profile_src" ]]; then
        cp "$profile_src" "$profile_dst"
        ok "Installed user_profile.md"
    fi

    # Copy agent prompts from repo
    local prompts_dst="$home/agents/prompts"
    local prompts_src="$repo_dir/agents/prompts"
    if [[ -d "$prompts_src" ]]; then
        for md_file in "$prompts_src"/*.md; do
            local base_name
            base_name=$(basename "$md_file")
            if [[ ! -f "$prompts_dst/$base_name" ]]; then
                cp "$md_file" "$prompts_dst/$base_name"
            fi
        done
        ok "Installed agent prompts"
    fi

    # Write install marker
    local marker_path="$home/.install-marker"
    cat > "$marker_path" <<MARKER_EOF
{
  "version": "1.0.0",
  "installed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "platform": "$(uname -s)",
  "channel": "$CHANNEL"
}
MARKER_EOF
    ok "Wrote install marker"
}

set_path_variable() {
    local home="$1"
    local venv_bin="$home/repo/.venv/bin"
    # macOS/Linux: uv creates bin/ not Scripts/
    if [[ "$(uname)" == "Darwin" ]] || [[ "$(uname)" == "Linux" ]]; then
        venv_bin="$home/repo/.venv/bin"
    fi

    # Remove old bin path if present
    local old_bin_dir="$home/bin"

    # Check if already in PATH
    if echo "$PATH" | tr ':' '\n' | grep -qF "$venv_bin"; then
        ok "PATH already contains $venv_bin"
        return 0
    fi

    # Detect shell and add to appropriate rc file
    local rc_file=""
    local shell_name="$(basename "${SHELL:-bash}")"
    case "$shell_name" in
        zsh)  rc_file="$HOME/.zshrc" ;;
        bash) rc_file="$HOME/.bashrc" ;;
        *)    rc_file="$HOME/.profile" ;;
    esac

    echo "" >> "$rc_file"
    echo "# OpenHarness" >> "$rc_file"
    echo "export PATH=\"\$PATH:$venv_bin\"" >> "$rc_file"
    export PATH="$PATH:$venv_bin"
    ok "Added $venv_bin to PATH (via $rc_file)"
}

# ---------------------------------------------------------------------------
# Setup Wizard
# ---------------------------------------------------------------------------
run_setup_wizard() {
    local home="$1"
    local harness_bin="$home/repo/.venv/bin/harness"
    if [[ ! -x "$harness_bin" ]]; then
        warn "harness command not found, skipping setup wizard"
        return 0
    fi

    echo ""
    info "Launching interactive setup wizard..."
    OPENHARNESS_HOME="$home" "$harness_bin" setup
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    banner

    local home
    home="$(get_harness_home)"
    echo "  Install directory: $home"
    echo ""

    # Dependency checks (Python, uv, Git are all required)
    local deps_ok=true
    check_python || deps_ok=false
    install_uv || deps_ok=false
    check_git || deps_ok=false

    if [[ "$deps_ok" == "false" ]]; then
        echo ""
        err "Missing required dependencies. Please install them and re-run."
        echo "  Python: https://www.python.org/downloads/"
        echo "  uv:     curl -fsSL https://astral.sh/uv/install.sh | sh"
        echo "  Git:    https://git-scm.com/downloads"
        return
    fi
    echo ""

    # Install
    init_directory_structure "$home"
    install_harness_source "$home"
    init_default_configs "$home"
    set_path_variable "$home"

    # Setup wizard
    run_setup_wizard "$home"

    # Summary
    echo ""
    echo -e "  ${GREEN}╔══════════════════════════════════════╗${NC}"
    echo -e "  ${GREEN}║     Installation Complete!            ║${NC}"
    echo -e "  ${GREEN}╚══════════════════════════════════════╝${NC}"
    echo ""
    echo "  Source:  $home/repo/"
    echo "  Config:  $home/config/"
    echo "  .env:    $home/.env"
    echo ""
    echo -e "  ${YELLOW}Next steps:${NC}"
    echo "    1. Run: source ~/.bashrc  (or restart your shell)"
    echo "    2. Run: harness info"
}

trap 'err "Installation failed on line $LINENO"; exit 1' ERR
main
