"""
Integration tests for QueryClient with the existing SFAuth architecture.

These tests verify that the QueryClient integrates properly with the existing
HTTP client and authentication components, and can be used as a drop-in replacement
for the query functionality in SFAuth.
"""

import os

import pytest

from sfq import SFAuth
from sfq.auth import AuthManager
from sfq.http_client import HTTPClient
from sfq.query import QueryClient


@pytest.fixture(scope="module")
def sf_auth():
    """Create an SFAuth instance for integration testing."""
    required_env_vars = [
        "SF_INSTANCE_URL",
        "SF_CLIENT_ID",
        "SF_CLIENT_SECRET",
        "SF_REFRESH_TOKEN",
    ]

    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        pytest.fail(f"Missing required env vars: {', '.join(missing_vars)}")

    return SFAuth(
        instance_url=os.getenv("SF_INSTANCE_URL"),
        client_id=os.getenv("SF_CLIENT_ID"),
        client_secret=os.getenv("SF_CLIENT_SECRET").strip(),
        refresh_token=os.getenv("SF_REFRESH_TOKEN"),
    )


@pytest.fixture(scope="module")
def modular_components():
    """Create modular components (AuthManager, HTTPClient, QueryClient) for comparison."""
    required_env_vars = [
        "SF_INSTANCE_URL",
        "SF_CLIENT_ID",
        "SF_CLIENT_SECRET",
        "SF_REFRESH_TOKEN",
    ]

    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        pytest.fail(f"Missing required env vars: {', '.join(missing_vars)}")

    auth_manager = AuthManager(
        instance_url=os.getenv("SF_INSTANCE_URL"),
        client_id=os.getenv("SF_CLIENT_ID"),
        client_secret=os.getenv("SF_CLIENT_SECRET").strip(),
        refresh_token=os.getenv("SF_REFRESH_TOKEN"),
    )

    http_client = HTTPClient(auth_manager)
    query_client = QueryClient(http_client)

    return {
        "auth_manager": auth_manager,
        "http_client": http_client,
        "query_client": query_client,
    }


