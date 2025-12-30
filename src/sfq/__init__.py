"""
.. include:: ../../README.md
"""

import webbrowser
from typing import Any, Dict, Generator, Iterable, List, Literal, Optional
from urllib.parse import quote

# Import new modular components
from .auth import AuthManager
from .crud import CRUDClient

# Import platform events support
from .platform_events import PlatformEventsClient

# Re-export all public classes and functions for backward compatibility
from .exceptions import (
    APIError,
    AuthenticationError,
    ConfigurationError,
    CRUDError,
    HTTPError,
    QueryError,
    QueryTimeoutError,
    SFQException,
    SOAPError,
)
from .http_client import HTTPClient
from .query import QueryClient
from .soap import SOAPClient
from .utils import get_logger, records_to_html_table
from .debug_cleanup import DebugCleanup
from .mdapi import mdapi_retrieve, unpack_mdapi_zip

# Re-export PlatformEventsClient for direct import
from .platform_events import PlatformEventsClient

# Define public API for documentation tools
__all__ = [
    "SFAuth",
    # Exception classes
    "SFQException",
    "AuthenticationError",
    "APIError",
    "QueryError",
    "QueryTimeoutError",
    "CRUDError",
    "SOAPError",
    "HTTPError",
    "ConfigurationError",
    # Package metadata
    "__version__",
    "PlatformEventsClient",
    # MDAPI helpers
    "mdapi_retrieve",
    "unpack_mdapi_zip",
]

__version__ = "0.0.48"
"""
### `__version__`

**The version of the sfq library.**
- Schema: `MAJOR.MINOR.PATCH`
- Used for debugging and compatibility checks
- Updated to reflect the current library version via CI/CD automation
"""
logger = get_logger("sfq")

