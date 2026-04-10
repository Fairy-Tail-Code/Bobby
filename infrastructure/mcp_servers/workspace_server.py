from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations


workspace_server = FastMCP("openharness-workspace", log_level="ERROR")

# Directories to skip during recursive traversal
_SKIP_DIRS: frozenset[str] = frozenset({
    ".git", ".svn", ".hg",
    "node_modules", "__pycache__", ".pytest_cache",
    ".venv", "venv", "env",
    ".idea", ".vscode", ".vs",
    "dist", "build", ".next", ".nuxt",
    ".tox", ".mypy_cache", ".ruff_cache",
})


@dataclass(frozen=True, slots=True)
class WorkspacePath:
    """Describe one resolved path pair used by workspace tools."""

    root: Path
    path: Path


def build_workspace_server() -> FastMCP:
    """Return the configured workspace MCP server instance."""
    return workspace_server


@workspace_server.tool(
    description="List files and directories under one path. Default is non-recursive. Use recursive=true to drill into subdirectories.",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
)
def list_files(
    path: str = ".",
    cwd: str | None = None,
    recursive: bool = False,
    max_entries: int = 200,
) -> dict[str, Any]:
    """List directory entries relative to one root path.

    Non-recursive by default to prevent context explosion.
    Skips known junk directories (.git, node_modules, __pycache__, etc.).
    """
    if max_entries <= 0:
        raise ValueError("Tool 'list_files' field 'max_entries' must be a positive integer.")
    resolved = _resolve_workspace_path(path, cwd=cwd)
    if not resolved.path.exists():
        raise ValueError(f"Path '{resolved.path}' does not exist.")
    if not resolved.path.is_dir():
        raise ValueError(f"Path '{resolved.path}' is not a directory.")

    entries: list[dict[str, Any]] = []
    if recursive:
        for current_path in _safe_rglob(resolved.path):
            if len(entries) >= max_entries:
                break
            entries.append(
                {
                    "path": _render_relative_path(current_path, resolved.root),
                    "type": "dir" if current_path.is_dir() else "file",
                }
            )
    else:
        for current_path in sorted(resolved.path.iterdir()):
            if len(entries) >= max_entries:
                break
            entries.append(
                {
                    "path": _render_relative_path(current_path, resolved.root),
                    "type": "dir" if current_path.is_dir() else "file",
                }
            )
    return {
        "ok": True,
        "root": str(resolved.root),
        "path": _render_relative_path(resolved.path, resolved.root),
        "recursive": recursive,
        "entries": entries,
        "truncated": len(entries) >= max_entries,
    }


@workspace_server.tool(
    description="Read one text file, optionally by line range.",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
)
def read_file(
    path: str,
    cwd: str | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
) -> dict[str, Any]:
    """Read one UTF-8 text file from disk."""
    resolved = _resolve_workspace_path(path, cwd=cwd)
    if not resolved.path.is_file():
        raise ValueError(f"Path '{resolved.path}' is not a file.")
    if start_line is not None and start_line <= 0:
        raise ValueError("Tool 'read_file' field 'start_line' must be positive when provided.")
    if end_line is not None and end_line <= 0:
        raise ValueError("Tool 'read_file' field 'end_line' must be positive when provided.")
    if start_line is not None and end_line is not None and end_line < start_line:
        raise ValueError("Tool 'read_file' field 'end_line' must be >= 'start_line'.")

    file_lines = resolved.path.read_text(encoding="utf-8").splitlines()
    slice_start = 0 if start_line is None else start_line - 1
    slice_end = len(file_lines) if end_line is None else end_line
    selected_lines = file_lines[slice_start:slice_end]
    return {
        "ok": True,
        "path": _render_relative_path(resolved.path, resolved.root),
        "line_start": slice_start + 1 if selected_lines else start_line,
        "line_end": slice_start + len(selected_lines) if selected_lines else start_line,
        "content": "\n".join(selected_lines),
    }


