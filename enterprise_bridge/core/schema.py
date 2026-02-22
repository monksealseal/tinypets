"""
Schema discovery and caching layer.

Fetches entity/object metadata from each adapter and caches it
so that Claude can reason about available fields without
hitting the remote system on every request.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from enterprise_bridge.core.adapter import BaseAdapter, OperationResult


@dataclass
class FieldInfo:
    name: str
    label: str
    data_type: str
    required: bool = False
    read_only: bool = False
    reference_to: str | None = None
    picklist_values: list[str] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "label": self.label,
            "type": self.data_type,
            "required": self.required,
        }
        if self.read_only:
            d["read_only"] = True
        if self.reference_to:
            d["reference_to"] = self.reference_to
        if self.picklist_values:
            d["picklist_values"] = self.picklist_values
        if self.description:
            d["description"] = self.description
        return d


@dataclass
class EntitySchema:
    name: str
    label: str
    fields: list[FieldInfo]
    key_field: str = "Id"
    description: str = ""
    fetched_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "key_field": self.key_field,
            "description": self.description,
            "field_count": len(self.fields),
            "fields": [f.to_dict() for f in self.fields],
        }


class SchemaCache:
    """
    In-memory schema cache with TTL.

    Avoids redundant describe calls while still refreshing metadata
    when it gets stale.
    """

    def __init__(self, ttl_seconds: int = 3600) -> None:
        self._ttl = ttl_seconds
        self._cache: dict[str, EntitySchema] = {}

    def get(self, entity: str) -> EntitySchema | None:
        schema = self._cache.get(entity)
        if schema and (time.time() - schema.fetched_at) < self._ttl:
            return schema
        return None

    def put(self, schema: EntitySchema) -> None:
        schema.fetched_at = time.time()
        self._cache[schema.name] = schema

    def invalidate(self, entity: str | None = None) -> None:
        if entity:
            self._cache.pop(entity, None)
        else:
            self._cache.clear()


class SchemaDiscovery:
    """High-level schema operations backed by an adapter + cache."""

    def __init__(self, adapter: BaseAdapter, cache: SchemaCache | None = None) -> None:
        self._adapter = adapter
        self._cache = cache or SchemaCache()

    async def list_entities(self) -> OperationResult:
        return await self._adapter.list_entities()

    async def describe(self, entity: str, force_refresh: bool = False) -> OperationResult:
        if not force_refresh:
            cached = self._cache.get(entity)
            if cached:
                return OperationResult(
                    success=True,
                    data=cached.to_dict(),
                    message="from cache",
                )

        result = await self._adapter.describe_entity(entity)
        if result.success and isinstance(result.data, dict):
            fields = [
                FieldInfo(**f) if isinstance(f, dict) else f
                for f in result.data.get("fields", [])
            ]
            schema = EntitySchema(
                name=result.data.get("name", entity),
                label=result.data.get("label", entity),
                fields=fields,
                key_field=result.data.get("key_field", "Id"),
                description=result.data.get("description", ""),
            )
            self._cache.put(schema)
            result.data = schema.to_dict()

        return result

    async def search_fields(self, entity: str, keyword: str) -> OperationResult:
        """Find fields whose name or label contains *keyword*."""
        desc = await self.describe(entity)
        if not desc.success:
            return desc

        keyword_lower = keyword.lower()
        matches = [
            f for f in desc.data.get("fields", [])
            if keyword_lower in f.get("name", "").lower()
            or keyword_lower in f.get("label", "").lower()
        ]
        return OperationResult(success=True, data=matches)
