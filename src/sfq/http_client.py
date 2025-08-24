"""
HTTP client module for the SFQ library.

This module handles HTTP/HTTPS connection management, request/response handling,
proxy support, and unified request processing with logging and error handling.
"""

import http.client
import json
from typing import Dict, Optional, Tuple

from .auth import AuthManager
from .exceptions import ConfigurationError
from .utils import format_headers_for_logging, get_logger, log_api_usage

logger = get_logger(__name__)


class HTTPClient:
    """
    Manages HTTP/HTTPS connections and requests for Salesforce API communication.

    This class encapsulates all HTTP-related functionality including connection
    creation, proxy support, request/response handling, and logging. It works
    in conjunction with AuthManager to provide authenticated API access.
    """

    def __init__(
        self,
        auth_manager: AuthManager,
        user_agent: str = "sfq/0.0.37",
        sforce_client: str = "_auto",
        high_api_usage_threshold: int = 80,
    ) -> None:
        """
        Initialize the HTTPClient with authentication and configuration.

        :param auth_manager: AuthManager instance for authentication
        :param user_agent: Custom User-Agent string for requests
        :param sforce_client: Custom application identifier for Sforce-Call-Options
        :param high_api_usage_threshold: Threshold for high API usage warnings
        """
        self.auth_manager = auth_manager
        self.user_agent = user_agent
        self.sforce_client = str(sforce_client).replace(",", "")  # Remove commas
        self.high_api_usage_threshold = high_api_usage_threshold

        # Auto-configure sforce_client if needed
        if sforce_client == "_auto":
            self.sforce_client = user_agent

    def create_connection(self, netloc: str) -> http.client.HTTPConnection:
        """
        Create an HTTP/HTTPS connection with optional proxy support.

        :param netloc: The target host and port (e.g., "example.com:443")
        :return: An HTTPConnection or HTTPSConnection object
        :raises ConfigurationError: If proxy configuration is invalid
        """
        proxy_config = self.auth_manager.get_proxy_config()

        if proxy_config:
            try:
                proxy_hostname, proxy_port = (
                    self.auth_manager.get_proxy_hostname_and_port()
                )
                logger.trace("Using proxy: %s", proxy_config)

                # Create HTTPS connection through proxy
                conn = http.client.HTTPSConnection(proxy_hostname, proxy_port)
                conn.set_tunnel(netloc)
                logger.trace("Using proxy tunnel to %s", netloc)

                return conn

            except Exception as e:
                raise ConfigurationError(f"Failed to create proxy connection: {e}")
        else:
            # Direct HTTPS connection
            conn = http.client.HTTPSConnection(netloc)
            logger.trace("Direct connection to %s", netloc)
            return conn

    def get_common_headers(
        self, include_auth: bool = True, recursive_call: bool = False
    ) -> Dict[str, str]:
        """
        Generate common headers for API requests.

        :param include_auth: Whether to include Authorization header
        :param recursive_call: Whether this is a recursive call (for token refresh)
        :return: Dictionary of common headers
        """
        logger.trace("Generating common headers...")
        headers = {
            "User-Agent": self.user_agent,
            "Sforce-Call-Options": f"client={self.sforce_client}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        if include_auth and not recursive_call:
            logger.trace("Including auth headers...")
            # Ensure we have a valid token before adding auth headers
            if self.auth_manager.needs_token_refresh():
                # This will be handled by the calling code that has access to token refresh
                logger.trace("Token refresh needed before adding auth headers")
                self.refresh_token_and_update_auth()

            if self.auth_manager.access_token:
                headers.update(self.auth_manager.get_auth_headers())
        return headers

    def send_request(
        self,
        method: str,
        endpoint: str,
        headers: Dict[str, str],
        body: Optional[str] = None,
    ) -> Tuple[Optional[int], Optional[str]]:
        """
        Send an HTTP request with built-in logging and error handling.

        :param method: HTTP method (GET, POST, PATCH, DELETE, etc.)
        :param endpoint: Target API endpoint path
        :param headers: HTTP headers dictionary
        :param body: Optional request body
        :return: Tuple of (status_code, response_body) or (None, None) on failure
        """
        try:
            # Get the instance netloc for connection
            netloc = self.auth_manager.get_instance_netloc()
            conn = self.create_connection(netloc)

            # Log request details
            logger.trace("Request method: %s", method)
            logger.trace("Request endpoint: %s", endpoint)
            logger.trace("Request headers: %s", headers)
            if body:
                logger.trace("Request body: %s", body)

            # Send the request
            conn.request(method, endpoint, body=body, headers=headers)
            response = conn.getresponse()

            # Process response headers and extract data
            self._process_response_headers(response)
            data = response.read().decode("utf-8")

            # Log response details
            logger.trace("Response status: %s", response.status)
            logger.trace("Response body: %s", data)

            return response.status, data

        except Exception as err:
            logger.exception("HTTP request failed: %s", err)
            return None, None

        finally:
            try:
                logger.trace("Closing connection...")
                conn.close()
            except Exception:
                pass  # Ignore connection close errors

    def _process_response_headers(self, response: http.client.HTTPResponse) -> None:
        """
        Process HTTP response headers for logging and API usage tracking.

        :param response: The HTTP response object
        """
        logger.trace(
            "Response status: %s, reason: %s", response.status, response.reason
        )

        # Get and log headers (filtered for sensitive data)
        headers = response.getheaders()
        filtered_headers = format_headers_for_logging(headers)
        logger.trace("Response headers: %s", filtered_headers)

        # Process specific headers
        for key, value in headers:
            if key == "Sforce-Limit-Info":
                log_api_usage(value, self.high_api_usage_threshold)

    def send_authenticated_request(
        self,
        method: str,
        endpoint: str,
        body: Optional[str] = None,
        additional_headers: Optional[Dict[str, str]] = None,
    ) -> Tuple[Optional[int], Optional[str]]:
        """
        Send an authenticated HTTP request with automatic token refresh.

        This is a convenience method that handles common request patterns
        with authentication and standard headers.

        :param method: HTTP method
        :param endpoint: API endpoint path
        :param body: Optional request body
        :param additional_headers: Optional additional headers to include
        :return: Tuple of (status_code, response_body) or (None, None) on failure
        """
        headers = self.get_common_headers(include_auth=True)

        if additional_headers:
            headers.update(additional_headers)

        return self.send_request(method, endpoint, headers, body)

    def send_token_request(
        self,
        payload: Dict[str, str],
        token_endpoint: str,
    ) -> Tuple[Optional[int], Optional[str]]:
        """
        Send a token refresh request with appropriate headers.

        :param payload: Token request payload
        :param token_endpoint: Token endpoint path
        :return: Tuple of (status_code, response_body) or (None, None) on failure
        """
        headers = self.get_common_headers(include_auth=False, recursive_call=True)
        headers.update(self.auth_manager.get_token_request_headers())

        body = self.auth_manager.format_token_request_body(payload)

        return self.send_request("POST", token_endpoint, headers, body)

    def refresh_token_and_update_auth(self) -> Optional[str]:
        """
        Perform a complete token refresh cycle and update the auth manager.

        This method handles the full token refresh process including:
        - Preparing the token request payload
        - Sending the token request
        - Processing the response and updating auth manager state

        :return: New access token if successful, None if failed
        """
        if not self.auth_manager.needs_token_refresh():
            return self.auth_manager.access_token

        logger.trace("Access token expired or missing, refreshing...")

        # Prepare token request payload
        payload = self.auth_manager._prepare_token_payload()

        # Send token request
        status, data = self.send_token_request(
            payload, self.auth_manager.token_endpoint
        )

        if status == 200 and data:
            try:
                token_data = json.loads(data)

                # Process the token response through auth manager
                if self.auth_manager.process_token_response(token_data):
                    logger.trace("Token refresh successful.")
                    return self.auth_manager.access_token
                else:
                    logger.error("Failed to process token response.")
                    return None

            except json.JSONDecodeError as e:
                logger.error("Failed to parse token response: %s", e)
                return None
        else:
            if status:
                logger.error("Token refresh failed: %s", status)
                logger.debug("Response body: %s", data)
            else:
                logger.error("Token refresh request failed completely")
            return None

    def get_instance_url(self) -> str:
        """
        Get the Salesforce instance URL.

        :return: The instance URL
        """
        return self.auth_manager.instance_url

    def get_api_version(self) -> str:
        """
        Get the API version being used.

        :return: The API version string
        """
        return self.auth_manager.api_version

    def is_connection_healthy(self) -> bool:
        """
        Check if the HTTP client can establish connections.

        This method performs a basic connectivity check without making
        actual API calls.

        :return: True if connection can be established, False otherwise
        """
        try:
            netloc = self.auth_manager.get_instance_netloc()
            conn = self.create_connection(netloc)
            conn.close()
            return True
        except Exception as e:
            logger.debug("Connection health check failed: %s", e)
            return False

    def __repr__(self) -> str:
        """String representation of HTTPClient for debugging."""
        return (
            f"HTTPClient(instance_url='{self.auth_manager.instance_url}', "
            f"user_agent='{self.user_agent}', "
            f"proxy={bool(self.auth_manager.get_proxy_config())})"
        )
