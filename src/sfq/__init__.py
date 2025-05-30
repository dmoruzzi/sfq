import base64
import http.client
import json
import logging
import os
import time
import warnings
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, Literal, Optional, List, Tuple
from urllib.parse import quote, urlparse

TRACE = 5
logging.addLevelName(TRACE, "TRACE")


class ExperimentalWarning(Warning):
    pass


def trace(self: logging.Logger, message: str, *args: Any, **kwargs: Any) -> None:
    """Custom TRACE level logging function with redaction."""

    def _redact_sensitive(data: Any) -> Any:
        """Redacts sensitive keys from a dictionary or query string."""
        REDACT_VALUE = "*" * 8
        REDACT_KEYS = [
            "access_token",
            "authorization",
            "set-cookie",
            "cookie",
            "refresh_token",
            "client_secret",
        ]
        if isinstance(data, dict):
            return {
                k: (REDACT_VALUE if k.lower() in REDACT_KEYS else v)
                for k, v in data.items()
            }
        elif isinstance(data, (list, tuple)):
            return type(data)(
                (
                    (item[0], REDACT_VALUE)
                    if isinstance(item, tuple) and item[0].lower() in REDACT_KEYS
                    else item
                    for item in data
                )
            )
        elif isinstance(data, str):
            parts = data.split("&")
            for i, part in enumerate(parts):
                if "=" in part:
                    key, value = part.split("=", 1)
                    if key.lower() in REDACT_KEYS:
                        parts[i] = f"{key}={REDACT_VALUE}"
            return "&".join(parts)
        return data

    redacted_args = args
    if args:
        first = args[0]
        if isinstance(first, str):
            try:
                loaded = json.loads(first)
                first = loaded
            except (json.JSONDecodeError, TypeError):
                pass
        redacted_first = _redact_sensitive(first)
        redacted_args = (redacted_first,) + args[1:]

    if self.isEnabledFor(TRACE):
        self._log(TRACE, message, redacted_args, **kwargs)


logging.Logger.trace = trace
logger = logging.getLogger("sfq")


