import os
import sys
from pathlib import Path

import pytest

# --- Setup local import path ---
project_root = Path(__file__).resolve().parents[1]
src_path = project_root / "src"
sys.path.insert(0, str(src_path))
from sfq import SFAuth  # noqa: E402


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
        client_secret=os.getenv("SF_CLIENT_SECRET"),
        refresh_token=os.getenv("SF_REFRESH_TOKEN"),
    )
    return sf


def test_simple_query(sf_instance):
    """Ensure that a simple query returns the expected results."""
    result = sf_instance.query("SELECT Id FROM Organization LIMIT 1")

    sf_api_version = sf_instance.api_version
    expected = {
        "totalSize": 1,
        "done": True,
        "records": [
            {
                "attributes": {
                    "type": "Organization",
                    "url": f"/services/data/{sf_api_version}/sobjects/Organization/00Daj000004ej9WEAQ",
                },
                "Id": "00Daj000004ej9WEAQ",
            }
        ],
    }

    assert result["done"]
    assert result["totalSize"] == 1
    assert len(result["records"]) == 1
    assert result == expected


def test_simple_query_with_tooling(sf_instance):
    """Ensure that a simple query returns the expected results."""
    result = sf_instance.query(
        "SELECT ProdSuffixType FROM OrgDomainLog LIMIT 1", tooling=True
    )

    sf_api_version = sf_instance.api_version
    expected = {
        "size": 1,
        "totalSize": 1,
        "done": True,
        "queryLocator": None,
        "entityTypeName": "OrgDomainLog",
        "records": [
            {
                "attributes": {
                    "type": "OrgDomainLog",
                    "url": f"/services/data/{sf_api_version}/tooling/sobjects/OrgDomainLog/9UXaj000000p9inGAA",
                },
                "ProdSuffixType": "MySalesforce",
            }
        ],
    }

    assert result["done"]
    assert result["totalSize"] == 1
    assert len(result["records"]) == 1
    assert result == expected


def test_query_with_pagination(sf_instance):
    """Ensure that query pagination is functioning"""
    current_count = sf_instance.query("SELECT Count() FROM FeedComment LIMIT 2200")[
        "totalSize"
    ]
    if current_count < 2200:
        feedItemId = sf_instance.query("SELECT Id FROM FeedItem LIMIT 1")["records"][0][
            "Id"
        ]
        required_count = 2200 - current_count + 250
        comments = [
            {
                "FeedItemId": feedItemId,
                "CommentBody": f"Test comment {i} via {sf_instance.user_agent}",
            }
            for i in range(required_count)
        ]

        results = sf_instance.create("FeedComment", comments)
        assert results and isinstance(results, list), (
            f"Batch create did not return a list: {results}"
        )

        current_count = sf_instance.query("SELECT Count() FROM FeedComment LIMIT 2200")[
            "totalSize"
        ]

    assert current_count >= 2200, (
        "Not enough FeedComment records for pagination test exist, despite recent creation..."
    )

    result = sf_instance.query("SELECT Id FROM FeedComment LIMIT 2200")

    assert len(result["records"]) == 2200
    assert result["totalSize"] == 2200
    assert result["done"]
