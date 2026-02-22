"""
NetSuite adapter — talks to the NetSuite SuiteQL / REST Web Services API.

Supports SuiteQL queries, standard CRUD on record types, and schema
discovery via the metadata catalog endpoint.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from enterprise_bridge.core.adapter import BaseAdapter, ConnectionStatus, OperationResult
from enterprise_bridge.core.auth import AuthProvider, create_auth_provider
from enterprise_bridge.core.query import parse_filter_key


_SQL_OPS = {
    "eq": "=",
    "ne": "!=",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
}


class NetSuiteAdapter(BaseAdapter):
    """Adapter for NetSuite REST Web Services + SuiteQL."""

    system_name = "netsuite"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._base_url: str = config["base_url"].rstrip("/")
        self._account_id: str = config.get("account_id", "")
        self._auth: AuthProvider = create_auth_provider(config["auth"])
        self._client: httpx.AsyncClient | None = None

    @property
    def _rest_base(self) -> str:
        return "/services/rest/record/v1"

    @property
    def _suiteql_url(self) -> str:
        return "/services/rest/query/v1/suiteql"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            token = await self._auth.get_token()
            headers = self._auth.auth_header(token)
            headers.update({
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Prefer": "transient",
            })
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=headers,
                timeout=60.0,
            )
        return self._client

    # -- SuiteQL builder ---------------------------------------------------

    def _build_suiteql(
        self,
        entity: str,
        filters: dict[str, Any] | None = None,
        fields: list[str] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> str:
        select = ", ".join(fields) if fields else "*"
        sql = f"SELECT {select} FROM {entity}"

        if filters:
            clauses: list[str] = []
            for key, value in filters.items():
                field_name, op = parse_filter_key(key)
                sql_op = _SQL_OPS.get(op)

                if op == "like":
                    clauses.append(f"{field_name} LIKE '%{value}%'")
                elif op == "in" and isinstance(value, list):
                    formatted = ", ".join(
                        f"'{v}'" if isinstance(v, str) else str(v) for v in value
                    )
                    clauses.append(f"{field_name} IN ({formatted})")
                elif op == "null":
                    clauses.append(
                        f"{field_name} IS NULL" if value else f"{field_name} IS NOT NULL"
                    )
                elif sql_op:
                    if isinstance(value, str):
                        clauses.append(f"{field_name} {sql_op} '{value}'")
                    else:
                        clauses.append(f"{field_name} {sql_op} {value}")
                else:
                    if isinstance(value, str):
                        clauses.append(f"{field_name} = '{value}'")
                    else:
                        clauses.append(f"{field_name} = {value}")

            sql += " WHERE " + " AND ".join(clauses)

        if limit:
            sql += f" FETCH NEXT {limit} ROWS ONLY"
        if offset:
            sql = sql.replace(
                f"FETCH NEXT {limit} ROWS ONLY",
                f"OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY",
            )

        return sql

    # -- lifecycle --------------------------------------------------------

    async def connect(self) -> OperationResult:
        try:
            client = await self._get_client()
            resp = await client.get(self._rest_base)
            if resp.status_code < 400:
                self._status = ConnectionStatus.CONNECTED
                return OperationResult(success=True, message="Connected to NetSuite")
            self._status = ConnectionStatus.ERROR
            return OperationResult(
                success=False, message=f"NetSuite returned {resp.status_code}"
            )
        except Exception as exc:
            self._status = ConnectionStatus.ERROR
            return OperationResult(success=False, message=str(exc))

    async def disconnect(self) -> OperationResult:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        self._client = None
        self._status = ConnectionStatus.DISCONNECTED
        return OperationResult(success=True, message="Disconnected from NetSuite")

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
        suiteql = self._build_suiteql(entity, filters, fields, limit, offset)
        try:
            resp = await client.post(
                self._suiteql_url,
                json={"q": suiteql},
                headers={"Prefer": "transient"},
            )
            resp.raise_for_status()
            body = resp.json()
            items = body.get("items", [])
            return OperationResult(
                success=True,
                data=items,
                metadata={
                    "total_count": body.get("totalResults"),
                    "suiteql": suiteql,
                    "has_more": body.get("hasMore", False),
                },
            )
        except Exception as exc:
            return OperationResult(success=False, message=str(exc), metadata={"suiteql": suiteql})

    async def get_record(self, entity: str, record_id: str) -> OperationResult:
        client = await self._get_client()
        try:
            resp = await client.get(
                f"{self._rest_base}/{entity.lower()}/{quote(record_id)}"
            )
            resp.raise_for_status()
            return OperationResult(success=True, data=resp.json())
        except Exception as exc:
            return OperationResult(success=False, message=str(exc))

    async def create_record(self, entity: str, data: dict[str, Any]) -> OperationResult:
        client = await self._get_client()
        try:
            resp = await client.post(
                f"{self._rest_base}/{entity.lower()}",
                json=data,
            )
            resp.raise_for_status()
            # NetSuite returns the new record ID in the Location header
            location = resp.headers.get("Location", "")
            record_id = location.rstrip("/").split("/")[-1] if location else None
            return OperationResult(
                success=True,
                data={"id": record_id},
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
                f"{self._rest_base}/{entity.lower()}/{quote(record_id)}",
                json=data,
            )
            if resp.status_code in (200, 204):
                return OperationResult(success=True, message="Record updated")
            resp.raise_for_status()
            return OperationResult(success=True, message="Record updated")
        except Exception as exc:
            return OperationResult(success=False, message=str(exc))

    async def delete_record(self, entity: str, record_id: str) -> OperationResult:
        client = await self._get_client()
        try:
            resp = await client.delete(
                f"{self._rest_base}/{entity.lower()}/{quote(record_id)}"
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
                f"{self._rest_base}/metadata-catalog/{entity.lower()}",
                headers={"Accept": "application/schema+json"},
            )
            resp.raise_for_status()
            schema = resp.json()

            properties = schema.get("properties", {})
            fields = []
            for name, prop in properties.items():
                fields.append({
                    "name": name,
                    "label": prop.get("title", name),
                    "data_type": prop.get("type", "string"),
                    "required": name in schema.get("required", []),
                    "read_only": prop.get("readOnly", False),
                    "description": prop.get("description", ""),
                })

            return OperationResult(
                success=True,
                data={
                    "name": entity,
                    "label": schema.get("title", entity),
                    "key_field": "id",
                    "description": schema.get("description", ""),
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
