"""
Unit tests for the timeout detection module.

These tests verify that the TimeoutDetector class correctly identifies
server timeouts, connection timeouts, and distinguishes them from other errors.
"""

import errno
import socket
from unittest.mock import Mock

import pytest

from sfq.timeout_detector import TimeoutDetector


class TestTimeoutDetector:
    """Test cases for the TimeoutDetector class."""

    def test_is_server_timeout_with_valid_timeout(self):
        """Test detection of valid server timeout response."""
        status_code = 400
        response_body = "Error: Your query request was running for too long. Please try again."
        
        result = TimeoutDetector.is_server_timeout(status_code, response_body)
        
        assert result is True

    def test_is_server_timeout_with_exact_message(self):
        """Test detection with exact timeout message."""
        status_code = 400
        response_body = "Your query request was running for too long."
        
        result = TimeoutDetector.is_server_timeout(status_code, response_body)
        
        assert result is True

    def test_is_server_timeout_with_error_code(self):
        """Test detection with QUERY_TIMEOUT error code."""
        status_code = 400
        response_body = '[{"message":"Your query request was running for too long.","errorCode":"QUERY_TIMEOUT"}]'
        
        result = TimeoutDetector.is_server_timeout(status_code, response_body)
        
        assert result is True

    def test_is_server_timeout_with_error_code_only(self):
        """Test detection with only QUERY_TIMEOUT error code (no message)."""
        status_code = 400
        response_body = '[{"errorCode":"QUERY_TIMEOUT","details":"Query execution exceeded time limit"}]'
        
        result = TimeoutDetector.is_server_timeout(status_code, response_body)
        
        assert result is True

    def test_is_server_timeout_with_different_error_code(self):
        """Test that different error codes are not detected as timeouts."""
        status_code = 400
        response_body = '[{"message":"Invalid query","errorCode":"INVALID_QUERY"}]'
        
        result = TimeoutDetector.is_server_timeout(status_code, response_body)
        
        assert result is False

    def test_is_server_timeout_with_wrong_status_code(self):
        """Test that non-400 status codes are not detected as server timeouts."""
        status_code = 500
        response_body = "Your query request was running for too long."
        
        result = TimeoutDetector.is_server_timeout(status_code, response_body)
        
        assert result is False

    def test_is_server_timeout_with_none_status_code(self):
        """Test that None status code is not detected as server timeout."""
        status_code = None
        response_body = "Your query request was running for too long."
        
        result = TimeoutDetector.is_server_timeout(status_code, response_body)
        
        assert result is False

    def test_is_server_timeout_with_none_response_body(self):
        """Test that None response body is not detected as server timeout."""
        status_code = 400
        response_body = None
        
        result = TimeoutDetector.is_server_timeout(status_code, response_body)
        
        assert result is False

    def test_is_server_timeout_with_different_400_error(self):
        """Test that other 400 errors are not detected as server timeouts."""
        status_code = 400
        response_body = "Bad Request: Invalid query syntax"
        
        result = TimeoutDetector.is_server_timeout(status_code, response_body)
        
        assert result is False

    def test_is_connection_timeout_with_valid_errno_110(self):
        """Test detection of connection timeout with errno 110."""
        status_code = None
        response_body = None
        exception = OSError()
        exception.errno = errno.ETIMEDOUT
        
        result = TimeoutDetector.is_connection_timeout(status_code, response_body, exception)
        
        assert result is True

    def test_is_connection_timeout_with_socket_timeout(self):
        """Test detection of socket timeout exception."""
        status_code = None
        response_body = None
        exception = socket.timeout("Connection timed out")
        exception.errno = errno.ETIMEDOUT
        
        result = TimeoutDetector.is_connection_timeout(status_code, response_body, exception)
        
        assert result is True

    def test_is_connection_timeout_with_nested_errno(self):
        """Test detection of connection timeout with nested exception containing errno."""
        status_code = None
        response_body = None
        
        # Create a nested exception structure
        cause_exception = OSError()
        cause_exception.errno = errno.ETIMEDOUT
        
        main_exception = Exception("Connection failed")
        main_exception.__cause__ = cause_exception
        
        result = TimeoutDetector.is_connection_timeout(status_code, response_body, main_exception)
        
        assert result is True

    def test_is_connection_timeout_with_errno_in_args(self):
        """Test detection of connection timeout with errno in exception args."""
        status_code = None
        response_body = None
        
        # Create an exception with errno in args
        arg_with_errno = Mock()
        arg_with_errno.errno = errno.ETIMEDOUT
        
        exception = Exception("Connection failed")
        exception.args = [arg_with_errno, "additional info"]
        
        result = TimeoutDetector.is_connection_timeout(status_code, response_body, exception)
        
        assert result is True

    def test_is_connection_timeout_with_non_none_status(self):
        """Test that non-None status code is not detected as connection timeout."""
        status_code = 500
        response_body = None
        exception = OSError()
        exception.errno = errno.ETIMEDOUT
        
        result = TimeoutDetector.is_connection_timeout(status_code, response_body, exception)
        
        assert result is False

    def test_is_connection_timeout_with_non_none_body(self):
        """Test that non-None response body is not detected as connection timeout."""
        status_code = None
        response_body = "Some error message"
        exception = OSError()
        exception.errno = errno.ETIMEDOUT
        
        result = TimeoutDetector.is_connection_timeout(status_code, response_body, exception)
        
        assert result is False

    def test_is_connection_timeout_with_no_exception(self):
        """Test that missing exception is not detected as connection timeout."""
        status_code = None
        response_body = None
        exception = None
        
        result = TimeoutDetector.is_connection_timeout(status_code, response_body, exception)
        
        assert result is False

    def test_is_connection_timeout_with_wrong_errno(self):
        """Test that wrong errno is not detected as connection timeout."""
        status_code = None
        response_body = None
        exception = OSError()
        exception.errno = errno.ECONNREFUSED  # Different errno
        
        result = TimeoutDetector.is_connection_timeout(status_code, response_body, exception)
        
        assert result is False

    def test_is_connection_timeout_with_no_errno(self):
        """Test that exception without errno is not detected as connection timeout."""
        status_code = None
        response_body = None
        exception = Exception("Some other error")
        
        result = TimeoutDetector.is_connection_timeout(status_code, response_body, exception)
        
        assert result is False

    def test_is_timeout_error_with_server_timeout(self):
        """Test unified timeout detection with server timeout."""
        status_code = 400
        response_body = "Your query request was running for too long."
        
        result = TimeoutDetector.is_timeout_error(status_code, response_body)
        
        assert result is True

    def test_is_timeout_error_with_connection_timeout(self):
        """Test unified timeout detection with connection timeout."""
        status_code = None
        response_body = None
        exception = OSError()
        exception.errno = errno.ETIMEDOUT
        
        result = TimeoutDetector.is_timeout_error(status_code, response_body, exception)
        
        assert result is True

    def test_is_timeout_error_with_no_timeout(self):
        """Test unified timeout detection with non-timeout error."""
        status_code = 500
        response_body = "Internal Server Error"
        
        result = TimeoutDetector.is_timeout_error(status_code, response_body)
        
        assert result is False

    def test_is_timeout_error_with_different_400_error(self):
        """Test unified timeout detection with different 400 error."""
        status_code = 400
        response_body = "Bad Request: Invalid syntax"
        
        result = TimeoutDetector.is_timeout_error(status_code, response_body)
        
        assert result is False

    def test_get_timeout_type_server(self):
        """Test timeout type detection for server timeout."""
        status_code = 400
        response_body = "Your query request was running for too long."
        
        result = TimeoutDetector.get_timeout_type(status_code, response_body)
        
        assert result == 'server'

    def test_get_timeout_type_connection(self):
        """Test timeout type detection for connection timeout."""
        status_code = None
        response_body = None
        exception = OSError()
        exception.errno = errno.ETIMEDOUT
        
        result = TimeoutDetector.get_timeout_type(status_code, response_body, exception)
        
        assert result == 'connection'

    def test_get_timeout_type_none(self):
        """Test timeout type detection for non-timeout error."""
        status_code = 500
        response_body = "Internal Server Error"
        
        result = TimeoutDetector.get_timeout_type(status_code, response_body)
        
        assert result is None

    def test_get_timeout_type_prioritizes_server_over_connection(self):
        """Test that server timeout is detected even when connection timeout conditions are also present."""
        status_code = 400
        response_body = "Your query request was running for too long."
        exception = OSError()
        exception.errno = errno.ETIMEDOUT
        
        result = TimeoutDetector.get_timeout_type(status_code, response_body, exception)
        
        assert result == 'server'


