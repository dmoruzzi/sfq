#!/usr/bin/env python3
"""
Pytest script to verify URL decoding functionality in telemetry.
"""

import json
import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# Add the src directory to the path so we can import sfq modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Mock the Grafana credentials fetch before importing telemetry
with patch('http.client.HTTPSConnection') as mock_conn_class:
    mock_conn = MagicMock()
    mock_conn_class.return_value = mock_conn

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = json.dumps({
        "URL": "https://logs-prod-001.grafana.net/loki/api/v1/push",
        "USER_ID": "1234567",
        "API_KEY": "test_api_key"
    }).encode('utf-8')
    mock_conn.getresponse.return_value = mock_response

    from sfq.telemetry import _build_salesforce_payload, _build_payload, _decode_url


@pytest.mark.parametrize(
    "input_url, expected_output",
    [
        ("/services/data/v65.0/query?q=SELECT%20Id%20FROM%20FeedComment%20LIMIT%201",
         "/services/data/v65.0/query?q=SELECT Id FROM FeedComment LIMIT 1"),
        ("/services/oauth2/token?code=test%20code", "/services/oauth2/token?code=test code"),
        (None, None),
        ("", ""),
        ("/simple/path", "/simple/path"),
    ]
)
def test_decode_url(input_url, expected_output):
    """Test the _decode_url function with multiple cases."""
    assert _decode_url(input_url) == expected_output


def test_salesforce_payload_url_decoding():
    """Test that Salesforce payload includes URL-decoded endpoints"""
    ctx = {
        "method": "GET",
        "endpoint": "/services/data/v65.0/query?q=SELECT%20Id%20FROM%20FeedComment%20LIMIT%201",
        "status": 200,
        "duration_ms": 184,
        "request_headers": {
            "User-Agent": "sfq/0.0.53",
            "Sforce-Call-Options": "client=sfq/0.0.53",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": "Bearer test_token"
        },
        "response_body": json.dumps({
            "access_token": "test_access_token",
            "instance_url": "https://test.salesforce.com",
            "token_type": "Bearer"
        })
    }

    payload = _build_salesforce_payload("http.request", ctx, -1)
    expected_endpoint = "/services/data/v65.0/query?q=SELECT Id FROM FeedComment LIMIT 1"
    assert payload["payload"]["endpoint"] == expected_endpoint


def test_main_payload_url_decoding():
    """Test that main telemetry payload includes URL-decoded endpoints"""
    ctx = {
        "method": "GET",
        "endpoint": "/services/data/v65.0/query?q=SELECT%20Id%20FROM%20FeedComment%20LIMIT%201",
        "status": 200,
        "duration_ms": 184,
        "request_headers": {
            "User-Agent": "sfq/0.0.53",
            "Sforce-Call-Options": "client=sfq/0.0.53",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": "Bearer test_token"
        },
        "response_body": {"totalSize": 1, "done": True}
    }

    payload = _build_payload("http.request", ctx, -1)
    expected_endpoint = "/services/data/v65.0/query?q=SELECT Id FROM FeedComment LIMIT 1"
    assert payload["payload"]["endpoint"] == expected_endpoint


# Example test using 5 sample names
@pytest.mark.parametrize(
    "name",
    ["Alice", "Bob", "Charlie", "Diana", "Eve"]
)
def test_sample_names(name):
    """Example test to show parameterized inputs for 5 names"""
    assert isinstance(name, str)
    assert len(name) > 0
