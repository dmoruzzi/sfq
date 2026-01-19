import json
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

# Add src to sys.path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Mock Grafana credentials before importing telemetry
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

    from sfq.telemetry import (
        emit_salesforce_telemetry,
        _build_salesforce_payload,
        _send_salesforce_telemetry,
        get_config
    )


@pytest.fixture(autouse=True)
def setup_test_telemetry():
    """Force enable telemetry for all tests."""
    config = get_config()
    config.level = 1
    config.sampling = 1.0
    return config


def test_build_salesforce_payload():
    """Test building Salesforce telemetry payload."""
    ctx = {
        "method": "POST",
        "endpoint": "/services/oauth2/token",
        "status": 200,
        "duration_ms": 492,
        "request_headers": {
            "User-Agent": "sfq/0.0.53",
            "Sforce-Call-Options": "client=sfq/0.0.53",
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded"
        },
        "response_body": json.dumps({
            "access_token": "00Daa0000000000000!Egrz59v00vHYP8jKlwyOgDmDE02nfcFB4sYs59DUwsbnq8rhdG29cT4XEyDE8YscMuROhx0s3CUsj7VAT2lzkeaCVgngn46a",
            "signature": "XPeCuEubN/xIu9regNF8effn8WgnIcR2oLpqftEZgqw=",
            "scope": "refresh_token web api",
            "instance_url": "https://dmoruzzi-dev-ed.trailblaze.my.salesforce.com",
            "id": "https://login.salesforce.com/id/00Daa0000000000000EAQ/005aj0000031QinAAE",
            "token_type": "Bearer",
            "issued_at": "1768812885587"
        })
    }

    payload = _build_salesforce_payload("oauth2.token", ctx, 1)

    # Top-level keys
    for key in ["timestamp", "sdk", "sdk_version", "event_type", "client_id",
                "telemetry_level", "trace_id", "span", "log_level", "payload"]:
        assert key in payload

    nested = payload["payload"]
    for key in ["method", "endpoint", "status", "duration_ms", "access_token",
                "instance_url", "environment"]:
        assert key in nested

    assert nested["access_token"].startswith("00Daa0000000000000!")
    assert nested["instance_url"] == "https://dmoruzzi-dev-ed.trailblaze.my.salesforce.com"


def test_send_salesforce_telemetry():
    """Test sending telemetry without actual network calls."""
    payload = {
        "timestamp": "2026-01-19T08:54:45Z",
        "sdk": "sfq",
        "sdk_version": "0.0.48",
        "event_type": "oauth2.token",
        "client_id": "test_client_id",
        "telemetry_level": 1,
        "trace_id": "test_trace_id",
        "span": "default",
        "log_level": "INFO",
        "payload": {
            "method": "POST",
            "endpoint": "/services/oauth2/token",
            "status": 200,
            "duration_ms": 492,
            "access_token": "test_access_token",
            "instance_url": "https://test.salesforce.com"
        }
    }

    with patch('http.client.HTTPSConnection') as mock_conn_class:
        mock_conn = MagicMock()
        mock_conn_class.return_value = mock_conn
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"success": true}'
        mock_conn.getresponse.return_value = mock_response

        _send_salesforce_telemetry(payload, "test_access_token", "https://test.salesforce.com")

        # Validate HTTP request
        mock_conn_class.assert_called_once()
        mock_conn.request.assert_called_once()
        method, endpoint = mock_conn.request.call_args[0][:2]
        assert method == "POST"
        assert endpoint == "/services/data/v1/telemetry"


def test_emit_salesforce_telemetry():
    """Test the emit_salesforce_telemetry function."""
    ctx = {
        "method": "POST",
        "endpoint": "/services/oauth2/token",
        "status": 200,
        "duration_ms": 492,
        "request_headers": {
            "User-Agent": "sfq/0.0.53",
            "Sforce-Call-Options": "client=sfq/0.0.53",
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded"
        },
        "response_body": json.dumps({
            "access_token": "00Daa0000000000000!Egrz59v00vHYP8jKlwyOgDmDE02nfcFB4sYs59DUwsbnq8rhdG29cT4XEyDE8YscMuROhx0s3CUsj7VAT2lzkeaCVgngn46a",
            "instance_url": "https://dmoruzzi-dev-ed.trailblaze.my.salesforce.com"
        })
    }

    with patch('sfq.telemetry._build_salesforce_payload') as mock_build, \
         patch('sfq.telemetry._send_salesforce_telemetry') as mock_send, \
         patch('sfq.telemetry.get_config') as mock_config:

        # Mock config
        mock_config.return_value.enabled.return_value = True
        mock_config.return_value.sampling = 1.0
        mock_config.return_value.level = 1

        mock_build.return_value = {"test": "payload"}

        emit_salesforce_telemetry("oauth2.token", ctx)

        mock_build.assert_called_once_with("oauth2.token", ctx, 1)
        mock_send.assert_called_once()