@workspace_server.tool(
    description="Search text across files under one path.",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
)
def search_text(
    pattern: str,
    path: str = ".",
    cwd: str | None = None,
    glob: str | None = None,
    case_sensitive: bool = False,
    max_matches: int = 200,
) -> dict[str, Any]:
    """Search file contents with a regular expression pattern."""
    if not pattern:
        raise ValueError("Tool 'search_text' field 'pattern' must be a non-empty string.")
    if max_matches <= 0:
        raise ValueError("Tool 'search_text' field 'max_matches' must be a positive integer.")
    resolved = _resolve_workspace_path(path, cwd=cwd)
    if not resolved.path.exists():
        raise ValueError(f"Path '{resolved.path}' does not exist.")

    candidate_files = _iter_candidate_files(resolved.path, glob=glob)
    regex_flags = 0 if case_sensitive else re.IGNORECASE
    compiled_pattern = re.compile(pattern, regex_flags)
    matches: list[dict[str, Any]] = []
    for candidate_file in candidate_files:
        try:
            file_lines = candidate_file.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(file_lines, start=1):
            if compiled_pattern.search(line) is None:
                continue
            matches.append(
                {
                    "path": _render_relative_path(candidate_file, resolved.root),
                    "line": line_number,
                    "text": line,
                }
            )
            if len(matches) >= max_matches:
                return {
                    "ok": True,
                    "matches": matches,
                    "truncated": True,
                }
    return {
        "ok": True,
        "matches": matches,
        "truncated": False,
    }


@workspace_server.tool(
    description="Write one text file, replacing or appending content.",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
    ),
)
def write_file(
    path: str,
    content: str,
    cwd: str | None = None,
    append: bool = False,
    create_dirs: bool = True,
) -> dict[str, Any]:
    """Write text content to one file."""
    resolved = _resolve_workspace_path(path, cwd=cwd)
    if create_dirs:
        resolved.path.parent.mkdir(parents=True, exist_ok=True)
    file_mode = "a" if append else "w"
    with resolved.path.open(file_mode, encoding="utf-8") as output_file:
        output_file.write(content)
    return {
        "ok": True,
        "path": _render_relative_path(resolved.path, resolved.root),
        "bytes_written": len(content.encode("utf-8")),
        "append": append,
    }


@workspace_server.tool(
    description="Create directories recursively.",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
    ),
)
def make_dirs(path: str, cwd: str | None = None) -> dict[str, Any]:
    """Create a directory and all missing parents."""
    resolved = _resolve_workspace_path(path, cwd=cwd)
    resolved.path.mkdir(parents=True, exist_ok=True)
    return {
        "ok": True,
        "path": _render_relative_path(resolved.path, resolved.root),
    }


@workspace_server.tool(
    description="Return file metadata for one path.",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
)
def stat_file(path: str, cwd: str | None = None) -> dict[str, Any]:
    """Return metadata for one path when it exists."""
    resolved = _resolve_workspace_path(path, cwd=cwd)
    if not resolved.path.exists():
        raise ValueError(f"Path '{resolved.path}' does not exist.")
    stat_result = resolved.path.stat()
    return {
        "ok": True,
        "path": _render_relative_path(resolved.path, resolved.root),
        "type": "dir" if resolved.path.is_dir() else "file",
        "size": stat_result.st_size,
    }


@workspace_server.tool(
    description="Delete one file from the workspace.",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
    ),
)
def delete_file(path: str, cwd: str | None = None) -> dict[str, Any]:
    """Delete one file when it exists."""
    resolved = _resolve_workspace_path(path, cwd=cwd)
    if not resolved.path.is_file():
        raise ValueError(f"Path '{resolved.path}' is not a file.")
    resolved.path.unlink()
    return {
        "ok": True,
        "path": _render_relative_path(resolved.path, resolved.root),
    }


@workspace_server.tool(
    description="Move or rename one file.",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
    ),
)
def move_file(
    source_path: str,
    destination_path: str,
    cwd: str | None = None,
    create_dirs: bool = True,
) -> dict[str, Any]:
    """Move one file to a new location."""
    resolved_source = _resolve_workspace_path(source_path, cwd=cwd)
    resolved_destination = _resolve_workspace_path(destination_path, cwd=cwd)
    if not resolved_source.path.exists():
        raise ValueError(f"Path '{resolved_source.path}' does not exist.")
    if create_dirs:
        resolved_destination.path.parent.mkdir(parents=True, exist_ok=True)
    resolved_source.path.replace(resolved_destination.path)
    return {
        "ok": True,
        "source_path": _render_relative_path(resolved_source.path, resolved_source.root),
        "destination_path": _render_relative_path(resolved_destination.path, resolved_destination.root),
    }


@workspace_server.tool(
    description="Apply a Codex-style patch to one or more files.",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
    ),
)
def apply_patch(patch: str, cwd: str | None = None) -> dict[str, Any]:
    """Apply one high-level patch envelope to files under the selected root."""
    if not patch.strip():
        raise ValueError("Tool 'apply_patch' field 'patch' must be a non-empty string.")
    result = apply_workspace_patch(patch, cwd=cwd)
    return {
        "ok": True,
        "files_changed": result["files_changed"],
    }


