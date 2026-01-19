#!/usr/bin/env python3
"""
Test script to verify that URL decoding doesn't break existing functionality.
"""

import json
import os
import sys
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
    
    from sfq.telemetry import _build_salesforce_payload, _build_payload

def test_salesforce_payload_without_url_encoding():
    """Test that Salesforce payload works with non-URL-encoded endpoints"""
    print("Testing Salesforce payload with non-URL-encoded endpoints...")
    
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
            "access_token": "test_access_token",
            "instance_url": "https://test.salesforce.com",
            "token_type": "Bearer"
        })
    }
    
    payload = _build_salesforce_payload("oauth2.token", ctx, 1)
    
    # Verify the payload structure
    assert "timestamp" in payload
    assert "sdk" in payload
    assert "payload" in payload
    
    nested_payload = payload["payload"]
    assert "method" in nested_payload
    assert "endpoint" in nested_payload
    assert "status" in nested_payload
    assert "duration_ms" in nested_payload
    assert "access_token" in nested_payload
    assert "instance_url" in nested_payload
    
    # Verify endpoint is unchanged (no URL encoding to decode)
    assert nested_payload["endpoint"] == "/services/oauth2/token"
    
    print("[PASS] Salesforce payload with non-URL-encoded endpoint works correctly")


def test_main_payload_without_url_encoding():
    """Test that main telemetry payload works with non-URL-encoded endpoints"""
    print("\nTesting main telemetry payload with non-URL-encoded endpoints...")
    
    ctx = {
        "method": "GET",
        "endpoint": "/services/data/v65.0/sobjects/Account/001xx000003DGb4AAG",
        "status": 200,
        "duration_ms": 184,
        "request_headers": {
            "User-Agent": "sfq/0.0.53",
            "Sforce-Call-Options": "client=sfq/0.0.53",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": "Bearer test_token"
        }
    }
    
    # Test with level 1 (standard)
    payload = _build_payload("http.request", ctx, 1)
    
    # Verify the payload structure
    assert "timestamp" in payload
    assert "sdk" in payload
    assert "payload" in payload
    
    nested_payload = payload["payload"]
    assert "method" in nested_payload
    # endpoint should not be in level 1 payload
    assert "endpoint" not in nested_payload
    
    print("[PASS] Main telemetry payload level 1 works correctly")
    
    # Test with level -1 (full transparency)
    ctx_with_response = ctx.copy()
    ctx_with_response["response_body"] = {"totalSize": 1, "done": True}
    
    payload_full = _build_payload("http.request", ctx_with_response, -1)
    nested_payload_full = payload_full["payload"]
    
    # For level -1, endpoint should be included and not URL-decoded
    assert "endpoint" in nested_payload_full
    assert nested_payload_full["endpoint"] == "/services/data/v65.0/sobjects/Account/001xx000003DGb4AAG"
    
    print("[PASS] Main telemetry payload level -1 works correctly")
