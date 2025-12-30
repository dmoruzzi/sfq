"""
HTTP client module for the SFQ library.

This module handles HTTP/HTTPS connection management, request/response handling,
proxy support, and unified request processing with logging and error handling.
"""

import errno
import http.client
import json
import time
from typing import Dict, Optional, Tuple

from .auth import AuthManager
from .exceptions import ConfigurationError, QueryTimeoutError
from .timeout_detector import TimeoutDetector
from .utils import format_headers_for_logging, get_logger, log_api_usage
from . import telemetry

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
        user_agent: str = "sfq/0.0.48",
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
        max_attempts = 10
        backoff_base_seconds = 1.0

        def _is_connection_timeout_error(exc: BaseException) -> bool:
            """
            Detect low-level connection timeout errors (including nested causes).

            We specifically look for:
            - OSError with errno == ETIMEDOUT
            - Messages like "Connection timed out"
            """
            current = exc
            while current is not None:
                if isinstance(current, OSError):
                    if getattr(current, "errno", None) in (
                        errno.ETIMEDOUT,
                        110,  # Common POSIX ETIMEDOUT value
                    ):
                        return True
                message = str(current).lower()
                if "connection timed out" in message or "timed out" in message:
                    return True
                current = getattr(current, "__cause__", None) or getattr(
                    current, "__context__", None
                )
            return False

        last_exception: Optional[Exception] = None

        for attempt in range(1, max_attempts + 1):
            conn = None
            try:
                attempt_start = time.time()
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

                # Emit telemetry (best-effort, non-blocking)
                try:
                    duration_ms = int((time.time() - attempt_start) * 1000)
                    ctx = {
                        "method": method,
                        "endpoint": endpoint,
                        "status": response.status,
                        "duration_ms": duration_ms,
                        "request_headers": headers,
                    }
                    telemetry.emit("http.request", ctx)
                except Exception:
                    pass

                return response.status, data

            except Exception as err:
                last_exception = err

                if _is_connection_timeout_error(err) and attempt < max_attempts:
                    # Connection timeout -> retry with exponential backoff
                    sleep_seconds = backoff_base_seconds * (2 ** (attempt - 1))
                    logger.warning(
                        "HTTP request attempt %d/%d failed due to connection timeout, "
                        "retrying in %.1fs: %s",
                        attempt,
                        max_attempts,
                        sleep_seconds,
                        err,
                    )
                    try:
                        if conn is not None:
                            conn.close()
                    except Exception:
                        pass
                    time.sleep(sleep_seconds)
                    continue

                # Non-timeout error or max attempts reached -> log and fail
                # Emit telemetry for failed attempt
                try:
                    duration_ms = 0
                    if 'attempt_start' in locals():
                        duration_ms = int((time.time() - attempt_start) * 1000)
                    ctx = {
                        "method": method,
                        "endpoint": endpoint,
                        "status": None,
                        "duration_ms": duration_ms,
                        "error": str(err),
                        "request_headers": headers,
                    }
                    telemetry.emit("http.request", ctx)
                except Exception:
                    pass

                logger.exception("HTTP request failed (attempt %d/%d): %s", attempt, max_attempts, err)
                return None, None

            finally:
                if conn is not None:
                    try:
                        logger.trace("Closing connection...")
                        conn.close()
                    except Exception as e:
                        logger.debug(
                            "Failed to close HTTP connection during cleanup: %s",
                            e,
                        )

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

    def send_authenticated_request_with_retry(
        self,
        method: str,
        endpoint: str,
        body: Optional[str] = None,
        additional_headers: Optional[Dict[str, str]] = None,
        max_retries: int = 3,
    ) -> Tuple[Optional[int], Optional[str]]:
        """
        Send an authenticated HTTP request with automatic timeout retry.

        This method wraps the existing send_authenticated_request with retry logic
        that handles timeout errors by retrying up to max_retries times.

        :param method: HTTP method
        :param endpoint: API endpoint path
        :param body: Optional request body
        :param additional_headers: Optional additional headers to include
        :param max_retries: Maximum number of retry attempts (default: 3)
        :return: Tuple of (status_code, response_body) or (None, None) on failure
        :raises QueryTimeoutError: When all retry attempts fail with timeout errors
        """
        # Validate retry count - negative values should be treated as 0
        if max_retries < 0:
            max_retries = 0
            
        last_exception = None
        request_context = f"{method} {endpoint}"
        
        # Log initial request context for debugging
        logger.trace("Starting request with retry capability: %s (max_retries=%d)", 
                    request_context, max_retries)
        
        for attempt in range(max_retries + 1):  # +1 for initial attempt
            try:
                # Make the request using the original method
                status, response_body = self._send_authenticated_request_internal(
                    method, endpoint, body, additional_headers
                )
                
                # Check if this is a timeout error
                if TimeoutDetector.is_timeout_error(status, response_body, last_exception):
                    timeout_type = TimeoutDetector.get_timeout_type(status, response_body, last_exception)
                    
                    if attempt < max_retries:
                        # Log detailed retry initiation with timeout type identification
                        logger.debug(
                            "Timeout detected (%s timeout) on attempt %d/%d for %s - "
                            "status_code=%s, retrying...",
                            timeout_type, attempt + 1, max_retries + 1, request_context, status
                        )
                        continue
                    else:
                        # All retries exhausted - log error before raising exception
                        logger.error(
                            "All %d retry attempts failed with timeout errors for %s - "
                            "final timeout type: %s, final status_code: %s",
                            max_retries + 1, request_context, timeout_type, status
                        )
                        raise QueryTimeoutError("QUERY_TIMEOUT")
                
                # Not a timeout error or successful response, return immediately
                if attempt > 0:
                    # Log successful retry recovery
                    logger.debug(
                        "Request succeeded on retry attempt %d/%d for %s - "
                        "status_code=%s, recovered from timeout",
                        attempt + 1, max_retries + 1, request_context, status
                    )
                else:
                    # Log successful first attempt (trace level to avoid noise)
                    logger.trace("Request succeeded on first attempt for %s - status_code=%s", 
                               request_context, status)
                
                return status, response_body
                
            except QueryTimeoutError:
                # Re-raise QueryTimeoutError without logging (it was already logged)
                raise
            except Exception as e:
                last_exception = e
                
                # Check if this exception indicates a timeout
                if TimeoutDetector.is_timeout_error(None, None, e):
                    timeout_type = TimeoutDetector.get_timeout_type(None, None, e)
                    
                    if attempt < max_retries:
                        # Log detailed retry initiation with exception context
                        logger.debug(
                            "Timeout exception (%s timeout) on attempt %d/%d for %s - "
                            "exception: %s, retrying...",
                            timeout_type, attempt + 1, max_retries + 1, request_context, 
                            type(e).__name__
                        )
                        continue
                    else:
                        # All retries exhausted - log error with exception details before raising
                        logger.error(
                            "All %d retry attempts failed with timeout errors for %s - "
                            "final timeout type: %s, final exception: %s",
                            max_retries + 1, request_context, timeout_type, type(e).__name__
                        )
                        raise QueryTimeoutError("QUERY_TIMEOUT")
                else:
                    # Not a timeout exception - log and re-raise immediately
                    logger.debug(
                        "Non-timeout exception on attempt %d for %s - "
                        "exception: %s, not retrying",
                        attempt + 1, request_context, type(e).__name__
                    )
                    raise e
        
        # This should never be reached, but just in case
        logger.error("Unexpected code path reached in retry logic for %s", request_context)
        raise QueryTimeoutError("QUERY_TIMEOUT")

    def _send_authenticated_request_internal(
        self,
        method: str,
        endpoint: str,
        body: Optional[str] = None,
        additional_headers: Optional[Dict[str, str]] = None,
    ) -> Tuple[Optional[int], Optional[str]]:
        """
        Internal method for sending authenticated requests without retry logic.
        
        This is the original send_authenticated_request logic extracted to avoid
        recursion in the retry wrapper.

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

    def send_authenticated_request(
        self,
        method: str,
        endpoint: str,
        body: Optional[str] = None,
        additional_headers: Optional[Dict[str, str]] = None,
        max_retries: int = 3,
    ) -> Tuple[Optional[int], Optional[str]]:
        """
        Send an authenticated HTTP request with automatic timeout retry.

        This is a convenience method that handles common request patterns
        with authentication, standard headers, and automatic retry for timeout errors.

        :param method: HTTP method
        :param endpoint: API endpoint path
        :param body: Optional request body
        :param additional_headers: Optional additional headers to include
        :param max_retries: Maximum number of retry attempts (default: 3)
        :return: Tuple of (status_code, response_body) or (None, None) on failure
        :raises QueryTimeoutError: When all retry attempts fail with timeout errors
        """
        return self.send_authenticated_request_with_retry(
            method, endpoint, body, additional_headers, max_retries
        )

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
