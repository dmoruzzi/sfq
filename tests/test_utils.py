"""
Unit tests for the foundational modules (exceptions and utils).

These tests verify that the extracted foundational modules work correctly
and that the trace logging functionality with redaction is preserved.
"""

import json
import logging
from unittest.mock import patch

import pytest

from sfq.exceptions import (
    APIError,
    AuthenticationError,
    ConfigurationError,
    CRUDError,
    HTTPError,
    QueryError,
    QueryTimeoutError,
    SFQException,
    SOAPError,
)
from sfq.utils import (
    TRACE,
    _redact_sensitive,
    extract_org_and_user_ids,
    format_headers_for_logging,
    get_logger,
    log_api_usage,
    parse_api_usage_from_header,
)


class TestExceptions:
    """Test the exception hierarchy."""

    def test_exception_hierarchy(self):
        """Test that exceptions inherit correctly."""
        assert issubclass(AuthenticationError, SFQException)
        assert issubclass(APIError, SFQException)
        assert issubclass(QueryError, APIError)
        assert issubclass(QueryTimeoutError, QueryError)
        assert issubclass(CRUDError, APIError)
        assert issubclass(SOAPError, APIError)
        assert issubclass(HTTPError, SFQException)
        assert issubclass(ConfigurationError, SFQException)

    def test_exception_instantiation(self):
        """Test that exceptions can be instantiated with messages."""
        auth_error = AuthenticationError("Auth failed")
        assert str(auth_error) == "Auth failed"

        api_error = APIError("API call failed")
        assert str(api_error) == "API call failed"

        query_timeout_error = QueryTimeoutError("QUERY_TIMEOUT")
        assert str(query_timeout_error) == "QUERY_TIMEOUT"

    def test_query_timeout_error_inheritance(self):
        """Test that QueryTimeoutError properly inherits from QueryError."""
        # Test inheritance chain
        assert issubclass(QueryTimeoutError, QueryError)
        assert issubclass(QueryTimeoutError, APIError)
        assert issubclass(QueryTimeoutError, SFQException)
        assert issubclass(QueryTimeoutError, Exception)

        # Test instantiation with QUERY_TIMEOUT identifier
        timeout_error = QueryTimeoutError("QUERY_TIMEOUT")
        assert isinstance(timeout_error, QueryTimeoutError)
        assert isinstance(timeout_error, QueryError)
        assert isinstance(timeout_error, APIError)
        assert isinstance(timeout_error, SFQException)
        assert str(timeout_error) == "QUERY_TIMEOUT"

        # Test instantiation with custom message
        custom_timeout_error = QueryTimeoutError("Query timed out after 3 retries")
        assert str(custom_timeout_error) == "Query timed out after 3 retries"


