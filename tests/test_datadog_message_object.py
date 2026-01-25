#!/usr/bin/env python3
"""
Pytest for DataDog message format requirement.
Tests that the message field is sent as an object instead of a JSON string.
"""

import json
import os
import sys
import pytest
from unittest.mock import patch

# Add src to path for testing
sys.path.insert(0, 'src')


def test_datadog_message_as_object_not_string():
    """Test that DataDog payload has message as object, not JSON string"""
    
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
            
            # Test context data matching the user's example
            test_ctx = {
                'method': 'GET',
                'status': 200,
                'duration_ms': 174,
                'sf': {
                    'instance_url': 'https://example.my.salesforce.com',
                    'org_id': '00D5e000000XXXX'
                },
                'request_headers': {
                    'User-Agent': 'sfq/0.0.53',
                    'Sforce-Call-Options': 'client=sfq/0.0.53'
                }
            }
            
            # Build the DataDog payload
            payload = _build_datadog_payload('http.request', test_ctx, 1)
            
            # Verify the basic structure
            assert 'ddsource' in payload, "Missing ddsource field"
            assert 'service' in payload, "Missing service field"
            assert 'hostname' in payload, "Missing hostname field"
            assert 'message' in payload, "Missing message field"
            assert 'ddtags' in payload, "Missing ddtags field"
            
            # The key requirement: message should be a dict/object, not a string
            assert isinstance(payload['message'], dict), \
                f"Message should be a dict/object, but got {type(payload['message'])}"
            
            # Verify message content structure matches user's requirement
            message = payload['message']
            assert 'timestamp' in message, "Message missing timestamp"
            assert 'sdk' in message, "Message missing sdk"
            assert message['sdk'] == 'sfq', "SDK should be 'sfq'"
            assert 'sdk_version' in message, "Message missing sdk_version"
            assert 'event_type' in message, "Message missing event_type"
            assert message['event_type'] == 'http.request', "Event type should be 'http.request'"
            assert 'client_id' in message, "Message missing client_id"
            assert 'telemetry_level' in message, "Message missing telemetry_level"
            assert message['telemetry_level'] == 1, "Telemetry level should be 1"
            assert 'trace_id' in message, "Message missing trace_id"
            assert 'span' in message, "Message missing span"
            assert 'log_level' in message, "Message missing log_level"
            assert message['log_level'] == 'INFO', "Log level should be INFO for level 1"
            assert 'payload' in message, "Message missing payload"
            
            # Verify payload content
            payload_data = message['payload']
            assert 'method' in payload_data, "Payload missing method"
            assert payload_data['method'] == 'GET', "Method should be GET"
            assert 'status_code' in payload_data, "Payload missing status_code"
            assert payload_data['status_code'] == 200, "Status code should be 200"
            assert 'duration_ms' in payload_data, "Payload missing duration_ms"
            assert payload_data['duration_ms'] == 174, "Duration should be 174"
            assert 'environment' in payload_data, "Payload missing environment"
            
            # Verify environment details
            environment = payload_data['environment']
            assert 'os' in environment, "Environment missing os"
            assert 'os_release' in environment, "Environment missing os_release"
            assert 'python_version' in environment, "Environment missing python_version"
            assert 'sforce_client' in environment, "Environment missing sforce_client"
            assert environment['sforce_client'] == 'sfq/0.0.53', "Sforce client should match"
            
            # Verify that message is NOT a JSON string (this was the old behavior)
            assert not isinstance(payload['message'], str), \
                "Message should NOT be a JSON string (old behavior)"
            
            # Verify the overall structure matches the user's desired format
            expected_structure = {
                "ddsource": "salesforce",
                "service": "salesforce",
                "hostname": "00D5e000000XXXX",  # org_id for level 1
                "message": {
                    "timestamp": str,  # Will be a string like "2026-01-19T09:21:05Z"
                    "sdk": "sfq",
                    "sdk_version": str,  # Version string
                    "event_type": "http.request",
                    "client_id": str,  # SHA256 hash
                    "telemetry_level": 1,
                    "trace_id": str,  # UUID
                    "span": "default",
                    "log_level": "INFO",
                    "payload": {
                        "method": "GET",
                        "status_code": 200,
                        "duration_ms": 174,
                        "environment": {
                            "os": "Windows",
                            "os_release": "11",
                            "python_version": str,  # Python version
                            "sforce_client": "sfq/0.0.53"
                        }
                    }
                },
                "ddtags": "source:salesforce"
            }
            
            # Verify structure matches expectations
            assert payload['ddsource'] == expected_structure['ddsource']
            assert payload['service'] == expected_structure['service']
            assert payload['ddtags'] == expected_structure['ddtags']
            assert message['sdk'] == expected_structure['message']['sdk']
            assert message['event_type'] == expected_structure['message']['event_type']
            assert message['telemetry_level'] == expected_structure['message']['telemetry_level']
            assert message['span'] == expected_structure['message']['span']
            assert message['log_level'] == expected_structure['message']['log_level']
            assert payload_data['method'] == expected_structure['message']['payload']['method']
            assert payload_data['status_code'] == expected_structure['message']['payload']['status_code']
            assert payload_data['duration_ms'] == expected_structure['message']['payload']['duration_ms']
            assert environment['sforce_client'] == expected_structure['message']['payload']['environment']['sforce_client']
            
        finally:
            os.environ.pop('SFQ_TELEMETRY', None)


def test_datadog_message_object_vs_string_comparison():
    """Test that demonstrates the difference between old (string) and new (object) format"""
    
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
            
            test_ctx = {'method': 'GET', 'status': 200, 'sf': {'org_id': 'test_org'}}
            payload = _build_datadog_payload('http.request', test_ctx, 1)
            
            # NEW BEHAVIOR: message is an object (dict)
            assert isinstance(payload['message'], dict), \
                "NEW: Message should be a dict/object"
            
            # OLD BEHAVIOR would have been: message is a JSON string
            # This would have been the old format:
            # assert isinstance(payload['message'], str)
            # old_message = json.loads(payload['message'])
            
            # Verify we can access message fields directly (new behavior)
            assert 'event_type' in payload['message'], \
                "Should be able to access event_type directly from message object"
            assert payload['message']['event_type'] == 'http.request', \
                "Should get event_type directly from message object"
            
        finally:
            os.environ.pop('SFQ_TELEMETRY', None)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])