class TestTimeoutDetectorEdgeCases:
    """Test edge cases and boundary conditions for TimeoutDetector."""

    def test_server_timeout_message_case_sensitivity(self):
        """Test that server timeout message detection is case sensitive."""
        status_code = 400
        response_body = "your query request was running for too long."  # lowercase
        
        result = TimeoutDetector.is_server_timeout(status_code, response_body)
        
        assert result is False

    def test_server_timeout_partial_message_match(self):
        """Test that partial message matches work correctly."""
        status_code = 400
        response_body = "Error occurred: Your query request was running for too long. Please retry."
        
        result = TimeoutDetector.is_server_timeout(status_code, response_body)
        
        assert result is True

    def test_connection_timeout_with_empty_args(self):
        """Test connection timeout detection with empty exception args."""
        status_code = None
        response_body = None
        exception = Exception("Connection failed")
        exception.args = []
        
        result = TimeoutDetector.is_connection_timeout(status_code, response_body, exception)
        
        assert result is False

    def test_connection_timeout_with_multiple_nested_causes(self):
        """Test connection timeout detection with multiple levels of nested exceptions."""
        status_code = None
        response_body = None
        
        # Create deeply nested exception structure
        deepest_cause = OSError()
        deepest_cause.errno = errno.ETIMEDOUT
        
        middle_cause = Exception("Middle exception")
        middle_cause.__cause__ = deepest_cause
        
        main_exception = Exception("Main exception")
        main_exception.__cause__ = middle_cause
        
        result = TimeoutDetector.is_connection_timeout(status_code, response_body, main_exception)
        
        # Current implementation only checks one level deep
        assert result is False

    def test_server_timeout_with_empty_string_body(self):
        """Test server timeout detection with empty string response body."""
        status_code = 400
        response_body = ""
        
        result = TimeoutDetector.is_server_timeout(status_code, response_body)
        
        assert result is False

    def test_all_methods_with_all_none_parameters(self):
        """Test all methods with None parameters."""
        status_code = None
        response_body = None
        exception = None
        
        assert TimeoutDetector.is_server_timeout(status_code, response_body) is False
        assert TimeoutDetector.is_connection_timeout(status_code, response_body, exception) is False
        assert TimeoutDetector.is_timeout_error(status_code, response_body, exception) is False
        assert TimeoutDetector.get_timeout_type(status_code, response_body, exception) is None