# sfq

A lightweight Python library for querying Salesforce with minimal boilerplate.

## Installation

```bash
pip install sfq
```

## Quick Start

```python
from sfq import SFAuth

sf = SFAuth(
    instance_url="https://your-org.my.salesforce.com",
    client_id="PlatformCLI",
    client_secret="",
    refresh_token="your-refresh-token"
)

# Query records
result = sf.query("SELECT Id, Name FROM Account LIMIT 5")
print(result["records"])
```

## Getting Credentials

Use the Salesforce CLI to obtain authentication tokens:

```bash
# Login to your org
sf org login web --alias myorg --instance-url https://your-org.my.salesforce.com

# Display credentials
sf org display --target-org myorg --verbose --json
```

From the output, extract values from the `sfdxAuthUrl` field:
```
force://<client_id>:<client_secret>:<refresh_token>@<instance_url>
```



## Core Features

### Querying

**Single Query**
```python
result = sf.query("SELECT Id, Name FROM Account LIMIT 10")
for record in result["records"]:
    print(record["Name"])
```

**Tooling API Query**
```python
result = sf.tooling_query("SELECT Id, FullName FROM CustomObject")
```

**Batch Queries (cquery)**

Execute multiple queries efficiently using the Composite API:

```python
queries = {
    "accounts": "SELECT Id, Name FROM Account LIMIT 5",
    "contacts": "SELECT Id, Name FROM Contact LIMIT 5",
    "users": "SELECT Id, Name FROM User LIMIT 5"
}

results = sf.cquery(queries)
for name, data in results.items():
    print(f"{name}: {data['totalSize']} records")
```

### CRUD Operations

**Delete Records**
```python
result = sf.cdelete(["001xx000003DGbYAAW", "001xx000003DGbZAAW"])
# Returns: [{'id': '...', 'success': True, 'errors': []}, ...]
```

### Static Resources

```python
# Read by name
content = sf.read_static_resource_name("MyResource")

# Read by ID
content = sf.read_static_resource_id("081xx000003DGbYAAW")

# Update by name
sf.update_static_resource_name("MyResource", "<h1>New Content</h1>")

# Update by ID
sf.update_static_resource_id("081xx000003DGbYAAW", "<h1>New Content</h1>")
```

### Platform Events

```python
# List available events
events = sf.list_events()

# Publish single event
result = sf.publish("MyEvent__e", {"Message__c": "Hello!"})

# Publish batch
results = sf.publish_batch(
    [{"Message__c": "Event 1"}, {"Message__c": "Event 2"}],
    "MyEvent__e"
)
```

### sObject Key Prefixes

```python
# Get prefix -> object name mapping
prefixes = sf.get_sobject_prefixes()
# {'001': 'Account', '003': 'Contact', '005': 'User', ...}

# Get object name -> prefix mapping
prefixes = sf.get_sobject_prefixes(key_type="name")
# {'Account': '001', 'Contact': '003', 'User': '005', ...}
```

### Limits API

```python
limits = sf.limits()
print(limits["DailyApiRequests"])  # {'Max': 5000, 'Remaining': 4950}
```

### Open Frontdoor URL

Open a browser session with valid authentication:

```python
sf.open_frontdoor()
```

### MDAPI Retrieve

Retrieve metadata components:

```python
# Retrieve by type
result = sf.mdapi_retrieve(["CustomObject", "ApexClass"])

# Retrieve specific members
result = sf.mdapi_retrieve({
    "CustomObject": ["Account", "Contact"],
    "ApexClass": ["MyClass"]
})
```

### HTML Table Output

```python
result = sf.query("SELECT Id, Name FROM Account LIMIT 5")
html = sf.records_to_html_table(result["records"], styled=True)
```

## Advanced Guides

- **[Authentication Guide](docs/authentication.md)** - OAuth flows, token management, proxy configuration
- **[Platform Events Guide](docs/platform-events.md)** - Publishing and subscribing to events
- **[MDAPI Guide](docs/mdapi.md)** - Retrieving metadata components
- **[CI Integration Guide](docs/ci-integration.md)** - CI/CD tracing and custom headers
- **[Telemetry Guide](docs/telemetry.md)** - Telemetry configuration and privacy

## Exception Handling

```python
from sfq import SFAuth, AuthenticationError, QueryError, APIError

try:
    result = sf.query("SELECT Id FROM NonExistentObject")
except QueryError as e:
    print(f"Query failed: {e}")
except APIError as e:
    print(f"API error: {e}")
```

Available exceptions:
- `SFQException` - Base exception
- `AuthenticationError` - Authentication failures
- `APIError` - General API errors
- `QueryError` - Query-specific errors
- `QueryTimeoutError` - Query timeout errors
- `CRUDError` - CRUD operation errors
- `SOAPError` - SOAP API errors
- `HTTPError` - HTTP-level errors
- `ConfigurationError` - Configuration errors

## Requirements

- Python 3.9+
- No external dependencies
