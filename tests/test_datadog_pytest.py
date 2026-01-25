#!/usr/bin/env python3
"""
PyTest suite for DataDog telemetry integration
"""

import os
import sys
import json
import base64
import pytest
from unittest.mock import patch, MagicMock

# Add src to path for testing
sys.path.insert(0, 'src')


class TestDataDogProviderDetection:
    """Test DataDog provider detection functionality"""
    
    def test_datadog_provider_detection_explicit(self):
        """Test explicit DataDog provider detection"""
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
                
                assert config.provider == "DATADOG"
                assert config.dd_api_key == "test_datadog_api_key"
                assert config.api_key == "test_datadog_api_key"
                assert config.user_id is None
                
            finally:
                os.environ.pop('SFQ_TELEMETRY', None)
    
    def test_datadog_provider_detection_case_insensitive(self):
        """Test case-insensitive provider detection"""
        datadog_creds = {
            "URL": "https://http-intake.logs.us3.datadoghq.com/api/v2/logs",
            "DD_API_KEY": "test_datadog_api_key",
            "PROVIDER": "datadog"  # lowercase
        }
        
        with patch('sfq.telemetry.TelemetryConfig._fetch_grafana_credentials') as mock_fetch:
            mock_fetch.return_value = datadog_creds
            os.environ['SFQ_TELEMETRY'] = '2'
            
            try:
                from sfq.telemetry import TelemetryConfig
                
                config = TelemetryConfig()
                
                assert config.provider == "DATADOG"  # Should be uppercase
                assert config.dd_api_key == "test_datadog_api_key"
                
            finally:
                os.environ.pop('SFQ_TELEMETRY', None)
    
    def test_grafana_default_provider(self):
        """Test default Grafana provider when no PROVIDER specified"""
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
                
                assert config.provider == "GRAFANA"  # Default
                assert config.user_id == "1234567"
                assert config.api_key == "test_grafana_api_key"
                assert config.dd_api_key is None
                
            finally:
                os.environ.pop('SFQ_TELEMETRY', None)


class TestDataDogPayloadBuilding:
    """Test DataDog payload building functionality"""
    
    def test_datadog_payload_format(self):
        """Test DataDog payload format structure"""
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
                
                test_ctx = {
                    "method": "GET",
                    "endpoint": "/test/endpoint",
                    "status": 200,
                    "sf": {
                        "org_id": "00D123456789ABCDEF"
                    }
                }
                
                payload = _build_datadog_payload("test.event", test_ctx, 1)
                
                # Verify required fields
                assert "ddsource" in payload
                assert "service" in payload
                assert "hostname" in payload
                assert "message" in payload
                assert "ddtags" in payload
                
                # Verify defaults
                assert payload["ddsource"] == "salesforce"
                assert payload["service"] == "salesforce"
                assert payload["hostname"] == "00D123456789ABCDEF"
                assert payload["ddtags"] == "source:salesforce"
                
                # Verify message is an object (not JSON string)
                message = payload["message"]
                assert isinstance(message, dict), f"Message should be a dict/object, got {type(message)}"
                assert "event_type" in message
                assert message["event_type"] == "test.event"
                
            finally:
                os.environ.pop('SFQ_TELEMETRY', None)
    
    def test_datadog_payload_environment_overrides(self):
        """Test DataDog payload with environment variable overrides"""
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
                
                test_ctx = {"method": "GET", "endpoint": "/test"}
                payload = _build_datadog_payload("test.event", test_ctx, 1)
                
                # Verify environment overrides applied
                assert payload["ddsource"] == "custom_source"
                assert payload["service"] == "custom_service"
                assert "env:test" in payload["ddtags"]
                assert "type:unit" in payload["ddtags"]
                
            finally:
                os.environ.pop('SFQ_TELEMETRY', None)
                os.environ.pop('DD_SOURCE', None)
                os.environ.pop('DD_SERVICE', None)
                os.environ.pop('DD_TAGS', None)
    
    def test_datadog_hostname_logic_level_2(self):
        """Test DataDog hostname logic for level 2 (should use instance_url)"""
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
                
                ctx = {
                    "sf": {
                        "instance_url": "https://test.salesforce.com",
                        "org_id": "00D123456789ABCDEF"
                    }
                }
                
                payload = _build_datadog_payload("test.event", ctx, 2)
                assert payload["hostname"] == "https://test.salesforce.com"
                
            finally:
                os.environ.pop('SFQ_TELEMETRY', None)
    
    def test_datadog_hostname_logic_level_1(self):
        """Test DataDog hostname logic for level 1 (should use org_id)"""
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
                
                ctx = {
                    "sf": {
                        "org_id": "00D123456789ABCDEF"
                    }
                }
                
                payload = _build_datadog_payload("test.event", ctx, 1)
                assert payload["hostname"] == "00D123456789ABCDEF"
                
            finally:
                os.environ.pop('SFQ_TELEMETRY', None)
    
    def test_datadog_hostname_logic_no_sf_context(self):
        """Test DataDog hostname logic with no Salesforce context"""
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
                
                ctx = {"other": "data"}
                payload = _build_datadog_payload("test.event", ctx, 1)
                assert payload["hostname"] == ""
                
            finally:
                os.environ.pop('SFQ_TELEMETRY', None)


