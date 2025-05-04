import base64
import http.client
import json
import logging
import os
import time
from typing import Any, Dict, Optional
from urllib.parse import quote, urlparse

TRACE = 5
logging.addLevelName(TRACE, "TRACE")


def trace(self: logging.Logger, message: str, *args: Any, **kwargs: Any) -> None:
    """Custom TRACE level logging function with redaction."""

    def _redact_sensitive(data: Any) -> Any:
        """Redacts sensitive keys from a dictionary or query string."""
        REDACT_VALUE = "*" * 8
        if isinstance(data, dict):
            return {
                k: (
                    REDACT_VALUE
                    if k.lower() in ["access_token", "authorization", "refresh_token"]
                    else v
                )
                for k, v in data.items()
            }
        elif isinstance(data, str):
            parts = data.split("&")
            for i, part in enumerate(parts):
                if "=" in part:
                    key, value = part.split("=", 1)
                    if key.lower() in [
                        "access_token",
                        "authorization",
                        "refresh_token",
                    ]:
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
        user_agent: str = "sfq/0.0.10",
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
        :param user_agent: Custom User-Agent string (default is "sfq/0.0.10").
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
            conn.close()

        return None

    def tooling_query(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Execute a SOQL query using the Tooling API.

        :param query: The SOQL query string.
        :return: Parsed JSON response or None on failure.
        """
        return self.query(query, tooling=True)
