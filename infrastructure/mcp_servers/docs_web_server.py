from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
import re
from typing import Any
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from openharness.shared.normalize import optional_string_list, required_string


docs_web_server = FastMCP("openharness-docs-web", log_level="ERROR")

_DUCKDUCKGO_HTML_SEARCH_URL = "https://html.duckduckgo.com/html/"
_DEFAULT_USER_AGENT = "OpenHarness Docs/Web MCP"


@dataclass(frozen=True, slots=True)
class ParsedHtmlDocument:
    """Describe one normalized HTML document."""

    title: str | None
    text_content: str


def build_docs_web_server() -> FastMCP:
    """Return the configured docs/web MCP server instance."""
    return docs_web_server


@docs_web_server.tool(
    description="Search the web or official docs for a query, optionally restricted to one or more domains.",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True),
)
def search_web(
    query: str,
    domains: list[str] | None = None,
    max_results: int = 8,
    timeout_ms: int = 15_000,
) -> dict[str, Any]:
    """Search the web and return normalized result metadata."""
    return search_web_documents(
        query=query,
        domains=domains,
        max_results=max_results,
        timeout_ms=timeout_ms,
    )


@docs_web_server.tool(
    description="Fetch one URL and return normalized text content, title, and metadata.",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True),
)
def fetch_url(
    url: str,
    timeout_ms: int = 15_000,
    max_chars: int = 20_000,
) -> dict[str, Any]:
    """Fetch one URL and return normalized text content."""
    return fetch_web_document(
        url=url,
        timeout_ms=timeout_ms,
        max_chars=max_chars,
    )


