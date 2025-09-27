"""
End-to-end tests for the SFTokenAuth module.

These tests run against a real Salesforce instance using environment variables
to ensure the SFTokenAuth functionality works correctly in practice.
"""

import os

import pytest

from sfq import _SFTokenAuth


@pytest.fixture(scope="module")
def sf_instance():
    """Create an AuthManager instance for E2E testing."""
    required_env_vars = [
        "SF_INSTANCE_URL",
        "SF_ACCESS_TOKEN",
    ]

    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        pytest.fail(f"Missing required env vars: {', '.join(missing_vars)}")

    sf = _SFTokenAuth(
        instance_url=os.getenv("SF_INSTANCE_URL"),
        access_token=os.getenv("SF_ACCESS_TOKEN"),
    )
    return sf


def test_query(sf_instance):
    """Ensure that a simple query returns the expected results."""
    query = "SELECT Id FROM FeedComment LIMIT 1"
    response = sf_instance.query(query)

    assert response and isinstance(response, dict), (
        f"Query did not return a dict: {response}"
    )

    assert "records" in response, f"No records in response: {response}"
    assert len(response["records"]) == 1, (
        f"Expected 1 record, got {len(response['records'])}: {response}"
    )
    assert "Id" in response["records"][0], (
        f"No Id in record: {response['records'][0]}"
    )
    assert response["records"][0]["Id"], (
        f"Id is empty in record: {response['records'][0]}"
    )
    assert response["done"] is True, f"Query not marked as done: {response}"
    assert "totalSize" in response, f"No totalSize in response: {response}"
    assert response["totalSize"] == 1, (
        f"Expected totalSize 1, got {response['totalSize']}: {response}"
    )
    
