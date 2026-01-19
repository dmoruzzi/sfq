import os
import uuid
import time

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


def test_cquery_with_pagination(sf_instance):
    """Ensure that query pagination is functioning"""
    result = sf_instance.cquery(
        {
            "refId": "SELECT Id FROM FeedComment LIMIT 2200",
            "refCount": "SELECT COUNT() FROM FeedComment LIMIT 2200",
        }
    )

    if result["refCount"]["totalSize"] < 2200:
        # Create the required number of FeedComment records
        required_records = 3500 - result["refCount"]["totalSize"]
        
        # Fetch a valid FeedItemId to use for creating FeedComment records
        feed_item_result = sf_instance.query("SELECT Id FROM FeedItem LIMIT 1")
        if not feed_item_result or not feed_item_result.get("records"):
            pytest.skip("No FeedItem records available to create FeedComment records")
        
        feed_item_id = feed_item_result["records"][0]["Id"]
        
        # Create FeedComment records in a batch
        records_to_create = [
            {
                "CommentBody": (
                    f"cquery-pagination-test "
                    f"#{_} "
                    f"{uuid.uuid4()} | "
                    f"{time.time()}"
                ),
                "FeedItemId": feed_item_id
            }
            for _ in range(required_records)
        ]
        created_records = sf_instance._create("FeedComment", records_to_create)
        
        # Re-run the query after creating records
        result = sf_instance.cquery(
            {
                "refId": "SELECT Id FROM FeedComment LIMIT 2200",
                "refCount": "SELECT COUNT() FROM FeedComment LIMIT 2200",
            }
        )

    assert len(result["refId"]["records"]) == 2200
    assert result["refId"]["totalSize"] == 2200
    assert result["refId"]["done"]
