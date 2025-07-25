import http.client
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import sleep
from urllib.parse import quote

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
    This test ensures the method deletes Apex logs as expected.
    """
    # Check if any Apex logs already exist
    apex_logs = sf_instance.query("SELECT Id FROM ApexLog LIMIT 1")
    if apex_logs.get("records"):
        sf_instance.debug_cleanup(apex_logs=True)
        apex_logs_after = sf_instance.query("SELECT Id FROM ApexLog LIMIT 1")
        assert len(apex_logs_after.get("records", [])) == 0, (
            "Apex logs were not cleaned up successfully."
        )
        return

    # No Apex logs yet; create one via anonymous Apex
    traceflag_query = sf_instance.tooling_query(
        f"SELECT Id FROM TraceFlag WHERE TracedEntityId = '{sf_instance.user_id}' LIMIT 1"
    )
    records = traceflag_query.get("records", [])
    traceflag_id = records[0].get("Id") if records else None

    if not traceflag_id:
        debuglevel_query = sf_instance.tooling_query(
            "SELECT Id FROM DebugLevel WHERE DeveloperName = 'SFDC_DevConsole' LIMIT 1"
        )
        debuglevel_id = debuglevel_query.get("records", [{}])[0].get("Id")

        if not debuglevel_id:
            pytest.fail(
                "DebugLevel 'SFDC_DevConsole' not found. Please create it in your Salesforce org."
            )

        traceflag_payload = {
            "DebugLevelId": debuglevel_id,
            "LogType": "USER_DEBUG",
            "TracedEntityId": sf_instance.user_id,
            "StartDate": datetime.now(timezone.utc).isoformat(),
            "ExpirationDate": (
                datetime.now(timezone.utc) + timedelta(minutes=5)
            ).isoformat(),
        }
        resp = sf_instance._create(
            sobject="TraceFlag", insert_list=[traceflag_payload], api_type="tooling"
        )
        with open("debug_payload.json", "w") as f:
            f.write(json.dumps(resp, indent=2))
        with open("debug_payload.json", "w") as f:
            f.write(json.dumps(traceflag_payload, indent=2))

        traceflag_query = sf_instance.tooling_query(
            f"SELECT Id FROM TraceFlag WHERE TracedEntityId = '{sf_instance.user_id}' LIMIT 1"
        )
        records = traceflag_query.get("records", [])
        traceflag_id = records[0].get("Id") if records else None

        if not traceflag_id:
            pytest.fail("Failed to create TraceFlag.")

    else:
        # Update the existing TraceFlag's dates
        starttime = datetime.now(timezone.utc).isoformat()
        endtime = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        payload = json.dumps({"StartDate": starttime, "ExpirationDate": endtime})

        conn = http.client.HTTPSConnection(
            sf_instance.instance_url.replace("https://", "")
        )
        conn.request(
            "PATCH",
            f"/services/data/v64.0/tooling/sobjects/TraceFlag/{traceflag_id}",
            body=payload,
            headers={
                "Authorization": f"Bearer {sf_instance.access_token}",
                "Content-Type": "application/json",
            },
        )
        response = conn.getresponse()
        resp_body = response.read().decode()

        if response.status not in (200, 204):
            pytest.fail(
                f"Failed to update TraceFlag: {response.reason} | Body: {resp_body}"
            )

    # Now generate an Apex log
    anonymous_body = f"System.debug('Hello from {sf_instance.user_agent}! :)');"
    encoded_body = quote(anonymous_body, safe="")
    conn = http.client.HTTPSConnection(sf_instance.instance_url.replace("https://", ""))
    conn.request(
        "GET",
        f"/services/data/v64.0/tooling/executeAnonymous/?anonymousBody={encoded_body}",
        headers={
            "Authorization": f"Bearer {sf_instance.access_token}",
            "Content-Type": "application/json",
        },
    )
    response = conn.getresponse()
    if response.status != 200:
        pytest.fail(f"Failed to execute anonymous Apex: {response.reason}")

    if already_executed:
        pytest.fail(
            "ApexLog creation failed or already attempted. Skipping recursion to avoid infinite loop."
        )

    sleep(1)  # Race condition mitigation
    return test_debug_cleanup(sf_instance, already_executed=True)
