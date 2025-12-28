"""
Unit tests for the HTTPClient module.

Tests HTTP connection management, request handling, proxy support,
and error scenarios with mocked HTTP responses.
"""

import json
from unittest.mock import Mock, patch

import pytest

from sfq import __version__
from sfq.auth import AuthManager
from sfq.exceptions import ConfigurationError
from sfq.http_client import HTTPClient


class TestHTTPClient:
    """Test cases for HTTPClient class."""

    @pytest.fixture
    def auth_manager(self):
        """Create a mock AuthManager for testing."""
        auth_manager = Mock(spec=AuthManager)
        auth_manager.instance_url = "https://test.my.salesforce.com"
        auth_manager.api_version = "v65.0"
        auth_manager.access_token = "test_token_123"
        auth_manager.get_proxy_config.return_value = None
        auth_manager.get_instance_netloc.return_value = "test.my.salesforce.com"
        auth_manager.needs_token_refresh.return_value = False
        auth_manager.get_auth_headers.return_value = {
            "Authorization": "Bearer test_token_123"
        }
        auth_manager.get_token_request_headers.return_value = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        auth_manager.format_token_request_body.return_value = (
            "grant_type=refresh_token&client_id=test"
        )
        return auth_manager

    @pytest.fixture
    def http_client(self, auth_manager):
        """Create HTTPClient instance for testing."""
        return HTTPClient(
            auth_manager=auth_manager,
            user_agent="test-agent/1.0",
            sforce_client="test-client",
        )

    def test_init_default_values(self, auth_manager):
        """Test HTTPClient initialization with default values."""
        client = HTTPClient(auth_manager)

        assert client.auth_manager is auth_manager
        assert client.user_agent == f"sfq/{__version__}"
        assert client.sforce_client == f"sfq/{__version__}"
        assert client.high_api_usage_threshold == 80

    def test_init_custom_values(self, auth_manager):
        """Test HTTPClient initialization with custom values."""
        client = HTTPClient(
            auth_manager=auth_manager,
            user_agent="custom-agent/2.0",
            sforce_client="custom-client",
            high_api_usage_threshold=90,
        )

        assert client.user_agent == "custom-agent/2.0"
        assert client.sforce_client == "custom-client"
        assert client.high_api_usage_threshold == 90

    def test_init_removes_commas_from_sforce_client(self, auth_manager):
        """Test that commas are removed from sforce_client."""
        client = HTTPClient(
            auth_manager=auth_manager, sforce_client="test,client,with,commas"
        )

        assert client.sforce_client == "testclientwithcommas"

    @patch("sfq.http_client.http.client.HTTPSConnection")
    def test_create_connection_direct(self, mock_https_conn, http_client):
        """Test creating a direct HTTPS connection."""
        mock_conn = Mock()
        mock_https_conn.return_value = mock_conn

        result = http_client.create_connection("test.my.salesforce.com")

        mock_https_conn.assert_called_once_with("test.my.salesforce.com")
        assert result is mock_conn

    @patch("sfq.http_client.http.client.HTTPSConnection")
    def test_create_connection_with_proxy(self, mock_https_conn, http_client):
        """Test creating a connection through a proxy."""
        mock_conn = Mock()
        mock_https_conn.return_value = mock_conn

        # Configure proxy
        http_client.auth_manager.get_proxy_config.return_value = (
            "https://proxy.example.com:8080"
        )
        http_client.auth_manager.get_proxy_hostname_and_port.return_value = (
            "proxy.example.com",
            8080,
        )

        result = http_client.create_connection("test.my.salesforce.com")

        mock_https_conn.assert_called_once_with("proxy.example.com", 8080)
        mock_conn.set_tunnel.assert_called_once_with("test.my.salesforce.com")
        assert result is mock_conn

    def test_create_connection_proxy_error(self, http_client):
        """Test connection creation with invalid proxy configuration."""
        http_client.auth_manager.get_proxy_config.return_value = "invalid-proxy"
        http_client.auth_manager.get_proxy_hostname_and_port.side_effect = Exception(
            "Invalid proxy"
        )

        with pytest.raises(
            ConfigurationError, match="Failed to create proxy connection"
        ):
            http_client.create_connection("test.my.salesforce.com")

    def test_get_common_headers_with_auth(self, http_client):
        """Test generating common headers with authentication."""
        headers = http_client.get_common_headers(include_auth=True)

        expected_headers = {
            "User-Agent": "test-agent/1.0",
            "Sforce-Call-Options": "client=test-client",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": "Bearer test_token_123",
        }

        assert headers == expected_headers

    def test_get_common_headers_without_auth(self, http_client):
        """Test generating common headers without authentication."""
        headers = http_client.get_common_headers(include_auth=False)

        expected_headers = {
            "User-Agent": "test-agent/1.0",
            "Sforce-Call-Options": "client=test-client",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        assert headers == expected_headers
        assert "Authorization" not in headers

    def test_get_common_headers_recursive_call(self, http_client):
        """Test generating headers for recursive calls (token refresh)."""
        headers = http_client.get_common_headers(include_auth=True, recursive_call=True)

        # Should not include auth headers for recursive calls
        assert "Authorization" not in headers
        http_client.auth_manager.get_auth_headers.assert_not_called()

    @patch("sfq.http_client.HTTPClient.create_connection")
    def test_send_request_success(self, mock_create_conn, http_client):
        """Test successful HTTP request."""
        # Mock connection and response
        mock_conn = Mock()
        mock_response = Mock()
        mock_response.status = 200
        mock_response.reason = "OK"
        mock_response.read.return_value = b'{"success": true}'
        mock_response.getheaders.return_value = [("Content-Type", "application/json")]

        mock_conn.getresponse.return_value = mock_response
        mock_create_conn.return_value = mock_conn

        headers = {"Authorization": "Bearer token"}
        body = '{"test": "data"}'

        status, data = http_client.send_request("POST", "/test/endpoint", headers, body)

        assert status == 200
        assert data == '{"success": true}'

        mock_conn.request.assert_called_once_with(
            "POST", "/test/endpoint", body=body, headers=headers
        )
        mock_conn.close.assert_called_once()

    @patch("sfq.http_client.HTTPClient.create_connection")
    def test_send_request_connection_error(self, mock_create_conn, http_client):
        """Test HTTP request with connection error."""
        mock_create_conn.side_effect = Exception("Connection failed")

        status, data = http_client.send_request("GET", "/test", {})

        assert status is None
        assert data is None

    @patch("sfq.http_client.HTTPClient.create_connection")
    def test_send_request_response_error(self, mock_create_conn, http_client):
        """Test HTTP request with response reading error."""
        mock_conn = Mock()
        mock_conn.getresponse.side_effect = Exception("Response error")
        mock_create_conn.return_value = mock_conn

        status, data = http_client.send_request("GET", "/test", {})

        assert status is None
        assert data is None
        mock_conn.close.assert_called_once()

    @patch("sfq.http_client.HTTPClient.send_request")
    def test_send_authenticated_request(self, mock_send_request, http_client):
        """Test sending authenticated request."""
        mock_send_request.return_value = (200, '{"result": "success"}')

        status, data = http_client.send_authenticated_request(
            "GET",
            "/test/endpoint",
            body='{"test": "data"}',
            additional_headers={"Custom-Header": "value"},
        )

        assert status == 200
        assert data == '{"result": "success"}'

        # Verify the call was made with correct headers
        call_args = mock_send_request.call_args
        assert call_args[0][0] == "GET"  # method
        assert call_args[0][1] == "/test/endpoint"  # endpoint
        assert call_args[0][3] == '{"test": "data"}'  # body

        headers = call_args[0][2]  # headers
        assert "Authorization" in headers
        assert headers["Custom-Header"] == "value"

    @patch("sfq.http_client.HTTPClient.send_request")
    def test_send_token_request(self, mock_send_request, http_client):
        """Test sending token refresh request."""
        mock_send_request.return_value = (200, '{"access_token": "new_token"}')

        payload = {"grant_type": "refresh_token", "client_id": "test"}

        status, data = http_client.send_token_request(payload, "/oauth2/token")

        assert status == 200
        assert data == '{"access_token": "new_token"}'

        # Verify the call was made correctly
        call_args = mock_send_request.call_args
        assert call_args[0][0] == "POST"  # method
        assert call_args[0][1] == "/oauth2/token"  # endpoint

        headers = call_args[0][2]  # headers
        assert "Content-Type" in headers
        assert (
            "Authorization" not in headers
        )  # Should not include auth for token requests

    @patch("sfq.http_client.log_api_usage")
    def test_process_response_headers_api_usage(self, mock_log_usage, http_client):
        """Test processing response headers with API usage information."""
        mock_response = Mock()
        mock_response.status = 200
        mock_response.reason = "OK"
        mock_response.getheaders.return_value = [
            ("Content-Type", "application/json"),
            ("Sforce-Limit-Info", "api-usage=100/15000"),
        ]

        http_client._process_response_headers(mock_response)

        mock_log_usage.assert_called_once_with("api-usage=100/15000", 80)

    def test_get_instance_url(self, http_client):
        """Test getting instance URL."""
        assert http_client.get_instance_url() == "https://test.my.salesforce.com"

    def test_get_api_version(self, http_client):
        """Test getting API version."""
        assert http_client.get_api_version() == "v65.0"

    @patch("sfq.http_client.HTTPClient.create_connection")
    def test_is_connection_healthy_success(self, mock_create_conn, http_client):
        """Test connection health check success."""
        mock_conn = Mock()
        mock_create_conn.return_value = mock_conn

        result = http_client.is_connection_healthy()

        assert result is True
        mock_conn.close.assert_called_once()

    @patch("sfq.http_client.HTTPClient.create_connection")
    def test_is_connection_healthy_failure(self, mock_create_conn, http_client):
        """Test connection health check failure."""
        mock_create_conn.side_effect = Exception("Connection failed")

        result = http_client.is_connection_healthy()

        assert result is False

    def test_repr(self, http_client):
        """Test string representation of HTTPClient."""
        repr_str = repr(http_client)

        assert "HTTPClient" in repr_str
        assert "https://test.my.salesforce.com" in repr_str
        assert "test-agent/1.0" in repr_str
        assert "proxy=False" in repr_str


class TestHTTPClientIntegration:
    """Integration tests for HTTPClient with real-like scenarios."""

    @pytest.fixture
    def auth_manager_with_proxy(self):
        """Create AuthManager with proxy configuration."""
        auth_manager = Mock(spec=AuthManager)
        auth_manager.instance_url = "https://test.my.salesforce.com"
        auth_manager.api_version = "v65.0"
        auth_manager.access_token = "test_token_123"
        auth_manager.get_proxy_config.return_value = "https://proxy.example.com:8080"
        auth_manager.get_proxy_hostname_and_port.return_value = (
            "proxy.example.com",
            8080,
        )
        auth_manager.get_instance_netloc.return_value = "test.my.salesforce.com"
        auth_manager.needs_token_refresh.return_value = False
        auth_manager.get_auth_headers.return_value = {
            "Authorization": "Bearer test_token_123"
        }
        auth_manager.get_token_request_headers.return_value = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        auth_manager.format_token_request_body.return_value = (
            "grant_type=refresh_token&client_id=test"
        )
        return auth_manager

    @patch("sfq.http_client.http.client.HTTPSConnection")
    def test_full_request_cycle_with_proxy(
        self, mock_https_conn, auth_manager_with_proxy
    ):
        """Test complete request cycle with proxy configuration."""
        # Setup mocks
        mock_conn = Mock()
        mock_response = Mock()
        mock_response.status = 200
        mock_response.reason = "OK"
        mock_response.read.return_value = b'{"records": []}'
        mock_response.getheaders.return_value = [
            ("Content-Type", "application/json"),
            ("Sforce-Limit-Info", "api-usage=50/15000"),
        ]

        mock_conn.getresponse.return_value = mock_response
        mock_https_conn.return_value = mock_conn

        # Create client and make request
        client = HTTPClient(auth_manager_with_proxy)
        status, data = client.send_authenticated_request(
            "GET", "/services/data/v65.0/query?q=SELECT+Id+FROM+Account"
        )

        # Verify results
        assert status == 200
        assert data == '{"records": []}'

        # Verify proxy connection was used
        mock_https_conn.assert_called_once_with("proxy.example.com", 8080)
        mock_conn.set_tunnel.assert_called_once_with("test.my.salesforce.com")

        # Verify request was made
        mock_conn.request.assert_called_once()
        call_args = mock_conn.request.call_args
        assert call_args[0][0] == "GET"  # method
        assert "query" in call_args[0][1]  # endpoint contains query

    @patch("sfq.http_client.HTTPClient.send_request")
    def test_token_refresh_flow(self, mock_send_request, auth_manager_with_proxy):
        """Test token refresh request flow."""
        mock_send_request.return_value = (
            200,
            json.dumps(
                {
                    "access_token": "new_access_token",
                    "issued_at": "1234567890",
                    "instance_url": "https://test.my.salesforce.com",
                    "id": "https://login.salesforce.com/id/00D000000000000EAA/005000000000000AAA",
                }
            ),
        )

        client = HTTPClient(auth_manager_with_proxy)

        payload = {
            "grant_type": "refresh_token",
            "client_id": "test_client_id",
            "refresh_token": "test_refresh_token",
        }

        status, data = client.send_token_request(payload, "/services/oauth2/token")

        assert status == 200
        response_data = json.loads(data)
        assert response_data["access_token"] == "new_access_token"

        # Verify auth manager methods were called
        auth_manager_with_proxy.get_token_request_headers.assert_called_once()
        auth_manager_with_proxy.format_token_request_body.assert_called_once_with(
            payload
        )

    @patch("sfq.http_client.HTTPClient.send_token_request")
    def test_refresh_token_and_update_auth_success(
        self, mock_send_token_request, auth_manager_with_proxy
    ):
        """Test complete token refresh and auth update cycle."""
        # Setup mocks
        auth_manager_with_proxy.needs_token_refresh.return_value = True
        auth_manager_with_proxy.token_endpoint = "/services/oauth2/token"
        auth_manager_with_proxy._prepare_token_payload.return_value = {
            "grant_type": "refresh_token",
            "client_id": "test_client_id",
            "refresh_token": "test_refresh_token",
        }
        auth_manager_with_proxy.process_token_response.return_value = True
        auth_manager_with_proxy.access_token = "new_access_token"

        mock_send_token_request.return_value = (
            200,
            json.dumps(
                {
                    "access_token": "new_access_token",
                    "issued_at": "1234567890",
                    "instance_url": "https://test.my.salesforce.com",
                    "id": "https://login.salesforce.com/id/00D000000000000EAA/005000000000000AAA",
                }
            ),
        )

        client = HTTPClient(auth_manager_with_proxy)

        # Test the refresh
        result = client.refresh_token_and_update_auth()

        assert result == "new_access_token"
        auth_manager_with_proxy.needs_token_refresh.assert_called_once()
        auth_manager_with_proxy._prepare_token_payload.assert_called_once()
        auth_manager_with_proxy.process_token_response.assert_called_once()
        mock_send_token_request.assert_called_once()

    @patch("sfq.http_client.HTTPClient.send_token_request")
    def test_refresh_token_and_update_auth_no_refresh_needed(
        self, mock_send_token_request, auth_manager_with_proxy
    ):
        """Test token refresh when no refresh is needed."""
        auth_manager_with_proxy.needs_token_refresh.return_value = False
        auth_manager_with_proxy.access_token = "existing_token"

        client = HTTPClient(auth_manager_with_proxy)

        result = client.refresh_token_and_update_auth()

        assert result == "existing_token"
        mock_send_token_request.assert_not_called()

    @patch("sfq.http_client.HTTPClient.send_token_request")
    def test_refresh_token_and_update_auth_failure(
        self, mock_send_token_request, auth_manager_with_proxy
    ):
        """Test token refresh failure scenarios."""
        auth_manager_with_proxy.needs_token_refresh.return_value = True
        auth_manager_with_proxy.token_endpoint = "/services/oauth2/token"
        auth_manager_with_proxy._prepare_token_payload.return_value = {
            "grant_type": "refresh_token",
            "client_id": "test_client_id",
            "refresh_token": "test_refresh_token",
        }

        # Test HTTP error
        mock_send_token_request.return_value = (401, '{"error": "invalid_grant"}')

        client = HTTPClient(auth_manager_with_proxy)

        result = client.refresh_token_and_update_auth()

        assert result is None
        auth_manager_with_proxy.process_token_response.assert_not_called()

    @patch("sfq.http_client.HTTPClient.send_token_request")
    def test_refresh_token_and_update_auth_json_error(
        self, mock_send_token_request, auth_manager_with_proxy
    ):
        """Test token refresh with invalid JSON response."""
        auth_manager_with_proxy.needs_token_refresh.return_value = True
        auth_manager_with_proxy.token_endpoint = "/services/oauth2/token"
        auth_manager_with_proxy._prepare_token_payload.return_value = {
            "grant_type": "refresh_token",
            "client_id": "test_client_id",
            "refresh_token": "test_refresh_token",
        }

        # Test invalid JSON
        mock_send_token_request.return_value = (200, "invalid json")

        client = HTTPClient(auth_manager_with_proxy)

        result = client.refresh_token_and_update_auth()

        assert result is None
        auth_manager_with_proxy.process_token_response.assert_not_called()
