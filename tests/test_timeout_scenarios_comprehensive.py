"""
Comprehensive test suite for timeout scenarios.

This module provides comprehensive testing of timeout detection and retry behavior
across different scenarios including server timeouts, connection timeouts, mixed
scenarios, and integration with QueryClient operations.
"""

import errno
import json
from unittest.mock import Mock, patch

import pytest

from sfq.auth import AuthManager
from sfq.exceptions import QueryTimeoutError
from sfq.http_client import HTTPClient
from sfq.query import QueryClient
from sfq.timeout_detector import TimeoutDetector


class TestServerTimeoutScenarios:
    """Test server timeout detection and retry behavior."""

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
        return auth_manager

    @pytest.fixture
    def http_client(self, auth_manager):
        """Create HTTPClient instance for testing."""
        return HTTPClient(
            auth_manager=auth_manager,
            user_agent="test-agent/1.0",
            sforce_client="test-client",
        )

    def test_server_timeout_with_exact_message_retry_success(self, http_client):
        """Test server timeout with exact message that succeeds on retry."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # First call returns server timeout, second call succeeds
            mock_internal.side_effect = [
                (400, "Your query request was running for too long."),
                (200, '{"records": [{"Id": "001000000000001"}]}')
            ]

            status, data = http_client.send_authenticated_request_with_retry(
                "GET", "/services/data/v65.0/query", max_retries=3
            )

            assert status == 200
            assert data == '{"records": [{"Id": "001000000000001"}]}'
            assert mock_internal.call_count == 2

    def test_server_timeout_with_error_code_retry_success(self, http_client):
        """Test server timeout with QUERY_TIMEOUT error code that succeeds on retry."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # First call returns server timeout with error code, second call succeeds
            mock_internal.side_effect = [
                (400, '[{"message":"Query execution exceeded time limit","errorCode":"QUERY_TIMEOUT"}]'),
                (200, '{"records": []}')
            ]

            status, data = http_client.send_authenticated_request_with_retry(
                "POST", "/services/data/v65.0/composite", max_retries=3
            )

            assert status == 200
            assert data == '{"records": []}'
            assert mock_internal.call_count == 2

    def test_server_timeout_all_retries_fail(self, http_client):
        """Test server timeout that fails on all retry attempts."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # All calls return server timeout
            mock_internal.return_value = (
                400, 
                "Error: Your query request was running for too long. Please try again."
            )

            with pytest.raises(QueryTimeoutError, match="QUERY_TIMEOUT"):
                http_client.send_authenticated_request_with_retry(
                    "GET", "/services/data/v65.0/query", max_retries=2
                )

            # Should try initial + 2 retries = 3 total attempts
            assert mock_internal.call_count == 3

    def test_server_timeout_mixed_responses(self, http_client):
        """Test server timeout with mixed response formats."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # Different server timeout response formats, then success
            mock_internal.side_effect = [
                (400, "Your query request was running for too long."),
                (400, '[{"errorCode":"QUERY_TIMEOUT","message":"Timeout occurred"}]'),
                (200, '{"success": true}')
            ]

            status, data = http_client.send_authenticated_request_with_retry(
                "PATCH", "/services/data/v65.0/sobjects/Account/001", max_retries=3
            )

            assert status == 200
            assert data == '{"success": true}'
            assert mock_internal.call_count == 3

    def test_server_timeout_preserves_request_parameters(self, http_client):
        """Test that server timeout retries preserve original request parameters."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # First call returns server timeout, second call succeeds
            mock_internal.side_effect = [
                (400, "Your query request was running for too long."),
                (200, '{"updated": true}')
            ]

            method = "POST"
            endpoint = "/services/data/v65.0/composite/batch"
            body = '{"batchRequests": []}'
            additional_headers = {"Custom-Header": "test-value", "X-Request-ID": "12345"}

            status, data = http_client.send_authenticated_request_with_retry(
                method, endpoint, body, additional_headers, max_retries=3
            )

            assert status == 200
            assert data == '{"updated": true}'
            assert mock_internal.call_count == 2

            # Verify both calls had identical parameters
            first_call = mock_internal.call_args_list[0]
            second_call = mock_internal.call_args_list[1]
            assert first_call == second_call
            assert first_call[0] == (method, endpoint, body, additional_headers)

    @patch("sfq.http_client.logger")
    def test_server_timeout_logging_behavior(self, mock_logger, http_client):
        """Test detailed logging behavior for server timeout scenarios."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # First call returns server timeout, second call succeeds
            mock_internal.side_effect = [
                (400, '[{"message":"Your query request was running for too long.","errorCode":"QUERY_TIMEOUT"}]'),
                (200, '{"records": []}')
            ]

            status, data = http_client.send_authenticated_request_with_retry(
                "GET", "/services/data/v65.0/query", max_retries=3
            )

            assert status == 200

            # Verify trace logging for initial request
            trace_calls = [call for call in mock_logger.trace.call_args_list]
            assert len(trace_calls) >= 1
            initial_trace = trace_calls[0]
            assert "Starting request with retry capability" in initial_trace[0][0]

            # Verify debug logging for retry attempt
            debug_calls = [call for call in mock_logger.debug.call_args_list]
            assert len(debug_calls) == 2

            # Check retry initiation log
            retry_log = debug_calls[0]
            retry_format = retry_log[0][0]
            retry_args = retry_log[0][1:]
            assert "Timeout detected" in retry_format
            assert "server" in retry_args  # timeout_type
            assert 1 in retry_args  # attempt number
            assert 400 in retry_args  # status code

            # Check successful retry recovery log
            success_log = debug_calls[1]
            success_format = success_log[0][0]
            assert "Request succeeded on retry attempt" in success_format
            assert "recovered from timeout" in success_format


