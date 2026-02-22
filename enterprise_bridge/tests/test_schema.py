"""Tests for schema discovery and caching."""

import time
from unittest.mock import AsyncMock

import pytest

from enterprise_bridge.core.adapter import OperationResult
from enterprise_bridge.core.schema import (
    EntitySchema,
    FieldInfo,
    SchemaCache,
    SchemaDiscovery,
)


class TestSchemaCache:
    def test_put_and_get(self):
        cache = SchemaCache(ttl_seconds=3600)
        schema = EntitySchema(
            name="Account",
            label="Account",
            fields=[FieldInfo(name="Id", label="Id", data_type="string")],
        )
        cache.put(schema)

        result = cache.get("Account")
        assert result is not None
        assert result.name == "Account"

    def test_expired_entry_returns_none(self):
        cache = SchemaCache(ttl_seconds=0)
        schema = EntitySchema(
            name="Account",
            label="Account",
            fields=[],
            fetched_at=time.time() - 10,
        )
        cache._cache["Account"] = schema

        assert cache.get("Account") is None

    def test_invalidate_single(self):
        cache = SchemaCache()
        schema = EntitySchema(name="Account", label="Account", fields=[])
        cache.put(schema)
        cache.invalidate("Account")
        assert cache.get("Account") is None

    def test_invalidate_all(self):
        cache = SchemaCache()
        for name in ["Account", "Contact", "Order"]:
            cache.put(EntitySchema(name=name, label=name, fields=[]))
        cache.invalidate()
        assert cache.get("Account") is None
        assert cache.get("Contact") is None


class TestFieldInfo:
    def test_to_dict_minimal(self):
        field = FieldInfo(name="Id", label="ID", data_type="string")
        d = field.to_dict()
        assert d["name"] == "Id"
        assert d["type"] == "string"
        assert "read_only" not in d  # False fields are omitted

    def test_to_dict_full(self):
        field = FieldInfo(
            name="Status",
            label="Status",
            data_type="picklist",
            required=True,
            read_only=True,
            reference_to="StatusType",
            picklist_values=["Active", "Inactive"],
            description="Current status",
        )
        d = field.to_dict()
        assert d["required"] is True
        assert d["read_only"] is True
        assert d["reference_to"] == "StatusType"
        assert d["picklist_values"] == ["Active", "Inactive"]


class TestSchemaDiscovery:
    @pytest.mark.asyncio
    async def test_describe_caches_result(self):
        mock_adapter = AsyncMock()
        mock_adapter.describe_entity = AsyncMock(return_value=OperationResult(
            success=True,
            data={
                "name": "Account",
                "label": "Account",
                "key_field": "Id",
                "fields": [
                    {"name": "Id", "label": "ID", "data_type": "string"},
                    {"name": "Name", "label": "Name", "data_type": "string"},
                ],
            },
        ))

        discovery = SchemaDiscovery(mock_adapter)

        # First call hits the adapter
        result1 = await discovery.describe("Account")
        assert result1.success
        assert mock_adapter.describe_entity.call_count == 1

        # Second call uses cache
        result2 = await discovery.describe("Account")
        assert result2.success
        assert result2.message == "from cache"
        assert mock_adapter.describe_entity.call_count == 1

    @pytest.mark.asyncio
    async def test_search_fields(self):
        mock_adapter = AsyncMock()
        mock_adapter.describe_entity = AsyncMock(return_value=OperationResult(
            success=True,
            data={
                "name": "Account",
                "label": "Account",
                "key_field": "Id",
                "fields": [
                    {"name": "Id", "label": "ID", "data_type": "string"},
                    {"name": "BillingCity", "label": "Billing City", "data_type": "string"},
                    {"name": "ShippingCity", "label": "Shipping City", "data_type": "string"},
                    {"name": "Name", "label": "Account Name", "data_type": "string"},
                ],
            },
        ))

        discovery = SchemaDiscovery(mock_adapter)
        result = await discovery.search_fields("Account", "city")
        assert result.success
        assert len(result.data) == 2