class TestDataDogAuthentication:
    """Test DataDog authentication functionality"""
    
    def test_datadog_authentication_header(self):
        """Test DataDog API key authentication header"""
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
            
            assert 'DD-API-KEY' in headers
            assert headers['DD-API-KEY'] == "test_datadog_api_key"
            assert 'Authorization' not in headers
    
    def test_grafana_authentication_unchanged(self):
        """Test that Grafana authentication remains unchanged"""
        from sfq.telemetry import _Sender
        
        # Create Grafana sender
        sender = _Sender(
            "https://logs-prod-001.grafana.net/loki/api/v1/push",
            "1234567",
            "test_grafana_api_key",
            provider="GRAFANA"
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
                "streams": [{
                    "stream": {"test": "stream"},
                    "values": [["1234567890", "test log line"]]
                }]
            }
            
            sender._post(test_payload)
            
            # Verify the request was made with proper Grafana authentication
            call_args = mock_conn_instance.request.call_args
            headers = call_args[1]['headers']
            
            assert 'Authorization' in headers
            assert headers['Authorization'].startswith('Basic ')
            assert 'DD-API-KEY' not in headers


class TestDataDogConfigurationLoading:
    """Test DataDog configuration loading functionality"""
    
    def test_datadog_credentials_validation(self):
        """Test DataDog credentials validation"""
        # Test with missing DD_API_KEY
        invalid_creds = {
            "URL": "https://http-intake.logs.us3.datadoghq.com/api/v2/logs",
            "PROVIDER": "DATADOG"
            # Missing DD_API_KEY
        }
        
        with patch('sfq.telemetry.TelemetryConfig._fetch_grafana_credentials') as mock_fetch:
            mock_fetch.return_value = invalid_creds
            os.environ['SFQ_TELEMETRY'] = '2'
            
            try:
                from sfq.telemetry import TelemetryConfig
                
                # Should raise ValueError for missing DD_API_KEY
                with pytest.raises(ValueError, match="DataDog credentials require DD_API_KEY"):
                    config = TelemetryConfig()
                    
            finally:
                os.environ.pop('SFQ_TELEMETRY', None)
    
    def test_datadog_api_key_environment_override(self):
        """Test DataDog API key environment variable override"""
        datadog_creds = {
            "URL": "https://http-intake.logs.us3.datadoghq.com/api/v2/logs",
            "DD_API_KEY": "original_api_key",
            "PROVIDER": "DATADOG"
        }
        
        with patch('sfq.telemetry.TelemetryConfig._fetch_grafana_credentials') as mock_fetch:
            mock_fetch.return_value = datadog_creds
            
            # Set environment override
            os.environ['SFQ_TELEMETRY'] = '2'
            os.environ['DD_API_KEY'] = 'environment_override_key'
            
            try:
                from sfq.telemetry import TelemetryConfig
                
                config = TelemetryConfig()
                
                # Should use environment override
                assert config.dd_api_key == "environment_override_key"
                assert config.api_key == "environment_override_key"
                
            finally:
                os.environ.pop('SFQ_TELEMETRY', None)
                os.environ.pop('DD_API_KEY', None)
    
    def test_base64_datadog_credentials(self):
        """Test base64 encoded DataDog credentials"""
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
                
                assert config.provider == "DATADOG"
                assert config.dd_api_key == "test_datadog_api_key"
                
            finally:
                os.environ.pop('SFQ_GRAFANACLOUD_URL', None)
                os.environ.pop('SFQ_TELEMETRY', None)


class TestDataDogEmitFunction:
    """Test DataDog emit function routing"""
    
    def test_emit_routes_to_grafana_by_default(self):
        """Test that emit function routes to Grafana by default"""
        grafana_creds = {
            "URL": "https://logs-prod-001.grafana.net/loki/api/v1/push",
            "USER_ID": "1234567",
            "API_KEY": "test_grafana_api_key"
        }
        
        with patch('sfq.telemetry.TelemetryConfig._fetch_grafana_credentials') as mock_fetch:
            mock_fetch.return_value = grafana_creds
            os.environ['SFQ_TELEMETRY'] = '2'
            
            try:
                from sfq.telemetry import emit, _build_grafana_payload
                
                # Mock the Grafana payload builder to verify it's called
                with patch('sfq.telemetry._build_grafana_payload') as mock_grafana_builder:
                    mock_grafana_builder.return_value = {"streams": [{"test": "stream"}]}
                    
                    # Mock the sender
                    with patch('sfq.telemetry._ensure_sender') as mock_sender:
                        mock_sender_instance = MagicMock()
                        mock_sender.return_value = mock_sender_instance
                        
                        # Emit a test event
                        test_ctx = {"method": "GET", "endpoint": "/test"}
                        emit("test.event", test_ctx)
                        
                        # Verify Grafana builder was called
                        mock_grafana_builder.assert_called_once()
                        
            finally:
                os.environ.pop('SFQ_TELEMETRY', None)


class TestDataDogErrorHandling:
    """Test DataDog error handling functionality"""
    
    def test_datadog_credentials_validation(self):
        """Test that DataDog credentials validation works correctly"""
        # Test with missing DD_API_KEY - should raise ValueError
        invalid_creds = {
            "URL": "https://http-intake.logs.us3.datadoghq.com/api/v2/logs",
            "PROVIDER": "DATADOG"
            # Missing DD_API_KEY
        }
        
        with patch('sfq.telemetry.TelemetryConfig._fetch_grafana_credentials') as mock_fetch:
            mock_fetch.return_value = invalid_creds
            os.environ['SFQ_TELEMETRY'] = '2'
            
            try:
                from sfq.telemetry import TelemetryConfig
                
                # Should raise ValueError for missing DD_API_KEY
                with pytest.raises(ValueError, match="DataDog credentials require DD_API_KEY"):
                    config = TelemetryConfig()
                    
            finally:
                os.environ.pop('SFQ_TELEMETRY', None)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])