#Requires -Version 5.1
<#
.SYNOPSIS
    OpenHarness installer for Windows.

.DESCRIPTION
    Downloads the harness binary from GitHub Releases and initializes
    the ~/.openharness/ configuration directory.

.EXAMPLE
    irm https://raw.githubusercontent.com/iamikunnnnn/Bobby/main/install/install.ps1 | iex
#>

param(
    [string]$InstallDir = "",
    [string]$Version = "latest",
    [string]$Channel = "irm-install"
)

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

$script:RepoOwner = "iamikunnnnn"
$script:RepoName = "Bobby"
$script:HasGit = $false
$script:HasPython = $false
$script:HasUv = $false

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

function Write-Banner {
    Write-Host ""
    Write-Host "  ╔══════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "  ║       OpenHarness Installer          ║" -ForegroundColor Cyan
    Write-Host "  ╚══════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Ok($msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  [WARN] $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "  [ERROR] $msg" -ForegroundColor Red }

function Get-HarnessHome {
    if ($script:InstallDir) { return $script:InstallDir }
    $envHome = [Environment]::GetEnvironmentVariable("OPENHARNESS_HOME", "User")
    if ($envHome) { return $envHome }
    return Join-Path $env:USERPROFILE ".openharness"
}

function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "Machine")
}

# ---------------------------------------------------------------------------
# Dependency checks
# ---------------------------------------------------------------------------

function Test-Python {
    Refresh-Path
    try {
        $py = Get-Command python -ErrorAction SilentlyContinue
        if (-not $py) { $py = Get-Command python3 -ErrorAction SilentlyContinue }
        if ($py) {
            $ver = & $py.Source --version 2>&1
            Write-Ok "Python found: $ver"
            $script:HasPython = $true
            return $true
        }
    } catch {}
    Write-Warn "Python not found. Required for MCP servers."
    return $false
}

function Install-Uv {
    Refresh-Path
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        Write-Ok "uv found: $(uv --version)"
        $script:HasUv = $true
        return $true
    }
    Write-Host "  Installing uv..."
    try {
        winget install astral-sh.uv --accept-source-agreements --accept-package-agreements 2>$null
        Refresh-Path
        if (Get-Command uv -ErrorAction SilentlyContinue) {
            Write-Ok "uv installed via winget"
            $script:HasUv = $true
            return $true
        }
    } catch {}
    try {
        $installScript = Invoke-RestMethod https://astral.sh/uv/install.ps1
        Invoke-Expression $installScript
        Refresh-Path
        if (Get-Command uv -ErrorAction SilentlyContinue) {
            Write-Ok "uv installed via install script"
            $script:HasUv = $true
            return $true
        }
    } catch {}
    Write-Warn "Could not install uv. Install manually: winget install astral-sh.uv"
    return $false
}

function Test-Git {
    Refresh-Path
    if (Get-Command git -ErrorAction SilentlyContinue) {
        $script:HasGit = $true
        Write-Ok "Git found: $(git --version)"
        return $true
    }
    Write-Warn "Git not found. Required for some features."
    return $false
}

# ---------------------------------------------------------------------------
# Install functions
# ---------------------------------------------------------------------------

