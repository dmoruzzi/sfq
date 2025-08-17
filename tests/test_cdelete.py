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


def test_cdelete(sf_instance):
    """Ensure that a simple delete returns the expected results."""
    query = "SELECT Id FROM FeedComment LIMIT 1"
    response = sf_instance.query(query)

    response_size = len(response["records"])
    if response_size < 1:
        pytest.skip("No FeedComment records to perform delete test.")

    feed_comment_id = response["records"][0]["Id"]

    result = sf_instance.cdelete([feed_comment_id])
    assert result and isinstance(result, list), (
        f"Delete did not return a list: {result}"
    )

    assert result[0].get("success"), f"Delete failed: {result}"
    assert "id" in result[0], f"No ID returned: {result}"


def test_cdelete_batch(sf_instance):
    """Test batching/pagination: Delete multiple FeedComment records and ensure batching works."""
    query = "SELECT Id FROM FeedComment LIMIT 250"
    response = sf_instance.query(query)

    response_size = len(response["records"])
    if response_size < 201:
        pytest.skip("Not enough FeedComment records for batch delete test.")

    feed_comment_ids = [record["Id"] for record in response["records"]]

    result = sf_instance.cdelete(feed_comment_ids)
    assert result and isinstance(result, list), (
        f"Delete did not return a list: {result}"
    )

    assert all(item.get("success") for item in result), f"Delete failed: {result}"

    assert len(result) == response_size, (
        f"Expected {response_size} results, got {len(result)}: {result}"
    )