class TestConnectionTimeoutScenarios:
    """Test connection timeout detection and retry behavior."""

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
        return auth_manager

    @pytest.fixture
    def http_client(self, auth_manager):
        """Create HTTPClient instance for testing."""
        return HTTPClient(
            auth_manager=auth_manager,
            user_agent="test-agent/1.0",
            sforce_client="test-client",
        )

    def test_connection_timeout_with_errno_110_retry_success(self, http_client):
        """Test connection timeout with errno 110 that succeeds on retry."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # Create a connection timeout exception
            timeout_exception = OSError("Connection timed out")
            timeout_exception.errno = errno.ETIMEDOUT

            # First call raises timeout exception, second call succeeds
            mock_internal.side_effect = [
                timeout_exception,
                (200, '{"records": [{"Id": "003000000000001"}]}')
            ]

            status, data = http_client.send_authenticated_request_with_retry(
                "GET", "/services/data/v65.0/tooling/query", max_retries=3
            )

            assert status == 200
            assert data == '{"records": [{"Id": "003000000000001"}]}'
            assert mock_internal.call_count == 2

    def test_connection_timeout_with_nested_exception_retry_success(self, http_client):
        """Test connection timeout with nested exception structure that succeeds on retry."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # Create a nested timeout exception (common in urllib/http.client)
            inner_exception = OSError("Connection timed out")
            inner_exception.errno = errno.ETIMEDOUT
            
            outer_exception = Exception("Request failed")
            outer_exception.__cause__ = inner_exception

            # First call raises nested timeout exception, second call succeeds
            mock_internal.side_effect = [
                outer_exception,
                (200, '{"success": true}')
            ]

            status, data = http_client.send_authenticated_request_with_retry(
                "POST", "/services/data/v65.0/composite", max_retries=3
            )

            assert status == 200
            assert data == '{"success": true}'
            assert mock_internal.call_count == 2

    def test_connection_timeout_all_retries_fail(self, http_client):
        """Test connection timeout that fails on all retry attempts."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # Create a connection timeout exception
            timeout_exception = OSError("Connection timed out")
            timeout_exception.errno = errno.ETIMEDOUT

            # All calls raise timeout exception
            mock_internal.side_effect = timeout_exception

            with pytest.raises(QueryTimeoutError, match="QUERY_TIMEOUT"):
                http_client.send_authenticated_request_with_retry(
                    "DELETE", "/services/data/v65.0/sobjects/Account/001", max_retries=2
                )

            # Should try initial + 2 retries = 3 total attempts
            assert mock_internal.call_count == 3

    def test_connection_timeout_with_errno_in_args(self, http_client):
        """Test connection timeout detection with errno in exception args."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # Create an exception with errno in args
            arg_with_errno = Mock()
            arg_with_errno.errno = errno.ETIMEDOUT
            
            exception = Exception("Connection failed")
            exception.args = [arg_with_errno, "additional info"]

            # First call raises timeout exception, second call succeeds
            mock_internal.side_effect = [
                exception,
                (200, '{"processed": true}')
            ]

            status, data = http_client.send_authenticated_request_with_retry(
                "PATCH", "/services/data/v65.0/sobjects/Contact/003", max_retries=3
            )

            assert status == 200
            assert data == '{"processed": true}'
            assert mock_internal.call_count == 2

    @patch("sfq.http_client.logger")
    def test_connection_timeout_logging_behavior(self, mock_logger, http_client):
        """Test detailed logging behavior for connection timeout scenarios."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # Create a connection timeout exception
            timeout_exception = OSError("Connection timed out")
            timeout_exception.errno = errno.ETIMEDOUT

            # First call raises timeout exception, second call succeeds
            mock_internal.side_effect = [
                timeout_exception,
                (200, '{"success": true}')
            ]

            status, data = http_client.send_authenticated_request_with_retry(
                "GET", "/services/data/v65.0/query", max_retries=2
            )

            assert status == 200

            # Verify debug logging for exception-based retry
            debug_calls = [call for call in mock_logger.debug.call_args_list]
            assert len(debug_calls) == 2

            # Check timeout exception retry log
            exception_retry_log = debug_calls[0]
            exception_format = exception_retry_log[0][0]
            exception_args = exception_retry_log[0][1:]
            
            assert "Timeout exception" in exception_format
            assert "connection" in exception_args  # timeout_type
            assert 1 in exception_args  # attempt number
            assert "OSError" in exception_args  # exception type

            # Check successful retry recovery log
            success_log = debug_calls[1]
            success_format = success_log[0][0]
            assert "Request succeeded on retry attempt" in success_format


class TestMixedTimeoutScenarios:
    """Test mixed timeout scenarios with various combinations."""

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
        return auth_manager

    @pytest.fixture
    def http_client(self, auth_manager):
        """Create HTTPClient instance for testing."""
        return HTTPClient(
            auth_manager=auth_manager,
            user_agent="test-agent/1.0",
            sforce_client="test-client",
        )

    def test_server_then_connection_timeout_then_success(self, http_client):
        """Test server timeout followed by connection timeout then success."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # Create a connection timeout exception
            timeout_exception = OSError("Connection timed out")
            timeout_exception.errno = errno.ETIMEDOUT

            # Mixed scenario: server timeout, then connection timeout, then success
            mock_internal.side_effect = [
                (400, '[{"message":"Your query request was running for too long.","errorCode":"QUERY_TIMEOUT"}]'),
                timeout_exception,
                (200, '{"records": []}')
            ]

            status, data = http_client.send_authenticated_request_with_retry(
                "GET", "/services/data/v65.0/query", max_retries=3
            )

            assert status == 200
            assert data == '{"records": []}'
            assert mock_internal.call_count == 3

    def test_connection_then_server_timeout_then_success(self, http_client):
        """Test connection timeout followed by server timeout then success."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # Create a connection timeout exception
            timeout_exception = OSError("Connection timed out")
            timeout_exception.errno = errno.ETIMEDOUT

            # Mixed scenario: connection timeout, then server timeout, then success
            mock_internal.side_effect = [
                timeout_exception,
                (400, "Your query request was running for too long."),
                (200, '{"updated": true}')
            ]

            status, data = http_client.send_authenticated_request_with_retry(
                "POST", "/services/data/v65.0/composite/batch", max_retries=3
            )

            assert status == 200
            assert data == '{"updated": true}'
            assert mock_internal.call_count == 3

    def test_multiple_server_timeouts_then_success(self, http_client):
        """Test multiple server timeouts with different formats then success."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # Multiple server timeout formats, then success
            mock_internal.side_effect = [
                (400, "Your query request was running for too long."),
                (400, '[{"errorCode":"QUERY_TIMEOUT"}]'),
                (400, '[{"message":"Timeout","errorCode":"QUERY_TIMEOUT"}]'),
                (200, '{"completed": true}')
            ]

            status, data = http_client.send_authenticated_request_with_retry(
                "PATCH", "/services/data/v65.0/sobjects/Account/001", max_retries=4
            )

            assert status == 200
            assert data == '{"completed": true}'
            assert mock_internal.call_count == 4

    def test_mixed_timeouts_all_fail(self, http_client):
        """Test mixed timeout scenarios where all attempts fail."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # Create a connection timeout exception
            timeout_exception = OSError("Connection timed out")
            timeout_exception.errno = errno.ETIMEDOUT

            # Mixed timeouts that all fail
            mock_internal.side_effect = [
                (400, "Your query request was running for too long."),
                timeout_exception,
                (400, '[{"errorCode":"QUERY_TIMEOUT"}]')
            ]

            with pytest.raises(QueryTimeoutError, match="QUERY_TIMEOUT"):
                http_client.send_authenticated_request_with_retry(
                    "GET", "/services/data/v65.0/query", max_retries=2
                )

            # Should try initial + 2 retries = 3 total attempts
            assert mock_internal.call_count == 3

    @patch("sfq.http_client.logger")
    def test_mixed_timeout_comprehensive_logging(self, mock_logger, http_client):
        """Test comprehensive logging for mixed timeout scenarios."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # Create a connection timeout exception
            timeout_exception = OSError("Connection timed out")
            timeout_exception.errno = errno.ETIMEDOUT

            # Mixed scenario: server timeout, then connection timeout, then success
            mock_internal.side_effect = [
                (400, '[{"message":"Your query request was running for too long.","errorCode":"QUERY_TIMEOUT"}]'),
                timeout_exception,
                (200, '{"records": []}')
            ]

            status, data = http_client.send_authenticated_request_with_retry(
                "GET", "/services/data/v65.0/query", max_retries=3
            )

            assert status == 200

            # Verify debug logging for both retry attempts and success
            debug_calls = [call for call in mock_logger.debug.call_args_list]
            assert len(debug_calls) == 3

            # Check first retry (server timeout)
            first_retry = debug_calls[0]
            first_format = first_retry[0][0]
            first_args = first_retry[0][1:]
            assert "Timeout detected" in first_format
            assert "server" in first_args
            assert 1 in first_args  # attempt 1

            # Check second retry (connection timeout exception)
            second_retry = debug_calls[1]
            second_format = second_retry[0][0]
            second_args = second_retry[0][1:]
            assert "Timeout exception" in second_format
            assert "connection" in second_args
            assert 2 in second_args  # attempt 2

            # Check success log
            success_log = debug_calls[2]
            success_format = success_log[0][0]
            success_args = success_log[0][1:]
            assert "Request succeeded on retry attempt" in success_format
            assert 3 in success_args  # attempt 3


