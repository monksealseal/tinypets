"""
Oracle adapter — talks to Oracle Fusion Cloud REST APIs and
Oracle ERP Cloud (FBDI / BI Publisher / REST).

Covers Oracle Fusion Cloud Applications (ERP, HCM, SCM) via their
common REST resource pattern: /fscmRestApi/resources/{version}/{entity}.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from enterprise_bridge.core.adapter import BaseAdapter, ConnectionStatus, OperationResult
from enterprise_bridge.core.auth import AuthProvider, create_auth_provider
from enterprise_bridge.core.query import parse_filter_key


class OracleAdapter(BaseAdapter):
    """Adapter for Oracle Fusion Cloud REST APIs."""

    system_name = "oracle"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._base_url: str = config["base_url"].rstrip("/")
        self._api_version: str = config.get("api_version", "v1")
        self._auth: AuthProvider = create_auth_provider(config["auth"])
        self._client: httpx.AsyncClient | None = None

    @property
    def _rest_base(self) -> str:
        return f"/fscmRestApi/resources/{self._api_version}"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            token = await self._auth.get_token()
            headers = self._auth.auth_header(token)
            headers.update({
                "Accept": "application/json",
                "Content-Type": "application/json",
                "REST-Framework-Version": "4",
            })
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=headers,
                timeout=60.0,
            )
        return self._client

    # -- filter builder ----------------------------------------------------

    def _build_finder_params(
        self,
        filters: dict[str, Any] | None,
        fields: list[str] | None,
        limit: int,
        offset: int,
    ) -> dict[str, str]:
        """Build Oracle REST query params (?q=, &fields=, &limit=, &offset=)."""
        params: dict[str, str] = {}

        if filters:
            conditions: list[str] = []
            for key, value in filters.items():
                field_name, op = parse_filter_key(key)

                if op == "like":
                    conditions.append(f"{field_name} LIKE '{value}'")
                elif op == "in" and isinstance(value, list):
                    formatted = ", ".join(
                        f"'{v}'" if isinstance(v, str) else str(v) for v in value
                    )
                    conditions.append(f"{field_name} IN ({formatted})")
                elif op == "null":
                    conditions.append(
                        f"{field_name} IS NULL" if value else f"{field_name} IS NOT NULL"
                    )
                elif op == "gt":
                    conditions.append(f"{field_name} > {self._format_val(value)}")
                elif op == "gte":
                    conditions.append(f"{field_name} >= {self._format_val(value)}")
                elif op == "lt":
                    conditions.append(f"{field_name} < {self._format_val(value)}")
                elif op == "lte":
                    conditions.append(f"{field_name} <= {self._format_val(value)}")
                elif op == "ne":
                    conditions.append(f"{field_name} != {self._format_val(value)}")
                else:
                    conditions.append(f"{field_name} = {self._format_val(value)}")

            params["q"] = " AND ".join(conditions)

        if fields:
            params["fields"] = ",".join(fields)
        if limit:
            params["limit"] = str(limit)
        if offset:
            params["offset"] = str(offset)
        params["totalResults"] = "true"

        return params

    @staticmethod
    def _format_val(value: Any) -> str:
        return f"'{value}'" if isinstance(value, str) else str(value)

    # -- lifecycle --------------------------------------------------------

    async def connect(self) -> OperationResult:
        try:
            client = await self._get_client()
            resp = await client.get(self._rest_base)
            if resp.status_code < 400:
                self._status = ConnectionStatus.CONNECTED
                return OperationResult(success=True, message="Connected to Oracle Fusion")
            self._status = ConnectionStatus.ERROR
            return OperationResult(
                success=False, message=f"Oracle returned {resp.status_code}"
            )
        except Exception as exc:
            self._status = ConnectionStatus.ERROR
            return OperationResult(success=False, message=str(exc))

    async def disconnect(self) -> OperationResult:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        self._client = None
        self._status = ConnectionStatus.DISCONNECTED
        return OperationResult(success=True, message="Disconnected from Oracle Fusion")

    async def health_check(self) -> OperationResult:
        try:
            client = await self._get_client()
            resp = await client.get(self._rest_base, timeout=10)
            ok = resp.status_code < 400
            return OperationResult(
                success=ok, message="healthy" if ok else f"status {resp.status_code}"
            )
        except Exception as exc:
            return OperationResult(success=False, message=str(exc))

    # -- CRUD -------------------------------------------------------------

    async def query(
        self,
        entity: str,
        filters: dict[str, Any] | None = None,
        fields: list[str] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> OperationResult:
        client = await self._get_client()
        params = self._build_finder_params(filters, fields, limit, offset)
        try:
            resp = await client.get(f"{self._rest_base}/{entity}", params=params)
            resp.raise_for_status()
            body = resp.json()
            items = body.get("items", [])
            return OperationResult(
                success=True,
                data=items,
                metadata={
                    "total_count": body.get("totalResults"),
                    "entity": entity,
                    "has_more": body.get("hasMore", False),
                },
            )
        except Exception as exc:
            return OperationResult(success=False, message=str(exc))

    async def get_record(self, entity: str, record_id: str) -> OperationResult:
        client = await self._get_client()
        try:
            resp = await client.get(
                f"{self._rest_base}/{entity}/{quote(record_id)}"
            )
            resp.raise_for_status()
            return OperationResult(success=True, data=resp.json())
        except Exception as exc:
            return OperationResult(success=False, message=str(exc))

    async def create_record(self, entity: str, data: dict[str, Any]) -> OperationResult:
        client = await self._get_client()
        try:
            resp = await client.post(
                f"{self._rest_base}/{entity}", json=data
            )
            resp.raise_for_status()
            body = resp.json()
            return OperationResult(
                success=True,
                data=body,
                message="Record created",
            )
        except Exception as exc:
            return OperationResult(success=False, message=str(exc))

    async def update_record(
        self, entity: str, record_id: str, data: dict[str, Any]
    ) -> OperationResult:
        client = await self._get_client()
        try:
            resp = await client.patch(
                f"{self._rest_base}/{entity}/{quote(record_id)}",
                json=data,
            )
            resp.raise_for_status()
            return OperationResult(success=True, message="Record updated")
        except Exception as exc:
            return OperationResult(success=False, message=str(exc))

    async def delete_record(self, entity: str, record_id: str) -> OperationResult:
        client = await self._get_client()
        try:
            resp = await client.delete(
                f"{self._rest_base}/{entity}/{quote(record_id)}"
            )
            if resp.status_code in (200, 204):
                return OperationResult(success=True, message="Record deleted")
            resp.raise_for_status()
            return OperationResult(success=True, message="Record deleted")
        except Exception as exc:
            return OperationResult(success=False, message=str(exc))

    # -- schema -----------------------------------------------------------

    async def list_entities(self) -> OperationResult:
        client = await self._get_client()
        try:
            resp = await client.get(self._rest_base)
            resp.raise_for_status()
            body = resp.json()
            items = body.get("items", [])
            entities = [
                {"name": item.get("name", ""), "label": item.get("name", "")}
                for item in items
            ]
            return OperationResult(success=True, data=entities)
        except Exception as exc:
            return OperationResult(success=False, message=str(exc))

    async def describe_entity(self, entity: str) -> OperationResult:
        client = await self._get_client()
        try:
            resp = await client.get(
                f"{self._rest_base}/{entity}/describe"
            )
            resp.raise_for_status()
            body = resp.json()

            attributes = body.get("attributes", [])
            fields = [
                {
                    "name": attr.get("name", ""),
                    "label": attr.get("title", attr.get("name", "")),
                    "data_type": attr.get("type", "string"),
                    "required": attr.get("required", False),
                    "read_only": attr.get("readOnly", False),
                    "description": attr.get("description", ""),
                }
                for attr in attributes
            ]

            return OperationResult(
                success=True,
                data={
                    "name": entity,
                    "label": body.get("title", entity),
                    "key_field": body.get("primaryKey", ["Id"])[0] if body.get("primaryKey") else "Id",
                    "description": body.get("description", ""),
                    "fields": fields,
                },
            )
        except Exception as exc:
            return OperationResult(success=False, message=str(exc))

    # -- raw --------------------------------------------------------------

    async def execute_raw(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> OperationResult:
        client = await self._get_client()
        try:
            resp = await client.request(method.upper(), path, json=body)
            resp.raise_for_status()
            try:
                data = resp.json()
            except Exception:
                data = resp.text
            return OperationResult(success=True, data=data)
        except Exception as exc:
            return OperationResult(success=False, message=str(exc))
