from __future__ import annotations

import json
from typing import Any

import httpx
import yaml
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations


def _required_string(value: str, *, error_message: str) -> str:
    """Validate and return a non-empty stripped string."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(error_message)
    return value.strip()


def _optional_string_mapping(
    value: dict[str, str] | None,
    *,
    field_name: str,
    mapping_error_message: str,
    key_error_message: str,
    item_error_builder: object,
) -> dict[str, str]:
    """Validate an optional dict[str, str] mapping."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(mapping_error_message)
    result: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        if not isinstance(raw_key, str) or not raw_key.strip():
            raise ValueError(key_error_message)
        if not isinstance(raw_value, str):
            builder = item_error_builder
            if callable(builder):
                raise ValueError(builder(field_name, raw_key))
            raise ValueError(f"Tool field '{field_name}.{raw_key}' must be a string.")
        result[raw_key.strip()] = raw_value
    return result


http_api_server = FastMCP("openharness-http-api", log_level="ERROR")

_READONLY_HTTP_METHODS = {"GET", "HEAD", "OPTIONS"}
_ALL_HTTP_METHODS = {"GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"}
_DEFAULT_USER_AGENT = "OpenHarness HTTP API MCP"


def build_http_api_server() -> FastMCP:
    """Return the configured HTTP API MCP server instance."""
    return http_api_server


@http_api_server.tool(
    description="Fetch one read-only HTTP response and return normalized metadata plus parsed body when possible.",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True),
)
def fetch_http_response(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    query_params: dict[str, str] | None = None,
    timeout_ms: int = 15_000,
    max_body_chars: int = 20_000,
) -> dict[str, Any]:
    """Fetch one read-only HTTP response."""
    normalized_method = _normalize_method(method, readonly_only=True)
    _validate_timeout(timeout_ms)
    _validate_positive_int(max_body_chars, field_name="max_body_chars")
    response = _send_http_request(
        method=normalized_method,
        url=url,
        headers=headers,
        query_params=query_params,
        timeout_ms=timeout_ms,
    )
    return _build_response_payload(response, max_body_chars=max_body_chars)


@http_api_server.tool(
    description="Send one HTTP request with optional JSON, form, or text body and return normalized response data.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True),
)
def request_http(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    query_params: dict[str, str] | None = None,
    json_body: Any | None = None,
    form_body: dict[str, str] | None = None,
    text_body: str | None = None,
    timeout_ms: int = 15_000,
    max_body_chars: int = 20_000,
) -> dict[str, Any]:
    """Send one HTTP request with optional payload."""
    normalized_method = _normalize_method(method, readonly_only=False)
    _validate_timeout(timeout_ms)
    _validate_positive_int(max_body_chars, field_name="max_body_chars")
    _validate_request_bodies(json_body=json_body, form_body=form_body, text_body=text_body)
    response = _send_http_request(
        method=normalized_method,
        url=url,
        headers=headers,
        query_params=query_params,
        json_body=json_body,
        form_body=form_body,
        text_body=text_body,
        timeout_ms=timeout_ms,
    )
    return _build_response_payload(response, max_body_chars=max_body_chars)


@http_api_server.tool(
    description="Fetch and summarize one OpenAPI document exposed over HTTP in JSON or YAML format.",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True),
)
def inspect_openapi_spec(
    url: str,
    headers: dict[str, str] | None = None,
    query_params: dict[str, str] | None = None,
    timeout_ms: int = 15_000,
    max_paths: int = 200,
) -> dict[str, Any]:
    """Fetch and summarize one OpenAPI spec."""
    _validate_timeout(timeout_ms)
    _validate_positive_int(max_paths, field_name="max_paths")
    response = _send_http_request(
        method="GET",
        url=url,
        headers=headers,
        query_params=query_params,
        timeout_ms=timeout_ms,
    )
    content = response.text
    parsed_spec = _parse_openapi_document(content)
    info = parsed_spec.get("info") if isinstance(parsed_spec, dict) else None
    paths = parsed_spec.get("paths") if isinstance(parsed_spec, dict) else None
    if not isinstance(paths, dict):
        raise ValueError("OpenAPI document does not contain a valid 'paths' object.")
    path_items = []
    for path_index, (path_name, raw_operations) in enumerate(paths.items()):
        if path_index >= max_paths:
            break
        operations = []
        if isinstance(raw_operations, dict):
            for method_name, method_payload in raw_operations.items():
                if not isinstance(method_name, str):
                    continue
                normalized_method_name = method_name.lower()
                if normalized_method_name not in {"get", "post", "put", "patch", "delete", "head", "options"}:
                    continue
                summary = None
                operation_id = None
                tags: list[str] = []
                if isinstance(method_payload, dict):
                    raw_summary = method_payload.get("summary")
                    raw_operation_id = method_payload.get("operationId")
                    raw_tags = method_payload.get("tags")
                    summary = raw_summary if isinstance(raw_summary, str) else None
                    operation_id = raw_operation_id if isinstance(raw_operation_id, str) else None
                    if isinstance(raw_tags, list):
                        tags = [item for item in raw_tags if isinstance(item, str)]
                operations.append(
                    {
                        "method": normalized_method_name.upper(),
                        "summary": summary,
                        "operation_id": operation_id,
                        "tags": tags,
                    }
                )
        path_items.append(
            {
                "path": path_name,
                "operations": operations,
            }
        )
    title = info.get("title") if isinstance(info, dict) and isinstance(info.get("title"), str) else None
    version = info.get("version") if isinstance(info, dict) and isinstance(info.get("version"), str) else None
    return {
        "ok": True,
        "url": str(response.url),
        "status_code": response.status_code,
        "title": title,
        "version": version,
        "openapi": (
            parsed_spec.get("openapi")
            if isinstance(parsed_spec, dict) and isinstance(parsed_spec.get("openapi"), str)
            else None
        ),
        "path_count": len(paths),
        "paths": path_items,
        "truncated": len(paths) > max_paths,
    }


