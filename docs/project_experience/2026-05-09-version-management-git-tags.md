# 版本管理系统 - Git Tags 方案

> 实现日期: 2026-05-09
> 方案: 使用 Git Tags 进行版本控制

## 背景

之前安装脚本在检测到已有代码时不会自动更新，即使用户重新运行 `irm` 命令。需要引入版本管理能力：
- 安装时检查版本，如果版本一致则跳过，不一致则重新 clone
- Git push 时自动更新版本号

## 方案选择

经过调研，采用 **Git Tags (方案 C)**，原因：
1. 符合 Git 工作流，tag 是官方版本标识方式
2. 无需额外脚本维护版本号
3. 可以回滚到任意历史版本
4. GitHub Releases 可以关联 tag 发布说明
5. 业内通用做法（Docker、很多 CLI 工具都采用此方案）

## 实现

### 1. 安装脚本版本检查功能

#### install.ps1 (Windows)

新增函数：
- `Get-LatestRemoteTag`: 从 GitHub API 获取最新 release tag
- `Get-CurrentLocalTag`: 获取本地当前 tag
- `Compare-Versions`: 语义化版本比较（v1.0.0 vs v1.0.1）

修改 `Install-HarnessSource`：
- 检测远程最新版本和本地版本
- 如果远程版本更新，提示使用 `-Upgrade` 标志
- 使用 `-Upgrade` 时自动 git checkout 到对应 tag 并执行 uv sync

#### install.sh (macOS/Linux)

同样实现上述功能（Bash 版本）。

### 2. GitHub Actions 自动发布

创建 `.github/workflows/release.yml`：

```yaml
name: Create Release

on:
  push:
    branches:
      - main
    paths:
      - 'pyproject.toml'
  workflow_dispatch:

permissions:
  contents: write

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Get version from pyproject.toml
        id: version
        run: |
          VERSION=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
          echo "version=$VERSION" >> $GITHUB_OUTPUT
          echo "tag=v$VERSION" >> $GITHUB_OUTPUT
      - name: Check if tag exists
        id: check_tag
        run: |
          TAG=${{ steps.version.outputs.tag }}
          if git rev-parse "$TAG" >/dev/null 2>&1; then
            echo "exists=true" >> $GITHUB_OUTPUT
          else
            echo "exists=false" >> $GAPSHOT_OUTPUT
          fi
      - name: Create tag and release
        if: steps.check_tag.outputs.exists == 'false'
        run: |
          TAG=${{ steps.version.outputs.tag }}
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git tag -a "$TAG" -m "Release $VERSION"
          git push origin "$TAG"
          gh release create "$TAG" --title "$TAG" --generate-notes
        env:
          GH_TOKEN: ${{ github.token }}
```

### 3. 版本号来源

版本号从 `pyproject.toml` 中的 `version` 字段获取：

```toml
[project]
name = "ag2-openharness"
version = "0.1.1"
```

## 使用方式

### 发布新版本

1. 修改 `pyproject.toml` 中的 `version`（如从 0.1.0 改为 0.1.1）
2. Push 到 main 分支
3. GitHub Actions 自动创建 Release 和 Tag

### 用户安装/升级

#### 首次安装

```powershell
# Windows
irm https://raw.githubusercontent.com/iamikunnnnn/Bobby/main/install/install.ps1 | iex
```

```bash
# macOS/Linux
curl -fsSL https://raw.githubusercontent.com/iamikunnnnn/Bobby/main/install/install.sh | bash
```

#### 升级

```powershell
# Windows
irm https://raw.githubusercontent.com/iamikunnnnn/Bobby/main/install/install.ps1 -OutFile install.ps1
.\install.ps1 -Upgrade
```

```bash
# macOS/Linux
INSTALL_UPGRADE=true curl -fsSL https://raw.githubusercontent.com/iamikunnnnn/Bobby/main/install/install.sh | bash
```

## 安装输出示例

```
  ╔══════════════════════════════════════╗
  ║       OpenHarness Installer          ║
  ╚══════════════════════════════════════╝

  Install directory: C:\Users\ikun\.openharness

  [OK] Python found: Python 3.11.7
  [OK] uv found: uv 0.11.9
  [OK] Git found: git version 2.45.1.windows.1

  [OK] Directory structure created at C:\Users\ikun\.openharness
  Latest version: v0.1.1
  Local version:  v0.0.8
  New version available!
  [WARN] Use -Upgrade flag to update from v0.0.8 to v0.1.1
  [OK] Source repo already exists at C:\Users\ikun\.openharness\repo
  ...

  ╔══════════════════════════════════════╗
  ║     Installation Complete!            ║
  ╚══════════════════════════════════════╝

  Version: v0.0.8
  Source:  C:\Users\ikun\.openharness\repo\
  Config:  C:\Users\ikun\.openharness\config\
  .env:    C:\Users\ikun\.openharness\.env

  Next steps:
    1. Open a new terminal (to refresh PATH)
    2. Run: harness info

  To upgrade later, run:
    irm https://raw.githubusercontent.com/iamikunnnnn/Bobby/main/install/install.ps1 -OutFile install.ps1
    .\install.ps1 -Upgrade
```

## 技术细节

### 版本比较算法

使用语义化版本比较（Semantic Versioning）：
- 去除 `v` 前缀
- 按点号分割为数字数组
- 逐位比较，高版本数字大则版本更新

示例：
- `v0.1.0` vs `v0.1.1` → 0.1.1 更新
- `v0.1.0` vs `v0.2.0` → 0.2.0 更新
- `v1.0.0` vs `v0.9.9` → 1.0.0 更新

### GitHub API 调用

使用 GitHub Releases API 获取最新版本：
```
GET https://api.github.com/repos/iamikunnnnn/Bobby/releases/latest
```

返回 JSON 中的 `tag_name` 字段即为最新版本。

### 标签检测

使用 `git describe` 命令：
- `git describe --exact-match --tags`: 检查 HEAD 是否恰好是某个 tag
- `git describe --tags --abbrev=0`: 获取最近的 tag

## 后续优化

1. **版本回滚**: 支持 `harness install --version v0.1.0` 回滚到指定版本
2. **预发布版本**: 支持 alpha/beta/rc 标签
3. **自动检查**: `harness` 命令运行时自动检查并提示更新
4. **changelog 集成**: 从 git commits 自动生成 changelog
