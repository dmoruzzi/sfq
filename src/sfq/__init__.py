import base64
import http.client
import json
import logging
import os
import time
import warnings
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Empty, Queue
from typing import Any, Dict, Literal, Optional
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
        refresh_token: str,
        api_version: str = "v63.0",
        token_endpoint: str = "/services/oauth2/token",
        access_token: Optional[str] = None,
        token_expiration_time: Optional[float] = None,
        token_lifetime: int = 15 * 60,
        user_agent: str = "sfq/0.0.12",
        proxy: str = "auto",
    ) -> None:
        """
        Initializes the SFAuth with necessary parameters.

        :param instance_url: The Salesforce instance URL.
        :param client_id: The client ID for OAuth.
        :param refresh_token: The refresh token for OAuth.
        :param api_version: The Salesforce API version (default is "v63.0").
        :param token_endpoint: The token endpoint (default is "/services/oauth2/token").
        :param access_token: The access token for the current session (default is None).
        :param token_expiration_time: The expiration time of the access token (default is None).
        :param token_lifetime: The lifetime of the access token in seconds (default is 15 minutes).
        :param user_agent: Custom User-Agent string (default is "sfq/0.0.12").
        :param proxy: The proxy configuration, "auto" to use environment (default is "auto").
        """
        self.instance_url = instance_url
        self.client_id = client_id
        self.refresh_token = refresh_token
        self.api_version = api_version
        self.token_endpoint = token_endpoint
        self.access_token = access_token
        self.token_expiration_time = token_expiration_time
        self.token_lifetime = token_lifetime
        self.user_agent = user_agent
        self._auto_configure_proxy(proxy)
        self._high_api_usage_threshold = 80

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

    def _prepare_payload(self) -> Dict[str, str]:
        """
        Prepare the payload for the token request.
        """
        return {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "refresh_token": self.refresh_token,
        }

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

    def _new_token_request(self, payload: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """
        Send a POST request to the Salesforce token endpoint using http.client.

        :param payload: Dictionary of form-encoded OAuth parameters.
        :return: Parsed JSON response if successful, otherwise None.
        """
        parsed_url = urlparse(self.instance_url)
        conn = self._create_connection(parsed_url.netloc)
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": self.user_agent,
        }
        body = "&".join(f"{key}={quote(str(value))}" for key, value in payload.items())

        try:
            logger.trace("Request endpoint: %s", self.token_endpoint)
            logger.trace("Request body: %s", body)
            logger.trace("Request headers: %s", headers)
            conn.request("POST", self.token_endpoint, body, headers)
            response = conn.getresponse()
            data = response.read().decode("utf-8")
            self._http_resp_header_logic(response)

            if response.status == 200:
                logger.trace("Token refresh successful.")
                logger.trace("Response body: %s", data)
                return json.loads(data)

            logger.error(
                "Token refresh failed: %s %s", response.status, response.reason
            )
            logger.debug("Response body: %s", data)

        except Exception as err:
            logger.exception("Error during token request: %s", err)

        finally:
            logger.trace("Closing connection.")
            conn.close()

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
            if key.startswith("Sforce-"):
                if key == "Sforce-Limit-Info":
                    current_api_calls = int(value.split("=")[1].split("/")[0])
                    maximum_api_calls = int(value.split("=")[1].split("/")[1])
                    usage_percentage = round(
                        current_api_calls / maximum_api_calls * 100, 2
                    )
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
        namespace = quote(namespace, safe="")
        query = f"SELECT Id FROM StaticResource WHERE Name = '{_safe_resource_name}'"
        if namespace:
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
        self._refresh_token_if_needed()

        if not self.access_token:
            logger.error("No access token available for limits.")
            return None

        endpoint = f"/services/data/{self.api_version}/sobjects/StaticResource/{resource_id}/Body"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }

        parsed_url = urlparse(self.instance_url)
        conn = self._create_connection(parsed_url.netloc)

        try:
            logger.trace("Request endpoint: %s", endpoint)
            logger.trace("Request headers: %s", headers)
            conn.request("GET", endpoint, headers=headers)
            response = conn.getresponse()
            data = response.read().decode("utf-8")
            self._http_resp_header_logic(response)

            if response.status == 200:
                logger.debug("Get Static Resource Body API request successful.")
                logger.trace("Response body: %s", data)
                return data

            logger.error(
                "Get Static Resource Body API request failed: %s %s",
                response.status,
                response.reason,
            )
            logger.debug("Response body: %s", data)

        except Exception as err:
            logger.exception(
                "Error during Get Static Resource Body API request: %s", err
            )

        finally:
            logger.trace("Closing connection...")
            conn.close()

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
        namespace = quote(namespace, safe="")
        query = f"SELECT Id FROM StaticResource WHERE Name = '{safe_resource_name}'"
        if namespace:
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
        self._refresh_token_if_needed()

        if not self.access_token:
            logger.error("No access token available for limits.")
            return None

        payload = {"Body": base64.b64encode(data.encode("utf-8"))}

        endpoint = (
            f"/services/data/{self.api_version}/sobjects/StaticResource/{resource_id}"
        )
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "User-Agent": self.user_agent,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        parsed_url = urlparse(self.instance_url)
        conn = self._create_connection(parsed_url.netloc)

        try:
            logger.trace("Request endpoint: %s", endpoint)
            logger.trace("Request headers: %s", headers)
            logger.trace("Request payload: %s", payload)
            conn.request(
                "PATCH",
                endpoint,
                headers=headers,
                body=json.dumps(payload, default=lambda x: x.decode("utf-8")),
            )
            response = conn.getresponse()
            data = response.read().decode("utf-8")
            self._http_resp_header_logic(response)

            if response.status == 200:
                logger.debug("Patch Static Resource request successful.")
                logger.trace("Response body: %s", data)
                return json.loads(data)

            logger.error(
                "Patch Static Resource API request failed: %s %s",
                response.status,
                response.reason,
            )
            logger.debug("Response body: %s", data)

        except Exception as err:
            logger.exception("Error during patch request: %s", err)

        finally:
            logger.trace("Closing connection.")
            conn.close()

        return None

    def limits(self) -> Optional[Dict[str, Any]]:
        """
        Execute a GET request to the Salesforce Limits API.

        :return: Parsed JSON response or None on failure.
        """
        self._refresh_token_if_needed()

        if not self.access_token:
            logger.error("No access token available for limits.")
            return None

        endpoint = f"/services/data/{self.api_version}/limits"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }

        parsed_url = urlparse(self.instance_url)
        conn = self._create_connection(parsed_url.netloc)

        try:
            logger.trace("Request endpoint: %s", endpoint)
            logger.trace("Request headers: %s", headers)
            conn.request("GET", endpoint, headers=headers)
            response = conn.getresponse()
            data = response.read().decode("utf-8")
            self._http_resp_header_logic(response)

            if response.status == 200:
                logger.debug("Limits API request successful.")
                logger.trace("Response body: %s", data)
                return json.loads(data)

            logger.error(
                "Limits API request failed: %s %s", response.status, response.reason
            )
            logger.debug("Response body: %s", data)

        except Exception as err:
            logger.exception("Error during limits request: %s", err)

        finally:
            logger.debug("Closing connection...")
            conn.close()

        return None

    def query(self, query: str, tooling: bool = False) -> Optional[Dict[str, Any]]:
        """
        Execute a SOQL query using the REST or Tooling API.

        :param query: The SOQL query string.
        :param tooling: If True, use the Tooling API endpoint.
        :return: Parsed JSON response or None on failure.
        """
        self._refresh_token_if_needed()

        if not self.access_token:
            logger.error("No access token available for query.")
            return None

        endpoint = f"/services/data/{self.api_version}/"
        endpoint += "tooling/query" if tooling else "query"
        query_string = f"?q={quote(query)}"

        endpoint += query_string

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }

        parsed_url = urlparse(self.instance_url)
        conn = self._create_connection(parsed_url.netloc)

        try:
            paginated_results = {"totalSize": 0, "done": False, "records": []}
            while True:
                logger.trace("Request endpoint: %s", endpoint)
                logger.trace("Request headers: %s", headers)
                conn.request("GET", endpoint, headers=headers)
                response = conn.getresponse()
                data = response.read().decode("utf-8")
                self._http_resp_header_logic(response)

                if response.status == 200:
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
                        "Query failed with HTTP status %s (%s)",
                        response.status,
                        response.reason,
                    )
                    logger.debug("Query response: %s", data)
                    break

            return paginated_results

        except Exception as err:
            logger.exception("Exception during query: %s", err)

        finally:
            logger.trace("Closing connection...")
            conn.close()

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

        self._refresh_token_if_needed()

        if not self.access_token:
            logger.error("No access token available for key prefixes.")
            return None

        endpoint = f"/services/data/{self.api_version}/sobjects/"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }

        parsed_url = urlparse(self.instance_url)
        conn = self._create_connection(parsed_url.netloc)
        prefixes = {}

        try:
            logger.trace("Request endpoint: %s", endpoint)
            logger.trace("Request headers: %s", headers)
            conn.request("GET", endpoint, headers=headers)
            response = conn.getresponse()
            data = response.read().decode("utf-8")
            self._http_resp_header_logic(response)

            if response.status == 200:
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
                "Key prefixes API request failed: %s %s",
                response.status,
                response.reason,
            )
            logger.debug("Response body: %s", data)

        except Exception as err:
            logger.exception("Exception during key prefixes API request: %s", err)

        finally:
            logger.trace("Closing connection...")
            conn.close()

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

        self._refresh_token_if_needed()

        if not self.access_token:
            logger.error("No access token available for query.")
            return None

        def _execute_batch(queries_batch):
            endpoint = f"/services/data/{self.api_version}/composite/batch"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "User-Agent": self.user_agent,
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

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

            parsed_url = urlparse(self.instance_url)
            conn = self._create_connection(parsed_url.netloc)
            batch_results = {}

            try:
                logger.trace("Request endpoint: %s", endpoint)
                logger.trace("Request headers: %s", headers)
                logger.trace("Request payload: %s", json.dumps(payload, indent=2))

                conn.request("POST", endpoint, json.dumps(payload), headers=headers)
                conn.sock.settimeout(60 * 10)
                response = conn.getresponse()
                data = response.read().decode("utf-8")
                self._http_resp_header_logic(response)

                if response.status == 200:
                    logger.debug("Composite query successful.")
                    logger.trace("Composite query full response: %s", data)
                    results = json.loads(data).get("results", [])
                    for i, result in enumerate(results):
                        records = []
                        if "result" in result and "records" in result["result"]:
                            records.extend(result["result"]["records"])
                        # Handle pagination
                        while not result["result"].get("done", True):
                            next_url = result["result"].get("nextRecordsUrl")
                            if next_url:
                                conn.request("GET", next_url, headers=headers)
                                response = conn.getresponse()
                                data = response.read().decode("utf-8")
                                self._http_resp_header_logic(response)
                                if response.status == 200:
                                    next_results = json.loads(data)
                                    records.extend(next_results.get("records", []))
                                    result["result"]["done"] = next_results.get("done")
                                else:
                                    logger.error(
                                        "Failed to fetch next records: %s",
                                        response.reason,
                                    )
                                    break
                            else:
                                result["result"]["done"] = True
                        batch_results[keys[i]] = {"records": records}
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
                        response.status,
                        response.reason,
                    )
                    batch_results[keys[i]] = data
                    logger.trace("Composite query response: %s", data)
            except Exception as err:
                logger.exception("Exception during composite query: %s", err)
            finally:
                logger.trace("Closing connection...")
                conn.close()

            return batch_results

        keys = list(query_dict.keys())
        results_dict = OrderedDict()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for i in range(0, len(keys), 25):
                batch_keys = keys[i : i + 25]
                batch_queries = [query_dict[key] for key in batch_keys]
                futures.append(executor.submit(_execute_batch, batch_queries))

            for future in as_completed(futures):
                results_dict.update(future.result())

        logger.trace("Composite query results: %s", results_dict)
        return results_dict

    def _reconnect_with_backoff(self, attempt: int) -> None:
        wait_time = min(2**attempt, 60)
        logger.warning(
            f"Reconnecting after failure, backoff {wait_time}s (attempt {attempt})"
        )
        time.sleep(wait_time)

    def _subscribe_topic(
        self,
        topic: str,
        queue_timeout: int = 90,
        max_runtime: Optional[int] = None,
    ):
        """
        Yields events from a subscribed Salesforce CometD topic.

        :param topic: Topic to subscribe to, e.g. '/event/MyEvent__e'
        :param queue_timeout: Seconds to wait for a message before logging heartbeat
        :param max_runtime: Max total time to listen in seconds (None = unlimited)
        """
        warnings.warn(
            "The _subscribe_topic method is experimental and subject to change in future versions.",
            ExperimentalWarning,
            stacklevel=2,
        )

        self._refresh_token_if_needed()
        self._msg_count: int = 0

        if not self.access_token:
            logger.error("No access token available for event stream.")
            return

        start_time = time.time()
        message_queue = Queue()
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": self.user_agent,
        }

        parsed_url = urlparse(self.instance_url)
        conn = self._create_connection(parsed_url.netloc)
        _API_VERSION = str(self.api_version).removeprefix("v")
        client_id = str()

        try:
            logger.trace("Starting handshake with Salesforce CometD server.")
            handshake_payload = json.dumps(
                {
                    "id": str(self._msg_count + 1),
                    "version": "1.0",
                    "minimumVersion": "1.0",
                    "channel": "/meta/handshake",
                    "supportedConnectionTypes": ["long-polling"],
                    "advice": {"timeout": 60000, "interval": 0},
                }
            )
            conn.request(
                "POST",
                f"/cometd/{_API_VERSION}/meta/handshake",
                headers=headers,
                body=handshake_payload,
            )
            response = conn.getresponse()
            self._http_resp_header_logic(response)

            logger.trace("Received handshake response.")
            for name, value in response.getheaders():
                if name.lower() == "set-cookie" and "BAYEUX_BROWSER=" in value:
                    _bayeux_browser_cookie = value.split("BAYEUX_BROWSER=")[1].split(
                        ";"
                    )[0]
                    headers["Cookie"] = f"BAYEUX_BROWSER={_bayeux_browser_cookie}"
                    break

            data = json.loads(response.read().decode("utf-8"))
            if not data or not data[0].get("successful"):
                logger.error("Handshake failed: %s", data)
                return

            client_id = data[0]["clientId"]
            logger.trace(f"Handshake successful, client ID: {client_id}")

            logger.trace(f"Subscribing to topic: {topic}")
            subscribe_message = {
                "channel": "/meta/subscribe",
                "clientId": client_id,
                "subscription": topic,
                "id": str(self._msg_count + 1),
            }
            conn.request(
                "POST",
                f"/cometd/{_API_VERSION}/meta/subscribe",
                headers=headers,
                body=json.dumps(subscribe_message),
            )
            response = conn.getresponse()
            self._http_resp_header_logic(response)

            sub_response = json.loads(response.read().decode("utf-8"))
            if not sub_response or not sub_response[0].get("successful"):
                logger.error("Subscription failed: %s", sub_response)
                return

            logger.info(f"Successfully subscribed to topic: {topic}")
            logger.trace("Entering event polling loop.")

            try:
                while True:
                    if max_runtime and (time.time() - start_time > max_runtime):
                        logger.info(
                            f"Disconnecting after max_runtime={max_runtime} seconds"
                        )
                        break

                    logger.trace("Sending connection message.")
                    connect_payload = json.dumps(
                        [
                            {
                                "channel": "/meta/connect",
                                "clientId": client_id,
                                "connectionType": "long-polling",
                                "id": str(self._msg_count + 1),
                            }
                        ]
                    )

                    max_retries = 5
                    attempt = 0

                    while attempt < max_retries:
                        try:
                            conn.request(
                                "POST",
                                f"/cometd/{_API_VERSION}/meta/connect",
                                headers=headers,
                                body=connect_payload,
                            )
                            response = conn.getresponse()
                            self._http_resp_header_logic(response)
                            self._msg_count += 1

                            events = json.loads(response.read().decode("utf-8"))
                            for event in events:
                                if event.get("channel") == topic and "data" in event:
                                    logger.trace(
                                        f"Event received for topic {topic}, data: {event['data']}"
                                    )
                                    message_queue.put(event)
                            break
                        except (
                            http.client.RemoteDisconnected,
                            ConnectionResetError,
                            TimeoutError,
                            http.client.BadStatusLine,
                            http.client.CannotSendRequest,
                            ConnectionAbortedError,
                            ConnectionRefusedError,
                            ConnectionError,
                        ) as e:
                            logger.warning(
                                f"Connection error (attempt {attempt + 1}): {e}"
                            )
                            conn.close()
                            conn = self._create_connection(parsed_url.netloc)
                            self._reconnect_with_backoff(attempt)
                            attempt += 1
                        except Exception as e:
                            logger.exception(
                                f"Connection error (attempt {attempt + 1}): {e}"
                            )
                            break
                    else:
                        logger.error("Max retries reached. Exiting event stream.")
                        break

                    while True:
                        try:
                            msg = message_queue.get(timeout=queue_timeout, block=True)
                            yield msg
                        except Empty:
                            logger.debug(
                                f"Heartbeat: no message in last {queue_timeout} seconds"
                            )
                            break
            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt, disconnecting...")

            except Exception as e:
                logger.exception(f"Polling error: {e}")

        finally:
            if client_id:
                try:
                    logger.trace(
                        f"Disconnecting from server with client ID: {client_id}"
                    )
                    disconnect_payload = json.dumps(
                        [
                            {
                                "channel": "/meta/disconnect",
                                "clientId": client_id,
                                "id": str(self._msg_count + 1),
                            }
                        ]
                    )
                    conn.request(
                        "POST",
                        f"/cometd/{_API_VERSION}/meta/disconnect",
                        headers=headers,
                        body=disconnect_payload,
                    )
                    response = conn.getresponse()
                    self._http_resp_header_logic(response)
                    _ = response.read()
                    logger.trace("Disconnected successfully.")
                except Exception as e:
                    logger.warning(f"Exception during disconnect: {e}")
            if conn:
                logger.trace("Closing connection.")
                conn.close()

            logger.trace("Leaving event polling loop.")
