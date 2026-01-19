# sfq (Salesforce Query)

sfq is a lightweight Python wrapper library designed to simplify querying Salesforce, reducing repetitive code for accessing Salesforce data.

For more varied workflows, consider using an alternative like [Simple Salesforce](https://simple-salesforce.readthedocs.io/en/stable/). This library was even referenced on the [Salesforce Developers Blog](https://developer.salesforce.com/blogs/2021/09/how-to-automate-data-extraction-from-salesforce-using-python).

## Features

- Simplified query execution for Salesforce instances.
- Integration with Salesforce authentication via refresh tokens.
- Option to interact with Salesforce Tooling API for more advanced queries.
- Platform Events support (list available & publish single/batch).
  
## Installation

You can install the `sfq` library using `pip`:

```bash
pip install sfq
```

## Usage

### Library Querying

```python
from sfq import SFAuth

# Initialize the SFAuth class with authentication details
sf = SFAuth(
    instance_url="https://example-dev-ed.trailblaze.my.salesforce.com",
    client_id="your-client-id-here",
    client_secret="your-client-secret-here",
    refresh_token="your-refresh-token-here"
)

# Execute a query to fetch account records
print(sf.query("SELECT Id FROM Account LIMIT 5"))

# Execute a query to fetch Tooling API data
print(sf.tooling_query("SELECT Id, FullName, Metadata FROM SandboxSettings LIMIT 5"))
```

### Composite Batch Queries

```python
multiple_queries = {
    "Recent Users": """
        SELECT Id, Name,CreatedDate
        FROM User
        ORDER BY CreatedDate DESC
        LIMIT 10""",
    "Recent Accounts": "SELECT Id, Name, CreatedDate FROM Account ORDER BY CreatedDate DESC LIMIT 10",
    "Frozen Users": "SELECT Id, UserId FROM UserLogin WHERE IsFrozen = true",  # If exceeds 2000 records, will paginate
}

batched_response = sf.cquery(multiple_queries)

for subrequest_identifer, subrequest_response in batched_response.items():
    print(f'"{subrequest_identifer}" returned {subrequest_response["totalSize"]} records')
>>> "Recent Users" returned 10 records
>>> "Recent Accounts" returned 10 records
>>> "Frozen Users" returned 4082 records
```

### Collection Deletions

```python
response = sf.cdelete(['07La0000000bYgj', '07La0000000bYgk', '07La0000000bYgl'])
>>> [{'id': '07La0000000bYgj', 'success': True, 'errors': []}, {'id': '07La0000000bYgk', 'success': True, 'errors': []}, {'id': '07La0000000bYgl', 'success': True, 'errors': []}]
```

### Static Resources

```python
page = sf.read_static_resource_id('081aj000009jUMXAA2')
print(f'Initial resource: {page}')
>>> Initial resource: <h1>It works!</h1>
sf.update_static_resource_name('HelloWorld', '<h1>Hello World</h1>')
page = sf.read_static_resource_name('HelloWorld')
print(f'Updated resource: {page}')
>>> Updated resource: <h1>Hello World</h1>
sf.update_static_resource_id('081aj000009jUMXAA2', '<h1>It works!</h1>')
```

### sObject Key Prefixes

```python
# Key prefix via IDs
print(sf.get_sobject_prefixes())
>>> {'0Pp': 'AIApplication', '6S9': 'AIApplicationConfig', '9qd': 'AIInsightAction', '9bq': 'AIInsightFeedback', '0T2': 'AIInsightReason', '9qc': 'AIInsightValue', ...}

# Key prefix via names
print(sf.get_sobject_prefixes(key_type="name"))
>>> {'AIApplication': '0Pp', 'AIApplicationConfig': '6S9', 'AIInsightAction': '9qd', 'AIInsightFeedback': '9bq', 'AIInsightReason': '0T2', 'AIInsightValue': '9qc', ...}
```

### Platform Events

Platform Events allow publishing and subscribing to real-time events. Requires a custom Platform Event (e.g., 'sfq__e' with fields like 'text__c').

```python
from sfq import SFAuth

sf = SFAuth(
    instance_url="https://example-dev-ed.trailblaze.my.salesforce.com",
    client_id="your-client-id-here",
    client_secret="your-client-secret-here",
    refresh_token="your-refresh-token-here"
)

# List available events
events = sf.list_events()
print(events)  # e.g., ['sfq__e']

# Publish single event
result = sf.publish('sfq__e', {'text__c': 'Hello Event!'})
print(result)  # {'success': True, 'id': '2Ee...'}

# Publish batch
events_data = [
    {'text__c': 'Batch 1 message'},
    {'text__c': 'Batch 2 message'}
]
batch_result = sf.publish_batch(events_data, 'sfq__e')
print(batch_result['results'])  # List of results

## How to Obtain Salesforce Tokens

To use the `sfq` library, you'll need a **client ID** and **refresh token**. The easiest way to obtain these is by using the Salesforce CLI:

### Steps to Get Tokens

1. **Install the Salesforce CLI**:  
   Follow the instructions on the [Salesforce CLI installation page](https://developer.salesforce.com/tools/salesforcecli).
   
2. **Authenticate with Salesforce**:  
   Login to your Salesforce org using the following command:
   
   ```bash
   sf org login web --alias int --instance-url https://corpa--int.sandbox.my.salesforce.com
   ```
   
3. **Display Org Details**:  
   To get the client ID, client secret, refresh token, and instance URL, run:
   
   ```bash
   sf org display --target-org int --verbose --json
   ```

   The output will look like this:

   ```json
   {
     "status": 0,
     "result": {
       "id": "00Daa0000000000000",
       "apiVersion": "63.0",
       "accessToken": "00Daa0000000000000!evaU3fYZEWGUrqI5rMtaS8KYbHfeqA7YWzMgKToOB43Jk0kj7LtiWCbJaj4owPFQ7CqpXPAGX1RDCHblfW9t8cNOCNRFng3o",
       "instanceUrl": "https://example-dev-ed.trailblaze.my.salesforce.com",
       "username": "user@example.com",
       "clientId": "PlatformCLI",
       "connectedStatus": "Connected",
       "sfdxAuthUrl": "force://PlatformCLI::nwAeSuiRqvRHrkbMmCKvLHasS0vRbh3Cf2RF41WZzmjtThnCwOuDvn9HObcUjKuTExJPqPegIwnLB5aH6GNWYhU@example-dev-ed.trailblaze.my.salesforce.com",
       "alias": "int"
     }
   }
   ```

4. **Extract and Use the Tokens**:  
   The `sfdxAuthUrl` is structured as:
   
   ```
   force://<client_id>:<client_secret>:<refresh_token>@<instance_url>
   ```

   This means with the above output sample, you would use the following information:

   ```python
   # This is for illustrative purposes; use environment variables instead
   client_id = "PlatformCLI"
   client_secret = ""
   refresh_token = "nwAeSuiRqvRHrkbMmCKvLHasS0vRbh3Cf2RF41WZzmjtThnCwOuDvn9HObcUjKuTExJPqPegIwnLB5aH6GNWYhU"
   instance_url = "https://example-dev-ed.trailblaze.my.salesforce.com"

   from sfq import SFAuth
   sf = SFAuth(
       instance_url=instance_url,
       client_id=client_id,
       client_secret=client_secret,
       refresh_token=refresh_token,
   )

   ```

## Important Considerations

- **Security**: Safeguard your client_id, client_secret, and refresh_token diligently, as they provide access to your Salesforce environment. Avoid sharing or exposing them in unsecured locations.
- **Efficient Data Retrieval**: The `query` and `cquery` function automatically handles pagination, simplifying record retrieval across large datasets. It's recommended to use the `LIMIT` clause in queries to control the volume of data returned.
- **Advanced Tooling Queries**: Utilize the `tooling_query` function to access the Salesforce Tooling API. This option is designed for performing complex operations, enhancing your data management capabilities.

## Telemetry

`sfq` includes an **HTTP event telemetry system** to gather usage insights. Telemetry is **enabled by default** to help improve the library, but you can disable it if you prefer.

### Configuration

| Variable                 | Description                                                     | Default                                           |
|--------------------------|-----------------------------------------------------------------|---------------------------------------------------|
| `SFQ_TELEMETRY`          | `0` (disabled), `1` (Standard), `2` (Debug - diagnostics, logs) | `1` (Standard)                                    |
| `SFQ_TELEMETRY_ENDPOINT` | URL to POST telemetry events                                    | `https://sfq-telemetry.moruzzi.org/api/v0/events` |
| `SFQ_TELEMETRY_SAMPLING` | Fraction of events to send (`0.0`–`1.0`)                        | `1.0`                                             |
| `SFQ_TELEMETRY_KEY`      | Optional bearer token for the telemetry endpoint                | None                                              |

### Telemetry Levels

* **Disabled (`0`)**:
  No telemetry events are sent.

* **Standard (`1`)** *(default)*:
  Sends **anonymized, non-PII events** such as method names, paths, status codes, and execution duration. Safe for general usage.

* **Debug (`2`)**:
  Sends **additional diagnostic information** and forwards log records from the library (everything). May include sensitive data (tokens, IDs, PII, stack traces). **Do not enable Debug telemetry against public endpoints.**

### Privacy & Security

* **Opt-out**: You can disable telemetry by setting `SFQ_TELEMETRY=0`.
* **Standard events** do **not** include request bodies, tokens, or user/org identifiers.
* **Debug diagnostics** are intended for internal use **only**. Route them to a trusted internal endpoint.
* Review retention and access controls on any telemetry receiver.


### Log Samples

Here are examples of telemetry log entries at different levels:

**Standard Telemetry Event:**
This includes anonymized, non-PII fields (method, status code, duration). Intended for general opt-in use.

```json
{
    "timestamp": "2025-12-29T03:48:06Z",
    "sdk": "sfq",
    "sdk_version": "0.0.47",
    "event_type": "http.request",
    "client_id": "c302d04df42738b23dbfe59688fac06367b768e180d9dfb4794a99cab41dad78",
    "telemetry_level": 1,
    "payload": {
        "method": "GET",
        "status_code": 200,
        "duration_ms": 123,
        "environment": {
            "os": "Windows",
            "os_release": "10",
            "python_version": "3.11.14",
            "sforce_client": "sfq/0.0.47"
        }
    }
}
```

**Debug Telemetry Event:**
This includes detailed request/response data and diagnostics. This is intended for opt-in use only. 

```json
{
    "timestamp": "2025-12-29T03:49:05Z",
    "sdk": "sfq",
    "sdk_version": "0.0.47",
    "event_type": "http.request",
    "client_id": "bbfd58c99e967895285d5ec5f5a9af8e2b5a040dc0bf261d64ae663e059c32f0",
    "telemetry_level": 2,
    "payload": {
        "method": "GET",
        "status": 200,
        "duration_ms": 242,
        "request_headers": {
            "User-Agent": "sfq/0.0.47",
            "Sforce-Call-Options": "client=sfq/0.0.47",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": "REDACTED"
        },
        "environment": {
            "os": "Windows",
            "os_release": "10",
            "python_version": "3.11.14",
            "user_agent": "sfq/0.0.47",
            "sforce_client": "sfq/0.0.47"
        },
        "path_hash": "119a7bffe38631d987935f5f88effb89fe9267993fa4b459f712a993ef5859f0"
    }
}
```

The following fields appear in telemetry events; below are concise explanations to help you interpret them:

- `timestamp`: ISO 8601 timestamp (UTC) when the event was generated.
- `sdk`: The SDK name that generated the event (this library: `sfq`).
- `sdk_version`: Version of the SDK (semantic version string).
- `sfk_version`: Alias for `sdk_version` (included for compatibility with some consumers).
- `event_type`: Logical event category (e.g., `http.request`, `log.record`).
- `client_id`: Anonymous identifier generated **at runtime** for the current client instance (SHA-256 of a UUID). This ID is **not persisted** across runs and **cannot be traced** to any user or organization data. Its purpose is to provide a temporary, unique identifier for telemetry events.
- `telemetry_level`: Telemetry level active for the client (0=disabled, 1=Standard, 2=Debug).

- `payload.method`: HTTP method used (e.g., `GET`, `POST`, `PUT`, `DELETE`).
- `payload.status` / `payload.status_code`: HTTP response status code (when available).
- `payload.duration_ms`: Duration of the operation in milliseconds (when available).
- `payload.environment`: Small environment summary containing:
    - `os`: OS name (e.g., `Windows`, `Linux`).
    - `os_release`: OS release string (e.g., `10`).
    - `python_version`: Python runtime version (e.g., `3.11.14`).
    - `user_agent`: (Debug telemetry only) User-Agent header value when available.
    - `sforce_client`: (Debug telemetry only) extracted `client=` value from `Sforce-Call-Options` header when available.

- `payload.path_hash` (Debug telemetry only): SHA-256 hash of the sanitized path string. The raw request path/URL is never included in Standard telemetry (level 1); Debug telemetry (level 2) includes only this hash to allow grouping without sending identifying path components.

If you need more detail for debugging, enable Debug telemetry (`SFQ_TELEMETRY=2`) and route events to a trusted internal endpoint via `SFQ_TELEMETRY_ENDPOINT`. To disable telemetry entirely, set `SFQ_TELEMETRY=0`.

## CI-Aware HTTP Header Attachment

`sfq` automatically attaches traceable CI metadata to outbound HTTP requests when running in CI environments. This enables request tracking and correlation across systems through the `AdditionalInfo` fields for ApiEvent and LoginEvent.

### How It Works

When running in a CI environment, `sfq` automatically detects the CI provider and attaches non-PII metadata headers to all HTTP requests. 

### Supported CI Providers

| CI Provider    | Detection Variable | Value  |
|----------------|--------------------|--------|
| GitHub Actions | `GITHUB_ACTIONS`   | `true` |
| GitLab CI      | `GITLAB_CI`        | `true` |
| CircleCI       | `CIRCLECI`         | `true` |

### Header Format

All CI metadata uses the `x-sfdc-addinfo-` prefix:

```
x-sfdc-addinfo-ci_provider: github
x-sfdc-addinfo-run_id: 123456
x-sfdc-addinfo-repository: org_repo
x-sfdc-addinfo-workflow: Release
x-sfdc-addinfo-ref: refs_heads_main
x-sfdc-addinfo-runner_os: Linux
```

### Non-PII Metadata

The following metadata is automatically included when available:

**GitHub Actions:**
- `GITHUB_RUN_ID` → `x-sfdc-addinfo-run_id`
- `GITHUB_REPOSITORY` → `x-sfdc-addinfo-repository`
- `GITHUB_WORKFLOW` → `x-sfdc-addinfo-workflow`
- `GITHUB_REF` → `x-sfdc-addinfo-ref`
- `RUNNER_OS` → `x-sfdc-addinfo-runner_os`

**GitLab CI:**
- `CI_PIPELINE_ID` → `x-sfdc-addinfo-pipeline_id`
- `CI_PROJECT_PATH` → `x-sfdc-addinfo-project_path`
- `CI_JOB_NAME` → `x-sfdc-addinfo-job_name`
- `CI_COMMIT_REF_NAME` → `x-sfdc-addinfo-commit_ref_name`
- `CI_RUNNER_ID` → `x-sfdc-addinfo-runner_id`

**CircleCI:**
- `CIRCLE_WORKFLOW_ID` → `x-sfdc-addinfo-workflow_id`
- `CIRCLE_PROJECT_REPONAME` → `x-sfdc-addinfo-project_reponame`
- `CIRCLE_BRANCH` → `x-sfdc-addinfo-branch`
- `CIRCLE_BUILD_NUM` → `x-sfdc-addinfo-build_num`

### PII Metadata 

PII headers are not included by default. To include them, set the environment variable:

```bash
export SFQ_ATTACH_CI_PII=true
```

**GitHub Actions PII:**
- `GITHUB_ACTOR` → `x-sfdc-addinfo-pii-actor`
- `GITHUB_ACTOR_ID` → `x-sfdc-addinfo-pii-actor_id`
- `GITHUB_TRIGGERING_ACTOR` → `x-sfdc-addinfo-pii-triggering_actor`

**GitLab CI PII:**
- `GITLAB_USER_LOGIN` → `x-sfdc-addinfo-pii-user_login`
- `GITLAB_USER_NAME` → `x-sfdc-addinfo-pii-user_name`
- `GITLAB_USER_EMAIL` → `x-sfdc-addinfo-pii-user_email`
- `GITLAB_USER_ID` → `x-sfdc-addinfo-pii-user_id`

**CircleCI PII:**
- `CIRCLE_USERNAME` → `x-sfdc-addinfo-pii-username`

### Configuration

| Variable            | Description                                   | Default |
|---------------------|-----------------------------------------------|---------|
| `SFQ_ATTACH_CI_PII` | Include PII headers (`true`, `1`, `yes`, `y`) | `false` |
| `SFQ_ATTACH_CI`     | Include CI headers (`true`, `1`, `yes`, `y`)  | `true`  |

## Custom Addinfo Headers

`sfq` supports injecting arbitrary custom headers into HTTP requests using the `SFQ_HEADERS` environment variable. This allows you to add custom metadata to all API requests, which appears in the `AdditionalInfo` fields for ApiEvent and LoginEvent.

### How It Works

The `SFQ_HEADERS` environment variable allows you to specify custom key-value pairs that will be converted into `x-sfdc-addinfo-` headers and attached to all HTTP requests.

### Usage

Set the `SFQ_HEADERS` environment variable using the format `key1:value1|key2:value2`:

```bash
export SFQ_HEADERS="custom_key:custom_value|another_header:another_value"
```

This will create the following HTTP headers:

```
x-sfdc-addinfo-custom_key: custom_value
x-sfdc-addinfo-another_header: another_value
```

### Example

```python
import os
from sfq import SFAuth

# Set custom headers
os.environ['SFQ_HEADERS'] = "deployment_id:deploy-123|environment:production|team:data-engineering"

# Initialize SFAuth
sf = SFAuth(
    instance_url="https://example-dev-ed.trailblaze.my.salesforce.com",
    client_id="your-client-id-here",
    client_secret="your-client-secret-here",
    refresh_token="your-refresh-token-here"
)

# All queries will now include the custom headers
result = sf.query("SELECT Id FROM Account LIMIT 5")
```

### Features

- **Multiple Headers**: Separate multiple key-value pairs with `|`
- **Value Support**: Values can contain spaces, equals signs, and other special characters
- **Empty Handling**: Empty keys or values are automatically ignored
- **Automatic Integration**: Headers are automatically added to all HTTP requests

### Configuration

| Variable      | Description                                        | Default |
|---------------|----------------------------------------------------|---------|
| `SFQ_HEADERS` | Custom headers in format `key1:value1|key2:value2` | None    |

### Use Cases

- **Deployment Tracking**: Add deployment IDs to track which deployment made API calls
- **Environment Identification**: Identify requests from different environments (dev, staging, prod)
- **Team Attribution**: Track which team or service is making requests
- **Custom Metadata**: Add any custom metadata needed for tracking and debugging

