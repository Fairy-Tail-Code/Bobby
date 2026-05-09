#Requires -Version 5.1
<#
.SYNOPSIS
    OpenHarness installer for Windows.

.DESCRIPTION
    Clones the repo to ~/.openharness/repo, runs uv sync, and sets up the
    harness CLI command via the venv entry point.

.EXAMPLE
    irm https://raw.githubusercontent.com/iamikunnnnn/Bobby/main/install/install.ps1 | iex
#>

param(
    [string]$InstallDir = "",
    [string]$Channel = "irm-install",
    [switch]$Upgrade
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

function Get-LatestRemoteTag {
    param([string]$RepoOwner, [string]$RepoName)

    try {
        $url = "https://api.github.com/repos/$RepoOwner/$RepoName/releases/latest"
        $response = Invoke-RestMethod -Uri $url -ErrorAction Stop
        return $response.tag_name
    } catch {
        Write-Warn "Could not fetch latest version from GitHub API: $_"
        return $null
    }
}

function Get-CurrentLocalTag {
    param([string]$RepoDir)

    if (-not (Test-Path $RepoDir)) { return $null }

    Push-Location $RepoDir
    try {
        # Check if HEAD is exactly on a tag
        $tag = git describe --exact-match --tags 2>$null
        if ($tag) { return $tag }

        # Get the most recent tag reachable from HEAD
        $tag = git describe --tags --abbrev=0 2>$null
        if ($tag) { return $tag }

        return "dev"
    } catch {
        return "dev"
    } finally {
        Pop-Location
    }
}

function Compare-Versions {
    param([string]$Tag1, [string]$Tag2)

    # Remove 'v' prefix and compare
    $v1 = $Tag1 -replace '^v', ''
    $v2 = $Tag2 -replace '^v', ''

    if ($v1 -eq $v2) { return 0 }

    try {
        $parts1 = $v1 -split '\.' | ForEach-Object { [int]$_ }
        $parts2 = $v2 -split '\.' | ForEach-Object { [int]$_ }

        $maxLen = [Math]::Max($parts1.Count, $parts2.Count)
        for ($i = 0; $i -lt $maxLen; $i++) {
            $p1 = if ($i -lt $parts1.Count) { $parts1[$i] } else { 0 }
            $p2 = if ($i -lt $parts2.Count) { $parts2[$i] } else { 0 }
            if ($p1 -gt $p2) { return 1 }
            if ($p1 -lt $p2) { return -1 }
        }
        return 0
    } catch {
        # If parsing fails, do string compare
        return [string]::Compare($v1, $v2)
    }
}

# ---------------------------------------------------------------------------
# Helpers (original)
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
    Write-Err "Python 3.12+ is required. Install: winget install Python.Python.3.12"
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
    Write-Err "Could not install uv. Install manually: winget install astral-sh.uv"
    return $false
}

function Test-Git {
    Refresh-Path
    if (Get-Command git -ErrorAction SilentlyContinue) {
        $script:HasGit = $true
        Write-Ok "Git found: $(git --version)"
        return $true
    }
    Write-Err "Git is required. Install: winget install Git.Git"
    return $false
}

# ---------------------------------------------------------------------------
# Install functions
# ---------------------------------------------------------------------------

