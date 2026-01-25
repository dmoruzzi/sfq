#!/usr/bin/env python3
"""
Test script for DataDog telemetry integration
"""

import os
import sys
import json
import base64
from unittest.mock import patch, MagicMock

# Add src to path for testing
sys.path.insert(0, 'src')

def test_datadog_provider_detection():
    """Test DataDog provider detection from credentials"""
    print("Testing DataDog provider detection...")
    
    # Mock DataDog credentials
    datadog_creds = {
        "URL": "https://http-intake.logs.us3.datadoghq.com/api/v2/logs",
        "DD_API_KEY": "test_datadog_api_key",
        "PROVIDER": "DATADOG"
    }
    
    with patch('sfq.telemetry.TelemetryConfig._fetch_grafana_credentials') as mock_fetch:
        mock_fetch.return_value = datadog_creds
        
        os.environ['SFQ_TELEMETRY'] = '2'
        
        try:
            from sfq.telemetry import TelemetryConfig
            
            config = TelemetryConfig()
            
            # Verify provider detection
            assert config.provider == "DATADOG", f"Expected DATADOG, got {config.provider}"
            assert config.dd_api_key == "test_datadog_api_key", f"Expected test_datadog_api_key, got {config.dd_api_key}"
            assert config.api_key == "test_datadog_api_key", "API key should be set to dd_api_key"
            assert config.user_id is None, "User ID should be None for DataDog"
            
            print("[PASS] DataDog provider detection test passed")
            
        except Exception as e:
            print(f"✗ DataDog provider detection test failed: {e}")
            return False
        finally:
            os.environ.pop('SFQ_TELEMETRY', None)

def test_grafana_backward_compatibility():
    """Test that Grafana Cloud still works (backward compatibility)"""
    print("Testing Grafana Cloud backward compatibility...")
    
    # Mock Grafana credentials (no PROVIDER field)
    grafana_creds = {
        "URL": "https://logs-prod-001.grafana.net/loki/api/v1/push",
        "USER_ID": "1234567",
        "API_KEY": "test_grafana_api_key"
    }
    
    with patch('sfq.telemetry.TelemetryConfig._fetch_grafana_credentials') as mock_fetch:
        mock_fetch.return_value = grafana_creds
        
        os.environ['SFQ_TELEMETRY'] = '2'
        
        try:
            from sfq.telemetry import TelemetryConfig
            
            config = TelemetryConfig()
            
            # Verify default provider (Grafana)
            assert config.provider == "GRAFANA", f"Expected GRAFANA, got {config.provider}"
            assert config.user_id == "1234567", f"Expected 1234567, got {config.user_id}"
            assert config.api_key == "test_grafana_api_key", f"Expected test_grafana_api_key, got {config.api_key}"
            assert config.dd_api_key is None, "dd_api_key should be None for Grafana"
            
            print("[PASS] Grafana backward compatibility test passed")
            
        except Exception as e:
            print(f"✗ Grafana backward compatibility test failed: {e}")
            return False
        finally:
            os.environ.pop('SFQ_TELEMETRY', None)

def test_datadog_payload_format():
    """Test DataDog payload format"""
    print("Testing DataDog payload format...")
    
    # Mock DataDog credentials
    datadog_creds = {
        "URL": "https://http-intake.logs.us3.datadoghq.com/api/v2/logs",
        "DD_API_KEY": "test_datadog_api_key",
        "PROVIDER": "DATADOG"
    }
    
    with patch('sfq.telemetry.TelemetryConfig._fetch_grafana_credentials') as mock_fetch:
        mock_fetch.return_value = datadog_creds
        
        os.environ['SFQ_TELEMETRY'] = '1'
        
        try:
            from sfq.telemetry import _build_datadog_payload
            
            # Test payload building
            test_ctx = {
                "method": "GET",
                "endpoint": "/test/endpoint",
                "status": 200,
                "sf": {
                    "org_id": "00D123456789ABCDEF"
                }
            }
            
            payload = _build_datadog_payload("test.event", test_ctx, 1)
            
            # Verify DataDog format
            assert "ddsource" in payload, "Missing ddsource field"
            assert "service" in payload, "Missing service field"
            assert "hostname" in payload, "Missing hostname field"
            assert "message" in payload, "Missing message field"
            assert "ddtags" in payload, "Missing ddtags field"
            
            # Verify defaults
            assert payload["ddsource"] == "salesforce", f"Expected salesforce, got {payload['ddsource']}"
            assert payload["service"] == "salesforce", f"Expected salesforce, got {payload['service']}"
            assert payload["hostname"] == "00D123456789ABCDEF", f"Expected org_id, got {payload['hostname']}"
            assert payload["ddtags"] == "source:salesforce", f"Expected source:salesforce, got {payload['ddtags']}"
            
            # Verify message is an object (not JSON string)
            message = payload["message"]
            assert isinstance(message, dict), f"Message should be a dict/object, got {type(message)}"
            assert "event_type" in message, "Message should contain event_type"
            assert message["event_type"] == "test.event", "Event type should be preserved"
            
            print("[PASS] DataDog payload format test passed")
            
        except Exception as e:
            print(f"✗ DataDog payload format test failed: {e}")
            return False
        finally:
            os.environ.pop('SFQ_TELEMETRY', None)

