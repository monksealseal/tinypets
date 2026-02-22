"""Tests for the query engine and filter parsing."""

import pytest

from enterprise_bridge.core.query import QuerySpec, QueryEngine, parse_filter_key
from enterprise_bridge.core.adapter import OperationResult


class TestFilterParsing:
    def test_bare_field_is_eq(self):
        field, op = parse_filter_key("Name")
        assert field == "Name"
        assert op == "eq"

    def test_gt_suffix(self):
        field, op = parse_filter_key("Revenue__gt")
        assert field == "Revenue"
        assert op == "gt"

    def test_gte_suffix(self):
        field, op = parse_filter_key("Amount__gte")
        assert field == "Amount"
        assert op == "gte"

    def test_lt_suffix(self):
        field, op = parse_filter_key("Count__lt")
        assert field == "Count"
        assert op == "lt"

    def test_lte_suffix(self):
        field, op = parse_filter_key("Value__lte")
        assert field == "Value"
        assert op == "lte"

    def test_ne_suffix(self):
        field, op = parse_filter_key("Status__ne")
        assert field == "Status"
        assert op == "ne"

    def test_in_suffix(self):
        field, op = parse_filter_key("Region__in")
        assert field == "Region"
        assert op == "in"

    def test_like_suffix(self):
        field, op = parse_filter_key("Description__like")
        assert field == "Description"
        assert op == "like"

    def test_null_suffix(self):
        field, op = parse_filter_key("Email__null")
        assert field == "Email"
        assert op == "null"


class TestQuerySpec:
    def test_from_dict(self):
        spec = QuerySpec.from_dict({
            "entity": "Account",
            "filters": {"Industry": "Tech"},
            "fields": ["Id", "Name"],
            "limit": 50,
        })
        assert spec.entity == "Account"
        assert spec.filters == {"Industry": "Tech"}
        assert spec.fields == ["Id", "Name"]
        assert spec.limit == 50
        assert spec.offset == 0

    def test_defaults(self):
        spec = QuerySpec.from_dict({"entity": "Contact"})
        assert spec.filters == {}
        assert spec.fields == []
        assert spec.limit == 100
        assert spec.offset == 0


class TestQueryEngine:
    @pytest.mark.asyncio
    async def test_aggregate_count(self):
        from unittest.mock import AsyncMock

        mock_adapter = AsyncMock()
        mock_adapter.query = AsyncMock(return_value=OperationResult(
            success=True,
            data=[
                {"Amount": 100},
                {"Amount": 200},
                {"Amount": 300},
            ],
        ))

        engine = QueryEngine(mock_adapter)
        result = await engine.aggregate("Order", "Amount", "count")
        assert result.success
        assert result.data["count"] == 3

    @pytest.mark.asyncio
    async def test_aggregate_sum(self):
        from unittest.mock import AsyncMock

        mock_adapter = AsyncMock()
        mock_adapter.query = AsyncMock(return_value=OperationResult(
            success=True,
            data=[
                {"Amount": 100},
                {"Amount": 200},
                {"Amount": 300},
            ],
        ))

        engine = QueryEngine(mock_adapter)
        result = await engine.aggregate("Order", "Amount", "sum")
        assert result.success
        assert result.data["sum"] == 600.0

    @pytest.mark.asyncio
    async def test_aggregate_avg(self):
        from unittest.mock import AsyncMock

        mock_adapter = AsyncMock()
        mock_adapter.query = AsyncMock(return_value=OperationResult(
            success=True,
            data=[{"Score": 10}, {"Score": 20}, {"Score": 30}],
        ))

        engine = QueryEngine(mock_adapter)
        result = await engine.aggregate("Student", "Score", "avg")
        assert result.success
        assert result.data["avg"] == 20.0

    @pytest.mark.asyncio
    async def test_aggregate_min_max(self):
        from unittest.mock import AsyncMock

        mock_adapter = AsyncMock()
        mock_adapter.query = AsyncMock(return_value=OperationResult(
            success=True,
            data=[{"Price": 5}, {"Price": 50}, {"Price": 25}],
        ))

        engine = QueryEngine(mock_adapter)

        result_min = await engine.aggregate("Product", "Price", "min")
        assert result_min.data["min"] == 5

        result_max = await engine.aggregate("Product", "Price", "max")
        assert result_max.data["max"] == 50
