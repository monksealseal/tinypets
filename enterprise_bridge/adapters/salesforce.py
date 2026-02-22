"""
Salesforce adapter — talks to the Salesforce REST API (sObject / SOQL).

Supports query via SOQL, full CRUD on sObjects, schema describe,
and raw Composite/Tooling API calls through execute_raw.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from enterprise_bridge.core.adapter import BaseAdapter, ConnectionStatus, OperationResult
from enterprise_bridge.core.auth import AuthProvider, create_auth_provider
from enterprise_bridge.core.query import parse_filter_key


_SOQL_OPS = {
    "eq": "=",
    "ne": "!=",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
}


class SalesforceAdapter(BaseAdapter):
    """Adapter for Salesforce REST API."""

    system_name = "salesforce"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._base_url: str = config["base_url"].rstrip("/")
        self._api_version: str = config.get("api_version", "v59.0")
        self._auth: AuthProvider = create_auth_provider(config["auth"])
        self._client: httpx.AsyncClient | None = None

    @property
    def _api_base(self) -> str:
        return f"/services/data/{self._api_version}"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            token = await self._auth.get_token()
            headers = self._auth.auth_header(token)
            headers["Accept"] = "application/json"
            headers["Content-Type"] = "application/json"
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=headers,
                timeout=60.0,
            )
        return self._client

    # -- filter → SOQL ----------------------------------------------------

    def _build_soql(
        self,
        entity: str,
        filters: dict[str, Any] | None = None,
        fields: list[str] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> str:
        select = ", ".join(fields) if fields else "FIELDS(ALL)"
        soql = f"SELECT {select} FROM {entity}"

        if filters:
            clauses: list[str] = []
            for key, value in filters.items():
                field_name, op = parse_filter_key(key)
                sql_op = _SOQL_OPS.get(op)

                if op == "like":
                    clauses.append(f"{field_name} LIKE '{value}'")
                elif op == "in" and isinstance(value, list):
                    formatted = ", ".join(
                        f"'{v}'" if isinstance(v, str) else str(v)
                        for v in value
                    )
                    clauses.append(f"{field_name} IN ({formatted})")
                elif op == "null":
                    clauses.append(
                        f"{field_name} = null" if value else f"{field_name} != null"
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

            soql += " WHERE " + " AND ".join(clauses)

        if limit:
            soql += f" LIMIT {limit}"
        if offset:
            soql += f" OFFSET {offset}"

        return soql

    # -- lifecycle --------------------------------------------------------

    async def connect(self) -> OperationResult:
        try:
            client = await self._get_client()
            resp = await client.get(self._api_base)
            if resp.status_code < 400:
                self._status = ConnectionStatus.CONNECTED
                return OperationResult(success=True, message="Connected to Salesforce")
            self._status = ConnectionStatus.ERROR
            return OperationResult(
                success=False, message=f"Salesforce returned {resp.status_code}"
            )
        except Exception as exc:
            self._status = ConnectionStatus.ERROR
            return OperationResult(success=False, message=str(exc))

    async def disconnect(self) -> OperationResult:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        self._client = None
        self._status = ConnectionStatus.DISCONNECTED
        return OperationResult(success=True, message="Disconnected from Salesforce")

    async def health_check(self) -> OperationResult:
        try:
            client = await self._get_client()
            resp = await client.get(f"{self._api_base}/limits", timeout=10)
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
        soql = self._build_soql(entity, filters, fields, limit, offset)
        try:
            resp = await client.get(
                f"{self._api_base}/query",
                params={"q": soql},
            )
            resp.raise_for_status()
            body = resp.json()
            records = body.get("records", [])
            # Strip Salesforce metadata attributes for cleaner output
            for r in records:
                r.pop("attributes", None)
            return OperationResult(
                success=True,
                data=records,
                metadata={
                    "total_count": body.get("totalSize"),
                    "soql": soql,
                    "done": body.get("done", True),
                    "next_url": body.get("nextRecordsUrl"),
                },
            )
        except Exception as exc:
            return OperationResult(success=False, message=str(exc), metadata={"soql": soql})

    async def get_record(self, entity: str, record_id: str) -> OperationResult:
        client = await self._get_client()
        try:
            resp = await client.get(
                f"{self._api_base}/sobjects/{entity}/{quote(record_id)}"
            )
            resp.raise_for_status()
            data = resp.json()
            data.pop("attributes", None)
            return OperationResult(success=True, data=data)
        except Exception as exc:
            return OperationResult(success=False, message=str(exc))

    async def create_record(self, entity: str, data: dict[str, Any]) -> OperationResult:
        client = await self._get_client()
        try:
            resp = await client.post(
                f"{self._api_base}/sobjects/{entity}", json=data
            )
            resp.raise_for_status()
            body = resp.json()
            return OperationResult(
                success=body.get("success", True),
                data={"id": body.get("id")},
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
                f"{self._api_base}/sobjects/{entity}/{quote(record_id)}",
                json=data,
            )
            # Salesforce returns 204 on successful PATCH
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
                f"{self._api_base}/sobjects/{entity}/{quote(record_id)}"
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
            resp = await client.get(f"{self._api_base}/sobjects")
            resp.raise_for_status()
            body = resp.json()
            entities = [
                {
                    "name": obj["name"],
                    "label": obj.get("label", obj["name"]),
                    "queryable": obj.get("queryable", False),
                    "createable": obj.get("createable", False),
                }
                for obj in body.get("sobjects", [])
            ]
            return OperationResult(success=True, data=entities)
        except Exception as exc:
            return OperationResult(success=False, message=str(exc))

    async def describe_entity(self, entity: str) -> OperationResult:
        client = await self._get_client()
        try:
            resp = await client.get(
                f"{self._api_base}/sobjects/{entity}/describe"
            )
            resp.raise_for_status()
            body = resp.json()

            fields = [
                {
                    "name": f["name"],
                    "label": f.get("label", f["name"]),
                    "data_type": f.get("type", "string"),
                    "required": not f.get("nillable", True) and f.get("createable", True),
                    "read_only": not f.get("updateable", True),
                    "reference_to": (f.get("referenceTo") or [None])[0],
                    "picklist_values": [
                        pv["value"] for pv in f.get("picklistValues", []) if pv.get("active")
                    ],
                    "description": f.get("inlineHelpText", ""),
                }
                for f in body.get("fields", [])
            ]

            return OperationResult(
                success=True,
                data={
                    "name": body.get("name", entity),
                    "label": body.get("label", entity),
                    "key_field": "Id",
                    "description": body.get("labelPlural", ""),
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
