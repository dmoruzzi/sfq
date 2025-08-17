import os
import re
from unittest.mock import patch
from urllib.parse import quote

import pytest
from pytest import fail

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

    return SFAuth(
        instance_url=os.getenv("SF_INSTANCE_URL"),
        client_id=os.getenv("SF_CLIENT_ID"),
        client_secret=os.getenv("SF_CLIENT_SECRET").strip(),
        refresh_token=os.getenv("SF_REFRESH_TOKEN"),
    )


def test_open_frontdoor(sf_instance):
    with patch("webbrowser.open") as mock_open:
        try:
            sf_instance.open_frontdoor()
            sid = quote(sf_instance.access_token, safe="")
            expected_url = f"{sf_instance.instance_url}/secur/frontdoor.jsp?sid={sid}"
            mock_open.assert_called_once_with(expected_url)
        except AssertionError as e:
            msg = str(e)
            if sf_instance.access_token and sf_instance.access_token in msg:
                msg = msg.replace(sf_instance.access_token, "[REDACTED]")
            msg = re.sub(r"([?&]sid=)[^&\s]+", r"\1[REDACTED]", msg)
            fail(f"Assertion failed: {msg}")
