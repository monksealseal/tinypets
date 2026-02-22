"""
SAP adapter — supports S/4HANA Cloud, SAP BTP, and on-premise OData APIs.

Communication happens via OData V2/V4 over HTTPS.  The adapter translates
the unified Enterprise Bridge query model into OData $filter, $select,
$top, $skip, and $orderby parameters.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from enterprise_bridge.core.adapter import BaseAdapter, ConnectionStatus, OperationResult
from enterprise_bridge.core.auth import AuthProvider, create_auth_provider
from enterprise_bridge.core.query import parse_filter_key


# OData operator mapping
_OPS = {
    "eq": "eq",
    "ne": "ne",
    "gt": "gt",
    "gte": "ge",
    "lt": "lt",
    "lte": "le",
}


class SAPAdapter(BaseAdapter):
    """Adapter for SAP S/4HANA Cloud & BTP OData services."""

    system_name = "sap"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._base_url: str = config["base_url"].rstrip("/")
        self._api_version: str = config.get("api_version", "v2")
        self._auth: AuthProvider = create_auth_provider(config["auth"])
        self._client: httpx.AsyncClient | None = None
        self._csrf_token: str | None = None

    # -- helpers ----------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            token = await self._auth.get_token()
            headers = self._auth.auth_header(token)
            headers.update({
                "Accept": "application/json",
                "Content-Type": "application/json",
            })
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=headers,
                timeout=60.0,
            )
        return self._client

    async def _fetch_csrf(self, client: httpx.AsyncClient) -> str:
        """Fetch an X-CSRF-Token for mutating OData requests."""
        if self._csrf_token:
            return self._csrf_token
        resp = await client.get("/", headers={"X-CSRF-Token": "Fetch"})
        self._csrf_token = resp.headers.get("X-CSRF-Token", "")
        return self._csrf_token or ""

    def _build_odata_filter(self, filters: dict[str, Any]) -> str:
        """Translate portable filter dict → OData $filter string."""
        parts: list[str] = []
        for key, value in filters.items():
            field_name, op = parse_filter_key(key)
            odata_op = _OPS.get(op)

            if op == "like":
                parts.append(f"substringof('{value}',{field_name})")
            elif op == "in" and isinstance(value, list):
                or_clauses = " or ".join(
                    f"{field_name} eq '{v}'" if isinstance(v, str) else f"{field_name} eq {v}"
                    for v in value
                )
                parts.append(f"({or_clauses})")
            elif op == "null":
                parts.append(f"{field_name} eq null" if value else f"{field_name} ne null")
            elif odata_op:
                if isinstance(value, str):
                    parts.append(f"{field_name} {odata_op} '{value}'")
                else:
                    parts.append(f"{field_name} {odata_op} {value}")
            else:
                if isinstance(value, str):
                    parts.append(f"{field_name} eq '{value}'")
                else:
                    parts.append(f"{field_name} eq {value}")

        return " and ".join(parts)

    def _odata_path(self, entity: str) -> str:
        return f"/sap/opu/odata/sap/{entity}"

    # -- lifecycle --------------------------------------------------------

    async def connect(self) -> OperationResult:
        try:
            client = await self._get_client()
            resp = await client.get("/sap/opu/odata/sap/")
            if resp.status_code < 400:
                self._status = ConnectionStatus.CONNECTED
                return OperationResult(success=True, message="Connected to SAP")
            self._status = ConnectionStatus.ERROR
            return OperationResult(success=False, message=f"SAP returned {resp.status_code}")
        except Exception as exc:
            self._status = ConnectionStatus.ERROR
            return OperationResult(success=False, message=str(exc))

    async def disconnect(self) -> OperationResult:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        self._client = None
        self._csrf_token = None
        self._status = ConnectionStatus.DISCONNECTED
        return OperationResult(success=True, message="Disconnected from SAP")

    async def health_check(self) -> OperationResult:
        try:
            client = await self._get_client()
            resp = await client.get("/sap/opu/odata/sap/", timeout=10)
            ok = resp.status_code < 400
            return OperationResult(
                success=ok,
                message="healthy" if ok else f"status {resp.status_code}",
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
        params: dict[str, str] = {"$format": "json"}

        if filters:
            params["$filter"] = self._build_odata_filter(filters)
        if fields:
            params["$select"] = ",".join(fields)
        if limit:
            params["$top"] = str(limit)
        if offset:
            params["$skip"] = str(offset)
        params["$inlinecount"] = "allpages"

        try:
            resp = await client.get(self._odata_path(entity), params=params)
            resp.raise_for_status()
            body = resp.json()
            results = body.get("d", {}).get("results", body.get("d", []))
            total = body.get("d", {}).get("__count")
            return OperationResult(
                success=True,
                data=results,
                metadata={"total_count": total, "entity": entity},
            )
        except Exception as exc:
            return OperationResult(success=False, message=str(exc))

    async def get_record(self, entity: str, record_id: str) -> OperationResult:
        client = await self._get_client()
        path = f"{self._odata_path(entity)}('{quote(record_id)}')"
        try:
            resp = await client.get(path, params={"$format": "json"})
            resp.raise_for_status()
            return OperationResult(success=True, data=resp.json().get("d", {}))
        except Exception as exc:
            return OperationResult(success=False, message=str(exc))

    async def create_record(self, entity: str, data: dict[str, Any]) -> OperationResult:
        client = await self._get_client()
        csrf = await self._fetch_csrf(client)
        try:
            resp = await client.post(
                self._odata_path(entity),
                json=data,
                params={"$format": "json"},
                headers={"X-CSRF-Token": csrf},
            )
            resp.raise_for_status()
            return OperationResult(
                success=True,
                data=resp.json().get("d", {}),
                message="Record created",
            )
        except Exception as exc:
            return OperationResult(success=False, message=str(exc))

    async def update_record(
        self, entity: str, record_id: str, data: dict[str, Any]
    ) -> OperationResult:
        client = await self._get_client()
        csrf = await self._fetch_csrf(client)
        path = f"{self._odata_path(entity)}('{quote(record_id)}')"
        try:
            resp = await client.patch(
                path,
                json=data,
                params={"$format": "json"},
                headers={"X-CSRF-Token": csrf},
            )
            resp.raise_for_status()
            return OperationResult(success=True, message="Record updated")
        except Exception as exc:
            return OperationResult(success=False, message=str(exc))

    async def delete_record(self, entity: str, record_id: str) -> OperationResult:
        client = await self._get_client()
        csrf = await self._fetch_csrf(client)
        path = f"{self._odata_path(entity)}('{quote(record_id)}')"
        try:
            resp = await client.delete(
                path,
                headers={"X-CSRF-Token": csrf},
            )
            resp.raise_for_status()
            return OperationResult(success=True, message="Record deleted")
        except Exception as exc:
            return OperationResult(success=False, message=str(exc))

    # -- schema -----------------------------------------------------------

    async def list_entities(self) -> OperationResult:
        client = await self._get_client()
        try:
            resp = await client.get("/sap/opu/odata/sap/", params={"$format": "json"})
            resp.raise_for_status()
            body = resp.json()
            collections = body.get("d", {}).get("EntitySets", [])
            return OperationResult(success=True, data=collections)
        except Exception as exc:
            return OperationResult(success=False, message=str(exc))

    async def describe_entity(self, entity: str) -> OperationResult:
        client = await self._get_client()
        try:
            resp = await client.get(
                f"{self._odata_path(entity)}/$metadata",
                headers={"Accept": "application/xml"},
            )
            resp.raise_for_status()
            # Parse OData metadata XML into our standard field format
            fields = self._parse_metadata_xml(resp.text, entity)
            return OperationResult(
                success=True,
                data={
                    "name": entity,
                    "label": entity,
                    "key_field": fields[0]["name"] if fields else "Id",
                    "fields": fields,
                },
            )
        except Exception as exc:
            return OperationResult(success=False, message=str(exc))

    def _parse_metadata_xml(self, xml_text: str, entity: str) -> list[dict[str, Any]]:
        """Best-effort parse of OData $metadata XML → field list."""
        import re

        fields: list[dict[str, Any]] = []
        # Match Property elements
        for m in re.finditer(
            r'<Property\s+Name="([^"]+)"\s+Type="([^"]+)"([^/]*?)/?>', xml_text
        ):
            name, dtype = m.group(1), m.group(2)
            attrs = m.group(3)
            nullable = 'Nullable="false"' not in attrs
            fields.append({
                "name": name,
                "label": name,
                "data_type": dtype.split(".")[-1],
                "required": not nullable,
            })
        return fields or [{"name": "Id", "label": "Id", "data_type": "String", "required": True}]

    # -- raw --------------------------------------------------------------

    async def execute_raw(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> OperationResult:
        client = await self._get_client()
        csrf = await self._fetch_csrf(client) if method.upper() != "GET" else ""
        headers = {}
        if csrf:
            headers["X-CSRF-Token"] = csrf
        try:
            resp = await client.request(
                method.upper(), path, json=body, headers=headers
            )
            resp.raise_for_status()
            try:
                data = resp.json()
            except Exception:
                data = resp.text
            return OperationResult(success=True, data=data)
        except Exception as exc:
            return OperationResult(success=False, message=str(exc))
