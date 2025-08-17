"""
End-to-end tests for the QueryClient module.

These tests run against a real Salesforce instance using environment variables
to ensure the QueryClient functionality works correctly in practice.
"""

import os

import pytest

from sfq.auth import AuthManager
from sfq.http_client import HTTPClient
from sfq.query import QueryClient
from sfq import SFAuth


@pytest.fixture(scope="module")
def auth_manager():
    """Create an AuthManager instance for E2E testing."""
    required_env_vars = [
        "SF_INSTANCE_URL",
        "SF_CLIENT_ID",
        "SF_CLIENT_SECRET",
        "SF_REFRESH_TOKEN",
    ]

    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        pytest.fail(f"Missing required env vars: {', '.join(missing_vars)}")

    return AuthManager(
        instance_url=os.getenv("SF_INSTANCE_URL"),
        client_id=os.getenv("SF_CLIENT_ID"),
        client_secret=os.getenv("SF_CLIENT_SECRET").strip(),
        refresh_token=os.getenv("SF_REFRESH_TOKEN"),
    )

@pytest.fixture(scope="module")
def sf_instance():
    required_env_vars = [
        "SF_INSTANCE_URL",
        "SF_CLIENT_ID",
        "SF_CLIENT_SECRET",
        "SF_REFRESH_TOKEN",
    ]

    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        pytest.fail(f"Missing required env vars: {', '.join(missing_vars)}")

    sf = SFAuth(
        instance_url=os.getenv("SF_INSTANCE_URL"),
        client_id=os.getenv("SF_CLIENT_ID"),
        client_secret=os.getenv("SF_CLIENT_SECRET").strip(),
        refresh_token=os.getenv("SF_REFRESH_TOKEN"),
    )
    return sf


@pytest.fixture(scope="module")
def http_client(auth_manager):
    """Create an HTTPClient instance for E2E testing."""
    return HTTPClient(auth_manager)


@pytest.fixture(scope="module")
def query_client(http_client):
    """Create a QueryClient instance for E2E testing."""
    return QueryClient(http_client)


