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

    # Allow empty string, only fail if it's not set at all
    missing_vars = [var for var in required_env_vars if os.getenv(var) is None]
    if missing_vars:
        pytest.fail(f"Missing required env vars: {', '.join(missing_vars)}")

    sf = SFAuth(
        instance_url=os.getenv("SF_INSTANCE_URL"),
        client_id=os.getenv("SF_CLIENT_ID"),
        client_secret=os.getenv("SF_CLIENT_SECRET").strip(),
        refresh_token=os.getenv("SF_REFRESH_TOKEN"),
    )
    return sf

def get_feed_item_id(sf_instance):
    """Helper to fetch a valid FeedItemId for tests."""
    response = sf_instance.query("SELECT Id FROM FeedItem LIMIT 1")
    assert response and response["records"], "No FeedItem found for test."
    return response["records"][0]["Id"]


def test_feed_comment_insertion(sf_instance):
    """Ensure that a simple insert returns the expected results."""
    feed_item_id = get_feed_item_id(sf_instance)
    comment = {
        "FeedItemId": feed_item_id,
        "CommentBody": f"Test comment via {sf_instance.user_agent}",
    }
    result = sf_instance._create("FeedComment", [comment])
    assert result and isinstance(result, list), (
        f"Create did not return a list: {result}"
    )
    assert result[0].get("success"), f"Insert failed: {result}"
    assert "id" in result[0], f"No ID returned: {result}"


def test_feed_comment_batch_insertion(sf_instance):
    """Test batching/pagination: Insert multiple FeedComment records and ensure batching works."""
    feed_item_id = get_feed_item_id(sf_instance)
    comments = [
        {
            "FeedItemId": feed_item_id,
            "CommentBody": f"Batch comment {i} via {sf_instance.user_agent}",
        }
        for i in range(250)
    ]
    results = sf_instance._create("FeedComment", comments)
    assert results and isinstance(results, list), (
        f"Batch create did not return a list: {results}"
    )
    assert len(results) == 250, f"Expected 250 results, got {len(results)}"
    successes = [
        r
        for r in results
        if str(r.get("success")).lower() == "true" or r.get("success") is True
    ]
    assert len(successes) == 250, f"Not all inserts succeeded: {len(successes)}"
    for r in results:
        assert "id" in r, f"Result missing 'id': {r}"
