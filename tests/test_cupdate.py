import os
import random
from datetime import datetime

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


def test_simple_cupdate(sf_instance):
    """Ensure that a simple update returns the expected results."""
    query = "SELECT Id, CommentBody FROM FeedComment LIMIT 1"
    response = sf_instance.query(query)
    assert response and response["records"], "No FeedComment found for test."

    update_dict = dict()
    feed_comment_id = response["records"][0]["Id"]
    update_dict[feed_comment_id] = {"CommentBody": f"Evaluated at {datetime.now()}"}

    result = sf_instance._cupdate(update_dict)

    # Validate the result
    assert result, "CUpdate did not return a result."
    assert isinstance(result, list), "CUpdate result is not a list."
    assert len(result) == 1, "CUpdate result should contain one response."
    assert "compositeResponse" in result[0], (
        "CUpdate response does not contain 'compositeResponse'."
    )
    assert len(result[0]["compositeResponse"]) == 1, (
        "CUpdate response should contain one composite response."
    )
    assert result[0]["compositeResponse"][0]["httpStatusCode"] == 204, (
        "CUpdate did not return HTTP status 204."
    )
    assert result[0]["compositeResponse"][0]["body"] is None, (
        "CUpdate response body should be None."
    )

    # Verify that the update was successful by querying the updated record
    new_query = (
        f"SELECT Id, CommentBody FROM FeedComment WHERE Id = '{feed_comment_id}'"
    )
    updated_response = sf_instance.query(new_query)
    assert updated_response and updated_response["records"], (
        "No updated FeedComment found."
    )
    assert len(updated_response["records"]) == 1, "Expected one updated FeedComment."
    assert (
        updated_response["records"][0]["CommentBody"]
        == update_dict[feed_comment_id]["CommentBody"]
    ), "Updated CommentBody does not match."


def test_cupdate_with_invalid_data(sf_instance):
    """Test cupdate with invalid data to ensure it raises an error."""
    update_dict = {"invalid_id": {"CommentBody": "This should fail"}}

    res = sf_instance._cupdate(update_dict)
    assert res, "CUpdate did not return a result."
    assert isinstance(res, list), "CUpdate result is not a list."
    assert len(res) == 1, "CUpdate result should contain one response."
    assert "compositeResponse" in res[0], (
        "CUpdate response does not contain 'compositeResponse'."
    )
    assert len(res[0]["compositeResponse"]) == 1, (
        "CUpdate response should contain one composite response."
    )
    assert res[0]["compositeResponse"][0]["httpStatusCode"] == 404, (
        "CUpdate did not return HTTP status 404."
    )
    assert res[0]["compositeResponse"][0]["body"][0]["errorCode"] == "NOT_FOUND", (
        "Expected NOT_FOUND error code."
    )
    assert (
        res[0]["compositeResponse"][0]["body"][0]["message"]
        == "The requested resource does not exist"
    ), "Expected NOT_FOUND error message."


def test_cupdate_pagination(sf_instance):
    """Test cupdate with pagination to ensure it handles multiple records."""
    size = 35  # using `/services/data/{self.api_version}/sobjects/{sobject}/{key}` which is 25 per pagination; I want to migrate to Soap for larger 200 batches.
    query = f"SELECT Id, CommentBody FROM FeedComment LIMIT {size}"
    initial_query_response = sf_instance.query(query)

    response_count = len(initial_query_response["records"])
    assert response_count == size, f"Expected {size} records, got {response_count}."
    ids_updated = {record["Id"] for record in initial_query_response["records"]}

    update_dict = dict()
    for record in initial_query_response["records"]:
        feed_comment_id = record["Id"]
        update_dict[feed_comment_id] = {
            "CommentBody": f"sfq/{datetime.now().timestamp()} #{random.randint(1000, 9999)}"
        }

    update_response = sf_instance._cupdate(update_dict)
    assert update_response, "CUpdate did not return a result."
    assert isinstance(update_response, list), "CUpdate result is not a list."

    subset_ids = random.sample(list(ids_updated), min(50, len(ids_updated)))
    subset_id_str = ", ".join([f"'{id_}'" for id_ in subset_ids])
    subset_query = (
        f"SELECT Id, CommentBody FROM FeedComment WHERE Id IN ({subset_id_str})"
    )
    updated_response = sf_instance.query(subset_query)

    # Validate the updated records
    assert updated_response, "Query for updated records did not return a result."
    assert updated_response and updated_response["records"], (
        "No updated FeedComment found."
    )
    assert len(updated_response["records"]) == len(subset_ids), (
        "Expected updated records count does not match subset size."
    )

    # validate that all updated records have the expected CommentBody
    for record in updated_response["records"]:
        expected_comment_body = update_dict[record["Id"]]["CommentBody"]
        assert record["CommentBody"] == expected_comment_body, (
            f"Updated CommentBody for {record['Id']} does not match expected value."
        )