function Initialize-DirectoryStructure {
    param([string]$HarnessHome)

    $dirs = @(
        $HarnessHome
        (Join-Path $HarnessHome "config")
        (Join-Path $HarnessHome "session")
        (Join-Path $HarnessHome "memory")
        (Join-Path $HarnessHome "skills\user")
        (Join-Path $HarnessHome "workspace\.tasks")
        (Join-Path $HarnessHome "agents\prompts")
        (Join-Path $HarnessHome ".openharness")
    )
    foreach ($dir in $dirs) {
        if (-not (Test-Path $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
    }
    Write-Ok "Directory structure created at $HarnessHome"
}

function Install-HarnessSource {
    param([string]$HarnessHome, [bool]$Upgrade = $false, [ref]$LatestTag)

    $repoDir = Join-Path $HarnessHome "repo"
    $venvBin = Join-Path $repoDir ".venv\Scripts"
    $script:LatestTag = Get-LatestRemoteTag -RepoOwner $script:RepoOwner -RepoName $script:RepoName

    if ($script:LatestTag) {
        Write-Host "  Latest version: $script:LatestTag" -ForegroundColor Cyan
    }

    # Check existing installation
    if (Test-Path $repoDir) {
        $localTag = Get-CurrentLocalTag -RepoDir $repoDir
        Write-Host "  Local version:  $localTag" -ForegroundColor Cyan

        # Version comparison
        if ($script:LatestTag -and $localTag -ne "dev") {
            $comparison = Compare-Versions -Tag1 $script:LatestTag -Tag2 $localTag

            if ($comparison -gt 0) {
                Write-Host "  New version available!" -ForegroundColor Yellow
                if ($Upgrade) {
                    Write-Host "  Updating from $localTag to $script:LatestTag..." -ForegroundColor Cyan
                    Push-Location $repoDir
                    try {
                        git fetch origin
                        git checkout $script:LatestTag 2>$null
                        if (-not $?) {
                            git pull origin $script:LatestTag
                        }
                        uv sync
                        Write-Ok "Updated to $script:LatestTag"
                        return $true, $script:LatestTag
                    } catch {
                        Write-Err "Update failed: $_"
                        return $false, $localTag
                    } finally {
                        Pop-Location
                    }
                } else {
                    Write-Warn "Use -Upgrade flag to update from $localTag to $script:LatestTag"
                    Write-Ok "Source repo already exists at $repoDir"
                    if (Test-Path $venvBin) {
                        return $true, $localTag
                    }
                }
            } else {
                Write-Ok "Already up to date at $localTag"
                if (Test-Path $venvBin) {
                    return $true, $localTag
                }
            }
        } else {
            # No version info or dev mode
            if ($Upgrade) {
                Write-Host "  Updating source code..." -ForegroundColor Cyan
                Push-Location $repoDir
                try {
                    git pull
                    uv sync
                    Write-Ok "Updated to latest"
                    return $true, "dev"
                } catch {
                    Write-Err "Update failed: $_"
                    return $false, $localTag
                } finally {
                    Pop-Location
                }
            }
            Write-Ok "Source repo already exists at $repoDir"
            if (Test-Path $venvBin) {
                return $true, $localTag
            }
        }
    }

    # Fresh install
    if (-not (Test-Path $repoDir)) {
        Write-Host "  Cloning repository..." -ForegroundColor Cyan
        git clone "https://github.com/$script:RepoOwner/$script:RepoName.git" $repoDir
        Write-Ok "Cloned to $repoDir"
    }

    Write-Host "  Installing dependencies (uv sync)..." -ForegroundColor Cyan
    Push-Location $repoDir
    try {
        uv sync
    } finally {
        Pop-Location
    }

    if (Test-Path $venvBin) {
        Write-Ok "Dependencies installed"
        return $true, $script:LatestTag
    }
    Write-Err "uv sync failed - venv not created"
    return $false, $null
}

function Initialize-DefaultConfigs {
    param([string]$HarnessHome, [string]$InstalledVersion = "unknown")

    $configDir = Join-Path $HarnessHome "config"
    $repoDir = Join-Path $HarnessHome "repo"
    $defaultsDir = Join-Path $repoDir "install\defaults"

    # Fallback: download defaults if repo not available
    if (-not (Test-Path $defaultsDir)) {
        $defaultsDir = Join-Path $HarnessHome "defaults_temp"
        if (-not (Test-Path $defaultsDir)) {
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

    # Copy .env.example and .env
    $envExampleDst = Join-Path $HarnessHome ".env.example"
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

    # Copy agent prompts from repo
    $promptsDst = Join-Path $HarnessHome "agents\prompts"
    $promptsSrc = Join-Path $repoDir "agents\prompts"
    if (Test-Path $promptsSrc) {
        foreach ($mdFile in (Get-ChildItem -Path $promptsSrc -Filter "*.md")) {
            $dst = Join-Path $promptsDst $mdFile.Name
            if (-not (Test-Path $dst)) {
                Copy-Item $mdFile.FullName $dst
            }
        }
        Write-Ok "Installed agent prompts"
    }

    # Write install marker
    $markerPath = Join-Path $HarnessHome ".install-marker"
    $marker = @{
        version = $InstalledVersion
        installed_at = (Get-Date).ToUniversalTime().ToString("o")
        platform = "windows"
        channel = $script:Channel
    }
    $marker | ConvertTo-Json | Set-Content $markerPath
    Write-Ok "Wrote install marker (version: $InstalledVersion)"
}

function Set-PathVariable {
    param([string]$HarnessHome)

    $venvBin = Join-Path $HarnessHome "repo\.venv\Scripts"
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")

    # Remove old bin path if present
    $oldBinDir = Join-Path $HarnessHome "bin"
    $parts = $userPath -split ";" | Where-Object { $_ -ne $oldBinDir }
    $cleanedPath = ($parts | Where-Object { $_ -ne "" }) -join ";"

    if ($parts | Where-Object { $_ -eq $venvBin }) {
        Write-Ok "PATH already contains $venvBin"
        return
    }

    $newPath = "$cleanedPath;$venvBin"
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    Refresh-Path
    Write-Ok "Added $venvBin to user PATH"
}

# ---------------------------------------------------------------------------
# Setup Wizard
# ---------------------------------------------------------------------------

function Invoke-SetupWizard {
    param([string]$HarnessHome)

    $harnessExe = Join-Path $HarnessHome "repo\.venv\Scripts\harness.exe"
    if (Test-Path $harnessExe) {
        Write-Host ""
        Write-Host "  Launching interactive setup wizard..." -ForegroundColor Cyan
        $env:OPENHARNESS_HOME = $HarnessHome
        try {
            & $harnessExe setup
            return
        } catch {
            Write-Warn "harness setup failed: $($_.Exception.Message)"
        }
    } else {
        Write-Warn "harness command not found, skipping setup wizard"
    }
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

function Main {
    Write-Banner

    $installHome = Get-HarnessHome
    Write-Host "  Install directory: $installHome" -ForegroundColor White
    Write-Host ""

    # Dependency checks (Python, uv, Git are all required now)
    $depsOk = $true
    if (-not (Test-Python)) { $depsOk = $false }
    if (-not (Install-Uv))  { $depsOk = $false }
    if (-not (Test-Git))    { $depsOk = $false }

    if (-not $depsOk) {
        Write-Host ""
        Write-Err "Missing required dependencies. Please install them and re-run."
        Write-Host "  Python: winget install Python.Python.3.12"
        Write-Host "  uv:     winget install astral-sh.uv"
        Write-Host "  Git:    winget install Git.Git"
        return
    }
    Write-Host ""

    # Install
    Initialize-DirectoryStructure $installHome
    $installResult = Install-HarnessSource $installHome -Upgrade:$Upgrade
    $installSuccess = $installResult[0]
    $installedVersion = if ($installResult[1]) { $installResult[1] } else { "unknown" }

    if (-not $installSuccess) {
        return
    }
    Initialize-DefaultConfigs $installHome -InstalledVersion $installedVersion
    Set-PathVariable $installHome

    # Setup wizard
    Invoke-SetupWizard $installHome

    # Summary
    Write-Host ""
    Write-Host "  ╔══════════════════════════════════════╗" -ForegroundColor Green
    Write-Host "  ║     Installation Complete!            ║" -ForegroundColor Green
    Write-Host "  ╚══════════════════════════════════════╝" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Version: $installedVersion" -ForegroundColor Cyan
    Write-Host "  Source:  $installHome\repo\" -ForegroundColor White
    Write-Host "  Config:  $installHome\config\" -ForegroundColor White
    Write-Host "  .env:    $installHome\.env" -ForegroundColor White
    Write-Host ""
    Write-Host "  Next steps:" -ForegroundColor Yellow
    Write-Host "    1. Open a new terminal (to refresh PATH)"
    Write-Host "    2. Run: harness info"
    if (-not $Upgrade) {
        Write-Host ""
        Write-Host "  To upgrade later, run:" -ForegroundColor Yellow
        Write-Host "    irm https://raw.githubusercontent.com/iamikunnnnn/Bobby/main/install/install.ps1 -OutFile install.ps1"
        Write-Host "    .\install.ps1 -Upgrade"
    }
}

try {
    Main
} catch {
    Write-Err "Installation failed: $_"
    exit 1
}