def test_datadog_environment_overrides():
    """Test DataDog environment variable overrides"""
    print("Testing DataDog environment variable overrides...")
    
    # Mock DataDog credentials
    datadog_creds = {
        "URL": "https://http-intake.logs.us3.datadoghq.com/api/v2/logs",
        "DD_API_KEY": "test_datadog_api_key",
        "PROVIDER": "DATADOG"
    }
    
    with patch('sfq.telemetry.TelemetryConfig._fetch_grafana_credentials') as mock_fetch:
        mock_fetch.return_value = datadog_creds
        
        # Set environment overrides
        os.environ['SFQ_TELEMETRY'] = '1'
        os.environ['DD_SOURCE'] = 'custom_source'
        os.environ['DD_SERVICE'] = 'custom_service'
        os.environ['DD_TAGS'] = 'env:test,type:unit'
        
        try:
            from sfq.telemetry import _build_datadog_payload
            
            # Test payload building with overrides
            test_ctx = {"method": "GET", "endpoint": "/test"}
            payload = _build_datadog_payload("test.event", test_ctx, 1)
            
            # Verify environment overrides applied
            assert payload["ddsource"] == "custom_source", f"Expected custom_source, got {payload['ddsource']}"
            assert payload["service"] == "custom_service", f"Expected custom_service, got {payload['service']}"
            assert "env:test" in payload["ddtags"], "DD_TAGS override should be applied"
            assert "type:unit" in payload["ddtags"], "DD_TAGS override should be applied"
            
            print("[PASS] DataDog environment overrides test passed")
            
        except Exception as e:
            print(f"✗ DataDog environment overrides test failed: {e}")
            return False
        finally:
            os.environ.pop('SFQ_TELEMETRY', None)
            os.environ.pop('DD_SOURCE', None)
            os.environ.pop('DD_SERVICE', None)
            os.environ.pop('DD_TAGS', None)

def test_datadog_hostname_logic():
    """Test DataDog hostname logic based on telemetry level"""
    print("Testing DataDog hostname logic...")
    
    # Mock DataDog credentials
    datadog_creds = {
        "URL": "https://http-intake.logs.us3.datadoghq.com/api/v2/logs",
        "DD_API_KEY": "test_datadog_api_key",
        "PROVIDER": "DATADOG"
    }
    
    with patch('sfq.telemetry.TelemetryConfig._fetch_grafana_credentials') as mock_fetch:
        mock_fetch.return_value = datadog_creds
        
        os.environ['SFQ_TELEMETRY'] = '2'
        
        try:
            from sfq.telemetry import _build_datadog_payload
            
            # Test level 2/-1: should use instance_url
            ctx_level_2 = {
                "sf": {
                    "instance_url": "https://test.salesforce.com",
                    "org_id": "00D123456789ABCDEF"
                }
            }
            
            payload_level_2 = _build_datadog_payload("test.event", ctx_level_2, 2)
            assert payload_level_2["hostname"] == "https://test.salesforce.com", "Level 2 should use instance_url"
            
            payload_level_neg1 = _build_datadog_payload("test.event", ctx_level_2, -1)
            assert payload_level_neg1["hostname"] == "https://test.salesforce.com", "Level -1 should use instance_url"
            
            # Test level 1: should use org_id
            ctx_level_1 = {
                "sf": {
                    "org_id": "00D123456789ABCDEF"
                }
            }
            
            payload_level_1 = _build_datadog_payload("test.event", ctx_level_1, 1)
            assert payload_level_1["hostname"] == "00D123456789ABCDEF", "Level 1 should use org_id"
            
            # Test no sf context: should be empty
            ctx_no_sf = {"other": "data"}
            payload_no_sf = _build_datadog_payload("test.event", ctx_no_sf, 1)
            assert payload_no_sf["hostname"] == "", "No sf context should result in empty hostname"
            
            print("[PASS] DataDog hostname logic test passed")
            
        except Exception as e:
            print(f"✗ DataDog hostname logic test failed: {e}")
            return False
        finally:
            os.environ.pop('SFQ_TELEMETRY', None)

