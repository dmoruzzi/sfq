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
        sforce_client="sfq-ci-headers-e2e"
    )
    return sf


def test_sfq_attach_ci_false(sf_instance):
    """
    This test is an end-to-end evaluation of the 'SFQ_ATTACH_CI' when False
    """
    pass_test = False
    
    os.environ['SFQ_ATTACH_CI'] = "false"

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

            if client != 'sfq-ci-headers-e2e':
                continue

            if query != target_query:
                continue

            assert '{}' == additional_info
            pass_test = True
            break
        
        if pass_test:
            break
        
        sleep(1)  # Brief delay, required for eventual consistency

    assert pass_test


def test_sfq_attach_ci_true(sf_instance):
    """
    This test is an end-to-end evaluation of the 'SFQ_ATTACH_CI' when False
    """
    assertions_ran = False

    os.environ['SFQ_ATTACH_CI'] = "true"
    github_actions = os.getenv("GITHUB_ACTIONS", "")
    if not github_actions:
        os.environ["GITHUB_RUN_ID"] = "1234567890"
        os.environ["RUNNER_OS"] = "Linux"
        os.environ["GITHUB_ACTIONS"] = "true"

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

            if client != 'sfq-ci-headers-e2e':
                continue

            if query != target_query:
                continue

            additional_info_dict = json.loads(additional_info)
            assert additional_info_dict.get("ci_provider") == "github"
            assert additional_info_dict.get("run_id") == os.getenv("GITHUB_RUN_ID")
            assert additional_info_dict.get("runner_os") == os.getenv("RUNNER_OS")

            assertions_ran = True
            break
        
        if assertions_ran:
            break
        
        sleep(1)  # Brief delay, required for eventual consistency

    assert assertions_ran

def test_ci_headers_org_repo_validation(sf_instance):
    """
    This test is an end-to-end evaluation of the 'SFQ_ATTACH_CI' with org/repo info
    """
    assertions_ran = False

    test_key = "repository"
    test_value_input = "dmoruzzi/sfq"
    test_value_output = test_value_input.replace("/", "_")

    os.environ["SFQ_HEADERS"] = f"{test_key}:{test_value_input}"

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

            if client != 'sfq-ci-headers-e2e':
                continue

            if query != target_query:
                continue

            additional_info_dict = json.loads(additional_info)
            assert additional_info_dict.get(test_key) == test_value_output

            assertions_ran = True
            break
        
        if assertions_ran:
            break
        
        sleep(1)  # Brief delay, required for eventual consistency

    assert assertions_ran