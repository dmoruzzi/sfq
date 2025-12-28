"""
Unit tests for the AuthManager class.

This module contains comprehensive tests for authentication functionality,
including token management, expiration checking, proxy configuration,
and instance URL formatting.
"""

import os
import time
import warnings
from unittest.mock import patch

import pytest

from sfq.auth import AuthManager
from sfq.exceptions import AuthenticationError, ConfigurationError


class TestAuthManager:
    """Test cases for the AuthManager class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.instance_url = "https://test.my.salesforce.com"
        self.client_id = "test_client_id"
        self.refresh_token = "test_refresh_token"
        self.client_secret = "test_client_secret"

    def test_init_basic(self):
        """Test basic initialization of AuthManager."""
        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
        )

        assert auth.instance_url == self.instance_url
        assert auth.client_id == self.client_id
        assert auth.refresh_token == self.refresh_token
        assert auth.client_secret == self.client_secret
        assert auth.api_version == "v65.0"
        assert auth.token_endpoint == "/services/oauth2/token"
        assert auth.access_token is None
        assert auth.token_expiration_time is None
        assert auth.token_lifetime == 15 * 60
        assert auth.org_id is None
        assert auth.user_id is None

    def test_init_with_all_parameters(self):
        """Test initialization with all parameters."""
        access_token = "test_access_token"
        token_expiration_time = time.time() + 900

        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
            api_version="v59.0",
            token_endpoint="/custom/token",
            access_token=access_token,
            token_expiration_time=token_expiration_time,
            token_lifetime=1800,
            proxy="http://proxy.example.com:8080",
        )

        assert auth.api_version == "v59.0"
        assert auth.token_endpoint == "/custom/token"
        assert auth.access_token == access_token
        assert auth.token_expiration_time == token_expiration_time
        assert auth.token_lifetime == 1800
        assert auth.proxy == "http://proxy.example.com:8080"

    def test_format_instance_url_https(self):
        """Test instance URL formatting with HTTPS."""
        auth = AuthManager(
            instance_url="https://test.my.salesforce.com",
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
        )
        assert auth.instance_url == "https://test.my.salesforce.com"

    def test_format_instance_url_http(self):
        """Test instance URL formatting converts HTTP to HTTPS."""
        auth = AuthManager(
            instance_url="http://test.my.salesforce.com",
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
        )
        assert auth.instance_url == "https://test.my.salesforce.com"

    def test_format_instance_url_no_protocol(self):
        """Test instance URL formatting adds HTTPS protocol."""
        auth = AuthManager(
            instance_url="test.my.salesforce.com",
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
        )
        assert auth.instance_url == "https://test.my.salesforce.com"

    @patch.dict(os.environ, {"https_proxy": "http://env-proxy.example.com:8080"})
    def test_configure_proxy_auto_with_env(self):
        """Test proxy auto-configuration with environment variable."""
        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
            proxy="_auto",
        )
        assert auth.proxy == "http://env-proxy.example.com:8080"

    @patch.dict(os.environ, {}, clear=True)
    def test_configure_proxy_auto_without_env(self):
        """Test proxy auto-configuration without environment variable."""
        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
            proxy="_auto",
        )
        assert auth.proxy is None

    def test_configure_proxy_explicit(self):
        """Test explicit proxy configuration."""
        proxy_url = "http://explicit-proxy.example.com:8080"
        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
            proxy=proxy_url,
        )
        assert auth.proxy == proxy_url

    def test_get_proxy_config(self):
        """Test getting proxy configuration."""
        proxy_url = "http://test-proxy.example.com:8080"
        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
            proxy=proxy_url,
        )
        assert auth.get_proxy_config() == proxy_url

    def test_validate_instance_url_valid(self):
        """Test instance URL validation with valid URL."""
        auth = AuthManager(
            instance_url="https://test.my.salesforce.com",
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
        )
        assert auth.validate_instance_url() is True

    def test_validate_instance_url_invalid_protocol(self):
        """Test instance URL validation with invalid protocol."""
        auth = AuthManager(
            instance_url="http://test.my.salesforce.com",  # Will be converted to HTTPS
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
        )
        # Should be valid after conversion to HTTPS
        assert auth.validate_instance_url() is True

    def test_validate_instance_url_invalid_domain(self):
        """Test instance URL validation with invalid domain."""
        auth = AuthManager(
            instance_url="https://invalid-domain.com",
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
        )
        assert auth.validate_instance_url() is False

    def test_is_token_expired_no_token(self):
        """Test token expiration check with no token."""
        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
        )
        assert auth.is_token_expired() is True

    def test_is_token_expired_valid_token(self):
        """Test token expiration check with valid token."""
        future_time = time.time() + 900  # 15 minutes in the future
        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
            token_expiration_time=future_time,
        )
        assert auth.is_token_expired() is False

    def test_is_token_expired_expired_token(self):
        """Test token expiration check with expired token."""
        past_time = time.time() - 900  # 15 minutes in the past
        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
            token_expiration_time=past_time,
        )
        assert auth.is_token_expired() is True

    def test_is_token_expired_invalid_time(self):
        """Test token expiration check with invalid expiration time."""
        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
            token_expiration_time="invalid",
        )
        assert auth.is_token_expired() is True

    def test_prepare_token_payload_basic(self):
        """Test token payload preparation with basic parameters."""
        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
        )

        payload = auth._prepare_token_payload()

        expected = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
        }
        assert payload == expected

    def test_init_missing_client_secret(self):
        """Ensure AuthManager raises TypeError when client_secret is omitted."""
        with pytest.raises(TypeError) as excinfo:
            # Intentionally omit the `client_secret` argument.
            AuthManager(
                instance_url=self.instance_url,
                client_id=self.client_id,
                refresh_token=self.refresh_token,
                # client_secret missing
            )
        assert "missing 1 required positional argument: 'client_secret'" in str(excinfo.value)

    def test_prepare_token_payload_with_empty_client_secret(self):
        """Test token payload preparation with deprecation warning."""
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")

            auth = AuthManager(
                instance_url=self.instance_url,
                client_id=self.client_id,
                refresh_token=self.refresh_token,
                client_secret="",
            )

        payload = auth._prepare_token_payload()

        expected = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "refresh_token": self.refresh_token,
        }
        assert payload == expected
        assert "client_secret" not in payload

    def test_prepare_token_payload_empty_client_secret(self):
        """Test token payload preparation with empty client secret."""
        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret="",
        )

        payload = auth._prepare_token_payload()

        expected = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "refresh_token": self.refresh_token,
        }
        assert payload == expected
        assert "client_secret" not in payload

    def test_process_token_response_success(self):
        """Test successful token response processing."""
        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
        )

        token_data = {
            "access_token": "new_access_token",
            "issued_at": str(int(time.time())),
            "id": "https://login.salesforce.com/id/00D000000000000EAA/005000000000000AAA",
            "instance_url": "https://test.my.salesforce.com",
        }

        result = auth.process_token_response(token_data)

        assert result is True
        assert auth.access_token == "new_access_token"
        assert auth.org_id == "00D000000000000EAA"
        assert auth.user_id == "005000000000000AAA"
        assert auth.token_expiration_time is not None

    def test_process_token_response_missing_access_token(self):
        """Test token response processing with missing access token."""
        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
        )

        token_data = {
            "issued_at": str(int(time.time())),
        }

        result = auth.process_token_response(token_data)

        assert result is False
        assert auth.access_token is None

    def test_process_token_response_invalid_id_format(self):
        """Test token response processing with invalid ID format."""
        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
        )

        token_data = {
            "access_token": "new_access_token",
            "issued_at": str(int(time.time())),
            "id": "invalid_id_format",
        }

        result = auth.process_token_response(token_data)

        assert result is True  # Should still succeed despite ID parsing failure
        assert auth.access_token == "new_access_token"
        assert auth.org_id is None
        assert auth.user_id is None

    def test_get_auth_headers_with_token(self):
        """Test getting authentication headers with valid token."""
        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
            access_token="test_access_token",
        )

        headers = auth.get_auth_headers()

        expected = {
            "Authorization": "Bearer test_access_token",
        }
        assert headers == expected

    def test_get_auth_headers_no_token(self):
        """Test getting authentication headers without token raises error."""
        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
        )

        with pytest.raises(AuthenticationError, match="No access token available"):
            auth.get_auth_headers()

    def test_get_token_request_headers(self):
        """Test getting token request headers."""
        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
        )

        headers = auth.get_token_request_headers()

        expected = {
            "Content-Type": "application/x-www-form-urlencoded",
        }
        assert headers == expected

    def test_format_token_request_body(self):
        """Test formatting token request body."""
        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
        )

        payload = {
            "grant_type": "refresh_token",
            "client_id": "test_client",
            "refresh_token": "test_token",
        }

        body = auth.format_token_request_body(payload)

        # Check that all parameters are present (order may vary)
        assert "grant_type=refresh_token" in body
        assert "client_id=test_client" in body
        assert "refresh_token=test_token" in body
        assert body.count("&") == 2  # Two separators for three parameters

    def test_get_token_endpoint_url(self):
        """Test getting token endpoint URL."""
        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
        )

        url = auth.get_token_endpoint_url()

        expected = f"{self.instance_url}/services/oauth2/token"
        assert url == expected

    def test_needs_token_refresh_no_token(self):
        """Test token refresh check with no token."""
        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
        )

        assert auth.needs_token_refresh() is True

    def test_needs_token_refresh_expired_token(self):
        """Test token refresh check with expired token."""
        past_time = time.time() - 900
        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
            access_token="expired_token",
            token_expiration_time=past_time,
        )

        assert auth.needs_token_refresh() is True

    def test_needs_token_refresh_valid_token(self):
        """Test token refresh check with valid token."""
        future_time = time.time() + 900
        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
            access_token="valid_token",
            token_expiration_time=future_time,
        )

        assert auth.needs_token_refresh() is False

    def test_clear_token(self):
        """Test clearing token and related data."""
        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
            access_token="test_token",
            token_expiration_time=time.time() + 900,
        )

        # Set some additional data
        auth.org_id = "test_org"
        auth.user_id = "test_user"

        auth.clear_token()

        assert auth.access_token is None
        assert auth.token_expiration_time is None
        assert auth.org_id is None
        assert auth.user_id is None

    def test_get_instance_netloc_valid(self):
        """Test getting instance network location."""
        auth = AuthManager(
            instance_url="https://test.my.salesforce.com",
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
        )

        netloc = auth.get_instance_netloc()
        assert netloc == "test.my.salesforce.com"

    def test_get_instance_netloc_with_port(self):
        """Test getting instance network location with port."""
        auth = AuthManager(
            instance_url="https://test.my.salesforce.com:8080",
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
        )

        netloc = auth.get_instance_netloc()
        assert netloc == "test.my.salesforce.com:8080"

    def test_get_instance_netloc_invalid_url(self):
        """Test getting instance network location with invalid URL."""
        # Create auth with valid URL first, then modify to invalid
        auth = AuthManager(
            instance_url="https://test.my.salesforce.com",
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
        )

        # Manually set invalid URL to test error handling
        auth.instance_url = "invalid_url"

        with pytest.raises(ConfigurationError, match="Invalid instance URL"):
            auth.get_instance_netloc()

    def test_validate_proxy_config_no_proxy(self):
        """Test proxy validation with no proxy configured."""
        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
            proxy=None,
        )

        assert auth.validate_proxy_config() is True

    def test_validate_proxy_config_valid_http(self):
        """Test proxy validation with valid HTTP proxy."""
        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
            proxy="http://proxy.example.com:8080",
        )

        assert auth.validate_proxy_config() is True

    def test_validate_proxy_config_valid_https(self):
        """Test proxy validation with valid HTTPS proxy."""
        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
            proxy="https://proxy.example.com:8080",
        )

        assert auth.validate_proxy_config() is True

    def test_validate_proxy_config_invalid_scheme(self):
        """Test proxy validation with invalid scheme."""
        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
            proxy="ftp://proxy.example.com:8080",
        )

        assert auth.validate_proxy_config() is False

    def test_validate_proxy_config_invalid_format(self):
        """Test proxy validation with invalid format."""
        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
            proxy="invalid_proxy_format",
        )

        assert auth.validate_proxy_config() is False

    def test_get_proxy_netloc_no_proxy(self):
        """Test getting proxy netloc with no proxy."""
        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
            proxy=None,
        )

        assert auth.get_proxy_netloc() is None

    def test_get_proxy_netloc_valid(self):
        """Test getting proxy netloc with valid proxy."""
        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
            proxy="http://proxy.example.com:8080",
        )

        netloc = auth.get_proxy_netloc()
        assert netloc == "proxy.example.com:8080"

    def test_get_proxy_netloc_invalid(self):
        """Test getting proxy netloc with invalid proxy."""
        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
            proxy="invalid_proxy",
        )

        with pytest.raises(ConfigurationError, match="Invalid proxy URL"):
            auth.get_proxy_netloc()

    def test_get_proxy_hostname_and_port_no_proxy(self):
        """Test getting proxy hostname and port with no proxy."""
        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
            proxy=None,
        )

        assert auth.get_proxy_hostname_and_port() is None

    def test_get_proxy_hostname_and_port_with_port(self):
        """Test getting proxy hostname and port with explicit port."""
        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
            proxy="http://proxy.example.com:8080",
        )

        hostname, port = auth.get_proxy_hostname_and_port()
        assert hostname == "proxy.example.com"
        assert port == 8080

    def test_get_proxy_hostname_and_port_no_port(self):
        """Test getting proxy hostname and port without explicit port."""
        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
            proxy="http://proxy.example.com",
        )

        hostname, port = auth.get_proxy_hostname_and_port()
        assert hostname == "proxy.example.com"
        assert port is None

    def test_is_sandbox_instance_production(self):
        """Test sandbox detection with production instance."""
        auth = AuthManager(
            instance_url="https://mycompany.my.salesforce.com",
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
        )

        assert auth.is_sandbox_instance() is False

    def test_is_sandbox_instance_sandbox_with_sandbox_keyword(self):
        """Test sandbox detection with sandbox keyword."""
        auth = AuthManager(
            instance_url="https://mycompany--dev.sandbox.my.salesforce.com",
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
        )

        assert auth.is_sandbox_instance() is True

    def test_is_sandbox_instance_sandbox_with_double_dash(self):
        """Test sandbox detection with double dash."""
        auth = AuthManager(
            instance_url="https://mycompany--dev.my.salesforce.com",
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
        )

        assert auth.is_sandbox_instance() is True

    def test_get_instance_type_production(self):
        """Test instance type detection for production."""
        auth = AuthManager(
            instance_url="https://mycompany.my.salesforce.com",
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
        )

        assert auth.get_instance_type() == "production"

    def test_get_instance_type_sandbox(self):
        """Test instance type detection for sandbox."""
        auth = AuthManager(
            instance_url="https://mycompany--dev.sandbox.my.salesforce.com",
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
        )

        assert auth.get_instance_type() == "sandbox"

    def test_get_instance_type_trailblazer(self):
        """Test instance type detection for trailblazer."""
        auth = AuthManager(
            instance_url="https://mycompany-dev-ed.trailblazer.my.salesforce.com",
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
        )

        assert auth.get_instance_type() == "trailblazer"

    def test_get_instance_type_unknown(self):
        """Test instance type detection for unknown."""
        auth = AuthManager(
            instance_url="https://unknown.example.com",
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
        )

        assert auth.get_instance_type() == "unknown"

    def test_normalize_instance_url_with_trailing_slash(self):
        """Test instance URL normalization with trailing slash."""
        auth = AuthManager(
            instance_url="https://test.my.salesforce.com/",
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
        )

        normalized = auth.normalize_instance_url()
        assert normalized == "https://test.my.salesforce.com"

    def test_normalize_instance_url_http_to_https(self):
        """Test instance URL normalization converts HTTP to HTTPS."""
        auth = AuthManager(
            instance_url="http://test.my.salesforce.com/",
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
        )

        normalized = auth.normalize_instance_url()
        assert normalized == "https://test.my.salesforce.com"

    def test_get_base_domain_production(self):
        """Test base domain extraction for production instance."""
        auth = AuthManager(
            instance_url="https://mycompany.my.salesforce.com",
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
        )

        domain = auth.get_base_domain()
        assert domain == "my.salesforce.com"

    def test_get_base_domain_sandbox(self):
        """Test base domain extraction for sandbox instance."""
        auth = AuthManager(
            instance_url="https://mycompany--dev.sandbox.my.salesforce.com",
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
        )

        domain = auth.get_base_domain()
        assert domain == "my.salesforce.com"

    def test_get_base_domain_invalid_url(self):
        """Test base domain extraction with invalid URL."""
        auth = AuthManager(
            instance_url="https://invalid.com",
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
        )

        domain = auth.get_base_domain()
        assert domain is None

    def test_repr(self):
        """Test string representation of AuthManager."""
        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
            access_token="test_token",
        )

        repr_str = repr(auth)
        assert "AuthManager" in repr_str
        assert self.instance_url in repr_str
        assert self.client_id in repr_str
        assert "has_token=True" in repr_str
        assert "token_expired=" in repr_strze_instance_url()
        assert normalized == "https://test.my.salesforce.com"

    def test_get_base_domain_production(self):
        """Test base domain extraction for production instance."""
        auth = AuthManager(
            instance_url="https://mycompany.my.salesforce.com",
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
        )

        base_domain = auth.get_base_domain()
        assert base_domain == "my.salesforce.com"

    def test_get_base_domain_sandbox(self):
        """Test base domain extraction for sandbox instance."""
        auth = AuthManager(
            instance_url="https://mycompany--dev.sandbox.my.salesforce.com",
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
        )

        base_domain = auth.get_base_domain()
        assert base_domain == "my.salesforce.com"

    def test_get_base_domain_invalid(self):
        """Test base domain extraction with invalid URL."""
        auth = AuthManager(
            instance_url="https://invalid.example.com",
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
        )

        base_domain = auth.get_base_domain()
        assert base_domain is None

    def test_repr(self):
        """Test string representation of AuthManager."""
        auth = AuthManager(
            instance_url=self.instance_url,
            client_id=self.client_id,
            refresh_token=self.refresh_token,
            client_secret=self.client_secret,
            access_token="test_token",
        )

        repr_str = repr(auth)

        assert "AuthManager" in repr_str
        assert self.instance_url in repr_str
        assert self.client_id in repr_str
        assert "has_token=True" in repr_str
        assert "token_expired=" in repr_str
