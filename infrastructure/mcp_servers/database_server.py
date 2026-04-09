from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations


database_server = FastMCP("openharness-database", log_level="ERROR")

_SQLITE_MAGIC_HEADER = b"SQLite format 3\x00"
_SQLITE_EXTENSIONS = {".db", ".sqlite", ".sqlite3"}
_READONLY_QUERY_PREFIXES = ("select", "with", "pragma", "explain")


def build_database_server() -> FastMCP:
    """Return the configured database MCP server instance."""
    return database_server


@database_server.tool(
    description="Find SQLite database files under one path.",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
)
def find_sqlite_databases(
    path: str = ".",
    cwd: str | None = None,
    recursive: bool = True,
    max_entries: int = 100,
) -> dict[str, Any]:
    """Find SQLite database files under one path."""
    if max_entries <= 0:
        raise ValueError("Tool 'find_sqlite_databases' field 'max_entries' must be a positive integer.")
    root = _resolve_root(cwd)
    search_path = _resolve_database_path(path, cwd=cwd, require_exists=True)
    if not search_path.is_dir():
        raise ValueError(f"Path '{search_path}' is not a directory.")

    iterator = search_path.rglob("*") if recursive else search_path.iterdir()
    matches: list[dict[str, Any]] = []
    for candidate_path in sorted(iterator):
        if not candidate_path.is_file():
            continue
        if not _is_sqlite_database_file(candidate_path):
            continue
        matches.append(
            {
                "path": _render_relative_path(candidate_path, root),
                "size": candidate_path.stat().st_size,
            }
        )
        if len(matches) >= max_entries:
            break
    return {
        "ok": True,
        "path": _render_relative_path(search_path, root),
        "recursive": recursive,
        "databases": matches,
        "truncated": len(matches) >= max_entries,
    }


@database_server.tool(
    description="Describe tables, views, indexes, and triggers in one SQLite database.",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
)
def describe_database_schema(db_path: str, cwd: str | None = None) -> dict[str, Any]:
    """Describe the schema for one SQLite database."""
    database_path = _resolve_database_path(db_path, cwd=cwd, require_exists=True)
    with _connect_database(database_path) as connection:
        rows = connection.execute(
            """
            SELECT type, name, tbl_name, sql
            FROM sqlite_master
            WHERE name NOT LIKE 'sqlite_%'
            ORDER BY type, name
            """
        ).fetchall()
    return {
        "ok": True,
        "db_path": str(database_path),
        "objects": [
            {
                "type": row["type"],
                "name": row["name"],
                "table_name": row["tbl_name"],
                "sql": row["sql"],
            }
            for row in rows
        ],
    }


@database_server.tool(
    description="Describe columns, indexes, and foreign keys for one SQLite table.",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
)
def describe_table_schema(
    db_path: str,
    table_name: str,
    cwd: str | None = None,
) -> dict[str, Any]:
    """Describe one table schema from one SQLite database."""
    database_path = _resolve_database_path(db_path, cwd=cwd, require_exists=True)
    normalized_table_name = _normalize_required_string(table_name, field_name="table_name")
    with _connect_database(database_path) as connection:
        columns = connection.execute(f"PRAGMA table_info({_quote_identifier(normalized_table_name)})").fetchall()
        foreign_keys = connection.execute(
            f"PRAGMA foreign_key_list({_quote_identifier(normalized_table_name)})"
        ).fetchall()
        indexes = connection.execute(f"PRAGMA index_list({_quote_identifier(normalized_table_name)})").fetchall()
    if not columns:
        raise ValueError(f"Table '{normalized_table_name}' does not exist in '{database_path}'.")
    return {
        "ok": True,
        "db_path": str(database_path),
        "table_name": normalized_table_name,
        "columns": [
            {
                "cid": row["cid"],
                "name": row["name"],
                "type": row["type"],
                "notnull": bool(row["notnull"]),
                "default_value": row["dflt_value"],
                "primary_key_position": row["pk"],
            }
            for row in columns
        ],
        "foreign_keys": [dict(row) for row in foreign_keys],
        "indexes": [dict(row) for row in indexes],
    }


@database_server.tool(
    description="Run a read-only SQL query against one SQLite database.",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
)
def query_sql(
    db_path: str,
    sql: str,
    params: list[Any] | None = None,
    cwd: str | None = None,
    max_rows: int = 200,
) -> dict[str, Any]:
    """Run one read-only SQL query and return rows."""
    database_path = _resolve_database_path(db_path, cwd=cwd, require_exists=True)
    normalized_sql = _normalize_required_string(sql, field_name="sql")
    if max_rows <= 0:
        raise ValueError("Tool 'query_sql' field 'max_rows' must be a positive integer.")
    normalized_params = _normalize_query_params(params)
    _ensure_sql_is_readonly(normalized_sql)

    with _connect_database(database_path) as connection:
        cursor = connection.execute(normalized_sql, normalized_params)
        column_names = tuple(item[0] for item in (cursor.description or ()))
        rows = cursor.fetchmany(max_rows + 1)

    truncated = len(rows) > max_rows
    rows = rows[:max_rows]
    return {
        "ok": True,
        "db_path": str(database_path),
        "sql": normalized_sql,
        "params": list(normalized_params),
        "columns": list(column_names),
        "rows": [_normalize_row(row, column_names) for row in rows],
        "row_count": len(rows),
        "truncated": truncated,
    }


