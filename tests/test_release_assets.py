from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL_SH = REPO_ROOT / "install" / "install.sh"
RELEASE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"


def _parse_non_windows_release_assets(workflow_text: str) -> set[str]:
    return {
        match.group(1)
        for match in re.finditer(r"mv harness (harness-(?:linux|macos)[^\s]*)", workflow_text)
    }


def test_install_script_references_non_windows_release_assets() -> None:
    workflow_text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    install_text = INSTALL_SH.read_text(encoding="utf-8")

    expected_assets = _parse_non_windows_release_assets(workflow_text)

    assert expected_assets
    for asset_name in expected_assets:
        assert asset_name in install_text, (
            f"install.sh does not reference released asset '{asset_name}'."
        )
