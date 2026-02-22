"""Tests for enterprise adapters using mocked HTTP responses."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enterprise_bridge.core.adapter import ConnectionStatus, OperationResult


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_config(system: str, auth_type: str = "basic") -> dict[str, Any]:
    """Build a minimal adapter config for testing."""
    base = {
        "name": f"test_{system}",
        "system": system,
        "base_url": f"https://test.{system}.example.com",
        "auth": {
            "type": auth_type,
            "username": "test_user",
            "password": "test_pass",
        },
    }
    if system == "netsuite":
        base["account_id"] = "123456"
    return base


def _mock_response(status_code: int = 200, json_data: Any = None, text: str = "", headers: dict | None = None):
    """Create a mock httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = text
    resp.headers = headers or {}
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        from httpx import HTTPStatusError, Request, Response
        resp.raise_for_status.side_effect = HTTPStatusError(
            message=f"{status_code}", request=MagicMock(), response=resp
        )
    return resp


# ── SAP Tests ────────────────────────────────────────────────────────────


class TestSAPAdapter:
    @pytest.fixture
    def adapter(self):
        from enterprise_bridge.adapters.sap import SAPAdapter
        return SAPAdapter(_make_config("sap"))

    @pytest.mark.asyncio
    async def test_connect_success(self, adapter):
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.get = AsyncMock(return_value=_mock_response(200))
        adapter._client = mock_client

        result = await adapter.connect()
        assert result.success
        assert adapter.status == ConnectionStatus.CONNECTED

    @pytest.mark.asyncio
    async def test_query_builds_odata_filter(self, adapter):
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.get = AsyncMock(return_value=_mock_response(200, {
            "d": {"results": [{"Id": "1", "Name": "Test"}], "__count": "1"}
        }))
        adapter._client = mock_client

        result = await adapter.query(
            entity="BusinessPartner",
            filters={"CompanyName": "Acme", "Revenue__gt": 1000},
            fields=["CompanyName", "Revenue"],
            limit=10,
        )
        assert result.success
        call_args = mock_client.get.call_args
        params = call_args.kwargs.get("params", call_args[1].get("params", {}))
        assert "$filter" in params
        assert "$select" in params
        assert "$top" in params

    @pytest.mark.asyncio
    async def test_disconnect(self, adapter):
        mock_client = AsyncMock()
        mock_client.is_closed = False
        adapter._client = mock_client

        result = await adapter.disconnect()
        assert result.success
        assert adapter.status == ConnectionStatus.DISCONNECTED


# ── Salesforce Tests ─────────────────────────────────────────────────────


class TestSalesforceAdapter:
    @pytest.fixture
    def adapter(self):
        from enterprise_bridge.adapters.salesforce import SalesforceAdapter
        return SalesforceAdapter(_make_config("salesforce"))

    @pytest.mark.asyncio
    async def test_connect_success(self, adapter):
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.get = AsyncMock(return_value=_mock_response(200))
        adapter._client = mock_client

        result = await adapter.connect()
        assert result.success

    @pytest.mark.asyncio
    async def test_query_generates_soql(self, adapter):
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.get = AsyncMock(return_value=_mock_response(200, {
            "records": [{"Id": "001", "Name": "Acme"}],
            "totalSize": 1,
            "done": True,
        }))
        adapter._client = mock_client

        result = await adapter.query(
            entity="Account",
            filters={"Industry": "Technology"},
            fields=["Id", "Name", "Industry"],
            limit=50,
        )
        assert result.success
        assert result.metadata.get("soql")
        assert "Account" in result.metadata["soql"]

    @pytest.mark.asyncio
    async def test_create_record(self, adapter):
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.post = AsyncMock(return_value=_mock_response(201, {
            "id": "001ABC", "success": True
        }))
        adapter._client = mock_client

        result = await adapter.create_record("Account", {"Name": "New Acme"})
        assert result.success
        assert result.data["id"] == "001ABC"

    @pytest.mark.asyncio
    async def test_update_record(self, adapter):
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.patch = AsyncMock(return_value=_mock_response(204))
        adapter._client = mock_client

        result = await adapter.update_record("Account", "001ABC", {"Name": "Updated"})
        assert result.success

    @pytest.mark.asyncio
    async def test_delete_record(self, adapter):
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.delete = AsyncMock(return_value=_mock_response(204))
        adapter._client = mock_client

        result = await adapter.delete_record("Account", "001ABC")
        assert result.success

    @pytest.mark.asyncio
    async def test_list_entities(self, adapter):
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.get = AsyncMock(return_value=_mock_response(200, {
            "sobjects": [
                {"name": "Account", "label": "Account", "queryable": True, "createable": True},
                {"name": "Contact", "label": "Contact", "queryable": True, "createable": True},
            ]
        }))
        adapter._client = mock_client

        result = await adapter.list_entities()
        assert result.success
        assert len(result.data) == 2


# ── NetSuite Tests ───────────────────────────────────────────────────────


class TestNetSuiteAdapter:
    @pytest.fixture
    def adapter(self):
        from enterprise_bridge.adapters.netsuite import NetSuiteAdapter
        return NetSuiteAdapter(_make_config("netsuite"))

    @pytest.mark.asyncio
    async def test_connect_success(self, adapter):
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.get = AsyncMock(return_value=_mock_response(200))
        adapter._client = mock_client

        result = await adapter.connect()
        assert result.success

    @pytest.mark.asyncio
    async def test_query_generates_suiteql(self, adapter):
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.post = AsyncMock(return_value=_mock_response(200, {
            "items": [{"id": "1", "companyname": "Acme"}],
            "totalResults": 1,
            "hasMore": False,
        }))
        adapter._client = mock_client

        result = await adapter.query(
            entity="customer",
            filters={"companyname__like": "Acme"},
            limit=25,
        )
        assert result.success
        assert "suiteql" in result.metadata

    @pytest.mark.asyncio
    async def test_create_record(self, adapter):
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.post = AsyncMock(return_value=_mock_response(
            204, headers={"Location": "/services/rest/record/v1/customer/12345"}
        ))
        adapter._client = mock_client

        result = await adapter.create_record("customer", {"companyname": "New Corp"})
        assert result.success
        assert result.data["id"] == "12345"


# ── Oracle Tests ─────────────────────────────────────────────────────────


class TestOracleAdapter:
    @pytest.fixture
    def adapter(self):
        from enterprise_bridge.adapters.oracle import OracleAdapter
        return OracleAdapter(_make_config("oracle"))

    @pytest.mark.asyncio
    async def test_connect_success(self, adapter):
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.get = AsyncMock(return_value=_mock_response(200))
        adapter._client = mock_client

        result = await adapter.connect()
        assert result.success

    @pytest.mark.asyncio
    async def test_query_with_filters(self, adapter):
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.get = AsyncMock(return_value=_mock_response(200, {
            "items": [{"SupplierName": "Test Supplier"}],
            "totalResults": 1,
            "hasMore": False,
        }))
        adapter._client = mock_client

        result = await adapter.query(
            entity="suppliers",
            filters={"SupplierName__like": "Test"},
            limit=10,
        )
        assert result.success
        assert len(result.data) == 1

    @pytest.mark.asyncio
    async def test_get_record(self, adapter):
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.get = AsyncMock(return_value=_mock_response(200, {
            "SupplierId": "300000001", "SupplierName": "Acme"
        }))
        adapter._client = mock_client

        result = await adapter.get_record("suppliers", "300000001")
        assert result.success
        assert result.data["SupplierName"] == "Acme"
