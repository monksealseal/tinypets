"""
CLI for Enterprise Bridge.

Provides commands for:
  - Generating configuration templates
  - Testing connections
  - Running the MCP server
  - Querying enterprise systems directly from the command line
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from enterprise_bridge.core.config import Config


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, default=str))


async def _cmd_init(args: argparse.Namespace) -> None:
    """Generate a template config file."""
    from pathlib import Path

    template = Config.generate_template()
    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(template)
    print(f"Configuration template written to {dest}")
    print("Edit the file with your connection details, then run:")
    print(f"  enterprise-bridge test --config {dest}")


async def _cmd_test(args: argparse.Namespace) -> None:
    """Test connectivity to all configured connections."""
    from enterprise_bridge.adapters import ADAPTER_REGISTRY

    config = Config.load(args.config)
    profiles = config.list_profiles()

    if not profiles:
        print("No connection profiles found in config.")
        sys.exit(1)

    print(f"Testing {len(profiles)} connection(s)...\n")

    for p in profiles:
        profile = config.get_profile(p["name"])
        adapter_cls = ADAPTER_REGISTRY.get(profile.system)
        if adapter_cls is None:
            print(f"  [{p['name']}] SKIP - unknown system: {profile.system}")
            continue

        adapter = adapter_cls(profile.to_adapter_config())
        try:
            result = await adapter.connect()
            if result.success:
                health = await adapter.health_check()
                status = "OK" if health.success else f"WARN - {health.message}"
                print(f"  [{p['name']}] ({profile.system}) {status}")
            else:
                print(f"  [{p['name']}] ({profile.system}) FAIL - {result.message}")
        except Exception as exc:
            print(f"  [{p['name']}] ({profile.system}) ERROR - {exc}")
        finally:
            await adapter.disconnect()


async def _cmd_query(args: argparse.Namespace) -> None:
    """Run a query against a connection."""
    from enterprise_bridge.adapters import ADAPTER_REGISTRY

    config = Config.load(args.config)
    profile = config.get_profile(args.connection)
    adapter_cls = ADAPTER_REGISTRY[profile.system]
    adapter = adapter_cls(profile.to_adapter_config())

    try:
        await adapter.connect()
        filters = json.loads(args.filters) if args.filters else None
        fields = args.fields.split(",") if args.fields else None

        result = await adapter.query(
            entity=args.entity,
            filters=filters,
            fields=fields,
            limit=args.limit,
            offset=args.offset,
        )
        _print_json(result.to_dict())
    finally:
        await adapter.disconnect()


async def _cmd_describe(args: argparse.Namespace) -> None:
    """Describe an entity's schema."""
    from enterprise_bridge.adapters import ADAPTER_REGISTRY
    from enterprise_bridge.core.schema import SchemaDiscovery

    config = Config.load(args.config)
    profile = config.get_profile(args.connection)
    adapter_cls = ADAPTER_REGISTRY[profile.system]
    adapter = adapter_cls(profile.to_adapter_config())

    try:
        await adapter.connect()
        discovery = SchemaDiscovery(adapter)
        result = await discovery.describe(args.entity)
        _print_json(result.to_dict())
    finally:
        await adapter.disconnect()


async def _cmd_serve(args: argparse.Namespace) -> None:
    """Start the MCP server."""
    from enterprise_bridge.mcp_server import main as mcp_main
    # Delegate to the MCP server's own argument handling
    sys.argv = ["enterprise-bridge-mcp"]
    if args.config:
        sys.argv += ["--config", args.config]
    if args.sse:
        sys.argv += ["--sse"]
    if args.port:
        sys.argv += ["--port", str(args.port)]
    mcp_main()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="enterprise-bridge",
        description="Enterprise Bridge — Claude Code integration with SAP, Salesforce, NetSuite, Oracle",
    )
    sub = parser.add_subparsers(dest="command")

    # -- init --
    p_init = sub.add_parser("init", help="Generate a configuration template")
    p_init.add_argument(
        "-o", "--output",
        default=str(Config.generate_template and "~/.enterprise-bridge/config.yaml"),
        help="Output path for the config file",
    )

    # -- test --
    p_test = sub.add_parser("test", help="Test all configured connections")
    p_test.add_argument("--config", type=str, default=None)

    # -- query --
    p_query = sub.add_parser("query", help="Query records from an entity")
    p_query.add_argument("--config", type=str, default=None)
    p_query.add_argument("-c", "--connection", required=True)
    p_query.add_argument("-e", "--entity", required=True)
    p_query.add_argument("-f", "--filters", type=str, default=None, help="JSON filter object")
    p_query.add_argument("--fields", type=str, default=None, help="Comma-separated field list")
    p_query.add_argument("--limit", type=int, default=100)
    p_query.add_argument("--offset", type=int, default=0)

    # -- describe --
    p_desc = sub.add_parser("describe", help="Describe an entity's schema")
    p_desc.add_argument("--config", type=str, default=None)
    p_desc.add_argument("-c", "--connection", required=True)
    p_desc.add_argument("-e", "--entity", required=True)

    # -- serve --
    p_serve = sub.add_parser("serve", help="Start the MCP server")
    p_serve.add_argument("--config", type=str, default=None)
    p_serve.add_argument("--sse", action="store_true")
    p_serve.add_argument("--port", type=int, default=8080)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    dispatch = {
        "init": _cmd_init,
        "test": _cmd_test,
        "query": _cmd_query,
        "describe": _cmd_describe,
        "serve": _cmd_serve,
    }

    asyncio.run(dispatch[args.command](args))


if __name__ == "__main__":
    main()
