from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover - exercised through fallback behavior in tests
    PlaywrightError = RuntimeError
    PlaywrightTimeoutError = TimeoutError
    sync_playwright = None


browser_server = FastMCP("openharness-browser", log_level="ERROR")

_SUPPORTED_BROWSERS = ("chromium", "firefox", "webkit")
_SESSIONS: dict[str, BrowserSession] = {}
_SESSIONS_LOCK = Lock()


@dataclass(slots=True)
class BrowserSession:
    """Track one long-lived Playwright browser session."""

    playwright: Any
    browser: Any
    context: Any
    page: Any
    browser_name: str
    headless: bool


def build_browser_server() -> FastMCP:
    """Return the configured browser MCP server instance."""
    return browser_server


@browser_server.tool(
    description="Fetch one web page through Playwright and return normalized text content.",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True),
)
def fetch_browser_page(
    url: str,
    browser: str = "chromium",
    headless: bool = True,
    timeout_ms: int = 15_000,
    wait_until: str = "load",
    max_chars: int = 20_000,
) -> dict[str, Any]:
    """Fetch one page with a short-lived browser session."""
    normalized_url = _normalize_required_string(url, field_name="url")
    normalized_browser = _normalize_browser_name(browser)
    _validate_timeout(timeout_ms, field_name="timeout_ms")
    _validate_positive_int(max_chars, field_name="max_chars")
    normalized_wait_until = _normalize_wait_until(wait_until)

    session = _create_browser_session(
        browser_name=normalized_browser,
        headless=headless,
    )
    try:
        _goto_page(
            page=session.page,
            url=normalized_url,
            timeout_ms=timeout_ms,
            wait_until=normalized_wait_until,
        )
        snapshot = _build_page_snapshot(session.page, max_chars=max_chars)
    finally:
        _close_browser_artifacts(session)
    return {
        "ok": True,
        "browser": normalized_browser,
        "headless": headless,
        **snapshot,
    }


@browser_server.tool(
    description="Open a long-lived Playwright browser session and optionally navigate to one URL.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True),
)
def open_browser_session(
    start_url: str | None = None,
    browser: str = "chromium",
    headless: bool = True,
    viewport_width: int = 1280,
    viewport_height: int = 800,
    timeout_ms: int = 15_000,
    wait_until: str = "load",
) -> dict[str, Any]:
    """Open one browser session and return a stable session id."""
    normalized_browser = _normalize_browser_name(browser)
    _validate_positive_int(viewport_width, field_name="viewport_width")
    _validate_positive_int(viewport_height, field_name="viewport_height")
    _validate_timeout(timeout_ms, field_name="timeout_ms")
    normalized_wait_until = _normalize_wait_until(wait_until)
    normalized_start_url = start_url.strip() if isinstance(start_url, str) and start_url.strip() else None

    session = _create_browser_session(
        browser_name=normalized_browser,
        headless=headless,
        viewport_width=viewport_width,
        viewport_height=viewport_height,
    )
    session_id = str(uuid4())
    try:
        if normalized_start_url is not None:
            _goto_page(
                page=session.page,
                url=normalized_start_url,
                timeout_ms=timeout_ms,
                wait_until=normalized_wait_until,
            )
        with _SESSIONS_LOCK:
            _SESSIONS[session_id] = session
    except Exception:
        _close_browser_artifacts(session)
        raise
    return {
        "ok": True,
        "session_id": session_id,
        "browser": normalized_browser,
        "headless": headless,
        "url": _safe_page_url(session.page),
        "title": _safe_page_title(session.page),
    }


@browser_server.tool(
    description="Navigate one existing browser session to a new URL.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True),
)
def navigate_browser_session(
    session_id: str,
    url: str,
    timeout_ms: int = 15_000,
    wait_until: str = "load",
    max_chars: int = 20_000,
) -> dict[str, Any]:
    """Navigate one session and return the latest page snapshot."""
    session = _get_required_session(session_id)
    normalized_url = _normalize_required_string(url, field_name="url")
    _validate_timeout(timeout_ms, field_name="timeout_ms")
    _validate_positive_int(max_chars, field_name="max_chars")
    normalized_wait_until = _normalize_wait_until(wait_until)
    _goto_page(session.page, normalized_url, timeout_ms=timeout_ms, wait_until=normalized_wait_until)
    return {
        "ok": True,
        "session_id": session_id,
        **_build_page_snapshot(session.page, max_chars=max_chars),
    }


@browser_server.tool(
    description="Click one element in an existing browser session.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True),
)
def click_browser_selector(
    session_id: str,
    selector: str,
    timeout_ms: int = 10_000,
) -> dict[str, Any]:
    """Click one selector in one browser session."""
    session = _get_required_session(session_id)
    normalized_selector = _normalize_required_string(selector, field_name="selector")
    _validate_timeout(timeout_ms, field_name="timeout_ms")
    try:
        session.page.click(normalized_selector, timeout=timeout_ms)
    except (PlaywrightError, PlaywrightTimeoutError) as error:
        raise ValueError(f"Failed to click selector '{normalized_selector}': {error}") from error
    return {
        "ok": True,
        "session_id": session_id,
        "selector": normalized_selector,
        "url": _safe_page_url(session.page),
        "title": _safe_page_title(session.page),
    }