@database_server.tool(
    description="Execute SQL statements against one SQLite database and commit the transaction.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False),
)
def execute_sql(
    db_path: str,
    sql: str,
    params: list[Any] | None = None,
    cwd: str | None = None,
) -> dict[str, Any]:
    """Execute SQL statements and commit the transaction."""
    database_path = _resolve_database_path(db_path, cwd=cwd, require_exists=False)
    normalized_sql = _normalize_required_string(sql, field_name="sql")
    normalized_params = _normalize_query_params(params)
    database_path.parent.mkdir(parents=True, exist_ok=True)

    with _connect_database(database_path) as connection:
        before_changes = connection.total_changes
        if normalized_params:
            cursor = connection.execute(normalized_sql, normalized_params)
            returned_rows = cursor.fetchall() if cursor.description is not None else []
            column_names = tuple(item[0] for item in (cursor.description or ()))
            last_row_id = cursor.lastrowid
        else:
            if _contains_multiple_statements(normalized_sql):
                connection.executescript(normalized_sql)
                returned_rows = []
                column_names = ()
                last_row_id = None
            else:
                cursor = connection.execute(normalized_sql)
                returned_rows = cursor.fetchall() if cursor.description is not None else []
                column_names = tuple(item[0] for item in (cursor.description or ()))
                last_row_id = cursor.lastrowid
        connection.commit()
        changes = connection.total_changes - before_changes

    return {
        "ok": True,
        "db_path": str(database_path),
        "sql": normalized_sql,
        "params": list(normalized_params),
        "changes": changes,
        "last_row_id": last_row_id,
        "columns": list(column_names),
        "rows": [_normalize_row(row, column_names) for row in returned_rows],
    }


def _connect_database(path: Path) -> sqlite3.Connection:
    """Return a SQLite connection configured for row access."""
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _normalize_required_string(value: str, *, field_name: str) -> str:
    """Return one validated non-empty string."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Tool field '{field_name}' must be a non-empty string.")
    return value.strip()


def _normalize_query_params(params: list[Any] | None) -> tuple[Any, ...]:
    """Return one normalized positional parameter tuple."""
    if params is None:
        return ()
    if not isinstance(params, list):
        raise ValueError("Tool field 'params' must be a list when provided.")
    return tuple(params)


def _ensure_sql_is_readonly(sql: str) -> None:
    """Reject statements that are not clearly read-only."""
    normalized_sql = sql.strip().lstrip("(").lower()
    if not normalized_sql.startswith(_READONLY_QUERY_PREFIXES):
        raise ValueError("Tool 'query_sql' only supports read-only SELECT/WITH/PRAGMA/EXPLAIN statements.")
    if _contains_multiple_statements(sql):
        raise ValueError("Tool 'query_sql' only supports a single SQL statement.")


def _contains_multiple_statements(sql: str) -> bool:
    """Return whether one SQL string contains multiple statements."""
    statements = [statement.strip() for statement in sql.split(";") if statement.strip()]
    return len(statements) > 1


def _normalize_row(row: sqlite3.Row | tuple[Any, ...], column_names: tuple[str, ...]) -> dict[str, Any]:
    """Return one JSON-serializable row mapping."""
    if isinstance(row, sqlite3.Row):
        return {key: _normalize_sql_value(row[key]) for key in row.keys()}
    return {
        column_name: _normalize_sql_value(value)
        for column_name, value in zip(column_names, row, strict=False)
    }


def _normalize_sql_value(value: Any) -> Any:
    """Return one JSON-serializable SQL value."""
    if isinstance(value, bytes):
        return value.hex()
    return value


def _quote_identifier(identifier: str) -> str:
    """Return one safely quoted SQLite identifier."""
    return '"' + identifier.replace('"', '""') + '"'


def _resolve_root(cwd: str | None) -> Path:
    """Return the effective root directory for relative database paths."""
    if cwd is None:
        return Path.cwd().resolve()
    return Path(cwd).expanduser().resolve(strict=False)


def _resolve_database_path(db_path: str, *, cwd: str | None, require_exists: bool) -> Path:
    """Resolve one database file or directory path."""
    normalized_path = _normalize_required_string(db_path, field_name="db_path")
    root = _resolve_root(cwd)
    candidate_path = Path(normalized_path).expanduser()
    if not candidate_path.is_absolute():
        candidate_path = root / candidate_path
    resolved_path = candidate_path.resolve(strict=False)
    if require_exists and not resolved_path.exists():
        raise ValueError(f"Path '{resolved_path}' does not exist.")
    return resolved_path


def _render_relative_path(path: Path, root: Path) -> str:
    """Return one path relative to the selected root when possible."""
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _is_sqlite_database_file(path: Path) -> bool:
    """Return whether one path appears to be a SQLite database."""
    if path.suffix.lower() in _SQLITE_EXTENSIONS:
        return True
    try:
        with path.open("rb") as input_file:
            return input_file.read(len(_SQLITE_MAGIC_HEADER)) == _SQLITE_MAGIC_HEADER
    except OSError:
        return False


def main() -> None:
    """Run the database MCP server over stdio."""
    build_database_server().run(transport="stdio")


if __name__ == "__main__":
    main()
