import json
import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# Add the src directory to the path so we can import sfq modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

@pytest.fixture
def mock_grafana_credentials():
    """Mock the HTTPSConnection for Grafana credentials"""
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

        yield mock_conn_class

@pytest.fixture
def telemetry_module(mock_grafana_credentials):
    """Import telemetry after mocking Grafana credentials"""
    from sfq.telemetry import _build_payload
    return _build_payload

def test_url_decoding_in_payload(telemetry_module):
    """Verify that URL-encoded endpoints are properly decoded in telemetry payloads"""
    _build_payload = telemetry_module

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
        "response_body": {
            "totalSize": 1,
            "done": True,
            "records": [{
                "attributes": {
                    "type": "FeedComment",
                    "url": "/services/data/v65.0/sobjects/FeedComment/0D7aj0000005TbECAU"
                },
                "Id": "0D7aj0000005TbECAU"
            }]
        },
        "response_headers": {
            "Date": "Mon, 19 Jan 2026 09:06:10 GMT",
            "Vary": "Accept-Encoding",
            "Set-Cookie": "test_cookie",
            "X-Content-Type-Options": "nosniff",
            "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
            "X-Robots-Tag": "none",
            "Cache-Control": "no-cache,must-revalidate,max-age=0,no-store,private",
            "Sforce-Limit-Info": "api-usage=5252/15000",
            "Content-Type": "application/json;charset=UTF-8",
            "Transfer-Encoding": "chunked"
        }
    }

    # SFQ_TELEMETRY = -1 for full transparency
    payload = _build_payload("http.request", ctx, -1)
    endpoint = payload["payload"]["endpoint"]

    expected_endpoint = "/services/data/v65.0/query?q=SELECT Id FROM FeedComment LIMIT 1"
    
    assert endpoint == expected_endpoint, (
        f"Endpoint is not properly URL-decoded.\n"
        f"Actual:   {endpoint}\nExpected: {expected_endpoint}"
    )