@browser_server.tool(
    description="Fill one input element in an existing browser session.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True),
)
def fill_browser_selector(
    session_id: str,
    selector: str,
    value: str,
    timeout_ms: int = 10_000,
) -> dict[str, Any]:
    """Fill one selector in one browser session."""
    session = _get_required_session(session_id)
    normalized_selector = _normalize_required_string(selector, field_name="selector")
    if not isinstance(value, str):
        raise ValueError("Tool field 'value' must be a string.")
    _validate_timeout(timeout_ms, field_name="timeout_ms")
    try:
        session.page.fill(normalized_selector, value, timeout=timeout_ms)
    except (PlaywrightError, PlaywrightTimeoutError) as error:
        raise ValueError(f"Failed to fill selector '{normalized_selector}': {error}") from error
    return {
        "ok": True,
        "session_id": session_id,
        "selector": normalized_selector,
        "chars_written": len(value),
    }


@browser_server.tool(
    description="Query one selector in an existing browser session and return matching text and key attributes.",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True),
)
def query_browser_selector(
    session_id: str,
    selector: str,
    max_items: int = 20,
) -> dict[str, Any]:
    """Return one selector query result from one browser session."""
    session = _get_required_session(session_id)
    normalized_selector = _normalize_required_string(selector, field_name="selector")
    _validate_positive_int(max_items, field_name="max_items")
    elements = session.page.query_selector_all(normalized_selector)
    items: list[dict[str, Any]] = []
    for element in elements[:max_items]:
        items.append(
            {
                "text": _normalize_optional_text(_playwright_call(element, "inner_text")),
                "value": _normalize_optional_text(_playwright_call(element, "get_attribute", "value")),
                "href": _normalize_optional_text(_playwright_call(element, "get_attribute", "href")),
                "src": _normalize_optional_text(_playwright_call(element, "get_attribute", "src")),
            }
        )
    return {
        "ok": True,
        "session_id": session_id,
        "selector": normalized_selector,
        "items": items,
        "count": len(elements),
        "truncated": len(elements) > max_items,
    }


@browser_server.tool(
    description="Inspect the current page loaded in one browser session.",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True),
)
def inspect_browser_session(
    session_id: str,
    max_chars: int = 20_000,
) -> dict[str, Any]:
    """Return the current page snapshot for one browser session."""
    session = _get_required_session(session_id)
    _validate_positive_int(max_chars, field_name="max_chars")
    return {
        "ok": True,
        "session_id": session_id,
        **_build_page_snapshot(session.page, max_chars=max_chars),
    }


@browser_server.tool(
    description="Save a screenshot from one browser session to a file path.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True),
)
def take_browser_screenshot(
    session_id: str,
    path: str,
    cwd: str | None = None,
    full_page: bool = True,
) -> dict[str, Any]:
    """Save one screenshot from one browser session."""
    session = _get_required_session(session_id)
    output_path = _resolve_output_path(path, cwd=cwd)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        session.page.screenshot(path=str(output_path), full_page=full_page)
    except (PlaywrightError, PlaywrightTimeoutError) as error:
        raise ValueError(f"Failed to capture screenshot to '{output_path}': {error}") from error
    return {
        "ok": True,
        "session_id": session_id,
        "path": str(output_path),
        "full_page": full_page,
    }


@browser_server.tool(
    description="Close one existing browser session and release Playwright resources.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True),
)
def close_browser_session(session_id: str) -> dict[str, Any]:
    """Close one browser session."""
    with _SESSIONS_LOCK:
        session = _SESSIONS.pop(session_id, None)
    if session is None:
        raise ValueError(f"No browser session '{session_id}' is active.")
    _close_browser_artifacts(session)
    return {
        "ok": True,
        "session_id": session_id,
    }


def _create_browser_session(
    *,
    browser_name: str,
    headless: bool,
    viewport_width: int = 1280,
    viewport_height: int = 800,
) -> BrowserSession:
    """Create one Playwright browser session."""
    factory = _require_playwright_factory()
    playwright = factory().start()
    try:
        browser_type = getattr(playwright, browser_name, None)
        if browser_type is None:
            raise ValueError(f"Unsupported browser '{browser_name}'.")
        browser = browser_type.launch(headless=headless)
        context = browser.new_context(
            viewport={
                "width": viewport_width,
                "height": viewport_height,
            }
        )
        page = context.new_page()
        return BrowserSession(
            playwright=playwright,
            browser=browser,
            context=context,
            page=page,
            browser_name=browser_name,
            headless=headless,
        )
    except Exception:
        try:
            playwright.stop()
        except Exception:
            pass
        raise


