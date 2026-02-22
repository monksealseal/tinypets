"""
MCP (Model Context Protocol) server for Enterprise Bridge.

This is the integration point that makes Claude Code work *natively*
with SAP, Salesforce, NetSuite, and Oracle.  When this server is
registered in the user's Claude Code MCP configuration, all enterprise
operations become available as tools that Claude can call directly
from natural-language conversation.

Launch:
    python -m enterprise_bridge.mcp_server          # stdio transport
    python -m enterprise_bridge.mcp_server --sse     # SSE transport (HTTP)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from enterprise_bridge.adapters import ADAPTER_REGISTRY
from enterprise_bridge.core.adapter import BaseAdapter, OperationResult
from enterprise_bridge.core.config import Config
from enterprise_bridge.core.query import QueryEngine, QuerySpec
from enterprise_bridge.core.schema import SchemaCache, SchemaDiscovery

logger = logging.getLogger("enterprise_bridge.mcp")

# ── Global state ─────────────────────────────────────────────────────────

_config: Config | None = None
_adapters: dict[str, BaseAdapter] = {}
_schemas: dict[str, SchemaDiscovery] = {}


def _result_to_content(result: OperationResult) -> list[TextContent]:
    """Convert an OperationResult into MCP TextContent."""
    payload = result.to_dict()
    return [TextContent(type="text", text=json.dumps(payload, indent=2, default=str))]


async def _get_adapter(connection: str) -> BaseAdapter:
    """Lazily instantiate, cache, and connect an adapter for *connection*."""
    if connection in _adapters:
        return _adapters[connection]

    if _config is None:
        raise RuntimeError("Configuration not loaded. Call enterprise_configure first.")

    profile = _config.get_profile(connection)
    adapter_cls = ADAPTER_REGISTRY.get(profile.system)
    if adapter_cls is None:
        raise ValueError(f"Unknown system type: {profile.system!r}")

    adapter = adapter_cls(profile.to_adapter_config())
    await adapter.connect()
    _adapters[connection] = adapter
    _schemas[connection] = SchemaDiscovery(adapter, SchemaCache())
    return adapter


# ── MCP Server definition ───────────────────────────────────────────────

app = Server("enterprise-bridge")


# ---------- Tool definitions ----------


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        # -- connection management ----------------------------------------
        Tool(
            name="enterprise_configure",
            description=(
                "Load Enterprise Bridge configuration and list available "
                "connection profiles. Call this first before any other "
                "enterprise tool. Pass config_path to use a non-default "
                "config file, or omit it to use the default location."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "config_path": {
                        "type": "string",
                        "description": "Path to config YAML/JSON file (optional).",
                    },
                },
            },
        ),
        Tool(
            name="enterprise_list_connections",
            description="List all configured enterprise system connection profiles.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="enterprise_connect",
            description=(
                "Connect to a configured enterprise system. Returns connection "
                "status. The connection name must match a profile in the config."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "connection": {
                        "type": "string",
                        "description": "Connection profile name (e.g. 'my_salesforce').",
                    },
                },
                "required": ["connection"],
            },
        ),
        Tool(
            name="enterprise_health_check",
            description="Check connectivity and auth status for a connection.",
            inputSchema={
                "type": "object",
                "properties": {
                    "connection": {
                        "type": "string",
                        "description": "Connection profile name.",
                    },
                },
                "required": ["connection"],
            },
        ),
        # -- schema / discovery -------------------------------------------
        Tool(
            name="enterprise_list_entities",
            description=(
                "List available entities / objects / tables in the connected "
                "enterprise system (e.g. Account, SalesOrder, Vendor, etc.)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "connection": {"type": "string", "description": "Connection profile name."},
                },
                "required": ["connection"],
            },
        ),
        Tool(
            name="enterprise_describe_entity",
            description=(
                "Get full field-level schema for an entity including field "
                "names, types, required status, picklist values, and "
                "relationships.  Use this to understand what data is "
                "available before querying."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "connection": {"type": "string", "description": "Connection profile name."},
                    "entity": {"type": "string", "description": "Entity / object name (e.g. 'Account')."},
                },
                "required": ["connection", "entity"],
            },
        ),
        Tool(
            name="enterprise_search_fields",
            description="Search for fields within an entity by keyword.",
            inputSchema={
                "type": "object",
                "properties": {
                    "connection": {"type": "string"},
                    "entity": {"type": "string"},
                    "keyword": {"type": "string", "description": "Keyword to search field names/labels."},
                },
                "required": ["connection", "entity", "keyword"],
            },
        ),
        # -- query / read -------------------------------------------------
        Tool(
            name="enterprise_query",
            description=(
                "Query records from an enterprise system entity with optional "
                "filters, field selection, and pagination. Filter operators: "
                "exact match (field: value), __gt, __gte, __lt, __lte, "
                "__ne, __in (array), __like (substring), __null (bool)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "connection": {"type": "string", "description": "Connection profile name."},
                    "entity": {"type": "string", "description": "Entity name (e.g. 'Account')."},
                    "filters": {
                        "type": "object",
                        "description": "Filter conditions. Keys are field names with optional operator suffix.",
                    },
                    "fields": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Fields to return (empty = all).",
                    },
                    "limit": {"type": "integer", "description": "Max records to return.", "default": 100},
                    "offset": {"type": "integer", "description": "Number of records to skip.", "default": 0},
                },
                "required": ["connection", "entity"],
            },
        ),
        Tool(
            name="enterprise_get_record",
            description="Fetch a single record by its ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "connection": {"type": "string"},
                    "entity": {"type": "string"},
                    "record_id": {"type": "string", "description": "Primary key / record ID."},
                },
                "required": ["connection", "entity", "record_id"],
            },
        ),
        # -- write operations ---------------------------------------------
        Tool(
            name="enterprise_create_record",
            description=(
                "Create a new record in the enterprise system. Pass the "
                "field values as the 'data' object."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "connection": {"type": "string"},
                    "entity": {"type": "string"},
                    "data": {"type": "object", "description": "Field-value pairs for the new record."},
                },
                "required": ["connection", "entity", "data"],
            },
        ),
        Tool(
            name="enterprise_update_record",
            description="Update an existing record by ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "connection": {"type": "string"},
                    "entity": {"type": "string"},
                    "record_id": {"type": "string"},
                    "data": {"type": "object", "description": "Fields to update."},
                },
                "required": ["connection", "entity", "record_id", "data"],
            },
        ),
        Tool(
            name="enterprise_delete_record",
            description="Delete a record by ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "connection": {"type": "string"},
                    "entity": {"type": "string"},
                    "record_id": {"type": "string"},
                },
                "required": ["connection", "entity", "record_id"],
            },
        ),
        # -- aggregation --------------------------------------------------
        Tool(
            name="enterprise_aggregate",
            description=(
                "Run a simple aggregation (count, sum, avg, min, max) on a "
                "field.  Useful for quick analytics directly from the "
                "enterprise system."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "connection": {"type": "string"},
                    "entity": {"type": "string"},
                    "field": {"type": "string", "description": "Field to aggregate."},
                    "function": {
                        "type": "string",
                        "enum": ["count", "sum", "avg", "min", "max"],
                        "description": "Aggregation function.",
                    },
                },
                "required": ["connection", "entity", "field", "function"],
            },
        ),
        # -- raw / escape-hatch ------------------------------------------
        Tool(
            name="enterprise_raw_request",
            description=(
                "Send a raw HTTP request through the enterprise adapter's "
                "authenticated transport.  Use this for vendor-specific API "
                "endpoints not covered by the standard CRUD tools."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "connection": {"type": "string"},
                    "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
                    "path": {"type": "string", "description": "API path (relative to base URL)."},
                    "body": {"type": "object", "description": "Request body (optional)."},
                },
                "required": ["connection", "method", "path"],
            },
        ),
        # -- utility ------------------------------------------------------
        Tool(
            name="enterprise_generate_config",
            description="Generate a template configuration file for Enterprise Bridge.",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


# ---------- Tool handlers ----------


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    global _config

    try:
        # -- configuration ------------------------------------------------
        if name == "enterprise_configure":
            _config = Config.load(arguments.get("config_path"))
            profiles = _config.list_profiles()
            return _result_to_content(OperationResult(
                success=True,
                data={"profiles": profiles},
                message=f"Loaded {len(profiles)} connection profile(s).",
            ))

        if name == "enterprise_generate_config":
            template = Config.generate_template()
            return _result_to_content(OperationResult(
                success=True, data=template, message="Configuration template"
            ))

        if name == "enterprise_list_connections":
            if _config is None:
                _config = Config.load()
            return _result_to_content(OperationResult(
                success=True, data=_config.list_profiles()
            ))

        # -- everything else requires a connection ------------------------
        connection = arguments.get("connection", "")

        if name == "enterprise_connect":
            adapter = await _get_adapter(connection)
            return _result_to_content(OperationResult(
                success=True,
                message=f"Connected to {adapter.system_name} via '{connection}'",
                data={"system": adapter.system_name, "status": adapter.status.value},
            ))

        if name == "enterprise_health_check":
            adapter = await _get_adapter(connection)
            return _result_to_content(await adapter.health_check())

        # -- schema -------------------------------------------------------
        if name == "enterprise_list_entities":
            adapter = await _get_adapter(connection)
            return _result_to_content(await adapter.list_entities())

        if name == "enterprise_describe_entity":
            discovery = _schemas.get(connection)
            if not discovery:
                await _get_adapter(connection)
                discovery = _schemas[connection]
            return _result_to_content(
                await discovery.describe(arguments["entity"])
            )

        if name == "enterprise_search_fields":
            discovery = _schemas.get(connection)
            if not discovery:
                await _get_adapter(connection)
                discovery = _schemas[connection]
            return _result_to_content(
                await discovery.search_fields(arguments["entity"], arguments["keyword"])
            )

        # -- query / read -------------------------------------------------
        if name == "enterprise_query":
            adapter = await _get_adapter(connection)
            return _result_to_content(await adapter.query(
                entity=arguments["entity"],
                filters=arguments.get("filters"),
                fields=arguments.get("fields"),
                limit=arguments.get("limit", 100),
                offset=arguments.get("offset", 0),
            ))

        if name == "enterprise_get_record":
            adapter = await _get_adapter(connection)
            return _result_to_content(
                await adapter.get_record(arguments["entity"], arguments["record_id"])
            )

        # -- write --------------------------------------------------------
        if name == "enterprise_create_record":
            adapter = await _get_adapter(connection)
            return _result_to_content(
                await adapter.create_record(arguments["entity"], arguments["data"])
            )

        if name == "enterprise_update_record":
            adapter = await _get_adapter(connection)
            return _result_to_content(
                await adapter.update_record(
                    arguments["entity"], arguments["record_id"], arguments["data"]
                )
            )

        if name == "enterprise_delete_record":
            adapter = await _get_adapter(connection)
            return _result_to_content(
                await adapter.delete_record(arguments["entity"], arguments["record_id"])
            )

        # -- aggregation --------------------------------------------------
        if name == "enterprise_aggregate":
            adapter = await _get_adapter(connection)
            engine = QueryEngine(adapter)
            return _result_to_content(
                await engine.aggregate(
                    arguments["entity"], arguments["field"], arguments["function"]
                )
            )

        # -- raw ----------------------------------------------------------
        if name == "enterprise_raw_request":
            adapter = await _get_adapter(connection)
            return _result_to_content(
                await adapter.execute_raw(
                    arguments["method"], arguments["path"], arguments.get("body")
                )
            )

        return _result_to_content(
            OperationResult(success=False, message=f"Unknown tool: {name}")
        )

    except Exception as exc:
        logger.exception("Tool %s failed", name)
        return _result_to_content(
            OperationResult(success=False, message=f"Error: {exc}")
        )


# ── Entry point ──────────────────────────────────────────────────────────


async def run_stdio() -> None:
    """Run the MCP server over stdio (default for Claude Code)."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


def main() -> None:
    parser = argparse.ArgumentParser(description="Enterprise Bridge MCP Server")
    parser.add_argument(
        "--config", type=str, default=None, help="Path to config file"
    )
    parser.add_argument(
        "--sse", action="store_true", help="Run in SSE mode instead of stdio"
    )
    parser.add_argument("--port", type=int, default=8080, help="SSE port")
    args = parser.parse_args()

    if args.config:
        global _config
        _config = Config.load(args.config)

    logging.basicConfig(level=logging.INFO, stream=sys.stderr)

    if args.sse:
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.routing import Route

        sse = SseServerTransport("/messages")

        async def handle_sse(request):
            async with sse.connect_sse(
                request.scope, request.receive, request._send
            ) as streams:
                await app.run(
                    streams[0], streams[1], app.create_initialization_options()
                )

        starlette_app = Starlette(
            routes=[
                Route("/sse", endpoint=handle_sse),
                Route("/messages", endpoint=sse.handle_post_message, methods=["POST"]),
            ]
        )

        import uvicorn

        uvicorn.run(starlette_app, host="0.0.0.0", port=args.port)
    else:
        asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
