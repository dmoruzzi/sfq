"""
Unit tests for the QueryClient module.

This module tests SOQL query operations, query result pagination,
composite query operations, and sObject prefix management using mocked HTTP clients.

For end-to-end tests against a real Salesforce instance, see test_query_e2e.py.
"""

import json
from collections import OrderedDict
from unittest.mock import Mock

import pytest

from sfq.query import QueryClient


class TestQueryClient:
    """Test cases for the QueryClient class."""

    @pytest.fixture
    def mock_http_client(self):
        """Create a mock HTTP client for testing."""
        mock_client = Mock()
        mock_client.send_authenticated_request = Mock()
        mock_client.send_request = Mock()
        mock_client.get_common_headers = Mock(
            return_value={
                "Authorization": "Bearer test_token",
                "Content-Type": "application/json",
            }
        )
        return mock_client

    @pytest.fixture
    def query_client(self, mock_http_client):
        """Create a QueryClient instance for testing."""
        return QueryClient(mock_http_client, api_version="v65.0")

    def test_init(self, mock_http_client):
        """Test QueryClient initialization."""
        client = QueryClient(mock_http_client, api_version="v55.0")
        assert client.http_client == mock_http_client
        assert client.api_version == "v55.0"

    def test_init_default_api_version(self, mock_http_client):
        """Test QueryClient initialization with default API version."""
        client = QueryClient(mock_http_client)
        assert client.api_version == "v65.0"

    def test_query_success(self, query_client, mock_http_client):
        """Test successful SOQL query execution."""
        # Mock response data
        mock_response = {
            "totalSize": 2,
            "done": True,
            "records": [
                {"Id": "001000000000001", "Name": "Test Account 1"},
                {"Id": "001000000000002", "Name": "Test Account 2"},
            ],
        }

        mock_http_client.send_authenticated_request.return_value = (
            200,
            json.dumps(mock_response),
        )

        result = query_client.query("SELECT Id, Name FROM Account LIMIT 2")

        assert result is not None
        assert result["totalSize"] == 2
        assert len(result["records"]) == 2
        assert result["records"][0]["Name"] == "Test Account 1"

        # Verify the correct endpoint was called
        mock_http_client.send_authenticated_request.assert_called_once_with(
            method="GET",
            endpoint="/services/data/v65.0/query?q=SELECT%20Id%2C%20Name%20FROM%20Account%20LIMIT%202",
        )

    def test_query_tooling_api(self, query_client, mock_http_client):
        """Test SOQL query execution using Tooling API."""
        mock_response = {
            "totalSize": 1,
            "done": True,
            "records": [{"Id": "01p000000000001", "Name": "Test Class"}],
        }

        mock_http_client.send_authenticated_request.return_value = (
            200,
            json.dumps(mock_response),
        )

        result = query_client.query(
            "SELECT Id, Name FROM ApexClass LIMIT 1", tooling=True
        )

        assert result is not None
        assert result["totalSize"] == 1

        # Verify the tooling endpoint was called
        mock_http_client.send_authenticated_request.assert_called_once_with(
            method="GET",
            endpoint="/services/data/v65.0/tooling/query?q=SELECT%20Id%2C%20Name%20FROM%20ApexClass%20LIMIT%201",
        )

    def test_tooling_query_convenience_method(self, query_client, mock_http_client):
        """Test the tooling_query convenience method."""
        mock_response = {
            "totalSize": 1,
            "done": True,
            "records": [{"Id": "01p000000000001", "Name": "Test Class"}],
        }

        mock_http_client.send_authenticated_request.return_value = (
            200,
            json.dumps(mock_response),
        )

        result = query_client.tooling_query("SELECT Id, Name FROM ApexClass LIMIT 1")

        assert result is not None
        assert result["totalSize"] == 1

        # Verify the tooling endpoint was called
        mock_http_client.send_authenticated_request.assert_called_once_with(
            method="GET",
            endpoint="/services/data/v65.0/tooling/query?q=SELECT%20Id%2C%20Name%20FROM%20ApexClass%20LIMIT%201",
        )

    def test_query_failure(self, query_client, mock_http_client):
        """Test query execution failure."""
        mock_http_client.send_authenticated_request.return_value = (400, "Bad Request")

        result = query_client.query("INVALID QUERY")

        assert result is None

    def test_query_exception(self, query_client, mock_http_client):
        """Test query execution with exception."""
        mock_http_client.send_authenticated_request.side_effect = Exception(
            "Network error"
        )

        result = query_client.query("SELECT Id FROM Account")

        assert result is None

    def test_paginate_query_result_single_page(self, query_client):
        """Test pagination with a single page of results."""
        initial_result = {
            "totalSize": 2,
            "done": True,
            "records": [
                {"Id": "001000000000001", "Name": "Test Account 1"},
                {"Id": "001000000000002", "Name": "Test Account 2"},
            ],
        }

        paginated = query_client._paginate_query_result(initial_result)

        assert paginated["totalSize"] == 2
        assert paginated["done"] is True
        assert len(paginated["records"]) == 2
        assert "nextRecordsUrl" not in paginated

    def test_paginate_query_result_multiple_pages(self, query_client, mock_http_client):
        """Test pagination with multiple pages of results."""
        # Initial result with nextRecordsUrl
        initial_result = {
            "totalSize": 4,
            "done": False,
            "nextRecordsUrl": "/services/data/v65.0/query/01gXX0000000001-2000",
            "records": [
                {"Id": "001000000000001", "Name": "Test Account 1"},
                {"Id": "001000000000002", "Name": "Test Account 2"},
            ],
        }

        # Second page result
        second_page = {
            "totalSize": 4,
            "done": True,
            "records": [
                {"Id": "001000000000003", "Name": "Test Account 3"},
                {"Id": "001000000000004", "Name": "Test Account 4"},
            ],
        }

        mock_http_client.send_request.return_value = (200, json.dumps(second_page))

        paginated = query_client._paginate_query_result(initial_result)

        assert paginated["totalSize"] == 4
        assert paginated["done"] is True
        assert len(paginated["records"]) == 4
        assert "nextRecordsUrl" not in paginated

        # Verify the next page was requested
        mock_http_client.send_request.assert_called_once_with(
            method="GET",
            endpoint="/services/data/v65.0/query/01gXX0000000001-2000",
            headers=mock_http_client.get_common_headers.return_value,
        )

    def test_paginate_query_result_pagination_failure(
        self, query_client, mock_http_client
    ):
        """Test pagination when fetching next page fails."""
        initial_result = {
            "totalSize": 4,
            "done": False,
            "nextRecordsUrl": "/services/data/v65.0/query/01gXX0000000001-2000",
            "records": [
                {"Id": "001000000000001", "Name": "Test Account 1"},
                {"Id": "001000000000002", "Name": "Test Account 2"},
            ],
        }

        mock_http_client.send_request.return_value = (500, "Server Error")

        paginated = query_client._paginate_query_result(initial_result)

        # Should return what we have so far
        assert len(paginated["records"]) == 2
        assert paginated["done"] is False  # Still false since we couldn't complete

    def test_cquery_success(self, query_client, mock_http_client):
        """Test successful composite query execution."""
        query_dict = {
            "accounts": "SELECT Id, Name FROM Account LIMIT 2",
            "contacts": "SELECT Id, Name FROM Contact LIMIT 2",
        }

        # Mock composite batch response
        batch_response = {
            "results": [
                {
                    "statusCode": 200,
                    "result": {
                        "totalSize": 2,
                        "done": True,
                        "records": [
                            {"Id": "001000000000001", "Name": "Test Account 1"},
                            {"Id": "001000000000002", "Name": "Test Account 2"},
                        ],
                    },
                },
                {
                    "statusCode": 200,
                    "result": {
                        "totalSize": 2,
                        "done": True,
                        "records": [
                            {"Id": "003000000000001", "Name": "Test Contact 1"},
                            {"Id": "003000000000002", "Name": "Test Contact 2"},
                        ],
                    },
                },
            ]
        }

        mock_http_client.send_authenticated_request.return_value = (
            200,
            json.dumps(batch_response),
        )

        result = query_client.cquery(query_dict)

        assert result is not None
        assert "accounts" in result
        assert "contacts" in result
        assert len(result["accounts"]["records"]) == 2
        assert len(result["contacts"]["records"]) == 2

        # Verify the composite batch endpoint was called
        mock_http_client.send_authenticated_request.assert_called_once()
        call_args = mock_http_client.send_authenticated_request.call_args
        assert call_args[1]["endpoint"] == "/services/data/v65.0/composite/batch"
        assert call_args[1]["method"] == "POST"

    def test_cquery_empty_dict(self, query_client):
        """Test composite query with empty query dictionary."""
        result = query_client.cquery({})
        assert result is None

    def test_cquery_partial_failure(self, query_client, mock_http_client):
        """Test composite query with partial failures."""
        query_dict = {
            "accounts": "SELECT Id, Name FROM Account LIMIT 2",
            "invalid": "INVALID QUERY",
        }

        batch_response = {
            "results": [
                {
                    "statusCode": 200,
                    "result": {
                        "totalSize": 2,
                        "done": True,
                        "records": [
                            {"Id": "001000000000001", "Name": "Test Account 1"},
                            {"Id": "001000000000002", "Name": "Test Account 2"},
                        ],
                    },
                },
                {
                    "statusCode": 400,
                    "result": [
                        {"message": "Invalid query", "errorCode": "MALFORMED_QUERY"}
                    ],
                },
            ]
        }

        mock_http_client.send_authenticated_request.return_value = (
            200,
            json.dumps(batch_response),
        )

        result = query_client.cquery(query_dict)

        assert result is not None
        assert "accounts" in result
        assert "invalid" in result
        assert len(result["accounts"]["records"]) == 2
        assert result["invalid"]["statusCode"] == 400

    def test_cquery_batch_failure(self, query_client, mock_http_client):
        """Test composite query when entire batch fails."""
        query_dict = {"accounts": "SELECT Id, Name FROM Account LIMIT 2"}

        mock_http_client.send_authenticated_request.return_value = (500, "Server Error")

        result = query_client.cquery(query_dict)

        assert result is not None
        assert "accounts" in result
        assert result["accounts"] == "Server Error"

    def test_cquery_batching(self, query_client, mock_http_client):
        """Test composite query batching with custom batch size."""
        # Create a query dict with more items than batch size
        query_dict = {
            f"query_{i}": f"SELECT Id FROM Account WHERE Id = '{i}'" for i in range(30)
        }

        # Mock successful responses for each batch
        def mock_batch_response(*args, **kwargs):
            return (
                200,
                json.dumps(
                    {
                        "results": [
                            {
                                "statusCode": 200,
                                "result": {
                                    "totalSize": 1,
                                    "done": True,
                                    "records": [{"Id": f"00100000000000{i}"}],
                                },
                            }
                            for i in range(
                                min(10, len(query_dict))
                            )  # Simulate batch size of 10
                        ]
                    }
                ),
            )

        mock_http_client.send_authenticated_request.side_effect = mock_batch_response

        result = query_client.cquery(query_dict, batch_size=10)

        assert result is not None
        assert len(result) == 30
        # Should have made 3 batch requests (30 queries / 10 batch size)
        assert mock_http_client.send_authenticated_request.call_count == 3

    def test_get_sobject_prefixes_id_mapping(self, query_client, mock_http_client):
        """Test getting sObject prefixes with ID mapping."""
        sobjects_response = {
            "sobjects": [
                {"name": "Account", "keyPrefix": "001"},
                {"name": "Contact", "keyPrefix": "003"},
                {"name": "Opportunity", "keyPrefix": "006"},
                {"name": "CustomObject__c", "keyPrefix": "a00"},
            ]
        }

        mock_http_client.send_authenticated_request.return_value = (
            200,
            json.dumps(sobjects_response),
        )

        result = query_client.get_sobject_prefixes(key_type="id")

        assert result is not None
        assert result["001"] == "Account"
        assert result["003"] == "Contact"
        assert result["006"] == "Opportunity"
        assert result["a00"] == "CustomObject__c"

        mock_http_client.send_authenticated_request.assert_called_once_with(
            method="GET", endpoint="/services/data/v65.0/sobjects/"
        )

    def test_get_sobject_prefixes_name_mapping(self, query_client, mock_http_client):
        """Test getting sObject prefixes with name mapping."""
        sobjects_response = {
            "sobjects": [
                {"name": "Account", "keyPrefix": "001"},
                {"name": "Contact", "keyPrefix": "003"},
            ]
        }

        mock_http_client.send_authenticated_request.return_value = (
            200,
            json.dumps(sobjects_response),
        )

        result = query_client.get_sobject_prefixes(key_type="name")

        assert result is not None
        assert result["Account"] == "001"
        assert result["Contact"] == "003"

    def test_get_sobject_prefixes_invalid_key_type(self, query_client):
        """Test getting sObject prefixes with invalid key type."""
        result = query_client.get_sobject_prefixes(key_type="invalid")
        assert result is None

    def test_get_sobject_prefixes_api_failure(self, query_client, mock_http_client):
        """Test getting sObject prefixes when API call fails."""
        mock_http_client.send_authenticated_request.return_value = (500, "Server Error")

        result = query_client.get_sobject_prefixes()
        assert result is None

    def test_get_sobject_prefixes_missing_data(self, query_client, mock_http_client):
        """Test getting sObject prefixes with missing keyPrefix or name."""
        sobjects_response = {
            "sobjects": [
                {"name": "Account", "keyPrefix": "001"},
                {"name": "Contact"},  # Missing keyPrefix
                {"keyPrefix": "006"},  # Missing name
                {"name": "Opportunity", "keyPrefix": "006"},
            ]
        }

        mock_http_client.send_authenticated_request.return_value = (
            200,
            json.dumps(sobjects_response),
        )

        result = query_client.get_sobject_prefixes(key_type="id")

        assert result is not None
        assert len(result) == 2  # Only Account and Opportunity should be included
        assert result["001"] == "Account"
        assert result["006"] == "Opportunity"

    def test_get_sobject_name_from_id(self, query_client, mock_http_client):
        """Test getting sObject name from record ID."""
        sobjects_response = {
            "sobjects": [
                {"name": "Account", "keyPrefix": "001"},
                {"name": "Contact", "keyPrefix": "003"},
            ]
        }

        mock_http_client.send_authenticated_request.return_value = (
            200,
            json.dumps(sobjects_response),
        )

        result = query_client.get_sobject_name_from_id("001000000000001AAA")
        assert result == "Account"

        result = query_client.get_sobject_name_from_id("003000000000001")
        assert result == "Contact"

    def test_get_sobject_name_from_id_invalid(self, query_client):
        """Test getting sObject name from invalid record ID."""
        result = query_client.get_sobject_name_from_id("")
        assert result is None

        result = query_client.get_sobject_name_from_id("12")
        assert result is None

    def test_get_key_prefix_for_sobject(self, query_client, mock_http_client):
        """Test getting key prefix for sObject name."""
        sobjects_response = {
            "sobjects": [
                {"name": "Account", "keyPrefix": "001"},
                {"name": "Contact", "keyPrefix": "003"},
            ]
        }

        mock_http_client.send_authenticated_request.return_value = (
            200,
            json.dumps(sobjects_response),
        )

        result = query_client.get_key_prefix_for_sobject("Account")
        assert result == "001"

        result = query_client.get_key_prefix_for_sobject("Contact")
        assert result == "003"

    def test_get_key_prefix_for_sobject_invalid(self, query_client):
        """Test getting key prefix for invalid sObject name."""
        result = query_client.get_key_prefix_for_sobject("")
        assert result is None

    def test_validate_query_syntax_valid(self, query_client):
        """Test query syntax validation with valid queries."""
        assert query_client.validate_query_syntax("SELECT Id FROM Account") is True
        assert (
            query_client.validate_query_syntax(
                "SELECT Id, Name FROM Contact WHERE Name = 'Test'"
            )
            is True
        )
        assert (
            query_client.validate_query_syntax("SELECT COUNT() FROM Opportunity")
            is True
        )
        assert (
            query_client.validate_query_syntax(
                "SELECT Id FROM Account WHERE Name IN ('Test1', 'Test2')"
            )
            is True
        )

    def test_validate_query_syntax_invalid(self, query_client):
        """Test query syntax validation with invalid queries."""
        assert query_client.validate_query_syntax("") is False
        assert query_client.validate_query_syntax("   ") is False
        assert (
            query_client.validate_query_syntax("UPDATE Account SET Name = 'Test'")
            is False
        )
        assert query_client.validate_query_syntax("SELECT Id") is False  # Missing FROM
        assert (
            query_client.validate_query_syntax(
                "SELECT Id FROM Account WHERE Name = 'Test"
            )
            is False
        )  # Unbalanced quotes
        assert (
            query_client.validate_query_syntax(
                "SELECT Id FROM Account WHERE (Name = 'Test'"
            )
            is False
        )  # Unbalanced parentheses

    def test_repr(self, query_client):
        """Test string representation of QueryClient."""
        repr_str = repr(query_client)
        assert "QueryClient" in repr_str
        assert "v65.0" in repr_str
        assert "Mock" in repr_str  # Should show the mock HTTP client type