def _close_browser_artifacts(session: BrowserSession) -> None:
    """Close one browser session and ignore secondary cleanup errors."""
    for closer in (
        getattr(session.context, "close", None),
        getattr(session.browser, "close", None),
        getattr(session.playwright, "stop", None),
    ):
        if closer is None:
            continue
        try:
            closer()
        except Exception:
            continue


def _get_required_session(session_id: str) -> BrowserSession:
    """Return one active browser session."""
    with _SESSIONS_LOCK:
        session = _SESSIONS.get(session_id)
    if session is None:
        raise ValueError(f"No browser session '{session_id}' is active.")
    return session


def _require_playwright_factory() -> Any:
    """Return the Playwright sync factory or raise an installation error."""
    if sync_playwright is None:
        raise ValueError(
            "Playwright is not installed. Install dependencies with `pip install -r requirements.txt` "
            "and run `playwright install chromium` before using the browser MCP server."
        )
    return sync_playwright


def _goto_page(page: Any, url: str, *, timeout_ms: int, wait_until: str) -> None:
    """Navigate one Playwright page with normalized error reporting."""
    try:
        page.goto(url, timeout=timeout_ms, wait_until=wait_until)
    except (PlaywrightError, PlaywrightTimeoutError) as error:
        raise ValueError(f"Failed to navigate to '{url}': {error}") from error


def _build_page_snapshot(page: Any, *, max_chars: int) -> dict[str, Any]:
    """Return a normalized page snapshot."""
    content = _extract_body_text(page)
    truncated = len(content) > max_chars
    if truncated:
        content = content[:max_chars]
    return {
        "url": _safe_page_url(page),
        "title": _safe_page_title(page),
        "content": content,
        "truncated": truncated,
    }


def _extract_body_text(page: Any) -> str:
    """Return the visible page body text when available."""
    try:
        locator = page.locator("body")
        text = locator.inner_text()
    except Exception:
        return ""
    if not isinstance(text, str):
        return ""
    return text


def _safe_page_url(page: Any) -> str | None:
    """Return the current page URL when available."""
    url = getattr(page, "url", None)
    if isinstance(url, str) and url:
        return url
    return None


def _safe_page_title(page: Any) -> str | None:
    """Return the current page title when available."""
    try:
        title = page.title()
    except Exception:
        return None
    if not isinstance(title, str) or not title.strip():
        return None
    return title


def _playwright_call(target: Any, method_name: str, *args: Any) -> Any:
    """Call one Playwright method and suppress element-specific lookup failures."""
    method = getattr(target, method_name, None)
    if method is None:
        return None
    try:
        return method(*args)
    except Exception:
        return None


def _normalize_browser_name(browser: str) -> str:
    """Return one validated browser engine name."""
    normalized_browser = _normalize_required_string(browser, field_name="browser").lower()
    if normalized_browser not in _SUPPORTED_BROWSERS:
        raise ValueError(
            "Tool field 'browser' must be one of: " + ", ".join(_SUPPORTED_BROWSERS) + "."
        )
    return normalized_browser


def _normalize_wait_until(wait_until: str) -> str:
    """Return one validated Playwright wait-until mode."""
    normalized_wait_until = _normalize_required_string(wait_until, field_name="wait_until").lower()
    if normalized_wait_until not in {"commit", "domcontentloaded", "load", "networkidle"}:
        raise ValueError(
            "Tool field 'wait_until' must be one of: commit, domcontentloaded, load, networkidle."
        )
    return normalized_wait_until


def _normalize_required_string(value: str, *, field_name: str) -> str:
    """Return one validated non-empty string."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Tool field '{field_name}' must be a non-empty string.")
    return value.strip()


def _normalize_optional_text(value: Any) -> str | None:
    """Return one optional normalized string."""
    if not isinstance(value, str):
        return None
    normalized_value = value.strip()
    return normalized_value or None


def _validate_positive_int(value: int, *, field_name: str) -> None:
    """Validate one positive integer field."""
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"Tool field '{field_name}' must be a positive integer.")


def _validate_timeout(value: int, *, field_name: str) -> None:
    """Validate one positive timeout field."""
    _validate_positive_int(value, field_name=field_name)


def _resolve_output_path(path: str, *, cwd: str | None) -> Path:
    """Resolve one screenshot output path."""
    normalized_path = _normalize_required_string(path, field_name="path")
    root = Path.cwd().resolve() if cwd is None else Path(cwd).expanduser().resolve(strict=False)
    candidate_path = Path(normalized_path).expanduser()
    if not candidate_path.is_absolute():
        candidate_path = root / candidate_path
    return candidate_path.resolve(strict=False)


def main() -> None:
    """Run the browser MCP server over stdio."""
    build_browser_server().run(transport="stdio")


if __name__ == "__main__":
    main()
