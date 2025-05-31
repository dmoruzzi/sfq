# sfq (Salesforce Query)

sfq is a lightweight Python wrapper library designed to simplify querying Salesforce, reducing repetitive code for accessing Salesforce data.

For more varied workflows, consider using an alternative like [Simple Salesforce](https://simple-salesforce.readthedocs.io/en/stable/). This library was even referenced on the [Salesforce Developers Blog](https://developer.salesforce.com/blogs/2021/09/how-to-automate-data-extraction-from-salesforce-using-python).

## Features

- Simplified query execution for Salesforce instances.
- Integration with Salesforce authentication via refresh tokens.
- Option to interact with Salesforce Tooling API for more advanced queries.
  
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

### sObject Key Prefixes

```python
# Key prefix via IDs
print(sf.get_sobject_prefixes())
>>> {'0Pp': 'AIApplication', '6S9': 'AIApplicationConfig', '9qd': 'AIInsightAction', '9bq': 'AIInsightFeedback', '0T2': 'AIInsightReason', '9qc': 'AIInsightValue', ...}

# Key prefix via names
print(sf.get_sobject_prefixes(key_type="name"))
>>> {'AIApplication': '0Pp', 'AIApplicationConfig': '6S9', 'AIInsightAction': '9qd', 'AIInsightFeedback': '9bq', 'AIInsightReason': '0T2', 'AIInsightValue': '9qc', ...}
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
>>> [{'id': '500aj000006wtdZAAQ', 'success': True, 'errors': []}, {'id': '500aj000006wtdaAAA', 'success': True, 'errors': []}, {'id': '500aj000006wtdbAAA', 'success': True, 'errors': []}]
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