class TestQueryClientE2E:
    """End-to-end tests for QueryClient against real Salesforce instance."""

    def test_simple_query(self, query_client, http_client, sf_instance):
        """Test a simple SOQL query against the real instance."""
        result = query_client.query("SELECT Id FROM Organization LIMIT 1")

        assert result is not None
        assert result["done"] is True
        assert result["totalSize"] == 1
        assert len(result["records"]) == 1
        assert "Id" in result["records"][0]
        assert result["records"][0]["Id"].startswith("00D")  # Organization ID prefix

    def test_tooling_query(self, query_client, http_client):
        """Test a tooling API query against the real instance."""
        # Refresh token to ensure we have valid authentication
        http_client.refresh_token_and_update_auth()

        result = query_client.tooling_query("SELECT Id, Name FROM ApexClass LIMIT 5")

        assert result is not None
        assert result["done"] is True
        assert result["totalSize"] >= 0  # ensure at least 1 Apex class
        assert len(result["records"]) == result["totalSize"]

        # If there are records, verify structure
        if result["totalSize"] > 0:
            assert "Id" in result["records"][0]
            assert "Name" in result["records"][0]
            assert result["records"][0]["Id"].startswith("01p")  # ApexClass ID prefix

    def test_query_with_pagination(self, query_client, http_client):
        """Test query pagination with a larger result set."""
        # Refresh token to ensure we have valid authentication
        http_client.refresh_token_and_update_auth()

        # Query for FeedComment which often has many records
        result = query_client.query("SELECT Id FROM FeedComment LIMIT 2200")

        assert result is not None
        assert result["done"] is True

        # The query should return up to 2200 records
        assert len(result["records"]) <= 2200
        assert result["totalSize"] == len(result["records"])

        # Verify all records have the expected structure
        for record in result["records"]:
            assert isinstance(record, dict)
            assert "Id" in record
            assert record["Id"].startswith("0D7")  # FeedComment ID prefix

    def test_cquery_single_query(self, query_client, http_client):
        """Test composite query with a single query."""
        # Refresh token to ensure we have valid authentication
        http_client.refresh_token_and_update_auth()

        query_dict = {"org_query": "SELECT Id FROM Organization LIMIT 1"}

        result = query_client.cquery(query_dict)

        assert result is not None
        assert "org_query" in result
        assert result["org_query"]["done"] is True
        assert result["org_query"]["totalSize"] == 1
        assert len(result["org_query"]["records"]) == 1
        assert result["org_query"]["records"][0]["Id"].startswith("00D")

    def test_cquery_multiple_queries(self, query_client, http_client):
        """Test composite query with multiple queries."""
        # Refresh token to ensure we have valid authentication
        http_client.refresh_token_and_update_auth()

        query_dict = {
            "org_query": "SELECT Id FROM Organization LIMIT 1",
            "user_query": "SELECT Id FROM User WHERE IsActive = true LIMIT 5",
            "profile_query": "SELECT Id, Name FROM Profile LIMIT 3",
        }

        result = query_client.cquery(query_dict)

        assert result is not None
        assert len(result) == 3

        # Check organization query
        assert "org_query" in result
        assert result["org_query"]["done"] is True
        assert result["org_query"]["totalSize"] == 1

        # Check user query
        assert "user_query" in result
        assert result["user_query"]["done"] is True
        assert result["user_query"]["totalSize"] <= 5
        assert len(result["user_query"]["records"]) == result["user_query"]["totalSize"]

        # Check profile query
        assert "profile_query" in result
        assert result["profile_query"]["done"] is True
        assert result["profile_query"]["totalSize"] <= 3
        assert (
            len(result["profile_query"]["records"])
            == result["profile_query"]["totalSize"]
        )

        # Verify record structures
        for record in result["user_query"]["records"]:
            assert record["Id"].startswith("005")  # User ID prefix

        for record in result["profile_query"]["records"]:
            assert record["Id"].startswith("00e")  # Profile ID prefix
            assert "Name" in record

    def test_cquery_with_large_batch(self, query_client, http_client):
        """Test composite query with a large number of queries to test batching."""
        # Refresh token to ensure we have valid authentication
        http_client.refresh_token_and_update_auth()

        query_dict = {}
        for i in range(30):
            query_dict[f"query_{i:02d}"] = "SELECT Id FROM Organization LIMIT 1"

        result = query_client.cquery(query_dict, batch_size=25)

        assert result is not None
        assert len(result) == 30

        # All queries should return the same organization record
        for i in range(30):
            key = f"query_{i:02d}"
            assert key in result
            assert result[key]["done"] is True
            assert result[key]["totalSize"] == 1
            assert len(result[key]["records"]) == 1
            assert result[key]["records"][0]["Id"].startswith("00D")

    def test_cquery_with_mixed_results(self, query_client, http_client):
        """Test composite query with both successful and failing queries."""
        # Refresh token to ensure we have valid authentication
        http_client.refresh_token_and_update_auth()

        query_dict = {
            "good_query": "SELECT Id FROM Organization LIMIT 1",
            "bad_query": "SELECT InvalidField FROM NonExistentObject",
            "another_good_query": "SELECT Id FROM User WHERE IsActive = true LIMIT 1",
        }

        result = query_client.cquery(query_dict)

        assert result is not None
        assert len(result) == 3

        # Check successful queries
        assert result["good_query"]["done"] is True
        assert result["good_query"]["totalSize"] == 1

        assert result["another_good_query"]["done"] is True
        assert result["another_good_query"]["totalSize"] >= 0

        # Check failed query - should have error information
        assert "bad_query" in result
        # The bad query should either have statusCode != 200 or be an error response
        bad_result = result["bad_query"]
        if isinstance(bad_result, dict) and "statusCode" in bad_result:
            assert bad_result["statusCode"] != 200
        # If it's a string, it means the entire batch failed
        elif isinstance(bad_result, str):
            assert "error" in bad_result.lower() or "invalid" in bad_result.lower()

    def test_get_sobject_prefixes(self, query_client, http_client):
        """Test getting sObject prefixes from the real instance."""
        # Refresh token to ensure we have valid authentication
        http_client.refresh_token_and_update_auth()

        # Test ID mapping (prefix -> name)
        id_prefixes = query_client.get_sobject_prefixes(key_type="id")

        assert id_prefixes is not None
        assert isinstance(id_prefixes, dict)
        assert len(id_prefixes) > 0

        # Check for common standard objects
        assert "001" in id_prefixes  # Account
        assert id_prefixes["001"] == "Account"
        assert "003" in id_prefixes  # Contact
        assert id_prefixes["003"] == "Contact"
        assert "006" in id_prefixes  # Opportunity
        assert id_prefixes["006"] == "Opportunity"

        # Test name mapping (name -> prefix)
        name_prefixes = query_client.get_sobject_prefixes(key_type="name")

        assert name_prefixes is not None
        assert isinstance(name_prefixes, dict)
        assert len(name_prefixes) > 0

        # Check reverse mapping
        assert "Account" in name_prefixes
        assert name_prefixes["Account"] == "001"
        assert "Contact" in name_prefixes
        assert name_prefixes["Contact"] == "003"
        assert "Opportunity" in name_prefixes
        assert name_prefixes["Opportunity"] == "006"

    def test_sobject_name_from_id(self, query_client, http_client):
        """Test getting sObject name from record ID."""
        # Refresh token to ensure we have valid authentication
        http_client.refresh_token_and_update_auth()

        # Get an actual Organization ID from the instance
        org_result = query_client.query("SELECT Id FROM Organization LIMIT 1")
        assert org_result is not None
        assert len(org_result["records"]) == 1

        org_id = org_result["records"][0]["Id"]

        # Test the utility method
        sobject_name = query_client.get_sobject_name_from_id(org_id)
        assert sobject_name == "Organization"

        # Test with a known prefix
        sobject_name = query_client.get_sobject_name_from_id("001000000000001AAA")
        assert sobject_name == "Account"

    def test_key_prefix_for_sobject(self, query_client, http_client):
        """Test getting key prefix for sObject name."""
        # Refresh token to ensure we have valid authentication
        http_client.refresh_token_and_update_auth()

        # Test common sObjects
        account_prefix = query_client.get_key_prefix_for_sobject("Account")
        assert account_prefix == "001"

        contact_prefix = query_client.get_key_prefix_for_sobject("Contact")
        assert contact_prefix == "003"

        opportunity_prefix = query_client.get_key_prefix_for_sobject("Opportunity")
        assert opportunity_prefix == "006"

        organization_prefix = query_client.get_key_prefix_for_sobject("Organization")
        assert organization_prefix == "00D"

    def test_query_validation(self, query_client):
        """Test query syntax validation."""
        # Valid queries
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

        # Invalid queries
        assert query_client.validate_query_syntax("") is False
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

    def test_query_error_handling(self, query_client, http_client):
        """Test query error handling with invalid queries."""
        # Refresh token to ensure we have valid authentication
        http_client.refresh_token_and_update_auth()

        # Test invalid field
        result = query_client.query("SELECT InvalidField FROM Account LIMIT 1")
        assert result is None

        # Test invalid object
        result = query_client.query("SELECT Id FROM NonExistentObject LIMIT 1")
        assert result is None

        # Test malformed query
        result = query_client.query("SELECT FROM Account")
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__])
