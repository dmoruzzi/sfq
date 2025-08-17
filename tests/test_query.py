import os

import pytest

from sfq import SFAuth


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


def test_simple_query(sf_instance):
    """Ensure that a simple query returns the expected results."""
    result = sf_instance.cquery({"refId": "SELECT Id FROM Organization LIMIT 1"})

    sf_api_version = sf_instance.api_version
    org_id = sf_instance.org_id
    
    expected = {
        "totalSize": 1,
        "done": True,
        "records": [
            {
                "attributes": {
                    "type": "Organization",
                    "url": f"/services/data/{sf_api_version}/sobjects/Organization/{org_id}",
                },
                "Id": f"{org_id}",
            }
        ],
    }

    assert result["refId"]["done"]
    assert result["refId"]["totalSize"] == 1
    assert len(result["refId"]["records"]) == 1
    assert result["refId"] == expected


def test_query_with_pagination(sf_instance):
    """Ensure that query pagination is functioning"""
    result = sf_instance.query("SELECT Count() FROM FeedComment LIMIT 2200")
    if result['totalSize'] != 2200:
        pytest.skip("Not enough FeedComments to evaluate query pagination")

    result = sf_instance.query("SELECT Id FROM FeedComment LIMIT 2200")

    assert len(result["records"]) == 2200
    assert result["totalSize"] == 2200
    assert result["done"]