class TestNonTimeoutErrorHandling:
    """Test that non-timeout errors do not trigger retry logic."""

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
        return auth_manager

    @pytest.fixture
    def http_client(self, auth_manager):
        """Create HTTPClient instance for testing."""
        return HTTPClient(
            auth_manager=auth_manager,
            user_agent="test-agent/1.0",
            sforce_client="test-client",
        )

    def test_non_timeout_400_error_no_retry(self, http_client):
        """Test that non-timeout 400 errors do not trigger retry logic."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # Return a 400 error that is NOT a timeout
            mock_internal.return_value = (400, '{"error": "INVALID_QUERY", "message": "Invalid syntax"}')

            status, data = http_client.send_authenticated_request_with_retry(
                "GET", "/services/data/v65.0/query", max_retries=3
            )

            assert status == 400
            assert data == '{"error": "INVALID_QUERY", "message": "Invalid syntax"}'
            # Should only be called once (no retries)
            assert mock_internal.call_count == 1

    def test_500_error_no_retry(self, http_client):
        """Test that 500 errors do not trigger retry logic."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # Return a 500 error
            mock_internal.return_value = (500, "Internal Server Error")

            status, data = http_client.send_authenticated_request_with_retry(
                "POST", "/services/data/v65.0/composite", max_retries=3
            )

            assert status == 500
            assert data == "Internal Server Error"
            # Should only be called once (no retries)
            assert mock_internal.call_count == 1

    def test_401_unauthorized_error_no_retry(self, http_client):
        """Test that 401 unauthorized errors do not trigger retry logic."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # Return a 401 error
            mock_internal.return_value = (401, '{"error": "INVALID_SESSION_ID"}')

            status, data = http_client.send_authenticated_request_with_retry(
                "GET", "/services/data/v65.0/query", max_retries=3
            )

            assert status == 401
            assert data == '{"error": "INVALID_SESSION_ID"}'
            # Should only be called once (no retries)
            assert mock_internal.call_count == 1

    def test_non_timeout_exception_no_retry(self, http_client):
        """Test that non-timeout exceptions do not trigger retry logic."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # Create a non-timeout exception
            non_timeout_exception = ValueError("Invalid parameter")

            mock_internal.side_effect = non_timeout_exception

            with pytest.raises(ValueError, match="Invalid parameter"):
                http_client.send_authenticated_request_with_retry(
                    "GET", "/services/data/v65.0/query", max_retries=3
                )

            # Should only be called once (no retries)
            assert mock_internal.call_count == 1

    def test_connection_error_wrong_errno_no_retry(self, http_client):
        """Test that connection errors with wrong errno do not trigger retry logic."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # Create a connection error with wrong errno
            connection_exception = OSError("Connection refused")
            connection_exception.errno = errno.ECONNREFUSED  # Different errno

            mock_internal.side_effect = connection_exception

            with pytest.raises(OSError, match="Connection refused"):
                http_client.send_authenticated_request_with_retry(
                    "GET", "/services/data/v65.0/query", max_retries=3
                )

            # Should only be called once (no retries)
            assert mock_internal.call_count == 1

    def test_successful_request_no_retry_overhead(self, http_client):
        """Test that successful requests have no retry overhead."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            mock_internal.return_value = (200, '{"records": []}')

            status, data = http_client.send_authenticated_request_with_retry(
                "GET", "/services/data/v65.0/query", max_retries=3
            )

            assert status == 200
            assert data == '{"records": []}'
            # Should only be called once (no retries needed)
            assert mock_internal.call_count == 1

    @patch("sfq.http_client.logger")
    def test_non_timeout_error_logging(self, mock_logger, http_client):
        """Test logging behavior for non-timeout errors."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # Create a non-timeout exception
            non_timeout_exception = ValueError("Invalid parameter")

            mock_internal.side_effect = non_timeout_exception

            with pytest.raises(ValueError, match="Invalid parameter"):
                http_client.send_authenticated_request_with_retry(
                    "GET", "/services/data/v65.0/query", max_retries=3
                )

            # Verify debug logging for non-timeout exception
            debug_calls = [call for call in mock_logger.debug.call_args_list]
            assert len(debug_calls) == 1

            non_timeout_log = debug_calls[0]
            non_timeout_format = non_timeout_log[0][0]
            non_timeout_args = non_timeout_log[0][1:]
            
            assert "Non-timeout exception" in non_timeout_format
            assert "not retrying" in non_timeout_format
            assert 1 in non_timeout_args  # attempt number
            assert "ValueError" in non_timeout_args  # exception type


class TestQueryClientIntegration:
    """Integration tests with QueryClient to verify end-to-end functionality."""

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
        return auth_manager

    @pytest.fixture
    def http_client(self, auth_manager):
        """Create HTTPClient instance for testing."""
        return HTTPClient(
            auth_manager=auth_manager,
            user_agent="test-agent/1.0",
            sforce_client="test-client",
        )

    @pytest.fixture
    def query_client(self, http_client):
        """Create QueryClient instance for testing."""
        return QueryClient(http_client, api_version="v65.0")

    def test_standard_query_with_server_timeout_retry_success(self, query_client, http_client):
        """Test standard SOQL query with server timeout that succeeds on retry."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # First call returns server timeout, second call succeeds
            mock_internal.side_effect = [
                (400, "Your query request was running for too long."),
                (200, json.dumps({
                    "totalSize": 2,
                    "done": True,
                    "records": [
                        {"Id": "001000000000001", "Name": "Test Account 1"},
                        {"Id": "001000000000002", "Name": "Test Account 2"}
                    ]
                }))
            ]

            result = query_client.query("SELECT Id, Name FROM Account LIMIT 2")

            assert result is not None
            assert result["totalSize"] == 2
            assert len(result["records"]) == 2
            assert result["records"][0]["Name"] == "Test Account 1"
            assert mock_internal.call_count == 2

    def test_tooling_query_with_connection_timeout_retry_success(self, query_client, http_client):
        """Test tooling API query with connection timeout that succeeds on retry."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # Create a connection timeout exception
            timeout_exception = OSError("Connection timed out")
            timeout_exception.errno = errno.ETIMEDOUT

            # First call raises timeout exception, second call succeeds
            mock_internal.side_effect = [
                timeout_exception,
                (200, json.dumps({
                    "totalSize": 1,
                    "done": True,
                    "records": [{"Id": "01p000000000001", "Name": "Test Class"}]
                }))
            ]

            result = query_client.tooling_query("SELECT Id, Name FROM ApexClass LIMIT 1")

            assert result is not None
            assert result["totalSize"] == 1
            assert result["records"][0]["Name"] == "Test Class"
            assert mock_internal.call_count == 2

    def test_composite_query_with_mixed_timeout_scenarios(self, query_client, http_client):
        """Test composite query operations with mixed timeout scenarios."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # Create a connection timeout exception
            timeout_exception = OSError("Connection timed out")
            timeout_exception.errno = errno.ETIMEDOUT

            # Mixed scenario: server timeout, then connection timeout, then success
            mock_internal.side_effect = [
                (400, '[{"message":"Your query request was running for too long.","errorCode":"QUERY_TIMEOUT"}]'),
                timeout_exception,
                (200, json.dumps({
                    "results": [
                        {
                            "statusCode": 200,
                            "result": {
                                "totalSize": 2,
                                "done": True,
                                "records": [
                                    {"Id": "001000000000001", "Name": "Test Account 1"},
                                    {"Id": "001000000000002", "Name": "Test Account 2"}
                                ]
                            }
                        },
                        {
                            "statusCode": 200,
                            "result": {
                                "totalSize": 1,
                                "done": True,
                                "records": [{"Id": "003000000000001", "Name": "Test Contact 1"}]
                            }
                        }
                    ]
                }))
            ]

            query_dict = {
                "accounts": "SELECT Id, Name FROM Account LIMIT 2",
                "contacts": "SELECT Id, Name FROM Contact LIMIT 1"
            }

            result = query_client.cquery(query_dict)

            assert result is not None
            assert "accounts" in result
            assert "contacts" in result
            assert len(result["accounts"]["records"]) == 2
            assert len(result["contacts"]["records"]) == 1
            assert mock_internal.call_count == 3

    def test_query_with_timeout_all_retries_fail(self, query_client, http_client):
        """Test query operation where all timeout retries fail."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # All calls return server timeout
            mock_internal.return_value = (
                400, 
                "Your query request was running for too long."
            )

            result = query_client.query("SELECT Id FROM Account")

            # QueryClient should handle the QueryTimeoutError and return None
            assert result is None
            # Should try initial + 3 retries = 4 total attempts (default max_retries)
            assert mock_internal.call_count == 4

    def test_sobject_prefixes_with_server_timeout_retry_success(self, query_client, http_client):
        """Test sObject prefixes retrieval with server timeout that succeeds on retry."""
        with patch.object(http_client, '_send_authenticated_request_internal') as mock_internal:
            # First call returns server timeout, second call succeeds
            mock_internal.side_effect = [
                (400, '[{"errorCode":"QUERY_TIMEOUT"}]'),
                (200, json.dumps({
                    "sobjects": [
                        {"name": "Account", "keyPrefix": "001"},
                        {"name": "Contact", "keyPrefix": "003"},
                        {"name": "Opportunity", "keyPrefix": "006"}
                    ]
                }))
            ]

            result = query_client.get_sobject_prefixes(key_type="id")

            assert result is not None
            assert result["001"] == "Account"
            assert result["003"] == "Contact"
            assert result["006"] == "Opportunity"
            assert mock_internal.call_count == 2

    def test_query_pagination_with_timeout_on_next_page(self, query_client, http_client):
        """Test query pagination where timeout occurs on next page request."""
        with patch.object(http_client, 'send_authenticated_request') as mock_auth_request:
            # Initial query succeeds
            mock_auth_request.return_value = (200, json.dumps({
                "totalSize": 4,
                "done": False,
                "nextRecordsUrl": "/services/data/v65.0/query/01gXX0000000001-2000",
                "records": [
                    {"Id": "001000000000001", "Name": "Test Account 1"},
                    {"Id": "001000000000002", "Name": "Test Account 2"}
                ]
            }))

            with patch.object(http_client, 'send_request') as mock_send_request:
                # Pagination call fails with non-200 status
                mock_send_request.return_value = (500, "Server Error")

                result = query_client.query("SELECT Id, Name FROM Account")

                # Note: The current pagination implementation in QueryClient doesn't use retry logic
                # This test documents the current behavior - pagination failures return partial results
                assert result is not None
                assert len(result["records"]) == 2  # Only initial page
                assert result["done"] is False  # Pagination didn't complete due to error
                assert mock_auth_request.call_count == 1
                assert mock_send_request.call_count == 1

    def test_end_to_end_timeout_detection_and_retry(self, query_client):
        """Test end-to-end timeout detection and retry functionality."""
        # Test that TimeoutDetector correctly identifies various timeout scenarios
        # and that the retry mechanism works properly
        
        # Server timeout scenarios
        assert TimeoutDetector.is_server_timeout(400, "Your query request was running for too long.") is True
        assert TimeoutDetector.is_server_timeout(400, '[{"errorCode":"QUERY_TIMEOUT"}]') is True
        assert TimeoutDetector.is_server_timeout(400, "Invalid query syntax") is False
        assert TimeoutDetector.is_server_timeout(500, "Your query request was running for too long.") is False

        # Connection timeout scenarios
        timeout_exception = OSError("Connection timed out")
        timeout_exception.errno = errno.ETIMEDOUT
        
        assert TimeoutDetector.is_connection_timeout(None, None, timeout_exception) is True
        assert TimeoutDetector.is_connection_timeout(400, None, timeout_exception) is False
        assert TimeoutDetector.is_connection_timeout(None, "error", timeout_exception) is False

        # Unified timeout detection
        assert TimeoutDetector.is_timeout_error(400, "Your query request was running for too long.") is True
        assert TimeoutDetector.is_timeout_error(None, None, timeout_exception) is True
        assert TimeoutDetector.is_timeout_error(500, "Internal Server Error") is False

        # Timeout type detection
        assert TimeoutDetector.get_timeout_type(400, "Your query request was running for too long.") == "server"
        assert TimeoutDetector.get_timeout_type(None, None, timeout_exception) == "connection"
        assert TimeoutDetector.get_timeout_type(500, "Internal Server Error") is None