class TestUtils:
    """Test utility functions."""

    def test_trace_level_configured(self):
        """Test that TRACE logging level is configured."""
        assert TRACE == 5
        assert logging.getLevelName(TRACE) == "TRACE"

    def test_get_logger(self):
        """Test logger creation."""
        logger = get_logger()
        assert logger.name == "sfq"
        assert hasattr(logger, "trace")

        custom_logger = get_logger("test")
        assert custom_logger.name == "test"

    def test_redact_sensitive_dict(self):
        """Test redaction of sensitive data in dictionaries."""
        data = {
            "access_token": "secret123",
            "normal_field": "normal_value",
            "Authorization": "Bearer token123",
            "client_secret": "secret456",
        }

        redacted = _redact_sensitive(data)

        assert redacted["access_token"] == "********"
        assert redacted["normal_field"] == "normal_value"
        assert (
            redacted["Authorization"] == "********"
        )  # authorization is in REDACT_KEYS (lowercase)
        assert redacted["client_secret"] == "********"

    def test_redact_sensitive_string_query_params(self):
        """Test redaction of sensitive data in query strings."""
        query_string = (
            "grant_type=refresh_token&client_id=123&access_token=secret&normal=value"
        )

        redacted = _redact_sensitive(query_string)

        assert "access_token=********" in redacted
        assert "client_id=123" in redacted
        assert "normal=value" in redacted

    def test_redact_sensitive_string_session_id(self):
        """Test redaction of sessionId in XML strings."""
        xml_string = "<soap:Envelope><sessionId>abc123def456</sessionId><other>data</other></soap:Envelope>"

        redacted = _redact_sensitive(xml_string)

        assert "<sessionId>********</sessionId>" in redacted
        assert "<other>data</other>" in redacted

    def test_redact_sensitive_list_tuples(self):
        """Test redaction of sensitive data in list of tuples."""
        headers = [
            ("Authorization", "Bearer token123"),
            ("Content-Type", "application/json"),
            ("access_token", "secret123"),
        ]

        redacted = _redact_sensitive(headers)

        assert ("Authorization", "********") in redacted
        assert ("Content-Type", "application/json") in redacted
        assert ("access_token", "********") in redacted

    def test_format_headers_for_logging(self):
        """Test header formatting for logging."""
        headers_dict = {
            "Authorization": "Bearer token",
            "Set-Cookie": "BrowserId=123; path=/",
            "Content-Type": "application/json",
        }

        formatted = format_headers_for_logging(headers_dict)

        # Should filter out BrowserId cookies
        assert len(formatted) == 2
        assert ("Authorization", "Bearer token") in formatted
        assert ("Content-Type", "application/json") in formatted

    def test_parse_api_usage_from_header(self):
        """Test parsing API usage from Sforce-Limit-Info header."""
        header_value = "api-usage=1234/15000"

        current, maximum, percentage = parse_api_usage_from_header(header_value)

        assert current == 1234
        assert maximum == 15000
        assert percentage == 8.23

    def test_parse_api_usage_invalid_header(self):
        """Test parsing invalid API usage header."""
        header_value = "invalid-format"

        current, maximum, percentage = parse_api_usage_from_header(header_value)

        assert current == 0
        assert maximum == 0
        assert percentage == 0.0

    @patch("sfq.utils.get_logger")
    def test_log_api_usage_high(self, mock_get_logger):
        """Test logging high API usage."""
        mock_logger = mock_get_logger.return_value
        header_value = "api-usage=12000/15000"  # 80% usage

        log_api_usage(header_value, high_usage_threshold=75)

        mock_logger.warning.assert_called_once()
        assert "High API usage" in mock_logger.warning.call_args[0][0]

    @patch("sfq.utils.get_logger")
    def test_log_api_usage_normal(self, mock_get_logger):
        """Test logging normal API usage."""
        mock_logger = mock_get_logger.return_value
        header_value = "api-usage=1000/15000"  # Low usage

        log_api_usage(header_value, high_usage_threshold=80)

        mock_logger.debug.assert_called_once()
        assert "API usage" in mock_logger.debug.call_args[0][0]

    def test_extract_org_and_user_ids(self):
        """Test extraction of org and user IDs from token URL."""
        token_url = "https://login.salesforce.com/id/00D123456789012/005987654321098"

        org_id, user_id = extract_org_and_user_ids(token_url)

        assert org_id == "00D123456789012"
        assert user_id == "005987654321098"

    def test_extract_org_and_user_ids_invalid(self):
        """Test extraction with invalid token URL."""
        token_url = "invalid-url"

        with pytest.raises(ValueError, match="Invalid token ID URL format"):
            extract_org_and_user_ids(token_url)

    def test_trace_logging_with_redaction(self):
        """Test that trace logging works with redaction."""
        # Get a real logger to test the trace method
        logger = get_logger("test_trace")

        # Test with JSON string containing sensitive data
        sensitive_data = json.dumps(
            {"access_token": "secret123", "normal_field": "normal_value"}
        )

        # Mock the _log method to capture what would be logged
        with patch.object(logger, "_log") as mock_log:
            with patch.object(logger, "isEnabledFor", return_value=True):
                # Call the trace method
                logger.trace("Test message: %s", sensitive_data)

                # Verify the logger was called
                mock_log.assert_called_once()

                # Check that the call included redacted data
                call_args = mock_log.call_args
                assert call_args[0][0] == TRACE  # Log level
                assert call_args[0][1] == "Test message: %s"  # Message

                # The redacted args should have sensitive data masked
                redacted_args = call_args[0][2]
                assert len(redacted_args) == 1
                redacted_dict = redacted_args[0]
                assert redacted_dict["access_token"] == "********"
                assert redacted_dict["normal_field"] == "normal_value"
