"""
Base adapter interface that all enterprise system adapters implement.

Each adapter translates the unified Enterprise Bridge API into the
vendor-specific protocol (OData, REST, SOAP, JDBC, etc.).
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ConnectionStatus(Enum):
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class OperationResult:
    """Standardised result envelope returned by every adapter operation."""

    success: bool
    data: Any = None
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "message": self.message,
            "metadata": self.metadata,
        }


class BaseAdapter(abc.ABC):
    """Abstract base class for all enterprise system adapters."""

    system_name: str = "generic"

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._status = ConnectionStatus.DISCONNECTED

    @property
    def status(self) -> ConnectionStatus:
        return self._status

    # -- lifecycle --------------------------------------------------------

    @abc.abstractmethod
    async def connect(self) -> OperationResult:
        """Establish a connection / authenticate with the remote system."""

    @abc.abstractmethod
    async def disconnect(self) -> OperationResult:
        """Tear down the connection gracefully."""

    @abc.abstractmethod
    async def health_check(self) -> OperationResult:
        """Lightweight connectivity & auth validity check."""

    # -- CRUD -------------------------------------------------------------

    @abc.abstractmethod
    async def query(
        self,
        entity: str,
        filters: dict[str, Any] | None = None,
        fields: list[str] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> OperationResult:
        """Read / list records of *entity* with optional filters."""

    @abc.abstractmethod
    async def get_record(self, entity: str, record_id: str) -> OperationResult:
        """Fetch a single record by its primary identifier."""

    @abc.abstractmethod
    async def create_record(
        self, entity: str, data: dict[str, Any]
    ) -> OperationResult:
        """Create a new record and return its id."""

    @abc.abstractmethod
    async def update_record(
        self, entity: str, record_id: str, data: dict[str, Any]
    ) -> OperationResult:
        """Update an existing record."""

    @abc.abstractmethod
    async def delete_record(self, entity: str, record_id: str) -> OperationResult:
        """Delete a record."""

    # -- schema -----------------------------------------------------------

    @abc.abstractmethod
    async def list_entities(self) -> OperationResult:
        """Return available entity / object / table names."""

    @abc.abstractmethod
    async def describe_entity(self, entity: str) -> OperationResult:
        """Return field-level schema for *entity*."""

    # -- raw / escape-hatch ----------------------------------------------

    @abc.abstractmethod
    async def execute_raw(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> OperationResult:
        """
        Send an arbitrary request through the adapter's transport layer.

        This is the escape hatch for operations not covered by the
        high-level CRUD surface.
        """
