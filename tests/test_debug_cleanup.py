import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

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

def test_debug_cleanup(sf_instance, already_executed: bool = False):
    """
    Test the debug_cleanup method of SFAuth.
    This test will check if the method can be called without errors.
    """
    apex_logs = sf_instance.query("SELECT Id FROM ApexLog LIMIT 1")
    apex_log_count = len(apex_logs.get("records", []))
    if apex_log_count == 0:
        # OK, so we need to create an Apex log to test cleanup
        # To do this, let's execute a simple Apex anonymous block
        import http.client
        conn = http.client.HTTPSConnection(sf_instance.instance_url.replace("https://", ""))
        conn.request(
            "GET",
            '/services/data/v64.0/tooling/executeAnonymous/?anonymousBody=Long%20currentUnixTime%20%3D%20DateTime.now().getTime()%20%2F%201000%3B',
            headers={
                "Authorization": f"Bearer {sf_instance.access_token}",
                "Content-Type": "application/json"
            }
        )
        response = conn.getresponse()
        if response.status != http.client.OK:
            pytest.fail(f"Failed to create Apex logs: {response.reason}")
        if already_executed:
            pytest.fail("ApexLog creation failed, cannot evaluate Apex log test.")
        return test_debug_cleanup(sf_instance, already_executed=True)

    sf_instance.debug_cleanup(apex_logs=True)

    apex_logs = sf_instance.query("SELECT Id FROM ApexLog LIMIT 1")
    apex_log_count = len(apex_logs.get("records", []))
    assert apex_log_count == 0, "Apex logs were not cleaned up successfully."