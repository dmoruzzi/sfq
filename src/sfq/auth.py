"""
Authentication module for the SFQ library.

This module handles OAuth token management, refresh logic, instance URL formatting,
and proxy configuration for Salesforce API authentication.
"""

import os
import time
from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote, urlparse

from .exceptions import AuthenticationError, ConfigurationError
from .utils import get_logger

logger = get_logger(__name__)


class AuthManager:
    """
    Manages OAuth authentication for Salesforce API access.

    This class handles token refresh, expiration checking, instance URL formatting,
    and proxy configuration. It encapsulates all authentication-related logic
    that was previously embedded in the main SFAuth class.
    """

    def __init__(
        self,
        instance_url: str,
        client_id: str,
        refresh_token: str,
        client_secret: str,
        api_version: str = "v65.0",
        token_endpoint: str = "/services/oauth2/token",
        access_token: Optional[str] = None,
        token_expiration_time: Optional[float] = None,
        token_lifetime: int = 15 * 60,
        proxy: str = "_auto",
    ) -> None:
        """
        Initialize the AuthManager with OAuth parameters.

        :param instance_url: The Salesforce instance URL
        :param client_id: The OAuth client ID
        :param refresh_token: The OAuth refresh token
        :param client_secret: The OAuth client secret
        :param api_version: The Salesforce API version
        :param token_endpoint: The token endpoint path
        :param access_token: Current access token (if available)
        :param token_expiration_time: Token expiration timestamp
        :param token_lifetime: Token lifetime in seconds
        :param proxy: Proxy configuration
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

        # Initialize proxy configuration
        self._configure_proxy(proxy)

        # Initialize org and user IDs (set during token refresh)
        self.org_id: Optional[str] = None
        self.user_id: Optional[str] = None

    def _format_instance_url(self, instance_url: str) -> str:
        """
        Format the instance URL to ensure HTTPS protocol.

        HTTPS is mandatory with Spring '21 release. This method ensures
        that the instance URL is formatted correctly.

        :param instance_url: The Salesforce instance URL
        :return: The formatted instance URL with HTTPS
        """
        if instance_url.startswith("https://"):
            return instance_url
        if instance_url.startswith("http://"):
            return instance_url.replace("http://", "https://")
        return f"https://{instance_url}"

    def _configure_proxy(self, proxy: str) -> None:
        """
        Configure the proxy based on the environment or provided value.

        :param proxy: Proxy configuration ("_auto" for environment detection)
        """
        if proxy == "_auto":
            self.proxy = os.environ.get("https_proxy")  # HTTPS is mandatory
            if self.proxy:
                logger.debug("Auto-configured proxy: %s", self.proxy)
        else:
            self.proxy = proxy
            if self.proxy:
                logger.debug("Using configured proxy: %s", self.proxy)

    def get_proxy_config(self) -> Optional[str]:
        """
        Get the current proxy configuration.

        :return: Proxy URL or None if no proxy is configured
        """
        return self.proxy

    def validate_proxy_config(self) -> bool:
        """
        Validate the current proxy configuration.

        :return: True if proxy config is valid or None, False if invalid
        """
        if not self.proxy:
            return True  # No proxy is valid

        try:
            parsed = urlparse(self.proxy)
            return (
                parsed.scheme in ("http", "https")
                and parsed.netloc
                and bool(parsed.hostname)
            )
        except Exception as e:
            logger.error("Proxy validation failed: %s", e)
            return False

    def get_proxy_netloc(self) -> Optional[str]:
        """
        Get the network location (host:port) from the proxy URL.

        :return: Network location string or None if no proxy
        :raises ConfigurationError: If proxy URL is invalid
        """
        if not self.proxy:
            return None

        try:
            parsed = urlparse(self.proxy)
            if not parsed.netloc:
                raise ConfigurationError(f"Invalid proxy URL: {self.proxy}")
            return parsed.netloc
        except Exception as e:
            raise ConfigurationError(f"Failed to parse proxy URL: {e}")

    def get_proxy_hostname_and_port(self) -> Optional[Tuple[str, Optional[int]]]:
        """
        Get the hostname and port from the proxy URL.

        :return: Tuple of (hostname, port) or None if no proxy
        :raises ConfigurationError: If proxy URL is invalid
        """
        if not self.proxy:
            return None

        try:
            parsed = urlparse(self.proxy)
            if not parsed.hostname:
                raise ConfigurationError(f"Invalid proxy URL: {self.proxy}")
            return parsed.hostname, parsed.port
        except Exception as e:
            raise ConfigurationError(f"Failed to parse proxy URL: {e}")

    def validate_instance_url(self) -> bool:
        """
        Validate that the instance URL is properly formatted.

        :return: True if valid, False otherwise
        """
        try:
            parsed = urlparse(self.instance_url)
            return (
                parsed.scheme == "https"
                and parsed.netloc
                and ".salesforce.com" in parsed.netloc
            )
        except Exception as e:
            logger.error("Instance URL validation failed: %s", e)
            return False

    def is_sandbox_instance(self) -> bool:
        """
        Check if the instance URL points to a sandbox environment.

        :return: True if sandbox, False if production or unknown
        """
        try:
            return ".sandbox." in self.instance_url or "--" in self.instance_url
        except Exception:
            return False

    def get_instance_type(self) -> str:
        """
        Determine the type of Salesforce instance.

        :return: String indicating instance type ('production', 'sandbox', 'trailblazer', 'unknown')
        """
        try:
            if ".trailblazer." in self.instance_url:
                return "trailblazer"
            elif ".sandbox." in self.instance_url or "--" in self.instance_url:
                return "sandbox"
            elif ".my.salesforce.com" in self.instance_url:
                return "production"
            else:
                return "unknown"
        except Exception:
            return "unknown"

    def normalize_instance_url(self) -> str:
        """
        Normalize the instance URL by removing trailing slashes and ensuring HTTPS.

        :return: Normalized instance URL
        """
        url = self._format_instance_url(self.instance_url)
        return url.rstrip("/")

    def get_base_domain(self) -> Optional[str]:
        """
        Extract the base domain from the instance URL.

        :return: Base domain or None if extraction fails
        """
        try:
            parsed = urlparse(self.instance_url)
            if parsed.hostname:
                # Extract the base domain (e.g., "my.salesforce.com" from "test.my.salesforce.com")
                parts = parsed.hostname.split(".")
                if len(parts) >= 3 and "salesforce.com" in parsed.hostname:
                    return ".".join(
                        parts[-3:]
                    )  # Get last 3 parts for "my.salesforce.com"
            return None
        except Exception as e:
            logger.error("Failed to extract base domain: %s", e)
            return None

    def is_token_expired(self) -> bool:
        """
        Check if the access token has expired.

        :return: True if token is expired or missing, False otherwise
        """
        if self.token_expiration_time == -1.0:
            return False # Token never expires
        try:
            return time.time() >= float(self.token_expiration_time)
        except (TypeError, ValueError):
            logger.warning("Token expiration check failed. Treating token as expired.")
            return True

    def _prepare_token_payload(self) -> Dict[str, Optional[str]]:
        """
        Prepare the payload for the token request.

        This method constructs a dictionary containing the necessary parameters
        for a token request using the refresh token grant type.

        :return: Dictionary containing the payload for the token request
        """
        payload = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
        }

        # Remove empty client_secret
        if not self.client_secret or self.client_secret == " ":
            payload.pop("client_secret", None)

        return payload

    def process_token_response(self, token_data: Dict[str, Any]) -> bool:
        """
        Process a successful token response and update internal state.

        :param token_data: The token response data from Salesforce
        :return: True if processing was successful, False otherwise
        """
        try:
            self.access_token = token_data.get("access_token")
            issued_at = token_data.get("issued_at")

            # Extract org and user IDs from the token response
            token_id = token_data.get("id")
            if token_id:
                try:
                    from .utils import extract_org_and_user_ids

                    self.org_id, self.user_id = extract_org_and_user_ids(token_id)
                    logger.trace(
                        "Authenticated as user %s for org %s (%s)",
                        self.user_id,
                        self.org_id,
                        token_data.get("instance_url"),
                    )
                except ValueError as e:
                    logger.error(
                        "Failed to extract org/user IDs from token response: %s", e
                    )

            # Calculate token expiration time
            if self.access_token and issued_at:
                self.token_expiration_time = int(issued_at) + self.token_lifetime
                logger.trace("New token expires at %s", self.token_expiration_time)
                return True

            return False

        except Exception as e:
            logger.error("Failed to process token response: %s", e)
            return False

    def get_auth_headers(self) -> Dict[str, str]:
        """
        Generate authentication headers for API requests.

        :return: Dictionary containing the Authorization header
        :raises AuthenticationError: If no valid access token is available
        """
        if not self.access_token:
            raise AuthenticationError("No access token available")

        return {
            "Authorization": f"Bearer {self.access_token}",
        }

    def get_token_request_headers(self) -> Dict[str, str]:
        """
        Generate headers for token refresh requests.

        :return: Dictionary containing headers for token requests
        """
        return {
            "Content-Type": "application/x-www-form-urlencoded",
        }

    def format_token_request_body(self, payload: Dict[str, str]) -> str:
        """
        Format the token request payload as URL-encoded form data.

        :param payload: The token request payload
        :return: URL-encoded form data string
        """
        return "&".join(f"{key}={quote(str(value))}" for key, value in payload.items())

    def get_token_endpoint_url(self) -> str:
        """
        Get the full URL for the token endpoint.

        :return: Complete token endpoint URL
        """
        return f"{self.instance_url}{self.token_endpoint}"

    def needs_token_refresh(self) -> bool:
        """
        Check if a token refresh is needed.

        :return: True if token refresh is needed, False otherwise
        """
        return not self.access_token or self.is_token_expired()

    def clear_token(self) -> None:
        """
        Clear the current access token and expiration time.

        This method is useful for forcing a token refresh or handling
        authentication failures.
        """
        self.access_token = None
        self.token_expiration_time = None
        self.org_id = None
        self.user_id = None
        logger.debug("Access token cleared")

    def get_instance_netloc(self) -> str:
        """
        Get the network location (host:port) from the instance URL.

        :return: Network location string
        :raises ConfigurationError: If instance URL is invalid
        """
        try:
            parsed = urlparse(self.instance_url)
            if not parsed.netloc:
                raise ConfigurationError(f"Invalid instance URL: {self.instance_url}")
            return parsed.netloc
        except Exception as e:
            raise ConfigurationError(f"Failed to parse instance URL: {e}")

    def __repr__(self) -> str:
        """String representation of AuthManager for debugging."""
        return (
            f"AuthManager(instance_url='{self.instance_url}', "
            f"client_id='{self.client_id}', "
            f"has_token={bool(self.access_token)}, "
            f"token_expired={self.is_token_expired() if self.access_token else 'N/A'})"
        )