def apply_workspace_patch(patch: str, cwd: str | None = None) -> dict[str, Any]:
    """Apply a Codex-style patch and return a summary."""
    parser = PatchParser(patch)
    operations = parser.parse()
    root = _resolve_root(cwd)
    changed_files: list[str] = []
    for operation in operations:
        if operation.kind == "add":
            target_path = _resolve_workspace_path(operation.path, cwd=str(root)).path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            _write_patch_lines(target_path, operation.new_lines)
            changed_files.append(_render_relative_path(target_path, root))
            continue
        if operation.kind == "delete":
            target_path = _resolve_workspace_path(operation.path, cwd=str(root)).path
            if not target_path.exists():
                raise ValueError(f"Patch delete target '{target_path}' does not exist.")
            target_path.unlink()
            changed_files.append(_render_relative_path(target_path, root))
            continue

        source_path = _resolve_workspace_path(operation.path, cwd=str(root)).path
        if not source_path.exists():
            raise ValueError(f"Patch update target '{source_path}' does not exist.")
        original_lines = source_path.read_text(encoding="utf-8").splitlines()
        updated_lines = _apply_patch_hunks(original_lines, operation.hunks, str(source_path))
        destination_path = source_path
        if operation.move_to is not None:
            destination_path = _resolve_workspace_path(operation.move_to, cwd=str(root)).path
            destination_path.parent.mkdir(parents=True, exist_ok=True)
        _write_patch_lines(destination_path, updated_lines)
        if operation.move_to is not None and destination_path != source_path:
            source_path.unlink()
            changed_files.append(_render_relative_path(source_path, root))
        changed_files.append(_render_relative_path(destination_path, root))
    return {
        "files_changed": _dedupe_preserve_order(changed_files),
    }


def _apply_patch_hunks(
    original_lines: list[str],
    hunks: list[list[str]],
    file_label: str,
) -> list[str]:
    """Apply parsed patch hunks to one list of file lines."""
    current_index = 0
    updated_lines: list[str] = []
    for hunk_lines in hunks:
        original_fragment = [line[1:] for line in hunk_lines if line and line[0] in {" ", "-"}]
        new_fragment = [line[1:] for line in hunk_lines if line and line[0] in {" ", "+"}]
        if not original_fragment:
            updated_lines.extend(new_fragment)
            continue
        match_index = _find_subsequence(original_lines, original_fragment, start_index=current_index)
        if match_index < 0:
            raise ValueError(f"Patch hunk did not match file '{file_label}'.")
        updated_lines.extend(original_lines[current_index:match_index])
        updated_lines.extend(new_fragment)
        current_index = match_index + len(original_fragment)
    updated_lines.extend(original_lines[current_index:])
    return updated_lines


def _find_subsequence(haystack: list[str], needle: list[str], *, start_index: int) -> int:
    """Return the first index where one line subsequence appears."""
    if not needle:
        return start_index
    maximum_index = len(haystack) - len(needle)
    for current_index in range(start_index, maximum_index + 1):
        if haystack[current_index : current_index + len(needle)] == needle:
            return current_index
    return -1


def _write_patch_lines(target_path: Path, lines: list[str]) -> None:
    """Write patch output lines back to disk with a trailing newline when non-empty."""
    content = "\n".join(lines)
    if lines:
        content += "\n"
    target_path.write_text(content, encoding="utf-8")


def _iter_candidate_files(path: Path, *, glob: str | None) -> tuple[Path, ...]:
    """Return file candidates for a text search request."""
    if path.is_file():
        return (path,)
    if glob:
        return tuple(sorted(candidate for candidate in _safe_rglob(path, pattern=glob) if candidate.is_file()))
    return tuple(sorted(candidate for candidate in _safe_rglob(path) if candidate.is_file()))


def _safe_rglob(root: Path, pattern: str = "*") -> list[Path]:
    """Recursive glob that skips known junk directories."""
    results: list[Path] = []
    for entry in sorted(root.rglob(pattern)):
        # Skip entries inside junk directories (check entry name + all parent names)
        names = {entry.name} | {p.name for p in entry.relative_to(root).parents if p.name}
        if names & _SKIP_DIRS:
            continue
        results.append(entry)
    return results


def _resolve_workspace_path(path: str, *, cwd: str | None) -> WorkspacePath:
    """Resolve one user-supplied path against an optional current working directory."""
    root = _resolve_root(cwd)
    candidate_path = Path(path).expanduser()
    if not candidate_path.is_absolute():
        candidate_path = root / candidate_path
    return WorkspacePath(root=root, path=candidate_path.resolve(strict=False))


