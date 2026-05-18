from __future__ import annotations

import keyword
import logging
import re
import types
from typing import Annotated, Any

from autogen.beta.tools.final.function_tool import FunctionTool, tool as beta_tool
from pydantic import Field

from infrastructure.mcp.manager import McpManager

logger = logging.getLogger(__name__)

_MISSING = object()
_TYPE_MAP = {
    "string": "str",
    "integer": "int",
    "number": "float",
    "boolean": "bool",
    "array": "list[Any]",
    "object": "dict[str, Any]",
}


def _schema_to_annotation(schema: dict[str, Any]) -> str:
    schema_type = schema.get("type")

    if isinstance(schema_type, list):
        non_null_types = [item for item in schema_type if item != "null"]
        if not non_null_types:
            return "Any"
        annotation = " | ".join(_TYPE_MAP.get(item, "Any") for item in non_null_types)
        if "null" in schema_type:
            return f"{annotation} | None"
        return annotation

    if schema_type == "array":
        items = schema.get("items")
        if isinstance(items, dict):
            return f"list[{_schema_to_annotation(items)}]"
        return "list[Any]"

    if schema_type == "object":
        return "dict[str, Any]"

    return _TYPE_MAP.get(schema_type, "Any")


def _make_safe_identifier(name: str, used_names: set[str]) -> str:
    candidate = re.sub(r"\W", "_", name).strip("_") or "arg"
    if candidate[0].isdigit():
        candidate = f"arg_{candidate}"
    if keyword.iskeyword(candidate) or candidate == "kwargs":
        candidate = f"{candidate}_"

    base_name = candidate
    suffix = 2
    while candidate in used_names:
        candidate = f"{base_name}_{suffix}"
        suffix += 1

    used_names.add(candidate)
    return candidate


def _build_parameter_specs(parameters_schema: dict[str, Any]) -> list[dict[str, Any]]:
    properties = parameters_schema.get("properties", {}) if isinstance(parameters_schema, dict) else {}
    required = set(parameters_schema.get("required", [])) if isinstance(parameters_schema, dict) else set()
    used_names: set[str] = set()
    specs: list[dict[str, Any]] = []

    for schema_name, param_info in properties.items():
        argument_name = _make_safe_identifier(schema_name, used_names)
        annotation = _schema_to_annotation(param_info if isinstance(param_info, dict) else {})
        is_required = schema_name in required
        if not is_required and "| None" not in annotation:
            annotation = f"{annotation} | None"
        if argument_name != schema_name:
            annotation = f"Annotated[{annotation}, Field(alias={schema_name!r})]"
        specs.append(
            {
                "schema_name": schema_name,
                "argument_name": argument_name,
                "annotation": annotation,
                "required": is_required,
            }
        )

    return specs


def _build_signature(parameter_specs: list[dict[str, Any]]) -> str:
    declarations = []
    for spec in parameter_specs:
        default_value = "" if spec["required"] else " = None"
        declarations.append(
            f"{spec['argument_name']}: {spec['annotation']}{default_value}"
        )

    if not declarations:
        return "**kwargs"
    return ", ".join(["*", *declarations, "**kwargs"])


def _build_call_params(
    parameter_specs: list[dict[str, Any]],
    local_values: dict[str, Any],
) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for spec in parameter_specs:
        value = local_values.get(spec["argument_name"], _MISSING)
        if value is _MISSING:
            continue
        if value is None and not spec["required"]:
            continue
        params[spec["schema_name"]] = value
    return params


def _create_async_tool_func(
    mcp_manager: McpManager,
    server_name: str,
    tool_name: str,
    parameters_schema: dict[str, Any],
) -> types.FunctionType:
    """Create a beta-compatible MCP tool with an explicit signature.

    AG2 beta infers tool validation from the Python function signature while
    still injecting internal kwargs such as ``__ctx__``. We generate a typed
    keyword-only signature from the MCP schema and keep ``**kwargs`` to absorb
    beta-only injected parameters.
    """

    parameter_specs = _build_parameter_specs(parameters_schema)
    signature = _build_signature(parameter_specs)
    safe_tool_name = _make_safe_identifier(tool_name, set())
    func_body = (
        f"async def {safe_tool_name}({signature}) -> str:\n"
        "    params = _build_call_params(_parameter_specs, locals())\n"
        "    return await _call_tool(_server_name, _tool_name, params)\n"
    )

    namespace = {
        "_build_call_params": _build_call_params,
        "_call_tool": lambda s, n, p: mcp_manager.call_tool(s, n, p),
        "_parameter_specs": parameter_specs,
        "_server_name": server_name,
        "_tool_name": tool_name,
        "Annotated": Annotated,
        "Any": Any,
        "Field": Field,
    }

    exec(func_body, namespace)
    func = namespace[safe_tool_name]
    func.__name__ = tool_name
    func.__qualname__ = tool_name
    return func


def build_beta_tools_for_servers(
    mcp_manager: McpManager,
    server_names: list[str],
    tool_filter: list[str] | None = None,
) -> list[FunctionTool]:
    """Build beta-compatible MCP tools for a role."""
    tools: list[FunctionTool] = []
    for server_name in server_names:
        for tool_info in mcp_manager.get_tools_for_server(server_name):
            if tool_filter and tool_info.tool_name not in tool_filter:
                continue

            tool_func = _create_async_tool_func(
                mcp_manager,
                server_name,
                tool_info.tool_name,
                tool_info.input_schema,
            )

            tools.append(
                beta_tool(
                    tool_func,
                    name=tool_info.tool_name,
                    description=tool_info.description,
                    schema=tool_info.input_schema,
                )
            )
            logger.debug(
                "Built beta MCP tool '%s' from server '%s'",
                tool_info.tool_name,
                server_name,
            )
    return tools
