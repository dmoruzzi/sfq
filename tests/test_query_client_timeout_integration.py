"""
Integration tests for QueryClient operations with timeout retry functionality.

This module tests the integration between QueryClient and HTTPClient retry mechanism
for various query types including standard SOQL queries, tooling API queries,
composite batch queries, and pagination scenarios.
"""

import errno
import json
from collections import OrderedDict
from unittest.mock import Mock, patch

import pytest

from sfq.auth import AuthManager
from sfq.exceptions import QueryTimeoutError
from sfq.http_client import HTTPClient
from sfq.query import QueryClient


class TestQueryClientTimeoutIntegration:
    """Integration tests for QueryClient with timeout retry functionality."""

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

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    def test_standard_soql_query_timeout_retry_success(self, mock_internal, query_client):
        """Test timeout retry with standard SOQL queries that succeed on retry."""
        # First call returns server timeout, second call succeeds
        mock_internal.side_effect = [
            (400, '[{"message":"Your query request was running for too long.","errorCode":"QUERY_TIMEOUT"}]'),
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

        # Verify the correct endpoint was called
        first_call = mock_internal.call_args_list[0]
        second_call = mock_internal.call_args_list[1]
        
        # Both calls should be identical
        assert first_call == second_call
        assert first_call[0][1] == "/services/data/v65.0/query?q=SELECT%20Id%2C%20Name%20FROM%20Account%20LIMIT%202"

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    def test_standard_soql_query_timeout_retry_all_fail(self, mock_internal, query_client):
        """Test timeout retry with standard SOQL queries that fail on all attempts."""
        # All calls return server timeout
        mock_internal.return_value = (
            400, 
            '[{"message":"Your query request was running for too long.","errorCode":"QUERY_TIMEOUT"}]'
        )

        result = query_client.query("SELECT Id, Name FROM Account")

        # QueryClient should return None when HTTPClient raises QueryTimeoutError
        assert result is None
        # Should try initial + 3 retries = 4 total attempts
        assert mock_internal.call_count == 4

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    def test_tooling_api_query_timeout_retry_success(self, mock_internal, query_client):
        """Test timeout retry with tooling API queries that succeed on retry."""
        # First call returns connection timeout, second call succeeds
        timeout_exception = OSError("Connection timed out")
        timeout_exception.errno = errno.ETIMEDOUT

        mock_internal.side_effect = [
            timeout_exception,
            (200, json.dumps({
                "totalSize": 1,
                "done": True,
                "records": [
                    {"Id": "01p000000000001", "Name": "Test Apex Class"}
                ]
            }))
        ]

        result = query_client.tooling_query("SELECT Id, Name FROM ApexClass LIMIT 1")

        assert result is not None
        assert result["totalSize"] == 1
        assert len(result["records"]) == 1
        assert result["records"][0]["Name"] == "Test Apex Class"
        assert mock_internal.call_count == 2

        # Verify the tooling endpoint was called
        first_call = mock_internal.call_args_list[0]
        assert first_call[0][1] == "/services/data/v65.0/tooling/query?q=SELECT%20Id%2C%20Name%20FROM%20ApexClass%20LIMIT%201"

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    def test_tooling_api_query_timeout_retry_all_fail(self, mock_internal, query_client):
        """Test timeout retry with tooling API queries that fail on all attempts."""
        # Create a connection timeout exception
        timeout_exception = OSError("Connection timed out")
        timeout_exception.errno = errno.ETIMEDOUT

        # All calls raise timeout exception
        mock_internal.side_effect = timeout_exception

        result = query_client.tooling_query("SELECT Id, Name FROM ApexClass")

        # QueryClient should return None when HTTPClient raises QueryTimeoutError
        assert result is None
        # Should try initial + 3 retries = 4 total attempts
        assert mock_internal.call_count == 4

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    def test_composite_batch_query_timeout_retry_success(self, mock_internal, query_client):
        """Test timeout retry with composite batch queries that succeed on retry."""
        query_dict = {
            "accounts": "SELECT Id, Name FROM Account LIMIT 2",
            "contacts": "SELECT Id, Name FROM Contact LIMIT 2"
        }

        # First call returns server timeout, second call succeeds
        mock_internal.side_effect = [
            (400, '[{"message":"Your query request was running for too long.","errorCode":"QUERY_TIMEOUT"}]'),
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
                            "totalSize": 2,
                            "done": True,
                            "records": [
                                {"Id": "003000000000001", "Name": "Test Contact 1"},
                                {"Id": "003000000000002", "Name": "Test Contact 2"}
                            ]
                        }
                    }
                ]
            }))
        ]

        result = query_client.cquery(query_dict)

        assert result is not None
        assert "accounts" in result
        assert "contacts" in result
        assert len(result["accounts"]["records"]) == 2
        assert len(result["contacts"]["records"]) == 2
        assert mock_internal.call_count == 2

        # Verify the composite batch endpoint was called
        first_call = mock_internal.call_args_list[0]
        assert first_call[0][1] == "/services/data/v65.0/composite/batch"
        assert first_call[0][0] == "POST"

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    def test_composite_batch_query_timeout_retry_all_fail(self, mock_internal, query_client):
        """Test timeout retry with composite batch queries that fail on all attempts."""
        query_dict = {
            "accounts": "SELECT Id, Name FROM Account LIMIT 2"
        }

        # All calls return server timeout
        mock_internal.return_value = (
            400, 
            '[{"message":"Your query request was running for too long.","errorCode":"QUERY_TIMEOUT"}]'
        )

        # When all retries fail, HTTPClient raises QueryTimeoutError which propagates through cquery
        with pytest.raises(QueryTimeoutError, match="QUERY_TIMEOUT"):
            query_client.cquery(query_dict)

        # Should try initial + 3 retries = 4 total attempts
        assert mock_internal.call_count == 4

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    @patch("sfq.http_client.HTTPClient.send_request")
    def test_pagination_with_timeout_retry_success(self, mock_send_request, mock_internal, query_client):
        """Test that pagination still works correctly after timeout retries."""
        # First call returns server timeout, second call returns paginated result
        mock_internal.side_effect = [
            (400, '[{"message":"Your query request was running for too long.","errorCode":"QUERY_TIMEOUT"}]'),
            (200, json.dumps({
                "totalSize": 4,
                "done": False,
                "nextRecordsUrl": "/services/data/v65.0/query/01gXX0000000001-2000",
                "records": [
                    {"Id": "001000000000001", "Name": "Test Account 1"},
                    {"Id": "001000000000002", "Name": "Test Account 2"}
                ]
            }))
        ]

        # Mock the pagination request
        mock_send_request.return_value = (200, json.dumps({
            "totalSize": 4,
            "done": True,
            "records": [
                {"Id": "001000000000003", "Name": "Test Account 3"},
                {"Id": "001000000000004", "Name": "Test Account 4"}
            ]
        }))

        result = query_client.query("SELECT Id, Name FROM Account")

        assert result is not None
        assert result["totalSize"] == 4
        assert result["done"] is True
        assert len(result["records"]) == 4
        assert "nextRecordsUrl" not in result

        # Verify retry was attempted
        assert mock_internal.call_count == 2
        # Verify pagination was called
        mock_send_request.assert_called_once_with(
            method="GET",
            endpoint="/services/data/v65.0/query/01gXX0000000001-2000",
            headers=query_client.http_client.get_common_headers(include_auth=True)
        )

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    @patch("sfq.http_client.HTTPClient.send_request")
    def test_pagination_timeout_during_next_records_fetch(self, mock_send_request, mock_internal, query_client):
        """Test pagination behavior when timeout occurs during nextRecordsUrl fetch."""
        # Initial query succeeds but returns paginated result
        mock_internal.return_value = (200, json.dumps({
            "totalSize": 4,
            "done": False,
            "nextRecordsUrl": "/services/data/v65.0/query/01gXX0000000001-2000",
            "records": [
                {"Id": "001000000000001", "Name": "Test Account 1"},
                {"Id": "001000000000002", "Name": "Test Account 2"}
            ]
        }))

        # Pagination request fails with server error (not timeout - pagination doesn't use retry)
        mock_send_request.return_value = (500, "Server Error")

        result = query_client.query("SELECT Id, Name FROM Account")

        assert result is not None
        # Should return what we have so far
        assert len(result["records"]) == 2
        assert result["done"] is False  # Still false since we couldn't complete pagination

        # Verify initial query was called once (no retry needed)
        assert mock_internal.call_count == 1
        # Verify pagination was attempted once
        mock_send_request.assert_called_once()

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    def test_successful_queries_no_performance_impact(self, mock_internal, query_client):
        """Test that successful queries have no performance impact from retry mechanism."""
        # Mock successful response
        mock_internal.return_value = (200, json.dumps({
            "totalSize": 1,
            "done": True,
            "records": [
                {"Id": "001000000000001", "Name": "Test Account"}
            ]
        }))

        result = query_client.query("SELECT Id, Name FROM Account LIMIT 1")

        assert result is not None
        assert result["totalSize"] == 1
        assert len(result["records"]) == 1
        # Should only be called once (no retries needed)
        assert mock_internal.call_count == 1

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    def test_composite_batch_single_batch_timeout_retry_success(self, mock_internal, query_client):
        """Test composite batch queries with timeout retry in a single batch scenario."""
        # Create a small query dict that fits in one batch
        query_dict = {
            "query_001": "SELECT Id FROM Account WHERE Name = 'Test1'",
            "query_002": "SELECT Id FROM Account WHERE Name = 'Test2'"
        }

        # First call times out, second call succeeds
        mock_internal.side_effect = [
            (400, '[{"message":"Your query request was running for too long.","errorCode":"QUERY_TIMEOUT"}]'),
            (200, json.dumps({
                "results": [
                    {
                        "statusCode": 200,
                        "result": {
                            "totalSize": 1,
                            "done": True,
                            "records": [{"Id": "001000000000001"}]
                        }
                    },
                    {
                        "statusCode": 200,
                        "result": {
                            "totalSize": 1,
                            "done": True,
                            "records": [{"Id": "001000000000002"}]
                        }
                    }
                ]
            }))
        ]

        result = query_client.cquery(query_dict, batch_size=25)

        assert result is not None
        assert len(result) == 2
        assert "query_001" in result
        assert "query_002" in result
        assert result["query_001"]["totalSize"] == 1
        assert result["query_002"]["totalSize"] == 1

        # Should have made 2 calls (timeout + retry)
        assert mock_internal.call_count == 2

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    def test_sobject_prefix_operations_with_timeout_retry(self, mock_internal, query_client):
        """Test sObject prefix operations with timeout retry functionality."""
        # First call returns connection timeout, second call succeeds
        timeout_exception = OSError("Connection timed out")
        timeout_exception.errno = errno.ETIMEDOUT

        mock_internal.side_effect = [
            timeout_exception,
            (200, json.dumps({
                "sobjects": [
                    {"name": "Account", "keyPrefix": "001"},
                    {"name": "Contact", "keyPrefix": "003"},
                    {"name": "Opportunity", "keyPrefix": "006"}
                ]
            }))
        ]

        # Test get_sobject_prefixes with retry
        result = query_client.get_sobject_prefixes(key_type="id")

        assert result is not None
        assert len(result) == 3
        assert result["001"] == "Account"
        assert result["003"] == "Contact"
        assert result["006"] == "Opportunity"
        assert mock_internal.call_count == 2

        # Reset mock for next test
        mock_internal.reset_mock()
        mock_internal.side_effect = [
            timeout_exception,
            (200, json.dumps({
                "sobjects": [
                    {"name": "Account", "keyPrefix": "001"},
                    {"name": "Contact", "keyPrefix": "003"}
                ]
            }))
        ]

        # Test get_sobject_name_from_id (which calls get_sobject_prefixes internally)
        result = query_client.get_sobject_name_from_id("001000000000001AAA")

        assert result == "Account"
        assert mock_internal.call_count == 2

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    def test_non_timeout_errors_no_retry_in_query_operations(self, mock_internal, query_client):
        """Test that non-timeout errors do not trigger retry logic in query operations."""
        # Return a 400 error that is NOT a timeout
        mock_internal.return_value = (400, json.dumps([{
            "message": "Invalid query syntax",
            "errorCode": "MALFORMED_QUERY"
        }]))

        result = query_client.query("INVALID QUERY SYNTAX")

        assert result is None
        # Should only be called once (no retries)
        assert mock_internal.call_count == 1

        # Reset mock for composite query test
        mock_internal.reset_mock()
        mock_internal.return_value = (500, "Internal Server Error")

        query_dict = {"test": "SELECT Id FROM Account"}
        result = query_client.cquery(query_dict)

        assert result is not None
        assert "test" in result
        assert result["test"] == "Internal Server Error"
        # Should only be called once (no retries)
        assert mock_internal.call_count == 1

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    def test_composite_batch_with_individual_query_pagination_and_timeout(self, mock_internal, query_client, http_client):
        """Test composite batch queries where individual results need pagination after timeout retry."""
        query_dict = {"large_query": "SELECT Id, Name FROM Account"}

        # First call times out, second call returns paginated result
        mock_internal.side_effect = [
            (400, '[{"message":"Your query request was running for too long.","errorCode":"QUERY_TIMEOUT"}]'),
            (200, json.dumps({
                "results": [
                    {
                        "statusCode": 200,
                        "result": {
                            "totalSize": 4,
                            "done": False,
                            "nextRecordsUrl": "/services/data/v65.0/query/01gXX0000000001-2000",
                            "records": [
                                {"Id": "001000000000001", "Name": "Test Account 1"},
                                {"Id": "001000000000002", "Name": "Test Account 2"}
                            ]
                        }
                    }
                ]
            }))
        ]

        # Mock the pagination response
        with patch.object(http_client, 'send_request') as mock_send_request:
            mock_send_request.return_value = (200, json.dumps({
                "totalSize": 4,
                "done": True,
                "records": [
                    {"Id": "001000000000003", "Name": "Test Account 3"},
                    {"Id": "001000000000004", "Name": "Test Account 4"}
                ]
            }))

            result = query_client.cquery(query_dict)

            assert result is not None
            assert "large_query" in result
            assert len(result["large_query"]["records"]) == 4
            assert result["large_query"]["done"] is True
            assert "nextRecordsUrl" not in result["large_query"]

            # Verify retry was attempted
            assert mock_internal.call_count == 2
            # Verify pagination was called
            mock_send_request.assert_called_once()

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    def test_query_client_maintains_order_with_timeout_retries(self, mock_internal, query_client):
        """Test that QueryClient maintains result order even with timeout retries."""
        # Use OrderedDict to ensure input order
        query_dict = OrderedDict([
            ("first", "SELECT Id FROM Account LIMIT 1"),
            ("second", "SELECT Id FROM Contact LIMIT 1"),
            ("third", "SELECT Id FROM Opportunity LIMIT 1")
        ])

        call_count = 0
        def mock_response(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            
            # Second query (Contact) times out on first attempt
            if call_count == 1:
                return (400, '[{"message":"Your query request was running for too long.","errorCode":"QUERY_TIMEOUT"}]')
            
            # All other calls succeed
            return (200, json.dumps({
                "results": [
                    {
                        "statusCode": 200,
                        "result": {
                            "totalSize": 1,
                            "done": True,
                            "records": [{"Id": "001000000000001"}]
                        }
                    },
                    {
                        "statusCode": 200,
                        "result": {
                            "totalSize": 1,
                            "done": True,
                            "records": [{"Id": "003000000000001"}]
                        }
                    },
                    {
                        "statusCode": 200,
                        "result": {
                            "totalSize": 1,
                            "done": True,
                            "records": [{"Id": "006000000000001"}]
                        }
                    }
                ]
            }))

        mock_internal.side_effect = mock_response

        result = query_client.cquery(query_dict)

        assert result is not None
        assert len(result) == 3

        # Verify order is maintained
        result_keys = list(result.keys())
        expected_keys = ["first", "second", "third"]
        assert result_keys == expected_keys

        # Verify retry was attempted (2 calls total)
        assert mock_internal.call_count == 2

    @patch("sfq.http_client.HTTPClient._send_authenticated_request_internal")
    def test_composite_batch_multiple_batches_no_threading(self, mock_internal, query_client):
        """Test composite batch queries with multiple batches without threading complexity."""
        # Create queries that will require multiple batches
        query_dict = {
            f"query_{i:03d}": f"SELECT Id FROM Account WHERE Name = 'Test{i}'"
            for i in range(6)  # 6 queries with batch_size=3 = 2 batches
        }

        # All calls succeed (no timeouts to avoid threading complexity)
        def mock_batch_response(*args, **kwargs):
            # Parse the request body to determine batch size
            # Body is the 3rd positional argument (method, endpoint, body, additional_headers)
            body_str = args[2] if len(args) > 2 else "{}"
            body = json.loads(body_str)
            batch_requests = body.get("batchRequests", [])

            return (200, json.dumps({
                "results": [
                    {
                        "statusCode": 200,
                        "result": {
                            "totalSize": 1,
                            "done": True,
                            "records": [{"Id": f"001000000000{i:03d}"}]
                        }
                    }
                    for i in range(len(batch_requests))
                ]
            }))

        mock_internal.side_effect = mock_batch_response

        # Test with custom batch size and max_workers=1 to avoid threading
        result = query_client.cquery(query_dict, batch_size=3, max_workers=1)

        assert result is not None
        assert len(result) == 6

        # With 6 queries and batch_size=3, we have 2 batches
        assert mock_internal.call_count == 2

        # Verify all queries are present in results
        for i in range(6):
            key = f"query_{i:03d}"
            assert key in result
            # Verify successful results have the expected structure
            assert result[key]["totalSize"] == 1