#!/usr/bin/env python3
"""
Test script for Grafana Cloud telemetry integration
"""

import os
import sys
import json
import time
from unittest.mock import patch, MagicMock

# Add src to path for testing
sys.path.insert(0, 'src')

def test_credentials_fetching():
    """Test credentials fetching from JSON endpoint"""
    print("Testing credentials fetching...")
    
    # Mock the HTTP response
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = json.dumps({
        "url": "https://logs-prod-001.grafana.net/loki/api/v1/push",
        "USER_ID": 1234567,
        "API_KEY": "test_api_key"
    }).encode()
    
    with patch('http.client.HTTPSConnection') as mock_conn:
        mock_conn_instance = MagicMock()
        mock_conn_instance.getresponse.return_value = mock_response
        mock_conn.return_value = mock_conn_instance
        
        # Set environment variable for test
        os.environ['SFQ_GRAFANACLOUD_URL'] = 'https://test.example.com/creds.json'
        os.environ['SFQ_TELEMETRY'] = '2'
        
        try:
            from sfq.telemetry import TelemetryConfig
            
            config = TelemetryConfig()
            
            # Verify credentials were fetched and parsed correctly
            assert config.user_id == "1234567"
            assert config.api_key == "test_api_key"
            assert config.endpoint == "https://logs-prod-001.grafana.net/loki/api/v1/push"
            assert config.enabled() == True
            
            print("[PASS] Credentials fetching test passed")
        finally:
            # Clean up environment variables
            os.environ.pop('SFQ_GRAFANACLOUD_URL', None)
            os.environ.pop('SFQ_TELEMETRY', None)

def test_payload_format():
    """Test Grafana Loki payload format"""
    print("Testing payload format...")
    
    # Mock credentials
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = json.dumps({
        "url": "https://logs-prod-001.grafana.net/loki/api/v1/push",
        "USER_ID": 1234567,
        "API_KEY": "test_api_key"
    }).encode()
    
    with patch('http.client.HTTPSConnection') as mock_conn:
        mock_conn_instance = MagicMock()
        mock_conn_instance.getresponse.return_value = mock_response
        mock_conn.return_value = mock_conn_instance
        
        os.environ['SFQ_TELEMETRY'] = '1'
        
        try:
            from sfq.telemetry import _build_grafana_payload
            
            # Test payload building
            payload = _build_grafana_payload("test.event", {"key": "value"}, 1)
            
            # Verify Grafana Loki format
            assert "streams" in payload
            assert len(payload["streams"]) == 1
            
            stream = payload["streams"][0]
            assert "stream" in stream
            assert "values" in stream
            
            # Verify stream labels
            assert stream["stream"]["Language"] == "Python"
            assert stream["stream"]["source"] == "Code"
            assert stream["stream"]["sdk"] == "sfq"
            assert stream["stream"]["telemetry_level"] == "1"
            
            # Verify values format (timestamp + JSON log line)
            values = stream["values"][0]
            assert len(values) == 2
            assert isinstance(values[0], str)  # nanosecond timestamp
            
            # Verify log line is valid JSON
            log_line = json.loads(values[1])
            assert "event_type" in log_line
            assert "payload" in log_line
            
            print("[PASS] Payload format test passed")
        except Exception as e:
            print(f"[FAIL] Payload format test failed: {e}")
            raise
        finally:
            os.environ.pop('SFQ_TELEMETRY', None)

def test_authentication():
    """Test Basic Authentication header generation"""
    print("Testing authentication...")
    
    # Mock credentials
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = json.dumps({
        "url": "https://logs-prod-001.grafana.net/loki/api/v1/push",
        "USER_ID": 1234567,
        "API_KEY": "test_api_key"
    }).encode()
    
    with patch('http.client.HTTPSConnection') as mock_conn:
        mock_conn_instance = MagicMock()
        mock_conn_instance.getresponse.return_value = mock_response
        mock_conn.return_value = mock_conn_instance
        
        os.environ['SFQ_TELEMETRY'] = '1'
        
        try:
            from sfq.telemetry import _Sender
            
            # Create sender with test credentials
            sender = _Sender(
                "https://logs-prod-001.grafana.net/loki/api/v1/push",
                "1234567",
                "test_api_key"
            )
            
            # Mock the HTTP connection for sending
            mock_post_response = MagicMock()
            mock_post_response.status = 200
            mock_post_response.read.return_value = b''
            
            with patch('http.client.HTTPSConnection') as mock_post_conn:
                mock_post_conn_instance = MagicMock()
                mock_post_conn_instance.getresponse.return_value = mock_post_response
                mock_post_conn.return_value = mock_post_conn_instance
                
                # Test sending a payload
                test_payload = {
                    "streams": [{
                        "stream": {"test": "stream"},
                        "values": [["1234567890", "test log line"]]
                    }]
                }
                
                sender._post(test_payload)
                
                # Verify the request was made with proper authentication
                call_args = mock_post_conn_instance.request.call_args
                headers = call_args[1]['headers']
                
                assert 'Authorization' in headers
                assert headers['Authorization'].startswith('Basic ')
                
                # Verify Basic Auth encoding
                import base64
                expected_auth = base64.b64encode(b"1234567:test_api_key").decode()
                assert headers['Authorization'] == f"Basic {expected_auth}"
                
                print("[PASS] Authentication test passed")
        except Exception as e:
            print(f"[FAIL] Authentication test failed: {e}")
            raise
        finally:
            os.environ.pop('SFQ_TELEMETRY', None)

def test_error_handling():
    """Test error handling for invalid credentials"""
    print("Testing error handling...")
    
    # Mock failed credentials fetch
    mock_response = MagicMock()
    mock_response.status = 404
    
    with patch('http.client.HTTPSConnection') as mock_conn:
        mock_conn_instance = MagicMock()
        mock_conn_instance.getresponse.return_value = mock_response
        mock_conn.return_value = mock_conn_instance
        
        os.environ['SFQ_GRAFANACLOUD_URL'] = 'https://invalid.example.com/creds.json'
        os.environ['SFQ_TELEMETRY'] = '1'
        
        try:
            from sfq.telemetry import TelemetryConfig
            
            # This should raise an exception
            try:
                config = TelemetryConfig()
                print("✗ Error handling test failed: Expected exception not raised")
                assert False, "Expected RuntimeError was not raised"
            except RuntimeError as e:
                if "Failed to fetch Grafana credentials" in str(e):
                    print("[PASS] Error handling test passed")
                else:
                    print(f"[FAIL] Error handling test failed: Wrong exception message: {e}")
                    assert False, f"Wrong exception message: {e}"
        except Exception as e:
            print(f"✗ Error handling test failed with unexpected error: {e}")
            raise
        finally:
            os.environ.pop('SFQ_GRAFANACLOUD_URL', None)
            os.environ.pop('SFQ_TELEMETRY', None)

def main():
    """Run all tests"""
    print("Running Grafana Cloud telemetry integration tests...\n")
    
    tests = [
        test_credentials_fetching,
        test_payload_format,
        test_authentication,
        test_error_handling
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print(f"Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("[SUCCESS] All tests passed! Grafana Cloud integration is working correctly.")
        return 0
    else:
        print("[FAILURE] Some tests failed. Please check the implementation.")
        return 1

if __name__ == "__main__":
    sys.exit(main())