class SFAuth:
    def __init__(
        self,
        instance_url: str,
        client_id: str,
        refresh_token: str,  # client_secret & refresh_token will swap positions 2025-AUG-1
        client_secret: str = "_deprecation_warning",  # mandatory after 2025-AUG-1
        api_version: str = "v63.0",
        token_endpoint: str = "/services/oauth2/token",
        access_token: Optional[str] = None,
        token_expiration_time: Optional[float] = None,
        token_lifetime: int = 15 * 60,
        user_agent: str = "sfq/0.0.15",
        sforce_client: str = "_auto",
        proxy: str = "auto",
    ) -> None:
        """
        Initializes the SFAuth with necessary parameters.

        :param instance_url: The Salesforce instance URL.
        :param client_id: The client ID for OAuth.
        :param refresh_token: The refresh token for OAuth.
        :param client_secret: The client secret for OAuth (default is "_deprecation_warning").
        :param api_version: The Salesforce API version (default is "v63.0").
        :param token_endpoint: The token endpoint (default is "/services/oauth2/token").
        :param access_token: The access token for the current session (default is None).
        :param token_expiration_time: The expiration time of the access token (default is None).
        :param token_lifetime: The lifetime of the access token in seconds (default is 15 minutes).
        :param user_agent: Custom User-Agent string (default is "sfq/0.0.15").
        :param sforce_client: Custom Application Identifier (default is user_agent).
        :param proxy: The proxy configuration, "auto" to use environment (default is "auto").
        """
        self.instance_url = self._format_instance_url(instance_url)
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.api_version = api_version
        self.token_endpoint = token_endpoint
        self.access_token = access_token
        self.token_expiration_time = token_expiration_time
        self.token_lifetime = token_lifetime
        self.user_agent = user_agent
        self.sforce_client = sforce_client
        self._auto_configure_proxy(proxy)
        self._high_api_usage_threshold = 80

        if sforce_client == "_auto":
            self.sforce_client = user_agent

        if self.client_secret == "_deprecation_warning":
            warnings.warn(
                "The 'client_secret' parameter will be mandatory and positional arguments will change after 1 August 2025. "
                "Please ensure explicit argument assignment and 'client_secret' inclusion when initializing the SFAuth object.",
                DeprecationWarning,
                stacklevel=2,
            )

            logger.debug(
                "Will be SFAuth(instance_url, client_id, client_secret, refresh_token) starting 1 August 2025... but please just use named arguments.."
            )

    def _format_instance_url(self, instance_url) -> str:
        if instance_url.startswith("https://"):
            return instance_url
        if instance_url.startswith("http://"):
            return instance_url.replace("http://", "https://")
        return f"https://{instance_url}"

    def _auto_configure_proxy(self, proxy: str) -> None:
        """
        Automatically configure the proxy based on the environment or provided value.
        """
        if proxy == "auto":
            self.proxy = os.environ.get("https_proxy")
            if self.proxy:
                logger.debug("Auto-configured proxy: %s", self.proxy)
        else:
            self.proxy = proxy
            logger.debug("Using configured proxy: %s", self.proxy)

    def _prepare_payload(self) -> Dict[str, Optional[str]]:
        """
        Prepare the payload for the token request.

        This method constructs a dictionary containing the necessary parameters
        for a token request using the refresh token grant type. It includes
        the client ID, client secret, and refresh token if they are available.

        Returns:
            Dict[str, Optional[str]]: A dictionary containing the payload for the token request.
        """
        payload = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
        }

        if self.client_secret == "_deprecation_warning":
            logger.warning(
                "The SFQ library is making a breaking change (2025-AUG-1) to require the 'client_secret' parameter to be assigned when initializing the SFAuth object. "
                "In addition, positional arguments will change. Please ensure explicit argument assignment and 'client_secret' inclusion when initializing the SFAuth object to avoid impact."
            )
            payload.pop("client_secret")

        if not self.client_secret:
            payload.pop("client_secret")

        return payload

    def _create_connection(self, netloc: str) -> http.client.HTTPConnection:
        """
        Create a connection using HTTP or HTTPS, with optional proxy support.

        :param netloc: The target host and port from the parsed instance URL.
        :return: An HTTP(S)Connection object.
        """
        if self.proxy:
            proxy_url = urlparse(self.proxy)
            logger.trace("Using proxy: %s", self.proxy)
            conn = http.client.HTTPSConnection(proxy_url.hostname, proxy_url.port)
            conn.set_tunnel(netloc)
            logger.trace("Using proxy tunnel to %s", netloc)
        else:
            conn = http.client.HTTPSConnection(netloc)
            logger.trace("Direct connection to %s", netloc)
        return conn

    def _send_request(
        self,
        method: str,
        endpoint: str,
        headers: Dict[str, str],
        body: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> Tuple[Optional[int], Optional[str]]:
        """
        Unified request method with built-in logging and error handling.

        :param method: HTTP method to use.
        :param endpoint: Target API endpoint.
        :param headers: HTTP headers.
        :param body: Optional request body.
        :param timeout: Optional timeout in seconds.
        :return: Tuple of HTTP status code and response body as a string.
        """
        parsed_url = urlparse(self.instance_url)
        conn = self._create_connection(parsed_url.netloc)

        try:
            logger.trace("Request method: %s", method)
            logger.trace("Request endpoint: %s", endpoint)
            logger.trace("Request headers: %s", headers)
            if body:
                logger.trace("Request body: %s", body)

            conn.request(method, endpoint, body=body, headers=headers)
            response = conn.getresponse()
            self._http_resp_header_logic(response)

            data = response.read().decode("utf-8")
            logger.trace("Response status: %s", response.status)
            logger.trace("Response body: %s", data)
            return response.status, data

        except Exception as err:
            logger.exception("HTTP request failed: %s", err)
            return None, None

        finally:
            logger.trace("Closing connection...")
            conn.close()

    def _new_token_request(self, payload: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """
        Perform a new token request using the provided payload.

        :param payload: Payload for the token request.
        :return: Parsed JSON response or None on failure.
        """
        headers = self._get_common_headers()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        del headers["Authorization"]

        body = "&".join(f"{key}={quote(str(value))}" for key, value in payload.items())
        status, data = self._send_request("POST", self.token_endpoint, headers, body)

        if status == 200:
            logger.trace("Token refresh successful.")
            return json.loads(data)

        if status:
            logger.error("Token refresh failed: %s", status)
            logger.debug("Response body: %s", data)

        return None

    def _http_resp_header_logic(self, response: http.client.HTTPResponse) -> None:
        """
        Perform additional logic based on the HTTP response headers.

        :param response: The HTTP response object.
        :return: None
        """
        logger.trace(
            "Response status: %s, reason: %s", response.status, response.reason
        )
        headers = response.getheaders()
        headers_list = [(k, v) for k, v in headers if not v.startswith("BrowserId=")]
        logger.trace("Response headers: %s", headers_list)
        for key, value in headers_list:
            if key == "Sforce-Limit-Info":
                current_api_calls = int(value.split("=")[1].split("/")[0])
                maximum_api_calls = int(value.split("=")[1].split("/")[1])
                usage_percentage = round(current_api_calls / maximum_api_calls * 100, 2)
                if usage_percentage > self._high_api_usage_threshold:
                    logger.warning(
                        "High API usage: %s/%s (%s%%)",
                        current_api_calls,
                        maximum_api_calls,
                        usage_percentage,
                    )
                else:
                    logger.debug(
                        "API usage: %s/%s (%s%%)",
                        current_api_calls,
                        maximum_api_calls,
                        usage_percentage,
                    )

    def _refresh_token_if_needed(self) -> Optional[str]:
        """
        Automatically refresh the access token if it has expired or is missing.

        :return: A valid access token or None if refresh failed.
        """
        if self.access_token and not self._is_token_expired():
            return self.access_token

        logger.trace("Access token expired or missing, refreshing...")
        payload = self._prepare_payload()
        token_data = self._new_token_request(payload)

        if token_data:
            self.access_token = token_data.get("access_token")
            issued_at = token_data.get("issued_at")

            try:
                self.org_id = token_data.get("id").split("/")[4]
                self.user_id = token_data.get("id").split("/")[5]
                logger.trace(
                    "Authenticated as user %s for org %s (%s)",
                    self.user_id,
                    self.org_id,
                    token_data.get("instance_url"),
                )
            except (IndexError, KeyError):
                logger.error("Failed to extract org/user IDs from token response.")

            if self.access_token and issued_at:
                self.token_expiration_time = int(issued_at) + self.token_lifetime
                logger.trace("New token expires at %s", self.token_expiration_time)
                return self.access_token

        logger.error("Failed to obtain access token.")
        return None

    def _get_common_headers(self) -> Dict[str, str]:
        """
        Generate common headers for API requests.

        :return: A dictionary of common headers.
        """
        if not self.access_token and self.token_expiration_time is None:
            self.token_expiration_time = int(time.time())
            self._refresh_token_if_needed()
        
        return {
            "Authorization": f"Bearer {self.access_token}",
            "User-Agent": self.user_agent,
            "Sforce-Call-Options": f"client={self.sforce_client}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    

    def _is_token_expired(self) -> bool:
        """
        Check if the access token has expired.

        :return: True if token is expired or missing, False otherwise.
        """
        try:
            return time.time() >= float(self.token_expiration_time)
        except (TypeError, ValueError):
            logger.warning("Token expiration check failed. Treating token as expired.")
            return True

    def read_static_resource_name(
        self, resource_name: str, namespace: Optional[str] = None
    ) -> Optional[str]:
        """
        Read a static resource for a given name from the Salesforce instance.

        :param resource_name: Name of the static resource to read.
        :param namespace: Namespace of the static resource to read (default is None).
        :return: Static resource content or None on failure.
        """
        _safe_resource_name = quote(resource_name, safe="")
        query = f"SELECT Id FROM StaticResource WHERE Name = '{_safe_resource_name}'"
        if namespace:
            namespace = quote(namespace, safe="")
            query += f" AND NamespacePrefix = '{namespace}'"
        query += " LIMIT 1"
        _static_resource_id_response = self.query(query)

        if (
            _static_resource_id_response
            and _static_resource_id_response.get("records")
            and len(_static_resource_id_response["records"]) > 0
        ):
            return self.read_static_resource_id(
                _static_resource_id_response["records"][0].get("Id")
            )

        logger.error(f"Failed to read static resource with name {_safe_resource_name}.")
        return None

    def read_static_resource_id(self, resource_id: str) -> Optional[str]:
        """
        Read a static resource for a given ID from the Salesforce instance.

        :param resource_id: ID of the static resource to read.
        :return: Static resource content or None on failure.
        """
        endpoint = f"/services/data/{self.api_version}/sobjects/StaticResource/{resource_id}/Body"
        headers = self._get_common_headers()
        status, data = self._send_request("GET", endpoint, headers)

        if status == 200:
            logger.debug("Static resource fetched successfully.")
            return data

        logger.error("Failed to fetch static resource: %s", status)
        return None

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
        safe_resource_name = quote(resource_name, safe="")
        query = f"SELECT Id FROM StaticResource WHERE Name = '{safe_resource_name}'"
        if namespace:
            namespace = quote(namespace, safe="")
            query += f" AND NamespacePrefix = '{namespace}'"
        query += " LIMIT 1"

        static_resource_id_response = self.query(query)

        if (
            static_resource_id_response
            and static_resource_id_response.get("records")
            and len(static_resource_id_response["records"]) > 0
        ):
            return self.update_static_resource_id(
                static_resource_id_response["records"][0].get("Id"), data
            )

        logger.error(
            f"Failed to update static resource with name {safe_resource_name}."
        )
        return None

    def update_static_resource_id(
        self, resource_id: str, data: str
    ) -> Optional[Dict[str, Any]]:
        """
        Replace the content of a static resource in the Salesforce instance by ID.

        :param resource_id: ID of the static resource to update.
        :param data: Content to update the static resource with.
        :return: Parsed JSON response or None on failure.
        """
        payload = {"Body": base64.b64encode(data.encode("utf-8")).decode("utf-8")}

        endpoint = (
            f"/services/data/{self.api_version}/sobjects/StaticResource/{resource_id}"
        )
        headers = self._get_common_headers()

        status_code, response_data = self._send_request(
            method="PATCH",
            endpoint=endpoint,
            headers=headers,
            body=json.dumps(payload),
        )

        if status_code == 200:
            logger.debug("Patch Static Resource request successful.")
            return json.loads(response_data)

        logger.error(
            "Patch Static Resource API request failed: %s",
            status_code,
        )
        logger.debug("Response body: %s", response_data)

        return None

    def limits(self) -> Optional[Dict[str, Any]]:
        """
        Fetch the current limits for the Salesforce instance.

        :return: Parsed JSON response or None on failure.
        """
        endpoint = f"/services/data/{self.api_version}/limits"
        headers = self._get_common_headers()

        status, data = self._send_request("GET", endpoint, headers)

        if status == 200:
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
        endpoint = f"/services/data/{self.api_version}/"
        endpoint += "tooling/query" if tooling else "query"
        query_string = f"?q={quote(query)}"
        endpoint += query_string
        headers = self._get_common_headers()

        paginated_results = {"totalSize": 0, "done": False, "records": []}

        try:
            while True:
                logger.trace("Request endpoint: %s", endpoint)
                logger.trace("Request headers: %s", headers)
                headers = self._get_common_headers()  # handle refresh token

                status_code, data = self._send_request(
                    method="GET",
                    endpoint=endpoint,
                    headers=headers,
                )

                if status_code == 200:
                    current_results = json.loads(data)
                    paginated_results["records"].extend(current_results["records"])
                    query_done = current_results.get("done")
                    if query_done:
                        total_size = current_results.get("totalSize")
                        paginated_results = {
                            "totalSize": total_size,
                            "done": query_done,
                            "records": paginated_results["records"],
                        }
                        logger.debug(
                            "Query successful, returned %s records: %r",
                            total_size,
                            query,
                        )
                        logger.trace("Query full response: %s", data)
                        break
                    endpoint = current_results.get("nextRecordsUrl")
                    logger.debug(
                        "Query batch successful, getting next batch: %s", endpoint
                    )
                else:
                    logger.debug("Query failed: %r", query)
                    logger.error(
                        "Query failed with HTTP status %s",
                        status_code,
                    )
                    logger.debug("Query response: %s", data)
                    break

            return paginated_results

        except Exception as err:
            logger.exception("Exception during query: %s", err)

        return None

    def tooling_query(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Execute a SOQL query using the Tooling API.

        :param query: The SOQL query string.
        :return: Parsed JSON response or None on failure.
        """
        return self.query(query, tooling=True)

    def get_sobject_prefixes(
        self, key_type: Literal["id", "name"] = "id"
    ) -> Optional[Dict[str, str]]:
        """
        Fetch all key prefixes from the Salesforce instance and map them to sObject names or vice versa.

        :param key_type: The type of key to return. Either 'id' (prefix) or 'name' (sObject).
        :return: A dictionary mapping key prefixes to sObject names or None on failure.
        """
        valid_key_types = {"id", "name"}
        if key_type not in valid_key_types:
            logger.error(
                "Invalid key type: %s, must be one of: %s",
                key_type,
                ", ".join(valid_key_types),
            )
            return None

        endpoint = f"/services/data/{self.api_version}/sobjects/"
        headers = self._get_common_headers()

        prefixes = {}

        try:
            logger.trace("Request endpoint: %s", endpoint)
            logger.trace("Request headers: %s", headers)

            status_code, data = self._send_request(
                method="GET",
                endpoint=endpoint,
                headers=headers,
            )

            if status_code == 200:
                logger.debug("Key prefixes API request successful.")
                logger.trace("Response body: %s", data)
                for sobject in json.loads(data)["sobjects"]:
                    key_prefix = sobject.get("keyPrefix")
                    name = sobject.get("name")
                    if not key_prefix or not name:
                        continue

                    if key_type == "id":
                        prefixes[key_prefix] = name
                    elif key_type == "name":
                        prefixes[name] = key_prefix

                logger.debug("Key prefixes: %s", prefixes)
                return prefixes

            logger.error(
                "Key prefixes API request failed: %s",
                status_code,
            )
            logger.debug("Response body: %s", data)

        except Exception as err:
            logger.exception("Exception during key prefixes API request: %s", err)

        return None

    def cquery(
        self, query_dict: dict[str, str], max_workers: int = 10
    ) -> Optional[Dict[str, Any]]:
        """
        Execute multiple SOQL queries using the Composite Batch API with threading to reduce network overhead.
        The function returns a dictionary mapping the original keys to their corresponding batch response.
        The function requires a dictionary of SOQL queries with keys as logical names (referenceId) and values as SOQL queries.
        Each query (subrequest) is counted as a unique API request against Salesforce governance limits.

        :param query_dict: A dictionary of SOQL queries with keys as logical names and values as SOQL queries.
        :param max_workers: The maximum number of threads to spawn for concurrent execution (default is 10).
        :return: Dict mapping the original keys to their corresponding batch response or None on failure.
        """
        if not query_dict:
            logger.warning("No queries to execute.")
            return None

        def _execute_batch(queries_batch):
            endpoint = f"/services/data/{self.api_version}/composite/batch"
            headers = self._get_common_headers()

            payload = {
                "haltOnError": False,
                "batchRequests": [
                    {
                        "method": "GET",
                        "url": f"/services/data/{self.api_version}/query?q={quote(query)}",
                    }
                    for query in queries_batch
                ],
            }

            status_code, data = self._send_request(
                method="POST",
                endpoint=endpoint,
                headers=headers,
                body=json.dumps(payload),
            )

            batch_results = {}
            if status_code == 200:
                logger.debug("Composite query successful.")
                logger.trace("Composite query full response: %s", data)
                results = json.loads(data).get("results", [])
                for i, result in enumerate(results):
                    records = []
                    if "result" in result and "records" in result["result"]:
                        records.extend(result["result"]["records"])
                    # Handle pagination
                    while not result["result"].get("done", True):
                        headers = self._get_common_headers()  # handles token refresh
                        next_url = result["result"].get("nextRecordsUrl")
                        if next_url:
                            status_code, next_data = self._send_request(
                                method="GET",
                                endpoint=next_url,
                                headers=headers,
                            )
                            if status_code == 200:
                                next_results = json.loads(next_data)
                                records.extend(next_results.get("records", []))
                                result["result"]["done"] = next_results.get("done")
                            else:
                                logger.error(
                                    "Failed to fetch next records: %s",
                                    next_data,
                                )
                                break
                        else:
                            result["result"]["done"] = True
                    paginated_results = result["result"]
                    paginated_results["records"] = records
                    if "nextRecordsUrl" in paginated_results:
                        del paginated_results["nextRecordsUrl"]
                    batch_results[keys[i]] = paginated_results
                    if result.get("statusCode") != 200:
                        logger.error("Query failed for key %s: %s", keys[i], result)
                        logger.error(
                            "Query failed with HTTP status %s (%s)",
                            result.get("statusCode"),
                            result.get("statusMessage"),
                        )
                        logger.trace("Query response: %s", result)
            else:
                logger.error(
                    "Composite query failed with HTTP status %s (%s)",
                    status_code,
                    data,
                )
                batch_results[keys[i]] = data
                logger.trace("Composite query response: %s", data)

            return batch_results

        keys = list(query_dict.keys())
        results_dict = OrderedDict()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            BATCH_SIZE = 25
            for i in range(0, len(keys), BATCH_SIZE):
                batch_keys = keys[i : i + BATCH_SIZE]
                batch_queries = [query_dict[key] for key in batch_keys]
                futures.append(executor.submit(_execute_batch, batch_queries))

            for future in as_completed(futures):
                results_dict.update(future.result())

        logger.trace("Composite query results: %s", results_dict)
        return results_dict
