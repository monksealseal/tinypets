# Enterprise Bridge

MCP server that gives Claude Code native access to enterprise systems — **SAP**, **Salesforce**, **NetSuite**, and **Oracle**.

Once configured, you can talk to Claude Code in natural language and it will read, write, query, and manage data across all four platforms through a single, unified interface.

## How it works

Enterprise Bridge runs as an [MCP (Model Context Protocol)](https://modelcontextprotocol.io) server.  When registered in your Claude Code configuration, it exposes 14 tools that Claude can call directly:

| Tool | Description |
|------|-------------|
| `enterprise_configure` | Load connection profiles |
| `enterprise_list_connections` | List available connections |
| `enterprise_connect` | Connect to a system |
| `enterprise_health_check` | Verify connectivity |
| `enterprise_list_entities` | Discover entities/objects/tables |
| `enterprise_describe_entity` | Get field-level schema |
| `enterprise_search_fields` | Find fields by keyword |
| `enterprise_query` | Query records with filters |
| `enterprise_get_record` | Fetch a single record |
| `enterprise_create_record` | Create a record |
| `enterprise_update_record` | Update a record |
| `enterprise_delete_record` | Delete a record |
| `enterprise_aggregate` | Run count/sum/avg/min/max |
| `enterprise_raw_request` | Send arbitrary API requests |

## Quick start

### 1. Install

```bash
pip install -e ".[dev]"
```

### 2. Configure connections

Generate a template:

```bash
enterprise-bridge init
```

This creates `~/.enterprise-bridge/config.yaml`.  Edit it with your connection details:

```yaml
connections:
  my_salesforce:
    system: salesforce
    base_url: https://myorg.my.salesforce.com
    auth:
      type: oauth2_client_credentials
      token_url: https://login.salesforce.com/services/oauth2/token
      client_id: YOUR_CLIENT_ID
      client_secret: YOUR_CLIENT_SECRET

  my_sap:
    system: sap
    base_url: https://my-sap.s4hana.cloud.sap
    auth:
      type: oauth2_client_credentials
      token_url: https://my-sap.authentication.eu10.hana.ondemand.com/oauth/token
      client_id: YOUR_CLIENT_ID
      client_secret: YOUR_CLIENT_SECRET

  my_netsuite:
    system: netsuite
    base_url: https://123456.suitetalk.api.netsuite.com
    auth:
      type: oauth2_client_credentials
      token_url: https://123456.suitetalk.api.netsuite.com/services/rest/auth/oauth2/v1/token
      client_id: YOUR_CLIENT_ID
      client_secret: YOUR_CLIENT_SECRET
    options:
      account_id: "123456"

  my_oracle:
    system: oracle
    base_url: https://myinstance.fa.us2.oraclecloud.com
    auth:
      type: basic
      username: YOUR_USERNAME
      password: YOUR_PASSWORD
```

Credentials can also be passed via environment variables:

```bash
export EB_MY_SALESFORCE_CLIENT_ID=...
export EB_MY_SALESFORCE_CLIENT_SECRET=...
```

### 3. Test connections

```bash
enterprise-bridge test
```

### 4. Register with Claude Code

Add to your Claude Code MCP settings (`.claude/mcp.json` or equivalent):

```json
{
  "mcpServers": {
    "enterprise-bridge": {
      "command": "python",
      "args": ["-m", "enterprise_bridge"],
      "env": {}
    }
  }
}
```

That's it. Claude Code now has native access to your enterprise systems.

## Usage examples

Once configured, just talk to Claude normally:

> "Show me all Salesforce accounts in the Technology industry with revenue over $1M"

> "Create a new vendor in SAP with company name 'Acme Corp'"

> "What fields are available on the NetSuite customer record?"

> "Get the Oracle purchase order with ID 300000047804082"

> "What's the total revenue across all Salesforce opportunities this quarter?"

Claude will automatically discover schemas, build the right queries, and return the results.

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  Claude Code                     │
│                                                  │
│  "Show me all SAP vendors with revenue > $1M"   │
└──────────────────────┬──────────────────────────┘
                       │ MCP (stdio / SSE)
┌──────────────────────▼──────────────────────────┐
│              Enterprise Bridge                    │
│                MCP Server                        │
│                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │  Query   │  │  Schema  │  │   Auth   │      │
│  │  Engine  │  │  Cache   │  │ Manager  │      │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘      │
│       │              │              │            │
│  ┌────▼──────────────▼──────────────▼────┐      │
│  │          Adapter Layer                 │      │
│  │  ┌─────┐ ┌────┐ ┌───────┐ ┌──────┐  │      │
│  │  │ SAP │ │ SF │ │  NS   │ │  ORA │  │      │
│  │  └──┬──┘ └─┬──┘ └──┬────┘ └──┬───┘  │      │
│  └─────┼──────┼───────┼─────────┼───────┘      │
└────────┼──────┼───────┼─────────┼───────────────┘
         │      │       │         │
    OData V2  REST    SuiteQL   REST
     HTTPS    API      API      API
         │      │       │         │
    ┌────▼┐ ┌──▼──┐ ┌──▼───┐ ┌──▼────┐
    │ SAP │ │ SF  │ │  NS  │ │Oracle │
    │S/4H │ │Cloud│ │Cloud │ │Fusion │
    └─────┘ └─────┘ └──────┘ └───────┘
```

## Supported systems

| System | Protocol | Auth methods | Key features |
|--------|----------|-------------|--------------|
| **SAP S/4HANA** | OData V2/V4 | OAuth 2.0, Basic, JWT | CSRF tokens, $metadata parsing |
| **Salesforce** | REST/SOQL | OAuth 2.0, JWT-bearer | SOQL generation, sObject describe |
| **NetSuite** | REST + SuiteQL | OAuth 2.0, Token-based | SuiteQL generation, metadata catalog |
| **Oracle Fusion** | REST | OAuth 2.0, Basic | Finder queries, resource describe |

## Supported auth types

- `oauth2_client_credentials` — Standard OAuth 2.0 client credentials flow
- `oauth2_jwt_bearer` — JWT bearer token flow (Salesforce connected apps, SAP BTP)
- `basic` — HTTP Basic authentication
- `api_key` — Static API key / token

## CLI commands

```bash
enterprise-bridge init       # Generate config template
enterprise-bridge test       # Test all connections
enterprise-bridge query      # Run a query from the command line
enterprise-bridge describe   # Describe an entity's schema
enterprise-bridge serve      # Start the MCP server manually
```

## Filter operators

When querying through Claude or the CLI, filters support these operators:

| Suffix | Meaning | Example |
|--------|---------|---------|
| *(none)* | Equals | `{"Status": "Active"}` |
| `__gt` | Greater than | `{"Revenue__gt": 1000000}` |
| `__gte` | Greater than or equal | `{"Count__gte": 10}` |
| `__lt` | Less than | `{"Price__lt": 50}` |
| `__lte` | Less than or equal | `{"Score__lte": 100}` |
| `__ne` | Not equal | `{"Status__ne": "Closed"}` |
| `__in` | In list | `{"Region__in": ["US", "EU"]}` |
| `__like` | Substring match | `{"Name__like": "Acme"}` |
| `__null` | Is null / not null | `{"Email__null": true}` |

## Running tests

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT
