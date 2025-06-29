import logging
import os
import sys
from io import StringIO
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
        pytest.skip(f"Missing required env vars: {', '.join(missing_vars)}")

    sf = SFAuth(
        instance_url=os.getenv("SF_INSTANCE_URL"),
        client_id=os.getenv("SF_CLIENT_ID"),
        client_secret=os.getenv("SF_CLIENT_SECRET"),
        refresh_token=os.getenv("SF_REFRESH_TOKEN"),
    )
    return sf


@pytest.fixture
def capture_logs():
    """
    Fixture to capture logs emitted to 'sfq' logger at TRACE level.
    """
    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(5)

    logger = logging.getLogger("sfq")
    original_level = logger.level
    original_handlers = logger.handlers[:]

    logger.setLevel(5)
    for h in original_handlers:
        logger.removeHandler(h)
    logger.addHandler(handler)

    yield logger, log_stream

    # Teardown - restore original handlers and level
    logger.removeHandler(handler)
    for h in original_handlers:
        logger.addHandler(h)
    logger.setLevel(original_level)


def test_access_token_redacted_in_logs(sf_instance, capture_logs):
    """
    Ensure access tokens are redacted in log output to prevent leakage.
    """
    logger, log_stream = capture_logs

    sf_instance._get_common_headers()

    logger.handlers[0].flush()
    log_contents = log_stream.getvalue()

    assert "access_token" in log_contents, "Expected access_token key in logs"
    assert "'access_token': '********'," in log_contents in log_contents, (
        "Access token was not properly redacted in logs"
    )