class _SFTokenAuth:
    def __init__(
        self,
        instance_url: str,
        access_token: str,
        api_version: str = "v65.0",
        token_endpoint: str = "/services/oauth2/token",
        user_agent: str = "sfq/0.0.48",
        sforce_client: str = "_auto",
        proxy: str = "_auto",
    ) -> None:
        from . import SFAuth

        self._sf_auth = SFAuth(
            instance_url=instance_url,
            client_id="_",
            refresh_token="_",
            client_secret=str("_").strip(),
            api_version=api_version,
            token_endpoint=token_endpoint,
            access_token=access_token,
            token_expiration_time=-1.0,
            user_agent=user_agent,
            sforce_client=sforce_client,
            proxy=proxy,
        )

        self._sf_auth._auth_manager.access_token = access_token
        self._sf_auth._auth_manager.token_expiration_time = -1.0

    def __getattr__(self, name: str) -> Any:
        return getattr(self._sf_auth, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_sf_auth":
            super().__setattr__(name, value)
        else:
            setattr(self._sf_auth, name, value)

class SFAuth:
    def __init__(
        self,
        instance_url: str,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        api_version: str = "v65.0",
        token_endpoint: str = "/services/oauth2/token",
        access_token: Optional[str] = None,
        token_expiration_time: Optional[float] = None,
        token_lifetime: int = 15 * 60,
        user_agent: str = "sfq/0.0.48",
        sforce_client: str = "_auto",
        proxy: str = "_auto",
    ) -> None:
        """
        Initializes the SFAuth with necessary parameters.

        :param instance_url: The Salesforce instance URL.
        :param client_id: The client ID for OAuth.
        :param refresh_token: The refresh token for OAuth.
        :param client_secret: The client secret for OAuth.
        :param api_version: The Salesforce API version.
        :param token_endpoint: The token endpoint.
        :param access_token: The access token for the current session.
        :param token_expiration_time: The expiration time of the access token.
        :param token_lifetime: The lifetime of the access token in seconds.
        :param user_agent: Custom User-Agent string.
        :param sforce_client: Custom Application Identifier.
        :param proxy: The proxy configuration, "_auto" to use environment.
        """
        # Initialize the AuthManager with all authentication-related parameters
        self._auth_manager = AuthManager(
            instance_url=instance_url,
            client_id=client_id,
            refresh_token=refresh_token,
            client_secret=str(client_secret).strip(),
            api_version=api_version,
            token_endpoint=token_endpoint,
            access_token=access_token,
            token_expiration_time=token_expiration_time,
            token_lifetime=token_lifetime,
            proxy=proxy,
        )

        # Initialize the HTTPClient with auth manager and user agent settings
        self._http_client = HTTPClient(
            auth_manager=self._auth_manager,
            user_agent=user_agent,
            sforce_client=sforce_client,
            high_api_usage_threshold=80,
        )

        # Initialize the SOAPClient
        self._soap_client = SOAPClient(
            http_client=self._http_client,
            api_version=api_version,
        )

        # Initialize the QueryClient
        self._query_client = QueryClient(
            http_client=self._http_client,
            api_version=api_version,
        )

        # Initialize the CRUDClient
        self._crud_client = CRUDClient(
            http_client=self._http_client,
            soap_client=self._soap_client,
            api_version=api_version,
        )

        # Initialize the DebugCleanup
        self._debug_cleanup = DebugCleanup(sf_auth=self)

        # Initialize the PlatformEventsClient
        self._platform_events_client = PlatformEventsClient(
            http_client=self._http_client,
            api_version=api_version,
        )

        # Store version information
        self.__version__ = "0.0.48"
        """
        ### `__version__`
        
        **The version of the sfq library.**
        - Schema: `MAJOR.MINOR.PATCH`
        - Used for debugging and compatibility checks
        - Updated to reflect the current library version via CI/CD automation
        """

    # Property delegation to preserve all existing public attributes
    @property
    def instance_url(self) -> str:
        """
        ### `instance_url`
        **The fully qualified Salesforce instance URL.**

        - Should end with `.my.salesforce.com`
        - No trailing slash

        **Examples:**
        - `https://sfq-dev-ed.trailblazer.my.salesforce.com`
        - `https://sfq.my.salesforce.com`
        - `https://sfq--dev.sandbox.my.salesforce.com`
        """
        return self._auth_manager.instance_url

    @property
    def client_id(self) -> str:
        """
        ### `client_id`
        **The OAuth client ID.**

        - Uniquely identifies your **Connected App** in Salesforce
        - If using **Salesforce CLI**, this is `"PlatformCLI"`
        - For other apps, find this value in the **Connected App details**
        """
        return self._auth_manager.client_id

    @property
    def client_secret(self) -> str:
        """
        ### `client_secret`
        **The OAuth client secret.**

        - Secret key associated with your Connected App
        - For **Salesforce CLI**, this is typically an empty string `""`
        - For custom apps, locate it in the **Connected App settings**
        """
        return self._auth_manager.client_secret

    @property
    def refresh_token(self) -> str:
        """
        ### `refresh_token`
        **The OAuth refresh token.**

        - Used to fetch new access tokens when the current one expires
        - For CLI, obtain via:

          ```bash
          sf org display --json
        ````

        * For other apps, this value is returned during the **OAuth authorization flow**
            * 📖 [Salesforce OAuth Flows Documentation](https://help.salesforce.com/s/articleView?id=xcloud.remoteaccess_oauth_flows.htm&type=5)
        """
        return self._auth_manager.refresh_token

    @property
    def api_version(self) -> str:
        """
        ### `api_version`

        **The Salesforce API version to use.**

        * Must include the `"v"` prefix (e.g., `"v65.0"`)
        * Periodically updated to align with new Salesforce releases
        """
        return self._auth_manager.api_version

    @property
    def token_endpoint(self) -> str:
        """
        ### `token_endpoint`

        **The token URL path for OAuth authentication.**

        * Defaults to Salesforce's `.well-known/openid-configuration` for *token* endpoint
        * Should start with a **leading slash**, e.g., `/services/oauth2/token`
        * No customization is typical, but internal designs may use custom ApexRest endpoints
        """
        return self._auth_manager.token_endpoint

    @property
    def access_token(self) -> Optional[str]:
        """
        ### `access_token`

        **The current OAuth access token.**

        * Used to authorize API requests
        * Does not include Bearer prefix, strictly the token
        """
        # refresh token if required

        return self._auth_manager.access_token

    @property
    def token_expiration_time(self) -> Optional[float]:
        """
        ### `token_expiration_time`

        **Unix timestamp (in seconds) for access token expiration.**

        * Managed automatically by the library
        * Useful for checking when to refresh the token
        """
        return self._auth_manager.token_expiration_time

    @property
    def token_lifetime(self) -> int:
        """
        ### `token_lifetime`

        **Access token lifespan in seconds.**

        * Determined by your Connected App's session policies
        * Used to calculate when to refresh the token
        """
        return self._auth_manager.token_lifetime

    @property
    def user_agent(self) -> str:
        """
        ### `user_agent`

        **Custom User-Agent string for API calls.**

        * Included in HTTP request headers
        * Useful for identifying traffic in Salesforce `ApiEvent` logs
        """
        return self._http_client.user_agent

    @property
    def sforce_client(self) -> str:
        """
        ### `sforce_client`

        **Custom application identifier.**

        * Included in the `Sforce-Call-Options` header
        * Useful for identifying traffic in Event Log Files
        * Commas are not allowed; will be stripped
        """
        return self._http_client.sforce_client

    @property
    def proxy(self) -> Optional[str]:
        """
        ### `proxy`

        **The proxy configuration.**

        * Proxy URL for HTTP requests
        * None if no proxy is configured
        """
        return self._auth_manager.get_proxy_config()

    @property
    def org_id(self) -> Optional[str]:
        """
        ### `org_id`

        **The Salesforce organization ID.**

        * Extracted from token response during authentication
        * Available after successful token refresh
        """
        return self._auth_manager.org_id

    @property
    def platform_events(self):
        """
        Access to the PlatformEventsClient for advanced usage.

        :return: The PlatformEventsClient instance.
        """
        return self._platform_events_client

    @property
    def user_id(self) -> Optional[str]:
        """
        ### `user_id`

        **The Salesforce user ID.**

        * Extracted from token response during authentication
        * Available after successful token refresh
        """
        return self._auth_manager.user_id

    # Token refresh method that delegates to HTTP client
    def _refresh_token_if_needed(self) -> Optional[str]:
        """
        Automatically refresh the access token if it has expired or is missing.

        :return: A valid access token or None if refresh failed.
        """
        return self._http_client.refresh_token_and_update_auth()

    def read_static_resource_name(
        self, resource_name: str, namespace: Optional[str] = None
    ) -> Optional[str]:
        """
        Read a static resource for a given name from the Salesforce instance.

        :param resource_name: Name of the static resource to read.
        :param namespace: Namespace of the static resource to read (default is None).
        :return: Static resource content or None on failure.
        """
        return self._crud_client.read_static_resource_name(resource_name, namespace)

    def read_static_resource_id(self, resource_id: str) -> Optional[str]:
        """
        Read a static resource for a given ID from the Salesforce instance.

        :param resource_id: ID of the static resource to read.
        :return: Static resource content or None on failure.
        """
        return self._crud_client.read_static_resource_id(resource_id)

    def update_static_resource_name(
        self, resource_name: str, data: str, namespace: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Update a static resource for a given name in the Salesforce instance.

        :param resource_name: Name of the static resource to update.
        :param data: Content to update the static resource with.
        :param namespace: Optional namespace to search for the static resource.
        :return: Static resource content or None on failure.
        """
        return self._crud_client.update_static_resource_name(
            resource_name, data, namespace
        )

    def update_static_resource_id(
        self, resource_id: str, data: str
    ) -> Optional[Dict[str, Any]]:
        """
        Replace the content of a static resource in the Salesforce instance by ID.

        :param resource_id: ID of the static resource to update.
        :param data: Content to update the static resource with.
        :return: Parsed JSON response or None on failure.
        """
        return self._crud_client.update_static_resource_id(resource_id, data)

    def limits(self) -> Optional[Dict[str, Any]]:
        """
        Fetch the current limits for the Salesforce instance.

        :return: Parsed JSON response or None on failure.
        """
        endpoint = f"/services/data/{self.api_version}/limits"

        # Ensure we have a valid token
        self._refresh_token_if_needed()

        status, data = self._http_client.send_authenticated_request("GET", endpoint)

        if status == 200:
            import json

            logger.debug("Limits fetched successfully.")
            return json.loads(data)

        logger.error("Failed to fetch limits: %s", status)
        return None

    def query(self, query: str, tooling: bool = False) -> Optional[Dict[str, Any]]:
        """
        Execute a SOQL query using the REST or Tooling API.

        :param query: The SOQL query string.
        :param tooling: If True, use the Tooling API endpoint.
        :return: Parsed JSON response or None on failure.
        """
        return self._query_client.query(query, tooling)

    def tooling_query(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Execute a SOQL query using the Tooling API.

        :param query: The SOQL query string.
        :return: Parsed JSON response or None on failure.
        """
        return self._query_client.tooling_query(query)

    def get_sobject_prefixes(
        self, key_type: Literal["id", "name"] = "id"
    ) -> Optional[Dict[str, str]]:
        """
        Fetch all key prefixes from the Salesforce instance and map them to sObject names or vice versa.

        :param key_type: The type of key to return. Either 'id' (prefix) or 'name' (sObject).
        :return: A dictionary mapping key prefixes to sObject names or None on failure.
        """
        return self._query_client.get_sobject_prefixes(key_type)

    def cquery(
        self,
        query_dict: Dict[str, str],
        batch_size: int = 25,
        max_workers: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Execute multiple SOQL queries using the Composite Batch API with threading to reduce network overhead.
        The function returns a dictionary mapping the original keys to their corresponding batch response.
        The function requires a dictionary of SOQL queries with keys as logical names (referenceId) and values as SOQL queries.
        Each query (subrequest) is counted as a unique API request against Salesforce governance limits.

        :param query_dict: A dictionary of SOQL queries with keys as logical names and values as SOQL queries.
        :param batch_size: The number of queries to include in each batch (default is 25).
        :param max_workers: The maximum number of threads to spawn for concurrent execution (default is None).
        :return: Dict mapping the original keys to their corresponding batch response or None on failure.
        """
        return self._query_client.cquery(query_dict, batch_size, max_workers)

    def cdelete(
        self,
        ids: Iterable[str],
        batch_size: int = 200,
        max_workers: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Execute the Collections Delete API to delete multiple records using multithreading.

        :param ids: A list of record IDs to delete.
        :param batch_size: The number of records to delete in each batch (default is 200).
        :param max_workers: The maximum number of threads to spawn for concurrent execution (default is None).
        :return: Combined JSON response from all batches or None on complete failure.
        """
        return self._crud_client.cdelete(ids, batch_size, max_workers)

    def _cupdate(
        self,
        update_dict: Dict[str, Any],
        batch_size: int = 25,
        max_workers: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Execute the Composite Update API to update multiple records.

        :param update_dict: A dictionary of keys of records to be updated, and a dictionary of field-value pairs to be updated, with a special key '_' overriding the sObject type which is otherwise inferred from the key.
        :param batch_size: The number of records to update in each batch (default is 25).
        :param max_workers: The maximum number of threads to spawn for concurrent execution (default is None).
        :return: JSON response from the update request or None on failure.
        """
        return self._crud_client.cupdate(update_dict, batch_size, max_workers)

    # SOAP methods delegated to SOAP client
    def _gen_soap_envelope(self, header: str, body: str, api_type: str) -> str:
        """Generates a full SOAP envelope with all required namespaces for Salesforce API."""
        return self._soap_client.generate_soap_envelope(header, body, api_type)

    def _gen_soap_header(self) -> str:
        """This function generates the header for the SOAP request."""
        # Ensure we have a valid token
        self._refresh_token_if_needed()
        return self._soap_client.generate_soap_header(self.access_token)

    def _extract_soap_result_fields(self, xml_string: str) -> Optional[Dict[str, Any]]:
        """Parse SOAP XML and extract all child fields from <result> as a dict."""
        return self._soap_client.extract_soap_result_fields(xml_string)

    def _gen_soap_body(self, sobject: str, method: str, data: Dict[str, Any]) -> str:
        """Generates a compact SOAP request body for one or more records."""
        return self._soap_client.generate_soap_body(sobject, method, data)

    def _xml_to_json(self, xml_string: str) -> Optional[Dict[str, Any]]:
        """Convert an XML string to a JSON-like dictionary."""
        return self._soap_client.xml_to_dict(xml_string)

    def _xml_to_dict(self, element) -> Dict[str, Any]:
        """Recursively convert an XML Element to a dictionary."""
        return self._soap_client._xml_element_to_dict(element)

    def _create(  # I don't like this name, will think of a better one later...as such, not public.
        self,
        sobject: str,
        insert_list: List[Dict[str, Any]],
        batch_size: int = 200,
        max_workers: Optional[int] = None,
        api_type: Literal["enterprise", "tooling"] = "enterprise",
    ) -> Optional[Dict[str, Any]]:
        """
        Execute the Insert API to insert multiple records via SOAP calls.

        :param sobject: The name of the sObject to insert into.
        :param insert_list: A list of dictionaries, each representing a record to insert.
        :param batch_size: The number of records to insert in each batch (default is 200).
        :param max_workers: The maximum number of threads to spawn for concurrent execution (default is None).
        :param api_type: API type to use ('enterprise' or 'tooling').
        :return: JSON response from the insert request or None on failure.
        """
        return self._crud_client.create(
            sobject, insert_list, batch_size, max_workers, api_type
        )

    def debug_cleanup(
        self,
        apex_logs: bool = True,
        expired_apex_flags: bool = True,
        all_apex_flags: bool = False,
    ) -> None:
        """
        Perform cleanup operations for Apex debug logs.
        """
        self._debug_cleanup.debug_cleanup(
            apex_logs=apex_logs,
            expired_apex_flags=expired_apex_flags,
            all_apex_flags=all_apex_flags,
        )

    def open_frontdoor(self) -> None:
        """
        This function opens the Salesforce Frontdoor URL in the default web browser.
        """
        self._refresh_token_if_needed()
        if not self.access_token:
            logger.error("No access token available for frontdoor URL")
            return

        sid = quote(self.access_token, safe="")
        frontdoor_url = f"{self.instance_url}/secur/frontdoor.jsp?sid={sid}"
        webbrowser.open(frontdoor_url)

    def records_to_html_table(
        self,
        items: List[Dict[str, Any]],
        headers: Dict[str, str] = None,
        styled: bool = False,
    ) -> str:
        """
        Convert a list of dictionaries to an HTML table.

        :param items: List of dictionaries to convert.
        :param styled: If True, apply basic CSS styles to the table.
        :return: HTML string representing the table.
        """
        if "records" in items:
            items = items["records"]
        return records_to_html_table(items, headers=headers, styled=styled)

    def list_events(self) -> Optional[List[str]]:
        """
        List available Platform Events in the Salesforce org.

        :return: List of event API names (e.g., ['sfq__e']) or None on failure.
        """
        return self._platform_events_client.list_events()

    def publish(
        self,
        event_name: str,
        event_data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Publish a single Platform Event.

        :param event_name: The API name of the Platform Event (e.g., 'sfq__e').
        :param event_data: Dict of field values for the event (e.g., {'text__c': 'value'}).
        :return: Response dict with 'success', 'id', etc., or None on failure.
        """
        self._refresh_token_if_needed()
        return self._platform_events_client.publish(event_name, event_data)

    def publish_batch(
        self,
        events: List[Dict[str, Any]],
        event_name: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Publish a batch of Platform Events.

        :param events: List of event data dicts (each with field values).
        :param event_name: The API name of the Platform Event (e.g., 'sfq__e').
        :return: Dict with 'results': list of individual results, or None on failure.
        """
        self._refresh_token_if_needed()
        return self._platform_events_client.publish_batch(events, event_name)

    def _subscribe(
        self,
        event_name: str,
        queue_timeout: int = 90,
        max_runtime: Optional[int] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Subscribe to a Platform Event topic and yield incoming events.

        Uses the CometD long-polling Streaming API. Topic format:
        '/event/{EventName}'.

        :param event_name: The Platform Event API name (e.g., 'MyEvent__e')
        :param queue_timeout: Seconds to wait for messages before heartbeat log
        :param max_runtime: Max seconds to listen (None for unlimited)
        :yields: Event dicts with channel and data
        """
        self._refresh_token_if_needed()
        yield from self._platform_events_client.subscribe(
            event_name, queue_timeout=queue_timeout, max_runtime=max_runtime
        )

    def mdapi_retrieve(
        self,
        package: Dict[str, Any] | List[str],
        mdapi_version: str | None = None,
        poll_interval_seconds: float = 3.0,
        max_poll_seconds: float = 600.0,
        raw_response: bool = False,
        raw_bytes: bool = False,
    ):
        """
        Retrieve metadata via the Salesforce Metadata API (MDAPI).

        This is a convenience wrapper over the top-level mdapi_retrieve() helper
        that is wired to this SFAuth instance.

        Args:
            package: Either:
                - dict[str, list[str] | str]: mapping metadata types to members, or
                - list[str]: list of metadata types (interpreted as wildcard "*").
            mdapi_version: Metadata API version, e.g. "v65.0".
            poll_interval_seconds: Delay between polling attempts.
            max_poll_seconds: Max total time to poll before aborting.

        Returns:
            BytesIO containing the retrieved ZIP file (not decompressed).

        Raises:
            SOAPError on failure or non-successful MDAPI result.
        """
        # Import lazily to avoid cycles at module import time
        from .mdapi import mdapi_retrieve as _mdapi_retrieve

        # Ensure we have a valid token before starting the MDAPI flow
        self._refresh_token_if_needed()

        if mdapi_version is None:
            mdapi_version = str(self.api_version).lower().removeprefix('v')

        return _mdapi_retrieve(
            sf=self,
            package=package,
            mdapi_version=mdapi_version,
            poll_interval_seconds=poll_interval_seconds,
            max_poll_seconds=max_poll_seconds,
            raw_response=raw_response,
            raw_bytes=raw_bytes,
        )
