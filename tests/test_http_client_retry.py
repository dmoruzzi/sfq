"""
Unit tests for HTTPClient retry functionality.

Tests the timeout retry logic with mocked timeout responses and various
timeout scenarios including server timeouts and connection timeouts.
"""

import errno
from unittest.mock import Mock, patch

import pytest

from sfq.auth import AuthManager
from sfq.exceptions import QueryTimeoutError
from sfq.http_client import HTTPClient


class TestHTTPClientRetry:
    """Test cases for HTTPClient retry functionality."""

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

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    def test_retry_server_timeout_success_on_second_attempt(self, mock_internal, http_client):
        """Test retry logic with server timeout that succeeds on second attempt."""
        # First call returns server timeout, second call succeeds
        mock_internal.side_effect = [
            (400, '[{"message":"Your query request was running for too long.","errorCode":"QUERY_TIMEOUT"}]'),
            (200, '{"records": []}')
        ]

        status, data = http_client.send_authenticated_request_with_retry(
            "GET", "/services/data/v65.0/query", max_retries=3
        )

        assert status == 200
        assert data == '{"records": []}'
        assert mock_internal.call_count == 2

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    def test_retry_server_timeout_all_attempts_fail(self, mock_internal, http_client):
        """Test retry logic with server timeout that fails on all attempts."""
        # All calls return server timeout
        mock_internal.return_value = (
            400, 
            '[{"message":"Your query request was running for too long.","errorCode":"QUERY_TIMEOUT"}]'
        )

        with pytest.raises(QueryTimeoutError, match="QUERY_TIMEOUT"):
            http_client.send_authenticated_request_with_retry(
                "GET", "/services/data/v65.0/query", max_retries=3
            )

        # Should try initial + 3 retries = 4 total attempts
        assert mock_internal.call_count == 4

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    def test_retry_connection_timeout_with_exception(self, mock_internal, http_client):
        """Test retry logic with connection timeout exception."""
        # Create a connection timeout exception
        timeout_exception = OSError("Connection timed out")
        timeout_exception.errno = errno.ETIMEDOUT

        # First call raises timeout exception, second call succeeds
        mock_internal.side_effect = [
            timeout_exception,
            (200, '{"records": []}')
        ]

        status, data = http_client.send_authenticated_request_with_retry(
            "POST", "/services/data/v65.0/composite", max_retries=3
        )

        assert status == 200
        assert data == '{"records": []}'
        assert mock_internal.call_count == 2

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    def test_retry_connection_timeout_all_attempts_fail(self, mock_internal, http_client):
        """Test retry logic with connection timeout that fails on all attempts."""
        # Create a connection timeout exception
        timeout_exception = OSError("Connection timed out")
        timeout_exception.errno = errno.ETIMEDOUT

        # All calls raise timeout exception
        mock_internal.side_effect = timeout_exception

        with pytest.raises(QueryTimeoutError, match="QUERY_TIMEOUT"):
            http_client.send_authenticated_request_with_retry(
                "GET", "/services/data/v65.0/query", max_retries=3
            )

        # Should try initial + 3 retries = 4 total attempts
        assert mock_internal.call_count == 4

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    def test_retry_mixed_timeout_scenarios(self, mock_internal, http_client):
        """Test retry logic with mixed timeout scenarios."""
        # Create a connection timeout exception
        timeout_exception = OSError("Connection timed out")
        timeout_exception.errno = errno.ETIMEDOUT

        # First: server timeout, Second: connection timeout, Third: success
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

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    def test_no_retry_for_non_timeout_errors(self, mock_internal, http_client):
        """Test that non-timeout errors do not trigger retry logic."""
        # Return a 400 error that is NOT a timeout
        mock_internal.return_value = (400, '{"error": "INVALID_QUERY"}')

        status, data = http_client.send_authenticated_request_with_retry(
            "GET", "/services/data/v65.0/query", max_retries=3
        )

        assert status == 400
        assert data == '{"error": "INVALID_QUERY"}'
        # Should only be called once (no retries)
        assert mock_internal.call_count == 1

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    def test_no_retry_for_non_timeout_exceptions(self, mock_internal, http_client):
        """Test that non-timeout exceptions do not trigger retry logic."""
        # Create a non-timeout exception
        non_timeout_exception = ValueError("Invalid parameter")

        mock_internal.side_effect = non_timeout_exception

        with pytest.raises(ValueError, match="Invalid parameter"):
            http_client.send_authenticated_request_with_retry(
                "GET", "/services/data/v65.0/query", max_retries=3
            )

        # Should only be called once (no retries)
        assert mock_internal.call_count == 1

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    def test_no_retry_for_successful_requests(self, mock_internal, http_client):
        """Test that successful requests have no retry overhead."""
        mock_internal.return_value = (200, '{"records": []}')

        status, data = http_client.send_authenticated_request_with_retry(
            "GET", "/services/data/v65.0/query", max_retries=3
        )

        assert status == 200
        assert data == '{"records": []}'
        # Should only be called once (no retries needed)
        assert mock_internal.call_count == 1

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    def test_retry_preserves_request_parameters(self, mock_internal, http_client):
        """Test that retry attempts preserve original request parameters."""
        # First call returns server timeout, second call succeeds
        mock_internal.side_effect = [
            (400, '[{"message":"Your query request was running for too long.","errorCode":"QUERY_TIMEOUT"}]'),
            (200, '{"records": []}')
        ]

        method = "POST"
        endpoint = "/services/data/v65.0/composite"
        body = '{"compositeRequest": []}'
        additional_headers = {"Custom-Header": "test-value"}

        status, data = http_client.send_authenticated_request_with_retry(
            method, endpoint, body, additional_headers, max_retries=3
        )

        assert status == 200
        assert data == '{"records": []}'
        assert mock_internal.call_count == 2

        # Verify both calls had the same parameters
        first_call = mock_internal.call_args_list[0]
        second_call = mock_internal.call_args_list[1]

        assert first_call == second_call
        assert first_call[0] == (method, endpoint, body, additional_headers)

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    def test_retry_with_custom_max_retries(self, mock_internal, http_client):
        """Test retry logic with custom max_retries parameter."""
        # All calls return server timeout
        mock_internal.return_value = (
            400, 
            '[{"message":"Your query request was running for too long.","errorCode":"QUERY_TIMEOUT"}]'
        )

        with pytest.raises(QueryTimeoutError, match="QUERY_TIMEOUT"):
            http_client.send_authenticated_request_with_retry(
                "GET", "/services/data/v65.0/query", max_retries=1
            )

        # Should try initial + 1 retry = 2 total attempts
        assert mock_internal.call_count == 2

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    def test_retry_with_zero_max_retries(self, mock_internal, http_client):
        """Test retry logic with zero max_retries (no retries)."""
        # Return server timeout
        mock_internal.return_value = (
            400, 
            '[{"message":"Your query request was running for too long.","errorCode":"QUERY_TIMEOUT"}]'
        )

        with pytest.raises(QueryTimeoutError, match="QUERY_TIMEOUT"):
            http_client.send_authenticated_request_with_retry(
                "GET", "/services/data/v65.0/query", max_retries=0
            )

        # Should only try once (no retries)
        assert mock_internal.call_count == 1

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    def test_send_authenticated_request_uses_retry_wrapper(self, mock_internal, http_client):
        """Test that send_authenticated_request uses the retry wrapper by default."""
        mock_internal.return_value = (200, '{"records": []}')

        status, data = http_client.send_authenticated_request(
            "GET", "/services/data/v65.0/query"
        )

        assert status == 200
        assert data == '{"records": []}'
        assert mock_internal.call_count == 1

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    def test_send_authenticated_request_with_custom_max_retries(self, mock_internal, http_client):
        """Test that send_authenticated_request accepts max_retries parameter."""
        # All calls return server timeout
        mock_internal.return_value = (
            400, 
            '[{"message":"Your query request was running for too long.","errorCode":"QUERY_TIMEOUT"}]'
        )

        with pytest.raises(QueryTimeoutError, match="QUERY_TIMEOUT"):
            http_client.send_authenticated_request(
                "GET", "/services/data/v65.0/query", max_retries=2
            )

        # Should try initial + 2 retries = 3 total attempts
        assert mock_internal.call_count == 3

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    def test_connection_timeout_with_nested_exception(self, mock_internal, http_client):
        """Test connection timeout detection with nested exception structure."""
        # Create a nested timeout exception (common in urllib/http.client)
        inner_exception = OSError("Connection timed out")
        inner_exception.errno = errno.ETIMEDOUT
        
        outer_exception = Exception("Request failed")
        outer_exception.__cause__ = inner_exception

        # First call raises nested timeout exception, second call succeeds
        mock_internal.side_effect = [
            outer_exception,
            (200, '{"records": []}')
        ]

        status, data = http_client.send_authenticated_request_with_retry(
            "GET", "/services/data/v65.0/query", max_retries=3
        )

        assert status == 200
        assert data == '{"records": []}'
        assert mock_internal.call_count == 2

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    @patch("sfq.http_client.logger")
    def test_retry_logging_behavior(self, mock_logger, mock_internal, http_client):
        """Test that retry attempts are logged appropriately."""
        # First call returns server timeout, second call succeeds
        mock_internal.side_effect = [
            (400, '[{"message":"Your query request was running for too long.","errorCode":"QUERY_TIMEOUT"}]'),
            (200, '{"records": []}')
        ]

        status, data = http_client.send_authenticated_request_with_retry(
            "GET", "/services/data/v65.0/query", max_retries=3
        )

        assert status == 200
        assert data == '{"records": []}'

        # Verify logging calls
        debug_calls = [call for call in mock_logger.debug.call_args_list]
        assert len(debug_calls) == 2  # One for retry attempt, one for success

        # Check retry attempt log - verify the format string and arguments
        retry_call = debug_calls[0]
        retry_format = retry_call[0][0]
        retry_args = retry_call[0][1:]
        
        assert "Timeout detected" in retry_format
        assert "timeout) on attempt" in retry_format
        assert "retrying" in retry_format
        assert "server" in retry_args  # timeout_type should be 'server'

        # Check success log
        success_call = debug_calls[1]
        success_format = success_call[0][0]
        assert "Request succeeded on retry attempt" in success_format

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    @patch("sfq.http_client.logger")
    def test_retry_failure_logging(self, mock_logger, mock_internal, http_client):
        """Test that final retry failures are logged appropriately."""
        # All calls return server timeout
        mock_internal.return_value = (
            400, 
            '[{"message":"Your query request was running for too long.","errorCode":"QUERY_TIMEOUT"}]'
        )

        with pytest.raises(QueryTimeoutError, match="QUERY_TIMEOUT"):
            http_client.send_authenticated_request_with_retry(
                "GET", "/services/data/v65.0/query", max_retries=2
            )

        # Verify error logging
        error_calls = [call for call in mock_logger.error.call_args_list]
        assert len(error_calls) == 1

        error_call = error_calls[0]
        error_format = error_call[0][0]
        error_args = error_call[0][1:]
        
        assert "retry attempts failed" in error_format
        assert "timeout errors" in error_format
        assert 3 in error_args  # max_retries + 1 = 3 total attempts

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    @patch("sfq.http_client.logger")
    def test_comprehensive_logging_server_timeout_retry_success(self, mock_logger, mock_internal, http_client):
        """Test comprehensive logging for server timeout with successful retry."""
        # First call returns server timeout with realistic response format, second call succeeds
        mock_internal.side_effect = [
            (400, '[{"message":"Your query request was running for too long.","errorCode":"QUERY_TIMEOUT"}]'),
            (200, '{"records": [{"Id": "001"}]}')
        ]

        status, data = http_client.send_authenticated_request_with_retry(
            "POST", "/services/data/v65.0/composite", max_retries=3
        )

        assert status == 200
        assert data == '{"records": [{"Id": "001"}]}'

        # Verify trace logging for initial request
        trace_calls = [call for call in mock_logger.trace.call_args_list]
        assert len(trace_calls) >= 1
        
        initial_trace = trace_calls[0]
        assert "Starting request with retry capability" in initial_trace[0][0]
        assert "POST /services/data/v65.0/composite" in initial_trace[0][1]
        assert 3 == initial_trace[0][2]  # max_retries

        # Verify debug logging for retry attempt
        debug_calls = [call for call in mock_logger.debug.call_args_list]
        assert len(debug_calls) == 2

        # Check retry initiation log with detailed context
        retry_log = debug_calls[0]
        retry_format = retry_log[0][0]
        retry_args = retry_log[0][1:]
        
        assert "Timeout detected" in retry_format
        assert "(%s timeout)" in retry_format  # Format string placeholder
        assert "attempt %d/%d" in retry_format  # Format string placeholder
        assert "status_code=%s" in retry_format  # Format string placeholder
        assert "retrying" in retry_format
        assert "server" in retry_args  # timeout_type should be 'server'
        assert 1 in retry_args  # attempt number
        assert 4 in retry_args  # total attempts
        assert "POST /services/data/v65.0/composite" in retry_args
        assert 400 in retry_args  # status code

        # Check successful retry recovery log
        success_log = debug_calls[1]
        success_format = success_log[0][0]
        success_args = success_log[0][1:]
        
        assert "Request succeeded on retry attempt" in success_format
        assert "recovered from timeout" in success_format
        assert "status_code=%s" in success_format  # Format string placeholder
        assert 2 in success_args  # attempt number
        assert 4 in success_args  # total attempts
        assert "POST /services/data/v65.0/composite" in success_args
        assert 200 in success_args  # status code

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    @patch("sfq.http_client.logger")
    def test_comprehensive_logging_connection_timeout_exception(self, mock_logger, mock_internal, http_client):
        """Test comprehensive logging for connection timeout exception scenarios."""
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
        assert data == '{"success": true}'

        # Verify debug logging for exception-based retry
        debug_calls = [call for call in mock_logger.debug.call_args_list]
        assert len(debug_calls) == 2

        # Check timeout exception retry log
        exception_retry_log = debug_calls[0]
        exception_format = exception_retry_log[0][0]
        exception_args = exception_retry_log[0][1:]
        
        assert "Timeout exception" in exception_format
        assert "(%s timeout)" in exception_format  # Format string placeholder
        assert "attempt %d/%d" in exception_format  # Format string placeholder
        assert "exception: %s" in exception_format  # Format string placeholder
        assert "retrying" in exception_format
        assert "connection" in exception_args  # timeout_type should be 'connection'
        assert 1 in exception_args  # attempt number
        assert 3 in exception_args  # total attempts
        assert "GET /services/data/v65.0/query" in exception_args
        assert "OSError" in exception_args  # exception type

        # Check successful retry recovery log
        success_log = debug_calls[1]
        success_format = success_log[0][0]
        assert "Request succeeded on retry attempt" in success_format
        assert "recovered from timeout" in success_format

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    @patch("sfq.http_client.logger")
    def test_comprehensive_logging_all_retries_fail_server_timeout(self, mock_logger, mock_internal, http_client):
        """Test comprehensive logging when all retry attempts fail with server timeout."""
        # All calls return server timeout
        mock_internal.return_value = (
            400, 
            '[{"message":"Your query request was running for too long.","errorCode":"QUERY_TIMEOUT"}]'
        )

        with pytest.raises(QueryTimeoutError, match="QUERY_TIMEOUT"):
            http_client.send_authenticated_request_with_retry(
                "PATCH", "/services/data/v65.0/sobjects/Account/001", max_retries=2
            )

        # Verify trace logging for initial request
        trace_calls = [call for call in mock_logger.trace.call_args_list]
        assert len(trace_calls) >= 1
        
        initial_trace = trace_calls[0]
        assert "Starting request with retry capability" in initial_trace[0][0]
        assert "PATCH /services/data/v65.0/sobjects/Account/001" in initial_trace[0][1]

        # Verify debug logging for retry attempts
        debug_calls = [call for call in mock_logger.debug.call_args_list]
        assert len(debug_calls) == 2  # Two retry attempts

        # Check first retry attempt
        first_retry = debug_calls[0]
        first_format = first_retry[0][0]
        first_args = first_retry[0][1:]
        assert "Timeout detected" in first_format
        assert "(%s timeout)" in first_format
        assert "attempt %d/%d" in first_format
        assert "server" in first_args
        assert 1 in first_args
        assert 3 in first_args

        # Check second retry attempt
        second_retry = debug_calls[1]
        second_format = second_retry[0][0]
        second_args = second_retry[0][1:]
        assert "Timeout detected" in second_format
        assert "(%s timeout)" in second_format
        assert "attempt %d/%d" in second_format
        assert "server" in second_args
        assert 2 in second_args
        assert 3 in second_args

        # Verify error logging before exception
        error_calls = [call for call in mock_logger.error.call_args_list]
        assert len(error_calls) == 1

        error_log = error_calls[0]
        error_format = error_log[0][0]
        error_args = error_log[0][1:]
        
        assert "All %d retry attempts failed" in error_format  # Format string placeholder
        assert "timeout errors" in error_format
        assert "final timeout type: %s" in error_format  # Format string placeholder
        assert "final status_code: %s" in error_format  # Format string placeholder
        assert 3 in error_args  # total attempts
        assert "PATCH /services/data/v65.0/sobjects/Account/001" in error_args
        assert "server" in error_args
        assert 400 in error_args

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    @patch("sfq.http_client.logger")
    def test_comprehensive_logging_all_retries_fail_connection_timeout(self, mock_logger, mock_internal, http_client):
        """Test comprehensive logging when all retry attempts fail with connection timeout."""
        # Create a connection timeout exception
        timeout_exception = OSError("Connection timed out")
        timeout_exception.errno = errno.ETIMEDOUT

        # All calls raise timeout exception
        mock_internal.side_effect = timeout_exception

        with pytest.raises(QueryTimeoutError, match="QUERY_TIMEOUT"):
            http_client.send_authenticated_request_with_retry(
                "DELETE", "/services/data/v65.0/sobjects/Account/001", max_retries=1
            )

        # Verify debug logging for retry attempts
        debug_calls = [call for call in mock_logger.debug.call_args_list]
        assert len(debug_calls) == 1  # One retry attempt

        retry_log = debug_calls[0]
        retry_format = retry_log[0][0]
        retry_args = retry_log[0][1:]
        assert "Timeout exception" in retry_format
        assert "(%s timeout)" in retry_format
        assert "attempt %d/%d" in retry_format
        assert "connection" in retry_args
        assert 1 in retry_args
        assert 2 in retry_args
        assert "OSError" in retry_args  # exception type

        # Verify error logging before exception
        error_calls = [call for call in mock_logger.error.call_args_list]
        assert len(error_calls) == 1

        error_log = error_calls[0]
        error_format = error_log[0][0]
        error_args = error_log[0][1:]
        
        assert "All %d retry attempts failed" in error_format  # Format string placeholder
        assert "timeout errors" in error_format
        assert "final timeout type: %s" in error_format  # Format string placeholder
        assert "final exception: %s" in error_format  # Format string placeholder
        assert 2 in error_args  # total attempts
        assert "DELETE /services/data/v65.0/sobjects/Account/001" in error_args
        assert "connection" in error_args
        assert "OSError" in error_args

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    @patch("sfq.http_client.logger")
    def test_comprehensive_logging_mixed_timeout_scenarios(self, mock_logger, mock_internal, http_client):
        """Test comprehensive logging for mixed timeout scenarios."""
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

        # Verify debug logging for both retry attempts and success
        debug_calls = [call for call in mock_logger.debug.call_args_list]
        assert len(debug_calls) == 3

        # Check first retry (server timeout)
        first_retry = debug_calls[0]
        first_format = first_retry[0][0]
        first_args = first_retry[0][1:]
        assert "Timeout detected" in first_format
        assert "(%s timeout)" in first_format
        assert "attempt %d/%d" in first_format
        assert "server" in first_args
        assert 1 in first_args
        assert 4 in first_args

        # Check second retry (connection timeout exception)
        second_retry = debug_calls[1]
        second_format = second_retry[0][0]
        second_args = second_retry[0][1:]
        assert "Timeout exception" in second_format
        assert "(%s timeout)" in second_format
        assert "attempt %d/%d" in second_format
        assert "connection" in second_args
        assert 2 in second_args
        assert 4 in second_args

        # Check success log
        success_log = debug_calls[2]
        success_format = success_log[0][0]
        success_args = success_log[0][1:]
        assert "Request succeeded on retry attempt" in success_format
        assert "%d/%d" in success_format
        assert 3 in success_args  # attempt 3
        assert 4 in success_args  # total 4

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    @patch("sfq.http_client.logger")
    def test_comprehensive_logging_non_timeout_error_no_retry(self, mock_logger, mock_internal, http_client):
        """Test comprehensive logging for non-timeout errors that should not retry."""
        # Create a non-timeout exception
        non_timeout_exception = ValueError("Invalid parameter")

        mock_internal.side_effect = non_timeout_exception

        with pytest.raises(ValueError, match="Invalid parameter"):
            http_client.send_authenticated_request_with_retry(
                "GET", "/services/data/v65.0/query", max_retries=3
            )

        # Verify trace logging for initial request
        trace_calls = [call for call in mock_logger.trace.call_args_list]
        assert len(trace_calls) >= 1

        # Verify debug logging for non-timeout exception
        debug_calls = [call for call in mock_logger.debug.call_args_list]
        assert len(debug_calls) == 1

        non_timeout_log = debug_calls[0]
        non_timeout_format = non_timeout_log[0][0]
        non_timeout_args = non_timeout_log[0][1:]
        
        assert "Non-timeout exception" in non_timeout_format
        assert "attempt %d" in non_timeout_format  # Format string placeholder
        assert "not retrying" in non_timeout_format
        assert 1 in non_timeout_args  # attempt number
        assert "GET /services/data/v65.0/query" in non_timeout_args
        assert "ValueError" in non_timeout_args  # exception type

        # Should not have any error logs (since we're not retrying)
        error_calls = [call for call in mock_logger.error.call_args_list]
        assert len(error_calls) == 0

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    @patch("sfq.http_client.logger")
    def test_comprehensive_logging_successful_first_attempt(self, mock_logger, mock_internal, http_client):
        """Test comprehensive logging for successful first attempt (no retries needed)."""
        mock_internal.return_value = (200, '{"records": []}')

        status, data = http_client.send_authenticated_request_with_retry(
            "GET", "/services/data/v65.0/query", max_retries=3
        )

        assert status == 200
        assert data == '{"records": []}'

        # Verify trace logging for initial request and success
        trace_calls = [call for call in mock_logger.trace.call_args_list]
        assert len(trace_calls) >= 2

        # Check initial request trace
        initial_trace = trace_calls[0]
        assert "Starting request with retry capability" in initial_trace[0][0]

        # Check successful first attempt trace
        success_trace = trace_calls[1]
        success_trace_format = success_trace[0][0]
        success_trace_args = success_trace[0][1:]
        assert "Request succeeded on first attempt" in success_trace_format
        assert "status_code=%s" in success_trace_format  # Format string placeholder
        assert 200 in success_trace_args  # status code value

        # Should not have any debug or error logs for successful first attempt
        debug_calls = [call for call in mock_logger.debug.call_args_list]
        assert len(debug_calls) == 0

        error_calls = [call for call in mock_logger.error.call_args_list]
        assert len(error_calls) == 0

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    @patch("sfq.http_client.logger")
    def test_comprehensive_logging_request_context_preservation(self, mock_logger, mock_internal, http_client):
        """Test that request context is preserved in all log messages."""
        # Server timeout followed by success
        mock_internal.side_effect = [
            (400, '[{"message":"Your query request was running for too long.","errorCode":"QUERY_TIMEOUT"}]'),
            (200, '{"records": []}')
        ]

        status, data = http_client.send_authenticated_request_with_retry(
            "POST", "/services/data/v65.0/composite/batch", 
            body='{"batchRequests": []}',
            additional_headers={"Custom-Header": "test"},
            max_retries=2
        )

        assert status == 200

        # Verify that all log messages contain the request context
        expected_context = "POST /services/data/v65.0/composite/batch"

        # Check trace logs
        trace_calls = [call for call in mock_logger.trace.call_args_list]
        for trace_call in trace_calls:
            log_args = trace_call[0][1:]
            assert any(expected_context in str(arg) for arg in log_args)

        # Check debug logs
        debug_calls = [call for call in mock_logger.debug.call_args_list]
        for debug_call in debug_calls:
            log_args = debug_call[0][1:]
            assert any(expected_context in str(arg) for arg in log_args)

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    @patch("sfq.http_client.logger")
    def test_comprehensive_logging_retry_attempt_numbers(self, mock_logger, mock_internal, http_client):
        """Test that retry attempt numbers are correctly logged."""
        # All calls return server timeout
        mock_internal.return_value = (
            400, 
            '[{"message":"Your query request was running for too long.","errorCode":"QUERY_TIMEOUT"}]'
        )

        with pytest.raises(QueryTimeoutError, match="QUERY_TIMEOUT"):
            http_client.send_authenticated_request_with_retry(
                "GET", "/services/data/v65.0/query", max_retries=3
            )

        # Verify debug logging shows correct attempt numbers
        debug_calls = [call for call in mock_logger.debug.call_args_list]
        assert len(debug_calls) == 3  # Three retry attempts

        # Check attempt numbers in logs
        for i, debug_call in enumerate(debug_calls):
            log_format = debug_call[0][0]
            log_args = debug_call[0][1:]
            
            expected_attempt = i + 1  # attempts are 1-indexed
            expected_total = 4  # max_retries + 1
            
            assert "attempt %d/%d" in log_format  # Format string placeholder
            assert expected_attempt in log_args
            assert expected_total in log_args


