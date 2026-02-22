"""
Unified query engine that translates a portable query DSL
into adapter-specific calls.

The DSL is intentionally simple so Claude can construct queries
from natural-language user requests without needing to know
vendor-specific syntax.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from enterprise_bridge.core.adapter import BaseAdapter, OperationResult


@dataclass
class QuerySpec:
    """
    Portable query specification.

    Example (as JSON — the shape Claude sees via MCP):
    {
        "entity": "Account",
        "filters": {"Industry": "Technology", "AnnualRevenue__gt": 1000000},
        "fields": ["Name", "Industry", "AnnualRevenue"],
        "order_by": ["-AnnualRevenue"],
        "limit": 25,
        "offset": 0
    }

    Filter operators are encoded as suffixes on the field name:
        __gt, __gte, __lt, __lte, __ne, __in, __like, __null
    A bare field name implies equality.
    """

    entity: str
    filters: dict[str, Any] = field(default_factory=dict)
    fields: list[str] = field(default_factory=list)
    order_by: list[str] = field(default_factory=list)
    limit: int = 100
    offset: int = 0

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "QuerySpec":
        return cls(
            entity=d["entity"],
            filters=d.get("filters", {}),
            fields=d.get("fields", []),
            order_by=d.get("order_by", []),
            limit=d.get("limit", 100),
            offset=d.get("offset", 0),
        )


OPERATOR_SUFFIXES = ("__gt", "__gte", "__lt", "__lte", "__ne", "__in", "__like", "__null")


def parse_filter_key(key: str) -> tuple[str, str]:
    """Split 'AnnualRevenue__gt' → ('AnnualRevenue', 'gt')."""
    for suffix in OPERATOR_SUFFIXES:
        if key.endswith(suffix):
            return key[: -len(suffix)], suffix[2:]
    return key, "eq"


class QueryEngine:
    """Runs a QuerySpec against a connected adapter."""

    def __init__(self, adapter: BaseAdapter) -> None:
        self._adapter = adapter

    async def execute(self, spec: QuerySpec) -> OperationResult:
        return await self._adapter.query(
            entity=spec.entity,
            filters=spec.filters,
            fields=spec.fields,
            limit=spec.limit,
            offset=spec.offset,
        )

    async def count(self, spec: QuerySpec) -> OperationResult:
        """Execute a query with limit=0 to get a count only (adapter-dependent)."""
        result = await self._adapter.query(
            entity=spec.entity,
            filters=spec.filters,
            fields=[],
            limit=0,
            offset=0,
        )
        return result

    async def aggregate(
        self, entity: str, field_name: str, function: str = "count"
    ) -> OperationResult:
        """
        Run a simple aggregation.  Not all adapters support this natively;
        those that don't will fall back to fetching + local aggregation.
        """
        result = await self._adapter.query(
            entity=entity, filters={}, fields=[field_name], limit=10000
        )
        if not result.success or not isinstance(result.data, list):
            return result

        values = [r.get(field_name) for r in result.data if r.get(field_name) is not None]

        computed: Any
        if function == "count":
            computed = len(values)
        elif function == "sum":
            computed = sum(float(v) for v in values)
        elif function == "avg":
            computed = sum(float(v) for v in values) / len(values) if values else 0
        elif function == "min":
            computed = min(values) if values else None
        elif function == "max":
            computed = max(values) if values else None
        else:
            return OperationResult(success=False, message=f"Unknown aggregation: {function}")

        return OperationResult(
            success=True,
            data={function: computed, "field": field_name, "record_count": len(values)},
        )
