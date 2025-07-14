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


def test_limits_api(sf_instance):
    """
    Test the limits API endpoint.
    """

    limits = sf_instance.limits()

    assert isinstance(limits, dict)
    assert "DailyApiRequests" in limits.keys()
