"""
End-to-end tests for the SFTokenAuth module.

These tests run against a real Salesforce instance using environment variables
to ensure the SFTokenAuth functionality works correctly in practice.
"""

import os
from typing import Dict, Any

import pytest

from sfq import SFAuth, _SFTokenAuth


# Environment variable names for Salesforce authentication
SF_ENV_VARS = {
    "INSTANCE_URL": "SF_INSTANCE_URL",
    "CLIENT_ID": "SF_CLIENT_ID",
    "CLIENT_SECRET": "SF_CLIENT_SECRET",
    "REFRESH_TOKEN": "SF_REFRESH_TOKEN"
}


def _validate_required_env_vars() -> None:
    """Validate that all required environment variables are present."""
    missing_vars = [
        env_var for env_var in SF_ENV_VARS.values()
        if not os.getenv(env_var)
    ]
    
    if missing_vars:
        pytest.fail(f"Missing required environment variables: {', '.join(missing_vars)}")


def _get_auth_credentials() -> Dict[str, str]:
    """Get authentication credentials from environment variables."""
    _validate_required_env_vars()
    
    return {
        "instance_url": os.getenv(SF_ENV_VARS["INSTANCE_URL"], ""),
        "client_id": os.getenv(SF_ENV_VARS["CLIENT_ID"], ""),
        "client_secret": os.getenv(SF_ENV_VARS["CLIENT_SECRET"], "").strip(),
        "refresh_token": os.getenv(SF_ENV_VARS["REFRESH_TOKEN"], ""),
    }


@pytest.fixture(scope="module")
def sf_auth_instance() -> SFAuth:
    """Create an SFAuth instance for E2E testing."""
    credentials = _get_auth_credentials()
    return SFAuth(**credentials)


@pytest.fixture(scope="module")
def token_auth_instance(sf_auth_instance: SFAuth) -> _SFTokenAuth:
    """Create an _SFTokenAuth instance using access token from SFAuth."""
    # Ensure we have a valid access token
    sf_auth_instance._refresh_token_if_needed()
    
    return _SFTokenAuth(
        instance_url=sf_auth_instance.instance_url,
        access_token=sf_auth_instance.access_token,
    )


def _validate_query_response(response: Dict[str, Any], expected_record_count: int = 1) -> None:
    """Validate that a query response contains the expected structure and data."""
    # Basic response validation
    assert response is not None, "Query response should not be None"
    assert isinstance(response, dict), f"Query should return a dict, got: {type(response)}"
    
    # Validate response structure
    required_fields = ["records", "done", "totalSize"]
    for field in required_fields:
        assert field in response, f"Response missing required field '{field}': {response}"
    
    # Validate records
    records = response["records"]
    assert len(records) == expected_record_count, (
        f"Expected {expected_record_count} record(s), got {len(records)}: {response}"
    )
    
    # Validate record structure (for expected record count > 0)
    if expected_record_count > 0:
        record = records[0]
        assert "Id" in record, f"Record missing 'Id' field: {record}"
        assert record["Id"], f"Record 'Id' should not be empty: {record}"
    
    # Validate query completion status
    assert response["done"] is True, f"Query should be marked as done: {response}"
    
    # Validate total size
    assert response["totalSize"] == expected_record_count, (
        f"Expected totalSize {expected_record_count}, got {response['totalSize']}: {response}"
    )


def test_basic_query_execution(token_auth_instance: _SFTokenAuth) -> None:
    """Test that a basic SOQL query executes successfully and returns expected results."""
    # Define a simple query that should return at least one record
    query = "SELECT Id FROM FeedComment LIMIT 1"
    
    # Execute the query
    response = token_auth_instance.query(query)
    
    # Validate the response
    _validate_query_response(response, expected_record_count=1)


def test_query_with_multiple_records(token_auth_instance: _SFTokenAuth) -> None:
    """Test query execution that returns multiple records."""
    query = "SELECT Id FROM FeedComment LIMIT 5"
    response = token_auth_instance.query(query)
    
    _validate_query_response(response, expected_record_count=5)