def test_datadog_authentication():
    """Test DataDog authentication header"""
    print("Testing DataDog authentication...")
    
    try:
        from sfq.telemetry import _Sender
        
        # Create DataDog sender
        sender = _Sender(
            "https://http-intake.logs.us3.datadoghq.com/api/v2/logs",
            None,  # user_id not used for DataDog
            "test_datadog_api_key",
            provider="DATADOG"
        )
        
        # Mock the HTTP connection
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b''
        
        with patch('http.client.HTTPSConnection') as mock_conn:
            mock_conn_instance = MagicMock()
            mock_conn_instance.getresponse.return_value = mock_response
            mock_conn.return_value = mock_conn_instance
            
            # Test sending a payload
            test_payload = {
                "ddsource": "salesforce",
                "service": "salesforce", 
                "hostname": "test.org",
                "message": "test message",
                "ddtags": "source:salesforce"
            }
            
            sender._post(test_payload)
            
            # Verify the request was made with proper DataDog authentication
            call_args = mock_conn_instance.request.call_args
            headers = call_args[1]['headers']
            
            assert 'DD-API-KEY' in headers, "Missing DD-API-KEY header"
            assert headers['DD-API-KEY'] == "test_datadog_api_key", f"Expected test_datadog_api_key, got {headers['DD-API-KEY']}"
            assert 'Authorization' not in headers, "DataDog should not use Authorization header"
            
            print("[PASS] DataDog authentication test passed")
            
    except Exception as e:
        print(f"✗ DataDog authentication test failed: {e}")
        return False

def test_base64_datadog_credentials():
    """Test base64 encoded DataDog credentials"""
    print("Testing base64 encoded DataDog credentials...")
    
    # Create DataDog credentials and encode as base64
    datadog_creds = {
        "URL": "https://http-intake.logs.us3.datadoghq.com/api/v2/logs",
        "DD_API_KEY": "test_datadog_api_key",
        "PROVIDER": "DATADOG"
    }
    
    b64_creds = base64.b64encode(json.dumps(datadog_creds).encode()).decode()
    
    with patch('sfq.telemetry.TelemetryConfig._fetch_from_base64') as mock_decode:
        mock_decode.return_value = datadog_creds
        
        os.environ['SFQ_GRAFANACLOUD_URL'] = b64_creds
        os.environ['SFQ_TELEMETRY'] = '2'
        
        try:
            from sfq.telemetry import TelemetryConfig
            
            config = TelemetryConfig()
            
            # Verify base64 decoding and provider detection
            assert config.provider == "DATADOG", f"Expected DATADOG, got {config.provider}"
            assert config.dd_api_key == "test_datadog_api_key", "API key should be loaded from base64"
            
            print("[PASS] Base64 DataDog credentials test passed")
            
        except Exception as e:
            print(f"✗ Base64 DataDog credentials test failed: {e}")
            return False
        finally:
            os.environ.pop('SFQ_GRAFANACLOUD_URL', None)
            os.environ.pop('SFQ_TELEMETRY', None)

def main():
    """Run all DataDog integration tests"""
    print("Running DataDog Telemetry Integration Tests...\n")
    
    tests = [
        test_datadog_provider_detection,
        test_grafana_backward_compatibility,
        test_datadog_payload_format,
        test_datadog_environment_overrides,
        test_datadog_hostname_logic,
        test_datadog_authentication,
        test_base64_datadog_credentials
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"Test {test.__name__} failed with exception: {e}")
        print()
    
    print(f"Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("[SUCCESS] All DataDog integration tests passed!")
        return 0
    else:
        print("[FAILURE] Some tests failed. Please check the implementation.")
        return 1

if __name__ == "__main__":
    sys.exit(main())