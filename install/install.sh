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
VERSION="${INSTALL_VERSION:-latest}"
CHANNEL="${INSTALL_CHANNEL:-curl-install}"
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
    warn "Python not found. MCP servers require Python."
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
    warn "Could not install uv. Install manually: curl -fsSL https://astral.sh/uv/install.sh | sh"
    return 1
}

check_git() {
    if command -v git &>/dev/null; then
        ok "Git found: $(git --version)"
        HAS_GIT=true
        return 0
    fi
    warn "Git not found. Required for some features."
    return 1
}

# ---------------------------------------------------------------------------
# Install functions
# ---------------------------------------------------------------------------
init_directory_structure() {
    local home="$1"
    local dirs=(
        "$home"
        "$home/bin"
        "$home/config"
        "$home/session"
        "$home/memory"
        "$home/skills/user"
        "$home/workspace/.tasks"
        "$home/.openharness"
    )
    for dir in "${dirs[@]}"; do
        mkdir -p "$dir"
    done
    ok "Directory structure created at $home"
}

install_harness_binary() {
    local home="$1"
    local dest="$home/bin/harness"

    if [[ -f "$dest" ]]; then
        ok "harness binary already exists, skipping download"
        return 0
    fi

    local tag
    tag=$( [[ "$VERSION" == "latest" ]] && echo "latest" || echo "v$VERSION" )
    local os_name arch asset_name
    os_name=$(uname -s | tr '[:upper:]' '[:lower:]')
    case "$(uname -m)" in
        x86_64|amd64) arch="x86_64" ;;
        arm64|aarch64) arch="aarch64" ;;
        *) arch="$(uname -m)" ;;
    esac

    case "$os_name" in
        linux) asset_name="harness-linux" ;;
        darwin) asset_name="harness-macos" ;;
        *) asset_name="harness-${os_name}" ;;
    esac

    local url="https://github.com/$REPO_OWNER/$REPO_NAME/releases/$tag/download/${asset_name}"

    info "Downloading harness binary..."
    if curl -fsSL -o "$dest" "$url"; then
        chmod +x "$dest"
        ok "Downloaded harness to $dest"
        return 0
    fi

    # Fallback: try legacy arch-specific asset names.
    url="https://github.com/$REPO_OWNER/$REPO_NAME/releases/$tag/download/harness-${os_name}-${arch}"
    if curl -fsSL -o "$dest" "$url"; then
        chmod +x "$dest"
        ok "Downloaded harness to $dest"
        return 0
    fi

    # Fallback: try generic name.
    url="https://github.com/$REPO_OWNER/$REPO_NAME/releases/$tag/download/harness"
    if curl -fsSL -o "$dest" "$url"; then
        chmod +x "$dest"
        ok "Downloaded harness to $dest"
        return 0
    fi

    # Fallback: build from source
    if $HAS_PYTHON && $HAS_UV; then
        warn "Download failed. Attempting to build from source..."
        build_from_source "$home"
        return $?
    fi

    err "Download failed and cannot build from source."
    return 1
}

build_from_source() {
    local home="$1"
    local dest="$home/bin/harness"

    info "Building harness from source..."
    local repo_dir="$home/repo"
    if [[ ! -d "$repo_dir" ]]; then
        git clone "https://github.com/$REPO_OWNER/$REPO_NAME.git" "$repo_dir"
    fi
    cd "$repo_dir"
    uv sync
    uv run pyinstaller cli.py --onefile --name harness --distpath "$home/bin"
    if [[ -f "$dest" ]]; then
        ok "Built harness from source"
        return 0
    fi
    err "Build failed"
    return 1
}

init_default_configs() {
    local home="$1"
    local config_dir="$home/config"
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local defaults_dir="$script_dir/defaults"

    # If defaults dir doesn't exist (running via curl), download them
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

    local env_example_dst="$home/.env.example"
    # Copy .env.example as .env
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

    # Write install marker
    local marker_path="$home/.install-marker"
    if [[ ! -f "$marker_path" ]]; then
        cat > "$marker_path" <<MARKER_EOF
{
  "version": "1.0.0",
  "installed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "platform": "$(uname -s)",
  "channel": "$CHANNEL"
}
MARKER_EOF
        ok "Wrote install marker"
    fi
}

