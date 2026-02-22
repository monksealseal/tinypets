"""Enterprise system adapters for SAP, Salesforce, NetSuite, and Oracle."""

from enterprise_bridge.adapters.sap import SAPAdapter
from enterprise_bridge.adapters.salesforce import SalesforceAdapter
from enterprise_bridge.adapters.netsuite import NetSuiteAdapter
from enterprise_bridge.adapters.oracle import OracleAdapter

ADAPTER_REGISTRY: dict[str, type] = {
    "sap": SAPAdapter,
    "salesforce": SalesforceAdapter,
    "netsuite": NetSuiteAdapter,
    "oracle": OracleAdapter,
}

__all__ = [
    "SAPAdapter",
    "SalesforceAdapter",
    "NetSuiteAdapter",
    "OracleAdapter",
    "ADAPTER_REGISTRY",
]
