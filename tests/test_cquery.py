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
    result = sf_instance.cquery({'refId': 'SELECT Id FROM Organization LIMIT 1'})

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

    assert result["refId"]["done"]
    assert result["refId"]["totalSize"] == 1
    assert len(result["refId"]["records"]) == 1
    assert result["refId"] == expected

def test_cquery_with_pagination(sf_instance):
    """Ensure that query pagination is functioning"""
    result = sf_instance.cquery({"refId": "SELECT Id FROM FeedComment LIMIT 2200"})

    assert len(result["refId"]["records"]) == 2200
    assert result["refId"]["totalSize"] == 2200
    assert result["refId"]["done"]