def _send_http_request(
    *,
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    query_params: dict[str, str] | None = None,
    json_body: Any | None = None,
    form_body: dict[str, str] | None = None,
    text_body: str | None = None,
    timeout_ms: int,
) -> httpx.Response:
    """Send one HTTP request and return the response."""
    normalized_url = _required_string(url, error_message="Tool field 'url' must be a non-empty string.")
    normalized_headers = _normalize_string_mapping(headers, field_name="headers")
    normalized_query_params = _normalize_string_mapping(query_params, field_name="query_params")
    normalized_form_body = _normalize_string_mapping(form_body, field_name="form_body")
    with httpx.Client(
        follow_redirects=True,
        timeout=timeout_ms / 1000.0,
        headers={"User-Agent": _DEFAULT_USER_AGENT, **normalized_headers},
    ) as client:
        response = client.request(
            method,
            normalized_url,
            params=normalized_query_params or None,
            json=json_body,
            data=normalized_form_body or text_body,
        )
    return response


def _build_response_payload(response: httpx.Response, *, max_body_chars: int) -> dict[str, Any]:
    """Return one normalized response payload."""
    body_text = response.text
    truncated = len(body_text) > max_body_chars
    if truncated:
        body_text = body_text[:max_body_chars]
    parsed_json = None
    content_type = response.headers.get("content-type", "")
    if "json" in content_type.lower():
        try:
            parsed_json = response.json()
        except json.JSONDecodeError:
            parsed_json = None
    return {
        "ok": True,
        "url": str(response.url),
        "status_code": response.status_code,
        "reason_phrase": response.reason_phrase,
        "headers": dict(response.headers),
        "content_type": content_type,
        "body": body_text,
        "truncated": truncated,
        "json": parsed_json,
    }


def _parse_openapi_document(content: str) -> dict[str, Any]:
    """Parse one OpenAPI document from JSON or YAML."""
    try:
        parsed_document = json.loads(content)
    except json.JSONDecodeError:
        parsed_document = yaml.safe_load(content)
    if not isinstance(parsed_document, dict):
        raise ValueError("OpenAPI document must parse into an object.")
    if "openapi" not in parsed_document and "swagger" not in parsed_document:
        raise ValueError("Document does not look like an OpenAPI or Swagger specification.")
    return parsed_document


def _normalize_method(method: str, *, readonly_only: bool) -> str:
    """Return one validated HTTP method."""
    normalized_method = _required_string(
        method,
        error_message="Tool field 'method' must be a non-empty string.",
    ).upper()
    if normalized_method not in _ALL_HTTP_METHODS:
        raise ValueError(
            "Tool field 'method' must be one of: "
            + ", ".join(sorted(_ALL_HTTP_METHODS))
            + "."
        )
    if readonly_only and normalized_method not in _READONLY_HTTP_METHODS:
        raise ValueError(
            "Read-only HTTP fetch only supports methods: "
            + ", ".join(sorted(_READONLY_HTTP_METHODS))
            + "."
        )
    return normalized_method


def _validate_request_bodies(
    *,
    json_body: Any | None,
    form_body: dict[str, str] | None,
    text_body: str | None,
) -> None:
    """Reject ambiguous request body combinations."""
    provided_payload_kinds = sum(
        1
        for value in (json_body, form_body, text_body)
        if value is not None
    )
    if provided_payload_kinds > 1:
        raise ValueError("Provide at most one of 'json_body', 'form_body', or 'text_body'.")
    if text_body is not None and not isinstance(text_body, str):
        raise ValueError("Tool field 'text_body' must be a string when provided.")


def _normalize_string_mapping(value: dict[str, str] | None, *, field_name: str) -> dict[str, str]:
    """Return one validated string mapping."""
    return _optional_string_mapping(
        value,
        field_name=field_name,
        mapping_error_message=f"Tool field '{field_name}' must be an object when provided.",
        key_error_message=f"Tool field '{field_name}' must use non-empty string keys.",
        item_error_builder=lambda field_name, raw_key: f"Tool field '{field_name}.{raw_key}' must be a string.",
    )


def _validate_positive_int(value: int, *, field_name: str) -> None:
    """Validate one positive integer field."""
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"Tool field '{field_name}' must be a positive integer.")


def _validate_timeout(timeout_ms: int) -> None:
    """Validate one timeout field."""
    _validate_positive_int(timeout_ms, field_name="timeout_ms")


def main() -> None:
    """Run the HTTP API MCP server over stdio."""
    build_http_api_server().run(transport="stdio")


if __name__ == "__main__":
    main()