def search_web_documents(
    *,
    query: str,
    domains: list[str] | None = None,
    max_results: int = 8,
    timeout_ms: int = 15_000,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Search the web and return parsed results."""
    normalized_query = required_string(query, error_message="Tool field 'query' must be a non-empty string.")
    if max_results <= 0:
        raise ValueError("Tool 'search_web' field 'max_results' must be a positive integer.")
    if timeout_ms <= 0:
        raise ValueError("Tool 'search_web' field 'timeout_ms' must be a positive integer.")

    normalized_domains = _normalize_domains(domains)
    search_query = _build_search_query(normalized_query, normalized_domains)
    response_text = _http_get_text(
        url=_DUCKDUCKGO_HTML_SEARCH_URL,
        params={"q": search_query},
        timeout_ms=timeout_ms,
        client=client,
    )
    results = _parse_duckduckgo_results(response_text, max_results=max_results)
    return {
        "ok": True,
        "query": normalized_query,
        "domains": list(normalized_domains),
        "search_query": search_query,
        "results": results,
        "result_count": len(results),
    }


def fetch_web_document(
    *,
    url: str,
    timeout_ms: int = 15_000,
    max_chars: int = 20_000,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Fetch one URL and return normalized text content."""
    normalized_url = required_string(url, error_message="Tool field 'url' must be a non-empty string.")
    if timeout_ms <= 0:
        raise ValueError("Tool 'fetch_url' field 'timeout_ms' must be a positive integer.")
    if max_chars <= 0:
        raise ValueError("Tool 'fetch_url' field 'max_chars' must be a positive integer.")

    created_client = client is None
    active_client = client or _build_http_client(timeout_ms)
    try:
        response = active_client.get(normalized_url)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        raw_text = response.text
    finally:
        if created_client:
            active_client.close()

    title: str | None = None
    normalized_text = raw_text
    if _looks_like_html(content_type=content_type, text=raw_text):
        parsed_document = _parse_html_document(raw_text)
        title = parsed_document.title
        normalized_text = parsed_document.text_content

    truncated = len(normalized_text) > max_chars
    if truncated:
        normalized_text = normalized_text[:max_chars]

    return {
        "ok": True,
        "url": normalized_url,
        "final_url": str(response.url),
        "status_code": response.status_code,
        "content_type": content_type,
        "title": title,
        "content": normalized_text,
        "truncated": truncated,
    }


def _http_get_text(
    *,
    url: str,
    params: dict[str, Any] | None,
    timeout_ms: int,
    client: httpx.Client | None,
) -> str:
    """Return one response body as text."""
    created_client = client is None
    active_client = client or _build_http_client(timeout_ms)
    try:
        response = active_client.get(url, params=params)
        response.raise_for_status()
        return response.text
    finally:
        if created_client:
            active_client.close()


def _build_http_client(timeout_ms: int) -> httpx.Client:
    """Return a client configured for web and docs retrieval."""
    return httpx.Client(
        follow_redirects=True,
        timeout=timeout_ms / 1000.0,
        headers={"User-Agent": _DEFAULT_USER_AGENT},
    )


def _build_search_query(query: str, domains: tuple[str, ...]) -> str:
    """Return one search query with optional domain filters."""
    if not domains:
        return query
    if len(domains) == 1:
        return f"{query} site:{domains[0]}"
    return f"{query} ({' OR '.join(f'site:{domain}' for domain in domains)})"


def _normalize_domains(domains: list[str] | None) -> tuple[str, ...]:
    """Return one validated list of unique domains."""
    return optional_string_list(
        domains,
        field_name="domains",
        list_error_message="Tool 'search_web' field 'domains' must be a list when provided.",
        item_error_builder=lambda field_name, index: (
            f"Tool 'search_web' field '{field_name}[{index}]' must be a non-empty string."
        ),
        dedupe=True,
    )


def _parse_duckduckgo_results(search_html: str, *, max_results: int) -> list[dict[str, Any]]:
    """Extract search results from a DuckDuckGo HTML result page."""
    results: list[dict[str, Any]] = []
    for match in re.finditer(
        r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
        search_html,
        re.IGNORECASE | re.DOTALL,
    ):
        title = _strip_html(match.group("title"))
        if not title:
            continue
        url = _normalize_search_result_url(match.group("href"))
        snippet_search_window = search_html[match.end() : match.end() + 2_000]
        snippet_match = re.search(
            r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(?P<snippet>.*?)</a>|'
            r'<div[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(?P<div_snippet>.*?)</div>',
            snippet_search_window,
            re.IGNORECASE | re.DOTALL,
        )
        snippet = ""
        if snippet_match is not None:
            snippet = _strip_html(
                snippet_match.group("snippet") or snippet_match.group("div_snippet") or ""
            )
        results.append(
            {
                "title": title,
                "url": url,
                "snippet": snippet,
                "domain": urlparse(url).netloc,
            }
        )
        if len(results) >= max_results:
            break
    return results


def _normalize_search_result_url(url: str) -> str:
    """Return the direct result URL for one DuckDuckGo link."""
    normalized_url = unescape(url.strip())
    if normalized_url.startswith("//"):
        normalized_url = f"https:{normalized_url}"
    parsed_url = urlparse(normalized_url)
    if parsed_url.netloc.endswith("duckduckgo.com") and parsed_url.path.startswith("/l/"):
        encoded_target = parse_qs(parsed_url.query).get("uddg")
        if encoded_target:
            return unquote(encoded_target[0])
    return normalized_url


def _looks_like_html(*, content_type: str, text: str) -> bool:
    """Return whether one response likely contains HTML."""
    normalized_content_type = content_type.lower()
    if "html" in normalized_content_type:
        return True
    return "<html" in text[:1_000].lower()


def _parse_html_document(html: str) -> ParsedHtmlDocument:
    """Return normalized title and visible text from one HTML document."""
    parser = _HtmlTextParser()
    parser.feed(html)
    return ParsedHtmlDocument(
        title=parser.title,
        text_content=parser.normalized_text(),
    )


def _strip_html(value: str) -> str:
    """Return one HTML fragment normalized to readable text."""
    text = re.sub(r"<[^>]+>", " ", value)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


class _HtmlTextParser(HTMLParser):
    """Extract visible text and title from one HTML document."""

    def __init__(self) -> None:
        """Initialize parser state."""
        super().__init__()
        self._text_chunks: list[str] = []
        self._title_chunks: list[str] = []
        self._ignore_depth = 0
        self._in_title = False

    @property
    def title(self) -> str | None:
        """Return the normalized page title when present."""
        if not self._title_chunks:
            return None
        return re.sub(r"\s+", " ", "".join(self._title_chunks)).strip() or None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Track ignored tags and block-level separators."""
        if tag in {"script", "style", "noscript"}:
            self._ignore_depth += 1
            return
        if tag == "title":
            self._in_title = True
        if tag in {"p", "div", "br", "li", "section", "article", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._text_chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        """Track ignored tags and block-level separators."""
        if tag in {"script", "style", "noscript"} and self._ignore_depth > 0:
            self._ignore_depth -= 1
            return
        if tag == "title":
            self._in_title = False
        if tag in {"p", "div", "li", "section", "article"}:
            self._text_chunks.append("\n")

    def handle_data(self, data: str) -> None:
        """Capture visible text and title data."""
        if self._ignore_depth > 0:
            return
        if self._in_title:
            self._title_chunks.append(data)
        self._text_chunks.append(data)

    def normalized_text(self) -> str:
        """Return the normalized visible text body."""
        raw_text = unescape("".join(self._text_chunks))
        raw_text = raw_text.replace("\r", "\n")
        normalized_lines = [re.sub(r"\s+", " ", line).strip() for line in raw_text.split("\n")]
        return "\n".join(line for line in normalized_lines if line)


def main() -> None:
    """Run the docs/web MCP server over stdio."""
    build_docs_web_server().run(transport="stdio")


if __name__ == "__main__":
    main()