set_path_variable() {
    local home="$1"
    local bin_dir="$home/bin"

    # Check if already in PATH
    if echo "$PATH" | tr ':' '\n' | grep -qF "$bin_dir"; then
        ok "PATH already contains $bin_dir"
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
    echo "export PATH=\"\$PATH:$bin_dir\"" >> "$rc_file"
    export PATH="$PATH:$bin_dir"
    ok "Added $bin_dir to PATH (via $rc_file)"
}

# ---------------------------------------------------------------------------
# Setup Wizard
# ---------------------------------------------------------------------------
run_setup_wizard() {
    local home="$1"
    local env_path="$home/.env"

    # Ask user if they want to configure, even if .env exists
    if [[ -f "$env_path" ]] && grep -qP '_API_KEY=\S+' "$env_path" 2>/dev/null; then
        echo "  .env already has API keys configured."
        read -rp "  Reconfigure? [y/N]: " reconfig
        if [[ ! "$reconfig" =~ ^[Yy]$ ]]; then
            echo "  Skipping wizard."
            return 0
        fi
    fi

    echo ""
    echo -e "  ${CYAN}── Configuration Wizard ──${NC}"
    echo ""

    # LLM Provider
    echo "  Which LLM provider do you want to use?"
    echo "    1) OpenAI"
    echo "    2) Zhipu / GLM (智谱)"
    echo "    3) DeepSeek"
    echo "    4) Anthropic / Claude"
    echo "    5) Other (custom base URL)"
    read -rp "  Enter choice [1-5, default=1]: " choice
    choice="${choice:-1}"

    case "$choice" in
        1) default_url="https://api.openai.com/v1"; default_model="gpt-4o" ;;
        2) default_url="https://open.bigmodel.cn/api/paas/v4"; default_model="GLM-4-Plus" ;;
        3) default_url="https://api.deepseek.com"; default_model="deepseek-chat" ;;
        4) default_url="https://api.anthropic.com"; default_model="claude-sonnet-4-20250514" ;;
        *) default_url=""; default_model="" ;;
    esac

    read -rp "  Base URL [$default_url]: " base_url
    base_url="${base_url:-$default_url}"

    read -rp "  Model name [$default_model]: " model
    model="${model:-$default_model}"

    read -rp "  API Key: " api_key
    if [[ -z "$api_key" ]]; then
        warn "No API key provided. You can edit .env later."
        return 0
    fi

    echo ""
    echo "  Use the same API config for all 4 agents (PM, Planner, Generator, Evaluator)?"
    read -rp "  [Y/n, default=Y]: " same_all
    same_all="${same_all:-Y}"

    local env_content=""
    local roles="PM:0.7 PLANNER:0.7 GENERATOR:0.4 EVALUATOR:0.2"

    for role_temp in $roles; do
        local prefix="${role_temp%%:*}"
        local temp="${role_temp##*:}"

        if [[ "$same_all" =~ ^[Yy] ]]; then
            r_model="$model"
            r_url="$base_url"
            r_key="$api_key"
        else
            echo ""
            echo -e "  ${YELLOW}── $prefix Agent ──${NC}"
            read -rp "  Model [$model]: " r_model
            r_model="${r_model:-$model}"
            read -rp "  Base URL [$base_url]: " r_url
            r_url="${r_url:-$base_url}"
            read -rp "  API Key [$api_key]: " r_key
            r_key="${r_key:-$api_key}"
        fi

        env_content+="${prefix}_MODEL=${r_model}"$'\n'
        env_content+="${prefix}_BASE_URL=${r_url}"$'\n'
        env_content+="${prefix}_API_KEY=${r_key}"$'\n'
        env_content+="${prefix}_TEMPERATURE=${temp}"$'\n'
    done

    echo "$env_content" > "$env_path"
    ok "Configuration saved to $env_path"
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

    # Dependency checks
    check_python || true
    install_uv || true
    check_git || true
    echo ""

    # Install
    init_directory_structure "$home"
    install_harness_binary "$home"
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
    echo "  Binary:  $home/bin/harness"
    echo "  Config:  $home/config/"
    echo "  .env:    $home/.env"
    echo ""
    echo -e "  ${YELLOW}Next steps:${NC}"
    echo "    1. Run: source ~/.bashrc  (or restart your shell)"
    echo "    2. Run: harness info"

    if ! $HAS_PYTHON; then
        echo ""
        warn "Python not found. MCP servers require Python."
        echo "  Install: https://www.python.org/downloads/"
    fi
}

trap 'err "Installation failed on line $LINENO"; exit 1' ERR
main
