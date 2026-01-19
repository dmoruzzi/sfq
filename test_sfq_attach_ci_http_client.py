#!/usr/bin/env python3
"""
Test to verify that the SFQ_ATTACH_CI fix addresses the specific test failures.
"""

import os
import sys
sys.path.insert(0, 'src')

from unittest.mock import Mock
from sfq.http_client import HTTPClient
from sfq.auth import AuthManager

def test_http_client_with_sfq_attach_ci_false():
    """Test that when SFQ_ATTACH_CI is false, no additional headers are attached."""
    # Set SFQ_ATTACH_CI to false
    os.environ['SFQ_ATTACH_CI'] = "false"
    
    # Set SFQ_HEADERS to simulate the test environment
    os.environ['SFQ_HEADERS'] = "custom_key:custom_value|test_header:test_value"
    
    # Create a mock auth manager
    auth_manager = Mock(spec=AuthManager)
    auth_manager.instance_url = "https://test.my.salesforce.com"
    auth_manager.api_version = "v65.0"
    auth_manager.access_token = "test_token_123"
    auth_manager.get_proxy_config.return_value = None
    auth_manager.get_instance_netloc.return_value = "test.my.salesforce.com"
    auth_manager.needs_token_refresh.return_value = False
    auth_manager.get_auth_headers.return_value = {
        "Authorization": "Bearer test_token_123"
    }
    
    # Create HTTPClient
    http_client = HTTPClient(
        auth_manager=auth_manager,
        user_agent="test-agent/1.0",
        sforce_client="test-client",
    )
    
    # Test get_common_headers with auth
    headers = http_client.get_common_headers(include_auth=True)
    
    expected_headers = {
        "User-Agent": "test-agent/1.0",
        "Sforce-Call-Options": "client=test-client",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": "Bearer test_token_123",
    }
    
    print(f"Headers with auth: {headers}")
    
    # Verify no additional headers are present
    assert headers == expected_headers, f"Expected {expected_headers}, got {headers}"
    
    # Specifically check that the custom headers are NOT present
    assert 'x-sfdc-addinfo-custom_key' not in headers
    assert 'x-sfdc-addinfo-test_header' not in headers
    
    # Test get_common_headers without auth
    headers_no_auth = http_client.get_common_headers(include_auth=False)
    
    expected_headers_no_auth = {
        "User-Agent": "test-agent/1.0",
        "Sforce-Call-Options": "client=test-client",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    
    print(f"Headers without auth: {headers_no_auth}")
    
    # Verify no additional headers are present
    assert headers_no_auth == expected_headers_no_auth
    
    # Specifically check that the custom headers are NOT present
    assert 'x-sfdc-addinfo-custom_key' not in headers_no_auth
    assert 'x-sfdc-addinfo-test_header' not in headers_no_auth
    
    print("Test passed: SFQ_ATTACH_CI=false correctly prevents all additional headers")

if __name__ == "__main__":
    print("Testing SFQ_ATTACH_CI fix for HTTP client...")
    
    try:
        test_http_client_with_sfq_attach_ci_false()
        print("\nTest passed! The fix correctly addresses the test failures.")
    except Exception as e:
        print(f"\nTest failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)