class TestCompositeQueryFunctionality:
    """Additional tests specifically for composite query functionality and sObject prefix management."""

    @pytest.fixture
    def mock_http_client(self):
        """Create a mock HTTP client for testing."""
        mock_client = Mock()
        mock_client.send_authenticated_request = Mock()
        mock_client.send_request = Mock()
        mock_client.get_common_headers = Mock(
            return_value={
                "Authorization": "Bearer test_token",
                "Content-Type": "application/json",
            }
        )
        return mock_client

    @pytest.fixture
    def query_client(self, mock_http_client):
        """Create a QueryClient instance for testing."""
        return QueryClient(mock_http_client, api_version="v65.0")

    def test_cquery_threading_with_large_dataset(self, query_client, mock_http_client):
        """Test composite query threading with a large number of queries."""
        # Create 100 queries to test threading
        query_dict = {
            f"query_{i:03d}": f"SELECT Id FROM Account WHERE Name = 'Test{i}'"
            for i in range(100)
        }

        def mock_batch_response(*args, **kwargs):
            # Parse the request body to determine batch size
            body = json.loads(kwargs.get("body", "{}"))
            batch_requests = body.get("batchRequests", [])

            return (
                200,
                json.dumps(
                    {
                        "results": [
                            {
                                "statusCode": 200,
                                "result": {
                                    "totalSize": 1,
                                    "done": True,
                                    "records": [{"Id": f"001000000000{i:03d}"}],
                                },
                            }
                            for i in range(len(batch_requests))
                        ]
                    }
                ),
            )

        mock_http_client.send_authenticated_request.side_effect = mock_batch_response

        # Test with custom batch size and max workers
        result = query_client.cquery(query_dict, batch_size=20, max_workers=5)

        assert result is not None
        assert len(result) == 100

        # Should have made 5 batch requests (100 queries / 20 batch size)
        assert mock_http_client.send_authenticated_request.call_count == 5

        # Verify all queries are present in results
        for i in range(100):
            key = f"query_{i:03d}"
            assert key in result
            assert result[key]["totalSize"] == 1

    def test_cquery_with_pagination_in_batch_results(
        self, query_client, mock_http_client
    ):
        """Test composite query where individual results need pagination."""
        query_dict = {"large_query": "SELECT Id, Name FROM Account"}

        # Mock the initial batch response with pagination needed
        batch_response = {
            "results": [
                {
                    "statusCode": 200,
                    "result": {
                        "totalSize": 4,
                        "done": False,
                        "nextRecordsUrl": "/services/data/v65.0/query/01gXX0000000001-2000",
                        "records": [
                            {"Id": "001000000000001", "Name": "Test Account 1"},
                            {"Id": "001000000000002", "Name": "Test Account 2"},
                        ],
                    },
                }
            ]
        }

        # Mock the pagination response
        pagination_response = {
            "totalSize": 4,
            "done": True,
            "records": [
                {"Id": "001000000000003", "Name": "Test Account 3"},
                {"Id": "001000000000004", "Name": "Test Account 4"},
            ],
        }

        mock_http_client.send_authenticated_request.return_value = (
            200,
            json.dumps(batch_response),
        )
        mock_http_client.send_request.return_value = (
            200,
            json.dumps(pagination_response),
        )

        result = query_client.cquery(query_dict)

        assert result is not None
        assert "large_query" in result
        assert len(result["large_query"]["records"]) == 4
        assert result["large_query"]["done"] is True
        assert "nextRecordsUrl" not in result["large_query"]

        # Verify pagination was called
        mock_http_client.send_request.assert_called_once()

    def test_sobject_prefix_management_integration(
        self, query_client, mock_http_client
    ):
        """Test sObject prefix management functionality integration."""
        # Mock sobjects response
        sobjects_response = {
            "sobjects": [
                {"name": "Account", "keyPrefix": "001"},
                {"name": "Contact", "keyPrefix": "003"},
                {"name": "Opportunity", "keyPrefix": "006"},
                {"name": "Lead", "keyPrefix": "00Q"},
                {"name": "Case", "keyPrefix": "500"},
            ]
        }

        mock_http_client.send_authenticated_request.return_value = (
            200,
            json.dumps(sobjects_response),
        )

        # Test getting all prefixes
        prefixes = query_client.get_sobject_prefixes(key_type="id")
        assert len(prefixes) == 5
        assert prefixes["001"] == "Account"
        assert prefixes["003"] == "Contact"

        # Test reverse mapping
        name_prefixes = query_client.get_sobject_prefixes(key_type="name")
        assert name_prefixes["Account"] == "001"
        assert name_prefixes["Contact"] == "003"

        # Test individual lookup methods
        assert query_client.get_sobject_name_from_id("001000000000001AAA") == "Account"
        assert query_client.get_sobject_name_from_id("003000000000001") == "Contact"
        assert query_client.get_key_prefix_for_sobject("Opportunity") == "006"
        assert query_client.get_key_prefix_for_sobject("Lead") == "00Q"

    def test_cquery_error_handling_mixed_results(self, query_client, mock_http_client):
        """Test composite query error handling with mixed success/failure results."""
        query_dict = {
            "good_query1": "SELECT Id FROM Account LIMIT 1",
            "bad_query": "SELECT InvalidField FROM NonExistentObject",
            "good_query2": "SELECT Id FROM Contact LIMIT 1",
            "timeout_query": "SELECT Id FROM LargeObject__c",
        }

        # Mock response with mixed results
        batch_response = {
            "results": [
                {
                    "statusCode": 200,
                    "result": {
                        "totalSize": 1,
                        "done": True,
                        "records": [{"Id": "001000000000001"}],
                    },
                },
                {
                    "statusCode": 400,
                    "result": [
                        {"message": "Invalid field", "errorCode": "INVALID_FIELD"}
                    ],
                },
                {
                    "statusCode": 200,
                    "result": {
                        "totalSize": 1,
                        "done": True,
                        "records": [{"Id": "003000000000001"}],
                    },
                },
                {
                    "statusCode": 500,
                    "result": [{"message": "Timeout", "errorCode": "REQUEST_TIMEOUT"}],
                },
            ]
        }

        mock_http_client.send_authenticated_request.return_value = (
            200,
            json.dumps(batch_response),
        )

        result = query_client.cquery(query_dict)

        assert result is not None
        assert len(result) == 4

        # Check successful queries
        assert result["good_query1"]["totalSize"] == 1
        assert len(result["good_query1"]["records"]) == 1
        assert result["good_query2"]["totalSize"] == 1
        assert len(result["good_query2"]["records"]) == 1

        # Check failed queries
        assert result["bad_query"]["statusCode"] == 400
        assert result["timeout_query"]["statusCode"] == 500

    def test_cquery_maintains_order(self, query_client, mock_http_client):
        """Test that composite query maintains the order of results."""
        # Use OrderedDict to ensure input order
        query_dict = OrderedDict(
            [
                ("first", "SELECT Id FROM Account LIMIT 1"),
                ("second", "SELECT Id FROM Contact LIMIT 1"),
                ("third", "SELECT Id FROM Opportunity LIMIT 1"),
            ]
        )

        batch_response = {
            "results": [
                {
                    "statusCode": 200,
                    "result": {
                        "totalSize": 1,
                        "done": True,
                        "records": [{"Id": "001000000000001"}],
                    },
                },
                {
                    "statusCode": 200,
                    "result": {
                        "totalSize": 1,
                        "done": True,
                        "records": [{"Id": "003000000000001"}],
                    },
                },
                {
                    "statusCode": 200,
                    "result": {
                        "totalSize": 1,
                        "done": True,
                        "records": [{"Id": "006000000000001"}],
                    },
                },
            ]
        }

        mock_http_client.send_authenticated_request.return_value = (
            200,
            json.dumps(batch_response),
        )

        result = query_client.cquery(query_dict)

        assert result is not None
        result_keys = list(result.keys())
        expected_keys = ["first", "second", "third"]

        assert result_keys == expected_keys

    def test_cquery_batch_size_limits(self, query_client, mock_http_client):
        """Test composite query respects Salesforce batch size limits."""
        # Create queries that would exceed the 25-query limit per batch
        query_dict = {
            f"query_{i}": f"SELECT Id FROM Account WHERE Id = '{i}'" for i in range(50)
        }

        def mock_batch_response(*args, **kwargs):
            body = json.loads(kwargs.get("body", "{}"))
            batch_requests = body.get("batchRequests", [])

            # Verify batch size doesn't exceed 25
            assert len(batch_requests) <= 25

            return (
                200,
                json.dumps(
                    {
                        "results": [
                            {
                                "statusCode": 200,
                                "result": {
                                    "totalSize": 1,
                                    "done": True,
                                    "records": [{"Id": f"001000000000{i:03d}"}],
                                },
                            }
                            for i in range(len(batch_requests))
                        ]
                    }
                ),
            )

        mock_http_client.send_authenticated_request.side_effect = mock_batch_response

        result = query_client.cquery(query_dict, batch_size=25)

        assert result is not None
        assert len(result) == 50
        # Should have made 2 batch requests (50 queries / 25 batch size)
        assert mock_http_client.send_authenticated_request.call_count == 2


if __name__ == "__main__":
    pytest.main([__file__])