function Initialize-DirectoryStructure {
    param([string]$HarnessHome)

    $dirs = @(
        $HarnessHome
        (Join-Path $HarnessHome "bin")
        (Join-Path $HarnessHome "config")
        (Join-Path $HarnessHome "session")
        (Join-Path $HarnessHome "memory")
        (Join-Path $HarnessHome "skills\user")
        (Join-Path $HarnessHome "workspace\.tasks")
        (Join-Path $HarnessHome ".openharness")
    )
    foreach ($dir in $dirs) {
        if (-not (Test-Path $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
    }
    Write-Ok "Directory structure created at $HarnessHome"
}

function Install-HarnessBinary {
    param([string]$HarnessHome, [string]$Version)

    $binDir = Join-Path $HarnessHome "bin"
    $dest = Join-Path $binDir "harness.exe"

    if (Test-Path $dest) {
        Write-Ok "harness.exe already exists, skipping download"
        return $true
    }

    # Determine download URL
    $tag = if ($Version -eq "latest") { "latest" } else { "v$Version" }
    $baseUrl = "https://github.com/$script:RepoOwner/$script:RepoName/releases/$tag/download"
    $url = "$baseUrl/harness-windows.exe"

    Write-Host "  Downloading harness binary..."
    try {
        Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
        Write-Ok "Downloaded harness.exe to $dest"
        return $true
    } catch {
        # Fallback: try building from source if Python + uv available
        if ($script:HasPython -and $script:HasUv) {
            Write-Warn "Download failed. Attempting to build from source..."
            return Build-FromSource -HarnessHome $HarnessHome
        }
        Write-Err "Download failed and cannot build from source: $_"
        return $false
    }
}

function Build-FromSource {
    param([string]$HarnessHome)

    $binDir = Join-Path $HarnessHome "bin"
    $dest = Join-Path $binDir "harness.exe"

    Write-Host "  Building harness from source..."

    # Clone or use existing
    $repoDir = Join-Path $HarnessHome "repo"
    if (-not (Test-Path $repoDir)) {
        git clone "https://github.com/$script:RepoOwner/$script:RepoName.git" $repoDir
    }

    Push-Location $repoDir
    try {
        uv sync
        uv run pyinstaller cli.py --onefile --name harness --distpath $binDir
        if (Test-Path $dest) {
            Write-Ok "Built harness.exe from source"
            return $true
        }
        Write-Err "Build failed"
        return $false
    } finally {
        Pop-Location
    }
}

function Initialize-DefaultConfigs {
    param([string]$HarnessHome)

    $configDir = Join-Path $HarnessHome "config"
    $defaultsDir = Join-Path $PSScriptRoot "defaults"

    # If defaults dir doesn't exist (running via irm), download them
    if (-not (Test-Path $defaultsDir)) {
        $defaultsDir = Join-Path $HarnessHome "defaults_temp"
        New-Item -ItemType Directory -Path $defaultsDir -Force | Out-Null
        $baseUrl = "https://raw.githubusercontent.com/$script:RepoOwner/$script:RepoName/main/install/defaults"
        foreach ($file in @("harness.yaml", "mcp.yaml", "skill.yaml", ".env.example", "user_profile.md")) {
            try {
                Invoke-WebRequest -Uri "$baseUrl/$file" -OutFile (Join-Path $defaultsDir $file) -UseBasicParsing
            } catch {
                Write-Warn "Could not download default config: $file"
            }
        }
    }

        foreach ($file in @("harness.yaml", "mcp.yaml", "skill.yaml")) {
        $src = Join-Path $defaultsDir $file
        $dst = Join-Path $configDir $file
        if (Test-Path $dst) {
            Write-Host "  Skipped $file (already exists)"
        } elseif (Test-Path $src) {
            Copy-Item $src $dst
            Write-Ok "Installed $file"
        }
    }

    $envExampleDst = Join-Path $HarnessHome ".env.example"
    # Copy .env.example as .env
    $envDst = Join-Path $HarnessHome ".env"
    $envSrc = Join-Path $defaultsDir ".env.example"
    if (-not (Test-Path $envExampleDst) -and (Test-Path $envSrc)) {
        Copy-Item $envSrc $envExampleDst
        Write-Ok "Installed .env.example"
    }
    if (-not (Test-Path $envDst) -and (Test-Path $envSrc)) {
        Copy-Item $envSrc $envDst
        Write-Ok "Installed .env"
    }

    # Copy user_profile.md
    $profileDst = Join-Path $HarnessHome "memory\user_profile.md"
    $profileSrc = Join-Path $defaultsDir "user_profile.md"
    if (-not (Test-Path $profileDst) -and (Test-Path $profileSrc)) {
        Copy-Item $profileSrc $profileDst
        Write-Ok "Installed user_profile.md"
    }

    # Write install marker
    $markerPath = Join-Path $HarnessHome ".install-marker"
    if (-not (Test-Path $markerPath)) {
        $marker = @{
            version = "1.0.0"
            installed_at = (Get-Date).ToUniversalTime().ToString("o")
            platform = "windows"
            channel = $script:Channel
        }
        $marker | ConvertTo-Json | Set-Content $markerPath
        Write-Ok "Wrote install marker"
    }
}

function Set-PathVariable {
    param([string]$HarnessHome)

    $binDir = Join-Path $HarnessHome "bin"
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($userPath -split ";" | Where-Object { $_ -eq $binDir }) {
        Write-Ok "PATH already contains $binDir"
        return
    }
    $newPath = "$userPath;$binDir"
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    Refresh-Path
    Write-Ok "Added $binDir to user PATH"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

function Main {
    Write-Banner

    $installHome = Get-HarnessHome
    Write-Host "  Install directory: $installHome" -ForegroundColor White
    Write-Host ""

    # Dependency checks
    Test-Python | Out-Null
    Install-Uv | Out-Null
    Test-Git | Out-Null
    Write-Host ""

    # Install
    Initialize-DirectoryStructure $installHome
    Install-HarnessBinary $installHome $Version
    Initialize-DefaultConfigs $installHome
    Set-PathVariable $installHome

    # Summary
    Write-Host ""
    Write-Host "  ╔══════════════════════════════════════╗" -ForegroundColor Green
    Write-Host "  ║     Installation Complete!            ║" -ForegroundColor Green
    Write-Host "  ╚══════════════════════════════════════╝" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Binary:  $installHome\bin\harness.exe" -ForegroundColor White
    Write-Host "  Config:  $installHome\config\" -ForegroundColor White
    Write-Host "  .env:    $installHome\.env" -ForegroundColor White
    Write-Host ""
    Write-Host "  Next steps:" -ForegroundColor Yellow
    Write-Host "    1. Edit $installHome\.env with your API keys"
    Write-Host "    2. Open a new terminal (to refresh PATH)"
    Write-Host "    3. Run: harness info"

    if (-not $script:HasPython) {
        Write-Host ""
        Write-Warn "Python not found. MCP servers require Python."
        Write-Host "  Install: winget install Python.Python.3.12"
    }
}

try {
    Main
} catch {
    Write-Err "Installation failed: $_"
    exit 1
}