def _resolve_root(cwd: str | None) -> Path:
    """Resolve one optional cwd string into an absolute directory path."""
    if cwd is None:
        return Path.cwd().resolve()
    return Path(cwd).expanduser().resolve(strict=False)


def _render_relative_path(path: Path, root: Path) -> str:
    """Return one path relative to the selected root when possible."""
    try:
        relative_path = path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return str(path.resolve(strict=False))
    normalized_relative = str(relative_path)
    return "." if not normalized_relative else normalized_relative


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    """Return de-duplicated strings in original order."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


@dataclass(slots=True)
class PatchOperation:
    """Describe one parsed patch file operation."""

    kind: str
    path: str
    move_to: str | None = None
    new_lines: list[str] | None = None
    hunks: list[list[str]] | None = None


class PatchParser:
    """Parse the stripped-down patch envelope used by Codex-style file edits."""

    def __init__(self, patch: str) -> None:
        """Store the patch text as a list of normalized lines."""
        self._lines = patch.splitlines()
        self._index = 0

    def parse(self) -> list[PatchOperation]:
        """Parse the full patch payload into file operations."""
        self._expect_line("*** Begin Patch")
        operations: list[PatchOperation] = []
        while self._index < len(self._lines):
            current_line = self._peek_line()
            if current_line == "*** End Patch":
                self._index += 1
                if self._index != len(self._lines):
                    raise ValueError("Patch contained trailing content after '*** End Patch'.")
                return operations
            if current_line.startswith("*** Add File: "):
                operations.append(self._parse_add_file())
                continue
            if current_line.startswith("*** Delete File: "):
                operations.append(self._parse_delete_file())
                continue
            if current_line.startswith("*** Update File: "):
                operations.append(self._parse_update_file())
                continue
            raise ValueError(f"Unsupported patch line '{current_line}'.")
        raise ValueError("Patch is missing '*** End Patch'.")

    def _parse_add_file(self) -> PatchOperation:
        """Parse one add-file block."""
        path = self._consume_line().removeprefix("*** Add File: ").strip()
        new_lines: list[str] = []
        while self._index < len(self._lines):
            current_line = self._peek_line()
            if current_line.startswith("*** "):
                break
            if not current_line.startswith("+"):
                raise ValueError("Add-file blocks may only contain '+' lines.")
            new_lines.append(self._consume_line()[1:])
        return PatchOperation(kind="add", path=path, new_lines=new_lines)

    def _parse_delete_file(self) -> PatchOperation:
        """Parse one delete-file block."""
        path = self._consume_line().removeprefix("*** Delete File: ").strip()
        return PatchOperation(kind="delete", path=path)

    def _parse_update_file(self) -> PatchOperation:
        """Parse one update-file block with one or more hunks."""
        path = self._consume_line().removeprefix("*** Update File: ").strip()
        move_to: str | None = None
        if self._index < len(self._lines) and self._peek_line().startswith("*** Move to: "):
            move_to = self._consume_line().removeprefix("*** Move to: ").strip()
        hunks: list[list[str]] = []
        current_hunk: list[str] = []
        while self._index < len(self._lines):
            current_line = self._peek_line()
            if current_line == "*** End of File":
                self._index += 1
                continue
            if current_line.startswith("*** "):
                break
            if current_line.startswith("@@"):
                if current_hunk:
                    hunks.append(current_hunk)
                    current_hunk = []
                self._index += 1
                continue
            if not current_line or current_line[0] not in {" ", "+", "-"}:
                raise ValueError(f"Unsupported patch hunk line '{current_line}'.")
            current_hunk.append(self._consume_line())
        if current_hunk:
            hunks.append(current_hunk)
        if not hunks:
            raise ValueError(f"Update-file block for '{path}' did not contain any hunks.")
        return PatchOperation(kind="update", path=path, move_to=move_to, hunks=hunks)

    def _expect_line(self, expected_line: str) -> None:
        """Consume one exact line or raise a validation error."""
        actual_line = self._consume_line()
        if actual_line != expected_line:
            raise ValueError(f"Expected patch line '{expected_line}', got '{actual_line}'.")

    def _consume_line(self) -> str:
        """Return the current line and advance the parser."""
        if self._index >= len(self._lines):
            raise ValueError("Patch ended unexpectedly.")
        current_line = self._lines[self._index]
        self._index += 1
        return current_line

    def _peek_line(self) -> str:
        """Return the current line without advancing the parser."""
        if self._index >= len(self._lines):
            raise ValueError("Patch ended unexpectedly.")
        return self._lines[self._index]


def main() -> None:
    """Run the workspace MCP server over stdio."""
    build_workspace_server().run(transport="stdio")


if __name__ == "__main__":
    main()
