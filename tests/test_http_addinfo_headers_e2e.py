import http.client
import json
import os
from datetime import datetime, timedelta, timezone
from time import sleep
from urllib.parse import quote

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
        sforce_client="sfq-addinfo-headers-e2e"
    )
    return sf


def test_sfq_addinfo_headers_empty(sf_instance):
    """
    This test is an end-to-end evaluation of SFQ_HEADERS when empty/unset
    """
    pass_test = False
    
    # Ensure SFQ_HEADERS is not set
    os.environ.pop('SFQ_HEADERS', None)

    now = datetime.now(timezone(timedelta(hours=-5))) - timedelta(seconds=20)
    now_iso = now.isoformat(timespec='milliseconds')

    target_query = "SELECT Id FROM ApiEvent WHERE EventDate >= {} LIMIT 1".format(now_iso)
    sf_instance.query(query=target_query)  # Make initial query to generate ApiEvent

    start_time = datetime.now()
    while (datetime.now() - start_time).total_seconds() < 30:
        res = sf_instance.query("SELECT Query, Client, AdditionalInfo FROM ApiEvent WHERE EventDate >= {} LIMIT 200".format(now_iso))
        
        for row in res['records']:
            client = row.get("Client", "")
            query = row.get("Query", "")
            additional_info = row.get("AdditionalInfo", "")

            if client != 'sfq-addinfo-headers-e2e':
                continue

            if query != target_query:
                continue

            # When no SFQ_HEADERS is set, AdditionalInfo should be empty or not contain our custom headers
            if additional_info:
                additional_info_dict = json.loads(additional_info)
                # Our custom headers should not be present
                assert 'custom_key' not in additional_info_dict
                assert 'test_header' not in additional_info_dict
            
            pass_test = True
            break
        
        if pass_test:
            break
        
        sleep(1)  # Brief delay, required for eventual consistency

    assert pass_test


def test_sfq_addinfo_headers_with_values(sf_instance):
    """
    This test is an end-to-end evaluation of SFQ_HEADERS with custom values
    """
    assertions_ran = False
    
    # Set custom addinfo headers
    os.environ['SFQ_HEADERS'] = "custom_key:custom_value|test_header:test_value"
    # Ensure headers are attached
    os.environ['SFQ_ATTACH_CI'] = "true"

    now = datetime.now(timezone(timedelta(hours=-5))) - timedelta(seconds=20)
    now_iso = now.isoformat(timespec='milliseconds')

    target_query = "SELECT Id FROM ApiEvent WHERE EventDate >= {} LIMIT 1".format(now_iso)
    sf_instance.query(query=target_query)  # Make initial query to generate ApiEvent

    start_time = datetime.now()
    while (datetime.now() - start_time).total_seconds() < 30:
        res = sf_instance.query("SELECT Query, Client, AdditionalInfo FROM ApiEvent WHERE EventDate >= {} LIMIT 200".format(now_iso))
        
        for row in res['records']:
            client = row.get("Client", "")
            query = row.get("Query", "")
            additional_info = row.get("AdditionalInfo", "")

            if client != 'sfq-addinfo-headers-e2e':
                continue

            if query != target_query:
                continue

            # Parse the additional info JSON
            additional_info_dict = json.loads(additional_info)
            
            # Verify our custom headers are present
            assert additional_info_dict.get("custom_key") == "custom_value"
            assert additional_info_dict.get("test_header") == "test_value"

            assertions_ran = True
            break
        
        if assertions_ran:
            break
        
        sleep(1)  # Brief delay, required for eventual consistency

    # Clean up environment variables
    os.environ.pop('SFQ_HEADERS', None)
    os.environ.pop('SFQ_ATTACH_CI', None)

    assert assertions_ran