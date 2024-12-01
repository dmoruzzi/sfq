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

### Querying Salesforce Data

```python
from sfq import SFAuth

# Initialize the SFAuth class with authentication details
sf = SFAuth(
    instance_url="https://example-dev-ed.trailblaze.my.salesforce.com",
    client_id="PlatformCLI",
    refresh_token="your-refresh-token-here"
)

# Execute a query to fetch account records
print(sf.query("SELECT Id FROM Account LIMIT 5"))

# Execute a query to fetch Tooling API data
print(sf.query("SELECT Id, FullName, Metadata FROM SandboxSettings LIMIT 5", tooling=True))
```

### Querying from Bash

You can easily incorporate this into ad-hoc bash scripts or commands:

```bash
python -c "from sfq import SFAuth; sf = SFAuth(instance_url='$instance_url', client_id='$client_id', refresh_token='$refresh_token'); print(sf.query('$query'))" | jq -r '.records[].Id'
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
   To get the client ID, refresh token, and instance URL, run:
   
   ```bash
   sf org display --target-org int --verbose --json
   ```

   The output will look like this:

   ```json
   {
     "status": 0,
     "result": {
       "id": "00Daa0000000000000",
       "apiVersion": "62.0",
       "accessToken": "your-access-token-here",
       "instanceUrl": "https://example-dev-ed.trailblaze.my.salesforce.com",
       "username": "user@example.com",
       "clientId": "PlatformCLI",
       "connectedStatus": "Connected",
       "sfdxAuthUrl": "force://PlatformCLI::your-refresh-token-here::https://example-dev-ed.trailblaze.my.salesforce.com",
       "alias": "int"
     }
   }
   ```

4. **Extract and Use the Tokens**:  
   The `sfdxAuthUrl` is structured as:
   
   ```
   force://<client_id>::<refresh_token>::<instance_url>
   ```

   You can extract and use the tokens in a bash script like this:

   ```bash
   query="SELECT Id FROM User WHERE IsActive = true AND Profile.Name = 'System Administrator'"

   sfdxAuthUrl=$(sf org display --target-org int --verbose --json | jq -r '.result.sfdxAuthUrl' | sed 's/force:\/\///')
   clientId=$(echo "$sfdxAuthUrl" | sed 's/::/\n/g' | sed -n '1p')
   refreshToken=$(echo "$sfdxAuthUrl" | sed 's/::/\n/g' | sed -n '2p')
   instanceUrl=$(echo "$sfdxAuthUrl" | sed 's/::/\n/g' | sed -n '3p')

   pip install sfq && python -c "from sfq import SFAuth; sf = SFAuth(instance_url='$instanceUrl', client_id='$clientId', refresh_token='$refreshToken'); print(sf.query('$query'))" | jq -r '.records[].Id'
   ```

## Notes

- **Authentication**: Make sure your refresh token is kept secure, as it grants access to your Salesforce instance.
- **Tooling API**: You can set the `tooling=True` argument in the `query` method to access the Salesforce Tooling API for more advanced metadata queries.
