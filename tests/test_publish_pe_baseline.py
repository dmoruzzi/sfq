import os
import http.client
import json
from urllib.parse import urlparse
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
        instance_url=os.getenv("SF_INSTANCE_URL") or "",
        client_id=os.getenv("SF_CLIENT_ID") or "",
        client_secret=(os.getenv("SF_CLIENT_SECRET") or "").strip(),
        refresh_token=os.getenv("SF_REFRESH_TOKEN") or "",
    )
    ensure_sfq_pe(sf)
    return sf

pe_available = False

def ensure_sfq_pe(sf_instance: SFAuth) -> None:
    """Ensure that sfq__e is available; if not, all Platform Event tests are skipped"""
    sf_instance._refresh_token_if_needed()
    instance_url = sf_instance.instance_url
    access_token = sf_instance.access_token
    if not access_token:
        pytest.skip("No access token available")

    parsed = urlparse(instance_url.rstrip('/'))
    host = parsed.netloc
    endpoint = f"/services/data/{sf_instance.api_version}/sobjects/sfq__e/describe"

    conn = http.client.HTTPSConnection(host)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json"
    }
    conn.request("GET", endpoint, headers=headers)
    response = conn.getresponse()
    response_body = response.read()
    response_str = response_body.decode('utf-8')
    data = json.loads(response_str)
    conn.close()

    global pe_available

    if response.status != 200:
        pe_available = False
        pytest.skip(f"sfq__e SObject not available: HTTP {response.status}")
    else:
        fields = data.get('fields', [])
        has_text_c = any(field.get('name') == 'text__c' for field in fields)
        pe_available = has_text_c
        

def test_baseline_permission_test(sf_instance: SFAuth) -> None:
    if not pe_available:
        pytest.skip("sfq__e is unavailable, cannot evaluate test")

    sf_instance._refresh_token_if_needed()  # ensure access token
    instance_url = sf_instance.instance_url
    access_token = sf_instance.access_token
    if not access_token:
        pytest.fail("No access token available for publish")

    parsed = urlparse(instance_url.rstrip('/'))
    host = parsed.netloc
    endpoint = f"/services/data/{sf_instance.api_version}/sobjects/sfq__e/"

    payload = {
        "text__c": f"test_publish_pe_baseline at {datetime.now().isoformat()}"
    }
    payload_json = json.dumps(payload)

    conn = http.client.HTTPSConnection(host)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Content-Length": len(payload_json)
    }
    conn.request("POST", endpoint, body=payload_json, headers=headers)
    response = conn.getresponse()
    response_body = response.read()
    conn.close()

    assert response.status == 201, f"Publish failed: HTTP {response.status}, body: {response_body.decode('utf-8')}"

    response_str = response_body.decode('utf-8')
    data = json.loads(response_str)
    assert 'id' in data, f"No id in response: {response_str}"
    assert data['success'] == True, f"Publish not successful: {response_str}"