class TestHTTPClientRetryIntegration:
    """Integration tests for HTTPClient retry functionality."""

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

    @patch("sfq.http_client.HTTPClient.send_request")
    def test_end_to_end_server_timeout_retry(self, mock_send_request, http_client):
        """Test end-to-end server timeout retry through all layers."""
        # First call returns server timeout, second call succeeds
        mock_send_request.side_effect = [
            (400, '[{"message":"Your query request was running for too long.","errorCode":"QUERY_TIMEOUT"}]'),
            (200, '{"records": [{"Id": "001000000000001"}]}')
        ]

        status, data = http_client.send_authenticated_request(
            "GET", "/services/data/v65.0/query?q=SELECT+Id+FROM+Account"
        )

        assert status == 200
        assert '"Id": "001000000000001"' in data
        assert mock_send_request.call_count == 2

        # Verify both calls used the same headers and parameters
        first_call = mock_send_request.call_args_list[0]
        second_call = mock_send_request.call_args_list[1]
        
        # Method and endpoint should be the same
        assert first_call[0][0] == second_call[0][0]  # method
        assert first_call[0][1] == second_call[0][1]  # endpoint
        
        # Headers should be the same (including auth)
        first_headers = first_call[0][2]
        second_headers = second_call[0][2]
        assert first_headers == second_headers
        assert "Authorization" in first_headers

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    def test_end_to_end_connection_timeout_retry(self, mock_internal, http_client):
        """Test end-to-end connection timeout retry through all layers."""
        # Create a connection timeout exception
        timeout_exception = OSError("Connection timed out")
        timeout_exception.errno = errno.ETIMEDOUT

        # First call raises connection timeout exception, second call succeeds
        mock_internal.side_effect = [
            timeout_exception,
            (200, '{"records": []}')
        ]

        status, data = http_client.send_authenticated_request(
            "POST", "/services/data/v65.0/composite/batch"
        )

        assert status == 200
        assert data == '{"records": []}'
        assert mock_internal.call_count == 2

    @patch("sfq.http_client.HTTPClient.send_request")
    def test_backward_compatibility_with_existing_code(self, mock_send_request, http_client):
        """Test that existing code using send_authenticated_request still works."""
        mock_send_request.return_value = (200, '{"success": true}')

        # Test with all parameter combinations that existing code might use
        
        # Basic call
        status, data = http_client.send_authenticated_request("GET", "/test")
        assert status == 200
        
        # With body
        status, data = http_client.send_authenticated_request(
            "POST", "/test", body='{"data": "test"}'
        )
        assert status == 200
        
        # With additional headers
        status, data = http_client.send_authenticated_request(
            "GET", "/test", additional_headers={"Custom": "header"}
        )
        assert status == 200
        
        # With all parameters
        status, data = http_client.send_authenticated_request(
            "PATCH", "/test", body='{"update": true}', 
            additional_headers={"Content-Type": "application/json"}
        )
        assert status == 200

        # All calls should have succeeded without any retry logic being triggered
        assert mock_send_request.call_count == 4

    @patch("sfq.http_client.HTTPClient.send_request")
    def test_performance_no_overhead_for_successful_requests(self, mock_send_request, http_client):
        """Test that successful requests have no performance overhead from retry mechanism."""
        import time
        
        mock_send_request.return_value = (200, '{"records": []}')

        # Time a successful request
        start_time = time.perf_counter()
        status, data = http_client.send_authenticated_request(
            "GET", "/services/data/v65.0/query"
        )
        end_time = time.perf_counter()

        assert status == 200
        assert data == '{"records": []}'
        
        # Should only be called once (no retry overhead)
        assert mock_send_request.call_count == 1
        
        # The request should complete very quickly (no retry delays)
        # This is more of a sanity check than a strict performance test
        elapsed_time = end_time - start_time
        assert elapsed_time < 0.1  # Should complete in less than 100ms

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    def test_method_signature_backward_compatibility(self, mock_internal, http_client):
        """Test that the send_authenticated_request method signature is backward compatible."""
        mock_internal.return_value = (200, '{"success": true}')

        # Test all the ways the method could be called in existing code
        
        # Positional arguments only
        status, data = http_client.send_authenticated_request("GET", "/test")
        assert status == 200
        
        # With body as positional
        status, data = http_client.send_authenticated_request("POST", "/test", '{"data": "test"}')
        assert status == 200
        
        # With body as keyword
        status, data = http_client.send_authenticated_request("POST", "/test", body='{"data": "test"}')
        assert status == 200
        
        # With additional_headers as keyword
        status, data = http_client.send_authenticated_request(
            "GET", "/test", additional_headers={"Custom": "header"}
        )
        assert status == 200
        
        # With all parameters as keywords
        status, data = http_client.send_authenticated_request(
            method="PATCH", 
            endpoint="/test", 
            body='{"update": true}', 
            additional_headers={"Content-Type": "application/json"}
        )
        assert status == 200
        
        # With new max_retries parameter
        status, data = http_client.send_authenticated_request(
            "GET", "/test", max_retries=5
        )
        assert status == 200
        
        # All calls should have succeeded
        assert mock_internal.call_count == 6

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    def test_default_max_retries_value(self, mock_internal, http_client):
        """Test that the default max_retries value is 3."""
        # All calls return server timeout
        mock_internal.return_value = (
            400, 
            '[{"message":"Your query request was running for too long.","errorCode":"QUERY_TIMEOUT"}]'
        )

        with pytest.raises(QueryTimeoutError, match="QUERY_TIMEOUT"):
            # Don't specify max_retries, should use default of 3
            http_client.send_authenticated_request(
                "GET", "/services/data/v65.0/query"
            )

        # Should try initial + 3 retries = 4 total attempts (default behavior)
        assert mock_internal.call_count == 4