class TestQueryClientIntegration:
    """Integration tests comparing SFAuth with modular QueryClient."""

    def test_query_results_match(self, sf_auth, modular_components):
        """Test that QueryClient produces the same results as SFAuth.query()."""
        query = "SELECT Id FROM Organization LIMIT 1"

        # Get result from original SFAuth
        sf_auth_result = sf_auth.query(query)

        # Get result from modular QueryClient
        query_client = modular_components["query_client"]
        http_client = modular_components["http_client"]

        # Ensure authentication
        http_client.refresh_token_and_update_auth()
        query_client_result = query_client.query(query)

        # Results should be identical
        assert sf_auth_result is not None
        assert query_client_result is not None
        assert sf_auth_result["totalSize"] == query_client_result["totalSize"]
        assert sf_auth_result["done"] == query_client_result["done"]
        assert len(sf_auth_result["records"]) == len(query_client_result["records"])

        # The actual records should be the same
        if len(sf_auth_result["records"]) > 0:
            assert (
                sf_auth_result["records"][0]["Id"]
                == query_client_result["records"][0]["Id"]
            )

    def test_tooling_query_results_match(self, sf_auth, modular_components):
        """Test that QueryClient tooling queries match SFAuth.tooling_query()."""
        query = "SELECT Id, Name FROM ApexClass LIMIT 3"

        # Get result from original SFAuth
        sf_auth_result = sf_auth.tooling_query(query)

        # Get result from modular QueryClient
        query_client = modular_components["query_client"]
        http_client = modular_components["http_client"]

        # Ensure authentication
        http_client.refresh_token_and_update_auth()
        query_client_result = query_client.tooling_query(query)

        # Results should be identical
        assert sf_auth_result is not None
        assert query_client_result is not None
        assert sf_auth_result["totalSize"] == query_client_result["totalSize"]
        assert sf_auth_result["done"] == query_client_result["done"]
        assert len(sf_auth_result["records"]) == len(query_client_result["records"])

        # If there are records, they should match
        if len(sf_auth_result["records"]) > 0:
            for i, record in enumerate(sf_auth_result["records"]):
                assert record["Id"] == query_client_result["records"][i]["Id"]
                if "Name" in record:
                    assert record["Name"] == query_client_result["records"][i]["Name"]

    def test_cquery_results_match(self, sf_auth, modular_components):
        """Test that QueryClient cquery produces the same results as SFAuth.cquery()."""
        query_dict = {
            "org_query": "SELECT Id FROM Organization LIMIT 1",
            "user_query": "SELECT Id FROM User WHERE IsActive = true LIMIT 2",
        }

        # Get result from original SFAuth
        sf_auth_result = sf_auth.cquery(query_dict)

        # Get result from modular QueryClient
        query_client = modular_components["query_client"]
        http_client = modular_components["http_client"]

        # Ensure authentication
        http_client.refresh_token_and_update_auth()
        query_client_result = query_client.cquery(query_dict)

        # Results should be identical
        assert sf_auth_result is not None
        assert query_client_result is not None
        assert len(sf_auth_result) == len(query_client_result)

        for key in query_dict.keys():
            assert key in sf_auth_result
            assert key in query_client_result

            sf_result = sf_auth_result[key]
            qc_result = query_client_result[key]

            assert sf_result["totalSize"] == qc_result["totalSize"]
            assert sf_result["done"] == qc_result["done"]
            assert len(sf_result["records"]) == len(qc_result["records"])

            # Records should match
            for i, record in enumerate(sf_result["records"]):
                assert record["Id"] == qc_result["records"][i]["Id"]

    def test_sobject_prefixes_match(self, sf_auth, modular_components):
        """Test that QueryClient sObject prefix functionality matches SFAuth."""
        # Get result from original SFAuth
        sf_auth_result = sf_auth.get_sobject_prefixes(key_type="id")

        # Get result from modular QueryClient
        query_client = modular_components["query_client"]
        http_client = modular_components["http_client"]

        # Ensure authentication
        http_client.refresh_token_and_update_auth()
        query_client_result = query_client.get_sobject_prefixes(key_type="id")

        # Results should be identical
        assert sf_auth_result is not None
        assert query_client_result is not None
        assert len(sf_auth_result) == len(query_client_result)

        # Check that all mappings match
        for prefix, sobject_name in sf_auth_result.items():
            assert prefix in query_client_result
            assert query_client_result[prefix] == sobject_name

    def test_pagination_behavior_matches(self, sf_auth, modular_components):
        """Test that pagination behavior is identical between implementations."""
        # Use a query that's likely to have pagination
        query = "SELECT Id FROM FeedComment LIMIT 2200"

        # Get result from original SFAuth
        sf_auth_result = sf_auth.query(query)

        # Get result from modular QueryClient
        query_client = modular_components["query_client"]
        http_client = modular_components["http_client"]

        # Ensure authentication
        http_client.refresh_token_and_update_auth()
        query_client_result = query_client.query(query)

        # Results should be identical
        assert sf_auth_result is not None
        assert query_client_result is not None

        # Both should have the same pagination behavior
        assert sf_auth_result["totalSize"] == query_client_result["totalSize"]
        assert sf_auth_result["done"] == query_client_result["done"]
        assert len(sf_auth_result["records"]) == len(query_client_result["records"])

        # Should not have nextRecordsUrl since pagination is handled automatically
        assert "nextRecordsUrl" not in sf_auth_result
        assert "nextRecordsUrl" not in query_client_result

        # All records should match
        for i, record in enumerate(sf_auth_result["records"]):
            assert record["Id"] == query_client_result["records"][i]["Id"]

    def test_error_handling_matches(self, sf_auth, modular_components):
        """Test that error handling behavior is consistent."""
        invalid_query = "SELECT InvalidField FROM NonExistentObject"

        # Get result from original SFAuth
        sf_auth_result = sf_auth.query(invalid_query)

        # Get result from modular QueryClient
        query_client = modular_components["query_client"]
        http_client = modular_components["http_client"]

        # Ensure authentication
        http_client.refresh_token_and_update_auth()
        query_client_result = query_client.query(invalid_query)

        # Both should return None for invalid queries
        assert sf_auth_result is None
        assert query_client_result is None

    def test_authentication_integration(self, modular_components):
        """Test that QueryClient properly integrates with AuthManager and HTTPClient."""
        auth_manager = modular_components["auth_manager"]
        http_client = modular_components["http_client"]
        query_client = modular_components["query_client"]

        # Clear any existing token to test refresh
        auth_manager.clear_token()

        # QueryClient should work even without pre-existing token
        result = query_client.query("SELECT Id FROM Organization LIMIT 1")

        assert result is not None
        assert result["totalSize"] == 1
        assert len(result["records"]) == 1

        # Token should now be available
        assert auth_manager.access_token is not None
        assert not auth_manager.needs_token_refresh()

    def test_api_version_consistency(self, sf_auth, modular_components):
        """Test that API version is handled consistently."""
        http_client = modular_components["http_client"]
        query_client = modular_components["query_client"]

        # Both should use the same API version
        assert sf_auth.api_version == http_client.get_api_version()
        assert sf_auth.api_version == query_client.api_version


if __name__ == "__main__":
    pytest.main([__file__])
